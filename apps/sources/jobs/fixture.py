import json
from pathlib import Path

from .base import (
    JobCollectionBatch,
    JobCollectionLimits,
    JobSourceItem,
    JobsAdapterError,
    JobsQuery,
)


def _text(value, limit: int) -> str:
    if not isinstance(value, (str, int, float)):
        return ""
    return " ".join(str(value).split())[:limit]


class FixtureJobsAdapter:
    def __init__(self, fixture_root: Path, fixture_name: str):
        if not fixture_name or Path(fixture_name).name != fixture_name:
            raise JobsAdapterError("Nome de fixture inválido.")
        self.path = (fixture_root / fixture_name).resolve()
        root = fixture_root.resolve()
        if self.path.parent != root or self.path.suffix.casefold() != ".json":
            raise JobsAdapterError("A fixture deve ser um JSON direto do diretório permitido.")

    def collect(self, query: JobsQuery, limits: JobCollectionLimits) -> JobCollectionBatch:
        try:
            size = self.path.stat().st_size
        except OSError as exc:
            raise JobsAdapterError("Fixture de vagas indisponível.") from exc
        if size > limits.max_bytes:
            raise JobsAdapterError("Fixture de vagas excede o limite de bytes.")
        try:
            payload = json.loads(self.path.read_bytes())
        except (OSError, ValueError) as exc:
            raise JobsAdapterError("Fixture de vagas inválida.") from exc
        pages = payload.get("pages") if isinstance(payload, dict) else None
        if not isinstance(pages, list):
            pages = [payload]
        selected_pages = pages[: limits.max_pages]
        raw_items = []
        for page in selected_pages:
            page_items = page.get("items") if isinstance(page, dict) else page
            if isinstance(page_items, list):
                raw_items.extend(page_items)
        truncated = len(pages) > len(selected_pages) or len(raw_items) > limits.max_results
        items = []
        for raw_item in raw_items[: limits.max_results]:
            if not isinstance(raw_item, dict):
                continue
            title = _text(raw_item.get("title"), 500)
            if not title:
                continue
            metadata = raw_item.get("metadata")
            items.append(
                JobSourceItem(
                    external_id=_text(raw_item.get("external_id"), 500),
                    title=title,
                    company_name=_text(raw_item.get("company_name"), 500),
                    company_domain=_text(raw_item.get("company_domain"), 255).casefold(),
                    company_cnpj=_text(raw_item.get("company_cnpj"), 32),
                    description=_text(raw_item.get("description"), 20_000),
                    location=_text(raw_item.get("location"), 500),
                    url=_text(raw_item.get("url"), 1000),
                    published_on=_text(raw_item.get("published_on"), 40),
                    valid_through=_text(raw_item.get("valid_through"), 40),
                    employment_type=_text(raw_item.get("employment_type"), 120),
                    metadata=metadata if isinstance(metadata, dict) else {},
                )
            )
        return JobCollectionBatch(tuple(items), len(selected_pages), size, truncated)
