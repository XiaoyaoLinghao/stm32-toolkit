# T10 continuation: confirmed session mismatch

Status: **BLOCKED_OFFLINE_SESSION_SCOPE**. P4 programming/readback, the native `d3-heartbeat` PASS and the user's alternating D3/D4 observation remain valid. This continuation performed no hardware access, deployment, firmware change or acceptance completion.

## Baseline and ownership

Integration base `b9ce0ba5225feb11abf803ebfee0f9c24a19149e`, branch `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`; deployed source `7d22c149d5f83ded14024569bce9a17734b2b7d1`, accepted product CodeHead `8e75012e0c92dc37e67d0d31064590772a53be4b`. Primary owns reconstruction, this proposal, integration and hardware; any future product implementation/tests remain Luna/max-owned with independent review. No remote action or ownership override is authorized.

## Reproducible finding

The installed existing `diagnostic_workflows._same_scope` was invoked offline using the actual recorded P3 and P4 identity fields. It returned **false**. Evidence: `D:\codex-tmp\t10a-0917\offline-scope-check.json`. This is a predicate check, not an executed full Monitor comparison.

The later read-only runtime/source traceability supplement is `D:\codex-tmp\t10a-0917\scope-check-runtime-pin.json`: explicit program-diagnostic Python, installed `diagnostic_workflows.py` SHA256 `edf047ae0b4f24aceb330f56cab93ad2c7bd7481de606a9fe18e6475fec5b7d2`, runtime-state SHA256 `c11d102f195c7b7b9dae7fc8a8b1602337eb643ca4ec8bd467b61bee1ef8f771`. It records a subsequent import/path/hash check, not retroactively captured metadata from the initial predicate invocation. No hardware or predicate rerun was performed.

| Compared field | Expected, from P3 | Actual, from P4 | Result |
| --- | --- | --- | --- |
| `workspace_id` | `d7b137149685154d159f2f0ded85852248e4a2de1fe2813a788aa9bb54c2fd74` | Same | Match |
| `project_id` | `4ea7b7c3-2ed9-51ae-bf7d-4b55a23bad6c` | Same | Match |
| `target_device` | `STM32F429ZGTx` | Same | Match |
| `session_id` | `vs10a-t10-d3-20260914-01` | `p4-recovery-20260917-03` | **Mismatch** |

P3 source: `D:\codex-tmp\t10-d3-flash-20260914\execute.stdout.json`, run `target-v2-53b0c81ffeb50ab65bd6c0ad815ad273`, evidence `1a89d89a06e815c6197e273f0a88a1bb3e8253b388c83d007f8c913086c28ab0`.

P4 source: `D:\codex-tmp\p4deploy-0917\recovery-03\execute.stdout.json`, run `target-v2-d5b0e440822671ba2812a367bfedf2f6`, evidence `96d588e2c192e18e531d7007b1f2b2e3eedff21942c9023dd858200082096d74`. The current successful Flash receipt has the same P4 session and SHA256 `8170689bffda028630f9ea6fb11fb326a3f3676ca1acf4baaed19f6a4fd84401`.

Checks at this baseline:

- `tools/stm32-toolkit/src/stm32_toolkit/diagnostic_workflows.py:1233-1236`: `_same_scope` requires equality of the four fields above. Lines2269-2270 separately require equal transcript sessions.
- `tools/stm32-monitor/src/stm32_monitor/analysis_workflows.py:606-613`: before/after origin and projected sessions must match each other and the comparison context; otherwise `INCOMPATIBLE_IDENTITY`. Lines1331-1332 also require both Target TestRuns to share a session. A source-change declaration permits the declared firmware change; it does not waive session identity.
- `tools/stm32-toolkit/src/stm32_toolkit/execution_provenance.py:40-54` and `testing/publication.py:696-697`: physical origin/import sessions must match the original manifest identity. Import cannot rename P4 into the P3 session while retaining physical provenance.
- `tools/stm32-toolkit/src/stm32_toolkit/acceptance/recovery_workflows.py:2025-2031,2143-2157`: recovery binds the TestRun and Diagnostic to its context session. Existing recovery does not bridge these original sessions.

The prior attempt `4956a90c-6132-4651-b597-e5aef5a7fd22` remains revision6 / firmware-built-after and expired at `2026-09-17T00:51:15.214976Z`. Its deadline and consumed authorizations must not be renewed in place. Diagnostic `2781df6812f2dc0ba067e0b1b9d07b5a` remains revision6 / FIX_PROPOSED; no completed FixVerification exists.

## Cause and reached stage

Classification: **INFRASTRUCTURE: acceptance orchestration created a cross-session association gap, which the evidence identity contract correctly rejects.** Primary placed successful recovery programming in a separate diagnostic session instead of retaining the campaign EvidenceIdentity session. A fresh hardware action/lease did not require changing that campaign session. The approved physical recovery plan explicitly preserves `_same_scope` session equality. This is not evidence of another board failure and is not caused by `gitDirty=true`.

The last physical stage reached is successful P4 programming/readback/native test with positive cleanup and subsequent user LED observation. The current continuation reached only offline artifact/identity and entry-point checks. No P4 dual-bit Monitor window, comparison, bundle or FixVerification was run. Therefore the full comparison error is a confirmed contract consequence, not a newly observed tool error.

## Minimum correction proposal — product decision required

The existing public contract cannot complete this exact chain from the two preserved sessions. Correcting a report or changing the next capture's session is insufficient. Removing the same-session check would also be insufficient because publication, Diagnostic and recovery independently enforce it.

Recommended bounded extension: allow an **explicit recovery continuation** to reference these original physical results without changing either result's identity. It must bind the original attempt/checkpoint, Diagnostic/source declaration, exact before/after run and evidence IDs, source intent/snapshots/builds/ELFs, workspace/project/target/probe and mailbox transport. An expired predecessor stays immutable; a new continuation has its own finite lifetime and grants no hardware authority. A continuation association is not a PASS and must still require the missing real P4 Monitor window, analysis and FixVerification.

Affected product areas, subject to a self-contained specification before implementation: existing acceptance recovery models/workflows and their CLI/MCP adapters; Diagnostic pair/verification binding; Monitor compare/bundle binding. The same verified association must serve all consumers. Preserve the low-level physical publication/provenance checks, original manifests, default same-session behavior and replay behavior. No firmware, probe backend, sampler timing, installer or new diagnostic framework is in scope.

Necessary offline evidence: original publication hashes unchanged; no-association cross-session rejection; exact valid association through persisted recovery/Diagnostic/Monitor paths; rejection of swapped runs, wrong probe/target/build/snapshot/declaration, replay evidence, stale checkpoint and unauthorized/expired actions; unchanged same-session and replay behavior. Reuse existing tests/public readers. A fixture verifies software behavior only. One Luna/max implementation owner and an independent complete-diff review are required; no full release matrix is justified by this change alone.

This proposal changes an explicitly approved identity/recovery contract. It is **not approved or implemented** by this report. Do not weaken validators or select a new hardware campaign silently. If the extension is approved and accepted, and the then-current programmed target satisfies the actual sampling prerequisites, schedule the missing Monitor observation. Reusing the successful programming is the intended path, not a claim that future board state or sampling readiness is already verified. No reflash is proposed to repair bookkeeping; any additional hardware scope would require its own evidence-based decision and authorization.

The existing capture entry `D:\codex-tmp\t10-d3-20260914\entries\t10_monitor_entry.py` is reusable, but its old configuration pins the previous runtime/toolkit and its hardcoded session is P3. It must not run unchanged or be relabeled after capture. The independent entry preflight verified current imports from the explicit program-diagnostic runtime; no Monitor runtime or connection was started.

Historical attempt7, T9, 100ms, FullFault and P3 evidence remain scoped as recorded. T10 G/H and VS10-A Tasks11/12 remain incomplete.

Independent read-only review by `t10_continuation_review` confirmed the predicates, reached-stage boundary and SOP consistency. Its requested cause/forward-readiness wording corrections are incorporated above. This review accepts the offline finding and procedure clarification, not the proposed new product contract. No tests or hardware operations were added for these documentation changes.
