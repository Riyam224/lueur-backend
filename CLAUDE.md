# CLAUDE.md - Lueur Backend

Technical documentation for Claude Code to understand and work with this Django project.

## Project Overview

This is a Django REST Framework application that provides an AI-powered wellness companion API. It uses the **Groq API with the `openai/gpt-oss-20b` model** to generate empathetic responses to user mood inputs. The AI companion is named **Luna**.

## Architecture

### Application Structure

- **Django Project**: `core/` - Main project configuration
- **Django App**: `therapist/` - Main application handling journal entries and AI responses
- **Django App**: `accounts/` - Custom user model, Firebase-verified identity, and account/profile management
- **Database**: PostgreSQL on Railway (via `dj-database-url`/`psycopg2`), SQLite fallback for local dev
- **AI Service**: Groq API (external REST API) accessed via [therapist/ai_model.py](therapist/ai_model.py)
- **Auth**: Firebase Authentication — the Flutter client owns sign-in/sign-up/password-reset/email-verification/Google/Apple via Firebase; Django only verifies Firebase ID tokens via [core/firebase_auth.py](core/firebase_auth.py) and resolves them to `request.user`. Django never issues or refreshes tokens itself.
- **API Docs**: drf-spectacular (Swagger UI at `/api/docs/`, ReDoc at `/api/redoc/`)
- **Admin Theme**: `django-jazzmin` (`JAZZMIN_SETTINGS`/`JAZZMIN_UI_TWEAKS` in [core/settings.py](core/settings.py)) — replaces the stock Django admin look; branded "Lueur Admin"
- **Deployment**: Railway-ready with WhiteNoise for static files

### Key Components

1. **Model Layer** ([therapist/models.py](therapist/models.py))
   - `JournalEntry`: Stores user journal/activity entries (renamed from `MoodEntry`)
     - Fields: `user_id` (CharField, db_index), `entry_type` (`EntryType` choices: `mood_chat` (default), `breathing`, `sudoku`, `drawing`, `letter_read`), `emoji`, `thoughts`, `ai_response`, `payload` (JSONField, default `{}` — shape depends on `entry_type`: `breathing` → `{"duration_seconds"}`, `sudoku` → `{"solved", "duration_seconds", "difficulty"}`, `drawing` → `{"thumbnail_url"}`, `letter_read`/`mood_chat` → unused/`{}`), `crisis_flagged` (BooleanField, db_index, default `False`), `created_at`
     - `user_id` scopes all entries to a specific user — always `str(request.user.id)`, set server-side; never accepted from the client
     - Uses auto-generated timestamps (`auto_now_add=True`)
     - Composite index `(user_id, -created_at)` (`therapist_userid_created_idx`) backs the history/streak queries
     - String representation: `"{user_id} | {entry_type} - {emoji} {thoughts[:20]}"`
     - Meta: `verbose_name = "JournalEntry"`, `verbose_name_plural = "JournalEntries"`

2. **View Layer** ([therapist/views.py](therapist/views.py))
   - Uses **class-based APIView** (DRF); every view requires `permission_classes = [IsAuthenticated]` (authenticated via `core.firebase_auth.FirebaseAuthentication`)
   - `GenerateResponseAPIView`: POST-only endpoint
     - Throttled: `ScopedRateThrottle` (`ai_generate` scope) plus `LunaChatRateThrottle` (`luna_chat` scope) — see [therapist/throttles.py](therapist/throttles.py)
     - Validates input with `JournalEntryCreateSerializer` (`emoji`, `thoughts` required; `history` optional, max 20 items; optional `context_flag` — `user_id` is NOT accepted from the client)
     - Extracts last 10 items from `history` to cap context window
     - Runs bilingual crisis-language detection ([therapist/crisis.py](therapist/crisis.py) for English, [therapist/crisis_ar.py](therapist/crisis_ar.py) for Arabic) before ever calling Groq; on a hit, saves a `crisis_flagged=True` entry with a canned crisis response and returns immediately, skipping the AI call
     - Otherwise calls `generate_ai_response(emoji, thoughts, history, preferred_language, gender, memory_summary=..., context_flag=...)` from ai_model, passing the user's `preferred_language`/`gender`/stored `memory_summary`
     - On AI error: catches exception, saves a localized fallback message, still returns 200
     - Creates `JournalEntry` with `user_id=str(request.user.id)` and returns serialized data (200)
     - Luna may include `[SESSION_END]` tag in `ai_response` when the user feels resolved — this fires `trigger_memory_update(...)`, a fire-and-forget background thread that summarizes the session and updates `accounts.User.memory_summary` (see Cross-Session Memory below)
   - `ActivityEntryAPIView`: POST-only endpoint — logs a completed non-chat activity (`breathing`, `sudoku`, `drawing`, `letter_read`) via `ActivityEntryCreateSerializer`, which validates `payload` shape per `entry_type`; no AI response generated (201)
   - `AllHistoryAPIView`: GET-only endpoint
     - Returns entries filtered by `str(request.user.id)`, ordered by `created_at` DESC
   - `DeleteJournalEntryAPIView`: DELETE-only endpoint, `entries/<int:entry_id>/delete/` — deletes a single entry owned by the authenticated user (404 if not found/not owned)
   - `DeleteAllJournalEntriesAPIView`: DELETE-only endpoint, `entries/delete-all/` — throttled (`delete_all` scope, `DeleteAllJournalEntriesRateThrottle`); requires `{"confirm": true}` in the body (400 otherwise); deletes every entry owned by the user
   - `WeeklyLetterAPIView`: GET-only endpoint
     - Fetches last 7 days of entries for `str(request.user.id)` via `build_weekly_letter_context()` ([therapist/services.py](therapist/services.py))
     - Returns `{"letter": null, "reason": "not_enough_entries"}` if fewer than 2 entries
     - Calls `generate_weekly_letter(...)` (Groq, response cached 24h) to generate a personal weekly letter from Luna — may serve from cache if the nightly warm-up already ran for this user (see `generate_weekly_letters` management command below)
     - Returns letter text + stats (entry_count, dominant_emoji, streak, week_start, week_end)

3. **AI Service** ([therapist/ai_model.py](therapist/ai_model.py))
   - Function: `generate_ai_response(emoji, thoughts, history=None, preferred_language=None, gender=None, memory_summary=None, context_flag=None) -> str`
   - `history`: optional list of `{"role": "user"|"assistant", "content": "..."}` dicts — injected between system prompt and current user message for multi-turn context (windowed to the last 8 — `HISTORY_WINDOW`)
   - Uses **Groq API** (external cloud service), model: `openai/gpt-oss-20b` (`GROQ_MODEL`)
   - Requires `GROQ_API_KEY` environment variable
   - Makes REST POST to `https://api.groq.com/openai/v1/chat/completions`, with retry (2 attempts, 1s backoff) and a guard against empty content (gpt-oss can spend its whole token budget on internal reasoning and return nothing — that's treated as a failure so the caller falls back)
   - System prompt is built per-request by `LunaPromptProvider` ([therapist/luna_prompts.py](therapist/luna_prompts.py)), which is language-aware (`preferred_language`: `en`/`ar`) and, for Arabic, gender-aware (`gender`), and folds in the user's stored `memory_summary` and an optional `context_flag` (e.g. `post_exercise_breathing`)
   - Generation params: `temperature=0.85`, `max_tokens=400`, `reasoning_effort="low"`, `top_p=0.9`, `frequency_penalty=0.6`, `presence_penalty=0.5`
   - Before every Groq call, [therapist/groq_budget_guard.py](therapist/groq_budget_guard.py) reserves estimated token budget against Groq's free-tier limits using Django's cache framework as the counter store; a budget miss returns a localized fallback message without calling Groq
   - **No local model loading** — stateless, synchronous API calls (except the fire-and-forget memory-summary call, which runs on a background thread)

4. **Serializers** ([therapist/serializers.py](therapist/serializers.py))
   - `JournalEntrySerializer`: full read serializer — `fields = "__all__"`, `user_id`/`ai_response`/`created_at`/`id`/`crisis_flagged` read-only
   - `JournalEntryCreateSerializer`: write serializer for `generate/` — exposes `emoji`, `thoughts` (max 5000 chars), optional `history` (write-only, max 20 items), optional `context_flag` (write-only, currently only `post_exercise_breathing`) — `user_id` is not client-writable
   - `ActivityEntryCreateSerializer`: plain (non-model) serializer for `activity/` — `entry_type` (required, any `EntryType` except `mood_chat`) + `payload`, with per-`entry_type` payload validation

5. **Firebase Authentication** ([core/firebase_auth.py](core/firebase_auth.py))
   - `FirebaseAuthentication(BaseAuthentication)` — DRF authentication backend, set as the sole entry in `REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"]`
   - Reads `Authorization: Bearer <firebase-id-token>`; missing/empty → unauthenticated (401 via `IsAuthenticated`); calls `firebase_admin.auth.verify_id_token(token, check_revoked=True)` — any exception (invalid signature, expired, wrong audience) → `AuthenticationFailed` (401)
   - `check_revoked=True` closes a token-reuse gap: without it, a Firebase ID token issued before its account was deleted would stay valid until its natural (short) expiry even though the account is gone. With it, `verify_id_token` raises `UserNotFoundError` for a deleted account, which falls into the same generic exception handler above and correctly returns 401 immediately rather than waiting for expiry.
   - Resolves the verified `uid` to an `accounts.User` via `get_or_create(firebase_uid=uid, ...)`, auto-creating on first sight; if Firebase provides no email (phone/anonymous sign-in) a synthetic `f"{uid}@firebase.local"` is used to satisfy `User.email`'s uniqueness constraint
   - `firebase_admin.initialize_app(...)` is guarded by `if not firebase_admin._apps` and only runs when `FIREBASE_CREDENTIALS_PATH` is set, so `manage.py check`/`makemigrations`/non-auth tests work without real credentials (e.g. CI)
   - Registers a `drf_spectacular` `OpenApiAuthenticationExtension` so the OpenAPI schema documents the Bearer scheme correctly

6. **Accounts App** ([accounts/](accounts/)) — account/profile management only; Firebase owns all credential/identity flows
   - **Model** ([accounts/models.py](accounts/models.py)): `User` (`AUTH_USER_MODEL = "accounts.User"`, extends `AbstractUser`, email is `USERNAME_FIELD`, optional unique `username`, nullable unique indexed `firebase_uid`, `full_name`, `phone_number`, `bio`, `date_of_birth`, `gender`, `preferred_language` (`en`/`ar`, default `en`), `is_verified`, `memory_summary`/`memory_updated_at` — see Cross-Session Memory below). No `PasswordResetToken`/`EmailVerificationToken`/`profile_image` — removed in the Firebase migration.
   - **Manager** ([accounts/managers.py](accounts/managers.py)): `UserManager.create_user`/`create_superuser`, email-based (still used by `createsuperuser` for admin access; regular users are created via `FirebaseAuthentication`'s `get_or_create`)
   - **Views** ([accounts/views.py](accounts/views.py)): only `MeView` (GET/PATCH `/me/`) and `DeleteAccountView` (DELETE `/delete-account/`); every view operates on `request.user` only — no endpoint accepts another user's identifier. `DeleteAccountView` calls `firebase_admin.auth.delete_user(firebase_uid)` first; on failure it logs and returns `502` **without** deleting the local row (no orphaned Firebase identity)
   - **Serializers** ([accounts/serializers.py](accounts/serializers.py)): `UserSerializer` (read-only, full profile including `preferred_language`) and `UserProfileUpdateSerializer` (`full_name`, `phone_number`, `bio`, `date_of_birth`, `gender`, `preferred_language` only — `firebase_uid`/`email`/`username`/staff/memory fields are never in `Meta.fields`, so extra payload keys are silently ignored)
   - **Validators** ([accounts/validators.py](accounts/validators.py)): phone format only (password-strength and profile-image validators removed)
   - **Services** ([accounts/services.py](accounts/services.py)): `success_response`/`error_response` envelope helpers, plus account-deletion logic
   - **Response envelope**: every `accounts/` endpoint returns `{"success": bool, "message": str, "data": {...}}` or `{"success": false, "message": str, "errors": {...}}` — except auth failures, which return DRF's default `{"detail": "..."}` 401 shape (auth runs before any view code)

7. **Cross-Session Memory** ([therapist/ai_model.py](therapist/ai_model.py), [accounts/models.py](accounts/models.py))
   - `accounts.User` carries `memory_summary` (TextField, default `""`) and `memory_updated_at` (nullable DateTimeField)
   - When Luna's reply in `GenerateResponseAPIView` contains `[SESSION_END]` (`SESSION_END_TAG`), `trigger_memory_update(...)` spawns a daemon thread that builds a redacted transcript of the session (crisis-language content is replaced with `"(a difficult moment)"` before being sent to Groq), asks Groq for a short summary via `LunaPromptProvider.get_memory_summary_prompt(...)`, and overwrites `memory_summary`/`memory_updated_at` on success
   - This runs after the HTTP response is already sent, so it never adds latency to the request; a Groq budget miss or error just skips that turn's update (silently logged), leaving the prior `memory_summary` in place
   - The stored `memory_summary` is fed back into `generate_ai_response(...)`'s system prompt on every subsequent chat turn, giving Luna continuity across separate sessions

### URL Routing

- **Main URLs** ([core/urls.py](core/urls.py)):
  - `/` → Home page (`templates/index.html`)
  - `/admin/` → Django admin interface (Jazzmin theme)
  - `/api/companion/` and `/api/v1/companion/` → Includes companion (therapist) app URLs (dual-routed, see below)
  - `/api/accounts/` and `/api/v1/accounts/` → Includes accounts app URLs (dual-routed, see below)
  - `/api/auth/verify/` and `/api/v1/auth/verify/` → `VerifyFirebaseTokenView` directly (legacy path kept for the existing Flutter client; identical to `/api/accounts/verify/`)
  - `/api/schema/` → OpenAPI schema
  - `/api/docs/` → Swagger UI
  - `/api/redoc/` → ReDoc UI
  - `/health/` → Health check (`{"status": "ok"}`, no auth)

  **Dual-routing (`/api/v1/`)**: `core/urls.py` registers every `companion`/`accounts`/`auth` route twice — once unprefixed (`/api/...`) and once under `/api/v1/...` — both `include()`s pointing at the same app `urls.py` and the same views. This is a temporary migration step so deployed app versions that haven't switched to `/api/v1/` yet keep working; `/api/v1/` is the path new clients should use. The unprefixed routes should be removed once all deployed app versions have migrated.

- **Therapist URLs** ([therapist/urls.py](therapist/urls.py)):
  - `generate/` → `GenerateResponseAPIView` (POST only, auth + throttled required)
  - `history/` → `AllHistoryAPIView` (GET only, auth required)
  - `weekly-letter/` → `WeeklyLetterAPIView` (GET only, auth required)
  - `activity/` → `ActivityEntryAPIView` (POST only, auth required)
  - `entries/delete-all/` → `DeleteAllJournalEntriesAPIView` (DELETE only, auth + throttled required)
  - `entries/<int:entry_id>/delete/` → `DeleteJournalEntryAPIView` (DELETE only, auth required)

- **Accounts URLs** ([accounts/urls.py](accounts/urls.py)): see Full API Endpoints below

### Full API Endpoints

All endpoints below require `Authorization: Bearer <firebase-id-token>` and are scoped to `request.user`, **except** `POST /api/accounts/verify/` (and its legacy alias `/api/auth/verify/`), which is `AllowAny` since it's called immediately after Firebase sign-in, before the client has anything to send as a Bearer token. Missing/invalid/expired token → `401 Unauthorized` on every other endpoint.

- `POST /api/accounts/verify/` (alias: `POST /api/auth/verify/`) — Verify a Firebase ID token and create/return the linked Django user (no auth required)
- `POST /api/companion/generate/` — Create a mood-chat journal entry with an AI response, scoped to `request.user` (throttled: `ai_generate` + `luna_chat` scopes)
- `POST /api/companion/activity/` — Log a completed non-chat activity entry (breathing/sudoku/drawing/letter_read), scoped to `request.user`
- `GET /api/companion/history/` — Retrieve all entries for the authenticated user
- `GET /api/companion/weekly-letter/` — Get Luna's weekly letter for the authenticated user
- `DELETE /api/companion/entries/<id>/delete/` — Delete a single journal entry owned by the authenticated user
- `DELETE /api/companion/entries/delete-all/` — Delete every journal entry owned by the authenticated user (requires `{"confirm": true}`; throttled: `delete_all` scope)
- `GET /api/accounts/me/` — Get the authenticated user's profile
- `PATCH /api/accounts/me/` — Update editable profile fields (`full_name`, `phone_number`, `bio`, `date_of_birth`, `gender`, `preferred_language` only)
- `DELETE /api/accounts/delete-account/` — Delete the user's Firebase identity and local account permanently

Registration, login, logout, token refresh, password reset, email verification, and profile-image upload are no longer Django endpoints — they're handled entirely by Firebase Auth (and Firebase Storage for photos) on the Flutter client.

## Development Conventions

### Code Style

- Arabic comments present in codebase — maintain when editing existing comments
- PEP 8 compliant
- Django naming conventions followed
- DRF best practices applied (class-based views, serializers)

### Database

- SQLite for development (file: `db.sqlite3`)
- Migrations managed in standard Django way
- Model uses auto-timestamps (`auto_now_add=True`)

### Dependencies

**Core** ([requirements.txt](requirements.txt)):
- `Django==5.1.4` — Web framework
- `django-jazzmin==3.0.5` — Admin theme ("Lueur Admin")
- `djangorestframework==3.17.1` — REST API
- `drf-spectacular==0.27.2` — OpenAPI schema + Swagger/ReDoc (branded "Lueur API" in [core/settings.py](core/settings.py) `SPECTACULAR_SETTINGS`)
- `requests==2.33.0` — HTTP client for Groq API calls
- `gunicorn==25.3.0` — Production WSGI server
- `whitenoise==6.5.0` — Static file serving for production
- `certifi==2026.2.25` — SSL certificate bundle
- `firebase-admin>=6.5,<7` — verifies Firebase ID tokens, deletes Firebase users server-side
- `dj-database-url==3.1.2` / `psycopg2-binary==2.9.12` — PostgreSQL connection for Railway
- `django-cors-headers==4.9.0` — CORS support (see Security Considerations)
- `sentry-sdk==2.64.0` — error monitoring (see Security Considerations)
- `python-dotenv==1.0.1` — loads a local `.env` file into environment variables for development convenience (not used/needed in production, where Railway sets real env vars)

**Note**: No `torch` or `transformers` — uses external API instead of local model. All settings are read via `os.environ.get(..., default)`; `python-dotenv`'s `load_dotenv()` is called at the top of [core/settings.py](core/settings.py) to load a local `.env` file into those environment variables for development convenience — Railway's production environment sets real env vars directly, so dotenv is a local-only convenience layer, not a replacement for the `os.environ.get()` pattern. No `Pillow` — profile photos are now stored in Firebase Storage by the client, not Django.

### Testing

- Therapist test file: [therapist/tests.py](therapist/tests.py) — run with `python manage.py test therapist`; mock `generate_ai_response()` to avoid real Groq calls and `core.firebase_auth.auth.verify_id_token` to avoid real Firebase calls
- Accounts test file: [accounts/tests.py](accounts/tests.py) — run with `python manage.py test accounts`; mock `core.firebase_auth.auth.verify_id_token` for every authenticated request and `accounts.views.firebase_auth_admin.delete_user` for delete-account tests — no real Firebase project needed

Example:
```python
from unittest.mock import patch
from django.test import TestCase
from rest_framework.test import APIClient

class TherapistAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        patcher = patch("core.firebase_auth.auth.verify_id_token")
        self.mock_verify = patcher.start()
        self.addCleanup(patcher.stop)
        self.mock_verify.return_value = {"uid": "test-uid", "email": "t@example.com"}

    @patch('therapist.views.generate_ai_response')
    def test_create_mood_entry(self, mock_generate):
        mock_generate.return_value = "Mocked AI response"
        response = self.client.post(
            '/api/companion/generate/',
            {'emoji': '😊', 'thoughts': 'Great day!'},
            format='json',
            HTTP_AUTHORIZATION="Bearer faketoken",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('ai_response', response.data)
```

## Common Tasks

### Adding New Features

1. **Database Changes**: Modify [therapist/models.py](therapist/models.py), then run:

   ```bash
   python manage.py makemigrations && python manage.py migrate
   ```

2. **API Changes**: Update [therapist/serializers.py](therapist/serializers.py) if needed, add/modify views in [therapist/views.py](therapist/views.py), add routes in [therapist/urls.py](therapist/urls.py).

3. **AI Service Changes**: Modify [therapist/ai_model.py](therapist/ai_model.py). No server restart needed (stateless calls).

### Working with the AI Service

**Important Notes**:
- Uses **Groq API** — requires `GROQ_API_KEY` environment variable
- No local model loading — each request makes an API call
- API calls are synchronous — blocks request until complete
- Typical response time: 1–2 seconds
- Requires internet connection

**Generation Function**:
```python
generate_ai_response(
    emoji: str, thoughts: str, history: list = None,
    preferred_language: str = None, gender: str = None,
    memory_summary: str = None, context_flag: str = None,
) -> str
```

- `history`: list of `{"role": "user"|"assistant", "content": "..."}` message dicts (optional, windowed to last 8)
- Makes POST request to Groq API
- Uses `openai/gpt-oss-20b` model
- Returns AI-generated response text; may include `[SESSION_END]` tag at the end
- Raises exceptions on failure — caller must handle

### Weekly Letter Cache Warm-Up

- Management command: `python manage.py generate_weekly_letters` ([therapist/management/commands/generate_weekly_letters.py](therapist/management/commands/generate_weekly_letters.py))
- For every user with at least 2 `JournalEntry` rows in the last 7 days, calls `warm_weekly_letter_cache(user_id)` ([therapist/services.py](therapist/services.py)) to pre-generate and cache that user's weekly letter (same 24h Groq response cache `WeeklyLetterAPIView` reads from), so the endpoint serves from cache during the day instead of making a live Groq call
- Intended to run nightly via Railway Cron — the schedule itself is configured in the Railway dashboard/service settings, not in this repo ([railway.json](railway.json) only configures the build command)

### Security Considerations

**Current State** ([core/settings.py](core/settings.py)):
- ✅ `SECRET_KEY` uses environment variable with fallback
- ✅ `DEBUG` uses environment variable (defaults to False)
- ✅ `ALLOWED_HOSTS` is a specific allowlist, not a wildcard: `["web-production-f8628.up.railway.app", "127.0.0.1", ".railway.app"]` — **update the first entry if the Railway app domain changes**
- ✅ `CSRF_TRUSTED_ORIGINS` includes the deployed Railway domain (`https://web-production-f8628.up.railway.app`) — **update this if the Railway app domain changes**
- ✅ WhiteNoise configured for secure static file serving
- ✅ Identity comes exclusively from a verified Firebase ID token (`request.user`, set by `core.firebase_auth.FirebaseAuthentication`) — no endpoint accepts a client-supplied user identifier from the request body or query parameters
- ✅ Every `therapist/` and `accounts/` endpoint (except `verify/`) requires authentication and is scoped to `request.user`
- ✅ Rate limiting: DRF `UserRateThrottle` as the default throttle class, with four scopes defined in `settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]` — `user: 60/minute` (default), `ai_generate: 20/minute` (`GenerateResponseAPIView`), `luna_chat: 20/min` (`LunaChatRateThrottle`, also on `GenerateResponseAPIView`), `delete_all: 5/minute` (`DeleteAllJournalEntriesAPIView`); custom scope classes live in [therapist/throttles.py](therapist/throttles.py)
- ✅ Sentry (`sentry_sdk.init(...)`, gated on `SENTRY_DSN` and skipped under `TESTING`) is configured with `send_default_pii=False`, `include_local_variables=False` (Python captures stack-frame local variable values by default, which would otherwise leak journal/chat content on an exception even with request-body redaction in place), and a `before_send` hook that redacts any dict key in `_SENTRY_REDACT_FIELDS = {"thoughts", "content", "ai_reply", "transcript", "memory_summary"}` from `event["request"]["data"]`
- ✅ TLS/cookie hardening — `SECURE_SSL_REDIRECT`, `SECURE_PROXY_SSL_HEADER`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` (all `True`), and `SECURE_HSTS_SECONDS = 31536000` are set whenever `not DEBUG and not TESTING`, so local development (where `DEBUG=True`) is unaffected
- ⚠️ `ALLOWED_HOSTS` includes the leading-dot entry `.railway.app`, which matches *any* subdomain of `railway.app` (Django's leading-dot wildcard), not just this app's own Railway domain — broader than strictly necessary, though far from the `["*"]`-allows-everything state this file previously (incorrectly) described
- ⚠️ `JournalEntry` rows created before the Firebase migration (under the old client-supplied `user_id` scheme) are permanently inaccessible through the now-authenticated endpoints — accepted, documented tradeoff, not a bug (see `specs/002-migrate-authentication-simplejwt/spec.md` Edge Cases)

**Environment Variables Required**:
- `GROQ_API_KEY` — **Required** for AI functionality
- `FIREBASE_CREDENTIALS_PATH` — **Required** for Firebase token verification (path to a service-account JSON); without it, authenticated requests fail at first use, but `manage.py check`/`makemigrations`/non-auth tests still run
- `SECRET_KEY` — Optional (has fallback for dev; used by Django's session/CSRF signing — set a strong value in production)
- `DEBUG` — Optional (defaults to False)

### Running Commands

**Development**:
```bash
export GROQ_API_KEY="your-api-key-here"
python manage.py runserver
python manage.py migrate
python manage.py makemigrations
python manage.py createsuperuser
python manage.py shell
python manage.py collectstatic
```

**Production** (uses Gunicorn per [Procfile](Procfile), launched automatically by Railway):
```bash
gunicorn core.wsgi:application --bind 0.0.0.0:$PORT
```

## API Behaviour

### POST Request Flow (Generate Endpoint)

1. Request received at `POST /api/companion/generate/` — `FirebaseAuthentication` verifies the Bearer token; 401 if missing/invalid/expired; throttle scopes `ai_generate`/`luna_chat` checked (429 if exceeded)
2. Input validated by `JournalEntryCreateSerializer` (`emoji`, `thoughts`, optional `history`, optional `context_flag`) — 400 if invalid
3. `history` extracted from validated data (last 10 items kept to cap context)
4. Bilingual crisis-language check runs on `thoughts`; on a hit, a `crisis_flagged=True` entry with a canned crisis response is saved and returned immediately (200), skipping Groq entirely
5. Otherwise `generate_ai_response(emoji, thoughts, history, preferred_language, gender, memory_summary=..., context_flag=...)` called; exception caught → localized fallback message used
6. `ai_response` may contain `[SESSION_END]` tag — clients should detect this and close the session; it also triggers a background memory-summary update (see Cross-Session Memory)
7. `JournalEntry` created with `user_id=str(request.user.id)`, emoji, thoughts, ai_response
8. Serialized response returned (200)

### GET Request Flow (History Endpoint)

1. Request received at `GET /api/companion/history/` — 401 if unauthenticated
2. `JournalEntry.objects.filter(user_id=str(request.user.id)).order_by("-created_at")`
3. All matching entries serialized and returned

### GET Request Flow (Weekly Letter Endpoint)

1. Request received at `GET /api/companion/weekly-letter/` — 401 if unauthenticated
2. Entries from last 7 days fetched for `str(request.user.id)`
3. If < 2 entries: `{"letter": null, "reason": "not_enough_entries"}` (200)
4. Entries formatted, dominant emoji found
5. `generate_weekly_letter(...)` called — serves from the 24h Groq response cache if present (e.g. warmed overnight by `generate_weekly_letters`), otherwise calls Groq live
6. Returns `{"letter": "...", "stats": {...}}` (200)

### Error Handling

- **401**: Missing/invalid/expired Firebase ID token, on every protected endpoint
- **429**: Throttle scope exceeded (`user`, `ai_generate`, `luna_chat`, or `delete_all`)
- **400**: Invalid/missing required fields
- **200 with fallback**: Groq API error in generate/ (entry still saved)
- **200 with letter: null**: Groq API error in weekly-letter/
- **404**: Entry not found/not owned in `DELETE /api/companion/entries/<id>/delete/`
- **502**: Firebase-side failure deleting a user during `DELETE /api/accounts/delete-account/`

## Data Isolation

All `JournalEntry` queries are scoped to `user_id`, which is always `str(request.user.id)` — never accepted from the client. Users cannot see each other's entries. The `user_id` field is indexed (`db_index=True`), plus a composite `(user_id, -created_at)` index, for query performance.

## File Organization

```
ai_therapist_backend/
├── core/
│   ├── settings.py       # All Django settings (env-var driven, Railway-ready)
│   ├── urls.py           # Root URL configuration
│   ├── firebase_auth.py  # FirebaseAuthentication DRF backend + OpenAPI scheme
│   ├── wsgi.py           # WSGI entry point (Gunicorn)
│   └── asgi.py           # ASGI entry point
├── therapist/
│   ├── models.py         # JournalEntry model, EntryType choices
│   ├── views.py          # GenerateResponseAPIView, ActivityEntryAPIView, AllHistoryAPIView,
│   │                     # DeleteJournalEntryAPIView, DeleteAllJournalEntriesAPIView, WeeklyLetterAPIView
│   ├── serializers.py    # JournalEntrySerializer, JournalEntryCreateSerializer, ActivityEntryCreateSerializer
│   ├── ai_model.py       # Groq API integration, memory-summary trigger, weekly-letter generation
│   ├── luna_prompts.py   # LunaPromptProvider — language/gender-aware system prompts
│   ├── crisis.py         # English crisis-language detection + canned response
│   ├── crisis_ar.py      # Arabic crisis-language detection
│   ├── groq_budget_guard.py  # Free-tier token/request budget guard (cache-backed)
│   ├── throttles.py      # LunaChatRateThrottle, DeleteAllJournalEntriesRateThrottle
│   ├── services.py       # build_weekly_letter_context, warm_weekly_letter_cache
│   ├── urls.py           # App URL patterns
│   ├── admin.py          # Admin site config
│   ├── apps.py           # App configuration
│   ├── tests.py          # Test cases
│   ├── management/commands/generate_weekly_letters.py  # Nightly cache warm-up command
│   └── migrations/       # Database migrations
├── accounts/
│   ├── models.py         # User (AUTH_USER_MODEL, has firebase_uid, preferred_language, memory_summary)
│   ├── managers.py       # UserManager (email-based create_user/create_superuser)
│   ├── views.py          # MeView, DeleteAccountView only
│   ├── serializers.py    # UserSerializer, UserProfileUpdateSerializer
│   ├── validators.py     # Phone format only
│   ├── services.py       # Response envelope helpers, account-deletion logic
│   ├── urls.py           # App URL patterns (me/, delete-account/)
│   ├── admin.py          # Admin site config
│   ├── apps.py           # App configuration
│   ├── tests.py          # Test cases
│   └── migrations/       # Database migrations
├── templates/
│   └── index.html        # Home page
├── staticfiles/          # Collected static files (generated)
├── .venv/                # Virtual environment
├── manage.py
├── requirements.txt
├── Procfile              # Gunicorn start command (Railway/Heroku)
├── railway.json          # Railway build config (build command only — no cron schedule)
├── runtime.txt           # Pins Python 3.11.9 for Railway
├── README.md             # Setup/usage docs
├── db.sqlite3            # SQLite database
└── .gitignore
```

## Performance Characteristics

- **Cold Start**: < 1 second (no model loading)
- **API Request**: 1–2 seconds (network + Groq API processing)
- **Memory**: ~50–100MB (no ML models in memory)
- **No GPU Required**: All processing happens on Groq's servers

## Extension Points

### Easy Additions

1. **Filtering**: Query parameters for date ranges, emoji filters, or `entry_type` on `history/`
2. **Pagination**: DRF pagination classes on history endpoint
3. **Sync `is_verified`**: Firebase's decoded-token `email_verified` claim could be synced into `accounts.User.is_verified` in `core/firebase_auth.py`'s `get_or_create`/update path if a future feature needs it
4. **Legacy account linking**: a one-time admin/data-migration to associate pre-Firebase `accounts.User` rows (`firebase_uid IS NULL`) with their Firebase UID, if needed

### API Service Improvements

1. **Async Calls**: Use async/await for non-blocking Groq requests
2. **Streaming**: Streaming responses for real-time generation
3. **Context**: Multi-turn history and cross-session memory are already in place (see Cross-Session Memory) — further work could extend memory retention length or summarization quality

## Known Limitations

1. Synchronous Groq API calls — blocks request during generation (except the fire-and-forget memory-summary update)
2. SQLite — not suitable for concurrent production writes
3. No input sanitization beyond serializer validation
4. `ALLOWED_HOSTS`'s `.railway.app` entry matches any subdomain of `railway.app`, broader than the one Railway domain this app actually runs on
5. `JournalEntry` rows created before the Firebase migration (under the old client-supplied `user_id` scheme) are permanently inaccessible — not linked to any `accounts.User`; documented tradeoff, not a bug
6. Pre-Firebase `accounts.User` rows (created back when SimpleJWT existed) have `firebase_uid = NULL` and are not automatically linked to a Firebase identity — out of scope for this migration
7. Account deletion deletes matching `therapist.JournalEntry` rows by `user_id` during account deletion — there's no FK link between the two apps, so this is an explicit query-and-delete, not a database-level cascade
8. The cache backend (`settings.CACHES["default"]`, used by both the Groq budget guard and the weekly-letter cache) is `DatabaseCache`, backed by a `django_cache_table` created via a real migration ([therapist/migrations/0007_create_django_cache_table.py](therapist/migrations/0007_create_django_cache_table.py)) — not `LocMemCache`. This already shares state correctly across multiple worker processes (unlike `LocMemCache`, which is per-process), so the multi-worker concern doesn't apply; the actual tradeoff is that every cache read/write is a database round trip, adding load to the same Postgres instance the app already depends on rather than to a dedicated cache store

## Deployment Checklist

- [x] `DEBUG = False` in production (via env var)
- [x] `SECRET_KEY` via environment variable
- [x] Static files configured with WhiteNoise
- [x] `user_id` data isolation implemented (derived from authenticated `request.user`, not client input)
- [x] Firebase authentication implemented (`core/firebase_auth.py`)
- [x] Rate limiting configured (`user`/`ai_generate`/`luna_chat`/`delete_all` scopes)
- [x] CORS headers configured (`django-cors-headers`)
- [x] Error logging configured (Sentry, gated on `SENTRY_DSN`)
- [ ] **Set `GROQ_API_KEY`** (CRITICAL)
- [ ] **Set `FIREBASE_CREDENTIALS_PATH`** (CRITICAL — points at a Firebase service-account JSON)
- [ ] Consider dropping the `.railway.app` wildcard entry from `ALLOWED_HOSTS` now that the app has a fixed domain (the other two entries are already specific)
- [x] Confirm `DATABASE_URL` is set in Railway — PostgreSQL support is already implemented via `dj-database-url`/`psycopg2-binary`, this just verifies the env var is actually pointing at a Postgres instance in production rather than falling back to SQLite
- [ ] Set up monitoring dashboards

## Debugging Tips

1. **AI not working**: Check `GROQ_API_KEY` is set
2. **Slow responses**: Normal — Groq API takes 1–2 seconds
3. **401 Unauthorized from Groq**: Invalid or missing API key
4. **Database locked**: SQLite concurrency issue — use PostgreSQL
5. **Import errors**: Activate virtual environment first
6. **Static files 404**: Run `python manage.py collectstatic`
7. **401 on any endpoint**: missing/invalid/expired Firebase ID token, or `FIREBASE_CREDENTIALS_PATH` not set/pointing at a valid service-account file — check server logs for "Firebase token verification failed"
8. **`manage.py check`/tests fail with a Firebase credentials error**: shouldn't happen — `core/firebase_auth.py` guards `initialize_app` behind `FIREBASE_CREDENTIALS_PATH` being set, and tests mock `core.firebase_auth.auth.verify_id_token` directly
9. **429 Too Many Requests**: One of the throttle scopes (`user`/`ai_generate`/`luna_chat`/`delete_all`) was exceeded — check `settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]`

---

**Last Updated**: 2026-09-05
**Django Version**: 5.1.4
**Python Version**: 3.11.9 (pinned via [runtime.txt](runtime.txt))
**AI Provider**: Groq API (`openai/gpt-oss-20b`)
**Auth Provider**: Firebase Authentication (`firebase-admin` server SDK)
**Deployed**: Railway (build config in [railway.json](railway.json); platform auto-detects run command via [Procfile](Procfile) + [runtime.txt](runtime.txt))

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan:
`specs/003-admin-dashboard/plan.md`
<!-- SPECKIT END -->
