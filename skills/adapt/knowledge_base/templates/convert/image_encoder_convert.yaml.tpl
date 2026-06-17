# Image Encoder Checkpoint Convert YAML Template
# Applicable scenarios: Vision encoder (ViT) HF ↔ mcore weight conversion
# Reference: image_encoder/ckpt_convert/qwen2_5_vit_convert.yaml, internvl_vit_0.3b_convert.yaml
#
# Usage: Replace all {{PLACEHOLDER}} values to produce a valid conversion config
# Note: Vision encoders have no word_embeddings / lm_head etc. language model fields

hydra:
  searchpath:
    - file://${oc.env:LOONGFORGE_PATH}/configs/models/

defaults:
  - image_encoder@module: ???
  - _self_

args:
  common:
    num_layers: ${module.num_layers}
    hidden_size: ${module.hidden_size}
    ffn_hidden_size: ${module.ffn_hidden_size}
    num_attention_heads: ${module.num_attention_heads}
    num_key_value_heads: ${module.num_query_groups}
  huggingface:
    # {{HF_VISION_ARGS}} Vision model-specific parameters:
    depth: ${module.num_layers}
    hidden_size: ${module.hidden_size}
    intermediate_size: ${module.ffn_hidden_size}
    num_heads: ${module.num_attention_heads}
    patch_size: ${module.patch_size}
    # {{EXTRA_HF_ARGS}} Model-specific:
    # out_hidden_size: ${module.hidden_size}             # Qwen2.5-ViT
    # fullatt_block_indexes: {{FULLATT_INDEXES}}         # Qwen2.5-ViT: [7, 15, 23, 31]
  mcore:
    use_rotary_position_embeddings: {{USE_ROPE}}         # true (Qwen2.5-ViT) | false (InternVL)
    use_distributed_optimizer: false
    transpose_mlp_dense: {{TRANSPOSE_MLP}}               # true (SwiGLU) | false (standard MLP)
    transpose_query_key_value: true

name_map:
  huggingface:
    transformer: {{HF_VISION_ROOT}}                      # visual | vision_model.encoder
    layer_prefix: {{HF_LAYER_PREFIX}}                    # blocks | layers
    input_layernorm: {{HF_LN1}}                          # norm1
    attention.query_key_value: {{HF_QKV}}                # attn.qkv (Format 1B: fused QKV)
    attention.dense: {{HF_PROJ}}                         # attn.proj
    post_attention_layernorm: {{HF_LN2}}                 # norm2
    mlp.dense_h_to_4h: {{HF_MLP_UP}}                    # mlp.fc1 or [mlp.gate_proj, mlp.up_proj]
    mlp.dense_4h_to_h: {{HF_MLP_DOWN}}                  # mlp.fc2 or mlp.down_proj
    # {{LAYER_SCALE_HF}} Uncomment for models with layer scale (InternVL etc.):
    # post_attention_layerscale:
    #   name: {{HF_LS1}}                                 # ls1
    #   is_direct_name: true
    # post_mlp_layerscale:
    #   name: {{HF_LS2}}                                 # ls2
    #   is_direct_name: true
  mcore:
    transformer: model
    layer_prefix: {{MCORE_LAYER_PREFIX}}                 # vision_model.decoder.layers | vision_model.encoder.layers
    input_layernorm:
      name: self_attention.linear_qkv
      is_layernorm: true
    attention.query_key_value:
      name: self_attention.linear_qkv
      extra: true
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
    # {{LAYER_SCALE_MCORE}} Uncomment for models with layer scale (InternVL etc.):
    # post_attention_layerscale: post_attention_layerscale
    # post_mlp_layerscale: post_mlp_layerscale
    transformer_tpl: model%d

torch_dtype: {{TORCH_DTYPE}}

# ── Vision Patch direct mappings (patch_embed, class_embedding, pos_embedding) ──
vision_patch:
  {{VISION_PATCH_MAPPINGS}}
  # Example - Qwen2.5-ViT:
  # vision_model.patch_embed.proj.weight: visual.patch_embed.proj.weight
  #
  # Example - InternVL:
  # vision_model.embeddings.class_embedding: vision_model.embeddings.class_embedding
  # vision_model.embeddings.patch_embedding.weight: vision_model.embeddings.patch_embedding.weight
  # vision_model.embeddings.patch_embedding.bias: vision_model.embeddings.patch_embedding.bias
  # vision_model.embeddings.position_embedding: vision_model.embeddings.position_embedding

# ============================================================
# Variable substitution guide:
#   {{HF_VISION_ROOT}}          → HF vision model root path (visual, vision_model.encoder)
#   {{HF_LAYER_PREFIX}}         → HF layer prefix (blocks, layers)
#   {{HF_LN1/LN2}}             → Layer normalization names (norm1/norm2)
#   {{HF_QKV}}                  → QKV path (Format 1B fused: attn.qkv)
#   {{HF_PROJ}}                 → Output projection path (attn.proj)
#   {{HF_MLP_UP}}               → MLP up path
#                                  Format 2B (non-gated): mlp.fc1
#                                  Format 2C (gated ViT): [mlp.gate_proj, mlp.up_proj]
#   {{HF_MLP_DOWN}}             → MLP down path (mlp.fc2 or mlp.down_proj)
#   {{MCORE_LAYER_PREFIX}}      → mcore side layer prefix
#   {{USE_ROPE}}                → true / false
#   {{TRANSPOSE_MLP}}           → true (SwiGLU) / false (standard MLP)
#   {{TORCH_DTYPE}}             → bfloat16 | float32
#   {{VISION_PATCH_MAPPINGS}}   → patch_embed etc. direct mappings (mcore_key: hf_key format)
#   {{FULLATT_INDEXES}}         → Full attention block index list (Qwen2.5-ViT: [7, 15, 23, 31]),
#                                  delete corresponding line if not applicable
#
# Field addition/removal rules:
#   - No layer scale → remove LAYER_SCALE block
#   - SwiGLU ViT (Qwen2.5) → transpose_mlp_dense=true, mlp.dense_h_to_4h is a list
#   - Standard ViT (InternVL) → transpose_mlp_dense=false, mlp.dense_h_to_4h is a string
#   - vision_patch section must include all non-layer direct weight mappings
# ============================================================
