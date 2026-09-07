# STM32TK-1001 Task 8 Native-Linker Ownership Transition Design

**Module / phase:** STM32 Toolkit 1.0 VS10-A, Task 8 offline P2 preparation  
**Parent accepted base:** `9b7839bb01f88a9e3d2c13203f38aa0d11647232`  
**Toolkit dispatch head:** `93d5b32dd2dc2cb613ba9c68f714abd95df83d14`  
**Project dispatch head:** `cf273a18b4c757b4866793c94b25d5ceaad39925`  
**Specification owner / reviewer:** GPT-5.6-sol primary  
**Implementation owner:** the existing single GPT-5.6-luna/max Task 8 implementer  
**User decision:** approach A approved on 2026-09-07

## 1. Problem and root cause

The approved Task 8 plan changes the generated Keil-conversion project from the Toolkit-managed
`linker/stm32tk.ld` to the project-owned `linker/vs10a.ld`. The first Task 8 RED candidate changed
`generation.nativeLinkerScript` before retiring the prior managed record. Public build therefore
failed before compilation with `BUILD_PROJECT_INVALID`, path `linker/stm32tk.ld`, rule
`ownership`; configuration dry-run reported `GENERATION_ORPHANED_MANAGED_FILE`.

This is not a Toolkit product defect. The existing generator and build runner intentionally reject
an old managed file that is no longer among generated targets. The repository's working native
linker fixture performs an explicit ownership transition: remove the exact prior managed record and
file after selecting the native linker. Task 8 omitted that transition step.

## 2. Runnable scenarios

1. The exact P1c managed linker bytes and managed-manifest record match SHA-256
   `f1eb3fb59947caea5011bcdbce3d757e8a46600a05779ec57f1e43d694ab2706`. The project copies those
   bytes to `linker/vs10a.ld`, applies only the frozen SRAM1 reservation, selects it as the native
   linker, and retires the exact old record and tracked file. Public configuration then has no
   orphan blocker.
2. Before any emitter exists, the transitioned project completes a public Debug build and the new
   ELF/MAP proves `.stm32tk_mailbox` is absent. This is the required Task 8 RED; no physical or
   transport PASS is claimed.
3. The same Task 8 implementer adds the approved v2 emitter and linker section. Public configure and
   build then produce P2 whose MAP/ELF, frame fixture, digest, and source scan satisfy the parent
   Task 8 Step 3 contract.

## 3. Frozen ownership transition

The transition is one closed project mutation and is permitted only from the exact project head and
tree already recorded in the SDD ledger.

1. Re-read `linker/stm32tk.ld` and `.stm32-toolkit/generated-files.json`. Require the old linker to
   be a regular tracked file, the managed record to appear exactly once, and both hashes to equal
   the frozen value above. Any drift stops without deleting or rewriting anything.
2. Create `linker/vs10a.ld` from the verified old bytes, then change only the approved memory facts:
   ordinary IRAM1 length `0x0002EFF0`; MAILBOX origin `0x2002EFF0`, length `0x00001010`.
3. Set `generation.nativeLinkerScript` to `linker/vs10a.ld` and add the already approved closed
   `testing.target` v2 memory-mailbox declaration.
4. Remove exactly the `linker/stm32tk.ld` record from the managed manifest and delete exactly the
   tracked `linker/stm32tk.ld`. No other managed record or file may change in this preflight step.
5. Run public configuration dry-run. It must report no blockers. Apply only that fresh plan ID with
   the existing authorized project-local configure path. The resulting generated inventory must
   omit `linker/stm32tk.ld`, and generated CMake must reference `linker/vs10a.ld` exactly once.

The deletion is recoverable from project Git and replaces, rather than duplicates, the linker
authority. Toolkit generator/build behavior is unchanged.

## 4. RED, GREEN, and evidence semantics

After the ownership transition and before emitter code, run the exact pinned 0.9 runtime public
build. A successful build whose ELF and MAP contain no `.stm32tk_mailbox` is RED. A configuration,
compile, link, or unrelated schema failure is not RED and stops the task.

GREEN remains byte-for-byte governed by parent Task 8 Steps 2-3: one 4112-byte project-owned object,
one `NOLOAD`/16-byte-aligned/`KEEP`ed section at `0x2002EFF0`, exact size assertion, output-only
bounded ring, CRC-32/ISO-HDLC, canonical JSON, TIM3-driven 64-bit monotonic time, inventory first,
two heartbeat epochs over at least 2200 ms, and the normal timer/PE4 case. Offline verification must
prove section placement and ownership, non-overlap, current Toolkit v2 decode, exact case digest
`966a489bdde16562885cc4ac3c3e2b9b9bde0b477f9c06aae25f4916be52c2b5`, and absence of a target
write API.

RED and GREEN evidence must name exact project commits, trees, runtime path, commands, outputs, and
run-owned cleanup. Historical P1c/H2 artifacts remain separately identified.

## 5. Failure semantics

- Old linker path, count, tracked state, or SHA mismatch: `PROJECT_STATE/BLOCKED`; no mutation.
- Any additional orphan, drift, collision, or generated-file change: `PROJECT_STATE/BLOCKED`.
- Build fails before section inspection: `BLOCKED_TEST_DESIGN` or the returned classified product
  error; do not claim RED.
- MAP/ELF ambiguity, overlap, wrong size/address, decoder rejection, digest mismatch, or any target
  input/write surface: `PRODUCT/BLOCKED`; do not proceed to hardware.

## 6. Non-goals

No Toolkit product/test behavior change, orphan auto-deletion, second generator/runtime/backend,
Agent-specific logic, schema expansion, Python/platform/MCU/probe expansion, CI, collaboration
automation, golden/original project mutation, probe/attach/read/reset/flash/Target execute, remote
operation, release, or VS10-B work is allowed.

## 7. Acceptance

The correction is accepted only when the exact ownership transition yields a clean public RED,
the parent Task 8 offline GREEN evidence passes, the project ends committed with only intended P2
files plus classified retained evidence, Toolkit tracked bytes remain unchanged after this design
and plan, and an independent Sol complete project-base-to-P2 review has no unresolved product or
safety finding.
