# GQA + MoE Composite Layer Spec Template (with multimodal spec preserved)
# Applicable scenarios: Models supporting MoE that may have VLM variants (Qwen3 series, MIMO series, etc.)
# Differences from gqa.py.tpl:
#   1. Includes _get_mlp_module_spec helper
#   2. Includes multimodal spec functions (get_*_vl_layer_with_te_spec, apply_mrope, etc.)
#   3. pre_mlp_layernorm dynamically selected based on MoE

"""{{FAMILY}} layer spec."""

import torch

from megatron.core import parallel_state
from megatron.core.transformer.enums import AttnMaskType
from megatron.core.transformer.identity_op import IdentityOp
from megatron.core.transformer.spec_utils import ModuleSpec
from megatron.core.transformer.transformer_layer import (
    TransformerLayer,
    TransformerLayerSubmodules,
)
from megatron.core.transformer.attention import SelfAttention, SelfAttentionSubmodules
from megatron.core.transformer.transformer_config import TransformerConfig
from megatron.core.transformer.mlp import MLP, MLPSubmodules
from megatron.core.transformer.moe.moe_layer import MoELayer, MoESubmodules
from megatron.core.transformer.moe.experts import SequentialMLP, TEGroupedMLP

from loongforge.utils import is_te_min_version
from loongforge.models.dispatch import multiacc_modules
from loongforge.models.omni_models.utils import get_pos_emb_on_this_cp_rank


# ── MoE helper ──────────────────────────────────────────────────────────────
# Keep this even if target model is dense-only. MoE variants of the same family
# reuse this file and route through this helper.
def _get_mlp_module_spec(
    num_experts: int = None, moe_grouped_gemm: bool = False
) -> ModuleSpec:
    """Helper function to get module spec for MLP/MoE."""
    if num_experts is None:
        return ModuleSpec(
            module=MLP,
            submodules=MLPSubmodules(
                linear_fc1=multiacc_modules.TELayerNormColumnParallelLinear,
                linear_fc2=multiacc_modules.TERowParallelLinear,
            ),
        )
    if moe_grouped_gemm:
        assert multiacc_modules.TEColumnParallelGroupedLinear is not None
        expert_module = TEGroupedMLP
        linear_fc1 = multiacc_modules.TEColumnParallelGroupedLinear
        linear_fc2 = multiacc_modules.TERowParallelGroupedLinear
    else:
        expert_module = SequentialMLP
        linear_fc1 = multiacc_modules.TEColumnParallelLinear
        linear_fc2 = multiacc_modules.TERowParallelLinear
    return ModuleSpec(
        module=MoELayer,
        submodules=MoESubmodules(
            experts=ModuleSpec(
                module=expert_module,
                submodules=MLPSubmodules(
                    linear_fc1=linear_fc1,
                    linear_fc2=linear_fc2,
                ),
            )
        ),
    )


# ── Primary Dense/MoE LLM spec ──────────────────────────────────────────────
def get_{{FAMILY}}_layer_with_te_spec(config: TransformerConfig) -> ModuleSpec:
    """Use this spec for an implementation using transformer, local or multi-accel engine."""
    assert not config.multi_latent_attention, (
        "Not supporting multi-latent attention for {{FAMILY_UPPER}} model yet."
    )

    mlp = _get_mlp_module_spec(
        num_experts=config.num_moe_experts,
        moe_grouped_gemm=config.moe_grouped_gemm,
    )

    qk_norm = (
        multiacc_modules.TENorm
        if is_te_min_version("1.9.0")
        and config.normalization in ["LayerNorm", "RMSNorm"]
        else multiacc_modules.LocalNorm
    )

    return ModuleSpec(
        module=TransformerLayer,
        submodules=TransformerLayerSubmodules(
            input_layernorm=IdentityOp,
            self_attention=ModuleSpec(
                module=SelfAttention,
                params={"attn_mask_type": AttnMaskType.causal},
                submodules=SelfAttentionSubmodules(
                    linear_qkv=multiacc_modules.TELayerNormColumnParallelLinear,
                    core_attention=multiacc_modules.DotProductAttention,
                    linear_proj=multiacc_modules.TERowParallelLinear,
                    q_layernorm=qk_norm if config.qk_layernorm else IdentityOp,
                    k_layernorm=qk_norm if config.qk_layernorm else IdentityOp,
                    apply_rotary_fn=multiacc_modules.apply_rotary_pos_emb,
                ),
            ),
            self_attn_bda=multiacc_modules.get_bias_dropout_add,
            pre_mlp_layernorm=(
                multiacc_modules.TENorm if config.num_moe_experts else IdentityOp
            ),
            mlp=mlp,
            mlp_bda=multiacc_modules.get_bias_dropout_add,
        ),
    )


# ── VLM variant spec (LLaVA-OV style) ───────────────────────────────────────
# Keep this even if target adaptation is dense LLM only.
# VLM pipeline references this via config.model_spec.
def get_{{FAMILY}}_llavaov_layer_with_te_spec(config: TransformerConfig) -> ModuleSpec:
    """Spec for LLaVA-OV VLM variant (no TE version gate on QKNorm)."""
    assert not config.multi_latent_attention, (
        "Not supporting multi-latent attention for {{FAMILY_UPPER}} model yet."
    )
    mlp = _get_mlp_module_spec(
        num_experts=config.num_moe_experts,
        moe_grouped_gemm=config.moe_grouped_gemm,
    )
    qk_norm = (
        multiacc_modules.TENorm
        if config.normalization in ["LayerNorm", "RMSNorm"]
        else multiacc_modules.LocalNorm
    )
    return ModuleSpec(
        module=TransformerLayer,
        submodules=TransformerLayerSubmodules(
            input_layernorm=IdentityOp,
            self_attention=ModuleSpec(
                module=SelfAttention,
                params={"attn_mask_type": AttnMaskType.causal},
                submodules=SelfAttentionSubmodules(
                    linear_qkv=multiacc_modules.TELayerNormColumnParallelLinear,
                    core_attention=multiacc_modules.DotProductAttention,
                    linear_proj=multiacc_modules.TERowParallelLinear,
                    q_layernorm=qk_norm if config.qk_layernorm else IdentityOp,
                    k_layernorm=qk_norm if config.qk_layernorm else IdentityOp,
                    apply_rotary_fn=multiacc_modules.apply_rotary_pos_emb,
                ),
            ),
            self_attn_bda=multiacc_modules.get_bias_dropout_add,
            pre_mlp_layernorm=(
                multiacc_modules.TENorm if config.num_moe_experts else IdentityOp
            ),
            mlp=mlp,
            mlp_bda=multiacc_modules.get_bias_dropout_add,
        ),
    )


# ── mRoPE helpers (needed by VL spec below) ──────────────────────────────────
def _rotate_half(x):
    x1, x2 = torch.chunk(x, 2, dim=-1)
    return torch.cat((-x2, x1), dim=-1)


def _apply_mrope_bshd(t, freq, config, cu_seqlens, mscale: float = 1.0):
    """Apply Rotary Position Embedding with Multimodal Sections to query/key."""
    rot_dim = freq.shape[-1]
    freq = freq.permute(2, 1, 0, 3).contiguous()
    t, t_pass = t[..., :rot_dim], t[..., rot_dim:]
    cos_ = (torch.cos(freq) * mscale).to(t.dtype)
    sin_ = (torch.sin(freq) * mscale).to(t.dtype)
    t = (t * cos_) + (_rotate_half(t) * sin_)
    t = torch.cat((t, t_pass), dim=-1)
    return t


def apply_mrope(t, freq, config, cu_seqlens=None, mscale: float = 1.0, cp_group=None):
    """Entry point for mRoPE application; handles packed sequences."""
    if cu_seqlens is not None:
        cp_size = (
            cp_group.size()
            if cp_group is not None
            else parallel_state.get_context_parallel_world_size()
        )
        cp_rank = parallel_state.get_context_parallel_rank()
        cu_seqlens = cu_seqlens // cp_size
        seqlens = (cu_seqlens[1:] - cu_seqlens[:-1]).tolist()
        return torch.cat(
            [
                _apply_mrope_bshd(
                    x.unsqueeze(1),
                    freq[:, :, int(cu_seqlens[i]): int(cu_seqlens[i]) + x.size(0), :],
                    config,
                    cu_seqlens,
                    mscale,
                )
                for i, x in enumerate(torch.split(t, seqlens))
            ]
        ).squeeze(1)
    else:
        return _apply_mrope_bshd(t, freq, config, cu_seqlens, mscale)


# ── VL spec with mRoPE ────────────────────────────────────────────────────────
def get_{{FAMILY}}_vl_layer_with_te_spec(config: TransformerConfig) -> ModuleSpec:
    """Spec for Qwen-VL style VLM (mRoPE, apply_mrope instead of apply_rotary_pos_emb)."""
    assert not config.multi_latent_attention, (
        "Not supporting multi-latent attention for {{FAMILY_UPPER}} model yet."
    )
    mlp = _get_mlp_module_spec(
        num_experts=config.num_moe_experts,
        moe_grouped_gemm=config.moe_grouped_gemm,
    )
    qk_norm = (
        multiacc_modules.TENorm
        if is_te_min_version("1.9.0")
        and config.normalization in ["LayerNorm", "RMSNorm"]
        else multiacc_modules.LocalNorm
    )
    return ModuleSpec(
        module=TransformerLayer,
        submodules=TransformerLayerSubmodules(
            input_layernorm=IdentityOp,
            self_attention=ModuleSpec(
                module=SelfAttention,
                params={"attn_mask_type": AttnMaskType.causal},
                submodules=SelfAttentionSubmodules(
                    linear_qkv=multiacc_modules.TELayerNormColumnParallelLinear,
                    core_attention=multiacc_modules.DotProductAttention,
                    linear_proj=multiacc_modules.TERowParallelLinear,
                    q_layernorm=qk_norm if config.qk_layernorm else IdentityOp,
                    k_layernorm=qk_norm if config.qk_layernorm else IdentityOp,
                    apply_rotary_fn=apply_mrope,   # ← key difference from LLM spec
                ),
            ),
            self_attn_bda=multiacc_modules.get_bias_dropout_add,
            pre_mlp_layernorm=(
                multiacc_modules.TENorm if config.num_moe_experts else IdentityOp
            ),
            mlp=mlp,
            mlp_bda=multiacc_modules.get_bias_dropout_add,
        ),
    )

# ============================================================
# Variable substitution guide:
#   {{FAMILY}}        → Model family lowercase name, e.g. qwen3, mimo
#   {{FAMILY_UPPER}}  → Model family display name, e.g. Qwen3, MIMO
#
# Function naming rules (must correspond to config.model_spec field):
#   LLM dense/MoE   → get_{{FAMILY}}_layer_with_te_spec
#   LLaVA-OV VLM   → get_{{FAMILY}}_llavaov_layer_with_te_spec
#   Qwen-VL mRoPE  → get_{{FAMILY}}_vl_layer_with_te_spec
#
# If the target model family has no planned VLM variant, the VL spec functions
# can be removed; but _get_mlp_module_spec and mRoPE helpers must be kept if
# the reference model has them.
# ============================================================
