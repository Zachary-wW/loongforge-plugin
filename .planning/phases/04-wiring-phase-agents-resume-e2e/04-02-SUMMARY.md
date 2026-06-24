---
phase: 04-wiring-phase-agents-resume-e2e
plan: 02
subsystem: testing, docs
tags: [e2e, fake-gh-client, doc-consistency, backward-compat, loop-engineering-hooks, fix-pr]

# Dependency graph
requires:
  - phase: 03-loop-controller
    provides: FSM loop controller, FakeGhClient, validator_wrapper, diagnose_classifier
  - phase: 04-wiring-phase-agents-resume-e2e/01
    provides: resume reconciliation with SHA drift detection, view_pr/view_issue lifecycle methods
provides:
  - Loop Engineering Hooks documentation in all 6 phase agent.md files
  - E2E test proving full FSM cycle with FakeGhClient
  - COMPAT-01 backward compatibility tests
  - fix-PR creation in FIX_PR state with Fixes #N linkage
  - fix_pr_number field in LoopState for tracking fix-PR numbers
affects: [05-knowledge-base-graduation]

# Tech tracking
tech-stack:
  added: []
  patterns: [conditional-hooks-section, fix-pr-creation-in-fsm, staging-branch-base-ref]

key-files:
  created:
    - skills/adapt/tests/lib/test_loop_e2e.py
    - skills/adapt/tests/lib/test_compat.py
  modified:
    - skills/adapt/references/phases/phase0/agent.md
    - skills/adapt/references/phases/phase1/agent.md
    - skills/adapt/references/phases/phase2/agent.md
    - skills/adapt/references/phases/phase3/agent.md
    - skills/adapt/references/phases/phase4/agent.md
    - skills/adapt/references/phases/phase5/agent.md
    - skills/adapt/lib/loop_controller.py
    - skills/adapt/tests/lib/test_loop_controller.py

key-decisions:
  - "FIX_PR state creates fix-PR branch and opens PR with Fixes #N linkage (ISSUE-02) instead of just advancing attempt"
  - "MERGE_FIX merges fix-PR (fix_pr_number) not base PR (pr_number), ensuring correct artifact is merged before rerun"
  - "fix_pr_number added as separate LoopState field from pr_number to track two distinct PRs in the cycle"
  - "Test repos use staging base_ref instead of default branch to satisfy PR-01 (no direct push to default branch)"

patterns-established:
  - "Conditional Loop Engineering Hooks section in agent.md: gate text + Pre-Edit branch creation + Post-Edit PR submission, all conditional on repos: presence"
  - "Doc consistency testing: extract section, normalize phase numbers, assert identical across all 6 files"
  - "E2E test pattern: use FakeGhClient directly, only mock run_validator/check_validator_integrity/classify_failure"

requirements-completed: [DOC-03, TEST-01, COMPAT-01]

# Metrics
duration: 16min
completed: 2026-06-22
---

# Phase 04 Plan 02: Wiring Phase Agents + E2E Summary

**Loop Engineering Hooks added to all 6 agent.md files with conditional gating, plus full FSM E2E test and COMPAT-01 backward compatibility test**

## Performance

- **Duration:** 16 min
- **Started:** 2026-06-22T16:11:51Z
- **Completed:** 2026-06-22T16:27:40Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments
- All 6 phase agent.md files now carry identical "Loop Engineering Hooks" section (after phase number normalization) with Pre-Edit branch creation and Post-Edit PR submission bullets, gated on repos: presence in run_inputs.yml
- Full E2E test (test_loop_e2e.py) exercises the complete VALIDATE-fail -> DIAGNOSE -> ISSUE -> FIX_PR -> REVIEW -> MERGE_FIX -> RERUN-pass cycle against FakeGhClient, verifying VALIDATOR_PASSED_AFTER_FIX exit, PR-02 merge-before-rerun, ISSUE-02 Fixes #N linkage, and RESUME-03 idempotency key
- COMPAT-01 backward compatibility verified: legacy phase output without pr/issues/loop blocks passes validate_phase_output; run_phase_loop with repos_info=None produces no gh PR/issue calls
- FIX_PR state now creates an actual fix-PR (branch + open_pr with kind="fix" and fixes_issue parameter) instead of just advancing the attempt counter
- MERGE_FIX state merges the fix-PR (tracked via new fix_pr_number field) rather than the base PR

## Task Commits

Each task was committed atomically:

1. **Task 1: Add Loop Engineering Hooks to agent.md + COMPAT-01 test** - `4fa8abc` (feat)
2. **Task 2: E2E test + fix-PR implementation** - `0bb5b56` (feat)

_Note: Task 2 was TDD; the existing loop_controller.py FIX_PR state was a stub, so implementation was needed to make tests pass (Rule 2 deviation)._

## Files Created/Modified
- `skills/adapt/references/phases/phase0/agent.md` - Added Loop Engineering Hooks section
- `skills/adapt/references/phases/phase1/agent.md` - Added Loop Engineering Hooks section
- `skills/adapt/references/phases/phase2/agent.md` - Added Loop Engineering Hooks section
- `skills/adapt/references/phases/phase3/agent.md` - Added Loop Engineering Hooks section
- `skills/adapt/references/phases/phase4/agent.md` - Added Loop Engineering Hooks section
- `skills/adapt/references/phases/phase5/agent.md` - Added Loop Engineering Hooks section
- `skills/adapt/tests/lib/test_compat.py` - DOC-03 doc consistency + COMPAT-01 backward compat tests (new)
- `skills/adapt/tests/lib/test_loop_e2e.py` - E2E full FSM cycle tests (new)
- `skills/adapt/lib/loop_controller.py` - FIX_PR creates fix-PR, MERGE_FIX merges fix-PR, fix_pr_number field added
- `skills/adapt/tests/lib/test_loop_controller.py` - Updated _write_loop_state helper + test base_ref to staging

## Decisions Made
- FIX_PR state now creates a fix branch and fix-PR with Fixes #N linkage instead of just advancing the attempt counter -- this was critical missing functionality (Rule 2) needed for the E2E test to verify ISSUE-02 and PR-02
- MERGE_FIX state merges the fix-PR (tracked via fix_pr_number) rather than the base PR (pr_number) -- this ensures the correct artifact is validated before rerun
- fix_pr_number is a separate LoopState field from pr_number because the cycle involves two distinct PRs: the base PR (created in PR state, merged in MERGE_BASE) and the fix-PR (created in FIX_PR, merged in MERGE_FIX)
- Test repos use non-default base_ref ("staging/test-run" or "staging/run-e2e-test") to satisfy PR-01 (create_branch refuses default branch base)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Implemented fix-PR creation in FIX_PR state**
- **Found during:** Task 2 (E2E test - GREEN phase)
- **Issue:** FIX_PR state was a stub that only advanced the attempt counter; it did not create a fix-PR with Fixes #N linkage, making ISSUE-02 verification impossible
- **Fix:** Added branch creation, open_pr with kind="fix" and fixes_issue parameter, and fix_pr_number tracking in FIX_PR state; updated MERGE_FIX to merge the fix-PR instead of base PR
- **Files modified:** skills/adapt/lib/loop_controller.py
- **Verification:** test_loop_e2e.py TestE2EIssueFixesLinkage passes; full test suite 311 tests green
- **Committed in:** 0bb5b56 (Task 2 commit)

**2. [Rule 3 - Blocking] Updated existing tests for PR-01 compliance**
- **Found during:** Task 2 (regression testing after FIX_PR implementation)
- **Issue:** Existing tests used base_ref="main" which triggered DirectPushError from FakeGhClient when FIX_PR now creates branches
- **Fix:** Updated all repos_info in existing tests to use non-default staging base_ref
- **Files modified:** skills/adapt/tests/lib/test_loop_controller.py
- **Verification:** Full test suite 311 tests green
- **Committed in:** 0bb5b56 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 missing critical, 1 blocking)
**Impact on plan:** Both auto-fixes were necessary for correctness and testability. The FIX_PR implementation fills a documented but unimplemented FSM state. No scope creep.

## Issues Encountered
- FakeGhClient PR-01 check (DirectPushError for default-branch base) caused initial test failures after FIX_PR implementation started creating branches; resolved by using staging branch names in test repos_info

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 6 agent.md files carry conditional Loop Engineering Hooks documentation
- Full FSM cycle is E2E tested against FakeGhClient with 4 test cases covering core requirements
- Backward compatibility (COMPAT-01) verified for legacy invocations
- Ready for Phase 05 (Knowledge Base Graduation) or any further integration testing

---
*Phase: 04-wiring-phase-agents-resume-e2e*
*Completed: 2026-06-22*

## Self-Check: PASSED

All created files exist. All task commits found in git log.
