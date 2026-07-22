# -----------------------------------------------------
# Base settings
# -----------------------------------------------------
import sys
import os
from pathlib import Path
import dj_database_url
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "fallback-local-dev-key")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
FIREBASE_CREDENTIALS_PATH = os.environ.get("FIREBASE_CREDENTIALS_PATH", "")
DEBUG = os.environ.get("DEBUG", "False") == "True"
ALLOWED_HOSTS = [
    "web-production-f8628.up.railway.app",
    "127.0.0.1",
    ".railway.app",  # keep for any future railway subdomain changes
]

CORS_ALLOWED_ORIGINS = [
    "https://web-production-f8628.up.railway.app",
]
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = [
    "https://web-production-f8628.up.railway.app",
]

AUTH_USER_MODEL = "accounts.User"

# -----------------------------------------------------
# Installed apps
# -----------------------------------------------------
INSTALLED_APPS = [
    "jazzmin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "therapist",
    "accounts",
]

# -----------------------------------------------------
# Jazzmin admin theme
# -----------------------------------------------------
JAZZMIN_SETTINGS = {
    "site_title": "Lueur Admin",
    "site_header": "Lueur Admin",
    "site_brand": "Lueur Admin",
    "welcome_sign": "Welcome to the Lueur Admin dashboard",
    "copyright": "Lueur",
    "custom_css": "admin/css/lueur-admin.css",
    "icons": {
        "auth": "fas fa-user-shield",
        "auth.Group": "fas fa-users",
        "accounts": "fas fa-user-circle",
        "accounts.User": "fas fa-user",
        "therapist": "fas fa-book-open",
        "therapist.MoodEntry": "fas fa-comment-dots",
    },
}
JAZZMIN_UI_TWEAKS = {
    # "united" is the closest built-in Bootswatch match to Tangerine Glow
    # (--bs-primary: #e95420, an Ubuntu-orange) — flatly's primary was blue/navy (#2c3e50).
    "theme": "united",
    "sidebar": "sidebar-dark-primary",
    "navbar": "navbar-white navbar-light",
    # Locks the admin to light mode permanently — no dark/auto toggle, no
    # following the visitor's OS light/dark preference.
    "default_theme_mode": "light",
}

# -----------------------------------------------------
# Middleware + WhiteNoise
# -----------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # <-- مهم لخدمة static
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# -----------------------------------------------------
# Templates
# -----------------------------------------------------
ROOT_URLCONF = "core.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

WSGI_APPLICATION = "core.wsgi.application"

# -----------------------------------------------------
# Database
# -----------------------------------------------------
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}

# -----------------------------------------------------
# Password validation
# -----------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# -----------------------------------------------------
# Internationalization
# -----------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# -----------------------------------------------------
# Static files
# -----------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "core.storage.LenientManifestStaticFilesStorage",
    },
}

# -----------------------------------------------------
# REST Framework
# -----------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "core.firebase_auth.FirebaseAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "user": "60/minute",
        "ai_generate": "10/minute",
        "luna_chat": "8/min",
    },
}
# -----------------------------------------------------
# Logging
# -----------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}


SPECTACULAR_SETTINGS = {
    "TITLE": "Lueur API",
    "DESCRIPTION": """
## Welcome to the Lueur API 🌱

Lueur is a wellness companion app featuring an AI companion named **Luna**, using a growing
plant metaphor to encourage daily check-ins. This API handles user accounts and
AI-powered mood journaling.

### Features
- 🌸 Firebase-authenticated user accounts
- 💬 AI-powered empathetic responses from Luna (Groq llama-3.1-8b-instant)
- 📔 Mood journal with history tracking
- 😔 Emoji-based mood selection
- 📝 Weekly personalized letters from Luna

### Authentication
All endpoints require a valid **Firebase ID token** in the `Authorization: Bearer <token>`
header. See the FirebaseAuth scheme below.
    """,
    "VERSION": "1.0.0",
    "CONTACT": {
        "name": "Riyam",
        "email": "riyam.thekluge@gmail.com",
    },
    "LICENSE": {"name": "MIT"},
    "SERVE_INCLUDE_SCHEMA": False,
    "TAGS": [
        {
            "name": "Companion",
            "description": "AI mood journal endpoints (Luna)",
        },
        {
            "name": "Accounts",
            "description": "Firebase-authenticated account management endpoints",
        },
    ],
}

# -----------------------------------------------------
# Production security hardening
# -----------------------------------------------------
TESTING = "test" in sys.argv

if not DEBUG and not TESTING:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True


# -----------------------------------------------------
# Sentry error monitoring
# -----------------------------------------------------
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")

if SENTRY_DSN and not DEBUG and not TESTING:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
    )
