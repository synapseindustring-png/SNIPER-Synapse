import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import TestCase

from apps.companies.models import Company
from apps.crawler.models import JobPosting, JobPostingReview
from apps.crawler.services import persist_job_postings, persist_page
from apps.jobs.models import Job
from apps.jobs.services import execute_job
from apps.sources.jobs.base import JobCollectionLimits, JobsAdapterError
from apps.sources.jobs.fixture import FixtureJobsAdapter
from apps.sources.jobs.services import collect_company_jobs
from apps.sources.models import Source, SourceRecord


class JobsAdapterTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            cnpj="11222333000144",
            legal_name="Indústria Alfa S.A.",
            trade_name="Indústria Alfa",
            company_type=Company.Type.INDUSTRY,
            registration_status=Company.RegistrationStatus.ACTIVE,
            website="https://industriaalfa.example/",
            website_domain="industriaalfa.example",
        )
        self.source = Source.objects.get(key="jobs-fixture")
        self.source.enabled = True
        self.source.save(update_fields=("enabled",))
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.fixture_root = Path(self.temporary_directory.name)

    def write_fixture(self, payload, name="jobs.json"):
        (self.fixture_root / name).write_text(json.dumps(payload), encoding="utf-8")
        return name

    def adapter(self, payload):
        return FixtureJobsAdapter(self.fixture_root, self.write_fixture(payload))

    def limits(self, **overrides):
        values = {"max_pages": 2, "max_results": 100, "max_bytes": 100_000}
        values.update(overrides)
        return JobCollectionLimits(**values)

    def fixture_items(self):
        return {
            "items": [
                {
                    "external_id": "job-1",
                    "title": "Vaga de PCM",
                    "company_name": "Indústria Alfa",
                    "company_domain": "industriaalfa.example",
                    "description": "Planejador de manutenção",
                    "location": "Campinas/SP",
                    "url": "https://jobs.example/vagas/1",
                    "published_on": "2026-09-01",
                },
                {
                    "external_id": "job-2",
                    "title": "Analista industrial",
                    "company_name": "Outra Empresa",
                    "company_domain": "outra.example",
                    "url": "https://jobs.example/vagas/2",
                },
            ]
        }

    def test_preview_reports_matches_without_persisting_any_candidate(self):
        with self.settings(JOBS_ADAPTER_ENABLED=True):
            outcome = collect_company_jobs(
                self.company,
                source=self.source,
                adapter=self.adapter(self.fixture_items()),
                mode="PREVIEW",
                limits=self.limits(),
            )

        self.assertEqual(outcome.items_scanned, 2)
        self.assertEqual(outcome.items_matched, 1)
        self.assertEqual(outcome.jobs_persisted, 0)
        self.assertEqual(SourceRecord.objects.count(), 0)
        self.assertEqual(JobPosting.objects.count(), 0)
        self.assertEqual(JobPostingReview.objects.count(), 0)

    def test_full_persists_strong_match_and_sends_divergence_to_review(self):
        with self.settings(JOBS_ADAPTER_ENABLED=True):
            outcome = collect_company_jobs(
                self.company,
                source=self.source,
                adapter=self.adapter(self.fixture_items()),
                mode="FULL",
                limits=self.limits(),
            )

        self.assertEqual(outcome.jobs_persisted, 1)
        self.assertEqual(outcome.reviews_created, 1)
        posting = JobPosting.objects.get()
        self.assertEqual(posting.company, self.company)
        self.assertEqual(posting.title, "Vaga de PCM")
        review = JobPostingReview.objects.get()
        self.assertEqual(review.status, JobPostingReview.Status.PENDING)
        self.assertEqual(review.suggested_company, self.company)
        self.assertIn("diverge", review.reason)

    def test_fixture_is_bounded_by_pages_results_and_bytes(self):
        payload = {
            "pages": [
                {"items": [{"title": "Primeira", "company_name": "Indústria Alfa"}]},
                {"items": [{"title": "Segunda", "company_name": "Indústria Alfa"}]},
            ]
        }
        batch = self.adapter(payload).collect(
            query=None,
            limits=self.limits(max_pages=1, max_results=1),
        )
        self.assertEqual((batch.pages_read, len(batch.items)), (1, 1))
        self.assertTrue(batch.truncated)

        adapter = self.adapter(payload)
        with self.assertRaises(JobsAdapterError):
            adapter.collect(query=None, limits=self.limits(max_bytes=1))

    def test_fixture_rejects_path_traversal(self):
        with self.assertRaises(JobsAdapterError):
            FixtureJobsAdapter(self.fixture_root, "../jobs.json")

    def test_kill_switch_blocks_collection(self):
        with self.assertRaises(JobsAdapterError):
            collect_company_jobs(
                self.company,
                source=self.source,
                adapter=self.adapter(self.fixture_items()),
                mode="PREVIEW",
                limits=self.limits(),
            )

    def test_find_jobs_handler_runs_pipeline_with_configured_caps(self):
        fixture_name = self.write_fixture(self.fixture_items())
        job = Job.objects.create(
            type=Job.Type.FIND_JOBS,
            payload={
                "company_id": str(self.company.pk),
                "source_key": self.source.key,
                "fixture_name": fixture_name,
                "mode": "FULL",
                "max_pages": 999,
                "max_results": 999,
            },
        )

        with self.settings(
            JOBS_ADAPTER_ENABLED=True,
            JOBS_FIXTURE_ROOT=self.fixture_root,
            JOBS_MAX_PAGES=1,
            JOBS_MAX_RESULTS=1,
            JOBS_MAX_RESPONSE_BYTES=100_000,
        ):
            execute_job(job)

        job.refresh_from_db()
        self.assertEqual((job.records_processed, job.records_success), (1, 1))
        self.assertEqual(JobPosting.objects.count(), 1)
        self.assertTrue(self.company.signals.filter(signal_type="contratacao").exists())
        self.assertTrue(Job.objects.filter(type=Job.Type.CALCULATE_SCORE).exists())

    def test_complete_full_refresh_deactivates_missing_jobs_but_truncated_does_not(self):
        with self.settings(JOBS_ADAPTER_ENABLED=True):
            collect_company_jobs(
                self.company,
                source=self.source,
                adapter=self.adapter({"items": [self.fixture_items()["items"][0]]}),
                mode="FULL",
                limits=self.limits(),
            )
            posting = JobPosting.objects.get()
            collect_company_jobs(
                self.company,
                source=self.source,
                adapter=self.adapter({"pages": [{"items": []}, {"items": []}]}),
                mode="FULL",
                limits=self.limits(max_pages=1),
            )
            posting.refresh_from_db()
            self.assertTrue(posting.active)

            collect_company_jobs(
                self.company,
                source=self.source,
                adapter=self.adapter({"items": []}),
                mode="FULL",
                limits=self.limits(),
            )

        posting.refresh_from_db()
        self.assertFalse(posting.active)

    def test_same_job_from_website_and_adapter_is_deduplicated(self):
        page = persist_page(
            self.company,
            url="https://industriaalfa.example/carreiras",
            status=200,
            content_type="text/html",
            title="Carreiras",
            text="Vagas abertas",
        ).page
        persist_job_postings(
            self.company,
            source_record=page.source_record,
            structured_data=[
                {
                    "@type": "JobPosting",
                    "title": "Vaga de PCM",
                    "jobLocation": {"address": {"addressLocality": "Campinas/SP"}},
                    "url": "https://industriaalfa.example/vagas/pcm",
                    "datePosted": "2026-09-01",
                }
            ],
        )

        with self.settings(JOBS_ADAPTER_ENABLED=True):
            collect_company_jobs(
                self.company,
                source=self.source,
                adapter=self.adapter({"items": [self.fixture_items()["items"][0]]}),
                mode="FULL",
                limits=self.limits(),
            )

        self.assertEqual(JobPosting.objects.count(), 1)
        posting = JobPosting.objects.get()
        self.assertEqual(posting.source_record.source, self.source)
        self.assertEqual(posting.url, "https://jobs.example/vagas/1")
