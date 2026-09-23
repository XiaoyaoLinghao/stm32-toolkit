# Risk-layered qualification v2

Accepted base: `4bb612beabfdaf1ab4c845b966061832add38482`.
Product source: `8a11caef14df16c5e56c0be2363d4ef5530110eb`.
The user's 2026-09-20 approval authorizes this test reorganization and offline
supplementation. Primary owns specification, scope, integration and acceptance;
Luna/max owns new implementation tests; a separate reviewer checks scope and
diffs. No remote action is authorized by this amendment.

## Three runnable scenarios

### User-approved named internal I/O boundary — 2026-09-24

The user accepted the preceding concrete proposal with "continue" after the
primary explicitly asked approval for this boundary. Integration base is
3de5e2a0010d96300d33dd3d41edddb672fd40f3; product/RC4 remains968cbb69 and
canonical coverage remains U63 until qualified data is admitted.

The sole additional tested entry is
`diagnostic_workflows._read_transcript_parent`, source blob
066716900211b530e2d673618dedc1af50120eea. Its state may be initialized by the real
`_make_state(context)` from a real project manifest; that setup is not permission
to test arbitrary other internal I/O entries. Real EvidenceStore objects, files,
normal constructors, canonical serialization, content hashes, identity checks
and transitive production validators remain unchanged. No private-state writes,
reader/store/identity/validator replacement, fake successful authority or new
generic fixture framework is allowed.

Two component scenarios are in scope: a normally produced replay transcript
loads successfully; constructor-valid, correctly content-addressed negative
records with inconsistent semantic relationships are rejected without mutating
the supplied evidence. Recheck a valid control after rejection. Each negative
record uses its own real ID and is never represented as accepted Diagnostic
analysis, a plan, authorization, or physical evidence. Run-owned negative copies
must preserve the original positive evidence; ordinary store checks may reject
inputs before a deeper reader guard, which earns no credit for that deeper guard.

Classify admitted evidence as `internal-component-io`, publicReachability=false,
authorityEvidence=false, physicalEvidence=false. This is a bounded extension to
the earlier pure-unit layer, not a release-threshold or denominator change.
Native parent/actual relevant subprocess data retention, matching-source
admission and independent full-diff review remain mandatory. Existing public
workflow, actual-resource, Windows, package and physical evidence stays required
and is reused where applicable. Old two-round STOP families stay held.

The primary fixes the exact semantic group and yield justification before
implementation. Only the existing Luna-owned internal validation test file is
eligible; the plan specifies the selected cases and budgets. This approval is
not a promise that nine reader guards, or the remaining release thresholds,
become reachable. No product changes, new system/remote/hardware authority,
coverage exclusions or automatic follow-on branch hunting are authorized.

### User-approved internal unit boundary — 2026-09-23

The user approved the primary's proposal to admit a bounded internal pure-unit
layer to formal native coverage, with at most four hours for method validation.
This changes test-entry eligibility, not the coverage algorithm, denominator,
frozen file membership, release percentages or mandatory workflow assertions.
Baseline integration is 85e6abfb91061b8dffc2f48dbb454ff226f9aff1; product RC4 is
968cbb69b1f54b95a8fdc18a550481f6ff7c1268; U60 remains canonical until a reviewed
union of accepted, matching-source raw data replaces it.

Each admitted internal entry must be named in the existing execution plan and
bound to its Git source blob. Review its transitive calls before implementation.
It may parse or compare ordinary wire values and publicly constructed models,
including revision, timestamp and identity fields. It must have no filesystem,
network, process, hardware, wall-clock, mutable-global, authorization-issuance,
evidence-publication or lifecycle-transition side effect. Merely comparing an
identity field is not issuing authority. Existing model construction and digest
functions remain real and unchanged; no validation/identity/hash monkeypatch,
private-state mutation, object-construction bypass or fake successful authority.

An internal test may exercise a defensive guard that an earlier public guard
normally dominates. It proves that internal validation contract only. Label it
creditClass=internal-pure-unit, publicReachability=false, authorityEvidence=false,
physicalEvidence=false. Real measured native branches may enter the formal
numerator after independent review; do not call them public-flow or physical
PASS. Existing critical public-flow and actual-resource evidence remains required.

Two bounded unit scenarios apply: (1) constructor-valid recovery/diagnostic models
with inconsistent cross-record relationships are rejected accurately; (2)
Monitor wire/model parsing rejects malformed values and preserves valid control
results. A separate measurement/integration control retains, admits and merges
accepted matching-source parent/child raw data without manufactured arcs; it is
not itself internal-pure-unit behavior evidence. Reuse existing tests, fixtures
and launchers.
Product changes, new generic frameworks, new platforms, hardware and remote
operations are outside this amendment. Real resource faults still use public
module/external-boundary tests with actual release and recovery proofs.

Prior two-round STOP families and their history are retained. This amendment
does not release runtime-cleanup-precedence or permit renaming an old failed
attempt. A proposed entry intersecting a held family requires a specific primary
design decision before implementation. Unknown reachability remains in scope.

1. Begin, checkpoint, resume and complete recovery using authenticated diagnostic
   and build/test evidence. An invalid identity, stale revision, corrupt chain or
   duplicate request must not create unauthorized evidence or advance state.
2. Prepare and apply a project operation or authorized probe operation. Valid
   inputs have bounded effects; refusal precedes dispatch; failure/cancellation
   preserves user files and settles the lease, process and session it owns.
3. Record, reload, analyze and export Monitor observations. Malformed or stale
   identity is rejected, publication is atomic, and stop/failure releases owned
   resources. Software fixtures are not physical acceptance.

Non-goals: features, new hardware or platforms, sampling upgrades, product edits
to inflate coverage, a diagnostic/test framework, new CI, coverage exclusions,
or reopening unchanged accepted hardware and UI checks.

## Gates and scope

Each Python package retains its complete native branch denominator and mandatory
90% floor. By the user's explicit 2026-09-22 amendment, Toolkit's existing
risk-core-v2 release floor is 90%; Monitor's remains 95%. Toolkit core95 is a
later quality-improvement target and does not block this1.0 release. This is an
approved acceptance-standard change, not evidence that the former95% gate passed.
Keep the original unmet95% records, all v2 file membership/denominators, native
measurement and relevant subprocess collection unchanged. The v1 broad-core
statistics remain visible under their original name and disposition; a new v2
score does not turn an old unmet v1 target into a PASS. No invented per-file
minimum is added. Critical behavior assertions below are independently required.

This amendment changes no Monitor, UI, native Windows, package, physical,
authorization or permission requirement. Preserve accepted RC2 build/install/
Repair/rollback/Monitor-use/physical evidence within its recorded scope. Once
both Toolkit90 floors, Monitor's unchanged floors, these critical assertions and
every remaining release gate pass, end this acceptance effort. Do not
automatically continue into Toolkit95 optimization. Recalculate existing accepted
data only; a threshold/report change does not trigger tests or product edits.

Select whole files by risk ownership, before calculating the v2 percentage.
Mixed files stay whole. Do not select individual favorable branches, remove
platform branches or rename a low-scoring owner as an adapter to exclude it.
The existing coverage.py per-file summaries suffice; no symbol-selection engine
or hand-edited arcs are needed.

For Toolkit, relative to `tools/stm32-toolkit/src/stm32_toolkit`, core v2 is:

- Every tracked Python file in `acceptance/`, `diagnostics/`, `evidence/`, and
  `probe/`: durable authority, authorization, identity and resource lifecycle.
- `identity.py`, `execution_provenance.py`, `paths.py`, `process.py`, `doctor.py`,
  `tool_support.py`, `creation_environment.py`, `context.py`: identity/path trust, environment
  digests, execution-profile guards and bounded process settlement.
- `creation_authorization.py`, `creation_apply.py`, `creation_workflows.py`,
  `cubemx_adapter.py`, `regeneration.py`, `regeneration_workflows.py`,
  `project_upgrade.py`, `workflows.py`: consumption, staged writes and rollback.
- `generation/managed_files.py`, `generation/configure.py`,
  `generation/creation.py`, `migration/apply.py`, `migration/git_guard.py`,
  `migration/planner.py`, `migration/model.py`, `migration/rules.py`: write
  ownership, plan identity/blocker authority and filesystem guards.
- `project.py`, `project_model.py`, `cubemx_project.py`, `build/identity.py`,
  `build/runner.py`: project/artifact identity used by authorized operations.
- `hardware_workflows.py`, `testing_workflows.py`, `diagnostic_workflows.py`,
  `testing/target.py`, `testing/host.py`, `testing/publication.py`,
  `testing/artifacts.py`, `testing/model.py`, `testing/protocol.py`,
  `testing/native_output.py`,
  `testing/replay.py`, and every tracked Python file in `testing/transports/`:
  controlled execution, result authority and resource settlement.
- `debug/read.py`, `debug/firmware.py`, `debug/fault.py`, `debug/sampling.py`,
  `debug/model.py`, `debug/svd.py`, `debug/dwarf.py`, `monitor_observation.py`, `monitor_replay_contract.py`,
  `monitor_analysis_contract.py`: read/control bounds and observation provenance.
- `cli.py`, `mcp_server.py`: adapter-local consent, root/path and wire guards.

Other Toolkit files remain overall-only: format interpretation, descriptions,
discovery, templates, ordinary result presentation and export inventories do not
own the above authority transitions. Their caller guards remain core. A reviewer
must reject this classification if an omitted file owns a unique safety check;
names alone do not establish omission. A changed/new responsibility requires a
scope amendment before measuring it, not after seeing its score.

For Monitor, all tracked Python source remains core except forwarding-only
`__init__.py` and `__main__.py`. Source inspection found that even `analysis.py`
owns lineage/window validation and `cli.py` owns context/file guards. Models,
protocol, groups, exports and UI assets also retain integrity/security behavior.
Whole-file selection therefore does not reduce Monitor's existing denominator;
its 140-branch gap at union23 remains real. Do not promise 95% by reclassification.

UI's complete-source native 784/810 result and existing per-file gate are retained
separately while source/configuration/dependencies remain unchanged. Final bundle
checks and the seven pending Windows native checks are separate release evidence.

## Test layers and invariants

Use existing model constructors/decoders, stores, workflow entries and provider
protocols. Start with valid factories/canonical records, then vary one supported
input or provider outcome. Assert results AND persisted state/owned resources.
Mock an external provider outcome, never the decision being tested. Do not build
impossible objects, bypass schema invariants or manufacture unreachable races.

| Risk | Required observable assertion |
| --- | --- |
| Consent, expiry, replay, identity mismatch | Exact refusal; dispatch count zero; authorization not wrongly consumed |
| Recovery CAS, retry, lineage and corruption | Exact revision/reference; idempotent result or refusal; no unauthorized new roots |
| Project apply or rollback failure | User-owned bytes preserved; only owned staged files affected; exact failure |
| Probe timeout/cancel/end | Settled lease and session; owned child terminated/reaped; no hidden retry |
| Monitor import/publication/export | Bound identity/digest; no partial publication or out-of-root file; correct error |

Missing relevant assertions block acceptance despite a percentage. Unsupported
platform/hardware evidence remains explicitly pending; fixtures never close it.

## Evidence retention

Keep union23 immutable and retain all valid functional conclusions. Coverage of
unchanged source can be reused; changed recovery source requires current-source
qualification only for that file. Existing finalization7, Diagnostic2 and
generic13 current-source PASS groups are not rerun. Historical failed aggregates
are not imported as complete passing raw coverage.

Report overall90, broad-core-v1, risk-core-v2, UI and critical-scenario status
separately using sums of native covered/total branches. Missing source mappings
or source-hash mismatch mean INCOMPLETE. Zero branches mean N/A. Preserve source,
test candidate, raw data, exact argv, terminal status and original attribution.

## Replay Diagnostic reference convergence, 2026-09-21

Accepted integration base: `79cf67334e2b78463dc4a3f70d809d35557b250f`.
Design owner: primary conversation; implementation and affected tests: existing
Luna/max Recovery owner; independent design and complete-diff review: existing
native reviewer. This is a bounded public-contract correction, not a coverage
exception. The primary freezes the following complete contract for implementation;
independent review may return a concrete finding and must accept the final diff
before integration. The two failed fixture rounds remain one convergence history.

The public Diagnostic producer emits any 32 lowercase hexadecimal characters.
Wave11 run3 produced `b9e8a8ae0a2fa22d66d7d85946bf9eaf`. Acceptance checkpoint
CLI/MCP advertise that domain, but the replay adapter and immutable attempt
model require RFC UUID version/variant nibbles. Inserting hyphens preserves the
ID and still fails. The final replay record workflow has the related restriction.
The same split exists in the genuine 0.9 baseline. Treat this as PRODUCT_CONTRACT;
do not patch a private ID factory or change ID bits to make a fixture pass.

The single representation for replay Acceptance Diagnostic references
is lowercase `8-4-4-4-12` grouping of the exact 128 identity bits, without UUID
version/variant semantics. Public replay inputs accept that representation and
the Diagnostic producer's compact 32-hex spelling, and normalize before any
retry, comparison, digest, or publication. Persisted replay models require the
grouped canonical spelling. Existing canonical UUID references therefore retain
their exact bytes, digests, authorization bindings, and idempotency results.
Diagnostic storage lookup removes only hyphens; identity equality remains exact.
No migration, alias index, rewritten evidence, or new schema is introduced.

This is an explicit 1.0 field-domain correction for `/1` replay attempt and
record schemas: `diagnosticSessionId` is a DiagnosticSessionRef, not an RFC UUID.
All supported 1.0 readers and writers change together: checkpoint input,
immutable stage outputs, source-change authorization, show/resume, after-build
revalidation, record create/show/retry, and final checkpoint equality. CLI and
MCP record inputs as well as checkpoint inputs use the dedicated domain; their
other UUID parameters do not change. This amendment takes precedence over older
wording that calls this specific field a UUID.

Compatibility is backward reading, not forward reading: 1.0 reads existing 0.9
records without rewriting them. A 0.9 consumer may reject a new 1.0 reference
whose version/variant nibbles are not RFC UUID nibbles; an unchanged schema label
does not promise otherwise. Such readers are not supported consumers of newly
created 1.0 replay evidence. Repair preserves the original 0.9 runtime and data;
rollback/recovery retains the appropriate original state and must not translate
new identities, rewrite evidence, or bypass the existing downgrade refusal.
Deployment compatibility notes must state this boundary. Final package validation
must distinguish old-data preservation from unsupported old-reader/new-data use.

Only `diagnosticSessionId` in replay Acceptance uses this domain. Other UUIDs,
Diagnostic's compact producer/storage contract, physical/continuation/finalization
schemas, source-change authorization, stage ordering, and error codes remain
unchanged. Physical dispatch still enforces its compact-only contract. Invalid
shape/type/case is rejected at the existing boundary with no evidence writes;
a different valid ID must still fail authoritative reference/identity checks.

Four runnable scenarios define completion:

1. A public Diagnostic producer's compact ID crosses replay checkpoint,
   show/resume, source-change authorization, final record, and final checkpoint.
2. Compact/grouped aliases address one identity and retry without extra roots;
   old canonical UUID records and checkpoints reload byte-for-byte unchanged.
3. Malformed or wrong valid IDs fail with existing errors and no publication;
   unrelated UUID and physical ID domains retain their existing restrictions.
4. Corrupt persisted ancestry is refused without writes; exact restoration makes
   the same public show/resume/checkpoint path usable again.

Non-goals: new recovery features, new hardware operations, general identity or
test frameworks, new dependencies, changing Diagnostic ID generation, weakening
evidence validation, or lowering any release/coverage threshold. Any accepted
product correction supersedes RC1 product identity; its failed build and prior
source qualification remain historical evidence within their original scope.
