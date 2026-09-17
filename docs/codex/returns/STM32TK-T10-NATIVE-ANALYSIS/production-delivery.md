# T10 native analysis deployment and production G/H

Deployment source: `2c6aedc6f9e85e9db43d2895d26395387c127a6b`. Accepted product CodeHead: `2c00d85abc739b404bae0f37e81e8f89263ed8a4`; correction base: `6a8da073d8e79595acad21d5f2367c8393ac9597`. The primary performed this authorized integration run; the previously accepted Luna/max implementation is unchanged. Local branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`.

The user's “开始部署，然后继续进行测试” authorized this deployment and completion of production G/H using existing captured evidence. No hardware enumeration, connection, sampling, control, reset or flashing occurred in this run. No remote mutation occurred.

## Deployment

One LF package build, bundle verification, missing-runtime Check, Bootstrap and final Check passed. The final runtime is **healthy/matching**. All 147 installed Toolkit/Monitor files match the verified wheels; the real final-path `pyocd.exe --version` exits 0 with 0.45.1.

- Active runtime: `D:\stm32tk-data\fault-controlled-20260911\candidates\native-20260917\runtime\0.9.0`.
- Reusable ToolkitRoot: `D:\codex-tmp\t10g-0917\extracted\stm32-toolkit-0.9.0`.
- Manifest SHA256: `0df2711f8d16cbe6ad663a1cda2eb45d80132a2a19e14fb83d4e16974ee6d30b`.
- Runtime-state SHA256: `fb19f130596be014a90efae6f2195883556f4595ec73b65a6297031424c381c6`.
- Evidence root: `D:\codex-tmp\t10g-0917`; `logs/check-final.json`, `evidence/installed-bytes.json`, bundle/build/bootstrap logs retain the actual results.

The previous continuation candidate remains available. Its runtime-state hash is unchanged; this is not a claim that every previous runtime byte was checked. Generated artifacts are confined to the approved run root and the established candidate runtime root.

## Production result

Public installed CLI calls operated on project `D:\codex-tmp\t10-d3-fw`, business root `D:\stm32tk-data\fault-controlled-20260911`, workspace `d7b137149685154d159f2f0ded85852248e4a2de1fe2813a788aa9bb54c2fd74`, and original evidence session `vs10a-t10-d3-20260914-01`. The separate Diagnostic ID is listed below. These are production records, distinct from the earlier real-evidence copy used for software acceptance.

The request/2 preserves both full original references and all 300 positions, `minimum_valid_pairs=297`, native uint register decoding and the 5,000,000ns pairing limit. Compare returned **300 valid pairs, 0 exclusions, VALID/COMPLETED, changed=true**. The canonical publication was saved and reopened through the installed loader before successful bundle export.

| Record | Actual production value |
| --- | --- |
| P3 failed Target run | `target-v2-53b0c81ffeb50ab65bd6c0ad815ad273` |
| P4 passed Target run | `target-v2-d5b0e440822671ba2812a367bfedf2f6` |
| Immutable continuation proof | `6af4ea4fddebe07a0a2899ce1adf142c869ddd10d5d8645f5254ca61f9d4e4be` |
| Analysis ID | `d8a82a8962954f90bfac50d3d03709ad332922c83c8e18e34c12d28dcb3a466b` |
| Analysis evidence ID | `3a8df616b2f8c7454d5559862ef8104b6248a49c4e98b63ab55f97309f142942` |
| Diagnostic | `2781df6812f2dc0ba067e0b1b9d07b5a`, revision 10, **RESOLVED** |
| FixVerification | `dfbe6d789c79d3379f0b608f1526096c436f941d7d5eb6e807a3f911bea420e7`, **PASSED** |
| Fresh v3 attempt | `ee7b50a4-22f5-4547-99ed-344582bcb853`, revision 1, **COMPLETED**, `target-fix-verified` |

Verification plan/start/marker/complete used distinct recorded operation IDs and Diagnostic revisions 6–9. Complete binds both original Monitor operation IDs, compare/bundle and the actual new Diagnostic operations. A fresh reuse attempt was begun only after verification passed; its checkpoint binds the actual production FixVerification. New CLI processes show/resume authenticate the stored graph: authoritative=true, COMPLETED, timedOut=false, no next stage or action digest. A separate fresh Diagnostic read confirms RESOLVED/PASSED. Exact arguments, stdout/stderr and exit codes are retained under `evidence/`, `results/` and `logs/`.

`results/preservation-check.json` confirms all 85 pinned original production files are unchanged. The old INVALID analysis and expired attempts remain intact. Attempt 7, T9 and earlier 100ms/physical evidence retain their original scope. This run does not claim a new LED observation.

## Classification and acceptance boundary

Two local integration-entry mistakes were corrected without repeating passed product operations: preparation initially used snake_case for a camelCase serialized proof key (`KeyError`, before Diagnostic mutation); the first final `diagnose show` used `--tool-session-id`, whereas that read-only command requires `--session-id` (parser exit 2). Corrected preparation and read both passed; original error logs and arguments are retained. Neither was a hardware failure. Future invocation preparation must use each subcommand's actual help and the observed serialized schema.

Production **G/H is complete**. This does not by itself accept every original Task 10 clause or VS10-A. The original Task 10 evidence requirements must be reconciled individually; Task 11 formal campaign evidence reconciliation and Task 12 complete-range independent review remain pending. No repeat hardware is justified merely to confirm the already sufficient G/H data. Any newly identified physical evidence gap requires its own precise scope and authorization.

Independent read-only reviewer `native_entry_review` accepted the production G/H evidence: it separately rechecked all 147 installed package hashes, the 85 original files, unchanged previous runtime-state, production argument roots, original publication/request/bundle equality and the final stored graph. No E2E, deployment or hardware operation was repeated. Its only report wording correction distinguishes the evidence session ID from the separate Diagnostic ID; the corrected wording above does not alter any product or evidence result.

Independent clause reconciliation found a concrete remaining **Task 10 Step 3 gap**: the production Diagnostic has only application candidate `06b4053634342aef290bdfa11f8cd7bb`, still open/unrated with no supporting/refuting assessments; its two observation results only establish failed run/case status. The timer/interrupt-stopped and GPIO/board-path alternatives have no corresponding hypothesis assessments. The new change-observed marker does not replace those assessments. Existing captured `testtime` and PE4 changes, P3 PE3 held-low data, and P4 PE3/PE4 transitions are available for a separately scoped offline reconciliation; they do not retroactively prove that the required diagnostic process occurred. Preserve the completed lifecycle and original event chain. Next prepare the explicit missing-assessment remedy using existing evidence before considering any new hardware. See the original plan Step 3 and `2026-09-14-stm32tk-t10-d3-diagnostic-lineage.md`.

The clean run-only packaging worktree was removed through `git worktree remove` after resolving its exact path and verifying the approved root and absence of reparse points. The temporary directory is empty. Candidate bundle/ToolkitRoot, installed runtime, original and new evidence, and minimum error logs remain available. `evidence/cleanup-plan.json` and `cleanup-result.json` record the scope and outcome. Prior t10c/t10d/t10n cleanup holds remain untouched; no deletion bypass or retry occurred.
