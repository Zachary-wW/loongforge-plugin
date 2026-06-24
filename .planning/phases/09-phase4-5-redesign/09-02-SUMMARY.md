---
phase: 09-phase4-5-redesign
plan: 02
subsystem: adapt-skill
tags: [hf_analysis, bridge_mapping, extraction_rules, megatron_code_paths, source_templates, phase5]

# Dependency graph
requires:
  - phase: 06-phase0-redesign
    provides: hf_analysis.yaml + bridge_mapping.yaml three-document output schema
  - phase: 07-phase1-redesign
    provides: generated_loongforge_files + generated_megatron_files dual-repo output
provides:
  - Phase 5 agent.md consuming hf_analysis + bridge_mapping as primary input
  - extraction_rules.yaml v2 with megatron_code_paths and behavioral_diff_rule
  - source_templates with megatron_code_paths section
  - phase5_output_schema.yaml with v2 source/checks fields
  - validate_phase_completion.py Phase 5 conditional checks
affects: [phase5, kb-consistency, validate_phase_completion]

# Tech tracking
tech-stack:
  added: []
  patterns: [conditional-check-pattern, behavioral-diff-to-trap-conversion, megatron-code-paths-matching]

key-files:
  created: []
  modified:
    - skills/adapt/references/phases/phase5/agent.md
    - skills/adapt/references/phases/phase5/extraction_rules.yaml
    - skills/adapt/references/phases/phase5/source_templates/llm.yaml
    - skills/adapt/references/phases/phase5/source_templates/vlm.yaml
    - skills/adapt/references/phases/phase5/source_templates/diffusion.yaml
    - skills/adapt/references/phases/phase5/phase5_output_schema.yaml
    - skills/adapt/scripts/validate_phase_completion.py

key-decisions:
  - "hf_analysis.yaml as PRIMARY source for structural_tags/traps, model_spec.yaml as legacy fallback"
  - "bridge_mapping.component_bridge[].behavioral_diff entries with high/critical impact become trap entries"
  - "megatron_code_paths section uses same pattern-matching approach as code_paths but for Megatron file paths"
  - "Phase 5 validation checks are conditional (if X is not None) for backward compatibility with legacy runs"

patterns-established:
  - "Conditional check pattern: bridge_mapping_consumed and hf_analysis_consumed fields are present only when Phase 0 v2 output exists"
  - "Behavioral diff to trap conversion: behavioral_diff entries with impact high/critical become trap entries with field=topic, detail=HF/Megatron comparison"

requirements-completed: [P5R-01, P5R-02]

# Metrics
duration: 5min
completed: 2026-06-24
---

# Phase 09 Plan 02: Phase 5 Redesign Summary

**Phase 5 agent.md, extraction_rules.yaml, source_templates, and output schema rewritten to consume hf_analysis.yaml + bridge_mapping.yaml as primary input with Megatron code_paths support**

## Performance

- **Duration:** 5 min
- **Started:** 2026-06-24T11:54:30Z
- **Completed:** 2026-06-24T11:59:33Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- Phase 5 agent.md Input Contract reads hf_analysis.yaml + bridge_mapping.yaml as primary sources (model_spec.yaml as legacy fallback)
- Step 1 reads components/structural_tags/traps from hf_analysis, component_bridge/gaps from bridge_mapping, generated_loongforge_files + generated_megatron_files from Phase 1
- Traps extraction includes bridge_mapping behavioral_diff entries (high/critical impact converted to trap entries with deduplication)
- extraction_rules.yaml version bumped to 2 with megatron_code_paths section, behavioral_diff_rule, and updated source paths
- All 3 source templates (llm.yaml, vlm.yaml, diffusion.yaml) have megatron_code_paths section after code_paths
- phase5_output_schema.yaml extended with source.hf_analysis_path, source.bridge_mapping_path, checks.bridge_mapping_consumed, checks.hf_analysis_consumed
- validate_phase_completion.py has Phase 5 conditional checks for bridge_mapping_consumed and hf_analysis_consumed

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewrite Phase 5 agent.md Input Contract and Step 1** - `285adff` (feat)
2. **Task 2: Update extraction_rules.yaml v2 + source_templates + validator** - `9d05f68` (feat)

## Files Created/Modified
- `skills/adapt/references/phases/phase5/agent.md` - Input Contract, Step 1 data reading, Step 7 megatron_code_paths check, Output Contract v2 fields
- `skills/adapt/references/phases/phase5/extraction_rules.yaml` - Version 2 with hf_analysis source, megatron_code_paths, behavioral_diff_rule, generated_megatron_files
- `skills/adapt/references/phases/phase5/source_templates/llm.yaml` - megatron_code_paths section added
- `skills/adapt/references/phases/phase5/source_templates/vlm.yaml` - megatron_code_paths section added
- `skills/adapt/references/phases/phase5/source_templates/diffusion.yaml` - megatron_code_paths section added
- `skills/adapt/references/phases/phase5/phase5_output_schema.yaml` - v2 source/checks fields with version comment
- `skills/adapt/scripts/validate_phase_completion.py` - Phase 5 bridge_mapping_consumed and hf_analysis_consumed conditional checks

## Decisions Made
- hf_analysis.yaml as PRIMARY source for structural_tags/traps (model_spec.yaml as legacy fallback only)
- behavioral_diff entries with impact high/critical are converted to trap entries with field=topic and detail="HF: ... / Megatron: ..."
- megatron_code_paths match rules use pattern-matching similar to code_paths but targeting megatron/ directory structure
- Phase 5 validation checks follow conditional pattern (if X is not None) for backward compatibility with legacy runs

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 5 redesign complete; Phase 4 redesign was completed in Plan 01
- Both Phase 4 and Phase 5 now consume hf_analysis + bridge_mapping as primary input
- validate_phase_completion.py has checks for both Phase 4 and Phase 5
- Phase 09 complete after this plan

---
*Phase: 09-phase4-5-redesign*
*Completed: 2026-06-24*

## Self-Check: PASSED

- All 7 modified files exist on disk
- Both task commits exist: 285adff (Task 1), 9d05f68 (Task 2)
- All success criteria grep checks pass
- Python compilation passes for validate_phase_completion.py
