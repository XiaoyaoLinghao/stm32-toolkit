# STM32TK-0702 VS07-B implementation report

## Status and ownership

- Status: `IMPLEMENTED_PENDING_INDEPENDENT_REVIEW`.
- Module/phase: STM32 Toolkit 0.7 / VS07-B authorized creation and build.
- Accepted base: `bff9cc120923b0e9f2ba29a1b3511f1bcc26ab6e`.
- CodeHead before this report/ledger commit:
  `3be836e292f98a231b59afcd1897dd4a7ac90efa`.
- Implementer: `/root/vs07b_implementer`, GPT-5.6-luna, reasoning `max`.
- Independent reviewer/acceptor: GPT-5.6-sol primary agent. The implementer
  does not self-accept this slice.
- Branch/worktree: `codex/STM32TK-0702-CREATION-APPLY` /
  `C:/tmp/stm32tk-0702-creation-apply`.
- Remote authority: none exercised. No push, PR mutation, merge, tag, release,
  close, or remote-branch operation was performed.
- Install/hardware authority: none exercised. No firmware package, software,
  hardware, or CubeMX updater operation was installed or invoked.

## Delivered behavior

Tasks 1–4 were executed sequentially by this one implementer:

1. Added bounded, file-backed, expiring single-use authorization records with
   atomic consume/replay/concurrency semantics, immutable execution-environment
   binding, and read-only preparation re-planning.
2. Added the closed CubeMX adapter: consumed-capability input, sibling Java,
   fixed JVM/process shape, closed environment, bounded protocol handling, and
   bounded native CMake/IOC/linker validation with CubeMX ownership manifests.
3. Added sibling staging, one generation, native validation, configure, Debug
   and Release builds, final destination revalidation, transactional absent/
   empty activation, rollback, and sanitized attempt evidence. Public apply now
   consumes before environment discovery, so an attempted apply cannot leave a
   reusable capability.
4. Added `project create-prepare` and `project create-apply`, the matching
   `stm32_project_create_prepare` and `stm32_project_create_apply` MCP tools,
   exact authorization/schema handling, English/Chinese usage notes, and the
   public regression tests.

The product commits preceding this report commit are `2dbb6c51`, `a4d70db9`,
`72b398d3`, and `3be836e2`; the CodeHead above is the last product/test/docs
commit and deliberately does not include this report or the ledger update.

## TDD RED/GREEN evidence

The tests for each checkpoint were written before the corresponding product
interfaces were edited. The first plan command omitted the repository's
uninstalled source path and produced `ModuleNotFoundError` during collection;
that was classified `ENVIRONMENT`, not a product result. Repeating with
`$env:PYTHONPATH='tools/stm32-toolkit/src'` exposed the intended missing
interface RED failures before each product edit.

- Task 1 RED: the authorization/environment/plan/workflow tests failed at
  collection for the missing authorization/environment interfaces. The green
  focused set was 36 tests at the checkpoint (the final set has 38 tests after
  the IOC source-digest and lifecycle regressions).
- Task 2 RED: adapter/project tests failed at collection for the missing
  `cubemx_adapter` and `cubemx_project` interfaces. Its green set was 329
  tests: 10 adapter, 4 native-project, 39 process, and 276 generation tests.
- Task 3 RED: the integration set failed at collection for the missing
  `creation_apply` interface. Its checkpoint green set was 174 tests; the
  final affected set is 175 after the apply-environment-consumption regression.
- Task 4 RED: CLI/MCP tests failed at collection for the missing public
  prepare/apply adapters. The final public set is 76 tests: 14 creation CLI,
  8 creation MCP, 26 CLI, 15 MCP server, and 13 MCP roots.

## Verification commands and results

All commands below were run from the returned worktree with CPython 3.12.10.
The source-path environment assignment is required because this isolated
worktree is intentionally not installed as a package.

Focused public command:

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m pytest tools/stm32-toolkit/tests/test_creation_cli.py tools/stm32-toolkit/tests/test_creation_mcp.py tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_mcp_server.py tools/stm32-toolkit/tests/test_mcp_roots.py -q --basetemp C:\tmp\p0702-t4-public-final
```

Result: exit 0, 76 passed, 0 failed/error/skipped/xfail, with only the
pre-existing `runpy` warning for `stm32_toolkit.cli`.

Exact complete VS07-B slice file set from the approved plan:

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m pytest tools/stm32-toolkit/tests/test_creation_authorization.py tools/stm32-toolkit/tests/test_creation_environment.py tools/stm32-toolkit/tests/test_cubemx_adapter.py tools/stm32-toolkit/tests/test_cubemx_project.py tools/stm32-toolkit/tests/test_creation_apply.py tools/stm32-toolkit/tests/test_creation_plan.py tools/stm32-toolkit/tests/test_creation_workflows.py tools/stm32-toolkit/tests/test_creation_cli.py tools/stm32-toolkit/tests/test_creation_mcp.py tools/stm32-toolkit/tests/test_process.py tools/stm32-toolkit/tests/test_generation.py tools/stm32-toolkit/tests/test_workflows.py tools/stm32-toolkit/tests/test_build_runner.py tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_mcp_server.py tools/stm32-toolkit/tests/test_mcp_roots.py -q --basetemp C:\tmp\p0702-slice-final4
```

Result: exit 0, 610 passed, 0 failed/error/skipped/xfail. Collection totals
were 83 build-runner, 26 CLI, 5 apply, 7 authorization, 14 creation-CLI, 4
environment, 8 creation-MCP, 19 creation-plan, 8 creation-workflow, 10
adapter, 4 native-project, 276 generation, 13 MCP-roots, 15 MCP-server, 39
process, and 79 workflow tests. The only warning was the same pre-existing
`runpy` warning. `git diff --check
bff9cc120923b0e9f2ba29a1b3511f1bcc26ab6e..HEAD` exited 0 at CodeHead.

Verification classification:

- `PRODUCT`: all source-pinned focused and complete slice tests, typed CLI/MCP
  schemas, replay/concurrency, staging/rollback, protocol, native-parser,
  configure/build ordering, and diff-check evidence above.
- `ENVIRONMENT`: the initial uninstalled-worktree collection failure and the
  real host's absent Cube firmware repository. These do not invalidate the
  product test evidence.
- `REPORT`: no report-format or diff-check failure observed.

## Real-host read-only observation

Disposable workspace: `C:\tmp\p0702-real-observe-final`. No destination or
repository bytes were changed. Commands were:

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m stm32_toolkit.cli doctor --project-root C:\tmp\p0702-real-observe-final --json
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m stm32_toolkit.cli project create-plan --project-root C:\tmp\p0702-real-observe-final --source-kind mcu --source STM32F429ZITx --destination generated --framework hal --language c --json
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m stm32_toolkit.cli project create-prepare --project-root C:\tmp\p0702-real-observe-final --source-kind mcu --source STM32F429ZITx --destination generated --framework hal --language c --plan-id 62659eb96bb4c4afc3b9247064d645a579850894e6d207e8353b06854b5e4865 --action-digest 449899123f48c5a1f6dd0e056be27f6787fdec986f987d7cacf98f9dd1884a92 --json
```

Observed results:

- `doctor`: exit 0; CPython `3.12.10`; creation support found CubeMX
  `6.18.1-RC2` at the registered App Paths location and CubeCLT `1.22.0`
  facts (GCC `14.3.1`, CMake `4.3.1`, Ninja `1.13.2`). The existing doctor
  `STM32CubeMX` tool entry remains unavailable while the creation-support
  resolver safely finds the installed executable.
- `create-plan`: exit 0, `mutated=false`, plan ID
  `62659eb96bb4c4afc3b9247064d645a579850894e6d207e8353b06854b5e4865`, action
  digest
  `449899123f48c5a1f6dd0e056be27f6787fdec986f987d7cacf98f9dd1884a92`, and no
  planning blockers.
- `create-prepare`: child exit 2 (the enclosing PowerShell probe also
  confirmed this with `CHILD_EXIT=2`), typed
  `CUBEMX_REPOSITORY_MISSING`, and no authorization record was issued.
- `C:\Users\ZhangYang\STM32Cube\Repository` was absent and the bounded
  package search found no `STM32Cube_FW_*` directory. The disposable
  `generated` destination remained absent before and after the commands, and
  `Get-Process -Name STM32CubeMX` found no CubeMX process afterward.

This is an `ENVIRONMENT` blocker for positive native acceptance, not a product
PASS or a deferred physical PASS. No positive native `.ioc`/MCU generation,
hardware action, package installation, release matrix, coverage gate, or
VS07-C work was performed.
