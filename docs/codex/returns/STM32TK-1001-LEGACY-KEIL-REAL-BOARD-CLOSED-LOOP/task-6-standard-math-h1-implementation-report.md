# STM32TK-1001 Task 6: standard-math P1c/H1 implementation report

Implementation evidence only. This report is not self-acceptance. The
implementer is GPT-5.6-luna/max; the result is waiting for an independent
GPT-5.6-sol complete-diff and evidence review. No hardware acceptance is made.

## Lineage and boundaries

- Accepted Toolkit product base: `29d063a2b922dd636e0865ae3c0c6a825592dfb3`.
- Standard-math product code head used by the runtime:
  `0cdd142f80421c6aea59e81e963936779b05f00f` (tree
  `c33729b55bcfcb40ff782e81548f5e2cba8a8e2f`).
- Toolkit worktree for this report:
  `C:\tmp\stm32tk-1001-legacy-hardware-impl`.
- Toolkit report-parent HEAD before this report-only commit:
  `706e36c1a9927bfd7b75f620e99fbea4364c357b` (tree
  `a26785368863867c3ee1df6f86c69f4e94dc0ede`).
- Project source root used for the preserved legacy assets:
  `D:\workspace\WDS_CODE\test`.
- Corrected project worktree:
  `C:\tmp\stm32tk-vs10a-legacy-campaign\project-standard-math`.
- Project base: `718c37ed5d381f01680e64abe8c3810d62723b2a` (tree
  `2990239f436c259ae3652cc0df48b9411b14b381`).
- Conversion commit: `43af128b9629ce203c9f3c49090a41aefe6f6d63`.
- Configuration/project final head: `9aae7ffd860405fadb7ac5f6278bcbb93add8d16`
  (tree `536a5aaedfefb35e7755cef22e9410b4bc6f27ea`).
- Project branch: `codex/STM32TK-1001-P1C-STANDARD-MATH-CORRECTED`.
- Project tracked diff from `718c37ed...` contains exactly the 13 public
  conversion/configuration artifacts; no C, H, S, or ASM source path changed.
  The 81 disposable public-build run outputs were reversibly moved with native
  `Move-Item` to
  `C:\tmp\stm32tk-vs10a-legacy-campaign\evidence\project-final-run-outputs-standard-math`.
  The project source worktree is now clean and has zero remotes.

The active managed runtime was not changed in this report task. Its state file
is `C:\tmp\stm32tk-vs10a-legacy-campaign\data\runtime\runtime-state.json`,
SHA-256 `63343866b035f97c89a8e72e614341509226cf9810f51f379c6cf41b2a3fb1de`.
The state identifies version `0.9.0`, source commit
`0cdd142f80421c6aea59e81e963936779b05f00f`, release manifest
`8ecb1e3a9155da851fde212eefdc735a7b6b5f510d12e3eec4e1263b1e589814`, and
generation 1. The verified runtime facts are CPython 3.12.10, Toolkit/Monitor
0.9.0, 64 release wheels, 48 MCP tools, 8 Skills, and doctor OK.

Boundaries for this slice were `hardware=false`, `physicalAcceptance=false`,
`network=false`, `remoteGitMutation=false`, `goldenWrite=false`, and
`ToolkitProductMutation=false`. The original Keil inputs and historical output
files were read-only throughout.

## Conversion and configuration evidence

The public conversion apply evidence is
`C:\tmp\stm32tk-vs10a-legacy-campaign\evidence\task-4a-conversion-apply.json`
(SHA-256 `3cb23c14975ccbf5d7ec7fb6559edfa248cb67d163cb5442e268901f121e5706`).
It records the fresh plan and authorized apply with zero blockers and the exact
three conversion writes. The resulting manifest is
`STM32F429ZGTx`, Cortex-M4, `fpv4-sp-d16`, hard ABI; no fixed sections, source
patches, or source-byte changes were introduced.

The public configuration apply evidence is
`C:\tmp\stm32tk-vs10a-legacy-campaign\evidence\task-4a-configure-apply.json`
(SHA-256 `bf830b9a04efca23f2c4f58e57c6b1f9a47719690e7da8918a1f9ad7ec990cab`).
It records the fresh plan/apply and the ten managed generated files. Compile and
link each contain exactly one `-mfpu=fpv4-sp-d16` and one
`-mfloat-abi=hard`; no FPU2, soft/softfp ABI, linker-vs10a script, mailbox, or
instrumentation was proposed or generated.

## Two reproducible public builds

The build comparison evidence is
`C:\tmp\stm32tk-vs10a-legacy-campaign\evidence\build-standard-math-comparison.json`
(SHA-256 `f73c27f3af017626ce99dc189a8bc0c79bbc0aa53cd72673daaef4c1279bb0`).
Both public `build --preset arm-debug --json` invocations exited 0. They have
the same build ID
`78007c0232fb954a1aa775dc67efdcc7757780f949740eec9ed8382ddbd01c5a`, input
snapshot
`dd4720e9e09aa5db919c232db1b4551b3e4bc882786129eb064c5c1e3eb5c6b6`, and
project head `9aae7ffd860405fadb7ac5f6278bcbb93add8d16`. The byte-identical
build-2 artifacts are:

| artifact | size | SHA-256 |
| --- | ---: | --- |
| `LWIP.elf` | 1,011,052 | `f59b84097e2f78a7e93f1c8a7d1041bd5818169bdf25d6598a8f749082475b6c` |
| `LWIP.map` | 801,205 | `8d7903b81a73ee1fc0e28c6a4d4140e6e5b09d6028e35e67388440e1873a1ee7` |
| `LWIP.hex` | 146,319 | `a89fb7874255bfd47282f44ba655b12e4615669e286caeeabe65f2a0c008801d` |
| `LWIP.bin` | 52,000 | `fa6915a18d4dc3b9f56b648804a4a6b0741df24aa992aa262b39bc346042f69c` |

Build-1 and build-2 evidence are retained independently at
`evidence/build1-standard-math` and `evidence/build2-standard-math`.

## P1c/H1 software evidence

The standard-math link proof is
`evidence/h1-standard-math-link.json` (SHA-256
`827dcdae5a4f21e9e5f9e09aac25c8dd958afe25ccb2febca778ae8dd8757e34`). It
proves one ordered `-lm`, hard-float link flags exactly once, final `cosf`,
`sinf`, and `atan2f` definitions attributed to the hard-float libm archive, and
zero strong unresolved symbols.

The entry/symbol proof is
`evidence/h1-standard-math-entry-symbols.json` (SHA-256
`5e3967a6ec58e84c083fb9fb8584adbdc50f8f84cb8473d838b4e2e769cabc33`). It
records ELF entry `0x080004e9`, `.isr_vector` at `0x08000000` with size
`0x1ac`, initial SP `0x20030000`, a Thumb Reset_Handler matching the entry,
`main`, one strong Thumb `TIM3_IRQHandler`, and DWARF `testtime` with a valid
type/location inspection and no volatile qualifier.

The memory/identity proof is
`evidence/h1-standard-math-memory-identity.json` (SHA-256
`885e25c54fa3cd3b0b63e1055f62427c444568769225b204514398b67a08ebce`). It
records IROM1 `0x08000000..0x08100000`, IRAM1
`0x20000000..0x20030000`, IRAM2 `0x10000000..0x10010000`, no alloc-section or
segment overflow/overlap, an empty `0x2002eff0..0x20030000` interval, and no
mailbox section/symbol.

The historical/GCC memory comparison is
`evidence/memory-comparison.json` (SHA-256
`b22338c8f792134cc89149e390c1a8d32db7642a3419548b0d07f8e3ffaa9d2e`). The
retained ARMCC MAP prints Keil ROM total 63,956 bytes, RW total 408,016 bytes,
and image component columns `62772, 5540, 1004, 1576, 406440, 534601`; its
execution regions include IROM1 `0x08000000/0x0000f920`, RW_IRAM1
`0x20000000/0x0001e8d0`, and the four absolute pool regions at
`0x10000000`, `0x1000f000`, `0x68000000`, and `0x68032000`. GCC directly lists
`.text=51412`, `.isr_vector + .ARM.exidx=436`, `.data=148`, and
`.bss + .heap + .stack=127828`, with the tool-reported IROM1/IRAM1/IRAM2
usage retained separately. Metrics with non-equivalent linker accounting are
explicitly marked non-comparable; no invented delta is claimed. The Keil
top-interval proof is only execution-region level because no retained
symbol-level scan exists, and is marked N/A at that narrower level.

The original-asset proof is
`evidence/h1-standard-math-original-assets.json` (SHA-256
`5853e3c4c95aea972eafb2364204c60eaed7e0adcf969802701875f982d136d5`). All
five frozen assets match the actual source root: `Project/LWIP.uvprojx`
`8efeec8cbe9366a8451d5bd59a00bf1dc11b5cff6e837a5ef12e005d609caa47`, ARMCC
startup
`faa280e93ab6cb7d24b27359aba718fdd1d7a94cce375ef9fbaecdd9cf38bdd7`,
historical AXF
`65f5b98c970befbea2c7fd529f54a51438b3c635d794e20519d284c33976c225`, MAP
`6fca9fc30bd964f81da0c2417d46fe6930f6317ce96ee30d63fbf2981e8bbe9f`, and HEX
`1a18daaa9d608f41d21a4a41d14fea852c2f978053f3dff44383c38e3c643a84`. The
source-preservation proof is
`evidence/h1-standard-math-source-preservation.json` (SHA-256
`b9ec35e69cc26ebd4b5dba097de6d6128e16543ea4d427f5325bb83d197629ea`). It
records zero source or historical-asset path changes, preserved D4/LED1 PE4
active-low toggle semantics, non-volatile `testtime`, and no added
instrumentation, fault, hardware-control, or mailbox behavior.

The two existing warnings are intentionally preserved and classified:

1. `Startup_config/core_cm4.h:94:28`: deprecated `sp` clobber listing,
   `UPSTREAM_CMSIS_LEGACY_HEADER`.
2. `WirelessCharg/WirelessCharg.c:217:119`: aggressive-loop-optimizations
   undefined-behavior warning, `LEGACY_PRODUCT_SOURCE`.

Neither warning caused a source edit. The retained build-log evidence is
`evidence/build2-standard-math/build.log`, size 7,339, SHA-256
`f04ffa7663c3af47e9b38f8e10c9d3230fa95cadd7685758ece7e6fd2045066a`.

The candidate/runtime evidence is
`evidence/task-3g-standard-math-candidate-runtime.json` (SHA-256
`585a28a41e8a5a95588a85d55236f20e96c4f97170b340b57ffd3bba069e44e3`). It
records two 13/13-identical candidates, release manifest
`8ecb1e3a9155da851fde212eefdc735a7b6b5f510d12e3eec4e1263b1e589814`, successful
bundle verification, 64 wheels, 48 MCP tools, and 8
Skills. The runtime replacement was already completed and is treated as an
unchanged input boundary for this report.

## Formal campaign evidence and cleanup

`evidence/p1c.json` (SHA-256
`ef47b2b3571fa68bfa9585825338e14053389d832d244f6bf4260734f4bf3541`) binds
the accepted product base, code/runtime identity, project base/conversion/
configuration commits, both build identities, all H1 proofs, warnings, and
the `hardware=false` boundary. `evidence/campaign-manifest.json` was preserved
byte-for-byte in all existing records and only received an appended
`standardMathH1` index. Its pre-addition SHA was
`00b55ec57fddb1e8c4e0a13fd4b4c5dc60f1c62c5c6b1f14e292e6d4709c6d76`; its
post-addition SHA is
`9d38a0f92254546fddc8b6d27d44451e857cc43a65e34652a3e573473ac81075`.

All newly generated JSON files parsed successfully. The final-state evidence is
`evidence/project-standard-math-final-state.json` (SHA-256
`9c948b2a9a718d309dcb592c401f7eca91558b8c96fc489b24b2ccf54d20d529`). The
only cleanup-policy residual recorded for this slice is the retained
`C:\tmp\stm32tk-vs10a-legacy-campaign\scratch\standard-math-build1-reset`;
the previously documented Toolkit test basetemps remain governed by their
earlier review report. No source-controlled file was removed or changed. No
hardware, network, remote Git, golden, or Toolkit product mutation occurred in
this report task.

The report itself is deliberately report-only and does not contain its own
final commit SHA. Independent Sol review is required before any acceptance
decision.
