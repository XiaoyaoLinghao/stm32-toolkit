# Release qualification

This is the current qualification contract consolidated from the accepted risk-layered design.
The [standard procedure](standard-test-procedure.md) governs execution and authorization;
[release status](../release-status.md) preserves the fixed v1.0.0 result and its limitations.
Historical measurements and one-time exceptions are not thresholds for a later release.

## v1.0.1 conditional exception authorized on 2026-10-10

The user explicitly approved an exception for v1.0.1 on condition that coverage is no lower than
published v1.0.0. This is a new, version-specific decision; it does not lower the permanent gates
below or grant installation, hardware, tag or release permission. Compare exact native fractions
before rounding, with the same source membership and collection rules:

| Scope | v1.0.0 minimum fraction |
| --- | --- |
| Toolkit overall / broad-core-v1 | 12047 / 13592 |
| Toolkit risk-core-v2 | 11429 / 12918 |
| Monitor overall / broad-core-v1 / risk-core-v2 | 2770 / 2956 |
| UI aggregate | 784 / 810 |

UI's existing 90% gate for every positive-denominator source file remains required. Denominators
follow actual current source; no exclusions, shifted membership, threshold rounding, or old arcs
on changed source are permitted. Identical source blobs may reuse applicable accepted native data;
current runs may be combined only through native coverage tooling after source binding is verified.
The [candidate qualification record](../codex/returns/STM32TK-101/qualification.md) retains original
results and records whether these new conditions are actually satisfied.

## Permanent gates

Both Python packages retain their complete native branch denominator and 90% overall floor.
Toolkit risk-core-v2 has a 90% floor; Monitor risk-core-v2 has a 95% floor. Toolkit core95 is a
later quality target, not a current release gate. Broad-core-v1 remains separately reported with
its original disposition. No per-file Python minimum, favorable-branch selection, coverage
exclusion, platform removal or after-measurement membership change is allowed.

Select whole source files by responsibility before measuring; mixed files stay whole. Use native
coverage.py branch summaries and relevant subprocess collection. A changed responsibility needs
an explicit scope amendment before measurement. Missing source mapping or hash mismatch means
INCOMPLETE; a zero branch denominator means N/A. New evidence cannot erase original failures.

## Frozen risk-core-v2 membership

Toolkit paths below are relative to `tools/stm32-toolkit/src/stm32_toolkit`:

- Every tracked Python file in `acceptance/`, `diagnostics/`, `evidence/`, and `probe/`.
- `identity.py`, `execution_provenance.py`, `paths.py`, `process.py`, `doctor.py`,
  `tool_support.py`, `creation_environment.py`, `context.py`.
- `creation_authorization.py`, `creation_apply.py`, `creation_workflows.py`,
  `cubemx_adapter.py`, `regeneration.py`, `regeneration_workflows.py`,
  `project_upgrade.py`, `workflows.py`.
- `generation/managed_files.py`, `generation/configure.py`, `generation/creation.py`,
  `migration/apply.py`, `migration/git_guard.py`, `migration/planner.py`,
  `migration/model.py`, `migration/rules.py`.
- `project.py`, `project_model.py`, `cubemx_project.py`, `build/identity.py`, `build/runner.py`.
- `hardware_workflows.py`, `testing_workflows.py`, `diagnostic_workflows.py`,
  `testing/target.py`, `testing/host.py`, `testing/publication.py`, `testing/artifacts.py`,
  `testing/model.py`, `testing/protocol.py`, `testing/native_output.py`, `testing/replay.py`,
  and every tracked Python file in `testing/transports/`.
- `debug/read.py`, `debug/firmware.py`, `debug/fault.py`, `debug/sampling.py`, `debug/model.py`,
  `debug/svd.py`, `debug/dwarf.py`, `monitor_observation.py`, `monitor_replay_contract.py`,
  `monitor_analysis_contract.py`.
- `cli.py`, `mcp_server.py`.

Other Toolkit files are overall-only while they own no unique safety/authority guard. Format
interpretation, descriptions, discovery, templates and ordinary presentation do not by themselves
own authority transitions. A reviewer must reject an omission if the file owns a unique check;
renaming a low-scoring owner as an adapter does not justify exclusion.

For Monitor, all tracked Python source is core except forwarding-only `__init__.py` and
`__main__.py`. Analysis, CLI, models, protocol, groups, exports and UI asset handlers retain
integrity/security behavior and stay in scope.

The UI retains complete-source native coverage and its existing configured per-file gate,
independent of Python. The historical 784/810 measurement can be reused only while the relevant
UI source, coverage configuration and dependencies are unchanged. A changed UI needs current
evidence, plus final bundle checks. Native Windows and physical checks remain separate.

## Required behavior evidence

Percentages do not replace these observable assertions:

| Risk | Required assertion |
| --- | --- |
| Consent, expiry, replay, identity mismatch | Exact refusal, zero dispatch, no improper action consumption |
| Recovery CAS, retry, lineage, corruption | Correct revision/reference, idempotence or refusal, no unauthorized roots |
| Apply/rollback failure | User bytes preserved, effects limited to owned staged files, exact failure |
| Probe timeout/cancel/end | Lease/session settled, owned child terminated and reaped, no hidden retry |
| Monitor import/publication/export | Identity/digest bound, no partial publication or escaping output, correct error |

Use valid public constructors/decoders, stores, workflows and provider protocols. Vary one supported
input or external-provider outcome; do not mock the decision under test, bypass identity validation,
fabricate impossible state or count software fixtures as physical evidence. Internal-pure-unit and
internal-component-io evidence must retain their actual attribution and specific approved scope;
historical bounded test allowances do not open all private APIs or stopped exploration routes.

Report overall90, broad-core-v1, risk-core-v2, UI and critical scenarios separately, using sums of
native covered/total branches. Preserve source identity, test candidate, raw data, command, terminal
status and execution owner. Reuse only still-applicable evidence; do not import failed aggregates
as passing raw coverage. Run packaging, install/upgrade/rollback, native Windows and hardware gates
at release level with explicit applicability and ownership. Missing mandatory external evidence
remains pending; a code failure cannot be deferred as a platform gap.

The original contract is retrievable at Git commit
`694c825d29a55a53052a148efa4cc6720c315a04`, path
`docs/superpowers/specs/2026-09-20-stm32tk-risk-layered-qualification.md`.
