# STM32TK-0601 Test and Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver immutable evidence, Project Schema v3, deterministic Host/Target tests over four transports, and the executable 0.6 acceptance framework.

**Architecture:** Prove Windows software/tool/support-fixture feasibility first, then add a content-addressed evidence package and a closed test protocol inside Toolkit. The feasibility verifier and controller contract are permitted acceptance infrastructure before that PASS. Host tests wrap separate CMake build and CTest presets with argv-only execution; Target tests share one little-endian CRC-32/ISO-HDLC framed decoder across mailbox, RTT, UART, and semihosting adapters. The Windows-only software candidate may finish as `SOFTWARE_COMPLETE_HARDWARE_PENDING`; both unified hardware contracts, including four real transports and the diagnostic chain, execute after the 0603 Candidate and remain mandatory for final `v0.6.0`.

**Tech Stack:** Python 3.10/3.12, dataclasses, jsonschema, SQLite, CMake/CTest JSON/JUnit, pyOCD, pyserial, pytest/pytest-cov, PowerShell 5.1, JSON Schema.

## Global Constraints

- Accepted base is exactly `bb6bc5e9ee937e4ce53996b31f25bf1109ffe13f`.
- Codex and Codex-derived agents permanently own implementation, review, and acceptance; no
  OpenClaw attempt, branch, report, or handoff semantics apply.
- Follow `docs/superpowers/specs/2026-08-14-stm32tk-0601-test-evidence-design.md`.
- Product Python remains `>=3.10`; run each affected correctness shard on 3.10 and 3.12.
- Each changed product Python file must reach at least 90% branch coverage in its owning shard.
- Preserve every 0.5 functional, safety, coverage, and performance threshold.
- Task 1 feasibility and Task 2 controller work are permitted acceptance infrastructure. Do not
  begin product Tasks 3--12 until the profile has a named Windows owner and PASS evidence for the
  Windows software/toolchain and immutable support fixture. Hardware PASS is not a coding
  prerequisite.
- Use `apply_patch` for source edits; preserve unrelated changes; use external temp/evidence roots.
- Never use an ambient shell for Host tests or accept arbitrary command strings.
- Real reset/flash/modify gates require a current-task, exact, single-use user authorization bound
  to the action digest. Those gates execute only in the post-0603 unified hardware activity; this
  plan and a prior authorization do not grant or transfer one.
- 0601 has no Linux owner, Linux browser, Linux shard, cross-machine transfer, or Linux evidence
  requirement. Linux is a separate later development effort.
- No remote Git operation is authorized by this plan. Each listed commit is local until the user
  separately authorizes push/PR changes.
- After two consecutive candidate failures caused by an acceptance-contract gap, stop and audit
  the contract instead of adding another late gate.
- Tasks 1--7 are accepted implementation history and are not reopened by the layered-integration
  amendment. The amendment below changes only the implementation source and ordering of Tasks
  8--13; it does not change any frozen Evidence, Test, Project v3, Host-runner, or gate behavior.
- The Task 9 timing delta that completes Probe v2 in 0601 becomes effective only after the user
  confirms the reconciled written-plan CodeHead. Until then, the implementation-timing sentence in
  the frozen 0601 design remains authoritative; confirmation supersedes that sentence only, not
  the already frozen Probe v2 public schema, safety levels, or operation set.

---

## Task 1: Prove Windows software and support-fixture feasibility

**Files:**

- Create: `tools/release/verify_0600_feasibility.py`
- Create: `tools/stm32-toolkit/tests/release/test_acceptance_feasibility_0600.py`

- [ ] Write failing verifier tests requiring a non-empty Windows owner ID; exact Windows host,
  CPython 3.10/3.12, PowerShell 5.1, CMake/CTest, pyOCD, pyserial, Node/npm, wheelhouse, and managed
  Chromium profiles; the exact Chromium executable/version/package-tree digest and a non-product
  blank-page launch proof bound to them;
  firmware fixture bytes/SHA-256; the declared RAM/mailbox/RTT/UART/semihosting capability
  contract without claiming real execution; immutable support-manifest binding; unique local
  evidence paths; and rejection of missing/fake/skip/stale/cross-profile results. Assert that Linux
  browser evidence, browser product-flow results, physical-hardware PASS, cross-machine package,
  and evidence-channel fields are forbidden; managed Chromium profile fields are required.

```python
def test_feasibility_requires_windows_support_contract(valid_profile):
    del valid_profile["tools"]["ctest"]
    result = verify_feasibility(valid_profile)
    assert result.code == "FEASIBILITY_CAPABILITY_MISSING"
```

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/release/test_acceptance_feasibility_0600.py -q -p no:cacheprovider
```

Expected: import failure because `verify_0600_feasibility.py` does not exist.

- [ ] Implement a read-only verifier with closed Windows software and fixture capability names. It
  accepts only result JSON whose owner/profile/run fields and exact argv/tool/fixture digests bind
  entries already hashed in the support manifest. Launch the exact managed Chromium executable only
  against a blank support-owned page and bind executable path, version, package-tree digest, argv,
  exit, and launch evidence. It does not accept arbitrary shell commands, hardware PASS claims,
  Linux browser evidence, browser product flows, or product PASS evidence.

- [ ] Run GREEN and commit the verifier before collecting external evidence:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/release/test_acceptance_feasibility_0600.py -q -p no:cacheprovider
git add -- tools/release/verify_0600_feasibility.py tools/stm32-toolkit/tests/release/test_acceptance_feasibility_0600.py
git commit -m "test(STM32TK-0600): verify acceptance feasibility"
```

- [ ] On the exact verifier CodeHead, run the known-good support fixture and capture the local
  Windows result. This task performs no probe lease, hardware open, reset, halt, flash, target-memory
  access, UART open, or semihosting session:

```powershell
$frozenWorktree = (Resolve-Path -LiteralPath '.').Path
$feasibilityVerifier = Join-Path $frozenWorktree 'tools\release\verify_0600_feasibility.py'
py -3.12 $feasibilityVerifier run --repo $frozenWorktree --support C:\tmp\stm32tk-0600-support --profile C:\tmp\stm32tk-0600-support\feasibility\profile.json --evidence C:\tmp\stm32tk-0600-feasibility-evidence
```

Expected: overall PASS with the named Windows owner, exact software/tool/fixture identities,
declared four-transport capability contract, managed Chromium executable/version/package digest
and non-product launch proof, and local evidence bytes/SHA-256. Missing or mismatched Windows
software or support-fixture facts are BLOCKED. Hardware remains explicitly `PENDING` and cannot be
reported as PASS or FAIL here. Task 2 is allowed regardless because it is acceptance infrastructure;
stop before Task 3 until this Windows-only feasibility result passes.

## Task 2: Freeze the gate schema, families, and controller contract

**Files:**

- Create: `tools/release/gates_0600.json`
- Create: `tools/release/performance_0600.json`
- Create: `tools/release/run_0600_gates.py`
- Create: `tools/release/run_0600_quick.ps1`
- Create: `tools/release/run_0600_candidate.ps1`
- Create: `tools/release/run_0600_final.ps1`
- Create: `tools/release/run_0600_hardware.ps1`
- Create: `tools/release/path_contract_0600.ps1`
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
  slots covering evidence/diagnostics/analytics/release without fabricating future commands
  or node IDs. Add the empty versioned performance profile schema. Exact 0601 entries are populated
  in Task 13 after all 0601 tests exist. For 0601, `complete catalog` means exact 0601 nodes plus
  non-executable reserved 0602/0603 families.

- [ ] Freeze deferred Windows hardware families `HW-0400-DEFERRED`, `HW-0600-TRANSPORT`, and
  `HW-0600-DIAGNOSTIC`. Because the 0.4 reports named behaviors rather than formal IDs, define
  `STM32TK-HW-0400-PROBE-ATTACH-READ`, `STM32TK-HW-0400-FLASH-READBACK`,
  `STM32TK-HW-0400-HANDOFF-REACQUIRE`, `STM32TK-HW-0400-TYPED-READ-SAMPLE-FAULT`, and
  `STM32TK-HW-0400-CLI-MCP-WORKFLOWS`; bind each new catalog ID to the exact source-report
  paragraphs and do not claim the ID existed in 0.4. Define exact 0.6 gate IDs `STM32TK-HW-0600-MAILBOX`,
  `STM32TK-HW-0600-RTT`, `STM32TK-HW-0600-UART`, `STM32TK-HW-0600-SEMIHOSTING`, and
  `STM32TK-HW-0600-DIAGNOSTIC-CHAIN`, with exact hardware/probe/UART/evidence-root locks. Keep every
  deferred entry non-executable in the 0601 software candidate.

- [ ] Give all quick/candidate/final wrappers the same closed runner interface: matrix/module/shard/run ID, evidence
  root, expected CodeHead, gate catalog, performance catalog, support profile, contract self-test,
  and candidate/final resume/recovery record. Give the verifier closed `performance-calibration`,
  `dependency-audit`, `candidate-evidence`, `final-readiness`, `final-evidence`, and read-only
  `verify-release-ledger` subcommands.
  Reject unknown switches, relative evidence roots, shell command strings, mismatched run IDs,
  and any resume without a policy-valid recovery record. At terminal PASS/FAIL/BLOCKED, each
  wrapper also writes the deterministic local shard ZIP/manifest defined by the design; the
  verifier reads it locally and rejects any archive or inner-manifest discrepancy.

- [ ] Freeze `verify-release-ledger` to accept only `--ledger <abs> --digest <abs>
  --software-input <abs> --hardware-input <abs>`. It derives its repository from its own committed
  path, performs no mutation/network/remote Git/gate dispatch, and keeps stdout empty until every
  check succeeds; the only success stdout is canonical
  `{"mode":"verify-release-ledger","status":"PASS"}` plus LF. Require canonical absolute paths,
  exact adjacent sidecars, canonical UTF-8/no-BOM/NFC/sorted-key/compact/trailing-LF bytes, lowercase
  SHA-256 sidecars, and unchanged rereads for ledger and both inputs.

- [ ] Add release-ledger schema tests for the exact recursively closed `stm32-release-ledger/1`
  root, fixed repository/program/0400 identities, lowercase resolvable commit types, ancestry, 0601
  and 0602 sole-parent report-only paths, and the historical non-report-only 0400 exception. Freeze
  one implementation-and-test constant mapping `0601` to
  `docs/codex/returns/STM32TK-0601-TEST-EVIDENCE/implementation-report.md` and `0602` to
  `docs/codex/returns/STM32TK-0602-DIAGNOSTIC-LOOP/implementation-report.md`; neither verifier code
  nor fixtures may repeat a divergent report-path literal. Test
  the exact closed governance fields and JSON types with owner constants `Codex`, `Codex/local
  derived agents`, `Codex`, `Codex`, `user`, bounded `remote_state`, and sorted unique string arrays
  for `remote_actions`/`bounded_overrides`.

- [ ] Add source-binding tests requiring exactly two closed `{path,bytes,sha256}` references bound
  to the explicit command paths, reread bytes, hashes, and sidecars. Recursively validate the exact
  closed software-input root and equality of every identity/governance value. Recursively validate
  the full `stm32-hardware-campaign-inputs/1` root and nested support/firmware objects: canonical
  campaign UUID/time, generator equals `0603Product`, hardware owner equals governance, bounded
  non-placeholder identity strings, exact UID/serial hashes, exact ordered four transports,
  canonical distinct paths, byte/hash checks, and distinct firmware build IDs. Require the ledger
  `hardware` object to equal the parsed hardware input.

- [ ] Add artifact tests for exact `{kind,path,bytes,sha256}` fields, the nine-kind enum, repository
  versus external path rules, link/reparse/traversal rejection, and per-entry file byte/digest
  verification. Require the exact duplicate-free union of software artifacts and the two hardware-
  support/two firmware projections, sorted by UTF-8 bytes on `(kind,path)`; coalesce identical
  cross-source members once and reject in-source duplicates, divergent duplicate bytes/digests,
  same-path different-kind conflicts, missing/extra members, and wrong order.

- [ ] Add table-driven negative tests at every nesting level for one extra field, one missing field,
  every wrong JSON type (including boolean-as-integer), noncanonical object/array order, duplicate
  and conflicting union members, mutated ledger/source/sidecar/artifact bytes, stale declared byte
  counts/digests, swapped source arguments, hardware campaign/generator/owner mutation, and mutation
  between first read and final reread. Assert every failure has empty stdout and records zero gate
  dispatches; assert one fully valid fixture returns the sole canonical PASS object.

- [ ] For the 0600 Task 1 caller and every other verifier caller, re-derive
  `tools/release/verify_0600_release.py` beneath the frozen worktree and compare its working
  `git hash-object` with the expected-CodeHead `git rev-parse <CodeHead>:<path>` on first use and
  again immediately before every process creation. The immediately-pre-spawn caller check, not the
  script itself, owns protection against complete replacement before interpreter load; do not claim
  that executing code can independently attest its own load bytes. After the trusted verifier has
  loaded, make every mode repeat the on-disk blob check against exact clean repository `HEAD` before
  its first evidence action, output, or gate dispatch; `verify-release-ledger` additionally binds
  `HEAD` to ledger `0603Product`.

- [ ] Keep the two mutation seams distinct in tests. In the caller pre-spawn test, mutate the file
  after the cached first-use check but before the mandatory immediate check and assert the caller
  refuses to create the interpreter process. In the loaded-script test, load the known-good verifier
  code first, mutate its on-disk file before invoking its first-evidence-action seam, and assert that
  the already-loaded trusted check rejects it with empty stdout and zero gate dispatch. Do not use
  the loaded-script test to claim resistance to a whole-file replacement performed before load.

- [ ] Make the candidate wrapper exclusively create and atomically update
  `<candidateRoot>/candidate-ledger.json` with exactly `schema`, `module`, `candidate_run_id`,
  `expected_code_head`, `controller_path`, `candidate_root`, `evidence_root`, `catalog_sha256`,
  `performance_sha256`, `support_profile_sha256`, `checkpoint`, `state`, `created_at_utc`, and
  `updated_at_utc`, using the exact constants/enums/path rules from design §9. Add only
  `-ResumeCandidateRun -CandidateLedger <absolute JSON> -RecoveryRecord <absolute JSON>` for
  candidate resume and reject legacy `-ResumeRun`. Any external orchestration input is named
  `candidate-invocation-context.json`, is non-authoritative, and cannot create/update/substitute for
  the wrapper-owned ledger.

- [ ] Add candidate reconciliation tests that, before invoking a verifier, require the ledger-bound
  frozen worktree's exact HEAD, exact origin URL
  `https://github.com/XiaoyaoLinghao/stm32-toolkit.git`, and empty porcelain status including
  untracked files. Re-derive controller, verifier, catalog, and performance paths only from their
  fixed relative names under that worktree; compare every working file's Git blob to the committed
  CodeHead blob and compare catalog/performance SHA-256 to the ledger. Execute only the re-derived
  verifier path. Reject dirty/wrong-origin/wrong-HEAD/missing/uncommitted/hash-mismatched files and
  every executable/config path supplied by `candidate-invocation-context.json` or other context.

- [ ] Freeze the one program `RecoveryRecord` canonical schema with exactly `classification`,
  `event`, `reviewer`, `recorded_at_utc`, `run_kind`, `run_id`, `code_head`, `checkpoint`, and
  `interrupted_attempt_digest`. Test the fixed classification `RECOVERABLE_INFRA_ERROR`, exact events
  `HOST_POWER_OR_REBOOT`, `RUNNER_LOSS_BEFORE_CHILD_RESULT`,
  `PHYSICAL_USB_OR_PROBE_REMOVAL`, `TARGET_POWER_LOSS`, exact run kinds `candidate-0601`,
  `candidate-0602`, `candidate-0603`, `final-windows`, `hardware-0400`, `hardware-0600`, absolute
  checkpoint, canonical bytes, and rejection of disk events or any missing/extra/mismatched field.

- [ ] Implement `ConvertTo-CanonicalAbsolutePath` in `path_contract_0600.ps1`, dot-source that
  committed file from every PowerShell wrapper, and forbid newer-runtime-only path APIs. Freeze this exact
  PowerShell 5.1-compatible implementation:

```powershell
function ConvertTo-CanonicalAbsolutePath {
  param([Parameter(Mandatory=$true)][string]$Path,[Parameter(Mandatory=$true)][string]$Name)
  if ([string]::IsNullOrWhiteSpace($Path)) { throw "$Name is empty" }
  if ($Path -match '^[A-Za-z]:[^\\/]' -or $Path -match '^[\\/](?![\\/])') { throw "$Name is drive/root-relative" }
  if ($Path.StartsWith('\\?\') -or $Path.StartsWith('\\.\') -or $Path.StartsWith('\??\')) { throw "$Name is an alias path" }
  if ($Path.Length -gt 3 -and ($Path.EndsWith('\') -or $Path.EndsWith('/'))) { throw "$Name has a trailing separator" }
  if (-not [System.IO.Path]::IsPathRooted($Path)) { throw "$Name is relative" }
  $canonical = [System.IO.Path]::GetFullPath($Path)
  if ($Path -cne $canonical) { throw "$Name is not canonical" }
  return $canonical
}
```

  Add Windows PowerShell 5.1 contract tests for canonical drive/UNC paths, nonexistent absolute
  outputs, empty/relative/drive-relative/root-relative/device/extended/NT-alias paths, `.`/`..`,
  mixed separators, trailing separators, and every normalization mismatch.

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
  wheelhouse caches, unique empty evidence root, exact node inventory executed once, and
  failure when any retained log/result/screenshot/coverage/wheel is missing or hash-mismatched.

- [ ] Add deterministic local shard-package tests: sorted POSIX-relative ZIP members, fixed
  metadata, canonical inner manifest, package/member bytes/SHA-256, closed owner/platform/run/
  CodeHead/catalog/lock/support bindings, no credential or absolute-private-path fields, no link/
  traversal/case-fold duplicate/extra member, and no controller network access. Do not implement a
  cross-machine import or handoff interface.

- [ ] Implement `run_0600_hardware.ps1` with base parameters `-Contract 0400|0600`, `-Repo <absolute
  exact worktree>`, `-ExpectedCodeHead <tested product SHA>`, `-FinalRunId <id>`, and `-EvidenceRoot
  <new on first prepare, then checkpoint-bound absolute path>`, plus exactly one mode: `-PrepareAction`; `-ExecuteAction -Nonce <nonce>
  -ActionDigest <sha256> -Authorized`; or `-ResumeContract -Checkpoint <absolute checkpoint JSON>
  -RecoveryRecord <absolute recovery JSON>`.
  Reject unknown parameters, wrong-contract gate IDs, dirty/mismatched worktrees, cross-root or
  stale checkpoints, missing/expired/reused authorization, and support/hardware identity mismatches
  before a product body. `0400` dispatches only 0.4 deferred gates; `0600` dispatches the four
  transports plus diagnostic chain. Bind every prepare record/checkpoint/result/artifact to separate
  `controller_code_head` and `tested_code_head` values and reject evidence that substitutes the
  0.6 controller SHA for the tested 0.4 product SHA.

- [ ] Make `-PrepareAction` select only the next pending catalog action, create/update
  `<EvidenceRoot>/checkpoint.json` atomically, emit exactly nonce/digest/expiry/checkpoint, and exit
  after exactly one product-prepare API call and one combined OBSERVE-only identity/state snapshot.
  Bind the canonical prepare summary into the action digest/checkpoint and require counters
  `identity_state_read=1`, `control=0`, `modify=0`, `reset=0`, `halt=0`, `write=0`, and `flash=0`.
  Generate the nonce from 32 CSPRNG bytes and encode exactly 64 lowercase hex characters. Make
  `-ExecuteAction` consume the matching authorization once, re-read identity/state and reject any
  change before CONTROL/MODIFY, execute exactly one action, persist terminal evidence, advance the
  same-root checkpoint, and exit; it may not pre-authorize the next action. Make `-ResumeContract`
  verify contract/run/root/both CodeHeads,
  recovery record and single-resume eligibility, never rerun a completed action, and require a new
  prepare/authorization whenever hardware execution would be repeated. Require a separate
  reviewer-authored program `RecoveryRecord` with exactly `classification`, `event`, `reviewer`,
  `recorded_at_utc`, `run_kind`, `run_id`, `code_head`, `checkpoint`, and
  `interrupted_attempt_digest`; validate the closed classification/event/run-kind enums,
  checkpoint equality, run/CodeHead binding, and retained-attempt digest before resume. Readiness checks only that
  this authorization mechanism is available; it never prepares or pre-authorizes an action.

- [ ] Add fake-executable contract tests and a `-ContractSelfTest` path proving both contracts,
  exact dispatch sets, exactly one prepare OBSERVE snapshot, zero prepare CONTROL/MODIFY/reset/halt/
  write/flash, changed-state execute refusal, one action per execute, no next-action
  preauthorization, exact 64-lowercase-hex CSPRNG nonce/digest/expiry validation, atomic same-root checkpoint/recovery,
  dual-CodeHead binding, resource locks, single-use authorization refusal, completed-action no-rerun,
  failure isolation, and zero real probe/UART/hardware access. The self-test is part of Task 1/2
  acceptance infrastructure and does not claim a hardware PASS.

- [ ] Add deterministic audit-policy tests for pinned advisory/cache digests, production zero
  vulnerabilities, development zero high/critical vulnerabilities, and only pre-candidate
  user-approved expiring exceptions. Require advisory source/database version/generated UTC/digest
  and age <=7 calendar days at candidate/final readiness. Network audit output must be rejected as
  release evidence.

- [ ] Run GREEN and controller-only coverage-off regression:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/release -q -p no:cacheprovider
$frozenWorktree = (Resolve-Path -LiteralPath '.').Path
$quickController = Join-Path $frozenWorktree 'tools\release\run_0600_quick.ps1'
$hardwareController = Join-Path $frozenWorktree 'tools\release\run_0600_hardware.ps1'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $quickController -ContractSelfTest
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $hardwareController -ContractSelfTest
```

Expected: all tests pass; self-test deliberately exercises PASS/FAIL/BLOCKED without touching
product code, network, or remote Git.

- [ ] Commit:

```powershell
git add -- tools/release/gates_0600.json tools/release/performance_0600.json tools/release/path_contract_0600.ps1 tools/release/run_0600_gates.py tools/release/run_0600_quick.ps1 tools/release/run_0600_candidate.ps1 tools/release/run_0600_final.ps1 tools/release/run_0600_hardware.ps1 tools/release/verify_0600_release.py tools/stm32-toolkit/tests/release/test_gate_catalog_0600.py tools/stm32-toolkit/tests/release/test_gate_controller_0600.py tools/stm32-toolkit/tests/release/test_release_verifier_0600.py
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
  schema mirror equality. Golden bytes must prove UTF-8 without BOM, Unicode-code-point key order,
  NFC strings, contract array order, compact separators, integer-only numbers, and rejection of
  non-canonical authoritative encodings. Assert the exact fields and `stm32-evidence/1` identifier
  from design §4.1 and operation-specific closed metadata schemas.

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
$frozenWorktree = (Resolve-Path -LiteralPath '.').Path
$gateController = Join-Path $frozenWorktree 'tools\release\run_0600_gates.py'
py -3.12 $gateController dev-coverage --task-id STM32TK-0601-T03 --evidence-root C:\tmp\stm32tk-0601-t03-coverage -- tools/stm32-toolkit/tests/test_evidence_model.py tools/stm32-toolkit/tests/test_evidence_schema.py --cov=stm32_toolkit.evidence.model -q -p no:cacheprovider
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
$frozenWorktree = (Resolve-Path -LiteralPath '.').Path
$gateController = Join-Path $frozenWorktree 'tools\release\run_0600_gates.py'
py -3.12 $gateController dev-coverage --task-id STM32TK-0601-T04 --evidence-root C:\tmp\stm32tk-0601-t04-coverage -- tools/stm32-toolkit/tests/test_evidence_store.py tools/stm32-toolkit/tests/test_evidence_catalog.py --cov=stm32_toolkit.evidence.store --cov=stm32_toolkit.evidence.catalog -q -p no:cacheprovider
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

- [ ] Write failing tests for the exact typed-root fields `root_type`, `root_id`, `manifest_id`, and
  `metadata`; registered test/diagnostic/bundle/annotation roots; conservative retention of unknown
  or malformed future roots; shared objects; dry-run canonical plan/digest; store change after plan;
  corrupt/linked entries; single-use MODIFY authorization and digest mismatch; partial-delete
  failure; and concurrent new references.

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_evidence_gc.py -q -p no:cacheprovider
```

- [ ] Implement the typed-root registry, `plan_gc(store) -> GcPlan`, and `apply_gc(plan, authorized,
  expected_plan_digest) -> GcResult`; bind the authorization digest to workspace/store, plan,
  manifest snapshot, and bytes reclaimable, and retain anything not known, verified, and
  unreachable.

- [ ] Run GREEN on both Python versions and confirm branch coverage:

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests/test_evidence_gc.py -q -p no:cacheprovider
$frozenWorktree = (Resolve-Path -LiteralPath '.').Path
$gateController = Join-Path $frozenWorktree 'tools\release\run_0600_gates.py'
py -3.12 $gateController dev-coverage --task-id STM32TK-0601-T05 --evidence-root C:\tmp\stm32tk-0601-t05-coverage -- tools/stm32-toolkit/tests/test_evidence_gc.py --cov=stm32_toolkit.evidence.gc -q -p no:cacheprovider
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

- [ ] Write failing v3 tests for distinct required external `buildPreset`/`ctestPreset` fields and
  internal `build_preset`/`ctest_preset` names, Host and all Target transport options, strict integer/address/
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
  semantics and comments/order guarantees. Never infer one preset from the other.

- [ ] Run GREEN on 3.10/3.12 plus existing project/schema regressions:

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests/test_project.py tools/stm32-toolkit/tests/test_project_upgrade.py tools/stm32-toolkit/tests/test_project_v3.py -q -p no:cacheprovider
$frozenWorktree = (Resolve-Path -LiteralPath '.').Path
$gateController = Join-Path $frozenWorktree 'tools\release\run_0600_gates.py'
py -3.12 $gateController dev-coverage --task-id STM32TK-0601-T06 --evidence-root C:\tmp\stm32tk-0601-t06-coverage -- tools/stm32-toolkit/tests/test_project.py tools/stm32-toolkit/tests/test_project_upgrade.py tools/stm32-toolkit/tests/test_project_v3.py --cov=stm32_toolkit.project_model --cov=stm32_toolkit.project_upgrade -q -p no:cacheprovider
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
  `target_device=host:<os>/<architecture>` without dummy firmware values. Assert the exact
  `TestCaseResult` and `TestInventory` fields, UTF-8-byte-sorted case IDs, and closed per-kind event
  payload schemas from design §6.

- [ ] Write failing Host tests using fake CMake/CTest executables. Assert list-form argv, exact
  `cmake --build --preset <buildPreset>` followed by
  `ctest --preset <ctestPreset> --show-only=json-v1`, JUnit parsing, allowlisted env only, exact case selection, inventory
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
$frozenWorktree = (Resolve-Path -LiteralPath '.').Path
$gateController = Join-Path $frozenWorktree 'tools\release\run_0600_gates.py'
py -3.12 $gateController dev-coverage --task-id STM32TK-0601-T07 --evidence-root C:\tmp\stm32tk-0601-t07-coverage -- tools/stm32-toolkit/tests/test_testing_model.py tools/stm32-toolkit/tests/test_host_testing.py --cov=stm32_toolkit.testing -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add -- schemas/stm32-test.schema.json tools/stm32-toolkit/src/stm32_toolkit/schemas/stm32-test.schema.json tools/stm32-toolkit/src/stm32_toolkit/testing/__init__.py tools/stm32-toolkit/src/stm32_toolkit/testing/model.py tools/stm32-toolkit/src/stm32_toolkit/testing/protocol.py tools/stm32-toolkit/src/stm32_toolkit/testing/artifacts.py tools/stm32-toolkit/src/stm32_toolkit/testing/host.py tools/stm32-toolkit/tests/test_testing_model.py tools/stm32-toolkit/tests/test_host_testing.py
git commit -m "feat(STM32TK-0601): run identity-bound host tests"
```

## Mandatory Task 8 precondition: freeze the layered execution boundary

Before editing Task 8 product code, create a reviewable component-admission record in the Task 8
report and pass it independently. Map the remaining work as follows:

| Remaining task | Layer | Toolkit-owned result | L0 execution source |
|---|---|---|---|
| Task 8 | L1/L2 | framing, state machine, transport identity, limits, bounded-memory port, authorization boundary, Evidence | PyOCD RTT, pyserial 3.5, frozen semihosting backend; mailbox execution is wired to Probe v2 in Task 9 |
| Task 9 | L1/L2 | closed Probe v2 protocol, bounded-memory mailbox binding, lease/identity/authorization, adapter validation, Target runner | existing Probe Service and PyOCD backend |
| Task 10 | L1/L3 | one CLI/MCP/Skill surface and GC dialogue | no new execution engine |
| Task 11 | L4 | calibrated performance evidence | the existing shared 0600 controller/verifier |
| Task 12 | L4 | package and deferred hardware inventory | the existing managed runtime/package path |
| Task 13 | L4 | exact candidate inventory and acceptance report | the same shared 0600 controller/verifier/catalog |

For PyOCD, pyserial, and the selected semihosting backend, the admission record must contain the
exact resolved version, license and retained LICENSE/NOTICE source, offline package source and
digest, and exact Windows version/probe argv, exit code, and sanitized output. Commit the closed
record as `tools/stm32-toolkit/tests/fixtures/component-admission/target-transports/
admission-manifest.json`; retain the real installed-component version/probe output as
`pyocd-version.txt`, `pyserial-version.txt`, and `semihosting-backend-version.txt`, and retain the
real package API observations as `pyocd-fake-api-observation.json`,
`pyserial-loopback-observation.json`, and `semihosting-fake-api-observation.json`. The manifest
binds each file's byte count/SHA-256 to the executable/package digest, argv/API call, exit/result,
sanitization operation, and UTC capture.
This precondition is software-only: run the real installed package/backend code against the
accepted fake/replay target or bounded local loopback. These observations prove package/API fit,
not native RTT/UART/semihosting transport bytes and not physical support. Toolkit protocol replay
streams remain separately labeled under `fixtures/target-streams` and must never be presented as
native-tool output. It must execute no probe, UART
adapter, board reset, flash, halt, or other hardware body and cannot claim transport support. The
same adapters later consume and preserve the separately identity-bound real RTT/UART/semihosting
output in the post-0603 campaign, where parser results are cross-checked with backend status,
terminal frame, and Test inventory; only that campaign can supply native transport fixtures and
satisfy hardware PASS.
It must also test a closed parser/error mapping; canonical path and credential handling;
network denial; concurrent ownership; timeout, disconnect, partial-output, and cleanup behavior;
project/workspace/session/firmware/Test/Evidence identity binding; probe lease and exact
authorization binding; performance and package-size cost; and the amount of not-yet-written code
and maintenance avoided. It must run the complete 0.2--0.5 regression suite. A failed admission
record means the component is not admitted and the product requirement remains unchanged; there is
no silent fallback. Do not use hand-authored approximations of external output. Do not create a
provider marketplace, dynamic provider loader, second controller, GDB-server manager, or second
probe service.

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
- Create: `tools/stm32-toolkit/tests/fixtures/component-admission/target-transports/admission-manifest.json`
- Create: `tools/stm32-toolkit/tests/fixtures/component-admission/target-transports/pyocd-version.txt`
- Create: `tools/stm32-toolkit/tests/fixtures/component-admission/target-transports/pyserial-version.txt`
- Create: `tools/stm32-toolkit/tests/fixtures/component-admission/target-transports/semihosting-backend-version.txt`
- Create: `tools/stm32-toolkit/tests/fixtures/component-admission/target-transports/pyocd-fake-api-observation.json`
- Create: `tools/stm32-toolkit/tests/fixtures/component-admission/target-transports/pyserial-loopback-observation.json`
- Create: `tools/stm32-toolkit/tests/fixtures/component-admission/target-transports/semihosting-fake-api-observation.json`

- [ ] Write failing frame tests for byte-at-a-time fragmentation, concatenation, strict sequence,
  CRC/magic/version/length/UTF-8 errors, bounded recovery, oversize-before-allocation, 64 MiB run
  limit, incomplete stream, and terminal digest/count/identity binding. Add deterministic recorded
  replay fixtures and property-generated fragmentation/corruption cases. Bind exact golden bytes
  for unsigned little-endian fields, CRC-32/ISO-HDLC parameters, kind values 1--6, zero flags, and
  one fixture for each kind plus every declared corruption class.

- [ ] Write failing adapter tests for typed config, open/read/close deadlines, mailbox RAM/ring
  bounds and no target writes, RTT channel/RAM bounds, UART exact port/baud/8N1, semihosting host-
  file denial, disconnect cleanup, identity, and `TEST_TRANSPORT_UNAVAILABLE`. Validate only the
  eight baud values and exact profile-declared RAM/mailbox/RTT/UART/probe/semihosting capabilities.
  Exercise mailbox through an injected closed `BoundedMemoryReader` port whose only production
  binding is the Probe v2 public client completed in Task 9; Task 8 uses only the deterministic
  fake reader and cannot claim the production mailbox binding. Exercise RTT only through the
  admitted PyOCD RTT adapter, UART only through pyserial 3.5, and semihosting only through the
  admitted frozen debug backend with host-file operations denied before backend execution.
  Component-admission tests consume the real version/probe/API observations; frame/parser tests
  consume separately labeled Toolkit replay streams. Neither may claim native physical transport
  evidence before the post-0603 campaign.

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_target_protocol.py tools/stm32-toolkit/tests/test_target_transports.py -q -p no:cacheprovider
```

- [ ] Implement the shared incremental decoder and four thin `TargetTransport` adapters. Add
  `pyserial==3.5` to the `probe` optional dependency, not the base install. The mailbox adapter
  accepts only the closed read-only `BoundedMemoryReader` port, enforces address/ring/read bounds,
  and performs no target write; its Task 8 tests inject the deterministic fake reader. RTT uses
  PyOCD's RTT implementation; UART uses only
  the closed project port/baud/8N1 configuration; semihosting uses the frozen debug backend and
  enforces the host-file deny policy. Keep all execution calls behind the closed transport/probe
  interfaces. Toolkit, not an L0 engine, owns framing, state transitions, identity, authorization,
  Evidence publication, and public errors.

- [ ] Run GREEN on 3.10/3.12 with branch coverage:

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests/test_target_protocol.py tools/stm32-toolkit/tests/test_target_transports.py -q -p no:cacheprovider
$frozenWorktree = (Resolve-Path -LiteralPath '.').Path
$gateController = Join-Path $frozenWorktree 'tools\release\run_0600_gates.py'
py -3.12 $gateController dev-coverage --task-id STM32TK-0601-T08 --evidence-root C:\tmp\stm32tk-0601-t08-coverage -- tools/stm32-toolkit/tests/test_target_protocol.py tools/stm32-toolkit/tests/test_target_transports.py --cov=stm32_toolkit.testing.target --cov=stm32_toolkit.testing.transports -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add -- tools/stm32-toolkit/pyproject.toml tools/stm32-toolkit/src/stm32_toolkit/testing/target.py tools/stm32-toolkit/src/stm32_toolkit/testing/transports/__init__.py tools/stm32-toolkit/src/stm32_toolkit/testing/transports/base.py tools/stm32-toolkit/src/stm32_toolkit/testing/transports/mailbox.py tools/stm32-toolkit/src/stm32_toolkit/testing/transports/rtt.py tools/stm32-toolkit/src/stm32_toolkit/testing/transports/uart.py tools/stm32-toolkit/src/stm32_toolkit/testing/transports/semihosting.py tools/stm32-toolkit/tests/test_target_protocol.py tools/stm32-toolkit/tests/test_target_transports.py tools/stm32-toolkit/tests/fixtures/target-streams/replay-manifest.json tools/stm32-toolkit/tests/fixtures/target-streams/valid-run.bin tools/stm32-toolkit/tests/fixtures/target-streams/corrupt-crc.bin tools/stm32-toolkit/tests/fixtures/target-streams/truncated-frame.bin tools/stm32-toolkit/tests/fixtures/target-streams/oversize-header.bin tools/stm32-toolkit/tests/fixtures/component-admission/target-transports/admission-manifest.json tools/stm32-toolkit/tests/fixtures/component-admission/target-transports/pyocd-version.txt tools/stm32-toolkit/tests/fixtures/component-admission/target-transports/pyserial-version.txt tools/stm32-toolkit/tests/fixtures/component-admission/target-transports/semihosting-backend-version.txt tools/stm32-toolkit/tests/fixtures/component-admission/target-transports/pyocd-fake-api-observation.json tools/stm32-toolkit/tests/fixtures/component-admission/target-transports/pyserial-loopback-observation.json tools/stm32-toolkit/tests/fixtures/component-admission/target-transports/semihosting-fake-api-observation.json
git commit -m "feat(STM32TK-0601): decode target tests across four transports"
```

## Task 9: Freeze Probe v2 and implement the authorized Target runner

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
- Modify: `tools/stm32-toolkit/tests/test_target_transports.py`
- Create: `tools/stm32-toolkit/tests/test_probe_protocol_v2.py`
- Create: `tools/stm32-toolkit/tests/test_target_runner.py`

- [ ] Write failing schema/protocol tests for exact v2 operations and arguments, v1/v2 mismatch,
  unknown fields/operations, same-version requirement, bounded reads/backpressure, lease cleanup,
  implemented OBSERVE/CONTROL operations, and root/packaged schema equality. Cover every exact
  request/result/access class/limit in design §7. Cover the implemented transport/identity
  `OBSERVE` operations and exactly the reserved `target.state.read`, `target.halt`, `target.resume`,
  single-instruction/5-second `target.step`, temporary breakpoint set/clear with eight-per-session
  limit, 1--64 allowlisted ordered register reads, 1--4,096-byte memory reads,
  `target.fault.capture` with exact core fault registers and bounded stack artifact, and
  `target.logs.capture` with `rtt|uart|semihosting|swo|probe`, 10 MiB, and 300,000 ms limits. Assert
  every exact success-result field, reject `target.debug.capture`, `target.log.capture`, step counts,
  and every unlisted operation/field. Assert the design §7 common error-code allowlist and exact
  `{code,message,details}` error object, with no partial success. All listed read/control operations
  must have complete Probe Service, public client, and admitted PyOCD backend adapters in 0601;
  no operation may be deferred to 0602, and no later operation may be added without a
  protocol-version change.

- [ ] Assert the implementation consumes the exact Windows support board/backend/transport
  capability contract; an identity or capability mismatch fails before lease, flash, or target
  capture. Schema freeze depends on the accepted 0602 requirements, not on hardware feasibility.

- [ ] Add the production mailbox integration test that binds Task 8's `BoundedMemoryReader` port
  exclusively to the Probe v2 public client's bounded-memory operation. Prove exact request/range/
  identity propagation, read-only access, deadlines, disconnect cleanup, and rejection of any
  direct PyOCD/backend object or alternate binding. This is the first point at which the mailbox
  transport can claim its required production Probe v2 execution path.

- [ ] Write failing Target runner tests proving the MODIFY digest binds every specified field,
  is single-use, rejects stale revision/identity/inventory, flashes through guarded workflow,
  re-reads target identity, closes on every failure, and persists raw/test/evidence manifests. Add
  a read-only target-discovery handshake test proving it only opens/reads/closes an already-running
  configured target, never resets/halt/flashes/writes or consumes MODIFY authorization, and returns
  `TEST_TRANSPORT_UNAVAILABLE` on firmware/config mismatch.

- [ ] Freeze and test the Probe v2 public authorization client used by later diagnostic callers.
  Its prepare call generates the persistent 32-byte CSPRNG nonce, exact action digest and <=5-minute
  UTC expiry, performs exactly one OBSERVE identity/state snapshot and no CONTROL/MODIFY, and binds
  workspace/project/session/revision/target/probe/firmware/state/operation/arguments. Its execute
  call consumes one exact authorization, repeats the identity/state check, executes at most one
  CONTROL action, closes success/refusal/mismatch/failure/timeout, and rejects reuse. Keep the
  common closed result/error contract; later modules may bind domain events to this interface but
  may not implement another authorization state machine.

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_probe_protocol_v2.py tools/stm32-toolkit/tests/test_target_runner.py -q -p no:cacheprovider
```

- [ ] Implement the full closed v2 schema, testing transport operations and every listed
  OBSERVE/CONTROL operation through the existing Probe Service, public client, and PyOCD backend;
  implement client validation, the public authorization prepare/execute interface, and
  `TargetTestRunner.prepare/run`. Reuse the existing Probe
  Service/backend/lease boundary and do not create a GDB-server manager, second probe service, or
  parallel debug-control kernel. PyOCD remains an untrusted execution engine: Toolkit performs
  range checks, state/identity/lease/authorization validation, bounded result conversion, error
  mapping, and Evidence publication.

- [ ] Run GREEN on both Pythons and affected Probe/process fake-backend regressions:

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests/test_probe_protocol_v2.py tools/stm32-toolkit/tests/test_target_runner.py tools/stm32-toolkit/tests/test_target_transports.py tools/stm32-toolkit/tests/test_probe_service.py tools/stm32-toolkit/tests/test_process.py -q -p no:cacheprovider
$frozenWorktree = (Resolve-Path -LiteralPath '.').Path
$gateController = Join-Path $frozenWorktree 'tools\release\run_0600_gates.py'
py -3.12 $gateController dev-coverage --task-id STM32TK-0601-T09 --evidence-root C:\tmp\stm32tk-0601-t09-coverage -- tools/stm32-toolkit/tests/test_probe_protocol_v2.py tools/stm32-toolkit/tests/test_target_runner.py tools/stm32-toolkit/tests/test_target_transports.py tools/stm32-toolkit/tests/test_probe_service.py tools/stm32-toolkit/tests/test_process.py --cov=stm32_toolkit.probe --cov=stm32_toolkit.testing.target --cov=stm32_toolkit.testing.transports.mailbox -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add -- schemas/probe-protocol.schema.json tools/stm32-toolkit/src/stm32_toolkit/schemas/probe-protocol.schema.json tools/stm32-toolkit/src/stm32_toolkit/probe/protocol.py tools/stm32-toolkit/src/stm32_toolkit/probe/model.py tools/stm32-toolkit/src/stm32_toolkit/probe/service.py tools/stm32-toolkit/src/stm32_toolkit/probe/client.py tools/stm32-toolkit/src/stm32_toolkit/probe/backend.py tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py tools/stm32-toolkit/src/stm32_toolkit/testing/target.py tools/stm32-toolkit/tests/test_target_transports.py tools/stm32-toolkit/tests/test_probe_protocol_v2.py tools/stm32-toolkit/tests/test_target_runner.py
git commit -m "feat(STM32TK-0601): authorize identity-bound target runs"
```

## Task 10: Expose CLI/MCP/Skill and evidence GC

Tasks 10--13 must extend only the one controller/verifier/catalog established in Task 2. They must
not add module-specific controllers or reinterpret external native output with hand-authored
fixtures.

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
$frozenWorktree = (Resolve-Path -LiteralPath '.').Path
$gateController = Join-Path $frozenWorktree 'tools\release\run_0600_gates.py'
py -3.12 $gateController dev-coverage --task-id STM32TK-0601-T10 --evidence-root C:\tmp\stm32tk-0601-t10-coverage -- tools/stm32-toolkit/tests/test_testing_cli.py tools/stm32-toolkit/tests/test_testing_mcp.py tools/stm32-toolkit/tests/test_plugin_layout.py --cov=stm32_toolkit.cli --cov=stm32_toolkit.mcp_server -q -p no:cacheprovider
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
  raw JSON externally. For each batch, calculate nearest-rank p95 at the sorted sample numbered
  `ceil(0.95 * sample_count)`; take the median of three batch p95 values as baseline and their median
  absolute deviation as MAD. Calculate the untruncated absolute threshold as
  `baseline + max(0.25 * baseline, 3 * MAD, 10 * clock_tick)` and round upward to the next whole
  clock tick. If the rounded result exceeds the design maximum, calibration fails and writes no
  threshold; never clamp with `min()`. Verification must satisfy that threshold and
  `(candidate_p95 - baseline) / baseline <= 0.15`. Add fixed-vector verifier tests proving
  `(baseline=1000,MAD=100,tick=10)->1300`, `(1000,0,10)->1250` and failure against maximum 1200,
  and `(1003,10,8)->1256` after tick rounding.

```powershell
$frozenWorktree = (Resolve-Path -LiteralPath '.').Path
$gateController = Join-Path $frozenWorktree 'tools\release\run_0600_gates.py'
$releaseVerifier = Join-Path $frozenWorktree 'tools\release\verify_0600_release.py'
$performanceTest = Join-Path $frozenWorktree 'tools\stm32-toolkit\tests\test_evidence_performance.py'
$performanceConfig = Join-Path $frozenWorktree 'tools\release\performance_0600.json'
py -3.10 $gateController performance --module STM32TK-0601 --test-file $performanceTest --mode calibrate --output C:\tmp\stm32tk-0601-perf-310.json
py -3.12 $gateController performance --module STM32TK-0601 --test-file $performanceTest --mode calibrate --output C:\tmp\stm32tk-0601-perf-312.json
py -3.12 $releaseVerifier performance-calibration --profile STM32TK-0601 --input C:\tmp\stm32tk-0601-perf-310.json --input C:\tmp\stm32tk-0601-perf-312.json --output $performanceConfig
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
$frozenWorktree = (Resolve-Path -LiteralPath '.').Path
$gateController = Join-Path $frozenWorktree 'tools\release\run_0600_gates.py'
$performanceTest = Join-Path $frozenWorktree 'tools\stm32-toolkit\tests\test_evidence_performance.py'
$performanceConfig = Join-Path $frozenWorktree 'tools\release\performance_0600.json'
py -3.10 $gateController performance --module STM32TK-0601 --test-file $performanceTest --mode verify --performance-config $performanceConfig --output C:\tmp\stm32tk-0601-perf-verify-310.json
py -3.12 $gateController performance --module STM32TK-0601 --test-file $performanceTest --mode verify --performance-config $performanceConfig --output C:\tmp\stm32tk-0601-perf-verify-312.json
```

- [ ] If and only if profiling produced product/test edits, run per-file coverage and commit the
  exact optimized paths. Otherwise record “no optimization required” externally and create no
  empty commit:

```powershell
$frozenWorktree = (Resolve-Path -LiteralPath '.').Path
$gateController = Join-Path $frozenWorktree 'tools\release\run_0600_gates.py'
py -3.12 $gateController dev-coverage --task-id STM32TK-0601-T11 --evidence-root C:\tmp\stm32tk-0601-t11-coverage -- tools/stm32-toolkit/tests/test_evidence_store.py tools/stm32-toolkit/tests/test_evidence_catalog.py tools/stm32-toolkit/tests/test_target_protocol.py --cov=stm32_toolkit.evidence --cov=stm32_toolkit.testing.target -q -p no:cacheprovider
git add -- tools/stm32-toolkit/src/stm32_toolkit/evidence/store.py tools/stm32-toolkit/src/stm32_toolkit/evidence/catalog.py tools/stm32-toolkit/src/stm32_toolkit/testing/target.py tools/stm32-toolkit/tests/test_evidence_store.py tools/stm32-toolkit/tests/test_evidence_catalog.py tools/stm32-toolkit/tests/test_target_protocol.py tools/stm32-toolkit/tests/test_evidence_performance.py
git commit -m "perf(STM32TK-0601): meet calibrated evidence budgets"
```

Expected: both versions satisfy their accepted absolute thresholds and <=15% relative limit; all
correctness/concurrency/corruption tests pass and changed product files remain >=90% branch.

## Task 12: Close packaging and freeze deferred real-transport gates

**Files:**

- Create: `tools/stm32-toolkit/tests/hardware/test_target_transports_real.py`
- Modify: `tools/stm32-toolkit/tests/test_setup_runtime.py`
- Modify: `tools/stm32-toolkit/tests/test_plugin_layout.py`
- Modify: `README.md`
- Create: `tools/stm32-toolkit/README.md`

- [ ] Add real-board tests bound to the Windows support profile and the deferred `0600` hardware
  catalog family. Each transport test describes one independently authorized flashed run and
  asserts board/MCU/probe-hash/ELF/build/config/inventory/raw stream/terminal counts. Profile
  mismatch or absence returns `TEST_TRANSPORT_UNAVAILABLE`; acceptance never uses skip. During
  0601, run collect-only/node-inventory validation, not the test bodies.

- [ ] Add package/managed-runtime tests for all root/packaged schemas, optional serial/probe
  dependencies, CLI/MCP entry points, new Skill, offline wheel installation, and source inventory.

- [ ] Run the newly affected package tests on both Pythons and prove collect-only sees exactly four
  real-transport nodes without executing them. Prior tasks own dual-Python correctness/coverage/
  performance evidence; the Windows software candidate owns the complete fake/replay regression.

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests/test_setup_runtime.py tools/stm32-toolkit/tests/test_plugin_layout.py -q -p no:cacheprovider
py -3.12 -m pytest tools/stm32-toolkit/tests/test_setup_runtime.py tools/stm32-toolkit/tests/test_plugin_layout.py -q -p no:cacheprovider
py -3.12 -m pytest tools/stm32-toolkit/tests/hardware/test_target_transports_real.py --collect-only -q -p no:cacheprovider
```

Expected: package tests PASS under both Pythons; collect-only reports exactly the four frozen
transport nodes and performs zero probe/UART/hardware access. Hardware status remains `PENDING`.

- [ ] Update README with Project v3, commands, implemented transports, evidence/GC, authorization,
  limits, unavailable behavior, and the explicit `SOFTWARE_COMPLETE_HARDWARE_PENDING` status. Do
  not claim real transport support or final `v0.6.0` acceptance before the post-0603 activity.
  Commit exact paths:

```powershell
git add -- tools/stm32-toolkit/tests/hardware/test_target_transports_real.py tools/stm32-toolkit/tests/test_setup_runtime.py tools/stm32-toolkit/tests/test_plugin_layout.py README.md tools/stm32-toolkit/README.md
git commit -m "test(STM32TK-0601): freeze deferred transport acceptance"
```

## Task 13: Freeze and accept the 0601 CodeHead

**Files:**

- Modify: `tools/release/gates_0600.json`
- Modify: `tools/stm32-toolkit/tests/release/test_gate_catalog_0600.py`
- Create after software PASS only: `docs/codex/returns/STM32TK-0601-TEST-EVIDENCE/implementation-report.md`

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
  candidate wrapper command below must first run its non-executing CodeHead/support/tools/Windows-
  owner/evidence-root/collect-only/controller precheck and refuse to start a product body on
  failure. Fix any repository problem only via a new CodeHead; environment-only precheck problems
  may be corrected externally and the same command restarted before any product result exists.

- [ ] Generate one `candidateRunId`, then run the Windows-only collect-all software candidate for
  that CodeHead on the named Windows owner. Scheduling-target overruns are warnings, not gate
  failures:

```powershell
$frozenWorktree = (Resolve-Path -LiteralPath '.').Path
$pathContract = Join-Path $frozenWorktree 'tools\release\path_contract_0600.ps1'
. $pathContract
$frozenWorktree = ConvertTo-CanonicalAbsolutePath -Path $frozenWorktree -Name 'frozen worktree'
$codeHead = (git -C $frozenWorktree rev-parse HEAD).Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or $codeHead -notmatch '^[0-9a-f]{40}$') { throw 'invalid candidate CodeHead' }
$candidateController = Join-Path $frozenWorktree 'tools\release\run_0600_candidate.ps1'
$catalogPath = Join-Path $frozenWorktree 'tools\release\gates_0600.json'
$performancePath = Join-Path $frozenWorktree 'tools\release\performance_0600.json'
if (-not (Test-Path -LiteralPath $candidateController -PathType Leaf)) { throw 'missing frozen candidate controller' }
$candidateRunId = [guid]::NewGuid().ToString('D')
$shortCodeHead = $codeHead.Substring(0, 12)
$candidateRoot = "C:\tmp\stm32tk-0601-candidate-$candidateRunId-$shortCodeHead"
$candidateEvidence = Join-Path $candidateRoot 'windows'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $candidateController -Module STM32TK-0601 -Shard windows -CandidateRunId $candidateRunId -EvidenceRoot $candidateEvidence -ExpectedCodeHead $codeHead -Catalog $catalogPath -Performance $performancePath -SupportProfile C:\tmp\stm32tk-0600-support\feasibility\profile.json
```

Expected: software overall PASS; Windows results, all four fake/replay/capability-contract results,
and deferred hardware node inventory are present; every retained file has path/bytes/SHA-256;
before/after worktree states are clean. Status is `SOFTWARE_COMPLETE_HARDWARE_PENDING`.

- [ ] If a shard reports one enumerated external event, preserve its attempt, have the reviewer
  write the recovery record, and resume only that shard once at the same candidate run ID and
  frozen inputs. External orchestration metadata, if used, is written only as
  `candidate-invocation-context.json`; it cannot alter or replace the wrapper ledger. Resume with
  the absolute frozen controller and wrapper-owned ledger:

```powershell
$pathContract = Join-Path $frozenWorktree 'tools\release\path_contract_0600.ps1'
. $pathContract
$candidateLedgerPath = Join-Path $candidateRoot 'candidate-ledger.json'
$recoveryRecordPath = Join-Path $candidateRoot 'recovery-record.json'
$candidateLedgerPath = ConvertTo-CanonicalAbsolutePath -Path $candidateLedgerPath -Name 'candidate ledger'
$recoveryRecordPath = ConvertTo-CanonicalAbsolutePath -Path $recoveryRecordPath -Name 'recovery record'
if (-not (Test-Path -LiteralPath $candidateController -PathType Leaf)) { throw 'missing frozen candidate controller' }
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $candidateController -ResumeCandidateRun -CandidateLedger $candidateLedgerPath -RecoveryRecord $recoveryRecordPath
```

  Repeated infrastructure failure
  is BLOCKED. Assertion/security/coverage/performance/timeout/corruption/dependency/product failure
  is not resumable and requires correction plus a new CodeHead/candidate run.

- [ ] Reconcile all shards and gate/node/artifact inventories against the frozen catalog:

```powershell
$candidateLedgerPath = Join-Path $candidateRoot 'candidate-ledger.json'
$candidateLedger = Get-Content -Raw -LiteralPath $candidateLedgerPath | ConvertFrom-Json
$expectedLedgerFields = @('candidate_root','candidate_run_id','catalog_sha256','checkpoint','controller_path','created_at_utc','evidence_root','expected_code_head','module','performance_sha256','schema','state','support_profile_sha256','updated_at_utc')
$actualLedgerFields = @($candidateLedger.PSObject.Properties.Name | Sort-Object)
if (($actualLedgerFields -join ',') -cne ($expectedLedgerFields -join ',') -or $candidateLedger.schema -cne 'stm32-candidate-ledger/1' -or $candidateLedger.module -cne 'STM32TK-0601') { throw 'candidate ledger schema mismatch' }
$candidateRunId = [string]$candidateLedger.candidate_run_id
$codeHead = ([string]$candidateLedger.expected_code_head).ToLowerInvariant()
if ($candidateRunId -notmatch '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' -or $codeHead -notmatch '^[0-9a-f]{40}$') { throw 'invalid candidate ledger identity' }
$ledgerControllerBootstrap = [string]$candidateLedger.controller_path
if ([string]::IsNullOrWhiteSpace($ledgerControllerBootstrap) -or $ledgerControllerBootstrap -match '^[A-Za-z]:[^\\/]' -or $ledgerControllerBootstrap -match '^[\\/](?![\\/])' -or $ledgerControllerBootstrap.StartsWith('\\?\') -or $ledgerControllerBootstrap.StartsWith('\\.\') -or $ledgerControllerBootstrap.StartsWith('\??\') -or -not [System.IO.Path]::IsPathRooted($ledgerControllerBootstrap)) { throw 'invalid bootstrap controller path' }
if ([System.IO.Path]::GetFullPath($ledgerControllerBootstrap) -cne $ledgerControllerBootstrap) { throw 'non-canonical bootstrap controller path' }
$bootstrapWorktree = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $ledgerControllerBootstrap))
if ((git -C $bootstrapWorktree rev-parse HEAD).Trim().ToLowerInvariant() -cne $codeHead) { throw 'frozen worktree HEAD mismatch' }
if ((git -C $bootstrapWorktree config --get remote.origin.url).Trim() -cne 'https://github.com/XiaoyaoLinghao/stm32-toolkit.git') { throw 'origin repository mismatch' }
if (@(git -C $bootstrapWorktree status --porcelain=v1 --untracked-files=all).Count -ne 0) { throw 'frozen worktree is dirty' }

$pathContract = Join-Path $bootstrapWorktree 'tools\release\path_contract_0600.ps1'
$pathContractBlob = (git -C $bootstrapWorktree rev-parse "$codeHead`:tools/release/path_contract_0600.ps1").Trim()
$workingPathContractBlob = (git -C $bootstrapWorktree hash-object -- $pathContract).Trim()
if ($pathContractBlob -notmatch '^[0-9a-f]{40}$' -or $workingPathContractBlob -cne $pathContractBlob) { throw 'path contract is not committed at CodeHead' }
. $pathContract
$frozenWorktree = ConvertTo-CanonicalAbsolutePath -Path $bootstrapWorktree -Name 'frozen worktree'
$candidateRoot = ConvertTo-CanonicalAbsolutePath -Path $candidateRoot -Name 'candidate root'
$candidateLedgerPath = ConvertTo-CanonicalAbsolutePath -Path $candidateLedgerPath -Name 'candidate ledger'
$ledgerCandidateRoot = ConvertTo-CanonicalAbsolutePath -Path ([string]$candidateLedger.candidate_root) -Name 'ledger candidate root'
$ledgerEvidenceRoot = ConvertTo-CanonicalAbsolutePath -Path ([string]$candidateLedger.evidence_root) -Name 'ledger evidence root'
if ($ledgerCandidateRoot -cne $candidateRoot -or [System.IO.Path]::GetDirectoryName($ledgerEvidenceRoot) -cne $candidateRoot) { throw 'candidate root binding mismatch' }

$fixedPaths = [ordered]@{
  candidate_controller = 'tools/release/run_0600_candidate.ps1'
  release_verifier = 'tools/release/verify_0600_release.py'
  gate_catalog = 'tools/release/gates_0600.json'
  performance_catalog = 'tools/release/performance_0600.json'
}
$resolved = @{}
foreach ($name in $fixedPaths.Keys) {
  $relative = $fixedPaths[$name]
  $absolute = ConvertTo-CanonicalAbsolutePath -Path (Join-Path $frozenWorktree ($relative -replace '/', '\')) -Name $name
  $committedBlob = (git -C $frozenWorktree rev-parse "$codeHead`:$relative").Trim()
  $workingBlob = (git -C $frozenWorktree hash-object -- $absolute).Trim()
  if ($committedBlob -notmatch '^[0-9a-f]{40}$' -or $workingBlob -cne $committedBlob) { throw "$name bytes differ from CodeHead" }
  $resolved[$name] = $absolute
}
$ledgerController = ConvertTo-CanonicalAbsolutePath -Path ([string]$candidateLedger.controller_path) -Name 'ledger controller'
if ($ledgerController -cne $resolved.candidate_controller) { throw 'ledger controller is not the fixed controller path' }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $resolved.gate_catalog).Hash.ToLowerInvariant() -cne [string]$candidateLedger.catalog_sha256) { throw 'catalog digest mismatch' }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $resolved.performance_catalog).Hash.ToLowerInvariant() -cne [string]$candidateLedger.performance_sha256) { throw 'performance digest mismatch' }
$supportProfile = ConvertTo-CanonicalAbsolutePath -Path 'C:\tmp\stm32tk-0600-support\feasibility\profile.json' -Name 'support profile'
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $supportProfile).Hash.ToLowerInvariant() -cne [string]$candidateLedger.support_profile_sha256) { throw 'support profile digest mismatch' }
py -3.12 $resolved.release_verifier candidate-evidence --module STM32TK-0601 --candidate-run-id $candidateRunId --evidence $candidateRoot --expected-code-head $codeHead --catalog $resolved.gate_catalog --performance $resolved.performance_catalog --support-profile $supportProfile
```

  Create the report-only child only after reconciliation PASS, recording accepted base, product
  CodeHead, `candidateRunId`, per-gate owner/platform/tool/command/result, coverage/performance,
  recovery attempts if any, local evidence paths/bytes/SHA-256, deferred hardware gate inventory,
  and `SOFTWARE_COMPLETE_HARDWARE_PENDING`, but not the report's own SHA.

- [ ] Verify the staged report is the sole change, then commit locally:

```powershell
git diff --check
git diff --name-only
git add docs/codex/returns/STM32TK-0601-TEST-EVIDENCE/implementation-report.md
git diff --cached --name-only
git commit -m "docs(STM32TK-0601): record accepted test evidence CodeHead"
```

Expected: the report commit has exactly one changed path and becomes 0602's software accepted base.
It is not final `v0.6.0` acceptance; that remains hardware-pending. Stop;
do not push, open/merge a PR, tag, or delete branches without separate user authorization.

## Deferred hardware execution ownership

0601 ends after implementing and self-testing `tools/release/run_0600_hardware.ps1`; it does not
duplicate or execute the unified hardware orchestration. The sole normative execution sequence,
exact worktree/ledger resolution, per-action authorization loop, recovery handling, dual-CodeHead
reconciliation, and final acceptance transition are owned by
`docs/superpowers/plans/2026-08-14-stm32tk-0600-release-acceptance.md` Tasks 2--5. Implementers must
use that sequence verbatim after the 0603 Candidate. This 0601 plan defines only the runner and its
contract tests and cannot override, abbreviate, or substitute for the 0600 release plan.
