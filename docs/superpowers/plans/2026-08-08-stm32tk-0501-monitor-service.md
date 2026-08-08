# STM32TK-0501 Monitor Service Implementation Plan

> **Execution:** Use `subagent-driven-development`, `test-driven-development`, and
> `verification-before-completion`.  Every task starts with a committed failing
> test, ends with focused GREEN evidence, and remains on the branch and PR named
> below.  Parallel workers may edit only their assigned paths.

**Module:** `STM32TK-0501-MONITOR-SERVICE`

**Phase:** Codex implementation after the accepted 0.4.0 release

**Repository:** `https://github.com/XiaoyaoLinghao/stm32-toolkit.git`

**Accepted base:** `913600f471d8fb0fb5345bdf668ca39ec1faf4d8`

**Branch:** `codex/STM32TK-0501-MONITOR-SERVICE`

**Specification owner / implementer / reviewer:** Codex / Codex subagents / an
independent Codex review subagent

**Remote authority:** Codex may push this branch, create and update one Draft PR
to `master`, mark it ready, and merge after acceptance.  Do not delete the remote
branch.

## Goal

Replace the unsafe legacy `stm32-monitor` implementation with a project-isolated,
authenticated, bounded monitor service.  The service must keep one exact
`OBSERVE` Probe Service lease, resolve variables from the current DWARF catalog
and registers from the exact project SVD, persist user-created groups and bounded
history outside the source tree, and stream typed samples without blocking the
sampler on slow clients.

This module delivers the Python service and protocol only.  The TypeScript UI,
browser launch flow, bundled assets, plugin/runtime release changes, and final
0.5.0 version promotion belong to `STM32TK-0502-MONITOR-UI-RELEASE`.

## Corrections to the older phase plan

The following older assumptions are rejected and must not survive in code,
tests, documentation, or compatibility shims:

- `stm32-monitor` never imports or opens PyOCD, reads a probe directly, or kills
  any PyOCD process.  It uses only Toolkit Probe Service and typed-debug APIs.
- Monitoring uses one exclusive `OBSERVE` lease.  There is no shared read lease,
  no lease stealing, and no automatic flash/debug pre-emption.  Same-probe work
  receives a stable busy result; different probes may run concurrently.
- The service binds only `127.0.0.1` on port `0`.  It never binds `localhost`, a
  fixed port, wildcard interfaces, or a caller-selected nonzero port.
- The caller cannot supply workspace ID, target, SVD path, ELF path, address,
  operation level, backend, or process command.  These come from the canonical
  Schema-v2 project and current firmware evidence.
- Legacy `.stm32-monitor.yaml`, `watch-groups.json`, project JSON, browser
  `localStorage`, and named presets are never auto-imported.  A fresh workspace
  has exactly zero group rows.  A bounded legacy document may be processed only
  by an explicit authorized import request.
- SQLite is the sole authority for group definitions and history.  There is no
  second JSON authority and no unbounded in-memory or thread-per-watch history.
- The existing `aiohttp` runtime is reused.  Do not add FastAPI, Uvicorn,
  Pydantic, PyYAML, CMSIS-SVD, or a second PyOCD dependency.

## Non-negotiable security and evidence contract

- All project and data roots are canonical and reparse-safe.  The data root must
  remain outside the project root before any directory, database, listener, or
  backend is created.  Runtime state is derived through `WorkspacePaths`.
- `MONITOR_PROTOCOL_VERSION` is exactly `stm32-toolkit-monitor/1`.  Every REST,
  WebSocket, runtime, export, and sample envelope includes the protocol version
  and Toolkit/Monitor versions.
- Each service start creates a cryptographically random 32-byte token.  Token
  values are `repr=False`, never logged, never placed in a query string, and
  never persisted.  The runtime record stores only its SHA-256 digest.  Bearer
  authentication and a fragment-to-HttpOnly-cookie bootstrap are the only web
  authentication paths.
- Enforce loopback peer, exact Host, allowed Origin, bounded headers/body/message,
  and no DNS-rebinding ambiguity.  REST and WebSocket limits are 1 MiB.  Tokens
  are compared in constant time.
- A monitor observation is bound to canonical project root, workspace, logical
  project, session, exact probe, target, resolved physical target, build ID, ELF
  SHA/size, input snapshot, Git HEAD/dirty state, flash session, lease, DWARF
  provenance, and exact SVD provenance.  Any change pauses the run as
  `PAUSED_BLOCKED`; old and new firmware samples are never mixed.
- Continuous register sampling calls a dedicated typed API that invokes
  `SvdRegister.authorize_read(..., sampling=True)`.  Read-side-effect and
  write-only registers are always rejected; no acknowledgement can override
  this for sampling.
- Hardware and storage errors expose stable codes and bounded public details,
  never raw exceptions, tokens, absolute paths, SQLite messages, USB details, or
  command lines.

## Stable public interfaces

### Toolkit observation bridge

Create the public, cancellation-safe bridge in
`stm32_toolkit.monitor_observation`:

```python
@dataclass(frozen=True)
class MonitorObservationRequest:
    project_root: Path
    data_root: Path
    session_id: str
    probe_id: str
    expected_build_id: str
    expected_elf_sha256: str

class MonitorObservationSession:
    binding: DebugFirmwareBinding
    catalog: DwarfCatalog
    svd: SvdSelection | None
    endpoint: ProbeEndpoint
    client: ProbeClient

    async def read_variables(self, expressions: tuple[str, ...]) -> OperationResult: ...
    async def sample_registers(self, paths: tuple[str, ...]) -> OperationResult: ...
    async def revalidate(self) -> OperationResult: ...
    async def close(self) -> None: ...

async def open_monitor_observation(
    request: MonitorObservationRequest,
    *,
    _seams: MonitorObservationSeams = MonitorObservationSeams(),
) -> OperationResult[MonitorObservationSession]: ...
```

It derives a per-probe hashed session root, starts one exact `OBSERVE`
supervisor, binds the current firmware, loads the real DWARF catalog and optional
exact SVD, and keeps the lease until `close()`.  `close()` uses owned-task
completion: repeated cancellation cannot release lifecycle ownership early, and
cleanup failure has priority over caller cancellation.

Add `RegisterSampleRequest` and `sample_registers()` to the typed-debug sampling
module.  It is a bounded single-sample primitive for the Monitor scheduler, not a
second persistence loop.

### Monitor models and storage

`MonitorConfig` contains only canonical project root, external data root, and
safe session ID.  `ProbeConnectRequest` adds exact probe/build/ELF pins.
`WatchItem` is a discriminated union of one DWARF expression or one SVD register
path; neither form accepts an address.  `WatchGroup` has UUID, NFC name,
description, interval, immutable tuple items, revision, created/updated UTC.

`GroupStore(paths)` and `HistoryStore(paths)` are workspace-bound; no public
method accepts workspace ID or an arbitrary database path.  Mutations and import
require `authorized is True` and an expected revision where applicable.

SQLite file:

```
${dataRoot}/projects/<workspaceId>/monitor/monitor.sqlite3
```

Use stdlib `sqlite3`, WAL, `synchronous=FULL`, foreign keys, 250 ms busy timeout,
bounded WAL/checkpoint behavior, `application_id`, and `user_version=1`.  One
dedicated bounded writer owns mutations; reads use short read-only connections.
Migrations run in one exclusive transaction and reject future, corrupt,
redirected, replaced, oversized, or wrong-workspace stores.  Missing storage is
read as an empty workspace and is created only by an authorized mutation or a
connected sampling run.

Limits: 128 groups, 256 items per group, 4,096 items total, 512-character
expression/register paths, 128-character NFC names unique by NFC+casefold,
1,024-character descriptions, 1 MiB import, 256 active de-duplicated watches,
10,000 returned values or 4 MiB per history page.

History binds immutable watch definitions and every batch to workspace, logical
project, session, probe, target, build ID, ELF SHA, input snapshot, Git evidence,
flash session, lease, group ID/revision, run ID, sequence, scheduled/captured UTC,
monotonic latency, actual rate, and all drop counters.  Use integer Unix
nanoseconds and half-open ranges.  Group rename/delete never deletes history.

Retention is fixed at 7 days and a 256 MiB logical workspace budget, with a 512
MiB database-plus-WAL hard stop.  Cleanup is chunked to 100 batches per pass and
must not block the sampler for 100 ms.  Export is server-owned under
`monitor/exports/<sessionId>/<exportId>/`, capped at 1,000,000 values and 64 MiB,
written atomically with a SHA-256 manifest; CSV cells beginning with formula
characters are neutralized.

### Sampler

One `MonitorSampler` owns the observation session and a single monotonic
producer.  It resolves the group revision before starting and deduplicates reads
within a tick.  Accepted intervals are 100..5,000 ms and are rejected, never
clamped.  Missed slots do not burst.

Each subscriber queue holds eight batches and drops the oldest.  The history
writer queue holds 128 batches or 8 MiB.  Subscriber, history, and deadline drops
are counted separately and appear in the next batch.  One item error remains a
typed item error; lost endpoint/lease/probe/firmware/DWARF/SVD changes the whole
run to `PAUSED_BLOCKED` without spinning or auto-reacquiring.  Explicit reconnect
obtains a new lease and binding and starts a new run ID/firmware epoch.

### Loopback service

`MonitorRuntime.start(MonitorConfig) -> MonitorEndpoint` starts group/history APIs
without requiring hardware.  An authenticated explicit connect operation takes
`ProbeConnectRequest`.  Expose only:

- `GET /api/v1/status`
- `POST /api/v1/auth/bootstrap`
- `GET|POST /api/v1/groups`
- `PATCH|DELETE /api/v1/groups/{groupId}`
- `POST /api/v1/groups/import`
- `POST /api/v1/probe/connect|release|reconnect`
- `POST /api/v1/sampling/start|pause|resume|stop`
- `GET /api/v1/history`
- `POST /api/v1/exports`
- `GET /api/v1/exports/{exportId}`
- `GET /api/v1/live` as authenticated WebSocket

Runtime records are atomically written under the per-probe or unbound session
directory and contain host, dynamic port, PID, start UTC, protocol, workspace,
session, and token digest only.  They never contain the plaintext token.  Stop
rejects new work, closes listeners/clients, awaits sampler and writer tasks,
closes the observation session once, releases locks, and removes runtime records.

Stable monitor codes include `MONITOR_REQUEST_INVALID`,
`MONITOR_AUTH_REQUIRED`, `MONITOR_WORKSPACE_MISMATCH`, `MONITOR_PROBE_BUSY`,
`MONITOR_FIRMWARE_CHANGED`, `MONITOR_PROVENANCE_CHANGED`,
`MONITOR_STORAGE_INVALID`, `MONITOR_STORAGE_BUSY`, `MONITOR_STORAGE_CORRUPT`,
`MONITOR_STORAGE_VERSION_UNSUPPORTED`, `MONITOR_STORAGE_FULL`,
`MONITOR_GROUP_NOT_FOUND`, `MONITOR_GROUP_CONFLICT`,
`MONITOR_GROUP_LIMIT_EXCEEDED`, `MONITOR_IMPORT_INVALID`,
`MONITOR_IMPORT_CONFLICT`, `MONITOR_HISTORY_QUERY_INVALID`,
`MONITOR_HISTORY_LIMIT_EXCEEDED`, `MONITOR_EXPORT_TOO_LARGE`,
`MONITOR_EXPORT_QUOTA_EXCEEDED`, `MONITOR_EXPORT_FAILED`, and
`MONITOR_RETENTION_FAILED`.

## Task 1: Secure typed observation bridge

**Owner paths:**

- Create `tools/stm32-toolkit/src/stm32_toolkit/monitor_observation.py`
- Modify `tools/stm32-toolkit/src/stm32_toolkit/debug/sampling.py`
- Modify `tools/stm32-toolkit/src/stm32_toolkit/debug/__init__.py`
- Modify `tools/stm32-toolkit/src/stm32_toolkit/__init__.py`
- Create `tools/stm32-toolkit/tests/test_monitor_observation.py`
- Modify `tools/stm32-toolkit/tests/test_sampling.py`

- [ ] Commit RED tests for exact OBSERVE, no raw overrides, real binding/catalog/SVD,
  side-effect register rejection, same-probe busy, different-probe isolation,
  firmware/provenance changes, cleanup failure, and repeated cancellation.
- [ ] Implement the public bridge and dedicated safe register sample primitive.
- [ ] Run Task 1 focused tests plus Probe Service, typed-debug, hardware workflow,
  flash, and handoff adjacent regression tests.
- [ ] Require branch coverage at least 90% for every new/modified product module.
- [ ] Commit product and tests without modifying monitor package files.

## Task 2: Immutable models, SQLite groups/history, retention, and export

**Owner paths:**

- Modify `tools/stm32-monitor/pyproject.toml`
- Modify `tools/stm32-monitor/src/stm32_monitor/__init__.py`
- Create `tools/stm32-monitor/src/stm32_monitor/models.py`
- Create `tools/stm32-monitor/src/stm32_monitor/protocol.py`
- Create `tools/stm32-monitor/src/stm32_monitor/storage.py`
- Create `tools/stm32-monitor/src/stm32_monitor/groups.py`
- Create `tools/stm32-monitor/src/stm32_monitor/history.py`
- Create `tools/stm32-monitor/src/stm32_monitor/exports.py`
- Create `tools/stm32-monitor/tests/test_models.py`
- Create `tools/stm32-monitor/tests/test_groups.py`
- Create `tools/stm32-monitor/tests/test_history.py`
- Create `tools/stm32-monitor/tests/test_exports.py`

- [ ] Commit RED tests for zero default groups, workspace binding, deep immutable
  JSON-safe models, CAS revisions, every limit, explicit authorization/import,
  corruption/version/redirect/descriptor-swap handling, retention, paging, export
  quotas, and CSV formula protection.
- [ ] Implement the schema and bounded dedicated writer without exposing database
  paths or accepting workspace IDs.
- [ ] Run focused tests under simultaneous writers/readers and cancellation.
- [ ] Require branch coverage at least 90% for every new product module.
- [ ] Commit product and tests without modifying Toolkit bridge or service files.

## Task 3: Single-producer sampler and Probe lifecycle integration

**Owner paths:**

- Create `tools/stm32-monitor/src/stm32_monitor/probe_session.py`
- Create `tools/stm32-monitor/src/stm32_monitor/sampler.py`
- Create `tools/stm32-monitor/tests/test_probe_session.py`
- Create `tools/stm32-monitor/tests/test_sampler.py`

- [ ] Commit RED tests for one exact lease, deduplicated reads, typed item errors,
  monotonic scheduling, no burst, all queue limits/drop counters, stale group
  revision, provenance loss, explicit release/reconnect, and cancellation-safe
  shutdown.
- [ ] Implement only against the public Task 1 bridge and Task 2 stores.
- [ ] Prove a slow subscriber and slow SQLite writer cannot block sampling.
- [ ] Require branch coverage at least 90% for every new product module.
- [ ] Commit product and tests without modifying Task 1 or Task 2 paths.

## Task 4: Authenticated aiohttp runtime, REST/WebSocket protocol, and CLI

**Owner paths:**

- Create `tools/stm32-monitor/src/stm32_monitor/auth.py`
- Create `tools/stm32-monitor/src/stm32_monitor/service.py`
- Create `tools/stm32-monitor/src/stm32_monitor/runtime.py`
- Replace `tools/stm32-monitor/src/stm32_monitor/cli.py`
- Replace `tools/stm32-monitor/src/stm32_monitor/__main__.py`
- Create `tools/stm32-monitor/tests/test_auth.py`
- Create `tools/stm32-monitor/tests/test_service.py`
- Create `tools/stm32-monitor/tests/test_runtime.py`
- Create `tools/stm32-monitor/tests/test_cli.py`

- [ ] Commit RED tests for loopback/dynamic-port binding, token secrecy, Bearer and
  cookie bootstrap, Host/Origin/peer/DNS-rebinding checks, exact API grammar,
  body/header/message bounds, cross-workspace rejection, WebSocket backpressure,
  runtime locks, and repeated-cancellation shutdown.
- [ ] Implement `stm32-monitor serve --project --data-root --session-id --json`.
  Do not implement `--open-browser`; that belongs to 0502.
- [ ] Test two projects and two probes concurrently, same-probe busy behavior,
  listener/record cleanup, no project writes, and no plaintext token in logs,
  exceptions, reprs, records, or test artifacts.
- [ ] Require branch coverage at least 90% for every new product module.
- [ ] Commit product and tests without modifying Tasks 1-3 paths.

## Task 5: Remove legacy runtime and integrate the complete service

**Owner paths:**

- Delete `tools/stm32-monitor/src/stm32_monitor/config.py`
- Delete `tools/stm32-monitor/src/stm32_monitor/elf_parser.py`
- Delete `tools/stm32-monitor/src/stm32_monitor/svd_parser.py`
- Delete `tools/stm32-monitor/src/stm32_monitor/pyocd_session.py`
- Delete `tools/stm32-monitor/src/stm32_monitor/poller.py`
- Delete `tools/stm32-monitor/src/stm32_monitor/sse_server.py`
- Delete legacy `tools/stm32-monitor/src/stm32_monitor/static/` if present
- Modify package metadata and tests only as required to prove no legacy path
- Create `docs/codex/returns/STM32TK-0501-MONITOR-SERVICE/implementation-report.md`
- Update this plan and the phase/roadmap checklists with verified facts only

- [ ] Add import/package-boundary tests proving ordinary Monitor/Toolkit imports do
  not load PyOCD and the Monitor wheel contains no direct backend or old defaults.
- [ ] Run all 0501 tests, all Probe/typed-debug/hardware regression tests, the full
  Toolkit suite, and the full Monitor suite with branch coverage at least 90%.
- [ ] Run `compileall`, `git diff --check`, forbidden API/default/token scans, build
  both wheels, install them in a fresh CPython 3.10 and 3.12 environment outside
  the repository, and exercise zero-group CRUD, fake observation, sampling,
  history, export, REST, WebSocket, and cancellation shutdown from the wheels.
- [ ] Performance gates: 256-value history batch p95 <50 ms; 10,000-value page p95
  <100 ms; 100,000-value export <5 s and <64 MiB; 100,000-value retention pass <2
  s and no sampler stall >=100 ms; service authentication/status p95 <10 ms.
- [ ] Windows owner verifies real NTFS junction rejection, SQLite lock/WAL behavior,
  dynamic loopback binding, and cancellation.  Linux owner verifies the same
  focused/full suites.  Physical probe tests are deferred to the 0.5 release gate
  and may not be claimed from software doubles.
- [ ] Commit the implementation report last.  It records accepted base and code
  head before the report commit, never its own final SHA.
- [ ] Push the branch, create one Draft PR, independently review the exact
  accepted-base-to-final-head diff in a fresh clean worktree, correct findings on
  this same branch, mark ready, merge after `ACCEPTED`, and retain the remote
  branch.

## Acceptance criteria

- A fresh workspace has no named groups, and neither service startup nor a read
  request creates defaults or modifies the project.
- All variable/register reads are exact typed reads tied to current firmware;
  arbitrary address, target, ELF, SVD, backend, or operation-level input is
  impossible at every public boundary.
- Same-probe monitor/flash/debug conflicts are deterministic and visible; no
  process is killed or lease stolen.  Different probes and projects remain
  isolated under concurrent use.
- Slow clients, storage pressure, malformed requests, stale evidence, process
  cancellation, and shutdown never leak tasks, listeners, files, tokens, leases,
  or mixed-firmware history.
- The source tree contains no active legacy Monitor runtime path and no direct
  Monitor dependency on PyOCD/CMSIS-SVD/PyYAML.
- All non-deferred gates pass and the independent review has no remaining P0/P1
  findings.
