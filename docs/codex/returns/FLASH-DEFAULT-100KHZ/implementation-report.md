# FLASH-DEFAULT-100KHZ execution and independent acceptance

2026-10-29 verdict: **SOFTWARE_COMPLETE_HARDWARE_PENDING**. The bounded
offline software slice is accepted after review corrections. Ordinary production
flash now defaults to 100 kHz; 1 MHz is an optional explicit configuration and
is no longer a required physical acceptance gate. This is not release acceptance
or evidence that the observed physical connection fault has been fixed.

## Source and ownership ledger

| Item | Recorded identity |
| --- | --- |
| Accepted base / diff origin | `4fe1be23d7b2c8a282757e1b8b45f73ee3484043` |
| Design/plan freeze | `389ffefd11f94cf07591aafa00e986f4f2f615c8` |
| Retained initial implementation candidate | `857b4814da526ea2293c5f9daeeeeed3ab093e88` |
| Final product/test CodeHead, before this report commit | `f55e95486fdec6e5cda8b9f25b70767a1f3ef1a4` |
| Branch | `codex/v135-flash-default-100k` |
| Implementation tree | `C:/Users/zhy76/.codex/worktrees/v135-flash-default-100k/STM32-Toolkit` |
| Clean independent review tree | `C:/Users/zhy76/.codex/worktrees/post134-independent-review/STM32-Toolkit` at exact final CodeHead |
| Specification, plan, orchestration, review and acceptance | Primary Codex |
| Product, tests and consumer guidance implementation | Local Claude Code CLI, unchanged configured `deepseek-v4.1-flash[1m]` route |
| Authority | Local offline implementation, tests, review and records only; no hardware, installation, packaging or remote mutation |

The governing [design](../../../superpowers/specs/2026-10-29-flash-default-100khz-design.md)
and [plan](../../../superpowers/plans/2026-10-29-flash-default-100khz-plan.md)
implement the user's explicit policy change. The stable dispatcher was
`C:/Users/zhy76/.codex/tools/claude-dispatch/dispatch.py`.
Source version metadata remains 1.3.4; this is an **Unreleased, planned v1.3.5
source candidate**. No installed runtime or global Skill was changed.

## Accepted behavior and boundaries

- `ProbeWorkerConfig` and `PyOCDBackend` production defaults are both 100,000 Hz.
  Shared normal Target programming inherits this default. Existing Monitor and
  under-reset profiles keep their own policies.
- An omitted public frequency remains `None` and preserves the supplied worker
  configuration. Production uses 100 kHz; an explicitly injected custom worker
  configuration, including 2 MHz, remains intact. An explicit public frequency
  still overrides the normal default within the existing integer
  100,000..50,000,000 Hz range. Validation ordering and recovery conflicts remain.
- Ordinary 100 kHz remains normal programming, with the existing explicit
  pre-program SYSRESETREQ reset-and-halt and HALTED confirmation. It does not
  select under-reset, add retries/reconnection, alter deadlines, or grant reset,
  recovery or hardware authority. Under-reset remains a separate explicit policy.
- CLI help, registered MCP descriptions, guide and flash Skill state the new
  default and distinguish the source candidate from installed/published 1.3.4.
  MCP descriptions also clarify that the pre-program reset belongs to the one
  authorized operation; an early failure does not prove reset/halt occurred.
- Current architecture, frequency/preparation/progress designs and standard
  procedure supersede the old 1 MHz requirement. Historical reports retain the
  actual frequency and outcomes of earlier attempts. Explicit frequency test
  data and unrelated numeric values are retained.

The only runtime changes are the two default literals. CLI help and MCP
docstrings change descriptions only. Authorization, receipts, identity checks,
control, failure-stop, cleanup, worker protocol and timeout logic are unchanged.
100 kHz may reduce SWD throughput; this slice does not measure physical timing
or expand operation budgets.

## Complete-diff review and corrections

Primary reviewed the full accepted-base-to-final-CodeHead diff in the clean
review tree: **19 files, 422 insertions, 40 deletions**.

| Area | Changed files |
| --- | --- |
| Runtime defaults | `tools/stm32-toolkit/src/stm32_toolkit/probe/worker.py`, `probe/pyocd_backend.py` |
| Public descriptions | `tools/stm32-toolkit/src/stm32_toolkit/cli.py`, `mcp_server.py` |
| Implementation tests | `tools/stm32-toolkit/tests/test_flash_frequency.py`, `test_probe_worker.py`, `test_pyocd_backend.py`, `test_physical_target_workflows.py` |
| Consumer documentation | `docs/user-guide.md`, `skills/flash-firmware/SKILL.md`, `CHANGELOG.md` |
| Governing records maintained by Primary | `docs/architecture.md`, `docs/testing/standard-test-procedure.md`; specifications `2026-10-25-flash-frequency-design.md`, `2026-10-28-flash-preparation-design.md`, `2026-10-29-attach-progress-design.md`, `2026-10-29-flash-default-100khz-design.md`; plans `2026-10-25-flash-frequency-plan.md`, `2026-10-29-flash-default-100khz-plan.md` |

Review corrections sent to Claude were bounded to the guide, MCP descriptions
and frequency tests: exclude source-only changes from the published-1.3.4
installation statement; clarify imported programming's existing reset; and
prove preservation of a supplied custom worker configuration when frequency is
omitted. All are reflected in final CodeHead. No actionable product finding
remains. No test failure was suppressed, assertion relaxed, or timeout enlarged.

Primary's external structural review additionally verified that worker/backend
bytes differ only in the one default each (allowing checkout line endings), CLI
AST differs only in strings, MCP AST differs only in docstrings, and all previous
test function names in the four changed modules remain. Five new test functions
produce eight parametrized cases. Native successful writes were checked against
the exact allowed file list for each edit task. The reviewed Git diff is retained
verbatim; report/checkpoint-only changes after CodeHead are not product changes.

## Fresh final-CodeHead verification

Before tests, Primary consulted the standard procedure, current checkpoint and
latest referenced execution report. All checks below ran at exact final
CodeHead with a clean source tree, explicit same-tree imports, isolated external
temp/cache/JUnit paths, and tracked source hashes checked before and after.
There is **no reuse from earlier product heads** in this matrix.

Interpreter: `D:/codex-tmp/kx23/venv/Scripts/python.exe` (Python 3.12.14,
existing pyOCD 0.45.1 environment). External `run_checks.py` is coordinator
orchestration, with no product assertions. Each execution record retains the
complete pytest argument array, source hashes, actual pytest exit code, owner,
timing and JUnit digest. Partitioning uses exact node IDs rather than overlapping
`-k` expressions. All native worker commands are preserved in task JSONs and raw
streams under `D:/codex-tmp/fd135`.

| Claude check groups | Labels | Different passing cases |
| --- | --- | ---: |
| Frequency and public option contracts | c01 | 107 |
| pyOCD backend | c02 | 159 |
| Worker, four partitions | c03–c06 | 64 |
| Pre-program preparation | c07 | 21 |
| Flash, three partitions | c08–c10 | 53 |
| Public hardware workflows with substitutes | c11 | 116 |
| Physical Target workflows with substitutes, two partitions | c12–c13 | 53 |
| Target runner, four partitions | c14–c17 | 202 |
| Imported firmware workflows, two partitions | c18–c19 | 18 |
| CLI | c20 | 46 |
| AI call guidance | c21 | 14 |
| IDE contracts, two partitions | c22–c23 | 40 |
| **Claude total** | **23 groups** | **893** |

Primary independently executed frequency (p01: 107), the four affected worker,
backend and Target default-profile cases (p02: 4), and guidance (p03: 14) in the
clean review tree: **125 passed**, including all eight new cases. Those cases are
a subset of the author matrix and are not added to its total. Combined distinct
evidence is **893 passed, 0 failures, 0 errors, 0 skips**. The frequency run emitted
a Pydantic unresolved `lifespan` annotation warning; its tests passed.

The repository flash Skill also passed the existing `quick_validate.py` format
check as an ordinary check, not a pytest case. Native PowerShell reported
successful matched results without numeric exit codes; those native exits stay
`null`. Actual pytest subprocess exits are independently recorded as 0. No
invented numeric exit is assigned to the Skill validator or native shell tool.

Primary reconciled JUnit freshness, digests, case identities, suite counts,
owner overlap, recorded commands and every recorded tracked source hash. This
is the affected offline matrix, not whole-repository coverage, release
qualification, real IDE acceptance or hardware execution. Earlier platform-only
release checks remain outside this slice and are not claimed as passes here.

## Retained delegation and execution deviations

All invocations retain their original verdicts and raw logs. Product acceptance
does not retroactively accept a rejected invocation or rely on model claims.

| Invocation | Actual result and retained limitation |
| --- | --- |
| `edit-run` | Primary stopped after read-scope deviations; CLI exit 4294967295, no final completion, four scope flags, zero writes and no tests. Initial read scope omitted relevant module parents/helper. User authorized one bounded replacement. |
| `replacement-run` | That one replacement performed 33 successful native edits, all within the 11 allowed write files; no tests/shell. CLI exit 1 / `error_max_turns`; seven read-scope flags (default Globs/root Greps, a nonexistent misspelled path, and pyproject reads). Dispatcher `accepted=false`; all edits/logs retained and independently reviewed. |
| `review-fix-run` | New concrete three-file review correction, not a restart of the failed broad task. Eight successful native edits within those files, no tests/shell. CLI exit 0, but one default-path Grep scope flag; dispatcher `accepted=false` retained. |
| `verify-run` | Fresh inventory and real harmless native shell smoke passed. Twenty exact commands c01–c20 completed with passing fresh tests. Coordinator supplied 24 commands to a launcher limited to 20 turns; CLI exit 1 / `error_max_turns`, dispatcher `accepted=false`. Remaining four commands were `not_invoked`, with no pending execution. |
| `verify-tail-run` | First execution of the four genuinely uninvoked checks c21–c23 and Skill validation. Fresh native PowerShell inventory/smoke passed; four matched successful commands, no scope/command/metadata flags or pending result. CLI exit 0, dispatcher `accepted=true`. No earlier check was rerun. |

The read-scope flags were related owned-repository searches/reads, including one
nonexistent path, not a permission-policy refusal. They remain deviations; they
were not retrospectively authorized. Review found no writes outside the exact
write lists and no shell execution by edit workers. Startup metadata registered
exactly Read/Edit/Write/Glob/Grep for file workers and PowerShell for verification,
using the unchanged configured route. No bypass, authentication/model change or
unrelated process interference was used. The dispatcher's audits are post-run
evidence rather than an OS sandbox; stopping a CLI does not undo prior actions.

Evidence root: `D:/codex-tmp/fd135`, including task JSONs, raw native streams,
manifests, original rejected summaries, per-command stdout/JUnit/execution
records, the coordinator stop record and final reconciliation.

| Frozen evidence | SHA-256 |
| --- | --- |
| `reviewed.diff` | `f73e3c4f5de74b8d52e3f44a69bddba09ae6e7bd193ca297720cc92e98046258` |
| `acceptance-evidence.json` | `cf7f28545a45def296698c1c70a08a7977e42dd3e49eb1616aefe7546a512f50` |

The reconciliation record embeds individual JUnit/execution/summary digests,
the structural-review digest, all eight new case identities, and the original
edit invocation audits. Its helper never invokes product code or reruns tests.

## Remaining issues and next gate

1. The confirmed physical blocker is still the prior attach timeout near
   Session construction, possible temporary USB open/protocol queries and the
   subsequent IPC boundary. SWD clock selection occurs later; current evidence
   does not establish frequency as its cause. Changing the default does not
   establish that this blocker is fixed. See the retained
   [offline analysis](../ATTACH-PROGRESS/attach-frequency-offline-2026-10-29.md).
2. The original `IPSR=3` programming failure's root cause and the physical effect
   of the new SYSRESETREQ/HALTED preparation remain unverified. The previous
   physical attempts failed before reaching programming. A historical successful
   100 kHz **under-reset** receipt does not prove ordinary 100 kHz works, or
   separate reset and frequency effects.
3. Project-specific risks remain: the inferred hard FPU ABI still lacks an
   independently confirmed ARMCC baseline, and the reported CCM margin is only
   256 bytes. Existing diagnostics expose these; this frequency slice does not
   establish ABI equivalence or add memory headroom.

Any future physical validation must use the maintained standard procedure,
actual candidate/runtime/firmware identities, a newly filled finite execution
card, independent review of the updated entry contract and fresh explicit
hardware authorization. Ordinary 100 kHz is the default path; no 1 MHz success
is required. A terminal failure stops the run without automatic recovery.
No such hardware step, installation, packaging, push, PR mutation, tag or release
was performed here. The result-only checkpoint update needs no product retest.
