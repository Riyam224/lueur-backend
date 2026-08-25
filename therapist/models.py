from django.db import models


class JournalEntry(models.Model):
    user_id = models.CharField(max_length=128, db_index=True)
    emoji = models.CharField(max_length=10)
    thoughts = models.TextField()
    ai_response = models.TextField()
    crisis_flagged = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user_id} | {self.emoji} - {self.thoughts[:20]}"

    class Meta:
        verbose_name = "JournalEntry"
        verbose_name_plural = "JournalEntries"
        indexes = [
            models.Index(fields=["user_id", "-created_at"], name="therapist_userid_created_idx"),
        ]
