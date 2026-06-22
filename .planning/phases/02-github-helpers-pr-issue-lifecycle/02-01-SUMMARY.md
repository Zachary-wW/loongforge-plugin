---
phase: 02-github-helpers-pr-issue-lifecycle
plan: 01
subsystem: github-helpers
tags: [sha256, idempotency, pr-template, issue-template, dedup-key, footer]

# Dependency graph
requires:
  - phase: 01-loop-foundation-contracts-schemas-safety-plumbing
    provides: "GhClient Protocol, schema.py (PrBlockOutput/IssuesBlockOutput), redact.py, protected_paths.py"
provides:
  - "idempotency.py: SHA256 key computation + footer format/parse + dedup key computation"
  - "templates.py: PR/issue/comment template rendering with dedup key embedding"
affects: [02-02-PLAN, 03-loop-controller]

# Tech tracking
tech-stack:
  added: []
  patterns: [idempotency-footer-html-comment, dedup-key-embedding, template-functions]

key-files:
  created:
    - skills/adapt/lib/idempotency.py
    - skills/adapt/lib/templates.py
    - skills/adapt/tests/lib/test_idempotency.py
    - skills/adapt/tests/lib/test_templates.py
  modified: []

key-decisions:
  - "Visible [adapt-skill-key: hex] fallback line before HTML comment addresses GitHub search indexing uncertainty for HTML comments (RESEARCH.md open question 1)"
  - "Idempotency key and dedup key use different input tuples: (run_id, phase, attempt, action_kind) vs (phase, validator, kind, location) -- they must never be conflated"

patterns-established:
  - "Idempotency footer: HTML comment + visible fallback line, parseable by parse_footer regex"
  - "Dedup key embedding: [dedup-key: hex] visible line in issue body, only when failure_signature has kind or location"
  - "Template functions: pure functions that accept primitive params and return strings, no side effects"

requirements-completed: [RESUME-03, PR-03, ISSUE-01, ISSUE-02, ISSUE-03]

# Metrics
duration: 12min
completed: 2026-06-22
---

# Phase 02 Plan 01: Idempotency & Template Foundation Summary

**SHA256 idempotency footer (HTML comment + visible fallback) and PR/issue/comment templates with dedup key embedding for cross-attempt issue dedup**

## Performance

- **Duration:** 12 min
- **Started:** 2026-06-22T10:40:54Z
- **Completed:** 2026-06-22T10:52:30Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Deterministic SHA256 idempotency key computation enabling crash-resume dedup (RESUME-03)
- HTML comment footer with visible machine-readable fallback for GitHub search compatibility
- Parse_footer regex extraction for idempotency footer with round-trip verification
- Dedup key computation (phase:validator:kind:location) distinct from idempotency key (ISSUE-03, D-02)
- PR title/body templates with Fixes #N linkage (PR-03, ISSUE-02)
- Issue body template with structured failure_signature table + dedup key embedding (ISSUE-01)
- Lifecycle comment templates: dedup_comment, agent_resume_comment, closing_summary
- REQUIRED_LABELS constant with "loongforge-adapt" base label

## Task Commits

Each task was committed atomically (TDD: RED then GREEN):

1. **Task 1 RED: Idempotency tests** - `9f98840` (test)
2. **Task 1 GREEN: Idempotency module** - `c66f0b9` (feat)
3. **Task 2 RED: Template tests** - `712682e` (test)
4. **Task 2 GREEN: Template module** - `e71d7d6` (feat)

## Files Created/Modified
- `skills/adapt/lib/idempotency.py` - SHA256 key computation, footer format/parse, dedup key computation
- `skills/adapt/lib/templates.py` - PR/issue/comment template rendering with label constants
- `skills/adapt/tests/lib/test_idempotency.py` - 19 unit tests for idempotency module
- `skills/adapt/tests/lib/test_templates.py` - 17 unit tests for template module

## Decisions Made
- Visible `[adapt-skill-key: hex]` fallback line placed immediately before the HTML comment, addressing the RESEARCH.md open question about GitHub search indexing of HTML comments. This ensures searchability even if HTML comments are not indexed.
- Idempotency key and dedup key deliberately use different input tuples and serve different purposes: idempotency key = (run_id, phase, attempt, action_kind) for crash-resume; dedup key = (phase, validator, kind, location) for issue dedup across attempts. The checker in Plan 02 flagged a blocker where these were mixed in open_issue, so the separation is explicit in both implementation and tests.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- idempotency.py and templates.py are ready for consumption by RealGhClient lifecycle methods in Plan 02
- FakeGhClient can import format_footer/compute_dedup_key for simulated state machine
- All 139 tests pass (103 existing + 36 new)

## Self-Check: PASSED

All 4 created files verified present. All 4 commit hashes verified in git log.

---
*Phase: 02-github-helpers-pr-issue-lifecycle*
*Completed: 2026-06-22*
