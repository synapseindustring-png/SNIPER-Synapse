from collections import namedtuple
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.companies.models import Company
from apps.sources.models import Source, SourceRecord

from .models import Job, JobAttempt


DiskUsage = namedtuple("DiskUsage", "total used free")


class JobOperationsViewsTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="operator", password="secret", is_staff=True
        )
        self.regular_user = get_user_model().objects.create_user(
            username="sales-ops", password="secret"
        )
        self.job = Job.objects.create(
            type=Job.Type.FIND_JOBS,
            status=Job.Status.FAILED,
            payload={
                "company_id": "company-1",
                "api_token": "never-show-this",
                "source_url": "https://example.com/jobs?token=also-secret",
            },
            idempotency_key="find-jobs:test",
            error_summary="request failed token=summary-secret",
        )
        JobAttempt.objects.create(
            job=self.job,
            attempt_number=1,
            worker_id="worker-test",
            finished_at=timezone.now(),
            succeeded=False,
            error_detail="password=attempt-secret",
            metrics={"api_key": "metric-secret", "items": 2},
        )

    def test_pages_require_authentication_and_staff(self):
        url = reverse("job-list")
        response = self.client.get(url)
        self.assertRedirects(
            response,
            f'{reverse("login")}?next={url}',
            fetch_redirect_response=False,
        )
        self.client.force_login(self.regular_user)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(
            self.client.get(reverse("job-detail", args=[self.job.pk])).status_code,
            404,
        )
        self.assertEqual(self.client.get(reverse("cnpj-source-detail")).status_code, 404)

    @patch("apps.jobs.operations.shutil.disk_usage")
    def test_list_filters_jobs_and_displays_sources_and_safe_capacity(self, disk_usage):
        disk_usage.return_value = DiskUsage(20_000, 8_000, 12_000)
        company = Company.objects.create(legal_name="Indústria Ops")
        source = Source.objects.get(key="website")
        SourceRecord.objects.create(
            source=source,
            external_id="https://ops.example/",
            company=company,
            payload={},
            payload_hash="a" * 64,
            observed_at=timezone.now(),
        )
        Job.objects.create(type=Job.Type.NOOP, status=Job.Status.SUCCEEDED)
        self.client.force_login(self.staff)

        with self.settings(CNPJ_MAX_TEMP_BYTES=10_000, CNPJ_MIN_FREE_BYTES=5_000):
            response = self.client.get(
                reverse("job-list"),
                {"job_type": Job.Type.FIND_JOBS, "status": Job.Status.FAILED},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page"].paginator.count, 1)
        self.assertEqual(response.context["storage"].safe_cnpj_capacity_bytes, 7_000)
        self.assertContains(response, "Vagas — fixture local")
        self.assertContains(response, "Website institucional")

    @patch("apps.jobs.operations.shutil.disk_usage")
    def test_list_is_paginated_at_fifty(self, disk_usage):
        disk_usage.return_value = DiskUsage(20_000, 8_000, 12_000)
        Job.objects.bulk_create([Job(type=Job.Type.NOOP) for _ in range(50)])
        self.client.force_login(self.staff)

        response = self.client.get(reverse("job-list"))

        self.assertEqual(response.context["page"].paginator.count, 51)
        self.assertEqual(len(response.context["page"].object_list), 50)
        self.assertContains(response, "Próxima")

    def test_detail_sanitizes_payload_errors_urls_and_metrics(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("job-detail", args=[self.job.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "[oculto]")
        self.assertContains(response, "https://example.com/jobs")
        for secret in (
            "never-show-this",
            "also-secret",
            "summary-secret",
            "attempt-secret",
            "metric-secret",
        ):
            self.assertNotContains(response, secret)

    @patch("apps.sources.cnpj.health.storage_status")
    def test_staff_can_open_read_only_cnpj_source_panel(self, source_storage_status):
        source_storage_status.return_value = type(
            "Storage",
            (),
            {"safe_cnpj_capacity_bytes": 10_000},
        )()
        self.client.force_login(self.staff)

        response = self.client.get(reverse("cnpj-source-detail"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Diagnóstico local e somente leitura")
        self.assertContains(response, "Sem manifesto")
