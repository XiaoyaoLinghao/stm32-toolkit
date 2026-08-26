# STM32TK-1001 Task 6 standard-math H1 Sol review

## Verdict

`H1 ACCEPTED` for the local pre-hardware gate.

This verdict accepts the reproducible migrated GCC firmware and its software
evidence. It is not physical acceptance and does not report a probe, flash,
reset, target read, or board observation. The next permitted phase is the
separately controlled real-hardware test; this review performs none of it.

## Frozen lineage and ownership

- Toolkit accepted product base:
  `29d063a2b922dd636e0865ae3c0c6a825592dfb3`.
- Toolkit accepted product code head:
  `0cdd142f80421c6aea59e81e963936779b05f00f`, tree
  `c33729b55bcfcb40ff782e81548f5e2cba8a8e2f`.
- Toolkit report-chain head before this review report:
  `fb1c54111cb6b0db31486e6c42ec7f031b5a6ef6`, tree
  `aea66d72e7bbf1b5c039e63e4d93c09e829a9671`.
- Project restart base:
  `718c37ed5d381f01680e64abe8c3810d62723b2a`, tree
  `2990239f436c259ae3652cc0df48b9411b14b381`.
- Corrected public conversion commit:
  `43af128b9629ce203c9f3c49090a41aefe6f6d63`.
- Final project configuration head:
  `9aae7ffd860405fadb7ac5f6278bcbb93add8d16`, tree
  `536a5aaedfefb35e7755cef22e9410b4bc6f27ea`.
- Unique project writer and implementation-evidence owner: GPT-5.6-luna/max.
- Independent complete-diff/evidence reviewer and acceptor: GPT-5.6-sol
  primary.
- Hardware, network, push, PR, merge, tag, release, and remote-branch actions:
  none.

## Complete-diff review

The complete Toolkit product diff
`29d063a2b922dd636e0865ae3c0c6a825592dfb3..0cdd142f80421c6aea59e81e963936779b05f00f`
was reviewed from a clean detached worktree at the exact code head. It contains
the frozen specification, plan, implementation report, two schema copies, two
CMake template copies, the model/configure/model-hash/planner changes, and the
three affected test files. `git diff --check` passed. The earlier independent
product review found and caused correction of the Schema-2 selector leak; the
corrected complete-diff review then found no remaining issue and the exact
focused correction set passed 15/15. The complete 97-test migration result
remained applicable because the correction did not change planner bytes.

All commits after product code head through
`fb1c54111cb6b0db31486e6c42ec7f031b5a6ef6` change only the two standard-math
reports and this campaign's implementation report. No later product byte is
present in the runtime or project result.

The complete project diff
`718c37ed5d381f01680e64abe8c3810d62723b2a..9aae7ffd860405fadb7ac5f6278bcbb93add8d16`
was reviewed from a clean detached worktree at the exact final head.
`git diff --check` passed. It contains exactly 13 additions: the three public
conversion products plus ten managed configuration files. There is no C, H,
S, ASM, original Keil, or historical-output path change. The conversion report
has zero blockers and omitted sources; its manifest and patch digests reproduce
the committed bytes.

The committed manifest is Schema 3 for `STM32F429ZGTx`, Cortex-M4,
`fpv4-sp-d16`, hard float, and `build.linkStandardMath=true`. Generated CMake
contains exactly one `target_link_libraries(LWIP PRIVATE m)`, two compile/link
occurrences each of the expected FPU and ABI flags, and no mailbox. All nine
managed-file hashes reproduce their declared hashes. The managed manifest's
`projectManifestSha256` is the canonical model hash, not the raw JSON-byte
hash; an independent runtime calculation reproduced
`c4b6307f3d9cbeea276b9f0751918cefd18961c789d9c2faecc29ac694969323`.

## Independent H1 verification

The two public builds both returned `status=success`. They bind the same
project head, input snapshot
`dd4720e9e09aa5db919c232db1b4551b3e4bc882786129eb064c5c1e3eb5c6b6`,
and build ID
`78007c0232fb954a1aa775dc67efdcc7757780f949740eec9ed8382ddbd01c5a`.
Independent SHA-256 comparison reproduced byte equality for all four required
artifacts:

| Artifact | SHA-256 |
| --- | --- |
| `LWIP.elf` | `f59b84097e2f78a7e93f1c8a7d1041bd5818169bdf25d6598a8f749082475b6c` |
| `LWIP.map` | `8d7903b81a73ee1fc0e28c6a4d4140e6e5b09d6028e35e67388440e1873a1ee7` |
| `LWIP.hex` | `a89fb7874255bfd47282f44ba655b12e4615669e286caeeabe65f2a0c008801d` |
| `LWIP.bin` | `fa6915a18d4dc3b9f56b648804a4a6b0741df24aa992aa262b39bc346042f69c` |

An independent read-only pyelftools verification against the frozen build-2
ELF returned `all_pass=true`. It reproduced entry/Reset vector
`0x080004e9`, `.isr_vector` at `0x08000000`, initial SP `0x20030000`, one
strong `TIM3_IRQHandler`, `main`, and global `testtime`. All alloc sections and
load segments lie inside IROM1, IRAM1, or IRAM2; the entire
`0x2002eff0..0x20030000` interval is free; no mailbox section/symbol and no
global undefined symbol exist.

The actual link command contains one ordered `-lm`. `atan2f`, `cosf`, and
`sinf` are defined in the final ELF, have real call sites, and are attributed
by the MAP to the hard-float `libm.a` members. The source declaration and DWARF
type chains retain non-volatile `testtime`; the ELF symbol supplies its address
`0x20000134`.

The active runtime was independently rechecked after the implementation work.
Doctor returned `ok=true` on explicit project root. Runtime state remains
source commit `0cdd142f...`, release-manifest SHA-256
`8ecb1e3a9155da851fde212eefdc735a7b6b5f510d12e3eec4e1263b1e589814`,
CPython 3.12.10 supported, Toolkit/Monitor 0.9.0 compatible, 64 release wheels,
48 MCP tools, and 8 Skills. There are zero runtime process holders and zero
reparse points; the prior runtime remains recoverable in its retired sibling.

All five original assets at the resolved frozen source root
`D:\workspace\WDS_CODE\test` were independently rehashed and reproduce the
frozen uvprojx, ARMCC startup, AXF, MAP, and HEX SHA-256/size values. The
business-source Git blobs for `Main/Main.c`, `Main/stm32f4xx_it.c`, and the
GPIO header equal the restart-base blobs. D4/LED1 remains the active-low PE4
toggle and no instrumentation, fault, hardware-control, or mailbox behavior
was added. The older project commits and the original failed-link evidence
remain addressable.

## Warnings, cleanup, and final boundary

Each build retained exactly two classified warnings: the legacy CMSIS `sp`
clobber deprecation and the pre-existing `WirelessCharg.c` aggressive-loop
undefined-behavior warning. Neither was introduced by this campaign diff, and
the frozen scope prohibited unrelated legacy-source edits. They are recorded
application-maintenance risks, not an unresolved Toolkit/H1 conversion defect.

The implementation owner moved all 81 public-build run outputs out of the
project worktree into the recoverable evidence residual
`C:\tmp\stm32tk-vs10a-legacy-campaign\evidence\project-final-run-outputs-standard-math`.
Final-state evidence SHA-256 is
`9c948b2a9a718d309dcb592c401f7eca91558b8c96fc489b24b2ccf54d20d529`.
The source project, detached project review, Toolkit implementation, and
Toolkit product-review worktrees were independently observed clean; the
project has zero remotes. The exact
`C:\tmp\stm32tk-vs10a-legacy-campaign\scratch\standard-math-build1-reset`
residual remains `ENVIRONMENT/cleanup-policy`; no bypass was attempted.

No non-deferred H1 gate failed and no product defect remains in the reviewed
scope. Hardware work is now eligible for a separate user-controlled phase, but
this task stops before touching the connected board.
