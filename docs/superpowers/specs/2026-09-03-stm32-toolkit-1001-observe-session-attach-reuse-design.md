# STM32TK-1001 OBSERVE Session Attach Reuse Design

Date: 2026-09-03

Module / phase: `STM32TK-1001 / VS10-A H2`, bounded public bind/read lifecycle correction

Status: FROZEN FOR USER REVIEW

Full accepted base: `391c3dd466eafaadbbadce188e1c2b2cba4028ca`

Accepted-base tree: `c183a70a07de1cf404720b82303e2f2ff5f80420`

Active branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`

Remote branch baseline: `74ee5f4c7872af1bb612c9068af36319457e087b`; the accepted base is 67 local
commits ahead and has not been pushed.

Specification owner and final reviewer: GPT-5.6-sol primary

Implementation owner after separate specification and plan approval: exactly one GPT-5.6-luna
agent at reasoning effort `max`

Remote action: none authorized

Hardware action: none authorized by this specification; implementation and software review are
hardware-free

## 1. Trigger, evidence, and exact classification

The accepted public observation correction at product head
`daaee91894003434d2ab7c70edf0098bdbf375df` made OBSERVE use 100 kHz SWD with normal halt-connect
and preserved truthful Probe errors. Its separately authorized physical public register-read
attempt returned `PROBE_ATTACH_FAILED`, published no binding, did not enter register read, did not
retry, and did not program or reset the target. The retained evidence is:

- `C:\tmp\stm32tk-vs10a-legacy-campaign\evidence\h2-public-bind-observation-compatibility-physical-20260903-04.json`;
- SHA-256 `33b59820a6ccbf87207315676dfead20057cc2aabdc0f95709de6b0a8b97a209`.

A later separately authorized low-level diagnostic used the same selected probe, target, PyOCD
0.45.1, CPython 3.12.10, 100 kHz SWD, and normal halt-connect exactly once. Session open succeeded,
the target moved from `HALTED` to `RUNNING`, session close succeeded, and the user observed D4 still
blinking afterward. It performed no application-memory read, reset, program, or retry. The
retained evidence is:

- `C:\tmp\stm32tk-vs10a-legacy-campaign\evidence\h2-low-level-attach-state-diagnostic-20260903-05.json`;
- SHA-256 `ff5e6daaab617ca3ab630d8fbeb140a98d3a2bcd9fd80ff6361036421793fff2`.

Source reconstruction proves a lifecycle mismatch independent of which physical attach failed in
the earlier public attempt:

1. `bind_debug_firmware()` performs an initial logical `client.attach()`, firmware segment
   readback, and a final logical `client.attach()`.
2. Debug-read guards perform further logical `client.attach()` calls before and after bounded
   reads.
3. `ProbeService` currently dispatches every logical `probe.attach` request to backend
   `open_attach()`.
4. `PyOCDBackend.open_attach()` selects a probe, closes the current session, and opens a new
   physical session even when the authenticated service, exact probe selector, and canonical
   target are unchanged.

The previous design described those later calls as freshness and identity revalidations, not
retries. The production composition nevertheless turns them into repeated physical
disconnect/reconnect and halt/resume cycles. That behavior unnecessarily disturbs the target and
contradicts the intended single service/session observation boundary.

Failure classification: `PRODUCT / OBSERVE SESSION LIFECYCLE`. The evidence proves that one
physical attach is compatible for the diagnostic attempt and proves that the public composition
performs repeated physical attaches. It does **not** uniquely prove whether the earlier public
failure occurred on its first or a later physical attach. This correction therefore removes a
demonstrated lifecycle defect without claiming a uniquely proven historical failure stage.

## 2. Runnable user scenarios

### Scenario 1 - public bind/read uses one physical attachment

Given one authenticated OBSERVE Probe Service, its fixed workspace/session/lease, one exact opaque
probe selector, and one canonical target, the first logical `probe.attach` performs exactly one
backend `open_attach()`. After the backend attachment passes the existing target-identity check,
the service records that immutable attachment evidence only for its own lifetime.

The final bind revalidation and all debug-read attachment guards continue to call the existing
public `ProbeClient.attach()` method. When they request the same exact probe selector and a
canonical-equivalent target through the same service, the service returns the already validated
session-bound attachment evidence without probe enumeration, backend close, a second
`open_attach()`, another halt/resume cycle, reset, or retry.

Firmware segment verification, final project/flash provenance checks, SVD/DWARF checks, bounded
memory/register reads, and before/after logical guards remain in their accepted order. One public
register-read workflow therefore has multiple logical identity gates but exactly one physical
attachment and one backend session until normal cleanup.

### Scenario 2 - a changed revalidation identity fails before hardware

After an OBSERVE service has accepted its first attachment, a later logical attach with a different
probe selector or non-equivalent canonical target returns `PROBE_IDENTITY_MISMATCH` before another
backend call. It does not close or replace the accepted session, enumerate another probe, open a
second session, read memory, reset, or program.

The enclosing debug layer retains its accepted mapping of exact `PROBE_IDENTITY_MISMATCH` to
`DEBUG_TARGET_MISMATCH`. No binding, read result, or Monitor session is published from the failed
identity gate.

### Scenario 3 - first physical attachment failure remains truthful and terminal

If the first OBSERVE backend `open_attach()` fails, the service records no reusable attachment.
The existing stable Probe error crosses the accepted client/debug boundary, and the public
workflow stops. It performs no automatic second attach, read, reset, recovery reconnect, fallback,
or programming action.

Cancellation, timeout, cleanup-error precedence, target restoration attempts, and safe unknown
error handling remain unchanged. Reuse never turns a failed or unvalidated first attachment into
success.

### Scenario 4 - non-OBSERVE behavior is unchanged

`MODIFY` and `CONTROL` services keep their current attach dispatch and state-transition behavior.
Guarded flash, ordinary flash, explicit under-reset recovery, control authorization, and their
backend calls do not use the OBSERVE reuse state. A new service always begins with no attachment
evidence; reuse never crosses service, worker, lease, workspace, session, process, or Toolkit run
boundaries.

## 3. Selected architecture

### 3.1 Probe Service owns the session-bound OBSERVE invariant

`ProbeService` is the existing owner of the authenticated endpoint, fixed probe lease,
workspace/session identity, operation level, serialized backend access, and backend lifetime. It
therefore owns one private, in-memory OBSERVE attachment record. No client, debug module, workflow,
or PyOCD-specific layer owns a second copy.

The record contains only:

- the exact accepted public probe selector;
- the canonical accepted target;
- the immutable `ProbeAttachmentEvidence` already returned by the backend and accepted by the
  service.

It is initialized empty, populated only after the existing backend `open_attach()` and resolved
target validation both succeed, and discarded with the service lifecycle. It is never persisted,
serialized into a new schema, shared across services, or used by `MODIFY` or `CONTROL`.

### 3.2 Logical attach remains public; physical attach becomes idempotent per OBSERVE service

The existing `probe.attach` operation, `ProbeClient.attach()` signature, protocol fields, response
model, and `ProbeAttachmentEvidence` remain unchanged.

For `OperationLevel.OBSERVE`, the service handles `probe.attach` as follows:

1. If no accepted record exists, call backend `open_attach()` exactly once and run the existing
   resolved-target validation. Store the record only after success.
2. If a record exists and the request has the same exact probe selector and canonical-equivalent
   target, return the stored evidence through the existing response shape without backend
   dispatch.
3. If a record exists but either identity differs, raise stable `PROBE_IDENTITY_MISMATCH` without
   backend dispatch or session replacement.

The service's existing backend lock and fixed endpoint identity serialize these transitions. No
new lock, process, worker, backend method, protocol operation, or client API is introduced.

The reused evidence proves continuity of the already authenticated service-owned physical
session; it is not represented as a new physical discovery. Higher-level revalidation still
checks the endpoint, request identity, firmware/flash facts, source provenance, SVD/DWARF facts,
and returned evidence at every accepted logical gate. A later memory/register operation still
fails through its stable existing boundary if the owned backend session is no longer usable.

### 3.3 Cleanup and failure state

The private record is never populated before target validation. A first-attach identity mismatch
continues through the existing restoration/close path and leaves the record empty. A repeated
identity mismatch does not close the valid current session; the caller fails and normal workflow
cleanup owns final service/worker/backend shutdown.

Service shutdown clears the private record as part of lifecycle teardown. Existing backend close,
worker termination, lease release, endpoint cleanup, cancellation, and error precedence are not
reordered. No cleanup failure is hidden by a cached success.

## 4. Public contracts and state ownership

The corrected lifecycle is:

1. preflight project, SVD/DWARF, request, trusted flash, and exact service facts at their accepted
   boundaries;
2. start one OBSERVE Probe Service, one worker, and one PyOCD backend at 100 kHz normal
   halt-connect;
3. perform the first logical attach as the only physical backend `open_attach()`;
4. validate and store session-bound evidence after the target returns to running;
5. verify firmware segments through the same backend session;
6. perform final bind and read guards as logical same-session evidence revalidations;
7. execute only the authorized bounded reads;
8. close the one backend session and release the one lease through existing cleanup.

There is one source of truth for each state:

- Probe Service: whether its current OBSERVE backend session has accepted attachment evidence;
- PyOCD backend: the live physical session and target handles;
- debug binding: project, firmware, flash, endpoint, and readable-region provenance;
- workflow: requested operation and result publication;
- lease manager: exclusive probe ownership.

No CLI flag, MCP field, protocol version, public request/result schema, error inventory, project
model, runtime, package, Agent adapter, or persisted evidence schema changes.

## 5. Alternatives considered

### Remove only the final attach from `bind_debug_firmware()`

Rejected. It would remove one reconnect but leave the debug-read before/after guards performing
additional physical reconnects. It also makes a debug-specific layer redefine a service/session
lifecycle that it does not own.

### Add a new public `probe.revalidate` operation

Rejected. It would expand the protocol, client, service, worker, and compatibility surface when
the existing `probe.attach` operation can preserve its logical contract and become idempotent
inside one OBSERVE service.

### Make `PyOCDBackend.open_attach()` globally idempotent

Rejected. The backend does not own the authenticated workspace/session/lease or operation-level
lifecycle. Global idempotence could unintentionally change `MODIFY` or `CONTROL`, including their
required halt behavior and attachment replacement semantics.

### Retry after a failed physical attach

Rejected. It would add an automatic second hardware attempt, obscure the first failure, and
violate the accepted no-retry observation policy.

## 6. Bounded implementation ownership

The sole GPT-5.6-luna/max implementer may change product code only in:

- `tools/stm32-toolkit/src/stm32_toolkit/probe/service.py`.

The implementer may change tests only in:

- `tools/stm32-toolkit/tests/test_probe_service.py`.

The tracked implementation report is created separately under:

- `docs/codex/returns/STM32TK-1001-OBSERVE-SESSION-ATTACH-REUSE/implementation-report.md`.

Tests must be committed RED before product code and must directly prove:

- the first OBSERVE logical attach performs one backend `open_attach()` and returns accepted
  evidence;
- repeated same-probe/canonical-target logical attaches return byte-for-model equivalent evidence
  without another `list_probes`, `open_attach`, `close`, halt/resume, reset, read, or program event;
- a sequence matching public bind and read guards (`attach`, firmware read, `attach`, read guard,
  bounded read, `attach`) still produces exactly one backend `open_attach()`;
- a changed probe or target after the first accepted attach returns
  `PROBE_IDENTITY_MISMATCH` before backend dispatch and publishes no replacement evidence;
- a failed or mismatched first physical attach is not cached and retains existing restoration,
  cleanup, and stable error behavior;
- `MODIFY` and `CONTROL` repeat-attach behavior remains accepted-base compatible;
- service stop clears reuse state and no record crosses a new service instance;
- public protocol/client models and existing debug bind/read logical attach counts remain
  unchanged.

If TDD proves that product or test paths outside these exact lists must change, implementation
stops and reports the contract conflict. The implementer must not remove or weaken existing tests,
change fake behavior globally to hide a production gap, or change product bytes before committing
the RED proof.

## 7. Proportionate verification and evidence ownership

### Slice verification - Luna/max implementation owner

Use CPython 3.12, source/test `PYTHONPATH`, `-p no:cacheprovider`, and one fresh external run-owned
basetemp. Run only:

- `tools/stm32-toolkit/tests/test_probe_service.py`;
- `tools/stm32-toolkit/tests/test_debug_firmware.py`;
- `tools/stm32-toolkit/tests/test_debug_read.py`.

`test_probe_service.py` proves the changed service lifecycle; the two unchanged debug files prove
that logical bind/read guards and error contracts remain intact. Expand only when a focused
failure or changed dependency supplies a written risk trigger. Run `git diff --check`, inspect the
exact changed-path list, preserve minimum failure evidence, and clean only the exact run-owned
temporary output.

The implementer does not run hardware, a full suite, coverage, packaging, installation, release,
UI, another Python version, or unrelated migration checks. It commits code/tests before the
implementation report and does not accept its own diff.

### Independent review - Sol primary

Create a fresh detached clean worktree at the returned report head. Review the complete
`391c3dd466eafaadbbadce188e1c2b2cba4028ca..CODE_HEAD` product/test diff and the report-only commit
separately. Re-run the same three-file focused matrix in a fresh Sol-owned external basetemp.
Acceptance requires exactly one backend attach for repeated OBSERVE logical guards, fail-closed
identity changes, unchanged first-attach failure/cleanup behavior, unchanged MODIFY/CONTROL,
unchanged public contracts, accurate RED/GREEN lineage, and clean worktree state.

### Physical confirmation - after software acceptance only

Software acceptance does not prove that the earlier public hardware failure is fixed. After Sol
acceptance, one public read-only bind plus `GPIOE.ODR` register read may run only under a new
explicit hardware authorization. It must use the exact accepted code/runtime/project, opaque
selected probe, STM32F429ZGTx, 100 kHz SWD, and normal halt-connect. Required evidence is:

- one service, worker, backend, public workflow attempt, and physical backend attach;
- multiple logical identity guards served within that one physical session;
- no reset, erase, unlock, program, fallback, or automatic retry;
- truthful stable failure if the first attach or a later read fails;
- successful bind and exact bounded register read if they succeed;
- target returned to running, D4 observation recorded separately as user evidence, released lease,
  stopped worker/service, no residual hardware process, and an exact evidence hash.

A failed physical confirmation stops without retry.

## 8. Explicit non-goals

- No claim that the earlier public failure uniquely occurred on the second physical attach.
- No special case for `ATK 20210914`, ATK, a USB serial, STM32F429, or one board model.
- No VS Code, Cortex-Debug, Keil, OpenOCD, or project-local PyOCD dependency.
- No second runtime, Probe Service, worker, backend, provider, controller, or MCP registration.
- No new public attach/revalidate operation, protocol field, schema, frequency option, or project
  migration.
- No change to PyOCD connection options, 100 kHz OBSERVE policy, ordinary flash, guarded flash,
  explicit under-reset recovery, or control authorization.
- No retry, reconnect after failure, fallback, frequency probing, transport negotiation, reset,
  unlock, erase, programming, arbitrary write, or target-family expansion.
- No removal of logical final bind or debug-read identity/provenance guards.
- No full suite, release matrix, package/install, CI, collaboration automation, or hardware action
  during software implementation/review.
- No push, PR mutation, merge, tag, release, close, or remote branch deletion.

## 9. Acceptance and stop boundary

This correction is accepted only when all four scenarios have direct tests, the focused CPython
3.12 matrix passes, the complete accepted-base-to-code-head diff has no unresolved product,
safety, compatibility, test, or scope defect, the report accurately records the accepted base and
RED/GREEN lineage, disposable run-owned artifacts are cleaned or classified, and implementation
and review worktrees are clean with remote state stated.

Software acceptance does not authorize hardware or remote publication. After acceptance, stop and
request one explicit authorization for the single read-only physical confirmation. Do not enter
another VS10 slice, VS10-B, release, or any remote action automatically.
