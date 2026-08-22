# VS04-A Production Composition Amendment

## Status

This amendment closes the production-composition ambiguity found while reviewing rejected candidate
`c0a5d4e262c2ebc42ed8df2acc31f72f693af5d8`. That candidate is not an accepted base and must not be
integrated. The product accepted base remains `5d6e06845a2c1d991181c5ff84a9194dfcc49c8c`.

This document supplements the VS-04 design. If either document differs, this amendment controls
VS04-A. Fake seams may replace narrow constructors in tests, but may never supply an already-derived
authorization binding or replace the default production composition.

## 1. Derived preparation facts

The public prepare request contains only project/data/session roots, transient raw `probeId`, and an
optional closed `caseIds` subset. It does not accept inventory, build, ELF, snapshot, target,
transport, timeout, or support-profile facts.

Preparation performs this exact read-only composition:

1. `load_project_model()` loads Project v3 and requires configured `testing.target`, PyOCD debug
   backend, and target.
2. A narrow public read-only projection in `probe.flash` delegates to `_load_fresh_firmware()` and
   returns the already-validated model, portable ELF path, ELF SHA-256, build ID, input snapshot,
   Git identity, and target device. It does not copy or weaken that validation.
3. Project v3 derives the transport kind/options, timeout, target executable, writable-RAM support
   profile, logical project, and target profile. `memory-mailbox` maps to `mailbox`; other frozen
   Target kinds keep their names.
4. A real `ProbeServiceSupervisor` at OBSERVE level, real `ProbeClient`, and the service transport
   bridge attach non-halting. `ProbeClient.target_identity()` supplies board, MCU, target ID, and
   probe serial hash. The hash must equal SHA-256 of the transient raw selector; the raw selector is
   never written durably.
5. Target discovery validates target/build/ELF/input-snapshot identity and derives inventory digest
   and case IDs from its single inventory frame. Discovery must no longer require an expected
   inventory digest before it can discover that digest.
6. Requested case IDs are empty-for-all or an exact unique subset of discovered cases.
7. Only after all checks pass does `TargetTestRunner.prepare()` create the canonical authorization
   record and action digest.

OBSERVE preparation performs no flash, reset, halt, resume, Target test, or TestRun publication.

## 2. Exact execute composition

Fresh-process execution accepts only roots, the same transient raw probe selector, and
`authorizedActionDigest`.

1. Load and validate the persisted prepared record by digest; hash-check the raw selector.
2. Atomically consume the digest and return an immutable consumed intent. No caller-reconstructed
   `PreparedTargetRun` is accepted.
3. Before any target write, reload Project v3 and the `probe.flash` fresh-firmware facts and compare
   workspace, project, session, input snapshot, build, ELF bytes/path, target, transport, timeout,
   and requested cases with the consumed intent.
4. Start exactly one `ProbeServiceSupervisor` at MODIFY level and exactly one `ProbeClient`.
5. Re-read target identity and rediscover inventory/cases through that client before flash.
6. A bound flash adapter calls `flash_firmware(FlashRequest, client)` using the same client. Calling
   `flash_workflow`, creating another supervisor, or acquiring another lease is forbidden.
7. Re-read target identity, execute the selected transport through the same Probe-v2 service
   client, collect Evidence, and publish the terminal physical TestRun.
8. The runner owns its transport only. The application owner closes the client once and stops the
   supervisor once on success, refusal, timeout, cancellation, and failure.

The existing runner default remains probe-owning for compatibility. Production VS04-A explicitly
sets non-owning probe behavior; no skip-cleanup boolean based on whether the runner started is valid.

## 3. Required narrow Probe contracts

The following existing files are in scope because the production path cannot be correct without
them:

- `probe/flash.py`: expose an immutable read-only fresh-firmware projection that delegates to
  `_load_fresh_firmware()`.
- `probe/client.py`, `probe/service.py`, and `probe/pyocd_backend.py`: preserve the actual closed
  Target transport identity from backend handle through service and client.
- `probe/pyocd_backend.py`: validate Monitor `log_transport` only when configured; Target transport
  admission remains independently governed by the explicit open request and project profile.
- The Probe Service, which knows `project_root`, safely resolves a portable semihosting ELF path for
  the backend and normalizes returned identity back to portable form. Absolute paths never enter an
  authorization record or TestRun.

Application code uses one `ProbeClientTargetTransport` adapter over
`target_transport_open/read/close`; it does not instantiate PyOCD or four provider implementations.

## 4. Physical provenance and publication

Provenance is explicit data, never inferred from the flash-adapter class. The consumed intent carries
a validated immutable physical provenance object into the runner.

The runner publishes operation `target-test-physical`, not an unlabeled `target-test-run` orphan.
The envelope and authoritative root contain only closed physical fields:

- execution source `physical`, physical flag `true`;
- current origin/import workspace and session;
- target ID;
- `probe_id` equal to the 64-hex probe serial hash;
- flash-session ID, lease ID, action digest, intent digest, inventory digest, and transport-config
  digest.

No durable byte or public result may contain the raw probe selector or absolute ELF path. Future
Monitor observation receives the raw selector transiently and binds to this TestRun by comparing
the independently observed hash.

## 5. Public adapters

- `test target prepare --probe-id ... [--case-id ...]`
- `test target execute --probe-id ... --authorized-action-digest ...`
- MCP tools with the same two operation-specific inputs plus runtime-bound roots.

`inventoryDigest` and all other identity fields are forbidden. CLI uses an operation-specific async
dispatch; it does not make general CLI dispatch awaitable. MCP checks client roots once and awaits
one workflow once. Both return the workflow result unchanged and sanitize failures.

## 6. Minimum acceptance evidence

Tests use a real Project v3, real build Evidence, real supervisor/service/client/lease machinery,
and a fake backend at the existing backend seam.

- Prepare discovers inventory, creates one record, performs zero MODIFY/control/flash, and leaves no
  TestRun root.
- A new process executes by digest through one acquire/start/client/flash/transport/close/stop and
  fresh `test.show` reloads the physical root.
- All four transports traverse the service identity contract.
- Reuse, busy owner, cancellation, timeout, build/ELF/snapshot/inventory/probe/target drift fail at
  their defined boundary without stealing a lease or producing an unauthorized root.
- Scanning authorization, Evidence, result, and stdout bytes finds neither the raw selector nor an
  absolute ELF path.
