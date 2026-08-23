# STM32 Toolkit VS07-B Native Contract Recovery Design

**Status:** Approved interface-level recovery under the user's standing approval waiver

**Date:** 2026-08-23

**Accepted base:** `bff9cc120923b0e9f2ba29a1b3511f1bcc26ab6e`

**Recovery input:** `9d388bfa35052cad86bc5e50d7d537de0abebc83`

**Owner/reviewer:** GPT-5.6-sol primary agent

**Implementation owner:** the same sole GPT-5.6-luna/max VS07-B implementer

## 1. Why this is a design recovery

Sol review round 2 did not converge F2, F4, or F6. The exact 630-test slice
collected 630 tests but failed
`test_activation_lock_serializes_independent_processes`. More importantly, the
tests still described an invented CubeMX protocol and CMake topology rather
than the installed 6.18 facts:

- native `help; exit` emitted 307 non-empty lines, including normal log4j,
  INFO, WARN, help-body and progress lines; the protocol tail was `OK`, `exit`,
  `Bye bye` with no `OK` after `exit`;
- native `SetStructure` help confirms `Advanced/Basic`;
- native `loadboard` help requires a second `allmodes` or `nomode` argument;
- the real updater file is
  `.stm32cubemx/plugins/updater/updater.ini` and uses `[Path]
  RepositoryPath=...`, not `STM32Cube/Updater/Updater.ini` with `Repository=`;
- the installed global CMake template sets `CMAKE_PROJECT_NAME`, calls
  `project(${CMAKE_PROJECT_NAME})`, delegates generated lists to
  `cmake/stm32cubemx/CMakeLists.txt`, and binds the toolchain through
  `CMakePresets.json`;
- the installed context template instead includes the exact
  `mx-generated.cmake` file and owns its MCU/linker flags in the top-level
  file.

Because the same findings survived two review rounds, no further local patch
may be applied to the current interfaces. This amendment replaces the native
protocol/parser and lock seams as one coherent integration boundary.

The real positive `.ioc` and MCU scenarios remain blocked by the absent
`STM32Cube_FW_*` repository package. No package installation is authorized.

## 2. Frozen native command contract

The adapter generates exactly one source command:

- MCU: `load <validated-mcu>`;
- board: `loadboard <validated-board> allmodes`;
- IOC: `config load "<control-root/input.ioc>"`, after verifying the current
  bytes against the authorized source hash and copying them outside product
  staging.

The remaining commands are project name, quoted project path, CMake toolchain,
GCC compiler, `SetStructure Advanced`, project generation, and exit. Values
are either closed tokens or quoted absolute paths with quote/control rejection.
The adapter never uses comments as pseudo-commands.

CubeMX stdout/stderr is a mixed log/protocol stream. Validation is an ordered
state machine, not whole-output equality:

1. Ignore arbitrary bounded non-protocol log/progress lines.
2. Find each exact required command echo in order.
3. For every command except `exit`, require an exact `OK` after that echo and
   before the next required command echo.
4. For `exit`, require the exact echo followed later by `Bye bye`; do not
   require an `OK` for exit.
5. Any exact `KO` terminal response, missing/reordered/duplicated required
   echo, missing required `OK`, missing `Bye bye`, nonzero exit, timeout, or
   truncation fails closed.

Tests use captured, sanitized native 6.18 transcripts that retain representative
log4j/INFO/WARN/progress noise and the real exit tail. A helper that manufactures
`command/OK` for every script line is prohibited.

## 3. Frozen isolated CubeMX home

Control files live only below the attempt evidence/control root outside product
staging. The adapter seeds the exact Windows location:

`.stm32cubemx/plugins/updater/updater.ini`

The `[Path]` section contains canonical `SoftwarePath`, `RepositoryPath`, and
`UpdaterPath`. Other required fields are emitted from a closed Toolkit template
based on the observed 6.18 layout; no ambient updater file, proxy credential, or
user-home byte is copied. Dead loopback JVM proxies and the closed child
environment remain the network boundary.

Every exit path returns the control-root identity to orchestration. Success
removes it before native validation. Nonzero, timeout, protocol, validation,
configuration, build, and activation failures also remove it; only a bounded,
sanitized failure record under the Toolkit data root may remain. Control files
never enter ownership or the activated project.

## 4. Frozen CubeMX CMake dialects

The parser recognizes exactly two 6.18 dialects and rejects mixtures.

### Global/subdirectory dialect

- Top level contains one literal `set(CMAKE_PROJECT_NAME <token>)` and
  `project(${CMAKE_PROJECT_NAME})`.
- Top level contains the exact `add_subdirectory(cmake/stm32cubemx)`.
- `CMakePresets.json` is bounded JSON and contains one default
  `toolchainFile` rooted through `${sourceDir}`.
- The toolchain contains literal `TARGET_FLAGS` facts for CPU/FPU/ABI and one
  contained linker-script reference.
- `cmake/stm32cubemx/CMakeLists.txt` contains literal closed lists
  `MX_Defines_Syms`, `MX_Include_Dirs`, `MX_Application_Src`, and
  `STM32_Drivers_Src`.

### Context/include dialect

- Top level contains one literal project-name binding and the exact
  `include("mx-generated.cmake")` only.
- Top level contains literal MCU flags and linker-script facts.
- `mx-generated.cmake` contains the closed generated sources/includes/defines.

Supported path expressions are only literal relative paths,
`${sourceDir}/...`, `${CMAKE_SOURCE_DIR}/...`,
`${CMAKE_CURRENT_SOURCE_DIR}/...`, and `${CMAKE_CURRENT_LIST_DIR}/...`.
`..` is accepted only after canonical resolution proves the result stays below
staging. Each list item retains the directory in which it was declared; no
loop-variable base may be reused for another file's values.

The parser resolves `project(${CMAKE_PROJECT_NAME})` through the preceding
literal binding, reads the preset-selected toolchain, and requires exact
CPU/FPU/ABI/linker/source/include/define facts. It does not fall back to an MCU,
staging name, or all source files. Representative F4 and H7 fixtures preserve
the relevant installed-template scaffolding and vary only placeholder values.
The synthesized manifest must load, configure, and produce both Toolkit build
plans without guessing.

## 5. Frozen cross-process locking

Authorization consumption and destination activation use one verified
descriptor-lock primitive shaped after the repository's existing evidence and
diagnostic store locks:

- create a one-byte, single-link regular lock file atomically;
- open it with `os.open(O_RDWR|O_BINARY|O_NOFOLLOW)`;
- bind pre-open/opened/current identity and size;
- seek to byte zero, then use `msvcrt.locking(..., LK_LOCK, 1)` on Windows or
  `flock(LOCK_EX)` on POSIX;
- revalidate identity while held;
- always seek, unlock, and close in `finally`.

Do not use Python `open("a+b")` for the lock. Do not translate normal lock
contention into `CREATION_ACTIVATION_FAILED`. Independent processes must
serialize and both exit normally; only the losing authorization consumer gets
`CREATION_AUTHORIZATION_CONSUMED`.

Tests start two real independent Python processes, hold the first lock until a
release marker, prove the second has not entered, release the first, and require
the second to enter and exit zero. They run in the exact aggregate on Windows.

## 6. Recovery acceptance

The recovery candidate must pass focused protocol/updater/dialect/control-
cleanup/lock tests and the exact VS07-B slice with zero failures/errors/skips/
xfails in a clean Sol worktree. It must match the fresh native observations,
repeat the real missing-repository observation without CubeMX or destination
mutation, preserve F1/F3/F5/rollback corrections, update report/ledger, and
remain local/unpushed.

Positive native acceptance is still required before VS07-B can be `ACCEPTED`.
Until the offline package exists, the maximum verdict is
`IMPLEMENTATION_COMPLETE_ENVIRONMENT_BLOCKED`. VS07-C implementation remains
frozen.
