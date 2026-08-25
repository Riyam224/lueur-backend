from rest_framework import serializers
from .models import JournalEntry


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
