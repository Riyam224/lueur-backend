# CLAUDE.md - Lueur Backend

Technical documentation for Claude Code to understand and work with this Django project.

## Project Overview

This is a Django REST Framework application that provides an AI-powered mental health support API. It uses the **Groq API with Llama 3.1 8B Instant model** to generate empathetic responses to user mood inputs. The AI companion is named **Luna**.

## Architecture

### Application Structure

- **Django Project**: `core/` - Main project configuration
- **Django App**: `therapist/` - Main application handling mood entries and AI responses
- **Django App**: `accounts/` - Custom user model, JWT authentication, and account/profile management
- **Database**: SQLite (default), easily swappable for PostgreSQL/MySQL
- **AI Service**: Groq API (external REST API) accessed via [therapist/ai_model.py](therapist/ai_model.py)
- **Auth**: Firebase Authentication — the Flutter client owns sign-in/sign-up/password-reset/email-verification/Google/Apple via Firebase; Django only verifies Firebase ID tokens via [core/firebase_auth.py](core/firebase_auth.py) and resolves them to `request.user`. Django never issues or refreshes tokens itself.
- **API Docs**: drf-spectacular (Swagger UI at `/api/docs/`, ReDoc at `/api/redoc/`)
- **Deployment**: Railway-ready with WhiteNoise for static files

### Key Components

1. **Model Layer** ([therapist/models.py](therapist/models.py))
   - `MoodEntry`: Stores user mood data
     - Fields: `user_id` (CharField, db_index), `emoji`, `thoughts`, `ai_response`, `created_at`
     - `user_id` scopes all entries to a specific user — always `str(request.user.id)`, set server-side; never accepted from the client (no schema change — the column is reused, see [accounts](#) auth migration)
     - Uses auto-generated timestamps (`auto_now_add=True`)
     - String representation: `"{user_id} | {emoji} - {thoughts[:20]}"`
     - Meta: `verbose_name` and `verbose_name_plural` configured

2. **View Layer** ([therapist/views.py](therapist/views.py))
   - Uses **class-based APIView** (DRF), all three require `permission_classes = [IsAuthenticated]` (authenticated via `core.firebase_auth.FirebaseAuthentication`)
   - `GenerateResponseAPIView`: POST-only endpoint
     - Validates input with `MoodEntryCreateSerializer` (`emoji`, `thoughts` required; `history` optional — `user_id` is NOT accepted from the client)
     - Extracts last 10 items from `history` to cap context window
     - Calls `generate_ai_response(emoji, thoughts, history)` from ai_model
     - On AI error: catches exception, saves fallback message, still returns 200
     - Creates `MoodEntry` with `user_id=str(request.user.id)` and returns serialized data (200)
     - Luna may include `[SESSION_END]` tag in `ai_response` when the user feels resolved
   - `AllHistoryAPIView`: GET-only endpoint
     - Returns entries filtered by `str(request.user.id)`, ordered by `created_at` DESC
   - `WeeklyLetterAPIView`: GET-only endpoint
     - Fetches last 7 days of entries for `str(request.user.id)`
     - Returns `{"letter": null, "reason": "not_enough_entries"}` if fewer than 2 entries
     - Calls Groq API directly to generate a personal weekly letter from Luna
     - Returns letter text + stats (entry_count, dominant_emoji, streak, week_start, week_end)

3. **AI Service** ([therapist/ai_model.py](therapist/ai_model.py))
   - Function: `generate_ai_response(emoji, thoughts, history=None) -> str`
   - `history`: optional list of `{"role": "user"|"assistant", "content": "..."}` dicts — injected between system prompt and current user message for multi-turn context
   - Uses **Groq API** (external cloud service), model: `llama-3.1-8b-instant`
   - Requires `GROQ_API_KEY` environment variable
   - Makes REST POST to `https://api.groq.com/openai/v1/chat/completions`
   - System prompt (`LUNA_SYSTEM_PROMPT`): defines Luna's personality (gentle, non-robotic, friend-like), response rules (2-3 sentences max, one follow-up question, no lists/headers, never repeats herself), and explicit `[SESSION_END]` trigger examples (only on clear resolution/gratitude/goodbye, never on vague requests like "help me")
   - Generation params tuned for natural variation: `temperature=0.85`, `max_tokens=180`, `top_p=0.9`, `frequency_penalty=0.6`, `presence_penalty=0.5`
   - **No local model loading** — stateless, synchronous API calls
   - Does not handle exceptions — caller is responsible

4. **Serializers** ([therapist/serializers.py](therapist/serializers.py))
   - `MoodEntrySerializer`: full read serializer — `fields = "__all__"`, `user_id`/`ai_response`/`created_at`/`id` read-only
   - `MoodEntryCreateSerializer`: write serializer — exposes only `emoji`, `thoughts`, and optional `history` (`user_id` is not client-writable)
     - `history`: write-only ListField of DictFields (`{"role", "content"}`), defaults to `[]`

5. **Firebase Authentication** ([core/firebase_auth.py](core/firebase_auth.py))
   - `FirebaseAuthentication(BaseAuthentication)` — DRF authentication backend, set as the sole entry in `REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"]`
   - Reads `Authorization: Bearer <firebase-id-token>`; missing/empty → unauthenticated (401 via `IsAuthenticated`); calls `firebase_admin.auth.verify_id_token(token)` — any exception (invalid signature, expired, wrong audience) → `AuthenticationFailed` (401)
   - Resolves the verified `uid` to an `accounts.User` via `get_or_create(firebase_uid=uid, ...)`, auto-creating on first sight; if Firebase provides no email (phone/anonymous sign-in) a synthetic `f"{uid}@firebase.local"` is used to satisfy `User.email`'s uniqueness constraint
   - `firebase_admin.initialize_app(...)` is guarded by `if not firebase_admin._apps` and only runs when `FIREBASE_CREDENTIALS_PATH` is set, so `manage.py check`/`makemigrations`/non-auth tests work without real credentials (e.g. CI)
   - Registers a `drf_spectacular` `OpenApiAuthenticationExtension` so the OpenAPI schema documents the Bearer scheme correctly

6. **Accounts App** ([accounts/](accounts/)) — account/profile management only; Firebase owns all credential/identity flows
   - **Model** ([accounts/models.py](accounts/models.py)): `User` (`AUTH_USER_MODEL = "accounts.User"`, extends `AbstractUser`, email is `USERNAME_FIELD`, optional unique `username`, nullable unique indexed `firebase_uid`, `full_name`, `phone_number`, `bio`, `date_of_birth`, `gender`, `is_verified`). No `PasswordResetToken`/`EmailVerificationToken`/`profile_image` — removed in the Firebase migration.
   - **Manager** ([accounts/managers.py](accounts/managers.py)): `UserManager.create_user`/`create_superuser`, email-based (still used by `createsuperuser` for admin access; regular users are created via `FirebaseAuthentication`'s `get_or_create`)
   - **Views** ([accounts/views.py](accounts/views.py)): only `MeView` (GET/PATCH `/me/`) and `DeleteAccountView` (DELETE `/delete-account/`); every view operates on `request.user` only — no endpoint accepts another user's identifier. `DeleteAccountView` calls `firebase_admin.auth.delete_user(firebase_uid)` first; on failure it logs and returns `502` **without** deleting the local row (no orphaned Firebase identity)
   - **Serializers** ([accounts/serializers.py](accounts/serializers.py)): `UserSerializer` (read-only, full profile) and `UserProfileUpdateSerializer` (`full_name`, `phone_number`, `bio`, `date_of_birth`, `gender` only — `firebase_uid`/`email`/`username`/staff fields are never in `Meta.fields`, so extra payload keys are silently ignored)
   - **Validators** ([accounts/validators.py](accounts/validators.py)): phone format only (password-strength and profile-image validators removed)
   - **Services** ([accounts/services.py](accounts/services.py)): `success_response`/`error_response` envelope helpers only
   - **Response envelope**: every `accounts/` endpoint returns `{"success": bool, "message": str, "data": {...}}` or `{"success": false, "message": str, "errors": {...}}` — except auth failures, which return DRF's default `{"detail": "..."}` 401 shape (auth runs before any view code)

### URL Routing

- **Main URLs** ([core/urls.py](core/urls.py)):
  - `/` → Home page (`templates/index.html`)
  - `/admin/` → Django admin interface
  - `/api/companion/` → Includes companion (therapist) app URLs
  - `/api/accounts/` → Includes accounts app URLs
  - `/api/schema/` → OpenAPI schema
  - `/api/docs/` → Swagger UI
  - `/api/redoc/` → ReDoc UI

- **Therapist URLs** ([therapist/urls.py](therapist/urls.py)):
  - `generate/` → `GenerateResponseAPIView` (POST only, auth required)
  - `history/` → `AllHistoryAPIView` (GET only, auth required)
  - `weekly-letter/` → `WeeklyLetterAPIView` (GET only, auth required)

- **Accounts URLs** ([accounts/urls.py](accounts/urls.py)): see Full API Endpoints below

### Full API Endpoints

All endpoints below (except none — every endpoint now requires auth) require `Authorization: Bearer <firebase-id-token>`. Missing/invalid/expired token → `401 Unauthorized`.

- `POST /api/companion/generate/` — Create mood entry with AI response, scoped to `request.user`
- `GET /api/companion/history/` — Retrieve entries for the authenticated user
- `GET /api/companion/weekly-letter/` — Get Luna's weekly letter for the authenticated user
- `GET /api/accounts/me/` — Get the authenticated user's profile
- `PATCH /api/accounts/me/` — Update editable profile fields (`full_name`, `phone_number`, `bio`, `date_of_birth`, `gender` only)
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
- `djangorestframework==3.17.1` — REST API
- `drf-spectacular==0.27.2` — OpenAPI schema + Swagger/ReDoc (branded "Lueur API" in [core/settings.py](core/settings.py) `SPECTACULAR_SETTINGS`)
- `requests==2.33.0` — HTTP client for Groq API calls
- `gunicorn==25.3.0` — Production WSGI server
- `whitenoise==6.5.0` — Static file serving for production
- `certifi==2026.2.25` — SSL certificate bundle
- `firebase-admin>=6.5,<7` — verifies Firebase ID tokens, deletes Firebase users server-side

**Note**: No `torch` or `transformers` — uses external API instead of local model. No `python-decouple`/`dotenv` — settings use the existing `os.environ.get(..., default)` pattern. No `Pillow` — profile photos are now stored in Firebase Storage by the client, not Django.

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
generate_ai_response(emoji: str, thoughts: str, history: list = None) -> str
```

- `history`: list of `{"role": "user"|"assistant", "content": "..."}` message dicts (optional)
- Makes POST request to Groq API
- Uses `llama-3.1-8b-instant` model
- Returns AI-generated response text; may include `[SESSION_END]` tag at the end
- Raises exceptions on failure — caller must handle

### Security Considerations

**Current State** ([core/settings.py](core/settings.py)):
- ✅ `SECRET_KEY` uses environment variable with fallback
- ✅ `DEBUG` uses environment variable (defaults to False)
- ✅ `ALLOWED_HOSTS` configured for Railway (`["*", ".railway.app"]`)
- ✅ `CSRF_TRUSTED_ORIGINS` includes the deployed Railway domain (`https://web-production-f8628.up.railway.app`) — **update this if the Railway app domain changes**
- ✅ WhiteNoise configured for secure static file serving
- ✅ Identity comes exclusively from a verified Firebase ID token (`request.user`, set by `core.firebase_auth.FirebaseAuthentication`) — no endpoint accepts a client-supplied user identifier from the request body or query parameters
- ✅ `therapist/` (`generate`, `history`, `weekly-letter`) and `accounts/` (`me/`, `delete-account/`) all require authentication and are scoped to `request.user`
- ⚠️ `ALLOWED_HOSTS = ["*"]` allows all hosts — restrict in production
- ⚠️ No CORS headers — add `django-cors-headers` if frontend on a different domain
- ⚠️ No Django-side rate limiting remains (the only previously-throttled endpoints — register/login/forgot-password/etc. — were removed; Firebase enforces its own abuse protection on those flows)
- ⚠️ `MoodEntry` rows created before this migration (under the old client-supplied `user_id` scheme) are permanently inaccessible through the now-authenticated endpoints — accepted, documented tradeoff, not a bug (see `specs/002-migrate-authentication-simplejwt/spec.md` Edge Cases)

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

1. Request received at `POST /api/companion/generate/` — `FirebaseAuthentication` verifies the Bearer token; 401 if missing/invalid/expired
2. Input validated by `MoodEntryCreateSerializer` (`emoji`, `thoughts`, optional `history`) — 400 if invalid
3. `history` extracted from validated data (last 10 items kept to cap context)
4. `generate_ai_response(emoji, thoughts, history)` called; exception caught → fallback message used
5. `ai_response` may contain `[SESSION_END]` tag — clients should detect this and close the session
6. `MoodEntry` created with `user_id=str(request.user.id)`, emoji, thoughts, ai_response
7. Serialized response returned (200)

### GET Request Flow (History Endpoint)

1. Request received at `GET /api/companion/history/` — 401 if unauthenticated
2. `MoodEntry.objects.filter(user_id=str(request.user.id)).order_by("-created_at")`
3. All matching entries serialized and returned

### GET Request Flow (Weekly Letter Endpoint)

1. Request received at `GET /api/companion/weekly-letter/` — 401 if unauthenticated
2. Entries from last 7 days fetched for `str(request.user.id)`
3. If < 2 entries: `{"letter": null, "reason": "not_enough_entries"}` (200)
4. Entries formatted, dominant emoji found
5. Groq API called to generate personal letter from Luna (timeout: 10s)
6. Returns `{"letter": "...", "stats": {...}}` (200)

### Error Handling

- **401**: Missing/invalid/expired Firebase ID token, on every protected endpoint
- **400**: Invalid/missing required fields
- **200 with fallback**: Groq API error in generate/ (entry still saved)
- **200 with letter: null**: Groq API error in weekly-letter/
- **502**: Firebase-side failure deleting a user during `DELETE /api/accounts/delete-account/`

## Data Isolation

All `MoodEntry` queries are scoped to `user_id`, which is always `str(request.user.id)` — never accepted from the client. Users cannot see each other's entries. The `user_id` field is indexed (`db_index=True`) for query performance.

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
│   ├── models.py         # MoodEntry model
│   ├── views.py          # GenerateResponseAPIView, AllHistoryAPIView, WeeklyLetterAPIView (all IsAuthenticated)
│   ├── serializers.py    # MoodEntrySerializer, MoodEntryCreateSerializer (no user_id field)
│   ├── ai_model.py       # Groq API integration
│   ├── urls.py           # App URL patterns
│   ├── admin.py          # Admin site config
│   ├── apps.py           # App configuration
│   ├── tests.py          # Test cases
│   └── migrations/       # Database migrations
├── accounts/
│   ├── models.py         # User (AUTH_USER_MODEL, has firebase_uid)
│   ├── managers.py       # UserManager (email-based create_user/create_superuser)
│   ├── views.py          # MeView, DeleteAccountView only
│   ├── serializers.py    # UserSerializer, UserProfileUpdateSerializer
│   ├── validators.py     # Phone format only
│   ├── services.py       # Response envelope helpers only
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

1. **Filtering**: Query parameters for date ranges, emoji filters on `history/`
2. **Pagination**: DRF pagination classes on history endpoint
3. **CORS**: `django-cors-headers` for cross-origin frontend
4. **Sync `is_verified`**: Firebase's decoded-token `email_verified` claim could be synced into `accounts.User.is_verified` in `core/firebase_auth.py`'s `get_or_create`/update path if a future feature needs it
5. **Legacy account linking**: a one-time admin/data-migration to associate pre-Firebase `accounts.User` rows (`firebase_uid IS NULL`) with their Firebase UID, if needed

### API Service Improvements

1. **Async Calls**: Use async/await for non-blocking Groq requests
2. **Streaming**: Streaming responses for real-time generation
3. **Retry Logic**: Exponential backoff for failed API calls
4. **Context**: Pass conversation history for context-aware responses

## Known Limitations

1. Synchronous Groq API calls — blocks request during generation
2. SQLite — not suitable for concurrent production writes
3. No Django-side rate limiting remains anywhere (Firebase enforces its own abuse protection on sign-in/sign-up flows; `therapist/` was never throttled)
4. No input sanitization beyond serializer validation
5. `ALLOWED_HOSTS = ["*"]` — too permissive for production
6. `MoodEntry` rows created before the Firebase migration (under the old client-supplied `user_id` scheme) are permanently inaccessible — not linked to any `accounts.User`; documented tradeoff, not a bug
7. Pre-Firebase `accounts.User` rows (created back when SimpleJWT existed) have `firebase_uid = NULL` and are not automatically linked to a Firebase identity — out of scope for this migration
8. Account deletion does not cascade into `therapist.MoodEntry` — there's no FK link between the two today

## Deployment Checklist

- [x] `DEBUG = False` in production (via env var)
- [x] `SECRET_KEY` via environment variable
- [x] Static files configured with WhiteNoise
- [x] `user_id` data isolation implemented (derived from authenticated `request.user`, not client input)
- [x] Firebase authentication implemented (`core/firebase_auth.py`)
- [ ] **Set `GROQ_API_KEY`** (CRITICAL)
- [ ] **Set `FIREBASE_CREDENTIALS_PATH`** (CRITICAL — points at a Firebase service-account JSON)
- [ ] Restrict `ALLOWED_HOSTS` to specific domain
- [ ] Use PostgreSQL
- [ ] Add CORS headers if needed
- [ ] Add error logging (Sentry)
- [ ] Set up monitoring

## Debugging Tips

1. **AI not working**: Check `GROQ_API_KEY` is set
2. **Slow responses**: Normal — Groq API takes 1–2 seconds
3. **401 Unauthorized from Groq**: Invalid or missing API key
4. **Database locked**: SQLite concurrency issue — use PostgreSQL
5. **Import errors**: Activate virtual environment first
6. **Static files 404**: Run `python manage.py collectstatic`
7. **401 on any endpoint**: missing/invalid/expired Firebase ID token, or `FIREBASE_CREDENTIALS_PATH` not set/pointing at a valid service-account file — check server logs for "Firebase token verification failed"
8. **`manage.py check`/tests fail with a Firebase credentials error**: shouldn't happen — `core/firebase_auth.py` guards `initialize_app` behind `FIREBASE_CREDENTIALS_PATH` being set, and tests mock `core.firebase_auth.auth.verify_id_token` directly

---

**Last Updated**: 2026-06-22
**Django Version**: 5.1.4
**Python Version**: 3.11.9 (pinned via [runtime.txt](runtime.txt))
**AI Provider**: Groq API (Llama 3.1 8B Instant)
**Auth Provider**: Firebase Authentication (`firebase-admin` server SDK)
**Deployed**: Railway (no `railway.json`/`railway.toml` — platform auto-detects via [Procfile](Procfile) + [runtime.txt](runtime.txt))

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan:
`specs/002-migrate-authentication-simplejwt/plan.md`
<!-- SPECKIT END -->
