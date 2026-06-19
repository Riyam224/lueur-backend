# Feature Specification: Accounts & Authentication Module

**Feature Branch**: `001-accounts-auth-module`

**Created**: 2026-06-19

**Status**: Draft

**Input**: User description: "Build a complete production-ready Accounts/Auth module for my existing Django REST Framework backend that will be consumed by a Flutter mobile application. Supports registration, login, profile management, token-based authentication, password reset, email verification, and future social authentication integrations."

## Clarifications

### Session 2026-06-19

- Q: FR-022 tracks an active/inactive status but no flow sets it — should this spec add a deactivate/reactivate action, or keep it as an internal flag only? → A: Internal flag only — no deactivation/reactivation endpoint is in scope for this spec; only account deletion is user-facing.
- Q: Should login, registration, password-reset, and verification-request endpoints be rate-limited/throttled? → A: Yes — these endpoints MUST be rate-limited per account and per IP to mitigate brute-force and abuse.
- Decision: Access/refresh token lifetimes, password strength rule, profile-image size/format limits, and per-endpoint throttle thresholds are pinned to concrete values (see FR-003, FR-006, FR-013, FR-026) rather than left for planning to decide.
- Decision: Permanent account deletion (FR-010) does NOT cascade into the existing `therapist` module's `MoodEntry` records. `MoodEntry.user_id` is a free-text, client-supplied string with no existing link to any account (confirmed from `therapist/views.py`/`models.py`) — there is no reliable way to identify which rows belong to a given account today, so cleaning up mood-journal history on deletion is explicitly out of scope for this spec and deferred to a future feature once a real linkage convention exists.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Account Registration & Sign-In (Priority: P1)

A new user installs the mobile app, creates an account with their email and a password, and is immediately signed in. A returning user signs in with their email and password on a new device.

**Why this priority**: Without registration and sign-in, no other feature (mood tracking, profile, password reset) is reachable. This is the foundation the entire module depends on.

**Independent Test**: Can be fully tested by registering a new account with a unique email/password, confirming the account is created and the user is signed in, then signing out and signing back in with the same credentials.

**Acceptance Scenarios**:

1. **Given** no account exists for an email address, **When** the user submits a valid email, password, and matching password confirmation, **Then** an account is created, and the user is signed in without a separate login step.
2. **Given** an account already exists for an email address, **When** a new registration is attempted with that same email, **Then** the registration is rejected with a clear "email already in use" message and no duplicate account is created.
3. **Given** a registered account, **When** the user signs in with the correct email and password, **Then** the user is authenticated and receives their profile information along with credentials that keep them signed in across app restarts.
4. **Given** a registered account, **When** the user signs in with an incorrect password, **Then** sign-in is rejected with a generic invalid-credentials message that does not reveal whether the email exists.
5. **Given** a signed-in user, **When** the user signs out, **Then** their existing sign-in credentials stop working for future requests.

---

### User Story 2 - Profile Management (Priority: P2)

A signed-in user views their own profile, updates personal details (name, phone, bio, date of birth, gender), and uploads or removes a profile photo.

**Why this priority**: Once a user can authenticate, maintaining an accurate, personalized profile (including a photo) is the next most common action and is required before richer personalization features can be built on top of it.

**Independent Test**: Can be fully tested by signing in, retrieving the current profile, changing editable fields, confirming the changes persist, then uploading and removing a profile photo.

**Acceptance Scenarios**:

1. **Given** a signed-in user, **When** they request their own profile, **Then** they receive their full profile details (excluding their password).
2. **Given** a signed-in user, **When** they update their name, phone number, bio, date of birth, or gender, **Then** the changes are saved and reflected the next time the profile is retrieved.
3. **Given** a signed-in user, **When** they attempt to change their email or account identifiers through the profile update action, **Then** that attempt is ignored or rejected — those fields are not editable through this action.
4. **Given** a signed-in user, **When** they upload a valid image as their profile photo, **Then** the photo is stored and returned as part of their profile.
5. **Given** a signed-in user with an existing profile photo, **When** they remove it, **Then** their profile no longer shows a photo.
6. **Given** a signed-in user, **When** they upload a file that is not a valid image or exceeds the allowed size, **Then** the upload is rejected with a clear validation message and the existing photo (if any) is unchanged.
7. **Given** one user's profile, **When** a different signed-in user attempts to view or edit it, **Then** the request is rejected — users may only view and edit their own profile.

---

### User Story 3 - Password & Account Lifecycle Management (Priority: P2)

A signed-in user changes their password from within the app. A user who forgot their password requests a reset via email, follows the reset flow, and regains access. A user who no longer wants the account permanently deletes it.

**Why this priority**: Password recovery and change are essential safety-net features — without them, a single forgotten password permanently locks a user out, which is unacceptable for a production app. Account deletion is a core user-rights expectation.

**Independent Test**: Can be fully tested by changing a password while signed in and confirming the old password no longer works; separately, by requesting a password reset, completing it with a valid reset token, and signing in with the new password; separately, by deleting an account and confirming sign-in with its credentials no longer succeeds.

**Acceptance Scenarios**:

1. **Given** a signed-in user, **When** they submit their correct current password plus a new password and matching confirmation, **Then** the password is updated and future sign-ins require the new password.
2. **Given** a signed-in user, **When** they submit an incorrect current password, **Then** the change is rejected and the existing password remains active.
3. **Given** a user who forgot their password, **When** they request a password reset for their registered email, **Then** the system issues a reset token associated with that account without revealing whether the email is registered.
4. **Given** a valid, unexpired reset token, **When** the user submits it with a new password and confirmation, **Then** the password is updated and the token can no longer be reused.
5. **Given** an expired or already-used reset token, **When** the user attempts to reset their password with it, **Then** the reset is rejected with a clear error and the password is unchanged.
6. **Given** a signed-in user, **When** they request permanent account deletion, **Then** their account and associated profile data are removed and subsequent sign-in attempts with those credentials fail.
7. **Given** a deletion request, **When** it originates from anyone other than the authenticated account owner, **Then** the request is rejected.

---

### User Story 4 - Email Verification (Priority: P3)

A registered user requests a verification email and confirms their email address by submitting the verification code/token they received, marking their account as verified.

**Why this priority**: Verified-email status unlocks trust-sensitive actions and reduces fake/throwaway accounts, but the app must remain usable immediately after registration (per Assumptions), so this is lower priority than core auth and profile flows.

**Independent Test**: Can be fully tested by registering an account (starting unverified), requesting a verification email, submitting the resulting verification token, and confirming the account's verified status flips to true.

**Acceptance Scenarios**:

1. **Given** a registered but unverified account, **When** the user requests a verification email, **Then** a verification token is issued for that account.
2. **Given** a valid, unexpired verification token, **When** the user submits it, **Then** the account is marked verified.
3. **Given** an expired or invalid verification token, **When** the user submits it, **Then** verification is rejected with a clear error and the account remains unverified.
4. **Given** an already-verified account, **When** the user requests verification again, **Then** the system responds gracefully without creating a contradictory state.

---

### Edge Cases

- What happens when a user submits a registration, login, or profile request with a malformed or missing required field? The system MUST reject it with a field-level validation message, not a generic error.
- What happens when a user's sign-in credentials expire mid-session? The app MUST be able to obtain a new working credential without forcing the user to re-enter their password, as long as their refresh credential is still valid and not blacklisted.
- What happens when a user requests a password reset or email verification for an email address that has no registered account? The system MUST respond the same way as for a registered email (no account-existence disclosure).
- What happens when a user submits a new password during reset or change that does not meet the minimum strength policy? The request MUST be rejected with a specific strength-related message before any password is changed.
- What happens when two devices are signed in simultaneously and one signs out? Only that device's credentials are invalidated; the other device's session is unaffected.
- What happens when a profile photo upload is interrupted or fails partway? The previously stored photo (if any) MUST remain intact and unchanged.
- What happens when a deleted account's email is reused for a new registration? It MUST be treated as a brand-new registration with no link to the deleted account's prior data.
- What happens when a single account or IP exceeds the allowed rate of sign-in, registration, password-reset, or verification-request attempts? Further attempts within the current window MUST be rejected with a clear rate-limit error instead of being processed, until the window resets (see FR-026 for the specific limit and window per action).
- What happens to a deleted account's mood-journal history? Out of scope for this spec — `therapist.MoodEntry` records are not touched by account deletion (see Assumptions); no existing convention links them to an account.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow a new user to register an account using an email address and a password, with a password confirmation that must match.
- **FR-002**: System MUST reject registration when the supplied email is already associated with an existing account.
- **FR-003**: System MUST enforce a minimum password strength policy on registration, password change, and password reset — minimum 8 characters, including at least one uppercase letter, one lowercase letter, and one number — rejecting weak passwords with a specific reason.
- **FR-004**: System MUST authenticate users using email and password as the sign-in identifier, never username alone.
- **FR-005**: System MUST issue the signed-in user a working credential immediately upon successful registration, without requiring a separate sign-in step.
- **FR-006**: System MUST issue a renewable credential pair upon sign-in: an access credential valid for 15 minutes and a refresh credential valid for 7 days.
- **FR-007**: System MUST allow a user to obtain a new access credential using a valid, non-revoked refresh credential, without re-entering a password.
- **FR-008**: System MUST allow a signed-in user to sign out, after which their refresh credential is permanently invalidated and cannot be used to obtain new access credentials.
- **FR-009**: System MUST allow a signed-in user to change their password by providing their current password and a new password with confirmation, rejecting the change if the current password is incorrect.
- **FR-010**: System MUST allow a signed-in user to permanently delete their own account and all associated profile data; the action MUST only be performable by the account owner. (Out of scope: this does not cascade into the existing `therapist` module's `MoodEntry` records — see Assumptions.)
- **FR-011**: System MUST allow a signed-in user to retrieve their own complete profile information, excluding their password.
- **FR-012**: System MUST allow a signed-in user to update their own editable profile fields (full name, phone number, bio, date of birth, gender) without being able to alter their email or other account-identifying fields through the same action.
- **FR-013**: System MUST allow a signed-in user to upload a profile photo, validating that the uploaded file is one of the accepted formats (JPG, JPEG, PNG, WEBP) and no larger than 5 MB before storing it.
- **FR-014**: System MUST allow a signed-in user to remove their existing profile photo.
- **FR-015**: System MUST ensure that a user can only view or modify their own account and profile data — no user may access another user's account, profile, or photo through any of these actions.
- **FR-016**: System MUST allow any user to request a password reset for an email address, issuing a single-use reset token without revealing whether that email is registered.
- **FR-017**: System MUST allow a user to verify a password-reset token before submitting a new password, confirming the token is currently valid and unexpired.
- **FR-018**: System MUST allow a user holding a valid, unexpired, unused reset token to set a new password, and MUST invalidate that token immediately after use (or after expiry, whichever comes first).
- **FR-019**: System MUST allow a registered user to request a verification message for their email address, issuing a verification token.
- **FR-020**: System MUST allow a user to submit a valid, unexpired verification token to mark their account's email as verified.
- **FR-021**: System MUST track and expose a verification status on every account so that other features can distinguish verified from unverified users.
- **FR-022**: System MUST track and expose a per-account active/inactive status as an account attribute; this spec does NOT include a user-facing or admin-facing action to toggle it — the flag exists for future use, and account removal in this spec is handled exclusively via permanent deletion (FR-010).
- **FR-023**: System MUST respond to every action defined in this spec with a consistent, predictable result shape that distinguishes success from failure and carries either the resulting data or a description of what went wrong.
- **FR-024**: System MUST reject malformed or missing required fields on every action in this spec with field-level detail about what failed, rather than a generic failure message.
- **FR-025**: System MUST allow registration with an email-only identity; a separate username, if supplied, MUST also be unique but is not required and is never used as a sign-in identifier.
- **FR-026**: System MUST rate-limit the following actions per account and per originating IP address, rejecting excess attempts within the stated rolling window with a clear "too many attempts" response rather than processing them: registration (5 attempts per 5 minutes), sign-in (5 attempts per 5 minutes), password-reset request (3 attempts per 15 minutes), password-reset-token verification (5 attempts per 15 minutes), and email-verification request (3 attempts per hour).

### Key Entities

- **Account**: Represents a single registered user identity. Key attributes: unique email (primary sign-in identifier), optional unique username, password (never exposed), active status, email-verified status, administrative/staff status, creation and last-updated timestamps.
- **Profile Details**: Personal information attached one-to-one to an Account. Key attributes: full name, phone number, profile photo, bio, date of birth, gender. Editable only by the owning Account.
- **Credential Session**: Represents an active sign-in for an Account, made up of a short-lived access credential and a longer-lived refresh credential. A refresh credential can be invalidated (e.g., on sign-out) independently of other active sessions for the same Account.
- **Password Reset Request**: A single-use, time-limited token tied to one Account, created when a password reset is requested and consumed (or expired) when the reset completes.
- **Email Verification Request**: A single-use, time-limited token tied to one Account, created when verification is requested and consumed (or expired) when verification completes, resulting in the Account's verified status changing.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new user can complete registration and reach a signed-in state in under 30 seconds of active interaction.
- **SC-002**: 100% of attempts to access or modify another user's account, profile, or photo are rejected — zero cross-user data exposure incidents.
- **SC-003**: A user who forgets their password can regain account access via the reset flow without contacting support, in under 5 minutes end-to-end (excluding email delivery time).
- **SC-004**: A signed-out refresh credential can never be used again to obtain a new access credential — 100% of reuse attempts are rejected.
- **SC-005**: 95% of registration, sign-in, and profile-update attempts that fail validation return a specific, actionable error identifying the offending field.
- **SC-006**: Account deletion takes effect immediately — any sign-in attempt using a deleted account's credentials fails on the very next request after deletion completes.
- **SC-007**: 100% of sign-in, registration, password-reset, and verification-request attempts beyond the allowed rate for an account or IP are rejected rather than processed, with no successful brute-force or spam attempt observed in testing.

## Assumptions

- Email verification is informational/trust-building, not access-blocking: an unverified user can still sign in and use the app's core features (consistent with the existing therapist module's open `user_id` model); verification status is exposed so future features can optionally restrict themselves to verified users.
- Account deletion is a permanent hard delete, not a soft-delete/recovery-grace-period flow, matching the explicit "permanently delete" requirement in the input description.
- Actual email delivery (SMTP/provider integration) for password reset and verification messages is out of scope for this spec; this spec only covers the request/issue/consume token lifecycle, designed so a delivery mechanism can be plugged in later without changing the user-facing flow.
- Social authentication (e.g., Google/Apple sign-in) is explicitly out of scope for this iteration; this spec only ensures the Account model and sign-in flow don't preclude adding it later.
- Username, when supplied, is a unique display/handle field only — it never replaces email as the sign-in identifier and has no uniqueness interaction with email.
- "Profile photo" storage is a simple file association on the profile; CDN/image-transformation pipelines are out of scope.
- Existing therapist-module data isolation conventions (strict per-user scoping) extend conceptually to this module: every account/profile action is scoped to the requesting account.
- The `therapist.MoodEntry.user_id` field is a free-text `CharField`, populated directly from arbitrary client-supplied request data (`therapist/views.py`), with no foreign-key relationship or established convention linking it to any account. Because no reliable mapping exists today, account deletion (FR-010) deliberately does NOT attempt to clean up `MoodEntry` rows — doing so would either silently miss all existing data or require inventing an unverified matching convention. This is deferred to a future feature once the `therapist` app's client contract establishes a real link to authenticated accounts.
