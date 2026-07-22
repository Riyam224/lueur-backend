# Tasks: Admin Dashboard

**Input**: Design documents from `/specs/003-admin-dashboard/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, quickstart.md

**Tests**: Included — the source request explicitly asked for a test on the delete-account admin action (item 7), and Constitution Principle IV requires test coverage for critical flows (the deletion action is irreversible).

**Organization**: Tasks are grouped by user story (see spec.md) to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

## Path Conventions

Existing Django monolith — no new app. Paths are `core/`, `therapist/`, `accounts/`, `templates/` at repository root, per plan.md's Project Structure.

---

## Phase 1: Setup (Shared Infrastructure)

**⚠️ AMENDMENT (post-implementation)**: `django-unfold==0.101.0` requires Python `>=3.12`, which is incompatible with `runtime.txt`'s pinned `python-3.11.9` (Railway deploy target) — this only surfaced after fixing an unrelated local-venv Python-version drift, not caught during `/speckit-plan` research. Decision: **drop `django-unfold` entirely**, keep `runtime.txt` at `3.11.9`, and use stock `django.contrib.admin` (unthemed) instead. T001–T004 below are superseded — `"unfold"` was removed from `INSTALLED_APPS`, the `UNFOLD` settings dict was removed, and `UserAdmin`/`MoodEntryAdmin` (T015/T019) now inherit from `django.contrib.admin.ModelAdmin`. Branding is preserved via `admin.site.site_header`/`site_title` in `core/urls.py` instead of Unfold's `SITE_HEADER`. Left checked below as a record of what was built and then reverted, not as current state.

**Purpose**: ~~Get `django-unfold` installed, configured, and rendering before any admin-content work begins.~~ Superseded — see amendment above.

- [X] ~~T001 Add `django-unfold` to `requirements.txt`~~ — reverted, removed from `requirements.txt`
- [X] ~~T002 Add `"unfold"` to `INSTALLED_APPS`~~ — reverted, removed from `core/settings.py`
- [X] ~~T003 Add a minimal `UNFOLD` settings dict~~ — reverted; "Lueur Admin" branding now set via `admin.site.site_header`/`site_title` in `core/urls.py`
- [X] ~~T004 Confirm the Unfold theme renders~~ — N/A; stock Django admin (unstyled/default grey) confirmed working instead

**Checkpoint**: Stock Django Admin renders locally, no third-party theme dependency. No `ModelAdmin` classes touched yet beyond the base-class revert.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Persist `crisis_flagged` on `MoodEntry` (approved decision — plan.md "Decisions Requiring Sign-Off" #1). Both US1 (filtering) and US3 (analytics counts) depend on this field existing and being populated, so it must land before either story's admin/analytics code is written.

**⚠️ CRITICAL**: No US1 or US3 task can begin until this phase is complete. US2 (deletion) has no dependency on this field and could theoretically proceed in parallel, but is sequenced after for simplicity since it shares `accounts/admin.py` file-editing with no other phase.

- [X] T005 Add `crisis_flagged = models.BooleanField(default=False, db_index=True)` to `MoodEntry` in `therapist/models.py`
- [X] T006 Run `python manage.py makemigrations therapist` to generate the schema migration in `therapist/migrations/`
- [X] T007 Write a data migration in `therapist/migrations/` (`RunPython`) that backfills `crisis_flagged` on all existing `MoodEntry` rows by re-running `contains_crisis_language()` (from `therapist/crisis.py`) over each row's stored `thoughts` — one-time reclassification of history, per research.md §2's backfill note
- [X] T008 In `therapist/views.py` `GenerateResponseAPIView.post()`, pass `crisis_flagged=True` on the crisis-branch `MoodEntry.objects.create(...)` call and `crisis_flagged=False` on the normal-branch call (the flag is already computed via `contains_crisis_language(thoughts)` in both branches — this only persists the existing value, no new classification logic)
- [X] T009 Remove the now-redundant manual `data["crisis_flagged"] = True` / `data["crisis_flagged"] = False` lines in `therapist/views.py` `GenerateResponseAPIView.post()`, since `crisis_flagged` is now a real model field and `MoodEntrySerializer(entry).data` will include it directly — avoids two sources of truth for the same response key
- [X] T010 Add `"crisis_flagged"` to `MoodEntrySerializer`'s `read_only_fields` in `therapist/serializers.py` (server-set only, never client-writable, consistent with `user_id`/`ai_response`/`created_at`/`id`)
- [X] T011 Run `python manage.py migrate` locally and `python manage.py test therapist` to confirm the migration applies cleanly and existing tests (which assert on `crisis_flagged` in the API response body) still pass with the field now backed by real data instead of a manually-set dict key

**Checkpoint**: `crisis_flagged` is a real, indexed, backfilled column; the API response shape is unchanged from the caller's perspective. US1 and US3 can now proceed.

---

## Phase 3: User Story 1 - Review and moderate journal content (Priority: P1) 🎯 MVP

**Goal**: Staff can browse/search/filter user accounts and journal entries in the themed admin without a separate tool (spec.md User Story 1).

**Independent Test**: Log in as staff, open the `MoodEntry` list (filter by date and `crisis_flagged`, confirm truncated text), open a single entry (confirm full text, non-editable `created_at`), open the `User` list (filter by status, newest-first ordering), open a single user (confirm entry count + link to their filtered entries).

### Tests for User Story 1

- [X] T012 [P] [US1] Test in `therapist/tests.py` asserting `MoodEntryAdmin.list_filter` includes `crisis_flagged`, `MoodEntryAdmin.date_hierarchy` is set to `created_at`, and `MoodEntryAdmin.readonly_fields` includes `created_at`
- [X] T013 [P] [US1] Test in `accounts/tests.py` asserting `UserAdmin.list_filter` includes `is_active`, `is_verified`, `is_staff`, and `UserAdmin.ordering` is `("-created_at",)`
- [X] T014 [P] [US1] Test in `accounts/tests.py` for the entry-count display method: create a user with 2 `MoodEntry` rows, call the `UserAdmin` display method directly, assert it returns "2" (or equivalent) and a link containing the user's id filter parameter

### Implementation for User Story 1

- [X] ~~T015 [US1] In `therapist/admin.py`, change `MoodEntryAdmin` to inherit from `unfold.admin.ModelAdmin`~~ — reverted per amendment above; stays on `django.contrib.admin.ModelAdmin`
- [X] T016 [US1] In `therapist/admin.py`, add `list_filter = ("crisis_flagged",)` and `date_hierarchy = "created_at"` to `MoodEntryAdmin`
- [X] T017 [US1] In `therapist/admin.py`, replace the raw `thoughts`/`ai_response` entries in `list_display` with short-description methods (e.g. `thoughts_preview`, `ai_response_preview`) that truncate to ~50 characters for the list view, while the full field remains visible on the detail/change view via `fields`/`readonly_fields` (no truncation there)
- [X] T018 [US1] In `therapist/admin.py`, add `readonly_fields = ("created_at",)` to `MoodEntryAdmin` (FR-004)
- [X] ~~T019 [US1] In `accounts/admin.py`, change `UserAdmin` to inherit from `unfold.admin.ModelAdmin`~~ — reverted per amendment above; stays on `django.contrib.admin.ModelAdmin`
- [X] T020 [US1] In `accounts/admin.py`, add `list_filter = ("is_active", "is_verified", "is_staff")` and `ordering = ("-created_at",)` to `UserAdmin`
- [X] T021 [US1] In `accounts/admin.py`, add a read-only display method (e.g. `mood_entry_count`) to `UserAdmin` that computes `MoodEntry.objects.filter(user_id=str(obj.id)).count()` and renders it as a link to the `MoodEntry` admin changelist pre-filtered to that `user_id`; add it to `list_display` and/or the detail view's `readonly_fields`

**Checkpoint**: User Story 1 is fully functional and independently testable — staff can browse and moderate content through the dashboard. This is the suggested MVP stopping point.

---

## Phase 4: User Story 2 - Process a manual account-deletion request (Priority: P2)

**Goal**: Staff can fulfill an email-based deletion request from the dashboard, using the existing `delete_user_account()` function, with a required confirmation step (spec.md User Story 2).

**Independent Test**: Select a test user in the dashboard, trigger "Delete account and journal entries," confirm on the intermediate page, verify the user row, Firebase identity call, and all their `MoodEntry` rows are gone; separately verify a forced Firebase failure leaves the local account and entries untouched with a clear error shown.

### Tests for User Story 2

- [X] T022 [P] [US2] Test in `accounts/tests.py`: mock `accounts.services.firebase_auth_admin.delete_user` to succeed, create a test user with `MoodEntry` rows, invoke the admin action via the Django admin test client `POST` with `action=delete_account_action` and `post=yes`, then assert directly against the database that the `User` row and all matching `MoodEntry` rows no longer exist — implemented as `UserAdminDeleteAccountActionTests.test_confirmed_action_deletes_user_and_mood_entries_for_real`
- [X] T023 [P] [US2] Test in `accounts/tests.py`: mock the Firebase delete call to raise, invoke the action, assert the `User` row and `MoodEntry` rows still exist (fail-closed, FR-009) and that the admin shows an error message rather than a success message — implemented as `UserAdminDeleteAccountActionTests.test_firebase_failure_keeps_user_and_mood_entries_and_shows_error`; `test_unconfirmed_action_shows_confirmation_and_deletes_nothing` additionally covers the no-`post`-param confirmation branch

### Implementation for User Story 2

- [X] T024 [US2] In `accounts/admin.py`, `delete_user_account` is imported from `accounts.services` and a `@admin.action(description="Delete account and journal entries")` method `delete_account_action` on `UserAdmin` calls `delete_user_account(user)` per selected user inside a `try`/`except`, using `self.message_user(request, ..., level=messages.ERROR)` on failure and a success message otherwise
- [X] T025 [US2] Confirmation step implemented in `accounts/admin.py`'s `delete_account_action` (checks `request.POST.get("post") != "yes"`; if unconfirmed, renders `TemplateResponse` using `templates/admin/accounts/user/delete_account_confirmation.html`, which lists the selected user(s) and warns the action is irreversible)
- [X] T026 [US2] `delete_account_action` registered on `UserAdmin.actions` in `accounts/admin.py`

**Checkpoint**: User Stories 1 AND 2 both work independently. Manual deletion requests no longer require the command line.

---

## Phase 5: User Story 3 - Check overall app health at a glance (Priority: P3)

**Goal**: A summary/overview screen shows the six aggregate figures from FR-010, computed live (spec.md User Story 3).

**Independent Test**: Log in, view the summary screen, confirm all six figures render; create a new `MoodEntry`, reload, confirm the relevant counts change immediately.

### Tests for User Story 3

- [X] T027 [P] [US3] Test in `core/tests.py` for the dashboard aggregate function: seed known users/entries (including some crisis-flagged, some outside the 7/30-day windows) and assert each of the six returned figures matches the expected count, including the average-streak calculation reusing `calculate_streak()`. Also covers the zero-data case (T030).

### Implementation for User Story 3

- [X] T028 [US3] Added `dashboard_summary()` in `core/admin_dashboard.py` computing the six FR-010 figures via plain ORM `Count`/`filter` queries and `therapist.views.calculate_streak()` (reused, not reimplemented, per research.md §3).
- [X] T029 [US3] Wired via a shadowed `templates/admin/index.html` (a full copy of Django's stock template, extending `admin/base_site.html` directly — cannot `{% extends "admin/index.html" %}` on a shadowed name) that calls `dashboard_summary()` through a `{% admin_dashboard_summary %}` template tag (`accounts/templatetags/dashboard_tags.py`, since `core` isn't an installed app and template tags must live under an app in `INSTALLED_APPS`) and renders an "Overview" module above the app list. No Unfold `DASHBOARD_CALLBACK` — this is the standard documented stock-admin index-override pattern.
- [X] T030 [US3] Zero-data case guarded (`average_streak = ... if streaks else 0`) and covered by `test_zero_data_renders_zeros_not_errors` in `core/tests.py`.

**Checkpoint**: All three user stories are independently functional. Full feature scope (minus deployment verification) is complete.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Security/deployment verification items (spec item 6 and 8) that span all three stories, plus final validation.

- [X] T031 [P] Verified: no `AdminSite` subclass or `has_permission` override anywhere in the project (grep clean) — default `is_staff` gating on `admin.site` is untouched.
- [X] T032 [P] Verified: `DEBUG = os.environ.get("DEBUG", "False") == "True"` — unchanged, defaults `False`.
- [X] T033 [P] Verified: `SECURE_SSL_REDIRECT`/`SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` all `True` inside `if not DEBUG and not TESTING:` — unchanged.
- [X] T034 [P] Verified: `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` still list the Railway production domain — unaffected (no Unfold, no new domain).
- [X] ~~T035 Run `python manage.py collectstatic --noinput` and confirm Unfold's static assets are present~~ — N/A, Unfold was dropped (Phase 1 amendment); ran `collectstatic --noinput` (154 files copied, no errors) confirming no regression.
- [X] T036 Added an "Admin Dashboard" section to `README.md` (between Deployment and Testing) documenting the `/admin/` URL, its stock-admin feature set, and `railway run python manage.py createsuperuser` for Railway superuser access.
- [X] T037 Ran `python manage.py test` (full suite): **53/53 passing**, including T012–T014, T022–T023, T027 (new: `core.tests.DashboardSummaryTests`, `accounts.tests.UserAdminDeleteAccountActionTests`).
- [X] T038 Walked through `quickstart.md` locally (sections 1–8, section 7 adjusted for no-Unfold): admin index renders with Overview summary; MoodEntry/User browsing verified via T012–T014 tests; deletion action verified via T022/T023-equivalent tests (confirm step + fail-closed); analytics summary verified via `core.tests.DashboardSummaryTests` and a live `/admin/` render check (200, "Overview"/"Active users"/"Average check-in streak" present); non-staff access to `/admin/` confirmed redirected to login (SC-005); `collectstatic` clean; full suite green. Section 4's live browser click-through and section 7's live-Railway check are the only pieces not directly observable from this environment (see T039).
- [ ] T039 Deploy to Railway (or ask the user to trigger/confirm the deploy) and load `https://<railway-domain>/admin/` in a browser to confirm it renders correctly (stock Django admin, not a themed page) and not a 500 — this cannot be verified from the local environment and is the final gate on spec item 8/SC-006; report the result back explicitly before considering this feature done

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup (Unfold must be installed/rendering first, though technically independent of the migration itself — sequenced after Setup for a clean checkpoint order). **Blocks US1 and US3.**
- **User Story 1 (Phase 3)**: Depends on Foundational (needs `crisis_flagged` for T016)
- **User Story 2 (Phase 4)**: Depends only on Setup (Phase 1) — does not touch `crisis_flagged` or `MoodEntryAdmin`. Sequenced after US1 here for a linear MVP path, but could be built in parallel by a second developer.
- **User Story 3 (Phase 5)**: Depends on Foundational (needs `crisis_flagged` for the crisis-count aggregates)
- **Polish (Phase 6)**: Depends on all three user stories being complete

### Parallel Opportunities

- T012, T013, T014 (US1 tests, different files/methods) can run in parallel
- T022, T023 (US2 tests) can run in parallel
- T031–T034 (Polish verification tasks, read-only checks in the same file but no code edits) can run in parallel
- US2 (Phase 4) has no hard dependency on Phase 2 and could be developed in parallel with Phase 2/3 by a second contributor, since it only touches `accounts/admin.py` and `accounts/services.py` (unchanged)

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational — `crisis_flagged` migration)
2. Complete Phase 3 (User Story 1)
3. **STOP and VALIDATE**: run `quickstart.md` sections 1–3, confirm browsing/filtering/moderation works
4. This alone delivers the dashboard's core value (spec.md SC-001) even before deletion or analytics ship

### Incremental Delivery

1. Setup + Foundational → Unfold renders, `crisis_flagged` is real and backfilled
2. + User Story 1 → staff can browse/moderate (MVP)
3. + User Story 2 → staff can process deletion requests without the CLI
4. + User Story 3 → staff get an at-a-glance health summary
5. + Polish → security/deployment verification, Railway superuser docs, live-deploy confirmation (spec item 8) — this phase is what makes the feature actually "done," not just locally working

## Notes

- No `contracts/` phase — this feature adds no new external API/interface contract (plan.md).
- The `crisis_flagged` migration (T005–T011) was explicitly approved by the requester during `/speckit-plan` before being included here (see plan.md "Decisions Requiring Sign-Off" #1).
- IP-restricting `/admin/` at the infrastructure level (spec item 6) is intentionally **not** a task in this file — it was explicitly deferred to a future decision, not part of this feature's implementation (plan.md #3).
- Commit after each task or logical group, per repository convention; run `python manage.py test <app>` for the touched app before moving to the next task within a phase.
