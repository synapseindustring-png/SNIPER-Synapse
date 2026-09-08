import re
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.db.models import Q

from apps.companies.models import Company

from .models import RuleSet, ScoreContribution, ScoreSnapshot, ScoringRule


ZERO = Decimal("0")
ONE = Decimal("1")
SCORE_QUANTUM = Decimal("0.001")
DEFAULT_DECAY_CURVE = ((30, "1.00"), (60, "0.80"), (90, "0.60"), (180, "0.30"), (None, "0.10"))
ALLOWED_FIELDS = {"company_type", "registration_status", "commercial_status", "state", "municipality_code", "size_code", "segment", "primary_cnae", "cnaes", "signal_types"}
COMPARISON_OPERATORS = {"EQ", "NE", "GT", "GTE", "LT", "LTE"}


class ScoringConfigurationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MatchedRule:
    rule: ScoringRule
    multiplier: Decimal
    effective_points: Decimal
    evidence: dict
    observed_at: object | None


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception as exc:
        raise ScoringConfigurationError(f"Valor numérico inválido: {value!r}") from exc


def _compare(actual, expected, operator: str) -> bool:
    if operator in {"GT", "GTE", "LT", "LTE"}:
        actual, expected = _decimal(actual), _decimal(expected)
    return {"EQ": lambda: actual == expected, "NE": lambda: actual != expected, "GT": lambda: actual > expected, "GTE": lambda: actual >= expected, "LT": lambda: actual < expected, "LTE": lambda: actual <= expected}[operator]()


def condition_matches(condition: dict, facts: dict, *, depth: int = 0) -> bool:
    if depth > 5 or not isinstance(condition, dict) or not condition:
        raise ScoringConfigurationError("Condição vazia, inválida ou profunda demais.")
    compound = [key for key in ("all", "any", "not") if key in condition]
    if compound:
        if len(compound) != 1 or len(condition) != 1:
            raise ScoringConfigurationError("Condição composta deve possuir uma única operação.")
        key = compound[0]
        children = condition[key]
        if key == "not":
            return not condition_matches(children, facts, depth=depth + 1)
        if not isinstance(children, list) or not children:
            raise ScoringConfigurationError(f"Operador {key} requer uma lista não vazia.")
        matches = [condition_matches(child, facts, depth=depth + 1) for child in children]
        return all(matches) if key == "all" else any(matches)

    field, operator, expected = condition.get("field"), condition.get("op"), condition.get("value")
    if field not in ALLOWED_FIELDS:
        raise ScoringConfigurationError(f"Campo não permitido: {field!r}")
    actual = facts.get(field)
    if operator in COMPARISON_OPERATORS:
        return _compare(actual, expected, operator)
    if operator == "IN":
        return actual in expected
    if operator == "NOT_IN":
        return actual not in expected
    if operator == "BETWEEN":
        if not isinstance(expected, list) or len(expected) != 2:
            raise ScoringConfigurationError("BETWEEN requer dois limites.")
        return _decimal(expected[0]) <= _decimal(actual) <= _decimal(expected[1])
    if operator == "EXISTS":
        return actual not in (None, "", [], {})
    if operator == "NOT_EXISTS":
        return actual in (None, "", [], {})
    if operator in {"CONTAINS_KEYWORD", "CONTAINS_ANY", "CONTAINS_ALL"}:
        haystack = str(actual or "").casefold()
        needles = expected if isinstance(expected, list) else [expected]
        matches = [str(item).casefold() in haystack for item in needles]
        return all(matches) if operator == "CONTAINS_ALL" else any(matches)
    if operator == "REGEX":
        pattern = str(expected)
        if len(pattern) > 200 or len(str(actual or "")) > 5000:
            raise ScoringConfigurationError("Expressão regular excede o limite seguro.")
        return re.search(pattern, str(actual or ""), flags=re.IGNORECASE) is not None
    if operator == "HAS_CNAE_PREFIX":
        prefixes = expected if isinstance(expected, list) else [expected]
        return any(str(code).startswith(tuple(str(item) for item in prefixes)) for code in facts["cnaes"])
    if operator == "HAS_SIGNAL":
        expected_types = expected if isinstance(expected, list) else [expected]
        return any(item in facts["signal_types"] for item in expected_types)
    raise ScoringConfigurationError(f"Operador não permitido: {operator!r}")


def _signal_types(condition) -> set[str]:
    if not isinstance(condition, dict):
        return set()
    if condition.get("op") == "HAS_SIGNAL":
        value = condition.get("value", [])
        return set(value if isinstance(value, list) else [value])
    found = set()
    for key in ("all", "any"):
        for child in condition.get(key, []):
            found.update(_signal_types(child))
    if "not" in condition:
        found.update(_signal_types(condition["not"]))
    return found


def decay_multiplier(rule: ScoringRule, observed_at, as_of) -> Decimal:
    if rule.decay_policy == ScoringRule.DecayPolicy.NONE or observed_at is None:
        return ONE
    age_days = max(0, (as_of.date() - observed_at.date()).days)
    curve = rule.decay_curve or [{"max_days": limit, "multiplier": value} for limit, value in DEFAULT_DECAY_CURVE]
    for bucket in curve:
        maximum = bucket.get("max_days")
        if maximum is None or age_days <= int(maximum):
            return _decimal(bucket["multiplier"])
    return ZERO


def _classification(rule_set: RuleSet, priority: Decimal) -> str:
    thresholds = sorted(rule_set.thresholds, key=lambda item: _decimal(item["min"]), reverse=True)
    for threshold in thresholds:
        if priority >= _decimal(threshold["min"]):
            return threshold["classification"]
    raise ScoringConfigurationError("O conjunto de regras não cobre a pontuação calculada.")


def _clamp(value: Decimal) -> Decimal:
    return min(Decimal("100"), max(ZERO, value)).quantize(SCORE_QUANTUM)


@transaction.atomic
def calculate_score(company: Company, *, as_of, rule_set: RuleSet | None = None) -> ScoreSnapshot:
    target = RuleSet.Target.INDUSTRY if company.company_type == Company.Type.INDUSTRY else RuleSet.Target.PARTNER
    if rule_set is None:
        rule_set = RuleSet.objects.get(target=target, active=True, status=RuleSet.Status.PUBLISHED)
    if rule_set.target != target or rule_set.status != RuleSet.Status.PUBLISHED:
        raise ScoringConfigurationError("Conjunto de regras incompatível ou não publicado.")

    cnaes = list(company.cnaes.order_by("-is_primary", "code").values_list("code", flat=True))
    signals = list(company.signals.filter(active=True, observed_at__lte=as_of).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=as_of)).order_by("-observed_at"))
    facts = {field: getattr(company, field, None) for field in ALLOWED_FIELDS - {"primary_cnae", "cnaes", "signal_types"}}
    facts.update({"cnaes": cnaes, "primary_cnae": cnaes[0] if cnaes else "", "signal_types": {signal.signal_type for signal in signals}})

    matches, group_totals = [], {}
    critical_outcome = ""
    for rule in rule_set.rules.filter(active=True):
        if not condition_matches(rule.condition, facts):
            continue
        relevant_types = _signal_types(rule.condition)
        evidence_signal = next((signal for signal in signals if signal.signal_type in relevant_types), None)
        observed_at = evidence_signal.observed_at if evidence_signal else None
        multiplier = decay_multiplier(rule, observed_at, as_of)
        effective = (rule.points * multiplier).quantize(SCORE_QUANTUM)
        if rule.group_key and rule.group_cap is not None and effective > 0:
            used = group_totals.get(rule.group_key, ZERO)
            effective = max(ZERO, min(effective, rule.group_cap - used))
            group_totals[rule.group_key] = used + effective
        evidence = {"rule": rule.name, "condition": rule.condition}
        if evidence_signal:
            evidence.update({"signal_id": str(evidence_signal.pk), "signal_type": evidence_signal.signal_type, "title": evidence_signal.title, "source_url": evidence_signal.source_url, "excerpt": evidence_signal.evidence_excerpt})
        matches.append(MatchedRule(rule, multiplier, effective, evidence, observed_at))
        critical_outcome = rule.critical_outcome or critical_outcome

    dimensions = {dimension: ZERO for dimension, _ in ScoringRule.Dimension.choices}
    for match in matches:
        dimensions[match.rule.dimension] += match.effective_points
    dimensions = {key: _clamp(value) for key, value in dimensions.items()}

    best_product, tied_products, best_value = "", [], ZERO
    if target == RuleSet.Target.INDUSTRY:
        products = {key: dimensions[key] for key in ("MES", "CMMS", "PULSE")}
        best_value = max(products.values())
        tied_products = [key for key in rule_set.tie_order if products.get(key) == best_value]
        if not tied_products:
            tied_products = [key for key, value in products.items() if value == best_value]
        best_product = tied_products[0]

    formula_detail, priority = {}, ZERO
    for dimension, coefficient_value in rule_set.formula.items():
        value = best_value if dimension == "BEST_PRODUCT" else dimensions.get(dimension, ZERO)
        coefficient = _decimal(coefficient_value)
        weighted = (value * coefficient).quantize(SCORE_QUANTUM)
        priority += weighted
        formula_detail[dimension] = {"score": str(value), "coefficient": str(coefficient), "weighted": str(weighted)}
    priority = _clamp(priority)
    snapshot = ScoreSnapshot.objects.create(
        company=company,
        rule_set=rule_set,
        as_of=as_of,
        dimensions={key: str(value) for key, value in dimensions.items()},
        priority=priority,
        calculated_classification=critical_outcome or _classification(rule_set, priority),
        best_product=best_product,
        tied_products=tied_products,
        formula_detail=formula_detail,
    )
    ScoreContribution.objects.bulk_create([ScoreContribution(snapshot=snapshot, rule=match.rule, dimension=match.rule.dimension, base_points=match.rule.points, decay_multiplier=match.multiplier, effective_points=match.effective_points, evidence=match.evidence, observed_at=match.observed_at) for match in matches])
    return snapshot
