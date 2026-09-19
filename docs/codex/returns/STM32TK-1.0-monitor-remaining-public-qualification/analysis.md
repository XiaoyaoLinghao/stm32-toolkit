# Analysis public model qualification return

Slice: STM32TK-1.0 Monitor Analysis public models/scalars  
Branch: `codex/STM32TK-1.0-analysis-model-qualification`  
Accepted base: `87699308535bd36431c2e44be8bf131e245d460d`  
Code head before this report commit: `714f63ea578ac5acd53b273b63ad78d385887ad2`

The implementation changes only `tools/stm32-monitor/tests/test_analysis.py`.
The new public cases use the existing replay and physical reference helpers,
ordinary finite scalar values, and copy-based payload edits. No production,
schema, dependency, coverage configuration, or shared helper changed.

| Missing public arc | Caller trigger added | Expected public result and state assertion |
|---|---|---|
| `analysis.py:299-303` | `AnalysisRequest.from_value` with an unknown request schema | `AnalysisError.code == ANALYSIS_REQUEST_INVALID`; no request is accepted |
| `analysis.py:329-333` | Native request constructor and parser with boolean `max_pairing_skew_ns` | `ANALYSIS_REQUEST_INVALID`; the valid native request remains unchanged |
| `analysis.py:357-378` | Request parser with a malformed persisted `before_run` object | `ANALYSIS_REQUEST_INVALID`; malformed reference authority is not adopted |
| `analysis.py:517-518` | `AnalysisComputation.from_value` given the exact typed computation | Returns the same object by identity |
| `analysis.py:427-513` | Computation schema/state/reason, pair/exclusion counts, changed type, missing or malformed statistics, valid/degraded exclusion consistency | Constructor and parser both refuse with `ANALYSIS_REQUEST_INVALID`; no invalid computation is returned |
| `analysis.py:492-499` | Finite `+/-1.7976931348623157e308` statistics whose subtraction overflows to infinity | `ANALYSIS_REQUEST_INVALID`; finite inputs cannot publish non-finite deltas |
| `analysis.py:842-853` | Result constructor with an unknown schema or non-lineage identity | `ANALYSIS_REQUEST_INVALID`; the original result and request digest remain unchanged |
| `analysis.py:906-911` | `AnalysisResult.new` with each of request/computation/lineage replaced by an arbitrary object | `ANALYSIS_REQUEST_INVALID`; no result is constructed |
| `analysis.py:931-932` | `AnalysisResult.from_value` given the exact typed result | Returns the same object by identity |
| `analysis.py:887-890` | Native persisted result whose embedded request threshold conflicts with completed or inconclusive state | `ANALYSIS_REQUEST_INVALID`; neither contradictory result is accepted |

The legacy `AnalysisResult` request-carrying branch at `analysis.py:881-882`
is intentionally not manufactured: a non-`None` request selects result/3 in
the preceding expected-schema calculation, while the closed legacy parser
rejects an extra `request` field. There is no caller-visible construction that
reaches that branch without bypassing the public contract.

## Verification

Test execution: `NOT_RUN` by the current-wave instruction. No pytest,
collect-only run, package import, build, install, hardware, cleanup, or remote
operation was performed.

AST syntax inspection only, with `TEMP`, `TMP`, and `TMPDIR` bound to the
approved D-drive temporary path:

```text
D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe -I -c "import ast, pathlib; p=pathlib.Path(r'tools/stm32-monitor/tests/test_analysis.py'); ast.parse(p.read_text(encoding='utf-8')); print('AST_OK', p)"
AST_OK tools\stm32-monitor\tests\test_analysis.py
exit code: 0
```

Coverage gain is intentionally unreported until the primary-owned selected
node run produces retained native evidence. Independent review and serial
execution remain primary-owned.
