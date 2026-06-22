# SUMMARY.md — Research Synthesis

Project: Adapt Skill Loop-Engineering Refactor
Date: 2026-06-22

---

## TL;DR

Refactor `skills/adapt/` so every model adaptation runs as an explicit **loop**: `Probe → Edit → PR → Merge(base) → Validate → (Diagnose → Issue → Fix-PR → Review → Merge → Rerun)*` against two external repos (LoongForge + Loong-Megatron). Existing Phase 0–5 stay as the "EDIT" payload inside the loop. Loop discipline (gate, budget, maker-checker separation, escape hatch) follows se.rpcx.io 04/08/12.

## Stack & Methodology — Top Picks

- **Loop primitive:** external-process Python entrypoint, fork/exec `gh` per call, state on disk (`attempts.jsonl` + `loop_state.yml`). Reload state every iteration; never trust conversation memory.
- **GitHub:** `gh` CLI (>=2.55.0) ambient auth + `gh api` for JSON. Tenacity for transient `gh` failures only — never on validator failures.
- **Schemas:** Pydantic v2 for `run_inputs.yml v2`, `phaseN_output.yml`, normalized validator output.
- **Sub-agents:** **Edit agent ≠ Diagnose agent** (rpcx.io/12 P16). Diagnose is read-only, classifies failure as `code-bug | flaky | wrong-direction | needs-human`.
- **Templates:** Jinja2 markdown templates under `skills/adapt/loop_templates/phaseN/` — repair prompts are code, not literals.
- **Tests:** pytest + `FakeGhClient` interface; mock `gh` at the adapter boundary.
- **Hard NOs:** webhooks, GitHub Actions hosting, SQLite, asyncio, retrying validator failures, free-form Claude self-report as exit signal, `requests`+raw REST, daemon process.

## Architecture — Layered Plan

A. **Input Collection** — `run.py` extended with 4 URL flags → `run_inputs.yml.repos`
B. **Loop Controller (NEW)** — `skills/adapt/scripts/loop_controller.py` + new SKILL.md "Loop Engineering" section, owns FSM
C. **Phase Dispatcher** — existing `agents/adapt-phaseN.md`, internals untouched (only pre-edit / post-edit hook bullets added)
D. **GH Helpers (NEW)** — `skills/adapt/lib/gh_client.py` pure subprocess shim
E. **Validator Invocation** — `validate_phase_completion.py` extended additively, gated by `loop_engineering: true` flag
F. **State** — `run_inputs.yml` (extended), `phaseN_output.yml` (extended with `pr`/`issues`/`loop` blocks), `attempts.jsonl` (one line per loop iteration), `run_state.json` legacy passthrough

Critical path build order: **B1 (gh_helper) → B5 (controller skeleton) → B6 (SKILL.md section) → B8 (wire side-effects) → B11 (e2e pytest)**. Schema/CLI/hook additions fan out around it.

## Top P0/P1 Pitfalls (must address in roadmap)

1. **Fake "passed" exit** — validator log mtime check, hash check, evidence_uri required.
2. **Loop runaway** — three-axis budget (per-phase, per-run, wall-clock); breach → `autonomous_blocked` exit.
3. **Validator non-determinism** — auto-rerun N times before opening issue; deterministic CUDA flags; flaky vs failed distinction.
4. **Cross-repo PR deadlock** — explicit `depends_on` DAG; pin Megatron SHA in LoongForge PR.
5. **Idempotency on resume** — `Idempotency-Key` in PR/issue body; `create_or_get` helpers.
6. **Branch protection / auth scope** — preflight `gh api` probe; policy-reject ≠ code-reject.
7. **Secret leakage** — mandatory redaction filter on every body posted to GitHub.
8. **Maker == checker on validator** — write-protect validator paths; auto-reject any PR touching them.
9. **Comprehension debt** — mandatory `phaseN_summary.md` + KB update enforced by phase gate.

## Feature Coverage

23 Table-Stakes features map 1:1 to the user-mandated loop steps and PROJECT.md REQ-*:
- Inputs (TS-01..04), Loop FSM (TS-05), Edit/PR (TS-06..08), Validate/Diagnose/Issue/Fix (TS-09..14), Logging/Termination/Resume (TS-15..21), Tests/Docs (TS-22..23).

8 Differentiators deferred to next milestone (auto-link, dedup, status command, log-excerpt template, retry/backoff, metrics, replay-only, diff viewer).

12 Anti-features explicitly NOT built (webhooks, GitHub App, multi-run scheduler, validator replacement, business-code edits in this PR, new validation dimensions, maker=checker, unbounded retry, force-push rewrite, direct push, suppress-as-warning, free-form logging).

## Roadmap Implication — Suggested 5 Phases

1. **Loop Contracts & State Types** — Pydantic models, `run_inputs.yml v2` schema, normalized validator output, redactor lib, preflight checks (TS-01/02/03, schema parts of TS-15, prevention layer for Pitfalls 1/9).
2. **GitHub Helpers + Tests** — `gh_client.py`, idempotency keys, `FakeGhClient`, pytest harness (TS-06/07/08/11/12, TS-21, TS-22 scaffolding).
3. **Loop Controller + State Machine** — FSM with maker-checker split, three-axis budget, escalation, validator wrapper, diagnose classifier (TS-05, TS-09/10, TS-13, TS-16/17/18/19, Pitfalls 2/3/4/16).
4. **Wiring + Resume + e2e** — phase-agent hook bullets, SKILL.md "Loop Engineering" section, `--resume` integration, `validate_phase_completion.py` extension, full e2e test (TS-04, TS-14, TS-20, TS-22 e2e, Pitfalls 5/6/8).
5. **Documentation, KB, Run Finalization** — SKILL.md / phase manuals refresh, KB enforcement, run digest, label hygiene, `loongforge-loop-gate` example hook (TS-23, Pitfalls 11/12/14/17).

## Open Questions for Roadmap

- Default `max_attempts_per_phase` and `max_total_attempts`? (Suggested 5 / 25 — confirm during planning.)
- Branch protection rules on the two external repos? (Probe at preflight.)
- Auto-merge vs review-required for base PR? (Likely review-required for `main`, auto for staging branches.)
- Reviewer sub-agent (TS-13): reuse issue-loop reviewer (commit `95c916f`) verbatim or fork?
- Autonomous mode allowed to merge to `main`/`loong-main/core_v0.15.0` directly, or via `staging/run-<id>` only?

## Cross-Reference Map

| PROJECT.md REQ | Article principle | Pitfall | Feature |
|----------------|-------------------|---------|---------|
| REQ-INPUT-01/02 | P15 (state) | — | TS-01, TS-02 |
| REQ-LOOP-01 | P14, P17 | — | TS-05 |
| REQ-LOOP-02 | P3, P10, P18 | 1 | TS-09, TS-16 |
| REQ-LOOP-03 | P2, P4, P18 | 2, 19 | TS-17, TS-18, TS-19 |
| REQ-PR-01/02 | P8 | 5, 6, 7, 8 | TS-07, TS-08, TS-21 |
| REQ-ISSUE-01/02 | P12 | 6, 8, 9, 17 | TS-11, TS-12, DF-01, DF-02 |
| REQ-RERUN-01 | P3 | 1, 16 | TS-14 |
| REQ-LOG-01 | P1, P15 | 5, 6 | TS-15 |
| REQ-DOC-01/02 | P6, P20 | 12, 14 | TS-23 |
| REQ-COMPAT-01 | P5 | 5, 6 | TS-20, TS-21 |
| REQ-TEST-01 | (general) | (general) | TS-22 |
