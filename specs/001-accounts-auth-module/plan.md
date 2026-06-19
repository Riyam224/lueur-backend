# Implementation Plan: Accounts & Authentication Module

**Branch**: `001-accounts-auth-module` | **Date**: 2026-06-19 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-accounts-auth-module/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Add a new `accounts` Django app providing a custom email-based user model and a full account lifecycle (register, login, logout, token refresh, password change, password reset, email verification, account deletion) plus a self-service profile (including profile photo upload) — consumed by a Flutter mobile client over JSON REST. Authentication uses SimpleJWT access/refresh tokens with blacklisting on logout. Auth-sensitive endpoints are rate-limited via DRF throttling. The module follows the existing project's conventions: serializer-validated input, a consistent `{success, message, data|errors}` response envelope, drf-spectacular schema coverage, and mocked-external-dependency tests — with email delivery and social auth deliberately stubbed/excluded per the spec's documented scope.

## Technical Context

**Language/Version**: Python 3.11.9 (pinned via `runtime.txt`, matches existing project)

**Primary Dependencies**: Django 5.1.4, djangorestframework 3.17.1 (existing); `djangorestframework-simplejwt` (new — JWT issuance/refresh/blacklist); `Pillow` (new — required by `ImageField` for profile photos); drf-spectacular 0.27.2 (existing, extended to cover new endpoints)

**Storage**: SQLite for local development (existing `db.sqlite3`, gitignored, no production data — safe to introduce a custom user model now); PostgreSQL-compatible at the ORM level for production, consistent with the project's stated PostgreSQL-migration intent in `CLAUDE.md`

**Testing**: `django.test.TestCase` + DRF `APIClient`, matching the existing convention in `therapist/tests.py`; run via `python manage.py test accounts`

**Target Platform**: Linux server (Railway deployment, Gunicorn/WSGI), API consumed by a Flutter mobile app over HTTPS/JSON — no server-side rendering concerns for this module

**Project Type**: Web service (Django monolith) — new app added alongside the existing `therapist` app, not a separate service

**Performance Goals**: No new numeric targets beyond the spec's Success Criteria (SC-001–SC-007); standard synchronous DRF request/response latency is acceptable, consistent with the rest of the project

**Constraints**: Must replace Django's default `auth.User` with a custom model (`AUTH_USER_MODEL`) — must be done now, before any production data exists, since swapping the user model after migrations are applied against real data is unsupported by Django; must preserve the existing `therapist` app's behavior and its `user_id`-based data isolation untouched; per Constitution Principle V, no new config-abstraction dependency (e.g., `python-decouple`) is introduced when the existing `os.environ`-based settings pattern already covers the need

**Scale/Scope**: Single new Django app, 15 endpoints (per contracts/accounts-api.md), one custom user model + one profile-photo field + 2 short-lived token-tracking entities (password reset, email verification); scope matches the existing single small backend (no multi-tenant or admin-portal requirements introduced)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Data Isolation & Privacy** — PASS. Every account/profile endpoint operates on `request.user` only (FR-015); no endpoint accepts a client-supplied user identifier to look up another account. This is a stricter version of the existing `user_id`-scoping pattern (here enforced by authentication identity rather than a validated field), so it's compliant by construction. No object-level `IsOwner` permission class is introduced, since no endpoint in this spec performs an arbitrary-object lookup that would need one — see research.md §7 (revised).
- **II. Input & Contract Validation** — PASS (by design, must be upheld in implementation). All endpoints will use serializers for input; distinct read vs. write serializers (e.g., `UserProfileSerializer` for output, `RegisterSerializer`/`ProfileUpdateSerializer` for input) so read-only fields (`id`, `is_verified`, `is_staff`, timestamps) can never be client-supplied. New endpoints must appear in `/api/docs/` via drf-spectacular.
- **III. Resilient External AI Integration** — N/A. This module makes no calls to Groq or any AI service.
- **IV. Test Coverage for Critical Flows** — PASS (must be upheld). `accounts/tests.py` will cover success + primary failure mode for every endpoint; the email-sending step (out of scope per Assumptions) is represented by a stub/service function so tests can assert "token issued" without a real network call, keeping with the existing "always mock external calls" convention.
- **V. Simplicity & Statelessness** — PASS. Only two new dependencies are added (`djangorestframework-simplejwt`, `Pillow`), each solving a concrete, named requirement (JWT issuance/blacklist; image field validation) — no speculative abstraction layers. `python-decouple`/`dotenv`, requested in the original input, is intentionally **not** added: the existing `os.environ.get(..., default)` pattern in `core/settings.py` already satisfies the need, and adding a second config-loading mechanism would violate "no new abstraction without a concrete second use case." The originally-planned `accounts/permissions.py` (`IsOwner`, `IsVerifiedUser`) is also dropped for the same reason: no endpoint in this spec performs an object-level lookup or gates on verified status, so both classes would be unused abstractions (see research.md §7, revised). Documented in Complexity Tracking below for visibility.
- **Cross-module note (Principle I)**: FR-010 deliberately does NOT cascade into `therapist.MoodEntry`. Verified against `therapist/views.py`/`models.py`: `MoodEntry.user_id` is populated directly from arbitrary, unauthenticated client-supplied request data with no FK or established convention linking it to any account — there is no reliable way to identify which rows belong to a deleted account today. Inventing an unverified matching convention now would risk either silently deleting nothing (if the convention never gets adopted client-side) or being simply wrong. Deferred to a future feature once `therapist` has a real account-linkage convention. See spec.md Assumptions.

No violations requiring justification beyond the one documented deviation from the original request (decouple/dotenv), which is a simplification, not an added complexity.

## Project Structure

### Documentation (this feature)

```text
specs/001-accounts-auth-module/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   └── accounts-api.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
core/
├── settings.py           # MODIFIED: AUTH_USER_MODEL, SIMPLE_JWT, MEDIA_URL/ROOT, INSTALLED_APPS, throttling
└── urls.py                # MODIFIED: include accounts.urls, serve MEDIA_URL in DEBUG

accounts/                  # NEW Django app
├── __init__.py
├── apps.py
├── models.py              # User (custom AbstractUser-based), PasswordResetToken, EmailVerificationToken
├── managers.py             # Custom UserManager (email as USERNAME_FIELD)
├── serializers.py          # Register/Login/Profile(read+write)/ChangePassword/ForgotPassword/ResetPassword/VerifyEmail serializers
├── views.py                # APIViews for all 15 endpoints listed in contracts/accounts-api.md
├── urls.py                 # accounts/ URL patterns
├── validators.py           # password strength, phone format, image size/type
├── services.py             # token issuance/consumption helpers, email-send stub
├── throttling.py            # ScopedRateThrottle subclasses for auth-sensitive actions
├── admin.py                 # register custom User in admin
├── tests.py                  # success + failure path per endpoint, mocked external calls
└── migrations/
    └── 0001_initial.py

media/                      # NEW (gitignored): profile_images/ uploads in development
```

**Structure Decision**: Single Django project, new app added at repo root (`accounts/`) next to the existing `therapist/` app — matches the project's established single-project, multi-app layout (no separate frontend/backend split is needed; the Flutter client is an external consumer of the existing REST API surface, not part of this repository).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Deviation from original request: omit `python-decouple`/`dotenv` | N/A — this is a simplification, not an added violation | Original request asked for it, but the project already has a working `os.environ`-based settings pattern (Constitution Principle V forbids a second config-loading abstraction without a concrete need); noted here only for traceability against the input description |
