# Tasks: Accounts & Authentication Module

**Input**: Design documents from `/specs/001-accounts-auth-module/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/accounts-api.md, quickstart.md (all present)

**Tests**: Included — Constitution Principle IV requires a test for every new/modified endpoint's success path and primary failure mode, and the original feature request explicitly asked for `tests.py` coverage.

**Organization**: Tasks are grouped by user story (spec.md priorities P1–P3) to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US4)
- All file paths are relative to the repository root

## Path Conventions

Single Django project (matches plan.md Project Structure): new `accounts/` app at repo root, alongside the existing `therapist/` app. `core/settings.py` and `core/urls.py` are modified, not created.

---

## Phase 1: Setup

**Purpose**: Scaffold the new app and register required dependencies

- [ ] T001 Run `python manage.py startapp accounts` at the repository root to create the `accounts/` app skeleton, then remove the unused default `accounts/views.py`/`accounts/models.py` boilerplate content (they will be rewritten in Phase 2/3)
- [ ] T002 [P] Add `djangorestframework-simplejwt` and `Pillow` to `requirements.txt`, pinned to current stable versions compatible with Django 5.1.4
- [ ] T003 Add `"accounts"`, `"rest_framework_simplejwt"`, and `"rest_framework_simplejwt.token_blacklist"` to `INSTALLED_APPS` in `core/settings.py` (depends on T001)

**Checkpoint**: `accounts` app exists and is installed; dependencies declared.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Custom user model, JWT config, shared utilities — required by every user story

**⚠️ CRITICAL**: `AUTH_USER_MODEL` MUST be set and the initial migration created before any other app migration that could reference the user model. No user-story work can begin until this phase is complete.

- [ ] T004 Set `AUTH_USER_MODEL = "accounts.User"` in `core/settings.py` (must precede T009's migration; local `db.sqlite3` is gitignored/dev-only per research.md §1, so this is safe to do now)
- [ ] T005 Create custom `UserManager` in `accounts/managers.py` with `create_user(email, password, **extra_fields)` and `create_superuser(...)`, using email (not username) as the required identifier
- [ ] T006 Create the `User` model in `accounts/models.py` extending `AbstractUser`, per data-model.md: `email` (unique, `USERNAME_FIELD`, `REQUIRED_FIELDS` adjusted so `username` is optional), `username` (unique, blank/null), `full_name`, `phone_number`, `bio`, `date_of_birth`, `gender` (choices), `profile_image` (`ImageField`, `upload_to="profile_images/"`), `is_verified` (default False), `created_at` (`auto_now_add`), `updated_at` (`auto_now`); wire `objects = UserManager()` (depends on T005)
- [ ] T007 Create `PasswordResetToken` and `EmailVerificationToken` models in `accounts/models.py` per data-model.md (FK to `User`, `token`, `created_at`, `expires_at`, `used_at`) (same file as T006 — sequential)
- [ ] T008 Register the custom `User` model in `accounts/admin.py` (basic `ModelAdmin` with list_display covering email, username, is_active, is_verified, is_staff)
- [ ] T009 Run `python manage.py makemigrations accounts` to generate `accounts/migrations/0001_initial.py`, then `python manage.py migrate` to confirm a clean migration against the dev SQLite DB (depends on T004, T006, T007)
- [ ] T010 Configure `SIMPLE_JWT` settings in `core/settings.py`: `ACCESS_TOKEN_LIFETIME = timedelta(minutes=15)`, `REFRESH_TOKEN_LIFETIME = timedelta(days=7)`, `ROTATE_REFRESH_TOKENS=True`, `BLACKLIST_AFTER_ROTATION=True`; add `"rest_framework_simplejwt.authentication.JWTAuthentication"` to `REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"]`
- [ ] T011 [P] Create reusable validators in `accounts/validators.py`: password strength (minimum 8 characters, at least one uppercase letter, one lowercase letter, and one number — FR-003), phone number format, profile-image content-type (JPG/JPEG/PNG/WEBP only) and size (max 5 MB) limits (FR-013)
- [ ] T012 [P] Create a shared response-envelope helper in `accounts/services.py` (`success_response(message, data)` / `error_response(message, errors)`) used by every view in this module (FR-023, FR-024), plus stub `send_password_reset_email(user, token)` / `send_verification_email(user, token)` functions (no-op/log only, per research.md §5 — designed to be mocked in tests and swapped for real delivery later)
- [ ] T013 [P] Create throttle classes in `accounts/throttling.py`: a per-IP throttle (using DRF's `AnonRateThrottle` base) and a per-account throttle keyed on the submitted email, with these exact scopes/rates (FR-026): `register` 5/5min, `login` 5/5min, `forgot-password` 3/15min, `verify-reset-token` 5/15min, `send-verification-email` 3/hour
- [ ] T014 Create `accounts/urls.py` with an empty `urlpatterns` list (populated per-story below), `include("accounts.urls")` under `path("api/accounts/", ...)` in `core/urls.py`, and add `MEDIA_URL = "/media/"` / `MEDIA_ROOT = BASE_DIR / "media"` to `core/settings.py` plus a `static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)` pattern in `core/urls.py` guarded by `if settings.DEBUG`
- [ ] T015 Add an `"Accounts"` entry to `SPECTACULAR_SETTINGS["TAGS"]` in `core/settings.py`, consistent with the existing `"Therapist"` tag

**Checkpoint**: Custom user model is migrated, JWT auth is configured, shared utilities exist — user story implementation can now begin.

> **Note**: No `accounts/permissions.py` is created. `IsOwner`/`IsVerifiedUser` were dropped per research.md §7 (revised) — every endpoint in this module operates on `request.user` directly, so neither class has a concrete call site (Constitution Principle V: no abstraction without a concrete use case).

---

## Phase 3: User Story 1 - Account Registration & Sign-In (Priority: P1) 🎯 MVP

**Goal**: A new user can register with email/password and is immediately signed in; a returning user can sign in, refresh their session, and sign out, with sign-out durably revoking the refresh token.

**Independent Test**: Register a new account, confirm signed-in tokens are returned; sign out and confirm the refresh token can no longer be used; sign back in with the same credentials.

### Tests for User Story 1

> Write these tests FIRST; they must FAIL before the corresponding implementation task is done.

- [ ] T016 [US1] Add `RegisterTests` to `accounts/tests.py`: successful registration returns 201 with tokens + user data; duplicate-email registration returns 400 with a field error; a password failing the strength policy (e.g., all-lowercase, no digit) is rejected (spec.md US1 scenarios 1–2; FR-003)
- [ ] T017 [US1] Add `LoginTests` to `accounts/tests.py`: correct credentials return 200 with tokens; incorrect password returns a generic 401 that doesn't reveal account existence (spec.md US1 scenarios 3–4)
- [ ] T018 [US1] Add `LogoutTests` to `accounts/tests.py`: logout blacklists the refresh token; a subsequent refresh attempt with that token returns 401 (spec.md US1 scenario 5; SC-004)
- [ ] T019 [US1] Add `TokenRefreshTests` to `accounts/tests.py`: a valid refresh token yields a new access token without re-authentication (FR-007)
- [ ] T020 [US1] Add `ThrottlingTests` to `accounts/tests.py`: the 6th request within 5 minutes to `register/` or `login/` returns HTTP 429 with the documented error envelope, while the first 5 are processed normally (FR-026, SC-007; spec.md Edge Cases rate-limit bullet)

### Implementation for User Story 1

- [ ] T021 [US1] Create `RegisterSerializer` (email, password, password_confirm, optional username; validates password match + strength via `accounts/validators.py`) in `accounts/serializers.py`
- [ ] T022 [US1] Create `LoginSerializer` (email, password) and `UserSerializer` (read-only: id, email, username, full_name, phone_number, bio, date_of_birth, gender, profile_image, is_verified, created_at, updated_at) in `accounts/serializers.py` (same file as T021 — sequential)
- [ ] T023 [US1] Create `LogoutSerializer` (single required `refresh` field) in `accounts/serializers.py` (same file as T021/T022 — sequential) — ensures `LogoutView` validates input via a serializer rather than reading `request.data` directly, per Constitution Principle II
- [ ] T024 [US1] Implement `RegisterView` (POST, unauthenticated, throttled) in `accounts/views.py`: validates via `RegisterSerializer`, creates the `User`, issues a token pair via SimpleJWT, returns the envelope from `accounts/services.py` with `user` + `access` + `refresh`
- [ ] T025 [US1] Implement `LoginView` (POST, unauthenticated, throttled) in `accounts/views.py`: authenticates via `LoginSerializer` + Django's `authenticate()` with `email` as the identifier, returns the same envelope shape as registration (same file as T024 — sequential)
- [ ] T026 [US1] Implement `LogoutView` (POST, authenticated) in `accounts/views.py`: validates the request body via `LogoutSerializer`, calls SimpleJWT's blacklist on the validated `refresh` token, returns success envelope; and a `CustomTokenRefreshView` (POST, unauthenticated) wrapping SimpleJWT's `TokenRefreshView` to apply the response envelope (same file — sequential)
- [ ] T027 [US1] Wire `register/`, `login/`, `logout/`, `token/refresh/` paths in `accounts/urls.py`, attaching the per-IP/per-account throttle scopes from `accounts/throttling.py` to `RegisterView` and `LoginView` (FR-026)

**Checkpoint**: User Story 1 is fully functional and independently testable — `python manage.py test accounts.tests.RegisterTests accounts.tests.LoginTests accounts.tests.LogoutTests accounts.tests.TokenRefreshTests accounts.tests.ThrottlingTests` passes.

---

## Phase 4: User Story 2 - Profile Management (Priority: P2)

**Goal**: A signed-in user can view and update their own profile and manage their profile photo; no user can view or edit another user's profile.

**Independent Test**: Sign in, fetch the current profile, update editable fields, confirm persistence; upload then remove a profile photo; confirm a second user cannot read or write the first user's profile.

### Tests for User Story 2

- [ ] T028 [US2] Add `ProfileTests` to `accounts/tests.py`: GET `/me/` returns full profile excluding password; PATCH updates editable fields and ignores/rejects attempts to change `email`/`is_staff`/etc.; a second authenticated user receives a rejection when targeting another user's profile data (spec.md US2 scenarios 1–3, 7)
- [ ] T029 [US2] Add `ProfileImageTests` to `accounts/tests.py`: a valid JPG/PNG/WEBP upload under 5 MB succeeds and is reflected in the profile; an unsupported format or a file over 5 MB is rejected with the prior image unchanged; removal clears the photo (spec.md US2 scenarios 4–6; FR-013)

### Implementation for User Story 2

- [ ] T030 [US2] Create `UserProfileUpdateSerializer` (full_name, phone_number, bio, date_of_birth, gender only — explicitly excludes email/is_staff/is_verified/etc.) in `accounts/serializers.py`
- [ ] T031 [US2] Create `ProfileImageSerializer` (single `image` field, validated via `accounts/validators.py` for type/size) in `accounts/serializers.py` (same file as T030 — sequential)
- [ ] T032 [US2] Implement `MeView` (GET returns `UserSerializer(request.user)`; PATCH validates via `UserProfileUpdateSerializer`, saves, returns updated `UserSerializer` data) in `accounts/views.py`, both authenticated and scoped to `request.user` only (FR-015)
- [ ] T033 [US2] Implement `ProfileImageView` (POST accepts `multipart/form-data`, validates via `ProfileImageSerializer`, saves to `request.user.profile_image`; DELETE clears `request.user.profile_image`) in `accounts/views.py` (same file as T032 — sequential)
- [ ] T034 [US2] Wire `me/` and `profile-image/` paths in `accounts/urls.py`

**Checkpoint**: User Stories 1 and 2 both work independently — profile retrieval/update/photo management is fully isolated per-account.

---

## Phase 5: User Story 3 - Password & Account Lifecycle Management (Priority: P2)

**Goal**: A signed-in user can change their password; a user who forgot their password can reset it via a single-use token; a user can permanently delete their own account.

**Independent Test**: Change password while signed in and confirm the old password stops working; request a reset, consume the token, sign in with the new password; delete the account and confirm sign-in afterward fails.

### Tests for User Story 3

- [ ] T035 [US3] Add `ChangePasswordTests` to `accounts/tests.py`: correct old password + valid new password (meeting the strength policy) succeeds and old password stops working; incorrect old password is rejected without changing anything (spec.md US3 scenarios 1–2; FR-003)
- [ ] T036 [US3] Add `PasswordResetTests` to `accounts/tests.py`, mocking `send_password_reset_email`: forgot-password always returns success regardless of email existing; verify-reset-token confirms validity; reset-password with a valid token succeeds and the token cannot be reused; an expired/used/invalid token is rejected without changing the password; the 4th `forgot-password/` request within 15 minutes and the 6th `verify-reset-token/` request within 15 minutes both return HTTP 429 (spec.md US3 scenarios 3–5; FR-026, SC-007)
- [ ] T037 [US3] Add `DeleteAccountTests` to `accounts/tests.py`: authenticated deletion removes the account and subsequent login fails; an unauthenticated/different-user deletion attempt is rejected (spec.md US3 scenarios 6–7; FR-010; SC-006)

### Implementation for User Story 3

- [ ] T038 [US3] Create `ChangePasswordSerializer` (old_password, new_password, new_password_confirm; validates old password against `request.user` and new password strength) in `accounts/serializers.py`
- [ ] T039 [US3] Create `ForgotPasswordSerializer` (email), `VerifyResetTokenSerializer` (token), `ResetPasswordSerializer` (token, new_password, new_password_confirm) in `accounts/serializers.py` (same file as T038 — sequential)
- [ ] T040 [US3] Implement token issuance/lookup/consumption helpers for `PasswordResetToken` in `accounts/services.py` (`issue_password_reset_token(user)`, `get_valid_password_reset_token(token)`, `consume_password_reset_token(token)`) per data-model.md state transitions
- [ ] T041 [US3] Implement `ChangePasswordView` (authenticated) and `DeleteAccountView` (authenticated, DELETE, deletes `request.user` only — does not touch `therapist.MoodEntry`, see data-model.md "Cross-Module Note") in `accounts/views.py`
- [ ] T042 [US3] Implement `ForgotPasswordView` (unauthenticated, throttled — always returns the same success message), `VerifyResetTokenView` (unauthenticated, throttled), and `ResetPasswordView` (unauthenticated) in `accounts/views.py`, using the T040 helpers (same file as T041 — sequential)
- [ ] T043 [US3] Wire `change-password/`, `delete-account/`, `forgot-password/`, `verify-reset-token/`, `reset-password/` paths in `accounts/urls.py`, attaching throttle scopes to `forgot-password/` and `verify-reset-token/` (FR-026)

**Checkpoint**: User Stories 1–3 all work independently — password recovery and account deletion are fully functional.

---

## Phase 6: User Story 4 - Email Verification (Priority: P3)

**Goal**: A registered user can request a verification message and confirm their email by submitting the resulting token, flipping their account's verified status.

**Independent Test**: Register (starts unverified), request verification, submit the issued token, confirm `is_verified` becomes true via `/me/`.

### Tests for User Story 4

- [ ] T044 [US4] Add `EmailVerificationTests` to `accounts/tests.py`, mocking `send_verification_email`: requesting verification issues a token for an unverified account; requesting again for an already-verified account responds gracefully without contradictory state; the 4th `send-verification-email/` request within an hour returns HTTP 429 (spec.md US4 scenarios 1, 4; FR-026, SC-007)
- [ ] T045 [US4] Extend `EmailVerificationTests`: submitting a valid token marks the account verified; submitting an expired/invalid token is rejected and the account remains unverified (spec.md US4 scenarios 2–3)

### Implementation for User Story 4

- [ ] T046 [US4] Create `VerifyEmailSerializer` (token) in `accounts/serializers.py` (send-verification-email takes no body)
- [ ] T047 [US4] Implement token issuance/lookup/consumption helpers for `EmailVerificationToken` in `accounts/services.py`, mirroring T040's shape (`issue_email_verification_token`, `get_valid_email_verification_token`, `consume_email_verification_token` — sets `user.is_verified = True`)
- [ ] T048 [US4] Implement `SendVerificationEmailView` (authenticated, throttled — no-ops gracefully if already verified) and `VerifyEmailView` (authenticated) in `accounts/views.py`
- [ ] T049 [US4] Wire `send-verification-email/` and `verify-email/` paths in `accounts/urls.py`, attaching a throttle scope to `send-verification-email/` (FR-026)

**Checkpoint**: All four user stories are independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, schema coverage, and final validation across all stories

- [ ] T050 [P] Add `@extend_schema` (drf-spectacular) annotations with request/response examples and auth requirements to every view in `accounts/views.py`, tagged `"Accounts"`, so all 15 endpoints from contracts/accounts-api.md appear correctly in `/api/docs/`
- [ ] T051 Run `python manage.py test accounts` and resolve any failures across all four stories' test classes
- [ ] T052 Execute quickstart.md scenarios 1–8 manually against `python manage.py runserver` to confirm end-to-end behavior, including the rate-limit scenario (8)
- [ ] T053 [P] Update `CLAUDE.md`: add an "Accounts" section to Application Structure/Key Components, list all 15 new endpoints under Full API Endpoints, and note the new `djangorestframework-simplejwt`/`Pillow` dependencies, per the Development Workflow convention of keeping `CLAUDE.md` in sync with observable behavior changes
- [ ] T054 Confirm `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` in `core/settings.py` still cover the deployed Railway domain after settings changes in Phase 1–2 (no regression to existing Security & Deployment Requirements)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories (custom user model must exist and be migrated first)
- **User Stories (Phase 3–6)**: All depend on Foundational phase completion
  - US1 has no dependency on US2–US4
  - US2, US3, US4 each depend only on Foundational (the `User` model), not on each other — but since all four stories edit the same `accounts/serializers.py`, `accounts/views.py`, `accounts/urls.py`, and `accounts/tests.py` files, they should be implemented sequentially (in priority order) by a single contributor, or carefully merged if split across contributors
- **Polish (Phase 7)**: Depends on all four user stories being complete

### Recommended Execution Order

P1 (US1) → P2 (US2) → P2 (US3) → P3 (US4) → Polish, matching spec.md priorities. US2 and US3 are both P2; US1's foundation (working auth) is required to test either, but they don't depend on each other's code — they are listed sequentially above only because they share files within this single-app structure.

### Parallel Opportunities

- **Phase 1**: T002 can run alongside T001/T003 (different file)
- **Phase 2**: T011, T012, T013 can all run in parallel once T006/T007 (models) exist — they're three independent new files with no cross-dependencies
- **Phase 7**: T050 and T053 can run in parallel (schema annotations vs. documentation, different files)
- Within each user story phase, implementation tasks are mostly sequential because they share `accounts/serializers.py`/`accounts/views.py`/`accounts/tests.py` — true file-level parallelism is limited by this project's existing one-file-per-concern convention (matches `therapist/` app structure)

---

## Parallel Example: Phase 2 (Foundational)

```bash
# After T006 (User model) and T007 (token models) are committed, run these three in parallel:
Task: "Create reusable validators in accounts/validators.py"
Task: "Create response-envelope helper in accounts/services.py"
Task: "Create throttle classes in accounts/throttling.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (custom user model, JWT, shared utilities)
3. Complete Phase 3: User Story 1 (register/login/logout/refresh)
4. **STOP and VALIDATE**: Run quickstart.md Scenarios 1–3 against a local server; confirm `accounts.tests.RegisterTests`/`LoginTests`/`LogoutTests`/`TokenRefreshTests` pass
5. This is a usable MVP: a Flutter client can register, sign in, and maintain a session — profile management and password recovery can ship as fast-follows

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add US1 → Test independently → MVP usable by Flutter client for auth-only flows
3. Add US2 → Test independently → Profile management available
4. Add US3 → Test independently → Password recovery + account deletion available (closes the "locked out forever" risk)
5. Add US4 → Test independently → Email verification available
6. Polish → Schema docs complete, `CLAUDE.md` updated, full quickstart validated

---

## Notes

- [P] tasks = different files, no dependencies — used sparingly here since this app deliberately follows the existing project's one-file-per-concern convention (single `serializers.py`/`views.py`/`tests.py`), which limits true file-level parallelism within a story
- Tests are written first per story and must fail before their corresponding implementation task
- Commit after each task or logical group
- Stop at any checkpoint to validate a story independently before continuing
- `accounts/services.py`'s email-sending stubs (T012) MUST be mocked in T036/T044 tests — no test may perform a real network call, per Constitution Principle IV
- No `accounts/permissions.py` exists in this task list — see the note after Phase 2's checkpoint
