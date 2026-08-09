# STM32TK-0501 Monitor Service Evidence Reconciliation

## 1. Status and ledger

- Module: `STM32TK-0501-MONITOR-SERVICE`
- Phase: Codex revision Task 6, partial 160 MiB export-cap amendment
- Specification/architecture owner: Codex
- Implementation owner for this revision: Codex-created task agents, as authorized
  by `docs/superpowers/plans/2026-08-09-stm32tk-0501-codex-revision.md`
- Evidence implementer: Codex Task 6 agent
- Final reviewer/verdict owner: Codex Task 5 controller and fresh independent reviewer
- Branch: `codex/STM32TK-0501-MONITOR-SERVICE`
- Accepted base: `913600f471d8fb0fb5345bdf668ca39ec1faf4d8`
- Stable code head before this report-only correction commit:
  `ec4b6b4a95fa09d0826ceaaff7f49045db695f20`
- Remote action authorized for Task 6: none

Task 6 does not issue a final review verdict. The user explicitly approved the
exact 160 MiB production artifact ceiling. Functional 100,000-value JSONL/CSV
evidence and the separate `<64 MiB` traced-memory gate now pass, but export `<5 s`
and append p95 `<50 ms` remain open non-deferred failures. A fresh final-head
independent review also remains assigned to Task 5.

No push, PR mutation, ready/merge/close operation, or remote branch deletion was
performed.

## 2. Accepted-base-to-code-head scope

`git diff --name-only
913600f471d8fb0fb5345bdf668ca39ec1faf4d8..ec4b6b4a95fa09d0826ceaaff7f49045db695f20`
contains 59 paths. They comprise three 0501 plans, one 0501 design, and this
report; Monitor metadata, product modules, legacy deletions, and tests; and the
bounded Toolkit observation/probe/typed-debug bridge and tests.

`ec4b6b4a95fa09d0826ceaaff7f49045db695f20` is the safe-subset product/docs
commit that implements and records the exact 160 MiB amendment. This subsequent
report-only correction does not change that product scope.

The post-review correction commits add these exact behaviors:

- atomic Monitor probe connect/release lifecycle transitions and deterministic
  concurrency regressions;
- retention caller-timeout margin without removing bounded work, cancellation,
  chunking, or storage-busy mapping;
- JSONL and CSV value flattening through public `flatten_history_page`, with one
  flattened value per JSONL line; and
- an exact 160 MiB artifact cap within the unchanged 512 MiB workspace quota,
  realistic lossless 100,000-value JSONL/CSV regressions, controlled overflow
  cleanup, buffered encoding, and an export-only uncached verified query mode.

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
C:\tmp\stm32-toolkit-review-py31213\Scripts\python.exe -m pytest tools\stm32-monitor\tests -q --basetemp C:\tmp\stm32tk-0501-task4-312-basetemp-rerun -p no:cacheprovider --cov=stm32_monitor --cov-branch --cov-report=term --cov-fail-under=90

$env:COVERAGE_FILE='C:\tmp\stm32tk-0501-task4-310-12c8f98.coverage'
C:\tmp\stm32tk-0301-py310\Scripts\python.exe -m pytest tools\stm32-monitor\tests -q --basetemp C:\tmp\stm32tk-0501-task4-310-basetemp -p no:cacheprovider --cov=stm32_monitor --cov-branch --cov-report=term --cov-fail-under=90
```

- Python 3.12.13: `363 passed in 174.71s`; zero failures, skips, or xfails;
  total branch-aware coverage `91.25%`.
- Python 3.10.11: `363 passed in 197.09s`; zero failures, skips, or xfails;
  total branch-aware coverage `91.26%`.

| Monitor module | 3.12 coverage | 3.10 coverage |
| --- | ---: | ---: |
| `__init__.py` | 100% | 100% |
| `__main__.py` | 100% | 100% |
| `auth.py` | 96% | 96% |
| `cli.py` | 100% | 100% |
| `exports.py` | 91% | 91% |
| `groups.py` | 93% | 93% |
| `history.py` | 91% | 91% |
| `models.py` | 91% | 91% |
| `probe_session.py` | 92% | 92% |
| `protocol.py` | 94% | 94% |
| `runtime.py` | 91% | 91% |
| `sampler.py` | 91% | 91% |
| `service.py` | 90% | 90% |
| `storage.py` | 92% | 92% |

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

## 5. Performance amendment and remaining blockers

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

The representative JSONL artifact is 121,051,826 bytes. After the export-only
uncached mode, `tracemalloc` measured a 14,937,459-byte peak and zero retained
verified batches, so the independent `<64 MiB` memory requirement passes. The
best current untraced create-plus-verification diagnostic is 5.8381 s, above
`<5 s`. Five untraced pre-buffer/encoder runs ranged from 6.6972 to 6.9388 s.
The append call-only p95 is 210.8441 ms against `<50 ms`; profiling attributes
the dominant time to per-write SQLite preflight/integrity work. The export timing
and append timing failures remain open and non-deferred. The uncommitted complete
performance candidate is failing and is not presented as durable PASS evidence.

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
  913600f471d8fb0fb5345bdf668ca39ec1faf4d8..ec4b6b4a95fa09d0826ceaaff7f49045db695f20`
  passed.
- Product scans found no direct Monitor PyOCD/CMSIS-SVD/PyYAML import or
  dependency, default group, PyOCD process-kill behavior, non-loopback bind,
  plaintext credential literal, or project-root mutation pattern.
- Before document edits, `git status --porcelain=v2 --untracked-files=all` was
  empty; the base-to-code-head inventory contained exactly 59 paths.
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
- [ ] Export `<5 s` and append p95 `<50 ms` remain blocked as detailed above.
- [ ] Fresh final-head independent review and final verdict remain assigned to Task 5.
- [ ] Linux and physical-board evidence remain deferred to their named owners.
- [ ] Push/PR/ready/merge/close/delete remains unperformed and requires explicit user authorization.
