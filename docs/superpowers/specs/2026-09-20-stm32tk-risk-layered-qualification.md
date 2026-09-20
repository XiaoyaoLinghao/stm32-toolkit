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
90% floor. Risk-core v2 has a separate 95% floor per package. The v1 broad-core
statistics remain visible under their original name and disposition; a new v2
score does not turn an old unmet v1 target into a PASS. No invented per-file
minimum is added. Critical behavior assertions below are independently required.

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
