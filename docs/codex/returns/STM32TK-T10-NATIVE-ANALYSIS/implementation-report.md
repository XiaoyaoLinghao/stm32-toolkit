# T10 native register analysis correction

Accepted base: `6a8da073d8e79595acad21d5f2367c8393ac9597`.
CodeHead: `2c00d85abc739b404bae0f37e81e8f89263ed8a4`.
Local branch: `codex/t10-native-analysis`. No remote action, deployment or hardware operation was authorized or performed in this slice.

Primary owns specification, integration and independent acceptance. Luna/max owns product code and implementation tests; a separate Luna/max owner corrected the finite external E2E entry. Primary reviewed the complete accepted-base-to-CodeHead change in clean detached worktrees and ran the integration checks. Verdict: **ACCEPTED for this bounded offline software correction**. This does not accept the production T10 ledger or VS10-A.

## Behavior delivered

The actual P3/P4 register samples use `{bitWidth,expression,rawHex,typeName,value}`. The old analysis only accepted `{type,value}` and required exactly equal relative nanoseconds from independent clocks, producing zero pairs. The correction adds explicit request/2 with strict native uint8/16/32 decoding and mutually unique relative-time matching, capped at 5ms. Invalid values, ambiguous times and unmatched positions remain excluded; no timestamp editing, interpolation, threshold reduction or sample reuse occurs.

Result/3 embeds and hashes its full request. Monitor and Toolkit share one pure numeric contract. Diagnostic completion, same-session stored reads and explicit-continuation readers authenticate the original transcripts and recompute new statistics, including strict numeric types. Old request/1 and result/1–2 wire formats and valid evidence remain supported. The final small Store correction limits plan lookup to the current source-change declaration.

Scope: Monitor analysis model/workflow, the Toolkit pure analysis contract and its existing Diagnostic/continuation readers, with affected tests. No sampling, firmware, backend, lease, packaging or installation behavior changed.

## Verification and attribution

Luna implementation logs under `D:\codex-tmp\t10n-0917` record the native/continuation subset (38 passing checks in `b9-native-continuation-final.log`), the final Store compatibility subset (6 in `b10-store-compat.log`), Monitor analysis (45 in `b4-monitor-analysis.log`) and affected Diagnostic workflows (85 progress markers, exit0, in `b4-diagnostic-workflows.log`). The return message's count93 for the latter was a reporting error; the retained log contains85. Earlier affected Monitor workflow and legacy regression evidence is retained in `evidence\test-logs`. Compile and diff checks passed. These are software fixtures, not new physical evidence.

The primary's actual integration invocation used Python3.12.10, `-I -B`, the clean `bade87d530c0b18ee4d1ebd19b2f6613bef91458` worktree, and the reviewed `e2e\run_native_analysis_real_e2e.py` with `--source-root` and `--code-head`. Entry SHA256: `4ec25ab9e298879752174d606ec5efe75cba766e4ecf1cd5c99cd07f3b877918`. Only the hash-verified copied store under `D:\codex-tmp\t10n-0917\real-data` was written. The original refs and threshold297 were retained.

Results:

- `GPIOE.ODR`: **300 valid pairs / 300 positions / 0 exclusions**, `VALID / COMPLETED / VALUES_CHANGED`, changed=true, explicit tolerance5,000,000ns.
- Analysis ID: `d8a82a8962954f90bfac50d3d03709ad332922c83c8e18e34c12d28dcb3a466b`.
- Canonical publication was saved and reopened through the existing CLI loader; bundle export passed.
- Copied Diagnostic: **RESOLVED**; FixVerification **PASSED**, ID `de655837e819737696778a74c22fcfdaf66a852ee6abe1bb7a040ea488402628`.
- Copied v3 attempt `00000000-0000-4000-8000-000000001701`: revision1, target-fix-verified, **COMPLETED**; fresh-process show/resume/Diagnostic read passed.

The final `bade87d5..2c00d85a` delta changes only the same-session Store plan lookup; the real continuation chain takes the separate association branch. Its valid E2E evidence was therefore retained. Primary additionally ran the existing show/resume/Diagnostic APIs in a fresh process from clean final CodeHead `2c00d85a`: all returned OK, COMPLETED/RESOLVED/PASSED and timedOut=false. No full-chain repetition or new fixture was required for that delta.

The85 original files inside the copy retained their hashes after the chain. A separate read-only check against the production project store verified all85 original files unchanged against the same pinned manifest. The old INVALID analysis `c28979be1bf12dc862e7c5f9592e91180cf707fceac713915697eea7511ff83e` remains intact.

Primary records: `e2e\output\run-results.json`, `e2e\output\final-codehead-readback.json`, `evidence\production-original-after.json`, retained stdout/stderr and incremental step records. A copied COMPLETED record proves software compatibility with real captured inputs; it is not a new physical test or production-ledger completion.

Entry review also found that the executed wrapper did not explicitly compare the full request/2 references with request/1 before calling product APIs. The actual invocation used the correct original references: primary independently compared both complete canonical reference objects from the executed result against the original request, recorded in `evidence\executed-input-identity-audit.json`. Luna then added this canonical equality guard; primary reviewed the exact change and accepted final entry SHA256 `6a75d8b2f6109c156a48130d2b822cf7608e68d44dc65f84ed32466709ad162f`. Compile/help and the unchanged real inputs passed the targeted offline checks. This entry correction does not invalidate the correct-input result and did not trigger a repeat of the chain. The executed and subsequently corrected entry hashes remain distinct.

## Integration and next boundary

Canonical local integration is `D:\codex-tmp\stm32tk-integration`. The runtime remains deployed source `ee2152b497e62389a103ea4ff9ce2ebf92aae160`; this correction is not deployed or pushed. Attempt7, T9, prior accepted100ms observations and the real P3/P4 captures remain valid in their original scopes.

Next: after explicit deployment authority, deploy this accepted correction once and verify installed identity. Then use the existing authenticated P3/P4 refs and immutable continuation proof to complete production G/H offline. Do not reacquire these already sufficient windows, alter their original identities, revive an expired attempt, or reuse a consumed hardware authorization. Production T10 G/H and VS10-A Task11/12 remain pending.

Useful unit-test logs were copied and hash-verified under `evidence\test-logs`. All proposed cleanup targets were verified under this run root with no reparse points. Automatic approval nevertheless rejected the deletion before process creation with `blocked by policy`; no deletion or alternate method was attempted. The run-owned temporary trees and all prior cleanup holds remain preserved, together with real-copy E2E evidence, original production evidence and historical migration/deployment records. See `evidence\cleanup-plan.json` and `evidence\cleanup-result.json`.
