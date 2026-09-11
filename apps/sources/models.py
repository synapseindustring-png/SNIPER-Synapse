import uuid

from django.db import models


class Source(models.Model):
    key = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=160)
    adapter_path = models.CharField(max_length=255, blank=True)
    enabled = models.BooleanField(default=False)
    capabilities = models.JSONField(default=dict, blank=True)
    rate_limit = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class SourceRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey(Source, on_delete=models.PROTECT, related_name="records")
    external_id = models.CharField(max_length=255, blank=True)
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.PROTECT,
        related_name="source_records",
    )
    query_run = models.ForeignKey(
        "discovery.QueryRun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_records",
    )
    source_url = models.URLField(max_length=1000, blank=True)
    payload = models.JSONField(default=dict)
    payload_hash = models.CharField(max_length=64)
    dataset_reference = models.CharField(max_length=80, blank=True)
    observed_at = models.DateTimeField()
    collected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-collected_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("source", "external_id", "payload_hash"),
                condition=~models.Q(external_id=""),
                name="unique_external_source_payload",
            )
        ]
        indexes = [
            models.Index(fields=("source", "external_id"), name="source_external_id_idx"),
            models.Index(fields=("company", "observed_at"), name="source_company_seen_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.source.key} · {self.external_id or self.id}"


class FieldObservation(models.Model):
    id = models.BigAutoField(primary_key=True)
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="field_observations",
    )
    source_record = models.ForeignKey(
        SourceRecord,
        on_delete=models.CASCADE,
        related_name="field_observations",
    )
    field_name = models.CharField(max_length=80)
    value = models.JSONField()
    normalized_value = models.TextField(blank=True)
    confidence = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    observed_at = models.DateTimeField()
    is_current = models.BooleanField(default=True)
    selected_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("field_name", "-observed_at")
        indexes = [
            models.Index(fields=("company", "field_name", "is_current"), name="field_current_idx")
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("source_record", "field_name", "normalized_value"),
                name="unique_source_field_observation",
            )
        ]

    def __str__(self) -> str:
        return f"{self.company} · {self.field_name}"


class CnpjDataset(models.Model):
    class Status(models.TextChoices):
        DISCOVERED = "DISCOVERED", "Descoberta"
        READY = "READY", "Pronta"
        INVALID = "INVALID", "Inválida"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey(Source, on_delete=models.PROTECT, related_name="cnpj_datasets")
    reference = models.CharField(max_length=20)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DISCOVERED)
    is_current = models.BooleanField(default=False)
    discovered_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-reference",)
        constraints = [
            models.UniqueConstraint(fields=("source", "reference"), name="unique_cnpj_dataset"),
            models.UniqueConstraint(
                fields=("source",),
                condition=models.Q(is_current=True),
                name="one_current_cnpj_dataset_per_source",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.source.key} · {self.reference}"


class CnpjDatasetFile(models.Model):
    class Kind(models.TextChoices):
        ESTABLISHMENTS = "ESTABLISHMENTS", "Estabelecimentos"
        COMPANIES = "COMPANIES", "Empresas"
        SIMPLES = "SIMPLES", "Simples"

    dataset = models.ForeignKey(CnpjDataset, on_delete=models.CASCADE, related_name="files")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    part_number = models.PositiveSmallIntegerField(default=0)
    url = models.URLField(max_length=1000)
    size_bytes = models.PositiveBigIntegerField()
    etag = models.CharField(max_length=255, blank=True)
    checksum = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("kind", "part_number")
        constraints = [
            models.UniqueConstraint(
                fields=("dataset", "kind", "part_number"),
                name="unique_cnpj_dataset_file_part",
            ),
            models.CheckConstraint(condition=models.Q(size_bytes__gt=0), name="cnpj_file_size_gt_zero"),
        ]

    def __str__(self) -> str:
        return f"{self.dataset.reference} · {self.kind} {self.part_number}"


class CnpjCandidate(models.Model):
    """Bounded staging row for establishments selected by a discovery run."""

    id = models.BigAutoField(primary_key=True)
    query_run = models.ForeignKey(
        "discovery.QueryRun",
        on_delete=models.CASCADE,
        related_name="cnpj_candidates",
    )
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cnpj_candidates",
    )
    cnpj = models.CharField(max_length=14)
    cnpj_basico = models.CharField(max_length=8)
    establishment_payload = models.JSONField(default=dict)
    company_payload = models.JSONField(default=dict, blank=True)
    simples_payload = models.JSONField(default=dict, blank=True)
    company_matched = models.BooleanField(default=False)
    simples_matched = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("cnpj",)
        constraints = [
            models.UniqueConstraint(
                fields=("query_run", "cnpj"),
                name="unique_cnpj_candidate_per_run",
            )
        ]
        indexes = [
            models.Index(
                fields=("query_run", "cnpj_basico"),
                name="candidate_run_basic_idx",
            )
        ]

    def __str__(self) -> str:
        return f"{self.cnpj} · {self.query_run_id}"
