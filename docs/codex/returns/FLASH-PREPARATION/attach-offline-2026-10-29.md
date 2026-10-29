# FLASH-PREPARATION — offline attach follow-up

Date: 2026-10-29. Verdict: **OFFLINE_CHECKS_PASS_PHYSICAL_CAUSE_UNRESOLVED**.

The 16 selected existing tests pass. The original physical attach timeout is still
unresolved, and the pre-program reset/halt change has no successful physical
validation. Overall status remains **SOFTWARE_COMPLETE_HARDWARE_PENDING**.
The failed [single physical attempt](hardware-validation-2026-10-28.md) is retained.

## Scope and ownership

- Accepted source/report base and execution HEAD before this report:
  `fa7b2547f657ffd3faa74f9af34d30e0925ecf5b`, clean isolated branch
  `codex/v135-flash-preparation`.
- Accepted product CodeHead remains `1bb95790dbe1552b700f588d56e5ef9301b839a2`.
  Product/version metadata is unchanged: Unreleased, planned v1.3.5, metadata 1.3.4.
- Worktree: `C:/Users/zhy76/.codex/worktrees/v135-flash-preparation/STM32-Toolkit`.
- Primary Codex owns investigation, bounded orchestration, independent source and
  execution-evidence review, acceptance and this procedure checkpoint. Local Claude
  Code CLI ran the delegated verification with its existing
  `deepseek-v4.1-flash[1m]` route. No implementation subagent or provider change.
- The user requested continued testing. The previous single physical authorization
  is consumed, so this continuation was explicitly limited to offline work. No
  probe enumeration, target connection/control/read/programming, firmware rebuild,
  installed-runtime change, installation or remote action was performed.
- The standard procedure, current checkpoint and latest execution report were read
  before planning these checks. There was no product/test implementation task and
  no product/test change. The clean existing worktree was reused for verification.

## New source findings

Initial Windows worker startup has a separate admission boundary: the child sends
its ready handshake after constructing the backend (`probe/worker.py:288`), and
the parent awaits it (`:407`). `probe/supervisor.py:99-121` creates that worker
before starting the service; the workflow creates the client and calls attach only
after supervisor start returns. Thus the previous `service-attach-deadline` is
after successful initial worker startup. The earlier physical report's broad
process-startup possibility is narrowed by this ordering; later IPC/scheduling
delay is not excluded.

PyOCD driver imports remain lazy (`probe/pyocd_backend.py:519-523`), on the attach
path through probe selection/enumeration (`:1001`). Probe enumeration, Session
creation/open, target identity and HALTED verification can still contribute to the
attach duration. The normal hardware workflow uses the default `ProbeClient`
(`hardware_workflows.py:241`), whose attach budget is 5,000 ms
(`probe/client.py:268`). Monitor has its own explicit 35,000 ms budget
(`monitor_observation.py:69,134`); that separate contract is not authority to change
the normal flash deadline. The service's terminal wait remains one second.

The previous response has `lateAttach=null` and `lastVerifiedTargetState=null`.
It does not identify which internal attach stage was incomplete when the owned
worker was aborted. Policy fields such as `preProgramReset=sysresetreq` still do
not prove that preparation executed.

## Executed offline checks

Verified interpreter: `D:/codex-tmp/kx23/venv/Scripts/python.exe`, Python 3.12.14,
pyOCD 0.45.1. Evidence root: `D:/codex-tmp/f135-attach-20261029`.
The exact three native PowerShell commands are preserved in `verify-task.json`
and `verify-run/task.json`; every command executed once, sequentially.

| Owner / evidence | Check | Result |
| --- | --- | --- |
| Claude / cw1 | Existing spawned fake-worker cooperative timeout settlement and unresponsive-worker bounded abort | 2 passed, subprocess exit 0; 8.75 s pytest, 12.12 s runner |
| Claude / cc1 | Existing default/explicit attach budget encoding and validation, simulated attach beyond five seconds on Monitor, late diagnostic retention, public cleanup success/failure merging | 14 passed, subprocess exit 0; 8.67 s pytest, 9.79 s runner |
| Claude / driver-import.json | One fresh-process module and driver-class dependency import; ordinary diagnostic, not a test | Matched native terminal success; no probe enumeration or Session construction requested |
| Primary / reconciled.json | Native command/tool audit, fresh JUnit/hash/case reconciliation, all recorded tracked-source hashes compared with the clean execution HEAD | 16 distinct passing cases; no failure/error/skip; evidence and source unchanged |

The dispatcher recorded exact native PowerShell inventory in each startup/main
stage, a matched harmless startup smoke, all three listed commands and both
designated test commands. CLI exit was 0; no denied/absent tool, unexpected
command, scope violation, retry or pending result occurred. Native numeric command
exit fields were absent and remain **null**. The two actual pytest subprocess
exits are separately recorded as 0. An ordinary diagnostic does not become a test
pass merely because it completed. Primary reconciled external JUnit independently;
the dispatcher's empty JUnit path list supplies no JUnit freshness proof itself.

The inherited source-bound runner records its base pytest argv before the
selection wrapper appends `-k`. The exact filter is therefore bound by the hashed
`run_selected.py` and checked against all JUnit case identities; `reconciled.json`
labels the effective argv as derived from that wrapper, not directly captured.
Only these selected tests ran (62 and 318 other cases were deselected). This is
not a new full matrix, release qualification or additional hardware evidence.

## Import measurement and interpretation

The fresh process imported the candidate backend module in **0.683 s**, then
constructed `_DefaultPyOCDDriver` to load its dependency classes in **0.964 s**;
total **1.647 s**. That constructor does not call probe enumeration, construct/open
a Session or perform target control. Primary inspected the constructor and plugin
loading before dispatch. Product backend-module import occurs before the worker
ready handshake, so only the lazy driver dependency portion is directly relevant
to that part of the attach deadline.

This measurement did not reproduce a driver import lasting five seconds. It is
one fresh Python process with uncontrolled OS cache/load, not a reconstruction of
the previous worker. It neither proves nor excludes an earlier import delay and
does not measure enumeration or Session/target initialization. No timeout was
extended, no default frequency changed and no physical failure was relabeled PASS.

The next useful evidence is bounded stage/timing capture within one normal
attachment: lazy driver loading, enumeration, Session creation/open, identity and
HALTED verification. Its capture entry needs a scoped design and offline review
before another explicitly authorized physical operation. The current test results
do not authorize that connection or another flash. Packaging, recovery behavior,
application execution and complete physical/release qualification remain pending.

## Evidence integrity

| Artifact under evidence root | SHA-256 |
| --- | --- |
| reconciled.json | 9329f16520ed1a70c25eaf6af767f124a0eaa2f113f3d78b02fee02b98973d0c |
| driver-import.json | 9a2ca389ca6ac4da298d3cec2379b9d4f0cb482afa129c2d1fe5b8da50bb2c9a |
| verify-run/summary.json | 70b455287b7df66515f0a1aed5cd155ba10ef6dfaeeec8f069565ffa1850dffc |
| run_selected.py | 79f8d990b0be7046c0cdf0533a3ac5af292d94c1595bf1731b9f662545f9e46e |
| measure_driver_import.py | c1aed0b8dcd13482beb4ce24504cb0eef9db8af0495467cd3bd4dbeaf88c48e5 |

Raw inventory/smoke/main streams, command inputs, two test executions/JUnit/logs,
source hashes, profile and coordinator reconciliation remain external. This report
and the result-only standard-procedure checkpoint are the only new tracked changes;
they require no repeat hardware or software matrix.
