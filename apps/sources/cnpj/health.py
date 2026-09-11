from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.jobs.operations import storage_status
from apps.sources.models import CnpjDataset, CnpjDatasetFile, Source


@dataclass(frozen=True, slots=True)
class CnpjManifestHealth:
    state: str
    label: str
    reason: str
    source: Source | None
    dataset: CnpjDataset | None
    establishment_parts: int = 0
    company_parts: int = 0
    simples_parts: int = 0
    total_files: int = 0
    total_bytes: int = 0
    largest_file_bytes: int = 0
    safe_capacity_bytes: int = 0
    fits_storage: bool = False
    is_stale: bool = False


def manifest_health(*, at=None) -> CnpjManifestHealth:
    at = at or timezone.now()
    source = Source.objects.filter(key="receita-cnpj").first()
    if not source:
        return CnpjManifestHealth(
            "unavailable",
            "Indisponível",
            "A fonte Receita CNPJ não está cadastrada.",
            None,
            None,
        )
    if not source.enabled:
        return CnpjManifestHealth(
            "disabled",
            "Desabilitada",
            "A fonte Receita CNPJ está desabilitada.",
            source,
            None,
        )
    dataset = (
        CnpjDataset.objects.filter(source=source, is_current=True)
        .prefetch_related("files")
        .first()
    )
    if not dataset:
        return CnpjManifestHealth(
            "unavailable",
            "Sem manifesto",
            "Nenhuma competência atual foi sincronizada.",
            source,
            None,
        )

    files = list(dataset.files.all())
    establishments = {
        item.part_number
        for item in files
        if item.kind == CnpjDatasetFile.Kind.ESTABLISHMENTS
    }
    companies = {
        item.part_number for item in files if item.kind == CnpjDatasetFile.Kind.COMPANIES
    }
    simples = [item for item in files if item.kind == CnpjDatasetFile.Kind.SIMPLES]
    complete = (
        establishments == set(range(10))
        and companies == set(range(10))
        and len(simples) == 1
    )
    reference_at = dataset.verified_at or dataset.discovered_at
    stale = reference_at < at - timedelta(days=settings.CNPJ_MANIFEST_MAX_AGE_DAYS)
    storage = storage_status()
    largest = max((item.size_bytes for item in files), default=0)
    fits = largest > 0 and largest <= storage.safe_cnpj_capacity_bytes

    if dataset.status != CnpjDataset.Status.READY:
        state, label, reason = "degraded", "Inválida", "A competência atual não está pronta."
    elif not complete:
        state, label, reason = (
            "degraded",
            "Incompleta",
            "O manifesto atual não possui exatamente 10+10 partes e o Simples.",
        )
    elif stale:
        state, label, reason = (
            "degraded",
            "Desatualizada",
            f"O manifesto excedeu {settings.CNPJ_MANIFEST_MAX_AGE_DAYS} dias.",
        )
    elif not fits:
        state, label, reason = (
            "degraded",
            "Sem capacidade",
            "O maior arquivo excede a capacidade temporária segura atual.",
        )
    else:
        state, label, reason = (
            "healthy",
            "Saudável",
            "Manifesto completo, recente e compatível com a capacidade atual.",
        )
    return CnpjManifestHealth(
        state=state,
        label=label,
        reason=reason,
        source=source,
        dataset=dataset,
        establishment_parts=len(establishments),
        company_parts=len(companies),
        simples_parts=len(simples),
        total_files=len(files),
        total_bytes=sum(item.size_bytes for item in files),
        largest_file_bytes=largest,
        safe_capacity_bytes=storage.safe_cnpj_capacity_bytes,
        fits_storage=fits,
        is_stale=stale,
    )
