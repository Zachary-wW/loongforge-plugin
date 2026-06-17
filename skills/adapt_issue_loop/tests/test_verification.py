import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verification.py"
SPEC = importlib.util.spec_from_file_location("issue_loop_verification", SCRIPT)
verification = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(verification)


def _passing_inputs():
    return {
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


def test_merge_gate_passes_when_all_inputs_are_approved_and_true():
    result = verification.evaluate_merge_gate(_passing_inputs())

    assert result == {
        "status": "passed",
        "blocking_reasons": [],
        "mode": "no_gpu_static_validation",
    }


def test_merge_gate_blocks_failed_review():
    inputs = _passing_inputs()
    inputs["review_verdict"] = "changes_requested"

    result = verification.evaluate_merge_gate(inputs)

    assert result["status"] == "blocked"
    assert result["blocking_reasons"] == ["review_verdict"]
    assert result["mode"] == "no_gpu_static_validation"


def test_merge_gate_blocks_gpu_gate_blocking_true():
    inputs = _passing_inputs()
    inputs["gpu_gate_blocking"] = True

    result = verification.evaluate_merge_gate(inputs)

    assert result["status"] == "blocked"
    assert result["blocking_reasons"] == ["gpu_gate_blocking"]
    assert result["mode"] == "no_gpu_static_validation"


def test_merge_gate_reports_failed_booleans_in_gate_order():
    inputs = _passing_inputs()
    inputs["plugin_tests_passed"] = False
    inputs["static_comparator_passed"] = False
    inputs["working_tree_clean"] = False

    result = verification.evaluate_merge_gate(inputs)

    assert result["status"] == "blocked"
    assert result["blocking_reasons"] == [
        "plugin_tests_passed",
        "static_comparator_passed",
        "working_tree_clean",
    ]
    assert result["mode"] == "no_gpu_static_validation"
