# PITFALLS.md — Adapt Skill Loop-Engineering Refactor

Domain: Validator-driven external-repo PR/issue loop in a Claude Code CLI skill (HF→LoongForge model adaptation, two coupled GitHub repos)
Researched: 2026-06-22
Confidence: HIGH

---

## Critical Pitfalls (P0 / P1)

### Pitfall 1 — Fake / honest-but-wrong "validator passed" exit signal (rpcx.io/04)
**P0.** The loop's only exit is `validator.status == passed`. A phase agent under iteration pressure can either forge `passed` or "honestly believe" it without actually executing the validator (cached log, stale `phaseN_output.yml`, validator stub returning 0).
- **Warning signs:** validator timestamp older than latest attempt; `attempts.jsonl` last entry has no validator stdout/stderr blob; `passed` returned in <30s for Phase 2/3 which always need GPU.
- **Prevention:** (1) `loongforge-phase-gate` re-runs cheap validator integrity check (hash of validator binary + presence of validator stdout in `phases/phaseN/logs/`) before honoring `passed`. (2) Require `validator.evidence_uri` and reject if file mtime predates attempt id. (3) Issue/PR body includes validator log SHA — humans spot-check.
- **Phase:** Phase 1 (loop control plane) and step gate.

### Pitfall 2 — Loop runaway: no hard upper bound (rpcx.io/04, /12)
**P0.** Three multiplicative axes: attempts/phase × phases × retries. Without global budget, flaky Phase 3 loss-diff burns a monthly token budget overnight. rpcx.io/12: "Loops without a gate are token incinerators"; rpcx.io/04: "`--max-iterations` is not optional, ever."
- **Warning signs:** total `attempts.jsonl` entries > 3× expected; same validator failing with same diff three runs in a row; PR count for one run > 10.
- **Prevention:** Three-axis budget — `max_attempts_per_phase`, `max_attempts_per_run`, `max_wallclock_seconds` + per-run dollar/token cap. On breach: `autonomous_blocked`, write escalation issue, exit. Defaults conservative + configurable in `run_inputs.yml`.
- **Phase:** Phase 1 (loop FSM).

### Pitfall 3 — Validator non-determinism mistaken for code regression
**P0.** Phase 3 loss-diff and Phase 4 feature-compat use FP thresholds. CUDA non-determinism (cuBLAS, NCCL, atomic adds, varying SM occupancy), tokenizer rounding, FP16/BF16 cast order produce noise > threshold on some runs. Loop sees "real" failure, opens issue, agent "fixes" code that wasn't broken, next run passes by chance, phantom commit lands.
- **Warning signs:** validator verdict flips between adjacent reruns with no code change; failed diff within 2× threshold; failure varies with GPU type or batch size.
- **Prevention:** (1) On near-threshold failure, auto-rerun N times (e.g., 3) before opening issue; only consistent failure → Diagnose. (2) Set `CUBLAS_WORKSPACE_CONFIG=:4096:8`, `torch.use_deterministic_algorithms(True)`, fixed seed, single-GPU profile recorded in phase3 docs. (3) Issue body shows distribution (min/median/max), not single number. (4) `attempts.jsonl` distinguishes `validator.status=flaky` from `failed`.
- **Phase:** Phase 2 (validator hardening) + Phase 3 (diagnose).

### Pitfall 4 — Cross-repo PR coordination deadlock (LoongForge ↔ Loong-Megatron)
**P0.** A model adaptation may require a base PR in Loong-Megatron (new op kernel) before LoongForge-side PR can compile/validate. Skill opens both PRs in parallel; LoongForge CI fails because Megatron PR hasn't merged; loop interprets as LoongForge defect, opens issue against wrong repo. Reverse: Megatron PR merges, LoongForge PR has been rebased and now drifts.
- **Warning signs:** validator failure mentions ImportError / undefined symbol / version mismatch; the Megatron PR referenced is still open or closed-without-merge; CI passed locally but fails on runner where Megatron is at `loong-main/core_v0.15.0` head.
- **Prevention:** (1) Encode explicit DAG: every PR declares `depends_on: [other_repo#PR_NUMBER]`; merge gate refuses to merge downstream until upstream merged AND downstream rebased on new SHA. (2) Pin Megatron commit SHA in LoongForge PR body and as `LOONG_MEGATRON_SHA` env in validator run; validator must echo resolved SHA. (3) Single "merge train" — only one repo at a time. (4) On Megatron merge, auto-comment "rebase request" on every dependent LoongForge PR.
- **Phase:** Phase 2 (PR helper) + Phase 3 (merge orchestration).

### Pitfall 5 — State drift between `phaseN_output.yml` and remote PR/issue state
**P1.** Local YAML says Phase 2 `passed`, but PR was reverted on GitHub between runs. Or PR was force-pushed by reviewer, local SHA in `attempts.jsonl` no longer exists, loop happily proceeds to Phase 3. Or issue was manually closed; loop re-opens next run because local state still says "open."
- **Warning signs:** `gh pr view --json mergeCommit` returns null for PR locally marked merged; issue numbers in `attempts.jsonl` 404; PR head SHA doesn't match `phaseN_output.yml`.
- **Prevention:** (1) Every iteration begins with remote-state reconcile: fetch PR/issue state by id, compare merge SHA, rebase local YAML, write `state_drift` event. (2) Use commit SHAs, never branch names, as joining key. (3) On `--resume`, re-validate every PR/issue id against `gh`; mismatches force `--reset-phase N`.
- **Phase:** Phase 1 (state model) + Phase 4 (`--resume` hardening).

### Pitfall 6 — Idempotency on resume / rerun (duplicate issues, ghost PRs)
**P1.** `--resume` after crash mid-Diagnose creates second issue for same failure. Same for fix-PRs after transient `gh` 502: agent retries and opens PR #41 and #42 with identical diffs.
- **Warning signs:** two open issues with identical titles in run window; two PRs with same head branch SHA; `attempts.jsonl` contains same `pr_url` under two different attempt ids.
- **Prevention:** (1) Idempotency key per loop action: `sha256(run_id + phase + attempt_id + action_kind)`. Before creating issue/PR, search GitHub for existing one with that key in body (`Idempotency-Key: <hex>`); if found, attach to it. (2) `gh` calls wrapped in `create_or_get` helpers. (3) `attempts.jsonl` writes append-only with explicit `event_id`; resume reads last event and skips already-confirmed remote actions.
- **Phase:** Phase 2 (PR/issue helpers) — must be in from day 1.

### Pitfall 7 — GitHub rate limits, auth scope, and branch protection conflicts
**P0/P1.** Three failure modes:
(a) `gh` token has only `repo:public`; repos are private → first PR succeeds, merge fails 403, loop retries forever.
(b) Default REST quota (5k/hr) burned; secondary rate limit on PR creation (20/min) trips during fix-PR storm.
(c) Branch protection on `main` requires checks the skill doesn't know about (human review approval, signed commits) → merge returns "merge not allowed", which diagnoser interprets as code failure.
- **Warning signs:** 403/422 from `gh` mentioning "review required" / "status check"; HTTP 403 with `X-RateLimit-Remaining: 0`; same merge call failing identically across attempts.
- **Prevention:** (1) Pre-flight at startup: `gh auth status`, `gh api repos/:o/:r` for both repos, verify scopes include `repo` + `workflow`, dump branch protection rules and assert auto-merge can satisfy them; otherwise fail-fast with precise error. (2) Distinguish "policy reject" from "code reject" — policy must escalate to `human_needed`, never become issue. (3) Track rate-limit headers; back off at 90% consumption; cap PR/issue create rate.
- **Phase:** Phase 0 (preflight) + Phase 2 (helpers).

### Pitfall 8 — PR ping-pong, force-push during review, stale PRs
**P1.** Reviewer pushes fixup; agent's next iteration force-pushes regenerated diff, clobbering human commit. Reverse: human force-pushes a rebase; agent's local SHA gone, validator-rerun comment refers to dead commit. Stale PRs accumulate (every failure spawns new branch).
- **Warning signs:** PR `pushed_at` newer than agent's last action; `attempts.jsonl` SHA unreachable on remote; `gh pr list` shows >5 open PRs from run.
- **Prevention:** (1) Agent never force-pushes a branch with non-bot commits. Detect via `git log --format=%ae <bot_branch>..origin/<bot_branch>`. (2) On detected human commits, loop pauses and posts "human change detected, awaiting /agent-resume". (3) Auto-close superseded PRs when new fix-PR opened for same `(phase, failure_signature)`. (4) Stale-PR sweeper at end of run.
- **Phase:** Phase 3 (PR lifecycle).

### Pitfall 9 — Secrets / sensitive paths leaking into PR/issue bodies
**P0 if any repo could be public.** Validator log includes ckpt absolute path with username, `~/.cache/huggingface/token`, internal hostnames, signed S3 URLs, W&B keys; diagnoser dumps log into issue body. Public repo → credentials in search index forever.
- **Warning signs:** log contains `Bearer `, `hf_`, `ghp_`, `AKIA`, `/home/<user>/`, internal domain; issue body length > 50KB.
- **Prevention:** (1) Mandatory redaction filter on every body: regex sweep for known secret prefixes + path normalization. Reject post if any secret regex still matches; route to local-only log. (2) Reference ckpt by HF model id, never absolute path. (3) Snapshot tests for redactor on contrived secrets corpus. (4) `loongforge-phase-gate` includes "leak guard" scanning `attempts.jsonl`.
- **Phase:** Phase 0 (redactor lib) — must precede any external posting.

### Pitfall 10 — Vague success criteria → loop wanders (rpcx.io/04)
**P1.** If validator yields vague `failed: some combination` without structured signature, diagnoser proposes random fixes; rpcx.io/04 calls fuzzy goals "Ralph Loop's biggest killer."
- **Warning signs:** two consecutive issues for same phase have very different diagnoses; PRs touch unrelated files; `attempts.jsonl` `failure_signature` missing or just log copy.
- **Prevention:** (1) Every validator emits `failure_signature: {kind, location, expected, actual}`, not free-text. (2) Diagnose acts only on structured signature; if missing, escalate. (3) Codify acceptance as testable predicates in `references/phases/phaseN/verify.md`.
- **Phase:** Phase 2 (validator output schema).

### Pitfall 11 — Fully-autonomous "wake up to merged PRs" loss of control (rpcx.io/08)
**P1.** Autonomous mode runs unattended, merges base PRs into `main`; user finds 12 merged PRs with subtle wrong fixes that compounded. rpcx.io/08: each round fixes one thing, breaks another; loops drift without humans.
- **Warning signs:** PR diffs grow over iterations; same files touched 3+ times; issue bodies > 1000 lines; monotonic code churn.
- **Prevention:** (1) Autonomous mode merges to `staging/run-<id>`, never directly to `main`/`loong-main/core_v0.15.0`; final human gate squash-merges. (2) Hard cap on per-PR diff size (e.g., 500 LOC); split if larger. (3) Force re-read of `PROJECT.md` at start of every iteration. (4) Post-run digest: every merged commit + one-line rationale.
- **Phase:** Phase 3 (autonomous policy).

### Pitfall 12 — Comprehension debt / cognitive surrender (rpcx.io/12)
**P1.** rpcx.io/12: "the faster a loop ships code you didn't write, the wider the gap between repo and what you understand." After 5 successful runs, no mental model of why Phase 2 conversion changed.
- **Warning signs:** PR review comments are "LGTM"; new team members can't explain how adapter works; phase manuals go un-updated.
- **Prevention:** (1) End-of-run mandatory `phases/phaseN_summary.md` written by agent in user's language with diff highlights and rationale. (2) REQ-DOC-01/02: update `references/phases/phaseN/agent.md` whenever agent learns new repair pattern. (3) Periodic "explain back" prompt; user must approve.
- **Phase:** Phase 5 (KB) + post-run digest.

### Pitfall 13 — Two agents writing the same file simultaneously (rpcx.io/12)
**P1.** If loop ever runs more than one phase agent concurrently against same repo, they collide on `phaseN_output.yml` or same Megatron file. rpcx.io/12 prescribes git worktrees.
- **Warning signs:** lost writes in `attempts.jsonl`; PR conflicts on bot-only files; `phaseN_output.yml` written twice with different statuses.
- **Prevention:** (1) Strictly sequential per run; document in SKILL.md. (2) If concurrency added later, mandate `git worktree` per phase + advisory `flock` on `attempts.jsonl`. (3) Single-writer invariant tested in pytest.
- **Phase:** Phase 1 (controller invariants).

### Pitfall 14 — Loop without compounding skills/connectors (rpcx.io/12)
**P1.** rpcx.io/12: "Loops without Skills re-derive the project from scratch each cycle. Loops without Connectors stop after editing code." Concretely: if diagnoser doesn't read `knowledge_base/INDEX.md` and QRH/traps docs, every fix is a fresh guess.
- **Warning signs:** same fix attempted across runs; KB never updated; manual steps in loop.
- **Prevention:** (1) Phase 5 KB update enforced by `loongforge-phase-gate` — KB diff is mandatory output, validated for non-emptiness when new failure pattern seen. (2) Loop controller owns full PR/issue/merge connector chain via `gh`; no manual steps. (3) Each iteration's first action is read `knowledge_base/INDEX.md` + matching QRH doc.
- **Phase:** Phase 5 (KB) + Phase 2 (connectors).

### Pitfall 15 — Using the loop for the wrong work (rpcx.io/12 four-condition test)
**P2.** rpcx.io/12: don't loop one-off work, work without automated validation, work whose token budget can't absorb waste, work where agent lacks senior-engineer tools. Two misuses: (a) exploratory new architecture (no clean validator) → loop spirals; (b) trivial typo fix routed through full Probe→Edit→PR→Merge→Validate.
- **Warning signs:** validator is "user reads output"; phase change touches < 20 LOC and validator runtime > human review time.
- **Prevention:** (1) SKILL.md "When NOT to use this loop" section. (2) `--fast-path` flag for trivial fixes that bypasses validate→issue→fix-PR. (3) If HF model has no published reference loss, refuse Phase 3 loop and route to `human_needed`.
- **Phase:** Phase 0 (entry guards) + docs.

### Pitfall 16 — Self-scoring leniency: validator authored by same agent that fixes (rpcx.io/12)
**P0.** rpcx.io/12: "the model that wrote the code is too kind when scoring itself." If loop ever lets phase agent edit validator (e.g., to "fix flaky threshold"), it can silently widen threshold to make bad fix pass.
- **Warning signs:** PR diff touches `references/phases/phaseN/verify.md`, `loongforge-phase-gate`, or any validator script; threshold constants change in same PR as code.
- **Prevention:** (1) Validator code paths write-protected: any PR diff touching validator path is auto-rejected and converted into `human_needed` escalation. (2) Independent reviewer sub-agent (already on `main` per commit `95c916f`) reviews every fix-PR; explicitly forbid maker == checker. (3) Validator binary hash in `attempts.jsonl`; if hash changes mid-run, abort.
- **Phase:** Phase 1 (controller invariants) + Phase 2 (PR guards).

### Pitfall 17 — PR/issue noise pollutes both repos forever
**P2.** Run of 30 attempts leaves 30 issues + 12 PRs in LoongForge. After 5 model adaptations, issue tracker unreadable. Future searches surface bot noise.
- **Warning signs:** `gh issue list --label bot` count grows monotonically.
- **Prevention:** (1) All bot-created artifacts carry labels `loongforge-adapt`, `run-<id>`, `phase-<N>`. (2) On run completion, close all auxiliary issues with summary linking digest. (3) Rolling housekeeping at startup: close stale bot issues older than N days from prior crashed runs. (4) Use draft PRs while iterating; mark ready-for-review only on final candidate.
- **Phase:** Phase 4 (run finalization).

### Pitfall 18 — `/loop` misuse — using it for phase-internal repair
**P2.** SKILL.md prohibits `/loop` for phase-internal repair, but the new outer loop visually resembles `/loop`. Easy regression: someone wraps PR/issue cycle inside `/loop`, losing structured `attempts.jsonl` audit trail.
- **Warning signs:** new file imports/invokes `/loop` from controller; `attempts.jsonl` entries lack structured fields.
- **Prevention:** (1) Loop controller is Python module, not `/loop` invocation. (2) Lint check in pytest: grep for `/loop` outside `references/` markdown. (3) Keep current SKILL.md `/loop` boundary section, extend with "the new outer loop is also NOT /loop".
- **Phase:** Phase 1.

### Pitfall 19 — In-session vs external-process loop mismatch (rpcx.io/04)
**P2.** rpcx.io/04 distinguishes in-session loops (rich context, risk of bloat) from external-process loops (clean per round, lose mid-flight steering). Adapt skill is in-session; for unattended overnight runs, in-session context will balloon (Phase 3 logs alone are MB-scale).
- **Warning signs:** skill responses slow down across iterations; assistant context recap mentions much earlier phases; OOM-like behavior.
- **Prevention:** (1) Phase agents externalize bulky logs to files, never paste into chat context. (2) On phase boundary, summarize prior phase to a paragraph and drop raw logs from working context. (3) For overnight autonomous, document recommendation: split per phase via separate skill invocations + `--resume`.
- **Phase:** Phase 1 + docs.

---

## Severity Roll-up

| # | Pitfall | Severity | Roadmap Phase |
|---|---------|----------|---------------|
| 1 | Fake/honest-wrong "passed" exit | P0 | Phase 1 |
| 2 | Loop runaway (cost/attempts/wallclock) | P0 | Phase 1 |
| 3 | Validator non-determinism | P0 | Phase 2 |
| 4 | Cross-repo PR deadlock | P0 | Phase 2/3 |
| 5 | State drift local↔remote | P1 | Phase 1/4 |
| 6 | Idempotency on resume/rerun | P1 | Phase 2 |
| 7 | GH rate limits / auth / branch protection | P1/P0 | Phase 0/2 |
| 8 | PR ping-pong, force-push, stale PRs | P1 | Phase 3 |
| 9 | Secrets in PR/issue bodies | P0 | Phase 0 |
| 10 | Vague success criteria | P1 | Phase 2 |
| 11 | Autonomous loss of control | P1 | Phase 3 |
| 12 | Comprehension debt | P1 | Phase 5 |
| 13 | Concurrent agents same files | P1 | Phase 1 |
| 14 | No skills/connectors compounding | P1 | Phase 2/5 |
| 15 | Loop for wrong work | P2 | Phase 0 |
| 16 | Maker == checker on validator | P0 | Phase 1/2 |
| 17 | PR/issue noise pollution | P2 | Phase 4 |
| 18 | `/loop` misuse regression | P2 | Phase 1 |
| 19 | In-session context bloat | P2 | Phase 1 |

---

## Cross-Reference to rpcx.io Articles

- rpcx.io/04: Pitfall 1 (false promises), 2 (max-iterations), 10 (vague success), 19 (in-session vs external)
- rpcx.io/08: Pitfall 11 (autonomous loss of control, oversized issues, context drift)
- rpcx.io/12: Pitfall 2 (token incinerator), 12 (comprehension debt), 13 (concurrent writes / worktrees), 14 (skills + connectors), 15 (four-condition test), 16 (maker-checker leniency)

---

## Confidence

| Area | Level | Reason |
|------|-------|--------|
| Loop control / termination | HIGH | Direct rpcx.io guidance + matches REQ-LOOP-03 |
| GitHub/`gh` integration pitfalls | HIGH | Well-known platform behavior |
| Validator non-determinism | HIGH | Standard CUDA/PyTorch known issues |
| Cross-repo PR coordination | MEDIUM | Loong-Megatron branch policy not externally verifiable |
| Secrets/redaction | HIGH | Standard guidance |

## Open Questions

- Exact branch protection rules on `Zachary-wW/LoongForge:main` and `Zachary-wW/Loong-Megatron:loong-main/core_v0.15.0` — needs `gh api` probe at preflight time
- Whether existing reviewer sub-agent (commit `95c916f`) already enforces validator-path write protection or only PR review
- Concrete loss-diff threshold values per phase — needed to set "rerun N times before issue" policy
- Whether autonomous mode is allowed to merge to `main` at all, or must always go via `staging/run-<id>`
