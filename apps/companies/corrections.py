import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from urllib.parse import urlsplit
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.sources.models import FieldObservation, Source, SourceRecord

from .models import Company, CompanyCorrection


CORRECTABLE_FIELDS = (
    "legal_name",
    "trade_name",
    "company_type",
    "registration_status",
    "size_code",
    "legal_nature_code",
    "share_capital",
    "opened_on",
    "segment",
    "street_type",
    "street",
    "number",
    "complement",
    "district",
    "municipality",
    "municipality_code",
    "state",
    "postal_code",
    "phone",
    "email",
    "website",
    "commercial_status",
)


def _json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    return value


def _normalized_value(value) -> str:
    value = _json_value(value)
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _website_domain(website: str) -> str:
    if not website:
        return ""
    return (urlsplit(website).hostname or "").lower().removeprefix("www.")


@transaction.atomic
def correct_company(*, company: Company, changes: dict, justification: str, user):
    if not getattr(user, "is_staff", False):
        raise PermissionError("Somente usuários staff podem corrigir empresas.")
    justification = justification.strip()
    if len(justification) < 10:
        raise ValueError("A justificativa deve possuir ao menos 10 caracteres.")
    invalid_fields = set(changes).difference(CORRECTABLE_FIELDS)
    if invalid_fields:
        raise ValueError(f"Campos não permitidos: {', '.join(sorted(invalid_fields))}")

    locked_company = Company.objects.select_for_update().get(pk=company.pk)
    effective_changes = {
        field_name: value
        for field_name, value in changes.items()
        if getattr(locked_company, field_name) != value
    }
    if not effective_changes:
        raise ValueError("Nenhuma alteração efetiva foi informada.")

    source, _ = Source.objects.get_or_create(
        key="manual-correction",
        defaults={
            "name": "Correção administrativa",
            "adapter_path": "apps.companies.corrections",
            "enabled": True,
            "capabilities": {"mode": "manual", "audited": True},
        },
    )
    now = timezone.now()
    old_values = {
        field_name: _json_value(getattr(locked_company, field_name))
        for field_name in effective_changes
    }
    for field_name, value in effective_changes.items():
        setattr(locked_company, field_name, value)
    update_fields = [*effective_changes, "updated_at"]
    if "website" in effective_changes:
        locked_company.website_domain = _website_domain(locked_company.website)
        update_fields.append("website_domain")
    locked_company.save(update_fields=update_fields)

    corrections = []
    for field_name, value in effective_changes.items():
        new_value = _json_value(value)
        correction = CompanyCorrection.objects.create(
            company=locked_company,
            field_name=field_name,
            old_value=old_values[field_name],
            new_value=new_value,
            justification=justification,
            corrected_by=user,
        )
        payload = {
            "correction_id": str(correction.pk),
            "field": field_name,
            "old_value": old_values[field_name],
            "new_value": new_value,
            "justification": justification,
            "corrected_by": user.get_username(),
        }
        serialized_payload = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        source_record = SourceRecord.objects.create(
            source=source,
            external_id=f"correction:{correction.pk}",
            company=locked_company,
            payload=payload,
            payload_hash=hashlib.sha256(serialized_payload.encode()).hexdigest(),
            dataset_reference="manual",
            observed_at=now,
        )
        FieldObservation.objects.filter(
            company=locked_company,
            field_name=field_name,
            is_current=True,
        ).update(is_current=False)
        FieldObservation.objects.create(
            company=locked_company,
            source_record=source_record,
            field_name=field_name,
            value="" if new_value is None else new_value,
            normalized_value=_normalized_value(new_value),
            confidence=Decimal("1.0000"),
            observed_at=now,
            selected_at=now,
            is_current=True,
        )
        correction.source_record = source_record
        correction.save(update_fields=("source_record",))
        corrections.append(correction)

    return locked_company, corrections
