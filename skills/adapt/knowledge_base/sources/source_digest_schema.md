# model_spec.yaml Structure Specification

> Phase 0 produces `run_dir/phases/phase0/model_spec.yaml` as its sole output. The `hf_file / hf_line` pointers
> allow subsequent Phases to directly read HF source files from `hf_path` on demand, without pre-extracted caching.
>
> **NOTE (v2):** Phase 0 has been redesigned to produce three core deliverables:
> `hf_analysis.yaml` (supersedes model_spec.yaml), `reference_impl_analysis.yaml`, and `bridge_mapping.yaml`.
> See the "Phase 0 Output Changes (v2)" section below for details.

---

## Phase 0 Output Changes (v2)

Phase 0 has been redesigned from a single-side HF analysis to a dual-reference bridge mapping architecture. The output artifacts have changed as follows:

### Deprecated fields (still readable for backward compat)

| Field | Status | Replacement |
|-------|--------|-------------|
| `model_spec_path` | **Deprecated** | `hf_analysis_path` |
| `reference_contract_path` | **Deprecated** | Absorbed into `bridge_mapping_path` (per D-05) |

### New fields

| Field | Type | Description |
|-------|------|-------------|
| `hf_analysis_path` | string (required) | Path to `phases/phase0/hf_analysis.yaml` -- supersedes `model_spec.yaml` (per D-04) |
| `reference_impl_analysis_path` | string (required) | Path to `phases/phase0/reference_impl_analysis.yaml` -- Megatron/community-side module analysis (per D-18) |
| `bridge_mapping_path` | string (required) | Path to `phases/phase0/bridge_mapping.yaml` -- component-by-component bridge mapping, the primary Phase 0 deliverable (per D-16) |
| `gap_decisions_path` | string (required) | Path to `phases/phase0/gap_decisions.md` -- human-readable record of components that cannot be 1:1 mapped (per D-02) |

### Phase 1 consumption change

**Phase 1 should read `bridge_mapping.yaml` as the primary input**, not `model_spec.yaml` or `hf_analysis.yaml` alone. The bridge_mapping contains:
- `component_bridge[]`: strategy, confidence, weight_map, behavioral_diff for each component
- `gaps[]`: missing Megatron modules with impact level and phase1_guidance
- `validator_requirements[]`: what downstream phases need to verify
- `implementation_contract`: integration level and required new components

Phase 1 may still read `hf_analysis.yaml` for detailed structural_tags and HF source pointers (hf_file, hf_line), and `reference_impl_analysis.yaml` for Megatron class signatures and submodule slots.

### Output directory structure (v2)

```
run_dir/phases/phase0/
  hf_analysis.yaml              (was model_spec.yaml -- per D-04)
  reference_impl_analysis.yaml  (NEW -- per D-18)
  bridge_mapping.yaml           (NEW, absorbs reference_contract.yml -- per D-05)
  gap_decisions.md              (NEW -- per D-02)
  slice_report.json             (retained -- per D-03)
  attempts.jsonl                (optional, quality loop records)
  sliced_hf/                    (optional, only when slicing performed)
```

---

## model_spec.yaml Complete Section Structure

```yaml
# -- Top-Level Meta Information -----------------------------------------
model_category: llm | vlm | diffusion
candidate_family: deepseek_v3
hf_reference_path: /path/to/candidate/hf
candidate_match_reason: "..."
has_chat_template: false
modeling_source: local | transformers_library | config_inferred | inherited_from | user_specified
inherited_from: ~   # Only fill when modeling_source=inherited_from

# -- Component Analysis (Core Input for Phase 1) -------------------------
components:
  <component_key>:
    diff: same | differs | new_component | absent_in_hf
    strategy: reuse_ref | adapt_ref | new_impl  # Phase 0 initial estimate, Phase 1 Step 2 can override
    delta: []           # Fill when diff=differs, specific to field names and values
    note: ~             # README special notes
    hf_class: ~         # Corresponding class name in HF
    hf_file: ~          # File name relative to hf_path, e.g., modeling_deepseek.py
    hf_line: ~          # Class definition start line
    structural_tags: [] # Structural feature tags
    same_class_as: ~    # Fill when sharing the same class as another component
    absent_in_hf: false # true when HF has no implementation

# -- Novel Modules (Cannot Be Classified Under Standard Component Keys) --
novel_modules:
  - hf_class: DSAIndexer
    hf_file: ~           # null if in external library
    hf_line: ~
    desc: "..."
    external_dependency: false

# -- Behavior Modifications (Core Input for Phase 1/2/3) -----------------
# Records behavior-only deltas where an existing component may still need
# different forward/helper/load/save behavior.
behavior_modifications:
  - id: swiglu_clamp_offset
    component: ffn | moe | attention | checkpoint | phase3_reference | other
    behavior_type: activation | routing | mtp_context | fp8_reference_load | checkpoint_key_transform | guard | other
    source_evidence:
      hf_file: modeling_xxx.py
      hf_line: 123
      config_fields: [activation_func_clamp_value, glu_linear_offset]
    required_behavior: "Clamp GLU halves and apply linear offset before activation product."
    affected_existing_modules:
      - megatron/core/transformer/mlp.py
      - megatron/core/fusions/fused_bias_swiglu.py
    validation_hint: "Use synthetic inputs exceeding the clamp threshold; random initialization is insufficient."

# -- Adaptation Traps and Special Features -------------------------------
traps:
  - "..."

special_features:
  routing_bias:
    hf_key: e_score_correction_bias
    desc: "..."

# -- Weight Structure (Core Input for Phase 2) ---------------------------
weight_structure:
  total_keys: 291
  components:
    llm:
      key_count: 241
      sample_keys:
        - "model.layers.0.self_attn.q_a_proj.weight"
        - "model.layers.0.mlp.gate_proj.weight"
        - "model.embed_tokens.weight"
        - "lm_head.weight"
      naming_pattern: "model.layers.{i}.{module}.{param}"
      index_range: "model.layers.0 ~ model.layers.60"
    vision_encoder:    # VLM only
      key_count: 32
      sample_keys: [...]
      naming_pattern: "..."
    projector:         # VLM only
      key_count: 18
      sample_keys: [...]
      naming_pattern: "..."
```

---

## Per-Phase Reading Conventions

| Phase | Content Read | Purpose |
|-------|-------------|---------|
| Phase 0 | Writes all sections | Output |
| Phase 1 Step 1 | Top-level meta information + `components` + `behavior_modifications` | Understand candidate family, component overview, and behavior-only deltas |
| Phase 1 Step 2 | `components[*].diff/strategy/delta/structural_tags/hf_file/hf_line` + `behavior_modifications` | Strategy decision: read HF source on demand via pointers; classify behavior gaps before declaring reuse |
| Phase 1 Step 3 | `components[*]` + relevant `behavior_modifications[*].affected_existing_modules` | Code generation reference and protected-file routing |
| Phase 2 | `candidate_family` (Step 1 locates reference convert YAML) + `weight_structure` section (Step 1 module format matching) + `components[*].hf_file/hf_line` + `behavior_modifications` with checkpoint/load/save behavior | Module format matching + convert YAML generation, hook strategy selection, and verification |
| Phase 3 | `behavior_modifications` with `fp8_reference_load`, `checkpoint_key_transform`, or `mtp_context` | Decide whether plain HF `from_pretrained()` is trustworthy or a custom reference loader is required |
| Phase 5 | `components[*].hf_file/hf_line` + behavior modifications tagged as `guard`, `routing`, or `mtp_context` | Locate root cause when feature toggle fails |

---

## HF Source On-Demand Reading Specification

All Agents after Phase 1 read HF source code in the following manner, **no pre-extraction, no caching**:

```python
# Example: Locate the complete definition of an attention class
hf_file = model_spec.components["attention"]["hf_file"]    # "modeling_deepseek.py"
hf_line = model_spec.components["attention"]["hf_line"]    # 630
hf_class = model_spec.components["attention"]["hf_class"]  # "DeepseekV3Attention"

# Read hf_path/<hf_file>, starting from hf_line, read the complete class definition
full_path = Path(hf_path) / hf_file
# Read the class's __init__ and forward, focusing on the differences described in the delta field
```

Reading focus:
1. `__init__`: Sub-module composition (member variables, shapes, types)
2. `forward`: Computation logic and data flow (especially the differences pointed out by the delta field)

---

## Write Rules (Used by Phase 0)

- The `components`, `behavior_modifications`, `traps`, and `special_features` sections are written by the `hf-model-analyzer` skill (Phase 0 Step 2)
- The `weight_structure` section is **appended** by Phase 0 Step 3 (does not overwrite existing sections)
- Both steps write to the same file `run_dir/phases/phase0/model_spec.yaml`
