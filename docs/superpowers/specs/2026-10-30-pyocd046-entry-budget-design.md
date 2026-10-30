# pyOCD 0.46.0 offline entry and budget review

Primary specification/review owner: Codex. Accepted origin is
`22f047189fbb0cf1fa7de98e86a2955eb13c5ac1`, branch
`codex/v135-pyocd046-entry-review`. Product/test CodeHead remains
`694e1e912adfc017c31b52630a323bd733567688`. The user authorized offline review,
procedure/card preparation and any necessary implementation through the local
Claude Code CLI; no hardware, installed-runtime replacement or remote action.
There is no retry grant or product ownership override.

## Required outcome

Trace the exact official-wheel 0.46.0 Windows CMSIS-DAP path from Toolkit driver
acquisition/enumeration through Session construction/open/close. Independently
review the updated standard procedure and concrete constructor-only card against
that source. Bind source, SDK, real Python, project, output and shared lease realm.
The prepared entry stays BLOCKED_NOT_EXECUTED until fresh finite hardware
authorization and current board/probe readiness/ownership are provided.

## Budget decision

Keep the current public default attach request timeout at 5000 ms. It is the
deadline for accepting an attach result, not a promise that the CLI and cleanup
finish within five seconds. Keep SDK Interface.DEFAULT_USB_TIMEOUT_MS=10000,
which limits each Windows HID read, not the entire constructor or attach.
Production may expire before the SDK read returns. It must preserve the
initiating timeout/cancellation and existing cleanup outcome, never treat a late
result as permission to continue programming. Do not add these budgets together,
raise either one, force a USB backend, retry, or change frequency/reset policy.

The existing service gives an entered attach one additional one-second terminal
wait. A still-running production worker is handled by its existing owned-child
abort path (one-second join after terminate and, if still alive, another after
kill). Late MODIFY attach success already has resume/state-check/close cleanup;
this is not a new retry and its target-control effects must be explicit in any
future production hardware card. These are separate cleanup paths, not an
eight-second universal wall-clock guarantee. Client HTTP total is currently
305 seconds and worker ordinary RPC default is 30 seconds. Neither replaces the
five-second request deadline; neither is an approved new hardware budget.

The diagnostic helper bypasses service.attach and Session.open. Keep its one
original 20-second parent deadline including startup/READY/GO/work/result/exit,
plus at most two seconds cooperative termination waiting. A ten-second API read
may be observable within that independent budget, but multiple reads, native
open/write/close, enumeration and cleanup are not bounded by that one read's
timeout. A surviving child is UNKNOWN with its lease retained. Do not force-kill
or delete/reclaim a lease outside existing guarded contracts and fresh authority.

## Evidence limits and acceptance

Session(auto_open=False) can temporarily open USB and query DAP_Info before
Session.open configures SWD. _TemporaryOpen may suppress a DAPAccess error; if
open fails before returning, its did-open flag may stay false and its exit does
not close that partial interface. Unopened Session.close returns immediately.
Thus helper ok/sessionConstructed/sessionClosed alone proves neither a healthy
USB exchange, independent native handle cleanup nor board state. Preserve logs
and the one-second native trace; a constructor return with internal suppressed
errors is inconclusive for probe responsiveness. The process must still exit and
the actual lease/health/handle outcomes must be reconciled.

Use existing offline tests only: six real-SDK HID/version/origin tests, three
production fake-worker cleanup cases, three private-injected helper cases.
No test may select the real default backend or shared physical lease. Primary
independently checks selected risks and reviews the complete documentation diff.
A fresh local Claude verify worker independently reviews Primary's source
analysis/procedure/card using only exact hash-bound source-view commands. These
ordinary checks are not tests. Reuse unchanged earlier software evidence only at
its recorded head/owner; no new full matrix, hardware or release acceptance.

If source review finds a necessary product correction, freeze a bounded plan and
delegate it to Claude in a clean isolated implementation worktree before its
separate verification. This review does not require changing working code merely
to make unlike timeout scopes numerically equal.
