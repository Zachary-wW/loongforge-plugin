# FEATURES.md — Adapt Skill Loop-Engineering Refactor

Domain: Loop-engineering driven adapter workflow with GitHub PR/issue feedback loop
Researched: 2026-06-22
Confidence: HIGH (cross-verified with PROJECT.md REQ-* and se.rpcx.io 04/08/12)

## User-Mandated Loop (anchor for traceability)

```
Probe inputs → Edit code → Submit PR → Merge(base) → Run validator
   └─ if fail ─→ Diagnose → Open issue → Fix PR → Review → Merge → Rerun validator
   └─ if pass ─→ next phase / exit
```

Steps used as `loop_step` tags below: `INPUT, PROBE, EDIT, PR, MERGE_BASE, VALIDATE, DIAGNOSE, ISSUE, FIX_PR, REVIEW, MERGE_FIX, RERUN, EXIT`.

---

## Table Stakes (loop breaks if missing)

| ID | Feature | loop_step | Complexity | Depends on | REQ |
|----|---------|-----------|------------|------------|-----|
| TS-01 | Four-input ingestion (HF impl URL, ckpt+tokenizer URL, LoongForge repo URL, Loong-Megatron repo URL) | INPUT | S | — | REQ-INPUT-01 |
| TS-02 | `run_inputs.yml` schema extension to persist the four URLs | INPUT | S | TS-01 | REQ-INPUT-02 |
| TS-03 | Input pre-flight checks (gh auth, write perms on both external repos, ckpt readable) | INPUT | S | TS-01 | Constraints |
| TS-04 | Probe step (HF parse + reference contract extraction) reused from Phase 0/1 | PROBE | S | TS-02 | — |
| TS-05 | Loop state machine controller | all | L | TS-02, TS-06..TS-13 | REQ-LOOP-01 |
| TS-06 | Code-edit step bound to a working branch on the target external repo | EDIT | M | TS-03 | — |
| TS-07 | PR creation helper using `gh pr create` with templated title/body/labels | PR | M | TS-06 | REQ-PR-01/02 |
| TS-08 | Base-PR merge step (`gh pr merge --squash`) before validate | MERGE_BASE | S | TS-07 | — |
| TS-09 | Validator invocation wrapper (calls existing phase validators on merged HEAD) | VALIDATE | M | TS-08 | — |
| TS-10 | Validator-fail diagnosis step (parses validator output → structured failure record) | DIAGNOSE | M | TS-09 | — |
| TS-11 | Issue creation helper (`gh issue create` with fail context, attempts.jsonl link, repro cmd) | ISSUE | M | TS-10 | REQ-ISSUE-01 |
| TS-12 | Fix-PR helper that links issue (`Fixes #N`) and re-uses TS-07 plumbing | FIX_PR | S | TS-07, TS-11 | REQ-ISSUE-02 |
| TS-13 | Review gate before fix-PR merge (sub-agent reviewer, distinct from maker) | REVIEW | M | TS-12 | rpcx.io/12 P16 |
| TS-14 | Fix-PR merge + auto-rerun of the failing validator | MERGE_FIX, RERUN | S | TS-13, TS-09 | REQ-RERUN-01 |
| TS-15 | Per-iteration attempt log row in `phases/phaseN/attempts.jsonl` | all | S | TS-05 | REQ-LOG-01 |
| TS-16 | Termination: validator-pass → loop exits with checkpoint | EXIT | S | TS-09, TS-15 | REQ-LOOP-02 |
| TS-17 | Termination: max-attempts ceiling per phase (hard cap) | EXIT | S | TS-15 | REQ-LOOP-03 |
| TS-18 | Termination: total wall-clock / total-PR budget (run-level cap) | EXIT | S | TS-15 | REQ-LOOP-03 |
| TS-19 | Escalation exit: emit `human_needed` checkpoint with full context when caps hit | EXIT | S | TS-17, TS-18 | rpcx.io/12 P19 |
| TS-20 | Resume from any loop step (`--resume <run_dir> [--from-phase N]`) | all | M | TS-15 | REQ-COMPAT-01 |
| TS-21 | Idempotent PR/issue creation (search-before-create by run_id+phase+attempt label) | PR, ISSUE | M | TS-07, TS-11, TS-20 | — |
| TS-22 | Sub-agent test fixture covering one full fail→issue→fix-PR→pass cycle (mocked `gh`) | all | M | TS-05..TS-14 | REQ-TEST-01 |
| TS-23 | SKILL.md / phase manuals / KB updated to reference loop FSM and the four inputs | docs | S | TS-05 | REQ-DOC-01/02 |

## Differentiators (improve velocity / observability)

| ID | Feature | loop_step | Value | Complexity | Depends on |
|----|---------|-----------|-------|------------|------------|
| DF-01 | Bidirectional auto-link issue ↔ fix-PR ↔ attempt row | ISSUE, FIX_PR | One-click traceability | S | TS-11, TS-12, TS-15 |
| DF-02 | Issue dedup across reruns (fingerprint validator failure → reuse open issue) | DIAGNOSE, ISSUE | Avoids issue spam on flaky failures | M | TS-10, TS-11 |
| DF-03 | Attempt diff viewer (`loongforge-adapt diff <run_dir> --phase N --attempt K`) | observability | Local CLI to inspect | M | TS-15 |
| DF-04 | Loop dashboard / status command (`loongforge-adapt status <run_dir>`) | observability | Single view of FSM state | M | TS-15, TS-17, TS-18 |
| DF-05 | PR/issue body templated to embed validator log excerpt | PR, ISSUE | Reviewer doesn't context-switch | S | TS-07, TS-11 |
| DF-06 | Configurable retry/backoff on transient `gh` failures | PR, ISSUE, MERGE | Distinguishes infra flake from real failure | S | TS-07, TS-11 |
| DF-07 | Loop-level metrics emission (attempts/phase, time-in-state, gh API count) | observability | Future tuning | M | TS-15 |
| DF-08 | "Replay last failure" affordance — re-run validator only, without new PR | RERUN | Useful when fix is suspected flake | S | TS-09 |

## Anti-Features (explicitly NOT built)

| ID | Feature | Why Excluded |
|----|---------|--------------|
| AF-01 | GitHub webhooks for event-driven loop progression | PROJECT.md Out-of-Scope; needs hosted endpoint |
| AF-02 | Custom GitHub App with elevated permissions | PROJECT.md Out-of-Scope; ownership/security overhead |
| AF-03 | Multi-run / multi-model parallel scheduler | PROJECT.md Out-of-Scope; state model is per-run_dir |
| AF-04 | Replacing or rewriting any phase validator | PROJECT.md Out-of-Scope; validators are ground truth |
| AF-05 | Modifying LoongForge / Loong-Megatron business code from this PR | PROJECT.md Out-of-Scope; this milestone refactors plugin only |
| AF-06 | Adding new validation dimensions (perf, interpretability) | PROJECT.md Out-of-Scope |
| AF-07 | Same agent both edits code and approves merge | rpcx.io/12: maker == checker is canonical anti-pattern |
| AF-08 | Unbounded retry / "keep trying until it passes" | rpcx.io/04: explicit max-attempts mandatory |
| AF-09 | Force-push / squash-rewriting an already-merged PR | Destroys traceability; attempts.jsonl refs would dangle |
| AF-10 | Direct `git push` to default branch, bypassing PR | User-mandated loop says all changes go through PR |
| AF-11 | Burying validator failures as warnings | rpcx.io/12: failure must surface; suppression = comprehension debt |
| AF-12 | Free-form natural-language attempt logging | Breaks resume (TS-20) and dedup (DF-02); machine-unparseable |

## Feature Dependencies

```
TS-01 (4 inputs)
   └─ TS-02 (run_inputs.yml schema)
        └─ TS-03 (preflight)
             └─ TS-05 (loop FSM) ────────────────────────────────────┐
                  ├─ TS-04 (probe / phase0+1 reuse)                  │
                  ├─ TS-06 (working branch)                          │
                  │    └─ TS-07 (PR helper) ── TS-21 (idempotent)    │
                  │         └─ TS-08 (merge base)                    │
                  │              └─ TS-09 (validator wrapper)        │
                  │                   ├─ pass → TS-16 (exit ok)      │
                  │                   └─ fail → TS-10 (diagnose)     │
                  │                        └─ TS-11 (issue) ── DF-02 │
                  │                             └─ TS-12 (fix PR)    │
                  │                                  └─ TS-13 (review) ── AF-07 forbidden
                  │                                       └─ TS-14 (merge+rerun) → back to TS-09
                  ├─ TS-15 (attempts.jsonl)  ◄── all transitions write here
                  │    └─ TS-20 (resume)
                  │    └─ DF-03 / DF-04 / DF-07 (observability)
                  ├─ TS-17 / TS-18 (caps)
                  │    └─ TS-19 (escalation)
                  └─ TS-22 (loop tests)
TS-23 (docs) ──documents──> TS-05 + cites se.rpcx.io 04/08/12
```

## MVP Definition

### Launch With (this milestone)
All Table Stakes TS-01 through TS-23. Each maps to a REQ-* in PROJECT.md or to a step the user explicitly enumerated, or to a loop-engineering invariant from se.rpcx.io 12.

### Add After Validation (next milestone)
- DF-01 auto-link (cheap once TS-11/TS-12 exist)
- DF-04 status command (high observability ROI)
- DF-05 templated body with log excerpt
- DF-06 gh retry/backoff (after observing real flake rate)

### Future Consideration
- DF-02 issue dedup
- DF-03 attempt diff viewer
- DF-07 metrics emission
- DF-08 replay-validator-only

## Loop-Step Coverage Check

| Loop step | Backing feature(s) |
|-----------|---------------------|
| Probe inputs | TS-01, TS-02, TS-03, TS-04 |
| Edit code | TS-06 |
| Submit PR | TS-07, TS-21, DF-05, DF-06 |
| Merge base | TS-08 |
| Run validator | TS-09 |
| Diagnose | TS-10 |
| Open issue | TS-11, TS-21, DF-01, DF-02, DF-05 |
| Fix PR | TS-12, DF-01 |
| Review | TS-13 (anti: AF-07) |
| Merge | TS-14 |
| Rerun validator | TS-14, TS-09, DF-08 |
| Repeat / terminate | TS-05, TS-15, TS-16, TS-17, TS-18, TS-19, TS-20 |

Every step has at least one backing Table-Stakes feature. ✓

## Termination / Safety Coverage

- Per-phase max attempts: TS-17
- Run-level wall-clock + total-PR budget: TS-18
- Validator-pass exit: TS-16
- Escalation to human with full context when caps hit: TS-19
- Idempotent re-entry on resume: TS-20 + TS-21
- Append-only audit trail of every transition: TS-15

## Sources

- `.planning/PROJECT.md` — REQ-* table — HIGH (authoritative)
- `skills/adapt/SKILL.md` (current state) — HIGH
- https://se.rpcx.io/04.html — HIGH — primitives: max-iterations cap, completion promise, state file, OR-semantic exit, escape hatch
- https://se.rpcx.io/08.html — HIGH — primitives: pipeline stages with gates, contract-driven handoff, advisory review, idempotent fs state
- https://se.rpcx.io/12.html — HIGH — primitives: automation trigger, isolation, reusable Skill, connector, maker/checker, persistent state, gate-or-token-furnace, triage-inbox escalation
- Repo prior art: commit 95c916f (independent reviewer sub-agent + verdict schema) — directly applicable to TS-13

## Open Questions

- Default value for max-attempts per phase (suggest 5; needs user confirmation in roadmap)
- Whether base-PR merge (TS-08) should require green CI on external repo, or only successful `gh pr merge`
- Whether reviewer sub-agent (TS-13) reuses the issue-loop reviewer schema verbatim or needs adapt-specific verdict fields
