import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from django.conf import settings


SENSITIVE_FRAGMENTS = ("token", "password", "secret", "authorization", "credential", "key")


@dataclass(frozen=True, slots=True)
class StorageStatus:
    path: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    cnpj_max_temp_bytes: int
    cnpj_min_free_bytes: int
    jobs_max_response_bytes: int
    safe_cnpj_capacity_bytes: int


def storage_status() -> StorageStatus:
    configured_path = Path(settings.TEMP_DATA_DIR)
    probe = configured_path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    usage = shutil.disk_usage(probe)
    safe_capacity = max(
        0,
        min(
            settings.CNPJ_MAX_TEMP_BYTES,
            usage.free - settings.CNPJ_MIN_FREE_BYTES,
        ),
    )
    return StorageStatus(
        path=str(configured_path),
        total_bytes=usage.total,
        used_bytes=usage.used,
        free_bytes=usage.free,
        cnpj_max_temp_bytes=settings.CNPJ_MAX_TEMP_BYTES,
        cnpj_min_free_bytes=settings.CNPJ_MIN_FREE_BYTES,
        jobs_max_response_bytes=settings.JOBS_MAX_RESPONSE_BYTES,
        safe_cnpj_capacity_bytes=safe_capacity,
    )


def _safe_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "[URL inválida]"
    if parsed.scheme not in {"http", "https"}:
        return value
    hostname = parsed.hostname or ""
    try:
        parsed_port = parsed.port
    except ValueError:
        return "[URL inválida]"
    port = f":{parsed_port}" if parsed_port else ""
    return urlunsplit((parsed.scheme, f"{hostname}{port}", parsed.path, "", ""))


def sanitize_job_data(value, *, depth=0):
    if depth > 5:
        return "[limite de profundidade]"
    if isinstance(value, dict):
        sanitized = {}
        for key, item in list(value.items())[:100]:
            key_text = str(key)
            if any(fragment in key_text.casefold() for fragment in SENSITIVE_FRAGMENTS):
                sanitized[key_text] = "[oculto]"
            else:
                sanitized[key_text] = sanitize_job_data(item, depth=depth + 1)
        return sanitized
    if isinstance(value, list):
        return [sanitize_job_data(item, depth=depth + 1) for item in value[:100]]
    if isinstance(value, str):
        value = _safe_url(value) if "://" in value else value
        value = re.sub(
            r"(?i)(token|password|secret|api[_-]?key)\s*[:=]\s*[^\s,;]+",
            r"\1=[oculto]",
            value,
        )
        return value[:2000]
    return value
