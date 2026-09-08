import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("companies", "0001_initial"), ("discovery", "0001_initial")]
    operations = [
        migrations.CreateModel(
            name="Source",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.SlugField(max_length=80, unique=True)),
                ("name", models.CharField(max_length=160)),
                ("adapter_path", models.CharField(blank=True, max_length=255)),
                ("enabled", models.BooleanField(default=False)),
                ("capabilities", models.JSONField(blank=True, default=dict)),
                ("rate_limit", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="SourceRecord",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("external_id", models.CharField(blank=True, max_length=255)),
                ("source_url", models.URLField(blank=True, max_length=1000)),
                ("payload", models.JSONField(default=dict)),
                ("payload_hash", models.CharField(max_length=64)),
                ("dataset_reference", models.CharField(blank=True, max_length=80)),
                ("observed_at", models.DateTimeField()),
                ("collected_at", models.DateTimeField(auto_now_add=True)),
                ("company", models.ForeignKey(on_delete=models.deletion.PROTECT, related_name="source_records", to="companies.company")),
                ("query_run", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="source_records", to="discovery.queryrun")),
                ("source", models.ForeignKey(on_delete=models.deletion.PROTECT, related_name="records", to="sources.source")),
            ],
            options={"ordering": ("-collected_at",)},
        ),
        migrations.CreateModel(
            name="FieldObservation",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("field_name", models.CharField(max_length=80)),
                ("value", models.JSONField()),
                ("normalized_value", models.TextField(blank=True)),
                ("confidence", models.DecimalField(blank=True, decimal_places=4, max_digits=5, null=True)),
                ("observed_at", models.DateTimeField()),
                ("is_current", models.BooleanField(default=True)),
                ("selected_at", models.DateTimeField(blank=True, null=True)),
                ("company", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="field_observations", to="companies.company")),
                ("source_record", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="field_observations", to="sources.sourcerecord")),
            ],
            options={"ordering": ("field_name", "-observed_at")},
        ),
        migrations.AddIndex(model_name="sourcerecord", index=models.Index(fields=["source", "external_id"], name="source_external_id_idx")),
        migrations.AddIndex(model_name="sourcerecord", index=models.Index(fields=["company", "observed_at"], name="source_company_seen_idx")),
        migrations.AddConstraint(model_name="sourcerecord", constraint=models.UniqueConstraint(condition=~models.Q(external_id=""), fields=("source", "external_id", "payload_hash"), name="unique_external_source_payload")),
        migrations.AddIndex(model_name="fieldobservation", index=models.Index(fields=["company", "field_name", "is_current"], name="field_current_idx")),
        migrations.AddConstraint(model_name="fieldobservation", constraint=models.UniqueConstraint(fields=("source_record", "field_name", "normalized_value"), name="unique_source_field_observation")),
    ]
