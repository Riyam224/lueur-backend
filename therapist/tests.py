import time
from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .admin import MoodEntryAdmin
from .crisis import contains_crisis_language
from .groq_budget_guard import BUDGET_EXCEEDED_MESSAGES, check_and_reserve_budget_with_retry
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

    @patch("therapist.ai_model.requests.post")
    def test_weekly_letter_scopes_to_authenticated_user(self, mock_post):
        class MockResponse:
            def raise_for_status(self):
                pass

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

    @patch("therapist.views.generate_weekly_letter")
    def test_weekly_letter_redacts_crisis_entries_before_sending_to_groq(
        self, mock_generate_letter
    ):
        mock_generate_letter.return_value = "Weekly letter"

        from accounts.models import User

        user_a = User.objects.create(
            email="user-crisis@example.com", firebase_uid="user-crisis", username="user-crisis"
        )
        MoodEntry.objects.create(
            user_id=str(user_a.id),
            emoji="😔",
            thoughts="I want to kill myself",
            ai_response="AI response",
        )
        MoodEntry.objects.create(
            user_id=str(user_a.id),
            emoji="😊",
            thoughts="had a good day",
            ai_response="AI response",
        )

        response = self.client.get(
            "/api/companion/weekly-letter/", **_auth_header("user-crisis")
        )
        self.assertEqual(response.status_code, 200)
        formatted_entries_sent = mock_generate_letter.call_args[0][0]
        self.assertNotIn("kill myself", formatted_entries_sent)
        self.assertIn("(a difficult moment)", formatted_entries_sent)
        self.assertIn("had a good day", formatted_entries_sent)


class MoodEntryAdminConfigTests(TestCase):
    def test_crisis_flagged_and_date_hierarchy_filters_configured(self):
        self.assertIn("crisis_flagged", MoodEntryAdmin.list_filter)
        self.assertEqual(MoodEntryAdmin.date_hierarchy, "created_at")

    def test_created_at_is_readonly(self):
        self.assertIn("created_at", MoodEntryAdmin.readonly_fields)

    def test_list_display_uses_preview_methods_not_raw_textfields(self):
        self.assertNotIn("thoughts", MoodEntryAdmin.list_display)
        self.assertNotIn("ai_response", MoodEntryAdmin.list_display)
        self.assertIn("thoughts_preview", MoodEntryAdmin.list_display)
        self.assertIn("ai_response_preview", MoodEntryAdmin.list_display)

    def test_preview_methods_truncate_long_text(self):
        entry = MoodEntry.objects.create(
            user_id="user-1",
            emoji="😊",
            thoughts="x" * 200,
            ai_response="y" * 200,
        )
        admin_instance = MoodEntryAdmin(MoodEntry, None)
        self.assertLess(len(admin_instance.thoughts_preview(entry)), 200)
        self.assertLess(len(admin_instance.ai_response_preview(entry)), 200)


class BudgetGuardRetryTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_returns_true_quickly_under_normal_load(self):
        start = time.monotonic()
        result = check_and_reserve_budget_with_retry(estimated_prompt_tokens=50)
        elapsed = time.monotonic() - start
        self.assertTrue(result)
        # An empty cache means the first attempt succeeds — no retry wait involved.
        self.assertLess(elapsed, 1.0)

    @patch("therapist.groq_budget_guard.check_and_reserve_budget")
    @patch("therapist.groq_budget_guard.time.sleep")
    def test_retries_and_succeeds_once_budget_frees_up(self, mock_sleep, mock_check):
        mock_check.side_effect = [False, False, True]
        result = check_and_reserve_budget_with_retry(estimated_prompt_tokens=50)
        self.assertTrue(result)
        self.assertEqual(mock_check.call_count, 3)

    @patch("therapist.groq_budget_guard.check_and_reserve_budget", return_value=False)
    @patch("therapist.groq_budget_guard.time.sleep")
    def test_gives_up_after_max_wait_and_never_returns_true(self, mock_sleep, mock_check):
        result = check_and_reserve_budget_with_retry(estimated_prompt_tokens=50)
        self.assertFalse(result)
        self.assertGreater(mock_check.call_count, 1)

    @patch("therapist.ai_model.check_and_reserve_budget_with_retry", return_value=False)
    def test_fallback_message_only_reached_when_budget_stays_unavailable(self, mock_retry):
        from .ai_model import generate_ai_response

        reply = generate_ai_response("😊", "just checking in")
        self.assertIn(reply, BUDGET_EXCEEDED_MESSAGES)
        mock_retry.assert_called_once()

    @patch("therapist.ai_model._call_groq")
    @patch("therapist.ai_model.check_and_reserve_budget_with_retry", return_value=True)
    def test_groq_called_when_budget_available(self, mock_retry, mock_call_groq):
        from .ai_model import generate_ai_response

        mock_call_groq.return_value = "Real Luna reply"
        reply = generate_ai_response("😊", "just checking in")
        self.assertEqual(reply, "Real Luna reply")
        mock_call_groq.assert_called_once()


class LunaChatThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.client = APIClient()
        patcher = patch("core.firebase_auth.auth.verify_id_token")
        self.mock_verify = patcher.start()
        self.addCleanup(patcher.stop)
        self.mock_verify.return_value = {"uid": "throttle-user", "email": "throttle-user@example.com"}

    @patch("therapist.views.generate_ai_response")
    def test_ninth_request_in_a_burst_is_throttled(self, mock_generate):
        mock_generate.return_value = "Mocked AI response"
        auth_header = {"HTTP_AUTHORIZATION": "Bearer faketoken-throttle-user"}

        statuses = []
        for _ in range(9):
            response = self.client.post(
                "/api/companion/generate/",
                {"emoji": "😊", "thoughts": "hi"},
                format="json",
                **auth_header,
            )
            statuses.append(response.status_code)

        # luna_chat is capped at 8/min, so the 9th call in the same minute
        # must be throttled regardless of the looser ai_generate scope.
        self.assertEqual(statuses[:8], [200] * 8)
        self.assertEqual(statuses[8], 429)
