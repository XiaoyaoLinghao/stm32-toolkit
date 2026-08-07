# STM32TK-0305-BUILD-IDENTITY r002 Implementation Report — Revision 4

Status: `IMPLEMENTED`
Module: `STM32TK-0305-BUILD-IDENTITY` / r002 / revision-4
Branch: `openclaw/STM32TK-0305-BUILD-IDENTITY/r002`
Accepted base commit: `e47eee0d374bd3a959fe555990b66a6163eb18b8` (exactly matches the work order; working tree clean at start)
Reviewed predecessor: `4678d0c372b4ed0aff7fc717704dae18ee5fa19a` (the r002 revision-3 report commit)
Code head before this report commit: `d9ce49f56e5ed158424ab8ccd395ac6cbfff2f7b`
Final branch head: supplied only in the return message and PR metadata
Work order: `docs/openclaw/modules/STM32TK-0305-BUILD-IDENTITY.md` (specification commit `cc2e4947aa692f940655c9ddf18ee8ab1f68c824`, `READY_FOR_OPENCLAW`, accepted base matches)

## 1. Revision verdict and scope

Codex returned `REVISION_REQUIRED` for the reviewed predecessor `4678d0c3…` after running the
7-test regression target on Windows NT 10.0.26200.0 with CPython 3.12.13 and pytest 8.3.5:
**7 failed, exit 1**; the Windows `test_process.py` run (26 passed, no 60 s wait) and the
fake-CMake target (3 passed) were green. The failures are two classes:

1. **Six fake-Git failures** — `test_git_invalid_malformed_head`,
   `test_git_invalid_nonzero_exit`, `test_git_invalid_overflow`,
   `test_git_failure_publishes_failure_record`, `test_pre_configure_input_change_returns_input_changed`,
   `test_pre_configure_snapshot_raise_publishes_failure`. Root cause: fake CMake already used
   the narrow Popen seam, but the fake Git and the two dynamic Git scripts were still
   installed only as `git.cmd` on `PATH`. Windows `shell=False` execution of a bare `"git"`
   argv does not reliably select `git.cmd` (CreateProcess appends `.exe`), so the product
   invoked the ambient real Git.
2. **One path-separator failure** — `test_success_publication_writes_no_unrelated_files`.
   Root cause: `str(path.relative_to(root))` returns backslash paths on Windows while the
   expected inventory set uses forward slashes.

Fix in this round (confined to the single allowed test path
`tools/stm32-toolkit/tests/test_build_runner.py`):

- The fake-CMake-only `_CmakeOnlyPopenSeam` became a composable `_FakeToolPopenSeam` that maps
  exactly one bare executable name (`"cmake"` or `"git"`, never a path or extension) to
  `sys.executable` plus the real `fake_<name>.py` script, records the untouched product argv,
  and delegates every other invocation to the fallback Popen (the previously installed seam
  or the real `subprocess.Popen`), so the git and cmake seams compose in one build and
  unrelated invocations are never intercepted. `install_fake_git` and the new
  `install_fake_git_script` install the fake Git behind this seam with hit-file and
  original-argv recording; the PATH-only `git.cmd` mechanism (`install_script_binary`) was
  removed.
- The six failing tests now assert per-mode hit evidence: the seam-recorded original product
  argv (exactly `git rev-parse --verify HEAD` and
  `git status --porcelain=v1 -z --untracked-files=all`) plus the fake script's own hit
  records, proving the fake Git actually ran and never fell through to ambient Git. A new
  composition test (`test_fake_git_and_cmake_seams_compose`) installs both seams in one
  successful build and proves git→fake Git, cmake→fake CMake, and unrelated invocations→real
  `Popen`, and that `prepare_project`'s real `git init/add/commit` (which runs before any
  seam exists) is never intercepted.
- `test_success_publication_writes_no_unrelated_files` now builds both inventories with
  `path.relative_to(root).as_posix()` so the forward-slash expected set matches on every
  host; no `os.sep` concatenation, no platform branch, and no duplicate expected set was
  added, and the approved six-file bound is still asserted.

No product file, schema, template, dependency, or lockfile was modified; `test_process.py`
and `test_firmware_identity.py` were not touched. No skip/xfail was added anywhere; the 17
full-suite skips are the pre-existing accepted-base Windows-only skips, unchanged. No fixed
sleeps or 60 s natural-exit waits were introduced.

## 2. Changed-path inventory (revision diff `4678d0c3…` → code head `d9ce49f5…`)

| Status | Path | Purpose |
|---|---|---|
| M | `tools/stm32-toolkit/tests/test_build_runner.py` | composable narrow Popen seam for the fake Git double; hit-proven fake-Git installers; hit/orig evidence in the six formerly failing tests; portable `as_posix()` file inventory; new git+cmake composition test |
| M | `docs/openclaw/returns/STM32TK-0305-BUILD-IDENTITY/r002-implementation-report.md` | this report (report-only final commit) |

`git diff --check 4678d0c3…...HEAD` is silent and `git diff --name-status 4678d0c3…...HEAD`
lists exactly these two paths and nothing else. No commit was amended, rebased, cherry-picked,
or force-pushed; `master`, the specification commit, the r001 branch, and PR #5 were not
touched.

## 3. Environment-separated verification (this revision round)

OpenClaw environment: Linux x86_64 (`Linux 7.0.0-22-generic`); CPython 3.10.11
(`/home/openclaw/coding/venvs/tk0302`, outside the repository); jsonschema 4.23.0, mcp 1.27.0,
pyelftools 0.33, Jinja2 3.1.6, pytest 8.3.5, pytest-cov 6.0.0. All commands ran with
`PYTHONPATH` set to the checked-out branch tree (`tools/stm32-toolkit/src`) from the
repository root on branch `openclaw/STM32TK-0305-BUILD-IDENTITY/r002` at code head
`d9ce49f5…`; the report commit follows separately.

| Gate/command | Evidence owner | Environment | Commit tested | Exit | Observed result | Status |
|---|---:|---:|---:|---|
| 7-test regression target: `python -m pytest tools/stm32-toolkit/tests/test_build_runner.py -q -k "git_invalid_malformed_head or git_invalid_nonzero_exit or git_invalid_overflow or git_failure_publishes_failure_record or pre_configure_input_change_returns_input_changed or pre_configure_snapshot_raise_publishes_failure or success_publication_writes_no_unrelated_files"` | OpenClaw | Linux; CPython 3.10.11 | code head | 0 | 7 passed, 0 failed; every fake-Git mode carries hit evidence (fake script hit records + seam-recorded original argv) | PASS |
| `python -m pytest tools/stm32-toolkit/tests/test_process.py -q --durations=10` | OpenClaw | same | code head | 0 | 26 passed, 0 skipped, 0 failed; slowest 3.01 s (bounded polls, no 60 s wait); `pgrep -af "time.sleep(60)"` after the run finds no residual processes | PASS |
| fake-CMake target: `python -m pytest tools/stm32-toolkit/tests/test_build_runner.py -q -k "fake_cmake_launcher_reaches_the_python_double or run_build_success_debug_publishes_exact_evidence or launch_failure_returns_configure_failed"` | OpenClaw | same | code head | 0 | 3 passed (launcher probe, exact-evidence success, launch failure) | PASS |
| 5-file focused gate: `python -m pytest tools/stm32-toolkit/tests/test_process.py tools/stm32-toolkit/tests/test_build_runner.py tools/stm32-toolkit/tests/test_build_map.py tools/stm32-toolkit/tests/test_firmware_identity.py tools/stm32-toolkit/tests/test_context.py -q` (junitxml) | OpenClaw | same | code head | 0 | 251 passed, 0 skipped, 0 failed (junitxml: tests=251, errors=0, failures=0, skipped=0) | PASS |
| Full suite: `python -m pytest tools/stm32-toolkit/tests -q` (junitxml) | OpenClaw | same | code head | 0 | 1049 collected; 1032 passed, 17 skipped (pre-existing accepted-base Windows-only skips; no new skip/xfail), 0 failures/errors (junitxml: tests=1049, errors=0, failures=0, skipped=17) | PASS |
| Branch coverage: `python -m pytest tools/stm32-toolkit/tests -q --cov=stm32_toolkit --cov-branch --cov-report=term` (clean `.coverage`) | OpenClaw | same | code head | 0 | **93% TOTAL** (6097 stmts, 408 miss; 1998 branches, 160 miss); build.model 100%, build.map_file 97%, build.identity 95%, build.runner 93%, process 91%, build.__init__ 100% — every new build/process module ≥90% | PASS |
| Compile: `python -m compileall -q tools/stm32-toolkit/src tools/stm32-toolkit/tests` | OpenClaw | same | code head | 0 | silent | PASS |
| Revision diff hygiene/scope: `git diff --check 4678d0c3…...HEAD`, `git diff --name-status 4678d0c3…...HEAD` | OpenClaw | same | code head | 0 | silent; exactly the §2 inventory | PASS |
| Working tree: `git status --short` | OpenClaw | same | code head | 0 | empty before the report commit | PASS |
| Windows `test_process.py` and fake-CMake target on the reviewed predecessor | Codex | Windows NT 10.0.26200.0; CPython 3.12.13, pytest 8.3.5 | `4678d0c3` | 0 | 26 passed (no 60 s wait); fake-CMake 3 passed | PASS (Codex review evidence) |
| Windows 7-test regression target on the reviewed predecessor | Codex | same | `4678d0c3` | 1 | 6 fake-Git failures + 1 path-separator failure; exact classes recorded in §1 | FAIL (rejection evidence) |
| Windows focused/full on the returned head, real process-tree timeout (`taskkill /T`, `CREATE_NEW_PROCESS_GROUP`), `msvcrt.locking`, replace/fsync publication | Codex | Windows NT 10.0.26200.0; CPython 3.12.13 | returned head | — | the fake-Git seam is host-independent by construction (bare `"git"` argv mapped to `sys.executable` plus an on-disk script; no PATH `git.cmd` resolution), but the full Windows suite must be re-run by Codex on the returned head | `DEFERRED_TO_CODEX` |
| Real CMake 4.3.1 + Ninja 1.13.2 + ARM GNU 14.3.1/binutils 2.44 debug+release builds of the `minimal-gcc` fixture | Codex | Windows; CMake 4.3.1, Ninja 1.13.2, ARM GNU 14.3.1 | returned head | — | configure+build of both presets must exit 0 with valid MAP/ELF/identity; OpenClaw verifies the runner end-to-end with the hit-proven fake toolchain only | `DEFERRED_TO_CODEX` |
| Visual/hardware | N/A | N/A | — | — | `NOT_APPLICABLE` — no UI or hardware access | N/A |

Attribution rules are honored: every `PASS` row is an OpenClaw run with its own observed exit
and result; the Codex Windows predecessor runs (26 + 3 passed, and the 7-test failure
evidence with its exact classes) are recorded only as the review evidence they are, never as
an OpenClaw PASS; the two Codex gates on the returned head are recorded only as
`DEFERRED_TO_CODEX`.

## 4. Regression and residual risk

- Regression proof: the 7-test target is 7 passed on the code head with per-mode hit
  evidence; `test_process.py` is 26 passed / 0 skipped with no residual processes; the
  5-file gate is 251 passed / 0 skipped; the full suite is 1049 collected, 1032 passed,
  17 pre-existing skips, 0 failures/errors; branch coverage is 93% overall with every new
  build/process module ≥90%. The revision diff touches only the allowed test path and this
  report; the product, schemas, templates, lockfile, and dependency set are byte-identical
  to the reviewed predecessor. `test_process.py` and `test_firmware_identity.py` are
  untouched.
- Residual risks:
  1. Windows focused/full on the returned head (including the 7-test regression target),
     real process-tree timeout (`taskkill /T`, `CREATE_NEW_PROCESS_GROUP`),
     `msvcrt.locking`, and replace/fsync publication remain Codex's gate. The fake-Git seam
     is deterministic by construction (bare `"git"` argv mapped to `sys.executable` plus the
     on-disk `fake_git.py` script; no PATH `git.cmd` resolution, no ambient-Git fallback) but
     has not been executed on Windows here.
  2. Real CMake/Ninja/ARM GNU builds of `minimal-gcc` remain Codex's gate; OpenClaw
     exercises the runner end-to-end only with the hit-proven Python doubles.
- Follow-up recommendation: unchanged from the reviewed predecessor (later CLI/MCP modules
  may consume `stm32_toolkit.build.run_build`).

## 5. Author checklist

- [x] Accepted base and code head are full SHAs (`e47eee0d374bd3a959fe555990b66a6163eb18b8`,
      `d9ce49f56e5ed158424ab8ccd395ac6cbfff2f7b`); reviewed predecessor
      `4678d0c372b4ed0aff7fc717704dae18ee5fa19a` recorded.
- [x] Final head is returned out of band after this report commit (PR metadata + return
      message); this report contains no self-referential final SHA and no moving commit
      totals or volatile file counts.
- [x] Revision diff contains exactly the one allowed test file plus this report; no product
      code, schema, template, dependency, or lockfile changed; `test_process.py` and
      `test_firmware_identity.py` untouched; no skip/xfail added; no fixed sleeps or 60 s
      natural-exit waits introduced (slowest test 3.01 s, bounded polls only).
- [x] The revision-3 failure classes (six fake-Git failures from PATH-only `git.cmd` on
      Windows and one backslash-vs-forward-slash inventory failure) are recorded in §1 and
      §3 with the Codex-observed evidence; the predecessor residual-risk item about fake Git
      on Windows is resolved by the narrow seam, and no earlier "Windows focused/full
      closed-loop" claim is repeated — Windows and real-toolchain gates remain deferred.
- [x] Every required OpenClaw gate has direct observed evidence on the code head (7-test
      target 7 passed; `test_process.py` 26 passed / 0 skipped, slowest 3.01 s, no residual
      processes; fake-CMake 3 passed; 5-file 251 passed / 0 skipped; full 1049 collected /
      1032 passed / 17 pre-existing skips / 0 failures; branch coverage 93% with every new
      build/process module ≥90%; compileall; both diff checks; clean status).
- [x] Other-environment gates are accurately attributed or deferred (Codex Windows
      predecessor evidence recorded as review evidence only; Windows suite/process-tree/lock
      and real ARM toolchain builds `DEFERRED_TO_CODEX`; visual `NOT_APPLICABLE`).
- [x] No credentials, private data, caches, build output, or temp projects are committed
      (venv outside the repository; `.coverage`/`__pycache__`/`.pytest_cache` ignored).
- [x] Overall status `IMPLEMENTED`: complete suite exits 0 on CPython 3.10.11 (1032 passed,
      17 pre-existing skips), branch coverage 93% with every new build/process module ≥90%,
      Windows and real-toolchain gates `DEFERRED_TO_CODEX`.
