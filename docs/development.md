# Development and review

Start with [AGENTS.md](../AGENTS.md), [current architecture](architecture.md), the approved change
specification, and the [standard test procedure](testing/standard-test-procedure.md). Product behavior
belongs in shared Python workflows; CLI/MCP and agent skills are thin adapters.

## Before implementation

Record the full accepted-base SHA, module/phase, specification owner, implementation owner, independent
reviewer, branch/PR, environment, authorized remote actions and any bounded ownership exception.
Inspect tracked/untracked and committed/uncommitted state before switching ownership. Work in a clean
isolated worktree; preserve unrelated user changes and do not recreate retired workspaces.

Define two to four runnable scenarios and explicit non-goals, then freeze shared models, errors,
lifecycle transitions, state ownership and dependency direction. One bounded vertical slice has one
implementation owner. The primary conversation agent owns the design, scheduling, integration and
acceptance; all subagents currently use `gpt-6-sol / max`. Implementation authors cannot approve
their own changes, and the primary agent does not implement product code without a user-named exception.

Keep specs under `docs/superpowers/specs/`, plans under `docs/superpowers/plans/`, and current acceptance
records under `docs/codex/returns/`. Old reports are not an extra source of current authority. Before
substantial work, retrieve only matching evidence-reviewed local engineering lessons; do not put
mutable lesson stores or personal credentials in this repository.

## During implementation and review

Use one owner for shared schemas, public types, lockfiles and release configuration. Parallel write
work requires explicit disjoint responsibility or verified isolated worktrees. Do not recursively
split a slice into a task tree; resolve cross-module design questions with the primary agent.

Run behavior, refusal and affected regression checks at slice level. Use existing fixtures and actual
hash/identity validation; mocks of external tools do not establish authorization or physical success.
Classify failures before changing code: PRODUCT, INFRASTRUCTURE, ENVIRONMENT, PLATFORM, HARDWARE, REPORT.
Preserve already-valid evidence unless relevant source, dependencies, environment or contracts change.

The independent review covers the complete accepted-base-to-CodeHead diff, including tests, docs,
generated resources and deletions. Cite the observed/expected behavior, path, evidence and reproduction
command for each actionable finding. Correctable findings return to the same implementation owner;
if an issue fails to converge after two rounds, revisit the interface rather than continuing patches.

Reports identify accepted base and CodeHead before the report commit, never their own future SHA.
Each PASS belongs to its actual execution owner and source identity. Track runnable scenarios,
connected paths, blockers and slice cycle time, rather than task-count completion percentages.
If verification/reporting dominates two consecutive slices, review the process before more product work.

## Release and repository maintenance

The current offline packaging entry is `tools/release/build_0900_artifacts.py`, governed by
`tools/release/release_0900_policy.json`. Its filename does not authorize using older 0.5/0.6 release
controllers. Installation, release and hardware qualification happen once at the appropriate final
layer, with justified reuse of still-applicable evidence.

Push, PR mutation, merge, tag, Release, closure and remote branch deletion each require current user
authorization. A version bump or local commit is not publication. Do not overwrite a published tag or
reuse another candidate's numerical exception. See [release status](release-status.md).

When removing obsolete tracked material, freeze its path list, inspect inbound references and runtime/
test/package dependencies, preserve any still-valid contract in current docs, and use Git history for
retrieval. Do not leave a second archive tree on master, silently discard user data, or rewrite history.
Keep source tests, required reusable fixtures, licenses and useful current documentation.

Windows run outputs default to short directories under `D:\codex-tmp`; set TEMP, TMP and TMPDIR together.
Record one cleanup owner. Resolve and verify exact paths before deleting only attributable disposable
outputs; retain minimal failure evidence. Use PowerShell native path operations and UTF-8 files for
complex commands. `rg` returning 1 with no error is simply no match.
