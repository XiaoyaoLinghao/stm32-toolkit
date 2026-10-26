# v1.3.2 candidate-specific authorization

On 2026-10-26 the user explicitly answered: “仅对此 v1.3.2 候选批准例外并发布 Latest”.
This authorizes **USER_APPROVED_EXCEPTION** and publication as Latest only for
frozen source `acb71b9f39e8ae4799179b0cab088245c0a5ea5b`, whose 13 files passed
independent double-build and official bundle verification. Windows ZIP SHA-256:
`1773a5e6b61a882bbd3d77a2a23902bd24f88ed296fb6e12dfccc03594c77f79`,
113,770,074 bytes. See [candidate evidence](candidate-build.md).

The approved disclosed limits are Toolkit overall 15381/17618 = 87.3028% and
risk-core-v2 14310/16354 = 87.5015% below the 90% floors; Monitor risk-core-v2
3227/3498 = 92.2527% below 95%; retained platform/historical-data skips; and
explicit source-bound reuse rather than a single final-head full rerun.
Original failures and successful corrections remain retained. These unmet
numeric gates are not relabeled PASS and permanent membership/floors do not change.

Final actual installation and VS Code validation remain user-owned and
**USER_VALIDATION_PENDING**. The user has not authorized original firmware-project
changes or hardware access. This exception does not transfer to another candidate.

Ownership ledger: module STM32TK-132, publication phase; overall accepted base
`cb2a1d2c78fcc4a5c886e77fb06d0ac01eddbab5`; primary specification/orchestration,
independent complete-diff review and release execution; local Claude CLI
implementation/tests using the user's existing provider; branch
`codex/v132-guidance`, no PR. Source report head before this record is
`78f78e2c208e14f8e6761c39c4e366b50f811f4e`.

Authorized remote scope: preserve full history with a non-forced push to master,
create annotated v1.3.2 at the frozen source, upload exactly the verified 13 files,
publish that release as Latest, verify anonymous downloads, and push the associated
truthful publication documentation. Frozen artifacts are not rebuilt for later
evidence-only documentation. No remote action is claimed completed by this record.
