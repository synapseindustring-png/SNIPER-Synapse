from django.test import TestCase
from django.utils import timezone

from apps.companies.models import Company
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
