import uuid

from django.db import models


class Signal(models.Model):
    class Product(models.TextChoices):
        NONE = "NONE", "Sem produto específico"
        MES = "MES", "MES"
        CMMS = "CMMS", "CMMS"
        PULSE = "PULSE", "Pulse"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.CASCADE, related_name="signals"
    )
    signal_type = models.SlugField(max_length=80)
    product = models.CharField(max_length=8, choices=Product.choices, default=Product.NONE)
    source_record = models.ForeignKey(
        "sources.SourceRecord",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="signals",
    )
    source_url = models.URLField(max_length=1000, blank=True)
    title = models.CharField(max_length=255)
    evidence_excerpt = models.TextField(blank=True)
    evidence_hash = models.CharField(max_length=64)
    base_weight = models.DecimalField(max_digits=7, decimal_places=3, default=0)
    applies_decay = models.BooleanField(default=True)
    observed_at = models.DateTimeField()
    detected_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-observed_at", "signal_type")
        constraints = [
            models.UniqueConstraint(
                fields=("company", "signal_type", "evidence_hash"),
                name="unique_company_signal_evidence",
            )
        ]
        indexes = [
            models.Index(fields=("company", "active", "observed_at"), name="signal_company_active_idx"),
            models.Index(fields=("signal_type", "active"), name="signal_type_active_idx"),
        ]

    def __str__(self):
        return f"{self.signal_type} · {self.company}"
