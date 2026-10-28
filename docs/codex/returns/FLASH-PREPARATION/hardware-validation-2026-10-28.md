# FLASH-PREPARATION — one-shot hardware validation

Date: 2026-10-28. Execution owner and result reviewer: Primary Codex.
Verdict: **FAILED_AT_ATTACH_HARDWARE_VALIDATION_INCOMPLETE**.

The single authorized ordinary 1 MHz flash failed during attach. It did not reach
the new pre-program preparation, programming or readback. The original IPSR=3
failure and the physical effectiveness of the preparation change remain unverified.
The prior [offline software acceptance](implementation-report.md) remains
**SOFTWARE_COMPLETE_HARDWARE_PENDING**; this result is not release acceptance.

## Authorization and frozen identities

The user explicitly authorized one ordinary 1 MHz flash of the existing firmware in
`C:/work/stm32/fresh-out`, using the original STM32F429ZG board and probe, including
SYSRESETREQ, halt confirmation and readback. The user confirmed power, connection,
external IDE detachment and exclusive ownership. The boundary was first failure
stops, no automatic recovery, no installed-runtime modification and no publication.
This one-attempt authorization has been consumed; no further hardware action is
authorized by this report.

- Source/report head before this report: `7193fcd933020a7084aab9472fc6716d5ca28e82`.
- Accepted product CodeHead: `1bb95790dbe1552b700f588d56e5ef9301b839a2`.
- Product accepted base: `528528f9e00791a96effa3a3bdb069c875fa9508`.
- Branch: `codex/v135-flash-preparation`; clean source worktree:
  `C:/Users/zhy76/.codex/worktrees/v135-flash-preparation/STM32-Toolkit`.
- Runtime: `D:/codex-tmp/kx23/venv/Scripts/python.exe`, Python 3.12.14,
  pyOCD 0.45.1, explicit candidate Toolkit/Monitor source paths. Source version
  metadata remains 1.3.4; these are Unreleased changes planned for v1.3.5.
  This was a source-candidate experiment, not an installed/package v1.3.5 test.
- Project: `C:/work/stm32/fresh-out`; existing shared data/lease root:
  `C:/data/stm32-toolkit`. No isolated registry, force reclaim or lease deletion.
- Target model: `STM32F429ZGTx`; requested debug target: `stm32f429xg`.
- Probe: `pyocd:91d67402fe525a5d16bf226f59ab5ecea743eb69292e95719167263ed1fcbf8c`.
- Session: `97ae45a6-bad7-4bf7-9a48-0c3c6f5aa289`.
- Build ID: `8d3368750cce364ad38e9ed0a6c0f6d6067779c52bc5d8e3a95115ee0ef4abcc`.
- ELF: `build/arm-debug/LWIP.elf`, 1,046,128 bytes; SHA-256:
  `b8d5f2c15963552f732ba5650c3150b9471a0d532f3d8c4712748e66fd06bf53`.
- Input snapshot: `09b178c4a285f3033ac35ae9dafbc2431028a0bbbd73de3b9daa89809b0e66d8`;
  `sourceBaseline=input-snapshot-v1`. Expected segment readback: 61,516 bytes.
- Initial CPU state: UNKNOWN, permitted by the normal halt-on-connect entry.
  The old recovery receipt was not reused as current state or current success.

## Entry review and offline admission

The standard procedure, checkpoint and latest offline execution report were read.
Before hardware, the shared firmware admission passed; parent and inert Windows
spawn child resolved identical candidate source modules, and the inert child exited
0. No probe enumeration/connection was used for that check. Project model, build
receipt, identity, ELF and previous flash receipt were copied with hashes.

Primary authored the run-local execution card/capture wrapper. An independent local
Claude Code CLI review of the procedure, frozen implementation excerpts, preserved
card, preflight and wrappers returned **NO_BLOCKERS**. This reviewed Primary's entry
contract and orchestration, not approval of Claude's own product implementation.
The invocation retained the configured `deepseek-v4.1-flash[1m]` route. Its no-action
inventory and actual startup smoke registered native PowerShell; two exact ordinary
read-only material commands have matched native execution evidence. No tests were
designated. Native command numeric exit fields were absent and remain null; the
dispatch CLI exit was 0. No scope discrepancy, pending result or retry was observed.

Only the card's status/review fields were then changed to READY with review and
input hashes. The wrapper's `--validate-only` returned `READY_OFFLINE`, exit 0,
`hardwareCalls=0`. Immediately before spawning the real CLI it rechecked clean
source HEAD, executable/source/pyOCD hashes, shared firmware admission, fixed
identities, argv and unchanged old receipt. An exclusive-create ledger consumed
the single attempt before startup. The wrapper had a 180-second outer bound,
retained native deadlines, no retry loop and a guarded Python main entry.

## Exact operation and observed result

The existing interpreter executed the following single CLI command with `shell=False`
in the frozen source worktree and explicit candidate PYTHONPATH:

```text
D:\codex-tmp\kx23\venv\Scripts\python.exe -m stm32_toolkit.cli --project-root C:\work\stm32\fresh-out flash --data-root C:\data\stm32-toolkit --session-id 97ae45a6-bad7-4bf7-9a48-0c3c6f5aa289 --probe pyocd:91d67402fe525a5d16bf226f59ab5ecea743eb69292e95719167263ed1fcbf8c --expected-build-id 8d3368750cce364ad38e9ed0a6c0f6d6067779c52bc5d8e3a95115ee0ef4abcc --expected-elf-sha256 b8d5f2c15963552f732ba5650c3150b9471a0d532f3d8c4712748e66fd06bf53 --frequency 1000000 --authorized --json
```

The outer record spans `2026-10-28T12:53:22.799568Z` to
`2026-10-28T12:53:32.489642Z`. The child CLI PID was 20064, with actual recorded
exit **2**, no outer timeout, empty stderr and a complete JSON failure response.
The coordinator PowerShell command was reported as exit 1; the captured child
exit 2 is the CLI execution identity, and the two are not conflated.

| Evidence | Observed value |
| --- | --- |
| Result | `ok=false`, `code=PROBE_CLOSE_FAILED`, `Probe attach cleanup failed` |
| Primary diagnostic | `service-attach-deadline`, `reason=timeout`, `sourceCode=PROBE_TIMEOUT` |
| Terminal wait | `service-terminal-wait`, `outcome=timed-out` |
| Worker settlement | `service-worker-abort`, `outcome=succeeded` |
| Later owned cleanup | client close, runner cleanup, backend close, lease release and service stop all recorded `succeeded` |
| Target state | `lastVerifiedTargetState=null`; remains UNKNOWN |
| Selected policy | normal, requested/configured 1,000,000 Hz, `preProgramReset=sysresetreq`, halt required, automatic retry false |
| Programming/readback | Not entered; no verified byte count, erase/write proof or new success receipt |

The policy fields are selection metadata, not proof of reset/halt execution or
measured SWD clock. The normal attach may have had target side effects before its
deadline; this result does not prove unchanged physical state. Successful worker
abort/lease release does not prove a physical detach or known CPU state, nor turn
the failed terminal wait into successful attach cleanup.

Offline source review explains the failure boundary: `probe/client.py` retains a
5,000 ms attach request; `probe/service.py` then permits the existing one-second
terminal wait and, on this observed path, aborts its owned worker and returns
`PROBE_CLOSE_FAILED`. `probe/flash.py:855-874` awaits successful attach before stale
receipt removal or `program_verified_elf`. Thus the new pre-program SYSRESETREQ
helper was not invoked by this run. Client/service/worker sources are unchanged
from the product accepted base. The captured diagnostic does not locate the
underlying stall within process startup, USB/probe access or target initialization.
Root-cause classification remains unresolved; a deadline alone does not establish
a software regression or hardware defect. No deadline was extended to obtain a pass.

After this terminal failure, only filesystem/source evidence was inspected. There
was no recovery, retry, lower-frequency connection, extra target read, reset,
halt/resume, power action or forced lease manipulation. The existing entry's owned
cleanup is the only cleanup executed.

## Preserved evidence and next boundary

Evidence root: `D:/codex-tmp/f135-hw-20261028`. `reconciled-result.json` binds the
raw streams, execution ledger, reviewed/READY cards, review streams and snapshots.
All five preserved project files retain their pre-run hashes. In particular,
`artifacts/migration/flash-result.json` is still the OLD recovery receipt, session
`7e6220c6-a3eb-4232-ac8d-2310f883f417`, SHA-256
`db8165a19ee8f8bf0f101f77bd3c4cd822baeae2f8ef349453fa0d07e222a4a0`;
it is not evidence of success for this attempt.

| Artifact under evidence root | SHA-256 |
| --- | --- |
| reconciled-result.json | 15acb0b6aa75ac7f728f6c8578bfc354d14f52a08c8c80a3e39774fd1ce2d2cf |
| hardware-attempt.json | a9eac9f8311112716ec4343091b74799bf2e8d6b2391d1e61f7e0704e7ead6d2 |
| flash.stdout.json | 98e494717cb834c88b5fd53030546d221d63700fb5e0006b0cefbbab6f2f0457 |
| flash.stderr.log (empty) | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |
| execution-card.json | 325f6eef86ad53665208963c21b2e54425e11b4e95bda1c3b83efa4048df471a |
| execution-card-reviewed-input.json | baba82f2d6cff25161ada51a6d51611ba80f7bdf5d66767f32ef30389a5e7c8b |
| preflight.json | c92bc265cf6997d450633b413092c389e9204f7cb34e61758f2dc589144b4b8f |
| perform_one_flash.py | b731a19fbbd08426d7be82aefde8705a8b34531f6dbf611586018acb1f9dd19b |
| procedure-review-verdict.md | 10ede5bcda0af1f5e49aee9167593cfee1eaefd2b38b36de6562057ff4f67906 |
| procedure-review-run/summary.json | e4b4f6cdb63e4b7b52be01a6742e666243645fdfefcee1c37ed448d08e9bba56 |

The validation has not passed. Further progress starts with offline localization
of the attach timeout and evidence gaps; any product change remains Claude-owned
and independently reviewed. A further physical diagnostic or programming attempt
needs a newly bounded execution card and explicit authorization. The same-image
smart-flash limitation, application execution, recovery-reset reuse, packaged
runtime/version alignment and full release qualification remain untested here.
No product code/test, installed runtime, original project inputs or remote state
was changed by this validation; only this report and the procedure checkpoint are
new tracked edits. These result-only documentation edits require no hardware or
repeat software matrix.
