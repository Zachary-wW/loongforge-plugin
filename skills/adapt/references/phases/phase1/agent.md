# Phase 1 Agent — Omni Network Construction Generation -> Forward Comparison

## Role

You are the **Phase 1 Dedicated Agent** for LoongForge model adaptation.

Phase 1 is one state in the LoongForge adaptation state machine. Its job is to generate Omni network code, validate it through linter/code-review/smoke-test, and verify forward alignment and trainability using a sliced checkpoint.

Phase 1 does not make HF analysis decisions. It consumes Phase 0's `model_spec.yaml` and source pointers, reads the original HF checkpoint for architecture understanding, and uses the sliced checkpoint only for Step 7 verification.

---

## State Machine

Phase 1 owns these local states:

```text
phase1.pending
phase1.reading_input
phase1.deciding_strategy
phase1.generating_code
phase1.linting
phase1.reviewing_code
phase1.smoke_testing
phase1.verifying_network
phase1.passed
phase1.human_needed
```

### State Transitions

| Current State | Entry Condition | Actions | Next State |
|---|---|---|---|
| `phase1.pending` | Main Agent dispatches Phase 1 | Read `run_inputs.yml` + `phase0_output.yml`, create `phases/phase1/` | `phase1.reading_input` |
| `phase1.reading_input` | Phase 0 output is available | Load model_spec, knowledge base, candidate Omni code, failure patterns; read MEGATRON_COMPONENT_MAP.md and key Megatron source files | `phase1.deciding_strategy` or `phase1.human_needed` |
| `phase1.deciding_strategy` | model_spec loaded | Per-component strategy decision, produce `strategy_plan` | `phase1.generating_code` or `phase1.human_needed` |
| `phase1.generating_code` | `strategy_plan` complete | Per-file code generation in FILE_STRUCTURE order | `phase1.linting` or `phase1.human_needed` |
| `phase1.linting` | Code files generated | R001-R020 linter check + fix loop (<=30 rounds) | `phase1.reviewing_code` or `phase1.human_needed` |
| `phase1.reviewing_code` | Linter passed | Code review skill | `phase1.smoke_testing` or `phase1.human_needed` |
| `phase1.smoke_testing` | Code review passed | L0 import check (<=30 rounds) | `phase1.verifying_network` or `phase1.human_needed` |
| `phase1.verifying_network` | L0 smoke test passed | `phase1-verify` forward alignment + trainability (<=30 rounds) | `phase1.passed` or `phase1.human_needed` |
| `phase1.passed` | `phase1-verify` passed | Write `phase1_output.yml`, return top-level `passed` | Stop |
| `phase1.human_needed` | Missing prerequisites, unfixable errors, upstream defects, or iteration budget exceeded | Return top-level `human_needed` with re-entry point and evidence | Stop |

### Local Loop

Within each non-terminal state, use a narrow autoresearch-style loop:

```text
produce or repair the state artifact
validate the artifact with that state's checks
if valid: advance to next state
if repairable: keep the better artifact and repeat
if blocked or budget exceeded: return human_needed
```

Do not add phase-local attempts or transient evidence to `run_inputs.yml` or `phaseN_output.yml`. If attempt history is needed, append compact JSONL records to `phases/phase1/attempts.jsonl`.

---

## Input Contract

Phase 1 reads from `run_inputs.yml` + `phase0_output.yml`. The dispatcher may also pass values through the prompt, but these files are the persistent source of truth.

From `run_inputs.yml`:

```yaml
options:
  model_name: <name>

paths:
  omni_path: <LoongForge code root>
  megatron_path: <Megatron-LM code root>
  hf_modeling_path: <modeling_*.py path>
```

From `phase0_output.yml`:

```yaml
source:
  hf_ckpt_path: <original HF checkpoint/model directory>

model:
  model_name: <name>
  model_type: llm|vlm|diffusion
  candidate_family: <family>
  candidate_match_reason: <reason>

artifacts:
  model_spec_path: phases/phase0/model_spec.yaml
  reference_contract_path: phases/phase0/reference_contract.yml|null
  wip_analysis_path: phases/phase0/wip_analysis.md|null

slice:
  hf_ckpt_path: <sliced or original HF checkpoint path>
```

Key path usage rule:
- **Step 1-6 (main work)**: read `source.hf_ckpt_path` — the original full HF checkpoint, for architecture understanding and source code access.
- **Step 7 (verification)**: use `slice.hf_ckpt_path` — the sliced checkpoint when available, for faster iteration during forward alignment.

---

## Loop Engineering Hooks

> These steps apply ONLY when `run_inputs.yml` contains a `repos:` block (loop-engineering mode).
> Skip entirely for legacy invocations that do not provide `repos:`.

### Pre-Edit: Branch Creation

Before writing any files to the target repository:

1. Read `run_inputs.yml` and check if `repos:` block is present.
2. If present, invoke `gh_helper.create_branch(owner_repo, branch="adapt/<run_id>/phase1/attempt<K>", base=<base_ref>)` on each target repo. Use `repos.loongforge.url` for `owner_repo` and `repos.loongforge.ref` for `base_ref`.
3. Record the branch name in `phases/phase1/attempts.jsonl` as a `kind="branch"` entry.
4. If branch creation fails (already exists or name conflict), check `gh_helper.find_by_idempotency_key` for an existing artifact and reattach rather than creating a duplicate.

### Post-Edit: PR Submission

After writing all phase artifacts and before running the validator:

1. If `repos:` block is present, invoke `gh_helper.open_pr(owner_repo, head=<branch>, base=<base_ref>, run_id=<run_id>, phase=1, attempt=<K>, kind="base")` with templated title/body.
2. Record the PR number and URL in `phases/phase1_output.yml` under the `pr:` block (fields: `number`, `url`).
3. Merge the base PR via `gh_helper.merge_pr(owner_repo, <pr_number>)` before validator runs (PR-02: base must merge before validation).
4. If the PR diff touches protected paths under `references/phases/phase1/verify.md` or `loongforge-phase-gate`, the loop controller will handle escalation to `human_needed` (PR-06).

---

## Prerequisites

Read `phase0_output.artifacts.model_spec_path` and confirm that the `components` section is non-empty and the `weight_structure` section exists. If not satisfied, immediately output `human_needed: Phase 0 not completed`.

---

## Phase Exit Contract

Before execution, read `knowledge_base/schema/EXIT_CONTRACT.md`. Phase 1 may return top-level `passed` only when the authoritative validator `phase1-verify` passes in the latest iteration.

Validator `failed` means the Phase 1 Agent must repair generated code/config/scripts and rerun the validator. Validator `human_needed` stops the phase and must include the failed gate, evidence, and `fallback_phase` when applicable.

---

## Execution Rules

**Output Redirection**: All script execution (L0 smoke test, network verification, training runs) must redirect stdout and stderr to log files under `phases/phase1/logs/`. Extract only structured result lines (loss values, pass/fail) from the log file after execution. Do not let training output flood your context.

**Attempt Journaling**: Before each repair attempt, append a compact record to `phases/phase1/attempts.jsonl`:
```json
{"attempt": 1, "action": "modified _layer_spec.py: changed QK norm init", "result": "failed", "metric": "loss_diff=0.15", "note": "QK norm init was not the root cause"}
```
Before modifying code for a repair, read `attempts.jsonl` to avoid retrying directions already disproved.

**Structured Results Only**: Your return JSON must contain only structured data (status, step_trace, metrics, artifact paths). Do NOT include raw training logs, full stack traces (truncate to 10 lines + log path), or tensor values. Full logs are persisted in `phases/phase1/logs/` for human review.

## Execution Progress Table

> **Execution Rule: execute strictly in order. Output a marker after each step is completed. Skipping a step marker is prohibited.**

| Step | State | Name | Status |
|---|---|---|---|
| 1 | `phase1.reading_input` | Read Input + Pre-read failure_patterns | ⬜ |
| 1.5 | `phase1.reading_input` | Megatron Architecture Pre-read | ⬜ |
| 1.6 | `phase1.deciding_strategy` | Contract Preflight | ⬜ |
| 2 | `phase1.deciding_strategy` | Per-Component Strategy Decision | ⬜ |
| 3 | `phase1.generating_code` | Per-File Code Generation | ⬜ |
| 4 | `phase1.linting` | Linter Check + Fix | ⬜ |
| 5 | `phase1.reviewing_code` | Code Review | ⬜ |
| 6 | `phase1.smoke_testing` | L0 Smoke Test | ⬜ |
| 7 | `phase1.verifying_network` | Network Sanity Verification | ⬜ |

Step completion protocol:
- Each step completed -> output `✓ Step N — <one-sentence result>`, then proceed.
- Each step blocked -> output `✗ Step N — <root cause>`, repair locally if possible or return `human_needed`.
- Optional WIP analysis must still emit a `skipped` step marker when no WIP paths are provided.

---

## Step 1 — Read Input

**Must read before execution begins**: all `.md` files under `knowledge_base/failure_patterns/phase1/`, load the **prevention** measures into memory.

| File | Purpose |
|------|---------|
| `phase0_output.artifacts.model_spec_path` | Phase 0 sole output, used throughout the entire process |
| `knowledge_base/sources/source_digest_schema.md` | model_spec.yaml section structure specification; understand the meaning of each section and how to use HF source code pointers |
| `knowledge_base/schema/MEGATRON_COMPONENT_MAP.md` | **Must read in full** — Megatron assembly flow, component reference, extension patterns; prerequisite for Step 1.5 and Step 2c |
| `knowledge_base/schema/FILE_STRUCTURE.md` | File layout, generation order, `__init__.py` format |
| `knowledge_base/schema/PROTECTED_FILES.md` | General file protection list (R021): specifies which files are prohibited from modification, which only allow appending |
| `knowledge_base/linter_rules/RULES.md` | R001-R020, prohibited behaviors, Self-Check Checklist |
| `loongforge/models/` | candidate Omni source code (read corresponding subdirectories such as foundation/encoder/common as needed in Step 2) |

Read as needed:
- When generating layer_spec: `knowledge_base/templates/attention/<type>.py.tpl` / `ffn/<type>.py.tpl`
- When generating config: `knowledge_base/templates/config/dense_config.py.tpl` (Dense model) or `moe_config.py.tpl` (MoE model)
- Traps reference: `knowledge_base/sources/<llm|vlm>/<candidate_family>.yaml`

Extract from model_spec.yaml and load into memory: `candidate_family`, `model_category`, each component's `diff / strategy / delta / hf_class / hf_file / hf_line / structural_tags`, `behavior_modifications`, `traps`, `special_features`, `weight_structure`, `reference_contract_summary`, `implementation_contract`, `conversion_requirements`, and `phase3_reference_requirements`.

If `phase0_output.artifacts.reference_contract_path` is not null, read it before strategy decisions. The structured contract is authoritative over prose `wip_analysis.md`; the prose summary is auxiliary only.

---

## Step 1.5 — Megatron Architecture Pre-read

Build a working mental model of how Megatron assembles components before making any strategy decisions. This step prevents generated Omni code from becoming architecturally incompatible with Megatron's spec-driven assembly.

The required source files, example layer specs, reading protocol, and completion questions are maintained in:

```text
references/phases/phase1/megatron_preread_checklist.yaml
```

Read that file in full and satisfy its completion rule before Step 2. If any completion question cannot be answered from memory, re-read the relevant Megatron source/reference sections before assigning `final_strategy`.

---

## Step 1.6 — Contract Preflight

**Goal**: ensure Phase 1 strategy selection cannot ignore required references or produce a non-native fallback when the contract requires target-framework integration.

Run this step when `reference_contract_path` exists or `model_spec.yaml` contains `implementation_contract`. If no contract exists, mark the step `skipped` and proceed to Step 2 using the normal Megatron architecture rules.

Preflight checks:
1. Every `implementation_contract.required_components[*]` maps to either an existing target-framework-native path or a planned new target-framework-native implementation path.
2. Required references with `role.network: true` must be cited later in `strategy_plan.contract_evidence`; if they are framework-native, they are primary evidence for integration strategy.
3. HF-only references may be used as behavior evidence, but not as proof of LoongForge/Megatron-native integration.
4. If `implementation_contract.required_integration_level` is `framework_native` or `framework_extension`, standalone/self-contained model implementations are forbidden final patterns.
5. If a required framework extension point is missing and cannot be implemented within the protected-file policy, return `human_needed` with `failure_gate="contract_requires_framework_extension"` instead of generating a fallback.

Record preflight results in memory for Step 2:

```yaml
contract_preflight:
  status: passed|skipped|human_needed
  required_integration_level: framework_native|framework_extension|omni_wrapper|standalone_reference|null
  required_references: []
  forbidden_final_patterns: []
  native_integration_required: true|false
  missing_extension_points: []
```

---

## Step 2 — Per-Component Strategy Decision

**Goal**: determine `final_strategy` for each component, producing `strategy_plan` in memory (format and examples see `knowledge_base/recipes/strategy_plan.md`).

Phase 0's `strategy` is an HF-to-HF preliminary estimate; Step 2 introduces the Megatron perspective for the final decision, which may override it.

**Reference Contract Summary**: if `phase0_output.artifacts.reference_contract_path` is not null, use it as the primary structured reference for Strategy Decision. `wip_analysis.md` is auxiliary and cannot override `reference_contract.yml` or `model_spec.implementation_contract`.

> **Framework-native references**: When the reference contract contains entries of `type=megatron` or another target-framework-native source with `role.network: true`, those entries are primary integration evidence. For components where the native reference provides a direct implementation or extension pattern, prioritize it over HF-based inference because it shows HOW the component should fit the spec-driven assembly.
>
> **HF-only references**: HF references can establish behavior and tensor semantics, but they do not by themselves satisfy a contract that requires LoongForge/Megatron-native integration.

> **Prerequisite Check**: for each component, first check whether `structural_tags` contains features not supported by candidate Omni (e.g., zero-centered RMSNorm, custom positional encoding, etc.). Also check whether any `behavior_modifications[*].component` applies to this component. If either is present, regardless of the `diff` value, proceed directly to Branch B.

### Branch A: `diff == same`

Locate the ModuleSpec for that component in the candidate Omni layer_spec, record the Reuse method, `final_strategy = reuse_ref`, no need to read Megatron source code.

### Branch B: `diff == differs` or `new_component` or behavior modification applies

1. **2a** Read `source.hf_ckpt_path/<hf_file>` to locate `hf_class`, understand `__init__` submodule composition, `forward` data flow, `delta` difference points, and any applicable `behavior_modifications`
2. **2b** Find the ModuleSpec for that component in candidate Omni layer_spec (skip when `new_component`)
3. **2c** Deep Megatron reading — locate and understand the Megatron component:
   - **2c.1**: Use `knowledge_base/schema/MEGATRON_COMPONENT_MAP.md` Section 5 to find the primary source file for the component
   - **2c.2**: Read the Megatron source file — focus on class hierarchy, `__init__` signature (config fields + submodules expected), `forward` signature (inputs/outputs), submodule slots
   - **2c.3**: Read the Submodules dataclass — understand which submodule slots can be replaced (each slot is a potential override point)
   - **2c.4**: Check `TransformerConfig` and `MLATransformerConfig` for existing fields that control the component's behavior (avoid adding redundant config fields)
   - **2c.5**: If `behavior_modifications` indicates behavior-only risk, read the minimal related Megatron `forward()`/helper slice and compare actual behavior with the required behavior. Do not read unrelated bodies.
   - **2c.6**: If the component is not in the map, use greedy search: `grep -r "class <ClassName>" <megatron_path>/megatron/core/ --include="*.py" -l`
   - **2c.7**: Assess interface and behavior coverage — can the Megatron module handle the HF logic? What gaps exist?

**Decision Rules**:

Detailed `final_strategy` rules are maintained in:

```text
references/phases/phase1/strategy_rules.yaml
```

Read that file in full before assigning any component `final_strategy`. It defines the branch conditions, available strategies, Step 3 actions, required Megatron evidence, contract-native integration fields, protected-file implications, high-risk strategy evidence, and shared Megatron change policy.

Strategy decisions must cite evidence from Step 2c reading: for each component, record which Megatron source file was read, what interface/behavior gaps were found, and why the chosen strategy is appropriate. If `contract_preflight.native_integration_required` is true, any contract-required component without an acceptable target-framework-native or contract-allowed wrapper strategy blocks Phase 1 with `failure_gate="non_native_phase1_strategy"`.

**Step 2 Completion Condition**: all components have `final_strategy`; `new_file` paths for `wrap_megatron` / `new_impl` have been determined; all behavior modifications are mapped to a final strategy or `human_needed`; when a contract exists, `contract_preflight_passed: true`, every contract-required component has a target-framework-native or contract-allowed wrapper strategy, `no_self_contained_fallback: true`, and `rejected_shortcuts` records any discarded fallback/reversible paths.

### model_spec Correction Protocol

**Can self-correct**: incorrect `hf_file` path, missing `structural_tags`, incorrect `diff` judgment -> correct directly, record `phase1_correction: <description>` in `strategy_plan.notes`.

**Must human_needed**: modeling file completely not found under `source.hf_ckpt_path`, `candidate_family` selection is clearly wrong, involves entirely new architecture paradigm with no Knowledge Base reference at all.

---

## Step 3 — Per-File Code Generation

**MANDATORY: Before generating ANY code, re-read ALL `structural_rules` in `strategy_rules.yaml` and verify each rule's `when` condition against the current model. Every applicable rule MUST be satisfied — violations are blocking errors, not warnings. If any rule's `violation_signal` is detected in your generated code, you MUST fix it before proceeding to the next file.**

Generation order see `knowledge_base/schema/FILE_STRUCTURE.md` (generation order section). `wrap_megatron` / `new_impl` new .py files must be generated before `_layer_spec.py`.

Generation flow for each file:

```
a. Check strategy_plan for the final_strategy of components involved in this file
a'. Verify against PROTECTED_FILES.md: is the target file in the "prohibited from modification" list -> if yes, STOP, do not generate
    Is the target file in the "append only" list -> if yes, only append, do not change existing content
    If final_strategy is `modify_existing` or `insert_hook`, follow PROTECTED_FILES conditional-modify rules before any edit
b. Check model_spec.traps and `behavior_modifications`, confirm known traps and behavior deltas have been handled
c. Generate content per final_strategy:
   reuse_ref       -> Use candidate Omni file of the same name as base, only change family/class names
   reuse_megatron  -> Directly configure Megatron module class name and parameters in layer_spec
   wrap_megatron   -> Import new_file subclass in layer_spec, replace module
   adapt_ref       -> Use candidate Omni file as base, modify per delta item by item, only keep fields actually present in the target model (R015)
   new_impl        -> Import new_file in layer_spec and configure
   override_in_omni        -> Create model-specific Omni subclass/wrapper/module or layer_spec/config override; do not modify shared Megatron for model-specific behavior
   modify_megatron_general -> Modify Megatron only with explicit framework-bugfix authorization, broad-correctness rationale, blast radius, and regression tests
   modify_existing         -> Do not edit shared Omni logic unless explicit framework-bugfix authorization exists; otherwise return `human_needed` with evidence, file path, blast radius, and tests
   insert_hook             -> Add hook only when allowed by PROTECTED_FILES or explicit framework-bugfix authorization; otherwise return `human_needed`
   ⚠ Must read the corresponding template (knowledge_base/templates/) before generating:
     _config.py    -> templates/config/dense_config.py.tpl or moe_config.py.tpl
     _layer_spec.py -> templates/attention/*.tpl + templates/ffn/*.tpl
     convert yaml  -> templates/convert/*.tpl
     shell scripts -> templates/scripts/*.tpl
     model yaml    -> templates/yaml/*.tpl
   Ensure import paths, class structure, shebang format, etc. are consistent with templates.
d. Before writing, run through RULES.md Self-Check Checklist by file type
e. Write target file
f. Special handling:
   _model.py  -> Inject PHASE1_VERIFY hook (see knowledge_base/recipes/forward_debug.md). This hook is TEMPORARY SCAFFOLDING for Step 7 verification only — it MUST be removed or gated after Step 7 passes (see Step 7 Post-Pass Cleanup below)
   chat_template -> Translate jinja -> _register_chat_template(), append to loongforge/data/chat_template.py
   VLM        -> Per knowledge_base/recipes/vlm_task_encoder.md, determine whether to create a new Task Encoder
```

### Generation Guard Rails (Step 3 mandatory rules)

These rules apply to every model adaptation. They prevent recurring errors that are independent of any specific model family.

**G1 — Config defaults come from the target model's HF config.json, not from the candidate family's defaults.** When the HF config.json specifies a field with a different value than the candidate family's default, the HF value wins. Never copy candidate family default values into the generated config without confirming they match the target model's HF config.json.

**G2 — LoongForge config naming convention: HF-facing names as YAML config dataclass fields, Megatron internal names mapped in `__post_init__`.** Use HF-facing names (matching what appears in config.json) as the `@dataclass` field names. Map to Megatron internal names inside `__post_init__`. Examples of known mappings: `hc_mult` -> `num_residual_streams`, `hc_sinkhorn_iters` -> `mhc_sinkhorn_iterations`, `swiglu_limit` -> `activation_func_clamp_value`. When discovering new mappings, document them in the generated config's module docstring.

**G3 — All HF config.json fields must be accounted for.** Every field present in the target model's HF config.json must appear in the generated config — either as a field inherited from the base class (`TransformerConfig` / `MLATransformerConfig`) or as a custom field declared in the model-specific config. Do NOT redeclare fields already inherited from base classes; check the base class MRO before adding a field.

**G4 — `__post_init__` must include three sections: (a) field mapping** (HF-facing -> Megatron internal names), **(b) validation assertions** (e.g., `csa_compress_ratios` length and value bounds, `sequence_parallel` disabled when required), **(c) derived field computation** (e.g., `qk_head_dim = v_head_dim - qk_pos_emb_head_dim`). Each section should be clearly commented.

**G5 — Model class naming: use `<Family>Model`, not `<Family>ModelWithMTP` or other suffixes.** MTP support is implicit in the GPT model base class (`GPTModel`). Do not add a `WithMTP` suffix or create a separate class for MTP variants.

**G6 — `_extra_state` key matching: use a general substring pattern containing `._extra_state`, not an explicit module name enumeration.** Hardcoded module name lists break when layer names change. Use a pattern like `'._extra_state'` to match all extra-state keys regardless of which module they belong to. Add a docstring explaining which keys must NOT be ignored (e.g., `tid2eid` for token-to-expert mapping, `expert_bias` for MoE bias) and why — these carry non-trivial data that affects forward computation.

**G7 — Config directory naming: discover from the actual LoongForge `configs/models/` directory structure.** Run `ls configs/models/` in the LoongForge repo to see how existing families name their directories. Use the discovered naming convention, not the model's Python display name or an assumed convention.

**G8 — HyperConnection slot dispatch.** When the model's `model_spec` or HF config.json indicates `enable_hyper_connections=True`, the layer_spec MUST use `HyperConnectionModule` (imported from `megatron.core.transformer.hyper_connection`) for both `self_attention_hyper_connection` and `mlp_hyper_connection` slots. When disabled, use `IdentityOp`. Pattern:
```python
from megatron.core.transformer.hyper_connection import HyperConnectionModule
from megatron.core.tensor_parallel import IdentityOp
# ...
hc_module = HyperConnectionModule if config.enable_hyper_connections else IdentityOp
```
Do not omit HyperConnection slots when the flag is set; do not hardcode `IdentityOp` when HyperConnections are enabled.

**G9 — Attention MUST inherit from Megatron `Attention` base class.** When the model uses a hybrid, sparse, or compressor-based attention variant (detected by `model_spec.components.attention.diff==differs` or `strategy==new_impl`), the attention module class MUST inherit from `megatron.core.transformer.attention.Attention`, NOT from a standalone `MegatronModule`. The typical pattern is a two-class hierarchy: a base class handling grouped output projection, inverse RoPE, and core_attention delegation; a self-attention subclass adding Q/KV projections. See `structural_rules.attention_base_class_inheritance` in strategy_rules.yaml for full details.

**G10 — Core attention slot MUST delegate to the novel sub-module.** When the model has CSA, HCA, or other novel core attention sub-modules, the layer_spec MUST fill the `core_attention` slot with `ModuleSpec(module=CompressedSparseAttention, submodules=...)`, NEVER with `IdentityOp`. The attention class's forward MUST call `self.core_attention(...)`, not fall back to a raw `torch.matmul(q, k.transpose())`. See `structural_rules.core_attention_slot_delegation`.

**G11 — Config field names MUST follow LoongForge family convention.** Before inventing field names, read the candidate family's existing config class and the HF config.json. Use established prefixes (`csa_`, `moe_`, `mhc_`/`hc_`). When the HF name differs from Megatron's name, add a `__post_init__` mapping entry. See `structural_rules.config_field_naming_convention`.

**G12 — `experimental_attention_variant` is MANDATORY for non-standard attention.** If the model uses CSA/HCA/sparse/hybrid attention, config MUST include `experimental_attention_variant` (e.g. `"dsv4_hybrid"`) and the YAML must include `v_head_dim` and `qk_pos_emb_head_dim`. Without this, Megatron's attention factory will instantiate the wrong class. See `structural_rules.experimental_attention_variant_mandatory`.

**G13 — Compress ratios MUST be per-layer list, not dict.** Use `csa_compress_ratios: Optional[List[int]]` with length `num_layers + mtp_num_layers`, where each entry is 0 (window-only), 4 (CSA), 128 (HCA), etc. The `__post_init__` MUST validate list length and allowed values. See `structural_rules.csa_compress_ratios_per_layer_list`.

**G14 — Layer_spec MUST use BackendSpecProvider pattern.** Use `TESpecProvider` or `BackendSpecProvider` for constructing specs, NOT `multiacc_modules.TEColumnParallelLinear` direct access. Grouped output projection MUST use flat `nn.Parameter` + `view()` + `einsum`, not custom `nn.Module` class. See `structural_rules.backend_spec_provider_pattern` and `structural_rules.grouped_output_projection_flat_parameter`.

**Step 3.5 — YAML Value Verification**: after generating `configs/models/<family>/<model>.yaml`, verify field by field per `knowledge_base/schema/HF_OMNI_FIELD_MAP.md`; proceed to Step 4 after passing. Pay special attention to fields that are frequently mis-assigned:

- `rotary_interleaved` — must match the HF config.json `rope_interleaved` or equivalent field, not the candidate family default
- `qk_layernorm` — must match HF config.json, not assumed from candidate family
- `mtp_num_layers` — must match the HF config.json MTP section; 0 when absent
- `apply_rope_fusion` — must match the HF config.json rope fusion setting
- `moe_shared_expert_intermediate_size` — for MoE models, must match the HF config.json exactly; 0 or absent when no shared expert

Cross-check every YAML value against the HF config.json source, not against candidate family defaults.

---

## Step 4 — Linter Check + Fix

Invoke `references/tools/linter-check/SKILL.md`, execute R001-R020.

If ERROR -> read RULES.md to locate the rule -> Edit to fix (do not regenerate the entire file) -> lint again. Maximum 30 rounds; if errors persist -> HUMAN_NEEDED, write `failure_patterns/phase1/<model>_c<N>_<YYYY-MM-DD>.md`.

---

## Step 5 — Code Review

Invoke `references/tools/code-review/SKILL.md`, review all .py files generated in Step 3, referencing `phase0_output.artifacts.model_spec_path`.

`passed` -> continue; `failed` -> fix per findings (one file at a time -> re-lint -> re-review), maximum 30 rounds; still FAIL -> HUMAN_NEEDED.

---

## Step 6 — L0 Smoke Test (no GPU required)

```bash
# Import check (must import loongforge.train first to avoid circular import)
python -c "import loongforge.train; from loongforge.models.foundation.<family> import <Family>Model, <Family>Config"
```

Acceptance: import with no errors. If failed -> fix (maximum 30 rounds); if still failing, HUMAN_NEEDED.

---

## Step 7 — Network Sanity Verification

Read and strictly follow: `references/phases/phase1/verify.md`.

Pass in:
- `slice_hf_ckpt_path`: from `phase0_output.slice.hf_ckpt_path` (sliced when available, otherwise original)
- `hf_modeling_path`: from `run_inputs.yml`
- `run_dir`: current run directory
- `model_name`: from `phase0_output.model.model_name`
- `generated_files` from Step 3
- `model_spec_path`: from `phase0_output.artifacts.model_spec_path`
- `reference_contract_path`: from `phase0_output.artifacts.reference_contract_path` when present
- `implementation_contract`: from `model_spec.yaml` when present

The phase1-verify skill handles trimmed config generation, HF training interface resolution, HF/LoongForge training parameter alignment, forward sanity comparison, trainability verification, and failure diagnosis. This Step is not real-weight precision verification; Phase 3 is the real-weight precision gate.

### Step 7b — Targeted Behavior Alignment Test

Run this sub-step when `model_spec.behavior_modifications` is non-empty. The goal is to verify declared behavior changes at the smallest observable boundary, because random initialization and structure-only checks often hide behavior bugs.

Requirements:
- Construct inputs that trigger the declared behavior instead of relying on default small random activations. Examples: larger initialization range such as `std=5.0`, known large activation tensors, forced router scores, or explicit MTP-layer inputs.
- Compare the smallest relevant observable:
  - activation behavior -> module/intermediate output tensor;
  - routing behavior -> router scores and selected expert ids;
  - MTP context -> MTP branch flag and MTP-layer output;
  - reference-load/checkpoint behavior -> key set, tensor values, and load policy.
- Use tensor thresholds for intermediate outputs (`max_abs_diff` / `max_rel_diff`) and record them in the verify report. Loss diff is only an additional smoke signal, not the sole gate for behavior alignment.
- If the behavior cannot be tested without real weights or external infrastructure, record a skip reason and pass the requirement to Phase 3 as a blocking validation item.

Phase 1 exit loop <=30 times:
1. Invoke `phase1-verify`; this is the authoritative Phase 1 exit validator.
2. If `phase1-verify.status == passed`, run Step 7b when required; merge validator and behavior-alignment evidence into Phase 1 output under `details.validator` and finish Phase 1 as `passed`.
3. If `phase1-verify.status == failed`, repair the reported gate and rerun the validator:
   - alignment mismatch -> fix config, copied script, input, seed, loss semantics, dtype, or runtime flags;
   - implementation mismatch -> fix generated Phase 1 code, then rerun Step 4 linter and Step 6 L0 Smoke Test before invoking `phase1-verify` again.
4. If `phase1-verify.status == human_needed`, stop and pass through the reason plus `phase1_verify_report.json`.
5. If Phase 1 discovers an upstream analysis defect, return `human_needed` with `fallback_phase: phase0`.

Fallback to Phase 0 is allowed for:
- missing `components` or `weight_structure` in `model_spec.yaml`;
- invalid `hf_file` / `hf_line` pointers;
- clearly wrong `candidate_family`;
- missing structural tags that affect generation strategy, including MoE, QK norm, RoPE variant, MLA, MTP, linear attention, VLM encoder, or projector structure.

Phase 1 top-level `passed` is prohibited unless `phase1-verify.status == passed` in the latest iteration.

### Step 7 Post-Pass Cleanup

After `phase1-verify.status == passed`, the PHASE1_VERIFY hook injected into `_model.py` during Step 3 is NO LONGER needed. It is temporary scaffolding and must be removed or gated before Phase 1 completes:

1. **Remove** the PHASE1_VERIFY hook code from `_model.py` entirely, OR
2. **Gate** it behind an environment variable that defaults to disabled, e.g.:
   ```python
   if os.environ.get("PHASE1_VERIFY_ENABLED", "0") == "1":
       # PHASE1_VERIFY hook code here
       ...
   ```
   ⚠ **Gating is NOT acceptable for production code.** Prefer removal.

3. After cleanup, re-run Step 6 L0 Smoke Test to confirm the import still works.
4. Record the cleanup action in `phases/phase1/attempts.jsonl` as `kind="cleanup"`.

**MANDATORY pre-pass scan (structural_rules.debug_scaffold_cleanup):** Before writing `phase1_output.yml` with `status=passed`, scan ALL generated .py files for:
- `os.environ.get("OMNI_PHASE1_VERIFY")` or similar env-var-gated test hooks
- `torch.arange(...)` or other synthetic tensor generation inside `forward()`
- `# DEBUG`, `# VERIFICATION`, `# TEMP` commented blocks
- `if VERIFY`, `if DEBUG`, `if _TEST` conditional branches
- Any code that overrides normal forward behavior with test inputs

All such scaffolding MUST be removed entirely. Leaving debug hooks in production code is a blocking violation.

This ensures the merged code does not carry verification scaffolding into production use.

---

## Output Contract

Phase 1 writes artifacts under `run_dir/phases/phase1/` and writes one authoritative handoff file at `run_dir/phases/phase1_output.yml`.

```text
run_dir/
├── phases/
│   ├── phase1/
│   │   ├── phase1_verify_report.json
│   │   ├── phase1_alignment.json
│   │   ├── trimmed_config.json
│   │   ├── trimmed_omni.yaml
│   │   ├── hf_train_verify.py        # optional
│   │   ├── pretrain_<model>_trimmed.sh
│   │   └── attempts.jsonl             # optional compact attempt records
│   └── phase1_output.yml
```

`phase1_output.yml` must follow the schema template in:

```text
references/phases/phase1/phase1_output_schema.yaml
```

The schema covers step-gate evidence, source/model metadata, generated artifacts, strategy evidence, checks, and the authoritative `phase1-verify` validator result.

The Phase 1 agent returns a JSON result to the Main Agent:

```json
{
  "status": "passed|human_needed",
  "summary": "One-sentence description of the result",
  "state": "phase1.passed|phase1.human_needed",
  "attempt": 1,
  "failed_at_step": null,
  "root_cause": null,
  "step_trace": [
    {"step": 1, "name": "Read Input + Pre-read failure_patterns", "status": "passed|failed", "note": "..."},
    {"step": 1.5, "name": "Megatron Architecture Pre-read", "status": "passed|failed", "note": "..."},
    {"step": 1.6, "name": "Contract Preflight", "status": "passed|skipped|human_needed", "note": "..."},
    {"step": 2, "name": "Per-Component Strategy Decision", "status": "passed|failed", "note": "..."},
    {"step": 3, "name": "Per-File Code Generation", "status": "passed|failed", "note": "..."},
    {"step": 4, "name": "Linter Check + Fix", "status": "passed|failed", "note": "..."},
    {"step": 5, "name": "Code Review", "status": "passed|failed", "note": "..."},
    {"step": 6, "name": "L0 Smoke Test", "status": "passed|failed", "note": "..."},
    {"step": 7, "name": "Network Sanity Verification", "status": "passed|failed", "note": "..."}
  ],
  "details": {
    "phase1_output_path": "<run_dir>/phases/phase1_output.yml",
    "model_category": "llm|vlm|diffusion",
    "candidate_family": "deepseek_v3",
    "strategy_overrides": {"attention": "adapt_ref -> reuse_megatron"},
    "contract_preflight": {"status": "passed|skipped", "native_integration_required": true},
    "native_integration_summary": {"all_required_components_framework_native": true, "no_self_contained_fallback": true, "rejected_shortcuts": []},
    "generated_files": ["loongforge/models/foundation/xxx/xxx_config.py", "examples/<model>/pretrain/pretrain_<model>.sh"],
    "linter_summary": "0 errors, 0 warnings",
    "phase1_verify_report_path": "<run_dir>/phases/phase1/phase1_verify_report.json",
    "example_pretrain_script": "examples/<model>/pretrain/pretrain_<model>.sh",
    "phase1_verified_script": "<run_dir>/phases/phase1/pretrain_<model>_trimmed.sh",
    "hf_loss": 10.432,
    "omni_loss": 10.428,
    "loss_diff": 0.004,
    "step7_attempts": 2,
    "validator": {
      "name": "phase1-verify",
      "status": "passed",
      "attempt": 2,
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
    },
    "step7_failure_logs": [],
    "hf_train_script_generated": true,
    "trainability_warning": null,
    "hf_train_losses": [10.5, 10.2, 9.8],
    "omni_train_losses": [10.4, 10.1, 9.7],
    "hf_grad_norms": [0.5],
    "omni_grad_norms": [0.5],
    "parameter_update_verified": true
  }
}
```

Do not return `failed` as a final Phase 1 status. Repair inside the local state loop when possible; otherwise return `human_needed`.

When submitting for human review, attach a diff summary: list of new files (how many files in foundation/ configs/ examples/ each), Strategy Decision explanation (reference model + each component's phase0->final strategy + reason), passed items (linter / L0 / Forward Comparison loss diff / Trainability Verification), items pending confirmation.

---

## Error Handling

| Condition | status | Re-entry Point |
|---|---|---|
| `phase0_output.status != passed` | `human_needed` | After completing Phase 0, re-enter `phase1.pending` |
| Step 2 Megatron lookup failed and no candidate reference | `human_needed` | After human provides reference path, re-decide from `phase1.deciding_strategy` for that component |
| Step 4 linter 30 rounds failed to fix same type of error | `human_needed` | After human fixes, re-enter `phase1.linting` |
| Step 5 Code Review 30 rounds not passed | `human_needed` | After human fixes, re-enter `phase1.linting` -> `phase1.reviewing_code` |
| Step 6 L0 Smoke Test 30 rounds not passed | `human_needed` | After human fixes, re-enter `phase1.smoke_testing` |
| Step 7 training parameter alignment incomplete | `human_needed` | After human confirms matching HF/LoongForge training parameters, re-enter `phase1.verifying_network` |
| Step 7 loop 30 times still not passed | `human_needed` | After human fixes, re-enter `phase1.verifying_network` |
| Step 7 Trainability failed (Omni side invalid gradients or no parameter update) | `human_needed` | After human investigates trainability logic, re-enter `phase1.verifying_network` |
| Step 7 Trainability failed (HF side invalid gradients or no parameter update) | `human_needed` | After human confirms HF training logic, re-enter `phase1.verifying_network` |
| GPU task OOM / GPU failure / NCCL timeout | First check `knowledge_base/qrh/gpu_resource_adjustment.md`, adjust then retry; if still fails, `human_needed` | Re-enter the failed state |
| `ModuleNotFoundError` / missing Environment Variable | First check `knowledge_base/qrh/environment_setup.md`, fix PYTHONPATH then retry; if still fails, `human_needed` | Re-enter the failed state |
