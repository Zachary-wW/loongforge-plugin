# Image Encoder YAML Config Template
# Applicable scenarios: Vision encoder configuration (ViT and variants)
# Reference: image_encoder/qwen2_5_vit.yaml, image_encoder/intern_vit_0.3b.yaml
#
# Usage: Replace all {{PLACEHOLDER}} values to produce a valid YAML config

_target_: loongforge.models.encoder.{{ENCODER_CONFIG_CLASS}}

num_layers: {{ENC_NUM_LAYERS}}
hidden_size: {{ENC_HIDDEN_SIZE}}
kv_channels: {{ENC_KV_CHANNELS}}
ffn_hidden_size: {{ENC_FFN_HIDDEN_SIZE}}
patch_size: {{ENC_PATCH_SIZE}}
num_attention_heads: {{ENC_NUM_HEADS}}
num_query_groups: {{ENC_NUM_QUERY_GROUPS}}
image_size: {{ENC_IMAGE_SIZE}}                    # int or [H, W]

# ── Activation & FFN ─────────────────────────────────────────────
# {{ACTIVATION}} Choose based on model:
# activation_func: ${act:silu}                    # Qwen2.5-ViT (SwiGLU)
# activation_func: ${act:gelu}                    # InternVL (standard GELU)
swiglu: {{ENC_SWIGLU}}                            # true for Qwen2.5-ViT; false for InternVL
# {{GATED_LINEAR}} Qwen2.5-ViT specific:
# gated_linear_unit: true

# ── Normalization ────────────────────────────────────────────────
normalization: {{ENC_NORMALIZATION}}              # "RMSNorm" | "LayerNorm"
# {{LAYERNORM_EPS}} Required for LayerNorm models:
# layernorm_epsilon: {{ENC_LAYERNORM_EPSILON}}

# ── Bias & Fusion ────────────────────────────────────────────────
add_bias_linear: {{ENC_ADD_BIAS_LINEAR}}
add_qkv_bias: {{ENC_ADD_QKV_BIAS}}
# {{QK_LAYERNORM}}
# qk_layernorm: false
bias_activation_fusion: {{ENC_BIAS_ACT_FUSION}}
apply_rope_fusion: {{ENC_APPLY_ROPE_FUSION}}

# ── Position Embedding ───────────────────────────────────────────
position_embedding_type: "{{ENC_POS_EMB_TYPE}}"   # "none" | "rope"

# ── Dropout ──────────────────────────────────────────────────────
hidden_dropout: 0
attention_dropout: 0

model_type: "{{ENC_MODEL_TYPE}}"

convert_file: ${oc.env:LOONGFORGE_PATH}/configs/models/image_encoder/ckpt_convert/{{ENC_CONVERT_YAML}}

# ============================================================
# Variable substitution guide:
#   {{ENCODER_CONFIG_CLASS}}     → Config class name (e.g. Qwen2VisionRMSNormConfig, InternVisionConfig)
#   {{ENC_NUM_LAYERS}}           → HF depth / num_hidden_layers
#   {{ENC_HIDDEN_SIZE}}          → HF hidden_size / embed_dim
#   {{ENC_KV_CHANNELS}}          → Per-head dimension (hidden_size / num_heads)
#   {{ENC_FFN_HIDDEN_SIZE}}      → HF intermediate_size / mlp_ratio * hidden_size
#   {{ENC_PATCH_SIZE}}           → HF patch_size
#   {{ENC_NUM_HEADS}}            → HF num_attention_heads / num_heads
#   {{ENC_NUM_QUERY_GROUPS}}     → Usually equals num_heads (vision encoders are typically MHA)
#   {{ENC_IMAGE_SIZE}}           → HF image_size (int or [H, W])
#   {{ENC_SWIGLU}}               → true (Qwen2.5-ViT) | false (InternVL, LLaVA)
#   {{ENC_NORMALIZATION}}        → "RMSNorm" | "LayerNorm"
#   {{ENC_ADD_BIAS_LINEAR}}      → True / False
#   {{ENC_ADD_QKV_BIAS}}         → True / False
#   {{ENC_BIAS_ACT_FUSION}}      → True / False
#   {{ENC_APPLY_ROPE_FUSION}}    → true / false
#   {{ENC_POS_EMB_TYPE}}         → "none" | "rope"
#   {{ENC_MODEL_TYPE}}           → e.g. "qwen2_5_vit", "intern_vit_300m"
#   {{ENC_CONVERT_YAML}}         → Convert YAML filename
#
# Field addition/removal rules:
#   - Qwen2.5-ViT: swiglu=true, gated_linear_unit=true, normalization=RMSNorm
#   - InternVL: swiglu=false, normalization=LayerNorm, layernorm_epsilon required
#   - LLaVA-ViT (Rice): swiglu=false, position_embedding_type=rope
#   - Delete conditional fields that are not applicable
# ============================================================
