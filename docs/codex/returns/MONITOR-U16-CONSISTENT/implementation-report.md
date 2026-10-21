# Monitor U16 consistent-read implementation return

- Implementer: `u16_compact_impl`, `gpt-6-sol` / `max`.
- Accepted full base: `ba390750127d9f89efd521a503f5338976640203`.
- Product and test CodeHead before this report: `d6e3749b65bf2266298a8002971f738d2aee85ea` on `codex/monitor-u16-consistent` in `D:\codex-tmp\ur1021\impl`.
- The primary owns specification, integration, independent review, acceptance, cleanup, and the local 8765 service. The implementer does not accept its own diff. No push, PR mutation, merge, tag, release, hardware, firmware, browser, HTTP, installation, or service restart was performed.

## Delivered behavior

The sampler passes deduplicated `u16le` operand pairs from its frozen group revision to ProbeSession and the existing Toolkit observation plan on start and resume. Eligible adjacent unsigned-byte variables in one safe aligned SRAM word are removed from ordinary read groups. Toolkit reads that word at most three times, compares only the union of protected operand bytes, and uses the last of two consecutive matching snapshots for raw and derived watches. Shared-word and reversed pairs, explicit raw dependencies, and neighboring ordinary variables preserve their distinct identities and normal output order.

An unstable word yields `DEBUG_READ_UNSTABLE` for affected raw items and a derived unavailable gap; read exceptions and short reads yield their existing distinct item errors without individual byte fallback. Ordinary and ineligible pairs retain the old path. Expanded reads require one and only one memory-region entry intersecting the aligned word; that entry must fully contain the word and inputs, be the same input region, be readable and writable, lie within the defined SRAM interval, and avoid SVD-readable overlap. The prepared plan is immutable and no accepted value is reused across batches or resumes. Public watch, storage, ProbeSession wire, UI, firmware, and version remain unchanged.

## Verification by implementation owner

Windows PowerShell with Python 3.12.10 at `C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe` ran with `-B`, `PYTHONDONTWRITEBYTECODE=1`, and `PYTHONPATH=D:\codex-tmp\ur1021\impl\tools\stm32-toolkit\src;D:\codex-tmp\ur1021\impl\tools\stm32-monitor\src`. `TEMP`, `TMP`, and `TMPDIR` pointed to `D:\codex-tmp\ur1021\t`; each pytest basetemp and cache directory was under the same task root. Logs record complete command output.

The deterministic pre-change read used an odd-address logical two-byte batch and produced the old-low/new-high combination `[255, 1]` instead of a coherent pair, **1 expected failure** (`red-timing.log`). The aligned protected-read correction passed that scenario (`green1.log`). Focused contract tests passed **24** (`focused4.log`), including A/A and A/B/B acceptance, A/B/C gap, padding changes, full-word failure and partial read, shared-word offset union, ordinary neighbors, safety rejection, resume, and a no-hardware PyOCD 0.45.1 transport-shape proof. One connected software integration passed (`integration2.log`): a saved/imported group through real prepared observation, ProbeSession/Sampler, persisted HistoryStore and CSV at 0 and 65535, followed by an unstable gap. This is software evidence, not physical target evidence.

The final Monitor command at exact CodeHead ran from the repository root:

```powershell
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -B -m pytest -o addopts='' -q -rs tools/stm32-monitor/tests/test_probe_session.py tools/stm32-monitor/tests/test_sampler.py tools/stm32-monitor/tests/test_history.py tools/stm32-monitor/tests/test_exports.py tools/stm32-monitor/tests/test_risk_sampler_start_transaction.py tools/stm32-monitor/tests/test_risk_sampler_group_epoch.py tools/stm32-monitor/tests/test_risk_probe_session_admission.py tools/stm32-monitor/tests/test_risk_monitor_contracts.py --basetemp D:\codex-tmp\ur1021\id -o cache_dir=D:\codex-tmp\ur1021\cd
```

Result: **302 passed, 0 skipped in 98.99s**, `D:\codex-tmp\ur1021\monitor-final.log`.

The final Toolkit and cross-package command at exact CodeHead ran from the repository root:

```powershell
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -B -m pytest -o addopts='' -q -rs tools/stm32-toolkit/tests/test_monitor_consistent_read.py tools/stm32-toolkit/tests/test_debug_read.py tools/stm32-toolkit/tests/test_debug_firmware.py tools/stm32-toolkit/tests/test_debug_handoff.py tools/stm32-toolkit/tests/test_monitor_observation.py tools/stm32-monitor/tests/test_risk_observation_supersession.py --basetemp D:\codex-tmp\ur1021\ie -o cache_dir=D:\codex-tmp\ur1021\ce
```

Result: **431 passed, 1 skipped in 429.08s**, exit code 0, `D:\codex-tmp\ur1021\toolkit-final.log`. The skip is the existing Windows directory-handle restriction on rename in `test_monitor_observation.py:948`; the test declares that platform limitation explicitly.

An earlier affected regression run yielded **206 passed, 2 failed, 1 skipped** (`affected1.log`). The two failures were **INFRASTRUCTURE** test-fixture mismatches: the old `FakeObservation`/`ByteObservation` preparation signatures did not accept the new private `u16_pairs` keyword. The fixtures were updated to verify pair forwarding and the final regressions passed. An earlier Toolkit run on product head `002f2a19` yielded **424 passed, 2 failed, 1 skipped** (`toolkit-codehead.log`). Those two failures were also **INFRASTRUCTURE**: the new PyOCD transport-shape test imported PyOCD into the shared pytest process, contaminating existing lazy-import assertions. The proof was moved to an isolated subprocess without changing product behavior; the proof and both lazy assertions passed together, **3 passed** (`orderfix.log`). An earlier Monitor-only attempt did not collect because `test_risk_observation_supersession.py` imports the Toolkit test fixture module `test_debug_read` from a test directory absent on that invocation's path; this was **ENVIRONMENT**, with no product assertion run. The final commands include that risk test alongside the Toolkit test module in one process. No failure evidence is mislabeled as a physical PASS.

## Limits and handoff

The stable aligned read removes the observed read-side split transaction and bounds stability checks. Two firmware byte stores can still be interrupted between writes; atomic firmware publication is not established. New physical sampling, browser behavior and authenticated live-service HTTP are deferred to the primary's separately authorized work. The primary independently reviews the accepted-base-to-CodeHead diff and issues the acceptance verdict.

Primary owns run-root cleanup after evidence reconciliation. Implementer-created basetemp/cache directories still present or attempted beneath `D:\codex-tmp\ur1021` are `c1`–`c9`, `cb`, `cc`, `cd`, `ce`, `i1`, `i1b`, `i2`–`i9`, `ib`, `ic`, `id`, `ie`, `catalog`, and `t`. Implementer logs are `red.log`, `red-timing.log`, `green1.log`, `affected1.log`, `focused2.log`–`focused4.log`, `integration1.log`, `integration2.log`, `monitor-codehead.log`, `monitor-final.log`, `toolkit-codehead.log`, `toolkit-final.log`, and `orderfix.log`. Useful held evidence is the deterministic red/green, connected integration, failed-run classification, and final suite logs. The primary/reviewer own `p`, `pc`, `pt`, `r`, `r2`, `review` and their evidence; the primary's cleanup attempt was policy-blocked before deletion. No source, shared cache, service state, or other owner's files were deleted by this implementer.
