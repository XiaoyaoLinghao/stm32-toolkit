# STM32TK-0601 Test and Evidence Design

**Status:** Approved module design baseline
**Date:** 2026-08-14
**Module:** `STM32TK-0601-TEST-EVIDENCE`
**Accepted base:** `bb6bc5e9ee937e4ce53996b31f25bf1109ffe13f` (`v0.5.0`)
**Specification owner:** Codex
**Implementation owner:** Codex in the separately authorized 0.6 development conversation
**Review and acceptance owner:** Codex
**Remote actions authorized by this document:** none

## 1. Objective

After the acceptance-feasibility phase proves every external dependency, build the immutable
evidence foundation and the complete Host/Target testing surface before diagnostic or analytics
work begins. This module makes the gate schema, stable gate families, evidence contract, and 0601
exact gates executable; later modules add their exact commands/nodes only inside reserved families
before their own candidates.

The module is complete only when Project Schema v3, evidence persistence, deterministic
Host tests, four Target transports, CLI/MCP surfaces, and all quick/candidate/final gate
controllers are implemented and pass the 0601 candidate matrix.

## 2. Scope

### 2.1 Included

- `stm32-evidence/1` envelopes, artifacts, content-addressed storage, catalog rebuild, and GC;
- Project Schema v3 test configuration and explicit v2-to-v3 upgrade;
- `stm32-test/1` Host and Target run events and manifests;
- CTest discovery/execution without an ambient shell;
- memory-mailbox, RTT, UART, and semihosting Target transports;
- Probe protocol v2 schema frozen in full, with the testing transport subset implemented;
- CLI, MCP, and a thin `test-firmware` Skill;
- frozen gate schema/families, exact 0601 catalog/nodes, and self-tested matrix controllers;
- module coverage, performance, security, isolation, offline-install, and real-board evidence.

### 2.2 Excluded

- hypotheses, debug stepping, breakpoints, and fix verification, owned by 0602;
- cross-run Monitor analytics and annotations, owned by 0603;
- automatic generation of firmware-side test harnesses;
- arbitrary executable strings, shell scripts, remote runners, and cloud test services;
- claiming a transport supported from a simulator-only result.

## 3. Source layout and ownership

The implementation adds these product areas. Root schemas and packaged schemas must be
byte-identical.

```text
schemas/
├── evidence-envelope.schema.json
├── stm32-project.schema.json          # becomes v3
├── stm32-test.schema.json
└── probe-protocol.schema.json         # becomes complete v2 contract

tools/stm32-toolkit/src/stm32_toolkit/
├── evidence/{__init__,model,store,catalog,gc}.py
├── testing/
│   ├── {__init__,model,protocol,host,target,artifacts}.py
│   └── transports/{__init__,base,mailbox,rtt,uart,semihosting}.py
├── schemas/                            # packaged schema mirrors
├── project_model.py
├── project_upgrade.py
├── cli.py
└── mcp_server.py

skills/test-firmware/SKILL.md
tools/release/{gates_0600.json,run_0600_quick.ps1,
               run_0600_quick.sh,run_0600_candidate.ps1,
               run_0600_candidate.sh,run_0600_final.ps1,
               run_0600_final.sh,run_0600_gates.py,
               performance_0600.json,verify_0600_release.py}
```

Tests mirror each package under `tools/stm32-toolkit/tests/`; release-controller tests are
kept in `tools/stm32-toolkit/tests/release/` and are always run without product coverage.

## 4. Evidence model

### 4.1 Identity and envelope

The module implements the program-level `EvidenceIdentity`, `ArtifactRef`, and
`EvidenceEnvelope` exactly. `evidence_id` is the lowercase SHA-256 of canonical UTF-8 JSON
containing the envelope with `evidence_id` omitted. Canonical JSON uses sorted keys, no
insignificant whitespace, NFC strings, and rejects NaN, infinity, duplicate keys, booleans
where integers are expected, and unknown fields.

Limits are fixed:

| Item | Limit |
|---|---:|
| Envelope JSON | 1 MiB |
| JSON nesting | 32 |
| Total JSON nodes | 100,000 |
| A string | 64 KiB |
| Parents per envelope | 64 |
| Artifacts per envelope | 4,096 |
| One artifact | 2 GiB |
| Relative path | 512 UTF-8 bytes |

`produced_at_utc` uses `YYYY-MM-DDTHH:MM:SS.ffffffZ`. Workspace IDs are stable hashes of
canonical workspace roots plus repository identity; logical project IDs come from Project
Schema v3 rather than directory names. Git dirty state and the input snapshot digest are
both mandatory so uncommitted inputs cannot masquerade as a clean build.

For Host runs, `build_id` is the canonical digest of the CMake build/test inventory,
`elf_sha256` is the canonical digest of the ordered Host test executable inventory, and
`target_device` is `host:<os>/<architecture>`. These are 64-digit lowercase hashes where
the common model requires hashes; empty strings and dummy firmware identities are invalid.
Target runs use the actual firmware build ID, ELF digest, and MCU identity.

### 4.2 Artifact ingestion

`EvidenceStore.ingest_file(source, kind, media_type)`:

1. opens the source without following links;
2. hashes and copies it to a same-directory temporary object;
3. flushes and fsyncs;
4. atomically publishes it at `objects/sha256/<prefix>/<digest>`;
5. reopens and rehashes the published object;
6. returns an immutable `ArtifactRef`.

An existing object is reused only after byte count and digest verification. No artifact path
may contain a drive, root, `..`, empty segment, backslash, control character, alternate data
stream, Windows reserved name, trailing dot/space, or case-fold collision. Every ancestor is
checked for links/reparse points. Hard-link count must be one for managed mutable metadata;
objects are opened read-only and never edited in place.

### 4.3 Manifests and catalog

`put_envelope()` validates all referenced objects before atomic manifest publication.
`get_envelope()` validates schema, canonical bytes, ID, paths, object sizes, and hashes on
every authoritative read. `catalog.sqlite3` contains only derived search fields and is never
accepted as evidence. `rebuild_catalog()` scans verified manifests in deterministic name
order into a new database and atomically replaces the old database.

Catalog queries support exact workspace, project, session, build, ELF, operation, and UTC
range filters with explicit limits from 1 through 1,000. Results are ordered by
`produced_at_utc, evidence_id`; no raw SQL or wildcard path query is public. A query returns
explicitly non-authoritative `EvidenceSummary` rows from the derived catalog and does not rehash
artifact objects. Any caller that acts on a row must call `get_envelope(evidence_id)`, which
performs the authoritative manifest/object verification. Catalog performance gates measure only
summary search; evidence verification has a separate end-to-end workload.

### 4.4 Garbage collection

`plan_gc()` returns a canonical manifest containing roots, reachable objects, unreachable
known objects, unknown entries, corrupt entries, bytes reclaimable, and a plan digest.
`apply_gc(plan, authorized, expected_plan_digest)` requires exact digest authorization and
refuses if the store changed since planning. It removes only verified unreachable known
objects. Unknown, corrupt, linked, or currently referenced entries are reported and retained.

## 5. Project Schema v3

Schema v3 retains every v2 field and adds an optional `testing` object:

```yaml
schema_version: 3
testing:
  host:
    ctest_preset: host-tests
    labels: [unit]
    timeout_seconds: 120
    environment:
      allow: [STM32TK_TEST_SEED]
      values: {STM32TK_TEST_SEED: "1"}
  target:
    executable: build/test/firmware-tests.elf
    timeout_seconds: 120
    transport:
      kind: memory-mailbox
      options: {address: 536936448, size: 4096}
```

Host configuration accepts one CTest preset, exact labels, 1--3,600 second timeout, a
32-name environment allowlist, and literal values up to 4 KiB each. It never accepts a shell
command. Target configuration accepts a workspace-relative ELF, one transport, and typed
transport options. Numeric addresses and baud rates are integers, not strings.

`upgrade_project_v2_to_v3()` adds `schema_version: 3` and no `testing` block, preserving all
comments/order supported by the existing upgrader. Dry-run returns the exact candidate and
diff; apply requires the existing modification authorization and an unchanged source digest.
Writers emit v3. Readers accept only v2 and v3 after 0601; v1 still follows the existing
explicit upgrade route and is never silently rewritten.

## 6. Test protocol

### 6.1 Run model

The schema identifier is `stm32-test/1`. A `TestRunManifest` has:

```python
@dataclass(frozen=True)
class TestRunManifest:
    schema: Literal["stm32-test/1"]
    run_id: str
    mode: Literal["host", "target"]
    state: Literal["discovered", "running", "passed", "failed", "error", "cancelled"]
    identity: EvidenceIdentity
    transport: str | None
    cases: tuple[TestCaseResult, ...]
    started_at_utc: str
    ended_at_utc: str
    duration_ms: int
    stdout: ArtifactRef | None
    stderr: ArtifactRef | None
    raw_events: ArtifactRef
```

Case IDs are stable discovered identifiers. Case states are `passed`, `failed`, `skipped`,
`error`, or `timeout`. The parser requires one start and one terminal result per started case,
rejects duplicate IDs and illegal state transitions, and records incomplete cases as errors.
An empty discovered inventory is `TEST_NO_CASES`, not PASS. Process exit zero cannot override
a failed/error/timeout case; a nonzero exit cannot be converted to PASS by event content.

### 6.2 Host tests

Host discovery executes:

```text
cmake --build --preset <preset>
ctest --preset <preset> --show-only=json-v1
```

Execution uses CTest's list-form process API with an allowlisted environment and an external
temporary results directory. It selects exact discovered test IDs, asks CTest for JUnit XML,
and ingests discovery JSON, JUnit, stdout, and stderr. Requested IDs not present in the frozen
discovery inventory fail `TEST_CASE_NOT_FOUND`. A changed inventory digest between discovery
and run fails `TEST_INVENTORY_CHANGED`.

### 6.3 Target event framing

All Target transports carry identical binary frames:

```text
magic "ST32" | version u8=1 | kind u8 | flags u16 | sequence u32
payload_length u32 | payload UTF-8 JSON | crc32 u32
```

Maximum payload is 16 KiB and maximum run stream is 64 MiB. Sequences start at zero and are
strictly increasing. The decoder recovers only at a valid magic/version/length/CRC boundary,
records discarded bytes, rejects oversize frames before allocation, and never decodes partial
UTF-8. A terminal `run_end` binds the inventory digest, build ID, ELF digest, target ID, counts,
and event-stream digest.

### 6.4 Transports

All transports implement:

```python
class TargetTransport(Protocol):
    def open(self, config: Mapping[str, object], deadline: float) -> None: ...
    def read(self, max_bytes: int, deadline: float) -> bytes: ...
    def close(self) -> None: ...
    def identity(self) -> Mapping[str, str]: ...
```

- **Memory mailbox:** Probe Service reads a fixed RAM ring header and data region. Address and
  size must be inside the declared MCU RAM map; producer/consumer counters are bounded and
  wrap-safe. The host never writes target memory.
- **RTT:** Probe backend opens channel 0 by default, accepts channels 0--15, and records control
  block address and probe identity. It does not auto-scan outside declared RAM.
- **UART:** `pyserial` opens an exact named port, 115200 default baud, 8N1, no flow control.
  Allowed baud values are enumerated. The port name is recorded but authorization data is not.
- **Semihosting:** Probe backend captures stdout from an exact launched ELF/debug session into
  bounded chunks. It must not expose arbitrary host file operations requested by firmware.

Each transport has parser unit fixtures, byte-fragmentation/property tests, recorded replay,
fake-backend integration, disconnect/timeout tests, and a named real-board acceptance run.
`TEST_TRANSPORT_UNAVAILABLE` is an honest terminal error, never a skipped PASS.

### 6.5 Target execution safety

Every Target run is `MODIFY`. Its action digest binds workspace, project, target, probe serial,
ELF path and SHA-256, build ID, transport configuration, requested cases, timeout, and expected
project revision. The runner verifies the digest, flashes only through the existing guarded
workflow, re-reads target identity, then starts capture. Authorization expires after that one
run and cannot cover a retry or another transport.

## 7. Probe protocol v2 boundary

After feasibility proves the named backend supports required target transport and debug
primitives, 0601 freezes the complete `stm32-toolkit-probe/2` JSON schema so 0602 cannot add an
unreviewed command during implementation. 0601 implements testing operations:

- `target.transport.open`, `target.transport.read`, `target.transport.close`;
- `target.identity.read`;
- existing lease, flash, read, sample, and Fault operations ported without semantic change.

The v2 schema also reserves and fully types 0602 operations for halt/resume/step, temporary
breakpoints, registers, bounded memory reads, and debug/log capture. Until 0602 implements
them, the service returns `PROBE_OPERATION_UNAVAILABLE`; it does not accept unknown arguments.
Protocol v1 and v2 are not mixed within one process. A version mismatch fails before a probe
lease or hardware session is opened.

## 8. CLI, MCP, and Skill

CLI commands:

```text
stm32 evidence verify <evidence-id>
stm32 evidence list [typed filters]
stm32 evidence gc --dry-run
stm32 test discover --mode host|target
stm32 test run --mode host|target [--case exact-id ...]
stm32 test show <run-id>
```

MCP tools expose the same typed operations and return the existing `OperationResult` envelope.
Large logs return verified artifact references, not inline unbounded content. `test-firmware`
explains strategy, requests exact MODIFY authorization for Target runs, and delegates only to
the deterministic MCP tools. It contains no subprocess recipe or implicit authorization.

Error codes include `EVIDENCE_INVALID`, `EVIDENCE_CORRUPT`, `EVIDENCE_PATH_UNSAFE`,
`EVIDENCE_LIMIT_EXCEEDED`, `TEST_NO_CASES`, `TEST_CASE_NOT_FOUND`,
`TEST_INVENTORY_CHANGED`, `TEST_PROTOCOL_INVALID`, `TEST_TIMEOUT`,
`TEST_TRANSPORT_UNAVAILABLE`, and existing authorization/identity errors.

## 9. Acceptance framework

`gates_0600.json` is a schema-validated, stable-family catalog. Each entry names phase, module,
matrix memberships, owner, platform, command argv, working directory, required tools and exact
versions, timeout, evidence files, node inventory source, coverage context, and prerequisites.
0601 freezes the schema/families and its own exact entries/nodes. Reserved 0602/0603 families
declare their purpose, owner role, platform, evidence type, and matrix placement without fictional
commands or nodes. Each module freezes its performance workload/design maximum before the measured
hot path, then freezes the accepted calibration after the correct implementation is within that
maximum and before optional post-baseline optimization. It replaces only its reserved entries with
complete exact commands and node inventories after all its tests exist and before candidate. The
final digest freezes at the 0603 candidate CodeHead.

Controllers must:

- verify the complete support root against a frozen relative-path/bytes/SHA-256 manifest before
  execution, rejecting missing/extra/case-fold-colliding/link/reparse/special entries, and treat
  Node/npm/Python/browser/wheelhouse caches as read-only inputs;
- create an external evidence root and one log/result file per gate;
- capture UTC, OS/architecture, absolute executable/version, cwd, argv, exit, duration, bytes,
  SHA-256, and the frozen CodeHead;
- run independent quick/candidate partitions even after another partition fails;
- honor catalog resource locks for reference-performance host, board, probe, UART, ports, and
  evidence roots; parallelize only disjoint resources;
- enforce dependency ordering without treating blocked dependents as PASS;
- reject missing/extra/duplicate gate IDs and missing retained evidence;
- prove each frozen test node is selected and executed exactly once, with no unexpected skip,
  deselection, xfail, or duplicate result;
- force product frameworks to zero hidden retries and record a deterministic seed; retryable
  infrastructure recovery is owned only by the top-level candidate/final controller;
- exclude controller subprocesses from product coverage;
- verify the worktree is clean before and after every product gate;
- perform no network or remote Git operation.

Readiness runs no product test body. It proves exact CodeHead, complete final catalog/nodes,
dependency locks, support manifests, empty evidence roots, tool versions, assigned owners,
hardware identity/connectivity, disk/power state, and controller self-tests. The final controller
is fail-fast within each platform shard and implements only the program's bounded
`RECOVERABLE_INFRA_ERROR` checkpoint/resume policy.

Candidate uses the same enumerated external-event classification and one affected-shard resume at
the same candidate run ID; it never silently reruns a product node or combines different run IDs.
A deterministic candidate failure requires a repository correction/new CodeHead, while a repeated
external interruption is BLOCKED rather than mislabeled as a product failure.

Every candidate/final shard produces a deterministic portable ZIP plus a canonical inner manifest.
Sorted relative members, normalized metadata, package/member bytes and SHA-256, closed owner/
platform/run/CodeHead/catalog/lock/support bindings, and absence of credentials/absolute private
paths are verifier-enforced. A named owner transfers non-aggregator packages through the user-
designated evidence channel; controller code never opens a network or remote Git connection.

Offline dependency audit is deterministic: the support manifest pins the advisory snapshot and
npm cache digests; production dependencies require zero vulnerabilities at every severity,
preserving 0.5; development dependencies require zero high/critical vulnerabilities. Any
exception must be user-approved and committed before the affected module candidate, with package,
advisory ID, reachability, expiry, and mitigation. Network audit results are never release evidence.
The advisory snapshot records source, database/version, generated UTC, and digest and must be no
older than seven calendar days at candidate/final readiness. A named support owner may refresh only
that external manifest segment before readiness; controllers stay offline, and the candidate/final
binds the refreshed digest. Refreshing product dependencies or lockfiles still creates a CodeHead.

## 10. Test and quality contract

### 10.1 Automated partitions

1. model/schema canonicalization and malformed input limits;
2. store path/link/casefold/atomicity/corruption/concurrency/fault injection;
3. catalog rebuild and GC reachability/change-after-plan;
4. Project v2/v3 read/write/dry-run/apply/rollback;
5. Host discovery, exact selection, env isolation, timeout/process-tree cleanup, artifacts;
6. Target frame parser fuzz/property/replay/state machine;
7. all four transport fake integration and failure cleanup;
8. Probe v2 schema/version/unknown-field/backpressure/lease isolation;
9. CLI/MCP exact results, bounded responses, cross-workspace isolation;
10. release-controller contract and evidence-verifier mutation tests;
11. offline build/install/smoke on CPython 3.10 and 3.12;
12. real-board transport matrix.

Every changed product Python file must have at least 90% branch coverage in its owning shard.
Coverage is measured separately for Toolkit product code, Probe product code, and schema/CLI
adapters. The development coverage runner discovers changed/untracked product files relative to
the current `HEAD`, emits external branch JSON, and validates integer branch counts for each file;
an aggregate percentage cannot mask a file below 90%. It rejects missing/duplicate/case-folded rows
and changed product paths absent from coverage output. Controller/helper tests run with coverage disabled and cannot raise
these totals.

### 10.2 Performance

The program calibration method is mandatory on the named reference host under 3.10 and 3.12.
The following are end-to-end design maxima, not already-calibrated thresholds:

| Operation | Dataset | Design maximum |
|---|---|---:|
| publish and authoritatively reload evidence | 1 MiB total, 32 artifacts | p95 500 ms |
| list derived evidence summaries | 10,000 manifests, return 100 | p95 500 ms |
| decode stream and publish Target manifest | 10 MiB fragmented stream | 3 s |
| verify manifests and rebuild catalog | 10,000 manifests | 10 s |

The correct straightforward implementation is provisionally characterized first. If a calculated
threshold exceeds a maximum, improve the implementation without changing workload or maximum and
repeat the characterization. Only a within-maximum result becomes the accepted calibration in
`performance_0600.json`; it freezes before optional post-baseline optimization and candidate.
Internal object-copy, canonical-JSON, SQLite, and decoder microbenchmarks are retained as diagnostic
facts rather than independent release blockers. Performance runs exclude coverage and record
antivirus/exclusion state rather than assuming it.

### 10.3 Real-board matrix

One named supported reference target must provide independent PASS evidence for memory mailbox,
RTT, UART, and semihosting. Every run records board identifier, MCU, probe serial hash, firmware
ELF digest, build ID, exact transport config, discovered/captured cases, raw event artifact, and
terminal counts. Fake backend evidence remains a separate gate and cannot own this result.

## 11. Candidate matrix and exit criteria

After the exact 0601 inventory commit, a non-executing candidate precheck verifies CodeHead,
catalog/nodes, support, tools, owners, hardware, and empty evidence roots. The unchanged CodeHead's
collect-all candidate matrix includes:

- whole accepted-base ancestry, diff, scope, source-hash, and clean-tree audit;
- Windows and Linux, CPython 3.10/3.12 Toolkit shards;
- schema mirror and package inventory;
- product branch coverage at or above 90%;
- performance thresholds under both Python versions;
- offline wheel build/install and managed launcher smoke;
- controller/verifier self-tests including intentional failure and bounded infrastructure-recovery
  fixtures;
- two-workspace concurrent isolation;
- four real-board transports;
- all applicable 0.5 regression gates.

The tracked implementation report is written only after overall PASS and is a report-only
child commit. It lists the product CodeHead, complete gate evidence inventory, bytes/SHA-256,
owners, tools, commands, UTC, platform, and no moving commit count. That report commit becomes
the accepted base for 0602.

## 12. Completion conditions

0601 succeeds when all of the following are true:

1. Evidence can be created, reloaded, verified, indexed, rebuilt, and safely collected.
2. Project v3 is the only emitted schema and v2 upgrades are explicit and reversible.
3. Host tests run only discovered exact IDs through argv-safe CTest execution.
4. Target tests produce identical verified semantics through all four real transports.
5. Every Target operation binds one MODIFY authorization to exact firmware and target identity.
6. Probe v2's complete schema, the gate schema/families, and exact 0601 gates/nodes are frozen;
   later module entries remain reserved rather than fabricated.
7. Coverage, performance, platform, offline-install, integrity, and isolation gates pass.
8. A report-only commit records the accepted 0601 CodeHead without changing product files.
