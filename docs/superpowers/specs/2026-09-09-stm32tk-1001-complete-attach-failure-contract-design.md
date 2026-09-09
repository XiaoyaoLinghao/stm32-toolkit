# STM32TK-1001 Complete Attach Failure Contract

Status: **approved by the user on 2026-09-09; implementation authorized but not yet accepted**

Accepted base: `776c052d43544ba599f16dde74f1264fd69cdb10`

Owner ledger: GPT-5.6-sol owns this specification, the implementation plan, integration decisions, and independent acceptance. One GPT-5.6-luna/max agent owns the approved product implementation and implementation tests. The active local branch is `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`. The user authorized local implementation, focused offline tests, local commits, independent review, and local fast-forward integration on 2026-09-09. Packaging, deployment, runtime replacement, hardware action, and every remote action remain unauthorized.

The deployed runtime is built from the accepted base. The latest replacement-board flash attempt returned `PROBE_ATTACH_FAILED` with `details.stage=cleanup-resume`; it did not reach program or readback, and OBSERVE did not run. That result proves a cleanup resume failure occurred. It does not recover the initiating attach failure and does not prove the target's current physical state. The old-board attempt 7 remains PASS. The three observations, Task 9, Task 10, and VS10-A remain incomplete.

## Runnable scenarios

1. A typed or untyped failure during session creation/open, target resolution/identity, or halt/resume verification remains the primary attach failure even when candidate restoration and close later produce one or more failures. Existing public code and message precedence remain compatible, while a closed diagnostic retains the primary and each modeled cleanup outcome.
2. A service deadline, caller cancellation that is replaced by a cleanup error, or post-attach identity mismatch records only operations that actually ran. A verified target state is historical evidence from an existing state read; after close, no current target state is claimed.
3. A valid diagnostic crosses worker IPC, service, client, flash, hardware workflow, debug binding, Monitor observation, Monitor runtime, and Monitor service without arbitrary keys or sensitive values. Worker crash, worker deadline, cancellation with no returned error, and malformed IPC keep their existing contracts and do not receive a fabricated primary.
4. The public flash seam proves attach success is required before programming. Any attach-path failure remains zero-program, including failures whose existing outer code is `PROBE_CLOSE_FAILED`, `FIRMWARE_IDENTITY_MISMATCH`, or `HARDWARE_CLEANUP_FAILED`.

## Non-goals

- No generic diagnostics framework, persistent log format, exception-text capture, stack trace, path, raw serial, backend object, or arbitrary details transport.
- No new probe enumeration, attach, target-state read, reset, halt, resume, close, retry, reconnect, recovery-under-reset, program, or readback operation. The order and count of existing hardware calls remain unchanged.
- No weakening of selector, workspace, session, build, ELF, target, authorization, lease, or freshness checks.
- No reinterpretation of a software stage or exception type as a physical board, cable, power, or probe cause. Physical classification still requires physical evidence.
- No retroactive rewriting of attempt 7, either replacement-board failure, canonical flash evidence, or consumed authorization.
- No promise that the next physical attempt will succeed or that every future third-party exception will be specifically classified. Unrecognized exceptions remain `unknown`.

## Current chain and failure branches

Line numbers refer to the accepted base. `Program?` answers whether `flash_firmware` can reach `program_verified_elf` after that branch.

| Layer and source | Trigger and current behavior | Existing cleanup and precedence | Frozen result | Program? |
|---|---|---|---|---|
| `probe/pyocd_backend.py:559-636,726-733` | Invalid selector/target, enumeration/descriptor failure, no match, or ambiguity fails before a session exists with its existing specific code. | No candidate cleanup. `_select_probe` precedes prior-session close. | Keep the specific code/message and existing empty details. Do not fabricate an attach diagnostic. | No |
| `probe/pyocd_backend.py:734,1282-1298` | Closing a previously held attachment fails before the new session is created. | `close()` clears internal references before `_close_external`; the close error currently escapes without attach context. | Keep `PROBE_CLOSE_FAILED`; add a primary at `prior-attachment-close` and only the close operations actually attempted. | No |
| `probe/pyocd_backend.py:757-760` | Session creation raises typed or untyped. | If no session is returned, no cleanup runs. | Primary `session-create`; typed Toolkit error retains its stable source code, untyped uses the closed type classifier. | No |
| `probe/pyocd_backend.py:761-765` | Pre-open target lookup or `session.open()` fails. A partially opened target may become available only after failure. | Lines 816-837 and 847-871 retry the existing target lookup, then either restore+close or close only. Cleanup can replace the initiating failure. | Primary is `target-resolve-before-open` or `session-open`; record the retry only when it produced target-state evidence, then record existing resume/state/close operations without replacing primary. | No |
| `probe/pyocd_backend.py:766-792` | Post-open target missing, core count invalid, or target identity unavailable. Current legacy stage is `target-resolve`, including identity errors. | Candidate resume/state verification and external close run; resume or close can replace the initiating error. | Precise primary `target-resolve-after-open` or `target-identity`; preserve legacy top-level `stage=target-resolve` when the outer code remains `PROBE_ATTACH_FAILED`. | No |
| `probe/pyocd_backend.py:793-807` | MODIFY halt-state verification or OBSERVE resume/resume verification fails. | Candidate resume/state verification and close run. A resume cleanup failure becomes `stage=cleanup-resume`; close failure becomes `PROBE_CLOSE_FAILED`. | Primary `halt-verify`, `resume`, or `resume-verify`; retain current outer code/message and legacy stage projection, plus all modeled cleanup entries. | No |
| `probe/pyocd_backend.py:808-872` | A typed `ProbeBackendError` is either normalized when already `PROBE_ATTACH_FAILED` or re-raised; any other exception becomes generic `PROBE_ATTACH_FAILED`. | Both catch branches discover a partial target if possible and invoke the same candidate cleanup; cleanup can replace either initiating form. | Preserve the current typed/untyped outer selection. Build the primary before cleanup and merge cleanup into it; never inspect the discarded exception message. | No |
| `probe/pyocd_backend.py:644-721` | Target-state reads, candidate resume, session close, probe open-state checks, and probe close can fail independently. `_close_external` currently retains only a single aggregate error; `_restore_candidate_and_close` replaces the primary. | Resume and state verification precede close. Session close, pre-close `is_open`, conditional probe close, and final `is_open` already run in that order. | Record each existing attempted operation in order. No new read or close is added. The last successfully returned state is historical only. Existing outer close/resume precedence is unchanged. | No |
| `probe/worker.py:222-309` | A child backend error is sanitized and sent before the implicit `backend.close()` in `finally`; that close may fail or hang and its outcome is not in the response. | Keep this ordering. Sending only after close could turn a currently received attach error into parent `PROBE_TIMEOUT`. The child still attempts the same final close after send; the parent may interrupt it during its existing abort. | Worker accepts only the exact schemas below. It never transports exception text/class/path/raw identifiers. A legacy valid attach stage may be promoted. The unobservable final close gets no fabricated outcome. | No |
| `probe/worker.py:362-439` | Parent receive deadline, dead child, malformed response, invalid details, abort/reap failure. After a valid error response, line 418 already aborts/reaps the exact child before raising it. | No second response, close acknowledgement, extra wait, or deadline extension is added. A hang before the first error frame keeps the current receive-timeout path. | Preserve current outer timeout/abort code and message. After a valid error frame, append only the observable `worker-parent-abort` result; abort failure keeps its existing `PROBE_BACKEND_ERROR` precedence while retaining the received primary. Other crash/deadline/malformed branches get no fabricated primary. | No |
| `probe/service.py:863-916` | Backend attach succeeds, then service target identity mismatches. | MODIFY tries resume and state verification; all levels close. Resume failure is collapsed; close or restoration can replace identity primary. | Primary `service-target-identity`, reason `identity-mismatch`; retain current outer code/message precedence and record the existing resume/state/close outcomes. | No |
| `probe/service.py:1141-1154` | Request times out or is cancelled before entering the backend lock. | Task is cancelled; no backend/hardware operation occurred. | Timeout keeps `PROBE_TIMEOUT` and may carry primary `service-backend-queue`; cancellation remains cancellation with no public result. No cleanup entries and no target state. | No |
| `probe/service.py:70-105,1155-1175` | An entered attach reaches terminal error during the absolute recovery wait, or does not become terminal within one second. | Current non-close task errors are discarded by bare `raise`; a recovery timeout attempts exact-worker abort and always becomes `PROBE_CLOSE_FAILED`; abort failure is swallowed. | Preserve current outer code/message. Primary is the request deadline/cancellation already observed. A single valid terminal task diagnostic is stored in the bounded `lateAttach` slot; terminal-wait and worker-abort outcomes remain top-level cleanup. No primary is flattened into a cleanup entry. | No |
| `probe/service.py:1177-1210` | Attach completes successfully only after deadline/cancellation. | MODIFY resumes and verifies; all levels close. Recovery or close failure becomes `PROBE_CLOSE_FAILED`; success rethrows original timeout/cancellation. | Preserve the original deadline/cancellation as primary and record the already-existing resume/state/close actions. If all cleanup succeeds, timeout/cancellation behavior is unchanged. | No |
| `probe/service.py:1442-1474` | Request handler maps backend and timeout exceptions to `ProbeResponse`. | Target-operation restrictions do not apply to `probe.attach`. | Preserve existing outer code/message. Forward only a validated diagnostic; cancellation still propagates. | No |
| `probe/service.py:1485-1537` | Service stop may fail in runner cleanup, backend close, and lease release. It currently retains only the first error. | All three are attempted and state references are cleared; endpoint unlink is best-effort. | When an upstream valid attach diagnostic exists, expose ordered outcomes for the existing stop operations so an outer workflow can merge them. Otherwise retain the existing first-error contract. Never invent a primary in `stop()`. | No |
| `probe/supervisor.py:123-137` | Supervisor waits for service stop or directly closes an owned backend, then clears all owned references. It currently discards a successful return and only propagates a failure. | This is the required boundary between service-internal cleanup and hardware/Monitor cleanup. | Return an internal closed cleanup fragment on success; on failure propagate a safe internal cleanup error carrying the fragment and chaining the first error. Call count, ordering, reference clearing, and public workflow code/message remain unchanged. | No |
| `probe/client.py:136-202,295-328,383-406`; `probe/protocol.py:165-175` | Protocol validates/encodes details and client forwards service failures. Transport failures have their own generic code. | No target cleanup occurs here. | Product code remains unchanged. Tests prove a valid diagnostic passes and an invalid response is rejected by existing boundaries. | No |
| `debug/firmware.py:213-223,250-260` | Non-identity `ProbeClientError` details pass through. Both identity mappings keep `DEBUG_TARGET_MISMATCH` but currently discard details. | No local cleanup. The service owns attachment cleanup. | Keep both existing debug code/messages; preserve only a validated nested attach diagnostic on identity mappings. | No |
| `probe/flash.py:562-603,647-659` | Generic attach failures preserve details and do not program. `PROBE_IDENTITY_MISMATCH` maps to `FIRMWARE_IDENTITY_MISMATCH` with `field/rule`, currently discarding attach details. | No workflow cleanup in this function. Programming begins only at line 591 after attach and identity validation. | Keep existing flash code/message and `field/rule`; add only a validated nested diagnostic. All attach failures remain zero-program. | No |
| `hardware_workflows.py:471-514,594-640` | Client close and service stop are both attempted. Any cleanup failure currently replaces the action result with `HARDWARE_CLEANUP_FAILED {}`. | Cleanup runs after the action and retains only aggregate failed/cancel/fatal state. | Keep `HARDWARE_CLEANUP_FAILED` precedence. If the action carried a valid attach diagnostic, merge workflow cleanup outcomes so its primary survives. With no attach diagnostic, preserve current behavior. | No |
| `monitor_observation.py:640-646,816-875,895-1049` | Initial binding and revalidation map failures to Monitor codes and erase details. Initial cleanup tries client, service, and root guard; a cleanup error becomes `MONITOR_CLEANUP_FAILED {}`. | All cleanup resources are attempted; only aggregate failure remains. | Keep Monitor code/messages. Preserve only a validated nested attach diagnostic from binding/revalidation, and append existing Monitor cleanup outcomes. Other provenance details remain omitted. | No |
| `stm32-monitor/runtime.py:1119-1151`; `stm32-monitor/service.py:115-124` | Runtime performs its existing discovery check, calls the Toolkit observation factory, and forwards failure details; Monitor service forwards protocol details. | No additional attach cleanup at these layers. | Product code remains unchanged. Focused tests prove the final safe diagnostic reaches the public Monitor response. | No |
| `probe/flash.py:589-643` | Only a successful, validated attachment reaches stale-result removal, program, full readback, freshness recheck, and evidence commit. | Normal outer workflow cleanup follows. | Success behavior and evidence format remain unchanged. Attach diagnostics never appear in success evidence. | Yes, only this row |

## Closed diagnostic contract

The existing outer `code` and `message` remain the compatibility authority. The new information is nested under `attachDiagnostic`; consumers must not infer the primary from the outer code when cleanup currently has precedence.

```json
{
  "stage": "cleanup-resume",
  "attachDiagnostic": {
    "version": 1,
    "primary": {
      "stage": "session-open",
      "reason": "probe-disconnected",
      "sourceCode": "UNTYPED"
    },
    "lateAttach": null,
    "cleanup": [
      {"stage": "candidate-resume", "outcome": "failed", "reason": "probe-disconnected", "sourceCode": "UNTYPED"},
      {"stage": "session-close", "outcome": "succeeded"}
    ],
    "lastVerifiedTargetState": null
  }
}
```

### Exact shape rules

- `attachDiagnostic` has exactly `version`, `primary`, `lateAttach`, `cleanup`, and `lastVerifiedTargetState`. `version` is integer `1`.
- `primary` has exactly `stage`, `reason`, and `sourceCode`, each a string in the closed sets below.
- `lateAttach` is either `null` or an exact object with `primary`, `cleanup`, and `lastVerifiedTargetState`. It has no `version` and no further `lateAttach` member, so nesting depth is fixed at one. It is permitted only when the top primary is `service-attach-deadline` or `service-attach-cancelled`, and its primary must be a backend-local stage or `service-target-identity`.
- `cleanup` is an ordered list. Every stage is unique and follows actual execution order within its scope. A success entry has exactly `stage` and `outcome`; a failure entry has exactly `stage`, `outcome`, `reason`, and `sourceCode`. `outcome` is `succeeded`, `failed`, or `timed-out`. An operation not attempted is absent.
- The complete cleanup enum has 23 stages. The top list is limited to 23 entries when its primary is neither deadline nor cancellation. A deadline/cancellation primary limits the top list to the 13 service/outer stages whether `lateAttach` is null or present; a present `lateAttach` is limited to the 10 backend/identity-local stages. The combined maximum remains 23. Stages cannot repeat within or across the two lists.
- `lastVerifiedTargetState` is `null`, `running`, `halted`, `reset`, or `faulted`. It changes only when an existing state read returns one of those values. It describes the last successful read, not state after later actions or close.
- For compatibility, an outer `PROBE_ATTACH_FAILED` may retain top-level `stage` from the existing set: `session-create`, `session-open`, `target-resolve`, `halt-verify`, `resume`, `resume-verify`, or `cleanup-resume`. New precise stages exist only inside `attachDiagnostic`.
- The worker accepts exactly one of: legacy `{"stage": <legacy>}`, new `{"attachDiagnostic": <valid>}`, or `{"stage": <legacy>, "attachDiagnostic": <valid>}` for an `open_attach` response. It rejects extra keys, duplicates, unknown enum values, booleans in integer fields, wrong types, overlong lists, and diagnostics on another worker method. Register-error details retain their existing separate contract.
- A child `open_attach` frame is stricter than the downstream public shape: `lateAttach` must be null, primary must be backend-local, and cleanup may use only the seven backend-local stages through `worker-parent-abort` (the parent appends that final stage). Service/identity/outer stages are rejected at this boundary.
- Downstream identity wrappers may combine their existing exact identity keys with one validated `attachDiagnostic`. Monitor wrappers emit only `attachDiagnostic`. No layer forwards arbitrary sibling keys because a nested diagnostic happened to validate.
- An internal `CleanupFragment` is an immutable ordered tuple of the same validated cleanup entries, with no primary and no target-state field. Each producer is limited to its own stage subset; service/supervisor stop may emit only `service-runner-cleanup`, `service-stop-backend-close`, and `service-lease-release`. It is never serialized or published by itself. `ProbeService.stop()`/`ProbeServiceSupervisor.stop()` return it on success; a new `ProbeServiceCleanupError` (a `ProbeServiceError`) carries it on failure and chains the original first error. Public serializers use only the safe fragment and never serialize the chained exception. Hardware workflow and Monitor consume the fragment only when merging into an already-valid attach diagnostic. If no valid primary exists, their current generic cleanup failure remains unchanged.

### Primary stages

`prior-attachment-close`, `session-create`, `target-resolve-before-open`, `session-open`, `target-resolve-after-open`, `target-identity`, `halt-verify`, `resume`, `resume-verify`, `service-backend-queue`, `service-target-identity`, `service-attach-deadline`, and `service-attach-cancelled`.

Selection/enumeration failures keep their already-specific codes and do not need a new primary stage. Worker crash/deadline/malformed IPC also keep their existing contracts.

### Cleanup stages

The 10 local stages allowed inside `lateAttach` are `candidate-resume`, `candidate-resume-verify`, `session-close`, `probe-open-check-before-close`, `probe-close`, `probe-open-check-after-close`, `worker-parent-abort`, `service-identity-resume`, `service-identity-resume-verify`, and `service-identity-close`.

The remaining 13 top-level stages when `lateAttach` is present are `service-terminal-wait`, `service-worker-abort`, `service-late-resume`, `service-late-resume-verify`, `service-late-close`, `service-runner-cleanup`, `service-stop-backend-close`, `service-lease-release`, `workflow-client-close`, `workflow-service-stop`, `monitor-client-close`, `monitor-service-stop`, and `monitor-root-guard-close`.

Stage/primary compatibility is closed:

- A backend-local primary permits backend-local cleanup plus later service-stop/workflow/Monitor cleanup, but no identity or late-recovery stages.
- `service-target-identity` permits its three identity cleanup stages plus later service-stop/workflow/Monitor cleanup, but no backend-candidate or late-recovery stages.
- `service-backend-queue` permits only later service-stop/workflow/Monitor cleanup.
- `service-attach-deadline` and `service-attach-cancelled` permit only the 13 top-level service/outer stages. Their optional `lateAttach` permits backend-local cleanup for a backend-local primary or the three identity stages for a `service-target-identity` primary.

`worker-final-close` is deliberately absent: its outcome occurs after the first response and is not observable under the accepted worker protocol.

These names describe software operations. They are not hardware-cause classifications.

### Reasons and source codes

Reasons are `backend-code`, `permission-denied`, `probe-disconnected`, `probe-io`, `transport-timeout`, `transport-protocol`, `transport-fault`, `transport-error`, `target-unsupported`, `target-response`, `target-register`, `debug-command`, `debug-operation`, `backend-internal`, `timeout`, `postcondition-failed`, `identity-mismatch`, `cancelled`, and `unknown`.

`sourceCode` is `UNTYPED`, `CALLER_CANCELLED`, or one of the existing closed worker backend codes in `probe/worker.py:40-51`. A successful cleanup entry has no `reason` or `sourceCode`.

The installed offline dependency inspected for this design is pyOCD `0.45.1`. The adapter classifies by exception type only, in the following most-specific-first order:

| Exception type | Safe reason |
|---|---|
| `PermissionError` | `permission-denied` |
| pyOCD `ProbeDisconnected` | `probe-disconnected` |
| pyOCD `TransferTimeoutError` | `transport-timeout` |
| pyOCD `TransferProtocolError` | `transport-protocol` |
| pyOCD `TransferFaultError` | `transport-fault` |
| pyOCD `CoreRegisterAccessError` | `target-register` |
| pyOCD `TargetSupportError` | `target-unsupported` |
| pyOCD `InternalError` | `backend-internal` |
| pyOCD `ProbeError` | `probe-io` |
| pyOCD `TransferError` | `transport-error` |
| pyOCD `TargetError` | `target-response` |
| pyOCD `CommandError` | `debug-command` |
| pyOCD `DebugError` | `debug-operation` |
| pyOCD or built-in `TimeoutError` | `timeout` |
| pyUSB `USBTimeoutError` | `transport-timeout` |
| pyUSB `USBError` | `probe-io` |
| remaining pyOCD `Error` or any other exception | `unknown` |

Optional pyOCD/pyUSB imports are lazy so Toolkit startup behavior remains unchanged when the backend package is unavailable. No class name, message, `errno`, path, or repr matching is allowed. These reasons classify the software exception domain only; none proves a physical cause.

An existing `ProbeBackendError` uses `backend-code` plus its allowlisted code unless the failure is an explicit Toolkit postcondition or identity check, which uses `postcondition-failed` or `identity-mismatch`. An unallowlisted code is normalized to `PROBE_BACKEND_ERROR` before crossing the worker boundary.

## Primary and cleanup precedence

1. The primary is the earliest modeled failure that prevents this attach request from committing. Candidate restoration and resource close are cleanup, even when their existing outer code currently wins.
2. Outer code/message precedence remains unchanged: current `PROBE_CLOSE_FAILED`, `PROBE_ATTACH_FAILED stage=cleanup-resume`, service timeout, identity-wrapper, `HARDWARE_CLEANUP_FAILED`, and `MONITOR_CLEANUP_FAILED` selections continue to win where they win today.
3. A later cleanup failure appends an entry and never replaces `attachDiagnostic.primary`. Multiple cleanup failures remain ordered.
4. An entered service request that first exceeds its deadline has primary `service-attach-deadline`. A single valid diagnostic returned by that same attach task during recovery is copied into `lateAttach` exactly once; its primary and local cleanup are not flattened. `service-terminal-wait` records only the wait outcome and stable outer source code. A second `lateAttach`, a nested `lateAttach`, or a local stage in the top list is invalid. The helper rejects that incoming fragment and retains the already-valid diagnostic unchanged.
5. Caller cancellation is represented only when an existing cleanup error replaces it; otherwise cancellation returns no public result, as today. A late attach diagnostic follows the same one-slot rule.
6. Worker keeps send-before-final-close ordering. The parent validates the first frame against the original absolute receive deadline, then performs its already-existing `abort_owned_execution` without a second IPC wait. Successful abort appends `worker-parent-abort=succeeded`; an abort error retains its current outer `PROBE_BACKEND_ERROR` and appends a failed entry. A failure or hang before the first frame remains the current timeout/crash contract with no diagnostic.
7. Closing resources does not prove a running target. After any close, `lastVerifiedTargetState` remains historical. Callers may conservatively report an external state such as `UNKNOWN_MAY_BE_HALTED`, but the diagnostic itself makes no current-state claim.

### Exact late-deadline example

This bounded example covers: deadline first, then a backend `session-open` failure, candidate resume failure, and a later service-stop failure. Existing outer cleanup precedence yields `HARDWARE_CLEANUP_FAILED`; the deadline remains primary and the backend primary remains intact in `lateAttach`.

```json
{
  "code": "HARDWARE_CLEANUP_FAILED",
  "message": "Hardware workflow cleanup failed",
  "details": {
    "attachDiagnostic": {
      "version": 1,
      "primary": {
        "stage": "service-attach-deadline",
        "reason": "timeout",
        "sourceCode": "PROBE_TIMEOUT"
      },
      "lateAttach": {
        "primary": {
          "stage": "session-open",
          "reason": "probe-disconnected",
          "sourceCode": "UNTYPED"
        },
        "cleanup": [
          {"stage": "candidate-resume", "outcome": "failed", "reason": "probe-disconnected", "sourceCode": "UNTYPED"},
          {"stage": "session-close", "outcome": "succeeded"},
          {"stage": "probe-open-check-before-close", "outcome": "succeeded"},
          {"stage": "probe-open-check-after-close", "outcome": "succeeded"},
          {"stage": "worker-parent-abort", "outcome": "succeeded"}
        ],
        "lastVerifiedTargetState": null
      },
      "cleanup": [
        {"stage": "service-terminal-wait", "outcome": "failed", "reason": "backend-code", "sourceCode": "PROBE_ATTACH_FAILED"},
        {"stage": "service-stop-backend-close", "outcome": "failed", "reason": "unknown", "sourceCode": "UNTYPED"},
        {"stage": "workflow-service-stop", "outcome": "failed", "reason": "backend-code", "sourceCode": "PROBE_CLOSE_FAILED"}
      ],
      "lastVerifiedTargetState": null
    }
  }
}
```

Merge is exact and non-recursive: install `lateAttach` only into an empty allowed slot; append a cleanup fragment only when every stage belongs to that scope and is absent from the whole diagnostic; update top `lastVerifiedTargetState` only from a later successful existing state read. Any invalid/duplicate incoming fragment is ignored as a whole while the prior valid diagnostic and existing outer code/message remain unchanged.

The existing outer selection order is frozen explicitly:

| Boundary | Highest-to-lowest existing outer result |
|---|---|
| Backend candidate failure | close failure (`PROBE_CLOSE_FAILED`) > restoration failure (`PROBE_ATTACH_FAILED`, legacy `cleanup-resume`) > initiating typed/normalized failure |
| Service identity mismatch | close failure (`PROBE_CLOSE_FAILED`) > MODIFY restoration failure (`PROBE_BACKEND_ERROR`) > identity mismatch (`PROBE_IDENTITY_MISMATCH`) |
| Entered service timeout/cancellation | terminal-wait/late close or restoration failure (`PROBE_CLOSE_FAILED`) > the original timeout/cancellation; a terminal backend `PROBE_CLOSE_FAILED` retains that code |
| Hardware one-shot | cleanup fatal raise > cleanup failure (`HARDWARE_CLEANUP_FAILED`) > action fatal raise > cancellation > action result |
| Monitor open | cleanup fatal raise or ordinary cleanup error (`MONITOR_CLEANUP_FAILED`) > action fatal raise > cancellation > original Monitor failure |

The nested primary and cleanup list explain the sequence underneath that outer selection. They do not change it.

## Source of truth and file scope

A new bounded module, `tools/stm32-toolkit/src/stm32_toolkit/probe/attach_diagnostics.py`, is the sole owner of the closed enums, strict validation, legacy-stage promotion, diagnostic construction, cleanup append, and safe extraction/merge. It contains no pyOCD import and no hardware call. Adapter-specific exception-type classification stays in `pyocd_backend.py`.

Production changes are limited to:

- `probe/attach_diagnostics.py`: closed schema and pure helpers.
- `probe/pyocd_backend.py`: primary construction, type-only classifier, ordered cleanup collection, and legacy stage projection without new hardware calls.
- `probe/worker.py`: strict IPC admission and existing final-close ordering for valid attach failures.
- `probe/service.py`: identity and deadline/cancellation recovery preservation; attach-aware stop cleanup details without changing generic stop behavior.
- `probe/supervisor.py`: carry the internal service cleanup fragment across its existing lifecycle boundary without changing cleanup calls.
- `debug/firmware.py` and `probe/flash.py`: preserve a valid nested diagnostic across existing identity mappings.
- `hardware_workflows.py`: retain a valid action primary when existing outer cleanup precedence wins.
- `monitor_observation.py`: retain a valid diagnostic across initial binding, revalidation, and existing cleanup precedence.

`probe/backend.py`, `probe/model.py`, `probe/protocol.py`, `probe/client.py`, `stm32-monitor/runtime.py`, and `stm32-monitor/service.py` require no production change. Their existing generic containers/forwarders are verified through focused tests. Any implementation need outside this list is a design change and must return for review before editing.

## Lifecycle invariants

- Every cleanup call already present on the accepted base remains present, in the same order, and executes at most once on a given path. Diagnostic recording performs no hardware action.
- Attach state is published to backend fields only after all attach checks pass (`pyocd_backend.py:874-886`). No failure diagnostic changes that commit point.
- Flash program remains after successful attach and attachment validation (`probe/flash.py:577-591`). No failure-path change may call program or remove stale canonical evidence.
- Worker parent still owns bounded terminate/join/kill. Invalid diagnostics remain a malformed response and trigger owned-child abort.
- Service and Monitor cleanup still attempt all currently attempted resources. Fatal and cancellation semantics stay unchanged; only a valid attach diagnostic accumulates modeled outcomes.
- A successful attach/flash/Monitor result contains no attach diagnostic. Evidence formats and hashes on successful paths remain unchanged.

## Acceptance boundary

The user approved this specification and its paired plan on 2026-09-09. Slice acceptance requires focused offline tests for every distinct modeled producer branch, cleanup precedence combination, strict IPC rejection, identity wrappers, public flash zero-program, Monitor forwarding, and no-new-hardware-call sequence; it does not require a full release matrix. GPT-5.6-sol must review the complete accepted-base-to-CodeHead diff in an independent clean D-drive worktree before issuing `ACCEPTED`.

A later physical batch requires separate authorization after the implementation is accepted, packaged, deployed, and freshness-checked. It remains one ordinary flash attempt with the frozen exact selector and ELF, followed only on full program/readback/evidence success by one bounded OBSERVE. The first failure ends the batch. No retry, reconnect, extra enumeration, reset, resume, alternate probe, or alternate ELF is implied.
