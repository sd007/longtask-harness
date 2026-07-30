# 安装、更新与卸载

Goal Flow 提供真正的一键管理脚本。普通用户不需要了解 Python、插件路径、marketplace 或 Codex CLI 参数。脚本会保留 marketplace 中的其他插件，安装失败时自动回滚。

## 一键安装

前置条件：macOS 或 Linux、Python 3.10+、已登录的 Codex CLI。

在本仓库根目录执行：

```bash
./install.sh
```

脚本会自动：

1. 将插件复制到 `~/plugins/goal-flow`；
2. 安全合并 `~/.agents/plugins/marketplace.json`，不会覆盖其他插件；
3. 为本次安装生成版本 cachebuster；
4. 执行 `codex plugin add goal-flow@<个人 marketplace 名称> --json`；
5. 失败时恢复原插件和 marketplace。

安装后只需重启 Codex、新建任务，然后在 `/hooks` 中审查并信任 `SessionStart` 和 `Stop`。Hook 信任不能自动跳过，这是安全边界。

这是普通安装需要执行的唯一命令。脚本会自动确认操作并调用内部安全安装器。

## 先预览再安装（可选）

```bash
./install.sh --dry-run
```

## 一键更新

取得新版源码后，重新运行：

```bash
./install.sh
```

脚本会替换旧插件、更新 cachebuster 并重新安装。Hook 内容变化时需要重新信任；请用新任务加载新版 Skill。

## 一键卸载

保留源码目录时，在仓库根目录运行：

```bash
./uninstall.sh
```

如果源码目录已经删除，可以运行安装副本自带的卸载脚本：

```bash
~/plugins/goal-flow/uninstall.sh
```

卸载会从 Codex 和个人 marketplace 移除 Goal Flow。插件目录默认移动到 `~/.Trash`，没有该目录时移动到 `~/.goal-flow-uninstalled`。所有项目里的 `.goal-flow/` 目标、状态和证据都会保留。

确定不需要恢复插件文件时可以永久删除：

```bash
./uninstall.sh --purge
```

## 常见问题

- `codex CLI was not found`：先安装并登录 Codex，再重试。
- 插件没有出现：重启 Codex、使用新任务，并运行 `codex plugin list --json`。
- Hook 没有运行：打开 `/hooks`，确认两个 Hook 已信任且未禁用。
- marketplace JSON 无效：脚本会停止且不会覆盖文件；先修复报告的 JSON 错误。

官方参考：[插件打包](https://developers.openai.com/plugins/build/plugins)、[Codex CLI 插件命令](https://developers.openai.com/codex/cli/reference)、[Hooks](https://learn.chatgpt.com/docs/hooks)。
