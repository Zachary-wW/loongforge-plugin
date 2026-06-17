# Source Resolution Order When modeling_*.py Is Missing

> For use by Phase 0 Step 1d. When there is no `modeling_*.py` in `hf_path/`, evaluate in A->B->C->D order.

---

## Situation A -- User Has Explicitly Specified the Source Location in Input

If the user has provided the following information in the task description:
- `modeling_path`: pointing to a `.py` file or directory
- Or described that "the model code is in the transformers library at `transformers.models.<X>.modeling_<X>`"

Directly use that path as `modeling_*.py`, record `modeling_source: "user_specified"`, no fallback needed.

---

## Situation B -- User Explicitly States No modeling File, Architecture Inherits from a Known Model

If the user describes "no modeling, architecture is the same as X (e.g., DeepSeek-V3), only differences in README":

Do **not** search for a source file; directly set:
```yaml
modeling_source: "inherited_from"
inherited_from: "<X>"
```

`hf-model-analyzer` uses the inherited model's HF source as the analysis basis, and the candidate is locked directly.
Step 5 comparison results are initially `same`, but each change point in the README's `special_arch_notes` must be converted to the corresponding component's `differs` or `new_component` -- differences do not disappear due to "inheritance"; only their source changes from source code scanning to README description.

---

## Situation C -- Automatic Fallback (User Did Not Specify)

```python
import importlib, inspect
from transformers import AutoConfig

cfg = AutoConfig.from_pretrained(hf_path)
model_type = cfg.model_type
module_path = f"transformers.models.{model_type}.modeling_{model_type}"
try:
    mod = importlib.import_module(module_path)
    source_path = inspect.getfile(mod)
except ModuleNotFoundError:
    source_path = None
```

- **Found**: Treat `source_path` as `modeling_*.py`, record `modeling_source: "transformers_library"`
- **Not found**: Proceed to Situation D

---

## Situation D -- config.json Field Inference (After Situation C Fails)

When there is no modeling file and the transformers library also cannot find one, infer the inheritance relationship from config.json:

1. Parse the `architectures` field (e.g., `["DeepseekV32ForCausalLM"]`), extract the class prefix, and perform similarity matching against KB source family names
2. Use structural fields in config.json (`q_lora_rank` / `kv_lora_rank` / `n_routed_experts` / `rope_scaling` etc.) to compute overlap with feature fields in KB sources yaml, selecting the family with the most overlapping fields
3. Append new fields in config.json that **do not appear in the standard field set of that family** (e.g., DSV3.2's `index_head_dim` / `index_n_heads` / `index_topk`) to `readme_context.special_arch_notes` as structural difference signals

If matching succeeds (overlapping fields >= 5 core fields):
- Record `modeling_source: "config_inferred"`, `inherited_from: <matched_family>`
- When passing to `hf-model-analyzer`, process according to the `inherited_from` path

If matching fails: output `human_needed`, requesting the user to explicitly specify the inheritance relationship.
(Re-entry point: after the human provides `modeling_path` or `inherited_from`, re-execute from **Step 1d**)
