"""Extract per-iteration loss values from Megatron-LM training stdout."""
from __future__ import annotations

import re

# Matches `lm loss: <float>` with either scientific (1.024E+01) or decimal (2.7183) form.
_LOSS_RE = re.compile(r"lm loss:\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)")
# Matches ANSI CSI sequences (e.g. \x1b[33m, \x1b[0m, \x1b[1;31m) that Megatron's
# logger emits when stdout is a TTY. Same scope as `tests/tools/log2json.py` strips.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def extract_losses(text: str, max_steps: int) -> list[float]:
    """Return the first `max_steps` `lm loss` values from `text`, in order.

    ANSI color codes (CSI sequences) are stripped before matching. Returns an
    empty list when the `lm loss:` token is not found.
    """
    if max_steps <= 0:
        return []
    matches = _LOSS_RE.findall(_ANSI_RE.sub("", text))
    return [float(v) for v in matches[:max_steps]]
