# STM32TK-1001 Public Bind Observation Compatibility

Status: `RETURNED FOR INDEPENDENT SOL REVIEW`

This report records the software implementation and code-head evidence for the bounded
`STM32TK-1001 / VS10-A H2` public bind/read observation correction. It is deliberately separate
from the code commits and makes no acceptance claim. The independent GPT-5.6-sol primary owns
the complete-diff review and verdict.

## Ledger and ownership

- Accepted base: `52392e4910aea3a152b0d2dd4d3c4b7d61f8a410`
- Accepted-base tree: `28b94cb6d9f61df09adf593caedaee4226dc742f`
- Approved specification commit: `4d42c09b7d3b5cbcf100696328241590ecc7f8ba`
- Approved implementation-plan commit: `607769b8e09aa1cc91cf418d778def50aad074c4`
- Active branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`
- Remote baseline: `74ee5f4c7872af1bb612c9068af36319457e087b`
- Remote action: none authorized or taken
- Specification owner and independent final reviewer: GPT-5.6-sol primary
- Sole implementation owner: one GPT-5.6-luna agent at reasoning effort `max`

The code head before this report is exactly `daaee91894003434d2ab7c70edf0098bdbf375df`, with
tree `858d111a71e52dcf576afe9d2432335ed5c1b2b6` and parent
`0d946d3d0e68c9d9436535a23957a686e71de823`. The report is the only intended change after that
code head; its future report-commit SHA is intentionally not recorded in this file.

## RED/GREEN lineage

The approved test-first sequence was preserved:

1. Task 1 RED commit `7d2726e57e5d47ef34069db2ae39fa033e744445` (`test(vs10a): define public
   observation profile`) added only the worker, hardware-workflow, and Monitor observation
   contracts. The fallback CPython 3.12.10/pytest 8.4.2 run collected 146 nodes: 142 passed,
   3 intended observation-profile failures, and 1 pre-existing skip. The named campaign runtime
   was CPython 3.12.10 but lacked pytest.
2. Task 2 RED commit `ed86b7284c3572d3486c698f12def5fe0b7c6acd` (`test(vs10a): distinguish public
   bind failures`) added only the firmware-bind and debug-read contracts. The fallback run
   collected 188 nodes: 157 passed and 31 intended structured/raw attachment-error failures.
   The failures showed the pre-existing broad catch collapsing structured Probe errors and raw
   attach failures to the old target-mismatch result. No accepted gate prevented isolating the
   attach stage.
3. Task 3 GREEN commit `0d946d3d0e68c9d9436535a23957a686e71de823` (`fix(vs10a): use proven public
   observation profile`) changed only the three observation-profile product files. Its focused
   fallback run collected 146 nodes: 145 passed and 1 pre-existing skip.
4. Task 4 GREEN/code commit `daaee91894003434d2ab7c70edf0098bdbf375df` (`fix(vs10a): preserve
   public bind probe errors`) changed only the two debug product files. The exact two-file fallback
   GREEN run collected 188 nodes and passed all 188. The first prescribed five-file order
   collected 334 nodes: 331 passed, 1 pre-existing skip, and 2 unchanged pyOCD-laziness failures.
   Independent re-review approved the debug-first order; a fresh five-file rerun in that order
   collected 334 nodes: 333 passed, 1 pre-existing skip, and 0 failures.

## Implemented scope

The complete accepted-base-to-code-head product/test change is limited to these ten paths:

Product:

- `tools/stm32-toolkit/src/stm32_toolkit/probe/worker.py`
- `tools/stm32-toolkit/src/stm32_toolkit/hardware_workflows.py`
- `tools/stm32-toolkit/src/stm32_toolkit/monitor_observation.py`
- `tools/stm32-toolkit/src/stm32_toolkit/debug/firmware.py`
- `tools/stm32-toolkit/src/stm32_toolkit/debug/read.py`

Tests:

- `tools/stm32-toolkit/tests/test_probe_worker.py`
- `tools/stm32-toolkit/tests/test_hardware_workflows.py`
- `tools/stm32-toolkit/tests/test_monitor_observation.py`
- `tools/stm32-toolkit/tests/test_debug_firmware.py`
- `tools/stm32-toolkit/tests/test_debug_read.py`

The product correction derives one immutable internal observation configuration at exactly
100 kHz with the existing normal halt-connect policy, preserving target profile and transport
provider. Only existing production `OBSERVE` construction points select it. `MODIFY`, `CONTROL`,
and explicit under-reset recovery retain their existing configurations, test-factory precedence is
preserved, and topology remains one Probe Service, one worker, and one backend.

Initial and final debug binding, plus every debug-read attachment guard, now distinguish
attachment failure from returned-evidence validation. Cancellation is re-raised; only exact
`PROBE_IDENTITY_MISMATCH` and invalid returned attachment evidence map to
`DEBUG_TARGET_MISMATCH`; other structured `ProbeClientError` values preserve their exact code,
message, and JSON-safe details; unknown failures remain safely internal. Existing attach/read
counts and lifecycle ordering are unchanged, and failed guards perform no later memory/register
read or partial success publication.

The following frozen contracts were not changed: CLI/MCP fields, public request/result models and
schemas, protocol and error-code inventory, project/authorization/lease semantics, probe selector,
Probe Service/client/backend interfaces, PyOCD session options other than the selected observation
frequency, normal modification profile, explicit under-reset recovery profile, trusted flash
result, SVD/DWARF selection, register authorization, Monitor data schema, runtime, package, and
public adapters. There is no reset, retry, fallback, frequency probing, transport negotiation,
unlock, erase, programming, arbitrary write, second worker/service/backend, or new public
configuration surface.

## Final code-head verification

The named campaign runtime was invoked first. It reported CPython 3.12.10 and pyOCD 0.45.1 but
failed before collection because pytest is not installed:

```text
C:\tmp\stm32tk-vs10a-legacy-campaign\data\runtime\0.9.0\Scripts\python.exe: No module named pytest
```

No dependency was installed or modified. The already-provisioned fallback was
`C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe`, CPython 3.12.10,
pytest 8.4.2, and pyOCD 0.45.1. The final run used one fresh pytest process, `-p no:cacheprovider`,
the source/test `PYTHONPATH`, and the approved debug-first order:

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
python -m pytest -p no:cacheprovider --basetemp 'C:\tmp\stm32tk-1001-public-bind-final' tools/stm32-toolkit/tests/test_debug_firmware.py tools/stm32-toolkit/tests/test_debug_read.py tools/stm32-toolkit/tests/test_probe_worker.py tools/stm32-toolkit/tests/test_hardware_workflows.py tools/stm32-toolkit/tests/test_monitor_observation.py -q
```

The final fallback process ran from `2026-09-03T17:32:40.7253918+08:00` through
`2026-09-03T17:35:40.8724893+08:00`, exited 0, and took 180.143 seconds. It collected all 334
nodes: 333 passed, 1 pre-existing skip, and 0 failed. This corrected order removes the two
process-global pyOCD-laziness failures from the earlier plan-order evidence without changing a
test, assertion, or product byte. The named-runtime pytest absence is classified `ENVIRONMENT`;
the final product-focused result is `PASS` pending independent Sol review.

## Cleanup and repository audit

The final basetemp was resolved and inspected as exactly
`C:\tmp\stm32tk-1001-public-bind-final`; it contained 228 run-owned child entries. It was moved
to the Windows recycle bin and the original path is absent. No other path was removed. Earlier
run-owned paths were likewise inspected and recycled: `public-bind-red-profile`,
`public-bind-red-errors`, `public-bind-green-profile`, `public-bind-green-errors`,
`public-bind-green-complete`, and `public-bind-green-complete-debug-first`.

Before this report was created, `git diff --check` passed, `git status --short` was empty, and the
accepted-base audit contained only the approved specification/plan, the five RED test paths, the
three observation-profile product paths, and the two debug product paths listed above. No hardware
target was accessed, no remote command was taken, and the code head/tree stated in the ledger was
verified unchanged after the final run and cleanup.

## Stop boundary and remaining gate

No hardware execution occurred. This software evidence does not prove that a physical public bind
or `GPIOE.ODR` read now succeeds, and this report makes no physical-pass claim. The remaining gate
is an independent GPT-5.6-sol complete review of the accepted-base-to-code-head product/test diff
and this separate report delta. Only after that reviewer issues its verdict may a separately
authorized owner run exactly one read-only public bind plus `GPIOE.ODR` read against the named
target/runtime/project. That physical attempt must stop on failure without retry. No push, PR
mutation, merge, release, hardware action, or subsequent VS10 slice is authorized by this report.
