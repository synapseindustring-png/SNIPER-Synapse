import hashlib
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from django.db import transaction
from django.utils import timezone

from apps.companies.models import Company
from apps.jobs.models import Job
from apps.sources.models import Source, SourceRecord

from .client import WebsiteFetchError, fetch_url
from .extraction import extract_html_text
from .models import WebsitePage
from .security import canonicalize_url


@dataclass(frozen=True, slots=True)
class CrawlOutcome:
    page: WebsitePage
    page_created: bool
    content_changed: bool


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


def _robots_allows(url: str) -> bool:
    parsed = urlsplit(url)
    robots_url = urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
    try:
        result = fetch_url(robots_url, accepted_types=("text/plain", "text/html"))
    except WebsiteFetchError:
        return True
    if result.status != 200:
        return True
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(result.body.decode("utf-8", errors="replace").splitlines())
    return parser.can_fetch("SynapseSniper", url)


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


def crawl_company_website(company: Company) -> CrawlOutcome:
    url = company_website_url(company)
    if not _robots_allows(url):
        raise WebsiteFetchError("A coleta foi bloqueada pelo robots.txt do website.")
    result = fetch_url(url)
    if result.status != 200:
        raise WebsiteFetchError(f"Website respondeu com HTTP {result.status}.")
    title, text = extract_html_text(result.body)
    if not text.strip():
        raise WebsiteFetchError("Website não produziu texto útil.")
    outcome = persist_page(
        company,
        url=result.url,
        status=result.status,
        content_type=result.content_type,
        title=title,
        text=text,
    )
    if not company.website:
        company.website = result.url
        company.website_domain = (urlsplit(result.url).hostname or "").removeprefix("www.")
        company.save(update_fields=("website", "website_domain", "updated_at"))
    return outcome


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
