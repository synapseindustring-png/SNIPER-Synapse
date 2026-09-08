import csv
import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


ESTABLISHMENT_COLUMN_COUNT = 30


class CnpjLayoutError(ValueError):
    """Raised when a source row does not match the documented Receita layout."""


@dataclass(frozen=True, slots=True)
class CnpjEstablishment:
    cnpj_basico: str
    cnpj_ordem: str
    cnpj_dv: str
    branch_identifier: str
    trade_name: str
    registration_status: str
    registration_status_date: str
    activity_started_on: str
    primary_cnae: str
    secondary_cnaes: tuple[str, ...]
    street_type: str
    street: str
    number: str
    complement: str
    district: str
    postal_code: str
    state: str
    municipality_code: str
    phone: str
    secondary_phone: str
    email: str

    @property
    def cnpj(self) -> str:
        return f"{self.cnpj_basico}{self.cnpj_ordem}{self.cnpj_dv}"


@dataclass(frozen=True, slots=True)
class CnpjEstablishmentFilter:
    registration_statuses: frozenset[str] = frozenset()
    states: frozenset[str] = frozenset()
    municipality_codes: frozenset[str] = frozenset()
    cnae_codes: frozenset[str] = frozenset()
    cnae_prefixes: tuple[str, ...] = ()
    include_secondary_cnaes: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "states",
            frozenset(state.strip().upper() for state in self.states if state.strip()),
        )
        object.__setattr__(
            self,
            "cnae_prefixes",
            tuple(prefix.strip() for prefix in self.cnae_prefixes if prefix.strip()),
        )
        for prefix in self.cnae_prefixes:
            if not prefix.isdigit() or len(prefix) > 7:
                raise ValueError(f"Invalid CNAE prefix: {prefix!r}")

    @property
    def is_selective(self) -> bool:
        return bool(
            self.states
            or self.municipality_codes
            or self.cnae_codes
            or self.cnae_prefixes
        )

    def matches(self, establishment: CnpjEstablishment) -> bool:
        if (
            self.registration_statuses
            and establishment.registration_status not in self.registration_statuses
        ):
            return False
        if self.states and establishment.state not in self.states:
            return False
        if (
            self.municipality_codes
            and establishment.municipality_code not in self.municipality_codes
        ):
            return False

        if not self.cnae_codes and not self.cnae_prefixes:
            return True
        cnaes = (establishment.primary_cnae,)
        if self.include_secondary_cnaes:
            cnaes += establishment.secondary_cnaes
        return any(
            cnae in self.cnae_codes
            or any(cnae.startswith(prefix) for prefix in self.cnae_prefixes)
            for cnae in cnaes
        )


@dataclass(slots=True)
class CnpjScanStats:
    rows_read: int = 0
    rows_matched: int = 0
    rows_invalid: int = 0


@dataclass(slots=True)
class CnpjEstablishmentReader:
    source_path: Path
    filters: CnpjEstablishmentFilter
    member_name: str | None = None
    encoding: str = "latin1"
    strict: bool = True
    require_selective_filter: bool = True
    stats: CnpjScanStats = field(default_factory=CnpjScanStats, init=False)

    def __post_init__(self) -> None:
        self.source_path = Path(self.source_path)
        if self.require_selective_filter and not self.filters.is_selective:
            raise ValueError("At least one selective location or CNAE filter is required")

    def __iter__(self) -> Iterator[CnpjEstablishment]:
        self.stats = CnpjScanStats()
        with zipfile.ZipFile(self.source_path) as archive:
            member_name = self._resolve_member(archive)
            with archive.open(member_name) as raw_stream:
                text_stream = io.TextIOWrapper(raw_stream, encoding=self.encoding, newline="")
                for line_number, row in enumerate(csv.reader(text_stream, delimiter=";"), start=1):
                    if not row:
                        continue
                    self.stats.rows_read += 1
                    try:
                        establishment = self._parse_row(row, line_number)
                    except CnpjLayoutError:
                        self.stats.rows_invalid += 1
                        if self.strict:
                            raise
                        continue
                    if self.filters.matches(establishment):
                        self.stats.rows_matched += 1
                        yield establishment

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

    @staticmethod
    def _parse_row(row: list[str], line_number: int) -> CnpjEstablishment:
        if len(row) != ESTABLISHMENT_COLUMN_COUNT:
            raise CnpjLayoutError(
                f"Line {line_number}: expected {ESTABLISHMENT_COLUMN_COUNT} columns, "
                f"found {len(row)}"
            )
        secondary_cnaes = tuple(code.strip() for code in row[12].split(",") if code.strip())
        return CnpjEstablishment(
            cnpj_basico=row[0].strip(),
            cnpj_ordem=row[1].strip(),
            cnpj_dv=row[2].strip(),
            branch_identifier=row[3].strip(),
            trade_name=row[4].strip(),
            registration_status=row[5].strip(),
            registration_status_date=row[6].strip(),
            activity_started_on=row[10].strip(),
            primary_cnae=row[11].strip(),
            secondary_cnaes=secondary_cnaes,
            street_type=row[13].strip(),
            street=row[14].strip(),
            number=row[15].strip(),
            complement=row[16].strip(),
            district=row[17].strip(),
            postal_code=row[18].strip(),
            state=row[19].strip().upper(),
            municipality_code=row[20].strip(),
            phone=f"{row[21].strip()}{row[22].strip()}",
            secondary_phone=f"{row[23].strip()}{row[24].strip()}",
            email=row[27].strip().lower(),
        )
