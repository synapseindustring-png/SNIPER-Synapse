from django.db import migrations


def seed_receita_source(apps, schema_editor):
    Source = apps.get_model("sources", "Source")
    Source.objects.update_or_create(
        key="receita-cnpj",
        defaults={
            "name": "Dados Abertos do CNPJ — Receita Federal",
            "adapter_path": "apps.sources.cnpj",
            "enabled": True,
            "capabilities": {
                "entity_targets": ["INDUSTRY", "PARTNER"],
                "filters": ["registration_status", "state", "municipality_code", "cnae"],
            },
            "rate_limit": {"concurrency": 1},
        },
    )


def remove_receita_source(apps, schema_editor):
    Source = apps.get_model("sources", "Source")
    Source.objects.filter(key="receita-cnpj").delete()


class Migration(migrations.Migration):
    dependencies = [("sources", "0001_initial")]
    operations = [migrations.RunPython(seed_receita_source, remove_receita_source)]
