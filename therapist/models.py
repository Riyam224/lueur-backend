from django.db import models


class EntryType(models.TextChoices):
    MOOD_CHAT = "mood_chat", "Mood chat"
    BREATHING = "breathing", "Breathing exercise"
    SUDOKU = "sudoku", "Sudoku"
    DRAWING = "drawing", "Free drawing"
    LETTER_READ = "letter_read", "Weekly letter read"


class JournalEntry(models.Model):
    user_id = models.CharField(max_length=128, db_index=True)
    entry_type = models.CharField(
        max_length=20, choices=EntryType.choices, default=EntryType.MOOD_CHAT, db_index=True
    )
    emoji = models.CharField(max_length=10, blank=True, default="")
    thoughts = models.TextField(blank=True, default="")
    ai_response = models.TextField(blank=True, default="")
    # Per-type extra data — shape depends on entry_type:
    #   breathing:   {"duration_seconds": int}
    #   sudoku:      {"solved": bool, "duration_seconds": int, "difficulty": str}
    #   drawing:     {"thumbnail_url": str}
    #   letter_read: {}
    #   mood_chat:   unused, stays {}
    payload = models.JSONField(default=dict, blank=True)
    crisis_flagged = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user_id} | {self.entry_type} - {self.emoji} {self.thoughts[:20]}".strip()

    class Meta:
        verbose_name = "JournalEntry"
        verbose_name_plural = "JournalEntries"
        indexes = [
            models.Index(fields=["user_id", "-created_at"], name="therapist_userid_created_idx"),
        ]
