# ATTACH-PROGRESS implementation and acceptance plan

Accepted base: `e4d9118e1c83f139db2959acbd4076a357c37992`.
Branch: `codex/v135-attach-progress`; clean isolated implementation worktree:
`C:/Users/zhy76/.codex/worktrees/v135-attach-progress/STM32-Toolkit`.
No PR or remote action authorized. No ownership exception. Primary owns design,
orchestration, complete-diff review and acceptance; local Claude Code CLI owns all
product/test/guide/Changelog changes, using the configured model/provider route.

Governing [design](../specs/2026-10-29-attach-progress-design.md) reflects the explicit
user scope. The standard procedure/current checkpoint/latest attach-offline report
were read before this plan. Its old runtime/hardware failure is retained. The
documentation development guide's old Codex-subagent sentence is superseded by the
current user/global/project Claude CLI ownership instruction; do not edit that
unrelated guide or change active projects.

## Implementation, one bounded slice

1. Freeze this plan and design at the base. Verify actual Claude edit inventory
   through the existing dispatch entry. File-only edit invocation, no shell or
   execution requirements, no retries. Keep exact write files below and bounded
   related-module Read/Grep/Glob. Return normal text, exact changed files and limits.
2. Claude adds the closed progress helper/optional diagnostic field, backend callback,
   bounded worker IPC/metadata ownership and service timeout attachment. Claude adds
   deterministic tests and short user-facing guide/Unreleased Changelog guidance.
3. Primary reviews all changes before freezing a code checkpoint; correctable findings
   return to Claude on this same slice. A review-fix is a separately bounded task,
   not a retry of a failed invocation. No bypass/fallback on CLI or permission failure.
4. Separate Claude verify dispatch with verified Python/native PowerShell and only
   coordinator-supplied single commands. Fresh inventory plus real harmless smoke
   are mandatory. Split tests below foreground limits; nonterminal calls are pending,
   worker finishes, Primary reconciles existing evidence without rerunning. No retries.
5. Primary reviews the complete accepted-base-to-final-code diff in a clean exact-head
   review checkout and independently runs all new cases plus targeted integration.
   Reconcile real native events, exact commands/source/JUnit freshness and counts;
   keep execution, passing and ordinary checks separate. Preserve failures.
6. Primary writes docs/codex/returns/ATTACH-PROGRESS/implementation-report.md and the
   standard-procedure checkpoint after review. Record CodeHead before report commit,
   not its own SHA. No hardware qualification or publication claim.

Allowed implementation writes (exact files):

- tools/stm32-toolkit/src/stm32_toolkit/probe/attach_progress.py (new)
- tools/stm32-toolkit/src/stm32_toolkit/probe/attach_diagnostics.py
- tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py
- tools/stm32-toolkit/src/stm32_toolkit/probe/worker.py
- tools/stm32-toolkit/src/stm32_toolkit/probe/service.py
- tools/stm32-toolkit/tests/test_attach_progress.py (new)
- tools/stm32-toolkit/tests/test_probe_worker.py (only affected fixtures/assertions)
- docs/user-guide.md
- CHANGELOG.md

The existing guide path was verified before dispatch. Read scope
includes AGENTS, this spec/plan, the probe module/model/protocol/client/authorization
helpers, shared hardware/Monitor/public result models, their tests/fixtures, existing
guide/Changelog and latest attach report. No credentials, installed-source discovery,
unrelated projects, global settings, runtime or firmware inputs.

## Verification layers

| Layer | Owner/environment | Required evidence |
| --- | --- | --- |
| Pure schema/callback/new unit cases | Claude then Primary; verified existing Python3.12 venv, fake driver only | strict validation/copies, compatibility, stage order/zero extra control |
| Real IPC and service | Claude then Primary; Windows native owned spawn/fake backend/local loopback | timeout snapshots survive abort, bounded message/refusal/deadline, token isolation |
| Affected regression | Claude; same clean source/runtime, serial deadline-sensitive groups | adapter, diagnostics/worker, service, client, hardware workflow, flash, Monitor and guide contracts |
| Independent integration/diff | Primary; clean exact final code head | all new tests plus targeted service/flash/public path and full diff, no actionable findings |
| Physical/release | Primary in separately authorized later qualification phase | PENDING; no hardware, packaging, install or remote authority in this plan |

Use `D:/codex-tmp/ap135` for distinct short temp/cache/report/coverage/evidence paths.
Interpreter: `D:/codex-tmp/kx23/venv/Scripts/python.exe` (verified existing file);
dispatch interpreter: `C:/Users/zhy76/AppData/Local/Programs/Python/Python312/python.exe`.
Source-bound runners record complete actual pytest argv including filters before
launch, owner, exact HEAD/tracked hashes, real subprocess exit and fresh JUnit;
same-tree PYTHONPATH, guarded main and no device API are mandatory. No dependencies
are installed. Required command lists are frozen in each verify task after source
review/test discovery; unlisted commands remain unauthorized.
