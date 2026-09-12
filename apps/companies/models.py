import uuid

from django.conf import settings
from django.db import models


class Company(models.Model):
    class Type(models.TextChoices):
        INDUSTRY = "INDUSTRY", "Indústria"
        CONSULTANCY = "CONSULTANCY", "Consultoria"
        INTEGRATOR = "INTEGRATOR", "Integrador"
        ENGINEERING = "ENGINEERING", "Engenharia"
        SERVICE_PROVIDER = "SERVICE_PROVIDER", "Prestador de serviços"
        OTHER = "OTHER", "Outro"

    class RegistrationStatus(models.TextChoices):
        ACTIVE = "ACTIVE", "Ativa"
        INACTIVE = "INACTIVE", "Inativa"
        SUSPENDED = "SUSPENDED", "Suspensa"
        UNKNOWN = "UNKNOWN", "Desconhecida"

    class CommercialStatus(models.TextChoices):
        NEW = "NEW", "Nova"
        REVIEWED = "REVIEWED", "Revisada"
        CONTACT_PENDING = "CONTACT_PENDING", "Contato pendente"
        CONTACTED = "CONTACTED", "Contatada"
        MEETING = "MEETING", "Reunião"
        OPPORTUNITY = "OPPORTUNITY", "Oportunidade"
        CUSTOMER = "CUSTOMER", "Cliente"
        LOST = "LOST", "Perdida"
        DO_NOT_CONTACT = "DO_NOT_CONTACT", "Não contatar"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cnpj = models.CharField(max_length=32, unique=True, null=True, blank=True)
    legal_name = models.CharField(max_length=255, blank=True)
    trade_name = models.CharField(max_length=255, blank=True)
    company_type = models.CharField(max_length=24, choices=Type.choices, default=Type.OTHER)
    registration_status = models.CharField(
        max_length=16,
        choices=RegistrationStatus.choices,
        default=RegistrationStatus.UNKNOWN,
    )
    size_code = models.CharField(max_length=8, blank=True)
    legal_nature_code = models.CharField(max_length=8, blank=True)
    share_capital = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    opened_on = models.DateField(null=True, blank=True)
    segment = models.CharField(max_length=160, blank=True)
    street_type = models.CharField(max_length=40, blank=True)
    street = models.CharField(max_length=255, blank=True)
    number = models.CharField(max_length=40, blank=True)
    complement = models.CharField(max_length=160, blank=True)
    district = models.CharField(max_length=160, blank=True)
    municipality = models.CharField(max_length=160, blank=True)
    municipality_code = models.CharField(max_length=16, blank=True)
    state = models.CharField(max_length=2, blank=True)
    postal_code = models.CharField(max_length=16, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(max_length=500, blank=True)
    website_domain = models.CharField(max_length=255, blank=True, db_index=True)
    commercial_status = models.CharField(
        max_length=24,
        choices=CommercialStatus.choices,
        default=CommercialStatus.NEW,
    )
    last_enriched_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("trade_name", "legal_name", "cnpj")
        indexes = [
            models.Index(fields=("company_type", "state"), name="company_type_state_idx"),
            models.Index(
                fields=("registration_status", "commercial_status"),
                name="company_status_idx",
            ),
            models.Index(fields=("municipality_code", "state"), name="company_city_state_idx"),
        ]

    def __str__(self) -> str:
        return self.trade_name or self.legal_name or self.cnpj or str(self.id)


class CompanyCnae(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="cnaes")
    code = models.CharField(max_length=7)
    description = models.CharField(max_length=255, blank=True)
    is_primary = models.BooleanField(default=False)
    source_record = models.ForeignKey(
        "sources.SourceRecord",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_cnaes",
    )
    observed_at = models.DateTimeField()

    class Meta:
        ordering = ("-is_primary", "code")
        constraints = [
            models.UniqueConstraint(fields=("company", "code"), name="unique_company_cnae"),
            models.UniqueConstraint(
                fields=("company",),
                condition=models.Q(is_primary=True),
                name="one_primary_cnae_per_company",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} · {self.company}"


class CompanyCorrection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="corrections",
    )
    field_name = models.CharField(max_length=80)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    justification = models.TextField(max_length=500)
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="company_corrections",
    )
    source_record = models.OneToOneField(
        "sources.SourceRecord",
        on_delete=models.PROTECT,
        related_name="company_correction",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=("company", "field_name", "created_at"),
                name="correction_field_idx",
            )
        ]

    def __str__(self) -> str:
        return f"{self.company} · {self.field_name} · {self.created_at:%Y-%m-%d}"

    @property
    def field_label(self) -> str:
        return self.company._meta.get_field(self.field_name).verbose_name.capitalize()
