# STM32 Toolkit Agent Instructions

## Model ownership and delegation

Git commits are the only durable source of truth. The primary conversation agent, regardless of its model, owns project-state reconstruction, product architecture, specifications, implementation plans, task boundaries, risk decisions, complete-diff review, and acceptance. It directly owns all task orchestration and subagent dispatch; no particular model is required as an intermediary. GPT-5.6-luna agents own product implementation and implementation tests.

Every product implementation subagent must be created with model `gpt-5.6-luna` and reasoning effort `max`. The primary conversation agent must not implement product code, and an implementation agent must not approve its own diff. Any ownership exception requires explicit user authorization naming the files and behavior, and expires after verification.

The user authorizes every push, PR mutation, merge, closure, tag, and remote branch deletion. “Continue,” urgency, defect size, prior approval, or model availability does not transfer implementation ownership or remote authority.

Before acting, reconstruct this ledger: module and phase, full accepted-base SHA, specification owner, implementer, reviewer, active branch/PR, exact remote action authorized, and any bounded override. On an ownership change, audit tracked/untracked, committed/uncommitted, and pushed/unpushed state before exposing or discarding anything.

## Repository contract

- Repository: `https://github.com/XiaoyaoLinghao/stm32-toolkit.git`.
- Default branch: `master`.
- Local implementation branches use the `codex/` prefix and identify the module and vertical slice.
- Current reports: `docs/codex/returns/{MODULE-ID}/implementation-report.md`.
- Approved specifications live under `docs/superpowers/specs/`.
- Approved implementation plans live under `docs/superpowers/plans/`.
- Architecture: `docs/superpowers/specs/2026-07-29-stm32-toolkit-ai-development-design.md`.
- Roadmap: `docs/superpowers/plans/2026-08-04-stm32-toolkit-complete-development-roadmap.md`.
- Current 0.7–1.0 integration design: `docs/superpowers/specs/2026-08-22-stm32-toolkit-0.7-1.0-integrated-product-design.md`.
- Current 0.7–1.0 delivery plan: `docs/superpowers/plans/2026-08-22-stm32-toolkit-0.7-1.0-vertical-delivery-plan.md`.
- Large-project lessons: `docs/codex/lessons/2026-08-22-large-project-development-error-book.md`.

Never accept, repeat, retain, or commit plaintext credentials. Commit identity is not proof of GitHub authentication; verify each computer independently. Preserve unrelated changes and review in a clean isolated worktree at the exact reviewed CodeHead/final head, using the accepted base only as the diff origin.

## Delivery workflow

1. The primary conversation agent reconstructs the ownership ledger and freezes one self-contained vertical-slice specification and implementation plan at a full accepted-base SHA, with public behavior, boundaries, risks, and proportionate evidence requirements.
2. After the governing specification is approved, the primary agent writes the bounded slice plan. The user has waived a separate approval stop for later written implementation plans; this does not waive product-scope, remote, release, installation, or hardware authorization.
3. The primary agent creates one `gpt-5.6-luna` implementation subagent with reasoning effort `max` for that bounded slice.
4. The 5.6-luna agent implements and runs slice-level tests in one clean isolated worktree. It does not push, create or mutate a PR, merge, close, tag, or delete a remote branch without separate user authorization.
5. The primary conversation agent independently reviews the complete accepted-base-to-CodeHead diff in a clean worktree, runs only the applicable slice or integration verification, reconciles the evidence, and records one verdict.
6. Correctable findings remain on the same slice branch and return to a 5.6-luna implementation agent. If the same issue does not converge after two rounds, stop local patching and return to the interface or integration design.
7. Release-level matrices, packaging, hardware, and evidence archival run only at the integration or release layer unless a written risk trigger explicitly moves the affected check forward.
8. Any push, PR, merge, tag, closure, or remote deletion stops for a new explicit user authorization.

Do not add collaboration apps, manifests, validators, CI, or dispatch automation unless the user explicitly assigns that tooling as product scope.

## Evidence and report rules

### Mandatory standard test procedure

Before planning or executing tests, deployment, or hardware acceptance, read [the standard test procedure](docs/testing/standard-test-procedure.md), its current acceptance checkpoint, and the referenced latest execution report. This is the single maintained procedure; old run-local execution cards are historical snapshots, not authority for the next run.

Before hardware access, fill its execution card with actual source/runtime/firmware identities, target state and ownership, existing entry-point preconditions, current authorization, finite budget, success evidence, failure stop and cleanup rules. Resolve missing or conflicting prerequisites offline before declaring a step READY. A terminal failure stops subsequent hardware; no automatic retry or recovery fallback. Preserve valid evidence and resume at the actual incomplete stage rather than repeating deployment or accepted Target tests.

The primary agent maintains this procedure. When an entry contract or missed prerequisite changes, update the relevant procedure section and obtain independent review before the dependent hardware step. Documentation-only changes do not trigger packaging, deployment or a full test cycle. The procedure itself grants no hardware or remote authority.

Every implementation plan specifies exact public behavior and boundaries and names the evidence owner and required environment for each verification layer. `PASS` means that owner ran the check against the recorded commit. A platform-only check may be `DEFERRED` only to a named later phase or owner; a pure code failure is never deferred. Do not invent target facts or attribute one agent's evidence to another owner.

The tracked implementation report records the accepted base and the CodeHead before the report commit. It must not contain its own final commit SHA or moving commit totals. Local Git evidence records the report commit; any later remote identity is reported only after an authorized remote action.

## Review outcomes

- `ACCEPTED`: all required non-deferred gates pass.
- `SOFTWARE_COMPLETE_HARDWARE_PENDING`: all required software gates pass, but a named mandatory hardware matrix remains outstanding; this is not release acceptance.
- `ACCEPTED_WITH_FIXES`: a 5.6-luna agent applied an explicitly bounded correction and the primary conversation agent verified it before the final CodeHead freeze.
- `REVISION_REQUIRED`: correctable issues remain on the same module branch.
- `REWRITE_REQUIRED`: architecture, safety, scope, or coverage requires a replacement implementation.

Every issue cites path, observed behavior, expected behavior, evidence, and verification command. GitHub approval, merge, close, push, tag, or deletion is never implicit.
