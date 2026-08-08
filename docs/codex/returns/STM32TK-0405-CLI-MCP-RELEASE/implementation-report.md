# STM32TK-0405-CLI-MCP-RELEASE Implementation Report

## Delivery identity

- Status: `IMPLEMENTED` (Windows software packet; named external gates remain
  deferred)
- Accepted product base: `32a79a7b84b083b9c94a74357add71dcb7e2dea4`
- Initial plan commit: `2756641f977b755e084eab8cdcc25b83a22a9fbf`
- Architecture-correction plan commit:
  `259d7ab6cf66867ebfce692f680e4ea35acde055`
- Branch: `codex/STM32TK-0405-CLI-MCP-RELEASE`
- Code head before this report commit:
  `96966c461e7e11bff965027d8d498dd40ea5fd55`
- Specification, implementation, test, and review owner: Codex, using
  independent Codex subagents on disjoint paths under the user's explicit
  delegation authorization.

This report intentionally does not contain its own final commit SHA. The PR URL
and final remote head are returned after the report is pushed.

## Delivered scope

The code head changes 42 plan, product, Skill, fixture, and test paths relative
to the accepted base (6,525 insertions and 308 deletions):

- eight frozen project-bound asynchronous hardware workflows for bounded probe
  discovery, identity-pinned flash, debugger handoff begin/end, typed variable
  read/sample, SVD register read, and already-halted Fault analysis;
- strict request boundaries that derive target, optional SVD, ELF path, raw
  addresses, workspace, lease, endpoint, token, and operation level from the
  current project/runtime evidence rather than caller input;
- project-external runtime-root validation before any path or backend creation,
  plus deterministic per-probe hashed session roots so different probes can run
  concurrently without endpoint overwrite while the OS lease rejects same-probe
  overlap immediately;
- a durable digest-only global handoff reservation with exact
  probe/workspace/session/operation-level binding, crash-recoverable consumed
  tombstones, ticket replay rejection, transport-only client close, and
  cancellation-safe service/backend/native-thread draining;
- one stable nested JSON CLI grammar: `probe list`, `flash`,
  `debug handoff begin|end`, `read variable|sample|register`, and `fault`;
- exactly 15 FastMCP tools: the existing seven plus eight hardware tools, with
  server-owned roots/session, strict intrusive authorization, per-probe
  concurrency, complete `OperationResult` evidence, and exception sanitization;
- exactly seven thin Skills and one bundled MCP registration, adding
  `flash-firmware`, `debug-firmware`, and `read-var` without embedding hardware
  logic or accepting raw target/address/path overrides;
- package, plugin, CLI, launcher, managed runtime, fixtures, and English/Chinese
  documentation reconciled at version 0.4.0;
- managed runtime Bootstrap/Repair installs the local package with `[probe]`,
  validates PyOCD with PEP 440 range `>=0.45.1,<0.46` in the isolated runtime,
  treats an existing 0.3.0 runtime as broken, quarantines it, and atomically
  promotes 0.4.0 without an ambient-interpreter fallback.

This packet does not add Monitor persistence, groups, history, WebSocket/HTTP
service, desktop UI, target control, raw-address APIs, or a background hardware
daemon. Monitor implementation remains owned by STM32TK-0501 and 0502.

## TDD and independent review corrections

Initial RED runs failed because the unified hardware workflow, CLI, and MCP
surfaces did not exist. Later deterministic RED/review passes exposed and
corrected these material defects before acceptance:

1. session-local handoff state did not prevent another process from acquiring a
   probe already owned by an external debugger;
2. service stop could close a backend while an entered native observe task was
   still running, and client close still sent an authenticated close request;
3. handoff wrappers requested OBSERVE but the underlying contract required
   MODIFY, making the real default composition fail;
4. heartbeat, reserve, consume, and release could overwrite one another across
   native threads; cancellation could report failure after a ticket commit;
5. consumed handoff evidence and local state writes had crash windows that could
   make a ticket permanently unrecoverable or allow a successor to erase proof;
6. an OBSERVE reservation could initially be claimed as MODIFY because the
   operation level was not part of the exact ticket binding;
7. repeated cancellation could interrupt client/backend cleanup or close an
   enumeration backend while its native thread was still active;
8. workflow requests accepted a data root inside the project and all probes
   shared one endpoint record, causing project mutation and cross-probe overwrite;
9. arbitrary code-shaped exceptions could return backend messages, tokens, or
   absolute paths without sanitization;
10. the managed 0.4 runtime installed only the base package even though PyOCD is
    supplied by the `[probe]` extra;
11. early MCP concurrency tests used a fake active set and therefore did not
    prove the real per-probe lease/session behavior;
12. the first three new Skill files failed the accepted-base diff whitespace
    gate because of an extra blank line at EOF.

Every item has a regression that failed on its predecessor and passes on the
code head. The final independent review returned `ACCEPTED` with no remaining
P0/P1/P2 blocker.

## Verification evidence

Environment: Microsoft Windows 11 Pro 10.0.26200 build 26200, AMD64, CPython
3.12.13, pytest 8.4.2, pyelftools 0.33, aiohttp 3.14.3, and PyOCD 0.45.1 in the
fresh managed-wheel environment.

| Gate | Result |
|---|---|
| Final full Toolkit suite | 2,080 passed, 3 skipped, exit 0; 1,120.1 s |
| Full branch coverage | 91.48%, required minimum 90% |
| Hardware workflow focused | 54 passed; 90% branch coverage |
| CLI focused | 56 passed; 91% branch coverage |
| Hardware workflow + MCP focused | 144 passed; MCP server 93% branch coverage |
| Probe lifecycle regression | 392 passed before final closure; final five-file closure 239 passed |
| Plugin layout | 15 passed; exactly 7 Skills and 1 MCP registration |
| PowerShell runtime | 17 passed, including isolated probe-extra/version and 0.3-to-0.4 repair gates |
| Broad version-sensitive regression | 522 passed |
| `compileall` | exit 0, silent |
| accepted-base/code-head `git diff --check` | exit 0, silent |
| Suppression/credential/boundary scans | no new suppression, credential, raw hardware-control, process, network, or eager-PyOCD import path |
| Wheel | `stm32_toolkit-0.4.0-py3-none-any.whl`, 221,864 bytes |
| Wheel SHA-256 | `e778af68781968176338390f1a078d3870fda2033048135a8f02d6b7475406be` |
| Fresh external install | CPython 3.12.13; Toolkit 0.4.0; PyOCD 0.45.1 |
| External MCP inventory | exactly 15 expected tool names |
| External CLI fake-seam smoke | all 8 request types invoked from outside the repository |
| Ordinary installed import | `pyocdLoaded=false`; backend remains lazy |
| Physical discovery | bounded PyOCD discovery completed; 0 probes found |

The final full coverage command was:

`python -m pytest tools/stm32-toolkit/tests -q --cov=stm32_toolkit --cov-branch --cov-report=term --cov-fail-under=90`

The three skips are environment-capability skips for file symbolic links; real
Windows NTFS junction gates passed. This packet adds no skip, xfail, `noqa`,
coverage suppression, or type-ignore escape.

## Deferred and non-claimed evidence

- `claude plugin validate`, isolated marketplace add/install/list, and the
  Claude Code 0.3.0-to-0.4.0 plugin update are
  `DEFERRED_TO_ENV_WITH_CLAUDE_CODE`; no `claude` executable is installed or
  available on this host. Static plugin validation, exact inventories, launcher,
  and managed-runtime upgrade tests passed, but they are not relabeled as Claude
  Code CLI evidence.
- Linux path/lease/cancellation/PyOCD gates are
  `DEFERRED_TO_AVAILABLE_LINUX_HOST`; WSL is not installed on this Windows host.
- Real non-halting read, flash, external-debug handoff/reacquire, typed sample,
  register, and Fault smoke gates are `DEFERRED_TO_SELECTED_REAL_PROBE_BOARD`;
  the single bounded discovery run returned zero probes.
- The 0.4 software packet may merge and freeze the protocol for Monitor work,
  but the release-level 0.4 hardware/Linux/plugin checkboxes remain open until
  their named environments are available.

## Known limitations

- Hardware operations require an explicit supported probe, current project
  identity pins, and the managed `[probe]` runtime; no ambient backend fallback
  is attempted.
- Handoff tickets are one-time capabilities. Only their SHA-256 digests are
  persisted globally, and external ownership intentionally blocks ordinary
  Toolkit acquisition until the exact recovery transaction completes.
- Different probes use separate hashed session roots. Operations on one exact
  probe remain mutually exclusive through the OS-backed global lease.
- CLI/MCP read and Fault workflows remain observation-only. They never halt,
  resume, reset, write memory/registers, infer target/SVD/ELF paths, or accept
  arbitrary addresses.
- Persistent Monitor groups, sampling history, authenticated loopback streaming,
  and the desktop UI are not part of 0.4.0.
