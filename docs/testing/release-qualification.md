# Release qualification

This is the current qualification contract consolidated from the accepted risk-layered design.
The [standard procedure](standard-test-procedure.md) governs execution and authorization;
[release status](../release-status.md) preserves the fixed v1.0.0 result and its limitations.
Historical measurements and one-time exceptions do not transfer automatically to a later release.
The user's explicit v1.0.1 conditional exception is recorded below, separately from permanent gates.

## v1.3.6 measured candidate — 2026-10-31

Subsequent publication: formal Latest Release429783935 is public at 2026-10-31T07:22:13Z; all13 exact frozen assets passed anonymous HTTP200 download size/SHA256 verification. See the [publication acceptance](../codex/returns/STM32TK-136/publication-2026-10-31.md). The candidate-specific exception and permanent unmet gates below are unchanged. Publication guidance is ACCEPTED_WITH_FIXES at119fe0b0 after29 bound checks and5 overlapping final affected rechecks; the explicitly authorized four-file closeout passed native audit, while both original abnormal invocations remain unaccepted. No new hardware or recipient-installation acceptance.

Subsequent explicit user authorization: **USER_APPROVED_EXCEPTION /
CONDITION_MET_NON_REGRESSION**, only for frozen source
`b00cbc4edee191712dd6da7e1beb073ff4a74f28` and its 13 verified files. Each native
scope is no lower than v1.3.5; UI's unchanged-source/per-file evidence is retained.
See the [candidate-specific authorization](../codex/returns/STM32TK-136/authorization-2026-10-31.md).
Permanent floors, unmet results, skips, original failures and final user
installation/IDE limitations remain unchanged. The measurement-time checkpoint
below is retained; it predates this approval and is not the current disposition.

Frozen source `b00cbc4edee191712dd6da7e1beb073ff4a74f28` has complete source-bound software evidence and reproducible
13-file packages. Current state: **COVERAGE_DECISION_PENDING**. No v1.3.6 coverage exception
has been authorized; permanent gates and prior exceptions below are unchanged.

| Scope | Native branches | Permanent floor | Result | v1.3.5 comparison only |
| --- | --- | --- | --- | --- |
| toolkit-overall | 16414/18836 (87.1416%) | 90% | UNMET | NOT_LOWER |
| toolkit-risk-core-v2 | 15281/17496 (87.3400%) | 90% | UNMET | NOT_LOWER |
| monitor-overall | 3293/3564 (92.3962%) | 90% | PASS | NOT_LOWER |
| monitor-risk-core-v2 | 3293/3564 (92.3962%) | 95% | UNMET | NOT_LOWER |

UI reuses exact unchanged source evidence 2938/3147 with per-file90 met. See the
[implementation report](../codex/returns/STM32TK-136/implementation-report.md)
and [native/source evidence](../codex/returns/STM32TK-136/integration-evidence.json).
Comparison alone grants no exception, installation, hardware or publication acceptance.

## v1.3.5 coverage non-regression exception authorized on 2026-10-30

The user explicitly permits a v1.3.5-only coverage exception provided coverage is
no lower than the previous release. The exact v1.3.4 native branch baselines are
Toolkit overall15336/18534, Toolkit risk-core-v2 14208/17194, Monitor overall and
risk-core-v2 each3292/3564, UI overall2938/3147. Compare each applicable group
separately using exact ratios and unchanged measurement/membership rules, with
new/changed in-scope source included. Existing UI per-file rules remain.
See the [authorization and comparison contract](../codex/returns/STM32TK-135/coverage-authorization-2026-10-30.md).
Status is **CONDITION_MET_NON_REGRESSION** at reviewed CodeHead `fa3613cb7b24a0f0532aff5248acb9ad919a112a`: Toolkit15530/18734 and14399/17394, Monitor3292/3564 for both groups, UI2938/3147 with per-file90 met. See the [current evidence](../codex/returns/STM32TK-135/integration-evidence.json). This meets the user-authorized coverage condition; it is not permanent-gate or release acceptance.
Permanent gates remain separately reported. Behavior, evidence and applicable
integration/package/install checks are not waived; no installation, hardware or
remote action is authorized by this exception.

## v1.3.4 frozen-candidate exception authorized on 2026-10-28

The user explicitly approved **USER_APPROVED_EXCEPTION** and Latest publication
only for `a7db6a8cc3ecdab53ef0b52cb80b54cbadcacead` and its 13 reproducible verified files.
Toolkit overall/risk82.7452%/82.6335% remain below90%; Monitor risk92.3681% remains
below95%. Exact-source reuse, original failures and bounded passing comparisons,
platform/historical-data skips and unverified actual vendor generation remain
separate disclosed limits. Permanent floors and membership remain unchanged;
no exception transfers or converts an unmet gate into PASS. Final installation/
VS Code is USER_VALIDATION_PENDING, owned by the user; no original-project or
physical hardware operation is authorized. See the [specific authorization](../codex/returns/STM32TK-134/authorization-2026-10-28.md)
and [frozen inventory](../codex/returns/STM32TK-134/candidate-build.md).
Publication is complete: [v1.3.4 is Latest](../codex/returns/STM32TK-134/publication-2026-10-28.md). All13assets were anonymously downloaded and rehashed; final recipient installation/VS Code remains pending.

## v1.3.3 frozen-candidate exception authorized on 2026-10-27

The user explicitly approves **USER_APPROVED_EXCEPTION** and Latest publication only
for `46ca09084bbe39f670714d19d7d55f9365ef06be` and its 13 reproducible verified files.
Toolkit overall/risk are 82.5877%/82.4231% below 90%; Monitor risk is 92.3681% below
95%. The original Monitor performance failure and subsequent passing bounded
comparisons remain separate evidence. Exact-source reuse, platform/historical-data
skips and unverified actual CubeMX vendor generation are disclosed, not a final-head
full rerun. Permanent thresholds and membership are unchanged; no exception transfers.
Final installation/VS Code remains **USER_VALIDATION_PENDING**, owned by the user;
original project/hardware access remains prohibited. See the
[specific authorization](../codex/returns/STM32TK-133/authorization-2026-10-27.md)
and [frozen build record](../codex/returns/STM32TK-133/candidate-build.md).
Publication is complete: [v1.3.3 is Latest](../codex/returns/STM32TK-133/publication-2026-10-27.md). All 13 assets were anonymously downloaded and rehashed; final user installation/VS Code remains pending.

## v1.3.2 frozen-candidate exception authorized on 2026-10-26

Publication is complete: [v1.3.2 is Latest](../codex/returns/STM32TK-132/publication-2026-10-26.md).
All 13 public files were anonymously downloaded and rehashed against the frozen
candidate. Final user installation/VS Code checks remain pending; publication
does not convert them or the disclosed limits into PASS.

The user explicitly approved **USER_APPROVED_EXCEPTION** and publication as Latest
only for frozen source `acb71b9f39e8ae4799179b0cab088245c0a5ea5b`, with 13
reproducible verified files. The Windows ZIP is 113,770,074 bytes, SHA-256
`1773a5e6b61a882bbd3d77a2a23902bd24f88ed296fb6e12dfccc03594c77f79`.
Approved disclosed limits: Toolkit overall 15381/17618 = 87.3028%, Toolkit
risk-core-v2 14310/16354 = 87.5015%, Monitor risk-core-v2 3227/3498 = 92.2527%,
retained platform/historical-data skips, and explicit source-bound reuse rather
than a single final-head full rerun. Permanent floors and scope remain unchanged;
this exception neither turns unmet gates into PASS nor transfers to another
candidate. Final actual installation/VS Code remains user-owned and
**USER_VALIDATION_PENDING**; original project/hardware actions remain prohibited.
See [authorization](../codex/returns/STM32TK-132/authorization-2026-10-26.md) and
[frozen build evidence](../codex/returns/STM32TK-132/candidate-build.md).

## v1.3.1 frozen-candidate exception authorized on 2026-10-26

The user subsequently explicitly requested publication as v1.3.1 and Latest
before their independent installation/VS Code testing. Publication is complete;
that final user testing remains USER_VALIDATION_PENDING, not PASS. The
[public verification record](../codex/returns/STM32TK-131/publication-2026-10-26.md)
binds the release, frozen source and all 13 downloaded assets. This ordering
decision preserves the disclosed limits and permanent gates below.

The user explicitly approved **USER_APPROVED_EXCEPTION** only for frozen source
`7ff99e50011b6321ae3f0c9bb2edfab91724be3e` and its reproducible 13-asset v1.3.1
candidate. The Windows ZIP is 113,475,542 bytes with SHA-256
`ec3eb4e9ccadecd832c570288b3449a5b6553b260cd734e1ac82dfc647fe6a08`.
The accepted disclosed limits are Toolkit overall 15,380/17,606 = 87.3566%,
Toolkit risk-core-v2 14,309/16,342 = 87.5597%, Monitor risk-core-v2
3,227/3,498 = 92.2527%, 19 retained platform/historical-data skips, and explicit
source-bound reuse rather than a single final-head full rerun. Original failures,
corrections, raw coverage and actual owner/source identities remain retained.
Permanent floors and membership below are unchanged; this exception does not
transfer to a different candidate or convert unmet gates into PASS.

The user initially required the other acceptance checks to proceed normally and
subsequently took ownership of final actual installation and VS Code verification,
explicitly asking the agent to concentrate on pushing GitHub. Fresh isolated
Check -> Bootstrap -> Check has passed for this frozen package. Final user
installation/IDE acceptance remains USER_VALIDATION_PENDING; it is not PASS and
does not block the newly authorized source push. Upgrade/rollback has no new
PASS. Original firmware-project edits and hardware access remain prohibited.
The user also authorized correcting the earlier mistaken Windows PowerShell5.1
invocation to the existing PowerShell7 without changing execution policy.
See the [frozen build evidence](../codex/returns/STM32TK-131/candidate-build.md)
and [authorization record](../codex/returns/STM32TK-131/authorization-2026-10-26.md).

## v1.2.0-only exception authorized on 2026-10-23

The user explicitly approved **USER_APPROVED_EXCEPTION** for only the frozen Windows x86_64 / CPython 3.12 v1.2.0 package and `v1.2.0` tag source `99e7f000e3ceb773071037f8b8e30f05091ba6fb` (tree `a5cbe6a0c318fad1d7fe3c48c547d88a2ef679bb`), with the limits below disclosed, and authorized its publication as Latest. The public [v1.2.0 Release](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.2.0) contains the verified 13-asset delivery and limitations; the [v1.2.0 execution record](../codex/returns/STM32TK-120/execution.md) identifies the decision, evidence owners and remote verification. This one-version delivery decision does not amend the permanent 90% Toolkit overall/risk-core-v2 and 95% Monitor risk-core-v2 floors below, transfer to another version or source, or grant hardware authorization.

The accepted limits are: Toolkit native overall/broad-core-v1 12,653/14,336 = 88.2603% and risk-core-v2 11,756/13,202 = 89.0471% below 90%; Monitor risk-core-v2 3,161/3,488 = 90.625% below 95%; and the original complete 6,476-node Toolkit matrix with 12 failures and 3 errors. Later 10 corrected tests, 3 fixture nodes and 2 quiet timing nodes passed focused checks, with no complete post-correction matrix. Monitor's original 118.805 ms p95 performance failure and 51.0939 ms quiet repeat PASS remain separate evidence. Interactive browser, IDE/probe and new physical-target qualification have no new v1.2.0 PASS. No original failure is rewritten as PASS; the older v1.0.1 exception remains independent.

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

Before the v1.3.1 measurement, the responsibility review at source
`712bd1721b10618b174b5ea35aef7c3407f48a4b` adds these complete files, with no
removals or changed thresholds: `build/memory_margin.py`, `debug_configuration.py`,
`doctor_readiness.py`, `external_firmware.py`, `extra_regions.py`, `ide_tasks.py`,
`linker_fragment.py`, `memory_layout.py`, `migration/constant_context.py`,
`migration/float_abi.py`, `migration/scoped_includes.py`, `migration/startup.py`,
and `vscode_configuration.py`. They own unique integrity, containment, authority,
safe execution-selection or migration/placement checks. The primary includes
`doctor_readiness.py` for its exact native launcher/layout selection before child
execution, despite its read-only output. `migration/preflight.py` remains
overall-only: it reports advisory readiness, delegates authoritative checks and
never returns an applicable plan ID or mutates. See the pre-measurement
[scope decision](../codex/returns/STM32TK-131/scope.md). No coverage score was used
to select this amendment; all source still enters the overall denominator.

Other Toolkit files are overall-only while they own no unique safety/authority guard. Format
interpretation, descriptions, discovery, templates and ordinary presentation do not by themselves
own authority transitions. A reviewer must reject an omission if the file owns a unique check;
renaming a low-scoring owner as an adapter does not justify exclusion.

Before the v1.3.3 release measurement, the primary's responsibility review at
accepted integration `39497f89e1ad2e2b5af27181af08385b755961b6` adds the complete
files `source_provenance.py`, `migration/delivery.py`, `migration/source_intent.py`
and `build/model.py`. They validate content identity, destination ownership and
delivery boundaries, explicit semantic-change intent, and serialized build identity
inputs. No member is removed and no threshold changes. The
[v1.3.3 release plan](../superpowers/plans/2026-10-27-v133-release-plan.md)
records this decision before measurement; no coverage score selected these files.

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
