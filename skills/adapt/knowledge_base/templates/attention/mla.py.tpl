# MLA (Multi-Latent Attention) Layer Spec Template
# Applicable scenarios: DeepSeek series (MLA + optional MoE)
# Corresponding models: DeepSeek-V2-Lite, DeepSeek-V2, DeepSeek-V3
#
# Constraints:
#   - Config must inherit BaseModelMLAConfig
#   - MLASelfAttention replaces standard SelfAttention
#   - MoE experts require _get_moe_module_spec helper (keep even for dense models)
#   - Direct import of TransformerEngine is prohibited

"""{{FAMILY}} layer spec."""

from megatron.core.transformer.enums import AttnMaskType
from megatron.core.transformer.identity_op import IdentityOp
from megatron.core.transformer.spec_utils import ModuleSpec
from megatron.core.transformer.transformer_layer import (
    TransformerLayer,
    TransformerLayerSubmodules,
)
from megatron.core.transformer.transformer_config import TransformerConfig
from megatron.core.transformer.mlp import MLP, MLPSubmodules
from megatron.core.transformer.moe.moe_layer import MoELayer, MoESubmodules
from megatron.core.transformer.moe.experts import SequentialMLP, TEGroupedMLP

from loongforge.models.dispatch import multiacc_modules
# MLA attention class — lives in megatron.core (patched by LoongForge)
from megatron.core.transformer.multi_latent_attention import (
    MLASelfAttention,
    MLASelfAttentionSubmodules,
)
from megatron.core.transformer.custom_layers.transformer_engine import (
    TEDotProductAttention,
)


def _get_mlp_module_spec(
    num_experts: int = None, moe_grouped_gemm: bool = False
) -> ModuleSpec:
    """Helper function to get module spec for MLP/MoE — keep even for dense models."""
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


def get_{{FAMILY}}_layer_with_te_spec(config: TransformerConfig) -> ModuleSpec:
    """Use this spec for MLA-based model with optional MoE."""
    assert config.multi_latent_attention, (
        "{{FAMILY_UPPER}} requires multi_latent_attention=True in config"
    )

    mlp = _get_mlp_module_spec(
        num_experts=config.num_moe_experts,
        moe_grouped_gemm=config.moe_grouped_gemm,
    )

    return ModuleSpec(
        module=TransformerLayer,
        submodules=TransformerLayerSubmodules(
            input_layernorm=IdentityOp,
            self_attention=ModuleSpec(
                module=MLASelfAttention,
                params={"attn_mask_type": AttnMaskType.causal},
                submodules=MLASelfAttentionSubmodules(
                    linear_q_up_proj=multiacc_modules.TEColumnParallelLinear,
                    linear_kv_up_proj=multiacc_modules.TEColumnParallelLinear,
                    core_attention=multiacc_modules.DotProductAttention,
                    linear_proj=multiacc_modules.TERowParallelLinear,
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
#   {{FAMILY}}        → Model family lowercase name, e.g. deepseek
#   {{FAMILY_UPPER}}  → Model family display name, e.g. DeepSeek
#   {{MLA_IMPORT_NOTE}} → Verify MLASelfAttention import path based on actual Megatron patch version
#                         Currently uses megatron.core.transformer.multi_latent_attention
# ============================================================
