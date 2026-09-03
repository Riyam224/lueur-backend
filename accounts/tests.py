from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from rest_framework.test import APIClient

from core.test_utils import make_v1_variant
from therapist.models import JournalEntry

from .admin import UserAdmin
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

    def test_default_preferred_language_is_english(self):
        user = User.objects.get(firebase_uid="alice")
        self.assertEqual(user.preferred_language, "en")

    def test_patch_me_updates_preferred_language(self):
        response = self.client.patch(
            "/api/accounts/me/",
            {"preferred_language": "ar"},
            format="json",
            **self.auth_header,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["preferred_language"], "ar")
        user = User.objects.get(firebase_uid="alice")
        self.assertEqual(user.preferred_language, "ar")

    def test_patch_me_rejects_invalid_preferred_language(self):
        response = self.client.patch(
            "/api/accounts/me/",
            {"preferred_language": "fr"},
            format="json",
            **self.auth_header,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("preferred_language", response.data["errors"])
        user = User.objects.get(firebase_uid="alice")
        self.assertEqual(user.preferred_language, "en")

    def test_patch_me_cannot_update_another_users_preferred_language(self):
        other_header = _auth_header("bob")
        with patch("core.firebase_auth.auth.verify_id_token") as mock_verify:
            mock_verify.return_value = {"uid": "bob", "email": "bob@example.com"}
            self.client.get("/api/accounts/me/", **other_header)

            response = self.client.patch(
                "/api/accounts/me/",
                {"preferred_language": "ar"},
                format="json",
                **other_header,
            )
        self.assertEqual(response.status_code, 200)

        alice = User.objects.get(firebase_uid="alice")
        bob = User.objects.get(firebase_uid="bob")
        self.assertEqual(alice.preferred_language, "en")
        self.assertEqual(bob.preferred_language, "ar")

    def test_default_gender_is_unset_for_new_users(self):
        user = User.objects.get(firebase_uid="alice")
        self.assertEqual(user.gender, "")

    def test_patch_me_updates_gender_to_male_or_female(self):
        for gender in ("male", "female"):
            response = self.client.patch(
                "/api/accounts/me/",
                {"gender": gender},
                format="json",
                **self.auth_header,
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["data"]["gender"], gender)
            user = User.objects.get(firebase_uid="alice")
            self.assertEqual(user.gender, gender)

    def test_patch_me_rejects_invalid_gender(self):
        response = self.client.patch(
            "/api/accounts/me/",
            {"gender": "robot"},
            format="json",
            **self.auth_header,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("gender", response.data["errors"])
        user = User.objects.get(firebase_uid="alice")
        self.assertEqual(user.gender, "")

    def test_patch_me_cannot_update_another_users_gender(self):
        other_header = _auth_header("bob-gender")
        with patch("core.firebase_auth.auth.verify_id_token") as mock_verify:
            mock_verify.return_value = {
                "uid": "bob-gender",
                "email": "bob-gender@example.com",
            }
            self.client.get("/api/accounts/me/", **other_header)

            response = self.client.patch(
                "/api/accounts/me/",
                {"gender": "male"},
                format="json",
                **other_header,
            )
        self.assertEqual(response.status_code, 200)

        alice = User.objects.get(firebase_uid="alice")
        bob = User.objects.get(firebase_uid="bob-gender")
        self.assertEqual(alice.gender, "")
        self.assertEqual(bob.gender, "male")

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
        JournalEntry.objects.create(
            user_id=str(alice.id), emoji="😊", thoughts="entry", ai_response="ok"
        )
        JournalEntry.objects.create(
            user_id=str(alice.id), emoji="😔", thoughts="entry two", ai_response="ok"
        )
        response = self.client.delete(
            "/api/accounts/delete-account/", **self.auth_header
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(JournalEntry.objects.filter(user_id=str(alice.id)).count(), 0)

    @patch("accounts.views.firebase_auth_admin.delete_user")
    def test_delete_account_firebase_failure_returns_error_and_keeps_local_row(
        self, mock_delete
    ):
        alice = User.objects.get(firebase_uid="alice")
        JournalEntry.objects.create(
            user_id=str(alice.id), emoji="😊", thoughts="entry", ai_response="ok"
        )
        mock_delete.side_effect = Exception("network error")
        response = self.client.delete(
            "/api/accounts/delete-account/", **self.auth_header
        )
        self.assertEqual(response.status_code, 502)
        self.assertTrue(User.objects.filter(firebase_uid="alice").exists())
        self.assertEqual(JournalEntry.objects.filter(user_id=str(alice.id)).count(), 1)

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
        JournalEntry.objects.create(
            user_id=str(user.id), emoji="😊", thoughts="entry one", ai_response="ok"
        )
        JournalEntry.objects.create(
            user_id=str(user.id), emoji="😔", thoughts="entry two", ai_response="ok"
        )
        user_id = user.id

        out = StringIO()
        call_command("delete_user_by_email", "requester@example.com", stdout=out)

        mock_delete.assert_called_once_with("requester-uid")
        self.assertFalse(User.objects.filter(id=user_id).exists())
        self.assertEqual(JournalEntry.objects.filter(user_id=str(user_id)).count(), 0)
        self.assertIn("Deleted account and journal entries", out.getvalue())

    def test_unknown_email_raises_command_error_and_deletes_nothing(self):
        with self.assertRaises(CommandError):
            call_command("delete_user_by_email", "nobody@example.com")

    @patch("accounts.services.firebase_auth_admin.delete_user")
    def test_firebase_failure_propagates_and_keeps_local_row(self, mock_delete):
        User.objects.create(
            email="keepme@example.com",
            firebase_uid="keepme-uid",
            username="keepme-uid",
        )
        mock_delete.side_effect = Exception("network error")

        with self.assertRaises(Exception):
            call_command("delete_user_by_email", "keepme@example.com")

        self.assertTrue(User.objects.filter(email="keepme@example.com").exists())


# /api/v1/... parity — same tests, run against the versioned prefix to
# confirm it behaves identically to the existing /api/... routes.
FirebaseAuthTestsV1 = make_v1_variant(FirebaseAuthTests)
ProfileTestsV1 = make_v1_variant(ProfileTests)
DeleteAccountTestsV1 = make_v1_variant(DeleteAccountTests)
VerifyFirebaseTokenTestsV1 = make_v1_variant(VerifyFirebaseTokenTests)


class UserAdminConfigTests(TestCase):
    def test_list_filter_and_ordering_configured(self):
        self.assertIn("is_active", UserAdmin.list_filter)
        self.assertIn("is_verified", UserAdmin.list_filter)
        self.assertIn("is_staff", UserAdmin.list_filter)
        self.assertIn("gender", UserAdmin.list_filter)
        self.assertEqual(UserAdmin.ordering, ("-created_at",))

    def test_journal_entry_count_reflects_actual_entries_and_links_to_filtered_list(self):
        user = User.objects.create(
            email="counted@example.com", username="counted", firebase_uid="counted-uid"
        )
        JournalEntry.objects.create(
            user_id=str(user.id), emoji="😊", thoughts="one", ai_response="ok"
        )
        JournalEntry.objects.create(
            user_id=str(user.id), emoji="😔", thoughts="two", ai_response="ok"
        )

        admin_instance = UserAdmin(User, None)
        result = admin_instance.journal_entry_count(user)

        self.assertIn("2", str(result))
        self.assertIn(str(user.id), str(result))


class UserAdminDeleteAccountActionTests(TestCase):
    """Exercises the admin "Delete account and journal entries" action.
    These assert directly against the database, not just mock calls, per
    the same pattern used in DeleteAccountTests above."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            email="admin@example.com", password="irrelevant"
        )
        self.client.force_login(self.superuser)
        self.user = User.objects.create(
            email="target@example.com",
            firebase_uid="target-uid",
            username="target-uid",
        )
        JournalEntry.objects.create(
            user_id=str(self.user.id), emoji="😊", thoughts="one", ai_response="ok"
        )
        JournalEntry.objects.create(
            user_id=str(self.user.id), emoji="😔", thoughts="two", ai_response="ok"
        )

    def _post_action(self, confirm=True):
        data = {
            "action": "delete_account_action",
            "_selected_action": [str(self.user.pk)],
        }
        if confirm:
            data["post"] = "yes"
        return self.client.post("/admin/accounts/user/", data, follow=True)

    @patch("accounts.services.firebase_auth_admin.delete_user")
    def test_confirmed_action_deletes_user_and_mood_entries_for_real(
        self, mock_delete
    ):
        user_id = self.user.id

        response = self._post_action(confirm=True)

        self.assertEqual(response.status_code, 200)
        mock_delete.assert_called_once_with("target-uid")
        self.assertFalse(User.objects.filter(id=user_id).exists())
        self.assertEqual(JournalEntry.objects.filter(user_id=str(user_id)).count(), 0)

    def test_unconfirmed_action_shows_confirmation_and_deletes_nothing(self):
        response = self._post_action(confirm=False)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(id=self.user.id).exists())
        self.assertContains(response, "target@example.com")

    @patch("accounts.services.firebase_auth_admin.delete_user")
    def test_firebase_failure_keeps_user_and_mood_entries_and_shows_error(
        self, mock_delete
    ):
        mock_delete.side_effect = Exception("network error")
        user_id = self.user.id

        response = self._post_action(confirm=True)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(id=user_id).exists())
        self.assertEqual(JournalEntry.objects.filter(user_id=str(user_id)).count(), 2)
        messages = [str(m) for m in response.context["messages"]]
        self.assertTrue(any("Failed to delete" in m for m in messages))
