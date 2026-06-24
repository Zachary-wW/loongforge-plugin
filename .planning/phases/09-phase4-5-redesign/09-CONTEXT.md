# Phase 9: Phase 4+5 Redesign — Context

**Gathered:** 2026-06-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Redesign Phase 4 and Phase 5 of the adapt skill to consume Phase 0's three-document output (hf_analysis.yaml, bridge_mapping.yaml) as primary input instead of model_spec.yaml, and add Megatron file paths to Phase 5 KB extraction logic.

Scope: Phase 4 agent.md rewrite (SMALL -- only Step 2 reads model_spec.yaml directly), Phase 5 agent.md rewrite + extraction_rules.yaml + source_templates + phase5_output_schema.yaml update (MEDIUM -- multiple files need Megatron paths), and validate_phase_completion.py Phase 4/5 checks. Phase 0/1/2/3 agent changes are separate phases (already complete).

</domain>

<decisions>
## Implementation Decisions

### Phase 4 Redesign

- **D-01:** Phase 4 Step 2 reads structure tags from **hf_analysis.yaml** (via `phase0_output.artifacts.hf_analysis_path`) as PRIMARY source, with **bridge_mapping.yaml** as secondary for cross-referencing component types. `model_spec.yaml` is legacy fallback (used only when hf_analysis_path is absent). The structure tags (is_llm, is_moe, is_dense, is_vlm, is_diffusion, has_vision_encoder, has_language_ce_loss) are derived from hf_analysis.components[].structural_tags and hf_analysis.model_category instead of model_spec.yaml fields.

- **D-02:** Phase 4 Input Contract adds `phase0_output.artifacts.hf_analysis_path` and `phase0_output.artifacts.bridge_mapping_path` as required sources (when present). The existing `phase0_output.model.model_type` field remains valid as a quick check, but Step 2's detailed tag derivation must come from hf_analysis.

- **D-03:** Phase 4 Output Contract adds `source.hf_analysis_path` and `source.bridge_mapping_path` fields (conditional -- present only when Phase 0 v2 output exists). `checks.bridge_mapping_consumed` field is added when bridge_mapping was read.

### Phase 5 Redesign

- **D-04:** Phase 5 Input Contract replaces direct `model_spec.yaml` read with **hf_analysis.yaml** (for components, structural_tags, traps, special_features) + **bridge_mapping.yaml** (for component_bridge, gaps). When bridge_mapping_path exists, components data comes from hf_analysis.components and bridge_mapping.component_bridge; when absent, falls back to model_spec.yaml.

- **D-05:** Phase 5 reads **generated_loongforge_files + generated_megatron_files** from Phase 1 output instead of the flat `generated_files` list. The extraction_rules.yaml code_paths section is extended with Megatron file path categories.

- **D-06:** Phase 5 extraction_rules.yaml `structural_tags` section changes source from `run_dir/phases/phase0/model_spec.yaml` to `run_dir/phases/phase0/hf_analysis.yaml`. The `true_when` rules are updated to read from hf_analysis.components[].structural_tags and hf_analysis.model_category instead of model_spec fields.

- **D-07:** Phase 5 extraction_rules.yaml `code_paths` section adds **megatron_code_paths** category for each model type (llm, vlm, diffusion). Match rules for Megatron files use `generated_megatron_files` from phase1_output. Placeholder behavior: `# Phase 1 not complete, to be supplemented` when phase1 is not passed.

- **D-08:** Phase 5 source_templates (llm.yaml, vlm.yaml, diffusion.yaml) add a `megatron_code_paths:` section after the existing `code_paths:` section. Fields populated from Phase 1 generated_megatron_files.

- **D-09:** Phase 5 `traps` extraction reads from both hf_analysis.traps and bridge_mapping.component_bridge[].behavioral_diff as source sections. model_spec.traps and model_spec.special_features are legacy fallback.

- **D-10:** Phase 5 Output Contract adds `source.hf_analysis_path`, `source.bridge_mapping_path` fields and `checks.bridge_mapping_consumed` conditional check. `checks.hf_analysis_consumed` added when hf_analysis was read.

### Shared Patterns (from Phase 7)

- **D-11:** Follow the same conditional-check pattern from Phase 7: when bridge_mapping_consumed is present in checks, validate_phase_completion.py verifies the file exists and is valid. When absent (legacy runs), skip silently. Use `if X is not None` pattern for backward compatibility.

- **D-12:** Phase 5 extraction_rules.yaml version bumped to 2. New fields are additive -- legacy Phase 5 agents that read version 1 rules will simply not produce megatron_code_paths, which is acceptable for backward compat.

### Claude's Discretion

- Exact structural tag derivation logic from hf_analysis (which component structural_tags map to which feature_matrix applies_to tags)
- Whether diff_components extraction also reads bridge_mapping.component_bridge[].delta or only hf_analysis.components[].diff
- Whether Megatron code_paths in source_templates should be a flat list or structured dict matching the LoongForge code_paths format
- How kb-consistency validator is updated to check megatron_code_paths section presence

### Folded Todos
None.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 0 v2 output (consumed by Phase 4/5)
- `skills/adapt/knowledge_base/schema/bridge_mapping_schema.yaml` — Bridge mapping YAML schema (component_bridge + gaps + validator_requirements)
- `skills/adapt/knowledge_base/schema/hf_analysis_schema.yaml` — HF analysis YAML schema (supersedes model_spec)
- `skills/adapt/knowledge_base/examples/bridge_mapping_llm.yaml` — DS V4 bridge_mapping example

### Phase 1 v2 output (consumed by Phase 5)
- `skills/adapt/references/phases/phase1/agent.md` — Phase 1 agent with generated_loongforge_files + generated_megatron_files output
- `skills/adapt/references/phases/phase1/phase1_output_schema.yaml` — Phase 1 output schema with dual-repo files

### Current Phase 4 implementation (to be rewritten)
- `skills/adapt/references/phases/phase4/agent.md` — Current Phase 4 agent manual (333 lines)
- `skills/adapt/references/phases/phase4/feature_matrix.yaml` — Fixed feature matrix (411 lines)
- `skills/adapt/references/phases/phase4/phase4_output_schema.yaml` — Current output schema

### Current Phase 5 implementation (to be rewritten)
- `skills/adapt/references/phases/phase5/agent.md` — Current Phase 5 agent manual (350 lines)
- `skills/adapt/references/phases/phase5/extraction_rules.yaml` — Current KB extraction rules (178 lines)
- `skills/adapt/references/phases/phase5/source_templates/llm.yaml` — LLM source template
- `skills/adapt/references/phases/phase5/source_templates/vlm.yaml` — VLM source template
- `skills/adapt/references/phases/phase5/source_templates/diffusion.yaml` — Diffusion source template
- `skills/adapt/references/phases/phase5/phase5_output_schema.yaml` — Current output schema

### Validation infrastructure
- `skills/adapt/scripts/validate_phase_completion.py` — Phase completion gate (266 lines)
- `skills/adapt/lib/schema.py` — Pydantic v2 models (BridgeMapping, ComponentBridge, etc.)

### Architecture references
- `.planning/phases/07-phase1-redesign/07-CONTEXT.md` — Phase 7 decisions (bridge_mapping primary, confidence-driven, dual-repo)
- `.planning/phases/06-phase0-redesign/06-CONTEXT.md` — Phase 6 decisions (three-document output)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Phase 4 agent.md already has Loop Engineering Hooks for dual-repo PR/branch creation -- these are correct and unchanged
- Phase 4 feature_matrix.yaml uses applies_to tags (llm, vlm, moe, dense, vision_encoder, etc.) -- Step 2's tag derivation just needs to read from hf_analysis instead of model_spec
- Phase 5 extraction_rules.yaml has a clear structure (base_fields, structural_tags, diff_components, traps, code_paths, omni_reference, source_templates) -- extending with megatron_code_paths is additive
- Phase 5 source_templates are simple YAML templates -- adding megatron_code_paths section is straightforward
- validate_phase_completion.py already has Phase 1 conditional checks (bridge_mapping_consumed, generated_megatron_files) as pattern to follow

### Established Patterns
- bridge_mapping_path as PRIMARY, model_spec_path as legacy fallback (from Phase 7 agent.md)
- Conditional checks in validate_phase_completion.py: `if X is not None` for backward compat (from Phase 7 Plan 03)
- Output schema adds bridge_mapping_consumed field (from Phase 1 output schema pattern)
- Phase 0 artifacts section provides hf_analysis_path and bridge_mapping_path (from Phase 6 output schema)

### Integration Points
- Phase 4 Step 2 -> hf_analysis.components[].structural_tags for structure tag derivation
- Phase 4 Step 2 -> bridge_mapping.component_bridge for component type cross-reference
- Phase 5 Step 1 -> hf_analysis for components, structural_tags, traps
- Phase 5 Step 1 -> bridge_mapping for component_bridge, gaps
- Phase 5 Step 1 -> phase1_output.artifacts.generated_loongforge_files + generated_megatron_files
- Phase 5 extraction_rules.yaml -> source path changed from model_spec.yaml to hf_analysis.yaml
- Phase 5 source_templates -> new megatron_code_paths section
- validate_phase_completion.py -> Phase 4 and Phase 5 bridge_mapping_consumed checks

</code_context>

<specifics>
## Specific Ideas

- Phase 4 change is SMALL because only Step 2 reads model_spec.yaml directly. Steps 1, 3-7 don't touch model_spec. The feature_matrix.yaml is a fixed file, not generated from model_spec.
- Structure tag mapping from hf_analysis: model_category gives is_llm/is_vlm/is_diffusion; components.moe_gate or moe_layer gives is_moe; absence of moe gives is_dense; components.attention.structural_tags contains vision_encoder gives has_vision_encoder; components.attention.structural_tags contains mla gives has_mla (already used in feature matrix applies_to).
- Phase 5 Megatron code_paths: generated_megatron_files already has file paths. The match rules can use similar pattern-matching as LoongForge code_paths: files matching `megatron/core/transformer/*.py` -> transformer_core, etc. But since Megatron files are more varied (new modules, existing file modifications), the template should use a simpler key-value mapping: file path -> descriptive key.
- Phase 5 traps extraction: bridge_mapping.component_bridge[].behavioral_diff provides structured behavioral differences that are NOT in model_spec.traps. These should be converted to trap entries (field=behavioral_diff topic, detail=hf vs megatron behavior).
- Phase 5 kb-consistency check needs minor update to verify megatron_code_paths section exists when phase1 is passed.

</specifics>

<deferred>
## Deferred Ideas

- **Phase 4 feature_matrix.yaml redesign**: The applies_to tags in feature_matrix.yaml could be derived from hf_analysis structural tags at runtime instead of being hardcoded. Deferred -- the fixed matrix with manual applies_to evaluation is sufficient and deterministic.
- **Phase 5 KB cross-repo consistency check**: Verify that Megatron code_paths in sources YAML are consistent with the actual files in the Megatron repo. Deferred -- requires live repo access during KB validation, which is out of scope.
- **Phase 5 bridge_mapping gap entries in KB**: Record which bridge_mapping gap entries were resolved (have code_paths) vs still open. Deferred -- gap tracking is a future enhancement, not needed for v1.

</deferred>

---

*Phase: 09-phase4-5-redesign*
*Context gathered: 2026-06-24*
