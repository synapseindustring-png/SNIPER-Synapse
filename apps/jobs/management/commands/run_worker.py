import os
import socket
import time

from django.core.management.base import BaseCommand

from apps.jobs.services import claim_next_job, execute_job, mark_failed, mark_succeeded


class Command(BaseCommand):
    help = "Processa a fila persistida de jobs do Synapse Sniper."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        worker_id = os.getenv("WORKER_ID", socket.gethostname())
        poll_seconds = float(os.getenv("WORKER_POLL_SECONDS", "2"))
        lock_seconds = int(os.getenv("JOB_LOCK_SECONDS", "300"))

        while True:
            job = claim_next_job(worker_id, lock_seconds)
            if job is None:
                if options["once"]:
                    return
                time.sleep(poll_seconds)
                continue

            self.stdout.write(f"Processing {job.id} ({job.type})")
            try:
                execute_job(job)
            except Exception as exc:
                mark_failed(job.id, f"{type(exc).__name__}: {exc}")
                self.stderr.write(f"Job {job.id} failed: {exc}")
            else:
                mark_succeeded(job.id)
                self.stdout.write(self.style.SUCCESS(f"Job {job.id} succeeded"))

            if options["once"]:
                return

