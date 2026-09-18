# VS10-B final acceptance

Status: **ACCEPTED — VS10-B**. Primary reconciled the completed scenarios and
independent software/archive verdicts on 2026-09-19 (Asia/Shanghai). All 3,000
inventory entries passed independent path, size and SHA256 comparison; the
175-file baseline and each application's seven additions were separately checked.
Final independent record:
`D:\codex-tmp\v10b-0918\fin\archive-review\final-acceptance-review.md`.

VS10-B is the existing BSMR-MC04 / STM32F429ZG / CMSIS-DAP scope. This report
reconciles the original physical results and the separately approved offline
finalization; it does not claim a new physical execution during finalization.

## Ownership and fixed source

- Full accepted product base: `abdc2fb5dbde2b6643e26d42e29c7ad6db72f921`.
- Finalization product/tests CodeHead: `22ec7ba68967bcbcacea325848886dd953affb31`.
- Approved design head: `1b448632ea6b7d3eb9dd2e5eb73d056df0270274`.
- Product and implementation tests: one Luna/max owner; see the adjacent
  `STM32TK-1002-VS10B-OFFLINE-FINALIZATION/implementation-report.md`.
- Design, complete-diff review, integration and final acceptance: primary agent,
  with a separate non-implementing reviewer for code and the final archive.
- Integration branch: `codex/STM32TK-1002-CUBEMX-REAL-BOARD-integration`.
- Existing installed diagnostic deployment remains
  `12df4fe0569104d6f0e7a827496341d999e1f3ea`; finalization used the clean reviewed
  source with its existing Python runtime. It was not a new installed deployment.
- No GitHub mutation, hardware operation or ownership override in this finalization.

## Completed scenarios and evidence

All local paths below are relative to `D:\codex-tmp\v10b-0918`.

| Required path | Actual outcome and retained evidence |
|---|---|
| Fresh CubeMX creation, native provenance, configuration and staging builds | PASS within original creation scope; `fin/e/acceptance-audit/acceptance-audit.md` maps the original files. Staging firmware is kept distinct from qualified NORMAL firmware. |
| NORMAL physical Target and real IDE/CLI/MCP path | PASS using the approved under-reset / 100 kHz route, 7,812-byte readback and physical mailbox. User saw `testtime=43063`, stopped normally, and confirmed alternating LEDs. CLI/MCP share the required identity. Ordinary attach flashing and IDE-derived 100 ms timing are not claimed. |
| Fault → source correction → fixed physical Target and Monitor | PASS at card05. Each side has 300 valid batches in 30 seconds at a requested 100 ms period, zero drops. Fault PE3 is fixed; repaired PE3/PE4 both change. Fixed Target passes; see `evidence/closed-loop-05/final-ledger.json`. |
| Diagnostic, FixVerification and separate Monitor bundle | Diagnostic revision15 RESOLVED; FixVerification `2802be0ae4f00f1769c68a25cee0d7665720a231897672a93fb26a19b546f654` PASSED. Bundle `bc4f0fa30c0f16f7af9bd260de57af9dedb8ccc50474393adac21e41f50cfca9` independently authenticated with the existing graph validator; see `fin/e/bundle-audit.json`. |
| Explicit offline completion of preserved physical graph | Copy rehearsal and canonical `/5` completion PASS through the public CLI and fresh-process reads; `fin/e/copy/summary.json` and `fin/e/canonical/summary.json`. No old evidence was relabeled or regenerated. |
| Unified archive | `fin/archive/manifest.json`, sorted inventory of 3,000 files; final independent verdict is recorded separately under `fin/archive-review`. |

The canonical new attempt is `17af06e8-a940-45df-8ccb-e1f250314fc6`, schema `/5`,
revision1, `COMPLETED / target-fix-verified`. Checkpoint:
`fdf7819a197b0a4cc49ae8bf14aaf0fa1bc3b2426720d71fb39f6aac2b5edb73`.
Its proof evidence is
`0f2c7cd8bcb9eadf65a6d8e7a34b88e07f603aac751204e246ceb1383ede1e4b`.
The original 175 evidence files retain identical bytes; exactly seven new records
were added. The old `/4` attempt `4787a53b-1291-4461-8a50-b984d22ad877` remains
expired at revision6, with its original 300-second deadline and no revision7.

The fixed firmware remains build
`cbf7f4b40102a54f01e55a42d374209281fe084afb4157447e4307600d2542a2`
at project commit `8445c769c5ccf116411eb682ad41edcadf1e8ab7`.
The archive explicitly retains the qualified NORMAL identity, earlier staging
identity, SVD configuration transition and historical/current deployment scopes.

Archive manifest SHA256:
`e1c2c506a7f54590f3bcd501ce88262dabdcdc24fcbf9c4799381bb15702b2e1`.
Inventory SHA256:
`12eb289e6749c83eff877f1cf1a90f0003f59138259ac981e965d8235794d6c6`.
The manifest's assembly-time pending status is immutable; its independent review
is a separate dated record, not a rewrite of the frozen manifest.

## Verification and limitations

Retained required software results: 16 persisted finalization regressions, 56
affected compatibility checks, 6 public CLI checks and 3 timestamp/deadline checks.
Focused subsets are not added to these totals as new coverage. Primary's separate
5 routing checks remain attributed to primary. The final unused-import deletion
does not invalidate unchanged behavior evidence. Source-controlled synthetic
records and real-data-copy checks remain offline software verification.

Windows native-thread contention is a known separate limitation: a second caller
failed `msvcrt.locking` after about 9.094 seconds; unchanged DiagnosticStore mapped
`OSError Errno 36` to chain-integrity failure before CAS. One root was published
and authenticated, but native-thread concurrency semantics are not marked PASS.
The approved serial finalization succeeded. Detailed stack and scope decision:
`fin/e/code-review/native-thread-cause.md` and `candidate-22-final-review.md`.

Automatic approval review rejected cleanup of `fin/t/review-route` before execution,
returning only `blocked by policy`; the folder was retained without workaround.
Existing VS10-A and attempt7 physical PASS remain unchanged. VS10-B completion is
separate from 1.0 release readiness and from any GitHub synchronization.
