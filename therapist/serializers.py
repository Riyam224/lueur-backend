from rest_framework import serializers
from .models import JournalEntry, EntryType


class JournalEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = JournalEntry
        fields = "__all__"
        extra_kwargs = {
            "user_id": {"read_only": True},
            "ai_response": {"read_only": True},
            "created_at": {"read_only": True},
            "id": {"read_only": True},
            "crisis_flagged": {"read_only": True},
        }


class JournalEntryCreateSerializer(serializers.ModelSerializer):
    thoughts = serializers.CharField(max_length=5000)
    context_flag = serializers.ChoiceField(
        choices=[("post_exercise_breathing", "post_exercise_breathing")],
        required=False,
        allow_null=True,
    )
    history = serializers.ListField(
        child=serializers.DictField(
            child=serializers.CharField(
                max_length=5000
            ),
        ),
        required=False,
        default=list,
        max_length=20,

    )

    class Meta:
        model = JournalEntry
        fields = ("emoji", "thoughts", "history", "context_flag")
        extra_kwargs = {
            "history": {"write_only": True},
            "context_flag": {"write_only": True},
        }


ACTIVITY_ENTRY_TYPE_CHOICES = [
    choice for choice in EntryType.choices if choice[0] != EntryType.MOOD_CHAT
]


class ActivityEntryCreateSerializer(serializers.Serializer):
    entry_type = serializers.ChoiceField(choices=ACTIVITY_ENTRY_TYPE_CHOICES, required=True)
    payload = serializers.JSONField(required=False, default=dict)

    def validate(self, attrs):
        entry_type = attrs.get("entry_type")
        payload = attrs.get("payload") or {}

        if not isinstance(payload, dict):
            raise serializers.ValidationError({"payload": "payload must be an object."})

        if entry_type == EntryType.BREATHING:
            if not isinstance(payload.get("duration_seconds"), int) or isinstance(
                payload.get("duration_seconds"), bool
            ):
                raise serializers.ValidationError(
                    {"payload": "breathing requires an integer 'duration_seconds'."}
                )
        elif entry_type == EntryType.SUDOKU:
            if not isinstance(payload.get("solved"), bool):
                raise serializers.ValidationError(
                    {"payload": "sudoku requires a boolean 'solved'."}
                )
            if not isinstance(payload.get("duration_seconds"), int) or isinstance(
                payload.get("duration_seconds"), bool
            ):
                raise serializers.ValidationError(
                    {"payload": "sudoku requires an integer 'duration_seconds'."}
                )
            if not isinstance(payload.get("difficulty"), str):
                raise serializers.ValidationError(
                    {"payload": "sudoku requires a string 'difficulty'."}
                )
        elif entry_type == EntryType.DRAWING:
            if not isinstance(payload.get("thumbnail_url"), str):
                raise serializers.ValidationError(
                    {"payload": "drawing requires a string 'thumbnail_url'."}
                )
        elif entry_type == EntryType.LETTER_READ:
            pass

        attrs["payload"] = payload
        return attrs
