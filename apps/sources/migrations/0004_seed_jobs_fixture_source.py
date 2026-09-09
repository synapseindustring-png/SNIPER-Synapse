from django.db import migrations


def seed_source(apps, schema_editor):
    apps.get_model("sources", "Source").objects.update_or_create(
        key="jobs-fixture",
        defaults={
            "name": "Vagas — fixture local",
            "adapter_path": "apps.sources.jobs.fixture.FixtureJobsAdapter",
            "enabled": False,
            "capabilities": {"jobs": True, "network": False, "preview": True},
            "rate_limit": {"max_pages": 2, "max_results": 100},
        },
    )


def unseed_source(apps, schema_editor):
    apps.get_model("sources", "Source").objects.filter(key="jobs-fixture").delete()


class Migration(migrations.Migration):
    dependencies = [("sources", "0003_cnpj_manifest")]
    operations = [migrations.RunPython(seed_source, unseed_source)]
