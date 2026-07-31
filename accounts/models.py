from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import UserManager


class GenderChoices(models.TextChoices):
    MALE = "male", "Male"
    FEMALE = "female", "Female"
    OTHER = "other", "Other"
    PREFER_NOT_TO_SAY = "prefer_not_to_say", "Prefer not to say"


class PreferredLanguage(models.TextChoices):
    ENGLISH = "en", "English"
    ARABIC = "ar", "العربية"


class User(AbstractUser):
    email = models.EmailField(unique=True)
    username = models.CharField(
        max_length=150, unique=True, blank=True, null=True
    )
    firebase_uid = models.CharField(
        max_length=128, unique=True, db_index=True, null=True, blank=True
    )
    full_name = models.CharField(max_length=150, blank=True)
    phone_number = models.CharField(max_length=32, blank=True)
    bio = models.TextField(max_length=500, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(
        max_length=20, choices=GenderChoices.choices, blank=True
    )
    preferred_language = models.CharField(
        max_length=2,
        choices=PreferredLanguage.choices,
        default=PreferredLanguage.ENGLISH,
    )
    is_verified = models.BooleanField(default=False)
    memory_summary = models.TextField(blank=True, default="")
    memory_updated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email
