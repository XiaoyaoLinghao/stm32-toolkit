# STM32TK-0501 Monitor Service Implementation Report

## 1. Outcome

- Module: `STM32TK-0501-MONITOR-SERVICE`
- Branch: `codex/STM32TK-0501-MONITOR-SERVICE`
- Accepted base: `913600f471d8fb0fb5345bdf668ca39ec1faf4d8`
- Stable code head before this report commit: `e9e7e1943312b70df595c5888670618b51bee014`
- Delivery outcome: `ACCEPTED_WITH_FIXES`
- Whole-branch final-review verdict: `ACCEPTED`
- Remote state: no push, PR mutation, ready/merge/close operation, or remote branch deletion was performed; each requires explicit user authorization.

The unsafe legacy Monitor runtime was replaced by a project-isolated,
authenticated, bounded service using the public Toolkit observation bridge. All
local implementation, Windows acceptance, package, performance, and independent
review gates passed. Only the named Linux and physical-board gates below remain
deferred; no pure-code failure is deferred.

## 2. Complete changed-path inventory

This is the accepted-base-to-code-head change set, plus this last report file.

- Design/records: added `docs/superpowers/plans/2026-08-08-stm32tk-0501-monitor-service.md`, `docs/superpowers/plans/2026-08-08-stm32tk-0501-ui-ready-monitor-contracts.md`, `docs/superpowers/specs/2026-08-08-stm32tk-0501-ui-ready-monitor-contracts-design.md`, and this report.
- Monitor metadata/entry points: modified `tools/stm32-monitor/pyproject.toml`, `src/stm32_monitor/__init__.py`, `__main__.py`, and `cli.py`.
- Monitor product: added `auth.py`, `exports.py`, `groups.py`, `history.py`, `models.py`, `probe_session.py`, `protocol.py`, `runtime.py`, `sampler.py`, `service.py`, and `storage.py` under `tools/stm32-monitor/src/stm32_monitor/`.
- Legacy removal: deleted Monitor `config.py`, `elf_parser.py`, `poller.py`, `pyocd_session.py`, `sse_server.py`, `svd_parser.py`, `static/app.js`, and `static/index.html`.
- Monitor tests: added `test_auth.py`, `test_cli.py`, `test_exports.py`, `test_groups.py`, `test_history.py`, `test_models.py`, `test_package_boundary.py`, `test_probe_session.py`, `test_protocol.py`, `test_runtime.py`, `test_sampler.py`, `test_service.py`, and `test_storage.py` under `tools/stm32-monitor/tests/`.
- Toolkit product: modified `tools/stm32-toolkit/src/stm32_toolkit/__init__.py`; added `monitor_observation.py`; modified `debug/__init__.py`, `debug/dwarf.py`, `debug/sampling.py`, `debug/svd.py`, `debug/types.py`, `probe/lease.py`, `probe/service.py`, and `probe/supervisor.py`.
- Toolkit tests: added `tools/stm32-toolkit/tests/test_monitor_observation.py`; modified `test_dwarf.py`, `test_generation.py`, `test_probe_lease.py`, `test_probe_service.py`, `test_probe_supervisor.py`, `test_sampling.py`, and `test_svd.py`.

No collaboration app, CI, manifest, validator, browser bundle, compatibility
importer, or second backend was added.

## 3. Implemented contracts

- Toolkit provides a cancellation-safe exact-identity OBSERVE bridge and typed register sampling. Monitor never imports or opens PyOCD.
- Immutable models deeply snapshot nested caller data. Groups are SQLite-authoritative, CAS-revisioned, workspace-bound, and paginated with canonical HMAC cursors and an actual 1 MiB UTF-8 HTTP-body ceiling.
- History is immutable, half-open, cursor-bound, corruption-checked, retained in bounded chunks, and exported atomically as lossless JSONL or safe CSV.
- One monotonic sampler producer owns the observation session. Subscriber, history, and deadline drops remain distinct; failed/cancelled persistence reattaches canonical subscriber-drop evidence exactly once.
- The aiohttp service binds dynamic IPv4 loopback only, authenticates Bearer or HttpOnly-cookie requests, validates exact route/query/body grammar, bounds public errors, and supports REST/WebSocket backpressure.
- Probe and variable/register catalog GET routes are present. Malformed download UUIDs map to bounded 4xx `MONITOR_REQUEST_INVALID`, not 500.
- Legacy config, direct ELF/SVD/PyOCD polling, SSE/static UI, default groups, and legacy assets are absent from the wheel.

## 4. Verification evidence

### Environment and complete suites

Windows 11 (`10.0.26200`, x86-64), CPython `3.12.13` and `3.10.11`, offline,
clean isolated worktree, short external basetemp/coverage paths.

```powershell
$env:PYTHONPATH='<worktree>\tools\stm32-monitor\src;<worktree>\tools\stm32-toolkit\src'
$env:COVERAGE_FILE='C:\tmp\r5-final312-02\.coverage'
C:\tmp\stm32-toolkit-review-py31213\Scripts\python.exe -m pytest tools\stm32-monitor\tests -q --basetemp C:\tmp\r5-final312-02 -p no:cacheprovider --cov=stm32_monitor --cov-branch --cov-report=term --cov-fail-under=90
C:\tmp\stm32tk-0301-py310\Scripts\python.exe -m pytest tools\stm32-monitor\tests -q --basetemp C:\tmp\r5-final310-01 -p no:cacheprovider
```

- 3.12: `357 passed in 159.24s`, zero failures/skips/xfails; branch `91.17%`.
- 3.10: `357 passed in 134.90s`, zero failures/skips/xfails.
- Module coverage: `__init__ 100`, `__main__ 100`, `auth 96`, `cli 100`, `exports 90`, `groups 93`, `history 91`, `models 91`, `probe_session 92`, `protocol 94`, `runtime 90`, `sampler 91`, `service 90`, `storage 92` percent. Every product module met 90%.

`rg --files tools/stm32-toolkit/tests -g test_*.py` enumerated 45 files. Eight
short-path shards proved `assigned = unique = expected = 45`, totaling
`2139 passed, 4 skipped`, no xfail/new skip. A mechanical skip-candidate scan and
rerun produced `294 passed, 4 skipped in 152.3s`; the four existing Windows nodes
were:

- `test_monitor_observation.py::test_real_supervisor_thread_swap_after_identity_check_writes_no_replacement_state`
- `test_project.py::test_source_symlink_cannot_escape_canonical_project_root`
- `test_project_model.py::test_file_symlink_cannot_escape_project_root`
- `test_project_model.py::test_directory_symlink_parent_cannot_escape_project_root`

The first is skipped because Windows directory handles deny rename; the other
three because symbolic links were unavailable in that test environment.

### Performance

`.superpowers/sdd/2026-08-08-stm32tk-0501-ui-ready-monitor-contracts/task6_benchmark.py`
ran on CPython 3.12.13/Windows with 3 warmups and 20 measurements. Fixture
SHA-256: `7540819495690c6d66a8e8f4b562b18715a2f018a6960f7cd4435ebe8a3b9b9b`;
database: `46,460,928` bytes.

| Gate (ms) | min | median | p95 | max | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| Append 256 | 26.3065 | 31.2102 | 35.8901 | 40.8105 | PASS |
| Query 10,000 | 75.2880 | 76.6277 | 77.8990 | 79.6737 | PASS |
| Export 100,000 | 3094.8801 | 3195.8586 | 3300.2231 | 3385.5418 | PASS |
| Retention 100,000 | 205.6178 | 211.6074 | 219.7101 | 253.2481 | PASS |
| Retention ticker | 16.0293 | 16.1000 | 16.5301 | 16.5718 | PASS |
| Auth bootstrap | 0.3813 | 0.3866 | 0.4127 | 0.4136 | PASS |
| Status | 0.3273 | 0.3352 | 0.3471 | 0.3496 | PASS |

Query output was `1,490,491` bytes. All 20 retention runs were `OK`, deleting two
batches each. Separate traced export peak was `742,777` bytes; traced latency
`13,655.2328 ms` was memory-only evidence, not the untraced <5 s latency gate.

### Final wheels and installed-package smoke

The stable code was copied outside the repository. Bundled offline CPython
3.12.13 (`pip 26.0.1`, `setuptools 83.0.0`, `wheel 0.47.0`) ran:

```powershell
python.exe -m pip wheel --no-index --no-deps --no-build-isolation --wheel-dir C:\tmp\stm32tk-0501-final-e9e7e19-build\wheels <external-source-copy>
```

| Wheel | Bytes | SHA-256 |
| --- | ---: | --- |
| `stm32_monitor-0.4.0-py3-none-any.whl` | 70,720 | `1c9463a721d5f78f7f3ecf46314d5fdcbf4d4b06285827f59478cd51be76c8be` |
| `stm32_toolkit-0.4.0-py3-none-any.whl` | 235,650 | `061f90261c1e391230a6456cc417394b5fe1f716b00c6d2a5662be7a74db645b` |

Fresh 3.10/3.12 environments installed both with `pip install --no-index
--no-deps` from an external cwd. Offline support trees contained dependencies
only and excluded `stm32*`/`__editable__*`. The same 14-node installed smoke
covered zero-group CRUD, fake observation, sampling, history, JSONL/CSV export,
REST status, WebSocket backpressure, and cancellation:

- 3.10: `14 passed in 3.70s`.
- 3.12: `14 passed in 3.35s`.

Each inventory contained exactly the Monitor/Toolkit package and respective
dist-info. Origins were the new venv site-packages; records contained 37 Monitor
and 133 Toolkit files with no source leakage. Backends/observation exports stayed
lazy and legacy modules/assets were absent.

### Static and immutability

- 3.10/3.12 `compileall` with external cache roots exited zero.
- Accepted-base-to-code-head and final document `git diff --check` passed.
- Package-boundary, forbidden direct-backend/input/default/token, legacy, and dependency scans passed with no prohibited hit.
- Read/start/status/catalog/history project-immutability checks found no byte, name, mtime, mode, or porcelain change.
- Exact path/status audits found no unrelated tracked or untracked product change.

## 5. Review and bounded corrections

Independent review covered the complete base-to-code-head diff. Five bounded
RED-to-GREEN rounds addressed: (1) query caching/retention/canonical cursors;
(2) verified streaming JSONL export; (3) probe/catalog routes, 4,096-item group
pagination, and drop separation; (4) deep GroupPage snapshots, compact UTF-8
budgeting, and failed/cancelled persistence restoration; (5) deep snapshotting
for large-tuple ProtocolResult groups. Toolkit root observation exports were
also restored to lazy import behavior.

The Task 3 malformed-download-UUID minor was fixed and dual-suite verified. Its
stale local report opening status was reconciled as report text only, not a
tracked product change. Final whole-branch review returned `ACCEPTED`, with no
remaining P0/P1 finding.

## 6. Deferred gates and remaining risk

| Status | Named owner | Deferred evidence | Reason |
| --- | --- | --- | --- |
| DEFERRED | Linux owner | Complete Monitor 3.10/3.12, 45-file Toolkit shards, package/install, project immutability, SQLite lock/WAL, loopback, and cancellation on Linux. | Windows cannot establish Linux filesystem/process behavior. |
| DEFERRED | 0.5 release-gate physical-board owner | Exact-probe OBSERVE lifecycle, typed DWARF/register sampling, probe isolation/busy, provenance changes, reconnect, and cancellation on supported board/probe. | Doubles cannot establish USB/probe/target behavior. |

No pure-code failure is deferred. TypeScript UI, browser launch, bundled assets,
release packaging, and 0.5.0 promotion remain in
`STM32TK-0502-MONITOR-UI-RELEASE`.

## 7. Checklist

- [x] Base/code head and exact inventory recorded.
- [x] Complete dual-Python Monitor and complete Toolkit gates passed.
- [x] Coverage, performance, memory, wheels, fresh-install smoke, static, boundary, token, legacy, and immutability gates passed.
- [x] Independent review returned `ACCEPTED` after five fix rounds.
- [x] Only Linux and physical-board evidence is deferred to named owners.
- [ ] Remote push/PR/ready/merge/close/delete remains unperformed and requires explicit authorization.
