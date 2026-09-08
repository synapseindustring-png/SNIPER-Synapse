from django.utils import timezone

from apps.companies.models import Company
from apps.jobs.models import Job

from .models import RuleSet


def enqueue_company_score(company: Company, *, as_of=None) -> tuple[Job, bool]:
    as_of = as_of or timezone.now()
    target = (
        RuleSet.Target.INDUSTRY
        if company.company_type == Company.Type.INDUSTRY
        else RuleSet.Target.PARTNER
    )
    rule_set = RuleSet.objects.get(
        target=target,
        active=True,
        status=RuleSet.Status.PUBLISHED,
    )
    latest_signal = (
        company.signals.order_by("-updated_at").values_list("updated_at", flat=True).first()
    )
    data_version = max(
        timestamp for timestamp in (company.updated_at, latest_signal) if timestamp
    )
    return Job.objects.get_or_create(
        idempotency_key=(
            f"score:{company.pk}:{rule_set.pk}:{data_version.isoformat()}:{as_of.date().isoformat()}"
        ),
        defaults={
            "type": Job.Type.CALCULATE_SCORE,
            "payload": {
                "company_id": str(company.pk),
                "rule_set_id": str(rule_set.pk),
                "as_of": as_of.isoformat(),
            },
            "priority": 10,
        },
    )
