# LoongForge Linter Rules Reference

Version: v3.0
Purpose: After the Agent generates code, perform a static check on each generated file according to the rules in this document. Passing requires 0 errors.
Check Method: Agent manually verifies each item (the executable script `loongforge_rules.py` has been removed; rules are maintained as documentation).

## Rules Quick Reference Table

| ID | Applicable Files | Check Content | Return Code |
|----|----------------|---------------|-------------|
| R001 | `*_config.py` | Config must inherit `BaseModelConfig` / `BaseModelMLAConfig` / `BaseModelStditConfig` | ERROR |
| R002 | `*_layer_spec.py` | Prohibited: direct `import transformer_engine.*`; use `multiacc_modules` instead | ERROR |
| R003 | `*_layer_spec.py` | Required: must include `from loongforge.models.dispatch import multiacc_modules` | ERROR |
| R004 | `*_model.py` | Prohibited: `@register_model_provider`; registration is done via `foundation/__init__.py` `AutoModel.register()` | ERROR |
| R006 | `*convert*.sh` | VLM convert shell must have 3 `python ... convert` calls (foundation + encoder + projector) | ERROR |
| R007 | `*_layer_spec.py` | When referencing `MoELayer`, must define `_get_mlp_module_spec` helper | ERROR |
| R008 | `*_config.py` | `num_layers` / `hidden_size` / `ffn_hidden_size` / `num_attention_heads` must not have default values | ERROR |
| R009 | All `.py` | Prohibited: `@register_model_config` (factory deprecated) | ERROR |
| R010 | All `.py` / `.sh` | First 10 lines of file must contain `Copyright 2026 The LoongForge Authors.` and `SPDX-License-Identifier: Apache-2.0` | ERROR |
| R011 | `*_model.py` | Prohibited: custom RotaryEmbedding subclass when there is no `rope_scaling` | ERROR |
| R012 | `*_model.py` | Prohibited: overriding `_preprocess` when there is no mRoPE-related field | ERROR |
| R013 | `*multi_token_prediction*.py` | MTP class must inherit `MultiTokenPredictionLayer` | ERROR |
| R014 | `*_config.py` | Config classes that import `LanguageModelFamilies` must include `model_spec` and `model_type` class attributes | ERROR |
| R015 | `*_config.py` | When using `adapt_ref`, only copy fields that actually exist in the target model's HF config; prohibited from introducing reference-model-specific fields | ERROR |
| R016 | `*_layer_spec.py` | Entry functions containing MTP references must return `Tuple` (for model.py unpacking) | ERROR |
| R017 | `*_model.py` | When `mtp_block_spec` variable exists, `super().__init__()` must pass `mtp_block_spec=` parameter | ERROR |
| R018 | `*_layer_spec.py` | Dense model's `pre_mlp_layernorm` must not use `num_moe_experts` conditional; write `IdentityOp` directly | ERROR |
| R019 | `*_model.py` / `*_layer_spec.py` | MTP missing in HF code is normal; **must not skip MTP**; as long as config has MTP fields, Omni must implement it | ERROR |
| R020 | `*_layer_spec.py` | When config contains `moe_layer_freq`, layer_spec must implement int / list / str three-format parsing | ERROR |
| R021 | All files | Prohibited: modifying files in the "prohibited from modification" list in `PROTECTED_FILES.md`; "append-only" files can only have additions, not modifications to existing content | ERROR |

---

## Rule Details

### R001 — Config Must Inherit Correct Base Class

- Applicable: Files ending in `_config.py`, `@dataclass` classes ending in `Config`
- Valid base classes: `BaseModelConfig` (Dense/MoE), `BaseModelMLAConfig` (MLA attention, e.g., DeepSeek), `BaseModelStditConfig` (Diffusion)
- Exempt: `BaseModelConfig` / `BaseModelMLAConfig` / `BaseModelStditConfig` themselves

```python
# Correct
@dataclass
class Qwen3Config(BaseModelConfig):
    ...

# Incorrect -- directly inherits object or omits base class
@dataclass
class Qwen3Config:
    ...
```

---

### R002 — Prohibited: Direct Import of TransformerEngine in layer_spec

- Applicable: Files ending in `_layer_spec.py`
- The hardware abstraction layer is provided by `multiacc_modules`; direct TE import causes XPU incompatibility
- **Exemption**: When a TE class is only used as a `ModuleSpec(module=TEXxx)` module type parameter (not instantiated), direct import is allowed, but a comment must be added after the import line: `# ModuleSpec type arg -- cannot dispatch via multiacc_modules`

```python
# Incorrect
import transformer_engine.pytorch as te
from transformer_engine.pytorch.module import Linear

# Correct
from loongforge.models.dispatch import multiacc_modules
linear = multiacc_modules.Linear(...)

# Exempt -- only as ModuleSpec module type parameter, not instantiated
from transformer_engine.pytorch import TEColumnParallelLinear  # ModuleSpec type arg -- cannot dispatch via multiacc_modules
spec = ModuleSpec(module=TEColumnParallelLinear, ...)
```

---

### R003 — layer_spec Must Import multiacc_modules

- Applicable: Files ending in `_layer_spec.py`
- Even if only referencing TE type annotations, must reference indirectly via `multiacc_modules`
- **Exemption**: If all TE imports in the file fall under the R002 exemption (only as `ModuleSpec(module=TEXxx)` type parameters) and no other TE components are needed, then the `multiacc_modules` import is not mandatory

```python
# Must include this line (when no R002 exemption applies)
from loongforge.models.dispatch import multiacc_modules
```

---

### R004 — Prohibited: Using `@register_model_provider` in `_model.py`

- Model registration is done via `AutoModel.register()` in `foundation/__init__.py`
- `@register_model_provider` is the old API, deprecated

```python
# Incorrect
@register_model_provider("qwen3")
def get_qwen3_model(...):
    ...

# Correct -- in foundation/__init__.py:
from .qwen3.qwen3_model import Qwen3Model
AutoModel.register(Qwen3Config, Qwen3Model, exist_ok=True)
```

---

### R006 — VLM Convert Shell Structure Check

- Applicable: Files containing `convert` with `.sh` extension, and content contains `encoder`/`projector`/`vit`
- VLM weight conversion must be in three stages: foundation LLM -> encoder -> projector

```bash
# Correct structure: 3 independent python ... convert calls
python tools/convert_checkpoint/hf_to_mcore.py --model foundation ...
python tools/convert_checkpoint/hf_to_mcore.py --model encoder ...
python tools/convert_checkpoint/hf_to_mcore.py --model projector ...
```

---

### R007 — MoE layer_spec Must Define MoE Helper Function

- Applicable: Files ending in `_layer_spec.py` that reference `MoELayer`
- Must define an MoE helper function, named `_get_mlp_module_spec` or `get_moe_module_spec` (including suffixed variants like `_for_backend`)
- Reference template: `knowledge_base/templates/ffn/moe_ffn.py.tpl`

---

### R008 — Config Required Fields Must Not Have Default Values

Required fields (no default values): `num_layers`, `hidden_size`, `ffn_hidden_size`, `num_attention_heads`

```python
# Incorrect -- has default values
@dataclass
class FooConfig(BaseModelConfig):
    num_layers: int = 32
    hidden_size: int = 4096

# Correct -- no default values
@dataclass
class FooConfig(BaseModelConfig):
    num_layers: int
    hidden_size: int
```

---

### R009 — Prohibited: `@register_model_config`

- `factory.register_model_config` is deprecated
- Configs are registered via `AutoModel.register()` in `foundation/__init__.py`, no decorator needed

---

### R010 — File Header Copyright Notice

All `.py` and `.sh` files must include both of the following within the first 10 lines:

```python
# Copyright 2026 The LoongForge Authors.
# SPDX-License-Identifier: Apache-2.0
```

For third-party derivative files, retain the original copyright header after the LoongForge header.

---

### R011 — Prohibited: Custom RoPE Subclass Without `rope_scaling`

- Applicable: Files ending in `_model.py`
- Exemption condition: the file contains `rope_scaling` or `use_rope_scaling`

```python
# Incorrect -- model has no rope_scaling but defines a custom RoPE
class DynamicRotaryEmbedding(RotaryEmbedding):
    ...

# Correct -- use the base RotaryEmbedding directly, no subclass needed
```

---

### R012 — Prohibited: Overriding `_preprocess` Without mRoPE

- Applicable: Files ending in `_model.py`
- Exemption condition: the file contains `mrope`, `apply_mrope`, `mRoPE`, or `MultiModalRotaryEmbedding`
- Standard LLM `_preprocess` is handled by `BaseGPTModel._preprocess`, no override needed

---

### R013 — MTP Subclass Must Inherit `MultiTokenPredictionLayer`

- Applicable: Files containing `multi_token_prediction` in the name, classes containing `mtp` or `multitokenprediction` (case-insensitive)
- Only override methods that differ from the base class (e.g., `_concat_embeddings`); must not inherit more basic classes like `MegatronModule`

**Scope**: Only applicable when creating a standalone `*multi_token_prediction*.py` file to customize MTP behavior (modifying `_concat_embeddings`, etc.). **Most models implement MTP via `reuse_megatron` (calling `get_gpt_mtp_block_spec()`) without generating a standalone file, so R013 does not apply.**

---

### R013b — `reuse_megatron` MTP Path Completeness Check

When config has `mtp_num_layers > 0` and MTP is implemented via `reuse_megatron` (no standalone MTP file):
- The MTP entry function in `_layer_spec.py` must call `get_gpt_mtp_block_spec()`
- The return value of that function must be `Tuple[TransformerBlockSubmodules, Optional[ModuleSpec]]` (i.e., satisfies R016)
- `_model.py` must unpack the Tuple and pass it via `mtp_block_spec=` parameter to the parent class `__init__` (i.e., satisfies R017)
- If any of the above conditions are not met -> ERROR

---

### R014 — Config Must Include `model_spec` and `model_type` Attributes

- Applicable: Config classes in `_config.py` that import `LanguageModelFamilies` (new-style indicator)
- Old-style files (that do not import `LanguageModelFamilies`) are exempt
- **Scope**: Only foundation LLM configs (classes inheriting `BaseModelConfig` / `BaseModelMLAConfig`). Vision encoder configs and projector configs are not subject to this rule.

```python
@dataclass
class Qwen3Config(BaseModelConfig):
    model_type = LanguageModelFamilies.QWEN3          # Enum value, class-level attribute
    model_spec = [
        "loongforge.models.foundation.qwen3.qwen3_layer_spec",
        "get_qwen3_spec",      # Use get_qwen3_layer_and_mtp_spec when MTP is present
    ]                                                  # Class-level attribute

    num_layers: int
    hidden_size: int
    ...
```

Both are **class-level attributes** (not dataclass fields). Without them, the framework cannot dispatch to the correct layer_spec.

---

### R015 — When Using `adapt_ref`, Only Copy Fields That Actually Exist in the Target Model

- Applicable: All `_config.py` files (when generated via `adapt_ref` strategy)
- Prohibited from introducing fields from the reference family that the target model does not have

Correct procedure:
1. Read the reference family's `_config.py`, list all fields
2. Cross-check each field against the new model's HF `config.json`
3. **Fields that do not exist must not be copied**

Common trap fields (do not copy blindly):

| Reference Model Field | Needed in Dense LLM? |
|----------------------|---------------------|
| `kv_channels` | Only needed for MLA models; GQA is derived from `num_query_groups` |
| `num_experts` / `moe_ffn_hidden_size` | Only needed for MoE |
| `word_embeddings_for_head` | Convert script field, not placed in config |
| `make_vocab_size_divisible_by` | Usually handled by base class, not required |
| `vocab_size_in_config_file` | `vocab_size_in_config_file` is a LoongForge common field (mapped from HF config.json's `vocab_size`); all foundation LLM configs should include this field, not just minimax. |

GQA field default values must reflect the actual model:
- `group_query_attention: bool = True` (if the model uses GQA)
- `num_query_groups: int = <actual KV head count>` (must not be `1`)

---

### R016 — MTP layer_spec Entry Function Must Return Tuple

- Applicable: Entry functions in `_layer_spec.py` containing `MultiTokenPrediction` or `mtp`
- In model.py, unpacked as `transformer_layer_spec, mtp_block_spec = import_module(...)`

```python
# Correct
def get_qwen3_layer_and_mtp_spec(...) -> Tuple[ModuleSpec, ModuleSpec]:
    ...
    return transformer_layer_spec, mtp_block_spec
```

---

### R017 — When MTP Exists, `super().__init__()` Must Pass `mtp_block_spec`

- Applicable: When `_model.py` contains `mtp_block_spec` variable
- Exempt: Base class files starting with `base_`

```python
# Correct
super().__init__(
    config=config,
    transformer_layer_spec=transformer_layer_spec,
    mtp_block_spec=mtp_block_spec,   # <- Must pass
    ...
)
```

**R016/R017 Triple Linkage**: For models with MTP, the following three locations must be synchronized; none can be missing:

| Location | Required Action |
|----------|----------------|
| `_layer_spec.py` | Entry function returns `Tuple[ModuleSpec, Optional[MultiTokenPredictionBlockSubmodules]]` |
| `_model.py.__init__` | Unpack as `transformer_layer_spec, mtp_block_spec = import_module(...)`, pass `mtp_block_spec=` to `super().__init__()` |
| MTP implementation file | If concatenation order differs from Megatron standard, create a subclass to override `_concat_embeddings` |

---

### R018 — Dense layer_spec Must Not Use MoE Conditionals

- Applicable: `_layer_spec.py` files that do not contain `MoELayer` (i.e., dense models)
- Dense = `IdentityOp`; MoE-only = `TENorm`; only Hybrid (with `moe_layer_freq` and dense layers) can use conditionals

```python
# Incorrect -- dense model should not have this conditional
pre_mlp_layernorm = LayerNorm if config.num_moe_experts else IdentityOp

# Correct
pre_mlp_layernorm = IdentityOp
```

---

### R019 — No MTP in HF Code Does Not Mean MTP Implementation Is Unnecessary

- HF only handles inference and typically does not include MTP implementation; this is normal
- **Criterion**: If config contains `num_nextn_predict_layers > 0` or equivalent MTP field -> Omni **must** implement MTP
- Must not skip R016/R017 just because "HF has no MTP class"

---

### R020 — `moe_layer_freq` Must Support Three Formats

- Applicable: `_layer_spec.py` where config contains `moe_layer_freq` field

```python
# Correct -- all three formats supported
if isinstance(config.moe_layer_freq, int):
    # Every N layers is MoE
    is_moe = (layer_idx % config.moe_layer_freq == 0)
elif isinstance(config.moe_layer_freq, list):
    # Specified layer index list
    is_moe = (layer_idx in config.moe_layer_freq)
elif isinstance(config.moe_layer_freq, str):
    # Parse string-form list into Python list, e.g., "[0,1,1,...]"
    import ast
    freq_list = ast.literal_eval(config.moe_layer_freq)
    is_moe = bool(freq_list[layer_idx % len(freq_list)])

# Incorrect -- assumes fixed format
is_moe = (layer_idx % config.moe_layer_freq == 0)  # Crashes when moe_layer_freq is a list
```

> **str format note**: String forms like `"[0]*3+[1]*58"` need to be `eval()`'d first, then indexed by position (not character-by-character). If str format input does not need to be supported, the `str` branch can raise a `ValueError` with a clear message, but must not process it using character indexing.

---

### R021 — Common File Protection

- Applicable: All file changes produced during model adaptation
- Full protection list: `knowledge_base/schema/PROTECTED_FILES.md`

**Check Method**: Compare git diff before and after adaptation, confirming all three conditions are met:

1. **"Prohibited from modification" files**: No changes to these files may appear in the diff
2. **"Append-only" files**: These files in the diff must only have new lines added, no deleted lines, no modified lines
3. **Phase 2 modifiable files**: Existing branches/functions/conditionals logic must not change; only new branches may be appended at method ends or new files created

**Trigger Scenario**: During adaptation, discovering that a protected file must be modified for the new model to work

```
# Incorrect -- modifying a common loss function for a new model
# loongforge/train/get_loss_func.py
def default_loss_func(...):
    if model_type == "new_model":     # <- Prohibited: modified a common file
        ...

# Incorrect -- modifying existing enum values
# loongforge/utils/constants.py
class LanguageModelFamilies:
    QWEN3 = "qwen3_modified"         # <- Prohibited: modified an existing entry

# Correct -- appending to the end of the enum
class LanguageModelFamilies:
    ...
    NEW_MODEL = "new_model"           # <- Allowed: appended a new entry
```

If a protected file truly needs modification -> Output `HUMAN_NEEDED: Need to modify protected file <file_path>, reason: <reason>`, for human evaluation of whether it constitutes framework evolution.

---

## Prohibited Actions

- **Must not** modify any files in the "prohibited from modification" list in `schema/PROTECTED_FILES.md` (including `models/dispatch.py`, `models/factory.py`, existing test files, etc.)
- **Must not** directly `import transformer_engine.*` in layer_spec (R002)
- **Must not** simplify the three-stage forward (`_preprocess` -> `decoder` -> `_postprocess`)
- **Must not** use `@register_model_provider` decorator in `_model.py` (R004)
- **Must not** copy auxiliary functions from reference models (e.g., FP8 `_load_state_dict_hook`, `DynamicRotaryEmbedding` subclasses) to target models that do not need that functionality

---

## Generation Quality Self-Check Checklist (Review After Writing Each File)

### `_config.py`

- [ ] Inherits the correct base class (R001)
- [ ] Has `model_spec` class attribute pointing to the correct layer_spec function (R014)
- [ ] Has `model_type` class attribute corresponding to constants.py enum (R014)
- [ ] No `@register_model_config` decorator (R009)
- [ ] Contains only fields that actually exist in the target model (R015)
- [ ] GQA field default values match the actual model (R015)
- [ ] Required fields have no default values (R008)

### `_layer_spec.py`

- [ ] All TE components referenced via `multiacc_modules.*` (R002/R003)
- [ ] `pre_mlp_layernorm`: Dense=`IdentityOp`, MoE-only=`TENorm`, Hybrid uses conditional (R018)
- [ ] When known to have no QK norm, `q_layernorm=k_layernorm=IdentityOp`
- [ ] With MTP, entry function returns `Tuple` (R016)
- [ ] When config has `moe_layer_freq`, int/list/str three-format parsing is implemented (R020)

### `_model.py`

- [ ] With MTP, `import_module` unpacks as tuple and passes `mtp_block_spec=` (R017)
- [ ] `forward()` includes `PHASE1_VERIFY` hook (controlled by `OMNI_PHASE1_VERIFY` environment variable)
- [ ] No unnecessary auxiliary functions (FP8 hook, DynamicRoPE, etc.)
- [ ] No `rotary_dtype` parameter (unless using custom RoPE)

---

## Exception Handling

| Situation | Action |
|-----------|--------|
| Delta level >= 4 (new operator/new paradigm) | Immediately output `HUMAN_NEEDED: delta level N`, stop |
| Linter same error category remains unresolved after the phase retry budget | Follow the retry and escalation policy defined by the caller phase manual |
| HF config.json missing required field | Output `HUMAN_NEEDED: missing field <field_name>`, stop |
| Encountering unknown model_type | First check `sources/`; if no match, output `HUMAN_NEEDED: unknown model_type` |

---

## Fix Loop

```
for each generated file:
    Check <file> item by item per rules in this document
    if errors:
        locate rule -> Edit fix
        re-check
        if still errors after the caller phase retry budget:
            return unresolved rule findings to the caller phase
```

Retry limits, failure-pattern archiving, and `human_needed` escalation are controlled by the caller phase manual. This document only defines static rules and self-check criteria.
