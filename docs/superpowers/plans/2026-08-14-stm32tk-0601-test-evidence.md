# STM32TK-0601 Test and Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver immutable evidence, Project Schema v3, deterministic Host/Target tests over four transports, and the executable 0.6 acceptance framework.

**Architecture:** Add a content-addressed evidence package and a closed test protocol inside Toolkit. Host tests wrap CMake/CTest with argv-only execution; Target tests share one framed event decoder across mailbox, RTT, UART, and semihosting adapters. Freeze Probe v2 and the release gate catalog before later modules consume them.

**Tech Stack:** Python 3.10/3.12, dataclasses, jsonschema, SQLite, CMake/CTest JSON/JUnit, pyOCD, pyserial, pytest/pytest-cov, PowerShell 5.1, JSON Schema.

## Global Constraints

- Accepted base is exactly `bb6bc5e9ee937e4ce53996b31f25bf1109ffe13f`.
- Follow `docs/superpowers/specs/2026-08-14-stm32tk-0601-test-evidence-design.md`.
- Product Python remains `>=3.10`; run each affected correctness shard on 3.10 and 3.12.
- Each changed product Python file must reach at least 90% branch coverage in its owning shard.
- Preserve every 0.5 functional, safety, coverage, and performance threshold.
- Use `apply_patch` for source edits; preserve unrelated changes; use external temp/evidence roots.
- Never use an ambient shell for Host tests or accept arbitrary command strings.
- No remote Git operation is authorized by this plan. Each listed commit is local until the user
  separately authorizes push/PR changes.
- After two consecutive candidate failures caused by an acceptance-contract gap, stop and audit
  the contract instead of adding another late gate.

---

## Task 1: Freeze the 0.6 gate catalog and controller contract

**Files:**

- Create: `tools/release/gates_0600.json`
- Create: `tools/release/run_0600_quick.ps1`
- Create: `tools/release/run_0600_candidate.ps1`
- Create: `tools/release/run_0600_final.ps1`
- Create: `tools/release/verify_0600_release.py`
- Create: `tools/stm32-toolkit/tests/release/test_gate_catalog_0600.py`
- Create: `tools/stm32-toolkit/tests/release/test_gate_controller_0600.py`
- Create: `tools/stm32-toolkit/tests/release/test_release_verifier_0600.py`

- [ ] Write failing catalog tests that require unique stable gate IDs, exact argv arrays, owner,
  platform, timeout, evidence paths, coverage context, prerequisites, and quick/candidate/final
  membership. Include fixtures for duplicate, missing, extra, cyclic, and unknown-prerequisite
  gates.

```python
def test_final_gate_ids_equal_frozen_inventory() -> None:
    catalog = load_catalog(CATALOG)
    assert catalog.final_ids == EXPECTED_FINAL_IDS
    assert all(g.command_argv and isinstance(g.command_argv, tuple) for g in catalog.gates)
```

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/release/test_gate_catalog_0600.py -q -p no:cacheprovider
```

Expected: collection/import failure because the catalog/verifier does not exist.

- [ ] Implement a strict catalog loader/verifier and create the full frozen inventory covering
  Git/source/inventory, dual Python, Toolkit/Monitor, Node, browser, transports, diagnostics,
  analytics, offline packages, launchers, Skills, documentation, hardware, and evidence.

- [ ] Add controller contract tests with fake executable fixtures. Assert quick/candidate collect
  all independent failures, dependencies become BLOCKED, final is fail-fast, each gate emits a
  bounded log/result with required metadata/hash, and controller subprocesses run without
  product coverage environment variables.

- [ ] Add support/evidence verifier mutation tests: exact support-root manifest path/size/SHA-256,
  no missing/extra/case-fold duplicate/link/reparse/special file, immutable Node/npm/Python/
  browser/wheelhouse caches, unique empty evidence root, exact node inventory executed once, and
  failure when any retained log/result/screenshot/coverage/wheel is missing or hash-mismatched.

- [ ] Run GREEN and controller-only coverage-off regression:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/release -q -p no:cacheprovider
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/release/run_0600_quick.ps1 -ContractSelfTest
```

Expected: all tests pass; self-test deliberately exercises PASS/FAIL/BLOCKED without touching
product code, network, or remote Git.

- [ ] Commit:

```powershell
git add tools/release tools/stm32-toolkit/tests/release
git commit -m "test(STM32TK-0601): freeze 0.6 gate contract"
```

## Task 2: Implement canonical evidence models and schemas

**Files:**

- Create: `schemas/evidence-envelope.schema.json`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/schemas/evidence-envelope.schema.json`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/evidence/__init__.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/evidence/model.py`
- Create: `tools/stm32-toolkit/tests/test_evidence_model.py`
- Create: `tools/stm32-toolkit/tests/test_evidence_schema.py`

- [ ] Write failing tests for `EvidenceIdentity`, `ArtifactRef`, `EvidenceEnvelope`, canonical
  serialization, calculated `evidence_id`, fresh `to_dict()`, UTC/NFC/path/hash validation,
  booleans-as-integers, duplicate/unknown fields, depth/node/string/count/size limits, NaN, and
  schema mirror equality.

```python
def test_envelope_id_is_canonical_content_digest(valid_envelope_dict):
    first = EvidenceEnvelope.from_dict(valid_envelope_dict)
    reordered = EvidenceEnvelope.from_dict(dict(reversed(valid_envelope_dict.items())))
    assert first.evidence_id == reordered.evidence_id
    assert first.to_dict() is not first.to_dict()
```

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_evidence_model.py tools/stm32-toolkit/tests/test_evidence_schema.py -q -p no:cacheprovider
```

Expected: imports fail for `stm32_toolkit.evidence`.

- [ ] Implement frozen dataclasses, exact parsers, canonical JSON encoder, and
  `calculate_evidence_id()`; write byte-identical root/packaged schemas with closed objects and
  the spec limits.

- [ ] Run GREEN under both interpreters and branch coverage:

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests/test_evidence_model.py tools/stm32-toolkit/tests/test_evidence_schema.py -q -p no:cacheprovider
py -3.12 -m pytest tools/stm32-toolkit/tests/test_evidence_model.py tools/stm32-toolkit/tests/test_evidence_schema.py --cov=stm32_toolkit.evidence.model --cov-branch --cov-report=term-missing --cov-fail-under=90 -q -p no:cacheprovider
```

Expected: both pass and `model.py` branch coverage is at least 90%.

- [ ] Commit:

```powershell
git add schemas/evidence-envelope.schema.json tools/stm32-toolkit/src/stm32_toolkit/evidence tools/stm32-toolkit/src/stm32_toolkit/schemas/evidence-envelope.schema.json tools/stm32-toolkit/tests/test_evidence_model.py tools/stm32-toolkit/tests/test_evidence_schema.py
git commit -m "feat(STM32TK-0601): add canonical evidence envelopes"
```

## Task 3: Build the content-addressed store and catalog

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/evidence/store.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/evidence/catalog.py`
- Create: `tools/stm32-toolkit/tests/test_evidence_store.py`
- Create: `tools/stm32-toolkit/tests/test_evidence_catalog.py`

- [ ] Write failing store tests for safe ingestion, existing-object verification, atomic
  publication, flush/fsync fault points, path escape, symlink/junction/reparse/hard-link/special
  file rejection, case-fold collision, corrupt object/manifest, concurrent same-object writers,
  and no partial authoritative state after injected crashes.

- [ ] Write failing catalog tests for exact typed filters, deterministic ordering/limits,
  verified reads, complete rebuild from manifests, corrupt-entry failure, atomic replacement,
  and proof that forged catalog rows cannot create evidence.

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_evidence_store.py tools/stm32-toolkit/tests/test_evidence_catalog.py -q -p no:cacheprovider
```

Expected: missing store/catalog imports.

- [ ] Implement `EvidenceStore.ingest_file`, `put_envelope`, `get_envelope`, `verify_envelope`,
  `EvidenceCatalog.query`, and `rebuild_catalog` using only validated POSIX-relative paths,
  same-directory temp files, and public model types.

```python
class EvidenceStore:
    def ingest_file(self, source: Path, *, kind: str, media_type: str) -> ArtifactRef: ...
    def put_envelope(self, envelope: EvidenceEnvelope) -> Path: ...
    def get_envelope(self, evidence_id: str) -> EvidenceEnvelope: ...
```

- [ ] Run GREEN with concurrency/fault tests on 3.10 and coverage on 3.12:

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests/test_evidence_store.py tools/stm32-toolkit/tests/test_evidence_catalog.py -q -p no:cacheprovider
py -3.12 -m pytest tools/stm32-toolkit/tests/test_evidence_store.py tools/stm32-toolkit/tests/test_evidence_catalog.py --cov=stm32_toolkit.evidence.store --cov=stm32_toolkit.evidence.catalog --cov-branch --cov-report=term-missing --cov-fail-under=90 -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add tools/stm32-toolkit/src/stm32_toolkit/evidence tools/stm32-toolkit/tests/test_evidence_store.py tools/stm32-toolkit/tests/test_evidence_catalog.py
git commit -m "feat(STM32TK-0601): persist verified evidence objects"
```

## Task 4: Add reachability-based evidence garbage collection

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/evidence/gc.py`
- Create: `tools/stm32-toolkit/tests/test_evidence_gc.py`

- [ ] Write failing tests for mark roots from tests/diagnostics/bundles/annotations, shared
  objects, dry-run canonical plan/digest, store change after plan, corrupt/unknown/linked entries,
  confirmation and digest mismatch, partial-delete failure, and concurrent new references.

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_evidence_gc.py -q -p no:cacheprovider
```

- [ ] Implement `plan_gc(store) -> GcPlan` and `apply_gc(plan, authorized,
  expected_plan_digest) -> GcResult`; retain anything not both known, verified, and unreachable.

- [ ] Run GREEN on both Python versions and confirm branch coverage:

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests/test_evidence_gc.py -q -p no:cacheprovider
py -3.12 -m pytest tools/stm32-toolkit/tests/test_evidence_gc.py --cov=stm32_toolkit.evidence.gc --cov-branch --cov-report=term-missing --cov-fail-under=90 -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add tools/stm32-toolkit/src/stm32_toolkit/evidence/gc.py tools/stm32-toolkit/tests/test_evidence_gc.py
git commit -m "feat(STM32TK-0601): add safe evidence collection plans"
```

## Task 5: Upgrade the project contract to Schema v3

**Files:**

- Modify: `schemas/stm32-project.schema.json`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/schemas/stm32-project.schema.json`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/project_model.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/project_upgrade.py`
- Modify: `tools/stm32-toolkit/tests/test_project.py`
- Modify: `tools/stm32-toolkit/tests/test_project_upgrade.py`
- Create: `tools/stm32-toolkit/tests/test_project_v3.py`

- [ ] Write failing v3 tests for Host and all Target transport options, strict integer/address/
  baud/timeout/env bounds, workspace-relative ELF, unknown fields, v2/v3 reads, v3 writes, v1
  explicit route, v2 dry-run exact diff, authorized apply, changed-source rejection, and schema
  mirror equality.

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_project.py tools/stm32-toolkit/tests/test_project_upgrade.py tools/stm32-toolkit/tests/test_project_v3.py -q -p no:cacheprovider
```

Expected: v3 fixtures are rejected or the new test module import fails.

- [ ] Implement typed `TestingConfig`, `HostTestConfig`, `TargetTestConfig`, and transport option
  unions; update writers to v3 and readers to v2/v3; preserve existing authorized upgrader
  semantics and comments/order guarantees.

- [ ] Run GREEN on 3.10/3.12 plus existing project/schema regressions:

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests/test_project.py tools/stm32-toolkit/tests/test_project_upgrade.py tools/stm32-toolkit/tests/test_project_v3.py -q -p no:cacheprovider
py -3.12 -m pytest tools/stm32-toolkit/tests/test_project.py tools/stm32-toolkit/tests/test_project_upgrade.py tools/stm32-toolkit/tests/test_project_v3.py --cov=stm32_toolkit.project_model --cov=stm32_toolkit.project_upgrade --cov-branch --cov-report=term-missing --cov-fail-under=90 -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add schemas/stm32-project.schema.json tools/stm32-toolkit/src/stm32_toolkit/schemas/stm32-project.schema.json tools/stm32-toolkit/src/stm32_toolkit/project_model.py tools/stm32-toolkit/src/stm32_toolkit/project_upgrade.py tools/stm32-toolkit/tests/test_project.py tools/stm32-toolkit/tests/test_project_upgrade.py tools/stm32-toolkit/tests/test_project_v3.py
git commit -m "feat(STM32TK-0601): define project schema v3 testing"
```

## Task 6: Implement the common test protocol and Host runner

**Files:**

- Create: `schemas/stm32-test.schema.json`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/schemas/stm32-test.schema.json`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/testing/{__init__,model,protocol,artifacts,host}.py`
- Create: `tools/stm32-toolkit/tests/test_testing_model.py`
- Create: `tools/stm32-toolkit/tests/test_host_testing.py`

- [ ] Write failing model/state tests for exact test/case states, one terminal event, duplicate
  IDs, empty inventory, incomplete case, exit/event disagreement, artifacts, identity, limits,
  root/packaged schema equality, canonical Host build/test-executable inventory digests, and
  `target_device=host:<os>/<architecture>` without dummy firmware values.

- [ ] Write failing Host tests using fake CMake/CTest executables. Assert list-form argv, exact
  `--show-only=json-v1`, JUnit parsing, allowlisted env only, exact case selection, inventory
  digest freeze, timeout/whole-process-tree cleanup, external results, and no ambient shell.

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_testing_model.py tools/stm32-toolkit/tests/test_host_testing.py -q -p no:cacheprovider
```

- [ ] Implement immutable `TestRunManifest`/`TestCaseResult`, transition validation, evidence
  artifact ingestion, and `HostTestRunner.discover/run` through the existing safe process layer.

```python
class HostTestRunner:
    def discover(self, config: HostTestConfig, identity: EvidenceIdentity) -> TestInventory: ...
    def run(self, inventory: TestInventory, case_ids: tuple[str, ...]) -> TestRunManifest: ...
```

- [ ] Run GREEN on both interpreters and per-file branch coverage:

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests/test_testing_model.py tools/stm32-toolkit/tests/test_host_testing.py -q -p no:cacheprovider
py -3.12 -m pytest tools/stm32-toolkit/tests/test_testing_model.py tools/stm32-toolkit/tests/test_host_testing.py --cov=stm32_toolkit.testing --cov-branch --cov-report=term-missing --cov-fail-under=90 -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add schemas/stm32-test.schema.json tools/stm32-toolkit/src/stm32_toolkit/schemas/stm32-test.schema.json tools/stm32-toolkit/src/stm32_toolkit/testing tools/stm32-toolkit/tests/test_testing_model.py tools/stm32-toolkit/tests/test_host_testing.py
git commit -m "feat(STM32TK-0601): run identity-bound host tests"
```

## Task 7: Implement Target framing and transport adapters

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/testing/target.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/testing/transports/{__init__,base,mailbox,rtt,uart,semihosting}.py`
- Modify: `tools/stm32-toolkit/pyproject.toml`
- Create: `tools/stm32-toolkit/tests/test_target_protocol.py`
- Create: `tools/stm32-toolkit/tests/test_target_transports.py`
- Add: `tools/stm32-toolkit/tests/fixtures/target-streams/*`

- [ ] Write failing frame tests for byte-at-a-time fragmentation, concatenation, strict sequence,
  CRC/magic/version/length/UTF-8 errors, bounded recovery, oversize-before-allocation, 64 MiB run
  limit, incomplete stream, and terminal digest/count/identity binding. Add deterministic recorded
  replay fixtures and property-generated fragmentation/corruption cases.

- [ ] Write failing adapter tests for typed config, open/read/close deadlines, mailbox RAM/ring
  bounds and no target writes, RTT channel/RAM bounds, UART exact port/baud/8N1, semihosting host-
  file denial, disconnect cleanup, identity, and `TEST_TRANSPORT_UNAVAILABLE`.

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_target_protocol.py tools/stm32-toolkit/tests/test_target_transports.py -q -p no:cacheprovider
```

- [ ] Implement the shared incremental decoder and four thin `TargetTransport` adapters. Add
  `pyserial>=3.5,<4` to the `probe` optional dependency, not the base install, and keep all
  backend calls behind the protocol interface.

- [ ] Run GREEN on 3.10/3.12 with branch coverage:

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests/test_target_protocol.py tools/stm32-toolkit/tests/test_target_transports.py -q -p no:cacheprovider
py -3.12 -m pytest tools/stm32-toolkit/tests/test_target_protocol.py tools/stm32-toolkit/tests/test_target_transports.py --cov=stm32_toolkit.testing.target --cov=stm32_toolkit.testing.transports --cov-branch --cov-report=term-missing --cov-fail-under=90 -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add tools/stm32-toolkit/pyproject.toml tools/stm32-toolkit/src/stm32_toolkit/testing tools/stm32-toolkit/tests/test_target_protocol.py tools/stm32-toolkit/tests/test_target_transports.py tools/stm32-toolkit/tests/fixtures/target-streams
git commit -m "feat(STM32TK-0601): decode target tests across four transports"
```

## Task 8: Freeze Probe v2 and execute authorized Target runs

**Files:**

- Modify: `schemas/probe-protocol.schema.json`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/schemas/probe-protocol.schema.json`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/{protocol,model,service,client,backend,pyocd_backend}.py`
- Create: `tools/stm32-toolkit/tests/test_probe_protocol_v2.py`
- Create: `tools/stm32-toolkit/tests/test_target_runner.py`

- [ ] Write failing schema/protocol tests for exact v2 operations and arguments, v1/v2 mismatch,
  unknown fields/operations, same-version requirement, bounded reads/backpressure, lease cleanup,
  unavailable reserved 0602 operations, and root/packaged schema equality.

- [ ] Write failing Target runner tests proving the MODIFY digest binds every specified field,
  is single-use, rejects stale revision/identity/inventory, flashes through guarded workflow,
  re-reads target identity, closes on every failure, and persists raw/test/evidence manifests.

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_probe_protocol_v2.py tools/stm32-toolkit/tests/test_target_runner.py -q -p no:cacheprovider
```

- [ ] Implement the full closed v2 schema, testing transport service operations, unavailable
  typed stubs for 0602 operations, client validation, and `TargetTestRunner.prepare/run`.

- [ ] Run GREEN on both Pythons and affected Probe/process/hardware regressions:

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests/test_probe_protocol_v2.py tools/stm32-toolkit/tests/test_target_runner.py tools/stm32-toolkit/tests/test_probe_service.py tools/stm32-toolkit/tests/test_process.py -q -p no:cacheprovider
py -3.12 -m pytest tools/stm32-toolkit/tests/test_probe_protocol_v2.py tools/stm32-toolkit/tests/test_target_runner.py tools/stm32-toolkit/tests/test_probe_service.py tools/stm32-toolkit/tests/test_process.py --cov=stm32_toolkit.probe --cov=stm32_toolkit.testing.target --cov-branch --cov-report=term-missing --cov-fail-under=90 -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add schemas/probe-protocol.schema.json tools/stm32-toolkit/src/stm32_toolkit/schemas/probe-protocol.schema.json tools/stm32-toolkit/src/stm32_toolkit/probe tools/stm32-toolkit/src/stm32_toolkit/testing/target.py tools/stm32-toolkit/tests/test_probe_protocol_v2.py tools/stm32-toolkit/tests/test_target_runner.py
git commit -m "feat(STM32TK-0601): authorize identity-bound target runs"
```

## Task 9: Expose CLI/MCP/Skill and evidence GC

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/cli.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`
- Create: `skills/test-firmware/SKILL.md`
- Create: `tools/stm32-toolkit/tests/test_testing_cli.py`
- Create: `tools/stm32-toolkit/tests/test_testing_mcp.py`
- Modify: `tools/stm32-toolkit/tests/test_plugin_layout.py`

- [ ] Write failing CLI/MCP tests for exact typed commands/tools, bounded output, artifact
  references, all error codes, read-only evidence operations, GC dry-run/authorization, Target
  prepare-before-run, action digest mutation, workspace isolation, and no secret/absolute path.

- [ ] Write failing plugin-layout tests requiring the new thin Skill and prohibiting subprocess,
  arbitrary shell, reusable authorization, model/cloud/API-key, and implicit Target execution.

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_testing_cli.py tools/stm32-toolkit/tests/test_testing_mcp.py tools/stm32-toolkit/tests/test_plugin_layout.py -q -p no:cacheprovider
```

- [ ] Implement CLI/MCP adapters over public evidence/testing APIs and write the Skill with
  strategy, exact authorization dialogue, evidence interpretation, and no product logic.

- [ ] Run GREEN under both interpreters and affected CLI/MCP/plugin suites:

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests/test_testing_cli.py tools/stm32-toolkit/tests/test_testing_mcp.py tools/stm32-toolkit/tests/test_plugin_layout.py -q -p no:cacheprovider
py -3.12 -m pytest tools/stm32-toolkit/tests/test_testing_cli.py tools/stm32-toolkit/tests/test_testing_mcp.py tools/stm32-toolkit/tests/test_plugin_layout.py --cov=stm32_toolkit.cli --cov=stm32_toolkit.mcp_server --cov-branch --cov-report=term-missing --cov-fail-under=90 -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add tools/stm32-toolkit/src/stm32_toolkit/cli.py tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py skills/test-firmware/SKILL.md tools/stm32-toolkit/tests/test_testing_cli.py tools/stm32-toolkit/tests/test_testing_mcp.py tools/stm32-toolkit/tests/test_plugin_layout.py
git commit -m "feat(STM32TK-0601): expose evidence-backed test workflows"
```

## Task 10: Lock performance, packaging, and four real transports

**Files:**

- Create: `tools/stm32-toolkit/tests/test_evidence_performance.py`
- Create: `tools/stm32-toolkit/tests/hardware/test_target_transports_real.py`
- Modify: `tools/stm32-toolkit/tests/test_setup_runtime.py`
- Modify: `tools/stm32-toolkit/tests/test_plugin_layout.py`
- Modify: `README.md`
- Create: `tools/stm32-toolkit/README.md`

- [ ] Before optimizing, run the performance test skeleton under 3.10/3.12, retain baseline JSON
  externally, verify the frozen Windows reference CPU/memory/NVMe/OS/power/Python/tool profile,
  then freeze absolute ceilings and 15% regression expectations in test constants. If the
  environment differs, calibrate the prior accepted CodeHead before new hot-path code. Do not
  change a threshold or calibrate after observing a product failure.

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests/test_evidence_performance.py -q -s -p no:cacheprovider
py -3.12 -m pytest tools/stm32-toolkit/tests/test_evidence_performance.py -q -s -p no:cacheprovider
```

- [ ] Add real-board tests selected only by explicit hardware configuration. Each transport must
  execute its own flashed run and assert board/MCU/probe-hash/ELF/build/config/inventory/raw stream/
  terminal counts. Absence returns `TEST_TRANSPORT_UNAVAILABLE` and fails the declared release
  gate; it is never `pytest.skip` in acceptance.

- [ ] Add package/managed-runtime tests for all root/packaged schemas, optional serial/probe
  dependencies, CLI/MCP entry points, new Skill, offline wheel installation, and source inventory.

- [ ] Run the complete affected regressions on both Python versions, per-file coverage, and the
  performance gates. Then run each real transport on the named board and retain logs externally.

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests -q -p no:cacheprovider --basetemp C:\tmp\stm32tk-0601-bt-310
py -3.12 -m pytest tools/stm32-toolkit/tests -q -p no:cacheprovider --basetemp C:\tmp\stm32tk-0601-bt-312
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/release/run_0600_quick.ps1 -Module STM32TK-0601 -EvidenceRoot C:\tmp\stm32tk-0601-quick
```

Expected: complete Toolkit suite passes on both Pythons; coverage verifier reports every changed
product file at least 90%; all performance values meet absolute and regression ceilings; all four
real transport results PASS with distinct evidence.

- [ ] Update README support claims only after the real evidence exists. Document v3, Host/Target
  commands, transports, evidence root/GC, authorization, limits, and honest unavailable behavior.

- [ ] Commit:

```powershell
git add -- tools/stm32-toolkit/tests/test_evidence_performance.py tools/stm32-toolkit/tests/hardware/test_target_transports_real.py tools/stm32-toolkit/tests/test_setup_runtime.py tools/stm32-toolkit/tests/test_plugin_layout.py README.md tools/stm32-toolkit/README.md
git commit -m "test(STM32TK-0601): close evidence and transport acceptance"
```

## Task 11: Freeze and accept the 0601 CodeHead

**Files:**

- Create after PASS only: `docs/openclaw/returns/STM32TK-0601-TEST-EVIDENCE/r001-implementation-report.md`

- [ ] Audit `accepted-base..HEAD`, tracked/untracked, committed/uncommitted, and pushed/unpushed
  state; verify only authorized 0601 product/tests/docs/release files changed and all schema mirrors
  are byte-identical.

- [ ] Run ordered preflight of every 0601 candidate gate with an external evidence root. Fix any
  product/test/helper problem only by creating a new CodeHead and rerunning all affected gates.

- [ ] Freeze the product CodeHead and run the collect-all candidate matrix exactly once for that
  attempt:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/release/run_0600_candidate.ps1 -Module STM32TK-0601 -EvidenceRoot C:\tmp\stm32tk-0601-candidate-<full-codehead>
```

Expected: overall PASS; Windows/Linux and real-hardware results are present; every retained file
has path/bytes/SHA-256; before/after worktree states are clean.

- [ ] Reconcile gate/node/artifact inventories against the frozen catalog. Create the report-only
  child only now, recording accepted base and product CodeHead but not the report's own commit SHA.

- [ ] Verify the staged report is the sole change, then commit locally:

```powershell
git diff --check
git diff --name-only
git add docs/openclaw/returns/STM32TK-0601-TEST-EVIDENCE/r001-implementation-report.md
git diff --cached --name-only
git commit -m "docs(STM32TK-0601): record accepted test evidence CodeHead"
```

Expected: the report commit has exactly one changed path and becomes 0602's accepted base. Stop;
do not push, open/merge a PR, tag, or delete branches without separate user authorization.
