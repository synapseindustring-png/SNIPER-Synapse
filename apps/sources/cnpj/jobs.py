from contextlib import nullcontext
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.discovery.models import QueryRun
from apps.jobs.models import Job
from apps.sources.models import Source

from .establishments import CnpjEstablishmentFilter, CnpjEstablishmentReader
from .ingestion import ingest_establishment
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
                ingest_establishment(
                    establishment,
                    source=source,
                    observed_at=observed_at,
                    dataset_reference=dataset_reference,
                    query_run=query_run,
                )
                if reader.stats.rows_matched >= max_results:
                    limit_reached = True
                    break
    except Exception:
        query_run.status = QueryRun.Status.FAILED
        if "reader" in locals():
            query_run.records_processed = reader.stats.rows_read
            query_run.records_matched = reader.stats.rows_matched
            query_run.records_failed = reader.stats.rows_invalid
        query_run.finished_at = timezone.now()
        query_run.save()
        raise

    partial = mode == "PREVIEW" or limit_reached
    query_run.status = QueryRun.Status.PARTIAL if partial else QueryRun.Status.SUCCEEDED
    query_run.records_processed = reader.stats.rows_read
    query_run.records_matched = reader.stats.rows_matched
    query_run.records_failed = reader.stats.rows_invalid
    query_run.coverage = {
        "complete": not partial,
        "mode": mode,
        "limit_reached": limit_reached,
        "max_results": max_results,
    }
    query_run.finished_at = timezone.now()
    query_run.save()
    Job.objects.filter(pk=job.pk).update(
        records_processed=reader.stats.rows_read,
        records_success=reader.stats.rows_matched,
        records_failed=reader.stats.rows_invalid,
    )
