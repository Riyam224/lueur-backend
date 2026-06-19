# MindEase — AI Therapist Backend

A Django REST Framework backend that provides AI-powered emotional support, plus a full account/authentication system. Users share their mood with an emoji and thoughts, and **Luna** (the AI therapist) responds with an empathetic, personalised message. All entries are saved per user for history tracking and weekly reflections.

Powered by **Groq API with Llama 3.1 8B Instant** — no local GPU or ML dependencies required.

---

## Features

### Therapist (`/api/therapist/`)

- **Luna AI responses** — warm, empathetic replies via Groq's fast cloud API
- **Multi-turn conversations** — pass conversation history so Luna maintains context across messages
- **Session detection** — Luna appends `[SESSION_END]` when the user feels resolved; clients use this to close sessions
- **Mood journal** — every entry (emoji + thoughts + AI reply) is saved per user
- **Weekly letter** — Luna writes a personal weekly reflection based on recent entries
- **Per-user data isolation** — each user only sees their own entries (scoped by `user_id`)

### Accounts (`/api/accounts/`)

- **Custom user model** — email as the login identifier (`AUTH_USER_MODEL = accounts.User`), optional unique username, profile fields (full name, phone, bio, date of birth, gender, profile image)
- **JWT authentication** — SimpleJWT access tokens (15 min) and refresh tokens (7 days) with rotation and blacklist-on-logout
- **Registration & login** — returns access/refresh token pair
- **Profile management** — view/update profile, upload/remove profile image (JPG/JPEG/PNG/WEBP, ≤5 MB)
- **Password management** — change password (authenticated), forgot/reset password via single-use expiring tokens
- **Email verification** — issue and verify single-use expiring tokens (email delivery is currently a log-only stub)
- **Account deletion** — permanently delete your own account
- **Rate limiting** — custom per-IP/per-account throttles on auth-sensitive endpoints (register, login, forgot-password, verify-reset-token, send-verification-email)
- **Consistent response envelope** — every endpoint returns `{"success": bool, "message": str, "data": {...}}` or `{"success": false, "message": str, "errors": {...}}`

### General

- **Interactive API docs** — Swagger UI at `/api/docs/`, ReDoc at `/api/redoc/`
- **Production-ready** — Railway deployment with Gunicorn + WhiteNoise

---

## Technology Stack

| Layer | Technology |
| --- | --- |
| Framework | Django 5.1.4 + Django REST Framework 3.17.1 |
| AI Model | Groq API — `llama-3.1-8b-instant` (cloud) |
| Auth | djangorestframework-simplejwt 5.5.1 (JWT access/refresh + blacklist) |
| Images | Pillow 12.2.0 (profile image validation/storage) |
| API Docs | drf-spectacular (Swagger UI + ReDoc) |
| Database | SQLite (dev) / PostgreSQL (prod recommended) |
| HTTP Client | Python `requests` |
| Static Files | WhiteNoise |
| Deployment | Gunicorn + Railway |

---

## Quick Start

### Prerequisites

- Python 3.8+
- A Groq API key — get one free at [console.groq.com](https://console.groq.com)

### Setup

```bash
# 1. Clone and enter the project
git clone <repository-url>
cd ai_therapist_backend

# 2. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set environment variables
export GROQ_API_KEY="your-groq-api-key"
export SECRET_KEY="your-secret-key"   # optional in dev, also signs JWTs
export DEBUG="True"                   # optional in dev

# 5. Run migrations
python manage.py migrate

# 6. Start the server
python manage.py runserver
```

Server runs at `http://127.0.0.1:8000/`

---

## API Endpoints

### Therapist — Base URL: `/api/therapist/`

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | `/api/therapist/generate/` | Submit mood, get Luna's AI response |
| GET | `/api/therapist/history/` | Get all saved entries for a user |
| GET | `/api/therapist/weekly-letter/` | Get Luna's weekly reflection letter |

### Accounts — Base URL: `/api/accounts/`

| Method | Endpoint | Auth required | Description |
| --- | --- | --- | --- |
| POST | `/api/accounts/register/` | No | Register a new account, returns JWT access/refresh tokens |
| POST | `/api/accounts/login/` | No | Sign in with email + password, returns JWT access/refresh tokens |
| POST | `/api/accounts/logout/` | Yes | Blacklist a refresh token |
| POST | `/api/accounts/token/refresh/` | No | Exchange a refresh token for a new access token |
| GET | `/api/accounts/me/` | Yes | Get the authenticated user's profile |
| PATCH | `/api/accounts/me/` | Yes | Update editable profile fields |
| POST | `/api/accounts/profile-image/` | Yes | Upload profile photo (multipart/form-data) |
| DELETE | `/api/accounts/profile-image/` | Yes | Remove profile photo |
| POST | `/api/accounts/change-password/` | Yes | Change password |
| DELETE | `/api/accounts/delete-account/` | Yes | Permanently delete own account |
| POST | `/api/accounts/forgot-password/` | No | Request a password-reset token by email |
| POST | `/api/accounts/verify-reset-token/` | No | Check whether a reset token is valid |
| POST | `/api/accounts/reset-password/` | No | Set a new password using a valid reset token |
| POST | `/api/accounts/send-verification-email/` | Yes | Issue an email-verification token |
| POST | `/api/accounts/verify-email/` | Yes | Confirm email verification with a token |

Interactive docs available at:

- **Swagger UI**: `/api/docs/`
- **ReDoc**: `/api/redoc/`

---

### POST `/api/therapist/generate/`

Submit a mood entry. Luna responds with an empathetic message that is saved to the journal.

**Request body**:

```json
{
  "user_id": "user_123",
  "emoji": "😔",
  "thoughts": "Feeling overwhelmed with everything lately",
  "history": [
    {"role": "user", "content": "I feel anxious"},
    {"role": "assistant", "content": "I hear you..."}
  ]
}
```

- **`user_id`**: required — 3–128 characters, letters / numbers / `_` / `-` only.
- **`history`**: optional — list of prior `{"role", "content"}` messages for multi-turn context. Only the last 10 items are used.

**Response (200)**:

```json
{
  "id": 1,
  "user_id": "user_123",
  "emoji": "😔",
  "thoughts": "Feeling overwhelmed with everything lately",
  "ai_response": "It sounds like you're carrying a lot right now...",
  "created_at": "2026-04-08T10:30:00Z"
}
```

When the user feels better or resolved, Luna's `ai_response` will end with `[SESSION_END]` — clients should detect this tag and close the session.

**Error (400)** — invalid or missing fields:

```json
{
  "user_id": ["This field is required."]
}
```

If the Groq API is unavailable, the entry is still saved with a fallback message:
`"Luna is taking a little break right now. Please try again in a moment 🌿"`

---

### GET `/api/therapist/history/?user_id=user_123`

Returns all mood entries for the given user, newest first.

**Response (200)**:

```json
[
  {
    "id": 2,
    "user_id": "user_123",
    "emoji": "😊",
    "thoughts": "Had a great day!",
    "ai_response": "That's wonderful to hear...",
    "created_at": "2026-04-08T14:00:00Z"
  }
]
```

**Error (400)** — missing `user_id`:

```json
{ "error": "user_id is required" }
```

---

### GET `/api/therapist/weekly-letter/?user_id=user_123`

Luna writes a personal letter summarising the user's emotional week (last 7 days).

Requires at least **2 entries** in the past 7 days; returns `null` with a reason otherwise.

**Response (200)**:

```json
{
  "letter": "Dear friend,\n\nThis week you carried both weight and warmth...\n\n— Luna 🌿",
  "stats": {
    "entry_count": 5,
    "dominant_emoji": "😔",
    "streak": 5,
    "week_start": "2026-04-01",
    "week_end": "2026-04-08"
  }
}
```

**Response when not enough entries**:

```json
{
  "letter": null,
  "reason": "not_enough_entries"
}
```

---

### Accounts API Details

Every accounts endpoint returns a consistent envelope:

```json
{ "success": true, "message": "...", "data": { ... } }
```

or, on failure:

```json
{ "success": false, "message": "...", "errors": { ... } }
```

**POST `/api/accounts/register/`** — body: `email`, `password`, optional `username`/`full_name`. Returns the user plus JWT `access`/`refresh` tokens.

**POST `/api/accounts/login/`** — body: `email`, `password`. Returns JWT `access`/`refresh` tokens. Throttled (5 requests / 5 min per IP).

**POST `/api/accounts/token/refresh/`** — body: `refresh`. Returns a new `access` token (refresh rotation + blacklist enabled).

**POST `/api/accounts/logout/`** — auth required. Body: `refresh`. Blacklists the refresh token.

**GET / PATCH `/api/accounts/me/`** — auth required. `GET` returns the authenticated user's profile; `PATCH` updates editable fields (`username`, `full_name`, `phone_number`, `bio`, `date_of_birth`, `gender`).

**POST / DELETE `/api/accounts/profile-image/`** — auth required. `POST` is multipart/form-data with a `profile_image` file (JPG/JPEG/PNG/WEBP, ≤5 MB); `DELETE` removes the current photo.

**POST `/api/accounts/change-password/`** — auth required. Body: `old_password`, `new_password` (min 8 chars, ≥1 uppercase, ≥1 lowercase, ≥1 number).

**DELETE `/api/accounts/delete-account/`** — auth required. Permanently deletes the authenticated user's account. Does **not** cascade into `therapist.MoodEntry` (no FK link between the two apps today).

**POST `/api/accounts/forgot-password/`** — body: `email`. Issues a single-use, expiring reset token (delivery is currently log-only). Throttled (3 requests / 15 min).

**POST `/api/accounts/verify-reset-token/`** — body: `token`. Checks validity without consuming it. Throttled (5 requests / 15 min).

**POST `/api/accounts/reset-password/`** — body: `token`, `new_password`. Consumes the token and sets the new password.

**POST `/api/accounts/send-verification-email/`** — auth required. Issues a single-use, expiring email-verification token (delivery is currently log-only). Throttled (3 requests / hour).

**POST `/api/accounts/verify-email/`** — auth required. Body: `token`. Marks the account as verified.

> ⚠️ `therapist/` endpoints remain unauthenticated and are **not** gated behind `accounts/` login — `user_id` is still a free-text client-supplied string with no link to `accounts.User`.

---

## Project Structure

```text
ai_therapist_backend/
├── core/
│   ├── settings.py        # Project settings (env-var driven)
│   ├── urls.py            # Root URL routing
│   ├── wsgi.py
│   └── asgi.py
├── therapist/
│   ├── models.py          # MoodEntry model
│   ├── views.py           # GenerateResponseAPIView, AllHistoryAPIView, WeeklyLetterAPIView
│   ├── serializers.py     # MoodEntrySerializer, MoodEntryCreateSerializer
│   ├── ai_model.py        # Groq API integration (generate_ai_response)
│   ├── urls.py            # App URL patterns
│   ├── tests.py
│   └── migrations/
├── accounts/
│   ├── models.py          # User (AUTH_USER_MODEL), PasswordResetToken, EmailVerificationToken
│   ├── managers.py        # UserManager (email-based create_user/create_superuser)
│   ├── views.py           # One APIView per endpoint
│   ├── serializers.py     # Register/Login/Logout/Profile/Password/Verification serializers
│   ├── validators.py      # Password strength, phone format, image type/size
│   ├── services.py        # Response envelope, email-send stubs, token helpers
│   ├── throttling.py      # Custom per-IP/per-account throttles
│   ├── urls.py            # App URL patterns
│   ├── tests.py
│   └── migrations/
├── templates/
│   └── index.html         # Home page
├── media/                 # Profile image uploads (gitignored, dev-only)
├── manage.py
├── requirements.txt
├── Procfile               # Gunicorn config for Railway
└── db.sqlite3             # SQLite database (dev)
```

---

## Environment Variables

| Variable | Required | Description |
| --- | --- | --- |
| `GROQ_API_KEY` | **Yes** | Groq API key from [console.groq.com](https://console.groq.com) |
| `SECRET_KEY` | Recommended | Django secret key (has dev fallback); also signs JWTs — set a strong value in production |
| `DEBUG` | No | `"True"` for dev, `"False"` for prod (default: `False`) |

---

## Deployment

### Railway

1. Connect your GitHub repository on [railway.app](https://railway.app)
2. Add environment variables in the Railway dashboard:
   - `GROQ_API_KEY`, `SECRET_KEY`, `DEBUG=False`
3. Railway auto-detects the `Procfile` and deploys
4. Run migrations via Railway shell: `python manage.py migrate`

### Heroku

```bash
heroku create your-app-name
heroku config:set GROQ_API_KEY="your-api-key"
heroku config:set SECRET_KEY="your-secret-key"
heroku config:set DEBUG="False"
git push heroku main
heroku run python manage.py migrate
```

### Production checklist

- [ ] `GROQ_API_KEY` set (**required**)
- [ ] Strong `SECRET_KEY` set
- [ ] `DEBUG=False`
- [ ] Restrict `ALLOWED_HOSTS` to your domain
- [ ] Switch to PostgreSQL
- [ ] Add CORS headers (`django-cors-headers`) if frontend is on a different domain
- [ ] Configure rate limiting (DRF throttling)
- [ ] Add error logging (Sentry)
- [ ] Set up monitoring and health checks

---

## Testing

```bash
python manage.py test therapist
python manage.py test accounts
```

Mock the AI function to keep `therapist` tests fast and offline:

```python
from unittest.mock import patch
from rest_framework.test import APIClient
from django.test import TestCase

class TherapistAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch('therapist.ai_model.generate_ai_response')
    def test_create_mood_entry(self, mock_generate):
        mock_generate.return_value = "Mocked AI response"
        response = self.client.post(
            '/api/therapist/generate/',
            {'user_id': 'user_test', 'emoji': '😊', 'thoughts': 'Great day!'},
            format='json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('ai_response', response.data)
```

For `accounts` tests: mock `send_password_reset_email`/`send_verification_email` (in `accounts.views`) to avoid implying real email delivery, call `cache.clear()` in `setUp()` for throttled-endpoint tests (Django's default `LocMemCache` persists across test classes), and use `@override_settings(MEDIA_ROOT=tempfile.mkdtemp())` for profile-image tests so uploads don't land in the real `media/` directory.

---

## Integration Examples

### cURL

```bash
# Generate AI response (with optional conversation history)
curl -X POST http://localhost:8000/api/therapist/generate/ \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_123", "emoji": "😊", "thoughts": "Great day!", "history": []}'

# Get history
curl "http://localhost:8000/api/therapist/history/?user_id=user_123"

# Get weekly letter
curl "http://localhost:8000/api/therapist/weekly-letter/?user_id=user_123"

# Register
curl -X POST http://localhost:8000/api/accounts/register/ \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "StrongPass1"}'

# Login
curl -X POST http://localhost:8000/api/accounts/login/ \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "StrongPass1"}'

# Get profile (auth required)
curl http://localhost:8000/api/accounts/me/ \
  -H "Authorization: Bearer <access_token>"
```

### JavaScript (Fetch)

```javascript
// Generate AI response (pass history for multi-turn context)
const res = await fetch('http://localhost:8000/api/therapist/generate/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    user_id: 'user_123',
    emoji: '😊',
    thoughts: 'Feeling good!',
    history: [], // prior [{role, content}] messages
  })
});
const data = await res.json();
// If data.ai_response includes '[SESSION_END]', close the session

// Get history
const history = await fetch('http://localhost:8000/api/therapist/history/?user_id=user_123');
const entries = await history.json();

// Login and use the access token for an authenticated request
const loginRes = await fetch('http://localhost:8000/api/accounts/login/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email: 'user@example.com', password: 'StrongPass1' }),
});
const { data: { access, refresh } } = await loginRes.json();

const meRes = await fetch('http://localhost:8000/api/accounts/me/', {
  headers: { Authorization: `Bearer ${access}` },
});
```

---

## Troubleshooting

| Problem | Solution |
| --- | --- |
| 500 on POST | Check `GROQ_API_KEY` is set and valid |
| `user_id` validation error | Use only letters, numbers, `_`, `-`; min 3 chars |
| Static files 404 | Run `python manage.py collectstatic` |
| Database locked | Switch to PostgreSQL for concurrent writes |
| Slow responses | Normal — Groq API takes 1–2 seconds |
| 401 on `accounts/` endpoints | Access tokens expire after 15 min — call `token/refresh/` with the refresh token (valid 7 days) instead of re-logging in |
| 429 on `accounts/` endpoints | Rate limit hit — see throttle thresholds above; `cache.clear()` in tests if writing new throttled-endpoint tests |
| Profile image upload rejected | Must be JPG/JPEG/PNG/WEBP and ≤5 MB |

---

## Disclaimer

This application provides AI-generated supportive messages and is **not a replacement for professional mental health services**.

If you are in crisis, please reach out:

- **US**: 988 (Suicide & Crisis Lifeline)
- **UK**: 116 123 (Samaritans)
- **International**: [findahelpline.com](https://findahelpline.com)

---

**Built with Django REST Framework · Powered by Groq API (Llama 3.1 8B)**

Last Updated: June 19, 2026
