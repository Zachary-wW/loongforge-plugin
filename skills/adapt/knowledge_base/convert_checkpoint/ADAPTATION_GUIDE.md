# New Model Weight Conversion Adaptation Guide

> Version: v1.0 | Updated: 2026-04-16
> Related Pages: [ARCHITECTURE](ARCHITECTURE.md) | [MODULE_FORMATS](MODULE_FORMATS.md) | [CUSTOM_CONVERTERS](CUSTOM_CONVERTERS.md)
> Associated Phase: Phase 2 (Weight Conversion)

This document describes the complete operational workflow for adapting weight conversion for a new model.

---

## Overall Decision Flow

```
A parameter in the new model
    |
    +-- Can an existing semantic name match it?
    |   +-- Yes -> Only write YAML name_map mapping (zero code changes)
    |
    +-- No (new module)
       |
       +-- Tensor layout consistent with existing patterns? (ordinary Linear/LayerNorm)
       |   +-- Yes -> Tier 1: Add constant + add to BASE_NAMES + write name_map
       |
       +-- No
          |
          +-- Only split/concat/interleave layout differs?
          |   +-- Yes -> Tier 2: + custom converter
          |
          +-- Iteration semantics differ (non-per-layer / special indexing)
              +-- Tier 3: + new classification list + modify orchestration layer
```

Most new models fall into **Tier 1** (pure configuration) or can be mapped to existing formats. Tier 2 occasionally appears; Tier 3 is rare.

---

## Step 1: Analyze HF Weight Structure

Phase 0 has already fully extracted the HF weight structure and written it to the `weight_structure` section of `run_dir/model_spec.yaml`. **No need to re-scan the HF checkpoint**.

Read `weight_structure.components.*.sample_keys` directly to list representative keys for each component (e.g., `model.layers.0.self_attn.q_proj.weight`), and classify them into existing formats in MODULE_FORMATS.md.

> If `sample_keys` are insufficient for determination, use `components[*].hf_file / hf_line` pointers to read HF source code for confirmation.

---

## Step 2: Per-Module Matching

Follow the decision quick-reference table (Section 8) in [MODULE_FORMATS.md](MODULE_FORMATS.md) to determine each module. The decision tree covers:

- **Attention**: MLA → Partial MLA → Mixer Attention → Gated Attention → Standard QKV separated → Standard QKV fused → New format
- **MLP**: Vision Encoder gated/ungated vs LLM Gated MLP
- **MoE**: Dict-for-expert → Shared Expert (with optional gate) → Gate Bias → Standard per-expert
- **MTP**: DeepSeek style → Qwen 3.5 style → MIMO style

For each module, match the `sample_keys` patterns against the format descriptions in MODULE_FORMATS.md Sections 1-5.

---

## Step 3: Write Conversion YAML

Create the configuration in `configs/models/<family>/ckpt_convert/<family>_convert.yaml`.

### Minimal Template (Dense LLM)

Reference: `configs/models/qwen3/ckpt_convert/qwen3_convert.yaml`.

```yaml
hydra:
  searchpath:
    - file://${oc.env:LOONGFORGE_PATH}/configs/models/

defaults:
  - <family>@module: ???   # Reference the corresponding model YAML, making parameters available via ${module.*}
  - _self_

args:
  common:
    num_layers: ${module.num_layers}
    hidden_size: ${module.hidden_size}
    num_attention_heads: ${module.num_attention_heads}
    num_key_value_heads: ${module.num_query_groups}
    ffn_hidden_size: ${module.ffn_hidden_size}
  mcore:
    untie_embeddings_and_output_weights: ${module.untie_embeddings_and_output_weights}
    transpose_query_key_value: true
    transpose_mlp_dense: true
    add_embedding_padding: true
    make_vocab_size_divisible_by: ${module.make_vocab_size_divisible_by}
    use_rotary_position_embeddings: true

name_map:
  huggingface:
    word_embeddings: model.embed_tokens
    transformer: model           # HF top-level module name
    layer_prefix: layers         # Per-layer prefix
    input_layernorm: input_layernorm
    attention.query_key_value:
      - self_attn.q_proj
      - self_attn.k_proj
      - self_attn.v_proj
    attention.dense: self_attn.o_proj
    post_attention_layernorm: post_attention_layernorm
    mlp.dense_h_to_4h:
      - mlp.gate_proj
      - mlp.up_proj
    mlp.dense_4h_to_h: mlp.down_proj
    final_layernorm: model.norm
    word_embeddings_for_head: ${module.word_embeddings_for_head}
  mcore:
    word_embeddings: embedding.word_embeddings
    transformer: model
    layer_prefix: decoder.layers
    input_layernorm:
      name: self_attention.linear_qkv
      is_layernorm: true
    attention.query_key_value:
      name: self_attention.linear_qkv
      extra: true
    attention.dense:
      name: self_attention.linear_proj
      extra: true
    post_attention_layernorm:
      name: mlp.linear_fc1
      is_layernorm: true
    mlp.dense_h_to_4h:
      name: mlp.linear_fc1
      extra: true
    mlp.dense_4h_to_h:
      name: mlp.linear_fc2
      extra: true
    final_layernorm:
      name: decoder.final_layernorm
      extra: true
    word_embeddings_for_head: output_layer

torch_dtype: bfloat16
```

> **Note**: `transformer` and `layer_prefix` are placed in `name_map.huggingface` / `name_map.mcore`, not in `args.huggingface`. `args.huggingface` is only for HF config fields (architectures / model_type, etc.) and can be omitted.

### QK-Norm Addition

```yaml
# huggingface
attention.q_a_layernorm: self_attn.q_norm
attention.kv_a_layernorm: self_attn.k_norm
# mcore
attention.q_a_layernorm:
  name: self_attention.q_layernorm
attention.kv_a_layernorm:
  name: self_attention.k_layernorm
```

### MoE Addition

```yaml
# huggingface
moe.gate: mlp.gate
moe.expert_h_to_4h:
  - gate_proj
  - up_proj
moe.expert_4h_to_h: down_proj
# mcore
moe.gate:
  name: mlp.router
moe.expert_h_to_4h:
  name: mlp.experts.local_experts.linear_fc1
  extra: true
moe.expert_4h_to_h:
  name: mlp.experts.local_experts.linear_fc2
  extra: true
```

### MTP Addition

Reference MODULE_FORMATS.md Section 5 to select the style (5A/5B/5C), and add the corresponding entries.

---

## Step 4: Handle Brand-New Modules (Tier 1/2/3)

### Tier 1: New Parameters, Standard Layout (Pure Configuration)

Files to modify:

| File | Operation |
|------|-----------|
| `tools/convert_checkpoint/common/common_checkpoint.py` | Add semantic constant + add to `BASE_NAMES` (or other classification list) |
| `configs/models/<family>/ckpt_convert/<family>_convert.yaml` | Add HF/mcore mapping in name_map |
| `tools/convert_checkpoint/mcore/mcore_base.py` | If TP slicing is needed, register in `TENSOR_PARALLEL_DIM` |

Example: DeepSeek V3.2's `attention.indexer.*` parameters are Tier 1 -- each is a simple 1-to-1 linear layer mapping.

### Tier 2: Custom Tensor Transformation or Hook Required

In addition to Tier 1, also required:

| File | Operation |
|------|-----------|
| `huggingface/util/hf_<name>_converter.py` | Create new converter class, implement `cat_*()` / `split_*()` |
| `huggingface/huggingface_base.py` | Add if/elif branch in `hf_to_common()` / `common_to_hf()` |
| `mcore/util/mcore_<name>_converter.py` | (If needed) Create new mcore-side converter, implement `chunk_*()` |
| `mcore/mcore_base.py` | (If needed) Add branch |

Converter design specifications:
- HF side: `cat_*()` receives `value_list` (multiple HF tensors), returns a single common tensor
- HF side: `split_*()` receives `(tag_names, fused_tensor)`, returns a list of HF tensors
- mcore side: `chunk_*()` receives `(fused_tensor, tp_size)`, returns `tp_size` shard list

Hook strategy specifications:
- `insert_load_preprocess`: normalize keys, split packed fields, dequant/rename FP8 scales, or materialize tied tensors before generic mapping
- `insert_save_postprocess`: merge split fields, restore HF key names, copy tied tensors, or restore metadata after generic mapping
- `override_parallel_dim`: append or override TP dimension entries only for the new semantic constant
- `custom_roundtrip_rule`: declare model-specific expected differences and tolerances with evidence

Do not change existing converter algorithms during ordinary adaptation. If the only correct solution is to alter an existing branch, classify it as `modify_existing` or `insert_hook` and return `human_needed` unless framework-bugfix authorization exists.

Reference implementation: See [CUSTOM_CONVERTERS.md](CUSTOM_CONVERTERS.md)

### Tier 3: New Iteration Semantics

In addition to Tier 1, also required:

| File | Operation |
|------|-----------|
| `common/common_checkpoint.py` | Define new classification list (e.g., `MY_NEW_NAMES = [...]`) |
| `common/common_config.py` or args | Add control parameters (e.g., `my_new_num_layers`) |
| `huggingface/huggingface_checkpoint.py` | Add new traversal block in `convert_to_common()` / `convert_from_common()` |
| `mcore/mcore_checkpoint.py` | Same as above |

Historical precedent: MTP layers are Tier 3 -- requiring `MTP_NAMES` list, `mtp_num_layers` parameter, independent traversal block.

If a new model only needs extra preprocessing/postprocessing around an existing traversal, prefer `insert_load_preprocess` / `insert_save_postprocess` over changing the traversal body. If no safe hook exists, return `human_needed` with `failure_gate="protected_file_change_required"`.

---

## Step 5: Verification

### Convert Dry-Run

```bash
python tools/convert_checkpoint/module_convertor/model.py --dry-run \
    --config_file configs/models/<family>/<model>.yaml \
    --convert_file configs/models/<family>/ckpt_convert/<family>_convert.yaml
```

Acceptance criteria: No missing keys, no duplicate keys, no shape errors.

### HF -> mcore -> HF Roundtrip

1. HF -> mcore
2. mcore -> HF
3. Compare original HF with roundtrip HF:
   - Key set symmetric difference is empty
   - Each tensor shape is identical
   - Each tensor values are consistent (`max_abs_diff < 1e-6`)

### Common Issue Troubleshooting

| Symptom | Most Likely Cause | Fix Direction |
|---------|------------------|---------------|
| Missing key | A parameter was omitted in name_map | Cross-check with HF state_dict and add |
| Duplicate key | Same HF key mapped to multiple common keys | Check name_map for duplicates |
| Shape error (TP>1) | QKV missing `transpose_query_key_value` | Add in args.mcore |
| Shape error (MLP) | gate+up concatenation order wrong | Check list order |
| Roundtrip numerical mismatch | FP8 precision loss (normal), or converter bug | Use `atol=1e-2` for FP8; otherwise check converter |
| MoE expert weights missing | Not registered in `MOE_EXPERT_PROJS` | Check common_checkpoint.py |
| MTP weights missing | Not registered in `MTP_NAMES` | Check common_checkpoint.py |

---

## Reference File Index

| What to Look Up | Path |
|----------------|------|
| Existing Dense convert YAML (simplest baseline) | `configs/models/qwen3/ckpt_convert/qwen3_convert.yaml` |
| Existing Dense convert YAML (LLaMA style) | `configs/models/llama3/ckpt_convert/llama3_convert.yaml` |
| Existing MoE+MLA+MTP convert YAML | `configs/models/deepseek3/ckpt_convert/deepseek_v3_convert.yaml` |
| Existing Mixer+Gated convert YAML | `configs/models/qwen3.5/ckpt_convert/qwen3_5_dense_convert.yaml` |
| Existing VLM three-stage conversion | `examples/internvl3.5/checkpoint_convert/` |
| CommonCheckpoint semantic constants | `tools/convert_checkpoint/common/common_checkpoint.py` |
| TP slicing dimension dictionary | `tools/convert_checkpoint/mcore/mcore_base.py` -> `TENSOR_PARALLEL_DIM` |
| HF-side branching logic | `tools/convert_checkpoint/huggingface/huggingface_base.py` -> `hf_to_common()` |
| mcore-side branching logic | `tools/convert_checkpoint/mcore/mcore_base.py` -> `common_to_mcore()` |
