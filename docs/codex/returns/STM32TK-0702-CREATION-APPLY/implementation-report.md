# STM32TK-0702 VS07-B implementation report

## Status and ownership

- Status: `IMPLEMENTATION_COMPLETE_PENDING_SOL_REVIEW`; the implementer does not self-accept.
- Module/phase: STM32 Toolkit 0.7 / VS07-B authorized creation and build.
- Accepted base: `bff9cc120923b0e9f2ba29a1b3511f1bcc26ab6e`.
- CodeHead before this report/ledger commit: `e515eac91e99b777819c1660221d5c29ad1ef9a5`.
- Implementer: `/root/vs07b_implementer`, GPT-5.6-luna, reasoning max.
- Reviewer/acceptor: GPT-5.6-sol primary agent.
- Branch/worktree: `codex/STM32TK-0702-CREATION-APPLY` / `C:/tmp/stm32tk-0702-creation-apply`.
- Product commit for this revision: `e515eac91e99b777819c1660221d5c29ad1ef9a5`.
- No push, PR, merge, tag, release, remote operation, hardware action, package installation, or VS07-C work was performed.

The revision binds authorization records to their complete canonical prepared
payload, requires exact native CubeMX firmware family and version, and restores
generic linker-role selection to the pre-runtime-recovery contract. The README
status wording is included in this final documentation change. The prior
activation integration remains the two-root boundary: generation and activation
staging are siblings, native validation and host-path scanning happen before
relocation, generation cleanup happens before configure, and configure/build
receive only activation staging.

## TDD RED/GREEN evidence for this revision

Each new product behavior had a witnessed RED before its product edit.

### Authorization record integrity

The RED command was:

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m pytest tools/stm32-toolkit/tests/test_creation_authorization.py -k record_integrity -q --basetemp C:\tmp\p0702-r4-f1-red
```

Result: `8 failed`, as expected. Rewriting any of request, project root,
plan/action/environment digest, issued/expiry time, or nonce was accepted by
the pre-fix `peek` path.

The GREEN command was:

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m pytest tools/stm32-toolkit/tests/test_creation_authorization.py -k 'record_integrity or replay_is_rejected or prepare_writes_bounded_record' -q --basetemp C:\tmp\p0702-r4-f1-green
```

Result: `10 passed`. The complete authorization module then returned `16
passed` in `C:\tmp\p0702-r4-f1-affected`. `peek` and `consume` now share the
same canonical prepared-state digest check; valid replay still reaches the
existing `CREATION_AUTHORIZATION_CONSUMED` state and expiry behavior remains
unchanged.

### Exact native firmware package identity

The RED command was:

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m pytest tools/stm32-toolkit/tests/test_cubemx_project.py -k missing_firmware_version -q --basetemp C:\tmp\p0702-r4-f2-red
```

Result: `1 failed`, because an IOC that named `STM32Cube FW_F4` without a
version was accepted before the fix. The GREEN command was:

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m pytest tools/stm32-toolkit/tests/test_cubemx_project.py -k 'requires_exact_firmware_family_and_version or missing_firmware_version or accepts_sanitized_r8_f429_global_template' -q --basetemp C:\tmp\p0702-r4-f2-green
```

Result: `3 passed`. Native parsing now rejects a missing or different family
or version and accepts the verified F4 `V1.28.3` output. The four existing
6.18 parser fixtures were made explicit with their test environment package
versions so the strict contract is literal rather than inferred.

### Generic memory-role compatibility

The RED command was:

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m pytest tools/stm32-toolkit/tests/test_generation.py -k generic_memory_roles -q --basetemp C:\tmp\p0702-r4-f3-red
```

Result: `1 failed`: a generic model ordered `RAM`, `CCMRAM`, `FLASH` but the
pre-fix code selected `FLASH`, `RAM`. The GREEN command was:

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m pytest tools/stm32-toolkit/tests/test_generation.py -k 'generic_memory_order or generic_memory_roles or non_native_configuration_restores' -q --basetemp C:\tmp\p0702-r4-f3-green2
```

Result: `3 passed`. Generic models again use the first executable and first
writable region by declared order, including `RAM`, `RAM` for the regression
topology. Native projects continue using their validated CubeMX linker and do
not call the generic role selection.

The combined affected command was:

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m pytest tools/stm32-toolkit/tests/test_creation_authorization.py tools/stm32-toolkit/tests/test_cubemx_project.py tools/stm32-toolkit/tests/test_generation.py -q --basetemp C:\tmp\p0702-r4-affected-f123-greenxml --junitxml=C:\tmp\p0702-r4-affected-f123-green.xml
```

Result: `321 tests, 0 failures, 0 errors, 0 skipped`, exit 0.

## Exact aggregate verification

After product/tests commit `e515eac9`, the exact approved 16-file command ran
with fresh basetemp `C:\tmp\p0702-r5-slice` and JUnit
`C:\tmp\p0702-r5-slice.xml`:

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m pytest tools/stm32-toolkit/tests/test_creation_authorization.py tools/stm32-toolkit/tests/test_creation_environment.py tools/stm32-toolkit/tests/test_cubemx_adapter.py tools/stm32-toolkit/tests/test_cubemx_project.py tools/stm32-toolkit/tests/test_creation_apply.py tools/stm32-toolkit/tests/test_creation_plan.py tools/stm32-toolkit/tests/test_creation_workflows.py tools/stm32-toolkit/tests/test_creation_cli.py tools/stm32-toolkit/tests/test_creation_mcp.py tools/stm32-toolkit/tests/test_process.py tools/stm32-toolkit/tests/test_generation.py tools/stm32-toolkit/tests/test_workflows.py tools/stm32-toolkit/tests/test_build_runner.py tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_mcp_server.py tools/stm32-toolkit/tests/test_mcp_roots.py -q --basetemp C:\tmp\p0702-r5-slice --junitxml=C:\tmp\p0702-r5-slice.xml
```

JUnit result: `698 tests, 0 failures, 0 errors, 0 skipped`, exit 0. The only
reported warning was the existing `runpy` warning from `test_cli.py`.

Compileall:

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m compileall -q tools/stm32-toolkit/src tools/stm32-toolkit/tests
```

Result: exit 0.

Accepted-base diff check:

```powershell
git diff --check bff9cc120923b0e9f2ba29a1b3511f1bcc26ab6e..e515eac91e99b777819c1660221d5c29ad1ef9a5
```

Result: exit 0. The product/tests commit was clean before the final README,
report, and ledger documentation edits. The branch has no upstream configured.

## Fresh public native MCU scenario

This is software/native evidence only; no hardware was used. The run began
from product/tests CodeHead `e515eac91e99b777819c1660221d5c29ad1ef9a5`; only
the pending README documentation edit was outside that commit.

- Workspace: `C:\tmp\p0702-r5-native-mcu`.
- Data root: `C:\tmp\p0702-r5-native-mcu-data`.
- Local Git setup commit: `d47aa21fb422ba623b73eb48b573ff681680b3f4`; no remote.
- Request: `CreationPlanWorkflowRequest(root, data, 'native-r5-mcu', 'mcu', 'STM32F429ZITx', 'generated', 'hal', 'c')`.
- Public plan: `OK`; plan ID `86cb0f1a1e0f6c162a909990bdc612755ec0ea3bedc5bdfc163f4fe03a7aea7f`.
- Action digest: `e59ec7ed21302c8f0e700a574bbc59227e346b2a882981fa790d798fc1515664`.
- Public prepare: `OK`; authorization digest `5c2b9755f19f3b687048d0596060ab9b1f0ce0b48c9eeb2507a65f875398ce21`.
- Execution-environment digest: `74dd331eadfa1ad4c6f622d477176ec7aae72d07cd0ab18f1549752f075cab62`.
- Public apply: `OK`; attempt `16e604974bdc447447daacf0`.
- Ownership manifest SHA-256: `570a0526a61bc12348fb2d3739aeaf64067f8f4ec65edb9b1b44dc95d2e30e3c`.
- Debug build ID: `6acc5f11d9c1e437df84e4ada37a98b1b8381bda27324c36483de0e70ae3da55`; ELF size 1,030,080 bytes.
- Release build ID: `9cf3c7c7bbfad3338026ab61ced0201a219c51e112ddc59d423e43a579123ebd`; ELF size 16,768 bytes.
- Both Debug and Release configuration/build results were `OK`; each used 1,584 RAM bytes. The native memory facts were RAM 196,608 bytes, CCMRAM 65,536 bytes, and FLASH 2,097,152 bytes.
- Activated output contained 1,562 files. Non-build public bytes had zero workspace/staging host-path hits.
- No `.stm32tk-*`, `.stm32-toolkit-cubemx-control-*`, generation, or activation residue remained.
- Relevant process snapshot before/after contained only pre-existing `javaw.exe` PID `32708` with unreadable command line; it was not terminated and no new persistent CubeMX/Java process remained.

## Fresh public native captured-IOC scenario

- Workspace: `C:\tmp\p0702-r5-native-ioc`.
- Data root: `C:\tmp\p0702-r5-native-ioc-data`.
- Captured source: `C:\tmp\p0702-native-capture-r8\generated-staging\STM32F429ZITx\STM32F429ZITx.ioc`.
- Portable copied path: `input/STM32F429ZITx.ioc`.
- Source and copied SHA-256: `636e9c2de3921db06e855c8180d6d701efda66c2db1b9e6e534dc135cb34d2b0`.
- Local Git setup commit: `4becd254df50ba04e263a76aa7f668238abd9533`; no remote.
- Request: `CreationPlanWorkflowRequest(root, data, 'native-r5-ioc', 'ioc', 'input/STM32F429ZITx.ioc', 'generated', 'hal', 'c')`.
- Public plan: `OK`; plan ID `2c5c81cf1de7b4680a4c136900b3f50a886175fd5caaf0d55a016c515ae9c02d`.
- Action digest: `27419915b77fcd4a7e4d8bed31083932973932113c613cd7f062f22e86c185a1`.
- Public prepare: `OK`; authorization digest `7ca74d6874642d554b3dfe3ffad49e426717f6852273622e0899b8c1fab7cfad`.
- Execution-environment digest: `24e69448b12f71273ce9bb03c8c85e245210515c58c60307bf1f80ad73cdf195`.
- Public apply: `OK`; attempt `0bef7326087e98a477590f99`.
- Ownership manifest SHA-256: `5349c90731ad944560b42a59ebd154a57b029ab90832bf0991d84f45a477299a`.
- Debug build ID: `ee919b5a39730e988c465f83c52c550361b3508cda946f1f35f529e18e96fe3d`; ELF size 1,030,080 bytes.
- Release build ID: `b422dcb02c2251d76720819eb3cb0ab5d70237501a0709c07c51a176a0fe0a3a`; ELF size 16,768 bytes.
- Both Debug and Release configuration/build results were `OK`; each used 1,584 RAM bytes. Native memory facts matched the MCU scenario.
- Activated output contained 1,562 files. Non-build public bytes had zero workspace/staging host-path hits and no control, generation, or activation residue.
- Relevant process snapshot before/after contained only pre-existing Java PID `32708`; no new persistent CubeMX/Java process remained.

## Environment, classification, and handoff

Verified host facts used by both public runs were CubeMX `6.18.1-RC2`,
CubeCLT `1.22.0`, GCC `14.3.1`, CMake `4.3.1`, Ninja `1.13.2`, and the
installed repository package
`C:/Users/ZhangYang/STM32Cube/Repository/STM32Cube_FW_F4_V1.28.3`. No
package/software installation was performed and no hardware was used. The
earlier `CUBEMX_REPOSITORY_MISSING` observation remains historical
environment evidence; it was not relabeled as a native PASS.

The authorization, parser, generic compatibility, activation, ownership, and
native integration changes are classified PRODUCT. The earlier one-test
process timeout was classified TEST (subprocess cleanup) and was corrected
before this CodeHead. Installed package facts are ENVIRONMENT evidence. No
REPORT format or diff-check failure remains.

The branch is local and unpushed, with no upstream configured. Sol must
independently review the complete accepted-base-to-CodeHead diff and issue the
acceptance verdict; this report makes no acceptance claim. VS07-C remains
frozen pending that review.
