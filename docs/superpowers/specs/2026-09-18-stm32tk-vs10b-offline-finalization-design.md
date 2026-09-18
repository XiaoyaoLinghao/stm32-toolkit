# VS10-B completed-evidence offline finalization

Status: DRAFT / USER_APPROVAL_PENDING. This proposal follows the user's request to continue after card05. It changes the B-only acceptance continuation boundary explicitly excluded by the original B specification; it is not an implementation, deployment or acceptance claim.

## Baseline, owner and scenarios

Accepted local integration base: `abdc2fb5dbde2b6643e26d42e29c7ad6db72f921`, branch `codex/STM32TK-1002-CUBEMX-REAL-BOARD-integration`. Deployed source remains `12df4fe0569104d6f0e7a827496341d999e1f3ea`. Primary owns this design, integration and acceptance; one Luna/max owner will implement and test after approval; primary independently reviews the complete diff. No remote action or implementation-ownership exception is authorized.

Three runnable scenarios:

1. A B physical attempt reached revision6, then expired before its final checkpoint. Both physical Target runs, both Monitor windows, source correction, analysis and Diagnostic FixVerification already exist and passed. Explicitly bind that exact completed evidence graph to a fresh, offline-only finalization attempt and complete it without changing the predecessor or generating physical evidence.
2. Missing, corrupt, replay, cross-session or incomplete evidence cannot create a binding or completed root. A resolved Diagnostic alone, a passed flag alone, or a caller-supplied evidence summary is insufficient.
3. Exact retries and fresh-process reads preserve immutable records. An expired new offline attempt can be followed by another fresh attempt referencing the same authenticated proof; it cannot renew source or hardware authorization. Existing replay /1, physical A /2, A continuation /3 and physical B /4 behavior and canonical bytes remain unchanged.

Non-goals: hardware access of any kind; firmware changes/builds; Monitor acquisition/publication/comparison; new Diagnostic events/plans; cross-session B repair; unfinished B repair continuation; retroactive deadline extension; changing old records or clocks; a workflow engine, scheduler, new command/tool family, global timeout increase, packaging matrix or 1.0 release.

The prior failure remains INFRASTRUCTURE / primary dispatch timing. This extension solves reuse of independently valid completed evidence, not an alleged flash or board defect. Original B `target-fix-verified:300` and its timeout remain true.

## Frozen public boundary

Use the existing CLI `scenario attempt begin --continuation-file`, checkpoint/show/resume, and existing corresponding MCP operations. Normal begin without continuation remains unchanged.

Allocate these previously unimplemented identities, only for this closed B profile:

| Item | Value |
| --- | --- |
| Request | `stm32-physical-continuation-request/2` |
| Immutable proof | `stm32-physical-continuation/2` |
| New attempt | `stm32-acceptance-attempt/5` |
| New policy | `stm32-physical-continuation-policy/2` |
| Scenario/version | `new-cubemx-physical-repair` / `1` |
| Origin/source/transport | `cubemx` / `physical` / `mailbox` |

Repository inventory found attempt /1-/4 and continuation request/proof/policy /1. One test currently uses request /2 as an unknown-schema negative; move that negative to a still-unknown value and add explicit wrong-scenario /2 rejection. Do not reinterpret any existing /1 payload.

Request /2 has exactly two forms:

- `bind`: existing /1 bind fields (`schema`, `kind`, `predecessorAttemptId`, `predecessorCheckpointId`, `predecessorEvidenceId`, `fixedAfterTestRunId`, `fixedAfterEvidenceId`, `diagnosticRevision`, `diagnosticEventHead`) plus required `fixVerificationId`.
- `reuse`: `schema`, `kind`, `continuationEvidenceId`.

Both forms require original B before-session context, B scenario/version and a new caller-selected attempt UUID. Every other key/profile/schema combination fails closed. Identifiers keep existing bounded UUID/native-run/digest/revision domains.

Proof /2 retains the exact /1 proof fields and adds `fixVerificationId`; it represents a completed Target/Diagnostic repair-evidence association, not authorization or overall VS10-B acceptance. The original predecessor, Diagnostic, before/after TestRun and source-diff authorities supply all identity fields. Callers cannot supply physical flags, source identity overrides or acceptance status. The separately published Monitor analysis bundle is deliberately outside this proof: it is not a parent of the existing VerificationPlan/FixVerification. Its presence, integrity and exact lineage remain a separate mandatory VS10-B final-acceptance gate below.

New attempt /5 uses the same field set as the existing two-revision continuation attempt, with the fixed B profile and proof /2. Rev0 is IN_PROGRESS / verification-pending, rev1 is COMPLETED / target-fix-verified. `fixVerificationId` is null at rev0 and the proof's exact already-passed ID at rev1. No source authorization/action fields exist. The policy fixes a 900-second offline verification window from actual rev0 publication; rev1 retains this deadline and actual completion publication time. Scenario/policy digests use existing canonical hashing over the closed B profile and two-stage descriptor; old digests never change.

## One authenticated graph and publication lifecycle

Bind must authenticate the complete original /4 chain at latest revision6, original B descriptor/policy, firmware-built-after stage, precise historic source authorization/intent/declaration and before/after build/ELF/input bindings. The predecessor deadline must already have elapsed; it remains historical input and is never renewed. Completed, replay, foreign-profile or substituted predecessors fail.

The pinned current Diagnostic must be the predecessor's same-session Diagnostic, RESOLVED, with a matching existing PASSED / VERIFICATION_PASSED FixVerification/1. Authenticate its exact revision/event head/checkpoint, original failed run, single source declaration, matching VerificationPlan/1, fixed run, required analyses/markers and their evidence through existing readers. The /4 revision6 stageOutputs diagnosticRevision/diagnosticEventHead must equal the historical source authorization's pinned revision/head; the authenticated event prefix at that revision must have exactly that digest. The final RESOLVED revision must be strictly later and descend from this prefix, with the same source declaration, exact expanded intent and authenticated action digest. Same session/declaration alone is not proof of this ancestry. Require the original same-session physical comparison contract: authenticated physical run-ref/2 on both sides, VALID / COMPLETED / changed=true analysis, required pairs/quality and exact source-change lineage. A continuation-dependent or unrelated FixVerification is outside this first extension.

TestRunRepository and existing physical readers must prove before=failed, after=passed, target/physical/mailbox, identical original workspace/logical project/session/probe_id/target_id and compatible transport_config_digest/mailbox inventory. Each run's flash_session_id and lease_id must match its own original publication; they are not required to equal the other run's values. Distinct actions, leases, builds and ELF hashes remain original. Do not infer silicon UID. Bind the current declared after firmware facts using the existing immutable firmware-facts loader; do not combine unrelated snapshot reads.

The proof references the already-resolved Diagnostic and its existing evidence graph. No prior Diagnostic/Monitor record references this new proof, so it introduces no back-edge. Proof envelope identity is the original failed-before identity; operation/artifact/root family reuses physical-continuation with schema-discriminated readers. Parents are exactly predecessor evidence, pinned Diagnostic evidence, before evidence, after evidence and source-diff evidence, ordered and deduplicated as in /1. The pinned Diagnostic already retains its verification/analysis references.

Authenticate proof content, canonical artifact, envelope, parents, roots and every bound authority on bind, reuse, show/resume and final checkpoint. `finalization.py` owns only the closed models and pure payload rules. One complete B graph reader belongs in the existing upper-level `recovery_workflows.py` adapter, which already imports Diagnostic workflow validators. It reuses the existing physical-chain, declaration/pair, analysis/transcript and marker validation functions; it must not call the A-only proof reader, whose Keil/cross-session/pre-verification assumptions are different. No successful-reader stubs or trusted saved response flags. This B proof has no new Monitor/Diagnostic consumers, so there is no need to move their full readers to a new shared layer or introduce an import from a low-level model back to a workflow.

Bind/reuse/begin/checkpoint publication must first hold the existing DiagnosticStore `_store_lock` and use `_load_chain_locked` to load and validate the pinned RESOLVED session, current revision/head, historic authorization prefix, FixVerification/plan and complete analysis/marker graph. Retain that D lock while acquiring the EvidenceStore `_mutation_lock` in D→E order. All complete Diagnostic graph validation happens under D before acquiring E. Inside E, reuse the already-loaded session and recheck only immutable proof/attempt authorities, latest predecessor/CAS, current firmware binding and the new-attempt deadline before publishing. Never call public DiagnosticStore.load(), a repairing Diagnostic reader, or a workflow that reloads/mutates Diagnostic while holding E. Read-only proof consumers release any short atomic E read before acquiring D; they do not invert the order. Use the established continuation publication pattern rather than another locking mechanism.

Exact idempotent retries may return an already-published identical result after expiry; conflicting IDs, mixed inputs, late first publication or changed authorities cannot publish a new accepted root. Fresh current-firmware checks gate new publication, not historical reads of already accepted immutable records. Preserve old roots/artifacts byte-for-byte.

The final checkpoint takes the existing fixed Target and FixVerification arguments, requires exact agreement with the authenticated proof and publishes only new /5 revision1. It cannot call hardware, build, Monitor or Diagnostic mutation. Expired /5 records remain expired; a new UUID can reuse the same proof after complete revalidation. Routing is exact: B plus request/2 enters this binding; schema/5 alone selects its checkpoint/show/resume reader. `authorize-source-change` on /5 returns the existing STAGE_INVALID error before generic or physical dispatch. Mixed A/B/request schemas and unknown schemas fail closed without entering another parser.

Reuse existing errors: malformed/unknown/mixed input is `ACCEPTANCE_ATTEMPT_INPUT_INVALID`; valid authenticated proof used in the wrong context is identity mismatch; missing/corrupt authority is evidence-integrity failure; stale revisions/conflicting UUIDs use current conflict semantics; late publication is attempt timeout. Do not broaden error translation in unrelated adapters.

## Implementation and validation boundary

One implementation owner covers the bounded finalization models, acceptance workflow routing, minimal MCP closed-input union/exports and affected existing tests. Reuse upper-level validators in the existing acceptance adapter; do not change A continuation consumers or copy a second evidence engine. The concrete file list and test ownership are frozen in the companion plan before dispatch.

Required evidence is offline: one persisted B chain using real store structures through bind → new-process read → final checkpoint → new-process read; expired-new-attempt reuse; unchanged legacy paths; and focused rejection/race tests for identity, predecessor/Diagnostic drift, evidence corruption, CAS and deadline at publication. Assert no backend/supervisor/service creation or Diagnostic/Monitor mutations. Preserve original canonical bytes and failure evidence.

After software acceptance, perform one offline application first against an isolated copy of card05's real data, with original-file hash verification, then use the reviewed public candidate against the canonical B evidence store only within the approved application boundary. New completion is explicitly an offline finalization of earlier physical results. It is not a second physical test or proof the original 300-second checkpoint passed. Independently authenticate the existing Monitor analysis bundle with its existing reader: root/payload/parents, before/after Target references, source declaration, analysis refs and session/probe/target lineage must agree with this finalized graph. A missing, swapped or corrupt bundle blocks overall VS10-B ACCEPTED even when /5 is COMPLETED; do not imply that /5 proved that bundle. Creation/NORMAL/IDE and other original B criteria likewise remain separate final gates. No bundle regeneration or new Monitor mutation is required.

All new worktrees, caches, tests and evidence remain under `D:\codex-tmp\v10b-0918`; no cleanup of preserved physical evidence. This draft authorizes nothing beyond offline design preparation until the user approves this contract and the companion plan.
