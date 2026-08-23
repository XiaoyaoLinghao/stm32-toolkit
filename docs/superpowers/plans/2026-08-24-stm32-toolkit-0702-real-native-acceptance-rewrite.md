# STM32 Toolkit VS07-B Real Native Acceptance Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use TDD/writing-good-tests,
> systematic-debugging, and verification-before-completion. The same sole
> GPT-5.6-luna/max implementer executes Tasks 1RR-3RR sequentially and does not
> dispatch another agent.

**Goal:** Replace the rejected simulated-native boundary with the exact CubeMX
6.18/F4 repository, process, output-root, transcript, and parser behavior proven
by Sol's real probes.

**Architecture:** Environment discovery binds one safe package directory and
one case-correct CubeMX MCU descriptor. The adapter owns a fully isolated
control lifecycle and generates one child project below a same-volume
container. Static captured protocol and real-template fixtures drive strict
validation before Toolkit configure/build and transactional activation.

**Tech Stack:** CPython `>=3.12,<3.13`, pathlib, XML, dataclasses, existing
bounded process/configure/build workflows, pytest, STM32CubeMX 6.18.1-RC2,
STM32Cube_FW_F4_V1.28.3.

## Global constraints

- Accepted base: `bff9cc120923b0e9f2ba29a1b3511f1bcc26ab6e`.
- Redesign input: `0553c6e71812d648d0642b2f9d66688aa8cd0084`.
- Design:
  `docs/superpowers/specs/2026-08-24-stm32-toolkit-0702-real-native-acceptance-redesign.md`.
- Work only in `C:/tmp/stm32tk-0702-creation-apply` on
  `codex/STM32TK-0702-CREATION-APPLY`.
- One Luna/max owns all product/test/report commits. Sol writes no product code
  and performs the final complete-diff review.
- No remote, install, hardware, release, VS07-C, extra Python, coverage, or
  platform-matrix work.
- Use static hand-checked fixtures. A helper that derives expected protocol
  responses from the generated script is forbidden.

## Task 1RR: Bind the official environment and real native process

**Files:** modify `creation_environment.py`, `cubemx_adapter.py`, their tests,
and add static transcript evidence below
`tools/stm32-toolkit/tests/fixtures/cubemx-6.18/native-f429/`.

**Interfaces:**

- `CreationExecutionEnvironment.native_source_token: str | None`
- `CreationExecutionEnvironment.native_descriptor_path: str | None`
- `CreationExecutionEnvironment.native_descriptor_sha256: str | None`
- `CubeMXExecutionResult.project_root: Path`; no public/live `control_root`
- `_closed_environment(..., isolated_temp)` emits exact closed `TEMP`/`TMP`

- [ ] Add RED tests named for these breaks: official `.zip` siblings are not
  package directories; unsafe matching redirects still close; normalized MCU
  resolves the exact descriptor `RefName`; descriptor ambiguity/drift closes;
  missing TEMP/TMP reproduces process failure; project path uses native Windows
  spelling; output is the exact destination-leaf child; every setup/process/
  protocol/IOC-drift exit removes control root; IOC copied bytes are the bytes
  hashed. Run them and record the expected failures against `0553c6e7`.
- [ ] Commit a static sanitized positive stdout fixture and stderr warning
  fixture derived from `C:/tmp/p0702-native-capture-r8`. Include fixed literal
  command echoes and responses; do not call a transcript builder. Add RED
  missing/duplicate/reordered/KO variants by literal fixture edits in each test.
- [ ] Implement directory-only package selection, bounded descriptor parsing
  and digest binding, isolated temp, single-read IOC staging, native path/token,
  exact child-root validation, and adapter-owned `finally` cleanup.
- [ ] Run `test_creation_environment.py test_cubemx_adapter.py
  test_creation_authorization.py test_creation_apply.py` with a short basetemp;
  require zero skip/xfail and commit product/tests.

## Task 2RR: Parse and activate the real native project root

**Files:** modify `cubemx_project.py`, `creation_apply.py`, their tests, and the
real-template fixture subtree under `fixtures/cubemx-6.18/native-f429/`.

**Interfaces:** apply receives the adapter's exact `project_root`; parser first
returns a bounded inventory, and host-path scanning consumes that inventory.

- [ ] Build the native fixture from r8 `CMakeLists.txt`, `CMakePresets.json`,
  `cmake/gcc-arm-none-eabi.cmake`, nested CMake, IOC, linker script, and literal
  listed source/include placeholders. Preserve the actual Debug generator
  expression and package spelling.
- [ ] Add RED tests proving the r8 tree parses and configures, the r6 absolute/
  missing-source tree closes, the Debug expression is not an unconditional
  define, exact package family/version agreement is required, and no file is
  read by host-path scanning before inventory bounds.
- [ ] Add RED lifecycle tests proving configure/build run in the child root,
  activation moves only that child, container/control cleanup is exact for
  absent and empty destinations and every typed failure, and no host path is
  activated.
- [ ] Implement the bounded parser and child-root orchestration without
  fallback guessing or arbitrary CMake evaluation.
- [ ] Run parser/apply/workflow/configure/build affected tests with a short
  basetemp; require zero skip/xfail and commit product/tests.

## Task 3RR: Real native acceptance, aggregate verification, and return

**Files:** public regressions only if RED proves a break; update implementation
report and VS07-B SDD ledger after product CodeHead is committed.

- [ ] Run the exact approved 16-file command:

  ```powershell
  py -3.12 -m pytest tools/stm32-toolkit/tests/test_creation_authorization.py tools/stm32-toolkit/tests/test_creation_environment.py tools/stm32-toolkit/tests/test_cubemx_adapter.py tools/stm32-toolkit/tests/test_cubemx_project.py tools/stm32-toolkit/tests/test_creation_apply.py tools/stm32-toolkit/tests/test_creation_plan.py tools/stm32-toolkit/tests/test_creation_workflows.py tools/stm32-toolkit/tests/test_creation_cli.py tools/stm32-toolkit/tests/test_creation_mcp.py tools/stm32-toolkit/tests/test_process.py tools/stm32-toolkit/tests/test_generation.py tools/stm32-toolkit/tests/test_workflows.py tools/stm32-toolkit/tests/test_build_runner.py tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_mcp_server.py tools/stm32-toolkit/tests/test_mcp_roots.py -q --basetemp C:\tmp\p0702-rr-slice --junitxml=C:\tmp\p0702-rr-slice.xml
  ```

- [ ] In fresh disposable roots, run the public plan/prepare/apply path once
  for MCU `STM32F429ZITx`, then once for the captured real F429 IOC. Require
  successful strict parse, Toolkit configuration, Debug and Release builds,
  activation, portable output, no control/container residue, and no CubeMX/
  Java process. Do not use hardware.
- [ ] If the real F4 parent-plus-`Legacy` include declarations reproduce
  `BUILD_INPUT_INVALID` with `rule=duplicate`, add one focused build-input
  regression and make only exact-path recursive/explicit overlap idempotent.
  Preserve both model include paths and every existing alias, collision,
  redirect, escape, and type rejection; then restart Task 3RR from the exact
  16-file command.
- [ ] Before the next native retry, prove that a missing or unborn workspace
  Git HEAD is rejected by public prepare as `BUILD_GIT_INVALID`, before CubeMX
  or authorization persistence. Reuse the existing bounded Git-evidence
  primitive and do not initialize or commit from product code. For both
  positive native scenarios, create a fresh local repository and initial test
  commit with command-scoped identity and no remote, then restart Task 3RR from
  the exact 16-file command.
- [ ] Run `compileall`, accepted-base `git diff --check`, inspect the complete
  diff/status, and confirm the branch has no upstream/push.
- [ ] Commit product/tests before reports. Then rewrite the implementation
  report and ledger with normal Markdown backticks, CodeHead before the report
  commit, exact RED/GREEN counts, real native commands/results, package facts,
  clean/unpushed state, and `pending Sol review`; commit docs separately.

Sol then creates a new clean detached worktree at the returned HEAD, reviews
`bff9cc120923b0e9f2ba29a1b3511f1bcc26ab6e..HEAD`, repeats the exact slice and
both real native scenarios, and issues the only verdict. Any load-bearing
recurrence returns to this interface design, not a compatibility shim.
