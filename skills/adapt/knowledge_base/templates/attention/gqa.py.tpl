# GQA (Grouped Query Attention) Layer Spec Template
# Applicable scenarios: Standard GQA with optional QKNorm, using TE backend
# Corresponding models: LLaMA3, Qwen2/3, InternLM2.5, etc.
#
# Usage: Replace all {{PLACEHOLDER}} values to produce runnable code
# Constraints:
#   - All module references must go through multiacc_modules; direct import of TransformerEngine is prohibited
#   - qk_layernorm dynamically selects TENorm or IdentityOp based on config.qk_layernorm
#   - When TE version < 1.9, QKNorm must use LocalNorm (see is_te_min_version check)

"""{{FAMILY}} layer spec."""

from megatron.core.transformer.enums import AttnMaskType
from megatron.core.transformer.identity_op import IdentityOp
from megatron.core.transformer.spec_utils import ModuleSpec
from megatron.core.transformer.transformer_layer import (
    TransformerLayer,
    TransformerLayerSubmodules,
)
from megatron.core.transformer.transformer_config import TransformerConfig
from megatron.core.transformer.attention import SelfAttention, SelfAttentionSubmodules
from megatron.core.transformer.mlp import MLP, MLPSubmodules

from loongforge.utils import is_te_min_version
from loongforge.models.dispatch import multiacc_modules


def get_{{FAMILY}}_layer_with_te_spec(config: TransformerConfig) -> ModuleSpec:
    """Use this spec for an implementation using transformer, local or multi-accel engine"""
    # {{FAMILY_UPPER}} does not support MoE (remove if MoE is needed)
    assert config.num_moe_experts is None, "Not support MoE for {{FAMILY_UPPER}} model yet."

    # Dense MLP with TE modules (SwiGLU)
    dense_mlp = ModuleSpec(
        module=MLP,
        submodules=MLPSubmodules(
            linear_fc1=multiacc_modules.TELayerNormColumnParallelLinear,
            linear_fc2=multiacc_modules.TERowParallelLinear,
        ),
    )

    # QK Norm: use TENorm (TE >= 1.9) or LocalNorm (fallback)
    # {{QKNORM_COMMENT}}
    qk_norm = (
        multiacc_modules.TENorm
        if is_te_min_version("1.9.0")
        and config.normalization in ["LayerNorm", "RMSNorm"]
        else multiacc_modules.LocalNorm
    )

    return ModuleSpec(
        module=TransformerLayer,
        submodules=TransformerLayerSubmodules(
            input_layernorm=IdentityOp,          # Norm fused into TELayerNormColumnParallelLinear
            self_attention=ModuleSpec(
                module=SelfAttention,
                params={"attn_mask_type": AttnMaskType.causal},
                submodules=SelfAttentionSubmodules(
                    linear_qkv=multiacc_modules.TELayerNormColumnParallelLinear,
                    core_attention=multiacc_modules.DotProductAttention,
                    linear_proj=multiacc_modules.TERowParallelLinear,
                    # {{QKNORM_LINES}} If the model has no QKNorm, change the two lines below to IdentityOp
                    q_layernorm=qk_norm if config.qk_layernorm else IdentityOp,
                    k_layernorm=qk_norm if config.qk_layernorm else IdentityOp,
                    apply_rotary_fn=multiacc_modules.apply_rotary_pos_emb,
                ),
            ),
            self_attn_bda=multiacc_modules.get_bias_dropout_add,
            pre_mlp_layernorm=IdentityOp,        # Norm fused into TELayerNormColumnParallelLinear
            mlp=dense_mlp,
            mlp_bda=multiacc_modules.get_bias_dropout_add,
        ),
    )

# ============================================================
# Variable substitution guide:
#   {{FAMILY}}        → Model family lowercase name, e.g. qwen3, internlm2_5
#   {{FAMILY_UPPER}}  → Model family display name, e.g. Qwen3, InternLM2.5
#   {{QKNORM_COMMENT}} → If no QKNorm: # This model does not use QKNorm
#   {{QKNORM_LINES}}   → If confirmed no QKNorm, the qk_norm variable and two qk_layernorm lines can be removed
# ============================================================
