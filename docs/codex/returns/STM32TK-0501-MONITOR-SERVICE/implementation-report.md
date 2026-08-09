# STM32TK-0501 Monitor Service Evidence Reconciliation

## 1. Status and ledger

- Module: `STM32TK-0501-MONITOR-SERVICE`
- Phase: Codex revision Task 6, completed 160 MiB performance amendment
- Specification/architecture owner: Codex
- Implementation owner for this revision: Codex-created task agents, as authorized
  by `docs/superpowers/plans/2026-08-09-stm32tk-0501-codex-revision.md`
- Evidence implementer: Codex Task 6 agent
- Final reviewer/verdict owner: Codex Task 5 controller and fresh independent reviewer
- Branch: `codex/STM32TK-0501-MONITOR-SERVICE`
- Accepted base: `913600f471d8fb0fb5345bdf668ca39ec1faf4d8`
- Stable code head before this report-only correction commit:
  `b1e5d1394daf14e1ba8a749ad6721dbaf87bf695`
- Remote action authorized for Task 6: none

Task 6 does not issue a final review verdict. The user explicitly approved the
exact 160 MiB production artifact ceiling and, after disclosure of the bounded
integrity-trust and batch-static JSONL-prefix risks, explicitly authorized those
optimizations. Functional, memory, and every named performance gate now pass. A
fresh final-head acceptance verdict remains assigned to the controller.

No push, PR mutation, ready/merge/close operation, or remote branch deletion was
performed.

## 2. Accepted-base-to-code-head scope

`git diff --name-only
913600f471d8fb0fb5345bdf668ca39ec1faf4d8..b1e5d1394daf14e1ba8a749ad6721dbaf87bf695`
contains 60 paths. They comprise three 0501 plans, one 0501 design, and this
report; Monitor metadata, product modules, legacy deletions, and tests; and the
bounded Toolkit observation/probe/typed-debug bridge and tests.

`b1e5d1394daf14e1ba8a749ad6721dbaf87bf695` is the stable product/test head that
completes the exact 160 MiB amendment. This subsequent report-only correction
does not change product scope.

The post-review correction commits add these exact behaviors:

- atomic Monitor probe connect/release lifecycle transitions and deterministic
  concurrency regressions;
- retention caller-timeout margin without removing bounded work, cancellation,
  chunking, or storage-busy mapping;
- JSONL and CSV value flattening through public `flatten_history_page`, with one
  flattened value per JSONL line; and
- an exact 160 MiB artifact cap within the unchanged 512 MiB workspace quota,
  realistic lossless 100,000-value JSONL/CSV regressions, controlled overflow
  cleanup, bounded buffering, public query pagination with one-page prefetch,
  batch-static JSONL prefix reuse, and a bounded transient verification cache;
- per-write path/directory/file/schema/workspace/WAL/size/descriptor checks with
  validated dev/inode pinning and fingerprint/data-version-bound quick-check
  amortization; and
- durable 3-warmup plus 20-measurement performance acceptance tests.

No collaboration app, CI workflow, manifest, validator, browser bundle, second
backend, or 0502 UI asset was added.

## 3. Complete Monitor suites and coverage

Environment: Windows `win32`, CPython 3.12.13 and 3.10.11. Both commands used
the code-head worktree sources, a repository-external basetemp and coverage data
file, disabled pytest caching, and prevented repository bytecode writes.

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-0501-monitor-service\tools\stm32-monitor\src;C:\tmp\stm32tk-0501-monitor-service\tools\stm32-toolkit\src'
$env:COVERAGE_FILE='C:\tmp\stm32tk-0501-task4-312-rerun.coverage'
$env:PYTHONDONTWRITEBYTECODE='1'
C:\tmp\stm32-toolkit-review-py31213\Scripts\python.exe -m pytest tools\stm32-monitor\tests -q --ignore=tools\stm32-monitor\tests\test_performance.py --basetemp C:\tmp\stm32tk-0501-full312-final-basetemp -p no:cacheprovider --cov=stm32_monitor --cov-branch --cov-report=term --cov-fail-under=90

$env:COVERAGE_FILE='C:\tmp\stm32tk-0501-task4-310-12c8f98.coverage'
C:\tmp\stm32tk-0301-py310\Scripts\python.exe -m pytest tools\stm32-monitor\tests -q --ignore=tools\stm32-monitor\tests\test_performance.py --basetemp C:\tmp\stm32tk-0501-full310-final-basetemp -p no:cacheprovider --cov=stm32_monitor --cov-branch --cov-report=term --cov-fail-under=90
```

- Python 3.12.13: `378 passed in 244.14s`; total branch-aware coverage `91.01%`.
- Python 3.10.11: `378 passed in 238.60s`; total branch-aware coverage `91.01%`.
- After the independent-review TOCTOU correction, the exact changed files plus
  runtime/service direct consumers passed `190 passed in 83.95s`; complete
  `test_storage.py` separately passed `42 passed in 2.45s`.

| Monitor module | 3.12 coverage | 3.10 coverage |
| --- | ---: | ---: |
| `__init__.py` | 100% | 100% |
| `__main__.py` | 100% | 100% |
| `auth.py` | 96% | 96% |
| `cli.py` | 100% | 100% |
| `exports.py` | 91% | 91% |
| `groups.py` | 93% | 93% |
| `history.py` | 90% | 90% |
| `models.py` | 91% | 91% |
| `probe_session.py` | 92% | 92% |
| `protocol.py` | 94% | 94% |
| `runtime.py` | 90% | 90% |
| `sampler.py` | 91% | 91% |
| `service.py` | 90% | 90% |
| `storage.py` | 91% | 91% |

Every Monitor product module meets the required 90% branch-aware threshold.
The first sandboxed 3.12 attempt was invalid because the sandbox denied external
pytest/coverage writes; it produced 284 setup errors and a coverage database
error. It is not product evidence and was replaced by the successful authorized
rerun above.

## 4. Complete Toolkit regression suite

Mechanical enumeration used:

```powershell
$files=@(rg --files tools/stm32-toolkit/tests -g 'test_*.py' | Sort-Object)
$assigned=@()
for($shard=0;$shard -lt 8;$shard++){
  for($index=$shard;$index -lt $files.Count;$index+=8){
    $assigned += $files[$index]
  }
}
```

It proved `EXPECTED=45`, `ASSIGNED=45`, and `UNIQUE=45`. Each disjoint shard ran
with CPython 3.12.13, the same Monitor/Toolkit source `PYTHONPATH`,
`PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`, and a distinct external
`--basetemp C:\tmp\stm32tk-0501-task4-toolkit-sN`.

| Shard | Test files | Outcome |
| --- | --- | ---: |
| 1 | build-map, detection, identity, migration-plan, probe-protocol, result | 192 passed |
| 2 | build-runner, doctor, keil-baseline, monitor-observation, probe-service, sampling | 231 passed, 1 skipped |
| 3 | CLI, DWARF, Keil-inspect, paths, probe-supervisor, setup-runtime | 245 passed |
| 4 | hardware CLI, fault, hardware MCP, planned-actions, process, SVD | 231 passed |
| 5 | context, firmware-identity, MCP migration/build, plugin-layout, project, workflows | 265 passed, 1 skipped |
| 6 | debug-firmware, flash, MCP roots, probe-backend, project-model | 293 passed, 2 skipped |
| 7 | debug-handoff, generation, MCP server, probe-client, project-upgrade | 473 passed |
| 8 | debug-read, hardware-workflows, migration-apply, probe-lease, PyOCD-backend | 209 passed |

Total: `2,139 passed, 4 skipped`, zero failures. A fresh four-node `-rs` rerun
recorded the existing skip reasons:

- `test_monitor_observation.py::test_real_supervisor_thread_swap_after_identity_check_writes_no_replacement_state` — Windows directory handles deny rename;
- `test_project.py::test_source_symlink_cannot_escape_canonical_project_root` — symbolic links unavailable;
- `test_project_model.py::test_file_symlink_cannot_escape_project_root` — symbolic links unavailable; and
- `test_project_model.py::test_directory_symlink_parent_cannot_escape_project_root` — symbolic links unavailable.

## 5. Performance amendment completion

The old report cited
`.superpowers/sdd/2026-08-08-stm32tk-0501-ui-ready-monitor-contracts/task6_benchmark.py`.
`git check-ignore -v` proves that path is ignored, and `git ls-files` proves it is
absent from the reviewed commit. Its old min/median/p95/max, fixture, database,
and memory numbers have therefore been removed from durable acceptance evidence.

A fresh pre-amendment diagnostic ran:

```powershell
$env:PYTHONPATH='C:\tmp\stm32tk-0501-monitor-service\tools\stm32-monitor\src;C:\tmp\stm32tk-0501-monitor-service\tools\stm32-toolkit\src'
$env:STM32TK_BENCH_ROOT='C:\tmp\stm32tk-0501-task4-bench-old'
C:\tmp\stm32-toolkit-review-py31213\Scripts\python.exe .superpowers\sdd\2026-08-08-stm32tk-0501-ui-ready-monitor-contracts\task6_benchmark.py
```

It failed at its first 100,000-value flattened JSONL export with
`MONITOR_EXPORT_TOO_LARGE: export byte limit was exceeded`. The user then stated
`批准将导出上限调整为 160 MiB 后续你自主确认就行`, explicitly approving an exact
160 MiB production artifact ceiling and autonomous downstream confirmation.

The amendment suite provides these durable assertions:

- the realistic 100,000-value JSONL/CSV regression compares all values and stable
  evidence by a collision-resistant digest, proves no pagination gaps or
  duplicates, and produces artifacts greater than 64 MiB but below 160 MiB;
- `test_jsonl_export_paginates_flattened_values_under_the_production_cap` proves
  lossless 20,000-value JSONL pagination through `flatten_history_page`;
- the controlled 32-byte-cap regression proves `MONITOR_EXPORT_TOO_LARGE` leaves
  neither artifact nor pending database record;
- the production quota regression proves exactly three `160 MiB + 16 KiB`
  reservations fit within 512 MiB and the fourth is rejected without corrupting
  the reservation ledger;
- the uncached verified-query regression proves exports retain no verified batch
  cache while ordinary cold/warm queries retain their existing cache behavior;
- `test_ten_thousand_value_query_normalizes_and_serializes_final_page_once`
  proves exact 10,000-value, <=4 MiB bounded query structure; and
- `test_retention_chunks_one_hundred_thousand_values_within_live_deadlines`
  asserts retention `<2 s` and sampler ticker gaps `<100 ms`.

The committed named acceptance command ran on CPython 3.12.13/Windows 11 with
three warmups and twenty measured runs and passed `2 passed in 320.66s`:

- fixture SHA-256
  `8863eb6dcc540e41b945cf60614ab252b2a5b1011045ee55425316e79640a0ce`,
  database 43,974,656 bytes, artifact exactly 121,051,826 bytes;
- append-256 min/median/p95/max
  `27.3045/29.4128/30.3309/30.6097 ms` (`<50 ms`);
- query-10,000 min/median/p95/max
  `75.2815/77.1200/78.5969/81.1914 ms` (`<100 ms`), serialized size
  1,431,097 bytes;
- export-100,000 min/median/p95/max
  `4625.4868/4697.96825/4745.2961/4758.9131 ms` (`<5 s`), with traced peak
  38,766,698 bytes (`<64 MiB`);
- retention p95 `227.5737 ms`, exactly two batches per bounded pass, sampler
  ticker maximum gap `16.5801 ms`;
- aiohttp bootstrap p95 `0.4803 ms` and status p95 `0.4016 ms`.

The separate export-only run also passed with p95 `4669.5824 ms`, maximum
`4703.1546 ms`, and traced peak 38,773,244 bytes. No performance blocker remains.

Independent review found one validation-to-cache TOCTOU: a fingerprint changed
after quick-check could have been cached without validation. A deterministic RED
proved the gap. The final implementation performs WAL/sidecar setup before the
validation fingerprint, caches only a validation-stable fingerprint, pins the
first validated main dev/inode, and uses `total_changes` so internally committed
writes refresh trust while truly read-only `try_write` calls retain their strict
deadline. The reviewer found no other issue.

## 6. Wheels and installed-package smoke

`git archive` created a clean repository-external source tree from exact code
head. CPython 3.12 then built both wheels with isolated build requirements:

```powershell
C:\Users\ZhangYang\AppData\Roaming\uv\python\cpython-3.12-windows-x86_64-none\python.exe -m pip wheel --no-deps --wheel-dir C:\tmp\stm32tk-0501-task4-package-12c8f98\wheels C:\tmp\stm32tk-0501-task4-package-12c8f98\source\tools\stm32-toolkit
C:\Users\ZhangYang\AppData\Roaming\uv\python\cpython-3.12-windows-x86_64-none\python.exe -m pip wheel --no-deps --wheel-dir C:\tmp\stm32tk-0501-task4-package-12c8f98\wheels C:\tmp\stm32tk-0501-task4-package-12c8f98\source\tools\stm32-monitor
```

| Wheel | Bytes | SHA-256 |
| --- | ---: | --- |
| `stm32_monitor-0.4.0-py3-none-any.whl` | 71,184 | `150b36b55a9410243879d22fd74f44a49cf8b84314d65332c3f498188e9b1b41` |
| `stm32_toolkit-0.4.0-py3-none-any.whl` | 235,282 | `04639e1367aab63d38e1ad83a8a853ed310e9b6754ae101540207a1692144ce4` |

Fresh CPython 3.12.13 and 3.10.11 venvs installed both wheels from an external
working directory with `pip install --no-index --no-deps`. The same 14 committed
nodes exercised zero-group CRUD, CAS update/delete, fake observation and
sampling, immutable history, flattened JSONL/CSV, verified download, dynamic
REST loopback/status, WebSocket backpressure, probe/runtime dispatch, and
cancellation cleanup:

- Python 3.12: `14 passed in 7.73s`.
- Python 3.10: `14 passed in 6.91s` after correcting a test-harness-only missing
  `tomli` support path; the first launch collected no tests.

Both imports resolved to their new venv `site-packages`. Each inventory contained
exactly 37 Monitor and 133 Toolkit distribution records. Monitor `Requires-Dist`
was exactly `stm32-toolkit==0.4.0` and `aiohttp>=3.9,<4`; root observation exports
did not load PyOCD; and legacy `config`, `elf_parser`, `poller`, `pyocd_session`,
`sse_server`, and `svd_parser` modules were absent.

## 7. Static, filesystem, and Windows evidence

- CPython 3.12 and 3.10 `compileall -q` passed for both product source trees with
  `PYTHONPYCACHEPREFIX` under the external package root.
- `git diff --check
  913600f471d8fb0fb5345bdf668ca39ec1faf4d8..b1e5d1394daf14e1ba8a749ad6721dbaf87bf695`
  passed.
- Product scans found no direct Monitor PyOCD/CMSIS-SVD/PyYAML import or
  dependency, default group, PyOCD process-kill behavior, non-loopback bind,
  plaintext credential literal, or project-root mutation pattern.
- Before document edits, only the ignored SDD evidence remained outside Git;
  the base-to-code-head inventory contained exactly 60 paths.
- A fresh installed-wheel scenario proved project bytes, names, mtimes, modes,
  and Git porcelain unchanged across `groups.list`, start, status, probe connect,
  variable catalog, history query, and stop.
- A focused Windows run passed five nodes covering a real NTFS junction rejection,
  persistent SQLite WAL visibility/revalidation, same-workspace runtime locking,
  dynamic IPv4 loopback, and repeated cancellation cleanup.

## 8. Deferred platform evidence

| Status | Named owner | Evidence |
| --- | --- | --- |
| DEFERRED | Linux owner | Complete Monitor 3.10/3.12, complete Toolkit, package/install, project immutability, SQLite lock/WAL, loopback, and cancellation behavior on Linux. |
| DEFERRED | 0.5 release-gate physical-board owner | Exact-probe OBSERVE lifecycle, typed DWARF/register sampling, probe isolation/busy behavior, provenance changes, reconnect, and cancellation on a supported physical board/probe. |

The export and append timing failures are non-platform blockers and are not
deferred. No pure-code failure is hidden under a platform deferral.

## 9. Task 4 checklist

- [x] Accepted base and stable code head before the report commit are recorded.
- [x] Complete dual-Python Monitor suites and branch-aware module coverage passed.
- [x] All 45 Toolkit test files ran in mechanically complete shards.
- [x] Both wheels built, installed fresh on both interpreters, and passed installed smoke/inventory checks.
- [x] Static, dependency, credential, scope, project-immutability, and locally owned Windows gates passed.
- [x] Ignored/absent benchmark PASS claims and stale final acceptance language were removed.
- [x] Exact 160 MiB cap, 512 MiB quota arithmetic, realistic 100,000-value
  JSONL/CSV losslessness, overflow cleanup, and `<64 MiB` traced memory are proven.
- [x] Export `<5 s`, append p95 `<50 ms`, query, memory, retention/ticker, and
  aiohttp bootstrap/status named performance gates pass as detailed above.
- [ ] Fresh final-head independent review and final verdict remain assigned to Task 5.
- [ ] Linux and physical-board evidence remain deferred to their named owners.
- [ ] Push/PR/ready/merge/close/delete remains unperformed and requires explicit user authorization.
