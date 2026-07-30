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

## 2026-07-30T07:02:23Z — Worktree bound
- **root:** /Users/sd/workspace/ai-project/longtask-harness
- **git_dir:** /Users/sd/workspace/ai-project/longtask-harness/.git
- **branch:** codex/goal-flow-v0.3

## 2026-07-30T07:11:39Z — Executed check TESTS
- **status:** PASS
- **command:** python3 -m unittest discover -s tests -v
- **exit code:** 0
- **summary:** exit=0 | hanges (test_goalctl.GoalCtlTests.test_gate_allows_audit_commits_but_invalidates_product_changes) ... ok test_locked_concurrent_updates_increment_state_revision_without_loss (test_goalctl.GoalCtlTests.test_locked_concurrent_updates_increment_state_revision_without_loss) ... ok test_pause_and_resume (test_goalctl.GoalCtlTests.test_pause_and_resume) ... ok test_plan_check_rejects_machine_only_acceptance_details (test_goalctl.GoalCtlTests.test_plan_check_rejects_machine_only_acceptance_details) ... ok test_plan_check_requires_detailed_acceptance_contract (test_goalctl.GoalCtlTests.test_plan_check_requires_detailed_acceptance_contract) ... ok test_profiles_default_to_standard_and_legacy_goals_remain_strict (test_goalctl.GoalCtlTests.test_profiles_default_to_standard_and_legacy_goals_remain_strict) ... ok test_replan_invalidates_approval_and_evidence (test_goalctl.GoalCtlTests.test_replan_invalidates_approval_and_evidence) ... ok test_report_supports_legacy_goals_without_events (test_goalctl.GoalCtlTests.test_report_supports_legacy_goals_without_events) ... ok test_serious_risk_mitigation_requires_fresh_check_receipt (test_goalctl.GoalCtlTests.test_serious_risk_mitigation_requires_fresh_check_receipt) ... ok test_standard_requires_core_dimensions_but_strict_requires_all (test_goalctl.GoalCtlTests.test_standard_requires_core_dimensions_but_strict_requires_all) ... ok test_state_compare_and_swap_rejects_a_stale_writer (test_goalctl.GoalCtlTests.test_state_compare_and_swap_rejects_a_stale_writer) ... ok test_status_is_graceful_without_an_active_goal (test_goalctl.GoalCtlTests.test_status_is_graceful_without_an_active_goal) ... ok test_stop_loop_breaker_waits_after_three_unchanged_attempts (test_goalctl.GoalCtlTests.test_stop_loop_breaker_waits_after_three_unchanged_attempts) ... ok test_summary_has_human_and_json_views (test_goalctl.GoalCtlTests.test_summary_has_human_and_json_views) ... ok test_verifier_receipt_contains_allowlisted_environment_fingerprint (test_goalctl.GoalCtlTests.test_verifier_receipt_contains_allowlisted_environment_fingerprint) ... ok test_verifier_timeout_kills_descendant_process_group (test_goalctl.GoalCtlTests.test_verifier_timeout_kills_descendant_process_group) ... ok test_plugin_hooks_config_matches_codex_schema (test_hooks.HookTests.test_plugin_hooks_config_matches_codex_schema) ... ok test_session_start_is_silent_without_goal_and_restores_active_goal (test_hooks.HookTests.test_session_start_is_silent_without_goal_and_restores_active_goal) ... ok test_stop_continues_execution_but_not_planning_or_repeated_stall (test_hooks.HookTests.test_stop_continues_execution_but_not_planning_or_repeated_stall) ... ok test_dry_run_changes_nothing (test_installer.InstallerTests.test_dry_run_changes_nothing) ... ok test_failed_codex_install_restores_previous_plugin_and_marketplace (test_installer.InstallerTests.test_failed_codex_install_restores_previous_plugin_and_marketplace) ... ok test_install_merges_marketplace_and_copies_plugin (test_installer.InstallerTests.test_install_merges_marketplace_and_copies_plugin) ... ok test_installed_plugin_can_uninstall_itself (test_installer.InstallerTests.test_installed_plugin_can_uninstall_itself) ... ok test_interactive_install_offers_codex_hook_setup (test_installer.InstallerTests.test_interactive_install_offers_codex_hook_setup) ... ok test_invalid_marketplace_is_never_overwritten (test_installer.InstallerTests.test_invalid_marketplace_is_never_overwritten) ... ok test_one_command_wrappers_install_and_uninstall (test_installer.InstallerTests.test_one_command_wrappers_install_and_uninstall) ... ok test_reinstall_replaces_entry_without_duplicates (test_installer.InstallerTests.test_reinstall_replaces_entry_without_duplicates) ... ok test_uninstall_preserves_other_entries_and_is_recoverable (test_installer.InstallerTests.test_uninstall_preserves_other_entries_and_is_recoverable) ... ok  ---------------------------------------------------------------------- Ran 41 tests in 27.059s  OK
- **output digest:** 68f492f1b1d6bc4784c39235179c8310909d0fbdf25451cdc914891dec16f617
- **duration ms:** 27155
- **environment:** {"architecture": "arm64", "lockfiles": {}, "os": "Darwin", "os_release": "25.5.0", "python": "3.13.3"}
- **Git SHA:** 89c8a7fe286a28d95a2aff38e24a6c5a81677a73

## 2026-07-30T07:11:39Z — Executed check COMPILE
- **status:** PASS
- **command:** python3 -m compileall -q goal-flow tests
- **exit code:** 0
- **summary:** exit=0
- **output digest:** e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- **duration ms:** 35
- **environment:** {"architecture": "arm64", "lockfiles": {}, "os": "Darwin", "os_release": "25.5.0", "python": "3.13.3"}
- **Git SHA:** 89c8a7fe286a28d95a2aff38e24a6c5a81677a73

## 2026-07-30T07:11:39Z — Executed check DOCS
- **status:** PASS
- **command:** python3 -c 'from pathlib import Path; text="\n".join(Path(p).read_text() for p in ["README.md","docs/design.md","docs/usage.md"]); required=["standard","strict","summary","bind-worktree","events.jsonl","report"]; raise SystemExit(0 if all(item in text for item in required) else 1)'
- **exit code:** 0
- **summary:** exit=0
- **output digest:** e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- **duration ms:** 26
- **environment:** {"architecture": "arm64", "lockfiles": {}, "os": "Darwin", "os_release": "25.5.0", "python": "3.13.3"}
- **Git SHA:** 89c8a7fe286a28d95a2aff38e24a6c5a81677a73

## 2026-07-30T07:11:55Z — Requirement REQ-PROFILE-01
- **status:** VERIFIED
- **statement:** 新目标默认使用 standard profile，显式 strict 保留现有八维合同，旧状态缺少 profile 时按 strict 处理；两档都保留 MUST、required verifier、失败模式、明确批准和最终验收。
- **evidence:** TESTS 覆盖 standard/strict、默认值、旧目标 strict 回退及维度门槛。
- **Git SHA:** 89c8a7fe286a28d95a2aff38e24a6c5a81677a73
- **verified by:** TESTS
- **what evidence proves:** 自动化测试证明两档 plan-check 的必需维度、默认值、旧状态解释和核心硬门槛符合设计。
- **failure modes:** standard 缺少核心维度必须拒绝；strict 缺少任一八维必须拒绝；旧状态不得被默认为 standard；profile 非法值必须拒绝。
- **basis:** 用户要求日常轻便但不牺牲完成 Gate，当前 plan-check 实现与旧状态兼容要求

## 2026-07-30T07:12:09Z — Requirement REQ-SUMMARY-02
- **status:** VERIFIED
- **statement:** summary 文本和 JSON 稳定展示目标、profile、状态、MUST 进度、里程碑、阻塞或最近失败、Git SHA 与下一步，SessionStart 复用同一摘要且不超出上下文限制。
- **evidence:** TESTS 覆盖 summary 文本/JSON、无活动目标和 SessionStart 有界恢复。
- **Git SHA:** 89c8a7fe286a28d95a2aff38e24a6c5a81677a73
- **verified by:** TESTS
- **what evidence proves:** 自动化测试证明文本/JSON 字段、无活动目标、失败状态和 Hook 恢复输出完整且有界。
- **failure modes:** 无活动目标必须友好返回；缺失可选字段不得崩溃；长文本必须截断；不得注入完整测试输出。
- **basis:** 用户提出趁手的日常恢复体验，当前 status 与 SessionStart 的信息缺口

## 2026-07-30T07:12:09Z — Requirement REQ-STATE-03
- **status:** VERIFIED
- **statement:** 并发控制器写入由文件锁串行化，state_revision 以 CAS 单调递增；绑定后的目标只能在匹配 canonical root、Git dir 和 branch 的 worktree 推进。
- **evidence:** TESTS 覆盖文件锁并发更新、revision CAS、worktree 与错误分支拒绝。
- **Git SHA:** 89c8a7fe286a28d95a2aff38e24a6c5a81677a73
- **verified by:** TESTS
- **what evidence proves:** 并发和 worktree 测试证明没有丢失更新，revision 冲突被拒绝，错误分支不能 verify 或 apply gate。
- **failure modes:** 两个并发更新不得覆盖彼此；手工旧 revision 必须触发冲突；detached HEAD、路径变化和分支变化必须明确处理；旧目标读取不得中断。
- **basis:** 当前原子替换没有锁/CAS且 branch 仅记录不执行，单写者安全边界需要代码保证

## 2026-07-30T07:12:09Z — Requirement REQ-VERIFY-04
- **status:** VERIFIED
- **statement:** verifier 超时时终止整棵子进程树并记录失败、时长、timeout/信号和轻量环境指纹，同时保持 Git 新鲜度与 dirty-tree 规则。
- **evidence:** TESTS 覆盖进程组超时 TERM/KILL、子进程清理、环境指纹和 dirty-tree 规则。
- **Git SHA:** 89c8a7fe286a28d95a2aff38e24a6c5a81677a73
- **verified by:** TESTS
- **what evidence proves:** 自动化测试用派生子进程验证超时后无存活进程，并检查回执包含允许的环境字段和 lockfile 哈希。
- **failure modes:** TERM 无效时必须升级 KILL；无 lockfile 时正常工作；环境指纹不得包含环境变量值；测试修改产品树仍必须 FAIL。
- **basis:** 当前 subprocess timeout 可能遗留子进程，跨环境回执缺少最小复现信息

## 2026-07-30T07:12:09Z — Requirement REQ-EVENTS-05
- **status:** VERIFIED
- **statement:** 状态变化和 verifier 执行产生最小 events.jsonl，report 文本/JSON 能重建时间线、失败统计、覆盖和风险，且事件不包含原始输出或秘密。
- **evidence:** TESTS 覆盖事件白名单、并发追加、敏感文本排除、损坏末行恢复、旧目标和 report。
- **Git SHA:** 89c8a7fe286a28d95a2aff38e24a6c5a81677a73
- **verified by:** TESTS
- **what evidence proves:** 自动化测试证明事件顺序、字段允许列表、损坏尾行容错和 report 聚合结果。
- **failure modes:** 并发追加不得交错；最后一行损坏不得使整个 report 失败；原始 verifier 输出和环境变量值不得写入事件；无事件旧目标必须可报告。
- **basis:** 日常复盘需要机器可读最小事件流，但用户明确拒绝大型平台

## 2026-07-30T07:12:09Z — Requirement REQ-COMPAT-06
- **status:** VERIFIED
- **statement:** 现有命令、Hook、安装器和 schema 1 目标继续工作，全部文档准确说明 v0.3 的两档流程、新命令、限制和回滚。
- **evidence:** TESTS、COMPILE、DOCS 均通过，覆盖命令、Hook、安装器、schema 1 和 v0.3 文档。
- **Git SHA:** 89c8a7fe286a28d95a2aff38e24a6c5a81677a73
- **verified by:** TESTS, COMPILE, DOCS
- **what evidence proves:** 全量回归、Python 编译检查和文档契约检查证明兼容路径及交付说明存在。
- **failure modes:** 旧状态不得要求离线迁移；现有 JSON 消费者不得因新增命令改变既有输出；安装失败回滚行为不得退化。
- **basis:** 当前 31 个基线测试、标准库依赖承诺和用户要求轻便升级

## 2026-07-30T07:14:35Z — Executed check TESTS
- **status:** PASS
- **command:** python3 -m unittest discover -s tests -v
- **exit code:** 0
- **summary:** exit=0 | hanges (test_goalctl.GoalCtlTests.test_gate_allows_audit_commits_but_invalidates_product_changes) ... ok test_locked_concurrent_updates_increment_state_revision_without_loss (test_goalctl.GoalCtlTests.test_locked_concurrent_updates_increment_state_revision_without_loss) ... ok test_pause_and_resume (test_goalctl.GoalCtlTests.test_pause_and_resume) ... ok test_plan_check_rejects_machine_only_acceptance_details (test_goalctl.GoalCtlTests.test_plan_check_rejects_machine_only_acceptance_details) ... ok test_plan_check_requires_detailed_acceptance_contract (test_goalctl.GoalCtlTests.test_plan_check_requires_detailed_acceptance_contract) ... ok test_profiles_default_to_standard_and_legacy_goals_remain_strict (test_goalctl.GoalCtlTests.test_profiles_default_to_standard_and_legacy_goals_remain_strict) ... ok test_replan_invalidates_approval_and_evidence (test_goalctl.GoalCtlTests.test_replan_invalidates_approval_and_evidence) ... ok test_report_supports_legacy_goals_without_events (test_goalctl.GoalCtlTests.test_report_supports_legacy_goals_without_events) ... ok test_serious_risk_mitigation_requires_fresh_check_receipt (test_goalctl.GoalCtlTests.test_serious_risk_mitigation_requires_fresh_check_receipt) ... ok test_standard_requires_core_dimensions_but_strict_requires_all (test_goalctl.GoalCtlTests.test_standard_requires_core_dimensions_but_strict_requires_all) ... ok test_state_compare_and_swap_rejects_a_stale_writer (test_goalctl.GoalCtlTests.test_state_compare_and_swap_rejects_a_stale_writer) ... ok test_status_is_graceful_without_an_active_goal (test_goalctl.GoalCtlTests.test_status_is_graceful_without_an_active_goal) ... ok test_stop_loop_breaker_waits_after_three_unchanged_attempts (test_goalctl.GoalCtlTests.test_stop_loop_breaker_waits_after_three_unchanged_attempts) ... ok test_summary_has_human_and_json_views (test_goalctl.GoalCtlTests.test_summary_has_human_and_json_views) ... ok test_verifier_receipt_contains_allowlisted_environment_fingerprint (test_goalctl.GoalCtlTests.test_verifier_receipt_contains_allowlisted_environment_fingerprint) ... ok test_verifier_timeout_kills_descendant_process_group (test_goalctl.GoalCtlTests.test_verifier_timeout_kills_descendant_process_group) ... ok test_plugin_hooks_config_matches_codex_schema (test_hooks.HookTests.test_plugin_hooks_config_matches_codex_schema) ... ok test_session_start_is_silent_without_goal_and_restores_active_goal (test_hooks.HookTests.test_session_start_is_silent_without_goal_and_restores_active_goal) ... ok test_stop_continues_execution_but_not_planning_or_repeated_stall (test_hooks.HookTests.test_stop_continues_execution_but_not_planning_or_repeated_stall) ... ok test_dry_run_changes_nothing (test_installer.InstallerTests.test_dry_run_changes_nothing) ... ok test_failed_codex_install_restores_previous_plugin_and_marketplace (test_installer.InstallerTests.test_failed_codex_install_restores_previous_plugin_and_marketplace) ... ok test_install_merges_marketplace_and_copies_plugin (test_installer.InstallerTests.test_install_merges_marketplace_and_copies_plugin) ... ok test_installed_plugin_can_uninstall_itself (test_installer.InstallerTests.test_installed_plugin_can_uninstall_itself) ... ok test_interactive_install_offers_codex_hook_setup (test_installer.InstallerTests.test_interactive_install_offers_codex_hook_setup) ... ok test_invalid_marketplace_is_never_overwritten (test_installer.InstallerTests.test_invalid_marketplace_is_never_overwritten) ... ok test_one_command_wrappers_install_and_uninstall (test_installer.InstallerTests.test_one_command_wrappers_install_and_uninstall) ... ok test_reinstall_replaces_entry_without_duplicates (test_installer.InstallerTests.test_reinstall_replaces_entry_without_duplicates) ... ok test_uninstall_preserves_other_entries_and_is_recoverable (test_installer.InstallerTests.test_uninstall_preserves_other_entries_and_is_recoverable) ... ok  ---------------------------------------------------------------------- Ran 41 tests in 26.436s  OK
- **output digest:** 7cb20ed2a544abcf9cfa8c85b9d62a9076ba6f42ae77afb2219c991f2518a01e
- **duration ms:** 26523
- **environment:** {"architecture": "arm64", "lockfiles": {}, "os": "Darwin", "os_release": "25.5.0", "python": "3.13.3"}
- **Git SHA:** ae88ccb4fdcd2946e34641ec3641754db4eda706

## 2026-07-30T07:14:36Z — Executed check COMPILE
- **status:** PASS
- **command:** python3 -m compileall -q goal-flow tests
- **exit code:** 0
- **summary:** exit=0
- **output digest:** e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- **duration ms:** 33
- **environment:** {"architecture": "arm64", "lockfiles": {}, "os": "Darwin", "os_release": "25.5.0", "python": "3.13.3"}
- **Git SHA:** ae88ccb4fdcd2946e34641ec3641754db4eda706

## 2026-07-30T07:14:36Z — Executed check DOCS
- **status:** PASS
- **command:** python3 -c 'from pathlib import Path; text="\n".join(Path(p).read_text() for p in ["README.md","docs/design.md","docs/usage.md"]); required=["standard","strict","summary","bind-worktree","events.jsonl","report"]; raise SystemExit(0 if all(item in text for item in required) else 1)'
- **exit code:** 0
- **summary:** exit=0
- **output digest:** e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- **duration ms:** 25
- **environment:** {"architecture": "arm64", "lockfiles": {}, "os": "Darwin", "os_release": "25.5.0", "python": "3.13.3"}
- **Git SHA:** ae88ccb4fdcd2946e34641ec3641754db4eda706

## 2026-07-30T07:14:48Z — Requirement REQ-PROFILE-01
- **status:** VERIFIED
- **statement:** 新目标默认使用 standard profile，显式 strict 保留现有八维合同，旧状态缺少 profile 时按 strict 处理；两档都保留 MUST、required verifier、失败模式、明确批准和最终验收。
- **evidence:** TESTS 覆盖 standard/strict、默认值、旧目标 strict 回退及维度门槛。
- **Git SHA:** ae88ccb4fdcd2946e34641ec3641754db4eda706
- **verified by:** TESTS
- **what evidence proves:** 自动化测试证明两档 plan-check 的必需维度、默认值、旧状态解释和核心硬门槛符合设计。
- **failure modes:** standard 缺少核心维度必须拒绝；strict 缺少任一八维必须拒绝；旧状态不得被默认为 standard；profile 非法值必须拒绝。
- **basis:** 用户要求日常轻便但不牺牲完成 Gate，当前 plan-check 实现与旧状态兼容要求

## 2026-07-30T07:14:48Z — Requirement REQ-SUMMARY-02
- **status:** VERIFIED
- **statement:** summary 文本和 JSON 稳定展示目标、profile、状态、MUST 进度、里程碑、阻塞或最近失败、Git SHA 与下一步，SessionStart 复用同一摘要且不超出上下文限制。
- **evidence:** TESTS 覆盖 summary 文本/JSON、无活动目标和 SessionStart 有界恢复；Skill 恢复路径优先使用摘要。
- **Git SHA:** ae88ccb4fdcd2946e34641ec3641754db4eda706
- **verified by:** TESTS
- **what evidence proves:** 自动化测试证明文本/JSON 字段、无活动目标、失败状态和 Hook 恢复输出完整且有界。
- **failure modes:** 无活动目标必须友好返回；缺失可选字段不得崩溃；长文本必须截断；不得注入完整测试输出。
- **basis:** 用户提出趁手的日常恢复体验，当前 status 与 SessionStart 的信息缺口

## 2026-07-30T07:14:48Z — Requirement REQ-STATE-03
- **status:** VERIFIED
- **statement:** 并发控制器写入由文件锁串行化，state_revision 以 CAS 单调递增；绑定后的目标只能在匹配 canonical root、Git dir 和 branch 的 worktree 推进。
- **evidence:** TESTS 覆盖文件锁并发更新、revision CAS、worktree 与错误分支拒绝。
- **Git SHA:** ae88ccb4fdcd2946e34641ec3641754db4eda706
- **verified by:** TESTS
- **what evidence proves:** 并发和 worktree 测试证明没有丢失更新，revision 冲突被拒绝，错误分支不能 verify 或 apply gate。
- **failure modes:** 两个并发更新不得覆盖彼此；手工旧 revision 必须触发冲突；detached HEAD、路径变化和分支变化必须明确处理；旧目标读取不得中断。
- **basis:** 当前原子替换没有锁/CAS且 branch 仅记录不执行，单写者安全边界需要代码保证

## 2026-07-30T07:14:49Z — Requirement REQ-VERIFY-04
- **status:** VERIFIED
- **statement:** verifier 超时时终止整棵子进程树并记录失败、时长、timeout/信号和轻量环境指纹，同时保持 Git 新鲜度与 dirty-tree 规则。
- **evidence:** TESTS 覆盖进程组超时 TERM/KILL、子进程清理、环境指纹和 dirty-tree 规则。
- **Git SHA:** ae88ccb4fdcd2946e34641ec3641754db4eda706
- **verified by:** TESTS
- **what evidence proves:** 自动化测试用派生子进程验证超时后无存活进程，并检查回执包含允许的环境字段和 lockfile 哈希。
- **failure modes:** TERM 无效时必须升级 KILL；无 lockfile 时正常工作；环境指纹不得包含环境变量值；测试修改产品树仍必须 FAIL。
- **basis:** 当前 subprocess timeout 可能遗留子进程，跨环境回执缺少最小复现信息

## 2026-07-30T07:14:49Z — Requirement REQ-EVENTS-05
- **status:** VERIFIED
- **statement:** 状态变化和 verifier 执行产生最小 events.jsonl，report 文本/JSON 能重建时间线、失败统计、覆盖和风险，且事件不包含原始输出或秘密。
- **evidence:** TESTS 覆盖事件白名单、并发追加、敏感文本排除、损坏末行恢复、旧目标和 report。
- **Git SHA:** ae88ccb4fdcd2946e34641ec3641754db4eda706
- **verified by:** TESTS
- **what evidence proves:** 自动化测试证明事件顺序、字段允许列表、损坏尾行容错和 report 聚合结果。
- **failure modes:** 并发追加不得交错；最后一行损坏不得使整个 report 失败；原始 verifier 输出和环境变量值不得写入事件；无事件旧目标必须可报告。
- **basis:** 日常复盘需要机器可读最小事件流，但用户明确拒绝大型平台

## 2026-07-30T07:14:49Z — Requirement REQ-COMPAT-06
- **status:** VERIFIED
- **statement:** 现有命令、Hook、安装器和 schema 1 目标继续工作，全部文档准确说明 v0.3 的两档流程、新命令、限制和回滚。
- **evidence:** TESTS、COMPILE、DOCS 均通过，覆盖命令、Hook、安装器、schema 1 和 v0.3 文档。
- **Git SHA:** ae88ccb4fdcd2946e34641ec3641754db4eda706
- **verified by:** TESTS, COMPILE, DOCS
- **what evidence proves:** 全量回归、Python 编译检查和文档契约检查证明兼容路径及交付说明存在。
- **failure modes:** 旧状态不得要求离线迁移；现有 JSON 消费者不得因新增命令改变既有输出；安装失败回滚行为不得退化。
- **basis:** 当前 31 个基线测试、标准库依赖承诺和用户要求轻便升级

## 2026-07-30T07:18:41Z — User acceptance
- **status:** ACCEPTED
- **accepted by:** user
- **Git SHA:** 968523a5733ecd8abfa27d482be089919035d240
