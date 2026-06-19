# Pre-Implementation Checklist: Accounts & Authentication Module

**Purpose**: Validate requirements quality across the full spec (completeness, clarity, consistency, edge cases, non-functional coverage) before running `/speckit-tasks` — standard-depth self-review by the spec author.
**Created**: 2026-06-19
**Feature**: [spec.md](../spec.md)

## Requirement Completeness

- [ ] CHK001 Are requirements defined for the exact data payload returned immediately after registration (FR-005) vs. after login, so an implementer doesn't have to guess what "user data" includes? [Completeness, Spec §FR-005]
- [ ] CHK002 Are maximum length/size limits defined for free-text profile fields (`bio`, `full_name`)? [Gap]
- [ ] CHK003 Are requirements defined for what happens to a user's outstanding password-reset or email-verification tokens when their account is deleted? [Gap, Spec §FR-010]
- [ ] CHK004 Are requirements defined for whether other active credential sessions (other devices) are invalidated when a password is changed (FR-009), or only future sign-ins are affected? [Gap, Spec §FR-009]
- [ ] CHK005 Is the exact field set of the "user data" object referenced in User Story 1 acceptance scenario 3 enumerated anywhere, or left to the Key Entities section by inference only? [Completeness, Spec §US1, §Key Entities]

## Requirement Clarity

- [x] CHK006 Is "minimum password strength policy" (FR-003) quantified with specific criteria (length, character classes, etc.), or left for the planning phase to define? [Clarity, Spec §FR-003] — Resolved: 8 chars minimum, ≥1 uppercase, ≥1 lowercase, ≥1 number.
- [x] CHK007 Are the relative lifetimes of the "short-lived access credential" and "longer-lived refresh credential" (FR-006) quantified, or intentionally deferred? [Clarity, Spec §FR-006] — Resolved: access=15min, refresh=7 days.
- [x] CHK008 Is the "allowed size limit" for profile photo uploads (FR-013) quantified with a specific value? [Clarity, Spec §FR-013] — Resolved: 5 MB max.
- [x] CHK009 Is the rate-limiting "rolling window" (FR-026) quantified with a specific duration and attempt threshold, or left abstract? [Clarity, Spec §FR-026] — Resolved: per-endpoint thresholds now in FR-026 (5/5min register+login, 3/15min forgot-password, 5/15min verify-reset-token, 3/hour send-verification-email).
- [x] CHK010 Is "accepted image type" (FR-013) enumerated explicitly in the spec, or only implied? [Clarity, Spec §FR-013] — Resolved: JPG/JPEG/PNG/WEBP enumerated.

## Requirement Consistency

- [ ] CHK011 Are the active/inactive status requirements in FR-022 worded consistently with the Key Entities description of the Account's "active status" attribute? [Consistency, Spec §FR-022, §Key Entities]
- [ ] CHK012 Are the no-account-existence-disclosure requirements in FR-016 and the corresponding Edge Cases bullet consistent in scope (do both cover email verification requests as well as password reset)? [Consistency, Spec §FR-016, §Edge Cases]
- [ ] CHK013 Are username-related requirements (FR-025, Assumptions) consistent on whether username uniqueness has any interaction with email uniqueness? [Consistency, Spec §FR-025, §Assumptions]
- [ ] CHK014 Are the Profile Details and Account entity descriptions in Key Entities consistent with the field-level edit restrictions stated in FR-012? [Consistency, Spec §FR-012, §Key Entities]

## Acceptance Criteria Quality

- [ ] CHK015 Can SC-001 ("under 30 seconds of active interaction") be objectively measured given no definition of what counts as "active interaction" vs. network/think time? [Measurability, Spec §SC-001]
- [ ] CHK016 Can SC-005 ("95% of attempts... return a specific, actionable error") be objectively verified without a definition of what qualifies an error message as "actionable"? [Measurability, Spec §SC-005]
- [ ] CHK017 Is SC-007's "no successful brute-force or spam attempt observed in testing" falsifiable, or does it require a bounded test procedure (e.g., N attempts in M minutes) to be meaningful? [Measurability, Spec §SC-007]
- [ ] CHK018 Does every acceptance scenario in User Stories 1–4 map to at least one Functional Requirement, with no scenario left without a corresponding FR? [Traceability, Spec §US1-4, §Requirements]

## Scenario Coverage

- [ ] CHK019 Are requirements defined for a user attempting to register a new account while already authenticated with an existing session? [Coverage, Gap]
- [ ] CHK020 Are requirements defined for the case where two password-reset tokens are outstanding for the same account at once (does issuing a new one invalidate the prior one)? [Coverage, Gap, Spec §FR-016]
- [ ] CHK021 Are requirements defined for a profile update (FR-012) submitted with one valid field and one invalid field in the same request — partial success or full rejection? [Coverage, Gap, Spec §US2]
- [ ] CHK022 Are requirements defined for the failure/exception path of account deletion itself (e.g., what the client sees if deletion cannot complete)? [Coverage, Exception Flow, Gap]

## Edge Case Coverage

- [ ] CHK023 Does the spec define behavior when an authenticated user requests email verification (FR-019) for an account whose email was already changed by some other means before this spec's scope (vs. their original registration email)? [Edge Case, Gap, Spec §US4]
- [ ] CHK024 Does the spec define what happens when a second profile-image upload (FR-013) is submitted before a prior upload for the same account has finished processing? [Edge Case, Gap]
- [ ] CHK025 Does the spec define behavior when a deleted account's refresh token is presented to the token-refresh action (FR-007), distinct from the explicit logout-invalidation edge case already covered? [Edge Case, Spec §FR-007, §FR-010, §SC-006]

## Non-Functional Requirements

- [ ] CHK026 Are observability/audit-logging requirements defined for security-sensitive events (failed logins, password changes, account deletion), or is this intentionally out of scope? [Gap, Non-Functional]
- [ ] CHK027 Are data-retention requirements defined for expired-but-unused password-reset/email-verification tokens (must they be purged, or may they persist indefinitely)? [Gap, Non-Functional]
- [ ] CHK028 Are requirements defined for the race condition where two requests attempt to consume the same single-use reset or verification token at nearly the same time? [Gap, Non-Functional]

## Dependencies & Assumptions

- [ ] CHK029 Is the assumption that email verification is non-blocking (Assumptions) cross-checked against every functional requirement to confirm none of them implicitly requires verified status as a precondition? [Assumption, Spec §Assumptions]
- [ ] CHK030 Is the dependency on a future email-delivery mechanism (currently out of scope per Assumptions) documented with enough of the token contract (format, expiry, single-use) that a later implementer can plug in delivery without re-deriving this spec's decisions? [Dependency, Spec §Assumptions]

## Ambiguities & Conflicts

- [x] CHK031 Is "permanently delete" (FR-010) unambiguous about whether related records owned by other apps (e.g., the existing `therapist` app's `MoodEntry` rows keyed by `user_id`) are in scope for deletion, or explicitly out of scope? [Ambiguity, Spec §FR-010] — Resolved: explicitly out of scope. Verified against `therapist/views.py`/`models.py` that `MoodEntry.user_id` is unauthenticated, free-text client input with no existing link to any account, so no cascade is implemented (see FR-010 note + Assumptions + research.md §8).
- [ ] CHK032 Is there a documented resolution for whether username uniqueness (FR-025) is case-sensitive, to avoid an implementation-time judgment call? [Ambiguity, Spec §FR-025]

## Notes

- Focus: full spec coverage (all nine requirement-quality dimensions), not limited to security/auth alone.
- Depth: standard (~30 items).
- Audience/timing: spec author, self-review before `/speckit-tasks`.
- Items marked unchecked indicate a requirements-writing gap to resolve (via spec edit or an explicit, documented decision to leave as a planning-time/implementation-time choice) before tasks are generated.
