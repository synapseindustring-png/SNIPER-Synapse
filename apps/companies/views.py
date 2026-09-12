import csv

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import CharField, DecimalField, Exists, F, OuterRef, Prefetch, Q, Subquery
from django.db.models.functions import Coalesce
from django.http import Http404, HttpResponseBadRequest, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.jobs.models import Job
from apps.crawler.services import WebsiteFetchError, enqueue_website_crawl
from apps.scoring.models import ScoreContribution, ScoreOverride, ScoreSnapshot
from apps.scoring.services import enqueue_company_score
from apps.signals.services import enqueue_signal_detection
from apps.sources.models import FieldObservation, SourceRecord

from .corrections import CORRECTABLE_FIELDS, correct_company
from .forms import CompanyCorrectionForm, CompanyFilterForm
from .models import Company, CompanyCnae, CompanyCorrection


def _company_ranking(parameters):
    latest_score = ScoreSnapshot.objects.filter(company=OuterRef("pk")).order_by(
        "-as_of", "-created_at"
    )
    active_override = ScoreOverride.objects.filter(company=OuterRef("pk"), active=True)
    companies = Company.objects.filter(
        company_type=Company.Type.INDUSTRY,
        deleted_at__isnull=True,
    ).annotate(
        latest_priority=Subquery(latest_score.values("priority")[:1]),
        latest_classification=Subquery(
            latest_score.values("calculated_classification")[:1]
        ),
        latest_best_product=Subquery(latest_score.values("best_product")[:1]),
        latest_score_at=Subquery(latest_score.values("as_of")[:1]),
        override_priority=Subquery(active_override.values("priority")[:1]),
        override_classification=Subquery(
            active_override.exclude(classification="").values("classification")[:1]
        ),
        has_override=Exists(active_override),
    ).annotate(
        effective_priority=Coalesce(
            "override_priority", "latest_priority", output_field=DecimalField()
        ),
        effective_classification=Coalesce(
            "override_classification", "latest_classification", output_field=CharField()
        ),
    ).prefetch_related(
        Prefetch("cnaes", queryset=CompanyCnae.objects.filter(is_primary=True), to_attr="primary_cnaes")
    )
    form = CompanyFilterForm(parameters)
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
        if filters["classification"]:
            companies = companies.filter(
                effective_classification=filters["classification"]
            )
        if filters["best_product"]:
            companies = companies.filter(latest_best_product=filters["best_product"])
        if filters["minimum_priority"] is not None:
            companies = companies.filter(effective_priority__gte=filters["minimum_priority"])
        if filters["scored_since"]:
            companies = companies.filter(latest_score_at__date__gte=filters["scored_since"])
        if filters["signal_type"]:
            now = timezone.now()
            companies = companies.filter(
                Q(signals__signal_type=filters["signal_type"])
                & Q(signals__active=True)
                & (Q(signals__expires_at__isnull=True) | Q(signals__expires_at__gt=now))
            ).distinct()

        ordering = {
            "priority_asc": (F("effective_priority").asc(nulls_last=True), "trade_name", "legal_name"),
            "score_recent": (F("latest_score_at").desc(nulls_last=True), F("effective_priority").desc(nulls_last=True)),
            "company_name": ("trade_name", "legal_name", "cnpj"),
        }.get(
            filters["ordering"],
            (F("effective_priority").desc(nulls_last=True), F("latest_score_at").desc(nulls_last=True), "trade_name", "legal_name"),
        )
        companies = companies.order_by(*ordering)
    else:
        companies = companies.order_by(
            F("effective_priority").desc(nulls_last=True), "trade_name", "legal_name"
        )

    return companies, form


@login_required
def company_list(request):
    companies, form = _company_ranking(request.GET)
    paginator = Paginator(companies, 50)
    page = paginator.get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)
    return render(
        request,
        "companies/company_list.html",
        {"form": form, "page": page, "querystring": query_params.urlencode()},
    )


class _CsvEcho:
    def write(self, value):
        return value


def _csv_safe(value):
    value = "" if value is None else str(value)
    return f"'{value}" if value.lstrip().startswith(("=", "+", "-", "@")) else value


@login_required
def company_export(request):
    parameters = request.GET.copy()
    parameters.pop("page", None)
    companies, form = _company_ranking(parameters)
    if not form.is_valid():
        return HttpResponseBadRequest("Filtros inválidos para exportação.")
    writer = csv.writer(_CsvEcho())

    def rows():
        yield "\ufeff" + writer.writerow(
            (
                "posição",
                "cnpj",
                "empresa",
                "município",
                "uf",
                "prioridade",
                "classificação",
                "produto",
                "score_em",
                "etapa_comercial",
            )
        )
        for position, company in enumerate(companies[:500].iterator(chunk_size=100), 1):
            yield writer.writerow(
                (
                    position,
                    _csv_safe(company.cnpj),
                    _csv_safe(str(company)),
                    _csv_safe(company.municipality),
                    _csv_safe(company.state),
                    company.effective_priority if company.effective_priority is not None else "",
                    _csv_safe(company.effective_classification),
                    _csv_safe(company.latest_best_product),
                    company.latest_score_at.isoformat() if company.latest_score_at else "",
                    company.commercial_status,
                )
            )

    response = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="ranking-industrias.csv"'
    response["X-Export-Limit"] = "500"
    return response


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
            Prefetch(
                "corrections",
                queryset=CompanyCorrection.objects.select_related(
                    "corrected_by", "source_record"
                )[:100],
                to_attr="recent_corrections",
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
    pending_signal_job = Job.objects.filter(
        type=Job.Type.DETECT_SIGNALS,
        status__in=(Job.Status.PENDING, Job.Status.RUNNING, Job.Status.RETRY_SCHEDULED),
        payload__company_id=str(company.pk),
    ).exists()
    signals = company.signals.filter(active=True).select_related("source_record__source")[:100]
    pending_crawl_job = Job.objects.filter(
        type=Job.Type.CRAWL_WEBSITE,
        status__in=(Job.Status.PENDING, Job.Status.RUNNING, Job.Status.RETRY_SCHEDULED),
        payload__company_id=str(company.pk),
    ).exists()
    website_pages = company.website_pages.filter(current=True)[:20]
    job_postings = company.job_postings.filter(active=True).select_related("source_record")[:100]
    return render(
        request,
        "companies/company_detail.html",
        {
            "company": company,
            "snapshot": snapshot,
            "score_override": override,
            "pending_score_job": pending_score_job,
            "pending_signal_job": pending_signal_job,
            "signals": signals,
            "pending_crawl_job": pending_crawl_job,
            "website_pages": website_pages,
            "job_postings": job_postings,
        },
    )


@login_required
def company_correction(request, pk):
    if not request.user.is_staff:
        raise Http404
    company = get_object_or_404(Company, pk=pk, deleted_at__isnull=True)
    form = CompanyCorrectionForm(request.POST or None, instance=company)
    if request.method == "POST" and form.is_valid():
        changes = {
            field_name: form.cleaned_data[field_name]
            for field_name in CORRECTABLE_FIELDS
            if field_name in form.changed_data
        }
        company, corrections = correct_company(
            company=company,
            changes=changes,
            justification=form.cleaned_data["justification"],
            user=request.user,
        )
        enqueue_company_score(company)
        messages.success(
            request,
            f"{len(corrections)} campo(s) corrigido(s) com trilha de auditoria.",
        )
        return redirect("company-detail", pk=company.pk)
    return render(
        request,
        "companies/company_correction_form.html",
        {"company": company, "form": form},
    )


@login_required
@require_POST
def company_score(request, pk):
    company = get_object_or_404(Company, pk=pk, deleted_at__isnull=True)
    _, created = enqueue_company_score(company)
    messages.info(
        request,
        "Cálculo enviado ao worker." if created else "Esta versão dos dados já foi calculada ou está na fila.",
    )
    return redirect("company-detail", pk=company.pk)


@login_required
@require_POST
def company_detect_signals(request, pk):
    company = get_object_or_404(Company, pk=pk, deleted_at__isnull=True)
    if not company.source_records.exists():
        messages.error(request, "A empresa ainda não possui evidências locais para analisar.")
        return redirect("company-detail", pk=company.pk)
    _, created = enqueue_signal_detection(company)
    messages.info(
        request,
        "Detecção enviada ao worker." if created else "As evidências atuais já foram analisadas ou estão na fila.",
    )
    return redirect("company-detail", pk=company.pk)


@login_required
@require_POST
def company_crawl_website(request, pk):
    company = get_object_or_404(Company, pk=pk, deleted_at__isnull=True)
    try:
        _, created = enqueue_website_crawl(company)
    except WebsiteFetchError as exc:
        messages.error(request, str(exc))
    else:
        messages.info(
            request,
            "Coleta enviada ao worker." if created else "Este website já foi coletado hoje ou está na fila.",
        )
    return redirect("company-detail", pk=company.pk)
