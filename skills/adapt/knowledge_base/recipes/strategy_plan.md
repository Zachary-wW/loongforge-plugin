# strategy_plan: In-Memory Format + Decision Cases

> For use by Phase 1 Step 2. After Step 2 completes, maintain this structure in memory for reference during Step 3 per-file generation.

---

## In-Memory Format

```yaml
strategy_plan:
  attention:
    phase0_strategy: adapt_ref
    final_strategy: wrap_megatron
    reason: "Megatron SelfAttention base class is usable, need to override get_query_key_value_tensors to handle gate split"
    megatron_class: SelfAttention
    megatron_file: megatron/core/transformer/attention.py
    new_file: loongforge/models/foundation/<family>/gated_attention.py  # filled when wrap/new_impl

  norm:
    phase0_strategy: reuse_ref
    final_strategy: reuse_ref
    reason: "Identical to candidate implementation"
    candidate_ref: loongforge/models/foundation/<candidate>/<candidate>_layer_spec.py

  mtp:
    phase0_strategy: new_impl
    final_strategy: reuse_megatron
    reason: "Megatron MultiTokenPredictionBlock has complete implementation"
    megatron_class: MultiTokenPredictionBlock
    megatron_file: megatron/core/transformer/multi_token_prediction.py

  swiglu_activation:
    phase0_strategy: adapt_ref
    final_strategy: modify_existing
    reason: "Existing fused SwiGLU module is the right abstraction, but behavior_modifications require clamp/offset behavior inside helper logic."
    target_file: megatron/core/fusions/fused_bias_swiglu.py
    protected_file_decision: human_needed_unless_framework_bugfix_authorized
    validation: "Compare fused and unfused SwiGLU with synthetic inputs crossing the clamp threshold."
```

**Completion Condition**: All components have `final_strategy`; `new_file` paths for `wrap_megatron` / `new_impl` are determined; every `behavior_modifications` entry is mapped to a strategy or `human_needed`.

---

## Actual Decision Cases

| Model | Component | diff | final_strategy | Reason |
|-------|-----------|------|----------------|--------|
| DSV3 | attention (MLA) | differs | reuse_megatron | Megatron `MLASelfAttention` has complete implementation; layer_spec can directly configure `q_lora_rank/kv_lora_rank` |
| DSV3 | moe_gate | differs | reuse_megatron | Megatron `TopKRouter` supports `sigmoid+noaux_tc+group_limited_topk`; just align config fields |
| DSV3 | mtp | new_component | reuse_megatron | Megatron `MultiTokenPredictionBlock` has complete implementation; connect via `get_gpt_mtp_block_spec()` |
| Qwen3Next | attention (gated softmax) | differs | wrap_megatron | Inherits Megatron `SelfAttention`, overrides `get_query_key_value_tensors` to handle gate split, < 50 lines |
| Qwen3Next | linear_attention (GatedDeltaNet) | new_component | new_impl | No corresponding Megatron implementation; implement from scratch using `fla` external library |

## Strategy Semantics

| final_strategy | Use When | Required Evidence |
|---|---|---|
| `reuse_ref` | Candidate Omni implementation is equivalent and no Megatron-specific change is needed | Candidate file and matching component behavior |
| `reuse_megatron` | Megatron module covers interface, data flow, and numerical behavior via config/layer_spec/submodule slots | Megatron file/class plus behavior coverage notes |
| `wrap_megatron` | Megatron base is usable but a thin wrapper or slot replacement is needed | Base class, overridden method/slot, why behavior remains localized |
| `adapt_ref` | Candidate Omni implementation is closest and can be adapted without changing protected framework behavior | Candidate file plus delta list |
| `new_impl` | No equivalent exists in Megatron or Omni | HF logic, template basis, expected integration points |
| `override_in_omni` | Megatron structure is reusable but behavior is model-specific or risky for shared Megatron | Omni subclass/wrapper/module path, layer_spec replacement, validation test |
| `modify_megatron_general` | Shared Megatron behavior is incomplete or incorrect for a broadly valid feature | General-correctness rationale, compatibility plan, blast radius, regression tests |
| `modify_existing` | Existing non-Megatron shared module is the right abstraction but its internal behavior is insufficient | Behavior gap, target file/helper, why config/wrapper/slot replacement cannot express it, blast radius, tests |
| `insert_hook` | Load/save/reference or execution flow needs an extension point with default no-op behavior | Hook location, default behavior, model-specific use, tests |
