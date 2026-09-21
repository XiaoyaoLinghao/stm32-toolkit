# Sampler failed-start transaction

Specification and acceptance owner: primary conversation. Implementation/tests:
existing Monitor Luna/max owner; independent reviewer: existing review owner.
Accepted branch base:9cd33a04b2d6cb79a3a4e8ab05f648abadd0cedb. Qualified product
source:8a11caef14df16c5e56c0be2363d4ef5530110eb. Integration's separately accepted
test-only Wave10 head is07dbf1f5b1825b1b7c1f67e318fb3bd57c0459ed.

## Proven defect

The once-only offline reproduction in r10/e/risk-v2/wave10/sampler/run1 tested
6e736d79fcfb9526f1c9486098d930121ce3bbf8. A public asyncio task factory refused
the first sampler-owned task. The exact injected exception propagated, but public
state before cleanup remained RUNNING. Public stop/close settled the sampler;
launcher7544 and interpreter34764 exited. This is a PRODUCT failure, not hardware
evidence. Failed raw data is excluded. sampler.py243 publishes RUNNING before
task creation244-245 without rollback.

## Required scenarios and lifecycle

1. First owned task creation fails after valid admission/read-plan setup: propagate
   the original exception, restore IDLE, leave no live owned task or usable stale
   read plan, and close the rejected coroutine.
2. Second owned task creation fails: settle the already-created history task
   before failure escapes, with the same state/plan/coroutine/exception guarantees.
3. After either refusal, public start/stop/close remain usable. Existing nominal
   sampling, epoch, pause/resume and shutdown behavior remains applicable.

The action lock remains the lifecycle authority. Rollback must not re-enter that
lock through public stop. Settle only this start's owned resources, invalidate its
epoch/read plan, clear run-owned references using the existing lifecycle mechanism,
then restore IDLE. Do not turn failure into success or automatically restart.
Tests use the public host task factory, not private state/predicate modifications.

Only tools/stm32-monitor/src/stm32_monitor/sampler.py and the candidate
tools/stm32-monitor/tests/test_risk_sampler_start_transaction.py may change.
No general scheduler abstraction, new error vocabulary, frequency change,
unrelated cleanup rewrite, hardware, deployment or remote action. Direct external
child cancellation is a separate unresolved scenario, not implicitly fixed here.

## Verification and source qualification

One bounded correction run covers both public failure/reuse cases and affected
test_sampler.py plus test_risk_sampler_group_epoch.py checks. Retain actual
candidate, JUnit, exit, original shards and native combined coverage; first
unexpected failure stops. An IDLE stop does not promise an additional read-plan
invalidation. Do not restore the removed extra-invalidation assertion.

Changed sampler.py invalidates its old-source coverage. Primary replaces only its
source-qualified evidence, retains unaffected files and frozen file selection,
and uses the actual new denominator. U34 remains the accepted pre-correction
baseline. Independent full-diff review and primary evidence reconciliation precede
integration. No self-acceptance; 1.0 release gates remain unchanged.
