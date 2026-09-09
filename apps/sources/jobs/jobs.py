from django.conf import settings

from apps.companies.models import Company
from apps.jobs.models import Job
from apps.scoring.services import enqueue_company_score
from apps.signals.detector import detect_company_signals
from apps.sources.models import Source

from .base import JobCollectionLimits, JobsAdapterError
from .fixture import FixtureJobsAdapter
from .services import collect_company_jobs


def _bounded_positive(value, configured_max: int) -> int:
    try:
        requested = int(value)
    except (TypeError, ValueError) as exc:
        raise JobsAdapterError("Limite solicitado inválido.") from exc
    if requested <= 0:
        raise JobsAdapterError("Limite solicitado deve ser positivo.")
    return min(requested, configured_max)


def execute_find_jobs(job: Job):
    payload = job.payload
    company = Company.objects.get(pk=payload["company_id"])
    source = Source.objects.get(key=payload.get("source_key", "jobs-fixture"))
    if source.key != "jobs-fixture":
        raise JobsAdapterError("Adapter de vagas não permitido nesta versão.")
    limits = JobCollectionLimits(
        max_pages=_bounded_positive(payload.get("max_pages", settings.JOBS_MAX_PAGES), settings.JOBS_MAX_PAGES),
        max_results=_bounded_positive(payload.get("max_results", settings.JOBS_MAX_RESULTS), settings.JOBS_MAX_RESULTS),
        max_bytes=settings.JOBS_MAX_RESPONSE_BYTES,
    )
    adapter = FixtureJobsAdapter(settings.JOBS_FIXTURE_ROOT, payload["fixture_name"])
    outcome = collect_company_jobs(
        company,
        source=source,
        adapter=adapter,
        mode=payload.get("mode", "PREVIEW"),
        limits=limits,
    )
    Job.objects.filter(pk=job.pk).update(
        records_processed=outcome.items_scanned,
        records_success=outcome.jobs_persisted if outcome.mode == "FULL" else outcome.items_matched,
        records_failed=outcome.reviews_created,
    )
    job.attempts.filter(attempt_number=job.attempt_count).update(
        metrics={
            "mode": outcome.mode,
            "pages_read": outcome.pages_read,
            "bytes_read": outcome.bytes_read,
            "truncated": outcome.truncated,
            "items_matched": outcome.items_matched,
            "reviews_created": outcome.reviews_created,
        }
    )
    if outcome.mode == "FULL" and outcome.jobs_persisted:
        detect_company_signals(company)
        enqueue_company_score(company)
    return outcome
