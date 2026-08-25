from django.contrib import admin

from .models import JournalEntry


def _truncate(text, length=50):
    text = text or ""
    return text if len(text) <= length else text[:length] + "…"


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ("user_id", "entry_type", "emoji", "thoughts_preview", "ai_response_preview", "crisis_flagged", "created_at")
    list_filter = ("entry_type", "crisis_flagged")
    date_hierarchy = "created_at"
    search_fields = ("user_id", "thoughts", "ai_response")
    readonly_fields = ("created_at",)

    @admin.display(description="Thoughts")
    def thoughts_preview(self, obj):
        return _truncate(obj.thoughts)

    @admin.display(description="AI response")
    def ai_response_preview(self, obj):
        return _truncate(obj.ai_response)
