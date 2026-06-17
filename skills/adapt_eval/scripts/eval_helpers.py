"""Pure helpers for /loongforge:adapt_eval. No subprocess / no agent dispatch."""
from __future__ import annotations

import datetime
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

LOSS_HARD_GATE = 1e-2
PASS_VERDICTS = ("PASS", "BASELINE")


def _atomic_write_text(path: Path, text: str) -> None:
    """Write text atomically: temp file + os.replace within the same dir.

    Survives SIGKILL/OOM mid-write so we never see partial YAML/JSON.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


# -- run_inputs ---------------------------------------------------------------

def init_eval_run_dir(
    family: str,
    hf_path: str,
    steps: int,
    plugin_commit: str,
    eval_root: Path,
) -> Path:
    """Create eval/runs/<ts>-<family>/ and write eval_run_inputs.yml."""
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = eval_root / "runs" / f"{ts}-{family}"
    run_dir.mkdir(parents=True, exist_ok=True)
    inputs = {
        "family": family,
        "hf_path": hf_path,
        "steps": steps,
        "plugin_commit": plugin_commit,
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    _atomic_write_text(
        run_dir / "eval_run_inputs.yml",
        yaml.dump(inputs, sort_keys=False, allow_unicode=True),
    )
    return run_dir


def load_eval_run_inputs(run_dir: Path) -> dict:
    return yaml.safe_load((run_dir / "eval_run_inputs.yml").read_text())


def update_eval_run_inputs(run_dir: Path, **fields: Any) -> dict:
    inputs = load_eval_run_inputs(run_dir)
    inputs.update(fields)
    _atomic_write_text(
        run_dir / "eval_run_inputs.yml",
        yaml.dump(inputs, sort_keys=False, allow_unicode=True),
    )
    return inputs


# -- autonomy -----------------------------------------------------------------

def compute_autonomy(adapt_run_dir: Path) -> dict:
    """Read phaseN_output.yml from `adapt_run_dir/phases/` and compute autonomy."""
    phase_status: dict[str, str] = {}
    for n in range(6):
        path = adapt_run_dir / "phases" / f"phase{n}_output.yml"
        if not path.exists():
            phase_status[f"phase{n}"] = "missing"
            continue
        data = yaml.safe_load(path.read_text()) or {}
        phase_status[f"phase{n}"] = data.get("status", "missing")

    passed_1_to_4 = sum(1 for n in (1, 2, 3, 4) if phase_status[f"phase{n}"] == "passed")
    return {
        "score": passed_1_to_4 / 4,
        "phase_status": phase_status,
        "phase0_5_ok": (
            phase_status["phase0"] == "passed" and phase_status["phase5"] == "passed"
        ),
    }


# -- loss diff ----------------------------------------------------------------

def compute_loss_diff(baseline: list[float], new: list[float]) -> dict:
    if not baseline or not new:
        raise ValueError("loss curves are empty")
    if len(baseline) != len(new):
        raise ValueError(f"loss curve length mismatch: {len(baseline)} vs {len(new)}")
    per_step = [abs(b - n) for b, n in zip(baseline, new)]
    return {"max_abs_diff": max(per_step), "per_step_diff": per_step}


# -- scoreboard ---------------------------------------------------------------

def find_last_entry(scoreboard_json: Path, family: str) -> dict | None:
    if not scoreboard_json.exists():
        return None
    entries = json.loads(scoreboard_json.read_text() or "[]")
    candidates = [
        e for e in entries
        if e.get("family") == family and e.get("verdict") in PASS_VERDICTS
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda e: e.get("timestamp", ""))
    return candidates[-1]


def append_scoreboard(scoreboard_md: Path, scoreboard_json: Path, entry: dict) -> None:
    """Append a PASS/BASELINE/REGRESSED entry to both scoreboards. Skip INVALID."""
    if entry.get("verdict") == "INVALID":
        return

    # JSON
    arr = json.loads(scoreboard_json.read_text() or "[]") if scoreboard_json.exists() else []
    arr.append(entry)
    _atomic_write_text(scoreboard_json, json.dumps(arr, indent=2, ensure_ascii=False))

    # Markdown
    md = render_scoreboard_entry(entry)
    existing = scoreboard_md.read_text() if scoreboard_md.exists() else ""
    _atomic_write_text(scoreboard_md, existing.rstrip() + "\n\n" + md + "\n")


def render_scoreboard_entry(entry: dict) -> str:
    """Render one Markdown block following design §5.3."""
    metrics = entry.get("metrics", {})
    delta = entry.get("delta_vs_last") or {}
    family = entry.get("family", "?")
    verdict = entry.get("verdict", "?")
    ts = entry.get("timestamp", "?").replace("T", " ")[:16]
    plugin_commit = (entry.get("plugin_commit") or "?")[:8]
    last_commit = (delta.get("last_plugin_commit") or "")[:8]
    vs_clause = f" (vs {last_commit})" if last_commit else ""

    lines = [f"## [{ts}] {verdict} | {family} | {plugin_commit}{vs_clause}"]
    auto = metrics.get("autonomy")
    if auto is not None:
        was = delta.get("autonomy_was")
        was_part = f"  (was {was:.2f})" if isinstance(was, (int, float)) else ""
        mark = "✓" if (was is None or auto >= was) else "✗"
        lines.append(f"- autonomy:       {auto:.2f}{was_part}  {mark}")
    loss = metrics.get("loss_max_diff")
    if loss is not None:
        mark = "✓" if loss < LOSS_HARD_GATE else "✗"
        lines.append(f"- loss_max_diff:  {loss:.4f}  (< 1e-2)  {mark}")
    omni = metrics.get("omni_score")
    if omni is not None:
        was = delta.get("omni_score_was")
        was_part = f"  (was {was})" if was is not None else ""
        mark = "✓" if (was is None or omni >= was) else "✗"
        lines.append(f"- omni_score:     {omni}{was_part}  {mark}")
    rd = entry.get("run_dir_relative")
    if rd:
        lines.append(f"- run: {rd}")
    reasons = entry.get("verdict_reasons") or []
    if reasons:
        lines.append(f"- reasons: {', '.join(reasons)}")
    return "\n".join(lines)


# -- verdict ------------------------------------------------------------------

def compute_verdict(metrics: dict, last_entry: dict | None) -> dict:
    """Apply design §5.2 Step 5 / §5.4 / §5.5 decision tree."""
    reasons: list[str] = []

    if not metrics.get("phase0_5_ok"):
        reasons.append("phase0_5_failed")
        return {"status": "INVALID", "reasons": reasons}
    if metrics.get("loss_max_diff") is None:
        reasons.append("loss_unavailable")
        return {"status": "INVALID", "reasons": reasons}
    if metrics.get("omni_score") is None:
        reasons.append("omni_unavailable")
        return {"status": "INVALID", "reasons": reasons}

    if metrics["loss_max_diff"] >= LOSS_HARD_GATE:
        reasons.append("loss_max_diff")
        return {"status": "REGRESSED", "reasons": reasons}

    if last_entry is None:
        return {"status": "BASELINE", "reasons": []}

    last = last_entry.get("metrics", {})
    if metrics["autonomy"] < last.get("autonomy", 0):
        reasons.append("autonomy")
    if metrics["omni_score"] < last.get("omni_score", 0):
        reasons.append("omni_score")
    if reasons:
        return {"status": "REGRESSED", "reasons": reasons}
    return {"status": "PASS", "reasons": []}
