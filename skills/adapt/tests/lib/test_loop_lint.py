"""SAFE-02: /loop must NOT appear as an invocation in skill code paths.

Allowed: prose mentions in SKILL.md and references/* (e.g. "the /loop boundary").
Forbidden: actual invocation patterns — `/loop <args>`, SlashCommand("/loop..."),
loop_command = "/loop..."."""
from __future__ import annotations

import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]   # .../loongforge-plugin
SCAN_DIRS = [
    REPO_ROOT / "skills" / "adapt" / "scripts",
    REPO_ROOT / "skills" / "adapt" / "lib",
    REPO_ROOT / "agents",
]
ALLOWED_FILES = {
    REPO_ROOT / "skills" / "adapt" / "SKILL.md",
}

INVOKE_PATTERNS = (
    re.compile(r"^/loop\b"),                            # /loop at line start
    re.compile(r"SlashCommand\s*\(\s*['\"]/loop"),      # programmatic invoke
    re.compile(r"loop_command\s*=\s*['\"]/loop"),
)


def _scan_file(p: pathlib.Path) -> list[tuple[int, str]]:
    if p.is_dir() or p.suffix not in {".py", ".md", ".sh"}:
        return []
    if "references" in p.parts:
        return []  # references/* allowed to mention /loop freely
    out: list[tuple[int, str]] = []
    try:
        text = p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError):
        return []
    for i, line in enumerate(text.splitlines(), start=1):
        for pat in INVOKE_PATTERNS:
            if pat.search(line):
                out.append((i, line.strip()))
                break
    return out


def test_no_loop_invocation_in_skill_code():
    """SAFE-02: /loop must not appear as an invocation in skill code paths."""
    hits: list[tuple[pathlib.Path, int, str]] = []
    for d in SCAN_DIRS:
        if not d.exists():
            continue
        for p in d.rglob("*"):
            if p in ALLOWED_FILES:
                continue
            hits.extend([(p, ln, line) for ln, line in _scan_file(p)])
    assert not hits, "/loop invocation found in skill code:\n" + "\n".join(
        f"  {p}:{ln}  {line}" for p, ln, line in hits
    )


def test_lint_regex_actually_catches_invocations(tmp_path):
    """Positive control: prove the regex catches a forbidden invocation.
    Without this, the main test could pass tautologically if regexes were broken."""
    f = tmp_path / "evil.py"
    f.write_text('SlashCommand("/loop fix-everything")\n')
    hits = _scan_file(f)
    assert hits, "INVOKE_PATTERNS failed to match a known-bad invocation"
