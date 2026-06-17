"""Static baseline comparator for loongforge-issue-loop."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable

import yaml


_HERE = Path(__file__).resolve().parent
_ISSUE_SPEC_NAME = "issue_loop_issue_spec"


def _load_issue_spec_module() -> ModuleType:
    existing = sys.modules.get(_ISSUE_SPEC_NAME)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(_ISSUE_SPEC_NAME, _HERE / "issue_spec.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load issue_spec.py from {_HERE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


issue_spec = _load_issue_spec_module()

TEXT_SUFFIXES = {".py", ".yaml", ".yml", ".json", ".md", ".sh", ".txt"}


def _read_text_tree(roots: Iterable[Path]) -> str:
    chunks: list[str] = []
    for raw_root in roots:
        root = Path(raw_root)
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


def _issue_for_missing_marker(phase: int, marker: str, rule_id: str, goal: str):
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
