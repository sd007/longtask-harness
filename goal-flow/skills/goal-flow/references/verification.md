# Evidence and Delivery Protocol

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

Check evidence must be a controller-generated execution receipt, not an Agent-authored PASS statement. A VERIFIED requirement must reference its approved passing checks. Evidence is bound to the tested implementation SHA. Later commits may update only `.goal-flow/` audit files; any other change makes the evidence stale and requires checks to be rerun. Lightweight Standard additionally protects its initialization product fingerprint, so pre-existing dirty files may remain but newly introduced drift does not pass verification.

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

## Assurance

Report:

- requirement coverage
- required-check coverage
- unresolved high or critical risks
- `HIGH`, `MEDIUM`, or `LOW` assurance
- `UNCALIBRATED` confidence until real historical outcomes support probability calibration

A high score never overrides a missing `MUST` requirement.

A mitigated risk is resolved only while its bound controller checks remain fresh. High or critical risks without such receipts block delivery. A user-accepted serious residual risk does not block the Gate, but prevents `HIGH` assurance.

## Delivery package

Provide:

- final Git SHA and implementation summary
- requirement-by-requirement evidence
- commands and results used for verification
- reviewer findings and their disposition
- known limitations and residual risks
- migration, deployment, rollback, and user acceptance steps when relevant

Only the user can accept the delivery.
