# STM32TK-0402-PYOCD-BACKEND Implementation Report

## Delivery identity

- Status: `IMPLEMENTED`
- Accepted product base: `8e16c4bef4fe52b29e8edea501e6b4d5bed37ff4`
- Plan commit: `35ec373a2f32750c8225324711c05b407b488b34`
- Initial adapter commit: `65f1ea637a4f47183c3d40fe36deae51b6f2f012`
- Branch: `codex/STM32TK-0402-PYOCD-BACKEND`
- Code head before this report commit:
  `56e3845a6682ae1fb8e521eae01228b9ee9ecdf5`
- Specification, implementation, and review owner: Codex, following the user's
  explicit pause of OpenClaw implementation after STM32TK-0306.

This report intentionally does not contain the final commit SHA that contains
the report itself. The pull-request URL and final remote head are returned out
of band after the report commit is pushed.

## Delivered scope

The code head changes exactly 10 plan, product, and test paths relative to the
accepted base (1,798 insertions and 1 deletion):

- lazy `PyOCDBackend` with no PyOCD import during ordinary
  `stm32_toolkit.probe` import;
- deterministic passive probe enumeration without reading
  `associated_board_info`, because the CMSIS-DAP implementation may open USB
  merely to populate that property;
- exact, case-sensitive full probe-ID selection; malformed, partial,
  wildcard-like, missing, and duplicate-exact IDs fail with stable codes;
- explicit target selection with one-core enforcement and fixed safety options:
  SWD, `connect_mode=attach`, `auto_unlock=false`, `no_config=true`, pack debug
  sequences disabled, primary core zero, no workspace user script, and no
  resume-on-disconnect state change;
- independently bounded memory/register requests, exact-length byte validation,
  item-scoped read errors, and no raw PyOCD exception serialization;
- core-register reads only when the target is already halted; the backend never
  halts implicitly in an observation request;
- failed partial-open cleanup directly closes a probe still reported open;
  failed cleanup blocks replacement attach, and flash remains fail-closed until
  STM32TK-0403 supplies identity/authorization gates;
- frozen `ProbeServiceConfig` and `ProbeServiceSupervisor` with serialized,
  idempotent start/stop, restart, startup cleanup, async context management, and
  ownership of only its own backend/service objects;
- hardened `ProbeService.stop()` that removes endpoint state, cleans runner and
  tasks, releases its own lease, reaches an idempotent stopped state, and only
  then re-raises a backend-close failure;
- optional package extra `probe = ["pyocd>=0.45.1,<0.46"]`, plus deterministic
  PyOCD and supervisor test doubles and regressions.

No CLI/MCP flash/control command, Monitor dependency, target write API, process
termination path, Option Bytes, chip erase, or version bump was added.

## TDD and review corrections

Initial RED collection failed with
`ModuleNotFoundError: stm32_toolkit.probe.pyocd_backend`. Supervisor RED failed
with `ModuleNotFoundError: stm32_toolkit.probe.supervisor`. Focused RED/GREEN
slices then exposed and corrected the following defects before the final code
head:

1. partial/case-changed probe IDs could have been delegated to PyOCD's
   case-insensitive substring selector instead of exact adapter-side equality;
2. duplicate exact IDs had no ambiguity gate;
3. malformed/throwing hardware descriptor properties could leak raw errors;
4. passive board metadata access could temporarily open CMSIS-DAP hardware;
5. session options did not initially pin SWD/core selection or disable pack
   debug sequences;
6. PyOCD partial open can leave the probe open while `Session.close()` returns
   early; direct probe cleanup was added and tested;
7. swallowed close failure allowed a replacement Session to open, violating the
   one-session invariant;
8. a multi-core target silently inherited PyOCD's implicit primary core;
9. the initial fake allowed register reads from a running core although PyOCD
   requires a halted core; the adapter now reports structured unavailability
   and proves it never calls `halt()`;
10. a backend-close exception originally prevented endpoint and lease cleanup;
11. public package imports did not expose the adapter and supervisor contracts;
12. the initial full coverage command used a 603-second external timeout, below
    the suite's measured instrumented duration. A no-coverage diagnostic full
    run completed in 459.94 seconds, and the unchanged coverage command then
    completed under a 20-minute external limit in 660.49 seconds.

Every product correction above was preceded by a focused failing regression and
was rerun GREEN. Agent-produced supervision changes were reviewed as a full diff
and independently rerun by the primary Codex agent.

## Verification evidence

Environment: Microsoft Windows 11 Pro 10.0.26200 build 26200, 64-bit, CPython
3.12.13, pytest 8.4.2, aiohttp 3.14.3, PyOCD 0.45.1.

| Gate | Result |
|---|---|
| Focused PyOCD/backend/supervisor/service/client suite | 120 passed, exit 0 |
| Full Toolkit suite without coverage | 1,386 passed, 3 skipped, 1,389 collected, exit 0; 459.94 s |
| Full Toolkit suite with branch coverage | 1,386 passed, 3 skipped, exit 0; 660.49 s |
| Full branch coverage | 91%, required minimum 90% |
| Changed module coverage | PyOCD backend 86%, supervisor 94%, service 85% |
| `compileall` | exit 0, silent |
| accepted-base/code-head `git diff --check` | exit 0, silent |
| changed production forbidden API scan | no process termination, subprocess, shell string, flash programmer, chip erase, Option Bytes, or raw-error serialization match |
| changed test suppression scan | no new skip/skipif/xfail |
| Unrelated-process survival | a real sleeping Python sentinel remained alive across supervisor start/stop |
| Persistent backend-close failure | endpoint removed, lease released/reacquired, stopped state idempotent, original failure re-raised |
| Ordinary package import | exports adapter/supervisor and imports no `pyocd` module |
| Installed PyOCD enumeration | PyOCD 0.45.1 returned zero probes as `()`; CLI reported `No available debug probes are connected` |
| Fresh external wheel `[probe]` install | offline install into a new CPython 3.12.13 venv passed; package loaded from `site-packages`, PyOCD 0.45.1 loaded, public exports loaded, enumeration returned `()` |

The final full coverage command was:

`python -m pytest tools/stm32-toolkit/tests -q --cov=stm32_toolkit --cov-branch --cov-report=term`

The three skips are pre-existing environment capability skips in
`test_project.py` and `test_project_model.py` because symbolic links are not
available to those fixtures. This packet added no skip or xfail. The one warning
is an existing third-party Pydantic Settings unresolved-forward-reference
warning from MCP server construction.

## Deferred and non-claimed evidence

- No physical debug probe was connected. Real attach/non-halting/memory-read
  evidence is `DEFERRED_TO_AVAILABLE_REAL_PROBE` and remains a named gate for
  `STM32TK-0405-CLI-MCP-RELEASE` and the non-skippable 1.0 board acceptance.
- Linux PyOCD/lease/path/cancellation behavior remains
  `DEFERRED_TO_STM32TK-0405-CLI-MCP-RELEASE`; no Windows observation is
  relabeled as Linux evidence.
- Flash identity, authorization, target-state restoration, and Cortex-Debug
  handoff belong to `STM32TK-0403-FLASH-HANDOFF`.
- No Monitor service or UI code is introduced before the 0.4 protocol and
  release integration packets are complete.

## Known limitations

- PyOCD 0.45.1 `Session.open()` in attach mode does not intentionally halt the
  target, but it necessarily enables the debug port and target implementations
  may initialize DBGMCU state. The adapter disables auto-unlock and pack debug
  sequences, pins SWD, and performs no explicit halt/reset/erase. It does not
  claim a physically side-effect-free debug connection.
- `resume_on_disconnect=false` preserves an already halted target instead of
  unexpectedly resuming it, but PyOCD may leave debug power/configuration
  enabled on close. Exact pre/post target-state restoration requires real-board
  evidence and is assigned to the 0403/0405 ownership gates.
- PyOCD target availability can depend on its managed CMSIS-Pack cache. This
  packet maps missing target/session setup to structured attach failure but does
  not bundle a device pack or claim a target without a real probe.
- PyOCD's in-process `Session` constructor executes `os.chdir(project_dir)`.
  Passing the current working directory prevents an intentional path change,
  and the Probe Service remains the sole Session owner, but PyOCD offers no
  option that removes the process-global call.
- Passive enumeration deliberately reports `boardName=null`; board identity is
  collected only after an exact probe owns an attached session in a later
  evidence path.

