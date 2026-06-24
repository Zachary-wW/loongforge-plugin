# Phase 1 RESEARCH — Loop Foundation: Contracts, Schemas & Safety Plumbing

**Goal recap:** Establish contracts/schemas/safety plumbing only. No loop behavior. Deliverables: extended `run_inputs.yml` schema, 4 URL flags + `--dry-run`, Pydantic v2 models with v1 compat, preflight, redactor, GhClient interface + FakeGhClient stub, inert `_validate_loop_evidence()` hook, append-only `attempts.jsonl` writer, `/loop` lint, validator-protected-paths data module, pytest coverage.

**REQ-IDs:** INPUT-01, INPUT-02, INPUT-03, INPUT-04, LOG-02, LOG-03, SAFE-01, SAFE-02, SAFE-03, COMPAT-02, COMPAT-03, TEST-02, TEST-03

---

## 1. Module layout (final)

All new code lives under `skills/adapt/lib/` (new package) plus a few extensions to existing scripts. Existing tree (read in full): `skills/adapt/scripts/run.py`, `skills/adapt/scripts/validate_phase_completion.py`.

| File | Responsibility | Est. LOC | Dependencies |
|------|----------------|----------|--------------|
| `skills/adapt/lib/__init__.py` | Package marker | 1 | — |
| `skills/adapt/lib/schema.py` | Pydantic v2 models for `RunInputs`, `ReposBlock`, `RepoSpec`, `HFCkptSpec`, `LoopBudget`, `PhaseOutputLoopFields` | ~180 | `pydantic>=2.9` |
| `skills/adapt/lib/redact.py` | Secret redactor (regex sweep + accept/reject) | ~80 | stdlib `re` |
| `skills/adapt/lib/gh_client.py` | `GhClient` Protocol + `RealGhClient` (stub) + `FakeGhClient` (in-memory) | ~140 | stdlib `subprocess`, `typing.Protocol` |
| `skills/adapt/lib/preflight.py` | gh auth / repo perms / ckpt URL / branch protection probes; `--dry-run` skips live writes | ~120 | `gh_client.py`, stdlib `urllib` |
| `skills/adapt/lib/protected_paths.py` | `PROTECTED_PATHS` tuple + `is_protected(path) -> bool` | ~30 | stdlib `fnmatch` |
| `skills/adapt/lib/jsonl.py` | `append_attempt(path, record)` — O_APPEND atomic-line writer | ~40 | stdlib `os`, `json`, `fcntl` |
| `skills/adapt/scripts/run.py` (extended) | Add 4 URL flags + `--dry-run`; build `repos:`/`loop:` blocks; call preflight | +90 | new `lib/*` |
| `skills/adapt/scripts/validate_phase_completion.py` (extended) | Add `_validate_loop_evidence()` gated by `loop_engineering: true` flag (inert when absent) | +25 | — |
| `skills/adapt/tests/lib/__init__.py` | Package marker | 1 | — |
| `skills/adapt/tests/lib/test_schema.py` | TEST-03 v1↔v2 round-trip | ~80 | pytest, `lib.schema` |
| `skills/adapt/tests/lib/test_redact.py` | TEST-02 snapshot tests | ~60 | pytest, `lib.redact` |
| `skills/adapt/tests/lib/test_jsonl_append_only.py` | LOG-03 invariant test | ~40 | pytest, `lib.jsonl` |
| `skills/adapt/tests/lib/test_loop_lint.py` | SAFE-02 grep guard | ~40 | pytest |
| `skills/adapt/tests/lib/test_preflight_dry_run.py` | INPUT-04 `--dry-run` skips writes; INPUT-03 fail-fast on bad auth | ~60 | pytest, `FakeGhClient` |
| `skills/adapt/tests/lib/test_validate_loop_evidence.py` | COMPAT-03 inert hook + future-flag honoured | ~50 | pytest |
| `skills/adapt/tests/lib/test_run_cli.py` | INPUT-01/02 CLI round-trip; COMPAT-02 legacy invocation | ~80 | pytest, `run.py:main` |

**Total new code:** ~1,100 LOC + tests.

**Why a new `lib/` package** instead of dumping into `scripts/`: `scripts/` are entrypoints (run via `bin/loongforge-adapt`), `lib/` is importable Python. Future Phase 2's `loop_controller.py` will live in `scripts/` and import from `lib/`.

---

## 2. Pydantic v2 schema (final)

`skills/adapt/lib/schema.py` — uses Pydantic v2.9+ idioms (`Field`, `model_validator`, `ConfigDict(extra='forbid')`).

```python
from __future__ import annotations
from typing import Optional, Literal, Any
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

# --- Repo specs ----------------------------------------------------------

class RepoSpec(BaseModel):
    """A single git repo reference (LoongForge or Loong-Megatron)."""
    model_config = ConfigDict(extra="forbid")
    url: HttpUrl
    base_ref: str = "main"
    work_branch: str = ""           # filled at loop time, not by user
    subpath: Optional[str] = None   # optional path within repo

class HFImplSpec(BaseModel):
    """HF model implementation reference (subpath inside HF transformers)."""
    model_config = ConfigDict(extra="forbid")
    url: HttpUrl
    ref: str = "main"
    subpath: Optional[str] = None

class HFCkptSpec(BaseModel):
    """HF checkpoint + tokenizer reference (HuggingFace hub URL)."""
    model_config = ConfigDict(extra="forbid")
    url: HttpUrl                    # https://huggingface.co/<org>/<model>
    revision: str = "main"

class ReposBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hf_impl: HFImplSpec
    hf_ckpt: HFCkptSpec
    loongforge: RepoSpec
    megatron: RepoSpec

class LoopBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_attempts_per_phase: int = Field(5, ge=1, le=50)
    max_attempts_per_run: int = Field(25, ge=1, le=500)
    max_wallclock_minutes: int = Field(240, ge=10, le=10_080)
    escalation: Literal["human_needed", "autonomous_blocked"] = "human_needed"

# --- run_inputs.yml v2 (legacy v1 stays valid) ---------------------------

class SourceBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hf_ckpt_path: str = ""

class PathsBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hf_modeling_path: str = ""
    hf_transformers_path: str = ""
    omni_path: str = ""
    megatron_path: str = ""

class OptionsBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_name: str = ""
    gpu_execution_mode: Literal["local_gpu", "k8s"] = "local_gpu"
    enable_slice_ckpt: Literal["true", "false"] = "false"
    k8s_yaml_path: str = ""
    k8s_launch_cmd: str = ""
    wip_code_paths: str = ""        # JSON-stringified list, kept opaque

class RunInputs(BaseModel):
    """Top-level run_inputs.yml. v1 had source/paths/options only.
    v2 adds optional repos and loop. Backward compat: omit them and we behave as v1."""
    model_config = ConfigDict(extra="forbid")
    source: SourceBlock = Field(default_factory=SourceBlock)
    paths: PathsBlock = Field(default_factory=PathsBlock)
    options: OptionsBlock = Field(default_factory=OptionsBlock)
    repos: Optional[ReposBlock] = None
    loop: Optional[LoopBudget] = None

    @model_validator(mode="after")
    def _v2_sanity(self) -> "RunInputs":
        # If `repos` is present, all four sub-fields must be present (Pydantic
        # already enforces this via ReposBlock). If `repos` is absent, we
        # silently disable loop engineering (loop_engineering=False downstream).
        return self

    @property
    def loop_engineering_enabled(self) -> bool:
        return self.repos is not None

# --- phaseN_output.yml extension (Phase 1 lays inert hook) ---------------

class LoopBlockOutput(BaseModel):
    """Optional `loop:` block in phaseN_output.yml. Only validated when
    loop_engineering: true is set."""
    model_config = ConfigDict(extra="forbid")
    attempts: int = Field(0, ge=0)
    max_attempts: int = Field(5, ge=1)
    exit_reason: Literal[
        "validator_passed", "validator_passed_after_fix",
        "exhausted", "escalated", "base_only", "human_needed",
    ] = "validator_passed"
    attempts_journal: str = ""
```

**Backward-compat strategy:** legacy `run_inputs.yml` (no `repos`, no `loop`) deserializes cleanly because both fields are `Optional` with default `None`. Validation strictness comes from `extra="forbid"` — typos like `repo:` (missing `s`) fail loudly.

**Strictness on URL fields:** `HttpUrl` rejects malformed URLs at parse time (Pydantic v2 calls `urllib`). Reachability check happens in preflight, not in the schema.

**Pydantic v2 version pin:** `pydantic>=2.9,<3` — already in research/STACK.md as the recommended pick.

---

## 3. CLI surface (final)

Extend `run.py:main` (current code at `skills/adapt/scripts/run.py:285-372`). New flags grouped under a separate argparse group.

```python
# Add after existing flag declarations (~line 316, before --from-phase):
repos_group = parser.add_argument_group("repos (loop engineering)")
repos_group.add_argument("--hf-impl-url", default=None,
    help="HF model impl repo URL (e.g. https://github.com/huggingface/transformers)")
repos_group.add_argument("--hf-impl-ref", default="main", help="HF impl branch/tag/sha")
repos_group.add_argument("--hf-impl-subpath", default=None,
    help="Path within HF impl repo (e.g. src/transformers/models/deepseek_v4)")
repos_group.add_argument("--hf-ckpt-url", default=None,
    help="HF Hub ckpt URL (e.g. https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-Base)")
repos_group.add_argument("--hf-ckpt-revision", default="main")
repos_group.add_argument("--loongforge-repo", default=None,
    help="LoongForge repo URL")
repos_group.add_argument("--loongforge-base-ref", default="main")
repos_group.add_argument("--megatron-repo", default=None,
    help="Loong-Megatron repo URL")
repos_group.add_argument("--megatron-base-ref", default="loong-main/core_v0.15.0")

dryrun_group = parser.add_argument_group("dry run")
dryrun_group.add_argument("--dry-run", action="store_true",
    help="Use FakeGhClient; skip live gh writes; still validate URL shape and schema")
```

**Decision:** explicit per-field flags, NOT a combined `URL@ref:subpath` syntax. Rationale: shell quoting of `@` and `:` is fragile; per-field flags self-document; `--help` lists them clearly. Cost: 8 flags vs 4. Acceptable.

**Decision:** all `repos`-related flags are optional. If ANY of the four URL flags is present, all four are required (validated in code, not argparse `required=`, because we still want the legacy positional `hf_path` to work alone). One-liner check:

```python
url_flags = [args.hf_impl_url, args.hf_ckpt_url, args.loongforge_repo, args.megatron_repo]
loop_engineering = any(url_flags)
if loop_engineering and not all(url_flags):
    parser.error("--hf-impl-url, --hf-ckpt-url, --loongforge-repo, --megatron-repo "
                 "must all be provided together")
```

**Decision:** `--dry-run` is a top-level flag, NOT under `repos`. It can be used with or without the URL flags. Without URLs: legacy run, no preflight (existing behavior). With URLs: schema validated, preflight runs in dry-run mode (skips live writes, keeps URL shape + auth-status check).

**`_build_run_inputs` extension** — add two kwargs `repos: Optional[dict] = None`, `loop: Optional[dict] = None`. Inject into the returned dict only when not None. Existing call sites pass nothing → unchanged behavior.

---

## 4. Preflight commands (final)

`skills/adapt/lib/preflight.py`:

```python
@dataclass
class PreflightResult:
    ok: bool
    failures: list[str]            # e.g. ["gh_auth_status: not logged in"]
    branch_protection: dict        # raw gh api output for record

def run_preflight(repos: ReposBlock, *, dry_run: bool, gh: GhClient) -> PreflightResult:
    """Probe gh + ckpt URL + branch protection.
    dry_run=True skips: write-permission probes, branch-protection writes.
    dry_run=True still does: URL shape check, gh auth status, ckpt HEAD probe.
    """
```

**Concrete `gh` invocations** (executed via `GhClient.run(["...", ...])`, which wraps `subprocess.run`):

| Check | Command | Pass condition |
|-------|---------|----------------|
| Auth | `gh auth status --hostname github.com` | exit 0 |
| Read perm | `gh api repos/<owner>/<repo>` | exit 0, JSON has `permissions.pull == true` |
| Write perm (skipped in `--dry-run`) | `gh api repos/<owner>/<repo> --jq .permissions.push` | output `true` |
| Branch protection | `gh api repos/<owner>/<repo>/branches/<base_ref>/protection` (404 means unprotected, OK) | exit 0 OR exit 1 with stderr containing "Branch not protected" |
| Ckpt URL reachable | `urllib.request.urlopen(HEAD, timeout=10)` on `https://huggingface.co/api/models/<org>/<model>` | HTTP 200 |
| HF impl URL reachable | `gh api repos/<owner>/<repo> --jq .default_branch` | exit 0 |

**Branch protection compatibility check:** read the protection JSON; if `required_status_checks.strict == true` AND no checks listed, fine; if `required_pull_request_reviews.required_approving_review_count > 0`, fail with: `"branch protection on <repo>:<branch> requires N approving reviews; loop's auto-merge cannot satisfy. Run with --require-human-merge or disable required reviews."` (The `--require-human-merge` flag is **not** in scope for Phase 1; we just emit the friendly error so Phase 2/3 can implement it later.)

**Fail-fast format** (one stable line per failure, ordered by gravity):
```
PREFLIGHT FAILED:
  - gh_auth_status: not logged in (run `gh auth login`)
  - megatron_write: missing push permission on Zachary-wW/Loong-Megatron
  - branch_protection: Zachary-wW/LoongForge:main requires 1 approving review (loop auto-merge incompatible)
Aborting. Re-run with --dry-run to bypass live-write probes.
```

Exit code: `2` (matches existing `BLOCK_EXIT_CODE` in `validate_phase_completion.py:17`).

**Dry-run path:** runs `gh auth status` AND URL shape AND HF API HEAD (all read-only / public), but skips repo write-perm and branch-protection probes. Returns `PreflightResult(ok=True, failures=[])` for any tests-only invocation that uses `FakeGhClient`.

---

## 5. Redactor (final)

`skills/adapt/lib/redact.py`:

```python
import re
from dataclasses import dataclass

# Order matters: longer/more-specific patterns FIRST so they win over shorter ones.
# All patterns are case-sensitive unless noted.
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("github_pat_v2",  re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("github_pat_v1",  re.compile(r"ghp_[A-Za-z0-9]{20,}")),
    ("github_oauth",   re.compile(r"gho_[A-Za-z0-9]{20,}")),
    ("github_user",    re.compile(r"ghu_[A-Za-z0-9]{20,}")),
    ("github_server",  re.compile(r"ghs_[A-Za-z0-9]{20,}")),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("hf_token",       re.compile(r"hf_[A-Za-z0-9]{20,}")),
    ("bearer_header",  re.compile(r"Bearer\s+[A-Za-z0-9._\-+/]{16,}")),
    ("home_path",      re.compile(r"/home/[a-zA-Z0-9_\-\.]+(/|$)")),
    ("aws_secret_kv",  re.compile(r"(?i)aws_secret(_access)?_key\s*[:=]\s*[A-Za-z0-9/+=]{30,}")),
)

# Internal-domain list lives in a YAML config so ops can extend without code change.
_INTERNAL_DOMAIN_CONFIG = "skills/adapt/knowledge_base/redact_domains.yml"

@dataclass(frozen=True)
class RedactionResult:
    cleaned: str
    matches: list[tuple[str, int]]   # [(pattern_name, count), ...]
    accept: bool                      # False = there is at least one residual hit after redaction (post-check)

def redact(text: str, *, internal_domains: tuple[str, ...] = ()) -> RedactionResult:
    """Replace each match with '[REDACTED:<name>]'. Re-run a sanity grep after
    replacement; if any pattern still matches, return accept=False so the caller
    refuses to post."""
    cleaned = text
    counts: dict[str, int] = {}
    for name, pat in _SECRET_PATTERNS:
        cleaned, n = pat.subn(f"[REDACTED:{name}]", cleaned)
        if n:
            counts[name] = n
    for dom in internal_domains:
        pat = re.compile(re.escape(dom))
        cleaned, n = pat.subn("[REDACTED:internal_domain]", cleaned)
        if n:
            counts.setdefault("internal_domain", 0)
            counts["internal_domain"] += n
    # Post-check: residual scan
    residual = any(p.search(cleaned) for _, p in _SECRET_PATTERNS)
    return RedactionResult(cleaned=cleaned, matches=list(counts.items()), accept=not residual)
```

**Decision: hardcode patterns + YAML for internal domains.** Hardcoded patterns are stable, well-tested, version-controlled. Internal domains change per deployment site (Baidu vs other), so a YAML config (`skills/adapt/knowledge_base/redact_domains.yml`) lets ops customize without touching code. Phase 1 ships the YAML with one example entry (commented out).

**Order rationale:** longer GitHub PAT prefixes (`github_pat_`) before older `ghp_` so the older shorter pattern doesn't capture a substring of the newer; `bearer_header` after specific tokens so we don't double-redact.

---

## 6. `_validate_loop_evidence()` insertion (final)

`skills/adapt/scripts/validate_phase_completion.py`. Add at the end of `validate_phase_output` (before the `return` paths in each branch is wrong — easier: add as the final call regardless of phase). Inert when `loop_engineering` flag absent.

```python
def _validate_loop_evidence(data: dict[str, Any]) -> None:
    """Phase 1 lays this hook inert. Real checks land in Phase 3.

    When loop_engineering: true is set, this is where future checks for
    PR-merged status, validator-binary hash, log-mtime, attempts.jsonl
    presence, etc. will live (per VAL-04, REQ-LOG-01)."""
    if data.get("loop_engineering") is not True:
        return  # legacy output: skip silently
    # Phase 3 will populate the body. Phase 1 just asserts the optional
    # `loop:` block, if present, parses cleanly through Pydantic.
    loop_block = data.get("loop")
    if loop_block is not None:
        from skills.adapt.lib.schema import LoopBlockOutput
        LoopBlockOutput.model_validate(loop_block)  # raises ValidationError on bad shape

def validate_phase_output(run_dir: Path, phase: int) -> None:
    data = _load_phase_output(run_dir, phase)
    _expect(data.get("status") == "passed", "phase status must be passed")
    _validate_step_gate(data)
    # ... existing per-phase checks (lines 71-114) UNCHANGED ...
    _validate_loop_evidence(data)  # NEW — final call, inert by default
```

**COMPAT-03 test fixture:** drop the existing `phase1_output.yml` from a real legacy run into `tests/lib/fixtures/legacy_phase1_output.yml`, run `validate_phase_output(...)`, expect zero errors. The new function is a no-op for that fixture.

**Why call at the end:** legacy data path is fully exercised first (all existing `_expect` calls). Only if the existing checks pass does the optional new check run. Reverse order would reject legacy outputs that don't have `loop_engineering` — bug we're avoiding.

---

## 7. Append-only `attempts.jsonl` (final)

`skills/adapt/lib/jsonl.py`:

```python
import json, os
from pathlib import Path
from typing import Any

def append_attempt(path: str | Path, record: dict[str, Any]) -> None:
    """Atomically append one JSON line. Refuses to write if file is being
    truncated (race with another process)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)

def assert_append_only(path: str | Path, expected_min_lines: int) -> None:
    """Test helper: assert file has at least N lines and last byte is newline."""
    p = Path(path)
    if not p.exists():
        raise AssertionError(f"{p} does not exist")
    data = p.read_bytes()
    if expected_min_lines > 0 and not data.endswith(b"\n"):
        raise AssertionError(f"{p} does not end with newline (partial write?)")
    n_lines = data.count(b"\n")
    if n_lines < expected_min_lines:
        raise AssertionError(f"{p} has {n_lines} lines, expected ≥ {expected_min_lines}")
```

**Decision:** runtime guard via `O_APPEND`-only open + `fsync`. No `flock` in Phase 1 — the design is single-writer per run (sequential controller), so file-level locking would only mask design bugs. Test-only invariant `assert_append_only` covers the "no truncation" check.

**Risk surfaced:** if Python crashes between `os.write` and the OS scheduler flushing, you can get a partial line. `fsync` after `write` minimizes this. Acceptable for v1.

---

## 8. `/loop` lint (final)

`skills/adapt/tests/lib/test_loop_lint.py`:

```python
import pathlib
import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]  # …/loongforge-plugin
SCAN_DIRS = [
    REPO_ROOT / "skills" / "adapt" / "scripts",
    REPO_ROOT / "skills" / "adapt" / "lib",
    REPO_ROOT / "agents",
]
ALLOWED_FILES = {
    REPO_ROOT / "skills" / "adapt" / "SKILL.md",     # describes /loop boundary
    # references/* explicitly allowed via dir filter, not file allowlist
}

# Patterns that constitute "invoking /loop" — bare token at line start or
# after backtick / quote / parenthesis. Excludes prose mentions like "the loop"
# or "the /loop boundary".
import re
INVOKE_PATTERNS = (
    re.compile(r"\b/loop\b\s+\S"),                     # /loop <args>
    re.compile(r"SlashCommand\s*\(\s*['\"]/loop"),     # programmatic invoke
    re.compile(r"loop_command\s*=\s*['\"]/loop"),
)

def _scan_file(p: pathlib.Path) -> list[tuple[int, str]]:
    if p.is_dir() or p.suffix not in {".py", ".md", ".sh"}:
        return []
    if "references" in p.parts:
        return []  # references/* allowed to mention /loop freely
    out = []
    for i, line in enumerate(p.read_text().splitlines(), start=1):
        for pat in INVOKE_PATTERNS:
            if pat.search(line):
                out.append((i, line.strip()))
    return out

def test_no_loop_invocation_in_skill_code():
    """SAFE-02: /loop must not appear as an invocation in skill code paths."""
    hits = []
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
```

**Decision:** pytest-only check, no pre-commit hook in Phase 1. Tests run in CI; that's enough enforcement. Pre-commit hook is a Phase 5 polish if desired.

---

## 9. Validator-protected-paths (final)

`skills/adapt/lib/protected_paths.py`:

```python
"""Paths the loop's PR helper (Phase 2) must never include in a fix-PR diff.
A PR touching any of these is auto-rejected and converted to human_needed
escalation (Pitfall 16, REQ-PR-06)."""
from __future__ import annotations
import fnmatch

PROTECTED_PATHS: tuple[str, ...] = (
    # Phase validators (the "checker" side of maker-checker)
    "skills/adapt/references/phases/*/verify.md",
    "skills/adapt/references/phases/*/loss_diff.md",
    "skills/adapt/references/phases/*/feature_compat.md",
    "skills/adapt/references/phases/*/kb_consistency.md",
    # Phase gate enforcement
    "skills/adapt/scripts/validate_phase_completion.py",
    "bin/loongforge-phase-gate",
    # Loop engineering safety primitives
    "skills/adapt/lib/redact.py",
    "skills/adapt/lib/protected_paths.py",
    "skills/adapt/lib/preflight.py",
    # Validator scripts inside each phase (Phase 1-4 verify scripts)
    "skills/adapt/scripts/perf_review.py",   # Phase 4 perf gate
    "skills/adapt/scripts/hf_forward.py",    # Phase 1 forward verify
)

def is_protected(repo_relative_path: str) -> bool:
    """Return True if a PR touching `repo_relative_path` should be auto-rejected.
    Path is interpreted relative to the loongforge-plugin repo root, NOT to
    the external LoongForge / Loong-Megatron repos. (Those repos' validators
    are out of scope for this protection — they aren't validators we wrote.)"""
    return any(fnmatch.fnmatch(repo_relative_path, pat) for pat in PROTECTED_PATHS)
```

**Phase 2 import:** `from skills.adapt.lib.protected_paths import PROTECTED_PATHS, is_protected`. Phase 1 ships the data module with a unit test that the list is non-empty and `is_protected("README.md") is False`.

---

## 10. GhClient interface (final)

`skills/adapt/lib/gh_client.py`:

```python
from __future__ import annotations
import subprocess
from dataclasses import dataclass, field
from typing import Protocol, Optional

@dataclass(frozen=True)
class GhResult:
    """Minimal result shape from a gh-CLI call."""
    returncode: int
    stdout: str
    stderr: str

class GhClient(Protocol):
    """Adapter shielding the rest of the skill from `gh` CLI syntax.
    Phase 1: only auth/perm/branch-protection methods are implemented.
    Phase 2: PR/issue lifecycle methods filled in."""
    # --- Read-only / preflight (Phase 1 fully implements) ---
    def auth_status(self) -> GhResult: ...
    def repo_view(self, owner_repo: str) -> GhResult: ...
    def repo_permissions(self, owner_repo: str) -> dict: ...
    def branch_protection(self, owner_repo: str, branch: str) -> dict: ...

    # --- PR / issue lifecycle (Phase 1 declares; Phase 2 implements) ---
    def create_branch(self, owner_repo: str, branch: str, base: str) -> GhResult: ...
    def open_pr(self, owner_repo: str, head: str, base: str, title: str, body: str,
                labels: list[str], draft: bool = True) -> GhResult: ...
    def merge_pr(self, owner_repo: str, number: int, method: str = "squash") -> GhResult: ...
    def open_issue(self, owner_repo: str, title: str, body: str, labels: list[str]) -> GhResult: ...
    def close_issue(self, owner_repo: str, number: int, comment: Optional[str] = None) -> GhResult: ...
    def find_by_idempotency_key(self, owner_repo: str, kind: str, key: str) -> Optional[int]: ...

class RealGhClient:
    """Phase 1 only implements the preflight subset. PR/issue methods raise."""
    def _run(self, args: list[str]) -> GhResult:
        cp = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
        return GhResult(cp.returncode, cp.stdout, cp.stderr)

    def auth_status(self) -> GhResult:
        return self._run(["auth", "status", "--hostname", "github.com"])

    def repo_view(self, owner_repo: str) -> GhResult:
        return self._run(["api", f"repos/{owner_repo}"])

    def repo_permissions(self, owner_repo: str) -> dict:
        import json
        r = self._run(["api", f"repos/{owner_repo}", "--jq", ".permissions"])
        if r.returncode != 0:
            return {}
        try:
            return json.loads(r.stdout)
        except json.JSONDecodeError:
            return {}

    def branch_protection(self, owner_repo: str, branch: str) -> dict:
        import json
        r = self._run(["api", f"repos/{owner_repo}/branches/{branch}/protection"])
        if r.returncode != 0:
            return {}  # 404 == unprotected, which is fine
        try:
            return json.loads(r.stdout)
        except json.JSONDecodeError:
            return {}

    def create_branch(self, *a, **k):    raise NotImplementedError("Phase 2")
    def open_pr(self, *a, **k):          raise NotImplementedError("Phase 2")
    def merge_pr(self, *a, **k):         raise NotImplementedError("Phase 2")
    def open_issue(self, *a, **k):       raise NotImplementedError("Phase 2")
    def close_issue(self, *a, **k):      raise NotImplementedError("Phase 2")
    def find_by_idempotency_key(self, *a, **k): raise NotImplementedError("Phase 2")

@dataclass
class FakeGhCall:
    method: str
    args: tuple
    kwargs: dict

@dataclass
class FakeGhClient:
    """In-memory GhClient for tests / dry-run.
    Records every call. Returns ok-shaped responses unless preset to fail."""
    calls: list[FakeGhCall] = field(default_factory=list)
    auth_ok: bool = True
    repo_perms: dict = field(default_factory=lambda: {"pull": True, "push": True, "admin": False})
    protection: dict = field(default_factory=dict)  # empty == unprotected

    def _record(self, method: str, *args, **kwargs):
        self.calls.append(FakeGhCall(method, args, kwargs))

    def auth_status(self) -> GhResult:
        self._record("auth_status")
        return GhResult(0 if self.auth_ok else 1, "", "")

    def repo_view(self, owner_repo: str) -> GhResult:
        self._record("repo_view", owner_repo)
        return GhResult(0, '{"name":"' + owner_repo + '"}', "")

    def repo_permissions(self, owner_repo: str) -> dict:
        self._record("repo_permissions", owner_repo)
        return dict(self.repo_perms)

    def branch_protection(self, owner_repo: str, branch: str) -> dict:
        self._record("branch_protection", owner_repo, branch)
        return dict(self.protection)

    # PR / issue lifecycle: record only, return placeholder shapes
    def create_branch(self, *a, **k):
        self._record("create_branch", *a, **k); return GhResult(0, "", "")
    def open_pr(self, *a, **k):
        self._record("open_pr", *a, **k); return GhResult(0, "https://example/pr/1", "")
    def merge_pr(self, *a, **k):
        self._record("merge_pr", *a, **k); return GhResult(0, "merged", "")
    def open_issue(self, *a, **k):
        self._record("open_issue", *a, **k); return GhResult(0, "https://example/issue/1", "")
    def close_issue(self, *a, **k):
        self._record("close_issue", *a, **k); return GhResult(0, "", "")
    def find_by_idempotency_key(self, *a, **k):
        self._record("find_by_idempotency_key", *a, **k); return None
```

**Decision:** `Protocol` (PEP 544) over `ABC`. Protocol gives structural typing without forcing inheritance, which is friendlier for `FakeGhClient` and any future SDK swap (PyGithub etc.). Phase 2 will fully implement `RealGhClient`'s PR/issue methods; Phase 1 just defines the contract and stubs them so `mypy --strict` / pytest don't complain about missing attributes.

---

## 11. Test layout (final)

All under `skills/adapt/tests/lib/`. Each maps to one or two REQ-IDs.

| Test file | REQ | Approach |
|-----------|-----|----------|
| `test_schema.py` | TEST-03, COMPAT-02 | Inline YAML strings: legacy v1 dict and v2 dict. Both must pass `RunInputs.model_validate()`. Round-trip: `dict → RunInputs → model_dump() → yaml.dump → yaml.load → RunInputs` must equal original. |
| `test_redact.py` | TEST-02, SAFE-01 | Snapshot tests. A frozen "secrets corpus" (small literal Python `dict`) with each pattern; assert `redact()` produces expected `cleaned` and `accept=True`. One adversarial case where the pattern is repeated post-redaction → `accept=False`. |
| `test_jsonl_append_only.py` | LOG-03 | Write 3 records via `append_attempt`, assert file ends with `\n`, assert `assert_append_only(path, 3)` passes. Manually truncate file in test → assert next call still appends (O_APPEND), assert helper raises on partial line. |
| `test_loop_lint.py` | SAFE-02 | The `_scan_file` test from §8. Initially passes (no `/loop` in code). |
| `test_preflight_dry_run.py` | INPUT-03, INPUT-04 | Use `FakeGhClient`; with `dry_run=True`, assert no `repo_permissions` call recorded. With `dry_run=False` and `auth_ok=False`, assert `PreflightResult.ok==False` and `failures` contains "gh_auth_status". |
| `test_validate_loop_evidence.py` | COMPAT-03 | Two fixture YAMLs: legacy phase1 output (no `loop_engineering` flag) → call passes; v2 phase1 output with malformed `loop:` block + `loop_engineering: true` → call raises `pydantic.ValidationError`. |
| `test_run_cli.py` | INPUT-01, INPUT-02, COMPAT-02 | Subprocess-invoke `python -m skills.adapt.scripts.run` with (a) only positional `hf_path` (legacy) — assert `run_inputs.yml` lacks `repos`/`loop`; (b) all 4 URL flags + `--dry-run` — assert `run_inputs.yml` has both blocks with correct values. |
| `test_protected_paths.py` | PR-06 (placeholder) | `is_protected("skills/adapt/scripts/validate_phase_completion.py")` True; `is_protected("README.md")` False; non-empty list. |

**pytest version:** existing `__pycache__` filenames suggest pytest 9.0.2. Pin in `setup.cfg`/`pyproject.toml` if not already.

**Fixture data location:** for the 1-2 cases that are larger than 5 lines, drop YAMLs into `tests/lib/fixtures/`. Most tests use inline strings.

---

## 12. Risk register for Phase 1

Mapped from PITFALLS.md to specific Phase-1 mitigations.

| Pitfall | Severity | Phase-1 mitigation | Mitigation lives in |
|---------|----------|--------------------|---------------------|
| **#1 Fake "passed" exit** | P0 | `_validate_loop_evidence()` hook lays the inert shell + Pydantic validation of `loop:` block shape. Real integrity checks (binary hash, log mtime) land in Phase 3. | `validate_phase_completion.py` extension |
| **#2 Loop runaway** | P0 | `LoopBudget` Pydantic model with hard `Field(le=...)` ceilings (`max_attempts_per_phase ≤ 50`, `max_attempts_per_run ≤ 500`, `max_wallclock_minutes ≤ 10080`). Schema rejects YAML that exceeds these, even before the controller runs. | `lib/schema.py` |
| **#5 State drift local↔remote** | P1 | (Deferred — no remote calls in Phase 1.) Phase 1 ensures `attempts.jsonl` schema is fixed shape so Phase 2/4's reconciler has structured data to work with. | `lib/jsonl.py`, `lib/schema.LoopBlockOutput` |
| **#6 Idempotency on resume** | P1 | (Deferred — no PR/issue creation in Phase 1.) Phase 1 reserves the idempotency-key concept as a column in `attempts.jsonl` records (the `event_id` field). | Schema documents the field; Phase 2 fills it |
| **#7 GH rate limits / auth scope / branch protection** | P1/P0 | Preflight does all three at startup. Branch-protection JSON is dumped into preflight result for record. | `lib/preflight.py` |
| **#9 Secrets in PR/issue bodies** | P0 | `redact()` ships in Phase 1 with snapshot tests. `accept=False` on residual hits = caller refuses to post. Phase 2's `gh_client.open_pr/open_issue` MUST call `redact()` first (we'll enforce in Phase 2 plan). | `lib/redact.py` |
| **#16 Maker == checker on validator** | P0 | `protected_paths.PROTECTED_PATHS` data module ships in Phase 1 with the canonical list. Phase 2's PR helper imports + enforces. | `lib/protected_paths.py` |
| **#18 `/loop` regression** | P2 | `test_loop_lint.py` ships in Phase 1, runs in CI from day one. | `tests/lib/test_loop_lint.py` |

**Phase-1-specific risks NOT covered above:**

- **R1: Backward-compat silent break.** A user with an old `run_inputs.yml` that has unrelated extra keys (e.g., a custom field someone added locally) suddenly hits `extra="forbid"` and fails. **Mitigation:** the existing tracked schema in `run.py:_build_run_inputs` (lines 47-67) only emits `source/paths/options`, all of which are in our model. Real-world drift is unlikely. If it happens, swap to `extra="ignore"` on `RunInputs` only — leaves sub-blocks strict.
- **R2: Pydantic v2 not installed in the dev env.** Existing repo has no pydantic dep declared. **Mitigation:** add `pydantic>=2.9` to `requirements.txt` (or `setup.cfg`) in this phase. Also test that `tests/test_plugin_layout.py` still passes (it does layout-only checks per filename).
- **R3: `gh` CLI absent on dev machine.** Preflight will fail. **Mitigation:** preflight wraps `subprocess.run` with `FileNotFoundError` handler emitting a clear "gh CLI not installed" message; `--dry-run` still works (uses `FakeGhClient`).
- **R4: `--dry-run` inadvertently allowed in resume.** Resume should NOT need preflight (run already ran once). **Mitigation:** in `main()`, only call `run_preflight` from the init path, never from `--resume`. Test covers this.

---

## 13. Deferred to Phase 2 (explicit list)

- Real implementation of `GhClient.create_branch / open_pr / merge_pr / open_issue / close_issue / find_by_idempotency_key`.
- Idempotency-key search-before-create logic (the `find_by_idempotency_key` body).
- Enforcement of `protected_paths.is_protected()` inside `open_pr` (auto-reject + escalation).
- `redact()` integration into `open_pr` / `open_issue` bodies.
- Force-push detection (PR-05) and `/agent-resume` comment posting.
- Issue dedup logic (ISSUE-03).

These are listed here so the Phase 2 planner can budget them precisely.

---

## Open questions for planner

1. **Sub-package naming:** `skills.adapt.lib` vs `loongforge_plugin.adapt.lib`? Existing repo uses no top-level package; `skills.adapt.scripts.run` is invoked via `bin/loongforge-adapt` which `cd`s into the repo root. Decision: stick with `skills.adapt.lib` (relative to repo root, no setup.py needed). Mark as decided unless the planner sees a reason to add `setup.py`.

2. **Where does `redact_domains.yml` live:** `skills/adapt/knowledge_base/` per existing layout, or `skills/adapt/lib/`? Recommend `knowledge_base/redact_domains.yml` (it's data/config, not code).

3. **Linting/typing:** the repo has no mypy/ruff config visible. Should Phase 1 add minimal `pyproject.toml` for ruff + mypy? **Recommend no** — keep Phase 1 focused; defer to a later polish.

4. **Test subprocess invocation:** `python -m skills.adapt.scripts.run` requires `__init__.py` files all the way down. Do we add them? **Recommend yes** in Phase 1 — tiny change, big payoff for test infrastructure.

---

## RESEARCH COMPLETE — 5-bullet executive summary

1. **All new code lives under `skills/adapt/lib/`** (new package): 7 modules + matching tests. Total ~1,100 LOC + ~410 LOC tests.
2. **Pydantic v2 schema in `lib/schema.py`** uses `Optional[ReposBlock]` + `Optional[LoopBudget]` so legacy v1 `run_inputs.yml` deserializes unchanged. `extra="forbid"` everywhere catches typos. Hard `Field(le=...)` ceilings on `LoopBudget` defang Pitfall #2 at parse time.
3. **CLI uses 8 explicit flags** (`--hf-impl-url/-ref/-subpath`, `--hf-ckpt-url/-revision`, `--loongforge-repo/-base-ref`, `--megatron-repo/-base-ref`) + `--dry-run`. Legacy positional `hf_path` continues to work alone. URL flags are all-or-nothing (validated post-parse).
4. **`GhClient` is a `typing.Protocol`** with `RealGhClient` (Phase 1: preflight subset only; Phase 2: PR/issue lifecycle) and `FakeGhClient` (records calls, parameterizable failure modes). This is the substrate for INPUT-04 + ACC-01 (Phase 5 local-acceptance gate).
5. **`_validate_loop_evidence()` ships inert** — final call in `validate_phase_output`, no-op when `loop_engineering` flag absent. COMPAT-03 covered; Phase 3 fills the body. Same pattern for the `protected_paths.py` data module: ships now with full canonical list, Phase 2 imports + enforces.
