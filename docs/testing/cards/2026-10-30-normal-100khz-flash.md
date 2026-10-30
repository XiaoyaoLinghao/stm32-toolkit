# Normal connection +100kHz managed flash execution card

Status: **OFFLINE_ENTRY_REVIEW_ACCEPTED / BLOCKED_NOT_EXECUTED**.
Diagnostic-preservation software slice accepted at CodeHead
bfa56c21fa67e53649ec0c9c15b5ab4e9b79ae4d:345 distinct related cases pass,
including37 new regressions; Primary independently passed23 overlapping cases.
The2 environment import failures were retained and resolved by one explicitly
authorized retry. Independent supplied-source card review found NO_BLOCKERS;
Primary discharged its software conditions. Hardware prerequisites below remain.
No hardware authorization in this task. Original constructor-only grant is
consumed; the earlier readiness reply is historical, not a new READY assertion.
Primary authored this card; independent domain reviews and final acceptance are
in [FLASH-FAILURE-EVIDENCE](../../codex/returns/FLASH-FAILURE-EVIDENCE/implementation-report.md).

## Exact proposed entry and identity

Use one real public managed flash invocation, which contains its own normal
connection. No preceding probe list/extra attach/constructor, no Monitor or Target
prepare/execute, no direct backend/fake seam. Static pins currently observed:

| Item | Pin / required pre-run recheck |
| --- | --- |
| Base/branch |3bf143cd314b0e396a420a8c6ef33ee3ec19535b; codex/v135-flash-failure-evidence. Source/test CodeHeadbfa56c21fa67e53649ec0c9c15b5ab4e9b79ae4d. Freeze exact final reviewed clean execution HEAD, actual entry/import bytes and SDK origins before any later launch; do not reuse old source pins. |
| Python/SDK |Direct CPython3.12.14 at C:/Users/zhy76/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe, SHA2565640e9be2fd33d05a1a9ae1228e2354609a69ab831605995ec4e2bd6da8fff5e. Existing isolated D:/codex-tmp/st135-pyocd046/candidate-site pyocd0.46.0 and read-only D:/codex-tmp/kx23/venv/Lib/site-packages, hidapi0.15.0. Pin module/distribution origins and347 SDK files to accepted wheel; never substitute installed runtime or venv redirector. |
| Project/data |C:/work/stm32/fresh-out / C:/data/stm32-toolkit; same real shared registry, no new realm or forced lease deletion. Current CPU/firmware UNKNOWN. |
| Original selector/target |pyocd:91d67402fe525a5d16bf226f59ab5ecea743eb69292e95719167263ed1fcbf8c / stm32f429xg; configured device STM32F429ZGTx, original board user-described STM32F429ZG. No current power/exclusivity/changes confirmation for this future step. |
| New session/output |Proposed session st135-normal-flash-hw03; external D:/codex-tmp/st135-normal-flash-hw03 for raw stdout/stderr/argv/start/exit/pre/post evidence. Must not exist/reuse old session. Product workspace/session path derived by existing WorkspacePaths, not guessed/copied. |
| Build/image |buildId8d3368750cce364ad38e9ed0a6c0f6d6067779c52bc5d8e3a95115ee0ef4abcc; build/arm-debug/LWIP.elf SHA256b8d5f2c15963552f732ba5650c3150b9471a0d532f3d8c4712748e66fd06bf53,1046128 filebytes. Input snapshot09b178c4a285f3033ac35ae9dafbc2431028a0bbbd73de3b9daa89809b0e66d8, Git explicitly unavailable/null. Fresh admission must still pass before the future call; no automatic rebuild or receipt rewrite. |
| Readback |Two segments:0x08000000 length61368 +0x0800efb8 length148 =61516bytes. MAX_READ_BYTES32768 requires3 RPC reads:0x08000000/32768,0x08008000/28600,0x0800efb8/148; exact bytes, no CRC-only acceptance. Original two-read arithmetic is explicitly superseded in firmware-observation-reconciled.json. |

Proposed literal argv, parser-observed only; **do not execute now**:

```text
C:/Users/zhy76/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe -B -m stm32_toolkit.cli flash --project C:/work/stm32/fresh-out --data-root C:/data/stm32-toolkit --session-id st135-normal-flash-hw03 --probe pyocd:91d67402fe525a5d16bf226f59ab5ecea743eb69292e95719167263ed1fcbf8c --expected-build-id 8d3368750cce364ad38e9ed0a6c0f6d6067779c52bc5d8e3a95115ee0ef4abcc --expected-elf-sha256 b8d5f2c15963552f732ba5650c3150b9471a0d532f3d8c4712748e66fd06bf53 --frequency 100000 --authorized --json
```

Process-local PYTHONPATH order: reviewed checkout/tools/stm32-toolkit/src,
candidate-site, existing dependency site. Parent/worker use direct pinned Python;
UTF8/no-bytecode/no-user-site and unique TEMP/TMP/TMPDIR. CLI spawn main guard
must not recursively run flash in the child. Check PYOCD_PROJECT_DIR,
PYOCD_USB_BACKEND,PYTHONHOME,__PYVENV_LAUNCHER__ and four default project YAML
paths absent, including redirects/dangling links; do not clear/delete conflicting
settings to force this card. Full pinned observations and request-count correction live under
D:/codex-tmp/st135-normal-flash-entry; source/runtime/firmware identities must be
refreshed at the actual future entry, not assumed from this snapshot.

## Later authority must cover the real control/cleanup effects

One normal100kHz MODIFY connection/Session.open, target identity and initial HALTED
check; one Toolkit SYSRESETREQ reset_and_halt and a fresh HALTED gate; sector
program/keep-unwritten, target RAM/register/CPU flash-algorithm operations and
three exact readback requests over two segments; existing client/service/worker/lease cleanup. SDK reset
polling can reconnect DP; SDK algorithms use halt/resume and can reset when
their branch requests it. These are disclosed ordinary SDK internals, not a
promise of one physical reset or zero internal reconnection. If the future user
requires absolutely no SDK reconnect, this unchanged entry is not compatible.
Builtin stm32f429xg connection writes DBGMCU.CR/APB1_FZ/APB2_FZ; reset catch
arms/restores DEMCR.VC_CORERESET. Configured part_number is statically consistent
with canonical stm32f429xg, not proof of physical identification.

Normal partial/failed attach or late MODIFY success may resume/check-running/
close during existing cleanup. This is within the future explicitly described
cleanup scope, not a separately authorized recovery invocation. Failed pre-program
reset/halt stops before FileProgrammer/readback/receipt and does not request
attach-restoration resume. Program/readback failure has no agent-added reset/run;
source close uses resume_on_disconnect=false but physical state remains UNKNOWN.
On a backend error response parent abort can race/truncate child finally
backend.close; SDK close/uninit and USB release are not guaranteed. Service
program timeout can terminate mid-program with partial writes and no readback.
No extra retry/reattach/discovery, under-reset, auto-unlock/chip erase fallback,
post-flash application run, force cleanup, installation or publication.

## Budget, evidence and stop gates

Keep actual attach5s success deadline, SDK per-Windows-HID-read10s, program30s, each of three
readbacks30s; worker startup10s/ordinary RPC30s/flash RPC300s/close5s. The service
program deadline remains30s and can abort that longer RPC. Existing1s terminal wait
and owned-worker terminate/join1s then kill/join1s where that branch requires it.
The1s attach terminal wait is distinct from those joins. SDK warnings may be lost
to worker NUL stdio; a returned reset call or absent warning is not halt proof.
CLI HTTP envelope305s is not a5s attach wall bound. The old constructor20s+2s
budget is inapplicable. Proposed whole-call observation budget180s must be
separately authorized: no universal hard exit guarantee or timer extension.
If unfinished, retain ongoing/UNKNOWN ownership and handles and stop later
hardware; do not claim programming stopped, kill/restart or release/delete lease
on behalf of an unknown/live process. Do not run this card until the independent
review and all required software gates are accepted, then fresh hardware authority
and current readiness/preflight are confirmed. No condition here grants access.

Before launch: new explicit finite hardware authority + current original-board/
probe power/exclusivity/IDE-disconnection/changes confirmation; accepted entry
review; exact source/runtime/SDK/firmware pins; safe absent session/output; actual
guard arbitration, no handoff/BUSY bypass. Archive existing flash-result.json bytes
before the call (current reference hashdb8165a19ee8f8bf0f101f77bd3c4cd822baeae2f8ef349453fa0d07e222a4a0).
Existing receipt presence is not this run's success. After attach/identity pass,
stale receipt removal precedes programming; removal failure stops before the
program call. Investigate conflicting evidence rather than inferring success.

Preserve raw CLI stdout/stderr, full JSON/code/details, argv and actual exit,
attachDiagnostic/progress/cleanup, programDiagnostic/pre-program stage where
present, receipt before/after bytes and ownership/worker terminal evidence.
Configured flashOptions are not execution proof. Ordinary programming-error plus
worker-abort failure now reports safe initiatingCode=PROBE_PROGRAM_FAILED,
validated programDiagnostic and a failed worker-parent-abort stage. If workflow
cleanup also fails, HARDWARE_CLEANUP_FAILED retains those facts followed by actual
workflow/service stages. Do not infer process death or USB release from the
envelope, proxy is_terminal or lease release; unresolved abort forbids later
hardware even when other cleanup stages succeeded. Invalid diagnostics/prior
cleanup are deliberately rejected; arbitrary private details are never copied.
Success+cleanup failure uses initiatingCode=OK while remaining a failure.
Unreportable fatal interruption, cleanup.fatal, invalid IPC or a process lost
before emitting a validated result can lack the diagnostic; preserve available
stdout/stderr/exit/ownership evidence and UNKNOWN state, without reconnecting or
retrying to recreate it. Non-Exception worker abort BaseException still propagates
under the existing fatal policy. The correction does not add a graceful-close,
rollback, termination or physical-state guarantee.

Success requires one authorized invocation, normal100kHz selected policy, correct
connected identity, source-enforced reset/HALTED gates,61516 exact verified bytes,
new receipt matching this session/build/ELF and final public ok=true plus reconciled
cleanup. Receipt can precede later cleanup failure; it alone never satisfies this
card. Success+cleanup failure drops public report data/postFlash; a new matching
receipt is only forensic partial evidence, never overall PASS. No claim of user firmware running: postFlash targetState=unknown,
runVerified=false. On any admission/lease/attach/reset/halt/program/readback/
receipt/cleanup failure or cancellation, stop later hardware, preserve initiating
and cleanup facts and mark partial-write/CPU/USB state UNKNOWN as appropriate.
No rollback, automatic recovery or second invocation belongs to this card.
