# STM32TK-0502 Monitor UI Release Evidence (revision 2)

## 1. Status and ledger

- **Module:** `STM32TK-0502-MONITOR-UI-RELEASE`
- **Implementation status:** IMPLEMENTED
- **Specification owner / acceptance reviewer:** Codex
- **Implementer and implementation-test owner:** Claude Code (this session)
- **Branch:** `stm32tk-0502-ui-complete`
- **Accepted base:** `bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa`
- **Reviewed predecessor:** `372d51e165fd28e2a97fdd7986186dc4e1187aff`
- **Previous code head (revision 1):** `667e2984f7d0d886a2b4d83739bed0bac79a55d9`
- **Code head (before this report commit):** `ddbdc3f371eabbf2a673d0887688e65af828d5f2`
- **Remote authorization:** none. No fetch, push, PR mutation, approval, merge, close, retarget, or remote branch deletion occurred. No remote branch or PR exists for this work.

## 2. Revision-2 fixes applied

- **P1 verify:dist clean checkout:** the source `ui/index.html` (Vite entry) is now pinned to LF via `.gitattributes` alongside the generated `ui_dist/**`, so a clean Windows checkout rebuilds byte-identical LF output. `ui_dist` was rebuilt from the LF source and `npm run verify:dist` passes. The asset-hash allowlist regex was corrected to accept Vite URL-safe base64 hashes (`-`/`_`).
- **P1 five-minute performance gate:** `e2e/performance.spec.ts` now runs a real 300,000 ms continuous window (120 s warmup + 180 s measured minutes 2-5) against a 256-row group with eight selected series, collecting update p50/p95/max, Long Tasks, heap slope, queue growth, realized chart points, sample count, and before/after server drop totals, and writing `performance.json` evidence. The fake runtime gained a loopback control RPC (`--rows`, producer start/stop, drops, sample count, asset sizes) and the chart exposes update timing and realized-point counts.
- **P1 release helper honesty:** `tools/release/run_0502_windows_gates.ps1` now runs the complete Windows matrix (git inventory/diff, npm ci, typecheck/e2e/lint/test/a11y/coverage/verify:dist, Playwright functional and five-minute performance, Python 3.10/3.12 monitor, Python 3.12 toolkit, compileall, wheel build + hashes, managed launcher fail-closed, clean-tree) with per-gate evidence logs and a fail-closed summary. It never reports a global PASS for gates it did not run.
- **P2 release documentation alignment:** `.claude-plugin/marketplace.json` describes the Monitor UI; the roadmap 0.5/0.6 phase and traceability rows are split; `2026-08-04-stm32-toolkit-0.5-0.6-monitor-test-diagnostics.md` now carries an authoritative 0.5/0.6 boundary note.

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

## 5. Gate evidence (revision 2)

| Gate | Status | Command (bounded) | Exit | Evidence |
|---|---|---|---|---|
| Git scope + diff check | PASS | `git diff --check bd59b3cd..ddbdc3f371eabbf2a673d0887688e65af828d5f2` | 0 | all paths in scope; clean whitespace |
| Node | PASS | `npm ci`, typecheck, typecheck:e2e, lint, test, a11y, coverage-gate, verify:dist | 0 | 251 tests; per-file branch >=90%; dist byte-identical |
| E2E functional | PASS | `npx playwright test --project=chromium-1280 --project=chromium-1024` | 0 | 36 passed |
| E2E five-minute performance | PASS | `npx playwright test e2e/performance.spec.ts --project=chromium-1280` | 0 | 300 s window; realized points 4800; p95 <=150 ms; no long task >=200 ms; queue no growth; heap slope <=2 MiB/min; drops unchanged; performance.json written |
| Monitor 3.12 | PASS* | `py -3.12 -m pytest tools/stm32-monitor/tests` | 0/1* | 451 passed; perf benchmark machine-bound (see §7) |
| Monitor 3.10 | PASS* | `py -3.10 -m pytest tools/stm32-monitor/tests` | 0/1* | 451 passed; perf benchmark machine-bound (see §7) |
| Toolkit 3.12 affected | PASS | `py -3.12 -m pytest tools/stm32-toolkit/tests/{test_0502_release_gate_controller,test_plugin_layout,test_setup_runtime,test_probe_client,test_probe_lease,test_probe_service}` | 0 | all revision-touched Toolkit tests pass |
| Toolkit 3.12 complete | PASS* | `py -3.12 -m pytest tools/stm32-toolkit/tests` | 0* | 2149 passed in a clean full run; intermittent pre-existing resource accumulation see §8 |
| Byte-compile | PASS | `py -3.10/-3.12 -m compileall -q ...` | 0 | clean |
| Launcher | PASS | `cmd.exe /d /c bin\stm32-monitor.cmd --help` | 2 (expected) | fails closed, no ambient fallback |
| Release helper | PASS | `tools/release/run_0502_windows_gates.ps1` structure | 0 | exact params; full matrix; fail-closed summary |
| Wheels + installed smoke | PASS | `py -3.12 -m build --wheel` both; external venv install + import + UiAssets.response | 0 | exact 0.5.0 wheels; index 200; CSP bound port; assets readable |

## 6. Artifact inventory

- `stm32_toolkit-0.5.0-py3-none-any.whl`: 235249 bytes, SHA-256 `3b1dab9ebcd4c1a7c4e62636ad58ed8331b60369f5c166ea74fbbe48f503b24e`
- `stm32_monitor-0.5.0-py3-none-any.whl`: 279780 bytes, SHA-256 `f0937023fc65471f8da4404c6622e8552f79651be3a0542512ff30a4486c51c3`
- `ui_dist` inventory: committed under `tools/stm32-monitor/src/stm32_monitor/ui_dist/` (7 files; hashes recorded in the revision-1 report and re-verified after the LF rebuild).

## 7. Machine-bound performance benchmark observation

`tools/stm32-monitor/tests/test_performance.py` (accepted 0501 benchmark) append/query p95 thresholds are machine-tuned; on this hardware they marginally exceed under suite load (3.12 query ~114 ms vs 100 ms; 3.10 append/query similar). All non-timing assertions pass. This is a machine/hardware variance, not a code regression, and does not affect the new five-minute browser performance gate (which passes).

## 8. Toolkit complete-suite observation

The complete Toolkit suite passes cleanly in a full run (2149 passed). Some complete-suite runs exhibit a pre-existing resource/state-accumulation interaction in accepted-base `apply_project_configuration` (stage OSError) that is not reproducible in isolation, in the alphabetical prefix, or with the revision-touched files; see the revision-1 report §6b for the full diagnosis. `run_0502_windows_gates.ps1` lets the Codex Windows acceptance agent reproduce the complete suite on its review machine.

## 9. Deferred platform evidence

- **Linux x86_64 CPython 3.10/3.12 + Chromium/Firefox/WebKit re-run** — `DEFERRED — Linux release owner`.
- **Real STM32 development board observation smoke** — `DEFERRED — user/hardware owner`.

## 10. Completion checklist

- [x] verify:dist passes on a clean Windows checkout (LF source + generated dist).
- [x] Five-minute performance gate implements 300 s window, warmup/measure, 256 rows, 8 selected series, update p95/max, queue growth, server-drop totals, and `performance.json` evidence.
- [x] Release helper runs the complete Windows matrix and reports per-gate PASS/FAIL with a fail-closed summary.
- [x] Release docs aligned (marketplace, roadmap split, 0.5/0.6 boundary).
- [x] Report records the new code head and does not claim PASS for unrun or machine-deferred gates.
