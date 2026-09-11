import csv
import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generic, Iterator, TypeVar

from .establishments import CnpjLayoutError, CnpjScanStats


@dataclass(frozen=True, slots=True)
class CnpjCompany:
    cnpj_basico: str
    legal_name: str
    legal_nature_code: str
    responsible_qualification: str
    share_capital: str
    size_code: str
    responsible_federative_entity: str


@dataclass(frozen=True, slots=True)
class CnpjSimples:
    cnpj_basico: str
    simples_option: str
    simples_option_on: str
    simples_excluded_on: str
    mei_option: str
    mei_option_on: str
    mei_excluded_on: str


Record = TypeVar("Record", CnpjCompany, CnpjSimples)


@dataclass(slots=True)
class _SelectiveComplementReader(Generic[Record]):
    source_path: Path
    target_basics: frozenset[str]
    member_name: str | None = None
    encoding: str = "latin1"
    strict: bool = True
    stats: CnpjScanStats = field(default_factory=CnpjScanStats, init=False)
    column_count: int = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.source_path = Path(self.source_path)
        if not self.target_basics:
            raise ValueError("At least one target CNPJ básico is required")
        invalid = [value for value in self.target_basics if len(value) != 8 or not value.isdigit()]
        if invalid:
            raise ValueError("Target CNPJ básico values must contain exactly 8 digits")

    def __iter__(self) -> Iterator[Record]:
        self.stats = CnpjScanStats()
        remaining = set(self.target_basics)
        with zipfile.ZipFile(self.source_path) as archive:
            member_name = self._resolve_member(archive)
            with archive.open(member_name) as raw_stream:
                text_stream = io.TextIOWrapper(raw_stream, encoding=self.encoding, newline="")
                for line_number, row in enumerate(csv.reader(text_stream, delimiter=";"), start=1):
                    if not row:
                        continue
                    self.stats.rows_read += 1
                    if len(row) != self.column_count:
                        self.stats.rows_invalid += 1
                        if self.strict:
                            raise CnpjLayoutError(
                                f"Line {line_number}: expected {self.column_count} columns, "
                                f"found {len(row)}"
                            )
                        continue
                    cnpj_basico = row[0].strip()
                    if cnpj_basico not in remaining:
                        continue
                    self.stats.rows_matched += 1
                    remaining.remove(cnpj_basico)
                    yield self._parse_row(row)
                    if not remaining:
                        return

    def _resolve_member(self, archive: zipfile.ZipFile) -> str:
        if self.member_name:
            try:
                member = archive.getinfo(self.member_name)
            except KeyError as exc:
                raise CnpjLayoutError(
                    f"CSV member {self.member_name!r} was not found in {self.source_path.name}"
                ) from exc
            if member.is_dir():
                raise CnpjLayoutError(f"ZIP member {self.member_name!r} is a directory")
            return member.filename
        candidates = [member.filename for member in archive.infolist() if not member.is_dir()]
        if len(candidates) != 1:
            raise CnpjLayoutError(
                f"Expected one data member in {self.source_path.name}, found {len(candidates)}"
            )
        return candidates[0]

    def _parse_row(self, row: list[str]) -> Record:
        raise NotImplementedError


@dataclass(slots=True)
class CnpjCompanyReader(_SelectiveComplementReader[CnpjCompany]):
    column_count: int = field(default=7, init=False, repr=False)

    def _parse_row(self, row: list[str]) -> CnpjCompany:
        return CnpjCompany(
            cnpj_basico=row[0].strip(),
            legal_name=row[1].strip(),
            legal_nature_code=row[2].strip(),
            responsible_qualification=row[3].strip(),
            share_capital=row[4].strip(),
            size_code=row[5].strip(),
            responsible_federative_entity=row[6].strip(),
        )


@dataclass(slots=True)
class CnpjSimplesReader(_SelectiveComplementReader[CnpjSimples]):
    column_count: int = field(default=7, init=False, repr=False)

    def _parse_row(self, row: list[str]) -> CnpjSimples:
        return CnpjSimples(
            cnpj_basico=row[0].strip(),
            simples_option=row[1].strip(),
            simples_option_on=row[2].strip(),
            simples_excluded_on=row[3].strip(),
            mei_option=row[4].strip(),
            mei_option_on=row[5].strip(),
            mei_excluded_on=row[6].strip(),
        )
