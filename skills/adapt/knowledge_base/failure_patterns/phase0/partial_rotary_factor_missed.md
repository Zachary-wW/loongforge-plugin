# [Phase 0] partial_rotary_factor Field Not Extracted

| Field | Value |
|-------|-------|
| Phase | 0 |
| Applicable Models | General (known: Qwen3-Next `partial_rotary_factor=0.25`, MiniMax-M2.1 `partial_rotary_factor=0.5`) |
| Symptom | Phase 1 Step 7 forward comparison loss does not decrease or deviates significantly, but no crash |
| Date | 2026-04-01 |

## Symptom

During Phase 1 forward comparison, `abs_diff` is far greater than `1e-2`. Diagnosis reveals that the Omni side applies RoPE rotation across all head_dim dimensions (`rotary_percent=1.0`), while the HF side only rotates the `partial_rotary_factor` proportion of dimensions.

## Root Cause

When Phase 0 extracts config.json, it does not check the `partial_rotary_factor` field (or the equivalent `rotary_dim / head_dim` representation), causing the `model_spec.yaml` top-level to be missing this field. When Phase 1 generates the YAML, `rotary_percent` is not set, and the default value `1.0` causes incorrect RoPE dimensions.

## Prevention (Checks Phase 0 Should Perform)

When extracting basic fields from config.json, additionally check:
1. `partial_rotary_factor` exists -> write it directly to `model_spec.yaml` top-level with key name `partial_rotary_factor`
2. The above field is absent but both `rotary_dim` + `head_dim` exist -> compute `rotary_dim / head_dim` and write it
3. Neither exists -> do not write (default full-dimension rotation; Phase 1 will not set `rotary_percent`)

Also append `partial_rotary=<value>` to `components.positional_encoding.structural_tags` as an explicit marker.

## Fix (When Phase 1 Step 7 Fails)

1. Check whether `run_dir/model_spec.yaml` top-level has a `partial_rotary_factor` field
2. If missing, go back to hf_path/config.json to manually confirm, and add it to model_spec.yaml
3. Update the generated `configs/models/<family>/<model>.yaml`: add `rotary_percent: <value>`
4. Re-run Step 7 forward comparison
