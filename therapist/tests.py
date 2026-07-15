from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from .models import MoodEntry


def _auth_header(uid):
    return {"HTTP_AUTHORIZATION": "Bearer faketoken-" + uid}


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
