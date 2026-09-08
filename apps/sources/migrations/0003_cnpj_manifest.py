import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("sources", "0002_seed_receita_source")]
    operations = [
        migrations.CreateModel(
            name="CnpjDataset",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("reference", models.CharField(max_length=20)),
                ("status", models.CharField(choices=[("DISCOVERED", "Descoberta"), ("READY", "Pronta"), ("INVALID", "Inválida")], default="DISCOVERED", max_length=16)),
                ("is_current", models.BooleanField(default=False)),
                ("discovered_at", models.DateTimeField()),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("source", models.ForeignKey(on_delete=models.deletion.PROTECT, related_name="cnpj_datasets", to="sources.source")),
            ],
            options={"ordering": ("-reference",)},
        ),
        migrations.CreateModel(
            name="CnpjDatasetFile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("ESTABLISHMENTS", "Estabelecimentos"), ("COMPANIES", "Empresas"), ("SIMPLES", "Simples")], max_length=20)),
                ("part_number", models.PositiveSmallIntegerField(default=0)),
                ("url", models.URLField(max_length=1000)),
                ("size_bytes", models.PositiveBigIntegerField()),
                ("etag", models.CharField(blank=True, max_length=255)),
                ("checksum", models.CharField(blank=True, max_length=128)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("dataset", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="files", to="sources.cnpjdataset")),
            ],
            options={"ordering": ("kind", "part_number")},
        ),
        migrations.AddConstraint(model_name="cnpjdataset", constraint=models.UniqueConstraint(fields=("source", "reference"), name="unique_cnpj_dataset")),
        migrations.AddConstraint(model_name="cnpjdataset", constraint=models.UniqueConstraint(condition=models.Q(is_current=True), fields=("source",), name="one_current_cnpj_dataset_per_source")),
        migrations.AddConstraint(model_name="cnpjdatasetfile", constraint=models.UniqueConstraint(fields=("dataset", "kind", "part_number"), name="unique_cnpj_dataset_file_part")),
        migrations.AddConstraint(model_name="cnpjdatasetfile", constraint=models.CheckConstraint(condition=models.Q(size_bytes__gt=0), name="cnpj_file_size_gt_zero")),
    ]
