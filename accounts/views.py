import logging

from drf_spectacular.utils import OpenApiResponse, extend_schema
from firebase_admin import auth as firebase_auth_admin
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import User
from .serializers import (
    UserProfileUpdateSerializer,
    UserSerializer,
    VerifyTokenSerializer,
)
from .services import delete_user_account, error_response, success_response

logger = logging.getLogger(__name__)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Accounts"],
        summary="Get current user's profile",
        responses={200: UserSerializer},
    )
    def get(self, request):
        return Response(
            success_response(
                "Profile retrieved.", UserSerializer(request.user).data
            )
        )

    @extend_schema(
        tags=["Accounts"],
        summary="Update current user's profile",
        description="Updates editable profile fields only. Identity-bearing fields are not editable here.",
        request=UserProfileUpdateSerializer,
        responses={
            200: UserSerializer,
            400: OpenApiResponse(description="Validation failed"),
        },
    )
    def patch(self, request):
        serializer = UserProfileUpdateSerializer(
            request.user, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return Response(
                error_response("Validation failed.", serializer.errors),
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer.save()
        return Response(
            success_response(
                "Profile updated.", UserSerializer(request.user).data
            )
        )


class DeleteAccountView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Accounts"],
        summary="Permanently delete account",
        description="Deletes the authenticated user's Firebase identity and local account. Owner-only; no request body.",
        responses={
            200: OpenApiResponse(description="Account deleted permanently"),
            502: OpenApiResponse(description="Firebase identity deletion failed"),
        },
    )
    def delete(self, request):
        user = request.user
        try:
            delete_user_account(user)
        except Exception as exc:
            logger.error(
                "Firebase delete_user failed for uid=%s: %s",
                user.firebase_uid,
                exc,
            )
            return Response(
                error_response(
                    "Failed to delete Firebase identity. Account not deleted."
                ),
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(success_response("Account deleted permanently."))


class VerifyFirebaseTokenView(APIView):
    """Verifies a Firebase ID token and returns the linked Django user.

    Called by the Flutter client right after Firebase sign-in/sign-up/Google
    sign-in — this is where the local `accounts.User` row is created on first
    sight. Response is a flat JSON object (not the usual success/data
    envelope) to match the existing Flutter `DjangoUserModel.fromJson` contract.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        tags=["Accounts"],
        summary="Verify a Firebase ID token",
        description=(
            "Verifies a Firebase ID token with the Firebase Admin SDK and "
            "creates the linked Django user on first sight."
        ),
        request=VerifyTokenSerializer,
        responses={
            200: OpenApiResponse(description="Token verified"),
            400: OpenApiResponse(description="Missing firebase_token"),
            401: OpenApiResponse(description="Invalid or expired token"),
            502: OpenApiResponse(description="Firebase verification service error"),
        },
    )
    def post(self, request):
        serializer = VerifyTokenSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                error_response("firebase_token is required.", serializer.errors),
                status=status.HTTP_400_BAD_REQUEST,
            )

        token = serializer.validated_data["firebase_token"]

        try:
            decoded = firebase_auth_admin.verify_id_token(token)
        except (
            firebase_auth_admin.ExpiredIdTokenError,
            firebase_auth_admin.InvalidIdTokenError,
            firebase_auth_admin.RevokedIdTokenError,
        ) as exc:
            logger.warning("Firebase token verification rejected: %s", exc)
            return Response(
                error_response("Invalid or expired token."),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except Exception as exc:
            logger.error("Firebase token verification errored: %s", exc)
            return Response(
                error_response("Could not verify token. Please try again."),
                status=status.HTTP_502_BAD_GATEWAY,
            )

        uid = decoded["uid"]
        email = decoded.get("email") or f"{uid}@firebase.local"
        name = decoded.get("name", "")
        picture = decoded.get("picture", "")
        email_verified = decoded.get("email_verified", False)

        user, created = User.objects.get_or_create(
            firebase_uid=uid,
            defaults={
                "email": email,
                "username": uid,
                "full_name": name,
                "is_verified": email_verified,
            },
        )
        if not created and (user.full_name != name and name):
            user.full_name = name
            user.save(update_fields=["full_name"])

        return Response(
            {
                "firebase_uid": user.firebase_uid,
                "email": user.email,
                "name": user.full_name,
                "picture": picture,
                "email_verified": email_verified,
                "is_new_user": created,
            }
        )
