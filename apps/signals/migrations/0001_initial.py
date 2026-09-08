import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("companies", "0002_initial"), ("sources", "0003_cnpj_manifest")]
    operations = [
        migrations.CreateModel(
            name="Signal",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("signal_type", models.SlugField(max_length=80)),
                ("product", models.CharField(choices=[("NONE", "Sem produto específico"), ("MES", "MES"), ("CMMS", "CMMS"), ("PULSE", "Pulse")], default="NONE", max_length=8)),
                ("source_url", models.URLField(blank=True, max_length=1000)),
                ("title", models.CharField(max_length=255)),
                ("evidence_excerpt", models.TextField(blank=True)),
                ("evidence_hash", models.CharField(max_length=64)),
                ("base_weight", models.DecimalField(decimal_places=3, default=0, max_digits=7)),
                ("applies_decay", models.BooleanField(default=True)),
                ("observed_at", models.DateTimeField()),
                ("detected_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("active", models.BooleanField(default=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="signals", to="companies.company")),
                ("source_record", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="signals", to="sources.sourcerecord")),
            ],
            options={
                "ordering": ("-observed_at", "signal_type"),
                "indexes": [models.Index(fields=["company", "active", "observed_at"], name="signal_company_active_idx"), models.Index(fields=["signal_type", "active"], name="signal_type_active_idx")],
                "constraints": [models.UniqueConstraint(fields=("company", "signal_type", "evidence_hash"), name="unique_company_signal_evidence")],
            },
        )
    ]
