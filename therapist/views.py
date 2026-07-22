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
from .ai_model import generate_ai_response, generate_weekly_letter
from .crisis import contains_crisis_language, CRISIS_RESPONSE
from .serializers import MoodEntrySerializer, MoodEntryCreateSerializer
from datetime import timedelta
from django.utils import timezone
from .models import MoodEntry
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
            200: MoodEntrySerializer,
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
        input_serializer = MoodEntryCreateSerializer(data=request.data)
        if not input_serializer.is_valid():
            return Response(input_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        emoji = input_serializer.validated_data["emoji"]
        thoughts = input_serializer.validated_data["thoughts"]
        history = input_serializer.validated_data.get("history", [])[-10:]

        if contains_crisis_language(thoughts):
            entry = MoodEntry.objects.create(
                user_id=str(request.user.id),
                emoji=emoji,
                thoughts=thoughts,
                ai_response=CRISIS_RESPONSE,
                crisis_flagged=True,
            )
            data = MoodEntrySerializer(entry).data
            return Response(data, status=status.HTTP_200_OK)

        try:
            ai_reply = generate_ai_response(emoji, thoughts, history)
        except Exception as e:
            logger.error("Groq AI error: %s", e)
            ai_reply = "Luna is taking a little break right now. Please try again in a moment 🌿"

        entry = MoodEntry.objects.create(
            user_id=str(request.user.id),
            emoji=emoji,
            thoughts=thoughts,
            ai_response=ai_reply,
            crisis_flagged=False,
        )
        data = MoodEntrySerializer(entry).data
        return Response(data, status=status.HTTP_200_OK)


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
            200: MoodEntrySerializer(many=True),
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
        entries = MoodEntry.objects.filter(
            user_id=str(request.user.id)
        ).order_by("-created_at")
        return Response(MoodEntrySerializer(entries, many=True).data)


def calculate_streak(user_id, now=None):
    now = now or timezone.now()
    today = timezone.localtime(now).date()

    dates = sorted(
        {
            timezone.localtime(dt).date()
            for dt in MoodEntry.objects.filter(user_id=str(user_id)).values_list(
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

        entries = MoodEntry.objects.filter(
            user_id=user_id, created_at__gte=week_start
        ).order_by("created_at")
        entries_count = entries.count()

        if entries_count < 2:
            return Response(
                {"letter": None, "reason": "not_enough_entries"}, status=200
            )

        formatted_entries = "\n".join(
            [
                f"- {e.created_at.strftime('%A')}: felt {e.emoji}, wrote: "
                f"'{e.thoughts[:100] if not contains_crisis_language(e.thoughts) else '(a difficult moment)'}'"
                for e in entries
            ]
        )

        emoji_list = [e.emoji for e in entries]
        dominant_emoji = max(set(emoji_list), key=emoji_list.count)

        try:
            letter_content = generate_weekly_letter(formatted_entries, entries_count, dominant_emoji)
        except Exception as e:
            letter_content = None
            logger.error("Error generating weekly letter: %s", e)

        return Response(
            {
                "letter": letter_content,
                "stats": {
                    "entry_count": entries_count,
                    "dominant_emoji": dominant_emoji,
                    "streak": calculate_streak(user_id),
                    "week_start": week_start.strftime("%Y-%m-%d"),
                    "week_end": week_end.strftime("%Y-%m-%d"),
                },
            },
            status=200,
        )
