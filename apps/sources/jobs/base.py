from dataclasses import dataclass, field
from typing import Protocol


class JobsAdapterError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class JobCollectionLimits:
    max_pages: int
    max_results: int
    max_bytes: int

    def __post_init__(self):
        if min(self.max_pages, self.max_results, self.max_bytes) <= 0:
            raise JobsAdapterError("Os limites do adapter de vagas devem ser positivos.")


@dataclass(frozen=True, slots=True)
class JobsQuery:
    company_id: str
    company_name: str
    company_domain: str = ""
    location: str = ""
    terms: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class JobSourceItem:
    external_id: str
    title: str
    company_name: str
    company_domain: str = ""
    company_cnpj: str = ""
    description: str = ""
    location: str = ""
    url: str = ""
    published_on: str = ""
    valid_through: str = ""
    employment_type: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class JobCollectionBatch:
    items: tuple[JobSourceItem, ...]
    pages_read: int
    bytes_read: int
    truncated: bool


class JobsAdapter(Protocol):
    def collect(self, query: JobsQuery, limits: JobCollectionLimits) -> JobCollectionBatch: ...
