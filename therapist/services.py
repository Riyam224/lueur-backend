import logging
from datetime import timedelta

from django.utils import timezone

from .ai_model import generate_weekly_letter
from .crisis import contains_crisis_language
from .models import MoodEntry

logger = logging.getLogger(__name__)


def build_weekly_letter_context(user_id):
    """
    Gathers the same 7-day window data the weekly-letter endpoint uses.
    Returns None if there aren't enough entries (< 2) to write a letter.
    """
    week_start = timezone.now() - timedelta(days=7)
    entries = MoodEntry.objects.filter(
        user_id=str(user_id), created_at__gte=week_start
    ).order_by("created_at")
    entries_count = entries.count()

    if entries_count < 2:
        return None

    formatted_entries = "\n".join(
        [
            f"- {e.created_at.strftime('%A')}: felt {e.emoji}, wrote: "
            f"'{e.thoughts[:100] if not contains_crisis_language(e.thoughts) else '(a difficult moment)'}'"
            for e in entries
        ]
    )
    emoji_list = [e.emoji for e in entries]
    dominant_emoji = max(set(emoji_list), key=emoji_list.count)

    return {
        "formatted_entries": formatted_entries,
        "entries_count": entries_count,
        "dominant_emoji": dominant_emoji,
    }


def warm_weekly_letter_cache(user_id):
    """
    Pre-generates (or refreshes) the cached weekly letter for one user,
    so a later request from the app hits the cache instead of calling
    Groq live. Safe to call from a nightly cron.
    """
    context = build_weekly_letter_context(user_id)
    if context is None:
        return False

    try:
        generate_weekly_letter(
            context["formatted_entries"],
            context["entries_count"],
            context["dominant_emoji"],
        )
        return True
    except Exception as exc:
        logger.error("Weekly letter warm-up failed for user %s: %s", user_id, exc)
        return False
