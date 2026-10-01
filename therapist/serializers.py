from rest_framework import serializers
from .models import ContentReport, JournalEntry, EntryType


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


HISTORY_MAX_TOTAL_CHARS = 12000
HISTORY_ITEM_MAX_CHARS = 5000
_HISTORY_MESSAGE_KEYS = {"role", "content"}


class HistoryMessageSerializer(serializers.Serializer):
    # Only user/assistant turns are accepted — history is passed straight
    # into the Groq messages list, so a client-supplied "system" turn would
    # override Luna's prompt.
    role = serializers.ChoiceField(choices=["user", "assistant"])
    content = serializers.CharField()

    def validate_content(self, value):
        # An over-long item is cut to the first HISTORY_ITEM_MAX_CHARS
        # characters instead of rejecting the whole request.
        return value[:HISTORY_ITEM_MAX_CHARS]

    def to_internal_value(self, data):
        if isinstance(data, dict):
            extra = set(data) - _HISTORY_MESSAGE_KEYS
            if extra:
                raise serializers.ValidationError(
                    "Only 'role' and 'content' are allowed; got unexpected "
                    f"key(s): {', '.join(sorted(extra))}."
                )
        return super().to_internal_value(data)


class JournalEntryCreateSerializer(serializers.ModelSerializer):
    thoughts = serializers.CharField(max_length=5000)
    context_flag = serializers.ChoiceField(
        choices=[("post_exercise_breathing", "post_exercise_breathing")],
        required=False,
        allow_null=True,
    )
    history = serializers.ListField(
        child=HistoryMessageSerializer(),
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

    def validate_history(self, history):
        # Over the total cap: drop the oldest messages rather than rejecting
        # the request, so a long conversation never breaks the chat.
        history = [dict(message) for message in history]
        total = sum(len(message["content"]) for message in history)
        while history and total > HISTORY_MAX_TOTAL_CHARS:
            total -= len(history.pop(0)["content"])
        return history


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


class ContentReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentReport
        fields = ("reported_text", "user_message", "reason", "comment", "status")
        extra_kwargs = {
            "user_message": {"required": False},
            "comment": {"required": False},
            "status": {"read_only": True},
        }
