# STM32TK-0501 Codex Revision Plan

## Context

Revise Draft PR #13 on `codex/STM32TK-0501-MONITOR-SERVICE` after independent review. The user has explicitly assigned all implementation and testing for the current 0.5/0.6 objective to Codex-created subagents; OpenClaw is not involved. Preserve the public API and unrelated accepted behavior unless a task below explicitly changes it.

## Global Constraints

- Work only in the isolated worktree `C:\tmp\stm32tk-0501-monitor-service` and on the existing Draft PR branch.
- Use test-driven development for every behavior change: first add a deterministic failing regression, then implement the smallest correct fix.
- Do not push, merge, close, delete remote branches, or change Draft/ready state from a task subagent.
- Preserve unrelated changes and generated/untracked files. Do not edit the main worktree.
- All new concurrency tests must be deterministic and avoid timing-only assertions.
- Every created observation and lease must be released exactly once on losing, failure, release, or shutdown paths.
- JSONL and CSV exports must share `flatten_history_page` as the per-value serialization source; JSONL emits one flattened value record per line.
- Reports may state only commands and outcomes actually observed against the reported commit.

## Task 1: Serialize probe lifecycle transitions

Files allowed: `tools/stm32-monitor/src/stm32_monitor/runtime.py`, `tools/stm32-monitor/tests/test_runtime.py`.

Add deterministic regression coverage for concurrent connect/connect and connect/release interleavings. Make lifecycle transitions atomic so that concurrent connects cannot both succeed and a successful release cannot be followed by an in-flight connect silently restoring the probe. At most one conflicting operation succeeds; returned results and final state agree. Close every created observation and release every acquired OBSERVE lease/supervisor resource exactly once. Preserve existing error/result contracts and normal connect/release behavior.

Required focused gate: run the complete `test_runtime.py` file on Python 3.12 with pytest cache disabled and an external basetemp.

## Task 2: Stabilize retention under loaded coverage runs

Files allowed: `tools/stm32-monitor/src/stm32_monitor/history.py`, `tools/stm32-monitor/src/stm32_monitor/storage.py`, `tools/stm32-monitor/tests/test_history.py`.

Add a deterministic regression that demonstrates the retention coordinator must not report `MONITOR_STORAGE_BUSY` merely because executor scheduling consumes the tiny gap between the internal retention budget and the caller timeout. Fix the timeout/budget relationship without removing bounded work, cancellation, chunking, or actual storage-busy handling. Avoid simply weakening the existing 100,000-value performance assertion. Verify the exact flaky test repeatedly and run the complete `test_history.py` file with coverage on Python 3.12 using external output paths.

## Task 3: Unify JSONL and CSV value flattening

Files allowed: `tools/stm32-monitor/src/stm32_monitor/exports.py`, `tools/stm32-monitor/tests/test_exports.py`.

Replace JSONL batch-per-line output with one flattened history value record per line. Both JSONL and CSV must obtain value records through the public `flatten_history_page` iterator and retain streaming, integrity verification, pagination, stable field evidence, batch value count, and value ordinal. Rewrite contradictory tests and add coverage proving the same flattened values feed both formats. Preserve memory bounds and terminal error semantics.

Required focused gate: run the complete `test_exports.py` file on Python 3.12 with pytest cache disabled and an external basetemp.

## Task 4: Reconcile durable evidence and acceptance documents

Files allowed: `docs/codex/returns/STM32TK-0501-MONITOR-SERVICE/implementation-report.md`, `docs/superpowers/plans/2026-08-08-stm32tk-0501-monitor-service.md`, and a committed monitor performance test if required to replace evidence that was absent from the reviewed commit.

After Tasks 1-3, run the complete monitor test suite with branch coverage on Python 3.12 and the compatibility suite on Python 3.10. Reconcile the implementation report and plan checkboxes with the exact observed commands, counts, coverage, accepted base, code head before the report commit, and any remaining deferred platform gates. Remove claims based on ignored or absent scripts. Do not call the module accepted until all required non-deferred gates pass.

## Task 5: Whole-branch acceptance review and GitHub submission

No implementation by the controller. Generate a complete accepted-base-to-head review package, use a fresh high-capability reviewer, resolve any load-bearing findings through one reviewed fix wave, rerun required gates, then push the existing branch and update Draft PR #13. Do not merge, close, delete branches, or mark ready without separate user authorization.

## Task 6: Exact 160 MiB export-cap amendment

The user explicitly approved raising the export artifact cap to exactly 160 MiB
and authorized downstream details to be confirmed autonomously. Preserve the
existing 512 MiB workspace quota and the separate `<64 MiB` traced-memory gate.
Prove realistic, lossless 100,000-value JSONL and CSV exports, controlled
small-cap overflow cleanup, and quota reservation arithmetic. Export may use an
internal uncached verified history-query mode only if ordinary query caching,
integrity verification, filter/cursor binding, concurrency, and stable errors
remain unchanged and every page is still consumed through public
`flatten_history_page`.

This bounded safe subset may modify `exports.py`, `history.py`, their focused
tests, and the governing evidence documents. The successful functional and
memory checks do not close the named performance contract: export `<5 s` and
append p95 `<50 ms` remain non-deferred blockers until separately verified.
