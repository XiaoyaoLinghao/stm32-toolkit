# Core public-contract qualification plan

Accepted base: `0a6bf2a6c591e5e89c6451050de3087168b77eb4`.
Specification: `../specs/2026-09-19-stm32tk-core-public-contract-qualification.md`.
Primary owns scheduling, independent complete-diff review, integration and
cleanup. Each implementation owner is `gpt-5.6-luna` with effort `max`.

## Activation and ownership

The Toolkit-only groups use their independently accepted native union and may
start immediately. Activate the Monitor/evidence group after the pending Monitor
native-data union is independently accepted. Create clean isolated worktrees at
the committed plan head. All runtime sources must remain byte-equal to a270d733. The following four
owners are peers directly dispatched by primary; none recursively delegates.

| Owner | Worktree / branch suffix | Exclusive test responsibility |
| --- | --- | --- |
| Authority | `r10/c95a` / `1.0-core-authority` | Toolkit root tests named `test_acceptance*`, `test_continuation*`, `test_diagnostic*`, `test_fix_verification*` |
| Project | `r10/c95p` / `1.0-core-project` | Toolkit root tests named `test_creation*`, `test_cubemx*`, `test_regeneration*`, `test_project*`, `test_generation*`, `test_migration*`, `test_keil*`, `test_build*`, `test_tool_support.py`, `test_mcp_migration_build.py` |
| Target | `r10/c95t` / `1.0-core-target` | Toolkit root tests named `test_probe*`, `test_testing*`, `test_target*`, `test_debug*`, `test_dwarf*`, plus `test_hardware_workflows.py`, `test_flash.py`, `test_svd.py`, `test_fault.py`, `test_context.py`, `test_doctor.py`, `test_process.py`, `test_mcp_server.py`, `test_mcp_roots.py`, `test_mcp_hardware.py`, `test_cli.py` if present |
| Monitor/evidence | `r10/c95m` / `1.0-core-monitor` | Toolkit root `test_monitor*`, `test_native_analysis_contract.py`, `test_evidence*`; Monitor root `test_analysis.py`, `test_analysis_workflows.py`, `test_analysis_cli.py`, `test_auth.py`, `test_cli.py`, `test_exports.py`, `test_groups.py`, `test_history.py`, `test_models.py`, `test_physical_publication.py`, `test_probe_session.py`, `test_protocol.py`, `test_replay.py`, `test_runtime.py`, `test_sampler.py`, `test_service.py`, `test_storage.py`, `test_ui_assets.py` |

Only existing files matching the table are owned; it does not authorize creating
every named file. One short return report per owner may be added under
`docs/codex/returns/STM32TK-1.0-core-public-contract-qualification/`. Branches have
the required `codex/STM32TK-` prefix. No owner changes shared conftest, fixture
files, schemas, runtime code, dependencies, lockfiles or coverage configuration.
Reuse unchanged existing factories; do not cross-import another owner's new
helpers. Preserve others' edits. Any missing ownership route returns to primary.

## One preparation wave

Use the reconciled native JSON and current source, not guessed percentages or
old line numbers. Existing feasibility notes are hints; private implementation
does not make a supported public-input check ineligible. For each added family,
record its public trigger, expected result, resource/authority assertion and
the uncovered guard group. Group variants by public contract rather than one
test per branch. Omit already accepted behavior with matching evidence.

Implement and inspect syntax only in this wave. No pytest, collect-only, product
imports, installers, build, hardware or cleanup while another owner has the test
execution slot. Return one committed test head, a compact selector list of actual
functions, and a concise residual map. Tests remain NOT_RUN until actual execution.
No framework, generic controller or separate diagnostic package may be added.

## Serial execution and independent acceptance

Primary reviews each full accepted-base-to-returned-head diff in a clean detached
worktree. The independent reviewer cannot be the implementer. Correctable issues
return to the same owner; after two unsuccessful rounds reconsider the contract.

Reuse the existing bounded selected-node launcher. Adapt only source identity,
known function selectors, outputs and proportional timeout; verify its arguments
and environment before release. Do not guess parametrized IDs. Set TEMP, TMP,
TMPDIR before Python. Evidence roots are `r10/e/core95/{authority,project,target,monitor}`;
temporary roots are `r10/t/c95/{a,p,t,m}`. Preserve raw coverage and first failure
evidence. Each current batch has one executor and no concurrent stateful pytest.

Execute newly added/changed functions once. If they pass and product bytes remain
unchanged, reuse other valid tests; do not repeat whole files or the release
matrix merely because tests were added. Stop the failing batch, classify the
actual failure, and retain its successful items. Release independent unaffected
batches without making them wait for unrelated remediation.

Native aggregation uses the existing coverage.py copy/combine approach with
verified source mapping and hashes. It does not sum JSON counts or mix changed
source arcs. Primary accepts the actual result, records exact overall/core gaps
and decides the single remaining-gap disposition. Product defects require a
bounded design and Luna implementation before relevant regression can resume.

Final packaging/deployment remains on hold until qualification is settled.
No push, PR mutation, merge to master, tag or release is authorized by this plan.
