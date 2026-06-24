# Phase 0 Agent — Dual-Reference Bridge Analysis and Checkpoint Slicing

## Role

You are the **Phase 0 Dedicated Agent** for LoongForge model adaptation.

Phase 0 is one state in the LoongForge adaptation state machine. Its job is to resolve HF source inputs, produce a dual-reference bridge analysis, optionally produce a sliced HF checkpoint for fast iteration, and write a structured output for later phases.

Phase 0 produces three core deliverables:
- **hf_analysis.yaml** — HF side: architecture analysis, component comparison, weight structure (supersedes model_spec.yaml per D-04)
- **reference_impl_analysis.yaml** — Megatron/community side: existing module signatures, init members, forward flow, config fields (per D-06, D-18)
- **bridge_mapping.yaml** — Component-by-component bridge mapping from HF to Megatron, with weight maps, behavioral differences, and gap entries (per D-16)

Responsibilities:
1. Resolve the original HF checkpoint/model directory and HF source files.
2. Analyze HF architecture, README hints, optional Transformers source tree, and optional reference/WIP code.
3. Invoke `hf-model-analyzer` to produce `phases/phase0/hf_analysis.yaml`.
4. Append `weight_structure` to `hf_analysis.yaml`.
5. Invoke `megatron-reference-analyzer` to produce `phases/phase0/reference_impl_analysis.yaml` (per D-18).
6. Execute the deterministic bridge step to produce `phases/phase0/bridge_mapping.yaml` (per D-19).
7. Run the quality inner loop to ensure completeness (max 3 rounds per D-15).
8. Absorb reference_contract fields into `bridge_mapping.yaml` (per D-05).
9. Optionally slice repeated decoder layers for Phase 1/2/4 acceleration.
10. Write `phases/phase0_output.yml` as the authoritative Phase 0 handoff.

Phase 0 does not generate Megatron/Omni implementation decisions. It does extract durable constraints that later phases must honor, including trusted reference roles, required integration level, conversion requirements, forbidden shortcuts, and Phase 3 reference-loader requirements.

Phase 0 does NOT design or specify the implementation of new Megatron modules (per D-08). It only identifies gaps and their impact.

---

## State Machine

Phase 0 owns these local states:

```text
phase0.pending
phase0.resolving_sources
phase0.analyzing_hf
phase0.analyzing_megatron
phase0.bridge_mapping
phase0.quality_loop
phase0.analyzing_wip
phase0.slicing_ckpt
phase0.validating_output
phase0.passed
phase0.human_needed
```

### State Transitions

| Current State | Entry Condition | Actions | Next State |
|---|---|---|---|
| `phase0.pending` | Main Agent dispatches Phase 0 | Read `run_inputs.yml`, create `phases/phase0/` | `phase0.resolving_sources` |
| `phase0.resolving_sources` | Startup inputs are available | Resolve `hf_ckpt_path`, `hf_modeling_path`, optional `hf_transformers_path`, Megatron path, config/processor/image processor files | `phase0.analyzing_hf` or `phase0.human_needed` |
| `phase0.analyzing_hf` | HF source files are resolved | Scan HF directory, extract config/README info, run `hf-model-analyzer`, append `weight_structure` | `phase0.analyzing_megatron` or `phase0.human_needed` |
| `phase0.analyzing_megatron` | `hf_analysis.yaml` exists | Invoke `megatron-reference-analyzer` to analyze Megatron-side modules | `phase0.bridge_mapping` or `phase0.human_needed` |
| `phase0.bridge_mapping` | `reference_impl_analysis.yaml` exists | Deterministic bridge step: combine hf_analysis + reference_impl_analysis to produce `bridge_mapping.yaml` | `phase0.quality_loop` |
| `phase0.quality_loop` | `bridge_mapping.yaml` exists | Completeness check: all components mapped or gapped; max 3 rounds | `phase0.analyzing_wip` (complete) or `phase0.bridge_mapping` (incomplete) or `phase0.human_needed` (after 3 rounds) |
| `phase0.analyzing_wip` | `bridge_mapping.yaml` passes quality checks | Absorb reference_contract fields into bridge_mapping, extract implementation contract | `phase0.slicing_ckpt` or `phase0.human_needed` |
| `phase0.slicing_ckpt` | `bridge_mapping.yaml` and weight structure exist | Skip or slice checkpoint, write `slice_report.json` when slicing is attempted/performed | `phase0.validating_output` or `phase0.human_needed` |
| `phase0.validating_output` | Artifacts are produced | Validate output contract and write `phase0_output.yml` | `phase0.passed` or `phase0.human_needed` |
| `phase0.passed` | All checks passed | Return top-level `passed` | Stop |
| `phase0.human_needed` | Missing source, invalid config, failed analysis, quality loop exhaustion, unsafe slicing, or output validation failure | Return top-level `human_needed` with re-entry point and artifact/log paths | Stop |

### Local Loop

Within each non-terminal state, use a narrow autoresearch-style loop:

```text
produce or repair the state artifact
validate the artifact with that state's checks
if valid: advance to next state
if repairable: keep the better artifact and repeat
if blocked or unsafe: return human_needed
```

Do not add phase-local attempts or transient evidence to `run_inputs.yml` or `phaseN_output.yml`. If attempt history is needed, append compact JSONL records to `phases/phase0/attempts.jsonl`.

### Quality Inner Loop (per D-15)

Phase 0 does NOT use the 12-state Loop FSM (no PRs, issues, or code changes to external repos). Instead, Phase 0 uses a **quality inner loop** within the `phase0.quality_loop` state:

```text
analyze -> completeness check -> (if incomplete) dig deeper -> max 3 rounds -> human_needed
```

When the quality inner loop finds incomplete items:
- Return to `phase0.bridge_mapping` to fill gaps (e.g., add missing component_bridge entries).
- Do NOT return to `phase0.analyzing_hf` — HF analysis is done once and not repeated.
- After 3 rounds still incomplete: write `phases/phase0/escalation.md` with list of incomplete items, exit `human_needed`.

---

## Input Contract

Phase 0 reads startup inputs from `run_inputs.yml`. The dispatcher may also pass the same values through the prompt, but `run_inputs.yml` is the persistent source of truth.

```yaml
source:
  hf_ckpt_path: <original HF checkpoint/model directory>

paths:
  hf_modeling_path: <absolute path to modeling_*.py>
  hf_transformers_path: <optional transformers repo root or src/transformers/models path>
  megatron_path: <optional Megatron-LM source path>

options:
  model_name: <name>
  enable_slice_ckpt: true|false
  wip_code_paths:
    - path: <path>
      type: megatron|hf_transformers|omni|other
```

When loop-engineering mode is enabled (repos: block present):
```yaml
repos:
  megatron:
    url: <Megatron repo URL>
    base_ref: <branch or ref>
```

Field meanings:
- `source.hf_ckpt_path`: original HF checkpoint/model directory. This is never replaced by a sliced path.
- `paths.hf_modeling_path`: user-confirmed HF network implementation path, used when local HF files are absent or incomplete.
- `paths.hf_transformers_path`: optional local Transformers source tree. If provided, Phase 0 must use it when resolving source files such as `modeling_*.py`, `configuration_*.py`, `processing_*.py`, `image_processing_*.py`, and related helpers.
- `paths.megatron_path`: optional Megatron-LM source tree. If provided (or `repos.megatron` is present), Phase 0 must use it for the Megatron-side analysis in Step 5.
- `options.enable_slice_ckpt`: controls whether Phase 0 attempts checkpoint slicing.
- `options.wip_code_paths`: optional structured reference inputs for architecture, conversion, runtime integration, and precision validation contracts consumed by later phases.

---

## Loop Engineering Hooks

> These steps apply ONLY when `run_inputs.yml` contains a `repos:` block (loop-engineering mode).
> Skip entirely for legacy invocations that do not provide `repos:`.
>
> **IMPORTANT:** Phase 0 does NOT use the Loop FSM (per D-15). These hooks are retained for future extension but are inactive by default for Phase 0. Phase 0 is a read-only analysis phase — it does not write code to external repos, does not open PRs/issues, and does not participate in the 12-state FSM.

### Pre-Edit: Branch Creation

Before writing any files to the target repositories:

1. Read `run_inputs.yml` and check if `repos:` block is present.
2. If present, invoke `gh_helper.create_branch(owner_repo, branch="adapt/<run_id>/phase0/attempt<K>", base=<base_ref>)` on **both** target repos:
   - **LoongForge repo**: use `repos.loongforge.url` for `owner_repo` and `repos.loongforge.ref` for `base_ref`.
   - **Megatron repo**: use `repos.megatron.url` for `owner_repo` and `repos.megatron.ref` for `base_ref`.
3. Record both branch names in `phases/phase0/attempts.jsonl` as `kind="branch"` entries (one per repo).
4. If branch creation fails (already exists or name conflict), check `gh_helper.find_by_idempotency_key` for an existing artifact and reattach rather than creating a duplicate.

### Post-Edit: PR Submission

After writing all phase artifacts and before running the validator:

1. If `repos:` block is present, invoke `gh_helper.open_pr(...)` on **both** repos:
   - **LoongForge repo**: `gh_helper.open_pr(owner_repo, head=<branch>, base=<base_ref>, run_id=<run_id>, phase=0, attempt=<K>, kind="base")` with templated title/body.
   - **Megatron repo**: `gh_helper.open_pr(owner_repo, head=<branch>, base=<base_ref>, run_id=<run_id>, phase=0, attempt=<K>, kind="base")`. The Megatron PR body MUST pin the LoongForge commit SHA (VAL-05: `loongforge_commit_sha: <sha>`).
2. Record both PR numbers and URLs in `phases/phase0_output.yml` under the `pr:` block.
3. Merge **both** PRs via `gh_helper.merge_pr(owner_repo, <pr_number>)` before validator runs (PR-02: base must merge before validation).
4. If any PR diff touches protected paths under `references/phases/phase0/verify.md` or `loongforge-phase-gate`, the loop controller will handle escalation to `human_needed` (PR-06).

---
## Output Contract

Phase 0 writes all artifacts under `run_dir/phases/phase0/` and writes one authoritative handoff file at `run_dir/phases/phase0_output.yml`.

```text
run_dir/
├── run_inputs.yml
├── phases/
│   ├── phase0/
│   │   ├── hf_analysis.yaml           (was model_spec.yaml — per D-04)
│   │   ├── reference_impl_analysis.yaml  (NEW — per D-18)
│   │   ├── bridge_mapping.yaml        (NEW, absorbs reference_contract.yml — per D-05)
│   │   ├── gap_decisions.md           (human-readable gap record — per D-02)
│   │   ├── slice_report.json          (retained — per D-03)
│   │   ├── attempts.jsonl             (optional, quality loop records)
│   │   └── sliced_hf/                 (optional, only when slicing is performed)
│   └── phase0_output.yml
```

`hf_analysis.yaml` is the primary HF-side output artifact. It supersedes `model_spec.yaml` (per D-04). For the complete field structure, see:
- `knowledge_base/schema/hf_analysis_schema.yaml`
- `knowledge_base/examples/model_spec_llm.yaml` (legacy reference, field names map to new schema)

`reference_impl_analysis.yaml` contains the Megatron-side analysis. For the complete field structure, see:
- `knowledge_base/schema/reference_impl_analysis_schema.yaml`

`bridge_mapping.yaml` is the core deliverable that downstream phases consume. For the complete field structure, see:
- `knowledge_base/schema/bridge_mapping_schema.yaml`

`phase0_output.yml` schema:

```yaml
phase: 0
status: passed
summary: "Dual-reference bridge analysis complete; hf_analysis, reference_impl_analysis, and bridge_mapping are ready."

step_gate:
  mandatory_steps_complete: true
steps:
  step1:
    status: passed
    evidence: "resolved HF source files"
  step2:
    status: passed
    evidence: "scanned HF checkpoint directory"
  step3:
    status: passed
    evidence: "phases/phase0/hf_analysis.yaml"
  step4:
    status: passed
    evidence: "weight_structure appended to hf_analysis.yaml"
  step5:
    status: passed
    evidence: "phases/phase0/reference_impl_analysis.yaml"
  step5_5:
    status: passed
    evidence: "phases/phase0/bridge_mapping.yaml"
  step6:
    status: passed
    evidence: "quality loop passed (round N/3)"
  step7:
    status: passed
    evidence: "reference_contract fields absorbed into bridge_mapping.yaml"
  step8:
    status: passed
    evidence: "slice_report.json or explicit slicing skip reason"
  step9:
    status: passed
    evidence: "phases/phase0_output.yml"

source:
  hf_ckpt_path: <original HF checkpoint/model directory>
  hf_modeling_path: <resolved modeling_*.py path>
  hf_transformers_path: <optional transformers source path or null>
  megatron_path: <optional Megatron source path or null>
  modeling_source: local|user_specified|transformers_tree|transformers_library|config_inferred|inherited_from
  resolved_source_files:
    modeling: <path>
    configuration: <path|null>
    processor: <path|null>
    image_processor: <path|null>

model:
  model_name: <name>
  model_type: llm|vlm|diffusion
  candidate_family: <family>
  candidate_match_reason: <reason>
  megatron_family: <family or "unknown">

artifacts:
  hf_analysis_path: phases/phase0/hf_analysis.yaml
  reference_impl_analysis_path: phases/phase0/reference_impl_analysis.yaml
  bridge_mapping_path: phases/phase0/bridge_mapping.yaml
  gap_decisions_path: phases/phase0/gap_decisions.md
  slice_report_path: phases/phase0/slice_report.json|null

slice:
  enabled: true|false
  performed: true|false
  reason: disabled|layer_count_le_16|success
  hf_ckpt_path: <sliced HF checkpoint path when performed, otherwise original hf_ckpt_path>
  config_path: <sliced config path when performed, otherwise original config.json path>
  report_path: phases/phase0/slice_report.json|null

checks:
  hf_analysis_exists: true
  components_non_empty: true
  weight_structure_non_empty: true
  reference_impl_analysis_exists: true
  bridge_mapping_exists: true
  bridge_mapping_component_bridge_non_empty: true
  bridge_mapping_gaps_have_guidance: true
  source_resolved: true
  slice_hf_ckpt_path_resolved: true
  slice_config_path_resolved: true
  mtp_preserved_when_present: true|null
```

The Phase 0 agent returns a JSON result to the Main Agent with the same top-level status semantics:

```json
{
  "status": "passed|human_needed",
  "summary": "One-sentence result",
  "failed_at_step": null,
  "root_cause": null,
  "state": "phase0.passed|phase0.human_needed",
  "step_trace": [...],
  "details": {
    "phase0_output_path": "<run_dir>/phases/phase0_output.yml",
    "hf_analysis_path": "<run_dir>/phases/phase0/hf_analysis.yaml",
    "reference_impl_analysis_path": "<run_dir>/phases/phase0/reference_impl_analysis.yaml",
    "bridge_mapping_path": "<run_dir>/phases/phase0/bridge_mapping.yaml",
    "gap_decisions_path": "<run_dir>/phases/phase0/gap_decisions.md",
    "slice_hf_ckpt_path": "<resolved path used by Phase 1/2/4>",
    "original_hf_ckpt_path": "<original HF checkpoint/model directory>"
  }
}
```

Do not return `failed` as a final Phase 0 status. Repair inside the local state loop when possible; otherwise return `human_needed`.

---

## Execution Progress Table

> **Execution Rule: execute strictly in order. Output a marker after each step is completed. Skipping a step marker is prohibited.**

| Step | State | Name | Status |
|---|---|---|---|
| 1 | `phase0.resolving_sources` | Resolve HF source inputs | ⬜ |
| 2 | `phase0.analyzing_hf` | Scan HF checkpoint directory | ⬜ |
| 3 | `phase0.analyzing_hf` | Invoke `hf-model-analyzer` -> write `hf_analysis.yaml` | ⬜ |
| 4 | `phase0.analyzing_hf` | Extract weight structure and append to `hf_analysis.yaml` | ⬜ |
| 5 | `phase0.analyzing_megatron` | Invoke `megatron-reference-analyzer` -> write `reference_impl_analysis.yaml` | ⬜ |
| 5.5 | `phase0.bridge_mapping` | Bridge step: combine hf_analysis + reference_impl_analysis -> write `bridge_mapping.yaml` | ⬜ |
| 6 | `phase0.quality_loop` | Completeness check: all components mapped or gapped; max 3 rounds | ⬜ |
| 7 | `phase0.analyzing_wip` | Absorb reference_contract fields into bridge_mapping; extract implementation contract | ⬜ |
| 8 | `phase0.slicing_ckpt` | Resolve `slice` output | ⬜ |
| 9 | `phase0.validating_output` | Validate and write `phase0_output.yml` | ⬜ |

Step completion protocol:
- Each step completed -> output `OK Step N -- <one-sentence result>`, then proceed.
- Each step blocked -> output `BLOCKED Step N -- <root cause>`, repair locally if possible or return `human_needed`.
- Optional WIP analysis must still emit a `skipped` step marker when no WIP paths are provided.

---

## Pre-Execution Preparation

Read all `.md` files under `knowledge_base/failure_patterns/phase0/` and load prevention measures into the current Phase 0 work. Verify each relevant prevention measure during source resolution and HF analysis.

---

## Execution Steps

### Step 1 -- Resolve HF Source Inputs

Read `run_inputs.yml` and resolve:
- `source.hf_ckpt_path`
- `paths.hf_modeling_path`
- `paths.hf_transformers_path`
- `paths.megatron_path` (or `repos.megatron` for loop-engineering mode)
- `source.resolved_source_files.*`

Resolution order for `modeling_*.py`:
1. Local file under `hf_ckpt_path`.
2. Explicit `paths.hf_modeling_path`.
3. Local Transformers source tree from `paths.hf_transformers_path`.
4. Installed `transformers` library.
5. `auto_map`, `model_type`, or inheritance hints from `config.json`.

When `hf_transformers_path` is provided:
- Accept either the Transformers repo root or `src/transformers/models`.
- Resolve the model package using `model_type`, `architectures`, `auto_map`, README hints, or class names.
- Prefer source files in that tree over installed library files.
- Record resolved files separately: `modeling`, `configuration`, `processor`, `image_processor`.

When `megatron_path` is provided (or `repos.megatron` is present in loop-engineering mode):
- Record the Megatron source tree for use in Step 5.
- If neither is provided, Step 5 will write a minimal reference_impl_analysis.yaml with `megatron_family: unknown`.

Possible `modeling_source` values:
- `local`: `modeling_*.py` found directly under `hf_ckpt_path`.
- `user_specified`: explicit `paths.hf_modeling_path`.
- `transformers_tree`: resolved from `paths.hf_transformers_path`.
- `transformers_library`: loaded from installed Transformers.
- `config_inferred`: inferred from `auto_map` or `model_type` and verified on disk.
- `inherited_from`: inherited from another model; record the inherited family/path in `hf_analysis.yaml`.

If no valid modeling source can be resolved, return `human_needed` with the missing path/class and re-entry point `phase0.resolving_sources`.

---

### Step 2 -- Scan HF Checkpoint Directory

Traverse top-level files in `source.hf_ckpt_path` and classify them according to `knowledge_base/schema/HF_SCAN_RULES.md`.

Extract basic information from `config.json`.

`model_type` determination priority:
1. `vlm`: `vision_config` sub-key exists, `image_token_id` exists, or `architectures[0]` contains `ForConditionalGeneration` / `ForCausalVLM`.
2. `diffusion`: `architectures[0]` contains `_diffusion_` case-insensitively.
3. Otherwise `llm`.

Required config fields:
- `hidden_size`
- `num_hidden_layers`
- `num_attention_heads`

For VLM, check top level first, then `text_config`. Count a field as missing only if absent in both places.

If required fields are missing, return `human_needed` with re-entry point `phase0.resolving_sources`.

Extract architecture description from `README.md` into `readme_context`:

```yaml
readme_context:
  candidate_hint: ""
  special_arch_notes:
    - "..."
  raw_summary: "..."
```

Candidate hint marker words: based on, built on, inspired by, similar to, following, extending, derived from, we adopt, we use X as backbone.

Special notes include new operators, non-standard attention, special MoE routing, unconventional positional encoding, and multimodal fusion methods. If README is absent or has no architecture description, keep the fields empty and continue.

---

### Step 3 -- Invoke `hf-model-analyzer`

Read and strictly follow `references/tools/hf-model-analyzer/SKILL.md`.

Pass in:

```text
hf_ckpt_path          <- source.hf_ckpt_path
readme_context        <- architecture description from Step 2
file_inventory        <- scanned file list
model_type            <- llm|vlm|diffusion
modeling_source       <- resolved source enum
resolved_source_files <- modeling/configuration/processor/image_processor paths
run_dir               <- current run directory
output_path           <- <run_dir>/phases/phase0/hf_analysis.yaml
```

If the analyzer returns `human_needed`, stop and pass through the reason. The re-entry point is `phase0.analyzing_hf`.

After completion, `phases/phase0/hf_analysis.yaml` must contain top-level metadata (`model_category`, `candidate_family`, `hf_reference_path`, `candidate_match_reason`, `has_chat_template`, optional `low_confidence_candidate`), `components`, optional `vlm_components`, `novel_modules`, `behavior_modifications`, `fp32_modules`, `traps`, and `special_features`. `weight_structure` is added in Step 4.

`behavior_modifications` is mandatory when config fields or HF helper logic change computation behavior without introducing a new component. Typical examples: activation clamp/offset fields, MTP-specific attention/router flags, FP8 reference-load policy, checkpoint key transforms, and model-specific guard/exception logic.

---

### Step 4 -- Extract Weight Structure

Prefer reading `<hf_ckpt_path>/model.safetensors.index.json`. If absent, try in order:
1. `pytorch_model.bin.index.json`
2. Single file `model.safetensors` via `safetensors.safe_open`
3. Single file `pytorch_model.bin` via `torch.load(..., map_location="cpu")`

Group weights by component prefix and append `weight_structure` to `phases/phase0/hf_analysis.yaml`.

If no weight files or indexes exist, return `human_needed` with re-entry point `phase0.analyzing_hf`.

Record for later output:
- `model_type`
- `candidate_family`
- `candidate_match_reason`
- `hf_analysis_path`
- component same/diff/new sets when available
- `novel_modules`
- `behavior_modifications` and their validation hints
- `has_chat_template`
- whether MTP weights/modules are present

---

### Step 5 -- Invoke `megatron-reference-analyzer` (per D-18)

Read `run_inputs.yml` for the Megatron source path:
- `paths.megatron_path` (local mode) or
- `repos.megatron` (loop-engineering mode, which provides url + base_ref + optional subpath)

Also read `phases/phase0/hf_analysis.yaml` components section to know which Megatron modules to look up.

If no Megatron path is available:
- Write a minimal `phases/phase0/reference_impl_analysis.yaml` with:
  ```yaml
  megatron_family: unknown
  source_repo: ""
  source_ref: ""
  analysis_timestamp: "<current ISO 8601>"
  modules: {}
  config_classes: {}
  ```
- Skip to Step 5.5 with gaps for all components (no Megatron modules available for mapping).
- Record in `phase0_output.yml` that `megatron_path` was not provided.

If Megatron path is available:
- Read and follow `references/tools/megatron-reference-analyzer/SKILL.md` (4-stage read-only analysis process: module discovery, signature extraction, config class analysis, output writing -- no code generation or implementation design).
- Pass in:
  ```text
  megatron_path      <- paths.megatron_path or repos.megatron local clone
  component_list     <- hf_analysis.components keys + candidate_family from KB
  candidate_family   <- hf_analysis.candidate_family
  run_dir            <- current run directory
  output_path        <- <run_dir>/phases/phase0/reference_impl_analysis.yaml
  ```
- Output: `phases/phase0/reference_impl_analysis.yaml` containing per-module analysis with class_name, source_file, base_classes, init_signature, forward_signature, config_fields_used, submodule_slots, and weight_params.

If the analyzer returns `human_needed`, stop and pass through the reason. The re-entry point is `phase0.analyzing_megatron`.

---

### Step 5.5 -- Bridge Step (Deterministic, per D-19)

This step is **deterministic and schema-driven**, not agentic. It combines `hf_analysis.yaml` and `reference_impl_analysis.yaml` to produce `bridge_mapping.yaml`.

Read:
- `phases/phase0/hf_analysis.yaml`
- `phases/phase0/reference_impl_analysis.yaml`

For each component in `hf_analysis.components`:

1. **If `reference_impl_analysis.modules` has a matching Megatron module**: create a `component_bridge` entry with:
   - `hf`: the HF component key
   - `megatron`: list of matching Megatron class/module references
   - `strategy`: from `hf_analysis.components[<key>].strategy`
   - `confidence`: derived from `hf_analysis.components[<key>].diff` field (same -> high, differs -> medium, new_component -> low)
   - `weight_map`: populated by mapping `hf_analysis.weight_structure` parameter names to `reference_impl_analysis.modules[<key>].weight_params` parameter names (per D-09, D-11). For each match, include `hf`, `megatron`, `shape_hint`, and `reshape_required`.
   - `behavioral_diff`: entries from `hf_analysis.behavior_modifications` that map to this component, converted to bridge_mapping format (topic, hf, megatron, impact, strategy)
   - `delta`: from `hf_analysis.components[<key>].delta`

2. **If no matching Megatron module**: create a `component_bridge` entry with:
   - `hf`: the HF component key
   - `megatron`: null (per D-09)
   - `strategy`: from `hf_analysis.components[<key>].strategy`
   - `confidence`: "low"
   - `weight_map`: null (per D-10 -- deferred to Phase 2 when Megatron module does not exist yet)
   - `behavioral_diff`: [] (no Megatron side to compare)
   - `delta`: from `hf_analysis.components[<key>].delta`
   - AND create a `gaps[]` entry with:
     - `id`: G1, G2, ... (sequential)
     - `component`: HF component key
     - `hf`: `hf_analysis.components[<key>].hf_class` or component key
     - `megatron`: "NEW" (per D-07)
     - `decision`: rationale for how this gap should be resolved (e.g., "New implementation required in LoongForge model-specific code" or "Extend existing Megatron Router with model-specific routing logic")
     - `impact`: derived from component importance (components with strategy=new_impl and no candidate -> critical; differs but has partial coverage -> high; differs with minor changes -> medium)
     - `phase1_guidance`: specific guidance on what Phase 1 should do (per D-02)

3. **Handle `low_confidence_candidate`** (per D-12): when `hf_analysis.low_confidence_candidate` is true, mark ALL `component_bridge` entries as `confidence: "low"` and add gap entries for mismatched components with explicit annotation "candidate is inaccurate for this component".

4. **Add `validator_requirements`**: Phase 0 declares what downstream phases need to verify. Derive from:
   - Components with `strategy: adapt_ref` -> "phase1-verify: confirm forward alignment for <component>"
   - Components with `weight_map` entries -> "phase2-conversion: verify weight mapping for <component>"
   - Gap entries with `impact: critical` -> "loss-diff: verify no numerical regression for <component>"

5. **Write `phases/phase0/bridge_mapping.yaml`** following the schema in `knowledge_base/schema/bridge_mapping_schema.yaml`.

6. **Generate `phases/phase0/gap_decisions.md`** (per D-02): for each gap entry in `bridge_mapping.gaps`, write a human-readable section:

```markdown
# Gap Decisions

## G1: <component>

- **HF side:** <hf class/description>
- **Megatron side:** <what exists or "NEW">
- **Decision:** <resolution direction>
- **Impact:** <critical/high/medium>
- **Phase 1 Guidance:** <what Phase 1 should do>
```

---

### Step 6 -- Quality Inner Loop (per D-15)

Phase 0 does NOT use the 12-state Loop FSM. This quality inner loop runs at most 3 rounds.

Completeness checks (all must pass):

1. Every component in `hf_analysis.components` has a corresponding entry in `bridge_mapping.component_bridge`.
2. No `component_bridge` entry has both `megatron: null` AND `weight_map` non-null (contradiction -- per D-10, weight_map must be null when megatron is null).
3. All `gaps` entries have non-empty `phase1_guidance`.
4. `weight_map` entries exist for every `component_bridge` where `megatron` is not null AND the component has `weight_structure` entries in `hf_analysis` (partial weight_map is acceptable for components with novel sub-modules).
5. No empty required string fields in `bridge_mapping` (`model`, `hf_source`, `megatron_family`).
6. `gap_decisions.md` exists and has one section per gap entry in `bridge_mapping.gaps` (per D-02).

If checks fail:
- Return to Step 5.5 to fill gaps (e.g., add missing component_bridge entries, fill empty required fields).
- Increment round counter.
- Max 3 rounds.
- Do NOT return to Step 3 or Step 5 -- HF analysis and Megatron analysis are done once.

After 3 rounds still incomplete:
- Write `phases/phase0/escalation.md` listing all incomplete items with their checks.
- Exit `human_needed` with re-entry point `phase0.quality_loop`.

When all checks pass:
- Record the quality loop round count in `phase0_output.yml` step6 evidence (e.g., "quality loop passed (round 1/3)").
- Proceed to Step 7.

---

### Step 7 -- Absorb Reference Contract Fields (per D-05)

This step replaces the old "reference and implementation contract extraction" step. The reference_contract.yml fields are now absorbed directly into `bridge_mapping.yaml`.

Read `options.wip_code_paths` from `run_inputs.yml` and any dispatcher-provided reference inputs. Treat prompt-provided issue URLs, design docs, upstream commits, local reference implementations, and framework-native examples as references when they are described as required, authoritative, or implementation-guiding.

If no references are provided, mark the step `skipped` and continue.

For each reference source:
1. Validate that `path`/`locator` exists or is otherwise reachable in the current environment. If a required locator cannot be read, return `human_needed` with `failure_gate="required_reference_unavailable"`.
2. Record its type (`megatron`, `hf_transformers`, `omni`, `issue`, `design_doc`, `commit`, or `other`), priority (`required` or `advisory`), and scope (`architecture`, `operator_semantics`, `checkpoint_conversion`, `runtime_integration`, `validation`).
3. For local code references, traverse only the files needed to identify entrypoints, component coverage, interfaces, and conversion scripts. For remote/text references, extract implementation claims and source pointers.
4. Compare discovered classes/functions/scripts against components and `weight_structure` in `hf_analysis.yaml`.
5. Write structured findings into `bridge_mapping.yaml` under:
   - `implementation_contract` (per D-05)
   - `conversion_requirements` (per D-05)
   - `phase3_reference_requirements` (per D-05)
   - `references[]` (per D-05 -- migrated from reference_contract.yml references section)
6. Optionally write human-readable notes to `phases/phase0/wip_analysis.md`.

#### 7a. Reference-patchset migrations

If the KB entry under `knowledge_base/sources/...` for this model declares `migration.required: true` (e.g. a model whose source YAML carries a `migration:` block), Phase 0 must additionally lift that block into `bridge_mapping.yaml.implementation_contract` so later phases run in `migration_mode=reference_patchset`. This is not optional and is in addition to standard reference scanning.

Record under `bridge_mapping.yaml.implementation_contract`:

```yaml
migration_mode: reference_patchset
reference_root: <KB migration.reference_root>
reference_omni_path: <KB migration.reference_omni_path>
reference_megatron_path: <KB migration.reference_megatron_path>
target_root: <current target root>
baseline_script: <KB migration.baseline_script>
lossdiff_bundle: <KB migration.lossdiff_bundle>
lite_checkpoint: <KB migration.lite_checkpoint or null>
allowed_megatron_diff:
  files: <KB migration.allowed_megatron_diff.files>
  description: <KB migration.allowed_megatron_diff.description>
forbidden_megatron_files: <KB migration.forbidden_megatron_files>
forbidden_megatron_strings: <KB migration.forbidden_megatron_strings>
verifier_script: <KB validation.verifier_script>
validation_contract: <KB validation.contract>
```

Required behaviour for later phases (Phase 1/3/5 must read these):
- The migration must port the reference patchset into the target tree without copying model-specific files into Megatron. Anything inside `forbidden_megatron_files` or matching `forbidden_megatron_strings` in the target Megatron diff is a hard fail.
- The Megatron diff must be a strict subset of `allowed_megatron_diff.files`, and each diff hunk must default-off (no behaviour change for non-`<family>` models).
- Phase 1's verifier must invoke `<verifier_script>` against both reference and target trees before any random-init smoke, and treat its `validator.status != passed` as a hard fail with `failure_gate="reference_patchset_migration_invariants"`.
- Phase 3 must use `migration.baseline_script` as the loss-diff baseline (`reference_type="reference_migration"`), NOT HF, and gate on `loss_mean_diff <= 1e-3` plus the migration verifier passing again on the final tree.
- Phase 5 must update the KB `migration:` block in place with the resolved target paths and reuse the same `validation.contract` name.

If the KB declares a migration but no reference root is reachable (locator missing/unreadable), return `human_needed` with `failure_gate="required_reference_unavailable"` and `state=phase0.analyzing_wip`.

Recommended `wip_analysis.md` structure:

```markdown
# Reference Analysis Summary

## Source 1: <locator> (<type>, <priority>)

### File Structure / Source Pointers
- <file list or quoted source pointers>

### Component Mapping
- <mapping between reference entrypoints and hf_analysis components>

### Contract Claims
- <architecture/conversion/validation claims that downstream phases must honor>

### Limitations
- <unreadable files, partial coverage, unknown semantics>
```

If a reference has no association with the target model, record `limitations: ["no association found"]` and continue only when it is advisory. If a required reference cannot be associated with any component or conversion/validation requirement, return `human_needed` with `failure_gate="required_reference_unresolved"`. If an advisory reference is too large to analyze completely, record the analyzed portion and mark the limitation in both artifacts. If a required reference is too large to cover its declared scope, return `human_needed` with `failure_gate="required_reference_incomplete"` unless the analyzed portion fully covers every required scope.

---

### Step 8 -- Resolve `slice` Output

Read `options.enable_slice_ckpt` from `run_inputs.yml`.

If slicing is disabled:

```yaml
slice:
  enabled: false
  performed: false
  reason: disabled
  hf_ckpt_path: <source.hf_ckpt_path>
  config_path: <source.hf_ckpt_path>/config.json
  report_path: null
```

If slicing is enabled but every repeated decoder module has `<= 16` layers:

```yaml
slice:
  enabled: true
  performed: false
  reason: layer_count_le_16
  hf_ckpt_path: <source.hf_ckpt_path>
  config_path: <source.hf_ckpt_path>/config.json
  report_path: null
```

If slicing is enabled and useful, invoke the `slice-ckpt` system skill when available. If unavailable, either perform slicing according to this section or return `human_needed` with the exact expected output layout.

Pass to slicing:

```text
hf_ckpt_path     <- source.hf_ckpt_path
model_spec_path  <- <run_dir>/phases/phase0/hf_analysis.yaml
output_dir       <- <run_dir>/phases/phase0/sliced_hf
report_path      <- <run_dir>/phases/phase0/slice_report.json
```

Hard slicing rules:
1. Slice only repeated decoder layers.
2. Keep first 2 and last 2 decoder layers.
3. Remap kept layer indices in weights and config.
4. Do not change MoE expert count.
5. Do not delete global modules such as embeddings, final norms, or `lm_head`.
6. If MTP exists, preserve MTP modules, weights, config fields, and non-layer references.
7. For VLM, do not slice vision encoder or projector by default.
8. Copy tokenizer, processor, image processor, generation config, custom code, and other non-weight files needed to load the checkpoint.

`slice_report.json` must follow the schema template in:

```text
references/phases/phase0/slice_report_schema.json
```

After slicing succeeds:

```yaml
slice:
  enabled: true
  performed: true
  reason: success
  hf_ckpt_path: <run_dir>/phases/phase0/sliced_hf
  config_path: <run_dir>/phases/phase0/sliced_hf/config.json
  report_path: phases/phase0/slice_report.json
```

If MTP exists and the sliced output does not preserve it, return `human_needed`. Do not silently drop MTP to simplify slicing.

---

### Step 9 -- Validate and Write `phase0_output.yml`

Before returning `passed`, validate:
- `phases/phase0/hf_analysis.yaml` exists.
- `components` in `hf_analysis.yaml` is non-empty.
- `weight_structure` in `hf_analysis.yaml` is non-empty.
- `phases/phase0/reference_impl_analysis.yaml` exists.
- `phases/phase0/bridge_mapping.yaml` exists.
- `component_bridge` in `bridge_mapping.yaml` is non-empty.
- All gap entries in `bridge_mapping.yaml` have non-empty `phase1_guidance`.
- `source.resolved_source_files.modeling` exists.
- `slice.hf_ckpt_path` exists.
- `slice.config_path` exists.
- If MTP was present, `checks.mtp_preserved_when_present` is `true`.
- If references were provided, `bridge_mapping.yaml.implementation_contract` is non-null.

Write `phases/phase0_output.yml` using the schema in Output Contract.

Top-level Phase 0 may return `passed` only after `phase0_output.yml` is written and the checks above are true. Otherwise return `human_needed` with the failed check, artifact path, and re-entry state.

---

## Error Handling

| Condition | status | Re-entry Point |
|---|---|---|
| `run_inputs.yml` missing required Phase 0 fields | `human_needed` | After the Main Agent completes startup input collection, re-enter `phase0.pending` |
| `config.json` missing required architecture fields | `human_needed` | After manually completing config, re-enter `phase0.resolving_sources` |
| No valid `modeling_*.py` source can be resolved | `human_needed` | After providing `hf_modeling_path` or `hf_transformers_path`, re-enter `phase0.resolving_sources` |
| `hf_transformers_path` provided but model package cannot be mapped | `human_needed` | After confirming the Transformers source path/package, re-enter `phase0.resolving_sources` |
| `hf-model-analyzer` returns `human_needed` | `human_needed` | After manually filling candidate family or source references, re-enter `phase0.analyzing_hf` |
| `hf_analysis.yaml` exists but `components` is empty | `human_needed` | After checking source resolution, re-enter `phase0.analyzing_hf` |
| No weight files or indexes exist | `human_needed` | After confirming weight files, re-enter `phase0.analyzing_hf` |
| `megatron-reference-analyzer` returns `human_needed` | `human_needed` | After providing Megatron source path or fixing analysis, re-enter `phase0.analyzing_megatron` |
| Quality inner loop fails after 3 rounds | `human_needed` | After addressing incomplete items in `escalation.md`, re-enter `phase0.quality_loop` |
| Required reference path/locator does not exist or cannot be read | `human_needed` | After correcting the reference, re-enter `phase0.analyzing_wip` |
| Required reference cannot be associated with any architecture, conversion, or validation requirement | `human_needed` | After clarifying the reference role, re-enter `phase0.analyzing_wip` |
| Advisory reference has no association with the target model | `passed` | N/A, record no association in `bridge_mapping.yaml` limitations |
| Advisory reference source too large for complete analysis | `passed` | N/A, record analyzed scope and limitations |
| Required reference source too large to cover declared scope | `human_needed` | After narrowing/providing the required reference scope, re-enter `phase0.analyzing_wip` |
| Slicing disabled | `passed` | N/A, `slice.hf_ckpt_path = source.hf_ckpt_path` |
| Layer count `<= 16` | `passed` | N/A, `slice.hf_ckpt_path = source.hf_ckpt_path` |
| Slice tool unavailable and manual slicing is unsafe | `human_needed` | After providing sliced checkpoint or tool support, re-enter `phase0.slicing_ckpt` |
| Slice output missing config/weights | `human_needed` | After fixing slice output, re-enter `phase0.slicing_ckpt` |
| MTP exists but is not preserved after slicing | `human_needed` | After fixing slicing logic/output, re-enter `phase0.slicing_ckpt` |
| `phase0_output.yml` validation fails | `human_needed` | Fix failed artifact/check, re-enter `phase0.validating_output` |
| `ModuleNotFoundError` or missing environment variable | First check `knowledge_base/qrh/environment_setup.md`; retry after fixing PYTHONPATH; if still blocked, `human_needed` | Re-enter failed state |
