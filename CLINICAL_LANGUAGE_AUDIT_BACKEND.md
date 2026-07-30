# Clinical Language Audit — Lueur Backend

Pre-launch audit of everything Django serves or exposes (homepage, privacy
policy, drf-spectacular API docs, and all user-facing string constants in
`therapist/` and `accounts/`) for clinical/medical/diagnostic language that
could undermine the "friend, not clinic" positioning or trigger a
health/medical app classification during App Store / Play Store review.

**Result: no clinical/diagnostic/medical language found in anything
user-facing or reviewer-facing.** No auto-fixes were required. Two items
are flagged below for your sign-off — neither needs a wording change, they
just fall under "crisis content" and "privacy.html", which the task scope
requires routing to you rather than auto-editing.

## Files scanned

- `templates/index.html` (public homepage)
- `templates/privacy.html` (privacy policy)
- `core/settings.py` → `SPECTACULAR_SETTINGS["DESCRIPTION"]` (Swagger/ReDoc landing copy)
- `therapist/views.py` — all `@extend_schema` summaries/descriptions/examples
- `therapist/serializers.py`
- `accounts/views.py` — all `@extend_schema` summaries/descriptions
- `accounts/serializers.py`
- `accounts/services.py` (response envelope messages)
- `therapist/luna_prompts.py` (English + Arabic: system prompts, weekly-letter prompts, Groq-error fallbacks, `CRISIS_RESPONSE_AR`)
- `therapist/groq_budget_guard.py` (`BUDGET_EXCEEDED_MESSAGES` / `_AR`)
- `therapist/crisis.py` (read-only — frozen, not modified)
- `therapist/crisis_ar.py` (read-only — keyword list, not user-facing)
- Repo-wide grep for clinical terms (`therapist|therapy|treatment|diagnos|symptom|disorder|clinical|patient|prescri|medication|dosage|counselor|psycholog|psychiatr`) across all `.py`/`.html`, admin excluded

## Auto-fixed

None. No clinical, diagnostic, or licensed-practice-implying language was
found in any store/reviewer-visible surface or any client-returned string.
The app already consistently uses "companion," "wellness," and "journal"
framing rather than clinical terms — e.g. API tags are `["Companion"]` (not
`["Therapist"]`), and `SPECTACULAR_SETTINGS["DESCRIPTION"]` describes Lueur
as "a wellness companion app featuring an AI companion named Luna."

## Flagged for review

These aren't wording problems — they're the two categories the task scope
says must come to you rather than being auto-edited, surfaced here so you
can explicitly sign off.

1. **`templates/privacy.html`, lines 282–284 (`.notice` block, crisis-support wording):**
   > "Lueur is designed as a supportive wellness tool, not a substitute for
   > professional support. Journal entries may contain sensitive personal
   > information about your emotional state. We encourage you to be mindful
   > of what you share and to seek help from a qualified professional if you
   > are going through a crisis. Lueur is not equipped to respond to
   > emergencies. If you are in crisis, please contact your local emergency
   > services or a crisis hotline immediately."

   Read as written, this avoids "treatment," "therapy," "medical advice,"
   and "health data" framing — it says "wellness tool" and "supportive,"
   not a healthcare/medical data processor. No change suggested; flagging
   per your instruction that any crisis/emergency-support wording needs
   your manual sign-off rather than an automatic edit.

2. **`therapist/luna_prompts.py`, lines 98–104 (`CRISIS_RESPONSE_AR`):**
   The Arabic crisis-response template (parallel to the frozen English
   `CRISIS_RESPONSE` in `therapist/crisis.py`). Contains no clinical
   terminology in Arabic either — it says Luna "isn't able to help directly
   in crisis moments" and points to `findahelpline.com` / local emergency
   services. Per your instruction, `CRISIS_RESPONSE`/`CRISIS_RESPONSE_AR`
   wording is flag-only — not auto-edited. Flagging for your review of the
   help-line information/accuracy and wording, as instructed.

## Not flagged (internal-only, confirmed out of scope)

Every other hit for a clinical-sounding term is an internal code
identifier, comment, docstring, or test name — never returned to a client,
never rendered in Swagger/ReDoc, never seen by an app reviewer:

- The Django app name `therapist` itself (`INSTALLED_APPS`, `AppConfig.name`,
  `TherapistConfig`, import paths, DB index name `therapist_userid_created_idx`,
  Jazzmin admin icon config in `core/settings.py`) — internal routing/app
  identifier, admin-only, invisible to end users and reviewers.
- `therapist/tests.py` class/method names (`TherapistAuthIsolationTests`,
  `test_weekly_letter_prompt_gets_same_gender_prepend_treatment`, etc.) and
  `@patch("therapist.views....")` targets — test code, never shipped.
- `therapist/luna_prompts.py` lines 32–52 and 64–82 (`LUNA_SYSTEM_PROMPT_EN`/`_AR`):
  these are the *model instructions* sent to Groq, not text ever returned to
  a user. They explicitly tell the model "not counseling a client," "never
  therapy-speak," and forbid it from calling itself "a therapist, counselor,
  or medical professional" — i.e. this is the guardrail *preventing*
  clinical language from reaching users, not an instance of it leaking out.
  No change needed; flagging its presence only to confirm it was reviewed.
- `therapist/crisis_ar.py` docstring/comments referencing `therapist/crisis.py`
  by path, and `CRISIS_KEYWORDS_AR`/`CRISIS_KEYWORDS` themselves — these are
  detection-input keyword lists (e.g. "suicide," "self harm") used only to
  match incoming user text server-side; they are never rendered to a client
  or reviewer and aren't a "clinical language" concern in the sense this
  audit targets (framing Luna or the app as medical).
- `therapist/management/commands/check_crisis_ar_keywords.py` and
  `check_luna_prompts.py` — CI-only management commands, error messages
  only ever seen in server logs/CI output.
- `therapist/groq_budget_guard.py` module docstring/comments — internal
  engineering notes about Groq's free-tier limits, never shipped to a client
  (the actual user-facing strings, `BUDGET_EXCEEDED_MESSAGES`/`_AR`, were
  checked separately above and are clean — casual "distracted friend" lines
  with zero clinical or infrastructure-revealing language, by design).

## Tests

No strings were changed, so no test updates were required.

```
python manage.py test therapist accounts
...
Ran 112 tests in 13.500s

OK
```

All 112 existing tests pass unmodified.
