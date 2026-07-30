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

## 2026-07-30T07:34:28Z — Executed check TESTS
- **status:** PASS
- **command:** python3 -m unittest discover -s tests -v
- **exit code:** 0
- **summary:** exit=0 | t_goalctl.GoalCtlTests.test_plan_check_requires_detailed_acceptance_contract) ... ok test_profiles_default_to_standard_and_legacy_goals_remain_strict (test_goalctl.GoalCtlTests.test_profiles_default_to_standard_and_legacy_goals_remain_strict) ... ok test_replan_invalidates_approval_and_evidence (test_goalctl.GoalCtlTests.test_replan_invalidates_approval_and_evidence) ... ok test_report_supports_legacy_goals_without_events (test_goalctl.GoalCtlTests.test_report_supports_legacy_goals_without_events) ... ok test_serious_risk_mitigation_requires_fresh_check_receipt (test_goalctl.GoalCtlTests.test_serious_risk_mitigation_requires_fresh_check_receipt) ... ok test_standard_requires_core_dimensions_but_strict_requires_all (test_goalctl.GoalCtlTests.test_standard_requires_core_dimensions_but_strict_requires_all) ... ok test_state_compare_and_swap_rejects_a_stale_writer (test_goalctl.GoalCtlTests.test_state_compare_and_swap_rejects_a_stale_writer) ... ok test_status_is_graceful_without_an_active_goal (test_goalctl.GoalCtlTests.test_status_is_graceful_without_an_active_goal) ... ok test_stop_loop_breaker_waits_after_three_unchanged_attempts (test_goalctl.GoalCtlTests.test_stop_loop_breaker_waits_after_three_unchanged_attempts) ... ok test_summary_has_human_and_json_views (test_goalctl.GoalCtlTests.test_summary_has_human_and_json_views) ... ok test_verifier_receipt_contains_allowlisted_environment_fingerprint (test_goalctl.GoalCtlTests.test_verifier_receipt_contains_allowlisted_environment_fingerprint) ... ok test_verifier_timeout_kills_descendant_process_group (test_goalctl.GoalCtlTests.test_verifier_timeout_kills_descendant_process_group) ... ok test_plugin_hooks_config_matches_codex_schema (test_hooks.HookTests.test_plugin_hooks_config_matches_codex_schema) ... ok test_session_start_is_silent_without_goal_and_restores_active_goal (test_hooks.HookTests.test_session_start_is_silent_without_goal_and_restores_active_goal) ... ok test_stop_continues_execution_but_not_planning_or_repeated_stall (test_hooks.HookTests.test_stop_continues_execution_but_not_planning_or_repeated_stall) ... ok test_dry_run_changes_nothing (test_installer.InstallerTests.test_dry_run_changes_nothing) ... ok test_failed_codex_install_restores_previous_plugin_and_marketplace (test_installer.InstallerTests.test_failed_codex_install_restores_previous_plugin_and_marketplace) ... ok test_install_merges_marketplace_and_copies_plugin (test_installer.InstallerTests.test_install_merges_marketplace_and_copies_plugin) ... ok test_installed_plugin_can_uninstall_itself (test_installer.InstallerTests.test_installed_plugin_can_uninstall_itself) ... ok test_interactive_install_offers_codex_hook_setup (test_installer.InstallerTests.test_interactive_install_offers_codex_hook_setup) ... ok test_invalid_marketplace_is_never_overwritten (test_installer.InstallerTests.test_invalid_marketplace_is_never_overwritten) ... ok test_one_command_wrappers_install_and_uninstall (test_installer.InstallerTests.test_one_command_wrappers_install_and_uninstall) ... ok test_reinstall_replaces_entry_without_duplicates (test_installer.InstallerTests.test_reinstall_replaces_entry_without_duplicates) ... ok test_uninstall_preserves_other_entries_and_is_recoverable (test_installer.InstallerTests.test_uninstall_preserves_other_entries_and_is_recoverable) ... ok test_approval_has_button_labels_and_natural_language_fallback (test_interaction_contract.InteractionContractTests.test_approval_has_button_labels_and_natural_language_fallback) ... ok test_commit_language_follows_conversation_and_repo_convention (test_interaction_contract.InteractionContractTests.test_commit_language_follows_conversation_and_repo_convention) ... ok test_decision_check_is_visible_and_asks_only_high_impact_questions (test_interaction_contract.InteractionContractTests.test_decision_check_is_visible_and_asks_only_high_impact_questions) ... ok  ---------------------------------------------------------------------- Ran 44 tests in 27.776s  OK
- **output digest:** de823092f77987203601916d54f7bf1ff8da646e86283864fe2f6cf1f0229319
- **duration ms:** 27867
- **environment:** {"architecture": "arm64", "lockfiles": {}, "os": "Darwin", "os_release": "25.5.0", "python": "3.13.3"}
- **Git SHA:** b649967d2adb6b661886473519b299732fe4b2b3

## 2026-07-30T07:34:28Z — Executed check COMPILE
- **status:** PASS
- **command:** python3 -m compileall -q goal-flow tests
- **exit code:** 0
- **summary:** exit=0
- **output digest:** e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- **duration ms:** 35
- **environment:** {"architecture": "arm64", "lockfiles": {}, "os": "Darwin", "os_release": "25.5.0", "python": "3.13.3"}
- **Git SHA:** b649967d2adb6b661886473519b299732fe4b2b3

## 2026-07-30T07:34:29Z — Executed check DOCS
- **status:** PASS
- **command:** python3 -c "from pathlib import Path; text=chr(10).join(Path(p).read_text() for p in [\"README.md\",\"docs/design.md\",\"docs/usage.md\",\"goal-flow/skills/goal-flow/SKILL.md\",\"goal-flow/skills/goal-flow/references/planning.md\"]); required=[\"当前对话语言\",\"决策检查\",\"批准并执行\",\"接受交付\",\"自然语言\",\"按钮\"]; raise SystemExit(0 if all(item in text for item in required) else 1)"
- **exit code:** 0
- **summary:** exit=0
- **output digest:** e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- **duration ms:** 25
- **environment:** {"architecture": "arm64", "lockfiles": {}, "os": "Darwin", "os_release": "25.5.0", "python": "3.13.3"}
- **Git SHA:** b649967d2adb6b661886473519b299732fe4b2b3

## 2026-07-30T07:34:39Z — Requirement REQ-LANG-01
- **status:** VERIFIED
- **statement:** 提交说明默认跟随当前对话语言，仓库规范优先并保留 Conventional Commit 类型
- **evidence:** TESTS 与 DOCS 通过，验证提交说明按当前对话语言、仓库规范优先和 Conventional Commit 前缀约定写入 Skill。
- **Git SHA:** b649967d2adb6b661886473519b299732fe4b2b3
- **verified by:** TESTS, DOCS
- **what evidence proves:** 文档契约和回归检查证明语言策略已写入 Skill
- **failure modes:** 中文任务继续产生无解释的英文描述，或仓库既有规范被覆盖
- **basis:** 用户关于提交语言的反馈

## 2026-07-30T07:34:39Z — Requirement REQ-DECISION-02
- **status:** VERIFIED
- **statement:** 方案批准前展示决策检查并在高影响问题未决时主动询问
- **evidence:** TESTS 与 DOCS 通过，验证批准前决策检查、无高影响未决项提示和主动询问条件。
- **Git SHA:** b649967d2adb6b661886473519b299732fe4b2b3
- **verified by:** TESTS, DOCS
- **what evidence proves:** 文档契约检查证明决策检查和主动询问条件存在
- **failure modes:** 未决高影响问题未询问，或无问题时无故打断
- **basis:** 用户关于方案阶段询问透明度的反馈

## 2026-07-30T07:34:39Z — Requirement REQ-APPROVAL-03
- **status:** VERIFIED
- **statement:** 批准和验收优先按钮交互，无 UI 时接受自然语言且不要求固定句式
- **evidence:** TESTS 与 DOCS 通过，验证按钮优先文案、无 UI 自然语言降级和内部 flags 兼容约定。
- **Git SHA:** b649967d2adb6b661886473519b299732fe4b2b3
- **verified by:** TESTS, DOCS
- **what evidence proves:** 文档契约与控制器回归证明 UI 降级协议和内部兼容接口存在
- **failure modes:** 用户必须输入固定句式，或按钮/自然语言绕过 Gate
- **basis:** 用户关于 approve/accept 体验的反馈

## 2026-07-30T07:34:39Z — Requirement REQ-COMPAT-04
- **status:** VERIFIED
- **statement:** 既有 41 项回归测试、编译、文档检查、控制器 flags 与旧目标继续工作
- **evidence:** TESTS、COMPILE、DOCS 均通过，验证现有控制器、Hook、安装器、旧目标和文档检查兼容。
- **Git SHA:** b649967d2adb6b661886473519b299732fe4b2b3
- **verified by:** TESTS, COMPILE, DOCS
- **what evidence proves:** 控制器生成的冻结检查回执证明兼容性
- **failure modes:** schema 1、无 UI 或现有 CLI 调用被破坏
- **basis:** v0.3 已验收基线
