# STM32TK-1001 H1 Debug Binding Correction Implementation Plan

> Execute sequentially. The original `gpt-5.6-luna/max` project owner implements
> and collects evidence; a `gpt-5.6-sol` reviewer independently accepts or rejects
> the complete diff. No actor accepts its own work.

**Goal:** Repair the missing explicit debug target and SVD project facts, re-prove
H1 without changing Toolkit product bytes, and only after acceptance continue to
the public H2 hardware gates.

**Design:**
`docs/superpowers/specs/2026-08-27-stm32-toolkit-1001-h1-debug-binding-correction-design.md`

**Accepted inputs:** Toolkit product code
`0cdd142f80421c6aea59e81e963936779b05f00f`; project
`9aae7ffd860405fadb7ac5f6278bcbb93add8d16`; runtime source/state
`0cdd142f80421c6aea59e81e963936779b05f00f` /
`63343866b035f97c89a8e72e614341509226cf9810f51f379c6cf41b2a3fb1de`.

**Frozen roots:** Toolkit
`C:\tmp\stm32tk-1001-legacy-hardware-impl`; project
`C:\tmp\stm32tk-vs10a-legacy-campaign\project-standard-math`; data
`C:\tmp\stm32tk-vs10a-legacy-campaign\data`; evidence
`C:\tmp\stm32tk-vs10a-legacy-campaign\evidence`; runtime Python
`C:\tmp\stm32tk-vs10a-legacy-campaign\data\runtime\0.9.0\Scripts\python.exe`.

## Task 1: Reconstruct and freeze the project correction

- [ ] Record fresh Toolkit/project branch, full HEAD/tree, tracked/untracked,
  staged/unstaged, remotes, runtime-state hash, relevant probe-owner processes,
  and source SVD metadata. Stop on any unexpected project change, any project
  remote, product-code drift, runtime-state drift, or probe owner.
- [ ] Reuse the existing failed public precheck as RED. Do not repeat it before
  the manifest correction and do not relabel OS USB visibility as probe PASS.
- [ ] Copy the CubeCLT SVD byte-for-byte to `svd/STM32F429.svd`; require size
  2,118,594 and SHA-256
  `2b7de1e383ee415f45339b776942fe01f7b48215316629c3cc280e12661c2400`.
- [ ] Change only the manifest `debug` value to the following canonical object:

```json
"debug": {
  "backend": "pyocd",
  "target": "stm32f429zgtx",
  "svd": "svd/STM32F429.svd"
}
```

- [ ] Run `git diff --check` and confirm the pre-configure diff names are exactly
  `.stm32-project.json` and `svd/STM32F429.svd`. Load the public project model and
  run the existing exact SVD selector offline for target device `STM32F429ZGTx`;
  require an exact selection and GPIOE/ODR/ODR4 availability without importing or
  opening PyOCD.
- [ ] Commit the project facts as one local project commit. Record full SHA/tree
  and exact diff/hash evidence outside both Git repositories.

## Task 2: Regenerate only through public guarded configure

- [ ] Invoke the installed 0.9.0 runtime with `-I -m stm32_toolkit.cli` and the
  explicit project/data roots. Run public `project configure --dry-run`; retain
  the operation envelope, plan ID, input digests, exact proposed files/diffs, and
  process/post-state audit.
- [ ] Review the plan. It may update only configuration-managed outputs caused by
  the three debug facts, including the existing Cortex-Debug launch configuration
  and managed manifest. It must not change C/C++/ASM, linker, CMake compile/link
  inputs, Keil sources, target memory, or hardware state.
- [ ] Apply exactly the unchanged guarded plan through the public command. Stop on
  plan drift, additional files, direct managed-file edits, or any hardware/backend
  process.
- [ ] Run `git diff --check`, confirm the manifest/SVD plus exact plan-owned file
  set, and commit the configure result separately in the local project repository.
  Record full SHA/tree and diff evidence.

## Task 3: Re-prove the risk-triggered H1 surface

- [ ] Run two public `build --preset arm-debug` operations with no source change.
  Use separate run-scoped output/evidence paths. Require both operations to succeed
  and to agree on input snapshot, build ID, ELF, MAP, HEX, BIN, entry/vector/reset,
  and declared inputs.
- [ ] Because only debug metadata and SVD changed, require the ELF SHA-256 to remain
  `f59b84097e2f78a7e93f1c8a7d1041bd5818169bdf25d6598a8f749082475b6c`
  and MAP SHA-256 to remain
  `8d7903b81a73ee1fc0e28c6a4d4140e6e5b09d6028e35e67388440e1873a1ee7`.
  A new input snapshot/build ID is expected; unexplained firmware-byte drift is a
  `PRODUCT/project` stop, not a tolerance opportunity.
- [ ] Recheck target/device/debug/SVD binding, readable/executable/writable memory,
  vector/SP/Thumb entry/Reset_Handler, unresolved strong symbols, region overflow,
  stale inputs, `main`, `TIM3_IRQHandler`, and DWARF `testtime`. Reuse earlier
  evidence only when exact firmware bytes and affected contracts prove it remains
  valid.
- [ ] Produce one H1 correction implementation report under
  `C:\tmp\stm32tk-vs10a-legacy-campaign\evidence`. It records accepted bases,
  project code head before any report-only commit, commands/exits/hashes, all
  cleanup, and an implementer verdict. It does not claim Sol acceptance or H2 PASS.
- [ ] Clean only disposable run-scoped outputs after retaining minimum evidence;
  preserve build outputs required for H2, project inputs, reusable fixtures, shared
  caches, user files, and failure evidence. Report exact residual cleanup failures.

## Task 4: Sol independent complete-diff H1 review

- [ ] Sol audits Toolkit and project state independently. Toolkit product code/tests
  must be byte-identical to `0cdd142f80421c6aea59e81e963936779b05f00f`.
- [ ] Review the complete project diff from
  `9aae7ffd860405fadb7ac5f6278bcbb93add8d16` to the returned candidate head, not
  just the report or last commit. Verify SVD provenance/hash/license, manifest
  facts, public configure ownership, no source/build-input drift, and evidence
  bindings.
- [ ] Independently run only the focused offline model/SVD checks and affected H1
  build/identity checks justified by the correction. Run `git diff --check` and
  verify both worktrees' exact status/remotes. Classify all failures before any
  revision request.
- [ ] Issue `ACCEPTED`, `REVISION_REQUIRED`, or `REWRITE_REQUIRED`. If revision is
  required, return to the same Luna/max owner; do not patch as Sol. H2 remains
  closed until `ACCEPTED`.

## Task 5: Ordered public H2 entry after H1 acceptance

- [ ] Reconfirm the disconnected-load safety topology, no probe owner, exact project
  head/clean state, runtime state, and OS probe identity. Stop on any change.
- [ ] Run one public `probe list` with a fresh safe session ID. Require exactly the
  expected CMSIS-DAP Probe ID `0001A0000000`; enumeration must close cleanly and
  must not attach, reset, read target memory, or flash.
- [ ] Through the next public read-only workflow, open only the named probe and
  verify the chip/target identity is STM32F429ZG / `stm32f429zgtx`. Release the
  session cleanly. Any mismatch stops before authorization or programming.
- [ ] Prepare fresh build/ELF/project/probe pins, then run exactly one public guarded
  flash with explicit authorization. Require segment validation and readback. No
  direct PyOCD, CubeProgrammer, Keil, or debugger flash is permitted.
- [ ] Collect the independent P1c smoke observations in order: user D4 approximately
  one-second blinking, bounded typed `testtime` activity, SVD GPIOE.ODR PE4
  transition, no active Cortex-M Fault, and one Monitor snapshot bound to the same
  project/firmware/probe/workspace identity.
- [ ] Stop and report after the P1c smoke verdict. Do not begin P2/H3 mailbox work
  automatically unless the smoke passes and the next-step boundary is explicitly
  reconciled against the VS10-A plan.

## Prohibited operations

No Toolkit product-code implementation, migration inference, new API/tool/Skill,
second runtime/backend/controller/provider, direct hardware backend, unrelated
project source edit, push, PR mutation, merge, close, tag, release, remote branch
operation, network action, or change to the disconnected external-load topology.
