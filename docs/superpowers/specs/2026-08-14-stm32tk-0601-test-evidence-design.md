# STM32TK-0601 Test and Evidence Design

**Status:** Approved module design baseline
**Date:** 2026-08-14
**Module:** `STM32TK-0601-TEST-EVIDENCE`
**Accepted base:** `bb6bc5e9ee937e4ce53996b31f25bf1109ffe13f` (`v0.5.0`)
**Specification owner:** Codex
**Implementation owner:** Codex and its local derived agents under the permanent project policy
**Review and acceptance owner:** Codex
**Remote actions authorized by this document:** none

## 1. Objective

After a Windows-only non-hardware feasibility phase proves the software tools, managed Chromium,
and support fixture,
build the immutable evidence foundation and the complete Host/Target testing surface before
diagnostic or analytics work begins. The feasibility verifier and gate-controller contract are
acceptance infrastructure and may be implemented before that feasibility PASS; product Tasks 3--12
may start after it. Real-board feasibility is not a product-coding prerequisite. This module makes
the gate schema, stable gate families, evidence contract, and 0601 exact gates executable; later
modules add their exact commands/nodes only inside reserved families before their own candidates.

The module reaches `SOFTWARE_COMPLETE_HARDWARE_PENDING` when Project Schema v3, evidence
persistence, deterministic Host tests, all four Target transport implementations, CLI/MCP
surfaces, and all quick/candidate/final gate controllers pass the Windows-only 0601 software
candidate matrix. Final `v0.6.0` acceptance additionally requires both `0400` and `0600` hardware
contracts, including all four real transports and the diagnostic chain, to PASS in the unified
0.4+0.6 hardware activity after the 0603 Candidate.

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
- module coverage, performance, security, isolation, and offline-install evidence;
- fake-backend, replay, and capability-contract coverage for all four Target transports;
- deferred real-board gates and evidence contracts for the post-0603 unified 0.4+0.6 activity.

### 2.2 Excluded

- hypotheses, debug stepping, breakpoints, and fix verification, owned by 0602;
- cross-run Monitor analytics and annotations, owned by 0603;
- automatic generation of firmware-side test harnesses;
- arbitrary executable strings, shell scripts, remote runners, and cloud test services;
- claiming a transport supported from a simulator-only result.
- Linux support, Linux owners, Linux browser gates, Linux shards, cross-machine evidence transfer,
  and Linux release claims; Linux is a separate later development effort.

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
               run_0600_candidate.ps1,run_0600_final.ps1,run_0600_hardware.ps1,
               path_contract_0600.ps1,run_0600_gates.py,
               performance_0600.json,verify_0600_release.py}
```

Tests mirror each package under `tools/stm32-toolkit/tests/`; release-controller tests are
kept in `tools/stm32-toolkit/tests/release/` and are always run without product coverage.

## 4. Evidence model

### 4.1 Identity and envelope

The module implements the program-level `EvidenceIdentity`, `ArtifactRef`, and
`EvidenceEnvelope` exactly. `evidence_id` is the lowercase SHA-256 of canonical UTF-8 JSON
containing the envelope with `evidence_id` omitted. Canonical JSON is UTF-8 without a BOM, uses
NFC-normalized strings, sorts object keys by Unicode code point, preserves contract-defined array
order, and uses `,` and `:` with no surrounding whitespace. It emits only JSON `true`, `false`,
and `null` literals and contract-bounded base-10 integers; floats and exponent form are forbidden.
Decoders reject non-canonical authoritative bytes, NaN, infinity, duplicate keys, booleans where
integers are expected, and unknown fields.

The closed records are:

| Record | Exact fields |
|---|---|
| `EvidenceIdentity` | `workspace_id`, `project_id`, `session_id`, `build_id`, `elf_sha256`, `target_device`, `input_snapshot_sha256`, `git_commit`, `git_dirty` |
| `ArtifactRef` | `sha256`, `size_bytes`, `relative_path`, `kind`, `media_type` |
| `EvidenceEnvelope` | `schema="stm32-evidence/1"`, `evidence_id`, `identity`, `operation`, `produced_at_utc`, `parents`, `artifacts`, `metadata` |

IDs and hashes are lowercase ASCII; `operation`, artifact `kind`, and media type are bounded
non-empty strings; parents and artifacts are tuples whose order is significant; `metadata` is a
closed canonical JSON object defined by the producing operation's schema. No record accepts an
extension field.

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

`plan_gc()` returns a canonical manifest containing typed roots, reachable objects, unreachable
known objects, unknown entries, corrupt entries, bytes reclaimable, and a plan digest. Every root
record has exactly `root_type`, `root_id`, `manifest_id`, and canonical `metadata`. The registry
defines `test-run`, `diagnostic-session`, `bundle`, and `annotation` root types in 0601 even when
later modules have not produced them. An unknown or malformed root is reported and retained
conservatively, never ignored or collected.
`apply_gc(plan, authorized, expected_plan_digest)` uses the common MODIFY prepare/execute contract:
`authorized` is a single-use authorization token whose action digest binds the workspace/store ID,
plan digest, manifest snapshot digest, and bytes reclaimable. It requires an exact
`expected_plan_digest`,
refuses if the store changed since planning. It removes only verified unreachable known
objects. Unknown, corrupt, linked, or currently referenced entries are reported and retained.

## 5. Project Schema v3

Schema v3 retains every v2 field and adds an optional `testing` object:

```yaml
schema_version: 3
testing:
  host:
    buildPreset: host-build
    ctestPreset: host-tests
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

External Project Schema v3 uses distinct required `buildPreset` and `ctestPreset` fields; Python
models expose them as `build_preset` and `ctest_preset`. They may have the same value but are never
inferred from each other. Host configuration accepts one build preset, one CTest preset, exact
labels, 1--3,600 second timeout, a
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

`TestCaseResult` has exactly `case_id`, `state`, `started_at_utc`, `ended_at_utc`, `duration_ms`,
`message`, `stdout`, and `stderr`; the last three are nullable and stdout/stderr are `ArtifactRef`s.
`TestInventory` has exactly `mode`, `identity`, `case_ids`, `inventory_digest`, and
`discovered_at_utc`; case IDs are unique, sorted by UTF-8 byte order before hashing, and preserved
in that order. Target event payload objects use only the fields needed to populate these records
plus the identity/count/digest bindings explicitly required by `run_end`; each kind has a closed
schema in `stm32-test.schema.json`.

### 6.2 Host tests

Host discovery executes using the two separately configured preset names:

```text
cmake --build --preset <buildPreset>
ctest --preset <ctestPreset> --show-only=json-v1
```

Execution uses CTest's list-form process API with an allowlisted environment and an external
temporary results directory. It selects exact discovered test IDs, asks CTest for JUnit XML,
and ingests discovery JSON, JUnit, stdout, and stderr. Requested IDs not present in the frozen
discovery inventory fail `TEST_CASE_NOT_FOUND`. A changed inventory digest between discovery
and run fails `TEST_INVENTORY_CHANGED`.

Target discovery is a read-only handshake over the selected transport. It may open/read/close an
already-running target session and obtain its inventory header, but it may not reset, halt, flash,
write target memory, or consume a MODIFY authorization. If the target is not already running the
exact configured firmware, it returns `TEST_TRANSPORT_UNAVAILABLE`. A later Target run freezes the
discovered inventory digest in its single-use action digest.

### 6.3 Target event framing

All Target transports carry identical binary frames. Every multibyte integer is unsigned
little-endian. CRC is CRC-32/ISO-HDLC (polynomial `0x04C11DB7`, reflected polynomial
`0xEDB88320`, init `0xFFFFFFFF`, refin/refout true, xorout `0xFFFFFFFF`) over the complete header
through payload, excluding the CRC field itself:

```text
magic "ST32" | version u8=1 | kind u8 | flags u16 | sequence u32
payload_length u32 | payload UTF-8 JSON | crc32 u32
```

Maximum payload is 16 KiB and maximum run stream is 64 MiB. Sequences start at zero and are
strictly increasing. The decoder recovers only at a valid magic/version/length/CRC boundary,
records discarded bytes, rejects oversize frames before allocation, and never decodes partial
UTF-8. A terminal `run_end` binds the inventory digest, build ID, ELF digest, target ID, counts,
and event-stream digest.

Kind values are frozen as `1=inventory`, `2=run_start`, `3=case_start`, `4=case_result`,
`5=run_end`, and `6=log`; every other kind and every nonzero flags bit are invalid in version 1.
Golden fixtures contain one frame of each kind plus byte-fragmented, CRC-corrupt, truncated,
oversize, invalid-UTF-8, and invalid-sequence streams; tests bind their exact bytes and SHA-256.

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
  Allowed baud values are exactly 9,600, 19,200, 38,400, 57,600, 115,200, 230,400, 460,800,
  and 921,600. The port name is recorded but authorization data is not.
- **Semihosting:** Probe backend captures stdout from an exact launched ELF/debug session into
  bounded chunks. It must not expose arbitrary host file operations requested by firmware.

Each transport has parser unit fixtures, byte-fragmentation/property tests, recorded replay,
fake-backend integration, disconnect/timeout tests, and a deferred named real-board acceptance run.
`TEST_TRANSPORT_UNAVAILABLE` is an honest terminal error, never a skipped PASS.

The Windows support profile is the sole source of allowed board/MCU identity, RAM regions, mailbox
address/size, RTT channel and optional explicit control-block address, UART port and baud, probe
identity, semihosting capability, and fixture ELF/build/inventory digests. Implementations may not
scan beyond declared RAM, guess ports or baud, or synthesize a capability absent from the profile.

### 6.5 Target execution safety

Every Target run is `MODIFY`. Its action digest binds workspace, project, target, probe serial,
ELF path and SHA-256, build ID, transport configuration, requested cases, timeout, and expected
project revision. The runner verifies the digest, flashes only through the existing guarded
workflow, re-reads target identity, then starts capture. Authorization expires after that one
run and cannot cover a retry or another transport. This contract is implemented and fake-tested in
0601; each real use is authorized separately when the post-0603 hardware activity executes.

## 7. Probe protocol v2 boundary

After Windows software/tool feasibility passes, 0601 freezes the complete
`stm32-toolkit-probe/2` JSON schema against the full accepted 0602 requirements so 0602 cannot add
an unreviewed command during implementation. Hardware capability is validated later and does not
block this schema work. 0601 implements these closed `OBSERVE` testing operations:

| Operation | Exact operation arguments | Exact success result |
|---|---|---|
| `target.transport.open` | `{transport,config,deadline_ms}` | `{transport_id,identity}` |
| `target.transport.read` | `{transport_id,max_bytes,deadline_ms}` | `{data_base64,eof}` |
| `target.transport.close` | `{transport_id}` | `{transport_id,closed:true}` |
| `target.identity.read` | `{}` | `{board_id,mcu,target_id,probe_serial_hash}` |

Transport/config use the closed Project v3 transport unions, `deadline_ms` is 1--300,000,
`max_bytes` is 1--65,536, and `identity` has exactly the same four fields as
`target.identity.read`. These operations do not flash, reset, halt, or write target state. Existing
non-`target.*` lease, flash, read, sample, and Fault operations are ported without semantic change.

The v2 schema also reserves and fully types the following and only the following 0602 Target
operations. Every request is a closed object and carries the existing lease ID and deadline fields
in the common envelope. `OBSERVE` never mutates target state; `CONTROL` requires the existing exact
single-use control authorization:

| Operation | Class | Exact operation arguments | Exact success result |
|---|---|---|---|
| `target.state.read` | `OBSERVE` | `{}` | `{state,reason}` |
| `target.halt` | `CONTROL` | `{}` | `{state:"halted",reason}` |
| `target.resume` | `CONTROL` | `{}` | `{state:"running"}` |
| `target.step` | `CONTROL` | `{}` | `{state:"halted",reason,pc_before,pc_after}` |
| `target.breakpoint.set` | `CONTROL` | `{address,kind:"temporary",size}` | `{breakpoint_id,address,kind:"temporary",size}` |
| `target.breakpoint.clear` | `CONTROL` | `{breakpoint_id}` | `{breakpoint_id,cleared:true}` |
| `target.registers.read` | `OBSERVE` | `{names}` | `{registers:[{name,value,width_bits}]}` |
| `target.memory.read` | `OBSERVE` | `{address,length}` | `{address,length,data_base64,sha256}` |
| `target.fault.capture` | `OBSERVE` | `{max_stack_bytes}` | `{fault_registers,stack_artifact,stack_bytes,truncated}` |
| `target.logs.capture` | `OBSERVE` | `{channel,max_bytes,duration_ms}` | `{channel,artifact,bytes,duration_ms,truncated}` |

`state` is exactly `running`, `halted`, `reset`, or `faulted`; `reason` is exactly `requested`,
`breakpoint`, `watchpoint`, `fault`, `exception`, or `reset`. One `target.step` performs exactly one
instruction step and has a hard 5-second deadline; `pc_before` and `pc_after` are unsigned integers.
Breakpoint size is 1, 2, or 4 bytes and a session may hold at most eight temporary breakpoints.
Register names are 1--64 unique names from the profile allowlist and results preserve request order.
Memory length is 1--4,096 bytes inside a profile-declared readable region. `max_stack_bytes` is
0--4,096; `fault_registers` contains exactly `cfsr`, `hfsr`, `dfsr`, `afsr`, `mmfar`, `bfar`,
`shcsr`, and `icsr`, and `stack_artifact` is a verified `ArtifactRef` or null when zero bytes were
requested. Log channel is exactly `rtt`, `uart`, `semihosting`, `swo`, or `probe`; `max_bytes` is
1--10,485,760 and `duration_ms` is 1--300,000. Addresses, register values, widths, lengths, byte
counts, durations, and program counters are unsigned JSON integers; binary content is canonical
base64 inside the referenced artifact. Until 0602 implements these operations, the service returns
`PROBE_OPERATION_UNAVAILABLE`; it does not accept unknown arguments.
Every `target.*` operation returns either its exact success object above or one common error from
`PROBE_PROTOCOL_INVALID`, `PROBE_VERSION_MISMATCH`, `PROBE_OPERATION_UNAVAILABLE`,
`PROBE_LEASE_INVALID`, `PROBE_AUTHORIZATION_REQUIRED`, `PROBE_AUTHORIZATION_INVALID`,
`PROBE_IDENTITY_MISMATCH`, `PROBE_LIMIT_EXCEEDED`, `PROBE_TIMEOUT`, `PROBE_BACKPRESSURE`, or
`PROBE_BACKEND_ERROR`; error objects have exactly `code`, `message`, and canonical bounded
`details`. No operation-specific ad-hoc error or partial success object is permitted.
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
0601 freezes the schema/families and its own exact entries/nodes. For 0601, a complete catalog
means all 0601 entries and nodes are exact while all 0602/0603 entries remain non-executable
reserved families. Reserved 0602/0603 families
declare their purpose, owner role, platform, evidence type, and matrix placement without fictional
commands or nodes. Each module freezes its performance workload/design maximum before the measured
hot path, then freezes the accepted calibration after the correct implementation is within that
maximum and before optional post-baseline optimization. It replaces only its reserved entries with
complete exact commands and node inventories after all its tests exist and before candidate. The
final digest freezes at the 0603 candidate CodeHead.

The catalog also freezes Windows-only deferred hardware families `HW-0400-DEFERRED`,
`HW-0600-TRANSPORT`, and `HW-0600-DIAGNOSTIC` for contracts `0400` and `0600`. The 0.4 reports
described deferred behaviors but did not assign formal gate IDs, so `0400` introduces these exact
0.6-catalog IDs without pretending they existed historically: `STM32TK-HW-0400-PROBE-ATTACH-READ`,
`STM32TK-HW-0400-FLASH-READBACK`, `STM32TK-HW-0400-HANDOFF-REACQUIRE`,
`STM32TK-HW-0400-TYPED-READ-SAMPLE-FAULT`, and `STM32TK-HW-0400-CLI-MCP-WORKFLOWS`. Each entry
hash-binds the exact historical report paragraphs and preserves their meaning. `0600` has exact
gate IDs `STM32TK-HW-0600-MAILBOX`, `STM32TK-HW-0600-RTT`,
`STM32TK-HW-0600-UART`, `STM32TK-HW-0600-SEMIHOSTING`, and
`STM32TK-HW-0600-DIAGNOSTIC-CHAIN`.
These entries have exact evidence schemas and resource locks but remain non-executable in the 0601
software candidate; the post-0603 hardware activity activates them against its frozen inputs.

Controllers must:

- verify the complete support root against a frozen relative-path/bytes/SHA-256 manifest before
  execution, rejecting missing/extra/case-fold-colliding/link/reparse/special entries, and treat
  Node/npm/Python/managed-Chromium/wheelhouse caches as read-only inputs;
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

The Windows feasibility/support profile contains the managed Chromium executable absolute path,
exact version, and package-tree digest plus a non-product launch proof bound to those three values.
The verifier launches only the managed executable with a blank support-owned page, records exit and
version evidence, and performs no browser product flow. A missing executable, version/digest
mismatch, or failed launch proof fails feasibility. Linux browser evidence and browser product-flow
evidence remain out of scope.

Readiness runs no product test body. It proves exact CodeHead, the module-complete catalog/nodes
defined above, dependency locks, support manifests, empty evidence roots, tool versions, the named
Windows owner, disk/power state, and controller self-tests. The 0601 software readiness does not
require hardware identity or connectivity. The final controller
is fail-fast within each platform shard and implements only the program's bounded
`RECOVERABLE_INFRA_ERROR` checkpoint/resume policy.

The only recoverable event tokens are exactly `HOST_POWER_OR_REBOOT`,
`RUNNER_LOSS_BEFORE_CHILD_RESULT`, `PHYSICAL_USB_OR_PROBE_REMOVAL`, and `TARGET_POWER_LOSS`.
Assertion, security, coverage, performance, timeout, corruption, dependency, capability mismatch,
and product failures are never recoverable. Candidate uses this closed classification and one
affected-shard resume at
the same candidate run ID; it never silently reruns a product node or combines different run IDs.
A deterministic candidate failure requires a repository correction/new CodeHead, while a repeated
external interruption is BLOCKED rather than mislabeled as a product failure.

Every Windows wrapper uses one PowerShell 5.1-compatible canonical-absolute-path helper; newer-
runtime-only fully-qualified-path APIs are forbidden. The helper rejects null/empty/whitespace,
relative, drive-relative (`C:foo`), root-relative
(`\foo` or `/foo`), device/extended/NT aliases (`\\.\`, `\\?\`, `\??\`), and any input containing
`.`/`..` or separator/trailing normalization. It first applies the explicit rejection rules, then
requires `[System.IO.Path]::IsPathRooted`, calls `[System.IO.Path]::GetFullPath`, and requires the
original input to be ordinally identical to that canonical result. Tests run under Windows
PowerShell 5.1 and cover drive, UNC, invalid, alias, normalization, and nonexistent output paths.

The entire program uses one canonical `RecoveryRecord` JSON object with exactly these fields and no
others: `classification`, `event`, `reviewer`, `recorded_at_utc`, `run_kind`, `run_id`, `code_head`,
`checkpoint`, and `interrupted_attempt_digest`. `classification` is exactly
`RECOVERABLE_INFRA_ERROR`; `event` is one of the four tokens above; `run_kind` is exactly one of
`candidate-0601`, `candidate-0602`, `candidate-0603`, `final-windows`, `hardware-0400`, or
`hardware-0600`; `reviewer` is a non-empty stable owner ID; `run_id` is a canonical lowercase
hyphenated UUID (`8-4-4-4-12`); `code_head` is exactly 40 lowercase hex and
`interrupted_attempt_digest` exactly 64;
`recorded_at_utc` uses the program UTC format; and `checkpoint` is a normalized absolute path to the
retained checkpoint. Canonical JSON follows §4.1. Any missing/extra field, other classification,
relative path, mismatched run identity/CodeHead/checkpoint, or unknown event/run kind is invalid.

The candidate wrapper exclusively creates and atomically updates
`<candidateRoot>/candidate-ledger.json`. Its closed canonical schema has exactly `schema:
"stm32-candidate-ledger/1"`, `module:"STM32TK-0601"`, `candidate_run_id`, `expected_code_head`,
`controller_path`, `candidate_root`, `evidence_root`, `catalog_sha256`, `performance_sha256`,
`support_profile_sha256`, `checkpoint`, `state`, `created_at_utc`, and `updated_at_utc`.
`controller_path`, candidate/evidence roots, and non-null checkpoint are normalized absolute paths;
the controller path resolves inside the frozen exact-CodeHead worktree. `state` is exactly
`prepared`, `running`, `passed`, `failed`, or `blocked`; hashes and run identity are immutable after
creation. External orchestration may write only `candidate-invocation-context.json`; it is
non-authoritative input and cannot create, update, replace, or satisfy the wrapper ledger.

Before candidate reconciliation, the verifier derives the frozen worktree only from the validated
wrapper ledger and its fixed controller-relative path, canonicalizes it with the helper above, and
proves: `HEAD` equals `expected_code_head`; `remote.origin.url` equals
`https://github.com/XiaoyaoLinghao/stm32-toolkit.git`; and porcelain status including untracked files
is empty. It then re-derives the candidate controller, release verifier, gate catalog, and
performance catalog from fixed relative paths under that worktree. For each it compares the
worktree bytes to the Git blob committed at the expected CodeHead; it additionally compares catalog
and performance SHA-256 to the wrapper-ledger digests. Only these re-derived paths may execute or be
passed to reconciliation. Executable/config paths from `candidate-invocation-context.json`, other
external context, environment variables, or unverified ledger fields are ignored and rejected if
present.

`verify_0600_release.py` also owns the read-only mode `verify-release-ledger`. Its only arguments are
exactly `--ledger <canonical-absolute-path> --digest <canonical-absolute-path> --software-input
<canonical-absolute-path> --hardware-input <canonical-absolute-path>`; unknown, repeated, relative,
aliased, or non-canonical paths fail. `--digest` must be exactly `<ledger>.sha256`, and each source
input must have an adjacent `<input>.sha256`. The mode derives the repository root only from its own
committed `tools/release/verify_0600_release.py` location. It is side-effect-free, opens no network,
performs no remote Git operation, and dispatches no gate. Before emitting any stdout field it reads
all three JSON files and three sidecars, verifies the canonical UTF-8/no-BOM/NFC/sorted-key/compact-
separator/trailing-LF bytes from §4.1, requires every sidecar to contain exactly its file's 64-
lowercase-hex SHA-256 plus LF, and rereads unchanged bytes. Failure produces no stdout; success
emits only canonical `{"mode":"verify-release-ledger","status":"PASS"}` plus LF.

The `stm32-release-ledger/1` root is recursively closed and has exactly `schema`, `repositoryUrl`,
`programBase`, `0400Product`, `0400Report`, `0601Product`, `0601Report`, `0602Product`, `0602Report`,
`0603Product`, `governance`, `softwareInput`, `hardwareInput`, `hardware`, and `artifacts`. String,
integer, object, and array JSON types are exact: booleans never satisfy integers and no numeric field
accepts a float. `repositoryUrl` is exactly
`https://github.com/XiaoyaoLinghao/stm32-toolkit.git`; `programBase` is exactly
`bb6bc5e9ee937e4ce53996b31f25bf1109ffe13f`; `0400Product` is exactly
`96966c461e7e11bff965027d8d498dd40ea5fd55`; and `0400Report` is exactly
`0ee0a5037b3bd158eea5bd312fce7feaadecbfc6`. Every Git identity is 40 lowercase hex, resolves to a
commit in the derived repository, and satisfies the frozen ancestry/report relationship:
`programBase` is an ancestor of `0601Product`; `0601Report` has sole parent `0601Product` and changes
only `docs/codex/returns/STM32TK-0601-TEST-EVIDENCE/implementation-report.md`; `0601Report` is an
ancestor of `0602Product`; `0602Report` has sole parent `0602Product` and changes only
`docs/codex/returns/STM32TK-0602-DIAGNOSTIC-LOOP/implementation-report.md`; and `0602Report` is an
ancestor of `0603Product`. The historical fixed 0400 commits must resolve but are not reclassified
as a report-only pair.

Every 0600 caller re-derives the verifier as
`<frozen-worktree>/tools/release/verify_0600_release.py`; on the first verifier use and immediately
before every verifier process creation it compares `git rev-parse
<expected-code-head>:tools/release/verify_0600_release.py` with `git hash-object -- <re-derived-
verifier>` and requires identical 40-lowercase-hex blob IDs. No cached first check authorizes a
later call. This caller-side immediately-pre-spawn check owns the guarantee against a complete script
replacement before the interpreter loads it. A script cannot independently attest the bytes from
which its own currently executing code was loaded, so the verifier self-check is not claimed as a
substitute for that caller trust boundary.

After the trusted script has been loaded by the interpreter, its process-entry path repeats the
on-disk blob check against the derived repository's exact clean `HEAD` before the first evidence
read, evidence write, output field, or gate dispatch. Each mode then binds that `HEAD` to its
expected CodeHead, and `verify-release-ledger` requires it to equal `0603Product`. This second check
guarantees only the loaded-trusted-script seam: an on-disk mutation after trusted-code load and
before the first evidence action fails closed with empty stdout and zero gate dispatch. It does not
claim independent resistance to a complete replacement that occurred before script load.

`governance` is closed with exactly `specification_owner`, `implementation_owner`, `reviewer`,
`windows_evidence_owner`, `hardware_evidence_owner`, `remote_state`, `remote_actions`, and
`bounded_overrides`. The owner constants are respectively `Codex`, `Codex/local derived agents`,
`Codex`, `Codex`, and `user`. `remote_state` is a non-empty NFC string of at most 256 UTF-8 bytes;
`remote_actions` and `bounded_overrides` are arrays of unique, non-empty NFC strings of at most 256
UTF-8 bytes, sorted by UTF-8 bytes. No object, number, boolean, null, placeholder, or inferred
authorization is accepted in those fields.

`softwareInput` and `hardwareInput` are the only two source references. Each is closed with exactly
`path`, `bytes`, and `sha256`: path equals the corresponding command-line canonical absolute path,
bytes is an integer `0..2^63-1`, and sha256 is 64 lowercase hex. Each reference must equal the
source's actual reread byte count and digest and its sidecar digest. The software source is itself a
recursively closed object with exactly `repositoryUrl`, `programBase`, `0400Product`, `0400Report`,
`0601Product`, `0601Report`, `0602Product`, `0602Report`, `0603Product`, `governance`, and
`artifacts`; every identity/governance value equals the ledger value. Its artifacts allow only
`catalog`, `controller`, `verifier`, `spec`, `plan`, `lock`, and `software-support`.

The hardware source and the ledger's `hardware` value are byte-semantically identical parsed
objects and use the recursively closed `stm32-hardware-campaign-inputs/1` schema. Its exact root
fields are `schema`, `campaign_id`, `created_at_utc`, `generator_code_head`, `evidence_owner`,
`board_id`, `board_revision`, `mcu_part`, `mcu_uid_hash`, `probe_model`, `probe_serial_hash`,
`uart_adapter_model`, `uart_serial_hash`, `power_identity`, `transports`, `support_profile`,
`support_manifest`, `firmware_0400`, and `firmware_0600`. `campaign_id` is a canonical lowercase
hyphenated UUID; `created_at_utc` uses the program UTC format; `generator_code_head` equals
`0603Product`; `evidence_owner` equals `governance.hardware_evidence_owner`; the six unhashed board/
MCU/probe/UART/power identity fields are non-empty NFC strings of at most 256 UTF-8 bytes and reject
placeholder values; UID and serial identity fields are 64 lowercase hex; and `transports` is exactly
`["mailbox","rtt","semihosting","uart"]`. `support_profile` and `support_manifest` each contain
exactly `path`, `bytes`, `sha256`; `firmware_0400` and `firmware_0600` each contain exactly `path`,
`bytes`, `sha256`, `build_id`. These four paths are distinct canonical absolutes, their integer byte
counts and hashes match reread files, firmware build IDs are distinct non-empty NFC strings of at
most 256 UTF-8 bytes, and neither firmware object may alias the other.

Every artifact object is closed with exactly `kind`, `path`, `bytes`, and `sha256`; `kind` is one of
`catalog`, `controller`, `verifier`, `spec`, `plan`, `lock`, `software-support`, `hardware-support`,
or `firmware`; bytes is an integer `0..2^63-1`; and sha256 is 64 lowercase hex. Repository kinds use
normalized POSIX-relative paths resolved beneath the derived repository without link/reparse/
traversal escape; support and firmware kinds use canonical absolute paths. Each entry's file is
reread and must match its byte count and digest. Ledger `artifacts` is exactly the duplicate-free
union of the software artifacts plus `hardware-support` projections of `support_profile` and
`support_manifest` and `firmware` projections of `firmware_0400` and `firmware_0600`, sorted by the
UTF-8-byte tuple `(kind,path)`. Identical union members coalesce once; any duplicate within one
source, same `(kind,path)` with different bytes/hash, or same normalized path with a different kind
is a conflict and fails. Missing, extra, wrong-order, or mutated members fail before PASS output.

Candidate recovery uses only the closed wrapper interface `-ResumeCandidateRun -CandidateLedger
<absolute-candidate-ledger-json> -RecoveryRecord <absolute-recovery-record-json>`. The wrapper
validates both canonical schemas, absolute paths, retained checkpoint/attempt digest, run kind
`candidate-0601`, run ID, CodeHead, and one-resume policy before executing any child. No legacy
`-ResumeRun`, inferred ledger, or orchestration-context-as-ledger form is accepted.

Every candidate/final shard produces a deterministic portable ZIP plus a canonical inner manifest.
Sorted relative members, normalized metadata, package/member bytes and SHA-256, closed owner/
platform/run/CodeHead/catalog/lock/support bindings, and absence of credentials/absolute private
paths are verifier-enforced. The Windows-only 0601 controller retains its package locally; there is
no cross-machine transfer or evidence handoff. Controller code never opens a network or remote Git
connection.

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
12. deferred real-board transport contract, with fake/replay tests in the software candidate and
    real execution only in the post-0603 unified 0.4+0.6 activity.

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
For each workload/version, each batch p95 is the nearest-rank sample at
`ceil(0.95 * sample_count)` after ascending sort. The baseline is the median of the three batch
p95 values. MAD is the median absolute deviation of those three values. The absolute threshold is
the untruncated value `baseline + max(0.25 * baseline, 3 * MAD, 10 * clock_tick)`, rounded upward
to the next whole clock tick. If that rounded value exceeds the design maximum, calibration fails;
the verifier must not clamp it with `min()` or write a threshold. Verification must satisfy both
elapsed p95 `<= absolute_threshold` and
`(elapsed_p95 - baseline) / baseline <= 0.15`; an improvement produces a negative ratio and passes.
Fixed verifier vectors include: baseline 1,000, MAD 100, tick 10 gives threshold 1,300; baseline
1,000, MAD 0, tick 10 gives 1,250 and fails against a 1,200 maximum; baseline 1,003, MAD 10, tick 8
gives raw 1,253.75 and tick-rounded threshold 1,256.
Internal object-copy, canonical-JSON, SQLite, and decoder microbenchmarks are retained as diagnostic
facts rather than independent release blockers. Performance runs exclude coverage and record
antivirus/exclusion state rather than assuming it.

### 10.3 Deferred real-board matrix

One named supported reference target must eventually provide independent PASS evidence for memory
mailbox, RTT, UART, and semihosting in the unified 0.4+0.6 hardware activity after the 0603
Candidate. Every run records board identifier, MCU, probe serial hash, firmware
ELF digest, build ID, exact transport config, discovered/captured cases, raw event artifact, and
terminal counts. Fake backend evidence remains a separate gate and cannot own this result.

`tools/release/run_0600_hardware.ps1` is implemented and contract-self-tested in 0601 but performs
no real hardware action until the unified activity. Its closed interface is:

```text
-Contract 0400|0600 -Repo <absolute-exact-worktree> -ExpectedCodeHead <tested-product-sha>
-FinalRunId <id> -EvidenceRoot <new-on-first-prepare-or-checkpoint-bound-absolute-path>
-PrepareAction
-ExecuteAction -Nonce <nonce> -ActionDigest <sha256> -Authorized
-ResumeContract -Checkpoint <absolute-checkpoint-json> -RecoveryRecord <absolute-recovery-json>
```

`0400` runs only the catalog entries mapped to the historical 0.4 deferred behaviors. `0600` runs the four transport
gates and diagnostic-chain gate. The base parameters are required in every mode and exactly one
mode switch is accepted. `-PrepareAction` selects only the next pending catalog action, verifies the
clean exact worktree and catalog/support/tool/owner/hardware preconditions, atomically creates or
updates `<EvidenceRoot>/checkpoint.json`, emits exactly `nonce`, `action_digest`, `expires_at_utc`,
and `checkpoint`, then exits without running a product body. It calls the product prepare API once;
that call performs exactly one combined `OBSERVE`-only identity/state read and returns the canonical
prepare summary bound into the action digest and checkpoint. Prepare counters must be exactly
`identity_state_read=1`, `control=0`, `modify=0`, `reset=0`, `halt=0`, `write=0`, and `flash=0`.
Any second observation or any CONTROL/MODIFY attempt fails preparation. The nonce is exactly 32
bytes from an operating-system CSPRNG, encoded as exactly 64 lowercase hexadecimal characters.
Prepare never prepares or authorizes the following action.

`-ExecuteAction` requires the matching unexpired nonce/digest plus the explicit `-Authorized`
switch, consumes that authorization once, executes exactly that one prepared action, writes its
terminal evidence, atomically advances the same-root checkpoint, and exits. The next action always
requires a new prepare invocation and new authorization. Immediately before the first authorized
CONTROL/MODIFY operation, execute re-reads the identity/state snapshot and rejects any difference
from the bound prepare summary without performing CONTROL/MODIFY. `-ResumeContract` accepts only the
same-root checkpoint plus a separate reviewer-authored recovery record after one enumerated
recoverable interruption. The recovery record is the program-wide `RecoveryRecord` defined in §9;
for hardware its `run_kind` is `hardware-0400` or `hardware-0600`, and its `checkpoint` is the same
absolute path passed on the command line. Resume verifies both files, the evidence root,
contract, run ID, both CodeHeads, completed evidence, recovery history, and single-resume limit. It
never reruns a completed product action. If recovery would repeat a hardware action, resume records
the interruption and exits so that action must receive a fresh prepare/authorization pair.

The checkpoint binds contract, `FinalRunId`, evidence-root identity, ordered action inventory,
per-action state, `contract_complete`, the product prepare summary and counters,
nonce/digest/expiry/authorization consumption, recovery history,
`controller_code_head`, and `tested_code_head`. Every result and artifact binds both
`controller_code_head` (the exact
0601+ controller/verifier implementation executing the gate) and `tested_code_head`
(`ExpectedCodeHead`). The verifier rejects omitted bindings or any attempt to use the 0.6
controller commit as evidence that 0.4 product code was tested. Contract self-tests use fake
executables and prove exactly one prepare OBSERVE snapshot with zero CONTROL/MODIFY, state-change
refusal before execute, one-action execution, per-action authorization, exact 64-hex CSPRNG nonce,
same-root recovery, dispatch isolation, dual-CodeHead binding, authorization refusal,
contract/gate mismatch rejection, and zero real hardware access. Readiness validates only that the
authorization mechanism and mode contracts are available; it never prepares an action, requests
authorization, or validates a reusable/pre-issued authorization.

## 11. Candidate matrix and exit criteria

After the exact 0601 inventory commit, a non-executing candidate precheck verifies CodeHead,
catalog/nodes, support, tools, the Windows owner, and empty evidence roots. The unchanged CodeHead's
collect-all candidate matrix includes:

- whole accepted-base ancestry, diff, scope, source-hash, and clean-tree audit;
- Windows, CPython 3.10/3.12 Toolkit shards;
- schema mirror and package inventory;
- product branch coverage at or above 90%;
- performance thresholds under both Python versions;
- offline wheel build/install and managed launcher smoke;
- controller/verifier self-tests including intentional failure and bounded infrastructure-recovery
  fixtures;
- two-workspace concurrent isolation;
- all four transports through fake backends, recorded replay, and capability-contract tests;
- all applicable 0.5 regression gates.

The tracked implementation report at
`docs/codex/returns/STM32TK-0601-TEST-EVIDENCE/implementation-report.md` is written only after
overall software PASS and is a report-only child commit. It lists the product CodeHead, complete
gate evidence inventory, bytes/SHA-256,
owners, tools, commands, UTC, platform, and no moving commit count. That report commit becomes
the accepted base for 0602.

## 12. Completion conditions

0601 succeeds when all of the following are true:

1. Evidence can be created, reloaded, verified, indexed, rebuilt, and safely collected.
2. Project v3 is the only emitted schema and v2 upgrades are explicit and reversible.
3. Host tests run only discovered exact IDs through argv-safe CTest execution.
4. Target tests produce identical verified semantics through all four fake/replay transport paths,
   and the module records `SOFTWARE_COMPLETE_HARDWARE_PENDING` until deferred real runs PASS.
5. Every Target operation binds one MODIFY authorization to exact firmware and target identity.
6. Probe v2's complete schema, the gate schema/families, and exact 0601 gates/nodes are frozen;
   later module entries remain reserved rather than fabricated.
7. Coverage, performance, platform, offline-install, integrity, and isolation gates pass.
8. A report-only commit records the accepted 0601 software CodeHead without changing product files.
9. Final `v0.6.0` acceptance remains blocked until the post-0603 unified 0.4+0.6 activity supplies
   independent PASS evidence for both contracts, including all four real transports and the
   diagnostic chain.
