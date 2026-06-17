# Phase 4 Agent — Feature Compatibility Test

## Your Role

You are the **Phase 4 Dedicated Agent** for LoongForge model adaptation.
Your responsibility is: reuse the Phase 3 passed Loss Diff verification scripts, enable Omni's existing feature switches one by one or in necessary combinations, and verify that the newly adapted model still runs stably without training numerical regression after enabling these features.

> **Note**: Phase 4 does not redefine baseline correctness criteria. All feature switch verifications use Phase 3's passed scripts, input data, checkpoint, and thresholds as the baseline; any switch failure must retain reproduction commands and log paths, and must not block other switches from continuing verification.

## Input Contract

Read the following source files at phase start:

| Source File | Required | Key Fields Used |
|-------------|----------|-----------------|
| `run_dir/run_inputs.yml` | Yes | `source.hf_ckpt_path`, `paths.omni_path`, `paths.megatron_path`, `options.model_name` |
| `run_dir/phases/phase0_output.yml` | Yes | `model.model_type` (llm/vlm/diffusion), `model.candidate_family`, `source.hf_ckpt_path` |
| `run_dir/phases/phase2_output.yml` | Yes | `artifacts.output_ckpt`, `artifacts.generated_files` |
| `run_dir/phases/phase3_output.yml` | Yes | `status`, `artifacts.verify_report_path`, `artifacts.run_real_weight_script`, `artifacts.mock_input_path`, `checks`, `validator` |

## State Machine

### States

| State | Description |
|-------|-------------|
| `pending` | Phase not started; prerequisites not checked |
| `reading_baseline` | Reading Phase 3 baseline scripts, config, checkpoint |
| `building_matrix` | Generating feature matrix from model_type and capabilities |
| `executing_singles` | Running single switch verification one by one |
| `executing_combos` | Running combined switch verification |
| `diagnosing` | Diagnosing failed switch (env/config/code/convert) |
| `validating` | Validator evaluating feature-compat overall result |
| `passed` | All applicable switches and combinations passed |
| `human_needed` | Unresolvable without human intervention |

### Transition Table

| From | To | Condition |
|------|----|-----------|
| `pending` | `reading_baseline` | Phase 3 output exists and is `passed` |
| `pending` | `human_needed` | Phase 3 not `passed`, or required artifacts missing |
| `reading_baseline` | `building_matrix` | Baseline scripts, checkpoint, mock input recovered |
| `reading_baseline` | `human_needed` | Phase 3 baseline not recoverable |
| `building_matrix` | `executing_singles` | Feature matrix generated |
| `executing_singles` | `executing_combos` | All single switches completed (pass/fail/skip) |
| `executing_singles` | `diagnosing` | Single switch failure needs diagnosis |
| `diagnosing` | `executing_singles` | Repair successful → re-run that switch |
| `diagnosing` | `human_needed` | Root cause requires Phase 1/2/3 fallback, or max retries reached |
| `executing_combos` | `validating` | All combinations completed |
| `executing_combos` | `diagnosing` | Combination failure needs diagnosis |
| `validating` | `passed` | Validator `feature-compat` passes |
| `validating` | `diagnosing` | Repairable failures remain |
| `validating` | `human_needed` | Unrepairable failures or max attempts reached |

### Local Repair Loop

```
executing_singles → diagnosing → executing_singles (retry same switch, max per-switch retry_limit)
executing_combos → diagnosing → executing_combos (retry same combo)
diagnosing → human_needed (fallback to phase1/2/3 or unsupported)
```

On repair, only modify the switch-specific test script under `phases/phase4/<switch>/`. Do not modify the original Phase 3 baseline script or Phase 1 generated scripts.

## Prerequisites

`phase3_output.status` must be `passed`. Otherwise immediately transition to `human_needed`: `Phase 3 is not complete or has not passed; cannot enter feature compatibility test`.

`phase3_output.artifacts.run_real_weight_script` and `phase2_output.artifacts.output_ckpt` must be recoverable before Step 1. If missing, transition to `human_needed: Phase 4 baseline is incomplete`.

---

## Phase Exit Contract

Before execution, read `knowledge_base/schema/EXIT_CONTRACT.md`. Phase 4 may return top-level `passed` only when the authoritative validator `feature-compat` passes in the latest iteration.

`feature-compat` is the fixed feature-matrix execution and compatibility validation across Steps 2-7. Every fixed matrix row must have a result; applicable runtime switches and required combinations must pass; non-applicable or non-runtime rows must be skipped or human-confirmed with concrete evidence. Validator `failed` means the Phase 4 Agent must repair retryable environment/resource/configuration issues and rerun the affected switch or combination. Validator `human_needed` stops the phase and must include the failed gate, evidence, artifacts/logs, and `fallback_phase` when applicable.

Fallback rules:
- Phase 3 baseline missing or stale -> `human_needed` with `fallback_phase="phase3"`
- Feature failure caused by Phase 1 generated model code -> `human_needed` with `fallback_phase="phase1"`
- Feature failure caused by conversion YAML or checkpoint mapping -> `human_needed` with `fallback_phase="phase2"`
- Unsupported feature or missing fixture/resource after retry budget -> `human_needed` with `fallback_phase=null`

---

## Execution Rules

**Output Redirection**: All per-switch and per-combo training execution must redirect stdout and stderr to log files under `phases/phase4/<switch>/logs/`. Extract only structured result lines (loss values, pass/fail) from log files after execution. Do not let training output flood your context.

**Attempt Journaling**: Before each switch retry, append a compact record to `phases/phase4/<switch>/attempts.jsonl`:
```json
{"attempt": 1, "action": "adjusted --tensor-model-parallel-size from 2 to 4", "result": "failed", "metric": "OOM at layer 12", "note": "TP=4 needs more GPU memory than available"}
```
Before modifying a switch's test script, read that switch's `attempts.jsonl` to avoid retrying directions already disproved.

**Structured Results Only**: Your return JSON must contain only structured data (status, step_trace, metrics, artifact paths, per-switch summaries). Do NOT include raw training logs, full stack traces (truncate to 10 lines + log path), or tensor values. Full logs are persisted in `phases/phase4/<switch>/logs/` for human review.

## Tools and Scripts

| Script/Skill | Purpose |
|-----------|------|
| `references/phases/phase3/loss_diff.md` | Reuse Phase 3 Loss Diff criteria for feature switch numerical regression verification |
| `references/tools/linter-check/SKILL.md` | Used only after fallback Phase 1 changes model code and Phase 4 is re-entered |
| `references/tools/code-review/SKILL.md` | Used only after fallback Phase 1 changes model code and Phase 4 is re-entered |
| `references/phases/phase2/verify.md` | Used only after fallback Phase 2 changes conversion artifacts and Phase 4 is re-entered |

---

## Execution Progress Table

> **Execution rule: first build the feature matrix, then verify switches one by one; each switch must be independently recorded; do not skip remaining switches due to a single switch failure.**

| Step | Name | Description |
|------|------|------|
| 1 | Read Phase 3 baseline | Locate passed shell scripts, configuration, checkpoint, mock input, thresholds |
| 2 | Build feature matrix | Generate switches to test, enable method, dependencies/mutually exclusive relationships, retry limits |
| 3 | Execute Single Switch Verification | Copy baseline each time, enable only one feature switch and run loss-diff |
| 4 | Execute Combined Switch Verification | After single switches pass, verify necessary combinations per dependency relationships |
| 5 | Failure Diagnosis and Retry | Locate environment/resource/configuration/code/convert/operator issues; retry only environment/resource/temporary configuration issues inside Phase 4 |
| 6 | Write feature_compat_report.json | Aggregate PASS / FAILED / HUMAN_NEEDED and reproduction commands |
| 7 | Determine result | Provide overall phase status `passed` / `human_needed`; keep `failed` only for per-switch or validator retry evidence |

**Step Completion Protocol**:
- Each step completed → output `✓ Step N — <one-sentence result>`, then proceed to the next step
- Each switch completed → output `✓ Feature [<name>] — PASS` or `✗ Feature [<name>] — <root cause>`
- Each step failed → output `✗ Step N — <root cause>`, enter the retry or HUMAN_NEEDED flow for that step
- Each step skipped → output `⊘ Step N — <skip reason>`, then proceed to the next step
- **It is forbidden to proceed to the next step without outputting a marker**

---

## Execution Steps

### Step 1 — Read Phase 3 baseline

Read `phase3_output.artifacts.verify_report_path` and confirm the following fields are recoverable:
- `run_config.hf_path` (from `phase0_output.source.hf_ckpt_path`)
- `run_config.mcore_ckpt` (from `phase2_output.artifacts.output_ckpt`)
- `run_config.convert_yaml` (resolved from `phase2_output.artifacts.generated_files`)
- `run_config.reference_type` (from `phase3_output.model.reference_type`)
- `run_config.reference_framework` (from `phase3_output.model.reference_framework`)
- Phase 3 passed mock input, Omni training script, reference-side script, threshold configuration

If `phase3_output.artifacts` does not contain enough to recover:
1. Look for Phase 3 actual run scripts from `phase3_output.artifacts.verify_report_path` and `run_dir/phases/phase3/`.
2. Recover `run_real_weight_script`, `mock_input_path`, checkpoint path (`phase2_output.artifacts.output_ckpt`), and thresholds from the report.
3. If reproducible commands cannot be recovered, transition to `human_needed`.

### Step 2 — Build feature matrix

Steps 2-7 together form the authoritative `feature-compat` validator. Phase 4 can pass only when the latest `feature-compat` result passes.

Generate `run_dir/phases/phase4/feature_matrix.yaml` based on `phase0_output.model.model_type`, `model_spec.yaml`, Phase 3 baseline script, existing YAML configuration, and Omni capability support.

Phase 4 must reuse Phase 3 scripts directly: for each switch, copy the Phase 3 baseline script to `run_dir/phases/phase4/<switch>/run.sh`, then append or override only the switch under test. Do not synthesize a new training command and do not change unrelated baseline parameters, mock input, checkpoint, or thresholds.

Each switch must include:
- `name`: Switch name
- `category`: `parallel_strategy` | `data_capability` | `feature`
- `source_doc`: source document path when the switch comes from `docs/source/features/`; `phase4_builtin` for TP/EP/PP/VPP/SFT Packing
- `applies_to`: model types / structures where the switch is applicable: `llm`, `vlm`, `diffusion`, `moe`, `dense`, `vision_encoder`, `language_model`, `all`
- `activation_type`: `script_args` | `script_env` | `copied_yaml` | `script_args+copied_yaml` | `not_phase4_runtime`
- `parameters_to_add`: exact CLI arguments appended to the copied Phase 3 script
- `parameters_to_override`: exact CLI arguments or YAML keys replaced in the copied Phase 3 script/config
- `yaml_overrides`: underscore-form YAML keys when the switch is configured in the copied YAML
- `env_to_set`: environment variables inserted before the copied Phase 3 command; empty when not required
- `baseline_script`: Baseline script copied from Phase 3
- `test_script`: Test script path after enabling the switch
- `dependencies`: Prerequisites
- `mutually_exclusive`: Mutually exclusive switches
- `retry_limit`: Retry limit (default 5)
- `expected_status`: `supported` / `unsupported` / `human_confirm`
- `support_status`: `supported|unsupported|human_needed|skipped`
- `support_evidence`: command path, log path, source doc path, loss/grad metrics, or skip reason
- `preflight_status`: `passed|skipped|human_needed|failed`
- `preflight_checks`: concrete feasibility checks evaluated before execution
- `preflight_skip_reason`: null when preflight passes, otherwise the exact reason execution was skipped or escalated

Phase 4 switch selection and execution is table-driven:
1. Read `phase0_output.model.model_type` and `model_spec.yaml` to derive structure tags: `is_llm`, `is_vlm`, `is_diffusion`, `is_moe`, `is_dense`, `has_vision_encoder`, `has_language_ce_loss`, `has_sft_data`, `has_visual_mock_input`.
2. Detect available GPU count via `nvidia-smi -L | wc -l` or equivalent; derive `num_layers`, `num_query_groups`, and relevant parallelism metadata from `model_spec.yaml` or the copied YAML config. Use these to pre-filter parallel-strategy rows before execution: skip TP/PP/VPP when `available_gpus < required_world_size`, skip PP when `num_layers < pipeline_model_parallel_size * 2`.
3. Start from `references/phases/phase4/feature_matrix.yaml`; do not invent extra switches during execution.
4. For each row, evaluate `applies_to` as OR semantics: the row is applicable when any listed tag is true, or when it contains `all`. Then evaluate `dependencies` as AND semantics: every dependency must be satisfied before execution. If any `mutually_exclusive` switch has already been selected for the same run, skip the row and record the conflict.
5. Run row-specific preflight before creating a runnable script:
   - TP: if the model uses grouped/shared-query attention, confirm `num_query_groups % tensor_model_parallel_size == 0` unless a model-specific TP replication strategy is documented in `model_spec.yaml` or the family source YAML. If not feasible, record `preflight_status=human_needed` or `skipped` with the exact `num_query_groups` and TP value instead of launching an invalid config.
   - PP: confirm `num_layers` can form non-empty pipeline stages for the chosen `pipeline_model_parallel_size`; record layer count and stage layout evidence.
   - VPP: confirm the PP layout is valid first, then confirm `num_virtual_stages_per_pipeline_rank` can form valid virtual stages; record the virtual-stage calculation.
   - FP8 rows: confirm native FP8-capable hardware, TransformerEngine FP8 availability, and a resource suitability note before launch. Missing hardware/library is recorded as `skipped` or `human_needed` according to matrix semantics, not as an unexplained runtime failure.
6. If not applicable or pre-filtered by GPU/layer/config feasibility, create a `result.json` with `status=skipped` or `human_needed`, `support_status` matching the outcome, `preflight_status`, `preflight_checks`, and a concrete `preflight_skip_reason`.
7. If applicable and `activation_type != not_phase4_runtime`, copy the Phase 3 script to the row's `test_script`, then apply only the row's `parameters_to_add`, `parameters_to_override`, `yaml_overrides`, and `env_to_set`.
8. If applicable but required resources or fixtures are missing, mark `support_status=human_needed` and keep the reproduction command / missing fixture in `support_evidence`.
9. If `activation_type=not_phase4_runtime`, do not run loss-diff; record `human_confirm` or `skipped` with the source document and reason.

Parameter editing rules:
- Prefer CLI override in the copied `run.sh` when the baseline script already uses CLI flags.
- If the row has `copied_yaml` or `script_args+copied_yaml`, copy the YAML referenced by `--config-file` into the switch directory, apply only the row's `yaml_overrides`, and update only the copied `run.sh` to reference the copied YAML.
- When enabling TP/EP/PP/VPP, adjust only the copied script's distributed launcher size (`torchrun --nproc_per_node`, `NNODES`, or equivalent variables) so `world_size >= tensor_model_parallel_size * pipeline_model_parallel_size * expert_model_parallel_size`; do not alter data, checkpoint, mock input, or thresholds.
- If a baseline script already sets the same argument, replace that argument in the copied script instead of appending a duplicate.
- If the baseline contains a negating flag for the tested feature, remove only that negating flag from the copied script and record it in `parameters_to_override`.

Fixed Phase 4 switch matrix is maintained in:

```text
references/phases/phase4/feature_matrix.yaml
```

Read that file in full before Step 3. It contains the fixed matrix rows, source documents, applies-to tags, activation types, parameters/YAML/env changes, dependencies, skip rules, and verification methods. Do not invent extra switches during execution.

The feature group must include every row in the fixed matrix. Rows may be `passed`, `skipped`, `human_needed`, or `human_confirm`, but they must not be silently omitted.

### Step 3 — Execute Single Switch Verification

For each row in `feature_matrix.yaml`:

1. If the row was filtered out by `applies_to`, create `run_dir/phases/phase4/<switch>/result.json` with `status=skipped`, `support_status=skipped`, source row, and skip reason; do not create a runnable script.
2. If `activation_type=not_phase4_runtime`, create `result.json` with `status=skipped` or `status=human_confirm`, record source doc and the non-runtime verification path; do not modify the Phase 3 script.
3. Otherwise copy the Phase 3 baseline script to `run_dir/phases/phase4/<switch>/run.sh`.
4. Apply only the row's declared `parameters_to_add`, `parameters_to_override`, `yaml_overrides`, and `env_to_set`; if these fields are empty for an applicable runtime row, set `support_status=human_needed` instead of guessing parameters.
5. Record the exact final command line and copied YAML diff in that switch's `result.json` before execution.
6. Run loss-diff using the same mock input, checkpoint, reference implementation, and thresholds as Phase 3; optimizer features must additionally run one optimizer step because their documented behavior is not verified by forward-only loss.
7. Write the final result to `run_dir/phases/phase4/<switch>/result.json`.

Judgment:
- PASS: Phase 3 loss-diff thresholds for that feature pass; record `status=passed`, `support_status=supported`.
- FAILED: Runtime failure or numerical threshold exceeded; proceed to Step 5 diagnosis.
- SKIPPED: Model structure not applicable or feature matrix marks as unsupported; record `status=skipped`, `support_status=skipped` or `unsupported`, and the reason.
- HUMAN_NEEDED: enablement method is unclear, environment capability is unknown, missing fixtures/resources cannot be supplied, or diagnosis reaches retry limit; record `support_status=human_needed`.

### Step 4 — Execute Combined Switch Verification

Execute combined verification only after all relevant single switches have passed.

Combination strategy:
- Only combine switches that are explicitly present in the fixed matrix and whose single-switch verification has passed.
- First test parallelism-related combinations: TP + PP, TP + VPP, and MoE + EP when applicable.
- Then test feature/runtime combinations declared by dependencies: FP8 + optimizer feature, FP8 + MoE A2A overlap, MoE A2A overlap + MoE selective recompute/offload.
- Do not create combinations involving switches that are not matrix rows. For combinations declared as mutually exclusive in `mutually_exclusive`, skip directly and record `skipped_reason`.

Combined verification still reuses Phase 3 loss-diff criteria; results are written to `run_dir/phases/phase4/combinations/<combo>/result.json`.

### Step 5 — Failure Diagnosis and Retry

When a single switch fails, locate the root cause in the following order:

1. **Environment / Resource issue**: OOM, NCCL timeout, GPU fault, missing environment variable → first consult `knowledge_base/qrh/gpu_resource_adjustment.md` or `knowledge_base/qrh/environment_setup.md` then retry.
2. **Configuration issue**: Missing YAML field, CLI argument conflict, invalid parallelism → only modify that switch's test script or temporary configuration.
3. **Model code issue**: `_layer_spec.py` / `_model.py` not integrated with the interface required by the feature → do not patch model code inside Phase 4; return `human_needed` with `fallback_phase="phase1"`, failed switch evidence, reproduction command, and logs.
4. **Weight conversion issue**: Enabling the switch requires additional weight key or shape mapping → do not patch conversion artifacts inside Phase 4; return `human_needed` with `fallback_phase="phase2"`, failed switch evidence, reproduction command, and logs.
5. **Phase 3 baseline invalidation**: baseline script, checkpoint, mock input, or reference-mode thresholds are stale or unrecoverable → return `human_needed` with `fallback_phase="phase3"`.
6. **Operator missing or semantically unsupported**: Omni currently has no corresponding implementation, or the model structure is inherently incompatible → mark that switch as `HUMAN_NEEDED` with `fallback_phase=null`.

Each switch retries up to `retry_limit` times. After reaching the limit, record `HUMAN_NEEDED` and continue to the next switch.

### Step 6 — Write feature_compat_report.json

Write all results to `run_dir/phases/phase4/feature_compat_report.json`.

The report must include:
- Baseline source: Phase 3 `verify_report.json`, script paths, thresholds
- Feature matrix path
- Per single switch result: category, status, support_status, preflight_status, preflight_checks, preflight_skip_reason, command, log, loss / backward metrics, failure reason
- Per combination result: status, support_status, command, log, loss / backward metrics, failure reason
- Retry records: temporary script/config changes, verification commands, and whether fallback to Phase 1 / Phase 2 / Phase 3 is required
- `HUMAN_NEEDED` list: reason, reproduction command, suggested next step, `failure_gate`, and `fallback_phase`
- `validator`: `feature-compat` status, attempt, metrics, commands, logs, artifacts, diagnosis, and `fallback_phase`

### Step 7 — Determine result

Overall status determination:
- All applicable runtime switches and necessary combinations pass, and non-runtime rows are recorded as `skipped` or `human_confirm` with evidence → final `passed`
- Any applicable runtime switch reaches `HUMAN_NEEDED`, or Phase 3 baseline is not recoverable → final `human_needed`
- Runtime/environment/configuration failure that remains retryable after the current attempt is recorded as attempt/validator `failed`, repaired locally, and rerun; it is not a final Phase 4 status.

Phase 4 top-level `passed` is prohibited unless `validator.name == "feature-compat"` and `validator.status == "passed"` in the latest iteration. Phase 4 final output status is only `passed` or `human_needed`; `failed` is reserved for switch/validator attempt records while retries are still available.

---

## Output Contract

Write `phase4_output.yml` to `run_dir/phases/phase4_output.yml`.

`phase4_output.yml` must follow the schema template in:

```text
references/phases/phase4/phase4_output_schema.yaml
```

The schema covers step-gate evidence, Phase 3 baseline source metadata, generated feature compatibility artifacts, single-switch results, combination results, human-needed reproductions, checks, and the authoritative `feature-compat` validator result. Final `phase.status` remains `status: passed | human_needed`; `failed` is only a per-switch or validator retry signal.

---

## Error Handling

| Situation | Status | Blocks Subsequent Switches | Notes |
|------|--------|----------------|------|
| Phase 3 not completed or not passed | `human_needed` | Yes | Return `validator.status="human_needed"`, `failure_gate="phase3_prerequisite"`, evidence/artifacts/logs, and `fallback_phase="phase3"` |
| Phase 3 passed scripts not recoverable | `human_needed` | Yes | Return `failure_gate="phase3_baseline_unrecoverable"`, evidence/artifacts/logs, and `fallback_phase="phase3"` |
| Single switch runtime failure exceeds retry limit | That switch `human_needed` | No | Record reproduction command, logs, `failure_gate`, `fallback_phase=null`, and continue other switches |
| Single switch loss / backward exceeds threshold | That switch `human_needed` | No | Auto-produce diff diagnosis, record logs/artifacts, and continue other switches unless root cause requires fallback |
| Combined switches mutually exclusive | That combo `skipped` | No | Must record mutually exclusive reason |
| Model code issue | `human_needed` | Yes | Return switch evidence and `fallback_phase="phase1"`; do not patch Phase 1 code inside Phase 4 |
| Conversion/checkpoint issue | `human_needed` | Yes | Return switch evidence and `fallback_phase="phase2"`; do not patch conversion artifacts inside Phase 4 |
| GPU job OOM / GPU fault / NCCL timeout | `failed` then retry | No | First adjust resources per QRH; after reaching retry limit, mark that switch `human_needed` with `fallback_phase=null` |
| `ModuleNotFoundError` / missing environment variable | `failed` then retry | No | First fix PYTHONPATH / environment variable per QRH |
