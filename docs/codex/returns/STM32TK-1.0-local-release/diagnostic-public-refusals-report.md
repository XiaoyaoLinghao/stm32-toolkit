# STM32TK 1.0 local release: Diagnostic public refusal qualification

## Scope

This bounded, test-only slice qualifies the two additional public Diagnostic refusal scenarios in the 1.0 local release plan:

1. Completion of prepared cross-state verification must read the required analysis or marker artifact through the completion evidence provider. An `OSError` from that provider returns `ENVIRONMENT_FAILURE`, leaves the authority snapshot unchanged, and proves that completion evidence was reached after the earlier Store authorization path.
2. `DiagnosticSession.from_value` must reject valid nested objects whose lifecycle or cross-object bindings contradict the public session contract. The returned codes are the existing `DIAGNOSTIC_PLAN_INVALID` and `DIAGNOSTIC_INVALID_EVENT` codes, and the caller's input mapping remains unchanged.

The tests reuse `_prepared_cross_state_operations`, `_authority_snapshot`, `_verifying`, and the existing valid builders. The new contradiction payloads preserve valid nested hashes and exercise only public lifecycle or binding contradictions. No product source, integration code, hardware, build, package, deploy, or remote state was changed.

The accepted integration base is `04bdd539597ec8dcb38bca34eb2256e970ecaa25`. Product imports were pinned to the frozen verification sources at product revision `15b1a70e9bd684285da5557104deff529f537e49`:

```text
D:\codex-tmp\v10b-0918\r10\verify\tools\stm32-toolkit\src
D:\codex-tmp\v10b-0918\r10\verify\tools\stm32-monitor\src
```

The implementation code head before this report commit was `8a5c48764a5577cefa3ba169194203e72e30e33e` (`fbe36025` added the bounded cases and `8a5c4876` corrected the test case builder). This report intentionally records no report-commit SHA.

## Qualification coverage

The completion test has two parameterized cases, `analysis` and `marker`. It enters the public completion evidence reader, then injects an `OSError` only for the selected prepared artifact. Each case asserts the stage sentinel, the exact artifact provider call, `ok is False`, `ENVIRONMENT_FAILURE`, `data is None`, and an unchanged `_authority_snapshot`.

The `DiagnosticSession.from_value` test has thirteen parameterized cases. Ten public binding contradictions return `DIAGNOSTIC_PLAN_INVALID`: missing active plan while verifying, an investigating session with an active plan, plan/session mismatch, plan/declaration mismatch, plan-id mismatch, an unclaimed marker, and fix plan/declaration/run/evidence mismatches. Three lifecycle contradictions return `DIAGNOSTIC_INVALID_EVENT`: OPEN with lifecycle data, FIX_PROPOSED without a declaration, and RESOLVED without a passed fix. Every case deep-copies the payload and asserts that the input is unchanged after refusal.

The reuse audit at `D:\codex-tmp\v10b-0918\r10\e\python-release\coverage-reuse-audit.md` recorded no prior combined binary coverage for these new `DiagnosticSession.from_value` or completion-provider scenarios. The audit caveat about pytest-cov child-process combination does not add subprocess work to this slice; these cases are ordinary focused in-process tests.

## Verification

The required pinned interpreter was used. Before pytest, `TEMP`, `TMP`, and `TMPDIR` were explicitly bound under the run root and a child process containment check was run against `childtempcheck`. The exact environment is recorded in `r2\environment.json`.

The final bounded invocation was recorded in:

```text
D:\codex-tmp\v10b-0918\r10\e\diagnostic-public-refusals\r2\command.txt
```

```text
D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe -m pytest -o addopts='' -o cache_dir=D:\codex-tmp\v10b-0918\r10\t\dp\r2\pytest-cache --basetemp D:\codex-tmp\v10b-0918\r10\t\dp\r2\basetemp --junitxml D:\codex-tmp\v10b-0918\r10\e\diagnostic-public-refusals\r2\junit.xml --cov=stm32_toolkit --cov=stm32_monitor --cov-branch --cov-fail-under=0 --cov-report=term-missing --cov-report=json:D:\codex-tmp\v10b-0918\r10\e\diagnostic-public-refusals\r2\coverage.json tests/test_fix_verification_workflows.py::test_task7b_completion_artifact_provider_oserror_is_environment_failure_without_mutation tests/test_fix_verification_events.py::test_diagnostic_session_from_value_rejects_public_lifecycle_and_crossbinding_contradictions
```

Result:

```text
collected 15 items
15 passed in 39.32s
pytest exit code: 0
```

The focused run enabled branch coverage and wrote the full report to `r2\coverage.json`; its broad two-package subset total was 18%. `--cov-fail-under=0` was used because the release 90% threshold is an aggregate release gate and is not a valid threshold for this bounded node selection. JUnit output is at `r2\junit.xml`; stdout, stderr, exit code, command, environment, and child containment evidence are retained under `D:\codex-tmp\v10b-0918\r10\e\diagnostic-public-refusals\r2`.

The child containment check passed with exit code 0 and reported `tempfile` under:

```text
D:\codex-tmp\v10b-0918\r10\t\dp\r2\tmpdir\childtempcheck
```

## Earlier invocation evidence

The first invocation used an unsupported `--cache-dir` pytest option and exited 4 before collection. Its command, stdout, stderr, and exit evidence are preserved in the diagnostic refusal evidence root; this is an infrastructure command error and provides no behavior result.

The next invocation collected the same 15 nodes and reached 14 passes plus one `UnboundLocalError` in the newly added `plan-declaration-mismatch` test builder. The inherited module `fail-under=90` setting also rejected that focused subset. The raw `corrected-*` files are preserved. The builder was corrected in the bounded test file, and the same two selectors were rerun with `--cov-fail-under=0`; no broader module or suite rerun was performed.

This report is implementation evidence only. Independent review of the complete accepted-base-to-code-head diff and acceptance remain with the primary agent or another reviewer; the implementation agent does not accept its own changes.
