# MoE LLM Model YAML Config Template
# Applicable scenarios: LLMs with MoE (Qwen3-MoE, DeepSeek dense-attention MoE, etc.)
# Reference: qwen3/qwen3_235b_a22b.yaml, deepseek2/deepseek_v2.yaml
#
# Usage: Replace all {{PLACEHOLDER}} values to produce a valid YAML config

# {{FAMILY_LOWER}} model configuration
_target_: loongforge.models.foundation.{{FAMILY_CLASS}}Config
num_layers: {{NUM_LAYERS}}
hidden_size: {{HIDDEN_SIZE}}
ffn_hidden_size: {{FFN_HIDDEN_SIZE}}
num_attention_heads: {{NUM_ATTENTION_HEADS}}
# {{VOCAB_SIZE_LINE}}
vocab_size_in_config_file: {{VOCAB_SIZE}}
make_vocab_size_divisible_by: 128

# ── MoE ──────────────────────────────────────────────────────────
num_experts: {{NUM_EXPERTS}}
moe_ffn_hidden_size: {{MOE_FFN_HIDDEN_SIZE}}
# {{MOE_LAYER_FREQ}} Uncomment if MoE is not applied to all layers:
# moe_layer_freq: ${moe_freq:"{{MOE_LAYER_FREQ_EXPR}}"}
# {{SHARED_EXPERT}} Uncomment if shared expert is present:
# moe_shared_expert_intermediate_size: {{SHARED_EXPERT_SIZE}}

# ── GQA ──────────────────────────────────────────────────────────
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
add_qkv_bias: {{ADD_QKV_BIAS}}
qk_layernorm: {{QK_LAYERNORM}}
untie_embeddings_and_output_weights: true

# {{EXTRA_FIELDS}} Model-specific fields below; delete if not applicable:
# kv_channels: {{KV_CHANNELS}}             # Qwen3: 128
# rotary_emb_func: "RotaryEmbedding"
# rotary_base: {{ROPE_THETA}}
# word_embeddings_for_head: "lm_head"
# variable_seq_lengths: true
model_type: "{{MODEL_TYPE}}"

convert_file: ${oc.env:LOONGFORGE_PATH}/configs/models/{{FAMILY_DIR}}/ckpt_convert/{{CONVERT_YAML_NAME}}

# ============================================================
# Variable substitution guide (Dense fields same as dense_model.yaml.tpl; below are MoE-specific):
#   {{NUM_EXPERTS}}              → HF num_local_experts / num_experts
#   {{MOE_FFN_HIDDEN_SIZE}}      → HF expert intermediate_size / moe_intermediate_size
#   {{MOE_LAYER_FREQ_EXPR}}      → Layer frequency expression, e.g. "[0]*1+[1]*59"
#   {{SHARED_EXPERT_SIZE}}       → Shared expert intermediate_size
#   {{KV_CHANNELS}}              → Per-head dimension (if not hidden_size/num_heads)
#
# Field addition/removal rules:
#   - If MoE applies to all layers → remove moe_layer_freq line
#   - If no shared expert → remove moe_shared_expert_intermediate_size line
#   - MLA models (DeepSeek) require additional MLA-specific fields (see MLA reference):
#     q_lora_rank, kv_lora_rank, qk_head_dim, qk_pos_emb_head_dim, v_head_dim,
#     multi_latent_attention: true, apply_rope_fusion: true
# ============================================================
