# [Phase 2] Common Convert Failure Quick Reference

| Symptom | Investigation Point |
|---------|-------------------|
| Convert shell execution failure (non-zero exit code) | Read stderr to locate the error line; common: environment variables `HF_MODEL_PATH` / `SAVE_ROOT` not set, or convert YAML path is incorrect |
| Roundtrip key missing | `model_spec.yaml` `weight_structure.components.<comp>.sample_keys` -> confirm `name_map.huggingface.*` coverage; common: routing_bias / lm_head.weight not added to name_map |
| Roundtrip key redundant | Compare `model_spec.yaml` `weight_structure.total_keys` against name_map entry count; common: attention.query_key_value written twice |
| Roundtrip shape incorrect | `model_spec.yaml` `weight_structure.components.<comp>.naming_pattern` + `args.common.num_layers/hidden_size`; common: `transpose_query_key_value: true` not added when TP>1 |
| Encoder key mismatch | `weight_structure.components.vision_encoder.sample_keys` -> read HF source via `components.vision_attention.hf_file/hf_line` pointers to confirm member naming |
| Projector key mismatch | `weight_structure.components.projector.sample_keys` -> read HF source via `components.projector.hf_file/hf_line` pointers to confirm |
| VLM missing 2nd/3rd convert YAML | R006: convert shell does not contain 3 independent python calls; need to add encoder / projector convert YAML + shell (regenerate in Step 3-4) |
| `ModuleNotFoundError` in convert script | PYTHONPATH does not include Megatron-LM or LoongForge; check shell script header exports |
| mcore ckpt directory empty after convert | `SAVE_ROOT` mount directory does not exist or has no write permission |
