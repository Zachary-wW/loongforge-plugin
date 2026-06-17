# MoE Config Dataclass Template
# Applicable scenarios: LLMs with MoE (Qwen3-MoE, InternLM-MoE, DeepSeek dense-attention MoE, etc.)
# Inherits from BaseModelConfig (except MLA series, which use mla_config.py.tpl)
#
# Usage: Replace all {{PLACEHOLDER}} values to produce runnable code
# Constraints:
#   - Must inherit BaseModelConfig (MLA models use BaseModelMLAConfig instead)
#   - Must use @dataclass decorator
#   - Only include fields that are new or need default value overrides relative to BaseModelConfig

"""{{FAMILY}} model config."""

from typing import Optional, Union, List
from dataclasses import dataclass

from loongforge.models.common.base_model_config import BaseModelConfig
from loongforge.utils.constants import LanguageModelFamilies


@dataclass
class {{FAMILY_CLASS}}Config(BaseModelConfig):
    """Configuration for {{FAMILY_UPPER}} model (dense + MoE variants).

    Fields beyond BaseModelConfig defaults:
    {{EXTRA_FIELDS_SUMMARY}}
    """

    # ── Required fields (NO default values, filled by YAML) ──────────────────
    num_layers: int
    hidden_size: int
    ffn_hidden_size: int
    num_attention_heads: int

    # ── GQA ──────────────────────────────────────────────────────────────────
    group_query_attention: bool = False
    num_query_groups: int = 1

    # ── MoE (None = dense) ────────────────────────────────────────────────────
    num_experts: int = None                       # total number of experts
    moe_ffn_hidden_size: int = None               # per-expert FFN hidden size
    # {{SHARED_EXPERT_FIELD}} uncomment if model has shared expert:
    # moe_shared_expert_intermediate_size: int = None
    moe_layer_freq: Optional[Union[int, List[int]]] = None  # which layers are MoE

    # ── RoPE ─────────────────────────────────────────────────────────────────
    position_embedding_type: str = "rope"
    add_position_embedding: bool = False
    rotary_interleaved: bool = False
    rotary_base: int = 10000           # override in YAML (e.g. Qwen=1000000)
    rotary_emb_func: str = "RotaryEmbedding"
    # {{MROPE_SECTION}} uncomment if model has multimodal mRoPE:
    # mrope_section: List[int] = None

    # ── Normalization ─────────────────────────────────────────────────────────
    normalization: str = "RMSNorm"

    # ── FFN ──────────────────────────────────────────────────────────────────
    swiglu: bool = True

    # ── Dropout ──────────────────────────────────────────────────────────────
    attention_dropout: float = 0
    hidden_dropout: float = 0

    # ── Linear bias ──────────────────────────────────────────────────────────
    add_bias_linear: bool = False
    add_qkv_bias: bool = False          # True for Qwen series; False for LLaMA series
    qk_layernorm: bool = False          # True for Qwen3 14B+ (set in YAML)

    # ── Vocab / Embedding ─────────────────────────────────────────────────────
    untie_embeddings_and_output_weights: bool = True
    vocab_size_in_config_file: int = None
    make_vocab_size_divisible_by: int = 128
    word_embeddings_for_head: str = "lm_head"   # "lm_head" or shared name

    # ── Other ─────────────────────────────────────────────────────────────────
    kv_channels: int = None

    model_type = LanguageModelFamilies.{{FAMILY_CONST}}

# ============================================================
# Variable substitution guide:
#   {{FAMILY}}               → Model family lowercase name, e.g. qwen3, internlm2_5
#   {{FAMILY_CLASS}}         → Config class prefix (UpperCamelCase), e.g. Qwen3, InternLM25
#   {{FAMILY_UPPER}}         → Display name, e.g. Qwen3, InternLM2.5
#   {{FAMILY_CONST}}         → LanguageModelFamilies enum value, e.g. QWEN3
#   {{EXTRA_FIELDS_SUMMARY}} → Brief description of new fields, e.g. "num_experts, moe_ffn_hidden_size"
#
# Field addition/removal rules:
#   - If target model has no MoE → remove num_experts/moe_ffn_hidden_size/moe_layer_freq lines
#   - If target model has shared expert → uncomment SHARED_EXPERT_FIELD
#   - If target model has mRoPE → uncomment MROPE_SECTION and set rotary_emb_func default value
#   - Do not add default values for num_layers/hidden_size/ffn_hidden_size/num_attention_heads
# ============================================================
