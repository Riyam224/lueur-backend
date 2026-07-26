from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from therapist.models import MoodEntry
from therapist.services import warm_weekly_letter_cache


class Command(BaseCommand):
    help = (
        "Pre-generates Luna's weekly letter for every user with at least 2 "
        "mood entries in the last 7 days, warming the Groq response cache "
        "so the /api/companion/weekly-letter/ endpoint serves from cache "
        "during the day instead of making a live Groq call. Intended to "
        "run nightly via Railway Cron."
    )

    def handle(self, *args, **options):
        week_start = timezone.now() - timedelta(days=7)

        active_user_ids = (
            MoodEntry.objects.filter(created_at__gte=week_start)
            .values_list("user_id", flat=True)
            .distinct()
        )

        warmed, skipped = 0, 0
        for user_id in active_user_ids:
            if warm_weekly_letter_cache(user_id):
                warmed += 1
            else:
                skipped += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Weekly letter cache warm-up done: "
                f"{warmed} warmed, {skipped} skipped (not enough entries)."
            )
        )
