from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .crisis import contains_crisis_language
from .models import MoodEntry
from .views import calculate_streak


def _auth_header(uid):
    return {"HTTP_AUTHORIZATION": "Bearer faketoken-" + uid}


class CrisisDetectionUnitTests(TestCase):
    def test_direct_statement_flagged(self):
        self.assertTrue(contains_crisis_language("I want to kill myself"))
        self.assertTrue(contains_crisis_language("sometimes I think about suicide"))

    def test_case_insensitive(self):
        self.assertTrue(contains_crisis_language("I WANT TO DIE"))
        self.assertTrue(contains_crisis_language("I Want To Die"))

    def test_normal_journal_text_not_flagged(self):
        self.assertFalse(contains_crisis_language("I feel overwhelmed with work lately"))
        self.assertFalse(contains_crisis_language("today was a good day, feeling grateful"))

    def test_empty_input_not_flagged(self):
        self.assertFalse(contains_crisis_language(""))
        self.assertFalse(contains_crisis_language(None))


class CalculateStreakTests(TestCase):
    def _entry_on(self, user_id, days_ago, now):
        e = MoodEntry.objects.create(
            user_id=str(user_id), emoji="😊", thoughts="entry", ai_response="ok"
        )
        MoodEntry.objects.filter(id=e.id).update(created_at=now - timedelta(days=days_ago))
        return e

    def test_no_entries_returns_zero(self):
        self.assertEqual(calculate_streak("no-such-user"), 0)

    def test_consecutive_days_counts_correctly(self):
        now = timezone.now()
        for d in [0, 1, 2]:
            self._entry_on("user-x", d, now)
        self.assertEqual(calculate_streak("user-x", now=now), 3)

    def test_gap_breaks_streak_at_the_gap(self):
        now = timezone.now()
        for d in [0, 1, 2, 4, 5]:
            self._entry_on("user-y", d, now)
        self.assertEqual(calculate_streak("user-y", now=now), 3)

    def test_same_day_duplicate_entries_count_once(self):
        now = timezone.now()
        self._entry_on("user-z", 0, now)
        self._entry_on("user-z", 0, now)
        self._entry_on("user-z", 1, now)
        self.assertEqual(calculate_streak("user-z", now=now), 2)

    def test_missed_today_but_active_yesterday_still_counts(self):
        now = timezone.now()
        for d in [1, 2, 3]:
            self._entry_on("user-w", d, now)
        self.assertEqual(calculate_streak("user-w", now=now), 3)

    def test_missed_more_than_one_day_resets_to_zero(self):
        now = timezone.now()
        for d in [3, 4, 5]:
            self._entry_on("user-v", d, now)
        self.assertEqual(calculate_streak("user-v", now=now), 0)


class TherapistAuthIsolationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        patcher = patch("core.firebase_auth.auth.verify_id_token")
        self.mock_verify = patcher.start()
        self.addCleanup(patcher.stop)
        self.mock_verify.side_effect = lambda token: {
            "uid": token.removeprefix("faketoken-"),
            "email": f"{token.removeprefix('faketoken-')}@example.com",
        }

    @patch("therapist.views.generate_ai_response")
    def test_generate_requires_auth_returns_401_without_token(self, mock_generate):
        mock_generate.return_value = "Mocked AI response"
        response = self.client.post(
            "/api/companion/generate/",
            {"emoji": "😊", "thoughts": "Great day!"},
            format="json",
        )
        self.assertEqual(response.status_code, 401)

    @patch("therapist.views.generate_ai_response")
    def test_generate_scopes_entry_to_authenticated_user(self, mock_generate):
        mock_generate.return_value = "Mocked AI response"
        response = self.client.post(
            "/api/companion/generate/",
            {"emoji": "😊", "thoughts": "Great day!"},
            format="json",
            **_auth_header("user-a"),
        )
        self.assertEqual(response.status_code, 200)
        from accounts.models import User

        user_a = User.objects.get(firebase_uid="user-a")
        self.assertEqual(response.data["user_id"], str(user_a.id))

    def test_history_requires_auth_returns_401_without_token(self):
        response = self.client.get("/api/companion/history/")
        self.assertEqual(response.status_code, 401)

    def test_weekly_letter_requires_auth_returns_401_without_token(self):
        response = self.client.get("/api/companion/weekly-letter/")
        self.assertEqual(response.status_code, 401)

    @patch("therapist.views.generate_ai_response")
    def test_history_isolates_between_two_users(self, mock_generate):
        mock_generate.return_value = "Mocked AI response"
        self.client.post(
            "/api/companion/generate/",
            {"emoji": "😊", "thoughts": "Entry one"},
            format="json",
            **_auth_header("user-a"),
        )
        self.client.post(
            "/api/companion/generate/",
            {"emoji": "😡", "thoughts": "Entry two"},
            format="json",
            **_auth_header("user-b"),
        )

        response_a = self.client.get(
            "/api/companion/history/", **_auth_header("user-a")
        )
        self.assertEqual(response_a.status_code, 200)
        self.assertEqual(len(response_a.data), 1)
        self.assertEqual(response_a.data[0]["thoughts"], "Entry one")

        response_b = self.client.get(
            "/api/companion/history/", **_auth_header("user-b")
        )
        self.assertEqual(response_b.status_code, 200)
        self.assertEqual(len(response_b.data), 1)
        self.assertEqual(response_b.data[0]["thoughts"], "Entry two")

    @patch("therapist.views.generate_ai_response")
    def test_crisis_text_short_circuits_and_never_calls_groq(self, mock_generate):
        response = self.client.post(
            "/api/companion/generate/",
            {"emoji": "😔", "thoughts": "I want to kill myself"},
            format="json",
            **_auth_header("user-a"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["crisis_flagged"])
        mock_generate.assert_not_called()

    @patch("therapist.views.generate_ai_response")
    def test_non_crisis_text_flags_false_and_calls_groq(self, mock_generate):
        mock_generate.return_value = "Mocked AI response"
        response = self.client.post(
            "/api/companion/generate/",
            {"emoji": "😊", "thoughts": "Great day!"},
            format="json",
            **_auth_header("user-a"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["crisis_flagged"])
        mock_generate.assert_called_once()

    @patch("therapist.views.generate_ai_response")
    def test_crisis_adjacent_non_literal_phrase(self, mock_generate):
        """Reports the real result for a non-literal phrase rather than assuming
        one way or the other — flagged for a product decision, not silently
        resolved here."""
        mock_generate.return_value = "Mocked AI response"
        response = self.client.post(
            "/api/companion/generate/",
            {"emoji": "😩", "thoughts": "this exam is killing me"},
            format="json",
            **_auth_header("user-a"),
        )
        self.assertEqual(response.status_code, 200)
        # NOTE: "killing me" does not match any CRISIS_KEYWORDS phrase
        # (which require "kill myself", not "killing me"), so this is
        # correctly NOT flagged. See test report for the false-positive
        # phrase that DOES currently trip the pattern.
        self.assertFalse(response.data["crisis_flagged"])
        mock_generate.assert_called_once()

    @patch("therapist.views.http_requests.post")
    def test_weekly_letter_scopes_to_authenticated_user(self, mock_post):
        class MockResponse:
            def json(self):
                return {"choices": [{"message": {"content": "Weekly letter"}}]}

        mock_post.return_value = MockResponse()

        from accounts.models import User

        user_a = User.objects.create(
            email="user-a@example.com", firebase_uid="user-a", username="user-a"
        )
        user_b = User.objects.create(
            email="user-b@example.com", firebase_uid="user-b", username="user-b"
        )

        MoodEntry.objects.create(
            user_id=str(user_a.id),
            emoji="😊",
            thoughts="Entry one",
            ai_response="AI response",
        )
        MoodEntry.objects.create(
            user_id=str(user_a.id),
            emoji="😊",
            thoughts="Entry two",
            ai_response="AI response",
        )
        MoodEntry.objects.create(
            user_id=str(user_b.id),
            emoji="😡",
            thoughts="Entry three",
            ai_response="AI response",
        )

        response = self.client.get(
            "/api/companion/weekly-letter/", **_auth_header("user-a")
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["stats"]["entry_count"], 2)
        self.assertEqual(response.data["stats"]["dominant_emoji"], "😊")
        self.assertEqual(response.data["letter"], "Weekly letter")
        self.assertTrue(mock_post.called)
