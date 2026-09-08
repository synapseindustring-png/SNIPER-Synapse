import uuid

from django.db import models
from django.utils import timezone


class Job(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendente"
        RUNNING = "RUNNING", "Executando"
        RETRY_SCHEDULED = "RETRY_SCHEDULED", "Nova tentativa agendada"
        SUCCEEDED = "SUCCEEDED", "Concluído"
        FAILED = "FAILED", "Falhou"
        CANCELLED = "CANCELLED", "Cancelado"

    class Type(models.TextChoices):
        NOOP = "NOOP", "Teste"
        SYNC_CNPJ_SOURCE = "SYNC_CNPJ_SOURCE", "Sincronizar fonte CNPJ"
        DISCOVER_CNPJ = "DISCOVER_CNPJ", "Descobrir por CNPJ"
        DISCOVER_MAPS = "DISCOVER_MAPS", "Descobrir no Maps"
        ENRICH_MAPS = "ENRICH_MAPS", "Enriquecer pelo Maps"
        CRAWL_WEBSITE = "CRAWL_WEBSITE", "Visitar website"
        FIND_JOBS = "FIND_JOBS", "Buscar vagas"
        DETECT_SIGNALS = "DETECT_SIGNALS", "Detectar sinais"
        CALCULATE_SCORE = "CALCULATE_SCORE", "Calcular score"
        REFRESH_COMPANY = "REFRESH_COMPANY", "Atualizar empresa"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=40, choices=Type.choices)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING)
    payload = models.JSONField(default=dict, blank=True)
    idempotency_key = models.CharField(max_length=255, unique=True, null=True, blank=True)
    priority = models.SmallIntegerField(default=0)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=3)
    run_after = models.DateTimeField(default=timezone.now)
    lock_owner = models.CharField(max_length=120, blank=True)
    lock_expires_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    records_processed = models.PositiveBigIntegerField(default=0)
    records_success = models.PositiveBigIntegerField(default=0)
    records_failed = models.PositiveBigIntegerField(default=0)
    error_summary = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-priority", "run_after", "created_at")
        indexes = [
            models.Index(fields=("status", "run_after", "priority"), name="job_claim_idx"),
            models.Index(fields=("type", "created_at"), name="job_type_created_idx"),
        ]

    def __str__(self):
        return f"{self.type} · {self.status} · {self.id}"


class JobAttempt(models.Model):
    id = models.BigAutoField(primary_key=True)
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="attempts")
    attempt_number = models.PositiveSmallIntegerField()
    worker_id = models.CharField(max_length=120)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    succeeded = models.BooleanField(null=True)
    error_detail = models.TextField(blank=True)
    metrics = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("attempt_number",)
        constraints = [
            models.UniqueConstraint(
                fields=("job", "attempt_number"), name="unique_job_attempt_number"
            )
        ]

