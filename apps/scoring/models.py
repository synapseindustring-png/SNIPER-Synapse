import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class RuleSet(models.Model):
    class Target(models.TextChoices):
        INDUSTRY = "INDUSTRY", "Indústria"
        PARTNER = "PARTNER", "Parceiro"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Rascunho"
        PUBLISHED = "PUBLISHED", "Publicado"
        RETIRED = "RETIRED", "Descontinuado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    target = models.CharField(max_length=16, choices=Target.choices)
    version = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    formula = models.JSONField(default=dict)
    thresholds = models.JSONField(default=list)
    tie_order = models.JSONField(default=list, blank=True)
    active = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="rule_sets",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("target", "-version")
        constraints = [
            models.UniqueConstraint(fields=("target", "version"), name="unique_rule_set_version"),
            models.UniqueConstraint(
                fields=("target",), condition=models.Q(active=True), name="one_active_rule_set"
            ),
        ]

    def __str__(self):
        return f"{self.get_target_display()} · v{self.version}"


class ScoringRule(models.Model):
    class Dimension(models.TextChoices):
        ICP = "ICP", "ICP"
        MES = "MES", "MES Fit"
        CMMS = "CMMS", "CMMS Fit"
        PULSE = "PULSE", "Pulse Fit"
        INTENT = "INTENT", "Intent"
        PARTNER_FIT = "PARTNER_FIT", "Partner Fit"
        CHANNEL = "CHANNEL", "Channel Potential"
        ACTIVITY = "ACTIVITY", "Partner Activity"
        CONFLICT = "CONFLICT", "Conflict Penalty"

    class DecayPolicy(models.TextChoices):
        NONE = "NONE", "Sem decay"
        AGE_BUCKETS = "AGE_BUCKETS", "Faixas por idade"

    class CriticalOutcome(models.TextChoices):
        NONE = "", "Nenhum"
        DISQUALIFIED = "DISQUALIFIED", "Desqualificada"
        CONFLICT = "CONFLICT", "Conflito"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rule_set = models.ForeignKey(RuleSet, on_delete=models.PROTECT, related_name="rules")
    key = models.SlugField(max_length=100)
    name = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    dimension = models.CharField(max_length=20, choices=Dimension.choices)
    condition = models.JSONField(default=dict)
    points = models.DecimalField(max_digits=7, decimal_places=3)
    decay_policy = models.CharField(max_length=16, choices=DecayPolicy.choices, default=DecayPolicy.NONE)
    decay_curve = models.JSONField(default=list, blank=True)
    critical_outcome = models.CharField(max_length=16, choices=CriticalOutcome.choices, blank=True)
    group_key = models.SlugField(max_length=80, blank=True)
    group_cap = models.DecimalField(max_digits=7, decimal_places=3, null=True, blank=True)
    max_occurrences = models.PositiveSmallIntegerField(default=1)
    active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("order", "key")
        constraints = [
            models.UniqueConstraint(fields=("rule_set", "key"), name="unique_rule_key_per_set")
        ]

    def __str__(self):
        return f"{self.rule_set} · {self.name}"


class ScoreSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.PROTECT, related_name="score_snapshots"
    )
    rule_set = models.ForeignKey(RuleSet, on_delete=models.PROTECT, related_name="snapshots")
    as_of = models.DateTimeField()
    dimensions = models.JSONField(default=dict)
    priority = models.DecimalField(max_digits=7, decimal_places=3)
    calculated_classification = models.CharField(max_length=32)
    best_product = models.CharField(max_length=16, blank=True)
    tied_products = models.JSONField(default=list, blank=True)
    formula_detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-as_of", "-created_at")
        indexes = [
            models.Index(fields=("company", "as_of"), name="score_company_asof_idx"),
            models.Index(fields=("calculated_classification", "priority"), name="score_class_priority_idx"),
        ]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Snapshots de score são imutáveis.")
        return super().save(*args, **kwargs)


class ScoreContribution(models.Model):
    id = models.BigAutoField(primary_key=True)
    snapshot = models.ForeignKey(
        ScoreSnapshot, on_delete=models.CASCADE, related_name="contributions"
    )
    rule = models.ForeignKey(ScoringRule, on_delete=models.PROTECT, related_name="contributions")
    dimension = models.CharField(max_length=20, choices=ScoringRule.Dimension.choices)
    base_points = models.DecimalField(max_digits=7, decimal_places=3)
    decay_multiplier = models.DecimalField(max_digits=6, decimal_places=5, default=1)
    effective_points = models.DecimalField(max_digits=7, decimal_places=3)
    evidence = models.JSONField(default=dict)
    observed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("dimension", "-effective_points", "rule__order")


class ScoreOverride(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "companies.Company", on_delete=models.CASCADE, related_name="score_overrides"
    )
    snapshot = models.ForeignKey(
        ScoreSnapshot, on_delete=models.PROTECT, related_name="overrides"
    )
    classification = models.CharField(max_length=32, blank=True)
    priority = models.DecimalField(max_digits=7, decimal_places=3, null=True, blank=True)
    reason = models.TextField()
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="score_overrides"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("company",), condition=models.Q(active=True), name="one_active_score_override"
            )
        ]
