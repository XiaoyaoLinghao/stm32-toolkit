# STM32TK-1001 H2 Build-to-Flash Contract Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the public flash workflow consume genuine unchanged public-build
evidence while preserving the accepted-base rich-evidence behavior and every
identity-before-program safety gate.

**Architecture:** Change only the flash evidence consumer. Dispatch schema-v1
success records by their exact stage into either the canonical public-build
path-only dialect or the accepted-base rich ELF/MAP dialect; both converge on the
same identity, Git, input, disk-hash, ELF, segment, target, programming, readback,
and publication checks. Do not rewrite producer output or add another evidence
normalizer.

**Tech Stack:** CPython `>=3.12,<3.13`, pytest, pyelftools, existing STM32 Toolkit
build identity and flash modules, Git, Windows PowerShell.

**Design:**
`docs/superpowers/specs/2026-08-27-stm32-toolkit-1001-h2-build-flash-contract-correction-design.md`

**Accepted slice base:**
`8149273677716840406987e342da1ccbd62969d3`, tree
`a3089b5971ad0c33252118f25f19e730577bf418`.

**Approved specification head:**
`3fc1e9033bd9415d5b9c854fb3560e518cebf31a`, tree
`63459c50ca3b97c400ed45ce7deed2979aacfc1f`.

## Global Constraints

- One `gpt-5.6-luna` implementer at reasoning effort `max` owns all product code,
  implementation tests, commits, and implementation evidence for this correction.
- A `gpt-5.6-sol` reviewer independently reviews the complete accepted-base to
  code-head diff and is the only actor that can accept the product candidate.
- The only permitted product file is
  `tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py`.
- The only permitted implementation-test file is
  `tools/stm32-toolkit/tests/test_flash.py`.
- `build/runner.py`, schemas, project model, CLI, MCP, service, backend, package,
  dependencies, runtime, campaign project, and hardware bytes must not change.
- Preserve the accepted-base `stage="complete"` rich ELF/MAP dialect and all
  adjacent authorization, stale-evidence, identity, ordering, readback, atomic
  publication, error-code, message, and details behavior.
- Accept the canonical producer dialect only as `status="success"`, `stage=""`,
  `code="OK"`, with exactly five unique path-only artifact records matching the
  public build log, result, debug identity, model-selected ELF, and MAP paths.
- Artifact path records are consistency evidence only. The validated identity,
  current Git/input snapshot, regular contained disk bytes and recomputed hashes
  remain authoritative.
- Use CPython 3.12, `-p no:cacheprovider`, and exact external run-owned basetemps.
- Do not run a full repository suite, packaging matrix, install, network, remote
  Git action, target attach, flash, target read, reset, Monitor, Fault, or other
  hardware operation in this correction.
- Commit RED tests first. Commit the minimal GREEN product change second. Commit
  the implementation report separately after code/tests. Never amend or squash
  these boundaries, and do not self-accept.
- After each test run, retain the minimum necessary failure evidence, inspect the
  exact basetemp, and remove only that run-owned disposable path. Preserve and
  report an exact path when host permissions prevent cleanup.

---

### Task 1: Prove the genuine public build-to-flash RED

**Files:**

- Modify: `tools/stm32-toolkit/tests/test_flash.py:12-27`
- Modify: `tools/stm32-toolkit/tests/test_flash.py:192-203`
- Modify: `tools/stm32-toolkit/tests/test_flash.py:698-741`

**Interfaces:**

- Consumes: `run_build(BuildRequest) -> OperationResult[BuildReport]`, the
  existing test helpers `prepare_project()` and `install_fake_cmake()`,
  `flash_firmware(FlashRequest, client)`, and `RecordingFlashClient`.
- Produces: one deterministic public-build fixture helper and three final-behavior
  tests that are RED at the accepted base without touching real CMake, GitHub, or
  hardware.

- [ ] **Step 1: Add the genuine public-build test imports**

Change the imports to include the public build API and existing deterministic
fake-CMake installer. Do not copy or modify the build runner fixture:

```python
from collections.abc import Callable

from stm32_toolkit.build import BuildRequest, run_build
from test_build_runner import (
    build_elf_bytes,
    build_map_text,
    install_fake_cmake,
    prepare_project,
)
```

- [ ] **Step 2: Add a helper that returns unchanged genuine producer evidence**

Place this helper after `_request`. It must assert the exact producer bytes before
calling flash and must not call `build_result_document()`:

```python
def _run_public_debug_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, dict[str, object]]:
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    built = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert built.ok is True, built

    identity = json.loads(
        (root / "build" / "arm-debug" / "firmware-identity.json").read_text(
            encoding="utf-8"
        )
    )
    result = json.loads(
        (root / "artifacts" / "migration" / "build-result.json").read_text(
            encoding="utf-8"
        )
    )
    assert result["status"] == "success"
    assert result["stage"] == ""
    assert result["code"] == "OK"
    assert result["artifacts"] == [
        {"path": "artifacts/migration/build.log"},
        {"path": "artifacts/migration/build-result.json"},
        {"path": "build/arm-debug/firmware-identity.json"},
        {"path": "build/arm-debug/firmware.elf"},
        {"path": "build/arm-debug/firmware.map"},
    ]
    return root, identity
```

- [ ] **Step 3: Add the RED success-path regression**

The fake build ELF intentionally has no program header. Patch only the existing
test seam that converts already validated ELF bytes into load segments; do not
patch identity, disk hashes, attachment validation, programming, or readback:

```python
def test_public_run_build_output_flashes_without_rewriting_build_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, identity = _run_public_debug_build(tmp_path, monkeypatch)
    build_result_path = root / "artifacts" / "migration" / "build-result.json"
    identity_path = root / "build" / "arm-debug" / "firmware-identity.json"
    build_result_before = build_result_path.read_bytes()
    identity_before = identity_path.read_bytes()
    payload = b"\x00\xbf\x00\xbf"
    monkeypatch.setattr(
        flash_mod,
        "_flash_segments",
        lambda _data, _model, _rel: (
            flash_mod.FlashSegment(0x08000000, payload),
        ),
    )
    client = RecordingFlashClient(payload)

    outcome = asyncio.run(flash_firmware(_request(root, identity), client))

    assert outcome.ok is True, outcome
    assert [event[0] for event in client.events] == ["attach", "program", "read"]
    assert build_result_path.read_bytes() == build_result_before
    assert identity_path.read_bytes() == identity_before
```

- [ ] **Step 4: Add the RED identity-before-program regression**

Reuse the genuine public build and the same bounded segment seam. The wrong part
may attach, but it must not program or read:

```python
def test_public_run_build_output_rejects_connected_target_before_program(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, identity = _run_public_debug_build(tmp_path, monkeypatch)
    monkeypatch.setattr(
        flash_mod,
        "_flash_segments",
        lambda _data, _model, _rel: (
            flash_mod.FlashSegment(0x08000000, b"\x00\xbf"),
        ),
    )
    client = RecordingFlashClient(b"\x00\xbf", resolved_target="STM32F429ZG")

    outcome = asyncio.run(flash_firmware(_request(root, identity), client))

    assert outcome.ok is False
    assert outcome.code == "FIRMWARE_IDENTITY_MISMATCH"
    assert outcome.details == {"field": "connectedTarget", "rule": "identity"}
    assert [event[0] for event in client.events] == ["attach"]
```

- [ ] **Step 5: Add the RED canonical artifact fail-closed regression**

Parameterize shape and path conflicts. Every variant must fail before attach:

```python
@pytest.mark.parametrize(
    "mutation, expected_code, expected_details",
    [
        (
            lambda items: items.pop(),
            "FIRMWARE_EVIDENCE_INVALID",
            {"path": "artifacts/migration/build-result.json", "rule": "artifacts"},
        ),
        (
            lambda items: items.__setitem__(1, dict(items[0])),
            "FIRMWARE_EVIDENCE_INVALID",
            {"path": "artifacts/migration/build-result.json", "rule": "artifacts"},
        ),
        (
            lambda items: items[3].__setitem__("kind", "elf"),
            "FIRMWARE_EVIDENCE_INVALID",
            {"path": "artifacts/migration/build-result.json", "rule": "artifacts"},
        ),
        (
            lambda items: items[3].__setitem__("path", "C:/outside/firmware.elf"),
            "FIRMWARE_IDENTITY_MISMATCH",
            {"field": "artifacts", "rule": "identity"},
        ),
    ],
)
def test_public_run_build_output_rejects_artifact_tampering_before_attach(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: Callable[[list[dict[str, object]]], object],
    expected_code: str,
    expected_details: dict[str, str],
) -> None:
    root, identity = _run_public_debug_build(tmp_path, monkeypatch)
    path = root / "artifacts" / "migration" / "build-result.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    mutation(document["artifacts"])  # type: ignore[operator]
    atomic_write_json(path, document)
    client = RecordingFlashClient(b"")

    outcome = asyncio.run(flash_firmware(_request(root, identity), client))

    assert outcome.ok is False
    assert outcome.code == expected_code
    assert outcome.details == expected_details
    assert client.events == []
```

- [ ] **Step 6: Add explicit cross-dialect and arbitrary-stage rejection**

The rich accepted-base fixture must not become valid under the canonical empty
stage, and path-only producer evidence must not become valid under the rich
`complete` stage:

```python
def test_flash_rejects_cross_dialect_and_arbitrary_stage_before_attach(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rich_root = prepare_project(tmp_path, name="rich-project")
    rich_identity = _publish_current_debug_build(rich_root)
    rich_path = rich_root / "artifacts" / "migration" / "build-result.json"
    rich_document = json.loads(rich_path.read_text(encoding="utf-8"))
    rich_document["stage"] = ""
    atomic_write_json(rich_path, rich_document)
    rich_client = RecordingFlashClient(b"")
    rich_outcome = asyncio.run(
        flash_firmware(_request(rich_root, rich_identity), rich_client)
    )
    assert rich_outcome.code == "FIRMWARE_EVIDENCE_INVALID"
    assert rich_outcome.details == {
        "path": "artifacts/migration/build-result.json",
        "rule": "artifacts",
    }
    assert rich_client.events == []

    public_root, public_identity = _run_public_debug_build(tmp_path, monkeypatch)
    public_path = public_root / "artifacts" / "migration" / "build-result.json"
    public_document = json.loads(public_path.read_text(encoding="utf-8"))
    public_document["stage"] = "complete"
    atomic_write_json(public_path, public_document)
    public_client = RecordingFlashClient(b"")
    public_outcome = asyncio.run(
        flash_firmware(_request(public_root, public_identity), public_client)
    )
    assert public_outcome.code == "FIRMWARE_EVIDENCE_INVALID"
    assert public_outcome.details == {
        "path": "artifacts/migration/build-result.json",
        "rule": "artifacts",
    }
    assert public_client.events == []

    public_document["stage"] = "complete-later"
    atomic_write_json(public_path, public_document)
    arbitrary = asyncio.run(
        flash_firmware(_request(public_root, public_identity), public_client)
    )
    assert arbitrary.code == "FIRMWARE_BUILD_REQUIRED"
    assert arbitrary.details == {
        "path": "artifacts/migration/build-result.json",
        "rule": "status",
    }
    assert public_client.events == []
```

- [ ] **Step 7: Run only the new nodes and record the exact RED**

Use a new exact external basetemp:

```powershell
$env:PYTHONPATH = ((Resolve-Path '.\tools\stm32-toolkit\src').Path + ';' + (Resolve-Path '.\tools\stm32-toolkit\tests').Path)
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest `
  tools/stm32-toolkit/tests/test_flash.py `
  -q -p no:cacheprovider `
  --basetemp=C:/tmp/stm32tk-1001-h2-build-flash-red `
  -k 'public_run_build_output or cross_dialect'
```

Expected at the accepted base: the canonical success, connected-target, canonical
tamper, and rich-under-empty-stage assertions fail because the consumer rejects
the empty stage before dialect dispatch. The already-fail-closed
path-only-under-`complete` and arbitrary-stage assertions may pass. Record the
exact selected, passed, failed, and exit counts plus the first mismatch.

- [ ] **Step 8: Inspect and clean only the RED basetemp**

```powershell
$runRoot = 'C:\tmp\stm32tk-1001-h2-build-flash-red'
$resolvedRunRoot = (Resolve-Path -LiteralPath $runRoot).Path
if ($resolvedRunRoot -ne $runRoot) { throw "unexpected RED basetemp: $resolvedRunRoot" }
Get-ChildItem -LiteralPath $resolvedRunRoot -Force
Remove-Item -LiteralPath $resolvedRunRoot -Recurse -Force
```

If deletion fails, preserve the exact path and error as `ENVIRONMENT/cleanup-policy`.
Do not touch any other `C:\tmp` directory.

- [ ] **Step 9: Commit the RED tests only**

```powershell
git diff --check
git diff --name-only
git add -- tools/stm32-toolkit/tests/test_flash.py
git commit -m "test: expose public build flash contract gap"
```

The name-only output must be exactly `tools/stm32-toolkit/tests/test_flash.py`.
Do not amend this commit after GREEN.

---

### Task 2: Add bounded consumer dialect dispatch

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py:40-67`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py:268-278`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py:320-408`

**Interfaces:**

- Consumes: the exact schema-v1 build result, validated identity document,
  `model_artifact_paths(model, "arm-debug")`, `_artifact_record()`, and `_fail()`.
- Produces: `_public_artifact_paths(result) -> tuple[str, ...]` and an internal
  exact-stage dispatch in `_load_fresh_firmware()`; public signatures and result
  envelopes remain unchanged.

- [ ] **Step 1: Add the canonical build-log path constant**

Add beside `_IDENTITY_REL` and `_RESULT_REL`:

```python
_BUILD_LOG_REL = "artifacts/migration/build.log"
```

- [ ] **Step 2: Add a strict path-only artifact parser without changing the rich parser**

Place the new helper immediately before `_artifact_record`. Keep
`_artifact_record()` byte-identical:

```python
def _public_artifact_paths(result: Mapping[str, object]) -> tuple[str, ...]:
    artifacts = result.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 5:
        raise _fail(
            "FIRMWARE_EVIDENCE_INVALID",
            "Firmware evidence is invalid",
            path=_RESULT_REL,
            rule="artifacts",
        )
    paths: list[str] = []
    for item in artifacts:
        if (
            not isinstance(item, dict)
            or set(item) != {"path"}
            or not isinstance(item.get("path"), str)
        ):
            raise _fail(
                "FIRMWARE_EVIDENCE_INVALID",
                "Firmware evidence is invalid",
                path=_RESULT_REL,
                rule="artifacts",
            )
        paths.append(item["path"])
    if len(set(paths)) != len(paths):
        raise _fail(
            "FIRMWARE_EVIDENCE_INVALID",
            "Firmware evidence is invalid",
            path=_RESULT_REL,
            rule="artifacts",
        )
    return tuple(paths)
```

- [ ] **Step 3: Dispatch only the two accepted stages**

Replace the current success-stage check with exact stage capture. Parse canonical
path-only shape early, but do not yet trust its paths:

```python
stage = result.get("stage")
if (
    result.get("status") != "success"
    or stage not in ("", "complete")
    or result.get("code") != "OK"
):
    raise _fail(
        "FIRMWARE_BUILD_REQUIRED",
        "A current successful debug build is required",
        path=_RESULT_REL,
        rule="status",
    )
public_artifact_paths = _public_artifact_paths(result) if stage == "" else None
```

Do not accept `None`, whitespace, case variants, arbitrary strings, or numeric
stage values.

- [ ] **Step 4: Validate canonical paths or preserve the rich branch**

After `expected_elf_rel`, `expected_map_rel`, identity path comparison, and disk
hash checks, replace the unconditional rich validation with exact dialect
branches:

```python
if public_artifact_paths is not None:
    expected_artifact_paths = {
        _BUILD_LOG_REL,
        _RESULT_REL,
        _IDENTITY_REL,
        str(elf_rel),
        map_rel,
    }
    if set(public_artifact_paths) != expected_artifact_paths:
        raise _fail(
            "FIRMWARE_IDENTITY_MISMATCH",
            "Build artifacts disagree with firmware identity",
            field="artifacts",
            rule="identity",
        )
else:
    elf_record = _artifact_record(result, "elf")
    map_record = _artifact_record(result, "map")
    if (
        elf_record.get("path") != elf_rel
        or elf_record.get("sha256") != identity.get("elfSha256")
        or elf_record.get("size") != len(elf_data)
        or map_record.get("path") != map_rel
        or map_record.get("sha256") != identity.get("mapSha256")
        or map_record.get("size") != len(map_data)
    ):
        raise _fail(
            "FIRMWARE_IDENTITY_MISMATCH",
            "Build artifacts disagree with firmware identity",
            field="artifacts",
            rule="identity",
        )
```

Keep all code before and after this dialect branch unchanged. In particular,
`validate_elf`, second ELF hash comparison, ELF structural identity checks,
`_flash_segments`, caller pins, attach, `_validate_attachment`, program, readback,
freshness revalidation, and atomic success publication must remain in their
accepted order.

- [ ] **Step 5: Run the new GREEN nodes**

```powershell
$env:PYTHONPATH = ((Resolve-Path '.\tools\stm32-toolkit\src').Path + ';' + (Resolve-Path '.\tools\stm32-toolkit\tests').Path)
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest `
  tools/stm32-toolkit/tests/test_flash.py `
  -q -p no:cacheprovider `
  --basetemp=C:/tmp/stm32tk-1001-h2-build-flash-green-target `
  -k 'public_run_build_output or cross_dialect'
```

Expected: every selected node passes, including all artifact-tamper parameter
cases. Record exact selected/passed counts and exit code.

- [ ] **Step 6: Run the complete risk-triggered regression set**

```powershell
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest `
  tools/stm32-toolkit/tests/test_flash.py `
  tools/stm32-toolkit/tests/test_build_runner.py `
  tools/stm32-toolkit/tests/test_debug_read.py `
  -q -p no:cacheprovider `
  --basetemp=C:/tmp/stm32tk-1001-h2-build-flash-green-focused
```

Expected: exit `0`; all selected tests pass. This set is justified because it
covers the changed consumer, the exact producer contract, and the direct rich
dialect/debug-read consumer. Do not expand to the full suite without a newly
classified product risk.

- [ ] **Step 7: Inspect and clean both GREEN basetemps**

For each exact path
`C:\tmp\stm32tk-1001-h2-build-flash-green-target` and
`C:\tmp\stm32tk-1001-h2-build-flash-green-focused`, repeat the resolve, exact
equality, inspection, and `Remove-Item -LiteralPath ... -Recurse -Force` procedure
from Task 1. Preserve and report only exact cleanup failures.

- [ ] **Step 8: Audit scope before committing GREEN**

```powershell
git diff --check
git diff --name-only HEAD^..HEAD
git diff --name-only
git diff -- tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py
```

The uncommitted name-only output must be exactly
`tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py`. The RED commit must still
contain exactly `tools/stm32-toolkit/tests/test_flash.py`. Stop on any product or
test path outside the two approved files.

- [ ] **Step 9: Commit the minimal GREEN product change**

```powershell
git add -- tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py
git commit -m "fix: accept public build evidence for flash"
```

Do not amend the RED commit. Record the full GREEN SHA/tree and the exact
accepted-base-to-GREEN name-status list.

---

### Task 3: Produce the separate implementation report without accepting the diff

**Files:**

- Create:
  `docs/codex/returns/2026-08-27-stm32-toolkit-1001-h2-build-flash-contract-correction-implementation-report.md`

**Interfaces:**

- Consumes: accepted base, specification/plan heads, RED/GREEN commits, exact test
  outputs, cleanup results, and final code-head tree/status.
- Produces: an implementation-only evidence ledger. It does not contain its own
  report commit SHA and does not issue a Sol verdict.

- [ ] **Step 1: Reconstruct the exact implementation ledger**

Run and record the literal output of:

```powershell
git status --short --branch
git rev-parse HEAD
git rev-parse 'HEAD^{tree}'
git log --format='%H %T %s' --reverse 3fc1e9033bd9415d5b9c854fb3560e518cebf31a..HEAD
git diff --check 8149273677716840406987e342da1ccbd62969d3..HEAD
git diff --name-status 8149273677716840406987e342da1ccbd62969d3..HEAD
git remote -v
```

Identify the exact RED and GREEN SHAs from commit contents, not commit subjects
alone.

- [ ] **Step 2: Write the implementation report**

The report must state all of the following explicitly:

```markdown
# STM32TK-1001 H2 Build-to-Flash Contract Correction Implementation Report

- Accepted slice base: 8149273677716840406987e342da1ccbd62969d3
- Approved spec head: 3fc1e9033bd9415d5b9c854fb3560e518cebf31a
- Code/tests head before this report: copy the exact Step 1 `git rev-parse HEAD`
  output.
- Code/tests tree: copy the exact Step 1 `git rev-parse 'HEAD^{tree}'` output.
- Implementer: gpt-5.6-luna / max
- Reviewer/acceptance owner: gpt-5.6-sol
- Implementer verdict: RETURNED_FOR_INDEPENDENT_REVIEW

## TDD lineage

- RED commit: copy the exact full RED SHA; include selected count, failures, exit code, and first
  FIRMWARE_BUILD_REQUIRED mismatch.
- GREEN commit: copy the exact full GREEN SHA; include targeted and focused counts, exits, and commands.

## Product boundary

- Product file changed: probe/flash.py only.
- Test file changed: test_flash.py only.
- build runner, schemas, CLI/MCP, service/backend, runtime, project, hardware,
  network, and remotes unchanged.

## Safety result

- Genuine public build evidence is consumed without rewriting.
- Wrong connected target attaches only and performs zero programming/readback.
- No physical hardware command was run for this correction.

## Cleanup

- List every exact basetemp removed.
- List each exact residual and classified error if deletion failed.
```

Copy every dynamic value from the exact Step 1 output before staging. Do not claim
`ACCEPTED`, hardware PASS, runtime installation, or second-flash authorization.

- [ ] **Step 3: Validate and commit only the report**

```powershell
git diff --check
git diff --name-only
git add -- docs/codex/returns/2026-08-27-stm32-toolkit-1001-h2-build-flash-contract-correction-implementation-report.md
git diff --cached --check
git diff --cached --name-only
git commit -m "docs: report H2 build flash correction"
```

Before commit, the staged name-only output must be exactly the report path. The
report records the GREEN code head, never its own future commit SHA.

- [ ] **Step 4: Return to Sol and stop**

Return the report commit, GREEN code head/tree, RED/GREEN lineage, exact tests,
status/remotes, and cleanup facts. Do not install runtime, attach, flash, push,
create or mutate a PR, merge, tag, release, or self-accept.

---

### Task 4: Sol independent complete-diff review and verdict

**Files:**

- Review:
  `tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py`
- Review:
  `tools/stm32-toolkit/tests/test_flash.py`
- Review:
  `docs/superpowers/specs/2026-08-27-stm32-toolkit-1001-h2-build-flash-contract-correction-design.md`
- Review:
  `docs/superpowers/plans/2026-08-27-stm32-toolkit-1001-h2-build-flash-contract-correction.md`
- Review:
  `docs/codex/returns/2026-08-27-stm32-toolkit-1001-h2-build-flash-contract-correction-implementation-report.md`

**Interfaces:**

- Consumes: the exact returned report commit and separately identified GREEN
  code/tests head.
- Produces: one Sol verdict: `ACCEPTED`, `REVISION_REQUIRED`, or
  `REWRITE_REQUIRED`, with product/report/environment findings classified
  separately.

- [ ] **Step 1: Create an exact clean isolated review worktree**

Resolve the returned report commit, verify it is a commit, and create a detached
worktree under a fresh exact `C:\tmp\stm32tk-1001-h2-build-flash-review-*` path.
Verify detached HEAD, clean status, tree, and zero review-process hardware use.
Do not review the implementation worktree in place.

- [ ] **Step 2: Review the complete diff and frozen boundaries**

Resolve the GREEN code head as the parent of the report-only commit, verify it is
a commit, and run the diff against that exact value:

```powershell
$greenSha = git rev-parse HEAD^
git cat-file -e "$greenSha^{commit}"
git diff --check 8149273677716840406987e342da1ccbd62969d3..$greenSha
git diff --name-status 8149273677716840406987e342da1ccbd62969d3..$greenSha
git diff 8149273677716840406987e342da1ccbd62969d3..$greenSha -- `
  tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py `
  tools/stm32-toolkit/tests/test_flash.py
git diff --exit-code 8149273677716840406987e342da1ccbd62969d3..$greenSha -- `
  tools/stm32-toolkit/src/stm32_toolkit/build/runner.py
```

Require `$greenSha` to equal the full code/tests head recorded in the report. The
last command must exit `0`. Review every changed line, not only the report or last
commit.

- [ ] **Step 3: Independently verify the two dialects and safety ordering**

Confirm statically and dynamically:

- stage empty dispatches only to exact five-entry path-only parsing;
- stage complete retains the accepted rich parser and identity comparison;
- cross-dialect and arbitrary stage records fail closed;
- canonical paths never select disk artifacts or replace hashes;
- current identity/Git/input/disk/ELF/segment checks remain before attach;
- `_validate_attachment` remains before stale-success removal and programming;
- connected mismatch has attach only, with no program/read;
- success remains attach -> program -> readback -> disk revalidation -> atomic
  publication.

- [ ] **Step 4: Run the independent risk-triggered suite**

From the clean review worktree, with a fresh external basetemp:

```powershell
$env:PYTHONPATH = ((Resolve-Path '.\tools\stm32-toolkit\src').Path + ';' + (Resolve-Path '.\tools\stm32-toolkit\tests').Path)
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest `
  tools/stm32-toolkit/tests/test_flash.py `
  tools/stm32-toolkit/tests/test_build_runner.py `
  tools/stm32-toolkit/tests/test_debug_read.py `
  -q -p no:cacheprovider `
  --basetemp=C:/tmp/stm32tk-1001-h2-build-flash-sol-review
```

Record exact count, skips, exit, Python version, code head/tree, and command.
Classify failures before requesting any product change.

- [ ] **Step 5: Inspect and clean only Sol-owned review evidence**

Inspect and remove the exact Sol basetemp using the resolved-path equality guard.
After evidence is reconciled, remove only the exact detached review worktree using
`git worktree remove` with the literal exact review path; preserve and report any
permission failure.
Do not touch implementation evidence or shared/user caches.

- [ ] **Step 6: Issue the product verdict and stop at the runtime boundary**

Issue `ACCEPTED` only if the complete diff, both dialects, all safety ordering,
target suite, report accuracy, worktree status, and cleanup classification have no
unresolved product defect. A report-only defect does not erase valid product test
evidence but must be corrected in a separate report-only commit.

On `REVISION_REQUIRED`, return exact path/behavior/expected/evidence/command to
the same Luna/max implementer and do not patch as Sol. On acceptance, report that
runtime installation and another hardware flash remain separate pending actions;
do not begin either automatically.
