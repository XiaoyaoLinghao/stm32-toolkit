# P4 firmware accepted offline; programming terminal-stopped

The requested P4 source change is implemented, independently reviewed and built. The single authorized normal Target execute failed; **P4 programming, fixed-after sampling and T10 closure are not accepted**. No hardware retry or fallback occurred. Historical P3 programming/Monitor, T9, 100ms, FullFault and attempt7 evidence remains valid in its original scope.

## Source and authority

User requested "开始修改代码，然后烧录", confirmed unchanged connected board/probe, D3 steady on/D4 blinking, stopped debuggers and unchanged wiring/loads, then explicitly authorized the additional single30s/100ms after-window and offline closure with "同意". Primary owns dispatch, independent review, acceptance and cleanup. Luna/max p4_firmware owns the firmware implementation/build; no product-code ownership exception or remote action.

Firmware base `8755ba8fd0c678f32d7d23e7d827e84317026429`; after commit `a5ebcab69278d3e25776ba7f9b0ab1376910cdd2` on `codex/t10-d3-fixture` at `D:\codex-tmp\t10-d3-fw`. The complete diff changes only periodic `LED0=0;` to `LED0=!LED0;` in `Main/Main.c`. Initial LED0 assignment, D4 toggle, all other bytes and original newline layout are preserved; after source SHA256 `ad07fad67c3d4aa5812f716bcfd461216aa59863979a218b3aa50365e6921bc4`,4544bytes. Primary reviewed the full diff in clean `D:\codex-tmp\t10-p4-review-0917` and proved exact byte replacement. Default Git whitespace checking flagged preserved CRLF; a command-local cr-at-eol-aware check passed without changing source formatting.

Existing public build exit0: build `5089b0924da702e38b05d245ae3b05d5f73935c02ee232b097f3e243c132e9fb`, ELF SHA256 `5dfdcdf122f4886132b8270d9abdd7620766af7e81f66770a3e20337440be745`, InputSnapshot `31a6b104512029a0a1c222dcff9070aa3036975b1610127d5b4ce0dfcdec9ba6`. Existing task8_offline_verify returned PASS_OFFLINE_ONLY. Preserve current build outputs; this is not physical execution evidence.

Deployment remains source `0c375c03ab6afa4192a37d5732009b82845216a7`, using explicit candidate Python `D:\stm32tk-data\fault-controlled-20260911\candidates\lease-20260914\runtime\0.9.0\Scripts\python.exe`; business DataRoot unchanged. Runtime hash, existing helpers and all83 P3 backup files were checked. No toolkit rebuild/deployment.

## Actual acceptance and hardware sequence

New attempt `4956a90c-6132-4651-b597-e5aef5a7fd22` reused the existing P3 failed TestRun and published before Monitor reference. Source authorization reached revision5 with current Diagnostic revision5/event head. The actual source declaration `a396d183e344cc8cef2de807964d0f629416c36265f43f44eb95c833c91e7363` was prepared from real Git diff/build identities and registered; Diagnostic reached revision6. Canonical declaration copy passed the existing Monitor input loader before hardware.

After-build checkpoint reached attempt revision6 at 2026-09-17T00:46:15.214976Z, deadline00:51:15.214976Z. The entire remaining path shares that deadline; it is not restarted after sampling. This was not a timeout failure.

1. One normal prepare: PID26184,7701ms,exit0. Fresh action `ecfaf68bbf063d0a22511fb8a47565dbb2ae130c9405091e042ec9f0fb996d00`; protocol stm32-target-frame/2, d3-heartbeat case digest and probe hash matched. No preliminary enumeration or recovery prepare.
2. One execute: PID25568,6259ms,exit2,outer budget169818ms and no outer timeout. Public `TEST_FLASH_FAILED`; unchanged capture entry retained `PROBE_PROGRAM_FAILED`, message "Probe worker operation failed", empty details. The action was consumed at00:46:26.677052Z. No successful P4 flash receipt or P4 TestRun was obtained.
3. All later steps stopped: no after Monitor invocation, comparison, bundle, FixVerification or final checkpoint. Persisted attempt snapshot remains revision6/ACTIVE with its original deadline; execution ledger is TERMINAL_STOPPED_FLASH_FAILED. ACTIVE is not permission to continue/retry, and the deadline cannot be extended.

The shared registry records released lease `lease-db677d7f8eac4bbeba52cf4fcd73d4d9`; the owned processes/descendants and other relevant debug consumers were absent. User after-operation observation: **D3 and D4 both steady on**. No extra target-state read occurred; lease/process cleanup does not prove running. Board execution state and partially programmed contents remain unverified.

## Offline failure boundary

Read-only tracing against deployed source `0c375c03ab6afa4192a37d5732009b82845216a7` found the unique production origin of `PROBE_PROGRAM_FAILED` at `tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py:1484-1489`: any exception inside `_get_driver().program_file(...)` becomes `ProbeBackendError("PROBE_PROGRAM_FAILED", "Firmware programming failed")`. The driver constructs PyOCD FileProgrammer and calls `.program()` at lines169-180. This proves arrival at the programming call boundary, but does not identify driver acquisition, programmer construction, erase/write, SWD, protection or power as the cause.

`tools/stm32-toolkit/src/stm32_toolkit/probe/worker.py:309-327` replaces the message with "Probe worker operation failed" and does not forward details for this error class. Lines467-531 then terminate the worker. The original exception type, text, cause chain, errno/winerror and programming stage were not retained in the returned protocol; no separate worker log was found. Classification: the lost diagnostic detail is a PRODUCT observability limitation; the physical programming failure itself remains UNCLASSIFIED. LED states and elapsed time cannot establish its cause.

The call had passed ELF path/size/hash validation (`probe/service.py:1959-2057`) and reached the backend. It did not reach post-program readback verification (`probe/flash.py:602-606`), successful receipt publication (lines629-647), or the Target post-flash identity/start/transport/test-frame path (`testing/target.py:1605+`). `probe/flash.py:593` calls `_remove_stale_result()` (lines555-560) before programming; that function unlinks the previous receipt. This explains why a missing receipt is compatible with this failed attempt and is not evidence of user cleanup or physical Flash erasure.

Minimal next correction proposal, not implemented or newly authorized for hardware: retain bounded, sanitized programming exception type/message/cause and the last programming stage through `probe/pyocd_backend.py` and `probe/worker.py`, keeping the existing public error code and terminal-stop behavior. Luna/max would own the two-module implementation and focused existing-seam exception propagation tests; primary would review the complete diff. First check the existing error-details contract before finalizing scope. No retry/recovery feature or generic diagnostic framework is required. Offline injected failures can verify diagnostic preservation, but cannot reconstruct this lost physical exception. Any later hardware attempt requires a separately bounded authorization.

## Evidence retention and next boundary

Run root `D:\codex-tmp\t10-p4-20260917` holds exact argv, raw results/exceptions/PID/exit/budgets, prepared/consumed action records, source authorization/declaration, build/verifier/review, offline Monitor preflight, registry/process/LED records and attempt snapshot. Workspace logs had no files; execute stderr was empty. The current project flash receipt is absent; the old successful P3 receipt remains intact in `D:\codex-tmp\t10-d3-p4-20260914\p3-preserved` with all83 verified files. Absence of a current receipt is not proof of erased Flash or user deletion.

Retain P4 source/build, original immutable P3 Target/Monitor evidence and backup, review checkout and minimal failure evidence. Run temporary directory is empty; no old policy-rejected cleanup was retried. The unused fixed-after config is only prepared input, not a fresh hardware authorization. Further hardware or recovery needs a new bounded authorization after the offline failure boundary is established. T10/VS10-A remain incomplete.
