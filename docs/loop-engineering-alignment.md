# Loop Engineering 在 LoongForge Plugin 中的对照与增强方案

> 参考：Addy Osmani《Loop engineering》— <https://addyosmani.com/blog/loop-engineering/>
>
> 写作日期：2026-06-18

## 0. TL;DR

LoongForge Plugin（尤其是 `/loongforge:adapt_issue_loop`）已经是一个非常典型的 loop engineering 项目：

- 你已经把"提示模型"换成了"设计一个自运行系统"——`adapt → compare-phase → issue-from-report → sync-issue → repair → review → verify-merge-gate → 再跑 phase`。
- Addy 文章里提的"五件套 + 记忆"——Skills、Sub-agents、Worktrees、Plugins/Connectors、Automations、State/Memory——本项目 **4/6 完整命中、2/6 部分命中、1/6 缺位**（详见 §1 表）。完整缺位的是自动调度（Automations）；部分命中的是 Worktrees（用 git 分支替代）和 Connectors（仅 GitHub，无 CI/IM 通道）。再叠加一条结构性短板：缺一个系统性的"独立打分员"。

但仍有 4 个明显的提升点，按优先级是：

1. **加一层独立的检查者**：把 phase 内自检和 PR 评审解耦成"创作者 ≠ 打分员"。
2. **把 `attempts.jsonl` 从日志升级成学习信号**：让上一轮的失败成为下一轮 prompt/skill 的输入。
3. **补上 Automations 这一档**：用 cron / `/loop` / GitHub Actions 做"晨间分诊"。
4. **守住理解债（comprehension debt）**：循环越快，越要给人保留可读的产物。

下面分四节展开：契合度对照、当前循环结构、增强方案、落地路线图。

---

## 1. 契合度对照表

Addy 在文章里把循环分成 **5 件套 + 1 个记忆**。逐项对照本仓库现状：

| Loop Engineering 要素 | 项目现状 | 实现位置 | 状态 |
|---|---|---|---|
| **Skills**（把 intent 写在外面） | 三个有 description 的 SKILL.md，触发说明清晰 | `skills/adapt/SKILL.md`、`skills/adapt_eval/SKILL.md`、`skills/adapt_issue_loop/SKILL.md` | ✅ 已具备 |
| **Sub-agents**（一个出主意、一个检查） | 6 个 phase agent + 隐式的 repair/review/verify 角色 | `agents/adapt-phase{0..5}.md`、`adapt_issue_loop` 中的 repair/review 流程 | ✅ 已具备，但角色分离偏隐式 |
| **Worktrees**（并行 agent 不互踩） | 每个 issue 一条独立分支 `agent/issue-<id>-<slug>` | `skills/adapt_issue_loop/SKILL.md` "Repair PR Loop" | 🟡 用分支替代了 worktree，单进程下够用，多 agent 并发时建议升级 |
| **Plugins / Connectors（MCP）** | GitHub Issue / PR 双向同步 | `skills/adapt_issue_loop/scripts/github.py`、`bin/loongforge-issue-loop sync-issue` | 🟡 有 GitHub 这一条，缺 CI、Linear、IM 等通知通道 |
| **Automations**（自动调度循环） | 仅手动 `loongforge-issue-loop` 触发；hook 是 pass-gate 而非调度器 | `hooks/task_completed_phase_gate.example.json` | ❌ **缺位**：没有 cron/triage inbox/晨间分诊 |
| **State / Memory**（agent 会忘，repo 不会） | 完整的、磁盘上的状态分层 | `run_inputs.yml`、`phases/phaseN_output.yml`、`phases/phaseN/attempts.jsonl`、`eval/SCOREBOARD.md`、`.loongforge/issue-loop/issue_specs/*.yml` | ✅ **典范级**——Addy 那句"the agent forgets, the repo doesn't"在这个项目几乎是一比一落地 |

另外，Addy 强调的两个 in-session 原语：

- **`/loop`**：项目里只允许给"K8s/GPU/远程 CI 这类粗粒度等待"用，phase-local 修复循环交给 phase agent 自己——这是清醒的克制，避免 `/loop` 蜕化成轮询。
- **`/goal`**（带可验证停止条件）：项目里以 `loongforge-phase-gate`（确定性的 `passed` 检查）+ `verify-merge-gate` 充当停止条件。这一层已经存在，但**判定者就是创作者本人**，距 Addy 强调的 "the agent that wrote the code isn't the one grading it" 还差一步。

---

## 2. 当前的循环结构（三层）

把项目拆成 inner / mid / outer 三层循环，便于后面定向加压：

### 2.1 Inner loop — Phase 内自修复（每个 phase agent 自己跑）

```
phase agent 写代码
   ↓
跑 linter / review / L0 smoke / phaseN-verify
   ↓
失败 → 写 phases/phaseN/attempts.jsonl，自己再来一遍
   ↓
通过 → 写 phases/phaseN_output.yml
```

特征：**封闭、短周期、低成本**，由 phase agent 自己掌握节奏。

### 2.2 Mid loop — Issue-driven 修复闭环（`adapt_issue_loop` 主线）

```
adapt 跑出 phaseN 产物
   ↓
compare-phase 与 groundtruth 对比
   ↓ 失败
issue-from-report → sync-issue（GitHub Issue 落地）
   ↓
repair agent: 创建 agent/issue-<n>-<slug> 分支，先复现，再改，再 PR
   ↓
review agent: 对照 IssueSpec / 测试 / 比较器报告
   ↓
verify-merge-gate 通过 → 合并 → 重跑 phaseN
```

特征：**跨 agent、跨进程、用 GitHub 当看板**。这是项目的精华，也是 loop engineering 最浓的一段。

### 2.3 Outer loop — Adapt eval（资格门 / 回归基准）

```
/loongforge:adapt_eval → 备份 → 重新 adapt → 对比 eval/SCOREBOARD
   ↓
追加一行 SCOREBOARD 记录 + witness 文件
```

特征：**只读历史、append-only**，给整个 plugin 提供"我没有越改越差"的证据。

> 这三层目前是手工触达的：内层由 phase agent 自跑，中层和外层都需要人去敲 CLI。**自动化（Automations）层就插在这里**。

---

## 3. 用 Loop Engineering 提升项目效果的四个改造

按"投入产出 + 不破坏现有契约"排序。

### 3.1 改造 A — 显式分离创作者与打分员（高优先级）

**问题**：当前 phase agent 自验、repair agent 自评的概率仍存在。Addy 反复强调："The agent that wrote the code isn't the one grading it."

**做法**：

1. 在 `agents/` 下新增一个 **`adapt-reviewer.md`** sub-agent，明确指令：
   - 只读 `IssueSpec`、`compare-phase` 报告、PR diff、phase manual。
   - 禁止修改代码，只产出 `review_verdict.yml`：`approved | request_changes | block`。
   - 推荐用更强模型 + 更高 reasoning effort（Addy 的"按价值分配 token"原则）。
2. `loongforge-issue-loop` 的 `verify-merge-gate` 在合并前**强制读取** `review_verdict.yml`，没有就直接 fail。
3. Phase 内部同理：phase agent 跑完后，dispatch 一次 **`adapt-verifier`** 子 agent（只读 `phaseN_output.yml` + 比较器报告），独立给 `passed/failed` 投票。两票一致才允许写最终 status。

**收益**：把"自己批改自己作业"这个最大的循环漏洞堵掉，几乎不增加工程复杂度，只多一次只读 sub-agent 调用。

---

### 3.2 改造 B — 让 `attempts.jsonl` 成为学习信号（高优先级）

**问题**：当前 `phases/phaseN/attempts.jsonl` 是"日志"，不是"教材"。下一次重跑时，phase agent 不会主动读它，于是同一个错误可能反复犯——这是 loop engineering 里 state/memory 没用到尽头的典型表现。

**做法**：

1. 给每个 phase manual 加一条入门动作：**Phase agent 启动时先 `tail` 自己的 `attempts.jsonl` 末 N 条**，把"上次为什么失败 + 上次的修复猜想"作为前置上下文。
2. 在 `skills/adapt_issue_loop/scripts/` 加一个 `lessons.py`：从同一个 `target` 历史的所有 `IssueSpec` 中抽取 `root_cause`，归并出 `.loongforge/issue-loop/lessons/<target>.md`。这是给 repair agent 的"踩过的坑清单"。
3. `lessons.md` 用 Addy 推荐的 skill 风格："tight boring description beats a clever one"——一行一条事实，不要叙事。

**收益**：让循环每跑一轮，下一轮的起点都更高。这是 Addy 的"repo 不会忘"原则的真正兑现。

---

### 3.3 改造 C — 补齐 Automations 层（中优先级）

**问题**：项目目前所有循环都靠人手动触发。Addy 给的"晨间分诊"模型——cron 起床、读昨日产物、写 markdown / Linear、为每个发现派 sub-agent——本仓库完全可以照搬。

**做法**：

1. 加一个 **`/loongforge:triage`** skill（或直接是 `bin/loongforge-triage`）：
   - 读 `eval/SCOREBOARD.md` 末 N 条，找回归。
   - 读所有 `runs/*/phases/phaseN/attempts.jsonl`，找连续失败 ≥ K 次的 phase。
   - 列 GitHub 上 `agent/issue-*` PR 的 CI 状态。
   - 输出一份 **`runs/_triage/<date>.md`** 分诊清单。
2. 用 Claude Code 的定时机制（或 GitHub Actions cron）每天早上 9:07（Addy 提醒避开整点）跑一次。
3. 分诊清单里的每一项，由用户人工选一两条让 mid loop 去做——**自动发现，半自动派单**，避开"无人值守地犯错"。
4. 增量：把 `verify-merge-gate` 的失败也作为 GitHub Actions check 暴露出来，让 PR 状态成为外部循环的可见信号。

**收益**：从"我去问循环"变成"循环来找我"，这才是 Addy 那句 "you replaced yourself as the prompter" 的字面意思。

---

### 3.4 改造 D — 守住理解债（必须做，但不是工程，是态度）

**问题**：循环跑得越顺，Addy 列出的三个老大难就越扎手——verification 仍是你的，comprehension debt 在涨，cognitive surrender 在诱惑。

**做法**：

1. **每个被合并的 `agent/issue-*` PR**：要求 PR 描述里有一段 "Human read summary"——repair agent 自己写一两句"这个改动改了什么、为什么有效"，留给将来读代码的人，而不是只给 reviewer agent 看。
2. **每周一次手工抽样**：从过去 7 天合并的 issue PR 里随机挑 2 条，由人完整读一遍 diff。Addy 原话："ship code you confirmed works." 抽样不是为了找 bug，是为了不丢失对自己代码库的理解权。
3. **SCOREBOARD 不只看 pass/fail**：人每周看一次趋势线（adapt 时长、attempts 次数），把"循环健康度"作为指标，而不是只看终态产物对不对。

**收益**：循环不知道你有没有理解它做了什么——你知道。这是文章最后一句话"The loop doesn't know the difference. You do." 在本项目语境下的直接含义。

---

## 4. 落地路线图

按"两周内可见效果"排序：

| 周次 | 动作 | 文件 / 命令 | 验收 |
|---|---|---|---|
| W1 | 新增 `agents/adapt-reviewer.md`、`agents/adapt-verifier.md` | `agents/` | repair PR 必须挂 `review_verdict.yml` 才能合 |
| W1 | 在 phase manual 启动段加入 `attempts.jsonl` 回读步骤 | `skills/adapt/references/phases/phase{0..5}/agent.md` | 重跑同一 phase 时 prompt 里包含"上次失败原因" |
| W2 | 实现 `lessons.py`，每次 sync-issue 后追加 `lessons.md` | `skills/adapt_issue_loop/scripts/lessons.py` | `.loongforge/issue-loop/lessons/ds-v4.md` 持续增长 |
| W2 | 加 `bin/loongforge-triage` + 一个 cron / GitHub Actions | `bin/`、`.github/workflows/triage.yml` | 每日产出 `runs/_triage/<date>.md`，回归立刻可见 |
| W3 | 给已合并 issue PR 增加 "Human read summary" 模板 | `.github/PULL_REQUEST_TEMPLATE.md` | 抽样阅读 2 条/周 |
| W3 | SCOREBOARD 周报：从 `eval/SCOREBOARD.md` 抽出趋势 | `bin/loongforge-adapt-eval` 加 `--weekly` | 每周可读的健康度报告 |

---

## 5. 一段总结

> "Loop engineering is replacing yourself as the person who prompts the agent. You design the system that does it instead."

按这句话的字面去看本项目：

- **你已经做到了**：six-phase 流水线 + issue 驱动闭环 + 比较器 + 状态文件 + 评分板，是一个工程师在用工程师的方式造循环。
- **下一步要做的**，不是再加更多 agent，而是把"独立打分员"装上、让 `attempts.jsonl` 真正反哺、加一层每天主动来找人的分诊、并守住人对代码的理解权。
- **不要做的**：不要让 `/loop` 退化成轮询、不要让 sub-agent 去做不值第二意见的事、不要把 SCOREBOARD 当摆设。

循环不知道你有没有看它做了什么。你知道。
