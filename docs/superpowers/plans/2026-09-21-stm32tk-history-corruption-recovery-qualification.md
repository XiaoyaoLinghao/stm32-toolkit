# Public history corruption refusal and recovery

This test-only addendum follows the approved risk-layered qualification and
defect-convergence release flow. Accepted base is
7b3dba9db07b2c6a593ef89adf3f2585c0b3a2f8. Primary owns design and acceptance;
the existing Monitor Luna/max owner owns implementation and first verification;
the existing independent reviewer reviews the complete diff. Product behavior,
frozen statistics, physical evidence and remote authority remain unchanged.

## Two public scenarios

1. Invalid append input is refused before storage creation; the same public
   store then accepts a valid batch, queries it and closes. Public
   HistoryStore.append_batches((object(),)) reaches history.py:1068->1069.
2. Valid public persisted history is externally corrupted, public query/export
   refuses it without publishing or deleting history, and exact restoration
   permits reuse and public close. Bound this family to three cases:
   - register-shaped watch with kind=variable: history.py:755->758;
   - an authenticated public cursor references a subsequently shortened batch,
     with coherent empty payload/index/digest: history.py:1484->1485;
   - a non-bytes persisted payload reaches public authorized export's uncached
     history path: history.py:1406->1407. No completed export is published and
     pending export resources settle before restoring and successfully exporting.

Use existing public fixture builders, external SQLite connections and public
HistoryStore/HistoryExporter methods. Restore exact saved persisted input; the
refusal no-write baseline is the already corrupted state. Never modify private
cache/state, replace product predicates or bypass production integrity checks.
Verify each earlier SQL, index, digest, model and cursor guard. An earlier guard
that rejects the proposed data disqualifies that case; do not force it through.

The corrected existing preflight is
e/risk-v2/wave11/monitor-storage-preflight.md, SHA256
AC7B2E685994B6B99CC551B037C681FD062DABAC6773E13C7D48CC3CBB2937EB.
It compares U35 current source69D2. These four missing arcs are candidates, not
measured gains. Its original v1 migration three arcs and zero-batch-id arc are
withdrawn due to earlier guards or wrong branch direction. Do not implement them.
This small family is justified by persisted-evidence integrity and successful
recovery, not by a speculative broad coverage gain. No additional variants,
storage races, retention clocks, replay work or production fixes belong here.

## Ownership, execution and exit

Isolated tree r10/w11m, branch
codex/STM32TK-1.0-history-corruption-recovery. Luna owns only
tools/stm32-monitor/tests/test_risk_history_corruption_recovery.py. Primary owns
this plan; shared fixtures, other tests, product files and ledgers are excluded.
The owner is not alone in this repository; preserve other owners' changes.

Continuously prepare, implement, commit and perform Ruff/AST/diff/source148 checks
against registry69D2A724BE181F715FF82E776FFA16F86F2410ADD16780B0C8F17AC9B01BB28A.
Reuse the existing guarded launcher and native collector, not a new framework.
One selected180-second run is admitted at r10/t/w11m/run1 and
e/risk-v2/wave11/monitor/run1, fresh memory>=15%. It uses slot1 only after Probe's
already admitted run2 has terminated and released that slot; primary coordinates
this resource handoff. This is a concurrency barrier, not a new approval gate.
The Recovery suite may use slot2; never exceed two actual suites.

Preserve exact source/argv/JUnit/process intervals/raw shards. Account for actual
descendant processes using native subprocess and multiprocessing support where
applicable; retain native raw files through combine --keep and verify unchanged
hashes and source-bearing data. Behavior and measurement receive separate
verdicts; incomplete measurement cannot enter formal coverage. First unexpected
failure stops with classification and evidence, without an automatic rerun.
Independent full-diff review and primary acceptance precede local integration.
Formal aggregation is serial. No hardware, deployment, final build, remote
mutation, shared-ledger write or cleanup retry is admitted by this slice.
