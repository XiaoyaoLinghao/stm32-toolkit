# VS10-A final acceptance — 2026-09-18

**Verdict: ACCEPTED.** The primary conversation owner closes VS10-A after the user explicitly ended further automatic-cleanup work. This is a bounded retention exception, not a successful-deletion claim. The earlier `PENDING_CLEANUP_DISPOSITION` labels in the implementation report and frozen evidence are historical checkpoints superseded by this verdict.

## Identity and ownership

- Accepted base: `9b7839bb01f88a9e3d2c13203f38aa0d11647232`.
- Accepted product/source head: `6e069660e4a5b62598f16637176caf086f82d3c8`.
- Prior technical report head: `0342d360485fec12b5ee75c296dad28bc66575d0`.
- Active branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`.
- Specification, integration, independent product review and final acceptance: primary conversation owner; product implementation and implementation tests retain their recorded Luna/max ownership. Evidence remains attributed to its actual executor.
- This addendum changes acceptance status only. No product, runtime, firmware, evidence-bundle bytes or public contract changed.

## Reused accepted evidence

`D:\codex-tmp\t10h-0917\evidence\final-validation-20260918.json` established that technical validation was complete and cleanup disposition was the sole remaining gate. Its existing evidence remains valid:

- T9 acceptance and historical attempt 7 PASS are retained. T10 is complete under the approved retrospective amendment; the original diagnostic session is RESOLVED and the separate supplementary session remains INVESTIGATING as specified.
- Complete software review covers the contiguous accepted-base-to-`ad87d4df0190594ab017600caa01f2261cc28013` and `ad87d4df0190594ab017600caa01f2261cc28013`-to-product-head segments, with 291/291 and 37/37 paths respectively. These are segment counts, not a claim of 328 unique paths.
- Deployment, bounded physical operations, archive content review and primary checksum verification have passed within their recorded scopes. The final bundle contains 474 checksum-covered files, zero mismatches and zero file-set differences. Its root manifest SHA256 is `509a7db2c51cc89704a6d35cf591f619223f01af7293b7aae0307364bb3e43f0`.
- P1c flash/Monitor/Fault and P4 restore retain their source/runtime attribution to `227f8ea8b6895d4c2eaa14bd2483cfbce668b4b9`. Only the two final finite activity smokes used the final product head. The successful 4,500 ms finite smoke is activity evidence, not 100 ms rate qualification; the original failure and three deadline misses remain recorded.
- Existing 100 ms sampling evidence is reused within its original scope. This verdict does not assert new timing, hardware or independent-checksum evidence.

## Cleanup disposition

The user's decision was: “算了，不纠结自动清理这件事了，现在vs10-a是否通过验收并推送github？” The primary records `RETAINED_WITH_USER_EXCEPTION` for this campaign's pending automatic cleanup; no general cleanup policy is waived.

The exact retained cache paths are the nine children `b7`, `b9`, `b10`, `b11`, `b12-mcp`, `b14-model`, `c2`, `c3`, `c6` under `D:\codex-tmp\t10h-0917`, and `basetemp`, `pytest-cache`, `pycache` under its `br-logs\review-run` directory. The final read-only inventory is 4,396 files / 43,012,207 bytes. Deletion was rejected before process creation and the deleted-file count is zero. See `evidence\cleanup-retry-20260918-result.json` under that run root.

The current P1c/P4restore firmware/build sets, receipts and locks remain preserved as recorded; no fully-clean project-tree claim is made. The acceptance bundle, necessary diagnostic evidence, original failure records and prior cleanup holds remain unchanged. No further deletion, test, deployment or hardware operation is required for this status-only closure.

## GitHub boundary

A read-only remote check at finalization confirmed the slice branch at `0342d360485fec12b5ee75c296dad28bc66575d0`, matching the previously pushed technical report and all accepted product changes. Remote `master` remains `9b7839bb01f88a9e3d2c13203f38aa0d11647232`.

This new acceptance addendum is local until a separately authorized push. No merge, tag or release is implied, and no remote action was performed while issuing this verdict.
