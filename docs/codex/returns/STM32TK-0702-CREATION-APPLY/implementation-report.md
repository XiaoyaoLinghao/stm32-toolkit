# STM32TK-0702 VS07-B implementation report

## Status and ownership

- Status: `IMPLEMENTATION_COMPLETE_PENDING_SOL_REVIEW`; the implementer does not self-accept.
- Module/phase: STM32 Toolkit 0.7 / VS07-B authorized creation and build.
- Accepted base: `bff9cc120923b0e9f2ba29a1b3511f1bcc26ab6e`.
- CodeHead before this report/ledger commit: `7bfcba8472ec00c25f37b856c0ff066ab56794f3`.
- Implementer: `/root/vs07b_implementer`, GPT-5.6-luna, reasoning max.
- Reviewer/acceptor: GPT-5.6-sol primary agent.
- Branch/worktree: `codex/STM32TK-0702-CREATION-APPLY` / `C:/tmp/stm32tk-0702-creation-apply`.
- Product commit for the activation integration rewrite: `7bfcba8472ec00c25f37b856c0ff066ab56794f3`.
- Preceding product commits include the native linker ownership integration `14b666e542878bc1045dc75f2d3d4890f0274a99` and bounded cleanup correction `cf908a6720304391abe07588ee462ec26061e130`.
- No push, PR, merge, tag, release, remote operation, hardware action, package installation, or VS07-C work was performed.

## Delivered activation boundary

The final product separates the CubeMX generation container from a distinct
same-volume activation staging sibling. CubeMX receives only the generation
container and can return only its validated destination-leaf child. Native
validation, ownership-manifest seeding, and bounded host-path scanning happen
before relocation. The validated child is atomically renamed to activation
staging, the empty generation container is removed with the existing bounded
20-attempt/50-ms empty-container retry, and only then do configure, Debug,
Release, and final activation receive the activation staging root.

The implementation rejects generation or activation-root collisions without
taking ownership of the colliding path. It cleans only roots created or
received by the current attempt, including both roots and an owned empty
backup on typed failure. It preserves absent/empty destination transactions,
destination revalidation, activation locking, and rollback semantics. There is
no post-build generation-container cleanup or rollback-after-container-cleanup
path.

## TDD RED/GREEN evidence

The recovery work was performed sequentially with a witnessed RED before each
corresponding product change.

Historical native-contract recovery checkpoints retained in this attempt:

- Task 1R adapter RED: `test_cubemx_adapter.py` had 10 failures and 9 passes;
  GREEN was 19 passes.
- Task 2R parser RED: `test_cubemx_project.py` had 6 failures and 10 passes;
  GREEN was 15 passes.
- The native linker ownership rewrite had 5 focused RED tests, then 5/5 GREEN.
- The bounded cleanup correction had focused RED `4 failed, 1 passed`, then
  focused GREEN `5 passed`; the affected apply/workflow set was `41 passed`.

Activation integration RED was added before the final product edit:

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m pytest tools/stm32-toolkit/tests/test_creation_apply.py -k 'relocat or activation_staging_collision or relocation_failure or configure_failure_after_relocation' -q --basetemp C:\tmp\p0702-activation-red2
```

Result: `4 failed, 0 passed`. The failures established that configure still
received the generation child, cleanup ran after configure/build, activation
staging collisions were not rejected, and relocation was not a separate
boundary.

The corresponding GREEN command passed `4 passed` in
`C:\tmp\p0702-activation-green2`. The final focused apply suite passed
`27 passed` in `C:\tmp\p0702-activation-apply-green2`; the directly affected
apply/workflow suite passed `41 passed`, exit 0, with JUnit at
`C:\tmp\p0702-activation-affected2.xml`.

The five new lifecycle tests prove validation and bounded scanning before
relocation, cleanup before configure, configure/build on the activation
root, exactly one pre-build generation cleanup call, collision fail-closed
behavior, relocation failure cleanup, configure failure cleanup, activation
failure cleanup, relative ownership evidence after relocation, and cleanup of
both owned roots. Existing retry tests continue to prove transient, bounded
persistent, and entry-appearing empty-container behavior.

## Final verification

The exact approved 16-file command was run with
`C:\tmp\p0702-rr4-slice` and JUnit `C:\tmp\p0702-rr4-slice.xml`:

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m pytest tools/stm32-toolkit/tests/test_creation_authorization.py tools/stm32-toolkit/tests/test_creation_environment.py tools/stm32-toolkit/tests/test_cubemx_adapter.py tools/stm32-toolkit/tests/test_cubemx_project.py tools/stm32-toolkit/tests/test_creation_apply.py tools/stm32-toolkit/tests/test_creation_plan.py tools/stm32-toolkit/tests/test_creation_workflows.py tools/stm32-toolkit/tests/test_creation_cli.py tools/stm32-toolkit/tests/test_creation_mcp.py tools/stm32-toolkit/tests/test_process.py tools/stm32-toolkit/tests/test_generation.py tools/stm32-toolkit/tests/test_workflows.py tools/stm32-toolkit/tests/test_build_runner.py tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_mcp_server.py tools/stm32-toolkit/tests/test_mcp_roots.py -q --basetemp C:\tmp\p0702-rr4-slice --junitxml=C:\tmp\p0702-rr4-slice.xml
```

Result: `688 tests, 0 failures, 0 errors, 0 skipped`, exit 0. The only
reported warning was the pre-existing `runpy` warning from `test_cli.py`.

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m compileall -q tools/stm32-toolkit/src tools/stm32-toolkit/tests
```

Result: exit 0.

```powershell
git diff --check bff9cc120923b0e9f2ba29a1b3511f1bcc26ab6e..7bfcba8472ec00c25f37b856c0ff066ab56794f3
```

Result: exit 0. Before this report/ledger edit the product worktree was
clean. `codex/STM32TK-0702-CREATION-APPLY` has no upstream configured.

## Real native MCU scenario

This was software/native evidence only; no hardware was used. The fresh
workspace was `C:\tmp\p0702-native-rewrite-mcu3` and the separate data root
was `C:\tmp\p0702-native-rewrite-mcu3-data`. Test setup created a local Git
repository with command-scoped identity, commit
`fc3af925caf1dcb8f126fac88dc0c80a794620a3`, and no remote. The product tree
was clean at `7bfcba84` before the public run.

The public commands were the existing `plan_creation_workflow`,
`prepare_creation_workflow`, and `apply_creation_workflow` APIs, invoked with
`CreationPlanWorkflowRequest(root, data, 'native-rewrite-mcu3', 'mcu',
'STM32F429ZITx', 'generated', 'hal', 'c')`. Plan and prepare returned `OK`.
Their exact identifiers were:

- plan ID: `5e698e2c4afcaf31663ec325956dcdc1455a274f45882d0c76cfaeaf5dcfe05a`
- action digest: `6be30edd55f632a5a7da2c1bb7f7a278e4f2d3963e332a5482b3dd1f4d674415`
- authorization digest: `ecf1d02bc419cae42867fe1d4ae30e885fff97ffe0d9739661bd34545566539b`
- execution-environment digest: `74dd331eadfa1ad4c6f622d477176ec7aae72d07cd0ab18f1549752f075cab62`

The public apply returned `OK`, attempt
`f3bb99fe4ed02e63bdcf6f86`, and ownership-manifest SHA-256
`1ac4e5e62935df9f0e458ed9f17e7e37154cdad1bf539385e6df98009eb50e94`.
Debug and Release both configured and built successfully:

- Debug build ID `3da3a38d3bff4f0954eb0185b2c2a46f255687e36572ef3a0fded11b59c8e02f`, ELF size 1,030,400, map size/identity present.
- Release build ID `a7a1846dec96f0302e192c1dacc111a26bc23cfb1771c5f1225be481b6ad708b`, ELF size 16,768, map size/identity present.
- Native memory facts were RAM 196,608 bytes, CCMRAM 65,536 bytes, and FLASH 2,097,152 bytes; Debug used 1,584 RAM bytes and Release used 1,584 RAM bytes.

The activated output contained 1,562 files. Non-build public bytes had zero
workspace/staging absolute-path hits. No `.stm32tk-*`,
`.stm32-toolkit-cubemx-control-*`, or generation/activation container
remained. The only CubeMX/Java process before and after was pre-existing
`javaw.exe` PID 32708; it was not terminated and no new persistent process
was attributable to the run.

## Real native captured-IOC scenario

The fresh workspace was `C:\tmp\p0702-native-rewrite-ioc3` and data root was
`C:\tmp\p0702-native-rewrite-ioc3-data`. The captured source was
`C:\tmp\p0702-native-capture-r8\generated-staging\STM32F429ZITx\STM32F429ZITx.ioc`.
It was copied once to the portable relative path
`input/STM32F429ZITx.ioc`; source and copied bytes both had SHA-256
`636e9c2de3921db06e855c8180d6d701efda66c2db1b9e6e534dc135cb34d2b0`.
Test setup created local Git commit
`0d5fd998592c7c4bf49409b6655c405ea59a870c` with no remote. The product tree
was clean at `7bfcba84` before this public run.

The public request was
`CreationPlanWorkflowRequest(root, data, 'native-rewrite-ioc3', 'ioc',
'input/STM32F429ZITx.ioc', 'generated', 'hal', 'c')`. Plan and prepare
returned `OK` with:

- plan ID: `713e99003b4680a37d5301f4a3daa304a98e40b4997fce030f876b1ea0cf748a`
- action digest: `82acd98b65f365a5b80b38a8083308f040cd74f76177123ffaf1f79b545f83a4`
- authorization digest: `f4797a276ceb574dcde792d5920674fcfde54b44ebb79ee1c45c680090613e2a`
- execution-environment digest: `24e69448b12f71273ce9bb03c8c85e245210515c58c60307bf1f80ad73cdf195`

The public apply returned `OK`, attempt
`d7560a5648cc402ad59aa587`, and ownership-manifest SHA-256
`45b0fa563078133012d54842297274b9d0c27df6d9db04a7a0176aa328d40983`.
Debug and Release both configured and built successfully:

- Debug build ID `1c3e9502eeb7a046d32a5a7020f93cfa1013050f6b2930ce9fa084dcd0d98549`, ELF size 1,030,400.
- Release build ID `267af93c4b619bdbc0840618201d1f3edd8864f1ac3a087bd2a321dcd7f1b63f`, ELF size 16,768.
- Native memory facts matched the MCU scenario: RAM 196,608 bytes, CCMRAM 65,536 bytes, FLASH 2,097,152 bytes; Debug used 1,584 RAM bytes and Release used 1,584 RAM bytes.

The activated output contained 1,562 files and zero non-build workspace/
staging absolute-path hits. No control, generation, or activation container
remained. PID delta was unchanged: only pre-existing Java PID 32708 remained;
no CubeMX/Java process attributable to this run persisted.

## Environment, scope, and classification

The verified host facts used by both public runs were CubeMX
6.18.1-RC2, CubeCLT 1.22.0, GCC 14.3.1, CMake 4.3.1, Ninja 1.13.2, and the
installed repository package
`C:/Users/ZhangYang/STM32Cube/Repository/STM32Cube_FW_F4_V1.28.3`.
No package or software installation was performed by this implementation.
The earlier missing-repository observation is historical environment evidence
and is resolved for this native run; it is not relabeled as a native PASS.

Classification is PRODUCT for the double-root activation boundary, strict
native integration, ownership/portability behavior, and product tests. The
earlier one-test process timeout was TEST-classified harness cleanup and was
already corrected before this CodeHead. ENVIRONMENT records only the earlier
missing-repository observation and the installed facts above. No REPORT
format/diff-check failure remains.

The branch is local and unpushed. Sol must independently review the complete
accepted-base-to-CodeHead diff and issue the acceptance verdict; VS07-C
remains frozen pending that review.
