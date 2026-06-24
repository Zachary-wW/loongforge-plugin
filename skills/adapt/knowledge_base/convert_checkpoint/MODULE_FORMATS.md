# Module Weight Format Overview

> Version: v1.0 | Updated: 2026-04-16
> Related Pages: [ARCHITECTURE](ARCHITECTURE.md) | [CUSTOM_CONVERTERS](CUSTOM_CONVERTERS.md) | [ADAPTATION_GUIDE](ADAPTATION_GUIDE.md)

This document lists all supported weight storage formats by module category, along with the corresponding models.
When adapting a new model, first consult this document to determine which existing format each module belongs to.

---

## 1. Attention Module

### 1A. Standard QKV -- Three Separate Projections (Most Common)

HF stores three independent tensors `q_proj`/`k_proj`/`v_proj`; during conversion, cat/split + GQA interleave.

```yaml
# name_map.huggingface
attention.query_key_value:
  - self_attn.q_proj      # [num_heads * head_dim, hidden_size]
  - self_attn.k_proj      # [num_kv_heads * head_dim, hidden_size]
  - self_attn.v_proj      # [num_kv_heads * head_dim, hidden_size]

# name_map.mcore
attention.query_key_value:
  name: self_attention.linear_qkv
  extra: true
```

mcore parameter: `transpose_query_key_value: true`

Custom converter: `HfAttnQkvConverter.cat_attn_qkv()` / `split_attn_qkv()`

Applicable models:
- LLaMA 2/3/3.1
- Qwen 1.5, Qwen 2, Qwen 2.5
- Qwen 3 (all variants: dense, intern, llava, qwen3vl, MoE)
- MiniMax (MoE)
- MIMO
- ERNIE 4.5 VL (LLM part)
- Kimi K2

### 1B. Standard QKV -- Single Fused Tensor

HF stores a single `qkv`/`wqkv`/`c_attn` fused tensor; no split needed on the HF side.

```yaml
# name_map.huggingface
attention.query_key_value: attn.qkv   # Single string, not a list
```

| HF Key | Model | `transpose_query_key_value` |
|--------|-------|----------------------------|
| `attn.c_attn` | Qwen v1 | `true` |
| `attention.wqkv` | InternLM 2.5 | `false` (unique) |
| `attn.qkv` / `wqkv` | All Vision Encoders | `true` |

Custom converter: Same as `HfAttnQkvConverter` (`len(qkv_names)==1` branch)

### 1C. Gated Attention QKV

Q dimension doubled (includes gate), interleaved per KV group `[q+gate, k, v]`.

```yaml
# name_map.huggingface
attention.query_gate_key_value:
  - self_attn.q_proj      # [2 * num_querys_per_group * head_dim * num_kv_heads, hidden_size]
  - self_attn.k_proj
  - self_attn.v_proj
```

Custom converters:
- HF side: `HfAttnGateQkvConverter.cat_attn_qgkv()` / `split_attn_qgkv()`
- mcore side: `McoreAttnGateQkvConverter.chunk_gqkv()` -- during TP slicing, chunk Q/K/V separately then reassemble

Applicable models: **Qwen 3.5** (dense + MoE), **Qwen3_next**

### 1D. MLA (Multi-head Latent Attention)

Q/KV each have down+up low-rank projections + layernorm, **no standard QKV**.

> **Canonical key names**: MLA uses `kv_down`/`kv_norm` (not `kv_shared`/`kv_shared_layernorm`) as the
> canonical LoongForge key names for the KV compression path. The `kv_up_layernorm` key name is likewise
> canonical (not `kv_shared_layernorm`). All adapt name maps must use these canonical names.
>
> **Layernorm mapping**: In mcore, MLA layernorms are **separate extra modules** --
> `self_attention.kv_layernorm` and `self_attention.q_layernorm` -- not `is_layernorm` flags on
> projection modules. Do not attempt to fuse MLA layernorms into their adjacent projections the way
> standard layernorms fuse into `linear_qkv` (6A). MLA layernorms always map as independent entries:
> ```yaml
> # name_map.mcore (MLA layernorms are standalone modules)
> attention.q_up_layernorm:  self_attention.q_layernorm
> attention.kv_up_layernorm: self_attention.kv_layernorm
> ```

```yaml
# name_map.huggingface (6 independent entries)
attention.q_down:   self_attn.q_a_proj
attention.q_up:     self_attn.q_b_proj
attention.q_up_layernorm:  self_attn.q_a_layernorm
attention.kv_down:  self_attn.kv_a_proj_with_mqa
attention.kv_up:    self_attn.kv_b_proj
attention.kv_up_layernorm: self_attn.kv_a_layernorm
```

No custom converter -- each is a simple 1-to-1 mapping.

Applicable models: **DeepSeek V2/V3/V3.2**, **ERNIE 4.5 VL** (LLM part), **Kimi K2**

### 1E. Partial MLA

Only KV uses MLA low-rank projection; Q is directly projected (no q_down/q_up).

```yaml
attention.q: self_attn.q_proj       # Direct Q projection, no low-rank decomposition
attention.kv_down: self_attn.kv_a_proj_with_mqa
attention.kv_up:   self_attn.kv_b_proj
attention.kv_up_layernorm: self_attn.kv_a_layernorm
```

Applicable models: **DeepSeek V2 Lite** (only)

### 1F. Lightning Indexer (Sparse MLA)

Adds an indexer sub-module on top of MLA for sparse attention indexing.

```yaml
# name_map.huggingface
attention.indexer.k_norm:       self_attn.indexer.k_norm
attention.indexer.weights_proj: self_attn.indexer.weights_proj
attention.indexer.wk:           self_attn.indexer.wk          # fp8: true
attention.indexer.wq_b:         self_attn.indexer.wq_b        # fp8: true
```

Applicable models: **DeepSeek V3.2** (only)

### 1G. Mixer Attention (SSM/DeltaNet Linear Attention)

Completely different from Transformer attention; includes `in_proj`, `conv1d`, `A_log`, `dt_bias` and other parameters.

```yaml
# name_map.huggingface
mixer_att.log:            { name: linear_attn.A_log, is_direct_name: true }
mixer_att.dt_bias:        { name: linear_attn.dt_bias, is_direct_name: true }
mixer_att.conv1d:         linear_attn.conv1d
mixer_att.norm:           linear_attn.norm
mixer_att.out_proj:       linear_attn.out_proj
# Qwen 3.5 style (HF stores qkv+z separately, needs interleave)
mixer_att.in_proj_qkvz:   [linear_attn.in_proj_qkv, linear_attn.in_proj_z]
mixer_att.in_proj_ba:     [linear_attn.in_proj_b, linear_attn.in_proj_a]
# Qwen3_next style (HF already fused, single string)
mixer_att.in_proj_qkvz:   linear_attn.in_proj_qkvz
mixer_att.in_proj_ba:     linear_attn.in_proj_ba
```

mcore side mostly marked `ignore_tp: true`.

Custom converters:
- HF side: `HfMixerAttnConverter.cat_qkv_z_to_qkvz()` / `split_qkvz_to_qkv_z()` / `cat_b_a_to_ba()` / `split_ba_to_b_a()`
- mcore side: `McoreMixerAttnConverter.chunk_mixer_in_proj_qkvz()` / `chunk_mixer_in_proj_ba()`

Special mechanism: **Hybrid architecture** -- within the same model, some layers use Gated Attention and some use Mixer Attention, distinguished via `depend_on_key`:
```yaml
input_layernorm:        { name: input_layernorm, depend_on_key: attention.query_gate_key_value }
mixer_input_layernorm:  { name: input_layernorm, depend_on_key: mixer_att.log }
```

Applicable models: **Qwen 3.5** (dense + MoE), **Qwen3_next**

### 1H. QK-Norm (Additional Feature, Combined with Above Formats)

Per-head normalization after Q/K projection, as an independent entry in `BASE_NAMES`.

```yaml
attention.q_a_layernorm: self_attn.q_norm
attention.kv_a_layernorm: self_attn.k_norm
```

Applicable models (stacked on top of 1A/1C): Qwen 3 full series, MiniMax, Qwen 3.5, Qwen3_next, InternVL ViT 6B

### 1I. HyperConnection (Multi-Head Hyper Connection)

Each HyperConnection (HC) decomposes into 5 parameters: `fn`, `base`, `alpha_pre`, `alpha_post`, `alpha_res`.
Attention-side and FFN-side HC are separate module groups (`hc_attn_*` / `hc_ffn_*` in HF).

```yaml
# name_map.huggingface -- attention HC
attention.hc_attn_fn:         { name: hc_attn_fn, is_direct_name: true }
attention.hc_attn_base:       { name: hc_attn_base, is_direct_name: true }
attention.hc_attn_alpha_pre:  { name: hc_attn_alpha_pre, is_direct_name: true }
attention.hc_attn_alpha_post:  { name: hc_attn_alpha_post, is_direct_name: true }
attention.hc_attn_alpha_res:  { name: hc_attn_alpha_res, is_direct_name: true }

# name_map.huggingface -- FFN HC
attention.hc_ffn_fn:         { name: hc_ffn_fn, is_direct_name: true }
attention.hc_ffn_base:       { name: hc_ffn_base, is_direct_name: true }
attention.hc_ffn_alpha_pre:  { name: hc_ffn_alpha_pre, is_direct_name: true }
attention.hc_ffn_alpha_post: { name: hc_ffn_alpha_post, is_direct_name: true }
attention.hc_ffn_alpha_res:  { name: hc_ffn_alpha_res, is_direct_name: true }

# name_map.mcore -- attention HC
attention.hc_attn_fn:         { name: self_attention_hyper_connection.mapping_proj, ignore_tp: true }
attention.hc_attn_base:       { name: self_attention_hyper_connection.bias, ignore_tp: true }
attention.hc_attn_alpha_pre:  { name: self_attention_hyper_connection.alpha_pre, ignore_tp: true }
attention.hc_attn_alpha_post: { name: self_attention_hyper_connection.alpha_post, ignore_tp: true }
attention.hc_attn_alpha_res:  { name: self_attention_hyper_connection.alpha_res, ignore_tp: true }

# name_map.mcore -- FFN HC
attention.hc_ffn_fn:         { name: mlp_hyper_connection.mapping_proj, ignore_tp: true }
attention.hc_ffn_base:       { name: mlp_hyper_connection.bias, ignore_tp: true }
attention.hc_ffn_alpha_pre:  { name: mlp_hyper_connection.alpha_pre, ignore_tp: true }
attention.hc_ffn_alpha_post: { name: mlp_hyper_connection.alpha_post, ignore_tp: true }
attention.hc_ffn_alpha_res:  { name: mlp_hyper_connection.alpha_res, ignore_tp: true }
```

No custom converter -- each parameter is a simple 1-to-1 mapping. All mcore HC entries carry `ignore_tp: true` because HC parameters are not partitioned by tensor parallel.

Applicable models: Any model with multi-head HyperConnections (e.g. DeepSeek V3+, V4, and future mHC models)

### 1J. Grouped Output Projection (Split wo)

MLA models with split output projections store `wo` as two separate tensors: `wo_a` (group projection) and `wo_b` (final projection).

```yaml
# name_map.huggingface
attention.wo_a: self_attn.wo_a    # group output projection
attention.wo_b: self_attn.wo_b    # final output projection

# name_map.mcore
attention.wo_a:
  name: self_attention.linear_o_group_proj
  is_direct_name: true
  # bare Parameter (no RowParallelLinear wrapper)

attention.wo_b:
  name: self_attention.linear_proj
  extra: true
  fp8: true
  # RowParallelLinear
```

Tensor-parallel dimension entries:
```yaml
tensor_parallel_dim:
  attention.wo_a: 0
  attention.wo_b: 1
```

No custom converter -- each is a simple 1-to-1 mapping. `wo_a` uses a bare `Parameter` in mcore (not wrapped in `RowParallelLinear`), hence `is_direct_name: true`. `wo_b` is the standard output projection with `extra: true` and optional `fp8: true`.

Applicable models: Any MLA model with split output projections

### Attention-Internal Sub-module Hierarchy

Attention-internal sub-modules (e.g. `attn_sink`, `compressor`, `indexer`) reside under `self_attention.core_attention.*` in mcore, **not** directly under `self_attention.*`. When mapping such modules, the mcore path must include the `core_attention` intermediate:

```yaml
# WRONG:
attention.indexer.wk: self_attention.indexer.wk

# CORRECT:
attention.indexer.wk: self_attention.core_attention.indexer.wk
```

This applies to any model with attention-internal sub-modules (sparse attention indexers, sink tokens, KV compressors, etc.).

---

## 2. MLP Module

### 2A. Gated MLP -- SwiGLU/GeGLU (Common Format)

`gate_proj + up_proj` concatenated into one tensor.

```yaml
# name_map.huggingface (list = cat)
mlp.dense_h_to_4h:
  - mlp.gate_proj    # [ffn_hidden_size, hidden_size]
  - mlp.up_proj      # [ffn_hidden_size, hidden_size]
# -> common: [2 * ffn_hidden_size, hidden_size]
mlp.dense_4h_to_h: mlp.down_proj
```

HF naming variants (same format):

| HF Key | Model |
|--------|-------|
| `mlp.gate_proj` / `mlp.up_proj` | LLaMA 2/3, Qwen 1.5~3.5, MIMO, DeepSeek |
| `mlp.w2` / `mlp.w1` | Qwen v1 |
| `feed_forward.w1` / `feed_forward.w3` | InternLM 2.5 |

Applicable models: Almost all Dense LLMs

### 2B. Ungated MLP -- Standard FC

Single `fc1` + `fc2`, no split/cat.

```yaml
mlp.dense_h_to_4h: mlp.fc1    # Single string, not a list
mlp.dense_4h_to_h: mlp.fc2
```

HF naming variants:

| HF Key | Model |
|--------|-------|
| `mlp.fc1` / `mlp.fc2` | LLaVA VIT, InternVL ViT, Moon ViT 3D, ERNIE VL VIT |
| `mlp.linear_fc1` / `mlp.linear_fc2` | Qwen3 VIT, Qwen3.5 VIT |

Applicable models: **All Vision Encoders** (except Qwen2.5 VIT)

### 2C. Gated Vision MLP (Special)

Rare gated MLP in Vision Encoder.

```yaml
mlp.dense_h_to_4h:
  - mlp.gate_proj
  - mlp.up_proj
```

Applicable models: **Qwen2.5 VIT** (only Vision Encoder using gated MLP)

---

## 3. MoE Module

### 3A. MoE Gate (Router)

```yaml
moe.gate: mlp.gate    # or block_sparse_moe.gate (MiniMax)
```

Gate Bias (learnable load-balancing bias):
```yaml
moe.gate.bias: mlp.gate.e_score_correction_bias   # mcore: mlp.router.expert_bias
```

Models with gate bias: DeepSeek V3/V3.2, MiniMax, ERNIE 4.5 VL, Kimi K2

### 3B. Standard per-expert MLP

Each expert is stored independently with `gate_proj`/`up_proj`/`down_proj`:

```yaml
moe.expert_h_to_4h:
  - gate_proj
  - up_proj
moe.expert_4h_to_h: down_proj
```

HF path: `mlp.experts.{expert_id}.gate_proj.weight`

Applicable models: DeepSeek V2/V3/V3.2, Qwen 3 MoE, MiniMax, ERNIE 4.5 VL, Kimi K2

### 3C. Dict-for-expert (Stacked Tensor Format)

All experts stacked as 3D tensors + transpose:

```yaml
moe.expert_h_to_4h:
  name: gate_up_proj
  is_direct_name: true
  is_dict_for_expert: true
  need_transpose: true
moe.expert_4h_to_h:
  name: down_proj
  is_direct_name: true
  is_dict_for_expert: true
  need_transpose: true
```

Applicable models: **Qwen3 MoE (qwen3vl)**, **Qwen 3.5 MoE**

### 3D. Shared Expert

Independent-path shared expert, same structure as Dense MLP:

```yaml
moe.shared_expert_h_to_4h:
  - mlp.shared_experts.gate_proj
  - mlp.shared_experts.up_proj
moe.shared_expert_4h_to_h: mlp.shared_experts.down_proj
```

Applicable models: DeepSeek V2/V3/V3.2, ERNIE 4.5 VL, Kimi K2, Qwen 3/3.5 MoE, Qwen3_next

### 3E. Shared Expert Gate

Independent gate weight for the shared expert:

```yaml
moe.shared_expert_gate: mlp.shared_expert_gate   # mcore: mlp.shared_experts.gate_weight
```

Applicable models: **Qwen 3.5 MoE**, **Qwen3_next** (other MoE models do not have this weight)

### 3F. MTP MoE

The MTP layer itself is also MoE, with independent expert mapping entries:

```yaml
mtp_moe.expert_h_to_4h: ...
mtp_moe.expert_4h_to_h: ...
mtp_moe.shared_expert_h_to_4h: ...
mtp_moe.shared_expert_4h_to_h: ...
```

Applicable models: **Qwen 3.5 MoE** (only)

---

## 4. Embedding Module

### 4A. Word Embeddings

```yaml
word_embeddings: model.embed_tokens   # Common
```

HF naming variants:

| HF Key | Model |
|--------|-------|
| `model.embed_tokens` | LLaMA 2/3, Qwen 1.5~3, DeepSeek, MIMO |
| `model.language_model.embed_tokens` | Qwen 3.5 |
| `language_model.model.embed_tokens` | Qwen (intern), Kimi K2 |
| `language_model.model.tok_embeddings` | InternLM 2.5 |
| `transformer.wte` | Qwen v1 |

### 4B. Output Head

```yaml
word_embeddings_for_head: lm_head    # Untied embeddings (most models)
```

HF naming variants:

| HF Key | Model |
|--------|-------|
| `lm_head` | LLaMA, Qwen 1.5/2/3, DeepSeek, MiniMax, MIMO, Qwen 3.5 |
| `language_model.lm_head` | Qwen (intern), Kimi K2 |
| `language_model.output` | InternLM 2.5 |

Tied embeddings: When `word_embeddings_for_head` is null/None, `word_embeddings` weights are automatically reused.

---

## 5. MTP (Multi-Token Prediction) Module

### 5A. DeepSeek Style

Fixed `mtp_layer_id`, `mtp_eh_proj` supports cross-dtype (HF bf16 <-> mcore fp8).

```yaml
mtp_word_embeddings: embed_tokens
mtp_enorm: enorm
mtp_hnorm: hnorm
mtp_eh_proj: { name: eh_proj, dtype: bf16 }    # mcore side dtype: fp8
mtp_shared_head_norm: shared_head.norm
mtp_shared_head_head: shared_head.head
```

Applicable models: **DeepSeek V3/V3.2**, **ERNIE 4.5 VL**

### 5B. MIMO Style

`mtp_word_embeddings` is null (shared main embedding), no `mtp_shared_head_head`.

```yaml
mtp_word_embeddings: null       # Shared
mtp_enorm: token_layernorm
mtp_hnorm: hidden_layernorm
mtp_eh_proj: input_proj
mtp_shared_head_norm: final_layernorm
```

Applicable models: **MIMO**

### 5C. Qwen 3.5 Style

Independent `mtp` transformer prefix, all entries marked `no_layer_id: true`.

```yaml
mtp_word_embeddings: null
mtp_enorm: { name: mtp.pre_fc_norm_embedding, no_layer_id: true }
mtp_hnorm: { name: mtp.pre_fc_norm_hidden, no_layer_id: true }
mtp_eh_proj: { name: mtp.fc, no_layer_id: true }
mtp_shared_head_norm: { name: mtp.norm, no_layer_id: true }
```

Applicable models: **Qwen 3.5** (dense + MoE), **Qwen3_next**

---

## 6. LayerNorm Module

### 6A. Standard LayerNorm

```yaml
input_layernorm: input_layernorm
post_attention_layernorm: post_attention_layernorm
final_layernorm: model.norm
```

mcore side fused storage: `input_layernorm` stored under `self_attention.linear_qkv` node (`is_layernorm: true`).

HF naming variants:

| Semantic Name | HF Key Variant | Model |
|--------------|----------------|-------|
| `input_layernorm` | `ln_1` | Qwen v1 |
| `input_layernorm` | `attention_norm` | InternLM 2.5 |
| `input_layernorm` | `norm1` | Vision Encoder (Qwen/InternVL) |
| `post_attention_layernorm` | `ln_2` | Qwen v1 |
| `post_attention_layernorm` | `ffn_norm` | InternLM 2.5 |
| `post_attention_layernorm` | `norm2` | Vision Encoder (Qwen/InternVL) |

### 6B. Layer Scale

Per-layer learnable scaling factor in ViT.

```yaml
post_attention_layerscale: { name: ls1, is_direct_name: true }
post_mlp_layerscale: { name: ls2, is_direct_name: true }
```

Applicable models: **InternVL ViT 6B**, **InternVL ViT 0.3B**, **ERNIE VL VIT**

### 6C. Mixer Input LayerNorm

In hybrid architectures, Mixer layers and Attention layers share the `input_layernorm` HF key, distinguished via `depend_on_key`:

```yaml
input_layernorm: { name: input_layernorm, depend_on_key: attention.query_gate_key_value }
mixer_input_layernorm: { name: input_layernorm, depend_on_key: mixer_att.log }
```

Applicable models: **Qwen 3.5**, **Qwen3_next**

---

## 7. Vision Encoder Common Format

Patterns shared by all Vision Encoders:
- Single fused QKV (`attn.qkv`, see 1B)
- Ungated MLP (`mlp.fc1`/`mlp.fc2`, see 2B)
- No MoE, no MTP
- `vision_patch` config handles patch embed / pos embed / class token

| Special Item | Model | Description |
|-------------|-------|-------------|
| Gated MLP | Qwen2.5 VIT | Only VIT using gated MLP |
| Layer Scale + QK-Norm | InternVL ViT 6B | `ls1`/`ls2` + `q_norm`/`k_norm` |
| `num_padded_heads` | InternVL ViT 6B | Head count alignment padding |
| Deepstack merger | Qwen3 VIT | vision_patch contains merger list |

---

## 8. Format Decision Quick-Reference Table

Given a module in a new model, match in the following order:

### Attention
```
Has hc_attn_fn / hc_ffn_fn?       -> HyperConnection (1I)
Has wo_a / wo_b (split output)?   -> Grouped Output Projection (1J)
Has q_a_proj / kv_a_proj_with_mqa? -> MLA (1D) or Partial MLA (1E)
Has linear_attn / A_log?           -> Mixer Attention (1G)
Q dimension = 2x standard?         -> Gated Attention (1C)
Separate q_proj/k_proj/v_proj?     -> Standard QKV separated (1A)
Single qkv tensor?                  -> Standard QKV fused (1B)
```

> **Note on attention-internal sub-modules**: Modules like `indexer`, `attn_sink`, or `compressor`
> live under `self_attention.core_attention.*` in mcore -- never directly under `self_attention.*`.
> See "Attention-Internal Sub-module Hierarchy" above.

### MLP
```
Vision Encoder?
+-- Has gate_proj? -> Gated Vision MLP (2C, rare)
+-- No             -> Ungated MLP (2B)
LLM?             -> Gated MLP (2A, almost certain)
```

### MoE
```
Expert weights are 3D stacked? -> Dict-for-expert (3C)
Has shared_expert?      -> Shared Expert (3D), check for gate (3E)
Has e_score_correction_bias? -> Gate Bias (3A)
Standard per-expert?        -> Standard per-expert (3B)
```

### MTP
```
Has independent embed_tokens?    -> DeepSeek style (5A)
Embed shared + has fc?     -> Qwen 3.5 style (5C)
Embed shared + has input_proj? -> MIMO style (5B)
```
