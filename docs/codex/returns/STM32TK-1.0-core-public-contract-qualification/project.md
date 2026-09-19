# STM32TK 1.0 core project public contract qualification and root correction

## Scope

This slice adds one bounded public-contract qualification wave for project
creation authorization, CubeMX native identity validation, project
configuration apply identity, and regeneration authorization/provider failure
paths. The tests use the existing public stores, workflow adapters, parser,
project factories, native fixture, and fake CubeMX/build seams. They assert
stable public error codes or exact messages, authorization state transitions,
no unexpected provider dispatch, unchanged destination bytes, and settled
regeneration roots. The review correction also snapshots both persisted
authorization records after each malformed-request refusal, checks that every
new post-claim regeneration refusal leaves the capability `consumed`, covers a
public adapter setup failure, and exercises invalid candidate ownership rows
through the public regeneration prepare workflow.

The first bounded Project run exposed a root-classification contract
contradiction: a missing plan root was reported as
`GENERATION_APPLY_FAILED` during lock setup instead of the documented
`GENERATION_PLAN_INVALID`/`projectRoot` result. The correction validates the
existing canonical-root guard before entering the shared mutation lock,
retains the under-lock validation for drift, and strengthens the public root
test to prove no lock entry or writes.

The follow-up run exposed only a test-fixture assertion issue after the public
contract correction passed: `write_project` does not create `CMakeLists.txt`,
so the root-refusal test now snapshots the genuine `Src/main.c` fixture bytes
and asserts those bytes remain unchanged.

The accepted qualification source base is `0a6bf2a6c591e5e89c6451050de3087168b77eb4`.
The worktree is `D:\codex-tmp\v10b-0918\r10\c95p` on
`codex/STM32TK-1.0-core-project`. The corrected product/test code head before
this report commit is `5096ff8a1be00ec06cc41dd89dc125e1dc7b304c`. The prior
release runtime identity was `a270d7332c3ad2d09cd0b9adfa96ca80042bcf9d`; this
correction changes only `generation/configure.py` from that identity.

Only these existing product/test files changed in the bounded correction and
qualification wave:

- `tools/stm32-toolkit/src/stm32_toolkit/generation/configure.py`
- `tools/stm32-toolkit/tests/test_creation_authorization.py`
- `tools/stm32-toolkit/tests/test_creation_apply.py`
- `tools/stm32-toolkit/tests/test_cubemx_project.py`
- `tools/stm32-toolkit/tests/test_generation.py`
- `tools/stm32-toolkit/tests/test_regeneration_workflows.py`

No schema, shared fixture, dependency, coverage configuration, installation,
build, hardware, package, deployment, or remote state changed. Existing
migration and tool-support public variants were reviewed and retained where
they already represented the meaningful caller paths; no duplicate cosmetic
cases were added.

## Public triggers and assertions

| Public selector | Trigger and residual guard | Expected result and state assertion |
| --- | --- | --- |
| `test_creation_authorization.py::test_peek_is_non_consuming_before_the_single_use_claim` | `CreationAuthorizationStore.peek` followed by one public `consume` | Peek leaves the persisted record `prepared`; exactly one later consume succeeds and the record settles to `consumed`. |
| `test_creation_authorization.py::test_persisted_request_shapes_are_rejected_before_authorization` | Rehashed persisted requests with non-object shape, extra source key, forbidden MCU/board hash, invalid IOC hash, and unknown source kind | Both public `peek` and `consume` return `CREATION_AUTHORIZATION_INVALID`; the original valid record and forged record bytes/state are unchanged after each refusal. Lock bookkeeping is not treated as product state. |
| `test_cubemx_project.py::test_native_parser_rejects_request_language_or_framework_drift` | `parse_native_project` receives a C++ request for a C native IOC or an LL request without an LL selection | `CUBEMX_NATIVE_OUTPUT_INVALID` with the exact public message; no project manifest is written. |
| `test_generation.py::test_apply_rejects_plan_root_that_is_not_a_project_directory` | `apply_project_configuration` receives a plan whose public project root is missing or a regular file | `GENERATION_PLAN_INVALID` with `{"rule": "projectRoot"}` before lock entry; original project/file bytes remain unchanged and no target or staging state is created. |
| `test_creation_apply.py::test_adapter_factory_failure_is_typed_without_dispatch_or_owned_roots` | Public creation apply receives an adapter factory that raises an unexpected setup exception after a valid environment digest | `CUBEMX_EXECUTION_ENVIRONMENT_CHANGED`; CubeMX is not dispatched and no generation or activation root is left behind. |
| `test_regeneration_workflows.py::test_apply_rejects_execution_environment_drift_before_generation` | `apply_regeneration_workflow` receives a prepared capability and a changed environment digest | `REGENERATION_GENERATOR_DRIFT`; the CubeMX adapter is not called, the destination remains byte-identical, and the public authorization store reports `REGENERATION_AUTHORIZATION_CONSUMED`. |
| `test_regeneration_workflows.py::test_apply_rejects_authorization_bound_destination_before_generation` | Apply uses a destination different from the one bound into the prepared capability | `REGENERATION_AUTHORIZATION_INVALID`; no adapter call, no regeneration root, and the public authorization store reports `REGENERATION_AUTHORIZATION_CONSUMED`. |
| `test_regeneration_workflows.py::test_apply_supported_build_failure_preserves_destination_and_settles_roots` | The injected public build seam fails at `arm-debug` or `arm-release` after candidate staging | Exact `REGENERATION_DEBUG_BUILD_FAILED` or `REGENERATION_RELEASE_BUILD_FAILED`; the expected build sequence is observed, the original destination is unchanged, generation/activation/backup roots are absent, and the capability is `consumed`. |
| `test_regeneration_workflows.py::test_prepare_rejects_invalid_candidate_ownership_manifest_before_authorization` | Public prepare receives a fake candidate whose ownership manifest has an unsafe path or duplicate path | `REGENERATION_OWNERSHIP_INVALID`; the destination is unchanged, no preview root remains, and no authorization record is issued. |

The parameterized selectors expand only to the declared finite alternatives:
six persisted-request rows, two native identity rows, two project-root rows,
one adapter setup failure, two ownership-manifest rows, and two build-provider
rows.

## Exact residual accounting

The pre-correction project source pool has 26 files and 588 missing branches
in the retained Toolkit union. That number is an upper bound from the existing
source-identity and coverage evidence, not a target or claimed gain. The
complete machine-readable map is retained at
`D:\codex-tmp\v10b-0918\r10\e\core95\project\residual-map.json` with SHA-256
`9554AEFD028434445345B23D8AC6514D26659B6F1368C124908A7F86CF63FF19`. It
contains every missing arc as an explicit `from`/`to` pair, source hash,
function-level missing arcs, exact guard family, existing public test
evidence, wave selectors, and the remaining disposition. The input was the
retained Toolkit coverage JSON at
`D:\codex-tmp\v10b-0918\r10\e\python-final\toolkit-reconciled-r1\coverage.json`,
not a new run. Because `generation/configure.py` changed in the bounded root
correction, old arcs for that file must be purged from copied inputs before
the primary-owned native union; run3 supplies its current arcs because run2
stopped before producing coverage data.

| Project source file | Missing | Covered | Total |
| --- | ---: | ---: | ---: |
| `tools/stm32-toolkit/src/stm32_toolkit/build/identity.py` | 11 | 159 | 170 |
| `tools/stm32-toolkit/src/stm32_toolkit/build/map_file.py` | 2 | 96 | 98 |
| `tools/stm32-toolkit/src/stm32_toolkit/build/runner.py` | 15 | 101 | 116 |
| `tools/stm32-toolkit/src/stm32_toolkit/creation_apply.py` | 39 | 65 | 104 |
| `tools/stm32-toolkit/src/stm32_toolkit/creation_authorization.py` | 44 | 50 | 94 |
| `tools/stm32-toolkit/src/stm32_toolkit/creation_environment.py` | 39 | 101 | 140 |
| `tools/stm32-toolkit/src/stm32_toolkit/creation_workflows.py` | 4 | 14 | 18 |
| `tools/stm32-toolkit/src/stm32_toolkit/cubemx_adapter.py` | 32 | 76 | 108 |
| `tools/stm32-toolkit/src/stm32_toolkit/cubemx_project.py` | 50 | 110 | 160 |
| `tools/stm32-toolkit/src/stm32_toolkit/generation/configure.py` | 42 | 398 | 440 |
| `tools/stm32-toolkit/src/stm32_toolkit/generation/creation.py` | 12 | 56 | 68 |
| `tools/stm32-toolkit/src/stm32_toolkit/generation/managed_files.py` | 3 | 63 | 66 |
| `tools/stm32-toolkit/src/stm32_toolkit/keil/armcc_scan.py` | 7 | 113 | 120 |
| `tools/stm32-toolkit/src/stm32_toolkit/keil/baseline.py` | 6 | 70 | 76 |
| `tools/stm32-toolkit/src/stm32_toolkit/keil/model.py` | 3 | 11 | 14 |
| `tools/stm32-toolkit/src/stm32_toolkit/keil/uvprojx.py` | 25 | 221 | 246 |
| `tools/stm32-toolkit/src/stm32_toolkit/migration/apply.py` | 14 | 172 | 186 |
| `tools/stm32-toolkit/src/stm32_toolkit/migration/git_guard.py` | 1 | 9 | 10 |
| `tools/stm32-toolkit/src/stm32_toolkit/migration/model.py` | 1 | 19 | 20 |
| `tools/stm32-toolkit/src/stm32_toolkit/migration/planner.py` | 12 | 114 | 126 |
| `tools/stm32-toolkit/src/stm32_toolkit/migration/rules.py` | 17 | 143 | 160 |
| `tools/stm32-toolkit/src/stm32_toolkit/project_model.py` | 9 | 137 | 146 |
| `tools/stm32-toolkit/src/stm32_toolkit/project_upgrade.py` | 9 | 125 | 134 |
| `tools/stm32-toolkit/src/stm32_toolkit/regeneration.py` | 63 | 113 | 176 |
| `tools/stm32-toolkit/src/stm32_toolkit/regeneration_workflows.py` | 78 | 116 | 194 |
| `tools/stm32-toolkit/src/stm32_toolkit/tool_support.py` | 50 | 198 | 248 |
| **Total** | **588** | **2,850** | **3,438** |

The remaining priority functions are accounted for explicitly in the map:
`creation_apply.apply_creation` (16 branches) now includes the public adapter
setup failure and retains cleanup/activation alternatives for primary
re-measurement; `generation.configure._validate_plan` (14) is reached by the
existing forged-plan public apply matrix and the new root case;
`cubemx_project.parse_native_project` (14) is covered by its parser identity
matrix plus the new language/framework cases; `regeneration.apply` (13) and
`prepare` (10) are covered by the drift/provider/ownership selectors;
`creation_authorization.peek` (12) is covered by malformed persisted request,
tamper, and replay cases; `regeneration._validate_ownership_manifest` (12) is
reached through public prepare with unsafe and duplicate rows;
`build.runner._require_managed_configuration` (11) is covered by the existing
public managed-manifest/schema/ownership matrix. The other map rows classify
their exact guards as already covered public variants, unreachable after an
earlier public invariant, or native/platform-only filesystem, process, Git,
Keil, and tool discovery behavior; none is presented as measured coverage.

## Verification

The initial bounded Project run at `e22d858494cdc8135052f8ac066d8ee370f8c0a4`
retained 10 passes and one failure with child/launcher exit 1 and no timeout.
The first failure was
`test_apply_rejects_plan_root_that_is_not_a_project_directory[missing]`:
`GENERATION_APPLY_FAILED` with `phase=projectMutationLock` was returned before
the correction. Its retained evidence is under
`D:\codex-tmp\v10b-0918\r10\e\core95\project\run1`, including the JUnit,
stdout, process metadata, and failure classification.

Run2 at `72e6ac246c2d9b8f7e2a6df409de558c4f5e87db` retained 228 passes and one
test assertion failure, with two warnings, child/launcher exit 1, and no
timeout. The public root correction returned the exact expected code/details,
entered no lock, and left the fixture tree and owned state unchanged. The
failure was the test's assertion that the untouched fixture contained
`CMakeLists.txt`; that file is created only by a successful apply and is not
written by `write_project`. Run2 evidence is retained under
`D:\codex-tmp\v10b-0918\r10\e\core95\project\run2`.

Run2 produced no raw `.coverage` file or `coverage.json` because `-x` stopped
at that first assertion; no coverage result or percentage is inferred. The
two retained `PytestUnhandledThreadExceptionWarning` diagnostics came from
the existing staging-root and staging-intermediate escape tests: Windows
subprocess reader threads attempted UTF-8 decoding of non-UTF-8 diagnostic
bytes. The affected tests passed; this is retained as an environment/
diagnostic encoding warning with no product or scope change.

The correction head was checked with AST parsing only. No product import,
collect-only run, build, install, hardware action, package, deployment, remote
action, or cleanup was performed after the run2 result. Primary owns the
bounded run3 selected-node pytest execution, complete accepted-base-to-head
review, raw coverage, JUnit, failure classification, and cleanup. Run3 must
select the failed generation function, every remaining module-level generation
test function after it in AST order, and the same four regeneration functions;
the 228 run2 passes are not rerun.

AST syntax inspection completed without importing Toolkit product modules:

```text
C:\Program Files\PowerShell\7\pwsh.exe -NoProfile -File D:\codex-tmp\v10b-0918\r10\t\c95\p\ast-check.ps1
D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe -I -c <ast.parse only; no product imports> <five owned test paths>
AST_OK <five owned test paths>
exit code: 0
```

The exact AST stdout, stderr, command, environment bindings, and exit code are
retained under `D:\codex-tmp\v10b-0918\r10\e\core95\project`.
`TEMP`, `TMP`, and `TMPDIR` were bound under
`D:\codex-tmp\v10b-0918\r10\t\c95\p` before starting Python. No pytest,
collect-only run, product import, build, install, hardware action, package,
remote action, or cleanup was performed.

The correction-only AST check also parsed
`tools/stm32-toolkit/src/stm32_toolkit/generation/configure.py` and
`tools/stm32-toolkit/tests/test_generation.py` with exit code 0. Its command,
environment, stdout, stderr, and exit code are retained as
`D:\codex-tmp\v10b-0918\r10\e\core95\project\correction-ast-*`.

## Retained barriers and acceptance boundary

The residual native denominator still includes real CubeMX/toolchain behavior,
Windows reparse and symlink privilege paths, native process/handle races,
fsync/crash and concurrent filesystem races, and hardware-dependent behavior.
The fake adapter and injected configure/build seams prove the supported public
software transaction and error boundary only. The reconciled Toolkit native
union remains the primary source for branch acceptance; the project pool's 588
missing arcs are an upper bound rather than a quota, and this report claims no
coverage gain before the primary-owned run.

Independent review of the complete accepted-base-to-code-head diff and final
qualification remain with the primary agent. This implementation agent does
not accept its own changes.
