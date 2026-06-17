# MoE LLM Checkpoint Convert YAML Template
# Applicable scenarios: LLM weight conversion with MoE (Qwen3-MoE, DeepSeek-V2, etc.)
# Reference: qwen3/ckpt_convert/qwen3_moe_convert.yaml, deepseek2/ckpt_convert/deepseek_v2_convert.yaml
#
# Usage: Replace all {{PLACEHOLDER}} values to produce a valid conversion config
# Extends dense_llm_convert.yaml.tpl with MoE-specific mappings

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
    vocab_size: ${module.vocab_size_in_config_file}
    num_experts: ${module.num_experts}
  mcore:
    use_rotary_position_embeddings: true
    add_embedding_padding: true
    transpose_mlp_dense: true
    transpose_query_key_value: true
    untie_embeddings_and_output_weights: ${module.untie_embeddings_and_output_weights}
    # {{MAKE_VOCAB}}
    # make_vocab_size_divisible_by: ${module.make_vocab_size_divisible_by}

name_map:
  huggingface:
    word_embeddings: model.embed_tokens
    transformer: model
    layer_prefix: layers
    input_layernorm: input_layernorm
    attention.query_key_value:
    - self_attn.q_proj
    - self_attn.k_proj
    - self_attn.v_proj
    # {{QK_NORM_HF}} Uncomment when QK Norm is present:
    # attention.q_a_layernorm: self_attn.q_norm
    # attention.kv_a_layernorm: self_attn.k_norm
    attention.dense: self_attn.o_proj
    post_attention_layernorm: post_attention_layernorm
    # ── MoE mappings ────────────────────────────────────────────────
    moe.gate: {{HF_MOE_GATE}}                                  # mlp.gate
    moe.expert: {{HF_MOE_EXPERT}}                              # mlp.experts
    moe.expert_h_to_4h:
    - {{HF_EXPERT_GATE_PROJ}}                                   # gate_proj
    - {{HF_EXPERT_UP_PROJ}}                                     # up_proj
    moe.expert_4h_to_h: {{HF_EXPERT_DOWN_PROJ}}                # down_proj
    # {{SHARED_EXPERT_HF}} Uncomment when shared expert is present:
    # moe.shared_expert: {{HF_SHARED_EXPERT}}                   # mlp.shared_experts
    # moe.shared_expert_h_to_4h:
    # - {{HF_SHARED_GATE_PROJ}}                                 # mlp.shared_experts.gate_proj
    # - {{HF_SHARED_UP_PROJ}}                                   # mlp.shared_experts.up_proj
    # moe.shared_expert_4h_to_h: {{HF_SHARED_DOWN_PROJ}}       # mlp.shared_experts.down_proj
    # {{SHARED_EXPERT_GATE_HF}} Uncomment when shared expert gate is present:
    # moe.shared_expert_gate: {{HF_SHARED_EXPERT_GATE}}         # mlp.shared_expert_gate
    # {{DENSE_MLP_HF}} Uncomment for mixed dense+MoE layers (some layers are dense):
    # mlp.dense_h_to_4h: [mlp.gate_proj, mlp.up_proj]
    # mlp.dense_4h_to_h: mlp.down_proj
    final_layernorm: model.norm
    word_embeddings_for_head: lm_head
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
    post_attention_layernorm: pre_mlp_layernorm
    # ── MoE mcore mappings ──────────────────────────────────────────
    moe.gate: mlp.router
    moe.expert: mlp.experts.local_experts
    moe.groupedgemm.expert: mlp.experts
    moe.expert_h_to_4h:
      name: linear_fc1
      extra: true
    moe.expert_4h_to_h:
      name: linear_fc2
      extra: true
    # {{SHARED_EXPERT_MCORE}} Uncomment when shared expert is present:
    # moe.shared_expert_h_to_4h:
    #   name: shared_experts.linear_fc1
    #   extra: true
    # moe.shared_expert_4h_to_h:
    #   name: shared_experts.linear_fc2
    #   extra: true
    # {{DENSE_MLP_MCORE}} Uncomment for mixed dense+MoE layers:
    # mlp.dense_h_to_4h:
    #   name: mlp.linear_fc1
    #   extra: true
    # mlp.dense_4h_to_h:
    #   name: mlp.linear_fc2
    #   extra: true
    final_layernorm:
      name: decoder.final_layernorm
      extra: true
    word_embeddings_for_head: output_layer
    transformer_tpl: model%d

torch_dtype: {{TORCH_DTYPE}}

# ============================================================
# Variable substitution guide:
#   Base fields same as dense_llm_convert.yaml.tpl
#   {{HF_MOE_GATE}}             → HF router path (typically mlp.gate)
#   {{HF_MOE_EXPERT}}           → HF expert prefix (typically mlp.experts)
#   {{HF_EXPERT_GATE_PROJ}}     → Expert internal gate_proj name
#   {{HF_EXPERT_UP_PROJ}}       → Expert internal up_proj name
#   {{HF_EXPERT_DOWN_PROJ}}     → Expert internal down_proj name
#   {{HF_SHARED_EXPERT}}        → Shared expert prefix (e.g. mlp.shared_experts)
#   {{HF_SHARED_EXPERT_GATE}}   → Shared expert gate (e.g. mlp.shared_expert_gate)
#
# Field addition/removal rules:
#   - No shared expert → remove SHARED_EXPERT block
#   - No shared expert gate → remove SHARED_EXPERT_GATE block
#   - All-layer MoE (no dense layer mixing) → remove DENSE_MLP block
#   - Has QK Norm → uncomment QK_NORM block
#   - MLA models (DeepSeek) → require significant attention mapping changes; see DeepSeek convert YAML
#   - Has gate bias (e.g. DeepSeek-V3) → add moe.gate.bias mapping
# ============================================================
