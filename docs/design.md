# Goal Flow 可靠性设计

## 核心原则

Goal Flow 不依赖 Agent 自报“已完成”。Skill 先根据任务规模、风险和验证难度选择任务级 Harness；随后由证据优先的目标推理、`plan-check`、Python 控制器、Git 快照和执行 Gate 共同约束结果。行为变化目标还通过 Delta、场景和语义 review 建立计划到实现的追踪链。

## 自适应 Harness

`micro` 不初始化控制器，只保留目标、范围和验证命令；`standard` 使用轻量验收、记录初始化基线并可留在当前工作树；`goal-flow` 才建立完整状态机、显式审批、epoch、证据和最终验收。`classify` 根据文件数、步骤数、风险、行为变化、跨会话和自主执行需求推荐最小安全 Harness。`profile` 只表示验收严格程度，`mode` 表示流程深度，避免把小任务误套成长任务审计。

## 项目上下文与失败恢复

`.goal-flow/context.md` 是项目级的低成本上下文缓存，只允许保存技术栈、命令、约定和安全边界；SessionStart 仅注入截断摘要，并明确其只是 advisory metadata。检查失败会归类为实现缺陷、环境/依赖、授权/外部输入、易失验证器或未知，并给出下一策略；分类是恢复提示，不替代真实根因分析。

## 行为变更追踪

对外可观察行为变化目标可使用 `delta.md` 的 `ADDED`、`MODIFIED`、`REMOVED` 段落，配合 `#### SCN-* (REQ-*):` 的 Given/When/Then 场景和 `tasks.md` 的 `T-*` 清单。`goalctl review` 检查完整性、正确性线索和一致性；它不替代真实测试，也不会把 Agent 自报结果当作证据。

## 状态模型

规划与等待状态不会触发自动续跑；`EXECUTING` 和 `VERIFYING` 允许 Gate 返回 `CONTINUE`；完整 Goal Flow 的硬门槛满足后进入 `READY_FOR_ACCEPTANCE`，只有用户明确确认才进入 `ACCEPTED`；低风险、非行为变化的 Standard 通过硬门槛后直接完成，行为变化或中风险 Standard 仍进入 `READY_FOR_ACCEPTANCE`。

需要改变批准基线时必须 `replan`。统一合同哈希覆盖 `goal.md`、profile、验收标准、证据范围、失败模式、依据来源、所需质量维度、标准到检查的映射以及检查命令；任何批准后的静默改写都会触发漂移，Gate 立即停止自动推进。旧目标缺少 profile 时按 `strict` 解释，保持原有八维合同。

## 轻量 profile

`standard` 是日常默认值，轻量 Harness 只强制评估 `functional`，并要求一个可观察 MUST 和一个控制器实际执行的 required check；完整 `goal-flow` 的 standard profile 再评估边界、兼容和交付物四个维度。涉及安全、数据迁移、性能 SLO、生产运维或不可逆操作时使用 `strict`，补齐全部八维。完整 Goal Flow 和 strict 保留完整的证据范围、失败模式与依据链；轻量 Standard 只在风险或行为变化需要时升级。

## 状态一致性与执行边界

控制器用 `.goal-flow/controller.lock` 的文件锁串行化读写，用递增 `state_revision` 做 compare-and-swap，避免并发更新静默覆盖。完整 Goal Flow/strict 批准后的目标必须绑定 `codex/goal-flow-*` 分支或独立 worktree；当前工作区例外必须带原因并写入绑定状态。Standard 记录初始化时的产品指纹，允许既有基线修改保持不变，但会阻止基线之外的变化进入验证。新目标不会静默覆盖活动目标，切换必须显式暂停旧目标；恢复指定目标时会同步 active 指针。

## Assurance 而非伪概率

控制器计算：

- MUST 验收标准的新鲜证据覆盖率；
- required checks 的新鲜通过率；
- 未缓解的 high/critical 风险数；
- `HIGH`、`MEDIUM` 或 `LOW` assurance band。

这些是可解释的交付指标，不是成功概率。只有建立带真实结果标签的历史任务集并完成校准后，才适合新增概率型置信度。

## 对话交互边界

提交说明遵循当前对话语言，仓库既有规范优先；控制器不强制英文。方案批准前必须显示结构化决策检查，只有高影响未决项才会触发用户询问。插件内置 `goal_flow_approval` MCP Server，通过标准 `elicitation/create` 请求让宿主生成“批准并执行/修改方案”和“接受交付/需要修改”控件；请求携带 `state_revision`，过期按钮会被拒绝。无 MCP elicitation 时降级为自然语言。按钮或自然语言只转译为现有状态转换，不能绕过 `plan-check`、验收 Gate 或证据新鲜度。

## 证据新鲜度

检查由控制器执行批准时冻结的命令，并记录唯一 receipt、退出码、输出摘要及 SHA-256 摘要、时间和被测试的实现提交；Agent 不能通过 `record check PASS` 自报成功。`VERIFIED` 需求的 SHA 必须从关联 PASS 回执推导，多个回执必须指向同一提交。交付被拒绝后会建立新证据 epoch，旧 receipt 不能再次满足 Gate。超时会先向独立进程组发送 `SIGTERM`，必要时升级为 `SIGKILL`，避免遗留子进程。回执还保存操作系统、架构、Python 版本和根目录依赖锁文件哈希，但不采集环境变量值。为了允许证据本身入库，后续只改变 `.goal-flow/` 的提交被视为审计提交，不改变证据所描述的产品树。若工作树存在其他修改，或证据 SHA 之后任何非 `.goal-flow/` 路径发生变化，证据立即过期。

## 恢复与可观测性

`summary` 输出目标、profile、状态、MUST 进度、里程碑、阻塞或最近失败、Git SHA 和下一动作；SessionStart 复用这份有界摘要，避免把整个审计历史重新塞回上下文。状态变更和验证执行只向 `events.jsonl` 追加白名单元数据，不记录原始输出、prompt、命令或环境变量值。`report` 以文本或 JSON 展示时间线、验证尝试与失败、标准和检查覆盖率、残余风险；读取器可忽略崩溃造成的不完整末行，旧目标没有事件文件也能正常报告。

风险也服从证据链：`MITIGATED` 必须绑定新鲜 PASS 检查，不能靠自由文本自报；不可机器证明的残余风险保持 `OPEN`，或由用户明确 `ACCEPTED`。用户接受的 high/critical 风险虽不阻断交付，但 assurance 不会是 `HIGH`。

## 信任边界

v0.8 能降低遗漏、漂移、早停、并发写丢失和无证据结论，同时减少普通任务的规划、审批、分支和审计开销；但不能证明：验收标准本身正确、外部服务陈述真实、测试覆盖了未知缺陷，或被授予文件写权限的恶意执行者不会同时篡改状态与哈希。因此状态与审计记录用于约束合作型 Agent、发现幻觉和支持复盘，不是防篡改账本；Hook 是工程护栏，不是安全沙箱。最终用户验收和 Codex 权限模型仍然有效。

## 未来扩展条件

只有观测到实际瓶颈后再扩展：多目标并发需要独立活动索引；多 Agent 需要租约与单写者协议；CI/远端运行需要签名证据和重放；概率置信度需要历史基准集、结果标签、Brier score 或可靠性曲线。它们不进入轻量 v0.8。
