# STM32TK 1.0 local release: DiagnosticStore lock contention correction

## Scope

This bounded implementation corrects the demonstrated Windows DiagnosticStore
lock contention path. Windows acquisition now uses repeated `LK_NBLCK`
attempts under one absolute monotonic 10-second budget, retries only native
`EACCES`, sleeps at most 25 ms and at most the remaining budget, checks the
deadline before protected entry, and always closes the descriptor after
cleanup. POSIX locking, descriptor identity and layout validation, protected
work ordering, publication semantics, and cleanup-error precedence remain
unchanged.

The public adapters expose the distinct operational results
`DIAGNOSTIC_STORE_BUSY` and `ACCEPTANCE_ATTEMPT_BUSY`. Acceptance forwards only
the validated nested `diagnostic.show` BUSY result; other non-OK Diagnostic
results retain `ACCEPTANCE_ATTEMPT_OUTPUT_INVALID`. The added continuation case
proves that BUSY during the second, postpublication authentication leaves the
revision-1 root and immutable payload available for an exact retry and read.
That case injects the public Busy boundary deterministically; it does not claim
a real native ten-second wait. The store module also contains a separate real
Windows child-process check that holds the native lock through an explicit
ready/release handshake, proves exclusion and no protected entry, waits for
the finite owned child to release it, and proves lock reuse. No model schemas,
`DIAGNOSTIC_CODES`, lock users, release configuration, hardware code, package,
deployment, or remote state changed.

The amended governing design and plan are recorded by primary commit
`a6e3888c35af853ce571c58036b063a69be409fd`. The accepted base is
`fa8502e6bf706fcaae26122cf996077678053cc5`. The implementation code head
before this report commit is `863603f0a4c8d0ed68f6fb19b8fd27c59cb59f19`
(`863603f0`); this report intentionally records no report-commit SHA.

## Implementation and regression coverage

The implementation owns these product files:

- `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/store.py`
- `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/__init__.py`
- `tools/stm32-toolkit/src/stm32_toolkit/diagnostic_workflows.py`
- `tools/stm32-toolkit/src/stm32_toolkit/acceptance/recovery_workflows.py`

The focused regressions cover deterministic native contention and deadline
expiry through the public `DiagnosticStore.load` entry, non-contention refusal,
no late protected entry, descriptor cleanup after unlock failure, direct
Diagnostic and acceptance mappings, nested public Diagnostic BUSY forwarding,
postpublication revision-1 preservation, and the real native cross-process
exclusion/release/reuse check. The existing concurrent continuation test function
`test_persisted_continuation_monitor_diagnostic_and_expired_attempt_reuse`
was left byte-for-byte unchanged. A separate new continuation case exercises
the second-authentication BUSY boundary with deterministic public-context
injection.

The implementation owner ran only the primary-authorized focused-r1 entry
recorded below. The primary agent owns entry review, execution, evidence
cleanup, independent review, and acceptance.

## Focused-r1 execution record

The primary-authorized focused-r1 launcher was run once at source head
`46f404e664532f90778bd12d1f6037aac2bb5389` with the reviewed 180-second
PowerShell 7 entry. Preflight passed, the owned child exited normally with
exit code `1`, and the launcher did not time out. Pytest collected 40 cases;
29 passed before `-x` stopped at
`test_windows_unlock_failure_still_closes_descriptor`. The assertion saw
whole-process native modes `[2, 1, 3, 3]` instead of `[2, 3]`: the public load
also reaches an EvidenceStore lock through
`DiagnosticStore.load -> _load_chain_locked -> _ensure_checkpoint_locked ->
_checkpoint_expected -> EvidenceStore.ingest_file -> _mutation_lock ->
LK_LOCK`. This is a test-fixture boundary failure, not a product behavior
classification. The corrected case now wraps the real Windows `msvcrt`
locking function, forwards all other descriptors and modes, injects `EIO`
only for the captured Diagnostic descriptor's `LK_UNLCK`, and asserts only
that descriptor's modes and close.

The preserved run evidence is under
`D:\codex-tmp\v10b-0918\r10\e\diagnostic-lock-contention\focused`, including
`stdout.txt`, `stderr.txt`, `junit.xml`, `process.json`,
`launch-result.json`, `preflight.json`, `heads.json`, `argv.json`,
`environment.json`, `command.txt`, and `exit-code.txt`. No retry, cleanup, or
continuation execution was performed for this result.

## Prepared serialized verification entries

All entries reuse the finite-child PowerShell 7 launcher pattern in
`D:\codex-tmp\v10b-0918\r10\e\retention-cancellation\r3\launch.ps1`:
hidden `Start-Process`, an owned process handle, bounded `WaitForExit`,
bounded termination of that exact child, and separate launcher and child exit
records. The primary must run the entries serially. The launcher must clear
inherited `PYTEST_ADDOPTS`, `COVERAGE_*`, and `COV_CORE_*`, set `TEMP`, `TMP`,
and `TMPDIR` below the entry's `D:\codex-tmp\v10b-0918\r10\t\lk` root, and
record the actual `tempfile.gettempdir()` check before creating the child.

The pinned interpreter and import roots are:

```text
D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe
D:\codex-tmp\v10b-0918\r10\lk\tools\stm32-toolkit\src
D:\codex-tmp\v10b-0918\r10\lk\tools\stm32-monitor\src
```

The focused entry is `diagnostic-lock-contention-focused-r1`, with a 180
second child wall bound. Its evidence root is
`D:\codex-tmp\v10b-0918\r10\e\diagnostic-lock-contention\focused` and its
temporary root is `D:\codex-tmp\v10b-0918\r10\t\lk\f` (basetemp
`D:\codex-tmp\v10b-0918\r10\t\lk\f\b`).

```text
D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe -m pytest -x -o addopts= -o cache_dir=D:\codex-tmp\v10b-0918\r10\t\lk\f\pytest-cache --basetemp D:\codex-tmp\v10b-0918\r10\t\lk\f\b --junitxml D:\codex-tmp\v10b-0918\r10\e\diagnostic-lock-contention\focused\junit.xml --cov=stm32_toolkit --cov=stm32_monitor --cov-branch --cov-fail-under=0 --cov-report=term-missing --cov-report=json:D:\codex-tmp\v10b-0918\r10\e\diagnostic-lock-contention\focused\coverage.json tools/stm32-toolkit/tests/test_diagnostic_store.py tools/stm32-toolkit/tests/test_diagnostic_workflows.py::test_diagnostic_store_busy_is_a_sanitized_public_result tools/stm32-toolkit/tests/test_acceptance_recovery_workflows.py::test_diagnostic_store_busy_maps_to_acceptance_availability_result tools/stm32-toolkit/tests/test_acceptance_recovery_workflows.py::test_nested_diagnostic_store_busy_maps_to_acceptance_availability_result tools/stm32-toolkit/tests/test_continuation_monitor.py::test_postpublication_diagnostic_busy_preserves_revision_one_for_exact_retry_and_read
```

The continuation entry is `diagnostic-lock-contention-continuation-r1`, with
a 240 second child wall bound. Its evidence root is
`D:\codex-tmp\v10b-0918\r10\e\diagnostic-lock-contention\continuation` and its
temporary root is `D:\codex-tmp\v10b-0918\r10\t\lk\c` (basetemp
`D:\codex-tmp\v10b-0918\r10\t\lk\c\b`). It runs
only the original existing node with Toolkit branch coverage:

```text
D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe -m pytest -x -o addopts= -o cache_dir=D:\codex-tmp\v10b-0918\r10\t\lk\c\pytest-cache --basetemp D:\codex-tmp\v10b-0918\r10\t\lk\c\b --junitxml D:\codex-tmp\v10b-0918\r10\e\diagnostic-lock-contention\continuation\junit.xml --cov=stm32_toolkit --cov=stm32_monitor --cov-branch --cov-fail-under=0 --cov-report=term-missing --cov-report=json:D:\codex-tmp\v10b-0918\r10\e\diagnostic-lock-contention\continuation\coverage.json tools/stm32-toolkit/tests/test_continuation_monitor.py::test_persisted_continuation_monitor_diagnostic_and_expired_attempt_reuse
```

The fresh focused-r2 remainder entry is
`diagnostic-lock-contention-focused-r2`, with a 180 second child wall bound.
Its evidence root is
`D:\codex-tmp\v10b-0918\r10\e\diagnostic-lock-contention\focused-r2` and its
temporary root is `D:\codex-tmp\v10b-0918\r10\t\lk\f2` (basetemp
`D:\codex-tmp\v10b-0918\r10\t\lk\f2\b`). It selects the corrected unlock
case, the six store cases that followed the failed first-run case, and the
four direct/nested adapter and postpublication cases:

```text
D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe -m pytest -x -o addopts= -o cache_dir=D:\codex-tmp\v10b-0918\r10\t\lk\f2\pytest-cache --basetemp D:\codex-tmp\v10b-0918\r10\t\lk\f2\b --junitxml D:\codex-tmp\v10b-0918\r10\e\diagnostic-lock-contention\focused-r2\junit.xml --cov=stm32_toolkit --cov=stm32_monitor --cov-branch --cov-fail-under=0 --cov-report=term-missing --cov-report=json:D:\codex-tmp\v10b-0918\r10\e\diagnostic-lock-contention\focused-r2\coverage.json tools/stm32-toolkit/tests/test_diagnostic_store.py::test_windows_unlock_failure_still_closes_descriptor tools/stm32-toolkit/tests/test_diagnostic_store.py::test_windows_native_lock_excludes_child_then_reuses_after_release tools/stm32-toolkit/tests/test_diagnostic_store.py::test_create_retry_validates_every_workspace_session_before_returning tools/stm32-toolkit/tests/test_diagnostic_store.py::test_create_operation_scope_ignores_later_event_operation_ids tools/stm32-toolkit/tests/test_diagnostic_store.py::test_session_limit_is_checked_without_creating_a_new_session tools/stm32-toolkit/tests/test_diagnostic_store.py::test_event_limit_is_checked_without_creating_a_new_event tools/stm32-toolkit/tests/test_diagnostic_store.py::test_event_redirect_is_rejected_without_root_mutation tools/stm32-toolkit/tests/test_diagnostic_workflows.py::test_diagnostic_store_busy_is_a_sanitized_public_result tools/stm32-toolkit/tests/test_acceptance_recovery_workflows.py::test_diagnostic_store_busy_maps_to_acceptance_availability_result tools/stm32-toolkit/tests/test_acceptance_recovery_workflows.py::test_nested_diagnostic_store_busy_maps_to_acceptance_availability_result tools/stm32-toolkit/tests/test_continuation_monitor.py::test_postpublication_diagnostic_busy_preserves_revision_one_for_exact_retry_and_read
```

Each launcher entry writes `command.txt`, `argv.json`, `environment.json`,
`preflight.json`, `heads.json`, `stdout.txt`, `stderr.txt`, `process.json`,
`launch-result.json`, `exit-code.txt`, `junit.xml`, `coverage.json`, and the
raw coverage database at `raw-coverage\.coverage`; a single
`shards\shard-001.json` records the selected nodes, serial setting, wall
bound, and coverage paths. The source head in every new entry must be
`863603f0a4c8d0ed68f6fb19b8fd27c59cb59f19`, and `PYTHONPATH` must resolve to
the `lk` paths above, never `verify15b`.

The executable launchers prepared for these entries are:

- `D:\codex-tmp\v10b-0918\r10\e\diagnostic-lock-contention\focused\launch.ps1`
  (SHA256 `5510AEC99EBA7EFBD988F1F39314F833BB8418A99E9383D5CE14C01F996838A8`)
- `D:\codex-tmp\v10b-0918\r10\e\diagnostic-lock-contention\continuation\launch.ps1`
  (SHA256 `C745DCF0E87A4675AEF9CB454772AF90CA690D68589F232F77D51042342F4201`)
- `D:\codex-tmp\v10b-0918\r10\e\diagnostic-lock-contention\focused-r2\launch.ps1`
  (SHA256 `4C12C832150A934CCE33970746D1641FA8E05A2DFF2555DFFF29AFC657A502A7`)

PowerShell 7 AST parsing reported zero errors for all three launchers. The
focused-r2 launcher is prepared only; it has not been run.

This report records implementation preparation and the primary-authorized
focused-r1 result. The implementation agent does not accept its own diff;
independent complete-diff review and the final verification verdict remain
with the primary agent and its separately assigned reviewer. No cleanup was
performed by this agent.
