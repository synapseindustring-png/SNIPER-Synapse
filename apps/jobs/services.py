import logging
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta

from django.db import close_old_connections, transaction
from django.utils import timezone

from .models import Job, JobAttempt


logger = logging.getLogger(__name__)


class JobLeaseLost(RuntimeError):
    """Raised when a worker no longer owns the job it was processing."""


@dataclass(slots=True)
class JobLeaseState:
    lost: bool = False
    renewals: int = 0


@transaction.atomic
def claim_next_job(worker_id: str, lock_seconds: int) -> Job | None:
    now = timezone.now()
    recoverable = Job.objects.filter(
        status=Job.Status.RUNNING,
        lock_expires_at__lt=now,
    )
    recoverable.update(
        status=Job.Status.RETRY_SCHEDULED,
        lock_owner="",
        lock_expires_at=None,
    )

    job = (
        Job.objects.select_for_update(skip_locked=True)
        .filter(
            status__in=(Job.Status.PENDING, Job.Status.RETRY_SCHEDULED),
            run_after__lte=now,
        )
        .order_by("-priority", "run_after", "created_at")
        .first()
    )
    if job is None:
        return None

    job.status = Job.Status.RUNNING
    job.attempt_count += 1
    job.lock_owner = worker_id
    job.lock_expires_at = now + timedelta(seconds=lock_seconds)
    job.heartbeat_at = now
    if job.started_at is None:
        job.started_at = now
    job.save(
        update_fields=(
            "status",
            "attempt_count",
            "lock_owner",
            "lock_expires_at",
            "heartbeat_at",
            "started_at",
            "updated_at",
        )
    )
    JobAttempt.objects.create(
        job=job,
        attempt_number=job.attempt_count,
        worker_id=worker_id,
    )
    return job


@transaction.atomic
def renew_job_lease(job_id, worker_id: str, lock_seconds: int) -> bool:
    if lock_seconds < 1:
        raise ValueError("lock_seconds must be positive")
    now = timezone.now()
    return bool(
        Job.objects.filter(
            pk=job_id,
            status=Job.Status.RUNNING,
            lock_owner=worker_id,
        ).update(
            heartbeat_at=now,
            lock_expires_at=now + timedelta(seconds=lock_seconds),
        )
    )


@contextmanager
def maintain_job_lease(job_id, worker_id: str, lock_seconds: int):
    """Renew a running job lease in a separate DB connection until work finishes."""
    if lock_seconds < 1:
        raise ValueError("lock_seconds must be positive")
    state = JobLeaseState()
    stop = threading.Event()
    interval = max(0.25, lock_seconds / 3)

    def heartbeat_loop():
        close_old_connections()
        try:
            while not stop.wait(interval):
                try:
                    if not renew_job_lease(job_id, worker_id, lock_seconds):
                        state.lost = True
                        return
                    state.renewals += 1
                except Exception:
                    logger.exception("job_heartbeat_failed", extra={"job_id": str(job_id)})
                    close_old_connections()
        finally:
            close_old_connections()

    thread = threading.Thread(
        target=heartbeat_loop,
        name=f"job-heartbeat-{job_id}",
        daemon=True,
    )
    thread.start()
    try:
        yield state
    finally:
        stop.set()
        thread.join(timeout=min(interval + 1, 5))


def _owned_running_job(job_id, worker_id: str) -> Job:
    job = Job.objects.select_for_update().get(pk=job_id)
    if job.status != Job.Status.RUNNING or job.lock_owner != worker_id:
        raise JobLeaseLost(f"Worker {worker_id} no longer owns job {job_id}")
    return job


@transaction.atomic
def mark_succeeded(job_id, worker_id: str) -> None:
    now = timezone.now()
    job = _owned_running_job(job_id, worker_id)
    job.status = Job.Status.SUCCEEDED
    job.finished_at = now
    job.lock_owner = ""
    job.lock_expires_at = None
    job.error_summary = ""
    job.save()
    job.attempts.filter(attempt_number=job.attempt_count).update(
        finished_at=now,
        succeeded=True,
    )


@transaction.atomic
def mark_failed(job_id, worker_id: str, message: str) -> None:
    now = timezone.now()
    job = _owned_running_job(job_id, worker_id)
    retry = job.attempt_count < job.max_attempts
    job.status = Job.Status.RETRY_SCHEDULED if retry else Job.Status.FAILED
    job.run_after = now + timedelta(seconds=min(300, 2 ** job.attempt_count))
    job.finished_at = None if retry else now
    job.lock_owner = ""
    job.lock_expires_at = None
    job.error_summary = message[:2000]
    job.save()
    job.attempts.filter(attempt_number=job.attempt_count).update(
        finished_at=now,
        succeeded=False,
        error_detail=message[:10000],
    )


def execute_job(job: Job) -> None:
    if job.type == Job.Type.NOOP:
        return
    if job.type == Job.Type.DISCOVER_CNPJ:
        from apps.sources.cnpj.jobs import execute_discover_cnpj

        execute_discover_cnpj(job)
        return
    if job.type == Job.Type.SYNC_CNPJ_SOURCE:
        from apps.sources.cnpj.manifest import sync_latest_manifest

        dataset = sync_latest_manifest()
        Job.objects.filter(pk=job.pk).update(records_processed=dataset.files.count())
        return
    if job.type == Job.Type.FIND_JOBS:
        from apps.sources.jobs.jobs import execute_find_jobs

        execute_find_jobs(job)
        return
    if job.type == Job.Type.CALCULATE_SCORE:
        from django.utils.dateparse import parse_datetime

        from apps.companies.models import Company
        from apps.scoring.engine import calculate_score
        from apps.scoring.models import RuleSet

        company = Company.objects.get(pk=job.payload["company_id"])
        rule_set = RuleSet.objects.get(pk=job.payload["rule_set_id"])
        as_of = parse_datetime(job.payload["as_of"])
        if as_of is None or not timezone.is_aware(as_of):
            raise ValueError("CALCULATE_SCORE requires a timezone-aware as_of")
        calculate_score(company, as_of=as_of, rule_set=rule_set)
        Job.objects.filter(pk=job.pk).update(records_processed=1, records_success=1)
        return
    if job.type == Job.Type.DETECT_SIGNALS:
        from apps.companies.models import Company
        from apps.scoring.services import enqueue_company_score
        from apps.signals.detector import detect_company_signals

        company = Company.objects.get(pk=job.payload["company_id"])
        stats = detect_company_signals(company)
        Job.objects.filter(pk=job.pk).update(
            records_processed=stats.records_scanned,
            records_success=stats.signals_matched,
            records_failed=0,
        )
        enqueue_company_score(company)
        return
    if job.type == Job.Type.CRAWL_WEBSITE:
        from apps.companies.models import Company
        from apps.crawler.services import crawl_company_website
        from apps.scoring.services import enqueue_company_score
        from apps.signals.detector import detect_company_signals

        company = Company.objects.get(pk=job.payload["company_id"])
        outcome = crawl_company_website(company)
        stats = detect_company_signals(company)
        enqueue_company_score(company)
        Job.objects.filter(pk=job.pk).update(
            records_processed=outcome.pages_attempted,
            records_success=len(outcome.pages),
            records_failed=outcome.pages_failed,
        )
        return
    raise NotImplementedError(f"Handler not implemented for job type {job.type}")
