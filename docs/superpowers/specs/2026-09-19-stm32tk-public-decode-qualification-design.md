# Public evidence decoding qualification

Accepted base: `63602bf6dbd2ad5ff2b676678695767e000bbb2a`.
Primary owns design, integration and acceptance. One Luna/max implementation
owner adds tests; a separate reviewer reviews the complete diff. This is a
bounded qualification slice within the authorized 1.0 goal, not a feature or a
change to the mandatory release threshold. No remote action is authorized.

## Caller scenarios and contracts

The retained public-decode-contract-map in
`r10/e/python-release/toolkit/public-decode-contract-map.md` maps published
specifications, actual exported entries, existing fixtures and uncovered wire
conditions. Use those existing fixtures and public JSON boundaries for four
scenarios. Existing adjacent positive and negative tests remain valid.

1. Reload a Diagnostic session or event JSON envelope. Reject incorrect JSON
   collection shapes, the invalid empty extended session shape and contradictory
   event sequence/actor/type. Preserve legacy versus extended shape semantics,
   immutable identities, canonical round trips and the caller's original input.
2. Decode a Diagnostic event containing nested observation, hypothesis or fix
   verification data. Reject invalid nested collection shapes, published limits,
   closed fields and request/result identity contradictions through the event
   entry. Reuse the canonical payloads and existing extended model fixtures.
   Do not repeat direct child-model negatives merely through another wrapper.
3. Reload an acceptance checkpoint or source-change intent. Reject incomplete
   stage prefixes, partial derived intents and published source-size/digest
   violations. Retain the existing valid revision helpers, exact stage-output
   binding and closed policy domain; never invent a physical execution.
4. Import raw replay or physical transcript bytes. Exercise the exported byte
   decoders with canonical fixture bytes, the documented final-LF option and
   caller-meaningful invalid UTF-8, duplicate keys, BOM, noncanonical JSON,
   scalar-root and resource-limit inputs. Validate a real existing v2 reference
   fixture and reject provenance/window contradictions without substituting an
   accepted physical identity.

Use exact error codes from the approved public contracts and existing error
families (`DiagnosticValidationError`, `AcceptanceRecoveryValidationError`,
`ReplayContractError`). Establish expected outcomes from those contracts before
choosing mutations. Deep-copy and compare caller inputs after rejection. A
decoder-only refusal proves no accepted model, not a durable publication or
hardware result. Where an existing workflow fixture is genuinely needed, assert
the unchanged authoritative files as well. Avoid redundant workflow execution
for a pure wire-decoding contract.

## Scope and non-goals

Only test files listed in the plan and one short return report may change. No
product bytes, schemas, error maps, dependencies, coverage exclusions, or gates
change. DiagnosticStore locking is an independently owned product correction;
this slice must not touch its implementation or tests. No new malformed-input
framework, generic mutation generator, hardware fixture, or new runner.

One readable parameter table per coherent public boundary is appropriate.
Include only distinct caller-visible branches absent from existing tests, not
unconstructable private states, Python-only containers, duplicate assertions or
artificial mocks of the decoder under test. Discovering a product-contract bug
stops the affected run and returns the concrete wire and expected behavior to
the primary; do not weaken the expected behavior or alter product code here.

## Evidence and acceptance

The release branch gate remains at least 90 percent for each Python package.
This bounded slice has no promised percentage gain and cannot by itself close
the currently measured gap. The written risk reason for these qualification
tests is incomplete coverage of persisted/public evidence input validation.

Require one scoped branch-instrumented run of the new nodes plus the existing
positive fixture nodes they rely on, retained command/head/exit/JUnit/raw data,
and independent complete-diff review. Preserve historical failures and accepted
physical A/B checks. No packaging, deployment, full suite, or hardware repetition
is needed for test-only changes.
