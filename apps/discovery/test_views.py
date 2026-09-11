import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.companies.models import Company
from apps.jobs.models import Job
from apps.sources.models import CnpjDataset, CnpjDatasetFile, Source

from .coverage import record_source_coverage
from .models import DiscoveryQuery, QueryResult, QueryRun


class DiscoveryViewsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="query-admin", password="secret")
        self.client.force_login(self.user)

    def create_query(self):
        return DiscoveryQuery.objects.create(
            name="Alimentos MG",
            entity_target=DiscoveryQuery.EntityTarget.INDUSTRY,
            filters={
                "registration_statuses": ["02"],
                "states": ["MG"],
                "cnae_prefixes": ["10"],
            },
            created_by=self.user,
        )

    def test_create_query_from_structured_form(self):
        response = self.client.post(
            reverse("query-create"),
            {
                "name": "Alimentos MG",
                "entity_target": "INDUSTRY",
                "state": "mg",
                "municipality_code": "",
                "cnae_prefixes": "10, 10911",
            },
        )

        query = DiscoveryQuery.objects.get()
        self.assertRedirects(response, reverse("query-detail", args=[query.pk]))
        self.assertEqual(query.normalized_filters["states"], ["MG"])
        self.assertEqual(query.normalized_filters["cnae_prefixes"], ["10", "10911"])

    def test_query_requires_a_selective_filter(self):
        response = self.client.post(
            reverse("query-create"),
            {"name": "Aberta", "entity_target": "INDUSTRY"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Informe ao menos UF, município ou CNAE")
        self.assertFalse(DiscoveryQuery.objects.exists())

    @override_settings(CNPJ_SOURCE_BASE_URL="")
    def test_detail_blocks_preview_without_source_manifest(self):
        query = self.create_query()

        response = self.client.get(reverse("query-detail", args=[query.pk]))

        self.assertContains(response, "origem CNPJ ainda não foi configurada")
        self.assertContains(response, "disabled")

    def test_preview_is_enqueued_only_after_capacity_check(self):
        query = self.create_query()
        source = Source.objects.get(key="receita-cnpj")
        dataset = CnpjDataset.objects.create(
            source=source,
            reference="2026-08",
            status=CnpjDataset.Status.READY,
            is_current=True,
            discovered_at=timezone.now(),
        )
        source_file = CnpjDatasetFile.objects.create(
            dataset=dataset,
            kind=CnpjDatasetFile.Kind.ESTABLISHMENTS,
            part_number=1,
            url="https://receita.example/CNPJ/2026-08/Estabelecimentos1.zip",
            size_bytes=1024,
        )
        with tempfile.TemporaryDirectory() as temporary, override_settings(
            TEMP_DATA_DIR=Path(temporary),
            CNPJ_SOURCE_BASE_URL="https://receita.example/CNPJ/",
            CNPJ_WEBDAV_TOKEN="public-token",
            CNPJ_MAX_TEMP_BYTES=2048,
            CNPJ_MIN_FREE_BYTES=0,
        ):
            response = self.client.post(
                reverse("query-run-preview", args=[query.pk]),
                {"max_results": 50},
            )

        run = QueryRun.objects.get()
        job = Job.objects.get(type=Job.Type.DISCOVER_CNPJ)
        self.assertRedirects(response, reverse("query-run-detail", args=[run.pk]))
        self.assertEqual(job.payload["mode"], "PREVIEW")
        self.assertEqual(job.payload["max_results"], 50)
        self.assertEqual(job.payload["source_url"], source_file.url)

    def test_staff_user_can_enqueue_manifest_sync_only_once_per_day(self):
        self.user.is_staff = True
        self.user.save(update_fields=("is_staff",))

        first = self.client.post(reverse("manifest-sync"))
        second = self.client.post(reverse("manifest-sync"))

        self.assertRedirects(first, reverse("query-list"))
        self.assertRedirects(second, reverse("query-list"))
        self.assertEqual(Job.objects.filter(type=Job.Type.SYNC_CNPJ_SOURCE).count(), 1)

    def test_run_detail_displays_selective_cnpj_coverage(self):
        query = self.create_query()
        run = QueryRun.objects.create(
            query=query,
            created_by=self.user,
            status=QueryRun.Status.PARTIAL,
            dataset_reference="2026-08",
            coverage={
                "mode": "FULL",
                "staged_candidates": 12,
                "companies": {
                    "basics_matched": 11,
                    "basics_missing": 1,
                    "rows_scanned": 300,
                    "sources_processed": 2,
                },
                "simples": {
                    "basics_matched": 12,
                    "basics_missing": 0,
                    "rows_scanned": 120,
                    "sources_processed": 1,
                },
            },
        )

        response = self.client.get(reverse("query-run-detail", args=[run.pk]))

        self.assertContains(response, "Cobertura CNPJ")
        self.assertContains(response, "Candidatos no staging")
        self.assertContains(response, "300 linhas lidas em 2 arquivo(s)")

    def test_preview_reuses_valid_exact_coverage_without_enqueuing_download(self):
        query = self.create_query()
        source = Source.objects.get(key="receita-cnpj")
        CnpjDataset.objects.create(
            source=source,
            reference="2026-08",
            status=CnpjDataset.Status.READY,
            is_current=True,
            discovered_at=timezone.now(),
        )
        company = Company.objects.create(
            cnpj="11111111000191",
            trade_name="ALIMENTOS MINAS",
            company_type=Company.Type.INDUSTRY,
            state="MG",
        )
        covered_run = QueryRun.objects.create(
            query=query,
            created_by=self.user,
            status=QueryRun.Status.SUCCEEDED,
            dataset_reference="2026-08",
            records_matched=1,
            started_at=timezone.now(),
            finished_at=timezone.now(),
        )
        QueryResult.objects.create(
            query_run=covered_run,
            company=company,
            source=source,
            rank=1,
        )
        coverage = record_source_coverage(source=source, query_run=covered_run)

        detail_response = self.client.get(reverse("query-detail", args=[query.pk]))

        response = self.client.post(
            reverse("query-run-preview", args=[query.pk]),
            {"max_results": 50},
        )

        cached_run = query.runs.exclude(pk=covered_run.pk).get()
        self.assertContains(detail_response, "nenhum download será realizado")
        self.assertRedirects(response, reverse("query-run-detail", args=[cached_run.pk]))
        self.assertEqual(cached_run.coverage["mode"], "CACHE")
        self.assertEqual(cached_run.coverage["source_coverage_id"], coverage.pk)
        self.assertEqual(cached_run.records_processed, 0)
        self.assertEqual(cached_run.results.get().company, company)
        self.assertFalse(Job.objects.filter(type=Job.Type.DISCOVER_CNPJ).exists())
