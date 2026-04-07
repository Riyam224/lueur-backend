from rest_framework import serializers
from django.core.validators import RegexValidator
from .models import MoodEntry


USER_ID_VALIDATOR = RegexValidator(
    regex=r"^[A-Za-z0-9_-]{3,128}$",
    message="user_id must be 3-128 characters and contain only letters, numbers, underscore, or hyphen.",
)


class MoodEntrySerializer(serializers.ModelSerializer):
    user_id = serializers.CharField(
        min_length=3,
        max_length=128,
        validators=[USER_ID_VALIDATOR],
    )

    class Meta:
        model = MoodEntry
        fields = "__all__"
        extra_kwargs = {
            "ai_response": {"read_only": True},
            "created_at": {"read_only": True},
            "id": {"read_only": True},
        }


class MoodEntryCreateSerializer(serializers.ModelSerializer):
    user_id = serializers.CharField(
        min_length=3,
        max_length=128,
        validators=[USER_ID_VALIDATOR],
    )

    class Meta:
        model = MoodEntry
        fields = ("user_id", "emoji", "thoughts")
