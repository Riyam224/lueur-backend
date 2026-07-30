from django.core.management.base import BaseCommand, CommandError

from therapist.luna_prompts import LunaPromptConfigurationError, assert_no_placeholder_prompts


class Command(BaseCommand):
    help = (
        "Fails if any Luna system prompt still contains placeholder text. "
        "Run this in CI before a production deploy."
    )

    def handle(self, *args, **options):
        try:
            assert_no_placeholder_prompts()
        except LunaPromptConfigurationError as exc:
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS("All Luna prompts are production-ready."))
