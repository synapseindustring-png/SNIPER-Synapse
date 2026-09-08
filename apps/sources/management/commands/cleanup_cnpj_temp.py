from django.core.management.base import BaseCommand

from apps.sources.cnpj.storage import cleanup_stale_downloads


class Command(BaseCommand):
    help = "Remove artefatos temporários CNPJ abandonados e mais antigos que o limite."

    def add_arguments(self, parser):
        parser.add_argument("--max-age-seconds", type=int)

    def handle(self, *args, **options):
        max_age = options["max_age_seconds"]
        if max_age is not None and max_age < 1:
            raise ValueError("max-age-seconds must be positive")
        removed = cleanup_stale_downloads(max_age)
        self.stdout.write(f"Removed {removed} stale CNPJ temporary file(s).")
