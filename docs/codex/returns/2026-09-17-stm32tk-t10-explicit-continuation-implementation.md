# T10 explicit continuation: offline implementation

Status: software slice ACCEPTED by independent review. This does not complete T10 or VS10-A.

Accepted base: `9975bcd3466f949c56801c81d618b2b57493a5a7`. Accepted CodeHead: `30ceae845f7770dfd01db90104bd01e5c3a70894`. Specification and plan: [design](../../superpowers/specs/2026-09-17-stm32tk-t10-explicit-continuation-design.md), [plan](../../superpowers/plans/2026-09-17-stm32tk-t10-explicit-continuation.md).

Primary owns design, orchestration and integration. The user explicitly approved the bounded temporary primary implementation exception after the original Luna/max writer stopped responding; its partial work was retained. The separate Luna/max `continuation_contract_tests` worker owns the contract test contribution. `t10_continuation_review` independently reviews the entire accepted-base-to-CodeHead diff and runs verification in a clean detached worktree. No implementation self-approval, remote mutation, deployment or hardware operation is authorized by this slice.

## Behavior delivered

P3 and recovered P4 retain their distinct original physical identities. An explicit immutable `physical-continuation` proof authenticates the original v2 revision6 chain, historical source authorization, pinned Diagnostic declaration and exact original TestRuns. It does not rename sessions or create an action authorization. Creation checks current Diagnostic/predecessor state under the existing Diagnostic-before-Evidence lock order; subsequent readers authenticate the fixed historical prefix so legitimate later verification events remain readable.

Existing attempt begin accepts a closed bind/reuse input. A separate v3 attempt has a fixed 900-second completion window and two states. Expiry publishes no completion root; a fresh UUID can reuse the accepted proof and valid FixVerification. Existing accepted exact retries remain stable. Default v1/v2 paths, physical provenance readers and tool inventory stay unchanged.

Monitor compare/bundle explicitly consume the same proof, preserve each side's session, and publish versioned analysis lineage. Diagnostic VerificationPlan v2 binds that proof and verifies the original pair through plan/start/marker/complete and persisted event replay. The original Diagnostic owns completion. Final checkpoint/readback revalidates the exact PASSED verification and associated analyses. The shared proof reader does not call high-level DiagnosticStore loading, avoiding recursive reference validation. GC registers the proof root and retains its parents through existing reachability rules.

Changed product scope: the bounded acceptance continuation helper/workflows, Diagnostic models/events/store/workflows, Monitor analysis/workflows, existing CLI/MCP adapters and GC root registration. Firmware, probe code, physical publication provenance and deployed runtime were not changed.

## Offline verification

Environment: Windows PowerShell 7.6.6; CPython 3.12.10 at `C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe`; pytest 8.4.2. Implementation root `D:\codex-tmp\t10c-0917\impl`; independent review root `D:\codex-tmp\t10c-0917\review`. `PYTHONPATH` uses each respective tree's Toolkit and Monitor `src`; `PYTHONDONTWRITEBYTECODE=1`, `TEMP/TMP=D:\codex-tmp\t10c-0917\env`, `python -B -m pytest`, `-p no:cacheprovider` and fresh short basetemp children. The installed D: runtime is not a test environment and was not modified.

Primary evidence at `D:\codex-tmp\t10c-0917`:

| Check | Result and preserved evidence |
| --- | --- |
| Existing physical recovery; FixVerification model/events/workflows/CLI/MCP; Monitor analysis model/workflows/CLI | 254 selected. Initially 253 passed; one reflection assertion expected only old dataclass fields. Updated the assertion for optional versioned fields while retaining exact v1 serialized payload assertions; that node then passed. `regression-1.log`, `lineage-model.log` |
| New CLI/MCP continuation adapters plus existing acceptance recovery CLI/MCP | 13 passed, exit0. `adapters-1.log` |
| Existing acceptance recovery model/workflows | 51 passed, exit0. `recovery-defaults.log` |
| Existing physical publication identity checks: foreign session, replay labels, coherent reference drift, probe mismatch, independent sequential leases | 13 passed, exit0. `physical-identity-regression.log` |
| Luna contract tests | Initial four passed; three additional nodes cover stale head/terminal predecessor, reordered rehashed parents and six readable wrong after identities; one additional readable replay input rejection passed. `t2/continuation-new-boundaries.log` preserves exact commands/output/exit codes for the added nodes |
| Persisted cross-session E2E | One passed in 60.33s, exit0. `continuation-e2e-1.log` |

The E2E executes public bind, a fresh CLI process, each side's Monitor publication, missing-proof rejection, compare/bundle, original Diagnostic plan/start/marker/complete, and fresh Diagnostic/proof reload. It forbids high-level DiagnosticStore readers during direct proof reload. It then expires the clock after the completion envelope but before its root: no completed root is accepted. A new attempt reuses the same proof and completed verification; concurrent checkpoint callers converge and exact completed retries remain valid after expiry. Original v2 roots remain byte-identical, and GC reaches the proof and all five parents. These are software fixtures, not new hardware evidence.

Independent first review covered the entire accepted-base-to-`40d50239db030206bb7bfd004f935597f5d9665a` diff in a clean detached tree, with `git diff --check` passing. Independent results: E2E 1 passed in 62.66s; contract tests 8 passed in 68.97s; adapters 6 passed in 2.85s. Only the existing TestRunPublisher collection warning remained.

The verdict was REVISION_REQUIRED for two P2 findings. The shared Diagnostic replay reader checked only partial analysis identity, and valid proofs used in a wrong consumer context were misclassified as corrupt evidence. The correction authenticates the closed analysis fields, complete lineage/metadata/root, and both original physical transcript/reference graphs against the proof's TestRuns, reusing Toolkit's existing pure Monitor wire validators. It retains acyclic loading. Independent E2E against this reader correction passed in 73.61s (`r2/test_continuation_monitor.log`); review covered through `76f62948cf84b1881b985692c842a850a12d7f58`.

That second review found the same error-category distinction still missing in Diagnostic adapters. In accordance with the two-round rule, local patching stopped for a complete consumer-boundary audit. The specification now freezes the four-adapter mapping and explicitly distinguishes external context mismatch from contradictions inside an authenticated persisted graph. One bounded correction applies that mapping to both Diagnostic workflows and both store consumers; Recovery and Monitor already conform. This preserves the pure analysis error contract and introduces no hardware safety code. The final verification below covers that correction.

Final independent verdict: ACCEPTED, no remaining findings, for the complete accepted-base-to-CodeHead diff. The clean review tree was at the accepted CodeHead; `git diff --check` passed. Three new nodes ran independently against that exact tree:

- `test_acceptance_continuation.py::test_public_begin_reuse_classifies_identity_malformed_and_tampered_proofs`: 1 passed in 12.96s, `r3/begin.log`.
- `test_continuation_monitor.py::test_diagnostic_store_rejects_self_consistent_forged_continuation_analysis_references`: 1 passed in 19.07s, `r3/forged-analysis.log`.
- `test_continuation_monitor.py::test_diagnostic_continuation_error_mapping_for_public_plan_and_store`: 1 passed in 18.41s, `r3/mapping.log`.

These cover public Recovery/Monitor/Diagnostic classification, self-consistent forged analysis/run/lineage/window links through direct DiagnosticStore append, corrupt proof/analysis roots, and a valid proof with an incompatible external plan. Existing 8 acceptance, 6 adapter and the 73.61s E2E results remain applicable to unchanged behavior. Luna's initial test-setup failures confused a proof evidence ID with its content-root ID; fixture addressing was corrected, with original logs preserved under `t3`. Product code was not changed to satisfy those setup failures. The temporary primary implementation exception is now closed; future product changes return to normal Luna/max ownership.

## Existing real evidence, copied offline

Only the existing `evidence` and `diagnostics` trees were copied from `D:\stm32tk-data\fault-controlled-20260911\projects\d7b137149685154d159f2f0d` into `D:\codex-tmp\t10c-0917\real-data`. The firmware project was read-only. All 68 original files in both the business store and the copy retain their original hashes: `original-evidence-hashes.json`, `original-evidence-unchanged.json` and the final `original-evidence-final-check.json` (zero mismatches).

Real P3 session is `vs10a-t10-d3-20260914-01`; real P4 session is `p4-recovery-20260917-03`. The source authorization pins Diagnostic revision5; the matching declaration is at revision6. The reader proved the ancestor relation without rewriting either revision. On the isolated copy, bind created proof evidence `b37a0bb8922af9207ae779e1ea589db16ee1159e4ad2c2a4e45d0271cb9fa505`, content ID `19323c5be2d370667255c69e352491278ce6672caaf448fe9a1f5dad79e7099b`. Public CLI in another process returned the identical v3 attempt `496a2528-f42e-476a-b015-229210c7ca53`. This attempt's deadline was `2026-09-17T05:45:05.425043Z`; it is an offline copy record, not a live authorization or real completed T10 attempt. Exact requests/results are `real-bind-request.json`, `real-bind-result.json`, `real-cli-retry.json`.

No actual P4 Monitor evidence was created or replaced. The real Diagnostic and original attempt were not mutated. Historical P4 native PASS/user LED observation, attempt7, T9 and prior applicable sampling evidence remain as recorded.

## Deployment and acceptance boundary

Deployed source remains `7d22c149d5f83ded14024569bce9a17734b2b7d1`; runtime remains `D:\stm32tk-data\fault-controlled-20260911\candidates\program-diagnostic-20260917\runtime\0.9.0`. This slice is not deployed. Real T10 G/H still require the missing P4 Monitor window, authenticated analysis/Diagnostic completion and final checkpoint; VS10-A Task11/12 remain incomplete. Future hardware work requires its own current preflight and authorization. Do not repeat P3/P4 flashing to reconstruct bookkeeping.

The [standard test procedure](../../testing/standard-test-procedure.md) now specifies bind/reuse, original-session publication, versioned plan/analysis binding and expiry handling for this case. Pure report/state updates do not trigger a complete retest.

During finalization the former integration directory `D:\workspace\stm32tk-1001-legacy-hardware-impl` was observed missing (Windows process creation error267); Git marked its worktree registration prunable, with the integration branch still at the plan commit. The earlier sole uncommitted amendment was the GC scope line already included in this candidate's committed plan. This slice did not delete that directory, recreate it or prune the stale registration. The current source worktree remains `D:\codex-tmp\t10c-0917\impl`, and the independent review worktree remains its `review` sibling. Original firmware, business evidence and D: runtime paths remain present. The default checkout is not used to infer acceptance state.

Cleanup owner: primary. All generated output is under `D:\codex-tmp\t10c-0917`. Native, exact-path deletion requests for `b1`–`b3`, and later separately for the newly completed `b4`–`b6`, were rejected by automatic approval policy with only `blocked by policy`; neither executed or was retried through another route. All six directories remain on hold. Worker `t`/`t2` and independent review roots, implementation/review trees, the real evidence copy and minimum logs remain attributed to this slice. No business evidence, old worktree or prior cleanup hold was deleted.
