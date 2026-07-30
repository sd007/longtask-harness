# Goal Flow v0.3.1 交互体验修订

## Outcome

让 Goal Flow 在中文或其他当前对话语言下更自然地工作：Git 提交说明遵循当前语言与仓库规范；方案阶段显式展示决策检查并在确有高影响未决项时主动询问；方案批准和最终验收优先使用宿主提供的按钮，无法使用按钮时接受自然语言确认，不再要求用户输入固定句式。

## Non-goals

- 不实现新的 Codex 宿主 UI，不伪造当前不存在的按钮 API。
- 不改变确定性 Gate、验收证据、Git 新鲜度或内部控制器安全边界。
- 不引入多 Agent、远程服务、数据库或 Web UI。

## Context and sources

- 当前仓库的 `goal-flow/skills/goal-flow/SKILL.md`、`references/planning.md`、`references/execution.md` 和 `docs/usage.md`。
- 用户反馈：中文任务产生英文 commit message、审批需要固定句式、方案阶段是否会主动询问不透明。
- 当前 Codex 工具能力检查：没有始终可用的通用审批按钮工具；按钮能力必须可选，CLI/无 UI 场景需要降级。

## Assumptions and decisions

- 当前对话语言是提交说明的默认语言；仓库既有提交规范优先于语言偏好。
- Conventional Commit 类型前缀（如 `feat:`、`fix:`）保留，描述正文使用当前语言。
- 方案阶段必须输出“决策检查”：已自动确定、建议默认、仍需用户决定；没有未决项也要明确说明。
- UI 按钮的点击结果只负责转译为内部 `approve`、`accept`、`reject` 或 `replan` 动作；无法提供按钮时由 Agent 识别自然语言并调用现有内部命令。

## Questions requiring user decision

- 无。用户已明确要求执行上述三项体验修订；按钮宿主能力不足时采用自然语言降级。

## Approved design

1. 在 Skill 和执行协议中增加提交语言策略：当前对话语言优先、仓库规范优先、中文示例和提交前检查。
2. 在规划协议中增加强制可见的决策检查，并明确何时必须主动询问、何时应说明“无高影响未决项”。
3. 在 Skill、使用说明和设计说明中定义审批交互：宿主 UI 可用时显示“批准并执行/修改方案”和“接受交付/需要修改”按钮；否则使用自然语言确认，用户无需输入固定句式。现有 CLI flags 只作为内部/无 UI 兼容接口保留。
4. 增加文档契约测试，确保上述行为不会在后续 Skill 编辑中丢失。

## Acceptance dimensions

| Dimension | COVERED or N_A | Rationale | Criterion IDs |
| --- | --- | --- | --- |
| functional | COVERED | 三项交互规则必须在 Skill 和使用协议中可执行。 | REQ-LANG-01, REQ-DECISION-02, REQ-APPROVAL-03 |
| negative-boundary | COVERED | 无 UI、无未决问题、仓库有既有规范时必须有明确降级和优先级。 | REQ-LANG-01, REQ-DECISION-02, REQ-APPROVAL-03 |
| regression-compatibility | COVERED | 现有控制器 flags、Hook、安装器和旧目标行为不能改变。 | REQ-COMPAT-04 |
| documentation-deliverables | COVERED | Skill、规划、执行、使用和设计文档需一致。 | REQ-COMPAT-04 |

## Acceptance criteria

| ID | Kind | Observable outcome | What evidence proves | Negative or boundary cases | Basis | Verifier |
| --- | --- | --- | --- | --- | --- | --- |
| REQ-LANG-01 | MUST | Skill 明确要求提交说明默认跟随当前对话语言、仓库规范优先、保留 Conventional Commit 类型并提供中文示例。 | 文档契约测试和全文检查能证明规则已写入执行协议。 | 仓库规范存在时不强行覆盖；非中文任务不强制中文。 | 用户反馈与现有执行协议。 | TESTS, DOCS |
| REQ-DECISION-02 | MUST | 方案批准前始终展示决策检查，并在存在无法从证据确定且会改变结果/授权边界的高影响问题时主动询问；无问题时明确说明。 | 文档契约测试覆盖三段决策检查和主动询问条件。 | 无高影响问题不得无故打断；低影响偏好采用推荐默认。 | 用户反馈与 planning protocol。 | TESTS, DOCS |
| REQ-APPROVAL-03 | MUST | 方案和交付阶段定义按钮优先的交互文案，并在无 UI 时允许自然语言确认，不要求用户输入固定句式；内部 flags 仍兼容。 | 文档契约测试和现有控制器回归测试证明交互协议与内部接口兼容。 | 宿主无按钮、CLI、手机端必须自然语言降级；按钮点击不得绕过 Gate。 | 用户反馈与当前宿主能力边界。 | TESTS, DOCS |
| REQ-COMPAT-04 | MUST | 现有 41 项回归测试、编译检查和文档检查继续通过，控制器 flags 与旧目标兼容。 | 控制器生成的 TESTS/COMPILE/DOCS 回执。 | schema 1、无 UI、旧 CLI 调用不得失败。 | v0.3 已验收基线。 | TESTS, COMPILE, DOCS |

Required check TESTS: `python3 -m unittest discover -s tests -v`

Required check COMPILE: `python3 -m compileall -q goal-flow tests`

Required check DOCS: `python3 -c 'from pathlib import Path; text="\n".join(Path(p).read_text() for p in ["README.md","docs/design.md","docs/usage.md","goal-flow/skills/goal-flow/SKILL.md","goal-flow/skills/goal-flow/references/planning.md"]); required=["当前对话语言","决策检查","批准并执行","接受交付","自然语言","按钮"]; raise SystemExit(0 if all(item in text for item in required) else 1)'`

Required check DOCS (shell-safe exact command): `python3 -c "from pathlib import Path; text=chr(10).join(Path(p).read_text() for p in [\"README.md\",\"docs/design.md\",\"docs/usage.md\",\"goal-flow/skills/goal-flow/SKILL.md\",\"goal-flow/skills/goal-flow/references/planning.md\"]); required=[\"当前对话语言\",\"决策检查\",\"批准并执行\",\"接受交付\",\"自然语言\",\"按钮\"]; raise SystemExit(0 if all(item in text for item in required) else 1)"`

## Acceptance detail index

- REQ-LANG-01: 提交说明默认跟随当前对话语言，仓库规范优先并保留 Conventional Commit 类型；文档契约和回归检查证明语言策略已写入 Skill；中文任务继续产生无解释的英文描述，或仓库既有规范被覆盖；用户关于提交语言的反馈。
- REQ-DECISION-02: 方案批准前展示决策检查并在高影响问题未决时主动询问；文档契约检查证明决策检查和主动询问条件存在；未决高影响问题未询问，或无问题时无故打断；用户关于方案阶段询问透明度的反馈。
- REQ-APPROVAL-03: 批准和验收优先按钮交互，无 UI 时接受自然语言且不要求固定句式；文档契约与控制器回归证明 UI 降级协议和内部兼容接口存在；用户必须输入固定句式，或按钮/自然语言绕过 Gate；用户关于 approve/accept 体验的反馈。
- REQ-COMPAT-04: 既有 41 项回归测试、编译、文档检查、控制器 flags 与旧目标继续工作；控制器生成的冻结检查回执证明兼容性；schema 1、无 UI 或现有 CLI 调用被破坏；v0.3 已验收基线。

## Dimension rationale index

- functional: 语言策略、决策检查和审批交互都有明确可观察文档行为。
- negative-boundary: 覆盖仓库规范优先、无高影响问题、无 UI 和固定句式降级边界。
- regression-compatibility: 保留现有 flags、Hook、安装器和旧目标行为。
- documentation-deliverables: Skill、planning、execution、usage 和 design 文档需保持一致。

## Milestones

1. M1：完成 v0.3.1 方案、验收合同和决策检查。
2. M2：更新 Skill、规划/执行/使用/设计文档与契约测试。
3. M3：运行冻结检查，提交实现和审计证据。

## Risks, migration, and rollback

- 宿主按钮 API 当前不可保证；保留自然语言和现有 CLI flags 作为兼容路径。
- 回滚方式：revert v0.3.1 文档/测试提交；不需要状态迁移。

## Approval

- Revision: 1
- Status: PENDING
- Approved by: pending
