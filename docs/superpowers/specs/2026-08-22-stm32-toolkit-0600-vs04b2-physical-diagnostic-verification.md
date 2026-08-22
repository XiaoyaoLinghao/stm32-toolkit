# STM32 Toolkit 0.6 VS04-B2 Physical Diagnostic Verification

## 1. Status, base, and ownership

This specification is the executable VS04-B2 integration contract. Its accepted base is
`2b8b5b166c04c59d3f0f8bf326204ac74264620e`, the independently accepted VS04-B1 replacement
candidate. It refines the VS04 physical integration design and supersedes replay-only assumptions
in VS03 only where explicitly stated here.

GPT-5.6-sol owns this specification, the implementation plan, risk decisions, and complete-diff
review. One GPT-5.6-luna/max implementer owns all product code and implementation tests for this
slice. No remote Git mutation or hardware action is authorized.

## 2. Product behavior and non-goals

Given two accepted B1 physical Monitor references and their failed-before/passed-after physical
TestRuns, a caller can run the existing Analysis, marker, deterministic bundle, Diagnostics, and
FixVerification lifecycle. After fresh reload the result is one `PASSED` FixVerification and a
`RESOLVED` diagnostic session whose complete Evidence graph is physical.

Non-goals are new probe/transport behavior, live sampling control, flash or lease operations,
source editing, new UI, new diagnostic states, new Analysis/marker/bundle/FixVerification schemas,
History migration, replay-v2 publication, packaging, release matrices, Python 3.10, and real
hardware execution.

## 3. Closed source union and authority

The only accepted Monitor reference union in 0.6 is:

- `stm32-monitor-run-ref/1`: `execution_source="replay"`, physical flag false, `fixture_sha256`;
- `stm32-monitor-run-ref/2`: `execution_source="physical"`, physical flag true,
  `source_record_sha256`.

Replay-v2, physical-v1, mixed before/after versions, mixed source/flag pairs, replay sentinels on a
physical record, and physical labels on replay fail as `INCOMPATIBLE_IDENTITY`. Existing v1 replay
objects and bytes remain exact. The older statement that a new replay publication may use v2 is
deferred; VS04-B2 does not implement it.

`validate_execution_provenance` remains the common workspace/session/source relation policy. Its
physical branch must reject both `replay` and every `replay:*` hardware label. Source-specific
consumers still validate their exact closed metadata and label vocabulary.

Authorities are:

- physical TestRun outcome and physical provenance: `TestRunRepository.load`;
- physical Monitor samples and TestRun link: immutable B1 transcript Evidence;
- replay samples: the accepted replay transcript plus current projected History cross-check;
- changed firmware: the exact `SourceChangeDeclaration`;
- Analysis, marker, bundle, and diagnostic state: their existing rooted Evidence/checkpoint chains.

No physical B2 path queries live History, asks for the transient raw probe selector, connects to a
probe, or mutates any source object.

## 4. Shared physical source-record contract

Toolkit's dependency-neutral Monitor wire module adds closed physical transcript decoding and
validation for `stm32-monitor-physical-transcript/1`. It uses the accepted physical limits: 64 MiB
canonical bytes, Monitor's 1 MiB-character typed JSON bound, 1,024 batches, 10,000 values, and the
existing depth/node/numeric/NFC constraints. It validates exact top-level fields, physical
source/flag, scenario role, linked `test_run_id`, binding, contiguous batch chain, selector
vocabulary, and canonical bytes. Replay decoding and budgets remain unchanged.

Monitor factors its existing physical fresh loader into one authenticated internal result containing:

- the exact stored `MonitorRunRefV2`;
- transcript root, envelope, canonical bytes, and complete immutable `SampleBatch` tuple;
- transcript-linked physical `test_run_id`;
- the freshly loaded authoritative physical TestRun.

The existing public `load_monitor_run_reference` retains its signature and returns only the
reference. It delegates to the authenticated result. Analysis consumes the richer result and
requires the stored reference to equal the reference supplied in `AnalysisRequest`.

Per physical run, TestRun, reference, and transcript agree on role/state, source/flag,
workspace/project/session, target device, physical target, hashed probe selector, firmware
snapshot/build/ELF/Git identity, flash session, and lease. The transcript TestRun ID is the only
Monitor-to-TestRun ID bridge; firmware equality cannot substitute for it.

## 5. Analysis and pair invariants

`AnalysisRequest`, `AnalysisLineage.new`, pure window validation, and comparison accept only exact
instances of the closed reference union and continue rejecting subclasses. No Analysis schema is
changed. Request and result digests naturally bind complete v1 or v2 reference bytes.

Both references require exact failed-before/fixed-after roles, the same source/flag, workspace and
project, target device, physical target, hashed selector, and compatible requested selector
vocabulary. Physical captures may use different Monitor group/run IDs, flash sessions, and leases;
each remains bound to its own transcript and TestRun. Changed snapshot/build/ELF values require the
exact existing declaration bridge and claimed hypothesis. Undeclared firmware drift fails before
derived publication.

Analysis dispatch is source-specific:

- v1 replay retains the accepted transcript validation and paged History query byte behavior;
- v2 physical loads both immutable authenticated source records and compares their stored batches,
  with no History access.

Insufficient trustworthy pairs still produce the accepted retained `INVALID/INCONCLUSIVE`
AnalysisResult. They are not an environment or identity exception.

## 6. Derived Evidence and deterministic bundle

AnalysisResult, AnalysisLineage, DiagnosticMarker, DiagnosticMarkerRef, AnalysisPublication,
analysis bundle, and AnalysisBundleRef keep their existing `/1` schemas and field ordering.
Analysis, marker, and bundle Evidence metadata copy the validated pair's source and physical flag
instead of hard-coding replay. Replay metadata and payload bytes remain exact.

Physical bundle export reloads the two TestRuns and the two authenticated source records. Each
caller-supplied TestRun ID must equal its transcript `test_run_id`; manifests require Target mode,
failed/passed role state, an accepted physical transport, `target-test-physical`, and exact
per-run identity/provenance. The TestRuns share project, current workspace/session, target, selected
case set, and inventory scope. Their firmware difference is exactly the declaration bridge.

The existing bundle schema, digest-table order, parent order, bundle ID equation, and deterministic
timestamp remain unchanged. Embedded v2 references make a physical bundle self-describing. The
bundle and all public/durable derived bytes contain only the hashed probe selector, never the raw
selector. Repeated export is byte-identical and idempotent.

## 7. Diagnostics and FixVerification

Diagnostics keeps `failed_run_mode = host | target`. Physical provenance is not a third routing
mode. For `target`, authoritative TestRun loading branches on validated Evidence:

- replay retains exact VS03 `target-test-replay`, transport, root, and non-physical rules;
- physical requires `target-test-physical`, physical/true, current equal workspace/session,
  accepted physical transport, and the closed physical root/envelope metadata.

The durable failed TestRun fixes the source policy for the session. Fixed TestRun, Monitor
references, Analysis, marker, and bundle must resolve to the same source/flag. Toolkit independently
validates physical transcript/reference Evidence with the shared wire contract and validates
Analysis/marker metadata dynamically. Wrong source, wrong linked TestRun, or incompatible identity
appends no diagnostic event or checkpoint.

`stm32-fix-verification/1`, VerificationPlan, diagnostic events, DiagnosticStore, and the state
machine remain unchanged. A physical FixVerification is a property of its freshly validated
physical TestRun/Monitor/Analysis/marker graph; optional provenance fields are not added to the v1
payload. Completion keeps the accepted status rules. Only `PASSED/VERIFICATION_PASSED` transitions
to `RESOLVED`.

## 8. Thin adapters

Monitor compare and bundle commands keep their current arguments; v2 request/publication documents
flow through the existing one-workflow-call adapters.

Toolkit adds only the missing projection of the existing application parameter:

- CLI `diagnose start ... --failed-run-mode {host,target}`, default `host`;
- MCP `stm32_diagnostic_start.failedRunMode`, closed `host|target`, default `host`.

They call `diagnostic_start` once and expose no replay/physical switch. Omitted/default Host calls
retain their accepted bytes and behavior.

## 9. Error semantics and publication order

- malformed caller wire/input: existing request/workflow-invalid code;
- mixed source/flag, role, selector, linked TestRun, scope, or declaration mismatch:
  `INCOMPATIBLE_IDENTITY`;
- missing/corrupt root, envelope, artifact, canonical source, digest, or supplied/stored reference
  contradiction: `EVIDENCE_INTEGRITY_FAILURE`;
- provider/filesystem/storage inability: `ENVIRONMENT_FAILURE`;
- changed derived-operation intent: `OPERATION_CONFLICT`;
- insufficient samples: retained inconclusive Analysis, then inconclusive FixVerification.

Both complete authority graphs and the declaration are preflighted before the first Analysis or
marker write. Bundle authority is preflighted before its write. Diagnostic incompatibility is
preflighted before event append. Existing append-only valid-prefix recovery remains unchanged;
already accepted input Evidence is never invalidated or rewritten.

## 10. Executable acceptance

1. **Physical positive:** real public stores with fake capture seams publish failed and passed
   physical TestRuns and B1 references around one declaration. Fresh contexts compare from Evidence
   with History access forbidden, produce VALID/COMPLETED/changed Analysis and marker, export the
   same bundle bytes twice, complete PASSED FixVerification, resolve the session, and fresh-reload
   every authority link.
2. **Mixed/identity negative:** replace one physical ref with replay v1, a different selector,
   undeclared firmware, or a wrong valid physical TestRun. Compare/bundle/verification returns
   `INCOMPATIBLE_IDENTITY`; no derived roots/events/revision changes occur.
3. **Integrity/provider negative:** corrupt a physical transcript/reference or inject provider
   failure. The public boundary distinguishes integrity from environment failure and appends no
   Analysis, marker, bundle, or diagnostic success.
4. **Insufficient data:** a valid physical pair with fewer than two usable aligned pairs retains an
   inconclusive Analysis and completes an inconclusive FixVerification without resolving.

## 11. Implementation boundary and risk triggers

Permitted production files are the shared execution/source-record contract, Monitor physical
loader/Analysis/workflow, Toolkit diagnostic workflow, and the two existing Toolkit start adapters.
Corresponding focused tests plus one VS04-B2 end-to-end test are permitted. Diagnostic models,
events/store, Testing producers, History, EvidenceStore/GC, Probe, runtime/service/sampler/UI,
packaging, and release controllers are out of scope.

Changing History, EvidenceStore/GC, Testing publication, diagnostic models/store, or hardware code
stops implementation and returns to this design. Normal verification is the B2 scenario, focused
contract/workflow/adapters, VS03 replay E2E, Host diagnostic regression, Python 3.12 compilation,
and complete diff review. Release, coverage, packaging, Python 3.10, UI, platform, and hardware
matrices remain deferred.
