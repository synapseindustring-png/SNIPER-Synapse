from django.test import TestCase, override_settings
from django.utils import timezone

from apps.sources.cnpj.manifest import (
    CnpjManifestError,
    WebDavEntry,
    sync_latest_manifest,
)
from apps.sources.models import CnpjDataset, CnpjDatasetFile, Source


class FakeManifestClient:
    def __init__(self, *, complete=True):
        self.complete = complete

    def list(self, path=""):
        if not path:
            return [
                WebDavEntry("2026-07", "/2026-07/", True, None, "old", None),
                WebDavEntry("2026-08", "/2026-08/", True, None, "new", None),
                WebDavEntry("cnpj.tar.gz", "/cnpj.tar.gz", False, 999, "ignored", None),
            ]
        files = []
        for part in range(10):
            if self.complete or part != 9:
                files.append(
                    WebDavEntry(
                        f"Estabelecimentos{part}.zip",
                        f"/{path}/Estabelecimentos{part}.zip",
                        False,
                        1000 + part,
                        f"est-{part}",
                        None,
                    )
                )
            files.append(
                WebDavEntry(
                    f"Empresas{part}.zip",
                    f"/{path}/Empresas{part}.zip",
                    False,
                    500 + part,
                    f"emp-{part}",
                    None,
                )
            )
        files.append(WebDavEntry("Simples.zip", f"/{path}/Simples.zip", False, 800, "simples", None))
        return files

    def file_url(self, competence, filename):
        return f"https://receita.example/public.php/webdav/{competence}/{filename}"


class CnpjManifestSyncTests(TestCase):
    @override_settings(
        CNPJ_SOURCE_BASE_URL="https://receita.example/public.php/webdav/",
        CNPJ_WEBDAV_TOKEN="public-token",
    )
    def test_persists_only_complete_latest_competence_atomically(self):
        dataset = sync_latest_manifest(FakeManifestClient())

        self.assertEqual(dataset.reference, "2026-08")
        self.assertEqual(dataset.status, CnpjDataset.Status.READY)
        self.assertTrue(dataset.is_current)
        self.assertEqual(dataset.files.count(), 21)
        self.assertEqual(
            dataset.files.filter(kind=CnpjDatasetFile.Kind.ESTABLISHMENTS).count(),
            10,
        )
        self.assertEqual(dataset.files.get(kind="ESTABLISHMENTS", part_number=0).size_bytes, 1000)

    def test_incomplete_latest_competence_preserves_current_manifest(self):
        source = Source.objects.get(key="receita-cnpj")
        current = CnpjDataset.objects.create(
            source=source,
            reference="2026-07",
            status=CnpjDataset.Status.READY,
            is_current=True,
            discovered_at=timezone.now(),
        )

        with self.assertRaisesMessage(CnpjManifestError, "incomplete"):
            sync_latest_manifest(FakeManifestClient(complete=False))

        current.refresh_from_db()
        self.assertTrue(current.is_current)
        self.assertFalse(CnpjDataset.objects.filter(reference="2026-08").exists())
