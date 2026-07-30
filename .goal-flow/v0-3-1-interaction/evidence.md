# Evidence — Goal Flow v0.3.1 交互体验修订

- Goal revision: 1
- Confidence: UNCALIBRATED

## 2026-07-30T07:28:49Z — Requirement REQ-LANG-01
- **status:** UNVERIFIED
- **statement:** 提交说明默认跟随当前对话语言，仓库规范优先并保留 Conventional Commit 类型
- **verified by:** TESTS, DOCS
- **what evidence proves:** 文档契约和回归检查证明语言策略已写入 Skill
- **failure modes:** 中文任务继续产生无解释的英文描述，或仓库既有规范被覆盖
- **basis:** 用户关于提交语言的反馈

## 2026-07-30T07:28:49Z — Requirement REQ-DECISION-02
- **status:** UNVERIFIED
- **statement:** 方案批准前展示决策检查并在高影响问题未决时主动询问
- **verified by:** TESTS, DOCS
- **what evidence proves:** 文档契约检查证明决策检查和主动询问条件存在
- **failure modes:** 未决高影响问题未询问，或无问题时无故打断
- **basis:** 用户关于方案阶段询问透明度的反馈

## 2026-07-30T07:28:50Z — Requirement REQ-APPROVAL-03
- **status:** UNVERIFIED
- **statement:** 批准和验收优先按钮交互，无 UI 时接受自然语言且不要求固定句式
- **verified by:** TESTS, DOCS
- **what evidence proves:** 文档契约与控制器回归证明 UI 降级协议和内部兼容接口存在
- **failure modes:** 用户必须输入固定句式，或按钮/自然语言绕过 Gate
- **basis:** 用户关于 approve/accept 体验的反馈

## 2026-07-30T07:28:50Z — Requirement REQ-COMPAT-04
- **status:** UNVERIFIED
- **statement:** 既有 41 项回归测试、编译、文档检查、控制器 flags 与旧目标继续工作
- **verified by:** TESTS, COMPILE, DOCS
- **what evidence proves:** 控制器生成的冻结检查回执证明兼容性
- **failure modes:** schema 1、无 UI 或现有 CLI 调用被破坏
- **basis:** v0.3 已验收基线

## 2026-07-30T07:28:50Z — Check TESTS
- **status:** PENDING
- **required:** True
- **command:** python3 -m unittest discover -s tests -v
- **timeout:** 180

## 2026-07-30T07:28:50Z — Check COMPILE
- **status:** PENDING
- **required:** True
- **command:** python3 -m compileall -q goal-flow tests
- **timeout:** 60

## 2026-07-30T07:28:50Z — Check DOCS
- **status:** PENDING
- **required:** True
- **command:** python3 -c 'from pathlib import Path; text=n.join(Path(p).read_text() for p in [README.md,docs/design.md,docs/usage.md,goal-flow/skills/goal-flow/SKILL.md,goal-flow/skills/goal-flow/references/planning.md]); required=[当前对话语言,决策检查,批准并执行,接受交付,自然语言,按钮]; raise SystemExit(0 if all(item in text for item in required) else 1)'
- **timeout:** 30

## 2026-07-30T07:28:50Z — Acceptance dimension functional
- **status:** COVERED
- **rationale:** 语言策略、决策检查和审批交互都有明确可观察文档行为
- **criteria:** REQ-LANG-01, REQ-DECISION-02, REQ-APPROVAL-03

## 2026-07-30T07:28:51Z — Acceptance dimension negative-boundary
- **status:** COVERED
- **rationale:** 覆盖仓库规范优先、无高影响问题、无 UI 和固定句式降级边界
- **criteria:** REQ-LANG-01, REQ-DECISION-02, REQ-APPROVAL-03

## 2026-07-30T07:28:51Z — Acceptance dimension regression-compatibility
- **status:** COVERED
- **rationale:** 保留现有 flags、Hook、安装器和旧目标行为
- **criteria:** REQ-COMPAT-04

## 2026-07-30T07:28:51Z — Acceptance dimension documentation-deliverables
- **status:** COVERED
- **rationale:** Skill、planning、execution、usage 和 design 文档需保持一致
- **criteria:** REQ-COMPAT-04

## 2026-07-30T07:30:18Z — Check DOCS
- **status:** PENDING
- **required:** True
- **command:** python3 -c "from pathlib import Path; text=chr(10).join(Path(p).read_text() for p in [\"README.md\",\"docs/design.md\",\"docs/usage.md\",\"goal-flow/skills/goal-flow/SKILL.md\",\"goal-flow/skills/goal-flow/references/planning.md\"]); required=[\"当前对话语言\",\"决策检查\",\"批准并执行\",\"接受交付\",\"自然语言\",\"按钮\"]; raise SystemExit(0 if all(item in text for item in required) else 1)"
- **timeout:** 30

## 2026-07-30T07:30:43Z — Design approved
- **goal revision:** 1
- **design hash:** 5abe289f7c619a997becd72e7d5ca299f77c3b74cdcc3d3aabb3a1b8a3ba8b2a
- **definitions hash:** ae64f33b8255b3a97ada795f94ee13012dd11e919f4540b0731c769450fd0abd
- **next action:** 更新 Skill、协议文档与契约测试
- **approved by:** user

## 2026-07-30T07:30:43Z — Worktree bound
- **root:** /Users/sd/workspace/ai-project/longtask-harness
- **git_dir:** /Users/sd/workspace/ai-project/longtask-harness/.git
- **branch:** codex/goal-flow-v0.3
