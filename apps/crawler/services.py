import hashlib
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.companies.models import Company
from apps.jobs.models import Job
from apps.sources.models import Source, SourceRecord

from .client import WebsiteFetchError, fetch_url
from .extraction import extract_html_document
from .models import WebsitePage
from .security import UnsafeWebsiteUrl, canonicalize_url, same_site


@dataclass(frozen=True, slots=True)
class CrawlOutcome:
    page: WebsitePage
    page_created: bool
    content_changed: bool


@dataclass(frozen=True, slots=True)
class CrawlBatchOutcome:
    pages: tuple[CrawlOutcome, ...]
    pages_attempted: int
    pages_failed: int


def company_website_url(company: Company) -> str:
    value = company.website or (f"https://{company.website_domain}" if company.website_domain else "")
    if not value:
        raise WebsiteFetchError("A empresa não possui website cadastrado.")
    url = canonicalize_url(value)
    actual_domain = (urlsplit(url).hostname or "").removeprefix("www.")
    expected_domain = company.website_domain.lower().removeprefix("www.")
    if expected_domain and actual_domain != expected_domain:
        raise WebsiteFetchError("O website não corresponde ao domínio canônico da empresa.")
    return url


def _robots_policy(url: str) -> RobotFileParser | None:
    parsed = urlsplit(url)
    robots_url = urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
    try:
        result = fetch_url(robots_url, accepted_types=("text/plain", "text/html"))
    except WebsiteFetchError:
        return None
    if result.status != 200:
        return None
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(result.body.decode("utf-8", errors="replace").splitlines())
    return parser


PRIORITY_PATH_TERMS = (
    ("sobre", "about", "empresa"),
    ("solucao", "solution", "produto", "servico"),
    ("case", "cliente", "industria"),
    ("noticia", "news", "blog"),
    ("carreira", "trabalhe", "vaga", "jobs"),
)


def discover_priority_urls(base_url: str, links, *, limit: int) -> list[str]:
    candidates = {}
    base_scheme = urlsplit(base_url).scheme
    for link in links:
        try:
            candidate = canonicalize_url(urljoin(base_url, link))
        except (UnsafeWebsiteUrl, ValueError):
            continue
        parsed = urlsplit(candidate)
        if parsed.query or not same_site(base_url, candidate):
            continue
        if base_scheme == "https" and parsed.scheme != "https":
            continue
        path = parsed.path.casefold()
        priority = next(
            (
                index
                for index, terms in enumerate(PRIORITY_PATH_TERMS)
                if any(term in path for term in terms)
            ),
            None,
        )
        if priority is None or candidate == canonicalize_url(base_url):
            continue
        candidates[candidate] = min(candidates.get(candidate, priority), priority)
    return [
        url
        for url, _ in sorted(candidates.items(), key=lambda item: (item[1], len(item[0]), item[0]))[
            : max(0, limit)
        ]
    ]


def _page_type(url: str) -> str:
    path = urlsplit(url).path.casefold()
    if path in {"", "/"}:
        return WebsitePage.PageType.HOME
    if any(term in path for term in ("sobre", "about", "empresa")):
        return WebsitePage.PageType.ABOUT
    if any(term in path for term in ("produto", "solucao", "solution", "servico")):
        return WebsitePage.PageType.PRODUCT
    if any(term in path for term in ("case", "cliente")):
        return WebsitePage.PageType.CASE
    if any(term in path for term in ("blog", "noticia", "news")):
        return WebsitePage.PageType.NEWS
    if any(term in path for term in ("carreira", "trabalhe", "vaga", "jobs")):
        return WebsitePage.PageType.CAREERS
    return WebsitePage.PageType.OTHER


@transaction.atomic
def persist_page(company: Company, *, url: str, status: int, content_type: str, title: str, text: str, observed_at=None) -> CrawlOutcome:
    observed_at = observed_at or timezone.now()
    canonical_url = canonicalize_url(url)
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    source = Source.objects.get(key="website", enabled=True)
    source_record, _ = SourceRecord.objects.get_or_create(
        source=source,
        external_id=canonical_url,
        payload_hash=content_hash,
        defaults={
            "company": company,
            "source_url": canonical_url,
            "payload": {
                "url": canonical_url,
                "title": title,
                "content_type": content_type,
                "http_status": status,
            },
            "observed_at": observed_at,
        },
    )
    if source_record.company_id != company.pk:
        raise WebsiteFetchError(
            "O mesmo website e conteúdo já estão vinculados a outra empresa; revisão necessária."
        )
    page = WebsitePage.objects.filter(
        company=company, url=canonical_url, content_hash=content_hash
    ).first()
    if page:
        WebsitePage.objects.filter(pk=page.pk).update(last_seen_at=observed_at, current=True)
        page.refresh_from_db()
        return CrawlOutcome(page, False, False)

    content_changed = WebsitePage.objects.filter(
        company=company, url=canonical_url, current=True
    ).exists()
    WebsitePage.objects.filter(company=company, url=canonical_url, current=True).update(current=False)
    page = WebsitePage.objects.create(
        company=company,
        source_record=source_record,
        url=canonical_url,
        page_type=_page_type(canonical_url),
        title=title,
        extracted_text=text,
        content_hash=content_hash,
        http_status=status,
        content_type=content_type,
        observed_at=observed_at,
        last_seen_at=observed_at,
    )
    return CrawlOutcome(page, True, content_changed)


def crawl_company_website(company: Company) -> CrawlBatchOutcome:
    url = company_website_url(company)
    robots = _robots_policy(url)
    if robots and not robots.can_fetch(settings.CRAWLER_USER_AGENT, url):
        raise WebsiteFetchError("A coleta foi bloqueada pelo robots.txt do website.")
    result = fetch_url(url)
    if result.status != 200:
        raise WebsiteFetchError(f"Website respondeu com HTTP {result.status}.")
    document = extract_html_document(result.body)
    if not document.text.strip():
        raise WebsiteFetchError("Website não produziu texto útil.")
    outcomes = [persist_page(
        company,
        url=result.url,
        status=result.status,
        content_type=result.content_type,
        title=document.title,
        text=document.text,
    )]
    candidate_urls = discover_priority_urls(
        result.url,
        document.links,
        limit=max(0, settings.CRAWLER_MAX_PAGES - 1),
    )
    pages_failed = 0
    for candidate_url in candidate_urls:
        if robots and not robots.can_fetch(settings.CRAWLER_USER_AGENT, candidate_url):
            continue
        try:
            candidate_result = fetch_url(candidate_url)
            if candidate_result.status != 200:
                raise WebsiteFetchError(f"Página respondeu com HTTP {candidate_result.status}.")
            candidate_document = extract_html_document(candidate_result.body)
            if not candidate_document.text.strip():
                raise WebsiteFetchError("Página não produziu texto útil.")
            outcomes.append(
                persist_page(
                    company,
                    url=candidate_result.url,
                    status=candidate_result.status,
                    content_type=candidate_result.content_type,
                    title=candidate_document.title,
                    text=candidate_document.text,
                )
            )
        except (UnsafeWebsiteUrl, WebsiteFetchError):
            pages_failed += 1
    if not company.website:
        company.website = result.url
        company.website_domain = (urlsplit(result.url).hostname or "").removeprefix("www.")
        company.save(update_fields=("website", "website_domain", "updated_at"))
    return CrawlBatchOutcome(tuple(outcomes), 1 + len(candidate_urls), pages_failed)


def enqueue_website_crawl(company: Company, *, as_of=None) -> tuple[Job, bool]:
    as_of = as_of or timezone.now()
    url = company_website_url(company)
    return Job.objects.get_or_create(
        idempotency_key=f"website:{company.pk}:{url}:{as_of.date().isoformat()}",
        defaults={
            "type": Job.Type.CRAWL_WEBSITE,
            "payload": {"company_id": str(company.pk)},
            "priority": 30,
        },
    )
