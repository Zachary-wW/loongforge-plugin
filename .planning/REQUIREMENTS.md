# REQUIREMENTS.md — Adapt Skill Loop-Engineering Refactor (v1)

Source: `.planning/PROJECT.md` Active requirements + `.planning/research/FEATURES.md` Table-Stakes mapping.
Date: 2026-06-22

---

## v1 Requirements

### Inputs

- [x] **INPUT-01** — Skill at startup collects four URL inputs: HF impl URL, ckpt+tokenizer URL, LoongForge repo URL, Loong-Megatron repo URL (with branch + optional subpath); each is validated for reachability and basic shape.
- [x] **INPUT-02** — `run_inputs.yml` extended with a top-level `repos:` block carrying all four URLs; downstream phases read from this single source.
- [x] **INPUT-03** — Pre-flight checks at startup: `gh auth status` OK, write permissions on both external repos, ckpt URL readable, branch protection rules dumped and asserted compatible with auto-merge — fail-fast with precise error otherwise.
- [x] **INPUT-04** — `loongforge-adapt --dry-run` flag wired from day one: when set, the entire FSM is driven against `FakeGhClient` with no live `gh` calls and no GPU validator invocation; preflight in dry-run mode skips remote-write checks but still validates URL shape + Pydantic schema. This is the substrate the local acceptance gate (ACC-01) runs on.

### Loop FSM

- [ ] **LOOP-01** — Implement explicit FSM `Probe → Edit → PR → Merge(base) → Validate → (Diagnose → Issue → Fix-PR → Review → Merge → Rerun)*` driven by a Python loop controller, callable per phase.
- [ ] **LOOP-02** — Validator-pass is the only positive exit; FSM exit reasons enumerated: `validator_passed | validator_passed_after_fix | exhausted | escalated | base_only | human_needed`.
- [ ] **LOOP-03** — Three-axis termination budget: `max_attempts_per_phase` (default 5), `max_attempts_per_run` (default 25), `max_wallclock_minutes` (default 240); breach forces `autonomous_blocked`/`human_needed` exit, never `passed`.
- [ ] **LOOP-04** — Diagnose step is a separate sub-agent distinct from Edit agent (maker ≠ checker, rpcx.io/12 P16); Diagnose is read-only and emits classification `code-bug | flaky | wrong-direction | needs-human`.
- [ ] **LOOP-05** — `wrong-direction` classification short-circuits the loop to `human_needed`, writing `phases/phaseN/escalation.md` with blockers + tried fixes.

### PR Lifecycle

- [x] **PR-01** — All adapt code changes land via `gh pr create` on either LoongForge or Loong-Megatron; direct push to default branch is forbidden.
- [x] **PR-02** — Base PR must be merged before any validator runs; merge uses `gh pr merge --squash` (or repo-default merge style).
- [x] **PR-03** — PR title/body/labels follow templated format containing `run_id`, `phase`, `attempt`, validator name, and a hidden `<!-- adapt-skill: ... -->` idempotency footer.
- [x] **PR-04** — Branch naming: `adapt/<run_id>/phase<N>/attempt<K>` on both external repos.
- [x] **PR-05** — Force-push to a branch that contains non-bot commits is forbidden; on detected human commit, loop pauses and posts a comment requesting `/agent-resume`.
- [x] **PR-06** — Validator-path edits (paths under `references/phases/phaseN/verify.md`, `loongforge-phase-gate`, validator scripts) are auto-rejected and converted to `human_needed` escalation.

### Issue Lifecycle

- [x] **ISSUE-01** — On validator failure (after rerun-for-flake threshold), open a `gh issue` containing structured `failure_signature`, log excerpt (last N lines + collapsed full log), `attempts.jsonl` link, and reproduction command.
- [x] **ISSUE-02** — Every issue is closed by a fix-PR carrying `Fixes #N`; merge of fix-PR auto-closes issue.
- [x] **ISSUE-03** — Issue dedup: same `(phase, validator_name, failure_signature)` reuses the open issue and appends a comment instead of opening a duplicate (basic version; advanced fingerprinting deferred).
- [x] **ISSUE-04** — All bot-created PRs/issues carry labels `loongforge-adapt`, `run-<id>`, `phase-<N>`; on run completion, auxiliary issues closed with summary linking digest.

### Validator Invocation

- [ ] **VAL-01** — Validator wrapper calls existing per-phase validators (`phase1-verify | phase2-conversion | loss-diff | feature-compat | kb-consistency`) on the merged HEAD; no validator logic is rewritten.
- [ ] **VAL-02** — Validators emit a `failure_signature: {kind, location, expected, actual}` structured record (or schema-equivalent). Free-text-only failures cause Diagnose to escalate, not guess.
- [ ] **VAL-03** — Phase 3 / Phase 4 near-threshold failures auto-rerun N times (default 3) before being treated as "real" failures; `attempts.jsonl` distinguishes `flaky` from `failed`.
- [ ] **VAL-04** — Validator integrity check: validator binary hash + log mtime ≥ attempt timestamp + log present in `phases/phaseN/logs/`. `loongforge-phase-gate` rejects `passed` if any check fails.
- [ ] **VAL-05** — Cross-repo coordination: LoongForge PR body must pin Megatron commit SHA; validator records `LOONG_MEGATRON_SHA` and refuses if mismatch.

### Logging & State

- [ ] **LOG-01** — Every loop transition appends one row to `phases/phaseN/attempts.jsonl` with `ts`, `attempt`, `kind`, `pr_url`, `issue_url`, `validator`, `verdict`, `exit_reason`, `event_id`.
- [x] **LOG-02** — `phaseN_output.yml` extended with optional `pr`, `issues`, `loop`, `loop_engineering: true` blocks; legacy outputs (no flag) still pass `loongforge-phase-gate` unchanged.
- [x] **LOG-03** — Append-only writes, no in-place edits to `attempts.jsonl`.

### Resume & Idempotency

- [ ] **RESUME-01** — `--resume <run_dir> [--from-phase N]` continues to work; controller reconstructs FSM state from last `attempts.jsonl` row plus `phaseN_output.yml`.
- [ ] **RESUME-02** — On resume, controller reconciles every PR/issue id against `gh`; mismatches force `--reset-phase N` rather than silent proceed.
- [x] **RESUME-03** — Idempotency keys (`sha256(run_id + phase + attempt + action_kind)`) prevent duplicate PR/issue creation across crash-resume.

### Safety

- [x] **SAFE-01** — Mandatory redaction filter on every body posted to GitHub: regex sweep for `Bearer `, `hf_`, `ghp_`, `AKIA`, `/home/<user>/`, internal domains; reject post if any pattern remains after redaction.
- [x] **SAFE-02** — `loop_controller.py` is a Python module — never invokes `/loop`; lint check fails build if `/loop` appears in skill code paths.
- [x] **SAFE-03** — Bulk log content externalized to files; only excerpts in chat context to avoid in-session bloat.

### Documentation

- [ ] **DOC-01** — `skills/adapt/SKILL.md` rewritten to describe the loop FSM, the four user inputs, the maker-checker split, termination budgets, and the "When NOT to use this loop" guard.
- [ ] **DOC-02** — New `skills/adapt/references/loop_engineering/README.md` cites se.rpcx.io/04, /08, /12 and maps each principle to the implementation.
- [ ] **DOC-03** — Each phase's `references/phases/phaseN/agent.md` updated with the two new bullets (pre-edit branch, post-edit PR) gated on `repos:` being present.
- [ ] **DOC-04** — End-of-run mandatory `phases/phaseN_summary.md` plus a per-run `comprehension_summary.md` (1 page) listing merged commits and one-line rationale.

### Compatibility

- [ ] **COMPAT-01** — Existing `loongforge-adapt <hf_path>` invocation without URL flags continues to produce a valid run dir; loop engineering is opt-in via `repos:` presence.
- [x] **COMPAT-02** — `run_state.json` legacy fields untouched; all new orchestration state lives in `run_inputs.yml` and `phaseN_output.yml`.
- [x] **COMPAT-03** — Existing Phase 0–5 validator and step-gate logic unchanged; new `_validate_loop_evidence()` in `validate_phase_completion.py` runs only when `loop_engineering: true` flag present.

### Tests

- [ ] **TEST-01** — pytest e2e covering `fail → diagnose → issue → fix-PR → review → merge → pass` on Phase 1 with mocked `gh` (FakeGhClient).
- [x] **TEST-02** — Snapshot tests on the redaction filter against a contrived secrets corpus.
- [x] **TEST-03** — Round-trip test for `run_inputs.yml v2` (with and without `repos:` block) exercising backward compat.
- [ ] **TEST-04** — Resume test: kill mid-Diagnose, re-invoke with `--resume`, assert no duplicate issue/PR created.

### Acceptance Handoff (local-only milestone target)

- [ ] **ACC-01** — Local milestone exit criterion is "plugin in runnable state": all pytest green, `loongforge-adapt --dry-run` (or equivalent) drives the full FSM against `FakeGhClient` without GPU; **no live `gh` calls and no GPU validators required to ship this milestone**.
- [ ] **ACC-02** — `skills/adapt/references/acceptance/ds_v4_runbook.md` exists, captures the exact GPU-machine invocation (HF impl URL, ckpt URL, LoongForge + Loong-Megatron repo URLs for DS V4), the community-version repo URL to diff against, and explicit pass criteria for the DS V4 acceptance run.
- [ ] **ACC-03** — Session/plugin portability: a `.planning/HANDOFF.md` lists what to copy to the GPU box (branch name, planning dir, skill paths) and how to resume there (`--resume` semantics, env vars, ckpt path expectations).

---

## Out of Scope

- Modifying LoongForge / Loong-Megatron business code (this milestone refactors plugin only)
- Replacing `loongforge-phase-gate` or any existing phase validator
- Adding new validation dimensions (perf, interpretability, etc.)
- Multi-run / multi-model parallel scheduler
- Custom GitHub App / webhooks / hosted endpoints
- Automatic merge to `main` / `loong-main/core_v0.15.0` in autonomous mode (must go via staging branch with human gate)
- Issue-fingerprint advanced dedup (only basic equality dedup in v1)

---

## Traceability

Mapped by `.planning/ROADMAP.md` on 2026-06-22. Coverage: 43/43 ✓ (no orphans, no duplicates).

| REQ-ID | Phase | Status |
|--------|-------|--------|
| INPUT-01 | Phase 1 | Complete |
| INPUT-02 | Phase 1 | Complete |
| INPUT-03 | Phase 1 | Complete |
| INPUT-04 | Phase 1 | Complete |
| LOOP-01 | Phase 3 | Pending |
| LOOP-02 | Phase 3 | Pending |
| LOOP-03 | Phase 3 | Pending |
| LOOP-04 | Phase 3 | Pending |
| LOOP-05 | Phase 3 | Pending |
| PR-01 | Phase 2 | Complete |
| PR-02 | Phase 2 | Complete |
| PR-03 | Phase 2 | Complete |
| PR-04 | Phase 2 | Complete |
| PR-05 | Phase 2 | Complete |
| PR-06 | Phase 2 | Complete |
| ISSUE-01 | Phase 2 | Complete |
| ISSUE-02 | Phase 2 | Complete |
| ISSUE-03 | Phase 2 | Complete |
| ISSUE-04 | Phase 2 | Complete |
| VAL-01 | Phase 3 | Pending |
| VAL-02 | Phase 3 | Pending |
| VAL-03 | Phase 3 | Pending |
| VAL-04 | Phase 3 | Pending |
| VAL-05 | Phase 3 | Pending |
| LOG-01 | Phase 3 | Pending |
| LOG-02 | Phase 1 | Complete |
| LOG-03 | Phase 1 | Complete |
| RESUME-01 | Phase 4 | Pending |
| RESUME-02 | Phase 4 | Pending |
| RESUME-03 | Phase 2 | Complete |
| SAFE-01 | Phase 1 | Complete |
| SAFE-02 | Phase 1 | Complete |
| SAFE-03 | Phase 1 | Complete |
| DOC-01 | Phase 5 | Pending |
| DOC-02 | Phase 5 | Pending |
| DOC-03 | Phase 4 | Pending |
| DOC-04 | Phase 5 | Pending |
| COMPAT-01 | Phase 4 | Pending |
| COMPAT-02 | Phase 1 | Complete |
| COMPAT-03 | Phase 1 | Complete |
| TEST-01 | Phase 4 | Pending |
| TEST-02 | Phase 1 | Complete |
| TEST-03 | Phase 1 | Complete |
| TEST-04 | Phase 4 | Pending |
