# STM32TK-1001 Probe Inventory/Selection Compatibility

## Outcome

- Status: `IMPLEMENTED — SOL REVIEW PENDING`
- Module / vertical slice: `STM32TK-1001 / VS10-A`
- Implementer: one GPT-5.6-luna agent at reasoning effort `max`
- Reviewer: GPT-5.6-sol primary; independent review remains pending
- Hardware status: `HARDWARE NOT RUN`
- Remote status: `REMOTE ACTION NONE`
- This report records implementation and local verification evidence only. It does not claim H2 or VS10-A acceptance.

## Ledger and lineage

- Accepted base: `74ee5f4c7872af1bb612c9068af36319457e087b`
- Accepted-base tree: `4eb81b6f24d70e31116f0c76a483fe3fccd8c0a3`
- Approved specification: `372d80388aa2ecd806fce1ba2cc83796106e15e0`
- Approved specification tree: `9fa27bd83ee82f69bbe2825e62fa55aafdbb91a8`
- Approved implementation plan: `0f06a94976e14cfdd7ae3189f2e921c6aec0b20a`
- Approved plan tree: `547ff02f238d131854ec9eed28e45541b8538bbe`
- Product implementation head: `e8407f89a9ca9b2c82ffaa5c54b63f0f04faef73`
- Product implementation tree: `249858352fd3d90e3c08e1bc90a287638517ec75`
- Final code/test head before this report: `9f6efedd16fd3c317fa3b84ea439528a79d25be1`
- Final code/test tree: `c7280970c9aca537dcbe92b159f5a9ce39c56428`

The accepted Task 1 RED lineage is:

| Commit | Full SHA | Purpose |
|---|---|---|
| RED-1 | `526bbc9103552bcea07fc628ac45f8b755aba14c` | Define portable opaque probe selection tests |
| RED-2 | `0e8753438a2e56b094da342438facc6b42d45846` | Add causal fresh-selection, invalid-candidate, boundary, and client-field tests |
| RED-3 | `6db9f08cb9b37c4bcb348102f47065f0d12b6c18` | Tighten invalid hardware-ID and display-control test data |
| Product GREEN | `e8407f89a9ca9b2c82ffaa5c54b63f0f04faef73` | Implement the frozen minimal selector/descriptor/client adapter |
| Test-contract correction | `9f6efedd16fd3c317fa3b84ea439528a79d25be1` | Align direct fake descriptor expectations to the six-key contract |

The implementation branch is `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`, with
upstream `origin/codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`. Before this report
commit it was clean and `ahead 7` of its upstream; all seven commits were local and unpushed.

## Original RED evidence

The original Task 1 focused command was run after RED-3 from a fresh external basetemp:

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest `
  tools/stm32-toolkit/tests/test_probe_selector.py `
  tools/stm32-toolkit/tests/test_pyocd_backend.py `
  tools/stm32-toolkit/tests/test_probe_worker.py `
  tools/stm32-toolkit/tests/test_probe_service.py `
  tools/stm32-toolkit/tests/test_probe_client.py `
  tools/stm32-toolkit/tests/test_hardware_workflows.py `
  tools/stm32-toolkit/tests/test_cli_hardware.py `
  tools/stm32-toolkit/tests/test_mcp_hardware.py `
  -p no:cacheprovider --basetemp 'C:\tmp\stm32tk-1001-probe-selector-red-20260902-revision3' -q
```

Result: exit code `1`; `428` collected, `63` failed, and `365` passed. Failure nodes were
selector `19`, backend `14`, worker `1`, service `1`, client `27`, and workflow `1`.
The failure class was `PRODUCT_COMPATIBILITY`:

- The selector module and pure validation/fingerprint/selector helpers did not yet exist.
- PyOCD rejected admitted opaque hardware IDs, emitted no expanded six-field descriptor, did not map reserved/raw IDs, and did not resolve public selectors against a fresh enumeration.
- Worker/service/workflow boundaries still used the old descriptor shape.
- The client did not yet close-validate six-key list responses, fingerprints, display fields, or duplicate public selectors.
- CLI and MCP dispatch/parity cases passed; the malformed unique-ID attach case was already fail-closed under the existing raw-ID guard.

No import, collection, infrastructure, environment, hardware, or unrelated product failure was observed in this RED run.

## Implemented scope

Product implementation commit `e8407f89a9ca9b2c82ffaa5c54b63f0f04faef73` changes exactly these
four approved product paths:

- `tools/stm32-toolkit/src/stm32_toolkit/probe/selector.py` (new pure adapter)
- `tools/stm32-toolkit/src/stm32_toolkit/probe/backend.py`
- `tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py`
- `tools/stm32-toolkit/src/stm32_toolkit/probe/client.py`

The final test-contract correction commit changes exactly one approved test path:

- `tools/stm32-toolkit/tests/test_probe_backend.py`

The accepted Task 1 tests remain limited to:

- `tools/stm32-toolkit/tests/test_probe_selector.py`
- `tools/stm32-toolkit/tests/test_pyocd_backend.py`
- `tools/stm32-toolkit/tests/test_probe_worker.py`
- `tools/stm32-toolkit/tests/test_probe_service.py`
- `tools/stm32-toolkit/tests/test_probe_client.py`
- `tools/stm32-toolkit/tests/test_hardware_workflows.py`
- `tools/stm32-toolkit/tests/test_cli_hardware.py`
- `tools/stm32-toolkit/tests/test_mcp_hardware.py`

No downstream product module was changed. In particular, worker/service/hardware workflows,
flash, handoff, lease, monitor, target, runtime, and hardware-operation product bytes remain
unchanged. No test logic was weakened or removed; the sole post-review test correction adds the
literal `hardwareId` and `probeFingerprint` values for trusted fake descriptors `probe-a` and
`probe-b`.

## GREEN evidence

### Probe-focused behavior

The eight-file changed-behavior matrix was run against the product head with a fresh external
basetemp `C:\tmp\stm32tk-1001-probe-selector-task2-slice-20260902`:

```text
Result: exit code 0; 428 passed, 0 failed, 0 skipped.
```

The exact basetemp was removed and verified absent.

The corrected direct backend contract test was then run with fresh external basetemp
`C:\tmp\t2backend`:

```text
Result: exit code 0; 12 passed, 0 failed, 0 skipped.
```

That basetemp and its captured log were removed and verified absent.

### Complete 14-file matrix

The Task 2 matrix plus `test_probe_backend.py` was run at both the prescribed 49-character
external root and a deterministic short root. The command was:

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest `
  tools/stm32-toolkit/tests/test_probe_selector.py `
  tools/stm32-toolkit/tests/test_pyocd_backend.py `
  tools/stm32-toolkit/tests/test_probe_worker.py `
  tools/stm32-toolkit/tests/test_probe_service.py `
  tools/stm32-toolkit/tests/test_probe_client.py `
  tools/stm32-toolkit/tests/test_probe_backend.py `
  tools/stm32-toolkit/tests/test_hardware_workflows.py `
  tools/stm32-toolkit/tests/test_cli_hardware.py `
  tools/stm32-toolkit/tests/test_mcp_hardware.py `
  tools/stm32-toolkit/tests/test_probe_lease.py `
  tools/stm32-toolkit/tests/test_flash.py `
  tools/stm32-toolkit/tests/test_debug_handoff.py `
  tools/stm32-toolkit/tests/test_monitor_observation.py `
  tools/stm32-toolkit/tests/test_physical_target_workflows.py `
  -p no:cacheprovider --basetemp '<EXTERNAL_BASETEMP>' -q
```

At `C:\tmp\stm32tk-1001-probe-selector-green-20260902` (49 characters), result was exit code
`1`: `698` collected, `696` passed, `1` skipped, and `1` failed. The sole failure was the
unchanged downstream baseline:

```text
tools/stm32-toolkit/tests/test_physical_target_workflows.py::test_v2_failed_terminal_run_still_publishes_only_after_physical_evidence
```

It returned `TEST_AUTHORIZATION_INVALID` during target preparation where the fixture expected
`prepared.ok is True`. No probe test failed, and no downstream product/test path was modified.

At the deterministic short root `C:\tmp\t2g`, the identical 14-file command completed with exit
code `0`: `698` collected, `697` passed, `1` pre-existing skip, and `0` failures. This is the
selector acceptance result used to avoid masking valid behavior with the Windows path limit.

## Independent Windows baseline concern

The prescribed 49-character run is tracked separately from selector behavior. The host reports:

```text
reg.exe query HKLM\SYSTEM\CurrentControlSet\Control\FileSystem /v LongPathsEnabled
LongPathsEnabled    REG_DWORD    0x0
```

A separate disposable reproduction under `C:\tmp\t2-maxpath-evidence-20260902` used a parent
path length of `232` and source path length `239`. `os.link(..., follow_symlinks=False)` failed
with `FileNotFoundError [WinError 3]` for destination path lengths `263`, `264`, `265`, and
`266`. This is an accepted-base Windows MAX_PATH limitation; it was not caused or fixed by the
probe selector implementation and is not a hardware result.

## Cleanup and verification

All run-scoped roots were removed only after preserving the minimum result evidence and were
verified absent:

- Task 1 RED roots: `C:\tmp\stm32tk-1001-probe-selector-red-20260902`,
  `C:\tmp\stm32tk-1001-probe-selector-red-20260902-revision1`,
  `C:\tmp\stm32tk-1001-probe-selector-red-20260902-revision2`, and
  `C:\tmp\stm32tk-1001-probe-selector-red-20260902-revision3`, including their captured logs.
- Task 2 roots: `C:\tmp\stm32tk-1001-probe-selector-task2-slice-20260902`,
  `C:\tmp\stm32tk-1001-probe-selector-green-20260902`, `C:\tmp\t2backend`,
  `C:\tmp\t2g`, and `C:\tmp\t2-maxpath-evidence-20260902`, including captured logs.
- Explicit diagnostic roots: `C:\tmp\stm32tk-1001-physical-diag-20260902`,
  `C:\tmp\stm32tk-1001-physical-diag-file-20260902`, and
  `C:\tmp\stm32tk-1001-physical-diag-pair-20260902`.

One Task 1 cleanup encountered a protected run-created redirect fixture; its entries were
inspected and removed individually within the exact basetemp. No cleanup residue remains. No
source-controlled tests, fixtures, baselines, user data, or shared caches were removed.

Final checks before this report commit:

- `git diff --check`: passed.
- `git diff --name-only`: only the report path pending staging.
- `git status --short`: only the report path pending staging.
- No hardware or remote operation was performed.

## Acceptance boundary

`HARDWARE NOT RUN`; replay/fake/fixture evidence is not physical acceptance. `SOL REVIEW PENDING`;
the independent primary review must inspect the complete accepted-base-to-final-code/test diff.
`REMOTE ACTION NONE`; the branch remains local and unpushed. The report commit is intentionally
not identified in this artifact, per the Task 3 brief; its full SHA, tree ID, and final remote
state are returned separately to the primary agent.
