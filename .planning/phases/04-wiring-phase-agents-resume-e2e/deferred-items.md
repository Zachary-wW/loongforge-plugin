# Deferred Items

## Pre-existing test failures (out of scope for 04-01)

**File:** `skills/adapt/tests/lib/test_loop_e2e.py`
**Tests:** `TestE2EBasePrMergeBeforeValidator::test_e2e_base_pr_merge_before_validator`, `TestE2EIssueFixesLinkage::test_e2e_issue_has_fixes_linkage`
**Issue:** These E2E tests start from `validate` state but expect the controller to go through PR/MERGE_BASE states. When starting from `validate`, the loop goes `validate -> diagnose -> issue -> fix_pr -> review -> merge_fix -> rerun` and never creates a base PR. The tests were likely written expecting the full cycle starting from `probe`, but the state is set to `validate`.
**Action:** Do NOT fix -- out of scope for this plan. These are pre-existing failures that existed before the 04-01 changes.

**File:** `skills/adapt/tests/lib/test_loop_controller.py`
**Test:** `TestRunPhaseLoopValidateState::test_issue_opens_gh_issue_and_tracks`
**Issue:** The parallel 04-02 agent modified the FIX_PR handler to call `gh.create_branch(owner_repo, fix_branch, base=base_ref)` with `base_ref="main"`, which triggers `DirectPushError` because `main` is the default branch for `Zachary-wW/LoongForge`. This is a regression introduced by the parallel agent's changes to loop_controller.py, not by the 04-01 changes.
**Action:** Do NOT fix -- out of scope for 04-01. The parallel agent should fix this in 04-02.
