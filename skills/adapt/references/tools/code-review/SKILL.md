---
name: code-review
description: >
  Perform semantic-level logic review on generated LoongForge network construction files, verifying implementation
  alignment with model_spec.yaml, and discovering field mapping errors, logic omissions, structural inconsistencies, etc.
  Called after Phase 1 linter passes completely and after Phase 2 convert files are generated.
  Use when semantic review of generated code is needed, or verifying architectural alignment correctness.
---

# code_review -- Generated Code Logic Review Tool

## Responsibility

After linter static rules pass, perform **semantic-level** logic review on generated files:
- Verify that implementation logic aligns with `run_dir/model_spec.yaml` (components section + weight_structure section)
- Discover defects beyond linter rules (field mapping errors, logic omissions, structural inconsistencies, etc.)
- Produce a structured review report; FAIL items block subsequent flow

## Invocation Timing

| Invocation Point | Review Target |
|------------------|---------------|
| After Phase 1 linter fully passes, before CHECKPOINT | `_config.py` / `_layer_spec.py` / `_model.py` |
| After Phase 2 convert files are generated, before k8s job submission | `convert_*.yaml` / `convert_*.sh` |

---

## Input

```
run_dir/model_spec.yaml     # Phase 0 sole artifact: components section (architecture blueprint) + weight_structure section (weight naming)
hf_path/                    # HF model directory; read source code on demand via model_spec hf_file/hf_line pointers
<list of files to review>    # Passed by the caller
```

---

## Phase 1 Review Checklist

### P1-C0 General File Protection Review (must check before any file change)

| Check Item | Method | Severity |
|------------|--------|----------|
| Changed file is not in `PROTECTED_FILES.md` "prohibited modification" list | Cross-check each file against `knowledge_base/schema/PROTECTED_FILES.md` | FAIL |
| "Append only" files have only new lines added, no deleted/modified lines | Compare git diff, confirm the file only has append operations | FAIL |
| Phase 2 `tools/convert_checkpoint/` modification does not alter existing branch logic | Compare git diff, confirm existing if/elif conditions and algorithms are unchanged | FAIL |

### P1-C1 `_config.py` Review

| Check Item | Method | Severity |
|------------|--------|----------|
| All fields described in model_spec `components[config].delta` are implemented, with no omissions | Cross-check each field against model_spec.yaml components.config.delta | FAIL |
| No reference family-specific fields (R015 semantic version) | Cross-check identically named fields in model_spec candidate_family, verify field origin belongs to target model | FAIL |
| GQA field (num_query_groups) default value is consistent with structural_tags in model_spec | Read model_spec.yaml components.attention.structural_tags | FAIL |
| Numeric field types are correct (int/float, no Optional wrapping required fields) | Check type annotations field by field | WARN |
| model_spec and model_type values are consistent with model_spec top-level model_category / candidate_family | Cross-check against model_spec.yaml top-level fields | FAIL |

### P1-C2 `_layer_spec.py` Review

| Check Item | Method | Severity |
|------------|--------|----------|
| Attention type (MHA/GQA/MLA) is consistent with model_spec | Read model_spec.yaml components.attention.structural_tags | FAIL |
| FFN type (SwiGLU/GeGLU/MoE etc.) is consistent with model_spec | Read model_spec.yaml components.ffn.structural_tags | FAIL |
| Norm position (pre_norm/post_norm) is consistent with model_spec | Read model_spec.yaml components.norm.structural_tags + read HF forward() call order via components.model.hf_file/hf_line | FAIL |
| QK norm presence is consistent with model_spec | Read model_spec.yaml components.attention_norm.diff; read HF attention source code via hf_file/hf_line to confirm q_norm/k_norm calls | FAIL |
| rope_theta / rotary_base is read from config (not hardcoded) | Check assignment source | WARN |
| MoE model: expert_num / top_k is consistent with model_spec | Read model_spec.yaml components.moe_gate.structural_tags | FAIL |

### P1-C3 `_model.py` Review

| Check Item | Method | Severity |
|------------|--------|----------|
| PHASE1_VERIFY hook exists and logic is correct (arange 100+seq_len) | String search for OMNI_PHASE1_VERIFY | FAIL |
| forward() parameter signature matches model_spec model_category | VLM has pixel_values, LLM does not | WARN |
| embed_tokens vocab_size source is config.vocab_size (not hardcoded) | Check embedding initialization | FAIL |
| When MTP is present: import_module result is tuple unpacking | Read model_spec.yaml components.mtp.diff -> check corresponding logic | FAIL |
| AutoModel.register() call is at end of file, parameter is correct family name | Search for AutoModel.register | FAIL |

### P1-C4 (Moved to Phase 2)

> Convert YAML is generated and reviewed in Phase 2; Phase 1 no longer produces convert files. For convert YAML related checks, see **P2-C2** below.

---

## Phase 2 Review Checklist

### P2-C1 Convert Shell Review

| Check Item | Method | Severity |
|------------|--------|----------|
| VLM: shell has exactly 3 independent `python ... model.py` or `python ... adapter.py` calls | grep count | FAIL |
| Each component save path variable (SAVE_LANGUAGE_MODEL / SAVE_VISION_MODEL / SAVE_ADAPTER) is defined | Search variable names | FAIL |
| HF_MODEL_PATH environment variable is read (not hardcoding hf_path) | Check path source | WARN |
| mcore->HF reverse shell is symmetric with forward shell (save = load relationship) | Compare SAVE/LOAD paths of both shells | FAIL |

### P2-C2 Convert YAML Completeness Review

| Check Item | Method | Severity |
|------------|--------|----------|
| `args.common` num_layers / hidden_size / num_heads is consistent with model_spec | Compare field by field against model_spec top-level fields | FAIL |
| LLM convert YAML: all sample_keys in `name_map` (model_spec weight_structure.components.llm.sample_keys) are covered by some rule | Match each sample_key | FAIL |
| VLM encoder YAML sample_keys are covered by name_map | Cross-check against model_spec.yaml weight_structure.components.vision_encoder.sample_keys | FAIL |
| VLM projector YAML sample_keys are covered by name_map | Cross-check against model_spec.yaml weight_structure.components.projector.sample_keys | FAIL |
| `name_map.huggingface` entry count is within 5% of model_spec weight_structure.total_keys | Count name_map entries | WARN |
| No duplicate mapping targets (two rules mapping to the same mcore key) | Check name_map value uniqueness | FAIL |

---

## Execution Flow

```
For each file to review:
  1. Read file contents
  2. Select corresponding review checklist by file type
  3. Read run_dir/model_spec.yaml (required)
  4. As needed, read corresponding HF source code from hf_path via model_spec components[*].hf_file/hf_line pointers
  5. Execute checks item by item, recording PASS / WARN / FAIL + specific location and reason

Generate review report:
  - FAIL items > 0: status = "failed", output all FAIL items; caller should fix and re-review according to the phase retry policy
  - Only WARN items: status = "passed", include WARN findings in details for the caller to display
  - No issues: status = "passed"

Fix principle: fix only one FAIL item at a time; after fixing, re-run linter (if .py changed), then re-invoke code_review.
```

---

## Output Format (JSON)

```json
{
  "status": "passed|failed|human_needed",
  "summary": "One-sentence description",
  "phase": "phase1|phase2",
  "reviewed_files": [
    "loongforge/models/foundation/xxx/xxx_config.py",
    "loongforge/models/foundation/xxx/xxx_layer_spec.py",
    "loongforge/models/foundation/xxx/xxx_model.py"
  ],
  "findings": [
    {
      "severity": "FAIL|WARN|PASS",
      "file": "loongforge/models/foundation/xxx/xxx_config.py",
      "check": "P1-C1: GQA field default value",
      "detail": "num_query_groups default value is 8, but model_spec attention.structural_tags shows 4; default value should be removed"
    }
  ]
}
```

---

## Error Handling

| Situation | Handling |
|-----------|----------|
| FAIL item still fails after fix (after 2 rounds) | Escalate to `human_needed` with findings attached |
| model_spec.yaml missing | Cannot execute review, output `human_needed` (Phase 0 not completed) |
| Review finds new_impl component logic questionable | Re-read HF source code via model_spec components[*].hf_file/hf_line and re-evaluate |
