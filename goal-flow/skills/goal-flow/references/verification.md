# Evidence and Delivery Protocol

This is Phase 3 of the single Goal Flow. Its context is the approved contract, final diff and Git SHA, current receipts, counter-evidence, residual risk, and user-visible outcome. Reconstruct coverage independently instead of accepting the implementation phase's completion narrative.

## Evidence rule

Every acceptance-criterion claim must identify:

- requirement ID
- current goal revision
- current Git SHA
- exact verifier or observation
- what the evidence proves
- which planned negative or boundary cases were exercised
- remaining counter-evidence or risk

Use these statuses:

- `VERIFIED`: direct, reproducible evidence supports the requirement.
- `PARTIAL`: only part of the requirement is demonstrated.
- `UNVERIFIED`: no sufficient current evidence exists.
- `CONTRADICTED`: current evidence shows the requirement is not met.

Check evidence must be a controller-generated execution receipt, not an Agent-authored PASS statement. Each check states `mock`, `simulated`, or `real`, the requirements it covers, what it proves, and its limitations. Freshness is a structured result with a reason, exact invalidating paths, and evidence SHA. Later commits may update only `.goal-flow/`; any other change makes evidence stale and effective status becomes `VERIFYING`.

## Verification ladder

Use the strongest applicable combination:

1. Static checks and type checks.
2. Unit and integration tests.
3. Black-box or browser end-to-end behavior.
4. Negative, boundary, retry, concurrency, and recovery scenarios.
5. Existing full regression suite.
6. Fresh-context review against the approved goal.
7. Clean product-tree reproduction on the tested implementation SHA.
8. User acceptance.

Do not extrapolate beyond the actual scope of a verifier.

## Classic product scenario set

Acceptance should be small but product-shaped. Select the 3–5 scenarios most likely to expose an expensive or hidden defect:

- the real user main path;
- the most important business boundary;
- the primary dependency failure, retry, or recovery path;
- the existing behavior most likely to regress;
- one performance smoke or explicit budget for latency, throughput, memory, or concurrency.

Do not require every category when it is immaterial. A performance `N_A` needs a concrete reason; a material performance concern needs a threshold and current-SHA evidence. Also recheck the implementation fidelity findings so passing tests do not hide a one-off architecture, hard-coded shortcut, or broken extension point.

## Assurance

Report:

- requirement coverage
- required-check coverage
- unresolved high or critical risks
- `HIGH`, `MEDIUM`, or `LOW` assurance
- `UNCALIBRATED` confidence until real historical outcomes support probability calibration

A high score never overrides a missing `MUST` requirement.

Risk states are `OPEN`, `PARTIALLY_MITIGATED`, `MITIGATED`, and user-approved `ACCEPTED`. Evidence below the declared minimum is at most partial. High or critical OPEN/PARTIAL risks block delivery; medium/low residual risks permit review but cap assurance below HIGH.

## Delivery package

Provide the conclusion under four headings: proved, partially proved, not proved, and residual risks. Also provide:

- final Git SHA and implementation summary
- requirement-by-requirement evidence
- commands and results used for verification
- reviewer findings and their disposition
- known limitations and residual risks
- migration, deployment, rollback, and user acceptance steps when relevant

Only the user can accept the delivery.

Requested corrections that preserve the design return to implementation and require fresh evidence. A failed approved assumption, changed public behavior, or changed architecture returns to analysis/design and requires a new revision and approval.
