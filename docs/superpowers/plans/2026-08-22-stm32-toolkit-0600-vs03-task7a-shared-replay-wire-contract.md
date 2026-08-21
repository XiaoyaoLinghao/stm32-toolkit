# VS-03 Task 7A-R1 Shared Replay Wire Contract Plan

> **Implementation owner:** the existing `gpt-5.6-luna` / `max` Task 7A implementer. GPT-5.6-sol
> owns the contract and independently reviews the complete diff.

**Goal:** Replace the duplicated Monitor/Toolkit replay parsers with one dependency-neutral wire
validator so producer and consumer accept exactly the same canonical documents and references.

**Dispatch base:** the local docs amendment commit created from
`e36bcf2e41602394547cf0a63c608808646f9dfd`; record its full SHA before product edits.

**Boundaries:** no diagnostic durable-mode/idempotency work, adapters, hardware, Python 3.10,
packaging, release matrix, or remote operation. Existing canonical fixture and public Monitor model
bytes must remain unchanged.

## Task: Establish and consume the single wire authority

**Product files:**

- Create `tools/stm32-toolkit/src/stm32_toolkit/monitor_replay_contract.py`
- Modify `tools/stm32-monitor/src/stm32_monitor/replay.py`
- Modify `tools/stm32-toolkit/src/stm32_toolkit/diagnostic_workflows.py`

**Tests:**

- Create `tools/stm32-toolkit/tests/test_monitor_replay_contract.py`
- Modify `tools/stm32-monitor/tests/test_replay.py`
- Modify `tools/stm32-toolkit/tests/test_fix_verification_workflows.py`

1. Write a table-driven RED conformance corpus containing the two real fixtures/references and
   producer-invalid mutations for every wire class: top/binding/batch/sample/watch extra or missing
   fields, selector leading/trailing whitespace, NFC/control text, bool-as-int, integer rate,
   timestamps, UUID/hash/range, typed/definition JSON bounds, batch ordering/vocabulary, fixture
   digest, projected digest list, and unsigned ref digest. Assert producer and shared validator
   agree for every case and do not mutate input.
2. Implement a stdlib-only bounded canonical validator for replay documents and run references.
   It returns an exact deep JSON copy only when round-trip bytes and all closed invariants hold.
   It exposes fixed internal validation errors without provider text and imports no Monitor,
   Evidence store, diagnostic workflow, or platform service.
3. Make Monitor replay `from_value`/ingestion call the shared authority and retain only Monitor
   object materialization and History/Evidence behavior locally. Exact accepted fixture and
   MonitorRunRef bytes/digests must not change.
4. Replace Toolkit's duplicated batch/sample/watch/ref shape validation with the shared functions;
   retain local Evidence/root/identity/import/transcript projection checks. Add the independent
   self-consistently re-signed whitespace-selector public diagnostic regression and require
   `EVIDENCE_INTEGRITY_FAILURE` plus byte-identical Evidence/DiagnosticStore snapshots.
5. Run CPython 3.12 with short basetemps: the new contract tests, Monitor replay/analysis tests,
   Toolkit fix-verification tests, and `git diff --check`. Commit once and report full SHA and
   working-tree state. Sol then reviews dispatch-base-to-head and reruns only this focused set.

## Conformance evidence reset after two non-convergent test rounds

The product accept set passed an independent fully re-signed corpus, but two tracked-test revisions
still allowed a second invariant to reject selected cases. Stop per-case patching and apply this
single isolation design to the corpus:

- every non-digest candidate is fully re-signed after mutation;
- document/batch binding and selector vocabulary are synchronized whenever they are not the target;
- boolean-as-integer uses an unbound count such as `subscriberDrops`, never sequence;
- document UUID and positive group revision mutate every batch consistently;
- reference canonical UUID uses `group_id`, which is not coupled to operation/run identity;
- a table records each target rule and its coherence transformation;
- an explicit sensitivity oracle (or equivalent assertion) proves that removing only the named
  target predicate leaves all remaining structural/relational/digest constraints satisfied.

This reset authorizes one test-only replacement of the affected corpus. It does not authorize a
third product parser change or any additional validation layer.
