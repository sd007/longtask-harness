---
name: goal-flow
description: Run long software-development goals in Codex from design approval through autonomous implementation, verification, milestone commits, recovery, and evidence-backed delivery. Use when a user asks Codex to own a multi-step coding task, continue until a reliable result, avoid requirement drift, or resume an active goal-flow run.
---

# Goal Flow

Treat the approved outcome as the source of truth. Keep working until the result is ready for user acceptance or a real wait condition exists.

## Resolve the controller

Resolve this `SKILL.md` directory and set:

```text
GOAL_FLOW_CLI = <skill-directory>/scripts/goalctl.py
```

Run controller commands as:

```text
python3 GOAL_FLOW_CLI --root <repository-root> <command>
```

Do not edit `state.json` directly. Use the controller.

## Start or resume

1. Run `status`.
2. If an active goal exists, read its `goal.md`, `state.json`, `evidence.md`, and current Git state. Resume the recorded `next_action`.
3. Otherwise run `init --goal-id <slug> --title <title> --goal <outcome>`.
4. Read [planning.md](references/planning.md) completely and conduct the design phase.

## Design before implementation

Inspect the repository, `AGENTS.md`, existing behavior, tests, relevant official documentation, constraints, risks, migration needs, and rollback path. Turn the request into explicit `MUST` requirements and verifiers.

Discuss material choices with the user until they explicitly approve the design. Before approval:

- Do not change implementation code.
- Do not weaken the requested outcome to make it easier.
- Keep unresolved assumptions visible.

When the user says the proposed design is ready to approve:

1. Finish `goal.md`.
2. Register every requirement as `UNVERIFIED` with one or more `--verified-by <check-id>` values.
3. Register each exact verifier command as a `PENDING` check. At least one check must be `--required`; these commands are part of the contract the user is approving.
4. Only after the user's explicit approval, run `approve --user-approved --approved-by <identity> --next-action <first milestone action>`.
5. Create or use an isolated `codex/goal-flow-<slug>` branch or worktree while preserving user changes.
6. Commit the approved design checkpoint.

## Execute autonomous epochs

Read [execution.md](references/execution.md) before coding. Repeat:

1. **Sense:** Read the approved goal revision, state, evidence, Git diff, and fresh tool output.
2. **Select:** Choose the largest currently verifiable delivery gap.
3. **Act:** Implement one bounded milestone without unrelated refactoring.
4. **Preflight:** Run targeted checks directly, inspect the diff, and test negative paths while the implementation is still editable.
5. **Commit:** Commit the coherent implementation candidate so evidence can bind to an immutable SHA.
6. **Verify:** Run approved checks through `verify --id <check-id>`. The controller executes the frozen command and records its exit code, output digest, and tested Git SHA. If one fails, fix and create a new implementation commit. Add a verifier only through `replan`.
7. **Record:** Mark requirements `VERIFIED` only after all their approved `verified_by` checks have fresh PASS receipts. Record risks and counter-evidence, then commit the `.goal-flow/` audit update separately.
8. **Gate:** Run `gate --apply` and follow its `next_action`.

Do not stop merely because a checklist is exhausted. Stop only when the Gate returns `WAIT`, `READY_FOR_REVIEW`, or the user pauses or cancels.

If a material requirement, architecture, public interface, quality threshold, permission, or irreversible action must change, run `replan`, explain the change, and obtain approval for the new revision.

## Verify before delivery

Read [verification.md](references/verification.md) completely before final review.

- Re-run required checks against the current Git SHA.
- Reconstruct coverage from the approved requirements rather than the worker summary.
- Use a fresh-context reviewer for substantial changes when available.
- Treat subagent reports as candidate findings, never as proof.
- Preserve counter-evidence and residual risks.
- Mark a risk `MITIGATED` only with non-empty evidence and fresh controller PASS receipts via `--verified-by`; otherwise keep it `OPEN` and replan if a new verifier is needed.
- Never mark a risk `ACCEPTED` unless the user explicitly accepts it; record their identity with `--accepted-by`.
- Do not claim a probability when confidence is `UNCALIBRATED`.

Only present `READY_FOR_ACCEPTANCE` after `gate --apply` succeeds. Evidence remains current across commits that change only `.goal-flow/`; any product-tree change invalidates it. The user, not the agent, decides acceptance. Run `accept --user-accepted --accepted-by <identity>` only after the user explicitly accepts; otherwise use `reject` with their reason.

## Control commands

Use these commands instead of inventing state transitions:

```text
status
update --status EXECUTING --milestone M2 --next-action "..." --progress
verify --id TEST
pause --reason "..."
resume
block --reason "..."
replan --reason "..."
gate --apply
accept --user-accepted --accepted-by "user"
reject --reason "..."
cancel --reason "..."
```

Never push, merge, deploy, spend money, modify production data, or perform another irreversible external action without explicit authorization.
