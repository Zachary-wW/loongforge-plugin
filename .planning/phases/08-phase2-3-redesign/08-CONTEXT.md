# Phase 8: Phase 2+3 Redesign — Context

**Gathered:** 2026-06-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Redesign Phase 2 and Phase 3 of the adapt skill to: (1) consume bridge_mapping as primary input replacing model_spec_path/reference_contract_path, (2) support dual-repo file consumption (generated_loongforge_files + generated_megatron_files from Phase 1 output), (3) align output schemas with the new Phase 0/1 artifact structure, and (4) add bridge_mapping_consumed validation fields.

Scope: Phase 2 agent.md rewrite, Phase 3 agent.md rewrite, Phase 2 output schema update, Phase 3 output schema update, and validate_phase_completion.py Phase 2+3 checks. Phase 4/5 changes are separate phases.

</domain>

<decisions>
## Implementation Decisions

### Phase 2 Bridge Mapping Consumption
- **D-01:** Phase 2 uses `bridge_mapping_path` as PRIMARY input for weight name mapping in Step 1 and Step 3. `model_spec_path` is legacy fallback only (used when bridge_mapping_path is absent). Step 1 reads `bridge_mapping.component_bridge[].weight_map` as the authoritative name map source, not just a hint. When `weight_map` is `null` (gap component), Phase 2 must design new weight mappings from scratch (same as current behavior for gap components).
- **D-02:** Phase 2 Input Contract reads `generated_loongforge_files` and `generated_megatron_files` (split lists) from Phase 1 output, replacing the flat `generated_files` list. When the split fields are absent (legacy Phase 1 output), fall back to reading `generated_files` as LoongForge-only.
- **D-03:** Phase 2 Step 0 (Conversion Contract Preflight) reads `bridge_mapping.conversion_requirements` instead of `model_spec.conversion_requirements`. When bridge_mapping is absent, fall back to model_spec. The `reference_contract_path` field in Phase 0 output is no longer read by Phase 2; its contents have been absorbed into bridge_mapping (per Phase 6 D-05).

### Phase 3 Bridge Mapping Consumption
- **D-04:** Phase 3 Step 0 reads `bridge_mapping.implementation_contract` and `bridge_mapping.conversion_requirements` instead of `reference_contract_path` and `model_spec.phase3_reference_requirements`. When bridge_mapping is absent, fall back to legacy fields.
- **D-05:** Phase 3 Step 2 (Detect reference type) reads `bridge_mapping.phase3_reference_requirements` for `allowed_reference_types` and `custom_reference_loader_required`. When bridge_mapping is absent, fall back to `model_spec.phase3_reference_requirements`. The `reference_contract_path` field in Phase 0 output is deprecated for Phase 3; Phase 3 reads bridge_mapping directly.

### Output Schema Updates
- **D-06:** Phase 2 output schema adds: `source.bridge_mapping_path`, `checks.bridge_mapping_consumed` (true when bridge_mapping was used as primary input), `artifacts.generated_megatron_files` (dual-repo consistency with Phase 1). The `source.model_spec_path` field remains for legacy backward compatibility.
- **D-07:** Phase 3 output schema adds: `source.bridge_mapping_path`, `checks.bridge_mapping_consumed`. The `source.reference_contract_path` field is deprecated/nullable — present when legacy mode, null when bridge_mapping mode.

### Validation
- **D-08:** validate_phase_completion.py adds Phase 2 and Phase 3 checks for `bridge_mapping_consumed` (conditional — only enforced when the field is present, same pattern as Phase 1). Phase 2 check also validates `generated_megatron_files` prefix consistency if present. Phase 3 check validates bridge_mapping_consumed is true when bridge_mapping was used.

### Claude's Discretion
- Exact wording of the "Key path usage rule" section rewrite in Phase 2 agent.md
- Whether Phase 2 Step 1 Source Discovery Mandates reference bridge_mapping.component_bridge[].behavioral_diff for edge cases
- Exact placement of bridge_mapping_consumed field in output JSON (in checks section, consistent with Phase 1)

### Folded Todos
None.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 0 v2 output (consumed by Phase 2/3)
- `skills/adapt/knowledge_base/schema/bridge_mapping_schema.yaml` — Bridge mapping YAML schema (component_bridge + gaps + validator_requirements + conversion_requirements + phase3_reference_requirements)
- `skills/adapt/knowledge_base/schema/hf_analysis_schema.yaml` — HF analysis YAML schema (supersedes model_spec)
- `skills/adapt/knowledge_base/schema/reference_impl_analysis_schema.yaml` — Megatron-side analysis schema
- `skills/adapt/knowledge_base/examples/bridge_mapping_llm.yaml` — DS V4 bridge_mapping example

### Current Phase 2/3 implementation (to be rewritten)
- `skills/adapt/references/phases/phase2/agent.md` — Current Phase 2 agent manual (512 lines, 6 steps)
- `skills/adapt/references/phases/phase2/phase2_output_schema.yaml` — Current Phase 2 output schema (95 lines)
- `skills/adapt/references/phases/phase3/agent.md` — Current Phase 3 agent manual (413 lines, 10 steps)
- `skills/adapt/references/phases/phase3/phase3_output_schema.yaml` — Current Phase 3 output schema (137 lines)

### Validation infrastructure
- `skills/adapt/scripts/validate_phase_completion.py` — Phase validation gate (267 lines, already has Phase 0 and Phase 1 checks)

### Phase 1 redesign pattern reference
- `.planning/phases/07-phase1-redesign/07-CONTEXT.md` — D-09 bridge_mapping primary pattern
- `.planning/phases/07-phase1-redesign/07-01-PLAN.md` — Phase 1 agent.md rewrite pattern
- `.planning/phases/07-phase1-redesign/07-03-PLAN.md` — validate_phase_completion.py Phase 1 checks pattern

### Architecture references
- `skills/adapt/references/loop_engineering/README.md` — P1-P21 principles mapping
- `skills/adapt/lib/loop_controller.py` — Loop FSM implementation
- `skills/adapt/lib/schema.py` — Pydantic v2 models (BridgeMapping, ComponentBridge, GapEntry)
- `.planning/PROJECT.md` — Core value, constraints, key decisions

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets from Phase 7 Redesign
- Phase 1 agent.md already establishes the bridge_mapping_path as primary input pattern — Phase 2/3 follow the same pattern
- Phase 1 output schema already has `bridge_mapping_consumed`, `generated_megatron_files`, `strategy_overrides` — Phase 2/3 output schemas follow the same pattern
- validate_phase_completion.py already has conditional (if X is not None) Phase 1 checks — Phase 2/3 checks follow the same pattern
- `_validate_phase1_bridge_mapping_consumption` helper function can be generalized or replicated for Phase 2/3

### Phase 2 Specific Bridge Mapping Usage
- Phase 2 Step 1 already mentions "When bridge_mapping.yaml exists, read bridge_mapping.component_bridge[].weight_map" — but only as an optional supplement, not as primary input. The redesign promotes it to primary.
- Phase 2 Step 0 already reads `model_spec.conversion_requirements` and `reference_contract_path` — both replaced by bridge_mapping fields
- Phase 2 Input Contract already has `bridge_mapping_path` listed in phase0_output artifacts — but the "Key path usage rule" still says "use model_spec.yaml" — needs inversion

### Phase 3 Specific Bridge Mapping Usage
- Phase 3 Step 0 reads `reference_contract_path` and `model_spec.phase3_reference_requirements` — both absorbed into bridge_mapping
- Phase 3 Step 2 reads `phase3_reference_requirements.allowed_reference_types` and `custom_reference_loader_required` — now in bridge_mapping.phase3_reference_requirements
- Phase 3 Input Contract does NOT currently reference bridge_mapping at all — needs addition

### Integration Points
- Phase 2 reads Phase 1 output: `generated_loongforge_files` and `generated_megatron_files` (split lists) replace flat `generated_files`
- Phase 3 reads Phase 2 output: unchanged structure, but Phase 2 output gains `bridge_mapping_consumed` field
- Both Phase 2 and Phase 3 read Phase 0 output: `bridge_mapping_path` replaces `model_spec_path` as primary
- validate_phase_completion.py: Phase 2 and Phase 3 checks parallel the existing Phase 1 check structure

</code_context>

<specifics>
## Specific Ideas

- Phase 2 weight_map is the most critical bridge_mapping consumption: the name_map in convert YAML is the core Phase 2 deliverable. When bridge_mapping provides weight_map entries, Step 1 uses them as authoritative starting points rather than deriving from scratch. Gap components (weight_map: null) still require Phase 2 to design new mappings.
- Phase 3 migration is primarily a Step 0 and Step 2 change: replacing reference_contract_path reads with bridge_mapping reads. The loss-diff workflow (Steps 4-7) is unchanged.
- Dual-repo file consumption in Phase 2 matters because Phase 1 now generates Megatron files that may affect convert_checkpoint (e.g., new Megatron modules with custom weight loading). Phase 2 needs to know about these files for the "Mcore module path discovery" in Step 1 Source Discovery Mandates.
- bridge_mapping.conversion_requirements absorbs reference_contract.conversion_requirements (per Phase 6 D-05). Phase 2 Step 0 can read it directly from bridge_mapping instead of reference_contract.
- bridge_mapping.phase3_reference_requirements absorbs reference_contract.phase3_reference_requirements (per Phase 6 D-05). Phase 3 Step 0/2 can read it directly from bridge_mapping.

</specifics>

<deferred>
## Deferred Ideas

- **Phase 2 convert_yaml template generation from bridge_mapping**: Automatically generating the convert YAML name_map from bridge_mapping.weight_map without agent intervention. Current design: agent uses weight_map as authoritative starting point but still verifies against HF checkpoint and LoongForge source. Full automation deferred until weight_map coverage is proven reliable.
- **Phase 2/3 Loop FSM exit path restructuring**: Phase 2/3 already have Loop Engineering Hooks. Further FSM integration (like Phase 1's explicit exit path description) is not needed — Phase 2/3 already describe the repos:-present and repos:-absent paths in their Loop Engineering Hooks sections.
- **Phase 3 loss-diff sub-doc rewrite**: The loss-diff sub-doc (`references/phases/phase3/loss_diff.md`) is a separate reference document. Changes to it are out of scope for this phase; only agent.md consumption changes are in scope.

</deferred>

---

*Phase: 08-phase2-3-redesign*
*Context gathered: 2026-06-24*
