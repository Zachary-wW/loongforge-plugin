#!/usr/bin/env python3
"""LoongForge issue-driven adapt loop CLI."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml


DESCRIPTION = "LoongForge issue-driven adapt loop"
_HERE = Path(__file__).resolve().parent


def _load_module(name: str) -> ModuleType:
    """Load a sibling script module without requiring package installation."""
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    path = _HERE / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


issue_spec = _load_module("issue_spec")
state = _load_module("state")
comparator = _load_module("comparator")
github = _load_module("github")
verification = _load_module("verification")


def _json_print(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True))


def _legacy_not_implemented(parser: argparse.ArgumentParser, command: str) -> None:
    """Preserve the early skeleton contract for placeholder-only invocations."""
    parser.error(f"subcommand not implemented yet: {command}")


def _parse_phase(value: str | int | None) -> int:
    if value is None:
        raise ValueError("--phase is required")
    raw = str(value).strip().lower()
    for prefix in ("phase-", "phase"):
        if raw.startswith(prefix):
            raw = raw[len(prefix) :]
            break
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid phase value: {value}") from exc


def _paths(values: list[str] | None, option_name: str) -> list[Path]:
    if not values:
        raise ValueError(f"{option_name} is required")
    return [Path(value) for value in values]


def _default_plugin_root(value: str | None) -> Path:
    return Path(value) if value else Path.cwd()


def _validate_target(target: str | None) -> None:
    if target is None:
        return
    normalized = target.strip().lower().replace("-", "_")
    if normalized != state.DEFAULT_TARGET:
        raise ValueError(f"unsupported target: {target}; only ds-v4 is supported")


def _baseline_roots_from_state(loop_state: Mapping[str, Any]) -> list[Path]:
    baseline = loop_state.get("baseline")
    if not isinstance(baseline, Mapping):
        return []
    roots: list[Path] = []
    for item in baseline.values():
        if isinstance(item, Mapping) and item.get("path"):
            roots.append(Path(str(item["path"])))
    return roots


def _compare_paths(args: argparse.Namespace) -> tuple[Path, list[Path], list[Path], Path]:
    plugin_root = _default_plugin_root(getattr(args, "plugin_root", None))
    state_dir = Path(args.state_dir) if args.state_dir else state.init_loop_state(plugin_root, repo=state.DEFAULT_REPO)
    phase = _parse_phase(args.phase)

    if args.generated_roots:
        generated_roots = _paths(args.generated_roots, "--generated-root")
    elif args.run_dir:
        generated_roots = [Path(args.run_dir) / "phases" / f"phase{phase}"]
    else:
        raise ValueError("compare-phase requires --run-dir or --generated-root")

    if args.baseline_roots:
        baseline_roots = _paths(args.baseline_roots, "--baseline-root")
    else:
        baseline_roots = _baseline_roots_from_state(state.load_state(state_dir))
        if not baseline_roots:
            raise ValueError("compare-phase requires --baseline-root or baseline paths in state.yml")

    report_path = (
        Path(args.report_out)
        if args.report_out
        else state_dir / "comparator_reports" / f"phase{phase}-report.yml"
    )
    return state_dir, generated_roots, baseline_roots, report_path


def _load_yaml_mapping(path: Path, label: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid {label} YAML: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be a YAML mapping: {path}")
    return data


def _issue_specs_from_report(report: Mapping[str, Any], out_dir: Path) -> list[tuple[Path, Any]]:
    raw_specs = report.get("issue_specs", [])
    if raw_specs is None:
        raw_specs = []
    if not isinstance(raw_specs, list):
        raise ValueError("report.issue_specs must be a list")

    written: list[tuple[Path, Any]] = []
    for index, raw_spec in enumerate(raw_specs):
        if not isinstance(raw_spec, Mapping):
            raise ValueError(f"report.issue_specs[{index}] must be a mapping")
        spec = issue_spec.IssueSpec.from_dict(dict(raw_spec))
        path = issue_spec.write_issue_spec(out_dir, spec)
        written.append((path, spec))
    return written


def _cmd_init(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    _validate_target(args.target)
    plugin_root = _default_plugin_root(args.plugin_root)
    state_dir = state.init_loop_state(plugin_root, repo=args.repo or state.DEFAULT_REPO, force=args.force)
    print(state_dir)
    return 0


def _cmd_compare_phase(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    phase = _parse_phase(args.phase)
    state_dir, generated_roots, baseline_roots, report_path = _compare_paths(args)
    goal_contract = state.load_goal_contract(state_dir)
    if not isinstance(goal_contract, dict):
        raise ValueError(f"Goal contract must be a YAML mapping: {state_dir / 'phase_goal_contract.yml'}")

    report = comparator.compare_phase_to_baseline(
        phase=phase,
        generated_roots=generated_roots,
        baseline_roots=baseline_roots,
        goal_contract=goal_contract,
    )
    comparator.write_report(report_path, report)
    print(report_path)
    return 0


def _cmd_issue_from_report(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.report is None or args.out_dir is None:
        parser.error("issue-from-report requires --report and --out-dir")

    report = comparator.load_report(Path(args.report))
    written = _issue_specs_from_report(report, Path(args.out_dir))
    _json_print({"issue_specs": [str(path) for path, _ in written]})
    return 0


def _cmd_sync_issue(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.repo is None:
        _legacy_not_implemented(parser, "sync-issue")
    if args.issue_spec is None:
        parser.error("sync-issue requires --issue-spec")
    if args.dry_run == args.apply:
        parser.error("sync-issue requires exactly one of --dry-run or --apply")

    spec = issue_spec.load_issue_spec(Path(args.issue_spec))
    payload = github.sync_issue(args.repo, spec, dry_run=args.dry_run)
    _json_print(payload)
    return 0


def _cmd_verify_merge_gate(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.inputs is None:
        parser.error("verify-merge-gate requires --inputs")

    inputs = _load_yaml_mapping(Path(args.inputs), "merge gate inputs")
    result = verification.evaluate_merge_gate(inputs)
    _json_print(result)
    return 0 if result.get("status") == "passed" else 2


def _cmd_run_dry(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if not all([args.plugin_root, args.generated_roots, args.baseline_roots]):
        parser.error("run-dry requires --plugin-root, --generated-root, and --baseline-root")

    repo = args.repo or state.DEFAULT_REPO
    phase = _parse_phase(args.phase)
    state_dir = state.init_loop_state(Path(args.plugin_root), repo=repo)
    goal_contract = state.load_goal_contract(state_dir)
    report = comparator.compare_phase_to_baseline(
        phase=phase,
        generated_roots=_paths(args.generated_roots, "--generated-root"),
        baseline_roots=_paths(args.baseline_roots, "--baseline-root"),
        goal_contract=goal_contract,
    )

    report_path = state_dir / "comparator_reports" / f"phase{phase}-dry-run.yml"
    comparator.write_report(report_path, report)
    written = _issue_specs_from_report(report, state_dir / "issue_specs")
    sync_payloads = [github.sync_issue(repo, spec, dry_run=True) for _, spec in written]
    _json_print(
        {
            "state_dir": str(state_dir),
            "report": str(report_path),
            "comparator_report": str(report_path),
            "status": report.get("status"),
            "issue_specs": [str(path) for path, _ in written],
            "dry_sync": sync_payloads,
            "sync_payloads": sync_payloads,
        }
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument("--version", action="version", version="loongforge-issue-loop 0.1.0")
    sub = parser.add_subparsers(dest="command")

    init = sub.add_parser("init", help="Initialize local issue-loop state")
    init.add_argument("--plugin-root", help="Plugin root where .loongforge/issue-loop will be created (default: current directory)")
    init.add_argument("--target", help="Target identifier; only ds-v4 is supported")
    init.add_argument("--repo", help="Repository path or slug")
    init.add_argument("--force", action="store_true", help="Overwrite existing state.yml and phase_goal_contract.yml")
    init.set_defaults(func=_cmd_init)

    compare_phase = sub.add_parser("compare-phase", help="Compare a phase against static baseline rules")
    compare_phase.add_argument("--phase", help="Phase identifier to compare")
    compare_phase.add_argument("--plugin-root", help="Plugin root for default state directory (default: current directory)")
    compare_phase.add_argument("--run-dir", help="Run directory containing comparator inputs")
    compare_phase.add_argument("--generated-root", dest="generated_roots", action="append", help="Generated artifact root to scan")
    compare_phase.add_argument("--baseline-root", dest="baseline_roots", action="append", help="Baseline source root to scan")
    compare_phase.add_argument("--state-dir", help="Issue-loop state directory containing phase_goal_contract.yml")
    compare_phase.add_argument("--report-out", help="Comparator report YAML path to write")
    compare_phase.set_defaults(func=_cmd_compare_phase)

    issue_from_report = sub.add_parser("issue-from-report", help="Create IssueSpec files from a comparator report")
    issue_from_report.add_argument("--report", help="Comparator report YAML path")
    issue_from_report.add_argument("--out-dir", help="Directory where IssueSpec YAML files will be written")
    issue_from_report.set_defaults(func=_cmd_issue_from_report)

    sync_issue = sub.add_parser("sync-issue", help="Create or update a GitHub Issue from an IssueSpec")
    sync_issue.add_argument("--issue-spec", help="Path to an IssueSpec file")
    sync_issue.add_argument("--repo", help="Repository slug, for example owner/repo")
    sync_issue.add_argument("--dry-run", action="store_true", help="Parse and validate without changing GitHub")
    sync_issue.add_argument("--apply", action="store_true", help="Create or update the GitHub issue")
    sync_issue.set_defaults(func=_cmd_sync_issue)

    verify = sub.add_parser("verify-merge-gate", help="Evaluate deterministic merge-gate inputs")
    verify.add_argument("--inputs", help="YAML mapping with merge-gate inputs")
    verify.set_defaults(func=_cmd_verify_merge_gate)

    run_dry = sub.add_parser("run-dry", help="Run local dry-run pipeline without touching GitHub")
    run_dry.add_argument("--plugin-root", help="Plugin root where state will be initialized")
    run_dry.add_argument("--repo", help="Repository slug, for example owner/repo")
    run_dry.add_argument("--phase", help="Phase identifier to compare", default="0")
    run_dry.add_argument("--generated-root", dest="generated_roots", action="append", help="Generated artifact root to scan")
    run_dry.add_argument("--baseline-root", dest="baseline_roots", action="append", help="Baseline source root to scan")
    run_dry.set_defaults(func=_cmd_run_dry)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0

    try:
        return args.func(args, parser)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
