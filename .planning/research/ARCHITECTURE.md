# ARCHITECTURE.md — Adapt Skill Loop-Engineering Refactor

Mode: Brownfield architecture mapping
Researched: 2026-06-22
Confidence: HIGH (all claims grounded in file evidence)

---

## 1. Current Architecture (file-evidence based)

### 1.1 Component map

```
User CLI
  │
  ▼
bin/loongforge-adapt        ──► skills/adapt/scripts/run.py        (init/resume runner; NO phase exec)
bin/loongforge-phase-gate   ──► skills/adapt/scripts/validate_phase_completion.py  (deterministic gate)

Skill entrypoint:  skills/adapt/SKILL.md  (160 lines — orchestration manual for the model-driven main agent)

Phase agents (top-level Claude Code agents, not nested in skill):
  agents/adapt-phase0.md ── reads references/phases/phase0/agent.md ── owns phases/phase0/
  agents/adapt-phase1.md ── reads references/phases/phase1/agent.md  + verify.md
  agents/adapt-phase2.md ── reads references/phases/phase2/agent.md  + verify.md
  agents/adapt-phase3.md ── reads references/phases/phase3/agent.md  + loss_diff.md
  agents/adapt-phase4.md ── reads references/phases/phase4/agent.md
  agents/adapt-phase5.md ── reads references/phases/phase5/agent.md

Validators (invoked INSIDE phase agents, not by top-level orchestrator):
  phase1-verify | phase2-conversion | loss-diff | feature-compat | kb-consistency
  (mapping in EXIT_CONTRACT.md; enforced in validate_phase_completion.py:79-89)

Hooks:  hooks/README.md + hooks/task_completed_phase_gate.example.json
        — examples only; not active.
```

### 1.2 State files (run.py:35-67)

```
<run_dir>/
  run_inputs.yml                       ◄── built by run.py:_build_run_inputs
  phases/
    phase0_output.yml ... phase5_output.yml   ◄── written by phase agent BEFORE checkpoint
    phaseN/
      attempts.jsonl                    ◄── one line per phase-internal repair attempt
      logs/                             ◄── phase 1-4 only (run.py:198-200)
      output.yml (legacy)
  run_state.json (legacy)               ◄── written for backward compat
```

`run_inputs.yml` schema today:
```yaml
source:
  hf_ckpt_path: <str>
paths:
  hf_modeling_path:
  hf_transformers_path:
  omni_path:              # local FS path to LoongForge repo (working copy)
  megatron_path:          # local FS path to Megatron-LM repo (working copy)
options:
  model_name:
  gpu_execution_mode:     local_gpu | k8s
  enable_slice_ckpt:      true | false
  k8s_yaml_path:
  k8s_launch_cmd:
  wip_code_paths:         # JSON-stringified list of {path,type}
```

ALL existing path fields are local filesystem paths. No git-remote / URL / branch concept. **This is the gap REQ-INPUT-01/02 must close.**

### 1.3 Critical observation: there is no top-level orchestrator process

SKILL.md:7-8 says the runner "does not execute Phase agents." The "orchestration" today is the model reading SKILL.md and dispatching `adapt-phaseN` agents. There is no Python/Bash control loop driving Phase 0 → Phase 5. **The new loop-engineering layer MUST live in this same model-driven control plane (markdown + sub-agents + helper scripts), not as a long-running Python process.**

### 1.4 Phase output contract (validate_phase_completion.py)

- Every phase output MUST have `status: passed`, `step_gate.mandatory_steps_complete: true`, per-step evidence (lines 44-63).
- Phase 0: four boolean checks (lines 71-77).
- Phase 1-5: `validator.{name,status}` evidence under `validator` or `details.validator` (lines 79-90).
- Phase 2: additionally `conversion.production_gate.*` booleans.

This is the ONLY thing the deterministic gate enforces. New loop fields are NOT auto-checked unless we extend `validate_phase_completion.py` carefully.

---

## 2. Integration Points for the Loop Layer

| # | Attach point | File / location | What attaches | Type |
|---|---|---|---|---|
| IP-1 | Pre-run input collection | `run.py:main` (lines 285-372) + new SKILL.md "Reading Order" item | Add 4 new CLI flags `--hf-impl-url`, `--hf-ckpt-url`, `--loongforge-repo`, `--megatron-repo` (with `@branch:path` syntax); validate via `gh repo view`; persist into `run_inputs.yml` new top-level key `repos:` | Pre-phase |
| IP-2 | Schema extension | `run.py:_build_run_inputs` (lines 35-67) | Add `repos:` block (see §4) without removing existing keys | Schema additive |
| IP-3 | Loop controller (per phase) | New section in SKILL.md between "Phase Dispatch Rules" (line 91) and "Phase-internal Step Enforcement" (line 106). New helper: `skills/adapt/scripts/loop_controller.py` | Owns outer `Probe→PR→Merge→Validate` loop. Calls `adapt-phaseN` for "Edit" step | New top-level orchestrator (model-driven) |
| IP-4 | Phase agent — pre-edit hook | Each `agents/adapt-phaseN.md` "Responsibilities" | "Before writing files, branch the target external repo via `gh_helper.create_branch`; record `current_branch` in attempt header" | Pre-phase-step |
| IP-5 | Phase agent — post-edit hook | Each `agents/adapt-phaseN.md` after "Write phaseN_output.yml" | "Open PR via `gh_helper.open_pr`, write PR URL into new `pr` field of `phaseN_output.yml`" | Post-phase-step (BEFORE validator) |
| IP-6 | Validator wrapper | `loop_controller.py` wraps validator-call (NOT inside `validate_phase_completion.py`) | Controller verifies PR is merged before accepting `phase.status=passed`; if validator fails, invokes `gh_helper.open_issue` and triggers fix-PR sub-loop | Validator post-condition |
| IP-7 | Phase-completion gate | `validate_phase_completion.py` — keep existing checks intact; add OPTIONAL fields gated by `loop_engineering: true` flag in `phaseN_output.yml` | Add `_validate_loop_evidence()` that runs only when flag is set. Old runs without flag continue to pass | Backward-compatible extension |
| IP-8 | Resume path | `run.py:resume_run_dir` (lines 220-239) | When resuming, controller reconstructs `pr_state` and `issue_state` from `phaseN_output.yml` + `attempts.jsonl`. `clear_phase_output` (lines 174-181) MUST also reset `pr`/`issues` keys | Resume |
| IP-9 | Hook integration | `hooks/task_completed_phase_gate.example.json` | Optional sibling example `task_completed_loop_gate.example.json` calling new `loongforge-loop-gate` | Optional |
| IP-10 | Skill discovery | `skills/adapt/SKILL.md` "Reading Order" (lines 28-37) | Add reference to new `references/loop_engineering/README.md` | Documentation |

**Critical: IP-3 / IP-6 / IP-7 are load-bearing.** IP-1/IP-2/IP-4/IP-5/IP-8 are mechanical. IP-9/IP-10 are wiring.

---

## 3. Target Layered Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│  Layer A — INPUT COLLECTION                                        │
│  bin/loongforge-adapt → run.py:main + run.py:_build_run_inputs     │
│  Adds 4 URL inputs; validates via `gh repo view`                   │
│  Output: run_inputs.yml (with new `repos:` block)                  │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  Layer B — LOOP CONTROLLER (NEW)                                   │
│  skills/adapt/scripts/loop_controller.py                           │
│  + SKILL.md "Loop Engineering" section (model reads this)          │
│  State machine:                                                    │
│    PROBE → EDIT(=phase agent) → PR(open) → MERGE(base)             │
│         → VALIDATE → [pass=>EXIT_PHASE] | [fail=>DIAGNOSE]         │
│         DIAGNOSE → ISSUE(open) → FIX_PR(=phase agent re-dispatch)  │
│                  → MERGE → VALIDATE (loop bounded by max_attempts) │
│  Reads/writes: phaseN_output.yml + phaseN/attempts.jsonl ONLY      │
└────────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────────────┐
│ Layer C —        │ │ Layer D — GH     │ │ Layer E — VALIDATOR      │
│ PHASE DISPATCHER │ │ HELPERS (NEW)    │ │ INVOCATION               │
│ (existing,       │ │ scripts/         │ │ scripts/                 │
│ unchanged        │ │  gh_helper.py    │ │  validate_phase_         │
│ internals)       │ │ - create_branch  │ │  completion.py           │
│ Task → adapt-    │ │ - open_pr        │ │ (extended w/ optional    │
│  phaseN agent    │ │ - merge_pr       │ │  loop_evidence check     │
│ Phase agent      │ │ - open_issue     │ │  gated by flag)          │
│ runs validator   │ │ - close_issue    │ │ + per-phase validators   │
│ internally       │ │ - link_pr_issue  │ │  unchanged               │
│                  │ │ - poll_status    │ │                          │
└──────────────────┘ └──────────────────┘ └──────────────────────────┘
              │               │               │
              └───────────────┼───────────────┘
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  Layer F — STATE PERSISTENCE                                       │
│  run_inputs.yml  (extended)                                        │
│  phases/phaseN_output.yml  (extended w/ pr / issues / loop fields) │
│  phases/phaseN/attempts.jsonl  (one line per loop iteration)       │
│  run_state.json  (legacy passthrough)                              │
└────────────────────────────────────────────────────────────────────┘
```

Layer boundaries enforced by file path:
- A = `run.py` only
- B = `loop_controller.py` + new SKILL.md section. NEVER reaches into phase-internal step files.
- C = `agents/adapt-phaseN.md` + `references/phases/phaseN/*` — UNTOUCHED internally; only pre-edit / post-edit hook bullets in `agents/*.md` change.
- D = `gh_helper.py` only — pure `subprocess` shim around `gh`. No business logic.
- E = `validate_phase_completion.py` extended additively + per-phase validators unchanged.
- F = same files as today, additive schema only.

---

## 4. State Schema Additions (non-breaking)

### 4.1 `run_inputs.yml` — add new top-level `repos:` block

```yaml
# existing keys unchanged: source, paths, options
repos:                              # NEW — REQ-INPUT-01
  hf_impl:
    url: "https://github.com/<org>/<repo>"
    ref: "main"
    subpath: "transformers/models/deepseek_v4"
  hf_ckpt:
    url: "https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-Base"
    revision: "main"
  loongforge:
    url: "https://github.com/Zachary-wW/LoongForge"
    base_ref: "main"
    work_branch: ""                  # filled by loop controller
  megatron:
    url: "https://github.com/Zachary-wW/Loong-Megatron"
    base_ref: "loong-main/core_v0.15.0"
    work_branch: ""
loop:                                # NEW — REQ-LOOP-03 bounds
  max_attempts_per_phase: 5
  max_total_minutes: 240
  escalation: "human_needed"
```

Backward compat: `repos:` and `loop:` absent → controller treats as "loop engineering disabled" and falls back to today's local-path-only behavior. `--resume` works unchanged.

### 4.2 `phaseN_output.yml` — add optional `pr`, `issues`, `loop` blocks

```yaml
# existing keys unchanged: status, step_gate, steps, validator, checks, conversion...
pr:                                  # NEW — REQ-PR-01/02
  base:
    repo: "Zachary-wW/LoongForge"
    number: 412
    url: "https://github.com/.../pull/412"
    state: "merged"
    title: "[adapt run=2026-06-22 phase=1] Omni MoE block init"
    merged_sha: "abc123"
  fixes: []
issues:                              # NEW — REQ-ISSUE-01/02
  - repo: "Zachary-wW/LoongForge"
    number: 87
    url: "..."
    state: "closed"
    fixed_by_pr: 415
    failure_gate: "phase1-verify.loss_align"
    attempt: 3
loop:                                # NEW — REQ-LOG-01
  attempts: 4
  max_attempts: 5
  exit_reason: "validator_passed_after_fix"
  attempts_journal: "phases/phase1/attempts.jsonl"
loop_engineering: true               # flag gating new validator checks (IP-7)
```

### 4.3 `phaseN/attempts.jsonl` — one record per outer-loop iteration

```jsonl
{"ts":"2026-06-22T10:00:00Z","attempt":1,"kind":"base_pr","pr":"https://.../412","validator":null,"verdict":null}
{"ts":"2026-06-22T10:25:00Z","attempt":1,"kind":"validate","validator":"phase1-verify","verdict":"failed","failure_gate":"loss_align","issue":"https://.../87"}
{"ts":"2026-06-22T11:10:00Z","attempt":2,"kind":"fix_pr","pr":"https://.../415","fixes_issue":"https://.../87"}
{"ts":"2026-06-22T11:35:00Z","attempt":2,"kind":"validate","validator":"phase1-verify","verdict":"passed"}
```

### 4.4 What we deliberately do NOT change

- `validate_phase_completion.py` existing required fields — unchanged.
- `run_state.json` — frozen.
- `references/phases/phaseN/*.md` internals — unchanged.

---

## 5. Build Order (dependency-driven)

Independent foundations (parallelizable):
- **B1. `gh_helper.py`** (Layer D). Pure `gh` CLI shim. Mockable. Unblocks REQ-TEST-01.
- **B2. Schema additions** (Layer F): extend `_build_run_inputs` to accept `repos`/`loop` kwargs. Pure data.
- **B3. Documentation skeleton**: new `skills/adapt/references/loop_engineering/README.md` referencing se.rpcx.io 04/08/12. No code.

First sequential layer (depends on B1+B2):
- **B4. Input-collection CLI extensions** (Layer A): add 4 URL flags to `run.py:main`. Validate via `gh_helper.repo_exists`. Persist into `repos:` block.
- **B5. `loop_controller.py` skeleton** (Layer B): pure state machine, no GitHub side-effects yet. Read `phaseN_output.yml`, decide next action, return directive. Drives off `attempts.jsonl`. Deterministic and unit-testable. **Most important new file.**

Second sequential layer (depends on B4+B5):
- **B6. SKILL.md "Loop Engineering" section**: insert between line 91 ("Phase Dispatch Rules") and line 106 ("Phase-internal Step Enforcement").
- **B7. Phase-agent hook bullets**: 2 bullets to each `agents/adapt-phaseN.md` (IP-4, IP-5). Mechanical, ×6.
- **B8. Connect controller → `gh_helper`**: wire side-effects. End-to-end smoke test against throwaway repo or `gh` mock.

Third sequential layer (depends on B5+B7):
- **B9. `validate_phase_completion.py` extension** (IP-7): `_validate_loop_evidence` gated by `loop_engineering: true`. Test legacy outputs still pass.
- **B10. Resume integration** (IP-8): extend `clear_phase_output` to reset `pr`/`issues`/`loop`. Verify `--resume --from-phase N` runnable.
- **B11. Pytest e2e** (REQ-TEST-01): mock `gh`, exercise fail→issue→fix-PR→pass on Phase 1.

Optional / last:
- **B12. `loongforge-loop-gate` bin + hook example** (IP-9). Cosmetic.
- **B13. `references/phases/*/agent.md` documentation refresh** (REQ-DOC-01). Doc-only; parallel from B6 onward.

**Critical path: B1 → B5 → B6 → B8 → B11.** B2/B3/B4/B7/B9/B10 fan out around it.

---

## 6. Backward Compatibility Notes

- `--resume` invariant: `resume_run_dir` already uses `.get()` on every field; adding `repos:` / `loop:` is invisible to old run dirs. Old `run_state.json` lacks these keys, but `_legacy_state_to_inputs` doesn't reference them.
- `loongforge-phase-gate` invariant: existing checks unchanged. New `_validate_loop_evidence` runs only when `loop_engineering: true` in output.
- Phase agent invariant: `adapt-phaseN.md` files keep existing responsibilities. Two new bullets are conditional on `repos:` being present in `run_inputs.yml`.
- Hook invariant: existing hook example unchanged. Loop hook is a new sibling example, not enabled by default.
- `run_state.json` invariant: per SKILL.md:67, zero new orchestration fields. All new state in `run_inputs.yml` and `phaseN_output.yml`.
- CLI invariant: `loongforge-adapt <hf_path>` without URL flags continues to work; loop engineering is opt-in.

---

## 7. Confidence Assessment

| Area | Confidence | Reason |
|---|---|---|
| Current architecture mapping | HIGH | All claims cite file path + line range, files read in full |
| Integration points | HIGH | Anchored to specific function names and line ranges |
| Target architecture layering | MEDIUM | Layer split is opinionated; no external precedent verified |
| Schema additions | HIGH | Each new key purely additive; tested against existing readers |
| Build order | MEDIUM | Internally consistent; B5 may need to split during implementation |
| Backward-compat claims | HIGH | Verified by reading `resume_run_dir`, `clear_phase_output`, `_legacy_state_to_inputs`, `validate_phase_output` end-to-end |

---

## 8. Open Questions

- Concurrency: does `loop_controller` handle parallel base PRs across LoongForge + Megatron in a single phase? Or per-phase one-PR-at-a-time?
- Branch naming for `repos.*.work_branch` — recommend `loongforge-adapt/<run_id>/phase<N>` but needs design confirmation.
- Should `loop_controller` block on PR review approval, or auto-merge?
- Token / API-rate-limit ceilings under `loop.max_total_minutes` — needs ops input.

---

## Files inspected

- `.planning/PROJECT.md`
- `skills/adapt/SKILL.md`
- `skills/adapt/scripts/run.py`
- `skills/adapt/scripts/validate_phase_completion.py`
- `skills/adapt/knowledge_base/schema/EXIT_CONTRACT.md`
- `skills/adapt/knowledge_base/schema/STEP_GATE.md`
- `agents/adapt-phase{0,1}.md`
- `bin/loongforge-adapt`, `bin/loongforge-phase-gate`
- `hooks/README.md`
