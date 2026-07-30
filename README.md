# Goal Flow

Goal Flow 是一个轻量、Codex 原生的长任务软件工程插件。它把“完成”从 Agent 的主观判断，改成由已批准验收标准、Git 状态、可复现检查和残余风险共同决定的确定性 Gate。

它只有四个核心部件：

- 一个用户可调用的 `$goal-flow` Skill；
- 一个无第三方依赖的 `goalctl.py` 状态与检查执行控制器；
- `SessionStart` 与 `Stop` 两个 Codex Hooks；
- 每个目标四份简单文件：`goal.md`、`state.json`、`evidence.md`、`events.jsonl`。

```mermaid
flowchart LR
    A["仓库、领域与目标推理"] --> B["方案与验收合同"]
    B --> C0["用户明确批准"]
    C0 --> C["实现一个可验证里程碑"]
    C --> D["测试、反例与审查"]
    D --> E["提交代码并记录证据"]
    E --> F{"确定性 Gate"}
    F -->|"仍有缺口"| C
    F -->|"真实等待条件"| G["等待用户或授权"]
    F -->|"硬门槛满足"| H["用户最终验收"]
```

## 设计边界

Goal Flow v0.3 聚焦单个 Codex、单个 Git 仓库、单个活动目标。默认 `standard` profile 只要求功能、边界、兼容和交付物四个核心维度；高风险任务可显式选择 `strict`，检查全部八维。`summary` 用于低成本恢复上下文，`report` 从最小 `events.jsonl` 汇总覆盖率、验证尝试和残余风险。它不会引入外部 Runner、数据库、Web UI、Agent 编排框架或复杂事件系统，也不会承诺虚假的“100% 正确”。

批准后用 `bind-worktree` 把目标绑定到规范化仓库、Git 目录和分支；文件锁与 revision CAS 防止并发写丢失。v0.4 内置 MCP 审批服务，在方案和最终交付节点通过标准 elicitation 生成可点击控件，并保留无控件环境下的自然语言降级。验证超时会清理整个进程组，并记录不含环境变量值的运行环境指纹。

## 快速开始

1. 运行 `./install.sh`，再按[安装说明](docs/installation.md)信任 Hooks。
2. 在目标 Git 仓库中新建 Codex 任务。
3. 输入：`使用 $goal-flow 完成 <你的长任务>`。
4. 与 Codex 完善 `goal.md`，明确回复批准方案。
5. Codex 会先展示决策检查，再自主执行里程碑；只有高影响未决项、方案变化、权限/外部输入阻塞和最终验收需要你介入。提交说明默认使用当前对话语言。

完整操作和恢复方式见[使用说明](docs/usage.md)，可靠性模型见[设计说明](docs/design.md)。

## 项目状态

当前版本是 `0.4.0`。它不是生产级形式化验证器；外部系统真实性、验收标准本身是否正确以及用户授权仍属于信任边界。
