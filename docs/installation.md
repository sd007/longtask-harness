# 安装 Goal Flow

## 前置条件

- Codex 桌面端或支持 Plugins 与 Hooks 的 Codex 版本；
- Python 3.10 或更高版本；
- 目标项目已经初始化 Git；
- 允许你审查并信任本地 Hook。

## 方式一：仓库级 marketplace（推荐开发测试）

假设目标仓库为 `/path/to/project`，本项目为 `/path/to/longtask-harness`：

1. 把 `goal-flow/` 复制到目标仓库的 `plugins/goal-flow/`。
2. 创建或合并目标仓库的 `.agents/plugins/marketplace.json`：

```json
{
  "name": "project-local",
  "interface": {
    "displayName": "Project Local Plugins"
  },
  "plugins": [
    {
      "name": "goal-flow",
      "source": {
        "source": "local",
        "path": "./plugins/goal-flow"
      },
      "policy": {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL"
      },
      "category": "Productivity"
    }
  ]
}
```

`source.path` 相对于 marketplace 根目录，也就是目标仓库根目录；必须以 `./` 开头并位于该根目录内。

3. 重启 Codex 桌面端。
4. 打开 Plugins Directory，选择 `Project Local Plugins`，安装并启用 Goal Flow。
5. 打开 `/hooks`，审查并信任 Goal Flow 的两个 command hooks。Hook 内容变化后必须重新信任。
6. 新建一个 Codex 任务，输入 `使用 $goal-flow 规划一个长软件任务` 验证 Skill 能被识别。

## 方式二：个人 marketplace

1. 把 `goal-flow/` 复制到 `~/.codex/plugins/goal-flow/`。
2. 在 `~/.agents/plugins/marketplace.json` 中合并同样的插件条目，把路径设为 `./.codex/plugins/goal-flow`。
3. 重启桌面端，从个人 marketplace 安装插件，然后用 `/hooks` 完成 Hook 信任。

不要直接覆盖已有 `marketplace.json`；保留其中其他插件条目。个人 marketplace 的路径相对于用户主目录。

## 安装验证

在一个临时 Git 仓库中启动新任务并调用 `$goal-flow`。验证以下现象：

- 仓库出现 `.goal-flow/<goal-id>/goal.md`、`state.json`、`evidence.md`；
- 未批准方案时，Codex 不开始修改实现；
- 重启或继续任务时，`SessionStart` 能提示活动目标和下一步；
- 尚有硬门槛缺口时，`Stop` 会要求继续；三次无状态进展后会持久化 `BLOCKED`、显示阻塞原因并停止续跑，而不是无限循环或无痕早停。

## 更新与卸载

更新插件源后，提升 `.codex-plugin/plugin.json` 的版本，刷新或重新安装 marketplace 中的插件，并重新审查发生变化的 Hooks。卸载时在 Plugins Directory 禁用或移除 Goal Flow；目标仓库中的 `.goal-flow/` 是项目审计记录，不会自动删除。

以上 marketplace、插件缓存与 Hook 信任流程依据当前 Codex 官方插件与 Hooks 机制；不同账户或组织策略可能限制本地插件和 Hooks。

官方参考：[构建与打包 Codex 插件](https://developers.openai.com/plugins/build/plugins)、[连接并测试插件](https://developers.openai.com/plugins/deploy/connect-chatgpt)、[Codex Hooks](https://learn.chatgpt.com/docs/hooks)。
