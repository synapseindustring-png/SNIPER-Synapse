import hashlib
import json
from dataclasses import asdict, dataclass

from django.db import transaction

from apps.companies.models import Company, CompanyCnae
from apps.discovery.models import QueryResult, QueryRun
from apps.sources.models import FieldObservation, Source, SourceRecord

from .establishments import CnpjEstablishment


@dataclass(frozen=True, slots=True)
class IngestionOutcome:
    company: Company
    source_record: SourceRecord
    company_created: bool
    source_record_created: bool


def _status_from_receita(value: str) -> str:
    return {
        "02": Company.RegistrationStatus.ACTIVE,
        "03": Company.RegistrationStatus.SUSPENDED,
    }.get(value, Company.RegistrationStatus.INACTIVE)


def _payload(establishment: CnpjEstablishment) -> dict:
    return asdict(establishment)


def _payload_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


@transaction.atomic
def ingest_establishment(
    establishment: CnpjEstablishment,
    *,
    source: Source,
    observed_at,
    dataset_reference: str,
    query_run: QueryRun | None = None,
) -> IngestionOutcome:
    canonical_fields = {
        "trade_name": establishment.trade_name,
        "company_type": Company.Type.INDUSTRY,
        "registration_status": _status_from_receita(establishment.registration_status),
        "street_type": establishment.street_type,
        "street": establishment.street,
        "number": establishment.number,
        "complement": establishment.complement,
        "district": establishment.district,
        "municipality_code": establishment.municipality_code,
        "state": establishment.state,
        "postal_code": establishment.postal_code,
        "phone": establishment.phone,
        "email": establishment.email,
    }
    company, company_created = Company.objects.get_or_create(
        cnpj=establishment.cnpj,
        defaults=canonical_fields,
    )
    if not company_created:
        changed_fields = []
        for field_name, value in canonical_fields.items():
            if value and getattr(company, field_name) != value:
                setattr(company, field_name, value)
                changed_fields.append(field_name)
        if changed_fields:
            company.save(update_fields=(*changed_fields, "updated_at"))

    payload = _payload(establishment)
    source_record, source_record_created = SourceRecord.objects.get_or_create(
        source=source,
        external_id=establishment.cnpj,
        payload_hash=_payload_hash(payload),
        defaults={
            "company": company,
            "query_run": query_run,
            "payload": payload,
            "dataset_reference": dataset_reference,
            "observed_at": observed_at,
        },
    )
    if source_record_created:
        observations = [
            FieldObservation(
                company=company,
                source_record=source_record,
                field_name=field_name,
                value=value,
                normalized_value=str(value),
                observed_at=observed_at,
            )
            for field_name, value in canonical_fields.items()
            if value not in (None, "")
        ]
        FieldObservation.objects.bulk_create(observations)

    CompanyCnae.objects.filter(company=company, is_primary=True).exclude(
        code=establishment.primary_cnae
    ).update(is_primary=False)
    primary_cnae, _ = CompanyCnae.objects.update_or_create(
        company=company,
        code=establishment.primary_cnae,
        defaults={
            "is_primary": True,
            "source_record": source_record,
            "observed_at": observed_at,
        },
    )
    for code in establishment.secondary_cnaes:
        if code == primary_cnae.code:
            continue
        CompanyCnae.objects.update_or_create(
            company=company,
            code=code,
            defaults={
                "is_primary": False,
                "source_record": source_record,
                "observed_at": observed_at,
            },
        )

    if query_run:
        QueryResult.objects.get_or_create(
            query_run=query_run,
            company=company,
            defaults={"source": source, "is_new_company": company_created},
        )

    return IngestionOutcome(
        company=company,
        source_record=source_record,
        company_created=company_created,
        source_record_created=source_record_created,
    )
