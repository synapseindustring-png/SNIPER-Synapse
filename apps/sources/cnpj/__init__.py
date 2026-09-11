"""Selective readers for Receita Federal CNPJ datasets."""

from .establishments import (
    CnpjEstablishment,
    CnpjEstablishmentFilter,
    CnpjEstablishmentReader,
    CnpjLayoutError,
    CnpjScanStats,
)
from .complements import (
    CnpjCompany,
    CnpjCompanyReader,
    CnpjSimples,
    CnpjSimplesReader,
)

__all__ = [
    "CnpjEstablishment",
    "CnpjEstablishmentFilter",
    "CnpjEstablishmentReader",
    "CnpjLayoutError",
    "CnpjScanStats",
    "CnpjCompany",
    "CnpjCompanyReader",
    "CnpjSimples",
    "CnpjSimplesReader",
]
