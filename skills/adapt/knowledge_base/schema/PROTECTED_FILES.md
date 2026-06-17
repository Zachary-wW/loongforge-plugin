# General File Protection List

> This file defines the general infrastructure files that are **prohibited from modification** and **append only** during model adaptation.
> When adapting a specific model, these files must not be modified to make that model run successfully, in order to avoid affecting other already-adapted models.

---

## Category Descriptions

| Category | Meaning | Operation During Adaptation |
|----------|---------|----------------------------|
| **Prohibited from Modification** | Pure general infrastructure with no model-specific logic; no changes allowed during adaptation | Read-only |
| **Append Only (Entry Level)** | Framework code must not be modified; only append new entries (enum values, mapping items, registration lines) at designated locations | Append at the end of the file or designated area; do not modify existing content |
| **Append Only (Function/Plugin Level)** | Files already contain model-specific functions, classes, or branches; appending a new model's same-type implementation is allowed | Append new functions/classes/branches/mapping entries; do not modify existing implementations |
| **Conditional Modify (Framework Bugfix Only)** | Existing framework behavior is incorrect or incomplete for a generally valid feature, not just one model's convenience | Allowed only when the user explicitly requested a framework bugfix or approved a `modify_existing` / `modify_megatron_general` / `insert_hook` plan with blast radius and tests |

---

## Conditional Modify Protocol

Normal model adaptation should use extension: new files, new branches, new mappings, and layer_spec/config wiring. Shared infrastructure, including AIAK-Megatron, is not read-only; however, changes there must be justified as general correctness fixes or default-compatible extension points.

When Phase 1/2 discovers that existing framework logic must change, classify it as one of:

- `override_in_omni`: model-specific behavior; implement in Omni via layer_spec/config/subclass/module instead of changing shared Megatron behavior.
- `modify_megatron_general`: shared Megatron behavior is incomplete or incorrect for a generally valid feature; a Megatron change is appropriate with compatibility tests.
- `insert_hook`: a default-no-op extension point can keep shared behavior stable while allowing model-specific handling.
- `human_needed`: the scope or blast radius is too large or unclear.

Required evidence before a conditional modify:

1. `model_spec.behavior_modifications` entry or validation failure proving the behavior gap.
2. Exact file/helper/branch that must change or be overridden.
3. Why config fields, wrapper classes, submodule replacement, or append-only branches cannot express the behavior.
4. Blast radius: which existing models/features may be affected.
5. Validation tests, including targeted behavior tests when random initialization cannot expose the bug.
6. For `modify_megatron_general`: why the behavior is broadly correct, not model-specific.

If explicit framework-bugfix authorization is absent, return `human_needed` with `failure_gate="protected_file_change_required"` and include the evidence above.

---

## I. Files Prohibited from Modification

### Training Infrastructure (`loongforge/train/`)

| File | Description |
|------|-------------|
| `loongforge/train.py` | Training main entry point |
| `loongforge/train/megatron_trainer.py` | General MegatronTrainer wrapper |
| `loongforge/train/checkpointing.py` | Distributed checkpoint save/load |
| `loongforge/train/trainer_builder.py` | Trainer registration/dispatch mechanism |
| `loongforge/train/training_utils.py` | Core training loop |
| `loongforge/train/initialize.py` | Training initialization (distributed, random seed) |
| `loongforge/train/arguments.py` | Training argument definitions |
| `loongforge/train/pretrain/pretrain_llm.py` | LLM pretrain entry point |
| `loongforge/train/sft/sft_llm.py` | LLM SFT entry point |
| `loongforge/train/sft/sft_vlm.py` | VLM SFT entry point |

### Model Framework Layer (`loongforge/models/`)

| File | Description |
|------|-------------|
| `loongforge/models/factory.py` | Model registration factory |
| `loongforge/models/dispatch.py` | Hardware abstraction dispatch (GPU/XPU) |
| `loongforge/models/utils.py` | General model utility functions |
| `loongforge/models/common/base_model_config.py` | Base configuration dataclass |
| `loongforge/models/common/base_model_mixins.py` | Model abstract base class |
| `loongforge/models/common/vlm_model_config.py` | VLM general configuration container |
| `loongforge/models/common/peft/` (entire directory) | General LoRA/PEFT implementation |
| `loongforge/models/common/local_layers/` (entire directory) | General local attention, LayerNorm |
| `loongforge/models/common/experimental_attention_variant/` (entire directory) | DSA/MLA general operators |
| `loongforge/models/foundation/llm_model_provider.py` | LLM provider factory |
| `loongforge/models/foundation/language_transformer_block.py` | General language Transformer block |
| `loongforge/models/encoder/vision_transformer_block.py` | General vision Transformer block |

### Multi-modal Composition Framework (`loongforge/models/omni_models/`)

| File | Description |
|------|-------------|
| `loongforge/models/omni_models/omni_combination_model.py` | Multi-modal model composition framework |
| `loongforge/models/omni_models/omni_decoder_model.py` | General Decoder model |
| `loongforge/models/omni_models/omni_encoder_model.py` | General Encoder model |
| `loongforge/models/omni_models/omni_model_provider.py` | Multi-modal model provider |
| `loongforge/models/omni_models/fine_grained_callables.py` | Fine-grained model components |
| `loongforge/models/omni_models/model_chunk_schedule_plan.py` | Model chunk scheduling |
| `loongforge/models/omni_models/utils.py` | Composition model utility functions |

### Global Utilities (`loongforge/utils/`)

| File | Description |
|------|-------------|
| `loongforge/utils/global_vars.py` | Global state management |
| `loongforge/utils/utils.py` | General utility functions |
| `loongforge/utils/xpu_init.py` | XPU initialization |

### Data Pipeline (`loongforge/data/`)

| File | Description |
|------|-------------|
| `loongforge/data/base_dataset_config.py` | Base dataset configuration |
| `loongforge/data/hf_dataset.py` | HuggingFace dataset abstract base class |
| `loongforge/data/blended_hf_dataset_config.py` | Blended dataset configuration |
| `loongforge/data/blended_hf_dataset_builder.py` | Blended dataset builder |
| `loongforge/data/sft_dataset.py` | General SFT dataset |
| `loongforge/data/sft_format_utils.py` | Data format conversion utilities |
| `loongforge/data/sft_supervised_utils.py` | SFT data processing utilities |
| `loongforge/data/sft_data_collator.py` | SFT data collator |
| `loongforge/data/dp_balance/` (entire directory) | Data-parallel load balancing |
| `loongforge/data/multimodal/base/` (entire directory) | Multi-modal data base classes |
| `loongforge/data/multimodal/dataloader_provider.py` | Data loader provider |
| `loongforge/data/multimodal/vlm_task_encoder.py` | General VLM task encoder |

### Tokenizer (`loongforge/tokenizer/`)

| File | Description |
|------|-------------|
| `loongforge/tokenizer/tokenization_hf.py` | HuggingFace Tokenizer wrapper |
| `loongforge/tokenizer/defaults.py` | Default configuration |

### AIAK-Megatron Shared Core (`<megatron_path>/megatron/`)

> AIAK-Megatron is shared by all models. It may be changed only for general correctness fixes or default-compatible extension points. If the behavior is model-specific or could affect other models, prefer Omni-side `override_in_omni`.

| File | Description |
|------|-------------|
| `core/transformer/mlp.py` | Dense MLP |
| `core/transformer/moe/shared_experts.py` | Shared expert MLP |
| `core/transformer/moe/experts.py` | Grouped/Sequential expert MLP |
| `core/transformer/moe/moe_layer.py` | MoE layer assembly |
| `core/transformer/moe/router.py` | Expert router |
| `core/fusions/fused_bias_swiglu.py` | Fused SwiGLU kernel |
| `core/transformer/hyper_connection.py` | Hyper connection module |
| `core/transformer/transformer_config.py` | Transformer config dataclass |
| `core/transformer/transformer_layer.py` | Transformer layer |
| `core/transformer/transformer_block.py` | Transformer block |
| `core/transformer/attention.py` | Self/Cross attention |
| `core/transformer/multi_latent_attention.py` | MLA attention |
| `core/models/gpt/gpt_layer_specs.py` | GPT layer spec |
| `core/models/gpt/experimental_attention_variant_module_specs.py` | Attention variant specs |

### Weight Conversion Framework (`tools/convert_checkpoint/`)

| File | Description |
|------|-------------|
| `common/abstact_config.py` | Configuration abstract base class |
| `common/abstact_checkpoint.py` | Checkpoint abstract base class |
| `common/common_config.py` | General configuration management |
| `utils/utils.py` | General tensor operations, FP8 quantization functions |
| `utils/ckpt_util.py` | Checkpoint I/O helpers |
| `huggingface/huggingface_checkpoint.py` | HF checkpoint load/save |
| `huggingface/huggingface_config.py` | HF configuration processing |
| `huggingface/merge_huggingface.py` | Multi-shard HF checkpoint merging |
| `mcore/mcore_checkpoint.py` | Megatron Core checkpoint load/save |
| `mcore/mcore_config.py` | Megatron Core configuration processing |
| `mcore/merge_megatron.py` | Distributed Megatron checkpoint merging |
| `mcore/merge_megatron_expert.py` | MoE expert shard merging |
| `key_mappings/to_omni_key.py` | General key prefix mapping transformation |
| `key_mappings/to_vanilla_key.py` | General key reverse mapping |

### Distributed Checkpoint (`tools/dist_checkpoint/`)

| File | Description |
|------|-------------|
| `config/parallel_config.py` | Parallel topology configuration |
| `core/parser.py` | Argument parsing |
| `core/topo_sharder.py` | parallel_state initialization |
| `core/tp_gather.py` | TP rank state_dict gathering |
| `utils/utils.py` | Distributed checkpoint utilities |
| `utils/comparison_utils.py` | Checkpoint comparison and verification |
| `checkpoint/hf_checkpoint_loader.py` | Distributed HF checkpoint loading |
| `checkpoint/hf_checkpoint_saver.py` | Distributed HF checkpoint saving |
| `checkpoint/hf_checkpoint_converter.py` | Distributed HF checkpoint conversion orchestration |
| `checkpoint/hf_roundtrip_test.py` | Roundtrip test framework |

### Data Preprocessing (`tools/data_preprocess/`)

| File | Description |
|------|-------------|
| `llm/preprocess_pretrain_data.py` | LLM pretrain data tokenization |
| `llm/preprocess_sft_data.py` | SFT dataset preparation |
| `vlm/convert_to_webdataset.py` | WebDataset format conversion |
| `vlm/offline_packing/` (entire directory) | Offline data packing pipeline |

### Custom Operators (`ops/`)

| Directory | Description |
|-----------|-------------|
| `ops/flex_eager/` | Flexible eager attention |
| `ops/sparse_mla_fwd/` | Sparse MLA forward kernel |
| `ops/sparse_mla_bwd/` | Sparse MLA backward kernel |
| `ops/lightning_indexer_bwd/` | Lightning Indexer backward kernel |

### Upstream Patches (`patches/`)

| File | Description |
|------|-------------|
| `patches/apply_patches.sh` | Patch application script |
| `patches/Megatron-LM_v0.15.0/` (entire directory) | Megatron-LM patches |
| `patches/TransformerEngine_v2.9/` (entire directory) | TransformerEngine patches |

### Test Infrastructure (`tests/`)

| File | Description |
|------|-------------|
| `tests/common/` (entire directory) | General shell utilities, metrics collection |
| `tests/tasks/` (entire directory) | Test base classes, check orchestration |
| `tests/tools/` (entire directory) | Argument parsing, logging, configuration management |
| `tests/utils/` (entire directory) | Constants, state restoration |
| `tests/main_start.sh` | Test main entry point |
| `tests/main.py` | Python test entry point |
| `tests/download_datasets.sh` | Dataset download |
| `tests/prepare_env.sh` | Environment preparation |

---

## II. Append-Only Files

### 2.1 Entry-Level Append

> The framework code in these files must not be modified; only append new entries at **designated locations**. Do not modify or delete existing entries.

| File | Allowed Append Operation | Append Location |
|------|------------------------|-----------------|
| `loongforge/utils/constants.py` | Append new family constant at the end of `LanguageModelFamilies` / `VisionLanguageModelFamilies` etc. | End of the corresponding enum class |
| `loongforge/utils/config_map.py` | Append new model name -> config path mapping in `MODEL_CONFIG_REGISTRY` | End of the dictionary |
| `loongforge/models/foundation/__init__.py` | Append `from .<family> import ...` and `AutoModel.register(...)` | End of the file (see FILE_STRUCTURE.md) |
| `loongforge/models/encoder/__init__.py` | For VLM, append encoder import and register | End of import section + end of register section |
| `loongforge/data/chat_template.py` | Append `_register_chat_template(name="<family>", ...)` | End of the file |
| `tools/convert_checkpoint/common/common_checkpoint.py` | Add key constants for new layer structures, add to corresponding classification lists (`BASE_NAMES` etc.) | Constant definition area + end of lists |
| `tools/convert_checkpoint/mcore/mcore_base.py` | Register new parameters in `TENSOR_PARALLEL_DIM` | End of the dictionary |
| `tools/convert_checkpoint/key_mappings/key_reverser.py` | Add reverse mapping for new VLM components | `reverse_mapping` dictionary |
| `tools/convert_checkpoint/key_mappings/key_reverser_expert.py` | Same as above | `reverse_mapping` dictionary |
| `tests/tasks/base_task.py` | Append new model metadata in `HF_CHECK_MODEL_MAPPING` | End of the dictionary |

### 2.2 Function/Plugin-Level Append

> These files already contain model-specific functions, classes, or branches. When adapting a new model, **appending same-type new implementations** (new functions, new plugin classes, new mapping entries, new `elif` branches) is allowed, but **existing implementations must not be modified**.

| File | Existing Model-Specific Content | Allowed Append Operation | Append Location |
|------|-------------------------------|------------------------|-----------------|
| `loongforge/train/get_loss_func.py` | `loss_func_internvl()` | Append new model's loss function (e.g., `loss_func_<family>()`) | End of the file |
| `loongforge/train/get_position_idx_func.py` | `get_rope_index_qwen3vl()`, `get_rope_index_internvl()`, `get_mrope_index()` | Append new model's position encoding function (e.g., `get_rope_index_<family>()`) | End of the file |
| `loongforge/train/parser.py` | InternVL/Qwen3VL entries in `POSITION_IDX_FUNC_MAP`, `LOSS_FUNC_MAP` | Append new model's mapping entries in `POSITION_IDX_FUNC_MAP` / `LOSS_FUNC_MAP`; append corresponding imports | End of mapping dictionaries + import section |
| `loongforge/train/validators.py` | `if args.model_family == QWEN3_VL` version validation | Append new model's argument validation branch (`elif`) | After existing validation branches |
| `loongforge/train/pretrain/pretrain_vlm.py` | Qwen3VL token ID default values | Append new model's token ID handling logic | Corresponding logic area |
| `loongforge/data/mm_plugin.py` | `Qwen2VLPlugin`, `Qwen3VLPlugin` classes | Append new model's `MMPlugin` subclass (e.g., `<Family>Plugin`) | End of the file |
| `loongforge/tokenizer/tokenizer.py` | `if args.model_family == QWEN` EOS handling | Append new model's tokenizer special handling branch (`elif`) | After existing branches |

---

## III. Phase 2 Modifiable `tools/convert_checkpoint/` Files

> Phase 2 Step 2 (Tier 1/2) allows modifying the following files, but **only by appending new branches or new converters**; existing branch logic must not be modified.

| File | Tier | Allowed Modification |
|------|------|---------------------|
| `common/common_checkpoint.py` | Tier 1 | Add new constants, add to classification lists |
| `mcore/mcore_base.py` | Tier 1 | Add new entries in `TENSOR_PARALLEL_DIM` |
| `huggingface/huggingface_base.py` | Tier 2 | Append new branches at the end of `hf_to_common()` / `common_to_hf()` |
| `mcore/mcore_base.py` | Tier 2 | Append new branches at the end of corresponding methods |
| `huggingface/util/hf_<name>_converter.py` | Tier 2 | **Create new** file (do not modify existing converters) |
| `mcore/util/mcore_<name>_converter.py` | Tier 2 | **Create new** file (do not modify existing converters) |
| `utils/config_utils.py` | Tier 1/2 | If new constants need to be parsed during config loading, append imports |

**Strictly prohibited**: Modifying existing logic in existing converters (e.g., `hf_attn_converter.py`, `hf_mixer_attn_converter.py`). New models must be supported by creating new converters or adding new branches.

---

## IV. Violation Criteria

The following situations during adaptation are considered violations and must be rolled back immediately:

1. **Modifying any line of code in files marked "Prohibited from Modification"**
2. **Modifying existing content in "Append Only" files** (including reordering, modifying values of existing entries, deleting existing entries)
3. **Modifying the logic of existing branches in Phase 2 modifiable files** (e.g., modifying existing `if/elif` conditions, changing algorithms in existing converters) unless an explicitly approved framework-bugfix plan classified it as `modify_existing` or `insert_hook`
4. **Modifying test baselines of existing models to make a new model pass tests**

> **Core Principle**: New model adaptation must be achieved through **extension** (new files, new branches, new entries), not through **modification** of existing logic.
> If you find that modifying general files is necessary to support a new model, this indicates that the framework design needs to evolve; submit `HUMAN_NEEDED` for human evaluation unless the user has explicitly authorized a framework bugfix with tests.
