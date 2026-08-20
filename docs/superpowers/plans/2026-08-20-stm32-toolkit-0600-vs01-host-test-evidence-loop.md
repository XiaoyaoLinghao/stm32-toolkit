# STM32 Toolkit 0.6 VS-01 Host Test Evidence Loop Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** Deliver one runnable Host-test product loop in which a caller discovers Host cases, runs an exact frozen inventory, durably publishes the resulting `TestRun`, and queries that run authoritatively through both CLI and MCP.

**Architecture:** Keep `HostTestRunner` as the only CMake/CTest executor and the Evidence store/root records as the only durable authority. Add one pre-execution identity context that the runner binds to its discovered build/executable digests, one publication/query boundary for completed manifests, and thin application/CLI/MCP adapters. This plan intentionally excludes Target execution, diagnosis, Monitor, catalog/list/GC public commands, Python 3.10, release matrices, packaging, hardware, remote Git operations, and all VS-02+ work.

**Tech Stack:** CPython 3.12, frozen dataclasses, pytest, argparse, FastMCP, existing CMake/CTest process bridge, existing immutable Evidence store and GC root records.

## 0. Execution contract and scope

- Integration design base: `5ce2d31eb7c873f3a038480aba5ab50fe60d219f` on local branch `codex/STM32TK-0600-INTEGRATION-DESIGN`.
- Product candidate base: parent `c16538de810189272793f263197f4551a4538bae`; the design commit changes only governance/specification files.
- One implementation owner: a `gpt-5.6-luna` subagent with reasoning effort `max`, dispatched only after the user approves this plan.
- One reviewer/acceptor: the primary `gpt-5.6-sol` agent. Luna must not self-accept.
- The six tasks below are sequential implementation checkpoints inside one vertical slice, not independent work orders, nested task trees, or release Gates.
- Luna stops after each task with a local commit and a concise evidence note. Sol reviews the task diff before allowing the same Luna agent to continue.
- If a checkpoint needs more than the named product behavior or more than two additional production modules, stop and return to this plan/design. Do not recursively split or silently expand scope.
- No push, PR mutation, merge, close, remote branch operation, hardware operation, Python 3.10 run, release matrix, coverage gate, or package build is authorized.
- Existing Python 3.10 scripts/tests remain untouched unless a 3.12-only metadata assertion directly requires a narrow update; such a need must be reported before editing.

## 1. Public contract frozen by this plan

### Commands and MCP tools

```text
stm32-toolkit test discover --mode host --project-root PATH --data-root PATH --session-id ID
stm32-toolkit test run --mode host --inventory-digest SHA256 [--case CASE_ID ...] --project-root PATH --data-root PATH --session-id ID
stm32-toolkit test show RUN_ID --project-root PATH --data-root PATH --session-id ID

stm32_test_host_discover()
stm32_test_host_run(inventoryDigest, caseIds=[])
stm32_test_show(runId)
```

Each `test` leaf parser uses a new private `_add_testing_context()` helper with required `--project`/`--project-root`, `--data-root`, and `--session-id` plus optional `--json`; this matches the existing hardware context spelling without importing probe/authorization fields. MCP derives project/data/session context from its bound `ServerRuntime` and never accepts caller-supplied filesystem roots.

### Success shapes

```python
# discover data
{
    "inventory": TestInventory.to_dict(),
    "discovery_artifact": ArtifactRef.to_dict(),
}

# run data
{
    "run": {  # exactly nine fields
        "run_id": str,
        "mode": "host",
        "state": "passed" | "failed" | "error",
        "identity": EvidenceIdentity.to_dict(),
        "transport": None,
        "case_counts": {
            "passed": int, "failed": int, "skipped": int,
            "error": int, "timeout": int,
        },
        "started_at_utc": str,
        "ended_at_utc": str,
        "duration_ms": int,
    },
    "test_manifest": ArtifactRef.to_dict(),
    "evidence_id": str,
}

# show data
{
    **run_data,
    "authoritative": True,
}
```

All public operations return the existing `OperationResult` envelope. CLI JSON and MCP structured data must be projections of the same workflow result, not separately implemented semantics.

### Failure rules

- Missing Project v3 Host configuration: `PROJECT_TESTING_NOT_CONFIGURED`.
- Empty discovery: `TEST_NO_CASES`.
- Unknown selected case: `TEST_CASE_NOT_FOUND`.
- Caller digest differs from fresh discovery: `TEST_INVENTORY_CHANGED`.
- Build/executable/project/session identity contradiction: `TEST_IDENTITY_MISMATCH`.
- Malformed CTest protocol/JUnit/manifest: the existing stable `TEST_*` protocol code.
- Process timeout/execution failure: preserve the runner's stable `TEST_PROCESS_*` code; adapters do not parse exception text.
- Missing/corrupt/oversized authoritative evidence: preserve the typed `EVIDENCE_*` code.
- A failed test suite is a successful product operation whose `run.state == "failed"`; it is not converted into an adapter failure.
- A root-publication failure makes the operation fail. An envelope published before that failure is not reported as a successful run and remains GC-eligible.

## Task 1: Make Host discovery bind identity without caller foreknowledge

**Product behavior:** A public caller can supply stable workspace/project/session/source/Git facts; `HostTestRunner` alone derives and freezes Host build/executable digests during discovery. Existing callers that provide a fully bound `EvidenceIdentity` retain their fail-closed equality check.

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/evidence/model.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/evidence/__init__.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/testing/host.py`
- Test: `tools/stm32-toolkit/tests/test_evidence_model.py`
- Test: `tools/stm32-toolkit/tests/test_host_testing.py`

- [ ] **Step 1: Write RED model and runner tests**

Add tests proving that the context validates the same shared fields as `EvidenceIdentity`, binds only the runner-owned fields, and cannot bypass full-identity equality.

```python
context = EvidenceIdentityContext(
    workspace_id="a" * 64,
    project_id="12345678-1234-5678-1234-567812345678",
    session_id="session-1",
    target_device=host_target_device(),
    input_snapshot_sha256="b" * 64,
    git_commit="c" * 40,
    git_dirty=False,
)
identity = context.bind(build_id="d" * 64, elf_sha256="e" * 64)
assert identity.build_id == "d" * 64
assert identity.elf_sha256 == "e" * 64
```

```python
inventory = runner.discover(config, context)
assert inventory.identity.build_id == calculate_host_build_inventory_digest(...)
assert inventory.identity.elf_sha256 == calculate_host_test_executable_inventory_digest(...)

with pytest.raises(TestProtocolError, match="Host identity differs"):
    runner.discover(config, contradictory_full_identity)
```

- [ ] **Step 2: Run the focused RED tests**

```powershell
python -m pytest tools/stm32-toolkit/tests/test_evidence_model.py tools/stm32-toolkit/tests/test_host_testing.py -q
```

Expected: new tests fail because `EvidenceIdentityContext` and context-aware discovery do not exist.

- [ ] **Step 3: Implement the narrow identity seam**

Add the shared model, exporting it from `evidence.__init__`:

```python
@dataclass(frozen=True)
class EvidenceIdentityContext:
    workspace_id: str
    project_id: str
    session_id: str
    target_device: str
    input_snapshot_sha256: str
    git_commit: str
    git_dirty: bool

    def bind(self, *, build_id: str, elf_sha256: str) -> EvidenceIdentity:
        return EvidenceIdentity(
            workspace_id=self.workspace_id,
            project_id=self.project_id,
            session_id=self.session_id,
            build_id=build_id,
            elf_sha256=elf_sha256,
            target_device=self.target_device,
            input_snapshot_sha256=self.input_snapshot_sha256,
            git_commit=self.git_commit,
            git_dirty=self.git_dirty,
        )
```

Its `__post_init__` must validate every supplied field using the same closed validators as `EvidenceIdentity`; do not validate with fake/sentinel build hashes.

Change `HostTestRunner.discover` and `_discover_only` to accept `EvidenceIdentity | EvidenceIdentityContext`. `_discover_only` computes canonical Host hashes once and either calls `context.bind(...)` or `dataclasses.replace(...)`. `discover` performs the old exact-equality check only when the caller supplied a fully bound identity. `run()` continues to require the frozen full `EvidenceIdentity` contained in `TestInventory`.

- [ ] **Step 4: Run focused GREEN and existing Host regressions**

```powershell
python -m pytest tools/stm32-toolkit/tests/test_evidence_model.py tools/stm32-toolkit/tests/test_host_testing.py -q
```

- [ ] **Step 5: Self-review and commit**

Verify no sentinel hash, duplicate CTest parser, relaxed `validate_host_identity`, or Target behavior change exists.

```powershell
git diff --check
git diff -- tools/stm32-toolkit/src/stm32_toolkit/evidence tools/stm32-toolkit/src/stm32_toolkit/testing/host.py tools/stm32-toolkit/tests/test_evidence_model.py tools/stm32-toolkit/tests/test_host_testing.py
git add tools/stm32-toolkit/src/stm32_toolkit/evidence tools/stm32-toolkit/src/stm32_toolkit/testing/host.py tools/stm32-toolkit/tests/test_evidence_model.py tools/stm32-toolkit/tests/test_host_testing.py
git commit -m "feat(testing): bind host identity during discovery"
```

**Sol checkpoint:** Review this task diff for closed validation and backward compatibility. Do not run later-slice or release tests.

## Task 2: Add authoritative Evidence reads required by `test show`

**Product behavior:** Given an exact root ID or `ArtifactRef`, callers can retrieve verified authoritative bytes without catalog inference or private path access.

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/evidence/store.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/evidence/gc.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/evidence/__init__.py`
- Test: `tools/stm32-toolkit/tests/test_evidence_store.py`
- Test: `tools/stm32-toolkit/tests/test_evidence_gc.py`

- [ ] **Step 1: Write RED tests for exact verified reads**

```python
assert store.read_artifact(ref, maximum_bytes=1024) == payload
with pytest.raises(EvidenceValidationError) as failure:
    store.read_artifact(ref, maximum_bytes=len(payload) - 1)
assert failure.value.code == EVIDENCE_LIMIT_EXCEEDED
```

Cover digest/size mismatch, missing object, redirect/hardlink rejection, invalid maximum, and read-time mutation using existing store fault/test patterns.

```python
assert get_root(store, "test-run", "run-1") == root
```

Cover missing, non-canonical JSON, mismatched `root_type`/`root_id`, case-fold collision, and unsafe path. `get_root` must not create the Evidence root or any directory on a miss.

- [ ] **Step 2: Run focused RED**

```powershell
python -m pytest tools/stm32-toolkit/tests/test_evidence_store.py tools/stm32-toolkit/tests/test_evidence_gc.py -q
```

- [ ] **Step 3: Implement bounded, fail-closed public reads**

```python
def read_artifact(self, artifact: ArtifactRef, *, maximum_bytes: int) -> bytes:
    """Read exact immutable object bytes after path, size, and SHA-256 verification."""
```

Reuse existing safe-open/hash/path primitives. Read at most `maximum_bytes + 1`, reject before returning oversized content, and verify the exact `ArtifactRef.relative_path`, size, and digest. Never resolve a caller-computed arbitrary path.

```python
def get_root(
    store: EvidenceStore | Path | str,
    root_type: str,
    root_id: str,
) -> RootRecord:
    """Load one exact canonical root without creating store state."""
```

Reuse the same normalization and canonical JSON/root validation used by `put_root`; do not consult the catalog or scan for approximate matches.

- [ ] **Step 4: Run focused GREEN, self-review, and commit**

```powershell
python -m pytest tools/stm32-toolkit/tests/test_evidence_store.py tools/stm32-toolkit/tests/test_evidence_gc.py -q
git diff --check
git add tools/stm32-toolkit/src/stm32_toolkit/evidence tools/stm32-toolkit/tests/test_evidence_store.py tools/stm32-toolkit/tests/test_evidence_gc.py
git commit -m "feat(evidence): add authoritative root and artifact reads"
```

**Sol checkpoint:** Review only safety, no-write-on-read, bounds, canonical decoding, and exact reference verification.

## Task 3: Publish and reload one durable Host `TestRun`

**Product behavior:** A completed Host manifest becomes one immutable Evidence envelope plus one `test-run` root, and the same record can be authoritatively reloaded by run ID.

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/testing/model.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/testing/publication.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/testing/__init__.py`
- Test: `tools/stm32-toolkit/tests/test_testing_model.py`
- Create: `tools/stm32-toolkit/tests/test_testing_publication.py`

- [ ] **Step 1: Write RED canonical round-trip tests**

```python
payload = manifest.to_dict()
assert TestRunManifest.from_dict(payload) == manifest
assert canonical_json_bytes(TestRunManifest.from_dict(payload).to_dict()) == canonical_json_bytes(payload)
```

Reject extra/missing fields, tuple containers at the JSON boundary, malformed nested artifact/identity/case values, duplicate cases, contradictory terminal state, and non-canonical types.

- [ ] **Step 2: Write RED publication/query tests**

```python
published = publisher.publish_host(manifest, inventory_digest=inventory.inventory_digest)
assert published.data == {
    "run": expected_nine_field_summary,
    "test_manifest": published.manifest_artifact.to_dict(),
    "evidence_id": published.envelope.evidence_id,
}

loaded = repository.load(manifest.run_id)
assert loaded.data == {**published.data, "authoritative": True}
```

Assert exact envelope operation `host-test-run`, exact four Host artifacts (manifest, raw events, stdout, stderr) once each, exact envelope metadata (`test_run_id`, `test_manifest_sha256`, `inventory_digest`), and exact root metadata (`mode`, `state`). Assert publication stops on envelope/root conflict and query rejects root/envelope/artifact/run-ID/digest contradictions.

- [ ] **Step 3: Run focused RED**

```powershell
python -m pytest tools/stm32-toolkit/tests/test_testing_model.py tools/stm32-toolkit/tests/test_testing_publication.py -q
```

- [ ] **Step 4: Implement closed deserialization**

```python
@classmethod
def from_dict(cls, value: object) -> "TestCaseResult": ...

@classmethod
def from_dict(cls, value: object) -> "TestRunManifest": ...
```

Use exact key sets and existing `ArtifactRef.from_dict`/`EvidenceIdentity.from_dict`; instantiate the frozen dataclasses so all existing invariants run once. Do not weaken constructors.

- [ ] **Step 5: Implement publication and query boundaries**

```python
@dataclass(frozen=True)
class PublishedTestRun:
    manifest: TestRunManifest
    manifest_artifact: ArtifactRef
    envelope: EvidenceEnvelope
    root: RootRecord

    def public_data(self, *, authoritative: bool = False) -> dict[str, object]: ...

class TestRunPublisher:
    def publish_host(
        self, manifest: TestRunManifest, *, inventory_digest: str
    ) -> PublishedTestRun: ...

class TestRunRepository:
    def load(self, run_id: str) -> PublishedTestRun: ...
```

`TestRunPublisher` receives `EvidenceStore`, `project_root`, and an owned results root, and uses the existing `TestArtifactCollector` to write/ingest canonical manifest bytes. It never re-ingests runner artifacts. `TestRunRepository` uses `get_root`, `get_envelope`, and `read_artifact(maximum_bytes=67_108_864)` only.

- [ ] **Step 6: Run focused GREEN, self-review, and commit**

```powershell
python -m pytest tools/stm32-toolkit/tests/test_testing_model.py tools/stm32-toolkit/tests/test_testing_publication.py -q
git diff --check
git add tools/stm32-toolkit/src/stm32_toolkit/testing tools/stm32-toolkit/tests/test_testing_model.py tools/stm32-toolkit/tests/test_testing_publication.py
git commit -m "feat(testing): publish authoritative host test runs"
```

**Sol checkpoint:** Review exact artifact/root/envelope membership, crash/conflict behavior, canonical round-trip, and the nine-field public summary.

## Task 4: Compose the Host application workflow

**Product behavior:** One application service performs discover, fresh-digest-checked run, and authoritative show using Project v3 and managed workspace paths.

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/testing_workflows.py`
- Create: `tools/stm32-toolkit/tests/test_testing_workflows.py`

- [ ] **Step 1: Write RED workflow tests around injected runner seams**

```python
discover = host_test_discover(context)
assert discover.ok is True
assert discover.data == {
    "inventory": inventory.to_dict(),
    "discovery_artifact": discovery_ref.to_dict(),
}

run = host_test_run(context, inventory_digest=inventory.inventory_digest, case_ids=("fails",))
assert run.ok is True
assert run.data["run"]["state"] == "failed"

shown = test_show(context, run_id=run.data["run"]["run_id"])
assert shown.ok is True
assert shown.data == {**run.data, "authoritative": True}
```

Also prove: Schema v2 or absent Host config fails before runner construction; each run creates a fresh runner and rediscovers; digest mismatch fails before execution/publication; unknown cases do not publish; managed Evidence root is exactly `<data-root>/projects/<workspace-id>/evidence`; results live under the current session root; no project file is written; typed errors map without message parsing.

- [ ] **Step 2: Run focused RED**

```powershell
python -m pytest tools/stm32-toolkit/tests/test_testing_workflows.py -q
```

- [ ] **Step 3: Implement the application boundary**

```python
@dataclass(frozen=True)
class TestingWorkflowContext:
    project_root: Path
    data_root: Path
    session_id: str

def host_test_discover(context: TestingWorkflowContext) -> OperationResult: ...
def host_test_run(
    context: TestingWorkflowContext,
    *,
    inventory_digest: str,
    case_ids: tuple[str, ...],
) -> OperationResult: ...
def test_show(context: TestingWorkflowContext, *, run_id: str) -> OperationResult: ...
```

Internal context construction must:

```python
model = load_project_model(project_root)
if model.schema_version != 3 or model.testing is None or model.testing.host is None:
    return failure("PROJECT_TESTING_NOT_CONFIGURED", ...)
workspace = WorkspacePaths.from_roots(data_root, project_root, model.logical_project_id, session_id)
workspace.ensure()
snapshot = snapshot_project_inputs(model)
git = git_evidence(project_root)
identity_context = EvidenceIdentityContext(
    workspace_id=workspace.workspace_id,
    project_id=str(model.logical_project_id),
    session_id=workspace.session_id,
    target_device=host_target_device(),
    input_snapshot_sha256=snapshot.sha256,
    git_commit=git.head,
    git_dirty=git.dirty,
)
```

Use factories as private test seams for `HostTestRunner`, snapshot/Git readers, store, publisher, and repository. Do not expose a generic dependency-injection framework. All three public functions share one typed exception-to-`OperationResult` projection.

- [ ] **Step 4: Run focused GREEN and affected workflow regressions**

```powershell
python -m pytest tools/stm32-toolkit/tests/test_testing_workflows.py tools/stm32-toolkit/tests/test_host_testing.py tools/stm32-toolkit/tests/test_testing_publication.py -q
```

- [ ] **Step 5: Self-review and commit**

```powershell
git diff --check
git add tools/stm32-toolkit/src/stm32_toolkit/testing_workflows.py tools/stm32-toolkit/tests/test_testing_workflows.py
git commit -m "feat(testing): compose host test evidence workflow"
```

**Sol checkpoint:** Review the end-to-end data ownership, fresh-discovery ordering, failure side effects, and exact managed paths.

### Task 4 design correction: one public workspace identity

Implementation review exposed a retained-base mismatch: `WorkspacePaths.workspace_id` used the
historical 24-hex directory key, while `EvidenceIdentity.workspace_id` requires the complete
SHA-256. Do not bridge this inside `testing_workflows.py`. Before Task 4 is accepted:

- `compute_workspace_id()` returns the complete lowercase SHA-256;
- `WorkspacePaths.workspace_id` is that complete public identity;
- `WorkspacePaths.workspace_storage_key` is the first 24 hex characters and is used only to form
  `workspace_root`;
- existing directory layout remains `<data-root>/projects/<workspace_storage_key>`;
- all existing callers of `workspace.workspace_id` automatically converge on the complete public
  identity; and
- tests for identity, paths, context, hardware workflows, and Task 4 prove the distinction.

This is a bounded shared-contract correction discovered by the vertical slice, not a new Gate or a
new slice. Remove every local workspace-ID hashing helper from Task 4.

## Task 5: Expose the loop through the CLI

**Product behavior:** A user can discover, run a selected failing Host test, and show its authoritative record using stable JSON CLI commands.

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/cli.py`
- Create: `tools/stm32-toolkit/tests/test_testing_cli.py`

- [ ] **Step 1: Write RED grammar/projection tests**

```python
assert parse(["test", "discover", "--mode", "host", *context_args]).operation == "test.host.discover"
assert parse(["test", "run", "--mode", "host", "--inventory-digest", digest, "--case", "fails", *context_args]).case_ids == ("fails",)
assert parse(["test", "show", "run-1", *context_args]).run_id == "run-1"
```

Assert missing/invalid mode, digest, repeated duplicate cases, unknown flags, and Target mode are rejected without calling workflows. Assert stdout is one canonical JSON `OperationResult`; unexpected internal exceptions follow existing CLI stderr policy.

- [ ] **Step 2: Run focused RED**

```powershell
python -m pytest tools/stm32-toolkit/tests/test_testing_cli.py -q
```

- [ ] **Step 3: Add thin parser and dispatcher branches**

Add a private `_add_testing_context()` parser helper and use it on all three leaf parsers. The dispatcher branches construct `TestingWorkflowContext` and call exactly one of `host_test_discover`, `host_test_run`, or `test_show`. They do not load project files, run CTest, inspect Evidence paths, or remap domain codes.

```python
if args.command == "test" and args.test_command == "run":
    result = host_test_run(
        context,
        inventory_digest=args.inventory_digest,
        case_ids=tuple(args.case_ids),
    )
```

- [ ] **Step 4: Run focused GREEN plus existing CLI tests**

```powershell
python -m pytest tools/stm32-toolkit/tests/test_testing_cli.py tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_cli_hardware.py -q
```

- [ ] **Step 5: Self-review and commit**

```powershell
git diff --check
git add tools/stm32-toolkit/src/stm32_toolkit/cli.py tools/stm32-toolkit/tests/test_testing_cli.py
git commit -m "feat(cli): expose host test evidence loop"
```

**Sol checkpoint:** Review CLI grammar, one-call delegation, JSON/error parity, and absence of Target or Evidence-management commands.

## Task 6: Expose MCP parity and prove the runnable slice

**Product behavior:** MCP callers receive the same result shapes/codes as CLI, and one realistic failing Host run remains queryable from durable Evidence after the execution object is gone.

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`
- Create: `tools/stm32-toolkit/tests/test_testing_mcp.py`
- Modify: `tools/stm32-toolkit/tests/test_testing_workflows.py`
- Modify only if exact registered-tool counts require it: existing MCP schema/count tests that enumerate all tools.

- [ ] **Step 1: Write RED MCP schema/delegation/parity tests**

```python
schemas = {tool.name: tool.inputSchema for tool in asyncio.run(server.list_tools())}
assert set(TEST_TOOL_NAMES) <= set(schemas)
assert schemas["stm32_test_host_run"]["required"] == ["inventoryDigest"]
```

Assert exact schemas, `caseIds` default `[]`, closed unknown fields, root/capability checks on every call, one workflow invocation, and exact `OperationResult.to_dict()` parity with CLI/workflow projections. Update hard-coded total tool counts from 15 to 18 only where the test intentionally enumerates the complete server.

- [ ] **Step 2: Add the runnable scenario test before implementation**

The acceptance fixture uses a temporary Project v3 repository, existing fake process/CTest bridge patterns, two cases (`passes`, `fails`), and a real temporary Evidence store. It must prove:

```python
inventory = unwrap(host_test_discover(context))
result = unwrap(host_test_run(
    context,
    inventory_digest=inventory["inventory"]["inventory_digest"],
    case_ids=("fails",),
))
assert result["run"]["state"] == "failed"

del execution_runner
shown = unwrap(test_show(context, run_id=result["run"]["run_id"]))
assert shown == {**result, "authoritative": True}
assert project_tree_bytes_after == project_tree_bytes_before
```

Also mutate the caller digest and assert `TEST_INVENTORY_CHANGED` with no run envelope/root.

- [ ] **Step 3: Run focused RED**

```powershell
python -m pytest tools/stm32-toolkit/tests/test_testing_mcp.py tools/stm32-toolkit/tests/test_testing_workflows.py -q
```

- [ ] **Step 4: Implement three thin MCP tools**

```python
@server.tool(name="stm32_test_host_discover")
async def stm32_test_host_discover(ctx: Context) -> dict[str, object]: ...

@server.tool(name="stm32_test_host_run")
async def stm32_test_host_run(
    ctx: Context,
    inventoryDigest: str,
    caseIds: list[str] | None = None,
) -> dict[str, object]: ...

@server.tool(name="stm32_test_show")
async def stm32_test_show(ctx: Context, runId: str) -> dict[str, object]: ...
```

Add corresponding `tool_test_host_discover_for_request`, `tool_test_host_run_for_request`, and `tool_test_show_for_request` helpers beside the existing request wrappers. Each helper must run the existing per-call client-root/capability validation before invoking its Task 4 workflow. The registered tools delegate only to those helpers. Follow the existing `ServerRuntime` project binding, async dispatch, and cleanup patterns; do not create a second authorization path.

- [ ] **Step 5: Run slice-level verification (only the affected layer)**

```powershell
python -m pytest tools/stm32-toolkit/tests/test_evidence_model.py tools/stm32-toolkit/tests/test_evidence_store.py tools/stm32-toolkit/tests/test_evidence_gc.py tools/stm32-toolkit/tests/test_testing_model.py tools/stm32-toolkit/tests/test_host_testing.py tools/stm32-toolkit/tests/test_testing_publication.py tools/stm32-toolkit/tests/test_testing_workflows.py tools/stm32-toolkit/tests/test_testing_cli.py tools/stm32-toolkit/tests/test_testing_mcp.py tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_cli_hardware.py tools/stm32-toolkit/tests/test_mcp_server.py tools/stm32-toolkit/tests/test_mcp_hardware.py tools/stm32-toolkit/tests/test_mcp_roots.py -q
```

No Python 3.10, full repository matrix, coverage, package, browser, Node, Linux, or hardware run is part of slice verification.

- [ ] **Step 6: Self-review and commit**

```powershell
git diff --check
git add tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py tools/stm32-toolkit/tests/test_testing_mcp.py tools/stm32-toolkit/tests/test_testing_workflows.py
git add tools/stm32-toolkit/tests/test_mcp_server.py tools/stm32-toolkit/tests/test_mcp_hardware.py tools/stm32-toolkit/tests/test_mcp_roots.py
git commit -m "feat(mcp): expose host test evidence loop"
```

Only add an existing MCP test file if it actually changed for exact tool enumeration.

## 2. Sol final review and slice acceptance

After Luna finishes Task 6, Sol independently reviews the complete diff from `5ce2d31eb7c873f3a038480aba5ab50fe60d219f` to final HEAD, not only the last commit.

- [ ] Reconstruct the ownership/state ledger and verify one Luna implementation lineage, no untracked product files, no unapproved remote state, and no edits outside the plan.
- [ ] Read every changed production/test line and reconcile each public shape, failure code, state transition, identity field, authoritative source, and side effect with the 0.6 integration spec.
- [ ] Re-run Task 6 slice verification under CPython 3.12 from a clean isolated worktree at final HEAD.
- [ ] Run `git diff --check 5ce2d31eb7c873f3a038480aba5ab50fe60d219f..HEAD` and inspect `git diff --stat` plus the exact changed-path list.
- [ ] Confirm the runnable acceptance scenario completes `discover -> failed run -> durable show`, while wrong digest stops before execution/publication.
- [ ] Report findings as product, contract, implementation, validation-infrastructure, environment/platform, or report-only. A report-only issue does not invalidate correct product bytes.
- [ ] Mark VS-01 accepted only if no Critical/Important product or contract finding remains. Do not start VS-02 automatically.

## 3. Risk triggers that may widen verification

Widening requires one of these observed triggers and user-visible justification:

- Evidence store/root safety primitives changed beyond read-only methods: run the full Evidence unit group, but not release packaging.
- Host runner process/bridge logic changed beyond identity binding: run all Host/Target common protocol regressions; do not run hardware.
- Shared `OperationResult`, global CLI context, MCP root authorization, or server lifecycle changed: run the complete corresponding adapter suite.
- Package metadata/runtime declaration changed: run the CPython 3.12 package smoke test.
- Any platform-dependent path/lock change lacks coverage on the current platform: classify as platform evidence debt and request the relevant platform run; do not relabel it a product failure.
- Two consecutive attempts fail on the same interface contradiction: stop local patching and return to the integration design.

Absent a trigger, previously passed unaffected evidence stays valid and no release-level Gate is pulled into VS-01.

## 4. Completion handoff

The final handoff contains:

```text
VS-01 status
accepted design base and final local HEAD
complete changed-path list
three completed caller behaviors: discover, run/publish, authoritative show
slice test command and fresh counts
open product blockers, if any
validation/environment/report-only observations kept separate
remote authorization: none; no push/PR/merge performed
recommended next action: user decides whether to accept VS-01 and authorize VS-02 planning
```
