import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("companies", "0002_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="RuleSet",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=160)),
                ("target", models.CharField(choices=[("INDUSTRY", "Indústria"), ("PARTNER", "Parceiro")], max_length=16)),
                ("version", models.PositiveIntegerField()),
                ("status", models.CharField(choices=[("DRAFT", "Rascunho"), ("PUBLISHED", "Publicado"), ("RETIRED", "Descontinuado")], default="DRAFT", max_length=16)),
                ("formula", models.JSONField(default=dict)),
                ("thresholds", models.JSONField(default=list)),
                ("tie_order", models.JSONField(blank=True, default=list)),
                ("active", models.BooleanField(default=False)),
                ("description", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="rule_sets", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("target", "-version")},
        ),
        migrations.CreateModel(
            name="ScoreSnapshot",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("as_of", models.DateTimeField()),
                ("dimensions", models.JSONField(default=dict)),
                ("priority", models.DecimalField(decimal_places=3, max_digits=7)),
                ("calculated_classification", models.CharField(max_length=32)),
                ("best_product", models.CharField(blank=True, max_length=16)),
                ("tied_products", models.JSONField(blank=True, default=list)),
                ("formula_detail", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="score_snapshots", to="companies.company")),
                ("rule_set", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="snapshots", to="scoring.ruleset")),
            ],
            options={"ordering": ("-as_of", "-created_at")},
        ),
        migrations.CreateModel(
            name="ScoreOverride",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("classification", models.CharField(blank=True, max_length=32)),
                ("priority", models.DecimalField(blank=True, decimal_places=3, max_digits=7, null=True)),
                ("reason", models.TextField()),
                ("active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="score_overrides", to="companies.company")),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="score_overrides", to=settings.AUTH_USER_MODEL)),
                ("snapshot", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="overrides", to="scoring.scoresnapshot")),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.CreateModel(
            name="ScoringRule",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("key", models.SlugField(max_length=100)),
                ("name", models.CharField(max_length=180)),
                ("description", models.TextField(blank=True)),
                ("dimension", models.CharField(choices=[("ICP", "ICP"), ("MES", "MES Fit"), ("CMMS", "CMMS Fit"), ("PULSE", "Pulse Fit"), ("INTENT", "Intent"), ("PARTNER_FIT", "Partner Fit"), ("CHANNEL", "Channel Potential"), ("ACTIVITY", "Partner Activity"), ("CONFLICT", "Conflict Penalty")], max_length=20)),
                ("condition", models.JSONField(default=dict)),
                ("points", models.DecimalField(decimal_places=3, max_digits=7)),
                ("decay_policy", models.CharField(choices=[("NONE", "Sem decay"), ("AGE_BUCKETS", "Faixas por idade")], default="NONE", max_length=16)),
                ("decay_curve", models.JSONField(blank=True, default=list)),
                ("critical_outcome", models.CharField(blank=True, choices=[("", "Nenhum"), ("DISQUALIFIED", "Desqualificada"), ("CONFLICT", "Conflito")], max_length=16)),
                ("group_key", models.SlugField(blank=True, max_length=80)),
                ("group_cap", models.DecimalField(blank=True, decimal_places=3, max_digits=7, null=True)),
                ("max_occurrences", models.PositiveSmallIntegerField(default=1)),
                ("active", models.BooleanField(default=True)),
                ("order", models.PositiveSmallIntegerField(default=0)),
                ("rule_set", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="rules", to="scoring.ruleset")),
            ],
            options={"ordering": ("order", "key")},
        ),
        migrations.CreateModel(
            name="ScoreContribution",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("dimension", models.CharField(choices=[("ICP", "ICP"), ("MES", "MES Fit"), ("CMMS", "CMMS Fit"), ("PULSE", "Pulse Fit"), ("INTENT", "Intent"), ("PARTNER_FIT", "Partner Fit"), ("CHANNEL", "Channel Potential"), ("ACTIVITY", "Partner Activity"), ("CONFLICT", "Conflict Penalty")], max_length=20)),
                ("base_points", models.DecimalField(decimal_places=3, max_digits=7)),
                ("decay_multiplier", models.DecimalField(decimal_places=5, default=1, max_digits=6)),
                ("effective_points", models.DecimalField(decimal_places=3, max_digits=7)),
                ("evidence", models.JSONField(default=dict)),
                ("observed_at", models.DateTimeField(blank=True, null=True)),
                ("rule", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="contributions", to="scoring.scoringrule")),
                ("snapshot", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="contributions", to="scoring.scoresnapshot")),
            ],
            options={"ordering": ("dimension", "-effective_points", "rule__order")},
        ),
        migrations.AddConstraint(model_name="ruleset", constraint=models.UniqueConstraint(fields=("target", "version"), name="unique_rule_set_version")),
        migrations.AddConstraint(model_name="ruleset", constraint=models.UniqueConstraint(condition=models.Q(("active", True)), fields=("target",), name="one_active_rule_set")),
        migrations.AddIndex(model_name="scoresnapshot", index=models.Index(fields=["company", "as_of"], name="score_company_asof_idx")),
        migrations.AddIndex(model_name="scoresnapshot", index=models.Index(fields=["calculated_classification", "priority"], name="score_class_priority_idx")),
        migrations.AddConstraint(model_name="scoreoverride", constraint=models.UniqueConstraint(condition=models.Q(("active", True)), fields=("company",), name="one_active_score_override")),
        migrations.AddConstraint(model_name="scoringrule", constraint=models.UniqueConstraint(fields=("rule_set", "key"), name="unique_rule_key_per_set")),
    ]
