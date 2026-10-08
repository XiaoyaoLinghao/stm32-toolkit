# Public control authorization and backend-result qualification

This is a test-only execution addendum to the approved risk-layered qualification
plan. Product behavior, release targets, hardware authority and frozen statistics
remain unchanged. Accepted base: 7b3dba9db07b2c6a593ef89adf3f2585c0b3a2f8.
Primary conversation owns this contract and integration; the existing Probe
Luna/max owner implements tests; the independent reviewer accepts the full diff.
Source registry: r10/e/risk-v2/union35/current-source-identity-sampler.json,
SHA256 69D2A724BE181F715FF82E776FFA16F86F2410ADD16780B0C8F17AC9B01BB28A.

## Scenarios and first guards

1. A valid public ControlAuthorizationStore.prepare binds target identity and
   state. A public ProbeClient control request later observes a changed backend
   snapshot. ProbeService.service.py:995-999 must return
   PROBE_AUTHORIZATION_INVALID before performing the control action. The digest
   is consumed: repeating it must remain refused. A fresh matching authorization
   succeeds, followed by public client/service shutdown and worker exit.
2. A valid authorization reaches target.step with a valid pre-step PC. The
   external test backend then reports one of three invalid post-action results:
   missing/invalid PC mapping (1178->1179), a non-integer or out-of-range PC
   (1181->1182), or a running rather than halted state (1184->1185).
   Public target_control must report PROBE_BACKEND_ERROR without returning a
   successful step report. A valid fresh request or fresh worker must recover;
   public shutdown must release its resources and terminate the actual worker.

The four named source arcs are missing in U34 and remain absent in U35. Existing
test_probe_protocol_v2 validates a malformed pre-step mapping; it does not reach
the post-step guards. Existing service fixtures already provide legal service,
authorization and protocol construction. These are security/control-boundary
oracles, which justify this small branch yield; no additional transport variants
or unrelated response checks belong in this slice.

The public route is ProbeClient -> ProbeService -> declared backend adapter.
The existing ProbeBackendWorker test backend factory is allowed as an external
software boundary. worker.py:602-613 forwards the mapping/state values, and its
JSON transport preserves empty dictionaries, booleans and integer values, so
those cases are not dominated by a worker response validator. Only the test-owned
backend may script its own results. Do not replace production predicates,
authorization consumption, private service state, worker internals or protocol
decoders. Prove the exact first guards before adding the test cases; if an
earlier real guard blocks a proposed case, stop that case rather than bypass it.

## Ownership and bounded execution

Implementation tree: r10/w11p, branch codex/STM32TK-1.0-control-result-boundary.
Luna owns only tools/stm32-toolkit/tests/test_risk_control_result_boundary.py.
The primary owns this addendum; no shared fixture or production file may change.
Reuse existing fixture builders and guarded launch/coverage entry points.
Do not create a generic diagnostics or corruption framework.

After committing and static checks, verify all148 product source hashes against
the new registry. Slot1 permits one selected run with a180-second wall bound and
fresh memory>=15%, at r10/t/w11p/run1 and e/risk-v2/wave11/probe/run1. At most one
other suite may run concurrently. The implementer must preserve exact argv,
candidate identity, JUnit, exit status, original coverage shards, and source
identity. Test behavior and measurement completeness are separate decisions.
Record actual worker PIDs and prove each successful child has a persisted native
coverage shard that survives combine --keep. A nonzero child/parent exit, missing
shard, timeout, or unexpected assertion stops this run; no automatic retry.

No hardware, deployment, package rebuild, remote action, cleanup retry or formal
coverage aggregation is authorized here. Primary alone updates the shared
ledger and performs the later serial aggregation. This software protocol result
must never be described as physical hardware acceptance.
