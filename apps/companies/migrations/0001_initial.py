import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="Company",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("cnpj", models.CharField(blank=True, max_length=32, null=True, unique=True)),
                ("legal_name", models.CharField(blank=True, max_length=255)),
                ("trade_name", models.CharField(blank=True, max_length=255)),
                ("company_type", models.CharField(choices=[("INDUSTRY", "Indústria"), ("CONSULTANCY", "Consultoria"), ("INTEGRATOR", "Integrador"), ("ENGINEERING", "Engenharia"), ("SERVICE_PROVIDER", "Prestador de serviços"), ("OTHER", "Outro")], default="OTHER", max_length=24)),
                ("registration_status", models.CharField(choices=[("ACTIVE", "Ativa"), ("INACTIVE", "Inativa"), ("SUSPENDED", "Suspensa"), ("UNKNOWN", "Desconhecida")], default="UNKNOWN", max_length=16)),
                ("size_code", models.CharField(blank=True, max_length=8)),
                ("legal_nature_code", models.CharField(blank=True, max_length=8)),
                ("share_capital", models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True)),
                ("opened_on", models.DateField(blank=True, null=True)),
                ("segment", models.CharField(blank=True, max_length=160)),
                ("street_type", models.CharField(blank=True, max_length=40)),
                ("street", models.CharField(blank=True, max_length=255)),
                ("number", models.CharField(blank=True, max_length=40)),
                ("complement", models.CharField(blank=True, max_length=160)),
                ("district", models.CharField(blank=True, max_length=160)),
                ("municipality", models.CharField(blank=True, max_length=160)),
                ("municipality_code", models.CharField(blank=True, max_length=16)),
                ("state", models.CharField(blank=True, max_length=2)),
                ("postal_code", models.CharField(blank=True, max_length=16)),
                ("latitude", models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ("longitude", models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ("phone", models.CharField(blank=True, max_length=32)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("website", models.URLField(blank=True, max_length=500)),
                ("website_domain", models.CharField(blank=True, db_index=True, max_length=255)),
                ("commercial_status", models.CharField(choices=[("NEW", "Nova"), ("REVIEWED", "Revisada"), ("CONTACT_PENDING", "Contato pendente"), ("CONTACTED", "Contatada"), ("MEETING", "Reunião"), ("OPPORTUNITY", "Oportunidade"), ("CUSTOMER", "Cliente"), ("LOST", "Perdida"), ("DO_NOT_CONTACT", "Não contatar")], default="NEW", max_length=24)),
                ("last_enriched_at", models.DateTimeField(blank=True, null=True)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ("trade_name", "legal_name", "cnpj"),
                "indexes": [models.Index(fields=["company_type", "state"], name="company_type_state_idx"), models.Index(fields=["registration_status", "commercial_status"], name="company_status_idx"), models.Index(fields=["municipality_code", "state"], name="company_city_state_idx")],
            },
        ),
        migrations.CreateModel(
            name="CompanyCnae",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=7)),
                ("description", models.CharField(blank=True, max_length=255)),
                ("is_primary", models.BooleanField(default=False)),
                ("observed_at", models.DateTimeField()),
                ("company", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="cnaes", to="companies.company")),
            ],
            options={"ordering": ("-is_primary", "code")},
        ),
    ]
