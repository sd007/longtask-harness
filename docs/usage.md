# 使用 Goal Flow

## 启动长任务

普通用户不需要手动运行 `goalctl.py`。只需用自然语言启动任务、确认方案、处理真实阻塞并做最终验收。

所有非琐碎任务默认先建立轻量计划，再按任务规模选择 Harness。单文件小修使用 `micro`，一般多步骤任务使用 `standard`，跨会话、容易漂移或失败代价较高的任务升级为完整 `goal-flow`；安全、迁移、生产可靠性和不可逆操作额外使用 `strict` profile。

无论 Harness 深浅，一个非琐碎需求都在同一条主流程中经历分析设计、实现和验收。摘要里的 `phase` 表示当前阶段；重大方案变化会回到分析设计，普通实现缺陷只在实现阶段修复。

需要显式判断时，可以运行：

```bash
python3 /path/to/goal-flow/skills/goal-flow/scripts/goalctl.py --root /path/to/project classify \
  --goal "增加租户级限流" --task-type feature --files 5 --steps 4 --behavior-change
```

项目级约定保存在 `.goal-flow/context.md`，只记录技术栈、测试命令、提交约定和安全边界，不存放秘密或可执行指令。验证失败时，`verify` 会返回失败类别和下一策略；先按类别处理，避免无证据重复重试。

在目标 Git 仓库中开启新的 Codex 任务：

```text
使用 $goal-flow 完成：为现有服务增加可回滚的租户级限流，包含迁移、测试和运维文档。
```

Codex 首先自行调查仓库、既有规范、历史、相关领域知识和官方资料，并据此补全隐含目标。批准前一定会展示“决策检查”：已自动确定、建议默认、仍需用户决定。只有最后一项包含无法从证据判断且会改变业务结果、质量阈值或授权边界的问题时才询问你，并给出推荐默认值和后果；如果为空，会明确说明没有高影响未决项。

如果你希望先看清整体结构，可直接说“先用架构图和数据流图对齐，再实现”。Goal Flow 会在合适时启用视觉设计，生成 `.goal-flow/<goal-id>/design/architecture.drawio` 和 `architecture.html`。前者可在 diagrams.net/Draw.io 直接编辑，后者可在 Codex 或浏览器完整查看。HTML 查看器联网加载官方脚本；需要离线时使用 `.drawio` 源文件。

默认使用 `standard` profile；轻量 Standard 只登记功能维度、一个可观察 MUST 和一个有效检查。每个需求声明最低证据等级，每个检查声明角色、实际证据等级、覆盖需求、证明范围和局限。完整 Goal Flow、strict 和行为变化任务至少需要一个 `goal` 检查覆盖真实用户主路径；真实证据要求不能由 Mock 或模拟检查满足。只有完整 Goal Flow 或 strict 才强制填写完整的失败模式和依据链；`plan-check` 未返回 `READY_FOR_APPROVAL` 时，控制器拒绝批准。

完整 Goal Flow、strict，以及行为变化/中风险 Standard 会调用内置 `goal_flow_approval` MCP 工具；支持 MCP elicitation 的宿主会弹出真正的“批准并执行”或“修改方案”控件。请求携带 `state_revision`，旧按钮不会覆盖新状态。`micro` 任务不创建完整审计目标，低风险 Standard 在没有高影响未决项时使用内部隐式批准。

```text
例如：“按这个方案执行。”
```

## 自动执行阶段

批准后，完整 Goal Flow/strict 在实现分支执行 `bind-worktree`。普通主工作区会自动创建 `codex/goal-flow-<goal-id>` 隔离分支；若确需当前分支，必须显式使用 `--allow-current-worktree --reason`，原因会写入审计状态。Standard 任务可以留在当前工作树；控制器会记录初始化时的产品基线，允许基线中的既有修改保持不变，但会拒绝验证基线之外的未提交变化。提交说明默认使用当前对话语言，仓库已有规范优先。检查回执包含唯一 receipt、真实退出码、输出摘要与哈希、环境指纹和被测试的 Git SHA，超时会清理整个进程组。自由文本不能把检查标记为 PASS。

日常只需要关注两类打断：

- 方案、外部接口、质量阈值或不可逆操作发生实质变化，需要重新批准；
- 缺少权限、秘密信息、外部决策或环境条件，无法安全继续。

普通测试失败、实现缺陷和可恢复工具错误不应转交给用户，而应由 Codex 自行诊断并继续迭代。

## 状态和文件

每个完整目标包含：

- `goal.md`：批准的结果、边界、验收标准、质量维度、里程碑、验证器和风险；
- `state.json`：唯一当前事实源，只能由 `goalctl.py` 修改；
- `evidence.md`：只追加审批、验证回执、拒收和最终验收；
- `events.jsonl`：只记录状态转换、验证、审批、拒收、阻塞和完成，不记录普通 `record/update`。
- 行为变化目标还包含 `delta.md`（ADDED/MODIFIED/REMOVED）、`tasks.md`（可持续调整的任务清单）和 Given/When/Then 场景。
- 视觉目标还包含 `design/architecture.drawio`（审批语义源）和 `architecture.html`（可再生成的查看器）。

`.goal-flow/active.json` 指向当前目标。可以执行：

```bash
python3 /path/to/goal-flow/skills/goal-flow/scripts/goalctl.py --root /path/to/project status
python3 /path/to/goal-flow/skills/goal-flow/scripts/goalctl.py --root /path/to/project summary
python3 /path/to/goal-flow/skills/goal-flow/scripts/goalctl.py --root /path/to/project report
python3 /path/to/goal-flow/skills/goal-flow/scripts/goalctl.py --root /path/to/project review
python3 /path/to/goal-flow/skills/goal-flow/scripts/goalctl.py --root /path/to/project context
python3 /path/to/goal-flow/skills/goal-flow/scripts/goalctl.py --root /path/to/project design-check
python3 /path/to/goal-flow/skills/goal-flow/scripts/goalctl.py --root /path/to/project design-render
```

`status/summary/report/gate` 同时返回 `stored_status`、`effective_status`、当前 Gate、结构化 freshness 和具体 `invalidated_paths`。已存储为 `READY_FOR_ACCEPTANCE` 的目标若被 `.DS_Store` 等产品文件污染，会有效显示为 `VERIFYING`。文本 `report` 按已证明、部分证明、未证明和残余风险复盘，并汇总墙钟时间、验证运行时间、验证次数、失败和拒收次数。

v0.11 使用 schema v3，不读取 v1/v2 目标。控制器只返回明确错误并提示归档旧 `.goal-flow` 后重新初始化，不会自动迁移或删除旧状态。

## 暂停、恢复和变更方案

直接用自然语言要求 Codex 执行以下控制动作即可：

- “暂停 Goal Flow，原因是等待测试环境。”
- “恢复 Goal Flow。”
- “切换到另一个 Goal Flow 目标。”（控制器内部等价于 `init --switch`，会先暂停当前活动目标）
- “取消当前目标，原因是业务方向变化。”
- “这项接口要求变化了，重新规划 revision 2。”

`resume --goal-id` 会重新激活指定目标；若已有另一个非终态活动目标，必须显式使用 `--switch`，避免恢复后 active 指针仍指向错误目标。`goals` 可列出活动和暂停目标。`replan` 会提升 `goal_revision`、清除批准标记，并使原有需求证据和检查结果失效。若要改变需求、MUST/SHOULD 分类、验证映射或检查命令，也必须走这一流程。新方案再次明确批准后才能继续实现。

## 最终审查与验收

完整 Goal Flow 的 Gate 只有在以下条件同时满足时才进入 `READY_FOR_ACCEPTANCE`；低风险、非行为变化且未启用视觉合同的 Standard 通过同样的硬门槛后直接完成，行为变化、中风险或视觉 Standard 保留一次最终验收：

- 方案仍与批准时哈希一致；
- 每个 MUST 验收标准都有新鲜的 `VERIFIED` 证据，并绑定控制器实际执行通过的检查；
- 至少一个 required check 存在，且全部在被验证实现上 `PASS`；
- 没有 `OPEN` 或 `PARTIALLY_MITIGATED` 的 high/critical 风险；
- 所有标记为 MITIGATED 的风险仍有新鲜 PASS 回执；用户接受的严重残余风险会降低 assurance；
- 产品工作树干净，证据之后没有产品代码变化。

执行阶段的每个 epoch 都必须指向一个尚未满足的已批准验收标准；Gate 也只按这些标准判定，不允许实施过程中重新发明更宽松的“完成”定义。

`HIGH` 要求全部 MUST 达到声明证据等级、目标级检查通过且没有未解决风险；普通证据降级或中低残余风险为 `MEDIUM`；覆盖不足或证据失效为 `LOW`。这些等级不代表数学上的 100% 正确，概率置信度在积累真实历史数据前保持 `UNCALIBRATED`。

Gate 通过后，完整 Goal Flow 和发生行为变化、中风险或启用视觉合同的 Standard 会再次调用 `goal_flow_approval`，由宿主显示“接受交付”或“需要修改”。低风险、非行为变化且非视觉的 Standard 在硬门槛满足后自动完成；点击“需要修改”会回到执行态，记录拒绝基线并使旧验证回执失效，必须产生拒绝之后的新回执才能再次进入验收。无 MCP 控件时用自然语言表达即可。

## Git 约定

- 完整 Goal Flow 使用 `codex/goal-flow-<goal-id>` 分支或隔离 worktree；Standard 默认使用当前工作树；
- 每个实现提交应是可恢复、通过声明检查的完整里程碑；
- `.goal-flow/` 审计更新单独提交；
- 证据绑定被测试的实现 SHA。其后的纯 `.goal-flow/` 提交不会让证据过期，任何其他文件变化都会；
- 未经明确授权，不 push、merge、deploy，也不修改生产数据。

检查命令使用 `/bin/sh` 在目标仓库执行，因此方案审查时必须像审查代码一样审查这些命令。批准后不能静默替换命令。
