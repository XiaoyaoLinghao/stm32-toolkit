# Diagnostic store and input integrity regression design

Accepted base `848dc0a79e3e5741ef0528cfbfca533345128a51`; the preceding Monitor slice is accepted. This is a test-only continuation of the user-authorized v1.3.1 goal. Primary owns specification, orchestration, complete independent review and acceptance. Claude Code CLI using the current provider owns tests and delegated execution. Product Python has not changed since the native full-matrix measurement.

## Contract

Diagnostic readers must fail closed on missing/corrupt authority without inventing, repairing or rewriting state. Workflow input and generated IDs/timestamps must be validated before publishing mutations. Add distinct public behavioral tests, not private-guard coverage tricks.

- Missing roots: append, resolve_operation, resolve_accepted_operation and load_durable return DIAGNOSTIC_NOT_FOUND and leave the root absent; inputs otherwise model-valid.
- Incomplete roots and invalid lock size: empty root, missing lock or sessions, and a two-byte lock are DIAGNOSTIC_CHAIN_CORRUPT on read, with byte/layout snapshots unchanged. Compare existing create-path tests; this slice tests read refusal and no repair.
- Bounded creation intent: a canonical model-valid event zero of the wrong type, a mismatched session binding, or the actual session.after_prepare crash prefix cannot become an invented host/target mode. Use real stores and public fault_injector hook; no reader/validator replacement.
- Stored chains: canonical model-valid events with a repeated creation transition, wrong prior digest, or repeated investigation start are rejected during load as corrupt. Use distinct operation IDs to reach the intended state/digest boundary. Verify no checkpoint repair or evidence rewrite.
- Non-canonical operation requests (unsupported object and NaN) fail as INVALID_EVENT before incomplete-root layout handling, preserving all authority.
- Public workflow context rejects wrong context type or nonstring session before filesystem work. The documented ID/time producer seams may return invalid values; real project/test-run/evidence/model/chain validation remains in place, and no diagnostic event/evidence mutation is published. Use existing real _make_run fixture and compare persisted authority, not a claim that fixture creation produced no directories. Test invalid type and malformed string when they take distinct short-circuit branches.

The read-only gap audit and primary disposition are planning aids, not authority to omit platform obligations or change denominators. Cases truly blocked by an upstream validator should be explained rather than forcing that validator. Do not duplicate existing cap scenarios, add thousands of fixtures or claim naturally occurring filesystem races. No statement-only or estimated branch gain counts as measured coverage.

## Scope

Only new files tools/stm32-toolkit/tests/test_diagnostic_store_integrity_boundaries.py and tools/stm32-toolkit/tests/test_diagnostic_input_integrity_boundaries.py. Existing authored helpers may be imported but not edited. No product, existing tests/fixtures, dependencies, configuration, documentation/Skill or release tooling changes. Primary owns report/spec/plan updates. No original project, hardware/probe/backend, installation, network, provider settings, remote ref or artifact mutation. Return genuine product defects for a scope decision.

## Acceptance

Primary reviews the complete diff and freezes a CodeHead. File-only completion does not mean tests passed. Separate verified native PowerShell runs all new files plus complete diagnostic_store/workflows/end_to_end/events groups under a source-bound manifest; primary independently runs both new files and diagnostic_end_to_end in a clean exact-head tree. Preserve first failures, strict tool boundaries and exact single-command verification. Native coverage can supplement prior data only after all required affected cases pass on unchanged product bytes. Keep per-package test identities, raw hashes, fixed source membership and permanent floors. No installed VS Code, release or hardware acceptance follows from this test-only slice.
