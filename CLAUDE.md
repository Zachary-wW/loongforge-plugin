<!-- GSD:project-start source:PROJECT.md -->
## Project

**LoongForge Adapt — Loop-Engineering HF→LoongForge Model Adaptation**

七阶段闭环模型适配系统。用户给出 HF 模型实现 + ckpt + LoongForge 仓库 + Loong-Megatron 仓库四份输入，skill 在外部 GitHub 仓库上以 PR → review → merge → 验证 → 失败建 issue → 修复 PR 闭环驱动适配，直到所有 phase validator 全部通过。

**Core Value:** 适配过程是闭环的——验证器是真相源，除非全部 pass，循环不结束。

### Constraints

- **Tech stack**：Claude Code skill (Markdown + Python helpers) + Bash + `gh` CLI；不引入新语言/服务
- **External access**：必须有对 LoongForge / Loong-Megatron 仓库的写权限；权限缺失 fail-fast
- **Compatibility**：保留 `--resume` 与现有 `phases/phaseN_output.yml` 契约
- **Determinism**：loop 有显式上界（max attempts + max wallclock），避免 token/GitHub API 失控
- **Security**：PR/issue 正文不得包含 ckpt 路径以外的敏感信息
- **Plugin layout**：所有改动收敛在 `skills/adapt/`；`skills/adapt_eval` 不动
- **Branch**：当前工作分支 `refactor/adapt-loop-engineering`（基于 main）
<!-- GSD:project-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

### Seven-Phase Flow

```
Phase 0: Bridge Analysis ──→ Phase 1: Network Construction ──→ Phase 2: Weight Conversion
    │                                                              │
    │  (hf_analysis.yaml, reference_impl_analysis.yaml,           │  (production checkpoint
    │   bridge_mapping.yaml)                                       │   verification)
    │                                                              │
    ↓                                                              ↓
Phase 3: Loss Diff ──→ Phase 4: Performance Tuning ──→ Phase 5: Feature Compat ──→ Phase 6: KB Update
```

| Phase | Agent | Core Task | Exit Gate (Validator) |
|-------|-------|-----------|----------------------|
| 0 | `adapt-phase0` | Dual-reference bridge analysis + checkpoint slicing | Three-document output checks |
| 1 | `adapt-phase1` | Omni network construction + random-init sanity | `phase1-verify` |
| 2 | `adapt-phase2` | Weight conversion + production checkpoint verification | `phase2-conversion` |
| 3 | `adapt-phase3` | Real-weight loss diff verification | `loss-diff` |
| 4 | `adapt-phase4` | Performance profiling and tuning (nsys + perf-tuner) | `performance-tuning` |
| 5 | `adapt-phase5` | Feature switch + combination verification | `feature-compat` |
| 6 | `adapt-phase6` | Knowledge base update | `kb-consistency` |

**Phase 0** is special: it does NOT use the 12-state Loop FSM. It runs a quality inner loop (max 3 rounds) producing three deliverables (`hf_analysis.yaml`, `reference_impl_analysis.yaml`, `bridge_mapping.yaml`) that all downstream phases consume.

**Cross-phase transition** is gated by user confirmation (`[CHECKPOINT]` protocol) unless `options.autonomous_mode: true`.

### Three Nested Loops

| Layer | Scope | Coordination Bus | Implementation |
|-------|-------|-------------------|----------------|
| **Inner** | Phase-internal self-repair | Disk files (`attempts.jsonl`) | Phase agent owns its checklist + step gate |
| **Middle** | GitHub PR/issue cycle | GitHub (`gh` CLI) | `loop_controller.py` 12-state FSM |
| **Outer** | Multi-model replay (future) | Run directory | Not yet implemented |

Key insight: the loop does not adapt the model — it adapts the plugin's own bugs out.

### 12-State FSM (Middle Loop)

```
PROBE → EDIT → PR → MERGE_BASE → VALIDATE
    → (DIAGNOSE → ISSUE → FIX_PR → REVIEW → MERGE_FIX → RERUN)*
    → EXIT
```

| State | Action |
|-------|--------|
| `probe` | Read run state from disk |
| `edit` | Agent performs code changes |
| `pr` | Create branch + open base PR |
| `merge_base` | Merge the base PR |
| `validate` | Run phase validator |
| `diagnose` | Classify failure (read-only) |
| `issue` | Open GitHub issue for the failure |
| `fix_pr` | Advance attempt, create fix branch + fix-PR |
| `review` | Advisory review of fix-PR |
| `merge_fix` | Merge the fix-PR |
| `rerun` | Re-run validator after fix merge |
| `exit` | Loop terminates |

**Exit reasons:** `validator_passed` | `validator_passed_after_fix` | `exhausted` | `escalated` | `base_only` | `human_needed` | `fix_needed`

The FSM is **re-entrant**: state lives on disk (`loop_state.yml` + `attempts.jsonl`), never in conversation context (P1). Each invocation reloads from disk.

### Maker-Checker Split

Edit/PR-author and Diagnose are **distinct sub-agents** (P16):

- **Edit agent**: writes code, creates PRs
- **Diagnose agent**: read-only — reads validator output + attempts history, classifies failures as `code-bug | flaky | wrong-direction | needs-human`

`wrong-direction` (3+ consecutive same-failure attempts) short-circuits to `human_needed` and writes `phases/phaseN/escalation.md`.

### Three-Axis Budget

| Axis | Default | Ceiling | Enforcement |
|------|---------|---------|-------------|
| `max_attempts_per_phase` | 5 | 50 | Per-phase attempt count |
| `max_attempts_per_run` | 25 | 500 | Total attempts across all phases |
| `max_wallclock_minutes` | 240 | 10,080 | Elapsed wall-clock time since run start |

Budget is checked **before** processing validator results (Pitfall 2). If breached, exit is ALWAYS `exhausted`/`human_needed`, never `passed`.

### Flake Rerun

Phases 3 and 5 support flake rerun: near-threshold numerical failures auto-rerun up to 3 times before being treated as real failures. Flake rerun uses the SAME attempt number (no `_advance_attempt`).

### Key Modules

| Module | Role |
|--------|------|
| `lib/loop_controller.py` | 12-state FSM spine |
| `lib/validator_wrapper.py` | Validator invocation, integrity checks, flake rerun, SHA pinning |
| `lib/diagnose_classifier.py` | Read-only failure classification (maker-checker) |
| `lib/gh_client.py` | GhClient Protocol + RealGhClient + FakeGhClient |
| `lib/schema.py` | Pydantic v2 models (RunInputs, LoopBudget, Phase 0 three-doc) |
| `lib/resume.py` | Resume reconciliation against remote GitHub state |
| `lib/preflight.py` | Startup preflight checks (gh auth, repos, branch protection) |
| `scripts/run.py` | Main runner (init/resume run directories) |
| `scripts/phase_loop.py` | CLI wrapper for `run_phase_loop()` |
| `scripts/validate_phase_completion.py` | Deterministic phase completion gate |

### Loop Activation

When `repos:` is present in `run_inputs.yml`, loop engineering is active (4 URL inputs: `hf_impl`, `hf_ckpt`, `loongforge`, `megatron`). When absent, legacy behavior runs unchanged (COMPAT-01).
<!-- GSD:architecture-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

- **State source of truth**: `run_inputs.yml`, `phases/phaseN_output.yml`, `phases/phaseN/attempts.jsonl`
- **Legacy compat only**: `run_state.json`, `phases/phaseN/output.yml` — do not add new orchestration fields
- **No retry on validator failures** — validator failure is signal, not transient (P18)
- **No free-form Claude self-report as exit signal** — only validator verdict (P3, P10)
- **No same sub-agent for Edit and Diagnose** — P16 maker-checker split
- **Prompts are code** — repair prompts in versioned `loop_templates/phaseN/repair.md` (P6)
- **Bulk log externalization** — logs under `phases/phaseN/logs/`, only excerpts in context (SAFE-03)
<!-- GSD:conventions-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
