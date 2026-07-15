from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from rest_framework.test import APIClient

from therapist.models import MoodEntry

from .models import User


def _auth_header(uid="user-1"):
    return {"HTTP_AUTHORIZATION": f"Bearer faketoken-{uid}"}


class FirebaseAuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch("core.firebase_auth.auth.verify_id_token")
    def test_new_firebase_uid_creates_user(self, mock_verify):
        mock_verify.return_value = {"uid": "abc123", "email": "a@example.com"}
        response = self.client.get("/api/accounts/me/", **_auth_header("abc123"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(firebase_uid="abc123").exists())

    @patch("core.firebase_auth.auth.verify_id_token")
    def test_existing_firebase_uid_reuses_user(self, mock_verify):
        mock_verify.return_value = {"uid": "abc123", "email": "a@example.com"}
        self.client.get("/api/accounts/me/", **_auth_header("abc123"))
        self.client.get("/api/accounts/me/", **_auth_header("abc123"))
        self.assertEqual(User.objects.filter(firebase_uid="abc123").count(), 1)

    def test_missing_token_returns_401(self):
        response = self.client.get("/api/accounts/me/")
        self.assertEqual(response.status_code, 401)

    def test_malformed_token_returns_401(self):
        response = self.client.get(
            "/api/accounts/me/", HTTP_AUTHORIZATION="NotBearer something"
        )
        self.assertEqual(response.status_code, 401)

    @patch("core.firebase_auth.auth.verify_id_token")
    def test_invalid_token_returns_401(self, mock_verify):
        mock_verify.side_effect = Exception("invalid signature")
        response = self.client.get("/api/accounts/me/", **_auth_header("bad"))
        self.assertEqual(response.status_code, 401)

    @patch("core.firebase_auth.auth.verify_id_token")
    def test_expired_token_returns_401(self, mock_verify):
        mock_verify.side_effect = Exception("token expired")
        response = self.client.get("/api/accounts/me/", **_auth_header("expired"))
        self.assertEqual(response.status_code, 401)


class ProfileTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.verify_patcher = patch("core.firebase_auth.auth.verify_id_token")
        mock_verify = self.verify_patcher.start()
        self.addCleanup(self.verify_patcher.stop)
        mock_verify.return_value = {"uid": "alice", "email": "alice@example.com"}
        self.auth_header = _auth_header("alice")
        # creates the user on first authenticated call
        self.client.get("/api/accounts/me/", **self.auth_header)

    def test_get_me_returns_own_profile_only(self):
        response = self.client.get("/api/accounts/me/", **self.auth_header)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["email"], "alice@example.com")

    def test_patch_me_updates_allowed_field(self):
        response = self.client.patch(
            "/api/accounts/me/",
            {"full_name": "Alice Doe", "bio": "Hi there"},
            format="json",
            **self.auth_header,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["full_name"], "Alice Doe")
        self.assertEqual(response.data["data"]["bio"], "Hi there")

    def test_patch_me_ignores_identity_fields(self):
        response = self.client.patch(
            "/api/accounts/me/",
            {
                "firebase_uid": "someone-else",
                "email": "hacked@example.com",
                "username": "hacked",
                "is_staff": True,
            },
            format="json",
            **self.auth_header,
        )
        self.assertEqual(response.status_code, 200)
        user = User.objects.get(email="alice@example.com")
        self.assertEqual(user.firebase_uid, "alice")
        self.assertFalse(user.is_staff)


class DeleteAccountTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.verify_patcher = patch("core.firebase_auth.auth.verify_id_token")
        mock_verify = self.verify_patcher.start()
        self.addCleanup(self.verify_patcher.stop)
        mock_verify.return_value = {"uid": "alice", "email": "alice@example.com"}
        self.auth_header = _auth_header("alice")
        self.client.get("/api/accounts/me/", **self.auth_header)

    @patch("accounts.views.firebase_auth_admin.delete_user")
    def test_delete_account_removes_firebase_and_local_user(self, mock_delete):
        response = self.client.delete(
            "/api/accounts/delete-account/", **self.auth_header
        )
        self.assertEqual(response.status_code, 200)
        mock_delete.assert_called_once_with("alice")
        self.assertFalse(User.objects.filter(firebase_uid="alice").exists())

    @patch("accounts.views.firebase_auth_admin.delete_user")
    def test_delete_account_removes_mood_entries(self, mock_delete):
        alice = User.objects.get(firebase_uid="alice")
        MoodEntry.objects.create(
            user_id=str(alice.id), emoji="😊", thoughts="entry", ai_response="ok"
        )
        MoodEntry.objects.create(
            user_id=str(alice.id), emoji="😔", thoughts="entry two", ai_response="ok"
        )
        response = self.client.delete(
            "/api/accounts/delete-account/", **self.auth_header
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(MoodEntry.objects.filter(user_id=str(alice.id)).count(), 0)

    @patch("accounts.views.firebase_auth_admin.delete_user")
    def test_delete_account_firebase_failure_returns_error_and_keeps_local_row(
        self, mock_delete
    ):
        alice = User.objects.get(firebase_uid="alice")
        MoodEntry.objects.create(
            user_id=str(alice.id), emoji="😊", thoughts="entry", ai_response="ok"
        )
        mock_delete.side_effect = Exception("network error")
        response = self.client.delete(
            "/api/accounts/delete-account/", **self.auth_header
        )
        self.assertEqual(response.status_code, 502)
        self.assertTrue(User.objects.filter(firebase_uid="alice").exists())
        self.assertEqual(MoodEntry.objects.filter(user_id=str(alice.id)).count(), 1)

    def test_unauthenticated_deletion_rejected(self):
        response = self.client.delete("/api/accounts/delete-account/")
        self.assertEqual(response.status_code, 401)
        self.assertTrue(User.objects.filter(firebase_uid="alice").exists())


class VerifyFirebaseTokenTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_missing_token_returns_400(self):
        response = self.client.post(
            "/api/auth/verify/", {}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    @patch("accounts.views.firebase_auth_admin.verify_id_token")
    def test_new_user_created_and_returns_flat_user_json(self, mock_verify):
        mock_verify.return_value = {
            "uid": "bob123",
            "email": "bob@example.com",
            "name": "Bob",
            "picture": "https://example.com/bob.png",
            "email_verified": True,
        }
        response = self.client.post(
            "/api/auth/verify/",
            {"firebase_token": "sometoken"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["firebase_uid"], "bob123")
        self.assertEqual(response.data["email"], "bob@example.com")
        self.assertEqual(response.data["name"], "Bob")
        self.assertTrue(response.data["is_new_user"])
        self.assertTrue(User.objects.filter(firebase_uid="bob123").exists())

    @patch("accounts.views.firebase_auth_admin.verify_id_token")
    def test_existing_user_reused_not_recreated(self, mock_verify):
        mock_verify.return_value = {"uid": "bob123", "email": "bob@example.com"}
        self.client.post(
            "/api/auth/verify/", {"firebase_token": "sometoken"}, format="json"
        )
        response = self.client.post(
            "/api/auth/verify/", {"firebase_token": "sometoken"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_new_user"])
        self.assertEqual(User.objects.filter(firebase_uid="bob123").count(), 1)

    @patch("accounts.views.firebase_auth_admin.verify_id_token")
    def test_invalid_token_returns_401(self, mock_verify):
        from firebase_admin.auth import InvalidIdTokenError

        mock_verify.side_effect = InvalidIdTokenError("bad token")
        response = self.client.post(
            "/api/auth/verify/", {"firebase_token": "bad"}, format="json"
        )
        self.assertEqual(response.status_code, 401)

    @patch("accounts.views.firebase_auth_admin.verify_id_token")
    def test_expired_token_returns_401(self, mock_verify):
        from firebase_admin.auth import ExpiredIdTokenError

        mock_verify.side_effect = ExpiredIdTokenError("expired", cause=None)
        response = self.client.post(
            "/api/auth/verify/", {"firebase_token": "expired"}, format="json"
        )
        self.assertEqual(response.status_code, 401)

    @patch("accounts.views.firebase_auth_admin.verify_id_token")
    def test_unexpected_error_returns_502(self, mock_verify):
        mock_verify.side_effect = Exception("network error")
        response = self.client.post(
            "/api/auth/verify/", {"firebase_token": "sometoken"}, format="json"
        )
        self.assertEqual(response.status_code, 502)


class DeleteUserByEmailCommandTests(TestCase):
    """Exercises the web-based account-deletion request path promised in
    templates/privacy.html for users who can't open the app: an operator
    runs `manage.py delete_user_by_email <email>` on request. These tests
    hit the real database directly (not the API), confirming the command
    itself actually removes the rows rather than trusting a mocked
    assertion."""

    @patch("accounts.services.firebase_auth_admin.delete_user")
    def test_deletes_user_and_mood_entries_for_real(self, mock_delete):
        user = User.objects.create(
            email="requester@example.com",
            firebase_uid="requester-uid",
            username="requester-uid",
        )
        MoodEntry.objects.create(
            user_id=str(user.id), emoji="😊", thoughts="entry one", ai_response="ok"
        )
        MoodEntry.objects.create(
            user_id=str(user.id), emoji="😔", thoughts="entry two", ai_response="ok"
        )
        user_id = user.id

        out = StringIO()
        call_command("delete_user_by_email", "requester@example.com", stdout=out)

        mock_delete.assert_called_once_with("requester-uid")
        self.assertFalse(User.objects.filter(id=user_id).exists())
        self.assertEqual(MoodEntry.objects.filter(user_id=str(user_id)).count(), 0)
        self.assertIn("Deleted account and journal entries", out.getvalue())

    def test_unknown_email_raises_command_error_and_deletes_nothing(self):
        with self.assertRaises(CommandError):
            call_command("delete_user_by_email", "nobody@example.com")

    @patch("accounts.services.firebase_auth_admin.delete_user")
    def test_firebase_failure_propagates_and_keeps_local_row(self, mock_delete):
        user = User.objects.create(
            email="keepme@example.com",
            firebase_uid="keepme-uid",
            username="keepme-uid",
        )
        mock_delete.side_effect = Exception("network error")

        with self.assertRaises(Exception):
            call_command("delete_user_by_email", "keepme@example.com")

        self.assertTrue(User.objects.filter(email="keepme@example.com").exists())
