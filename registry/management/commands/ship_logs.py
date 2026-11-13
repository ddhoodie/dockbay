import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from registry.logs import ship_log_batch


class Command(BaseCommand):
    help = "Periodically ship complete application log lines to Elasticsearch."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--interval", type=float, default=5.0)

    def handle(self, *args, **options):
        if options["interval"] <= 0:
            raise CommandError("The interval must be greater than zero.")

        while True:
            try:
                count = ship_log_batch(
                    settings.DOCKBAY_LOG_FILE,
                    settings.DOCKBAY_LOG_CHECKPOINT,
                )
            except Exception:
                raise CommandError(
                    "Log shipping failed; check the log file and Elasticsearch availability."
                ) from None
            if count:
                self.stdout.write(f"Shipped {count} log line(s).")
            if options["once"]:
                return
            time.sleep(options["interval"])
