# Phase 0 Research: Accounts & Authentication Module

All unknowns from the Technical Context have a concrete decision below; no `NEEDS CLARIFICATION` markers remain.

## 1. Custom user model strategy

- **Decision**: Define `accounts.User` extending `django.contrib.auth.models.AbstractUser` (not `AbstractBaseUser` from scratch), with `username` made optional/non-unique-required-off and `email` set as `USERNAME_FIELD`. Set `AUTH_USER_MODEL = "accounts.User"` in `core/settings.py` before the first `accounts` migration is created.
- **Rationale**: `AbstractUser` already provides `is_active`, `is_staff`, `is_superuser`, `password` hashing, `last_login`, and full compatibility with Django admin and `django.contrib.auth` permission machinery — all required attributes from the spec's Account entity. Building from `AbstractBaseUser` would mean re-implementing permission/group support with no added benefit for this spec's requirements.
- **Alternatives considered**: `AbstractBaseUser` + `PermissionsMixin` from scratch — rejected as unnecessary extra code for behavior `AbstractUser` already provides; a separate `Profile` model with a `OneToOneField` to the default `auth.User` — rejected because the spec requires `email` as the unique sign-in identifier, which default `auth.User` does not support cleanly (it does not enforce email uniqueness or use it as `USERNAME_FIELD`).
- **Timing constraint**: This must be done before any other migrations are applied. The local `db.sqlite3` is gitignored and contains no production data, so swapping `AUTH_USER_MODEL` now is safe; doing it later (after real user data exists in `auth_user`) is unsupported by Django without a manual data migration, which is out of scope.

## 2. JWT issuance, refresh, and blacklist

- **Decision**: Use `djangorestframework-simplejwt` with `rest_framework_simplejwt.token_blacklist` enabled (`INSTALLED_APPS`), `ACCESS_TOKEN_LIFETIME = timedelta(minutes=15)`, `REFRESH_TOKEN_LIFETIME = timedelta(days=7)`, `ROTATE_REFRESH_TOKENS = True`, `BLACKLIST_AFTER_ROTATION = True`. Logout endpoint blacklists the supplied refresh token via `RefreshToken(token).blacklist()`.
- **Rationale**: Matches the explicitly requested "SimpleJWT" tech stack, is the de facto standard DRF JWT library, and its `token_blacklist` app directly satisfies FR-008 (sign-out permanently invalidates the refresh token) without custom token-revocation storage.
- **Alternatives considered**: Plain DRF `TokenAuthentication` (single static token) — rejected, doesn't support short-lived access/long-lived refresh split required by FR-006/FR-007; hand-rolled JWT with `PyJWT` — rejected as reinventing rotation/blacklist logic that SimpleJWT already provides (Constitution Principle V: no new abstraction without a concrete need it doesn't already meet).

## 3. Rate limiting / throttling (FR-026)

- **Decision**: Use DRF's built-in throttling framework with custom throttle classes per scope, each enforcing both a per-IP rate (DRF's default `AnonRateThrottle` keying) and a per-account rate (a custom throttle keyed on the submitted email/identifier, since the requester isn't authenticated yet for most of these). Concrete rates (FR-026):

  | Scope | Rate |
  |---|---|
  | `register` | 5/5min |
  | `login` | 5/5min |
  | `forgot-password` | 3/15min |
  | `verify-reset-token` | 5/15min |
  | `send-verification-email` | 3/hour |
- **Rationale**: DRF throttling is already a dependency (no new package), configurable per-view via `throttle_classes`/`throttle_scope`, and integrates with the existing `REST_FRAMEWORK` settings dict already present in `core/settings.py`.
- **Alternatives considered**: `django-ratelimit` — rejected as an unnecessary added dependency when DRF's built-in throttling already covers the requirement; Redis-backed distributed throttling — rejected as premature for the project's current single-instance SQLite-dev/Railway-deploy scale (no demonstrated need per Constitution Principle V); default DRF cache backend (`LocMemCache`) is sufficient for now.

## 4. Profile photo storage & validation

- **Decision**: `ImageField(upload_to="profile_images/")` on the profile, validated in a serializer/`validators.py` function checking content-type against the allowed set (`image/jpeg`, `image/png`, `image/webp` — i.e., JPG/JPEG/PNG/WEBP) and file size against a 5 MB ceiling (FR-013). `Pillow` added as a dependency (required by Django's `ImageField`).
- **Rationale**: Matches the requested "Pillow for profile images," is the standard Django mechanism, and keeps storage local-filesystem-based in development per `MEDIA_URL`/`MEDIA_ROOT`, consistent with the spec's assumption that CDN/transformation pipelines are out of scope.
- **Alternatives considered**: Direct cloud storage (S3-compatible) integration — rejected as out of scope per spec Assumptions ("CDN/image-transformation pipelines are out of scope"); storing raw bytes in the database — rejected as a well-known anti-pattern for file storage in Django.

## 5. Password-reset / email-verification token lifecycle (no real email sending)

- **Decision**: Two short-lived, single-use token models (`PasswordResetToken`, `EmailVerificationToken`), each with `user` FK, opaque random token value (`secrets.token_urlsafe`), `created_at`, `expires_at`, `used_at` (nullable). A `services.py` function `send_password_reset_email(user, token)` / `send_verification_email(user, token)` is defined as the single integration seam but only logs/no-ops in this iteration (per spec Assumption: actual delivery out of scope), so tests can mock it and a real email backend can be substituted later without changing call sites.
- **Rationale**: Satisfies FR-016–FR-020 fully while honoring the spec's explicit scope boundary on email delivery; keeps the design "pluggable later" without building unused infrastructure now (Constitution Principle V).
- **Alternatives considered**: Django's built-in `PasswordResetTokenGenerator` (stateless, derives token from user state instead of storing it) — rejected because the spec requires an explicit single-use/expiry model independent of password-state changes, and a stored token makes "verify token before reset" (FR-017) and blacklist-style single-use semantics (FR-018) straightforward to test and reason about.

## 6. Response envelope consistency

- **Decision**: A small shared helper (`accounts/services.py` or a `core`-level utility) producing `{"success": bool, "message": str, "data": {...}}` / `{"success": false, "message": str, "errors": {...}}`, used by every view in this module via DRF `Response`.
- **Rationale**: Directly satisfies the requested consistent API response format and FR-023/FR-024, and gives the Flutter client (Dio + Repository pattern) one predictable shape to parse.
- **Alternatives considered**: A custom DRF exception handler that wraps all responses globally — rejected for this iteration since it would also reshape the existing `therapist` app's responses (out of scope, risk of regressing an unrelated, already-working module); scoping the helper to `accounts` views only avoids that blast radius.

## 7. Permissions (revised: `IsOwner`/`IsVerifiedUser` dropped)

- **Decision**: Do **not** create `accounts/permissions.py` or any custom permission class. Every endpoint in this spec operates exclusively on `request.user` (never an arbitrary object ID supplied by the client), so DRF's standard `IsAuthenticated` on authenticated views is the entire permission requirement — there is no object to compare ownership against, and no endpoint gates on verified-email status (per spec Assumptions, verification is informational-only).
- **Rationale**: The original input requested `IsOwner`/`IsVerifiedUser` classes, but neither has a concrete call site in this spec's 15 endpoints. Creating them anyway would be exactly the kind of unused abstraction Constitution Principle V prohibits ("new abstractions... require a concrete second use case before being introduced"). If a future feature needs object-level ownership checks (e.g., an admin endpoint listing other users' resources) or verified-gated actions, a permission class can be introduced then, against a real call site.
- **Alternatives considered**: Creating the classes now "for future use" — rejected per Principle V; keeping only `IsOwner` and dropping `IsVerifiedUser` — rejected because `IsOwner` is equally unused (every view already scopes via `request.user`, making an object-comparison permission class redundant, not just unused-for-now).

## 8. Account deletion and `therapist.MoodEntry` (rejected: no cascade)

- **Decision**: `DeleteAccountView` does NOT touch `therapist.MoodEntry` at all. Account deletion is scoped strictly to the `User` row and this module's own data (tokens, profile fields).
- **Verification performed**: Read `therapist/views.py`, `therapist/serializers.py`, `therapist/models.py` directly. `MoodEntry.user_id` is a plain `CharField` populated verbatim from `MoodEntryCreateSerializer.validated_data["user_id"]` — i.e., whatever string an unauthenticated client chooses to send (the `therapist` app has no authentication layer at all). There is no FK, no convention, and no existing code path that derives `user_id` from any account.
- **Rationale**: An earlier draft of this decision proposed matching `MoodEntry.user_id` against the deleted account's stringified primary key — but that was an invented convention, not something confirmed by the codebase. Adopting it now would either (a) silently delete nothing, since no existing `MoodEntry` row was created with that convention, or (b) require a client-side contract change to the `therapist` API that is outside this spec's control and unverified. Per the instruction to not assume an unconfirmed storage convention, this spec leaves `therapist.MoodEntry` untouched.
- **Alternatives considered**: Matching on `str(user.id)` going forward only — rejected as misleading (the cascade would appear to work in tests but silently fail to find any rows in real usage until/unless the Flutter client adopts the convention, which this spec cannot guarantee); adding a real FK migration to `therapist.MoodEntry` — rejected as out-of-scope schema churn on an already-working, unrelated app, better handled as its own explicit feature once a real linkage convention is established.
