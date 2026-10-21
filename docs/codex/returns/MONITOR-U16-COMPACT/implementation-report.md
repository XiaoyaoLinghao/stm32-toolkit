# Monitor U16 compact implementation return

- Implementer: `u16_compact_impl`, `gpt-6-sol` / `max`.
- Accepted full base: `b7d5f43cec3efcfa18ecc1dc7c1e62a839434be7`.
- Product, tests, and generated-asset CodeHead before this report: `3d11c00c5068d988bd8943923f5fe0d2cb67886c` on `codex/monitor-u16-compact` in `D:\codex-tmp\uw1021\impl`.
- The primary owns the specification, integration, complete-diff review, acceptance, standard test procedure, and local 8765 service. This implementer does not approve its own diff. No push, PR, merge, tag, release, hardware, firmware, browser, live-service HTTP, installation, or service restart was performed.

## Delivered behavior

Groups accept one fixed `u16le` watch with `lowExpression` and `highExpression`, preserve its ordered canonical identity through schema-1 transfer, and reject a candidate that cannot fit the existing one-group response envelope before committing it. The sampler freezes ordinary read dependencies at the group revision, reads each unique byte dependency once in the existing ProbeSession batch, and emits original watch order. It composes `low + 256 * high` only from two valid bytes in that batch; unavailable and malformed inputs have separate derived error codes and no typed value. Raw watches and existing lifecycle admission remain unchanged. Group/history rows persist through schema 3; runtime completes the transactional v2 metadata migration before the listener or first public read, with failed-start and cancellation cleanup retaining lock ownership.

The group editor has an initially closed two-variable combination form, uses the normal draft/save path, and keeps complete source expressions accessible. The shared frontend watch helper supplies ordered identity and readable labels in live rows, chart legends, selected curves, and history. The source directory shows globals directly when a file is explicitly opened, loads only those global scopes once per context, and leaves function scopes lazy. Array elements show `[index]`; full selectors, types, provenance, and reasons remain in accessible labels and row details. Source counts and coverage issues are in the existing global diagnostics drawer. Local request failures and explicit retries remain visible.

## Implementer verification

Windows PowerShell 7.6.7, Python 3.12.10 at `C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe`, and Node 24.18.0 at `C:\Program Files\nodejs` were used. Python `PYTHONPATH` contained this checkout's absolute Toolkit and Monitor `src` paths; the Toolkit `tests` path was additionally required by `test_risk_observation_supersession.py` for its `test_debug_read` fixture. `PYTHONDONTWRITEBYTECODE=1`; Python and Node temporary paths and logs were under `D:\codex-tmp\uw1021`. Frozen UI `node_modules` was copied from `D:\codex-tmp\uc1021\review\tools\stm32-monitor\ui\node_modules` into the ignored implementation checkout, without an install or shared-cache mutation.

The exact final backend command ran from the repository root, with `PYTHONPATH` set to `D:\codex-tmp\uw1021\impl\tools\stm32-toolkit\src;D:\codex-tmp\uw1021\impl\tools\stm32-monitor\src;D:\codex-tmp\uw1021\impl\tools\stm32-toolkit\tests`, `PYTHONDONTWRITEBYTECODE=1`, and `TEMP`, `TMP`, `TMPDIR` set to `D:\codex-tmp\uw1021\pytemp`:

```powershell
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest -o addopts='' tools/stm32-monitor/tests/test_models.py tools/stm32-monitor/tests/test_protocol.py tools/stm32-monitor/tests/test_groups.py tools/stm32-monitor/tests/test_storage.py tools/stm32-monitor/tests/test_sampler.py tools/stm32-monitor/tests/test_history.py tools/stm32-monitor/tests/test_exports.py tools/stm32-monitor/tests/test_service.py tools/stm32-monitor/tests/test_probe_session.py tools/stm32-monitor/tests/test_runtime.py tools/stm32-monitor/tests/test_risk_sampler_start_transaction.py tools/stm32-monitor/tests/test_risk_sampler_group_epoch.py tools/stm32-monitor/tests/test_risk_probe_session_admission.py tools/stm32-monitor/tests/test_risk_observation_supersession.py tools/stm32-monitor/tests/test_risk_history_replay_settlement.py tools/stm32-monitor/tests/test_risk_history_corruption_recovery.py tools/stm32-monitor/tests/test_risk_runtime_failed_start_cancellation.py tools/stm32-monitor/tests/test_risk_runtime_lock_allocation.py tools/stm32-monitor/tests/test_risk_runtime_service_cleanup_public.py tools/stm32-monitor/tests/test_ui_assets.py tools/stm32-monitor/tests/test_ui_dist.py --basetemp 'D:\codex-tmp\uw1021\py-final-codehead' -p no:cacheprovider
```

Result at exact CodeHead: **658 passed**, one existing `aiohttp` cookie-filter deprecation warning; `D:\codex-tmp\uw1021\backend-codehead.log`. This includes a software public path from saved/schema-1-imported group through one sampler dependency batch, real HistoryStore, reopening, and CSV. It covers 0, 65535, then an unavailable high byte without stale-value reuse; runtime tests cover read-first v2 groups/history, corrupt-v2 refusal before service start, and cancellation after migration with a replacement owner.

Final UI commands ran from `tools/stm32-monitor/ui`, with `TEMP`, `TMP`, and `TMPDIR` set to `D:\codex-tmp\uw1021\ui-temp`:

| Exact command | Result |
| --- | --- |
| `& 'C:\Program Files\nodejs\npm.cmd' test -- --maxWorkers=2` | 59 files; **506 passed, 1 existing optional replay skip**; `D:\codex-tmp\uw1021\ui-codehead.log`. The skip requires `MONITOR_REAL_BATCHES_JSONL` and does not affect the checked-in replay. |
| `& 'C:\Program Files\nodejs\npm.cmd' run typecheck` | PASS. |
| `& 'C:\Program Files\nodejs\npm.cmd' run typecheck:e2e` | PASS. |
| `& 'C:\Program Files\nodejs\npm.cmd' run lint` | PASS. |
| `& 'C:\Program Files\nodejs\npm.cmd' run build` | PASS; existing large-chunk advisory. |
| `& 'C:\Program Files\nodejs\npm.cmd' run verify:dist` | PASS; seven files byte-identical to the fresh build and committed in CodeHead. |

The initial default-worker full UI run hit one five-second test timeout while running concurrently with backend work. That same test passed in isolation in 1.56 seconds, and the full suite passed twice with two workers; this was test-host contention, not a product assertion failure. An initial backend collection attempt lacked the Toolkit test fixture path, so no tests ran; the corrected exact-head invocation above passed. A new runtime cancellation regression first exposed that a synchronous initialization could finish before cancellation was observed; the startup path now yields before listener publication and the full runtime/lifecycle set passed. Early CSV fixture expectations were corrected for existing JSON-encoded CSV cells. No replay or fixture evidence is labeled physical validation.

## Handoff and artifacts

The exact CodeHead is ready for independent accepted-base-to-CodeHead review and primary integration. The primary owns cleanup of run-scoped logs/basetemps and the ignored implementation `node_modules` after evidence reconciliation. Useful evidence is `backend-codehead.log`, `ui-codehead.log`, and `runtime-final.log` under `D:\codex-tmp\uw1021`; earlier diagnostic logs and `py-*` basetemps remain there for the primary's verified cleanup. No source, service state, backup, or shared dependency cache was deleted. Real browser layout, authenticated live-service HTTP, and physical target behavior are deferred to their separately authorized owners.
