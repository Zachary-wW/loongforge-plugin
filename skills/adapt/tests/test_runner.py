# tests/test_runner.py -- Unit tests for the runner/ module
# Coverage: run_inputs / phase output / resume / legacy compat / CLI

import importlib.util
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

_RUNNER_MODULE_PATH = Path(__file__).parent.parent / "scripts" / "run.py"
_RUNNER_SPEC = importlib.util.spec_from_file_location("loongforge_adapt_runner", _RUNNER_MODULE_PATH)
assert _RUNNER_SPEC and _RUNNER_SPEC.loader
_runner = importlib.util.module_from_spec(_RUNNER_SPEC)
_RUNNER_SPEC.loader.exec_module(_runner)

_build_run_inputs = _runner._build_run_inputs
save_run_inputs = _runner.save_run_inputs
load_run_inputs = _runner.load_run_inputs
save_legacy_state = _runner.save_legacy_state
load_legacy_state = _runner.load_legacy_state
phase_output_path = _runner.phase_output_path
legacy_phase_output_path = _runner.legacy_phase_output_path
get_phase_status = _runner.get_phase_status
clear_phase_output = _runner.clear_phase_output
init_run_dir = _runner.init_run_dir
resume_run_dir = _runner.resume_run_dir

ADAPT_ROOT = Path(__file__).parent.parent
REPO_ROOT = ADAPT_ROOT.parents[2]
RUNNER_SCRIPT = str(ADAPT_ROOT / "scripts" / "run.py")


# -- run_inputs helpers -------------------------------------------------------

def test_build_run_inputs_minimal():
    inputs = _build_run_inputs(hf_ckpt_path="/tmp/model", model_name="test")
    assert inputs["source"]["hf_ckpt_path"] == "/tmp/model"
    assert inputs["options"]["model_name"] == "test"
    assert inputs["paths"]["omni_path"] == ""
    assert inputs["options"]["gpu_execution_mode"] == "local_gpu"


def test_build_run_inputs_full():
    inputs = _build_run_inputs(
        hf_ckpt_path="/tmp/model",
        model_name="qwen3",
        hf_modeling_path="/tmp/modeling.py",
        hf_transformers_path="/tmp/transformers",
        omni_path="/opt/loongforge",
        megatron_path="/opt/megatron",
        gpu_execution_mode="k8s",
        enable_slice_ckpt="true",
        k8s_yaml_path="/tmp/job.yaml",
        k8s_launch_cmd="kubectl apply",
        wip_code_paths='[{"path":"/tmp/wip","type":"megatron"}]',
    )
    assert inputs["source"]["hf_ckpt_path"] == "/tmp/model"
    assert inputs["paths"]["hf_modeling_path"] == "/tmp/modeling.py"
    assert inputs["paths"]["hf_transformers_path"] == "/tmp/transformers"
    assert inputs["options"]["enable_slice_ckpt"] == "true"
    assert inputs["options"]["wip_code_paths"] == '[{"path":"/tmp/wip","type":"megatron"}]'


def test_save_and_load_run_inputs(tmp_path):
    inputs = _build_run_inputs(hf_ckpt_path="/tmp/model", model_name="test")
    save_run_inputs(str(tmp_path), inputs)
    loaded = load_run_inputs(str(tmp_path))
    assert loaded["source"]["hf_ckpt_path"] == "/tmp/model"
    assert loaded["options"]["model_name"] == "test"


def test_load_run_inputs_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_run_inputs(str(tmp_path / "no_such_dir"))


# -- legacy state compat ------------------------------------------------------

def test_legacy_state_roundtrip(tmp_path):
    inputs = _build_run_inputs(hf_ckpt_path="/tmp/model", model_name="mimo")
    save_legacy_state(str(tmp_path), inputs, current_state="PHASE1_RUNNING")
    legacy = load_legacy_state(str(tmp_path))
    assert legacy["hf_path"] == "/tmp/model"
    assert legacy["model_name"] == "mimo"
    assert legacy["current_state"] == "PHASE1_RUNNING"
    assert legacy["version"] == "2.0"


def test_legacy_state_phases_preserved(tmp_path):
    inputs = _build_run_inputs(hf_ckpt_path="/tmp/m", model_name="x")
    phases = {"phase0": {"status": "passed"}, "phase1": {"status": "passed"}}
    save_legacy_state(str(tmp_path), inputs, phases=phases)
    legacy = load_legacy_state(str(tmp_path))
    assert legacy["phases"]["phase0"]["status"] == "passed"


# -- phase output helpers -----------------------------------------------------

def test_get_phase_status_missing(tmp_path):
    assert get_phase_status(str(tmp_path), 0) is None


def test_get_phase_status_present(tmp_path):
    phase_dir = tmp_path / "phases"
    phase_dir.mkdir(parents=True)
    output = {"phase": 0, "status": "passed", "summary": "ok"}
    Path(phase_output_path(str(tmp_path), 0)).write_text(yaml.dump(output))
    assert get_phase_status(str(tmp_path), 0) == "passed"


def test_get_phase_status_legacy_fallback(tmp_path):
    phase_dir = tmp_path / "phases" / "phase0"
    phase_dir.mkdir(parents=True)
    output = {"phase": 0, "status": "passed", "summary": "legacy ok"}
    Path(legacy_phase_output_path(str(tmp_path), 0)).write_text(yaml.dump(output))
    assert get_phase_status(str(tmp_path), 0) == "passed"


def test_clear_phase_output(tmp_path):
    phase_dir = tmp_path / "phases" / "phase1"
    phase_dir.mkdir(parents=True)
    Path(phase_output_path(str(tmp_path), 1)).write_text("status: passed\n")
    Path(legacy_phase_output_path(str(tmp_path), 1)).write_text("status: passed\n")
    clear_phase_output(str(tmp_path), 1)
    assert not Path(phase_output_path(str(tmp_path), 1)).exists()
    assert not Path(legacy_phase_output_path(str(tmp_path), 1)).exists()


def test_clear_phase_output_idempotent(tmp_path):
    # Clearing non-existent phase should not error
    clear_phase_output(str(tmp_path), 3)


def test_clear_phase_output_also_clears_attempts(tmp_path):
    phase_dir = tmp_path / "phases" / "phase1"
    phase_dir.mkdir(parents=True)
    Path(phase_output_path(str(tmp_path), 1)).write_text("status: failed\n")
    (phase_dir / "attempts.jsonl").write_text('{"attempt":1,"action":"x","result":"failed"}\n')
    clear_phase_output(str(tmp_path), 1)
    assert not Path(phase_output_path(str(tmp_path), 1)).exists()
    assert not (phase_dir / "attempts.jsonl").exists()


# -- init_run_dir -------------------------------------------------------------

def test_init_run_dir_creates_structure(tmp_path):
    run_dir = str(tmp_path / "run_test")
    inputs = init_run_dir(hf_ckpt_path="/tmp/model", model_name="test", run_dir=run_dir)
    assert Path(run_dir).exists()
    assert (Path(run_dir) / "run_inputs.yml").exists()
    assert (Path(run_dir) / "run_state.json").exists()
    # Phase directories
    for i in range(7):
        assert (Path(run_dir) / "phases" / f"phase{i}").is_dir()
    # Logs subdirectories for Phase 1-5
    for i in range(1, 6):
        assert (Path(run_dir) / "phases" / f"phase{i}" / "logs").is_dir()
    # Phase 0 and 6 should not have logs dir
    assert not (Path(run_dir) / "phases" / "phase0" / "logs").exists()
    assert not (Path(run_dir) / "phases" / "phase6" / "logs").exists()


def test_init_run_dir_inputs_content(tmp_path):
    run_dir = str(tmp_path / "run_test2")
    inputs = init_run_dir(hf_ckpt_path="/tmp/model", model_name="test", run_dir=run_dir)
    assert inputs["source"]["hf_ckpt_path"] == "/tmp/model"
    assert inputs["options"]["model_name"] == "test"


def test_init_run_dir_with_options(tmp_path):
    run_dir = str(tmp_path / "run_test3")
    inputs = init_run_dir(
        hf_ckpt_path="/tmp/model",
        model_name="qwen3",
        run_dir=run_dir,
        omni_path="/opt/loongforge",
        megatron_path="/opt/megatron",
        enable_slice_ckpt="true",
    )
    assert inputs["paths"]["omni_path"] == "/opt/loongforge"
    assert inputs["paths"]["megatron_path"] == "/opt/megatron"
    assert inputs["options"]["enable_slice_ckpt"] == "true"


# -- resume_run_dir -----------------------------------------------------------

def test_resume_loads_inputs(tmp_path):
    run_dir = str(tmp_path / "resume1")
    init_run_dir(hf_ckpt_path="/tmp/model", model_name="test", run_dir=run_dir)
    inputs = resume_run_dir(run_dir)
    assert inputs["source"]["hf_ckpt_path"] == "/tmp/model"


def test_resume_from_phase_clears_outputs(tmp_path):
    run_dir = str(tmp_path / "resume2")
    init_run_dir(hf_ckpt_path="/tmp/model", model_name="test", run_dir=run_dir)

    # Simulate phase0 and phase1 passing
    for i in range(2):
        output = {"phase": i, "status": "passed", "summary": "ok"}
        Path(phase_output_path(run_dir, i)).write_text(yaml.dump(output))

    # Resume from phase 1 — should clear phase1 output
    inputs = resume_run_dir(run_dir, from_phase=1)
    assert get_phase_status(run_dir, 0) == "passed"
    assert get_phase_status(run_dir, 1) is None

    # Legacy state should reflect reset
    legacy = load_legacy_state(run_dir)
    assert legacy["current_state"] == "PHASE1_RUNNING"
    assert "phase1" not in legacy["phases"]


# -- CLI tests ----------------------------------------------------------------

def test_cli_first_run(tmp_path):
    import subprocess
    run_dir = str(tmp_path / "cli_test")
    result = subprocess.run(
        ["python", RUNNER_SCRIPT, "/tmp/model",
         "--run-dir", run_dir, "--omni-path", "/opt/loongforge"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    inputs = yaml.safe_load(Path(run_dir, "run_inputs.yml").read_text())
    assert inputs["source"]["hf_ckpt_path"] == "/tmp/model"
    assert inputs["paths"]["omni_path"] == "/opt/loongforge"


def test_cli_hf_transformers_path(tmp_path):
    import subprocess
    run_dir = str(tmp_path / "cli_transformers")
    result = subprocess.run(
        ["python", RUNNER_SCRIPT, "/tmp/model",
         "--run-dir", run_dir, "--hf-transformers-path", "/opt/transformers"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    inputs = yaml.safe_load(Path(run_dir, "run_inputs.yml").read_text())
    assert inputs["paths"]["hf_transformers_path"] == "/opt/transformers"


def test_cli_wip_code_paths(tmp_path):
    import subprocess
    run_dir = str(tmp_path / "cli_wip")
    result = subprocess.run(
        ["python", RUNNER_SCRIPT, "/tmp/model",
         "--run-dir", run_dir, "--wip-code-paths",
         "/path/to/megatron|megatron,/path/to/hf|hf_transformers"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    inputs = yaml.safe_load(Path(run_dir, "run_inputs.yml").read_text())
    parsed = json.loads(inputs["options"]["wip_code_paths"])
    assert len(parsed) == 2
    assert parsed[0]["path"] == "/path/to/megatron"
    assert parsed[0]["type"] == "megatron"


def test_cli_wip_code_paths_invalid(tmp_path):
    import subprocess
    run_dir = str(tmp_path / "cli_wip_bad")
    result = subprocess.run(
        ["python", RUNNER_SCRIPT, "/tmp/model",
         "--run-dir", run_dir, "--wip-code-paths", "invalid_no_separator"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0


def test_cli_resume(tmp_path):
    import subprocess
    run_dir = str(tmp_path / "cli_resume")
    init_run_dir(hf_ckpt_path="/tmp/model", model_name="test", run_dir=run_dir)

    result = subprocess.run(
        ["python", RUNNER_SCRIPT, "--resume", run_dir],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "[Resume]" in result.stdout


def test_cli_resume_from_phase(tmp_path):
    import subprocess
    run_dir = str(tmp_path / "cli_resume_phase")
    init_run_dir(hf_ckpt_path="/tmp/model", model_name="test", run_dir=run_dir)

    # Simulate phase0-6 passing
    for i in range(7):
        output = {"phase": i, "status": "passed", "summary": "ok"}
        Path(phase_output_path(run_dir, i)).write_text(yaml.dump(output))

    result = subprocess.run(
        ["python", RUNNER_SCRIPT, "--resume", run_dir, "--from-phase", "2"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    # Phase 0/1 should remain, phase 2+ cleared
    assert get_phase_status(run_dir, 0) == "passed"
    assert get_phase_status(run_dir, 1) == "passed"
    assert get_phase_status(run_dir, 2) is None


def test_cli_no_args_errors():
    import subprocess
    result = subprocess.run(
        ["python", RUNNER_SCRIPT],
        capture_output=True, text=True,
    )
    assert result.returncode != 0


# -- backward compat: legacy test coverage -----------------------------------

def test_legacy_state_written_on_init(tmp_path):
    """run_state.json must still be written for backward compatibility."""
    run_dir = str(tmp_path / "legacy_compat")
    init_run_dir(hf_ckpt_path="/tmp/model", model_name="test", run_dir=run_dir)
    legacy = json.loads(Path(run_dir, "run_state.json").read_text())
    assert legacy["hf_path"] == "/tmp/model"
    assert legacy["version"] == "2.0"


def test_legacy_wip_code_paths_preserved(tmp_path):
    """WIP code paths in legacy state must match run_inputs.yml."""
    run_dir = str(tmp_path / "legacy_wip")
    wip_json = json.dumps([{"path": "/tmp/wip", "type": "megatron"}])
    init_run_dir(
        hf_ckpt_path="/tmp/model",
        model_name="test",
        run_dir=run_dir,
        wip_code_paths=wip_json,
    )
    legacy = json.loads(Path(run_dir, "run_state.json").read_text())
    parsed = json.loads(legacy["wip_code_paths"])
    assert parsed[0]["path"] == "/tmp/wip"


# -- documentation consistency -------------------------------------------------


def _read_adapt_doc(relative_path):
    return (ADAPT_ROOT / relative_path).read_text()


def test_phase_docs_use_canonical_attempts_journal_path():
    """Attempt journals live under phases/phaseN/attempts.jsonl."""
    phase_docs = sorted((ADAPT_ROOT / "references" / "phases").glob("phase*/agent.md"))
    offenders = []
    for path in phase_docs:
        text = path.read_text()
        if "attempts/phase" in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []


def test_skill_documents_gpu_execution_mode_under_options():
    """run_inputs.yml stores GPU launch options under the options map."""
    skill = _read_adapt_doc("SKILL.md")
    assert "Passed field: `options.gpu_execution_mode`" in skill
    assert "Passed field: `gpu_execution_mode`" not in skill


def test_phase_final_status_docs_exclude_failed_checkpoint_status():
    """failed is an attempt/validator loop signal, not a final phase checkpoint."""
    skill = _read_adapt_doc("SKILL.md")
    assert "phase.status: `passed` or `human_needed`" in skill
    assert "attempt.status: `passed`, `failed`, or `human_needed`" in skill

    phase4 = _read_adapt_doc("references/phases/phase4/agent.md")
    assert "status: passed | human_needed" in phase4
    assert "status: passed | failed | human_needed" not in phase4


def test_skill_documents_claude_code_harness_reuse_and_loop_limits():
    """The skill should document when native Claude Code task/loop features are useful."""
    skill = _read_adapt_doc("SKILL.md")
    assert "Claude Code Harness Reuse" in skill
    assert "TaskCreate" in skill
    assert "/loop" in skill
    assert "Do not use /loop for phase-local repair loops" in skill
