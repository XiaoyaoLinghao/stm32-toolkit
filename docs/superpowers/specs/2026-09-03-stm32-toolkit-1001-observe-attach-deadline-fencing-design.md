# STM32TK-1001 OBSERVE Attach Absolute-Deadline Fencing Design

Date: 2026-09-03

Module / phase: `STM32TK-1001 / VS10-A H2`, bounded OBSERVE session-attach reuse correction

Status: `FROZEN FOR USER REVIEW`

Full accepted base: `391c3dd466eafaadbbadce188e1c2b2cba4028ca`

Accepted-base tree: `c183a70a07de1cf404720b82303e2f2ff5f80420`

Original approved design: `1a54ed0f9b5c1dc9544ce3f15dc015e71e7216f3`

Original approved plan: `4639e4c53749a2341baea5340c1f470eefc2538b`

Latest unaccepted report head: `553450694eb7b33ad6d23580f81ebc11595bd685`; tree
`0d1706238c80c450336583d1f194c5ff767353fd`

Active branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`

Remote branch baseline: `74ee5f4c7872af1bb612c9068af36319457e087b`; no remote action is
authorized by this design.

Specification owner and final reviewer: GPT-5.6-sol primary

Implementation owner after separate approval of this written specification and its implementation
plan: the same sole GPT-5.6-luna agent at reasoning effort `max`

Hardware action: none authorized by this design; software implementation and review remain
hardware-free

## 1. Trigger and exact amendment

The first independent review of the OBSERVE session-attach reuse candidate found that attachment
evidence could become reusable before a timed-out or cancelled request finished recovery. A Luna
correction moved publication after successful completion and added a private
`_observation_attachment_lock` so queued attach requests could not observe a candidate while the
backend session was being closed.

The second independent review proved that the correction introduced a different product defect:
a queued OBSERVE attach did not begin its `timeout_ms` accounting until after acquiring the new
lock. A request declaring 20 ms remained pending for roughly 80 ms and then succeeded. It could
therefore return cached evidence or dispatch hardware after its public deadline. The correction
also contradicted the original frozen statement that no new lock would be introduced, while its
report incorrectly claimed timeout semantics were unchanged.

Failure classification: `PRODUCT / OBSERVE SESSION LIFECYCLE AND DEADLINE`. This is not a
hardware, platform, environment, infrastructure, or report-only failure. The inaccurate report
statement is a secondary `REPORT` defect and does not make the product defect less severe.

The user approved this exact bounded design amendment:

- permit exactly one private, service-local OBSERVE attach lifecycle lock;
- capture one monotonic absolute request deadline before waiting for that lock;
- charge lock queueing and backend execution to the same public `timeout_ms` budget;
- retain the existing separately bounded attach-recovery budget only after backend execution has
  actually begun;
- prohibit a request that expires while queued from later reading the cache, publishing evidence,
  or dispatching hardware.

This document supersedes only the original design's `No new lock` statement and its assumption
that the existing backend lock alone serialized the complete OBSERVE attach lifecycle. Every
other approved scenario, public contract, non-goal, ownership boundary, hardware policy, and
verification boundary remains in force.

## 2. Runnable scenarios

### Scenario 1 - same-session OBSERVE guards still use one physical attach

The first OBSERVE `probe.attach` captures its absolute deadline, acquires the private lifecycle
lock within that deadline, sees no committed evidence, and performs the existing serialized
backend attach and identity validation. Only after payload creation and successful completion
does the service publish the immutable session-bound evidence.

Later same-probe, canonical-equivalent logical attach guards capture their own deadlines, acquire
the lifecycle lock within those deadlines, and return the committed evidence without another
backend `open_attach()`, enumeration, close, halt/resume, reset, retry, read, or program action.
The public bind/read composition therefore retains multiple logical identity gates but uses one
physical backend session.

### Scenario 2 - queued expiry is terminal before cache or hardware

One OBSERVE attach holds the lifecycle lock. A later OBSERVE attach declares a deadline shorter
than the remaining queue wait. The later request returns the existing stable public
`PROBE_TIMEOUT` result when its absolute deadline expires.

It never enters the protected lifecycle, never inspects or returns committed evidence, never
creates a provisional candidate, and never calls the backend after the first request releases the
lock. Releasing the first request cannot revive the expired request. Cancellation while queued
has the same no-cache and no-hardware boundary and propagates the accepted cancellation behavior.

### Scenario 3 - entered-backend timeout or cancellation abandons before recovery

If an OBSERVE attach acquires the lifecycle lock and enters backend `open_attach()` but its public
deadline expires or its caller is cancelled, no candidate becomes committed. The service marks
the operation abandoned before recovery, retains the lifecycle lock, waits for the existing
bounded attach outcome, and performs the existing backend close/error-precedence path.

Queued OBSERVE attach requests cannot observe evidence or enter backend execution while that
recovery is active. Their independent absolute deadlines continue to run while queued. The lock
is released only after recovery reaches its existing terminal success or stable cleanup error.

### Scenario 4 - cleanup failure cannot retain evidence or deadlock admission

If recovery close fails, the initiating request returns the existing stable
`PROBE_CLOSE_FAILED`. Any queued request whose deadline expires during recovery returns
`PROBE_TIMEOUT` without later backend dispatch. The lifecycle lock is released when the recovery
path exits, even by error, and the abandoned evidence remains empty.

A later explicit caller request with a fresh deadline may acquire the released lock and reach the
backend according to the existing service contract. This is not an automatic retry. Service stop
continues to clear committed evidence before propagating backend-close or lease-release errors.

### Scenario 5 - changed identity and non-OBSERVE behavior remain unchanged

After committed OBSERVE evidence exists, a different probe selector or non-equivalent target
still returns `PROBE_IDENTITY_MISMATCH` inside the lifecycle fence and before backend dispatch.
It does not replace or close the accepted session.

`CONTROL` and `MODIFY` do not acquire the OBSERVE lifecycle lock and retain their accepted attach,
halt-on-connect, authorization, timeout, recovery, guarded-flash, and cleanup behavior. No state
crosses a service, worker, lease, workspace, session, process, or Toolkit-run boundary.

## 3. Selected architecture

### 3.1 One deadline owner from request admission

For OBSERVE `probe.attach` only, `ProbeService._run_backend()` captures:

```python
deadline = asyncio.get_running_loop().time() + request.timeout_ms / 1000
```

This occurs before any lifecycle-lock wait. The value is monotonic, private, and used only for the
current request. No wall clock, schema field, protocol value, or persisted evidence is added.

Lock acquisition uses the remaining budget derived from that deadline. If no positive budget
remains, the request raises `asyncio.TimeoutError` through the existing service mapping to
`PROBE_TIMEOUT`. The implementation must not create a backend task before successful acquisition.

After acquisition, backend wait uses the same remaining deadline rather than starting a new
`request.timeout_ms` interval. Time spent waiting for the lifecycle lock is therefore never
refunded. Non-OBSERVE operations continue through the accepted path and retain their existing
timeout accounting.

### 3.2 One private lifecycle fence, not a second backend lock

The user-approved bounded override permits exactly one private
`asyncio.Lock` owned by `ProbeService` for OBSERVE attach lifecycle admission. Its responsibility
is distinct from the existing `_backend_lock`:

- the lifecycle lock fences cache inspection, provisional attach work, publication or
  abandonment, and entered-backend recovery;
- the existing backend lock continues to serialize native backend calls across all operations.

The lifecycle lock is not a public API, backend primitive, worker, controller, provider, process,
or persisted lock. It is not used by reads, CONTROL, MODIFY, flash, or other operations. No second
runtime or backend is introduced.

The implementation must avoid nested acquisition of the same lock and must release the lifecycle
lock through structured `async with` cleanup on success, timeout, cancellation, close failure,
and unexpected exceptions.

### 3.3 Attachment evidence has provisional, committed, or abandoned outcomes

The existing committed field remains:

```python
self._observation_attachment: tuple[
    str, str, ProbeAttachmentEvidence
] | None = None
```

A backend result is held only in a request-local provisional variable. It becomes committed only
after backend attach, resolved-target validation, payload serialization, and successful return
from the deadline-bounded serialized backend task. No provisional state is visible to another
request or stored in a second service field.

Timeout, cancellation, validation failure, serialization failure, recovery, or cleanup error
abandons the request-local candidate. Entered-backend timeout/cancellation also clears any prior
committed record before recovery closes the physical session. Service teardown clears the
committed record regardless of backend-close or lease-release error propagation.

### 3.4 Public errors and recovery budgets

Expiry while queued or during the ordinary backend wait retains the existing public
`PROBE_TIMEOUT` code and message. Cancellation remains cancellation. A request that never acquired
the lifecycle lock performs no backend recovery because it never entered hardware.

Once backend attach has entered, the existing `_ATTACH_RECOVERY_SECONDS` budget remains a cleanup
budget, not an extension that can turn the expired request into success. Existing
`PROBE_CLOSE_FAILED` precedence, abort behavior, backend close, and target-restoration rules remain
unchanged. The lifecycle lock stays held throughout that bounded cleanup solely to prevent
another OBSERVE attach from racing a session being closed.

## 4. Frozen ownership and dependency direction

There remains one source of truth for each state:

- request admission: the request-local monotonic absolute deadline;
- OBSERVE attach lifecycle: the private service-local lifecycle lock;
- accepted session evidence: `ProbeService._observation_attachment`;
- native calls and physical handles: the existing backend and `_backend_lock`;
- exclusive probe ownership: the existing lease manager;
- project, firmware, SVD/DWARF, and readable-region provenance: the accepted debug binding and
  workflow layers.

The public client and debug layers continue issuing the same logical attach guards. They do not
own retries, deadline correction, cached evidence, or physical-session replacement.

## 5. Alternatives rejected

### Reuse `_backend_lock` for the complete caller lifecycle

Rejected. The existing lock is acquired inside the backend task and covers native-call
serialization, not caller deadline admission and recovery ownership. Moving it outside would
require a broader refactor of every backend operation or a re-entrant/nested acquisition scheme,
increasing deadlock and compatibility risk.

### Add a provisional shared state machine without a lifecycle lock

Rejected. A shared future or generation state would add more mutable states and wake-up paths than
the bounded problem requires. It would be harder to prove that cancellation, timeout, close
failure, and teardown cannot leak a candidate.

### Keep the current lock and give queued requests a generous timeout

Rejected. A caller's declared timeout is a public contract, not a test tuning value. Extending or
restarting it after queue acquisition would preserve the observed defect and could authorize
hardware access after caller expiry.

## 6. Implementation ownership and retained history

The same sole GPT-5.6-luna/max implementer may change product code only in:

- `tools/stm32-toolkit/src/stm32_toolkit/probe/service.py`.

It may change tests only in:

- `tools/stm32-toolkit/tests/test_probe_service.py`.

The implementation report is corrected separately in:

- `docs/codex/returns/STM32TK-1001-OBSERVE-SESSION-ATTACH-REUSE/implementation-report.md`.

The original specification, original plan, both prior RED/GREEN waves, both review findings, and
the current unaccepted report remain in Git history. They are not rewritten, squashed, deleted,
or relabeled as accepted. This design and its later plan are Sol-owned governance files and are
outside Luna product ownership.

After approval of this written specification and its plan, the implementer first commits new
failing tests against the current unaccepted code head, then commits the minimal product
correction, then commits the corrected report separately. The implementer does not accept its own
diff.

## 7. Required tests and evidence

The new RED tests must directly prove:

- the first blocking OBSERVE attach has entered before the queued request is created;
- a queued request's short absolute deadline expires while the first attach still holds the
  lifecycle lock;
- the queued request returns `asyncio.TimeoutError` at the service seam and `PROBE_TIMEOUT` at the
  existing public service/client seam, without reading committed evidence;
- releasing the first attach after queued expiry does not cause a later backend `open_attach()`
  for the expired request;
- an entered-backend timeout/cancellation holds admission until recovery close finishes and then
  permits a fresh explicit request;
- recovery-close failure returns `PROBE_CLOSE_FAILED`, a queued short-deadline request returns
  `PROBE_TIMEOUT`, the lock is released without deadlock, and a later fresh request does not reuse
  abandoned evidence;
- the same-service normal-stop, backend-close-error, lease-release-error mutation tests remain
  effective;
- same-identity reuse, changed-identity rejection, first-failure non-caching, and CONTROL/MODIFY
  compatibility remain unchanged.

Timing assertions use event ordering and a generous bounded tolerance; they must not depend on
task creation order. Tests create the queued request only after the first backend-entered event.
They assert backend event sequences and task outcomes, not the private cache field.

### Luna slice verification

Use CPython 3.12, source/test `PYTHONPATH`, `-p no:cacheprovider`, and fresh external run-owned
basetemps. Run the new deadline/recovery tests first, then only:

- `tools/stm32-toolkit/tests/test_probe_service.py`;
- `tools/stm32-toolkit/tests/test_debug_firmware.py`;
- `tools/stm32-toolkit/tests/test_debug_read.py`.

This is the same bounded matrix as the approved slice. No full suite, hardware, package, install,
release, coverage, CI, or other Python version is authorized. Run `git diff --check`, audit exact
changed paths, and clean only exact run-owned outputs.

### Sol independent review

Review from a new detached clean worktree at the returned report head. Inspect the complete
accepted-base-to-final-code diff, the correction delta, and the report-only commit separately.
Repeat the new deadline/recovery tests and the same three-file matrix in a fresh Sol-owned external
basetemp. Independently prove that queue wait consumes the deadline and an expired request never
dispatches later. Acceptance also requires accurate TDD lineage, clean worktrees, classified
cleanup, and no public or scope expansion.

## 8. Explicit non-goals

- No public protocol, client, CLI, MCP, schema, error inventory, project model, runtime, package,
  Agent adapter, or persisted-evidence change.
- No second service, worker, backend, provider, controller, runtime, or MCP registration.
- No change to PyOCD connection options, 100 kHz OBSERVE policy, ordinary flash, guarded flash,
  under-reset recovery, control authorization, target restoration, or hardware identity rules.
- No retry, reconnect after failure, fallback, frequency probing, reset, unlock, erase, program,
  arbitrary write, or target-family expansion.
- No removal of public logical bind or read identity/provenance guards.
- No lock outside the one private OBSERVE lifecycle fence authorized here.
- No hardware action, push, PR mutation, merge, tag, release, close, or remote branch deletion.
- No automatic transition to another VS10 slice or VS10-B.

## 9. Acceptance and stop boundary

This correction is accepted only when all five scenarios have direct evidence; a queued request's
deadline includes lock wait; expired work cannot later inspect cache, publish evidence, or dispatch
hardware; recovery and cleanup release the lifecycle fence without stale evidence or deadlock;
the focused CPython 3.12 matrix passes; and the complete diff has no unresolved product, safety,
compatibility, test, report, or scope defect.

Software acceptance does not authorize hardware or remote publication. After acceptance, stop and
request a separately authorized single public read-only bind plus `GPIOE.ODR` read. A failed
physical confirmation stops without retry.
