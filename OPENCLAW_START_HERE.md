# OpenClaw Start Here

This repository uses document-based GitHub delivery. Conversation history and files stored only on Codex’s computer are not inputs.

## Repository contract

- Repository: `https://github.com/XiaoyaoLinghao/stm32-toolkit.git`
- Default branch: `master`
- Work orders: `docs/openclaw/modules/{MODULE-ID}-*.md`
- Reports: `docs/openclaw/returns/{MODULE-ID}/{ATTEMPT}-implementation-report.md`
- Report template: `docs/openclaw/returns/implementation-report-template.md`
- First branch: `openclaw/{MODULE-ID}/r001`

Configure authentication on this machine without placing tokens in prompts, remotes, logs, or files. Commit author identity is not proof of GitHub authentication.

## Required procedure

1. Clone or fetch the repository, check out `master`, record its full SHA as the specification commit, and verify the worktree is clean.
2. Read `AGENTS.md`, this file, and the unique work order for the supplied module ID from that specification commit.
3. Verify the supplied full accepted-base SHA exists, exactly matches the work order, and the work order is `READY_FOR_OPENCLAW` with no placeholder or contradictory command. Otherwise return `BLOCKED` with exact evidence.
4. Create the specified `r001` branch from the accepted base. Do not reuse local state from another attempt and do not merge the specification commit into the implementation branch.
5. Implement only the listed scope. Do not modify agent rules, the approved work order, unrelated modules, credentials, or remote policy.
6. Run each gate available in the actual environment. Record actor, OS/tool versions, tested commit, command, exit code, and observed result. Mark an unavailable platform gate only with the work order’s named deferred owner.
7. Reconcile the complete accepted-base-to-code-head diff, record that code head, push it to the one module branch, and create the single PR targeting `master`. Materialize the report template from the recorded specification commit and complete it without any future or final report-commit SHA.
8. Commit the report last and push that commit to the same module branch and PR.
9. Confirm local HEAD, remote module-branch HEAD, and PR head are identical.
10. Return status, branch, accepted base, code head, final head, PR URL, report path, changed-path inventory, environment-separated verification, and deferred gates.

## Prohibited behavior

- No credentials, `.env`, private reports, caches, build output, screenshots containing private data, or unredacted diagnostics.
- No push to `master`, merge, approval, PR close, or branch deletion.
- No fabricated Windows, GUI, visual, device, performance, or target-machine result.
- No claim that another actor’s test was run by OpenClaw.
- No new PR for a bounded `REVISION_REQUIRED` correction.
- No self-referential final SHA or moving commit total in a tracked report.
- No silent dependency, requirement, architecture, scope, or accepted-base substitution.

## Revision procedure

For `REVISION_REQUIRED`, update the existing attempt branch and PR, correct all listed issues, rerun the complete required suite, update the report, and return the new final head. Codex will review the whole accepted-base-to-new-head diff.

For `REWRITE_REQUIRED`, wait for explicit new attempt and base instructions. Do not close or modify the earlier PR unless the user separately authorizes it.
