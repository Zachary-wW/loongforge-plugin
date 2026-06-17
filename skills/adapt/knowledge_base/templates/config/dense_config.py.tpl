# Dense LLM Config Dataclass Template
# Applicable scenarios: Standard Dense LLM (no MoE, no MLA)
# Reference: llama_config.py, qwen_config.py
#
# Usage: Replace all {{PLACEHOLDER}} values to produce runnable code
# Constraints:
#   - Must inherit BaseModelConfig (MLA models use BaseModelMLAConfig instead)
#   - Must use @dataclass decorator
#   - Only include fields that are new or need default value overrides relative to BaseModelConfig

"""{{FAMILY}} model config."""

from dataclasses import dataclass

from loongforge.models.common.base_model_config import BaseModelConfig
from loongforge.utils.constants import LanguageModelFamilies


@dataclass
class {{FAMILY_CLASS}}Config(BaseModelConfig):
    """Configuration for {{FAMILY_UPPER}} model.

    Fields beyond BaseModelConfig defaults:
    {{EXTRA_FIELDS_SUMMARY}}
    """

    # --- Required: base architecture params (fields with no default in BaseModelConfig) ---
    num_layers: int
    hidden_size: int
    ffn_hidden_size: int
    num_attention_heads: int

    # --- GQA (keep the following two lines if the model uses GQA; delete for MHA) ---
    group_query_attention: bool = True          # {{GQA_COMMENT}}
    num_query_groups: int = {{NUM_KV_HEADS}}    # HF: num_key_value_heads

    # --- RoPE configuration ---
    position_embedding_type: str = "rope"
    add_position_embedding: bool = False
    rotary_interleaved: bool = False            # False = split layout (default for LLaMA/Qwen)
    # rotary_base: int = {{ROPE_THETA}}         # Uncomment and fill with HF rope_theta

    # --- Normalization ---
    normalization: str = "RMSNorm"             # Almost all modern LLMs use RMSNorm

    # --- FFN ---
    swiglu: bool = True

    # --- Dropout (0 for both inference and training) ---
    attention_dropout: float = 0
    hidden_dropout: float = 0

    # --- Bias ---
    add_bias_linear: bool = False
    add_qkv_bias: bool = {{ADD_QKV_BIAS}}      # False in most cases; True for Qwen series

    # --- QK Norm (present in newer models like Qwen3) ---
    qk_layernorm: bool = {{QK_LAYERNORM}}      # Corresponds to HF use_qk_norm / qk_norm

    # --- Output weights ---
    untie_embeddings_and_output_weights: bool = True  # = not(tie_word_embeddings)

    # --- Model-specific fields below; delete if not applicable ---
    # {{MODEL_SPECIFIC_FIELDS}}
    # Example (Qwen3 MRoPE):
    # mrope_section: list = None    # HF: rope_scaling.mrope_section

    model_type = LanguageModelFamilies.{{FAMILY_CONST}}

# ============================================================
# Variable substitution guide:
#   {{FAMILY}}               → Model family lowercase name, e.g. qwen3, internlm2_5
#   {{FAMILY_CLASS}}         → Config class prefix (UpperCamelCase), e.g. Qwen3, InternLM25
#   {{FAMILY_UPPER}}         → Display name, e.g. Qwen3, InternLM2.5
#   {{EXTRA_FIELDS_SUMMARY}} → Brief description of new fields, e.g. "qk_layernorm, add_qkv_bias=True"
#   {{FAMILY_CONST}}         → LanguageModelFamilies enum value, e.g. QWEN3
#   {{NUM_KV_HEADS}}         → HF num_key_value_heads value
#   {{ROPE_THETA}}           → HF rope_theta value
#   {{ADD_QKV_BIAS}}         → True or False
#   {{QK_LAYERNORM}}         → True or False
#   {{MODEL_SPECIFIC_FIELDS}} → Remove or add model-specific fields
# ============================================================
