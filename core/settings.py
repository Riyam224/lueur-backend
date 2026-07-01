# -----------------------------------------------------
# Base settings
# -----------------------------------------------------
import sys
import os
from pathlib import Path
import dj_database_url


BASE_DIR = Path(__file__).resolve().parent.parent

# Move to Railway environment variables
SECRET_KEY = os.environ.get("SECRET_KEY", "fallback-local-dev-key")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
FIREBASE_CREDENTIALS_PATH = os.environ.get("FIREBASE_CREDENTIALS_PATH", "")
DEBUG = os.environ.get("DEBUG", "False") == "True"
ALLOWED_HOSTS = [
    "web-production-f8628.up.railway.app",
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
# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.sqlite3",
#         "NAME": BASE_DIR / "db.sqlite3",
#     }
# }

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
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

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
    "TITLE": "MindEase AI Therapist API",
    "DESCRIPTION": """
## Welcome to MindEase API 🌸

MindEase is an AI-powered mood journal that uses GROQ AI 
to provide empathetic responses to your emotional entries.

### Features
- 🤖 AI-powered emotional support responses
- 📔 Mood journal with history tracking  
- 😔 Emoji-based mood selection
- 💜 Powered by GROQ llama-3.1-8b-instant
    """,
    "VERSION": "1.0.0",
    "CONTACT": {
        "name": "Riyam",
        "email": "your@email.com",
    },
    "LICENSE": {"name": "MIT"},
    "SERVE_INCLUDE_SCHEMA": False,
    "TAGS": [
        {
            "name": "Therapist",
            "description": "AI mood journal endpoints",
        },
        {
            "name": "Accounts",
            "description": "Authentication and account management endpoints",
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