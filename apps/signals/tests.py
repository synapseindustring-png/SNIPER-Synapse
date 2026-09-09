import hashlib
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.companies.models import Company
from apps.crawler.models import JobPosting
from apps.jobs.models import Job
from apps.jobs.services import execute_job
from apps.sources.models import Source, SourceRecord

from .detector import detect_company_signals
from .models import Signal, SignalDetection, SignalRule


class SignalDetectorTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            cnpj="11222333000144",
            legal_name="Indústria Detectora",
            company_type=Company.Type.INDUSTRY,
            registration_status=Company.RegistrationStatus.ACTIVE,
        )
        self.source = Source.objects.get(key="receita-cnpj")
        self.record = SourceRecord.objects.create(
            source=self.source,
            external_id=self.company.cnpj,
            company=self.company,
            payload={
                "title": "Oportunidade industrial",
                "description": "Projeto de PCM com foco em OEE e manutenção preventiva.",
            },
            payload_hash="d" * 64,
            dataset_reference="fixture",
            observed_at=timezone.now(),
        )

    def create_job_posting(self, *, title, published_on, suffix):
        source = Source.objects.get(key="website")
        record = SourceRecord.objects.create(
            source=source,
            external_id="https://example.com/carreiras",
            company=self.company,
            source_url="https://example.com/carreiras",
            payload={"title": "Carreiras"},
            payload_hash=hashlib.sha256(suffix.encode()).hexdigest(),
            observed_at=timezone.now(),
        )
        return JobPosting.objects.create(
            company=self.company,
            source_record=record,
            fingerprint=hashlib.sha256(f"job-{suffix}".encode()).hexdigest(),
            title=title,
            description="Atuação industrial.",
            url=f"https://example.com/vagas/{suffix}",
            published_on=published_on,
            first_seen_at=timezone.now(),
            last_seen_at=timezone.now(),
        )

    def test_detects_multiple_explicit_signals_and_preserves_evidence(self):
        first = detect_company_signals(self.company)
        second = detect_company_signals(self.company)

        self.assertGreaterEqual(first.signals_created, 3)
        self.assertEqual(second.signals_created, 0)
        self.assertEqual(Signal.objects.count(), first.signals_created)
        pcm = Signal.objects.get(signal_type="pcm")
        self.assertIn("PCM", pcm.evidence_excerpt)
        detection = SignalDetection.objects.get(signal=pcm)
        self.assertEqual(detection.source_record, self.record)
        self.assertIn("pcm", [term.casefold() for term in detection.matched_terms])

    def test_matching_uses_word_boundaries(self):
        SignalRule.objects.all().delete()
        SignalRule.objects.create(
            key="sap",
            name="SAP",
            signal_type="erp",
            keywords=["sap"],
            source_fields=["description"],
        )
        self.record.payload["description"] = "Projeto para tratamento de sapos industriais."
        self.record.save(update_fields=("payload",))

        stats = detect_company_signals(self.company)

        self.assertEqual(stats.signals_matched, 0)

    def test_stale_generated_signal_is_deactivated(self):
        detect_company_signals(self.company)
        SignalRule.objects.update(active=False)

        stats = detect_company_signals(self.company)

        self.assertGreater(stats.signals_deactivated, 0)
        self.assertFalse(Signal.objects.filter(active=True).exists())

    def test_detection_job_enqueues_score_recalculation(self):
        job = Job.objects.create(
            type=Job.Type.DETECT_SIGNALS,
            payload={"company_id": str(self.company.pk)},
        )

        execute_job(job)

        job.refresh_from_db()
        self.assertEqual(job.records_processed, 1)
        self.assertGreater(job.records_success, 0)
        self.assertTrue(
            Job.objects.filter(type=Job.Type.CALCULATE_SCORE).exists()
        )

    def test_each_job_is_individual_evidence_dated_by_publication(self):
        SignalRule.objects.all().delete()
        rule = SignalRule.objects.create(
            key="job-pcm",
            name="Contratação PCM",
            signal_type="contratacao",
            keywords=["pcm"],
            source_fields=["job_title", "job_description"],
            expires_after_days=365,
        )
        today = timezone.localdate()
        first = self.create_job_posting(
            title="Analista de PCM", published_on=today - timedelta(days=20), suffix="pcm-1"
        )
        second = self.create_job_posting(
            title="Coordenador de PCM", published_on=today - timedelta(days=5), suffix="pcm-2"
        )

        stats = detect_company_signals(self.company)

        signals = list(Signal.objects.filter(signal_type="contratacao").order_by("observed_at"))
        self.assertEqual(stats.signals_created, 2)
        self.assertEqual(len(signals), 2)
        self.assertEqual(signals[0].observed_at.date(), first.published_on)
        self.assertEqual(signals[1].observed_at.date(), second.published_on)
        self.assertEqual(signals[0].source_url, first.url)
        self.assertEqual(signals[1].metadata["job_posting_id"], str(second.pk))
        self.assertEqual(
            SignalDetection.objects.filter(rule=rule).values_list("field_name", flat=True).distinct().get(),
            "job_title",
        )

    def test_old_job_and_its_generated_signal_are_deactivated(self):
        SignalRule.objects.all().delete()
        SignalRule.objects.create(
            key="job-pcm",
            name="Contratação PCM",
            signal_type="contratacao",
            keywords=["pcm"],
            source_fields=["job_title"],
            expires_after_days=365,
        )
        posting = self.create_job_posting(
            title="Analista de PCM",
            published_on=timezone.localdate() - timedelta(days=20),
            suffix="old-pcm",
        )
        with self.settings(JOB_POSTING_MAX_AGE_DAYS=365):
            detect_company_signals(self.company)
        self.assertTrue(Signal.objects.get(signal_type="contratacao").active)

        with self.settings(JOB_POSTING_MAX_AGE_DAYS=10):
            stats = detect_company_signals(self.company)

        posting.refresh_from_db()
        self.assertFalse(posting.active)
        self.assertEqual(stats.signals_deactivated, 1)
        self.assertFalse(Signal.objects.get(signal_type="contratacao").active)
