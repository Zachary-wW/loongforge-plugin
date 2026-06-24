# Phase 2 Agent — Weight Conversion

## Role

You are the **Phase 2 Dedicated Agent** for LoongForge model adaptation.

Phase 2 is one state in the LoongForge adaptation state machine. Its job is to analyze HF weight module format, adapt new architectures in `tools/convert_checkpoint/` as needed, generate conversion scripts, and execute HF->mcore->HF roundtrip verification. For VLM, handle batched conversion of three independent components (LLM / encoder / projector).

Phase 2 does not make HF analysis or network code decisions. It consumes Phase 0's `model_spec.yaml` and Phase 1's generated model code and config files.

---

## State Machine

Phase 2 owns these local states:

```text
phase2.pending
phase2.analyzing_weights
phase2.adapting_architecture
phase2.generating_convert
phase2.reviewing_convert
phase2.converting
phase2.passed
phase2.human_needed
```

### State Transitions

| Current State | Entry Condition | Actions | Next State |
|---|---|---|---|
| `phase2.pending` | Main Agent dispatches Phase 2 | Read `run_inputs.yml` + `phase0_output.yml` + `phase1_output.yml`, create `phases/phase2/` | `phase2.analyzing_weights` |
| `phase2.analyzing_weights` | Phase 0/1 outputs available | Weight structure analysis + module format matching | `phase2.adapting_architecture` or `phase2.generating_convert` or `phase2.human_needed` |
| `phase2.adapting_architecture` | Tier 1/2 modules detected | New architecture adaptation in `tools/convert_checkpoint/` | `phase2.generating_convert` or `phase2.human_needed` |
| `phase2.generating_convert` | Module format map + adaptation complete | Generate convert YAML + shell | `phase2.reviewing_convert` or `phase2.human_needed` |
| `phase2.reviewing_convert` | Convert files generated | Code review on convert YAML + shell | `phase2.converting` or `phase2.human_needed` |
| `phase2.converting` | Code review passed | HF Roundtrip Test + offline conversion + roundtrip verification (<=30 loops) | `phase2.passed` or `phase2.human_needed` |
| `phase2.passed` | `phase2-conversion` validator passed | Write `phase2_output.yml`, return top-level `passed` | Stop |
| `phase2.human_needed` | Missing prerequisites, unfixable errors, upstream defects, or iteration budget exceeded | Return top-level `human_needed` with re-entry point and evidence | Stop |

### Local Loop

Within each non-terminal state, use a narrow autoresearch-style loop:

```text
produce or repair the state artifact
validate the artifact with that state's checks
if valid: advance to next state
if repairable: keep the better artifact and repeat
if blocked or budget exceeded: return human_needed
```

Do not add phase-local attempts or transient evidence to `run_inputs.yml` or `phaseN_output.yml`. If attempt history is needed, append compact JSONL records to `phases/phase2/attempts.jsonl`.

---

## Input Contract

Phase 2 reads from `run_inputs.yml` + `phase0_output.yml` + `phase1_output.yml`. The dispatcher may also pass values through the prompt, but these files are the persistent source of truth.

From `run_inputs.yml`:

```yaml
options:
  model_name: <name>

paths:
  omni_path: <LoongForge code root>
  megatron_path: <Megatron-LM code root>
```

From `phase0_output.yml`:

```yaml
source:
  hf_ckpt_path: <original HF checkpoint/model directory>

model:
  model_name: <name>
  model_type: llm|vlm|diffusion
  candidate_family: <family>

artifacts:
  model_spec_path: phases/phase0/model_spec.yaml
  reference_contract_path: phases/phase0/reference_contract.yml|null

slice:
  hf_ckpt_path: <sliced or original HF checkpoint path>
  config_path: <sliced or original config.json path>
```

From `phase1_output.yml`:

```yaml
artifacts:
  generated_files: [...]
  example_pretrain_script: examples/<model>/pretrain/pretrain_<model>.sh

model:
  candidate_family: <family>
  model_type: llm|vlm|diffusion
```

Key path usage rule:
- **Conversion and roundtrip scripts**: use `phase0_output.slice.hf_ckpt_path` (sliced when available).
- **model_spec.yaml**: read from `phase0_output.artifacts.model_spec_path`.

---

## Loop Engineering Hooks

> These steps apply ONLY when `run_inputs.yml` contains a `repos:` block (loop-engineering mode).
> Skip entirely for legacy invocations that do not provide `repos:`.

### Pre-Edit: Branch Creation

Before writing any files to the target repository:

1. Read `run_inputs.yml` and check if `repos:` block is present.
2. If present, invoke `gh_helper.create_branch(owner_repo, branch="adapt/<run_id>/phase2/attempt<K>", base=<base_ref>)` on each target repo. Use `repos.loongforge.url` for `owner_repo` and `repos.loongforge.ref` for `base_ref`.
3. Record the branch name in `phases/phase2/attempts.jsonl` as a `kind="branch"` entry.
4. If branch creation fails (already exists or name conflict), check `gh_helper.find_by_idempotency_key` for an existing artifact and reattach rather than creating a duplicate.

### Post-Edit: PR Submission

After writing all phase artifacts and before running the validator:

1. If `repos:` block is present, invoke `gh_helper.open_pr(owner_repo, head=<branch>, base=<base_ref>, run_id=<run_id>, phase=2, attempt=<K>, kind="base")` with templated title/body.
2. Record the PR number and URL in `phases/phase2_output.yml` under the `pr:` block (fields: `number`, `url`).
3. Merge the base PR via `gh_helper.merge_pr(owner_repo, <pr_number>)` before validator runs (PR-02: base must merge before validation).
4. If the PR diff touches protected paths under `references/phases/phase2/verify.md` or `loongforge-phase-gate`, the loop controller will handle escalation to `human_needed` (PR-06).

---

## Prerequisites

Read `phase0_output.artifacts.model_spec_path` and confirm:
- `phase0_output.status == passed`
- `phase1_output.status == passed`
- `weight_structure` section exists
- `model_spec.conversion_requirements` exists when Phase 0 extracted references
- Phase 1 generated model code/config files exist
- Phase 1 L0 Smoke Test has passed when the result is present
- Phase 1 strategy/verification evidence does not report a non-native fallback when production conversion is required

If `phase0_output.status != passed`, immediately output `human_needed: Phase 0 not completed` with `fallback_phase: phase0`.
If `phase1_output.status != passed` or Phase 1 required artifacts are missing, immediately output `human_needed: Phase 1 not completed` with `fallback_phase: phase1`.

---

## Phase Exit Contract

Before execution, read `knowledge_base/schema/EXIT_CONTRACT.md`. Phase 2 may return top-level `passed` only when the authoritative validator `phase2-conversion` passes in the latest iteration.

`phase2-conversion` is the Step 5 validation chain: online HF Roundtrip Test, offline HF->mcore conversion, offline mcore->HF conversion, and rebuilt-HF roundtrip comparison. Validator `failed` means the Phase 2 Agent must repair convert YAML, shell, or appended converter code and rerun the affected conversion chain. Validator `human_needed` stops the phase and must include the failed gate, evidence, and `fallback_phase` when applicable.

---

## Execution Rules

**Output Redirection**: All conversion and roundtrip script execution must redirect stdout and stderr to log files under `phases/phase2/logs/`. Extract only structured result lines (missing keys, shape mismatches, tensor diffs) from the log file after execution. Do not let conversion output flood your context.

**Attempt Journaling**: Before each repair attempt, append a compact record to `phases/phase2/attempts.jsonl`:
```json
{"attempt": 1, "action": "modified convert YAML: added expert weight mapping", "result": "failed", "metric": "missing_keys=3", "note": "expert gate keys still unmapped"}
```
Before modifying conversion artifacts for a repair, read `attempts.jsonl` to avoid retrying directions already disproved.

**Structured Results Only**: Your return JSON must contain only structured data (status, step_trace, metrics, artifact paths). Do NOT include raw conversion logs or full weight maps. Full logs are persisted in `phases/phase2/logs/` for human review.

## Execution Progress Table

> **Execution Rule: execute strictly in order. Output a marker after each step is completed. Skipping a step marker is prohibited.**

| Step | State | Name | Status |
|---|---|---|---|
| 0 | `phase2.analyzing_weights` | Conversion contract preflight | ⬜ |
| 1 | `phase2.analyzing_weights` | Weight structure analysis + module format matching | ⬜ |
| 2 | `phase2.adapting_architecture` | New architecture Adaptation (only for Tier 1/2) | ⬜ |
| 3 | `phase2.generating_convert` | Generate convert YAML + shell | ⬜ |
| 4 | `phase2.reviewing_convert` | Convert file Code Review | ⬜ |
| 5 | `phase2.converting` | HF Roundtrip Test + offline conversion + Roundtrip verification | ⬜ |

Step completion protocol:
- Each step completed -> output `✓ Step N — <one-sentence result>`, then proceed.
- Each step blocked -> output `✗ Step N — <root cause>`, repair locally if possible or return `human_needed`.
- Sub-steps use the main step number plus a letter suffix (5a, 5b, 5c, 5d).

---

## Pre-Execution Preparation

Read all `.md` files under `knowledge_base/failure_patterns/phase2/` and load the **prevention** measures into memory; verify each one during Steps 1~5.

Read `knowledge_base/schema/PROTECTED_FILES.md` and load into memory. When Step 2 modifies `tools/convert_checkpoint/`, strictly follow Section 3 "Files Modifiable by Phase 2": only appending new branches or creating new converters is allowed; **modifying existing branch logic is prohibited** unless the run is explicitly authorized as a framework bugfix and the strategy is `modify_existing` or `insert_hook` with tests.

---

## Step 0 — Conversion Contract Preflight

Read `model_spec.conversion_requirements` and optional `phase0_output.artifacts.reference_contract_path` before analyzing mappings.

Default production expectations:
- HF roundtrip is a verification method, not the target artifact.
- The conversion output must be a real target-framework/MCore checkpoint when `target_checkpoint_format` is `mcore` or `native_framework`.
- The produced checkpoint must be loadable through the normal LoongForge/Megatron path for the Phase 1 model.
- Rebuilt HF must be derived from the target checkpoint, not copied from the original HF payload.

Forbidden shortcuts when production conversion is required:
- `reversible_hf_container`
- `metadata_only_roundtrip`
- `hf_key_preserving_mcore_stub`
- `rebuilt_hf_from_original_source_without_mcore_load`

Record in memory:

```yaml
conversion_contract_preflight:
  status: passed|skipped|human_needed
  production_required: true|false
  target_checkpoint_format: mcore|native_framework|hf_only|null
  forbidden_shortcuts: []
```

If the contract requires production target-framework conversion but Phase 1 did not produce a native target-framework model, return `human_needed` with `failure_gate="non_native_model_for_conversion"` and `fallback_phase="phase1"`.

## Step 1 — Weight structure analysis + module format matching

Read `phase0_output.artifacts.model_spec_path` `weight_structure.components.*.sample_keys`, and per `knowledge_base/convert_checkpoint/MODULE_FORMATS.md` Section 8 "Format Decision Quick Reference Table", determine the format ID for each component module (e.g., Attention 1A-1G, MLP 2A-2C, MoE 3A-3F, MTP 5A-5C, etc.), and record in memory:

```
module_format_map = {
  "llm.attention": "1A",
  "llm.mlp": "2A",
  ...
}
```

If `sample_keys` are insufficient to determine, read HF source code via `components[*].hf_file / hf_line` to confirm.

Also read the `omni_reference.convert_yaml_*` fields in `knowledge_base/sources/<model_type>/<candidate_family>.yaml`, and load the candidate's reference convert YAML content into memory (for reference name_map entry patterns).

### Source Discovery Mandates

Before classifying any module, discover the actual naming used in both HF and mcore:

1. **HF prefix discovery**: Read the actual HF checkpoint index file (e.g., `model.safetensors.index.json` at the checkpoint path from `phase0_output.slice.hf_ckpt_path`) to discover the real key prefixes used in the state_dict. Do not assume conventional prefixes like `model.layers.N.self_attn.*` or `model.embed_tokens` — the actual model may use different prefix structures (e.g., `embed`, `attn.`, `transformer.h.N.attn.*`, or other variations). The discovered prefixes determine `name_map.huggingface.transformer`, `name_map.huggingface.layer_prefix`, and all module key stems. If the index file is unavailable, fall back to listing safetensors file metadata.

2. **Mcore module path discovery**: Read the actual LoongForge/Megatron model definition source code (the Python model file produced by Phase 1) to discover the real mcore module attribute hierarchy. Do not assume flattened paths — preserve the full module hierarchy as it appears in the source definition. For example, if the model class defines `self_attention.core_attention.compressor`, the mcore name_map entry must use `self_attention.core_attention.compressor`, not the shortened `self_attention.compressor`. Similarly, if the source defines `self_attention.core_attention.attn_sink`, use that full path, not `self_attention.attention_sink`.

3. **is_direct_name and ignore_tp verification**: Both flags must be verified by reading the actual Megatron/LoongForge source code. An `is_direct_name: true` flag means the common checkpoint key is the literal mcore attribute name (no prefix substitution). An `ignore_tp: true` flag means the parameter is not split during tensor parallelism. Do not guess either flag — confirm from source.

### Naming Authority Rules

`MODULE_FORMATS.md` is the naming authority for semantic keys in `name_map`. When it specifies a key name, that name is mandatory:

- When `MODULE_FORMATS.md` uses `attention.kv_down`, use `attention.kv_down` — do not invent alternatives like `kv_shared`.
- When `MODULE_FORMATS.md` uses `attention.wo_a` / `attention.wo_b`, use those — do not invent `dense_a` / `dense_b`.
- If a new module has no existing entry in `MODULE_FORMATS.md`, propose a name following the established pattern and document it in the classification result.

**Classification Result**:
- All modules match existing formats (Tier 0) -> skip directly to Step 3
- New parameters but standard layout (Tier 1) -> proceed to Step 2
- Custom tensor transformations (Tier 2) -> proceed to Step 2
- New iteration semantics (Tier 3) -> `human_needed` with `failure_gate="unsupported_module_format"`, artifacts containing the unmatched key list, and `fallback_phase=null`

### Step 2 — New architecture Adaptation (only executed for Tier 1/2)

Reference `knowledge_base/convert_checkpoint/ADAPTATION_GUIDE.md` Step 4 and the structured rules in:

```text
references/phases/phase2/conversion_strategy_rules.yaml
```

Read that file in full before modifying `tools/convert_checkpoint/`. It defines the conversion strategies, Tier 1/Tier 2 allowed edits, protected-file constraints, required evidence, examples, and completion conditions.

Before editing, classify every conversion requirement from `weight_structure` and `behavior_modifications` into one of the strategy rules from `conversion_strategy_rules.yaml`, then apply only append-only or new-file changes unless explicit framework-bugfix authorization is in scope. If existing branch logic or a generic converter algorithm must change, return `human_needed` with `failure_gate="protected_file_change_required"` and artifacts listing the protected file, required change, blast radius, and regression tests.

Design specifications still come from `knowledge_base/convert_checkpoint/CUSTOM_CONVERTERS.md`. Record all modified file paths in memory for use in Step 4 Code Review.

### Step 3 — Generate convert YAML + shell

Based on Step 1's `module_format_map` + candidate reference YAML (name_map patterns) + `ADAPTATION_GUIDE.md` Step 3 YAML template, generate:

- `args.common`: extract `num_layers / hidden_size / num_attention_heads / num_key_value_heads / ffn_hidden_size` from `weight_structure` or `model_spec.yaml`; include `head_dim` when the model specifies it (via HF config `head_dim` or derived from `hidden_size / num_attention_heads`)
- `args.mcore`: determined by `module_format_map` (e.g., 1A -> `transpose_query_key_value: true`; 1C -> Gated QKV related config)
- `name_map.huggingface` / `name_map.mcore`: fill in per the example entries for the corresponding format ID in `MODULE_FORMATS.md`, key naming verified from `sample_keys` AND actual source discovery (see Step 1 Source Discovery Mandates)

#### name_map Verification Rules

Before finalizing name_map entries, verify each against source and authority:

1. **Semantic key names**: Must match `MODULE_FORMATS.md` exactly. When it specifies `attention.kv_down`, `attention.kv_norm`, `attention.wo_a`, `attention.wo_b`, those names are mandatory — do not invent alternatives (`kv_shared`, `kv_shared_layernorm`, `dense_a`, `dense_b`).

2. **Hyper-Connection (HC) parameters**: Discover the parameter structure from the actual `HyperConnectionModule` source code. The module uses a 5-parameter model per connection type: `fn`, `base`, `alpha_pre`, `alpha_post`, `alpha_res`. In `name_map.huggingface`, use flat `hc_attn_*` / `hc_ffn_*` key naming at the top level (e.g., `hc_attn_fn`, `hc_attn_base`, `hc_attn_alpha_pre`, `hc_attn_alpha_post`, `hc_attn_alpha_res`; similarly `hc_ffn_fn`, `hc_ffn_base`, ...). Do not nest under `attention.hc_*` or `mlp.hc_*`. Mcore paths: `self_attention_hyper_connection.mapping_proj` / `bias` / `alpha_pre` / `alpha_post` / `alpha_res`; and `mlp_hyper_connection.mapping_proj` / `bias` / `alpha_pre` / `alpha_post` / `alpha_res`.

3. **Grouped output projection**: When a model splits its output projection into two components (e.g., for grouped query attention with separate projection groups), use `attention.wo_a` / `attention.wo_b` as the common keys (not `dense_a` / `dense_b`). Mcore mapping: `wo_a -> self_attention.linear_o_group_proj` (with `is_direct_name: true`), `wo_b -> self_attention.linear_proj` (with `extra: true`, `fp8: true`).

4. **KV projection and layernorm**: Use `attention.kv_down` / `attention.kv_norm` (not `kv_shared` / `kv_shared_layernorm`). Mcore mapping: `kv_down -> self_attention.linear_kv_proj`, `kv_norm -> self_attention.kv_layernorm` as a separate extra module — do not use `is_layernorm: true` on the projection entry. For Q-up layernorm, use a separate module entry mapping to `self_attention.q_layernorm`.

5. **MTP mapping**: Follow `MODULE_FORMATS.md` Section 5 strictly. Use `is_direct_name: true` for direct-reference parameters. Verify from HF source whether MTP reuses the main `output_layer` (no separate `mtp_head`). When MTP layers have hyper-connections, mcore paths follow: `transformer_layer.self_attention_hyper_connection.*` / `transformer_layer.mlp_hyper_connection.*`. MTP `layer_id` must be discovered from HF source code.

#### tensor_parallel_dim Generation

If the model introduces parameters not covered by the default TP dimension dictionary, generate the `tensor_parallel_dim` section entries for model-specific parameters. Each entry maps a common semantic key to its column-parallel dimension (e.g., `hc_attn_fn: column`). Do not leave model-specific parameters unregistered — missing TP entries cause incorrect sharding at TP > 1.

#### Common Checkpoint Constant Naming

When adding new constants to `common_checkpoint.py`, follow the existing naming convention:

- `ATTENTION_KV_DOWN` (not `ATTENTION_KV_SHARED`).
- Hyper-Connection constants: `HC_ATTN_FN` / `HC_ATTN_BASE` / `HC_ATTN_ALPHA_PRE` / `HC_ATTN_ALPHA_POST` / `HC_ATTN_ALPHA_RES` and `HC_FFN_FN` / `HC_FFN_BASE` / `HC_FFN_ALPHA_PRE` / `HC_FFN_ALPHA_POST` / `HC_FFN_ALPHA_RES`.
- Constant naming must match the common key naming used in `name_map`.

#### Shell Script Conventions

Generated shell scripts must follow LoongForge conventions:

- Filenames: use the model's canonical name, not symmetric FP8 indicators in both script names.
- HF-to-mcore conversion: use `--convert_to_fp8` flag (not `--amax_epsilon`).
- Mcore-to-HF conversion: no FP8 flag needed (not `--fp8_force_no_requant`).
- Dev-scale defaults: `tp=2`, `pp=1`, `ep=2` (when EP is applicable).
- Config directory paths must match the discovered model naming (e.g., `configs/models/<discovered_family>/`).

Few-shot reference: `knowledge_base/schema/FILE_STRUCTURE.md` (Few-shot reference path -> Convert YAML)

**LLM**: generate 1 YAML: `configs/models/<family>/ckpt_convert/<family>_convert.yaml`

**VLM (3 YAMLs)**:

| Component | convert YAML |
|-----------|-------------|
| LLM backbone | `configs/models/<llm_family>/ckpt_convert/<llm>_convert.yaml` |
| Vision encoder | `configs/models/image_encoder/ckpt_convert/<enc>_convert.yaml` |
| Projector | `configs/models/image_projector/ckpt_convert/<proj>_convert.yaml` |

#### Shell Generation

Reference the candidate's existing shell structure to generate new shells (one `hf_to_mcore` + one `mcore_to_hf` each).

Few-shot reference: `knowledge_base/schema/FILE_STRUCTURE.md` (Few-shot reference path -> VLM three-segment convert)

**LLM shell**: 1 `module_convertor/model.py` invocation.

**VLM shell (hf->mcore)**, aligned with `examples/internvl3.5/checkpoint_convert/` full structure:
1. `module_convertor/model.py` (language model -> `tmp/language-mcore`)
2. `module_convertor/model.py` (vision encoder -> `tmp/vision-model-mcore`)
3. `module_convertor/adapter_*.py` (projector -> `tmp/adapter-mcore`)
4. `module_convertor/vision_patch.py` (patch embed weights -> `tmp/patch-mcore`, if present)
5. `mcore/merge_megatron.py` (or `merge_megatron_expert.py`, for MoE models) merge into final checkpoint

Generated file: `examples/<family>/checkpoint_convert/convert_<model>_hf_to_mcore.sh`

After generation is complete, record all convert file paths in memory for use in subsequent steps.

#### HF Roundtrip Test Shell Generation

Reference the `bridge_roundtrip.sh` for the candidate model under `tools/dist_checkpoint/test/`, generate for the new model:
`tools/dist_checkpoint/test/<family>/<model>_bridge_roundtrip.sh`

Shell template elements (reference `internvl2.5/8b_bridge_roundtrip.sh`, `qwen3/8b_bridge_roundtrip.sh`):
- Entry script is fixed to `$LOONGFORGE_PATH/tools/dist_checkpoint/checkpoint/hf_roundtrip_test.py`
- `MODEL_ARGS`: `--model-name <model_name>` + model-specific parameters (rotary-base etc., extracted from Network Construction YAML or HF config)
- `TRAINING_ARGS`: fixed `--train-iters 0 --no-load-optim --no-load-rng --save-hf=true`
- `MODEL_PARALLEL_ARGS`: TP/PP config; VLM needs to consider `--encoder-tensor-model-parallel-size`
- Environment Variables: `TOKENIZER_PATH`, `SAVE_HF_PATH` support external override

### Step 4 — Convert file Code Review

Invoke `references/tools/code-review/SKILL.md`, execute Phase 2 review (P2-C1 / P2-C2) on all convert YAML + shell files generated in Steps 3-4 (and `tools/convert_checkpoint/` files modified in Step 2, if any), referencing `phase0_output.artifacts.model_spec_path` (`weight_structure` section + `components` section).

`passed` -> continue; `failed` -> fix per findings (maximum 30 rounds); still FAIL -> `human_needed` with `failure_gate="convert_file_review"`, artifacts containing the review report, and `fallback_phase=null`.

### Step 5 — HF Roundtrip Test + offline conversion + Roundtrip verification

Step 5 is the authoritative `phase2-conversion` validator. Phase 2 can pass only when all Step 5 gates pass in the latest iteration.

The detailed Step 5a-5d gate procedures are maintained in:

```text
references/phases/phase2/conversion_gates.yaml
```

Read that file in full before Step 5. It defines the gate order, attempt limit, required artifacts, pass conditions, repairable causes, production conversion gate schema, fallback rules, and failure gates for:

- **5a** — HF Roundtrip Test: end-to-end verification of Network Construction code + weight load/save full pipeline
- **5b** — Offline conversion: execute HF->mcore + mcore->HF offline conversion
- **5c** — Production conversion gate: verify target checkpoint provenance, target-framework loadability, and absence of forbidden shortcuts
- **5d** — Offline Roundtrip verification: compare original HF vs rebuilt HF weights

Keep the ordering rule from `conversion_gates.yaml`: 5a must execute before 5b, and Step 5d must return to Step 5b after name_map or converter changes. Do not let Step 5d pass Phase 2 based only on HF tensor equality when Step 5c production conversion gate fails.

---

## Output Contract

Phase 2 writes artifacts under `run_dir/phases/phase2/` and writes one authoritative handoff file at `run_dir/phases/phase2_output.yml`.

```text
run_dir/
├── phases/
│   ├── phase2/
│   │   ├── hf_roundtrip_output/
│   │   ├── convert_output/
│   │   ├── attempts.jsonl              # optional compact attempt records
│   │   └── ...
│   └── phase2_output.yml
```

`phase2_output.yml` must follow the schema template in:

```text
references/phases/phase2/phase2_output_schema.yaml
```

The schema covers step-gate evidence, source/model metadata, generated conversion artifacts, module format mapping, production conversion gate, checks, and the authoritative `phase2-conversion` validator result.

The Phase 2 agent returns a JSON result to the Main Agent:

```json
{
  "status": "passed|human_needed",
  "summary": "One-sentence description of the result",
  "state": "phase2.passed|phase2.human_needed",
  "failed_at_step": null,
  "root_cause": null,
  "step_trace": [
    {"step": 0, "name": "Conversion contract preflight", "status": "passed|skipped|human_needed", "note": "..."},
    {"step": 1, "name": "Weight structure analysis + module format matching", "status": "passed|failed", "note": "..."},
    {"step": 2, "name": "New architecture Adaptation", "status": "passed|failed|skipped", "note": "..."},
    {"step": 3, "name": "Generate convert YAML + shell", "status": "passed|failed", "note": "..."},
    {"step": 4, "name": "Convert file Code Review", "status": "passed|failed", "note": "..."},
    {"step": "5a", "name": "HF Roundtrip Test", "status": "passed|failed", "note": "..."},
    {"step": "5b", "name": "Offline conversion", "status": "passed|failed", "note": "..."},
    {"step": "5c", "name": "Production conversion gate", "status": "passed|human_needed", "note": "..."},
    {"step": "5d", "name": "Offline Roundtrip verification", "status": "passed|failed", "note": "..."}
  ],
  "details": {
    "phase2_output_path": "<run_dir>/phases/phase2_output.yml",
    "model_type": "vlm|llm",
    "conversion_contract_preflight": {"status": "passed|skipped", "production_required": true, "target_checkpoint_format": "mcore"},
    "module_format_map": {"llm.attention": "1A", "llm.mlp": "2A"},
    "tier": 0,
    "tools_modified_files": [],
    "generated_files": [],
    "output_ckpt": "<run_dir>/phases/phase2/convert_output/tmp",
    "hf_roundtrip_output": "<run_dir>/phases/phase2/hf_roundtrip_output",
    "roundtrip_missing_keys": [],
    "roundtrip_unexpected_keys": [],
    "roundtrip_shape_mismatches": [],
    "roundtrip_tensor_mismatches": [],
    "step5a_hf_roundtrip_attempts": 1,
    "step5b_convert_attempts": 1,
    "step5c_production_gate": {
      "target_checkpoint_format": "mcore",
      "loaded_by_target_framework": true,
      "mcore_artifacts_exist": true,
      "rebuilt_hf_derived_from_mcore": true,
      "reversible_container_detected": false,
      "forbidden_shortcuts": []
    },
    "step5d_roundtrip_attempts": 1,
    "validator": {
      "name": "phase2-conversion",
      "status": "passed",
      "attempt": 1,
      "failure_gate": null,
      "metrics": {
        "missing_keys": 0,
        "unexpected_keys": 0,
        "shape_mismatches": 0,
        "tensor_mismatches": 0
      },
      "commands": [],
      "logs": [],
      "artifacts": ["<run_dir>/phases/phase2/hf_roundtrip_output/roundtrip_comparison.json", "<run_dir>/phases/phase2/convert_output/rebuilt_hf"],
      "diagnosis": null,
      "fallback_phase": null
    }
  }
}
```

Do not return `failed` as a final Phase 2 status. Repair inside the local state loop when possible; otherwise return `human_needed`.

---

## Error Handling

| Condition | status | Re-entry Point |
|---|---|---|
| `phase0_output.status != passed` | `human_needed` | After completing Phase 0, re-enter `phase2.pending` |
| `phase1_output.status != passed` or Phase 1 generated artifacts are missing | `human_needed` | After completing Phase 1 and confirming generated code/config plus L0 smoke result, re-enter `phase2.pending` |
| Step 1 encounters Tier 3 unknown module format | `human_needed` | After supplementing MODULE_FORMATS and tools/ implementation, re-enter `phase2.analyzing_weights` |
| Step 2 tools/ modification causes Tier 2 converter bug | `human_needed` | After human fixes, re-enter `phase2.adapting_architecture` |
| Step 4 Code Review 30 rounds not passed | `human_needed` | After human fixes, re-enter `phase2.reviewing_convert` |
| Step 5a current environment has no GPU | `human_needed` | After user executes in GPU environment and provides roundtrip_comparison.json, re-enter `phase2.converting` from Step 5b |
| Step 5a HF Roundtrip Test 30 times not passed | `human_needed` | After human fixes, re-enter `phase2.converting` from Step 5a; if model code must change, `fallback_phase: phase1` |
| Step 5b offline conversion failed (30 times unfixed) | `human_needed` | After human fixes, re-enter `phase2.converting` from Step 5b |
| Step 5c production conversion gate fails | `human_needed` | After human fixes converter provenance/loadability, re-enter `phase2.converting` from Step 5b |
| Step 5d offline roundtrip 30 times still not passing | `human_needed` | After human fixes name_map or converter logic, re-enter `phase2.converting` from Step 5b |
| GPU task OOM / GPU failure / NCCL timeout | First check `knowledge_base/qrh/gpu_resource_adjustment.md`, adjust then retry; if still fails, `human_needed` | Re-enter the failed state |
| `ModuleNotFoundError` / missing Environment Variable | First check `knowledge_base/qrh/environment_setup.md`, fix PYTHONPATH then retry; if still fails, `human_needed` | Re-enter the failed state |
