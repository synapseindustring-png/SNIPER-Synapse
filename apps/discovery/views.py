from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import CharField, DecimalField, Exists, F, OuterRef, Prefetch, Q, Subquery
from django.db.models.functions import Coalesce
from django.core.paginator import Paginator
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils import timezone

from apps.jobs.models import Job
from apps.companies.models import Company, CompanyCnae
from apps.scoring.models import ScoreOverride, ScoreSnapshot
from apps.signals.models import Signal

from .coverage import materialize_cached_run
from .forms import DiscoveryQueryForm, FullRunForm, OpportunitySearchForm, PreviewRunForm
from .models import DiscoveryQuery, GeographicRegion, Initiative, MarketSegment, OpportunitySearch, QueryRun
from .planning import build_full_plan, build_preview_plan


PARTNER_TYPES = (
    Company.Type.CONSULTANCY,
    Company.Type.INTEGRATOR,
    Company.Type.ENGINEERING,
    Company.Type.SERVICE_PROVIDER,
)


@login_required
def opportunity_create(request):
    form = OpportunitySearchForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            search = form.save(request.user)
        return redirect("opportunity-results", pk=search.pk)
    recent_searches = OpportunitySearch.objects.filter(created_by=request.user)[:5]
    return render(
        request,
        "discovery/opportunity_form.html",
        {"form": form, "recent_searches": recent_searches},
    )


@login_required
def opportunity_options(request):
    state = request.GET.get("state", "MG").upper()
    target = request.GET.get("target", DiscoveryQuery.EntityTarget.INDUSTRY)
    regions = GeographicRegion.objects.filter(state=state, active=True)
    if regions.filter(kind=GeographicRegion.Kind.COMMERCIAL).exists():
        regions = regions.filter(kind=GeographicRegion.Kind.COMMERCIAL)
    return JsonResponse(
        {
            "regions": [{"value": item.pk, "label": item.name} for item in regions],
            "segments": [
                {"value": item.pk, "label": item.name, "description": item.description}
                for item in MarketSegment.objects.filter(target=target, active=True)
            ],
            "initiatives": [
                {"value": item.pk, "label": item.name, "description": item.description}
                for item in Initiative.objects.filter(target=target, active=True)
            ],
        }
    )


def _opportunity_companies(search):
    latest_score = ScoreSnapshot.objects.filter(company=OuterRef("pk")).order_by(
        "-as_of", "-created_at"
    )
    active_override = ScoreOverride.objects.filter(company=OuterRef("pk"), active=True)
    company_types = (
        (Company.Type.INDUSTRY,)
        if search.target == DiscoveryQuery.EntityTarget.INDUSTRY
        else PARTNER_TYPES
    )
    companies = Company.objects.filter(
        company_type__in=company_types,
        state=search.state,
        registration_status=Company.RegistrationStatus.ACTIVE,
        deleted_at__isnull=True,
    )
    filters = search.technical_filters
    if filters.get("municipality_codes"):
        companies = companies.filter(municipality_code__in=filters["municipality_codes"])
    cnae_filter = Q()
    for prefix in filters.get("cnae_prefixes", []):
        cnae_filter |= Q(cnaes__code__startswith=prefix)
    if cnae_filter:
        companies = companies.filter(cnae_filter)
    now = timezone.now()
    relevant_signals = Signal.objects.filter(active=True).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    )
    if search.initiative.signal_types:
        relevant_signals = relevant_signals.filter(
            signal_type__in=search.initiative.signal_types
        )
    return (
        companies.annotate(
            latest_priority=Subquery(latest_score.values("priority")[:1]),
            latest_classification=Subquery(latest_score.values("calculated_classification")[:1]),
            latest_best_product=Subquery(latest_score.values("best_product")[:1]),
            override_priority=Subquery(active_override.values("priority")[:1]),
            override_classification=Subquery(
                active_override.exclude(classification="").values("classification")[:1]
            ),
            has_override=Exists(active_override),
        )
        .annotate(
            effective_priority=Coalesce(
                "override_priority", "latest_priority", output_field=DecimalField()
            ),
            effective_classification=Coalesce(
                "override_classification", "latest_classification", output_field=CharField()
            ),
        )
        .prefetch_related(
            Prefetch(
                "cnaes", queryset=CompanyCnae.objects.filter(is_primary=True), to_attr="primary_cnaes"
            ),
            Prefetch("signals", queryset=relevant_signals.order_by("-observed_at"), to_attr="opportunity_signals"),
        )
        .distinct()
        .order_by(F("effective_priority").desc(nulls_last=True), "trade_name", "legal_name")
    )


@login_required
def opportunity_results(request, pk):
    search = get_object_or_404(
        OpportunitySearch.objects.select_related("initiative").prefetch_related("regions", "segments"),
        pk=pk,
        created_by=request.user,
    )
    paginator = Paginator(_opportunity_companies(search), 24)
    page = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "discovery/opportunity_results.html",
        {"search": search, "page": page},
    )


@login_required
def query_list(request):
    queries = DiscoveryQuery.objects.filter(created_by=request.user).prefetch_related("runs")
    manifest_job = (
        Job.objects.filter(type=Job.Type.SYNC_CNPJ_SOURCE).order_by("-created_at").first()
    )
    return render(
        request,
        "discovery/query_list.html",
        {"queries": queries, "manifest_job": manifest_job},
    )


@login_required
@require_POST
def manifest_sync(request):
    if not request.user.is_staff:
        raise Http404
    key = f"sync-cnpj-manifest:{timezone.localdate().isoformat()}"
    job, created = Job.objects.get_or_create(
        idempotency_key=key,
        defaults={"type": Job.Type.SYNC_CNPJ_SOURCE, "priority": 10},
    )
    if created:
        messages.success(request, "Atualização do manifesto adicionada à fila.")
    else:
        messages.info(request, f"A atualização de hoje já existe: {job.get_status_display()}.")
    return redirect("query-list")


@login_required
def query_create(request):
    form = DiscoveryQueryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                query = form.save(request.user)
        except IntegrityError:
            form.add_error(None, "Uma consulta equivalente já existe.")
        else:
            messages.success(request, "Consulta criada. Revise a estimativa antes de executar.")
            return redirect("query-detail", pk=query.pk)
    return render(request, "discovery/query_form.html", {"form": form})


def _user_query(request, pk):
    return get_object_or_404(DiscoveryQuery, pk=pk, created_by=request.user)


@login_required
def query_detail(request, pk):
    query = _user_query(request, pk)
    return render(
        request,
        "discovery/query_detail.html",
        {
            "query": query,
            "plan": build_preview_plan(query),
            "preview_form": PreviewRunForm(),
            "full_plan": build_full_plan(query) if request.user.is_staff else None,
            "full_form": FullRunForm() if request.user.is_staff else None,
            "runs": query.runs.all()[:20],
        },
    )


@login_required
@require_POST
def query_run_preview(request, pk):
    query = _user_query(request, pk)
    form = PreviewRunForm(request.POST)
    plan = build_preview_plan(query)
    if not form.is_valid() or not plan.allowed or not plan.dataset:
        reason = plan.reason if not plan.allowed else "O limite informado é inválido."
        messages.error(request, f"A prévia não foi iniciada: {reason}")
        return redirect("query-detail", pk=query.pk)

    max_results = form.cleaned_data["max_results"]
    if plan.coverage:
        existing_run = query.runs.filter(
            dataset_reference=plan.dataset.reference,
            coverage__mode="CACHE",
            coverage__source_coverage_id=plan.coverage.pk,
            coverage__max_results=max_results,
        ).first()
        if existing_run:
            messages.info(request, "Esta consulta já foi atendida pelo cache local.")
            return redirect("query-run-detail", pk=existing_run.pk)
        run = materialize_cached_run(
            query=query,
            created_by=request.user,
            coverage=plan.coverage,
            max_results=max_results,
        )
        messages.success(request, "Resultados reutilizados do cache local, sem download.")
        return redirect("query-run-detail", pk=run.pk)

    if not plan.source_file:
        messages.error(request, "A prévia não foi iniciada: arquivo de origem indisponível.")
        return redirect("query-detail", pk=query.pk)
    idempotency_key = (
        f"cnpj-preview:{query.pk}:{plan.dataset.pk}:{plan.source_file.pk}:{max_results}"
    )
    existing_job = Job.objects.filter(idempotency_key=idempotency_key).first()
    if existing_job:
        run_id = existing_job.payload.get("query_run_id")
        if run_id:
            messages.info(
                request,
                "Esta prévia já foi solicitada; exibindo a execução existente.",
            )
            return redirect("query-run-detail", pk=run_id)
        raise Http404

    with transaction.atomic():
        query_run = QueryRun.objects.create(
            query=query,
            created_by=request.user,
            dataset_reference=plan.dataset.reference,
        )
        Job.objects.create(
            type=Job.Type.DISCOVER_CNPJ,
            idempotency_key=idempotency_key,
            payload={
                "query_run_id": str(query_run.pk),
                "dataset_reference": plan.dataset.reference,
                "source_url": plan.source_file.url,
                "mode": "PREVIEW",
                "max_results": max_results,
                "filters": query.normalized_filters,
            },
        )
    messages.success(request, "Prévia adicionada à fila.")
    return redirect("query-run-detail", pk=query_run.pk)


@login_required
@require_POST
def query_run_full(request, pk):
    if not request.user.is_staff:
        raise Http404
    query = _user_query(request, pk)
    form = FullRunForm(request.POST)
    plan = build_full_plan(query)
    if not form.is_valid() or not plan.allowed or not plan.dataset or not plan.simples_file:
        reason = plan.reason if not plan.allowed else "Revise o limite e a confirmação."
        messages.error(request, f"A execução completa não foi iniciada: {reason}")
        return redirect("query-detail", pk=query.pk)

    max_results = form.cleaned_data["max_results"]
    idempotency_key = f"cnpj-full:{query.pk}:{plan.dataset.pk}:{max_results}"
    existing_job = Job.objects.filter(idempotency_key=idempotency_key).first()
    if existing_job:
        run_id = existing_job.payload.get("query_run_id")
        if run_id:
            messages.info(request, "Esta execução completa já foi solicitada.")
            return redirect("query-run-detail", pk=run_id)
        raise Http404

    with transaction.atomic():
        query_run = QueryRun.objects.create(
            query=query,
            created_by=request.user,
            dataset_reference=plan.dataset.reference,
        )
        Job.objects.create(
            type=Job.Type.DISCOVER_CNPJ,
            priority=5,
            idempotency_key=idempotency_key,
            payload={
                "query_run_id": str(query_run.pk),
                "dataset_reference": plan.dataset.reference,
                "source_urls": [source_file.url for source_file in plan.establishment_files],
                "company_source_urls": [source_file.url for source_file in plan.company_files],
                "simples_source_urls": [plan.simples_file.url],
                "mode": "FULL",
                "max_results": max_results,
                "filters": query.normalized_filters,
                "coverage_complete": True,
                "expected_establishment_parts": 10,
            },
        )
    messages.success(
        request,
        "Execução completa adicionada à fila; os arquivos serão processados um por vez.",
    )
    return redirect("query-run-detail", pk=query_run.pk)


@login_required
def query_run_detail(request, pk):
    run = get_object_or_404(
        QueryRun.objects.select_related("query"),
        pk=pk,
        created_by=request.user,
    )
    return render(
        request,
        "discovery/query_run_detail.html",
        {"run": run, "results": run.results.select_related("company", "source")[:500]},
    )
