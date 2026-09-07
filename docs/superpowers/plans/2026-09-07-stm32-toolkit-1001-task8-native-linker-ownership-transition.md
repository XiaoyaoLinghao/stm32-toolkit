# STM32TK-1001 Task 8 Native-Linker Ownership Transition Plan

**Goal:** Correct only the omitted managed-to-native linker ownership transition, obtain a valid
project RED, then resume the already approved Task 8 Steps 2-3 offline P2 implementation.

**Design:** `docs/superpowers/specs/2026-09-07-stm32-toolkit-1001-task8-native-linker-ownership-transition-design.md`

**Owners:** GPT-5.6-sol owns design, plan, complete-diff review, and verdict. The existing single
GPT-5.6-luna/max Task 8 implementer owns every project change and implementation test. It cannot
accept its own work.

**Exact bases:** Toolkit `93d5b32dd2dc2cb613ba9c68f714abd95df83d14`, project
`cf273a18b4c757b4866793c94b25d5ceaad39925`. No remote or hardware authority is included.

## Task 1: Freeze and commit the correction documents

- Sol checks the design for placeholders, ambiguity, scope expansion, and conflict with the parent
  Task 8 contract.
- Commit only this design and plan on the existing Toolkit implementation branch.
- Reconfirm that the project candidate remains uncommitted and Toolkit has no other tracked change.

## Task 2: Perform the exact ownership handoff and reproduce RED

The existing Task 8 Luna/max implementer must:

1. Audit the current project tracked/untracked state and the two existing candidate files. Preserve
   retained H2 evidence and report its location; do not treat it as Task 8 evidence.
2. Before mutation, require the old linker file and its one managed record to match SHA-256
   `f1eb3fb59947caea5011bcdbce3d757e8a46600a05779ec57f1e43d694ab2706` and require project HEAD
   `cf273a18b4c757b4866793c94b25d5ceaad39925`.
3. Complete the design's closed transition: native candidate, exact manifest selection, remove only
   the old linker managed record, delete only the old tracked linker.
4. Run pinned-runtime public configure dry-run. Any blocker stops. Apply only the fresh plan ID with
   `--authorized`, then prove the generated manifest omits the old linker and CMake names the native
   linker exactly once.
5. With no emitter and no `.stm32tk_mailbox` output section, run the public Debug build. It must
   succeed; inspect the new MAP/ELF and record the required absence as RED. Any earlier failure is a
   blocker, not RED.
6. Run `git diff --check` and `git diff --name-only`. Record exact commands/results in the existing
   SDD `task-8-report.md`. Do not commit a deliberately broken project state unless needed to make
   the RED evidence independently reproducible; normally retain RED evidence in the report and
   continue directly to Task 3.

## Task 3: Resume parent Task 8 GREEN and offline proofs

The same implementer must:

1. Add only project-owned emitter source/header and the minimal existing TIM3/main hooks required by
   the parent Task 8 brief.
2. Complete `linker/vs10a.ld` with the exact output section, `KEEP`, alignment, `NOLOAD`, and size
   assertion. Rerun the public guarded configure cycle when generated inputs change.
3. Build P2 and run focused project tests proving exact section address/size/ownership/non-overlap,
   frame structure and CRC, inventory-first ordering, bounded output-only ring behavior, heartbeat
   timing/state, exact case digest, decoding by the current Toolkit v2 decoder, and no target write
   surface.
4. Run `git diff --check`, `git diff --name-only`, the complete Task 8 offline target suite, and a
   clean project status audit. Commit project code/tests as P2 and append exact head/tree/evidence to
   `task-8-report.md`. Do not self-accept and do not run hardware.

## Task 4: Independent review

- Generate a review package for project base `cf273a18...` through P2 head.
- A clean independent GPT-5.6-sol reviewer checks the complete diff, ownership transition, retained
  safety behavior, RED-before-GREEN evidence, MAP/ELF/decoder/digest/no-write proofs, and scope.
- Run only reviewer-selected affected offline checks with a fresh external basetemp. Classify and
  clean only review-owned temporary outputs.
- A clean verdict permits returning to parent Task 8 Step 4. It does not authorize attach, flash,
  Target execute, remote mutation, release, or VS10-B.
