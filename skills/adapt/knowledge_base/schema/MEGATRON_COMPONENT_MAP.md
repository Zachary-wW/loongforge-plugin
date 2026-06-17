# Megatron Core Architecture & Component Reference

> For use by Phase 1 Step 1.5 (Architecture Pre-read) and Step 2c (Deep Megatron Reading).
> Source: `AIAK-Megatron/megatron/core/` — read and verify against actual code.

---

## 1. Architecture Overview

Megatron-LM uses a **spec-driven assembly** pattern. Components are not hardwired — they are composed via `ModuleSpec` trees that specify which class implements each sub-module, along with its parameters and sub-specs.

### Key Files to Read (Phase 1 Step 1.5)

| File | Purpose | What to understand |
|------|---------|-------------------|
| `<megatron_path>/megatron/core/transformer/spec_utils.py` | Spec utilities | `ModuleSpec` class — `module`, `params`, `submodules` fields; `build_module()` how specs become instances |
| `<megatron_path>/megatron/core/transformer/transformer_layer.py` | Core assembly point | `TransformerLayerSubmodules` slots; how `TransformerLayer.__init__` calls `build_module()` for each slot |
| `<megatron_path>/megatron/core/transformer/transformer_config.py` | Config system | `TransformerConfig` and `MLATransformerConfig` fields; which flags control which behavior |
| `<megatron_path>/megatron/core/transformer/transformer_block.py` | Block assembly | `TransformerBlockSubmodules` (layer_specs + layer_norm); how layers are stacked per PP stage |

### Assembly Flow

```
TransformerConfig (dataclass)
       |
       v
get_<model>_decoder_block_spec(config)   [in layer_spec.py]
       |
       v
TransformerBlockSubmodules(
    layer_specs=[TransformerLayerSubmodules(...), ...],
    layer_norm=TENorm,
)
       |
       v
TransformerBlock.build(position_encoder, ...)
  -> for each layer_spec: TransformerLayer(spec, config)
    -> self_attention = build_module(submodules.self_attention, config=config, ...)
    -> mlp = build_module(submodules.mlp, config=config, ...)
    -> input_layernorm = build_module(submodules.input_layernorm, config=config, ...)
    -> ... (hyper connections, cross attention, etc.)
```

---

## 2. TransformerLayer Submodule Slots

`TransformerLayerSubmodules` (source: `transformer_layer.py:197-241`) defines all slots:

```python
@dataclass
class TransformerLayerSubmodules:
    input_layernorm: Union[ModuleSpec, type] = IdentityOp
    self_attention_hyper_connection: Union[ModuleSpec, type] = IdentityOp   # mHC only
    self_attention: Union[ModuleSpec, type] = IdentityOp
    self_attn_bda: Union[ModuleSpec, type] = IdentityFuncOp

    pre_cross_attn_layernorm: Union[ModuleSpec, type] = IdentityOp         # cross-attn only
    cross_attention_hyper_connection: Union[ModuleSpec, type] = IdentityOp  # mHC only
    cross_attention: Union[ModuleSpec, type] = IdentityOp                   # cross-attn only
    cross_attn_bda: Union[ModuleSpec, type] = IdentityFuncOp               # cross-attn only

    pre_mlp_layernorm: Union[ModuleSpec, type] = IdentityOp
    mlp_hyper_connection: Union[ModuleSpec, type] = IdentityOp             # mHC only
    mlp: Union[ModuleSpec, type] = IdentityOp
    mlp_bda: Union[ModuleSpec, type] = IdentityFuncOp

    sharded_state_dict_keys_map: Dict[str, str] = field(default_factory=dict)
```

### Slot Groups

| Group | Slots | When Active |
|-------|-------|-------------|
| **Self-attention** | `input_layernorm` → `self_attention_hyper_connection?` → `self_attention` → `self_attn_bda` | Always (decoder) |
| **Cross-attention** | `pre_cross_attn_layernorm` → `cross_attention_hyper_connection?` → `cross_attention` → `cross_attn_bda` | Encoder-decoder models; `IdentityOp` in decoder-only |
| **MLP/MoE** | `pre_mlp_layernorm` → `mlp_hyper_connection?` → `mlp` → `mlp_bda` | Always |
| **Hyper connections** | `*_hyper_connection` | When `config.enable_hyper_connections=True`; else `IdentityOp` (no-op) |

### How to Replace a Component

You do NOT add new slots. Instead, replace the module in an existing slot via `ModuleSpec`:

```python
# Example: Replace SelfAttention with MLASelfAttention
ModuleSpec(
    module=TransformerLayer,
    submodules=TransformerLayerSubmodules(
        self_attention=ModuleSpec(
            module=MLASelfAttention,
            params={"attn_mask_type": AttnMaskType.causal},
            submodules=MLASelfAttentionSubmodules(
                linear_q_proj=multiacc_modules.TEColumnParallelLinear,
                linear_q_down_proj=multiacc_modules.TEColumnParallelLinear,
                # ...
            ),
        ),
        # other slots...
    ),
)
```

---

## 3. Hardware Abstraction: `multiacc_modules`

LoongForge uses `loongforge/models/dispatch.py` to provide hardware-agnostic module references via `multiacc_modules`. **Always use `multiacc_modules.*` instead of direct TE/local imports in layer_spec.**

| `multiacc_modules` field | TE Implementation | Local Fallback |
|--------------------------|-------------------|----------------|
| `TELayerNormColumnParallelLinear` | TE fused LN+Linear | `ColumnParallelLinear` with separate norm |
| `TEColumnParallelLinear` | TE Linear | `ColumnParallelLinear` |
| `TERowParallelLinear` | TE Linear | `RowParallelLinear` |
| `TEColumnParallelGroupedLinear` | TE GroupedLinear (MoE) | — |
| `TERowParallelGroupedLinear` | TE GroupedLinear (MoE) | — |
| `DotProductAttention` | TE FlashAttention | Local attention |
| `TENorm` | TE RMSNorm/LayerNorm | `LocalNorm` |
| `TELinear` | TE Linear (no TP) | `torch.nn.Linear` |
| `get_bias_dropout_add` | Fused bias-dropout-add | — |
| `apply_rotary_pos_emb` | Fused rotary embedding | — |

### When to Use Which

- **Standard case**: Use `multiacc_modules.TE*` for all linear/norm layers in layer_spec
- **QK LayerNorm**: Use `multiacc_modules.TENorm` (if TE >= 1.9) or `multiacc_modules.LocalNorm`
- **FP8 blockwise**: Replace `TEColumnParallelLinear` with `TELinear` for certain MLA projections (see DeepSeek layer_spec)
- **VLM**: Some VLM specs use direct TE imports (`from megatron.core.extensions.transformer_engine import ...`) instead of `multiacc_modules`

---

## 4. Config System

### Config Hierarchy

```
ModelParallelConfig (Megatron core)
  └── TransformerConfig (+ all model architecture fields, MoE, MTP, hyper-connections, etc.)
        ├── BaseModelConfig (+ HuggingFace PretrainedConfig, + LoongForge fields)
        │     Used by: LLaMA, Qwen, InternLM, MiniMax, GLM, etc.
        │
        └── MLATransformerConfig (+ MLA-specific fields: q_lora_rank, kv_lora_rank, YaRN RoPE, etc.)
              └── BaseModelMLAConfig (+ HuggingFace PretrainedConfig, + LoongForge fields)
                    Used by: DeepSeek, MIMO (all MLA models)
```

### Key Config Fields by Component

| Component | Config Fields | Notes |
|-----------|--------------|-------|
| **Attention** | `num_attention_heads`, `num_query_groups` (GQA), `multi_latent_attention`, `qk_layernorm`, `add_qkv_bias`, `softmax_scale`, `window_size`, `no_rope_freq` | `multi_latent_attention=True` switches from `SelfAttention` to `MLASelfAttention` |
| **MLA** | `q_lora_rank`, `kv_lora_rank`, `qk_head_dim`, `qk_pos_emb_head_dim`, `v_head_dim` | Only on `MLATransformerConfig` and subclasses |
| **MLA RoPE** | `rope_type` ("yarn"|"rope"), `rotary_base`, `rotary_percent`, `rotary_scaling_factor`, `original_max_position_embeddings`, `beta_fast`, `beta_slow`, `mscale`, `mscale_all_dim` | MLA default is YaRN RoPE |
| **MLP** | `ffn_hidden_size`, `gated_linear_unit`, `add_bias_linear`, `activation_func`, `swiglu` | `gated_linear_unit=True` means SwiGLU-style gated MLP |
| **MoE** | `num_moe_experts`, `moe_grouped_gemm`, `moe_layer_freq`, `moe_shared_expert_intermediate_size`, `moe_shared_expert_overlap`, `moe_ffn_hidden_size`, `moe_router_topk`, `moe_router_num_groups`, `moe_router_group_topk`, `moe_router_load_balancing_type` | `moe_layer_freq` controls dense vs MoE layer pattern; `moe_shared_expert_intermediate_size=None` means no shared expert |
| **MTP** | `mtp_num_layers`, `mtp_loss_scaling_factor`, `mtp_loss_scaling_factor_decay_ratio`, `mtp_shared_layers`, `mtp_connection_type` ("sequential"|"parallel") | `mtp_num_layers=None` = disabled; uses `get_gpt_mtp_block_spec` |
| **Hyper Connections** | `enable_hyper_connections`, `num_residual_streams`, `mhc_sinkhorn_iterations`, `mhc_init_gating_factor` | Multi-Head Hyper-Connections (mHC) residual stream; replaces simple residual add |
| **Norm** | `normalization` ("RMSNorm"|"LayerNorm"), `layernorm_epsilon`, `layernorm_zero_centered_gamma` | |
| **RoPE** | `position_embedding_type`, `rotary_interleaved`, `apply_rope_fusion`, `no_rope_freq` | `no_rope_freq` controls which layers skip RoPE |
| **FP8** | `fp8`, `fp8_recipe`, `fp8_dynamic_policy_path` | FP8 + MLA: certain projections switch to `TELinear` |
| **Experimental** | `experimental_attention_variant` ("gated_delta_net"|"dsa" or None), `dsa_indexer_n_heads`, `dsa_indexer_head_dim`, `dsa_indexer_topk`, `dsa_indexer_loss_coeff` | Controls attention variant dispatch in layer_spec |

### Adding Custom Config Fields

Inherit from the appropriate base class and add fields as dataclass attributes:

```python
@dataclass
class DeepseekConfig(BaseModelMLAConfig):
    num_layers: int
    hidden_size: int
    ffn_hidden_size: int
    num_attention_heads: int
    # Custom fields
    num_experts: int = None
    moe_ffn_hidden_size: int = None
    q_lora_rank: int = None
    kv_lora_rank: int = None
    moe_layer_freq: Optional[Union[int, List[int]]] = None
    multi_latent_attention: bool = True  # MLA always on for DeepSeek
    mtp_num_layers: int = 0
```

**Important**: Config fields are read by `layer_spec.py` functions (e.g., `config.multi_latent_attention`, `config.qk_layernorm`, `config.experimental_attention_variant`). Any field accessed in layer_spec MUST exist in the config class. Before adding a custom field, check `TransformerConfig` / `MLATransformerConfig` first — many fields already exist upstream.

---

## 5. Component Reference

### 5.1 Attention

| Type | Module Class | Submodules Class | Source File |
|------|-------------|-----------------|-------------|
| MHA/GQA | `SelfAttention` | `SelfAttentionSubmodules` | `megatron/core/transformer/attention.py` |
| Cross-attention | `CrossAttention` | `CrossAttentionSubmodules` | `megatron/core/transformer/attention.py` |
| MLA | `MultiLatentAttention` | `MLASelfAttentionSubmodules` | `megatron/core/transformer/multi_latent_attention.py` |

#### SelfAttentionSubmodules (source: `attention.py:106-116`)

| Slot | Module | Purpose |
|------|--------|---------|
| `linear_qkv` | `TELayerNormColumnParallelLinear` | Fused QKV projection (TP-split) |
| `core_attention` | `DotProductAttention` | Flash attention |
| `linear_proj` | `TERowParallelLinear` | Output projection |
| `q_layernorm` | `TENorm` or `IdentityOp` | Q norm (when `qk_layernorm=True`) |
| `k_layernorm` | `TENorm` or `IdentityOp` | K norm |
| `apply_rotary_fn` | `apply_rotary_pos_emb` | RoPE application function |

#### CrossAttentionSubmodules (source: `attention.py:119-129`)

| Slot | Module | Purpose |
|------|--------|---------|
| `linear_q` | `TELayerNormColumnParallelLinear` | Q projection |
| `linear_kv` | `TELayerNormColumnParallelLinear` | KV projection |
| `core_attention` | `DotProductAttention` | Flash attention |
| `linear_proj` | `TERowParallelLinear` | Output projection |
| `apply_rotary_fn` | `apply_rotary_pos_emb` | RoPE application function |

#### MLASelfAttentionSubmodules (source: `multi_latent_attention.py:71-82`)

| Slot | Module | Purpose |
|------|--------|---------|
| `linear_q_proj` | `TEColumnParallelLinear` | Q output projection |
| `linear_q_down_proj` | `TEColumnParallelLinear` | Q latent compression |
| `linear_q_up_proj` | `TEColumnParallelLinear` or `TELayerNormColumnParallelLinear` | Q latent decompression |
| `linear_kv_down_proj` | `TEColumnParallelLinear` | KV latent compression |
| `linear_kv_up_proj` | `TEColumnParallelLinear` | KV latent decompression |
| `core_attention` | `DotProductAttention` | Flash attention |
| `linear_proj` | `TERowParallelLinear` | Output projection |
| `q_layernorm` | `IdentityOp` or `TENorm` | Q norm |
| `kv_layernorm` | `IdentityOp` or `TENorm` | KV norm |

Note: `MultiLatentAttention` inherits from `Attention` (not `SelfAttention`). It is used as the `module` in `ModuleSpec`, not as a direct base class for custom attention.

#### Extension Points for Attention

- **Custom rotary embedding**: Replace `apply_rotary_fn` slot (e.g., `apply_mrope` for Qwen2-VL)
- **QK norm**: Set `qk_layernorm=True` in config, use `TENorm` (TE>=1.9) or `LocalNorm`
- **New attention type**: Create a new class, define `*Submodules`, reference it in `ModuleSpec`
- **Experimental attention variant**: Use `config.experimental_attention_variant` to dispatch in layer_spec

#### Pattern: DeepSeek Sparse Attention (DSA)

DSA demonstrates adding a complex new attention variant. Source: `megatron/core/transformer/experimental_attention_variant/dsa.py`.

1. New config field: `experimental_attention_variant: str` (supports `"gated_delta_net"` and `"dsa"`)
2. Additional config fields: `dsa_indexer_n_heads`, `dsa_indexer_head_dim`, `dsa_indexer_topk`, `dsa_indexer_loss_coeff`
3. Conditional dispatch in layer_spec: `if config.experimental_attention_variant == "dsa":`
4. New module class: `DSAttention` (source: `dsa.py:693`) with `DSAttentionSubmodules` (source: `dsa.py:332`)
5. New indexer class: `DSAIndexer` (source: `dsa.py:343`) with `DSAIndexerSubmodules` (source: `dsa.py:314`)
6. Nested spec: `core_attention = ModuleSpec(module=DSAttention, submodules=DSAttentionSubmodules(indexer=ModuleSpec(module=DSAIndexer, submodules=DSAIndexerSubmodules(...))))`
7. LoongForge also has Omni optimized variant: `DSAttentionFused` in `loongforge/models/common/experimental_attention_variant/`

### 5.2 MLP / MoE

| Type | Module Class | Submodules Class | Source File |
|------|-------------|-----------------|-------------|
| Dense | `MLP` | `MLPSubmodules` | `megatron/core/transformer/mlp.py` |
| MoE | `MoELayer` | `MoESubmodules` | `megatron/core/transformer/moe/moe_layer.py` |

#### MLPSubmodules (source: `mlp.py:49-57`)

| Slot | Module | Purpose |
|------|--------|---------|
| `linear_fc1` | `TELayerNormColumnParallelLinear` | Gate + Up projection (when `gated_linear_unit=True`) or single projection |
| `activation_func` | Callable | Activation function (default `F.gelu`); usually left as None in spec |
| `linear_fc2` | `TERowParallelLinear` | Down projection |

#### MoESubmodules (source: `moe/moe_layer.py:40-44`)

| Slot | Module | Purpose |
|------|--------|---------|
| `shared_experts` | `ModuleSpec(SharedExpertMLP, ...)` | Shared expert (always active); `None` when `moe_shared_expert_intermediate_size` is None |
| `experts` | `ModuleSpec(SequentialMLP or TEGroupedMLP, ...)` | Routed experts |

#### Extension Points for MLP/MoE

- **Dense vs MoE pattern**: Use `moe_layer_freq` in config. In layer_spec, create both `dense_layer_spec` and `moe_layer_spec`, then select per-layer.
- **Grouped GEMM**: Set `moe_grouped_gemm=True` to use `TEGroupedMLP` (faster) instead of `SequentialMLP`
- **Shared expert**: Present in DeepSeek models. Use `SharedExpertMLP` (source: `moe/shared_experts.py`). Set `moe_shared_expert_intermediate_size` in config.
- **Custom routing**: Override router for new strategies (e.g., group-limited routing via `moe_router_num_groups` + `moe_router_group_topk`; load balancing via `moe_router_load_balancing_type` — supports "aux_loss", "seq_aux_loss", "global_aux_loss", "sinkhorn", "none")

### 5.3 Hyper Connections

| Module | Source File |
|--------|------------|
| `HyperConnectionModule` | `megatron/core/transformer/hyper_connection.py` |

Hyper connections (mHC) replace the simple residual add with multi-stream residual connections. Controlled by:
- `config.enable_hyper_connections: bool = False`
- `config.num_residual_streams: int = 4`
- `config.mhc_sinkhorn_iterations: int = 20`
- `config.mhc_init_gating_factor: float = 0.01`

When enabled, three additional submodule slots are activated:
- `self_attention_hyper_connection`
- `cross_attention_hyper_connection`
- `mlp_hyper_connection`

These slots default to `IdentityOp` (no-op). When `enable_hyper_connections=True`, the TransformerLayer `__init__` builds `HyperConnectionModule` instances for each slot.

**Current LoongForge models do not use hyper connections**. When adapting a new model, keep these slots as `IdentityOp` unless the model explicitly uses mHC.

### 5.4 Norm

| Type | Module | Source |
|------|--------|--------|
| TE Norm | `TENorm` | `megatron/core/extensions/transformer_engine/__init__.py` |
| Local Norm | `LocalNorm` | `loongforge/models/common/local_layers/local_norm.py` |
| Identity | `IdentityOp` | `megatron/core/transformer/identity_op.py` |

**When to use which**:
- Pre-attention / Pre-MLP norm: `TENorm` (standard) or `IdentityOp` (when norm is fused into the first linear via `TELayerNormColumnParallelLinear`)
- QK norm: `TENorm` (TE>=1.9) or `LocalNorm` (TE<1.9, avoids convergence degradation)
- VLM: Often uses `IdentityOp` for `input_layernorm` (fused into linear)

### 5.5 MTP (Multi-Token Prediction)

| Module | Source |
|--------|--------|
| `get_gpt_mtp_block_spec` | `megatron/core/models/gpt/gpt_layer_specs.py` |
| `MultiTokenPredictionBlock` | `megatron/core/transformer/multi_token_prediction.py` |

MTP config fields (on `TransformerConfig`):
- `mtp_num_layers: Optional[int] = None` — None = disabled
- `mtp_loss_scaling_factor: Optional[float] = None` — loss weight
- `mtp_loss_scaling_factor_decay_ratio: Optional[float] = None` — decay ratio across MTP layers
- `mtp_shared_layers: bool = False` — tie all MTP layers
- `mtp_connection_type: str = 'sequential'` — "sequential" (chain) or "parallel" (fan-out)

In layer_spec:
```python
if config.mtp_num_layers is not None:
    mtp_block_spec = get_gpt_mtp_block_spec(config, transformer_layer_spec_for_mtp, ...)
```

**Important**: `mtp_num_layers=0` still enters the MTP branch (Python truthiness check is `is not None`). For backbone verification, explicitly set to 0.

### 5.6 Positional Encoding

| Type | Source File |
|------|------------|
| Standard RoPE | `megatron/core/models/common/embeddings/rotary_pos_embedding.py` |
| YaRN RoPE | `megatron/core/models/common/embeddings/yarn_rotary_pos_embedding.py` |
| M-RoPE (VLM) | Implemented as `apply_rotary_fn` in VLM layer_spec (not a separate class) |

MLA models default to YaRN RoPE (`rope_type="yarn"`). Standard models use `rope_type="rope"` or set `position_embedding_type` in config.

---

## 6. Common Extension Patterns

### Pattern 1: Add a new model family with standard attention (reuse_megatron)

When the model uses standard GQA/MHA attention and dense MLP:
1. Create `*_config.py` inheriting from `BaseModelConfig`
2. Create `*_layer_spec.py` using `SelfAttention` + `MLP`
3. Create `*_model.py` with provider function
4. Add YAML config mapping fields to config class attributes

This is the simplest case — just change config fields and family/class names.

### Pattern 2: Add MLA model (wrap_megatron)

When the model uses MLA attention:
1. Config inherits from `BaseModelMLAConfig` (NOT `BaseModelConfig`)
2. Layer spec uses `MultiLatentAttention` + `MLASelfAttentionSubmodules`
3. MLA submodule slots differ from standard attention (no `linear_qkv`, separate Q/KV projections)
4. Must set `config.multi_latent_attention = True`
5. `MLATransformerConfig` defaults: `rope_type="yarn"`, `normalization="RMSNorm"`

### Pattern 3: Add MoE model (wrap_megatron)

When the model uses MoE:
1. Config includes `num_moe_experts`, `moe_layer_freq`, `moe_shared_expert_intermediate_size`, etc.
2. Layer spec creates both dense and MoE specs, selects per-layer based on `moe_layer_freq`
3. MoE spec uses `MoELayer` with `MoESubmodules` containing `shared_experts` + `experts`
4. `moe_layer_freq` accepts int (1:N ratio) or list (custom pattern like `[1,1,1,0,1,1,1,0]`)
5. Convert YAML must handle expert weight name mapping

### Pattern 4: Add new attention variant (new_impl / adapt_ref)

When the model has a fundamentally new attention mechanism:
1. Create new attention class — inherit from `MegatronModule` or appropriate base
2. Define `*Submodules` dataclass with the new submodule slots
3. In layer_spec, use `ModuleSpec(module=NewAttention, submodules=NewAttentionSubmodules(...))`
4. Add config field to control the variant (e.g., `experimental_attention_variant`)
5. Follow the DSA pattern for conditional dispatch in layer_spec
6. Read the Megatron source for `SelfAttention` or `MultiLatentAttention` to understand required interface:
   - `__init__(config, submodules, layer_number, attn_mask_type, attention_type, ...)`: Accept config and submodules
   - `forward(hidden_states, attention_mask, ...)`: Return `(output, bias)` tuple or `(output, bias, ...)`
   - Must handle TP communication correctly (column-parallel input, row-parallel output)

### Pattern 5: Add custom linear/norm layer

When the model needs custom projections (e.g., new compression/decompression):
1. Create the custom module in `loongforge/models/common/` or `loongforge/models/foundation/<family>/`
2. In layer_spec, replace the corresponding submodule slot: `linear_q_proj=CustomLinear`
3. Ensure the custom module follows the same interface as the replaced module:
   - Column-parallel: input [S, B, H] → output [S, B, H/TP]
   - Row-parallel: input [S, B, H/TP] → output [S, B, H]
4. Ensure weight names match what convert YAML expects

---

## 7. Deep Reading Guide for Phase 1 Step 2c

When Phase 1 encounters `diff == differs` or `new_component` (Branch B), the subagent must read and understand the relevant Megatron source code. Follow this procedure:

### Step 2c.1: Locate the Component Source File

Use Section 5 above to find the primary source file. For components not listed, use greedy search:
```bash
grep -r "class <ClassName>" <megatron_path>/megatron/core/ --include="*.py" -l
grep -r "<feature_keyword>" <megatron_path>/megatron/core/ --include="*.py" -l
```

### Step 2c.2: Read the Component Source File

Focus on:
- Class definition and inheritance chain
- `__init__` signature: what config fields and submodules it expects
- `forward` signature: what inputs it receives, what it returns
- How TP/EP communication is handled

**Default**: do not read full `forward()` implementation bodies — only signatures and class structure.

**Bounded behavior exception**: if `model_spec.behavior_modifications` or the component delta identifies a behavior-only risk, read only the minimal relevant `forward()`/helper slice needed to verify behavior equivalence. Record the exact source pointer and extracted behavior. Examples: activation clamp/offset in GLU helpers, MTP-specific router/attention branches, FP8 reference-load helpers, checkpoint key transforms, and model-specific guard logic.

### Step 2c.3: Read the Submodules Dataclass

Understand which submodule slots the component exposes. Each slot is a potential override point:
- Existing slots with direct replacement → `wrap_megatron` or `reuse_megatron`
- New slots required → `new_impl` with a new Submodules dataclass

### Step 2c.4: Check TransformerConfig for Existing Fields

Before adding custom config fields, check:
1. `TransformerConfig` (source: `transformer_config.py:35-1900+`) already has many fields
2. `MLATransformerConfig` (source: `transformer_config.py:1892-1964`) has MLA-specific fields
3. Only add fields that don't already exist upstream

### Step 2c.5: Read an Existing layer_spec for Reference

Choose the closest existing model:
- MLA+MoE: `loongforge/models/foundation/deepseek/deepseek_layer_spec.py`
- GQA dense: `loongforge/models/foundation/qwen2/qwen_layer_spec.py`
- VLM: `loongforge/models/foundation/qwen3_next/qwen3_next_layer_spec.py`

Understand: how the ModuleSpec tree is constructed, what config fields control conditional dispatch, how `multiacc_modules` is used.

### Step 2c.6: Assess Interface Coverage

Based on your reading, determine:
- Can the existing Megatron module fully handle the HF logic, including behavior modifications? → `reuse_megatron`
- Can it handle most of it, with small wrapper overrides or submodule-slot replacement? → `wrap_megatron`
- Does it lack key functionality, but Omni has a similar implementation? → `adapt_ref`
- Is there no equivalent at all? → `new_impl`
- Is the Megatron structure useful but the behavior model-specific or risky for other models? → `override_in_omni`
- Is shared Megatron behavior incomplete or incorrect for a broadly valid feature? → `modify_megatron_general`
- Is an existing non-Megatron shared module abstraction correct, but internal forward/helper behavior must change? → `modify_existing`
- Does a load/save/reference or execution flow need a default-no-op extension point? → `insert_hook`

---

## 8. LoongForge-Specific Patterns

These patterns exist in LoongForge but NOT in upstream Megatron-LM:

| Pattern | Location | Purpose |
|---------|----------|---------|
| `multiacc_modules` dispatch | `loongforge/models/dispatch.py` | Hardware abstraction layer (TE vs local) |
| `BaseModelConfig` / `BaseModelMLAConfig` | `loongforge/models/common/base_model_config.py` | Adds `PretrainedConfig` inheritance + LoongForge fields (freeze, model_type, peft_config, etc.) |
| `LocalNorm` | `loongforge/models/common/local_layers/local_norm.py` | Fallback norm for TE<1.9 QK norm |
| DSA fused variant | `loongforge/models/common/experimental_attention_variant/` | Omni-optimized fused DSA kernels |
| `moe_layer_freq` as list | `loongforge/models/foundation/deepseek/deepseek_layer_spec.py` | Per-layer dense/MoE pattern (also exists in upstream Megatron) |
| `first_k_dense_replace` | DeepSeek config | First N layers forced to dense (LoongForge convention, not upstream Megatron config field) |
