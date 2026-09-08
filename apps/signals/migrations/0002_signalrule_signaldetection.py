import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("signals", "0001_initial")]
    operations = [
        migrations.CreateModel(
            name="SignalRule",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("key", models.SlugField(max_length=100)),
                ("version", models.PositiveIntegerField(default=1)),
                ("name", models.CharField(max_length=180)),
                ("description", models.TextField(blank=True)),
                ("signal_type", models.SlugField(max_length=80)),
                ("product", models.CharField(choices=[("NONE", "Sem produto específico"), ("MES", "MES"), ("CMMS", "CMMS"), ("PULSE", "Pulse")], default="NONE", max_length=8)),
                ("keywords", models.JSONField(default=list)),
                ("match_mode", models.CharField(choices=[("ANY", "Qualquer termo"), ("ALL", "Todos os termos")], default="ANY", max_length=8)),
                ("source_fields", models.JSONField(default=list)),
                ("base_weight", models.DecimalField(decimal_places=3, default=0, max_digits=7)),
                ("applies_decay", models.BooleanField(default=True)),
                ("expires_after_days", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ("key", "-version"),
                "constraints": [
                    models.UniqueConstraint(fields=("key", "version"), name="unique_signal_rule_version"),
                    models.UniqueConstraint(condition=models.Q(("active", True)), fields=("key",), name="one_active_signal_rule"),
                ],
            },
        ),
        migrations.CreateModel(
            name="SignalDetection",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("field_name", models.CharField(max_length=120)),
                ("matched_terms", models.JSONField(default=list)),
                ("evidence_excerpt", models.TextField()),
                ("detected_at", models.DateTimeField(auto_now_add=True)),
                ("rule", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="detections", to="signals.signalrule")),
                ("signal", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="detections", to="signals.signal")),
                ("source_record", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="signal_detections", to="sources.sourcerecord")),
            ],
            options={
                "ordering": ("-detected_at",),
                "constraints": [models.UniqueConstraint(fields=("signal", "rule", "source_record", "field_name"), name="unique_signal_detection_evidence")],
            },
        ),
    ]
