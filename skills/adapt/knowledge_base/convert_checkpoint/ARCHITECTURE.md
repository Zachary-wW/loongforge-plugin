# Weight Conversion System Architecture

> Version: v1.0 | Updated: 2026-04-16
> Code Path: `tools/convert_checkpoint/`
> Related Pages: [MODULE_FORMATS](MODULE_FORMATS.md) | [ADAPTATION_GUIDE](ADAPTATION_GUIDE.md) | [CUSTOM_CONVERTERS](CUSTOM_CONVERTERS.md)

---

## 1. Hub-and-Spoke Intermediate Representation Design

All format conversions route through a **Common intermediate representation**; no N x N direct conversions:

```
HuggingFace --convert_to_common--> CommonCheckpoint --convert_from_common--> Megatron Core
Megatron Core --convert_to_common--> CommonCheckpoint --convert_from_common--> HuggingFace
```

Adding a new format only requires implementing `to_common` + `from_common`, complexity O(N).

---

## 2. Directory Structure

```
tools/convert_checkpoint/
├── common/                     # Intermediate representation layer
│   ├── abstact_checkpoint.py   # AbstractCheckpoint abstract base class
│   ├── abstact_config.py       # AbstractConfig abstract base class
│   ├── common_checkpoint.py    # CommonCheckpoint (~60 semantic constants)
│   └── common_config.py        # CommonConfig (JSON/YAML config, Visitor pattern dispatch)
├── huggingface/                # HF-side conversion
│   ├── huggingface_config.py   # HuggingFaceConfig
│   ├── huggingface_checkpoint.py  # Orchestrator: load/save safetensors, traverse classification lists
│   ├── huggingface_base.py     # Core conversion logic hf_to_common / common_to_hf
│   ├── huggingface_moe.py      # MoE expert weight processing
│   ├── merge_huggingface.py    # Merge segmented HF sub-checkpoints
│   └── util/
│       ├── hf_attn_converter.py       # HfAttnQkvConverter + HfAttnGateQkvConverter
│       └── hf_mixer_attn_converter.py # HfMixerAttnConverter
├── mcore/                      # Megatron Core-side conversion
│   ├── mcore_config.py         # McoreConfig
│   ├── mcore_checkpoint.py     # Orchestrator: TP/PP/EP/ETP/VPP full-dimension parallelism
│   ├── mcore_base.py           # Core conversion + TENSOR_PARALLEL_DIM + FP8/LoRA
│   ├── mcore_moe.py            # MoE expert weights (per-expert + grouped-gemm)
│   ├── merge_megatron.py       # Merge mcore segments
│   ├── merge_megatron_expert.py # Merge EP dimension
│   └── util/
│       └── mcore_attn_converter.py    # McoreAttnGateQkvConverter + McoreMixerAttnConverter
├── key_mappings/               # LoongForge internal/external naming prefix remapping
│   ├── to_omni_key.py          # foundation_model <-> language_model
│   ├── to_vanilla_key.py       # Common prefix remapping
│   ├── key_reverser.py         # Full checkpoint reverse rename
│   └── key_reverser_expert.py  # Per-shard reverse rename (for large MoE)
├── module_convertor/           # Top-level orchestration entry point
│   ├── model.py                # main() + Model class, VLM per-module orchestration
│   ├── adapter.py              # Image Projector key remapping
│   ├── adapter_internvl.py     # InternVL-specific adapter remapping
│   └── vision_patch.py         # Vision patch embed remapping
├── utils/                      # Utility functions
│   ├── ckpt_util.py            # Checkpoint I/O (safetensors/mcore multi-dimensional layout)
│   ├── config_utils.py         # Hydra YAML loading + parallel parameter parsing
│   └── utils.py                # Pipeline partition / embedding padding / FP8 / done-file
└── pi05/                       # Pi0.5 VLA-specific conversion
    └── convert_hf_to_Mfsdp.py
```

---

## 3. Core Abstractions

### AbstractCheckpoint

Defines the bidirectional conversion interface:
- `convert_to_common()` -- Instance method, source format -> CommonCheckpoint
- `convert_from_common()` -- Static method, CommonCheckpoint -> target format
- `save()` -- Persist to disk

### CommonCheckpoint

Intermediate representation, storing all weights with flat keys:

```
"layer_prefix.<layer_id>.<semantic_name>.weight"
```

Provides semantic access:
- `get(key)` -> `(weight, bias, weight_scale)` triple
- `set(key, weight, bias, weight_scale)` for writing
- `get_key(name, layer_id, expert_id)` for key construction

Parameters are grouped by **classification lists**, which determine traversal order:

| Classification | Constant | Processing Timing |
|---------------|----------|-------------------|
| `FIRST_LAYER_NAMES` | `word_embeddings`, `word_position_embeddings`, `word_block_position_embeddings`, `vision_word_embeddings` | Processed once at PP rank 0 |
| `BASE_NAMES` | ~30 items (attention/MLP/layernorm/MoE gate, etc.) | Per-layer traversal |
| `MOE_EXPERT_PROJS` | `moe.expert_h_to_4h`, `moe.expert_4h_to_h` | Per-layer per-expert traversal |
| `MTP_NAMES` | `mtp_word_embeddings`, `mtp_enorm`, `mtp_hnorm`, `mtp_eh_proj`, `mtp_shared_head_norm`, `mtp_shared_head_head` | Last PP stage, layer_id >= num_layers |
| `LAST_LAYER_NAMES` | `final_layernorm`, `word_embeddings_for_head` | Processed once at last PP rank |

### CommonConfig

JSON/YAML configuration, core structure:

```json
{
  "args": {
    "common": { "num_layers": 32, "hidden_size": 4096, ... },
    "mcore": { "transpose_query_key_value": true, ... },
    "huggingface": { "transformer": "model", "layer_prefix": "layers", ... }
  },
  "name_map": {
    "huggingface": { "word_embeddings": "model.embed_tokens", ... },
    "mcore": { "word_embeddings": "language_model.embedding.word_embeddings", ... }
  }
}
```

Uses Visitor pattern for dispatch: `common_config.convert(McoreConfig)` -> `McoreConfig.convert_from_common(self)`.

---

## 4. name_map -- Conversion Core

name_map is the core data structure of the entire conversion system, mapping **semantic names** to **platform-specific key paths**.

### Entry Types

| Type | Format | Example | Meaning |
|------|--------|---------|---------|
| Simple string | `"hf_path"` | `attention.dense: self_attn.o_proj` | 1-to-1 mapping |
| List | `[path1, path2, ...]` | `attention.query_key_value: [q_proj, k_proj, v_proj]` | Multiple HF tensors concatenated into one common tensor |
| Dictionary with metadata | `{name: ..., flag: ...}` | `{name: linear_qkv, extra: true, fp8: true}` | With special processing flags |

### Metadata Flag Quick Reference

| Flag | Meaning | Typical Scenario |
|------|---------|-----------------|
| `extra: true` | Save mcore `_extra_state` (quantization metadata) | FP8 / TE quantized layers |
| `fp8: true` | Parameter is in FP8 format | FP8 linear layers |
| `fp8_ignore_tp: true` | FP8 parameter not subject to TP slicing | MLA q_down / kv_down |
| `ignore_tp: true` | Skip TP slicing | Mixer attention weights |
| `is_layernorm: true` | Use `.layer_norm_weight` suffix | TE fused layernorm |
| `is_direct_name: true` | Path is a complete key, do not append `.weight` | `A_log`, `ls1`/`ls2`, grouped expert |
| `no_layer_id: true` | Not under per-layer hierarchy | Qwen 3.5 MTP weights |
| `depend_on_key: xxx` | Only process when xxx weight exists | Hybrid architecture layer type distinction |
| `dtype: bf16/fp8` | Force type conversion | HF bf16 <-> mcore fp8 |
| `need_transpose: true` | Transpose weight | dict-for-expert layout |
| `is_dict_for_expert: true` | Expert weights stored as stacked dict | Qwen3 MoE (qwen3vl) |
| `weight_scale_key` | Override default FP8 scale suffix | Kimi K2 (`weight_scale`) |

---

## 5. TP Slicing Rules

The `TENSOR_PARALLEL_DIM` dictionary in `mcore_base.py` defines which dimension each parameter is sliced on:

- **dim=0** (column parallel, slicing output dim): `word_embeddings`, `attention.query_key_value`, `mlp.dense_h_to_4h`, `mtp_eh_proj`
- **dim=1** (row parallel, slicing input dim): `attention.dense`, `mlp.dense_4h_to_h`
- **Not in the dictionary**: Not sliced (replicated)

If a model has new parameters requiring TP slicing, they must be registered in this dictionary. Can be overridden at the config level via `tensor_parallel_dim`.

---

## 6. Conversion Flow

### Dense Model (LLM)

```
main() launches
  |
  +-- Load CommonConfig (JSON or Hydra YAML)
  +-- Assign PP stages to each rank
  |
  +-- For each PP stage:
      +-- Model.convert_to_common()
      |   +-- HuggingFaceCheckpoint.load() -> .convert_to_common()
      |       Traverse: FIRST -> BASE -> MOE_EXPERT -> MTP -> LAST
      |
      +-- Model.convert_from_common()
          +-- McoreCheckpoint.convert_from_common()
              Slice each weight per TP rank -> save()
```

### VLM Model (Per-Module)

```
Foundation LLM   --convert--> mcore language_model/
Vision Encoder   --convert--> mcore encoder_model.image_encoder/
Image Projector  --adapter--> mcore encoder_model.image_projector/
Vision Patch     --patch----> mcore vision_patch weights
                      |
                      v
               merge_megatron.py merges into final checkpoint
```

### Distributed Coordination

Multiple ranks convert different PP stages in parallel, synchronized via **done-file** mechanism:
- Each rank calls `touch_file(done_key)` after completion
- `check_all_done()` waits for all ranks to complete
- During HF output, the final step is `make_hf_sub_checkpoints()` to merge segments

---

## 7. Entry Points and Invocation

### CLI Invocation

```bash
# HF -> mcore
python tools/convert_checkpoint/module_convertor/model.py \
    --load_platform huggingface --save_platform mcore \
    --config_file configs/models/<family>/<model>.yaml \
    --convert_file configs/models/<family>/ckpt_convert/<family>_convert.yaml \
    --load_ckpt_path <HF_PATH> --save_ckpt_path <MCORE_PATH> \
    --tensor_model_parallel_size <TP> --pipeline_model_parallel_size <PP> \
    --safetensors --no_save_optim --no_load_optim

# mcore -> HF (reverse, same parameters, swap platforms)
python tools/convert_checkpoint/module_convertor/model.py \
    --load_platform mcore --save_platform huggingface \
    ...
```

### Legacy JSON Configuration

```bash
python tools/convert_checkpoint/module_convertor/model.py \
    --common_config_path <config.json>
```

### VERL In-Memory Invocation

```python
from convert_checkpoint.module_convertor.model import verl_convert_mcore_to_hf_v3
verl_convert_mcore_to_hf_v3(mcore_state_dict, config)
```
