from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import Job, JobAttempt


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
def mark_succeeded(job_id) -> None:
    now = timezone.now()
    job = Job.objects.select_for_update().get(pk=job_id)
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
def mark_failed(job_id, message: str) -> None:
    now = timezone.now()
    job = Job.objects.select_for_update().get(pk=job_id)
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
    raise NotImplementedError(f"Handler not implemented for job type {job.type}")
