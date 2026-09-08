from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("discovery", "0001_initial"), ("sources", "0001_initial"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name="queryresult", name="source", field=models.ForeignKey(on_delete=models.deletion.PROTECT, related_name="query_results", to="sources.source")),
        migrations.AddField(model_name="queryrun", name="created_by", field=models.ForeignKey(on_delete=models.deletion.PROTECT, related_name="query_runs", to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name="queryrun", name="query", field=models.ForeignKey(on_delete=models.deletion.PROTECT, related_name="runs", to="discovery.discoveryquery")),
        migrations.AddField(model_name="queryresult", name="query_run", field=models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="results", to="discovery.queryrun")),
        migrations.AddField(model_name="sourcecoverage", name="source", field=models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="coverage_entries", to="sources.source")),
        migrations.AddConstraint(model_name="discoveryquery", constraint=models.UniqueConstraint(fields=("created_by", "entity_target", "fingerprint"), name="unique_user_query_fingerprint")),
        migrations.AddConstraint(model_name="queryresult", constraint=models.UniqueConstraint(fields=("query_run", "company"), name="unique_query_run_company")),
        migrations.AddConstraint(model_name="sourcecoverage", constraint=models.UniqueConstraint(fields=("source", "dataset_reference", "scope_hash"), name="unique_source_dataset_scope")),
    ]
