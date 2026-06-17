"""Merge-gate verification helpers for loongforge-issue-loop."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


BOOLEAN_GATES = [
    "issue_acceptance_passed",
    "plugin_tests_passed",
    "phase_artifact_gate_passed",
    "static_comparator_passed",
    "downstream_readiness_passed",
    "working_tree_clean",
    "pr_mergeable",
]

MODE = "no_gpu_static_validation"


def evaluate_merge_gate(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate whether issue-loop output is ready to merge.

    The current loop runs in Mac/static-validation mode, so GPU runtime checks are
    non-blocking unless the caller explicitly sets ``gpu_gate_blocking``.
    """
    blocking_reasons: list[str] = []

    for gate in BOOLEAN_GATES:
        if inputs.get(gate) is not True:
            blocking_reasons.append(gate)

    if inputs.get("review_verdict") != "approved":
        blocking_reasons.append("review_verdict")

    if inputs.get("gpu_gate_blocking") is True:
        blocking_reasons.append("gpu_gate_blocking")

    return {
        "status": "blocked" if blocking_reasons else "passed",
        "blocking_reasons": blocking_reasons,
        "mode": MODE,
    }
