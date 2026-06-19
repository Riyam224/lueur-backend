# Quickstart: Validating the Accounts & Authentication Module

Prerequisites: virtualenv activated, `pip install -r requirements.txt` run after the new dependencies (`djangorestframework-simplejwt`, `Pillow`) are added, `python manage.py migrate` run after `accounts` migrations exist.

```bash
export GROQ_API_KEY="unused-for-this-module-but-required-by-existing-settings"
python manage.py makemigrations accounts
python manage.py migrate
python manage.py runserver
```

## Scenario 1 — Register, get tokens, fetch profile (User Story 1 + 2)

```bash
curl -s -X POST http://localhost:8000/api/accounts/register/ \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"Str0ngPass!23","password_confirm":"Str0ngPass!23"}'
# Expect 201, data.access + data.refresh present, data.user.is_verified == false

ACCESS=$(... extract data.access from above ...)

curl -s http://localhost:8000/api/accounts/me/ -H "Authorization: Bearer $ACCESS"
# Expect 200, data.email == "alice@example.com"
```

**Validates**: spec.md User Story 1 acceptance scenarios 1 & 3; User Story 2 acceptance scenario 1; FR-001, FR-005, FR-006, FR-011.

## Scenario 2 — Duplicate registration rejected (User Story 1)

```bash
curl -s -X POST http://localhost:8000/api/accounts/register/ \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"Str0ngPass!23","password_confirm":"Str0ngPass!23"}'
# Expect 400, success: false, errors.email present
```

**Validates**: User Story 1 acceptance scenario 2; FR-002.

## Scenario 3 — Login, refresh, logout, refresh-reuse rejected (User Story 1)

```bash
curl -s -X POST http://localhost:8000/api/accounts/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"Str0ngPass!23"}'
REFRESH=$(... extract data.refresh ...)

curl -s -X POST http://localhost:8000/api/accounts/token/refresh/ \
  -H "Content-Type: application/json" -d "{\"refresh\":\"$REFRESH\"}"
# Expect 200, new data.access present

curl -s -X POST http://localhost:8000/api/accounts/logout/ \
  -H "Content-Type: application/json" -d "{\"refresh\":\"$REFRESH\"}"
# Expect 200

curl -s -X POST http://localhost:8000/api/accounts/token/refresh/ \
  -H "Content-Type: application/json" -d "{\"refresh\":\"$REFRESH\"}"
# Expect 401 — refresh token is blacklisted
```

**Validates**: User Story 1 acceptance scenarios 3, 5; FR-006, FR-007, FR-008; SC-004.

## Scenario 4 — Cross-user access denied (Success Criterion SC-002)

```bash
# Register a second user "bob", obtain bob's ACCESS_BOB.
curl -s http://localhost:8000/api/accounts/me/ -H "Authorization: Bearer $ACCESS_BOB"
# Expect bob's own data only — there is no endpoint that accepts another user's id,
# so this is validated structurally: confirm no view in accounts/urls.py takes a user-id path param.
```

**Validates**: FR-015; SC-002.

## Scenario 5 — Password change and reset flow (User Story 3)

```bash
curl -s -X POST http://localhost:8000/api/accounts/change-password/ \
  -H "Authorization: Bearer $ACCESS" -H "Content-Type: application/json" \
  -d '{"old_password":"Str0ngPass!23","new_password":"EvenStr0nger!45","new_password_confirm":"EvenStr0nger!45"}'
# Expect 200

curl -s -X POST http://localhost:8000/api/accounts/forgot-password/ \
  -H "Content-Type: application/json" -d '{"email":"alice@example.com"}'
# Expect 200 regardless of email existing (check server logs / mocked service call for the issued token in tests)

# In tests, the issued token is retrieved directly from PasswordResetToken.objects.last() (no real email sent).
curl -s -X POST http://localhost:8000/api/accounts/verify-reset-token/ \
  -H "Content-Type: application/json" -d '{"token":"<token-from-db>"}'
# Expect 200, data.valid == true

curl -s -X POST http://localhost:8000/api/accounts/reset-password/ \
  -H "Content-Type: application/json" \
  -d '{"token":"<token-from-db>","new_password":"Newest!67","new_password_confirm":"Newest!67"}'
# Expect 200; re-using the same token afterward must return 400
```

**Validates**: User Story 3 acceptance scenarios 1–5; FR-003, FR-009, FR-016, FR-017, FR-018; SC-003.

## Scenario 6 — Account deletion (User Story 3)

```bash
curl -s -X DELETE http://localhost:8000/api/accounts/delete-account/ -H "Authorization: Bearer $ACCESS"
# Expect 200

curl -s -X POST http://localhost:8000/api/accounts/login/ \
  -H "Content-Type: application/json" -d '{"email":"alice@example.com","password":"Newest!67"}'
# Expect 401 — account no longer exists
```

**Validates**: User Story 3 acceptance scenarios 6–7; FR-010; SC-006. (Account deletion does not touch `therapist.MoodEntry` — out of scope, see data-model.md "Cross-Module Note".)

## Scenario 7 — Email verification (User Story 4)

```bash
curl -s -X POST http://localhost:8000/api/accounts/send-verification-email/ -H "Authorization: Bearer $ACCESS_BOB"
# Token issued — fetch from EmailVerificationToken.objects.last() in tests

curl -s -X POST http://localhost:8000/api/accounts/verify-email/ \
  -H "Authorization: Bearer $ACCESS_BOB" -H "Content-Type: application/json" -d '{"token":"<token-from-db>"}'
# Expect 200; GET /me/ now shows is_verified: true
```

**Validates**: User Story 4 acceptance scenarios 1–4; FR-019, FR-020, FR-021.

## Scenario 8 — Rate limiting (FR-026, SC-007)

```bash
for i in $(seq 1 8); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/api/accounts/login/ \
    -H "Content-Type: application/json" -d '{"email":"nobody@example.com","password":"wrong"}'
done
# login/ allows 5 attempts per 5 minutes: expect the first 5 requests to return 401,
# and requests 6-8 (within the same 5-minute window) to return 429
```

**Validates**: FR-026; SC-007; the rate-limit edge case in spec.md Edge Cases.

## Automated equivalent

All of the above are expected to be encoded as `accounts/tests.py` cases using `APIClient`, with `send_password_reset_email`/`send_verification_email` mocked (per Constitution Principle IV) — `python manage.py test accounts` must pass before this feature is considered complete.
