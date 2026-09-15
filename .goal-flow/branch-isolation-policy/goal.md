# 调整分支隔离默认策略

## Outcome

普通任务留在当前分支；仅新项目、重大特性或高风险改动自动使用隔离分支或 worktree；Git 提交信息清楚说明变更对象、行为变化和目的/边界。

## Non-goals

- 不改变 Standard 的当前工作树行为。
- 不取消用户显式要求的隔离，也不改变验证、审批和证据机制。
- 不改写已经产生的 Git 历史，只约束后续提交。

## Context and sources

- `cmd_bind_worktree` 当前对完整 Goal Flow/strict 在主工作树自动创建 `codex/goal-flow-*` 分支。
- `classify_harness` 已能区分 task type、risk level、文件数和步骤数，但没有把“是否需要隔离”作为独立策略。
- 用户明确要求普通任务不切换分支，仅新项目、重大特性或高风险改动隔离。
- 用户明确要求提交信息不要过短，要能说明改动内容和解决的问题。

## Assumptions and decisions

- Profile: standard。
- Harness mode: goal-flow.
- Task type: feature.
- Risk level: medium.
- Behavior change: yes.
- Infer from repository and domain evidence before asking the user.

## Decision Check

- Status: RESOLVED
- Auto-decided: 保留 Standard 当前工作树；把隔离判定集中为一个可测试策略；高风险和迁移继续隔离。
- Recommended defaults: 新项目通过显式 `--new-project` 标记；重大特性通过显式 `--major-feature` 或明确的大规模 feature 形态识别。
- User decisions: None

## Questions requiring user decision

- None after repository inspection.

## Current and target behavior

- Current: 完整 Goal Flow/strict 只要绑定主工作树，就默认自动切换到隔离分支。
- Target: 普通任务绑定当前分支；新项目、重大特性、迁移和 high/critical 风险才自动切换到隔离分支或独立 worktree。

## Solution boundaries and critical path

- `classify_harness` 产出任务形态和隔离建议；`cmd_init` 保存新项目/重大特性信号；`cmd_bind_worktree` 只按统一策略决定是否切换。
- 当前分支仍写入 binding，验证阶段继续检查 root/git_dir/branch 一致性；不改变证据绑定方式。
- 提交规范写入 Skill、执行参考和交互契约测试；提交主体保留 Conventional Commits 前缀，描述使用当前对话语言，并在需要时补充正文说明影响和验证。

## Evolvability probe

- Most likely next change: 团队增加新的隔离触发条件。
- Expected extension point: `requires_isolated_worktree(state)` 策略函数和对应分类字段，不改写状态机或验证器。

## Approved design

普通 Goal Flow/中风险 feature 默认不切换分支；`--new-project`、`--major-feature`、迁移和 high/critical 风险使用隔离分支或 worktree。用户显式要求 `--allow-current-worktree` 仍可覆盖并记录原因。

## Acceptance dimensions

| Dimension | COVERED or N_A | Rationale | Criterion IDs |
| --- | --- | --- | --- |
| functional | COVERED | 分类、绑定行为和提交规范契约由单元测试验证。 | REQ-001, REQ-002 |
| performance-reliability | N_A | 仅改变本地分支选择，不改变运行时性能路径。 | REQ-001 |
| evolvability-maintainability | COVERED | 隔离触发条件和提交表达规则均集中在可持续维护的 Skill/策略入口。 | REQ-001, REQ-002 |
| negative-boundary | COVERED | 覆盖普通任务不切换、新项目/重大特性/高风险切换，以及不改写旧历史。 | REQ-001, REQ-002 |
| regression-compatibility | COVERED | 保留 Standard 当前工作树和显式覆盖行为；不改写已有提交历史。 | REQ-001, REQ-002 |

## Acceptance criteria

| ID | Kind | Observable outcome | What evidence proves | Negative or boundary cases | Basis | Verifier |
| --- | --- | --- | --- | --- | --- | --- |
| REQ-001 | MUST | 普通任务在当前分支执行；新项目、重大特性、迁移和 high/critical 风险才使用隔离分支或 worktree。 | 控制器测试覆盖分类、绑定和显式覆盖。 | 普通 Goal Flow 不应切换；已存在隔离分支、detached HEAD 和显式覆盖继续按既有错误/审计规则处理。 | 用户明确要求减少无必要分支切换，同时保留高风险隔离。 | CHK-ALL |
| REQ-002 | MUST | 后续 Git 提交信息保留 Conventional Commits 类型，并清楚说明变更对象、核心行为变化及目的或边界；必要时正文补充影响和验证。 | Skill、执行参考、项目用法和交互契约测试均包含该规则。 | 不要求改写已有提交；不把提交正文写成无关的实现流水账。 | 用户明确要求提交信息更清晰，避免过短而无法判断交付内容。 | CHK-ALL |

## Product scenarios

Choose 3–5 high-value scenarios when useful; the minimum is the real main path and one critical boundary or failure.

#### SCN-001 (REQ-001): 普通任务留在当前分支

- GIVEN 一个中风险、非重大 feature 的完整 Goal Flow 目标位于普通主分支
- WHEN 批准后执行 `bind-worktree`
- THEN 记录当前分支但不自动创建或切换到 `codex/goal-flow-*`

#### SCN-002 (REQ-001): 高影响任务隔离

- GIVEN 新项目、重大 feature、迁移或 high/critical 风险目标位于普通主分支
- WHEN 批准后执行 `bind-worktree`
- THEN 自动切换到隔离分支或使用独立 worktree

#### SCN-003 (REQ-001): 显式例外保留审计

- GIVEN 普通任务需要留在当前工作树
- WHEN 用户显式提供 `--allow-current-worktree --reason`
- THEN 绑定记录包含例外原因且不触发自动切换

#### SCN-004 (REQ-002): 提交信息能解释交付内容

- GIVEN 一个需要提交的实现里程碑
- WHEN Goal Flow 生成或指导 Git 提交信息
- THEN 首行说明类型、变更对象和核心行为变化；必要时正文说明目的、边界和验证结果，且不改写已有历史

## Milestones

1. 实现统一隔离策略与初始化字段。
2. 补充边界/回归测试并同步分支与提交规范文档。
3. 运行冻结全量检查并验收。

## Risks, migration, and rollback

- 风险：任务形态判断过于宽松可能让高影响改动留在主分支；通过显式 high/critical、migration、new-project、major-feature 触发隔离降低风险。
- 迁移：schema v3 增加可选 harness 字段，旧目标仍按既有绑定规则读取。
- 回滚：回退实现提交即可恢复原隔离策略。

Required check CHK-ALL: python3 -m unittest discover -s tests -v

## Approval

Approval state is stored only in state.json.
