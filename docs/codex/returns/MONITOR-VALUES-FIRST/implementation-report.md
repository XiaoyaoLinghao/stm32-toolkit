# Monitor values-first — implementation return

## Identity and scope

- Accepted base: `1a9cadb42f9eace2fa173bdd9d5a42e9a4d20742`.
- Approved design and plan: `docs/superpowers/specs/2026-10-19-monitor-values-first-design.md` and `docs/superpowers/plans/2026-10-19-monitor-values-first-plan.md`.
- Implementation branch: `codex/monitor-values-first`; clean starting docs HEAD: `98ec11d15fdda95e15be38ea121226bd0bc8b662`.
- Product, implementation tests, and generated dist CodeHead before this report: `543741b2d42c2e51ddcc8ae41b3b3100ea5eaad3`.
- Implementation/test owner: `values_first_impl` (`gpt-6-sol` / max). Specification, integration review, acceptance, procedure, and deployment belong to the primary agent; independent review belongs to `values_first_review`.
- No push, PR mutation, merge, tag, release, installation, authentication, browser automation, hardware access, or service deployment was performed by this implementation owner.

The CodeHead changes only Monitor UI presentation and App assembly, an App behavior test, and the generated `ui_dist`. It does not change controller, reducer, API, schema, backend, DWARF, dependency, lock, or version contracts. The original `D:\workspace\stm32-toolkit` tree was not used for implementation or tests.

## Delivered behavior

- The live workbench now lays out the 44 px sampling toolbar, source, always-visible values, and optional chart in that order. `selectedSeries.size > 0` is the chart's display condition for both variable and register curves, including selections with no points. Without curves, values take the available main region; with curves, the values region stays above an internally scrolling chart split. The normal desktop value budget is up to 208 px, with a 108 px lower bound. Real browser layout at 1366×768 and 1440×900 remains deferred.
- The old hide-all-values action is gone. “放大波形” reduces the still-reachable values region to 108 px and expands the chart; removing the final curve clears that emphasis. The selected-curve removal entry, row controls, source/freshness, waiting state, zoom, and eight-curve limit remain available. `LiveChart` remains mounted and receives visibility and layout changes for resize without changing chart math or controller lifecycle.
- An App-local presentation receipt records a probe scope/request ID only when the sole existing reducer invocation actually adopts a matching `request.succeeded`. A thin dispatch observer forwards every original action unchanged and binds a synchronous `request.started` only to the current device-button intent and drawer epoch. Connect, reconnect, and release close the device drawer after that adopted ACK. Promise resolution, pending disappearance, status GET, failures, retired attempts, access blocks, diagnostic retries, and stale ACKs do not grant return. A later independent status failure remains a `status` failure. Closing, reopening, switching drawers, and group navigation invalidate the prior intent. Focus returns to a visible device trigger, with header/diagnostic fallback when the original trigger is hidden.

## Verification

Environment: PowerShell `7.6.7` at `C:\Program Files\PowerShell\7\pwsh.exe`; Node `v24.18.0` at `C:\Program Files\nodejs\node.exe`; cwd `D:\codex-tmp\mv1019\impl\tools\stm32-monitor\ui`. The dependency tree was copied from `D:\codex-tmp\mw1018\review\tools\stm32-monitor\ui\node_modules`; no install or borrowed-cache write occurred. Each command used its own `D:\codex-tmp\mv1019\impl-check\<run>\` with `TEMP`, `TMP`, `TMPDIR`, `XDG_CACHE_HOME`, and `npm_config_cache` bound to that run. Complete `argv.txt`, `output.log`, and `exit.txt` remain in every named run root. The command prefix below is the exact Node executable above.

| Run root | Arguments after Node executable | Exit | Evidence |
| --- | --- | ---: | --- |
| `red-app` | `node_modules/vitest/vitest.mjs run tests/values-first-app.test.tsx --configLoader runner --maxWorkers 4 --testTimeout 15000` | 1 | Before implementation, 8 of 9 new tests failed on the old behavior; one passed. |
| `focused-app-1`, `focused-app-2`, `focused-app-5` | Same focused App command | 1 | Test fixture/assertion corrections: open the mock live socket, query hidden drawer by its DOM identity, and inspect diagnostic code inside a closed details element. These were TEST failures, not accepted product regressions. |
| `focused-app-3`, `focused-app-4`, `focused-app-6`, `focused-app-7` | Same focused App command | 0 | Final run: 15 App cases pass, covering both catalog item kinds, selected/no-points chart, emphasis, max eight, all three probe writes, failed/unknown/no-op, retired retry, access block, late close/reopen/switch, group navigation, diagnostic retry, follow-up status failure, and focus fallback. |
| `focused-regressions` | `node_modules/vitest/vitest.mjs run tests/values-first-app.test.tsx tests/app.test.tsx tests/app-errors.test.tsx tests/workbench-app.test.tsx tests/ui06-app-live.test.tsx tests/ui06-live-freshness.test.tsx tests/ui04-chart-interaction.test.tsx tests/live-table-interaction.test.tsx tests/sampling-controls.test.tsx tests/recovery-ui.test.tsx tests/groups-import-lifecycle.test.tsx tests/ui06-app-history.test.tsx tests/export-panel.test.tsx tests/a11y.test.tsx tests/components-coverage.test.tsx --configLoader runner --maxWorkers 4 --testTimeout 15000` | 0 | 15 files / 87 tests, including the existing live source, chart, sampling, focus, group draft/import, history, export, recovery, and a11y paths. |
| `full-ui-final` | `node_modules/vitest/vitest.mjs run --configLoader runner --maxWorkers 4 --testTimeout 15000` | 0 | Final source: 52 files / 454 tests passed, including UI unit and a11y. jsdom emitted its existing “Not implemented: navigation to another Document” advisory without a failed test. |
| `typecheck-final` | `node_modules/typescript/bin/tsc -p tsconfig.json` | 0 | UI TypeScript passed. |
| `typecheck-e2e-final` | `node_modules/typescript/bin/tsc -p tsconfig.e2e.json` | 0 | Browser test types passed; no browser test was run. |
| `lint-final` | `node_modules/eslint/bin/eslint.js src tests` | 0 | UI lint passed. |
| `build-final` | `node_modules/vite/bin/vite.js build --configLoader runner` | 0 | Production UI build passed; Vite's existing >500 kB chunk advisory remains. |
| `verify-dist-final` | `scripts/verify-dist.mjs` | 0 | Seven generated dist files byte-identical. |

Earlier successful `typecheck-early`, `typecheck-current`, and `lint-current` runs are retained with exact argv and output; the final checks above cover the frozen source. `git diff --check` and `git diff --cached --check` passed before the CodeHead commit.

Run-owned `tmp` and `cache` directories under this round's `impl-check` root were resolved, checked for root containment and reparse components, then removed with native PowerShell after their evidence was no longer needed. All run logs remain; reusable copied dependencies and tracked fixtures were preserved. No cleanup was attempted against the older `mw1018` roots.

## Deferred and handoff

Actual browser rendering at the specified desktop sizes, browser e2e/bootstrap, hardware/probe operation, physical sampling, installation, release checks, and the 8765 service update are not implementation PASS. The primary agent owns any later authorized service update and independent exact-CodeHead integration verification. This report supplies implementation evidence only and does not accept its own diff.
