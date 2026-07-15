# API Contracts: Post-Migration Endpoint Surface

All endpoints below require `Authorization: Bearer <firebase-id-token>` unless noted. Missing/invalid/expired token → `401 Unauthorized`, body `{"detail": "..."}` (DRF default `AuthenticationFailed` shape — `accounts/`'s custom envelope is not used for auth failures since they happen before any view's `success_response`/`error_response` helper runs).

## `accounts/` — retained endpoints

### `GET /api/accounts/me/`

- **Auth**: required.
- **Request body**: none.
- **Response 200**: `{"success": true, "message": "Profile retrieved.", "data": {"id", "email", "username", "full_name", "phone_number", "bio", "date_of_birth", "gender", "is_verified", "created_at", "updated_at"}}` — `profile_image` removed from this shape; `firebase_uid` intentionally **not** exposed (internal linkage detail, not user-facing profile data).

### `PATCH /api/accounts/me/`

- **Auth**: required.
- **Request body**: any subset of `{"full_name", "phone_number", "bio", "date_of_birth", "gender"}`. Any other key (`firebase_uid`, `email`, `username`, `is_staff`, etc.) is silently ignored — never an error, never applied.
- **Response 200**: same shape as GET, reflecting applied changes.
- **Response 400**: `{"success": false, "message": "...", "errors": {...}}` on validation failure (e.g., bad `phone_number` format).

### `DELETE /api/accounts/delete-account/`

- **Auth**: required.
- **Request body**: none.
- **Process**: (1) read `request.user.firebase_uid`; (2) call `firebase_admin.auth.delete_user(firebase_uid)` if `firebase_uid` is set — log and raise on failure rather than proceeding silently; (3) delete the local `accounts.User` row; (4) return success.
- **Response 200**: `{"success": true, "message": "Account deleted permanently."}`.
- **Response 502/500** (new): if the Firebase-side deletion call fails, return an error response (exact status TBD at implementation — `502 Bad Gateway` fits "upstream identity provider failed" semantics) instead of `200`; the local Django row is **not** deleted in this case, so the account remains usable and deletion can be retried.

## `accounts/` — removed endpoints (return 404 — route no longer exists)

`register/`, `login/`, `logout/`, `token/refresh/`, `profile-image/`, `change-password/`, `forgot-password/`, `verify-reset-token/`, `reset-password/`, `send-verification-email/`, `verify-email/`.

## `therapist/` — modified contracts (auth added, `user_id` removed)

### `POST /api/companion/generate/`

- **Auth**: required (was: none).
- **Request body** (changed): `{"emoji": str, "thoughts": str, "history": [{"role", "content"}, ...] (optional, last 10 kept)}` — **`user_id` removed**; isolation key is `str(request.user.id)`.
- **Response 200**: unchanged shape (`MoodEntrySerializer` output: `id, user_id, emoji, thoughts, ai_response, created_at`) — `user_id` in the *response* now reflects `str(request.user.id)`, not a client value.
- **Response 401** (new): unauthenticated request.
- **Response 400**: unchanged — missing `emoji`/`thoughts`.

### `GET /api/companion/history/`

- **Auth**: required (was: none).
- **Query params** (changed): none required — **`user_id` query param removed**; isolation key is `str(request.user.id)`.
- **Response 200**: unchanged shape (list of `MoodEntrySerializer`), scoped to caller.
- **Response 401** (new): unauthenticated request.

### `GET /api/companion/weekly-letter/`

- **Auth**: required (was: none).
- **Query params** (changed): none required — **`user_id` query param removed**.
- **Response 200**: unchanged shape (`{"letter", "stats": {...}}` or `{"letter": null, "reason": "not_enough_entries"}`), scoped to caller.
- **Response 401** (new): unauthenticated request.
