# STM32TK-0600 VS-03/VS-04 Local Acceptance Ledger

## Identity and ownership

- Repository: `https://github.com/XiaoyaoLinghao/stm32-toolkit.git`.
- Runtime authority: CPython `>=3.12,<3.13`; Python 3.10 remains frozen historical scope.
- VS-03 review base: `dc304de6ef1d7efbdabe06ae37ec96a859615f84`.
- VS-03 accepted CodeHead: `5d6e06845a2c1d991181c5ff84a9194dfcc49c8c`.
- VS04-A accepted CodeHead: `6d8a593990d176e5ef2b9e051059ab6e5b3fd76b`.
- VS04-B1 accepted replacement CodeHead: `2b8b5b166c04c59d3f0f8bf326204ac74264620e`.
- VS04-B2 and current product CodeHead: `d09e2343ab970f4ddeaa4c24dbf581c9bbe96f58`.
- Governance-ledger correction head before this report: `52e44e730b982a632f9eff54364d38877bb9292b`.
- Specification, plans, risk decisions, reviews, and acceptance: GPT-5.6-sol primary.
- Product implementation and implementation tests: bounded GPT-5.6-luna/max agents as named by the slice plans.
- Remote, PR, merge, tag, branch-deletion, and hardware authority: none.

Git authorship records the repository identity only and is not used as proof of model ownership.
The accepted chain is linear from VS-03 through VS04-B2. Superseded attempt heads may remain Git
ancestors, but they are not accepted CodeHeads or verdicts.

## Accepted product behavior

| Slice | Accepted behavior | Verdict |
|---|---|---|
| VS-03 | Public Target replay, Monitor ingestion/comparison, diagnostic verification lifecycle, marker, deterministic bundle, CLI/MCP adapters, Scenario B fresh reload, incompatible-identity and insufficient-data negatives | `ACCEPTED` |
| VS04-A | Identity-bound prepare/execute/show, single-use action digest, one MODIFY lease, post-flash inventory authority, physical TestRun publication and reload | `ACCEPTED` |
| VS04-B1 | Replay-v1/physical-v2 closed reference union, authenticated physical transcript publication, idempotent/fresh reload, bounded recovery and conflict semantics | `ACCEPTED` |
| VS04-B2 | History-independent physical analysis, marker and deterministic bundle, physical FixVerification, fresh reload to `PASSED`/`RESOLVED`, mixed-source fail-closed behavior | `ACCEPTED` |
| VS04-C | Named-board failed-before/fixed-after Scenario C with two separately authorized MODIFY digests | `PENDING_NAMED_HARDWARE` |

The combined local state is `SOFTWARE_COMPLETE_HARDWARE_PENDING`, not 0.6 release acceptance.

## Sol-owned verification evidence

All checks below used clean exact-SHA worktrees and CPython 3.12. No hardware or remote action ran.

- VS-03 final review covered `dc304de6ef1d7efbdabe06ae37ec96a859615f84..5d6e06845a2c1d991181c5ff84a9194dfcc49c8c` and the planned software integration set. A stale system `.pth` import was isolated to an old worktree; the candidate-bound check passed. The named performance check passed on the isolated candidate run in `66.83s`. Two expected skips remained. Complete-diff review found no actionable product issue.
- A later completion-audit invocation at the same VS-03 CodeHead ended with two failures and two skips. One failure proved it imported `stm32_toolkit` from `C:\tmp\stm32tk-0601-t08-target-transports`, not the candidate. The performance sample reported query p95 `159.3885ms` while multiple independent audits were running. This invocation is retained as non-PASS audit evidence; it neither replaces the earlier isolated PASS nor invalidates unchanged accepted product bytes. It was not rerun.
- VS04-A exact-SHA focused audit selected 550 tests and exited zero. VS04-B1 exact-SHA focused audit selected 268 tests and exited zero. Both worktrees remained clean.
- VS04-B2 final review ran the final correction group (`11 passed`), B2 end-to-end (`2 passed`), and Analysis/publication/shared-contract group (`153 passed`), plus `py_compile` and cumulative `git diff --check`; no finding remained.
- A fresh cross-slice audit at `d09e2343ab970f4ddeaa4c24dbf581c9bbe96f58` ran VS-03 Scenario B, VS04-A physical workflows, B1 physical publication, and B2 end-to-end: `60 passed, 1 warning` in `83.12s`, exit zero.
- After the governance correction, `git diff --check 5d6e06845a2c1d991181c5ff84a9194dfcc49c8c..52e44e730b982a632f9eff54364d38877bb9292b` exited zero. No product file changed after `d09e2343ab970f4ddeaa4c24dbf581c9bbe96f58`, so accepted product evidence remains applicable.

## Governance reconciliation

The governance-only correction at `52e44e730b982a632f9eff54364d38877bb9292b`:

- removed three specification EOF blank lines that made the VS04-A accepted-base diff-check fail;
- recorded the accepted B1 replacement branch;
- recorded B1's bounded `protocol.py` use for the already-required public `OPERATION_CONFLICT` result;
- recorded the B2 implementation branch.

These were formatting and ledger repairs. They did not alter product behavior and did not trigger
another product verification layer.

## Remaining boundary

VS04-C has no planned product coding and no generic implementation plan. It remains blocked until
the user names the board, MCU/target, raw probe selector, Project v3, failing case, transport
configuration, Monitor selector, failing/fixed source revisions, and tool environment. Preparation
may then return the first action digest, but execution must stop for explicit user authorization of
that exact digest. The fixed-after action requires a second independently prepared and explicitly
authorized digest.

Broader platform, browser, packaging, coverage, hardware matrix, evidence archival, and release
checks remain at the release layer. The historical dual-Python and literal release gate ladders are
not reinstated. No push, PR mutation, merge, tag, close, or remote branch action is implied.
