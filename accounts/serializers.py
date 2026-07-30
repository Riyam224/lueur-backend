from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import User
from .validators import validate_phone_number


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "username",
            "full_name",
            "phone_number",
            "bio",
            "date_of_birth",
            "gender",
            "preferred_language",
            "is_verified",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "full_name",
            "phone_number",
            "bio",
            "date_of_birth",
            "gender",
            "preferred_language",
        )
        extra_kwargs = {
            "preferred_language": {
                "help_text": "UI language preference for the Flutter client. 'en' (English) or 'ar' (Arabic)."
            }
        }

    def validate_phone_number(self, value):
        try:
            validate_phone_number(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages)
        return value


class VerifyTokenSerializer(serializers.Serializer):
    firebase_token = serializers.CharField()
