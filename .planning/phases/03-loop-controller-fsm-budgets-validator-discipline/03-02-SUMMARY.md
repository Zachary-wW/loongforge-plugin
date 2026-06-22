---
phase: 03-loop-controller-fsm-budgets-validator-discipline
plan: 02
subsystem: loop-controller
tags: [fsm, loop-engineering, budget-enforcement, re-entrant, maker-checker, validator-integrity, attempts-jsonl]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: "LoopBudget, LoopBlockOutput, PrBlockOutput, IssuesBlockOutput, GhClient protocol, FakeGhClient, append_attempt, validate_phase_completion.py VAL-04 hook"
  - phase: 02-github-helpers
    provides: "Full GhClient lifecycle (PR/issue/merge), FakeGhClient state machine, idempotency, dedup, templates"
  - phase: 03-01
    provides: "FailureSignature, ValidatorResult, run_validator, should_rerun_for_flake, check_validator_integrity, get_megatron_head_sha, make_attempt_row, DiagnoseClassification, classify_failure, write_escalation, repair.md template"
provides:
  - "FSMState enum (12 members), ExitReason enum (6 members)"
  - "LoopState dataclass with from_disk/persist for re-entrant disk state"
  - "check_budget: three-axis enforcement (per-phase, per-run, wallclock)"
  - "_advance_attempt, _transition, _read_attempts_history helper functions"
  - "_compute_validator_hash: SHA-256 hash of validator binary"
  - "_write_phase_output: writes phaseN_output.yml with validator_integrity/loop/pr/issues blocks on ALL terminal exits"
  - "run_phase_loop: re-entrant FSM controller implementing full LOOP-01 cycle"
  - "_reconstruct_validator_result: builds ValidatorResult from last_validator_summary dict"
affects: [fsm-integration, run-wiring]

# Tech tracking
tech-stack:
  added: []
  patterns: [re-entrant-fsm, budget-first-check, flake-rerun-same-attempt, exit-safety-net, disk-state-persistence]

key-files:
  created:
    - skills/adapt/lib/loop_controller.py
    - skills/adapt/tests/lib/test_loop_controller.py
  modified: []

key-decisions:
  - "Recursive match/case architecture chosen for FSM dispatch -- each state returns run_phase_loop recursively with max_iterations-1, providing natural termination"
  - "_write_phase_output called on ALL terminal exits (VALIDATOR_PASSED, VALIDATOR_PASSED_AFTER_FIX, EXHAUSTED, HUMAN_NEEDED) including budget exhaustion at entry, ensuring validate_phase_completion VAL-04 hook always has data"
  - "EXIT state includes safety-net _write_phase_output for resume-after-crash scenarios where the file might not have been written"
  - "Flake reruns (VALIDATE state for Phase 3/4) use same attempt number and kind='validate_rerun', do not consume budget (Pitfall 6)"
  - "Budget check at entry uses current attempt/total; budget check after VALIDATE/RERUN uses attempt+1/total+1 to preempt next iteration"

patterns-established:
  - "Budget-first pattern: check_budget called before processing validator results in every state (Pitfall 2)"
  - "Exit-safety-net pattern: EXIT state checks if phaseN_output.yml has validator_integrity block; if not, writes one"
  - "Disk-persistence pattern: LoopState.from_disk reads loop_state.yml + attempts.jsonl tail; every state transition calls persist() before recursing"

requirements-completed: [LOOP-01, LOOP-02, LOOP-03, LOG-01]

# Metrics
duration: 10min
completed: 2026-06-22
---

# Phase 3 Plan 2: FSM Loop Controller Summary

**Re-entrant FSM loop controller with 12-state dispatch, three-axis budget enforcement, _write_phase_output on all terminal exits, and full-cycle CODE_BUG diagnosis-to-fix-to-pass flow against FakeGhClient**

## Performance

- **Duration:** 10 min
- **Started:** 2026-06-22T13:48:22Z
- **Completed:** 2026-06-22T13:58:22Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Complete FSM controller (loop_controller.py) implementing Probe->Edit->PR->Merge(base)->Validate->(Diagnose->Issue->Fix-PR->Review->Merge->Rerun)* cycle
- LoopState dataclass with from_disk/persist for P1 re-entrant disk-based state (reads loop_state.yml + attempts.jsonl tail)
- check_budget: three-axis enforcement (per-phase, per-run, wallclock) with budget-before-validator discipline (Pitfall 2)
- _write_phase_output writes phaseN_output.yml with validator_integrity, loop, pr, issues blocks on ALL terminal exits (BLOCKER fix for VAL-04)
- _compute_validator_hash records SHA-256 of validator binary at loop start for VAL-04 integrity checking
- VALIDATE and RERUN states pass megatron_repo/megatron_ref to run_validator (VAL-05) and store loong_megatron_sha
- DIAGNOSE reconstructs ValidatorResult from last_validator_summary (no in-memory coupling across re-entries)
- Full cycle test: VALIDATE(fail)->DIAGNOSE(CODE_BUG)->ISSUE->FIX_PR->REVIEW->MERGE_FIX->RERUN(pass) produces VALIDATOR_PASSED_AFTER_FIX
- Safety iteration limit (max_iterations=100) prevents infinite recursion
- No /loop invocation in controller code (SAFE-02)
- 44 controller tests (all passing); 270 total tests (no regressions)

## Task Commits

Each task was committed atomically (TDD: RED test then GREEN implementation):

1. **Task 1: FSM enums, LoopState, budget, helpers, VALIDATE/DIAGNOSE/ISSUE states** - `d442895` (test) + `8c73e95` (feat)
2. **Task 2: FIX_PR/REVIEW/MERGE_FIX/RERUN/EXIT states + full-cycle tests** - `fb81186` (feat + test)

## Files Created/Modified
- `skills/adapt/lib/loop_controller.py` - FSM controller with 12-state dispatch, LoopState, budget enforcement, phase output writer
- `skills/adapt/tests/lib/test_loop_controller.py` - 44 tests covering all FSM states, budget checks, helpers, re-entrancy, and full-cycle integration

## Decisions Made
- Recursive match/case architecture chosen for FSM dispatch -- each state returns run_phase_loop recursively with max_iterations-1, providing natural termination
- _write_phase_output called on ALL terminal exits including budget exhaustion at entry, ensuring validate_phase_completion VAL-04 hook always has data
- EXIT state includes safety-net _write_phase_output for resume-after-crash scenarios
- Flake reruns use same attempt number and kind='validate_rerun', do not consume budget (Pitfall 6)
- Budget check after VALIDATE/RERUN uses attempt+1/total+1 to preempt next iteration

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] _write_phase_output not called on budget exhaustion paths**
- **Found during:** Task 2 (test_exhausted_exit_writes_phase_output)
- **Issue:** Budget exhaustion at entry, in VALIDATE, and in RERUN states returned without writing phaseN_output.yml, leaving VAL-04 hook without data
- **Fix:** Added _write_phase_output(run_dir, phase, state, None, budget) call on all budget-breach paths before return
- **Files modified:** skills/adapt/lib/loop_controller.py
- **Verification:** test_exhausted_exit_writes_phase_output passes, output file exists with loop.exit_reason="exhausted"

**2. [Rule 1 - Bug] EXIT state safety-net check had unsafe YAML parse in conditional**
- **Found during:** Task 2 (EXIT handler review)
- **Issue:** Original code had `yaml.safe_load(output_path.read_text()) or {} if output_path.exists() else {}` in an inline conditional which was fragile
- **Fix:** Refactored to proper try/except block with explicit needs_write flag
- **Files modified:** skills/adapt/lib/loop_controller.py

---

**Total deviations:** 2 auto-fixed (1 missing critical, 1 bug)
**Impact on plan:** Both auto-fixes essential for correctness and VAL-04 compatibility. No scope creep.

## Issues Encountered
- Test `test_diagnose_reconstructs_from_last_validator_summary` initially hit real subprocess in RERUN state -- fixed by patching run_validator for states that follow DIAGNOSE
- Test `test_issue_opens_gh_issue_and_tracks` same issue -- patched run_validator for full-cycle paths
- Test `test_re_entrant_from_disk` initially used max_iterations=2 which set exit_reason=EXHAUSTED, preventing second run -- fixed by manually setting intermediate state at EDIT

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- FSM controller complete and ready for integration with run.py and SKILL.md wiring
- All LOOP-01, LOOP-02, LOOP-03, LOG-01 requirements satisfied
- _write_phase_output ensures VAL-04 hook compatibility on all exit paths
- Validator result persisted via last_validator_summary for DIAGNOSE state reconstruction
- No blockers for Phase 4 (wiring/integration)

## Self-Check: PASSED

All 2 created files verified present. All 3 commit hashes (d442895, 8c73e95, fb81186) verified in git log.

---
*Phase: 03-loop-controller-fsm-budgets-validator-discipline*
*Completed: 2026-06-22*
