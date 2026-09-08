from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils import timezone

from apps.jobs.models import Job

from .forms import DiscoveryQueryForm, PreviewRunForm
from .models import DiscoveryQuery, QueryRun
from .planning import build_preview_plan


@login_required
def query_list(request):
    queries = DiscoveryQuery.objects.filter(created_by=request.user).prefetch_related("runs")
    manifest_job = Job.objects.filter(type=Job.Type.SYNC_CNPJ_SOURCE).order_by("-created_at").first()
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
            "plan": build_preview_plan(),
            "preview_form": PreviewRunForm(),
            "runs": query.runs.all()[:20],
        },
    )


@login_required
@require_POST
def query_run_preview(request, pk):
    query = _user_query(request, pk)
    form = PreviewRunForm(request.POST)
    plan = build_preview_plan()
    if not form.is_valid() or not plan.allowed or not plan.dataset or not plan.source_file:
        reason = plan.reason if not plan.allowed else "O limite informado é inválido."
        messages.error(request, f"A prévia não foi iniciada: {reason}")
        return redirect("query-detail", pk=query.pk)

    max_results = form.cleaned_data["max_results"]
    idempotency_key = (
        f"cnpj-preview:{query.pk}:{plan.dataset.pk}:{plan.source_file.pk}:{max_results}"
    )
    existing_job = Job.objects.filter(idempotency_key=idempotency_key).first()
    if existing_job:
        run_id = existing_job.payload.get("query_run_id")
        if run_id:
            messages.info(request, "Esta prévia já foi solicitada; exibindo a execução existente.")
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
