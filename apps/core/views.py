from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db import connection
from django.db.models import OuterRef, Subquery
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone

from apps.companies.models import Company
from apps.discovery.models import DiscoveryQuery, QueryResult
from apps.jobs.models import Job
from apps.scoring.models import ScoreSnapshot
from apps.sources.models import CnpjDataset, SourceRecord


@login_required
def dashboard(request):
    active_jobs = Job.objects.filter(
        status__in=(Job.Status.PENDING, Job.Status.RUNNING, Job.Status.RETRY_SCHEDULED)
    ).count()
    recent_results = (
        QueryResult.objects.select_related("company", "query_run__query")
        .order_by("-created_at")[:8]
    )
    latest_score = ScoreSnapshot.objects.filter(company=OuterRef("pk")).order_by(
        "-as_of", "-created_at"
    )
    context = {
        "industry_count": Company.objects.filter(
            company_type=Company.Type.INDUSTRY, deleted_at__isnull=True
        ).count(),
        "partner_count": Company.objects.filter(
            company_type__in=(
                Company.Type.CONSULTANCY,
                Company.Type.INTEGRATOR,
                Company.Type.ENGINEERING,
                Company.Type.SERVICE_PROVIDER,
            ),
            deleted_at__isnull=True,
        ).count(),
        "query_count": DiscoveryQuery.objects.filter(active=True).count(),
        "hot_lead_count": Company.objects.filter(
            company_type=Company.Type.INDUSTRY, deleted_at__isnull=True
        ).annotate(
            latest_classification=Subquery(
                latest_score.values("calculated_classification")[:1]
            )
        ).filter(latest_classification="HOT").count(),
        "recent_collection_count": SourceRecord.objects.filter(
            collected_at__gte=timezone.now() - timedelta(days=30)
        ).count(),
        "recent_results": recent_results,
        "active_jobs": active_jobs,
        "last_job": Job.objects.order_by("-updated_at").first(),
        "current_dataset": CnpjDataset.objects.filter(is_current=True).select_related("source").first(),
    }
    return render(request, "dashboard.html", context)


def health_live(request):
    return JsonResponse({"status": "ok"})


def health_ready(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
