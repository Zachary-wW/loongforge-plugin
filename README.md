# LoongForge Plugin for Claude Code

Plugin namespace: `loongforge`. A seven-phase closed-loop system for adapting HuggingFace models to LoongForge, driven by validators as the source of truth.

## Skills

| Skill | Description |
|-------|-------------|
| `/loongforge:adapt` | Seven-phase HF→LoongForge model adaptation with loop-engineering mode |
| `/loongforge:adapt_eval` | Qualification-gate eval: backup → re-adapt → verdict against `eval/SCOREBOARD` |

## Quick Start

```bash
# Legacy mode (no GitHub loop)
loongforge-adapt <hf_path> --model-name <name>

# Loop-engineering mode (repos: gated — closed-loop PR/issue/merge/validate cycle)
loongforge-adapt <hf_path> \
  --hf-impl-url <url> --hf-ckpt-url <url> \
  --loongforge-repo <url> --megatron-repo <url>

# Resume a run
loongforge-adapt --resume <run_dir> [--from-phase <N>]

# Phase completion gate
loongforge-phase-gate --run-dir <run_dir> --phase <N>
```

## Seven-Phase Flow

```
Phase 0 ──→ Phase 1 ──→ Phase 2 ──→ Phase 3 ──→ Phase 4 ──→ Phase 5 ──→ Phase 6
Bridge      Network     Weight       Loss         Perf         Feature      KB
Analysis    Construct   Convert      Diff         Tuning       Compat       Update
```

| Phase | Agent | Core Task | Exit Gate |
|-------|-------|-----------|-----------|
| 0 | `adapt-phase0` | Dual-reference bridge analysis + checkpoint slicing | Three-document output checks |
| 1 | `adapt-phase1` | Omni network construction + random-init sanity | `phase1-verify` |
| 2 | `adapt-phase2` | Weight conversion + production checkpoint verification | `phase2-conversion` |
| 3 | `adapt-phase3` | Real-weight loss diff verification | `loss-diff` |
| 4 | `adapt-phase4` | Performance profiling and tuning (nsys + perf-tuner) | `performance-tuning` |
| 5 | `adapt-phase5` | Feature switch + combination verification | `feature-compat` |
| 6 | `adapt-phase6` | Knowledge base update | `kb-consistency` |

**Phase 0** produces three deliverables consumed by all downstream phases:
- `hf_analysis.yaml` — HF-side architecture analysis
- `reference_impl_analysis.yaml` — Megatron-side module signatures
- `bridge_mapping.yaml` — Component-by-component bridge mapping with weight maps and gap detection

**Cross-phase transition** is gated by user confirmation (`[CHECKPOINT]`) unless `autonomous_mode: true`.

## Loop-Engineering Architecture

When `repos:` is present in `run_inputs.yml`, the skill operates as a closed-loop system: every code change goes through PR → merge → validate → fix cycles on external GitHub repos until all phase validators pass.

### Three Nested Loops

| Layer | Scope | Coordination Bus |
|-------|-------|-------------------|
| **Inner** | Phase-internal self-repair | Disk files (`attempts.jsonl`) |
| **Middle** | GitHub PR/issue cycle (12-state FSM) | GitHub (`gh` CLI) |
| **Outer** | Multi-model replay (future) | Run directory |

The loop does not adapt the model — it adapts the plugin's own bugs out.

### 12-State FSM (Middle Loop)

```
PROBE → EDIT → PR → MERGE_BASE → VALIDATE
    → (DIAGNOSE → ISSUE → FIX_PR → REVIEW → MERGE_FIX → RERUN)*
    → EXIT
```

The FSM is **re-entrant**: state lives on disk (`loop_state.yml` + `attempts.jsonl`), never in conversation context. Each invocation reloads from disk.

**Exit reasons:** `validator_passed` | `validator_passed_after_fix` | `exhausted` | `escalated` | `base_only` | `human_needed` | `fix_needed`

### Maker-Checker Split

Edit/PR-author and Diagnose are **distinct sub-agents**:
- **Edit agent**: writes code, creates PRs
- **Diagnose agent**: read-only — classifies failures as `code-bug | flaky | wrong-direction | needs-human`

`wrong-direction` (3+ consecutive same-failure attempts) short-circuits to `human_needed`.

### Three-Axis Budget

| Axis | Default | Ceiling |
|------|---------|---------|
| Per-phase attempts | 5 | 50 |
| Per-run total attempts | 25 | 500 |
| Wall-clock minutes | 240 | 10,080 |

Budget is checked **before** processing validator results. If breached, exit is always `exhausted`/`human_needed`, never `passed`.

## CLI Wrappers

```bash
loongforge-adapt <hf_path> [options]
loongforge-adapt --resume <run_dir> [--from-phase <N>]
loongforge-phase-gate --run-dir <run_dir> --phase <N>
loongforge-adapt-eval <family> --hf-path <path> [--steps 10] [--keep-deleted]
```

## Validation Gate

`loongforge-phase-gate` checks whether a phase has a passed output artifact. It is deterministic and checks passed phase completion only — it does not run runtime validators or agentic reviews.

```bash
loongforge-phase-gate --run-dir <run_dir> --phase <N>
```

Do not invoke it for `human_needed` or `autonomous_blocked` checkpoints.

## State Files

Authoritative:

```text
run_inputs.yml
phases/phaseN_output.yml
phases/phaseN/attempts.jsonl
phases/phaseN/loop_state.yml       # FSM state (loop-engineering mode only)
```

Legacy compatibility only:

```text
run_state.json
phases/phaseN/output.yml
```

## Project Layout

```
skills/adapt/
├── SKILL.md                     # Operational guide (reading order starts here)
├── lib/                         # Python helper modules
│   ├── loop_controller.py       # 12-state FSM spine
│   ├── validator_wrapper.py     # Validator invocation + integrity + flake rerun
│   ├── diagnose_classifier.py   # Read-only failure classification
│   ├── gh_client.py             # GhClient Protocol + Real/Fake implementations
│   ├── schema.py                # Pydantic v2 models
│   ├── resume.py                # Resume reconciliation
│   └── ...                      # preflight, templates, redact, idempotency, etc.
├── references/phases/phaseN/    # Phase agent manuals
├── knowledge_base/              # Domain references, templates, failure patterns
├── loop_templates/phaseN/       # Versioned repair prompt templates
├── scripts/                     # CLI wrappers
└── tests/                       # 428+ pytest tests
```
