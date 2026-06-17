"""Static baseline comparator for loongforge-issue-loop."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable

import yaml


_HERE = Path(__file__).resolve().parent
_ISSUE_SPEC_NAME = "issue_loop_issue_spec"

TEXT_SUFFIXES = {".py", ".yaml", ".yml", ".json", ".md", ".sh", ".txt"}
SKIP_DIR_NAMES = frozenset({"__pycache__", ".git", "node_modules", ".venv", "venv", "runs", "logs"})
MAX_FILE_BYTES = 1_000_000
MAX_TOTAL_BYTES = 5_000_000
MAX_FILES = 1_000
MAX_SKIPPED_RECORDS = 100


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


def _new_scan_stats() -> dict[str, Any]:
    return {
        "files_read": 0,
        "bytes_read": 0,
        "skipped_count": 0,
        "skipped_by_reason": {},
        "skipped": [],
    }


def _record_skip(stats: dict[str, Any], path: Path, reason: str) -> None:
    stats["skipped_count"] += 1
    skipped_by_reason = stats["skipped_by_reason"]
    skipped_by_reason[reason] = skipped_by_reason.get(reason, 0) + 1
    if len(stats["skipped"]) < MAX_SKIPPED_RECORDS:
        stats["skipped"].append({"path": str(path), "reason": reason})


def _limits_reached(stats: dict[str, Any]) -> bool:
    return stats["files_read"] >= MAX_FILES or stats["bytes_read"] >= MAX_TOTAL_BYTES


def _append_text_file(path: Path, chunks: list[str], stats: dict[str, Any]) -> None:
    if stats["files_read"] >= MAX_FILES:
        _record_skip(stats, path, "max_files_reached")
        return
    if stats["bytes_read"] >= MAX_TOTAL_BYTES:
        _record_skip(stats, path, "max_total_bytes_reached")
        return

    try:
        stat_size = path.stat().st_size
    except OSError:
        _record_skip(stats, path, "stat_failed")
        return

    if stat_size > MAX_FILE_BYTES:
        _record_skip(stats, path, "max_file_bytes_exceeded")
        return

    remaining_total = MAX_TOTAL_BYTES - stats["bytes_read"]
    if stat_size > remaining_total:
        _record_skip(stats, path, "max_total_bytes_exceeded")
        return

    max_read = min(MAX_FILE_BYTES, remaining_total)
    try:
        with path.open("rb") as handle:
            data = handle.read(max_read + 1)
    except OSError:
        _record_skip(stats, path, "read_failed")
        return

    if len(data) > MAX_FILE_BYTES:
        _record_skip(stats, path, "max_file_bytes_exceeded")
        return
    if len(data) > remaining_total:
        _record_skip(stats, path, "max_total_bytes_exceeded")
        return

    chunks.append(data.decode("utf-8", errors="replace"))
    stats["files_read"] += 1
    stats["bytes_read"] += len(data)


def _read_text_tree(roots: Iterable[Path], stats: dict[str, Any] | None = None) -> str:
    scan_stats = stats if stats is not None else _new_scan_stats()
    chunks: list[str] = []
    for raw_root in roots:
        root = Path(raw_root)
        if _limits_reached(scan_stats):
            _record_skip(scan_stats, root, "scan_limit_reached")
            break
        if root.is_file():
            if root.suffix in TEXT_SUFFIXES:
                _append_text_file(root, chunks, scan_stats)
            continue
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            current_dir = Path(dirpath)
            skipped_dirs = [name for name in dirnames if name in SKIP_DIR_NAMES]
            for name in sorted(skipped_dirs):
                _record_skip(scan_stats, current_dir / name, "skipped_directory")
            dirnames[:] = sorted(name for name in dirnames if name not in SKIP_DIR_NAMES)

            if _limits_reached(scan_stats):
                dirnames[:] = []
                break

            for filename in sorted(filenames):
                path = current_dir / filename
                if path.suffix not in TEXT_SUFFIXES:
                    continue
                if _limits_reached(scan_stats):
                    _record_skip(scan_stats, path, "scan_limit_reached")
                    dirnames[:] = []
                    break
                _append_text_file(path, chunks, scan_stats)
    return "\n".join(chunks)


def _phase_key(phase: int) -> str:
    return f"phase{phase}"


def _rules_for_phase(goal_contract: dict[str, Any], phase: int) -> list[dict[str, Any]]:
    phase_key = _phase_key(phase)
    phase_contract = goal_contract.get(phase_key)
    if not isinstance(phase_contract, dict):
        raise ValueError(f"{phase_key}.comparator_rules is required and must be a non-empty list")
    if "comparator_rules" not in phase_contract:
        raise ValueError(f"{phase_key}.comparator_rules is required and must be a non-empty list")
    rules = phase_contract["comparator_rules"]
    if not isinstance(rules, list):
        raise ValueError(f"{phase_key}.comparator_rules must be a list")
    if not rules:
        raise ValueError(f"{phase_key}.comparator_rules must be a non-empty list")
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

    rules = _rules_for_phase(goal_contract, phase)
    baseline_scan = _new_scan_stats()
    generated_scan = _new_scan_stats()
    baseline_text = _read_text_tree(baseline_roots, baseline_scan)
    generated_text = _read_text_tree(generated_roots, generated_scan)
    checks: list[dict[str, Any]] = []
    issue_specs: list[dict[str, Any]] = []
    baseline_missing = 0
    generated_missing = 0
    passed = 0
    goal = _goal_for_phase(goal_contract, phase)

    for rule in rules:
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

    if generated_missing:
        status = "failed"
    elif baseline_missing:
        status = "baseline_unavailable"
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
        "scan_limits": {
            "max_file_bytes": MAX_FILE_BYTES,
            "max_total_bytes": MAX_TOTAL_BYTES,
            "max_files": MAX_FILES,
            "baseline": baseline_scan,
            "generated": generated_scan,
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
