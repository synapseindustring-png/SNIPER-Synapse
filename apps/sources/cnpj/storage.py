import fcntl
import base64
import os
import re
import shutil
import urllib.request
import zipfile
from dataclasses import dataclass
from time import time
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from django.conf import settings


class CnpjDownloadError(RuntimeError):
    pass


class CnpjDownloadBusy(CnpjDownloadError):
    pass


class CnpjQuotaExceeded(CnpjDownloadError):
    pass


@dataclass(frozen=True, slots=True)
class CnpjCapacity:
    expected_bytes: int
    free_bytes: int
    remaining_bytes: int
    max_temp_bytes: int
    min_free_bytes: int
    allowed: bool
    reason: str


def assess_download_capacity(expected_bytes: int) -> CnpjCapacity:
    Path(settings.TEMP_DATA_DIR).mkdir(mode=0o700, parents=True, exist_ok=True)
    free_bytes = shutil.disk_usage(settings.TEMP_DATA_DIR).free
    remaining_bytes = free_bytes - expected_bytes
    if expected_bytes > settings.CNPJ_MAX_TEMP_BYTES:
        reason = "O arquivo excede a quota temporária configurada."
    elif remaining_bytes < settings.CNPJ_MIN_FREE_BYTES:
        reason = "O download reduziria o espaço livre abaixo da reserva mínima."
    else:
        reason = "Capacidade disponível."
    return CnpjCapacity(
        expected_bytes=expected_bytes,
        free_bytes=free_bytes,
        remaining_bytes=remaining_bytes,
        max_temp_bytes=settings.CNPJ_MAX_TEMP_BYTES,
        min_free_bytes=settings.CNPJ_MIN_FREE_BYTES,
        allowed=reason == "Capacidade disponível.",
        reason=reason,
    )


def validate_source_url(value: str) -> str:
    return _validated_url(value)


def cleanup_stale_downloads(max_age_seconds: int | None = None) -> int:
    """Remove only old, flat CNPJ job artifacts while no download owns the lock."""
    root = Path(settings.TEMP_DATA_DIR)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_path = root / ".download.lock"
    removed = 0
    cutoff = time() - (max_age_seconds or settings.CNPJ_TEMP_MAX_AGE_SECONDS)
    with lock_path.open("a+b") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise CnpjDownloadBusy("A CNPJ download is active; cleanup was skipped") from exc
        try:
            for job_directory in root.iterdir():
                if not job_directory.is_dir() or job_directory.is_symlink():
                    continue
                entries = list(job_directory.iterdir())
                if not entries or any(
                    not entry.is_file()
                    or entry.is_symlink()
                    or not entry.name.lower().endswith((".zip", ".zip.part"))
                    for entry in entries
                ):
                    continue
                if max(entry.stat().st_mtime for entry in entries) >= cutoff:
                    continue
                for entry in entries:
                    entry.unlink()
                    removed += 1
                job_directory.rmdir()
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)
    return removed


def _validated_url(value: str) -> str:
    base_value = settings.CNPJ_SOURCE_BASE_URL
    if not base_value:
        raise CnpjDownloadError("CNPJ_SOURCE_BASE_URL is not configured")
    base = urlparse(base_value)
    candidate = urlparse(value)
    if base.scheme != "https" or candidate.scheme != "https":
        raise CnpjDownloadError("CNPJ downloads require HTTPS")
    if candidate.username or candidate.password:
        raise CnpjDownloadError("Credentials are not allowed in CNPJ source URLs")
    if candidate.netloc != base.netloc:
        raise CnpjDownloadError("CNPJ source URL is outside the configured host")
    base_path = base.path.rstrip("/") + "/"
    if not candidate.path.startswith(base_path):
        raise CnpjDownloadError("CNPJ source URL is outside the configured path")
    return value


def _job_directory(job_id: str) -> Path:
    safe_job_id = str(job_id)
    if not re.fullmatch(r"[A-Za-z0-9-]+", safe_job_id):
        raise CnpjDownloadError("Invalid job identifier")
    root = Path(settings.TEMP_DATA_DIR)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    job_directory = root / safe_job_id
    job_directory.mkdir(mode=0o700, exist_ok=False)
    return job_directory


def _content_length(headers) -> int:
    value = headers.get("Content-Length")
    if not value:
        raise CnpjDownloadError("Source did not provide Content-Length")
    try:
        length = int(value)
    except (TypeError, ValueError) as exc:
        raise CnpjDownloadError("Source provided an invalid Content-Length") from exc
    if length <= 0:
        raise CnpjDownloadError("Source provided an empty Content-Length")
    return length


def _check_quota(expected_bytes: int) -> None:
    capacity = assess_download_capacity(expected_bytes)
    if not capacity.allowed:
        raise CnpjQuotaExceeded(capacity.reason)


def _download(url: str, job_id: str) -> tuple[Path, Path]:
    validated_url = _validated_url(url)
    filename = PurePosixPath(urlparse(validated_url).path).name
    if not filename.lower().endswith(".zip"):
        raise CnpjDownloadError("CNPJ source URL must identify a ZIP file")
    job_directory = _job_directory(job_id)
    part_path = job_directory / f"{filename}.part"
    ready_path = job_directory / filename
    request = urllib.request.Request(
        validated_url,
        headers={"User-Agent": "SynapseSniper/0.1"},
    )
    if settings.CNPJ_WEBDAV_TOKEN:
        credentials = base64.b64encode(
            f"{settings.CNPJ_WEBDAV_TOKEN}:".encode()
        ).decode()
        request.add_header("Authorization", f"Basic {credentials}")
    try:
        with urllib.request.urlopen(
            request,
            timeout=settings.CNPJ_DOWNLOAD_TIMEOUT_SECONDS,
        ) as response:
            _validated_url(response.geturl())
            expected_bytes = _content_length(response.headers)
            _check_quota(expected_bytes)
            written = 0
            with part_path.open("xb") as destination:
                while chunk := response.read(1024 * 1024):
                    written += len(chunk)
                    if written > expected_bytes or written > settings.CNPJ_MAX_TEMP_BYTES:
                        raise CnpjQuotaExceeded("Download exceeded its declared or configured size")
                    destination.write(chunk)
                destination.flush()
                os.fsync(destination.fileno())
            if written != expected_bytes:
                raise CnpjDownloadError(
                    f"Incomplete download: expected {expected_bytes} bytes, received {written}"
                )
        with zipfile.ZipFile(part_path) as archive:
            corrupt_member = archive.testzip()
            if corrupt_member:
                raise CnpjDownloadError(f"Corrupt ZIP member: {corrupt_member}")
        part_path.replace(ready_path)
        return ready_path, job_directory
    except Exception:
        part_path.unlink(missing_ok=True)
        ready_path.unlink(missing_ok=True)
        job_directory.rmdir()
        raise


@contextmanager
def downloaded_cnpj_zip(url: str, job_id: str):
    root = Path(settings.TEMP_DATA_DIR)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_path = root / ".download.lock"
    with lock_path.open("a+b") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise CnpjDownloadBusy("Another CNPJ download is already running") from exc
        ready_path = None
        job_directory = None
        try:
            ready_path, job_directory = _download(url, job_id)
            yield ready_path
        finally:
            if ready_path:
                ready_path.unlink(missing_ok=True)
            if job_directory and job_directory.exists():
                job_directory.rmdir()
            fcntl.flock(lock_file, fcntl.LOCK_UN)
