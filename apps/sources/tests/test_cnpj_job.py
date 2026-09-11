import tempfile
import zipfile
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.companies.models import Company
from apps.discovery.models import DiscoveryQuery, QueryRun, SourceCoverage
from apps.jobs.models import Job
from apps.jobs.services import execute_job
from apps.sources.models import (
    CnpjCandidate,
    CnpjDataset,
    CnpjDatasetFile,
    Source,
    SourceRecord,
)


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

    def make_content_zip(self, content: str, member_name: str) -> Path:
        temp_root = Path(tempfile.gettempdir()) / "synapse-sniper"
        temp_root.mkdir(exist_ok=True)
        temporary = tempfile.NamedTemporaryFile(dir=temp_root, suffix=".zip", delete=False)
        temporary.close()
        path = Path(temporary.name)
        self.addCleanup(path.unlink, missing_ok=True)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(member_name, content.encode("latin1"))
        return path

    def test_job_persists_only_matching_companies_with_provenance(self):
        job = Job.objects.create(
            type=Job.Type.DISCOVER_CNPJ,
            payload={
                "query_run_id": str(self.query_run.id),
                "dataset_reference": "2026-08",
                "source_path": str(self.make_zip()),
                "mode": "FULL",
                "coverage_complete": True,
                "expected_establishment_parts": 1,
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
        candidate = CnpjCandidate.objects.get(query_run=self.query_run)
        self.assertEqual(candidate.company.cnpj, "11111111000191")
        self.assertEqual(candidate.cnpj_basico, "11111111")
        coverage = SourceCoverage.objects.get(query_run=self.query_run)
        self.assertEqual(coverage.record_count, 1)
        self.assertEqual(coverage.scope["filters"], self.query_run.query.normalized_filters)

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

    def test_job_enriches_only_staged_candidates_from_company_and_simples_files(self):
        companies = self.make_content_zip(
            '99999999;IGNORADA;0000;00;0,00;00;\n'
            '11111111;ALIMENTOS MINAS SA;2062;49;150000,50;05;\n',
            "K3241.K03200Y0.D60810.EMPRECSV",
        )
        simples = self.make_content_zip(
            '11111111;S;20200101;;N;;\n'
            '99999999;N;;20210101;N;;\n',
            "F.K03200$W.SIMPLES.CSV.D60810",
        )
        job = Job.objects.create(
            type=Job.Type.DISCOVER_CNPJ,
            payload={
                "query_run_id": str(self.query_run.id),
                "dataset_reference": "2026-08",
                "source_path": str(self.make_zip()),
                "company_source_paths": [str(companies)],
                "simples_source_paths": [str(simples)],
                "mode": "FULL",
                "filters": {
                    "registration_statuses": ["02"],
                    "states": ["MG"],
                    "cnae_prefixes": ["10"],
                },
            },
        )

        execute_job(job)

        company = Company.objects.get()
        candidate = CnpjCandidate.objects.get(query_run=self.query_run)
        self.query_run.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual(company.legal_name, "ALIMENTOS MINAS SA")
        self.assertEqual(company.legal_nature_code, "2062")
        self.assertEqual(company.size_code, "05")
        self.assertEqual(company.share_capital, Decimal("150000.50"))
        self.assertTrue(candidate.company_matched)
        self.assertTrue(candidate.simples_matched)
        self.assertEqual(candidate.simples_payload["simples_option"], "S")
        self.assertEqual(SourceRecord.objects.count(), 3)
        self.assertEqual(self.query_run.coverage["companies"]["basics_matched"], 1)
        self.assertEqual(self.query_run.coverage["simples"]["basics_matched"], 1)
        self.assertEqual(job.records_processed, 7)

    def test_requested_missing_complement_marks_run_partial(self):
        companies = self.make_content_zip(
            '99999999;IGNORADA;0000;00;0,00;00;\n',
            "K3241.K03200Y0.D60810.EMPRECSV",
        )
        job = Job.objects.create(
            type=Job.Type.DISCOVER_CNPJ,
            payload={
                "query_run_id": str(self.query_run.id),
                "dataset_reference": "2026-08",
                "source_path": str(self.make_zip()),
                "company_source_paths": [str(companies)],
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
        self.assertEqual(self.query_run.status, QueryRun.Status.PARTIAL)
        self.assertEqual(self.query_run.coverage["companies"]["basics_missing"], 1)
        self.assertEqual(self.query_run.coverage["companies"]["sources_processed"], 1)

    def test_preview_rejects_complement_files(self):
        companies = self.make_content_zip(
            '11111111;ALIMENTOS MINAS SA;2062;49;150000,50;05;\n',
            "K3241.K03200Y0.D60810.EMPRECSV",
        )
        job = Job.objects.create(
            type=Job.Type.DISCOVER_CNPJ,
            payload={
                "query_run_id": str(self.query_run.id),
                "dataset_reference": "2026-08",
                "source_path": str(self.make_zip()),
                "company_source_paths": [str(companies)],
                "mode": "PREVIEW",
                "filters": {"states": ["MG"]},
            },
        )

        with self.assertRaisesMessage(ValueError, "only in FULL"):
            execute_job(job)

    def test_remote_file_must_belong_to_selected_manifest(self):
        source = Source.objects.get(key="receita-cnpj")
        dataset = CnpjDataset.objects.create(
            source=source,
            reference="2026-08",
            status=CnpjDataset.Status.READY,
            discovered_at=timezone.now(),
        )
        CnpjDatasetFile.objects.create(
            dataset=dataset,
            kind=CnpjDatasetFile.Kind.ESTABLISHMENTS,
            part_number=0,
            url="https://receita.example/CNPJ/2026-08/Estabelecimentos0.zip",
            size_bytes=100,
        )
        job = Job.objects.create(
            type=Job.Type.DISCOVER_CNPJ,
            payload={
                "query_run_id": str(self.query_run.id),
                "dataset_reference": "2026-08",
                "source_url": "https://receita.example/CNPJ/2026-08/Outro.zip",
                "mode": "PREVIEW",
                "filters": {"states": ["MG"]},
            },
        )

        with self.assertRaisesMessage(ValueError, "not part"):
            execute_job(job)

    def test_full_job_processes_all_establishment_parts_sequentially(self):
        source_paths = [str(self.make_zip()) for _ in range(3)]
        job = Job.objects.create(
            type=Job.Type.DISCOVER_CNPJ,
            payload={
                "query_run_id": str(self.query_run.id),
                "dataset_reference": "fixture-2026-08",
                "source_paths": source_paths,
                "mode": "FULL",
                "filters": {
                    "registration_statuses": ["02"],
                    "states": ["MG"],
                    "cnae_prefixes": ["10"],
                },
                "coverage_complete": True,
                "expected_establishment_parts": 3,
            },
        )

        execute_job(job)

        self.query_run.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual(self.query_run.status, QueryRun.Status.SUCCEEDED)
        self.assertEqual(self.query_run.records_processed, 12)
        self.assertEqual(self.query_run.records_matched, 3)
        self.assertEqual(
            self.query_run.coverage["establishments"]["sources_processed"],
            3,
        )
        self.assertEqual(Company.objects.count(), 1)
        self.assertEqual(self.query_run.results.count(), 1)
        self.assertTrue(SourceCoverage.objects.filter(query_run=self.query_run).exists())

    def test_complete_coverage_rejects_missing_establishment_part(self):
        job = Job.objects.create(
            type=Job.Type.DISCOVER_CNPJ,
            payload={
                "query_run_id": str(self.query_run.id),
                "dataset_reference": "fixture-2026-08",
                "source_paths": [str(self.make_zip())],
                "mode": "FULL",
                "filters": {"states": ["MG"]},
                "coverage_complete": True,
                "expected_establishment_parts": 2,
            },
        )

        with self.assertRaisesMessage(ValueError, "every expected"):
            execute_job(job)

        self.assertFalse(SourceCoverage.objects.exists())

    @override_settings(CNPJ_FULL_ENABLED=False)
    def test_remote_full_job_stops_when_kill_switch_is_disabled(self):
        job = Job.objects.create(
            type=Job.Type.DISCOVER_CNPJ,
            payload={
                "query_run_id": str(self.query_run.id),
                "dataset_reference": "2026-08",
                "source_url": "https://receita.example/CNPJ/2026-08/Estabelecimentos0.zip",
                "mode": "FULL",
                "filters": {"states": ["MG"]},
            },
        )

        with self.assertRaisesMessage(ValueError, "kill switch"):
            execute_job(job)

    @override_settings(CNPJ_FULL_ENABLED=True)
    def test_complete_remote_job_requires_each_manifest_file_exactly_once(self):
        source = Source.objects.get(key="receita-cnpj")
        dataset = CnpjDataset.objects.create(
            source=source,
            reference="2026-08",
            status=CnpjDataset.Status.READY,
            discovered_at=timezone.now(),
        )
        establishment_urls = []
        company_urls = []
        for part_number in range(10):
            establishment_urls.append(
                f"https://receita.example/CNPJ/2026-08/Estabelecimentos{part_number}.zip"
            )
            company_urls.append(
                f"https://receita.example/CNPJ/2026-08/Empresas{part_number}.zip"
            )
            CnpjDatasetFile.objects.create(
                dataset=dataset,
                kind=CnpjDatasetFile.Kind.ESTABLISHMENTS,
                part_number=part_number,
                url=establishment_urls[-1],
                size_bytes=100,
            )
            CnpjDatasetFile.objects.create(
                dataset=dataset,
                kind=CnpjDatasetFile.Kind.COMPANIES,
                part_number=part_number,
                url=company_urls[-1],
                size_bytes=100,
            )
        simples_url = "https://receita.example/CNPJ/2026-08/Simples.zip"
        CnpjDatasetFile.objects.create(
            dataset=dataset,
            kind=CnpjDatasetFile.Kind.SIMPLES,
            part_number=0,
            url=simples_url,
            size_bytes=100,
        )
        job = Job.objects.create(
            type=Job.Type.DISCOVER_CNPJ,
            payload={
                "query_run_id": str(self.query_run.id),
                "dataset_reference": "2026-08",
                "source_urls": [establishment_urls[0]] * 10,
                "company_source_urls": company_urls,
                "simples_source_urls": [simples_url],
                "mode": "FULL",
                "filters": {"states": ["MG"]},
                "coverage_complete": True,
                "expected_establishment_parts": 10,
            },
        )

        with self.assertRaisesMessage(ValueError, "every manifest"):
            execute_job(job)
