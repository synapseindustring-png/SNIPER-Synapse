from django.db import transaction
from django.utils import timezone

from apps.companies.models import Company
from apps.signals.services import enqueue_signal_detection
from apps.sources.jobs.base import JobSourceItem
from apps.sources.jobs.services import persist_source_item

from .models import JobPosting, JobPostingReview


class JobReviewResolutionError(RuntimeError):
    pass


@transaction.atomic
def approve_job_review(review_id, *, company: Company, user, note: str) -> JobPosting:
    review = JobPostingReview.objects.select_for_update().select_related("source").get(pk=review_id)
    if review.status != JobPostingReview.Status.PENDING:
        raise JobReviewResolutionError("Esta revisão já foi resolvida.")
    item = JobSourceItem(
        external_id=review.external_id,
        title=review.title,
        company_name=review.company_name,
        company_domain=review.company_domain,
        location=review.location,
        url=review.url,
        published_on=review.published_on.isoformat() if review.published_on else "",
        valid_through=review.valid_through.isoformat() if review.valid_through else "",
        employment_type=review.employment_type,
        metadata={**review.metadata, "approved_from_review": str(review.pk)},
    )
    fingerprint = persist_source_item(review.source, company, item, timezone.now())
    if not fingerprint:
        raise JobReviewResolutionError("Não foi possível persistir a vaga para a empresa escolhida.")
    posting = JobPosting.objects.get(company=company, fingerprint=fingerprint)
    review.status = JobPostingReview.Status.MATCHED
    review.suggested_company = company
    review.job_posting = posting
    review.reviewed_by = user
    review.reviewed_at = timezone.now()
    review.resolution_note = note.strip()
    review.save(
        update_fields=(
            "status",
            "suggested_company",
            "job_posting",
            "reviewed_by",
            "reviewed_at",
            "resolution_note",
        )
    )
    transaction.on_commit(lambda: enqueue_signal_detection(company))
    return posting


@transaction.atomic
def dismiss_job_review(review_id, *, user, reason: str) -> JobPostingReview:
    review = JobPostingReview.objects.select_for_update().get(pk=review_id)
    if review.status != JobPostingReview.Status.PENDING:
        raise JobReviewResolutionError("Esta revisão já foi resolvida.")
    review.status = JobPostingReview.Status.DISMISSED
    review.reviewed_by = user
    review.reviewed_at = timezone.now()
    review.resolution_note = reason.strip()
    review.save(update_fields=("status", "reviewed_by", "reviewed_at", "resolution_note"))
    return review
