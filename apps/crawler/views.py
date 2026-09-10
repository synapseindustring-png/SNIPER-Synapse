from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import JobReviewDismissForm, JobReviewMatchForm
from .models import JobPostingReview
from .reviews import JobReviewResolutionError, approve_job_review, dismiss_job_review


def _require_staff(request):
    if not request.user.is_staff:
        raise Http404


@login_required
def job_review_list(request):
    _require_staff(request)
    status = request.GET.get("status", JobPostingReview.Status.PENDING)
    valid_statuses = {value for value, _ in JobPostingReview.Status.choices}
    if status not in valid_statuses:
        status = JobPostingReview.Status.PENDING
    reviews = JobPostingReview.objects.filter(status=status).select_related(
        "source", "suggested_company", "reviewed_by"
    )
    page = Paginator(reviews, 50).get_page(request.GET.get("page"))
    return render(request, "crawler/job_review_list.html", {"page": page, "status": status})


@login_required
def job_review_detail(request, pk):
    _require_staff(request)
    review = get_object_or_404(
        JobPostingReview.objects.select_related(
            "source", "suggested_company", "reviewed_by", "job_posting__company"
        ),
        pk=pk,
    )
    initial_reference = str(review.suggested_company_id or "")
    return render(
        request,
        "crawler/job_review_detail.html",
        {
            "review": review,
            "match_form": JobReviewMatchForm(initial={"company_reference": initial_reference}),
            "dismiss_form": JobReviewDismissForm(),
        },
    )


@login_required
@require_POST
def job_review_match(request, pk):
    _require_staff(request)
    review = get_object_or_404(JobPostingReview, pk=pk)
    form = JobReviewMatchForm(request.POST)
    if form.is_valid():
        try:
            posting = approve_job_review(
                review.pk,
                company=form.cleaned_data["company_reference"],
                user=request.user,
                note=form.cleaned_data["note"],
            )
        except JobReviewResolutionError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Vaga vinculada; detecção de sinais adicionada à fila.")
            return redirect("company-detail", pk=posting.company_id)
    else:
        messages.error(request, "Revise a empresa e a justificativa informadas.")
    return render(
        request,
        "crawler/job_review_detail.html",
        {"review": review, "match_form": form, "dismiss_form": JobReviewDismissForm()},
        status=400,
    )


@login_required
@require_POST
def job_review_dismiss(request, pk):
    _require_staff(request)
    review = get_object_or_404(JobPostingReview, pk=pk)
    form = JobReviewDismissForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Informe o motivo do descarte.")
        return redirect("job-review-detail", pk=review.pk)
    try:
        dismiss_job_review(review.pk, user=request.user, reason=form.cleaned_data["reason"])
    except JobReviewResolutionError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Candidato descartado com registro de auditoria.")
    return redirect("job-review-list")
