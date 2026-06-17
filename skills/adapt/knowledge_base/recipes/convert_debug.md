# Phase 2 Convert Debug Manual

> For use when Phase 2 Step 3/4/5 fails. Includes: convert shell debugging, roundtrip diagnosis, name_map repair.

---

## Convert Shell Debugging (Step 3 Failure)

1. Read stderr to locate the error line
2. Check whether environment variables are correctly exported (`HF_MODEL_PATH` / `SAVE_ROOT` / `PYTHONPATH`)
3. If the error is in convert YAML parsing: open the corresponding YAML, check `name_map` format (key indentation, space after colon)
4. Re-execute the shell after fixing; each fix counts as one retry

---

## Roundtrip Diagnosis Flow (Step 5 Failure)

### Preferred: Compare Against weight_structure

1. Read `model_spec.yaml` `weight_structure.components.<comp>.sample_keys`, compare against `name_map.huggingface.*` one by one
2. If key is missing -> add to name_map
3. If key is redundant -> check for duplicate entries
4. If shape is wrong -> check `args.common` for `hidden_size / num_layers / num_attention_heads / kv_channels`

### As Needed: Read HF Source Code

Read the corresponding source code in `hf_path` via the `components[*].hf_file / hf_line` pointers in `model_spec.yaml` to confirm:
- Member naming of sub-modules in `__init__` (affects key prefix)
- Linear layer weight shape (affects transpose strategy)

---

## VLM Three-Component name_map Responsibility

| Component | Convert YAML | Common name_map Issues |
|-----------|-------------|----------------------|
| LLM backbone | `<llm>_convert.yaml` | Whether embedding / lm_head are tied; MTP layer key prefix |
| Vision encoder | `<enc>_convert.yaml` | patch_embed / pos_embed key naming; whether class_token exists |
| Projector | `<proj>_convert.yaml` | linear_proj vs mlp naming difference; whether bias has independent key |

---

## name_map Repair Verification

After fixing the convert YAML, you must re-execute from Step 3 (HF->mcore) in full; **you cannot only re-run Step 4 (mcore->HF)**, otherwise the mcore ckpt content will be inconsistent with name_map.
