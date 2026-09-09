import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("companies", "0002_initial"),
        ("crawler", "0002_seed_website_source"),
        ("sources", "0003_cnpj_manifest"),
    ]

    operations = [
        migrations.CreateModel(
            name="JobPosting",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("fingerprint", models.CharField(max_length=64)),
                ("external_id", models.CharField(blank=True, max_length=500)),
                ("title", models.CharField(max_length=500)),
                ("description", models.TextField(blank=True)),
                ("location", models.CharField(blank=True, max_length=500)),
                ("employment_type", models.CharField(blank=True, max_length=120)),
                ("url", models.URLField(blank=True, max_length=1000)),
                ("published_on", models.DateField(blank=True, null=True)),
                ("valid_through", models.DateField(blank=True, null=True)),
                ("first_seen_at", models.DateTimeField()),
                ("last_seen_at", models.DateTimeField()),
                ("active", models.BooleanField(default=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="job_postings", to="companies.company")),
                ("source_record", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="job_postings", to="sources.sourcerecord")),
            ],
            options={
                "ordering": ("-published_on", "-last_seen_at", "title"),
                "indexes": [models.Index(fields=["company", "active", "published_on"], name="job_company_active_idx")],
                "constraints": [models.UniqueConstraint(fields=("company", "fingerprint"), name="unique_company_job_fingerprint")],
            },
        )
    ]
