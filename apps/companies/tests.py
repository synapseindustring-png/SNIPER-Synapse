from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.sources.models import FieldObservation, Source, SourceRecord
from apps.jobs.models import Job
from apps.scoring.models import RuleSet, ScoreOverride, ScoreSnapshot
from apps.signals.models import Signal

from .corrections import correct_company
from .models import Company, CompanyCnae, CompanyCorrection


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


class CompanyCorrectionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="operator", password="secret", is_staff=True
        )
        self.company = Company.objects.create(
            cnpj="12345678000199",
            legal_name="Nome obtido na fonte",
            company_type=Company.Type.INDUSTRY,
            registration_status=Company.RegistrationStatus.ACTIVE,
            state="MG",
        )
        source = Source.objects.create(key="original", name="Fonte original")
        self.original_record = SourceRecord.objects.create(
            source=source,
            external_id=self.company.cnpj,
            company=self.company,
            payload={"legal_name": self.company.legal_name},
            payload_hash="c" * 64,
            observed_at=timezone.now(),
        )
        self.original_observation = FieldObservation.objects.create(
            company=self.company,
            source_record=self.original_record,
            field_name="legal_name",
            value=self.company.legal_name,
            normalized_value=self.company.legal_name,
            observed_at=timezone.now(),
            selected_at=timezone.now(),
            is_current=True,
        )

    def form_data(self, **changes):
        data = {
            "legal_name": self.company.legal_name,
            "trade_name": self.company.trade_name,
            "company_type": self.company.company_type,
            "registration_status": self.company.registration_status,
            "size_code": self.company.size_code,
            "legal_nature_code": self.company.legal_nature_code,
            "share_capital": "",
            "opened_on": "",
            "segment": self.company.segment,
            "street_type": self.company.street_type,
            "street": self.company.street,
            "number": self.company.number,
            "complement": self.company.complement,
            "district": self.company.district,
            "municipality": self.company.municipality,
            "municipality_code": self.company.municipality_code,
            "state": self.company.state,
            "postal_code": self.company.postal_code,
            "phone": self.company.phone,
            "email": self.company.email,
            "website": self.company.website,
            "commercial_status": self.company.commercial_status,
            "justification": "Conferência documental realizada pela operação.",
        }
        data.update(changes)
        return data

    def test_service_preserves_original_observation_and_creates_manual_evidence(self):
        company, corrections = correct_company(
            company=self.company,
            changes={
                "legal_name": "Nome corrigido",
                "website": "https://www.example.com/contato",
            },
            justification="Conferência documental realizada pela operação.",
            user=self.user,
        )

        self.assertEqual(company.legal_name, "Nome corrigido")
        self.assertEqual(company.website_domain, "example.com")
        self.assertEqual(len(corrections), 2)
        self.original_observation.refresh_from_db()
        self.assertFalse(self.original_observation.is_current)
        current = FieldObservation.objects.get(
            company=company, field_name="legal_name", is_current=True
        )
        self.assertEqual(current.value, "Nome corrigido")
        self.assertEqual(current.source_record.source.key, "manual-correction")
        correction = CompanyCorrection.objects.get(field_name="legal_name")
        self.assertEqual(correction.old_value, "Nome obtido na fonte")
        self.assertEqual(correction.new_value, "Nome corrigido")
        self.assertEqual(correction.corrected_by, self.user)
        self.assertEqual(correction.source_record, current.source_record)
        self.assertTrue(SourceRecord.objects.filter(pk=self.original_record.pk).exists())

    def test_correction_view_is_staff_only_and_cnpj_is_not_editable(self):
        regular_user = get_user_model().objects.create_user(
            username="sales", password="secret"
        )
        self.client.force_login(regular_user)
        url = reverse("company-correction", args=[self.company.pk])
        self.assertEqual(self.client.get(url).status_code, 404)

        self.client.force_login(self.user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="cnpj"')

        with self.assertRaises(PermissionError):
            correct_company(
                company=self.company,
                changes={"legal_name": "Tentativa sem permissão"},
                justification="Tentativa realizada por usuário comum.",
                user=regular_user,
            )
        self.assertEqual(CompanyCorrection.objects.count(), 0)

    def test_valid_correction_updates_company_audits_and_enqueues_score(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("company-correction", args=[self.company.pk]),
            self.form_data(legal_name="Nome revisado", state="sp"),
        )

        self.assertRedirects(
            response, reverse("company-detail", args=[self.company.pk])
        )
        self.company.refresh_from_db()
        self.assertEqual(self.company.legal_name, "Nome revisado")
        self.assertEqual(self.company.state, "SP")
        self.assertEqual(CompanyCorrection.objects.count(), 2)
        self.assertEqual(Job.objects.filter(type=Job.Type.CALCULATE_SCORE).count(), 1)
        detail = self.client.get(reverse("company-detail", args=[self.company.pk]))
        self.assertContains(detail, "Correções administrativas")
        self.assertContains(detail, "Conferência documental")
        self.assertContains(detail, "operator")

    def test_unchanged_or_poorly_justified_submission_does_not_write(self):
        self.client.force_login(self.user)
        url = reverse("company-correction", args=[self.company.pk])
        unchanged = self.client.post(url, self.form_data())
        short_reason = self.client.post(
            url,
            self.form_data(legal_name="Outro nome", justification="curta"),
        )

        self.assertEqual(unchanged.status_code, 200)
        self.assertContains(unchanged, "Altere ao menos um campo")
        self.assertEqual(short_reason.status_code, 200)
        self.assertEqual(CompanyCorrection.objects.count(), 0)
        self.company.refresh_from_db()
        self.assertEqual(self.company.legal_name, "Nome obtido na fonte")
