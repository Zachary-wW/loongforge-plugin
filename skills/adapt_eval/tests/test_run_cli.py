import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_SCRIPTS = Path(__file__).parent.parent / "scripts"
_RUN_SCRIPT = _SCRIPTS / "run.py"


def _invoke_cli(argv: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_RUN_SCRIPT), *argv],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_help_lists_subcommands():
    result = _invoke_cli(["--help"], cwd=Path.cwd())
    assert result.returncode == 0
    for sub in ("init", "record-loss", "set-backup-info", "set-adapt-run",
                "set-omni-review", "compute-verdict", "restore"):
        assert sub in result.stdout


def test_cli_init_creates_eval_run_dir(tmp_path):
    eval_root = tmp_path / "eval"
    result = _invoke_cli(
        ["init", "qwen3", "--hf-path", "/data/qwen3", "--steps", "10",
         "--plugin-commit", "a4e0df0f", "--eval-root", str(eval_root)],
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    runs_dir = eval_root / "runs"
    assert runs_dir.exists()
    [run_dir] = list(runs_dir.iterdir())
    inputs = yaml.safe_load((run_dir / "eval_run_inputs.yml").read_text())
    assert inputs["family"] == "qwen3"
    assert inputs["steps"] == 10
    # CLI prints the absolute eval_run_dir for the orchestrator to consume
    assert str(run_dir) in result.stdout


def test_cli_init_requires_family(tmp_path):
    result = _invoke_cli(["init"], cwd=tmp_path)
    assert result.returncode != 0


def test_cli_record_loss_extracts_lm_loss(tmp_path):
    # Setup: init eval run + create a fake training log
    eval_root = tmp_path / "eval"
    init = _invoke_cli(
        ["init", "qwen3", "--hf-path", "/d", "--steps", "3",
         "--plugin-commit", "c1", "--eval-root", str(eval_root)],
        cwd=tmp_path,
    )
    run_dir = Path(init.stdout.strip())

    log = run_dir / "baseline_train.log"
    log.write_text(
        " iteration       1/    3 | lm loss: 1.000E+01 |\n"
        " iteration       2/    3 | lm loss: 9.500E+00 |\n"
        " iteration       3/    3 | lm loss: 9.000E+00 |\n"
    )

    result = _invoke_cli(
        ["record-loss", str(run_dir), "--label", "baseline", "--log", str(log)],
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    losses = json.loads((run_dir / "baseline_loss.json").read_text())
    assert losses["label"] == "baseline"
    assert losses["losses"] == [pytest.approx(10.0), pytest.approx(9.5), pytest.approx(9.0)]
    assert losses["log_path"].endswith("baseline_train.log")


def test_cli_record_loss_short_log_returns_nonzero(tmp_path):
    eval_root = tmp_path / "eval"
    init = _invoke_cli(
        ["init", "qwen3", "--hf-path", "/d", "--steps", "10",
         "--plugin-commit", "c1", "--eval-root", str(eval_root)],
        cwd=tmp_path,
    )
    run_dir = Path(init.stdout.strip())
    log = run_dir / "baseline_train.log"
    log.write_text(" iteration       1/   10 | lm loss: 1.0E+00 |\n")  # only 1 step

    result = _invoke_cli(
        ["record-loss", str(run_dir), "--label", "baseline", "--log", str(log)],
        cwd=tmp_path,
    )
    assert result.returncode != 0
    assert "fewer than" in (result.stderr + result.stdout).lower()


def test_cli_set_backup_info(tmp_path):
    eval_root = tmp_path / "eval"
    init = _invoke_cli(
        ["init", "qwen3", "--hf-path", "/d", "--steps", "10",
         "--plugin-commit", "c1", "--eval-root", str(eval_root)],
        cwd=tmp_path,
    )
    run_dir = Path(init.stdout.strip())

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "family": "qwen3",
        "git_commit_before": "abc1111",
        "delete_commit": "def2222",
        "backup_root": str(tmp_path / "backup"),
    }))

    result = _invoke_cli(
        ["set-backup-info", str(run_dir), "--manifest", str(manifest)],
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    inputs = yaml.safe_load((run_dir / "eval_run_inputs.yml").read_text())
    assert inputs["backup"]["delete_commit"] == "def2222"
    assert inputs["backup"]["git_commit_before"] == "abc1111"
    assert inputs["backup"]["manifest_path"] == str(manifest.resolve())


def test_cli_set_adapt_run_records_autonomy(tmp_path):
    eval_root = tmp_path / "eval"
    init = _invoke_cli(
        ["init", "qwen3", "--hf-path", "/d", "--steps", "10",
         "--plugin-commit", "c1", "--eval-root", str(eval_root)],
        cwd=tmp_path,
    )
    run_dir = Path(init.stdout.strip())

    adapt_run = tmp_path / "adapt_run"
    phases = adapt_run / "phases"
    phases.mkdir(parents=True)
    for n in range(6):
        (phases / f"phase{n}_output.yml").write_text(yaml.dump({"status": "passed"}))

    result = _invoke_cli(
        ["set-adapt-run", str(run_dir), "--adapt-run-dir", str(adapt_run)],
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    inputs = yaml.safe_load((run_dir / "eval_run_inputs.yml").read_text())
    assert inputs["adapt_run_dir"] == str(adapt_run.resolve())
    assert inputs["autonomy"]["score"] == 1.0
    assert inputs["autonomy"]["phase0_5_ok"] is True


def test_cli_set_omni_review(tmp_path):
    eval_root = tmp_path / "eval"
    init = _invoke_cli(
        ["init", "qwen3", "--hf-path", "/d", "--steps", "3",
         "--plugin-commit", "c1", "--eval-root", str(eval_root)],
        cwd=tmp_path,
    )
    run_dir = Path(init.stdout.strip())

    report = tmp_path / "omni_review_report.json"
    report.write_text(json.dumps({
        "overall_score": 88,
        "grade": "Good",
        "quality_analysis": {"score": 34},
    }))

    result = _invoke_cli(
        ["set-omni-review", str(run_dir), "--report", str(report)],
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    inputs = yaml.safe_load((run_dir / "eval_run_inputs.yml").read_text())
    assert inputs["omni_review"]["overall_score"] == 88
    assert inputs["omni_review"]["report_path"] == str(report.resolve())


def _seed_full_eval_run(tmp_path, eval_root):
    """Build an eval_run_dir with all upstream artefacts so compute-verdict can run."""
    init = _invoke_cli(
        ["init", "qwen3", "--hf-path", "/d", "--steps", "3",
         "--plugin-commit", "newcommit", "--eval-root", str(eval_root)],
        cwd=tmp_path,
    )
    run_dir = Path(init.stdout.strip())

    # baseline + new loss
    for label, vals in (("baseline", [10.0, 9.5, 9.0]), ("new", [10.001, 9.503, 9.001])):
        log = run_dir / f"{label}_train.log"
        log.write_text("\n".join(
            f" iteration       {i+1}/  3 | lm loss: {v} |"
            for i, v in enumerate(vals)
        ))
        rc = _invoke_cli(
            ["record-loss", str(run_dir), "--label", label, "--log", str(log)],
            cwd=tmp_path,
        )
        assert rc.returncode == 0, rc.stderr

    # backup info
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "family": "qwen3", "git_commit_before": "ab", "delete_commit": "cd",
    }))
    rc = _invoke_cli(
        ["set-backup-info", str(run_dir), "--manifest", str(manifest)],
        cwd=tmp_path,
    )
    assert rc.returncode == 0, rc.stderr

    # adapt run with all 6 phases passed
    adapt_run = run_dir / "adapt_run"
    phases = adapt_run / "phases"
    phases.mkdir(parents=True)
    for n in range(6):
        (phases / f"phase{n}_output.yml").write_text(yaml.dump({"status": "passed"}))
    rc = _invoke_cli(
        ["set-adapt-run", str(run_dir), "--adapt-run-dir", str(adapt_run)],
        cwd=tmp_path,
    )
    assert rc.returncode == 0, rc.stderr

    # omni review
    omni = run_dir / "omni_review_report.json"
    omni.write_text(json.dumps({"overall_score": 90}))
    rc = _invoke_cli(
        ["set-omni-review", str(run_dir), "--report", str(omni)],
        cwd=tmp_path,
    )
    assert rc.returncode == 0, rc.stderr
    return run_dir


def test_cli_compute_verdict_baseline_first_run(tmp_path):
    eval_root = tmp_path / "eval"
    eval_root.mkdir()
    (eval_root / "SCOREBOARD.md").write_text("# header\n")
    (eval_root / "SCOREBOARD.json").write_text("[]")

    run_dir = _seed_full_eval_run(tmp_path, eval_root)

    result = _invoke_cli(
        ["compute-verdict", str(run_dir)],
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads((run_dir / "eval_report.json").read_text())
    assert report["verdict"] == "BASELINE"
    assert report["metrics"]["loss_max_diff"] < 0.01
    sb = json.loads((eval_root / "SCOREBOARD.json").read_text())
    assert len(sb) == 1 and sb[0]["family"] == "qwen3"
    assert "BASELINE" in (eval_root / "SCOREBOARD.md").read_text()
    assert (run_dir / "eval_report.md").exists()


def test_cli_compute_verdict_pass_when_better_than_last(tmp_path):
    eval_root = tmp_path / "eval"
    eval_root.mkdir()
    (eval_root / "SCOREBOARD.md").write_text("# header\n")
    (eval_root / "SCOREBOARD.json").write_text(json.dumps([{
        "family": "qwen3", "timestamp": "2026-06-05T10:00:00",
        "plugin_commit": "oldcommit", "verdict": "BASELINE",
        "metrics": {"autonomy": 0.75, "loss_max_diff": 0.001,
                    "omni_score": 85, "phase0_5_ok": True},
    }]))

    run_dir = _seed_full_eval_run(tmp_path, eval_root)
    result = _invoke_cli(["compute-verdict", str(run_dir)], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    report = json.loads((run_dir / "eval_report.json").read_text())
    assert report["verdict"] == "PASS"
    assert report["metrics"]["autonomy"] == 1.0
    assert report["delta_vs_last"]["last_plugin_commit"] == "oldcommit"


def test_cli_compute_verdict_invalid_skips_scoreboard(tmp_path):
    eval_root = tmp_path / "eval"
    eval_root.mkdir()
    (eval_root / "SCOREBOARD.md").write_text("# header\n")
    (eval_root / "SCOREBOARD.json").write_text("[]")

    run_dir = _seed_full_eval_run(tmp_path, eval_root)
    # Corrupt phase0 to FAIL the validity gate
    phase0 = run_dir / "adapt_run" / "phases" / "phase0_output.yml"
    phase0.write_text(yaml.dump({"status": "human_needed"}))
    _invoke_cli(
        ["set-adapt-run", str(run_dir), "--adapt-run-dir", str(run_dir / "adapt_run")],
        cwd=tmp_path,
    )

    result = _invoke_cli(["compute-verdict", str(run_dir)], cwd=tmp_path)
    assert result.returncode == 0, result.stderr  # Verdict computed, just INVALID
    report = json.loads((run_dir / "eval_report.json").read_text())
    assert report["verdict"] == "INVALID"
    sb = json.loads((eval_root / "SCOREBOARD.json").read_text())
    assert sb == []


def test_cli_compute_verdict_invalid_when_loss_files_missing(tmp_path):
    """When baseline/new loss files are absent, verdict must be INVALID and
    eval_report must surface a concrete loss_diff reason."""
    eval_root = tmp_path / "eval"
    eval_root.mkdir()
    (eval_root / "SCOREBOARD.md").write_text("# header\n")
    (eval_root / "SCOREBOARD.json").write_text("[]")

    init = _invoke_cli(
        ["init", "qwen3", "--hf-path", "/d", "--steps", "3",
         "--plugin-commit", "newcommit", "--eval-root", str(eval_root)],
        cwd=tmp_path,
    )
    assert init.returncode == 0, init.stderr
    run_dir = Path(init.stdout.strip())

    # Skip record-loss entirely. Provide adapt_run + omni so phase0_5_ok=True.
    adapt_run = run_dir / "adapt_run"
    phases = adapt_run / "phases"
    phases.mkdir(parents=True)
    for n in range(6):
        (phases / f"phase{n}_output.yml").write_text(yaml.dump({"status": "passed"}))
    rc = _invoke_cli(
        ["set-adapt-run", str(run_dir), "--adapt-run-dir", str(adapt_run)],
        cwd=tmp_path,
    )
    assert rc.returncode == 0, rc.stderr

    omni = run_dir / "omni_review_report.json"
    omni.write_text(json.dumps({"overall_score": 90}))
    rc = _invoke_cli(
        ["set-omni-review", str(run_dir), "--report", str(omni)],
        cwd=tmp_path,
    )
    assert rc.returncode == 0, rc.stderr

    rc = _invoke_cli(["compute-verdict", str(run_dir)], cwd=tmp_path)
    assert rc.returncode == 0, rc.stderr

    report = json.loads((run_dir / "eval_report.json").read_text())
    assert report["verdict"] == "INVALID"
    assert "loss_unavailable" in report["verdict_reasons"]
    # Concrete cause from Issue B should be present.
    assert any("loss_diff" in r for r in report["verdict_reasons"])

    # Markdown report shows the reasons line (Issue A).
    md = (run_dir / "eval_report.md").read_text()
    assert "reasons:" in md


def _git(repo: Path, *args, check=True):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=check)


def test_cli_restore_reverts_delete_commit(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    target = repo / "model.txt"
    target.write_text("hello\n")
    _git(repo, "add", "model.txt")
    _git(repo, "commit", "-qm", "init")
    git_commit_before = _git(repo, "rev-parse", "HEAD").stdout.strip()
    target.unlink()
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "delete model")
    delete_commit = _git(repo, "rev-parse", "HEAD").stdout.strip()
    assert not target.exists()

    eval_root = repo / "claude-loongforge-plugin" / "eval"
    eval_root.mkdir(parents=True)
    init = _invoke_cli(
        ["init", "qwen3", "--hf-path", "/d", "--steps", "3",
         "--plugin-commit", "c1", "--eval-root", str(eval_root)],
        cwd=repo,
    )
    run_dir = Path(init.stdout.strip())
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "git_commit_before": git_commit_before,
        "delete_commit": delete_commit,
    }))
    _invoke_cli(
        ["set-backup-info", str(run_dir), "--manifest", str(manifest)],
        cwd=repo,
    )

    result = _invoke_cli(["restore", str(run_dir)], cwd=repo)
    assert result.returncode == 0, result.stderr
    assert target.exists()
    assert target.read_text() == "hello\n"


def test_cli_restore_keep_deleted_skips_revert(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    target = repo / "model.txt"
    target.write_text("hello\n")
    _git(repo, "add", "model.txt")
    _git(repo, "commit", "-qm", "init")
    target.unlink()
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "delete")
    delete_commit = _git(repo, "rev-parse", "HEAD").stdout.strip()

    eval_root = repo / "claude-loongforge-plugin" / "eval"
    eval_root.mkdir(parents=True)
    init = _invoke_cli(
        ["init", "qwen3", "--hf-path", "/d", "--steps", "3",
         "--plugin-commit", "c1", "--eval-root", str(eval_root)],
        cwd=repo,
    )
    run_dir = Path(init.stdout.strip())
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({"git_commit_before": "x", "delete_commit": delete_commit}))
    _invoke_cli(["set-backup-info", str(run_dir), "--manifest", str(manifest)], cwd=repo)

    result = _invoke_cli(["restore", str(run_dir), "--keep-deleted"], cwd=repo)
    assert result.returncode == 0, result.stderr
    assert not target.exists()  # still deleted


def test_cli_compute_verdict_regressed_when_loss_exceeds_gate(tmp_path):
    """REGRESSED via the loss hard gate produces a scoreboard entry tagged REGRESSED."""
    eval_root = tmp_path / "eval"
    eval_root.mkdir()
    (eval_root / "SCOREBOARD.md").write_text("# header\n")
    (eval_root / "SCOREBOARD.json").write_text(json.dumps([{
        "family": "qwen3", "timestamp": "2026-06-05T10:00:00",
        "plugin_commit": "oldcommit", "verdict": "BASELINE",
        "metrics": {"autonomy": 0.5, "loss_max_diff": 0.001,
                    "omni_score": 80, "phase0_5_ok": True},
    }]))

    # Build a full eval_run, but override new_loss to diverge by 0.05 (> 1e-2 gate).
    init = _invoke_cli(
        ["init", "qwen3", "--hf-path", "/d", "--steps", "3",
         "--plugin-commit", "newcommit", "--eval-root", str(eval_root)],
        cwd=tmp_path,
    )
    assert init.returncode == 0, init.stderr
    run_dir = Path(init.stdout.strip())

    for label, vals in (("baseline", [10.0, 9.5, 9.0]), ("new", [10.05, 9.55, 9.05])):
        log = run_dir / f"{label}_train.log"
        log.write_text("\n".join(
            f" iteration       {i+1}/  3 | lm loss: {v} |"
            for i, v in enumerate(vals)
        ))
        rc = _invoke_cli(
            ["record-loss", str(run_dir), "--label", label, "--log", str(log)],
            cwd=tmp_path,
        )
        assert rc.returncode == 0, rc.stderr

    # Phase 0/5 must pass so we test the loss gate, not the validity gate.
    adapt_run = run_dir / "adapt_run"
    phases = adapt_run / "phases"
    phases.mkdir(parents=True)
    for n in range(6):
        (phases / f"phase{n}_output.yml").write_text(yaml.dump({"status": "passed"}))
    rc = _invoke_cli(
        ["set-adapt-run", str(run_dir), "--adapt-run-dir", str(adapt_run)],
        cwd=tmp_path,
    )
    assert rc.returncode == 0, rc.stderr

    omni = run_dir / "omni_review_report.json"
    omni.write_text(json.dumps({"overall_score": 88}))
    rc = _invoke_cli(
        ["set-omni-review", str(run_dir), "--report", str(omni)],
        cwd=tmp_path,
    )
    assert rc.returncode == 0, rc.stderr

    rc = _invoke_cli(["compute-verdict", str(run_dir)], cwd=tmp_path)
    assert rc.returncode == 0, rc.stderr

    report = json.loads((run_dir / "eval_report.json").read_text())
    assert report["verdict"] == "REGRESSED"
    assert "loss_max_diff" in report["verdict_reasons"]

    # REGRESSED entries DO get appended to the scoreboard (per design §5.4).
    sb = json.loads((eval_root / "SCOREBOARD.json").read_text())
    assert len(sb) == 2
    assert sb[-1]["verdict"] == "REGRESSED"
