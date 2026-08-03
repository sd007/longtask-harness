# Goal Flow

Goal Flow 是一个面向 Codex 的任务执行插件。它会先判断任务规模，再选择合适的工作方式，帮助 Codex 持续完成规划、实现、验证、恢复和交付，减少长任务中途停止、需求偏移或未经验证就宣称完成的问题。

## 主要工具

| 工具 | 作用 |
| --- | --- |
| `$goal-flow` Skill | 用自然语言启动任务，自动选择轻量或完整流程 |
| `goalctl.py` | 管理目标状态、执行检查并生成可审计证据 |
| `SessionStart` Hook | 新任务或恢复会话时加载活动目标摘要 |
| `Stop` Hook | 结束前检查任务是否真正满足完成条件 |
| 审批 MCP | 在完整流程中提供方案批准和最终验收按钮 |

Goal Flow 会按任务复杂度选择最小可用流程：

- `micro`：单文件、小范围修改，直接执行并做最小验证；
- `standard`：一般多步骤任务，使用轻量计划和功能检查；
- `goal-flow`：跨会话、容易偏移或需要完整证据的长任务；
- `strict`：安全、迁移、生产可靠性或不可逆操作等高风险任务。

完整流程只保留三个核心 Gate：方案必须可信、执行不能漂移、交付必须有当前证据。每个检查声明 `mock`、`simulated` 或 `real` 证据等级、覆盖的需求、能证明与不能证明的范围；完整流程、strict 和行为变化任务还必须有一个覆盖用户主路径的目标级检查。

## 安装

前置条件：

- macOS 或 Linux；
- Python 3.10 或更高版本；
- 已安装并登录 Codex CLI。

```bash
git clone https://github.com/sd007/longtask-harness.git
cd longtask-harness
./install.sh
```

安装完成后：

1. 重启 Codex 并新建任务；
2. 在 Codex CLI 输入 `/hooks`；
3. 审查并信任 Goal Flow 的 `SessionStart` 和 `Stop` Hook。

Hook 必须由用户手动信任，安装脚本不会绕过此安全步骤。MCP 配置、启动自检、插件注册和失败回滚均由脚本完成；用户不需要编辑任何配置。更新插件时拉取最新代码后重新运行 `./install.sh` 即可。

常用安装选项：

```bash
./install.sh --dry-run   # 只预览安装操作
./install.sh --no-hooks  # 安装后不打开 Hook 配置引导
./uninstall.sh           # 卸载插件，保留项目中的目标记录
```

## 配置

插件开箱即用，不要求额外配置。需要记录项目约定时，可在目标仓库创建 `.goal-flow/context.md`：

```markdown
# Project context

- 技术栈：Python 3.12
- 测试命令：python3 -m unittest discover -s tests -v
- 提交规范：Conventional Commits，说明使用中文
- 安全边界：未经确认不得部署或修改生产数据
```

这里只应保存技术栈、测试命令、提交约定和安全边界，不要写入密码、令牌或可执行脚本。

## 使用示例

在需要修改的 Git 仓库中开启 Codex 任务，然后直接描述目标：

```text
使用 $goal-flow 为订单接口增加幂等处理，并补充测试和使用文档。
```

高风险任务可以明确要求严格模式：

```text
使用 $goal-flow 的 strict 模式完成数据库迁移，提供回滚方案并验证数据兼容性。
```

Goal Flow 会先展示决策检查。没有高影响未决项时，轻量任务会自动继续；完整流程会请求批准方案。执行期间 Codex 会实现、测试和记录证据，只有真实阻塞、重大方案变化或最终验收需要用户介入。

恢复和控制任务也可以直接使用自然语言：

```text
暂停 Goal Flow，原因是等待测试环境。
恢复 Goal Flow。
显示当前 Goal Flow 的进度和剩余风险。
取消当前目标，原因是需求已变更。
```

## 状态与排查

完整目标保存在目标仓库的 `.goal-flow/` 目录中，主要包括：

- `goal.md`：目标、范围和验收标准；
- `state.json`：唯一当前事实源，保存状态、需求、检查和风险；
- `evidence.md`：只追加审批、验证回执、拒收和最终验收；
- `events.jsonl`：只记录关键状态转换和验证事件。

通常无需手动调用控制器。排查时可在插件源码目录运行：

```bash
python3 goal-flow/skills/goal-flow/scripts/goalctl.py --root /path/to/project status
python3 goal-flow/skills/goal-flow/scripts/goalctl.py --root /path/to/project summary
python3 goal-flow/skills/goal-flow/scripts/goalctl.py --root /path/to/project report
```

常见问题：

- 插件未出现：重启 Codex、新建任务，并检查 `codex plugin list --json`；
- Hook 未运行：在 Codex CLI 的 `/hooks` 中确认两个 Hook 已信任且未禁用；
- 安装失败：先运行 `./install.sh --dry-run` 查看将执行的操作。
- 旧目标报 schema 不兼容：先归档旧 `.goal-flow`，再重新初始化；v0.10 不会自动修改或删除 v1/v2 状态。

更多内容见[安装说明](docs/installation.md)、[使用说明](docs/usage.md)和[设计说明](docs/design.md)。当前版本为 `0.10.0`（schema v3）。
