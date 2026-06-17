---
name: omni-reviewer
description: >
  Three-part comprehensive review of /loongforge:adapt Phase 1 generated code: (1) code quality analysis (R001-R020
  static rule checks); (2) logic similarity analysis against backup code (MATCH/SIMILAR/DIVERGE three-level judgment);
  (3) DIVERGE root cause analysis (reading run_dir/model_spec.yaml and skills/adapt/ related files to locate
  strategy errors, rule gaps, Phase 1 Agent defects, etc., outputting fix suggestions).
  Called after backup-model has been run and Phase 1 is complete.
---

# omni_reviewer -- Code Review Tool

## Responsibility

Perform a three-part review of /loongforge:adapt Phase 1 generated code, producing a comprehensive scoring report:

1. **Code quality analysis**: Static review against `linter_rules/RULES.md` (R001-R020) and LoongForge coding standards
2. **Logic similarity analysis**: Per-file logic equivalence comparison between generated code and backup code
3. **DIVERGE root cause analysis**: For each logic difference, read `run_dir/model_spec.yaml` and skills/adapt/ related files to locate whether the root cause is a strategy decision error, rule gap, Phase 1 Agent defect, or other cause

Prerequisite: `references/tools/backup-model/SKILL.md` has been run to generate a backup, and /loongforge:adapt Phase 0-1 has been run to generate target code.

## Input Parameters

```
Required:
  --family <name>          Model family under review, e.g., qwen3
  --backup-path <path>     Directory containing manifest.json, e.g., ~/.omni_backup/qwen3/2026-04-13T10:00:00/

Optional:
  --run-dir <path>         /loongforge:adapt run_dir, for reading model_spec.yaml (default inferred from run_inputs.yml)
  --skip-quality           Skip code quality analysis, only do similarity comparison
  --skip-similarity        Skip similarity comparison, only do code quality analysis
```

## Part 1 -- Code Quality Analysis

Read `knowledge_base/linter_rules/RULES.md`, check each file against each rule:

| File | Core Check Items (Rule IDs) |
|------|----------------------------|
| `_config.py` | Base class correctness (R001), required fields without default values (R008), no deprecated decorators (R009/R004), model_spec/model_type present (R014), no field filtering (R015) |
| `_layer_spec.py` | No direct TE import (R002/R003), dense pre_mlp_layernorm=IdentityOp (R018), MTP returns Tuple (R016), moe_layer_freq complete parsing (R020) |
| `_model.py` | No @register_model_provider (R004), no unnecessary custom RoPE (R011/R012), MTP mtp_block_spec passing (R017) |
| `__init__.py` | Only two lines of re-export, format correct |
| `*.yaml` (config) | `_target_` points to existing class, required field value types reasonable |
| `*.sh` (convert/pretrain) | File header copyright notice present (R010); path variable completeness: `MEGATRON_PATH`, `LOONGFORGE_PATH`, `HF_MODEL_PATH` undefined -> WARN; `MODEL_SAVE_PATH` (or synonymous variable) undefined -> FAIL |

Each item outputs PASS / WARN / FAIL + specific location and reason.

## Part 2 -- Logic Similarity Analysis

Read generated code and backup code file by file, comparing the following dimensions.

**Path correspondence:**

| Generated Code Path | Backup Code Path |
|--------------------|-----------------|
| `loongforge/models/foundation/<family>/` | `<backup_path>/foundation/` |
| `configs/models/<family>/` | `<backup_path>/configs/` |
| `examples/<family>/` | `<backup_path>/examples/` |
| `loongforge/models/encoder/<family>_vision_models/` (if exists) | `<backup_path>/encoder/` |

Backup content for registration code (`__init__.py` registration lines, `config_map.py` entries) is read from `<backup_path>/patches/foundation_init.patch` and `<backup_path>/patches/config_map.patch`.

| Comparison Dimension | Description | Applicable Files |
|---------------------|-------------|-----------------|
| Class structure | Whether class names, inheritance relationships, class attributes (model_type, model_spec) are equivalent | _config.py, _model.py |
| Field set | Whether Config dataclass fields are fully reproduced (no omissions, no extras) | _config.py |
| Key function logic | Whether core branches of get_layer_spec, forward(), _preprocess() are equivalent | _layer_spec.py, _model.py |
| Weight mapping | Whether convert YAML name_map entries match backup (key set symmetric difference) | convert YAML |
| Registration code | Whether AutoModel.register(), config_map.py entries match backup | __init__.py, config_map |

Conclusion for each dimension:
- `MATCH`: Completely equivalent (identical logic and structure)
- `SIMILAR`: Logically equivalent but written differently. Judgment criteria: the two code segments produce the same operator call sequence and parameter sources under the same inputs,
  differing only in expression forms such as variable names, comments, blank lines, etc.
- `DIVERGE`: Substantive logic differences exist. Trigger conditions: any of the following --
  - Different control flow branches (if/else conditions differ)
  - Different operator types (e.g., RMSNorm vs LayerNorm)
  - Different field reference sources (hardcoded vs read from config)
  - Inconsistent entry counts (e.g., name_map key set has differences)
  Requires Part 3 root cause analysis

## Part 3 -- DIVERGE Root Cause Analysis

For each `DIVERGE` item in Part 2, execute the following analysis flow:

### Analysis Input Files (read in priority order)

| File | Purpose |
|------|---------|
| `run_dir/model_spec.yaml` | View `components[*].diff / strategy / delta / structural_tags` and `hf_file/hf_line` pointers for the component |
| `hf_path/<hf_file>` | Read HF source code via model_spec hf_file/hf_line pointers, judge whether generated code correctly understood the HF implementation |
| `knowledge_base/linter_rules/RULES.md` | Check if applicable rules have constraint conflicts or rule gaps |
| `knowledge_base/sources/<llm\|vlm>/<family>.yaml` | View the `traps` section for this family, confirm whether any known pitfalls were unrecorded or unheeded |
| `references/phases/phase1/agent.md` | View Phase 1 generation logic, locate corresponding step (Step 2 strategy decision / Step 3 generation) |
| `knowledge_base/failure_patterns/` | Check for similar historical failure cases |

### Root Cause Classification

| Root Cause Type | Judgment Condition | Description |
|----------------|--------------------|-------------|
| `model_spec_error` | model_spec.yaml components delta / structural_tags description is incorrect or missing | Phase 0 parsing stage issue; model_spec needs correction |
| `strategy_error` | Step 2 strategy decision (final_strategy) is wrong, causing generation direction deviation | Phase 1 Step 2 decision defect; re-decision needed |
| `codegen_rule_gap` | `linter_rules/RULES.md` lacks rule constraints for this pattern | Knowledge base rule gap; new rule needed |
| `phase1_agent_bug` | `references/phases/phase1/agent.md` or `adapt-phase1` flow steps have logic errors or omissions | Phase 1 Agent design defect |
| `source_trap_missing` | The pitfall is not recorded in the sources yaml `traps` section, causing the Agent to fall into it | Sources traps knowledge gap; needs supplementation |
| `template_error` | The attention/ffn template used does not match the target model | Template selection or content error |
| `unknown` | Root cause cannot be located through existing files | Requires in-depth human investigation |

> **Multiple root cause priority**: If multiple root cause conditions are satisfied simultaneously, select the first matching item in the following priority order:
> `model_spec_error` > `strategy_error` > `codegen_rule_gap` > `phase1_agent_bug` > `source_trap_missing` > `template_error` > `unknown`

### Output for Each DIVERGE Item

1. **Inconsistency details**: Specific line/logic difference, comparison snippet of backup code vs generated code
2. **Root cause classification**: Type from the table above
3. **Evidence**: Specific file paths and content from skills/adapt/ supporting the root cause judgment
4. **Fix suggestion**: Which file in skills/adapt/ should be modified, and what to change

## Comprehensive Scoring

| Dimension | Weight | Calculation Method |
|-----------|--------|--------------------|
| Code quality | 40% | Full score 40, each FAIL -10, each WARN -3, floor 0 |
| Logic similarity | 60% | Full score 60, total dimensions fixed at 5 (the 5 dimensions in the Part 2 table); inapplicable dimensions count as MATCH. MATCH x (60/5), SIMILAR x 0.7 x (60/5), DIVERGE x 0 |
| **Total score** | 100% | Sum of both dimensions |

Grading:
- 90-100 -> **Excellent** (can submit CR directly)
- 70-89 -> **Good** (recommend human confirmation of DIVERGE items before submitting)
- 50-69 -> **Needs Improvement** (requires fixing FAIL and DIVERGE items)
- <50 -> **Poor** (recommend re-running Phase 1)

## Output

**JSON report** (written to `<run_dir>/omni_review_report.json`):

```json
{
  "family": "qwen3",
  "timestamp": "2026-04-13T10:30:00",
  "backup_path": "~/.omni_backup/qwen3/2026-04-13T10:00:00/",
  "overall_score": 78,
  "grade": "Good",
  "quality_analysis": {
    "status": "passed",
    "fail_count": 0,
    "warn_count": 2,
    "score": 34,
    "findings": [
      {
        "severity": "WARN",
        "file": "loongforge/models/foundation/qwen3/qwen_config.py",
        "rule": "R008",
        "detail": "ffn_hidden_size has default value 0; recommend removing"
      }
    ]
  },
  "similarity_analysis": {
    "files_compared": 4,
    "dimensions_total": 5,
    "match": 3,
    "similar": 1,
    "diverge": 1,
    "score": 44,
    "diverge_details": [
      {
        "file": "qwen_layer_spec.py",
        "dimension": "Key function logic",
        "detail": "QK Norm conditional branch in get_layer_spec differs from backup logic: backup uses config.qk_layernorm, generated code hardcodes True",
        "backup_snippet": "qk_norm = RMSNorm if config.qk_layernorm else IdentityOp",
        "generated_snippet": "qk_norm = RMSNorm",
        "root_cause": "model_spec_error",
        "root_cause_evidence": "model_spec.yaml components.attention_norm.delta does not record qk_layernorm as optional field, causing Phase 1 Step 2 to treat it as constant True",
        "fix_suggestion": "Add to model_spec.yaml components.attention_norm.delta: 'qk_norm should use config.qk_layernorm to control; use IdentityOp when False'"
      }
    ]
  },
  "recommendation": "Code quality meets standard; layer_spec QK Norm conditional branch has logic difference requiring confirmation before submitting CR"
}
```

**Markdown summary** (written to `<run_dir>/omni_review_report.md`, human-readable).

## Execution Flow

```
1. Read backup-path/manifest.json, confirm family and delete_commit

2. Read knowledge_base/linter_rules/RULES.md

3. Determine run_dir
   - If --run-dir is provided, use directly
   - Otherwise: search for `adaptation_run_*/run_inputs.yml` in current working directory, take the one with newest mtime,
     use that directory as run_dir
   - If no run_inputs.yml exists, model_spec.yaml is unavailable (see error handling)
   Read run_dir/model_spec.yaml

4. Part 1: Code quality analysis (unless --skip-quality)
   - Enumerate all .py files under loongforge/models/foundation/<family>/
   - Enumerate all .yaml files under configs/models/<family>/
   - Enumerate all .sh files under examples/<family>/
   - Check each file against each rule, recording PASS/WARN/FAIL

5. Part 2: Logic similarity analysis (unless --skip-similarity)
   - Compare file contents directory by directory against backed_up_dirs in manifest.json
   - Registration code dimension: read <backup_path>/patches/foundation_init.patch and config_map.patch
     extract backup registration lines, compare against current loongforge/models/foundation/__init__.py and config_map.py
   - Output MATCH/SIMILAR/DIVERGE for each comparison dimension of each file

6. Part 3: DIVERGE root cause analysis (only when Part 2 has DIVERGE items)
   - For each DIVERGE item, read in order:
     a. components[*].diff/strategy/delta/structural_tags for the component in run_dir/model_spec.yaml
     b. Corresponding hf_file/hf_line pointers in model_spec, read HF source code for corresponding class, compare against HF original logic
     c. Related rules in knowledge_base/linter_rules/RULES.md
     d. Known pitfalls in traps section of knowledge_base/sources/<llm|vlm>/<family>.yaml
     e. Corresponding steps (Step 2 / Step 3) in references/phases/phase1/agent.md
     f. Similar historical cases in knowledge_base/failure_patterns/
   - Synthesize the above content, output for each DIVERGE item: root cause classification, evidence references, fix suggestions

7. Calculate comprehensive score, write JSON report and Markdown summary

8. Output terminal summary: total score, grade, key FAIL/DIVERGE items and root cause classifications
```

## Error Handling

| Situation | Handling |
|-----------|----------|
| backup-path does not exist or has no manifest.json | ABORT: prompt to run backup_model first |
| Family in manifest does not match --family | ABORT: parameter inconsistency |
| Generated code directory does not exist | ABORT: prompt to run /loongforge:adapt Phase 1 first |
| model_spec.yaml does not exist (--run-dir not provided and run_inputs.yml does not exist) | Skip checks dependent on model_spec, WARN prompt (Phase 0 not completed) |
| Generated code directory exists but some files are missing | WARN: list missing files; continue review for existing files; mark those files as `MISSING` in report |
