from django.db import migrations


def seed_manual_source(apps, schema_editor):
    Source = apps.get_model("sources", "Source")
    Source.objects.update_or_create(
        key="manual-correction",
        defaults={
            "name": "Correção administrativa",
            "adapter_path": "apps.companies.corrections",
            "enabled": True,
            "capabilities": {"mode": "manual", "audited": True},
            "rate_limit": {},
        },
    )


class Migration(migrations.Migration):
    dependencies = [("sources", "0005_cnpjcandidate")]
    operations = [migrations.RunPython(seed_manual_source, migrations.RunPython.noop)]
