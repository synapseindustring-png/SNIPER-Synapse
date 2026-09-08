from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import OuterRef, Prefetch, Q, Subquery
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.jobs.models import Job
from apps.scoring.models import RuleSet, ScoreContribution
from apps.scoring.models import ScoreSnapshot
from apps.sources.models import FieldObservation, SourceRecord

from .forms import CompanyFilterForm
from .models import Company, CompanyCnae


@login_required
def company_list(request):
    latest_score = ScoreSnapshot.objects.filter(company=OuterRef("pk")).order_by(
        "-as_of", "-created_at"
    )
    companies = Company.objects.filter(
        company_type=Company.Type.INDUSTRY,
        deleted_at__isnull=True,
    ).annotate(
        latest_priority=Subquery(latest_score.values("priority")[:1]),
        latest_classification=Subquery(
            latest_score.values("calculated_classification")[:1]
        ),
    ).prefetch_related(
        Prefetch("cnaes", queryset=CompanyCnae.objects.filter(is_primary=True), to_attr="primary_cnaes")
    )
    form = CompanyFilterForm(request.GET)
    if form.is_valid():
        filters = form.cleaned_data
        if filters["q"]:
            term = filters["q"].strip()
            companies = companies.filter(
                Q(cnpj__icontains=term)
                | Q(legal_name__icontains=term)
                | Q(trade_name__icontains=term)
                | Q(segment__icontains=term)
            )
        if filters["state"]:
            companies = companies.filter(state=filters["state"])
        if filters["registration_status"]:
            companies = companies.filter(registration_status=filters["registration_status"])
        if filters["commercial_status"]:
            companies = companies.filter(commercial_status=filters["commercial_status"])

    paginator = Paginator(companies, 50)
    page = paginator.get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)
    return render(
        request,
        "companies/company_list.html",
        {"form": form, "page": page, "querystring": query_params.urlencode()},
    )


@login_required
def company_detail(request, pk):
    company = get_object_or_404(
        Company.objects.filter(deleted_at__isnull=True).prefetch_related(
            "cnaes",
            Prefetch(
                "source_records",
                queryset=SourceRecord.objects.select_related("source", "query_run__query")[:100],
                to_attr="recent_source_records",
            ),
            Prefetch(
                "field_observations",
                queryset=FieldObservation.objects.select_related("source_record__source").filter(
                    is_current=True
                )[:100],
                to_attr="current_observations",
            ),
        ),
        pk=pk,
    )
    snapshot = (
        company.score_snapshots.select_related("rule_set")
        .prefetch_related(
            Prefetch(
                "contributions",
                queryset=ScoreContribution.objects.select_related("rule"),
            )
        )
        .first()
    )
    override = company.score_overrides.filter(active=True).first()
    pending_score_job = Job.objects.filter(
        type=Job.Type.CALCULATE_SCORE,
        status__in=(Job.Status.PENDING, Job.Status.RUNNING, Job.Status.RETRY_SCHEDULED),
        payload__company_id=str(company.pk),
    ).exists()
    return render(
        request,
        "companies/company_detail.html",
        {
            "company": company,
            "snapshot": snapshot,
            "score_override": override,
            "pending_score_job": pending_score_job,
        },
    )


@login_required
@require_POST
def company_score(request, pk):
    company = get_object_or_404(Company, pk=pk, deleted_at__isnull=True)
    target = (
        RuleSet.Target.INDUSTRY
        if company.company_type == Company.Type.INDUSTRY
        else RuleSet.Target.PARTNER
    )
    rule_set = get_object_or_404(
        RuleSet,
        target=target,
        active=True,
        status=RuleSet.Status.PUBLISHED,
    )
    latest_signal = company.signals.order_by("-updated_at").values_list("updated_at", flat=True).first()
    now = timezone.now()
    data_version = max(timestamp for timestamp in (company.updated_at, latest_signal) if timestamp)
    _, created = Job.objects.get_or_create(
        idempotency_key=(
            f"score:{company.pk}:{rule_set.pk}:{data_version.isoformat()}:{now.date().isoformat()}"
        ),
        defaults={
            "type": Job.Type.CALCULATE_SCORE,
            "payload": {
                "company_id": str(company.pk),
                "rule_set_id": str(rule_set.pk),
                "as_of": now.isoformat(),
            },
            "priority": 10,
        },
    )
    messages.info(
        request,
        "Cálculo enviado ao worker." if created else "Esta versão dos dados já foi calculada ou está na fila.",
    )
    return redirect("company-detail", pk=company.pk)
