# Phase 6: Phase 0 Redesign — Dual-Reference Bridge Analysis - Context

**Gathered:** 2026-06-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Redesign Phase 0 of the adapt skill from single-side HF analysis to dual-reference-system bridge mapping. Phase 0 produces structured analysis of both HF source and Megatron/community reference implementations, with a component-by-component bridge mapping as the core deliverable. This ensures downstream Phase 1-5 have sufficient information to consume without blind guessing.

Scope: Phase 0 output artifacts and analysis logic only. Phase 1-5 internal logic changes are separate phases.

</domain>

<decisions>
## Implementation Decisions

### Output structure — Three-document architecture
- **D-01:** Phase 0 produces three separate YAML/MD files as core deliverables:
  - `hf_analysis.yaml` — Evolution of current `model_spec.yaml`; retains all existing fields plus new sections (fp32_modules, behavior_modifications, etc.)
  - `reference_impl_analysis.yaml` — NEW: Megatron/community side analysis; class signatures, __init__ members, forward flow, config fields for existing modules
  - `bridge_mapping.yaml` — NEW: Component-by-component bridge mapping (HF ↔ Megatron); the core deliverable that downstream phases consume
- **D-02:** `gap_decisions.md` — Human-readable record of components that cannot be 1:1 mapped, with decision rationale
- **D-03:** `slice_report.json` — Retained unchanged from current design
- **D-04:** Current `model_spec.yaml` is superseded by `hf_analysis.yaml`; the old name is retired to avoid confusion with the new three-document structure
- **D-05:** Current `reference_contract.yml` is absorbed into `bridge_mapping.yaml` (its `implementation_contract`, `conversion_requirements`, `phase3_reference_requirements` become subsections of bridge_mapping)

### Megatron analysis depth — Existing modules only
- **D-06:** Phase 0 analyzes Megatron/Community side to **existing module** depth: class signatures, __init__ members, forward flow signatures, config fields, weight parameter names
- **D-07:** Components that do NOT exist in Megatron (gaps) are recorded in `bridge_mapping.yaml` `gaps[]` with: HF component name, what's missing in Megatron, impact level (critical/high/medium), and suggested resolution scope (e.g., "requires new module in Megatron" or "implement in LoongForge model-specific code")
- **D-08:** Phase 0 does NOT design or specify the implementation of new Megatron modules — that is Phase 1's responsibility. Phase 0 only identifies the gap and its impact.

### Weight mapping — Conditional on Megatron coverage
- **D-09:** Phase 0 produces `weight_map` entries in `bridge_mapping.yaml` `component_bridge[]` ONLY for components where Megatron has a corresponding existing module
- **D-10:** For gap components (no Megatron counterpart), weight mapping is deferred to Phase 2. The `bridge_mapping.yaml` entry for that component will have `weight_map: null` and a note: "Deferred to Phase 2 — Megatron module does not exist yet"
- **D-11:** When Phase 0 produces weight_map, it includes: HF parameter name → Megatron parameter name, shape hints, and any known reshape/transposition requirements

### No-KB novel architecture — Best-effort + gaps
- **D-12:** When KB has no entry for the target model (e.g., DS V4 with mHC/CSA/HashRouter), Phase 0:
  1. Selects closest candidate via existing 3-path fallback (README hint → config.json → structural_tags)
  2. Marks `low_confidence_candidate: true` in `hf_analysis.yaml`
  3. Records each mismatched component in `bridge_mapping.yaml` `gaps[]` with explicit "candidate is inaccurate for this component" annotation
  4. Scans Megatron issue/PR references (from user-provided URLs) for implementation clues
- **D-13:** Phase 0 does NOT escalate to `human_needed` solely due to KB absence. It provides enough signal for Phase 1 to choose `adapt_ref`/`new_impl` over `reuse_ref`
- **D-14:** Auto-create KB stub is deferred to future work (Phase 5 or separate task)

### Phase 0 does NOT use Loop FSM
- **D-15:** Phase 0 is a read-only analysis phase. It does not write code to external repos, does not open PRs/issues, and does not participate in the 12-state FSM. Instead, it runs a **quality inner loop**: analyze → completeness check → (if incomplete) dig deeper on specific gaps → (max 3 rounds) → `human_needed` if still incomplete

### Bridge mapping schema — DS V4 validated structure
- **D-16:** `bridge_mapping.yaml` top-level structure (validated against DS V4 GT):

```yaml
model: <model_name>
hf_source: <modeling file>
megatron_family: <candidate family>

component_bridge:
  - hf: <HF class name>
    megatron: [<Megatron class/module reference>]
    strategy: reuse_ref | adapt_ref | new_impl
    confidence: high | medium | low
    weight_map:           # only when Megatron module exists
      - hf: <param_name> → megatron: <param_name>
    behavioral_diff:
      - topic: <description>
        hf: <HF behavior>
        megatron: <Megatron behavior>
        impact: critical | high | medium
        strategy: <guidance for Phase 1>
    delta: [...]          # structural differences (from current model_spec)

gaps:
  - id: <G1, G2, ...>
    component: <component name>
    hf: <HF class>
    megatron: <what exists or "NEW">
    decision: <resolution direction>
    impact: critical | high | medium
    phase1_guidance: <what Phase 1 should do>

validator_requirements:    # Phase 0 declares what downstream needs to verify
  - <structured check>
```

### hf-model-analyzer scope change
- **D-17:** The existing `hf-model-analyzer` skill remains responsible for Stage 1-3 of HF-side analysis (read source → identify components → compare with candidate → write `hf_analysis.yaml`)
- **D-18:** A NEW sub-skill or sub-agent `megatron-reference-analyzer` is responsible for analyzing the Megatron/community side: reading existing module code, extracting class signatures, __init__ members, forward flow, config fields
- **D-19:** A NEW step (Step 3.5 or "Bridge Step") combines `hf_analysis.yaml` + `reference_impl_analysis.yaml` to produce `bridge_mapping.yaml`. This step is deterministic (schema-driven mapping + gap detection), not agentic

### Claude's Discretion
- Exact schema field names and types for `bridge_mapping.yaml` and `reference_impl_analysis.yaml`
- How to handle the `reference_contract.yml` → `bridge_mapping.yaml` migration (backward compat vs clean cut)
- Whether `megatron-reference-analyzer` is a separate skill or a mode of `hf-model-analyzer`
- Inner loop iteration limit (3 rounds suggested, may need tuning)
- How to structure `phase0_output.yml` checks given the new three-document output

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 0 current implementation
- `skills/adapt/references/phases/phase0/agent.md` — Current Phase 0 agent manual (7-step state machine, input/output contracts)
- `skills/adapt/references/tools/hf-model-analyzer/SKILL.md` — Current HF analyzer skill (4-stage process, component identification, candidate selection, comparison)
- `skills/adapt/knowledge_base/schema/HF_SCAN_RULES.md` — File classification rules for Phase 0 Step 1
- `skills/adapt/knowledge_base/recipes/modeling_source_resolution.md` — Source resolution fallback chain

### Phase 0 output schemas and examples
- `skills/adapt/knowledge_base/examples/model_spec_llm.yaml` — Current LLM model_spec example (what's being superseded)
- `skills/adapt/knowledge_base/examples/model_spec_vlm.yaml` — Current VLM model_spec example
- `skills/adapt/references/phases/phase0/reference_contract_schema.yaml` — Current reference contract schema (being absorbed into bridge_mapping)
- `skills/adapt/references/phases/phase0/slice_report_schema.json` — Slice report schema (retained unchanged)

### Ground truth reference (DS V4 adaptation)
- `/Users/weizhihao/workspace/tmp_repo/0623/ground_truth/baidu/hac-aiacc/AIAK-Megatron/` — GT: Megatron-side implementation (15 changed files, latest commit e5b77017)
- `/Users/weizhihao/workspace/tmp_repo/0623/ground_truth/baidu/hac-aiacc/AIAK-Training-Omni/` — GT: LoongForge-side implementation (33 changed files, latest commit 3a16d140)
- Key GT files to validate bridge_mapping structure against:
  - `AIAK-Training-Omni/loongforge/models/foundation/deepseek_v4/` — Model-specific code (7 core files)
  - `AIAK-Training-Omni/configs/models/deepseek4/ckpt_convert/deepseek_v4_convert.yaml` — Weight name mapping (100+ entries)
  - `AIAK-Megatron/megatron/core/transformer/hyper_connection.py` — New mHC module
  - `AIAK-Megatron/megatron/core/transformer/experimental_attention_variant/dsa.py` — DSA/Indexer base
  - `AIAK-Megatron/megatron/core/transformer/moe/router.py` — Router extensions (hash, expert bias)

### External references
- `https://github.com/huggingface/transformers/tree/main/src/transformers/models/deepseek_v4` — HF DS V4 source (15 classes including mHC, CSA/HCA, Indexer, HashRouter)
- `https://github.com/NVIDIA/Megatron-LM/issues/4468` — Megatron DS V4 tracking issue (CSA/HCA, Hash MoE, mHC, ClampedSwiGLU, MTP)

### Downstream phase contracts
- `skills/adapt/knowledge_base/schema/EXIT_CONTRACT.md` — Phase exit semantics
- `skills/adapt/knowledge_base/schema/STEP_GATE.md` — Step gate enforcement
- `skills/adapt/references/phases/phase1/agent.md` — Phase 1 consumer of Phase 0 output
- `skills/adapt/references/phases/phase2/agent.md` — Phase 2 consumer (weight mapping)

### Architecture references
- `skills/adapt/references/loop_engineering/README.md` — P1-P21 principles mapping
- `.planning/PROJECT.md` — Core value, constraints, key decisions
- `.planning/REQUIREMENTS.md` — REQ-IDs and traceability

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `hf-model-analyzer` skill (Stages 1-3): Component identification, candidate selection, per-component comparison — all reusable for `hf_analysis.yaml` production
- `knowledge_base/sources/` YAML entries: Provide reference family definitions for candidate matching — can be extended to include Megatron-side module information
- `skills/adapt/lib/schema.py`: Pydantic v2 models for `RunInputs` and output validation — can be extended with new output schema models
- `skills/adapt/scripts/validate_phase_completion.py`: Phase gate logic — needs new checks for the three-document output
- `skills/adapt/knowledge_base/failure_patterns/phase0/`: Known failure patterns — can be extended with DS V4 specific patterns

### Established Patterns
- Append-only JSONL for `attempts.jsonl`: Not needed for Phase 0 (no FSM), but the quality inner loop could use a similar append-only progress log
- Pydantic v2 strict models for schema validation: Should be used for `bridge_mapping.yaml` and `reference_impl_analysis.yaml` schemas
- Step gate enforcement: The quality inner loop's completeness checks should follow the same `step_gate.mandatory_steps_complete` pattern

### Integration Points
- `phase0_output.yml` — Must be updated to reference the new three-document structure instead of single `model_spec.yaml`
- Phase 1 agent reads `model_spec.yaml` currently — must be updated to read `bridge_mapping.yaml` as primary input
- Phase 2 agent reads `weight_structure` from model_spec — must be updated to read `bridge_mapping.weight_map`
- `loongforge-phase-gate` — Must add checks for `bridge_mapping.yaml` existence and completeness
- `SKILL.md` — Must document the new Phase 0 output structure

</code_context>

<specifics>
## Specific Ideas

- "参考的代码无非就是两个（transformers库 + 其他开源社区代码例如megatron）" — user's framing of the dual-reference model
- DS V4 as the primary validation case: Phase 0 must be able to produce output that, when consumed by Phase 1-3, can lead to the GT code structure
- The GT `deepseek_v4_convert.yaml` (100+ weight mappings) is the benchmark for whether Phase 0's weight_map is sufficient
- The GT's two-repo division (AIAK-Megatron = generic infra, AIAK-Training-Omni = model-specific) should be reflected in how bridge_mapping separates "adapt existing module" vs "new module in gap"
- Megatron issue #4468 provides implementation clues for novel components — Phase 0 should be able to ingest this kind of external reference

</specifics>

<deferred>
## Deferred Ideas

- **Auto-create KB stub** for novel architectures — deferred to Phase 5 or separate task. Phase 0 marks `low_confidence_candidate` and records gaps instead.
- **Unified validator for Phase 0** — out of scope; the quality inner loop uses structural completeness checks, not GPU validators.
- **Megatron module implementation design** — Phase 0 only identifies gaps; designing new Megatron modules is Phase 1's job.
- **MTP handling for DS V4** — DS V4 explicitly ignores MTP weights; this is a model-specific detail that Phase 0 records but doesn't resolve.
- **Community implementation references beyond Megatron** (e.g., vLLM, DeepSpeed) — current scope is HF + Megatron only; can extend `reference_impl_analysis.yaml` format to support additional references in the future.

</deferred>

---

*Phase: 06-phase0-redesign*
*Context gathered: 2026-06-24*
