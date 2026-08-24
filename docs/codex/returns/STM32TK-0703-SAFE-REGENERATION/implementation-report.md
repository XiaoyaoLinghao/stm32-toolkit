# VS07-C safe regeneration implementation report

- Accepted base: `fcdcd1ab9c1f358df78fbfb8b12ed9b0397c534d`
- Product/tests CodeHead before this report commit: `b01ece4e11c5db051f1ddbdd569195d9e47c811b`
- Implementer: one GPT-5.6-luna implementation pass, reasoning max
- Branch/worktree: `codex/STM32TK-0703-SAFE-REGENERATION` /
  `C:/tmp/stm32tk-0703-safe-regeneration`
- Remote, PR, merge, release, hardware, installation: none

## Delivered boundary

The product commits add the neutral plan/prepare/apply regeneration workflows,
strict schema-3 CubeMX ownership inventory, bounded complete preview/change
digests, single-use persistent authorization, CubeMX adapter replay, atomic
activation and rollback cleanup, CLI commands, MCP tools, regression tests, and
English / Chinese usage notes. The revision product commit additionally
rehashes `App/` and `Tests/` after configure/build under the activation lock,
rejects candidate ownership blockers, excludes Toolkit-owned paths from
CubeMX-drift checks for both missing and modified paths, hardens no-follow
identity reads (including authorization records), and bounds the complete
public preview representation. Schema-2/
non-CubeMX destinations fail with `REGENERATION_NOT_CUBEMX_PROJECT`.
`build/`, `artifacts/`, and `.stm32-toolkit/build.lock` are disposable.

## TDD evidence

The original focused RED run was executed before adding the core module:

```text
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m pytest tools/stm32-toolkit/tests/test_regeneration.py -q --basetemp C:\tmp\p0703-luna-red
ERROR collecting ... ModuleNotFoundError: No module named 'stm32_toolkit.regeneration'
```

For review round 1, the focused RED run collected 30 tests and failed the 11
newly added boundary/race/precedence cases expected by TDD; its GREEN run
passed 29 with one Windows symlink-specific test skipped. For review round 2,
the focused deletion RED run collected 31 tests and failed the one new
missing-Toolkit precedence case; its GREEN run passed 30 with the same one
platform skip, producing `C:\tmp\p0703-luna-green-r2.xml`. The exact approved
slice contained 699 tests: `698 passed, 1 skipped` with zero failures and zero
errors, producing `C:\tmp\p0703-luna-slice-r2.xml`. The skipped check is recorded as
deferred platform evidence, not as a physical pass.

The exact slice was:

```text
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m pytest tools/stm32-toolkit/tests/test_regeneration.py tools/stm32-toolkit/tests/test_regeneration_workflows.py tools/stm32-toolkit/tests/test_regeneration_cli.py tools/stm32-toolkit/tests/test_regeneration_mcp.py tools/stm32-toolkit/tests/test_creation_authorization.py tools/stm32-toolkit/tests/test_creation_environment.py tools/stm32-toolkit/tests/test_cubemx_adapter.py tools/stm32-toolkit/tests/test_cubemx_project.py tools/stm32-toolkit/tests/test_creation_apply.py tools/stm32-toolkit/tests/test_creation_workflows.py tools/stm32-toolkit/tests/test_generation.py tools/stm32-toolkit/tests/test_build_runner.py tools/stm32-toolkit/tests/test_migration_plan.py tools/stm32-toolkit/tests/test_migration_apply.py tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_mcp_server.py tools/stm32-toolkit/tests/test_mcp_roots.py -q --basetemp C:\tmp\p0703-luna-slice-r2 --junitxml=C:\tmp\p0703-luna-slice-r2.xml
```

`py -3.12 -m compileall -q tools/stm32-toolkit/src tools/stm32-toolkit/tests`
and `git diff --check fcdcd1ab9c1f358df78fbfb8b12ed9b0397c534d..b01ece4e11c5db051f1ddbdd569195d9e47c811b` both passed.

The final verification commands were:

```text
py -3.12 -m compileall -q tools/stm32-toolkit/src tools/stm32-toolkit/tests
git diff --check fcdcd1ab9c1f358df78fbfb8b12ed9b0397c534d..b01ece4e11c5db051f1ddbdd569195d9e47c811b
```

The round-2 product correction is limited to the missing/type branch of
Toolkit-over-CubeMX classification. It does not affect the already-passed
native happy path, which contains all Toolkit files; Sol is responsible for
repeating the final native evidence independently.

## Fresh native software scenario

Evidence workspace: `C:/tmp/stm32tk-0703-native-evidence-r3/workspace` (fresh
local Git repository with no remote). The copied accepted VS07-B captured-IOC
project had the prior owned IOC value `ProjectManager.HeapSize=0x200`; the
scenario changed it to `0x300` before planning and seeded
`App/keep.txt` and `Tests/keep.txt`. Support and execution facts were
discovered from the installed CubeMX `6.18.1-RC2`, CubeCLT `1.22.0`, and
`C:/Users/ZhangYang/STM32Cube/Repository/STM32Cube_FW_F4_V1.28.3`; no tool was
installed.

- Environment digest: `24e69448b12f71273ce9bb03c8c85e245210515c58c60307bf1f80ad73cdf195`; CubeMX executable SHA-256 `db4ca49eea336b819eede7f2a1cea19fff65f2f435aee35efc54ce856b6fae01`; package SHA-256 `9b3230070c1199526d1d3a344eb2a2e628b0c54fb279ef709673a4577ea6d3cc`.
- Plan: `OK`, plan ID `e50ec444c42bdc81877e34fc4b77643a8010cbededdd17bfe352bb4fc6ba7964`, action digest `2aa401d83b38abd0dc49e4fbb52f032483eac19c41ec2a0b4a3c7d608972dfb3`.
- Prepare: `OK`, preview digest `3e63534cc536a2fd0dc1d3cdf971d85ceebb5e309f9f1cb0c2a445266bc13209`, authorization digest `db63dd57b54079d760f77d391a47e0f09107c7f9804e8f8038ebc4cf52c2920f`.
- Apply: `OK`, one replay CubeMX invocation, configure `OK`, Debug `OK`, Release `OK`, ownership manifest SHA-256 `9ddfc1cc378ea83057855717ec170ea50d41fd11f5b6127958c19d601e43000d`, attempt `98562fd76c6671ed8d6f1966`.
- Debug build ID: `0fc47a3a45b08a6364e8ac1aafef9b87dbae587528be764602d99d89f255a864`; Release build ID: `184586217158fee43dd63d0890d9f35720a6c4a6cf3e665c46538dc306ea20b2`.
- `App/keep.txt`: before/after `727948d3d05623d6152720a780545ecc7da8f9fb5a8c2885fe8f565733b8c6dd`.
- `Tests/keep.txt`: before/after `b3c0f9601084c9d578dcf5621fab01ee59fa46957f424c51dee9a5a48dbf4b4c`.
- The regenerated project contained `generated.ioc` with `ProjectManager.HeapSize=0x300`; no `.stm32tk-*` transaction or CubeMX-control sibling remained. The configure/build mutation ledgers and derived build/artifact outputs were created by the existing configure/build stages.
- Pre-existing `javaw` PID `32708` was observed before and after the scenario and remained the only `javaw` PID; PID delta was empty and it was not terminated. Replay of the same authorization returned `REGENERATION_AUTHORIZATION_CONSUMED` without a third generation.

## Keil read-only refusal

Against the copied schema-2 Keil fixture in
`C:/tmp/stm32tk-0703-keil-evidence/workspace`, fresh public planning returned
operation `project-regenerate-plan` / code
`REGENERATION_NOT_CUBEMX_PROJECT`. The recursive before/after tree digest was
`3fe379cf892915a39f4c063704bf757e390b44dd7cfb14bbf35cbd4b5a5cb47c` on both
sides. No CubeMX call or destination mutation occurred.

## Handoff

The product candidate is committed locally and unpushed. This report records
implementer evidence only; independent complete-diff review and the final
acceptance verdict remain with the GPT-5.6-sol primary agent.
