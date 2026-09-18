# STM32TK-1.0 retention cancellation contract implementation return

Status: `REVISION_REQUIRED`. The original two-node run passed, but the bounded
future-observation correction produced a new diagnostic failure. This report
records both runs and is not a product acceptance decision. The primary agent
remains the independent reviewer and acceptor.

## Ownership and source ledger

- Slice: Retention writer phase discrimination and cancellation contract
  qualification for the local 1.0 release.
- Accepted base: `8070832fed4b25141a915d38e7c02055e8b32938`.
- Branch/worktree: `codex/STM32TK-1.0-retention-cancellation-contract` /
  `D:\codex-tmp\v10b-0918\r10\rc`.
- Test code head before this report commit:
  `d0f4703301f6aae26cbe26ce9d0d4c19aedc23f2`.
- Frozen product import source: `D:\codex-tmp\v10b-0918\r10\verify`,
  revision `15b1a70e9bd684285da5557104deff529f537e49`.
- Interpreter: `D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe`.
- Implementer: `/root/retention_failure_probe`; independent review and
  acceptance remain with the primary agent.
- Remote state: no push, pull request mutation, merge, tag, release, or branch
  deletion.

## Delivered test-only change

`tools/stm32-monitor/tests/test_history.py` adds exactly two selected checks.
They reuse `_paths`, `_batch`, `HistoryStore`, `HistoryQuery`, the instance
`_refresh_owned_integrity` seam, and the instance `_before_commit` seam.
Each uses bounded `threading.Event` waits and releases its barrier and closes
the store in `finally`.

The refresh-boundary scenario holds the existing integrity refresh after the
retention callback has returned from the existing durable commit. The caller
must return the unchanged `MONITOR_STORAGE_BUSY` result while a separate
read-only SQLite connection sees the deletion, matching accounting, and
`PRAGMA integrity_check` equal to `ok`. After release, the writer must accept a
fresh `SELECT 1` and the primed public query must not return the deleted value.

The commit-boundary scenario holds the existing `_before_commit` callback,
allows the caller to return `MONITOR_STORAGE_BUSY`, then releases the callback.
It accepts the existing contract's rollback-or-committed outcome, checks
batch/value/accounting consistency and integrity, checks writer reuse, and
checks that the public query agrees with the final durable state. This seam is
before Python calls `super().commit()`; it does not reproduce cancellation
inside SQLite's C-level commit and does not assert that `BUSY` implies rollback.

No product source, SQL, retention budget, clock, timeout, deletion limit,
cancellation handler, fixture generator, or shared helper signature changed.
The tests do not establish the cause of the historical 100,000-value
performance failure or claim that it is fixed.

## Single authorized verification run

The code commit was created before this report. The approved command ran once
with only the two new nodes, `-x`, dual-package branch coverage, and
`--cov-fail-under=0`:

```text
D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe -m pytest -x -o addopts= -o cache_dir=D:\codex-tmp\v10b-0918\r10\t\rc\pytest-cache --basetemp D:\codex-tmp\v10b-0918\r10\t\rc\basetemp --junitxml D:\codex-tmp\v10b-0918\r10\e\retention-cancellation\retention-cancellation.junit.xml --cov=stm32_toolkit --cov=stm32_monitor --cov-branch --cov-fail-under=0 --cov-report=term-missing --cov-report=json:D:\codex-tmp\v10b-0918\r10\e\retention-cancellation\retention-cancellation.coverage.json tools/stm32-monitor/tests/test_history.py::test_retention_timeout_after_commit_refresh_keeps_public_state_consistent tools/stm32-monitor/tests/test_history.py::test_retention_timeout_at_commit_boundary_preserves_consistency_and_reuse
```

Result: `2 passed in 11.16s`, exit code `0`; JUnit records two tests with zero
failures and zero errors. The raw coverage database, official JSON coverage,
JUnit, stdout, stderr, exact argv, command, environment, heads, preflight, and
exit evidence are retained under:

`D:\codex-tmp\v10b-0918\r10\e\retention-cancellation`

The effective Python temporary directory was verified as
`D:\codex-tmp\v10b-0918\r10\t\rc\tmpdir`. `TEMP`, `TMP`, `TMPDIR`, pytest
cache, and basetemp were all under the approved `r10\t\rc` root. Coverage
reported the selected-node projection with the required zero failure
threshold; it is not a release-wide coverage claim.

The launch manifest records UTC start `2026-09-18T23:18:58.0244491Z` and end
`2026-09-18T23:19:10.2786713Z`. A post-run process check found no Python,
Node, or browser process under `r10`. The primary preservation hold remains on
the run artifacts; no cleanup was performed.

## Boundary and review status

The run demonstrates the two specified existing-seam contracts for this small
fixture on the frozen product source. It does not reproduce the historical
100,000-value `FutureTimeout`, identify its original interrupted statement, or
prove a no-mutation guarantee that the current specification does not make.
Independent review must inspect the complete accepted-base-to-report diff and
decide whether any product action is justified.

## Revision run r2

The review correction was committed at code head
`d0f4703301f6aae26cbe26ce9d0d4c19aedc23f2`. It captures the actual retention
future through the existing instance `_submit` passthrough, retains callback
stage and exception evidence, accepts only normal completion or
`StorageFailure(MONITOR_STORAGE_BUSY)` with a SQLite `OperationalError` whose
message contains `interrupted`, and skips normal `store.close()` when caller or
future settlement is not proven. The new launcher prepared a hidden child with
a 60-second wall bound.

The single r2 attempt used the two selected nodes with `-x` and stopped at the
first unexpected result. Node A passed. Node B reached the callback release,
then the observed retention future ended as
`StorageFailure("MONITOR_STORAGE_BUSY")` with cause
`sqlite3.OperationalError("interrupted")`, while the callback wrapper had
captured the separate original
`StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage size cannot be inspected")`.
The test assertion rejected that unexpected callback failure instead of
swallowing it, so the result is `1 passed, 1 failed in 1.68s`, exit code `1`.
This is a bounded diagnostic failure requiring primary design review; it is not
a product root-cause claim.

The r2 launcher itself also exposed a preparation defect: its `$pid` variable
collided with PowerShell's read-only `$PID` automatic variable. The child
completed and no r2 Python process remains, but the launcher did not produce a
valid child-PID/wall-timeout manifest. The r2 command, argv, environment,
heads, stdout, stderr, JUnit, process error, and exit evidence remain under
`D:\codex-tmp\v10b-0918\r10\e\retention-cancellation\r2`; no official coverage
artifact was claimed for this failed run. No retry was performed.

The primary's separate read-only durable-outcome evidence is retained at
`D:\codex-tmp\v10b-0918\r10\e\retention-cancellation\primary-durable-outcomes.json`:
scenario A observed zero rows after deletion, and scenario B observed the
rollback/one-row outcome. That offline evidence was not produced by a rerun.

This report is committed separately from the test code head recorded above and
does not record its own final commit SHA.
