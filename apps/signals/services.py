from apps.companies.models import Company
from apps.jobs.models import Job

from .models import SignalRule


def enqueue_signal_detection(company: Company) -> tuple[Job, bool]:
    latest_record = (
        company.source_records.order_by("-collected_at")
        .values_list("collected_at", flat=True)
        .first()
    )
    latest_rule = (
        SignalRule.objects.filter(active=True)
        .order_by("-updated_at")
        .values_list("updated_at", flat=True)
        .first()
    )
    data_version = max(
        timestamp for timestamp in (company.updated_at, latest_record, latest_rule) if timestamp
    )
    return Job.objects.get_or_create(
        idempotency_key=f"signals:{company.pk}:{data_version.isoformat()}",
        defaults={
            "type": Job.Type.DETECT_SIGNALS,
            "payload": {"company_id": str(company.pk)},
            "priority": 20,
        },
    )
