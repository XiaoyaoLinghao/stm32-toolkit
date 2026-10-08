# STM32TK 1.0 local release: Monitor lifecycle qualification

## Scope

This bounded, test-only slice qualifies the three remaining public Monitor lifecycle scenarios against frozen product source revision `15b1a70e9bd684285da5557104deff529f537e49`:

1. A Ctrl+C during the replay adapter returns exit code `130` and emits no protocol result.
2. A provider failure after public `ProbeSession.revalidate()` and `prepare_read_plan()` returns an empty `MONITOR_PROVENANCE_CHANGED` outcome, clears the prepared plan and admission token, and does not expose provider exception text.
3. A full public `subscribe_deliveries()` queue is terminated by `MonitorSampler.close()` and the subscriber reaches `StopAsyncIteration`.

The tests reuse the existing public lifecycle entry points and fixtures. The sampler case observes the existing bounded queue until it is full, then calls public `close()`; it does not mutate the private queue or force the defensive `QueueEmpty` race. No product source, build, package, deployment, hardware, or remote state was changed.

The accepted integration base is `c3f7106356da9da18b572652d135b2444a77b1df`. The implementation code head before this report commit was `3832e8ce4b15ecb364d6600a8fd80827aaacd8c0`. This report intentionally records no report-commit SHA.

## Added qualification nodes

- `tools/stm32-monitor/tests/test_analysis_cli.py::test_replay_adapter_ctrl_c_returns_130_without_protocol_result` drives the existing replay-ingest adapter seam with `KeyboardInterrupt`, then asserts one dispatch, exit `130`, and an empty stdout buffer.
- `tools/stm32-monitor/tests/test_probe_session.py::test_prepared_read_provider_failure_returns_empty_and_invalidates_admission` uses public revalidation and plan preparation, makes the prepared provider raise, and asserts empty values, `MONITOR_PROVENANCE_CHANGED`, the stable sanitized message, cleared session plan/token, and cleared observation admission.
- `tools/stm32-monitor/tests/test_sampler.py::test_close_full_delivery_queue_still_terminates_subscriber` starts an `anext` task before sampling so the subscriber registers, waits with a three-second deadline for its existing queue to reach its capacity of eight, closes the sampler, and drains the stream with a two-second bounded wait until `StopAsyncIteration`.

The retained coverage map at `D:\codex-tmp\v10b-0918\r10\e\python-release\monitor-public-next-map.md` identifies exactly these three reachable branches and excludes the impossible `QueueEmpty` race and already-covered post-close subscription path.

## Verification

The pinned interpreter was `D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe`. `PYTHONPATH` used only the frozen verification imports:

```text
D:\codex-tmp\v10b-0918\r10\verify\tools\stm32-toolkit\src
D:\codex-tmp\v10b-0918\r10\verify\tools\stm32-monitor\src
```

The first recorded invocation was infrastructure-invalid because it used `tests/...` selectors from the worktree root instead of `tools/stm32-monitor/tests/...`. It collected zero items and exited 4 with pytest's file-not-found error. Its command, stdout, stderr, JUnit, exit code, environment, and child containment evidence remain at `D:\codex-tmp\v10b-0918\r10\e\monitor-lifecycle`; no test behavior or coverage result is attributed to that invocation.

The corrected invocation, recorded at `D:\codex-tmp\v10b-0918\r10\e\monitor-lifecycle\r2\command.txt`, was:

```text
D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe -m pytest -o addopts= -o cache_dir=D:\codex-tmp\v10b-0918\r10\t\ml\run2\pytest-cache --basetemp D:\codex-tmp\v10b-0918\r10\t\ml\run2\basetemp --junitxml D:\codex-tmp\v10b-0918\r10\e\monitor-lifecycle\r2\junit.xml --cov=stm32_toolkit --cov=stm32_monitor --cov-branch --cov-fail-under=0 --cov-report=term-missing --cov-report=json:D:\codex-tmp\v10b-0918\r10\e\monitor-lifecycle\r2\coverage.json tools/stm32-monitor/tests/test_analysis_cli.py::test_replay_adapter_ctrl_c_returns_130_without_protocol_result tools/stm32-monitor/tests/test_probe_session.py::test_prepared_read_provider_failure_returns_empty_and_invalidates_admission tools/stm32-monitor/tests/test_sampler.py::test_close_full_delivery_queue_still_terminates_subscriber
```

Actual result:

```text
collected 3 items
3 passed in 12.96s
pytest exit code: 0
```

The JUnit file reports three tests, zero failures, zero errors and zero skips. Branch coverage was enabled for both `stm32_toolkit` and `stm32_monitor`; this focused two-package subset measured `290/16500` branches and `6015/46449` statements, or 10.016% aggregate coverage. `--cov-fail-under=0` is recorded because the release threshold is an aggregate gate and is not a valid threshold for this three-node subset.

The raw coverage database was deliberately placed under the durable evidence root:

```text
D:\codex-tmp\v10b-0918\r10\e\monitor-lifecycle\r2\coverage\.coverage
```

It is retained alongside `coverage.json`, `junit.xml`, `stdout.txt`, `stderr.txt`, `exit-code.txt`, `command.txt`, `environment.json`, and the child tempfile evidence. The effective `tempfile.gettempdir()` was `D:\codex-tmp\v10b-0918\r10\t\ml\run2\tmpdir`; the child file was created under `D:\codex-tmp\v10b-0918\r10\t\ml\run2\childtempcheck` and the containment check exited 0.

## Evidence and preservation inventory

The initial infrastructure attempt is preserved at:

```text
D:\codex-tmp\v10b-0918\r10\e\monitor-lifecycle\
```

It contains `command.txt`, `environment.json`, `childtempcheck.stdout.txt`, `childtempcheck.stderr.txt`, `childtempcheck.exit`, `stdout.txt`, `stderr.txt`, `exit-code.txt`, and `junit.xml`; no raw coverage database or coverage JSON was produced because collection did not start.

The corrected run is preserved at:

```text
D:\codex-tmp\v10b-0918\r10\e\monitor-lifecycle\r2\
```

It contains the same command, environment, child containment, stdout, stderr, exit and JUnit files plus `coverage.json` and `coverage\.coverage`.

All run-scoped temporary roots remain under these primary-owned paths and are intentionally preserved for review and aggregation:

```text
D:\codex-tmp\v10b-0918\r10\t\ml\run1\
D:\codex-tmp\v10b-0918\r10\t\ml\run2\
```

No cleanup was performed by the implementation agent.

This report records implementation evidence only. Independent review of the complete accepted-base-to-code-head diff and acceptance remain with the primary agent or another reviewer; the implementation agent does not accept its own changes.
