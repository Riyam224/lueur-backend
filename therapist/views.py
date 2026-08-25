import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import (
    extend_schema,
    OpenApiExample,
    OpenApiResponse,
)
from .ai_model import (
    generate_ai_response,
    generate_weekly_letter,
    SESSION_END_TAG,
    trigger_memory_update,
)
from .services import build_weekly_letter_context
from .crisis import contains_crisis_language
from .crisis_ar import contains_crisis_language_ar
from .luna_prompts import LunaPromptProvider
from .serializers import (
    JournalEntrySerializer,
    JournalEntryCreateSerializer,
    ActivityEntryCreateSerializer,
)
from datetime import timedelta
from django.utils import timezone
from .models import JournalEntry
from rest_framework.throttling import ScopedRateThrottle
from .throttles import LunaChatRateThrottle

logger = logging.getLogger(__name__)


class GenerateResponseAPIView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle, LunaChatRateThrottle]
    throttle_scope = "ai_generate"

    @extend_schema(
        tags=["Companion"],
        summary="Generate AI response",
        description="""
Send an emoji and your thoughts to Luna, your AI companion.
Luna will respond with an empathetic, supportive message.

The entry is automatically saved to your journal history.
        """,
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "emoji": {"type": "string", "example": "😔"},
                    "thoughts": {
                        "type": "string",
                        "example": "I feel overwhelmed lately",
                    },
                    "history": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "role": {"type": "string", "example": "user"},
                                "content": {"type": "string", "example": "I feel sad"},
                            },
                        },
                        "example": [],
                    },
                },
                "required": ["emoji", "thoughts"],
            }
        },
        responses={
            200: JournalEntrySerializer,
            400: OpenApiResponse(description="Missing emoji or thoughts"),
            401: OpenApiResponse(description="Authentication required"),
        },
        examples=[
            OpenApiExample(
                "Overwhelmed example",
                value={
                    "emoji": "😔",
                    "thoughts": "I feel very overwhelmed with everything lately",
                    "history": [],
                },
                request_only=True,
            ),
            OpenApiExample(
                "Happy example",
                value={
                    "emoji": "😊",
                    "thoughts": "I feel happy and grateful today!",
                    "history": [],
                },
                request_only=True,
            ),
            OpenApiExample(
                "Anxious example",
                value={
                    "emoji": "😰",
                    "thoughts": "I am anxious about my future career",
                    "history": [],
                },
                request_only=True,
            ),
        ],
    )
    def post(self, request):
        input_serializer = JournalEntryCreateSerializer(data=request.data)
        if not input_serializer.is_valid():
            return Response(input_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        emoji = input_serializer.validated_data["emoji"]
        thoughts = input_serializer.validated_data["thoughts"]
        history = input_serializer.validated_data.get("history", [])[-10:]
        context_flag = input_serializer.validated_data.get("context_flag")

        # Both detectors always run, regardless of preferred_language: a user
        # set to 'en' may still type in Arabic and vice versa. Each is a
        # cheap regex over a short keyword list (negligible next to the
        # network-bound Groq call below), so there's no performance reason
        # to gate either one on preferred_language.
        crisis_hit_languages = []
        if contains_crisis_language(thoughts):
            crisis_hit_languages.append("en")
        if contains_crisis_language_ar(thoughts):
            crisis_hit_languages.append("ar")

        if crisis_hit_languages:
            logger.warning(
                "Crisis language detected (languages=%s) for user_id=%s",
                ",".join(crisis_hit_languages),
                request.user.id,
            )
            crisis_response = LunaPromptProvider.get_crisis_response(
                request.user.preferred_language, request.user.gender
            )
            entry = JournalEntry.objects.create(
                user_id=str(request.user.id),
                emoji=emoji,
                thoughts=thoughts,
                ai_response=crisis_response,
                crisis_flagged=True,
            )
            data = JournalEntrySerializer(entry).data
            return Response(data, status=status.HTTP_200_OK)

        try:
            ai_reply = generate_ai_response(
                emoji,
                thoughts,
                history,
                request.user.preferred_language,
                request.user.gender,
                memory_summary=request.user.memory_summary,
                context_flag=context_flag,
            )
        except Exception as e:
            logger.error("Groq AI error: %s", e)
            ai_reply = LunaPromptProvider.get_groq_error_fallback(request.user.preferred_language)

        entry = JournalEntry.objects.create(
            user_id=str(request.user.id),
            emoji=emoji,
            thoughts=thoughts,
            ai_response=ai_reply,
            crisis_flagged=False,
        )

        if SESSION_END_TAG in ai_reply:
            trigger_memory_update(
                request.user.id,
                history,
                emoji,
                thoughts,
                ai_reply,
                request.user.preferred_language,
                request.user.gender,
            )

        data = JournalEntrySerializer(entry).data
        return Response(data, status=status.HTTP_200_OK)


class ActivityEntryAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Companion"],
        summary="Log a non-chat activity entry",
        description="""
Records a completed activity (breathing exercise, sudoku, drawing, or weekly
letter read) to the authenticated user's journal history. No AI response is
generated.
        """,
        request=ActivityEntryCreateSerializer,
        responses={
            201: JournalEntrySerializer,
            400: OpenApiResponse(description="Invalid entry_type or payload"),
            401: OpenApiResponse(description="Authentication required"),
        },
    )
    def post(self, request):
        input_serializer = ActivityEntryCreateSerializer(data=request.data)
        if not input_serializer.is_valid():
            return Response(input_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        entry = JournalEntry.objects.create(
            user_id=str(request.user.id),
            entry_type=input_serializer.validated_data["entry_type"],
            payload=input_serializer.validated_data["payload"],
        )
        data = JournalEntrySerializer(entry).data
        return Response(data, status=status.HTTP_201_CREATED)


class AllHistoryAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Companion"],
        summary="Get mood history",
        description="""
Returns all saved mood journal entries for the authenticated user, ordered by most recent first.

Each entry contains:
- **user_id** — the user ID the entry belongs to
- **emoji** — the mood emoji selected by the user
- **thoughts** — what the user shared
- **ai_response** — Luna's empathetic response
- **created_at** — timestamp of the entry
        """,
        responses={
            200: JournalEntrySerializer(many=True),
            401: OpenApiResponse(description="Authentication required"),
        },
        examples=[
            OpenApiExample(
                "History response",
                value=[
                    {
                        "id": 1,
                        "user_id": "1",
                        "emoji": "😔",
                        "thoughts": "I feel overwhelmed",
                        "ai_response": "It sounds like you are carrying a lot right now...",
                        "created_at": "2026-03-27T12:00:00Z",
                    },
                    {
                        "id": 2,
                        "user_id": "1",
                        "emoji": "😊",
                        "thoughts": "Feeling grateful today",
                        "ai_response": "That is beautiful! Gratitude is a powerful...",
                        "created_at": "2026-03-26T09:30:00Z",
                    },
                ],
                response_only=True,
            ),
        ],
    )
    def get(self, request):
        entries = JournalEntry.objects.filter(
            user_id=str(request.user.id)
        ).order_by("-created_at")
        return Response(JournalEntrySerializer(entries, many=True).data)


def calculate_streak(user_id, now=None):
    # Intentionally unfiltered by entry_type — any activity (mood_chat,
    # breathing, sudoku, drawing, letter_read) counts toward the streak,
    # per product decision. Do not add an entry_type filter here.
    now = now or timezone.now()
    today = timezone.localtime(now).date()

    dates = sorted(
        {
            timezone.localtime(dt).date()
            for dt in JournalEntry.objects.filter(user_id=str(user_id)).values_list(
                "created_at", flat=True
            )
        },
        reverse=True,
    )
    if not dates:
        return 0
    if (today - dates[0]).days > 1:
        return 0

    streak, cursor = 0, dates[0]
    for d in dates:
        if d == cursor:
            streak += 1
            cursor -= timedelta(days=1)
        elif d < cursor:
            break
    return streak

class WeeklyLetterAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Companion"],
        summary="Get Luna's weekly letter",
        description="Generates a personal weekly letter from Luna based on the authenticated user's recent entries.",
        responses={
            200: OpenApiResponse(description="Weekly letter"),
            401: OpenApiResponse(description="Authentication required"),
        },
    )
    def get(self, request):
        user_id = str(request.user.id)
        week_start = timezone.now() - timedelta(days=7)
        week_end = timezone.now()

        context = build_weekly_letter_context(user_id)
        if context is None:
            return Response(
                {"letter": None, "reason": "not_enough_entries"}, status=200
            )

        try:
            # If the nightly cron already warmed this user's cache tonight
            # with the same entries, this hits cache — no live Groq call.
            letter_content = generate_weekly_letter(
                context["formatted_entries"],
                context["entries_count"],
                context["dominant_emoji"],
                request.user.preferred_language,
                request.user.gender,
            )
        except Exception as e:
            letter_content = None
            logger.error("Error generating weekly letter: %s", e)

        return Response(
            {
                "letter": letter_content,
                "stats": {
                    "entry_count": context["entries_count"],
                    "dominant_emoji": context["dominant_emoji"],
                    "streak": calculate_streak(user_id),
                    "week_start": week_start.strftime("%Y-%m-%d"),
                    "week_end": week_end.strftime("%Y-%m-%d"),
                },
            },
            status=200,
        )
