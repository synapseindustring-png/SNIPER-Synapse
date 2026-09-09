import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.db.models import Prefetch

from apps.companies.models import Company
from apps.crawler.models import JobPosting

from .models import Signal, SignalDetection, SignalRule


@dataclass(frozen=True, slots=True)
class DetectionStats:
    records_scanned: int
    rules_evaluated: int
    signals_matched: int
    signals_created: int
    signals_deactivated: int


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(character for character in value if not unicodedata.combining(character))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def _payload_value(record, path: str):
    if path in {"job_title", "job_description"}:
        attribute = "title" if path == "job_title" else "description"
        values = [
            getattr(posting, attribute)
            for posting in getattr(record, "active_job_postings", ())
            if getattr(posting, attribute)
        ]
        return "\n".join(values) or None
    if path in {"content", "text"}:
        try:
            return record.website_page.extracted_text
        except AttributeError:
            pass
    value = record.payload
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    if isinstance(value, list):
        return " ".join(str(item) for item in value if not isinstance(item, (dict, list)))
    return value if isinstance(value, (str, int, float)) else None


def _matched_terms(text: str, rule: SignalRule) -> list[str]:
    normalized = _normalize(text)
    matches = []
    for keyword in rule.keywords:
        term = _normalize(str(keyword))
        if term and re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", normalized):
            matches.append(str(keyword))
    if rule.match_mode == SignalRule.MatchMode.ALL and len(matches) != len(rule.keywords):
        return []
    return matches


def _excerpt(text: str, terms: list[str], limit: int = 360) -> str:
    compact = " ".join(text.split())
    positions = [compact.casefold().find(term.casefold()) for term in terms]
    positions = [position for position in positions if position >= 0]
    center = min(positions) if positions else 0
    start = max(0, center - limit // 3)
    end = min(len(compact), start + limit)
    prefix, suffix = ("…" if start else ""), ("…" if end < len(compact) else "")
    return f"{prefix}{compact[start:end]}{suffix}"


@transaction.atomic
def detect_company_signals(company: Company) -> DetectionStats:
    rules = list(SignalRule.objects.filter(active=True))
    seen_signal_ids = set()
    records_scanned = rules_evaluated = signals_matched = signals_created = 0
    records = company.source_records.select_related("website_page").prefetch_related(
        Prefetch(
            "job_postings",
            queryset=JobPosting.objects.filter(active=True),
            to_attr="active_job_postings",
        )
    ).order_by("collected_at")
    for record in records.iterator(chunk_size=100):
        records_scanned += 1
        for rule in rules:
            rules_evaluated += 1
            match = None
            for field_name in rule.source_fields:
                value = _payload_value(record, field_name)
                if value is None:
                    continue
                terms = _matched_terms(str(value), rule)
                if terms:
                    match = (field_name, str(value), terms)
                    break
            if match is None:
                continue
            field_name, value, terms = match
            evidence_hash = hashlib.sha256(
                f"{rule.key}:{rule.version}:{record.pk}".encode()
            ).hexdigest()
            expires_at = (
                record.observed_at + timedelta(days=rule.expires_after_days)
                if rule.expires_after_days
                else None
            )
            excerpt = _excerpt(value, terms)
            signal, created = Signal.objects.update_or_create(
                company=company,
                signal_type=rule.signal_type,
                evidence_hash=evidence_hash,
                defaults={
                    "product": rule.product,
                    "source_record": record,
                    "source_url": record.source_url,
                    "title": rule.name,
                    "evidence_excerpt": excerpt,
                    "base_weight": rule.base_weight,
                    "applies_decay": rule.applies_decay,
                    "observed_at": record.observed_at,
                    "expires_at": expires_at,
                    "active": True,
                    "metadata": {"rule_key": rule.key, "rule_version": rule.version},
                },
            )
            SignalDetection.objects.update_or_create(
                signal=signal,
                rule=rule,
                source_record=record,
                field_name=field_name,
                defaults={"matched_terms": terms, "evidence_excerpt": excerpt},
            )
            seen_signal_ids.add(signal.pk)
            signals_matched += 1
            signals_created += int(created)

    generated = Signal.objects.filter(company=company, detections__isnull=False).distinct()
    stale = generated.exclude(pk__in=seen_signal_ids)
    signals_deactivated = stale.filter(active=True).update(active=False)
    return DetectionStats(records_scanned, rules_evaluated, signals_matched, signals_created, signals_deactivated)
