import base64
import json
import logging
import os

import firebase_admin
from django.conf import settings
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from firebase_admin import auth, credentials
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from accounts.models import User

logger = logging.getLogger(__name__)


def _init_firebase():
    if firebase_admin._apps:
        return

    # Preferred: base64-encoded JSON (safe from newline/escaping corruption)
    firebase_creds_b64 = os.environ.get("FIREBASE_CREDENTIALS_JSON_B64")
    if firebase_creds_b64:
        try:
            decoded = base64.b64decode(firebase_creds_b64).decode("utf-8")
            cred_dict = json.loads(decoded)
        except Exception as exc:
            logger.error("FIREBASE_CREDENTIALS_JSON_B64 is invalid: %s", exc)
            return
        firebase_admin.initialize_app(credentials.Certificate(cred_dict))
        logger.info("Firebase initialized from FIREBASE_CREDENTIALS_JSON_B64.")
        return

    # Fallback: raw JSON env var
    firebase_creds_json = os.environ.get("FIREBASE_CREDENTIALS_JSON")
    if firebase_creds_json:
        try:
            cred_dict = json.loads(firebase_creds_json)
        except json.JSONDecodeError as exc:
            logger.error("FIREBASE_CREDENTIALS_JSON is not valid JSON: %s", exc)
            return
        firebase_admin.initialize_app(credentials.Certificate(cred_dict))
        logger.info("Firebase initialized from FIREBASE_CREDENTIALS_JSON.")
        return

    # Fallback: local file path
    if settings.FIREBASE_CREDENTIALS_PATH:
        firebase_admin.initialize_app(
            credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
        )
        logger.info("Firebase initialized from FIREBASE_CREDENTIALS_PATH file.")
        return

    logger.warning("Firebase not initialized: no credentials source found.")


_init_firebase()


class FirebaseAuthentication(BaseAuthentication):
    """Resolves request.user from a verified Firebase ID token.

    Identity comes exclusively from the verified token's `uid` claim —
    never from the request body or query parameters.
    """

    keyword = "Bearer"

    def authenticate(self, request):
        header = request.META.get("HTTP_AUTHORIZATION", "")
        if not header.startswith(f"{self.keyword} "):
            return None
        token = header[len(self.keyword) + 1 :].strip()
        if not token:
            return None

        try:
            decoded = auth.verify_id_token(token)
        except Exception as exc:
            logger.warning("Firebase token verification failed: %s", exc)
            raise AuthenticationFailed("Invalid or expired token.")

        uid = decoded["uid"]
        email = decoded.get("email") or f"{uid}@firebase.local"

        user, _ = User.objects.get_or_create(
            firebase_uid=uid,
            defaults={"email": email, "username": uid},
        )
        return (user, None)

    def authenticate_header(self, request):
        return self.keyword


class FirebaseAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "core.firebase_auth.FirebaseAuthentication"
    name = "FirebaseAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "Firebase ID token",
        }