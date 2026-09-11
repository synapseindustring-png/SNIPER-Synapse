from collections import namedtuple
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.sources.cnpj.health import manifest_health
from apps.sources.models import CnpjDataset, CnpjDatasetFile, Source


DiskUsage = namedtuple("DiskUsage", "total used free")


class CnpjManifestHealthTests(TestCase):
    def setUp(self):
        self.source = Source.objects.get(key="receita-cnpj")

    def create_dataset(self, *, discovered_at=None, complete=True):
        dataset = CnpjDataset.objects.create(
            source=self.source,
            reference="2026-08",
            status=CnpjDataset.Status.READY,
            is_current=True,
            discovered_at=discovered_at or timezone.now(),
            verified_at=discovered_at or timezone.now(),
        )
        for part_number in range(10):
            if complete or part_number < 9:
                CnpjDatasetFile.objects.create(
                    dataset=dataset,
                    kind=CnpjDatasetFile.Kind.ESTABLISHMENTS,
                    part_number=part_number,
                    url=f"https://receita.example/CNPJ/Estabelecimentos{part_number}.zip",
                    size_bytes=1000 + part_number,
                )
            CnpjDatasetFile.objects.create(
                dataset=dataset,
                kind=CnpjDatasetFile.Kind.COMPANIES,
                part_number=part_number,
                url=f"https://receita.example/CNPJ/Empresas{part_number}.zip",
                size_bytes=500 + part_number,
            )
        CnpjDatasetFile.objects.create(
            dataset=dataset,
            kind=CnpjDatasetFile.Kind.SIMPLES,
            part_number=0,
            url="https://receita.example/CNPJ/Simples.zip",
            size_bytes=800,
        )
        return dataset

    @patch("apps.jobs.operations.shutil.disk_usage")
    def test_complete_recent_manifest_with_capacity_is_healthy(self, disk_usage):
        disk_usage.return_value = DiskUsage(20_000, 5_000, 15_000)
        self.create_dataset()

        with override_settings(CNPJ_MAX_TEMP_BYTES=10_000, CNPJ_MIN_FREE_BYTES=5_000):
            health = manifest_health()

        self.assertEqual(health.state, "healthy")
        self.assertEqual(health.total_files, 21)
        self.assertEqual(health.establishment_parts, 10)
        self.assertEqual(health.company_parts, 10)
        self.assertEqual(health.simples_parts, 1)
        self.assertTrue(health.fits_storage)

    @patch("apps.jobs.operations.shutil.disk_usage")
    def test_incomplete_manifest_is_degraded(self, disk_usage):
        disk_usage.return_value = DiskUsage(20_000, 5_000, 15_000)
        self.create_dataset(complete=False)

        health = manifest_health()

        self.assertEqual(health.state, "degraded")
        self.assertEqual(health.label, "Incompleta")

    @patch("apps.jobs.operations.shutil.disk_usage")
    def test_old_manifest_is_reported_as_stale(self, disk_usage):
        disk_usage.return_value = DiskUsage(20_000, 5_000, 15_000)
        self.create_dataset(discovered_at=timezone.now() - timedelta(days=3))

        with override_settings(CNPJ_MANIFEST_MAX_AGE_DAYS=2):
            health = manifest_health()

        self.assertEqual(health.label, "Desatualizada")
        self.assertTrue(health.is_stale)

    def test_missing_manifest_is_unavailable_without_disk_probe(self):
        health = manifest_health()

        self.assertEqual(health.state, "unavailable")
        self.assertIsNone(health.dataset)
