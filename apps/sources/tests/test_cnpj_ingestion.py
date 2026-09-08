from datetime import UTC, datetime

from django.test import TestCase

from apps.companies.models import Company, CompanyCnae
from apps.sources.cnpj.establishments import CnpjEstablishment
from apps.sources.cnpj.ingestion import ingest_establishment
from apps.sources.models import FieldObservation, Source, SourceRecord


class CnpjIngestionTests(TestCase):
    def setUp(self):
        self.source = Source.objects.create(key="test-receita", name="Receita teste")
        self.observed_at = datetime(2026, 8, 31, tzinfo=UTC)
        self.establishment = CnpjEstablishment(
            cnpj_basico="11111111",
            cnpj_ordem="0001",
            cnpj_dv="91",
            branch_identifier="1",
            trade_name="ALIMENTOS MINAS",
            registration_status="02",
            registration_status_date="20260831",
            activity_started_on="20200101",
            primary_cnae="1091102",
            secondary_cnaes=("1099601", "4721102"),
            street_type="RUA",
            street="DAS INDUSTRIAS",
            number="100",
            complement="",
            district="DISTRITO INDUSTRIAL",
            postal_code="30100000",
            state="MG",
            municipality_code="4123",
            phone="3133334444",
            secondary_phone="",
            email="contato@example.com",
        )

    def test_ingests_company_provenance_and_cnaes(self):
        outcome = ingest_establishment(
            self.establishment,
            source=self.source,
            observed_at=self.observed_at,
            dataset_reference="2026-08",
        )

        self.assertTrue(outcome.company_created)
        self.assertEqual(outcome.company.cnpj, "11111111000191")
        self.assertEqual(outcome.company.registration_status, Company.RegistrationStatus.ACTIVE)
        self.assertEqual(SourceRecord.objects.count(), 1)
        self.assertGreater(FieldObservation.objects.count(), 5)
        self.assertEqual(CompanyCnae.objects.filter(company=outcome.company).count(), 3)
        self.assertEqual(outcome.company.cnaes.get(is_primary=True).code, "1091102")

    def test_repeated_payload_is_idempotent(self):
        first = ingest_establishment(
            self.establishment,
            source=self.source,
            observed_at=self.observed_at,
            dataset_reference="2026-08",
        )
        second = ingest_establishment(
            self.establishment,
            source=self.source,
            observed_at=self.observed_at,
            dataset_reference="2026-08",
        )

        self.assertTrue(first.company_created)
        self.assertFalse(second.company_created)
        self.assertFalse(second.source_record_created)
        self.assertEqual(Company.objects.count(), 1)
        self.assertEqual(SourceRecord.objects.count(), 1)
