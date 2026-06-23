# Phase 05: Documentation, KB & Run Finalization - Context

**Gathered:** 2026-06-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Produce all documentation and finalization artifacts that make the refactored adapt skill self-describing and ready for GPU-handoff. No new runtime behavior, no new FSM states. Everything Phases 1-4 built now gets described in user-facing docs, validated through a local acceptance gate, and packaged for GPU-machine portability.

This is the last mile: DOC-01 (SKILL.md rewrite), DOC-02 (loop_engineering/README.md), DOC-04 (comprehension_summary + per-phase summaries), ACC-01 (local acceptance gate), ACC-02 (DS V4 GPU runbook), ACC-03 (HANDOFF.md).

</domain>

<decisions>
## Implementation Decisions

### SKILL.md Rewrite Scope
- **D-01:** Preserve existing "how each phase runs" sections (Reading Order, Phase Dispatch Rules, Checkpoint Protocol, Bulk Log Externalization, Autonomous Mode) — these describe mechanics that haven't changed. Rewrite the top-level framing to surface the loop-first architecture: 12-state FSM, repos: gated behavior, maker-checker split, three-axis budget, GitHub as coordination bus, "When NOT to use" guard. The rewrite is surgical: keep phase mechanics, replace architecture framing.

### comprehension_summary.md Depth
- **D-02:** Medium depth: commit list + FSM path summary (states visited, attempt count per phase, which validator failed/passed). Derivable from disk state (loop_state.yml + attempts.jsonl). Richer narrative ("what was wrong and how fixed") risks exceeding 1-page limit for multi-phase runs. Per-phase `phaseN_summary.md` follows the same template: phase number, validator outcome, attempts count, key decision log (from decision_log.md if exists).

### ACC-01 Dry-Run Gap
- **D-03:** Declare ACC-01 met by: (a) all pytest green (311+ tests already prove full FSM cycle against FakeGhClient), (b) `test_loop_e2e.py` IS the proof that fail→diagnose→issue→fix-PR→merge→rerun→pass works end-to-end without GPU. Adding a separate dry-run integration test is redundant with unit test coverage. The `--dry-run` flag is for user convenience, not acceptance. No code changes needed to validator_wrapper.py for ACC-01.

### DS V4 Runbook Format
- **D-04:** Narrative document ("here's how to run DS V4 acceptance step by step") with structured invocation command + expected output + pass criteria sections. Community-version diff target URL left as `TODO: <community-repo-URL>` placeholder — user will fill in when available. Known URLs from PROJECT.md: HF impl `transformers/models/deepseek_v4`, ckpt `deepseek-ai/DeepSeek-V4-Flash-Base`, LoongForge `Zachary-wW/LoongForge`, Loong-Megatron `Zachary-wW/Loong-Megatron` branch `loong-main/core_v0.15.0`.

### User-Provided Canonical Reference
- **D-05:** The user has drafted `docs/loop-engineering-in-practice.md` — a three-layer loop framing (Inner: phase-internal self-repair, Middle: GitHub PR/issue cycle, Outer: multi-model replay). This doc captures the "plugin itself is what the loop fixes" insight and "GitHub as bus" architecture. Content should be integrated into DOC-01 (SKILL.md) framing and DOC-02 (loop_engineering/README.md). The doc is NOT yet on disk — researcher/planner should treat the user's shared content as the canonical source.

### Claude's Discretion
- Exact SKILL.md section ordering and heading names
- Template strings for comprehension_summary.md and phaseN_summary.md
- Label color schemes for bot PRs/issues (already established in Phase 2)
- HANDOFF.md formatting and env var naming
- Whether to create docs/loop-engineering-in-practice.md as a separate file or merge its content entirely into SKILL.md + loop_engineering/README.md

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 5 Target Files (rewrite or create)
- `skills/adapt/SKILL.md` (164 lines) — DOC-01 rewrite target; existing sections to preserve listed in D-01
- `skills/adapt/references/loop_engineering/README.md` — DOC-02 net-new; cite se.rpcx.io/04, /08, /12

### Source Material for Documentation
- `skills/adapt/lib/loop_controller.py` (673 lines) — FSM implementation: 12 states, ExitReason enum, LoopState dataclass, run_phase_loop signature
- `skills/adapt/lib/gh_client.py` (720 lines) — GhClient Protocol, FakeGhClient state machine, view_pr/view_issue
- `skills/adapt/lib/diagnose_classifier.py` — Maker-checker: DiagnoseClassification enum, classify_failure
- `skills/adapt/lib/validator_wrapper.py` — ValidatorResult, FailureSignature, run_validator, check_validator_integrity
- `skills/adapt/lib/resume.py` — reconcile_remote_state, reconcile_run, ReconciliationMismatch
- `skills/adapt/lib/schema.py` — LoopBudget, ReposBlock, PrBlockOutput, IssuesBlockOutput
- `skills/adapt/scripts/run.py` (483 lines) — CLI entry point, --dry-run, --resume wiring
- `skills/adapt/references/phases/phase{0..5}/agent.md` — All 6 now have Loop Engineering Hooks sections

### Principle-to-Implementation Mapping (for DOC-02)
- `.planning/research/STACK.md` — Loop-engineering principles P1..P21 with implementation mapping table
- `CLAUDE.md` lines 8-120 — Part 1 table: P1..P21 with "Application" column mapping to concrete code
- `docs/loop-engineering-in-practice.md` — User-drafted three-layer loop narrative (NOT on disk yet; user shared content is canonical)

### Data Sources for comprehension_summary (DOC-04)
- `phases/phaseN/loop_state.yml` — FSM state, attempt count, exit_reason per phase
- `phases/phaseN/attempts.jsonl` — Full attempt history
- `phases/phaseN_output.yml` — Validator outcome, PR/issues blocks
- `phases/phaseN/decision_log.md` — Decision records (if created during loop)
- `skills/adapt/knowledge_base/LOG.md` (41 lines) — Existing append-only event log format

### Acceptance Artifacts
- `.planning/REQUIREMENTS.md` — ACC-01, ACC-02, ACC-03 definitions
- `.planning/PROJECT.md` — "验收分两层" section: local acceptance (runnable plugin) vs GPU acceptance (separate session)
- `skills/adapt/references/phases/phase5/phase5_output_schema.yaml` (81 lines) — Output schema with summary fields
- `skills/adapt/references/phases/phase5/extraction_rules.yaml` (177 lines) — KB extraction rules

### Test Baseline
- `skills/adapt/tests/lib/test_loop_e2e.py` — 4 E2E tests proving full FSM cycle against FakeGhClient
- `skills/adapt/tests/lib/test_compat.py` — 8 compat tests proving legacy invocation unaffected
- Full suite: 311 tests green as of Phase 4 completion

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `skills/adapt/SKILL.md` (164 lines): Existing section structure (Reading Order, Phase Dispatch, Checkpoint Protocol, Bulk Log Externalization, Autonomous Mode) is still valid — D-01 says preserve these
- `skills/adapt/knowledge_base/LOG.md` (41 lines): Append-only event log format — provides pattern for comprehension_summary timestamps
- `skills/adapt/knowledge_base/INDEX.md` (136 lines): KB index structure — may need update per DOC-04
- `skills/adapt/lib/loop_controller.py`: LoopState.from_disk(run_dir, phase) + persist() — can be used to generate FSM path summary for comprehension_summary
- `skills/adapt/lib/jsonl.py`: read_jsonl helper — can read attempts.jsonl for summary generation

### Established Patterns
- Documentation files are Markdown under `skills/adapt/references/` or `skills/adapt/` root
- Test files in `skills/adapt/tests/lib/test_*.py` using FakeGhClient
- Phase output schemas in `skills/adapt/references/phases/phaseN/phaseN_output_schema.yaml`
- SKILL.md frontmatter: name, description fields

### Integration Points
- SKILL.md is the primary entry point invoked as `/loongforge:adapt` — DOC-01 rewrite must preserve frontmatter
- `references/loop_engineering/` is a new directory — needs creation
- `references/acceptance/` is a new directory — needs creation
- `.planning/HANDOFF.md` is a new file — needs creation at project root planning dir
- comprehension_summary.md generation: either a Python helper or a template with manual fill — Claude's discretion per D-02

</code_context>

<specifics>
## Specific Ideas

- The user's draft `docs/loop-engineering-in-practice.md` frames three nested loops (Inner/Middle/Outer). This framing should appear prominently in the rewritten SKILL.md (DOC-01) and be the organizing principle for loop_engineering/README.md (DOC-02)
- "Plugin itself is what the loop fixes" — this insight from the user's doc is the key mental model that SKILL.md should convey. The loop doesn't adapt the model; it adapts the plugin's own bugs out
- "GitHub as bus" — not in-session loop, but cross-session, cross-process with GitHub as coordination layer. This distinguishes this loop from Claude Code SDK's in-session agent loop
- comprehension_summary.md should be generated at run completion (or on demand via `--resume` when all phases are done). Data comes from loop_state.yml + attempts.jsonl per phase

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 05-documentation-kb-run-finalization*
*Context gathered: 2026-06-23*
