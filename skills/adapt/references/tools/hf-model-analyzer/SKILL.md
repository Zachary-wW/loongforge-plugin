---
name: hf-model-analyzer
description: LoongForge Phase 0 core skill. Reads HF model source, identifies all components with code pointers, selects candidate family, compares new model against candidate HF source code, and writes model_spec.yaml. Use when executing Phase 0 of model adaptation.
compatibility: Designed for LoongForge /loongforge:adapt workflow (Claude Code or similar)
---

Perform complete architecture analysis on an HF model: read source code -> identify components -> select candidate -> code-level comparison -> write `model_spec.yaml` (excluding the `weight_structure` section).

## Input

```
hf_path          -- HF model local directory
readme_context   -- Architecture description extracted in Phase 0 Step 1
file_inventory   -- File path list scanned in Phase 0 Step 1
model_category   -- LLM | VLM | Diffusion
modeling_source  -- "local" | "user_specified" | "transformers_library" | "config_inferred" | "inherited_from"
inherited_from   -- Only filled when modeling_source="inherited_from" (family name, e.g., "deepseek_v3")
run_dir          -- Output artifact directory
```

`readme_context` format:

```yaml
readme_context:
  candidate_hint: "deepseek_v3"       # Reference model family explicitly mentioned in README; empty if none
  special_arch_notes:                 # Architecture special points described in README, recorded item by item
    - "introduces DSA replacing standard MLA core_attention"
  raw_summary: "..."                  # Original text of architecture-related paragraphs from README (1-3 paragraphs)
```

---

## Stage 1 -- Read Source Code, Identify Components

**If `modeling_source == "inherited_from"`**: Do not read the new model's modeling file. Retrieve `hf_reference_path` from `knowledge_base/sources/<llm|vlm>/<inherited_from>.yaml`, use the `modeling_*.py` under that path as the code base, and lock the candidate to the family specified by `inherited_from` (skip Stage 2 scoring).

**`config_inferred` processing rule**: When `modeling_source == "config_inferred"`, the processing is **completely equivalent** to `inherited_from`:
- Use the HF source files of the family specified in the `inherited_from` field of `model_spec.yaml` as the analysis basis
- Skip the scoring process in Stage 2 (the candidate has already been determined by Phase 0 Step 1c through config field inference)
- Perform comparison analysis in Stage 3 against the HF code of the `inherited_from` family

**Otherwise**: Read all `modeling_*.py` and `configuration_*.py` under `hf_path`.

Scan all class definitions, classify them according to the table below, record `hf_class / hf_file / hf_line`, and extract `structural_tags` from `__init__` / `forward`:

**LLM Components**

| Component Key | Identification Rule |
|---------------|---------------------|
| `embedding` | `embed_tokens` / Embedding vocabulary; fill `inline` if no standalone class |
| `positional_encoding` | Contains `Rotary` / `RoPE` / `YaRN` / `ALiBi` / `NTK` |
| `attention` | Contains `Attention` / `Attn`, decoder side |
| `attention_norm` | Internal norm within attention (q_norm / kv_norm / latent_norm) |
| `flash_attention` | Standalone class containing `Flash` / `FA2` |
| `ffn` | Contains `MLP` / `FFN`, dense layer |
| `moe_gate` | Contains `Gate` / `Router` |
| `moe_experts` | Routed expert FFN; when same class as ffn, record `same_class_as: ffn` |
| `moe_shared_experts` | Shared expert; same as above when same class as ffn |
| `moe_layer` | Entire layer encapsulating gate + experts + shared_expert |
| `norm` | Specific RMSNorm / LayerNorm class |
| `decoder_layer` | Complete single decoder layer encapsulation |
| `mtp` | MultiTokenPrediction; when HF has no implementation, `absent_in_hf: true` |
| `lm_head` | Output projection; fill `inline` if no standalone class |
| `model` | Backbone class (without lm_head) |
| `causal_lm` | ForCausalLM top-level class |
| `config` | Config dataclass |

**VLM Additional Components**

| Component Key | Identification Rule |
|---------------|---------------------|
| `vision_patch_embed` | Contains `PatchEmbed` / patch Conv2d |
| `vision_positional_encoding` | Vision-side positional encoding |
| `vision_attention` | Vision encoder side attention |
| `vision_ffn` | Vision encoder side FFN |
| `vision_norm` | Vision encoder side norm |
| `vision_encoder_layer` | Single vision transformer layer |
| `vision_encoder` | Complete vision encoder |
| `vision_model` | Vision tower top-level |
| `projector` | Vision-language projector |
| `vision_config` | Vision Config dataclass |
| `conditional_gen` | ForConditionalGeneration top-level |
| `processor` | Data processor |

Classes not matching any category are placed in `novel_modules`. When a class contains both attention + ffn, classify by actual responsibility and annotate `structural_tags` with `fused_attn_ffn`.

**structural_tags quick reference:**
```
attention:   mla/gqa/mha/mqa, q_lora_rank=N, kv_lora_rank=N, qk_nope_head_dim=N,
             qk_rope_head_dim=N, v_head_dim=N, decoupled_rope, latent_norm, per_head_qknorm
positional:  yarn/ntkscaling/linear_scaling/alibi/2d_rope/3d_rope, factor=N, mscale=N
ffn:         swiglu/geglu/gelu/relu, gate_proj+up_proj+down_proj
moe_gate:    sigmoid/softmax, noaux_tc/aux_loss, group_limited_topk, e_score_correction_bias,
             n_group=N, topk_group=N, norm_topk_prob, routed_scaling_factor=N
norm:        rms_norm/layer_norm, pre_norm/post_norm, eps=N, zero_centered
decoder:     pre_norm, residual, dense_first_k=N, moe_layer_freq=N
```

**`zero_centered` identification rule**: The norm class weights are initialized to `torch.zeros()` (rather than `torch.ones()`) and the forward computation is `output * (1.0 + self.weight.float())`. Affected models: Qwen3-Next (`Qwen3NextRMSNorm`).

**Strategy impact**: When `structural_tags` contains `zero_centered`, Phase 1 Step 2 Branch A must upgrade the `norm` component's strategy from `reuse_ref` to `new_impl` (Megatron standard RMSNorm does not support zero-centered initialization).

**Additional extraction rules (model-agnostic):**

| Rule | Identification / Extraction |
|------|----------------------------|
| R1 `_keep_in_fp32_modules` | Inspect the `PreTrainedModel` subclass for `_keep_in_fp32_modules`. Record **strict_fp32** list (modules named directly) and **non_strict_fp32** list (modules added conditionally via config fields like `bf16_include` / `fp32_include`). If no conditional expansion, non_strict list is empty. |
| R2 Novel module sub-enumeration | For each class placed in `novel_modules`, list all `nn.Module` sub-components from `__init__` and key parameters (scaling constants, `register_buffer(persistent=True)` entries) as `sub_modules` and `key_params`. |
| R3 Novel module count check | After classification, cross-check: `len(novel_modules)` must equal the count of classes not matching any standard component category. Mismatch triggers re-scan. |
| R4 Compressor-internal state | When a novel module's `forward()` maintains cross-call state (e.g., `overlap_kv`, `overlap_gate`, running-window accumulators, rolling buffers), add `has_internal_state` to `structural_tags` and record variable names + roles. |
| R5 Compressor causal masking | When a novel module's `forward()` computes `block_bias`, `causal_threshold`, or similar mask-like logic, add `causal_masking` to `structural_tags` and record the computation. |
| R6 `rope_scaling` sub-fields | When `positional_encoding` `structural_tags` include `yarn` / `ntkscaling` / `linear_scaling`, drill into `config.json` `rope_scaling` sub-dict for `beta_fast`, `beta_slow`, `original_max_position_embeddings`, `mscale`, `mscale_all_dim`. Record as `rope_scaling:<key>=<value>` pairs in `structural_tags`. |
| R7 Config dtype/precision signals | Scan `config.json` for top-level fields signaling dtype/precision (e.g., `expert_dtype`, `torch_dtype`, `bf16`), even if redundant with `quantization_config`. Record as `config_precision_signals`. |
| R8 Generation-mode constraints | Inspect the `PreTrainedModel` subclass for: `_is_stateful` (True = append-only KV cache), non-rewindable cache flags, `_no_split_modules`, `_keys_to_never_split`. Record as `generation_constraints`. |

---

## Stage 2 -- Select Candidate (skipped when `inherited_from`)

**Priority 1: README hint** -- `readme_context.candidate_hint` is non-empty and exists in KB -> use directly.

**Priority 2: config.json field inference** -- Applicable to models without modeling files but with rich config fields (e.g., DSV3.2):
- Parse the `architectures` field (e.g., `DeepseekV32ForCausalLM`) to extract the class prefix, and find the closest matching name among KB families
- Use structural fields in config.json (`q_lora_rank` / `kv_lora_rank` / `n_routed_experts` / `rope_scaling.type`, etc.) to compute overlap matching against the feature fields in KB sources yaml
- Also collect **new fields in config.json not present in known KB family configs** (e.g., `index_head_dim` / `index_n_heads` / `index_topk`) as supplementary `special_arch_notes` candidates

**Priority 3: structural_tags scoring** -- Iterate over KB sources:

| Feature | Weight |
|---------|--------|
| attention type (mla/gqa/mha) | 3 |
| qk_norm presence | 2 |
| moe/dense | 2 |
| mtp presence | 2 |
| positional encoding variant | 1 |
| linear_attention presence | 2 |

When scores are tied, prefer the family matching the attention type.

After the candidate is determined, read `hf_reference_path` from the KB yaml. If the path is TODO or does not exist -> `human_needed`.

**Low confidence degradation rule**: If `top1_score < 5` (or the proportion of `diff=same` among all components is < 30%, confirmed after Stage 3 comparison), append at the top level of `model_spec.yaml`:
```yaml
low_confidence_candidate: true
low_confidence_reason: "Highest match score <N>, only <matched_tags> consistent with candidate family"
```
When Phase 1 Step 2 reads `low_confidence_candidate: true`, it should use `foundation/qwen3/` (dense model) or `foundation/deepseek/` (MoE/MLA model) as the "simplest baseline" reference, rather than directly using the full implementation of a low-quality candidate. Note the degradation reason in the `candidate_reference_note` field of `strategy_plan`.

Read the complete contents of `<hf_reference_path>/modeling_*.py` as the comparison baseline (do not substitute with KB yaml summaries).

---

## Stage 3 -- Per-Component Comparison + README Difference Reconciliation

For each component identified in Stage 1, perform **code-level comparison** against the candidate's corresponding implementation:

| Comparison Priority | Item |
|---------------------|------|
| 1 | Model paradigm (Decoder-only / Encoder-Decoder) |
| 2 | Config-driven paths (key fields such as num_experts / sliding_window) |
| 3 | `__init__` member shape / type |
| 4 | Attention core (MHA/GQA/MLA, QKV dimensions) |
| 5 | MoE mechanism (Router scoring, TopK, shared experts) |
| 6 | Positional encoding (RoPE variant, scaling) |
| 7 | Norm and residual (Pre/Post Norm, type) |
| 8 | FFN (activation function, gating) |
| 9 | Multimodal modules (VLM) |

**Judgment conclusions:**

| diff | Meaning | Preliminary strategy estimate |
|------|---------|-------------------------------|
| `same` | Implementation semantics are equivalent | `reuse_ref` |
| `differs` | Substantive differences exist | `adapt_ref` or `new_impl` |
| `new_component` | Candidate lacks this component | `new_impl` |
| `absent_in_hf` | HF has no implementation but config has the field | `new_impl` |

When `differs`, must fill `delta`, specific to field names and values:
```yaml
delta:
  - "core_attention: DSAttention -> DotProductAttention"
  - "index_head_dim: 128 (new field, DSA indexer dimension)"
```

**README difference reconciliation**: Cross-reference `readme_context.special_arch_notes` with comparison results --

- Each change point described in a note must find its corresponding component and override its `diff` (`differs` or `new_component`)
- If the corresponding implementation is in an external library (e.g., DSAIndexer in tilelang) rather than HF code, add a placeholder entry in `novel_modules` with `external_dependency: true`
- When `modeling_source == "inherited_from"`, this step is the primary source of differences; no note must be missed

**behavior_modifications identification:** Record behavior-only deltas even when the module class already exists or weight shapes look standard. Add an entry when a config field or HF helper changes computation, routing, reference loading, or checkpoint key semantics.

Common examples:
- `activation_func_clamp_value` / `glu_linear_offset`: activation behavior in GLU/SwiGLU paths; validation must use synthetic inputs that cross the clamp threshold.
- `is_mtp_layer` or equivalent layer-context flags: MTP-specific attention/router behavior.
- FP8 scale/key naming or dequantization policy: reference loading and checkpoint conversion behavior.
- Model-specific guard/exception logic, such as hybrid attention SP constraints.
- MTP key layout or tied-head behavior that affects load/save, not just tensor names.

Each entry must include source evidence (`hf_file`, `hf_line`, config fields), required behavior, affected existing modules if known, and a validation hint.

**Additional comparison/extraction rules (model-agnostic):**

| Rule | What to record |
|------|---------------|
| X1 FP32 module lists | Record strict_fp32 / non_strict_fp32 from R1 as a top-level `fp32_modules` section in model_spec.yaml. Compare against candidate; modules absent from candidate's fp32 list go into `delta`. |
| X2 MoE behavior_modifications scope | When a `behavior_modification` references `moe_experts`, explicitly check whether `moe_shared_experts` share the same behavior. If yes, extend `affected_existing_modules` to include `moe_shared_experts`. Do not assume routed and shared experts always diverge. |
| X3 Compressor state as behavior_modification | When a novel module has `has_internal_state` (R4), create a `behavior_modification` entry: `component: <novel_module>`, `behavior_type: state_management`, capturing the state mechanism (rolling overlap, windowed accumulation, etc.). |
| X4 Compressor causal masking as behavior_modification | When a novel module has `causal_masking` (R5), create a `behavior_modification` entry: `component: <novel_module>`, `behavior_type: causal_masking`, capturing the masking logic. |
| X5 `rope_scaling` sub-field comparison | Compare R6 sub-fields against candidate's `rope_scaling`. Fields present in the new model but absent or different in the candidate go into `positional_encoding.delta`. |
| X6 Config dtype/precision comparison | Compare R7 `config_precision_signals` against candidate config. Novel or changed dtype fields go into a top-level `config_precision_delta`. |
| X7 Novel module count verification | Verify `len(novel_modules)` matches R3 count. Mismatch flagged in `traps`. |
| X8 Generation constraints comparison | Compare R8 `generation_constraints` against candidate. Novel constraints (e.g., `_is_stateful=True` when candidate has no such flag) go into a top-level `generation_constraints` section. |

**traps / special_features identification:**
- `routing_bias`: moe_gate forward has bias/correction participating in score -> `special_features.routing_bias`
- `mtp_absent`: config has MTP field but HF has no implementation -> append explanation to `traps`
- `non_standard_qknorm`: attention_norm is full-tensor rather than per-head -> record in `traps`, force `attention.strategy` to `new_impl`
- Inherit known pitfalls from the `traps` field of KB `<candidate_family>.yaml`

---

## Stage 4 -- Write model_spec.yaml


```yaml
model_category: llm
candidate_family: deepseek_v3
hf_reference_path: /path/to/candidate/hf
candidate_match_reason: "..."
has_chat_template: false

components:
  <component_key>:
    diff: same | differs | new_component | absent_in_hf
    strategy: reuse_ref | adapt_ref | new_impl
    delta: []           # Fill when diff=differs
    note: ~             # Fill when README has special notes
    hf_class: ~
    hf_file: ~
    hf_line: ~
    structural_tags: []
    same_class_as: ~

novel_modules:
  - hf_class: DSAIndexer
    hf_file: ~
    hf_line: ~
    desc: "DSA indexer, implemented in tilelang external library"
    external_dependency: true
    sub_modules: []          # R2: nn.Module sub-components from __init__
    key_params: []           # R2: scaling constants, persistent buffers

fp32_modules:
  strict_fp32: []            # R1: modules in _keep_in_fp32_modules directly
  non_strict_fp32: []        # R1: modules added conditionally via config

generation_constraints: []    # R8/X8: _is_stateful, non-rewindable cache, _no_split_modules, etc.

config_precision_delta: []   # X6: dtype/precision fields novel or different vs candidate

behavior_modifications:
  - id: swiglu_clamp_offset
    component: ffn
    behavior_type: activation
    source_evidence:
      hf_file: modeling_<family>.py
      hf_line: 123
      config_fields: [swiglu_limit, glu_linear_offset]
    required_behavior: "Clamp GLU halves and apply linear offset before activation product."
    affected_existing_modules: []
    validation_hint: "Use synthetic inputs exceeding the clamp threshold; random initialization is insufficient."

traps:
  - "..."

special_features:
  routing_bias:
    hf_key: e_score_correction_bias
    desc: "noaux_tc routing load balancing correction bias"
```

## Output

```json
{
  "status": "passed | human_needed",
  "candidate_family": "deepseek_v3",
  "candidate_match_reason": "...",
  "components_same": ["embedding", "ffn", "norm"],
  "components_differs": ["attention"],
  "components_new_impl": ["mtp"],
  "novel_modules": ["DSAIndexer"],
  "behavior_modifications": ["swiglu_clamp_offset"]
}
```

## human_needed Trigger Conditions

| Condition | Description |
|-----------|-------------|
| No modeling files and all three inference paths (transformers fallback / config inference / inherited_from) fail | Cannot determine source code basis |
| No yaml files in KB sources/ | Knowledge base is empty |
| top1 score <= 0 after scoring | No match with any known family |
| `hf_reference_path` is TODO or path does not exist | Cannot read candidate source code |
| `components` section is empty | Scan result abnormal |
