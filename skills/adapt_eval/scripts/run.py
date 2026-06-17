#!/usr/bin/env python3
"""LoongForge Adapt Eval — CLI dispatcher.

This script is a deterministic transform layer. The orchestration (which
sub-agents to dispatch when) lives in skills/adapt_eval/SKILL.md and is
executed by the main Claude agent.

Sub-commands:
  init             — create eval_run_dir and seed eval_run_inputs.yml
  record-loss      — append loss values (baseline or new) to eval_run_dir
  set-backup-info  — record backup-model manifest path + delete_commit
  set-adapt-run    — record /loongforge:adapt run_dir + autonomy snapshot
  set-omni-review  — record omni-reviewer report path + score
  compute-verdict  — write eval_report.{json,md} + append SCOREBOARD.{md,json}
  restore          — git revert delete_commit and verify clean tree
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HELPERS_SPEC = importlib.util.spec_from_file_location(
    "eval_helpers", _HERE / "eval_helpers.py"
)
eval_helpers = importlib.util.module_from_spec(_HELPERS_SPEC)
_HELPERS_SPEC.loader.exec_module(eval_helpers)

_PARSER_SPEC = importlib.util.spec_from_file_location(
    "log_parser", _HERE / "log_parser.py"
)
log_parser = importlib.util.module_from_spec(_PARSER_SPEC)
_PARSER_SPEC.loader.exec_module(log_parser)


# -- sub-command: init --------------------------------------------------------

def cmd_init(args: argparse.Namespace) -> int:
    eval_root = Path(args.eval_root).resolve()
    run_dir = eval_helpers.init_eval_run_dir(
        family=args.family,
        hf_path=args.hf_path,
        steps=args.steps,
        plugin_commit=args.plugin_commit,
        eval_root=eval_root,
    )
    print(str(run_dir))
    return 0


# -- sub-command: record-loss -------------------------------------------------

def cmd_record_loss(args: argparse.Namespace) -> int:
    import json
    run_dir = Path(args.eval_run_dir).resolve()
    inputs = eval_helpers.load_eval_run_inputs(run_dir)
    steps = inputs["steps"]
    log_path = Path(args.log).resolve()

    losses = log_parser.extract_losses(log_path.read_text(), max_steps=steps)
    if len(losses) < steps:
        print(
            f"record-loss: extracted {len(losses)} loss values, fewer than required {steps}",
            file=sys.stderr,
        )
        return 1

    out = run_dir / f"{args.label}_loss.json"
    out.write_text(json.dumps({
        "label": args.label,
        "steps": steps,
        "losses": losses,
        "log_path": str(log_path),
    }, indent=2))
    return 0


# -- sub-command: set-backup-info ---------------------------------------------

def cmd_set_backup_info(args: argparse.Namespace) -> int:
    import json
    run_dir = Path(args.eval_run_dir).resolve()
    manifest_path = Path(args.manifest).resolve()
    manifest = json.loads(manifest_path.read_text())
    eval_helpers.update_eval_run_inputs(
        run_dir,
        backup={
            "manifest_path": str(manifest_path),
            "git_commit_before": manifest.get("git_commit_before"),
            "delete_commit": manifest.get("delete_commit"),
            "backup_root": manifest.get("backup_root"),
        },
    )
    return 0


# -- sub-command: set-adapt-run -----------------------------------------------

def cmd_set_adapt_run(args: argparse.Namespace) -> int:
    run_dir = Path(args.eval_run_dir).resolve()
    adapt_run_dir = Path(args.adapt_run_dir).resolve()
    autonomy = eval_helpers.compute_autonomy(adapt_run_dir)
    eval_helpers.update_eval_run_inputs(
        run_dir,
        adapt_run_dir=str(adapt_run_dir),
        autonomy=autonomy,
    )
    return 0


# -- sub-command: set-omni-review ---------------------------------------------

def cmd_set_omni_review(args: argparse.Namespace) -> int:
    import json
    run_dir = Path(args.eval_run_dir).resolve()
    report_path = Path(args.report).resolve()
    report = json.loads(report_path.read_text())
    eval_helpers.update_eval_run_inputs(
        run_dir,
        omni_review={
            "report_path": str(report_path),
            "overall_score": report.get("overall_score"),
            "grade": report.get("grade"),
        },
    )
    return 0


# -- sub-command: compute-verdict ---------------------------------------------

def cmd_compute_verdict(args: argparse.Namespace) -> int:
    import json
    run_dir = Path(args.eval_run_dir).resolve()
    inputs = eval_helpers.load_eval_run_inputs(run_dir)
    eval_root = run_dir.parent.parent  # eval/runs/<ts-family>/.. = eval/
    assert run_dir.parent.name == "runs", (
        f"compute-verdict expected eval_run_dir under <eval_root>/runs/, got {run_dir}"
    )

    # Load loss curves (may be missing → INVALID)
    baseline_path = run_dir / "baseline_loss.json"
    new_path = run_dir / "new_loss.json"
    loss_max_diff = None
    loss_per_step: list[float] = []
    loss_diff_error = None
    if baseline_path.exists() and new_path.exists():
        baseline = json.loads(baseline_path.read_text())["losses"]
        new = json.loads(new_path.read_text())["losses"]
        try:
            ld = eval_helpers.compute_loss_diff(baseline, new)
            loss_max_diff = ld["max_abs_diff"]
            loss_per_step = ld["per_step_diff"]
        except ValueError as e:
            loss_diff_error = str(e)
    elif not baseline_path.exists():
        loss_diff_error = "baseline_loss.json not found"
    elif not new_path.exists():
        loss_diff_error = "new_loss.json not found"

    autonomy = inputs.get("autonomy") or {"score": 0.0, "phase_status": {}, "phase0_5_ok": False}
    omni_score = (inputs.get("omni_review") or {}).get("overall_score")

    metrics = {
        "autonomy": autonomy["score"],
        "autonomy_phase_status": autonomy["phase_status"],
        "loss_max_diff": loss_max_diff,
        "loss_per_step_diff": loss_per_step,
        "omni_score": omni_score,
        "phase0_5_ok": autonomy["phase0_5_ok"],
    }

    sb_json = eval_root / "SCOREBOARD.json"
    sb_md = eval_root / "SCOREBOARD.md"
    last_entry = eval_helpers.find_last_entry(sb_json, family=inputs["family"])

    verdict = eval_helpers.compute_verdict(metrics, last_entry)

    if loss_diff_error:
        verdict["reasons"] = (verdict.get("reasons") or []) + [f"loss_diff: {loss_diff_error}"]

    delta = None
    if last_entry is not None:
        last_metrics = last_entry.get("metrics", {})
        delta = {
            "last_entry_ts": last_entry.get("timestamp"),
            "last_plugin_commit": last_entry.get("plugin_commit"),
            "autonomy_was": last_metrics.get("autonomy"),
            "omni_score_was": last_metrics.get("omni_score"),
            "autonomy": _signed(metrics["autonomy"], last_metrics.get("autonomy")),
            "omni_score": _signed(metrics["omni_score"], last_metrics.get("omni_score")),
        }

    try:
        run_dir_relative = "eval/" + str(run_dir.relative_to(eval_root)).replace("\\", "/")
    except ValueError:
        run_dir_relative = str(run_dir)

    report = {
        "schema_version": 1,
        "family": inputs["family"],
        "plugin_commit": inputs["plugin_commit"],
        "timestamp": inputs["timestamp"],
        "verdict": verdict["status"],
        "verdict_reasons": verdict["reasons"],
        "metrics": metrics,
        "delta_vs_last": delta,
        "artifacts": {
            "adapt_run_dir": inputs.get("adapt_run_dir"),
            "baseline_loss": str(baseline_path) if baseline_path.exists() else None,
            "new_loss": str(new_path) if new_path.exists() else None,
            "omni_review": (inputs.get("omni_review") or {}).get("report_path"),
        },
        "run_dir_relative": run_dir_relative,
    }
    (run_dir / "eval_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    (run_dir / "eval_report.md").write_text(eval_helpers.render_scoreboard_entry(report))

    eval_helpers.append_scoreboard(sb_md, sb_json, report)
    print(f"verdict: {verdict['status']}")
    return 0


def _signed(new, old):
    if not isinstance(new, (int, float)) or not isinstance(old, (int, float)):
        return None
    diff = new - old
    sign = "+" if diff >= 0 else ""
    return f"{sign}{diff:.2f}" if isinstance(new, float) else f"{sign}{int(diff)}"


# -- sub-command: restore -----------------------------------------------------

def cmd_restore(args: argparse.Namespace) -> int:
    import subprocess
    run_dir = Path(args.eval_run_dir).resolve()
    inputs = eval_helpers.load_eval_run_inputs(run_dir)

    if args.keep_deleted:
        eval_helpers.update_eval_run_inputs(run_dir, restore={"action": "skipped"})
        return 0

    backup = inputs.get("backup") or {}
    delete_commit = backup.get("delete_commit")
    if not delete_commit:
        print("restore: no delete_commit recorded; run set-backup-info first",
              file=sys.stderr)
        return 1

    repo = _find_git_root(run_dir)
    if repo is None:
        print(f"restore: no git repo found above {run_dir}", file=sys.stderr)
        return 1

    revert = subprocess.run(
        ["git", "revert", "--no-edit", delete_commit],
        cwd=repo, capture_output=True, text=True,
    )
    if revert.returncode != 0:
        print(f"restore: git revert failed:\n{revert.stderr}", file=sys.stderr)
        return revert.returncode

    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo, capture_output=True, text=True, check=True,
    )
    warnings = []
    if status.stdout.strip():
        warnings.append(f"git status non-empty after revert:\n{status.stdout}")

    eval_helpers.update_eval_run_inputs(run_dir, restore={
        "action": "reverted",
        "delete_commit": delete_commit,
        "warnings": warnings,
    })
    return 0


def _find_git_root(start: Path) -> Path | None:
    cur = start.resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


# -- top-level parser ---------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="loongforge-adapt-eval")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="create eval run directory")
    p_init.add_argument("family")
    p_init.add_argument("--hf-path", required=True)
    p_init.add_argument("--steps", type=int, default=10)
    p_init.add_argument("--plugin-commit", required=True)
    p_init.add_argument("--eval-root", required=True,
                        help="absolute path to claude-loongforge-plugin/eval")
    p_init.set_defaults(func=cmd_init)

    # Stubs registered now so --help lists them; bodies added in later tasks.
    p_loss = sub.add_parser("record-loss", help="extract loss values from training log")
    p_loss.add_argument("eval_run_dir")
    p_loss.add_argument("--label", required=True, choices=["baseline", "new"])
    p_loss.add_argument("--log", required=True, help="path to teed training stdout log")
    p_loss.set_defaults(func=cmd_record_loss)

    p_bk = sub.add_parser("set-backup-info", help="record backup-model manifest")
    p_bk.add_argument("eval_run_dir")
    p_bk.add_argument("--manifest", required=True)
    p_bk.set_defaults(func=cmd_set_backup_info)

    p_ar = sub.add_parser("set-adapt-run", help="record adapt run_dir + autonomy")
    p_ar.add_argument("eval_run_dir")
    p_ar.add_argument("--adapt-run-dir", required=True)
    p_ar.set_defaults(func=cmd_set_adapt_run)

    p_or = sub.add_parser("set-omni-review", help="record omni-reviewer report")
    p_or.add_argument("eval_run_dir")
    p_or.add_argument("--report", required=True)
    p_or.set_defaults(func=cmd_set_omni_review)

    p_cv = sub.add_parser("compute-verdict", help="compute verdict + write report + scoreboard")
    p_cv.add_argument("eval_run_dir")
    p_cv.set_defaults(func=cmd_compute_verdict)

    p_rs = sub.add_parser("restore", help="git revert delete_commit")
    p_rs.add_argument("eval_run_dir")
    p_rs.add_argument("--keep-deleted", action="store_true",
                      help="skip the revert (leave repo in deleted state)")
    p_rs.set_defaults(func=cmd_restore)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
