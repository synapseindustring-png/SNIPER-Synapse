from django.db import migrations


def seed_source(apps, schema_editor):
    apps.get_model("sources", "Source").objects.update_or_create(
        key="website",
        defaults={
            "name": "Website institucional",
            "adapter_path": "apps.crawler.services.crawl_company_website",
            "enabled": True,
            "capabilities": {"enrichment": True, "signals": True},
            "rate_limit": {"concurrency": 1},
        },
    )


class Migration(migrations.Migration):
    dependencies = [("crawler", "0001_initial")]
    operations = [migrations.RunPython(seed_source, migrations.RunPython.noop)]
