import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("companies", "0002_initial"),
        ("crawler", "0003_jobposting"),
        ("sources", "0003_cnpj_manifest"),
    ]
    operations = [
        migrations.CreateModel(
            name="JobPostingReview",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("candidate_fingerprint", models.CharField(max_length=64)),
                ("external_id", models.CharField(blank=True, max_length=500)),
                ("company_name", models.CharField(blank=True, max_length=500)),
                ("company_domain", models.CharField(blank=True, max_length=255)),
                ("title", models.CharField(max_length=500)),
                ("location", models.CharField(blank=True, max_length=500)),
                ("url", models.URLField(blank=True, max_length=1000)),
                ("reason", models.CharField(max_length=500)),
                ("status", models.CharField(choices=[("PENDING", "Pendente"), ("MATCHED", "Vinculada"), ("DISMISSED", "Descartada")], default="PENDING", max_length=16)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("first_seen_at", models.DateTimeField()),
                ("last_seen_at", models.DateTimeField()),
                ("source", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="job_posting_reviews", to="sources.source")),
                ("suggested_company", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="job_posting_reviews", to="companies.company")),
            ],
            options={
                "ordering": ("status", "-last_seen_at"),
                "indexes": [models.Index(fields=["status", "last_seen_at"], name="job_review_status_idx")],
                "constraints": [models.UniqueConstraint(fields=("source", "candidate_fingerprint"), name="unique_source_job_review_candidate")],
            },
        )
    ]
