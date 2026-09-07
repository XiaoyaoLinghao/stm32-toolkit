# STM32TK-1001 GNU MAP Exact-Width Section Plan

**Goal:** Correct the one-character wrapped-section boundary exposed by the Task 8 P2 real MAP
without weakening any other MAP/ELF validation.

**Design:** `docs/superpowers/specs/2026-09-07-stm32-toolkit-1001-gnu-map-exact-width-section-design.md`

**Base:** `69b7f2e2fdc45a6052adb1680d778b7e54f125d6`. One existing GPT-5.6-luna/max
implements; GPT-5.6-sol independently reviews. Project candidate stays uncommitted during the
product correction.

## Task 1: RED and minimal parser correction

1. In `test_build_map.py`, add an exact 16-character wrapped output-section case using
   `.stm32tk_mailbox`, matching alloc ELF evidence, exact VMA, and exact size. Run only that test at
   the base and record the expected `BUILD_MAP_INVALID`/missing failure.
2. Add a boundary case proving a 15-character name-only row is not accepted as a wrapped section.
3. Change only `_WRAPPED_SECTION_NAME_RE` so the total accepted name length begins at sixteen rather
   than seventeen. Do not special-case mailbox or relax the continuation regex.
4. Run the two boundary tests, existing wrapped-section tests, and complete `test_build_map.py` with
   an external basetemp and no pytest cache. Run `git diff --check` and `git diff --name-only`.
5. Commit product code and tests together. Append exact RED/GREEN evidence to the Task 8 SDD report;
   do not self-accept.

## Task 2: Independent review and runtime integration

1. Sol reviews the complete `69b7f2e2..CodeHead` diff in a clean detached worktree and runs only
   `test_build_map.py` plus any directly affected runner test justified by the diff.
2. If accepted, rebuild the existing campaign-local 0.9 runtime from CodeHead using the established
   offline runtime process and record its state hash. Do not install globally.
3. The same Luna/max Task 8 implementer resumes the existing uncommitted project candidate, clears
   only its run-owned stale build outputs after preserving diagnostics, and reruns public build with
   the rebuilt runtime.
4. If the public build passes, continue the parent Task 8 offline fixture/digest/no-write proofs and
   P2 project commit. Hardware remains prohibited until a later independent project review.
