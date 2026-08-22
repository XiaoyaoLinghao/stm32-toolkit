# STM32 Toolkit VS04-B1 Physical Monitor Reference Plan

## Ledger and outcome

- Accepted base: `6d8a593990d176e5ef2b9e051059ab6e5b3fd76b`.
- Branch: `codex/STM32TK-0600-VS04B1-PHYSICAL-MONITOR-REF` from the documentation head.
- Specification/review owner: GPT-5.6-sol.
- Implementation/test owner: one GPT-5.6-luna agent with reasoning effort `max`.
- Python 3.12 only; no physical or remote authority.

Deliver one public, production-shaped behavior: publish an exact already-committed live Monitor
History window, bind it to an accepted physical TestRun, return `MonitorRunRef` v2, and fresh-load
the same immutable reference. Analysis, Diagnostics, FixVerification, live observation control,
and hardware are out of scope.

## Allowed implementation boundary

Monitor product code:

- `tools/stm32-monitor/src/stm32_monitor/replay.py` or one narrowly named sibling physical
  publication module;
- `tools/stm32-monitor/src/stm32_monitor/history.py` only if a read-only helper is strictly needed;
- `tools/stm32-monitor/src/stm32_monitor/cli.py`;
- package exports only where required.

Shared contract:

- `tools/stm32-toolkit/src/stm32_toolkit/monitor_replay_contract.py` only for the discriminated
  v1/v2 closed wire validator and constants.

Tests may change only the directly corresponding Monitor replay/history/CLI files and one new
physical publication test file. Do not edit Analysis, Diagnostics, Testing publication, Probe,
Monitor runtime/service/sampler, UI, schemas unrelated to run references, or release tooling.

## TDD execution

### 1. Freeze v1/v2 without changing v1 bytes

First add failing model/contract tests proving:

- every existing v1 fixture/reference round-trips to identical canonical bytes;
- v2 requires `source_record_sha256` and forbids `fixture_sha256`;
- v1 forbids v2 fields;
- physical v2 requires equal workspaces/sessions/runs, true physical flag, non-replay labels, and a
  hash-shaped probe ID;
- mixed, unknown, null-filled, extra-field, tuple-container, noncanonical, and contradictory values
  fail closed.

Implement the smallest discriminated contract. Do not migrate or rewrite stored v1 Evidence.

### 2. Publish one real History window

Create a production-shaped test with real `WorkspacePaths`, `HistoryStore`, `EvidenceStore`, and
`TestRunRepository`. Publish a physical failed TestRun through the accepted VS04-A publication
contract, append at least two live batches whose binding contains the transient raw selector, then
call the new public physical publisher.

The first GREEN must prove:

- no Probe/runtime/service method is called;
- the exact complete sequence/time window is reconstructed through public History queries;
- TestRun/Project/History identity and physical provenance match;
- the transcript and v2 reference publish with authoritative roots;
- fresh loader returns the same reference;
- new/public durable bytes contain the probe hash but not the raw selector.

The publisher must preflight both roots and complete payloads before its first root write. Repeated
identical publication returns the same reference. A conflict never replaces an existing root.
After preflight, publish the transcript artifact/envelope/root before the reference
artifact/envelope/root. If a provider failure interrupts this append-only sequence, return
`ENVIRONMENT_FAILURE`, retain only the exact validated prefix, and let the same complete intent
resume from that prefix on retry. Never roll back, delete, or replace retained Evidence.

### 3. Close negative behavior

Add parameterized tests for replay TestRun, wrong role/state, raw selector/hash, workspace/session,
project, build/ELF/snapshot/Git, target/debug target, flash session/lease, run/group/revision,
sequence/time window, incomplete slices, repeated cursors, storage corruption, Evidence conflict,
and provider failure. Validation, integrity, and pre-existing conflict cases assert the frozen error
class and zero new roots. Fault injection at each durable publication boundary asserts either zero
durable data or the exact valid publication prefix; retrying the same intent must complete both
roots, while a malformed or contradictory prefix must fail closed.

Do not manufacture physical Evidence from replay batches. Do not accept caller identity fields or
caller-supplied batch bytes.

### 4. Add the thin CLI

Add exact `physical publish` arguments from the amendment. The adapter loads Project v3 workspace
and Evidence roots once, calls the public workflow once, returns the reference, and sanitizes all
failures. Raw selector and absolute paths never appear in output or error text. No MCP tool is added.

### 5. Slice verification

Use short Windows basetemps and exact worktree source roots. Run:

- the new physical publication tests;
- Monitor replay model/contract/ingestion tests;
- Monitor History tests directly affected by query reconstruction;
- Monitor CLI adapter tests;
- Toolkit physical TestRun publication/repository smoke tests;
- changed-file `py_compile`;
- `git diff --check` from this documentation head;
- clean status and durable/public raw-selector scan.

Do not run Analysis/Diagnostics/Monitor UI, release matrices, hardware, coverage, packaging, or
Python 3.10. The Sol reviewer independently publishes and fresh-loads one physical v2 reference and
probes v1 byte identity, pre-commit negative no-root behavior, and interrupted-publication resume.

Expected commit: `feat(monitor): publish physical run references`.
