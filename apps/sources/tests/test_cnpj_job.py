import tempfile
import zipfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.companies.models import Company
from apps.discovery.models import DiscoveryQuery, QueryRun
from apps.jobs.models import Job
from apps.jobs.services import execute_job
from apps.sources.models import SourceRecord


FIXTURE = Path(__file__).parent / "fixtures" / "establishments.csv"


class DiscoverCnpjJobTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="job-admin")
        query = DiscoveryQuery.objects.create(
            name="Alimentos ativos em MG",
            entity_target=DiscoveryQuery.EntityTarget.INDUSTRY,
            filters={"states": ["MG"], "cnae_prefixes": ["10"]},
            created_by=user,
        )
        self.query_run = QueryRun.objects.create(query=query, created_by=user)

    def make_zip(self) -> Path:
        temp_root = Path(tempfile.gettempdir()) / "synapse-sniper"
        temp_root.mkdir(exist_ok=True)
        temporary = tempfile.NamedTemporaryFile(dir=temp_root, suffix=".zip", delete=False)
        temporary.close()
        path = Path(temporary.name)
        self.addCleanup(path.unlink, missing_ok=True)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(FIXTURE, arcname="K3241.K03200Y0.D60810.ESTABELE")
        return path

    def test_job_persists_only_matching_companies_with_provenance(self):
        job = Job.objects.create(
            type=Job.Type.DISCOVER_CNPJ,
            payload={
                "query_run_id": str(self.query_run.id),
                "dataset_reference": "2026-08",
                "source_path": str(self.make_zip()),
                "mode": "FULL",
                "filters": {
                    "registration_statuses": ["02"],
                    "states": ["MG"],
                    "cnae_prefixes": ["10"],
                },
            },
        )

        execute_job(job)

        self.query_run.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual(self.query_run.status, QueryRun.Status.SUCCEEDED)
        self.assertEqual(self.query_run.records_processed, 4)
        self.assertEqual(self.query_run.records_matched, 1)
        self.assertEqual(job.records_success, 1)
        self.assertEqual(Company.objects.count(), 1)
        self.assertEqual(SourceRecord.objects.count(), 1)
        self.assertEqual(self.query_run.results.count(), 1)

    def test_preview_stops_at_limit_and_is_marked_partial(self):
        job = Job.objects.create(
            type=Job.Type.DISCOVER_CNPJ,
            payload={
                "query_run_id": str(self.query_run.id),
                "dataset_reference": "2026-08",
                "source_path": str(self.make_zip()),
                "mode": "PREVIEW",
                "max_results": 1,
                "filters": {"registration_statuses": ["02"], "states": ["MG"]},
            },
        )

        execute_job(job)

        self.query_run.refresh_from_db()
        self.assertEqual(self.query_run.status, QueryRun.Status.PARTIAL)
        self.assertEqual(self.query_run.records_matched, 1)
        self.assertTrue(self.query_run.coverage["limit_reached"])
