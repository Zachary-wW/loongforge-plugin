---
phase: 06-phase0-redesign
plan: 03
subsystem: validation, contracts
tags: [pydantic, yaml, bridge_mapping, phase0, validation-gate]

# Dependency graph
requires:
  - phase: 06-phase0-redesign
    provides: "Three-document schemas (hf_analysis, reference_impl_analysis, bridge_mapping) from Plan 01-02"
provides:
  - "Updated Phase 0 validation gate with three-document checks"
  - "Phase 1/2 input contracts wired to bridge_mapping_path"
  - "reference_contract_schema.yaml deprecation notice"
  - "SKILL.md Phase 0 description update"
affects: [phase1, phase2, validation, phase0-output]

# Tech tracking
tech-stack:
  added: []
  patterns: [bridge_mapping_as_primary_input, v2_checks_replace_model_spec, bridge_mapping_file_content_validation]

key-files:
  created:
    - skills/adapt/tests/lib/test_validate_phase0.py
  modified:
    - skills/adapt/scripts/validate_phase_completion.py
    - skills/adapt/references/phases/phase1/agent.md
    - skills/adapt/references/phases/phase2/agent.md
    - skills/adapt/references/phases/phase0/reference_contract_schema.yaml
    - skills/adapt/SKILL.md
    - skills/adapt/tests/test_plugin_layout.py

key-decisions:
  - "Phase 0 validation gate replaces model_spec_exists with three-document checks (hf_analysis_exists, reference_impl_analysis_exists, bridge_mapping_exists) plus bridge_mapping_component_bridge_non_empty and bridge_mapping_gaps_have_guidance"
  - "Phase 1 reads bridge_mapping_path as primary input with model_spec_path as deprecated legacy fallback for backward compat during transition"
  - "Phase 2 reads bridge_mapping weight_map as starting point for name_map generation; gap components require Phase 2 to design new weight mappings"
  - "reference_contract_schema.yaml retains full content with DEPRECATED header (not deleted) for backward reference"

patterns-established:
  - "Bridge mapping as primary Phase 0 output: downstream phases read bridge_mapping.yaml first, falling back to model_spec.yaml"
  - "Deep validation helper: _validate_phase0_bridge_mapping does file content validation beyond existence checks, called at end of Phase 0 block"

requirements-completed: [P0R-03, P0R-04]

# Metrics
duration: 6min
completed: 2026-06-24
---

# Phase 6 Plan 3: Validation Gate + Downstream Contracts Update Summary

**Phase 0 three-document validation gate with bridge_mapping file content validation, Phase 1/2 consumer contracts wired to bridge_mapping_path, reference_contract deprecation notice**

## Performance

- **Duration:** 6 min
- **Started:** 2026-06-24T08:58:55Z
- **Completed:** 2026-06-24T09:04:55Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- Updated validate_phase_completion.py Phase 0 block with 5 new three-document checks replacing model_spec_exists
- Added _validate_phase0_bridge_mapping helper for deep bridge_mapping.yaml file content validation (component_bridge non-empty, gaps have phase1_guidance)
- Wired Phase 1 input contract to bridge_mapping_path as primary input with model_spec_path deprecated fallback
- Wired Phase 2 input contract to bridge_mapping_path for weight_map source with Step 1 integration
- Added DEPRECATED header to reference_contract_schema.yaml pointing to bridge_mapping_schema.yaml
- Updated SKILL.md Phase 0 description to Dual-Reference Bridge Analysis with three-document output and quality inner loop

## Task Commits

Each task was committed atomically:

1. **Task 1: Update validate_phase_completion.py for three-document Phase 0 output** - `0c6333d` (test) + `d601288` (feat)
2. **Task 2: Update Phase 1/2 input contracts, deprecation notice, and SKILL.md** - `6b44245` (feat)

## Files Created/Modified
- `skills/adapt/scripts/validate_phase_completion.py` - Phase 0 three-document checks + _validate_phase0_bridge_mapping helper
- `skills/adapt/tests/lib/test_validate_phase0.py` - 13 TDD tests for Phase 0 validation (v2 checks, bridge_mapping file validation, regression)
- `skills/adapt/references/phases/phase1/agent.md` - bridge_mapping_path primary input, Step 1/2 bridge_mapping extraction
- `skills/adapt/references/phases/phase2/agent.md` - bridge_mapping_path for weight_map, Step 1 weight_map as name_map starting point
- `skills/adapt/references/phases/phase0/reference_contract_schema.yaml` - DEPRECATED header
- `skills/adapt/SKILL.md` - Dual-Reference Bridge Analysis, three-document output, quality inner loop
- `skills/adapt/tests/test_plugin_layout.py` - Fixed stale assertion (reference_contract_schema path -> bridge_mapping_schema compat)

## Decisions Made
- Phase 0 validation gate replaces model_spec_exists with 5 new three-document checks (hf_analysis_exists, reference_impl_analysis_exists, bridge_mapping_exists, bridge_mapping_component_bridge_non_empty, bridge_mapping_gaps_have_guidance) while retaining 3 v1 checks
- Phase 1 uses bridge_mapping_path as primary input with model_spec_path as deprecated fallback for transition compatibility
- Phase 2 uses bridge_mapping weight_map as name_map starting point; gap components require Phase 2 to design new weight mappings
- reference_contract_schema.yaml content preserved (not deleted) with DEPRECATED header for backward reference

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Fixed stale test_plugin_layout assertion**
- **Found during:** Task 1 (TDD GREEN phase)
- **Issue:** test_phase0_schemas_are_externalized asserted literal path `references/phases/phase0/reference_contract_schema.yaml` in agent.md, but Plan 01's Phase 0 agent.md rewrite replaced this reference with bridge_mapping_schema references
- **Fix:** Updated assertion to accept either the literal path or `bridge_mapping_schema` reference, maintaining the intent that Phase 0 schemas must be referenced in the agent manual
- **Files modified:** skills/adapt/tests/test_plugin_layout.py
- **Verification:** 428 tests pass (was 415 before new tests + 1 previously failing)
- **Committed in:** d601288 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical — stale test assertion)
**Impact on plan:** Fix necessary for test suite health. Pre-existing issue from Plan 01; not introduced by this plan.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 0 three-document output is now fully wired through validation gate and downstream consumer contracts
- Phase 1 reads bridge_mapping_path as primary input; Phase 2 reads bridge_mapping weight_map
- All 428 tests pass including 13 new Phase 0 validation tests
- Ready for end-to-end Phase 0 execution with the new three-document structure

## Self-Check: PASSED

All created/modified files verified present. All commit hashes verified in git log.

---
*Phase: 06-phase0-redesign*
*Completed: 2026-06-24*
