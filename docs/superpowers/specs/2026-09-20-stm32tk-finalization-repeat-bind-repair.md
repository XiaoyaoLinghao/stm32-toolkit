# Finalization repeat-bind repair

Accepted integration base: `6ea381515457bf4705682b0d812e8a6026e9354d`.
Frozen product base: `465249dba5560f7c08b1172794fec8fedd9b8d96`.
Unintegrated qualification candidate: `f63bf9fba3f256f7463213af7411966f834f5071`.
Owner: primary design/review/integration; same Luna/max recovery implementer.
This repairs the existing approved VS10-B offline-finalization contract, not
a new request form or hardware operation.

## Observed defect and exact cause

The new public finalization journey failed at a fresh UUID's second bind to
the same valid proof. It returned data=null; run1 stopped with 1 PASS/1 FAIL,
71.63 seconds. Continuation PASS remains valid. Full failed-batch raw is held
and excluded from accepted aggregation. No hardware was accessed.

At recovery_workflows.py:3966-3968, preparing bind with require_proof_root=False
returns an AuthenticatedFinalization whose root/envelope are None. When the
proof already exists, :4265 calls _existing_finalization_association; :4044
reads continuation_evidence_id. finalization.py:517 dereferences the missing
envelope and raises AttributeError; _result:208 maps it to
ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED. This is a product lifecycle bug,
not evidence corruption. The exact wire code follows the source exception
mapping; the original failed assertion retained data=null, not the full wire.

## Required behavior and bounded correction

1. A fresh attempt UUID with an unchanged valid bind request must reuse the
   existing immutable proof after complete validation, then publish only its
   own revision0. Explicit reuse and exact existing-attempt retries retain
   their existing behavior.
2. A missing, corrupt or mismatching existing proof must fail closed before
   a new attempt root. Prior proof, Diagnostic history and attempt bytes stay
   unchanged. There is no fallback to a newly invented proof or another route.

Resolve a not-yet-bound association's persisted proof through its deterministic
proof root key, then validate the actual manifest/proof using the existing
reader. Do not dereference the absent envelope. An already authenticated
association remains pinned to its original evidence ID; do not silently
rebind it to an altered root. Reuse the existing proof equality, identity and
parent checks. Do not catch AttributeError and treat it as success.

Keep D->E ordering and the existing complete graph validation under D. The
existing-proof fast path under E must not load or repair Diagnostic state.
No new locks, public types, schemas, errors, helper framework or reader seam.
Only recovery_workflows.py product code may change; finalization.py is read-only.
Tests may change only test_acceptance_finalization.py. The completed
test_acceptance_continuation.py candidate is retained without another edit.

Strengthen the new journey's success assertion so an unexpected public result
prints its complete wire object before indexing data. Keep repeated bind as
the regression; do not replace it with explicit reuse. Add a bounded cloned
existing-proof rejection check only if existing public tests do not cover the
new proof-root lookup. Use real records/public readers, no invented graph or
fake successful authority. Exact new-resource and prior-byte oracles stay.

## Acceptance and evidence impact

Primary reviews complete accepted-base-to-final-candidate content and the
focused repair independently. Runtime uses the new finalization journey plus
the existing persisted round trip, expired/fresh explicit reuse, authority
rejection, same UUID competing proof and begin commit timestamp tests.
This is a product-risk-triggered regression batch, not a full release rerun.
No unchanged continuation/physical test is repeated merely to recover coverage.

The product source identity changes for recovery_workflows.py. Historical
union20 remains explicitly tied to 465; its old coverage for the changed file
cannot be presented as current without reconciliation. Preserve raw inputs,
exclude failed batches, and apply the existing changed-file invalidation rule
before publishing a new native union. Unchanged files, actual VS10-A/B hardware
results and attempt7 retain their original scope. 1.0 remains NOT_ACCEPTED.
