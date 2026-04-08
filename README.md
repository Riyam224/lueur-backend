# MindEase — AI Therapist Backend

A Django REST Framework backend that provides AI-powered emotional support. Users share their mood with an emoji and thoughts, and **Luna** (the AI therapist) responds with an empathetic, personalised message. All entries are saved per user for history tracking and weekly reflections.

Powered by **Groq API with Llama 3.1 8B Instant** — no local GPU or ML dependencies required.

---

## Features

- **Luna AI responses** — warm, empathetic replies via Groq's fast cloud API
- **Mood journal** — every entry (emoji + thoughts + AI reply) is saved per user
- **Weekly letter** — Luna writes a personal weekly reflection based on recent entries
- **Per-user data isolation** — each user only sees their own entries
- **Interactive API docs** — Swagger UI at `/api/docs/`
- **Production-ready** — Railway/Heroku deployment with Gunicorn + WhiteNoise

---

## Technology Stack

| Layer | Technology |
| --- | --- |
| Framework | Django 5.1.4 + Django REST Framework 3.17.1 |
| AI Model | Groq API — `llama-3.1-8b-instant` (cloud) |
| API Docs | drf-spectacular (Swagger UI + ReDoc) |
| Database | SQLite (dev) / PostgreSQL (prod recommended) |
| HTTP Client | Python `requests` |
| Static Files | WhiteNoise |
| Deployment | Gunicorn + Railway/Heroku |

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
export SECRET_KEY="your-secret-key"   # optional in dev
export DEBUG="True"                   # optional in dev

# 5. Run migrations
python manage.py migrate

# 6. Start the server
python manage.py runserver
```

Server runs at `http://127.0.0.1:8000/`

---

## API Endpoints

Base URL: `/api/therapist/`

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | `/api/therapist/generate/` | Submit mood, get Luna's AI response |
| GET | `/api/therapist/history/` | Get all saved entries for a user |
| GET | `/api/therapist/weekly-letter/` | Get Luna's weekly reflection letter |

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
  "thoughts": "Feeling overwhelmed with everything lately"
}
```

**`user_id` rules**: 3–128 characters, letters / numbers / `_` / `-` only.

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

**Error (400)** — invalid or missing fields:
```json
{
  "user_id": ["This field is required."]
}
```

If the Groq API is unavailable, the entry is still saved with a fallback message:
`"Could not generate a response at this time. Please try again later."`

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

## Project Structure

```
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
│   └── migrations/
├── templates/
│   └── index.html         # Home page
├── manage.py
├── requirements.txt
├── Procfile               # Gunicorn config for Railway/Heroku
└── db.sqlite3             # SQLite database (dev)
```

---

## Environment Variables

| Variable | Required | Description |
| --- | --- | --- |
| `GROQ_API_KEY` | **Yes** | Groq API key from [console.groq.com](https://console.groq.com) |
| `SECRET_KEY` | Recommended | Django secret key (has dev fallback) |
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
```

Mock the AI function to keep tests fast and offline:

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

---

## Integration Examples

### cURL
```bash
# Generate AI response
curl -X POST http://localhost:8000/api/therapist/generate/ \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_123", "emoji": "😊", "thoughts": "Great day!"}'

# Get history
curl "http://localhost:8000/api/therapist/history/?user_id=user_123"

# Get weekly letter
curl "http://localhost:8000/api/therapist/weekly-letter/?user_id=user_123"
```

### JavaScript (Fetch)
```javascript
// Generate AI response
const res = await fetch('http://localhost:8000/api/therapist/generate/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ user_id: 'user_123', emoji: '😊', thoughts: 'Feeling good!' })
});
const data = await res.json();

// Get history
const history = await fetch('http://localhost:8000/api/therapist/history/?user_id=user_123');
const entries = await history.json();
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

---

## Disclaimer

This application provides AI-generated supportive messages and is **not a replacement for professional mental health services**.

If you are in crisis, please reach out:
- **US**: 988 (Suicide & Crisis Lifeline)
- **UK**: 116 123 (Samaritans)
- **International**: [findahelpline.com](https://findahelpline.com)

---

**Built with Django REST Framework · Powered by Groq API (Llama 3.1 8B)**

Last Updated: April 8, 2026
