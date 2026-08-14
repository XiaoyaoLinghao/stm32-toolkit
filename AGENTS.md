# STM32 Toolkit Agent Instructions

## Codex ownership

Git commits are the only durable source of truth. Codex and its local derived agents own architecture, specifications, implementation, implementation tests, review, and acceptance. Do not dispatch product work to OpenClaw or another external AI cluster. Historical OpenClaw documents and reports remain historical evidence only and do not grant current ownership.

The user authorizes every push, PR mutation, merge, closure, tag, and remote branch deletion. Local implementation and verification do not imply any remote authority.

Before acting, reconstruct this ledger: module and phase, full accepted-base SHA, specification owner, implementer, reviewer, active branch/PR, exact remote action authorized, and any bounded override. On an ownership change, audit tracked/untracked, committed/uncommitted, and pushed/unpushed state before exposing or discarding anything.

## Repository contract

- Repository: `https://github.com/XiaoyaoLinghao/stm32-toolkit.git`.
- Default branch: `master`.
- Codex branches: `codex/{MODULE-ID}` unless the user names another branch.
- Current reports: `docs/codex/returns/{MODULE-ID}/implementation-report.md`.
- `docs/openclaw/` contains historical collaboration records and is not the destination for new work.
- Architecture: `docs/superpowers/specs/2026-07-29-stm32-toolkit-ai-development-design.md`.
- Roadmap: `docs/superpowers/plans/2026-08-04-stm32-toolkit-complete-development-roadmap.md`.

Never accept, repeat, retain, or commit plaintext credentials. Commit identity is not proof of GitHub authentication; verify each computer independently. Preserve unrelated changes and review in a clean isolated worktree at the exact reviewed CodeHead/final head, using the accepted base only as the diff origin.

## Delivery workflow

1. Codex freezes a self-contained specification and implementation plan at a full accepted-base SHA with an environment evidence matrix.
2. Codex implements locally on one `codex/{MODULE-ID}` branch. Derived agents may own disjoint tasks, but the primary Codex agent integrates their changes and remains accountable for the complete result.
3. Task-local tests run during implementation. Candidate and final evidence run only against a frozen CodeHead in clean isolated worktrees.
4. Codex reviews the complete accepted-base-to-CodeHead diff, reconciles retained evidence, and records one verdict. A report-only commit may be created only after every gate assigned to that report phase passes; a later hardware phase may remain pending only when the frozen specification explicitly permits it. The report commit must not repair product or test code.
5. Any push, PR, merge, tag, closure, or remote deletion stops for a new explicit user authorization.

Do not add collaboration apps, manifests, validators, CI, or dispatch automation unless the user explicitly assigns that tooling as product scope.

## Evidence and report rules

Every plan specifies exact paths/contracts and names the evidence owner and required environment for each gate. `PASS` means that owner ran the gate against the recorded commit. A platform-only gate may be `DEFERRED` only to a named later phase or owner; a pure code failure is never deferred. Do not invent target facts or attribute one agent's evidence to another owner.

The tracked implementation report records the accepted base and the CodeHead before the report commit. It must not contain its own final commit SHA or moving commit totals. Local Git evidence records the report commit; any later remote identity is reported only after an authorized remote action.

## Review outcomes

- `ACCEPTED`: all required non-deferred gates pass.
- `SOFTWARE_COMPLETE_HARDWARE_PENDING`: all required software gates pass, but a named mandatory hardware matrix remains outstanding; this is not release acceptance.
- `ACCEPTED_WITH_FIXES`: an explicitly bounded correction was applied and verified before the final CodeHead freeze.
- `REVISION_REQUIRED`: correctable issues remain on the same module branch.
- `REWRITE_REQUIRED`: architecture, safety, scope, or coverage requires a replacement implementation.

Every issue cites path, observed behavior, expected behavior, evidence, and verification command. GitHub approval, merge, close, push, tag, or deletion is never implicit.
