# T10 native analysis implementation plan

Accepted base: `6a8da073d8e79595acad21d5f2367c8393ac9597`.
Governing specification: [native analysis contract](../specs/2026-09-17-stm32tk-t10-native-analysis-design.md).
User authorization: “开始进行修正” for the diagnosed bounded offline correction. The existing plan-approval waiver applies; no deployment/hardware/remote authority is included.

## Ownership and paths

- Primary: frozen specification/plan, evidence-copy preparation, integration decisions, complete-diff review, acceptance and SOP/report.
- One Luna/max implementation owner: new pure core contract, affected Monitor model/workflow and Toolkit persisted-reader adapters, focused implementation tests. No recursive delegation and no self-approval.
- Independent reviewer: contract consistency first, then complete final diff in a clean detached review worktree.
- Active slice branch `codex/t10-native-analysis`; isolated worktree `D:\codex-tmp\t10n-0917\impl`; evidence/cache/temp/review under the same short run root. Primary owns cleanup. No PR or remote mutation.

## Bounded file scope and order

1. Toolkit `monitor_analysis_contract.py` (new, pure) plus Monitor `analysis.py`: implement only request/2, strict native uint8/16/32 values, mutually unique <=5ms matching, result/3 with embedded request, old-version compatibility.
2. Existing `analysis_workflows.py`, Toolkit `diagnostic_workflows.py`, `diagnostics/events.py` or `store.py`, `acceptance/continuation.py` only where persisted /3 validation actually requires changes. Reuse existing transcript readers and enforce recomputation; do not widen physical/session identity rules.
3. Existing analysis, diagnostic and continuation test modules, with a small focused test module if needed. No generator/CI/backend/firmware/deployment changes. If a further file is necessary, provide its exact dependency reason before expanding scope.
4. Code commit; return full CodeHead and exact verification commands/results. Implementation report records accepted base and CodeHead, not its own report SHA. Primary updates SOP and integration report after independent acceptance.

## Required verification

- Native exact shape, selector, status, bool/range/type/width/hex negatives; compatible and incompatible pairs.
- Zero/5ms/over-5ms skew, invalid policy bounds, one-to-many/many-to-one ambiguity, no reuse, missing positions, invalid-value ambiguity, duplicate/reversed timestamps and threshold behavior. Preserve original timestamps.
- Existing v1 exact behavior and serialized IDs; request/result version downgrade, embedded request mismatch, reference/lineage consistency, forged statistics despite recomputed hashes.
- Existing affected Monitor model/workflow and Toolkit Diagnostic/continuation regression subsets. Select tests after identifying real call paths; no unrelated release matrix.
- Real-evidence copy: original P3/P4 physical references, accepted immutable continuation proof and actual source-change declaration; 300 valid pairs and zero exclusions at threshold297, compare/bundle/Diagnostic RESOLVED and FixVerification PASSED, final v3 checkpoint and fresh-process reader. All writes to copied store, hashes of production evidence unchanged. Existing public CLI/API used directly; a new run wrapper is justified only if existing entry cannot combine this bounded offline sequence, and must not become a framework.

Use Windows Python3.12 and candidate Toolkit+Monitor source paths, with explicit short basetemp/temp/cache under `D:\codex-tmp\t10n-0917`. Do not accidentally import deployed old packages. Keep canonical JSON inputs. Preserve relevant full logs, summarize routine outcomes; classify failure before changing product code.

## Exit

Independent ACCEPTED requires all affected software gates, genuine copied-evidence E2E and complete diff review. One owner corrects findings on the same branch. Two failures to converge on the same issue trigger design reconsideration. Fast-forward local canonical integration only after acceptance. Actual runtime and business acceptance remain unchanged; later authorized deployment/real ledger completion are separate steps. No packaging, new hardware or push in this slice.
