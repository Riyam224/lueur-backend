from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import (
    extend_schema,
    OpenApiExample,
    OpenApiResponse,
    OpenApiParameter,
)
from .ai_model import generate_ai_response
from .serializers import MoodEntrySerializer, MoodEntryCreateSerializer
from datetime import datetime, timedelta
from django.conf import settings


from drf_spectacular.utils import extend_schema, OpenApiResponse
from django.utils import timezone
from .models import MoodEntry
import requests as http_requests


class GenerateResponseAPIView(APIView):

    @extend_schema(
        tags=["Therapist"],
        summary="Generate AI response",
        description="""
Send an emoji and your thoughts to Luna (AI Therapist).
Luna will respond with an empathetic, supportive message.

The entry is automatically saved to your journal history.
        """,
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "example": "user_123",
                    },
                    "emoji": {"type": "string", "example": "😔"},
                    "thoughts": {
                        "type": "string",
                        "example": "I feel overwhelmed lately",
                    },
                },
                "required": ["user_id", "emoji", "thoughts"],
            }
        },
        responses={
            200: MoodEntrySerializer,
            400: OpenApiResponse(description="Missing user_id, emoji or thoughts"),
        },
        examples=[
            OpenApiExample(
                "Overwhelmed example",
                value={
                    "user_id": "user_123",
                    "emoji": "😔",
                    "thoughts": "I feel very overwhelmed with everything lately",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Happy example",
                value={
                    "user_id": "user_123",
                    "emoji": "😊",
                    "thoughts": "I feel happy and grateful today!",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Anxious example",
                value={
                    "user_id": "user_123",
                    "emoji": "😰",
                    "thoughts": "I am anxious about my future career",
                },
                request_only=True,
            ),
        ],
    )
    def post(self, request):
        input_serializer = MoodEntryCreateSerializer(data=request.data)
        if not input_serializer.is_valid():
            return Response(input_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user_id = input_serializer.validated_data["user_id"]
        emoji = input_serializer.validated_data["emoji"]
        thoughts = input_serializer.validated_data["thoughts"]

        try:
            ai_reply = generate_ai_response(emoji, thoughts)
        except Exception as e:
            print(f"GROQ AI error: {e}")
            ai_reply = "Could not generate a response at this time. Please try again later."

        entry = MoodEntry.objects.create(
            user_id=user_id,
            emoji=emoji,
            thoughts=thoughts,
            ai_response=ai_reply,
        )

        return Response(MoodEntrySerializer(entry).data, status=status.HTTP_200_OK)


class AllHistoryAPIView(APIView):

    @extend_schema(
        tags=["Therapist"],
        summary="Get mood history",
        description="""
Returns all saved mood journal entries for the given user, ordered by most recent first.

Each entry contains:
- **user_id** — the user ID the entry belongs to
- **emoji** — the mood emoji selected by the user
- **thoughts** — what the user shared
- **ai_response** — Luna's empathetic response
- **created_at** — timestamp of the entry
        """,
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="User ID to filter mood history entries.",
            ),
        ],
        responses={
            200: MoodEntrySerializer(many=True),
            400: OpenApiResponse(description="Missing user_id"),
        },
        examples=[
            OpenApiExample(
                "History response",
                value=[
                    {
                        "id": 1,
                        "user_id": "user_123",
                        "emoji": "😔",
                        "thoughts": "I feel overwhelmed",
                        "ai_response": "It sounds like you are carrying a lot right now...",
                        "created_at": "2026-03-27T12:00:00Z",
                    },
                    {
                        "id": 2,
                        "user_id": "user_123",
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
        user_id = request.query_params.get("user_id")
        if not user_id:
            return Response(
                {"error": "user_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        entries = MoodEntry.objects.filter(user_id=user_id).order_by("-created_at")
        return Response(MoodEntrySerializer(entries, many=True).data)


# class WeeklyLetterAPIView(APIView):

#     @extend_schema(
#         tags=["Therapist"],
#         summary="Get Luna's weekly letter",
#         description="Generates a personal weekly letter from Luna based on recent entries.",
#         responses={200: OpenApiResponse(description="Weekly letter")},
#     )
#     def post(self, request):
#         week_start = datetime.now() - timedelta(days=7)
#         week_end = datetime.now()

#         # get last 7 days entries
#         entries = MoodEntry.objects.filter(
#             created_at__gte=week_start,
#         ).order_by("created_at")

#         # need at least 2 entries
#         if entries.count() < 2:
#             return Response(
#                 {"letter": None, "reason": "not_enough_entries"},
#                 status=status.HTTP_200_OK,
#             )

#         # format for AI
#         formatted_entries = "\n".join(
#             [
#                 f"- {e.created_at.strftime('%A')}: "
#                 f"felt {e.emoji}, wrote: '{e.thoughts[:100]}'"
#                 for e in entries
#             ]
#         )

#         # dominant emoji this week
#         emoji_list = [e.emoji for e in entries]
#         dominant_emoji = max(set(emoji_list), key=emoji_list.count)

#         # call GROQ
#         import requests as http_requests

#         groq_api_key = getattr(settings, "GROQ_API_KEY", None)
#         headers = {
#             "Authorization": f"Bearer {groq_api_key}",
#             "Content-Type": "application/json",
#         }
#         payload = {
#             "model": "llama-3.1-8b-instant",
#             "messages": [
#                 {
#                     "role": "system",
#                     "content": (
#                         "You are Luna, a warm and empathetic AI journal "
#                         "companion in the MindEase app. Write a short "
#                         "personal weekly letter summarizing the emotional "
#                         "week. Your letter must:\n"
#                         '- Start with "Dear friend,"\n'
#                         "- Be 3-4 short paragraphs\n"
#                         "- Reference specific moods from the entries\n"
#                         "- Be warm, encouraging, never clinical\n"
#                         '- End with "— Luna 🌿"\n'
#                         "- Be under 200 words"
#                     ),
#                 },
#                 {
#                     "role": "user",
#                     "content": (
#                         f"Write a weekly letter based on these entries:\n\n"
#                         f"{formatted_entries}\n\n"
#                         f"Entry count: {entries.count()}\n"
#                         f"Dominant mood: {dominant_emoji}"
#                     ),
#                 },
#             ],
#         }
#         groq_response = http_requests.post(
#             "https://api.groq.com/openai/v1/chat/completions",
#             json=payload,
#             headers=headers,
#         )
#         response = groq_response.json()

#         return Response(
#             {
#                 "letter": response["choices"][0]["message"]["content"],
#                 "stats": {
#                     "entry_count": entries.count(),
#                     "dominant_emoji": dominant_emoji,
#                     "streak": entries.count(),
#                     "week_start": week_start.strftime("%Y-%m-%d"),
#                     "week_end": week_end.strftime("%Y-%m-%d"),
#                 },
#             },
#             status=status.HTTP_200_OK,
#         )


# from rest_framework.views import APIView
# from rest_framework.response import Response
# from drf_spectacular.utils import extend_schema, OpenApiResponse
# from datetime import datetime, timedelta
# from django.conf import settings
# from .models import MoodEntry
# import requests as http_requests


# class WeeklyLetterAPIView(APIView):

#     @extend_schema(
#         tags=["Therapist"],
#         summary="Get Luna's weekly letter",
#         description="Generates a personal weekly letter from Luna based on recent entries.",
#         responses={200: OpenApiResponse(description="Weekly letter")},
#     )
#     def get(self, request):
#         week_start = datetime.now() - timedelta(days=7)
#         week_end = datetime.now()

#         # get last 7 days entries
#         entries = MoodEntry.objects.filter(
#             created_at__gte=week_start,
#         ).order_by("created_at")

#         # need at least 2 entries
#         if entries.count() < 2:
#             return Response(
#                 {"letter": None, "reason": "not_enough_entries"},
#                 status=200,
#             )

#         # format for AI
#         formatted_entries = "\n".join(
#             [
#                 f"- {e.created_at.strftime('%A')}: "
#                 f"felt {e.emoji}, wrote: '{e.thoughts[:100]}'"
#                 for e in entries
#             ]
#         )

#         # dominant emoji this week
#         emoji_list = [e.emoji for e in entries]
#         dominant_emoji = max(set(emoji_list), key=emoji_list.count)

#         # call GROQ AI
#         groq_api_key = getattr(settings, "GROQ_API_KEY", None)
#         headers = {
#             "Authorization": f"Bearer {groq_api_key}",
#             "Content-Type": "application/json",
#         }
#         payload = {
#             "model": "llama-3.1-8b-instant",
#             "messages": [
#                 {
#                     "role": "system",
#                     "content": (
#                         "You are Luna, a warm and empathetic AI journal "
#                         "companion in the MindEase app. Write a short "
#                         "personal weekly letter summarizing the emotional "
#                         "week. Your letter must:\n"
#                         '- Start with "Dear friend,"\n'
#                         "- Be 3-4 short paragraphs\n"
#                         "- Reference specific moods from the entries\n"
#                         "- Be warm, encouraging, never clinical\n"
#                         '- End with "— Luna 🌿"\n'
#                         "- Be under 200 words"
#                     ),
#                 },
#                 {
#                     "role": "user",
#                     "content": (
#                         f"Write a weekly letter based on these entries:\n\n"
#                         f"{formatted_entries}\n\n"
#                         f"Entry count: {entries.count()}\n"
#                         f"Dominant mood: {dominant_emoji}"
#                     ),
#                 },
#             ],
#         }
#         groq_response = http_requests.post(
#             "https://api/groq.com/openai/v1/chat/completions",
#             json=payload,
#             headers=headers,
#         )
#         response = groq_response.json()

#         return Response(
#             {
#                 "letter": response["choices"][0]["message"]["content"],
#                 "stats": {
#                     "entry_count": entries.count(),
#                     "dominant_emoji": dominant_emoji,
#                     "streak": entries.count(),
#                     "week_start": week_start.strftime("%Y-%m-%d"),
#                     "week_end": week_end.strftime("%Y-%m-%d"),
#                 },
#             },
#             status=200,
#         )
class WeeklyLetterAPIView(APIView):
    @extend_schema(
        tags=["Therapist"],
        summary="Get Luna's weekly letter",
        description="Generates a personal weekly letter from Luna based on recent entries.",
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="User ID to filter weekly letter entries.",
            ),
        ],
        responses={
            200: OpenApiResponse(description="Weekly letter"),
            400: OpenApiResponse(description="Missing user_id"),
        },
    )
    def get(self, request):
        user_id = request.query_params.get("user_id")
        if not user_id:
            return Response({"error": "user_id is required"}, status=400)
        week_start = timezone.now() - timedelta(days=7)
        week_end = timezone.now()

        entries = MoodEntry.objects.filter(user_id=user_id, created_at__gte=week_start).order_by("created_at")
        entries_count = entries.count()

        if entries_count < 2:
            return Response({"letter": None, "reason": "not_enough_entries"}, status=200)

        formatted_entries = "\n".join(
            [f"- {e.created_at.strftime('%A')}: felt {e.emoji}, wrote: '{e.thoughts[:100]}'" for e in entries]
        )

        emoji_list = [e.emoji for e in entries]
        dominant_emoji = max(set(emoji_list), key=emoji_list.count)

        groq_api_key = getattr(settings, "GROQ_API_KEY", None)
        headers = {"Authorization": f"Bearer {groq_api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are Luna, a warm and empathetic AI journal companion. "
                        "Write a short personal weekly letter summarizing the emotional week. "
                        'Start with "Dear friend,"; 3-4 short paragraphs; reference moods; end with "— Luna 🌿"; <200 words.'
                    ),
                },
                {"role": "user", "content": f"Entries:\n{formatted_entries}\nCount: {entries_count}\nDominant: {dominant_emoji}"}
            ],
        }

        try:
            groq_response = http_requests.post(
                "https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers, timeout=10
            )
            response = groq_response.json()
            letter_content = response["choices"][0]["message"]["content"]
        except Exception as e:
            letter_content = None
            print(f"Error generating weekly letter: {e}")

        return Response(
            {
                "letter": letter_content,
                "stats": {
                    "entry_count": entries_count,
                    "dominant_emoji": dominant_emoji,
                    "streak": entries_count,
                    "week_start": week_start.strftime("%Y-%m-%d"),
                    "week_end": week_end.strftime("%Y-%m-%d"),
                },
            },
            status=200,
        )
