# Phase 6: Phase 0 Redesign — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-24
**Phase:** 06-phase0-redesign
**Areas discussed:** Output structure, Megatron depth, Weight mapping, No-KB novel architecture

---

## Output Structure

| Option | Description | Selected |
|--------|-------------|----------|
| 3 separate files | hf_analysis.yaml + reference_impl_analysis.yaml + bridge_mapping.yaml | ✓ |
| 1 expanded model_spec.yaml | All information in one file, risk of 800+ lines | |
| model_spec + extended contract | Keep model_spec, expand reference_contract.yml | |

**User's choice:** 3 separate files
**Notes:** User confirmed the three-document architecture. `model_spec.yaml` is retired (renamed to `hf_analysis.yaml`). `reference_contract.yml` is absorbed into `bridge_mapping.yaml`. `gap_decisions.md` added as human-readable record. `slice_report.json` retained unchanged.

---

## Megatron Analysis Depth

| Option | Description | Selected |
|--------|-------------|----------|
| Analyze existing only | Read existing Megatron module signatures, __init__, forward; gaps go to bridge_mapping gaps[] | ✓ |
| Full depth (A + B) | Analyze existing + design new modules needed | |
| Shallow (issue/PR only) | Only extract info from Megatron issues/PRs, no code reading | |

**User's choice:** Analyze existing only
**Notes:** Phase 0 only reads existing Megatron modules. New module requirements go to `gaps[]` with impact level and guidance. Phase 1 decides how to implement. A new sub-skill `megatron-reference-analyzer` will handle the Megatron-side reading.

---

## Weight Mapping

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 0 produces weight map | weight_map in bridge_mapping.yaml per component where Megatron has existing module | ✓ (conditional) |
| Phase 0 lists patterns only | Weight naming patterns, not specific names | |
| Phase 2 only | Phase 0 doesn't touch weights at all | |

**User's choice:** Conditional — "如果Megatron有对应的实现可以做weight map，没有就交给phase2做"
**Notes:** When Megatron has a corresponding existing module, Phase 0 produces the weight_map (HF → Megatron parameter names). When the Megatron module doesn't exist yet (gap), weight mapping is deferred to Phase 2. The bridge_mapping.yaml entry will have `weight_map: null` with a note.

---

## No-KB Novel Architecture

| Option | Description | Selected |
|--------|-------------|----------|
| Best-effort + gaps | Select closest candidate, mark low_confidence_candidate, record gaps, scan Megatron issues for clues | ✓ |
| Fail fast → human_needed | Escalate when KB has no entry | |
| Auto-create KB stub | Automatically create draft KB entry for new architectures | |

**User's choice:** Best-effort + gaps
**Notes:** Phase 0 never escalates to human_needed solely due to KB absence. It provides enough signal (low_confidence_candidate flag + explicit gap entries) for Phase 1 to choose adapt_ref/new_impl over reuse_ref. Auto-create KB stub deferred to future work.

---

## Phase 0 Does NOT Use Loop FSM

**Discussion:** User confirmed in prior turn that Phase 0 is read-only analysis and does not need the 12-state FSM. Instead, Phase 0 uses a quality inner loop: analyze → completeness check → (if incomplete) dig deeper → (max 3 rounds) → human_needed.

**Decision:** Phase 0 does not participate in the Loop FSM. Quality assurance is via structural completeness checks, not PR/issue cycles.

---

## Claude's Discretion

- Exact schema field names and types for bridge_mapping.yaml and reference_impl_analysis.yaml
- reference_contract.yml → bridge_mapping.yaml migration strategy
- Whether megatron-reference-analyzer is a separate skill or a mode of hf-model-analyzer
- Inner loop iteration limit (3 rounds suggested)
- phase0_output.yml check structure for three-document output

## Deferred Ideas

- Auto-create KB stub for novel architectures — future work
- Unified validator for Phase 0 — out of scope (quality inner loop uses structural checks)
- Megatron module implementation design — Phase 1's job
- Community references beyond Megatron (vLLM, DeepSpeed) — extendable in future
