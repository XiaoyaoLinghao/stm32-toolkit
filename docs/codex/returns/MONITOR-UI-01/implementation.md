# MONITOR-UI-01 implementation return

- Accepted release base: `0f06c659f5e04aa1f8e53022eae9b5e964da2b4b` (v1.0.1).
- Product CodeHead before this report: `67f0ec4fbc375ed60e1f857b4cae248bf73d1589` on `codex/monitor-ui-01-zh-workbench`.
- Implementation owner: delegated `gpt-6-sol` / `max`, in isolated worktree `D:\codex-tmp\mui1015\impl`. The primary conversation owns independent acceptance. No remote action or hardware access was performed.

The default UI is now a fixed light, Simplified Chinese workbench. Real-time waveforms, sampling controls and latest values lead the page; watch groups and catalog remain at the side, device details open on demand, and history/export share a second view. The same App/controller and stream remain mounted across navigation. The local typed presentation source covers visible and accessible copy, status/error/notice summaries and bigint latency formatting; raw codes and messages remain in diagnostic details. UTC query/export drafts, submitted export ranges, blocker behavior, and existing API semantics are preserved. The generated `ui_dist` was rebuilt from these sources.

Independent review round 1 findings were closed in the same branch: catalog results scroll locally at 320px; export creation and status refresh are serialized so a late older response cannot displace a newer task; the export dialog traps Tab/Shift-Tab and restores focus on Escape, Cancel and Confirm (with an enabled fallback while the creation trigger is busy). The S3 browser test source now covers UTC query prefill, retained manual export draft, per-task submitted range, controlled CSV/JSONL responses and JSONL download content/hash; the 320px browser regression is also present. An inherited missing ECharts `DataZoomComponent` registration was fixed in the owned chart adapter and verified with a real ECharts Node SSR model/window test. Controller, reducer, API, Python service, dependency lock, configuration, version and auth/port behavior were not changed.

At the exact CodeHead above, the implementation owner ran from `tools/stm32-monitor/ui` with `TEMP=TMP=TMPDIR=D:\codex-tmp\mui1015\run\codehead-67f0ec4f`, `npm_config_cache=D:\codex-tmp\mui1015\run\npm-cache`, and `PYTHONUTF8=1`:

| Command | Exit | Evidence |
| --- | ---: | --- |
| `npm.cmd run typecheck` | 0 | `run/codehead-67f0ec4f/typecheck.log` |
| `npm.cmd run typecheck:e2e` | 0 | `run/codehead-67f0ec4f/typecheck-e2e.log` |
| `npm.cmd run lint` | 0 | `run/codehead-67f0ec4f/lint.log` |
| `npm.cmd test` | 0 | `run/codehead-67f0ec4f/vitest.log` — 34 files, 277 tests passed |
| `npm.cmd run build` | 0 | `run/codehead-67f0ec4f/build.log` |
| `npm.cmd run verify:dist` | 0 | `run/codehead-67f0ec4f/verify-dist.log` |

All `run/` paths above are under `D:\codex-tmp\mui1015`; the post-build tracked tree was clean. The primary agent separately reported a complete accepted-base-to-CodeHead review and independent clean-tree verification; that evidence and verdict are its own, not claimed as implementation-owner execution.

Real browser, axe, viewport screenshot and HTTP/WS workflow evidence remain **unobtained**, not PASS. Playwright's Python fake service timed out before page load; direct bounded traces showed Windows asyncio loop creation blocked in `socket._fallback_socketpair`. A Node loopback self-fetch failed `connect EACCES`; controlled Chromium exited with code `3221225506` before a page existed. The primary agent's CUA attempt to visit the tiny local listener was rejected by browser origin/network authority, and the listener was stopped without trying another surface. Minimal failure evidence is `D:\codex-tmp\mui1015\run\browser-blockers.txt` plus `run/browser-dev2/workflow.log` and `run/browser-dev3/workflow.log`. The browser-only S3 and 320px tests are source/type checked but await an authorized Windows browser/loopback environment. There is no screenshot, visual/a11y PASS, physical-device claim or release qualification from this slice.
