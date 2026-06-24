---
name: megatron-reference-analyzer
description: LoongForge Phase 0 Megatron-side analysis skill. Reads Megatron source code, identifies existing module class signatures, init members, forward flow, and config fields. Produces reference_impl_analysis.yaml. Use when executing Phase 0 Step 5 of model adaptation.
compatibility: Designed for LoongForge /loongforge:adapt workflow (Claude Code or similar)
---

Read Megatron source code, identify existing module class signatures, init members, forward flow, and config fields. Write `reference_impl_analysis.yaml`. This skill is **read-only** -- it never writes code, never opens PRs/issues, and never makes implementation decisions (per D-06: "Phase 0 only analyzes existing Megatron modules"; D-08: "Phase 0 does NOT design new Megatron modules").

## Input

```
megatron_path       -- Megatron-LM repo root (from run_inputs.yml repos.megatron or paths.megatron_path)
component_list      -- List of HF component keys to look up (from hf_analysis.components keys)
candidate_family    -- Candidate family name (from hf_analysis.candidate_family, used for KB lookup)
kb_source_path       -- Optional KB source YAML for the candidate family (knowledge_base/sources/<type>/<family>.yaml)
run_dir              -- Output artifact directory
```

`component_list` format:

```yaml
component_list:
  - embedding
  - positional_encoding
  - attention
  - attention_norm
  - ffn
  - moe_gate
  - moe_experts
  - moe_shared_experts
  - norm
  - decoder_layer
  - mtp
  - hyper_connection
```

---

## Stage 1 -- Module Discovery

For each component in `component_list`:

1. Look up the Megatron module path using `MEGATRON_COMPONENT_MAP.md` Section 5 (component-to-file mapping). For standard components (attention, ffn, norm, etc.), the map provides the primary source file.

2. If component is not in the map, use greedy search:
   ```bash
   grep -r "class <ClassName>" <megatron_path>/megatron/core/ --include="*.py" -l
   ```

3. If no Megatron module is found for a component, record `found: false` and skip to next component. The bridge step will create a gap entry for this component (per D-07).

4. Read the discovered source file, locate the target class, and record:
   - `class_name`: the Megatron class name (e.g., `MLASelfAttention`, `Router`, `HyperConnectionModule`)
   - `source_file`: relative path from `megatron_path` (e.g., `megatron/core/transformer/multi_latent_attention.py`)
   - `base_classes`: list of parent classes (e.g., `["Attention", "MegatronModule"]`)

**Component identification table:**

| Component Key | Megatron Lookup Path |
|---------------|---------------------|
| `embedding` | `megatron/core/transformer/embedding.py` -- `Embedding` class |
| `positional_encoding` | `megatron/core/transformer/rotary_pos_embedding.py` -- `RotaryEmbedding` or model-specific |
| `attention` | `megatron/core/transformer/attention.py` -- `SelfAttention` or `multi_latent_attention.py` -- `MLASelfAttention` or `experimental_attention_variant/` |
| `attention_norm` | `megatron/core/transformer/torch_norm.py` -- `RMSNorm` or `LayerNorm` (applied within attention as q_norm/kv_norm) |
| `ffn` | `megatron/core/transformer/mlp.py` -- `MLP` class |
| `moe_gate` | `megatron/core/transformer/moe/router.py` -- `Router` class or `TopKRouter` class |
| `moe_experts` | `megatron/core/transformer/moe/experts.py` -- `MLP` subclass or `SequentialMLP` |
| `moe_shared_experts` | `megatron/core/transformer/moe/shared_experts.py` -- `SharedExpertMLP` |
| `moe_layer` | `megatron/core/transformer/moe/moe_layer.py` -- `MoELayer` class |
| `norm` | `megatron/core/transformer/torch_norm.py` -- `RMSNorm` or `LayerNorm` |
| `decoder_layer` | `megatron/core/transformer/transformer_layer.py` -- `TransformerLayer` |
| `mtp` | `megatron/core/transformer/multi_token_prediction.py` -- `GPTMultiTokenPrediction` |
| `hyper_connection` | `megatron/core/transformer/hyper_connection.py` -- `HyperConnectionModule` |
| `lm_head` | `megatron/core/models/common/embeddings/embedding.py` or `megatron/core/transformer/mlp.py` -- output projection |
| `model` | `megatron/core/models/gpt/gpt_model.py` -- `GPTModel` class |
| `config` | `megatron/core/transformer/transformer_config.py` -- `TransformerConfig` or `MLATransformerConfig` |

For components not in this table (e.g., novel modules from `hf_analysis.novel_modules`): mark `found: false` with the component name -- the bridge step will create gap entries.

**Discovery heuristic for attention variants:**

When `hf_analysis.components.attention.structural_tags` contain `mla`, look up `multi_latent_attention.py` first, then fall back to `attention.py`. When structural_tags contain experimental variant indicators (e.g., `dsa`, `gated_delta_net`), look up `megatron/core/transformer/experimental_attention_variant/` directory.

**Discovery heuristic for MoE components:**

When `hf_analysis` contains `moe_gate` or `moe_experts`, all three MoE components (gate, experts, shared_experts) should be discovered together from the `moe/` subdirectory.

---

## Stage 2 -- Signature Extraction

For each discovered module:

### 2.1 Parse `__init__` signature

Extract all `self.X = Y(...)` submodule assignments as `init_signature.params`. Each param entry:

| Field | Description | Example |
|-------|-------------|---------|
| `name` | The attribute name assigned to self | `linear_q_proj` |
| `type_hint` | The class used for initialization | `TEColumnParallelLinear` |
| `default_value` | None if conditional, otherwise the default | `None` |
| `description` | Brief role of this sub-module | "Q output projection" |

Example extraction from `MLASelfAttention.__init__`:
```yaml
init_signature:
  params:
    - name: linear_q_proj
      type_hint: TEColumnParallelLinear
      default_value: None
      description: "Q output projection (full-rank)"
    - name: linear_q_down_proj
      type_hint: TEColumnParallelLinear
      default_value: None
      description: "Q latent compression (lora down)"
    - name: linear_q_up_proj
      type_hint: TEColumnParallelLinear
      default_value: None
      description: "Q latent decompression (lora up, grouped output)"
    - name: linear_kv_proj
      type_hint: TEColumnParallelLinear
      default_value: None
      description: "KV latent compression (joint K+V down)"
    - name: core_attention
      type_hint: DotProductAttention
      default_value: None
      description: "Flash attention core"
    - name: q_layernorm
      type_hint: "TENorm or IdentityOp"
      default_value: None
      description: "Q norm on compressed representation"
    - name: kv_layernorm
      type_hint: "TENorm or IdentityOp"
      default_value: None
      description: "KV norm on compressed representation"
    - name: linear_proj
      type_hint: TERowParallelLinear
      default_value: None
      description: "Output projection"
```

### 2.2 Parse `forward` signature

Extract method parameters as `forward_signature.inputs` and return values as `forward_signature.outputs`:

```yaml
forward_signature:
  inputs:
    - name: hidden_states
      type_hint: Tensor
      description: "Input hidden states [s, b, h]"
    - name: attention_mask
      type_hint: "Optional[Tensor]"
      description: "Causal or padding mask"
  outputs:
    - "output: Tensor [s, b, h]"
    - "bias: Optional[Tensor]"
  description: "MLA attention forward with latent compression"
```

### 2.3 Identify config fields used

Read `TransformerConfig` or `MLATransformerConfig` or model-specific config class referenced in `__init__`, record which `config.*` fields control this module's behavior as `config_fields_used`:

```yaml
config_fields_used:
  - field_name: multi_latent_attention
    config_class: TransformerConfig
    usage_description: "Switches from SelfAttention to MLASelfAttention"
  - field_name: q_lora_rank
    config_class: MLATransformerConfig
    usage_description: "Q latent compression dimension"
  - field_name: kv_lora_rank
    config_class: MLATransformerConfig
    usage_description: "KV latent compression dimension"
```

### 2.4 Identify submodule slots

Identify `SubmoduleSpec` or `ModuleSpec` usage in `__init__` -- record as `submodule_slots`. Each slot:

| Field | Description | Example |
|-------|-------------|---------|
| `slot_name` | Name of the submodule slot | `core_attention` |
| `slot_type` | `ModuleSpec` or direct class | `ModuleSpec` |
| `default_class` | Default implementation class | `DotProductAttention` |
| `is_replaceable` | True if the slot can be overridden in layer_spec | `true` |

```yaml
submodule_slots:
  - slot_name: core_attention
    slot_type: ModuleSpec
    default_class: DotProductAttention
    is_replaceable: true
  - slot_name: linear_q_proj
    slot_type: ModuleSpec
    default_class: TEColumnParallelLinear
    is_replaceable: true
  - slot_name: linear_kv_proj
    slot_type: ModuleSpec
    default_class: TEColumnParallelLinear
    is_replaceable: true
```

### 2.5 Identify weight parameters

Scan `__init__` for `nn.Parameter`, `nn.Linear`, `register_buffer` -- record as `weight_params`. Each entry:

| Field | Description | Example |
|-------|-------------|---------|
| `param_name` | Full attribute name (including parent path) | `mapping_proj.weight` |
| `shape_hint` | Shape description | `[n^2 + 2n, n*C]` |
| `dtype` | Data type | `float32` |

```yaml
weight_params:
  - param_name: weight
    shape_hint: "[num_experts, hidden_size]"
    dtype: float32
  - param_name: bias
    shape_hint: "[num_experts]"
    dtype: float32
  - param_name: expert_bias
    shape_hint: "[num_experts]"
    dtype: float32
  - param_name: tid2eid
    shape_hint: "[vocab_size, topk]"
    dtype: int32
```

---

## Stage 3 -- Config Class Analysis

For the candidate family's config class (identified from KB source or by searching for `<family>Config` in the codebase):

1. Read the config class source file
2. Extract all field definitions as `ConfigClassAnalysis.fields`. Each entry:

| Field | Description | Example |
|-------|-------------|---------|
| `field_name` | Attribute name | `q_lora_rank` |
| `type_hint` | Type annotation | `Optional[int]` |
| `default_value` | Default value | `None` |
| `description` | What this field controls | "Q latent compression rank for MLA" |

3. Record parent classes (e.g., `MLATransformerConfig`, `TransformerConfig`)
4. Note which fields are new vs inherited from parent

Example config class analysis for `MLATransformerConfig`:

```yaml
config_classes:
  mlatransformer_config:
    class_name: MLATransformerConfig
    source_file: megatron/core/transformer/transformer_config.py
    parent_classes:
      - TransformerConfig
    fields:
      - field_name: multi_latent_attention
        type_hint: bool
        default_value: "False"
        description: "Enable Multi-Latent Attention (MLA)"
        is_inherited: false
      - field_name: q_lora_rank
        type_hint: "Optional[int]"
        default_value: "None"
        description: "Q latent compression rank"
        is_inherited: false
      - field_name: kv_lora_rank
        type_hint: "Optional[int]"
        default_value: "None"
        description: "KV latent compression rank"
        is_inherited: false
      - field_name: qk_nope_head_dim
        type_hint: int
        default_value: "0"
        description: "Non-positional-encoding head dimension for decoupled RoPE"
        is_inherited: false
      - field_name: qk_rope_head_dim
        type_hint: int
        default_value: "0"
        description: "RoPE head dimension for decoupled RoPE"
        is_inherited: false
      - field_name: v_head_dim
        type_hint: int
        default_value: "0"
        description: "Value head dimension"
        is_inherited: false
      - field_name: hidden_size
        type_hint: int
        default_value: "0"
        description: "Transformer hidden size"
        is_inherited: true
```

When no KB source YAML exists for the candidate family, search the codebase:
```bash
grep -r "class <FamilyName>Config" <megatron_path>/ --include="*.py" -l
```
If no config class is found, record `found: false` for the config analysis.

---

## Stage 4 -- Write reference_impl_analysis.yaml

Write output following the schema from `knowledge_base/schema/reference_impl_analysis_schema.yaml`. Include all discovered modules, config classes, and cross-references.

Output structure:

```yaml
megatron_family: <candidate_family>
source_repo: <repo URL or local path>
source_ref: <branch or commit>
analysis_timestamp: <ISO 8601>

modules:
  <component_key>:
    found: true | false
    class_name: <Megatron class>
    source_file: <relative path>
    base_classes: [...]
    init_signature:
      params: [...]
    forward_signature:
      inputs: [...]
      outputs: [...]
      description: "..."
    config_fields_used: [...]
    submodule_slots: [...]
    weight_params: [...]

config_classes:
  <config_key>:
    class_name: <Config class>
    source_file: <relative path>
    parent_classes: [...]
    fields: [...]
```

For modules where `found: false`, only the `found` and `component_key` fields are required. All other fields are omitted.

### Writing rules

- Every component from `component_list` must have an entry under `modules`, even if `found: false`
- `init_signature.params` entries should use the actual Megatron class names (e.g., `TEColumnParallelLinear`, not `nn.Linear`)
- `config_fields_used` should reference the most specific config class (e.g., `MLATransformerConfig` for MLA fields, not `TransformerConfig`)
- `submodule_slots.is_replaceable` is true when the slot is specified in a `ModuleSpec` (not hardwired) -- this is critical for Phase 1 strategy decisions
- `weight_params` should include both `nn.Parameter` and `register_buffer` entries, as both become weights in the checkpoint
- When a Megatron module uses `multiacc_modules` dispatch, record the TE class name in `type_hint` and note the local fallback in `description`

---

## Output

```json
{
  "status": "passed | human_needed",
  "megatron_family": "deepseek_v3",
  "modules_found": ["attention", "ffn", "moe_gate", "norm", "hyper_connection"],
  "modules_not_found": ["csa_indexer", "hash_router"],
  "config_classes_found": ["mlatransformer_config"],
  "total_weight_params": 15
}
```

## human_needed Trigger Conditions

| Condition | Description |
|-----------|-------------|
| `megatron_path` is not provided or does not contain `megatron/core/transformer/` directory | Cannot access Megatron source |
| No modules can be discovered for ANY standard component (total failure) | Megatron codebase appears empty or misconfigured |
| KB source YAML for `candidate_family` references files that don't exist in the provided `megatron_path` | KB is out of date; may need re-indexing |

## Key Constraints (per D-06, D-08)

This skill ONLY reads and extracts. It does NOT:

- Design new Megatron modules -- that is Phase 1's job
- Write code of any kind -- this is a pure analysis skill
- Make implementation decisions -- it only records what exists and what is absent
- Open PRs, issues, or modify any external repository -- Phase 0 does not use the Loop FSM (per D-15)

If a Megatron module does not exist for a component, it records `found: false`. That is the complete and correct behavior. Designing new modules to fill those gaps is Phase 1's responsibility.

## Relationship to Other Skills

- **hf-model-analyzer** (Stage 1-3): Produces `hf_analysis.yaml` which provides the `component_list` and `candidate_family` inputs to this skill
- **Bridge Step** (Phase 0 Step 5.5): Combines `hf_analysis.yaml` + this skill's `reference_impl_analysis.yaml` to produce `bridge_mapping.yaml` (per D-19)
- **MEGATRON_COMPONENT_MAP.md**: Provides the authoritative component-to-file mapping used by Stage 1
- **knowledge_base/sources/**: Provides family-specific reference information for Stage 3
