---
phase: 10-integrate-nsys-profiler-and-performance-tuner-as-new-phase-4-renumber-feature-compat-to-phase-5-and-kb-update-to-phase-6
plan: 02
subsystem: adapt-skill-core
tags: [phase-renumbering, validator-wrapper, schema-version, protected-paths, 7-phase]

# Dependency graph
requires:
  - phase: 10-01
    provides: Phase 4 performance_tuning_gate.md, phase4 agent.md, nsys profiling references
provides:
  - PHASE_VALIDATORS with 7 entries (4=performance-tuning, 5=feature-compat, 6=kb-consistency)
  - FLAKE_RERUN_PHASES = {3, 5}
  - validate_phase_completion.py with phase 4/5/6 checks
  - range(7) across all runner/loop/resume/summary/housekeeping files
  - schema_version: 2 in RunInputs for migration compat
  - SKILL.md seven-phase table and EXIT_CONTRACT.md updated validator mapping
  - protected_paths.py with performance_tuning_gate.md entry
affects: [adapt-skill-core, validator-gate, run-lifecycle, documentation]

# Tech tracking
tech-stack:
  added: []
  patterns: [schema_version migration gate, conditional phase checks with backward compat]

key-files:
  created: []
  modified:
    - skills/adapt/lib/validator_wrapper.py
    - skills/adapt/scripts/validate_phase_completion.py
    - skills/adapt/scripts/run.py
    - skills/adapt/scripts/phase_loop.py
    - skills/adapt/lib/resume.py
    - skills/adapt/lib/housekeeping_check.py
    - skills/adapt/lib/summary_generator.py
    - skills/adapt/lib/protected_paths.py
    - skills/adapt/SKILL.md
    - skills/adapt/knowledge_base/schema/EXIT_CONTRACT.md
    - skills/adapt/lib/schema.py

key-decisions:
  - "performance-tuning (Phase 4) excluded from FLAKE_RERUN_PHASES because its failures are structural (wrong optimization, memory OOM), not near-threshold numerical flakes"
  - "schema_version default 2 with warning on resume when legacy version detected, rather than auto-migration, to avoid silent phase-number misinterpretation"
  - "Phase 4 validation checks are conditional (if X is not None) matching existing Phase 1/2/3 pattern for backward compat"

patterns-established:
  - "Conditional phase checks: new Phase 4 checks follow if-is-not-None pattern for backward compat with legacy runs"

requirements-completed: [PH4-01, PH4-02, PH4-03, PH5-RENUM, PH6-RENUM]

# Metrics
duration: 7min
completed: 2026-06-24
---

# Phase 10: 7-Phase Code and Doc Renumbering Summary

**Updated all Python code, validators, and documentation from 6-phase to 7-phase structure with performance-tuning as Phase 4, schema_version migration gate, and protected_paths entry**

## Performance

- **Duration:** 7 min
- **Started:** 2026-06-24T14:39:48Z
- **Completed:** 2026-06-24T14:46:55Z
- **Tasks:** 3
- **Files modified:** 11

## Accomplishments
- PHASE_VALIDATORS expanded to 6 entries with performance-tuning at Phase 4, feature-compat renumbered to Phase 5, kb-consistency to Phase 6
- FLAKE_RERUN_PHASES updated from {3,4} to {3,5} -- performance-tuning failures are structural, not flaky
- validate_phase_completion.py gained a full Phase 4 performance-tuning checks block with profiling_evidence, bottleneck_diagnosis, candidate_table, candidate_validated, all_four_gates_judged, and bridge_mapping_consumed checks
- All 5 files with range(6) updated to range(7); run.py choices and logs dirs extended for Phase 5/6
- SKILL.md updated to seven-phase table with Phase 4 = Performance Tuning
- EXIT_CONTRACT.md validator mapping and fallback semantics updated for Phase 4/5/6
- schema_version: 2 added to RunInputs and run.py with resume-time warning for legacy schema
- protected_paths.py includes performance_tuning_gate.md pattern

## Task Commits

Each task was committed atomically:

1. **Task 1: Update validator_wrapper.py + validate_phase_completion.py** - `d0e3f53` (feat)
2. **Task 2: Batch update range(6)->range(7) + protected_paths** - `554fba4` (feat)
3. **Task 3: Update SKILL.md + EXIT_CONTRACT.md + schema_version** - `c7a5cbd` (feat)

## Files Created/Modified
- `skills/adapt/lib/validator_wrapper.py` - PHASE_VALIDATORS 7 entries, FLAKE_RERUN_PHASES {3,5}
- `skills/adapt/scripts/validate_phase_completion.py` - Phase 4 performance-tuning checks, renumbered Phase 5/6, range(7)
- `skills/adapt/scripts/run.py` - range(7), schema_version="2", resume warning, choices include "6"
- `skills/adapt/scripts/phase_loop.py` - choices range(0,7), help text 0-6
- `skills/adapt/lib/resume.py` - range(7), docstring phases 0-6
- `skills/adapt/lib/housekeeping_check.py` - range(7)
- `skills/adapt/lib/summary_generator.py` - both range(6)->range(7)
- `skills/adapt/lib/protected_paths.py` - performance_tuning_gate.md entry added
- `skills/adapt/SKILL.md` - seven-phase table, Phase 0-6 tracking, downstream phases 1-6
- `skills/adapt/knowledge_base/schema/EXIT_CONTRACT.md` - Phase 4/5/6 validator mapping, Phase 4->3 fallback
- `skills/adapt/lib/schema.py` - schema_version Optional[str]="2" field in RunInputs

## Decisions Made
- Performance-tuning excluded from FLAKE_RERUN_PHASES because its failures are structural (OOM, wrong optimization), not numerical threshold flakes
- schema_version set as string with default "2" rather than integer to avoid type confusion with legacy YAML that may lack the field; resume_run_dir warns rather than auto-migrates to prevent silent misinterpretation
- Phase 4 validation checks follow conditional (if-is-not-None) pattern for backward compat, matching existing Phase 1/2/3 style

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All code and doc files updated for 7-phase structure
- Plan 10-03 should add the remaining references and templates for Phase 4 performance-tuning gate doc, nsys profiling agent materials, and any test updates
- schema_version gate will warn users resuming legacy runs about the phase numbering change

---
*Phase: 10-integrate-nsys-profiler-and-performance-tuner-as-new-phase-4-renumber-feature-compat-to-phase-5-and-kb-update-to-phase-6*
*Completed: 2026-06-24*
