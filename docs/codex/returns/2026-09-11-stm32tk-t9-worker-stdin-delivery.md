# T9 Windows MCP worker correction and physical parity

Status: **T9_CLI_MCP_PHYSICAL_PARITY_PASS**. User authorized the correction, local deployment and T9 continuation; before the run the user confirmed connected hardware and blinking D4, and after both reads confirmed D4 still blinking. No remote action, flash, reset, repeated IDE cycle or hardware retry was performed. Full T9, T10 and VS10-A remain open.

Independent acceptance-ledger review: **ACCEPTED for the remaining CLI/MCP equivalence subitem**. The reviewer checked raw responses, shared binding/typed semantics, lease release and empty process snapshots; original generated-configuration compatibility remains outside this verdict.

## Accepted correction

Implementation base `61e8250a384f2ffb9ec2bfb27e741ef6484c7d42`; Luna/max CodeHead `97edbe2431d42a6984f3e3ac17619d5e60fddbad`; integrated candidate `814b1683d2f562ce1bb2db464ee4c572cb31d658`. Main owns design/integration/deployment; the independent reviewer accepted the complete four-file implementation diff, with no blockers.

The private Windows worker launcher binds only its child standard handles to owned NUL handles, preserving the parent MCP streams, CPython spawn protocol, IPC, timeout and cleanup. It does not globally patch WinAPI or stdlib. The supported private CPython 3.12 shape is checked before creation; non-Windows launch behavior remains unchanged. Original evidence identifies inherited stdin as the startup trigger; an exact lower-level blocking stack was not obtained.

Owner checks: worker module 55 passed, MCP module 18 passed, real stdio offline startup/close passed. Independent checks: focused launcher/pipe 3 passed, real stdio 1 passed, normal worker call/close 1 passed, complete diff check clean. These are software evidence, not physical results.

## Deployed candidate and physical result

- New DataRoot: `D:\stm32tk-data\t9-worker-stdin-20260911`; runtime `runtime\0.9.0`. Old campaign root was preserved; no old session/ticket/lease/action/runtime-state was copied.
- Manifest SHA: `a7ad6feab88ae172077ee44d284fcfeb47f7cd5d9a2c96e350aff6a9da48fb2f`; runtime-state SHA: `298e5ca655f7be96d1141d8e157a27401fd5d0eb5cb4ea17c27b2dbf41076e9b`.
- Existing builder verified the source-bound bundle; Check=missing → Bootstrap=healthy → Check=healthy/matching. All 145 installed product files matched the wheels. Actual final `pyocd.exe --version` returned 0 / 0.45.1 and its Python binding points to the final runtime, with no staging path.
- Deployed real MCP stdio offline worker constructor/close: ready in 1.468 seconds, `aliveAfterClose=false`, no hardware access.
- Exactly one deployed CLI typed read returned `testtime=38`; one true stdio MCP `stm32_variable_read` returned `testtime=0`. Both product responses were OK, item status=ok, `long unsigned int`, 32 bits; process exits were 0. Complete bindings match except capture time. Different one-shot counter values do not establish continuous-sampling behavior.
- P2 workspace `d26e5624cd091c34683d45c4f90dbe7ad696c624c2a7f8761439c4ed9b5dce03`; session `vs10a-t9t10-p2-20260911-04`; build `77d787ee83f744831316f9531b825935ef276520472221a8174f7a7d4cfe57f9`; ELF `10df523425dbe8567d5876e5e790714d1314a5dd3d545e4d43a063c300fd6ead`; input `2ea7aff366fcb776fbeb9f82b2f21d35f9611f97429918494d2b9b90f9411ad6`. Full probe/target and command bindings are retained in run evidence.
- Each read released its lease. Final registry=released, no Python/PyOCD/GDB/Monitor/Toolkit consumer remained. Old runtime/state/launcher, P2 ELF, flash receipt, handoff and registry hashes remained unchanged. User confirms D4 still blinking.

Evidence: `D:\codex-tmp\t9-worker-stdin-delivery-20260911`, particularly `result.json`, `commands.json`, `cli-read.json`, `mcp-read.json`, exit/dispatch records, `registry-final.json`, `processes-final.json`, deployment checks and `evidence-hashes.json`. Product checks: `D:\codex-tmp\stm32tk-mcp-worker-stdin-fix-20260911\final-checks.txt`.

## Reusable deployment lessons and remaining acceptance

First packaging failed because the wheel used CRLF checkout bytes while the source archive used LF. A clean dedicated LF worktree at the same candidate commit corrected the environment; no product change was made. Apply archive settings before creating that worktree and verify actual bytes, not just Git cleanliness. Automatic policy rejected cleanup commands for the original and later LF packaging worktree build/egg-info outputs; both sets are retained, and denied paths were not retried. The builder/installer's run-owned D temporary directory is empty; candidate delivery and useful evidence are retained.

Two offline execution-harness assumptions were corrected before hardware dispatch: `_read_state` requires an existing session directory, whereas a fresh DataRoot legitimately has none; and UTF-8 evidence containing Chinese must be read explicitly as UTF-8 rather than Windows GBK. Neither failure dispatched hardware or invalidated product evidence. The existing Pydantic unresolved `lifespan` annotation warning remains in MCP stderr; initialization and the actual product read succeeded, so it is not treated as the previous startup timeout.

Preserve attempt 7, P2 Target 04, historical -12 sampling and continuation 09 adapted IDE/handoff/CLI successes. The original 09 MCP timeout remains a historical failed operation. This run closes the corrected candidate's CLI/MCP physical parity gap. Original generated IDE configuration still needs its bounded compatibility correction and applicable verification; the adapted IDE path must not be relabeled as directly generated configuration acceptance. T10 physical P3/P4, Diagnostic/FixVerification, Task11 lineage and Task12 full-diff acceptance remain outstanding.
