from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.sources.models import Source, SourceRecord
from apps.jobs.models import Job
from apps.scoring.models import RuleSet, ScoreOverride, ScoreSnapshot
from apps.signals.models import Signal

from .models import Company, CompanyCnae


class CompanyViewsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="sales", password="secret")
        self.client.force_login(self.user)
        self.company = Company.objects.create(
            cnpj="12345678000199",
            legal_name="Metalúrgica Horizonte Ltda",
            trade_name="Horizonte",
            company_type=Company.Type.INDUSTRY,
            registration_status=Company.RegistrationStatus.ACTIVE,
            state="MG",
            municipality="Contagem",
        )
        CompanyCnae.objects.create(
            company=self.company,
            code="2511000",
            is_primary=True,
            observed_at=timezone.now(),
        )

    def create_snapshot(
        self, company, *, priority, classification, product="MES", as_of=None
    ):
        return ScoreSnapshot.objects.create(
            company=company,
            rule_set=RuleSet.objects.get(target=RuleSet.Target.INDUSTRY, active=True),
            as_of=as_of or timezone.now(),
            dimensions={},
            priority=priority,
            calculated_classification=classification,
            best_product=product,
        )

    def test_list_requires_authentication(self):
        self.client.logout()
        response = self.client.get(reverse("company-list"))
        self.assertRedirects(
            response,
            f'{reverse("login")}?next={reverse("company-list")}',
            fetch_redirect_response=False,
        )

    def test_list_filters_industries_without_downloading_anything(self):
        Company.objects.create(
            legal_name="Consultoria Horizonte",
            company_type=Company.Type.CONSULTANCY,
            state="MG",
        )
        response = self.client.get(reverse("company-list"), {"q": "12345678", "state": "mg"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Horizonte")
        self.assertNotContains(response, "Consultoria Horizonte")
        self.assertEqual(response.context["page"].paginator.per_page, 50)

    def test_list_is_paginated(self):
        Company.objects.bulk_create(
            [
                Company(legal_name=f"Indústria {index:02d}", company_type=Company.Type.INDUSTRY)
                for index in range(50)
            ]
        )

        response = self.client.get(reverse("company-list"))

        self.assertEqual(response.context["page"].paginator.count, 51)
        self.assertEqual(len(response.context["page"].object_list), 50)
        self.assertContains(response, "Próxima")

    def test_list_defaults_to_effective_priority_with_unscored_companies_last(self):
        higher = Company.objects.create(
            legal_name="Indústria Prioritária",
            company_type=Company.Type.INDUSTRY,
        )
        unscored = Company.objects.create(
            legal_name="Indústria sem Score",
            company_type=Company.Type.INDUSTRY,
        )
        self.create_snapshot(self.company, priority="30", classification="COLD")
        self.create_snapshot(higher, priority="85", classification="HOT", product="CMMS")

        response = self.client.get(reverse("company-list"))

        companies = list(response.context["page"].object_list)
        self.assertEqual(companies, [higher, self.company, unscored])
        self.assertContains(response, "CMMS")

    def test_ranking_combines_score_product_recency_and_active_signal_filters(self):
        snapshot = self.create_snapshot(
            self.company,
            priority="80",
            classification="HOT",
            product="CMMS",
            as_of=timezone.now() - timedelta(days=2),
        )
        Signal.objects.create(
            company=self.company,
            signal_type="pcm",
            product=Signal.Product.CMMS,
            title="PCM",
            evidence_hash="f" * 64,
            observed_at=snapshot.as_of,
        )

        response = self.client.get(
            reverse("company-list"),
            {
                "classification": "HOT",
                "best_product": "CMMS",
                "minimum_priority": "75",
                "scored_since": (timezone.localdate() - timedelta(days=3)).isoformat(),
                "signal_type": "pcm",
                "ordering": "score_recent",
            },
        )

        self.assertEqual(response.context["page"].paginator.count, 1)
        self.assertEqual(response.context["page"].object_list[0], self.company)

        Signal.objects.filter(company=self.company).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        expired_response = self.client.get(reverse("company-list"), {"signal_type": "pcm"})
        self.assertEqual(expired_response.context["page"].paginator.count, 0)

    def test_active_override_controls_effective_ranking_without_changing_snapshot(self):
        snapshot = self.create_snapshot(
            self.company, priority="20", classification="COLD", product="PULSE"
        )
        ScoreOverride.objects.create(
            company=self.company,
            snapshot=snapshot,
            classification="HOT",
            priority="95",
            reason="Validação comercial",
            created_by=self.user,
        )

        response = self.client.get(
            reverse("company-list"),
            {"classification": "HOT", "minimum_priority": "90"},
        )

        company = response.context["page"].object_list[0]
        self.assertEqual(company.effective_priority, Decimal("95"))
        self.assertEqual(company.effective_classification, "HOT")
        snapshot.refresh_from_db()
        self.assertEqual(str(snapshot.priority), "20.000")
        self.assertEqual(snapshot.calculated_classification, "COLD")

    def test_csv_export_respects_filters_and_escapes_spreadsheet_formulas(self):
        dangerous = Company.objects.create(
            cnpj="99888777000166",
            legal_name="=CMD|' /C calc'!A0",
            company_type=Company.Type.INDUSTRY,
            state="SP",
        )
        self.create_snapshot(dangerous, priority="90", classification="HOT", product="MES")

        response = self.client.get(
            reverse("company-export"),
            {"q": "99888777", "classification": "HOT"},
        )
        content = b"".join(response.streaming_content).decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Export-Limit"], "500")
        self.assertIn("ranking-industrias.csv", response["Content-Disposition"])
        self.assertIn("'=CMD", content)
        self.assertIn("99888777000166", content)
        self.assertNotIn(self.company.cnpj, content)

    def test_csv_export_rejects_invalid_filters_and_caps_rows(self):
        invalid = self.client.get(reverse("company-export"), {"minimum_priority": "101"})
        self.assertEqual(invalid.status_code, 400)

        Company.objects.bulk_create(
            [
                Company(legal_name=f"Exportação {index:03d}", company_type=Company.Type.INDUSTRY)
                for index in range(501)
            ]
        )
        response = self.client.get(reverse("company-export"))
        content = b"".join(response.streaming_content).decode("utf-8")
        self.assertEqual(len(content.splitlines()), 501)

    def test_detail_shows_cnae_and_provenance(self):
        source, _ = Source.objects.get_or_create(key="test-source", defaults={"name": "Fonte teste"})
        SourceRecord.objects.create(
            source=source,
            external_id=self.company.cnpj,
            company=self.company,
            payload={"cnpj": self.company.cnpj},
            payload_hash="a" * 64,
            dataset_reference="2026-08",
            observed_at=timezone.now(),
        )

        response = self.client.get(reverse("company-detail", args=[self.company.pk]))

        self.assertContains(response, "2511000")
        self.assertContains(response, "Fonte teste")
        self.assertContains(response, "2026-08")

    def test_score_action_enqueues_one_job_for_the_current_data_version(self):
        first = self.client.post(reverse("company-score", args=[self.company.pk]))
        second = self.client.post(reverse("company-score", args=[self.company.pk]))

        self.assertRedirects(first, reverse("company-detail", args=[self.company.pk]))
        self.assertRedirects(second, reverse("company-detail", args=[self.company.pk]))
        job = Job.objects.get(type=Job.Type.CALCULATE_SCORE)
        self.assertEqual(job.payload["company_id"], str(self.company.pk))

    def test_signal_action_enqueues_one_job_for_current_evidence(self):
        source, _ = Source.objects.get_or_create(
            key="signal-source", defaults={"name": "Fonte de sinais"}
        )
        SourceRecord.objects.create(
            source=source,
            external_id=self.company.cnpj,
            company=self.company,
            payload={"description": "Projeto de OEE"},
            payload_hash="b" * 64,
            observed_at=timezone.now(),
        )

        first = self.client.post(
            reverse("company-detect-signals", args=[self.company.pk])
        )
        second = self.client.post(
            reverse("company-detect-signals", args=[self.company.pk])
        )

        self.assertRedirects(first, reverse("company-detail", args=[self.company.pk]))
        self.assertRedirects(second, reverse("company-detail", args=[self.company.pk]))
        self.assertEqual(Job.objects.filter(type=Job.Type.DETECT_SIGNALS).count(), 1)

    def test_website_action_requires_a_url_and_is_daily_idempotent(self):
        missing = self.client.post(
            reverse("company-crawl-website", args=[self.company.pk])
        )
        self.assertRedirects(missing, reverse("company-detail", args=[self.company.pk]))
        self.assertFalse(Job.objects.filter(type=Job.Type.CRAWL_WEBSITE).exists())

        self.company.website = "https://example.com/"
        self.company.website_domain = "example.com"
        self.company.save(update_fields=("website", "website_domain", "updated_at"))
        self.client.post(reverse("company-crawl-website", args=[self.company.pk]))
        self.client.post(reverse("company-crawl-website", args=[self.company.pk]))
        self.assertEqual(Job.objects.filter(type=Job.Type.CRAWL_WEBSITE).count(), 1)
