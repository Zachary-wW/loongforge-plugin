# LoongForge Issue-Driven Adapt Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the no-GPU MVP for a local-first issue-driven `/loongforge:adapt` loop that validates Phase 0-2 against DS V4 baseline code, creates or updates GitHub issues, and provides deterministic gates for repair/review/merge orchestration.

**Architecture:** Add a new `adapt_issue_loop` skill with a deterministic Python transform layer, following the existing `adapt_eval` pattern. The Python layer owns state files, phase goal contracts, IssueSpec generation, static baseline comparison, GitHub issue sync, and merge-gate decisions; the skill document owns agent orchestration for repair, PR review, and automatic merge.

**Tech Stack:** Python 3 standard library, PyYAML, pytest, GitHub CLI (`gh`) for real issue sync, bash wrapper in `bin/`, existing LoongForge plugin layout.

---

## File Structure

Create a focused new skill instead of adding more responsibilities to `/loongforge:adapt`:

```text
bin/loongforge-issue-loop
  Bash wrapper that executes skills/adapt_issue_loop/scripts/run.py.

skills/adapt_issue_loop/SKILL.md
  Human/agent orchestration instructions for local execution, GitHub issue sync, repair PRs, review, verification, and merge.

skills/adapt_issue_loop/scripts/run.py
  CLI dispatcher. Subcommands: init, compare-phase, issue-from-report, sync-issue, verify-merge-gate, run-dry.

skills/adapt_issue_loop/scripts/state.py
  State directory creation, state.yml read/write, default phase_goal_contract.yml, atomic YAML writes.

skills/adapt_issue_loop/scripts/issue_spec.py
  IssueSpec dataclass, dedup-key generation, issue markdown rendering, issue-spec file persistence.

skills/adapt_issue_loop/scripts/comparator.py
  No-GPU static baseline comparator for Phase 0-2 using marker rules from phase_goal_contract.yml.

skills/adapt_issue_loop/scripts/github.py
  GitHub issue create/update/reopen interface with dry-run mode and subprocess-backed `gh` mode.

skills/adapt_issue_loop/scripts/verification.py
  Deterministic merge-gate decision helper.

skills/adapt_issue_loop/tests/test_layout.py
  Layout and wrapper tests.

skills/adapt_issue_loop/tests/test_state.py
  State and goal-contract tests.

skills/adapt_issue_loop/tests/test_issue_spec.py
  IssueSpec rendering, dedup, and persistence tests.

skills/adapt_issue_loop/tests/test_comparator.py
  Static comparator tests using small DS V4-like fixtures.

skills/adapt_issue_loop/tests/test_github.py
  Dry-run and mocked `gh` issue sync tests.

skills/adapt_issue_loop/tests/test_verification.py
  Merge-gate decision tests.

skills/adapt_issue_loop/tests/test_cli.py
  CLI integration tests for init, compare, issue generation, dry-run sync, and merge-gate verification.

README.md
  Add the new skill and wrapper to plugin docs.
```

Keep the Python layer deterministic and small. Do not dispatch agents from Python. Repair/review agents are launched by the main Claude session following `SKILL.md`, the same separation used by `skills/adapt_eval/SKILL.md`.

---

### Task 1: Add Issue Loop Skill Skeleton and Wrapper

**Files:**
- Create: `bin/loongforge-issue-loop`
- Create: `skills/adapt_issue_loop/SKILL.md`
- Create: `skills/adapt_issue_loop/scripts/run.py`
- Create: `skills/adapt_issue_loop/scripts/state.py`
- Create: `skills/adapt_issue_loop/scripts/issue_spec.py`
- Create: `skills/adapt_issue_loop/scripts/comparator.py`
- Create: `skills/adapt_issue_loop/scripts/github.py`
- Create: `skills/adapt_issue_loop/scripts/verification.py`
- Create: `skills/adapt_issue_loop/tests/test_layout.py`
- Modify: `README.md`

- [ ] **Step 1: Write the failing layout test**

Create `skills/adapt_issue_loop/tests/test_layout.py`:

```python
from pathlib import Path
import subprocess
import sys


SKILL_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = SKILL_ROOT.parents[1]


def test_issue_loop_layout_exists():
    assert (PLUGIN_ROOT / "bin" / "loongforge-issue-loop").exists()
    assert (SKILL_ROOT / "SKILL.md").exists()
    for name in (
        "run.py",
        "state.py",
        "issue_spec.py",
        "comparator.py",
        "github.py",
        "verification.py",
    ):
        assert (SKILL_ROOT / "scripts" / name).exists(), name


def test_issue_loop_skill_documents_entrypoint():
    text = (SKILL_ROOT / "SKILL.md").read_text()
    assert "name: adapt_issue_loop" in text
    assert "/loongforge:adapt_issue_loop" in text
    assert "loongforge-issue-loop" in text
    assert "Mac no GPU" in text
    assert "Phase 0-2" in text
    assert "GitHub Issue" in text


def test_issue_loop_cli_help_runs():
    result = subprocess.run(
        [str(PLUGIN_ROOT / "bin" / "loongforge-issue-loop"), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "LoongForge issue-driven adapt loop" in result.stdout


def test_readme_mentions_issue_loop():
    text = (PLUGIN_ROOT / "README.md").read_text()
    assert "/loongforge:adapt_issue_loop" in text
    assert "loongforge-issue-loop" in text
```

- [ ] **Step 2: Run the layout test and verify it fails**

Run:

```bash
python3 -m pytest skills/adapt_issue_loop/tests/test_layout.py -q
```

Expected: FAIL because the new skill files and wrapper do not exist.

- [ ] **Step 3: Add the wrapper**

Create `bin/loongforge-issue-loop`:

```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
exec python3 "$PLUGIN_ROOT/skills/adapt_issue_loop/scripts/run.py" "$@"
```

Run:

```bash
chmod +x bin/loongforge-issue-loop
```

- [ ] **Step 4: Add the initial skill document**

Create `skills/adapt_issue_loop/SKILL.md`:

```markdown
---
name: adapt_issue_loop
description: >
  Use when running the local-first issue-driven LoongForge adapt iteration loop,
  creating GitHub issues from Phase 0-2 DS V4 static baseline mismatches,
  driving repair PRs, review, verification, and merge.
---

# /loongforge:adapt_issue_loop — Issue-Driven Adapt Loop

This skill coordinates the local-first issue loop for `/loongforge:adapt`.

Invocation:

```text
/loongforge:adapt_issue_loop --target ds-v4 --run-dir <adapt_run_dir> [--dry-run|--apply]
```

CLI wrapper:

```bash
loongforge-issue-loop <subcommand> [options]
```

## Scope

The MVP runs on a Mac no GPU environment. It validates Phase 0-2 only:

- Phase 0: static artifact completeness against DS V4 baseline facts.
- Phase 1: generated code structure/signature/config/native integration against DS V4 baseline code.
- Phase 2: conversion/tensor mapping coverage against DS V4 baseline conversion facts.

Phase 3 and Phase 4 are deferred in this MVP and must not be reported as passed.

## Baseline Groundtruth

Default target case `ds-v4` uses:

```text
../baidu/hac-aiacc/AIAK-Megatron      @ 12713af0
../baidu/hac-aiacc/AIAK-Training-Omni @ 83e71867
```

## Orchestration Rules

1. Initialize `.loongforge/issue-loop/state.yml` and `phase_goal_contract.yml`.
2. Run or resume `/loongforge:adapt` locally for the enabled phase.
3. Run `loongforge-issue-loop compare-phase` for the current phase.
4. If comparison fails, run `issue-from-report` and `sync-issue`.
5. Repair agent reads exactly one GitHub Issue and creates branch `agent/issue-<id>-<slug>`.
6. Repair agent proves the issue with a failing check or artifact-level evidence before changing code.
7. Repair agent commits and opens or updates one PR linked to the issue.
8. Review agent checks issue scope, diff, tests, comparator report, and merge gate.
9. Merge only when `verify-merge-gate` returns passed and review verdict is approved.
10. After merge, rerun the current phase before advancing.

## Status Semantics

- `passed`: the local no-GPU static comparator and phase artifact gates passed.
- `failed`: an actionable mismatch exists and should become or update a GitHub Issue.
- `deferred`: GPU-only Phase 3/4 validation is outside the MVP.
- `needs-human`: iteration limits, missing baseline, or unreproducible issue blocked autonomy.

## Deterministic CLI Layer

The Python scripts do deterministic transforms only. They do not dispatch agents.
The main Claude session dispatches repair/review agents using the GitHub Issue and PR as task boundaries.
```

- [ ] **Step 5: Add script stubs that make help work**

Create `skills/adapt_issue_loop/scripts/run.py`:

```python
#!/usr/bin/env python3
"""LoongForge issue-driven adapt loop CLI."""
from __future__ import annotations

import argparse


DESCRIPTION = "LoongForge issue-driven adapt loop"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument("--version", action="version", version="loongforge-issue-loop 0.1.0")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("init", help="Initialize local issue-loop state")
    sub.add_parser("compare-phase", help="Compare a phase against static baseline rules")
    sub.add_parser("issue-from-report", help="Create IssueSpec files from a comparator report")
    sub.add_parser("sync-issue", help="Create or update a GitHub Issue from an IssueSpec")
    sub.add_parser("verify-merge-gate", help="Evaluate deterministic merge-gate inputs")
    sub.add_parser("run-dry", help="Run local dry-run pipeline without touching GitHub")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    parser.error(f"subcommand not implemented yet: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

Create `skills/adapt_issue_loop/scripts/state.py`:

```python
"""State helpers for loongforge-issue-loop."""
from __future__ import annotations
```

Create `skills/adapt_issue_loop/scripts/issue_spec.py`:

```python
"""IssueSpec helpers for loongforge-issue-loop."""
from __future__ import annotations
```

Create `skills/adapt_issue_loop/scripts/comparator.py`:

```python
"""Static baseline comparator for loongforge-issue-loop."""
from __future__ import annotations
```

Create `skills/adapt_issue_loop/scripts/github.py`:

```python
"""GitHub issue sync helpers for loongforge-issue-loop."""
from __future__ import annotations
```

Create `skills/adapt_issue_loop/scripts/verification.py`:

```python
"""Merge-gate verification helpers for loongforge-issue-loop."""
from __future__ import annotations
```

- [ ] **Step 6: Update README**

Modify `README.md` to include the new skill and wrapper. Add bullets under existing sections:

```markdown
- `/loongforge:adapt_issue_loop` — Local-first issue-driven Phase 0-2 adapt iteration loop with GitHub Issue/PR handoff.
```

Add wrapper usage:

```bash
loongforge-issue-loop init --target ds-v4 --repo Zachary-wW/loongforge-plugin
loongforge-issue-loop compare-phase --phase 0 --run-dir <run_dir>
loongforge-issue-loop sync-issue --issue-spec <issue.yml> --dry-run
```

- [ ] **Step 7: Run the layout test and verify it passes**

Run:

```bash
python3 -m pytest skills/adapt_issue_loop/tests/test_layout.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

Run:

```bash
git add bin/loongforge-issue-loop skills/adapt_issue_loop README.md
git commit -m "feat: add issue loop skill skeleton" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Implement State Store and Mutable Phase Goal Contract

**Files:**
- Modify: `skills/adapt_issue_loop/scripts/state.py`
- Create: `skills/adapt_issue_loop/tests/test_state.py`

- [ ] **Step 1: Write failing state tests**

Create `skills/adapt_issue_loop/tests/test_state.py`:

```python
import importlib.util
from pathlib import Path

import yaml


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "state.py"
SPEC = importlib.util.spec_from_file_location("issue_loop_state", SCRIPT)
state = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(state)


def test_default_state_records_ds_v4_baseline():
    data = state.default_state(repo="Zachary-wW/loongforge-plugin")
    assert data["target_case"] == "ds_v4"
    assert data["baseline"]["megatron"]["commit"] == "12713af0"
    assert data["baseline"]["omni"]["commit"] == "83e71867"
    assert data["scope"]["phases_enabled"] == [0, 1, 2]
    assert data["scope"]["phases_deferred"][3].startswith("Mac no GPU")
    assert data["merge_policy"] == "auto_after_review_and_verification"


def test_default_goal_contract_has_phase0_1_2_and_deferred_runtime():
    contract = state.default_goal_contract()
    assert sorted(contract.keys()) == ["phase0", "phase1", "phase2", "phase3", "phase4"]
    assert contract["phase0"]["version"] == 1
    assert "MLA" in "\n".join(contract["phase0"]["acceptance"])
    assert "framework-native" in "\n".join(contract["phase1"]["acceptance"])
    assert "tensor" in "\n".join(contract["phase2"]["acceptance"])
    assert contract["phase3"]["status"] == "deferred"
    assert contract["phase4"]["status"] == "deferred"


def test_init_loop_state_writes_state_and_contract(tmp_path):
    state_dir = state.init_loop_state(
        plugin_root=tmp_path,
        repo="Zachary-wW/loongforge-plugin",
    )
    assert state_dir == tmp_path / ".loongforge" / "issue-loop"
    loaded_state = yaml.safe_load((state_dir / "state.yml").read_text())
    loaded_contract = yaml.safe_load((state_dir / "phase_goal_contract.yml").read_text())
    assert loaded_state["active_phase"] == 0
    assert loaded_state["limits"]["max_iterations_per_issue"] == 5
    assert loaded_contract["phase0"]["goal"].startswith("Extract enough DS V4")


def test_update_state_merges_top_level_keys(tmp_path):
    state_dir = state.init_loop_state(plugin_root=tmp_path, repo="repo/example")
    updated = state.update_state(state_dir, {"active_phase": 1, "active_issue": 17})
    assert updated["active_phase"] == 1
    assert updated["active_issue"] == 17
    loaded = state.load_state(state_dir)
    assert loaded["active_phase"] == 1
    assert loaded["repo"] == "repo/example"
```

- [ ] **Step 2: Run the state tests and verify they fail**

Run:

```bash
python3 -m pytest skills/adapt_issue_loop/tests/test_state.py -q
```

Expected: FAIL because state functions are not defined.

- [ ] **Step 3: Implement state helpers**

Replace `skills/adapt_issue_loop/scripts/state.py` with:

```python
"""State helpers for loongforge-issue-loop."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import yaml


STATE_REL_DIR = Path(".loongforge") / "issue-loop"
DEFAULT_REPO = "Zachary-wW/loongforge-plugin"
DEFAULT_TARGET = "ds_v4"
DEFAULT_MEGATRON_PATH = "../baidu/hac-aiacc/AIAK-Megatron"
DEFAULT_MEGATRON_COMMIT = "12713af0"
DEFAULT_OMNI_PATH = "../baidu/hac-aiacc/AIAK-Training-Omni"
DEFAULT_OMNI_COMMIT = "83e71867"


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def dump_yaml(path: Path, data: dict[str, Any]) -> None:
    atomic_write_text(path, yaml.dump(data, sort_keys=False, allow_unicode=True))


def load_yaml(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text())
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected YAML mapping at {path}")
    return loaded


def default_state(repo: str = DEFAULT_REPO) -> dict[str, Any]:
    return {
        "repo": repo,
        "mode": "local_execution_github_issues",
        "target_case": DEFAULT_TARGET,
        "baseline": {
            "megatron": {
                "path": DEFAULT_MEGATRON_PATH,
                "commit": DEFAULT_MEGATRON_COMMIT,
            },
            "omni": {
                "path": DEFAULT_OMNI_PATH,
                "commit": DEFAULT_OMNI_COMMIT,
            },
        },
        "scope": {
            "phases_enabled": [0, 1, 2],
            "phases_deferred": {
                3: "Mac no GPU; loss-diff validation deferred",
                4: "Mac no GPU; runtime feature matrix validation deferred",
            },
        },
        "active_phase": 0,
        "active_issue": None,
        "active_pr": None,
        "phase_iterations": {"0": 0, "1": 0, "2": 0},
        "limits": {
            "max_iterations_per_issue": 5,
            "max_iterations_per_phase": 10,
        },
        "merge_policy": "auto_after_review_and_verification",
    }


def default_goal_contract() -> dict[str, Any]:
    return {
        "phase0": {
            "version": 1,
            "goal": "Extract enough DS V4 facts for Phase 1 code generation.",
            "acceptance": [
                "Resolve HF source/config/modeling paths.",
                "Record AIAK-Megatron and AIAK-Training-Omni baseline commits.",
                "Identify DS V4 architecture family/category.",
                "Extract MLA-related config fields and structural facts.",
                "Extract MoE router/expert/shared-expert facts.",
                "Extract MTP facts or explicitly prove MTP is absent.",
                "Extract checkpoint tensor naming patterns needed by Phase 2.",
                "Write reference_contract.yml linking baseline files/symbols to required components.",
                "Phase 1 strategy preflight can consume Phase 0 output without fallback_phase=0 for missing analysis.",
            ],
            "comparator_rules": [
                {"id": "phase0_mla", "markers": ["qk_rope_head_dim", "o_lora_rank", "csa_compress_ratios"]},
                {"id": "phase0_moe", "markers": ["moe_n_hash_layers", "moe_router_score_function", "sqrtsoftplus"]},
                {"id": "phase0_mtp", "markers": ["mtp_num_layers"]},
            ],
        },
        "phase1": {
            "version": 1,
            "goal": "Generate baseline-aligned framework-native DS V4 code.",
            "acceptance": [
                "Generated code uses framework-native integration, not standalone fallback.",
                "DS V4 config fields cover baseline-required fields.",
                "MLA component structure matches baseline-required classes/functions/interfaces.",
                "MoE component structure matches baseline-required classes/functions/interfaces.",
                "MTP component structure matches baseline-required classes/functions/interfaces, or absence is justified.",
                "Layer spec / module spec integration follows baseline native pattern.",
                "Lint/import/static checks pass where available on Mac.",
                "Phase 2 can consume generated code and config without missing structural information.",
            ],
            "comparator_rules": [
                {"id": "phase1_package", "markers": ["DeepseekV4Config", "DeepseekV4Model", "deepseek_v4_layer_spec"]},
                {"id": "phase1_attention", "markers": ["experimental_attention_variant", "dsv4_hybrid", "csa_compress_ratios"]},
                {"id": "phase1_moe_mtp", "markers": ["moe_n_hash_layers", "mtp_num_layers", "sqrtsoftplus"]},
            ],
        },
        "phase2": {
            "version": 1,
            "goal": "Generate baseline-aligned DS V4 conversion rules.",
            "acceptance": [
                "Conversion config/rules cover baseline DS V4 tensor names.",
                "MLA tensor mappings are present.",
                "MoE router/expert/shared expert tensor mappings are present.",
                "MTP tensor mappings are present or absence is justified.",
                "Split/merge/transpose rules match baseline intent.",
                "Converter entrypoints/scripts are generated.",
                "No runtime GPU gate is required for MVP pass.",
            ],
            "comparator_rules": [
                {"id": "phase2_mla_tensors", "markers": ["q_lora", "kv_lora", "qk_rope_head_dim"]},
                {"id": "phase2_moe_tensors", "markers": ["experts", "router", "shared"]},
                {"id": "phase2_mtp_tensors", "markers": ["mtp"]},
            ],
        },
        "phase3": {
            "status": "deferred",
            "reason": "Mac no GPU; runtime loss-diff validation is out of MVP scope.",
        },
        "phase4": {
            "status": "deferred",
            "reason": "Mac no GPU; runtime feature matrix validation is out of MVP scope.",
        },
    }


def init_loop_state(plugin_root: Path, repo: str = DEFAULT_REPO) -> Path:
    state_dir = plugin_root / STATE_REL_DIR
    state_dir.mkdir(parents=True, exist_ok=True)
    for child in ("issue_specs", "verification_reports", "comparator_reports"):
        (state_dir / child).mkdir(parents=True, exist_ok=True)
    dump_yaml(state_dir / "state.yml", default_state(repo=repo))
    dump_yaml(state_dir / "phase_goal_contract.yml", default_goal_contract())
    return state_dir


def load_state(state_dir: Path) -> dict[str, Any]:
    return load_yaml(state_dir / "state.yml")


def load_goal_contract(state_dir: Path) -> dict[str, Any]:
    return load_yaml(state_dir / "phase_goal_contract.yml")


def update_state(state_dir: Path, updates: dict[str, Any]) -> dict[str, Any]:
    data = load_state(state_dir)
    data.update(updates)
    dump_yaml(state_dir / "state.yml", data)
    return data
```

- [ ] **Step 4: Run the state tests and verify they pass**

Run:

```bash
python3 -m pytest skills/adapt_issue_loop/tests/test_state.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add skills/adapt_issue_loop/scripts/state.py skills/adapt_issue_loop/tests/test_state.py
git commit -m "feat: add issue loop state store" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Implement IssueSpec Generation and Markdown Rendering

**Files:**
- Modify: `skills/adapt_issue_loop/scripts/issue_spec.py`
- Create: `skills/adapt_issue_loop/tests/test_issue_spec.py`

- [ ] **Step 1: Write failing IssueSpec tests**

Create `skills/adapt_issue_loop/tests/test_issue_spec.py`:

```python
import importlib.util
from pathlib import Path

import yaml


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "issue_spec.py"
SPEC = importlib.util.spec_from_file_location("issue_loop_issue_spec", SCRIPT)
issue_spec = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(issue_spec)


def test_make_dedup_key_is_stable_and_slugged():
    key = issue_spec.make_dedup_key(phase=0, root_cause="model_spec missing MTP", gate="Phase 1 Contract")
    assert key == "phase0:model_spec_missing_mtp:phase_1_contract"


def test_issue_spec_renders_markdown_with_checklist():
    spec = issue_spec.IssueSpec(
        dedup_key="phase0:model_spec_missing_mtp:phase1_contract_blocked",
        phase=0,
        title="[Phase 0][DS V4] model_spec misses MTP fields",
        kind="contract-missing",
        severity="blocker",
        goal_blocked="Phase 1 cannot choose DS V4 native strategy without MTP metadata.",
        observed="model_spec.yaml does not contain mtp_num_layers.",
        expected="Phase 0 output records MTP facts or proves MTP is absent.",
        reproduction={"commands": ["loongforge-issue-loop compare-phase --phase 0"], "artifacts": ["run/phases/phase0/model_spec.yaml"]},
        acceptance=["model_spec contains mtp_num_layers", "Phase 1 preflight has no fallback_phase=0"],
        labels=["loongforge-adapt", "phase-0", "ds-v4", "agent-fixable"],
    )
    body = spec.render_markdown()
    assert "## Phase" in body
    assert "Phase 0" in body
    assert "## Dedup key" in body
    assert "`phase0:model_spec_missing_mtp:phase1_contract_blocked`" in body
    assert "- [ ] model_spec contains mtp_num_layers" in body
    assert "Repair agent must reproduce or prove the issue" in body


def test_issue_spec_roundtrip_file(tmp_path):
    spec = issue_spec.IssueSpec(
        dedup_key="phase1:missing_deepseekv4model:baseline_static_compare",
        phase=1,
        title="[Phase 1][DS V4] generated code misses DeepseekV4Model",
        kind="verification-failure",
        severity="high",
        goal_blocked="Phase 1 code is not baseline aligned.",
        observed="Generated roots do not contain DeepseekV4Model.",
        expected="Generated code contains baseline-required DeepseekV4Model symbol.",
        reproduction={"commands": [], "artifacts": []},
        acceptance=["DeepseekV4Model appears in generated code"],
        labels=["phase-1"],
    )
    path = issue_spec.write_issue_spec(tmp_path, spec)
    assert path.name == "phase1-missing_deepseekv4model-baseline_static_compare.yml"
    loaded = issue_spec.load_issue_spec(path)
    assert loaded.dedup_key == spec.dedup_key
    assert loaded.labels == ["phase-1"]
```

- [ ] **Step 2: Run the IssueSpec tests and verify they fail**

Run:

```bash
python3 -m pytest skills/adapt_issue_loop/tests/test_issue_spec.py -q
```

Expected: FAIL because `IssueSpec` helpers are not defined.

- [ ] **Step 3: Implement IssueSpec helpers**

Replace `skills/adapt_issue_loop/scripts/issue_spec.py` with:

```python
"""IssueSpec helpers for loongforge-issue-loop."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml


_VALID_KINDS = {
    "bug",
    "gap",
    "regression",
    "contract-missing",
    "verification-failure",
    "goal-contract-gap",
}
_VALID_SEVERITIES = {"blocker", "high", "medium", "low"}


def slugify(value: str) -> str:
    lowered = value.strip().lower()
    replaced = re.sub(r"[^a-z0-9]+", "_", lowered)
    return replaced.strip("_") or "unknown"


def make_dedup_key(phase: int, root_cause: str, gate: str) -> str:
    return f"phase{phase}:{slugify(root_cause)}:{slugify(gate)}"


@dataclass
class IssueSpec:
    dedup_key: str
    phase: int
    title: str
    kind: str
    severity: str
    goal_blocked: str
    observed: str
    expected: str
    reproduction: dict[str, Any]
    acceptance: list[str]
    labels: list[str]

    def __post_init__(self) -> None:
        if self.phase not in (0, 1, 2, 3, 4, 5):
            raise ValueError(f"phase must be 0-5, got {self.phase}")
        if self.kind not in _VALID_KINDS:
            raise ValueError(f"invalid issue kind: {self.kind}")
        if self.severity not in _VALID_SEVERITIES:
            raise ValueError(f"invalid issue severity: {self.severity}")
        if not self.dedup_key:
            raise ValueError("dedup_key is required")
        if not self.acceptance:
            raise ValueError("acceptance checklist is required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IssueSpec":
        return cls(
            dedup_key=data["dedup_key"],
            phase=int(data["phase"]),
            title=data["title"],
            kind=data["kind"],
            severity=data["severity"],
            goal_blocked=data["goal_blocked"],
            observed=data["observed"],
            expected=data["expected"],
            reproduction=data.get("reproduction") or {"commands": [], "artifacts": []},
            acceptance=list(data.get("acceptance") or []),
            labels=list(data.get("labels") or []),
        )

    def render_markdown(self) -> str:
        commands = self.reproduction.get("commands") or []
        artifacts = self.reproduction.get("artifacts") or []
        labels = ", ".join(self.labels) if self.labels else "none"
        lines = [
            "## Phase",
            f"Phase {self.phase}",
            "",
            "## Kind / Severity",
            f"{self.kind} / {self.severity}",
            "",
            "## Goal blocked",
            self.goal_blocked,
            "",
            "## Observed failure",
            self.observed,
            "",
            "## Expected behavior",
            self.expected,
            "",
            "## Evidence",
            "### Commands",
        ]
        if commands:
            lines.extend(f"- `{cmd}`" for cmd in commands)
        else:
            lines.append("- No command-level reproducer recorded; use artifact-level evidence below.")
        lines.extend(["", "### Artifacts"])
        if artifacts:
            lines.extend(f"- `{artifact}`" for artifact in artifacts)
        else:
            lines.append("- No artifacts recorded.")
        lines.extend(["", "## Acceptance checklist"])
        lines.extend(f"- [ ] {item}" for item in self.acceptance)
        lines.extend([
            "",
            "## Dedup key",
            f"`{self.dedup_key}`",
            "",
            "## Labels",
            labels,
            "",
            "## Agent instructions",
            "Repair agent must reproduce or prove the issue before modifying code.",
            "Repair agent must keep the PR scoped to this issue.",
        ])
        return "\n".join(lines) + "\n"


def issue_spec_filename(spec: IssueSpec) -> str:
    safe = spec.dedup_key.replace(":", "-")
    return f"{safe}.yml"


def write_issue_spec(directory: Path, spec: IssueSpec) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / issue_spec_filename(spec)
    path.write_text(yaml.dump(spec.to_dict(), sort_keys=False, allow_unicode=True))
    return path


def load_issue_spec(path: Path) -> IssueSpec:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"Invalid issue spec YAML: {path}")
    return IssueSpec.from_dict(data)
```

- [ ] **Step 4: Run IssueSpec tests and verify they pass**

Run:

```bash
python3 -m pytest skills/adapt_issue_loop/tests/test_issue_spec.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add skills/adapt_issue_loop/scripts/issue_spec.py skills/adapt_issue_loop/tests/test_issue_spec.py
git commit -m "feat: add issue spec rendering" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Implement No-GPU Static Baseline Comparator

**Files:**
- Modify: `skills/adapt_issue_loop/scripts/comparator.py`
- Create: `skills/adapt_issue_loop/tests/test_comparator.py`

- [ ] **Step 1: Write failing comparator tests**

Create `skills/adapt_issue_loop/tests/test_comparator.py`:

```python
import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "comparator.py"
SPEC = importlib.util.spec_from_file_location("issue_loop_comparator", SCRIPT)
comparator = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(comparator)


PHASE0_CONTRACT = {
    "phase0": {
        "goal": "Extract enough DS V4 facts for Phase 1 code generation.",
        "comparator_rules": [
            {"id": "phase0_mla", "markers": ["qk_rope_head_dim", "o_lora_rank"]},
            {"id": "phase0_mtp", "markers": ["mtp_num_layers"]},
        ],
    }
}


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_compare_phase_passes_when_generated_contains_baseline_markers(tmp_path):
    baseline = tmp_path / "baseline"
    generated = tmp_path / "run" / "phases" / "phase0"
    _write(baseline / "deepseek_v4_config.py", "qk_rope_head_dim = 64\no_lora_rank = 1024\nmtp_num_layers = 1\n")
    _write(generated / "model_spec.yaml", "qk_rope_head_dim: 64\no_lora_rank: 1024\nmtp_num_layers: 1\n")

    report = comparator.compare_phase_to_baseline(
        phase=0,
        generated_roots=[generated],
        baseline_roots=[baseline],
        goal_contract=PHASE0_CONTRACT,
    )

    assert report["status"] == "passed"
    assert report["summary"]["generated_missing"] == 0
    assert report["issue_specs"] == []


def test_compare_phase_fails_and_creates_issue_spec_when_generated_misses_marker(tmp_path):
    baseline = tmp_path / "baseline"
    generated = tmp_path / "run" / "phases" / "phase0"
    _write(baseline / "deepseek_v4_config.py", "qk_rope_head_dim = 64\no_lora_rank = 1024\nmtp_num_layers = 1\n")
    _write(generated / "model_spec.yaml", "qk_rope_head_dim: 64\no_lora_rank: 1024\n")

    report = comparator.compare_phase_to_baseline(
        phase=0,
        generated_roots=[generated],
        baseline_roots=[baseline],
        goal_contract=PHASE0_CONTRACT,
    )

    assert report["status"] == "failed"
    missing = [check for check in report["checks"] if check["status"] == "generated_missing"]
    assert missing[0]["marker"] == "mtp_num_layers"
    assert report["issue_specs"][0]["dedup_key"] == "phase0:missing_mtp_num_layers:baseline_static_compare"
    assert "mtp_num_layers" in report["issue_specs"][0]["acceptance"][0]


def test_compare_phase_reports_baseline_unavailable_when_baseline_lacks_marker(tmp_path):
    baseline = tmp_path / "baseline"
    generated = tmp_path / "run" / "phases" / "phase0"
    _write(baseline / "deepseek_v4_config.py", "qk_rope_head_dim = 64\n")
    _write(generated / "model_spec.yaml", "qk_rope_head_dim: 64\n")

    report = comparator.compare_phase_to_baseline(
        phase=0,
        generated_roots=[generated],
        baseline_roots=[baseline],
        goal_contract=PHASE0_CONTRACT,
    )

    assert report["status"] == "baseline_unavailable"
    assert report["summary"]["baseline_missing"] == 2
    assert report["issue_specs"] == []
```

- [ ] **Step 2: Run comparator tests and verify they fail**

Run:

```bash
python3 -m pytest skills/adapt_issue_loop/tests/test_comparator.py -q
```

Expected: FAIL because comparator functions are not defined.

- [ ] **Step 3: Implement comparator**

Replace `skills/adapt_issue_loop/scripts/comparator.py` with:

```python
"""Static baseline comparator for loongforge-issue-loop."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Iterable

import yaml


_HERE = Path(__file__).resolve().parent
_ISSUE_SPEC = importlib.util.spec_from_file_location("issue_loop_issue_spec", _HERE / "issue_spec.py")
issue_spec = importlib.util.module_from_spec(_ISSUE_SPEC)
assert _ISSUE_SPEC and _ISSUE_SPEC.loader
_ISSUE_SPEC.loader.exec_module(issue_spec)

TEXT_SUFFIXES = {".py", ".yaml", ".yml", ".json", ".md", ".sh", ".txt"}


def _read_text_tree(roots: Iterable[Path]) -> str:
    chunks: list[str] = []
    for root in roots:
        if root.is_file() and root.suffix in TEXT_SUFFIXES:
            chunks.append(root.read_text(encoding="utf-8", errors="replace"))
            continue
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix in TEXT_SUFFIXES:
                chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


def _phase_key(phase: int) -> str:
    return f"phase{phase}"


def _rules_for_phase(goal_contract: dict[str, Any], phase: int) -> list[dict[str, Any]]:
    phase_contract = goal_contract.get(_phase_key(phase)) or {}
    rules = phase_contract.get("comparator_rules") or []
    if not isinstance(rules, list):
        raise ValueError(f"phase{phase}.comparator_rules must be a list")
    return rules


def _goal_for_phase(goal_contract: dict[str, Any], phase: int) -> str:
    phase_contract = goal_contract.get(_phase_key(phase)) or {}
    return phase_contract.get("goal") or f"Phase {phase} static baseline comparison"


def _issue_for_missing_marker(phase: int, marker: str, rule_id: str, goal: str) -> issue_spec.IssueSpec:
    dedup = issue_spec.make_dedup_key(
        phase=phase,
        root_cause=f"missing {marker}",
        gate="baseline static compare",
    )
    labels = ["loongforge-adapt", f"phase-{phase}", "ds-v4", "agent-fixable"]
    return issue_spec.IssueSpec(
        dedup_key=dedup,
        phase=phase,
        title=f"[Phase {phase}][DS V4] generated artifacts miss baseline marker `{marker}`",
        kind="verification-failure",
        severity="blocker" if phase == 0 else "high",
        goal_blocked=goal,
        observed=f"Static baseline comparison rule `{rule_id}` found `{marker}` in baseline code but not in generated phase artifacts.",
        expected=f"Generated Phase {phase} artifacts include `{marker}` or explicitly justify why it is absent.",
        reproduction={
            "commands": [f"loongforge-issue-loop compare-phase --phase {phase} --run-dir <run_dir>"],
            "artifacts": [".loongforge/issue-loop/comparator_reports/<report>.yml"],
        },
        acceptance=[
            f"Generated Phase {phase} artifacts contain `{marker}` or record an explicit absence proof.",
            f"Comparator rule `{rule_id}` passes for `{marker}`.",
            f"Phase {phase} remains in no-GPU static validation mode; GPU-only validators are not required for this issue.",
        ],
        labels=labels,
    )


def compare_phase_to_baseline(
    phase: int,
    generated_roots: list[Path],
    baseline_roots: list[Path],
    goal_contract: dict[str, Any],
) -> dict[str, Any]:
    if phase not in (0, 1, 2):
        return {
            "phase": phase,
            "status": "deferred",
            "reason": "Only Phase 0-2 static comparison is enabled in the Mac no GPU MVP.",
            "checks": [],
            "issue_specs": [],
            "summary": {"baseline_missing": 0, "generated_missing": 0, "passed": 0},
        }

    baseline_text = _read_text_tree(baseline_roots)
    generated_text = _read_text_tree(generated_roots)
    checks: list[dict[str, Any]] = []
    issue_specs: list[dict[str, Any]] = []
    baseline_missing = 0
    generated_missing = 0
    passed = 0
    goal = _goal_for_phase(goal_contract, phase)

    for rule in _rules_for_phase(goal_contract, phase):
        rule_id = rule.get("id") or f"phase{phase}_rule"
        markers = rule.get("markers") or []
        if not isinstance(markers, list):
            raise ValueError(f"{rule_id}.markers must be a list")
        for marker in markers:
            baseline_has = marker in baseline_text
            generated_has = marker in generated_text
            if not baseline_has:
                baseline_missing += 1
                checks.append({
                    "rule_id": rule_id,
                    "marker": marker,
                    "status": "baseline_missing",
                    "message": f"Baseline roots do not contain marker `{marker}`.",
                })
            elif not generated_has:
                generated_missing += 1
                checks.append({
                    "rule_id": rule_id,
                    "marker": marker,
                    "status": "generated_missing",
                    "message": f"Generated roots do not contain baseline marker `{marker}`.",
                })
                issue_specs.append(_issue_for_missing_marker(phase, marker, rule_id, goal).to_dict())
            else:
                passed += 1
                checks.append({
                    "rule_id": rule_id,
                    "marker": marker,
                    "status": "passed",
                    "message": f"Marker `{marker}` exists in baseline and generated roots.",
                })

    if baseline_missing:
        status = "baseline_unavailable"
    elif generated_missing:
        status = "failed"
    else:
        status = "passed"

    return {
        "phase": phase,
        "status": status,
        "mode": "no_gpu_static_baseline_compare",
        "generated_roots": [str(path) for path in generated_roots],
        "baseline_roots": [str(path) for path in baseline_roots],
        "checks": checks,
        "issue_specs": issue_specs,
        "summary": {
            "baseline_missing": baseline_missing,
            "generated_missing": generated_missing,
            "passed": passed,
        },
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(report, sort_keys=False, allow_unicode=True))


def load_report(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"Invalid comparator report YAML: {path}")
    return data
```

- [ ] **Step 4: Run comparator tests and verify they pass**

Run:

```bash
python3 -m pytest skills/adapt_issue_loop/tests/test_comparator.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add skills/adapt_issue_loop/scripts/comparator.py skills/adapt_issue_loop/tests/test_comparator.py
git commit -m "feat: add static baseline comparator" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Implement GitHub Issue Sync with Dry-Run and Mockable gh Mode

**Files:**
- Modify: `skills/adapt_issue_loop/scripts/github.py`
- Create: `skills/adapt_issue_loop/tests/test_github.py`

- [ ] **Step 1: Write failing GitHub tests**

Create `skills/adapt_issue_loop/tests/test_github.py`:

```python
import importlib.util
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
GH_SCRIPT = ROOT / "scripts" / "github.py"
ISSUE_SCRIPT = ROOT / "scripts" / "issue_spec.py"

ISSUE_SPEC = importlib.util.spec_from_file_location("issue_loop_issue_spec", ISSUE_SCRIPT)
issue_spec = importlib.util.module_from_spec(ISSUE_SPEC)
assert ISSUE_SPEC and ISSUE_SPEC.loader
ISSUE_SPEC.loader.exec_module(issue_spec)

GH_SPEC = importlib.util.spec_from_file_location("issue_loop_github", GH_SCRIPT)
github = importlib.util.module_from_spec(GH_SPEC)
assert GH_SPEC and GH_SPEC.loader
GH_SPEC.loader.exec_module(github)


def _spec():
    return issue_spec.IssueSpec(
        dedup_key="phase0:missing_mtp_num_layers:baseline_static_compare",
        phase=0,
        title="[Phase 0][DS V4] generated artifacts miss baseline marker `mtp_num_layers`",
        kind="verification-failure",
        severity="blocker",
        goal_blocked="Phase 0 blocks Phase 1.",
        observed="Generated artifacts miss mtp_num_layers.",
        expected="Generated artifacts contain mtp_num_layers.",
        reproduction={"commands": ["cmd"], "artifacts": ["report.yml"]},
        acceptance=["Generated artifacts contain mtp_num_layers"],
        labels=["loongforge-adapt", "phase-0"],
    )


def test_sync_issue_dry_run_returns_create_payload():
    result = github.sync_issue(repo="owner/repo", spec=_spec(), dry_run=True)
    assert result["mode"] == "dry-run"
    assert result["action"] == "create"
    assert result["repo"] == "owner/repo"
    assert result["title"].startswith("[Phase 0]")
    assert "Dedup key" in result["body"]
    assert result["labels"] == ["loongforge-adapt", "phase-0"]


def test_sync_issue_apply_creates_when_no_existing_issue(monkeypatch):
    calls = []

    def fake_run(cmd, capture_output=True, text=True, check=False):
        calls.append(cmd)
        if cmd[:3] == ["gh", "issue", "list"]:
            return SimpleNamespace(returncode=0, stdout="[]", stderr="")
        if cmd[:3] == ["gh", "issue", "create"]:
            return SimpleNamespace(returncode=0, stdout="https://github.com/owner/repo/issues/12\n", stderr="")
        raise AssertionError(cmd)

    monkeypatch.setattr(github.subprocess, "run", fake_run)
    result = github.sync_issue(repo="owner/repo", spec=_spec(), dry_run=False)
    assert result["action"] == "create"
    assert result["issue_url"].endswith("/12")
    assert any(cmd[:3] == ["gh", "issue", "create"] for cmd in calls)


def test_sync_issue_apply_comments_when_existing_issue_found(monkeypatch):
    calls = []

    def fake_run(cmd, capture_output=True, text=True, check=False):
        calls.append(cmd)
        if cmd[:3] == ["gh", "issue", "list"]:
            return SimpleNamespace(returncode=0, stdout='[{"number":7,"url":"https://github.com/owner/repo/issues/7"}]', stderr="")
        if cmd[:3] == ["gh", "issue", "comment"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(cmd)

    monkeypatch.setattr(github.subprocess, "run", fake_run)
    result = github.sync_issue(repo="owner/repo", spec=_spec(), dry_run=False)
    assert result["action"] == "update"
    assert result["issue_number"] == 7
    assert any(cmd[:3] == ["gh", "issue", "comment"] for cmd in calls)
```

- [ ] **Step 2: Run GitHub tests and verify they fail**

Run:

```bash
python3 -m pytest skills/adapt_issue_loop/tests/test_github.py -q
```

Expected: FAIL because `sync_issue` is not defined.

- [ ] **Step 3: Implement GitHub issue sync**

Replace `skills/adapt_issue_loop/scripts/github.py` with:

```python
"""GitHub issue sync helpers for loongforge-issue-loop."""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any


_HERE = Path(__file__).resolve().parent
_ISSUE_SPEC = importlib.util.spec_from_file_location("issue_loop_issue_spec", _HERE / "issue_spec.py")
issue_spec = importlib.util.module_from_spec(_ISSUE_SPEC)
assert _ISSUE_SPEC and _ISSUE_SPEC.loader
_ISSUE_SPEC.loader.exec_module(issue_spec)


def _run_gh(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def _find_issue(repo: str, dedup_key: str) -> dict[str, Any] | None:
    result = _run_gh([
        "gh",
        "issue",
        "list",
        "--repo",
        repo,
        "--state",
        "all",
        "--search",
        f'"{dedup_key}" in:body',
        "--json",
        "number,url,state,title",
        "--limit",
        "10",
    ])
    if result.returncode != 0:
        raise RuntimeError(f"gh issue list failed: {result.stderr.strip()}")
    issues = json.loads(result.stdout or "[]")
    for item in issues:
        if item.get("number"):
            return item
    return None


def _create_issue(repo: str, spec: issue_spec.IssueSpec, body: str) -> str:
    cmd = ["gh", "issue", "create", "--repo", repo, "--title", spec.title, "--body", body]
    for label in spec.labels:
        cmd.extend(["--label", label])
    result = _run_gh(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"gh issue create failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _comment_issue(repo: str, number: int, body: str) -> None:
    result = _run_gh(["gh", "issue", "comment", str(number), "--repo", repo, "--body", body])
    if result.returncode != 0:
        raise RuntimeError(f"gh issue comment failed: {result.stderr.strip()}")


def sync_issue(repo: str, spec: issue_spec.IssueSpec, dry_run: bool) -> dict[str, Any]:
    body = spec.render_markdown()
    if dry_run:
        return {
            "mode": "dry-run",
            "action": "create",
            "repo": repo,
            "title": spec.title,
            "body": body,
            "labels": spec.labels,
            "dedup_key": spec.dedup_key,
        }

    existing = _find_issue(repo, spec.dedup_key)
    if existing:
        number = int(existing["number"])
        _comment_issue(repo, number, "New evidence for this deduplicated issue:\n\n" + body)
        return {
            "mode": "apply",
            "action": "update",
            "repo": repo,
            "issue_number": number,
            "issue_url": existing.get("url"),
            "dedup_key": spec.dedup_key,
        }

    url = _create_issue(repo, spec, body)
    return {
        "mode": "apply",
        "action": "create",
        "repo": repo,
        "issue_url": url,
        "dedup_key": spec.dedup_key,
    }
```

- [ ] **Step 4: Run GitHub tests and verify they pass**

Run:

```bash
python3 -m pytest skills/adapt_issue_loop/tests/test_github.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add skills/adapt_issue_loop/scripts/github.py skills/adapt_issue_loop/tests/test_github.py
git commit -m "feat: add github issue sync" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Implement Merge-Gate Verification Helper

**Files:**
- Modify: `skills/adapt_issue_loop/scripts/verification.py`
- Create: `skills/adapt_issue_loop/tests/test_verification.py`

- [ ] **Step 1: Write failing merge-gate tests**

Create `skills/adapt_issue_loop/tests/test_verification.py`:

```python
import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verification.py"
SPEC = importlib.util.spec_from_file_location("issue_loop_verification", SCRIPT)
verification = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(verification)


def _passing_inputs():
    return {
        "issue_acceptance_passed": True,
        "review_verdict": "approved",
        "plugin_tests_passed": True,
        "phase_artifact_gate_passed": True,
        "static_comparator_passed": True,
        "downstream_readiness_passed": True,
        "working_tree_clean": True,
        "pr_mergeable": True,
        "gpu_gate_blocking": False,
    }


def test_merge_gate_passes_when_all_inputs_pass():
    result = verification.evaluate_merge_gate(_passing_inputs())
    assert result["status"] == "passed"
    assert result["blocking_reasons"] == []


def test_merge_gate_blocks_failed_review():
    data = _passing_inputs()
    data["review_verdict"] = "changes_requested"
    result = verification.evaluate_merge_gate(data)
    assert result["status"] == "blocked"
    assert "review_verdict" in result["blocking_reasons"]


def test_merge_gate_blocks_gpu_gate_marked_blocking():
    data = _passing_inputs()
    data["gpu_gate_blocking"] = True
    result = verification.evaluate_merge_gate(data)
    assert result["status"] == "blocked"
    assert "gpu_gate_blocking" in result["blocking_reasons"]


def test_merge_gate_reports_all_failed_booleans():
    data = _passing_inputs()
    data["plugin_tests_passed"] = False
    data["static_comparator_passed"] = False
    data["working_tree_clean"] = False
    result = verification.evaluate_merge_gate(data)
    assert result["status"] == "blocked"
    assert result["blocking_reasons"] == [
        "plugin_tests_passed",
        "static_comparator_passed",
        "working_tree_clean",
    ]
```

- [ ] **Step 2: Run merge-gate tests and verify they fail**

Run:

```bash
python3 -m pytest skills/adapt_issue_loop/tests/test_verification.py -q
```

Expected: FAIL because `evaluate_merge_gate` is not defined.

- [ ] **Step 3: Implement merge-gate helper**

Replace `skills/adapt_issue_loop/scripts/verification.py` with:

```python
"""Merge-gate verification helpers for loongforge-issue-loop."""
from __future__ import annotations

from typing import Any


BOOLEAN_GATES = [
    "issue_acceptance_passed",
    "plugin_tests_passed",
    "phase_artifact_gate_passed",
    "static_comparator_passed",
    "downstream_readiness_passed",
    "working_tree_clean",
    "pr_mergeable",
]


def evaluate_merge_gate(inputs: dict[str, Any]) -> dict[str, Any]:
    blocking: list[str] = []
    for key in BOOLEAN_GATES:
        if inputs.get(key) is not True:
            blocking.append(key)

    if inputs.get("review_verdict") != "approved":
        blocking.append("review_verdict")

    if inputs.get("gpu_gate_blocking") is True:
        blocking.append("gpu_gate_blocking")

    return {
        "status": "passed" if not blocking else "blocked",
        "blocking_reasons": blocking,
        "mode": "no_gpu_static_validation",
    }
```

- [ ] **Step 4: Run merge-gate tests and verify they pass**

Run:

```bash
python3 -m pytest skills/adapt_issue_loop/tests/test_verification.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add skills/adapt_issue_loop/scripts/verification.py skills/adapt_issue_loop/tests/test_verification.py
git commit -m "feat: add merge gate evaluator" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Implement CLI Subcommands

**Files:**
- Modify: `skills/adapt_issue_loop/scripts/run.py`
- Create: `skills/adapt_issue_loop/tests/test_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Create `skills/adapt_issue_loop/tests/test_cli.py`:

```python
import json
import subprocess
import sys
from pathlib import Path

import yaml


SKILL_ROOT = Path(__file__).resolve().parents[1]
RUN = SKILL_ROOT / "scripts" / "run.py"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_cli_init_creates_state(tmp_path):
    result = subprocess.run(
        [sys.executable, str(RUN), "init", "--plugin-root", str(tmp_path), "--repo", "owner/repo"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    state_dir = Path(result.stdout.strip())
    assert (state_dir / "state.yml").exists()
    data = yaml.safe_load((state_dir / "state.yml").read_text())
    assert data["repo"] == "owner/repo"


def test_cli_compare_phase_writes_report(tmp_path):
    baseline = tmp_path / "baseline"
    generated = tmp_path / "generated"
    state_dir = tmp_path / ".loongforge" / "issue-loop"
    _write(baseline / "deepseek_v4_config.py", "mtp_num_layers = 1\nqk_rope_head_dim = 64\no_lora_rank = 1024\n")
    _write(generated / "model_spec.yaml", "qk_rope_head_dim: 64\no_lora_rank: 1024\n")

    init = subprocess.run(
        [sys.executable, str(RUN), "init", "--plugin-root", str(tmp_path), "--repo", "owner/repo"],
        capture_output=True,
        text=True,
    )
    assert init.returncode == 0, init.stderr

    report_path = tmp_path / "report.yml"
    result = subprocess.run(
        [
            sys.executable,
            str(RUN),
            "compare-phase",
            "--phase",
            "0",
            "--generated-root",
            str(generated),
            "--baseline-root",
            str(baseline),
            "--state-dir",
            str(state_dir),
            "--report-out",
            str(report_path),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    report = yaml.safe_load(report_path.read_text())
    assert report["status"] == "failed"
    assert report["issue_specs"]


def test_cli_issue_from_report_writes_issue_specs(tmp_path):
    report = {
        "phase": 0,
        "status": "failed",
        "issue_specs": [
            {
                "dedup_key": "phase0:missing_mtp_num_layers:baseline_static_compare",
                "phase": 0,
                "title": "[Phase 0][DS V4] generated artifacts miss baseline marker `mtp_num_layers`",
                "kind": "verification-failure",
                "severity": "blocker",
                "goal_blocked": "Phase 0 blocks Phase 1.",
                "observed": "Generated artifacts miss mtp_num_layers.",
                "expected": "Generated artifacts contain mtp_num_layers.",
                "reproduction": {"commands": ["cmd"], "artifacts": ["report.yml"]},
                "acceptance": ["Generated artifacts contain mtp_num_layers"],
                "labels": ["phase-0"],
            }
        ],
    }
    report_path = tmp_path / "report.yml"
    report_path.write_text(yaml.dump(report, sort_keys=False))
    out_dir = tmp_path / "issues"
    result = subprocess.run(
        [sys.executable, str(RUN), "issue-from-report", "--report", str(report_path), "--out-dir", str(out_dir)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    written = json.loads(result.stdout)
    assert len(written["issue_specs"]) == 1
    assert Path(written["issue_specs"][0]).exists()


def test_cli_verify_merge_gate_outputs_blocked(tmp_path):
    gate_path = tmp_path / "gate.yml"
    gate_path.write_text(yaml.dump({"review_verdict": "approved"}, sort_keys=False))
    result = subprocess.run(
        [sys.executable, str(RUN), "verify-merge-gate", "--inputs", str(gate_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    data = json.loads(result.stdout)
    assert data["status"] == "blocked"
```

- [ ] **Step 2: Run CLI tests and verify they fail**

Run:

```bash
python3 -m pytest skills/adapt_issue_loop/tests/test_cli.py -q
```

Expected: FAIL because subcommands are stubs.

- [ ] **Step 3: Implement CLI dispatcher**

Replace `skills/adapt_issue_loop/scripts/run.py` with:

```python
#!/usr/bin/env python3
"""LoongForge issue-driven adapt loop CLI."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import yaml


DESCRIPTION = "LoongForge issue-driven adapt loop"
_HERE = Path(__file__).resolve().parent


def _load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _HERE / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


state = _load_module("issue_loop_state", "state.py")
comparator = _load_module("issue_loop_comparator", "comparator.py")
issue_spec = _load_module("issue_loop_issue_spec", "issue_spec.py")
github = _load_module("issue_loop_github", "github.py")
verification = _load_module("issue_loop_verification", "verification.py")


def cmd_init(args: argparse.Namespace) -> int:
    state_dir = state.init_loop_state(plugin_root=Path(args.plugin_root), repo=args.repo)
    print(state_dir)
    return 0


def cmd_compare_phase(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir)
    contract = state.load_goal_contract(state_dir)
    generated_roots = [Path(value) for value in args.generated_root]
    baseline_roots = [Path(value) for value in args.baseline_root]
    report = comparator.compare_phase_to_baseline(
        phase=args.phase,
        generated_roots=generated_roots,
        baseline_roots=baseline_roots,
        goal_contract=contract,
    )
    comparator.write_report(Path(args.report_out), report)
    print(args.report_out)
    return 0


def cmd_issue_from_report(args: argparse.Namespace) -> int:
    report = comparator.load_report(Path(args.report))
    out_dir = Path(args.out_dir)
    written: list[str] = []
    for raw in report.get("issue_specs") or []:
        spec = issue_spec.IssueSpec.from_dict(raw)
        written.append(str(issue_spec.write_issue_spec(out_dir, spec)))
    print(json.dumps({"issue_specs": written}, indent=2))
    return 0


def cmd_sync_issue(args: argparse.Namespace) -> int:
    spec = issue_spec.load_issue_spec(Path(args.issue_spec))
    result = github.sync_issue(repo=args.repo, spec=spec, dry_run=args.dry_run)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_verify_merge_gate(args: argparse.Namespace) -> int:
    inputs = yaml.safe_load(Path(args.inputs).read_text())
    if not isinstance(inputs, dict):
        raise ValueError(f"Expected YAML mapping at {args.inputs}")
    result = verification.evaluate_merge_gate(inputs)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "passed" else 2


def cmd_run_dry(args: argparse.Namespace) -> int:
    state_dir = state.init_loop_state(plugin_root=Path(args.plugin_root), repo=args.repo)
    contract = state.load_goal_contract(state_dir)
    report = comparator.compare_phase_to_baseline(
        phase=args.phase,
        generated_roots=[Path(value) for value in args.generated_root],
        baseline_roots=[Path(value) for value in args.baseline_root],
        goal_contract=contract,
    )
    report_path = state_dir / "comparator_reports" / f"phase{args.phase}-dry-run.yml"
    comparator.write_report(report_path, report)
    issue_paths: list[str] = []
    dry_sync: list[dict] = []
    for raw in report.get("issue_specs") or []:
        spec = issue_spec.IssueSpec.from_dict(raw)
        path = issue_spec.write_issue_spec(state_dir / "issue_specs", spec)
        issue_paths.append(str(path))
        dry_sync.append(github.sync_issue(repo=args.repo, spec=spec, dry_run=True))
    print(json.dumps({
        "state_dir": str(state_dir),
        "report": str(report_path),
        "status": report["status"],
        "issue_specs": issue_paths,
        "dry_sync": dry_sync,
    }, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument("--version", action="version", version="loongforge-issue-loop 0.1.0")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Initialize local issue-loop state")
    p_init.add_argument("--plugin-root", required=True)
    p_init.add_argument("--repo", default=state.DEFAULT_REPO)
    p_init.set_defaults(func=cmd_init)

    p_compare = sub.add_parser("compare-phase", help="Compare a phase against static baseline rules")
    p_compare.add_argument("--phase", required=True, type=int, choices=[0, 1, 2, 3, 4])
    p_compare.add_argument("--generated-root", action="append", required=True)
    p_compare.add_argument("--baseline-root", action="append", required=True)
    p_compare.add_argument("--state-dir", required=True)
    p_compare.add_argument("--report-out", required=True)
    p_compare.set_defaults(func=cmd_compare_phase)

    p_issue = sub.add_parser("issue-from-report", help="Create IssueSpec files from a comparator report")
    p_issue.add_argument("--report", required=True)
    p_issue.add_argument("--out-dir", required=True)
    p_issue.set_defaults(func=cmd_issue_from_report)

    p_sync = sub.add_parser("sync-issue", help="Create or update a GitHub Issue from an IssueSpec")
    p_sync.add_argument("--issue-spec", required=True)
    p_sync.add_argument("--repo", required=True)
    mode = p_sync.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    p_sync.set_defaults(func=cmd_sync_issue)

    p_gate = sub.add_parser("verify-merge-gate", help="Evaluate deterministic merge-gate inputs")
    p_gate.add_argument("--inputs", required=True)
    p_gate.set_defaults(func=cmd_verify_merge_gate)

    p_run_dry = sub.add_parser("run-dry", help="Run local dry-run pipeline without touching GitHub")
    p_run_dry.add_argument("--plugin-root", required=True)
    p_run_dry.add_argument("--repo", default=state.DEFAULT_REPO)
    p_run_dry.add_argument("--phase", required=True, type=int, choices=[0, 1, 2])
    p_run_dry.add_argument("--generated-root", action="append", required=True)
    p_run_dry.add_argument("--baseline-root", action="append", required=True)
    p_run_dry.set_defaults(func=cmd_run_dry)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run CLI tests and verify they pass**

Run:

```bash
python3 -m pytest skills/adapt_issue_loop/tests/test_cli.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add skills/adapt_issue_loop/scripts/run.py skills/adapt_issue_loop/tests/test_cli.py
git commit -m "feat: add issue loop cli" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: Add End-to-End Dry-Run Coverage and Documentation Checks

**Files:**
- Modify: `skills/adapt_issue_loop/tests/test_cli.py`
- Modify: `README.md`
- Modify: `skills/adapt_issue_loop/SKILL.md`

- [ ] **Step 1: Add a dry-run pipeline test**

Append this test to `skills/adapt_issue_loop/tests/test_cli.py`:

```python

def test_cli_run_dry_creates_report_issue_spec_and_dry_sync_payload(tmp_path):
    baseline = tmp_path / "baseline"
    generated = tmp_path / "generated"
    _write(baseline / "deepseek_v4_config.py", "mtp_num_layers = 1\nqk_rope_head_dim = 64\no_lora_rank = 1024\n")
    _write(generated / "model_spec.yaml", "qk_rope_head_dim: 64\no_lora_rank: 1024\n")

    result = subprocess.run(
        [
            sys.executable,
            str(RUN),
            "run-dry",
            "--plugin-root",
            str(tmp_path),
            "--repo",
            "owner/repo",
            "--phase",
            "0",
            "--generated-root",
            str(generated),
            "--baseline-root",
            str(baseline),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert Path(payload["report"]).exists()
    assert len(payload["issue_specs"]) == 1
    assert payload["dry_sync"][0]["mode"] == "dry-run"
    assert payload["dry_sync"][0]["action"] == "create"
```

- [ ] **Step 2: Run the dry-run test and verify it passes**

Run:

```bash
python3 -m pytest skills/adapt_issue_loop/tests/test_cli.py::test_cli_run_dry_creates_report_issue_spec_and_dry_sync_payload -q
```

Expected: PASS.

- [ ] **Step 3: Strengthen skill document with repair/review commands**

In `skills/adapt_issue_loop/SKILL.md`, add this section after `## Deterministic CLI Layer`:

```markdown
## Repair PR Loop

For each synced GitHub Issue:

1. Fetch the issue body and linked IssueSpec.
2. Create branch `agent/issue-<number>-<short-slug>`.
3. Prove the issue by rerunning the comparator command or by citing artifact-level evidence.
4. Modify only plugin files required by the issue.
5. Run targeted tests and the relevant comparator.
6. Commit with `Fixes #<number>` or `Closes #<number>` in the PR body.
7. Push the branch and create a PR.

## Review and Merge Gate

Review agent must evaluate:

- PR scope matches exactly one linked issue.
- Issue acceptance checklist passes.
- Plugin tests pass.
- Phase artifact gate passes when an artifact exists.
- DS V4 static comparator passes.
- Downstream readiness is not blocked.
- No GPU-only gate is treated as a local blocking gate.

Before merge, write a gate input YAML and run:

```bash
loongforge-issue-loop verify-merge-gate --inputs <gate.yml>
```

Only merge when the command exits 0 and review verdict is `approved`.
```

- [ ] **Step 4: Update README with dry-run and apply examples**

Add this section to `README.md`:

```markdown
## Issue-Driven Adapt Loop

`/loongforge:adapt_issue_loop` is a local-first iteration loop for Phase 0-2 DS V4 adaptation on a Mac without GPU. It compares generated phase artifacts/code/conversion rules with baseline code, writes IssueSpec files, and can create or update GitHub Issues.

Dry-run example:

```bash
loongforge-issue-loop run-dry \
  --plugin-root . \
  --repo Zachary-wW/loongforge-plugin \
  --phase 0 \
  --generated-root <run_dir>/phases/phase0 \
  --baseline-root ../baidu/hac-aiacc/AIAK-Megatron \
  --baseline-root ../baidu/hac-aiacc/AIAK-Training-Omni
```

Real issue sync example:

```bash
loongforge-issue-loop sync-issue \
  --repo Zachary-wW/loongforge-plugin \
  --issue-spec .loongforge/issue-loop/issue_specs/<issue>.yml \
  --apply
```
```

- [ ] **Step 5: Run layout and CLI tests**

Run:

```bash
python3 -m pytest skills/adapt_issue_loop/tests/test_layout.py skills/adapt_issue_loop/tests/test_cli.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add skills/adapt_issue_loop/SKILL.md skills/adapt_issue_loop/tests/test_cli.py README.md
git commit -m "docs: document issue loop dry run" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 9: Run Full Test Suite and Fix Integration Regressions

**Files:**
- Modify only files touched in Tasks 1-8 if tests expose concrete failures.

- [ ] **Step 1: Run all new issue-loop tests**

Run:

```bash
python3 -m pytest skills/adapt_issue_loop/tests -q
```

Expected: PASS.

- [ ] **Step 2: Run existing adapt tests likely affected by plugin layout**

Run:

```bash
python3 -m pytest skills/adapt/tests/test_plugin_layout.py skills/adapt/tests/test_runner.py -q
```

Expected: PASS.

- [ ] **Step 3: Run the full available plugin test suite**

Run:

```bash
python3 -m pytest skills/adapt/tests skills/adapt_issue_loop/tests -q
```

Expected: PASS or SKIP only for tests that already skip when external reference trees are absent. If a test fails, keep the failing output, fix the smallest relevant code path, and rerun this exact command until it passes.

- [ ] **Step 4: Run a real local dry-run against current baseline paths when directories exist**

Run:

```bash
loongforge-issue-loop run-dry \
  --plugin-root . \
  --repo Zachary-wW/loongforge-plugin \
  --phase 0 \
  --generated-root skills/adapt/knowledge_base/sources/llm \
  --baseline-root ../baidu/hac-aiacc/AIAK-Megatron \
  --baseline-root ../baidu/hac-aiacc/AIAK-Training-Omni
```

Expected: command exits 0 and prints JSON with `state_dir`, `report`, `status`, `issue_specs`, and `dry_sync`. `status` may be `passed`, `failed`, or `baseline_unavailable`; `failed` is acceptable for this smoke command because it proves the dry-run issue payload path works.

- [ ] **Step 5: Check git status**

Run:

```bash
git status --short
```

Expected: only intentional files are modified.

- [ ] **Step 6: Commit final test fixes if any files changed after Task 8**

If Task 9 changed files, run:

```bash
git add skills/adapt_issue_loop skills/adapt README.md
git commit -m "test: verify issue loop integration" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

If Task 9 changed no files, do not create an empty commit.

---

## Self-Review Checklist

Spec coverage:

- Local execution + GitHub ledger: Tasks 1, 5, 7, 8.
- State store and mutable goal contract: Task 2.
- IssueSpec with dedup key and GitHub issue template: Task 3.
- No-GPU Phase 0-2 static baseline comparator: Task 4.
- GitHub issue create/update dry-run and apply modes: Task 5.
- Review/verification merge gates: Task 6 and Task 8.
- CLI wrapper and dry-run/apply paths: Tasks 1, 7, 8.
- Phase 3/4 deferred semantics: Task 2 and Task 4.
- Tests: Tasks 1-9.

Type consistency:

- `IssueSpec` fields are consistent across `issue_spec.py`, `comparator.py`, `github.py`, and CLI tests.
- Comparator reports use `issue_specs` as a list of dictionaries produced by `IssueSpec.to_dict()`.
- `state_dir` always points to `.loongforge/issue-loop` and contains `state.yml` plus `phase_goal_contract.yml`.
- Merge gate inputs use the exact keys in `verification.BOOLEAN_GATES` plus `review_verdict` and `gpu_gate_blocking`.

Execution notes:

- Start with Task 1 and commit after every task.
- Do not skip failing-test steps.
- Do not touch Phase 3/4 runtime validators in this MVP.
- Do not make real GitHub issues during tests; use `--dry-run` or monkeypatched subprocess calls.
