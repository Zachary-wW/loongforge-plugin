---
phase: 07-phase1-redesign
plan: 02
subsystem: verification
tags: [perf-rules, shared-seed, hf-sanity, example-dry-run, input-fixation, bridge-mapping]

# Dependency graph
requires:
  - phase: 07-phase1-redesign
    provides: "07-CONTEXT.md decisions D-03 through D-06, strategy_rules.yaml format reference"
provides:
  - "perf_rules.yaml with P1-P8 performance guard rails"
  - "verify.md rewritten with shared-seed initialization, HF sanity run, example script dry run, full input tensor fixation"
  - "phase1_output_schema.yaml extended with bridge_mapping_consumed, generated_megatron_files, strategy_overrides, verification check fields"
affects: [07-phase1-redesign-plan-03, phase1-agent-md]

# Tech tracking
tech-stack:
  added: []
  patterns: [shared-seed-initialization, perf-lint-blocking, input-tensor-fixation, gap-component-skip-report]

key-files:
  created:
    - skills/adapt/references/phases/phase1/perf_rules.yaml
  modified:
    - skills/adapt/references/phases/phase1/verify.md
    - skills/adapt/references/phases/phase1/phase1_output_schema.yaml

key-decisions:
  - "Shared-seed initialization tightens tolerance from 1e-2 to 1e-3 because identical parameters eliminate initialization noise"
  - "Gap components (weight_map=null) are skipped during parameter mapping with explicit report; they cannot participate in loss comparison"
  - "All perf rules P1-P8 are violation_severity: blocking per D-03; no warnings"
  - "HF Sanity Run is a separate Step 0B (not integrated into Step 3) for early failure detection"

patterns-established:
  - "Shared-seed initialization: torch.manual_seed(42) -> dump HF state_dict -> map via bridge_mapping -> set LoongForge params"
  - "Input tensor fixation: all four tensors (input_ids, attention_mask, position_ids, labels) fixed identically on both sides"
  - "Perf lint pattern: when/violation_signal/rationale format matching strategy_rules.yaml structural_rules"

requirements-completed: [P1R-03, P1R-04]

# Metrics
duration: 5min
completed: 2026-06-24
---

# Phase 07 Plan 02: Verification Rigor & Performance Guard Rails Summary

**8 blocking perf guard rails (P1-P8), shared-seed initialization with 1e-3 tolerance, HF sanity run, example script dry run, full input tensor fixation, and extended output schema with dual-repo fields**

## Performance

- **Duration:** 5 min
- **Started:** 2026-06-24T11:06:38Z
- **Completed:** 2026-06-24T11:11:49Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Created perf_rules.yaml with 8 blocking performance guard rails covering IdentityOp, flat Parameter, MoE reuse, activation checkpointing, TP/EP communication, fused kernels, inverse RoPE for MLA, and activation offloading
- Rewrote verify.md with shared-seed initialization (1e-3 tolerance), HF Sanity Run (Step 0B), full input tensor fixation (all 4 tensors), Example Script Dry Run (Step 6.5), and gap component skip with explicit report
- Extended phase1_output_schema.yaml with bridge_mapping_consumed, generated_megatron_files, strategy_overrides, hf_sanity_run_passed, example_script_dry_run_passed, perf_lint_executed

## Task Commits

Each task was committed atomically:

1. **Task 1: Create perf_rules.yaml with 8 static performance guard rails (P1-P8)** - `40b37b3` (feat)
2. **Task 2: Rewrite verify.md with shared-seed init, HF sanity run, example script dry run; extend phase1_output_schema.yaml** - `3f06575` (feat)

## Files Created/Modified
- `skills/adapt/references/phases/phase1/perf_rules.yaml` - 8 blocking performance guard rails (P1-P8) with when/violation_signal/rationale format
- `skills/adapt/references/phases/phase1/verify.md` - Rewritten verification skill with shared-seed init, HF sanity run, full tensor fixation, example dry run (402 lines, up from 254)
- `skills/adapt/references/phases/phase1/phase1_output_schema.yaml` - Extended with bridge_mapping_consumed, generated_megatron_files, strategy_overrides, 3 new check fields, 2 new validator metric fields

## Decisions Made
- Shared-seed initialization tightens tolerance from 1e-2 to 1e-3 because identical parameters eliminate initialization noise
- Gap components (weight_map=null in bridge_mapping) are skipped during parameter mapping with explicit report listing component name, reason, and parameter count delta
- All perf rules use violation_severity: blocking (no warnings) per D-03 -- violations must be fixed before Phase 1 can pass
- HF Sanity Run is a separate Step 0B (not integrated into Step 3) for early failure detection before spending time on LoongForge alignment
- PHASE1_VERIFY hook now fixes all four input tensors (input_ids, attention_mask, position_ids, labels) instead of only input_ids

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Next Phase Readiness
- verify.md and perf_rules.yaml ready for Phase 1 agent.md to reference in Step 3
- phase1_output_schema.yaml ready for Phase 1 agent.md output contract and validate_phase_completion.py checks
- Plan 03 (agent.md rewrite) can now reference these files

---
*Phase: 07-phase1-redesign*
*Completed: 2026-06-24*
