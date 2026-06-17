# SwiGLU Dense FFN Template (standard MLP for GQA models)
# Applicable scenarios: Standard dense attention + SwiGLU activation (Qwen3, LLaMA3, InternLM, etc.)
# Used in conjunction with gqa.py.tpl / gqa_moe_vl.py.tpl
#
# Note: This snippet describes the dense branch (when num_experts=None) MLP spec
# If the model has MoE variants, the overall file should use _get_mlp_module_spec helper (see moe_ffn.py.tpl)

"""SwiGLU dense FFN spec snippet — embed in <model>_layer_spec.py."""

from megatron.core.transformer.mlp import MLP, MLPSubmodules
from megatron.core.transformer.spec_utils import ModuleSpec

from loongforge.models.dispatch import multiacc_modules


def _get_dense_mlp_spec() -> ModuleSpec:
    """Dense SwiGLU MLP spec using TE fused LayerNorm + ColumnParallel Linear.

    linear_fc1 uses TELayerNormColumnParallelLinear which fuses:
      - pre_mlp LayerNorm
      - gate_proj + up_proj (concat) ← SwiGLU requires 2x hidden
    linear_fc2 maps: [ffn_hidden_size] → [hidden_size]

    convert.yaml must set:
      mcore:
        transpose_mlp_dense: true   # splits gate/up correctly
    """
    return ModuleSpec(
        module=MLP,
        submodules=MLPSubmodules(
            linear_fc1=multiacc_modules.TELayerNormColumnParallelLinear,
            linear_fc2=multiacc_modules.TERowParallelLinear,
        ),
    )


# ============================================================
# Usage in TransformerLayerSubmodules:
#
#   TransformerLayerSubmodules(
#       ...
#       pre_mlp_layernorm=IdentityOp,    # Already fused into linear_fc1
#       mlp=_get_dense_mlp_spec(),
#       mlp_bda=multiacc_modules.get_bias_dropout_add,
#   )
#
# convert.yaml name_map:
#   mlp.dense_h_to_4h:
#     - mlp.gate_proj
#     - mlp.up_proj
#   mlp.dense_4h_to_h: mlp.down_proj
#
# config.py must have:
#   swiglu: bool = True
#   ffn_hidden_size: int   # per-expert dim; for dense models this is the full ffn hidden
# ============================================================
