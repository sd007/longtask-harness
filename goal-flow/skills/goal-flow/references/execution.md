# Autonomous Execution Protocol

## Epoch rule

Make each epoch answer one question: what is the largest unsatisfied approved acceptance criterion that can be closed and verified now?

An epoch ends as one of:

- `PROGRESSED`: implementation or evidence materially improved.
- `FAILED_WITH_NEW_EVIDENCE`: failure produced a new root-cause signal or invalidated assumption.
- `WAIT`: user input, permission, or an external dependency is required.
- `MILESTONE_VERIFIED`: milestone checks pass and a coherent commit exists.

Do not repeat a failed strategy without new evidence. Use `--progress` only when the observable state improved; otherwise use `--no-progress`. Three unchanged Stop gates persist `BLOCKED` with a visible reason.

## Git discipline

- Preserve pre-existing user changes.
- Prefer one writer per worktree.
- Use subagents for bounded research, test design, and independent review; treat their output as unverified.
- Commit approved design before implementation.
- Run preflight checks, then commit a coherent implementation candidate so controller-generated receipts can bind to its SHA.
- Write commit subjects in the current conversation language unless the repository has an explicit commit-language convention. Preserve an existing Conventional Commit prefix such as `feat:` or `fix:` and localize the descriptive text; do not silently default a Chinese task to an English sentence.
- If a frozen check fails, fix the defect and create a new implementation commit; never attach the old PASS to the new tree.
- Inspect the diff before every commit.
- Never use Git history as proof that behavior is correct.

Execute frozen check definitions with `goalctl.py verify`; do not use `record check` to claim PASS or FAIL. The controller captures the real exit code, output digest, and exact implementation Git SHA. Later audit-only commits may change `.goal-flow/`; any other change makes the check receipt stale.

## Drift control

At the start and end of every epoch compare the diff with the approved `goal.md`.

Trace every implementation change to one or more approved acceptance criteria. Work that satisfies none is out of scope unless it is a necessary enabler recorded in the milestone.

Replan when changing the core outcome, scope, architecture, public contract, quality threshold, risk, or authorization boundary. Local implementation choices that preserve those constraints do not require user interruption.

Do not make progress by deleting requirements, weakening tests, adding skips, replacing real integration with mocks, or hiding counter-evidence.

## Failure handling

Classify failures before changing code:

- implementation defect
- invalid design assumption
- pre-existing repository failure
- environment or dependency failure
- flaky verifier
- missing permission or external input

Record the observation, changed hypothesis, and next strategy. Block rather than thrash when no new evidence is available.
