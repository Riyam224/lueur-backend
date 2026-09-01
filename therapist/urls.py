from django.urls import path
from .views import (
    GenerateResponseAPIView,
    AllHistoryAPIView,
    WeeklyLetterAPIView,
    ActivityEntryAPIView,
    DeleteJournalEntryAPIView,
    DeleteAllJournalEntriesAPIView,
)

urlpatterns = [
    path("generate/", GenerateResponseAPIView.as_view()),
    path("history/", AllHistoryAPIView.as_view()),
    path("weekly-letter/", WeeklyLetterAPIView.as_view()),
    path("activity/", ActivityEntryAPIView.as_view()),
    path("entries/delete-all/", DeleteAllJournalEntriesAPIView.as_view()),
    path("entries/<int:entry_id>/delete/", DeleteJournalEntryAPIView.as_view()),
]
