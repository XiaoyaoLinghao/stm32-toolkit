# MONITOR-U16-COMPACT acceptance

Verdict: **ACCEPTED** for this software slice.

Accepted base: `b7d5f43cec3efcfa18ecc1dc7c1e62a839434be7`.
Product/tests/generated-dist CodeHead: `3d11c00c5068d988bd8943923f5fe0d2cb67886c`.
Implementation-report head: `2a6ffda67109f8271a04c0df1680e6c22dc1cd2f`.
Branch: codex/monitor-u16-compact. Primary owns specification, integration, complete-diff review, acceptance and operations; u16_compact_impl is the sole product/test author and u16_compact_review the independent reviewer, both gpt-6-sol/max. No product ownership override or remote action. Governing [specification](../../../superpowers/specs/2026-10-21-monitor-u16-compact-design.md) and [plan](../../../superpowers/plans/2026-10-21-monitor-u16-compact-plan.md) reflect the user's approved ongoing development scope and latest feature request.

## Accepted scenarios

A saved/imported unsigned u16le watch combines low + 256*high from the same batch's deduplicated ordinary byte reads. It survives reload, appears in live values and one of the existing eight curve slots, and persists in history/CSV with both expressions. Public-path fixture evidence covers 0, 65535, then an unavailable high byte without stale-value reuse. Expanded dependency count is bounded before probe admission. Existing variable/register and old group-transfer representations remain compatible; there is no generic formula engine, new backend or CPU-control path.

Source browsing is now file -> global variable or named function -> member/[index]. Globals load only for an explicitly opened file; existing pending/failure state does not trigger an automatic retry. Full selectors remain accessible, types/provenance live in row details, and statistics/coverage live in the existing diagnostics drawer. Normal rows no longer repeat counts, global-role badges or ownership prose. Group editing, local retries, binding/run/revision admission, waveforms and CSV remain connected to their existing state authorities.

Storage schema 2->3 changes metadata only; old v1 conversion chains through v2. Runtime completes initialization before exposing its listener or runtime record, including read-first, invalid-store and cancellation cleanup. Source/ELF/firmware/build identities and version 1.1.2 are unchanged.

## Review and evidence

Primary read the complete accepted-base-to-CodeHead source/spec/test diff in the clean detached review tree, including every correction delta, and verified generated assets through byte-identical rebuilding. Independent reviewer separately reviewed the complete diff and recorded no remaining actionable finding in D:\codex-tmp\uw1021\review-evidence\review-final.md. Three product findings were corrected by the original implementer: raw internal keys in curve labels, implicit retry of retained global-scope failures/pending requests, and missing startup migration before first public reads.

The Unicode canonical-selector bound and group response-budget edge were resolved during design. A suspected oversized live event from unsupported Unicode selectors was withdrawn after checking Toolkit's actual ASCII variable grammar and supported maximum serialized cases; no unnecessary admission framework was added.

| Evidence owner, exact CodeHead | Result |
| --- | --- |
| Implementer | 658 affected backend/protocol/storage/sampling/history/export/service/runtime/lifecycle/assets tests passed; one existing aiohttp deprecation warning. Full UI: 506 passed, one existing optional replay skip. Both TypeScript checks, lint, build and seven-file dist rebuild passed. Commands and logs in implementation-report.md and backend-codehead.log/ui-codehead.log under the run root. |
| Independent reviewer | 12 focused backend and 25 UI checks passed. A consistent read-only backup of the real schema-2 DB migrated through final storage initialization without changing row counts or row-content SHA-256 digests across groups, items, history batches/values, accounting and export records. Public stores list both groups and read history. Commands/proofs in review-evidence/review-final.md and live-copy-final-result.json. |
| Primary | 102 Python integration/runtime/cleanup/u16 public-path/assets checks and 51 UI integration checks passed. All seven committed dist files matched an independent rebuild. Exact command arrays and timestamps are in primary-checks/proof.json; complete logs in the same directory. |

All run paths above are under D:\codex-tmp\uw1021. Earlier default-worker UI timeout was classified ENVIRONMENT/test-host contention: the target passed alone, and full suites passed at two workers without changing product behavior or timeouts. An initial cross-package fixture-path collection failure was ENVIRONMENT and the corrected same-tree invocation passed. Presentation assertion updates were REPORT; the three resolved product findings were PRODUCT.

These are software fixtures/DOM/replay and offline data-copy evidence. Browser layout, authenticated live-service HTTP, and physical-board sampling remain **DEFERRED**, not PASS. No firmware build/flash/reset/halt/resume, install, version bump, push, PR, tag or release occurred.

## Local promotion and cleanup

After acceptance, primary revalidates the old uc1021 service card, exact PID/creation/command/source/loopback listener and terminal ownership, stops only that owned service normally and proves port/process release. Before startup migration, make an offline SQLite rollback backup at D:\codex-tmp\uw1021\rollback\monitor-v2.sqlite3. Start the accepted clean review tree through public open with unchanged project D:\codex-tmp\mr1019\p, data D:\codex-tmp\mr1019\data, session mr-stable-20261019 and port8765. Check actual schema3 and equality of all preexisting group/history/export/accounting table row digests. Successful final source/PID/terminal/default-browser handoff is authoritative in D:\codex-tmp\uw1021\service.json; until that successful card exists the old service remains the serving version. This operational proof is not browser or hardware validation.

Disposable test/database-copy/temp roots were removed after evidence reconciliation; source, reusable dependencies and concise proof/logs remain. Four roots contain test-created reparse points and remain on explicit HOLD_REPARSE_BOUNDARY in cleanup.json: py-backend-final, py-basetemp-full, py-final-codehead and pybase. They were not recursively traversed for deletion or retried around the guard. Prior task holds and user-owned files remain untouched. The rollback backup and live service temp directory are retained.
