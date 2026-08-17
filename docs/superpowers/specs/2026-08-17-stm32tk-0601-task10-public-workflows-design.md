# STM32TK-0601 Task 10 Public Workflows Design

**Status:** prerequisite correction after rejected T10.1 candidate; implementation paused

**Accepted base:** `d4b43ff1bf74f7ac5058e93c708bfb49a5371304`

**Specification owner:** Codex

**Implementation owner:** local Codex subagents, one bounded unit at a time

**Reviewer:** a fresh local Codex subagent for every unit

**Remote action:** none authorized

**Hardware action:** none authorized or required

## 1. Objective

Expose the Evidence and Host/Target testing capabilities completed by STM32TK-0601 through one
closed public workflow contract. The command line keeps the nouns already frozen in the 0601
design. MCP uses separate tools where a single conditional input object would admit invalid
prepare/execute or Host/Target combinations.

This design replaces the original monolithic Task 10 with independently reviewable units. Each
unit has one primary delivery surface, one local commit, its own tests, and an independent verdict.
It does not change Probe v2, Evidence schemas, the GC algorithm, Target authorization semantics,
the Target execution state machine, or the release controller.

## 2. Frozen boundaries

### 2.1 One workspace, one managed Evidence store

Every operation is bound to one canonical project root, external Toolkit data root, and safe
session ID. The workflow loads the Project v3 logical project ID and uses `WorkspacePaths` to derive
the workspace. The only Evidence store visible to the workflow is:

```text
<data-root>/projects/<workspace-id>/evidence
```

The caller cannot supply an Evidence root, authorization-ledger root, manifest path, catalog path,
or artifact path. CLI receives `--project`, `--data-root`, and `--session-id` on each leaf command.
MCP uses the project/data/session values permanently bound in `ServerRuntime`. Evidence list always
injects the current `workspace_id` and `project_id`; callers cannot query another workspace or
project by supplying those filters.

The workflow creates only managed workspace directories through the existing path authority. It
does not change the process current directory and does not accept shell text, arbitrary argv, SQL,
wildcards, environment overrides, or paths outside the canonical project/data roots.

### 2.2 Thin shared application adapter

CLI and MCP call the same functions in a new `stm32_toolkit.testing_workflows` module. That module
may:

- derive the bound workspace and managed Evidence store;
- instantiate existing Evidence, Host, Target, Probe-client, and transport public APIs;
- translate closed request dataclasses to those APIs;
- invoke the public Test-run publisher from section 6.7 after a successful Host/Target run;
- project domain objects into the safe public result shapes in this document;
- map known domain exceptions to the closed error table in section 7.

It may not parse native test output, decode Target frames, flash directly, open a backend directly,
read private ledger files, call a name beginning with `_`, create a second authorization record,
rewrite an Evidence object, or implement retry/recovery logic.

### 2.3 Existing protocol envelope

Every successful or domain-failure CLI/MCP result is the existing `OperationResult`:

```json
{
  "protocol": "stm32-toolkit/1",
  "ok": true,
  "operation": "evidence.verify",
  "code": "OK",
  "message": "",
  "data": {},
  "details": {}
}
```

JSON data keys remain snake_case because they are existing domain protocol fields. MCP input names
remain lower camel case to match the existing MCP tools. CLI writes exactly one JSON document to
stdout for success and domain failure. Success exits 0; grammar/domain failure exits 2. A sanitized
unexpected internal failure exits 1 with no JSON and a bounded stderr line.

The canonical compact JSON encoding of a public `OperationResult` is at most 1,048,576 bytes. The
adapter measures the final result before emission and returns `EVIDENCE_LIMIT_EXCEEDED` instead of
truncating or emitting a partial object. Run/show use the bounded summary below rather than placing
all case results inline. Discovery keeps exact case IDs and therefore fails closed at this aggregate
bound rather than returning a partial inventory.

## 3. Public CLI grammar

The executable is the installed `stm32-toolkit` entry point. The shorter `stm32` spelling in the
program design is descriptive and is not introduced as a second executable.

`<context>` below is exactly:

```text
--project <canonical project directory>
--data-root <canonical external Toolkit data directory>
--session-id <safe session id>
```

The new commands always emit JSON; they do not add a redundant `--json` switch.

### 3.1 Evidence

```text
stm32-toolkit evidence verify <evidence-id> <context>

stm32-toolkit evidence list <context>
  [--session <session-id>]
  [--build-id <sha256>]
  [--elf-sha256 <sha256>]
  [--operation <exact operation>]
  [--produced-from <canonical UTC microseconds>]
  [--produced-to <canonical UTC microseconds>]
  [--limit <1..1000>]

stm32-toolkit evidence gc --dry-run <context>

stm32-toolkit evidence gc --apply <context>
  --plan-digest <sha256>
  --action-digest <sha256>
  --authorized
```

`--dry-run` and `--apply` are mutually exclusive and required. Apply requires all three authorization
arguments. `--authorized` is process-local explicit consent only; the exact action digest remains
the single-use authority consumed by the existing GC implementation. Dry-run accepts none of the
apply arguments.

### 3.2 Test discovery and execution

```text
stm32-toolkit test discover --mode host <context>

stm32-toolkit test discover --mode target <context>
  --probe <exact probe selector>
  --support-profile <canonical absolute support-profile path>

stm32-toolkit test run --mode host <context>
  --inventory-digest <sha256>
  [--case <exact case id> ...]

stm32-toolkit test run --mode target --prepare <context>
  --probe <exact probe selector>
  --support-profile <canonical absolute support-profile path>
  --inventory-digest <sha256>
  [--case <exact case id> ...]

stm32-toolkit test run --mode target --execute <context>
  --probe <exact probe selector>
  --action-digest <sha256>
  --authorized

stm32-toolkit test show <run-id> <context>
```

Host run has no prepare/execute switch. Target requires exactly one of `--prepare` or `--execute`.
Prepare accepts no authorization flag. Execute accepts no inventory/case override: those values are
loaded from the prepared record, and current Project v3 revision/inventory facts are independently
derived before the record is consumed. Omitting `--case` means every discovered case. Case IDs are
unique exact strings and are reordered only into frozen inventory order.

Project v3 owns build preset, CTest preset, Target executable, timeout, transport, transport config,
revision, build ID, and ELF identity. It does **not** own board/probe identity or the complete Target
support profile. Target discover and prepare additionally require:

```text
--support-profile <canonical absolute .../target/target-support-profile.json>
```

The path selects one manifest-bound support root; it is not a field override and the caller cannot
submit profile JSON. The loader in section 6.5 validates the complete root and returns the only
support mapping admitted to discovery/prepare. Prepare binds the complete validated mapping into
the action digest. Execute neither accepts nor rereads a support path: the immutable prepared copy
is its sole support authority, while current project revision/inventory, firmware, live target
identity, and raw probe-selector hash are independently checked before/during consumption. The
Target probe selector is repeated at execute because the prepared record binds only its SHA-256;
the raw selector is neither persisted nor returned.

## 4. MCP tools

All tools use the permanently bound `ServerRuntime`. They do not accept project, data, session,
support-profile, or Evidence-root arguments. Server startup may bind one canonical support-profile
path once. When none is bound, all non-Target tools plus `stm32_test_target_run` remain available;
Target discover/prepare return the fixed `TEST_TRANSPORT_UNAVAILABLE` result before probe creation.

| Tool | Exact input fields |
|---|---|
| `stm32_evidence_verify` | `evidenceId: Digest` |
| `stm32_evidence_list` | `sessionId?: SessionId`, `buildId?: Digest`, `elfSha256?: Digest`, `operation?: BoundedString`, `producedFrom?: CanonicalUtc`, `producedTo?: CanonicalUtc`, `limit: 1..1000 = 100` |
| `stm32_evidence_gc_plan` | none |
| `stm32_evidence_gc_apply` | `planDigest: Digest`, `actionDigest: Digest`, `authorized: StrictBool` |
| `stm32_test_host_discover` | none |
| `stm32_test_target_discover` | `probeId: ProbeId` |
| `stm32_test_host_run` | `inventoryDigest: Digest`, `caseIds: UniqueCaseIds = []` |
| `stm32_test_target_prepare` | `probeId: ProbeId`, `inventoryDigest: Digest`, `caseIds: UniqueCaseIds = []` |
| `stm32_test_target_run` | `probeId: ProbeId`, `actionDigest: Digest`, `authorized: StrictBool` |
| `stm32_test_show` | `runId: RunId` |

MCP discovery is split into Host and Target tools even though CLI retains `--mode`. This refinement
prevents a conditional `probeId` schema in which Host calls could carry a probe or Target calls could
omit it. MCP prepare and execute are also separate tools; no `phase` enum or union of optional fields
is public.

`Digest` is exactly 64 lowercase hexadecimal characters. `ProbeId`, `SessionId`, `RunId`, UTC,
bounded strings, list lengths, and integer ranges reuse the existing product validators. MCP/Pydantic
must reject unknown fields, booleans in integer positions, repeated logical values, and invalid
conditional combinations before invoking a workflow.

## 5. Exact success data

### 5.1 Evidence verify

Operation is `evidence.verify`. `data` is:

```json
{
  "evidence": { "schema": "stm32-evidence/1", "evidence_id": "..." },
  "authoritative": true
}
```

`evidence` is the complete verified `EvidenceEnvelope.to_dict()` result. Its existing 1 MiB envelope,
collection, string, metadata, and artifact limits are the public bound. Artifact locations remain
validated store-relative paths. The adapter does not inline artifact bytes.

### 5.2 Evidence list

Operation is `evidence.list`. `data` is:

```json
{
  "items": [
    {
      "evidence_id": "...",
      "workspace_id": "...",
      "project_id": "...",
      "session_id": "...",
      "build_id": "...",
      "elf_sha256": "...",
      "operation": "target-test-run",
      "produced_at_utc": "..."
    }
  ],
  "count": 1,
  "limit": 100,
  "authoritative": false
}
```

Rows are existing `EvidenceSummary` projections ordered by `produced_at_utc, evidence_id`. The
adapter always filters by the current workspace/project. Acting on a row requires `evidence.verify`.
The adapter calls `EvidenceCatalog.query_fresh(...)` from section 6.3. Under one store mutation
lock it validates freshness, rebuilds once only when missing/legacy/dirty, and executes the bounded
read-only query before releasing the lock. This prevents a manifest mutation between validation and
query. The freshness state is derived coordination metadata only; it never mutates authoritative
manifests, objects, roots, or authorization records. A concurrent authoritative mutation cannot be
missed because every manifest publication/deletion marks the catalog dirty under the same mutation
lock before committing that mutation. The warm 10,000-row query remains the separately frozen
500 ms workload; a cold/dirty rebuild is the separately frozen 10 s workload. Acting on a returned
non-authoritative row still requires verify/show.

### 5.3 GC plan

Operation is `evidence.gc.plan`. `data` contains exactly:

```text
schema, store_id, roots, manifest_ids, reachable_manifests,
unreachable_manifests, reachable_objects, unreachable_objects,
unknown_entries, corrupt_entries, bytes_reclaimable,
manifest_snapshot_digest, store_snapshot_digest, plan_digest, action_digest
```

Values are copied from the existing `GcPlan`; `store_root` is deliberately omitted. Each `roots`
member contains exactly `root_type`, `root_id`, and `manifest_id`; arbitrary `RootRecord.metadata`
is omitted because it is not needed to authorize deletion and is not a public-safe field. All paths
in the collections are validated store-relative paths. `action_digest` is shown separately because
it is the exact value the user must authorize and the canonical plan document intentionally
excludes it.

### 5.4 GC apply

Operation is `evidence.gc.apply`. The workflow computes a fresh plan under the existing mutation
lock. It applies only when both supplied digests match the fresh plan and `authorized` is exactly
true. `data` projects every `GcResult.to_dict()` field. The `errors` collection alone is sanitized:
it preserves the lower-level error count but replaces every member with the fixed public message
for the result code from section 7. It never returns `str(exc)` or a managed path. A store change,
digest mismatch, reused authorization, or partial deletion remains a non-OK domain result; it is
never converted to success. Any committed manifest deletion has already marked the catalog dirty;
GC does not rebuild it on the mutation hot path, and the next list performs the bounded cold/dirty
refresh.

### 5.5 Discovery

Operations are `test.host.discover` and `test.target.discover`. Both return:

```json
{
  "inventory": { "mode": "host", "case_ids": [], "inventory_digest": "..." },
  "discovery_artifact": {
    "sha256": "...",
    "size_bytes": 0,
    "relative_path": "objects/sha256/...",
    "kind": "test-discovery",
    "media_type": "application/json"
  }
}
```

`inventory` is the complete `TestInventory.to_dict()` result. Host reuses its existing discovery
artifact. Target discovery raw bytes are ingested as one bounded artifact; raw bytes are not inlined.
Discovery performs no flash, reset, halt, write, or reusable authorization.

### 5.6 Host run

Operation is `test.host.run`. The workflow creates a fresh runner, rediscovers, requires the supplied
inventory digest to match, and executes exact cases. It passes the complete manifest plus the
runner-owned artifacts to `TestRunPublisher.publish_host()`, which publishes one `host-test-run`
Evidence envelope and one `test-run` root whose `root_id` is the run ID and whose `manifest_id` is
the Evidence ID. `data` is:

```json
{
  "run": {
    "run_id": "...",
    "mode": "host",
    "state": "passed",
    "identity": {},
    "transport": null,
    "case_counts": {
      "passed": 1,
      "failed": 0,
      "skipped": 0,
      "error": 0,
      "timeout": 0
    },
    "started_at_utc": "...",
    "ended_at_utc": "...",
    "duration_ms": 1
  },
  "test_manifest": {
    "sha256": "...",
    "size_bytes": 1,
    "relative_path": "objects/sha256/...",
    "kind": "test-manifest",
    "media_type": "application/json"
  },
  "evidence_id": "..."
}
```

`run` is derived from the complete manifest and has exactly the shown fields; `case_counts` always
contains all five case states. The canonical complete manifest is returned only as a verified
artifact reference, as are stdout/stderr/raw event content.
A Host envelope contains the non-null manifest, raw-event, stdout, and stderr artifacts exactly
once. Its metadata is exactly `test_run_id`, `test_manifest_sha256`, and `inventory_digest`. The
root metadata is exactly `mode` and terminal `state`.
A root-publication failure is an operation failure; an already published but unrooted envelope is
not reported as a successful run and remains eligible for later GC.

### 5.7 Target prepare

Operation is `test.target.prepare`. It performs fresh Target discovery, checks the supplied inventory
digest and case selection, derives the closed binding from Project v3 and observed target identity,
and invokes the existing `TargetTestRunner.prepare()` exactly once. `data` is:

```json
{
  "action_digest": "...",
  "nonce": "...",
  "expires_at_utc": "...",
  "action": {
    "operation": "target-test-run",
    "workspace_id": "...",
    "project_id": "...",
    "session_id": "...",
    "revision": "...",
    "target": {},
    "probe_serial_hash": "...",
    "elf_path": "project/relative/path.elf",
    "elf_sha256": "...",
    "build_id": "...",
    "inventory_digest": "...",
    "transport": "rtt",
    "transport_config": {},
    "support_profile_digest": "...",
    "cases": [],
    "timeout_ms": 1000
  }
}
```

`action` is the complete human-reviewable action summary. `elf_path` is canonical project-relative
POSIX syntax and is also the value bound in the internal prepared record; the support profile body
and ledger paths are omitted. `support_profile_digest` identifies the exact canonical profile. The
action digest still binds the complete internal record, including the exact support profile and
internal ELF binding. The nonce is not an authorization token and cannot execute the run.

### 5.8 Target run

Operation is `test.target.run`. The workflow loads the prepared handle by exact digest through the
new public rehydration API defined in section 6, derives current revision/inventory facts, constructs
the existing guarded flash/probe/transport composition, and calls `TargetTestRunner.run()` once.
It then passes the returned manifest/envelope pair to `TestRunPublisher.publish_target()` to publish
the `test-run` root. The envelope publication has already marked derived catalog state dirty; no
catalog rebuild runs on the execution hot path. `data` has the same shape as Host run.
The root metadata is exactly `mode: "target"` and the manifest's terminal `state`.

Execute does not load `VerifiedTargetSupport` and does not require its source root to remain
present. The action digest already binds the complete validated support mapping copied during
prepare; re-reading a mutable source after authorization would create a second, unbound authority.
The workflow must use only that prepared mapping while independently deriving and checking the
current project revision/inventory/ELF/build facts and the runner checks current target, transport,
firmware, and probe identity before the one-time run.

The workflow never silently prepares, retries, substitutes a digest, or executes another transport.
`authorized=false` fails before prepared-handle load, probe open, flash, or authorization consumption.
Every attempt that reaches the existing runner keeps its single-use semantics, including failures.

### 5.9 Test show

Operation is `test.show`. The workflow reads the exact `test-run` root by run ID through the new
public root lookup, verifies its referenced Evidence envelope authoritatively, locates exactly one
`test-manifest` artifact, verifies that artifact, parses a canonical `TestRunManifest`, and requires
all run IDs/digests to agree. `data` has exactly `run`, `test_manifest`, `evidence_id`, and
`authoritative`. `run` is the exact nine-field run object defined in section 5.6; `test_manifest` is
the exact five-field `ArtifactRef` defined there; `evidence_id` is the verified envelope digest; and
`authoritative` is exactly true. A manifest larger than 67,108,864 bytes returns
`EVIDENCE_LIMIT_EXCEEDED`. It never returns a catalog-only summary as an authoritative run.

## 6. Required narrow prerequisites

Ten gaps in the accepted-base public APIs prevent a correct thin adapter. Each prerequisite is a
separate owner-domain unit and commit. None is worked around with exception-text parsing, private
calls, live-identity self-authorization, or duplicate persistence.

### 6.0A Project mutation exception ownership

The accepted base makes `project_upgrade.py` construct `EvidenceValidationError` directly and
borrow private Windows identity helpers from `evidence.gc`. That cross-domain dependency prevents
the Evidence exception constructor from becoming closed without breaking Project mutation paths.
Before section 6.1, introduce private Project-domain `ProjectMutationLockError(RuntimeError)` in
`project_upgrade.py`. Project mutation-lock/authorization persistence failures use that type;
`apply_project_upgrade`, generation configuration, and migration conversion continue projecting it
to their existing fixed result codes and details. It is not added to the Task 10 public error table.

`project_upgrade.py` owns the exact safe file/parent identity primitives it needs and no longer
imports private helpers from `evidence.gc`. Lower-level `EvidenceValidationError` raised by reused
EvidenceStore path/storage primitives is translated at the Project boundary without inspecting its
code or text. No Evidence, GC, Project schema, public result, lock order, authorization decision, or
wire contract changes. This is one Project-domain prerequisite unit and commit.

### 6.0B Probe authorization exception ownership

The accepted base also makes `probe/authorization.py` construct `EvidenceValidationError` directly
for its CONTROL authorization ledger. Before section 6.1, introduce private
`_ControlAuthorizationStorageError(Exception)` in that module and migrate every Probe-owned direct
raise to it. The existing authority-lock, records-directory, and prepared-record boundaries catch
both this private type and any `EvidenceValidationError` still produced by reused EvidenceStore
primitives, then preserve the current `PROBE_AUTHORIZATION_INVALID` and downstream
`TEST_AUTHORIZATION_INVALID` results. The private type has no public code, export, serialization,
or message-parsing role. No Evidence implementation, Target runner, Probe service/client/worker,
ledger format, authorization decision, or wire protocol changes. This is one Probe-authorization
prerequisite unit and commit.

### 6.0C Project regression exception realism

After T10.P1, three Project regression tests still synthesize the old one-argument
`EvidenceValidationError` constructor even though their purpose is to verify translation of a
lower-level EvidenceStore failure. Before section 6.1, replace those synthetic calls in
`test_project_upgrade.py` with a test helper that causes a real accepted EvidenceStore validation
failure, such as a managed-directory operation on a file root. The tests continue asserting only
`ProjectMutationLockError` and Project locking behavior; they do not branch on the Evidence
constructor signature, code, or text. This is a test-only prerequisite commit, changes no product
behavior, and keeps T10.1's nine-path Evidence scope closed.

### 6.1 Machine-readable Evidence failure taxonomy

The existing `EvidenceValidationError` has no machine-readable reason, while its human text may
contain a managed absolute path. Add a closed reason/code to the existing Evidence exception
boundary with exactly `EVIDENCE_INVALID`, `EVIDENCE_CORRUPT`, `EVIDENCE_PATH_UNSAFE`, and
`EVIDENCE_LIMIT_EXCEEDED`. Every `EvidenceValidationError` raised by Evidence
model/store/catalog/GC code must carry one of those codes without changing its current fail-closed
behavior; expected filesystem failures are wrapped at that boundary rather than leaked as raw
`OSError`. The existing private `_GcStoreChanged` becomes a separate `GcStoreChangedError` (not an
`EvidenceValidationError`) with the sole code `GC_STORE_CHANGED`; it is raised only for a mutation
or identity race during GC plan/apply and is mapped by the GC result boundary. The public workflow
reads only a typed code and emits the fixed message in section 7; it never parses or returns
exception text. This is one Evidence error-taxonomy unit and commit.

### 6.2 Authoritative Evidence read primitives

Add `get_root(store, root_type, root_id) -> RootRecord` to the Evidence GC/root module. It performs
the same stable, canonical, no-link, single-link, case-fold-safe authoritative read used by GC. It
accepts only a registered root type and a valid root ID and does not list or mutate roots. This is
paired with
`EvidenceStore.read_artifact(artifact: ArtifactRef, *, maximum_bytes: int) -> bytes`. The method
requires `maximum_bytes` from 1 through 67,108,864, rejects a larger artifact before allocation, and
revalidates the relative path, object identity, exact size, SHA-256, and EOF before returning bytes.
Neither function exposes an absolute path or an open descriptor. Root lookup must not call a helper
that creates a missing `manifests` or `roots` directory; absence is a coded no-create read failure.
This is one Evidence
authoritative-read task and commit with its own tests and review.

### 6.3 Derived catalog freshness lifecycle

Add one Evidence-only freshness contract around the existing derived catalog. The canonical JSON
marker is exactly `<store>/catalog-state.json`, schema
`stm32-evidence-catalog-state/1`, with exactly `schema`, `catalog_sha256`, and `dirty`.
For `dirty=true`, `catalog_sha256` is exactly null; for `dirty=false`, it is the lowercase SHA-256
of `catalog.sqlite3`. `EvidenceStore.put_envelope()` atomically writes the dirty marker under the
mutation lock before the manifest CREATE_NEW publication; GC does the same before its first
manifest deletion. A failed later mutation may leave a harmless dirty marker. After atomically
publishing the verified catalog, `rebuild_catalog()` atomically writes a clean marker with that
catalog digest under the same lock. A missing/noncanonical/legacy marker, missing catalog, digest
mismatch, or `dirty=true` is stale.

Add `ensure_catalog_fresh(store) -> EvidenceCatalog`: under the existing mutation lock it validates
the marker/catalog; a clean catalog returns without scanning manifests, otherwise it calls the
existing private locked rebuild primitive once (never recursively acquiring the public rebuild
lock). Also add `EvidenceCatalog.query_fresh(...)`, which calls the same locked primitive and runs
the existing closed query while retaining that lock; Task 10 list must use this method rather than
an ensure-then-query pair. Marker/catalog reads and publications use the existing no-link/reparse,
single-link, case-fold-safe stable path primitives. The marker is derived cache state, never an
authority or GC root.
Crash/fault/race tests must prove no committed manifest creation/deletion can leave a falsely clean
catalog. The warm list workload therefore stays a catalog query; cold/dirty refresh remains the
separate rebuild workload. This is one Evidence catalog-lifecycle unit and commit and does not
change envelope/root/GC schemas or deletion authority.

### 6.4 Canonical Test manifest deserialization

Add closed `from_dict()` constructors for `TestCaseResult` and `TestRunManifest` in the existing
testing model. They reject tuples and unknown/missing fields, delegate identity/artifact parsing to
the existing models, and rerun every current semantic invariant. No second schema or permissive
legacy form is accepted. This is one Test protocol-model task and commit with its own tests and
review.

### 6.5 Verified Target support provider

The accepted base has no product-runtime source for the complete mapping required by
`TargetTestRunner`; Project v3 and the Task 1 feasibility profile are both intentionally
insufficient. Add a read-only `VerifiedTargetSupport` loader. Its only source is the canonical
absolute file `<support-root>/target/target-support-profile.json`, and that exact sibling must be
declared by `<support-root>/support-manifest.json`. The closed profile schema is
`stm32-target-support/1` and contains exactly:

```text
schema, backend, board_id, mcu, target_id, probe_serial_hash,
ram, mailbox, rtt, uart, semihosting, firmware
```

`backend` is exactly `pyocd`; `board_id`, `mcu`, and `target_id` match exactly
`[A-Za-z0-9][A-Za-z0-9._:-]{0,127}`; `probe_serial_hash` and all other digests are lowercase
SHA-256;
capabilities use the existing Target runner shapes. `firmware` contains exactly a
support-root-relative POSIX `elf_path`, `elf_sha256`, `build_id`, and `inventory_digest`; that ELF
is another exact manifest member. The loader derives the runner-only absolute
`semihosting_runtime` after validation. The loader validates the canonical root, rejects
link/reparse/special/case-fold
aliases, validates the closed manifest with exact member/size/digest equality, requires the
manifest-bound `feasibility/profile.json` RAM, mailbox, UART, and semihosting capabilities to equal
the Target profile values and its RTT channel to equal the Target RTT channel. An optional explicit
RTT control-block address exists only in the Target profile and must be inside its declared RAM.
Mailbox bounds must also lie inside that RAM. The loader rereads the manifest, both profiles, and
ELF before return.

The immutable result exposes only the runner `support_profile` projection, expected target
identity, expected firmware/build/inventory bindings, and source profile/manifest digests. It does
not expose the root path or raw probe selector. CLI binds the path once per Target discover or
prepare invocation; MCP binds it once in `ServerRuntime`. Execute uses only the immutable prepared
copy and never rereads this source. Missing or mismatched support is
`TEST_TRANSPORT_UNAVAILABLE`; malformed CLI/MCP grammar is `TEST_PROTOCOL_INVALID`. No code may
derive this authority from the live probe or import release-controller internals. This is one
Target-support provenance unit and commit; it performs no probe/hardware operation.

### 6.6 Target prepared-handle rehydration

Add `TargetTestRunner.load_prepared(action_digest, *, now=None) -> PreparedTargetRun`. It reads and
validates the existing persistent prepared record through the same pinned authorization authority,
does not consume or rewrite it, rejects expired/consumed/malformed records, and returns the exact
immutable handle required by `run()`. It introduces no new record or state. This is a Target
execution-only task and commit with its own tests and review.

### 6.7 Test-run Evidence publication bridge

Add a public `TestRunPublisher` in `testing/publication.py`. It is the only Task 10 component that
translates an already complete immutable Test run result into Evidence publication; it never
discovers, executes, flashes, authorizes, or parses native/Target output. `publish_host()` verifies
the Host manifest and its existing artifact references, ingests the canonical manifest, publishes
the exact Host envelope/root from section 5.6. `publish_target()`
accepts the exact manifest/envelope pair already returned by `TargetTestRunner.run()`, verifies
their identity/artifact relationship, and publishes only the `test-run` root. Envelope publication
marks the catalog dirty; publication never performs the 10,000-manifest rebuild workload.

Publication is fail-closed but not falsely transactional: if an envelope or root was committed
before a later root/catalog failure, the operation is non-success and the retained authoritative
state remains verifiable/GC-reachable according to its existing semantics. This is one publication
bridge unit and commit; it changes no Test/Evidence schema, execution engine, or authorization.

## 7. Errors, output safety, and cleanup

### 7.1 Closed mappings

The public code/message/details projection is exhaustive. Details are always `{}`. Source exception
text, `cleanup_notes`, process argv/output, and GC deletion text are never returned.

| Source code or typed Evidence reason | Public code | Fixed public message |
|---|---|---|
| `EVIDENCE_INVALID` | same | `Evidence is invalid.` |
| `EVIDENCE_CORRUPT` | same | `Evidence is corrupt.` |
| `EVIDENCE_PATH_UNSAFE` | same | `Evidence path is unsafe.` |
| `EVIDENCE_LIMIT_EXCEEDED` | same | `Evidence limit exceeded.` |
| `PROJECT_NOT_CONFIGURED` | same | `Project is not configured.` |
| `PROJECT_JSON_INVALID` | same | `Project manifest JSON is invalid.` |
| `PROJECT_SCHEMA_INVALID` | same | `Project manifest schema is invalid.` |
| `PROJECT_SCHEMA_VERSION_UNSUPPORTED` | same | `Project manifest schema version is unsupported.` |
| `TEST_NO_CASES` | same | `No test cases were discovered.` |
| `TEST_CASE_NOT_FOUND` | same | `A requested test case was not discovered.` |
| `TEST_INVENTORY_CHANGED` | same | `The test inventory changed.` |
| `TEST_PROTOCOL_INVALID` | same | `Test protocol is invalid.` |
| `TEST_TIMEOUT`, `TEST_PROCESS_TIMEOUT` | `TEST_TIMEOUT` | `Test operation timed out.` |
| `TEST_TRANSPORT_UNAVAILABLE` | same | `Target test transport is unavailable.` |
| `TEST_AUTHORIZATION_INVALID` | same | `Target test authorization is invalid.` |
| `TEST_IDENTITY_MISMATCH` | same | `Test identity does not match.` |
| `TEST_PROCESS_ERROR`, `TEST_PROCESS_FAILED`, `TEST_FLASH_FAILED` | `TEST_EXECUTION_FAILED` | `Test execution failed.` |
| `TEST_DUPLICATE_CASE`, `TEST_ENVIRONMENT_INVALID`, `TEST_DISCOVERY_INVALID`, `TEST_EVENT_PAYLOAD_INVALID`, `TEST_EVENT_SEQUENCE_INVALID`, `TEST_EXIT_MISMATCH`, `TEST_NATIVE_RESULT_INVALID`, `TEST_FRAME_CRC_INVALID`, `TEST_FRAME_VERSION_INVALID`, `TEST_STREAM_INCOMPLETE` | `TEST_PROTOCOL_INVALID` | `Test protocol is invalid.` |
| `TEST_FRAME_TOO_LARGE`, `TEST_FRAME_RECOVERY_LIMIT`, `TEST_STREAM_TOO_LARGE`, `TEST_PROCESS_OUTPUT_LIMIT` | `EVIDENCE_LIMIT_EXCEEDED` | `Evidence limit exceeded.` |
| `TEST_RESULTS_UNSAFE` | `EVIDENCE_PATH_UNSAFE` | `Evidence path is unsafe.` |
| `PROBE_ENDPOINT_INVALID`, `PROBE_RESPONSE_INVALID`, `PROBE_PROTOCOL_INVALID`, `PROBE_REQUEST_INVALID`, `PROBE_VERSION_MISMATCH`, `PROBE_TOOLKIT_INCOMPATIBLE` | `TEST_PROTOCOL_INVALID` | `Test protocol is invalid.` |
| `PROBE_CONTENT_TYPE_REQUIRED`, `PROBE_OPERATION_LEVEL_DENIED` | `TEST_PROTOCOL_INVALID` | `Test protocol is invalid.` |
| `PROBE_PROJECT_ROOT_REQUIRED`, `PROBE_SESSION_MISMATCH`, `PROBE_SESSION_UNSAFE` | `TEST_IDENTITY_MISMATCH` | `Test identity does not match.` |
| `PROBE_OPERATION_UNAVAILABLE`, `PROBE_OPERATION_UNSUPPORTED`, `PROBE_LEASE_INVALID`, `PROBE_LEASE_LOST`, `PROBE_BACKPRESSURE`, `PROBE_BACKEND_ERROR`, `PROBE_SERVICE_UNAVAILABLE`, `PROBE_SESSION_UNAVAILABLE`, `PROBE_MODIFICATIONS_DRAINING`, `PROBE_AUTH_REQUIRED`, `PROBE_HOST_REJECTED`, `PROBE_ORIGIN_REJECTED`, `PROBE_PEER_REJECTED` | `TEST_TRANSPORT_UNAVAILABLE` | `Target test transport is unavailable.` |
| `PROBE_AUTHORIZATION_REQUIRED`, `PROBE_AUTHORIZATION_INVALID` | `TEST_AUTHORIZATION_INVALID` | `Target test authorization is invalid.` |
| `PROBE_IDENTITY_MISMATCH` | `TEST_IDENTITY_MISMATCH` | `Test identity does not match.` |
| `PROBE_LIMIT_EXCEEDED`, `PROBE_REQUEST_TOO_LARGE` | `EVIDENCE_LIMIT_EXCEEDED` | `Evidence limit exceeded.` |
| `PROBE_TIMEOUT`, `PROBE_REQUEST_TIMEOUT` | `TEST_TIMEOUT` | `Test operation timed out.` |
| `PROBE_INTERNAL_ERROR` | `TEST_EXECUTION_FAILED` | `Test execution failed.` |
| `GC_AUTHORIZATION_INVALID` | same | `GC authorization is invalid.` |
| `GC_AUTHORIZATION_CONSUMED` | same | `GC authorization was already consumed.` |
| `GC_PLAN_DIGEST_MISMATCH` | same | `GC plan digest does not match.` |
| `GC_PLAN_INVALID` | same | `GC plan is invalid.` |
| `GC_STORE_CHANGED` | same | `Evidence store changed.` |
| `GC_DELETE_FAILED` | same | `Evidence deletion failed.` |
| `GC_PARTIAL_DELETE` | same | `Evidence deletion was partial.` |

`TEST_EXECUTION_FAILED` is the sole new Task 10 public code. It closes a confirmed gap: a native
Host process or guarded Target flash can fail without being a timeout, protocol defect, identity
failure, or unavailable transport. It adds no new execution behavior. `GC_APPLIED` remains the
lower-level successful `GcResult.code` inside data while the outer successful
`OperationResult.code` is `OK`. `GC_PLAN_SCHEMA`, `GC_RESULT_SCHEMA`, and `TEST_SCHEMA` are schema
identifiers, not errors.

`TEST_EVIDENCE_FAILED` means the workflow was composed without its required collector and is an
internal programming failure, not a domain result. Any source code absent from the table is also a
sanitized internal failure. CLI exits 1 with fixed stderr `Test workflow failed.`; MCP uses its
existing sanitized internal-error boundary. Neither path emits an `OperationResult`.

Before table lookup, expected `OSError`/`ValueError` from canonical project/workspace derivation is
normalized to `PROJECT_NOT_CONFIGURED`; support-loader absence/mismatch is normalized to
`TEST_TRANSPORT_UNAVAILABLE`. No other untyped exception is normalized.

No operation-specific partial-success object is returned. GC's existing terminal non-success result
is wrapped in `OperationResult(ok=false)` even when it reports retained/deleted counts.

### 7.2 No path or secret disclosure

Before returning, the shared adapter recursively validates `data` and `details`:

- no absolute Windows/POSIX path, drive, UNC path, home expansion, data root, project root, scratch
  directory, authorization-ledger path, or catalog path;
- only validated project-relative `elf` and Evidence `relative_path` values may look path-like;
- no raw probe serial/selector in persisted Evidence, Target prepare output, errors, or details;
- no environment value, command argv, API key, token, authorization record, or support-profile body;
- messages and details are bounded and use fixed public wording rather than exception text.

The CLI grammar-error path uses the existing safe parser and never echoes caller values. MCP
validation errors are generated before a workflow call.

### 7.3 Cleanup

Host process-tree and Target transport/probe cleanup remain owned by their existing runners. The
adapter adds no retry. A failure to publish Evidence/root is returned only after required runner
cleanup has completed. Target prepare discovery uses the existing required cleanup contract and
never leaves a reusable live transport/probe session.

## 8. Test strategy

Every implementation unit begins with a focused RED and ends with dual-Python correctness, changed-
file branch coverage of at least 90%, `git diff --check`, exact allowlist, and a fresh independent
review. No test uses real hardware, network, remote Git, ambient shell, or a caller-chosen Evidence
root.

Required behavior matrices include:

1. exact CLI grammar, conflicts, unknown/repeated arguments, types, exit/stdout/stderr contracts;
2. exact MCP tool inventory and JSON schema with no invalid conditional state;
3. CLI/MCP semantic parity for every success and closed domain error;
4. two projects sharing one data root cannot list, verify, show, prepare, execute, or GC each
   other's state;
5. recursive no-secret/no-absolute-path checks for success, domain failure, and injected exception;
6. list missing/stale catalog rebuild, limits/order/filters, derived-only mutation, and explicit
   non-authoritative status; catalog-state pre-publication invalidation, crash recovery, clean warm
   query without manifest scan, and the independent 500 ms list/10 s rebuild workloads;
7. verify/show authoritative rehash and corruption/path/link/case-fold rejection;
8. GC dry-run/apply digest mutation, false authorization, changed store, consumption, and no
   deletion before exact authorization;
9. Host discover/run exact inventory/cases, fresh rediscovery, envelope/root publication, process
   failure, output limits, and cleanup;
10. Target discover/prepare/run exact binding, mutation, expiry, single consumption, cross-process
    rehydration, verified support-root/profile/manifest/ELF provenance, wrong raw probe selector,
    no implicit flash, and transport/probe cleanup;
11. large discovery/log/run content appears only as verified `ArtifactRef` values;
12. `test show` rejects missing, ambiguous, corrupt, cross-bound, or contradictory root/envelope/
    manifest chains.
13. every Project/Probe source code in section 7 maps to its exact fixed code/message with empty
    details, and every unknown source code reaches only the sanitized internal boundary.

## 9. Delivery decomposition

The implementation order is mandatory. The three accepted-base dependency corrections must be CLEAN
before the original numbered units start:

All paths below are repository-relative and exact; a unit may modify no other path.

- **T10.P1 — Project mutation exception decoupling:** Project-domain ownership only. Paths:
  `tools/stm32-toolkit/src/stm32_toolkit/project_upgrade.py`,
  `tools/stm32-toolkit/src/stm32_toolkit/generation/configure.py`,
  `tools/stm32-toolkit/src/stm32_toolkit/migration/apply.py`,
  `tools/stm32-toolkit/tests/test_project_upgrade.py`,
  `tools/stm32-toolkit/tests/test_generation.py`, and
  `tools/stm32-toolkit/tests/test_migration_apply.py`.
- **T10.P2 — Probe authorization exception decoupling:** Probe authorization storage ownership
  only. Paths: `tools/stm32-toolkit/src/stm32_toolkit/probe/authorization.py` and
  `tools/stm32-toolkit/tests/test_target_runner.py`.
- **T10.P3 — Project regression exception realism:** replace three synthetic legacy Evidence
  constructor calls with a real lower-level EvidenceStore failure; test-only. Path:
  `tools/stm32-toolkit/tests/test_project_upgrade.py`.

1. **T10.1 — Evidence failure taxonomy:** coded Evidence/GC race errors only. Paths:
   `tools/stm32-toolkit/src/stm32_toolkit/evidence/model.py`,
   `tools/stm32-toolkit/src/stm32_toolkit/evidence/store.py`,
   `tools/stm32-toolkit/src/stm32_toolkit/evidence/catalog.py`,
   `tools/stm32-toolkit/src/stm32_toolkit/evidence/gc.py`,
   `tools/stm32-toolkit/src/stm32_toolkit/evidence/__init__.py`,
   `tools/stm32-toolkit/tests/test_evidence_model.py`,
   `tools/stm32-toolkit/tests/test_evidence_store.py`,
   `tools/stm32-toolkit/tests/test_evidence_catalog.py`, and
   `tools/stm32-toolkit/tests/test_evidence_gc.py`.
2. **T10.2 — Authoritative Evidence reads:** `get_root` and `read_artifact` only. Paths:
   `tools/stm32-toolkit/src/stm32_toolkit/evidence/store.py`,
   `tools/stm32-toolkit/src/stm32_toolkit/evidence/gc.py`,
   `tools/stm32-toolkit/src/stm32_toolkit/evidence/__init__.py`,
   `tools/stm32-toolkit/tests/test_evidence_store.py`, and
   `tools/stm32-toolkit/tests/test_evidence_gc.py`.
3. **T10.3 — Derived catalog freshness lifecycle:** marker/invalidations,
   `ensure_catalog_fresh`, and no public workflow. Paths:
   `tools/stm32-toolkit/src/stm32_toolkit/evidence/store.py`,
   `tools/stm32-toolkit/src/stm32_toolkit/evidence/catalog.py`,
   `tools/stm32-toolkit/src/stm32_toolkit/evidence/gc.py`,
   `tools/stm32-toolkit/src/stm32_toolkit/evidence/__init__.py`,
   `tools/stm32-toolkit/tests/test_evidence_store.py`,
   `tools/stm32-toolkit/tests/test_evidence_catalog.py`, and
   `tools/stm32-toolkit/tests/test_evidence_gc.py`.
4. **T10.4 — Canonical Test manifest deserialization:** model `from_dict()` methods only. Paths:
   `tools/stm32-toolkit/src/stm32_toolkit/testing/model.py`,
   `tools/stm32-toolkit/src/stm32_toolkit/testing/__init__.py`, and
   `tools/stm32-toolkit/tests/test_testing_model.py`.
5. **T10.5 — Shared public workflow context/error contract:** managed workspace/store derivation,
   exhaustive section 7 mapping, bounded result emission, and no workflow execution. Paths:
   `tools/stm32-toolkit/src/stm32_toolkit/testing_workflows.py` and
   `tools/stm32-toolkit/tests/test_testing_workflows.py`.
6. **T10.6 — Evidence verify/list public workflows:** verify plus atomic fresh-query list; no GC or Test
   operation. Paths: `tools/stm32-toolkit/src/stm32_toolkit/testing_workflows.py`,
   `tools/stm32-toolkit/src/stm32_toolkit/cli.py`,
   `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`,
   `tools/stm32-toolkit/tests/test_testing_cli.py`,
   `tools/stm32-toolkit/tests/test_testing_mcp.py`, and
   `tools/stm32-toolkit/tests/test_testing_workflows.py`.
7. **T10.7 — Evidence GC public workflows:** dry-run/apply and safe plan/result projections only.
   Paths: `tools/stm32-toolkit/src/stm32_toolkit/testing_workflows.py`,
   `tools/stm32-toolkit/src/stm32_toolkit/cli.py`,
   `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`,
   `tools/stm32-toolkit/tests/test_testing_cli.py`,
   `tools/stm32-toolkit/tests/test_testing_mcp.py`, and
   `tools/stm32-toolkit/tests/test_testing_workflows.py`.
8. **T10.8 — Test-run Evidence publication bridge:** immutable Host/Target result publication only;
   no execution. Paths: `tools/stm32-toolkit/src/stm32_toolkit/testing/publication.py`,
   `tools/stm32-toolkit/src/stm32_toolkit/testing/__init__.py`, and
   `tools/stm32-toolkit/tests/test_testing_publication.py`.
9. **T10.9 — Host discover/run public workflows:** Host execution and delegation to the accepted
   publisher; `testing/host.py` is not modified. Paths:
   `tools/stm32-toolkit/src/stm32_toolkit/testing_workflows.py`,
   `tools/stm32-toolkit/src/stm32_toolkit/cli.py`,
   `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`,
   `tools/stm32-toolkit/tests/test_testing_cli.py`,
   `tools/stm32-toolkit/tests/test_testing_mcp.py`, and
   `tools/stm32-toolkit/tests/test_testing_workflows.py`.
10. **T10.10 — Test show public workflow:** mode-neutral authoritative read/summary and no
    execution. Paths: `tools/stm32-toolkit/src/stm32_toolkit/testing_workflows.py`,
    `tools/stm32-toolkit/src/stm32_toolkit/cli.py`,
    `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`,
    `tools/stm32-toolkit/tests/test_testing_cli.py`,
    `tools/stm32-toolkit/tests/test_testing_mcp.py`, and
    `tools/stm32-toolkit/tests/test_testing_workflows.py`.
11. **T10.11 — Verified Target support provider:** section 6.5 provenance only; tests construct
    temporary roots and no tracked support fixture is allowed. Paths:
    `tools/stm32-toolkit/src/stm32_toolkit/testing/target_support.py`,
    `tools/stm32-toolkit/src/stm32_toolkit/testing/__init__.py`, and
    `tools/stm32-toolkit/tests/test_target_support.py`.
12. **T10.12 — Target prepared-handle rehydration:** `load_prepared` only. Paths:
    `tools/stm32-toolkit/src/stm32_toolkit/testing/target.py`,
    `tools/stm32-toolkit/src/stm32_toolkit/testing/__init__.py`, and
    `tools/stm32-toolkit/tests/test_target_runner.py`.
13. **T10.13 — Target discover public workflow:** support composition and observation only; no
    authorization/flash or lower-level Target/Probe edit. Paths:
    `tools/stm32-toolkit/src/stm32_toolkit/testing_workflows.py`,
    `tools/stm32-toolkit/src/stm32_toolkit/cli.py`,
    `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`,
    `tools/stm32-toolkit/tests/test_testing_cli.py`,
    `tools/stm32-toolkit/tests/test_testing_mcp.py`, and
    `tools/stm32-toolkit/tests/test_testing_workflows.py`.
14. **T10.14 — Target prepare public workflow:** preparation only. Paths:
    `tools/stm32-toolkit/src/stm32_toolkit/testing_workflows.py`,
    `tools/stm32-toolkit/src/stm32_toolkit/cli.py`,
    `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`,
    `tools/stm32-toolkit/tests/test_testing_cli.py`,
    `tools/stm32-toolkit/tests/test_testing_mcp.py`, and
    `tools/stm32-toolkit/tests/test_testing_workflows.py`.
15. **T10.15 — Target execute public workflow:** exact authorized run plus delegation to the
    accepted publisher only. Paths:
    `tools/stm32-toolkit/src/stm32_toolkit/testing_workflows.py`,
    `tools/stm32-toolkit/src/stm32_toolkit/cli.py`,
    `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`,
    `tools/stm32-toolkit/tests/test_testing_cli.py`,
    `tools/stm32-toolkit/tests/test_testing_mcp.py`, and
    `tools/stm32-toolkit/tests/test_testing_workflows.py`.
16. **T10.16 — `test-firmware` Skill:** thin MCP delegation and interpretation only. Paths:
    `skills/test-firmware/SKILL.md` and
    `tools/stm32-toolkit/tests/test_plugin_layout.py`.

Each prerequisite and numbered unit is a separate branch-local commit and review verdict. T10.P1,
T10.P2, and T10.P3 run in that order; T10.1 uses the accepted T10.P3 head as its base. If a unit reveals a
reproducible defect in a frozen lower-level contract, work stops for a separately scoped owner-domain
fix; the public adapter is not enlarged to hide it.

## 10. Explicit non-goals

- no new authoritative Evidence envelope/root/GC, Test, or Probe schema/protocol version; derived
  `stm32-evidence-catalog-state/1` is private cache coordination introduced only by T10.3, and
  `stm32-target-support/1` is non-wire provenance introduced only by T10.11;
- no second CLI executable or module-specific release controller;
- no reusable, wildcard, implicit, cached, or model-inferred authorization;
- no arbitrary Evidence root, SQL, native command, environment, or transport override;
- no new transport, hardware controller, retry engine, recovery journal, ACL, remote service, or
  theoretical same-user rollback protection;
- no real probe, board, UART, semihosting, network, push, PR, merge, or release action;
- no version promotion to 0.6.0 in Task 10.

## 11. Completion criteria

Task 10 is complete only when all three prerequisite corrections and all sixteen numbered units are
independently accepted, the complete cumulative
CLI/MCP/Skill affected matrix passes on Python 3.10 and 3.12, every changed product file has at least
90% branch coverage, the plugin inventory contains the thin Skill, all prior release suites remain
green, the tracked worktree is clean, and no hardware/network/remote access occurred. Completion of
Task 10 does not claim 0601, 0602, 0603, or v0.6.0 completion.
