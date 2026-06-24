# Phase 02: GitHub Helpers — PR & Issue Lifecycle - Context

**Gathered:** 2026-06-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Implement the full PR/issue lifecycle in the `GhClient` adapter: branch creation, PR open/merge with idempotency footers and label policy, issue open/close/dedup with structured failure signatures, validator-path write-protection, and force-push detection. All via the existing `GhClient` Protocol, with `FakeGhClient` and `RealGhClient` implementations. Phase 1 shipped the Protocol declaration + 6 `NotImplementedError` stubs + placeholder `FakeGhClient` returns — this phase fills them in with real `gh` CLI calls and testable behavior.

</domain>

<decisions>
## Implementation Decisions

### Human-commit Conflict Handling
- **D-01:** When a branch contains non-bot commits (detected via `git log --format=%ae`), the loop enters a `paused` state and posts an `/agent-resume` comment on the PR. The run is NOT marked as failed — human responds (e.g., via `--resume`) and the controller continues the same loop iteration. This requires the controller (Phase 3) to support a `paused` exit reason, but preserves run continuity and avoids unnecessary run restarts.

### Issue Dedup Granularity
- **D-02:** Same `(phase, validator_name, failure_signature)` reuses the open issue by appending a comment (containing new attempt number, log excerpt, timestamp) rather than opening a duplicate. This keeps one issue per bug across all attempts, making it easy for reviewers to see the full history in one place. The issue is only closed when its fix-PR merges (via `Fixes #N`).

### Validator-path Protection Timing
- **D-03:** Protected-path scanning happens BEFORE `open_pr` — the diff is checked for files matching `skills/adapt/lib/protected_paths.py` patterns. If any match is found, the PR is NOT created and the loop transitions to `human_needed` escalation. This keeps the repository clean (no invalid PRs left behind). The scan uses `git diff --name-only` against the base branch before calling `gh pr create`.

### PR/Issue Template Format
- **D-04:** Template format left to Claude discretion — researcher surveys common bot PR/issue patterns (dependabot, renovate), planner designs concrete templates. Key constraints already locked in REQUIREMENTS:
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

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 1 Artifacts (build directly on these)
- `skills/adapt/lib/gh_client.py` — GhClient Protocol with 6 lifecycle method stubs + FakeGhClient placeholder returns
- `skills/adapt/lib/redact.py` — Secret redactor; MUST be called before any body is posted to GitHub (SAFE-01)
- `skills/adapt/lib/protected_paths.py` — Validator-protected glob patterns; used for PR-06 write-protection
- `skills/adapt/lib/schema.py` — `PrBlockOutput`, `IssuesBlockOutput` Pydantic models (extra='ignore' for forward-compat)
- `skills/adapt/lib/jsonl.py` — Append-only JSONL writer for attempts.jsonl
- `skills/adapt/lib/preflight.py` — `run_preflight()` already checks auth/permissions; Phase 2 lifecycle methods run AFTER preflight passes

### Project Requirements
- `.planning/REQUIREMENTS.md` — PR-01 through PR-06, ISSUE-01 through ISSUE-04, RESUME-03 (idempotency keys)
- `.planning/PROJECT.md` — Core value (closed loop), constraints (tech stack, security, plugin layout)
- `.planning/ROADMAP.md` — Phase 2 success criteria (5 items)

### Research Artifacts
- `.planning/research/ARCHITECTURE.md` — Integration points IP-1 through IP-10, build order B1..B13
- `.planning/research/STACK.md` — Loop-engineering principles P1..P21 (especially P8 data contracts, P11 advisory review, P12 issue granularity)
- `.planning/research/PITFALLS.md` — Pitfalls relevant to PR/issue lifecycle
- `.planning/research/FEATURES.md` — Table-stakes items mapped to loop steps

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `GhClient` Protocol: Already declares all 6 lifecycle methods with correct signatures — Phase 2 just needs to implement them in `RealGhClient` and flesh out `FakeGhClient`
- `FakeGhClient`: Already records calls and returns placeholder `GhResult(0, ...)` — needs realistic return values (PR URL with number, issue URL with number, parsed idempotency key lookups)
- `GhResult` dataclass: `returncode`, `stdout`, `stderr` — sufficient for all lifecycle methods
- `redact.py`: `redact(text) -> (cleaned_text, accepted)` — call before every `body` parameter in `open_pr` and `open_issue`
- `protected_paths.py`: `PROTECTED_PATTERNS` list + `is_protected(path)` function — use in diff scanning
- `schema.py`: `PrBlockOutput(url, number, merged_sha)`, `IssuesBlockOutput(url, number, title)` — Phase 2 code writes into these

### Established Patterns
- `_run(self, args: list[str]) -> GhResult`: `RealGhClient`'s single subprocess runner — all new methods should use this
- `FakeGhClient._record(method, *args, **kwargs)`: Recording pattern — new methods follow the same pattern
- Test structure: `skills/adapt/tests/lib/test_*.py` with `FakeGhClient` injection — all Phase 2 tests follow this

### Integration Points
- `RealGhClient.open_pr` must call `redact(body)` before passing to `gh pr create` (SAFE-01)
- `RealGhClient.open_pr` must scan diff against `protected_paths` before creating PR (PR-06)
- `RealGhClient.merge_pr` must verify base PR is merged before fix-PR validation runs (PR-02) — this is a Phase 3 concern but Phase 2 lays the `merge_pr` interface
- `FakeGhClient` needs a simulated PR/issue store (dict of number → record) so tests can verify `find_by_idempotency_key`, `merge_pr` state transitions, etc.
- `RealGhClient.find_by_idempotency_key` uses `gh pr list --search` or `gh issue list --search` with the idempotency footer text (RESUME-03)

</code_context>

<specifics>
## Specific Ideas

- `FakeGhClient` should evolve from simple call-recording to a simulated GitHub state machine: tracks created PRs/issues by number, supports `find_by_idempotency_key` against its own store, returns realistic URLs (e.g., `https://github.com/Zachary-wW/LoongForge/pull/42`)
- Idempotency key computation: `sha256(f"{run_id}:{phase}:{attempt}:{action_kind}")` embedded as HTML comment footer in PR/issue body — `find_by_idempotency_key` searches for this exact string
- Issue dedup search: `gh issue list --state open --label loongforge-adapt --search "<failure_signature_hash>"` — if found, append comment instead of creating new

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 02-github-helpers-pr-issue-lifecycle*
*Context gathered: 2026-06-22*
