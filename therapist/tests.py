import time
from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .admin import JournalEntryAdmin
from .crisis import contains_crisis_language, CRISIS_RESPONSE
from .crisis_ar import (
    CRISIS_KEYWORDS_AR,
    CrisisArConfigurationError,
    assert_no_placeholder_keywords,
    contains_crisis_language_ar,
)
from .groq_budget_guard import BUDGET_EXCEEDED_MESSAGES, check_and_reserve_budget_with_retry
from .luna_prompts import (
    CRISIS_RESPONSE_AR,
    GENDER_INSTRUCTIONS_AR,
    GROQ_ERROR_FALLBACK_AR,
    GROQ_ERROR_FALLBACK_EN,
    LUNA_SYSTEM_PROMPT_AR,
    LUNA_SYSTEM_PROMPT_EN,
    WEEKLY_LETTER_PROMPT_EN,
    LunaPromptConfigurationError,
    LunaPromptProvider,
    apply_gender_variant,
    assert_no_placeholder_prompts,
)
from .models import JournalEntry
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
        e = JournalEntry.objects.create(
            user_id=str(user_id), emoji="😊", thoughts="entry", ai_response="ok"
        )
        JournalEntry.objects.filter(id=e.id).update(created_at=now - timedelta(days=days_ago))
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

        JournalEntry.objects.create(
            user_id=str(user_a.id),
            emoji="😊",
            thoughts="Entry one",
            ai_response="AI response",
        )
        JournalEntry.objects.create(
            user_id=str(user_a.id),
            emoji="😊",
            thoughts="Entry two",
            ai_response="AI response",
        )
        JournalEntry.objects.create(
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
        JournalEntry.objects.create(
            user_id=str(user_a.id),
            emoji="😔",
            thoughts="I want to kill myself",
            ai_response="AI response",
        )
        JournalEntry.objects.create(
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


class JournalEntryAdminConfigTests(TestCase):
    def test_crisis_flagged_and_date_hierarchy_filters_configured(self):
        self.assertIn("crisis_flagged", JournalEntryAdmin.list_filter)
        self.assertEqual(JournalEntryAdmin.date_hierarchy, "created_at")

    def test_created_at_is_readonly(self):
        self.assertIn("created_at", JournalEntryAdmin.readonly_fields)

    def test_list_display_uses_preview_methods_not_raw_textfields(self):
        self.assertNotIn("thoughts", JournalEntryAdmin.list_display)
        self.assertNotIn("ai_response", JournalEntryAdmin.list_display)
        self.assertIn("thoughts_preview", JournalEntryAdmin.list_display)
        self.assertIn("ai_response_preview", JournalEntryAdmin.list_display)

    def test_preview_methods_truncate_long_text(self):
        entry = JournalEntry.objects.create(
            user_id="user-1",
            emoji="😊",
            thoughts="x" * 200,
            ai_response="y" * 200,
        )
        admin_instance = JournalEntryAdmin(JournalEntry, None)
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
    def test_request_past_the_burst_limit_is_throttled(self, mock_generate):
        mock_generate.return_value = "Mocked AI response"
        auth_header = {"HTTP_AUTHORIZATION": "Bearer faketoken-throttle-user"}

        statuses = []
        for _ in range(21):
            response = self.client.post(
                "/api/companion/generate/",
                {"emoji": "😊", "thoughts": "hi"},
                format="json",
                **auth_header,
            )
            statuses.append(response.status_code)

        # luna_chat is capped at 20/min, so the 21st call in the same minute
        # must be throttled regardless of the looser ai_generate scope.
        self.assertEqual(statuses[:20], [200] * 20)
        self.assertEqual(statuses[20], 429)


class LunaPromptProviderTests(TestCase):
    def test_arabic_returns_placeholder_prompt_with_neutral_gender_instruction_by_default(self):
        result = LunaPromptProvider.get_system_prompt("ar")
        self.assertIn(LUNA_SYSTEM_PROMPT_AR, result)
        self.assertIn(GENDER_INSTRUCTIONS_AR["unspecified"], result)

    def test_english_returns_existing_prompt_unchanged(self):
        self.assertEqual(
            LunaPromptProvider.get_system_prompt("en"), LUNA_SYSTEM_PROMPT_EN
        )

    def test_missing_language_defaults_to_english(self):
        self.assertEqual(LunaPromptProvider.get_system_prompt(None), LUNA_SYSTEM_PROMPT_EN)
        self.assertEqual(LunaPromptProvider.get_system_prompt(""), LUNA_SYSTEM_PROMPT_EN)

    @patch("therapist.luna_prompts.sentry_sdk.capture_message")
    def test_unexpected_language_falls_back_to_english_and_logs_warning(
        self, mock_capture
    ):
        result = LunaPromptProvider.get_system_prompt("fr")
        self.assertEqual(result, LUNA_SYSTEM_PROMPT_EN)
        mock_capture.assert_called_once()
        self.assertEqual(mock_capture.call_args.kwargs.get("level"), "warning")

    @patch("therapist.luna_prompts.sentry_sdk.capture_message")
    def test_known_language_never_logs_warning(self, mock_capture):
        LunaPromptProvider.get_system_prompt("en")
        LunaPromptProvider.get_system_prompt("ar")
        LunaPromptProvider.get_system_prompt(None)
        mock_capture.assert_not_called()


class LunaPromptGenderInstructionTests(TestCase):
    def test_arabic_male_includes_male_instruction(self):
        result = LunaPromptProvider.get_system_prompt("ar", "male")
        self.assertIn(GENDER_INSTRUCTIONS_AR["male"], result)
        self.assertNotIn(GENDER_INSTRUCTIONS_AR["female"], result)

    def test_arabic_female_includes_female_instruction(self):
        result = LunaPromptProvider.get_system_prompt("ar", "female")
        self.assertIn(GENDER_INSTRUCTIONS_AR["female"], result)
        self.assertNotIn(GENDER_INSTRUCTIONS_AR["male"], result)

    def test_arabic_unspecified_includes_neutral_instruction(self):
        result = LunaPromptProvider.get_system_prompt("ar", "unspecified")
        self.assertIn(GENDER_INSTRUCTIONS_AR["unspecified"], result)

    def test_arabic_existing_gender_choices_other_and_prefer_not_to_say_map_to_neutral(self):
        for gender in ("other", "prefer_not_to_say", "", None):
            result = LunaPromptProvider.get_system_prompt("ar", gender)
            self.assertIn(GENDER_INSTRUCTIONS_AR["unspecified"], result)

    def test_english_never_includes_any_gender_instruction(self):
        for gender in ("male", "female", "unspecified", "other", "prefer_not_to_say", None):
            result = LunaPromptProvider.get_system_prompt("en", gender)
            self.assertEqual(result, LUNA_SYSTEM_PROMPT_EN)
            for instruction in GENDER_INSTRUCTIONS_AR.values():
                self.assertNotIn(instruction, result)

    def test_weekly_letter_prompt_gets_same_gender_prepend_treatment(self):
        result_male = LunaPromptProvider.get_weekly_letter_prompt("ar", "male")
        result_female = LunaPromptProvider.get_weekly_letter_prompt("ar", "female")
        self.assertIn(GENDER_INSTRUCTIONS_AR["male"], result_male)
        self.assertIn(GENDER_INSTRUCTIONS_AR["female"], result_female)
        self.assertEqual(
            LunaPromptProvider.get_weekly_letter_prompt("en", "male"),
            WEEKLY_LETTER_PROMPT_EN,
        )


class GenerateAiResponsePreferredLanguageTests(TestCase):
    @patch("therapist.ai_model._call_groq")
    @patch("therapist.ai_model.check_and_reserve_budget_with_retry", return_value=True)
    def test_arabic_preferred_language_sends_arabic_system_prompt(
        self, mock_retry, mock_call_groq
    ):
        from .ai_model import generate_ai_response

        mock_call_groq.return_value = "reply"
        generate_ai_response("😊", "hi", preferred_language="ar", gender="female")

        sent_payload = mock_call_groq.call_args[0][0]
        system_message = sent_payload["messages"][0]
        self.assertEqual(system_message["role"], "system")
        self.assertIn(LUNA_SYSTEM_PROMPT_AR, system_message["content"])
        self.assertIn(GENDER_INSTRUCTIONS_AR["female"], system_message["content"])

    @patch("therapist.ai_model._call_groq")
    @patch("therapist.ai_model.check_and_reserve_budget_with_retry", return_value=True)
    def test_unset_preferred_language_sends_english_system_prompt_no_regression(
        self, mock_retry, mock_call_groq
    ):
        from .ai_model import generate_ai_response

        mock_call_groq.return_value = "reply"
        generate_ai_response("😊", "hi")

        sent_payload = mock_call_groq.call_args[0][0]
        self.assertEqual(sent_payload["messages"][0]["content"], LUNA_SYSTEM_PROMPT_EN)


class GenerateAiResponseInternalCrisisCheckTests(TestCase):
    """Covers generate_ai_response()'s own crisis short-circuit directly.
    Unreachable via the API today (views.py crisis-checks first and never
    calls this function for crisis text), but kept correct defensively —
    this locks in that it stays localized/gendered like the views.py path."""

    def test_english_returns_english_crisis_response(self):
        from .ai_model import generate_ai_response

        reply = generate_ai_response("😔", "I want to kill myself", preferred_language="en")
        self.assertEqual(reply, CRISIS_RESPONSE)

    def test_arabic_female_returns_gendered_arabic_crisis_response(self):
        from .ai_model import generate_ai_response

        reply = generate_ai_response(
            "😔", "I want to kill myself", preferred_language="ar", gender="female"
        )
        self.assertEqual(reply, LunaPromptProvider.get_crisis_response("ar", "female"))
        self.assertIn("تحمليه", reply)

    def test_missing_language_defaults_to_english_crisis_response(self):
        from .ai_model import generate_ai_response

        reply = generate_ai_response("😔", "I want to kill myself")
        self.assertEqual(reply, CRISIS_RESPONSE)


class LunaPromptPlaceholderCheckTests(TestCase):
    def test_passes_now_that_real_arabic_copy_is_in_place(self):
        assert_no_placeholder_prompts()  # should not raise — no PLACEHOLDER left

    def test_fails_if_a_placeholder_is_reintroduced(self):
        with patch(
            "therapist.luna_prompts._PROMPTS_BY_LANGUAGE",
            {"en": LUNA_SYSTEM_PROMPT_EN, "ar": "ARABIC_SYSTEM_PROMPT_PLACEHOLDER"},
        ):
            with self.assertRaises(LunaPromptConfigurationError):
                assert_no_placeholder_prompts()

    def test_management_command_passes_now_that_real_arabic_copy_is_in_place(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("check_luna_prompts", stdout=out)
        self.assertIn("production-ready", out.getvalue())


class CrisisArUnitTests(TestCase):
    def test_direct_statement_flagged(self):
        self.assertTrue(contains_crisis_language_ar("أريد أن أنتحر"))
        self.assertTrue(contains_crisis_language_ar(CRISIS_KEYWORDS_AR[0]))

    def test_case_insensitive(self):
        # Arabic has no letter case, so .lower()/.upper() are no-ops here —
        # this just confirms re.IGNORECASE doesn't break matching either way.
        self.assertTrue(contains_crisis_language_ar(CRISIS_KEYWORDS_AR[0].lower()))
        self.assertTrue(contains_crisis_language_ar(CRISIS_KEYWORDS_AR[0].upper()))

    def test_normal_text_not_flagged(self):
        self.assertFalse(contains_crisis_language_ar("اليوم كان يومًا جميلًا"))

    def test_empty_and_none_not_flagged(self):
        self.assertFalse(contains_crisis_language_ar(""))
        self.assertFalse(contains_crisis_language_ar(None))


class CrisisArPipelineIntegrationTests(TestCase):
    """Confirms the Arabic detector is wired into the same downstream
    crisis-handling path as therapist/crisis.py's English detector, and
    that the English path is completely unaffected."""

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
    def test_arabic_crisis_phrase_triggers_same_crisis_handling_as_english(
        self, mock_generate
    ):
        response = self.client.post(
            "/api/companion/generate/",
            {"emoji": "😔", "thoughts": "random text أريد أن أنتحر more text"},
            format="json",
            **_auth_header("user-ar"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["crisis_flagged"])
        mock_generate.assert_not_called()

    @patch("therapist.views.generate_ai_response")
    def test_english_crisis_keyword_still_works_unaffected(self, mock_generate):
        response = self.client.post(
            "/api/companion/generate/",
            {"emoji": "😔", "thoughts": "I want to kill myself"},
            format="json",
            **_auth_header("user-en"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["crisis_flagged"])
        mock_generate.assert_not_called()

    @patch("therapist.views.generate_ai_response")
    def test_no_crisis_language_in_either_language_does_not_trigger(self, mock_generate):
        mock_generate.return_value = "Mocked AI response"
        response = self.client.post(
            "/api/companion/generate/",
            {"emoji": "😊", "thoughts": "اليوم كان يومًا جميلًا, great day!"},
            format="json",
            **_auth_header("user-neither"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["crisis_flagged"])
        mock_generate.assert_called_once()

    @patch("therapist.views.logger")
    @patch("therapist.views.generate_ai_response")
    def test_crisis_trigger_logs_matched_languages(self, mock_generate, mock_logger):
        self.client.post(
            "/api/companion/generate/",
            {"emoji": "😔", "thoughts": CRISIS_KEYWORDS_AR[0]},
            format="json",
            **_auth_header("user-log"),
        )
        mock_logger.warning.assert_called_once()
        self.assertIn("ar", mock_logger.warning.call_args[0][1])


class CrisisArPlaceholderCheckTests(TestCase):
    def test_passes_now_that_real_keywords_are_in_place(self):
        assert_no_placeholder_keywords()  # should not raise — no PLACEHOLDER left

    def test_fails_if_a_placeholder_is_reintroduced(self):
        with patch(
            "therapist.crisis_ar.CRISIS_KEYWORDS_AR",
            ["TEST_ARABIC_CRISIS_PHRASE_PLACEHOLDER_1"],
        ):
            with self.assertRaises(CrisisArConfigurationError):
                assert_no_placeholder_keywords()

    def test_management_command_passes_now_that_real_keywords_are_in_place(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("check_crisis_ar_keywords", stdout=out)
        self.assertIn("production-ready", out.getvalue())


class ApplyGenderVariantTests(TestCase):
    def test_female_selects_female_form(self):
        result = apply_gender_variant("هل {ذهبت/ذهبتِ} اليوم؟", "female")
        self.assertEqual(result, "هل ذهبتِ اليوم؟")

    def test_male_selects_male_form(self):
        result = apply_gender_variant("هل {ذهبت/ذهبتِ} اليوم؟", "male")
        self.assertEqual(result, "هل ذهبت اليوم؟")

    def test_unspecified_other_prefer_not_to_say_and_blank_default_to_male_form(self):
        template = "هل {ذهبت/ذهبتِ} اليوم؟"
        expected = "هل ذهبت اليوم؟"
        for gender in ("unspecified", "other", "prefer_not_to_say", "", None):
            self.assertEqual(apply_gender_variant(template, gender), expected)

    def test_multiple_markers_all_substituted(self):
        result = apply_gender_variant(
            "{تحمل/تحملين} و{تريد/تريدين}", "female"
        )
        self.assertEqual(result, "تحملين وتريدين")

    def test_text_without_markers_returned_unchanged(self):
        self.assertEqual(apply_gender_variant("لا توجد متغيرات هنا", "female"), "لا توجد متغيرات هنا")


class LunaPromptCrisisResponseTests(TestCase):
    def test_english_returns_existing_crisis_response_unchanged(self):
        self.assertEqual(LunaPromptProvider.get_crisis_response("en"), CRISIS_RESPONSE)

    def test_arabic_male_applies_male_gender_variant(self):
        result = LunaPromptProvider.get_crisis_response("ar", "male")
        self.assertIn("تحمله", result)
        self.assertNotIn("تحمليه", result)
        self.assertNotIn("{", result)

    def test_arabic_female_applies_female_gender_variant(self):
        result = LunaPromptProvider.get_crisis_response("ar", "female")
        self.assertIn("تحمليه", result)
        self.assertNotIn("تحمله", result)
        self.assertNotIn("{", result)

    def test_arabic_unspecified_defaults_to_male_variant(self):
        result = LunaPromptProvider.get_crisis_response("ar", "unspecified")
        self.assertEqual(result, apply_gender_variant(CRISIS_RESPONSE_AR, "male"))

    def test_missing_language_defaults_to_english(self):
        self.assertEqual(LunaPromptProvider.get_crisis_response(None), CRISIS_RESPONSE)


class LunaPromptGroqErrorFallbackTests(TestCase):
    def test_arabic_returns_arabic_fallback(self):
        self.assertEqual(
            LunaPromptProvider.get_groq_error_fallback("ar"), GROQ_ERROR_FALLBACK_AR
        )

    def test_english_or_missing_returns_english_fallback(self):
        self.assertEqual(
            LunaPromptProvider.get_groq_error_fallback("en"), GROQ_ERROR_FALLBACK_EN
        )
        self.assertEqual(
            LunaPromptProvider.get_groq_error_fallback(None), GROQ_ERROR_FALLBACK_EN
        )


class CrisisViewLocalizationTests(TestCase):
    """Confirms GenerateResponseAPIView selects the crisis response by the
    user's preferred_language + gender, not the language the crisis text
    happened to be typed in."""

    def setUp(self):
        self.client = APIClient()
        patcher = patch("core.firebase_auth.auth.verify_id_token")
        self.mock_verify = patcher.start()
        self.addCleanup(patcher.stop)

    def _auth_as(self, uid):
        self.mock_verify.return_value = {"uid": uid, "email": f"{uid}@example.com"}
        return {"HTTP_AUTHORIZATION": f"Bearer faketoken-{uid}"}

    def test_arabic_preferring_user_gets_arabic_crisis_response(self):
        from accounts.models import User

        header = self._auth_as("crisis-ar-user")
        self.client.get("/api/accounts/me/", **header)
        User.objects.filter(firebase_uid="crisis-ar-user").update(
            preferred_language="ar", gender="female"
        )

        response = self.client.post(
            "/api/companion/generate/",
            {"emoji": "😔", "thoughts": "I want to kill myself"},
            format="json",
            **header,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["crisis_flagged"])
        self.assertIn("تحمليه", response.data["ai_response"])

    def test_english_preferring_user_still_gets_english_crisis_response(self):
        header = self._auth_as("crisis-en-user")
        response = self.client.post(
            "/api/companion/generate/",
            {"emoji": "😔", "thoughts": "I want to kill myself"},
            format="json",
            **header,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["ai_response"], CRISIS_RESPONSE)


class BudgetGuardArabicFallbackTests(TestCase):
    def test_arabic_preferred_language_returns_arabic_fallback_message(self):
        from .groq_budget_guard import BUDGET_EXCEEDED_MESSAGES_AR, get_fallback_message

        message = get_fallback_message("ar")
        self.assertIn(message, BUDGET_EXCEEDED_MESSAGES_AR)

    def test_english_or_missing_language_returns_english_fallback_message(self):
        from .groq_budget_guard import get_fallback_message

        self.assertIn(get_fallback_message("en"), BUDGET_EXCEEDED_MESSAGES)
        self.assertIn(get_fallback_message(None), BUDGET_EXCEEDED_MESSAGES)
        self.assertIn(get_fallback_message(), BUDGET_EXCEEDED_MESSAGES)

    @patch("therapist.ai_model.check_and_reserve_budget_with_retry", return_value=False)
    def test_generate_ai_response_passes_preferred_language_to_fallback(self, mock_retry):
        from .ai_model import generate_ai_response
        from .groq_budget_guard import BUDGET_EXCEEDED_MESSAGES_AR

        reply = generate_ai_response("😊", "hi", preferred_language="ar")
        self.assertIn(reply, BUDGET_EXCEEDED_MESSAGES_AR)
