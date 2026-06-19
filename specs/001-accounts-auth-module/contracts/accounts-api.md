# API Contract: Accounts & Authentication Module

Base path: `/api/accounts/`. All responses use the envelope below (see research.md §6).

**Success**: `{"success": true, "message": "<human-readable>", "data": {...}}`
**Error**: `{"success": false, "message": "<human-readable>", "errors": {"<field>": ["<reason>"]}}`

Authenticated endpoints require `Authorization: Bearer <access_token>`.

| # | Endpoint | Method | Auth | Throttled | FRs covered |
|---|---|---|---|---|---|
| 1 | `/register/` | POST | No | Yes | FR-001, FR-002, FR-003, FR-005, FR-006, FR-025, FR-026 |
| 2 | `/login/` | POST | No | Yes | FR-004, FR-006, FR-026 |
| 3 | `/logout/` | POST | Yes | No | FR-008 |
| 4 | `/token/refresh/` | POST | No (refresh token in body) | No | FR-007 |
| 5 | `/change-password/` | POST | Yes | No | FR-003, FR-009 |
| 6 | `/delete-account/` | DELETE | Yes | No | FR-010 |
| 7 | `/me/` | GET | Yes | No | FR-011 |
| 8 | `/me/` | PATCH | Yes | No | FR-012 |
| 9 | `/profile-image/` | POST | Yes | No | FR-013 |
| 10 | `/profile-image/` | DELETE | Yes | No | FR-014 |
| 11 | `/forgot-password/` | POST | No | Yes | FR-016, FR-026 |
| 12 | `/verify-reset-token/` | POST | No | Yes | FR-017, FR-026 |
| 13 | `/reset-password/` | POST | No | No* | FR-003, FR-018 |
| 14 | `/send-verification-email/` | POST | Yes | Yes | FR-019, FR-026 |
| 15 | `/verify-email/` | POST | Yes | No | FR-020 |

\* `reset-password` itself is not separately throttled because it requires a valid single-use token (already rate-limiting in effect via FR-018's invalidate-on-use behavior); `forgot-password` and `verify-reset-token` (the guessable/brute-forceable steps) are throttled.

All endpoints enforce FR-015 (owner-only access) implicitly: every authenticated action operates on `request.user`, never a client-supplied user identifier.

---

### 1. `POST /api/accounts/register/`

Request:
```json
{"email": "user@example.com", "password": "Str0ngPass!23", "password_confirm": "Str0ngPass!23", "username": "optional_handle"}
```
Success (201):
```json
{"success": true, "message": "Registration successful.", "data": {"user": {"id": 1, "email": "user@example.com", "username": "optional_handle", "is_verified": false, ...}, "access": "<jwt>", "refresh": "<jwt>"}}
```
Error (400) — duplicate email:
```json
{"success": false, "message": "Validation failed.", "errors": {"email": ["An account with this email already exists."]}}
```

### 2. `POST /api/accounts/login/`

Request: `{"email": "user@example.com", "password": "Str0ngPass!23"}`
Success (200): `{"success": true, "message": "Login successful.", "data": {"user": {...}, "access": "<jwt>", "refresh": "<jwt>"}}`
Error (401): `{"success": false, "message": "Invalid email or password.", "errors": {}}`

### 3. `POST /api/accounts/logout/`

Request: `{"refresh": "<jwt>"}`
Success (200): `{"success": true, "message": "Logged out successfully.", "data": {}}`
Error (400): `{"success": false, "message": "Invalid or expired refresh token.", "errors": {}}`

### 4. `POST /api/accounts/token/refresh/`

Request: `{"refresh": "<jwt>"}`
Success (200): `{"success": true, "message": "Token refreshed.", "data": {"access": "<jwt>", "refresh": "<jwt>"}}`
Error (401): `{"success": false, "message": "Refresh token invalid or expired.", "errors": {}}`

### 5. `POST /api/accounts/change-password/`

Auth required. Request: `{"old_password": "...", "new_password": "...", "new_password_confirm": "..."}`
Success (200): `{"success": true, "message": "Password changed successfully.", "data": {}}`
Error (400): `{"success": false, "message": "Validation failed.", "errors": {"old_password": ["Incorrect current password."]}}`

### 6. `DELETE /api/accounts/delete-account/`

Auth required. No body. Does not affect `therapist.MoodEntry` records (out of scope — see data-model.md "Cross-Module Note").
Success (200): `{"success": true, "message": "Account deleted permanently.", "data": {}}`

### 7–8. `GET` / `PATCH /api/accounts/me/`

Auth required.
GET success (200): `{"success": true, "message": "Profile retrieved.", "data": {"id": 1, "email": "...", "username": "...", "full_name": "...", "phone_number": "...", "bio": "...", "date_of_birth": "...", "gender": "...", "profile_image": "<url|null>", "is_verified": false, "created_at": "...", "updated_at": "..."}}`
PATCH request: `{"full_name": "...", "phone_number": "...", "bio": "...", "date_of_birth": "...", "gender": "..."}` (any subset; `email`/identifiers ignored if present)
PATCH success (200): same shape as GET, with updated fields.

### 9–10. `POST` / `DELETE /api/accounts/profile-image/`

Auth required. POST is `multipart/form-data` with field `image`.
POST success (200): `{"success": true, "message": "Profile image updated.", "data": {"profile_image": "<url>"}}`
POST error (400) — bad type/size: `{"success": false, "message": "Validation failed.", "errors": {"image": ["Unsupported image type." ]}}`
DELETE success (200): `{"success": true, "message": "Profile image removed.", "data": {"profile_image": null}}`

### 11. `POST /api/accounts/forgot-password/`

Request: `{"email": "user@example.com"}`
Success (200) — always, regardless of whether the email exists: `{"success": true, "message": "If an account exists for this email, a reset link has been sent.", "data": {}}`

### 12. `POST /api/accounts/verify-reset-token/`

Request: `{"token": "<token>"}`
Success (200): `{"success": true, "message": "Token is valid.", "data": {"valid": true}}`
Error (400): `{"success": false, "message": "Invalid or expired token.", "errors": {}}`

### 13. `POST /api/accounts/reset-password/`

Request: `{"token": "<token>", "new_password": "...", "new_password_confirm": "..."}`
Success (200): `{"success": true, "message": "Password reset successfully.", "data": {}}`
Error (400): `{"success": false, "message": "Invalid or expired token.", "errors": {}}`

### 14. `POST /api/accounts/send-verification-email/`

Auth required. No body.
Success (200): `{"success": true, "message": "Verification email sent.", "data": {}}`
Already-verified (200, graceful no-op per FR acceptance scenario): `{"success": true, "message": "Account is already verified.", "data": {}}`

### 15. `POST /api/accounts/verify-email/`

Auth required. Request: `{"token": "<token>"}`
Success (200): `{"success": true, "message": "Email verified successfully.", "data": {}}`
Error (400): `{"success": false, "message": "Invalid or expired verification token.", "errors": {}}`

---

## Rate limits (FR-026)

| Endpoint | Limit |
|---|---|
| `/register/` | 5 attempts / 5 minutes (per account + per IP) |
| `/login/` | 5 attempts / 5 minutes (per account + per IP) |
| `/forgot-password/` | 3 attempts / 15 minutes (per account + per IP) |
| `/verify-reset-token/` | 5 attempts / 15 minutes (per account + per IP) |
| `/send-verification-email/` | 3 attempts / hour (per account + per IP) |

## Rate-limit error shape (FR-026)

All throttled endpoints, when exceeded, return HTTP 429:
```json
{"success": false, "message": "Too many attempts. Please try again later.", "errors": {}}
```
