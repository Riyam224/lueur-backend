# Luna Voice — Arabic Coverage Checklist

Every place backend code generates or sends Luna-voiced text to a user.
Items marked **✅ shipped** now have final MSA copy in place and are wired
through `therapist/luna_prompts.py`. `check_luna_prompts` (management
command + `TherapistConfig.ready()` production boot check) passes — no
`PLACEHOLDER` text remains in the system prompt or weekly-letter prompt.

Arabic content is also **gender-aware**, two different ways:
- **Model-steering** (system prompt, weekly-letter prompt): `LunaPromptProvider`
  prepends one of `GENDER_INSTRUCTIONS_AR` (male/female/neutral) ahead of the
  prompt, so the LLM conjugates its own generated reply correctly.
- **Literal template substitution** (crisis response): `apply_gender_variant()`
  replaces `{male_form/female_form}` markers in fixed, final user-facing text.
  Never mix the two — model-instruction prompts use the prepend, literal
  templates use the substitution, not both.

Gender comes from `accounts.User.gender` (reused from the existing profile
field — `other`/`prefer_not_to_say`/blank/unspecified all resolve to the
male form/neutral instruction, per Modern Standard Arabic's masculine-as-
default-for-unspecified-audience convention). This only applies to `ar`;
English never gets a gender instruction or substitution.

| # | File : Function | What it is | Status |
|---|---|---|---|
| 1 | `therapist/luna_prompts.py` : `LUNA_SYSTEM_PROMPT_EN` / `_AR` (via `LunaPromptProvider.get_system_prompt`) | The main chat system prompt — defines Luna's personality/voice for every `POST /api/companion/generate/` reply. | ✅ shipped — final MSA copy, gender instruction prepended |
| 2 | `therapist/luna_prompts.py` : `WEEKLY_LETTER_PROMPT_EN` / `_AR` (via `LunaPromptProvider.get_weekly_letter_prompt`) | System prompt for the weekly letter ("Dear friend," ... "— Luna 🌿"), used by `generate_weekly_letter()` / `GET /api/companion/weekly-letter/`. | ✅ shipped — final MSA copy, gender instruction prepended. Cache key includes language+gender so a cached English letter can never be served to an Arabic-preferring user. |
| 3 | `therapist/luna_prompts.py` : `GROQ_ERROR_FALLBACK_EN` / `_AR` (via `LunaPromptProvider.get_groq_error_fallback`) | Shown when Groq errors but the request still needs to save an entry. | ✅ shipped — final MSA copy. No gender variant (see judgment call below). |
| 4 | `therapist/groq_budget_guard.py` : `BUDGET_EXCEEDED_MESSAGES` / `_AR` (via `get_fallback_message(preferred_language)`) | 6 rotating "distracted friend" lines shown when the Groq budget guard throttles a request. | ✅ shipped — final MSA copy. No gender variant (deliberately gender-neutral/polite phrasing, per your instruction). |
| 5 | `therapist/luna_prompts.py` : `CRISIS_RESPONSE` / `CRISIS_RESPONSE_AR` (via `LunaPromptProvider.get_crisis_response`) | Safety response shown when crisis language is detected in a journal entry (findahelpline.com; MSA copy generalizes the English version's "US: 988" to "look for a local crisis line in your area", since 988 is US-only). | ✅ shipped — final MSA copy, `apply_gender_variant()` applied. Lives in `luna_prompts.py`, NOT in `therapist/crisis.py` (which stays frozen) — wired from `views.py`, selected by `request.user.preferred_language`/`gender`, not by which detector (`crisis.py` vs `crisis_ar.py`) fired. |

### Judgment call carried over from the previous pass: items 3–4 have no gender variant

Confirmed, not overridden: both are short, in-character lines that don't use a
gendered second-person verb in either language's final copy, so there's
nothing for `apply_gender_variant()` to substitute. If future copy changes
introduce a gendered verb here, add `{male/female}` markers and route through
`apply_gender_variant()` the same way `CRISIS_RESPONSE_AR` does.

## Known, deliberately separate gap: `therapist/crisis_ar.py` keyword list

`crisis_ar.py`'s `CRISIS_KEYWORDS_AR` (the Arabic **crisis-language
detection** list, not the response) is still
`TEST_ARABIC_CRISIS_PHRASE_PLACEHOLDER_1/2` — `check_crisis_ar_keywords`
correctly still fails. This is intentionally out of scope for this pass
(response text vs. detection keywords are separate concerns/separate product
review); do not confuse the two when reading `manage.py check` output.

## Explicitly out of scope for this checklist

- `templates/index.html`, `templates/privacy.html` — describe Luna in
  marketing/legal copy but are not text *spoken as* Luna to an end user;
  these are static Django templates, not part of the Flutter app's runtime
  UI, and would be handled (if ever) as separate i18n work, not through
  `LunaPromptProvider`.
- `therapist/throttles.py` — `LunaChatRateThrottle` is a rate-limit class
  name, not user-facing text.
- `therapist/ai_model.py`'s own `contains_crisis_language(thoughts)` check
  inside `generate_ai_response()` (line ~49) still returns the raw English
  `CRISIS_RESPONSE` directly, unlocalized. In practice this is dead code for
  the one caller that matters — `views.py` already runs its own (bilingual)
  crisis check and returns before ever calling `generate_ai_response()` — but
  it's a redundant safety net for any other future caller. Not touched in
  this pass since it wasn't in scope; worth localizing if another call site
  is ever added.
