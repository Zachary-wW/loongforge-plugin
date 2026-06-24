"""Summary generation: comprehension_summary.md and phaseN_summary.md (DOC-04).

Reads loop_state.yml (including merge_commit_sha) + attempts.jsonl from disk,
produces markdown summaries. CLI entry point for SKILL.md End-of-Run Housekeeping.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml


def generate_phase_summary(run_dir: Path, phase: int) -> str:
    """Generate per-phase summary markdown from loop_state.yml + attempts.jsonl."""
    phase_dir = run_dir / "phases" / f"phase{phase}"
    state_path = phase_dir / "loop_state.yml"
    if not state_path.exists():
        return f"Phase {phase}: no loop data (legacy mode or not yet executed)\n"
    data = yaml.safe_load(state_path.read_text()) or {}
    attempt = data.get("attempt", 1)
    exit_reason = data.get("exit_reason", "unknown")
    merge_sha = data.get("merge_commit_sha") or "N/A"
    validator_name = (data.get("last_validator_summary") or {}).get("name", "unknown")
    # FSM path from attempts.jsonl
    attempts_path = phase_dir / "attempts.jsonl"
    kinds: list[str] = []
    if attempts_path.exists():
        for line in attempts_path.read_text().strip().split("\n"):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                kinds.append(row.get("kind", ""))
            except (json.JSONDecodeError, ValueError):
                pass
    path_str = " -> ".join(kinds) if kinds else "(no FSM path recorded)"
    parts = [
        f"# Phase {phase} Summary\n",
        f"- **Exit reason:** {exit_reason}",
        f"- **Attempts:** {attempt} attempts",
        f"- **Merged commit:** {merge_sha}",
        f"- **Validator:** {validator_name}",
        f"- **FSM path:** {path_str}\n",
    ]
    # Decision log
    decision_path = phase_dir / "decision_log.md"
    if decision_path.exists():
        parts.append("## Decisions\n")
        parts.append(decision_path.read_text())
        parts.append("\n")
    return "\n".join(parts)


def generate_comprehension_summary(run_dir: Path) -> str:
    """Generate 1-page comprehension summary across all phases (DOC-04, D-02)."""
    rows = []
    for phase in range(6):
        state_path = run_dir / "phases" / f"phase{phase}" / "loop_state.yml"
        if not state_path.exists():
            continue
        data = yaml.safe_load(state_path.read_text()) or {}
        attempt = data.get("attempt", 1)
        exit_reason = data.get("exit_reason", "unknown")
        merge_sha = data.get("merge_commit_sha") or "N/A"
        validator = (data.get("last_validator_summary") or {}).get("name", "unknown")
        rows.append((phase, attempt, exit_reason, merge_sha, validator))
    if not rows:
        return f"# Comprehension Summary -- Run {run_dir.name}\n\nNo phases completed.\n"
    total_attempts = sum(r[1] for r in rows)
    all_passed = all(r[2] in ("validator_passed", "validator_passed_after_fix") for r in rows)
    outcome = "All phases passed" if all_passed else "Incomplete"
    header = f"# Comprehension Summary -- Run {run_dir.name}\n\n"
    table = "| Phase | Attempts | Exit Reason | Merged Commit | Validator |\n"
    table += "|-------|----------|-------------|---------------|----------|\n"
    for phase, attempt, exit_reason, merge_sha, validator in rows:
        table += f"| Phase {phase} | {attempt} | {exit_reason} | {merge_sha} | {validator} |\n"
    return f"{header}{table}\n- **Total attempts:** {total_attempts}\n- **Outcome:** {outcome}\n"


def write_summaries(run_dir: Path) -> None:
    """Write comprehension_summary.md and per-phase summaries to disk."""
    comp = generate_comprehension_summary(run_dir)
    (run_dir / "comprehension_summary.md").write_text(comp)
    for phase in range(6):
        state_path = run_dir / "phases" / f"phase{phase}" / "loop_state.yml"
        if state_path.exists():
            phase_dir = run_dir / "phases" / f"phase{phase}"
            summary = generate_phase_summary(run_dir, phase)
            (phase_dir / f"phase{phase}_summary.md").write_text(summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate run summaries (DOC-04)")
    parser.add_argument("--run-dir", required=True, help="Path to run directory")
    args = parser.parse_args()
    try:
        write_summaries(Path(args.run_dir))
        print(f"Summaries written to {args.run_dir}")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
