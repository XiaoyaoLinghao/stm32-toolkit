# STM32 Toolkit Agent Instructions

## OpenClaw collaboration model

This project uses an external OpenClaw agent cluster for product implementation and testing.

Codex is the architecture owner, work-order author, acceptance owner, and code reviewer. OpenClaw owns product-code and product-test implementation. Unless the user explicitly authorizes Codex to implement a specific bounded change, use this workflow:

1. Codex writes one self-contained module work order under `docs/openclaw/modules/`.
2. The user gives OpenClaw the repository URL and module ID; OpenClaw follows `OPENCLAW_START_HERE.md`.
3. OpenClaw implements and tests on `openclaw/{MODULE-ID}/r001`, pushes that branch, and returns a PR or compare URL targeting `master`.
4. Codex fetches and reviews the complete diff, runs proportionate tests, and checks the result against the approved work order.
5. OpenClaw corrects rejected work on the same branch after `REVISION_REQUIRED`. Codex may make a correction only when the user explicitly authorizes that exact bounded correction.

Urgency, “continue,” or a small defect does not grant Codex implementation authority. Do not add collaboration scripts, validators, manifests, CI, or dispatch tooling unless the user explicitly assigns that tooling as product scope.

## Repository boundaries

- Default branch: `master`.
- OpenClaw branches: `openclaw/{MODULE-ID}/{ATTEMPT}`; first attempt is `r001`.
- Work orders: `docs/openclaw/modules/{MODULE-ID}-*.md`.
- Return reports: `docs/openclaw/returns/{MODULE-ID}/{ATTEMPT}-implementation-report.md`.
- Report template: `docs/openclaw/returns/implementation-report-template.md`.
- Approved architecture: `docs/superpowers/specs/2026-07-29-stm32-toolkit-ai-development-design.md`.
- Development roadmap: `docs/superpowers/plans/2026-08-04-stm32-toolkit-complete-development-roadmap.md`.

Never commit credentials, plugin data, probe identifiers, private target logs, caches, generated build output, or unredacted diagnostics. Preserve unrelated user changes.

## Required work-order content

Every handoff must include objective, outcome, scope, non-scope, exact versions, architecture, exact paths, file responsibilities, public interfaces, state/data flow, validation, errors, security, privacy, performance, compatibility, tests, expected results, return evidence, acceptance criteria, rejection conditions, prohibited shortcuts, and forbidden unrelated changes.

Do not leave unresolved placeholders or invent facts available only on an OpenClaw worker or hardware target. Use a separate read-only diagnostic module when target-machine facts are required.

## Review outcomes

- `ACCEPTED`: requirements and tests pass without required changes.
- `ACCEPTED_WITH_FIXES`: Codex applied only a user-authorized bounded correction and verified it.
- `REVISION_REQUIRED`: bounded issues must be corrected by OpenClaw on the same attempt branch.
- `REWRITE_REQUIRED`: architecture, safety, scope, or coverage materially conflicts with the work order.

Every review report must cite affected files and verification evidence. GitHub pushes by Codex, PR approval, merge, PR closure, and remote branch deletion require explicit user authorization.
