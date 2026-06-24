---
name: phase1-verify
description: >
  Use when Phase 1 generated LoongForge network code has passed lint, code review, and L0 smoke test, and needs shared-seed initialized HF vs LoongForge network sanity verification before Phase 2.
---

# phase1-verify -- Phase 1 Network Sanity Verification

## Responsibility

Verify that Phase 1 generated LoongForge network code is structurally runnable and trainable under shared-seed initialization with trimmed configuration.

`phase1-verify` is the authoritative Phase 1 exit validator. Phase 1 can pass only when this tool returns `status=passed`. A `failed` result is repairable inside Phase 1 and must be followed by another validator run. A `human_needed` result stops Phase 1 and should include the failed gate, evidence, and fallback phase when applicable.

This is not real-weight precision verification. Phase 1 uses trimmed configs and shared-seed initialization for network sanity; Phase 3 is the real-weight precision gate using Phase 2 converted checkpoints.

## Input

Passed by the Phase 1 Agent:
- `slice_hf_ckpt_path`: HF model path used for shared-seed HF config loading (sliced when Phase 0 performed slicing, otherwise original)
- `hf_modeling_path`: HF modeling file used to inspect training/loss interface
- `run_dir`: current run directory
- `model_name`: LoongForge model name
- `generated_files`: Phase 1 generated files, including model YAML and examples/<model>/ scripts
- `model_spec_path`: path to `model_spec.yaml` (legacy fallback, from `phase0_output.artifacts.model_spec_path`)
- `bridge_mapping_path`: path to `bridge_mapping.yaml` (PRIMARY input, from `phase0_output.artifacts.bridge_mapping_path`)
- `reference_contract_path`: optional path to `reference_contract.yml` (deprecated, absorbed into bridge_mapping.yaml)
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
| 0B | HF Sanity Run | ⬜ |
| 0 | Generate trimmed configs | ⬜ |
| 1 | Resolve HF training interface | ⬜ |
| 2 | Build and verify training parameter alignment | ⬜ |
| 3 | Forward sanity comparison (shared-seed initialization) | ⬜ |
| 4 | Trainability verification | ⬜ |
| 5 | Failure diagnosis | ⬜ |
| 6 | Write phase1_verify_report.json | ⬜ |
| 6.5 | Example Script Dry Run | ⬜ |

**Step Completion Protocol**:
- Each step completed -> output `Step N -- <one-sentence result>`, then proceed to the next step
- Each step failed -> output `Step N -- <root cause>`, enter retry or HUMAN_NEEDED flow
- Each step skipped -> output `Step N -- <skip reason>`, then proceed to the next step

---

## Step 0A -- Contract/native integration gate

Before generating trimmed configs, inspect `generated_files`, `example_pretrain_script`, `model_spec_path`, and optional `reference_contract_path`.

If `implementation_contract.required_integration_level` is `framework_native` or `framework_extension`, verify:
- generated Python files are normal LoongForge/Megatron model/config/layer-spec/provider files, not an isolated standalone runner;
- the generated example script invokes the real LoongForge training entrypoint and normal model registry/factory path;
- model registration/config mapping is present in the generated files or expected registry files;
- no generated artifact bypasses LoongForge/Megatron assembly to satisfy only the verifier;
- Phase 1 strategy metadata, when available, records `contract_preflight_passed: true`, `all_required_components_framework_native: true`, and `no_self_contained_fallback: true`.

If this gate fails, return `human_needed` with `failure_gate="non_native_phase1_implementation"`, `fallback_phase="phase1"`, and evidence listing the offending file/script. Do not continue to shared-seed loss comparison because a numerically matching standalone shim does not satisfy a native integration contract.

If no implementation contract exists, or the contract explicitly allows `standalone_reference`, record the gate as `skipped` or `passed` with the reason and continue.

### 0A.1 -- Reference-patchset migration gate (model-specific)

When the model entry in `knowledge_base/sources/...` declares `migration.required: true`, Phase 1 must additionally run the model's deterministic migration verifier before shared-seed smoke. This catches migrations that drop required Omni files, leak model-specific code into Megatron, or fail to register the new family.

Invoke the verifier named in the source YAML's `validation.verifier_script` against both reference and target trees, writing its report to `<run_dir>/phases/phase1/<family>_migration_report.json`. The verifier must report `validator.status=passed`. Treat any failure as `failure_gate="reference_patchset_migration_invariants"` with `fallback_phase="phase1"` and stop before Step 0B; do not paper over leaked Megatron strings or missing Omni files with shared-seed runs.

---

## Step 0B -- HF Sanity Run

Before generating trimmed configs, verify that the HF model can actually execute a forward pass and produce finite loss. This catches broken HF checkpoints, missing dependencies, and config mismatches early -- before spending time on LoongForge alignment.

Procedure:
1. Load the HF model using `transformers.AutoModelForCausalLM.from_pretrained(slice_hf_ckpt_path)`.
2. Create fixed input:
   ```python
   input_ids = torch.arange(100, 100 + 128, dtype=torch.long).unsqueeze(0)
   attention_mask = torch.ones(1, 128, dtype=torch.long)
   ```
3. Run forward pass: `outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=input_ids)`.
4. Verify `outputs.loss` is finite (not NaN, not Inf).
5. Record `hf_sanity_run_passed: true|false` and `hf_sanity_loss: float|null`.

If HF sanity run fails:
- Return `human_needed` with `failure_gate="hf_sanity_run_failed"`, `fallback_phase="phase1"`, and evidence including the exception traceback or loss value.
- Do not continue to Step 0 or later steps -- a broken HF model makes all downstream comparison meaningless.

If HF sanity run passes:
- Record the result and proceed to Step 0.

---

## Step 0 -- Generate trimmed configs

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

## Step 1 -- Resolve HF training interface

Read `hf_modeling_path` and determine whether HF can compute training loss directly:
- If the HF model class defines `compute_loss` or returns `loss` when `labels` are passed, use the native HF path.
- Otherwise generate `<run_dir>/phases/phase1/hf_train_verify.py` that wraps model outputs with standard causal-LM `CrossEntropyLoss`.

Generated HF wrapper must implement the same label shift and ignore-index semantics recorded in Step 2. If the semantics cannot be confirmed from HF source, output `human_needed: HF loss semantics unclear`.

---

## Step 2 -- Build and verify training parameter alignment

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

### Input Tensor Fixation

All input tensors MUST be fixed and identical on both HF and LoongForge sides. Write an `input_tensor_fixation` block into `phase1_alignment.json`:

```json
{
  "input_tensor_fixation": {
    "input_ids": {
      "constructor": "torch.arange(100, 100 + seq_len, dtype=torch.long).unsqueeze(0)",
      "shape": [1, 128],
      "description": "Deterministic token IDs starting from 100"
    },
    "attention_mask": {
      "constructor": "torch.ones(1, seq_len, dtype=torch.long)",
      "shape": [1, 128],
      "description": "Full attention mask (no padding)"
    },
    "position_ids": {
      "constructor": "torch.arange(seq_len, dtype=torch.long).unsqueeze(0)",
      "shape": [1, 128],
      "description": "Sequential position IDs starting from 0"
    },
    "labels": {
      "constructor": "input_ids.clone()",
      "shape": [1, 128],
      "description": "Labels match input_ids unless loss semantics require shifted labels internally"
    }
  }
}
```

The PHASE1_VERIFY hook in the generated LoongForge model MUST fix ALL four tensors (input_ids, attention_mask, position_ids, labels) -- not just input_ids. When `OMNI_PHASE1_VERIFY` is set:
- `input_ids = torch.arange(100, 100 + input_ids.shape[-1], dtype=torch.long, device=input_ids.device).unsqueeze(0)`
- `attention_mask = torch.ones(1, input_ids.shape[-1], dtype=torch.long, device=input_ids.device)`
- `position_ids = torch.arange(input_ids.shape[-1], dtype=torch.long, device=input_ids.device).unsqueeze(0)`
- `labels = input_ids.clone()` (unless loss semantics require shifted labels internally)

If any field cannot be matched or verified, stop and return `human_needed: Phase 1 HF/LoongForge training parameter alignment incomplete` with `alignment_mismatches` listing the fields. If a difference is intentional because the frameworks expose different names for the same behavior, record the mapping in `phase1_alignment.json` and continue.

---

## Step 3 -- Forward sanity comparison (shared-seed initialization)

Copy `example_pretrain_script` into `<run_dir>/phases/phase1/` and modify only the copy for trimmed shared-seed verification. Preserve the original `examples/<model>/` script unchanged. The copied script is the LoongForge execution entry for this verification.

### Shared-Seed Initialization Procedure

Instead of independent random initialization, use shared-seed initialization so both models have IDENTICAL parameters. Differences in loss then reflect only architecture discrepancies, not initialization noise.

1. **Initialize HF model with fixed seed**: Set `torch.manual_seed(42)`, load HF model with trimmed config, verify all parameters are deterministic.
2. **Dump all HF parameters**: Save `hf_model.state_dict()` to `<run_dir>/phases/phase1/hf_state_dict.pt`.
3. **Create LoongForge model with trimmed config**: Initialize using the trimmed LoongForge config from Step 0.
4. **Map each HF parameter to LoongForge parameter**: Use `weight_map` from `bridge_mapping.yaml` (component_bridge entries) to find the corresponding LoongForge parameter name for each HF parameter. Load the bridge_mapping file and iterate over component_bridge entries.
5. **Set LoongForge parameters from HF parameters**: For each mapped parameter pair, copy the HF parameter tensor to the LoongForge model parameter using `loongforge_model.load_state_dict(mapped_state_dict, strict=False)` or direct parameter assignment.
6. **Verify parameter identity**: Both models now have IDENTICAL parameters for all mapped components.

### Gap Component Handling

For gap components where `weight_map` is `null` in bridge_mapping.yaml (i.e., components that have no Megatron equivalent -- they are new modules without LoongForge counterparts), skip parameter mapping entirely. These components CANNOT participate in loss comparison because they have no corresponding LoongForge parameters. The verification report MUST explicitly list:
- Which components were skipped
- Why they were skipped (weight_map is null -- gap component with no LoongForge equivalent)
- The parameter count delta attributable to skipped components

The parameter count delta reported in the verification output must explicitly list which components were skipped and why. Example:

```json
{
  "skipped_gap_components": [
    {
      "component": "compressor",
      "reason": "weight_map is null in bridge_mapping -- gap component with no LoongForge equivalent",
      "hf_parameter_count": 65536
    }
  ],
  "total_hf_parameters": 1234567,
  "total_loongforge_parameters": 1169031,
  "delta_from_skipped_components": 65536
}
```

### Forward Comparison

Use fixed input (all four tensors from Step 2 input_tensor_fixation):
- `input_ids = arange(100, 100 + seq_len)` where `seq_len = 128`
- `attention_mask = ones(1, seq_len)`
- `position_ids = arange(seq_len).unsqueeze(0)`
- `labels = input_ids.clone()` unless loss semantics require shifted labels internally
- `seed = 42`

Run HF and LoongForge with the trimmed configs and aligned parameters from Step 2. LoongForge may use `OMNI_PHASE1_VERIFY=1` to activate Phase 1 debug hooks (which fix all four input tensors).

Pass condition:

```text
abs(hf_loss - omni_loss) < 1e-3
```

The tolerance is tighter than the previous 1e-2 because shared-seed initialization eliminates initialization noise. Both models start from identical parameters; any remaining loss difference reflects genuine architecture discrepancies.

Failure enters Step 5. Do not run Phase 3 real-weight loss-diff here.

---

## Step 4 -- Trainability verification

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

## Step 5 -- Failure diagnosis

For Step 3 forward mismatch:
1. Compare `phase1_alignment.json` first; do not debug model code until alignment is confirmed.
2. Use Phase 1 forward hooks from `knowledge_base/recipes/forward_debug.md` to locate the first divergent component.
3. Check generated `_config.py`, `_layer_spec.py`, `_model.py`, and YAML field mappings against `model_spec.yaml` and `bridge_mapping.yaml`.
4. After fixes, rerun the Phase 1 Agent's linter and L0 smoke test when generated Python files changed.

For Step 4 trainability failure:
1. Check loss semantics and label shift.
2. Check `requires_grad`, optimizer parameter groups, gradient flow, and parameter update.
3. Check train/eval mode, dropout, precision flags, and gradient clipping.

Write failure diagnosis into `<run_dir>/phases/phase1/phase1_verify_report.json`. The Phase 1 Agent owns retry policy and decides whether to archive persistent failure patterns under `knowledge_base/failure_patterns/phase1/` after repeated unresolved failures.

---

## Step 6 -- Write phase1_verify_report.json

Write `<run_dir>/phases/phase1/phase1_verify_report.json` and return this JSON to the Phase 1 Agent:

```json
{
  "status": "passed|failed|human_needed",
  "summary": "Phase 1 network sanity verification result",
  "failed_at_step": null,
  "root_cause": null,
  "step_trace": [
    {"step": "0A", "name": "Contract/native integration gate", "status": "passed|skipped|human_needed", "note": "..."},
    {"step": "0B", "name": "HF Sanity Run", "status": "passed|failed|human_needed", "note": "..."},
    {"step": 0, "name": "Generate trimmed configs", "status": "passed|failed", "note": "..."},
    {"step": 1, "name": "Resolve HF training interface", "status": "passed|failed|human_needed", "note": "..."},
    {"step": 2, "name": "Build and verify training parameter alignment", "status": "passed|human_needed", "note": "..."},
    {"step": 3, "name": "Forward sanity comparison (shared-seed initialization)", "status": "passed|failed|human_needed", "note": "..."},
    {"step": 4, "name": "Trainability verification", "status": "passed|failed|human_needed", "note": "..."},
    {"step": 5, "name": "Failure diagnosis", "status": "passed|skipped|human_needed", "note": "..."},
    {"step": 6, "name": "Write phase1_verify_report.json", "status": "passed|failed", "note": "..."},
    {"step": "6.5", "name": "Example Script Dry Run", "status": "passed|failed|human_needed", "note": "..."}
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
    "hf_sanity_run_passed": true,
    "hf_sanity_loss": 10.123,
    "example_script_dry_run_passed": true,
    "input_tensor_fixation": {
      "input_ids": "arange(100, 100+seq_len)",
      "attention_mask": "ones(1, seq_len)",
      "position_ids": "arange(seq_len).unsqueeze(0)",
      "labels": "input_ids.clone()"
    },
    "shared_seed_initialization": {
      "seed": 42,
      "hf_parameters_dumped": true,
      "loongforge_parameters_set": true,
      "skipped_gap_components": [],
      "parameter_count_delta_from_skipped": 0
    },
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
        "parameter_update_verified": true,
        "hf_sanity_run_passed": true,
        "example_script_dry_run_passed": true
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

---

## Step 6.5 -- Example Script Dry Run

After the forward comparison passes (Step 3) and the report is written (Step 6), verify that the generated example script is actually executable. This catches shell syntax errors, incorrect path references, missing model imports, and broken training loop configurations before Phase 2.

Procedure:
1. Locate the original generated example script from `generated_files` (the `examples/<model>/pretrain/*.sh` script).
2. Run the script with dry-run flags: `--train-iters 0 --no-load-optim`.
3. Verify:
   - Bash syntax is valid (script parses without error)
   - All path references are correct (model config YAML path, data path, tokenizer path)
   - Model can be imported and instantiated (no ImportError or ModuleNotFoundError)
   - Training loop starts (even if it runs 0 iterations, the initialization should succeed)
4. Record `example_script_dry_run_passed: true|false`.

If the dry run fails:
- Return `human_needed` with `failure_gate="example_script_dry_run_failed"`, `fallback_phase="phase1"`, and evidence including the error output.
- Common failure modes: incorrect `--model` flag value, missing `MODEL_CONFIG` environment variable, wrong config YAML path in the script, import errors from missing model registration.

If the dry run passes:
- Record the result. The Phase 1 verification is now complete with all steps passing.

Note: This step requires GPU or at minimum a CPU-mode execution environment. When no GPU is available, run with `--use-cpu` or equivalent flag. If neither GPU nor CPU execution is possible, record `example_script_dry_run_passed: null` with a note explaining the environment limitation.
