from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("companies", "0002_initial"),
        ("discovery", "0002_initial"),
        ("sources", "0004_seed_jobs_fixture_source"),
    ]

    operations = [
        migrations.CreateModel(
            name="CnpjCandidate",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("cnpj", models.CharField(max_length=14)),
                ("cnpj_basico", models.CharField(max_length=8)),
                ("establishment_payload", models.JSONField(default=dict)),
                ("company_payload", models.JSONField(blank=True, default=dict)),
                ("simples_payload", models.JSONField(blank=True, default=dict)),
                ("company_matched", models.BooleanField(default=False)),
                ("simples_matched", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "company",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="cnpj_candidates",
                        to="companies.company",
                    ),
                ),
                (
                    "query_run",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="cnpj_candidates",
                        to="discovery.queryrun",
                    ),
                ),
            ],
            options={"ordering": ("cnpj",)},
        ),
        migrations.AddConstraint(
            model_name="cnpjcandidate",
            constraint=models.UniqueConstraint(
                fields=("query_run", "cnpj"),
                name="unique_cnpj_candidate_per_run",
            ),
        ),
        migrations.AddIndex(
            model_name="cnpjcandidate",
            index=models.Index(
                fields=["query_run", "cnpj_basico"],
                name="candidate_run_basic_idx",
            ),
        ),
    ]
