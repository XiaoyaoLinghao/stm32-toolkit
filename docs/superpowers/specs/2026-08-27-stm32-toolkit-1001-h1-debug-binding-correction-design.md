# STM32TK-1001 H1 Debug Binding Correction Design

**Status:** Approved by the user's 2026-08-27 instruction to start the named
connected-hardware operation under the previously delegated best-choice authority.

**Module and phase:** STM32 Toolkit VS10-A,
`STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP`, reopened H1 before H2.

**Toolkit ledger:** accepted product base
`29d063a2b922dd636e0865ae3c0c6a825592dfb3`; accepted product code head
`0cdd142f80421c6aea59e81e963936779b05f00f`; current report head before this
design `8251b9316b3f8863b20fb80975b42d6a7dbf6e0c`; branch
`codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`. Sol owns the design,
plan, complete-diff review, and acceptance. The original Luna/max project owner
owns the bounded project correction and physical evidence. No remote action is
authorized.

**Project ledger:** local-only repository
`C:\tmp\stm32tk-vs10a-legacy-campaign\project-standard-math`, branch
`codex/STM32TK-1001-P1C-STANDARD-MATH-CORRECTED`, accepted project head
`9aae7ffd860405fadb7ac5f6278bcbb93add8d16`, tree
`536a9ef60b416c4695799a03475b58883646939f`, clean, and zero remotes.

## 1. Trigger and corrected verdict boundary

Windows passively reports the expected connected probe at
`USB\VID_C251&PID_F001\0001A0000000`, including its HID interfaces and COM7.
That evidence is `OS_USB_VISIBLE`, not Toolkit or H2 PASS. Its retained evidence
SHA-256 is
`815a74114fb01a8f52cb538b08480b9d510edb9dfb359bd7622b8c46ffa5db9b`.

The first public `probe list` attempt stopped before backend enumeration with
`HARDWARE_INPUT_INVALID` because the schema-v3 project manifest contains
`"debug": {}`. The corrected precheck evidence SHA-256 is
`0360dfd5c0e174532ea4f71f7de3842de1316cdeaf0a89c7d063da09f7bebda3`.
No attach, reset, target read, or flash occurred.

The previously recorded H1 acceptance is therefore reopened: VS10-A design
requires debug target `stm32f429zgtx` before H2, but that condition was not met.
No H2 action may start until the correction below is implemented and Sol issues
a fresh H1 verdict.

## 2. Runnable scenarios

1. A project owner loads the corrected manifest through the public project model;
   it yields backend `pyocd`, target `stm32f429zgtx`, and the exact project-contained
   STM32F429 SVD.
2. The owner runs public guarded configure and two public `arm-debug` builds. The
   configuration is reproducible, build identities agree, and firmware bytes stay
   identical to the accepted standard-math candidate because debug metadata is not
   a compile or link input.
3. After independent H1 acceptance, public `probe list` enumerates the connected
   probe without attaching to the target. Only then may the H2 identity/read/flash
   gates begin.

## 3. Frozen correction

The project repository, not Toolkit product code, receives exactly these source
facts:

- `.stm32-project.json` changes `debug` from `{}` to backend `pyocd`, target
  `stm32f429zgtx`, and SVD path `svd/STM32F429.svd`;
- `svd/STM32F429.svd` is copied byte-for-byte from
  `C:\ST\STM32CubeCLT_1.22.0\STMicroelectronics_CMSIS_SVD\STM32F429.svd`;
- the source SVD is 2,118,594 bytes, declares device `STM32F429`, version `1.9`,
  is Apache-2.0 licensed in-file, and has SHA-256
  `2b7de1e383ee415f45339b776942fe01f7b48215316629c3cc280e12661c2400`;
- no other project source, conversion output, build setting, or Toolkit byte is
  directly changed by this correction.

The manifest is the version-controlled project model authority defined by the
VS10-A design. The change is a user-authorized, bounded project configuration
correction after the public H1/H2 boundary exposed a missing explicit fact. It is
not conversion inference, a source portability workaround, or permission for
unbounded manual editing. Exact before/after bytes and Git diff remain reviewable.

Public guarded configure owns any resulting managed-file updates. Direct edits to
managed generated files are forbidden.

## 4. Rejected alternatives

- Changing the migration planner to infer a debugger target is rejected because
  migration intentionally supports build-only manifests and must not guess debug
  facts.
- Adding a public debug-config setter is rejected because it expands the 0.9
  product surface for a single project-fact correction.
- Passing a target or SVD through a CLI override, calling PyOCD directly, or
  flashing outside Toolkit is rejected because callers may not inject those pins
  or bypass the public workflow.
- Deferring the SVD is rejected because H2 explicitly requires an exact SVD-based
  GPIOE ODR/PE4 observation; omitting it would knowingly create the next blocker.

## 5. Acceptance and safety gates

Before H1 can be accepted again:

- Toolkit product code and tests remain byte-identical to
  `0cdd142f80421c6aea59e81e963936779b05f00f`;
- the project correction diff contains only the manifest and copied SVD before
  guarded configure, then only the exact public configure plan's managed outputs;
- the model loads the three explicit debug facts and exact SVD selection succeeds
  for `STM32F429ZGTx` without hardware;
- public configure dry-run/apply succeeds against the same unchanged plan;
- two clean public builds have equal new input snapshot/build identity and retain
  the accepted ELF SHA-256
  `f59b84097e2f78a7e93f1c8a7d1041bd5818169bdf25d6598a8f749082475b6c`
  and MAP SHA-256
  `8d7903b81a73ee1fc0e28c6a4d4140e6e5b09d6028e35e67388440e1873a1ee7`;
- all earlier H1 vector, entry, symbols, memory, and link findings remain valid or
  are rerun only where the project/config bytes are a documented risk trigger;
- Sol independently reviews the complete accepted-project-head-to-candidate diff,
  reconciles evidence, and issues the only H1 verdict.

After H1 acceptance, `probe list` remains enumeration-only. Target attach, identity
read, and guarded flash are separate ordered H2 actions. Any probe mismatch,
unexpected owner, target mismatch, changed safety topology, heat, smell, or abnormal
board behavior stops the activity. No push, PR mutation, merge, tag, release,
remote branch operation, network action, direct backend bypass, or unrelated
hardware action is included.
