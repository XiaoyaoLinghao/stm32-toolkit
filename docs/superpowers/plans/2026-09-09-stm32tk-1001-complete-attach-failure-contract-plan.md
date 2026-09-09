# STM32TK-1001 Complete Attach Failure Contract Implementation Plan

Status: **approved by the user on 2026-09-09; implementation authorized and starting**

Paired specification: `docs/superpowers/specs/2026-09-09-stm32tk-1001-complete-attach-failure-contract-design.md`

Accepted base: `776c052d43544ba599f16dde74f1264fd69cdb10`

Specification, integration, complete-diff review, and acceptance owner: GPT-5.6-sol. Product implementation and implementation-test owner: one GPT-5.6-luna/max agent. Active branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`. The user authorized local product edits in the frozen scope, focused offline tests, local commits, independent review, and local fast-forward integration on 2026-09-09. Packaging, deployment, hardware, runtime replacement, and remote actions remain outside this authorization.

## Delivery boundary

The slice adds one closed attach diagnostic, preserves it through the existing public chain, and leaves outer code/message and hardware behavior compatible. Product scope is exactly:

- add `tools/stm32-toolkit/src/stm32_toolkit/probe/attach_diagnostics.py`;
- edit `probe/pyocd_backend.py`, `probe/worker.py`, `probe/service.py`, `probe/supervisor.py`, `debug/firmware.py`, `probe/flash.py`, `hardware_workflows.py`, and `monitor_observation.py`;
- edit only the focused existing tests named below.

No product edit is expected in backend/model/protocol/client or STM32 Monitor runtime/service. A need outside the listed product files stops implementation and returns to GPT-5.6-sol for a specification revision.

All worktrees, virtual environments, caches, basetemp roots, and test output are created under a new run-owned `D:\codex-tmp` root. The implementer must start from a clean detached worktree at the accepted base. It must not touch the installed campaign runtime, old canonical evidence, consumed hardware markers, old C-drive temp paths, master, or any remote.

## Task 1: Lock the pure schema and RED privacy tests

Owner: GPT-5.6-luna/max.

Files:

- create `probe/attach_diagnostics.py`;
- edit `tests/test_probe_worker.py` and `tests/test_pyocd_backend.py` first for RED;
- no production edit before the focused tests demonstrate the absent contract.

Add pure helpers for exact validation, legacy-stage promotion, primary construction, ordered cleanup append, last-verified-state update, safe extraction, and merge. Constants in this module are the only enum authority. The module imports no pyOCD, USB, worker, service, client, or hardware code.

RED cases must show that the accepted base cannot:

- retain an initiating `session-open` failure when candidate resume and close both fail;
- distinguish pre/post-open target resolution and target identity inside the nested primary while retaining the legacy stage projection;
- retain all existing close attempts in execution order;
- represent a deadline primary and one later backend/service-identity diagnostic without flattening either primary;
- accept a valid versioned diagnostic through worker IPC while rejecting extra keys, recursive or second `lateAttach`, wrong stage scope, unknown enum values, wrong scalar types, duplicate cleanup stages, overlong cleanup, and attach diagnostics on a non-attach worker method;
- retain the current first-error-frame timing when the implicit worker final close fails or blocks.

Then implement only the pure schema module needed by subsequent tasks. Do not add serialization, logging, or hardware APIs.

## Task 2: Produce complete backend diagnostics without new hardware calls

Owner: the same GPT-5.6-luna/max implementer.

Files: `probe/pyocd_backend.py`, `tests/test_pyocd_backend.py`.

Refactor `open_attach`, `_restore_candidate_and_close`, `_close_external`, and `close` so each branch in the specification table constructs one primary and appends outcomes from calls that already exist. Preserve selection failures without a diagnostic. Preserve the exact attach-state commit at lines 874-886 and the current outer error precedence.

The exception classifier must use lazy imports and `isinstance` against the frozen built-in, pyOCD, and pyUSB exception types. It must not inspect exception text, repr, class-name strings, paths, errno text, or device identifiers. Explicit Toolkit identity and postcondition checks use their frozen reasons; all unmatched exceptions use `unknown`.

Focused GREEN evidence:

- one parameterized producer test covers every primary stage and typed/untyped normalization;
- one parameterized cleanup test covers no target, all cleanup success, resume failure, state-verification failure, session-close failure, probe-state read failure, probe-close failure, final-open check failure, and multiple failure retention;
- one call-trace test proves no new enumeration/session/open/state/resume/close call and no order change on success and representative failure paths;
- existing success and stage-compatibility nodes remain green.

## Task 3: Preserve the contract across worker and service lifecycle

Owner: the same GPT-5.6-luna/max implementer.

Files: `probe/worker.py`, `probe/service.py`, `probe/supervisor.py`, `tests/test_probe_worker.py`, `tests/test_probe_service.py`, `tests/test_probe_supervisor.py`.

Worker:

- replace its private attach-stage validator with the shared strict helper;
- keep sending a valid/promotable `open_attach` failure before the existing implicit backend close; do not add a second frame, acknowledgement wait, or deadline extension;
- after the parent receives and validates that first frame, append the outcome of its already-existing immediate `abort_owned_execution`; if abort fails, preserve the current `PROBE_BACKEND_ERROR` outer result and the received primary;
- leave a failure/hang before the first frame, crash, receive deadline, malformed IPC, register details, and all non-attach operations on the current contract. Never claim the unobservable child final-close outcome.

Service:

- build a primary for service identity mismatch and retain existing MODIFY resume/state and close outcomes;
- on pre-lock timeout, retain `PROBE_TIMEOUT` and record no backend operation; cancellation still propagates;
- on an entered timeout/cancellation, preserve the deadline/cancellation primary and record terminal wait, worker abort, late resume/state, and close outcomes that actually occur;
- store at most one valid diagnostic returned by that same late attach task in the non-recursive `lateAttach` slot; never flatten its primary or local cleanup, and retain current outer code/message precedence;
- let service stop collect runner/backend/lease outcomes into the internal closed `CleanupFragment`; return it on success or carry it in a safe `ProbeServiceCleanupError` chained from the first error;
- let supervisor stop carry that fragment across its existing service/direct-backend lifecycle boundary, while retaining the same cleanup calls, order, reference clearing, cancellation ownership, and public workflow behavior;
- merge the fragment only into an already-valid attach diagnostic. With no valid primary, callers keep their existing generic cleanup result. Neither stop layer invents a primary.

Focused tests use the existing fake backend and absolute-deadline seams. They cover service identity plus resume/close combinations; deadline followed by a late backend or service-identity diagnostic; terminal-wait timeout with worker abort success/failure; late attach success for OBSERVE and MODIFY; caller cancellation; missing abort test seams; and supervisor propagation of successful/multi-failure cleanup fragments. A worker fake whose final close blocks proves the first error frame still wins and the existing parent abort bounds cleanup without a second wait. Existing worker timeout/crash/malformed-response and service/supervisor cancellation/reap tests run as regression nodes and must keep their old public shapes.

## Task 4: Preserve valid diagnostics through public wrappers

Owner: the same GPT-5.6-luna/max implementer.

Files:

- `debug/firmware.py`, `tests/test_debug_firmware.py`;
- `probe/flash.py`, `tests/test_flash.py`;
- `hardware_workflows.py`, `tests/test_hardware_workflows.py`;
- `monitor_observation.py`, `tests/test_monitor_observation.py`;
- tests only in `tools/stm32-monitor/tests/test_runtime.py` and `test_service.py`.

Rules:

- Debug and flash identity mappings retain their existing outer code/message and fixed identity fields, adding only a validated nested diagnostic.
- Generic flash attach errors keep current forwarding. Every attach failure asserts zero calls to program, readback, stale-result removal, and canonical evidence write.
- Hardware workflow keeps `HARDWARE_CLEANUP_FAILED` precedence; only a valid action diagnostic receives ordered client/service cleanup entries. Other cleanup failures retain current empty-details behavior.
- Monitor initial open and revalidation keep their existing Monitor code/messages, retain only the nested diagnostic, and append client/service/root-guard cleanup outcomes. Other provenance details remain omitted.
- STM32 Monitor runtime/service production files remain unchanged; focused tests prove they forward the Toolkit result unchanged.

Use one small parameterized wrapper test per distinct transformation, not a copy of the backend matrix at every layer. Add one end-to-end fake production seam from `flash_firmware` through worker/service/client/workflow that proves a valid diagnostic reaches the public failure and programming remains zero. Add one Monitor production-factory seam proving the same nested diagnostic reaches the public Monitor response.

## Task 5: Implementation evidence and commit

Owner: the GPT-5.6-luna/max implementer.

Run only the new/focused nodes and the directly affected existing nodes. Do not run the full repository or release matrix. Use `python -m pytest -q -o addopts=''` with explicit node/file arguments, a D-drive run-owned `--basetemp`, and a D-drive run-owned cache directory. The implementation return must record:

- exact accepted base and CodeHead;
- RED command and failure attributable to the missing contract;
- GREEN commands and node counts;
- hardware-call trace evidence showing no added calls;
- `git diff --check`, tracked/untracked status, and the complete changed-file list;
- confirmation that no campaign runtime, evidence, hardware, or remote was touched.

After preserving the minimum useful failure evidence, remove only exact run-owned disposable output. A cleanup policy rejection ends cleanup; do not retry with a variant. Commit product and tests locally on the one slice branch or detached implementation branch as directed by GPT-5.6-sol. The implementer does not approve its own diff.

## Task 6: Independent review and proportionate verification

Owner: GPT-5.6-sol.

Create a separate clean D-drive worktree at CodeHead. Review the complete `776c052d43544ba599f16dde74f1264fd69cdb10..CodeHead` diff, not the report summary. Verify:

- every branch-table row is either implemented or explicitly unchanged as specified;
- enum and schema authority exists only in `attach_diagnostics.py`;
- public code/message precedence and legacy top-level stage compatibility remain exact;
- no raw exception data or arbitrary sibling details can cross worker or wrapper boundaries;
- worker crash/deadline/cancel/malformed IPC remain on the prior contract;
- worker sends its first error frame before final close and adds no second wait or deadline extension;
- cleanup retains all modeled outcomes without overwriting primary;
- deadline/cancellation primary and a single late attach primary remain distinct in the bounded non-recursive shape;
- no new hardware call, reordered call, retry, or state read exists;
- flash still reaches program only after successful attach and identity validation;
- success evidence bytes and formats are unchanged.

Run the smallest focused subset needed to independently verify the shared schema, backend call trace, worker privacy, service deadline/cleanup precedence, public flash zero-program, and Monitor forwarding. Reuse the implementer's unchanged-behavior evidence when the final CodeHead differs only in non-behavioral test naming; do not restart a full cycle for report formatting.

Verdict is `ACCEPTED`, `REVISION_REQUIRED`, or `REWRITE_REQUIRED`. Correctable findings return to the same Luna owner. After two non-converging implementation/review rounds, stop patching and return to design. The final tracked review report records accepted base and reviewed CodeHead but not its own report commit SHA.

## Later deployment and physical boundary

Packaging, Bootstrap replacement of the D campaign runtime, and hardware remain separate later authorizations. Before any new physical action, the accepted CodeHead must be packaged into a new candidate and pass bundle verification, Bootstrap/CHECK/doctor/isolated import/hash, project freshness, exact ELF/build/selector, canonical-history preservation, no-process/no-lease, and a fresh single-use marker.

The recommended physical batch adds no independent enumeration or diagnostic attach. It consists of one ordinary flash with the frozen selector, `recovery_under_reset=false`, normal program reset, and full readback. The first failure is terminal. Only a fully pinned new canonical result permits one five-second OBSERVE for typed `testtime`, `GPIOE.ODR/PE4`, and correlation, with normal attach auto-resume and normal release/stop cleanup. It does not authorize retry, reconnect, extra reset/resume, alternate ELF/probe, or modification of old evidence.
