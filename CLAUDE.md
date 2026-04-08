# CLAUDE.md - AI Therapist Backend

Technical documentation for Claude Code to understand and work with this Django project.

## Project Overview

This is a Django REST Framework application that provides an AI-powered mental health support API. It uses the **Groq API with Llama 3.1 8B Instant model** to generate empathetic responses to user mood inputs. The AI companion is named **Luna**.

## Architecture

### Application Structure

- **Django Project**: `core/` - Main project configuration
- **Django App**: `therapist/` - Main application handling mood entries and AI responses
- **Database**: SQLite (default), easily swappable for PostgreSQL/MySQL
- **AI Service**: Groq API (external REST API) accessed via [therapist/ai_model.py](therapist/ai_model.py)
- **API Docs**: drf-spectacular (Swagger UI at `/api/docs/`, ReDoc at `/api/redoc/`)
- **Deployment**: Railway-ready with WhiteNoise for static files

### Key Components

1. **Model Layer** ([therapist/models.py](therapist/models.py))
   - `MoodEntry`: Stores user mood data
     - Fields: `user_id` (CharField, db_index), `emoji`, `thoughts`, `ai_response`, `created_at`
     - `user_id` scopes all entries to a specific user — all queries must filter by it
     - Uses auto-generated timestamps (`auto_now_add=True`)
     - String representation: `"{user_id} | {emoji} - {thoughts[:20]}"`
     - Meta: `verbose_name` and `verbose_name_plural` configured

2. **View Layer** ([therapist/views.py](therapist/views.py))
   - Uses **class-based APIView** (DRF)
   - `GenerateResponseAPIView`: POST-only endpoint
     - Validates input with `MoodEntryCreateSerializer` (user_id, emoji, thoughts required)
     - Calls `generate_ai_response()` from ai_model
     - On AI error: catches exception, saves fallback message, still returns 200
     - Creates `MoodEntry` and returns serialized data (200)
   - `AllHistoryAPIView`: GET-only endpoint
     - Requires `user_id` query param — returns 400 if missing
     - Returns entries filtered by `user_id`, ordered by `created_at` DESC
   - `WeeklyLetterAPIView`: GET-only endpoint
     - Requires `user_id` query param
     - Fetches last 7 days of entries for that user
     - Returns `{"letter": null, "reason": "not_enough_entries"}` if fewer than 2 entries
     - Calls Groq API directly to generate a personal weekly letter from Luna
     - Returns letter text + stats (entry_count, dominant_emoji, streak, week_start, week_end)

3. **AI Service** ([therapist/ai_model.py](therapist/ai_model.py))
   - Function: `generate_ai_response(emoji, thoughts) -> str`
   - Uses **Groq API** (external cloud service), model: `llama-3.1-8b-instant`
   - Requires `GROQ_API_KEY` environment variable
   - Makes REST POST to `https://api.groq.com/openai/v1/chat/completions`
   - System prompt: warm, supportive AI therapist, short empathetic responses
   - **No local model loading** — stateless, synchronous API calls
   - Does not handle exceptions — caller is responsible

4. **Serializers** ([therapist/serializers.py](therapist/serializers.py))
   - `USER_ID_VALIDATOR`: regex `^[A-Za-z0-9_-]{3,128}$` — used on both serializers
   - `MoodEntrySerializer`: full read serializer — `fields = "__all__"`, `ai_response`/`created_at`/`id` read-only
   - `MoodEntryCreateSerializer`: write serializer — only exposes `user_id`, `emoji`, `thoughts`

### URL Routing

- **Main URLs** ([core/urls.py](core/urls.py)):
  - `/` → Home page (`templates/index.html`)
  - `/admin/` → Django admin interface
  - `/api/therapist/` → Includes therapist app URLs
  - `/api/schema/` → OpenAPI schema
  - `/api/docs/` → Swagger UI
  - `/api/redoc/` → ReDoc UI

- **Therapist URLs** ([therapist/urls.py](therapist/urls.py)):
  - `generate/` → `GenerateResponseAPIView` (POST only)
  - `history/` → `AllHistoryAPIView` (GET only)
  - `weekly-letter/` → `WeeklyLetterAPIView` (GET only)

### Full API Endpoints

- `POST /api/therapist/generate/` — Create mood entry with AI response
- `GET /api/therapist/history/?user_id=<id>` — Retrieve entries for a user
- `GET /api/therapist/weekly-letter/?user_id=<id>` — Get Luna's weekly letter

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
- `drf-spectacular` — OpenAPI schema + Swagger/ReDoc
- `requests==2.33.0` — HTTP client for Groq API calls
- `gunicorn==25.3.0` — Production WSGI server
- `whitenoise==6.5.0` — Static file serving for production
- `certifi==2026.2.25` — SSL certificate bundle

**Note**: No `torch` or `transformers` — uses external API instead of local model.

### Testing

- Test file: [therapist/tests.py](therapist/tests.py)
- Run with: `python manage.py test therapist`
- Always mock `generate_ai_response()` to avoid real API calls

Example:
```python
from django.test import TestCase
from rest_framework.test import APIClient
from unittest.mock import patch

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
generate_ai_response(emoji: str, thoughts: str) -> str
```
- Makes POST request to Groq API
- Uses `llama-3.1-8b-instant` model
- Returns AI-generated response text
- Raises exceptions on failure — caller must handle

### Security Considerations

**Current State** ([core/settings.py](core/settings.py)):
- ✅ `SECRET_KEY` uses environment variable with fallback
- ✅ `DEBUG` uses environment variable (defaults to False)
- ✅ `ALLOWED_HOSTS` configured for Railway (`["*", ".railway.app"]`)
- ✅ WhiteNoise configured for secure static file serving
- ✅ `user_id` validated with strict regex on all endpoints
- ⚠️ `ALLOWED_HOSTS = ["*"]` allows all hosts — restrict in production
- ⚠️ No CORS headers — add `django-cors-headers` if frontend on a different domain
- ⚠️ No authentication — anyone can submit/read entries

**Environment Variables Required**:
- `GROQ_API_KEY` — **Required** for AI functionality
- `SECRET_KEY` — Optional (has fallback for dev)
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

**Production** (uses Gunicorn per [Procfile](Procfile)):
```bash
gunicorn core.wsgi --log-file -
```

## API Behaviour

### POST Request Flow (Generate Endpoint)

1. Request received at `POST /api/therapist/generate/`
2. Input validated by `MoodEntryCreateSerializer` — 400 if invalid
3. `generate_ai_response()` called; exception caught → fallback message used
4. `MoodEntry` created with user_id, emoji, thoughts, ai_response
5. Serialized response returned (200)

### GET Request Flow (History Endpoint)

1. Request received at `GET /api/therapist/history/?user_id=...`
2. `user_id` extracted from query params — 400 if missing
3. `MoodEntry.objects.filter(user_id=user_id).order_by("-created_at")`
4. All matching entries serialized and returned

### GET Request Flow (Weekly Letter Endpoint)

1. Request received at `GET /api/therapist/weekly-letter/?user_id=...`
2. `user_id` extracted — 400 if missing
3. Entries from last 7 days fetched for that user
4. If < 2 entries: `{"letter": null, "reason": "not_enough_entries"}` (200)
5. Entries formatted, dominant emoji found
6. Groq API called to generate personal letter from Luna (timeout: 10s)
7. Returns `{"letter": "...", "stats": {...}}` (200)

### Error Handling

- **400**: Invalid/missing required fields
- **200 with fallback**: Groq API error in generate/ (entry still saved)
- **200 with letter: null**: Groq API error in weekly-letter/
- No rate limiting currently implemented

## Data Isolation

All `MoodEntry` queries are scoped to `user_id`. Users cannot see each other's entries. The `user_id` field is indexed (`db_index=True`) for query performance.

## File Organization

```
ai_therapist_backend/
├── core/
│   ├── settings.py       # All Django settings (env-var driven, Railway-ready)
│   ├── urls.py           # Root URL configuration
│   ├── wsgi.py           # WSGI entry point (Gunicorn)
│   └── asgi.py           # ASGI entry point
├── therapist/
│   ├── models.py         # MoodEntry model
│   ├── views.py          # GenerateResponseAPIView, AllHistoryAPIView, WeeklyLetterAPIView
│   ├── serializers.py    # MoodEntrySerializer, MoodEntryCreateSerializer
│   ├── ai_model.py       # Groq API integration
│   ├── urls.py           # App URL patterns
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
├── Procfile              # Gunicorn config for Railway/Heroku
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

1. **Authentication**: Add Django auth or JWT tokens
2. **Filtering**: Query parameters for date ranges, emoji filters
3. **Pagination**: DRF pagination classes on history endpoint
4. **Rate Limiting**: DRF throttling to prevent API abuse
5. **CORS**: `django-cors-headers` for cross-origin frontend

### API Service Improvements

1. **Async Calls**: Use async/await for non-blocking Groq requests
2. **Streaming**: Streaming responses for real-time generation
3. **Retry Logic**: Exponential backoff for failed API calls
4. **Context**: Pass conversation history for context-aware responses

## Known Limitations

1. No authentication — anyone can submit/read entries
2. Synchronous Groq API calls — blocks request during generation
3. SQLite — not suitable for concurrent production writes
4. No rate limiting — vulnerable to spam/API cost abuse
5. No input sanitization beyond field presence + regex
6. `ALLOWED_HOSTS = ["*"]` — too permissive for production

## Deployment Checklist

- [x] `DEBUG = False` in production (via env var)
- [x] `SECRET_KEY` via environment variable
- [x] Static files configured with WhiteNoise
- [x] `user_id` data isolation implemented
- [ ] **Set `GROQ_API_KEY`** (CRITICAL)
- [ ] Restrict `ALLOWED_HOSTS` to specific domain
- [ ] Use PostgreSQL
- [ ] Add CORS headers if needed
- [ ] Configure rate limiting (DRF throttling)
- [ ] Add error logging (Sentry)
- [ ] Set up monitoring

## Debugging Tips

1. **AI not working**: Check `GROQ_API_KEY` is set
2. **Slow responses**: Normal — Groq API takes 1–2 seconds
3. **401 Unauthorized from Groq**: Invalid or missing API key
4. **Database locked**: SQLite concurrency issue — use PostgreSQL
5. **Import errors**: Activate virtual environment first
6. **Static files 404**: Run `python manage.py collectstatic`

---

**Last Updated**: 2026-04-08
**Django Version**: 5.1.4
**Python Version**: 3.13
**AI Provider**: Groq API (Llama 3.1 8B Instant)
