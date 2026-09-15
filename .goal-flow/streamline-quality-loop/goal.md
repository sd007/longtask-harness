# 精简 Goal Flow 质量闭环

## Outcome

Goal Flow 以轻量三阶段闭环保证：方案先对齐，实施结果与方案一致，验收命中少量经典功能、失败、回归与性能场景，并显式检查下一次典型变化能否局部扩展。

## Non-goals

- 不把普通任务改造成不可绕过的合规或审计系统。
- 不要求穷举全部产品场景，也不以文档数量代表质量。
- 不移除 strict 对安全、迁移、生产可靠性和不可逆操作的加强要求。

## Context and sources

- 当前仓库已实现三阶段、验收标准冻结、Git SHA 证据新鲜度、风险 Gate 与可选视觉设计。
- 当前 behavior-change 强制生成 `delta.md` 和 `tasks.md`，完整 standard 强制四个维度，普通任务的可迭代性与方案—代码一致性主要依靠文字约定。
- 用户明确要求优先保障方案一致、实施效果、经典产品场景和可迭代架构，而非形式上的绝对强制。

## Assumptions and decisions

- 保留现有状态机、审批、证据新鲜度和风险机制，只调整默认质量模型与文档协议。
- `delta.md` 与 `tasks.md` 改为可选增强；行为场景可以直接写入 `goal.md`。
- lightweight Standard 评估功能、性能/可靠性、可迭代性三个质量焦点；完整 Goal Flow standard 再增加关键边界和回归兼容，共五项。
- strict 继续评估所有高风险维度，并新增可迭代性维度。
- 经典场景采用“从主路径、关键边界、失败恢复、回归、性能冒烟中选择 3～5 个”的指导，不要求所有类别机械齐全。

## Decision Check

- Status: RESOLVED
- Auto-decided: 保留现有三阶段、状态机和证据机制；普通任务不启用视觉设计；使用现有 unittest 全量回归作为目标级检查。
- Recommended defaults: 行为变化至少两个 Given/When/Then 场景；方案中增加一次下一次典型变化推演；性能不相关时允许有依据地标记 N_A。
- User decisions: None

## Questions requiring user decision

- None

## Current and target behavior

- Current: 过程强调完整证据合同，行为变化依赖额外 Delta/Tasks 文件，Standard 缺少性能与可迭代性焦点。
- Target: 一个 `goal.md` 即可表达方案、场景和演进探针；额外文件按需使用；质量焦点直接对应用户关心的功能、性能和长期可维护性。

## Solution boundaries and critical path

- Skill 与 planning reference 定义方案一致 Gate 和紧凑方案卡。
- execution reference 定义主路径、模块边界、接口错误、临时捷径和演进探针五项实施一致复核。
- verification reference 定义 3～5 个经典产品场景与性能冒烟策略。
- `goalctl.py` 调整质量维度、初始化模板和 behavior-change 语义 review；不改变已有状态文件 schema。
- README、设计和使用文档同步新的用户心智模型。

## Evolvability probe

- Most likely next change: 团队未来增加新的产品场景类别或项目级质量焦点。
- Expected extension point: 通过场景指导与 acceptance dimension 集合局部扩展，不改写三阶段状态机、证据收据或审批协议。
- Failure signal: 新增一种场景必须增加新的流程阶段、强制文件或重写已有目标状态。

## Acceptance dimensions

| Dimension | COVERED or N_A | Rationale | Criterion IDs |
| --- | --- | --- | --- |
| functional | COVERED | 初始化模板、语义 review 与文档共同体现新的三 Gate 行为。 | REQ-001, REQ-002, REQ-003 |
| negative-boundary | COVERED | 回归测试覆盖可选文件缺失、场景不足和旧增强文件存在时的边界。 | REQ-002 |
| regression-compatibility | COVERED | 全量测试必须保持现有状态机、审批和证据机制兼容。 | REQ-001, REQ-002, REQ-003 |
| documentation-deliverables | COVERED | Skill、references、README、设计和使用文档保持一致。 | REQ-001, REQ-003 |

## Acceptance criteria

| ID | Kind | Observable outcome | What evidence proves | Negative or boundary cases | Basis | Verifier |
| --- | --- | --- | --- | --- | --- | --- |
| REQ-001 | MUST | 新目标模板和方案协议以方案一致、关键路径、经典产品场景与演进探针为中心，普通任务无需额外管理文档。 | 初始化与交互合同测试证明模板、核心术语和质量焦点可见。 | 非行为变化和低风险任务仍保持轻量；strict 能继续覆盖高风险维度。 | 用户确认的精简三阶段目标和现有 Harness 分层。 | CHK-ALL |
| REQ-002 | MUST | behavior-change 可仅用 `goal.md` 中的场景通过语义 review，至少两个有效场景；存在 `delta.md` 或 `tasks.md` 时仍校验其一致性。 | 控制器测试覆盖无额外文件、场景不足、可选增强文件有效和引用错误。 | 缺少 MUST 关联场景必须阻断；可选文件一旦存在不能包含无效引用。 | 减少形式负担，同时保留关键行为场景追踪。 | CHK-ALL |
| REQ-003 | MUST | Standard 明确评估功能、性能/可靠性和可迭代性；完整流程增加关键边界与回归，并在实施和验收协议中使用 3～5 个经典场景与方案—代码一致复核。 | 全量单元测试和文档交互测试证明维度集合、实施复核与经典场景规则一致。 | 性能不相关时允许有依据的 N_A；不强制穷举五类场景。 | 用户要求关注功能、性能、合理架构和后续迭代。 | CHK-ALL |

Required check CHK-ALL: python3 -m unittest discover -s tests -v

## Product scenarios

#### SCN-001 (REQ-001): 新目标生成精简方案卡

- GIVEN 一个普通或完整 Goal Flow 目标被初始化
- WHEN Agent 打开生成的 `goal.md`
- THEN 方案卡直接呈现当前与目标、方案边界、关键路径、经典场景和演进探针

#### SCN-002 (REQ-002): 行为变化不依赖额外管理文件

- GIVEN 行为变化的 MUST 已在 `goal.md` 中声明两个有效场景
- WHEN 运行 plan-check 和 semantic review
- THEN 不创建或不提供 `delta.md`、`tasks.md` 也可以通过结构审查

#### SCN-003 (REQ-003): 经典场景和可迭代性进入质量 Gate

- GIVEN 一个 Standard 任务准备批准和交付
- WHEN Agent 评估质量焦点并复核最终 diff
- THEN 功能、性能/可靠性、可迭代性被明确评估，并从五类经典场景中选择最关键的 3～5 个

## Milestones

1. 调整控制器质量维度、初始化模板和可选行为场景逻辑。
2. 更新 Skill、三阶段 reference 与用户文档。
3. 更新测试并运行全量回归，复核最终 diff 与演进探针。

## Risks, migration, and rollback

- 风险：现有测试与旧目标仍期待 Delta/Tasks 或四维 Standard；通过兼容读取、可选增强文件和完整回归降低风险。
- 迁移：schema v3 不变，旧目标中的维度和可选文件继续有效。
- 回滚：回退本次实现提交即可恢复旧规则，不修改用户已有状态数据。

## Approval

Approval state is stored only in state.json.
