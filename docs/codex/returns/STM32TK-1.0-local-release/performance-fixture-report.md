# STM32TK-1.0 performance fixture implementation return

Status: `IMPLEMENTED_PENDING_INDEPENDENT_REVIEW`. This is the implementation
return for the bounded fixture-lifecycle correction, not an acceptance
decision. The primary agent remains the independent reviewer and acceptor.

## Ownership and source ledger

- Slice: Narrow backend performance follow-up for the local 1.0 release.
- Named accepted product base: `f7f19053649f16ae4ab390a5af6012c451833bea`.
- Approved integration/worktree starting head: `e21d15f0ad80bd3a16b86e8cc362a161ff587de9`.
- Specification: `docs/superpowers/specs/2026-09-19-stm32tk-1.0-local-release-design.md`.
- Plan: `docs/superpowers/plans/2026-09-19-stm32tk-1.0-local-release.md`, section
  `Narrow backend performance follow-up`.
- Product/test CodeHead before this report commit:
  `920794e11a3969843bd4ed1bfacbfaa1ad06cc87`.
- Branch/worktree: `codex/STM32TK-1.0-performance-fixture` /
  `D:\codex-tmp\v10b-0918\r10\pf`.
- Implementer: `/root/retention_failure_probe`; independent review and acceptance
  remain with the primary agent.
- Remote state: no push, pull request mutation, merge, tag, release, or branch
  deletion.

## Delivered correction

`tools/stm32-monitor/tests/test_performance.py::_seed_fixture` now opens the
checkpoint SQLite connection explicitly, executes the existing
`PRAGMA wal_checkpoint(TRUNCATE)`, and closes that connection in `finally`.
The fixture generation loop, digest bytes, value count, batch count, helper
signature, history close, clocks, and all performance limits are unchanged.

The correction is limited to the checkpoint connection lifetime. No product
source, fixture data, shared helper signature, threshold, or performance entry
was changed. No new test framework or diagnostic framework was added.

## Verification boundary

No test, build, fixture seed, export benchmark, UI benchmark, browser, or
performance execution was run while preparing this return. The only static
check performed after the edit was `git diff --check`, which passed. The
corrected helper therefore remains pending independent review and the later
exclusive run authorized by the plan.

## Deferred exclusive run

After independent review and ordinary concurrent tests, the existing named
entry is to run once with exclusive resources and the original
append/query/export/retention/HTTP ordering:

```powershell
& 'D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe' -m pytest -q `
  --basetemp='D:\codex-tmp\v10b-0918\r10\t\pf\pytest' `
  tools/stm32-monitor/tests/test_performance.py `
  -k test_named_monitor_performance_acceptance
```

At that time, `TEMP`, `TMP`, `TMPDIR`, bytecode, coverage variables, cache,
stdout, stderr, exit, and diagnostic JSON are to be bound or retained under
the approved `r10\t\pf` and `r10\e\performance-followup` roots. The reviewed
StorageFailure constructor observer may retain throw source and bounded inner
exception details only when the existing entry fails; it must not change
successful behavior, budgets, thresholds, or ordering. A successful run is
evidence for that run and does not establish the old BUSY cause or release
acceptance.

The separate export benchmark and UI performance run are not part of this
follow-up. The first abnormal result stops the run and is returned with its
actual exception evidence.

This report is committed separately from the CodeHead recorded above; it does
not record its own final commit SHA.
