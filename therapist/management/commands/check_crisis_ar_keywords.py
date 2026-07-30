from django.core.management.base import BaseCommand, CommandError

from therapist.crisis_ar import CrisisArConfigurationError, assert_no_placeholder_keywords


class Command(BaseCommand):
    help = (
        "Fails if therapist/crisis_ar.py still contains placeholder crisis "
        "keywords. Run this in CI before a production deploy."
    )

    def handle(self, *args, **options):
        try:
            assert_no_placeholder_keywords()
        except CrisisArConfigurationError as exc:
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS("crisis_ar.py keywords are production-ready."))
