"""Housekeeping verification: check bot artifact labels + stranded issues (ROADMAP criterion 4).

Exits 0 when all artifacts have correct labels and no stranded issues exist.
Exits 1 on any failure. Supports --dry-run to skip live gh calls (ROADMAP criterion 5).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

REQUIRED_LABELS = ["loongforge-adapt"]


def check_artifact_labels(actual_labels: list[str], required_labels: list[str]) -> list[str]:
    """Return list of missing label names. Empty list means all present."""
    return [lbl for lbl in required_labels if lbl not in actual_labels]


def run_housekeeping_check(
    run_dir: Path, loongforge_repo: str, dry_run: bool = False,
) -> tuple[bool, list[str]]:
    """Verify bot artifacts have correct labels and no stranded issues.

    If dry_run is True, return (True, []) immediately -- no live gh calls.
    In dry-run mode loop_state.yml contains fake PR/issue numbers from
    FakeGhClient that do not correspond to real GitHub artifacts.
    """
    if dry_run:
        return (True, [])
    errors: list[str] = []
    run_id = run_dir.name
    for phase in range(6):
        state_path = run_dir / "phases" / f"phase{phase}" / "loop_state.yml"
        if not state_path.exists():
            continue
        data = yaml.safe_load(state_path.read_text()) or {}
        phase_labels = REQUIRED_LABELS + [f"run-{run_id}", f"phase-{phase}"]
        for pr_field in ("pr_number", "fix_pr_number"):
            num = data.get(pr_field)
            if num is None:
                continue
            r = subprocess.run(
                ["gh", "pr", "view", str(num), "-R", loongforge_repo, "--json", "labels,state"],
                capture_output=True, text=True, check=False,
            )
            if r.returncode != 0:
                errors.append(f"Phase {phase} PR #{num}: gh pr view failed")
                continue
            info = json.loads(r.stdout)
            actual = [l["name"] for l in info.get("labels", [])]
            missing = check_artifact_labels(actual, phase_labels)
            if missing:
                errors.append(f"Phase {phase} PR #{num}: missing labels {missing}")
        issue_num = data.get("issue_number")
        if issue_num is not None:
            r = subprocess.run(
                ["gh", "issue", "view", str(issue_num), "-R", loongforge_repo, "--json", "labels,state"],
                capture_output=True, text=True, check=False,
            )
            if r.returncode != 0:
                errors.append(f"Phase {phase} issue #{issue_num}: gh issue view failed")
                continue
            info = json.loads(r.stdout)
            actual = [l["name"] for l in info.get("labels", [])]
            missing = check_artifact_labels(actual, phase_labels)
            if missing:
                errors.append(f"Phase {phase} issue #{issue_num}: missing labels {missing}")
            if info.get("state", "").upper() != "CLOSED":
                errors.append(f"Phase {phase} issue #{issue_num}: not closed (stranded)")
    return (True, []) if not errors else (False, errors)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Housekeeping verification (ROADMAP criterion 4)")
    parser.add_argument("--run-dir", required=True, help="Path to run directory")
    parser.add_argument("--repo", required=True, help="LoongForge repo (owner/repo)")
    parser.add_argument("--dry-run", action="store_true", help="Skip live gh calls")
    args = parser.parse_args()
    if args.dry_run:
        print("SKIP: dry-run mode -- no real GitHub artifacts to verify")
        sys.exit(0)
    ok, errs = run_housekeeping_check(Path(args.run_dir), args.repo, dry_run=False)
    if ok:
        print("PASS: all artifacts verified")
        sys.exit(0)
    else:
        print(f"FAIL: {errs}")
        sys.exit(1)
