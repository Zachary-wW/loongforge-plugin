---
phase: 10-integrate-nsys-profiler-and-performance-tuner-as-new-phase-4-renumber-feature-compat-to-phase-5-and-kb-update-to-phase-6
plan: 01
subsystem: adapt-skill
tags: [nsys-profiler, performance-tuner, phase-renumbering, feature-compat, kb-update]

# Dependency graph
requires:
  - phase: 09-loop-controller-hardening
    provides: Stable loop controller and validator infrastructure
provides:
  - New Phase 4 Performance Tuning reference content (agent.md, output schema, gate definition)
  - Phase 5 Feature Compat (renumbered from old Phase 4) with Phase 4 handoff fields
  - Phase 6 KB Update (renumbered from old Phase 5) with phase4_status and phase5_status
  - Updated agent files for adapt-phase4, adapt-phase5, adapt-phase6
affects: [SKILL.md, validate_phase_completion.py, loop_controller.py, run.py]

# Tech tracking
tech-stack:
  added: []
  patterns: [two-stage-orchestration-profiling-then-optimization, four-gate-acceptance-model, staged-validation-approach]

key-files:
  created:
    - skills/adapt/references/phases/phase4/agent.md
    - skills/adapt/references/phases/phase4/phase4_output_schema.yaml
    - skills/adapt/references/phases/phase4/performance_tuning_gate.md
    - agents/adapt-phase6.md
  modified:
    - skills/adapt/references/phases/phase5/agent.md
    - skills/adapt/references/phases/phase5/phase5_output_schema.yaml
    - skills/adapt/references/phases/phase5/feature_matrix.yaml
    - skills/adapt/references/phases/phase6/agent.md
    - skills/adapt/references/phases/phase6/phase6_output_schema.yaml
    - skills/adapt/references/phases/phase6/extraction_rules.yaml
    - agents/adapt-phase4.md
    - agents/adapt-phase5.md

key-decisions:
  - "Phase 4 Performance Tuning uses two-stage orchestration: Stage A profiling (nsys-profiler) then Stage B optimization (performance-tuner)"
  - "Four-gate acceptance model (performance, numerical, memory/stability, scope) for optimization candidates"
  - "Phase 5 Input Contract adds phase4_output.yml and phase4/ as optional inputs for Phase 4 handoff"
  - "Phase 6 adaptation_status_source now has phase4_status (Performance Tuning) and phase5_status (Feature Compat, renamed from old phase4_status)"

patterns-established:
  - "Two-stage phase orchestration: profiling sub-skill then optimization sub-skill within one phase"
  - "SKILL_DIR env var pattern with $HOME/.claude/skills/<name> fallback for external skill directories"
  - "Four-gate acceptance model for performance optimization candidates"
  - "Staged validation: short-smoke -> medium -> full with explicit user approval for escalation"

requirements-completed: [PH4-01, PH4-02, PH4-03, PH5-RENUM, PH6-RENUM]

# Metrics
duration: 12min
completed: 2026-06-24
---

# Phase 10 Plan 01: Performance Tuning Phase 4 + Phase Renumbering Summary

**New Phase 4 Performance Tuning with two-stage nsys-profiler/performance-tuner orchestration and 4-gate acceptance model; old Phase 4 (Feature Compat) moved to Phase 5 with handoff fields; old Phase 5 (KB Update) moved to Phase 6 with phase4_status/phase5_status**

## Performance

- **Duration:** 12 min
- **Started:** 2026-06-24T14:23:38Z
- **Completed:** 2026-06-24T14:35:29Z
- **Tasks:** 3
- **Files modified:** 12

## Accomplishments
- Created new Phase 4 Performance Tuning reference content with two-stage orchestration, 12-step execution table, 4-gate acceptance model, and SKILL_DIR env vars for nsys-profiler and performance-tuner
- Moved old Phase 4 (Feature Compat) to Phase 5 with all internal references renumbered and Phase 4 handoff note added
- Moved old Phase 5 (KB Update) to Phase 6 with all internal references renumbered, phase4_status added, and LOG template updated with P4/P5 rows
- Updated all three agent files (adapt-phase4, adapt-phase5, adapt-phase6) to reference correct phase manuals

## Task Commits

Each task was committed atomically:

1. **Task 1: Create new Phase 4 Performance Tuning reference content** - `ebc1c6e` (feat)
2. **Task 2: Move old phase4/ -> phase5/ and old phase5/ -> phase6/ with internal renumbering** - `490ae80` (feat)
3. **Task 3: Update agents/ directory** - `2177f58` (feat)

## Files Created/Modified
- `skills/adapt/references/phases/phase4/agent.md` - New Phase 4 Performance Tuning agent manual with two-stage orchestration
- `skills/adapt/references/phases/phase4/phase4_output_schema.yaml` - Phase 4 output schema with performance-tuning validator and 4-gate acceptance
- `skills/adapt/references/phases/phase4/performance_tuning_gate.md` - Gate definition for 4-gate acceptance model
- `skills/adapt/references/phases/phase5/agent.md` - Phase 5 Feature Compat (renumbered from Phase 4) with Phase 4 handoff
- `skills/adapt/references/phases/phase5/phase5_output_schema.yaml` - Phase 5 output schema with phase4_optimization_report and phase4_best_recipe
- `skills/adapt/references/phases/phase5/feature_matrix.yaml` - Feature matrix with phase5_builtin and not_phase5_runtime
- `skills/adapt/references/phases/phase6/agent.md` - Phase 6 KB Update (renumbered from Phase 5) with P4/P5 in LOG template
- `skills/adapt/references/phases/phase6/phase6_output_schema.yaml` - Phase 6 output schema with phase4_status and phase5_status
- `skills/adapt/references/phases/phase6/extraction_rules.yaml` - Extraction rules updated for Phase 6 with phase5_status
- `agents/adapt-phase4.md` - Rewritten for Performance Tuning with NSYS_SKILL_DIR and TUNER_SKILL_DIR
- `agents/adapt-phase5.md` - Updated for Feature Compat with Phase 4 handoff note
- `agents/adapt-phase6.md` - Created for KB Update with phase4_status/phase5_status in adaptation_status_source

## Decisions Made
- Phase 4 Performance Tuning uses two-stage orchestration (profiling then optimization) rather than a monolithic single-pass approach
- Four-gate acceptance model (performance, numerical, memory/stability, scope) for optimization candidates, matching the performance-tuner skill's gate structure
- Phase 5 Input Contract adds Phase 4 output as optional (not required) since Phase 4 may produce no accepted candidate (best_recipe: null)
- Phase 6 adaptation_status_source ordering: phase0..phase3, then new phase4_status (Performance Tuning), then phase5_status (Feature Compat, renamed from old phase4_status)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed remaining Phase 4 prose references in phase5/agent.md**
- **Found during:** Task 2 (phase4->phase5 renumbering)
- **Issue:** sed bulk replacements missed several prose "Phase 4" references that were not exact matches (e.g., "Phase 4 may return", "Phase 4 must reuse", "not a final Phase 4 status", "Phase 4 final output")
- **Fix:** Manually applied targeted Edit replacements for each remaining Phase 4 prose reference
- **Files modified:** skills/adapt/references/phases/phase5/agent.md
- **Verification:** grep confirms only Phase 4 handoff references remain
- **Committed in:** 490ae80 (part of Task 2 commit)

**2. [Rule 1 - Bug] Fixed phase=4 in phase5/agent.md Loop Engineering Hooks PR submission**
- **Found during:** Task 2 (phase4->phase5 renumbering)
- **Issue:** The `gh_helper.open_pr` calls in the Post-Edit section still had `phase=4` instead of `phase=5`
- **Fix:** Applied targeted Edit to change `phase=4, attempt=<K>` to `phase=5, attempt=<K>` in both LoongForge and Megatron PR submission lines
- **Files modified:** skills/adapt/references/phases/phase5/agent.md
- **Verification:** grep confirms no remaining `phase=4` in phase5/agent.md
- **Committed in:** 490ae80 (part of Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both auto-fixes were correctness requirements for the renumbering task. No scope creep.

## Issues Encountered
- Original phase4/agent.md did not have a standalone `phase: 4` declaration line or `adapt-phase4` string, so the plan's verify command that grepped for `phase: 5` and `adapt-phase5` in the phase5/agent.md could not find exact matches. The key content (Phase 5 identity, correct path references) is present in prose form.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase reference directories are now correctly structured with phase0 through phase6
- Plan 02 should update SKILL.md and validate_phase_completion.py to reflect the new phase numbering
- Plan 03 should update loop_controller.py and run.py for the new 7-phase workflow

---
*Phase: 10-integrate-nsys-profiler-and-performance-tuner-as-new-phase-4-renumber-feature-compat-to-phase-5-and-kb-update-to-phase-6*
*Completed: 2026-06-24*

## Self-Check: PASSED

All 13 created/modified files verified present. All 3 task commits verified in git log.
