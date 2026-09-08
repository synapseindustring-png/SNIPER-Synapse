import io
import os
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.sources.cnpj.storage import (
    CnpjDownloadError,
    CnpjQuotaExceeded,
    cleanup_stale_downloads,
    downloaded_cnpj_zip,
)


class FakeResponse(io.BytesIO):
    def __init__(self, content: bytes, url: str, declared_size: int | None = None):
        super().__init__(content)
        self._url = url
        self.headers = {"Content-Length": str(declared_size or len(content))}

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def make_zip_bytes() -> bytes:
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ESTABELE", "a;b;c")
    return target.getvalue()


class CnpjStorageTests(SimpleTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.url = "https://receita.example/CNPJ/2026-08/Estabelecimentos0.zip"
        self.settings = override_settings(
            TEMP_DATA_DIR=Path(self.temporary.name),
            CNPJ_SOURCE_BASE_URL="https://receita.example/CNPJ/",
            CNPJ_MAX_TEMP_BYTES=1024 * 1024,
            CNPJ_MIN_FREE_BYTES=0,
            CNPJ_DOWNLOAD_TIMEOUT_SECONDS=1,
        )
        self.settings.enable()
        self.addCleanup(self.settings.disable)

    def test_valid_zip_is_available_only_inside_context(self):
        content = make_zip_bytes()
        response = FakeResponse(content, self.url)
        with patch("urllib.request.urlopen", return_value=response):
            with downloaded_cnpj_zip(self.url, "job-1") as downloaded:
                self.assertTrue(downloaded.exists())
                self.assertEqual(downloaded.read_bytes(), content)
            self.assertFalse(downloaded.exists())
            self.assertFalse((Path(self.temporary.name) / "job-1").exists())

    def test_rejects_declared_size_above_quota_before_writing(self):
        response = FakeResponse(make_zip_bytes(), self.url, declared_size=2 * 1024 * 1024)
        with patch("urllib.request.urlopen", return_value=response):
            with self.assertRaises(CnpjQuotaExceeded):
                with downloaded_cnpj_zip(self.url, "job-2"):
                    pass
        self.assertFalse((Path(self.temporary.name) / "job-2").exists())

    def test_rejects_truncated_download(self):
        content = make_zip_bytes()
        response = FakeResponse(content, self.url, declared_size=len(content) + 10)
        with patch("urllib.request.urlopen", return_value=response):
            with self.assertRaisesMessage(CnpjDownloadError, "Incomplete download"):
                with downloaded_cnpj_zip(self.url, "job-3"):
                    pass

    def test_rejects_redirect_outside_configured_source(self):
        response = FakeResponse(make_zip_bytes(), "https://attacker.example/file.zip")
        with patch("urllib.request.urlopen", return_value=response):
            with self.assertRaisesMessage(CnpjDownloadError, "configured host"):
                with downloaded_cnpj_zip(self.url, "job-4"):
                    pass

    def test_cleanup_removes_only_old_known_artifacts(self):
        root = Path(self.temporary.name)
        stale = root / "old-job"
        stale.mkdir()
        stale_part = stale / "Estabelecimentos0.zip.part"
        stale_part.write_bytes(b"partial")
        os.utime(stale_part, (1, 1))
        unknown = root / "unknown-job"
        unknown.mkdir()
        unknown_file = unknown / "keep.txt"
        unknown_file.write_text("keep")
        os.utime(unknown_file, (1, 1))

        removed = cleanup_stale_downloads(max_age_seconds=1)

        self.assertEqual(removed, 1)
        self.assertFalse(stale.exists())
        self.assertTrue(unknown_file.exists())
