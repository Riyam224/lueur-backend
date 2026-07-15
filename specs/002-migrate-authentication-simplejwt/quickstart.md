# Quickstart: Validating the Firebase Auth Migration

## Prerequisites

- `.venv` activated, `pip install -r requirements.txt` (after this feature lands, includes `firebase-admin`).
- `GROQ_API_KEY` set (unrelated to this feature, but `therapist/` tests still mock `generate_ai_response`/Groq calls per existing convention — no real key needed for automated tests, only for manually exercising `generate/` end-to-end).
- For automated tests: **no real Firebase project needed** — all tests mock `core.firebase_auth.auth.verify_id_token` / `.delete_user`.
- For manual/local end-to-end exercise only (optional): a real Firebase project, `FIREBASE_CREDENTIALS_PATH` pointing at a service-account JSON, and a real Firebase ID token obtained from a client SDK or the Firebase Auth REST API.

## Automated validation (primary path)

```bash
python manage.py check
python manage.py makemigrations --check --dry-run   # confirm no missing migration after model edits
python manage.py makemigrations
python manage.py migrate
python manage.py test accounts
python manage.py test therapist
python manage.py check --deploy
```

All six commands must exit 0. `test accounts` and `test therapist` must show zero references to `rest_framework_simplejwt` anywhere in output or code (`grep -rn "simplejwt\|SimpleJWT" --include=*.py .` should return nothing outside `.venv`).

## Scenario walkthroughs (map to spec.md User Stories)

### US1 — Authenticate via Firebase ID token

```python
# accounts/tests.py — illustrative shape, not full code
from unittest.mock import patch

@patch("core.firebase_auth.auth.verify_id_token")
def test_new_firebase_uid_creates_user(self, mock_verify):
    mock_verify.return_value = {"uid": "abc123", "email": "a@example.com"}
    resp = self.client.get("/api/accounts/me/", HTTP_AUTHORIZATION="Bearer faketoken")
    self.assertEqual(resp.status_code, 200)
    self.assertTrue(User.objects.filter(firebase_uid="abc123").exists())
```

Run: `python manage.py test accounts.tests.AccountsAuthTests.test_new_firebase_uid_creates_user` — expect pass.

### US2 — Manage own profile

`PATCH /api/accounts/me/` with `{"full_name": "New Name"}` under a valid mocked token → 200, `GET /me/` reflects the change. A `PATCH` with `{"firebase_uid": "other-uid"}` → 200 (ignored key), `firebase_uid` on the DB row unchanged — verify via `User.objects.get(pk=...).firebase_uid`.

### US3 — Delete own account

```python
@patch("core.firebase_auth.auth.delete_user")
@patch("core.firebase_auth.auth.verify_id_token")
def test_delete_account_removes_firebase_and_local_user(self, mock_verify, mock_delete):
    mock_verify.return_value = {"uid": "abc123", "email": "a@example.com"}
    self.client.get("/api/accounts/me/", HTTP_AUTHORIZATION="Bearer faketoken")  # creates user
    resp = self.client.delete("/api/accounts/delete-account/", HTTP_AUTHORIZATION="Bearer faketoken")
    self.assertEqual(resp.status_code, 200)
    mock_delete.assert_called_once_with("abc123")
    self.assertFalse(User.objects.filter(firebase_uid="abc123").exists())
```

### US4 — Therapist endpoints require auth + isolation

```python
@patch("core.firebase_auth.auth.verify_id_token")
@patch("therapist.views.generate_ai_response")
def test_generate_requires_auth_and_scopes_to_user(self, mock_ai, mock_verify):
    mock_ai.return_value = "Mocked reply"
    resp = self.client.post("/api/companion/generate/", {"emoji": "😊", "thoughts": "ok"}, format="json")
    self.assertEqual(resp.status_code, 401)  # no token

    mock_verify.return_value = {"uid": "u1", "email": "u1@example.com"}
    resp = self.client.post(
        "/api/companion/generate/", {"emoji": "😊", "thoughts": "ok"}, format="json",
        HTTP_AUTHORIZATION="Bearer faketoken",
    )
    self.assertEqual(resp.status_code, 200)
```

Then repeat `history/`/`weekly-letter/` with a second mocked `uid` and confirm no cross-user data appears (per spec.md US4 Acceptance Scenario 2).

## Manual smoke test (optional, real Firebase project)

1. Obtain a real Firebase ID token (e.g. via the Firebase Auth REST API `signInWithPassword` against a test user, or a throwaway Flutter/web client).
2. `export FIREBASE_CREDENTIALS_PATH=/path/to/service-account.json`
3. `curl -H "Authorization: Bearer <token>" http://localhost:8000/api/accounts/me/` → expect 200 with profile JSON and a new `accounts.User` row created in `db.sqlite3` on first call.
4. Re-run the same curl → expect the same user, no duplicate row.
5. `curl -H "Authorization: Bearer garbage" http://localhost:8000/api/accounts/me/` → expect 401.
