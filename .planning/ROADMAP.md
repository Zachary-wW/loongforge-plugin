# ROADMAP — Adapt Skill Loop-Engineering Refactor

Granularity: **coarse** (7 phases)
Mode: yolo · parallelization: true
Source: `.planning/REQUIREMENTS.md` (v1) + `.planning/research/SUMMARY.md` "Suggested 5 Phases" + `.planning/research/ARCHITECTURE.md` §5 build order
Created: 2026-06-22

---

## Phases

- [x] **Phase 1: Loop Foundation — Contracts, Schemas & Safety Plumbing** — Inputs, schema extensions, preflight, redactor, additive validator hooks; no loop behavior yet
- [x] **Phase 2: GitHub Helpers — PR & Issue Lifecycle** — `gh_client.py`, idempotency keys, branch/label/template policy, validator-path write-protection
- [x] **Phase 3: Loop Controller — FSM, Budgets & Validator Discipline** — Probe→Edit→PR→Merge→Validate→Diagnose FSM with maker-checker split, three-axis budget, structured failure signature, flake handling, cross-repo SHA pinning
- [x] **Phase 4: Wiring — Phase Agents, Resume & E2E** — Pre/post-edit hooks in phase agents, `--resume` remote reconciliation, full `fail→fix→pass` pytest e2e
- [x] **Phase 5: Documentation, KB & Run Finalization** — SKILL.md rewrite, `loop_engineering/README.md` citing rpcx.io 04/08/12, per-run comprehension summary, label hygiene
- [x] **Phase 6: Phase 0 Redesign — Dual-Reference Bridge Analysis** — Redesign Phase 0 from single-side HF analysis to three-document output (hf_analysis.yaml, reference_impl_analysis.yaml, bridge_mapping.yaml) with Megatron-side analysis, deterministic bridge mapping, gap detection, and quality inner loop
- [x] **Phase 7: Phase 1 Redesign — Dual-Repo Consumption, Generation & Verification** — Redesign Phase 1 to consume bridge_mapping as primary input, support dual-repo code generation (LoongForge + Megatron), add perf guard rails, strengthen verification with HF sanity run and shared-seed init, integrate Loop FSM exit path
- [ ] **Phase 8: Phase 2+3 Redesign — Weight Conversion & Loss-Diff Bridge Consumption** — Redesign Phase 2 and Phase 3 agent.md to consume bridge_mapping as primary input, support dual-repo file consumption, migrate from deprecated reference_contract_path/model_spec_path
- [ ] **Phase 9: Phase 4+5 Redesign — Feature Compat & KB Bridge Consumption** — Redesign Phase 4 and Phase 5 agent.md to consume bridge_mapping/hf_analysis, add Megatron file paths to KB extraction

---

## Phase Details

### Phase 1: Loop Foundation — Contracts, Schemas & Safety Plumbing
**Goal**: A run can collect the four URL inputs, persist them in extended schemas, pre-flight against GitHub (or skip in `--dry-run`), and any text bound for external repos passes through a hardened redactor — all without touching loop behavior. `FakeGhClient` interface is in place from day one so later phases can be developed and tested offline. Establishes plumbing later phases layer on without rewriting.
**Depends on**: Nothing (foundation phase; maps to ARCHITECTURE B1/B2/B3)
**Requirements**: INPUT-01, INPUT-02, INPUT-03, INPUT-04, LOG-02, LOG-03, SAFE-01, SAFE-02, SAFE-03, COMPAT-02, COMPAT-03, TEST-02, TEST-03
**Success Criteria** (what must be TRUE):
  1. Running `loongforge-adapt --hf-impl-url ... --hf-ckpt-url ... --loongforge-repo ... --megatron-repo ...` produces a `run_inputs.yml` containing the new `repos:` and `loop:` blocks; a legacy invocation without those flags still produces a valid run dir (COMPAT-02 round-trip).
  2. Pre-flight fails fast with a precise error when `gh auth status` is not OK, write permissions on either external repo are missing, the ckpt URL is unreachable, or branch protection rules are incompatible with auto-merge.
  3. Pydantic v2 models reject `run_inputs.yml` v2 missing required `repos.*.url` fields and accept legacy v1 inputs unchanged; the round-trip test (TEST-03) passes for both shapes.
  4. Redaction filter strips `Bearer `, `hf_`, `ghp_`, `AKIA`, `/home/<user>/`, and configured internal-domain patterns from any string before any GitHub post; snapshot tests (TEST-02) against a contrived secrets corpus match expected output and a residual secret causes post-rejection.
  5. `validate_phase_completion.py` continues to pass legacy `phaseN_output.yml` without the `loop_engineering` flag (COMPAT-03), and the new `_validate_loop_evidence()` extension is callable but inert when the flag is absent; `attempts.jsonl` writes are append-only with no in-place edits (LOG-03).
  6. `--dry-run` flag and `GhClient` interface are wired (INPUT-04): `loongforge-adapt --dry-run` produces a valid run dir with `repos:`/`loop:` blocks, preflight skips live-write probes but enforces URL shape + Pydantic schema, and a `FakeGhClient` stub (interface only, behavior fleshed out in Phase 2) is selected when `--dry-run` is present. This is the substrate the Phase 5 local-acceptance gate (ACC-01) runs on.
**Plans**: 4 plans
- [x] 01-PLAN.md — Foundation libs: schema, jsonl, protected_paths, redact, pydantic dep (Wave 1)
- [x] 02-PLAN.md — GhClient (Protocol + RealGhClient stub + FakeGhClient) + run_preflight (Wave 1)
- [x] 03-PLAN.md — CLI extension: 8 URL flags + --dry-run + repos/loop blocks + preflight wire-up (Wave 2)
- [x] 04-PLAN.md — Validator hook (_validate_loop_evidence inert) + /loop lint + SAFE-03 doc note (Wave 2)

### Phase 2: GitHub Helpers — PR & Issue Lifecycle
**Goal**: A maker agent can branch, open, label, and merge PRs and issues against both external repos through a single typed adapter, with idempotency keys and policy guards (validator-path write-protection, force-push refusal) that survive crashes.
**Depends on**: Phase 1 (uses redactor + repos schema)
**Requirements**: PR-01, PR-02, PR-03, PR-04, PR-05, PR-06, ISSUE-01, ISSUE-02, ISSUE-03, ISSUE-04, RESUME-03
**Success Criteria** (what must be TRUE):
  1. `gh_client.py` exposes `create_branch`, `open_pr`, `merge_pr`, `open_issue`, `close_issue`, and `find_by_idempotency_key`; each call records a `sha256(run_id+phase+attempt+action_kind)` footer and re-invocation with the same key returns the existing artifact rather than creating a duplicate (RESUME-03).
  2. PRs are created on branch `adapt/<run_id>/phase<N>/attempt<K>` (PR-04) with title/body/labels matching the templated format containing `run_id`, `phase`, `attempt`, validator name, and `<!-- adapt-skill: ... -->` footer (PR-03); every fix-PR carries `Fixes #N` linkage (ISSUE-02); direct push to default branch is refused (PR-01); merge uses `gh pr merge --squash` and base PR must merge before any validator runs (PR-02).
  3. Any PR diff touching paths under `references/phases/phaseN/verify.md`, `loongforge-phase-gate`, or validator scripts is auto-rejected and converted to a `human_needed` escalation (PR-06); force-push to a branch containing non-bot commits is refused — the helper detects human commits via `git log --format=%ae` and posts an `/agent-resume` comment instead (PR-05).
  4. Issue creation contains structured `failure_signature`, log excerpt + collapsed full log, `attempts.jsonl` link, and reproduction command (ISSUE-01); same `(phase, validator_name, failure_signature)` reuses the open issue and appends a comment instead of duplicating (ISSUE-03); every fix-PR closes its issue on merge (ISSUE-02).
  5. All bot-created PRs/issues carry labels `loongforge-adapt`, `run-<id>`, `phase-<N>`; opening, commenting on, closing, and re-finding artifacts each work end-to-end against `FakeGhClient` in pytest (ISSUE-04).
**Plans**: 2 plans
- [ ] 01-PLAN.md — Idempotency module + template module (Wave 1)
- [ ] 02-PLAN.md — RealGhClient lifecycle + FakeGhClient state machine + test suite (Wave 2)

### Phase 3: Loop Controller — FSM, Budgets & Validator Discipline
**Goal**: A Python loop controller drives `Probe → Edit → PR → Merge(base) → Validate → (Diagnose → Issue → Fix-PR → Review → Merge → Rerun)*` per phase with hard budgets, maker-checker separation, validator-integrity checks, and structured failure signatures — exiting only on a verifiable validator-pass or a bounded escalation. This is the FSM spine.
**Depends on**: Phase 1 (schemas), Phase 2 (gh helpers)
**Requirements**: LOOP-01, LOOP-02, LOOP-03, LOOP-04, LOOP-05, VAL-01, VAL-02, VAL-03, VAL-04, VAL-05, LOG-01
**Success Criteria** (what must be TRUE):
  1. The controller's only positive exit is `validator_passed` / `validator_passed_after_fix` (LOOP-02); any of the three budget axes (`max_attempts_per_phase=5`, `max_attempts_per_run=25`, `max_wallclock_minutes=240`) tripping forces exit reason `exhausted` / `human_needed` and never `passed` (LOOP-03).
  2. Diagnose runs as a read-only sub-agent distinct from the Edit/PR-author agent (LOOP-04, maker ≠ checker per rpcx.io/12 P16); Diagnose emits classification `code-bug | flaky | wrong-direction | needs-human` and `wrong-direction` short-circuits to `human_needed` with `phases/phaseN/escalation.md` written listing blockers and tried fixes (LOOP-05).
  3. Validator wrapper enforces all three integrity properties: (a) calls existing per-phase validators on the merged HEAD without rewriting them (VAL-01), (b) rejects free-text-only failures and requires structured `failure_signature: {kind, location, expected, actual}` (VAL-02), (c) verifies validator binary hash + log mtime ≥ attempt timestamp + log present in `phases/phaseN/logs/`; `loongforge-phase-gate` rejects `passed` if any check fails (VAL-04).
  4. Phase 3/Phase 4 near-threshold failures auto-rerun N=3 times before being treated as real failures; `attempts.jsonl` distinguishes `flaky` from `failed` (VAL-03); LoongForge PR body pins a Megatron commit SHA, the validator records and asserts `LOONG_MEGATRON_SHA`, and SHA mismatch refuses validation rather than reporting a false code failure (VAL-05).
  5. Every loop transition appends exactly one row to `phases/phaseN/attempts.jsonl` containing `ts`, `attempt`, `kind`, `pr_url`, `issue_url`, `validator`, `verdict`, `exit_reason`, and `event_id` (LOG-01); FSM is fully driven by re-reading disk state, never in-memory conversation (LOOP-01).
**Plans**: 2 plans
- [x] 03-01-PLAN.md — Validator wrapper + Diagnose classifier + repair template + VAL-04 hook (Wave 1)
- [x] 03-02-PLAN.md — FSM loop controller with budget enforcement and state persistence (Wave 2)

### Phase 4: Wiring — Phase Agents, Resume & E2E
**Goal**: The loop is wired into existing phase agents through pre-edit/post-edit hook bullets, `--resume` reconciles local state with remote PR/issue state, and an end-to-end pytest exercises a complete `fail → diagnose → issue → fix-PR → review → merge → pass` cycle on Phase 1.
**Depends on**: Phase 3 (controller exists), Phase 2 (gh helpers exist)
**Requirements**: COMPAT-01, RESUME-01, RESUME-02, DOC-03, TEST-01, TEST-04
**Success Criteria** (what must be TRUE):
  1. Each `agents/adapt-phaseN.md` (N=0..5) carries the two new bullets — pre-edit branch creation via `gh_helper.create_branch`, post-edit `gh_helper.open_pr` writing PR URL into `phaseN_output.yml.pr` — gated on `repos:` being present in `run_inputs.yml`; legacy invocations without `repos:` skip the bullets without error (DOC-03).
  2. `loongforge-adapt --resume <run_dir> [--from-phase N]` reconstructs FSM state from the last `attempts.jsonl` row plus `phaseN_output.yml` (RESUME-01); every PR/issue id is reconciled against `gh` and any mismatch (404, merge SHA drift, force-push) forces `--reset-phase N` rather than silent proceed (RESUME-02).
  3. Killing the controller mid-Diagnose and re-invoking with `--resume` produces zero duplicate issues or PRs; the idempotency-key search-before-create path (TEST-04) reattaches to the existing artifact.
  4. `pytest skills/adapt/tests/test_loop_e2e.py` runs a full `fail → diagnose → issue → fix-PR → review → merge → pass` cycle on Phase 1 against `FakeGhClient` and exits green (TEST-01).
  5. A run launched via the legacy `loongforge-adapt <hf_path>` invocation without URL flags continues to produce a valid run dir, no `pr`/`issues`/`loop` blocks are written, and `loongforge-phase-gate` accepts the legacy outputs unchanged (COMPAT-01 backward-compat smoke test).
**Plans**: 2 plans
- [x] 04-01-PLAN.md — Resume reconciliation infrastructure: view_pr/view_issue on GhClient + lib/resume.py + run.py wiring (Wave 1)
- [x] 04-02-PLAN.md — Phase agent hook bullets + E2E cycle test + COMPAT-01 smoke test (Wave 1)

### Phase 5: Documentation, KB & Run Finalization
**Goal**: SKILL.md, phase manuals, and the loop-engineering reference cite the actual implementation; every run ends with a comprehension summary so users understand what merged and why; bot artifacts are housekept so the issue tracker stays readable across runs. Also produces the GPU-machine handoff so DS V4 acceptance can be driven there.
**Depends on**: Phase 4 (implementation must exist before docs reference it)
**Requirements**: DOC-01, DOC-02, DOC-04, ACC-01, ACC-02, ACC-03
**Success Criteria** (what must be TRUE):
  1. `skills/adapt/SKILL.md` is rewritten to describe the loop FSM, the four user inputs (`repos:` block), the maker-checker split (Edit ≠ Diagnose), the three-axis termination budget, and a "When NOT to use this loop" guard listing trivial-fix and no-validator cases (DOC-01).
  2. `skills/adapt/references/loop_engineering/README.md` exists, cites se.rpcx.io/04, /08, /12 with quoted principles, and maps each principle (P1..P21) to a concrete implementation file/function in this skill (DOC-02).
  3. End-of-run produces `phases/phaseN_summary.md` for every executed phase plus a single per-run `comprehension_summary.md` (≤1 page) listing every merged commit and one-line rationale (DOC-04).
  4. On run completion, all auxiliary bot-created issues are closed with a summary comment linking the run digest, and bot PRs/issues consistently carry `loongforge-adapt`, `run-<id>`, `phase-<N>` labels — verified by an end-of-run housekeeping pass that exits non-zero on any unlabeled or stranded artifact.
  5. **Local-acceptance gate (ACC-01)**: `pytest skills/adapt/tests/` green AND a `loongforge-adapt --dry-run --hf-impl-url ... --hf-ckpt-url ... --loongforge-repo ... --megatron-repo ...` invocation drives the FSM end-to-end against `FakeGhClient` with **no live `gh` calls and no GPU** — this is the local milestone exit criterion.
  6. **GPU handoff artifacts**: `skills/adapt/references/acceptance/ds_v4_runbook.md` (ACC-02) captures the DS V4 invocation, community-version diff target, and pass criteria; `.planning/HANDOFF.md` (ACC-03) lists what to copy to the GPU box and how to `--resume` there.
**Plans**: 2 plans
- [x] 05-01-PLAN.md — Core documentation: SKILL.md surgical rewrite (DOC-01) + loop_engineering/README.md P1-P21 mapping (DOC-02)
- [x] 05-02-PLAN.md — Summary generator + acceptance artifacts: summary_generator.py (DOC-04) + ds_v4_runbook.md (ACC-02) + HANDOFF.md (ACC-03) + ACC-01 verification

### Phase 6: Phase 0 Redesign — Dual-Reference Bridge Analysis
**Goal**: Redesign Phase 0 from single-side HF analysis to dual-reference bridge mapping. Phase 0 produces three core deliverables: hf_analysis.yaml (HF side), reference_impl_analysis.yaml (Megatron/community side), bridge_mapping.yaml (component-by-component bridge mapping with weight maps and gap detection). Phase 0 uses a quality inner loop (max 3 rounds) instead of the Loop FSM. Downstream Phase 1/2 consume bridge_mapping.yaml as their primary input.
**Depends on**: Phase 1-5 (builds on existing schema patterns and validation infrastructure)
**Requirements**: P0R-01 (three-document output), P0R-02 (Megatron existing-module analysis), P0R-03 (conditional weight mapping), P0R-04 (no-KB best-effort + gaps), P0R-05 (quality inner loop), P0R-06 (bridge mapping schema), P0R-07 (hf-model-analyzer retained), P0R-08 (megatron-reference-analyzer), P0R-09 (bridge step deterministic)
**Success Criteria** (what must be TRUE):
  1. Phase 0 produces hf_analysis.yaml preserving all current model_spec.yaml fields plus new sections (fp32_modules, behavior_modifications), reference_impl_analysis.yaml with Megatron module class signatures/init/forward/config/weights, and bridge_mapping.yaml with component_bridge entries linking every HF component to a Megatron module or a gap.
  2. Bridge_mapping.yaml gap entries have non-empty phase1_guidance and correct impact levels (critical/high/medium). Weight_map entries are populated for components where Megatron has a module; null for gaps (deferred to Phase 2).
  3. Megatron-reference-analyzer SKILL.md defines a 4-stage read-only analysis process: module discovery, signature extraction, config class analysis, and output writing — no code generation or implementation design.
  4. Phase 0 agent.md defines a 9-step state machine with quality inner loop (max 3 rounds, not FSM). Bridge step (Step 5.5) is deterministic schema-driven mapping, not agentic.
  5. validate_phase_completion.py checks all three new output files exist and bridge_mapping has non-empty component_bridge and gap entries with guidance.
  6. Phase 1 and Phase 2 agent.md input contracts reference bridge_mapping_path as primary input (with legacy model_spec_path fallback). reference_contract_schema.yaml has deprecation notice.
**Plans**: 3 plans
- [x] 06-01-PLAN.md — Three-document schemas (Pydantic v2 + YAML templates) + Phase 0 agent.md rewrite (Wave 1)
- [ ] 06-02-PLAN.md — Megatron reference analyzer skill + example YAML files + KB extension (Wave 1)
- [x] 06-03-PLAN.md — Validation gate update + downstream Phase 1/2 contract updates + deprecation notes (Wave 2)

### Phase 7: Phase 1 Redesign — Dual-Repo Consumption, Generation & Verification
**Goal**: Redesign Phase 1 to correctly consume Phase 0's three-document output, support dual-repo code generation (LoongForge + Megatron), add performance guard rails, strengthen verification with HF sanity run and shared-seed initialization, and explicitly integrate the Loop FSM exit path.
**Depends on**: Phase 6 (Phase 0 three-document output must exist), Phase 1-5 (loop infrastructure)
**Requirements**: P1R-01 (bridge_mapping primary input), P1R-02 (dual-repo generation), P1R-03 (perf guard rails), P1R-04 (verification rigor), P1R-05 (confidence-driven validation), P1R-06 (FSM exit path)
**Success Criteria** (what must be TRUE):
  1. Phase 1 agent.md uses bridge_mapping_path as primary input (model_spec_path is legacy fallback only). Step 1 extracts component_bridge, gaps, and validator_requirements from bridge_mapping.yaml. reference_impl_analysis.yaml is loaded as Megatron architecture context.
  2. Step 2 uses confidence-driven 3-level validation: confidence=high → adopt Phase 0 strategy + skip 2c; confidence=medium → simplified 2c on behavioral_diff parts; confidence=low → full 2c; gap → Step 2d Megatron gap module design (no 2c).
  3. Step 3 generates code for BOTH LoongForge and Megatron repositories. Output includes generated_loongforge_files and generated_megatron_files. Megatron modifications follow PROTECTED_FILES.md rules (append-only, no behavior change for other models).
  4. Step 3 enforces perf guard rails (P1-P8) from references/phases/phase1/perf_rules.yaml alongside existing G1-G14. Violation signals are blocking errors, not warnings.
  5. Step 7 verification uses shared-seed initialization (not independent random init): initialize HF model with fixed seed → dump parameters → set into LoongForge model. All input tensors (input_ids, attention_mask, position_ids, labels) are fixed and identical on both sides.
  6. Phase 1 verification includes HF Sanity Run (confirm HF transformers can load and forward) and Example Script Dry Run (confirm generated example script is executable with valid parameters).
  7. Phase 1 agent.md explicitly describes the Loop FSM exit path: repos: present → commit to branch → validate → pass = PR + merge / fail = exit to loop_controller. repos: absent → local repair loop.
  8. phase1_output_schema.yaml updated with bridge_mapping_consumed, generated_megatron_files, strategy_overrides recording Phase 0 → Phase 1 strategy changes, hf_sanity_run_passed, example_script_dry_run_passed.
  9. validate_phase_completion.py includes Phase 1 checks for bridge_mapping consumption and perf lint execution.
**Plans**: 3 plans
- [x] 07-01-PLAN.md — Core agent.md rewrite + strategy_rules.yaml confidence rules (Wave 1)
- [x] 07-02-PLAN.md — perf_rules.yaml + verify.md rewrite + phase1_output_schema.yaml extension (Wave 1)
- [x] 07-03-PLAN.md — validate_phase_completion.py Phase 1 checks + megatron_preread_checklist.yaml restructuring (Wave 2)

### Phase 8: Phase 2+3 Redesign — Weight Conversion & Loss-Diff Bridge Consumption
**Goal**: Redesign Phase 2 and Phase 3 agent.md to consume bridge_mapping as primary input (replacing model_spec_path/reference_contract_path), support dual-repo file consumption (generated_loongforge_files + generated_megatron_files), and align output schemas with the new Phase 0/1 artifact structure.
**Depends on**: Phase 7 (Phase 1 redesign must be complete so Phase 2/3 consume the new output format)
**Requirements**: P2R-01 (bridge_mapping primary for weight_map), P2R-02 (dual-repo generated_files consumption), P2R-03 (convert_yaml reads from bridge_mapping), P3R-01 (reference_contract_path → bridge_mapping migration), P3R-02 (phase3_reference_requirements from bridge_mapping)
**Success Criteria** (what must be TRUE):
  1. Phase 2 agent.md uses bridge_mapping_path as primary input for weight name mapping; model_spec_path is legacy fallback. Step 1 reads bridge_mapping.component_bridge[].weight_map as the authoritative name map, not just a hint.
  2. Phase 2 Input Contract reads generated_loongforge_files + generated_megatron_files (split lists) from Phase 1 output, not the flat generated_files list.
  3. Phase 2 output schema adds bridge_mapping_consumed field and source.bridge_mapping_path.
  4. Phase 3 agent.md replaces reference_contract_path with bridge_mapping_path as primary input. Step 0 reads bridge_mapping.implementation_contract and bridge_mapping.conversion_requirements instead of reference_contract.phase3_reference_requirements.
  5. Phase 3 output schema adds source.bridge_mapping_path; reference_contract_path is deprecated/nullable.
  6. validate_phase_completion.py has Phase 2 and Phase 3 checks for bridge_mapping_consumed.
  7. All 428+ existing tests continue to pass.
**Plans**: 3 plans
- [x] 08-01-PLAN.md — Phase 2 agent.md rewrite + phase2_output_schema.yaml (Wave 1)
- [x] 08-02-PLAN.md — Phase 3 agent.md rewrite + phase3_output_schema.yaml (Wave 1)
- [ ] 08-03-PLAN.md — validate_phase_completion.py Phase 2+3 checks (Wave 2)

### Phase 9: Phase 4+5 Redesign — Feature Compat & KB Bridge Consumption
**Goal**: Redesign Phase 4 and Phase 5 agent.md to consume bridge_mapping/hf_analysis for structure tags and component data, and add Megatron file paths to KB extraction logic.
**Depends on**: Phase 7 (Phase 1 redesign), Phase 8 (Phase 2/3 redesign for output contract stability)
**Requirements**: P4R-01 (structure tags from bridge_mapping/hf_analysis), P5R-01 (KB reads from hf_analysis + bridge_mapping), P5R-02 (Megatron code_paths in KB)
**Success Criteria** (what must be TRUE):
  1. Phase 4 Step 2 reads bridge_mapping.yaml or hf_analysis.yaml for structure tags (is_llm, is_moe, is_dense) instead of model_spec.yaml.
  2. Phase 5 Input Contract replaces direct model_spec.yaml read with hf_analysis.yaml + bridge_mapping.yaml.
  3. Phase 5 reads generated_loongforge_files + generated_megatron_files from Phase 1 output.
  4. Phase 5 extraction_rules.yaml and source_templates updated to include Megatron file paths in code_paths.
  5. Phase 5 output schema adds source.bridge_mapping_path and source.hf_analysis_path.
  6. validate_phase_completion.py has Phase 4 and Phase 5 checks for bridge_mapping_consumed.
  7. All 428+ existing tests continue to pass.
**Plans**: 2 plans
- [x] 09-01-PLAN.md — Phase 4 agent.md + phase4_output_schema.yaml + validate_phase_completion.py Phase 4 checks (Wave 1)
- [x] 09-02-PLAN.md — Phase 5 agent.md + extraction_rules.yaml + source_templates + phase5_output_schema.yaml + validate_phase_completion.py Phase 5 checks (Wave 1)

---

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Loop Foundation | 4/4 | Complete | 2026-06-22 |
| 2. GitHub Helpers | 2/2 | Complete | 2026-06-22 |
| 3. Loop Controller | 2/2 | Complete | 2026-06-22 |
| 4. Wiring & E2E | 2/2 | Complete | 2026-06-22 |
| 5. Docs & Finalization | 2/2 | Complete | 2026-06-22 |
| 6. Phase 0 Redesign | 3/3 | Complete | 2026-06-24 |
| 7. Phase 1 Redesign | 3/3 | Complete | 2026-06-24 |
| 8. Phase 2+3 Redesign | 0/3 | Planned |  |
| 9. Phase 4+5 Redesign | 0/2 | Planned |  |

---

## Coverage

- **Total v1 requirements**: 47 (original) + 9 (Phase 6 new) + 6 (Phase 7 new) + 5 (Phase 8 new) = 67
- **Mapped**: 67/67
- **Orphans**: 0
- **Duplicates**: 0

| REQ | Phase |
|-----|-------|
| INPUT-01 | 1 |
| INPUT-02 | 1 |
| INPUT-03 | 1 |
| INPUT-04 | 1 |
| LOOP-01 | 3 |
| LOOP-02 | 3 |
| LOOP-03 | 3 |
| LOOP-04 | 3 |
| LOOP-05 | 3 |
| PR-01 | 2 |
| PR-02 | 2 |
| PR-03 | 2 |
| PR-04 | 2 |
| PR-05 | 2 |
| PR-06 | 2 |
| ISSUE-01 | 2 |
| ISSUE-02 | 2 |
| ISSUE-03 | 2 |
| ISSUE-04 | 2 |
| VAL-01 | 3 |
| VAL-02 | 3 |
| VAL-03 | 3 |
| VAL-04 | 3 |
| VAL-05 | 3 |
| LOG-01 | 3 |
| LOG-02 | 1 |
| LOG-03 | 1 |
| RESUME-01 | 4 |
| RESUME-02 | 4 |
| RESUME-03 | 2 |
| SAFE-01 | 1 |
| SAFE-02 | 1 |
| SAFE-03 | 1 |
| DOC-01 | 5 |
| DOC-02 | 5 |
| DOC-03 | 4 |
| DOC-04 | 5 |
| COMPAT-01 | 4 |
| COMPAT-02 | 1 |
| COMPAT-03 | 1 |
| TEST-01 | 4 |
| TEST-02 | 1 |
| TEST-03 | 1 |
| TEST-04 | 4 |
| ACC-01 | 5 |
| ACC-02 | 5 |
| ACC-03 | 5 |
| P0R-01 | 6 |
| P0R-02 | 6 |
| P0R-03 | 6 |
| P0R-04 | 6 |
| P0R-05 | 6 |
| P0R-06 | 6 |
| P0R-07 | 6 |
| P0R-08 | 6 |
| P0R-09 | 6 |
| P1R-01 | 7 |
| P1R-02 | 7 |
| P1R-03 | 7 |
| P1R-04 | 7 |
| P1R-05 | 7 |
| P1R-06 | 7 |
| P4R-01 | 9 |
| P5R-01 | 9 |
| P5R-02 | 9 |

| P2R-01 | 8 |
| P2R-02 | 8 |
| P2R-03 | 8 |
| P3R-01 | 8 |
| P3R-02 | 8 |

---

## Parallelization Notes

Per `config.json` (`parallelization: true`) and ARCHITECTURE.md §5:

- **Phase 1** internal parallelism: schema extensions (B2), redactor lib (part of B1 foundation), preflight CLI (B4), and doc skeleton (B3) are independent and can run concurrently.
- **Phase 2** depends on Phase 1's `repos:` schema and redactor; internally `gh_client.py` primitives are independent, idempotency layer wraps them.
- **Phase 3** depends on Phases 1–2; FSM skeleton (pure state) and validator-wrapper (gh-dependent) can develop in parallel.
- **Phase 4** wiring fans out across six phase-agent files (mechanical edits) in parallel; resume + e2e test sequential.
- **Phase 5** doc-only; safe to draft in parallel with Phase 4 finalization. Both plans are Wave 1 (no inter-plan dependencies, no file overlap).
- **Phase 6** Plan 01 (schemas + agent.md) and Plan 02 (analyzer + examples) are Wave 1 with no file overlap — can run parallel. Plan 03 depends on Plan 01 for schema field names.
- **Phase 7** Plan 01 (agent.md + strategy_rules.yaml) and Plan 02 (perf_rules.yaml + verify.md + phase1_output_schema.yaml) are Wave 1 with no file overlap — can run parallel. Plan 03 depends on Plan 01 and Plan 02 for schema field names and check specifications.

Critical path: **B1 (gh_helper) → B5 (controller) → B6 (SKILL.md hook) → B8 (wire) → B11 (e2e)** spans Phases 2 → 3 → 4.

### Phase 10: Integrate nsys-profiler and performance-tuner as new Phase 4, renumber Feature Compat to Phase 5 and KB Update to Phase 6

**Goal:** Insert a new Phase 4 (Performance Tuning) between Loss Diff (Phase 3) and Feature Compat (now Phase 5), orchestrating nsys-profiler for profiling and performance-tuner for optimization. Renumber the current Phase 4 (Feature Compat) to Phase 5 and current Phase 5 (KB Update) to Phase 6. Update all code, schemas, validators, and tests to reflect the 7-phase structure.
**Requirements**: PH4-01 (new Phase 4 agent + schema), PH4-02 (performance-tuning validator), PH4-03 (FLAKE_RERUN_PHASES update), PH5-RENUM (Phase 4 -> 5 renumbering), PH6-RENUM (Phase 5 -> 6 renumbering + phase4_status), TEST-UPD (test updates)
**Depends on:** Phase 9
**Plans:** 1/3 plans executed

Plans:
- [x] 10-01-PLAN.md — New Phase 4 content + directory moves + agent files (Wave 1)
- [ ] 10-02-PLAN.md — Code + doc updates: validators, range(7), SKILL.md, EXIT_CONTRACT.md, schema_version (Wave 2)
- [ ] 10-03-PLAN.md — Test updates for 7-phase structure (Wave 3)

---

## References

- `.planning/PROJECT.md` — vision, constraints, key decisions
- `.planning/REQUIREMENTS.md` — REQ-IDs and traceability
- `.planning/research/SUMMARY.md` — synthesized research summary, source of "Suggested 5 Phases"
- `.planning/research/ARCHITECTURE.md` — integration points (IP-1..IP-10), build order (B1..B13), schema deltas
- `.planning/research/STACK.md` — loop-engineering principles P1..P21, toolchain picks, hard NOs
- `.planning/research/PITFALLS.md` — 19 P0/P1/P2 pitfalls keyed to phases
- `.planning/research/FEATURES.md` — Table-Stakes TS-01..23 mapped to loop steps
