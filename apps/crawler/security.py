import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


class UnsafeWebsiteUrl(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ResolvedWebsiteUrl:
    url: str
    scheme: str
    hostname: str
    port: int
    ip_address: str
    request_target: str


def canonicalize_url(value: str) -> str:
    value = value.strip()
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise UnsafeWebsiteUrl("A URL contém caracteres de controle.")
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise UnsafeWebsiteUrl("Apenas URLs HTTP/HTTPS são permitidas.")
    if not parsed.hostname or parsed.username or parsed.password:
        raise UnsafeWebsiteUrl("A URL precisa ter host e não pode conter credenciais.")
    try:
        hostname = parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError as exc:
        raise UnsafeWebsiteUrl("Hostname inválido.") from exc
    scheme = parsed.scheme.lower()
    try:
        port = parsed.port
    except ValueError as exc:
        raise UnsafeWebsiteUrl("Porta inválida.") from exc
    expected_port = 443 if scheme == "https" else 80
    if port not in (None, expected_port):
        raise UnsafeWebsiteUrl("Somente as portas HTTP/HTTPS padrão são permitidas.")
    netloc = f"[{hostname}]" if ":" in hostname else hostname
    path = parsed.path or "/"
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


def resolve_public_url(value: str) -> ResolvedWebsiteUrl:
    url = canonicalize_url(value)
    parsed = urlsplit(url)
    port = 443 if parsed.scheme == "https" else 80
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(
                parsed.hostname, port, type=socket.SOCK_STREAM
            )
        }
    except socket.gaierror as exc:
        raise UnsafeWebsiteUrl("Não foi possível resolver o domínio.") from exc
    if not addresses:
        raise UnsafeWebsiteUrl("O domínio não retornou endereços IP.")
    for address in addresses:
        try:
            parsed_ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise UnsafeWebsiteUrl("O domínio retornou um IP inválido.") from exc
        if not parsed_ip.is_global:
            raise UnsafeWebsiteUrl("O domínio aponta para uma rede privada ou reservada.")
    selected = sorted(addresses, key=lambda item: (":" in item, item))[0]
    target = parsed.path or "/"
    if parsed.query:
        target = f"{target}?{parsed.query}"
    return ResolvedWebsiteUrl(
        url=url,
        scheme=parsed.scheme,
        hostname=parsed.hostname,
        port=port,
        ip_address=selected,
        request_target=target,
    )


def same_site(first_url: str, second_url: str) -> bool:
    def normalized_host(value):
        host = (urlsplit(value).hostname or "").lower().rstrip(".")
        return host[4:] if host.startswith("www.") else host

    return normalized_host(first_url) == normalized_host(second_url)
