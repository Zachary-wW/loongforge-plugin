#!/usr/bin/env python3
"""
LoongForge Adapt Phase Loop CLI.

Wraps run_phase_loop() for agent-friendly Bash invocation.
Handles GhClient construction, repos_info extraction, and exit-code mapping.

Usage:
  loongforge-phase-loop --run-dir <dir> --phase <N> [--dry-run] [--continue-fix]

Exit codes:
  0  validator_passed or validator_passed_after_fix
  1  exhausted / human_needed / escalated / base_only
  10 FIX_NEEDED — agent must inject fix code, then re-invoke with --continue-fix
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# When invoked via bin/loongforge-phase-loop, the project root is not on sys.path.
_PLUGIN_ROOT = str(Path(__file__).resolve().parents[3])  # .../loongforge-plugin
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

from skills.adapt.lib.loop_controller import run_phase_loop, ExitReason
from skills.adapt.lib.gh_client import FakeGhClient, RealGhClient
from skills.adapt.lib.schema import RunInputs, LoopBudget


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_run_inputs(run_dir: Path) -> RunInputs:
    """Load and validate run_inputs.yml from the run directory."""
    yml_path = run_dir / "run_inputs.yml"
    if not yml_path.exists():
        print(f"ERROR: {yml_path} not found. Run loongforge-adapt init first.", file=sys.stderr)
        raise SystemExit(2)
    import yaml
    raw = yaml.safe_load(yml_path.read_text())
    return RunInputs.model_validate(raw)


def _extract_repos_info(inputs: RunInputs) -> dict | None:
    """Build repos_info dict from ReposBlock, or None if loop engineering is off."""
    if not inputs.loop_engineering_enabled:
        return None

    repos = inputs.repos
    # Extract owner/repo from URL: https://github.com/owner/repo → owner/repo
    def _owner_repo(url: str) -> str:
        m = re.match(r"https?://github\.com/([^/]+/[^/]+?)(?:\.git)?$", url.rstrip("/"))
        return m.group(1) if m else ""

    return {
        "loongforge_repo": _owner_repo(str(repos.loongforge.url)),
        "loongforge_base_ref": repos.loongforge.base_ref,
        "megatron_repo": _owner_repo(str(repos.megatron.url)),
        "megatron_ref": repos.megatron.base_ref,
        "run_id": "",  # filled below from run_dir name
    }


def _run_id_from_dir(run_dir: Path) -> str:
    """Derive run_id from the run directory name."""
    return run_dir.name


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the adapt phase loop (FSM) for a single phase.",
    )
    parser.add_argument("--run-dir", required=True, type=Path, help="Path to the run directory")
    parser.add_argument("--phase", required=True, type=int, choices=range(0, 6),
                        help="Phase number (0-5)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Use FakeGhClient; no live gh writes")
    parser.add_argument("--continue-fix", action="store_true",
                        help="Resume from fix_pr state after agent has written fix code. "
                             "When this flag is set, pause_before_fix is False so the FSM "
                             "runs the full FIX_PR→REVIEW→MERGE_FIX→RERUN cycle.")

    args = parser.parse_args(argv)
    run_dir = args.run_dir.resolve()

    if not run_dir.is_dir():
        print(f"ERROR: run directory does not exist: {run_dir}", file=sys.stderr)
        return 2

    # Load run_inputs.yml
    inputs = _load_run_inputs(run_dir)

    # Build repos_info
    repos_info = _extract_repos_info(inputs)
    if repos_info is not None:
        repos_info["run_id"] = _run_id_from_dir(run_dir)

    # Build budget
    budget = inputs.loop if inputs.loop is not None else LoopBudget()

    # GhClient
    gh = FakeGhClient() if args.dry_run else RealGhClient()

    # pause_before_fix: True on first run (so agent can inject fix code),
    # False on --continue-fix (agent already wrote fix code, let FSM run).
    pause_before_fix = not args.continue_fix

    # Run the FSM
    try:
        result = run_phase_loop(
            run_dir=run_dir,
            phase=args.phase,
            gh=gh,
            budget=budget,
            dry_run=args.dry_run,
            repos_info=repos_info,
            pause_before_fix=pause_before_fix,
        )
    except Exception as exc:
        print(f"ERROR: loop controller failed: {exc}", file=sys.stderr)
        return 1

    # Map exit reason to exit code
    exit_code_map = {
        ExitReason.VALIDATOR_PASSED: 0,
        ExitReason.VALIDATOR_PASSED_AFTER_FIX: 0,
        ExitReason.FIX_NEEDED: 10,
    }
    exit_code = exit_code_map.get(result, 1)  # exhausted/human_needed/etc → 1

    # Print summary to stdout for the calling agent
    print(f"exit_reason={result.value}")
    print(f"phase={args.phase}")
    print(f"run_dir={run_dir}")

    # Read loop_state.yml for diagnostics on non-pass exits
    loop_state_path = run_dir / "phases" / f"phase{args.phase}" / "loop_state.yml"
    if loop_state_path.exists() and exit_code != 0:
        import yaml
        ls = yaml.safe_load(loop_state_path.read_text())
        print(f"current_state={ls.get('current_state', 'unknown')}")
        print(f"attempt={ls.get('attempt', 'unknown')}")
        if ls.get("last_validator_summary"):
            vs = ls["last_validator_summary"]
            print(f"validator_name={vs.get('name', 'unknown')}")
            print(f"validator_status={vs.get('status', 'unknown')}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
