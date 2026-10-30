# FLASH-FAILURE-EVIDENCE implementation and acceptance

2026-10-30 physical follow-up: **PASS_ONE_NORMAL_100KHZ_MANAGED_FLASH** at executed
HEAD e8e3c5f8d77490eaa0fae3e8ab8586237f30935c; see
[one-shot hardware report](normal-flash-2026-10-30.md). One public ordinary100kHz
call exited0/OK in19656ms and verified61516bytes; matching new receipt, endpoint
removed and new lease released. No retry/recovery/runtime replacement/remote action.
This single original-pair case passes; application state remains unknown and
runVerified=false, historical IPSR root cause is not proven. New hardware authority
is consumed, not READY for another operation. The prior offline checkpoint follows.

2026-10-30 verdict: **ACCEPTED — offline diagnostic-preservation slice**.
Normal connection/100kHz physical validation remains
**SOFTWARE_COMPLETE_HARDWARE_PENDING / BLOCKED_NOT_EXECUTED**; this is not release acceptance.

Accepted base:3bf143cd314b0e396a420a8c6ef33ee3ec19535b.
CodeHead before this report:bfa56c21fa67e53649ec0c9c15b5ab4e9b79ae4d.
Branch:codex/v135-flash-failure-evidence; no PR/remote mutation authorized.
Primary owns specification/plan/procedure/card/orchestration/independent review
and acceptance; local Claude Code CLI implemented code/tests using unchanged
deepseek-v4.1-flash[1m] route. No ownership override or Codex implementation fallback.

Governing [design](../../../superpowers/specs/2026-10-30-flash-failure-evidence-design.md),
[plan](../../../superpowers/plans/2026-10-30-flash-failure-evidence-plan.md),
[standard procedure](../../../testing/standard-test-procedure.md) and
[reviewed card](../../../testing/cards/2026-10-30-normal-100khz-flash.md).

## Behaviour and complete-diff review

Previously a programming error followed by workflow cleanup failure lost its
original diagnostic; worker abort failure could replace that error even earlier.
The four implementation/test files are:

- tools/stm32-toolkit/src/stm32_toolkit/hardware_workflows.py
- tools/stm32-toolkit/src/stm32_toolkit/probe/worker.py
- tools/stm32-toolkit/tests/test_hardware_workflows.py
- tools/stm32-toolkit/tests/test_probe_worker.py

Worker ordinary abort failure for either programming method now keeps the valid
programDiagnostic, initiatingCode=PROBE_PROGRAM_FAILED and one closed failed
worker-parent-abort stage beside PROBE_BACKEND_ERROR/fixed termination message.
Successful abort retains the prior ordinary programming-error shape. A subsequent
workflow cleanup failure returns HARDWARE_CLEANUP_FAILED while preserving safe
initiating code, independently validated diagnostic and ordered worker then actual
workflow/service cleanup stages. Invalid input is rejected; arbitrary private
details and abort text are not copied. Frozen protocol containers are supported.

No new hardware call, reset/run, retry, ownership or timing policy. Primary reviewed
the full accepted-base-to-CodeHead diff in a clean exact-head checkout. Static
comparison confirms all prior108 hardware-workflow and63 worker test/helper
definitions unchanged; only existing _one_shot and ProbeBackendWorker.call change,
plus new projection helpers. Existing abort/close/reset/flash control functions
and all other old methods remain identical. Whitespace checks pass.

Non-flash privacy, attach and controlled-Fault branches remain compatible.
Success+cleanup failure is still failure with initiatingCode=OK and no public
success data/postFlash. Managed receipt may already exist as partial evidence;
imported-flash cleanup failure writes no receipt. Action cancellation/fatal plus
cleanup failure uses fixed safe codes; cleanup.fatal and non-Exception worker
abort BaseException keep existing fatal propagation. Invalid/lost IPC or fatal
interruption can still lack a structured diagnostic; no blanket capture guarantee.

## Offline verification

All results below use direct pinned CPython3.12.14, unchanged official isolated
pyOCD0.46.0 and existing dependencies.345 distinct related cases (195 selected
functions) finally pass, including37 new regression cases; Primary separately
passed23 overlapping cases in the clean independent checkout. Do not add those23
to the distinct total.0 unresolved failures/errors/skips; execution history still
contains the2 original environment failures described below.

| Module | Distinct passing cases |
| --- | ---: |
| test_hardware_workflows.py |134|
| test_probe_worker.py |83|
| test_flash_preparation.py |21|
| test_flash_frequency.py |107|

New regressions cover both worker programming methods/all5 diagnostic stages,
ordinary abort compatibility, abort-code allowlist, unsafe diagnostics, immutable
results, trusted/untrusted cleanup, safe code fallback, cancellation/fatal,
success+cleanup partial-evidence, imported flash and non-flash/attach privacy.
Only fakes, temporary fixtures/leases and owned inert test children are used.

Claude issued41 exact test-group commands: t01–t17 with original runner, then
r01–r24 with corrected runner. t17 exited1 with2 passing and2 failing MCP cases;
all other test commands exited0. Primary issued one independent pytest command,
actual exit0. Successful native PowerShell numeric exits are null, not invented0;
actual pytest exits come from the bound runner records and fresh JUnit.
No pending/unfinished test remains. Every launch inventory matched requested
tools and verify startup performed a real harmless native smoke.

Initial isolated PYTHONPATH omitted pywin32.pth's existing win32/win32/lib paths;
2 old, unchanged MCP cases failed during pywintypes import before product assertions.
User explicitly authorized one bounded entry correction/retest. Only those2
failed cases were retried and passed, then the23 previously unexecuted groups ran.
No install, .pth-hook execution, interpreter substitution or global environment
change: only those2 existing child-process search paths were added. Existing DLL/
module hashes are pinned.151 original-entry passes remain valid;194 cases pass
under corrected entry. This is not a claim of a full rerun under one entry.

Exact commands and child argv are retained in task JSONs and execution.json:
run_tests.py t01–t17, run_tests_v2.py r01–r24, and primary_checks.py.
Artifacts live under D:/codex-tmp/st135-flash-evidence and
D:/codex-tmp/fxe01 / D:/codex-tmp/fxe02. Source/test bytes,347 SDK Python files,
existing pywin32 files and protected project/model/identity/ELF/receipts stayed unchanged.

## Abnormal edit invocation is not retroactively accepted

Original edit invocation: CLI exit0, dispatcher exit1,104 matched file-tool calls,
15 successful native edits across the4 allowed files. Root-default Glob violated
read scope; one Edit text mismatch was followed by unauthorized continuation.
The invocation remains NOT_ACCEPTED; original logs, mismatch and later actions
are preserved. No shell/test/hardware action occurred in that edit invocation.

Primary retained and independently reviewed the candidate bytes, without retrying
the edit or implementing product code. Separate first-time verification used the
user's existing authorization; only the actual environment test failure was
retried under the later explicit one-round grant. Candidate-source acceptance is
based on complete-diff review and independently reconciled test evidence, not
the invalid edit invocation or implementer's self-assessment.

## Execution-card re-review and retained limits

Fresh local Claude supplied-source review: actual PowerShell inventory/smoke,
zero main tool calls/edits/tests; NO_BLOCKERS for the card contract, conditional on
all software gates and future hardware prerequisites. Primary discharged software
conditions with the results above and applies the reviewed contract unchanged;
only checkpoint/evidence metadata changes. This does not accept an unexecuted
hardware step. Main card body SHA/identity equivalence is recorded externally.

Primary excludes the reviewer's erroneous address arithmetic and rendering
speculation: actual chunks are32768 at0x08000000,28600 at0x08008000,148 at
0x0800efb8, totalling61516bytes. Literal reset/HID/cleanup constants were retained
from the prior review and verified unchanged; Primary's23-case evidence is in
fxe01/p01 even though the card reviewer was not supplied that whole report.

Keep initial HALTED then SYSRESETREQ/fresh HALTED before programmer; failed prep
cannot reach programmer/readback/success receipt. Service attach5s, SDK per-read10s,
program/readback30s, worker flash300s and existing cleanup remain distinct.
180s is only proposed observation budget, not a hard exit/kill guarantee.
Worker parent abort races child finally close; graceful close/uninit and USB
release are not assured. is_terminal may mean proxy closed while child lives;
lease release alone also does not prove death/USB availability. Failed abort or
unresolved state stops later hardware; no extra recovery, force cleanup or retry.

No actual hardware, runtime replacement/install, packaging, push, release or other
remote action. Target remains UNKNOWN. Prior constructor-only grant stays consumed.
Future ordinary100kHz flash needs a new explicit finite grant/current original
board/probe readiness and final source/runtime/firmware/output/lease preflight.
No1MHz acceptance gate or hardware success is introduced.
