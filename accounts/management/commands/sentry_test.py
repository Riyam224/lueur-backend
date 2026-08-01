"""
TEMPORARY verification command — confirms Sentry is wired up end-to-end.
Delete this file once you've confirmed a test event shows up in the
Sentry dashboard; it has no purpose beyond that one-time check.
"""
from django.core.management.base import BaseCommand

import sentry_sdk


class Command(BaseCommand):
    help = "TEMPORARY: raises a test exception, captures it, and flushes to Sentry. Safe to delete after verifying."

    def handle(self, *args, **options):
        self.stdout.write("Raising a test exception for Sentry...")
        try:
            raise RuntimeError("Sentry test event from `manage.py sentry_test`")
        except RuntimeError as exc:
            sentry_sdk.capture_exception(exc)

        sentry_sdk.flush(timeout=2)
        self.stdout.write(self.style.SUCCESS("Test event captured and flushed to Sentry."))
