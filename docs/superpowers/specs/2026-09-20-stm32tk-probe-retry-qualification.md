# Probe ownership retry qualification

This is a bounded test-only continuation of the approved core public-contract
qualification. Accepted base: `3ba1439c20b09257dfcbe55eee517e1349655f01`.
Runtime stays `465249dba5560f7c08b1172794fec8fedd9b8d96`. Primary owns design,
review and acceptance; Luna/max owns implementation. No remote authority.

## Three caller scenarios

1. A valid debug handoff reaches end, finalization succeeds, but the public
   acknowledge provider returns false once. End returns
   `HANDOFF_REACQUIRE_FAILED`, preserves `observing-pending-release` and a
   `handoff-finalized` reservation, and leaves no endpoint. Another begin is
   refused with `HANDOFF_REACQUIRE_REQUIRED` without lifecycle dispatch.
   Public end with the same ticket, after the provider recovers, completes
   acknowledgement, restores the saved selection, clears the ticket and
   releases the reservation. Begin is not the recovery operation.
2. A valid end attaches, then its public readback provider fails and the
   supervisor stop reports failure after cleanup. The public result preserves
   cleanup-error precedence (`HANDOFF_REACQUIRE_FAILED`), an absent endpoint,
   `reacquiring` state and the external reservation. It must not consume,
   finalize, acknowledge or release prematurely. Clear the provider failures;
   retry the same ticket through public end and prove normal settlement.
3. A caller supplies a naive datetime to the public lease clock. Acquire and
   heartbeat raise `ValueError("UTC clock must return a timezone-aware datetime")`
   before writing an owner record. Acquire releases its guard lock; a later
   valid public acquire succeeds. Heartbeat preserves the active record bytes
   and ownership; a later aware heartbeat and release succeed. No writer .tmp
   remains. A persistent .guard file or registry created by acquire is allowed.

The scenarios protect resource ownership and recovery after supported software
provider failures; they are not hardware evidence. They address four candidate
native pairs in handoff.py and lease.py, not the remaining 452-branch gate.
The measured union alone determines any coverage gain. The claimed-false edge
at handoff.py:1549->1559 is not reached by the readback/cleanup failure case;
its actual cleanup error is mapped at lines 1554-1558. Do not manufacture a
different internal state to reach the excluded edge.

## Frozen boundaries

Reuse handoff_env, FakeSupervisor, FakeClient, and the real ProbeLeaseManager
fixture. A test-local one-shot wrapper around the public acknowledge method is
allowed; changing private decisions or persisted handoff state to force a result
is not. Public wire errors and actual state/record bytes remain the oracles.
One owner changes only test_debug_handoff.py and test_probe_lease.py. Existing
tests remain intact. No shared fixtures, production code, schema, dependencies,
coverage configuration or denominator changes.

The proposed metadata-abort failure scenario is excluded. Independent review
found no subsequent public stop path that can settle its retained ownership.
Do not fabricate stop proof, clear private flags, or introduce a worker just to
exercise that branch. The static finding is retained for a separate design
decision, not labeled a reproduced product defect or a passed test.

Acceptance requires exact errors and ownership transitions, no live test-owned
resources after completion, complete PASS evidence and independent full-diff
review. Source, prior A/B/attempt7 and deployment evidence remain unchanged.
Toolkit overall 90% remains mandatory; core 95% is preferred. 1.0 is not accepted.
