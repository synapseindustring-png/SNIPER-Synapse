import os
import socket
import time

from django.core.management.base import BaseCommand

from apps.jobs.services import (
    JobLeaseLost,
    claim_next_job,
    execute_job,
    maintain_job_lease,
    mark_failed,
    mark_succeeded,
)


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
                with maintain_job_lease(job.id, worker_id, lock_seconds) as lease:
                    execute_job(job)
                if lease.lost:
                    raise JobLeaseLost(f"Worker lease was lost for job {job.id}")
            except Exception as exc:
                try:
                    mark_failed(job.id, worker_id, f"{type(exc).__name__}: {exc}")
                except JobLeaseLost:
                    self.stderr.write(f"Job {job.id} lease was lost; result was discarded")
                    if options["once"]:
                        return
                    continue
                self.stderr.write(f"Job {job.id} failed: {exc}")
            else:
                try:
                    mark_succeeded(job.id, worker_id)
                except JobLeaseLost:
                    self.stderr.write(f"Job {job.id} lease was lost; result was discarded")
                    if options["once"]:
                        return
                    continue
                self.stdout.write(self.style.SUCCESS(f"Job {job.id} succeeded"))

            if options["once"]:
                return
