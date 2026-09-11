from dataclasses import dataclass

from django.conf import settings

from apps.discovery.coverage import find_valid_coverage
from apps.sources.cnpj.storage import (
    CnpjCapacity,
    CnpjDownloadError,
    assess_download_capacity,
    validate_source_url,
)
from apps.sources.models import CnpjDataset, CnpjDatasetFile

from .models import DiscoveryQuery, SourceCoverage


@dataclass(frozen=True, slots=True)
class PreviewPlan:
    available: bool
    allowed: bool
    reason: str
    dataset: CnpjDataset | None = None
    source_file: CnpjDatasetFile | None = None
    capacity: CnpjCapacity | None = None
    coverage: SourceCoverage | None = None


@dataclass(frozen=True, slots=True)
class FullPlan:
    available: bool
    allowed: bool
    reason: str
    dataset: CnpjDataset | None = None
    establishment_files: tuple[CnpjDatasetFile, ...] = ()
    company_files: tuple[CnpjDatasetFile, ...] = ()
    simples_file: CnpjDatasetFile | None = None
    total_transfer_bytes: int = 0
    peak_temp_bytes: int = 0
    capacity: CnpjCapacity | None = None


def build_preview_plan(query: DiscoveryQuery | None = None) -> PreviewPlan:
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
    if dataset and query:
        coverage = find_valid_coverage(
            source=dataset.source,
            dataset_reference=dataset.reference,
            query=query,
        )
        if coverage:
            return PreviewPlan(
                True,
                True,
                "Cobertura local válida: nenhum download será realizado.",
                dataset=dataset,
                coverage=coverage,
            )
    if not settings.CNPJ_SOURCE_BASE_URL or not settings.CNPJ_WEBDAV_TOKEN:
        return PreviewPlan(False, False, "A origem CNPJ ainda não foi configurada.")
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


def build_full_plan(query: DiscoveryQuery | None = None) -> FullPlan:
    if not settings.CNPJ_FULL_ENABLED:
        return FullPlan(False, False, "A execução completa está desabilitada pelo kill switch.")
    if not settings.CNPJ_SOURCE_BASE_URL or not settings.CNPJ_WEBDAV_TOKEN:
        return FullPlan(False, False, "A origem CNPJ ainda não foi configurada.")
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
        return FullPlan(False, False, "Nenhum manifesto CNPJ validado está disponível.")
    if query and find_valid_coverage(
        source=dataset.source,
        dataset_reference=dataset.reference,
        query=query,
    ):
        return FullPlan(
            True,
            False,
            "Esta competência e estes filtros já possuem cobertura local.",
            dataset,
        )
    establishments = tuple(
        dataset.files.filter(kind=CnpjDatasetFile.Kind.ESTABLISHMENTS).order_by("part_number")
    )
    companies = tuple(
        dataset.files.filter(kind=CnpjDatasetFile.Kind.COMPANIES).order_by("part_number")
    )
    simples_files = tuple(dataset.files.filter(kind=CnpjDatasetFile.Kind.SIMPLES))
    if len(establishments) != 10 or len(companies) != 10 or len(simples_files) != 1:
        return FullPlan(
            True,
            False,
            "O manifesto não contém as 10+10 partes e o Simples.",
            dataset,
        )
    all_files = (*establishments, *companies, simples_files[0])
    try:
        for source_file in all_files:
            validate_source_url(source_file.url)
    except CnpjDownloadError as exc:
        return FullPlan(True, False, str(exc), dataset)
    peak = max(source_file.size_bytes for source_file in all_files)
    capacity = assess_download_capacity(peak)
    return FullPlan(
        True,
        capacity.allowed,
        capacity.reason,
        dataset,
        establishments,
        companies,
        simples_files[0],
        sum(source_file.size_bytes for source_file in all_files),
        peak,
        capacity,
    )
