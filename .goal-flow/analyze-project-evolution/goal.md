# 分析项目定位与 Agent 长任务演进

## Outcome

基于当前仓库代码、测试、文档、Git 历史与截至 2026-07-30 可获得的一手资料，系统分析 Goal Flow 的项目作用、使用场景、优缺点，并形成与主流 AI 长任务自执行策略和 Agent 演化方向对齐的分阶段优化路线。本目标只产出分析、决策建议与验收合同，不修改业务实现。

## Non-goals

- 本轮不实现路线图中的功能，不创建新分支、提交、推送或部署。
- 不把 benchmark 成绩等同于真实生产可靠性，也不声称系统能保证 100% 正确。
- 不把多 Agent、自演化或外部运行时预设为必选架构；是否引入取决于可测瓶颈。
- 不评价特定基础模型的绝对优劣，重点评价 harness、状态、验证和治理机制。

## Context and sources

### Repository evidence inspected on 2026-07-30

- `README.md`：项目定位为轻量、Codex 原生、单仓库单活动目标的长任务软件工程插件。
- `docs/design.md`：说明状态模型、合同哈希、证据新鲜度、assurance 与信任边界。
- `docs/usage.md` 与 `docs/installation.md`：说明用户流程、Git 约定、Hook 信任和安装回滚。
- `goal-flow/skills/goal-flow/scripts/goalctl.py`：控制器状态、Gate、验证回执、风险和设计漂移的实际实现。
- `goal-flow/hooks/session_start.py` 与 `goal-flow/hooks/stop.py`：跨会话恢复提示和停止拦截实现。
- `tests/`：31 个单元测试覆盖控制器、Hook 和安装器；2026-07-30 本地执行全部通过。
- Git 历史 `33c67b1..ad27502`：项目从证据 Gate 演进到加强规划合同、一键安装、Hook 信任引导与 schema 兼容修复。

### External primary sources inspected on 2026-07-30

- Anthropic, Effective harnesses for long-running agents: https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- Anthropic, Harness design for long-running application development: https://www.anthropic.com/engineering/harness-design-long-running-apps
- OpenAI, A practical guide to building agents: https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/
- OpenAI Agents SDK tracing: https://openai.github.io/openai-agents-python/tracing/
- METR, Task-Completion Time Horizons of Frontier AI Models: https://metr.org/time-horizons/
- SWE-agent paper: https://arxiv.org/abs/2405.15793
- Agentless paper: https://arxiv.org/abs/2407.01489
- SWE-Skills-Bench preprint: https://arxiv.org/abs/2603.15401
- Darwin Godel Machine paper: https://arxiv.org/abs/2505.22954
- Live-SWE-agent preprint: https://arxiv.org/abs/2511.13646

## Current project analysis

### What the project is

Goal Flow is a deterministic governance sidecar for a collaborative coding agent. The model still performs repository exploration, planning, coding and diagnosis; Goal Flow supplies a durable acceptance contract, a finite-state controller, Git-bound verification receipts, session recovery hints and a Stop gate. Its central move is to shift “done” from the model's prose judgment to a conjunction of approved requirements, frozen verifier commands, fresh Git evidence, clean product state, residual-risk policy and explicit user acceptance.

This makes it closer to a lightweight transaction protocol for agentic software delivery than to a model runtime or general orchestration framework. It does not own LLM calls, context compaction, tool routing, sandbox provisioning, token budgets, queues, distributed workers or learned planning.

### Core control loop

1. `init` creates `goal.md`, `state.json`, `evidence.md` and an active-goal pointer.
2. Planning registers MUST/SHOULD criteria, exact checks and eight quality dimensions; `plan-check` rejects incomplete contracts.
3. Explicit user approval freezes both the human-readable design hash and machine definitions hash.
4. The agent works in bounded epochs and commits a coherent product candidate.
5. `verify` executes the frozen shell command, captures exit code, digest and Git SHA, and refuses a dirty product tree.
6. Requirement and risk evidence must bind to fresh passing checks.
7. `gate` returns WAIT, CONTINUE or READY_FOR_REVIEW; the Stop hook blocks early termination while CONTINUE remains actionable.
8. Only explicit user acceptance can move the goal to ACCEPTED.

### Best-fit use cases

- Multi-hour or multi-session coding changes with measurable acceptance tests.
- Repository-local refactors, migrations, bug fixes or feature work where rollback through Git is meaningful.
- Regulated or review-heavy teams that value traceability, change approval and evidence over maximum speed.
- Ambiguous requirements that benefit from a formal design checkpoint before implementation.
- Tasks where current Codex tools are sufficient and one writer can safely own the worktree.

### Poor-fit use cases

- Tiny edits whose planning and audit overhead exceeds the work itself.
- Non-Git work, live operations, incident response or production mutations requiring external transactional controls.
- Subjective design/content tasks without reliable executable checks, unless an independent evaluator is added.
- High-concurrency multi-Agent work across branches or repositories; current state has one active goal and no lease/lock protocol.
- Tasks requiring durable remote workers, scheduled wakeups, distributed queues, environment images or service credentials.

## Strengths

1. **Completion semantics are unusually explicit.** MUST criteria, exact verifiers, serious risks, clean-tree checks and user acceptance form a deterministic hard gate.
2. **Evidence is stronger than agent self-report.** Checks are executed by the controller and bound to a Git SHA; product changes invalidate prior evidence.
3. **Requirement drift is actively detected.** Both `goal.md` and structured definitions are hashed after approval, so silent weakening is visible.
4. **Recovery is simple and legible.** Git plus three text/JSON artifacts avoids an external database and lets a fresh session reconstruct next action.
5. **Human authority is preserved.** Plan approval, risky external actions and final acceptance remain explicit user decisions.
6. **The implementation is portable.** The controller uses the Python standard library, installation supports rollback, and the full current regression suite is fast.
7. **It avoids fake probabilistic confidence.** `UNCALIBRATED` is more honest than invented success percentages without labeled historical outcomes.

## Weaknesses and risks

1. **Governance is stronger than execution intelligence.** The controller knows whether evidence is missing, but not how to decompose a large goal, select an optimal next milestone or recover from a complex failure.
2. **Observability is audit-oriented, not operational.** `evidence.md` and short summaries omit full event traces, tool latency, tokens/cost, retry lineage, context resets and failure taxonomy aggregates.
3. **Single-writer assumptions are unenforced.** State writes are atomic but not locked; `branch` is recorded but not enforced; concurrent controller calls can lose updates, and one active goal prevents safe portfolio use.
4. **Verifier trust is broad.** Approved commands run through `/bin/sh`; this is intentional but means approval is also authorization to execute arbitrary repository-local shell behavior. There is no command risk class, sandbox profile, network policy or artifact allowlist.
5. **Process-tree timeout handling is incomplete.** A timed-out shell command may leave descendant processes alive because no process group is created and terminated as a unit.
6. **Evidence is reproducible only within the current environment.** Receipts bind to Git SHA and output digest, but not OS, Python/tool versions, dependency lock digest, environment variables, container image or external service version.
7. **Planning quality is checked structurally.** Length and presence checks can reject placeholders, but cannot prove that acceptance criteria are sufficient, non-gameable or aligned with the user's real intent.
8. **The same agent typically proposes, implements and interprets evidence.** Deterministic tests reduce self-bias, but subjective quality and test adequacy still benefit from an independent evaluator.
9. **The stall detector is coarse.** Three unchanged Stop fingerprints become BLOCKED, but there is no strategy registry, causal graph or distinction between a legitimate long-running action and repeated reasoning failure.
10. **No empirical harness evaluation exists yet.** The repository tests controller correctness, not whether Goal Flow improves task success, time, cost or human intervention relative to baseline Codex runs.

## Comparison with mainstream long-task strategies

| Strategy | Industry/research signal | Current Goal Flow | Gap or decision |
| --- | --- | --- | --- |
| Incremental epochs and clean handoff | Anthropic uses initializer/coding roles, progress artifacts and Git across context windows | Strong: goal/evidence/state artifacts, Git checkpoints, next action | Add explicit context-reset/handoff schema and milestone dependency graph |
| Deterministic acceptance and verifiers | SWE-agent emphasizes agent-computer interface; SWE-Skills-Bench uses criterion-traceable executable tests | Strong differentiator | Benchmark whether the extra contract improves outcomes enough to justify token overhead |
| Simple single-agent first | OpenAI recommends maximizing one agent before adding coordination; Agentless shows simple fixed workflows can outperform complex agents on some tasks | Correct current bias | Keep single-agent core; add evaluator or workers only behind measured failure signals |
| Planner-generator-evaluator separation | Anthropic reports gains from planner/generator/evaluator for multi-hour apps and subjective quality | Partial: planning and gate exist, but usually share one model context | Add optional fresh-context evaluator with evidence-only write permissions |
| Tracing and production telemetry | OpenAI Agents SDK records generations, tools, handoffs, guardrails and custom spans | Weak | Introduce append-only machine event log and optional trace export with redaction controls |
| Durable sessions and managed workers | Modern runtimes serialize resumable state and separate session, harness and sandbox | Minimal: filesystem state plus hooks | Add explicit run/attempt IDs, resumable job state and environment manifest before remote execution |
| Calibrated eval loop | METR evaluates success by task difficulty/human duration; agent eval guidance stresses outcome and trajectory datasets | Honest but absent | Build a labeled task corpus and paired with/without Goal Flow evaluation before confidence scoring |
| Self-evolving scaffolds | DGM and Live-SWE-agent modify agent scaffolds and empirically retain improvements | Not present, appropriately | Treat as later-stage offline optimization; never let a task silently rewrite its own safety gate |

## Agent evolution direction

The likely direction is not simply “more autonomy” or “more agents.” It is a layered progression:

1. From conversational memory to durable, typed run state and structured handoffs.
2. From one monolithic loop to adaptive decomposition, with fresh-context evaluators where self-review is weak.
3. From tool access to purpose-built Agent-Computer Interfaces with typed preconditions, postconditions and risk levels.
4. From pass/fail tests to trajectory observability, counterexample generation, verifier ensembles and outcome-calibrated evals.
5. From fixed prompts/skills to selectively retrieved, versioned procedural knowledge whose marginal value is measured.
6. From manually tuned harnesses to offline/self-evolving scaffolds, but only under immutable external safety gates and held-out evaluation.
7. From local interactive sessions to durable managed execution with sandbox identity, leases, budgets and resumable approvals.

Goal Flow already occupies layers 1 and 4 at a basic level and has unusually solid governance primitives. Its strongest product opportunity is to become the reliable control plane that survives model and scaffold evolution, rather than competing to become another full Agent runtime.

## Assumptions and decisions

- Recommendation: preserve the lightweight, Codex-native, single-agent-first identity. Consequence: the project stays easy to install and reason about, while advanced orchestration remains optional.
- Recommendation: evolve from Markdown audit trail to a dual format: human report plus append-only JSONL events. Consequence: better debugging and benchmarking without requiring a hosted service.
- Recommendation: separate immutable safety policy from evolvable planning/worker policies. Consequence: future self-improvement experiments cannot weaken approval, permission or final acceptance gates.
- Recommendation: evaluate each added skill or sub-agent by paired task outcomes and token/latency cost. Consequence: avoids growing prompt overhead without demonstrated utility.
- Assumption: Codex Hook semantics and plugin schemas may evolve; compatibility must be version-tested rather than inferred from current tests alone.

## Questions requiring user decision

- No decision is required to accept this analysis. A future implementation phase would require choosing whether the next release prioritizes reliability foundations or multi-Agent capability. Recommended default: reliability foundations first, because they are prerequisites for safe concurrency and self-evolution.

## Approved design

The proposed evolution keeps Goal Flow as a deterministic control plane around a capable coding agent. It adds telemetry, reproducibility, concurrency safety and measurable evaluation before optional evaluator/worker orchestration. This proposal is awaiting explicit user approval before any implementation.

### Prioritized optimization roadmap

#### P0 — Reliability foundations

1. Add file locking plus compare-and-swap revision checks around all state transitions; enforce recorded branch/worktree identity.
2. Run verifiers in a process group and terminate descendants on timeout; record timeout, signal and artifact changes.
3. Add command risk metadata (`read`, `build`, `network`, `destructive`) and require explicit approval/sandbox policy for elevated categories.
4. Record an environment manifest: OS/arch, runtime/tool versions, dependency lock digests, selected non-secret environment names and external dependency identifiers.
5. Add schema migration commands and backward/forward compatibility tests for `.goal-flow` state.

Success measures: zero lost updates in concurrency tests; zero orphan verifier processes; receipts reproducible in a clean worktree; upgrade/downgrade fixtures pass.

#### P1 — Observability and evaluation

1. Add append-only `events.jsonl` with run/attempt/epoch IDs, state transitions, tool/check timings, retry class, context-reset marker and redacted metadata.
2. Add `goalctl report` to render timeline, requirement coverage, critical path, cost/latency when available, and residual risk.
3. Build a 20-50 task internal benchmark with paired baseline-vs-Goal-Flow runs, fixed repositories, acceptance tests and labels for success, human interventions, wall time, token cost and regressions.
4. Calibrate assurance only after enough held-out outcomes; otherwise retain `UNCALIBRATED`.

Success measures: complete event reconstruction; no secret leakage fixtures; statistically reported paired deltas rather than anecdotal wins.

#### P2 — Better long-horizon control

1. Represent milestones as a dependency DAG with status, owner/lease, verifier set, retry budget and handoff summary.
2. Add explicit context-reset checkpoints and a machine-generated “next session packet” containing decisions, changed files, failed hypotheses and next action.
3. Replace the three-fingerprint stall rule with classified retry budgets and strategy-change evidence.
4. Add optional independent evaluator mode that can inspect and record findings but cannot mutate product files or weaken the contract.

Success measures: lower repeated-action rate; faster recovery after context reset; evaluator finds seeded defects without increasing false blocks beyond a defined threshold.

#### P3 — Selective multi-Agent and controlled evolution

1. Add manager-style bounded workers only for independent research, test design and review, using isolated worktrees and a single-writer merge protocol.
2. Introduce policy/skill selection based on task type and prior measured utility, with version pinning and rollback.
3. Experiment offline with scaffold mutation or evolutionary search against held-out tasks; promotion requires external immutable gates, reproducible gains and human review.

Success measures: multi-Agent variants outperform single-agent baseline on selected task classes after cost normalization; no policy promotion without held-out improvement.

## Acceptance dimensions

| Dimension | COVERED or N_A | Rationale | Criterion IDs |
| --- | --- | --- | --- |
| functional | COVERED | 项目定位、机制、场景、对照和路线图均由明确的分析验收标准覆盖。 | REQ-ANALYSIS-01, REQ-TREND-02, REQ-ROADMAP-03 |
| negative-boundary | COVERED | 报告必须区分控制器强制能力、Skill 行为约束与未覆盖的信任边界。 | REQ-ANALYSIS-01 |
| regression-compatibility | COVERED | 当前 31 个回归测试必须继续通过，以证明分析基于可工作的仓库基线。 | REQ-ANALYSIS-01 |
| security-privacy | COVERED | 路线图必须覆盖 shell 验证器、权限边界、日志脱敏和自演化安全门。 | REQ-ROADMAP-03 |
| performance-reliability | COVERED | 路线图必须包含并发、超时、环境复现、成本和长任务成功率指标。 | REQ-ROADMAP-03 |
| operations-observability | COVERED | 路线图必须包含事件日志、运行标识、时间线和可审计报告能力。 | REQ-ROADMAP-03 |
| migration-rollback | N_A | 本目标不修改业务实现或状态 schema，因此不存在本轮迁移与回滚操作。 | - |
| documentation-deliverables | COVERED | 最终交付必须包含证据来源、结论、优缺点、趋势对照和分级路线图。 | REQ-ANALYSIS-01, REQ-TREND-02, REQ-ROADMAP-03 |

## Acceptance criteria

| ID | Kind | Observable outcome | What evidence proves | Negative or boundary cases | Basis | Verifier |
| --- | --- | --- | --- | --- | --- | --- |
| REQ-ANALYSIS-01 | MUST | 分析文档准确覆盖当前项目架构、关键状态机、使用边界、测试基线与已验证局限。 | 仓库证据检查证明当前实现仍通过现有回归套件，且报告结构完整并引用关键实现文件。 | 若只复述 README 而未核对控制器、Hook 和测试，项目能力判断可能失真。；若把 Skill 约束误述为控制器强制能力，报告会高估确定性保证。 | README.md、docs/design.md、goalctl.py、hooks 与 tests 的当前仓库证据 | TESTS, REPORT-CONTRACT |
| REQ-TREND-02 | MUST | 分析文档将当前项目与单 Agent 循环、结构化交接、评估器分离、多 Agent 编排、可观测性和自演化方向进行有来源的对照。 | 结构检查证明所有对照维度和一手来源被显式纳入；观点正确性仍需用户审阅。 | 若依赖过时或二手资料，趋势判断可能失真。；若把多 Agent 或自演化视为默认答案，会忽略复杂度、成本和安全门。 | 截至 2026-07-30 检索的 OpenAI、Anthropic、METR 与原始论文 | REPORT-CONTRACT |
| REQ-ROADMAP-03 | MUST | 报告给出按 P0 至 P3 排序的优化路线，每阶段包含目标、取舍、风险和可测成功指标。 | 结构检查证明路线图、优先级和成功指标完整存在；商业优先级仍由用户决定。 | 若先做多 Agent 而没有锁、追踪和环境复现，故障面会扩大。；若没有配对评测，新增机制可能只增加 token、时延与维护成本。 | 当前代码缺口、主流 Agent 工程实践与用户要求的可优化点 | REPORT-CONTRACT |

Required check TESTS: `python3 -m unittest discover -s tests -v`

Required check REPORT-CONTRACT: `python3 -c 'from pathlib import Path; t=Path(".goal-flow/analyze-project-evolution/goal.md").read_text(); required=["## Current project analysis","## Strengths","## Weaknesses and risks","## Comparison with mainstream long-task strategies","## Agent evolution direction","### Prioritized optimization roadmap","REQ-ANALYSIS-01","REQ-TREND-02","REQ-ROADMAP-03","https://metr.org/time-horizons/"]; raise SystemExit(0 if all(x in t for x in required) else 1)'`

## Milestones

1. M1 Analysis baseline: inspect repository, tests, hooks, controller, docs and history; run current regression suite.
2. M2 External comparison: compare current design with current primary sources and research on long-running agents.
3. M3 Decision-ready roadmap: rank improvements by prerequisite, expected value, risk and measurable validation.
4. M4 User decision: present the analysis and await approval only if implementation is desired.

## Risks, migration, and rollback

- External research, especially 2026 preprints, may change; source dates and preliminary status are explicit.
- The repository's 31 passing tests validate current encoded behavior, not real-world long-task success.
- Static report checks prove presence and regression health, not semantic correctness; final interpretation remains subject to user review.
- This planning-only change is confined to `.goal-flow/`; it can be removed without affecting product behavior if the user cancels the goal.

## Approval

- Revision: 1
- Status: PENDING
- Approved by: pending
