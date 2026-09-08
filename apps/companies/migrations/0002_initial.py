from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("companies", "0001_initial"), ("sources", "0001_initial")]
    operations = [
        migrations.AddField(
            model_name="companycnae",
            name="source_record",
            field=models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="company_cnaes", to="sources.sourcerecord"),
        ),
        migrations.AddConstraint(model_name="companycnae", constraint=models.UniqueConstraint(fields=("company", "code"), name="unique_company_cnae")),
        migrations.AddConstraint(model_name="companycnae", constraint=models.UniqueConstraint(condition=models.Q(is_primary=True), fields=("company",), name="one_primary_cnae_per_company")),
    ]
