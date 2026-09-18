# STM32 Toolkit 1.0 Monitor replay regression slice

This report records the bounded replay and physical-publication test slice. It
does not accept the slice or the local release; independent review and the
release-level coverage combination remain pending.

## Ledger

- Accepted integration base: `bab6c8e8d698aa3bddd88a0d20e94a7864980633`
- Frozen product/artifact CodeHead: `15b1a70e9bd684285da5557104deff529f537e49`
- Test CodeHead before this report commit: `f21f829b618af22a233b3aa0811346ab5fd4d3d0`
- Branch: `codex/STM32TK-1.0-replay-contract-regressions`
- Implementer: `/root/monitor_replay_regressions` (bounded Luna/max test owner)
- Independent reviewer: required and pending; the implementer has not approved
  this diff.
- Owned files: `tools/stm32-monitor/tests/test_replay.py`,
  `tools/stm32-monitor/tests/test_physical_publication.py`, and this report.
- Product source remained read-only at the frozen CodeHead under
  `D:\codex-tmp\v10b-0918\r10\verify`.

## Contract scenarios covered

The tests exercise public replay and physical-publication behavior using the
existing fixtures and provider seams:

- External replay documents with drifted schema, source, physical-evidence
  marker, scenario role, binding label, typed value, or batch shape are refused
  before History or evidence publication.
- Public replay canonicalization rejects non-JSON, non-finite, and non-NFC
  values while valid document and `MonitorRunRef` values retain canonical
  round trips.
- Invalid and absent replay document sources are classified before mutation.
- Replay History query/provider failures are classified as environment failures
  without changing an existing publication; an append storage-integrity failure
  is classified as an operation conflict after the valid publication prefix.
- A bounded partial History page is rejected as an intent conflict before
  republication, and a root provider exception is classified without leaking
  provider text or mutating History.
- Physical History provider busy/corrupt results, repeated cursors, and wrong
  page shapes fail before physical roots are written with the contract's
  environment or integrity category.
- Physical TestRun provider exceptions are sanitized; public physical reference
  loading rejects invalid or absent authority; persisted reference envelope
  drift is rejected as evidence-integrity failure.

## Verification

The final affected-module run used the requested Python and unchanged source
roots. It exited `0` with `95 passed` and no stderr output.

```text
"D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe" -m pytest tools/stm32-monitor/tests/test_replay.py tools/stm32-monitor/tests/test_physical_publication.py -q -p "no:cacheprovider" --basetemp "D:\codex-tmp\v10b-0918\r10\t\re\final2-20260919\basetemp" --junitxml "D:\codex-tmp\v10b-0918\r10\e\replay-regressions\final2-20260919\junit.xml" --cov=stm32_monitor.replay --cov-branch --cov-report "json:D:\codex-tmp\v10b-0918\r10\e\replay-regressions\final2-20260919\coverage.json" --cov-report term-missing --cov-fail-under=0
```

The retained evidence directory is
`D:\codex-tmp\v10b-0918\r10\e\replay-regressions\final2-20260919` and
contains `command.txt`, `environment.json`, `exit.txt`, `stdout.txt`,
`stderr.txt`, `junit.xml`, and `coverage.json`. The binary coverage database
is `D:\codex-tmp\v10b-0918\r10\t\re\final2-20260919\.coverage`. The
recorded child tempfile directory and pytest basetemp are both under
`D:\codex-tmp\v10b-0918\r10\t\re\final2-20260919`.

Scoped replay source attribution from the retained `coverage.json` is:

| Metric | Covered | Total | Ratio |
| --- | ---: | ---: | ---: |
| Statements | 915 | 1196 | 76.505% |
| Branches | 248 | 404 | 61.386% |
| Statements plus branches | 1163 | 1600 | 72.688% |

The unchanged pre-existing aggregate has `2394/2936` Monitor branches
(`81.54%`). The scoped run is informational and does not claim the release
gate. The replay source still has 156 uncovered branches and 281 uncovered
statements in this run; remaining paths are defensive parser/model cases,
provider/race outcomes, and physical/publication conditions outside the
approved caller scenarios. The verification owner must combine valid coverage
by one source identity before making any release-level statement.

## Retained initial failures

- `D:\codex-tmp\v10b-0918\r10\e\replay-regressions\focused-20260919`
  exited `4` because the first focused harness invocation did not quote its
  `-k` expression; no product test ran.
- `D:\codex-tmp\v10b-0918\r10\e\replay-regressions\after-tests-20260919`
  exited `1` with `92 passed, 2 failed`. Both were test assertion/setup
  corrections: one inspected History while the provider monkeypatch was still
  active, and one expected `OPERATION_CONFLICT` for a History query failure
  whose public contract maps to `ENVIRONMENT_FAILURE`. The corrected run above
  passes without a product change.

No product contradiction was found in this slice. No hardware, packaging,
deployment, remote action, or release acceptance was performed.
