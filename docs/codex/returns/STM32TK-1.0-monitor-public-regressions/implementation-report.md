# STM32TK 1.0 Monitor public regressions

Status: implementation complete; independent review and primary acceptance are
pending. This slice adds test-only evidence for four approved public scenarios.

## Fixed identities

- Accepted product base: `15b1a70e9bd684285da5557104deff529f537e49`.
- Product CodeHead under test: `15b1a70e9bd684285da5557104deff529f537e49`.
- Test CodeHead before this report commit: `84fabf629a685620575ae235f58faa657de900d1`.
- Branch: `codex/STM32TK-1.0-monitor-public-regressions`.
- Actor: `desktop-8s1m8fb\zhangyang`.
- Interpreter: `D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe`,
  Python 3.12.10, pytest 8.4.2.

The product source equality record is
`D:\codex-tmp\v10b-0918\r10\e\monitor-gaps\product-source-equality.json`.
It compares the CLI, ProbeSession and Sampler product blobs in the test
worktree and the final `r10\verify` checkout with the accepted product head;
all six comparisons match.

## Test changes

Only these existing test modules changed:

- `tools/stm32-monitor/tests/test_cli.py`: public replay adapter rejects an
  invalid project context with a sanitized protocol result before workflow
  input is opened; test-local workflow and JSON-loader sentinels also assert
  that neither side effect was invoked.
- `tools/stm32-monitor/tests/test_probe_session.py`: catalog invalid-query
  versus provider-loss mapping, plus invalid preparation and changed-watch
  plan refusal without a backend read.
- `tools/stm32-monitor/tests/test_sampler.py`: start/resume plan-preparation
  failure lifecycle, more-than-256-watch refusal, and a delivery stream made
  after close terminating promptly through the existing bounded `_next`
  helper.

The tests reuse the existing `FakeObservation`, `FakeGroups`, `FakeHistory`,
binding and temporary-project fixtures. They exercise public methods and assert
observable result/state and absence of sampling/backend side effects. No product
code, dependency, framework, coverage threshold or exclusion changed.

## Verification

The affected-module command was run with all three temporary variables bound to
the short task root and with the final product source roots on `PYTHONPATH`:

```text
D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe -m pytest -o addopts= -o cache_dir=D:\codex-tmp\v10b-0918\r10\t\monitor-gaps\cache-r2 --basetemp D:\codex-tmp\v10b-0918\r10\t\monitor-gaps\basetemp-r2 -q D:\codex-tmp\v10b-0918\r10\mg\tools\stm32-monitor\tests\test_cli.py D:\codex-tmp\v10b-0918\r10\mg\tools\stm32-monitor\tests\test_probe_session.py D:\codex-tmp\v10b-0918\r10\mg\tools\stm32-monitor\tests\test_sampler.py --cov=stm32_monitor --cov-branch --cov-report=term-missing --cov-report=json:D:\codex-tmp\v10b-0918\r10\e\monitor-gaps\affected-r2.coverage.json --cov-fail-under=0 --junitxml D:\codex-tmp\v10b-0918\r10\e\monitor-gaps\affected-r2.junit.xml
```

Environment and child `tempfile.gettempdir()` are recorded in
`affected-r2.environment.json`. The run passed 76 tests: CLI 14, ProbeSession
16 and Sampler 46, in 18.62 seconds, exit 0. JUnit, coverage JSON, stdout,
stderr, command and exit records are retained under
`D:\codex-tmp\v10b-0918\r10\e\monitor-gaps\`.

The informational affected-only coverage result was reported from the
`affected-r2.coverage.json` data as statements, branches and their combined
total. CLI was 187/299 statements (62.54%), 14/66 branches (21.21%), combined
55.07%. ProbeSession was 218/266 statements (81.95%), 63/80 branches (78.75%),
combined 81.21%. Sampler was 459/480 statements (95.625%), 136/164 branches
(82.93%), combined 92.39%. This is not a release-gate measurement; the
verification owner must combine it with the unchanged full suite using the
recorded source equality.

The affected-r2 run did not set `COVERAGE_FILE`; coverage.py therefore wrote
the default database at
`D:\codex-tmp\v10b-0918\r10\mg\.coverage`. Its preserved copy is
`D:\codex-tmp\v10b-0918\r10\t\monitor-gaps\coverage-r2.dat`. The SHA-256
for both files is
`AD383068923D856228332DFEF6C7CDFC21F2AFF30878539130D243FB74FF146A`.
`coverage-database-consistency.json` records `MATCH` for all 18 files without
rerunning tests.

Round2 review corrections were run separately against only the two changed
node IDs, with no coverage collection:

```text
D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe -m pytest -o addopts= -o cache_dir=D:\codex-tmp\v10b-0918\r10\t\monitor-gaps\round2\cache --basetemp D:\codex-tmp\v10b-0918\r10\t\monitor-gaps\round2\basetemp -q D:\codex-tmp\v10b-0918\r10\mg\tools\stm32-monitor\tests\test_cli.py::test_adapter_cli_rejects_invalid_project_context_before_workflow D:\codex-tmp\v10b-0918\r10\mg\tools\stm32-monitor\tests\test_sampler.py::test_delivery_subscription_created_after_close_terminates_promptly
```

The round2 stdout was `.. [100%]` and `2 passed in 2.84s`; stderr was empty
and the process exit code was 0. The exact argv, bound `TEMP`/`TMP`/`TMPDIR`
and child `tempfile.gettempdir()` are recorded in
`D:\codex-tmp\v10b-0918\r10\e\monitor-gaps\round2-command.txt`,
`round2-environment.json`, `round2.stdout.txt`, `round2.stderr.txt` and
`round2-exit.json`. The prior 76-pass affected-module evidence remains valid;
this targeted run only verifies the two review corrections.

No hardware, deployment, packaging, remote action or canonical evidence was
performed. The automatic cleanup policy rejected removal of this run's
`r10\t\monitor-gaps` temporary subdirectories; they were retained without a
workaround, while the evidence files remain preserved.
