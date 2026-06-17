# HF config.json -> Omni Field Map + YAML Verification Checklist

> Used jointly by Phase 1 Step 3 (generating _config.py) and Step 3.5 (YAML value verification).

---

## Core Field Mapping

| HF config.json Field | Omni Field | Notes |
|---------------------|-----------|-------|
| `num_hidden_layers` | `num_layers` | Direct copy |
| `hidden_size` | `hidden_size` | Direct copy |
| `intermediate_size` | `ffn_hidden_size` | Different names, easy to miss |
| `num_attention_heads` | `num_attention_heads` | Direct copy |
| `num_key_value_heads` | `num_query_groups` | When `< num_heads`, set `group_query_attention=True` |
| `rope_theta` | `rotary_base` | Different names |
| `partial_rotary_factor` (float, 0~1) | `rotary_percent` | If this field is absent but `rotary_dim` + `head_dim` exist, then `rotary_percent = rotary_dim / head_dim`; easy to miss, default 1.0 |
| `rms_norm_eps` | `layernorm_epsilon` | |
| `tie_word_embeddings` | `untie_embeddings_and_output_weights` | **Negated!** True->False, False->True |
| `head_dim` | `kv_channels` | Must be set when HF explicitly provides it |
| `num_experts` | `num_experts` | MoE |
| `moe_intermediate_size` | `moe_ffn_hidden_size` | MoE |
| `vocab_size` | `vocab_size_in_config_file` | Different names |
| `scoring_func: "sigmoid"` | `moe_router_score_function` | Default softmax; DeepSeek family must be `sigmoid` |
| `num_nextn_predict_layers` | `mtp_num_layers` | If HF has no such field, set to 0 |

For VLM, LLM backbone parameters are read from `text_config` (if `text_config` nesting exists).

---

## Step 3.5 YAML Value Verification Checklist

After generating `configs/models/<family>/<model>.yaml` and before entering the Linter, verify each item:

| YAML Field | HF Source Field | Verification Point |
|-----------|----------------|-------------------|
| `num_layers` | `num_hidden_layers` | Must be directly equal |
| `hidden_size` | `hidden_size` | Must be directly equal |
| `ffn_hidden_size` | `intermediate_size` | Different names, easy to miss |
| `num_attention_heads` | `num_attention_heads` | Must be directly equal |
| `num_query_groups` | `num_key_value_heads` | Different names |
| `kv_channels` | `head_dim` or `hidden_size/num_attention_heads` | Must be explicitly computed or read from HF config |
| `rotary_base` | `rope_theta` | Different names |
| `rotary_percent` | `partial_rotary_factor` or `rotary_dim/head_dim` | **If model_spec.yaml top-level has `partial_rotary_factor`, the YAML must set this value accordingly** |
| `vocab_size_in_config_file` | `vocab_size` | Different names |
| `mtp_num_layers` | `num_nextn_predict_layers` | If HF has no such field, fill 0 |
