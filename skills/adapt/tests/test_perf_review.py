"""End-to-end test for the perf-reviewer + DS V4 witness.

Run via: pytest claude-loongforge-plugin/skills/adapt/tests/test_perf_review.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
PERF_REVIEW = PLUGIN_ROOT / "skills" / "adapt" / "scripts" / "perf_review.py"
WITNESS_DIR = PLUGIN_ROOT / "eval" / "witnesses" / "deepseek_v4_flash"
VERIFY_WITNESS = PLUGIN_ROOT / "eval" / "scripts" / "verify_witness.py"
CORPUS_NEG = PLUGIN_ROOT / "eval" / "scripts" / "check_corpus_negatives.py"


def _run_json(*args: str) -> dict:
    out = subprocess.check_output([sys.executable, *args], text=True)
    return json.loads(out)


def test_perf_review_runs_on_witness_and_produces_findings():
    target = WITNESS_DIR / "baseline_attention.py"
    assert target.exists(), "DS V4 witness baseline not vendored"
    out = _run_json(str(PERF_REVIEW), str(target), "--json")
    assert out["findings"], "perf-reviewer produced no findings on the regression witness"
    rule_ids = {f["rule_id"] for f in out["findings"]}
    # Must hit at least the high-severity rules we hand-derived from V4.
    assert {"P004", "P005", "P011", "P012", "P013", "P014"} <= rule_ids


def test_witness_verifier_passes_at_batch_2():
    proc = subprocess.run(
        [sys.executable, str(VERIFY_WITNESS), "--batch", "2", "--json"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, (
        "witness verification failed at batch 2:\n" + proc.stdout + proc.stderr
    )
    report = json.loads(proc.stdout)
    s = report["summary"]
    assert s["static_missed"] == 0
    assert s["static_caught"] >= s["static_in_scope"]


def test_corpus_negative_files_do_not_trip_p_rules():
    proc = subprocess.run(
        [sys.executable, str(CORPUS_NEG), "--json"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, (
        "corpus negative check failed:\n" + proc.stdout + proc.stderr
    )
    report = json.loads(proc.stdout)
    assert report["pass"]
    assert all(f["status"] == "ok" for f in report["files"])


def test_draft_rules_emit_only_info():
    """Until rules are promoted past 'draft', the reviewer must not raise WARN
    or FAIL — that's the bootstrapping safety net."""
    target = WITNESS_DIR / "baseline_attention.py"
    out = _run_json(str(PERF_REVIEW), str(target), "--json")
    for f in out["findings"]:
        assert f["severity"] == "INFO", (
            f"rule {f['rule_id']} emitted {f['severity']} but its status is "
            f"{out['rule_status'].get(f['rule_id'])}"
        )
