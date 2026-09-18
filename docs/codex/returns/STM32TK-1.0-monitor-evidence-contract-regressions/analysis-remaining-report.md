# STM32TK 1.0 remaining Monitor Analysis public-contract regressions

Status: first review returned `REVISION_REQUIRED`; the first correction round
has been implemented and its released verification evidence is recorded below.
Independent review and primary acceptance remain pending. This remains a
test-only slice for the approved Analysis model, workflow and durable-publication
contracts.

## Fixed identities

- Accepted integration base: `39bf982af688b7653735b0de02ce75a19804c2b4`.
- Test worktree start: `47988d34725f97075d3ea69a43a65cb5b2144189`.
- Frozen product CodeHead: `15b1a70e9bd684285da5557104deff529f537e49`.
- Test CodeHead before this report commit: `575be6f8bd451e2dd70508ae4fe9a8ea914549a6` (`bc160a8a94e815c7d387fdb061e0e7006d9a919f` is the prior correction-round test head).
- Branch: `codex/STM32TK-1.0-analysis-remaining`.
- Worktree: `D:\codex-tmp\v10b-0918\r10\am`.
- Implementation owner: Luna/max Analysis slice owner.
- Independent reviewer and primary acceptance: pending; this report does not
  self-accept the implementation.

The required product source for the later run is the frozen verification
checkout under `D:\codex-tmp\v10b-0918\r10\verify`:

```text
D:\codex-tmp\v10b-0918\r10\verify\tools\stm32-monitor\src
D:\codex-tmp\v10b-0918\r10\verify\tools\stm32-toolkit\src
```

No product source, schema, dependency or lockfile changed in this slice.

## Test changes

Only the two owned existing Analysis test modules changed:

- `tools/stm32-monitor/tests/test_analysis.py` adds public request/lineage and
  embedded-result binding contradictions, exact window count/order/end-boundary
  and replay-group authority failures, and malformed typed-value shape/control
  cases that are excluded by the scalar policy.
- `tools/stm32-monitor/tests/test_analysis_workflows.py` adds closed bundle
  artifact and publication graph binding checks, History page partial/order/
  repeated-cursor authority checks, an additional storage-provider code and
  `OSError` classification with call sentinels, a derived artifact identity
  failure seam, and a target TestRun provider failure seam.

The tests use public constructors, `analyze_monitor_windows`,
`HistoryStore.query_history`, `EvidenceStore.ingest_file` and
`TestRunRepository.load`. Valid `HistoryPage` and `HistoryBatchSlice` values
are returned through the provider seam; states rejected by the public page
model were not fabricated. Provider cases assert that the seam was reached,
the stable public error category is returned, private exception text is not
leaked, and no derived root/bundle mutation occurs. Existing fixture helper
signatures/defaults and fixture bytes are unchanged. No generic matrix
framework, private product helper call, threshold, schema, CLI, hardware,
deployment or package operation was added.

The one-line follow-up test commit `c23573c4` changes the deliberately
shortened replay digest sequence from a Python tuple to a JSON list before
passing it to the public canonical replay parser. It does not alter product
code or the scenario contract.

The first independent review at `D:\\codex-tmp\\v10b-0918\\r10\\e\\analysis-remaining\\independent-review.md`
returned `REVISION_REQUIRED`. Test commit
`bc160a8a94e815c7d387fdb061e0e7006d9a919f` prepared the bounded correction
round, and test commit `575be6f8bd451e2dd70508ae4fe9a8ea914549a6` corrected the
reopened-batch cursor construction after the first released correction run:

- The repeated-cursor provider now returns a structurally valid second
  `HistoryPage` whose last ordinal matches the repeated cursor, records the
  cursor supplied to the second public seam call, and uses a different valid
  batch key so the cursor check is reached before a slice contradiction.
- Cross-linked publication tests build each altered `DiagnosticMarker` with
  public `DiagnosticMarker.new`, round-trip it through `from_value`, and then
  assert the publication-level analysis and evidence relations. The marker
  IDs are recomputed by the public constructor.
- Persisted lineage/result cases now cover invalid lineage schema, native
  result schema mismatch, native request schema mismatch, native request run
  binding mismatch, and native result lineage mismatch. A v1 continuation
  field is tested through the closed wire and the public constructor. A legacy
  wire carrying `request` is recorded as a closed-field rejection: the public
  parser selects the legacy field set before construction, while the result
  constructor derives schema v3 whenever a request exists, so the legacy
  `request is not None` branch cannot be reached without forging an impossible
  typed state.
- Public History provider scenarios now prepare valid multi-page responses for
  reopening a closed batch key, changing a static slice tuple, exceeding the
  aggregate 10,000-value limit across pages, leaving a declared batch
  incomplete, and changing the authenticated binding. Each expects
  `INCOMPATIBLE_IDENTITY`, records provider calls, and checks that no derived
  analysis root is written.

The reopened-batch scenario initially used the same legacy cursor batch ID for
the first and second pages, so the public pagination loop correctly rejected it
as a repeated cursor before the intended third-page closed-key check. The
follow-up test commit changes only that second page's structurally valid public
cursor to batch ID `2`; the narrow rerun then reaches the third page and the
closed-key branch without forging a `HistoryPage`.

The previously retained `valid88passed+1` correction-node evidence remains
authoritative historical evidence and is not replaced by this slice.

## Verification state

No test, build, browser, coverage or large-copy command was run while the
retention-diagnosis exclusive window was active. The primary released that
window before the following verification. All run files are retained under
`D:\codex-tmp\v10b-0918\r10\e\analysis-remaining` and the run-scoped
cache, basetemp, coverage database and child temp directories are under the
historical `D:\codex-tmp\v10b-0918\r10\t\an2` root or the correction
round's new `D:\codex-tmp\v10b-0918\r10\t\an2-rev1` suffix.

The first post-release invocation was an infrastructure failure before test
collection: exit code `4` because the command used the invalid
`--cov-report=json=...` spelling. Its real command text, empty stdout, parser
stderr and exit record are retained as `run-command.txt`, `run.stdout.txt`,
`run.stderr.txt` and `run-initial-exit.json`. No product or test code ran in
that invocation.

The corrected full two-module invocation was recorded verbatim in
`run-corrected-command.txt`:

```text
D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe -m pytest -o addopts= -o cache_dir=D:\codex-tmp\v10b-0918\r10\t\an2\cache --basetemp D:\codex-tmp\v10b-0918\r10\t\an2\basetemp-corrected -q D:\codex-tmp\v10b-0918\r10\am\tools\stm32-monitor\tests\test_analysis.py D:\codex-tmp\v10b-0918\r10\am\tools\stm32-monitor\tests\test_analysis_workflows.py --cov=stm32_monitor --cov-branch --cov-report=term-missing --cov-report=json:D:\codex-tmp\v10b-0918\r10\e\analysis-remaining\affected.coverage.json --cov-fail-under=0 --junitxml D:\codex-tmp\v10b-0918\r10\e\analysis-remaining\affected.junit.xml
```

Against frozen product source imported only through `PYTHONPATH` from
`D:\codex-tmp\v10b-0918\r10\verify`, that invocation exited `1` after
`92 passed`, `1 failed`, `3 warnings` in `41.67s`. The failed test was a test
construction error: the new shortened public replay reference used a tuple,
which the frozen public canonical replay contract correctly rejects. The
complete stdout, stderr, JUnit and scoped coverage JSON are retained as
`run-corrected.stdout.txt`, `run-corrected.stderr.txt`, `affected.junit.xml`
and `affected.coverage.json`; `run-corrected-exit.json` records the exact
result.

After the one-line test correction in `c23573c4`, the failed scenario was
rerun narrowly with this recorded command:

```text
D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe -m pytest -o addopts= -o cache_dir=D:\codex-tmp\v10b-0918\r10\t\an2\cache-correction --basetemp D:\codex-tmp\v10b-0918\r10\t\an2\basetemp-correction -q D:\codex-tmp\v10b-0918\r10\am\tools\stm32-monitor\tests\test_analysis.py::test_public_window_reference_authority_rejects_count_order_and_boundary_contradictions --cov=stm32_monitor --cov-branch --cov-report=term-missing --cov-report=json:D:\codex-tmp\v10b-0918\r10\e\analysis-remaining\narrow-correction.coverage.json --cov-fail-under=0 --junitxml D:\codex-tmp\v10b-0918\r10\e\analysis-remaining\narrow-correction.junit.xml
```

That narrow run exited `0` with `1 passed` in `2.38s`; its stdout, stderr,
JUnit, coverage JSON and exit record are retained under the corresponding
`run-narrow-correction.*`, `narrow-correction.*` files. The child environment
record confirms `tempfile.gettempdir()`, `TEMP`, `TMP` and `TMPDIR` all resolve
to `D:\codex-tmp\v10b-0918\r10\t\an2\temp`.

After the independent review and release of the backend benchmark, the
correction nodes were run once with the exact nine explicit node arguments in
`run-review-correction-command.txt`. The command used the frozen product
sources through `PYTHONPATH`, `--cov=stm32_monitor`, `--cov=stm32_toolkit`,
and the valid `--cov-report=json:<path>` form. It exited `1` after `8 passed,
1 failed` in `17.33s`. The failed node was
`test_history_multipage_reopened_batch_is_rejected_before_derived_publication`:
the test supplied the same legacy cursor token on pages one and two, so the
public pagination loop correctly reached the repeated-cursor error before the
intended third-page closed-key check and the test observed two provider calls
instead of three. This is a test construction failure, not a product failure;
the complete stdout, stderr, JUnit, exit record and combined coverage JSON are
retained as `run-review-correction.stdout.txt`,
`run-review-correction.stderr.txt`, `review-correction.junit.xml`,
`run-review-correction-exit.json` and `review-correction.coverage.json`.

Test commit `575be6f8bd451e2dd70508ae4fe9a8ea914549a6` changed that second
page's valid cursor batch ID from `1` to `2`. The changed node was then run
once with the exact command in `run-reopened-fix-command.txt`, using new
`cache-reopened-fix`, `basetemp-reopened-fix`, `temp-reopened-fix` and
`review-reopened-fix.coverage` paths beneath the correction suffix. It exited
`0` with `1 passed` in `12.41s`; the JUnit contains one passing testcase and
stderr is empty. The retained stdout, stderr, JUnit, exit record, environment
record and coverage JSON are `run-reopened-fix.stdout.txt`,
`run-reopened-fix.stderr.txt`, `review-reopened-fix.junit.xml`,
`run-reopened-fix-exit.json`, `review-reopened-fix-environment.json` and
`review-reopened-fix.coverage.json`. The valid second cursor lets the public
loop reach the third page, where the reopened closed batch key is rejected
with the exact public `INCOMPATIBLE_IDENTITY` error before derived publication.

The scoped `--cov-fail-under=0` results are informational and cannot be
reported as the unchanged `>=90%` release PASS. Since the full two-module run
predates this review correction round, this report retains the exact prior
`92 + 1` full-run result, the correction-round `8 passed + 1 test-construction
failure` result, and the final corrected scenario result. It makes no claim of
a post-correction full-module PASS. Earlier accepted coverage and the retained
`valid88passed+1` correction-node evidence remain available to the primary
verification owner; this slice did not rerun either full module.

No cleanup, remote operation, hardware access, deployment, package build or
self-review was performed.
