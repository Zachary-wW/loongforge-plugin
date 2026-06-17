import importlib.util
import json
from pathlib import Path

import pytest
import yaml

_SCRIPTS = Path(__file__).parent.parent / "scripts"
_SPEC = importlib.util.spec_from_file_location("eval_helpers", _SCRIPTS / "eval_helpers.py")
eval_helpers = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(eval_helpers)


# -- run_inputs round trip ----------------------------------------------------

def test_init_eval_run_dir_writes_inputs(tmp_path):
    run_dir = eval_helpers.init_eval_run_dir(
        family="qwen3",
        hf_path="/data/qwen3",
        steps=10,
        plugin_commit="a4e0df0f",
        eval_root=tmp_path,
    )
    inputs = yaml.safe_load((run_dir / "eval_run_inputs.yml").read_text())
    assert inputs["family"] == "qwen3"
    assert inputs["hf_path"] == "/data/qwen3"
    assert inputs["steps"] == 10
    assert inputs["plugin_commit"] == "a4e0df0f"
    assert run_dir.parent == tmp_path / "runs"


def test_load_eval_run_inputs(tmp_path):
    run_dir = eval_helpers.init_eval_run_dir("qwen3", "/d", 10, "abc", tmp_path)
    loaded = eval_helpers.load_eval_run_inputs(run_dir)
    assert loaded["family"] == "qwen3"


# -- autonomy -----------------------------------------------------------------

def _write_phase_output(adapt_run, phase_num, status):
    phases = adapt_run / "phases"
    phases.mkdir(parents=True, exist_ok=True)
    (phases / f"phase{phase_num}_output.yml").write_text(yaml.dump({"status": status}))


def test_compute_autonomy_all_passed(tmp_path):
    for n in range(6):
        _write_phase_output(tmp_path, n, "passed")
    result = eval_helpers.compute_autonomy(tmp_path)
    assert result["score"] == 1.0
    assert result["phase_status"] == {f"phase{n}": "passed" for n in range(6)}
    assert result["phase0_5_ok"] is True


def test_compute_autonomy_partial(tmp_path):
    _write_phase_output(tmp_path, 0, "passed")
    _write_phase_output(tmp_path, 1, "passed")
    _write_phase_output(tmp_path, 2, "human_needed")
    _write_phase_output(tmp_path, 3, "passed")
    _write_phase_output(tmp_path, 4, "passed")
    _write_phase_output(tmp_path, 5, "passed")
    result = eval_helpers.compute_autonomy(tmp_path)
    assert result["score"] == 0.75  # 3/4 phase 1-4 passed
    assert result["phase0_5_ok"] is True


def test_compute_autonomy_phase05_failure(tmp_path):
    _write_phase_output(tmp_path, 0, "human_needed")
    for n in range(1, 6):
        _write_phase_output(tmp_path, n, "passed")
    result = eval_helpers.compute_autonomy(tmp_path)
    assert result["phase0_5_ok"] is False


def test_compute_autonomy_missing_phase(tmp_path):
    # Only phase0 written; everything else absent
    _write_phase_output(tmp_path, 0, "passed")
    result = eval_helpers.compute_autonomy(tmp_path)
    assert result["score"] == 0.0
    assert result["phase_status"]["phase1"] == "missing"
    assert result["phase0_5_ok"] is False  # phase5 missing


# -- loss diff ----------------------------------------------------------------

def test_compute_loss_diff_basic():
    result = eval_helpers.compute_loss_diff(
        baseline=[10.0, 9.5, 9.0, 8.5],
        new=[10.001, 9.499, 9.003, 8.498],
    )
    assert result["max_abs_diff"] == pytest.approx(0.003)
    assert len(result["per_step_diff"]) == 4


def test_compute_loss_diff_length_mismatch():
    with pytest.raises(ValueError, match="length"):
        eval_helpers.compute_loss_diff(baseline=[1.0, 2.0], new=[1.0])


def test_compute_loss_diff_empty():
    with pytest.raises(ValueError, match="empty"):
        eval_helpers.compute_loss_diff(baseline=[], new=[])


# -- scoreboard last-entry rule ----------------------------------------------

def test_find_last_entry_returns_latest_pass(tmp_path):
    sb = tmp_path / "SCOREBOARD.json"
    sb.write_text(json.dumps([
        {"family": "qwen3", "timestamp": "2026-06-01T10:00:00", "verdict": "BASELINE",
         "metrics": {"autonomy": 0.5, "omni_score": 80}},
        {"family": "qwen3", "timestamp": "2026-06-05T10:00:00", "verdict": "PASS",
         "metrics": {"autonomy": 0.75, "omni_score": 85}},
        {"family": "deepseek_v3", "timestamp": "2026-06-06T10:00:00", "verdict": "PASS",
         "metrics": {"autonomy": 1.0, "omni_score": 90}},
    ]))
    last = eval_helpers.find_last_entry(sb, family="qwen3")
    assert last["timestamp"] == "2026-06-05T10:00:00"


def test_find_last_entry_skips_regressed_and_invalid(tmp_path):
    sb = tmp_path / "SCOREBOARD.json"
    sb.write_text(json.dumps([
        {"family": "qwen3", "timestamp": "2026-06-01T10:00:00", "verdict": "BASELINE",
         "metrics": {"autonomy": 0.5, "omni_score": 80}},
        {"family": "qwen3", "timestamp": "2026-06-05T10:00:00", "verdict": "REGRESSED",
         "metrics": {"autonomy": 0.25, "omni_score": 70}},
        {"family": "qwen3", "timestamp": "2026-06-06T10:00:00", "verdict": "INVALID",
         "metrics": {}},
    ]))
    last = eval_helpers.find_last_entry(sb, family="qwen3")
    assert last["timestamp"] == "2026-06-01T10:00:00"


def test_find_last_entry_none_when_empty(tmp_path):
    sb = tmp_path / "SCOREBOARD.json"
    sb.write_text("[]")
    assert eval_helpers.find_last_entry(sb, family="qwen3") is None


# -- verdict ------------------------------------------------------------------

def test_verdict_baseline_when_no_last_entry():
    metrics = {"autonomy": 0.75, "loss_max_diff": 0.003, "omni_score": 85, "phase0_5_ok": True}
    v = eval_helpers.compute_verdict(metrics, last_entry=None)
    assert v["status"] == "BASELINE"


def test_verdict_pass():
    metrics = {"autonomy": 1.0, "loss_max_diff": 0.003, "omni_score": 88, "phase0_5_ok": True}
    last = {"metrics": {"autonomy": 0.75, "omni_score": 85}}
    v = eval_helpers.compute_verdict(metrics, last_entry=last)
    assert v["status"] == "PASS"


def test_verdict_invalid_when_phase05_failed():
    metrics = {"autonomy": 1.0, "loss_max_diff": 0.003, "omni_score": 88, "phase0_5_ok": False}
    v = eval_helpers.compute_verdict(metrics, last_entry=None)
    assert v["status"] == "INVALID"


def test_verdict_invalid_when_loss_unavailable():
    metrics = {"autonomy": 1.0, "loss_max_diff": None, "omni_score": 88, "phase0_5_ok": True}
    v = eval_helpers.compute_verdict(metrics, last_entry=None)
    assert v["status"] == "INVALID"


def test_verdict_regressed_on_loss_hard_gate():
    metrics = {"autonomy": 1.0, "loss_max_diff": 0.05, "omni_score": 88, "phase0_5_ok": True}
    last = {"metrics": {"autonomy": 0.75, "omni_score": 85}}
    v = eval_helpers.compute_verdict(metrics, last_entry=last)
    assert v["status"] == "REGRESSED"
    assert "loss_max_diff" in v["reasons"]


def test_verdict_regressed_on_autonomy_drop():
    metrics = {"autonomy": 0.5, "loss_max_diff": 0.001, "omni_score": 88, "phase0_5_ok": True}
    last = {"metrics": {"autonomy": 0.75, "omni_score": 85}}
    v = eval_helpers.compute_verdict(metrics, last_entry=last)
    assert v["status"] == "REGRESSED"
    assert "autonomy" in v["reasons"]


def test_verdict_regressed_on_omni_drop():
    metrics = {"autonomy": 1.0, "loss_max_diff": 0.001, "omni_score": 70, "phase0_5_ok": True}
    last = {"metrics": {"autonomy": 0.75, "omni_score": 85}}
    v = eval_helpers.compute_verdict(metrics, last_entry=last)
    assert v["status"] == "REGRESSED"
    assert "omni_score" in v["reasons"]


def test_verdict_invalid_when_omni_unavailable():
    metrics = {"autonomy": 1.0, "loss_max_diff": 0.001, "omni_score": None, "phase0_5_ok": True}
    v = eval_helpers.compute_verdict(metrics, last_entry=None)
    assert v["status"] == "INVALID"
    assert "omni_unavailable" in v["reasons"]


# -- scoreboard append --------------------------------------------------------

def test_append_scoreboard_writes_both_formats(tmp_path):
    sb_md = tmp_path / "SCOREBOARD.md"
    sb_md.write_text("# header\n")
    sb_json = tmp_path / "SCOREBOARD.json"
    sb_json.write_text("[]")

    entry = {
        "family": "qwen3",
        "timestamp": "2026-06-10T08:42:00",
        "plugin_commit": "a4e0df0f",
        "verdict": "PASS",
        "metrics": {"autonomy": 1.0, "loss_max_diff": 0.003, "omni_score": 88, "phase0_5_ok": True},
        "delta_vs_last": {"last_plugin_commit": "f36a765b", "autonomy": "+0.25", "omni_score": "+3"},
        "run_dir_relative": "eval/runs/20260610-0842-qwen3/",
    }
    eval_helpers.append_scoreboard(sb_md, sb_json, entry)

    md_text = sb_md.read_text()
    assert "[2026-06-10 08:42] PASS | qwen3 | a4e0df0f" in md_text
    assert "autonomy:" in md_text

    json_arr = json.loads(sb_json.read_text())
    assert json_arr[-1]["family"] == "qwen3"
    assert json_arr[-1]["verdict"] == "PASS"


def test_append_scoreboard_skips_invalid(tmp_path):
    sb_md = tmp_path / "SCOREBOARD.md"
    sb_md.write_text("# header\n")
    sb_json = tmp_path / "SCOREBOARD.json"
    sb_json.write_text("[]")

    entry = {"family": "x", "verdict": "INVALID", "timestamp": "t", "plugin_commit": "c", "metrics": {}}
    eval_helpers.append_scoreboard(sb_md, sb_json, entry)
    assert json.loads(sb_json.read_text()) == []
    assert "INVALID" not in sb_md.read_text()


def test_update_eval_run_inputs_is_atomic(tmp_path):
    """A mid-write crash must not leave eval_run_inputs.yml truncated."""
    run_dir = eval_helpers.init_eval_run_dir("qwen3", "/d", 10, "abc", tmp_path)
    # The YAML must already exist after init.
    yml = run_dir / "eval_run_inputs.yml"
    assert yml.exists() and yml.stat().st_size > 0

    # Updating writes a new file via os.replace, so no `.tmp` files leak.
    eval_helpers.update_eval_run_inputs(run_dir, foo="bar")
    leftovers = [p for p in run_dir.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []
    loaded = eval_helpers.load_eval_run_inputs(run_dir)
    assert loaded["foo"] == "bar"


def test_append_scoreboard_uses_atomic_writes(tmp_path):
    """append_scoreboard must not leave .tmp leftovers next to SCOREBOARD files."""
    sb_md = tmp_path / "SCOREBOARD.md"
    sb_md.write_text("# header\n")
    sb_json = tmp_path / "SCOREBOARD.json"
    sb_json.write_text("[]")
    entry = {
        "family": "x", "verdict": "PASS", "timestamp": "2026-06-10T00:00:00",
        "plugin_commit": "abc", "metrics": {"autonomy": 1.0, "loss_max_diff": 0.001, "omni_score": 90},
    }
    eval_helpers.append_scoreboard(sb_md, sb_json, entry)
    leftovers = [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []
