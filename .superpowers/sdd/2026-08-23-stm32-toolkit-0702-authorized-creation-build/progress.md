# SDD ledger — VS07-B authorized creation and build

- Module/phase: STM32 Toolkit 0.7 / VS07-B.
- Accepted base: `bff9cc120923b0e9f2ba29a1b3511f1bcc26ab6e`.
- Specification/plan owner: GPT-5.6-sol primary agent.
- Implementer: `/root/vs07b_implementer`, GPT-5.6-luna, reasoning max.
- Reviewer/acceptor: GPT-5.6-sol primary agent.
- Branch/worktree: `codex/STM32TK-0702-CREATION-APPLY` / `C:/tmp/stm32tk-0702-creation-apply`.
- CodeHead before the separate report/ledger commit: `7bfcba8472ec00c25f37b856c0ff066ab56794f3`.
- Product activation rewrite commit: `7bfcba8472ec00c25f37b856c0ff066ab56794f3`.
- Prior bounded cleanup correction: `cf908a6720304391abe07588ee462ec26061e130`.
- No push, PR, merge, tag, release, remote operation, package installation,
  hardware action, or VS07-C work was performed.
- Sol must independently review the complete accepted-base-to-CodeHead diff;
  the implementer does not self-accept.

## History and recovery

- The accepted VS07-A baseline was `bff9cc12`; the unrelated
  `D:/workspace/stm32-toolkit` worktree was preserved and untouched.
- Sol's first review returned F1-F6 revision findings. The subsequent
  recovery established the verified CubeMX 6.18 protocol, isolated updater and
  control lifecycle, strict global/context native parser, native linker
  ownership, Git precondition, and durable authorization/activation claims.
- Two native linker/runtime reconstruction rounds did not converge and were
  replaced by the `generation.nativeLinkerScript` interface design. The real
  native link then configured and built both presets before exposing the
  generation-container cleanup race.
- The first cleanup correction proved bounded empty-container retry, but two
  fresh native attempts (`ea3bb6fee91111b8ee0dbb66` and
  `a01eb84a1e22775f000be767`) reproduced post-build parent cleanup failure.
  Sol's approved activation redesign separated generation and activation
  roots; this ledger records the resulting implementation below.
- VS07-C remains frozen pending Sol's independent verdict.

## TDD and product evidence

Historical recovery checkpoints retained in this attempt:

- Task 1R adapter RED: 10 failed, 9 passed; GREEN: 19 passed.
- Task 2R parser RED: 6 failed, 10 passed; GREEN: 15 passed.
- Native linker ownership focused RED: 5 failed; GREEN: 5 passed.
- Bounded cleanup correction RED: 4 failed, 1 passed; GREEN: 5 passed.
- The first affected activation-process run had 89 tests with one timeout;
  this was classified TEST (subprocess cleanup), corrected in the separate
  cleanup correction commit, and the affected set then passed 89/89.

The final activation integration RED was:

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m pytest tools/stm32-toolkit/tests/test_creation_apply.py -k 'relocat or activation_staging_collision or relocation_failure or configure_failure_after_relocation' -q --basetemp C:\tmp\p0702-activation-red2
```

It returned `4 failed, 0 passed`. The failures proved the old single-root
ordering and absence of collision/relocation seams. The matching GREEN run
returned `4 passed` in `C:\tmp\p0702-activation-green2`.

The final focused apply suite returned `27 passed` in
`C:\tmp\p0702-activation-apply-green2`. The directly affected apply/workflow
suite returned `41 passed`, exit 0, with JUnit
`C:\tmp\p0702-activation-affected2.xml`.

The final product owns generation and activation roots independently, rejects
collisions without deleting them, validates/scans before relocation, cleans
the generation root before configure, sends only activation staging to
configure/build/final activation, and cleans both roots on relocation,
configure, build, activation, and typed validation failures. Existing
absent/empty destination transactions and bounded retry tests remain green.

## Final verification

The exact approved 16-file slice was run with fresh basetemp
`C:\tmp\p0702-rr4-slice` and JUnit `C:\tmp\p0702-rr4-slice.xml`:

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m pytest tools/stm32-toolkit/tests/test_creation_authorization.py tools/stm32-toolkit/tests/test_creation_environment.py tools/stm32-toolkit/tests/test_cubemx_adapter.py tools/stm32-toolkit/tests/test_cubemx_project.py tools/stm32-toolkit/tests/test_creation_apply.py tools/stm32-toolkit/tests/test_creation_plan.py tools/stm32-toolkit/tests/test_creation_workflows.py tools/stm32-toolkit/tests/test_creation_cli.py tools/stm32-toolkit/tests/test_creation_mcp.py tools/stm32-toolkit/tests/test_process.py tools/stm32-toolkit/tests/test_generation.py tools/stm32-toolkit/tests/test_workflows.py tools/stm32-toolkit/tests/test_build_runner.py tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_mcp_server.py tools/stm32-toolkit/tests/test_mcp_roots.py -q --basetemp C:\tmp\p0702-rr4-slice --junitxml=C:\tmp\p0702-rr4-slice.xml
```

JUnit result: `688 tests, 0 failures, 0 errors, 0 skipped`, exit 0. The only
warning was the existing `runpy` warning from `test_cli.py`.

Compileall:

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m compileall -q tools/stm32-toolkit/src tools/stm32-toolkit/tests
```

Result: exit 0.

Accepted-base diff check:

```powershell
git diff --check bff9cc120923b0e9f2ba29a1b3511f1bcc26ab6e..7bfcba8472ec00c25f37b856c0ff066ab56794f3
```

Result: exit 0. The product worktree was clean before this docs edit, and
the branch has no upstream configured.

## Real native MCU evidence

The run used CubeMX 6.18.1-RC2, CubeCLT 1.22.0, GCC 14.3.1, CMake 4.3.1,
Ninja 1.13.2, and installed package
`C:/Users/ZhangYang/STM32Cube/Repository/STM32Cube_FW_F4_V1.28.3`. No install
was performed by the implementer and no hardware was used.

Fresh workspace/data roots:

- Workspace: `C:\tmp\p0702-native-rewrite-mcu3`.
- Data root: `C:\tmp\p0702-native-rewrite-mcu3-data`.
- Local Git setup commit: `fc3af925caf1dcb8f126fac88dc0c80a794620a3`; no remote.
- Request: `CreationPlanWorkflowRequest(root, data,
  'native-rewrite-mcu3', 'mcu', 'STM32F429ZITx', 'generated', 'hal', 'c')`.
- Plan ID: `5e698e2c4afcaf31663ec325956dcdc1455a274f45882d0c76cfaeaf5dcfe05a`.
- Action digest: `6be30edd55f632a5a7da2c1bb7f7a278e4f2d3963e332a5482b3dd1f4d674415`.
- Authorization digest: `ecf1d02bc419cae42867fe1d4ae30e885fff97ffe0d9739661bd34545566539b`.
- Environment digest: `74dd331eadfa1ad4c6f622d477176ec7aae72d07cd0ab18f1549752f075cab62`.
- Public plan and prepare: `OK`.
- Public apply: `OK`; attempt `f3bb99fe4ed02e63bdcf6f86`.
- Ownership manifest SHA-256: `1ac4e5e62935df9f0e458ed9f17e7e37154cdad1bf539385e6df98009eb50e94`.
- Debug build ID: `3da3a38d3bff4f0954eb0185b2c2a46f255687e36572ef3a0fded11b59c8e02f`.
- Release build ID: `a7a1846dec96f0302e192c1dacc111a26bc23cfb1771c5f1225be481b6ad708b`.
- Debug/Release ELF sizes: 1,030,400 / 16,768 bytes.
- Memory: RAM 196,608 bytes, CCMRAM 65,536 bytes, FLASH 2,097,152 bytes.
- Activated output: 1,562 files; non-build host-path hits: 0.
- No control, generation, or activation root remained after apply.
- Process delta: only pre-existing Java PID 32708 before and after; it was not
  terminated and no new persistent CubeMX/Java process remained.

## Real native captured-IOC evidence

Fresh workspace/data roots:

- Workspace: `C:\tmp\p0702-native-rewrite-ioc3`.
- Data root: `C:\tmp\p0702-native-rewrite-ioc3-data`.
- Captured source:
  `C:\tmp\p0702-native-capture-r8\generated-staging\STM32F429ZITx\STM32F429ZITx.ioc`.
- Portable copied path: `input/STM32F429ZITx.ioc`.
- Source and copied SHA-256:
  `636e9c2de3921db06e855c8180d6d701efda66c2db1b9e6e534dc135cb34d2b0`.
- Local Git setup commit: `0d5fd998592c7c4bf49409b6655c405ea59a870c`; no remote.
- Request: `CreationPlanWorkflowRequest(root, data,
  'native-rewrite-ioc3', 'ioc', 'input/STM32F429ZITx.ioc', 'generated',
  'hal', 'c')`.
- Plan ID: `713e99003b4680a37d5301f4a3daa304a98e40b4997fce030f876b1ea0cf748a`.
- Action digest: `82acd98b65f365a5b80b38a8083308f040cd74f76177123ffaf1f79b545f83a4`.
- Authorization digest: `f4797a276ceb574dcde792d5920674fcfde54b44ebb79ee1c45c680090613e2a`.
- Environment digest: `24e69448b12f71273ce9bb03c8c85e245210515c58c60307bf1f80ad73cdf195`.
- Public plan and prepare: `OK`.
- Public apply: `OK`; attempt `d7560a5648cc402ad59aa587`.
- Ownership manifest SHA-256: `45b0fa563078133012d54842297274b9d0c27df6d9db04a7a0176aa328d40983`.
- Debug build ID: `1c3e9502eeb7a046d32a5a7020f93cfa1013050f6b2930ce9fa084dcd0d98549`.
- Release build ID: `267af93c4b619bdbc0840618201d1f3edd8864f1ac3a087bd2a321dcd7f1b63f`.
- Debug/Release ELF sizes: 1,030,400 / 16,768 bytes.
- Memory: RAM 196,608 bytes, CCMRAM 65,536 bytes, FLASH 2,097,152 bytes.
- Activated output: 1,562 files; non-build host-path hits: 0.
- No control, generation, or activation root remained after apply.
- Process delta: only pre-existing Java PID 32708 before and after; no new
  persistent CubeMX/Java process remained.

## Classification and handoff

- PRODUCT: double-root activation implementation, collision/cleanup/ordering
  contracts, native integration, and all product regression evidence.
- TEST: the earlier one-test subprocess timeout caused by harness cleanup;
  corrected before the final CodeHead.
- ENVIRONMENT: the prior missing-repository observation is historical; the
  installed package facts above enabled these two native software runs. No
  native hardware or physical PASS is claimed.
- REPORT: this report and ledger use normal Markdown backticks; diff-check
  passed before docs editing.

The branch remains local and unpushed. Sol independently reviews the complete
accepted-base-to-CodeHead diff and repeats the applicable evidence; no
acceptance claim is made here.
