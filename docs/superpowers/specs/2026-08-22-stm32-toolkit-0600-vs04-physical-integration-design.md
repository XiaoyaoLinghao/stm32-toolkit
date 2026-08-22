# STM32 Toolkit 0.6 VS-04 Physical Integration Design

## 1. Status and authority

This specification extends the approved 0.6 cross-module integration design after VS-03 CodeHead
`5d6e06845a2c1d991181c5ff84a9194dfcc49c8c` was independently accepted. It is the single VS-04
contract for physical Scenario C and supersedes replay-only assumptions only where this document
explicitly says so. Existing VS-01 through VS-03 behavior remains compatible.

The GPT-5.6-sol primary owns this specification, slice plans, risk decisions, and final reviews.
GPT-5.6-luna/max implementers own product code and implementation tests. No physical action and no
remote Git operation is authorized by this document.

## 2. User-visible goal and non-goals

VS-04 lets a caller take one named supported board and probe through a physical failed-before and
fixed-after loop:

1. prepare and explicitly authorize an identity-bound Target action;
2. flash and run the selected Target cases under one probe lease;
3. publish a durable physical TestRun;
4. capture and publish a physical Monitor window;
5. diagnose, bind an external source change, repeat with a second authorization, compare, and
   produce a marker, deterministic bundle, and physical FixVerification.

Non-goals are new probe backends, automatic source modification, automatic authorization,
simulation as physical evidence, batch hardware farms, device-pack discovery, release packaging,
Python 3.10, UI redesign, and broad refactoring of VS-01 through VS-03.

## 3. Delivery shape

VS-04 is delivered as three sequential vertical product behaviors, not a recursive task tree:

- **VS04-A — authorized physical Target result:** public prepare/execute operations produce one
  durable, reloadable physical TestRun.
- **VS04-B — physical diagnostic verification:** a live Monitor window becomes a durable physical
  run reference and two compatible physical captures complete Analysis and FixVerification.
- **VS04-C — named-board Scenario C:** the same public operations run on the named hardware with
  two separately approved MODIFY digests.

Each predecessor must be integrable before the next plan is written. VS04-C contains no planned
product coding; a defect returns to the owning A or B contract instead of growing a hardware Gate
tree.

## 4. Cross-module responsibility boundaries

### 4.1 Common provenance authority

Toolkit owns one closed execution-provenance policy consumed by Testing, Diagnostics, and Monitor:

| source | physical flag | workspace/session relation | hardware labels |
|---|---:|---|---|
| `replay` | `false` | imported origin may differ from current import/projected identity | exact replay labels remain required |
| `physical` | `true` | origin equals import/current workspace; origin session equals projected/current session | real non-replay probe, target, flash-session, and lease IDs |

Unknown sources, mixed source/flag pairs, replay labels on physical records, physical labels on
replay records, or cross-source before/after pairs fail closed as incompatible identity. This table
is the unique authority; consumers must not each invent another source switch.

### 4.2 0601 Testing and Probe

0601 owns Target preparation, exact action digest persistence/consumption, the single MODIFY probe
lease, guarded flash, transport execution, raw evidence, TestRunManifest, and `test-run` root.
It exposes prepare, execute, and show through public application APIs plus CLI/MCP adapters.

### 4.3 0602 Diagnostics

0602 owns diagnostic session transitions and validation that the TestRun, Monitor run, analysis,
marker, verification plan, and final verification all carry the same permitted provenance. It does
not flash hardware or create Monitor history.

### 4.4 0603 Monitor

0603 owns live observation/history, publication of an immutable physical Monitor run reference,
before/after comparison, marker, and bundle. It does not acquire a MODIFY lease and does not import
physical history as replay.

### 4.5 0600 Integration

0600 names the hardware/firmware environment, records the two user authorizations, composes the
public operations, and accepts Scenario C. It never edits Evidence to synthesize a physical PASS.

## 5. Public data contracts

### 5.1 Physical Target preparation

`test.target.prepare` derives, rather than trusts caller-supplied identity fields. Its closed intent
contains:

`workspace_id, logical_project_id, session_id, input_snapshot_sha256, target, probe_serial_hash,
elf_path, elf_sha256, build_id, inventory_digest, transport, transport_config, support_profile,
case_ids, timeout_ms, nonce, prepared_at_utc, expires_at_utc`.

`elf_path` is a portable project-relative regular file path. Target, firmware, inventory, project,
and probe identity come from the current Project v3/build/discovery boundaries. Preparation may use
a bounded OBSERVE connection and may write only the authorization record under the workspace data
root; it performs no flash, reset, halt, resume, test, or Monitor mutation.

Canonical JSON SHA-256 of the complete intent is the action digest. It expires within five minutes,
is durable across CLI processes, and is single-use.

### 5.2 Physical Target execution

`test.target.execute` accepts project/data/session, the same raw probe selector, and exactly one
`authorized_action_digest`. It reloads the persisted intent; the caller does not resubmit or alter
the binding. Before side effects it revalidates project snapshot, build, ELF bytes, inventory,
probe/target identity, expiry, and digest. It consumes the authorization once before MODIFY work.

One `ProbeServiceSupervisor` owns one MODIFY lease for identity check, flash, post-flash identity,
transport run, and cleanup. Flash uses the already-bound service client. No nested
`flash_workflow`, second supervisor, or second lease is allowed.

Success publishes a TestRun whose source contract is:

- mode `target`;
- execution source `physical` and physical evidence `true`;
- origin/import workspace both equal the executing `WorkspacePaths.workspace_id`;
- selected real transport, real probe/target/flash-session/lease labels;
- complete FirmwareIdentity and action digest lineage;
- immutable manifest/raw-event artifacts and a `test-run` root.

`test.show` reloads both replay and physical Target runs and projects the same common fields without
claiming replay for a physical run.

### 5.3 Monitor run reference v2

The generic v2 schema is `stm32-monitor-run-ref/2`. It retains run/window/binding/digest fields but
uses `source_record_sha256` instead of the replay-specific `fixture_sha256`.

- Existing v1 replay references remain accepted and serialize unchanged.
- A v1 replay reference projects `fixture_sha256` as its source-record digest internally.
- New replay or physical publications use v2.
- A physical v2 reference has equal origin/import workspace and origin/projected session/run IDs,
  real hardware labels, `execution_source=physical`, and `physical_transport_evidence=true`.

The physical publisher queries an already committed live HistoryStore window, validates contiguous
sequence/digests/binding, publishes its transcript Evidence and root, then returns the reference.
It does not reconnect to the probe or mutate history.

### 5.4 Analysis, marker, bundle, and verification

Before/after Monitor references must use the same source, project, workspace relation, target, and
selector. Changed firmware requires the existing SourceChangeDeclaration. Derived Analysis,
marker, bundle, diagnostic metadata, and FixVerification copy the validated provenance rather than
hard-code replay.

Replay and physical outputs use the same analysis and diagnostic state machines. A physical PASS
requires two physical TestRuns and two physical Monitor references; replay evidence can never
satisfy it.

## 6. Error semantics and lifecycle

Preparation states are `PREPARED -> CONSUMED`; there is no reusable authorized state. Execution is
`CONSUMED -> RUNNING -> terminal TestRun publication`. A failure after consumption remains consumed
and preserves valid partial Evidence; retry requires a new preparation and user authorization.

Stable classification:

- invalid or stale intent/digest: `TEST_AUTHORIZATION_INVALID`;
- changed project/inventory: `TEST_INVENTORY_CHANGED`;
- changed probe/target/firmware: `TEST_IDENTITY_MISMATCH`;
- occupied probe: existing probe-busy code plus owner evidence;
- unavailable transport: `TEST_TRANSPORT_UNAVAILABLE`;
- flash failure: `TEST_FLASH_FAILED`;
- deadline/cancellation: existing timeout/cancellation semantics;
- corrupt durable evidence: Evidence integrity failure;
- provider/filesystem/tool inability: environment failure;
- incompatible cross-module source or identity: `INCOMPATIBLE_IDENTITY`.

Environment failure never becomes a failed test case. A product test failure is still a successful
physical execution with a terminal `failed` TestRun.

## 7. Cross-module invariants

1. One raw probe has at most one live owner. Busy owners are reported, never killed or stolen.
2. One authorization digest causes at most one MODIFY attempt and cannot authorize a second build,
   case set, transport, probe, revision, or timeout.
3. Physical execution never creates replay labels; replay never creates physical evidence.
4. Physical origin/import identities equal the current workspace and remain equal at every derived
   boundary.
5. TestRun and Monitor firmware identities match byte-for-byte before comparison.
6. Source changes bridge the exact before/after snapshot, build, and ELF identities.
7. Derived Evidence is append-only, deterministic for one intent, and reloadable from fresh
   objects.
8. Failed preflight and incompatible inputs append no TestRun/Monitor/analysis/verification roots.
9. Project trees are unchanged by Evidence publication; only the named build output and authorized
   hardware side effects are permitted.

## 8. Executable acceptance scenarios

### 8.1 A — authorized physical Target result

With fake production seams, prepare returns a digest without MODIFY calls. Execute uses the digest
once, obtains one MODIFY lease, flashes and runs exactly the selected cases, publishes a physical
TestRun, and fresh `test.show` reloads it. Reuse, drift, and same-probe overlap fail closed.

### 8.2 B — physical diagnostic verification

With fake probe/Monitor seams and real public storage, two physical Target/Monitor captures around
one SourceChangeDeclaration produce changed Analysis, marker, deterministic bundle, PASSED
FixVerification, and RESOLVED session after fresh reload. Mixed replay/physical and incompatible
firmware append nothing.

### 8.3 C — named-board physical failed-before/fixed-after

On a user-named board/probe, the first separately authorized digest flashes known failing firmware,
runs one Target case and Monitor window, and opens diagnosis. After the externally supplied change,
the second separately authorized digest rebuilds/flashes/reruns the same behavior. Both physical
chains reload and produce the final physical FixVerification.

## 9. Migration and historical disposition

- Preserve every VS-03 replay schema, fixture, TestRun, reference, and acceptance result.
- Add source-policy validation and physical variants; do not rewrite existing Evidence.
- Accept Monitor run-reference v1 for replay and introduce v2 for generic source semantics.
- Retain TargetTestRunner's closed binding, nonce, expiry, single-use record, transport limits, and
  Evidence collector.
- Replace only its unusable nested-flash production composition with the single-lease composition.
- The old `flash --authorized` boolean remains a separate one-shot manual flash command; it cannot
  satisfy Target-run exact-digest authorization.
- Historical physical deferrals remain truthful until Scenario C passes.

## 10. Verification and risk triggers

VS04-A and B each use focused behavior tests, cross-module contract tests, affected regression, and
one independent complete-diff review. Probe/authorization changes trigger busy, cancellation,
timeout, identity-drift, and fault-injection regression. Persistent schema changes trigger v1/v2
compatibility tests. Physical and release matrices do not move forward.

VS04-C runs only the named Scenario C and its mandatory authorization/identity negatives. Broader
hardware, platform, packaging, coverage, or release checks remain release-level work.

## 11. Stop conditions and current blockers

If the same contract fails two implementation/review rounds, return here instead of patching again.
If A or B cannot remain a 1–3 day demonstrable behavior, revise this design rather than splitting
by files or error classes.

VS04-C is blocked until the user names the board, MCU/target, raw probe selector, Project v3,
failing case, transport configuration, Monitor selector, failing/fixed source revisions, and tool
environment. Each returned action digest then requires a separate explicit user authorization.
