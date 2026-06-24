# Phase 02: GitHub Helpers — PR & Issue Lifecycle - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-22
**Phase:** 02-github-helpers-pr-issue-lifecycle
**Areas discussed:** Human-commit conflict handling, Issue dedup granularity, Validator-path protection timing, PR/Issue template format

---

## Human-commit Conflict Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Pause + 等待回应 | 检测到 human commit → 发 /agent-resume comment → loop 进入 paused 状态，等 human 回应后继续 | ✓ |
| Exit human_needed | 检测到 human commit → 写 escalation.md → exit human_needed → run 结束 | |
| Auto-rebase + fallback pause | 尝试 rebase onto human commit → 有冲突则 pause | |

**User's choice:** Pause + 等待回应
**Notes:** Run 不算失败，human 回应后 controller 继续同一轮 loop。Controller 需要支持 `paused` 状态。

---

## Issue Dedup Granularity

| Option | Description | Selected |
|--------|-------------|----------|
| 追加 comment | 同一 (phase, validator, signature) → 追加 comment（含新 attempt 号、新 log 摘要）→ 不开新 issue | ✓ |
| 关旧开新 | 关旧 issue → 开新 issue（链接旧 issue） | |
| 混合：同 attempt 追加，跨 attempt 关旧开新 | 同一 attempt 链追加；fix-PR merge 后 rerun 又失败则关旧开新 | |

**User's choice:** 追加 comment
**Notes:** 一条 issue 追踪一个 bug 的所有 attempt，reviewer 只看一处。

---

## Validator-path Protection Timing

| Option | Description | Selected |
|--------|-------------|----------|
| open_pr 前拦截 | 扫描 diff 是否含 protected paths → 含则拒绝创建 PR → 转 human_needed | ✓ |
| merge_pr 前拦截 | PR 照常创建，merge 前检查 diff → 含则拒绝 merge | |
| 双层：open 前主拦截 + merge 前 fallback | open 前主拦截，diff 解析失败时 merge 前再检查 | |

**User's choice:** open_pr 前拦截
**Notes:** 不创建无效 PR，保持仓库干净。使用 `git diff --name-only` 扫描。

---

## PR/Issue Template Format

| Option | Description | Selected |
|--------|-------------|----------|
| Claude discretion | Researcher 调研常见 bot 格式，planner 参照设计 | ✓ |
| 定义关键约束，其余 discretion | 在 CONTEXT.md 中预定义关键字段，其余留给 planner | |
| 我指定具体格式 | 用户给出具体标题格式、正文模板、label 列表 | |

**User's choice:** Claude discretion
**Notes:** 关键约束已在 REQUIREMENTS 中锁定：标题含 run_id/phase/attempt、正文有 idempotency footer、Fixes #N 关联、labels 含 loongforge-adapt/run-<id>/phase-<N>。

---

## Claude's Discretion

- PR/Issue 具体模板字符串
- Label 颜色
- Comment 模板内容
- Diff 扫描实现细节

## Deferred Ideas

None — discussion stayed within phase scope.
