# VS07-C safe regeneration implementation report

- Accepted base: `fcdcd1ab9c1f358df78fbfb8b12ed9b0397c534d`
- Product/tests CodeHead before this report commit: `15701023441ad05d11d39120c43c50a3f3857a3c`
- Implementer: one GPT-5.6-luna implementation pass, reasoning max
- Branch/worktree: `codex/STM32TK-0703-SAFE-REGENERATION` /
  `C:/tmp/stm32tk-0703-safe-regeneration`
- Remote, PR, merge, release, hardware, installation: none

## Delivered boundary

The product commit adds the neutral plan/prepare/apply regeneration workflows,
strict schema-3 CubeMX ownership inventory, bounded preview/change digests,
single-use persistent authorization, CubeMX adapter replay, atomic activation
and rollback cleanup, CLI commands, MCP tools, regression tests, and English /
Chinese usage notes. Schema-2/non-CubeMX destinations fail with
`REGENERATION_NOT_CUBEMX_PROJECT`. `App/` and `Tests/` are copied and rehashed;
`build/`, `artifacts/`, and `.stm32-toolkit/build.lock` are disposable.

## TDD evidence

The first focused RED run was executed before adding the core module:

```text
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m pytest tools/stm32-toolkit/tests/test_regeneration.py -q --basetemp C:\tmp\p0703-luna-red
ERROR collecting ... ModuleNotFoundError: No module named 'stm32_toolkit.regeneration'
```

After implementation, the focused regeneration command passed `13 passed`;
the Windows symlink-specific test was `SKIPPED` because this host did not
permit creating a test symlink. The exact approved slice passed `681 passed,
1 skipped` and produced `C:\tmp\p0703-luna-slice.xml` with zero failures and
zero errors. The skipped check is recorded as deferred platform evidence, not
as a physical pass.

The exact slice was:

```text
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m pytest tools/stm32-toolkit/tests/test_regeneration.py tools/stm32-toolkit/tests/test_regeneration_workflows.py tools/stm32-toolkit/tests/test_regeneration_cli.py tools/stm32-toolkit/tests/test_regeneration_mcp.py tools/stm32-toolkit/tests/test_creation_authorization.py tools/stm32-toolkit/tests/test_creation_environment.py tools/stm32-toolkit/tests/test_cubemx_adapter.py tools/stm32-toolkit/tests/test_cubemx_project.py tools/stm32-toolkit/tests/test_creation_apply.py tools/stm32-toolkit/tests/test_creation_workflows.py tools/stm32-toolkit/tests/test_generation.py tools/stm32-toolkit/tests/test_build_runner.py tools/stm32-toolkit/tests/test_migration_plan.py tools/stm32-toolkit/tests/test_migration_apply.py tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_mcp_server.py tools/stm32-toolkit/tests/test_mcp_roots.py -q --basetemp C:\tmp\p0703-luna-slice --junitxml=C:\tmp\p0703-luna-slice.xml
```

`py -3.12 -m compileall -q tools/stm32-toolkit/src tools/stm32-toolkit/tests`
and `git diff --check fcdcd1ab9c1f358df78fbfb8b12ed9b0397c534d..15701023441ad05d11d39120c43c50a3f3857a3c` both passed.

## Fresh native software scenario

Evidence workspace: `C:/tmp/stm32tk-0703-native-evidence/workspace` (local Git
repository with no remote). The captured-IOC project was seeded from the
VS07-B native F429 fixture, `App/fixture.txt` and `Tests/fixture.txt` were
added, and only `ProjectManager.HeapSize=0x200` was changed to `0x300` before
planning. Support and execution facts were discovered from the installed
CubeMX `6.18.1-RC2`, CubeCLT `1.22.0`, and
`C:/Users/ZhangYang/STM32Cube/Repository/STM32Cube_FW_F4_V1.28.3`; no tool was
installed.

- Plan: `OK`, plan ID `af2f65c5bb36744d4dbf69c1ebcee5967de0355ea13a359b53a6f88c9bce6915`, action digest `305838943ba45bada73ca8096f821d57bdbd7170b7c3307d3a3134e4a2c8e140`.
- Prepare: `OK`, one CubeMX invocation, preview digest `659bb7499a6d17de8b791cc29cc6680095b0dac745ced35d27d9434d212f8cbe`, authorization digest `d38f3ddb1d4cd3e3c965b6f5ca4ba2e1ec7108cc90c7098b11b27901c176037c`.
- Apply: `OK`, one replay CubeMX invocation, configure `OK`, Debug `OK`, Release `OK`, ownership manifest SHA-256 `0b0db38cf155f01225f382794ed02c4ed93f612b0312c9cfe5e3784f22864ee0`, attempt `12bbb016b9c4d2cee8b03ac8`.
- `App/fixture.txt`: before/after `5f360513ef957290b48bd9bee4407e2a5dba2fbe08f3c7b07b4346114b755207`.
- `Tests/fixture.txt`: before/after `73a1cb006db02800fdd842c2343c3f3c565c4489a3def8699f2c1e8a077a4e67`.
- The regenerated project contained `generated.ioc` with `ProjectManager.HeapSize=0x300`; no transaction or CubeMX control sibling remained. The derived build lock and build/artifact outputs were recreated by the configure/build stage.
- Pre-existing `javaw` PID `32708` was observed before the scenario and was the only `javaw` PID afterward. It was not terminated. Replay of the same authorization returned `REGENERATION_AUTHORIZATION_CONSUMED` without a third generation.

## Keil read-only refusal

Against a copied schema-2 Keil fixture in
`C:/tmp/stm32tk-0703-keil-evidence/workspace`, public planning returned
`REGENERATION_NOT_CUBEMX_PROJECT`. The recursive before/after tree digest was
`f16c51dbed27f99c8a630007a92c3378a9272c5d24cf9ef66321631698765b8c` on both
sides. No CubeMX call or destination mutation occurred.

## Handoff

The product candidate is committed locally and unpushed. This report records
implementer evidence only; independent complete-diff review and the final
acceptance verdict remain with the GPT-5.6-sol primary agent.
