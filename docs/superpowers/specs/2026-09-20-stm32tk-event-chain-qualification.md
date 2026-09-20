# Event and predecessor-chain qualification

Accepted base: `dcd92a6377e240306de02603027bc6c4f1deb53e`.
This test-only slice is within the approved core public-contract qualification.
Runtime stays `465249dba5560f7c08b1172794fec8fedd9b8d96`; native union19 remains
the measured baseline. Primary owns design, integration and independent review;
Luna/max owns implementation. No remote action or hardware is authorized here.

## Three caller scenarios

1. Decode a canonical Diagnostic event with one invalid sequence, payload shape,
   schema, assessment polarity or request/result assessment binding. Use the
   public DiagnosticEvent.from_value and existing canonical event factories.
   Preserve the old outer digest intentionally: the nested contract rejects
   these inputs before digest comparison. Only invalid polarity returns
   DIAGNOSTIC_PLAN_INVALID; the others return DIAGNOSTIC_INVALID_EVENT. Changing
   assessment rationale requires the public assessment ID calculation, with the
   request rationale unchanged. The caller's input object remains unchanged.
2. Decode source-change, verification-plan, verification-start and marker events
   whose result ID/digest differs from the valid request. Change only the result
   binding to another well-formed value. Existing public lifecycle fixtures
   supply the valid prefix. Reject with DIAGNOSTIC_INVALID_EVENT without input
   mutation or fabricated typed instances.
3. Authenticate a persisted v2 revision-six predecessor before continuation.
   Reuse prepare_pair once; clone its data tree per case, preserving project and
   workspace identity. Enter through ContinuationRequest.from_value followed by
   prepare_continuation. An unchanged clone must authenticate successfully.
   Ten corruptions must raise the exact ContinuationValidationError below,
   leaving all fixture bytes unchanged by the read and publishing no proof.

| Mutation | Expected message after the valid prefix |
| --- | --- |
| rev6 envelope attempt_sha256 differs from typed attempt/root | predecessor attempt evidence is incompatible |
| rev1 envelope parent differs | predecessor attempt chain is corrupt |
| rev1 previousCheckpointId differs | predecessor attempt chain is corrupt |
| rev1 envelope timestamp differs from update | predecessor attempt envelope is corrupt |
| rev1 logicalProjectId differs | predecessor immutable fields changed |
| rev2 update occurs after prior deadline | predecessor transition was outside its deadline |
| rev2 changes a previously fixed stage output | predecessor outputs changed |
| rev5 changes prior source intent | predecessor source authority changed |
| rev1 envelope session differs | predecessor session changed |
| rev6 deadline differs from stage policy | predecessor policy deadline differs |

## Construction and non-goals

Use real EvidenceStore, public EvidenceEnvelope/RootRecord and public canonical
JSON/attempt constructors. Mutation occurs only in cloned fixture storage;
resolve its root path from the public root key/canonical bytes, without calling
private production path/reader/validator helpers. Preserve the original graph.
Republish a changed attempt's checkpoint and matching envelope/root metadata
except the deliberately mismatched field. Preserve workspace/project envelope
identity and root metadata for the logical-project case. Preserve prior links;
do not repair downstream revisions. For rev2 time drift recompute its deadline
using the actual public policy, preserving earlier immutable/previous fields.
For rev5 recompute the intent digest/checkpoint with legal null after-output
fields, leaving rev4 intact. Keep the bind request at its accepted rev6 identity:
chain validation precedes later proof binding, including the rev6 deadline case.

The store.py:596->597 proposal is excluded: valid unique plan evidence IDs make
the match a singleton; changing an analysis ID reaches another guard. Do not
substitute a reader, forge an envelope or test private decisions to force it.
No runtime, schema, shared fixture, dependency, configuration or denominator
change; no generic diagnostics framework, platform workaround or physical claim.
Nineteen candidate branches are static scope, not a promised numerator gain.

Acceptance requires exact public results, unmodified input/storage, a valid
positive predecessor prefix, complete PASS evidence and full-diff review.
Toolkit 90% and preferred core 95% remain unchanged; 1.0 stays unaccepted.
