# Recovery public producer qualification addendum

This test-only addendum executes the approved risk-layered qualification plan.
It changes no product contract, release requirement or frozen scope. Accepted
base is 7b3dba9db07b2c6a593ef89adf3f2585c0b3a2f8. The primary owns design and
integration; the existing recovery Luna/max owner implements tests; an independent
reviewer accepts the complete diff. No remote or hardware authority is added.

## Two bounded public journeys

1. Software v1 recovery: valid public begin, checkpoints, authorization and
   identical-request retries use real persisted build and project facts. A valid
   retry returns the same attempt wire; a stale or altered request is refused
   with the declared public code/message and does not publish a new record.
2. From that same legal prefix, canonical persisted evidence corruption is
   refused by public show/resume/checkpoint with an unchanged evidence tree.
   Exact restoration recovers the original wire. Only public model/envelope/root
   serializers and test-owned persisted fixture bytes may be used.

Reuse test_flash._publish_current_debug_build and public build_project_context
for real software fixture facts, plus public replay and Diagnostic producers
where the frozen scenario requires them. Do not patch _build_project_context,
_load_fresh_firmware_facts, snapshot providers, production predicates or private
state. Do not introduce or relabel physical/continuation/finalization evidence.

The reassessment's62 software residual arcs are an inventory, not a prediction
of obtainable new coverage. Before implementation, the owner must map the exact
selected inputs and first guards against current U35 missing arcs. Prioritize
the public checkpoint/authorization retry and transition families at
recovery_workflows.py:798-828,910-1039,1249-1281,1411-1472. A real serialized
fixture must pass all earlier identity/model/source checks. Exclude model-
dominated or already-covered paths, even if a private patch could reach them.
Proceed only if the two complete journeys jointly establish at least six new
reachable arcs; otherwise return the concrete low-yield/guard result and stop
without adding a large success-only test. This is an execution admission bound,
not a coverage denominator or release threshold change.

## Ownership and execution

Tree r10/w11r, branch codex/STM32TK-1.0-recovery-public-producers. Luna owns only
tools/stm32-toolkit/tests/test_risk_recovery_public_producers.py. Primary owns
this plan. Other tests, fixtures, product files and the shared ledger are not
owned. Retain existing results; no generic corruption/diagnostic framework.
The existing callable fixture builders are sufficient; do not add a standalone
runner solely to bypass their public validation. Record the first-guard map
under e/risk-v2/wave11/recovery before writing the test scenarios.

If the reachability bound is met, commit and run Ruff/AST/diff checks, verify all
148 sources against e/risk-v2/union35/current-source-identity-sampler.json
(SHA69D2A724BE181F715FF82E776FFA16F86F2410ADD16780B0C8F17AC9B01BB28A),
then slot2 permits one selected300-second run, memory>=15%, under r10/t/w11r/run1
and e/risk-v2/wave11/recovery/run1. Slot1 is the independent Probe suite; at most
two suites may execute. Reuse the guarded launcher and native coverage entry,
capture actual child processes/shards and keep original raw data through combine.
Behavior and measurement completeness are separate verdicts. First unexpected
failure stops; no automatic retry. No formal aggregation, hardware, deployment,
remote mutation or retry of rejected cleanup is authorized.
