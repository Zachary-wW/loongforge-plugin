#!/usr/bin/env python3
"""
Minimal perf-reviewer for LoongForge generated model code.

Consumes the P-series rules described in
  claude-loongforge-plugin/skills/adapt/knowledge_base/perf_rules/RULES.md
and applies them as concrete pattern / AST checks against a target Python file.

This is the batch-1 implementation: pattern-driven, deterministic, no LLM
in the loop. The reviewer emits findings as JSON; status-gating (draft /
warn-only / enforced) is applied so a draft rule cannot exceed INFO unless
its status is upgraded centrally here.

Usage:
    python perf_review.py <target.py>                # human-readable report
    python perf_review.py <target.py> --json         # JSON for the harness
    python perf_review.py <target.py> --rules P004,P005   # subset

Exit code: 0 always (the orchestrator decides what's fatal based on findings).
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Iterable


# ---------------------------------------------------------------------------
# Status gate. Mirrors RULES.md. Severity emitted by a rule is capped here.
# ---------------------------------------------------------------------------

RULE_STATUS = {
    # rule_id -> "draft" | "warn-only" | "enforced"
    "P004": "draft",
    "P005": "draft",
    "P006": "draft",
    "P007": "draft",
    "P008": "draft",
    "P009": "draft",
    "P010": "draft",
    "P011": "draft",
    "P012": "draft",
    "P013": "draft",
    "P014": "draft",
    "P015": "draft",
}

SEVERITY_ORDER = {"INFO": 0, "WARN": 1, "FAIL": 2}

# Status caps: a draft rule can only emit INFO; warn-only caps at WARN; enforced
# emits whatever the rule declares. The reviewer's job is detection — promotion
# is managed by changing RULE_STATUS, not by individual rules.
STATUS_CAP = {"draft": "INFO", "warn-only": "WARN", "enforced": "FAIL"}


def cap_severity(rule_id: str, declared: str) -> str:
    cap = STATUS_CAP[RULE_STATUS.get(rule_id, "draft")]
    if SEVERITY_ORDER[declared] <= SEVERITY_ORDER[cap]:
        return declared
    return cap


# ---------------------------------------------------------------------------
# Finding record + helpers
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    rule_id: str
    severity: str            # post-cap severity actually emitted
    declared_severity: str   # what the rule wanted to emit before capping
    line_start: int
    line_end: int
    snippet: str
    note: str = ""

    def overlaps(self, lo: int, hi: int) -> bool:
        return not (self.line_end < lo or self.line_start > hi)


# ---------------------------------------------------------------------------
# Detector toolkit
# ---------------------------------------------------------------------------


def lines_of(src: str) -> list[str]:
    return src.splitlines()


def find_pattern_lines(src_lines: list[str], pattern: str) -> list[int]:
    rx = re.compile(pattern)
    return [i + 1 for i, ln in enumerate(src_lines) if rx.search(ln)]


def block_around(src_lines: list[str], line_no: int, ctx: int = 1) -> tuple[int, int, str]:
    lo = max(1, line_no - ctx)
    hi = min(len(src_lines), line_no + ctx)
    return lo, hi, "\n".join(src_lines[lo - 1:hi])


# ---------------------------------------------------------------------------
# Hot-path scope.  We treat functions named "forward" or any function called
# transitively from forward() as hot path.  For batch-1 simplicity we use the
# simpler proxy "method named forward + any free function called inside it".
# This covers the known corpus well enough; refining is a batch-2 concern.
# ---------------------------------------------------------------------------


def collect_hot_path_lines(tree: ast.AST) -> set[int]:
    """Return the set of source line numbers that live inside any function
    named `forward` (or `_apply_rotary`, the obvious helpers)."""
    targets = {"forward", "_apply_rotary", "_compute_attention",
               "_overlap_transform", "_indexer_score", "_grouped_output_proj"}
    in_scope: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in targets or node.name == "forward":
                start = node.lineno
                end = getattr(node, "end_lineno", start)
                in_scope.update(range(start, end + 1))
    return in_scope


# ===========================================================================
# Rule implementations.  Each rule_* function receives:
#   src_text  : full file text
#   src_lines : list of lines (1-indexed via src_lines[i-1])
#   tree      : parsed ast.AST  (None if file failed to parse)
#   hot_lines : set[int] of line numbers in hot path
# and returns: list[Finding].
# ===========================================================================


def rule_P004_nested_python_for(src_text, src_lines, tree, hot_lines) -> list[Finding]:
    """Two nested Python `for` loops whose innermost body writes to a tensor
    subscript or calls a tensor op."""
    findings: list[Finding] = []
    if tree is None:
        return findings

    ALLOWED_ITER_NAMES = {"num_layers", "self.layers", "self.experts"}

    def iter_name_str(call_or_name: ast.AST) -> str:
        try:
            return ast.unparse(call_or_name)
        except Exception:
            return ""

    for outer in ast.walk(tree):
        if not isinstance(outer, ast.For):
            continue
        if outer.lineno not in hot_lines:
            continue
        # Skip layer/expert top-level construction loops.
        outer_iter = iter_name_str(outer.iter)
        if any(s in outer_iter for s in ALLOWED_ITER_NAMES):
            continue
        for inner in ast.walk(outer):
            if not isinstance(inner, ast.For) or inner is outer:
                continue
            # Look at inner.body for tensor write / tensor call.
            for stmt in ast.walk(inner):
                if isinstance(stmt, ast.Assign):
                    for tgt in stmt.targets:
                        if isinstance(tgt, ast.Subscript):
                            findings.append(Finding(
                                rule_id="P004",
                                declared_severity="FAIL",
                                severity=cap_severity("P004", "FAIL"),
                                line_start=outer.lineno,
                                line_end=getattr(inner, "end_lineno", inner.lineno),
                                snippet=f"for {iter_name_str(outer.target)} in ...:\n  for {iter_name_str(inner.target)} in ...:\n    <tensor subscript write>",
                                note="nested Python for-loops driving tensor scatter in hot path",
                            ))
                            return findings  # one is enough per file
    return findings


def rule_P005_value_is_clone_of_key(src_text, src_lines, tree, hot_lines) -> list[Finding]:
    findings: list[Finding] = []
    rx = re.compile(r"\bvalue\s*=\s*key\.clone\s*\(\s*\)")
    for ln_no, ln in enumerate(src_lines, start=1):
        if rx.search(ln):
            findings.append(Finding(
                rule_id="P005",
                declared_severity="FAIL",
                severity=cap_severity("P005", "FAIL"),
                line_start=ln_no, line_end=ln_no,
                snippet=ln.strip(),
                note="V==K should reuse the tensor; clone() doubles KV memory",
            ))
    return findings


def rule_P006_redundant_ops(src_text, src_lines, tree, hot_lines) -> list[Finding]:
    findings: list[Finding] = []
    patterns = [
        (r"\.permute\([^)]*\)\.contiguous\(\)",
         "permute(...).contiguous() — layout transform may be unnecessary"),
        (r"\.to\(\s*(torch\.[a-zA-Z0-9_]+|[a-zA-Z_.]*dtype)\s*\)",
         ".to(<dtype>) inside hot path; cast at init or rely on autocast"),
        (r"\.item\s*\(\s*\)|\.cpu\s*\(\s*\)|\.numpy\s*\(\s*\)|\.tolist\s*\(\s*\)",
         "host sync (.item/.cpu/.numpy/.tolist) on hot-path tensor"),
    ]
    for ln_no, ln in enumerate(src_lines, start=1):
        if ln_no not in hot_lines:
            continue
        for rx, note in patterns:
            if re.search(rx, ln):
                findings.append(Finding(
                    rule_id="P006",
                    declared_severity="WARN",
                    severity=cap_severity("P006", "WARN"),
                    line_start=ln_no, line_end=ln_no,
                    snippet=ln.strip(),
                    note=note,
                ))
                break
    return findings


def rule_P007_per_forward_alloc(src_text, src_lines, tree, hot_lines) -> list[Finding]:
    findings: list[Finding] = []
    rx = re.compile(r"\.new_full\s*\(|\btorch\.zeros\s*\(|\btorch\.empty\s*\(|\btorch\.cat\s*\(\s*\[")
    for ln_no, ln in enumerate(src_lines, start=1):
        if ln_no not in hot_lines:
            continue
        if rx.search(ln) and "self." not in ln:  # ignore registered buffers
            findings.append(Finding(
                rule_id="P007",
                declared_severity="WARN",
                severity=cap_severity("P007", "WARN"),
                line_start=ln_no, line_end=ln_no,
                snippet=ln.strip(),
                note="per-forward buffer allocation; pre-allocate or cache",
            ))
    return findings


def rule_P011_kv_mask_full_materialise(src_text, src_lines, tree, hot_lines) -> list[Finding]:
    findings: list[Finding] = []
    # A4 / triple-permute KV expand
    rx_expand = re.compile(r"\.expand\([^)]*\)\.contiguous\(\)")
    rx_full_mask = re.compile(r"torch\.zeros\([^)]*sq[^)]*skv|torch\.zeros\([^)]*seq[^)]*skv|sdpa_mask\s*=\s*torch\.zeros")
    rx_dense_topk_mask = re.compile(r"comp_mask_dense|dense_topk_mask")
    rx_einsum_full = re.compile(r"torch\.einsum\(['\"]bqhd,bsd->bqhs['\"]")
    for ln_no, ln in enumerate(src_lines, start=1):
        if ln_no not in hot_lines and "comp_mask_dense" not in ln:
            continue
        for rx, note in [
            (rx_expand, "K/V expand+contiguous → use enable_gqa or broadcast view"),
            (rx_full_mask, "full [b,h,sq,skv] mask in activation dtype"),
            (rx_dense_topk_mask, "sparse top-k materialised as dense mask"),
            (rx_einsum_full, "indexer logits einsum produces full [b,sq,h,nc]"),
        ]:
            if rx.search(ln):
                findings.append(Finding(
                    rule_id="P011",
                    declared_severity="FAIL",
                    severity=cap_severity("P011", "FAIL"),
                    line_start=ln_no, line_end=ln_no,
                    snippet=ln.strip(),
                    note=note,
                ))
                break
    return findings


def rule_P012_attention_sink_via_kv_column(src_text, src_lines, tree, hot_lines) -> list[Finding]:
    findings: list[Finding] = []
    rx_sink_cat = re.compile(r"torch\.cat\s*\(\s*\[[^]]*sink|torch\.cat\s*\(\s*\[\s*k_sdpa\s*,|torch\.cat\s*\(\s*\[\s*key\s*,\s*sink")
    # Full-size sdpa_mask allocated to host an additive sink/causal bias spanning skv.
    rx_full_sdpa_mask = re.compile(r"sdpa_mask\s*=\s*torch\.zeros\s*\(")
    for ln_no, ln in enumerate(src_lines, start=1):
        if ln_no not in hot_lines:
            continue
        if rx_sink_cat.search(ln):
            findings.append(Finding(
                rule_id="P012",
                declared_severity="FAIL",
                severity=cap_severity("P012", "FAIL"),
                line_start=ln_no, line_end=ln_no,
                snippet=ln.strip(),
                note="attention sink should be a logit bias, not an extra KV column",
            ))
        elif rx_full_sdpa_mask.search(ln):
            findings.append(Finding(
                rule_id="P012",
                declared_severity="FAIL",
                severity=cap_severity("P012", "FAIL"),
                line_start=ln_no, line_end=ln_no,
                snippet=ln.strip(),
                note="full [b,h,sq,skv] sdpa_mask used as additive sink/causal bias; use is_causal + per-head bias",
            ))
    return findings


def rule_P013_dequantize_in_forward(src_text, src_lines, tree, hot_lines) -> list[Finding]:
    findings: list[Finding] = []
    rx = re.compile(r"\.dequantize\s*\(\s*\)")
    for ln_no, ln in enumerate(src_lines, start=1):
        if ln_no not in hot_lines:
            continue
        if rx.search(ln):
            findings.append(Finding(
                rule_id="P013",
                declared_severity="FAIL",
                severity=cap_severity("P013", "FAIL"),
                line_start=ln_no, line_end=ln_no,
                snippet=ln.strip(),
                note=".dequantize() in forward defeats FP8 GEMM",
            ))
    return findings


def rule_P014_einsum_on_weight(src_text, src_lines, tree, hot_lines) -> list[Finding]:
    """Flag matmul/einsum where one operand is a Linear's .weight (or an alias
    of it via .view/.reshape/.dequantize/.to/.flatten). Catches the pattern
    where the .weight is aliased through .view before the einsum."""
    findings: list[Finding] = []
    if tree is None:
        return findings

    # Build alias set: variables assigned (directly or transitively) from a
    # `*.weight` access. Restricted to the function scope.
    weight_aliases: set[str] = set()
    src_in_hot: list[tuple[int, str]] = [
        (i + 1, ln) for i, ln in enumerate(src_lines)
        if (i + 1) in hot_lines
    ]
    rx_assign = re.compile(r"^\s*(\w+)\s*=\s*(.+?)\s*$")
    rx_weight_access = re.compile(r"\.weight\b")
    forwarding_methods = ("view", "reshape", "flatten", "dequantize",
                          "to", "transpose", "permute", "contiguous", "type_as")
    # Two passes — handles `wo_a_weight = self.linear_wo_a.weight` then
    # `wo_a_w = wo_a_weight.view(...)`.
    for _ in range(3):
        for ln_no, ln in src_in_hot:
            m = rx_assign.match(ln)
            if not m:
                continue
            lhs, rhs = m.group(1), m.group(2)
            if rx_weight_access.search(rhs):
                weight_aliases.add(lhs)
                continue
            for alias in list(weight_aliases):
                if re.search(rf"\b{re.escape(alias)}\b\s*\.\s*({'|'.join(forwarding_methods)})\s*\(", rhs):
                    weight_aliases.add(lhs)
                    break

    rx_einsum = re.compile(r"torch\.einsum\s*\(([^)]+)\)")
    rx_matmul = re.compile(r"torch\.matmul\s*\(([^)]+)\)")
    for ln_no, ln in src_in_hot:
        for rx in (rx_einsum, rx_matmul):
            m = rx.search(ln)
            if not m:
                continue
            args = m.group(1)
            if rx_weight_access.search(args):
                hit_alias = ".weight"
            else:
                hit_alias = next(
                    (a for a in weight_aliases
                     if re.search(rf"\b{re.escape(a)}\b", args)),
                    None,
                )
            if not hit_alias:
                continue
            findings.append(Finding(
                rule_id="P014",
                declared_severity="FAIL",
                severity=cap_severity("P014", "FAIL"),
                line_start=ln_no, line_end=ln_no,
                snippet=ln.strip(),
                note=f"matmul/einsum reads Linear.weight (via '{hit_alias}'); bypasses TE GEMM/FP8/TP",
            ))
    # Also matrix-multiplication operator `.weight @ ...` form (kept as before).
    rx_at = re.compile(r"\b\w+\.weight\s*@\s*")
    for ln_no, ln in src_in_hot:
        if rx_at.search(ln):
            findings.append(Finding(
                rule_id="P014",
                declared_severity="FAIL",
                severity=cap_severity("P014", "FAIL"),
                line_start=ln_no, line_end=ln_no,
                snippet=ln.strip(),
                note="`.weight @ x` bypasses TE GEMM/FP8/TP",
            ))
    return findings


def rule_P015_rope_recomputed(src_text, src_lines, tree, hot_lines) -> list[Finding]:
    findings: list[Finding] = []
    rx = re.compile(r"torch\.outer\([^)]*positions[^)]*inv_freq|torch\.outer\([^)]*inv_freq[^)]*positions|torch\.outer\([^)]*positions[^)]*self\.\w*inv_freq")
    for ln_no, ln in enumerate(src_lines, start=1):
        if ln_no not in hot_lines:
            continue
        if rx.search(ln):
            findings.append(Finding(
                rule_id="P015",
                declared_severity="WARN",
                severity=cap_severity("P015", "WARN"),
                line_start=ln_no, line_end=ln_no,
                snippet=ln.strip(),
                note="RoPE freq recomputed in forward; cache cos/sin in a buffer",
            ))
    return findings


# Registry
RULES: dict[str, Callable] = {
    "P004": rule_P004_nested_python_for,
    "P005": rule_P005_value_is_clone_of_key,
    "P006": rule_P006_redundant_ops,
    "P007": rule_P007_per_forward_alloc,
    "P011": rule_P011_kv_mask_full_materialise,
    "P012": rule_P012_attention_sink_via_kv_column,
    "P013": rule_P013_dequantize_in_forward,
    "P014": rule_P014_einsum_on_weight,
    "P015": rule_P015_rope_recomputed,
}


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def review_file(path: Path, only: Iterable[str] | None = None) -> list[Finding]:
    src_text = path.read_text(encoding="utf-8")
    src_lines = lines_of(src_text)
    try:
        tree = ast.parse(src_text)
    except SyntaxError:
        tree = None
    hot_lines = collect_hot_path_lines(tree) if tree else set(range(1, len(src_lines) + 1))

    selected = list(RULES.keys()) if not only else [r for r in RULES if r in set(only)]
    out: list[Finding] = []
    for rule_id in selected:
        out.extend(RULES[rule_id](src_text, src_lines, tree, hot_lines))
    out.sort(key=lambda f: (f.line_start, f.rule_id))
    return out


def render_text(path: Path, findings: list[Finding]) -> str:
    lines = [f"# perf-review report\nfile: {path}\nfindings: {len(findings)}\n"]
    by_sev = {"FAIL": 0, "WARN": 0, "INFO": 0}
    for f in findings:
        by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
    lines.append(f"  FAIL={by_sev['FAIL']} WARN={by_sev['WARN']} INFO={by_sev['INFO']}\n")
    for f in findings:
        cap_note = ""
        if f.declared_severity != f.severity:
            cap_note = f"  (capped from {f.declared_severity} by RULE_STATUS={RULE_STATUS[f.rule_id]})"
        lines.append(f"[{f.severity}] {f.rule_id}  L{f.line_start}-{f.line_end}{cap_note}")
        if f.note:
            lines.append(f"    note: {f.note}")
        lines.append(f"    code: {f.snippet[:160]}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", type=Path)
    ap.add_argument("--rules", type=str, default=None,
                    help="comma-separated subset, e.g. P004,P011")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    only = args.rules.split(",") if args.rules else None
    findings = review_file(args.target, only=only)

    if args.json:
        payload = {
            "file": str(args.target),
            "rule_status": RULE_STATUS,
            "findings": [asdict(f) for f in findings],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(render_text(args.target, findings))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
