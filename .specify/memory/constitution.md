<!--
Sync Impact Report
- Version change: [TEMPLATE] → 1.0.0 (initial ratification)
- Modified principles: n/a (first concrete version, replacing placeholder template)
- Added sections:
  - Core Principles: Data Isolation & Privacy, Input & Contract Validation,
    Resilient External AI Integration, Test Coverage for Critical Flows, Simplicity & Statelessness
  - Security & Deployment Requirements
  - Development Workflow
  - Governance
- Removed sections: none (template placeholders replaced)
- Templates requiring updates:
  - ✅ .specify/templates/plan-template.md (generic "[Gates determined based on constitution file]" — no project-specific names to change, gate check reads this file directly)
  - ✅ .specify/templates/spec-template.md (no constitution references found)
  - ✅ .specify/templates/tasks-template.md (no constitution references found)
  - ✅ .specify/templates/checklist-template.md (no constitution references found)
- Follow-up TODOs: none
-->

# AI Therapist Backend Constitution

## Core Principles

### I. Data Isolation & Privacy (NON-NEGOTIABLE)

Every `MoodEntry` query MUST be scoped by `user_id`; no endpoint may return or
aggregate data across users. `user_id` MUST be validated against the strict
regex (`^[A-Za-z0-9_-]{3,128}$`) on every serializer that accepts it. New
endpoints that read or write mood/conversation data MUST filter by `user_id`
before any other condition is applied.
**Rationale**: This is a mental health application handling sensitive
personal disclosures. A single cross-user data leak is a trust-ending and
potentially harmful incident, not a recoverable bug.

### II. Input & Contract Validation

All request input MUST be validated through a DRF serializer before touching
business logic or the database — no raw `request.data` access in views.
Read and write concerns MUST use distinct serializers
(`MoodEntrySerializer` for output, `MoodEntryCreateSerializer` for input) so
that read-only fields (`id`, `ai_response`, `created_at`) can never be
client-supplied. API surface changes MUST stay reflected in drf-spectacular
schema output (`/api/docs/`, `/api/redoc/`).
**Rationale**: Class-based views plus serializer validation is the existing
convention; mixing concerns invites unvalidated input reaching the AI
service or the database.

### III. Resilient External AI Integration

`generate_ai_response()` and any other external AI call MUST be treated as
fallible: it may raise on network failure, timeout, or API error.
View-layer callers MUST catch these exceptions, persist a safe fallback
response, and still return HTTP 200 to the client — a third-party AI outage
MUST NOT surface as a 5xx to the end user. `ai_model.py` itself MUST remain a
stateless, synchronous wrapper around the Groq API and MUST NOT swallow
exceptions itself; handling happens at the call site, where context
(fallback copy, persistence) is known.
**Rationale**: Users in a vulnerable emotional state hitting a generic
500 error is a worse outcome than receiving a gentle fallback message while
the entry is still saved for later context.

### IV. Test Coverage for Critical Flows

Every new or modified endpoint MUST have a corresponding test in
`therapist/tests.py` covering at least the success path and the primary
failure mode (missing required field, missing `user_id`, or AI-call
failure). Tests MUST mock `generate_ai_response()` (or any other external
API call) — no test may perform a real network call to Groq or any other
third-party service. `python manage.py test therapist` MUST pass before a
change is considered complete.
**Rationale**: Network-dependent tests are slow, flaky, and burn real API
quota; mocking is the only way to keep the suite fast and deterministic.

### V. Simplicity & Statelessness

The AI service layer MUST remain a stateless wrapper over a remote API —
no local model loading, no in-process ML inference, no caching layer unless
a specific, demonstrated performance problem requires one. Features MUST be
implemented with the smallest change that satisfies the requirement; new
abstractions (base classes, generic helpers, config layers) require a
concrete second use case before being introduced.
**Rationale**: The project's stated value (`CLAUDE.md`) is a lightweight,
fast-cold-start backend with no GPU/local-model dependency — added
complexity directly undermines that property.

## Security & Deployment Requirements

- Secrets (`GROQ_API_KEY`, `SECRET_KEY`) MUST be supplied via environment
  variables; no secret may be hardcoded or committed, including in tests or
  fixtures.
- `DEBUG` MUST default to `False` and only be enabled via environment
  variable in non-production environments.
- Any new deployed domain MUST be added to both `ALLOWED_HOSTS` and
  `CSRF_TRUSTED_ORIGINS` in `core/settings.py`.
- New endpoints that accept user-supplied identifiers MUST validate them
  with an explicit regex or serializer field constraint — free-text fields
  used as lookup keys are not acceptable.
- Static files MUST continue to be served via WhiteNoise in production; no
  endpoint may bypass `collectstatic` asset handling.

## Development Workflow

- Model changes MUST be followed by `makemigrations` and `migrate` in the
  same change set — migrations MUST be committed alongside the model edit
  that produced them.
- Existing Arabic-language comments MUST be preserved when editing
  surrounding code; new comments may be written in English or Arabic to
  match the surrounding context, not replace it.
- AI service changes (prompt text, generation parameters, model name) MUST
  be documented in `CLAUDE.md` if they change observable behavior (response
  length, tone rules, `[SESSION_END]` triggering conditions).
- Before marking work complete, run `python manage.py test therapist` and
  confirm the relevant endpoint manually (or via a mocked test) against the
  documented request/response flow in `CLAUDE.md`.

## Governance

This constitution supersedes ad-hoc conventions when the two conflict. Any
change to a Core Principle (I–V) is an amendment and MUST update the version
number, the Sync Impact Report at the top of this file, and the "Last
Amended" date below. Pull requests and reviews MUST verify compliance with
the principles above; a deviation MUST be called out explicitly in the
change description with a justification, not silently introduced. Added
complexity (new dependency, new abstraction layer, new persistent service)
MUST be justified against Principle V before being accepted.

Versioning policy: MAJOR for removal/redefinition of a Core Principle,
MINOR for a new principle or materially expanded section, PATCH for
wording/clarification fixes with no rule change.

**Version**: 1.0.0 | **Ratified**: 2026-06-19 | **Last Amended**: 2026-06-19
