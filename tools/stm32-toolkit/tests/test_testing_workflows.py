from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID
import sys

import pytest

import stm32_toolkit.testing_workflows as workflows
from stm32_toolkit.build.model import BuildError
from stm32_toolkit.evidence import EvidenceValidationError
from stm32_toolkit.project_model import ProjectManifestError
from stm32_toolkit.testing.host import HostTestRunner
from stm32_toolkit.testing.model import TestProtocolError as ProtocolError


PROJECT_ID = UUID("12345678-1234-5678-1234-567812345678")
SNAPSHOT_SHA = "a" * 64
GIT_HEAD = "b" * 40


@dataclass(frozen=True)
class _FakeInventory:
    inventory_digest: str = "c" * 64
    case_ids: tuple[str, ...] = ("fails", "passes")

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": "host",
            "identity": {},
            "case_ids": list(self.case_ids),
            "inventory_digest": self.inventory_digest,
            "discovered_at_utc": "2026-08-20T00:00:00.000000Z",
        }


DISCOVERY = {
    "sha256": "d" * 64,
    "size_bytes": 4,
    "relative_path": "objects/sha256/dd/dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
    "kind": "test-discovery",
    "media_type": "application/json",
}


class _FakeManifest:
    run_id = "run-1"
    state = "failed"


class _FakePublished:
    def __init__(self) -> None:
        self.data = {
            "run": {"run_id": "run-1", "state": "failed"},
            "test_manifest": {"sha256": "e" * 64},
            "evidence_id": "f" * 64,
        }

    def public_data(self, *, authoritative: bool = False) -> dict[str, object]:
        result = dict(self.data)
        if authoritative:
            result["authoritative"] = True
        return result


def _model(project_root: Path, *, schema_version: int = 3, host: object = object()):
    testing = None if host is None else SimpleNamespace(host=host)
    return SimpleNamespace(
        project_root=project_root,
        schema_version=schema_version,
        logical_project_id=PROJECT_ID,
        testing=testing,
    )


def _install_context_seams(monkeypatch: pytest.MonkeyPatch, project_root: Path) -> None:
    monkeypatch.setattr(
        workflows,
        "_load_project_model",
        lambda _root: _model(project_root),
    )
    monkeypatch.setattr(
        workflows,
        "_snapshot_project_inputs",
        lambda _model: SimpleNamespace(sha256=SNAPSHOT_SHA),
    )
    monkeypatch.setattr(
        workflows,
        "_git_evidence",
        lambda _root: SimpleNamespace(head=GIT_HEAD, dirty=False),
    )


def _context(tmp_path: Path) -> workflows.TestingWorkflowContext:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / ".stm32-project.json").write_bytes(b"project-before")
    return workflows.TestingWorkflowContext(
        project_root=project_root,
        data_root=tmp_path / "data",
        session_id="session-1",
    )


def test_host_discover_run_and_show_compose_the_frozen_public_shapes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    context = _context(tmp_path)
    _install_context_seams(monkeypatch, context.project_root)
    inventory = _FakeInventory()
    runners: list[object] = []
    identities: list[object] = []

    class Runner:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs
            self.discovery_artifact = SimpleNamespace(to_dict=lambda: DISCOVERY)
            self.calls: list[str] = []
            runners.append(self)

        def discover(self, config: object, identity: object) -> _FakeInventory:
            self.calls.append("discover")
            identities.append(identity)
            return inventory

        def run(self, received: _FakeInventory, case_ids: tuple[str, ...]) -> _FakeManifest:
            self.calls.append("run")
            assert received is inventory
            assert case_ids == ("fails",)
            return _FakeManifest()

    stores: list[object] = []

    class Store:
        def __init__(self, root: Path) -> None:
            self.root = root
            stores.append(self)

    publishers: list[object] = []

    class Publisher:
        def __init__(self, store: object, project_root: Path, results_root: Path) -> None:
            self.store = store
            self.project_root = project_root
            self.results_root = results_root
            publishers.append(self)

        def publish_host(self, manifest: object, *, inventory_digest: str) -> _FakePublished:
            assert manifest.run_id == "run-1"
            assert inventory_digest == inventory.inventory_digest
            return _FakePublished()

    class Repository:
        def __init__(self, store: object) -> None:
            self.store = store

        def load(self, run_id: str) -> _FakePublished:
            assert run_id == "run-1"
            return _FakePublished()

    monkeypatch.setattr(workflows, "_host_runner_factory", Runner)
    monkeypatch.setattr(workflows, "_evidence_store_factory", Store)
    monkeypatch.setattr(workflows, "_publisher_factory", Publisher)
    monkeypatch.setattr(workflows, "_repository_factory", Repository)

    discovered = workflows.host_test_discover(context)
    assert discovered.ok is True
    assert discovered.operation == "test.host.discover"
    assert discovered.to_dict()["data"] == {
        "inventory": inventory.to_dict(),
        "discovery_artifact": DISCOVERY,
    }

    run = workflows.host_test_run(
        context,
        inventory_digest=inventory.inventory_digest,
        case_ids=("fails",),
    )
    assert run.ok is True
    assert run.operation == "test.host.run"
    assert run.to_dict()["data"]["run"]["state"] == "failed"

    shown = workflows.test_show(context, run_id="run-1")
    assert shown.ok is True
    assert shown.operation == "test.show"
    assert shown.to_dict()["data"] == {**run.to_dict()["data"], "authoritative": True}
    assert len(runners) == 2
    assert runners[0].calls == ["discover"]
    assert runners[1].calls == ["discover", "run"]
    assert identities[0].project_id == str(PROJECT_ID)
    workspace = workflows.WorkspacePaths.from_roots(
        context.data_root, context.project_root, PROJECT_ID, context.session_id
    )
    assert identities[0].workspace_id == workspace.workspace_id
    assert len(identities[0].workspace_id) == 64
    assert identities[0].session_id == context.session_id
    assert identities[0].input_snapshot_sha256 == SNAPSHOT_SHA
    assert identities[0].git_commit == GIT_HEAD
    assert identities[0].git_dirty is False

    assert stores[0].root == workspace.workspace_root / "evidence"
    assert publishers[0].results_root == workspace.session_root / "test-results"
    assert (context.project_root / ".stm32-project.json").read_bytes() == b"project-before"


@pytest.mark.parametrize(
    ("schema_version", "host"),
    [(2, object()), (3, None)],
)
def test_unconfigured_project_fails_before_runner_construction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    schema_version: int,
    host: object,
):
    context = _context(tmp_path)
    monkeypatch.setattr(
        workflows,
        "_load_project_model",
        lambda _root: _model(context.project_root, schema_version=schema_version, host=host),
    )
    calls: list[str] = []

    def runner(**kwargs: object) -> object:
        calls.append("runner")
        raise AssertionError("runner must not be constructed")

    monkeypatch.setattr(workflows, "_host_runner_factory", runner)

    result = workflows.host_test_discover(context)

    assert result.ok is False
    assert result.code == "PROJECT_TESTING_NOT_CONFIGURED"
    assert result.message == "Project testing is not configured."
    assert result.details == {}
    assert calls == []


def test_project_loading_failures_keep_their_existing_codes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    context = _context(tmp_path)

    monkeypatch.setattr(
        workflows,
        "_load_project_model",
        lambda _root: (_ for _ in ()).throw(OSError("project unavailable")),
    )
    unavailable = workflows.host_test_discover(context)
    assert unavailable.code == "PROJECT_NOT_CONFIGURED"
    assert unavailable.message == "Project is not configured."

    monkeypatch.setattr(
        workflows,
        "_load_project_model",
        lambda _root: (_ for _ in ()).throw(
            ProjectManifestError("PROJECT_JSON_INVALID", "invalid", {})
        ),
    )
    manifest_error = workflows.host_test_discover(context)
    assert manifest_error.code == "PROJECT_JSON_INVALID"
    assert manifest_error.message == "Project manifest JSON is invalid."


def test_run_rediscovers_and_digest_mismatch_has_no_execution_or_publication(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    context = _context(tmp_path)
    _install_context_seams(monkeypatch, context.project_root)
    expected = _FakeInventory()
    changed = _FakeInventory(inventory_digest="1" * 64)
    executed: list[str] = []

    class Runner:
        def __init__(self, **kwargs: object) -> None:
            self.discovery_artifact = SimpleNamespace(to_dict=lambda: DISCOVERY)

        def discover(self, config: object, identity: object) -> _FakeInventory:
            return changed

        def run(self, inventory: object, case_ids: tuple[str, ...]) -> _FakeManifest:
            executed.append("run")
            return _FakeManifest()

    published: list[str] = []

    class Publisher:
        def __init__(self, *args: object) -> None:
            pass

        def publish_host(self, *args: object, **kwargs: object) -> _FakePublished:
            published.append("publish")
            return _FakePublished()

    monkeypatch.setattr(workflows, "_host_runner_factory", Runner)
    monkeypatch.setattr(workflows, "_publisher_factory", Publisher)

    result = workflows.host_test_run(
        context,
        inventory_digest=expected.inventory_digest,
        case_ids=(),
    )

    assert result.ok is False
    assert result.code == "TEST_INVENTORY_CHANGED"
    assert result.message == "The test inventory changed."
    assert result.details == {}
    assert executed == []
    assert published == []


def test_unknown_cases_do_not_publish_and_typed_errors_use_fixed_projection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    context = _context(tmp_path)
    _install_context_seams(monkeypatch, context.project_root)
    inventory = _FakeInventory()
    published: list[str] = []

    class Runner:
        def __init__(self, **kwargs: object) -> None:
            self.discovery_artifact = SimpleNamespace(to_dict=lambda: DISCOVERY)

        def discover(self, config: object, identity: object) -> _FakeInventory:
            return inventory

        def run(self, inventory: object, case_ids: tuple[str, ...]) -> _FakeManifest:
            raise ProtocolError(
                "TEST_CASE_NOT_FOUND", r"secret C:\\Users\\victim\\private.txt"
            )

    class Publisher:
        def __init__(self, *args: object) -> None:
            pass

        def publish_host(self, *args: object, **kwargs: object) -> _FakePublished:
            published.append("publish")
            return _FakePublished()

    monkeypatch.setattr(workflows, "_host_runner_factory", Runner)
    monkeypatch.setattr(workflows, "_publisher_factory", Publisher)

    result = workflows.host_test_run(
        context,
        inventory_digest=inventory.inventory_digest,
        case_ids=("unknown",),
    )

    assert result.ok is False
    assert result.code == "TEST_CASE_NOT_FOUND"
    assert result.message == "A requested test case was not discovered."
    assert result.details == {}
    assert published == []

    class FailedRunner(Runner):
        def run(self, inventory: object, case_ids: tuple[str, ...]) -> _FakeManifest:
            raise ProtocolError("TEST_PROCESS_FAILED", "native output contains a secret path")

    monkeypatch.setattr(workflows, "_host_runner_factory", FailedRunner)
    result = workflows.host_test_run(
        context,
        inventory_digest=inventory.inventory_digest,
        case_ids=("fails",),
    )
    assert result.ok is False
    assert result.code == "TEST_EXECUTION_FAILED"
    assert result.message == "Test execution failed."
    assert result.details == {}

    class UnknownRunner(Runner):
        def run(self, inventory: object, case_ids: tuple[str, ...]) -> _FakeManifest:
            raise ProtocolError("TEST_UNKNOWN", r"secret C:\\Users\\victim\\private.txt")

    monkeypatch.setattr(workflows, "_host_runner_factory", UnknownRunner)
    with pytest.raises(RuntimeError):
        workflows.host_test_run(
            context,
            inventory_digest=inventory.inventory_digest,
            case_ids=("fails",),
        )


def test_evidence_typed_error_and_snapshot_error_do_not_leak_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    context = _context(tmp_path)
    _install_context_seams(monkeypatch, context.project_root)
    monkeypatch.setattr(
        workflows,
        "_snapshot_project_inputs",
        lambda _model: (_ for _ in ()).throw(
            BuildError("BUILD_INPUT_INVALID", r"secret C:\\Users\\victim\\project", {})
        ),
    )
    with pytest.raises(BuildError):
        workflows.host_test_discover(context)

    _install_context_seams(monkeypatch, context.project_root)

    class Runner:
        def __init__(self, **kwargs: object) -> None:
            self.discovery_artifact = SimpleNamespace(to_dict=lambda: DISCOVERY)

        def discover(self, config: object, identity: object) -> _FakeInventory:
            return _FakeInventory()

        def run(self, inventory: object, case_ids: tuple[str, ...]) -> _FakeManifest:
            return _FakeManifest()

    class Store:
        def __init__(self, root: Path) -> None:
            self.root = root

    class Publisher:
        def __init__(self, *args: object) -> None:
            pass

        def publish_host(self, *args: object, **kwargs: object) -> _FakePublished:
            raise EvidenceValidationError("EVIDENCE_CORRUPT", r"secret C:\\Users\\victim\\evidence")

    monkeypatch.setattr(workflows, "_host_runner_factory", Runner)
    monkeypatch.setattr(workflows, "_evidence_store_factory", Store)
    monkeypatch.setattr(workflows, "_publisher_factory", Publisher)
    result = workflows.host_test_run(
        context,
        inventory_digest=_FakeInventory().inventory_digest,
        case_ids=("fails",),
    )
    assert result.ok is False
    assert result.code == "EVIDENCE_CORRUPT"
    assert result.message == "Evidence is corrupt."
    assert result.details == {}


@pytest.mark.parametrize(
    "error_factory",
    [
        lambda: ValueError(r"secret C:\\Users\\victim\\publisher"),
        lambda: BuildError("BUILD_FAILED", r"secret C:\\Users\\victim\\publisher", {}),
    ],
)
def test_publisher_programming_errors_propagate_without_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    error_factory,
):
    context = _context(tmp_path)
    _install_context_seams(monkeypatch, context.project_root)

    class Runner:
        def __init__(self, **kwargs: object) -> None:
            self.discovery_artifact = SimpleNamespace(to_dict=lambda: DISCOVERY)

        def discover(self, config: object, identity: object) -> _FakeInventory:
            return _FakeInventory()

        def run(self, inventory: object, case_ids: tuple[str, ...]) -> _FakeManifest:
            return _FakeManifest()

    class Publisher:
        def __init__(self, *args: object) -> None:
            pass

        def publish_host(self, *args: object, **kwargs: object) -> _FakePublished:
            raise error_factory()

    monkeypatch.setattr(workflows, "_host_runner_factory", Runner)
    monkeypatch.setattr(workflows, "_publisher_factory", Publisher)

    with pytest.raises((ValueError, BuildError)):
        workflows.host_test_run(
            context,
            inventory_digest=_FakeInventory().inventory_digest,
            case_ids=("fails",),
        )


def test_show_uses_only_authoritative_repository_projection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    context = _context(tmp_path)
    _install_context_seams(monkeypatch, context.project_root)
    calls: list[str] = []

    class Store:
        def __init__(self, root: Path) -> None:
            calls.append("store")

    class Repository:
        def __init__(self, store: object) -> None:
            calls.append("repository")

        def load(self, run_id: str) -> _FakePublished:
            calls.append(f"load:{run_id}")
            return _FakePublished()

    def no_runner(**kwargs: object) -> object:
        raise AssertionError("show must not construct a HostTestRunner")

    monkeypatch.setattr(workflows, "_evidence_store_factory", Store)
    monkeypatch.setattr(workflows, "_repository_factory", Repository)
    monkeypatch.setattr(workflows, "_host_runner_factory", no_runner)

    result = workflows.test_show(context, run_id="run-1")

    assert result.ok is True
    assert result.data["authoritative"] is True
    assert calls == ["store", "repository", "load:run-1"]


def test_real_host_discover_failed_run_and_durable_show_use_bound_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """The MCP-facing workflow survives process objects being discarded."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    data_root = tmp_path / "data"
    context = workflows.TestingWorkflowContext(project_root, data_root, "session-real")

    manifest = {
        "schemaVersion": 3,
        "logicalProjectId": str(PROJECT_ID),
        "generatedBy": {"tool": "stm32-toolkit", "version": "0.6.0"},
        "project": {"name": "firmware", "origin": "manual"},
        "target": {"device": "STM32F429ZGTx", "core": "cortex-m4"},
        "framework": {"type": "spl", "version": None},
        "build": {
            "sources": ["App/main.c"], "includePaths": [], "defines": [],
            "compileOptions": [], "assemblySources": [], "presets": [],
            "elf": "build-fw/firmware.elf",
        },
        "memory": {"source": "manual", "regions": []},
        "debug": {"backend": "pyocd", "target": "stm32f429zgtx", "svd": None},
        "generation": {
            "cubeMxIoc": None,
            "managedManifest": ".stm32-toolkit/generated-files.json",
            "generatedDirectories": [],
            "userDirectories": [],
        },
        "testing": {
            "host": {
                "buildPreset": "host-build",
                "ctestPreset": "host-tests",
                "labels": [],
                "timeout_seconds": 30,
                "environment": {
                    "allow": ["SCENARIO_DIR", "JUNIT_SOURCE", "RESULTS_ROOT"],
                    "values": {},
                },
            },
            "target": {
                "executable": "build/test/firmware-tests.elf",
                "timeout_seconds": 120,
                "transport": {
                    "kind": "memory-mailbox",
                    "options": {"address": 0x20010000, "size": 4096},
                },
            },
        },
    }
    scenario = tmp_path / "scenario"
    scenario.mkdir()
    script = scenario / "fake-host-tool.py"
    script.write_text(
        r'''
import json
import os
from pathlib import Path
import sys

mode, *argv = sys.argv[1:]
if mode == "cmake":
    raise SystemExit(0)
if "--show-only=json-v1" in argv:
    print(json.dumps({
        "backtraceGraph": {"commands": [], "files": [], "nodes": []},
        "kind": "ctestInfo",
        "tests": [
            {"command": ["<REPOSITORY_ROOT>/build/passes.exe"], "name": "passes", "properties": []},
            {"command": ["<REPOSITORY_ROOT>/build/fails.exe"], "name": "fails", "properties": []},
        ],
        "version": {"major": 1, "minor": 0},
    }))
    raise SystemExit(0)
selection = argv[argv.index("--tests-information") + 1]
output = Path(argv[argv.index("--output-junit") + 1])
if selection.endswith(",2"):
    output.write_text(
        '<testsuite tests="1" failures="1" disabled="0" skipped="0">'
        '<testcase name="fails" classname="fails" time="0" status="fail">'
        '<failure message="Failed"/><properties/><system-out></system-out>'
        '</testcase></testsuite>',
        encoding="utf-8",
    )
    print("Test project <REPOSITORY_ROOT>/build")
    print("    Start 1: fails")
    print("1/1 Test #1: fails ......................***Failed    0.01 sec")
    print("0% tests passed, 1 tests failed out of 1")
else:
    raise SystemExit(2)
print("fake stderr", file=sys.stderr)
raise SystemExit(1)
''',
        encoding="utf-8",
    )
    junit_source = scenario / "unused-junit.xml"
    junit_source.write_text("<testsuite/>", encoding="utf-8")
    results_root = tmp_path / "results"
    original_environment = {
        "SCENARIO_DIR": str(scenario),
        "JUNIT_SOURCE": str(junit_source),
        "RESULTS_ROOT": str(results_root),
    }
    manifest["testing"]["host"]["environment"]["values"] = original_environment
    (project_root / ".stm32-project.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    before_project = sorted(
        (path.relative_to(project_root).as_posix(), path.read_bytes())
        for path in project_root.rglob("*")
        if path.is_file()
    )

    runners: list[HostTestRunner] = []

    def runner_factory(**kwargs: object) -> HostTestRunner:
        runner = HostTestRunner(
            **kwargs,
            cmake_executable=(sys.executable, str(script), "cmake"),
            ctest_executable=(sys.executable, str(script), "ctest"),
        )
        runners.append(runner)
        return runner

    monkeypatch.setattr(workflows, "_host_runner_factory", runner_factory)
    monkeypatch.setattr(
        workflows,
        "_snapshot_project_inputs",
        lambda _model: SimpleNamespace(sha256=SNAPSHOT_SHA),
    )
    monkeypatch.setattr(
        workflows,
        "_git_evidence",
        lambda _root: SimpleNamespace(head=GIT_HEAD, dirty=False),
    )

    discovered = workflows.host_test_discover(context)
    assert discovered.ok is True
    inventory_data = discovered.to_dict()["data"]["inventory"]
    assert inventory_data["case_ids"] == ["fails", "passes"]
    assert len(runners) == 1

    wrong = workflows.host_test_run(
        context, inventory_digest="0" * 64, case_ids=("fails",)
    )
    assert wrong.ok is False
    assert wrong.code == "TEST_INVENTORY_CHANGED"
    workspace = workflows.WorkspacePaths.from_roots(
        data_root, project_root, PROJECT_ID, context.session_id
    )
    roots = workspace.workspace_root / "evidence" / "roots"
    manifests = workspace.workspace_root / "evidence" / "manifests"
    manifests_before = tuple(sorted(path.name for path in manifests.glob("*.json")))
    assert not roots.exists() or not any(roots.rglob("*.json"))
    assert tuple(sorted(path.name for path in manifests.glob("*.json"))) == manifests_before

    inventory_digest = inventory_data["inventory_digest"]
    run = workflows.host_test_run(
        context, inventory_digest=inventory_digest, case_ids=("fails",)
    )
    assert run.ok is True
    run_data = run.to_dict()["data"]
    assert run_data["run"]["state"] == "failed"
    assert run_data["run"]["case_counts"] == {
        "passed": 0, "failed": 1, "skipped": 0, "error": 0, "timeout": 0,
    }
    assert len(runners) == 3
    runners.clear()

    shown = workflows.test_show(context, run_id=run_data["run"]["run_id"])
    assert shown.ok is True
    assert shown.to_dict()["data"] == {**run_data, "authoritative": True}
    assert runners == []
    after_project = sorted(
        (path.relative_to(project_root).as_posix(), path.read_bytes())
        for path in project_root.rglob("*")
        if path.is_file()
    )
    assert after_project == before_project
