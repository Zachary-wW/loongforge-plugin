# Phase 02: GitHub Helpers -- PR & Issue Lifecycle - Research

**Researched:** 2026-06-22
**Domain:** GitHub PR/issue lifecycle via `gh` CLI adapter with idempotency, policy guards, and simulated state
**Confidence:** HIGH

## Summary

Phase 2 fills in the six lifecycle methods declared on `GhClient` Protocol in Phase 1 (currently `NotImplementedError` stubs in `RealGhClient` and placeholder returns in `FakeGhClient`). Each method wraps a specific `gh` CLI subcommand (`gh pr create`, `gh pr merge --squash`, `gh issue create`, `gh issue close`, `gh pr comment`/`gh issue comment`, `gh pr list --search`/`gh issue list --search`). The key engineering challenges are: (1) idempotency via SHA256 footer + search-before-create, (2) policy guards that run BEFORE side-effects (protected-path diff scan, force-push detection), (3) issue dedup by `(phase, validator_name, failure_signature)` triple, and (4) evolving `FakeGhClient` from a simple call-recorder to a simulated GitHub state machine so that tests can exercise `find_by_idempotency_key`, merge transitions, and dedup without live `gh` calls.

**Primary recommendation:** Implement `RealGhClient` methods as thin wrappers around `_run()` with pre-flight policy checks (redaction, protected-path scan, human-commit detection) baked into `open_pr` and `create_branch`. Evolve `FakeGhClient` into an in-memory PR/issue store (dict-of-records) so that `find_by_idempotency_key`, dedup, and merge-state transitions are testable without mocking.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** When a branch contains non-bot commits (detected via `git log --format=%ae`), the loop enters a `paused` state and posts an `/agent-resume` comment on the PR. The run is NOT marked as failed -- human responds (e.g., via `--resume`) and the controller continues the same loop iteration. This requires the controller (Phase 3) to support a `paused` exit reason, but preserves run continuity and avoids unnecessary run restarts.
- **D-02:** Same `(phase, validator_name, failure_signature)` reuses the open issue by appending a comment (containing new attempt number, log excerpt, timestamp) rather than opening a duplicate. This keeps one issue per bug across all attempts, making it easy for reviewers to see the full history in one place. The issue is only closed when its fix-PR merges (via `Fixes #N`).
- **D-03:** Protected-path scanning happens BEFORE `open_pr` -- the diff is checked for files matching `skills/adapt/lib/protected_paths.py` patterns. If any match is found, the PR is NOT created and the loop transitions to `human_needed` escalation. This keeps the repository clean (no invalid PRs left behind). The scan uses `git diff --name-only` against the base branch before calling `gh pr create`.
- **D-04:** Template format left to Claude discretion -- researcher surveys common bot PR/issue patterns (dependabot, renovate), planner designs concrete templates. Key constraints already locked in REQUIREMENTS:
  - PR title must contain `run_id`, `phase`, `attempt`, validator name
  - PR body must include hidden `<!-- adapt-skill: ... -->` idempotency footer (SHA256 of run_id+phase+attempt+action_kind per RESUME-03)
  - Every fix-PR must carry `Fixes #N` linkage (ISSUE-02)
  - Labels: `loongforge-adapt`, `run-<id>`, `phase-<N>` (ISSUE-04)
  - Branch naming: `adapt/<run_id>/phase<N>/attempt<K>` (PR-04)
  - Issue must contain structured `failure_signature: {kind, location, expected, actual}`, log excerpt, `attempts.jsonl` link, reproduction command (ISSUE-01)
  - Merge uses `gh pr merge --squash` (PR-02)

### Claude's Discretion
- Exact PR title template string (subject to constraints above)
- Exact PR body template structure (sections, formatting)
- Exact issue body template structure
- Label color schemes
- Comment templates for dedup append, `/agent-resume`, and run-completion summary
- Diff scanning implementation detail (git diff vs gh api)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PR-01 | All adapt code changes land via `gh pr create`; direct push to default branch is forbidden | `open_pr` + `create_branch` methods; `RealGhClient` refuses `create_branch` with `base == default` and no branch name |
| PR-02 | Base PR must be merged before any validator runs; merge uses `gh pr merge --squash` | `merge_pr(owner_repo, number, method="squash")` wraps `gh pr merge --squash -R <repo>`; returns merged SHA |
| PR-03 | PR title/body/labels follow templated format with `run_id`, `phase`, `attempt`, validator name, and hidden idempotency footer | Template patterns from dependabot/renovate; SHA256 footer computation; `<!-- adapt-skill: run=... phase=... attempt=... key=sha256hex -->` |
| PR-04 | Branch naming: `adapt/<run_id>/phase<N>/attempt<K>` on both external repos | `create_branch` constructs branch name; validated by regex `^adapt/[a-zA-Z0-9_-]+/phase[0-9]+/attempt[0-9]+$` |
| PR-05 | Force-push to a branch containing non-bot commits is forbidden; on detected human commit, loop pauses and posts `/agent-resume` comment | D-01 locked decision; detect via `git log --format=%ae` checking if all emails match bot identity; `open_pr` runs this check before creation |
| PR-06 | Validator-path edits auto-rejected and converted to `human_needed` escalation | D-03 locked decision; `open_pr` calls `protected_paths.is_protected()` after `git diff --name-only` scan before `gh pr create` |
| ISSUE-01 | On validator failure, open `gh issue` containing structured `failure_signature`, log excerpt, `attempts.jsonl` link, reproduction command | `open_issue` method; body template with structured fields |
| ISSUE-02 | Every issue closed by a fix-PR carrying `Fixes #N`; merge auto-closes | `open_pr` for fix-PRs appends `Fixes #N` to body; GitHub auto-close on merge |
| ISSUE-03 | Issue dedup: same `(phase, validator_name, failure_signature)` reuses the open issue, appends comment | D-02 locked decision; `open_issue` searches for existing open issue with matching signature; if found, calls `gh issue comment` instead |
| ISSUE-04 | All bot PRs/issues carry labels `loongforge-adapt`, `run-<id>`, `phase-<N>`; end-to-end works against `FakeGhClient` in pytest | Labels applied via `--label` flag on `gh pr create`/`gh issue create`; `FakeGhClient` simulates label attachment and full lifecycle |
| RESUME-03 | Idempotency keys (`sha256(run_id+phase+attempt+action_kind)`) prevent duplicate PR/issue creation across crash-resume | `find_by_idempotency_key` searches via `gh pr list --search` / `gh issue list --search` for the footer text; returns existing artifact number |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `gh` CLI | 2.87.3 | All GitHub API operations (PR, issue, branch, merge, comment, search) | Project constraint: tech stack is `gh` CLI + Python + Bash; no `requests`, no PyGithub as primary |
| pydantic | 2.12.5 | Schema validation for `PrBlockOutput`, `IssuesBlockOutput`, structured `failure_signature` | Phase 1 established; extra='ignore' for forward-compat |
| pytest | 9.0.2 | Test framework for all lifecycle methods via `FakeGhClient` | Phase 1 established; all 103 tests green |
| Python stdlib hashlib | 3.12 | SHA256 idempotency key computation | stdlib; no external dep needed |
| Python stdlib subprocess | 3.12 | `_run()` wrapper for `gh` CLI calls | Phase 1 established in `RealGhClient._run()` |
| Python stdlib json | 3.12 | Parsing `gh api` / `--json` output | Phase 1 established |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tenacity | 9.1.2 | Retry with backoff for transient `gh` 502/503 errors | Wrap `_run()` calls in `RealGhClient` for network-retry only; NEVER retry validator failures |
| fnmatch | stdlib | Glob matching for protected-path scanning | Already used in `protected_paths.is_protected()` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `gh pr list --search` for idempotency lookup | `gh api graphql` for bulk search | GraphQL is more powerful but adds query complexity; `--search` with the SHA256 hex string is precise and simple for single-key lookups |
| `git diff --name-only` for protected-path scanning | `gh api repos/:o/:r/pulls/:n/files` | `gh api` requires PR to already exist (chicken-and-egg); `git diff` runs locally before PR creation, which matches D-03 timing requirement |
| In-memory FakeGhClient store | Mock subprocess calls | Mock subprocess is fragile (tight coupling to `gh` flag ordering); FakeGhClient with its own state machine is testable at higher abstraction |

**Installation:**
No new packages needed. All dependencies installed from Phase 1.

**Version verification (confirmed 2026-06-22):**
```
gh version 2.87.3
pydantic 2.12.5
tenacity 9.1.2
pytest 9.0.2
python 3.12.9
```

## Architecture Patterns

### Recommended Project Structure
```
skills/adapt/lib/
  gh_client.py       # GhClient Protocol + RealGhClient (lifecycle impl) + FakeGhClient (state machine)
  redact.py           # Unchanged from Phase 1 -- called by open_pr/open_issue
  protected_paths.py  # Unchanged from Phase 1 -- called by open_pr pre-check
  schema.py           # Unchanged from Phase 1 -- PrBlockOutput/IssuesBlockOutput written by callers
  jsonl.py            # Unchanged from Phase 1 -- append_attempt called by controller
  preflight.py        # Unchanged from Phase 1 -- already passed by the time lifecycle methods run
  idempotency.py      # NEW -- SHA256 key computation + footer formatting + parsing
  templates.py        # NEW -- PR title/body template, issue body template, comment templates
skills/adapt/tests/lib/
  test_gh_client_lifecycle.py  # NEW -- all lifecycle method tests
  test_idempotency.py          # NEW -- SHA256 key + footer tests
  test_templates.py            # NEW -- template rendering tests
  test_preflight_dry_run.py    # Existing -- untouched
  test_protected_paths.py      # Existing -- untouched
  test_redact.py               # Existing -- untouched
  ...
```

### Pattern 1: GhClient Method Implementation Pattern
**What:** Every `RealGhClient` lifecycle method follows the same structure: (1) policy pre-check, (2) redaction on body, (3) `_run()` call, (4) parse result, (5) return `GhResult`.
**When to use:** Every new method added to `RealGhClient`.
**Example:**
```python
# Source: established pattern from RealGhClient.auth_status / repo_permissions
def open_pr(self, owner_repo: str, head: str, base: str, title: str,
            body: str, labels: list[str], draft: bool = True) -> GhResult:
    # 1. Policy pre-checks (protected paths, force-push, direct-push)
    # 2. Redact body
    # 3. Build and run gh command
    r = self._run([
        "pr", "create",
        "-R", owner_repo,
        "--base", base,
        "--head", head,
        "--title", title,
        "--body", body,
        "--label", ",".join(labels),
    ] + (["--draft"] if draft else []))
    return r
```

### Pattern 2: Idempotency Key as HTML Comment Footer
**What:** Every PR and issue body gets a hidden HTML comment containing `adapt-skill: run=<run_id> phase=<phase> attempt=<attempt> key=<sha256hex>`. This is both machine-parseable and invisible in rendered Markdown.
**When to use:** On every `open_pr` and `open_issue` call.
**Example:**
```python
# Source: RESUME-03 + CONTEXT.md D-04
import hashlib

def compute_idempotency_key(run_id: str, phase: int, attempt: int, action_kind: str) -> str:
    raw = f"{run_id}:{phase}:{attempt}:{action_kind}"
    return hashlib.sha256(raw.encode()).hexdigest()

def format_footer(run_id: str, phase: int, attempt: int, action_kind: str) -> str:
    key = compute_idempotency_key(run_id, phase, attempt, action_kind)
    return f"\n<!-- adapt-skill: run={run_id} phase={phase} attempt={attempt} action={action_kind} key={key} -->\n"
```

### Pattern 3: FakeGhClient In-Memory State Machine
**What:** `FakeGhClient` evolves from simple call-recording to maintaining simulated PR/issue state in dictionaries, keyed by `(owner_repo, number)`. This allows `find_by_idempotency_key` to search the simulated store, `merge_pr` to transition state, and issue dedup to check existing open issues.
**When to use:** All Phase 2 tests.
**Example:**
```python
# Source: CONTEXT.md code_context section
@dataclass
class FakePrRecord:
    number: int
    owner_repo: str
    head: str
    base: str
    title: str
    body: str
    labels: list[str]
    state: str  # "open" | "closed" | "merged"
    merged_sha: Optional[str] = None
    idempotency_key: Optional[str] = None

@dataclass
class FakeIssueRecord:
    number: int
    owner_repo: str
    title: str
    body: str
    labels: list[str]
    state: str  # "open" | "closed"
    failure_signature: Optional[str] = None
    idempotency_key: Optional[str] = None
    comments: list[str] = field(default_factory=list)
```

### Pattern 4: Issue Dedup by Failure Signature Hash
**What:** Before creating an issue, search for existing open issues with the same `(phase, validator_name, failure_signature)` triple. If found, append a comment with the new attempt info instead of creating a duplicate.
**When to use:** `open_issue` method when `failure_signature` is provided.
**Example:**
```python
# RealGhClient.open_issue dedup logic
def open_issue(self, owner_repo: str, title: str, body: str,
               labels: list[str], failure_signature: str = "") -> GhResult:
    # Search for existing open issue with same signature
    if failure_signature:
        sig_key = compute_idempotency_key(run_id, phase, attempt, f"issue-{failure_signature}")
        existing = self.find_by_idempotency_key(owner_repo, "issue", sig_key)
        if existing is not None:
            # Append comment instead of creating new issue
            return self._run([
                "issue", "comment", str(existing),
                "-R", owner_repo,
                "--body", comment_body,
            ])
    # Create new issue
    r = self._run(["issue", "create", "-R", owner_repo, "--title", title, "--body", body,
                    "--label", ",".join(labels)])
    return r
```

### Anti-Patterns to Avoid
- **Subprocess mocking:** Do not mock `subprocess.run` directly to test `gh` calls. Use `FakeGhClient` injection instead. Subprocess mocking is fragile and couples tests to exact `gh` flag ordering.
- **Retrying validator failures:** Tenacity retry is ONLY for transient `gh` CLI network errors (502, 503, timeout). Validator failure is signal, not transient. Retrying it violates P18 ("a loop without a gate is a token bonfire").
- **Free-form body without footer:** Every PR/issue body MUST include the idempotency footer. Bodies without it cannot be found by `find_by_idempotency_key`, breaking crash-resume (RESUME-03).
- **Creating PR then checking protected paths:** D-03 is explicit: check BEFORE creating. A PR that touches protected paths must never be opened -- it creates noise and requires manual cleanup.
- **Same sub-agent for Edit and Diagnose:** P16 / maker-checker separation. This phase creates the helpers that BOTH agents will use, but the helpers themselves must not embed editing logic.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Idempotency key generation | Custom UUID or timestamp-based key | SHA256(run_id:phase:attempt:action_kind) | Deterministic across crashes; same inputs always produce same key; grep-friendly |
| GitHub search for existing artifacts | Custom REST/GraphQL query builder | `gh pr list --search <key>` / `gh issue list --search <key>` | `gh` handles auth, pagination, rate-limiting; `--search` uses GitHub's native search syntax |
| PR merge strategy selection | Custom merge logic | `gh pr merge --squash` | PR-02 is explicit; squash keeps history linear; one-liner `gh` call |
| Label creation | `gh api` POST to labels endpoint | `gh label create` (if label doesn't exist) | Labels may not exist on target repos; `gh label create` is idempotent |
| Body redaction | Inline regex in each method | `redact.py: redact(text) -> RedactionResult` | Phase 1 already ships this; 10 hardcoded patterns + YAML internal domains; residual check |

**Key insight:** The `gh` CLI already handles auth, pagination, rate-limiting, and GraphQL translation. Wrapping `subprocess.run(["gh", ...])` is simpler and more maintainable than any Python HTTP client approach. The project's hard "Do Not Use" list (CLAUDE.md Part 3) explicitly forbids `requests` + raw GitHub REST.

## Common Pitfalls

### Pitfall 1: Idempotency Footer Not Searchable
**What goes wrong:** `find_by_idempotency_key` uses `gh pr list --search <key_hex>` but GitHub search does not index HTML comment content, or the search query syntax is wrong, so the search always returns nothing and duplicate PRs are created.
**Why it happens:** GitHub's search API has specific indexing rules. HTML comments in Markdown bodies may not be fully indexed. The SHA256 hex string must appear in a searchable part of the body, or the search must use the right qualifier.
**How to avoid:** Test the search query against a real PR with the footer. If HTML comments are not indexed, include the key hex in a visible machine-readable line (e.g., a code block or metadata table) alongside the HTML comment. The `--search` flag on `gh pr list` supports body search; verify with `gh pr list --search "adapt-skill key=abc123" -R <repo>`.
**Warning signs:** `find_by_idempotency_key` always returns `None`; duplicate PRs with same idempotency key appear on resume.

### Pitfall 2: Race Between `git diff` and `gh pr create`
**What goes wrong:** The protected-path scan (`git diff --name-only`) runs against the local branch, but the actual pushed branch has different content (e.g., someone force-pushed between the scan and the PR creation).
**Why it happens:** The scan and the push are not atomic. In a single-run, single-laptop-open environment this is unlikely, but worth documenting.
**How to avoid:** Accept this as a known minor gap for the single-laptop-open assumption (P21). The Phase 3 controller runs sequentially. Document that the scan is a best-effort pre-check; the ultimate protection is that reviewers (human or diagnose-agent) also check the diff.
**Warning signs:** PR created despite protected-path scan passing; diff shows validator file changes that weren't in local `git diff`.

### Pitfall 3: `gh pr create` Interactive Prompt Blocks Automation
**What goes wrong:** `gh pr create` without `--title` and `--body` enters interactive mode, waiting for user input, which hangs the subprocess.
**Why it happens:** `gh` CLI defaults to interactive prompts when required flags are missing. A missing `--title` or `--body` will hang `subprocess.run` indefinitely.
**How to avoid:** Always pass `--title`, `--body`, and `--head`/`--base` explicitly. Never rely on `gh` interactive prompts. The `RealGhClient.open_pr` signature already requires all these parameters.
**Warning signs:** `_run()` call never returns; subprocess hangs.

### Pitfall 4: Label Does Not Exist on Target Repo
**What goes wrong:** `gh pr create --label loongforge-adapt` fails with 422 if the label `loongforge-adapt` does not exist on the target repository.
**Why it happens:** GitHub requires labels to exist before they can be applied to PRs/issues. `gh pr create --label` does NOT auto-create labels.
**How to avoid:** Before the first PR/issue creation in a run, call `gh label create <name> --color <hex> -R <repo>` for each required label. This command is idempotent (returns error if label exists, which is fine). Alternatively, check `gh label list -R <repo>` first.
**Warning signs:** `open_pr` or `open_issue` returns returncode != 0 with stderr mentioning "Label does not exist" or "Validation Failed".

### Pitfall 5: `Fixes #N` Linkage Requires Exact Syntax
**What goes wrong:** Fix-PR body contains "fixes #N" (lowercase) or "Fixes N" (no `#`), and GitHub does not auto-close the issue on merge.
**Why it happens:** GitHub recognizes only specific keywords in specific casing: `Fixes #N`, `Closes #N`, `Resolves #N`, `Fixes org/repo#N`.
**How to avoid:** Template must use exactly `Fixes #N` in the PR body. Test this in `FakeGhClient` by checking that the body contains the correct pattern. In `RealGhClient`, the template enforces this.
**Warning signs:** Issue remains open after fix-PR merge; manual close required.

### Pitfall 6: `gh pr merge --squash` Returns Non-Zero on Merge Conflict
**What goes wrong:** `merge_pr` is called on a PR that has merge conflicts; `gh pr merge --squash` returns non-zero, and the caller interprets this as a code failure rather than a merge-blocking state.
**Why it happens:** Merge conflicts are a normal operational state, not a code error. The controller (Phase 3) needs to distinguish "merge conflict" from "merge unauthorized" from "PR not ready."
**How to avoid:** Parse `GhResult.stderr` for conflict indicators. Return a structured error that the Phase 3 controller can classify. For now, `merge_pr` returns the raw `GhResult`; the controller interprets it.
**Warning signs:** `merge_pr` returncode != 0 on a PR that should be mergeable.

### Pitfall 7: Force-Push Detection False Positives
**What goes wrong:** `git log --format=%ae` detects human commits on a branch that only has bot commits, because the bot's email is different from the expected pattern.
**Why it happens:** The "bot identity" email must be known. `gh` CLI operations use the authenticated user's email, which may not match a hardcoded "bot email" pattern.
**How to avoid:** Use `gh api user --jq .email` to get the bot user's email at preflight time. Compare branch commit emails against this known bot email. D-01 says "non-bot commits" -- the definition of "bot" is "the authenticated `gh` user."
**Warning signs:** Every branch is flagged as having human commits; loop always pauses.

## Code Examples

Verified patterns from `gh` CLI help output (2026-06-22):

### Create Branch
```python
# gh gitbranch create is not a direct command; use gh api or git push
# Option 1: Use gh api to create branch via API
r = self._run(["api", f"repos/{owner_repo}/git/refs",
               "-f", f"ref=refs/heads/{branch}",
               "-f", f"sha={base_sha}"])
# Option 2: Simpler -- just use the branch name in --head when creating the PR
# (gh pr create will push the branch automatically if it doesn't exist remotely)
# DECISION: Use gh api for explicit branch creation (required for pre-PR branch setup)
```

### Open PR
```python
# Source: gh pr create --help (verified 2026-06-22)
r = self._run([
    "pr", "create",
    "-R", owner_repo,
    "--base", base,
    "--head", head,
    "--title", title,
    "--body", body_with_footer,
    "--label", ",".join(labels),
] + (["--draft"] if draft else []))
# r.stdout contains the PR URL: "https://github.com/<owner>/<repo>/pull/<number>"
```

### Merge PR with Squash
```python
# Source: gh pr merge --help (verified 2026-06-22)
r = self._run([
    "pr", "merge", str(number),
    "-R", owner_repo,
    "--squash",
    "--delete-branch",
])
# r.stdout contains merge confirmation; r.returncode != 0 means merge failed
```

### Open Issue
```python
# Source: gh issue create --help (verified 2026-06-22)
r = self._run([
    "issue", "create",
    "-R", owner_repo,
    "--title", title,
    "--body", body_with_footer,
    "--label", ",".join(labels),
])
# r.stdout contains issue URL: "https://github.com/<owner>/<repo>/issues/<number>"
```

### Close Issue with Comment
```python
# Source: gh issue close --help (verified 2026-06-22)
r = self._run([
    "issue", "close", str(number),
    "-R", owner_repo,
    "--comment", closing_comment,
    "--reason", "completed",
])
```

### Post Comment on PR or Issue
```python
# PR comment
r = self._run([
    "pr", "comment", str(number),
    "-R", owner_repo,
    "--body", comment_body,
])
# Issue comment
r = self._run([
    "issue", "comment", str(number),
    "-R", owner_repo,
    "--body", comment_body,
])
```

### Find by Idempotency Key
```python
# Source: gh pr list --search --help (verified 2026-06-22)
# Search for PRs containing the idempotency key in body
r = self._run([
    "pr", "list",
    "-R", owner_repo,
    "--state", "all",
    "--search", f"adapt-skill key={key_hex}",
    "--json", "number,state",
    "--limit", "5",
])
# Parse r.stdout as JSON array; return first match number or None
```

### Ensure Label Exists (Pre-PR/Issue Bootstrap)
```python
# Source: gh label create --help (verified 2026-06-22)
# Idempotent -- fails silently if label already exists
self._run(["label", "create", "loongforge-adapt",
           "--color", "0e8a16", "-R", owner_repo])
self._run(["label", "create", f"run-{run_id}",
           "--color", "bfd4f2", "-R", owner_repo])
self._run(["label", "create", f"phase-{phase}",
           "--color", "bfd4f2", "-R", owner_repo])
```

### Protected Path Pre-Check (Before open_pr)
```python
# Source: D-03 from CONTEXT.md + protected_paths.py
# This runs BEFORE the PR is created, on the local working copy
import subprocess
diff_result = subprocess.run(
    ["git", "diff", "--name-only", f"origin/{base}...{head}"],
    capture_output=True, text=True, check=False
)
changed_files = diff_result.stdout.strip().split("\n")
for f in changed_files:
    if is_protected(f):
        raise ProtectedPathError(f)  # Caller converts to human_needed
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| PyGithub as primary GitHub client | `gh` CLI + `subprocess.run` | Project constraint from CLAUDE.md | Simpler auth, no extra dep, ambient `gh auth` |
| Mock subprocess for tests | `FakeGhClient` in-memory state machine | Phase 1 design decision | Tests at higher abstraction, not coupled to `gh` flag ordering |
| UUID-based idempotency keys | SHA256(run_id:phase:attempt:action_kind) | Phase 2 requirement RESUME-03 | Deterministic across crashes; same inputs = same key |
| Open issue per failure | Dedup by (phase, validator, failure_signature) | CONTEXT.md D-02 | One issue per bug across all attempts; cleaner tracker |

**Deprecated/outdated:**
- `requests` + raw GitHub REST: Replaced by `gh` CLI wrapper per CLAUDE.md hard NO list
- PyGithub as primary: Heavier dependency, parallel auth; `gh api` is sufficient

## Open Questions

1. **GitHub search indexing of HTML comments**
   - What we know: GitHub search indexes PR/issue body text, but behavior with HTML comments is not documented
   - What's unclear: Whether `<!-- adapt-skill: key=abc123 -->` is searchable via `gh pr list --search`
   - Recommendation: Include the key in a visible machine-readable format (e.g., `[adapt-skill-key: abc123]` in a details block) as a fallback. Test against a real repo during implementation. If HTML comments are searchable, the visible fallback is redundant but harmless.

2. **Bot email identity for force-push detection**
   - What we know: `gh auth status` shows the logged-in account; `gh api user --jq .email` returns the user's public email
   - What's unclear: Whether the bot user's Git commit email matches the `gh api user` email, or if it uses a `noreply` address
   - Recommendation: At preflight time, capture `gh api user --jq '.login'` as the bot identity. For force-push detection, compare commit author logins (not emails) against this identity. `git log --format='%an'` gives author name; `git log --format='%ae'` gives email. Both should be checked.

3. **`link_pr_issue` method on GhClient Protocol**
   - What we know: The ROADMAP success criteria mention `link_pr_issue` as a method that must be exposed. The current Protocol does NOT declare it.
   - What's unclear: Whether `link_pr_issue` is a separate method or is handled implicitly by `Fixes #N` in the PR body
   - Recommendation: `Fixes #N` in the PR body automatically links and auto-closes the issue on merge. No separate `gh` command is needed for linking. Remove `link_pr_issue` from the Protocol or implement it as a no-op that verifies the `Fixes #N` pattern is present in the body.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| gh CLI | All RealGhClient methods | Yes | 2.87.3 | -- |
| gh auth (logged in) | PR/issue/branch operations | Yes | Zachary-wW | -- |
| push perm on LoongForge | create_branch, open_pr, merge_pr | Yes | admin+push | -- |
| push perm on Loong-Megatron | create_branch, open_pr, merge_pr | Yes (assumed from preflight) | admin+push (assumed) | -- |
| Python 3.12 | All code | Yes | 3.12.9 | -- |
| pydantic | schema models | Yes | 2.12.5 | -- |
| tenacity | network retry | Yes | 9.1.2 | -- |
| pytest | test framework | Yes | 9.0.2 | -- |
| pytest-mock | mock helpers | No | -- | Use stdlib unittest.mock (already used in Phase 1 tests) |
| git CLI | diff scanning, commit email detection | Yes | system | -- |

**Missing dependencies with no fallback:**
- None -- all required tools are available.

**Missing dependencies with fallback:**
- pytest-mock not installed; use `unittest.mock` (already established pattern in Phase 1 tests via `from unittest.mock import patch`).

## Sources

### Primary (HIGH confidence)
- `gh pr create --help` (2026-06-22) -- flags: `--title`, `--body`, `--base`, `--head`, `--label`, `--draft`, `-R`
- `gh pr merge --help` (2026-06-22) -- flags: `--squash`, `--delete-branch`, `-R`
- `gh issue create --help` (2026-06-22) -- flags: `--title`, `--body`, `--label`, `-R`
- `gh issue close --help` (2026-06-22) -- flags: `--comment`, `--reason`, `-R`
- `gh pr comment --help` (2026-06-22) -- flags: `--body`, `-R`
- `gh issue comment --help` (2026-06-22) -- flags: `--body`, `-R`
- `gh pr list --help` (2026-06-22) -- flags: `--search`, `--state`, `--label`, `--json`, `-R`
- `gh issue list --help` (2026-06-22) -- flags: `--search`, `--state`, `--label`, `--json`, `-R`
- `gh label --help` (2026-06-22) -- `create`, `list` subcommands
- `skills/adapt/lib/gh_client.py` -- existing Protocol + stubs (Phase 1 code)
- `skills/adapt/lib/redact.py` -- existing redactor (Phase 1 code)
- `skills/adapt/lib/protected_paths.py` -- existing protected-path patterns (Phase 1 code)
- `skills/adapt/lib/schema.py` -- existing Pydantic models (Phase 1 code)
- `.planning/REQUIREMENTS.md` -- PR-01..PR-06, ISSUE-01..ISSUE-04, RESUME-03
- `02-CONTEXT.md` -- locked decisions D-01 through D-04

### Secondary (MEDIUM confidence)
- `.planning/research/PITFALLS.md` -- Pitfalls 6 (idempotency), 7 (rate limits), 8 (force-push), 16 (maker-checker)
- `.planning/research/ARCHITECTURE.md` -- Layer D (gh_helper.py) integration points
- CONTEXT.md `code_context` section -- FakeGhClient evolution guidance

### Tertiary (LOW confidence)
- GitHub search indexing of HTML comments -- not verified by official docs; recommendation includes visible-key fallback

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all versions verified by `pip show` and `gh --version` on 2026-06-22
- Architecture: HIGH -- builds directly on Phase 1 established patterns (Protocol, _run, FakeGhClient._record, redact, protected_paths)
- Pitfalls: HIGH -- grounded in `gh` CLI help output and GitHub platform behavior
- Idempotency search behavior: MEDIUM -- HTML comment searchability not verified by official docs; fallback strategy included

**Research date:** 2026-06-22
**Valid until:** 2026-07-22 (stable: `gh` CLI, pydantic, tenacity are mature libraries)
