import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.companies.models import Company
from apps.jobs.models import Job

from .engine import (
    ALLOWED_FIELDS,
    COMPARISON_OPERATORS,
    ScoringConfigurationError,
    calculate_score,
)
from .models import RuleSet, ScoringRule


ALLOWED_OPERATORS = COMPARISON_OPERATORS | {
    "IN",
    "NOT_IN",
    "BETWEEN",
    "EXISTS",
    "NOT_EXISTS",
    "CONTAINS_KEYWORD",
    "CONTAINS_ANY",
    "CONTAINS_ALL",
    "REGEX",
    "HAS_CNAE_PREFIX",
    "HAS_SIGNAL",
}


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
        company.signals.order_by("-updated_at")
        .values_list("updated_at", flat=True)
        .first()
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


def _validate_condition(condition, *, depth=0):
    if depth > 5 or not isinstance(condition, dict) or not condition:
        raise ScoringConfigurationError("Condição vazia, inválida ou profunda demais.")
    compound = [key for key in ("all", "any", "not") if key in condition]
    if compound:
        if len(compound) != 1 or len(condition) != 1:
            raise ScoringConfigurationError("Condição composta deve ter uma operação.")
        operator = compound[0]
        children = condition[operator]
        if operator == "not":
            return _validate_condition(children, depth=depth + 1)
        if not isinstance(children, list) or not children:
            raise ScoringConfigurationError(f"Operador {operator} requer uma lista.")
        for child in children:
            _validate_condition(child, depth=depth + 1)
        return
    if set(condition) != {"field", "op", "value"}:
        raise ScoringConfigurationError("Condição simples requer field, op e value.")
    if condition["field"] not in ALLOWED_FIELDS:
        raise ScoringConfigurationError(f"Campo não permitido: {condition['field']!r}")
    if condition["op"] not in ALLOWED_OPERATORS:
        raise ScoringConfigurationError(f"Operador não permitido: {condition['op']!r}")
    if condition["op"] == "BETWEEN" and (
        not isinstance(condition["value"], list) or len(condition["value"]) != 2
    ):
        raise ScoringConfigurationError("BETWEEN requer exatamente dois limites.")
    if condition["op"] in {"IN", "NOT_IN"} and not isinstance(
        condition["value"], list
    ):
        raise ScoringConfigurationError(f"{condition['op']} requer uma lista.")
    if condition["op"] == "REGEX":
        pattern = str(condition["value"])
        if len(pattern) > 200:
            raise ScoringConfigurationError("Expressão regular excede o limite seguro.")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ScoringConfigurationError("Expressão regular inválida.") from exc


def validate_rule_set(rule_set: RuleSet) -> list[str]:
    errors = []
    rule_dimensions = (
        {"ICP", "MES", "CMMS", "PULSE", "INTENT"}
        if rule_set.target == RuleSet.Target.INDUSTRY
        else {"PARTNER_FIT", "CHANNEL", "ACTIVITY", "CONFLICT"}
    )
    expected_formula_dimensions = (
        {"ICP", "BEST_PRODUCT", "INTENT"}
        if rule_set.target == RuleSet.Target.INDUSTRY
        else {"PARTNER_FIT", "CHANNEL", "ACTIVITY", "CONFLICT"}
    )
    try:
        coefficients = {key: Decimal(str(value)) for key, value in rule_set.formula.items()}
        if set(coefficients) != expected_formula_dimensions:
            errors.append("A fórmula deve conter todas e somente as dimensões do público.")
        positive_sum = sum(value for value in coefficients.values() if value > 0)
        if positive_sum != Decimal("1"):
            errors.append("Os coeficientes positivos da fórmula devem somar 1.")
    except (AttributeError, InvalidOperation, TypeError):
        errors.append("A fórmula deve ser um objeto JSON com coeficientes numéricos.")

    try:
        thresholds = [(Decimal(str(item["min"])), item["classification"]) for item in rule_set.thresholds]
        minimums = [item[0] for item in thresholds]
        classifications = [item[1] for item in thresholds]
        if not thresholds or min(minimums) != 0 or len(minimums) != len(set(minimums)):
            errors.append("Thresholds devem ser únicos e cobrir a pontuação zero.")
        if len(classifications) != len(set(classifications)):
            errors.append("Cada threshold deve produzir uma classificação diferente.")
        if any(value < 0 or value > 100 or not classification for value, classification in thresholds):
            errors.append("Thresholds exigem mínimo entre 0 e 100 e classificação.")
    except (KeyError, InvalidOperation, TypeError, ValueError):
        errors.append("Thresholds possuem formato inválido.")

    if rule_set.target == RuleSet.Target.INDUSTRY and set(rule_set.tie_order) != {
        "MES",
        "CMMS",
        "PULSE",
    }:
        errors.append("O desempate de indústrias deve ordenar MES, CMMS e PULSE.")

    for rule in rule_set.rules.all():
        try:
            _validate_condition(rule.condition)
        except ScoringConfigurationError as exc:
            errors.append(f"Regra {rule.key}: {exc}")
        if rule.dimension not in rule_dimensions:
            errors.append(f"Regra {rule.key}: dimensão incompatível com o público.")
        if rule.decay_policy == ScoringRule.DecayPolicy.AGE_BUCKETS:
            try:
                maximums = [item["max_days"] for item in rule.decay_curve]
                multipliers = [Decimal(str(item["multiplier"])) for item in rule.decay_curve]
                finite_maximums = [int(value) for value in maximums if value is not None]
                if (
                    not maximums
                    or maximums[-1] is not None
                    or any(value is None for value in maximums[:-1])
                    or finite_maximums != sorted(finite_maximums)
                    or len(finite_maximums) != len(set(finite_maximums))
                    or any(value < 0 for value in finite_maximums)
                    or any(value < 0 or value > 1 for value in multipliers)
                ):
                    raise ValueError
            except (KeyError, InvalidOperation, TypeError, ValueError):
                errors.append(f"Regra {rule.key}: curva de decay inválida.")
    return errors


def compare_rule_sets(rule_set: RuleSet, baseline: RuleSet | None) -> dict:
    if baseline is None:
        return {"added": [], "removed": [], "changed": [], "configuration_changed": False}
    current_rules = {rule.key: rule for rule in rule_set.rules.all()}
    baseline_rules = {rule.key: rule for rule in baseline.rules.all()}
    fields = (
        "name",
        "description",
        "dimension",
        "condition",
        "points",
        "decay_policy",
        "decay_curve",
        "critical_outcome",
        "group_key",
        "group_cap",
        "max_occurrences",
        "active",
        "order",
    )
    shared = set(current_rules).intersection(baseline_rules)
    return {
        "added": sorted(set(current_rules).difference(baseline_rules)),
        "removed": sorted(set(baseline_rules).difference(current_rules)),
        "changed": sorted(
            key
            for key in shared
            if any(
                getattr(current_rules[key], field) != getattr(baseline_rules[key], field)
                for field in fields
            )
        ),
        "configuration_changed": any(
            getattr(rule_set, field) != getattr(baseline, field)
            for field in ("name", "description", "formula", "thresholds", "tie_order")
        ),
    }


@transaction.atomic
def clone_active_rule_set(*, target: str, user) -> tuple[RuleSet, bool]:
    if not user.is_staff:
        raise PermissionError("Somente staff pode versionar regras.")
    sets = RuleSet.objects.select_for_update().filter(target=target)
    draft = sets.filter(status=RuleSet.Status.DRAFT).first()
    if draft:
        return draft, False
    active = sets.get(active=True, status=RuleSet.Status.PUBLISHED)
    version = (sets.aggregate(value=Max("version"))["value"] or 0) + 1
    draft = RuleSet.objects.create(
        name=active.name,
        target=active.target,
        version=version,
        formula=active.formula,
        thresholds=active.thresholds,
        tie_order=active.tie_order,
        description=active.description,
        created_by=user,
    )
    ScoringRule.objects.bulk_create(
        [
            ScoringRule(
                rule_set=draft,
                key=rule.key,
                name=rule.name,
                description=rule.description,
                dimension=rule.dimension,
                condition=rule.condition,
                points=rule.points,
                decay_policy=rule.decay_policy,
                decay_curve=rule.decay_curve,
                critical_outcome=rule.critical_outcome,
                group_key=rule.group_key,
                group_cap=rule.group_cap,
                max_occurrences=rule.max_occurrences,
                active=rule.active,
                order=rule.order,
            )
            for rule in active.rules.all()
        ]
    )
    return draft, True


@transaction.atomic
def publish_rule_set(rule_set: RuleSet, *, user) -> RuleSet:
    if not user.is_staff:
        raise PermissionError("Somente staff pode publicar regras.")
    draft = RuleSet.objects.select_for_update().get(pk=rule_set.pk)
    if draft.status != RuleSet.Status.DRAFT:
        raise ValueError("Somente um rascunho pode ser publicado.")
    errors = validate_rule_set(draft)
    if errors:
        raise ScoringConfigurationError("\n".join(errors))
    RuleSet.objects.filter(target=draft.target, active=True).update(
        active=False, status=RuleSet.Status.RETIRED
    )
    draft.status = RuleSet.Status.PUBLISHED
    draft.active = True
    draft.published_at = timezone.now()
    draft.save(update_fields=("status", "active", "published_at"))
    return draft


@dataclass(frozen=True)
class ScoreSimulation:
    priority: Decimal
    classification: str
    best_product: str
    dimensions: dict
    contributions: tuple


def simulate_rule_set(rule_set: RuleSet, company: Company) -> ScoreSimulation:
    errors = validate_rule_set(rule_set)
    if errors:
        raise ScoringConfigurationError("\n".join(errors))
    with transaction.atomic():
        snapshot = calculate_score(
            company,
            as_of=timezone.now(),
            rule_set=rule_set,
            allow_draft=True,
        )
        result = ScoreSimulation(
            priority=snapshot.priority,
            classification=snapshot.calculated_classification,
            best_product=snapshot.best_product,
            dimensions=snapshot.dimensions,
            contributions=tuple(snapshot.contributions.select_related("rule")),
        )
        transaction.set_rollback(True)
    return result
