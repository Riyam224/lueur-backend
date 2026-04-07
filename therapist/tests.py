from django.test import TestCase
from rest_framework.test import APIClient
from unittest.mock import patch

from .models import MoodEntry


class TherapistUserIdTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch("therapist.ai_model.generate_ai_response")
    def test_generate_requires_user_id(self, mock_generate):
        mock_generate.return_value = "Mocked AI response"
        response = self.client.post(
            "/api/therapist/generate/",
            {"emoji": "😊", "thoughts": "Great day!"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("user_id", response.data)

    @patch("therapist.ai_model.generate_ai_response")
    def test_generate_rejects_invalid_user_id(self, mock_generate):
        mock_generate.return_value = "Mocked AI response"
        response = self.client.post(
            "/api/therapist/generate/",
            {"user_id": "bad id!", "emoji": "😊", "thoughts": "Great day!"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("user_id", response.data)

    def test_history_requires_user_id(self):
        response = self.client.get("/api/therapist/history/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)

    def test_history_filters_by_user_id(self):
        MoodEntry.objects.create(
            user_id="user_1",
            emoji="😊",
            thoughts="Entry one",
            ai_response="AI response",
        )
        MoodEntry.objects.create(
            user_id="user_1",
            emoji="😔",
            thoughts="Entry two",
            ai_response="AI response",
        )
        MoodEntry.objects.create(
            user_id="user_2",
            emoji="😡",
            thoughts="Entry three",
            ai_response="AI response",
        )

        response = self.client.get("/api/therapist/history/?user_id=user_1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)
        self.assertTrue(all(entry["user_id"] == "user_1" for entry in response.data))

    def test_weekly_letter_requires_user_id(self):
        response = self.client.get("/api/therapist/weekly-letter/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)

    @patch("therapist.views.http_requests.post")
    def test_weekly_letter_filters_by_user_id(self, mock_post):
        class MockResponse:
            def json(self):
                return {"choices": [{"message": {"content": "Weekly letter"}}]}

        mock_post.return_value = MockResponse()

        MoodEntry.objects.create(
            user_id="user_1",
            emoji="😊",
            thoughts="Entry one",
            ai_response="AI response",
        )
        MoodEntry.objects.create(
            user_id="user_1",
            emoji="😔",
            thoughts="Entry two",
            ai_response="AI response",
        )
        MoodEntry.objects.create(
            user_id="user_2",
            emoji="😡",
            thoughts="Entry three",
            ai_response="AI response",
        )

        response = self.client.get("/api/therapist/weekly-letter/?user_id=user_1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["stats"]["entry_count"], 2)
        self.assertEqual(response.data["stats"]["dominant_emoji"], "😊")
        self.assertEqual(response.data["letter"], "Weekly letter")
        self.assertTrue(mock_post.called)
