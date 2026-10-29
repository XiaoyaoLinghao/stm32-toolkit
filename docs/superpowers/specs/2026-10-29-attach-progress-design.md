# ATTACH-PROGRESS — retained connection stage evidence

Approved product scope: the user's 2026-10-29 instruction to add internal connection
stage logs, delegate implementation to local Claude Code CLI, and independently
review/verify offline. No hardware, installation or remote publication is authorized.
Primary Codex owns this design and acceptance; Claude owns product/test/guide edits.
Accepted base: `e4d9118e1c83f139db2959acbd4076a357c37992`.

## Problem and behavior

The retained normal 1 MHz failure returned `service-attach-deadline`, then terminal
wait timeout and worker abort, with `lateAttach=null`. It supplies no internal stage.
Initial worker readiness precedes service attach; lazy driver acquisition,
enumeration, Session creation/open and state/identity validation remain candidates.
Offline import timing does not establish the previous physical cause.

Add bounded structured progress to an existing attach failure diagnostic when the
service has a matching current worker attach snapshot. It must survive worker abort
and existing worker/service/CLI/MCP diagnostic preservation. Do not add hardware calls,
retry, recovery, resets, state repair, process discovery, raw logging or persistent
telemetry infrastructure. Successful attachment/results retain their exact contract.

An optional `progress` key extends the existing closed `attachDiagnostic` version 1.
Absent progress retains the exact old five-key shape and all legacy projections.
The optional value is a detached closed object:

```json
{
  "version": 1,
  "clock": "parent-receipt",
  "elapsedMs": 5010,
  "events": [
    {"stage": "worker-dispatch", "elapsedMs": 0},
    {"stage": "driver-acquire", "elapsedMs": 1},
    {"stage": "probe-enumeration", "elapsedMs": 965},
    {"stage": "session-open", "elapsedMs": 1000}
  ]
}
```

`elapsedMs` is the parent's monotonic elapsed time from dispatch to snapshot capture
(frozen at the terminal call when available). Each event is a stage-entry marker
timestamped when the parent receives it, using that same origin. These are observed
IPC timing markers; differences are approximate software-stage intervals, not exact
hardware durations, completion proofs or target state. A hung operation retains the
last received marker; markers still buffered/unreceived are not invented.

Closed ordered vocabulary: `worker-dispatch`, `driver-acquire`, `probe-enumeration`,
`prior-attachment-close`, `session-create`, `target-resolve-before-open`,
`session-open`, `target-resolve-after-open`, `target-identity`, `halt-verify`,
`resume`, `resume-verify`. `worker-dispatch` is first, parent-created, at zero.
Later stages are an ordered subsequence (no duplicate); halt and resume branches
cannot coexist, and resume-verify requires resume. Existing preserve-observe emits
neither control branch. Max events is the vocabulary size; all millisecond values
are exact integers (not bool), nonnegative, nondecreasing, <=600000 and <=snapshot
elapsedMs. Extra keys, strings/floats/NaN, recursive values, unknown/reordered stages
and oversized lists are invalid. The public progress object contains only the above
constants and integers: no request/token/probe/target IDs, paths, addresses,
exception text, registers or raw pyOCD output. Validation and copy helpers belong
below backend/worker/service to avoid dependency cycles.

## Transport and ownership

Use the existing owned worker IPC stream for small stage frames, bounded by the
closed vocabulary, tied to the exact current open_attach worker request ID.
No reader thread or second connection, subprocess, file sink, backend poll or target
read is introduced. Progress frames are legal only while receiving that matching
open_attach response. Reject malformed, extra-key, wrong-ID, non-attach, duplicate,
reordered or excessive frames with the existing fail-closed worker protocol cleanup.
Every receive uses the same original absolute deadline; progress never renews it.
Ready/success/error result envelopes keep their existing meaning and exact shapes.

Instrument PyOCDBackend through a private optional stage callback. Emit before
the corresponding existing operations and only during open_attach. Driver acquisition
must remain the same single lazy acquisition preceding enumeration, not a warmup,
extra enumeration or double import. Keep all validation, prior-close, attach,
identity/state checks, cleanup and authority order unchanged. Callback transport
exceptions must not trigger new target actions or replace the primary backend error.
An optional private registration hook may also support spawned deterministic test
backends; it is not a new public backend capability or dynamic import extension.

Parent snapshots must be bounded, detached, local-only and available without
acquiring the blocking call lock or invoking IPC/hardware. Scope each to the exact
service attach request token, supplied through a private optional worker attach
entry; other backends retain the original open_attach call. Reset on a new attach
and refuse mismatching tokens so earlier attempts cannot contaminate queued/new
attempts. Request tokens remain private and never enter public progress.
Protect the small metadata snapshot against the service/receiver/abort race without
holding locks across waits or hardware. Preserve the snapshot after owned abort.

The service adds validated matching progress to its existing deadline/cancellation
attach diagnostics after the existing terminal wait/abort path. All existing branches
that already return an attach diagnostic in this timeout path must retain it through
cleanup and late-error merging. Queue-before-dispatch gets no old trace. Invalid or
unavailable optional snapshot data is omitted without replacing the initiating error.
Cancellation propagation itself is unchanged. Ordinary non-timeout errors without an
existing diagnostic need no new error envelope; success carries no public progress.

## Boundaries and evidence

Keep normal 5 s and Monitor 35 s attach budgets, one-second terminal wait, worker
deadlines, frequencies, connection policy, flash preparation and all cleanup/control
semantics unchanged. No schema/protocol version bump, release metadata alignment,
installation, packaging or remote action. Document this as Unreleased/planned1.3.5.

Required offline evidence, owned by Claude and independently reviewed by Primary:
closed-schema hostile inputs and old-envelope compatibility; stage order on halt,
resume and preserve branches with no extra control; callback failure isolation;
real Windows spawned fake backend that emits stages then stalls, service timeout,
owned abort and retained trace/no late program; stale-token rejection and detached
snapshots; malformed/wrong-ID/out-of-order/overflow/nonattach IPC refusal and unchanged
absolute receive deadline; preservation through diagnostic/cleanup/public JSON;
unchanged exact successful attachment. Use meaningful deterministic substitutes,
not real probe discovery or Session connections. Existing worker, service, adapter,
flash/Monitor/public workflow contracts provide proportionate regression coverage.

Physical effectiveness and the old attach stall remain unverified until a separately
authorized later phase uses the reviewed runtime and a fresh finite execution card.
