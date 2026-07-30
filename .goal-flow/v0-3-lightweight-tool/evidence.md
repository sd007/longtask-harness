# Evidence — Goal Flow v0.3 精巧日用版

- Goal revision: 1
- Confidence: UNCALIBRATED

## 2026-07-30T06:49:51Z — Check TESTS
- **status:** PENDING
- **required:** True
- **command:** python3 -m unittest discover -s tests -v
- **timeout:** 180

## 2026-07-30T06:49:51Z — Check COMPILE
- **status:** PENDING
- **required:** True
- **command:** python3 -m compileall -q goal-flow tests
- **timeout:** 60

## 2026-07-30T06:49:51Z — Check DOCS
- **status:** PENDING
- **required:** True
- **command:** python3 -c 'from pathlib import Path; text="\n".join(Path(p).read_text() for p in ["README.md","docs/design.md","docs/usage.md"]); required=["standard","strict","summary","bind-worktree","events.jsonl","report"]; raise SystemExit(0 if all(item in text for item in required) else 1)'
- **timeout:** 30

## 2026-07-30T06:49:51Z — Requirement REQ-PROFILE-01
- **status:** UNVERIFIED
- **statement:** 新目标默认使用 standard profile，显式 strict 保留现有八维合同，旧状态缺少 profile 时按 strict 处理；两档都保留 MUST、required verifier、失败模式、明确批准和最终验收。
- **verified by:** TESTS
- **what evidence proves:** 自动化测试证明两档 plan-check 的必需维度、默认值、旧状态解释和核心硬门槛符合设计。
- **failure modes:** standard 缺少核心维度必须拒绝；strict 缺少任一八维必须拒绝；旧状态不得被默认为 standard；profile 非法值必须拒绝。
- **basis:** 用户要求日常轻便但不牺牲完成 Gate，当前 plan-check 实现与旧状态兼容要求

## 2026-07-30T06:49:51Z — Requirement REQ-SUMMARY-02
- **status:** UNVERIFIED
- **statement:** summary 文本和 JSON 稳定展示目标、profile、状态、MUST 进度、里程碑、阻塞或最近失败、Git SHA 与下一步，SessionStart 复用同一摘要且不超出上下文限制。
- **verified by:** TESTS
- **what evidence proves:** 自动化测试证明文本/JSON 字段、无活动目标、失败状态和 Hook 恢复输出完整且有界。
- **failure modes:** 无活动目标必须友好返回；缺失可选字段不得崩溃；长文本必须截断；不得注入完整测试输出。
- **basis:** 用户提出趁手的日常恢复体验，当前 status 与 SessionStart 的信息缺口

## 2026-07-30T06:49:51Z — Requirement REQ-STATE-03
- **status:** UNVERIFIED
- **statement:** 并发控制器写入由文件锁串行化，state_revision 以 CAS 单调递增；绑定后的目标只能在匹配 canonical root、Git dir 和 branch 的 worktree 推进。
- **verified by:** TESTS
- **what evidence proves:** 并发和 worktree 测试证明没有丢失更新，revision 冲突被拒绝，错误分支不能 verify 或 apply gate。
- **failure modes:** 两个并发更新不得覆盖彼此；手工旧 revision 必须触发冲突；detached HEAD、路径变化和分支变化必须明确处理；旧目标读取不得中断。
- **basis:** 当前原子替换没有锁/CAS且 branch 仅记录不执行，单写者安全边界需要代码保证

## 2026-07-30T06:49:51Z — Requirement REQ-VERIFY-04
- **status:** UNVERIFIED
- **statement:** verifier 超时时终止整棵子进程树并记录失败、时长、timeout/信号和轻量环境指纹，同时保持 Git 新鲜度与 dirty-tree 规则。
- **verified by:** TESTS
- **what evidence proves:** 自动化测试用派生子进程验证超时后无存活进程，并检查回执包含允许的环境字段和 lockfile 哈希。
- **failure modes:** TERM 无效时必须升级 KILL；无 lockfile 时正常工作；环境指纹不得包含环境变量值；测试修改产品树仍必须 FAIL。
- **basis:** 当前 subprocess timeout 可能遗留子进程，跨环境回执缺少最小复现信息

## 2026-07-30T06:49:51Z — Requirement REQ-EVENTS-05
- **status:** UNVERIFIED
- **statement:** 状态变化和 verifier 执行产生最小 events.jsonl，report 文本/JSON 能重建时间线、失败统计、覆盖和风险，且事件不包含原始输出或秘密。
- **verified by:** TESTS
- **what evidence proves:** 自动化测试证明事件顺序、字段允许列表、损坏尾行容错和 report 聚合结果。
- **failure modes:** 并发追加不得交错；最后一行损坏不得使整个 report 失败；原始 verifier 输出和环境变量值不得写入事件；无事件旧目标必须可报告。
- **basis:** 日常复盘需要机器可读最小事件流，但用户明确拒绝大型平台

## 2026-07-30T06:49:52Z — Requirement REQ-COMPAT-06
- **status:** UNVERIFIED
- **statement:** 现有命令、Hook、安装器和 schema 1 目标继续工作，全部文档准确说明 v0.3 的两档流程、新命令、限制和回滚。
- **verified by:** TESTS, COMPILE, DOCS
- **what evidence proves:** 全量回归、Python 编译检查和文档契约检查证明兼容路径及交付说明存在。
- **failure modes:** 旧状态不得要求离线迁移；现有 JSON 消费者不得因新增命令改变既有输出；安装失败回滚行为不得退化。
- **basis:** 当前 31 个基线测试、标准库依赖承诺和用户要求轻便升级

## 2026-07-30T06:50:06Z — Acceptance dimension functional
- **status:** COVERED
- **rationale:** 两档 profile、summary、恢复摘要、worktree 绑定、事件和 report 均有可执行行为标准。
- **criteria:** REQ-PROFILE-01, REQ-SUMMARY-02, REQ-STATE-03, REQ-EVENTS-05

## 2026-07-30T06:50:06Z — Acceptance dimension negative-boundary
- **status:** COVERED
- **rationale:** 必须覆盖旧状态、错误分支、并发写、超时子进程、损坏事件尾行和敏感数据边界。
- **criteria:** REQ-PROFILE-01, REQ-STATE-03, REQ-VERIFY-04, REQ-EVENTS-05

## 2026-07-30T06:50:06Z — Acceptance dimension regression-compatibility
- **status:** COVERED
- **rationale:** 旧目标按 strict 读取，现有命令输出和 31 个基线测试保持兼容。
- **criteria:** REQ-COMPAT-06

## 2026-07-30T06:50:06Z — Acceptance dimension security-privacy
- **status:** COVERED
- **rationale:** 事件和环境指纹采用字段允许列表，不记录秘密；shell 验证仍受显式方案批准约束。
- **criteria:** REQ-VERIFY-04, REQ-EVENTS-05

## 2026-07-30T06:50:06Z — Acceptance dimension performance-reliability
- **status:** COVERED
- **rationale:** 文件锁、CAS、进程组终止和轻量日志必须在并发及超时测试中可靠工作。
- **criteria:** REQ-STATE-03, REQ-VERIFY-04

## 2026-07-30T06:50:06Z — Acceptance dimension operations-observability
- **status:** COVERED
- **rationale:** summary、SessionStart、events.jsonl 和 report 提供日常恢复与复盘所需的最小信号。
- **criteria:** REQ-SUMMARY-02, REQ-EVENTS-05

## 2026-07-30T06:50:07Z — Acceptance dimension migration-rollback
- **status:** COVERED
- **rationale:** 新字段可选、旧状态默认 strict，所有里程碑可通过 Git revert 回滚且不要求状态迁移。
- **criteria:** REQ-COMPAT-06

## 2026-07-30T06:50:07Z — Acceptance dimension documentation-deliverables
- **status:** COVERED
- **rationale:** README、设计、使用和安装说明必须反映新 profile、命令、兼容性与限制。
- **criteria:** REQ-COMPAT-06

## 2026-07-30T06:51:30Z — Design approved
- **goal revision:** 1
- **design hash:** aa3085b7e96829aa115c613154b08f0c065ddade2a91fab7d352a0e8311c3b48
- **definitions hash:** e0f5996ee0acd500474ced41fbe127c93c504bd2042bc46438ab5d313334528f
- **next action:** 实现 standard/strict profile、summary 与 SessionStart 恢复摘要
- **approved by:** user
