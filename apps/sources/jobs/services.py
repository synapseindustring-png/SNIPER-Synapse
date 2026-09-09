import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlsplit

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.companies.models import Company
from apps.crawler.models import JobPosting, JobPostingReview
from apps.crawler.security import UnsafeWebsiteUrl, canonicalize_url
from apps.crawler.services import persist_job_postings
from apps.sources.models import Source, SourceRecord

from .base import JobCollectionLimits, JobsAdapter, JobsAdapterError, JobsQuery


@dataclass(frozen=True, slots=True)
class JobsCollectionOutcome:
    mode: str
    items_scanned: int
    items_matched: int
    jobs_persisted: int
    reviews_created: int
    pages_read: int
    bytes_read: int
    truncated: bool


def _normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(character for character in value if not unicodedata.combining(character))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def _normalize_cnpj(value: str) -> str:
    return "".join(character for character in value.upper() if character.isalnum())


def _normalize_domain(value: str) -> str:
    value = value.strip().casefold()
    if "://" in value:
        value = urlsplit(value).hostname or ""
    return value.removeprefix("www.").rstrip(".")


def _safe_url(value: str) -> str:
    try:
        return canonicalize_url(value) if value else ""
    except (UnsafeWebsiteUrl, ValueError):
        return ""


def _bounded_metadata(value: dict) -> dict:
    result = {}
    for key, item in list(value.items())[:20]:
        if isinstance(item, (str, int, float, bool)) or item is None:
            result[str(key)[:80]] = str(item)[:200] if isinstance(item, str) else item
    return result


def _match_company(company: Company, item) -> tuple[bool, str]:
    if item.company_cnpj and company.cnpj:
        if _normalize_cnpj(item.company_cnpj) == _normalize_cnpj(company.cnpj):
            return True, "CNPJ exato"
        return False, "CNPJ do candidato diverge da empresa consultada"
    expected_domain = _normalize_domain(
        company.website_domain or (urlsplit(company.website).hostname or "")
    )
    candidate_domain = _normalize_domain(item.company_domain)
    if candidate_domain and expected_domain:
        if candidate_domain == expected_domain:
            return True, "Domínio exato"
        return False, "Domínio do candidato diverge da empresa consultada"
    candidate_name = _normalize_name(item.company_name)
    company_names = {
        _normalize_name(company.legal_name),
        _normalize_name(company.trade_name),
    } - {""}
    if candidate_name and candidate_name in company_names:
        matches = list(
            Company.objects.filter(deleted_at__isnull=True)
            .filter(Q(legal_name__iexact=item.company_name) | Q(trade_name__iexact=item.company_name))
            .values_list("pk", flat=True)[:2]
        )
        if matches == [company.pk]:
            return True, "Nome exato e único"
        return False, "Nome exato, porém não único"
    return False, "Identidade da empresa insuficiente ou divergente"


def _candidate_fingerprint(source: Source, item) -> str:
    identity = item.external_id or item.url or json.dumps(
        [item.company_name.casefold(), item.title.casefold(), item.location.casefold(), item.published_on],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(f"{source.key}:{identity}".encode()).hexdigest()


def _review_candidate(source: Source, company: Company, item, reason: str, observed_at) -> bool:
    fingerprint = _candidate_fingerprint(source, item)
    defaults = {
        "external_id": item.external_id,
        "company_name": item.company_name,
        "company_domain": _normalize_domain(item.company_domain),
        "title": item.title,
        "location": item.location,
        "url": _safe_url(item.url),
        "reason": reason,
        "suggested_company": company,
        "metadata": _bounded_metadata(item.metadata),
        "last_seen_at": observed_at,
    }
    _, created = JobPostingReview.objects.update_or_create(
        source=source,
        candidate_fingerprint=fingerprint,
        defaults=defaults,
        create_defaults={**defaults, "first_seen_at": observed_at},
    )
    return created


def _persist_item(source: Source, company: Company, item, observed_at) -> str:
    source_url = _safe_url(item.url)
    external_id = item.external_id or _candidate_fingerprint(source, item)
    payload = {
        "external_id": item.external_id,
        "title": item.title,
        "company_name": item.company_name,
        "company_domain": _normalize_domain(item.company_domain),
        "description": item.description,
        "location": item.location,
        "url": source_url,
        "published_on": item.published_on,
        "valid_through": item.valid_through,
        "employment_type": item.employment_type,
        "metadata": _bounded_metadata(item.metadata),
    }
    payload_hash = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    record, _ = SourceRecord.objects.get_or_create(
        source=source,
        external_id=external_id[:255],
        payload_hash=payload_hash,
        defaults={
            "company": company,
            "source_url": source_url,
            "payload": payload,
            "observed_at": observed_at,
        },
    )
    if record.company_id != company.pk:
        return ""
    structured = {
        "@type": "JobPosting",
        "identifier": item.external_id,
        "title": item.title,
        "description": item.description,
        "jobLocation": {"address": {"addressLocality": item.location}},
        "employmentType": item.employment_type,
        "url": source_url,
        "datePosted": item.published_on,
        "validThrough": item.valid_through,
    }
    persist_job_postings(
        company,
        source_record=record,
        structured_data=[structured],
        observed_at=observed_at,
    )
    return (
        JobPosting.objects.filter(company=company, source_record=record)
        .values_list("fingerprint", flat=True)
        .first()
        or ""
    )


def collect_company_jobs(
    company: Company,
    *,
    source: Source,
    adapter: JobsAdapter,
    mode: str = "PREVIEW",
    limits: JobCollectionLimits,
) -> JobsCollectionOutcome:
    mode = mode.upper()
    if mode not in {"PREVIEW", "FULL"}:
        raise JobsAdapterError("Modo de vagas deve ser PREVIEW ou FULL.")
    if not settings.JOBS_ADAPTER_ENABLED or not source.enabled:
        raise JobsAdapterError("Adapter de vagas está desligado.")
    query = JobsQuery(
        company_id=str(company.pk),
        company_name=company.trade_name or company.legal_name,
        company_domain=company.website_domain,
        location="/".join(filter(None, (company.municipality, company.state))),
    )
    batch = adapter.collect(query, limits)
    observed_at = timezone.now()
    matched = persisted = reviews = 0
    seen_fingerprints = set()
    for item in batch.items:
        is_match, reason = _match_company(company, item)
        if is_match:
            matched += 1
            if mode == "FULL":
                fingerprint = _persist_item(source, company, item, observed_at)
                if fingerprint:
                    seen_fingerprints.add(fingerprint)
                    persisted += 1
        elif mode == "FULL":
            reviews += int(_review_candidate(source, company, item, reason, observed_at))
    if mode == "FULL" and not batch.truncated:
        JobPosting.objects.filter(
            company=company, source_record__source=source, active=True
        ).exclude(fingerprint__in=seen_fingerprints).update(active=False)
    return JobsCollectionOutcome(
        mode=mode,
        items_scanned=len(batch.items),
        items_matched=matched,
        jobs_persisted=persisted,
        reviews_created=reviews,
        pages_read=batch.pages_read,
        bytes_read=batch.bytes_read,
        truncated=batch.truncated,
    )
