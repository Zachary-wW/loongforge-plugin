# Custom Converter Reference

> Version: v1.0 | Updated: 2026-04-16
> Related Pages: [MODULE_FORMATS](MODULE_FORMATS.md) | [ADAPTATION_GUIDE](ADAPTATION_GUIDE.md)

When the weight storage layout differs between HF and mcore (requiring split/cat/interleave), custom converters are needed.
This document records all 5 existing converters and their design patterns.

Existing converter files are reference implementations during ordinary model adaptation. Do not modify their algorithms for a new model. Create a new converter or append a new dispatch branch. If the model requires key normalization, FP8 scale renaming/dequantization, MTP tied-copy handling, or load/save metadata reconstruction, classify it as `insert_load_preprocess`, `insert_save_postprocess`, or `custom_roundtrip_rule` before editing protected generic code.

---

## Converter Overview

| # | Class Name | File | Side | Responsibility |
|---|-----------|------|------|---------------|
| 1 | `HfAttnQkvConverter` | `huggingface/util/hf_attn_converter.py` | HF | Standard QKV split/cat (GQA interleave + padded heads) |
| 2 | `HfAttnGateQkvConverter` | `huggingface/util/hf_attn_converter.py` | HF | Gated Attention QKV -- Q contains gate, interleaved per KV group |
| 3 | `HfMixerAttnConverter` | `huggingface/util/hf_mixer_attn_converter.py` | HF | Mixer Attention -- qkvz/ba interleave (Qwen 3.5 style) |
| 4 | `McoreAttnGateQkvConverter` | `mcore/util/mcore_attn_converter.py` | mcore | Gated QKV TP slicing |
| 5 | `McoreMixerAttnConverter` | `mcore/util/mcore_attn_converter.py` | mcore | Mixer in_proj TP slicing |

---

## Design Patterns

### HF-Side Converters

Responsibility: HF separate storage <-> Common fused storage

Each HF-side converter provides a pair of methods:
- `cat_*()` -- HF -> Common: merge multiple HF tensors into one common tensor
- `split_*()` -- Common -> HF: split one common tensor into multiple HF tensors

### mcore-Side Converters

Responsibility: Common fused tensor -> correct slicing per TP rank

Each mcore-side converter provides:
- `chunk_*()` -- slice the common fused tensor into `tp_size` shards along the TP dimension

Reason for mcore-side converters: non-standard layouts cannot be simply `torch.chunk`'d; they need to be unpacked first and sliced per sub-component.

---

## 1. HfAttnQkvConverter

Handles standard QKV split/cat, considering GQA grouping and interleaved arrangement.

### Core Parameters
- `heads` -- Q head count
- `num_key_value_heads` -- KV head count (less than heads for GQA)
- `head_dim` -- dimension per head
- `transpose_query_key_value` -- whether to interleave by KV group
- `num_padded_heads` -- head count padding amount (only used by InternVL ViT 6B)

### cat_attn_qkv (HF -> Common)

```
Input: value_list = [Q, K, V] (or [QKV_fused])
  +-- transpose=false -> direct cat
  +-- transpose=true  -> interleave by KV group: [q_g0, k_g0, v_g0, q_g1, k_g1, v_g1, ...]
Output: fused QKV tensor + optional padding
```

### split_attn_qkv (Common -> HF)

```
Input: fused QKV tensor
  +-- remove padding
  +-- transpose=false -> return directly
  +-- transpose=true  -> reverse interleave to recover [Q, K, V]
Output: [Q, K, V] (or [QKV_fused])
```

---

## 2. HfAttnGateQkvConverter

Handles MiniMax / Qwen 3.5 style gated self-attention, where Q dimension is doubled.

### Core Parameters
- `num_querys_per_group = heads // num_key_value_heads`
- `q_dim = 2 * num_querys_per_group * head_dim` (2x for gate)
- `kv_dim = head_dim`

### cat_attn_qgkv (HF -> Common)

```
Input: [Q, K, V] (Q shape includes gate)
reshape to (num_kv_heads, q_dim+kv_dim+kv_dim, hidden_size)
-> interleave cat per group
Output: fused tensor
```

### split_attn_qgkv (Common -> HF)

```
Input: fused tensor
reshape -> slice Q (including gate), K, V per group
Output: [Q, K, V]
```

---

## 3. HfMixerAttnConverter

Handles mixer attention in_proj layout conversion for Qwen 3.5 / GatedDeltaNet. Provides 4 method pairs.

### Core Parameters
- `mixer_num_key_heads` (nk)
- `mixer_num_value_heads` (nv)
- `mixer_key_head_dim` (dk)
- `mixer_value_head_dim` (dv)
- `r = nv // nk` (number of value heads per key group)

### Method Pair 1: cat/split_mixer_in_proj (legacy, simple cat)

```
cat: [in_proj_ba, in_proj_qkvz] -> cat -> in_proj
split: in_proj -> split -> [in_proj_ba, in_proj_qkvz]
```

### Method Pair 2: cat/split_qkv_z_to_qkvz (Qwen 3.5 core)

HF contiguous layout: `in_proj_qkv = [q_all, k_all, v_all]`, `in_proj_z = [z_all]`
Common interleaved layout: per group `[q_g, k_g, v_g*r, z_g*r]`

```
cat_qkv_z_to_qkvz (HF -> Common):
  split q(nk,dk), k(nk,dk), v(nk,r*dv), z(nk,r*dv)
  -> cat [q,k,v,z] per group -> reshape -> interleaved qkvz

split_qkvz_to_qkv_z (Common -> HF):
  reshape -> split q,k,v,z per group
  -> cat q->Q, k->K, v->V (contiguous), z->Z
```

### Method Pair 3: cat/split_b_a_to_ba

HF: independent `in_proj_b(nv,H)`, `in_proj_a(nv,H)`
Common: interleaved per group `[b_g*r, a_g*r]`

```
cat:   reshape(nk,r,H) -> cat [b,a] dim=1 -> ba
split: reshape(nk,2r,H) -> split -> b, a
```

---

## 4. McoreAttnGateQkvConverter

TP slicing for Gated QKV. Cannot simply `torch.chunk` because Q (including gate)/K/V have different dimensions.

### chunk_gqkv

```
Input: gqkv fused tensor, tp_size
  reshape -> (num_kv_heads, q_dim+kv_dim+kv_dim, hidden_size)
  split -> Q, K, V
  chunk(tp) each -> Q_s[], K_s[], V_s[]
  Reassemble: per rank cat [Q_i, K_i, V_i]
Output: [rank0_qkv, rank1_qkv, ...]
```

---

## 5. McoreMixerAttnConverter

TP slicing for Mixer in_proj.

### chunk_mixer_in_proj_qkvz

```
Input: qkvz fused tensor, tp_size
  reshape -> (nk, 2*dk + 2*r*dv, H)
  split -> q(dk), k(dk), v(r*dv), z(r*dv)
  chunk(tp) each
  Reassemble: per rank cat [q_i, k_i, v_i, z_i]
Output: [rank0_qkvz, rank1_qkvz, ...]
```

### chunk_mixer_in_proj_ba

```
Input: ba fused tensor, tp_size
  reshape -> (nk, 2r, H)
  split -> ba1(r), ba2(r)
  chunk(tp) each
  Reassemble: per rank cat [ba1_i, ba2_i]
Output: [rank0_ba, rank1_ba, ...]
```

---

## When to Create a New Converter

See the decision flowchart in [ADAPTATION_GUIDE](ADAPTATION_GUIDE.md). Quick assessment:

| Situation | Need New Converter? |
|-----------|-------------------|
| New parameter is an ordinary Linear / LayerNorm | No -- pure configuration |
| HF stores separately, mcore stores fused (or vice versa), but logic is same as QKV cat/split | No -- reuse list-type name_map |
| Merge/split rules are completely different from existing ones (new interleave pattern) | Yes -- new HF-side converter |
| New non-standard layout requiring TP slicing | Yes -- new mcore-side converter |

Code locations for new converters:
- HF side: `tools/convert_checkpoint/huggingface/util/hf_<name>_converter.py`
- mcore side: `tools/convert_checkpoint/mcore/util/mcore_<name>_converter.py`

Also need to add branches in `huggingface_base.py`'s `hf_to_common()` / `common_to_hf()` and/or `mcore_base.py`.
