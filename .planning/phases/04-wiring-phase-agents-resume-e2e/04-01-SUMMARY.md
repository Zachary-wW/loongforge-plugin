---
phase: 04-wiring-phase-agents-resume-e2e
plan: 01
subsystem: resume-reconciliation
tags: [resume, reconciliation, sha-drift, force-push, idempotency, gh-cli, pydantic]

# Dependency graph
requires:
  - phase: 03-loop-controller-fsm-budgets-validator
    provides: LoopState, FSMState, ExitReason, GhClient Protocol, FakeGhClient, RealGhClient
  - phase: 02-gh-client-pr-issue-lifecycle
    provides: view_pr/view_issue capability foundation, idempotency keys, dedup keys
provides:
  - reconcile_remote_state for single-phase remote state verification
  - reconcile_run for multi-phase aggregated verification
  - ReconciliationMismatch exception with --from-phase hint
  - MismatchDetail dataclass for structured mismatch reporting
  - SHA drift and force-push detection via merge_commit_sha comparison
  - resume idempotency via dedup key and idempotency key lookup
  - run.py --resume reconciliation wiring with SystemExit(3) on mismatch
affects: [resume-path, crash-safety, validator-gate-enforcement]

# Tech tracking
tech-stack:
  added: []
  patterns: [reconcile-then-proceed, sha-drift-detection, dedup-key-idempotency-on-resume]

key-files:
  created:
    - skills/adapt/lib/resume.py
    - skills/adapt/tests/lib/test_resume.py
    - .planning/phases/04-wiring-phase-agents-resume-e2e/deferred-items.md
  modified:
    - skills/adapt/lib/gh_client.py
    - skills/adapt/lib/loop_controller.py
    - skills/adapt/scripts/run.py
    - skills/adapt/tests/lib/test_gh_client_lifecycle.py
    - skills/adapt/tests/lib/test_loop_controller.py

key-decisions:
  - "Force-push detection subsumed by SHA drift check; dedicated force_push mismatch type reserved for v1 when commit-author timestamps are available"
  - "reconcile_remote_state only checks loongforge_repo (both PRs and issues opened there); megatron_repo not reconciled since no PRs/issues are opened against it"
  - "Reconciliation skipped when --from-phase specified (explicit reset takes precedence over stale state detection)"

patterns-established:
  - "Reconcile-then-proceed: on --resume, first verify remote state matches local records, then allow controller to re-enter"
  - "SHA drift detection: compare merge_commit_sha recorded at MERGE_BASE time with current view_pr result; mismatch = stale state"

requirements-completed: [RESUME-01, RESUME-02, TEST-04]

# Metrics
duration: 9min
completed: 2026-06-22
---

# Phase 04 Plan 01: Resume Reconciliation + View Methods Summary

**Remote-state reconciliation wired into --resume path with SHA drift/force-push detection; view_pr/view_issue added to GhClient; LoopState extended with merge_commit_sha/head_sha for crash-safe resume**

## Performance

- **Duration:** 9 min
- **Started:** 2026-06-22T16:11:43Z
- **Completed:** 2026-06-22T16:21:22Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Added view_pr and view_issue to GhClient Protocol, RealGhClient, and FakeGhClient with full state reflection
- Extended LoopState with merge_commit_sha and head_sha fields for SHA drift/force-push detection (RESUME-02)
- Created reconcile_remote_state and reconcile_run functions that detect 6 mismatch types: PR 404, PR closed-without-merge, merge SHA drift, force-push (via SHA drift), issue 404, issue closed-unexpectedly
- Wired reconciliation into run.py --resume path; exits SystemExit(3) with --from-phase hint on mismatch; skips reconciliation when --from-phase is specified
- TEST-04 proven: kill mid-DIAGNOSE or mid-ISSUE, resume produces zero duplicate issues (dedup key finds existing artifact)
- MERGE_BASE handler now records merge_commit_sha via view_pr for SHA drift detection on resume

## Task Commits

Each task was committed atomically:

1. **Task 1: Add view_pr/view_issue to GhClient + extend LoopState with merge_commit_sha and head_sha + tests** - `e0534e9` (feat)
2. **Task 2: Create lib/resume.py with reconciliation + wire into run.py + TEST-04 resume idempotency test** - `8794e06` (feat)

## Files Created/Modified
- `skills/adapt/lib/resume.py` - New: reconcile_remote_state, reconcile_run, ReconciliationMismatch, MismatchDetail
- `skills/adapt/lib/gh_client.py` - Added view_pr/view_issue to Protocol, RealGhClient, FakeGhClient; FakePrRecord.merge_commit_sha field
- `skills/adapt/lib/loop_controller.py` - Added merge_commit_sha and head_sha to LoopState; persist/from_disk/merge_base handler updated
- `skills/adapt/scripts/run.py` - Wired reconciliation into --resume path; SystemExit(3) on mismatch
- `skills/adapt/tests/lib/test_resume.py` - New: 19 tests (10 reconcile_remote_state, 4 reconcile_run, 2 TEST-04 idempotency, 1 ReconciliationMismatch, 2 run.py integration)
- `skills/adapt/tests/lib/test_gh_client_lifecycle.py` - Added TestViewMethods class with 8 tests
- `skills/adapt/tests/lib/test_loop_controller.py` - Added TestLoopStateShaFields with 2 tests; updated _write_loop_state helper

## Decisions Made
- Force-push detection is subsumed by SHA drift check in v1; a dedicated `force_push` mismatch type is reserved for when commit-author timestamps can distinguish re-merge from force-push-re-merge
- reconcile_remote_state only checks loongforge_repo since both PRs and issues are opened there; megatron_repo is not reconciled (no PRs/issues opened against it)
- Reconciliation is skipped when --from-phase is specified, treating it as an explicit reset that takes precedence over stale state detection

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Pre-existing E2E test failures in test_loop_e2e.py (TestE2EBasePrMergeBeforeValidator, TestE2EIssueFixesLinkage) existed before this plan's changes; documented in deferred-items.md
- Parallel 04-02 agent modified FIX_PR handler in loop_controller.py, causing DirectPushError regression in test_issue_opens_gh_issue_and_tracks; out of scope for this plan, documented in deferred-items.md

## Known Stubs
None - all data paths are wired to real implementations or FakeGhClient mock state.

## Next Phase Readiness
- Resume reconciliation is complete; --resume path detects stale remote state and errors clearly
- view_pr/view_issue methods are available for any future code needing PR/issue state inspection
- LoopState merge_commit_sha/head_sha fields enable SHA drift detection across all future resume scenarios
- Ready for Plan 02 (wiring phase agents for real execution with resume capability)

## Self-Check: PASSED

- All 5 key files verified as existing on disk
- Both task commits (e0534e9, 8794e06) verified in git log
- 29 new tests pass (8 view methods + 2 SHA round-trip + 19 resume)
- No regressions in existing tests (excluding pre-existing failures from parallel agent)

---
*Phase: 04-wiring-phase-agents-resume-e2e*
*Completed: 2026-06-22*
