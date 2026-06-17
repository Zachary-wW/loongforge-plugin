---
name: backup-model
description: >
  Model code backup tool before /loongforge:adapt end-to-end verification. Given a model family name, fully backs up
  its network construction code, configuration YAML, example scripts, and registration code to an external path,
  then removes them from the repository, preparing a baseline for /loongforge:adapt generation effectiveness verification.
  Used in conjunction with omni-reviewer: backup-model backup -> Phase 0-1 generation -> omni-reviewer review.
  Use when verifying /loongforge:adapt adaptation effectiveness, or clearing model code to create a fresh adaptation scenario.
---

# backup_model -- Model Code Backup Tool

## Responsibility

Given a model family name, fully back up all of its code in the omni repository to an external path, then delete it from the repository, preparing for /loongforge:adapt verification.

Used with `omni_reviewer.md`: first backup_model clears target model code, then run /loongforge:adapt Phase 0-1, and finally omni_reviewer evaluates restoration quality.

## Input Parameters

```
Required:
  --family <name>       Model family name, e.g., qwen3, deepseek_v3
  --backup-root <path>  External backup root directory, e.g., ~/.omni_backup

Optional:
  --dry-run             Only print files to be deleted, do not execute
  --no-commit           Execute file deletion but skip git commit (for debugging)
```

## Backup Scope (full)

| File Type | Path |
|-----------|------|
| Network construction code | `loongforge/models/foundation/<family>/` (if exists; may not exist for VLM sharing LLM foundation, see "Shared Foundation") |
| VLM-specific code within shared Foundation | Code in `loongforge/models/foundation/<llm_family>/` containing `<family>` VLM layer spec, etc. (see "Shared Foundation") |
| VLM vision encoder (if exists) | `loongforge/models/encoder/<family>_vision_models/` |
| Model configuration YAML | `configs/models/<family>/` (including `ckpt_convert/` subdirectory conversion YAML) |
| Module configuration YAML -- Foundation (VLM) | `configs/models/<foundation_config_dir>/` (LLM foundation config directory referenced by VLM via Hydra defaults, see Step 3) |
| Module configuration YAML -- Encoder (VLM) | `configs/models/image_encoder/<encoder_config_name>.yaml` (vision encoder config file referenced by VLM via Hydra defaults) |
| Module configuration YAML -- Projector (VLM) | `configs/models/image_projector/<projector_config_name>.yaml` (projector config file referenced by VLM via Hydra defaults) |
| Conversion YAML (vision encoder) | YAML files in `configs/models/image_encoder/ckpt_convert/` containing `<family>` (VLM applicable) |
| Conversion YAML (projector) | YAML files in `configs/models/image_projector/ckpt_convert/` containing `<family>` (VLM applicable) |
| Example scripts | `examples/<family>/` |
| chat_template registration line | `_register_chat_template(...)` block in `loongforge/data/chat_template.py` containing `name="<family>"` |
| Foundation `__init__.py` registration line | Import + `AutoModel.register(...)` lines in `loongforge/models/foundation/__init__.py` containing `<Family>Model, <Family>Config` |
| config_map entry | Entry in `loongforge/utils/config_map.py` containing `<family>` |
| VLM vision encoder registration line | Import + `AutoModel.register(...)` lines in `loongforge/models/encoder/__init__.py` containing `<Family>Vision|<Family>Adapter|<Family>Config|<Family>AdapterConfig` |
| Model family enum constant | Enum entry in `loongforge/utils/constants.py` containing `<family>` (`<FAMILY> = "<family>"`) |
| Dedicated trainer import | Import line in `loongforge/train/__init__.py` containing `<family>` |
| Dedicated trainer implementation (single file) | `loongforge/train/sft/sft_<family>.py` (if exists) |
| Dedicated trainer implementation (directory) | `loongforge/train/embodied/` (if exists and specific to this family), `loongforge/train/diffusion/` (same) |
| Model-specific validation logic | Validation code block in `loongforge/train/validators.py` containing `<family>` |
| Family branch in multimodal combination code | if branch or exclusion logic in `loongforge/models/omni_models/` containing `<family>` (e.g., `fine_grained_callables.py`) |
| Model-specific data processing | `loongforge/data/<family>/` directory and `loongforge/data/*<family>*.py` files (if exists) |
| Model-specific subclasses/functions in shared files | See "Model-Specific Code in Shared Files" below |
| Conversion engine model-specific code | Code in `tools/convert_checkpoint/` related to this family's least-shared conversion logic (see Step 5b) |

> **Conversion engine code cleanup principle**: `tools/convert_checkpoint/` is a purely YAML-driven generic framework; most code does not depend on specific models.
> When cleaning up, **no need to consider the impact of deletion on other models** (this tool is for verification). Steps:
> - Look up the "Canonical Key Frequency Reference Table", find all keys with the fewest occurrences for this family, and delete them all
> - `tools/convert_checkpoint/module_convertor/adapter_<family>.py` (e.g., `adapter_internvl.py`)
> - `tools/convert_checkpoint/<family>/` directory (e.g., `pi05/`)
> - `<family>` related entries in `BIG_MODEL_LIST` within `tools/convert_checkpoint/module_convertor/model.py`
> - For VLM, clean up each module (LLM backbone, vision encoder, projector) separately

> **Foundation/Encoder directory location**: This tool is for verification, **no need to consider the impact of deletion on other models**; shared modules are also deleted as entire directories.
> VLM foundation/encoder directory names typically differ from the family name (they reference other family directories via Hydra defaults).
> Steps 1-3 dynamically locate the actual directories by parsing the network construction YAML's Hydra defaults and the encoder config's `_target_` field.

> **`<code_prefix>` code matching prefix**: This tool uses `<family>` to locate configs and examples directories,
> but all other code artifacts (trainer, adapter, data, shared files, etc.) use `<code_prefix>` as the grep anchor:
> - **VLM**: Derived by removing the `_vision_models` suffix from the parsed `<encoder_dir>` (e.g., `internvl_vision_models` -> `internvl`).
>   Code artifacts are prefixed by encoder module name, independent of family version number (internvl2.5 and internvl3.5 share the same code).
> - **LLM**: `<code_prefix>` = `<family>`, and `<family_us>` = `<family>.replace('.', '_')` for filename matching.
> Automatically derived in Steps 1-4.
>
> **`<Family>` naming convention**: `<Family>` is the CamelCase form of `<family>`
> (e.g., `qwen3` -> `Qwen3`, `deepseek_v3` -> `DeepseekV3`, `internlm` -> `Internlm`).
> If unsure, run `grep -i "<family>Model|<family>Config" loongforge/models/foundation/__init__.py`
> to find the actual symbol names.
>
> **`<family_us>` filename variant**: `.` in the family name must be replaced with `_` for file/directory matching
> (e.g., `qwen2.5` -> `qwen2_5`, `qwen3.5` -> `qwen3_5`).
> The underscore form is used uniformly in the filesystem and YAML (`.` has special meaning in Hydra/YAML).
> Derivation rule: `<family_us>` = `<family>.replace('.', '_')`.
>
> | Shared File | Model-Specific Code | Matching Method |
> |------------|--------------------| ------------|
> | `omni_models/fine_grained_callables.py` | Line 192: exclusion of `Qwen2VLRotaryEmbedding`, `Qwen3VLRotaryEmbedding` | grep `Qwen.*VLRotary` |
> | `data/mm_plugin.py` | `Qwen2VLPlugin` (line 235), `Qwen3VLPlugin` (line 347) subclasses | grep `Qwen.*VLPlugin` |
> | `data/kimi_k25_plugin.py` | Entire `KimiK25Plugin` class | filename match |
> | `data/dp_balance/dataloader/reconstruct.py` | `reconstruct_*_for_internvl` functions | grep `internvl|intern_vl` |
> | `data/dp_balance/dataloader/depack_and_pack.py` | `InternVLDataSample` class, `*_for_intern_vl` functions | grep `internvl|intern_vl|InternVL` |
> | `data/dp_balance/dataloader/data_balance.py` | Line 682: `model_family == "intern_vl"` branch | grep `intern_vl` |
> | `data/dp_balance/dataloader/warmup.py` | Line 192: `model_family == "intern_vl"` branch | grep `intern_vl` |

## Canonical Key Frequency Reference Table

> The following statistics are based on name_map analysis of all convert YAMLs in the repository.
> "Occurrence count" = how many **families** a key appears in (not YAML file count).
> Each row lists all keys with the **fewest occurrences** for that family (all keys at the same frequency are listed; all are deleted).
> Constant names correspond to definitions in `tools/convert_checkpoint/common/common_checkpoint.py`.
> This tool is for verification; **no need to consider the impact of deletion on other models**; delete directly according to the table.

### LLM Backbone

| Family | Least-Shared Canonical Key | Constant Name | Occurrence Count |
|--------|---------------------------|---------------|------------------|
| deepseek2 | `attention.q` | `ATTENTION_Q` | 1 |
| deepseek3 | `attention.indexer.k_norm` | `ATTENTION_INDEXER_K_NORM` | 1 |
| deepseek3 | `attention.indexer.weights_proj` | `ATTENTION_INDEXER_WEIGHTS_PROJ` | 1 |
| deepseek3 | `attention.indexer.wk` | `ATTENTION_INDEXER_WK` | 1 |
| deepseek3 | `attention.indexer.wq_b` | `ATTENTION_INDEXER_WQ_B` | 1 |
| kimi_k2 | `weight_scale_key` | (non-standard canonical key) | 1 |
| qwen3.5 | `moe.shared_expert_h_to_4h` | `MOE_SHARED_EXPERT_H_TO_4H` | 1 |
| qwen3.5 | `moe.shared_expert_4h_to_h` | `MOE_SHARED_EXPERT_4H_TO_H` | 1 |
| qwen3.5 | `mtp_moe.expert_h_to_4h` | `MTP_MOE_EXPERT_H_TO_4H` | 1 |
| qwen3.5 | `mtp_moe.expert_4h_to_h` | `MTP_MOE_EXPERT_4H_TO_H` | 1 |
| qwen3.5 | `mtp_moe.shared_expert_h_to_4h` | `MTP_MOE_SHARED_EXPERT_H_TO_4H` | 1 |
| qwen3.5 | `mtp_moe.shared_expert_4h_to_h` | `MTP_MOE_SHARED_EXPERT_4H_TO_H` | 1 |
| llama2 | `attention.rotary_emb.inv_freq` | `ATTENTION_ROTARY_EMB_INV_FREQ` | 2 |
| llama3 | `attention.rotary_emb.inv_freq` | `ATTENTION_ROTARY_EMB_INV_FREQ` | 2 |
| ernie4_5_vl | `mtp_shared_head_head` | `MTP_SHARED_HEAD_HEAD` | 2 |
| qwen3_next | `mtp_transformer` | `MTP_TRANSFORMER` | 2 |
| qwen3_next | `mixer_input_layernorm` | `MIXER_INPUT_LAYERNORM` | 2 |
| qwen3_next | `mixer_att.log` | `MIXER_ATT_LOG` | 2 |
| qwen3_next | `mixer_att.dt_bias` | `MIXER_ATT_DT` | 2 |
| qwen3_next | `mixer_att.conv1d` | `MIXER_ATT_CONV1D` | 2 |
| qwen3_next | `mixer_att.norm` | `MIXER_ATT_NORM` | 2 |
| qwen3_next | `mixer_att.out_proj` | `MIXER_ATT_OUT_PROJ` | 2 |
| qwen3_next | `mixer_att.in_proj_qkvz` | `MIXER_ATT_IN_PROJ_QKVZ` | 2 |
| qwen3_next | `mixer_att.in_proj_ba` | `MIXER_ATT_IN_PROJ_BA` | 2 |
| qwen3_next | `attention.query_gate_key_value` | `ATTENTION_QUERY_GATE_KEY_VALUE` | 2 |
| qwen3_next | `moe.shared_expert_gate` | `MOE_SHARED_EXPERT_GATE` | 2 |
| mimo | `mtp_name_prefix_for_layer` | `MTP_NAME_PREFIX_FOR_LAYER` | 4 |
| minimax | `attention.q_a_layernorm` | `ATTENTION_QNORM` | 4 |
| minimax | `attention.kv_a_layernorm` | `ATTENTION_KNORM` | 4 |
| qwen3 | `attention.q_a_layernorm` | `ATTENTION_QNORM` | 4 |
| qwen3 | `attention.kv_a_layernorm` | `ATTENTION_KNORM` | 4 |
| qwen | `attention.query_key_value` | `ATTENTION_QUERY_KEY_VALUE` | 9 |
| qwen2 | `attention.query_key_value` | `ATTENTION_QUERY_KEY_VALUE` | 9 |
| qwen2.5 | `attention.query_key_value` | `ATTENTION_QUERY_KEY_VALUE` | 9 |
| internlm2.5 | `attention.query_key_value` | `ATTENTION_QUERY_KEY_VALUE` | 9 |

### Vision Encoder (image_encoder/ckpt_convert/)

| Vision Encoder Family | Least-Shared Canonical Key | Constant Name | Occurrence Count |
|-----------------------|---------------------------|---------------|------------------|
| ernie4.5 | `final_layernorm` | `FINAL_LAYERNORM` | 1 |
| internvl | `post_attention_layerscale` | `POST_ATTENTION_LAYERSCALE` | 3 |
| internvl | `post_mlp_layerscale` | `POST_MLP_LAYERSCALE` | 3 |
| llava | `post_attention_layerscale` | `POST_ATTENTION_LAYERSCALE` | 3 |
| llava | `post_mlp_layerscale` | `POST_MLP_LAYERSCALE` | 3 |
| moon | `post_attention_layerscale` | `POST_ATTENTION_LAYERSCALE` | 3 |
| moon | `post_mlp_layerscale` | `POST_MLP_LAYERSCALE` | 3 |
| qwen / qwen2.5 / qwen3 / qwen3.5 | (all keys at same frequency, all 7) | -- | 7 |

> **Note**: image_projector YAMLs have no name_map-specific canonical keys (they only use `layer_prefix` and top-level adapter mapping);
> no need to clean up common_checkpoint.py constants when deleting projector YAMLs.

### Usage

When Step 5b is executed, look up this table based on the `--family` parameter:
1. Find the family in the LLM Backbone table, **delete all keys listed** along with their corresponding constants and code
2. If VLM, also find the corresponding vision encoder family in the Vision Encoder table and delete all its keys
3. For constant deletion: delete constant definition lines + references in `BASE_NAMES`/`MTP_NAMES` etc. lists + globally grep and delete all referencing code
4. Also process model-specific standalone files (adapter_<family>.py, <family>/ directory, BIG_MODEL_LIST)

## Backup Directory Structure

```
<backup_root>/<family>/<timestamp>/
+-- foundation/              # Complete copy of loongforge/models/foundation/<family>/
+-- encoder/                 # Complete copy of loongforge/models/encoder/<family>_vision_models/ (if exists)
+-- configs/                 # Complete copy of configs/models/<family>/ (including ckpt_convert/)
+-- module_configs/          # VLM module configuration YAML (VLM only)
|   +-- foundation/          # Complete copy of configs/models/<foundation_config_dir>/ (if not null)
|   +-- image_encoder/       # configs/models/image_encoder/<encoder_config_name>.yaml
|   +-- image_projector/     # configs/models/image_projector/<projector_config_name>.yaml
+-- convert_configs/         # Related YAMLs from image_encoder/ckpt_convert/ and image_projector/ckpt_convert/ (VLM applicable)
+-- convert_checkpoint/      # Model-specific code files deleted from tools/convert_checkpoint/ (if exists)
+-- examples/                # Complete copy of examples/<family>/
+-- trainers/                # loongforge/train/sft/sft_<family>.py (if exists)
|                             # loongforge/train/embodied/ or diffusion/ (if exists and specific to this family)
+-- omni_models/             # Related files from loongforge/models/omni_models/ (if exists)
+-- data/                    # loongforge/data/<family>/ directory and *<family>*.py files (if exists)
+-- patches/
|   +-- chat_template.patch  # Deleted lines from chat_template.py (unified diff format)
|   +-- foundation_init.patch # Deleted lines from foundation/__init__.py
|   +-- config_map.patch     # Deleted entries from config_map.py
|   +-- encoder_init.patch   # Deleted import + register lines from encoder/__init__.py
|   +-- constants.patch      # Deleted enum entries from constants.py
|   +-- train_init.patch     # Deleted import lines from train/__init__.py
|   +-- validators.patch     # Deleted validation code blocks from validators.py
|   +-- convert_checkpoint.patch # Deleted constants and code lines from common_checkpoint.py / model.py
|   +-- shared_files.patch   # Deleted model-specific code from shared files: omni_models/, mm_plugin.py, dp_balance/, etc.
+-- manifest.json            # Backup metadata
```

### manifest.json Format

```json
{
  "family": "qwen3",
  "timestamp": "2026-04-13T10:00:00",
  "git_commit_before": "abc1234",
  "backup_root": "~/.omni_backup",
  "backed_up_dirs": ["foundation/", "configs/", "examples/"],
  "module_configs_backed_up": {
    "foundation_config_dir": null,
    "encoder_config_file": null,
    "projector_config_file": null
  },
  "backed_up_patches": ["chat_template.patch", "foundation_init.patch", "config_map.patch"],
  "encoder_backed_up": false,
  "trainer_files_backed_up": [],
  "omni_models_files_backed_up": [],
  "data_files_backed_up": [],
  "convert_configs_backed_up": [],
  "convert_checkpoint_files_backed_up": [],
  "convert_checkpoint_patches": [],
  "shared_files_patches": [],
  "expected_residuals": [],
  "unexpected_residuals": [],
  "delete_commit": "def5678"
}
```

## Execution Flow

```
1. Pre-check + model type determination
   - family exists in config_map or constants.py
   - backup_root path is writable (create if not exists)
   - git working directory is clean (no uncommitted changes), otherwise ABORT
   - Derive <family_us> = <family>.replace('.', '_')
   - Determine model type:
     Search for <family> in constants.py:
     - Exists in VisionLanguageModelFamilies -> VLM
     - Exists in LanguageModelFamilies -> LLM

2. Read network construction YAML, extract model information
   - Read any one YAML under configs/models/<family>/
   - Extract model.model_type -> <model_type> (e.g., intern_vl, qwen2_5_vl, qwen)
   - Search for enum with value <model_type> in constants.py -> <MODEL_TYPE_ENUM> (e.g., INTERN_VL = "intern_vl")
   - Derive <CodePrefix>: CamelCase form of <MODEL_TYPE_ENUM> (e.g., INTERN_VL -> InternVL)
     If unsure, run grep -i "<model_type>" loongforge/models/encoder/__init__.py to find actual class names

3. Module directory resolution -- Foundation
   - If loongforge/models/foundation/<family>/ exists -> <foundation_dir> = <family>
   - If not, parse Hydra defaults @model.foundation reference in network construction YAML
     -> <foundation_dir> = referenced target family name
   - If still not found -> <foundation_dir> = null
   - (VLM only) Extract <foundation_config_dir>:
     From the directory portion of the @model.foundation value in Hydra defaults
     (e.g., @model.foundation: internlm2_5/internlm2_5_7b -> <foundation_config_dir> = internlm2_5)
     If <foundation_config_dir> == <family_us> (i.e., main configs directory already covers it), set to null to avoid duplication
     If no @model.foundation reference -> <foundation_config_dir> = null

4. Module directory resolution -- Encoder (VLM only)
   - If loongforge/models/encoder/<family>_vision_models/ exists -> <encoder_dir> = <family>_vision_models
   - If not, parse Hydra defaults from network construction YAML:
     a. Find @model.image_encoder: <encoder_config_name>
     b. Read configs/models/image_encoder/<encoder_config_name>.yaml
     c. Extract encoder directory name from _target_ field's Python module path
        (e.g., _target_: loongforge.models.encoder.internvl_vision_models.internvl_config.InternVisionConfig
         -> <encoder_dir> = internvl_vision_models)
   - If still not found -> <encoder_dir> = null
   - Record @model.image_encoder config name -> <encoder_config_name> (for locating module YAML and finding convert YAML)
   - Record @model.image_projector config name -> <projector_config_name> (for locating module YAML and finding convert YAML)

5. Derive <code_prefix> (code file grep anchor)
   - VLM: remove _vision_models suffix from <encoder_dir> (e.g., internvl_vision_models -> internvl)
     If <encoder_dir> = null, use <model_type> with underscores removed (e.g., qwen2_5_vl -> qwen2vl)
   - LLM: <code_prefix> = <family>, and <code_prefix_us> = <family_us>
   - <code_prefix> is used for all subsequent code greps (trainer, adapter, data, shared files, etc.)
     <family> is only used for locating configs/models/<family>/ and examples/<family>/

6. If --dry-run: print list of files to be deleted, exit

7. Create <backup_root>/<family>/<timestamp>/

8. Copy directories
   - cp -r loongforge/models/foundation/<foundation_dir>/ -> backup/foundation/ (if <foundation_dir> not null)
   - If <encoder_dir> not null: cp -r loongforge/models/encoder/<encoder_dir>/ -> backup/encoder/
   - cp -r configs/models/<family>/              -> backup/configs/
   - (VLM only) Module configuration YAML copy:
     - If <foundation_config_dir> not null:
       cp -r configs/models/<foundation_config_dir>/ -> backup/module_configs/foundation/
     - If <encoder_config_name> not null:
       cp configs/models/image_encoder/<encoder_config_name>.yaml -> backup/module_configs/image_encoder/
     - If <projector_config_name> not null:
       cp configs/models/image_projector/<projector_config_name>.yaml -> backup/module_configs/image_projector/
   - cp -r examples/<family>/                    -> backup/examples/
   - If loongforge/train/sft/sft_<code_prefix>.py exists: cp -> backup/trainers/
   - If loongforge/train/embodied/ exists and is specific to this family: cp -r -> backup/trainers/embodied/
   - If loongforge/train/diffusion/ exists and is specific to this family: cp -r -> backup/trainers/diffusion/
   - If files referencing <code_prefix> exist in loongforge/models/omni_models/: cp each file to backup/omni_models/
   - If directories containing <code_prefix> exist under loongforge/data/: cp -r -> backup/data/
   - If *<code_prefix>*.py files exist under loongforge/data/: cp each file to backup/data/
   - LLM additional: if *<family_us>*.py files exist under loongforge/data/ (when different from <code_prefix>): cp each file to backup/data/
   - If YAMLs containing <code_prefix> exist in configs/models/image_encoder/ckpt_convert/ (only when <encoder_dir> not null):
     cp each file to backup/convert_configs/
   - If YAMLs containing <projector_config_name> or <code_prefix> exist in configs/models/image_projector/ckpt_convert/ (only when <encoder_dir> not null):
     cp each file to backup/convert_configs/
   - If tools/convert_checkpoint/module_convertor/adapter_<code_prefix>.py exists: cp -> backup/convert_checkpoint/
   - If tools/convert_checkpoint/<code_prefix>/ directory exists: cp -r -> backup/convert_checkpoint/<code_prefix>/

9. Extract patch files (run before deletion, recording content to be removed)
   - chat_template.py: grep -n "name=\"<family>\"" extract full _register_chat_template(...) block
   - foundation/__init__.py: grep -n "<FoundationDir>Model|<FoundationDir>Config|AutoModel.register"
     (<FoundationDir> is CamelCase of <foundation_dir>, e.g., internlm2.5 -> Internlm2_5)
     Write matching lines to backup/patches/foundation_init.patch
   - config_map.py: grep -n "<family>" | grep -v "\-vl"
     Write matching lines to backup/patches/config_map.patch (exclude lines containing -vl to avoid accidentally deleting other family entries)
   - encoder/__init__.py (VLM only):
     grep -n "<CodePrefix>Vision|<CodePrefix>Adapter|<CodePrefix>Config|AutoModel.register"
     Write matching lines to backup/patches/encoder_init.patch
   - constants.py: grep -n "<MODEL_TYPE_ENUM>|<family>"
     Write matching enum entries to backup/patches/constants.patch
   - train/__init__.py: grep -n "<code_prefix>"
     Write matching import lines to backup/patches/train_init.patch
   - validators.py: grep -n "<code_prefix>|<family>"
     Write matching validation code blocks (including complete if/conditional blocks) to backup/patches/validators.patch
   - Model-specific code in shared files (see "Model-Specific Code in Shared Files" table):
     Grep using matching method from table and extract -> backup/patches/shared_files.patch
   - Note: match results for each file must be unique (see error handling)

10. Clean up convert_checkpoint model-specific code
    - Look up "Canonical Key Frequency Reference Table" LLM Backbone section, get all keys with fewest occurrences for this family
    - For **each key** listed in the table:
      a. Locate corresponding constant definition line in common_checkpoint.py
      b. Check if the constant appears in BASE_NAMES, MTP_NAMES, etc. lists; if so, remove synchronously
      c. Globally grep the constant name in tools/convert_checkpoint/, locate all reference positions
      d. Write all related code lines to backup/patches/convert_checkpoint.patch
      e. Delete these code lines from source files (Edit tool)
    - Process model-specific standalone files (if exists):
      - tools/convert_checkpoint/module_convertor/adapter_<code_prefix>.py -> full file backup, then git rm
      - tools/convert_checkpoint/<code_prefix>/ directory -> full directory backup, then git rm
      - Entries containing <code_prefix> or <family> in BIG_MODEL_LIST in tools/convert_checkpoint/module_convertor/model.py
    - VLM vision encoder: look up Vision Encoder section in reference table, same cleanup process
    - VLM projector: no need to clean up common_checkpoint.py constants

11. Write manifest.json (delete_commit field is empty at this point)

12. git rm -r delete directories
    - If <foundation_dir> not null: git rm -r loongforge/models/foundation/<foundation_dir>/
    - If <encoder_dir> not null: git rm -r loongforge/models/encoder/<encoder_dir>/
    - git rm -r configs/models/<family>/
    - (VLM only) Delete module configuration YAMLs:
      - If <foundation_config_dir> not null: git rm -r configs/models/<foundation_config_dir>/
      - If <encoder_config_name> not null: git rm configs/models/image_encoder/<encoder_config_name>.yaml
      - If <projector_config_name> not null: git rm configs/models/image_projector/<projector_config_name>.yaml
    - git rm -r examples/<family>/
    - If sft_<code_prefix>.py exists: git rm
    - If embodied/diffusion is specific to this family: git rm -r
    - If related files exist in omni_models: git rm each file
    - If directories containing <code_prefix> exist under data/: git rm -r
    - If *<code_prefix>*.py or *<family_us>*.py files exist under data/: git rm each file
    - If YAMLs containing <code_prefix> exist in image_encoder/ckpt_convert/ (only when <encoder_dir> not null): git rm each file
    - If related YAMLs exist in image_projector/ckpt_convert/ (only when <encoder_dir> not null): git rm each file
    - If adapter_<code_prefix>.py exists: git rm
    - If convert_checkpoint/<code_prefix>/ directory exists: git rm -r
    - If data/kimi_k25_plugin.py exists and is related: git rm

13. Precisely delete registration code from files (Edit tool, without breaking other code)
    - chat_template.py: delete full _register_chat_template(...) block containing name="<family>"
    - foundation/__init__.py: delete import + register lines for <FoundationDir>Model, <FoundationDir>Config
    - config_map.py: delete entry lines containing <family> (exclude lines containing -vl)
    - encoder/__init__.py (VLM only): delete lines related to <CodePrefix>Vision / <CodePrefix>Adapter / <CodePrefix>Config
    - constants.py: delete <MODEL_TYPE_ENUM> enum entry
    - train/__init__.py: delete import lines containing <code_prefix>
    - validators.py: delete complete validation code blocks containing <code_prefix> or <family>
    - Model-specific code in shared files (per "Model-Specific Code in Shared Files" table):
      Locate and delete using matching method from table
    - After deletion complete: git add all modified files

14. Residual scan (verify deletion completeness)
    - Scan scope: loongforge/ and tools/convert_checkpoint/ (exclude .git, __pycache__, backup_root)

    Scan category A -- Code matching prefix related identifiers:
      grep -rn "<code_prefix>" loongforge/ tools/convert_checkpoint/ --include="*.py" --include="*.yaml"
      grep -rn "<CodePrefix>" loongforge/ --include="*.py"
      grep -rn "<MODEL_TYPE_ENUM>" loongforge/ --include="*.py"
      Coverage: trainer, adapter, data, constants, __init__.py import/register, shared files, etc. all code artifacts

    Scan category B -- Actual directory names (foundation/encoder resolved directory names):
      grep -rn "<foundation_dir>" loongforge/ --include="*.py" --include="*.yaml"
      grep -rn "<encoder_dir>" loongforge/ --include="*.py" --include="*.yaml"
      Only execute when <foundation_dir> or <encoder_dir> differs from <code_prefix>

    Scan category C -- Canonical key constants deleted in Step 10:
      For each constant name for this family in the frequency table: grep -rn "<CONSTANT_NAME>" tools/convert_checkpoint/ --include="*.py"

    Scan category D -- Model-specific code identifiers in shared files (per "Model-Specific Code in Shared Files" table):
      If this family has entries in the shared files table, grep using the matching method from the table

    Scan category E -- Full deletion completeness item-by-item verification (item-by-item assertion, not dependent on grep keywords):
      Each item below checks "whether it still exists"; if it exists, it is reported as an unexpected residual.
      Verify item by item per the backup scope table, ensuring each category of deletion from Steps 10/12/13 was actually executed.

      E1. Directory-level deletion (corresponding to Step 12 git rm -r):
        - If <foundation_dir> not null: loongforge/models/foundation/<foundation_dir>/ should not exist
        - If <encoder_dir> not null: loongforge/models/encoder/<encoder_dir>/ should not exist
        - configs/models/<family>/ should not exist (including ckpt_convert/ subdirectory)
        - (VLM only) Module configuration YAML verification:
          - If <foundation_config_dir> not null: configs/models/<foundation_config_dir>/ should not exist
          - If <encoder_config_name> not null: configs/models/image_encoder/<encoder_config_name>.yaml should not exist
          - If <projector_config_name> not null: configs/models/image_projector/<projector_config_name>.yaml should not exist
        - examples/<family>/ should not exist
        - If data/<code_prefix>/ directory was backed up in Step 8: loongforge/data/<code_prefix>/ should not exist
        - If train/embodied/ was backed up in Step 8: loongforge/train/embodied/ should not exist
        - If train/diffusion/ was backed up in Step 8: loongforge/train/diffusion/ should not exist
        - If convert_checkpoint/<code_prefix>/ was backed up in Step 8:
          tools/convert_checkpoint/<code_prefix>/ should not exist

      E2. File-level deletion (corresponding to Step 12 per-file git rm):
        - If sft_<code_prefix>.py was backed up in Step 8:
          loongforge/train/sft/sft_<code_prefix>.py should not exist
        - If data/*<code_prefix>*.py files were backed up in Step 8:
          Check each backed up .py file should not exist
        - If LLM and data/*<family_us>*.py files were backed up in Step 8 (when different from <code_prefix>):
          Check each backed up .py file should not exist
        - If omni_models/ related files were backed up in Step 8:
          Check each backed up file should not exist
        - If data/kimi_k25_plugin.py was backed up in Step 8: this file should not exist
        - If VLM and image_encoder/ckpt_convert/ YAMLs were backed up in Step 8:
          Check each backed up YAML should not exist in configs/models/image_encoder/ckpt_convert/
        - If VLM and image_projector/ckpt_convert/ YAMLs were backed up in Step 8:
          Check each backed up YAML should not exist in configs/models/image_projector/ckpt_convert/
        - If adapter_<code_prefix>.py was backed up in Step 8:
          tools/convert_checkpoint/module_convertor/adapter_<code_prefix>.py should not exist

      E3. Registration code line deletion (corresponding to Step 13 Edit deletion):
        - chat_template.py: read file, search for name="<family>", no match should exist
        - foundation/__init__.py: search for <FoundationDir>Model or <FoundationDir>Config, no match should exist
        - config_map.py: search for <family> (exclude lines containing -vl), no match should exist
        - constants.py: search for <MODEL_TYPE_ENUM>, no match should exist
        - train/__init__.py: search for <code_prefix>, no match should exist
        - validators.py: search for <code_prefix> or <family>, no match should exist (except whitelist)
        - If VLM: search encoder/__init__.py for <CodePrefix>Vision or <CodePrefix>Adapter
          or <CodePrefix>Config, no match should exist

      E4. Model-specific code in shared files (corresponding to Step 13 deletion per shared files table):
        - If this family has entries in the "Model-Specific Code in Shared Files" table:
          For each entry, read the target file using the matching method from the table, check if model-specific code blocks have been deleted
          Example: omni_models/fine_grained_callables.py should not contain <CodePrefix>VLRotary references
          Example: data/mm_plugin.py should not contain <CodePrefix>VLPlugin subclass definitions
          Example: data/dp_balance/ files should not contain <code_prefix> related functions/branches

      E5. convert_checkpoint core conversion code (corresponding to Step 10):
        - BIG_MODEL_LIST: read tools/convert_checkpoint/module_convertor/model.py,
          parse BIG_MODEL_LIST contents, should not contain entries with <code_prefix> or <family> or <family_us>
        - Canonical key constants: for each constant name for this family in the frequency reference table,
          check one by one that common_checkpoint.py should not have assignment lines for that constant (`<CONSTANT_NAME> = "..."` form)
        - Category list references: check that BASE_NAMES, MTP_NAMES, etc. lists in common_checkpoint.py
          should not contain the above constant names
        - Conversion code branches:
          No if/elif branches referencing the above constants should exist in huggingface/huggingface_base.py
          No if/elif branches referencing the above constants should exist in mcore/mcore_base.py
          No entries for the above constants should exist in TENSOR_PARALLEL_DIM dict in mcore/mcore_base.py

      Note: Any failure in E1-E5 is reported as an unexpected residual, grouped by category for output

    - Whitelist filtering (the following are expected residuals, not counted as issues):
      - Mentions in comments (lines starting with #)
      - Mentions in documentation files such as CLAUDE.md, SKILL.md
      - Enum listings in generic fallback/else branches
      - Code for other families with the same model_type (e.g., internvl3.5 also uses INTERN_VL, not deleted)
    - Categorize filtered residual results into two groups:
      - **Expected residuals**: written to manifest.json expected_residuals
      - **Unexpected residuals**: written to manifest.json unexpected_residuals, reported grouped by scan category
    - If unexpected residuals exist: ASK_USER whether to continue committing or handle manually
    - If no unexpected residuals: print "Residual scan passed, no unexpected residuals"

15. Unless --no-commit:
    git commit -m "chore: backup and remove <family> for /loongforge:adapt validation"

16. Update delete_commit field in manifest.json
    - manifest.json is located at <backup_root>/<family>/<timestamp>/ (outside repo)
    - Run git rev-parse HEAD to get commit hash
    - Replace delete_commit in manifest.json with actual hash

17. Output summary: backup path, number of deleted files, commit hash, residual scan results
```

## Error Handling

| Situation | Handling |
|-----------|----------|
| Family directory does not exist | ABORT: output "family <name> not found in loongforge/models/foundation/" |
| backup_root is not writable | ABORT: output permission error message |
| Git working directory has uncommitted changes | ABORT: require user to commit or stash first |
| Patch extraction results in non-unique deletion lines (multiple matches) | HUMAN_NEEDED: list all match locations for human confirmation |
| Residual scan finds unexpected residuals | ASK_USER: list residual locations for human confirmation on whether to continue committing or handle first |
| --dry-run mode | Only output file list, do not execute any modifications |
