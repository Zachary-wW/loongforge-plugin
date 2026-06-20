---
name: phase1-verify
description: >
  Use when Phase 1 generated LoongForge network code has passed lint, code review, and L0 smoke test, and needs random-init trimmed HF vs LoongForge network sanity verification before Phase 2.
---

# phase1-verify — Phase 1 Network Sanity Verification

## Responsibility

Verify that Phase 1 generated LoongForge network code is structurally runnable and trainable under random-init / trimmed configuration.

`phase1-verify` is the authoritative Phase 1 exit validator. Phase 1 can pass only when this tool returns `status=passed`. A `failed` result is repairable inside Phase 1 and must be followed by another validator run. A `human_needed` result stops Phase 1 and should include the failed gate, evidence, and fallback phase when applicable.

This is not real-weight precision verification. Phase 1 uses trimmed configs and random initialization for network sanity; Phase 3 is the real-weight precision gate using Phase 2 converted checkpoints.

## Input

Passed by the Phase 1 Agent:
- `slice_hf_ckpt_path`: HF model path used for random-init HF config loading (sliced when Phase 0 performed slicing, otherwise original)
- `hf_modeling_path`: HF modeling file used to inspect training/loss interface
- `run_dir`: current run directory
- `model_name`: LoongForge model name
- `generated_files`: Phase 1 generated files, including model YAML and examples/<model>/ scripts
- `model_spec_path`: path to `model_spec.yaml` (from `phase0_output.artifacts.model_spec_path`)
- `reference_contract_path`: optional path to `reference_contract.yml` (from `phase0_output.artifacts.reference_contract_path`)
- `implementation_contract`: optional contract mirrored inside `model_spec.yaml`

Resolve `example_pretrain_script` from `generated_files` by selecting the generated `examples/<model>/pretrain/*.sh` script. The verification must use a copy of this generated example script; do not synthesize an independent LoongForge training command.

## Output Artifacts

- `<run_dir>/phases/phase1/trimmed_config.json`: HF trimmed config
- `<run_dir>/phases/phase1/trimmed_omni.yaml`: LoongForge trimmed config
- `<run_dir>/phases/phase1/phase1_alignment.json`: HF/LoongForge alignment contract and verification result
- `<run_dir>/phases/phase1/hf_train_verify.py`: generated only when HF source lacks a usable loss/training interface
- `<run_dir>/phases/phase1/phase1_verify_report.json`: final verification report

---

## Execution Progress Table

| Step | Name | Status |
|------|------|--------|
| 0A | Contract/native integration gate | ⬜ |
| 0 | Generate trimmed configs | ⬜ |
| 1 | Resolve HF training interface | ⬜ |
| 2 | Build and verify training parameter alignment | ⬜ |
| 3 | Forward sanity comparison | ⬜ |
| 4 | Trainability verification | ⬜ |
| 5 | Failure diagnosis | ⬜ |
| 6 | Write phase1_verify_report.json | ⬜ |

**Step Completion Protocol**:
- Each step completed -> output `✓ Step N — <one-sentence result>`, then proceed to the next step
- Each step failed -> output `✗ Step N — <root cause>`, enter retry or HUMAN_NEEDED flow
- Each step skipped -> output `⊘ Step N — <skip reason>`, then proceed to the next step

---

## Step 0A — Contract/native integration gate

Before generating trimmed configs, inspect `generated_files`, `example_pretrain_script`, `model_spec_path`, and optional `reference_contract_path`.

If `implementation_contract.required_integration_level` is `framework_native` or `framework_extension`, verify:
- generated Python files are normal LoongForge/Megatron model/config/layer-spec/provider files, not an isolated standalone runner;
- the generated example script invokes the real LoongForge training entrypoint and normal model registry/factory path;
- model registration/config mapping is present in the generated files or expected registry files;
- no generated artifact bypasses LoongForge/Megatron assembly to satisfy only the verifier;
- Phase 1 strategy metadata, when available, records `contract_preflight_passed: true`, `all_required_components_framework_native: true`, and `no_self_contained_fallback: true`.

If this gate fails, return `human_needed` with `failure_gate="non_native_phase1_implementation"`, `fallback_phase="phase1"`, and evidence listing the offending file/script. Do not continue to random-init loss comparison because a numerically matching standalone shim does not satisfy a native integration contract.

If no implementation contract exists, or the contract explicitly allows `standalone_reference`, record the gate as `skipped` or `passed` with the reason and continue.

### 0A.1 — Reference-patchset migration gate (model-specific)

When the model entry in `knowledge_base/sources/...` declares `migration.required: true`, Phase 1 must additionally run the model's deterministic migration verifier before random-init smoke. This catches migrations that drop required Omni files, leak model-specific code into Megatron, or fail to register the new family.

Invoke the verifier named in the source YAML's `validation.verifier_script` against both reference and target trees, writing its report to `<run_dir>/phases/phase1/<family>_migration_report.json`. The verifier must report `validator.status=passed`. Treat any failure as `failure_gate="reference_patchset_migration_invariants"` with `fallback_phase="phase1"` and stop before Step 0; do not paper over leaked Megatron strings or missing Omni files with random-init runs.

---

## Step 0 — Generate trimmed configs

Generate both configs before any comparison:
- HF: `<run_dir>/phases/phase1/trimmed_config.json`
- LoongForge: `<run_dir>/phases/phase1/trimmed_omni.yaml`

Rules:
- `num_hidden_layers` / `num_layers` = 2
- MoE routed experts = 4 when present
- Shared experts keep original values
- `seq_len` = 128
- TP/PP/EP = 1 unless the model structure cannot run without a non-1 value; if so, record the reason in `phase1_alignment.json`
- Do not modify original HF or LoongForge config files

After writing, verify key architectural fields are aligned: layer count, hidden size, attention heads, KV heads, FFN hidden size, vocab size, norm epsilon, rope/position settings, and MoE expert counts.

---

## Step 1 — Resolve HF training interface

Read `hf_modeling_path` and determine whether HF can compute training loss directly:
- If the HF model class defines `compute_loss` or returns `loss` when `labels` are passed, use the native HF path.
- Otherwise generate `<run_dir>/phases/phase1/hf_train_verify.py` that wraps model outputs with standard causal-LM `CrossEntropyLoss`.

Generated HF wrapper must implement the same label shift and ignore-index semantics recorded in Step 2. If the semantics cannot be confirmed from HF source, output `human_needed: HF loss semantics unclear`.

---

## Step 2 — Build and verify training parameter alignment

**Training Parameter Alignment Contract**: HF and LoongForge must use identical training parameters during Phase 1 comparison.

Write `<run_dir>/phases/phase1/phase1_alignment.json` before running Step 3. It must include both HF and LoongForge values plus `matched: true|false` for each field:

- Data shape: `micro_batch_size`, `global_batch_size`, `seq_len`, `attention mask`, `position ids`, label tensor shape
- Randomness: `seed`, parameter initialization seed, data generation seed
- Runtime mode: Step 3 uses eval/no-grad unless loss requires grad; Step 4 uses train mode on both sides
- Dropout: disabled for Step 3 forward comparison; enabled/disabled consistently for Step 4
- Model config: layer count, hidden size, head count, KV head count, FFN hidden size, vocab size, norm epsilon, rope/position settings, MoE expert counts
- Loss semantics: loss function, label shift, ignore_index, reduction, loss dtype
- Optimizer and train loop for Step 4: optimizer type, learning_rate, weight_decay, beta/epsilon values, gradient accumulation, gradient clipping, scheduler setting, train iterations
- Precision/runtime flags: precision dtype, AMP/autocast, TF32, deterministic flags, device placement

If any field cannot be matched or verified, stop and return `human_needed: Phase 1 HF/LoongForge training parameter alignment incomplete` with `alignment_mismatches` listing the fields. If a difference is intentional because the frameworks expose different names for the same behavior, record the mapping in `phase1_alignment.json` and continue.

---

## Step 3 — Forward sanity comparison

Copy `example_pretrain_script` into `<run_dir>/phases/phase1/` and modify only the copy for trimmed random-init verification. Preserve the original `examples/<model>/` script unchanged. The copied script is the LoongForge execution entry for this verification.

Use fixed input:
- `input_ids = arange(100, 100 + seq_len)`
- `labels = input_ids.clone()` unless loss semantics require shifted labels internally
- `seq_len = 128`
- `seed = 42`

Run HF and LoongForge with the trimmed configs and aligned parameters from Step 2. LoongForge may use `OMNI_PHASE1_VERIFY=1` to activate Phase 1 debug hooks.

Pass condition:

```text
abs(hf_loss - omni_loss) < 1e-2
```

Failure enters Step 5. Do not run Phase 3 real-weight loss-diff here.

---

## Step 4 — Trainability verification

After Step 3 passes, run 10 training steps on both sides with the aligned Step 2 parameters.

Record:
- `hf_train_losses`
- `omni_train_losses`
- `hf_grad_norms`
- `omni_grad_norms`
- whether at least one trainable parameter changed on each side

Pass condition:
- Grad norms are finite and non-zero on both sides
- At least one trainable parameter updates on both sides
- Record `trainability_warning` if the short loss trend is noisy despite healthy gradients and parameter updates

The primary pass criteria are finite/non-zero gradients and parameter updates on both sides. A noisy short loss trend alone may still return top-level `passed` when gradients and parameter updates are healthy, with `trainability_warning` recorded in details. NaN/Inf gradients, zero gradients, or no parameter update must return `human_needed`.

---

## Step 5 — Failure diagnosis

For Step 3 forward mismatch:
1. Compare `phase1_alignment.json` first; do not debug model code until alignment is confirmed.
2. Use Phase 1 forward hooks from `knowledge_base/recipes/forward_debug.md` to locate the first divergent component.
3. Check generated `_config.py`, `_layer_spec.py`, `_model.py`, and YAML field mappings against `model_spec.yaml`.
4. After fixes, rerun the Phase 1 Agent's linter and L0 smoke test when generated Python files changed.

For Step 4 trainability failure:
1. Check loss semantics and label shift.
2. Check `requires_grad`, optimizer parameter groups, gradient flow, and parameter update.
3. Check train/eval mode, dropout, precision flags, and gradient clipping.

Write failure diagnosis into `<run_dir>/phases/phase1/phase1_verify_report.json`. The Phase 1 Agent owns retry policy and decides whether to archive persistent failure patterns under `knowledge_base/failure_patterns/phase1/` after repeated unresolved failures.

---

## Step 6 — Write phase1_verify_report.json

Write `<run_dir>/phases/phase1/phase1_verify_report.json` and return this JSON to the Phase 1 Agent:

```json
{
  "status": "passed|failed|human_needed",
  "summary": "Phase 1 network sanity verification result",
  "failed_at_step": null,
  "root_cause": null,
  "step_trace": [
    {"step": "0A", "name": "Contract/native integration gate", "status": "passed|skipped|human_needed", "note": "..."},
    {"step": 0, "name": "Generate trimmed configs", "status": "passed|failed", "note": "..."},
    {"step": 1, "name": "Resolve HF training interface", "status": "passed|failed|human_needed", "note": "..."},
    {"step": 2, "name": "Build and verify training parameter alignment", "status": "passed|human_needed", "note": "..."},
    {"step": 3, "name": "Forward sanity comparison", "status": "passed|failed|human_needed", "note": "..."},
    {"step": 4, "name": "Trainability verification", "status": "passed|failed|human_needed", "note": "..."},
    {"step": 5, "name": "Failure diagnosis", "status": "passed|skipped|human_needed", "note": "..."},
    {"step": 6, "name": "Write phase1_verify_report.json", "status": "passed|failed", "note": "..."}
  ],
  "details": {
    "trimmed_hf_config": "<run_dir>/phases/phase1/trimmed_config.json",
    "trimmed_omni_config": "<run_dir>/phases/phase1/trimmed_omni.yaml",
    "phase1_verify_report_path": "<run_dir>/phases/phase1/phase1_verify_report.json",
    "example_pretrain_script": "examples/<model>/pretrain/pretrain_<model>.sh",
    "phase1_verified_script": "<run_dir>/phases/phase1/pretrain_<model>_trimmed.sh",
    "phase1_alignment_path": "<run_dir>/phases/phase1/phase1_alignment.json",
    "contract_native_gate": {
      "status": "passed|skipped|human_needed",
      "failure_gate": null,
      "framework_native_required": true,
      "standalone_fallback_detected": false
    },
    "alignment_mismatches": [],
    "hf_train_script_generated": true,
    "hf_loss": 10.432,
    "omni_loss": 10.428,
    "loss_diff": 0.004,
    "trainability_warning": null,
    "hf_train_losses": [10.5, 10.2, 9.8],
    "omni_train_losses": [10.4, 10.1, 9.7],
    "hf_grad_norms": [0.5],
    "omni_grad_norms": [0.5],
    "parameter_update_verified": true,
    "validator": {
      "name": "phase1-verify",
      "status": "passed|failed|human_needed",
      "attempt": 1,
      "failure_gate": null,
      "metrics": {
        "hf_loss": 10.432,
        "omni_loss": 10.428,
        "loss_diff": 0.004,
        "parameter_update_verified": true
      },
      "commands": [],
      "logs": [],
      "artifacts": ["<run_dir>/phases/phase1/phase1_verify_report.json", "<run_dir>/phases/phase1/phase1_alignment.json"],
      "diagnosis": null,
      "fallback_phase": null
    }
  }
}
```
