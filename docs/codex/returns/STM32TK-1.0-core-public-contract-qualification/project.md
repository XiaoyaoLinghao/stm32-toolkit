# STM32TK 1.0 core project public contract qualification

## Scope

This tests-only slice adds one bounded public-contract qualification wave for
project creation authorization, CubeMX native identity validation, project
configuration apply identity, and regeneration authorization/provider failure
paths. The tests use the existing public stores, workflow adapters, parser,
project factories, native fixture, and fake CubeMX/build seams. They assert
stable public error codes or exact messages, authorization state transitions,
no unexpected provider dispatch, unchanged destination bytes, and settled
regeneration roots.

The accepted source base is `0a6bf2a6c591e5e89c6451050de3087168b77eb4`.
The worktree is `D:\codex-tmp\v10b-0918\r10\c95p` on
`codex/STM32TK-1.0-core-project`. The test code head before this report commit
is `10299383da2dece028929a34acc396c9402e606`. The runtime source identity used
by the release evidence remains `a270d7332c3ad2d09cd0b9adfa96ca80042bcf9d`.

Only these existing test files changed:

- `tools/stm32-toolkit/tests/test_creation_authorization.py`
- `tools/stm32-toolkit/tests/test_cubemx_project.py`
- `tools/stm32-toolkit/tests/test_generation.py`
- `tools/stm32-toolkit/tests/test_regeneration_workflows.py`

No product source, schema, shared fixture, dependency, coverage
configuration, installation, build, hardware, package, deployment, or remote
state changed. Existing migration and tool-support public variants were
reviewed and retained where they already represented the meaningful caller
paths; no duplicate cosmetic cases were added.

## Public triggers and assertions

| Public selector | Trigger and residual guard | Expected result and state assertion |
| --- | --- | --- |
| `test_creation_authorization.py::test_peek_is_non_consuming_before_the_single_use_claim` | `CreationAuthorizationStore.peek` followed by one public `consume` | Peek leaves the persisted record `prepared`; exactly one later consume succeeds and the record settles to `consumed`. |
| `test_creation_authorization.py::test_persisted_request_shapes_are_rejected_before_authorization` | Rehashed persisted requests with non-object shape, extra source key, forbidden MCU/board hash, invalid IOC hash, and unknown source kind | Both public `peek` and `consume` return `CREATION_AUTHORIZATION_INVALID`; malformed request data never becomes an authorization claim. |
| `test_cubemx_project.py::test_native_parser_rejects_request_language_or_framework_drift` | `parse_native_project` receives a C++ request for a C native IOC or an LL request without an LL selection | `CUBEMX_NATIVE_OUTPUT_INVALID` with the exact public message; no project manifest is written. |
| `test_generation.py::test_apply_rejects_plan_root_that_is_not_a_project_directory` | `apply_project_configuration` receives a plan whose public project root is missing or a regular file | `GENERATION_PLAN_INVALID` with `{"rule": "projectRoot"}`; no target or staging state is created. |
| `test_regeneration_workflows.py::test_apply_rejects_execution_environment_drift_before_generation` | `apply_regeneration_workflow` receives a prepared capability and a changed environment digest | `REGENERATION_GENERATOR_DRIFT`; the CubeMX adapter is not called and the destination remains byte-identical. |
| `test_regeneration_workflows.py::test_apply_rejects_authorization_bound_destination_before_generation` | Apply uses a destination different from the one bound into the prepared capability | `REGENERATION_AUTHORIZATION_INVALID`; no adapter call and no regeneration root. |
| `test_regeneration_workflows.py::test_apply_supported_build_failure_preserves_destination_and_settles_roots` | The injected public build seam fails at `arm-debug` or `arm-release` after candidate staging | Exact `REGENERATION_DEBUG_BUILD_FAILED` or `REGENERATION_RELEASE_BUILD_FAILED`; the expected build sequence is observed, the original destination is unchanged, and generation/activation/backup roots are absent. |

The parameterized selectors expand only to the declared finite alternatives:
six persisted-request rows, two native identity rows, two project-root rows,
and two build-provider rows.

## Verification

Test execution is `NOT_RUN` by this implementation wave. Primary owns the
bounded selected-node pytest run, complete accepted-base-to-head review, raw
coverage, JUnit, failure classification, and cleanup.

AST syntax inspection completed without importing Toolkit product modules:

```text
C:\Program Files\PowerShell\7\pwsh.exe -NoProfile -File D:\codex-tmp\v10b-0918\r10\t\c95\p\ast-check.ps1
D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe -I -c <ast.parse only; no product imports> <four owned test paths>
AST_OK <four owned test paths>
exit code: 0
```

The exact AST stdout, stderr, command, environment bindings, and exit code are
retained under `D:\codex-tmp\v10b-0918\r10\e\core95\project`.
`TEMP`, `TMP`, and `TMPDIR` were bound under
`D:\codex-tmp\v10b-0918\r10\t\c95\p` before starting Python. No pytest,
collect-only run, product import, build, install, hardware action, package,
remote action, or cleanup was performed.

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
