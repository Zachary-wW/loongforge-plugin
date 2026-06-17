import json
import sys
from pathlib import Path
import subprocess

import yaml


RUN_PY = Path(__file__).resolve().parents[1] / "scripts" / "run.py"


def _run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUN_PY), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _init_state(tmp_path: Path) -> Path:
    result = _run_cli("init", "--plugin-root", str(tmp_path), "--repo", "owner/repo")
    assert result.returncode == 0, result.stderr
    return Path(result.stdout.strip())


def _write_baseline_and_generated(tmp_path: Path) -> tuple[Path, Path]:
    baseline = tmp_path / "baseline"
    generated = tmp_path / "generated"
    _write(
        baseline / "deepseek_v4_config.py",
        "qk_rope_head_dim = 64\no_lora_rank = 1024\nmtp_num_layers = 1\n",
    )
    _write(
        generated / "model_spec.yaml",
        "qk_rope_head_dim: 64\no_lora_rank: 1024\n",
    )
    return baseline, generated


def _write_comparator_report(tmp_path: Path) -> tuple[Path, Path]:
    state_dir = _init_state(tmp_path)
    baseline, generated = _write_baseline_and_generated(tmp_path)
    report = tmp_path / "report.yml"

    result = _run_cli(
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
        str(report),
    )

    assert result.returncode == 0, result.stderr
    return state_dir, report


def test_init_writes_state_and_prints_state_dir(tmp_path):
    result = _run_cli("init", "--plugin-root", str(tmp_path), "--repo", "owner/repo")

    assert result.returncode == 0, result.stderr
    state_dir = tmp_path / ".loongforge" / "issue-loop"
    assert result.stdout.strip() == str(state_dir)
    state_yml = yaml.safe_load((state_dir / "state.yml").read_text())
    assert state_yml["repo"] == "owner/repo"


def test_documented_init_command_defaults_plugin_root_to_cwd(tmp_path):
    result = _run_cli(
        "init",
        "--target",
        "ds-v4",
        "--repo",
        "owner/repo",
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    state_dir = tmp_path / ".loongforge" / "issue-loop"
    assert result.stdout.strip() == str(state_dir)
    assert yaml.safe_load((state_dir / "state.yml").read_text())["repo"] == "owner/repo"


def test_compare_phase_run_dir_derives_defaults_from_state(tmp_path):
    init_result = _run_cli("init", "--repo", "owner/repo", cwd=tmp_path)
    assert init_result.returncode == 0, init_result.stderr
    state_dir = Path(init_result.stdout.strip())

    baseline = tmp_path / "baseline"
    run_dir = tmp_path / "run"
    generated = run_dir / "phases" / "phase0"
    _write(
        baseline / "deepseek_v4_config.py",
        "qk_rope_head_dim = 64\no_lora_rank = 1024\nmtp_num_layers = 1\n",
    )
    _write(
        generated / "model_spec.yaml",
        "qk_rope_head_dim: 64\no_lora_rank: 1024\n",
    )

    state_yml = yaml.safe_load((state_dir / "state.yml").read_text())
    state_yml["baseline"] = {"local": {"path": str(baseline), "commit": "test"}}
    (state_dir / "state.yml").write_text(yaml.dump(state_yml))

    result = _run_cli("compare-phase", "--phase", "0", "--run-dir", str(run_dir), cwd=tmp_path)

    expected_report = state_dir / "comparator_reports" / "phase0-report.yml"
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(expected_report)
    assert expected_report.exists()
    assert yaml.safe_load(expected_report.read_text())["status"] == "failed"


def test_compare_phase_writes_failed_report_with_issue_specs(tmp_path):
    state_dir = _init_state(tmp_path)
    baseline, generated = _write_baseline_and_generated(tmp_path)
    report = tmp_path / "report.yml"

    result = _run_cli(
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
        str(report),
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(report)
    loaded = yaml.safe_load(report.read_text())
    assert loaded["status"] == "failed"
    assert loaded["issue_specs"]
    assert loaded["issue_specs"][0]["dedup_key"] == "phase0:missing_mtp_num_layers:baseline_static_compare"
    assert any(check["marker"] == "mtp_num_layers" for check in loaded["checks"])


def test_issue_from_report_writes_issue_spec_files_and_prints_json(tmp_path):
    _, report = _write_comparator_report(tmp_path)
    out_dir = tmp_path / "issues"

    result = _run_cli("issue-from-report", "--report", str(report), "--out-dir", str(out_dir))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    paths = payload["issue_specs"]
    assert len(paths) == 1
    issue_path = Path(paths[0])
    assert issue_path.exists()
    loaded = yaml.safe_load(issue_path.read_text())
    assert loaded["dedup_key"] == "phase0:missing_mtp_num_layers:baseline_static_compare"


def test_verify_merge_gate_prints_json_and_exits_zero_when_passed(tmp_path):
    gate = tmp_path / "gate.yml"
    gate.write_text(
        yaml.dump(
            {
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
        )
    )

    result = _run_cli("verify-merge-gate", "--inputs", str(gate))

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "passed"


def test_verify_merge_gate_exits_two_when_blocked(tmp_path):
    gate = tmp_path / "gate.yml"
    gate.write_text(yaml.dump({"review_verdict": "approved"}))

    result = _run_cli("verify-merge-gate", "--inputs", str(gate))

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert "issue_acceptance_passed" in payload["blocking_reasons"]


def test_sync_issue_dry_run_prints_json(tmp_path):
    _, report = _write_comparator_report(tmp_path)
    issue_dir = tmp_path / "issues"
    issue_result = _run_cli("issue-from-report", "--report", str(report), "--out-dir", str(issue_dir))
    issue_spec_path = json.loads(issue_result.stdout)["issue_specs"][0]

    result = _run_cli(
        "sync-issue",
        "--issue-spec",
        issue_spec_path,
        "--repo",
        "owner/repo",
        "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["mode"] == "dry-run"
    assert payload["action"] == "create"
    assert payload["repo"] == "owner/repo"
    assert payload["dedup_key"] == "phase0:missing_mtp_num_layers:baseline_static_compare"


def test_run_dry_initializes_state_writes_report_and_returns_dry_sync_payloads(tmp_path):
    baseline, generated = _write_baseline_and_generated(tmp_path)
    plugin_root = tmp_path / "plugin"

    result = _run_cli(
        "run-dry",
        "--plugin-root",
        str(plugin_root),
        "--repo",
        "owner/repo",
        "--phase",
        "0",
        "--generated-root",
        str(generated),
        "--baseline-root",
        str(baseline),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    report = Path(payload["comparator_report"])
    assert report == plugin_root / ".loongforge" / "issue-loop" / "comparator_reports" / "phase0-dry-run.yml"
    assert report.exists()
    assert len(payload["issue_specs"]) == 1
    assert payload["sync_payloads"][0]["mode"] == "dry-run"


def test_cli_run_dry_creates_report_issue_spec_and_dry_sync_payload(tmp_path):
    baseline = tmp_path / "baseline"
    generated = tmp_path / "generated"
    _write(
        baseline / "deepseek_v4_config.py",
        "mtp_num_layers = 1\nqk_rope_head_dim = 64\no_lora_rank = 1024\n",
    )
    _write(generated / "model_spec.yaml", "qk_rope_head_dim: 64\no_lora_rank: 1024\n")

    result = _run_cli(
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
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert Path(payload["report"]).exists()
    assert len(payload["issue_specs"]) == 1
    assert payload["dry_sync"][0]["mode"] == "dry-run"
    assert payload["dry_sync"][0]["action"] == "create"
