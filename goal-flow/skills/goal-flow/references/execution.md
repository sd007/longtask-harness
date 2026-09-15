# Autonomous Execution Protocol

This is Phase 2 of the single Goal Flow. Start from the approved outcome, accepted diagram semantics when present, relevant code/tests, current milestone, and fresh targeted outputs. Do not reinterpret discarded design alternatives as requirements.

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
- Run preflight checks, then commit a coherent implementation candidate so controller-generated receipts can bind to its SHA. Standard may retain unrelated initialization-baseline edits, but must not introduce additional uncommitted product changes before verification.
- Write commit subjects in the current conversation language unless the repository has an explicit commit-language convention. Preserve an existing Conventional Commit prefix such as `feat:` or `fix:` and localize the descriptive text; do not silently default a Chinese task to an English sentence. The subject should identify the changed object and core behavior change, not just say “update”, “fix”, or “完成”. When that is not enough, add a short body covering the purpose, important boundary, and verification result. Do not rewrite existing history solely to improve wording.
- If a frozen check fails, fix the defect and create a new implementation commit; never attach the old PASS to the new tree.
- Inspect the diff before every commit.
- Never use Git history as proof that behavior is correct.

Execute frozen check definitions with `goalctl.py verify`; do not use `record check` to claim PASS or FAIL. The controller captures the real exit code, output digest, and exact implementation Git SHA. Later audit-only commits may change `.goal-flow/`; any other change makes the check receipt stale.

## Drift control

At the start and end of every epoch compare the diff with the approved `goal.md`.

Trace every implementation change to one or more approved acceptance criteria. Work that satisfies none is out of scope unless it is a necessary enabler recorded in the milestone.

Replan when changing the core outcome, scope, architecture, public contract, quality threshold, risk, or authorization boundary. Local implementation choices that preserve those constraints do not require user interruption.

An implementation defect stays in this phase. Evidence that an approved assumption or architecture is wrong returns the whole flow to analysis/design through `replan`; update the diagram and contract and obtain approval again. Draw.io geometry and styling are presentation-only, while changed nodes, labels, connections, pages, or semantic metadata are contract changes.

Do not make progress by deleting requirements, weakening tests, adding skips, replacing real integration with mocks, or hiding counter-evidence.

## Implementation fidelity review

Before the implementation milestone is complete, inspect the final diff against the approved solution and answer five questions:

1. Does the real user trigger traverse the intended main path to the observable result?
2. Do module responsibilities and dependency direction still match the approved boundaries?
3. Do interfaces preserve the agreed inputs, outputs, errors, compatibility, and failure behavior?
4. Did temporary mocks, hard-coded values, bypasses, global state, or unexplained TODOs enter the product path?
5. Can the approved likely next change be absorbed by the named extension point without rewriting the core flow?

Record actionable defects as implementation work and fix them in this phase. Keep the review concise; it is a solution-to-code comparison, not a separate architecture specification.

## Failure handling

Classify failures before changing code:

- implementation defect
- invalid design assumption
- pre-existing repository failure
- environment or dependency failure
- flaky verifier
- missing permission or external input

Record the observation, changed hypothesis, and next strategy. `goalctl verify` provides a deterministic first classification and recommended action; treat it as a triage hint, then confirm against the actual output. Block rather than thrash when no new evidence is available. Upgrade the Harness or run `replan` when the failure changes the risk, scope, or authorization boundary.
