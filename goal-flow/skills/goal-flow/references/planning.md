# Planning and Acceptance Protocol

Complete the appropriate depth of this protocol before implementation. Full Goal Flow and strict tasks use the complete contract; lightweight Standard tasks use the reduced contract described below.

## Infer before asking

Build the first complete proposal yourself:

1. Inspect `AGENTS.md`, code, tests, history, configuration, schemas, interfaces, and existing failures.
2. Retrieve relevant official documentation and domain standards when repository evidence is insufficient.
3. Infer implicit expectations from adjacent behavior: compatibility, error handling, security, reliability, operations, migration, rollback, and deliverables.
4. Record each inference with its basis and expose material assumptions in `goal.md`.
5. Ask the user only when the answer is a business preference, changes scope or public behavior, authorizes risk or irreversible action, or cannot be resolved from available evidence.

For unresolved questions, give a recommended default and its consequence. Batch only related, high-impact questions. Do not ask the user to discover repository facts Codex can inspect.

## Decision check before approval

After repository and domain investigation, always show a compact decision check before asking for approval:

| Section | Meaning |
| --- | --- |
| 已自动确定 | Choices resolved from repository, domain, or official evidence. |
| 建议默认 | Reversible choices where the recommended option is good enough to proceed. |
| 仍需用户决定 | Choices that cannot be inferred and would change outcome, public behavior, quality threshold, authorization, or irreversible risk. |

If `仍需用户决定` is non-empty, stop and ask those questions with a recommended default and consequence. If it is empty, explicitly state that no high-impact user decision remains; do not manufacture a question merely to satisfy the protocol.

## Make the plan decision-complete

Include in `goal.md`:

1. Outcome, non-goals, and measurable quality bar.
2. Repository, business, and domain context with sources or retrieval dates.
3. Assumptions, decisions, alternatives, and why the recommendation wins.
4. Interfaces, data changes, compatibility, security, performance, observability, migration, and rollback where applicable.
5. Stable acceptance criteria and their exact verifier commands.
6. Milestones and Git checkpoint boundaries.
7. Remaining questions that genuinely require a user decision.

Never place secret values in `goal.md` or verifier commands. Refer to environment-variable names or credential mechanisms and request authorization only when execution actually needs them.

## Assess the selected profile

Use the lightweight `standard` Harness for normal day-to-day repository work and `strict` when security, migration, production reliability, irreversible actions, or similarly costly failure modes are material. Full `goal-flow` keeps explicit approval and the complete evidence contract; lightweight standard work may use implicit approval when no high-impact question remains.

For lightweight `standard`, assess `functional`, define one observable MUST criterion, and register one required controller check. Its MUST needs an outcome and a verifier, but not a full evidence-scope, failure-mode, or basis narrative unless the task makes those material. Full `goal-flow` standard additionally assesses the other three core dimensions. For `strict`, continue through the full list. Record each required dimension as `COVERED` with linked criterion IDs, or `N_A` with a substantive rationale:

- `functional`
- `negative-boundary`
- `regression-compatibility`
- `documentation-deliverables`

Strict additionally requires:

- `security-privacy`
- `performance-reliability`
- `operations-observability`
- `migration-rollback`

`N_A` means evidence shows the dimension is immaterial, not that it was forgotten.

## Write acceptance criteria, not activities

Every MUST criterion must include:

- a stable ID and observable outcome
- what the cited evidence will and will not prove
- negative, boundary, recovery, or failure cases
- repository, domain, official-source, or explicit-user basis
- one or more required controller checks

Good: `REQ-API-01: Retrying the same idempotency key creates at most one order.`

Bad: `Implement retry handling.`

Prefer black-box outcomes over implementation details. Include tolerances or thresholds in the observable outcome when they matter. A test name alone is not an acceptance criterion.

## Run the planning gate

Register the criteria, checks, and dimensions, then run `plan-check`. Resolve every reported gap yourself when evidence permits. Present the plan to the user only after it returns `READY_FOR_APPROVAL`.

User approval freezes the exact `goal.md`, criteria definitions, evidence scope, failure modes, basis, dimension assessment, verifier mapping, and check commands. When the bundled `goal_flow_approval` MCP tool is available, use its `elicitation/create` request so the host can render `批准并执行` and `修改方案`; a declined or cancelled request must not run a controller transition. Any material change requires `replan` and new approval. In hosts without MCP elicitation, retain the natural-language fallback without requiring a fixed phrase.

## Baseline the environment

Before coding, determine Git/worktree state, runtime and dependency versions, test commands, required services and permissions, and existing failing or flaky checks. Record baseline failures separately from task regressions.
