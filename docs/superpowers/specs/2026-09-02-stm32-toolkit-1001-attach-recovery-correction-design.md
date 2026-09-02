# STM32TK-1001 Attach Recovery Correction Design

Date: 2026-09-02
Module / phase: STM32TK-1001 / VS10-A
Status: FROZEN FOR USER REVIEW
Full accepted product base: `03036f912e16006b1d2030b212962d3704e8a20f`
Accepted-base tree: `b7688538514a50f2e083d4bef788030f342daaba`
Reviewed but unaccepted predecessor code head: `1783b33ab77bdce2f6103e7f765db8bad8cd3d00`
Predecessor tree: `fdf79c8b8c043c3434251dcc6edb6dd6c4d184dc`
Specification owner and final reviewer: GPT-5.6-sol primary
Implementation owner: one GPT-5.6-luna agent at reasoning effort `max`
Remote action: none authorized

## 1. Purpose and predecessor status

This document is a bounded correction to
`2026-09-02-stm32-toolkit-1001-pyocd-connection-policy-correction-design.md`.
It does not replace that specification's accepted transient-halt policy, canonical target gate,
flash error mapping, public interfaces, or non-goals.

The predecessor candidate at `1783b33a` passed the focused software matrix with `463 passed` and
one existing Windows skip, but independent complete-diff review returned `REVISION_REQUIRED`.
The candidate is therefore not an accepted product head. Three lifecycle defects remain:

1. `PyOCDBackend.open_attach()` can enter `session.open()`, allow PyOCD to halt the target, and
   then receive an exception before it captures `session.board.target`; its cleanup can close
   without the required resume attempt.
2. `ProbeService` uses `ProbeBackendWorker.abort_owned_execution()` for attach timeout or
   cancellation. That method terminates the owned child and bypasses the worker child's `finally`
   cleanup, so a halted target can remain halted or unknown.
3. Direct-backend cancellation cleanup and simultaneous restoration/close failures do not
   consistently produce sanitized, authoritative `PROBE_CLOSE_FAILED` with the initiating safe
   error as the explicit cause.

The full final acceptance review remains `03036f91..FINAL_CODE_HEAD`; the predecessor commits and
their valid RED evidence remain part of the lineage and are not rewritten.

## 2. Approved user scenarios

### Scenario 1 — a partially failed PyOCD open restores before close

Given one exact probe selector and explicit target, Toolkit creates one PyOCD session using the
already-approved halt/Pack policy. Toolkit captures the session's pre-created target object before
calling `session.open()` whenever that object is available. If `session.open()` later fails after
the target may have halted, Toolkit performs exactly one bounded `resume()`, verifies `running`,
then closes the session/probe. No backend attachment fields or successful evidence are published.

If no target object was ever discoverable, Toolkit closes only acquired resources as already
specified. It does not invent a target, reopen the session, reset, erase, unlock, retry, or report
success.

### Scenario 2 — attach timeout or cancellation cooperatively restores the worker-owned target

When `probe.attach` has entered the existing production `ProbeBackendWorker`, timeout or caller
cancellation does not immediately terminate the child. Probe Service first waits a fixed one-second
interval for the in-flight attach task to reach a terminal response. If the attach succeeds, the
same existing worker proxy serially performs exactly one `resume`, requires
`target_state().state == "running"`, and closes the backend and owned child before the original
timeout or cancellation is propagated. If attach finishes with a sanitized backend failure, that
failure proves its own candidate cleanup under the corrected backend contract; an embedded
`PROBE_CLOSE_FAILED` remains authoritative.

This is recovery of one already-owned attach attempt, not a retry. No second probe, session,
backend, worker, controller, or runtime is created.

### Scenario 3 — an unresponsive child fails explicitly and is terminated only as last resort

If the in-flight worker attach does not reach a terminal response within the fixed recovery
interval, the proxy terminates and joins only its exact owned child using the existing bounded
termination mechanism. The public outcome is the existing sanitized `PROBE_CLOSE_FAILED`, not a
normal timeout, cancellation success, or successful attachment. The target state is explicitly
unknown; no physical recovery claim is made.

Hard termination is therefore an unsafe-cleanup fallback with an authoritative safety error. It
is never the first attach-cancellation action and never produces PASS evidence.

### Scenario 4 — cleanup errors have one deterministic safe precedence

For backend candidate validation, service identity rejection, direct-backend cancellation, and
worker recovery:

1. The initiating failure is normalized to an existing sanitized Toolkit error.
2. Toolkit attempts at most one resume/state proof when a target may be halted.
3. Toolkit attempts close even if restoration fails.
4. If close or owned-child cleanup cannot be completed, the final public error is
   `PROBE_CLOSE_FAILED`.
5. `PROBE_CLOSE_FAILED.__cause__` is the initiating sanitized Toolkit error, not a raw PyOCD,
   OS, path-bearing, hardware-identifier-bearing, or test exception.
6. If restoration and close succeed, the original timeout/cancellation or existing sanitized
   attach/identity/state error remains authoritative.

Successful-looking attachment evidence is never returned after recovery or cleanup begins.

## 3. Selected architecture

### 3.1 PyOCD candidate acquisition

`PyOCDBackend.open_attach()` keeps all candidate state local until identity and final target state
are proven. After `create_session()` and before `session.open()`, it reads
`session.board.target` through one private candidate-target helper. If the first lookup is empty,
it may repeat the same lookup once after an open exception because PyOCD can populate the board
during partial initialization. It must not enumerate another probe or construct another session.

Every failure after `session.open()` has begun uses the same local cleanup authority:

- when a candidate target exists: one resume, one running-state proof, then close;
- when no candidate target exists: close only acquired resources;
- when close fails: sanitized `PROBE_CLOSE_FAILED` chained from the initiating sanitized error;
- when restoration fails but close succeeds: the existing sanitized attach/state error required
  by the predecessor specification.

### 3.2 Probe Service mediates recovery through the unchanged worker contract

`ProbeBackendWorker` remains the only production worker and the only process owner. Its product
bytes, `_METHODS`, IPC protocol, call codec, process topology, and public `ProbeBackend` surface do
not change in this correction.

Probe Service already owns the asynchronous task that wraps the synchronous worker call. On
attach timeout/cancellation after backend entry it performs this sequence:

1. Wait at most one second for the exact owned attach task to finish; repeated
   caller cancellation cannot skip this bounded wait.
2. If the task succeeds, the worker call lock is necessarily released. For a MODIFY attachment,
   invoke the existing `resume()` and `target_state()` proxy methods and require running; for an
   OBSERVE/CONTROL attachment, the accepted backend contract already proves running. Then invoke
   the existing `close()` proxy method.
3. If the task finishes with a backend failure other than `PROBE_CLOSE_FAILED`, preserve the
   original timeout/cancellation because the corrected backend failure path has already restored
   and closed its local candidate. If it finishes with `PROBE_CLOSE_FAILED`, cleanup failure
   overrides the terminal request.
4. If the task does not finish within the recovery interval, call the existing
   `abort_owned_execution()` exactly once, join only the exact owned child, and return sanitized
   `PROBE_CLOSE_FAILED` with target state classified as unknown.
5. If resume, state proof, close, termination, or join fails, return sanitized
   `PROBE_CLOSE_FAILED` from the initiating sanitized recovery error.

This design does not create a second connection, side channel, IPC version, worker method,
process, retry, or background controller.

### 3.3 Probe Service cancellation boundary

For `probe.attach` only:

- Probe Service applies the same bounded task wait to production worker and admitted direct
  in-process backends.
- If the attach succeeds, Probe Service explicitly calls `resume()`, requires running state for a
  MODIFY attachment, then closes. An OBSERVE/CONTROL successful attach is already required to be
  running, so it closes without an additional resume.
- If the attach task cannot terminate within the bound and the backend exposes the existing
  `abort_owned_execution`, Probe Service invokes that existing hard-termination fallback once and
  returns `PROBE_CLOSE_FAILED`.
- A direct test backend without an owned child cannot be force-terminated; failure to reach its
  bounded terminal state within one second returns `PROBE_CLOSE_FAILED` and is never reported as
  safe cleanup. Test seams used by this slice must release within that bound so no test worker
  remains live after a terminal assertion.
- A direct close failure is normalized to `PROBE_CLOSE_FAILED`; it never escapes as
  `PROBE_INTERNAL_ERROR`.

The guarded-flash commit point and CONTROL-operation cancellation behavior are unchanged.

## 4. Rejected alternatives

### Infinite wait for attach completion

Rejected because a wedged driver or USB stack could block the local service indefinitely and
destroy the existing timeout contract.

### Immediate terminate/kill while returning ordinary timeout or cancellation

Rejected because it can bypass target restoration while making the result look like routine
control flow. Hard termination remains only an explicit `PROBE_CLOSE_FAILED` fallback.

### A second worker, recovery controller, backend, runtime, or IPC channel

Rejected because it duplicates ownership, expands the failure surface, and violates the
single-runtime/single-backend/single-controller product boundary.

## 5. Error, causality, and data-safety contract

No new public error code is introduced.

- Partial-open, Pack, resume, and state failures retain the predecessor specification's existing
  sanitized attach/state error mapping when cleanup succeeds.
- Target mismatch retains `PROBE_IDENTITY_MISMATCH` when restoration and close succeed.
- Flash still converts only `PROBE_IDENTITY_MISMATCH` to
  `FIRMWARE_IDENTITY_MISMATCH`; it does not convert `PROBE_CLOSE_FAILED`.
- Any failed close, failed worker recovery, failed owned-child join, or required hard termination
  produces `PROBE_CLOSE_FAILED`.
- Cancellation remains cancellation only after safe recovery and close complete.
- Error messages/details and explicit cause chains contain no raw host path, probe hardware ID,
  PyOCD exception text, OS exception text, secret, or user data.

No recovery path performs reset, erase, unlock, mass erase, programming, retry, fallback probe
selection, or session reopen.

## 6. Bounded implementation and test ownership

The sole GPT-5.6-luna/max implementer may correct product code only in:

- `tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py`
- `tools/stm32-toolkit/src/stm32_toolkit/probe/service.py`

`worker.py` and `flash.py` are frozen at predecessor commit `1783b33a`; no product change in either
file is needed.

Applicable correction tests may change only:

- `tools/stm32-toolkit/tests/fakes/fake_pyocd.py`
- `tools/stm32-toolkit/tests/test_pyocd_backend.py`
- `tools/stm32-toolkit/tests/test_probe_service.py`
- `tools/stm32-toolkit/tests/test_probe_worker.py`

The accepted predecessor RED tests and test-design reconciliation remain. Tests must add:

- partial `session.open()` failure after a halted candidate exists, with exact
  `resume -> get_state -> close` behavior and no published attachment;
- simultaneous initiating/restoration and close failures with sanitized explicit cause ordering;
- direct-backend cancellation/timeout where `close()` does not resume implicitly;
- direct cleanup close failure returning `PROBE_CLOSE_FAILED`, never `PROBE_INTERNAL_ERROR`;
- production-worker cooperative service recovery before terminal propagation, using the existing
  worker methods and process topology;
- unresponsive worker fallback proving exact owned-child termination, no late action, and
  `PROBE_CLOSE_FAILED` with target state recorded as unknown rather than PASS.

The implementation agent must stop if any product path outside these two files is required.
It must not modify worker/protocol/schema files, add a worker method to `_METHODS`, weaken an existing
assertion, or relabel fake/worker evidence as physical target PASS.

## 7. Verification layers and acceptance

### Slice correction

Run only the affected backend/service/worker tests first with CPython 3.12, source/test
`PYTHONPATH`, cache provider disabled, and an external run-owned basetemp.

### Focused integration

After correction, rerun the predecessor six-file matrix and add `test_probe_worker.py` because
the reviewed defect is in the production process boundary. No full suite, coverage, packaging,
release, UI, or hardware run is justified by this correction.

### Independent acceptance

The Sol primary reviews the complete `03036f91..FINAL_CODE_HEAD` diff in a fresh detached clean
worktree. Acceptance requires:

- all frozen public behavior and focused tests pass;
- no unresolved product/security/compatibility defect;
- no scope outside the paths above;
- accurate RED/GREEN/report lineage;
- run-owned temporary artifacts cleaned or explicitly classified;
- implementation worktree clean and remote state stated.

Hardware remains `NOT RUN BY IMPLEMENTER`. A later physical attach/flash smoke requires a Sol
software acceptance verdict and the user's existing hardware authority. Runtime-launcher
relocation remains a separate slice. No push, PR mutation, merge, tag, release, or other remote
action is authorized by this specification.

## 8. Non-goals

- No new runtime, Probe Service, backend, provider, controller, process type, or IPC protocol.
- No CLI/MCP/schema/version change.
- No new Python or platform support.
- No VS Code or Keil runtime configuration dependency.
- No automatic retry, reset, erase, unlock, program, fallback probe, or target-family fallback.
- No hardware execution by the implementer.
- No runtime-launcher correction, packaging, CI, collaboration automation, release, or remote
  mutation.
