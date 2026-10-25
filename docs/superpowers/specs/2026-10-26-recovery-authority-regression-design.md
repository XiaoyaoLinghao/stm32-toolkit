# Offline recovery authority regression design

Accepted base `41925c6e915a8af41c350bd08113e82bed41d1ed`. This test-only slice continues the authorized v1.3.1 qualification goal. Primary owns requirements, orchestration, complete independent review and acceptance; local Claude Code CLI with existing configuration owns test writing and delegated execution. No product, hardware or remote changes are assigned.

## Contract

Public acceptance readers/checkpoints/source authorization must reject corrupted attempt metadata, wrong TestRun identity/state, stale checkpoints and inconsistent stored history without publishing or repairing authority. Physical-marked schemas here are synthetic offline fixtures; they provide no hardware qualification. Existing model/chain/snapshot/TestRun/Diagnostic/evidence validators must remain real. Only the existing fresh-firmware-facts producer seam may be used for the synthetic project; no predetermined validation outputs.

Correct stage sequence: begin rev0; project-materialized rev1; firmware-built-before rev2; target-failure-observed rev3; diagnosis-completed rev4; source authorization rev5. All input scenarios must reach their intended stage. The read-only audit has off-by-one stage descriptions corrected in the primary disposition and is not itself an approved specification.

- Invalid rev0 envelope attempt metadata (array or non-string schema) must return evidence-integrity failure through show, resume, checkpoint and source authorization. Use genuine rev0 fixture with rehashed untrusted envelope/root input.
- At rev2, target-failure-observed rejects missing native runs as evidence-integrity failure; replay-operation or passed runs as output-invalid; mismatched build or input snapshot as identity-mismatch. Use real published synthetic TestRun graphs, never forged in-memory validator decisions. Replay-operation rejection may precede transport checking; claim only the observed contract.
- At rev3, diagnosis-completed rejects wrong before-source digest, no-op source intent and a prematurely changed working source as identity-mismatch. Use a real bound diagnostic session and preserve/restore the owned source. Do not duplicate existing out-of-source direct-unit coverage.
- At rev4, a retry with expected revision2 is rejected as revision-conflict without appending anything.
- Stored model-valid tampering: rev0 opened/updated mismatch with valid deadline; latest rev1 beyond predecessor deadline; latest rev1 rewriting prior project-model digest; latest authorized rev5 changing expanded source intent; and current fixture model origin drift keil→cubemx. The first four fail integrity; origin drift fails identity. Preserve valid shape/digests/parent bindings so the relevant chain contract is evaluated. Restore authentic inputs and prove successful reader recovery. No automatic repair or actual source authorization outside the synthetic fixture.

Snapshot persisted authority after deliberate input preparation and before each public operation. Compare unaffected attempt/envelope/root/Diagnostic/TestRun bytes; no surprise new revision. Explicitly account for envelopes intentionally introduced as untrusted input. Test count is secondary to reachable independent behavior. Explain upstream refusals or duplicates instead of patching validators or inventing a later-guard PASS.

## Scope

New file: `tools/stm32-toolkit/tests/test_acceptance_physical_integrity_boundaries.py`. The sole allowed existing-file change is `_prepare_public_physical_attempt` in `test_acceptance_physical_recovery.py`: support stopping at revisions0,2,3 while preserving prior1/4 semantics and return tuple. Existing assertions, other helpers and fixtures stay unchanged. No product/config/dependency/docs/Skill/tooling changes by the implementer. Primary owns reports/spec/plan. No historical archive reconstruction, original project edit, installation, probe/backend/hardware/network or remote mutation.

## Acceptance

Primary reviews complete base-to-CodeHead diff. Separate verified native PowerShell runs the new file and complete physical recovery, recovery workflow/model, continuation, finalization and continuation-adapter suites, with exact names verified beforehand. Primary independently runs all new cases and relevant model/public integration coverage in another clean exact-head tree. Preserve failures; exact single-command execution and no denied-tool fallback. Existing fixture consumers must pass with prior1/4 behavior intact.

Native reconciliation supplements accepted coverage-diagnostic-a only on unchanged product bytes, fixed source membership/denominators/floors and distinct package-qualified nodes. Any new skip is unresolved unless an actual named platform obligation is explicitly reviewed; no arbitrary deferral. No installed VS Code, release or hardware acceptance follows from this slice.
