# Monitor workbench refactor — implementation return

## Ledger and scope

- Accepted base: ab274cf8ecde1bfd352419eb49140961818a43ac
- Approved specification: docs/superpowers/specs/2026-10-18-monitor-workbench-refactor-design.md
- Approved plan: docs/superpowers/plans/2026-10-18-monitor-workbench-refactor-plan.md
- Implementation branch: codex/monitor-workbench-refactor
- Frozen product/tests/dist CodeHead before this report: 8649c494721e8cb631c84855a204dc271e09df00
- Implementation owner: workbench_impl. Independent review and acceptance belong to the primary agent and reviewer. No remote action was taken.

The two implementation commits after the approved parent commit change only Monitor UI source, UI tests, and generated ui_dist assets. The accepted-base-to-CodeHead diff also contains primary-owned approved docs, design assets, and test SOP changes from the parent commit. The implementation does not change controller/state/API/chart math, Python backend, schemas, dependencies, lockfiles, or versions.

## Delivered behavior

- A compact light Chinese workbench has a 52 px header, 28 px footer, default narrow grouped directory, flexible wave canvas, 44 px sampling toolbar, and a value region that adapts from one through three rows and then scrolls within a 208 px cap. The directory has a visible close control on narrow layouts.
- A single App-owned drawer selector exposes device, group, and diagnostics. The group editor, catalog query/expansion, history draft range, export manual range/confirmation, and diagnostic write confirmation retain local state while their view or drawer is hidden. Add from directory still uses the existing reducer action and then opens the group editor.
- Disconnected Start opens device choice. Existing legal Pause/Resume/Stop, including Stop while disconnected, retain their underlying controller gates. The catalog preserves the distinction between an unsampleable register and one that can be added after access acknowledgement.
- The chart header owns zoom controls; layout changes trigger chart resize. At the 390 px shell minimum, the value region contracts to 84 px and leaves about 88 px for the chart host; at ordinary desktop heights the 108/180/208 px value budgets remain. The selected-curve removal popup opens downward and scrolls inside the remaining value-region height. The full run/group/revision IDs are available in diagnostic details while the canvas uses a compact source/revision/freshness label.
- The persistent failure count opens diagnostics from every page. The original scope/request ID retry and recovery operations remain reachable. Nested confirmations own Escape/Tab only while topmost, receive focus even when a hidden parent drawer is reopened, and restore focus to a visible target. The export confirmation uses a portal so it remains visible across a forced page change.
- Group import/export remains JSON through existing handlers. History query/paging and server CSV/JSONL export/download handlers remain in place; the refactor changes presentation and mounting, not those contracts.
- The footer now shows source and freshness from the exact active run group/revision, plus compact rate, latency, and total drops in a horizontally scrollable strip. Diagnostics exposes the complete rate, latency, raw nanoseconds, sample time, and all four drop counters. When a saved group revision changes during an old run, the footer marks the source unverified rather than relabeling the old sample with the new draft or revision.

New App regression tests cover directory add and dirty retention, hidden failure retry, group import preview retention, history and export ranges across page switches, export confirmation retention, pending group navigation and nested focus/keyboard behavior, write-confirm priority, and acknowledgement-required versus unsampleable catalog items. Affected existing tests were updated for relocated controls. Chart resize and disconnected Stop have focused coverage. The R1 App regression checks footer source identity before and after a saved revision ACK, then opens diagnostics to verify raw latency and all four drop counters.

## Verification and failure classification

Environment: PowerShell 7 at C:\Program Files\PowerShell\7\pwsh.exe, Node at C:\Program Files\nodejs\node.exe, cwd D:\codex-tmp\mw1018\impl\tools\stm32-monitor\ui. Existing node_modules was copied from D:\codex-tmp\mf1017\impl\tools\stm32-monitor\ui\node_modules; no install or shared-cache write occurred. Each run set TEMP, TMP, and TMPDIR together to its own run-root tmp directory, and XDG_CACHE_HOME/npm_config_cache to its cache directory.

Every run has exact argv.txt, complete output.log (stdout and stderr), and exit.txt under D:\codex-tmp\mw1018\impl-check\<run-name>\. The following command keys are exact argv after the common executable prefix N = C:\Program Files\nodejs\node.exe:

| Key | Arguments after N |
| --- | --- |
| WB | node_modules/vitest/vitest.mjs run tests/workbench-app.test.tsx --configLoader runner |
| F13 | node_modules/vitest/vitest.mjs run tests/app.test.tsx tests/app-errors.test.tsx tests/ui05-group-ui.test.tsx tests/ui06-app-live.test.tsx tests/ui06-app-history.test.tsx tests/groups-import-lifecycle.test.tsx tests/catalog-tree.test.tsx tests/sampling-controls.test.tsx tests/recovery-ui.test.tsx tests/history-panel.test.tsx tests/export-panel.test.tsx tests/ui04-chart-interaction.test.tsx tests/workbench-app.test.tsx --configLoader runner |
| APP | node_modules/vitest/vitest.mjs run tests/app.test.tsx --configLoader runner |
| MIX4 | node_modules/vitest/vitest.mjs run tests/workbench-app.test.tsx tests/sampling-controls.test.tsx tests/export-panel.test.tsx tests/recovery-ui.test.tsx --configLoader runner |
| ERR4 | node_modules/vitest/vitest.mjs run tests/app-errors.test.tsx tests/components-coverage.test.tsx tests/ui03-recovery-ui.test.tsx tests/workbench-app.test.tsx --configLoader runner |
| ALL | node_modules/vitest/vitest.mjs run --configLoader runner |
| BOUNDED | node_modules/vitest/vitest.mjs run --maxWorkers 4 --testTimeout 15000 --configLoader runner |
| CHART | node_modules/vitest/vitest.mjs run tests/ui04-chart-interaction.test.tsx --configLoader runner |
| FOCUS3 | node_modules/vitest/vitest.mjs run tests/workbench-app.test.tsx tests/components-coverage.test.tsx tests/a11y.test.tsx --maxWorkers 4 --testTimeout 15000 --configLoader runner |
| R1-F9 | node_modules/vitest/vitest.mjs run tests/ui06-app-live.test.tsx tests/ui06-live-freshness.test.tsx tests/live-table-interaction.test.tsx tests/workbench-app.test.tsx tests/components-coverage.test.tsx tests/a11y.test.tsx tests/ui04-chart-interaction.test.tsx tests/app-errors.test.tsx tests/sampling-controls.test.tsx --maxWorkers 4 --testTimeout 15000 --configLoader runner |
| R1-A6 | node_modules/vitest/vitest.mjs run tests/app.test.tsx tests/ui03-recovery-ui.test.tsx tests/ui05-group-ui.test.tsx tests/ui06-app-history.test.tsx tests/presentation-workbench.test.tsx tests/components.test.tsx --maxWorkers 4 --testTimeout 15000 --configLoader runner |
| R1-A1 | node_modules/vitest/vitest.mjs run tests/app.test.tsx --maxWorkers 4 --testTimeout 15000 --configLoader runner |
| TSC | node_modules/typescript/bin/tsc -p tsconfig.json |
| TSC-E2E | node_modules/typescript/bin/tsc -p tsconfig.e2e.json |
| LINT | node_modules/eslint/bin/eslint.js src tests |
| BUILD | node_modules/vite/bin/vite.js build --configLoader runner |
| DIST | scripts/verify-dist.mjs |

| Run root | Key | Exit | Result or reason |
| --- | --- | ---: | --- |
| focused1 | WB | 0 | Initial new App scenarios passed. |
| focused2 | F13 | 1 | Six legacy App expectations referred to relocated controls (TEST assertion update). |
| focused3 | F13 | 1 | One App test used an unflushed direct click (TEST assertion update). |
| focused4 | APP | 1 | One remaining device-detail close-button expectation (TEST assertion update). |
| focused5 | APP | 0 | Updated App test passed. |
| focused6 | MIX4 | 1 | New import-preview test omitted a mock spy (TEST fixture correction). |
| focused7 | WB | 0 | Seven new App scenarios passed. |
| focused8 | ERR4 | 0 | Four files / 23 tests passed after focus and recovery corrections. |
| focused-typing | WB | 0 | Seven new App scenarios passed after the range-input assertion change. |
| full-ui | ALL | 1 | 434/438 passed. Two standalone dialog-focus fixtures lacked modal semantics, one recovery assertion assumed old layout (TEST assertion correction), and one test hit the default 5 s timeout under parallel load (ENVIRONMENT). |
| full-ui-final | ALL | 1 | 435/438 passed. Only three default 5 s timeouts under 51-file parallel load: queued newer create draft; recovery draft/history navigation; history retry A retaining draft B/export range. No failed assertions. Classified ENVIRONMENT scheduling. |
| full-ui-bounded | BOUNDED | 0 | 51 files / 438 tests passed with four workers and a 15 s runner timeout. The same product and assertions were used. |
| chart-resize | CHART | 0 | Four chart interaction tests passed after the added resize assertion. |
| focus-fallback | FOCUS3 | 0 | Three files / 19 tests passed after the final nested-focus fallback and label changes. |
| typecheck | TSC | 2 | New test TypeScript inference errors (TEST typing correction). |
| typecheck-final, typecheck-posttest, typecheck-fallback | TSC | 0 | Final TypeScript checks passed. |
| typecheck-e2e, typecheck-e2e-final | TSC-E2E | 0 | Final e2e type checks passed; no browser e2e run. |
| lint, lint-posttest, lint-fallback | LINT | 0 | Final UI lint passed. |
| build, build-final | BUILD | 0 | Final UI build passed. Vite reported the existing >500 kB chunk-size advisory. |
| verify-dist, verify-dist-final | DIST | 0 | Final dist verification: seven files byte-identical. |
| r1-focused | R1-F9 | 0 | Nine affected files / 47 tests passed, including runtime source, complete stats, focus, chart, and curve removal. |
| r1-app-regressions | R1-A6 | 1 | Five files / 27 tests passed; App test used an ambiguous label query after diagnostics gained a second, hidden stats region (TEST assertion correction). |
| r1-app-fix | R1-A1 | 0 | Corrected App test passed using the visible region role. |
| r1-typecheck, r1-typecheck-e2e | TSC, TSC-E2E | 2 | exactOptionalPropertyTypes rejected a sourceFreshness prop explicitly passed as undefined (PRODUCT typing correction). |
| r1-typecheck-final, r1-typecheck-e2e-final, r1-typecheck-postapp, r1-typecheck-e2e-postapp | TSC, TSC-E2E | 0 | Both type checks passed on final R1 source and test bytes. |
| r1-lint, r1-lint-final, r1-lint-postapp | LINT | 0 | UI lint passed on final R1 source and test bytes. |
| r1-build | BUILD | 0 | R1 production build passed; the >500 kB chunk-size advisory remains. |
| r1-verify-dist | DIST | 0 | R1 dist verification: seven files byte-identical. |

The bounded full suite preceded the final narrow chart-test and nested-focus fallback/label edits. Those exact affected paths were rerun in chart-resize and focus-fallback. The R1 product changes were checked with the focused App/focus/chart/curve/stats and App regression selections above; the 438-test full suite was not repeated because the R1 behavior was bounded to these paths. Final source passed both type checks, lint, build, and dist verification. git diff --check and git diff --cached --check passed before each product commit (Git emitted only LF-to-CRLF working-copy notices).

## Deferred evidence, artifacts, and cleanup

Real browser/e2e execution, hardware/probe operation, physical sampling, release matrix, and the 8765 service update were outside this implementation role and were not claimed as PASS. No tokens, registry credentials, or user data were read.

The run root D:\codex-tmp\mw1018\impl-check contains 41 named runs. Their argv/output/exit records and diagnostic failure output are retained. Per-run tmp/cache directories are inside that root; the latest inventory found 7,467 tmp entries and zero cache entries. A resolved-path-checked native PowerShell recursive cleanup attempt for D:\codex-tmp\mw1018\impl-check\focused1\tmp and ...\focused1\cache was rejected by automatic tool policy. I did not retry those paths, change tools to bypass the rejection, or attempt further recursive deletion. These disposable directories remain pending an authorized cleanup path. The copied node_modules is a reusable dependency tree, not a run artifact.

This report records implementation evidence only. Independent complete-diff review, acceptance, and service update remain with the primary agent.
