import uuid

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("companies", "0001_initial"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="QueryRun",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(choices=[("PENDING", "Pendente"), ("RUNNING", "Executando"), ("SUCCEEDED", "Concluída"), ("PARTIAL", "Parcial"), ("FAILED", "Falhou"), ("CANCELLED", "Cancelada")], default="PENDING", max_length=16)),
                ("dataset_reference", models.CharField(blank=True, max_length=80)),
                ("coverage", models.JSONField(blank=True, default=dict)),
                ("records_processed", models.PositiveBigIntegerField(default=0)),
                ("records_matched", models.PositiveBigIntegerField(default=0)),
                ("records_failed", models.PositiveBigIntegerField(default=0)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.CreateModel(
            name="SourceCoverage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("dataset_reference", models.CharField(max_length=80)),
                ("scope", models.JSONField(default=dict)),
                ("scope_hash", models.CharField(max_length=64)),
                ("record_count", models.PositiveBigIntegerField(default=0)),
                ("completed_at", models.DateTimeField()),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"ordering": ("-completed_at",)},
        ),
        migrations.CreateModel(
            name="DiscoveryQuery",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=160)),
                ("entity_target", models.CharField(choices=[("INDUSTRY", "Indústria"), ("PARTNER", "Parceiro")], max_length=16)),
                ("filters", models.JSONField(default=dict)),
                ("normalized_filters", models.JSONField(default=dict, editable=False)),
                ("fingerprint", models.CharField(db_index=True, editable=False, max_length=64)),
                ("schema_version", models.PositiveSmallIntegerField(default=1, editable=False)),
                ("active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(on_delete=models.deletion.PROTECT, related_name="discovery_queries", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.CreateModel(
            name="QueryResult",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rank", models.PositiveIntegerField(blank=True, null=True)),
                ("matched_filters", models.JSONField(blank=True, default=dict)),
                ("is_new_company", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("company", models.ForeignKey(on_delete=models.deletion.PROTECT, related_name="query_results", to="companies.company")),
            ],
            options={"ordering": ("rank", "created_at")},
        ),
    ]
