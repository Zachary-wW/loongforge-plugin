---
phase: 06-phase0-redesign
plan: 01
subsystem: schema
tags: [pydantic, bridge-mapping, phase0, dual-reference, yaml-schema]

# Dependency graph
requires:
  - phase: 01-loop-foundation-contracts-schemas-safety-plumbing
    provides: "Pydantic v2 pattern (extra='forbid'), existing schema.py models"
provides:
  - "HfAnalysis, ReferenceImplAnalysis, BridgeMapping Pydantic v2 models"
  - "YAML schema templates for hf_analysis, reference_impl_analysis, bridge_mapping"
  - "Rewritten Phase 0 agent.md with 11-state dual-reference state machine"
  - "phase0_output_schema.yaml with three-document output contract"
affects: [06-02, 06-03, phase1-agent, phase2-agent, validate_phase_completion]

# Tech tracking
tech-stack:
  added: []
  patterns: ["dual-reference bridge mapping", "quality inner loop (max 3 rounds)", "deterministic bridge step (schema-driven)", "gap entry with phase1_guidance"]

key-files:
  created:
    - skills/adapt/tests/lib/test_schema_phase0.py
    - skills/adapt/knowledge_base/schema/hf_analysis_schema.yaml
    - skills/adapt/knowledge_base/schema/reference_impl_analysis_schema.yaml
    - skills/adapt/knowledge_base/schema/bridge_mapping_schema.yaml
    - skills/adapt/references/phases/phase0/phase0_output_schema.yaml
  modified:
    - skills/adapt/lib/schema.py
    - skills/adapt/references/phases/phase0/agent.md

key-decisions:
  - "HfAnalysis uses ConfigDict(extra='forbid') consistent with existing schema.py pattern; all model_spec_llm.yaml fields preserved"
  - "BridgeMapping.component_bridge.megatron uses Optional[List[str]] to represent gaps (null) vs mapped modules (list of references)"
  - "BridgeMapping absorbs reference_contract.yml fields (implementation_contract, conversion_requirements, phase3_reference_requirements) as Optional[Dict[str,Any]] for forward-compat (per D-05)"
  - "ReferenceEntry model in BridgeMapping uses string-typed fields (type, priority, trust_level) rather than Literal enums to match existing reference_contract_schema.yaml flexibility"
  - "Phase 0 agent.md quality inner loop uses max 3 rounds (per D-15), not the 12-state Loop FSM"

patterns-established:
  - "Three-document output: hf_analysis.yaml (HF side) + reference_impl_analysis.yaml (Megatron side) + bridge_mapping.yaml (bridge) per D-01"
  - "Deterministic bridge step (Step 5.5): schema-driven mapping, not agentic, per D-19"
  - "Quality inner loop: analyze -> completeness check -> dig deeper (max 3 rounds) -> human_needed per D-15"
  - "Gap entry pattern: id/component/hf/megatron/decision/impact/phase1_guidance per D-07"
  - "Weight map null for gap components (no Megatron module exists) per D-10"

requirements-completed: [P0R-01, P0R-03, P0R-04, P0R-05, P0R-06, P0R-09]

# Metrics
duration: 12min
completed: 2026-06-24
---

# Phase 6 Plan 1: Three-Document Schemas + Phase 0 Agent Rewrite Summary

**Pydantic v2 models (HfAnalysis, ReferenceImplAnalysis, BridgeMapping) + YAML templates + 11-state Phase 0 agent.md with dual-reference bridge analysis and quality inner loop**

## Performance

- **Duration:** 12 min
- **Started:** 2026-06-24T08:29:50Z
- **Completed:** 2026-06-24T08:42:19Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Defined three Pydantic v2 models (HfAnalysis, ReferenceImplAnalysis, BridgeMapping) with extra='forbid' and full D-spec field coverage; all 12 TDD tests pass
- Created three YAML schema templates with field documentation, examples (MLASelfAttention), and D-reference annotations
- Rewrote Phase 0 agent.md from 584-line 7-step single-reference to 781-line 9-step dual-reference state machine with three new states (analyzing_megatron, bridge_mapping, quality_loop)
- Created phase0_output_schema.yaml with updated checks and artifacts section referencing all three new output files

## Task Commits

Each task was committed atomically:

1. **Task 1 (TDD RED): test(06-01): add failing tests** - `40a3a45` (test)
2. **Task 1 (TDD GREEN): feat(06-01): implement Phase 0 three-document Pydantic models and YAML schemas** - `bcb1fbd` (feat)
3. **Task 2: feat(06-01): rewrite Phase 0 agent.md with dual-reference state machine and bridge step** - `c4728da` (feat)

## Files Created/Modified
- `skills/adapt/lib/schema.py` - Added 17 new Pydantic models for HfAnalysis, ReferenceImplAnalysis, BridgeMapping and their sub-models
- `skills/adapt/tests/lib/test_schema_phase0.py` - 12 TDD tests covering model parsing, extra='forbid', gap validation, reference contract absorption
- `skills/adapt/knowledge_base/schema/hf_analysis_schema.yaml` - YAML schema template for hf_analysis.yaml output (supersedes model_spec.yaml)
- `skills/adapt/knowledge_base/schema/reference_impl_analysis_schema.yaml` - YAML schema template for reference_impl_analysis.yaml with MLASelfAttention example
- `skills/adapt/knowledge_base/schema/bridge_mapping_schema.yaml` - YAML schema template for bridge_mapping.yaml with component_bridge, gaps, and absorbed reference_contract fields
- `skills/adapt/references/phases/phase0/agent.md` - Complete rewrite with 11-state dual-reference state machine and 9-step execution progress
- `skills/adapt/references/phases/phase0/phase0_output_schema.yaml` - Updated output schema with three-document artifact paths and new validation checks

## Decisions Made
- BridgeMapping.component_bridge.megatron uses Optional[List[str]] (null for gaps) rather than a separate GapComponentBridge model -- keeps the schema simpler and matches D-09 directly
- ReferenceEntry uses string-typed fields rather than Literal enums for type/priority/trust_level to maintain compatibility with existing reference_contract_schema.yaml which uses string values
- WeightStructure kept as a sub-model within HfAnalysis (rather than a separate file) to preserve backward compat with current model_spec.yaml Step 4 behavior
- Phase 0 agent.md explicitly preserves the Step 5a reference-patchset migration section since bridge_mapping.yaml.implementation_contract absorbs those fields

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Worktree was sparse (missing lib/ and tests/lib/ directories). Copied existing files from main repo to worktree before implementing. This is a worktree setup issue, not a plan deviation.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Three-document schema contracts are ready for Plan 02 (Megatron reference analyzer skill + example YAML files)
- BridgeMapping model structure is ready for Plan 03 (validation gate update + downstream Phase 1/2 contract updates)
- Phase 0 agent.md references megatron-reference-analyzer skill which is created in Plan 02

---
*Phase: 06-phase0-redesign*
*Completed: 2026-06-24*

## Self-Check: PASSED

All 8 created/modified files verified present. All 3 commits verified in git log. No stub patterns (TODO/FIXME/placeholder) found in any plan file.
