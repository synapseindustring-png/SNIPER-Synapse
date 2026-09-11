from contextlib import nullcontext
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.discovery.models import QueryRun
from apps.jobs.models import Job
from apps.sources.models import CnpjCandidate, CnpjDataset, CnpjDatasetFile, Source

from .complements import CnpjCompanyReader, CnpjSimplesReader
from .establishments import CnpjEstablishmentFilter, CnpjEstablishmentReader
from .ingestion import (
    ingest_company_complement,
    ingest_establishment,
    ingest_simples_complement,
    stage_establishment,
)
from .storage import downloaded_cnpj_zip


def _safe_source_path(value: str) -> Path:
    temp_root = Path(settings.TEMP_DATA_DIR).resolve()
    source_path = Path(value).resolve(strict=True)
    try:
        source_path.relative_to(temp_root)
    except ValueError as exc:
        raise ValueError(f"CNPJ source must be inside {temp_root}") from exc
    if source_path.suffix.lower() != ".zip":
        raise ValueError("CNPJ source must be a ZIP file")
    return source_path


def _optional_sources(
    payload: dict,
    path_key: str,
    url_key: str,
    maximum: int,
) -> list[tuple[str, bool]]:
    paths = payload.get(path_key) or []
    urls = payload.get(url_key) or []
    if not isinstance(paths, list) or not isinstance(urls, list):
        raise ValueError(f"{path_key} and {url_key} must be lists")
    if paths and urls:
        raise ValueError(f"Provide {path_key} or {url_key}, not both")
    values = paths or urls
    if len(values) > maximum:
        raise ValueError(f"At most {maximum} complement sources are allowed")
    return [(str(value), bool(urls)) for value in values]


def _source_context(value: str, is_url: bool, job_id: str, suffix: str):
    if is_url:
        return downloaded_cnpj_zip(value, f"{job_id}-{suffix}")
    return nullcontext(_safe_source_path(value))


def _validate_manifest_urls(
    *,
    source: Source,
    dataset_reference: str,
    establishment_url: str | None,
    company_sources: list[tuple[str, bool]],
    simples_sources: list[tuple[str, bool]],
) -> None:
    requested = {
        CnpjDatasetFile.Kind.ESTABLISHMENTS: [establishment_url] if establishment_url else [],
        CnpjDatasetFile.Kind.COMPANIES: [value for value, is_url in company_sources if is_url],
        CnpjDatasetFile.Kind.SIMPLES: [value for value, is_url in simples_sources if is_url],
    }
    if not any(requested.values()):
        return
    dataset = CnpjDataset.objects.filter(
        source=source,
        reference=dataset_reference,
        status=CnpjDataset.Status.READY,
    ).first()
    if not dataset:
        raise ValueError("Remote CNPJ sources require a ready manifest for the same competence")
    for kind, urls in requested.items():
        if not urls:
            continue
        allowed = set(dataset.files.filter(kind=kind).values_list("url", flat=True))
        if not set(urls).issubset(allowed):
            raise ValueError(f"A requested {kind} URL is not part of the selected manifest")


def execute_discover_cnpj(job: Job) -> None:
    payload = job.payload
    query_run = QueryRun.objects.select_related("query").get(pk=payload["query_run_id"])
    dataset_reference = str(payload["dataset_reference"]).strip()
    if not dataset_reference:
        raise ValueError("dataset_reference is required")
    if bool(payload.get("source_path")) == bool(payload.get("source_url")):
        raise ValueError("Provide exactly one of source_path or source_url")
    source_context = (
        nullcontext(_safe_source_path(payload["source_path"]))
        if payload.get("source_path")
        else downloaded_cnpj_zip(payload["source_url"], str(job.id))
    )
    mode = str(payload.get("mode", "PREVIEW")).upper()
    if mode not in {"PREVIEW", "FULL"}:
        raise ValueError("mode must be PREVIEW or FULL")
    configured_limit = (
        settings.CNPJ_PREVIEW_MAX_RESULTS
        if mode == "PREVIEW"
        else settings.CNPJ_MAX_PERSISTED_MATCHES
    )
    max_results = int(payload.get("max_results", configured_limit))
    if max_results < 1 or max_results > configured_limit:
        raise ValueError(f"max_results must be between 1 and {configured_limit}")
    filter_payload = payload.get("filters", {})
    filters = CnpjEstablishmentFilter(
        registration_statuses=frozenset(filter_payload.get("registration_statuses", [])),
        states=frozenset(filter_payload.get("states", [])),
        municipality_codes=frozenset(filter_payload.get("municipality_codes", [])),
        cnae_codes=frozenset(filter_payload.get("cnae_codes", [])),
        cnae_prefixes=tuple(filter_payload.get("cnae_prefixes", [])),
        include_secondary_cnaes=bool(filter_payload.get("include_secondary_cnaes", False)),
    )
    source = Source.objects.get(key="receita-cnpj", enabled=True)
    observed_at = timezone.now()
    company_sources = _optional_sources(
        payload,
        "company_source_paths",
        "company_source_urls",
        10,
    )
    simples_sources = _optional_sources(
        payload,
        "simples_source_paths",
        "simples_source_urls",
        1,
    )
    if mode == "PREVIEW" and (company_sources or simples_sources):
        raise ValueError("CNPJ complements are allowed only in FULL mode")
    _validate_manifest_urls(
        source=source,
        dataset_reference=dataset_reference,
        establishment_url=payload.get("source_url"),
        company_sources=company_sources,
        simples_sources=simples_sources,
    )

    query_run.status = QueryRun.Status.RUNNING
    query_run.dataset_reference = dataset_reference
    query_run.started_at = observed_at
    query_run.finished_at = None
    query_run.save(
        update_fields=("status", "dataset_reference", "started_at", "finished_at")
    )
    limit_reached = False
    try:
        with source_context as source_path:
            reader = CnpjEstablishmentReader(source_path, filters)
            for establishment in reader:
                with transaction.atomic():
                    candidate = stage_establishment(establishment, query_run=query_run)
                    outcome = ingest_establishment(
                        establishment,
                        source=source,
                        observed_at=observed_at,
                        dataset_reference=dataset_reference,
                        query_run=query_run,
                    )
                    if candidate.company_id != outcome.company.id:
                        candidate.company = outcome.company
                        candidate.save(update_fields=("company", "updated_at"))
                if reader.stats.rows_matched >= max_results:
                    limit_reached = True
                    break

        establishment_rows = reader.stats.rows_read
        invalid_rows = reader.stats.rows_invalid
        candidates = list(
            CnpjCandidate.objects.filter(query_run=query_run).select_related("company")
        )
        candidates_by_basic: dict[str, list[CnpjCandidate]] = {}
        for candidate in candidates:
            candidates_by_basic.setdefault(candidate.cnpj_basico, []).append(candidate)

        company_rows = 0
        company_matches = 0
        company_sources_processed = 0
        company_remaining = set(candidates_by_basic)
        for index, (value, is_url) in enumerate(company_sources):
            if not company_remaining:
                break
            with _source_context(value, is_url, str(job.id), f"companies-{index}") as path:
                company_sources_processed += 1
                company_reader = CnpjCompanyReader(path, frozenset(company_remaining))
                for company_record in company_reader:
                    for candidate in candidates_by_basic[company_record.cnpj_basico]:
                        ingest_company_complement(
                            candidate,
                            company_record,
                            source=source,
                            observed_at=observed_at,
                            dataset_reference=dataset_reference,
                        )
                    company_remaining.discard(company_record.cnpj_basico)
                company_rows += company_reader.stats.rows_read
                company_matches += company_reader.stats.rows_matched
                invalid_rows += company_reader.stats.rows_invalid

        simples_rows = 0
        simples_matches = 0
        simples_sources_processed = 0
        simples_remaining = set(candidates_by_basic)
        for index, (value, is_url) in enumerate(simples_sources):
            if not simples_remaining:
                break
            with _source_context(value, is_url, str(job.id), f"simples-{index}") as path:
                simples_sources_processed += 1
                simples_reader = CnpjSimplesReader(path, frozenset(simples_remaining))
                for simples_record in simples_reader:
                    for candidate in candidates_by_basic[simples_record.cnpj_basico]:
                        ingest_simples_complement(
                            candidate,
                            simples_record,
                            source=source,
                            observed_at=observed_at,
                            dataset_reference=dataset_reference,
                        )
                    simples_remaining.discard(simples_record.cnpj_basico)
                simples_rows += simples_reader.stats.rows_read
                simples_matches += simples_reader.stats.rows_matched
                invalid_rows += simples_reader.stats.rows_invalid
    except Exception:
        query_run.status = QueryRun.Status.FAILED
        if "reader" in locals():
            query_run.records_processed = reader.stats.rows_read
            query_run.records_matched = reader.stats.rows_matched
            query_run.records_failed = reader.stats.rows_invalid
        query_run.finished_at = timezone.now()
        query_run.save()
        raise

    complement_incomplete = bool(
        (company_sources and company_remaining) or (simples_sources and simples_remaining)
    )
    partial = mode == "PREVIEW" or limit_reached or complement_incomplete
    query_run.status = QueryRun.Status.PARTIAL if partial else QueryRun.Status.SUCCEEDED
    total_rows = establishment_rows + company_rows + simples_rows
    query_run.records_processed = total_rows
    query_run.records_matched = reader.stats.rows_matched
    query_run.records_failed = invalid_rows
    query_run.coverage = {
        "complete": not partial,
        "mode": mode,
        "limit_reached": limit_reached,
        "max_results": max_results,
        "staged_candidates": len(candidates),
        "companies": {
            "sources_processed": company_sources_processed,
            "rows_scanned": company_rows,
            "basics_matched": company_matches,
            "basics_missing": len(company_remaining),
        },
        "simples": {
            "sources_processed": simples_sources_processed,
            "rows_scanned": simples_rows,
            "basics_matched": simples_matches,
            "basics_missing": len(simples_remaining),
        },
    }
    query_run.finished_at = timezone.now()
    query_run.save()
    Job.objects.filter(pk=job.pk).update(
        records_processed=total_rows,
        records_success=reader.stats.rows_matched,
        records_failed=invalid_rows,
    )
