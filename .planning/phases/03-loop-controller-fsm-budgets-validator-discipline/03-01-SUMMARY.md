---
phase: 03-loop-controller-fsm-budgets-validator-discipline
plan: 01
subsystem: validator-wrapper, diagnose-classifier
tags: [failure-signature, integrity-check, flake-rerun, sha-pinning, diagnose-classification, repair-template]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: "LoopBudget, LoopBlockOutput, GhClient protocol, FakeGhClient, append_attempt, validate_phase_completion.py inert hook"
  - phase: 02-github-helpers
    provides: "Full GhClient lifecycle (PR/issue/merge), FakeGhClient state machine, idempotency, dedup, templates"
provides:
  - "FailureSignature, ValidatorResult, run_validator, should_rerun_for_flake, check_validator_integrity, get_megatron_head_sha, make_attempt_row"
  - "DiagnoseClassification, DiagnoseResult, classify_failure, write_escalation"
  - "repair.md Jinja2 template with escape_hatch"
  - "VAL-04 integrity hook activated in _validate_loop_evidence"
affects: [03-02, fsm-controller]

# Tech tracking
tech-stack:
  added: []
  patterns: [maker-checker-separation, integrity-three-check, flake-rerun-threshold, escalation-file]

key-files:
  created:
    - skills/adapt/lib/validator_wrapper.py
    - skills/adapt/lib/diagnose_classifier.py
    - skills/adapt/loop_templates/phaseN/repair.md
    - skills/adapt/tests/lib/test_validator_wrapper.py
    - skills/adapt/tests/lib/test_diagnose_classifier.py
  modified:
    - skills/adapt/lib/gh_client.py
    - skills/adapt/scripts/validate_phase_completion.py
    - skills/adapt/tests/lib/test_validate_loop_evidence.py

key-decisions:
  - "FakeGhClient._run added to support get_megatron_head_sha; uses _sha_store dict for simulated SHA lookups"
  - "FailureSignature and ValidatorResult use @dataclass (not Pydantic) per RESEARCH recommendation: internal-only models avoid validation overhead"
  - "classify_failure counts consecutive same-kind+location entries from the tail of attempts_history (reversed iteration)"

patterns-established:
  - "Maker-checker separation: diagnose_classifier.py is read-only, never writes code or calls gh"
  - "Integrity three-check: binary hash + log mtime + log presence, all must pass for integrity_ok=True"
  - "Escalation file pattern: phases/phaseN/escalation.md with classification, rationale, attempts summary, escape hatch"

requirements-completed: [VAL-01, VAL-02, VAL-03, VAL-04, VAL-05, LOOP-04, LOOP-05]

# Metrics
duration: 7min
completed: 2026-06-22
---

# Phase 3 Plan 1: Validator Wrapper, Diagnose Classifier & Repair Template Summary

**Structured failure signatures, validator integrity gate, flake-rerun logic, read-only diagnose classification, and Jinja2 repair prompt template -- the checker side of maker-checker split**

## Performance

- **Duration:** 7 min
- **Started:** 2026-06-22T13:36:56Z
- **Completed:** 2026-06-22T13:44:53Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments
- Validator wrapper (validator_wrapper.py) with FailureSignature, ValidatorResult, run_validator, should_rerun_for_flake, check_validator_integrity, get_megatron_head_sha, make_attempt_row
- Diagnose classifier (diagnose_classifier.py) with DiagnoseClassification enum, classify_failure, write_escalation -- read-only by design (LOOP-04)
- Jinja2 repair prompt template (repair.md) with all variables and escape_hatch section (P4, P6)
- VAL-04 integrity hook activated in _validate_loop_evidence: rejects passed exits when integrity fails
- All 226 tests pass (56 new tests added)

## Task Commits

Each task was committed atomically (TDD: RED test then GREEN implementation):

1. **Task 1: Validator wrapper** - `e236268` (test) + `1d516d6` (feat)
2. **Task 2: Diagnose classifier + repair template** - `6ebb65e` (test) + `8b9cb58` (feat)
3. **Task 3: VAL-04 validator hook activation** - `7d5da5b` (test) + `ee77327` (feat)

## Files Created/Modified
- `skills/adapt/lib/validator_wrapper.py` - Validator invocation, integrity checks, flake-rerun, SHA pinning, attempt-row helper
- `skills/adapt/lib/diagnose_classifier.py` - Read-only failure classification (CODE_BUG/FLAKY/WRONG_DIRECTION/NEEDS_HUMAN)
- `skills/adapt/loop_templates/phaseN/repair.md` - Jinja2 repair prompt template with escape_hatch
- `skills/adapt/lib/gh_client.py` - Added FakeGhClient._run and _sha_store for SHA lookups
- `skills/adapt/scripts/validate_phase_completion.py` - VAL-04 integrity hook in _validate_loop_evidence
- `skills/adapt/tests/lib/test_validator_wrapper.py` - 31 tests for validator wrapper
- `skills/adapt/tests/lib/test_diagnose_classifier.py` - 19 tests for diagnose classifier
- `skills/adapt/tests/lib/test_validate_loop_evidence.py` - 6 new VAL-04 integrity tests + 1 existing test updated

## Decisions Made
- FakeGhClient._run added to support get_megatron_head_sha; uses _sha_store dict for simulated SHA lookups rather than adding a new protocol method
- FailureSignature and ValidatorResult use @dataclass (not Pydantic) per RESEARCH: internal-only models avoid validation overhead; persisted schemas remain Pydantic
- classify_failure counts consecutive same-kind+location entries from the tail of attempts_history (reversed iteration) to match the plan's "3+ consecutive" intent

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Existing test_loop_engineering_true_valid_loop_passes had exit_reason=validator_passed without validator_integrity key; updated to include integrity since VAL-04 now enforces it for passed exits (this is the correct behavior per the plan)

## User Setup Required
None - no external service configuration required.

## Self-Check: PASSED

All 5 created files verified present. All 6 commit hashes verified in git log.

## Next Phase Readiness
- Validator wrapper, diagnose classifier, and repair template ready for FSM controller (Plan 02) to consume
- All VAL-01..VAL-05, LOOP-04, LOOP-05 requirements satisfied
- No blockers for Plan 02

---
*Phase: 03-loop-controller-fsm-budgets-validator-discipline*
*Completed: 2026-06-22*
