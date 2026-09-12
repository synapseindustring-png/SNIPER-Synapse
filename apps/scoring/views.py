from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .engine import ScoringConfigurationError
from .forms import RuleSetForm, ScoreSimulationForm, ScoringRuleForm
from .models import RuleSet, ScoringRule
from .services import (
    clone_active_rule_set,
    compare_rule_sets,
    publish_rule_set,
    simulate_rule_set,
    validate_rule_set,
)


def _require_staff(request):
    if not request.user.is_staff:
        raise Http404


@login_required
def rule_set_list(request):
    _require_staff(request)
    rule_sets = RuleSet.objects.prefetch_related("rules").all()
    return render(request, "scoring/rule_set_list.html", {"rule_sets": rule_sets})


@login_required
def rule_set_detail(request, pk):
    _require_staff(request)
    rule_set = get_object_or_404(RuleSet.objects.prefetch_related("rules"), pk=pk)
    editable = rule_set.status == RuleSet.Status.DRAFT
    baseline = (
        RuleSet.objects.filter(
            target=rule_set.target,
            status__in=(RuleSet.Status.PUBLISHED, RuleSet.Status.RETIRED),
            version__lt=rule_set.version,
        )
        .prefetch_related("rules")
        .order_by("-version")
        .first()
    )
    form = RuleSetForm(request.POST or None, instance=rule_set)
    if request.method == "POST":
        if not editable:
            raise Http404
        if form.is_valid():
            form.save()
            messages.success(request, "Configuração do rascunho salva.")
            return redirect("rule-set-detail", pk=rule_set.pk)
    return render(
        request,
        "scoring/rule_set_detail.html",
        {
            "rule_set": rule_set,
            "form": form,
            "editable": editable,
            "validation_errors": validate_rule_set(rule_set),
            "baseline": baseline,
            "comparison": compare_rule_sets(rule_set, baseline),
            "simulation_form": ScoreSimulationForm(rule_set=rule_set),
        },
    )


@login_required
@require_POST
def rule_set_clone(request, target):
    _require_staff(request)
    if target not in RuleSet.Target.values:
        raise Http404
    draft, created = clone_active_rule_set(target=target, user=request.user)
    messages.info(
        request,
        "Nova versão criada a partir da ativa."
        if created
        else "Já existe um rascunho para este público.",
    )
    return redirect("rule-set-detail", pk=draft.pk)


@login_required
@require_POST
def rule_set_publish(request, pk):
    _require_staff(request)
    rule_set = get_object_or_404(RuleSet, pk=pk)
    try:
        publish_rule_set(rule_set, user=request.user)
    except (ValueError, ScoringConfigurationError) as exc:
        messages.error(request, str(exc).replace("\n", " "))
    else:
        messages.success(request, f"Versão {rule_set.version} publicada e ativada.")
    return redirect("rule-set-detail", pk=rule_set.pk)


@login_required
def scoring_rule_edit(request, rule_set_pk, pk=None):
    _require_staff(request)
    rule_set = get_object_or_404(RuleSet, pk=rule_set_pk, status=RuleSet.Status.DRAFT)
    rule = get_object_or_404(ScoringRule, pk=pk, rule_set=rule_set) if pk else None
    form = ScoringRuleForm(request.POST or None, instance=rule)
    if request.method == "POST" and form.is_valid():
        rule = form.save(commit=False)
        rule.rule_set = rule_set
        rule.save()
        messages.success(request, "Regra salva no rascunho.")
        return redirect("rule-set-detail", pk=rule_set.pk)
    return render(
        request,
        "scoring/scoring_rule_form.html",
        {"rule_set": rule_set, "rule": rule, "form": form},
    )


@login_required
@require_POST
def scoring_rule_delete(request, rule_set_pk, pk):
    _require_staff(request)
    rule = get_object_or_404(
        ScoringRule,
        pk=pk,
        rule_set_id=rule_set_pk,
        rule_set__status=RuleSet.Status.DRAFT,
    )
    rule_set_pk = rule.rule_set_id
    rule.delete()
    messages.success(request, "Regra removida do rascunho.")
    return redirect("rule-set-detail", pk=rule_set_pk)


@login_required
@require_POST
def rule_set_simulate(request, pk):
    _require_staff(request)
    rule_set = get_object_or_404(RuleSet, pk=pk)
    form = ScoreSimulationForm(request.POST, rule_set=rule_set)
    simulation = None
    if form.is_valid():
        try:
            simulation = simulate_rule_set(rule_set, form.cleaned_data["company"])
        except ScoringConfigurationError as exc:
            messages.error(request, str(exc).replace("\n", " "))
    return render(
        request,
        "scoring/rule_set_simulation.html",
        {"rule_set": rule_set, "form": form, "simulation": simulation},
    )
