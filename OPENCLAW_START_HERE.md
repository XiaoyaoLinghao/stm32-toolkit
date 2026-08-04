# OpenClaw Start Here

This repository uses document-based delivery. The repository URL and module ID are the complete dispatch payload; no conversation history or out-of-band files are required.

## Inputs

- Repository: `https://github.com/XiaoyaoLinghao/stm32-toolkit.git`
- Default branch: `master`
- Module ID: supplied by the user
- Work orders: `docs/openclaw/modules/{MODULE-ID}-*.md`
- Return reports: `docs/openclaw/returns/{MODULE-ID}/{ATTEMPT}-implementation-report.md`
- Report template: `docs/openclaw/returns/implementation-report-template.md`

## Required procedure

1. Clone or fetch the repository and check out `master`.
2. Read `AGENTS.md`, this file, and the unique work order whose filename starts with the supplied module ID.
3. Confirm the work order status is `READY_FOR_OPENCLAW` and contains no unresolved placeholders. Otherwise stop and report `BLOCKED` with exact evidence.
4. On the fetched `master`, record `$baseCommit = (git rev-parse HEAD).Trim()`, then create `openclaw/{MODULE-ID}/r001` from `$baseCommit`. The commit must contain this ready work order.
5. Implement only the listed scope. Do not modify agent rules, approved work orders, unrelated modules, or remote workflow policy.
6. Run every required command and record the observed results.
7. Copy the report template to `docs/openclaw/returns/{MODULE-ID}/r001-implementation-report.md`, resolve every field, and reconcile it with the complete base-to-head diff.
8. Commit and push only the module branch. Create a PR or compare URL targeting `master`.
9. Return the branch, full base/head commits, PR or compare URL, report path, changed-path inventory, and test evidence.

## Prohibited behavior

- Do not commit credentials, tokens, `.env` files, caches, build outputs, real probe identifiers, private target data, or unredacted diagnostics.
- Do not push to `master`, merge, approve, close PRs, or delete remote branches.
- Do not silently alter requirements, substitute dependencies, broaden scope, or add speculative compatibility.
- Do not claim a test passed without the exact command, environment, exit code, and observed result.
- Do not create dispatch manifests, validators, collaboration automation, or CI unless the work order explicitly requires it.

## Revision procedure

For `REVISION_REQUIRED`, correct every cited issue on the same module branch, update the same implementation report, rerun all required checks, push, and return the new head commit. For `REWRITE_REQUIRED`, wait for the replacement-branch instruction before starting another attempt.
