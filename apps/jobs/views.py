from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Max, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from apps.sources.models import Source

from .forms import JobFilterForm
from .models import Job
from .operations import sanitize_job_data, storage_status


def _require_staff(request):
    if not request.user.is_staff:
        raise Http404


@login_required
def job_list(request):
    _require_staff(request)
    jobs = Job.objects.order_by("-created_at")
    form = JobFilterForm(request.GET)
    if form.is_valid():
        filters = form.cleaned_data
        if filters["q"]:
            term = filters["q"].strip()
            search = Q(idempotency_key__icontains=term) | Q(error_summary__icontains=term)
            try:
                search |= Q(pk=uuid.UUID(term))
            except ValueError:
                pass
            jobs = jobs.filter(search)
        if filters["job_type"]:
            jobs = jobs.filter(type=filters["job_type"])
        if filters["status"]:
            jobs = jobs.filter(status=filters["status"])
        if filters["created_since"]:
            jobs = jobs.filter(created_at__date__gte=filters["created_since"])
    page = Paginator(jobs, 50).get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)
    status_counts = {
        row["status"]: row["count"]
        for row in Job.objects.values("status").annotate(count=Count("id"))
    }
    sources = Source.objects.annotate(
        record_count=Count("records"), last_record_at=Max("records__collected_at")
    ).order_by("name")
    return render(
        request,
        "jobs/job_list.html",
        {
            "form": form,
            "page": page,
            "querystring": query_params.urlencode(),
            "status_counts": status_counts,
            "sources": sources,
            "storage": storage_status(),
        },
    )


@login_required
def job_detail(request, pk):
    _require_staff(request)
    job = get_object_or_404(Job.objects.prefetch_related("attempts"), pk=pk)
    for attempt in job.attempts.all():
        attempt.safe_metrics = sanitize_job_data(attempt.metrics)
        attempt.safe_error_detail = sanitize_job_data(attempt.error_detail)
    return render(
        request,
        "jobs/job_detail.html",
        {
            "job": job,
            "safe_payload": sanitize_job_data(job.payload),
            "safe_error_summary": sanitize_job_data(job.error_summary),
        },
    )
import uuid
