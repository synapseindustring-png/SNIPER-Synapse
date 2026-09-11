from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("discovery", "0002_initial")]

    operations = [
        migrations.AddField(
            model_name="sourcecoverage",
            name="query_run",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name="source_coverages",
                to="discovery.queryrun",
            ),
        ),
    ]
