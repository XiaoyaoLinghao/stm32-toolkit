# Risk-layered qualification v2

Accepted base: `4bb612beabfdaf1ab4c845b966061832add38482`.
Product source: `8a11caef14df16c5e56c0be2363d4ef5530110eb`.
The user's 2026-09-20 approval authorizes this test reorganization and offline
supplementation. Primary owns specification, scope, integration and acceptance;
Luna/max owns new implementation tests; a separate reviewer checks scope and
diffs. No remote action is authorized by this amendment.

## Three runnable scenarios

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
