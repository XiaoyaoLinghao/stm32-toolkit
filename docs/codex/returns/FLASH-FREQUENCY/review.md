# FLASH-FREQUENCY independent review

Verdict: **ACCEPTED_WITH_FIXES** for this bounded offline source slice.

Accepted base 449c30e056f614d1ecc9a4340c0ea5feda28f07b; final CodeHead 4cd1baf11a028438a69bf1cf74b91833731b13ed; tested product/guide head a8095f03e9a8a5fa1d9dddf51075a6ac02e932f5. Primary owns specification, orchestration, independent complete-diff review and acceptance. Local Claude Code CLI using the existing provider owns implementation/tests/product guidance. No ownership override or remote authority. Review used a clean detached build-snapshot-final/STM32-Toolkit at exact heads. See [implementation return](implementation-report.md) and [evidence](evidence.json).

## Accepted behavior

Managed and imported flash accept100000..50000000Hz, strict integer types and duplicate/malformed CLI rejection. Omission preserves configuration, production normal default1MHz. Managed under-reset stays100kHz: omit frequency or explicitly use100000; conflicts fail before effects. Imported recovery remains unsupported. Config copies preserve profile/transport/policy without shared mutation or dataclass replacement on the custom worker initializer.

details.flashOptions reports requested/configured values, never measured frequency or proof of attach. Original errors, diagnostics and cleanup priority remain, as do postFlash unknown/runVerified=false and imported post-cleanup integrity/receipt checks. Conditional recoverySuggestion exists only after owned cleanup for specified managed normal program/attach failures. No automatic retry, extra hardware call, lower-frequency fallback or route switch.

Primary reviewed the entire base-to-CodeHead diff, every product/test/guide/Skill change and each correction. No actionable scope finding remains.

| Finding | Correction and evidence |
| --- | --- |
| CLI tests expected SystemExit while public main returns2 | Corrected public safe-error/zero-call/no-directory assertions on both routes; parser not weakened. |
| Skill selected frequency after call/report steps | Select all options before one call; preserve applicable authorization and separate failure recovery authority. Fresh consumer simulation confirms. |
| Recovery advice gated only on request flag | Also require actual NORMAL selected policy; custom non-normal config test passes. |
| Generic conflict guidance could mention recovery to imported caller | Route-neutral guidance and imported no-suggestion tests. |
| Missing boundary evidence | Fake session frequency, malformed diagnostic, cancellation, one-call/full-error preservation, imported program/receipt/integrity failures, strict types on both MCP tools and root-first rejection. |
| Existing multi-RAM mailbox fixture lacked explicit layout | Reproduced at accepted base; only fixture layout added, all regions/order and no-memory-I/O assertions preserved. Both owners' final targeted case passed. |

## Verification and limits

Both owners ran424 core cases at product head:424 passed,0 failed/skipped, including95 new cases. Both ran386 relevant worker/backend/flash/import/Target/IDE cases:385 passed and one legacy fixture failed identically at accepted base. Both then ran the corrected case at final CodeHead:1 passed. Product and all other tests remain unchanged after that seven-line repair, so424+385 passes are reused. **810 distinct passing cases per owner**, not a final all-tests or release-matrix claim. Initial10 CLI-test failures and the legacy failure remain in evidence; no failure is deferred.

Actual native tool_use/tool_result and JUnit establish author execution. Primary execution records subprocess exits. Source-first imports, read-only third-party dependencies and separate short temporary roots were used. Existing non-failing pydantic_settings lifespan warning retained. Target regression filename does not imply hardware: all tested backends are synthetic.

Repository Skill quick_validate passed for both owners. Fresh read-only consumer A-F correctly used one request without redundant authorization, stopped after failure, rejected unsupported imported recovery/conflicting recovery frequency, preserved unknown/run-unverified state and distinguished source from installed schema. This does not qualify live VS Code behavior. Primary-authored procedure additions received independent read-only review and a completion review confirming actual default and cleanup ordering.

## Delivery boundary

Product remains **1.3.0**; frozen/installed1.3.0 does not include this source patch, and restart does not install it. Memory-margin warnings, combined integration and unified **v1.3.1** version/release work remain. Real IDE/frequency/reset/wiring qualification belongs to primary-owned later authorized integration. No packaging, remote push/PR/tag/release, original-project access, runtime or global Skill changes; no release qualification granted.

Cleanup preflight resolved13 contained disposable directories without reparse entries. Automatic approval review rejected native PowerShell removal before process creation: **blocked by policy**. All outputs retained; no retry or alternate deletion tool. Failure evidence and earlier policy-held roots preserved. Local delivery is recorded separately after the report commit; this report omits its own SHA.
