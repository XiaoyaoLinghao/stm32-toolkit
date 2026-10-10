# STM32TK-101 C implementation return

- Slice base: `748efdc6aad422edc8c7b63565b53854855df274`
- CodeHead before this report: `8454d3f1afb6a435e7bfbcb56fbf2851ac9730ec`
- Owner: C implementation agent. Independent complete-diff review and acceptance belong to the primary agent.
- Authority used: local implementation, offline software tests, and local commits only. No board access, install, push, PR, merge, tag, or release.

The result now identifies the first out-of-range SVD register with its path, address, width, byte count, and trusted regions. Debug binding reports all mismatched flash-receipt field names and whether the validated receipt ELF digest matches the current validated ELF. The original receipt checks and file format remain in force. Public attach refusals add the requested target and an offline PyOCD target-list check for `target-unsupported`; failed `resume-verify` exposes the last validated state and run/reset guidance. These additions use the existing closed attach diagnostic after worker IPC validation.

Successful public flash results add `details.postFlash={targetState:"unknown",runVerified:false}` after workflow cleanup. The persisted `FlashReport` and receipt format were not changed, and the fake-backend tests show no added reset, resume, state query, attach retry, or programming call. Recovery flash remains a separate explicit policy and may leave the target halted.

The Monitor launcher now explains why `STM32_TOOLKIT_DATA_ROOT` is needed before Python can parse `--data-root`, while retaining the exact missing runtime path in errors. The Monitor skill gives a foreground PowerShell invocation with environment restoration, Ctrl-C shutdown, and fresh-tab recovery. UI startup errors use fixed messages for invalid links, 401/403 access rejection, other non-2xx service failures, malformed responses, and incomplete requests; the fragment is still cleared before fetch and no token or raw response body is rendered. The committed `ui_dist` was rebuilt at the current 1.0.0 source version; slice D must rebuild it with the final 1.0.1 version.

## Verification

All runs used Python 3.12.10 or Node 24.18.0/npm 11.16.0 from the existing verified environments. `PYTHONPATH` pointed to this worktree's Toolkit and Monitor `src`, bytecode was disabled, and `TEMP`, `TMP`, `TMPDIR`, npm cache, pytest basetemp, and browser output were under `D:\codex-tmp\tk101\c-run`. Node dependencies were copied from the verified tree into this run root; the initial task-owned UI junction was replaced with an ordinary copy in `tools/stm32-monitor/ui/node_modules` for the reproducible dist build. Nothing was installed.

Before each Python run, the process environment set `PYTHONPATH=D:/codex-tmp/tk101/c/tools/stm32-toolkit/src;D:/codex-tmp/tk101/c/tools/stm32-monitor/src`, `PYTHONDONTWRITEBYTECODE=1`, and all three temporary variables to that run's `tmp` directory. The commands below ran from the worktree root unless marked UI:

```powershell
& 'D:/codex-tmp/v10b-0918/r10/py/Scripts/python.exe' -m pytest -q -o addopts= -p no:cacheprovider --basetemp 'D:/codex-tmp/tk101/c-run/py4/bt' tools/stm32-toolkit/tests/test_svd.py tools/stm32-toolkit/tests/test_debug_firmware.py tools/stm32-toolkit/tests/test_debug_handoff.py tools/stm32-toolkit/tests/test_flash.py tools/stm32-toolkit/tests/test_pyocd_backend.py tools/stm32-toolkit/tests/test_hardware_workflows.py tools/stm32-toolkit/tests/test_cli_hardware.py tools/stm32-toolkit/tests/test_mcp_hardware.py
& 'D:/codex-tmp/v10b-0918/r10/py/Scripts/python.exe' -m pytest -q -o addopts= -p no:cacheprovider --basetemp 'D:/codex-tmp/tk101/c-run/py6/bt' tools/stm32-toolkit/tests/test_hardware_workflows.py
& 'D:/codex-tmp/v10b-0918/r10/py/Scripts/python.exe' -m pytest -q -o addopts= -p no:cacheprovider --basetemp 'D:/codex-tmp/tk101/c-run/plugin2/bt' tools/stm32-toolkit/tests/test_plugin_layout.py
& 'D:/codex-tmp/v10b-0918/r10/py/Scripts/python.exe' -m pytest -o addopts= -p no:cacheprovider --basetemp 'D:/codex-tmp/tk101/c-run/monpy1/bt' tools/stm32-monitor/tests/test_auth.py tools/stm32-monitor/tests/test_ui_dist.py
# UI directory: D:/codex-tmp/tk101/c/tools/stm32-monitor/ui
npm run test -- tests/bootstrap.test.ts tests/main.test.tsx
npm run typecheck
npm run lint
npm run build
npm run verify:dist
npm run test:e2e:windows -- e2e/security.spec.ts --output 'D:/codex-tmp/tk101/c-run/ui-e2e/results' --workers=1
```

The UI browser run additionally bound `STM32_MONITOR_PYTHON` to the verified Python executable, `STM32_MONITOR_CHROMIUM_EXECUTABLE` to the pre-existing Chromium executable, and `STM32_MONITOR_EVIDENCE` to `D:/codex-tmp/tk101/c-run/ui-e2e`.

| Check | Result | Retained output |
| --- | --- | --- |
| Eight affected Toolkit pytest modules (`test_svd`, `test_debug_firmware`, `test_debug_handoff`, `test_flash`, `test_pyocd_backend`, `test_hardware_workflows`, `test_cli_hardware`, `test_mcp_hardware`) | 770 passed, one test assertion failed in 411.24 s: immutable in-process tuple was compared with a list. No product failure. The assertion now checks wire JSON. | `c-run/py4/stdout.txt`, `exit.txt` |
| Final full `test_hardware_workflows.py` after the assertion and handoff-reclaim correction | 104 passed in 6.89 s | `c-run/py6/stdout.txt`, `exit.txt` |
| Focused firmware/Flash/CLI/MCP diagnostics | 12 passed in 10.52 s | `c-run/py3/stdout.txt`, `exit.txt` |
| Final SVD and handoff edge cases | 6 passed in 1.66 s | `c-run/py5/stdout.txt`, `exit.txt` |
| `test_plugin_layout.py` after launcher wording correction | 19 passed in 9.45 s | `c-run/plugin2/stdout.txt`, `exit.txt` |
| Monitor `test_auth.py` and `test_ui_dist.py` | 53 passed in 0.98 s | `c-run/monpy1/stdout.txt`, `exit.txt` |
| UI bootstrap/main Vitest, typecheck, lint, build, byte-identical `verify:dist` | 15 passed; remaining commands exit 0; `verify:dist` confirms seven identical files | `c-run/ui1`, `ui-type`, `ui-lint`, `ui-build`, `ui-verify` |
| Existing Playwright security tests, two Chromium viewports | 4 passed in 21.1 s; pre-existing Chromium executable verified before use | `c-run/ui-e2e/stdout.txt`, `exit.txt` |
| `git diff --check` | Exit 0 | Local Git check |

The first broad run was interrupted after exposing the same test assertion, and a focused diagnostic run confirmed it; their minimal logs are retained under `c-run/py1` and `c-run/py2`. An initial launcher test failed because its error string omitted the exact runtime path; the final launcher test passes. The initial eight-module aggregate is not a whole-suite PASS; the affected module and edge cases passed after correction. The other seven modules had no subsequent product changes.

After independent review requested two corrections, 401/403 remained the only non-2xx statuses labeled access rejection; 404, 429, 500, and 503 now use a fixed neutral startup failure. The revised DOM test also checks unknown-code fallback and absence of token, response body, and false rejection wording. A rebuilt manifest now uses `node_modules/preact/...`, with no `c-run` path; the UI dependency path was verified as an ordinary directory. Using the same UI commands above, the revision passed `npm run test -- tests/bootstrap.test.ts tests/main.test.tsx` (20 passed, exit 0), `npm run typecheck` (exit 0), `npm run build` (exit 0), and `npm run verify:dist` (seven files byte-identical, exit 0). Logs and exit markers are in `c-run/rev-ui-test`, `rev-ui-type`, `rev-ui-build`, and `rev-ui-verify`. Python product bytes were unchanged in this revision, so their prior evidence was retained without rerunning the broad matrix.

All `c-run` subdirectories (including `replace_ui_deps.py` and the original copied dependency source) and `D:\codex-tmp\tk101\c\tools\stm32-monitor\ui\node_modules` (ordinary copied dependency directory) are disposable after the primary agent retains the needed evidence. The primary agent owns their cleanup. Actual target behavior and the reported physical attach cause remain external evidence, not software PASS.
