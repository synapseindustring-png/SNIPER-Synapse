import uuid

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("companies", "0002_initial"),
        ("sources", "0006_seed_manual_correction_source"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CompanyCorrection",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("field_name", models.CharField(max_length=80)),
                ("old_value", models.JSONField(blank=True, null=True)),
                ("new_value", models.JSONField(blank=True, null=True)),
                ("justification", models.TextField(max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=models.deletion.PROTECT,
                        related_name="corrections",
                        to="companies.company",
                    ),
                ),
                (
                    "corrected_by",
                    models.ForeignKey(
                        on_delete=models.deletion.PROTECT,
                        related_name="company_corrections",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "source_record",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=models.deletion.PROTECT,
                        related_name="company_correction",
                        to="sources.sourcerecord",
                    ),
                ),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.AddIndex(
            model_name="companycorrection",
            index=models.Index(
                fields=["company", "field_name", "created_at"],
                name="correction_field_idx",
            ),
        ),
    ]
