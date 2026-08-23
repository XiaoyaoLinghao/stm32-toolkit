# STM32TK-0702 VS07-B implementation report

## Status and ownership

- Status: `IMPLEMENTED_PENDING_INDEPENDENT_REVIEW`.
- Module/phase: STM32 Toolkit 0.7 / VS07-B authorized creation and build.
- Accepted base: `bff9cc120923b0e9f2ba29a1b3511f1bcc26ab6e`.
- CodeHead before this report/ledger commit:
  `fe984f8dcd78f8f2339fa574733dd33e3badc3bf`.
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
`72b398d3`, `3be836e2`, and `fe984f8d`; the CodeHead above is the last
product/test commit and deliberately does not include this report or the
ledger update. Sol's independent round-1 review of the prior candidate
`a493be274f7c857fa7e85ab11964d65854525abc` returned `REVISION_REQUIRED` with
findings F1-F6. `fe984f8d` addresses each finding with product tests written
RED before the corresponding fixes.

## TDD RED/GREEN evidence

Tests were written before each corresponding product edit. The initial
uninstalled-worktree collection failure (`ModuleNotFoundError`) was classified
`ENVIRONMENT`; repeating with
`$env:PYTHONPATH='tools/stm32-toolkit/src'` produced the intended product RED
signals. The review-revision RED/GREEN checkpoints were:

- F1 authorization: an independent-process replay/concurrency test returned
  `['OK', 'OK']` before the durable claim fix, and the forged-capability test
  reached the runner before issuance validation. After the fix, the focused
  authorization/adapter set passed (8 authorization and 15 adapter tests in
  the final slice).
- F2/F3 adapter and privacy: five protocol/source-kind/control-artifact tests
  failed before the closed script, updater binding, and external control-root
  fixes. The final adapter set passed 15 tests, including exact echo/OK/Bye-bye
  validation, source-specific commands, updater binding, and no control bytes
  in the activated product.
- F4 native parser: three tests failed before nested 6.18 CMake parsing and
  strict CPU/FPU/ABI/project-fact validation. The final native-project set
  passed 7 tests, including representative F4/H7 nested fixtures and
  configure-plan synthesis.
- F5 revalidation: drift tests first failed with an unexpected
  `revalidate_plan` argument and then passed after the apply/workflow contract
  was wired; adapter invocation remained zero for IOC and absent-to-empty
  destination drift.
- F6 activation: rollback injection first reproduced the missing-backup-path
  failure and the durable-lock seam was absent; the final apply set passed 14
  tests covering rename/cleanup/rollback injection, restoration, and
  concurrency.
- Public Task 4: CLI/MCP tests were authored before the public adapters and
  passed as the final 76-test public set (14 creation CLI, 8 creation MCP, 26
  CLI, 15 MCP server, and 13 MCP roots).

## Verification commands and results

All commands below were run from the returned worktree with CPython 3.12.10.
The source-path environment assignment is required because this isolated
worktree is intentionally not installed as a package.

Focused public command:

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m pytest tools/stm32-toolkit/tests/test_creation_cli.py tools/stm32-toolkit/tests/test_creation_mcp.py tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_mcp_server.py tools/stm32-toolkit/tests/test_mcp_roots.py -q --basetemp C:\tmp\p0702-r1-public-final --junitxml=C:\tmp\p0702-r1-public-final.xml
```

Result: exit 0, 76 passed, 0 failed/error/skipped/xfail, with only the
pre-existing `runpy` warning for `stm32_toolkit.cli`.

Exact complete VS07-B slice file set from the approved plan:

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m pytest tools/stm32-toolkit/tests/test_creation_authorization.py tools/stm32-toolkit/tests/test_creation_environment.py tools/stm32-toolkit/tests/test_cubemx_adapter.py tools/stm32-toolkit/tests/test_cubemx_project.py tools/stm32-toolkit/tests/test_creation_apply.py tools/stm32-toolkit/tests/test_creation_plan.py tools/stm32-toolkit/tests/test_creation_workflows.py tools/stm32-toolkit/tests/test_creation_cli.py tools/stm32-toolkit/tests/test_creation_mcp.py tools/stm32-toolkit/tests/test_process.py tools/stm32-toolkit/tests/test_generation.py tools/stm32-toolkit/tests/test_workflows.py tools/stm32-toolkit/tests/test_build_runner.py tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_mcp_server.py tools/stm32-toolkit/tests/test_mcp_roots.py -q --basetemp C:\tmp\p0702-r1-slice-final --junitxml=C:\tmp\p0702-r1-slice-final.xml
```

Result: exit 0, 630 passed, 0 failed/error/skipped/xfail. JUnit totals were
83 build-runner, 26 CLI, 14 apply, 8 authorization, 14 creation-CLI, 4
environment, 8 creation-MCP, 19 creation-plan, 10 creation-workflow, 15
adapter, 7 native-project, 276 generation, 13 MCP-roots, 15 MCP-server, 39
process, and 79 workflow tests. The only warning was the same pre-existing
`runpy` warning. `py -3.12 -m compileall -q
tools/stm32-toolkit/src/stm32_toolkit` exited 0. `git diff --check
bff9cc120923b0e9f2ba29a1b3511f1bcc26ab6e..fe984f8dcd78f8f2339fa574733dd33e3badc3bf`
also exited 0 at CodeHead.

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
