from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from therapist.models import JournalEntry

from .admin_dashboard import dashboard_summary


def _entry(user_id, days_ago, now, crisis_flagged=False):
    e = JournalEntry.objects.create(
        user_id=str(user_id),
        emoji="😊",
        thoughts="entry",
        ai_response="ok",
        crisis_flagged=crisis_flagged,
    )
    JournalEntry.objects.filter(id=e.id).update(created_at=now - timedelta(days=days_ago))
    return e


class DashboardSummaryTests(TestCase):
    def test_zero_data_renders_zeros_not_errors(self):
        summary = dashboard_summary()
        self.assertEqual(
            summary,
            {
                "active_users": 0,
                "entries_last_7_days": 0,
                "entries_last_30_days": 0,
                "crisis_flagged_last_7_days": 0,
                "crisis_flagged_last_30_days": 0,
                "average_streak": 0,
            },
        )

    def test_six_figures_match_expected_counts(self):
        now = timezone.now()

        User.objects.create(
            email="active1@example.com", username="active1", is_active=True
        )
        User.objects.create(
            email="active2@example.com", username="active2", is_active=True
        )
        User.objects.create(
            email="inactive@example.com", username="inactive", is_active=False
        )

        # user-a: 2 entries within 7 days (1 crisis-flagged), forms a 2-day streak
        _entry("user-a", 0, now)
        _entry("user-a", 1, now, crisis_flagged=True)

        # user-b: 1 entry within 30 days but outside 7 days, no streak (gap > 1 day)
        _entry("user-b", 15, now, crisis_flagged=True)

        # user-c: entry outside the 30-day window entirely — excluded from both counts
        _entry("user-c", 45, now)

        summary = dashboard_summary()

        self.assertEqual(summary["active_users"], 2)
        self.assertEqual(summary["entries_last_7_days"], 2)
        self.assertEqual(summary["entries_last_30_days"], 3)
        self.assertEqual(summary["crisis_flagged_last_7_days"], 1)
        self.assertEqual(summary["crisis_flagged_last_30_days"], 2)
        # user-a streak=2, user-b streak=0, user-c streak=0 -> average 0.7
        self.assertEqual(summary["average_streak"], 0.7)
