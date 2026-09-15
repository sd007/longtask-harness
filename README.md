# Goal Flow

Goal Flow 是一个面向 Codex 的任务执行插件。它把一个需求放在同一条“分析设计 → 实现 → 验收”主流程中，重点回答三个问题：方案是否达成一致、实现是否忠实完成方案、少量经典产品场景是否证明结果可用。目标是交付架构合理、能够继续迭代的代码，而不是一次性 demo。

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

完整流程只保留三个核心 Gate：方案一致、实施一致、产品验收。方案用当前/目标状态、模块边界、关键路径、非目标和一次“下一次典型变化”推演对齐；实施结束时复核主路径、模块职责、接口错误、临时捷径和演进扩展点；验收从主路径、关键边界、失败恢复、回归和性能冒烟中选择最重要的 3～5 个场景。每个检查仍声明 `mock`、`simulated` 或 `real` 证据等级；完整流程、strict 和行为变化任务至少有一个覆盖用户主路径的目标级检查。

当需求涉及跨组件架构、关键数据链路、前后端协作、公共接口或高代价决策时，可启用视觉设计。每个目标只增加一个多页 `architecture.drawio` 源文件和一个可在 Codex/浏览器中完整查看的 `architecture.html`；默认两页分别表达整体架构与关键数据流。Draw.io 源文件可直接编辑，审批后仍可移动、缩放或改色，但组件、文字、连线或页面语义变化会要求重新对齐方案。

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

- `goal.md`：目标、方案边界、产品场景、演进探针和验收标准；
- `design/architecture.drawio` / `architecture.html`：按需创建的可编辑设计源与浏览器视图；
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
- 旧目标报 schema 不兼容：先归档旧 `.goal-flow`，再重新初始化；v0.12 不会自动修改或删除 v1/v2 状态。

更多内容见[安装说明](docs/installation.md)、[使用说明](docs/usage.md)和[设计说明](docs/design.md)。当前版本为 `0.12.0`（schema v3）。
