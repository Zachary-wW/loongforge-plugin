# Dense LLM Model YAML Config Template
# Applicable scenarios: Standard Dense LLM (no MoE, no MLA)
# Reference: llama3/llama3_8b.yaml, qwen2.5/qwen2_5_7b.yaml
#
# Usage: Replace all {{PLACEHOLDER}} values to produce a valid YAML config

# {{FAMILY_LOWER}} model configuration
_target_: loongforge.models.foundation.{{FAMILY_CLASS}}Config
num_layers: {{NUM_LAYERS}}
hidden_size: {{HIDDEN_SIZE}}
ffn_hidden_size: {{FFN_HIDDEN_SIZE}}
num_attention_heads: {{NUM_ATTENTION_HEADS}}
# {{VOCAB_SIZE_LINE}} Uncomment and fill if the model requires explicit vocab_size:
# vocab_size_in_config_file: {{VOCAB_SIZE}}
# make_vocab_size_divisible_by: 128

# ── GQA (delete the following two lines if MHA) ──────────────────────────────
group_query_attention: true
num_query_groups: {{NUM_KV_HEADS}}

# ── Common defaults ──────────────────────────────────────────────
position_embedding_type: "rope"
add_position_embedding: false
rotary_interleaved: false
normalization: "RMSNorm"
swiglu: true
attention_dropout: 0
hidden_dropout: 0
add_bias_linear: false
add_qkv_bias: {{ADD_QKV_BIAS}}              # False in most cases; True for Qwen series
qk_layernorm: {{QK_LAYERNORM}}              # True for newer models like Qwen3 14B+
untie_embeddings_and_output_weights: true

# {{EXTRA_FIELDS}} Model-specific fields below; delete if not applicable:
# word_embeddings_for_head: "lm_head"       # Needed for Qwen series
# kv_channels: null                         # Needed for Qwen3+ (e.g. 128)
# rotary_emb_func: "RotaryEmbedding"        # Specify when not using default
# rotary_base: {{ROPE_THETA}}               # HF rope_theta
model_type: "{{MODEL_TYPE}}"

convert_file: ${oc.env:LOONGFORGE_PATH}/configs/models/{{FAMILY_DIR}}/ckpt_convert/{{CONVERT_YAML_NAME}}

# ============================================================
# Variable substitution guide:
#   {{FAMILY_CLASS}}          → Config class prefix, e.g. LLaMA, Qwen2
#   {{FAMILY_LOWER}}          → Lowercase display name, e.g. llama3, qwen2.5
#   {{FAMILY_DIR}}            → Config directory name, e.g. llama3, qwen2.5
#   {{NUM_LAYERS}}            → HF num_hidden_layers
#   {{HIDDEN_SIZE}}           → HF hidden_size
#   {{FFN_HIDDEN_SIZE}}       → HF intermediate_size
#   {{NUM_ATTENTION_HEADS}}   → HF num_attention_heads
#   {{NUM_KV_HEADS}}          → HF num_key_value_heads
#   {{ADD_QKV_BIAS}}          → true / false
#   {{QK_LAYERNORM}}          → true / false
#   {{ROPE_THETA}}            → HF rope_theta (e.g. 500000, 1000000)
#   {{MODEL_TYPE}}            → model_type string (e.g. "llama", "qwen")
#   {{VOCAB_SIZE}}            → HF vocab_size
#   {{CONVERT_YAML_NAME}}     → Conversion YAML filename
#
# Field addition/removal rules:
#   - If model is MHA (not GQA) → remove group_query_attention and num_query_groups
#   - If model does not need explicit vocab_size → remove vocab_size_in_config_file line
#   - {{EXTRA_FIELDS}} section: uncomment or delete based on model needs
#   - Do not modify Common defaults section values (unless the model actually differs)
# ============================================================
