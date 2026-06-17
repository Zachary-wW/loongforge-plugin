# GeGLU Dense FFN Template (for GELU-activated ViT or legacy LLMs)
# Applicable scenarios:
#   1. InternVision ViT (GELU, not SwiGLU)
#   2. LLaVA-OV Rice ViT
#   3. Qwen2-VL Vision Transformer (QuickGELU)
#   4. Any attention+GELU FFN vision encoder
#
# Key differences from SwiGLU:
#   - fc1 output goes directly to GELU, no gate split
#   - convert.yaml does not need transpose_mlp_dense: true
#   - ffn_hidden_size is the fc1 output dimension (no 2x doubling)

"""GELU dense FFN spec snippet — for ViT and non-SwiGLU models."""

from megatron.core.transformer.mlp import MLP, MLPSubmodules
from megatron.core.transformer.spec_utils import ModuleSpec

from loongforge.models.dispatch import multiacc_modules


def _get_gelu_mlp_spec() -> ModuleSpec:
    """Dense GELU MLP spec.

    Suitable for:
    - InternViT (GELU activation)
    - Rice ViT / LLaVA-OV vision encoder
    - Qwen2-VL vision encoder (QuickGELU — same structure, different activation)

    linear_fc1: [hidden_size] → [ffn_hidden_size]   (no gate/up split)
    linear_fc2: [ffn_hidden_size] → [hidden_size]

    convert.yaml does NOT need transpose_mlp_dense: true for this spec.
    name_map uses simple 1:1 mapping (no list concat).
    """
    return ModuleSpec(
        module=MLP,
        submodules=MLPSubmodules(
            # Note: TELayerNormColumnParallelLinear fuses pre-MLP LayerNorm.
            # For ViTs that have explicit LayerNorm before MLP, use this.
            # If the ViT has its own explicit norm, use TEColumnParallelLinear
            # and set pre_mlp_layernorm separately.
            linear_fc1=multiacc_modules.TELayerNormColumnParallelLinear,
            linear_fc2=multiacc_modules.TERowParallelLinear,
        ),
    )


# ============================================================
# convert.yaml name_map (GELU single-path fc1, no concat):
#
#   mlp.dense_h_to_4h: mlp.fc1     # ← single weight, not a list!
#   mlp.dense_4h_to_h: mlp.fc2
#
# Comparison with SwiGLU convert.yaml:
#   SwiGLU:
#     mlp.dense_h_to_4h:
#       - mlp.gate_proj    ← list! two weights
#       - mlp.up_proj
#   GELU:
#     mlp.dense_h_to_4h: mlp.fc1   ← string! single weight
#
# Actual HF weight names in different ViT implementations:
#   InternViT:   mlp.fc1 / mlp.fc2
#   Rice ViT:    mlp.fc1 / mlp.fc2 (or intermediate / output)
#   Qwen2-VL ViT: mlp.gate_proj / mlp.fc2 (Note: Qwen2-VL ViT also has gate_proj but is actually GELU-gated)
#     → For Qwen2-VL ViT, confirm whether SwiGLU-style based on HF config hidden_act
# ============================================================
