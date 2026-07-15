# Lueur Backend — AI Wellness Companion API

A Django REST Framework backend that provides AI-powered emotional support, plus account/profile management. Users share their mood with an emoji and thoughts, and **Luna** (the AI companion) responds with an empathetic, personalised message. All entries are saved per user for history tracking and weekly reflections.

Powered by **Groq API with Llama 3.1 8B Instant** — no local GPU or ML dependencies required.

Authentication is handled entirely by **Firebase Auth**: the client (e.g. a Flutter app) signs in via Firebase (email/password, Google, Apple), and Django verifies the resulting Firebase ID token on every request — Django never issues, stores, or refreshes its own credentials.

Every journal entry is checked for crisis language **before** it ever reaches an LLM. See [Crisis Detection](#crisis-detection) below.

---

## Features

### Companion (`/api/companion/`)

- **Luna AI responses** — warm, empathetic replies via Groq's fast cloud API, with automatic retry (2 attempts, short backoff) and a graceful fallback message if Groq is unreachable
- **Multi-turn conversations** — pass conversation history so Luna maintains context across messages
- **Session detection** — Luna appends `[SESSION_END]` when the user feels resolved; clients use this to close sessions
- **Crisis detection** — journal text is checked for crisis language *before* any AI call, at both the endpoint and the AI-service layer; a match returns a static support response (with real hotline numbers) and `crisis_flagged: true`, and is redacted before ever appearing in a weekly letter prompt — see [Crisis Detection](#crisis-detection)
- **Mood journal** — every entry (emoji + thoughts + AI reply) is saved per user
- **Weekly letter** — Luna writes a personal weekly reflection based on recent entries, including a real consecutive-day streak (not just an entry count)
- **Per-user data isolation** — every entry is scoped to the authenticated user (`request.user`); no client-supplied identifier is ever accepted

### Accounts (`/api/accounts/`)

- **Firebase-backed identity** — registration, login, logout, password reset, email verification, Google/Apple sign-in are all handled by Firebase Auth on the client; Django only verifies the resulting ID token
- **Custom user model** — `accounts.User` (email as `USERNAME_FIELD`), linked to Firebase via a nullable, unique `firebase_uid`, auto-created on first sight of a new Firebase identity
- **Profile management** — view/update profile (`full_name`, `phone_number`, `bio`, `date_of_birth`, `gender`); identity-bearing fields (`firebase_uid`, `email`, `username`, staff flags) are never client-writable
- **Account deletion** — deletes the Firebase identity, all of the user's `MoodEntry` rows, then the local Django record; fails closed (nothing deleted) if the Firebase-side call errors. Users who can't open the app can request the same deletion by email — see [Account Deletion](#account-deletion)
- **Consistent response envelope** — every endpoint returns `{"success": bool, "message": str, "data": {...}}` or `{"success": false, "message": str, "errors": {...}}`

### General

- **Interactive API docs** — Swagger UI at `/api/docs/`, ReDoc at `/api/redoc/`
- **Health check** — `GET /health/` (unauthenticated) for Railway and uptime monitoring
- **Production-ready** — Railway deployment with Gunicorn + WhiteNoise

---

## Live Deployment

Deployed on Railway at [web-production-f8628.up.railway.app](https://web-production-f8628.up.railway.app):

![Lueur API landing page deployed on Railway](docs/screenshots/railway-deployment.png)

> The screenshot above reflects the currently live deployment, which predates the Firebase Auth migration documented in this README (the live landing page copy still references the old `user_id`-based contract). Redeploy this branch to bring the live site in line with the endpoints described below.

---

## Technology Stack

| Layer | Technology |
| --- | --- |
| Framework | Django 5.1.4 + Django REST Framework 3.17.1 |
| AI Model | Groq API — `llama-3.1-8b-instant` (cloud) |
| Auth | Firebase Authentication via `firebase-admin` (server-side ID token verification only) |
| API Docs | drf-spectacular (Swagger UI + ReDoc) |
| Database | SQLite (dev) / PostgreSQL (prod recommended) |
| HTTP Client | Python `requests` |
| Static Files | WhiteNoise |
| Deployment | Gunicorn + Railway |

---

## Authentication Architecture

```text
Flutter client → Firebase Auth → Firebase ID Token → Django API
                                                          │
                                          core.firebase_auth.FirebaseAuthentication
                                                          │
                                                    request.user
                                                          │
                                               Luna business logic
```

- Firebase owns: registration, login, logout, password reset, email verification, Google/Apple sign-in, and the entire token lifecycle (issuance, refresh, revocation).
- Django owns: user profile data, mood history, weekly letters, and admin functionality — and verifies every request's Firebase ID token before any view code runs.
- Every protected endpoint requires `Authorization: Bearer <firebase-id-token>`. Missing, malformed, invalid, or expired tokens return `401 Unauthorized`.
- On first sight of a new `firebase_uid`, Django auto-creates a matching `accounts.User` row — no separate registration call to Django is needed.

---

## Quick Start

### Prerequisites

- Python 3.11+
- A Groq API key — get one free at [console.groq.com](https://console.groq.com)
- A Firebase project with a service-account credentials JSON (for verifying ID tokens) — see [Firebase Console → Project Settings → Service Accounts](https://console.firebase.google.com/)

### Setup

```bash
# 1. Clone and enter the project
git clone <repository-url>
cd ai_therapist_backend

# 2. Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set environment variables
export GROQ_API_KEY="your-groq-api-key"
export FIREBASE_CREDENTIALS_PATH="/path/to/firebase-service-account.json"
export SECRET_KEY="your-secret-key"   # optional in dev
export DEBUG="True"                   # optional in dev

# 5. Run migrations
python manage.py migrate

# 6. Start the server
python manage.py runserver
```

Server runs at `http://127.0.0.1:8000/`

> Note: `manage.py check`/`makemigrations`/non-auth tests run fine without `FIREBASE_CREDENTIALS_PATH` set — Firebase initialization is lazy and only required when an authenticated request actually comes in.

---

## API Endpoints

Every endpoint below requires `Authorization: Bearer <firebase-id-token>` **except** `/api/accounts/verify/` (and its `/api/auth/verify/` alias), which is called right after Firebase sign-in — before the client has anything to put in that header — and `GET /health/`, used by Railway/uptime monitoring.

### Companion — Base URL: `/api/companion/`

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | `/api/companion/generate/` | Submit mood, get Luna's AI response (scoped to the authenticated user). Crisis-language input short-circuits before any Groq call. |
| GET | `/api/companion/history/` | Get all saved entries for the authenticated user |
| GET | `/api/companion/weekly-letter/` | Get Luna's weekly reflection letter and real streak stats for the authenticated user |

### Accounts — Base URL: `/api/accounts/`

| Method | Endpoint | Auth | Description |
| --- | --- | --- | --- |
| GET | `/api/accounts/me/` | Required | Get the authenticated user's profile |
| PATCH | `/api/accounts/me/` | Required | Update editable profile fields (`full_name`, `phone_number`, `bio`, `date_of_birth`, `gender`) |
| DELETE | `/api/accounts/delete-account/` | Required | Delete the user's Firebase identity, journal entries, and local account permanently |
| POST | `/api/accounts/verify/` (alias: `/api/auth/verify/`) | None | Verify a Firebase ID token, auto-creating the linked `accounts.User` on first sight |

Registration, login, logout, token refresh, password reset, email verification, and profile-photo upload are **not** Django endpoints — they're handled entirely by Firebase Auth (and Firebase Storage for photos) on the client.

Interactive docs available at:

- **Swagger UI**: `/api/docs/`
- **ReDoc**: `/api/redoc/`

#### Swagger UI

![Swagger UI showing the six authenticated Lueur API endpoints](docs/screenshots/swagger-ui.png)

#### ReDoc

![ReDoc rendering of the Lueur API schema](docs/screenshots/redoc.png)

---

### POST `/api/companion/generate/`

Submit a mood entry. Luna responds with an empathetic message that is saved to the journal under the authenticated user.

**Request body**:

```json
{
  "emoji": "😔",
  "thoughts": "Feeling overwhelmed with everything lately",
  "history": [
    {"role": "user", "content": "I feel anxious"},
    {"role": "assistant", "content": "I hear you..."}
  ]
}
```

- **`history`**: optional — list of prior `{"role", "content"}` messages for multi-turn context. Only the last 10 items are used.
- There is no `user_id` field — the entry is always attributed to `request.user`.

**Response (200)**:

```json
{
  "id": 1,
  "user_id": "1",
  "emoji": "😔",
  "thoughts": "Feeling overwhelmed with everything lately",
  "ai_response": "It sounds like you're carrying a lot right now...",
  "created_at": "2026-06-22T10:30:00Z",
  "crisis_flagged": false
}
```

When the user feels better or resolved, Luna's `ai_response` will end with `[SESSION_END]` — clients should detect this tag and close the session.

**Error (401)** — missing/invalid/expired token:

```json
{ "detail": "Invalid or expired token." }
```

If the Groq API is unavailable, the entry is still saved with a fallback message:
`"Luna is taking a little break right now. Please try again in a moment 🌿"`

---

### Crisis Detection

`thoughts` is checked against a crisis-language pattern (`therapist/crisis.py`) **before** `generate_ai_response` is ever called — so Groq never sees crisis text. This runs at two layers for defense in depth: once in `GenerateResponseAPIView` and again inside `ai_model.generate_ai_response()` itself, in case anything else ever calls it directly.

A match:

- Skips the Groq call entirely
- Saves the entry with a static support response (real crisis-line numbers, no AI-generated text)
- Returns `crisis_flagged: true` in the response

```json
{
  "id": 7,
  "user_id": "1",
  "emoji": "😔",
  "thoughts": "I want to kill myself",
  "ai_response": "It sounds like you're carrying something really heavy right now...\n\n• US: call or text 988 (Suicide & Crisis Lifeline)\n• Outside the US: https://findahelpline.com\n\n...",
  "created_at": "2026-06-22T10:30:00Z",
  "crisis_flagged": true
}
```

The same check also runs when building `weekly-letter/`'s prompt: any past entry that matches is redacted to `"(a difficult moment)"` before its text is sent to Groq, so a flagged entry from earlier in the week can't leak into a third-party API call via the weekly summary.

This is keyword-based pattern matching, not a clinical or diagnostic tool, and it **will** produce false positives on non-literal phrasing (e.g. "I can't go on watching this show"). That tradeoff is intentional — over-triggering toward a support message is safer than under-triggering and saying nothing.

---

### GET `/api/companion/history/`

Returns all mood entries for the authenticated user, newest first.

**Response (200)**:

```json
[
  {
    "id": 2,
    "user_id": "1",
    "emoji": "😊",
    "thoughts": "Had a great day!",
    "ai_response": "That's wonderful to hear...",
    "created_at": "2026-06-22T14:00:00Z"
  }
]
```

---

### GET `/api/companion/weekly-letter/`

Luna writes a personal letter summarising the authenticated user's emotional week (last 7 days).

Requires at least **2 entries** in the past 7 days; returns `null` with a reason otherwise.

`stats.streak` is a real consecutive-day count (`calculate_streak()` in `therapist/views.py`), not just the number of entries — it walks backward from today (or yesterday, if nothing was logged today) and stops at the first gap. Any crisis-flagged entry in the window is redacted before its text is sent to Groq for the letter itself — see [Crisis Detection](#crisis-detection).

**Response (200)**:

```json
{
  "letter": "Dear friend,\n\nThis week you carried both weight and warmth...\n\n— Luna 🌿",
  "stats": {
    "entry_count": 5,
    "dominant_emoji": "😔",
    "streak": 5,
    "week_start": "2026-06-15",
    "week_end": "2026-06-22"
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

Every accounts endpoint returns a consistent envelope (except auth failures, which use DRF's default `{"detail": "..."}` shape since they happen before any view code runs):

```json
{ "success": true, "message": "...", "data": { ... } }
```

or, on failure:

```json
{ "success": false, "message": "...", "errors": { ... } }
```

**GET / PATCH `/api/accounts/me/`** — `GET` returns the authenticated user's profile; `PATCH` updates only `full_name`, `phone_number`, `bio`, `date_of_birth`, `gender`. Any other field in the payload (`firebase_uid`, `email`, `username`, `is_staff`, ...) is silently ignored.

**POST `/api/accounts/verify/`** (alias `/api/auth/verify/`) — No auth required; called by the client right after Firebase sign-in/sign-up. Verifies the Firebase ID token and returns a flat (non-enveloped) JSON object, auto-creating the linked `accounts.User` on first sight:

```json
{
  "firebase_uid": "abc123",
  "email": "user@example.com",
  "name": "Alex",
  "picture": "https://...",
  "email_verified": true,
  "is_new_user": false
}
```

### Account Deletion

**DELETE `/api/accounts/delete-account/`** (self-service, requires auth) — Deletes the Firebase identity (`firebase_admin.auth.delete_user`) first, then all matching `therapist.MoodEntry` rows, then the local Django row. If the Firebase-side call fails, the request returns `502` and nothing else is deleted (no orphaned Firebase identity, retryable).

**Web-based deletion request** (no app access required) — The privacy policy (`/privacy/`) promises a way to request deletion for users who can't open the app. That promise is backed by `accounts.services.delete_user_account()` — the exact same function the API endpoint calls — exposed as a management command:

```bash
python manage.py delete_user_by_email someone@example.com
```

Both paths share one implementation, so there's no risk of the manual path doing something different (or less complete) than the in-app one.

---

## Project Structure

```text
ai_therapist_backend/
├── core/
│   ├── settings.py        # Project settings (env-var driven)
│   ├── urls.py            # Root URL routing
│   ├── firebase_auth.py   # FirebaseAuthentication DRF backend + OpenAPI scheme
│   ├── wsgi.py
│   └── asgi.py
├── therapist/
│   ├── models.py          # MoodEntry model
│   ├── views.py           # GenerateResponseAPIView, AllHistoryAPIView, WeeklyLetterAPIView (all IsAuthenticated)
│   ├── serializers.py     # MoodEntrySerializer, MoodEntryCreateSerializer (no user_id field)
│   ├── ai_model.py        # Groq API integration (generate_ai_response)
│   ├── urls.py            # App URL patterns
│   ├── tests.py
│   └── migrations/
├── accounts/
│   ├── models.py          # User (AUTH_USER_MODEL, has firebase_uid)
│   ├── managers.py        # UserManager (email-based create_user/create_superuser)
│   ├── views.py           # MeView, DeleteAccountView only
│   ├── serializers.py     # UserSerializer, UserProfileUpdateSerializer
│   ├── validators.py      # Phone format only
│   ├── services.py        # Response envelope helpers only
│   ├── urls.py            # App URL patterns (me/, delete-account/)
│   ├── tests.py
│   └── migrations/
├── templates/
│   └── index.html         # Home page
├── docs/
│   └── screenshots/       # API docs screenshots (this README)
├── manage.py
├── requirements.txt
├── Procfile                # Gunicorn config for Railway
└── db.sqlite3               # SQLite database (dev, gitignored)
```

---

## Environment Variables

| Variable | Required | Description |
| --- | --- | --- |
| `GROQ_API_KEY` | **Yes** | Groq API key from [console.groq.com](https://console.groq.com) |
| `FIREBASE_CREDENTIALS_PATH` | **Yes** | Path to a Firebase service-account JSON, used to verify ID tokens |
| `SECRET_KEY` | Recommended | Django secret key (has dev fallback) |
| `DEBUG` | No | `"True"` for dev, `"False"` for prod (default: `False`) |

---

## Deployment

### Railway

1. Connect your GitHub repository on [railway.app](https://railway.app)
2. Add environment variables in the Railway dashboard:
   - `GROQ_API_KEY`, `FIREBASE_CREDENTIALS_PATH`, `SECRET_KEY`, `DEBUG=False`
3. Railway auto-detects the `Procfile` and deploys
4. Run migrations via Railway shell: `python manage.py migrate`

### Heroku

```bash
heroku create your-app-name
heroku config:set GROQ_API_KEY="your-api-key"
heroku config:set FIREBASE_CREDENTIALS_PATH="/app/firebase-service-account.json"
heroku config:set SECRET_KEY="your-secret-key"
heroku config:set DEBUG="False"
git push heroku main
heroku run python manage.py migrate
```

### Production checklist

- [ ] `GROQ_API_KEY` set (**required**)
- [ ] `FIREBASE_CREDENTIALS_PATH` set (**required**)
- [ ] Strong `SECRET_KEY` set
- [ ] `DEBUG=False`
- [ ] Restrict `ALLOWED_HOSTS` to your domain
- [ ] Switch to PostgreSQL
- [ ] Add CORS headers (`django-cors-headers`) if frontend is on a different domain
- [ ] Add error logging (Sentry)
- [ ] Set up monitoring and health checks

---

## Testing

```bash
python manage.py test therapist
python manage.py test accounts
```

Tests never hit real external services — mock `generate_ai_response()` for Groq calls and `core.firebase_auth.auth.verify_id_token` / `accounts.views.firebase_auth_admin.delete_user` for Firebase calls:

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

---

## Integration Examples

### cURL

```bash
# Generate AI response (with optional conversation history)
curl -X POST http://localhost:8000/api/companion/generate/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <firebase-id-token>" \
  -d '{"emoji": "😊", "thoughts": "Great day!", "history": []}'

# Get history
curl http://localhost:8000/api/companion/history/ \
  -H "Authorization: Bearer <firebase-id-token>"

# Get weekly letter
curl http://localhost:8000/api/companion/weekly-letter/ \
  -H "Authorization: Bearer <firebase-id-token>"

# Get profile
curl http://localhost:8000/api/accounts/me/ \
  -H "Authorization: Bearer <firebase-id-token>"
```

### JavaScript (Fetch)

```javascript
// Obtain a Firebase ID token on the client first, e.g.:
// const idToken = await firebase.auth().currentUser.getIdToken();

// Generate AI response (pass history for multi-turn context)
const res = await fetch('http://localhost:8000/api/companion/generate/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${idToken}`,
  },
  body: JSON.stringify({
    emoji: '😊',
    thoughts: 'Feeling good!',
    history: [], // prior [{role, content}] messages
  })
});
const data = await res.json();
// If data.ai_response includes '[SESSION_END]', close the session

// Get history
const history = await fetch('http://localhost:8000/api/companion/history/', {
  headers: { Authorization: `Bearer ${idToken}` },
});
const entries = await history.json();

// Get profile
const meRes = await fetch('http://localhost:8000/api/accounts/me/', {
  headers: { Authorization: `Bearer ${idToken}` },
});
```

---

## Troubleshooting

| Problem | Solution |
| --- | --- |
| 500 on POST `/api/companion/generate/` | Check `GROQ_API_KEY` is set and valid |
| 401 on any endpoint | Missing/invalid/expired Firebase ID token, or `FIREBASE_CREDENTIALS_PATH` not set/invalid — check server logs for "Firebase token verification failed" |
| Static files 404 | Run `python manage.py collectstatic` |
| Database locked | Switch to PostgreSQL for concurrent writes |
| Slow responses | Normal — Groq API takes 1–2 seconds |
| 502 on `DELETE /api/accounts/delete-account/` | Firebase-side deletion failed — the local account is intentionally **not** deleted; retry once the Firebase-side issue is resolved |

---

## Disclaimer

This application provides AI-generated supportive messages and is **not a replacement for professional support**.

If you are in crisis, please reach out:

- **US**: 988 (Suicide & Crisis Lifeline)
- **UK**: 116 123 (Samaritans)
- **International**: [findahelpline.com](https://findahelpline.com)

---

Built with Django REST Framework · Powered by Groq API (Llama 3.1 8B) · Authenticated via Firebase Auth

Last Updated: June 22, 2026
