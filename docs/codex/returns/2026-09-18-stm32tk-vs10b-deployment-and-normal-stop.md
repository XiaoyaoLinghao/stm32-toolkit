# VS10-B deployment and first physical stop

Historical deployment/NORMAL record. Current state is **DIAGNOSTIC_SOFTWARE_ACCEPTED_AND_DEPLOYED; FAULT_TARGET_EXPECTED_FAILURE_CONFIRMED; MONITOR_PRE_DEVICE_STOPPED; VS10-B NOT ACCEPTED**. See [latest SVD stop and exact offline cause](2026-09-18-stm32tk-vs10b-diagnostic-deployment-svd-stop.md). All pending/current wording below describes its earlier timestamp and does not supersede that report.

## Latest: authorized recovery and IDE/CLI/MCP passed

After the stopped operation, the user explicitly approved one static recovery prepare and one under-reset/100 kHz execute. Source, deployment, NORMAL build, ELF and input bytes were unchanged. New digest `8f97329220c7d71112d1f29548cecc6a9b76cc78c926f46a44ca06c11cb40517` was consumed once. Execute exited 0 after 13,710 ms, producing authoritative physical mailbox TestRun `target-v2-8f97329220c7d71112d1f29548cecc6a`, **1/1 passed**, evidence `88c443752959349b83b3983b460e19b1e6bea69e9f40c11f88545e6b1133a7c0`.

The actual `p/b/artifacts/migration/flash-result.json` reports `OK` and `verifiedBytes=7812`; identity matches the frozen NORMAL build and common B session. Lease `lease-ca959a9f569148cb9faa5d9f12a3d284` was released. Two Python processes in the cleanup snapshot belong to the separately owned offline Monitor `--validate-only` work, not residual hardware workers. Independent audit **accepted bounded recovery evidence** in `evidence/normal-recovery-review/review.md`. The result does not isolate frequency from reset policy and does not invalidate the initial failure.

Under the original B closed-loop and manual IDE authority, one new `debug handoff begin` passed. Its raw ticket/configuration is retained in `evidence/ide-01/handoff-begin.stdout.json`. The exact returned schema/profile/UID/attach/ready-regex configuration was installed in `ide/VS10-B.code-workspace` as **VS10-B NORMAL - Attach**, with verified absolute GDB/ELF/PyOCD/pack paths and no task dependency. The user reported `testtime=43063`, normal Shift+F5 stop, then D3/D4 alternating. This is attributed actual operator evidence. The original ticket end returned OK. One subsequent CLI variable read returned 56150 and one actual MCP stdio variable call returned 65781; all twelve checked firmware/probe/session identity fields matched. Final registry lease `lease-056d5f7abee34a55809e786708119f4b` is released and the matching hardware/MCP process set is empty. The MCP lifespan warning is retained with the successful response; no unrelated change was made. Evidence: `evidence/ide-01/handoff-cli-mcp-summary.json`. No normal PE4 machine-transition window or 100ms timing qualification is claimed from these single reads. Fault selection, B timed attempt and both 30-second Monitor windows have not started.

Fresh-Diagnostic preflight found a separate PRODUCT contract gap: `physical-monitor-fact/1` requires A continuation evidence and authenticates a completed before/after pair. B has no continuation and needs before-fix observations before its source authorization. The installed pure parser reproduced the missing-field rejection offline, with no state or hardware mutation. The user approved the versioned-input correction in the [fresh failed-run Monitor specification](../../superpowers/specs/2026-09-18-stm32tk-fresh-failed-monitor-facts-design.md) and paired plan, one deployment after independent acceptance, and the remaining fault/fixed under-reset 100 kHz Target pair plus one 30-second/100ms Monitor window per role. The Luna/max implementation starts at exact base907 in the isolated dgfix worktree. Independent review corrected the file estimate to five existing modules: event/store/MCP dispatch also hardcodes v1 and must carry the already approved v2 behavior; no additional public capability is introduced. Independent Monitor-entry review found MON-ENTRY-001: the connect binding uses observationSessionId while historical batch bindings use sessionId; the entry currently reads only the latter. The original entry owner is correcting this offline before any physical role run. Keep the current working NORMAL firmware and all valid evidence while closing these prerequisites.

The following sections preserve the first stopped operation and its diagnosis; historical pending/retry wording there is superseded only by this explicit recovery result.

The user authorized deployment and the VS10-B physical closed loop, confirmed the same board/probe and unchanged wiring, and initially observed D3/D4 alternating. The user is available for a real IDE step; that step has not started. The primary owns hardware execution, integration and acceptance; `/root/vs10b_deploy` (Luna/max) owns deployment, `/root/vs10b_firmware_impl` (Luna/max) owns firmware, and `/root/vs10b_host_review` independently reviews entry contracts and the failure. No remote GitHub mutation or ownership exception was authorized or performed.

## Fixed candidate and deployment

- Accepted base: `16a6e59dff7fed2999fae611e3d936b0b04bbabd`.
- Deployed source: `907b17094d7d6192f68735c470ca0bb73c1c7e23`, branch `codex/STM32TK-1002-CUBEMX-REAL-BOARD-integration`; product ancestor `f9c8ff7479f96ea799f6218f1c74efb90399424d`. Source was clean during packaging and deployment.
- Runtime: `D:\codex-tmp\v10b-0918\dep\data\runtime\0.9.0`. Bundle SHA256 `c01c1e70875d5b48fefc47e7d72ce3cfe60b0c54cb1c18917f98dade34e58b7c`; manifest `a22425d48a5ffc918740647e4f3ed7ac065e75b134e63678f6b8c606b64a8633`; runtime state `76afc6b7fa60e6e7f9b127ee579b02e5aa5214fd86dbcdbed54841c068bb8669`.
- Installer Check was healthy/matching, all 64 runtime wheels matched, and final Python/PyOCD/Toolkit/Monitor launchers passed. Packaging's original PTY exit code was not recovered; bundle integrity and installation were independently verified. Details: `evidence/deployment/deployment-final.json` and `builder-command-capture-note.txt`.
- Current project `D:\codex-tmp\v10b-0918\p\b` is clean, detached NORMAL `3a34dfdaad97d29d47f1e5405b3dedfe52318d43`. Its freshly qualified active Debug build is `ce6fb3cd4ed61a9803c85f26558fd25911e08a61869df9082a9895f975be56c3`, ELF `cebe2ca983fcd186111a7e7c675c2b211e2de2a4730ad2cb4e3fd6a34ef8c7ad`, input snapshot `5a63e050105ade3383cd8f3ff87dae7c0b10988e37dd6bd20dd910c6be51e749`. Use `evidence/firmware/normal-active-01`; older normal build identities are archived only. Fault and actual fixed-after have not been selected or applied in this execution.

## Actual hardware result

All commands used the installed B runtime, B data root and common session `vs10b-closed-loop-20260918-01`; TEMP/TMP/TMPDIR were under the approved B root. One direct invocation of the existing installed `PyOCDBackend.list_probes` enumerated exactly one ATK-HS-V3-CMSIS-DAP, hardware ID `ATK 20210914`. It preserved chained exceptions rather than using the public workflow's generic exception mapping; this is enumeration evidence, not public probe CLI acceptance. The fresh public selector was `pyocd:91d67402fe525a5d16bf226f59ab5ecea743eb69292e95719167263ed1fcbf8c`.

The unchanged `target-capture.py` (SHA256 `e25b59830330d18ff339ccbfca414294c9b9279c9ea942f2d2bbd06c85f19de4`) passed its existing probe-exception and Windows-spawn offline checks on B. It delegated the original CLI arguments and retained original errors before generic mapping.

One ordinary `test target prepare` passed in 5443 ms. Its stored authorization matched the normal build, ELF, input snapshot, project/Git/session, STM32F429ZGTx, probe, and v2 `d3-heartbeat` mailbox at `0x2002EFF0`. `recovery_under_reset=false`.

The only `test target execute` ended at `2026-09-18T05:55:06.8541357Z`, exit 2 after 6294 ms:

```text
TEST_FLASH_FAILED
  PROBE_PROGRAM_FAILED
    programDiagnostic.stage = program-call
    pyocd.core.exceptions.FlashFailure:
    target was not halted as expected after calling flash algorithm routine (IPSR=3)
```

Address, result code and OS error fields are null. This proves entry into programming and failure of an algorithm return-state check. It does not establish which Flash subroutine failed, whether erase/write partly completed, or the underlying cause. No TestRun or successful flash receipt was produced. Original response, boundary records and full command/exit evidence are retained under `evidence/closed-loop-01`.

Independent offline review is retained in `evidence/normal-flash-failure-review/review.md`. In the installed PyOCD `Lib/site-packages/pyocd/flash/flash.py:648-672`, the loop reads `target.get_state()`; line 668 expects `Target.State.HALTED`. The reported branch proves the observed state differed, but its exact enum value was not logged. The code then attempts `target.halt()`, reads IPSR, and raises the captured error. Thus `IPSR=3` is measured after that halt attempt, not a complete pre-failure fault snapshot. The exact Flash routine, PC/LR and fault-status registers are missing. Classify the observed layer as a physical programming/transport-runtime failure; firmware, environment and board root causes remain unproved.

The closest retained A comparison also contains a 1 MHz/halt failure followed by successful 100 kHz/under-reset programming. That supports the existing route as bounded operational recovery, but it changes two parameters together and cannot isolate the causal factor. No new product/runtime defect was established. The recovery proposal's success fields were explicitly renamed `plannedSuccessCriteria`; they are not results. The exact NORMAL source and deployed runtime remain unchanged.

The new action `c2074b251f10e04a81e48e063ac740e24bf326f2809ed62c4d71107d8bba40a4` was consumed. Lease `lease-f27f44fc35c04a49acc4a5497f8df1cc` is `released`; the post-operation process audit found no Python/PyOCD/GDB/OpenOCD/UV4 process. These prove cleanup, not application running. The user then observed **D3 on, D4 off**. No recovery, reset, reattach, read or hardware retry followed the failure.

## Remaining boundary

The isolated VS Code workspace and Cortex-Debug extension were opened, with automatic CMake configuration disabled. No handoff, debug launch or Watch result occurred; do not press F5 yet. Normal physical qualification, the B IDE check, fault/fix evidence, Diagnostic and final acceptance remain incomplete. No B timed acceptance attempt was started.

The existing 30-second acquisition entry is being bound to B paths and identities offline. `physical publish` alone cannot collect history. A recovery proposal under `evidence/closed-loop-02/recovery-proposal.json` passed bounded offline review and is awaiting new authority after this stopped card. It does not create or consume a new hardware action. Its scope is one static recovery prepare and one new-digest execute against the same NORMAL image, with under-reset/100 kHz, sector erase, keep-unwritten, no auto-unlock, existing readback/start/mailbox and first-error stop.

Deployment, unchanged software/build evidence, historical attempt 7 and accepted VS10-A remain valid within their original scope. Persistent B runtime, project, data and minimum failure evidence are retained. No cleanup bypass or remote mutation occurred.
