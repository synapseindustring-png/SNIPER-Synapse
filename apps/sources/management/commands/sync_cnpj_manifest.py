from django.core.management.base import BaseCommand

from apps.sources.cnpj.manifest import sync_latest_manifest


class Command(BaseCommand):
    help = "Descobre e persiste a competência CNPJ completa mais recente via WebDAV."

    def handle(self, *args, **options):
        dataset = sync_latest_manifest()
        self.stdout.write(
            self.style.SUCCESS(
                f"CNPJ manifest {dataset.reference}: {dataset.files.count()} file(s), ready."
            )
        )
