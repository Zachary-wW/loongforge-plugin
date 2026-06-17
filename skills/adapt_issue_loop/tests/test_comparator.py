import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "comparator.py"
SPEC = importlib.util.spec_from_file_location("issue_loop_comparator", SCRIPT)
comparator = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = comparator
SPEC.loader.exec_module(comparator)


PHASE0_CONTRACT = {
    "phase0": {
        "goal": "Extract enough DS V4 facts for Phase 1 code generation.",
        "comparator_rules": [
            {"id": "phase0_mla", "markers": ["qk_rope_head_dim", "o_lora_rank"]},
            {"id": "phase0_mtp", "markers": ["mtp_num_layers"]},
        ],
    }
}


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_compare_phase_passes_when_generated_contains_baseline_markers(tmp_path):
    baseline = tmp_path / "baseline"
    generated = tmp_path / "run" / "phases" / "phase0"
    _write(baseline / "deepseek_v4_config.py", "qk_rope_head_dim = 64\no_lora_rank = 1024\nmtp_num_layers = 1\n")
    _write(generated / "model_spec.yaml", "qk_rope_head_dim: 64\no_lora_rank: 1024\nmtp_num_layers: 1\n")

    report = comparator.compare_phase_to_baseline(
        phase=0,
        generated_roots=[generated],
        baseline_roots=[baseline],
        goal_contract=PHASE0_CONTRACT,
    )

    assert report["status"] == "passed"
    assert report["summary"]["generated_missing"] == 0
    assert report["issue_specs"] == []


def test_compare_phase_fails_and_creates_issue_spec_when_generated_misses_marker(tmp_path):
    baseline = tmp_path / "baseline"
    generated = tmp_path / "run" / "phases" / "phase0"
    _write(baseline / "deepseek_v4_config.py", "qk_rope_head_dim = 64\no_lora_rank = 1024\nmtp_num_layers = 1\n")
    _write(generated / "model_spec.yaml", "qk_rope_head_dim: 64\no_lora_rank: 1024\n")

    report = comparator.compare_phase_to_baseline(
        phase=0,
        generated_roots=[generated],
        baseline_roots=[baseline],
        goal_contract=PHASE0_CONTRACT,
    )

    assert report["status"] == "failed"
    missing = [check for check in report["checks"] if check["status"] == "generated_missing"]
    assert missing[0]["marker"] == "mtp_num_layers"
    assert report["issue_specs"][0]["dedup_key"] == "phase0:missing_mtp_num_layers:baseline_static_compare"
    assert "mtp_num_layers" in report["issue_specs"][0]["acceptance"][0]


def test_compare_phase_reports_baseline_unavailable_when_baseline_lacks_marker(tmp_path):
    baseline = tmp_path / "baseline"
    generated = tmp_path / "run" / "phases" / "phase0"
    _write(baseline / "deepseek_v4_config.py", "qk_rope_head_dim = 64\n")
    _write(generated / "model_spec.yaml", "qk_rope_head_dim: 64\n")

    report = comparator.compare_phase_to_baseline(
        phase=0,
        generated_roots=[generated],
        baseline_roots=[baseline],
        goal_contract=PHASE0_CONTRACT,
    )

    assert report["status"] == "baseline_unavailable"
    assert report["summary"]["baseline_missing"] == 2
    assert report["issue_specs"] == []
