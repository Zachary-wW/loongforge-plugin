# MoE FFN Layer Spec Template (embedded in GQA layer spec)
# Applicable scenarios: Dense-attention models with MoE (Qwen3-MoE, InternLM-MoE, Minimax, etc.)
# Usage: Add the _get_mlp_module_spec helper to the GQA layer spec file
#
# Constraints:
#   - This helper must be kept even if the current target is a dense model
#   - MoE variants of the same family reuse the same layer_spec file and route through this helper

"""MoE FFN helper — embed this in <model>_layer_spec.py."""

from megatron.core.transformer.mlp import MLP, MLPSubmodules
from megatron.core.transformer.moe.moe_layer import MoELayer, MoESubmodules
from megatron.core.transformer.moe.experts import SequentialMLP, TEGroupedMLP
from megatron.core.transformer.spec_utils import ModuleSpec

from loongforge.models.dispatch import multiacc_modules


def _get_mlp_module_spec(
    num_experts: int = None, moe_grouped_gemm: bool = False
) -> ModuleSpec:
    """Helper function to get module spec for MLP/MoE.

    Keep this function even if the target model is dense-only.
    MoE variants of the same family reuse this file.
    """
    if num_experts is None:
        # Dense MLP w/ TE modules.
        return ModuleSpec(
            module=MLP,
            submodules=MLPSubmodules(
                linear_fc1=multiacc_modules.TELayerNormColumnParallelLinear,
                linear_fc2=multiacc_modules.TERowParallelLinear,
            ),
        )

    # MoE MLP
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

# ============================================================
# Usage in get_{{FAMILY}}_layer_with_te_spec:
#
#   mlp = _get_mlp_module_spec(
#       num_experts=config.num_moe_experts,
#       moe_grouped_gemm=config.moe_grouped_gemm,
#   )
#
#   # pre_mlp_layernorm: TENorm for MoE, IdentityOp for dense
#   pre_mlp_layernorm=(
#       multiacc_modules.TENorm if config.num_moe_experts else IdentityOp
#   ),
# ============================================================
