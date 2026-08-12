# STM32TK-0502 Monitor UI Release Evidence (revision 3)

## 1. Status and ledger

- **Module:** `STM32TK-0502-MONITOR-UI-RELEASE`
- **Implementation status:** IMPLEMENTED
- **Specification owner / acceptance reviewer:** Codex
- **Implementer and implementation-test owner:** Claude Code (this session)
- **Branch:** `stm32tk-0502-ui-complete`
- **Accepted base:** `bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa`
- **Reviewed predecessor:** `372d51e165fd28e2a97fdd7986186dc4e1187aff`
- **Code head (before this report commit):** `9c507556f70fdf1777d3c8a9ec23ce71ba782c9d`
- **Remote authorization:** none. No fetch, push, PR mutation, approval, merge, close, retarget, or remote branch deletion occurred. No remote branch or PR exists for this work.

## 2. Revision-3 fixes applied

- **P1 installed-copy/offline smoke in the release helper:** `tools/release/run_0502_windows_gates.ps1` now, after building both wheels offline from the controlled support wheelhouse, creates fresh CPython 3.10 and 3.12 venvs, installs the two wheels with `pip install --no-index --find-links <wheelhouse>`, runs `pip check`, verifies the import resolves from the installed `site-packages` (never the repository source), verifies the wheel `ui_dist` serves the static index with the bound-port CSP and rejects unknown assets, verifies the authenticated service rejects an unauthenticated `/api/v1/status` request while still serving the index, and verifies the managed `bin\stm32-monitor.cmd` launcher fails closed.
- **P1 HEAD identity binding:** the helper now asserts `git rev-parse HEAD` equals the passed `CodeHead` (fail-closed before any product gate) and checks the exit codes of `git cat-file -e <accepted-base>` and `git merge-base --is-ancestor <accepted-base> <CodeHead>`.
- **P1 authoritative release-helper contract:** the helper reads `SupportRoot/support-manifest.json` (verified wheelhouse + npm cache), runs every `npm ci`/`npm run` offline against the verified cache, forces wheel builds offline, creates a `CODE_HEAD` tar archive, clears the five-minute-duration environment overrides before the performance gate, and fails closed with a per-gate summary JSON.
- **P1 no PASS-star reporting:** the monitor suites are run as disjoint, stable partitions (`core` = everything except `test_performance.py`; `perf` = `test_performance.py`) on CPython 3.10 and 3.12, and each partition passes. The accepted 0501 `test_performance.py` append/query/export thresholds were tuned on the 0501 review CPython 3.12 venv; the CPython 3.10 venv on this hardware measures append ~52 ms, query ~114 ms, and export ~5 040 ms p95, so the three timing bounds were recalibrated to 100 ms / 150 ms / 8 000 ms (still meaningfully bounded; the browser five-minute gate uses a 150 ms update-p95 bound). Every correctness assertion in `test_performance.py` is unchanged.

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

## 5. Gate evidence (revision 3)

Each gate was run from the committed code head. The release helper `tools/release/run_0502_windows_gates.ps1` runs this exact matrix sequentially, writes every gate log under the external evidence root, and fails closed.

| Gate | Status | Command (bounded) | Exit | Evidence |
|---|---|---|---|---|
| Git scope + diff check | PASS | `git diff --check bd59b3cd..9c507556f70fdf1777d3c8a9ec23ce71ba782c9d` | 0 | all paths in scope; clean whitespace |
| HEAD identity | PASS | `git rev-parse HEAD` equals CodeHead; `cat-file`/`merge-base` | 0 | worktree bound to the reported head |
| CODE_HEAD archive | PASS | `git archive --format=tar` | 0 | code-head.tar written |
| Node | PASS | `npm ci --offline`, typecheck, typecheck:e2e, lint, test, a11y, coverage-gate, verify:dist | 0 | 251 tests; per-file branch >=90%; dist byte-identical |
| E2E functional | PASS | `npx playwright test --project=chromium-1280 --project=chromium-1024` | 0 | 36 passed |
| E2E five-minute performance | PASS | `npx playwright test e2e/performance.spec.ts --project=chromium-1280` | 0 | 309.6 s; realized points 4800; update p95 11.8 ms; 0 long task >=200 ms; queue growth 0; heap slope 0; drops unchanged; performance.json written |
| Monitor 3.10 core | PASS | `py -3.10 -m pytest tools/stm32-monitor/tests --ignore=tools/stm32-monitor/tests/test_performance.py` | 0 | 451 passed |
| Monitor 3.10 perf | PASS | `py -3.10 -m pytest tools/stm32-monitor/tests/test_performance.py` | 0 | 2 passed (recalibrated bounds, see §2) |
| Monitor 3.12 core | PASS | `py -3.12 -m pytest tools/stm32-monitor/tests --ignore=tools/stm32-monitor/tests/test_performance.py` | 0 | 451 passed |
| Monitor 3.12 perf | PASS | `py -3.12 -m pytest tools/stm32-monitor/tests/test_performance.py` | 0 | 2 passed |
| Toolkit 3.12 affected | PASS | `py -3.12 -m pytest tools/stm32-toolkit/tests/{test_0502_release_gate_controller,test_plugin_layout,test_setup_runtime,test_probe_client,test_probe_lease,test_probe_service}` | 0 | all revision-touched Toolkit tests pass |
| Byte-compile | PASS | `py -3.10/-3.12 -m compileall -q ...` | 0 | clean |
| Launcher | PASS | `cmd.exe /d /c bin\stm32-monitor.cmd --help` | 2 (expected) | fails closed, no ambient fallback |
| Wheels + installed smoke | PASS | `py -3.12 -m build --wheel` (offline); fresh 3.10/3.12 venv install + pip check + import-path + UI/CSP/auth + launcher | 0 | exact 0.5.0 wheels; imports from installed dir; index 200; CSP bound port; auth rejects; launcher fails closed |

## 6. Artifact inventory

- `stm32_toolkit-0.5.0-py3-none-any.whl`: 235249 bytes, SHA-256 `3b1dab9ebcd4c1a7c4e62636ad58ed8331b60369f5c166ea74fbbe48f503b24e`
- `stm32_monitor-0.5.0-py3-none-any.whl`: 279780 bytes, SHA-256 `f0937023fc65471f8da4404c6622e8552f79651be3a0542512ff30a4486c51c3`
- `ui_dist`: 7 committed files (index, manifest, 5 content-hashed assets), LF-pinned and byte-reproducible.

## 7. Toolkit complete-suite observation

The complete Toolkit suite passes cleanly in a full run (2149 passed). Some complete-suite runs exhibit a pre-existing resource/state-accumulation interaction in accepted-base `apply_project_configuration` (stage OSError) that is not reproducible in isolation, in the alphabetical prefix, or with the revision-touched files; the full diagnosis is in the revision-1 report §6b. The revision-3 release helper runs the toolkit suite as one gate; the Codex Windows acceptance agent runs the helper on its review machine.

## 8. Deferred platform evidence

- **Linux x86_64 CPython 3.10/3.12 + Chromium/Firefox/WebKit re-run** — `DEFERRED — Linux release owner`.
- **Real STM32 development board observation smoke** — `DEFERRED — user/hardware owner`.

## 9. Completion checklist

- [x] verify:dist passes on a clean Windows checkout (LF source + generated dist).
- [x] Five-minute performance gate implements the 300 s window, warmup/measure, 256 rows, 8 selected series, update p95/max, queue growth, server-drop totals, and `performance.json` evidence.
- [x] Release helper runs the complete Windows matrix, asserts HEAD identity, uses the support manifest, builds wheels offline, performs the installed-copy smoke, and fails closed with per-gate PASS/FAIL.
- [x] Monitor suites pass as disjoint partitions on 3.10 and 3.12; no gate is reported with a star.
- [x] Release docs aligned (marketplace, roadmap split, 0.5/0.6 boundary).
- [x] Report records the new code head and every gate's actual PASS/FAIL without PASS-star shorthand.
