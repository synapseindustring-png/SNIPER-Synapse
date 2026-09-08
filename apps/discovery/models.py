import hashlib
import json
import uuid
from collections.abc import Mapping

from django.conf import settings
from django.db import models


QUERY_SCHEMA_VERSION = 1


def _normalize_value(key: str, value):
    if isinstance(value, Mapping):
        return {
            child_key: normalized
            for child_key in sorted(value)
            if (normalized := _normalize_value(child_key, value[child_key])) not in (None, "", [], {})
        }
    if isinstance(value, list):
        normalized = [_normalize_value(key, item) for item in value]
        normalized = [item for item in normalized if item not in (None, "", [], {})]
        return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False))
    if isinstance(value, str):
        value = " ".join(value.strip().split())
        if key in {"state", "states", "uf", "ufs"}:
            return value.upper()
        if key in {"cnpj", "cnae", "cnaes", "municipality_code", "municipality_codes"}:
            return "".join(character for character in value if character.isalnum())
        return value
    return value


def normalize_filters(filters: Mapping) -> dict:
    return _normalize_value("", filters)


def fingerprint_filters(filters: Mapping, schema_version: int = QUERY_SCHEMA_VERSION) -> str:
    canonical = json.dumps(
        {"schema_version": schema_version, "filters": normalize_filters(filters)},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


class DiscoveryQuery(models.Model):
    class EntityTarget(models.TextChoices):
        INDUSTRY = "INDUSTRY", "Indústria"
        PARTNER = "PARTNER", "Parceiro"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    entity_target = models.CharField(max_length=16, choices=EntityTarget.choices)
    filters = models.JSONField(default=dict)
    normalized_filters = models.JSONField(default=dict, editable=False)
    fingerprint = models.CharField(max_length=64, db_index=True, editable=False)
    schema_version = models.PositiveSmallIntegerField(default=QUERY_SCHEMA_VERSION, editable=False)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="discovery_queries",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("created_by", "entity_target", "fingerprint"),
                name="unique_user_query_fingerprint",
            )
        ]

    def save(self, *args, **kwargs):
        self.normalized_filters = normalize_filters(self.filters)
        self.fingerprint = fingerprint_filters(self.filters, self.schema_version)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


class QueryRun(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendente"
        RUNNING = "RUNNING", "Executando"
        SUCCEEDED = "SUCCEEDED", "Concluída"
        PARTIAL = "PARTIAL", "Parcial"
        FAILED = "FAILED", "Falhou"
        CANCELLED = "CANCELLED", "Cancelada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    query = models.ForeignKey(DiscoveryQuery, on_delete=models.PROTECT, related_name="runs")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    dataset_reference = models.CharField(max_length=80, blank=True)
    coverage = models.JSONField(default=dict, blank=True)
    records_processed = models.PositiveBigIntegerField(default=0)
    records_matched = models.PositiveBigIntegerField(default=0)
    records_failed = models.PositiveBigIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="query_runs",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.query.name} · {self.status}"


class QueryResult(models.Model):
    query_run = models.ForeignKey(QueryRun, on_delete=models.CASCADE, related_name="results")
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.PROTECT,
        related_name="query_results",
    )
    source = models.ForeignKey(
        "sources.Source",
        on_delete=models.PROTECT,
        related_name="query_results",
    )
    rank = models.PositiveIntegerField(null=True, blank=True)
    matched_filters = models.JSONField(default=dict, blank=True)
    is_new_company = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("rank", "created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("query_run", "company"), name="unique_query_run_company"
            )
        ]


class SourceCoverage(models.Model):
    source = models.ForeignKey(
        "sources.Source",
        on_delete=models.CASCADE,
        related_name="coverage_entries",
    )
    dataset_reference = models.CharField(max_length=80)
    scope = models.JSONField(default=dict)
    scope_hash = models.CharField(max_length=64)
    record_count = models.PositiveBigIntegerField(default=0)
    completed_at = models.DateTimeField()
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-completed_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("source", "dataset_reference", "scope_hash"),
                name="unique_source_dataset_scope",
            )
        ]
