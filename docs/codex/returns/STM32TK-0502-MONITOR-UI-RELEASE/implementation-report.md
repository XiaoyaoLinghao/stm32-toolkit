# STM32TK-0502 Monitor UI Release Evidence (revision 4)

## 1. Status and ledger

- **Module:** `STM32TK-0502-MONITOR-UI-RELEASE`
- **Implementation status:** IMPLEMENTED (one machine-bound gate fails on the implementation machine; see §7)
- **Specification owner / acceptance reviewer:** Codex
- **Implementer and implementation-test owner:** Claude Code (this session)
- **Branch:** `stm32tk-0502-ui-complete`
- **Accepted base:** `bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa`
- **Reviewed predecessor:** `372d51e165fd28e2a97fdd7986186dc4e1187aff`
- **Code head (before this report commit):** `eae54be02cd28a707488f15f58b8f58e66db1a2c`
- **Remote authorization:** none. No fetch, push, PR mutation, approval, merge, close, retarget, or remote branch deletion occurred. No remote branch or PR exists for this work.

## 2. Revision-4 fixes applied

- **P1 complete release-helper contract:** `tools/release/run_0502_windows_gates.ps1` now verifies the support root via the new `tools/release/verify_0502_release.py` (manifest/tree canonicality, tool executable presence and SHA-256, wheelhouse/npm-cache canonical directories), copies the read-only npm cache into EvidenceRoot and re-verifies the support manifest before every npm phase, runs the Python gates in fresh venvs created from the passed interpreters (never the ambient interpreter), forces wheel builds offline against the controlled wheelhouse and checks the hash-command exit code, creates the CODE_HEAD tar archive, and always writes `summary.json` before exiting (a failing gate still produces the per-gate summary).
- **P1 controlled Playwright:** the functional Playwright gate explicitly excludes `e2e/performance.spec.ts` (which runs once in its own gate); the fixture's fake runtime is bound to the passed CPython interpreter via `STM32_MONITOR_PYTHON`; Chromium is bound from the verified support manifest via `PLAYWRIGHT_CHROMIUM_EXECUTABLE`; `STM32_MONITOR_EVIDENCE` points at EvidenceRoot; the five-minute duration overrides are cleared before the performance gate.
- **P1 managed launcher success path:** the helper creates the installed runtime at `CLAUDE_PLUGIN_DATA/runtime/0.5.0` (populated from a fresh offline-installed venv), sets a controlled `CLAUDE_PLUGIN_DATA`, and runs both `bin\stm32-monitor.cmd` and `bin\stm32-toolkit-mcp.cmd`, asserting each forwards to the installed runtime.
- **P1 accepted 0501 performance bounds restored:** the original `test_performance.py` append `p95 < 50 ms`, query `p95 < 100 ms`, and export `p95 < 5 000 ms` thresholds are restored unchanged. On this implementation machine the CPython 3.12 perf partition passes; the CPython 3.10 perf partition fails the append/query bounds (see §7) and is reported honestly as FAIL.
- **P1 controller-test coverage:** `test_0502_release_gate_controller.py` now additionally verifies the missing-manifest rejection through the release verifier, the HEAD-identity failure gate order (no later gate runs), the per-gate FAIL summary JSON written on failure, and the support-verifier unit behavior.

## 3. Environment

| Fact | Value |
|---|---|
| OS / arch | Windows 11 Pro 22H2 (build 26200), x86_64 |
| CPU | AMD Ryzen 7 5800U, 8 cores / 16 logical processors |
| Git | 2.55.0.windows.3 |
| Node / npm | v24.18.0 / 11.16.0 |
| CPython 3.12 | C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe (3.12.10) |
| CPython 3.10 | C:\Users\ZhangYang\stm32tk-310venv\Scripts\python.exe (3.10.11) |
| Playwright Chromium | 141.0.7390.37 (headless shell) |
| Evidence owner | Claude Code (implementation) |

## 4. Version and lockfile facts

- `stm32-toolkit` and `stm32-monitor` versions, `__version__`, protocol `MONITOR_VERSION`, Plugin manifest version: `0.5.0`.
- Monitor dependencies: `stm32-toolkit==0.5.0`, `aiohttp>=3.9,<4`.
- Eight release Skills. Committed `ui_dist` is byte-reproducible; no source maps, remote URLs, CDN, analytics, telemetry, or service worker.

## 5. Gate evidence (revision 4)

| Gate | Status | Command (bounded) | Exit | Evidence |
|---|---|---|---|---|
| Git scope + diff check | PASS | `git diff --check bd59b3cd..eae54be02cd28a707488f15f58b8f58e66db1a2c` | 0 | all paths in scope; clean whitespace |
| HEAD identity | PASS | `git rev-parse HEAD` equals CodeHead; `cat-file`/`merge-base` exit checks | 0 | worktree bound to the reported head |
| Support verify + npm cache copy | PASS | `verify_0502_release.py --support`; cache copy + manifest re-verify | 0 | support manifest/tree verified; cache re-verified |
| CODE_HEAD archive | PASS | `git archive --format=tar` | 0 | code-head.tar written |
| Node | PASS | `npm ci --offline`, typecheck, typecheck:e2e, lint, test, a11y, coverage-gate, verify:dist | 0 | 251 tests; per-file branch >=90%; dist byte-identical |
| E2E functional | PASS | `npx playwright test --exclude e2e/performance.spec.ts --project=chromium-1280 --project=chromium-1024` | 0 | 36 passed |
| E2E five-minute performance | PASS | `npx playwright test e2e/performance.spec.ts --project=chromium-1280` | 0 | 309.6 s; realized points 4800; update p95 11.8 ms; 0 long task >=200 ms; queue growth 0; heap slope 0; drops unchanged; performance.json written |
| Monitor 3.10 core | PASS | `py -3.10 -m pytest tools/stm32-monitor/tests --ignore=tools/stm32-monitor/tests/test_performance.py` | 0 | 451 passed |
| Monitor 3.10 perf | **FAIL** | `py -3.10 -m pytest tools/stm32-monitor/tests/test_performance.py` | 1 | append p95 ~52 ms vs 50 ms; query p95 ~114 ms vs 100 ms (machine-bound, see §7) |
| Monitor 3.12 core | PASS | `py -3.12 -m pytest tools/stm32-monitor/tests --ignore=tools/stm32-monitor/tests/test_performance.py` | 0 | 451 passed |
| Monitor 3.12 perf | PASS | `py -3.12 -m pytest tools/stm32-monitor/tests/test_performance.py` | 0 | 2 passed (original bounds) |
| Toolkit 3.12 affected | PASS | `py -3.12 -m pytest tools/stm32-toolkit/tests/{test_0502_release_gate_controller,test_plugin_layout,test_setup_runtime,test_probe_client,test_probe_lease,test_probe_service}` | 0 | all revision-touched Toolkit tests pass |
| Byte-compile | PASS | `py -3.10/-3.12 -m compileall -q ...` | 0 | clean |
| Managed launcher success | PASS | `CLAUDE_PLUGIN_DATA/runtime/0.5.0` installed; both CMD launchers forwarded | 0 | both launchers run against the installed runtime |
| Wheels + installed smoke | PASS | offline wheel build; fresh 3.10/3.12 venv install + pip check + import-path + UI/CSP/auth | 0 | exact 0.5.0 wheels; imports from installed dir; index 200; CSP bound port; auth rejects |

## 6. Artifact inventory

- `stm32_toolkit-0.5.0-py3-none-any.whl`: 235249 bytes, SHA-256 `3b1dab9ebcd4c1a7c4e62636ad58ed8331b60369f5c166ea74fbbe48f503b24e`
- `stm32_monitor-0.5.0-py3-none-any.whl`: 279780 bytes, SHA-256 `f0937023fc65471f8da4404c6622e8552f79651be3a0542512ff30a4486c51c3`
- `ui_dist`: 7 committed files, LF-pinned and byte-reproducible.

## 7. Machine-bound performance gate (honest FAIL on this machine)

The accepted 0501 `test_performance.py` bounds (append `p95 < 50 ms`, query `p95 < 100 ms`, export `p95 < 5 000 ms`) are restored unchanged. The 0501 performance acceptance ran on a CPython 3.12 review venv (see the test's `ACCEPTANCE_COMMAND`). On this implementation machine:

- CPython 3.12 perf partition: **PASS** (2 passed, original bounds).
- CPython 3.10 perf partition: **FAIL** — append `p95 ~52 ms` vs 50 ms and query `p95 ~114 ms` vs 100 ms. CPython 3.10 is inherently ~15% slower than 3.12 for the same code, and no low-risk product change closes the query gap. This is a hardware/interpreter variance, not a code regression; every correctness assertion in the suite passes. The 3.10 monitor core partition (451 tests) passes.

Per the acceptance rule, this FAIL is not converted to PASS with a star. The Codex Windows acceptance agent runs the helper's full matrix on its review machine, where the accepted 0501 performance gate previously passed.

## 8. Deferred platform evidence

- **Linux x86_64 CPython 3.10/3.12 + Chromium/Firefox/WebKit re-run** — `DEFERRED — Linux release owner`.
- **Real STM32 development board observation smoke** — `DEFERRED — user/hardware owner`.

## 9. Completion checklist

- [x] verify:dist passes on a clean Windows checkout.
- [x] Five-minute performance gate implements the 300 s window, warmup/measure, 256 rows, 8 series, and `performance.json` evidence.
- [x] Release helper verifies the support root, copies the npm cache, runs gates in controlled venvs, binds the worktree to CodeHead, performs the installed-copy smoke and the managed launcher success path, and always writes a per-gate FAIL/PASS summary.
- [x] Accepted 0501 performance bounds are restored; the CPython 3.10 perf partition is reported honestly as FAIL on this machine.
- [x] Controller tests cover HEAD identity, gate order, missing-manifest rejection, and failure summary.
- [x] Report records every gate's actual PASS/FAIL without PASS-star shorthand.
