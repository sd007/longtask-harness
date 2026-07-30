# Goal Flow v0.3 精巧日用版

## Outcome

实现一个精而巧的 Goal Flow v0.3：用 `standard`/`strict` 两档降低日常启动成本，提供清晰 `summary` 与跨会话恢复摘要，补齐状态并发安全、worktree 绑定和 verifier 超时治理，并用极简事件日志与 `report` 支持复盘；保持单 Agent、单仓库、无第三方运行时依赖。

## Non-goals

- 不实现多 Agent 调度、任务 DAG、远程 Runner、云队列、数据库或 Web UI。
- 不实现模型路由、token 计费平台、自演化 scaffold 或概率型完成置信度。
- 不改变“方案需用户批准、严重风险需处理、最终交付需用户验收”的核心语义。
- 不追求 Windows 支持；继续以文档声明的 macOS/Linux 为运行边界。

## Context and sources

- 当前基线提交：`ad275021cfb797ebbc4fe119f75e5127b563aec3`，分支 `codex/goal-flow-v0.1`。
- 2026-07-30 基线：`python3 -m unittest discover -s tests -v` 共 31 个测试全部通过。
- 当前 `plan-check` 对所有目标强制八个质量维度和完整可见合同，可靠但对日常中型任务偏重。
- 当前 `status` 以机器 JSON 为主；SessionStart 只提供状态、里程碑和下一步，没有进度与最近失败摘要。
- 当前 `save_state` 采用原子替换但没有进程锁或 compare-and-swap；`branch` 被记录但未强制校验。
- 当前 verifier 通过 `subprocess.run(..., shell=True, timeout=...)` 执行；超时不能保证终止整棵子进程树。
- 当前 `evidence.md` 可审计，但缺少适合时间线和失败复盘的最小机器事件流。

## Assumptions and decisions

### Profiles

- 新目标默认 `standard`，可通过 `init --profile strict` 选择严格模式。
- 旧状态没有 `profile` 字段时按 `strict` 解释，避免升级后静默弱化既有合同。
- `standard` 仍要求至少一个 MUST、至少一个 required verifier、可观察结果、证据范围、失败模式和依据；只将强制质量维度缩减为 `functional`、`negative-boundary`、`regression-compatibility`、`documentation-deliverables`。
- `strict` 保持现有八维合同，不改变安全、迁移、生产和高风险任务的治理强度。
- Skill 根据任务风险推荐 profile；只要涉及生产数据、权限/隐私、公开接口迁移、可靠性阈值或不可逆操作，就推荐 `strict`。

### Human summary and recovery

- 新增 `summary` 子命令，默认输出简洁文本，`--json` 输出稳定机器结构。
- 摘要固定包含：目标、profile、状态、MUST 进度、当前里程碑、阻塞原因或最近失败、Git SHA 和下一步。
- SessionStart 使用同一摘要生成器，保持 `additionalContextLimit` 内的恢复包；不复制完整 `goal.md` 或 verifier 输出。

### State safety and worktree identity

- 控制器在 `.goal-flow/controller.lock` 上使用 `fcntl.flock`：读命令共享锁，写命令独占锁。
- 状态增加向后兼容的 `state_revision`；每次写入重新读取磁盘 revision 并执行 compare-and-swap，成功后递增。
- 新增 `bind-worktree`，在批准并切换隔离分支后绑定 canonical root、Git dir 和 branch。
- 已批准目标执行 `update`、`verify`、`gate --apply` 等推进操作时校验绑定；路径或分支不一致时 WAIT/拒绝，而不是继续写入。
- 规划、状态查看、暂停、取消和旧目标读取不因缺少绑定而损坏；旧目标可显式绑定后获得强校验。

### Verifier reliability

- verifier 改用独立进程组；超时先向进程组发送 TERM，短暂等待后发送 KILL，并记录 timeout 与终止方式。
- 回执增加轻量环境指纹：OS、架构、Python 版本，以及仓库中已存在的常见 lockfile 哈希；不记录环境变量值和秘密。
- 保持现有 shell 命令批准模型、Git SHA 新鲜度规则和 dirty product-tree 拒绝逻辑。

### Minimal events and report

- 每个目标新增 append-only `events.jsonl`，在同一控制器锁内追加允许列表字段：时间、事件、状态、revision、milestone、check/result、duration、Git SHA 和简短非敏感原因。
- 不记录 verifier 原始输出、环境变量值、用户秘密或完整 prompt。
- 读取器容忍崩溃留下的最后一行无效 JSON，并在 report 中显示 warning。
- 新增 `report`，默认输出 Markdown 风格文本，`--json` 输出机器结构；包含时间线、尝试/失败统计、验收覆盖、检查结果和残余风险。

## Questions requiring user decision

- 没有未决高影响问题。推荐范围已经选择“轻量优先”：保留两档 profile 和两个展示命令，不加入额外运行时或编排层。

## Approved design

v0.3 分三个可独立回滚的实现里程碑：先完成 profile 与摘要体验，再完成状态/verifier 可靠性，最后完成事件与报告。现有 CLI 命令的默认 JSON 行为、旧目标读取、安装与 Hook 配置保持兼容。新命令和新字段均为增量能力。

## Interfaces

```text
goalctl.py init ... [--profile standard|strict]
goalctl.py summary [--goal-id ID] [--json]
goalctl.py bind-worktree [--goal-id ID]
goalctl.py report [--goal-id ID] [--json]
```

- `init` 的新默认 profile 为 `standard`。
- 现有命令仍输出 JSON；只有新增的 `summary` 和 `report` 默认面向人输出文本。
- `state.json` 增加可选字段：`profile`、`state_revision`、`worktree_binding`。
- 新增每目标 `events.jsonl`；`goal.md`、`state.json`、`evidence.md` 继续保留。

## Acceptance dimensions

| Dimension | COVERED or N_A | Rationale | Criterion IDs |
| --- | --- | --- | --- |
| functional | COVERED | 两档 profile、summary、恢复摘要、worktree 绑定、事件和 report 均有可执行行为标准。 | REQ-PROFILE-01, REQ-SUMMARY-02, REQ-STATE-03, REQ-EVENTS-05 |
| negative-boundary | COVERED | 必须覆盖旧状态、错误分支、并发写、超时子进程、损坏事件尾行和敏感数据边界。 | REQ-PROFILE-01, REQ-STATE-03, REQ-VERIFY-04, REQ-EVENTS-05 |
| regression-compatibility | COVERED | 旧目标按 strict 读取，现有命令输出和 31 个基线测试保持兼容。 | REQ-COMPAT-06 |
| security-privacy | COVERED | 事件和环境指纹采用字段允许列表，不记录秘密；shell 验证仍受显式方案批准约束。 | REQ-VERIFY-04, REQ-EVENTS-05 |
| performance-reliability | COVERED | 文件锁、CAS、进程组终止和轻量日志必须在并发及超时测试中可靠工作。 | REQ-STATE-03, REQ-VERIFY-04 |
| operations-observability | COVERED | summary、SessionStart、events.jsonl 和 report 提供日常恢复与复盘所需的最小信号。 | REQ-SUMMARY-02, REQ-EVENTS-05 |
| migration-rollback | COVERED | 新字段可选、旧状态默认 strict，所有里程碑可通过 Git revert 回滚且不要求状态迁移。 | REQ-COMPAT-06 |
| documentation-deliverables | COVERED | README、设计、使用和安装说明必须反映新 profile、命令、兼容性与限制。 | REQ-COMPAT-06 |

## Acceptance criteria

| ID | Kind | Observable outcome | What evidence proves | Negative or boundary cases | Basis | Verifier |
| --- | --- | --- | --- | --- | --- | --- |
| REQ-PROFILE-01 | MUST | 新目标默认使用 standard profile，显式 strict 保留现有八维合同，旧状态缺少 profile 时按 strict 处理；两档都保留 MUST、required verifier、失败模式、明确批准和最终验收。 | 自动化测试证明两档 plan-check 的必需维度、默认值、旧状态解释和核心硬门槛符合设计。 | standard 缺少核心维度必须拒绝；strict 缺少任一八维必须拒绝；旧状态不得被默认为 standard；profile 非法值必须拒绝。 | 用户要求日常轻便但不牺牲完成 Gate，当前 plan-check 实现与旧状态兼容要求 | TESTS |
| REQ-SUMMARY-02 | MUST | summary 文本和 JSON 稳定展示目标、profile、状态、MUST 进度、里程碑、阻塞或最近失败、Git SHA 与下一步，SessionStart 复用同一摘要且不超出上下文限制。 | 自动化测试证明文本/JSON 字段、无活动目标、失败状态和 Hook 恢复输出完整且有界。 | 无活动目标必须友好返回；缺失可选字段不得崩溃；长文本必须截断；不得注入完整测试输出。 | 用户提出趁手的日常恢复体验，当前 status 与 SessionStart 的信息缺口 | TESTS |
| REQ-STATE-03 | MUST | 并发控制器写入由文件锁串行化，state_revision 以 CAS 单调递增；绑定后的目标只能在匹配 canonical root、Git dir 和 branch 的 worktree 推进。 | 并发和 worktree 测试证明没有丢失更新，revision 冲突被拒绝，错误分支不能 verify 或 apply gate。 | 两个并发更新不得覆盖彼此；手工旧 revision 必须触发冲突；detached HEAD、路径变化和分支变化必须明确处理；旧目标读取不得中断。 | 当前原子替换没有锁/CAS且 branch 仅记录不执行，单写者安全边界需要代码保证 | TESTS |
| REQ-VERIFY-04 | MUST | verifier 超时时终止整棵子进程树并记录失败、时长、timeout/信号和轻量环境指纹，同时保持 Git 新鲜度与 dirty-tree 规则。 | 自动化测试用派生子进程验证超时后无存活进程，并检查回执包含允许的环境字段和 lockfile 哈希。 | TERM 无效时必须升级 KILL；无 lockfile 时正常工作；环境指纹不得包含环境变量值；测试修改产品树仍必须 FAIL。 | 当前 subprocess timeout 可能遗留子进程，跨环境回执缺少最小复现信息 | TESTS |
| REQ-EVENTS-05 | MUST | 状态变化和 verifier 执行产生最小 events.jsonl，report 文本/JSON 能重建时间线、失败统计、覆盖和风险，且事件不包含原始输出或秘密。 | 自动化测试证明事件顺序、字段允许列表、损坏尾行容错和 report 聚合结果。 | 并发追加不得交错；最后一行损坏不得使整个 report 失败；原始 verifier 输出和环境变量值不得写入事件；无事件旧目标必须可报告。 | 日常复盘需要机器可读最小事件流，但用户明确拒绝大型平台 | TESTS |
| REQ-COMPAT-06 | MUST | 现有命令、Hook、安装器和 schema 1 目标继续工作，全部文档准确说明 v0.3 的两档流程、新命令、限制和回滚。 | 全量回归、Python 编译检查和文档契约检查证明兼容路径及交付说明存在。 | 旧状态不得要求离线迁移；现有 JSON 消费者不得因新增命令改变既有输出；安装失败回滚行为不得退化。 | 当前 31 个基线测试、标准库依赖承诺和用户要求轻便升级 | TESTS, COMPILE, DOCS |

Required check TESTS: `python3 -m unittest discover -s tests -v`

Required check COMPILE: `python3 -m compileall -q goal-flow tests`

Required check DOCS: `python3 -c 'from pathlib import Path; text="\n".join(Path(p).read_text() for p in ["README.md","docs/design.md","docs/usage.md"]); required=["standard","strict","summary","bind-worktree","events.jsonl","report"]; raise SystemExit(0 if all(item in text for item in required) else 1)'`

## Milestones and Git checkpoints

1. M1 Daily UX：实现 profile、`summary`、SessionStart 恢复摘要和相关文档/测试；提交一个可独立回滚的实现候选。
2. M2 Reliability：实现控制器锁、state_revision CAS、`bind-worktree`、进程组超时清理和环境指纹；提交一个可独立回滚的实现候选。
3. M3 Observability：实现 `events.jsonl`、`report`、容错和脱敏测试；提交一个可独立回滚的实现候选。
4. M4 Verification：在当前实现 SHA 上执行冻结检查、独立复核需求覆盖并提交审计证据。

## Baseline, migration, and rollback

- 基线运行环境：macOS，Python 3 标准库，无项目第三方依赖。
- 旧目标通过字段默认值即时读取，不执行批量迁移，不重写历史 `state.json`。
- 新事件文件缺失表示“尚无事件”，不是错误。
- 每个里程碑单独提交；发生兼容问题时按 M3、M2、M1 逆序 Git revert。
- 卸载和安装失败回滚行为保持不变；项目内 `.goal-flow/` 数据继续保留。

## Risks

- `fcntl` 是 Unix 能力；与当前 macOS/Linux 文档边界一致，但不会扩展 Windows。
- standard 模式减少强制维度，可能漏掉高风险关注点；通过 Skill 风险推荐、核心四维和 strict 显式升级缓解。
- 进程组测试若设计不当可能留下测试进程；使用短生命周期 fixture、PID 探测和最终清理保证测试安全。
- JSONL 最后一行在崩溃时可能不完整；读取器显式容错并报告 warning，不静默忽略中间损坏。
- 事件记录可能意外泄露文本；字段允许列表和不记录原始输出的测试是硬门槛。

## Approval

- Revision: 1
- Status: PENDING
- Approved by: pending
