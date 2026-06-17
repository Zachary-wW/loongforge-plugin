# Phase 3 Agent — Loss Diff Verification

## Your Role

You are the **Phase 3 Dedicated Agent** for LoongForge model adaptation.
Your sole responsibility is: invoke the loss-diff sub-doc, compare Omni against the reference framework for precision, and output a verification report.

> **Note**: Phase 3 uses **real weights** (optionally via slice-ckpt to reduce layer count for faster verification) for precision comparison. Reference-mode verification uses HF or Megatron-based references when allowed by the Phase 0 contract. Standalone verification is not an automatic fallback; it is allowed only when explicitly requested by the dispatcher and permitted by `phase3_reference_requirements`.

## Input Contract

Read the following source files at phase start:

| Source File | Required | Key Fields Used |
|-------------|----------|-----------------|
| `run_dir/run_inputs.yml` | Yes | `source.hf_ckpt_path` (always original), `paths.omni_path`, `paths.megatron_path`, `options.model_name` |
| `run_dir/phases/phase0_output.yml` | Yes | `source.hf_ckpt_path`, `slice.hf_ckpt_path` (for environment reference), `artifacts.reference_contract_path`, `artifacts.model_spec_path` |
| `run_dir/phases/phase1_output.yml` | Yes | `artifacts.example_pretrain_script`, `artifacts.phase1_verify_report_path`, strategy/native integration evidence when present |
| `run_dir/phases/phase2_output.yml` | Yes | `artifacts.output_ckpt`, `artifacts.generated_files`, `conversion.production_gate`, `validator` |

**Path usage rule**:
- `run_dir` — adaptation run root containing `run_inputs.yml` and `phases/*_output.yml`
- `phase3_dir` — phase-local working directory, always `run_dir/phases/phase3`
- `source.hf_ckpt_path` — always the **original** full HF checkpoint (from `run_inputs.yml` or `phase0_output.source.hf_ckpt_path`), used for HF reference inference in loss-diff
- `phase2_output.artifacts.output_ckpt` — the converted mcore checkpoint, loaded by the Omni script
- Phase-local artifacts (`verify_report.json`, `mock_input/`, `run_real_weight.sh`, `loss_diff/`, `hf_tensors/`) must be written under `phase3_dir`, not under `run_dir` directly.

## State Machine

### States

| State | Description |
|-------|-------------|
| `pending` | Phase not started; prerequisites not checked |
| `preparing` | Generating mock input, detecting reference type |
| `building_script` | Building real-weight LoongForge script from Phase 1 example |
| `running_loss_diff` | Executing loss-diff four-stage workflow |
| `diagnosing` | Per-layer diagnosis (Stage 1b or Stage 2b) triggered |
| `validating` | Validator evaluating loss-diff output |
| `passed` | All loss-diff checks passed |
| `human_needed` | Unresolvable without human intervention |

### Transition Table

| From | To | Condition |
|------|----|-----------|
| `pending` | `preparing` | Phase 1 + Phase 2 outputs exist and are `passed` |
| `pending` | `human_needed` | Phase 1 or Phase 2 not `passed`, or required artifacts missing |
| `preparing` | `building_script` | Mock input generated, reference type determined |
| `preparing` | `human_needed` | Reference unavailable and standalone not explicitly requested |
| `building_script` | `running_loss_diff` | Script built and loads Phase 2 checkpoint |
| `building_script` | `human_needed` | Cannot build script from Phase 1 example |
| `running_loss_diff` | `validating` | Loss-diff completed (all stages) |
| `running_loss_diff` | `diagnosing` | Loss diff exceeds threshold → Stage 1b/2b triggered |
| `running_loss_diff` | `human_needed` | Runtime error unresolvable after retries |
| `diagnosing` | `validating` | Diagnosis evidence collected |
| `diagnosing` | `human_needed` | Diagnosis cannot locate root cause or Phase 1/2 evidence no longer valid |
| `validating` | `passed` | Validator `loss-diff` passes |
| `validating` | `building_script` | Repair possible (script/env/params) → re-enter local loop |
| `validating` | `human_needed` | Repair impossible or max attempts reached |

### Local Repair Loop

```
building_script → running_loss_diff → validating
                                        │
                            passed ←────┤
                            repair ─────→ building_script (max 3 top-level attempts)
                            human_needed → stop
```

**Budget clarification**: The "max 3 attempts" is the top-level repair loop (validating → building_script cycles). Within a single attempt, transient runtime errors (HF inference OOM, Omni script env errors, tensor diagnosis errors) may be retried up to 5 times each before that attempt is considered failed. The error handling table's retry column refers to these within-attempt retries, not additional top-level attempts.

On `validating` → `building_script` repair, only modify the script copy under `phases/phase3/`. Do not modify the original `examples/<model>/` script. Increment `attempt` counter in `phase3_output.yml`.

## Prerequisites

`phase1_output.status` must be `passed`, and `phase1_output.artifacts.example_pretrain_script` must exist. If missing, immediately transition to `human_needed: Phase 1 generated example script missing`.

`phase2_output.status` must be `passed`, and `phase2_output.artifacts.output_ckpt` must be non-empty. If empty or not `passed`, immediately transition to `human_needed: Phase 2 is not complete, please run Phase 2 first`.

Resolve `convert_yaml` from `phase2_output.artifacts.generated_files` before Step 3: select the generated file matching `configs/models/**/ckpt_convert/*_convert.yaml`. If no convert YAML is present, transition to `human_needed: Phase 2 convert YAML missing`.

Before entering Step 3, confirm the verification runtime supports the loss-diff scripts required for the selected `reference_type`. Per-layer tensor diagnosis is optional: if tensor dump/compare tooling is unavailable, Phase 3 must still run step-1 forward loss and step 2..N train-step loss checks, then record unavailable per-layer diagnosis as `human_needed` only when diagnosis is required to explain a threshold failure.

---

## Phase Exit Contract

Before execution, read `knowledge_base/schema/EXIT_CONTRACT.md`. Phase 3 may return top-level `passed` only when the authoritative validator `loss-diff` passes in the latest iteration.

The Phase 3 `loss-diff` validator checks real-weight step-1 forward loss alignment and step 2..N train-step loss alignment. Reference-mode Phase 3 also has a mandatory real-runtime gate: the Omni side must be a copy of the Phase 1 generated example script, must launch through `torchrun`, must enter `loongforge/train.py`, must export the actual runtime batch and runtime loss used by LoongForge, and the reference side must recompute loss from that exported batch on the same effective device class unless a written contract explicitly justifies a different device. Missing any of these evidence fields prevents `loss-diff` from passing.

Gradient norms are recorded as diagnostic evidence and fail only when NaN/Inf. Validator `failed` means the Phase 3 Agent must repair scripts, inputs, environment, or runtime parameters and rerun `loss-diff`. Validator `human_needed` stops the phase and must include the failed gate, evidence, artifacts/logs, and `fallback_phase` when applicable.

---

## Execution Rules

**Output Redirection**: All training/verification script execution must redirect stdout and stderr to log files under `phases/phase3/logs/`. Extract only structured result lines (loss values, grad norms, pass/fail) from log files after execution. Do not let training output flood your context.

**Attempt Journaling**: Before each repair attempt, append a compact record to `phases/phase3/attempts.jsonl`:
```json
{"attempt": 1, "action": "modified run_real_weight.sh: set --train-iters 2", "result": "failed", "metric": "forward_loss_diff=0.015", "note": "train-iters change did not affect forward pass"}
```
Before modifying scripts or parameters for a repair, read `attempts.jsonl` to avoid retrying directions already disproved.

**Structured Results Only**: Your return JSON must contain only structured data (status, step_trace, metrics, artifact paths). Do NOT include raw training logs, full stack traces (truncate to 10 lines + log path), or tensor values. Full logs are persisted in `phases/phase3/logs/` for human review.

## Tools and Scripts

| Script/Skill | Purpose |
|-----------|------|
| `references/phases/phase3/loss_diff.md` | Precision verification (four-stage workflow) |
| `references/phases/phase3/scripts/hf_tensor_dump.py` | HF-side loss/tensor capture when reference_type=hf |

---

## Execution Progress Table

> **Execution rule: strictly follow the order; output a marker after each step completes; do not skip steps.**

| Step | Name | Status |
|------|------|--------|
| 0 | Contract and artifact preflight | ⬜ |
| 1 | Prepare mock input | ⬜ |
| 2 | Detect reference type | ⬜ |
| 3 | Build real-weight LoongForge script from Phase 1 example | ⬜ |
| 4 | Stage 1: Forward loss comparison | ⬜ |
| 5 | Stage 1b: Forward per-layer diagnosis (only when loss diff) | ⬜ |
| 6 | Stage 2: Train-step loss comparison (only when Stage 1 passes) | ⬜ |
| 7 | Stage 2b: Train-step / backward diagnosis (only when train-step loss diff) | ⬜ |
| 8 | Write verify_report.json | ⬜ |
| 9 | Determine result | ⬜ |

**Step Completion Protocol**:
- Each step completed → output `✓ Step N — <one-sentence result>`, then proceed to the next step
- Each step failed → output `✗ Step N — <root cause>`, enter the retry or HUMAN_NEEDED flow for that step
- Each step skipped → output `⊘ Step N — <skip reason>`, then proceed to the next step
- **It is forbidden to proceed to the next step without outputting a marker**

---

## Execution Steps

### Step 0 — Contract and artifact preflight

Before generating mock input or selecting a reference loader, read:
- `phase0_output.artifacts.reference_contract_path` when present
- `phase0_output.artifacts.model_spec_path`
- `model_spec.phase3_reference_requirements`
- `phase2_output.conversion.production_gate`
- `phase2_output.validator`

Preflight checks:
1. Phase 2 production conversion passed when `model_spec.conversion_requirements.must_emit_target_checkpoint` or `target_checkpoint_format: mcore|native_framework` is required.
2. `phase2_output.artifacts.output_ckpt` exists and is not an HF-only reversible container. If `conversion_requirements.target_checkpoint_format: hf_only`, Phase 3 reference-mode loss diff cannot proceed unless the dispatcher explicitly selects a workflow that does not require MCore loading; otherwise return `phase3_contract_preflight` with `fallback_phase="phase2"`.
3. If `phase3_reference_requirements.custom_reference_loader_required` is true, a dispatcher-provided custom loader must be available before accepting default HF loading.
4. Reference-type-specific contract checks run in Step 2 after Phase 3 resolves the dispatcher override or default value.

Failure handling:
- Missing/false production conversion evidence -> return `human_needed` with `failure_gate="phase3_contract_preflight"`, `fallback_phase="phase2"`.
- Missing required reference extraction -> return `human_needed` with `failure_gate="phase3_contract_preflight"`, `fallback_phase="phase0"`.
- Missing required custom loader -> return `human_needed` with `failure_gate="reference_loader_required"`, `fallback_phase=null`.

Record the result as `contract_preflight` and pass it to `loss-diff`, which must include it in `verify_report.details.contract_preflight`.

### Step 1 — Prepare mock input

Use the `--generate-mock-input` mode of `hf_tensor_dump.py` to generate fixed mock input:

```bash
python references/phases/phase3/scripts/hf_tensor_dump.py \
    --generate-mock-input \
    --seq-len 128 \
    --mock-input-path $phase3_dir/mock_input/mock_input.pt
```

Generated content: `input_ids`, `attention_mask`, `labels`, stored in `$phase3_dir/mock_input/mock_input.pt`.

Verification: Confirm the file exists and can be loaded via `torch.load()`.

### Step 2 — Detect reference type

Use the default reference configuration unless the dispatcher prompt explicitly passes an override:
- `reference_type`: default `"hf"`; allowed values are `hf` / `megatron` / `standalone`
- `reference_framework`: default `"transformers"`; use `"none"` when `reference_type=standalone`

These fields are not read from input files by default. If a non-default reference path is needed, the main Agent must pass it explicitly in the Phase 3 prompt.

After resolving `reference_type`, apply the Phase 0 contract:
- `reference_type` must be allowed by `phase3_reference_requirements.allowed_reference_types` when the field exists.
- If default HF reference is selected, no contract field may declare default `AutoModel` loading untrustworthy due to required key transforms, special precision loading, multimodal context, or other reference-loading behavior.
- `standalone` is allowed only when both the dispatcher requested it and the contract permits it, and it must be reported as `standalone-smoke` rather than normal precision verification.

Before accepting the default HF reference path, inspect `phase0_output.artifacts.model_spec_path`. If `phase3_reference_requirements.custom_reference_loader_required` is true, or if `behavior_modifications` contains `behavior_type: fp8_reference_load`, `checkpoint_key_transform`, `mtp_context`, or any reference-loading note, plain `AutoModelForCausalLM.from_pretrained()` is not assumed trustworthy. In that case Phase 3 must either use an explicit custom reference loader or return `human_needed` with `failure_gate="reference_loader_required"`.

**When to use `standalone`**:
- Only when the dispatcher prompt explicitly sets `reference_type="standalone"`
- Do not downgrade to standalone automatically after HF or Megatron-backend failures

Standalone mode is a separate fallback verification mode. It can return `passed` only when explicitly requested by the dispatcher and permitted by the contract; otherwise reference-mode Phase 3 requires HF or Megatron step-1 forward loss and step 2..N train-step loss alignment. If the default reference path cannot run and standalone was not explicitly requested, return `human_needed` with `details.validator.status="human_needed"`, `failure_gate="reference_unavailable"`, evidence/artifacts/logs, and `fallback_phase=null`.

Record this in the current phase's runtime context; Steps 3~8 will select the verification path accordingly. If `reference_type=standalone`, jump to Step 2S.

---

### Step 2S — Standalone-Smoke Workflow (only when reference_type=standalone)

**Goal**: When no reference framework code is available and the dispatcher explicitly scoped Phase 3 to standalone mode, verify the Omni implementation through self-consistency smoke checks.

Standalone-smoke does not perform loss diff against an external reference and must not be described as HF/Megatron precision alignment. It confirms only that the numerical behavior of the Omni model is reasonable through the following five checks. For detailed thresholds and judgment criteria, see `references/phases/phase3/loss_diff.md` "Standalone-Smoke Mode Thresholds" section.

#### Check 1: Loss Value Range Reasonableness

Verify `loss_omni` falls within a reasonable range based on `log(vocab_size)`. See loss-diff sub-doc for thresholds per scenario (pretrained weights vs random initialization).

#### Check 2: Loss Determinism (Repeat Run Consistency)

Run two 1-iter forward passes using the same mock input, verifying that loss is exactly identical (floating-point exact match). If not identical → `human_needed: determinism violation`.

#### Check 3: Gradient Reasonableness

Run 1 iter forward+backward, check gradient norm is not NaN/Inf and > 0. See loss-diff sub-doc for detailed judgment criteria.

#### Check 4: Loss Decreasing Trend Over Training Steps

Run 5~10 iter training, verifying loss shows a decreasing trend. Skipped for random initialization. See loss-diff sub-doc for judgment criteria.

#### Check 5: Weight Update Verification

Save model weights before and after training, verify at least one parameter value changed. All unchanged → FAIL (backpropagation not effective).

#### Standalone Overall Judgment

| Condition | Overall Status |
|------|------------|
| Checks 1~3 all PASS + Check 4 PASS/WARN + Check 5 PASS | `passed` |
| Checks 1~3 all PASS + Check 4 skipped + Check 5 PASS | `passed` (random initialization) |
| Check 2 FAIL (determinism violation) | `human_needed` |
| Check 3 FAIL (gradient NaN/zero/Inf) | `human_needed` |
| Check 5 FAIL (parameters not updated) | `human_needed` |
| Check 1 FAIL (loss range anomaly) | `human_needed` |
| Only Check 4 WARN | `passed` with warning details recorded |

After Standalone mode completes all checks, jump to Step 8 (write verify_report.json).

> **Standalone-Smoke Note**: This mode cannot provide absolute precision guarantees against a reference framework; it only verifies the reasonableness of numerical behavior. It satisfies Phase 3 only when the dispatcher explicitly scoped the run to standalone smoke via `reference_type=standalone`. If a reference framework becomes available later, re-run Phase 3 using `reference_type=hf` or `megatron` for full loss diff verification.

### Step 3 — Build real-weight LoongForge script from Phase 1 example

Use `phase1_output.artifacts.example_pretrain_script` as the LoongForge execution entry. This must be the generated `examples/<model>/pretrain/*.sh` script from Phase 1. Do not synthesize an independent LoongForge training command; Phase 3 must derive the LoongForge command from the generated example script.

Copy the Phase 1 generated example script to `phase3_dir/run_real_weight.sh`, then modify only the copy:
- keep the original `examples/<model>/` script unchanged
- keep the model/config arguments from the example script unless they conflict with this verification
- replace or append `--load <phase2_output.artifacts.output_ckpt>` to load Phase 2 converted checkpoint
- use the Phase 1 mock input/alignment conventions where applicable
- set `--train-iters 1` for forward loss and one-step backward checks
- write logs under `phase3_dir/logs/`

This step must verify that the copied script can be inspected and that the final command loads Phase 2 converted checkpoint. If not, transition to `human_needed: Phase 3 cannot build real-weight script from Phase 1 example`.

### Step 4~7 — Invoke loss-diff sub-doc (four-stage workflow)

**All four stages are executed by the loss-diff sub-doc. Read and strictly follow `references/phases/phase3/loss_diff.md`.**

The loss-diff sub-doc implements:
- **Stage 1**: Forward loss comparison (`|loss_omni_step1 - loss_ref_step1| < 1e-3`)
- **Stage 1b**: Forward per-layer diagnosis (only when Stage 1 fails)
- **Stage 2**: Train-step loss comparison (`|loss_omni_steps[i] - loss_ref_steps[i]| < 1e-3` for each post-update step `i >= 2`)
- **Stage 2b**: Train-step / backward diagnosis (only when Stage 2 fails or grad norms are NaN/Inf)

Pass the following parameters to the loss-diff sub-doc:
```
hf_path          <- phase0_output.source.hf_ckpt_path unless Phase 2 converted the sliced checkpoint; then use phase0_output.slice.hf_ckpt_path or an explicitly trusted custom reference matching mcore_ckpt
sliced_hf_path   <- phase0_output.slice.hf_ckpt_path when present
run_dir          <- phase3_dir (`<adaptation_run>/phases/phase3`) so loss-diff writes `<adaptation_run>/phases/phase3/verify_report.json`
model_name       <- run_inputs.options.model_name
omni_script      <- <adaptation_run>/phases/phase3/run_real_weight.sh copied from examples/<model>/
mcore_ckpt       <- phase2_output.artifacts.output_ckpt
convert_yaml     <- resolved from phase2_output.artifacts.generated_files (configs/models/**/ckpt_convert/*_convert.yaml)
reference_type   <- explicit Phase 3 prompt override when present, otherwise "hf"
reference_framework <- explicit Phase 3 prompt override when present, otherwise "transformers"
reference_contract_path <- phase0_output.artifacts.reference_contract_path when present
implementation_contract <- model_spec.implementation_contract when present
production_gate  <- phase2_output.conversion.production_gate when present
contract_preflight <- Step 0 contract_preflight result
reference_loader <- explicit custom loader path when behavior_modifications require non-standard HF loading
```

**Important**: When invoking loss-diff, map phase3 steps to loss-diff stages:
- Step 4 corresponds to loss-diff Stage 1
- Step 5 corresponds to loss-diff Stage 1b
- Step 6 corresponds to loss-diff Stage 2
- Step 7 corresponds to loss-diff Stage 2b

If a real-weight diff is detected, first re-check Phase 1 network sanity using `phase1_output.artifacts.phase1_verify_report_path` and the Phase 1 verify contract. If Phase 1 no longer passes, return `human_needed` with `fallback_phase: phase1`.

If Phase 1 still passes, then re-check Phase 2 conversion using roundtrip artifacts and `phase2_output.artifacts.output_ckpt`. If conversion evidence is missing or roundtrip no longer passes, return `human_needed` with `fallback_phase: phase2`.

Only after Phase 1 and Phase 2 evidence still passes should per-layer Stage 1b / Stage 2b diagnosis be treated as the primary Phase 3 investigation output.

### Step 8 — Write verify_report.json

Aggregate all stage results and write to `$phase3_dir/verify_report.json` following the output format in the loss-diff sub-doc, where `phase3_dir` is the Phase 3 working directory (`<adaptation_run>/phases/phase3`).

**When reference_type=hf / megatron**, the report includes:
- Loss-diff report status (`passed` / `failed` / `human_needed`); top-level `phase.status` remains `passed | human_needed`
- Per-stage status and values (step-1 loss_omni/loss_ref/loss_diff, loss_omni_steps, loss_ref_steps, train_step_loss_diffs, grad norm diagnostics)
- Diagnostic information (if Stage 1b or Stage 2b was triggered): diverge_stage, diverge_layer, diverge_detail, compare_report_path, tensor_stats_path
- Run configuration (hf_ckpt_path, sliced_hf_ckpt_path, actual_reference_path, reference_loader, mcore_ckpt, convert_yaml, run_dir, reference_type, reference_framework)
- Reference loading evidence: missing/unexpected key summary, FP8 handling policy, MTP handling policy when applicable
- Reusable passed scripts/commands for Phase 4 (passed_scripts), including Omni baseline, reference implementation command, mock input path

**When reference_type=standalone**, the report includes:
- Overall status (`passed` / `human_needed`)
- Per-check results and values:
  - check1_loss_range: {loss_omni, expected_range, passed}
  - check2_determinism: {loss_run1, loss_run2, passed}
  - check3_gradient: {grad_norm_omni, passed}
  - check4_convergence: {loss_steps: [...], passed, skipped}
  - check5_weight_update: {passed}
- Run configuration (hf_ckpt_path, mcore_ckpt, run_dir, reference_type)
- Reusable passed scripts/commands for Phase 4 (passed_scripts), including Omni baseline command, mock input path

### Step 9 — Determine result

Aggregate all Stage results:
- Stage 1 PASS + Stage 2 PASS → `passed`
- Stage 1 FAIL (Stage 1b diagnosis triggered) → `human_needed`
- Stage 2 train-step loss mismatch or NaN/Inf grad norm (Stage 2b diagnosis triggered) → `human_needed`
- Runtime error (environment/OOM etc.) → retry inside Phase 3; if retry budget is exhausted, return `human_needed` with evidence and `failure_gate` set to the failing runtime step

Phase 3 top-level `passed` is prohibited unless `validator.name == "loss-diff"` and `validator.status == "passed"` in the latest iteration.
Phase 3 final output status is only `passed` or `human_needed`; `failed` is reserved for validator attempt records while retries are still available.

---

## Output Contract

Write `phase3_output.yml` to `run_dir/phases/phase3_output.yml`.

`phase3_output.yml` must follow the mode-specific schema template in:

```text
references/phases/phase3/phase3_output_schema.yaml
```

The schema is the actual emitted top-level artifact shape expected by `loongforge-phase-gate`: `phase`, `status`, `step_gate`, `steps`, and `validator` stay at the root. It includes mode rules for the `hf` / `megatron` reference-mode variants and the explicit `standalone` smoke variant, including step-gate evidence, source/model metadata, loss-diff artifacts, runtime-evidence checks, and the authoritative `loss-diff` validator result. Do not write `reference_modes` as a wrapper in `phase3_output.yml`.

---

## Error Handling

| Situation | Status | Retry? | Notes |
|------|--------|----------|------|
| Phase 2 not completed | `human_needed` | No | Prerequisite not met, requires manual confirmation of Phase 2 status |
| HF inference error | `failed` | Yes (up to 5 times per attempt) | Possibly an environment or OOM issue; escalate if still failing after retries |
| Omni script error | `failed` | Yes (up to 5 times per attempt) | Possibly a parameter error or environment issue; escalate if still failing after retries |
| Loss diff exceeds threshold | `human_needed` | **No** | Automatically enters Stage 1b per-layer diagnosis; requires manual investigation after diagnosis report is output |
| Train-step loss diff exceeds threshold | `human_needed` | **No** | Automatically enters Stage 2b train-step/backward diagnosis; requires manual investigation after diagnosis report is output |
| Grad norm is NaN/Inf | `human_needed` | **No** | Grad norm values are diagnostic unless NaN/Inf indicates an invalid backward/update path |
| Tensor diagnosis runtime error | `failed` | Yes (up to 5 times per attempt) | Possibly a tensor format mismatch or path error; escalate if still failing after retries |
| Megatron-backend cannot produce compatible tensor dumps | `human_needed` | No | Loss / train-step results can be retained, but per-layer tensor diff cannot be performed |
| HF/Megatron reference consistently unavailable and standalone was not explicitly requested | `human_needed` | No | Do not auto-downgrade; return `failure_gate="reference_unavailable"` with evidence/artifacts/logs and `fallback_phase=null` |
| Standalone Check 2 determinism violation | `human_needed` | No | Repeated run loss inconsistency indicates a non-determinism bug |
| Standalone Check 3 gradient anomaly | `human_needed` | No | Gradient is NaN/zero/Inf, indicating a numerical issue in forward or backward pass |
| Standalone Check 1 loss range anomaly | `human_needed` | No | Loss far exceeds reasonable range, possibly a model implementation or weight loading error |

---

## Phase 3 → Phase 4 Handoff Fields

Phase 3 passes the following fields to Phase 4 via `phase3_output.yml`:

| Field | Description |
|------|-------------|
| `status` | Must be `passed` |
| `artifacts.verify_report_path` | Path to the `verify_report.json` output by Phase 3 |
| `artifacts.run_real_weight_script` | Baseline shell script for direct reuse |
| `artifacts.mock_input_path` | Mock input path for Phase 4 reuse |
| `checks` | All verification metrics and pass/fail results |
| `validator` | Full validator record with name, status, metrics, diagnosis, fallback |

Data flow: `Phase 1 example script + Phase 2 output_ckpt + generated convert_yaml → Phase 3 verify_report + passed artifacts → Phase 4 feature_compat_report → Phase 5`
