from dataclasses import dataclass

from django.conf import settings

from apps.sources.cnpj.storage import (
    CnpjCapacity,
    CnpjDownloadError,
    assess_download_capacity,
    validate_source_url,
)
from apps.sources.models import CnpjDataset, CnpjDatasetFile


@dataclass(frozen=True, slots=True)
class PreviewPlan:
    available: bool
    allowed: bool
    reason: str
    dataset: CnpjDataset | None = None
    source_file: CnpjDatasetFile | None = None
    capacity: CnpjCapacity | None = None


def build_preview_plan() -> PreviewPlan:
    if not settings.CNPJ_SOURCE_BASE_URL or not settings.CNPJ_WEBDAV_TOKEN:
        return PreviewPlan(False, False, "A origem CNPJ ainda não foi configurada.")
    dataset = (
        CnpjDataset.objects.filter(
            source__key="receita-cnpj",
            source__enabled=True,
            status=CnpjDataset.Status.READY,
            is_current=True,
        )
        .select_related("source")
        .first()
    )
    if not dataset:
        return PreviewPlan(False, False, "Nenhum manifesto CNPJ validado está disponível.")
    source_file = (
        dataset.files.filter(kind=CnpjDatasetFile.Kind.ESTABLISHMENTS)
        .order_by("size_bytes", "part_number")
        .first()
    )
    if not source_file:
        return PreviewPlan(False, False, "O manifesto não possui arquivo de estabelecimentos.")
    try:
        validate_source_url(source_file.url)
    except CnpjDownloadError as exc:
        return PreviewPlan(True, False, str(exc), dataset, source_file)
    capacity = assess_download_capacity(source_file.size_bytes)
    return PreviewPlan(
        True,
        capacity.allowed,
        capacity.reason,
        dataset,
        source_file,
        capacity,
    )
