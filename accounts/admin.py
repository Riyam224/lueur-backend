import logging

from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html

from therapist.models import JournalEntry

from .models import User
from .services import delete_user_account

logger = logging.getLogger(__name__)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "username",
        "is_active",
        "is_verified",
        "is_staff",
        "preferred_language",
        "gender",
        "created_at",
        "journal_entry_count",
    )
    list_filter = ("is_active", "is_verified", "is_staff", "preferred_language", "gender")
    ordering = ("-created_at",)
    search_fields = ("email", "username")
    readonly_fields = ("journal_entry_count",)
    actions = ["delete_account_action"]

    @admin.display(description="Journal entries")
    def journal_entry_count(self, obj):
        count = JournalEntry.objects.filter(user_id=str(obj.id)).count()
        url = reverse("admin:therapist_journalentry_changelist")
        return format_html('<a href="{}?user_id={}">{}</a>', url, obj.id, count)

    @admin.action(description="Delete account and journal entries")
    def delete_account_action(self, request, queryset):
        if request.POST.get("post") != "yes":
            return TemplateResponse(
                request,
                "admin/accounts/user/delete_account_confirmation.html",
                {
                    **self.admin_site.each_context(request),
                    "title": "Are you sure?",
                    "queryset": queryset,
                    "opts": self.model._meta,
                    "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
                },
            )

        deleted, failed = [], []
        for user in queryset:
            try:
                delete_user_account(user)
                deleted.append(user)
            except Exception as exc:
                logger.error(
                    "Firebase delete_user failed for uid=%s: %s",
                    user.firebase_uid,
                    exc,
                )
                failed.append(user)

        if deleted:
            self.message_user(
                request,
                f"Deleted {len(deleted)} account(s) and their journal entries.",
                level=messages.SUCCESS,
            )
        if failed:
            self.message_user(
                request,
                "Failed to delete Firebase identity for: "
                + ", ".join(u.email for u in failed)
                + ". These accounts were not deleted.",
                level=messages.ERROR,
            )
