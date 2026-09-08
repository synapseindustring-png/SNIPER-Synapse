import base64
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import PurePosixPath
from urllib.parse import quote, unquote, urljoin, urlparse

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.sources.models import CnpjDataset, CnpjDatasetFile, Source

from .storage import CnpjDownloadError, validate_source_url


DAV = "{DAV:}"
COMPETENCE_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
FILE_PATTERNS = (
    (re.compile(r"^Estabelecimentos(\d+)\.zip$", re.IGNORECASE), CnpjDatasetFile.Kind.ESTABLISHMENTS),
    (re.compile(r"^Empresas(\d+)\.zip$", re.IGNORECASE), CnpjDatasetFile.Kind.COMPANIES),
    (re.compile(r"^Simples\.zip$", re.IGNORECASE), CnpjDatasetFile.Kind.SIMPLES),
)


class CnpjManifestError(CnpjDownloadError):
    pass


@dataclass(frozen=True, slots=True)
class WebDavEntry:
    name: str
    href: str
    is_collection: bool
    size_bytes: int | None
    etag: str
    last_modified: object | None


class CnpjWebDavClient:
    def __init__(self, opener=urllib.request.urlopen):
        self.opener = opener
        self.base_url = settings.CNPJ_SOURCE_BASE_URL.rstrip("/") + "/"
        self.token = settings.CNPJ_WEBDAV_TOKEN
        if not self.base_url or not self.token:
            raise CnpjManifestError("CNPJ WebDAV URL and token must be configured")
        validate_source_url(self.base_url)

    def list(self, relative_path: str = "") -> list[WebDavEntry]:
        clean_path = "/".join(
            quote(part, safe="") for part in PurePosixPath(relative_path).parts if part not in {"/", "."}
        )
        url = urljoin(self.base_url, f"{clean_path}/" if clean_path else "")
        validate_source_url(url)
        credentials = base64.b64encode(f"{self.token}:".encode()).decode()
        request = urllib.request.Request(
            url,
            method="PROPFIND",
            data=(
                b'<?xml version="1.0"?>'
                b'<d:propfind xmlns:d="DAV:"><d:prop>'
                b"<d:resourcetype/><d:getcontentlength/><d:getetag/><d:getlastmodified/>"
                b"</d:prop></d:propfind>"
            ),
            headers={
                "Authorization": f"Basic {credentials}",
                "Depth": "1",
                "Content-Type": "application/xml",
                "User-Agent": "SynapseSniper/0.1",
            },
        )
        with self.opener(request, timeout=settings.CNPJ_DOWNLOAD_TIMEOUT_SECONDS) as response:
            validate_source_url(response.geturl())
            content = response.read(settings.CNPJ_MANIFEST_MAX_BYTES + 1)
        if len(content) > settings.CNPJ_MANIFEST_MAX_BYTES:
            raise CnpjManifestError("WebDAV manifest exceeded the configured size")
        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            raise CnpjManifestError("WebDAV returned invalid XML") from exc
        entries = []
        requested_path = urlparse(url).path.rstrip("/") + "/"
        for response_node in root.findall(f"{DAV}response"):
            href = unquote(response_node.findtext(f"{DAV}href", default=""))
            if urlparse(href).path.rstrip("/") + "/" == requested_path:
                continue
            prop = response_node.find(f"{DAV}propstat/{DAV}prop")
            if prop is None:
                continue
            name = PurePosixPath(urlparse(href).path.rstrip("/")).name
            resource_type = prop.find(f"{DAV}resourcetype")
            is_collection = resource_type is not None and resource_type.find(f"{DAV}collection") is not None
            size_text = prop.findtext(f"{DAV}getcontentlength")
            modified_text = prop.findtext(f"{DAV}getlastmodified")
            entries.append(
                WebDavEntry(
                    name=name,
                    href=href,
                    is_collection=is_collection,
                    size_bytes=int(size_text) if size_text else None,
                    etag=(prop.findtext(f"{DAV}getetag") or "").strip('"'),
                    last_modified=parsedate_to_datetime(modified_text) if modified_text else None,
                )
            )
        return entries

    def file_url(self, competence: str, filename: str) -> str:
        url = urljoin(self.base_url, f"{quote(competence)}/{quote(filename)}")
        return validate_source_url(url)


def _classify_file(entry: WebDavEntry):
    if entry.is_collection or not entry.size_bytes:
        return None
    for pattern, kind in FILE_PATTERNS:
        if match := pattern.fullmatch(entry.name):
            part_number = int(match.group(1)) if match.groups() else 0
            return kind, part_number
    return None


@transaction.atomic
def sync_latest_manifest(client: CnpjWebDavClient | None = None) -> CnpjDataset:
    client = client or CnpjWebDavClient()
    competences = sorted(
        entry.name
        for entry in client.list()
        if entry.is_collection and COMPETENCE_PATTERN.fullmatch(entry.name)
    )
    if not competences:
        raise CnpjManifestError("No valid CNPJ competence was found")
    competence = competences[-1]
    classified = []
    for entry in client.list(competence):
        if classification := _classify_file(entry):
            classified.append((entry, *classification))
    establishment_parts = {
        part_number for _, kind, part_number in classified if kind == CnpjDatasetFile.Kind.ESTABLISHMENTS
    }
    company_parts = {
        part_number for _, kind, part_number in classified if kind == CnpjDatasetFile.Kind.COMPANIES
    }
    has_simples = any(kind == CnpjDatasetFile.Kind.SIMPLES for _, kind, _ in classified)
    expected_parts = set(range(10))
    if establishment_parts != expected_parts or company_parts != expected_parts or not has_simples:
        raise CnpjManifestError("Latest competence is incomplete; current manifest was preserved")

    source = Source.objects.select_for_update().get(key="receita-cnpj", enabled=True)
    dataset, _ = CnpjDataset.objects.update_or_create(
        source=source,
        reference=competence,
        defaults={
            "status": CnpjDataset.Status.READY,
            "discovered_at": timezone.now(),
            "verified_at": timezone.now(),
        },
    )
    CnpjDataset.objects.filter(source=source, is_current=True).exclude(pk=dataset.pk).update(
        is_current=False
    )
    dataset.is_current = True
    dataset.save(update_fields=("is_current",))
    seen = []
    for entry, kind, part_number in classified:
        file_record, _ = CnpjDatasetFile.objects.update_or_create(
            dataset=dataset,
            kind=kind,
            part_number=part_number,
            defaults={
                "url": client.file_url(competence, entry.name),
                "size_bytes": entry.size_bytes,
                "etag": entry.etag,
            },
        )
        seen.append(file_record.pk)
    dataset.files.exclude(pk__in=seen).delete()
    return dataset
