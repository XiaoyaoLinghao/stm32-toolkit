# STM32 Toolkit VS-03 Task 7A Authority Amendment

**Status:** approved by the GPT-5.6-sol specification owner under the user's autonomous local
approval instruction on 2026-08-22.

**Accepted product base:** `9ff0f727f5997cf0ffd92c7272ffeb4e1153fccb`

**Amendment base:** `d9e3e1d6b8af8d4193c3a4268eae76fd20657f95`

This amendment resolves three interface contradictions found by the independent complete-diff
review of Task 7A. It supersedes only the affected authority, failure-projection, and retry clauses
of `2026-08-21-stm32-toolkit-0600-vs03-target-replay-monitor-verification-design.md`. All other
VS-03 boundaries remain valid.

## 1. Root causes and decisions

### 1.1 A complete MonitorRunRef must have a durable preimage

The accepted design requires Toolkit to cross-check every Monitor binding, window, group revision,
and projected batch digest. The current producer persists only `run_ref_sha256` in the
`monitor-run` root and returns the digest preimage to its immediate caller. A later Toolkit process
therefore cannot perform the required check. A digest without its canonical preimage is not a
complete cross-module contract.

The existing immutable `monitor-run/<operation_id>` root remains the transcript/operation
authority and is not rewritten. Monitor additionally publishes one immutable
`monitor-run-ref/<operation_id>` root. Its manifest is a closed Evidence envelope containing one
canonical `stm32-monitor-run-ref/1` artifact and naming the transcript Evidence as its sole parent.
The reference artifact contains the existing complete `MonitorRunRef`; its unsigned canonical
digest must equal both `MonitorRunRef.run_ref_sha256` and the digest recorded by both roots.

This second root is a projection authority, not a competing operation authority. Its identity is
the reference origin identity. Its closed metadata binds `operation_id`, `run_ref_sha256`,
`fixture_sha256`, scenario role, origin/import workspace IDs, replay source, and false physical
transport. `monitor-run-ref` is statically registered in Toolkit's Evidence root registry.

Monitor ingestion validates the old transcript root and any existing projected History before it
publishes a missing reference root. This makes an accepted legacy transcript/History pair
upgradeable without deleting, mutating, or adopting conflicting data. A different reference at the
same operation is `OPERATION_CONFLICT`; corrupt immutable bytes are
`EVIDENCE_INTEGRITY_FAILURE`; provider I/O is `ENVIRONMENT_FAILURE`.

Monitor comparison validates both roots and the complete reference artifact before it reads
History. Toolkit diagnostic validation independently reloads that reference artifact, validates
its canonical closed shape and digest, proves its sole transcript parent, reconstructs the
canonical transcript projection, and compares every reference field. Analysis
`before_run_id`/`after_run_id` must equal the respective authoritative `run_ref_sha256`; TestRun
Evidence IDs are never substitutes for Monitor run IDs.

### 1.2 Durable mode controls every later failure projection

`DiagnosticStore` remains responsible for structural chain validation and does not learn
application-level Target result vocabulary. It must preserve the original exception as the cause
when a referenced Evidence read becomes `DIAGNOSTIC_EVIDENCE_MISSING`.

It exposes a bounded read-only creation-intent query that validates the canonical session-created
event without dereferencing its Evidence and returns the durable `failed_run_mode`. Workflow code
must use that query for every session load, including show and all legacy diagnostic mutations. It
must not parse `00000000.json` directly and must not accept a caller-selected projection flag.

For Host sessions the existing public diagnostic codes and bytes remain unchanged. For Target
sessions, a referenced Evidence absence/corruption maps to `EVIDENCE_INTEGRITY_FAILURE`, a provider
`OSError` anywhere in the preserved cause chain maps to `ENVIRONMENT_FAILURE`, and identity
contradiction maps to `INCOMPATIBLE_IDENTITY`. The durable mode is used even when full reduction
cannot finish.

### 1.3 Accepted operation identity precedes current-state legality

An accepted operation ID is durable independent of later state transitions. `DiagnosticStore`
exposes an atomic read-only operation resolver taking session ID, operation ID, event type, actor,
and canonical request. It returns the current authoritative session plus the originally accepted
event when intent is identical; different event type, actor, or request is
`DIAGNOSTIC_OPERATION_CONFLICT`. An absent operation returns no match and performs no mutation.

Each Task 7A mutation validates and normalizes its public request, loads the bound authoritative
session, then resolves the operation before checking current-state legality or running new
preflight. An exact retry returns the current session and response data reconstructed from the
accepted event. `expected_revision` is concurrency control for a new append and is not operation
intent. A new stale request remains `DIAGNOSTIC_REVISION_CONFLICT` and appends nothing.

The store's existing append-time operation check remains the race-closing authority. The new
resolver is not an authorization bypass and does not weaken full-chain or Evidence validation.

## 2. Cross-module invariants

1. Every analysis run ID names a reloadable canonical `MonitorRunRef`, not a TestRun, History key,
   UUID alias, or unbacked digest.
2. The reference envelope's sole parent is exactly the transcript Evidence named by the reference.
3. Transcript bytes, transcript envelope/root, reference bytes/envelope/root, projected History,
   and AnalysisResult form one consistent chain or the operation fails before diagnostic append.
4. Session mode comes only from the canonical creation event; callers cannot select error
   projection.
5. Exact accepted operation retries remain successful after any legal later state transition and
   never add an event.
6. Conflict, stale revision, integrity failure, environment failure, and incompatible identity are
   distinct outcomes and do not invalidate unaffected accepted Evidence.

## 3. Migration and scope

Existing `monitor-run` roots and transcripts are retained. Re-ingesting the same frozen replay may
repair a missing `monitor-run-ref` envelope/root only after validating the existing root and full
History projection. No product command deletes or rewrites legacy Evidence. A workspace that has
conflicting or partial data fails closed and requires explicit operator recovery outside this
slice.

This amendment does not add Probe, hardware, packaging, release matrices, Python 3.10, adapters,
remote operations, or a new report Gate. Verification is limited to focused producer/consumer
contract tests, diagnostic store/workflow regressions, the existing Task 7A four-file suite, and
one independent real public-path probe.

## 4. Acceptance scenarios

1. Ingest two real frozen Monitor replays, reload both complete reference authorities in a fresh
   process, compare them, and prepare a Target diagnostic plan whose analysis IDs equal those
   reference digests.
2. Remove or corrupt a Target session's referenced TestRun Evidence and verify fresh show and every
   later operation return Target integrity failure; inject provider I/O and verify environment
   failure; repeat against Host and preserve its existing result.
3. Advance a session through declaration, plan, verification start, and marker attach; retry each
   accepted operation with its original actor/request and stale original revision and receive the
   original accepted product plus current session without a new event. Reuse each ID with changed
   intent and receive stable conflict; use a fresh stale ID and receive revision conflict.

