---
phase: 10-integrate-nsys-profiler-and-performance-tuner-as-new-phase-4-renumber-feature-compat-to-phase-5-and-kb-update-to-phase-6
plan: 03
subsystem: testing
tags: [pytest, 7-phase, renumbering, validator-wrapper, flake-rerun]

# Dependency graph
requires:
  - phase: 10-integrate-nsys-profiler-and-performance-tuner-as-new-phase-4-renumber-feature-compat-to-phase-5-and-kb-update-to-phase-6
    plan: 02
    provides: "7-phase code structure (performance-tuning at Phase 4, feature-compat at Phase 5, kb-consistency at Phase 6)"
provides:
  - "All test files updated to match 7-phase structure"
  - "FLAKE_RERUN_PHASES={3,5} test assertion"
  - "PHASE_VALIDATORS with performance-tuning at 4, feature-compat at 5, kb-consistency at 6"
affects: [testing, validator-wrapper, plugin-layout, compat]

# Tech tracking
tech-stack:
  added: []
  patterns: [gate-file-name-normalization-in-doc-consistency-tests]

key-files:
  created: []
  modified:
    - skills/adapt/tests/test_runner.py
    - skills/adapt/tests/test_plugin_layout.py
    - skills/adapt/tests/lib/test_compat.py
    - skills/adapt/tests/lib/test_housekeeping_check.py
    - skills/adapt/tests/lib/test_summary_generator.py
    - skills/adapt/tests/lib/test_phase_loop_cli.py
    - skills/adapt/tests/lib/test_validator_wrapper.py
    - skills/adapt/references/phases/phase4/agent.md

key-decisions:
  - "Phase 4 agent.md protected paths reference updated to performance_tuning_gate.md (consistent with verify.md in other phases)"
  - "test_compat.py _normalize_phase_numbers adds performance_tuning_gate.md -> verify.md normalization for structural comparison"
  - "test_runner.py phase4->phase5 for status doc check (Phase 4 agent.md uses different status formatting)"

patterns-established:
  - "Gate file name normalization: when a new phase uses a different gate file name than verify.md, the doc consistency test normalizes it for structural comparison"

requirements-completed: [PH4-01, PH4-02, PH4-03, PH5-RENUM, PH6-RENUM, TEST-UPD]

# Metrics
duration: 8min
completed: 2026-06-24
---

# Phase 10 Plan 03: Test Updates for 7-Phase Structure Summary

**Updated 7 test files for 7-phase renumbering: range(7) throughout, FLAKE_RERUN_PHASES={3,5}, performance-tuning at Phase 4, feature-compat at Phase 5, kb-consistency at Phase 6**

## Performance

- **Duration:** 8 min
- **Started:** 2026-06-24T14:49:48Z
- **Completed:** 2026-06-24T14:57:43Z
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments
- All test files updated to use range(7) for 7-phase structure
- test_validator_wrapper.py now asserts FLAKE_RERUN_PHASES={3,5} and PHASE_VALIDATORS with performance-tuning at 4, feature-compat at 5, kb-consistency at 6
- test_plugin_layout.py fully updated: Phase 4 checks performance-tuning, Phase 5 checks feature-compat, Phase 6 checks kb-consistency
- Phase 4 agent.md protected paths reference fixed to use performance_tuning_gate.md
- Doc consistency test normalization extended to handle different gate file names

## Task Commits

Each task was committed atomically:

1. **Task 1: Update test_runner.py + test_plugin_layout.py** - `83c1fe5` (test)
2. **Task 2: Update test_compat.py, test_housekeeping_check.py, test_summary_generator.py, test_phase_loop_cli.py** - `cf3aae6` (test)
3. **Task 3: Update test_validator_wrapper.py for FLAKE_RERUN_PHASES and PHASE_VALIDATORS** - `5e53c8b` (test)

**Deviation fixes:** `759fd9d` (fix)

## Files Created/Modified
- `skills/adapt/tests/test_runner.py` - range(7), logs range(1,6), phase6 no-logs, phase4->phase5 status check
- `skills/adapt/tests/test_plugin_layout.py` - Phase 4 performance-tuning schema/gate, Phase 5 feature-compat schema/matrix, Phase 6 kb-consistency schema/extraction_rules/source_templates, adapt-phase6.md agent
- `skills/adapt/tests/lib/test_compat.py` - range(7), phase=[0-6] regex, performance_tuning_gate.md normalization
- `skills/adapt/tests/lib/test_housekeeping_check.py` - range(7)
- `skills/adapt/tests/lib/test_summary_generator.py` - range(7)
- `skills/adapt/tests/lib/test_phase_loop_cli.py` - range(7), logs range 1-5
- `skills/adapt/tests/lib/test_validator_wrapper.py` - FLAKE_RERUN_PHASES={3,5}, PHASE_VALIDATORS with 7 phases, phase4 no-flake-rerun, phase5 threshold test
- `skills/adapt/references/phases/phase4/agent.md` - protected paths reference fixed to performance_tuning_gate.md

## Decisions Made
- Phase 4 agent.md protected paths reference updated to `performance_tuning_gate.md` instead of bare directory, making it consistent with `verify.md` references in other phases
- Added `performance_tuning_gate.md -> verify.md` normalization in test_compat.py so the DOC-03 structural comparison remains valid despite different gate file names
- Changed test_runner.py status doc check from Phase 4 to Phase 5 because Phase 4 (performance-tuning) uses different status formatting in its agent.md

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Phase 4 agent.md protected paths reference incomplete**
- **Found during:** Task 2 verification (test_compat.py::test_hooks_sections_identical_after_normalization)
- **Issue:** Phase 4 agent.md referenced `references/phases/phase4/` (bare directory) instead of a specific gate file like other phases
- **Fix:** Changed to `references/phases/phase4/performance_tuning_gate.md` and added normalization in test_compat.py
- **Files modified:** skills/adapt/references/phases/phase4/agent.md, skills/adapt/tests/lib/test_compat.py
- **Verification:** test_compat.py DOC-03 tests pass after normalization
- **Committed in:** 759fd9d

**2. [Rule 1 - Bug] test_runner.py status doc check referenced Phase 4 with wrong assertion**
- **Found during:** Task 1 verification (test_runner.py::test_phase_final_status_docs_exclude_failed_checkpoint_status)
- **Issue:** Phase 4 (performance-tuning) agent.md uses different status formatting; the exact string "status: passed | human_needed" does not appear
- **Fix:** Changed the test to check Phase 5 (feature-compat) agent.md which has the expected string format
- **Files modified:** skills/adapt/tests/test_runner.py
- **Verification:** test passes
- **Committed in:** 759fd9d

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both auto-fixes were necessary for test correctness after the Phase 4 renumbering. The Phase 4 agent.md was a genuine oversight from Plan 02.

## Issues Encountered
- Pre-existing test_schema.py::test_legacy_v1_round_trip failure (unrelated to this plan, out of scope)

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 7-phase test files updated and passing (132 tests in modified files)
- Phase 10 plan execution complete
- Ready for any remaining phase-level verification

---
*Phase: 10-integrate-nsys-profiler-and-performance-tuner-as-new-phase-4-renumber-feature-compat-to-phase-5-and-kb-update-to-phase-6*
*Completed: 2026-06-24*

## Self-Check: PASSED
