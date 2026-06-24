---
phase: 07-phase1-redesign
plan: 03
subsystem: phase1-validation-and-checklist
tags: [validation, bridge-mapping, perf-lint, confidence-driven, checklist]
dependency_graph:
  requires: ["07-01", "07-02"]
  provides: [P1R-04, P1R-06]
  affects: [validate_phase_completion.py, megatron_preread_checklist.yaml]
tech_stack:
  added: []
  patterns: [conditional-validation-gate, confidence-driven-reading]
key-files:
  created: []
  modified:
    - skills/adapt/scripts/validate_phase_completion.py
    - skills/adapt/references/phases/phase1/megatron_preread_checklist.yaml
decisions:
  - "All Phase 1 validation checks are conditional (if X is not None) for backward compatibility with legacy runs"
  - "Valid Megatron file prefixes: megatron/ and loongforge/models/common/experimental_attention_variant/"
  - "Bridge mapping consumption helper verifies file exists AND component_bridge is non-empty"
  - "Checklist version bumped to 2; confidence_driven_reading is a new top-level section"
metrics:
  duration: 2min
  completed: "2026-06-24"
  tasks: 2
  files: 2
---

# Phase 07 Plan 03: Phase 1 Validation Checks & Confidence-Driven Checklist Summary

Conditional Phase 1 validation gate with bridge_mapping consumption verification, Megatron file prefix validation, perf lint execution checks, HF sanity run checks, and strategy override reason enforcement; plus confidence-driven Megatron pre-read checklist delegating component-specific reading to reference_impl_analysis.yaml.

## Completed Tasks

| Task | Name | Commit | Files Modified |
|------|------|--------|----------------|
| 1 | Add Phase 1 validation checks to validate_phase_completion.py | 5efd1af | skills/adapt/scripts/validate_phase_completion.py |
| 2 | Restructure megatron_preread_checklist.yaml for confidence-driven component reading | c375b18 | skills/adapt/references/phases/phase1/megatron_preread_checklist.yaml |

## Key Changes

### Task 1: Phase 1 Validation Checks

Added an `if phase == 1:` block in `validate_phase_output()` with 7 conditional checks:

1. **bridge_mapping_consumed** -- When present, must be True; indicates bridge_mapping was used as primary input
2. **generated_megatron_files** -- When present, must be a list with entries starting with valid Megatron prefixes (`megatron/` or `loongforge/models/common/experimental_attention_variant/`)
3. **perf_lint_executed** -- When present, must be True; indicates perf rules were enforced
4. **hf_sanity_run_passed** -- When present, must be True; indicates HF sanity run executed successfully
5. **example_script_dry_run_passed** -- When present, must be True; indicates example script dry run passed
6. **strategy_overrides** -- When overrides dict is present, each override must include a `reason` field
7. **_validate_phase1_bridge_mapping_consumption** helper -- When bridge_mapping_consumed is True, verifies the referenced bridge_mapping.yaml file exists on disk and has a non-empty component_bridge list

All checks are conditional (`if X is not None`) for backward compatibility: legacy Phase 1 runs without bridge_mapping will not have these fields and will pass through without error.

### Task 2: Confidence-Driven Megatron Pre-read Checklist

Restructured the checklist (version 1 -> 2) with a new `confidence_driven_reading` section containing 4 subsections:

- **high_confidence_components**: Load from reference_impl_analysis.yaml modules section; no direct Megatron source reading; downgrade to low if entry missing/incomplete
- **medium_confidence_components**: reference_impl_analysis.yaml for general context + targeted Megatron source for behavioral_diff topics only; downgrade to full 2c if behavioral_diff needs uncovered sections
- **low_confidence_components**: Full Step 2c.1-2c.7 reading protocol (traditional deep-read)
- **gap_components**: No Megatron source reading; use phase1_guidance from bridge_mapping gaps; proceed to Step 2d

Also: 3 assembly-flow sources marked `always_required: true`, 3 new confidence-level completion questions added, completion_rule updated to reference confidence levels.

## Deviations from Plan

None - plan executed exactly as written.

## Pre-existing Issues (Out of Scope)

Two test failures from Plan 01/02 changes, logged in deferred-items.md:

1. `test_compat.py::TestDocConsistency::test_hooks_sections_identical_after_normalization` -- agent.md dual-repo wording mismatch
2. `test_plugin_layout.py::test_phase1_strategy_rules_are_externalized` -- strategy_rules.yaml YAML parser error around step2d

These are pre-existing and not caused by Plan 03 changes.

## Known Stubs

None.

## Self-Check: PASSED

- FOUND: skills/adapt/scripts/validate_phase_completion.py
- FOUND: skills/adapt/references/phases/phase1/megatron_preread_checklist.yaml
- FOUND: commit 5efd1af
- FOUND: commit c375b18
