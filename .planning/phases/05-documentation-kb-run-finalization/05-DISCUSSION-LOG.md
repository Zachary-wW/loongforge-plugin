# Phase 05: Documentation, KB & Run Finalization - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-23
**Phase:** 05-documentation-kb-run-finalization
**Areas discussed:** SKILL.md rewrite scope, comprehension_summary depth, ACC-01 dry-run gap, DS V4 runbook specifics

---

## SKILL.md Rewrite Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Rewrite from scratch | Discard existing 164 lines, write entirely new | |
| Surgical insert | Add new FSM/budget/repos sections, keep existing unchanged | |
| Preserve mechanics, rewrite framing | Keep Phase Dispatch/Checkpoint/Autonomous sections, replace top-level architecture framing | ✓ |

**User's choice:** Preserve mechanics, rewrite framing (recommended)
**Notes:** Existing "how each phase runs" sections are still valid. The top-level framing (what this skill does, how the loop works) needs complete replacement to surface FSM, repos: gating, maker-checker split, budgets, GitHub-as-bus architecture.

---

## comprehension_summary.md Depth

| Option | Description | Selected |
|--------|-------------|----------|
| Thin | Commit list + pass/fail status per phase only | |
| Medium | Commit list + FSM path summary (states visited, attempt count, validator outcomes) | ✓ |
| Rich | Medium + narrative ("what was wrong, how fixed") from attempts.jsonl + escalation.md | |

**User's choice:** Medium (recommended)
**Notes:** FSM path is the most valuable signal for run reviewers. Richer narrative risks exceeding 1-page limit for multi-phase runs. Data derivable from loop_state.yml + attempts.jsonl.

---

## ACC-01 Dry-Run Gap

| Option | Description | Selected |
|--------|-------------|----------|
| Mock validator in dry-run | Add dry_run=True path to validator_wrapper.py returning configurable result | |
| Declare ACC-01 met by existing tests | 311 pytest green + test_loop_e2e.py proves full FSM against FakeGhClient = acceptance | ✓ |
| Add --skip-validator flag | Pure FSM walk-through without validator (scope creep for Phase 5) | |

**User's choice:** Declare ACC-01 met by existing tests (recommended)
**Notes:** test_loop_e2e.py IS the proof that fail→diagnose→issue→fix-PR→merge→rerun→pass works end-to-end without GPU. Adding a separate dry-run integration test is redundant. --dry-run is user convenience, not acceptance.

---

## DS V4 Runbook Specifics

| Option | Description | Selected |
|--------|-------------|----------|
| Structured checklist | Command → expected output → pass criteria in table format | |
| Narrative walkthrough | Step-by-step prose with invocation, expected output, pass criteria sections | ✓ |
| Placeholder only | Just URL TODOs, fill in later | |

**User's choice:** Narrative walkthrough
**Notes:** Community-version diff target URL left as TODO placeholder. Known URLs from PROJECT.md: HF impl transformers/models/deepseek_v4, ckpt deepseek-ai/DeepSeek-V4-Flash-Base, LoongForge Zachary-wW/LoongForge, Loong-Megatron Zachary-wW/Loong-Megatron branch loong-main/core_v0.15.0.

---

## User-Provided Canonical Reference

The user shared content from a draft `docs/loop-engineering-in-practice.md` — a three-layer loop framing document (Inner: phase-internal self-repair, Middle: GitHub PR/issue cycle, Outer: multi-model replay). Key insights captured:
- "Plugin itself is what the loop fixes"
- "GitHub as bus" — cross-session, cross-process coordination
- "You stop being the prompter; you design the loop that prompts the agents"

This content should be integrated into DOC-01 (SKILL.md) and DOC-02 (loop_engineering/README.md). File is NOT yet on disk — user's shared content is the canonical source.

---

## Claude's Discretion

- Exact SKILL.md section ordering and heading names
- Template strings for comprehension_summary.md and phaseN_summary.md
- HANDOFF.md formatting and env var naming
- Whether to create docs/loop-engineering-in-practice.md as separate file or merge entirely into SKILL.md + loop_engineering/README.md

---

## Deferred Ideas

None — discussion stayed within phase scope.
