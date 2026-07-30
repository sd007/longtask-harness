# Planning Protocol

Use this protocol before implementation.

## Required design content

Keep `goal.md` concise but decision-complete:

1. Outcome and non-goals.
2. Repository and business context.
3. Relevant official or industry sources, including version or retrieval date.
4. Proposed design and meaningful alternatives.
5. Public interfaces, data changes, compatibility, migration, and rollback.
6. Security, performance, observability, and operational effects when relevant.
7. `MUST` requirements with stable IDs.
8. Verification method for every `MUST` requirement.
9. Milestones and Git checkpoint boundaries.
10. Assumptions, open questions, and authorization boundaries.

## Discussion gate

Ask only questions that materially change the outcome or design. Resolve repository facts by inspection. Present tradeoffs with a recommendation. Continue until the user explicitly approves.

Treat approval as applying to one exact `goal.md` revision plus its registered requirement and check definitions. A later material change invalidates approval and requires `replan`.

## Requirement quality

Write requirements as observable outcomes, not activities:

- Good: `REQ-API-01: Retrying the same idempotency key creates at most one order.`
- Bad: `Implement retry handling.`

Classify requirements as `must` or `should`. Give each MUST requirement one or more named `verified_by` checks. Register every exact required check command while planning; because the controller will execute it later, the command and timeout are part of what the user approves. A MUST requirement must have direct, reproducible evidence on the tested implementation SHA before delivery.

## Environment baseline

Before coding, determine:

- Git branch, worktree, and existing user changes.
- Runtime and dependency versions.
- Build, test, lint, type-check, and end-to-end commands.
- Required services, credentials, network access, and approvals.
- Existing failing or flaky checks.

Record baseline failures separately from regressions caused by the task.
