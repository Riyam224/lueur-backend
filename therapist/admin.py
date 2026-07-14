from django.contrib import admin
from .models import MoodEntry


@admin.register(MoodEntry)
class MoodEntryAdmin(admin.ModelAdmin):
    list_display = ("user_id", "emoji", "thoughts", "ai_response", "created_at")
    search_fields = ("user_id", "thoughts", "ai_response")
