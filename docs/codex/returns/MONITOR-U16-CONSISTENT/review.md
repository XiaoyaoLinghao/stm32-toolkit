# Monitor combined-read correction acceptance

Verdict: **ACCEPTED** for the software slice. Accepted base `ba390750127d9f89efd521a503f5338976640203`; final product/test CodeHead `d6e3749b65bf2266298a8002971f738d2aee85ea`; branch `codex/monitor-u16-consistent`. The primary owns specification, integration, complete-diff review, acceptance and local operations. `u16_compact_impl` (gpt-6-sol/max) implemented the slice; `u16_compact_review` (gpt-6-sol/max) independently reviewed it. No ownership exception or remote authorization applies.

The [specification](../../../superpowers/specs/2026-10-21-monitor-u16-consistent-read-design.md) and [plan](../../../superpowers/plans/2026-10-21-monitor-u16-consistent-read-plan.md) cover this user-authorized correction and the local 8765 update. Firmware, browser, authenticated HTTP and new physical sampling are outside this software acceptance. Version remains 1.1.2.

## Accepted behavior and complete-diff review

The existing Sampler -> ProbeSession -> MonitorObservation -> prepared Debug reader now carries private low/high pair constraints on start and resume. Eligible adjacent unsigned-byte operands share aligned SRAM snapshots and accept the last of two consecutive matching pairs within three reads. Padding does not affect comparison. Raw operands, overlapping combinations, history and CSV share the accepted bytes. Unstable or failed reads produce item errors and derived gaps, without split-byte fallback or reuse of stale values. Ineligible pairs and ordinary reads keep their existing behavior.

The primary and independent reviewer covered the complete accepted-base-to-CodeHead diff: four product files, four test files and the specification/plan. The initial safety review required counting every memory region intersecting an expanded word, including read-only, write-only and partial padding overlap; the final code and tests implement this frozen rule. Final independent verdict: no blocking findings. The final test-only change isolates the installed PyOCD transport proof in a subprocess; product bytes are identical to `002f2a193476836d6c26451be2908a65c213e19c`. No UI, public wire, storage, firmware, transport implementation or dependency changed.

## Evidence and attribution

All evidence is under `D:\codex-tmp\ur1021` unless otherwise stated. These are software checks, never new physical PASS claims.

| Owner | Evidence | Result |
| --- | --- | --- |
| Implementer | Exact final CodeHead Monitor probe/sampler/history/export/lifecycle regression, `monitor-final.log`; full command in implementation report | 302 passed, 0 skipped |
| Implementer | Exact final CodeHead Toolkit Debug/observation and cross-package supersession regression, `toolkit-final.log` | 431 passed, 1 existing Windows rename restriction skip |
| Independent reviewer | Complete initial product diff and targeted safety/contract tests, `r/review-focused.log` | 27 passed, 0 skipped |
| Independent reviewer | Final complete diff; isolated PyOCD transport proof plus both existing lazy-import assertions, `r2/final-transport-lazy.log` | 3 passed, 0 skipped; no blockers |
| Primary | Saved/imported group -> actual prepared read -> sampler/history/CSV, unique dependencies and export source expressions, `primary-integration.log` | 3 passed at product-identical `002f2a19`; reused for final CodeHead with byte-equivalence proof in `primary-final-evidence.json` |
| Primary | Complete diff review, `git diff --check`, no changes to UI/storage/history/export implementation; hash comparison of all 7 packaged UI assets | PASS, `ui-assets-unchanged.json` |
| Read-only design audit agent | Current bound ELF through production DwarfCatalog, summary `real-elf-audit.json` | Both operands are unsigned bytes at 0x2001dc29/0x2001dc2a in the safe shared word 0x2001dc28 |

The primary integration command, with both source roots in absolute PYTHONPATH and run-owned TEMP/cache, was:

```powershell
python.exe -B -m pytest tools/stm32-monitor/tests/test_sampler.py::test_u16_saved_imported_group_samples_history_and_csv_without_stale_bytes tools/stm32-monitor/tests/test_sampler.py::test_u16_sampler_reads_unique_dependencies_and_emits_only_saved_order tools/stm32-monitor/tests/test_exports.py::test_u16_batch_round_trips_history_and_csv_with_source_expressions -q -o cache_dir=D:\codex-tmp\ur1021\pc --basetemp=D:\codex-tmp\ur1021\p
```

The deterministic red case and installed PyOCD 0.45.1 offline MemoryInterface proof establish why odd-address length-2 reading splits into two read8 operations while aligned length-4 uses one word read. The final snapshot algorithm corrects that reader-side fault. This does not make the firmware's two byte-store instructions an atomic publication; legitimate window-counter variation remains unchanged.

Failure reconciliation: the early prepared-plan test doubles required the new private pair keyword; the first broad Toolkit run exposed shared-process PyOCD import contamination. Both are INFRASTRUCTURE test-fixture issues corrected without weakening existing assertions. A Monitor-only invocation initially failed collection because its cross-package fixture module was not collected; ENVIRONMENT, corrected by the final paired command. The existing Windows directory-handle rename skip is PLATFORM evidence, not a product failure. The final broad commands passed after these corrections. No unrelated release matrix was added.

## Local promotion and preservation

Only after software acceptance, promote the clean accepted source using the existing public `open` command, project `D:\codex-tmp\mr1019\p`, data root `D:\codex-tmp\mr1019\data`, session `mr-stable-20261019`, port 8765. Verify old PID, creation time, executable, command and listener before normal Ctrl+C shutdown; retain a stopped-database backup in `rollback/monitor-v3.sqlite3`. The ops script verifies unchanged project Git/build/ELF identity before startup. No schema migration is required.

Actual completion is recorded by `service.json`, `old-service-stop.json` and `data-preservation.json` in this run root; until a successful new service card exists, the prior `uw1021/service.json` remains the deployment record. Public default-browser authorization delivery is not browser validation. Browser, authenticated HTTP and new physical sampling remain DEFERRED. No firmware write, halt, reset, resume, new probe access, push, PR mutation, tag or release is part of this work.

The original dirty workspace is preserved; `original-preservation.json` confirms matching initial/final `git status --short`. Main is cleanup owner. Automatic approval policy rejected the native PowerShell cleanup command before process creation with only `blocked by policy`; no deletion executed, and no alternate removal route was used. Primary/reviewer test roots are retained in `cleanup-primary-review.json`; implementation test roots and overall disposition are recorded in `cleanup-hold.json`. Preserve source worktrees, final/diagnostic logs, live service temporary files and rollback backup. Prior cleanup holds outside this run root are untouched. Cleanup hold does not invalidate accepted product evidence.
