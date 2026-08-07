# STM32TK-0305-BUILD-IDENTITY r002 Implementation Report — Revision 3

Status: `IMPLEMENTED`
Module: `STM32TK-0305-BUILD-IDENTITY` / r002 / revision-3
Branch: `openclaw/STM32TK-0305-BUILD-IDENTITY/r002`
Accepted base commit: `e47eee0d374bd3a959fe555990b66a6163eb18b8` (exactly matches the work order; working tree clean at start)
Reviewed predecessor: `bc261c19a53e65758988be371755bb1c42f65469` (the r002 revision-2 report commit)
Code head before this report commit: `f775192d16ab78d378b76c6759868a90e5001081`
Final branch head: supplied only in the return message and PR metadata
Work order: `docs/openclaw/modules/STM32TK-0305-BUILD-IDENTITY.md` (specification commit `cc2e4947aa692f940655c9ddf18ee8ab1f68c824`, `READY_FOR_OPENCLAW`, accepted base matches)

## 1. Revision verdict and scope

Codex returned `REVISION_REQUIRED` for the reviewed predecessor `bc261c19…` after running
`python -m pytest tools/stm32-toolkit/tests/test_process.py -q --durations=10` on Windows NT
10.0.26200.0 with CPython 3.12.13 and pytest 8.3.5: **4 failed / 22 passed, exit 1**. All four
failures are one class: `assert interpreter_pid == root_pid` failed because the Popen root PID
and the script interpreter PID differ. Codex-observed evidence:

| Location | Failure |
|---|---|
| `test_process.py:411` | `assert interpreter_pid == root_pid (13932 != 20848)` |
| `test_process.py:495` | `assert interpreter_pid == root_pid (5872 != 25240)` |
| `test_process.py:518` | `assert interpreter_pid == root_pid (26264 != 16108)` |
| `test_process.py:612` | `assert interpreter_pid == root_pid (4888 != 9268)` |

Root cause: on Windows, `Scripts/python.exe` inside a virtual environment is a launcher
(redirector) that can spawn a distinct real interpreter child process, so `Popen.pid` — the
root process the product actually tracks — and the pid the child script writes via
`os.getpid()` are not guaranteed equal. Revision 2 read both PIDs as distinct quantities but
then re-asserted their equality, so the Popen-root / launcher / interpreter distinction the
revision asked for was not actually delivered; the claim that revision 2 "distinguished the
Popen root PID from the interpreter PID" was therefore inaccurate and is retracted here.

Fix in this round (confined to the single allowed test path `tools/stm32-toolkit/tests/test_process.py`):

- Deleted every remaining `assert interpreter_pid == root_pid`. No assertion forces the two
  PIDs equal or unequal; on direct-exec hosts they may coincide and behind a Windows venv
  launcher they may differ.
- `root_pid` still comes from the product-tracked `Popen` instance (the proxy records
  `Popen.pid`); `interpreter_pid` still comes from the pid file the child script writes; the
  PID-file evidence is kept in every test.
- The graceful, force-kill, taskkill, and `Popen.kill()` fallback seams are still asserted to
  receive the root PID (`assert terminated == [root_pid]`, `assert killed == [root_pid]`,
  `assert taskkilled == [root_pid]`, `assert root._kill_called is True`).
- Every test still proves reaping with `assert_process_reaped` on each PID independently
  (root, interpreter, and grandchild where present); when the two PIDs coincide the repeated
  check on the same PID is allowed and returns immediately. No test was weakened to
  seam-call-only assertions.
- Two fixtures additionally received host-adaptive kill bodies so the reaping proof also
  holds on Windows: the graceful→force test's force-kill seam and the taskkill-failure
  test's fake now terminate the whole child tree through the real `taskkill /T` on Windows
  (captured `subprocess.Popen`, never routed through the tests' proxy), because a
  root-only `Popen.kill()`/TerminateProcess cannot reach a launcher's interpreter child
  there. On POSIX those bodies keep the previous behavior (killpg / direct SIGKILL via the
  real fallback). The taskkill-failure fake still returns `False` so the fallback dispatch
  (`Popen.kill()` on the tracked root) is exercised on every host.

The fake-CMake launcher gates are unaffected (`test_build_runner.py` untouched): the
predecessor's `_CmakeOnlyPopenSeam` still maps only exact bare `"cmake"` argv to
`sys.executable` plus the real `fake_cmake.py`, records the untouched product argv, and the
launch-failure fixture still destroys the seam's real target. No product file, schema,
template, dependency, or lockfile was modified in this round; `test_firmware_identity.py`
was not touched. No skip/xfail was added anywhere; the 17 full-suite skips are the
pre-existing accepted-base Windows-only skips, unchanged.

## 2. Changed-path inventory (revision diff `bc261c19…` → code head `f775192d…`)

| Status | Path | Purpose |
|---|---|---|
| M | `tools/stm32-toolkit/tests/test_process.py` | remove the Popen-root == interpreter equality assumption; independent reaping of root/interpreter/grandchild; host-adaptive whole-tree force-kill for the graceful→force and taskkill-fallback fixtures; shared `_real_taskkill_tree` helper; corrected module docstring |
| M | `docs/openclaw/returns/STM32TK-0305-BUILD-IDENTITY/r002-implementation-report.md` | this report (report-only final commit) |

`git diff --check bc261c19…...HEAD` is silent and `git diff --name-status bc261c19…...HEAD`
lists exactly these two paths and nothing else. No commit was amended, rebased, cherry-picked,
or force-pushed; `master`, the specification commit, the r001 branch, and PR #5 were not
touched.

## 3. Environment-separated verification (this revision round)

OpenClaw environment: Linux x86_64 (`Linux 7.0.0-22-generic`); CPython 3.10.11
(`/home/openclaw/coding/venvs/tk0302`, outside the repository); jsonschema 4.23.0, mcp 1.27.0,
pyelftools 0.33, Jinja2 3.1.6, pytest 8.3.5, pytest-cov 6.0.0. All commands ran with
`PYTHONPATH` set to the checked-out branch tree (`tools/stm32-toolkit/src`) from the
repository root on branch `openclaw/STM32TK-0305-BUILD-IDENTITY/r002` at code head
`f775192d…`; the report commit follows separately. The pytest summary line is not printed in
this environment (dumb terminal, doubled `-q`), so exact counts were taken from junitxml
output, as in revision 2.

| Gate/command | Owner | Environment | Commit tested | Exit | Observed result | Status |
|---|---:|---:|---:|---|
| Static removal check: no `assert interpreter_pid == root_pid` / `!=` remains in `test_process.py` | OpenClaw | Linux; CPython 3.10.11 | code head | 0 | grep finds no equality or inequality assertion between the two PIDs | PASS |
| `python -m pytest tools/stm32-toolkit/tests/test_process.py -q --durations=10` (junitxml) | OpenClaw | Linux; CPython 3.10.11 | `f775192d` | 0 | 26 passed, 0 skipped, 0 failed; slowest test 3.01 s (bounded polls; no 60 s natural-exit wait); `pgrep -af "time.sleep(60)"` after the run finds no residual test processes | PASS |
| `python -m pytest tools/stm32-toolkit/tests/test_build_runner.py -q -k "fake_cmake_launcher_reaches_the_python_double or run_build_success_debug_publishes_exact_evidence or launch_failure_returns_configure_failed"` | OpenClaw | same | `f775192d` | 0 | 3 passed (launcher probe, exact-evidence success, launch failure) | PASS |
| Focused gate: `python -m pytest tools/stm32-toolkit/tests/test_process.py tools/stm32-toolkit/tests/test_build_runner.py tools/stm32-toolkit/tests/test_build_map.py tools/stm32-toolkit/tests/test_firmware_identity.py tools/stm32-toolkit/tests/test_context.py -q` (junitxml) | OpenClaw | same | `f775192d` | 0 | 250 passed; 0 skipped, 0 failed (junitxml: tests=250, errors=0, failures=0, skipped=0) | PASS |
| Full suite: `python -m pytest tools/stm32-toolkit/tests -q` (junitxml) | OpenClaw | same | `f775192d` | 0 | 1048 collected; 1031 passed, 17 skipped (pre-existing accepted-base Windows-only skips; no new skip/xfail), 0 failures/errors (junitxml: tests=1048, errors=0, failures=0, skipped=17) | PASS |
| Branch coverage: `python -m pytest tools/stm32-toolkit/tests -q --cov=stm32_toolkit --cov-branch --cov-report=term` (clean `.coverage`) | OpenClaw | same | `f775192d` | 0 | **93% TOTAL** (6097 stmts, 408 miss; 1998 branches, 160 miss); build.model 100%, build.map_file 97%, build.identity 95%, build.runner 93%, process 91%, build.__init__ 100% — every new build/process module ≥90% | PASS |
| Compile: `python -m compileall -q tools/stm32-toolkit/src tools/stm32-toolkit/tests` | OpenClaw | same | `f775192d` | 0 | silent | PASS |
| Revision diff hygiene: `git diff --check bc261c19…...HEAD` | OpenClaw | same | `f775192d` | 0 | silent | PASS |
| Revision diff scope: `git diff --name-status bc261c19…...HEAD` | OpenClaw | same | `f775192d` | 0 | exactly the §2 revision inventory (one test file + this report) | PASS |
| Working tree: `git status --short` | OpenClaw | same | `f775192d` | 0 | empty before the report commit | PASS |
| Windows focused/full, real process-tree timeout (`taskkill /T`, `CREATE_NEW_PROCESS_GROUP`), `msvcrt.locking`, replace/fsync publication | Codex | Windows NT 10.0.26200.0; CPython 3.12.13 | returned head | — | the revised fixtures no longer assume launcher == interpreter and keep proving independent reaping; the full Windows suite must be re-run by Codex on the returned head | `DEFERRED_TO_CODEX` |
| Real CMake 4.3.1 + Ninja 1.13.2 + ARM GNU 14.3.1/binutils 2.44 debug+release builds of the `minimal-gcc` fixture | Codex | Windows; CMake 4.3.1, Ninja 1.13.2, ARM GNU 14.3.1 | returned head | — | configure+build of both presets must exit 0 with valid MAP/ELF/identity; OpenClaw verifies the runner end-to-end with the hit-proven fake toolchain only | `DEFERRED_TO_CODEX` |
| Visual/hardware | N/A | N/A | — | — | `NOT_APPLICABLE` — no UI or hardware access | N/A |

Attribution rules are honored: every `PASS` row is an OpenClaw run with its own observed exit
and result; the Codex Windows run of the predecessor (4 failed / 22 passed, exit 1, the exact
PID evidence above) is recorded only as the rejection evidence it is, never as an OpenClaw
PASS; the two Codex gates are recorded only as `DEFERRED_TO_CODEX`.

## 4. Regression and residual risk

- Regression proof: `test_process.py` is 26 passed / 0 skipped on the code head with no
  residual processes; the five-file gate is 250 passed / 0 skipped; the full suite is 1048
  collected, 1031 passed, 17 pre-existing skips, 0 failures/errors; branch coverage is 93%
  overall with every new build/process module ≥90% (process 91%, runner 93%, identity 95%,
  map_file 97%, model 100%). The revision diff touches only the allowed test path and this
  report; the product, schemas, templates, lockfile, and dependency set are byte-identical
  to the reviewed predecessor. `test_firmware_identity.py` is untouched.
- Residual risks:
  1. Real Windows process-group creation/termination (`taskkill /T`), `msvcrt.locking`, and
     the full Windows suite remain Codex's gate. The revised fixtures are deterministic by
     construction (no launcher==interpreter assumption, host-adaptive whole-tree kill bodies
     for the force-kill and fallback fixtures) but have not been executed on Windows here.
  2. Real CMake/Ninja/ARM GNU builds of `minimal-gcc` remain Codex's gate; OpenClaw
     exercises the runner end-to-end only with the hit-proven Python double.
  3. Git-evidence tests install a fake `git` via PATH; on Windows a bare `"git"` resolves to
     the ambient real `git.exe` (CreateProcess appends `.exe`), the same pre-existing
     limitation as the old cmake PATH launcher. Per the work order the launch seam must not
     intercept Git, so the fake-git Windows behavior is unchanged and falls under the
     deferred Windows full gate.
- Follow-up recommendation: unchanged from the reviewed predecessor (later CLI/MCP modules
  may consume `stm32_toolkit.build.run_build`).

## 5. Author checklist

- [x] Accepted base and code head are full SHAs (`e47eee0d374bd3a959fe555990b66a6163eb18b8`,
      `f775192d16ab78d378b76c6759868a90e5001081`); reviewed predecessor
      `bc261c19a53e65758988be371755bb1c42f65469` recorded.
- [x] Final head is returned out of band after this report commit (PR metadata + return
      message); this report contains no self-referential final SHA and no moving commit
      totals or volatile file counts.
- [x] Revision diff contains exactly the one allowed test file plus this report; no product
      code, schema, template, dependency, or lockfile changed; `test_firmware_identity.py`
      untouched; no skip/xfail added; no fixed sleeps or 60 s natural-exit waits introduced
      (slowest test 3.01 s, bounded polls only).
- [x] The revision-2 failure class (four Windows `interpreter_pid == root_pid` assertions at
      lines 411/495/518/612 with the Codex-observed PID pairs) is recorded above, and the
      revision-2 claim that PIDs were "distinguished" while equality was still asserted is
      retracted.
- [x] Every required OpenClaw gate has direct observed evidence on the code head
      (`test_process.py` 26 passed / 0 skipped, slowest 3.01 s, no residual processes;
      fake-CMake 3 passed; five-file 250 passed / 0 skipped; full 1048 collected /
      1031 passed / 17 pre-existing skips / 0 failures; branch coverage 93% with every new
      build/process module ≥90%; compileall; both diff checks; clean status).
- [x] Other-environment gates are accurately attributed or deferred (Windows
      suite/process-tree/lock and real ARM toolchain builds `DEFERRED_TO_CODEX`; visual
      `NOT_APPLICABLE`); the Codex predecessor run is recorded as rejection evidence only,
      never as an OpenClaw PASS.
- [x] No credentials, private data, caches, build output, or temp projects are committed
      (venv outside the repository; `.coverage`/`__pycache__`/`.pytest_cache` ignored).
- [x] Overall status `IMPLEMENTED`: complete suite exits 0 on CPython 3.10.11 (1031 passed,
      17 pre-existing skips), branch coverage 93% with every new build/process module ≥90%,
      Windows and real-toolchain gates `DEFERRED_TO_CODEX`.
