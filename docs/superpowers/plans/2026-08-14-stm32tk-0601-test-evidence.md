# STM32TK-0601 Test and Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver immutable evidence, Project Schema v3, deterministic Host/Target tests over four transports, and the executable 0.6 acceptance framework.

**Architecture:** Prove external platform/hardware capability first, then add a content-addressed evidence package and a closed test protocol inside Toolkit. Host tests wrap CMake/CTest with argv-only execution; Target tests share one framed event decoder across mailbox, RTT, UART, and semihosting adapters. Freeze the gate schema/families early, characterize correct measured paths against predeclared maxima, freeze accepted calibration before optional post-baseline optimization, and freeze complete exact 0601 gates/nodes only after all 0601 tests exist and before candidate.

**Tech Stack:** Python 3.10/3.12, dataclasses, jsonschema, SQLite, CMake/CTest JSON/JUnit, pyOCD, pyserial, pytest/pytest-cov, PowerShell 5.1, JSON Schema.

## Global Constraints

- Accepted base is exactly `bb6bc5e9ee937e4ce53996b31f25bf1109ffe13f`.
- Follow `docs/superpowers/specs/2026-08-14-stm32tk-0601-test-evidence-design.md`.
- Product Python remains `>=3.10`; run each affected correctness shard on 3.10 and 3.12.
- Each changed product Python file must reach at least 90% branch coverage in its owning shard.
- Preserve every 0.5 functional, safety, coverage, and performance threshold.
- Do not begin product tasks until the feasibility profile has named owners and PASS evidence for
  Windows, Linux browser launch, and all four real Target transport capabilities.
- Use `apply_patch` for source edits; preserve unrelated changes; use external temp/evidence roots.
- Never use an ambient shell for Host tests or accept arbitrary command strings.
- Real reset/flash/modify gates require a current-task user authorization bound to the exact action
  digest; this plan and a prior authorization do not grant or transfer it.
- No remote Git operation is authorized by this plan. Each listed commit is local until the user
  separately authorizes push/PR changes.
- After two consecutive candidate failures caused by an acceptance-contract gap, stop and audit
  the contract instead of adding another late gate.

---

## Task 1: Prove acceptance platform and hardware feasibility

**Files:**

- Create: `tools/release/verify_0600_feasibility.py`
- Create: `tools/stm32-toolkit/tests/release/test_acceptance_feasibility_0600.py`

- [ ] Write failing verifier tests requiring non-empty owner IDs; exact Windows/Linux host and
  tool profiles; board/MCU/probe/UART/power identities; firmware fixture bytes/SHA-256; mailbox,
  RTT, UART, semihosting, and Linux browser result records; immutable support-manifest binding;
  deterministic Linux shard package/import round trip; unique evidence paths; and rejection of
  missing/fake/skip/stale/cross-profile results.

```python
def test_feasibility_requires_all_real_capabilities(valid_profile):
    del valid_profile["capabilities"]["semihosting"]
    result = verify_feasibility(valid_profile)
    assert result.code == "FEASIBILITY_CAPABILITY_MISSING"
```

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/release/test_acceptance_feasibility_0600.py -q -p no:cacheprovider
```

Expected: import failure because `verify_0600_feasibility.py` does not exist.

- [ ] Implement a read-only verifier with closed capability names. It accepts only result JSON
  whose owner/profile/run fields and exact argv/tool digests bind entries already hashed in the
  support manifest; it does not accept arbitrary shell commands or create product PASS evidence.

- [ ] Run GREEN and commit the verifier before collecting external evidence:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/release/test_acceptance_feasibility_0600.py -q -p no:cacheprovider
git add -- tools/release/verify_0600_feasibility.py tools/stm32-toolkit/tests/release/test_acceptance_feasibility_0600.py
git commit -m "test(STM32TK-0600): verify acceptance feasibility"
```

- [ ] On the exact verifier CodeHead, run the known-good support fixture and aggregate the Windows,
  Linux, and physical-hardware results. The feasibility profile freezes the user-designated evidence
  channel identifier and handoff procedure. The named Linux owner creates the deterministic
  feasibility ZIP and the user places it in `C:\tmp\stm32tk-0600-feasibility-inbox`; the verifier never fetches it.
  Use a preflashed known-good board. If any reset/flash/modify action is required, stop for a current-
  task user authorization bound to its exact action digest; this plan does not grant it:

```bash
python3.12 tools/release/verify_0600_feasibility.py capture --shard linux --repo . --support /tmp/stm32tk-0600-support --profile /tmp/stm32tk-0600-support/feasibility/profile.json --evidence /tmp/stm32tk-0600-feasibility-linux
```

Expected: `shard-package.zip` and its SHA-256 contain Linux owner/profile, Python/Node/browser launch,
support/tool digests, and no credential or absolute-private-path field. Transfer that package
unchanged to the declared inbox.

```powershell
py -3.12 tools/release/verify_0600_feasibility.py run --repo . --support C:\tmp\stm32tk-0600-support --profile C:\tmp\stm32tk-0600-support\feasibility\profile.json --import-shard C:\tmp\stm32tk-0600-feasibility-inbox\linux-feasibility.zip --evidence C:\tmp\stm32tk-0600-feasibility-evidence
```

Expected: overall PASS with named Windows, Linux, and user/hardware owners; real independent
mailbox/RTT/UART/semihosting capture; Linux Chromium/Firefox/WebKit launch; exact tool/fixture/
hardware identities; and external evidence bytes/SHA-256. Any missing capability is BLOCKED.
Stop before Task 2 until the user either supplies it or explicitly revises 0.6 scope.

## Task 2: Freeze the gate schema, families, and controller contract

**Files:**

- Create: `tools/release/gates_0600.json`
- Create: `tools/release/performance_0600.json`
- Create: `tools/release/run_0600_gates.py`
- Create: `tools/release/run_0600_quick.ps1`
- Create: `tools/release/run_0600_quick.sh`
- Create: `tools/release/run_0600_candidate.ps1`
- Create: `tools/release/run_0600_candidate.sh`
- Create: `tools/release/run_0600_final.ps1`
- Create: `tools/release/run_0600_final.sh`
- Create: `tools/release/verify_0600_release.py`
- Create: `tools/stm32-toolkit/tests/release/test_gate_catalog_0600.py`
- Create: `tools/stm32-toolkit/tests/release/test_gate_controller_0600.py`
- Create: `tools/stm32-toolkit/tests/release/test_release_verifier_0600.py`

- [ ] Write failing catalog tests that require unique stable family IDs and non-executable reserved
  0601/0602/0603 families with owner class, platform class, evidence type, coverage-context type,
  prerequisite and impact-map schemas. Include duplicate, missing, extra, cyclic, unknown-
  prerequisite, executable future command/node, and unreserved-family cases.

```python
def test_gate_families_and_module_slots_are_frozen() -> None:
    catalog = load_catalog(CATALOG)
    assert catalog.family_ids == EXPECTED_FAMILY_IDS
    assert all(not entry.command_argv for entry in catalog.reserved_entries())
```

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/release/test_gate_catalog_0600.py -q -p no:cacheprovider
```

Expected: collection/import failure because the catalog/verifier does not exist.

- [ ] Implement a strict catalog loader/verifier. Freeze schema/families and typed 0601/0602/0603
  slots covering evidence/diagnostics/analytics/browser/release without fabricating future commands
  or node IDs. Add the empty versioned performance profile schema. Exact 0601 entries are populated
  in Task 13 after all 0601 tests exist.

- [ ] Give all quick/candidate/final wrappers the same closed runner interface: matrix/module/shard/run ID, evidence
  root, expected CodeHead, gate catalog, performance catalog, support profile, contract self-test,
  and candidate/final resume/recovery record. Give the verifier closed `performance-calibration`,
  `dependency-audit`, `candidate-evidence`, `final-readiness`, and `final-evidence` subcommands.
  Reject unknown switches, relative evidence roots, shell command strings, mismatched run IDs,
  and any resume without a policy-valid recovery record. At terminal PASS/FAIL/BLOCKED, each
  wrapper also writes the deterministic shard ZIP/manifest defined by the design; the verifier
  imports packages read-only and rejects any archive or inner-manifest discrepancy.

- [ ] Give `run_0600_gates.py performance` a module ID, validated repository `test-file`,
  `calibrate|verify` mode, required absolute output path, and verify-only performance-config path.
  It invokes the entire file through `sys.executable -m pytest` with environment isolation, never a
  custom shell, and rejects unknown modules, non-`test_*_performance.py` paths, stale workload/
  config digests, coverage variables, or an existing output file.

- [ ] Give `run_0600_gates.py dev-coverage` a task ID, new absolute evidence root, and argv-token
  separator. It discovers changed and untracked Python product files relative to `HEAD`, invokes
  only `sys.executable -m pytest` with validated repository test paths/coverage modules, emits branch
  JSON externally, and requires each discovered file (not the aggregate) to have integer branch
  coverage >=90%. Reject case-fold duplicates, missing/multiple rows, shell tokens, links, no changed
  product file, and any changed product file absent from the coverage output.

- [ ] Add controller contract tests with fake executable fixtures. Assert quick/candidate collect
  all independent failures, each candidate shard runs a non-executing precheck before its first
  product body, final readiness executes no product body, platform shards bind one logical
  finalRunId, final is fail-fast, product frameworks have zero hidden retries, eligible external
  errors can resume once, ineligible/repeated errors cannot, each gate emits bounded metadata/hash,
  catalog locks prevent performance-host/board/probe/UART/port/evidence-root conflicts, and
  controller subprocesses run without product coverage environment variables.

- [ ] Add support/evidence verifier mutation tests: exact support-root manifest path/size/SHA-256,
  no missing/extra/case-fold duplicate/link/reparse/special file, immutable Node/npm/Python/
  browser/wheelhouse caches, unique empty evidence root, exact node inventory executed once, and
  failure when any retained log/result/screenshot/coverage/wheel is missing or hash-mismatched.

- [ ] Add deterministic shard-package/import tests: sorted POSIX-relative ZIP members, fixed
  metadata, canonical inner manifest, package/member bytes/SHA-256, closed owner/platform/run/
  CodeHead/catalog/lock/support bindings, no credential or absolute-private-path fields, no link/
  traversal/case-fold duplicate/extra member, no import rewrite, and no controller network access.

- [ ] Add deterministic audit-policy tests for pinned advisory/cache digests, production zero
  vulnerabilities, development zero high/critical vulnerabilities, and only pre-candidate
  user-approved expiring exceptions. Require advisory source/database version/generated UTC/digest
  and age <=7 calendar days at candidate/final readiness. Network audit output must be rejected as
  release evidence.

- [ ] Run GREEN and controller-only coverage-off regression:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/release -q -p no:cacheprovider
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/release/run_0600_quick.ps1 -ContractSelfTest
```

Expected: all tests pass; self-test deliberately exercises PASS/FAIL/BLOCKED without touching
product code, network, or remote Git.

- [ ] Commit:

```powershell
git add -- tools/release/gates_0600.json tools/release/performance_0600.json tools/release/run_0600_gates.py tools/release/run_0600_quick.ps1 tools/release/run_0600_quick.sh tools/release/run_0600_candidate.ps1 tools/release/run_0600_candidate.sh tools/release/run_0600_final.ps1 tools/release/run_0600_final.sh tools/release/verify_0600_release.py tools/stm32-toolkit/tests/release/test_gate_catalog_0600.py tools/stm32-toolkit/tests/release/test_gate_controller_0600.py tools/stm32-toolkit/tests/release/test_release_verifier_0600.py
git commit -m "test(STM32TK-0601): freeze 0.6 gate contract"
```

## Task 3: Implement canonical evidence models and schemas

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
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0601-T03 --evidence-root C:\tmp\stm32tk-0601-t03-coverage -- tools/stm32-toolkit/tests/test_evidence_model.py tools/stm32-toolkit/tests/test_evidence_schema.py --cov=stm32_toolkit.evidence.model -q -p no:cacheprovider
```

Expected: both pass and `model.py` branch coverage is at least 90%.

- [ ] Commit:

```powershell
git add -- schemas/evidence-envelope.schema.json tools/stm32-toolkit/src/stm32_toolkit/evidence/__init__.py tools/stm32-toolkit/src/stm32_toolkit/evidence/model.py tools/stm32-toolkit/src/stm32_toolkit/schemas/evidence-envelope.schema.json tools/stm32-toolkit/tests/test_evidence_model.py tools/stm32-toolkit/tests/test_evidence_schema.py
git commit -m "feat(STM32TK-0601): add canonical evidence envelopes"
```

## Task 4: Build the content-addressed store and catalog

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
  proof that forged catalog rows cannot create evidence, non-authoritative summary results that do
  not hash objects, and mandatory `get_envelope()` verification before an action consumes a row.

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
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0601-T04 --evidence-root C:\tmp\stm32tk-0601-t04-coverage -- tools/stm32-toolkit/tests/test_evidence_store.py tools/stm32-toolkit/tests/test_evidence_catalog.py --cov=stm32_toolkit.evidence.store --cov=stm32_toolkit.evidence.catalog -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add -- tools/stm32-toolkit/src/stm32_toolkit/evidence/store.py tools/stm32-toolkit/src/stm32_toolkit/evidence/catalog.py tools/stm32-toolkit/tests/test_evidence_store.py tools/stm32-toolkit/tests/test_evidence_catalog.py
git commit -m "feat(STM32TK-0601): persist verified evidence objects"
```

## Task 5: Add reachability-based evidence garbage collection

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
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0601-T05 --evidence-root C:\tmp\stm32tk-0601-t05-coverage -- tools/stm32-toolkit/tests/test_evidence_gc.py --cov=stm32_toolkit.evidence.gc -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add tools/stm32-toolkit/src/stm32_toolkit/evidence/gc.py tools/stm32-toolkit/tests/test_evidence_gc.py
git commit -m "feat(STM32TK-0601): add safe evidence collection plans"
```

## Task 6: Upgrade the project contract to Schema v3

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
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0601-T06 --evidence-root C:\tmp\stm32tk-0601-t06-coverage -- tools/stm32-toolkit/tests/test_project.py tools/stm32-toolkit/tests/test_project_upgrade.py tools/stm32-toolkit/tests/test_project_v3.py --cov=stm32_toolkit.project_model --cov=stm32_toolkit.project_upgrade -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add schemas/stm32-project.schema.json tools/stm32-toolkit/src/stm32_toolkit/schemas/stm32-project.schema.json tools/stm32-toolkit/src/stm32_toolkit/project_model.py tools/stm32-toolkit/src/stm32_toolkit/project_upgrade.py tools/stm32-toolkit/tests/test_project.py tools/stm32-toolkit/tests/test_project_upgrade.py tools/stm32-toolkit/tests/test_project_v3.py
git commit -m "feat(STM32TK-0601): define project schema v3 testing"
```

## Task 7: Implement the common test protocol and Host runner

**Files:**

- Create: `schemas/stm32-test.schema.json`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/schemas/stm32-test.schema.json`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/testing/__init__.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/testing/model.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/testing/protocol.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/testing/artifacts.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/testing/host.py`
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
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0601-T07 --evidence-root C:\tmp\stm32tk-0601-t07-coverage -- tools/stm32-toolkit/tests/test_testing_model.py tools/stm32-toolkit/tests/test_host_testing.py --cov=stm32_toolkit.testing -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add -- schemas/stm32-test.schema.json tools/stm32-toolkit/src/stm32_toolkit/schemas/stm32-test.schema.json tools/stm32-toolkit/src/stm32_toolkit/testing/__init__.py tools/stm32-toolkit/src/stm32_toolkit/testing/model.py tools/stm32-toolkit/src/stm32_toolkit/testing/protocol.py tools/stm32-toolkit/src/stm32_toolkit/testing/artifacts.py tools/stm32-toolkit/src/stm32_toolkit/testing/host.py tools/stm32-toolkit/tests/test_testing_model.py tools/stm32-toolkit/tests/test_host_testing.py
git commit -m "feat(STM32TK-0601): run identity-bound host tests"
```

## Task 8: Implement Target framing and transport adapters

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/testing/target.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/testing/transports/__init__.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/testing/transports/base.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/testing/transports/mailbox.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/testing/transports/rtt.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/testing/transports/uart.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/testing/transports/semihosting.py`
- Modify: `tools/stm32-toolkit/pyproject.toml`
- Create: `tools/stm32-toolkit/tests/test_target_protocol.py`
- Create: `tools/stm32-toolkit/tests/test_target_transports.py`
- Create: `tools/stm32-toolkit/tests/fixtures/target-streams/replay-manifest.json`
- Create: `tools/stm32-toolkit/tests/fixtures/target-streams/valid-run.bin`
- Create: `tools/stm32-toolkit/tests/fixtures/target-streams/corrupt-crc.bin`
- Create: `tools/stm32-toolkit/tests/fixtures/target-streams/truncated-frame.bin`
- Create: `tools/stm32-toolkit/tests/fixtures/target-streams/oversize-header.bin`

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
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0601-T08 --evidence-root C:\tmp\stm32tk-0601-t08-coverage -- tools/stm32-toolkit/tests/test_target_protocol.py tools/stm32-toolkit/tests/test_target_transports.py --cov=stm32_toolkit.testing.target --cov=stm32_toolkit.testing.transports -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add -- tools/stm32-toolkit/pyproject.toml tools/stm32-toolkit/src/stm32_toolkit/testing/target.py tools/stm32-toolkit/src/stm32_toolkit/testing/transports/__init__.py tools/stm32-toolkit/src/stm32_toolkit/testing/transports/base.py tools/stm32-toolkit/src/stm32_toolkit/testing/transports/mailbox.py tools/stm32-toolkit/src/stm32_toolkit/testing/transports/rtt.py tools/stm32-toolkit/src/stm32_toolkit/testing/transports/uart.py tools/stm32-toolkit/src/stm32_toolkit/testing/transports/semihosting.py tools/stm32-toolkit/tests/test_target_protocol.py tools/stm32-toolkit/tests/test_target_transports.py tools/stm32-toolkit/tests/fixtures/target-streams/replay-manifest.json tools/stm32-toolkit/tests/fixtures/target-streams/valid-run.bin tools/stm32-toolkit/tests/fixtures/target-streams/corrupt-crc.bin tools/stm32-toolkit/tests/fixtures/target-streams/truncated-frame.bin tools/stm32-toolkit/tests/fixtures/target-streams/oversize-header.bin
git commit -m "feat(STM32TK-0601): decode target tests across four transports"
```

## Task 9: Freeze Probe v2 and execute authorized Target runs

**Files:**

- Modify: `schemas/probe-protocol.schema.json`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/schemas/probe-protocol.schema.json`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/protocol.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/model.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/service.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/client.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/backend.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/testing/target.py`
- Create: `tools/stm32-toolkit/tests/test_probe_protocol_v2.py`
- Create: `tools/stm32-toolkit/tests/test_target_runner.py`

- [ ] Write failing schema/protocol tests for exact v2 operations and arguments, v1/v2 mismatch,
  unknown fields/operations, same-version requirement, bounded reads/backpressure, lease cleanup,
  unavailable reserved 0602 operations, and root/packaged schema equality.

- [ ] Assert the implementation consumes the exact feasibility board/backend/transport profile;
  an identity or capability mismatch fails before schema freeze, lease, flash, or target capture.

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
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0601-T09 --evidence-root C:\tmp\stm32tk-0601-t09-coverage -- tools/stm32-toolkit/tests/test_probe_protocol_v2.py tools/stm32-toolkit/tests/test_target_runner.py tools/stm32-toolkit/tests/test_probe_service.py tools/stm32-toolkit/tests/test_process.py --cov=stm32_toolkit.probe --cov=stm32_toolkit.testing.target -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add -- schemas/probe-protocol.schema.json tools/stm32-toolkit/src/stm32_toolkit/schemas/probe-protocol.schema.json tools/stm32-toolkit/src/stm32_toolkit/probe/protocol.py tools/stm32-toolkit/src/stm32_toolkit/probe/model.py tools/stm32-toolkit/src/stm32_toolkit/probe/service.py tools/stm32-toolkit/src/stm32_toolkit/probe/client.py tools/stm32-toolkit/src/stm32_toolkit/probe/backend.py tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py tools/stm32-toolkit/src/stm32_toolkit/testing/target.py tools/stm32-toolkit/tests/test_probe_protocol_v2.py tools/stm32-toolkit/tests/test_target_runner.py
git commit -m "feat(STM32TK-0601): authorize identity-bound target runs"
```

## Task 10: Expose CLI/MCP/Skill and evidence GC

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
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0601-T10 --evidence-root C:\tmp\stm32tk-0601-t10-coverage -- tools/stm32-toolkit/tests/test_testing_cli.py tools/stm32-toolkit/tests/test_testing_mcp.py tools/stm32-toolkit/tests/test_plugin_layout.py --cov=stm32_toolkit.cli --cov=stm32_toolkit.mcp_server -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add tools/stm32-toolkit/src/stm32_toolkit/cli.py tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py skills/test-firmware/SKILL.md tools/stm32-toolkit/tests/test_testing_cli.py tools/stm32-toolkit/tests/test_testing_mcp.py tools/stm32-toolkit/tests/test_plugin_layout.py
git commit -m "feat(STM32TK-0601): expose evidence-backed test workflows"
```

## Task 11: Characterize, calibrate, and meet the 0601 performance contract

**Files:**

- Create: `tools/stm32-toolkit/tests/test_evidence_performance.py`
- Modify: `tools/release/performance_0600.json`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/evidence/store.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/evidence/catalog.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/testing/target.py`
- Modify: `tools/stm32-toolkit/tests/test_evidence_store.py`
- Modify: `tools/stm32-toolkit/tests/test_evidence_catalog.py`
- Modify: `tools/stm32-toolkit/tests/test_target_protocol.py`

- [ ] Add correctness-first end-to-end workloads for publish/reload, derived-summary list,
  Target decode/manifest publish, and verified catalog rebuild at the exact datasets in the spec.
  Confirm framework code records every raw sample and nearest-rank batch result; do not add caching,
  GC manipulation, or other hot-path optimization yet.

- [ ] Run calibration on the frozen Windows profile under 3.10 and 3.12: fast workloads use five
  warmups plus three × 30 measurements; slow workloads use three warmups plus three × 20. Retain
  raw JSON externally and calculate median batch p95, MAD margin, absolute candidate, and 15%
  relative limit with the verifier.

```powershell
py -3.10 tools/release/run_0600_gates.py performance --module STM32TK-0601 --test-file tools/stm32-toolkit/tests/test_evidence_performance.py --mode calibrate --output C:\tmp\stm32tk-0601-perf-310.json
py -3.12 tools/release/run_0600_gates.py performance --module STM32TK-0601 --test-file tools/stm32-toolkit/tests/test_evidence_performance.py --mode calibrate --output C:\tmp\stm32tk-0601-perf-312.json
py -3.12 tools/release/verify_0600_release.py performance-calibration --profile STM32TK-0601 --input C:\tmp\stm32tk-0601-perf-310.json --input C:\tmp\stm32tk-0601-perf-312.json --output tools/release/performance_0600.json
```

Expected: characterization formula and environment checks PASS; every calculated absolute threshold
is at or below its design maximum. The verifier updates `performance_0600.json` atomically only on
that PASS. If not, it leaves the tracked file byte-identical; improve the architecture/reference
implementation without changing the workload or maximum, rerun characterization, and never raise a
maximum.

- [ ] Record the accepted 3.10/3.12 baselines, batch p95/MAD, absolute thresholds, relative limits,
  environment digest, and workload digest in `performance_0600.json`. Stage only that contract and
  the performance test, run `diff --check`, then commit before any optional post-baseline
  optimization.

```powershell
git add -- tools/release/performance_0600.json tools/stm32-toolkit/tests/test_evidence_performance.py
git commit -m "test(STM32TK-0601): freeze calibrated evidence performance"
```

- [ ] Profile the correct reference. If a calibrated gate does not pass, add the smallest local,
  thread-safe optimization plus concurrency/corruption regression tests. Do not toggle global GC
  state or weaken authoritative verification.

- [ ] Always run both calibrated gates without coverage:

```powershell
py -3.10 tools/release/run_0600_gates.py performance --module STM32TK-0601 --test-file tools/stm32-toolkit/tests/test_evidence_performance.py --mode verify --performance-config tools/release/performance_0600.json --output C:\tmp\stm32tk-0601-perf-verify-310.json
py -3.12 tools/release/run_0600_gates.py performance --module STM32TK-0601 --test-file tools/stm32-toolkit/tests/test_evidence_performance.py --mode verify --performance-config tools/release/performance_0600.json --output C:\tmp\stm32tk-0601-perf-verify-312.json
```

- [ ] If and only if profiling produced product/test edits, run per-file coverage and commit the
  exact optimized paths. Otherwise record “no optimization required” externally and create no
  empty commit:

```powershell
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0601-T11 --evidence-root C:\tmp\stm32tk-0601-t11-coverage -- tools/stm32-toolkit/tests/test_evidence_store.py tools/stm32-toolkit/tests/test_evidence_catalog.py tools/stm32-toolkit/tests/test_target_protocol.py --cov=stm32_toolkit.evidence --cov=stm32_toolkit.testing.target -q -p no:cacheprovider
git add -- tools/stm32-toolkit/src/stm32_toolkit/evidence/store.py tools/stm32-toolkit/src/stm32_toolkit/evidence/catalog.py tools/stm32-toolkit/src/stm32_toolkit/testing/target.py tools/stm32-toolkit/tests/test_evidence_store.py tools/stm32-toolkit/tests/test_evidence_catalog.py tools/stm32-toolkit/tests/test_target_protocol.py tools/stm32-toolkit/tests/test_evidence_performance.py
git commit -m "perf(STM32TK-0601): meet calibrated evidence budgets"
```

Expected: both versions satisfy their accepted absolute thresholds and <=15% relative limit; all
correctness/concurrency/corruption tests pass and changed product files remain >=90% branch.

## Task 12: Close packaging and four real transports

**Files:**

- Create: `tools/stm32-toolkit/tests/hardware/test_target_transports_real.py`
- Modify: `tools/stm32-toolkit/tests/test_setup_runtime.py`
- Modify: `tools/stm32-toolkit/tests/test_plugin_layout.py`
- Modify: `README.md`
- Create: `tools/stm32-toolkit/README.md`

- [ ] Add real-board tests bound to the PASS feasibility profile. Each transport executes its own
  flashed run and asserts board/MCU/probe-hash/ELF/build/config/inventory/raw stream/terminal counts.
  Profile mismatch or absence returns `TEST_TRANSPORT_UNAVAILABLE`; acceptance never uses skip.

- [ ] Add package/managed-runtime tests for all root/packaged schemas, optional serial/probe
  dependencies, CLI/MCP entry points, new Skill, offline wheel installation, and source inventory.

- [ ] Before documenting support, run only the newly affected package tests on both Pythons and the
  four distinct real transports once on the physical-hardware owner. Prior tasks already own their
  dual-Python correctness/coverage/performance evidence; the candidate owns the complete affected
  regression. Retain all hardware logs outside the worktree.

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests/test_setup_runtime.py tools/stm32-toolkit/tests/test_plugin_layout.py -q -p no:cacheprovider
py -3.12 -m pytest tools/stm32-toolkit/tests/test_setup_runtime.py tools/stm32-toolkit/tests/test_plugin_layout.py -q -p no:cacheprovider
$env:STM32TK_FEASIBILITY_PROFILE='C:\tmp\stm32tk-0600-support\feasibility\profile.json'
try {
  py -3.12 -m pytest tools/stm32-toolkit/tests/hardware/test_target_transports_real.py -q -p no:cacheprovider
  if ($LASTEXITCODE -ne 0) { throw 'real transport acceptance failed' }
} finally {
  Remove-Item Env:STM32TK_FEASIBILITY_PROFILE -ErrorAction SilentlyContinue
}
```

Expected: package tests PASS under both Pythons; four independent hardware results bind the
feasibility profile and PASS.

- [ ] Update README claims only after real evidence exists. Document v3, commands, transports,
  evidence/GC, authorization, limits, and unavailable behavior. Commit exact paths:

```powershell
git add -- tools/stm32-toolkit/tests/hardware/test_target_transports_real.py tools/stm32-toolkit/tests/test_setup_runtime.py tools/stm32-toolkit/tests/test_plugin_layout.py README.md tools/stm32-toolkit/README.md
git commit -m "test(STM32TK-0601): close evidence and transport acceptance"
```

## Task 13: Freeze and accept the 0601 CodeHead

**Files:**

- Modify: `tools/release/gates_0600.json`
- Modify: `tools/stm32-toolkit/tests/release/test_gate_catalog_0600.py`
- Create after PASS only: `docs/openclaw/returns/STM32TK-0601-TEST-EVIDENCE/r001-implementation-report.md`

- [ ] Audit `accepted-base..HEAD`, tracked/untracked, committed/uncommitted, and pushed/unpushed
  state; verify only authorized 0601 product/tests/docs/release files changed and all schema mirrors
  are byte-identical.

- [ ] Collect every exact 0601 node only now, replace only the reserved 0601 catalog slots with
  closed argv/owners/platforms/timeouts/evidence/coverage/prerequisites/impact edges, and add
  catalog mutation tests proving missing/extra/duplicate/renamed/deselected/skip/xfail nodes fail.
  Commit this last test-contract change before candidate:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/release/test_gate_catalog_0600.py -q -p no:cacheprovider
git add -- tools/release/gates_0600.json tools/stm32-toolkit/tests/release/test_gate_catalog_0600.py
git commit -m "test(STM32TK-0601): freeze exact candidate inventory"
```

- [ ] Freeze the resulting exact 0601 catalog, node, impact-map, and performance digests. Each
  candidate wrapper command below must first run its non-executing CodeHead/support/tools/owner/
  hardware/evidence-root/collect-only/controller precheck and refuse to start a product body on
  failure. Fix any repository problem only via a new CodeHead; environment-only precheck problems
  may be corrected externally and the same command restarted before any product result exists.

- [ ] Generate one `candidateRunId`, then run the affected collect-all candidate shards for that
  CodeHead on the named Windows, Linux, and hardware owners. Scheduling-target overruns are warnings,
  not gate failures:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/release/run_0600_candidate.ps1 -Module STM32TK-0601 -Shard windows -CandidateRunId <candidateRunId> -EvidenceRoot C:\tmp\stm32tk-0601-candidate-<candidateRunId>\windows -ExpectedCodeHead <full-codehead> -Catalog tools/release/gates_0600.json -Performance tools/release/performance_0600.json -SupportProfile C:\tmp\stm32tk-0600-support\feasibility\profile.json
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/release/run_0600_candidate.ps1 -Module STM32TK-0601 -Shard hardware -CandidateRunId <candidateRunId> -EvidenceRoot C:\tmp\stm32tk-0601-candidate-<candidateRunId>\hardware -ExpectedCodeHead <full-codehead> -Catalog tools/release/gates_0600.json -Performance tools/release/performance_0600.json -SupportProfile C:\tmp\stm32tk-0600-support\feasibility\profile.json
```

```bash
./tools/release/run_0600_candidate.sh --module STM32TK-0601 --shard linux --candidate-run-id <candidateRunId> --evidence-root /tmp/stm32tk-0601-candidate-<candidateRunId>/linux --expected-code-head <full-codehead> --catalog tools/release/gates_0600.json --performance tools/release/performance_0600.json --support-profile /tmp/stm32tk-0600-support/feasibility/profile.json
```

The Linux owner returns `linux/shard-package.zip` and its SHA-256 through the user-designated
evidence channel; place it unchanged at
`C:\tmp\stm32tk-0601-candidate-<candidateRunId>\imports\linux.zip`. No controller performs transfer.

Expected: overall PASS; Windows/Linux and real-hardware results are present; every retained file
has path/bytes/SHA-256; before/after worktree states are clean.

- [ ] If a shard reports one enumerated external event, preserve its attempt, have the reviewer
  write the recovery record, and resume only that shard once at the same candidate run ID and
  frozen inputs (`-ResumeRun ... -RecoveryRecord <absolute-json>` on PowerShell;
  `--resume-run ... --recovery-record <absolute-json>` on Linux). Repeated infrastructure failure
  is BLOCKED. Assertion/security/coverage/performance/timeout/corruption/dependency/product failure
  is not resumable and requires correction plus a new CodeHead/candidate run.

- [ ] Reconcile all shards and gate/node/artifact inventories against the frozen catalog:

```powershell
py -3.12 tools/release/verify_0600_release.py candidate-evidence --module STM32TK-0601 --candidate-run-id <candidateRunId> --evidence C:\tmp\stm32tk-0601-candidate-<candidateRunId> --import-shard C:\tmp\stm32tk-0601-candidate-<candidateRunId>\imports\linux.zip --expected-code-head <full-codehead> --catalog tools/release/gates_0600.json --performance tools/release/performance_0600.json --support-profile C:\tmp\stm32tk-0600-support\feasibility\profile.json
```

  Create the report-only child only after reconciliation PASS, recording accepted base, product
  CodeHead, `candidateRunId`, per-gate owner/platform/tool/command/result, coverage/performance,
  recovery attempts if any, and external evidence paths/bytes/SHA-256, but not the report's own SHA.

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
