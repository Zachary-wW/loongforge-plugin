import importlib.util
import sys
from pathlib import Path

import pytest


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


@pytest.mark.parametrize(
    "goal_contract",
    [
        {},
        {"phase0": {}},
        {"phase0": {"comparator_rules": []}},
    ],
)
def test_missing_or_empty_comparator_rules_raise_value_error(tmp_path, goal_contract):
    baseline = tmp_path / "baseline"
    generated = tmp_path / "generated"
    _write(baseline / "baseline.py", "marker = True\n")
    _write(generated / "generated.py", "marker = True\n")

    with pytest.raises(ValueError, match="comparator_rules"):
        comparator.compare_phase_to_baseline(
            phase=0,
            generated_roots=[generated],
            baseline_roots=[baseline],
            goal_contract=goal_contract,
        )


def test_comparator_rule_with_empty_markers_raises_value_error(tmp_path):
    baseline = tmp_path / "baseline"
    generated = tmp_path / "generated"
    _write(baseline / "baseline.py", "marker = True\n")
    _write(generated / "generated.py", "marker = True\n")
    goal_contract = {"phase0": {"comparator_rules": [{"id": "empty", "markers": []}]}}

    with pytest.raises(ValueError, match="empty.*markers"):
        comparator.compare_phase_to_baseline(
            phase=0,
            generated_roots=[generated],
            baseline_roots=[baseline],
            goal_contract=goal_contract,
        )


@pytest.mark.parametrize("markers", [["valid", ""], ["valid", 3]])
def test_comparator_rule_with_invalid_marker_values_raises_value_error(tmp_path, markers):
    baseline = tmp_path / "baseline"
    generated = tmp_path / "generated"
    _write(baseline / "baseline.py", "marker = True\n")
    _write(generated / "generated.py", "marker = True\n")
    goal_contract = {"phase0": {"comparator_rules": [{"id": "invalid", "markers": markers}]}}

    with pytest.raises(ValueError, match="invalid.*markers"):
        comparator.compare_phase_to_baseline(
            phase=0,
            generated_roots=[generated],
            baseline_roots=[baseline],
            goal_contract=goal_contract,
        )


def test_mixed_baseline_and_generated_missing_status_fails_with_issue_specs(tmp_path):
    baseline = tmp_path / "baseline"
    generated = tmp_path / "run" / "phases" / "phase0"
    contract = {
        "phase0": {
            "goal": "Validate mixed missing outcomes.",
            "comparator_rules": [
                {"id": "mixed", "markers": ["baseline_only_marker", "missing_everywhere_marker"]},
            ],
        }
    }
    _write(baseline / "deepseek_v4_config.py", "baseline_only_marker = True\n")
    _write(generated / "model_spec.yaml", "other_marker: true\n")

    report = comparator.compare_phase_to_baseline(
        phase=0,
        generated_roots=[generated],
        baseline_roots=[baseline],
        goal_contract=contract,
    )

    assert report["status"] == "failed"
    assert report["summary"]["generated_missing"] == 1
    assert report["summary"]["baseline_missing"] == 1
    assert [issue["dedup_key"] for issue in report["issue_specs"]] == [
        "phase0:missing_baseline_only_marker:baseline_static_compare"
    ]


def test_large_files_are_skipped_and_smaller_marker_file_still_passes(tmp_path, monkeypatch):
    baseline = tmp_path / "baseline"
    generated = tmp_path / "run" / "phases" / "phase0"
    marker = "scan_marker"
    contract = {
        "phase0": {
            "goal": "Validate bounded scanning.",
            "comparator_rules": [{"id": "bounded", "markers": [marker]}],
        }
    }
    monkeypatch.setattr(comparator, "MAX_FILE_BYTES", 32)
    monkeypatch.setattr(comparator, "MAX_TOTAL_BYTES", 1024)

    _write(baseline / "huge.py", "x" * 33)
    _write(baseline / "small.py", f"{marker} = True\n")
    _write(generated / "huge.py", "y" * 33)
    _write(generated / "small.py", f"{marker}: true\n")

    report = comparator.compare_phase_to_baseline(
        phase=0,
        generated_roots=[generated],
        baseline_roots=[baseline],
        goal_contract=contract,
    )

    assert report["status"] == "passed"
    assert report["summary"] == {"baseline_missing": 0, "generated_missing": 0, "passed": 1}
    assert report["scan_limits"]["baseline"]["skipped_by_reason"]["max_file_bytes_exceeded"] == 1
    assert report["scan_limits"]["generated"]["skipped_by_reason"]["max_file_bytes_exceeded"] == 1
