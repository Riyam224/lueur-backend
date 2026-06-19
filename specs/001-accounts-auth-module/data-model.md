# Phase 1 Data Model: Accounts & Authentication Module

## User (`accounts.User`, `AUTH_USER_MODEL`)

Extends Django's `AbstractUser`.

| Field | Type | Constraints / Notes |
|---|---|---|
| `id` | BigAutoField (PK) | Auto |
| `email` | EmailField | `unique=True`, `USERNAME_FIELD`, required |
| `username` | CharField | `unique=True`, `blank=True`, `null=True` — optional, never used for sign-in (FR-025) |
| `full_name` | CharField | `blank=True`, max_length 150 — replaces `first_name`/`last_name` usage in this module |
| `phone_number` | CharField | `blank=True`, validated by a reusable phone-format validator (FR-012, Validation section) |
| `bio` | TextField | `blank=True`, reasonable max length (e.g., 500 chars) |
| `date_of_birth` | DateField | `null=True`, `blank=True` |
| `gender` | CharField with `choices` | `blank=True`; free-text-safe enum (`male`, `female`, `other`, `prefer_not_to_say`) — reasonable default since spec doesn't constrain values |
| `profile_image` | ImageField | `upload_to="profile_images/"`, `null=True`, `blank=True` — validated for type/size at the serializer layer (FR-013) |
| `is_active` | BooleanField | Inherited from `AbstractUser`; tracked per FR-022, no toggle endpoint in this spec |
| `is_verified` | BooleanField | `default=False` — FR-021 |
| `is_staff` | BooleanField | Inherited from `AbstractUser` |
| `is_superuser` | BooleanField | Inherited from `AbstractUser` |
| `created_at` | DateTimeField | `auto_now_add=True` |
| `updated_at` | DateTimeField | `auto_now=True` |

**Validation rules**:
- Email uniqueness enforced at the DB level (`unique=True`) and re-checked in `RegisterSerializer` for a clean field-level error (FR-002).
- Password strength enforced via Django's `AUTH_PASSWORD_VALIDATORS` plus a project-specific minimum-strength validator reused across register/change-password/reset-password (FR-003).
- `email`, `is_active`, `is_verified`, `is_staff`, `is_superuser`, `id`, `created_at`, `updated_at` are never writable through the profile-update action (FR-012 acceptance scenario 3).

**Relationships**: One `User` has at most one set of profile fields (modeled as columns on `User` itself, not a separate table, per Assumptions — keeps a single round-trip for "get current user" / FR-011 and avoids an unnecessary `OneToOne` join for a 1:1, always-present relationship).

## PasswordResetToken

| Field | Type | Constraints / Notes |
|---|---|---|
| `id` | BigAutoField (PK) | Auto |
| `user` | ForeignKey(`User`) | `on_delete=CASCADE`, `related_name="password_reset_tokens"` |
| `token` | CharField | `unique=True`, opaque random value (`secrets.token_urlsafe(32)`) |
| `created_at` | DateTimeField | `auto_now_add=True` |
| `expires_at` | DateTimeField | Set at creation time (e.g., now + 1 hour) |
| `used_at` | DateTimeField | `null=True`, `blank=True` — set when consumed (FR-018) |

**State transitions**: `created` → (`verified`, no state change, read-only check per FR-017) → `used` (terminal, `used_at` set) **or** → `expired` (terminal, implicit via `expires_at < now`, no explicit field needed). A token is valid only when `used_at IS NULL AND expires_at > now`.

## EmailVerificationToken

| Field | Type | Constraints / Notes |
|---|---|---|
| `id` | BigAutoField (PK) | Auto |
| `user` | ForeignKey(`User`) | `on_delete=CASCADE`, `related_name="email_verification_tokens"` |
| `token` | CharField | `unique=True`, opaque random value |
| `created_at` | DateTimeField | `auto_now_add=True` |
| `expires_at` | DateTimeField | Set at creation time (e.g., now + 24 hours) |
| `used_at` | DateTimeField | `null=True`, `blank=True` — set when consumed |

**State transitions**: Same shape as `PasswordResetToken`. Consuming a valid token sets `used_at` and flips `User.is_verified = True` (FR-020) in the same transaction.

## Notes on entities deliberately not modeled

- No `CredentialSession`/refresh-token table is created directly by this app: `djangorestframework-simplejwt`'s `token_blacklist` app (`OutstandingToken`, `BlacklistedToken`) already models the "Credential Session" entity from the spec — adding a parallel table would duplicate state (Constitution Principle V).
- No deactivation/reactivation endpoint or audit table — per the resolved clarification, `is_active` is tracked but has no user-facing or admin-facing mutation path in this spec.
- No `IsOwner`/`IsVerifiedUser` permission classes — see research.md §7 (revised): neither has a concrete call site in this spec's endpoints, so neither is created.

## Cross-Module Note: Account Deletion does NOT touch `therapist.MoodEntry`

Deleting a `User` (FR-010) is scoped strictly to this module's own data. `therapist.MoodEntry.user_id` is a plain `CharField` populated from arbitrary, unauthenticated client-supplied input (per `therapist/views.py`/`models.py`), with no `ForeignKey` to `accounts.User` and no existing convention linking it to an account. Rather than invent an unverified matching rule, this spec leaves `MoodEntry` untouched on deletion — see research.md §8 for the full rationale and the rejected alternative.
