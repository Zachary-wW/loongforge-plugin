---
phase: 02-github-helpers-pr-issue-lifecycle
plan: 02
subsystem: github-helpers
tags: [gh-cli, pr-lifecycle, issue-dedup, idempotency, policy-guards, state-machine]

# Dependency graph
requires:
  - phase: 02-github-helpers-pr-issue-lifecycle
    provides: "Plan 01 idempotency + templates (compute_idempotency_key, format_footer, parse_footer, compute_dedup_key, pr_title, pr_body, issue_title, issue_body, dedup_comment, agent_resume_comment, closing_summary, REQUIRED_LABELS)"
  - phase: 01-loop-foundation-contracts-schemas-safety-plumbing
    provides: "GhClient Protocol, GhResult, FakeGhClient, RealGhClient preflight, redact(), is_protected()"
provides:
  - "RealGhClient lifecycle methods: create_branch, open_pr, merge_pr, open_issue, close_issue"
  - "RealGhClient find methods: find_by_idempotency_key, find_by_dedup_key"
  - "FakeGhClient in-memory state machine with FakePrRecord + FakeIssueRecord"
  - "Policy exceptions: ProtectedPathError, HumanCommitError, DirectPushError"
  - "31 lifecycle tests via FakeGhClient injection"
affects: [03-loop-controller, testing]

# Tech tracking
tech-stack:
  added: []
  patterns: ["policy-guard-before-side-effect", "template-driven-pr-issue-creation", "dedup-via-dedup-key-not-idempotency-key", "find-by-idempotency-key-for-crash-resume", "in-memory-state-machine-for-testing"]

key-files:
  created:
    - skills/adapt/tests/lib/test_gh_client_lifecycle.py
  modified:
    - skills/adapt/lib/gh_client.py

key-decisions:
  - "Protocol signatures changed: open_pr/open_issue no longer accept title/body/labels; templates enforce format (PR-03/ISSUE-01)"
  - "find_by_dedup_key is separate from find_by_idempotency_key: dedup key = SHA256(phase:validator:kind:location) for cross-attempt dedup; idempotency key = SHA256(run_id:phase:attempt:action_kind) for crash-resume"
  - "Human commit detection uses git log --format=%ae per D-01 (not %an, which is unreliable for GitHub login matching)"
  - "open_pr posts /agent-resume comment on existing PR when human commits detected (D-01 best-effort)"
  - "open_issue uses find_by_dedup_key for dedup, NOT find_by_idempotency_key -- the hashes serve different purposes and would never match"

patterns-established:
  - "Policy-guard-before-side-effect: open_pr checks protected paths and human commits BEFORE calling gh pr create"
  - "Template-driven creation: PR/issue title/body/labels computed from run_id/phase/attempt/validator params, not passed by caller"
  - "FakeGhClient state machine: _pr_store/_issue_store dicts keyed by (owner_repo, number) for find/merge/close operations"
  - "Two find methods with distinct purposes: idempotency key for crash-resume, dedup key for issue dedup across attempts"

requirements-completed: [PR-01, PR-02, PR-03, PR-04, PR-05, PR-06, ISSUE-01, ISSUE-02, ISSUE-03, ISSUE-04, RESUME-03]

# Metrics
duration: 7min
completed: 2026-06-22
---

# Phase 02 Plan 02: PR/Issue Lifecycle Summary

**RealGhClient lifecycle methods with policy guards + FakeGhClient in-memory state machine + dedup-by-dedup-key + 31 lifecycle tests**

## Performance

- **Duration:** 7 min
- **Started:** 2026-06-22T10:49:54Z
- **Completed:** 2026-06-22T10:56:45Z
- **Tasks:** 3 (1a+1b combined implementation + 2 test suite)
- **Files modified:** 2

## Accomplishments
- All 6 RealGhClient lifecycle methods implemented with policy guards (protected-path scan, human-commit detection, direct-push refusal, redaction, label bootstrapping)
- FakeGhClient evolved from call-recorder to full in-memory state machine with FakePrRecord + FakeIssueRecord stores
- Issue dedup via find_by_dedup_key (cross-attempt) kept separate from find_by_idempotency_key (crash-resume)
- HumanCommitError posts /agent-resume comment on existing PR before raising (D-01)
- 31 comprehensive lifecycle tests pass, all 170 total tests green

## Task Commits

Each task was committed atomically:

1. **Task 1a+1b: RealGhClient lifecycle + FakeGhClient state machine + policy exceptions** - `1e87a1c` (feat)
2. **Task 2: Comprehensive lifecycle test suite via FakeGhClient** - `c3f8fb4` (test)

## Files Created/Modified
- `skills/adapt/lib/gh_client.py` - Full lifecycle methods, policy exceptions, FakePrRecord/FakeIssueRecord, find methods
- `skills/adapt/tests/lib/test_gh_client_lifecycle.py` - 31 tests covering PR lifecycle, issue lifecycle, policy guards, dedup, end-to-end fix loop

## Decisions Made
- Protocol signatures for open_pr/open_issue changed to template-driven params (run_id/phase/attempt/validator) instead of raw title/body/labels -- callers cannot bypass template constraints
- find_by_dedup_key and find_by_idempotency_key are separate methods with different search scopes (open issues only vs all PR/issues) and different hash inputs
- Task 1a and 1b combined into single implementation commit since they modify the same file and are logically inseparable

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- GhClient adapter is complete: preflight + lifecycle + policy guards + find methods
- FakeGhClient state machine is ready for Phase 3 loop controller integration tests
- 11 requirements (PR-01 through PR-06, ISSUE-01 through ISSUE-04, RESUME-03) fully implemented and tested

## Self-Check: PASSED

- skills/adapt/lib/gh_client.py: FOUND
- skills/adapt/tests/lib/test_gh_client_lifecycle.py: FOUND
- 02-02-SUMMARY.md: FOUND
- Commit 1e87a1c: FOUND
- Commit c3f8fb4: FOUND

---
*Phase: 02-github-helpers-pr-issue-lifecycle*
*Completed: 2026-06-22*
