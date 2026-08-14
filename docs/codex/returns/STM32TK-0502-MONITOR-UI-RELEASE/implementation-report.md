# STM32TK-0502 Monitor UI Release — Final Acceptance Report

## 1. Ledger and outcome

- Module: `STM32TK-0502-MONITOR-UI-RELEASE`
- Acceptance outcome: `ACCEPTED`
- Implementation status: `IMPLEMENTED`
- Specification owner / acceptance reviewer / final evidence owner: Codex
- Branch: `stm32tk-0502-ui-complete`
- Accepted base: `bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa`
- Code head before this report commit: `f6284d444ebb5a11c346aef2e5ff7777027e5ec1`
- Final bounded correction: Codex changed only `tools/stm32-monitor/tests/test_history.py`; product implementation and all accepted thresholds remained unchanged.
- Remote authorization/actions: none; no fetch, push, PR mutation, approval, merge, close, retarget, or remote branch deletion occurred.
- Blockers: none.
- Deviations: none.

The complete accepted-base-to-CodeHead diff contains 162 no-renames entries. Its exact status/path/byte/SHA-256 inventory is retained as `accepted-base-to-code-head-inventory.json` (35,741 bytes, SHA-256 `14f092062b01679ebb2d13934eef3008386d6bcbc8ce7146cc0cb998b5a6a6c0`). It covers the Monitor service/UI, Toolkit integration, release controller/verifier, release Skills/docs, and implementation tests. This report is the sole report-only change after the recorded CodeHead.

## 2. Environment and immutable invocation

| Fact | Value |
|---|---|
| OS / arch | Microsoft Windows 11 Pro `10.0.26200` build `26200`, AMD64 |
| CPU | AMD Ryzen 7 5800U, 8 cores / 16 logical processors |
| Git | `C:\Program Files\Git\cmd\git.exe`, `2.55.0.windows.3` |
| Windows PowerShell | `C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe`, `5.1` |
| Node | `C:\tmp\stm32tk-0502-support\node\node.exe`, `v24.18.0` |
| npm | `C:\tmp\stm32tk-0502-support\node\npm.cmd`, `11.16.0` |
| CPython 3.10 | `C:\Users\ZhangYang\stm32tk-310venv\Scripts\python.exe`, `3.10.11` |
| CPython 3.12 | `C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe`, `3.12.10` |
| cmd.exe | `C:\WINDOWS\System32\cmd.exe` |
| Chromium | verified support artifact `chromium-1194/chrome-win/chrome.exe` |
| Support manifest | SHA-256 `49feb9180e8d6068caffd98e3193dd53a271e173944774e41db8ab5282dffefa` |
| Working directory | clean detached worktree at the exact CodeHead (`<isolated-review-root>`) |
| Evidence directory | repository-external empty root (`<external-evidence-root>`); only relative evidence paths are recorded below |
| UTC execution window | `2026-08-14T12:20:29Z`–`2026-08-14T13:22:29Z` |

The following full controller invocation applies to every gate row in §3. Non-tool project/evidence roots use the defined aliases above so the tracked report does not disclose absolute project/data/evidence paths.

```powershell
& 'C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe' -NoProfile -ExecutionPolicy Bypass -File '<isolated-review-root>\tools\release\run_0502_windows_gates.ps1' -RepoRoot '<isolated-review-root>' -EvidenceRoot '<external-evidence-root>' -SupportRoot 'C:\tmp\stm32tk-0502-support' -CodeHead 'f6284d444ebb5a11c346aef2e5ff7777027e5ec1' -Git 'C:\Program Files\Git\cmd\git.exe' -Node 'C:\tmp\stm32tk-0502-support\node\node.exe' -Npm 'C:\tmp\stm32tk-0502-support\node\npm.cmd' -Python310 'C:\Users\ZhangYang\stm32tk-310venv\Scripts\python.exe' -Python312 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -CmdExe 'C:\WINDOWS\System32\cmd.exe'
```

For every row below: evidence owner is Codex; environment, tools, working directory, commit, command, and UTC window are exactly those in §2; exit is the child gate exit captured by the fail-fast controller; `summary.json` is the authoritative reconciliation record. Full bounded stdout/stderr is retained in the correspondingly named `.log` when the command emitted output.

## 3. Complete gate reconciliation

| Gate | Exit | Bounded observed result / measurement | Status |
|---|---:|---|---|
| `git-status-before` | 0 | clean detached tree | PASS |
| `git-head-identity` | 0 | HEAD equals CodeHead | PASS |
| `git-accepted-ancestor` | 0 | accepted base is ancestor | PASS |
| `git-diff-check` | 0 | no whitespace errors | PASS |
| `git-diff-inventory` | 0 | 162 changed paths inventoried with bytes/SHA-256 | PASS |
| `git-archive-code-head` | 0 | immutable CodeHead tar created | PASS |
| `verify-support-before-copy` | 0 | support manifest/tree verified | PASS |
| `version-node` | 0 | `v24.18.0` | PASS |
| `version-npm` | 0 | `11.16.0` | PASS |
| `verify-support-after-copy` | 0 | copied npm cache/support reverified | PASS |
| `verify-changed-scope` | 0 | every changed path within release scope | PASS |
| `historical-skill-blob` | 0 | immutable blob `ffb90521113cb3643cc8ebb4573489a7a36a0d6c` | PASS |
| `version-python310` | 0 | CPython `3.10.11` | PASS |
| `version-python312` | 0 | CPython `3.12.10` | PASS |
| `verify-support-before-node-npm-ci` | 0 | support reverified | PASS |
| `node-npm-ci` | 0 | offline locked install | PASS |
| `verify-support-after-node-npm-ci` | 0 | support reverified | PASS |
| `node-typecheck` | 0 | application typecheck clean | PASS |
| `node-typecheck-e2e` | 0 | E2E typecheck clean | PASS |
| `node-lint` | 0 | lint clean | PASS |
| `node-unit-coverage` | 0 | 33 files / 260 tests; branch 783/810 = 96.66% | PASS |
| `node-coverage-gate` | 0 | per-file accepted coverage gate passed | PASS |
| `node-a11y` | 0 | 1 component accessibility test passed | PASS |
| `node-build` | 0 | production build completed in 4.11 s | PASS |
| `node-verify-dist-1` | 0 | tracked dist byte-identical | PASS |
| `node-verify-dist-2` | 0 | repeated deterministic dist verification | PASS |
| `verify-support-before-node-production-audit` | 0 | support reverified | PASS |
| `node-production-audit` | 0 | 0 vulnerabilities in offline production audit | PASS |
| `verify-support-after-node-production-audit` | 0 | support reverified | PASS |
| `venv-create-310` | 0 | fresh test venv | PASS |
| `venv-install-310` | 0 | Monitor requirements installed offline | PASS |
| `venv-install-toolkit-310` | 0 | Toolkit requirements installed offline | PASS |
| `venv-create-312` | 0 | fresh test venv | PASS |
| `venv-install-312` | 0 | Monitor requirements installed offline | PASS |
| `venv-install-toolkit-312` | 0 | Toolkit requirements installed offline | PASS |
| `python312-monitor-perf-monitor` | 0 | accepted Monitor performance thresholds; 1 passed | PASS |
| `python312-monitor-perf-export` | 0 | accepted export threshold; 1 passed | PASS |
| `python310-monitor-complete` | 0 | 550 passed in 142.01 s | PASS |
| `python312-monitor-main` | 0 | 430 passed in 138.95 s | PASS |
| `python312-monitor-special` | 0 | 120 passed in 12.79 s | PASS |
| `python312-toolkit-controller-contract` | 0 | exact controller contract partition passed | PASS |
| `python312-toolkit-shard-1` | 0 | exact unique shard passed | PASS |
| `python312-toolkit-shard-2` | 0 | exact unique shard passed | PASS |
| `python312-toolkit-shard-3` | 0 | exact unique shard passed; declared skip preserved | PASS |
| `python312-toolkit-shard-4` | 0 | exact unique shard passed | PASS |
| `python312-toolkit-shard-5` | 0 | exact unique shard passed | PASS |
| `python312-toolkit-shard-6` | 0 | exact unique shard passed | PASS |
| `python312-toolkit-shard-7` | 0 | exact unique shard passed | PASS |
| `python312-toolkit-shard-8` | 0 | exact unique shard passed | PASS |
| `python312-monitor-coverage-json` | 0 | canonical Monitor coverage JSON written | PASS |
| `python312-toolkit-coverage-json` | 0 | canonical Toolkit coverage JSON written | PASS |
| `changed-product-branch-coverage` | 0 | 13 changed product files each ≥90% branch | PASS |
| `compileall-310` | 0 | monitored Python trees byte-compile clean | PASS |
| `compileall-312` | 0 | monitored Python trees byte-compile clean | PASS |
| `wheel-toolkit` | 0 | exact `0.5.0` wheel built offline | PASS |
| `wheel-monitor` | 0 | exact `0.5.0` wheel built offline | PASS |
| `wheel-hashes` | 0 | exact names, sizes, and hashes recorded | PASS |
| `installed-venv-310` | 0 | fresh installed-copy venv | PASS |
| `installed-packages-310` | 0 | wheels installed offline | PASS |
| `installed-pip-check-310` | 0 | dependency check clean | PASS |
| `installed-smoke-310` | 0 | imports resolve from installed copy | PASS |
| `installed-http-310` | 0 | real loopback HTTP/CSP/auth smoke passed | PASS |
| `launcher-monitor-310` | 0 | managed Monitor launcher forwarded | PASS |
| `launcher-toolkit-310` | 0 | managed Toolkit launcher forwarded | PASS |
| `installed-venv-312` | 0 | fresh installed-copy venv | PASS |
| `installed-packages-312` | 0 | wheels installed offline | PASS |
| `installed-pip-check-312` | 0 | dependency check clean | PASS |
| `installed-smoke-312` | 0 | imports resolve from installed copy | PASS |
| `installed-http-312` | 0 | real loopback HTTP/CSP/auth smoke passed | PASS |
| `launcher-monitor-312` | 0 | managed Monitor launcher forwarded | PASS |
| `launcher-toolkit-312` | 0 | managed Toolkit launcher forwarded | PASS |
| `launcher-fail-closed-missing-env` | 0 | both launchers exited 2 without plugin data | PASS |
| `launcher-fail-closed-missing-runtime` | 0 | both launchers exited 2 without versioned runtime | PASS |
| `verify-support-before-chromium-copy` | 0 | support reverified | PASS |
| `chromium-working-copy` | 0 | exact-byte browser working copy | PASS |
| `verify-support-after-chromium-copy` | 0 | support reverified | PASS |
| `playwright-functional` | 0 | 40 tests passed at 1280 and 1024 widths | PASS |
| `playwright-performance` | 0 | one 5.1-minute production test passed | PASS |
| `playwright-performance-evidence` | 0 | 4,800 points; update p95 18.9 ms; 0 long tasks ≥200 ms; queue growth 0; heap slope 0.178 MiB/min; all server-drop counters unchanged | PASS |
| `release-static-closure` | 0 | manifest closure, eight Skills, and active surfaces exact | PASS |
| `tracked-byte-manifest` | 0 | 347 tracked files hashed | PASS |
| `git-diff-check-after` | 0 | no whitespace errors after all gates | PASS |
| `verify-support-final` | 0 | support manifest/tree unchanged | PASS |
| `clean-tree` | 0 | isolated worktree clean after all gates | PASS |

`summary.json` records `overall=PASS` and all 84 rows above as `PASS`; no mandatory gate was deferred. The coverage rows most directly affected by the bounded test-only correction are: `history.py` 303/336 branches (90.179%), `models.py` 229/254 (90.157%), and `storage.py` 251/278 (90.288%).

## 4. Version, security, privacy, accessibility, and compatibility facts

- `stm32-toolkit`, `stm32-monitor`, protocol `MONITOR_VERSION`, and plugin manifest are exactly `0.5.0`; locked Node/Python dependency inputs were used offline.
- Loopback/random-port, Host/Origin/auth/CSP, same-origin, no-remote, workspace isolation, forged/persisted data rejection, and real second-service sentinel checks passed.
- Accessibility passed component checks and keyboard-only Connect → group/watch/save/start → RUNNING at 200% zoom with reduced motion; both required viewport screenshots are retained.
- The five-minute test used the accepted 120 s warmup plus 180 s measurement window and all original thresholds. No performance or product timeout threshold was changed.
- Installed wheel imports, real HTTP smoke, and managed launcher behavior passed under both CPython 3.10 and 3.12.
- No token, access URL, raw endpoint, request/response body, or sample value is included in this report or the retained evidence inventory.

## 5. Artifact inventory

`artifact-inventory.json` is the frozen exhaustive inventory of the 99 retained gate logs, nodeid/coverage results, browser/performance evidence, code archive, wheels, and smoke evidence, using relative evidence paths plus exact bytes and SHA-256. It is 15,533 bytes with SHA-256 `12e674f4d4d1128fb97dac97decab5c5c6036097ac38e62a4d4603c5e10870d4`. Key artifacts are reconciled below.

| Relative evidence/repository path | Bytes | SHA-256 |
|---|---:|---|
| `summary.json` | 23,350 | `e99f012d5a76efbb2b9fdb24074c262d360c125d38f5160349fd8f476aa7fef9` |
| `accepted-base-to-code-head-inventory.json` | 35,741 | `14f092062b01679ebb2d13934eef3008386d6bcbc8ce7146cc0cb998b5a6a6c0` |
| `tracked-byte-manifest.json` | 69,178 | `565405dab864b3151b21983d0e4717fb2eaaeafdd7a9df84e0e25262ad15fa42` |
| `monitor-coverage.json` | 321,514 | `85eb148364cbd6ce9c77ce086063683bfee377639ec7373eaf0987fbc70b2bbb` |
| `toolkit-coverage.json` | 861,696 | `e8d79f02e70ec8c116710c71f0b20ad6af2b2aacb5552e27e168a2f3a635cf5c` |
| `.performance-evidence/performance.json` | 634 | `30a95fbf69fc254c410c1026598f446b989b60218d107f2af1f24b306be776c0` |
| `playwright-functional.log` | 6,078 | `c0274928ff4602768569b7fd6b533beedaeeaca0c21e0107e43906b32a7b4548` |
| `playwright-performance.log` | 344 | `62e9d52d5034454f4351ebc80d440537346fa93bd81fce876428263da6db601d` |
| `screenshots/accessibility-chromium-1024.png` | 320,625 | `0d7bd6c26d3e04811ffc1fe2eb57dfa75b4ccabadf076bdc4171de6d01b2e927` |
| `screenshots/accessibility-chromium-1280.png` | 338,446 | `61ab573206e96a4f08fe6af7d7c808e79d894cf0945422b75a4c408e00e6804d` |
| `code-head-archive/code-head.tar` | 6,799,360 | `cf3162e133299cf51a43de65359d769807347f03f391e19283197cf5a5fd07a9` |
| `packages/wheels/stm32_monitor-0.5.0-py3-none-any.whl` | 282,961 | `d10c86c763af58ab6409e7f617ff90f4222c33f83d240acd57e0fe7a49c2101c` |
| `packages/wheels/stm32_toolkit-0.5.0-py3-none-any.whl` | 235,281 | `d5bb7318fcf01bcc3ef3d35e70ef8beb7c1910d657631a41cee2fc75e46e975f` |
| `tools/stm32-monitor/src/stm32_monitor/ui_dist/.vite/manifest.json` | 894 | `927347848b843f133a57c5a285318f5ca519332ba4c2a6d6d6e610b9fc9fe1be` |
| `tools/stm32-monitor/src/stm32_monitor/ui_dist/assets/app-CzzUzrMN.js` | 557,760 | `6ccd89bb0c1b91db046ff9588e264a69897ecbda48106ef4f72c44ba6b9e93d9` |
| `tools/stm32-monitor/src/stm32_monitor/ui_dist/assets/contract-BPQw5UZt.js` | 13,816 | `4e6949d3cea23a3985a8c2706691937fadae4237ef12f9ff7297f56156f95220` |
| `tools/stm32-monitor/src/stm32_monitor/ui_dist/assets/index-6JLIetMy.js` | 3,166 | `3ea409155e49be39596e27762a4039e7ca16cf16e897c6238806bcb2c6353fe4` |
| `tools/stm32-monitor/src/stm32_monitor/ui_dist/assets/index-ytfcZfPW.css` | 1,664 | `b6ce1979b6a607079512eed03dc0dd22d97c86588d6d8dedb1a8b63291f6157e` |
| `tools/stm32-monitor/src/stm32_monitor/ui_dist/assets/preact.module-ZOr5Neeu.js` | 11,695 | `1d9aee8e2dc54b1d38ab9f8c1698f9e68be28329c3d0ee002c2e2a1fb29acae0` |
| `tools/stm32-monitor/src/stm32_monitor/ui_dist/index.html` | 437 | `aad3ebef1b7198bf01df2d636355189f075ec0ace1f3718e25dddc3d79fcf0b2` |

## 6. Named platform deferrals

- Linux x86_64 CPython 3.10/3.12 + Node/npm + Chromium/Firefox/WebKit independent rerun: `DEFERRED — Linux release owner`.
- One supported STM32 board observation smoke: `DEFERRED — user/hardware owner`.

These are the only deferred gates. They do not conceal any reproducible Windows or pure-code failure.

## 7. Final checklist

- [x] Accepted base and CodeHead are full immutable SHAs.
- [x] The complete Windows/pure-code matrix passed at the recorded CodeHead.
- [x] Dual Python, original performance thresholds, ≥90% changed-product branch coverage, exact wheels, installed-copy smoke, browser functional/security/accessibility/isolation, and five-minute performance all passed.
- [x] External evidence uses relative paths with exact bytes/SHA-256 and remains outside the repository.
- [x] No credential, token, access URL, cache, generated test output, or evidence directory is committed.
- [x] This report contains neither its own/final commit SHA nor a moving commit total.
- [x] No remote action was performed.
