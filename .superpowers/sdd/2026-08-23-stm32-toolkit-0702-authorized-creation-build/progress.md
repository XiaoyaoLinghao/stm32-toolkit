# SDD ledger — VS07-B authorized creation and build

- Module/phase: STM32 Toolkit 0.7 / VS07-B.
- Accepted base: `bff9cc120923b0e9f2ba29a1b3511f1bcc26ab6e`.
- Specification/plan owner: GPT-5.6-sol primary agent.
- Implementer: `/root/vs07b_implementer`, GPT-5.6-luna, reasoning max.
- Reviewer/acceptor: GPT-5.6-sol primary agent.
- Branch/worktree: `codex/STM32TK-0702-CREATION-APPLY` / `C:/tmp/stm32tk-0702-creation-apply`.
- CodeHead before the separate report/ledger commit: `e515eac91e99b777819c1660221d5c29ad1ef9a5`.
- Product revision commit: `e515eac91e99b777819c1660221d5c29ad1ef9a5`.
- No push, PR, merge, tag, release, remote operation, package installation, hardware action, or VS07-C work was performed.
- Sol independently reviewed the complete accepted-base-to-returned-head diff; the implementer did not self-accept.

## Scope and recovery history

The implementation retains the approved VS07-B lifecycle: public plan is
read-only; prepare revalidates the plan, Git head, environment, and destination
facts before writing one capability; apply consumes it once, generates in a
bounded CubeMX root, validates native bytes and ownership before relocation,
cleans that root before configure, builds Debug and Release in a separate
activation staging sibling, and activates only after both builds. Collision,
redirect, unsafe-type, drift, rollback, and cleanup paths remain fail closed.

Earlier recovery checkpoints were retained as evidence: adapter RED 10 failed
/ 9 passed then 19 passed GREEN; parser RED 6 failed / 10 passed then 15 passed
GREEN; native linker ownership focused RED 5 failed then 5 passed; bounded
cleanup correction RED 4 failed / 1 passed then 5 passed; and the activation
integration RED 4 failed / 0 passed then 4 passed. The earlier affected
activation process timeout was TEST-classified subprocess cleanup, corrected
before this revision.

## Current revision TDD evidence

Authorization record-integrity RED:

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m pytest tools/stm32-toolkit/tests/test_creation_authorization.py -k record_integrity -q --basetemp C:\tmp\p0702-r4-f1-red
```

Result: `8 failed`. GREEN returned `10 passed` with the focused integrity,
replay, and bounded-record selection. The complete authorization module
returned `16 passed`.

Strict native family/version RED:

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m pytest tools/stm32-toolkit/tests/test_cubemx_project.py -k missing_firmware_version -q --basetemp C:\tmp\p0702-r4-f2-red
```

Result: `1 failed`. GREEN returned `3 passed` for exact family/version,
missing-version rejection, and the sanitized F4 fixture.

Generic memory-role RED:

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m pytest tools/stm32-toolkit/tests/test_generation.py -k generic_memory_roles -q --basetemp C:\tmp\p0702-r4-f3-red
```

Result: `1 failed`. GREEN returned `3 passed` for generic order/role
compatibility and non-native configuration. The combined affected command
returned `321 passed, 0 failures, 0 errors, 0 skipped`, JUnit
`C:\tmp\p0702-r4-affected-f123-green.xml`.

The product change centralizes canonical prepared-state authorization hashing,
requires exact native IOC package family and version, and restores generic
first-executable/first-writable region order. Native mode continues to use the
validated CubeMX linker and does not use generic linker roles.

## Aggregate verification

The exact approved 16-file command ran after product commit `e515eac9`:

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'; py -3.12 -m pytest tools/stm32-toolkit/tests/test_creation_authorization.py tools/stm32-toolkit/tests/test_creation_environment.py tools/stm32-toolkit/tests/test_cubemx_adapter.py tools/stm32-toolkit/tests/test_cubemx_project.py tools/stm32-toolkit/tests/test_creation_apply.py tools/stm32-toolkit/tests/test_creation_plan.py tools/stm32-toolkit/tests/test_creation_workflows.py tools/stm32-toolkit/tests/test_creation_cli.py tools/stm32-toolkit/tests/test_creation_mcp.py tools/stm32-toolkit/tests/test_process.py tools/stm32-toolkit/tests/test_generation.py tools/stm32-toolkit/tests/test_workflows.py tools/stm32-toolkit/tests/test_build_runner.py tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_mcp_server.py tools/stm32-toolkit/tests/test_mcp_roots.py -q --basetemp C:\tmp\p0702-r5-slice --junitxml=C:\tmp\p0702-r5-slice.xml
```

JUnit: `698 tests, 0 failures, 0 errors, 0 skipped`, exit 0. The only warning
was the existing `runpy` warning in `test_cli.py`. Compileall over source and
tests exited 0. Accepted-base `git diff --check
bff9cc120923b0e9f2ba29a1b3511f1bcc26ab6e..e515eac91e99b777819c1660221d5c29ad1ef9a5`
exited 0.

## Fresh native MCU evidence

Environment: CubeMX `6.18.1-RC2`, CubeCLT `1.22.0`, GCC `14.3.1`, CMake
`4.3.1`, Ninja `1.13.2`, and installed
`C:/Users/ZhangYang/STM32Cube/Repository/STM32Cube_FW_F4_V1.28.3`. No install
or hardware action was performed. The public API path was
`plan_creation_workflow`, `prepare_creation_workflow`, then
`apply_creation_workflow` with a discovered support profile.

- Workspace/data: `C:\tmp\p0702-r5-native-mcu` /
  `C:\tmp\p0702-r5-native-mcu-data`.
- Test local Git setup commit: `d47aa21fb422ba623b73eb48b573ff681680b3f4`; no remote.
- Request source: MCU `STM32F429ZITx`; destination `generated`.
- Plan/action: `86cb0f1a1e0f6c162a909990bdc612755ec0ea3bedc5bdfc163f4fe03a7aea7f` /
  `e59ec7ed21302c8f0e700a574bbc59227e346b2a882981fa790d798fc1515664`.
- Prepare/auth/environment: `OK` /
  `5c2b9755f19f3b687048d0596060ab9b1f0ce0b48c9eeb2507a65f875398ce21` /
  `74dd331eadfa1ad4c6f622d477176ec7aae72d07cd0ab18f1549752f075cab62`.
- Apply: `OK`; attempt `16e604974bdc447447daacf0`; ownership manifest
  `570a0526a61bc12348fb2d3739aeaf64067f8f4ec65edb9b1b44dc95d2e30e3c`.
- Debug/Release build IDs:
  `6acc5f11d9c1e437df84e4ada37a98b1b8381bda27324c36483de0e70ae3da55` /
  `9cf3c7c7bbfad3338026ab61ced0201a219c51e112ddc59d423e43a579123ebd`.
- Both builds and activation were `OK`; Debug/Release ELF sizes were
  1,030,080 / 16,768 bytes; each used 1,584 RAM bytes. Memory facts were RAM
  196,608, CCMRAM 65,536, and FLASH 2,097,152 bytes.
- Output: 1,562 files, zero non-build workspace/staging path hits, zero
  control/generation/activation residue.
- PID delta: only pre-existing `javaw.exe` PID `32708` before and after; it
  was not terminated and no new persistent CubeMX/Java PID remained.

## Fresh native captured-IOC evidence

- Workspace/data: `C:\tmp\p0702-r5-native-ioc` /
  `C:\tmp\p0702-r5-native-ioc-data`.
- Captured source:
  `C:\tmp\p0702-native-capture-r8\generated-staging\STM32F429ZITx\STM32F429ZITx.ioc`;
  copied once to `input/STM32F429ZITx.ioc`.
- Source/copy SHA-256:
  `636e9c2de3921db06e855c8180d6d701efda66c2db1b9e6e534dc135cb34d2b0`.
- Test local Git setup commit: `4becd254df50ba04e263a76aa7f668238abd9533`; no remote.
- Request source: IOC `input/STM32F429ZITx.ioc`; destination `generated`.
- Plan/action: `2c5c81cf1de7b4680a4c136900b3f50a886175fd5caaf0d55a016c515ae9c02d` /
  `27419915b77fcd4a7e4d8bed31083932973932113c613cd7f062f22e86c185a1`.
- Prepare/auth/environment: `OK` /
  `7ca74d6874642d554b3dfe3ffad49e426717f6852273622e0899b8c1fab7cfad` /
  `24e69448b12f71273ce9bb03c8c85e245210515c58c60307bf1f80ad73cdf195`.
- Apply: `OK`; attempt `0bef7326087e98a477590f99`; ownership manifest
  `5349c90731ad944560b42a59ebd154a57b029ab90832bf0991d84f45a477299a`.
- Debug/Release build IDs:
  `ee919b5a39730e988c465f83c52c550361b3508cda946f1f35f529e18e96fe3d` /
  `b422dcb02c2251d76720819eb3cb0ab5d70237501a0709c07c51a176a0fe0a3a`.
- Both builds and activation were `OK`; ELF sizes were 1,030,080 / 16,768
  bytes; each used 1,584 RAM bytes and memory facts matched MCU.
- Output: 1,562 files, zero non-build host-path hits, and no control,
  generation, or activation residue.
- PID delta: only pre-existing Java PID `32708` remained; no new persistent
  CubeMX/Java PID remained.

## Classification and handoff

- PRODUCT: authorization integrity, strict native package identity, generic
  compatibility, activation lifecycle, ownership/portability, and native
  software integration.
- TEST: the earlier one-test subprocess timeout caused by harness cleanup;
  corrected before the returned product CodeHead.
- ENVIRONMENT: installed CubeMX/CubeCLT/package facts above; the earlier
  `CUBEMX_REPOSITORY_MISSING` observation remains historical and is not a
  native PASS claim.
- REPORT: normal Markdown and accepted-base diff check passed.

The branch is local and unpushed with no upstream configured. The implementation
return made no self-acceptance claim; the independent reviewer reconciliation
below records the final VS07-B verdict.

## Sol independent acceptance reconciliation

- Reviewed returned head: `51b739f9fe48a9f312b3a0950a7416e3333024af` in clean detached worktree
  `C:/tmp/stm32tk-0702-final2-review-51b739f`.
- Complete review range: accepted base
  `bff9cc120923b0e9f2ba29a1b3511f1bcc26ab6e` through the reviewed head;
  `git diff --check` passed. The correction range from `5070be3e` was also
  inspected independently.
- Independent probes rejected retained-digest authorization record tampering
  from both `peek` and `consume`, rejected an IOC firmware fact missing its
  exact version, and restored generic non-native memory-role selection to
  first executable/first writable (`RAM`, `RAM`).
- The exact approved 16-file slice returned `698 tests, 0 failures, 0 errors,
  0 skipped`; JUnit is `C:/tmp/p0702-sol-final2-slice.xml`. Source/test
  `compileall` passed.
- Fresh public MCU workspace/data:
  `C:/tmp/p0702-sol-final2-mcu` /
  `C:/tmp/p0702-sol-final2-mcu-data`; local Git head
  `10a9922ea953b29ac329102de94bf79d10720b73`, no remote. Plan, prepare,
  apply, configure, Debug, Release, and activation returned `OK`. The attempt
  was `01bf122bd9422ceee63e1c66`; ownership manifest SHA-256 was
  `052e21276e4d3bfd32f32f1f9eae6336dad00b4fb2691db3ef2e774ffbcbb6c9`;
  Debug/Release build IDs were
  `b9f775b36f40b2d1100bd1d61e1e1c6dd60bb94216c6bac2df9b35ad377f3fb5` /
  `902973ec3996247164643757a0f9f8c6ab9ee7dd94f2c5cf95c185100a0750b8`.
- Fresh public captured-IOC workspace/data:
  `C:/tmp/p0702-sol-final2-ioc` /
  `C:/tmp/p0702-sol-final2-ioc-data`; local Git head
  `970c100ca77cf2738f2bbde5c39a90e250e92b86`, no remote. Captured source
  and copy both had SHA-256
  `636e9c2de3921db06e855c8180d6d701efda66c2db1b9e6e534dc135cb34d2b0`.
  Plan, prepare, apply, configure, Debug, Release, and activation returned
  `OK`. The attempt was `253ecedbb891f5e94c8bd421`; ownership manifest
  SHA-256 was
  `0fc0d43967392446c1618e0f7c16fea05d20c27d27c1e8bf6408ac482b1aad93`;
  Debug/Release build IDs were
  `f88105be6feb252f8498e8466df0d4144576e3dfeb28d48e394f61815124b492` /
  `6d6ba74167567a39072973ab91b1670746dce6f07ccd60a648167858d282cec7`.
- Each public scenario activated 1,562 files, had zero non-build host-path
  hits, left no generation/activation/control residue, and added no persistent
  CubeMX/Java PID. Pre-existing `javaw.exe` PID 32708 was unchanged and was
  not terminated. No hardware evidence is claimed.
- Verdict: `ACCEPTED`. No unresolved PRODUCT defect remains in VS07-B.
  VS07-C may now be reconstructed as the next separately bounded slice.
- Remote status: branch remains local, unpushed, and without an upstream. No
  push, PR, merge, tag, release, remote mutation, installation, or hardware
  operation was performed.
