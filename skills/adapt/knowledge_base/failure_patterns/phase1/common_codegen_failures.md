# [Phase 1] Common Code Generation Failure Quick Reference

| Symptom | Investigation Point |
|---------|-------------------|
| `cannot import <Family>Config` | `__init__.py` does not export it; add the export |
| `TE module not found` / R002/R003 | layer_spec directly imports `transformer_engine.*`; change to `multiacc_modules.<Name>` |
| R007 failure | layer_spec references `MoELayer` but no MoE helper is defined; helper naming accepts both `_get_mlp_module_spec` and `get_moe_module_spec` forms |
| R008 failure | Config core fields have default values (e.g., `num_layers: int = 32`) |
| `reuse_megatron` component forward error | Check whether field names passed from layer_spec to Megatron modules are consistent with Megatron's interface |
| `wrap_megatron` subclass shape error | Check whether the output shape of overridden methods is consistent with what the base class expects |
| loss = NaN | Check `kv_channels` / layernorm epsilon / vocab_size mapping |
| Large loss deviation | Read HF attention/ffn implementation via model_spec pointers, compare mask / rope_theta / head_dim |
| MoE forward error | `pre_mlp_layernorm` uses IdentityOp; for MoE, TENorm must be used instead |

> For convert YAML / shell related failures (missing/duplicate keys, shape errors, R006 shell structure), see `failure_patterns/phase2/common_convert_failures.md`.
