from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.sources.models import Source, SourceRecord
from apps.jobs.models import Job

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
