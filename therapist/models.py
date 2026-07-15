from django.db import models


class MoodEntry(models.Model):
    user_id = models.CharField(max_length=128, db_index=True)
    emoji = models.CharField(max_length=10)
    thoughts = models.TextField()
    ai_response = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user_id} | {self.emoji} - {self.thoughts[:20]}"

    class Meta:
        verbose_name = "MoodEntry"
        verbose_name_plural = "MoodEntries"
        indexes = [
            models.Index(fields=["user_id", "-created_at"], name="therapist_userid_created_idx"),
        ]
