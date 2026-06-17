#!/usr/bin/env python3
"""Run perf-reviewer over every corpus_must_not_trip file listed in the
witness expectations file. Fail if any rule whose status > "draft" exceeds
the per-file `max_severity_allowed` cap, or if any draft rule produces a
"would-have-been-FAIL" finding (declared_severity FAIL) on a corpus file —
which means once the rule promotes it WILL false-positive on a known-good
model."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WITNESS_DIR = ROOT / "eval" / "witnesses" / "deepseek_v4_flash"
PERF_REVIEW = ROOT / "skills" / "adapt" / "scripts" / "perf_review.py"
REPO_ROOT = ROOT.parent

SEVERITY_ORDER = {"INFO": 0, "WARN": 1, "FAIL": 2}


def load_yaml(path: Path) -> dict:
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def review(target: Path) -> dict:
    out = subprocess.check_output(
        [sys.executable, str(PERF_REVIEW), str(target), "--json"], text=True
    )
    return json.loads(out)


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true",
                    help="also fail on declared_severity > cap, even if currently capped by draft")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    expected = load_yaml(WITNESS_DIR / "expected_perf_findings.yml")
    corpus_specs = expected.get("corpus_must_not_trip", [])

    report = {"files": [], "pass": True}
    for spec in corpus_specs:
        rel = spec["file"]
        rules = set(spec.get("rules") or [])
        max_allowed = spec.get("max_severity_allowed", "WARN")
        target = REPO_ROOT / rel
        if not target.exists():
            report["files"].append({"file": rel, "status": "missing"})
            continue
        review_out = review(target)
        offenders = []
        for f in review_out["findings"]:
            if rules and f["rule_id"] not in rules:
                continue
            actual_sev = f["severity"]
            declared = f["declared_severity"]
            sev_to_check = declared if args.strict else actual_sev
            if SEVERITY_ORDER[sev_to_check] > SEVERITY_ORDER[max_allowed]:
                offenders.append({
                    "rule_id": f["rule_id"],
                    "line": f["line_start"],
                    "severity": actual_sev,
                    "declared_severity": declared,
                    "note": f["note"],
                })
        report["files"].append({
            "file": rel,
            "rules_checked": sorted(rules) or "all",
            "max_severity_allowed": max_allowed,
            "offenders": offenders,
            "status": "ok" if not offenders else "trip",
        })
        if offenders:
            report["pass"] = False

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for f in report["files"]:
            mark = {"ok": "✓", "trip": "✗", "missing": "?"}[f["status"]]
            print(f"{mark} {f['file']}")
            for o in f.get("offenders", []):
                print(f"    {o['severity']} {o['rule_id']} L{o['line']}: {o['note']}")
        print(f"\nresult: {'PASS' if report['pass'] else 'FAIL'}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
