# STM32TK 1.0 Monitor Analysis evidence-contract regressions

Status: implementation complete; independent review and primary acceptance are
pending. This is a test-only slice for the approved Analysis model, workflow,
and CLI contracts.

## Fixed identities

- Accepted integration base: `bab6c8e8d698aa3bddd88a0d20e94a7864980633`.
- Frozen product CodeHead: `15b1a70e9bd684285da5557104deff529f537e49`.
- Test CodeHead before this report commit: `9b8590c631c12e7ea1c8b13fe329f1229c072e67`.
- Branch: `codex/STM32TK-1.0-analysis-contract-regressions`.
- Actor: `desktop-8s1m8fb\zhangyang`.
- Interpreter: `D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe`,
  Python 3.12.10, pytest 8.4.2.

The product-source attribution record is
`D:\codex-tmp\v10b-0918\r10\e\analysis-regressions\product-source-equality.json`.
The three Analysis/CLI product blobs in this worktree and the final `r10\verify`
checkout match the frozen product head. The record also compares LF-normalized
source bytes to keep checkout line endings out of the product identity check.

## Test changes

Only the three owned existing test modules changed:

- `tools/stm32-monitor/tests/test_analysis.py` covers native request closure
  and physical-reference admission, bounded native alignment with an excluded
  position, and continuation lineage requiring distinct sessions and a source
  change declaration; the changed-firmware reference is the positive setup for
  that lineage.
- `tools/stm32-monitor/tests/test_analysis_workflows.py` covers source-diff
  provider failure without bundle mutation and distinct corrupt-history versus
  unavailable-history error mapping before derived publication.
- `tools/stm32-monitor/tests/test_analysis_cli.py` covers sanitized provider
  failure mapping without leaking exception text or private paths.

The tests reuse the existing replay, physical-reference, history, evidence and
target-run fixtures without changing shared helper signatures or fixture bytes.
No product module, dependency, schema, configuration, coverage threshold or
exclusion changed.

## Verification

The focused new-case check ran seven collected cases and passed:

```text
D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe -m pytest -o addopts= -o cache_dir=D:\codex-tmp\v10b-0918\r10\t\an\selected\cache --basetemp D:\codex-tmp\v10b-0918\r10\t\an\selected\basetemp -q D:\codex-tmp\v10b-0918\r10\av\tools\stm32-monitor\tests\test_analysis.py::test_native_request_rejects_legacy_references_and_invalid_contract_fields D:\codex-tmp\v10b-0918\r10\av\tools\stm32-monitor\tests\test_analysis.py::test_native_alignment_returns_inconclusive_when_pairing_skew_excludes_a_position D:\codex-tmp\v10b-0918\r10\av\tools\stm32-monitor\tests\test_analysis.py::test_continuation_lineage_requires_distinct_sessions_and_changed_firmware D:\codex-tmp\v10b-0918\r10\av\tools\stm32-monitor\tests\test_analysis_workflows.py::test_export_analysis_bundle_maps_source_provider_failure_without_bundle_mutation D:\codex-tmp\v10b-0918\r10\av\tools\stm32-monitor\tests\test_analysis_workflows.py::test_history_provider_failures_are_classified_before_derived_publication D:\codex-tmp\v10b-0918\r10\av\tools\stm32-monitor\tests\test_analysis_cli.py::test_analysis_provider_failure_is_sanitized_without_exception_or_path_leak
```

It produced `7 passed in 4.70s`, exit 0. Its exact command, bound temporary
variables, child `tempfile.gettempdir()`, stdout, stderr and exit record are
retained as `selected-command.txt`, `selected-environment.json`,
`selected.stdout.txt`, `selected.stderr.txt` and `selected-exit.json` under
`D:\codex-tmp\v10b-0918\r10\e\analysis-regressions\`.

After review, the provider-failure CLI case was rerun alone with a call
sentinel to prove that the patched `compare_monitor_runs` seam was reached:
`test_analysis_provider_failure_is_sanitized_without_exception_or_path_leak`
passed, exit 0. The original focused seven-case result and the affected
88-case result below remain the retained slice evidence; this correction did
not change product source bytes or the retained coverage database.

The required affected-module run used the final product source roots on
`PYTHONPATH`, bound `TEMP`, `TMP` and `TMPDIR` to
`D:\codex-tmp\v10b-0918\r10\t\an\full\temp`, and set `COVERAGE_FILE` to
`D:\codex-tmp\v10b-0918\r10\t\an\full\analysis.coverage`:

```text
D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe -m pytest -o addopts= -o cache_dir=D:\codex-tmp\v10b-0918\r10\t\an\full\cache --basetemp D:\codex-tmp\v10b-0918\r10\t\an\full\basetemp -q D:\codex-tmp\v10b-0918\r10\av\tools\stm32-monitor\tests\test_analysis.py D:\codex-tmp\v10b-0918\r10\av\tools\stm32-monitor\tests\test_analysis_workflows.py D:\codex-tmp\v10b-0918\r10\av\tools\stm32-monitor\tests\test_analysis_cli.py --cov=stm32_monitor --cov-branch --cov-report=term-missing --cov-report=json:D:\codex-tmp\v10b-0918\r10\e\analysis-regressions\affected.coverage.json --cov-fail-under=0 --junitxml D:\codex-tmp\v10b-0918\r10\e\analysis-regressions\affected.junit.xml
```

The affected run passed 88 tests in 40.95 seconds, exit 0. Stderr was empty;
the three collection warnings are retained in the stdout record and did not
fail tests. JUnit, branch coverage JSON, stdout, stderr, command, environment
and exit records are under
`D:\codex-tmp\v10b-0918\r10\e\analysis-regressions\`.

Coverage is informational and is reported as statements, branches and the
combined statement-plus-branch ratio. It is not a line-coverage label or a
release gate:

- Analysis: 599/718 statements (83.43%), 216/294 branches (73.47%), combined
  80.53%.
- Analysis workflows: 473/707 statements (66.90%), 131/220 branches (59.55%),
  combined 65.16%.
- CLI: 203/299 statements (67.89%), 27/66 branches (40.91%), combined 63.01%.

The exact derived summary is retained in
`D:\codex-tmp\v10b-0918\r10\e\analysis-regressions\coverage-summary.json`;
the source branch database is
`D:\codex-tmp\v10b-0918\r10\t\an\full\analysis.coverage`.

No hardware, deployment, package build, remote action or cleanup attempt was
performed. The separately diagnosed Toolkit Diagnostic failures and the
unchanged release-level coverage gate remain outside this test-only slice and
are retained for the primary integration and verification owners.
