from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.companies.models import Company
from apps.jobs.models import Job
from apps.jobs.services import execute_job

from .client import FetchResult
from .extraction import extract_html_document, extract_html_text
from .models import WebsitePage
from .security import UnsafeWebsiteUrl, canonicalize_url, resolve_public_url
from .services import crawl_company_website, discover_priority_urls, persist_page


class WebsiteSecurityTests(TestCase):
    def test_canonicalization_rejects_credentials_and_nonstandard_ports(self):
        with self.assertRaises(UnsafeWebsiteUrl):
            canonicalize_url("https://user:secret@example.com/")
        with self.assertRaises(UnsafeWebsiteUrl):
            canonicalize_url("https://example.com:8443/")
        with self.assertRaises(UnsafeWebsiteUrl):
            canonicalize_url("https://example.com/\nheader")

    @patch("apps.crawler.security.socket.getaddrinfo")
    def test_dns_resolution_rejects_private_or_mixed_answers(self, getaddrinfo):
        getaddrinfo.return_value = [
            (2, 1, 6, "", ("93.184.216.34", 443)),
            (2, 1, 6, "", ("127.0.0.1", 443)),
        ]
        with self.assertRaises(UnsafeWebsiteUrl):
            resolve_public_url("https://example.com/")

    @patch("apps.crawler.security.socket.getaddrinfo")
    def test_public_resolution_returns_a_pinned_ip(self, getaddrinfo):
        getaddrinfo.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
        resolved = resolve_public_url("https://Example.com/path?q=1#fragment")
        self.assertEqual(resolved.hostname, "example.com")
        self.assertEqual(resolved.ip_address, "93.184.216.34")
        self.assertEqual(resolved.request_target, "/path?q=1")


class WebsiteExtractionTests(TestCase):
    @override_settings(CRAWLER_MAX_TEXT_CHARS=1000)
    def test_extracts_visible_text_without_script_or_style(self):
        title, text = extract_html_text(
            b"<html><head><title>Industria Alfa</title><style>secret-css</style></head>"
            b"<body><h1>OEE e PCM</h1><script>secret-js</script></body></html>"
        )
        self.assertEqual(title, "Industria Alfa")
        self.assertIn("OEE e PCM", text)
        self.assertNotIn("secret-css", text)
        self.assertNotIn("secret-js", text)

    def test_extracts_unique_links_only_from_visible_markup(self):
        document = extract_html_document(
            b'<a href="/sobre">Sobre</a><a href="/sobre">Repetido</a>'
            b'<script><a href="/private">Privado</a></script>'
        )
        self.assertEqual(document.links, ("/sobre",))

    def test_prioritization_is_same_site_queryless_and_bounded(self):
        urls = discover_priority_urls(
            "https://example.com/",
            [
                "/blog/noticia?pagina=2",
                "https://evil.example.net/sobre",
                "/carreiras",
                "/produtos/mes",
                "/sobre",
            ],
            limit=2,
        )
        self.assertEqual(
            urls,
            ["https://example.com/sobre", "https://example.com/produtos/mes"],
        )


class WebsitePersistenceTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            legal_name="Indústria Web",
            company_type=Company.Type.INDUSTRY,
            registration_status=Company.RegistrationStatus.ACTIVE,
            website="https://example.com/",
            website_domain="example.com",
        )

    def test_unchanged_page_is_deduplicated_and_changed_page_keeps_history(self):
        first = persist_page(
            self.company,
            url=self.company.website,
            status=200,
            content_type="text/html",
            title="Alfa",
            text="Conteúdo inicial",
        )
        repeated = persist_page(
            self.company,
            url=self.company.website,
            status=200,
            content_type="text/html",
            title="Alfa",
            text="Conteúdo inicial",
            observed_at=timezone.now(),
        )
        changed = persist_page(
            self.company,
            url=self.company.website,
            status=200,
            content_type="text/html",
            title="Alfa",
            text="Novo conteúdo sobre OEE",
        )

        self.assertTrue(first.page_created)
        self.assertFalse(repeated.page_created)
        self.assertTrue(changed.content_changed)
        self.assertEqual(WebsitePage.objects.count(), 2)
        self.assertEqual(WebsitePage.objects.filter(current=True).count(), 1)

    @patch("apps.crawler.services.fetch_url")
    def test_crawl_job_persists_page_and_enqueues_scoring(self, fetch_url):
        fetch_url.side_effect = [
            FetchResult("https://example.com/robots.txt", 404, "text/plain", b""),
            FetchResult(
                "https://example.com/",
                200,
                "text/html",
                b"<html><title>Alfa</title><body>Projeto de OEE</body></html>",
            ),
        ]
        job = Job.objects.create(
            type=Job.Type.CRAWL_WEBSITE,
            payload={"company_id": str(self.company.pk)},
        )

        execute_job(job)

        self.assertEqual(WebsitePage.objects.count(), 1)
        self.assertTrue(self.company.signals.filter(signal_type="oee").exists())
        self.assertTrue(Job.objects.filter(type=Job.Type.CALCULATE_SCORE).exists())

    @override_settings(CRAWLER_MAX_PAGES=3)
    @patch("apps.crawler.services.fetch_url")
    def test_crawl_follows_only_the_bounded_priority_pages(self, fetch_url):
        fetch_url.side_effect = [
            FetchResult("https://example.com/robots.txt", 404, "text/plain", b""),
            FetchResult(
                "https://example.com/",
                200,
                "text/html",
                b'<a href="/sobre">Sobre</a><a href="/produtos">Produtos</a>'
                b'<a href="/carreiras">Carreiras</a>',
            ),
            FetchResult(
                "https://example.com/sobre",
                200,
                "text/html",
                b"<h1>Sobre a empresa</h1>",
            ),
            FetchResult(
                "https://example.com/produtos",
                200,
                "text/html",
                b"<h1>Solucoes industriais</h1>",
            ),
        ]

        outcome = crawl_company_website(self.company)

        self.assertEqual(outcome.pages_attempted, 3)
        self.assertEqual(len(outcome.pages), 3)
        self.assertEqual(WebsitePage.objects.filter(current=True).count(), 3)
        self.assertFalse(
            WebsitePage.objects.filter(url="https://example.com/carreiras").exists()
        )
