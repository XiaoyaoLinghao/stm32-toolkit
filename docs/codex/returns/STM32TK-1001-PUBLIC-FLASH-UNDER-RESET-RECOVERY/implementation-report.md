# STM32TK-1001 public flash under-reset recovery implementation report

Status: `RETURNED FOR INDEPENDENT SOL REVIEW`

Module/phase: VS10-A legacy hardware, public flash under-reset recovery correction.
Date: 2026-09-03 (Asia/Shanghai workday; test timestamps below are UTC).

## Frozen lineage and ownership

- Full accepted base: `f7865ed6e927403b51664705506237f4f69aa21d`; tree
  `91bbcfa5314df8e5b7f0b510a7155187428a69b9`.
- Accepted code head below that report: `f801f41905f8601c30cbe82d6cf07753f704a357`;
  tree `cf01bca001d0a7566e83374507d6af57ba064d23`.
- Approved specification: commit `8a41d5ae542dfc81ffa35616809bb7418ef901a0`, tree
  `715002c351465c1ed8de4e60c1ac8ffbe5d8857e`.
- Approved plan: commit `a289c4ae5f5277b750a1b7d477f7c82275d9961f`, tree
  `f9a832d98db43fa1b8adb7621892a6edf38cf09a`.
- Active branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`.
- Tracked remote baseline: `origin/codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`
  at `74ee5f4c7872af1bb612c9068af36319457e087b`; local code head was ahead 40 and
  behind 0. No push, PR mutation, merge, tag, release, or other remote action occurred.
- Implementation owner: one GPT-5.6-luna agent at reasoning effort `max`.
- Independent reviewer: GPT-5.6-sol primary agent; this report is not an acceptance verdict.

## Commit lineage

The two planned RED waves remained test-only. A one-line test-fixture correction was committed
separately after auditing the first GREEN attempt; it only supplied the recovery test's intended
target identity.

1. `e3331f5f239864d1fe9cb82ec61a8a4c0be21e19` (`097b493ab376d03f7847bb90cb5776dbddc18297`)
   — `test(vs10a): define under-reset recovery profile`.
2. `a5888063a9eccdabc3ecff3b564439394d667efe` (`b21dfb678d1ecf4b9b3e467e9e5b3afbea386e4b`)
   — `test(vs10a): define public flash recovery transition`.
3. `0a0b7d271204e1c908758bfd91c9c92a77b317dd` (`f9e1386f2a215bffa1323592c71411be11ac855a`)
   — `test(vs10a): correct recovery target fixture` (test-only follow-up).
4. Code head: `35da97e57939636c021e74802f3604dc2da5f914`
   (`9de8bbbeeefad697810c130a3b60f265527786de`), parent `0a0b7d271204e1c908758bfd91c9c92a77b317dd`
   — `fix(vs10a): add explicit under-reset flash recovery`.

The report is intentionally added after that code head and does not contain its own future report
commit SHA.

## Implemented behavior

- Normal flash remains the existing 1 MHz SWD / `connect_mode="halt"` path.
- The public CLI `flash --recovery-under-reset` and MCP `recoveryUnderReset` selection accept only
  exact boolean `true`; the MCP field is `StrictBool` and defaults to `false`.
- `FlashWorkflowRequest` gains only the trailing `recovery_under_reset: object = False` field.
- Recovery derives one immutable worker configuration with the unchanged target profile and
  provider, exactly 100 kHz SWD, and the closed `under-reset-recovery` policy. The same service,
  worker, backend, attach, flash callback, sector erase, `trustCrc=false`, `keepUnwritten=true`,
  target identity gate, halted-state gate, and readback-before-atomic-publication path are used.
- No retry, normal-first fallback, second service/backend/controller/provider/MCP, schema field,
  or agent-specific branch was added. `flash-result.json` and its consumer contract are unchanged.

## Changed and unchanged paths

Implementation product paths (the five-file allowlist only):

- `tools/stm32-toolkit/src/stm32_toolkit/probe/worker.py`
- `tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py`
- `tools/stm32-toolkit/src/stm32_toolkit/hardware_workflows.py`
- `tools/stm32-toolkit/src/stm32_toolkit/cli.py`
- `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`

Test paths (the seven-file allowlist only):

- `tools/stm32-toolkit/tests/test_probe_worker.py`
- `tools/stm32-toolkit/tests/test_pyocd_backend.py`
- `tools/stm32-toolkit/tests/test_hardware_workflows.py`
- `tools/stm32-toolkit/tests/test_cli_hardware.py`
- `tools/stm32-toolkit/tests/test_mcp_hardware.py`
- `tools/stm32-toolkit/tests/test_flash.py`
- `tools/stm32-toolkit/tests/test_debug_firmware.py`

The only report path is this file. `probe/flash.py`, `debug/firmware.py`, Probe Service, client,
lease, handoff, schemas, result format, dependencies, packaging, and runtime files were unchanged.

## Test evidence

All test commands used the prescribed executable:

`C:\tmp\stm32tk-vs10a-legacy-campaign\data\runtime\0.9.0\Scripts\python.exe`

That runtime is CPython `3.12.10` with PyOCD `0.45.1`. It does not contain pytest, so the first
prescribed RED command failed before collection with `ModuleNotFoundError: No module named
'pytest'` (classification: `ENVIRONMENT`). To keep the prescribed interpreter and avoid any
dependency or packaging change, subsequent commands appended the existing global pytest path
`C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\Lib\site-packages` to `PYTHONPATH`; that provided pytest `8.4.2` only.

The internal RED command was the plan's exact two-file command with the candidate `src` and
`tests` roots. Its environment-only first attempt exited 1 as noted above. The rerun with the
site-packages path exited 1 with 9 intended failures for the missing worker policy/derivation,
worker propagation, and backend recovery constructor/options; existing assertions stayed green.
The exact run-owned internal basetemp was cleaned.

The public RED command was the plan's exact five-file command with the same runtime and appended
site-packages path. It exited 1 with 18 intended failures covering the missing workflow field and
selection, CLI flag/grammar, MCP schema/strict input, and forwarding. Existing flash transaction,
exact result-field, and genuine producer-to-binder trust assertions passed. Its exact run-owned
basetemp was cleaned after normalizing only read-only attributes within that run root; no source
fixture was changed.

After the fixture correction, the focused backend check
(`test_pyocd_backend.py`) passed 37 tests, exit 0, in 3 seconds. Its run root was absent after
pytest cleanup.

The exact code-head seven-file command, in the plan-prescribed file order, was:

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\src;C:\tmp\stm32tk-1001-legacy-hardware-impl\tools\stm32-toolkit\tests;C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\Lib\site-packages'
& 'C:\tmp\stm32tk-vs10a-legacy-campaign\data\runtime\0.9.0\Scripts\python.exe' -m pytest -p no:cacheprovider --basetemp 'C:\tmp\stm32tk-1001-flash-recovery-final' tools/stm32-toolkit/tests/test_probe_worker.py tools/stm32-toolkit/tests/test_pyocd_backend.py tools/stm32-toolkit/tests/test_hardware_workflows.py tools/stm32-toolkit/tests/test_cli_hardware.py tools/stm32-toolkit/tests/test_mcp_hardware.py tools/stm32-toolkit/tests/test_flash.py tools/stm32-toolkit/tests/test_debug_firmware.py -q
```

UTC interval: `03:03:02`–`03:05:35`; exit code 1. The seven files contained 458 collected tests:
456 passed and 2 failed. The only failures were the pre-existing
`test_debug_public_api_is_complete_and_pyocd_lazy` and
`test_debug_package_exports_task_one_contracts_without_importing_pyocd` assertions in
`test_debug_firmware.py`. Classification: `INFRASTRUCTURE` (pre-existing same-process
test-isolation order interaction). The existing `test_production_worker_uses_only_closed_serializable_pyocd_and_task8_config`
exercises the existing semihost adapter, which imports PyOCD before the debug-laziness assertions
when the prescribed order is used. No recovery/product assertion failed, and neither those
assertions nor the transport/product behavior was weakened or changed.

The literal plan-prescribed file order did not pass and is therefore not claimed as a PASS.

As the order-conflict control, the same seven approved files were run at the exact code head with
`test_debug_firmware.py` first, followed by the other six files, using a fresh external
`C:\tmp\stm32tk-1001-flash-recovery-final-order` basetemp. UTC interval: `03:07:00`–`03:09:30`;
exit code 0; all 458 tests passed. A collection-only check recorded the per-file counts as
`test_probe_worker.py` 25, `test_pyocd_backend.py` 109, `test_hardware_workflows.py` 69,
`test_cli_hardware.py` 44, `test_mcp_hardware.py` 55, `test_flash.py` 42, and
`test_debug_firmware.py` 114.

## Independent Sol reviewer control evidence

The independent GPT-5.6-sol reviewer ran a fresh detached accepted-base worktree at
`f7865ed6e927403b51664705506237f4f69aa21d`, using the same runtime, `PYTHONPATH`, and literal
plan-prescribed seven-file order. That control reproduced the same two debug PyOCD-laziness
failures, proving they pre-date the candidate and are not a candidate regression. The reviewer
also ran a fresh detached candidate worktree at report head `caef83173a1e4fa263144460971a76a43fcc9a0b`
with code head `35da97e57939636c021e74802f3604dc2da5f914`, using the same seven files with
`test_debug_firmware.py` first; it exited 0. Collection evidence records 458 tests. These are
reviewer-owned control results, not an implementation-owner acceptance claim.

The exact code-head run roots (`green`, `green2`, `green-order`, `green-pyocd`, diagnostic,
`final`, and `final-order`) were inspected and removed only when they resolved to their explicit
run-owned paths. The failed final root contained 5,100 files / 3,644,505 bytes before cleanup;
read-only attributes were normalized only under that root. No repository-generated or reusable
fixture artifact remains.

## Hardware and remaining gate

No physical probe attach, flash, target read, or public Toolkit recovery attempt was run. Fake,
fixture, subprocess, and reordered software evidence is not a physical PASS and was not relabeled
as one. Public recovery remains physically unverified. The remaining gate is the GPT-5.6-sol
primary's independent complete accepted-base-to-code-head diff review and verdict. Only after that
verdict may a separately authorized owner run one public recovery attempt followed by one read-only
bind/read confirmation; no retry is implied.
