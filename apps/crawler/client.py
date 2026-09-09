import http.client
import socket
import ssl
from dataclasses import dataclass
from urllib.parse import urljoin

from django.conf import settings

from .security import resolve_public_url, same_site


class WebsiteFetchError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FetchResult:
    url: str
    status: int
    content_type: str
    body: bytes


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host, *, ip_address, port, timeout):
        self._ip_address = ip_address
        super().__init__(host, port=port, timeout=timeout)

    def connect(self):
        self.sock = socket.create_connection(
            (self._ip_address, self.port), self.timeout, self.source_address
        )


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, *, ip_address, port, timeout):
        self._ip_address = ip_address
        super().__init__(
            host,
            port=port,
            timeout=timeout,
            context=ssl.create_default_context(),
        )

    def connect(self):
        raw_socket = socket.create_connection(
            (self._ip_address, self.port), self.timeout, self.source_address
        )
        self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)


def _user_agent() -> str:
    contact = settings.CRAWLER_CONTACT
    return f"{settings.CRAWLER_USER_AGENT} ({contact})" if contact else settings.CRAWLER_USER_AGENT


def fetch_url(value: str, *, accepted_types=("text/html", "application/xhtml+xml")) -> FetchResult:
    original_url = value
    current_url = value
    for redirect_count in range(settings.CRAWLER_MAX_REDIRECTS + 1):
        resolved = resolve_public_url(current_url)
        connection_class = (
            _PinnedHTTPSConnection if resolved.scheme == "https" else _PinnedHTTPConnection
        )
        connection = connection_class(
            resolved.hostname,
            ip_address=resolved.ip_address,
            port=resolved.port,
            timeout=settings.CRAWLER_TIMEOUT_SECONDS,
        )
        try:
            connection.request(
                "GET",
                resolved.request_target,
                headers={
                    "Host": resolved.hostname,
                    "User-Agent": _user_agent(),
                    "Accept": "text/html,application/xhtml+xml;q=0.9,text/plain;q=0.5",
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                },
            )
            response = connection.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                response.read(1024)
                if not location or redirect_count >= settings.CRAWLER_MAX_REDIRECTS:
                    raise WebsiteFetchError("Redirect ausente ou acima do limite.")
                next_url = urljoin(resolved.url, location)
                if not same_site(original_url, next_url):
                    raise WebsiteFetchError("Redirect para outro domínio foi bloqueado.")
                if resolved.scheme == "https" and next_url.lower().startswith("http://"):
                    raise WebsiteFetchError("Downgrade de HTTPS para HTTP foi bloqueado.")
                current_url = next_url
                continue

            content_type = (response.getheader("Content-Type") or "").split(";", 1)[0].lower()
            if content_type not in accepted_types:
                raise WebsiteFetchError(f"Content-Type não permitido: {content_type or 'ausente'}")
            content_length = response.getheader("Content-Length")
            if content_length:
                try:
                    declared_length = int(content_length)
                except ValueError as exc:
                    raise WebsiteFetchError("Content-Length inválido.") from exc
                if declared_length > settings.CRAWLER_MAX_BYTES:
                    raise WebsiteFetchError("Página excede o limite configurado.")
            body = response.read(settings.CRAWLER_MAX_BYTES + 1)
            if len(body) > settings.CRAWLER_MAX_BYTES:
                raise WebsiteFetchError("Página excedeu o limite durante a leitura.")
            return FetchResult(resolved.url, response.status, content_type, body)
        except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
            raise WebsiteFetchError(f"Falha ao buscar website: {type(exc).__name__}") from exc
        finally:
            connection.close()
    raise WebsiteFetchError("Redirect acima do limite.")
