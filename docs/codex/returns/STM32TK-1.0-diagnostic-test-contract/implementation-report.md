# STM32TK 1.0 Diagnostic persisted-analysis contract correction

Status: the bounded test correction is implemented and locally verified;
independent review and primary acceptance remain pending. Product behavior is
unchanged.

## Fixed identities

- Accepted integration base: `eb4958add2c0133457e40b218400376143ffccb7`.
- Frozen product CodeHead: `15b1a70e9bd684285da5557104deff529f537e49`.
- Test CodeHead before this report commit: `edd5d5b77f3728020e1921ceafe1026e229c1164`.
- Branch: `codex/STM32TK-1.0-diagnostic-test-contract`.
- Actor: `desktop-8s1m8fb\zhangyang`.
- Interpreter: `D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe`,
  Python 3.12.10.

## Bounded correction

Only `tools/stm32-toolkit/tests/test_fix_verification_workflows.py` changed.
The completion corruption case now snapshots authority after replacing the
authenticated native-analysis root with malformed bytes and before the public
operation. It asserts `ok is False`, code
`DIAGNOSTIC_CHAIN_CORRUPT`, `data is None`, and an unchanged authority
snapshot. This preserves the full `DiagnosticStore.load` fail-closed contract
and proves that no completion event or other authority record is appended.

The `absent-analysis-root` attach matrix entry now expects the same
`DIAGNOSTIC_CHAIN_CORRUPT` code. Its existing before/after evidence and
Diagnostic tree snapshots still assert no mutation. All other matrix mappings
and the fresh-store native-artifact rejection test remain unchanged.

## Verification

The only test run after the correction used the r10 Python 3.12 interpreter and
the final product source roots from `r10\verify`:

```text
D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe -m pytest -o addopts= -o cache_dir=D:\codex-tmp\v10b-0918\r10\t\ds\focused-r2\cache --basetemp D:\codex-tmp\v10b-0918\r10\t\ds\focused-r2\basetemp -q D:\codex-tmp\v10b-0918\r10\ds\tools\stm32-toolkit\tests\test_fix_verification_workflows.py::test_task7b_completion_deterministic_outcome_priority_and_zero_mutation D:\codex-tmp\v10b-0918\r10\ds\tools\stm32-toolkit\tests\test_fix_verification_workflows.py::test_target_replay_attach_fail_closed_matrix_preserves_complete_authority[absent-analysis-root-DIAGNOSTIC_CHAIN_CORRUPT] D:\codex-tmp\v10b-0918\r10\ds\tools\stm32-toolkit\tests\test_continuation_monitor.py::test_diagnostic_store_rejects_missing_same_session_native_artifact --junitxml D:\codex-tmp\v10b-0918\r10\e\diagnostic-regressions\focused-r2.junit.xml
```

`TEMP`, `TMP` and `TMPDIR` were all
`D:\codex-tmp\v10b-0918\r10\t\ds\focused-r2\temp`; pytest cache and
basetemp used the paths shown above, and `COVERAGE_FILE` was
`D:\codex-tmp\v10b-0918\r10\t\ds\focused-r2\diagnostic.coverage`.
The child interpreter reported the same `tempfile.gettempdir()` and the exact
production `PYTHONPATH` in
`D:\codex-tmp\v10b-0918\r10\e\diagnostic-regressions\focused-r2-environment.json`.

Result: `3 passed in 79.02s`, exit 0, stderr empty. Exact command, environment,
stdout, stderr, exit and JUnit records are retained under
`D:\codex-tmp\v10b-0918\r10\e\diagnostic-regressions\focused-r2-*`.

The original two-failure diagnosis and retained failure evidence remain under
`D:\codex-tmp\v10b-0918\r10\e\python-release\monitor-cross\`, including
`contract-review.md`, `failure-diagnosis.md`, `junit.xml` and `stdout.txt`.
The complete Toolkit suite was not rerun.

No product source, dependency, configuration, hardware, deployment, package,
remote or cleanup action was performed. This report does not claim independent
review or release acceptance.
