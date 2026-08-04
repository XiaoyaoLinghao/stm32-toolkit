# STM32 Toolkit Agent Instructions

## Codex/OpenClaw ownership

Git commits are the only cross-machine source of truth. Codex owns architecture, module work orders, review, and acceptance. OpenClaw owns product implementation and implementation tests. The user authorizes every push, PR mutation, merge, closure, and remote branch deletion.

An explicit bounded Codex correction applies only to the named files and behavior and expires after verification. “Continue,” urgency, defect size, or prior approval does not transfer implementation ownership.

Before acting, reconstruct this ledger: module and phase, full accepted-base SHA, specification owner, implementer, reviewer, active branch/PR, exact remote action authorized, and any bounded override. On an ownership change, audit tracked/untracked, committed/uncommitted, and pushed/unpushed state before exposing or discarding anything.

## Repository contract

- Repository: `https://github.com/XiaoyaoLinghao/stm32-toolkit.git`.
- Default branch: `master`.
- OpenClaw branches: `openclaw/{MODULE-ID}/{ATTEMPT}`; first attempt is `r001`.
- Work orders: `docs/openclaw/modules/{MODULE-ID}-*.md`.
- Reports: `docs/openclaw/returns/{MODULE-ID}/{ATTEMPT}-implementation-report.md`.
- Report template: `docs/openclaw/returns/implementation-report-template.md`.
- Architecture: `docs/superpowers/specs/2026-07-29-stm32-toolkit-ai-development-design.md`.
- Roadmap: `docs/superpowers/plans/2026-08-04-stm32-toolkit-complete-development-roadmap.md`.

Never accept, repeat, retain, or commit plaintext credentials. Commit identity is not proof of GitHub authentication; verify each computer independently. Preserve unrelated changes and use a clean isolated worktree at the exact remote SHA for every implementation review.

## Delivery workflow

1. Codex writes one self-contained work order with a remotely visible full accepted-base SHA and an environment evidence matrix.
2. The user dispatches repository URL, module ID, and accepted base; OpenClaw follows `OPENCLAW_START_HERE.md`.
3. OpenClaw implements and tests on one `r001` branch, pushes only that branch, and returns one PR or compare URL targeting `master`.
4. Codex fetches read-only, reviews the complete accepted-base-to-final-head diff in a clean worktree, runs its assigned gates, reconciles the report, and issues one verdict.
5. `REVISION_REQUIRED` remains on the same branch and PR. A new attempt is allowed only after `REWRITE_REQUIRED` or an explicit replacement decision.

Do not add collaboration apps, manifests, validators, CI, or dispatch automation unless the user explicitly assigns that tooling as product scope.

## Evidence and report rules

Every work order specifies exact paths/contracts and names the evidence owner and required environment for each gate. `PASS` means that owner ran the gate against the returned commit. A platform-only gate may be `DEFERRED` only to the named later owner; a pure code failure is never deferred. Do not invent target facts or attribute another actor’s evidence to OpenClaw.

The tracked implementation report records the accepted base and the code head before the report commit. It must not contain its own final commit SHA or moving commit totals. The return message and PR metadata provide the final remote head.

## Review outcomes

- `ACCEPTED`: all required non-deferred gates pass.
- `ACCEPTED_WITH_FIXES`: Codex applied only a user-authorized bounded correction and verified it.
- `REVISION_REQUIRED`: correctable issues remain on the same attempt branch and PR.
- `REWRITE_REQUIRED`: architecture, safety, scope, or coverage requires a replacement attempt.

Every issue cites path, observed behavior, expected behavior, evidence, and verification command. GitHub approval, merge, close, push, or deletion is never implicit.
