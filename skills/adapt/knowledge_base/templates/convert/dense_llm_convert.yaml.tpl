# Dense LLM Checkpoint Convert YAML Template
# Applicable scenarios: Standard Dense LLM HF ↔ mcore weight conversion
# Reference: llama3/ckpt_convert/llama3_convert.yaml, qwen2.5/ckpt_convert/qwen2_5_convert_llm.yaml
#
# Usage: Replace all {{PLACEHOLDER}} values to produce a valid conversion config
# Note: The name_map.mcore section is highly fixed and usually needs no modification

hydra:
  searchpath:
    - file://${oc.env:LOONGFORGE_PATH}/configs/models/

defaults:
  - {{FAMILY_DIR}}@module: ???
  - _self_

args:
  common:
    num_layers: ${module.num_layers}
    hidden_size: ${module.hidden_size}
    ffn_hidden_size: ${module.ffn_hidden_size}
    num_attention_heads: ${module.num_attention_heads}
    num_key_value_heads: ${module.num_query_groups}
    # {{VOCAB_SIZE}} Choose one approach:
    # vocab_size: {{FIXED_VOCAB_SIZE}}                          # Fixed value (e.g. LLaMA: 128256)
    # vocab_size: ${module.vocab_size_in_config_file}           # Reference model config
  # {{HF_ARGS}} Uncomment when args.huggingface is needed (for mcore→HF reverse conversion):
  # huggingface:
  #   architectures: [{{HF_ARCHITECTURE_CLASS}}]
  #   model_type: {{HF_MODEL_TYPE}}
  #   hidden_size: ${module.hidden_size}
  #   intermediate_size: ${module.ffn_hidden_size}
  #   num_attention_heads: ${module.num_attention_heads}
  #   num_hidden_layers: ${module.num_layers}
  #   num_key_value_heads: ${module.num_query_groups}
  mcore:
    untie_embeddings_and_output_weights: {{UNTIE_EMB}}
    use_rotary_position_embeddings: true
    add_embedding_padding: true
    transpose_mlp_dense: true
    transpose_query_key_value: true
    # {{MAKE_VOCAB}} Uncomment if needed:
    # make_vocab_size_divisible_by: ${module.make_vocab_size_divisible_by}

name_map:
  huggingface:
    word_embeddings: {{HF_EMBED_TOKENS}}                        # model.embed_tokens
    transformer: model
    layer_prefix: {{HF_LAYER_PREFIX}}                           # layers
    input_layernorm: {{HF_INPUT_LN}}                            # input_layernorm
    attention.query_key_value:                                   # Format 1A: separate QKV
    - {{HF_Q_PROJ}}                                             # self_attn.q_proj
    - {{HF_K_PROJ}}                                             # self_attn.k_proj
    - {{HF_V_PROJ}}                                             # self_attn.v_proj
    # {{QK_NORM_HF}} Uncomment when QK Norm is present:
    # attention.q_a_layernorm: {{HF_Q_NORM}}                    # self_attn.q_norm
    # attention.kv_a_layernorm: {{HF_K_NORM}}                   # self_attn.k_norm
    attention.dense: {{HF_O_PROJ}}                              # self_attn.o_proj
    post_attention_layernorm: {{HF_POST_LN}}                    # post_attention_layernorm
    mlp.dense_h_to_4h:                                          # Format 2A: SwiGLU gate+up
    - {{HF_GATE_PROJ}}                                          # mlp.gate_proj
    - {{HF_UP_PROJ}}                                            # mlp.up_proj
    mlp.dense_4h_to_h: {{HF_DOWN_PROJ}}                        # mlp.down_proj
    final_layernorm: {{HF_FINAL_LN}}                            # model.norm
    word_embeddings_for_head: {{HF_LM_HEAD}}                    # lm_head
  mcore:
    word_embeddings: embedding.word_embeddings
    word_position_embeddings: model.embedding.position_embeddings
    transformer: model
    layer_prefix: decoder.layers
    input_layernorm:
      name: self_attention.linear_qkv
      is_layernorm: true
    attention.query_key_value:
      name: self_attention.linear_qkv
      extra: true
    # {{QK_NORM_MCORE}} Uncomment when QK Norm is present:
    # attention.q_a_layernorm:
    #   name: self_attention.q_layernorm
    #   is_layernorm: false
    # attention.kv_a_layernorm:
    #   name: self_attention.k_layernorm
    #   is_layernorm: false
    attention.dense:
      name: self_attention.linear_proj
      extra: true
    post_attention_layernorm:
      name: mlp.linear_fc1
      is_layernorm: true
    mlp.dense_h_to_4h:
      name: mlp.linear_fc1
      extra: true
    mlp.dense_4h_to_h:
      name: mlp.linear_fc2
      extra: true
    final_layernorm:
      name: decoder.final_layernorm
      extra: true
    word_embeddings_for_head: output_layer
    transformer_tpl: model%d

torch_dtype: {{TORCH_DTYPE}}

# ============================================================
# Variable substitution guide:
#   {{FAMILY_DIR}}               → Hydra defaults reference directory (e.g. llama3, qwen2.5)
#   {{UNTIE_EMB}}                → true / false (= !tie_word_embeddings)
#   {{TORCH_DTYPE}}              → bfloat16 | float16 | float32
#   Values in HF name_map are the same for nearly all standard LLMs; keep the default commented values
#   If HF naming differs (e.g. Qwen v1's c_attn), replace the corresponding entries
#
# Field addition/removal rules:
#   - Has QK Norm → uncomment QK_NORM_HF and QK_NORM_MCORE blocks
#   - Needs reverse conversion → uncomment args.huggingface block
#   - Fixed vocab_size → use fixed value; dynamic reference → use ${module.xxx}
# ============================================================
