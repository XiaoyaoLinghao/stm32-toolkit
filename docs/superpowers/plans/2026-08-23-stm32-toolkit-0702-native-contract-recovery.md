# STM32 Toolkit VS07-B Native Contract Recovery Plan

> **Worker requirement:** the same sole GPT-5.6-luna/max VS07-B implementer
> executes Tasks 1R-3R sequentially. Use receiving-code-review, executing-plans,
> TDD/writing-good-tests, and verification-before-completion. Do not dispatch
> another agent.

**Goal:** Replace the non-converged invented native protocol/CMake/lock seams
with the exact integration boundary frozen in the recovery design.

**Recovery input:** `9d388bfa35052cad86bc5e50d7d537de0abebc83`

**Design:**
`docs/superpowers/specs/2026-08-23-stm32-toolkit-0702-native-contract-recovery-design.md`

All original remote/install/hardware/Python/VS07-C constraints remain.

## Task 1R: Replace the protocol and isolated-home contract

**Files:** `cubemx_adapter.py`, `test_cubemx_adapter.py`, and apply/control
cleanup files/tests only when required.

- [ ] Add RED transcripts with native log4j/INFO/WARN/progress noise, exact
  per-command `OK`, and `exit` followed by `Bye bye` without `OK`. Prove the
  current equality parser fails them.
- [ ] Add RED literal script tests for MCU, IOC, and
  `loadboard <board> allmodes`; exact updater path
  `.stm32cubemx/plugins/updater/updater.ini`; `[Path] RepositoryPath`; and
  cleanup after every adapter exit class.
- [ ] Implement the ordered protocol state machine, exact source commands,
  exact updater layout, and returned/cleaned external control-root lifecycle.
- [ ] Run adapter/apply tests with a short basetemp; require exit 0 and no
  skip/xfail.

## Task 2R: Replace the CMake dialect parser

**Files:** `cubemx_project.py`, `test_cubemx_project.py`, and bounded fixture
files below `tools/stm32-toolkit/tests/fixtures/cubemx-6.18/`.

- [ ] Derive fixtures from the installed JAR entries
  `CMakeLists_template.txt`, `cmake_generated_template.cmake`,
  `cmake_generated_template-context.cmake`, `CMakePresets.json`, and
  `gcc-arm-none-eabi.cmake`. Preserve relevant scaffolding; substitute only
  closed F4/H7 placeholder values.
- [ ] Add RED tests proving `project(${CMAKE_PROJECT_NAME})`, preset toolchain
  discovery, nested generated lists, contained `CURRENT_SOURCE_DIR/../..`,
  context include, and per-file base retention. Prove missing/mixed dialects
  close.
- [ ] Implement the two exact dialect parsers with no fallbacks or arbitrary
  evaluation.
- [ ] Load the synthesized schema-3 model and run real Toolkit configuration
  planning for Debug/Release identities in tests.
- [ ] Run parser/generation/workflow affected tests; require exit 0 and no
  skip/xfail.

## Task 3R: Replace and prove the durable lock, then return

**Files:** authorization/apply lock implementation and tests, report, SDD
ledger.

- [ ] Preserve the round-2 failing test as RED. Add the same real-process
  serialization proof for authorization consumption.
- [ ] Replace `open("a+b")` locking with the frozen, identity-checked
  descriptor primitive. Re-run both process tests repeatedly and require every
  process exit zero with exact ordering/outcomes.
- [ ] Run the exact 16-file VS07-B slice from the original plan with JUnit XML;
  require every collected test pass, no skip/xfail.
- [ ] Run `compileall`, accepted-base `git diff --check`, and inspect full
  diff/status.
- [ ] Repeat doctor/create-plan/create-prepare in a fresh disposable workspace;
  require `CUBEMX_REPOSITORY_MISSING`, unchanged snapshot, and no CubeMX/Java
  process. Do not run native generation or install a package.
- [ ] Commit product/tests first. Update report/ledger with Sol round-2
  evidence, CodeHead before report commit, exact counts, environment blocker,
  clean/unpushed state, and no positive native claim; commit docs separately.

Sol then reviews the complete accepted-base diff in a third new clean detached
worktree. Any recurrence of this recovered interface is a design blocker, not
another local patch opportunity.
