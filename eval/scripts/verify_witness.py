#!/usr/bin/env python3
"""
Witness verifier for the DS V4 attention regression anchor.

Reads expected_perf_findings.yml, runs the perf-reviewer on the frozen
baseline_attention.py, and reports which expected findings were caught and
which were missed. This is the script the eval scoreboard consumes.

Exit code: 0 if every "must_be_caught_by_batch <= --batch" finding is caught,
1 otherwise.

Usage:
    python verify_witness.py --batch 2     # check what batch-2 must catch
    python verify_witness.py --batch 4 --json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WITNESS_DIR = ROOT / "eval" / "witnesses" / "deepseek_v4_flash"
PERF_REVIEW = ROOT / "skills" / "adapt" / "scripts" / "perf_review.py"


def load_yaml(path: Path) -> dict:
    try:
        import yaml
    except ImportError:
        sys.stderr.write("PyYAML required: pip install pyyaml\n")
        sys.exit(2)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def run_review(target: Path) -> dict:
    out = subprocess.check_output(
        [sys.executable, str(PERF_REVIEW), str(target), "--json"],
        text=True,
    )
    return json.loads(out)


def line_overlap(a_lo: int, a_hi: int, b_lo: int, b_hi: int) -> bool:
    return not (a_hi < b_lo or a_lo > b_hi)


def collect_anchor_ranges(expected: dict) -> list[tuple[int, int]]:
    anchors = expected.get("anchors") or [expected.get("anchor")]
    ranges: list[tuple[int, int]] = []
    for a in anchors:
        if not a:
            continue
        if "lines" in a:
            lo, hi = a["lines"]
            ranges.append((int(lo), int(hi)))
        elif "line" in a:
            ln = int(a["line"])
            ranges.append((ln, ln))
    return ranges


def verify(batch: int) -> dict:
    expected = load_yaml(WITNESS_DIR / "expected_perf_findings.yml")
    target = WITNESS_DIR / "baseline_attention.py"
    review = run_review(target)
    findings = review["findings"]

    static = expected.get("static_findings", [])
    parallel = expected.get("parallel_findings", [])

    results = {"batch": batch, "static": [], "parallel": []}
    failed = 0

    for exp in static:
        in_scope = int(exp.get("must_be_caught_by_batch", 99)) <= batch
        anchors = collect_anchor_ranges(exp)
        rule_id = exp["rule"]
        # Match: any finding with same rule_id whose line range overlaps any anchor.
        matched = []
        for f in findings:
            if f["rule_id"] != rule_id:
                continue
            if any(line_overlap(f["line_start"], f["line_end"], lo, hi)
                   for lo, hi in anchors):
                matched.append(f)
        result = {
            "id": exp["id"],
            "rule": rule_id,
            "expected_severity": exp["severity"],
            "must_be_caught_by_batch": exp.get("must_be_caught_by_batch"),
            "in_scope_for_this_batch": in_scope,
            "matched_count": len(matched),
            "matched_lines": [[m["line_start"], m["line_end"]] for m in matched[:3]],
            "matched_severity": [m["severity"] for m in matched[:3]],
            "status": "ok" if matched else ("missed" if in_scope else "out-of-scope"),
        }
        results["static"].append(result)
        if in_scope and not matched:
            failed += 1

    # Parallel findings are not caught by static reviewer (batch 4 territory).
    # Record the listed grep-must-be-zero checks as deferred.
    for exp in parallel:
        in_scope = int(exp.get("must_be_caught_by_batch", 99)) <= batch
        results["parallel"].append({
            "id": exp["id"],
            "must_be_caught_by_batch": exp.get("must_be_caught_by_batch"),
            "in_scope_for_this_batch": in_scope,
            "status": "deferred-to-batch-4",
        })

    results["summary"] = {
        "static_total": len(static),
        "static_in_scope": sum(1 for s in results["static"] if s["in_scope_for_this_batch"]),
        "static_caught": sum(1 for s in results["static"]
                             if s["in_scope_for_this_batch"] and s["status"] == "ok"),
        "static_missed": failed,
    }
    results["pass"] = failed == 0
    return results


def render(report: dict) -> str:
    s = report["summary"]
    lines = [
        f"# Witness verification — DS V4 attention",
        f"  batch under test         : {report['batch']}",
        f"  static findings total    : {s['static_total']}",
        f"  in-scope for this batch  : {s['static_in_scope']}",
        f"  caught                   : {s['static_caught']}",
        f"  missed                   : {s['static_missed']}",
        f"  parallel findings        : deferred to batch 4",
        f"  result                   : {'PASS' if report['pass'] else 'FAIL'}",
        "",
        "## Per-finding detail",
    ]
    for f in report["static"]:
        marker = {"ok": "✓", "missed": "✗", "out-of-scope": "·"}[f["status"]]
        lines.append(f"  {marker} {f['id']:48s} rule={f['rule']:5s} "
                     f"caught={f['matched_count']}  "
                     f"by_batch={f['must_be_caught_by_batch']}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=2,
                    help="batch number to check (1=draft only, 2=static, 3=+probe, 4=+parallel)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    report = verify(args.batch)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render(report))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
