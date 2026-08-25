from datetime import timedelta

from django.utils import timezone

from accounts.models import User
from therapist.models import JournalEntry
from therapist.views import calculate_streak


def dashboard_summary():
    """Computes the six FR-010 aggregate figures for the admin index page.

    Plain ORM Count/filter queries run at request time, per research.md §3 —
    no caching, so figures always reflect current data (FR-011).
    """
    now = timezone.now()
    entries_7d = JournalEntry.objects.filter(created_at__gte=now - timedelta(days=7))
    entries_30d = JournalEntry.objects.filter(created_at__gte=now - timedelta(days=30))

    user_ids_with_entries = JournalEntry.objects.values_list(
        "user_id", flat=True
    ).distinct()
    streaks = [calculate_streak(uid, now=now) for uid in user_ids_with_entries]
    average_streak = round(sum(streaks) / len(streaks), 1) if streaks else 0

    return {
        "active_users": User.objects.filter(is_active=True).count(),
        "entries_last_7_days": entries_7d.count(),
        "entries_last_30_days": entries_30d.count(),
        "crisis_flagged_last_7_days": entries_7d.filter(crisis_flagged=True).count(),
        "crisis_flagged_last_30_days": entries_30d.filter(
            crisis_flagged=True
        ).count(),
        "average_streak": average_streak,
    }
