"""Real-process tests for the CMake/CTest Host runner."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import threading
import time
from xml.etree import ElementTree

import pytest

import stm32_toolkit.testing.artifacts as artifacts_mod
from stm32_toolkit.evidence import EvidenceIdentity, EvidenceIdentityContext
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.process import ProcessError, ProcessResult
from stm32_toolkit.project_model import HostTestConfig
from stm32_toolkit.testing.artifacts import TestArtifactCollector as ArtifactCollector
from stm32_toolkit.testing.host import HostTestRunner
from stm32_toolkit.testing.model import (
    TestCaseResult as CaseResult,
    TestProtocolError as ProtocolError,
    create_inventory,
    calculate_host_build_inventory_digest,
    calculate_host_test_executable_inventory_digest,
    host_target_device,
)


REPO = Path(__file__).resolve().parents[3]
JUNIT = REPO / "tools/stm32-toolkit/tests/release/fixtures/native-outcomes/ctest-4.3.1-junit.xml"
CTEST_TEXT = (
    "Test project <REPOSITORY_ROOT>/build\n"
    "    Start 1: native-fail\n"
    "1/2 Test #1: native-fail ......................***Failed    0.07 sec\n"
    "    Start 2: native-pass\n"
    "2/2 Test #2: native-pass ......................   Passed    0.09 sec\n"
    "50% tests passed, 1 tests failed out of 2\n"
)
FAKE_TOOL = r'''
import json
import os
from pathlib import Path
import subprocess
import sys
import time

mode, *argv = sys.argv[1:]
root = Path(os.environ["SCENARIO_DIR"])
with (root / "calls.jsonl").open("a", encoding="utf-8") as stream:
    stream.write(json.dumps({
        "mode": mode,
        "argv": argv,
        "environment": sorted(os.environ),
        "authoritative_junit_before": sorted(
            str(path) for path in Path(os.environ["RESULTS_ROOT"]).rglob("ctest-junit.xml")
        ),
    }, ensure_ascii=False) + "\n")

if mode == "cmake":
    raise SystemExit(0)
if "--show-only=json-v1" in argv:
    changed = (root / "changed").exists()
    tests = [
        {"command": ["<REPOSITORY_ROOT>/build/native-pass.exe"], "name": "native-pass", "properties": []},
        {"command": ["<REPOSITORY_ROOT>/build/native-fail.exe" if not changed else "<REPOSITORY_ROOT>/build/changed.exe"], "name": "native-fail", "properties": []},
    ]
    print(json.dumps({
        "backtraceGraph": {"commands": [], "files": [], "nodes": []},
        "kind": "ctestInfo",
        "tests": tests,
        "version": {"major": 1, "minor": 0},
    }, ensure_ascii=False))
    raise SystemExit(0)
if (root / "timeout").exists():
    child = subprocess.Popen([
        sys.executable, "-c",
        "import pathlib,time; p=pathlib.Path(r'%s'); "
        "[(p.open('a').write('x'), time.sleep(.05)) for _ in range(600)]" % (root / "child-alive.txt"),
    ])
    (root / "child.pid").write_text(str(child.pid), encoding="ascii")
    time.sleep(30)
if (root / "no-junit").exists():
    raise SystemExit(1)
output = Path(argv[argv.index("--output-junit") + 1])
junit = Path(os.environ["JUNIT_SOURCE"]).read_text(encoding="utf-8")
if (root / "forge-swap").exists():
    junit = junit.replace('name="native-pass" classname="native-pass" time="0" status="run"><properties/><system-out></system-out>', 'name="native-pass" classname="native-pass" time="0" status="fail"><failure message="forged"/><properties/><system-out></system-out>')
    junit = junit.replace('name="native-fail" classname="native-fail" time="0" status="fail"><failure message="Failed"/>', 'name="native-fail" classname="native-fail" time="0" status="run">')
if (root / "forge-error").exists():
    junit = junit.replace('failures="1" disabled="0" skipped="0"', 'failures="0" errors="1" disabled="0" skipped="0"')
    junit = junit.replace('<failure message="Failed"/>', '<error message="forged"/>')
if (root / "harmless-text").exists():
    junit = junit.replace('message="Failed"', 'message="harmless diagnostic text"')
if (root / "unsafe-junit").exists():
    junit = junit.replace(
        'message="Failed"',
        'message="password=ROUND5-PLAINTEXT-SECRET C:\\\\Users\\\\victim\\\\private.txt"',
    )
output.write_bytes(junit.encode("utf-8"))
if (root / "invalid-ctest-text").exists():
    print("not a CTest report")
else:
    print("Test project <REPOSITORY_ROOT>/build")
    print("    Start 1: native-fail")
    print("1/2 Test #1: native-fail ......................***Failed    0.07 sec")
    print("    Start 2: native-pass")
    name = "native-extra" if (root / "wrong-text-node").exists() else "native-pass"
    print(f"2/2 Test #2: {name} ......................   Passed    0.09 sec")
    print("50% tests passed, 1 tests failed out of 2")
print("ctest stderr", file=sys.stderr)
raise SystemExit(1)
'''


def _identity() -> EvidenceIdentity:
    from hashlib import sha256

    digest = lambda value: sha256(value.encode("ascii")).hexdigest()
    return EvidenceIdentity(
        workspace_id=digest("workspace"),
        project_id="123e4567-e89b-42d3-a456-426614174000",
        session_id="session-0601-t07",
        build_id="b1f4df8abd1500605987396648ab0e3a39dab4c7c705675dde7f8d0559c1a3d1",
        elf_sha256="21d76339b932c29fc93d8e1a25edadf68b26c569e8748b979dac86306d702fb1",
        target_device=host_target_device(),
        input_snapshot_sha256=digest("snapshot"),
        git_commit="a" * 40,
        git_dirty=False,
    )


def _identity_context() -> EvidenceIdentityContext:
    identity = _identity()
    return EvidenceIdentityContext(
        workspace_id=identity.workspace_id,
        project_id=identity.project_id,
        session_id=identity.session_id,
        target_device=identity.target_device,
        input_snapshot_sha256=identity.input_snapshot_sha256,
        git_commit=identity.git_commit,
        git_dirty=identity.git_dirty,
    )


@pytest.fixture
def task_tmp() -> Path:
    """Use a fresh C:\\tmp direct child; the default pytest root has a stale denied ACL."""
    return Path(tempfile.mkdtemp(prefix="stm32tk-0601-t07-", dir="C:/tmp"))


def _runner(tmp_path: Path, *, timeout: int = 5) -> tuple[HostTestRunner, HostTestConfig, Path, Path]:
    scenario = tmp_path / "scenario"
    scenario.mkdir()
    script = scenario / "fake_tool.py"
    script.write_text(FAKE_TOOL, encoding="utf-8")
    results = tmp_path / "external-results"
    evidence = tmp_path / "evidence"
    config = HostTestConfig(
        build_preset="host-build",
        ctest_preset="host-tests",
        labels=(),
        timeout_seconds=timeout,
        environment_allow=("SystemRoot", "SCENARIO_DIR", "JUNIT_SOURCE", "RESULTS_ROOT", "TEST_TOKEN"),
        environment_values={
            "SCENARIO_DIR": str(scenario),
            "JUNIT_SOURCE": str(JUNIT),
            "RESULTS_ROOT": str(results),
            "TEST_TOKEN": "allowlisted",
        },
    )
    runner = HostTestRunner(
        project_root=REPO,
        evidence_store=EvidenceStore(evidence),
        results_root=results,
        cmake_executable=(sys.executable, str(script), "cmake"),
        ctest_executable=(sys.executable, str(script), "ctest"),
    )
    return runner, config, scenario, evidence


def _calls(scenario: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in (scenario / "calls.jsonl").read_text(encoding="utf-8").splitlines()]


def test_discover_builds_then_uses_distinct_ctest_preset_and_freezes_real_json(task_tmp: Path):
    """Preset inference, shell commands, ambient environment, or simplified discovery all fail here."""
    runner, config, scenario, evidence = _runner(task_tmp)

    inventory = runner.discover(config, _identity())

    calls = _calls(scenario)
    assert [(call["mode"], call["argv"]) for call in calls] == [
        ("cmake", ["--build", "--preset", "host-build"]),
        ("ctest", ["--preset", "host-tests", "--show-only=json-v1"]),
    ]
    assert inventory.case_ids == ("native-fail", "native-pass")
    assert inventory.identity == _identity()
    assert all(
        {name.casefold() for name in call["environment"]}
        == {"systemroot", "junit_source", "results_root", "scenario_dir", "test_token"}
        for call in calls
    )
    assert runner.discovery_artifact is not None
    discovery_object = evidence / runner.discovery_artifact.relative_path
    assert discovery_object.is_file()
    payload = json.loads(discovery_object.read_text(encoding="utf-8"))
    assert payload["kind"] == "ctestInfo"
    assert payload["version"] == {"major": 1, "minor": 0}


def test_context_discovery_derives_host_hashes_and_full_identity_stays_fail_closed(task_tmp: Path):
    """Discovery owns Host digests while a fully bound identity still requires exact equality."""
    runner, config, _scenario, _evidence = _runner(task_tmp)
    context = _identity_context()
    inventory = runner.discover(config, context)
    executables = (
        {
            "case_id": "native-pass",
            "command": ["<REPOSITORY_ROOT>/build/native-pass.exe"],
        },
        {
            "case_id": "native-fail",
            "command": ["<REPOSITORY_ROOT>/build/native-fail.exe"],
        },
    )

    assert inventory.identity.workspace_id == context.workspace_id
    assert inventory.identity.project_id == context.project_id
    assert inventory.identity.session_id == context.session_id
    assert inventory.identity.target_device == context.target_device
    assert inventory.identity.input_snapshot_sha256 == context.input_snapshot_sha256
    assert inventory.identity.git_commit == context.git_commit
    assert inventory.identity.git_dirty == context.git_dirty
    assert inventory.identity.build_id == calculate_host_build_inventory_digest(
        config.build_preset, config.ctest_preset, config.labels, executables
    )
    assert inventory.identity.elf_sha256 == calculate_host_test_executable_inventory_digest(executables)

    with pytest.raises(ProtocolError, match="Host identity differs"):
        runner.discover(config, replace(inventory.identity, build_id="1" * 64))


def test_execute_passes_child_only_environment_without_global_mutation(task_tmp: Path):
    """A blocked Host process must not alter bytes observed by another thread or subprocess."""
    runner, config, _scenario, _evidence = _runner(task_tmp)
    entered = threading.Event()
    release = threading.Event()
    observed = []
    before = tuple(os.environ.items())

    def blocking(request):
        observed.append(request.env)
        entered.set()
        assert release.wait(5)
        return ProcessResult(0, "", "", False, 1, False, False)

    runner._process_runner = blocking
    worker = threading.Thread(target=runner._execute, args=(("tool",), config))
    worker.start()
    assert entered.wait(5)
    assert tuple(os.environ.items()) == before
    import subprocess
    child = subprocess.run(
        [sys.executable, "-c", "import os,sys;sys.stdout.buffer.write(os.environ.get('SCENARIO_DIR','absent').encode())"],
        stdout=subprocess.PIPE, check=True,
    )
    assert child.stdout == os.environ.get("SCENARIO_DIR", "absent").encode()
    release.set()
    worker.join(5)
    assert not worker.is_alive()
    assert dict(observed[0]) == runner._environment(config)


def test_invalid_host_environment_is_stable_and_never_mutates_process_bytes(task_tmp: Path):
    """Invalid names fail before the runner or global process environment is touched."""
    runner, config, _scenario, _evidence = _runner(task_tmp)
    bad = replace(
        config,
        environment_allow=("BAD=NAME",),
        environment_values={"BAD=NAME": "x"},
    )
    before = json.dumps(dict(os.environ), ensure_ascii=False, sort_keys=True).encode("utf-8")
    with pytest.raises(ProtocolError) as caught:
        runner._execute(("tool",), bad)
    assert caught.value.code == "TEST_ENVIRONMENT_INVALID"
    assert json.dumps(dict(os.environ), ensure_ascii=False, sort_keys=True).encode("utf-8") == before


def test_native_outcomes_fixtures_are_lf_bytes():
    """The fake CTest preserves the tracked JUnit bytes when publishing evidence."""
    assert b"\r" not in JUNIT.read_bytes()


def test_run_selects_exact_ids_parses_ctest_431_junit_and_ingests_every_artifact(task_tmp: Path):
    """The run result is derived from real CTest JUnit and content-addressed stored bytes."""
    runner, config, scenario, evidence = _runner(task_tmp)
    inventory = runner.discover(config, _identity())

    manifest = runner.run(inventory, ("native-fail", "native-pass"))

    calls = _calls(scenario)
    assert calls[2]["argv"] == ["--preset", "host-tests", "--show-only=json-v1"]
    run_argv = calls[3]["argv"]
    assert run_argv[:3] == ["--preset", "host-tests", "--tests-information"]
    assert run_argv[3] == "0,0,0,1,2"
    assert run_argv[4:7] == ["--verbose", "--output-on-failure", "--output-junit"]
    junit_path = Path(run_argv[7])
    assert junit_path.is_absolute()
    assert REPO not in junit_path.parents
    assert junit_path.name == "ctest-native-junit.xml"
    assert "ctest-bridge-private" in junit_path.parent.name
    assert calls[3]["authoritative_junit_before"] == []
    assert not any(
        path.name == "ctest-junit.xml" and path == junit_path
        for path in task_tmp.rglob("ctest-junit.xml")
    )
    assert manifest.state == "failed"
    assert [(case.case_id, case.state) for case in manifest.cases] == [
        ("native-fail", "failed"), ("native-pass", "passed")
    ]
    assert manifest.transport is None
    assert manifest.stdout is not None and manifest.stderr is not None
    assert (evidence / manifest.stdout.relative_path).read_text(encoding="utf-8") == CTEST_TEXT
    assert (evidence / manifest.stderr.relative_path).read_text(encoding="utf-8") == "ctest stderr\n"
    assert (evidence / manifest.raw_events.relative_path).read_bytes() == JUNIT.read_bytes()


def test_missing_case_and_changed_executable_inventory_fail_before_execution(task_tmp: Path):
    """Selection and the complete executable inventory stay bound to discovery."""
    runner, config, scenario, _evidence = _runner(task_tmp)
    inventory = runner.discover(config, _identity())

    with pytest.raises(ProtocolError) as caught:
        runner.run(inventory, ("absent",))
    assert caught.value.code == "TEST_CASE_NOT_FOUND"
    assert len(_calls(scenario)) == 2

    (scenario / "changed").write_text("changed", encoding="ascii")
    with pytest.raises(ProtocolError) as caught:
        runner.run(inventory, ("native-pass",))
    assert caught.value.code == "TEST_INVENTORY_CHANGED"
    assert len(_calls(scenario)) == 3


def test_discovery_rejects_noncanonical_host_build_or_executable_identity(task_tmp: Path):
    """Random nonzero hashes cannot masquerade as canonical Host build/test inventories."""
    for field in ("build_id", "elf_sha256"):
        child = task_tmp / field
        child.mkdir()
        runner, config, _scenario, _evidence = _runner(child)
        with pytest.raises(ProtocolError) as caught:
            runner.discover(config, replace(_identity(), **{field: "1" * 64}))
        assert caught.value.code == "TEST_IDENTITY_MISMATCH"


def test_timeout_uses_safe_process_layer_to_cleanup_the_whole_child_tree(task_tmp: Path):
    """CTest timeout must reap its descendant instead of only abandoning the parent."""
    runner, config, scenario, _evidence = _runner(task_tmp, timeout=1)
    inventory = runner.discover(config, _identity())
    (scenario / "timeout").write_text("timeout", encoding="ascii")

    with pytest.raises(ProtocolError) as caught:
        runner.run(inventory, ("native-pass",))

    assert caught.value.code == "TEST_PROCESS_TIMEOUT"
    assert "scratch preserved at " in caught.value.message
    assert Path(caught.value.message.split("scratch preserved at ", 1)[1]).is_dir()
    alive = scenario / "child-alive.txt"
    deadline = time.monotonic() + 3
    while not alive.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert alive.exists()
    first = alive.stat().st_size
    time.sleep(0.4)
    assert alive.stat().st_size == first


def test_bridge_failure_preserves_and_reports_private_scratch(task_tmp: Path):
    runner, config, scenario, _evidence = _runner(task_tmp)
    inventory = runner.discover(config, _identity())
    (scenario / "no-junit").write_text("no-junit", encoding="ascii")

    with pytest.raises(ProtocolError) as caught:
        runner.run(inventory, ("native-pass",))

    assert caught.value.code == "TEST_PROCESS_ERROR"
    assert "scratch preserved at " in caught.value.message
    assert Path(caught.value.message.split("scratch preserved at ", 1)[1]).is_dir()


def test_exit_and_junit_disagreement_is_rejected(task_tmp: Path):
    """A successful exit cannot override a failing native CTest case."""
    runner, config, scenario, _evidence = _runner(task_tmp)
    inventory = runner.discover(config, _identity())
    script = scenario / "fake_tool.py"
    script.write_text(FAKE_TOOL.replace("raise SystemExit(1)", "raise SystemExit(0)"), encoding="utf-8")

    with pytest.raises(ProtocolError) as caught:
        runner.run(inventory, ("native-fail", "native-pass"))

    assert caught.value.code == "TEST_EXIT_MISMATCH"


@pytest.mark.parametrize("forge", ["forge-swap", "forge-error"])
def test_stdout_node_facts_reject_self_consistent_forged_junit(task_tmp: Path, forge: str):
    """A forged JUnit cannot swap or recategorize nodes while preserving aggregate failure."""
    runner, config, scenario, _evidence = _runner(task_tmp)
    inventory = runner.discover(config, _identity())
    (scenario / "authoritative-text").write_text("on", encoding="ascii")
    (scenario / forge).write_text("on", encoding="ascii")

    with pytest.raises(ProtocolError) as caught:
        runner.run(inventory, ("native-fail", "native-pass"))

    assert caught.value.code == "TEST_NATIVE_RESULT_INVALID"


def test_rejected_junit_is_validated_before_any_run_artifact_publication(task_tmp: Path):
    """Rejected raw JUnit bytes never enter evidence, even as a transient artifact."""
    runner, config, scenario, evidence = _runner(task_tmp)
    inventory = runner.discover(config, _identity())
    before = {path.relative_to(evidence) for path in evidence.rglob("*") if path.is_file()}
    (scenario / "unsafe-junit").write_text("on", encoding="ascii")

    with pytest.raises(ProtocolError) as caught:
        runner.run(inventory, ("native-fail", "native-pass"))

    assert caught.value.code == "TEST_NATIVE_RESULT_INVALID"
    after = {path.relative_to(evidence) for path in evidence.rglob("*") if path.is_file()}
    assert after == before
    published = b"\n".join(path.read_bytes() for path in evidence.rglob("*") if path.is_file())
    assert b"ROUND5-PLAINTEXT-SECRET" not in published
    assert b"private.txt" not in published


def test_matching_junit_free_text_cannot_change_public_case_facts(task_tmp: Path):
    """Safe JUnit prose is retained only as raw evidence and never enters case facts."""
    runner, config, scenario, _evidence = _runner(task_tmp)
    inventory = runner.discover(config, _identity())
    (scenario / "authoritative-text").write_text("on", encoding="ascii")
    baseline = runner.run(inventory, ("native-fail", "native-pass"))
    (scenario / "harmless-text").write_text("on", encoding="ascii")
    forged = runner.run(inventory, ("native-fail", "native-pass"))

    public = lambda manifest: tuple(
        (case.case_id, case.state, case.duration_ms, case.message, case.stdout, case.stderr)
        for case in manifest.cases
    )
    assert forged.identity == baseline.identity == inventory.identity
    assert forged.state == baseline.state == "failed"
    assert public(forged) == public(baseline)


@pytest.mark.parametrize("marker", ["invalid-ctest-text", "wrong-text-node"])
def test_native_text_malformed_or_inventory_mismatch_fails_closed(
    task_tmp: Path, marker: str,
):
    runner, config, scenario, _evidence = _runner(task_tmp)
    inventory = runner.discover(config, _identity())
    (scenario / marker).write_text("on", encoding="ascii")
    with pytest.raises(ProtocolError) as caught:
        runner.run(inventory, ("native-fail", "native-pass"))
    assert caught.value.code == "TEST_NATIVE_RESULT_INVALID"


def test_artifact_collector_rejects_nonexternal_aliases_and_invalid_paths(
    task_tmp: Path, monkeypatch,
):
    """Only new files below the owned external root may become authoritative artifacts."""
    project = task_tmp / "project"
    project.mkdir()
    evidence = EvidenceStore(task_tmp / "evidence")
    with pytest.raises(TypeError):
        ArtifactCollector("results", evidence, project_root=project)
    inside = project / "inside"
    with pytest.raises(ProtocolError):
        ArtifactCollector(project / "inside", evidence, project_root=project)
    assert not inside.exists()
    with pytest.raises(TypeError):
        ArtifactCollector(task_tmp / "results-wrong-store", object(), project_root=project)

    collector = ArtifactCollector(task_tmp / "results", evidence, project_root=project)
    for prefix in ("", "UPPER"):
        with pytest.raises(ProtocolError):
            collector.new_directory(prefix)
    directory = collector.new_directory("native")
    with pytest.raises(ProtocolError):
        collector.output_path(task_tmp, "result.xml")
    for name in ("", "../result.xml", "sub/result.xml", "sub\\result.xml"):
        with pytest.raises(ProtocolError):
            collector.output_path(directory, name)
    existing = directory / "existing.xml"
    existing.write_bytes(b"x")
    with pytest.raises(ProtocolError):
        collector.output_path(directory, existing.name)
    with pytest.raises(TypeError):
        collector.write_and_ingest(
            directory, "bad.txt", "not-bytes", kind="test", media_type="text/plain"
        )

    original_fsync = os.fsync
    monkeypatch.setattr(os, "fsync", lambda _descriptor: (_ for _ in ()).throw(OSError("fsync")))
    with pytest.raises(ProtocolError) as caught:
        collector.write_and_ingest(
            directory, "fsync.txt", b"bytes", kind="test", media_type="text/plain"
        )
    assert caught.value.code == "TEST_RESULTS_UNSAFE"
    monkeypatch.setattr(os, "fsync", original_fsync)

    with pytest.raises(ProtocolError):
        collector.ingest_existing(
            "not-a-path", kind="test", media_type="text/plain"
        )
    missing = directory / "missing.xml"
    with pytest.raises(ProtocolError) as caught:
        collector.ingest_existing(missing, kind="test", media_type="application/xml")
    assert caught.value.code == "TEST_NATIVE_RESULT_INVALID"
    huge = directory / "huge.bin"
    with huge.open("wb") as stream:
        stream.seek(64 * 1024 * 1024)
        stream.write(b"x")
    with pytest.raises(ProtocolError) as caught:
        collector.ingest_existing(
            huge, kind="events", media_type="application/octet-stream", stream_limit=True
        )
    assert caught.value.code == "TEST_STREAM_TOO_LARGE"


def test_artifact_collector_rejects_directory_alias_before_writing(task_tmp: Path):
    """A symlinked external root must fail before any child result is created."""
    project = task_tmp / "project"
    project.mkdir()
    real_results = task_tmp / "real-results"
    real_results.mkdir()
    alias = task_tmp / "results-alias"
    import subprocess
    created = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(alias), str(real_results)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    assert created.returncode == 0, created.stderr
    before = tuple(real_results.iterdir())
    with pytest.raises(ProtocolError) as caught:
        ArtifactCollector(alias, EvidenceStore(task_tmp / "evidence"), project_root=project)
    assert caught.value.code == "TEST_RESULTS_UNSAFE"
    assert tuple(real_results.iterdir()) == before

    parent_target = task_tmp / "parent-target"
    parent_target.mkdir()
    parent_alias = task_tmp / "parent-alias"
    created = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(parent_alias), str(parent_target)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    assert created.returncode == 0, created.stderr
    before = tuple(parent_target.iterdir())
    with pytest.raises(ProtocolError) as caught:
        ArtifactCollector(
            parent_alias / "must-not-be-created",
            EvidenceStore(task_tmp / "parent-evidence"),
            project_root=project,
        )
    assert caught.value.code == "TEST_RESULTS_UNSAFE"
    assert tuple(parent_target.iterdir()) == before


def test_artifact_write_detects_child_replacement_during_ingestion(task_tmp: Path, monkeypatch):
    """Replacing a CREATE_NEW child cannot make different bytes authoritative."""
    project = task_tmp / "project"
    project.mkdir()
    store = EvidenceStore(task_tmp / "evidence")
    collector = ArtifactCollector(task_tmp / "results", store, project_root=project)
    directory = collector.new_directory("native")
    original = store.ingest_file

    def replace_then_ingest(path, *, kind, media_type):
        displaced = path.with_suffix(".displaced")
        os.replace(path, displaced)
        path.write_bytes(b"attacker")
        return original(path, kind=kind, media_type=media_type)

    monkeypatch.setattr(store, "ingest_file", replace_then_ingest)
    with pytest.raises(ProtocolError) as caught:
        collector.write_and_ingest(
            directory, "result.txt", b"trusted", kind="test", media_type="text/plain"
        )
    assert caught.value.code == "TEST_RESULTS_UNSAFE"


def test_artifact_windows_handles_fail_closed_on_final_path_and_api_faults(
    task_tmp: Path, monkeypatch,
):
    """Final-path aliases and handle duplication/conversion failures never publish an artifact."""
    project = task_tmp / "project"
    project.mkdir()
    with monkeypatch.context() as scoped:
        scoped.setattr(artifacts_mod, "_windows_final_path", lambda _handle: task_tmp / "other")
        with pytest.raises(ProtocolError):
            ArtifactCollector(task_tmp / "bad-final", EvidenceStore(task_tmp / "e1"), project_root=project)

    collector = ArtifactCollector(task_tmp / "results", EvidenceStore(task_tmp / "e2"), project_root=project)
    directory = collector.new_directory("native")
    with monkeypatch.context() as scoped:
        scoped.setattr(artifacts_mod._kernel32, "DuplicateHandle", lambda *_args: False)
        with pytest.raises(ProtocolError) as caught:
            collector.write_and_ingest(directory, "duplicate.txt", b"x", kind="test", media_type="text/plain")
        assert caught.value.code == "TEST_RESULTS_UNSAFE"
    with monkeypatch.context() as scoped:
        scoped.setattr(
            artifacts_mod.msvcrt, "open_osfhandle",
            lambda *_args: (_ for _ in ()).throw(OSError("conversion")),
        )
        with pytest.raises(ProtocolError) as caught:
            collector.write_and_ingest(directory, "conversion.txt", b"x", kind="test", media_type="text/plain")
        assert caught.value.code == "TEST_RESULTS_UNSAFE"


def test_artifact_directory_handle_detects_missing_reparse_and_replaced_paths(
    task_tmp: Path, monkeypatch,
):
    """Every use rechecks the registered directory's type, path, and pinned identity."""
    project = task_tmp / "project"
    project.mkdir()
    collector = ArtifactCollector(task_tmp / "results", EvidenceStore(task_tmp / "evidence"), project_root=project)
    directory = collector.new_directory("native")
    with pytest.raises(ProtocolError):
        collector.output_path(collector.results_root / "unregistered", "x")

    with monkeypatch.context() as scoped:
        scoped.setattr(artifacts_mod.os, "lstat", lambda _path: (_ for _ in ()).throw(OSError("missing")))
        with pytest.raises(ProtocolError):
            collector.output_path(directory, "missing.txt")
    real = os.lstat(directory)
    from types import SimpleNamespace
    with monkeypatch.context() as scoped:
        scoped.setattr(
            artifacts_mod.os, "lstat",
            lambda _path: SimpleNamespace(st_mode=real.st_mode, st_file_attributes=0x400),
        )
        with pytest.raises(ProtocolError):
            collector.output_path(directory, "reparse.txt")
    with monkeypatch.context() as scoped:
        scoped.setattr(
            artifacts_mod, "_path_identity",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("identity")),
        )
        with pytest.raises(ProtocolError):
            collector.output_path(directory, "identity-error.txt")
    with monkeypatch.context() as scoped:
        scoped.setattr(artifacts_mod, "_path_identity", lambda *_args, **_kwargs: (0, 0, 0))
        with pytest.raises(ProtocolError):
            collector.output_path(directory, "replaced.txt")


def test_artifact_creation_and_pinned_pre_post_identity_faults_are_stable(
    task_tmp: Path, monkeypatch,
):
    """Create failure and identity changes before/after ingestion are stable closed failures."""
    project = task_tmp / "project"
    project.mkdir()
    collector = ArtifactCollector(task_tmp / "results", EvidenceStore(task_tmp / "evidence"), project_root=project)
    with monkeypatch.context() as scoped:
        scoped.setattr(
            artifacts_mod.tempfile, "mkdtemp",
            lambda **_kwargs: (_ for _ in ()).throw(OSError("create")),
        )
        with pytest.raises(ProtocolError):
            collector.new_directory("fault")

    directory = collector.new_directory("native")
    path, handle = collector._open_child(directory, "pre.txt", create=True, write=True)
    try:
        before = artifacts_mod._handle_identity(handle)
        with monkeypatch.context() as scoped:
            scoped.setattr(artifacts_mod, "_path_identity", lambda *_args, **_kwargs: (0, 0, 0))
            with pytest.raises(ProtocolError):
                collector._ingest_pinned(path, handle, kind="test", media_type="text/plain", stream_limit=False)
        calls = iter((before, (0, 0, 0)))
        with monkeypatch.context() as scoped:
            scoped.setattr(artifacts_mod, "_path_identity", lambda *_args, **_kwargs: next(calls))
            with pytest.raises(ProtocolError):
                collector._ingest_pinned(path, handle, kind="test", media_type="text/plain", stream_limit=False)
    finally:
        artifacts_mod._close_handle(handle)


def _discovery_payload() -> dict[str, object]:
    return {
        "backtraceGraph": {"commands": [], "files": [], "nodes": []},
        "kind": "ctestInfo",
        "tests": [
            {
                "command": ["build/one.exe"], "name": "one",
                "properties": [{"name": "LABELS", "value": ["unit", "fast"]}],
            },
            {
                "command": ["build/two.exe"], "name": "two",
                "properties": [{"name": "LABELS", "value": "unit"}],
            },
        ],
        "version": {"major": 1, "minor": 0},
    }


def test_ctest_json_v1_parser_filters_labels_and_rejects_native_shape_mutations():
    """Discovery consumes the real json-v1 record shape, including both LABELS encodings."""
    cases, executables, ordinals = HostTestRunner._parse_discovery(
        _discovery_payload(), ("unit", "fast")
    )
    assert cases == ("one",)
    assert executables == ({"case_id": "one", "command": ["build/one.exe"]},)
    assert ordinals == {"one": 1}
    assert HostTestRunner._parse_discovery(_discovery_payload(), ("unit",))[0] == ("one", "two")

    invalid_payloads: list[object] = [
        [],
        {**_discovery_payload(), "kind": "other"},
        {**_discovery_payload(), "tests": [None]},
        {**_discovery_payload(), "tests": [{"name": "", "command": ["x"]}]},
        {**_discovery_payload(), "tests": [{"name": "one", "command": []}]},
        {**_discovery_payload(), "tests": [{"name": "one", "command": [1]}]},
        {**_discovery_payload(), "tests": [{"name": "one", "command": ["x"], "properties": {}}]},
        {**_discovery_payload(), "tests": [{"name": "one", "command": ["x"], "properties": [None]}]},
        {**_discovery_payload(), "tests": [{
            "name": "one", "command": ["x"],
            "properties": [{"name": "LABELS", "value": 1}],
        }]},
        {**_discovery_payload(), "tests": [
            {"name": "one", "command": ["x"]}, {"name": "one", "command": ["y"]},
        ]},
    ]
    for payload in invalid_payloads:
        with pytest.raises(ProtocolError):
            HostTestRunner._parse_discovery(payload, ())


def test_runner_constructor_environment_and_process_failures_are_closed(task_tmp: Path):
    """Invalid injection, environment, and process outcomes produce stable domain failures."""
    project = task_tmp / "project"
    project.mkdir()
    evidence = EvidenceStore(task_tmp / "evidence")
    arguments = {
        "project_root": project,
        "evidence_store": evidence,
        "results_root": task_tmp / "results",
    }
    with pytest.raises(TypeError):
        HostTestRunner(**{**arguments, "project_root": "project"})
    file_root = task_tmp / "file-root"
    file_root.write_text("file", encoding="ascii")
    with pytest.raises(ValueError):
        HostTestRunner(**{**arguments, "project_root": file_root})
    for executable in ((), ("ok", 1), 1):
        with pytest.raises(ValueError):
            HostTestRunner(**arguments, cmake_executable=executable)
    with pytest.raises(TypeError):
        HostTestRunner(**arguments, process_runner=None)

    config = HostTestConfig("build", "test", (), 1, ("A", "A"), {})
    with pytest.raises(ProtocolError):
        HostTestRunner._environment(config)
    config = HostTestConfig("build", "test", (), 1, (), {"A": "x"})
    with pytest.raises(ProtocolError):
        HostTestRunner._environment(config)
    config = HostTestConfig("build", "test", (), 1, ("PATH", "Path"), {})
    with pytest.raises(ProtocolError):
        HostTestRunner._environment(config)
    config = HostTestConfig("build", "test", (), 1, ("A",), {"A": 1})
    with pytest.raises(ProtocolError):
        HostTestRunner._environment(config)
    config = HostTestConfig("build", "test", (), 1, (["A"],), {})
    with pytest.raises(ProtocolError):
        HostTestRunner._environment(config)
    config = HostTestConfig("build", "test", (["unit"],), 1, (), {})
    with pytest.raises(ProtocolError):
        HostTestRunner._parse_discovery(_discovery_payload(), config.labels)
    with pytest.raises(ProtocolError):
        HostTestRunner._environment(object())

    def broken(_request):
        raise ProcessError("launch", "failed")

    runner = HostTestRunner(**arguments, process_runner=broken)
    good_config = HostTestConfig("build", "test", (), 1, (), {})
    with pytest.raises(ProtocolError) as caught:
        runner._execute(("tool",), good_config)
    assert caught.value.code == "TEST_PROCESS_ERROR"
    for result, code in (
        (ProcessResult(1, "", "", True, 1, False, False), "TEST_PROCESS_TIMEOUT"),
        (ProcessResult(0, "", "", False, 1, True, False), "TEST_PROCESS_OUTPUT_LIMIT"),
        (ProcessResult(1, "", "", False, 1, False, False), "TEST_PROCESS_FAILED"),
    ):
        with pytest.raises(ProtocolError) as caught:
            HostTestRunner._check_process(result, operation="operation")
        assert caught.value.code == code


def test_run_rejects_nonhost_unknown_and_duplicate_selection_before_process(task_tmp: Path):
    """Only a runner-frozen Host inventory and unique tuple selection can execute."""
    runner, config, _scenario, _evidence = _runner(task_tmp)
    inventory = runner.discover(config, _identity())
    target = create_inventory("target", _identity(), ("one",), "2026-08-16T00:00:00.000000Z")
    with pytest.raises(ProtocolError):
        runner.run(target, ("one",))
    unknown = create_inventory("host", _identity(), ("one",), "2026-08-16T00:00:00.000000Z")
    with pytest.raises(ProtocolError):
        runner.run(unknown, ("one",))
    for selection in (["native-pass"], ("native-pass", "native-pass"), (["native-pass"],)):
        with pytest.raises(ProtocolError) as caught:
            runner.run(inventory, selection)
        assert caught.value.code == "TEST_CASE_NOT_FOUND"


def test_junit_parser_cross_checks_states_but_never_promotes_junit_free_text(task_tmp: Path):
    """JUnit categories/streams are checked but native text alone supplies public facts."""
    runner, _config, _scenario, evidence = _runner(task_tmp)
    directory = runner._collector.new_directory("junit-states")
    path = runner._collector.output_path(directory, "states.xml")
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<testsuite tests="3" failures="1" errors="0" skipped="1">'
        '<testcase name="failure" time="0.001" status="fail"><failure message="boom"/></testcase>'
        '<testcase name="skip" time="0" status="notrun"><skipped message="disabled"/></testcase>'
        '<testcase name="pass" time="0" status="run"><system-out>out</system-out><system-err>err</system-err></testcase>'
        '</testsuite>',
        encoding="utf-8",
    )

    cases = runner._parse_junit(
        path, ("failure", "skip", "pass"), directory,
        {"failure": "failed", "skip": "skipped", "pass": "passed"},
    )

    assert [(case.case_id, case.state) for case in cases] == [
        ("failure", "failed"), ("skip", "skipped"), ("pass", "passed"),
    ]
    assert all(
        case.duration_ms == 0 and case.message is None
        and case.stdout is None and case.stderr is None
        for case in cases
    )


@pytest.mark.parametrize(
    "xml",
    [
        "not xml",
        "<root/>",
        '<testsuite tests="1"><testcase name="other" status="run"/></testsuite>',
        '<testsuite tests="1"><testcase name="one" status="mystery"/></testsuite>',
        '<testsuite tests="1"><testcase name="one" status="run" time="bad"/></testsuite>',
        '<testsuite tests="2"><testcase name="one" status="run"/></testsuite>',
        '<testsuite tests="1" failures="0"><testcase name="one" status="fail"/></testsuite>',
        '<testsuite tests="0"/>',
    ],
)
def test_junit_parser_rejects_malformed_root_inventory_status_duration_and_counts(
    task_tmp: Path, xml: str,
):
    """Malformed native XML cannot be normalized into a plausible TestRunManifest."""
    runner, _config, _scenario, _evidence = _runner(task_tmp)
    directory = runner._collector.new_directory("junit-invalid")
    path = runner._collector.output_path(directory, "invalid.xml")
    path.write_text(xml, encoding="utf-8")
    with pytest.raises(ProtocolError):
        runner._parse_junit(path, ("one",), directory, {"one": "passed"})


def test_junit_duration_summary_and_run_state_boundaries_are_exact():
    """Fractional milliseconds, overflow, absent suites, and state priority stay deterministic."""
    assert HostTestRunner._junit_duration(None) == 0
    for value in ("nan", "-1", "0.0001", str(2**63)):
        with pytest.raises(ProtocolError):
            HostTestRunner._junit_duration(value)
    with pytest.raises(ProtocolError):
        HostTestRunner._validate_junit_summaries(ElementTree.fromstring("<testsuites/>"), [])


def test_junit_counts_are_exact_per_category_and_root_totals_must_match(task_tmp: Path):
    """Moving a count between failure/error or skipped/disabled must be rejected."""
    runner, _config, _scenario, _evidence = _runner(task_tmp)
    directory = runner._collector.new_directory("junit-counts")
    base_cases = (
        '<testcase name="f" status="fail"><failure/></testcase>'
        '<testcase name="e" status="run"><error/></testcase>'
        '<testcase name="s" status="skip"><skipped/></testcase>'
        '<testcase name="d" status="notrun"/>'
    )
    for attributes in (
        'tests="4" failures="2" errors="0" skipped="1" disabled="1"',
        'tests="4" failures="1" errors="1" skipped="2" disabled="0"',
    ):
        path = directory / f"bad-{len(list(directory.iterdir()))}.xml"
        path.write_text(f"<testsuite {attributes}>{base_cases}</testsuite>", encoding="utf-8")
        with pytest.raises(ProtocolError) as caught:
            runner._parse_junit(
                path, ("f", "e", "s", "d"), directory,
                {"f": "failed", "e": "failed", "s": "skipped", "d": "skipped"},
            )
        assert caught.value.code == "TEST_NATIVE_RESULT_INVALID"

    root = directory / "bad-root.xml"
    root.write_text(
        '<testsuites tests="99" failures="1" errors="1" skipped="1" disabled="1">'
        '<testsuite tests="4" failures="1" errors="1" skipped="1" disabled="1">'
        f"{base_cases}</testsuite></testsuites>", encoding="utf-8",
    )
    with pytest.raises(ProtocolError) as caught:
        runner._parse_junit(
            root, ("f", "e", "s", "d"), directory,
            {"f": "failed", "e": "failed", "s": "skipped", "d": "skipped"},
        )
    assert caught.value.code == "TEST_NATIVE_RESULT_INVALID"


def test_junit_case_has_at_most_one_terminal_child(task_tmp: Path):
    """Duplicate or mixed terminal children cannot be collapsed by a tag dictionary."""
    runner, _config, _scenario, _evidence = _runner(task_tmp)
    directory = runner._collector.new_directory("junit-terminal")
    for children in ("<failure/><failure/>", "<failure/><error/>", "<skipped/><error/>"):
        path = directory / f"bad-{len(list(directory.iterdir()))}.xml"
        path.write_text(
            '<testsuite tests="1" failures="0" errors="1" skipped="0" disabled="0">'
            f'<testcase name="one" status="run">{children}</testcase></testsuite>',
            encoding="utf-8",
        )
        with pytest.raises(ProtocolError) as caught:
            runner._parse_junit(path, ("one",), directory, {"one": "failed"})
        assert caught.value.code == "TEST_NATIVE_RESULT_INVALID"
    passed = CaseResult("p", "passed", "2026-08-16T00:00:00.000000Z", "2026-08-16T00:00:00.000000Z", 0, None, None, None)
    failed = CaseResult("f", "failed", "2026-08-16T00:00:00.000000Z", "2026-08-16T00:00:00.000000Z", 0, None, None, None)
    error = CaseResult("e", "error", "2026-08-16T00:00:00.000000Z", "2026-08-16T00:00:00.000000Z", 0, None, None, None)
    assert HostTestRunner._run_state((passed,)) == "passed"
    assert HostTestRunner._run_state((failed,)) == "failed"
    assert HostTestRunner._run_state((failed, error)) == "error"


@pytest.mark.parametrize(
    "unsafe",
    ["password=hunter2", r"C:\Users\victim\secret.txt", "/home/victim/secret.txt"],
)
def test_junit_untrusted_text_rejects_credentials_and_absolute_paths(
    task_tmp: Path, unsafe: str,
):
    """Untrusted JUnit prose is retained only when it cannot disclose secrets or host paths."""
    runner, _config, _scenario, _evidence = _runner(task_tmp)
    directory = runner._collector.new_directory("junit-unsafe")
    path = runner._collector.output_path(directory, "unsafe.xml")
    path.write_text(
        '<testsuite tests="1" failures="1" errors="0" skipped="0" disabled="0">'
        f'<testcase name="one" status="fail"><failure message="{unsafe}"/></testcase>'
        '</testsuite>',
        encoding="utf-8",
    )
    with pytest.raises(ProtocolError) as caught:
        runner._parse_junit(path, ("one",), directory, {"one": "failed"})
    assert caught.value.code == "TEST_NATIVE_RESULT_INVALID"


@pytest.mark.parametrize("kind", ["nontext", "nonnfc", "overflow"])
def test_junit_untrusted_text_rejects_nontext_nonnfc_and_overflow(kind: str):
    value = {"nontext": 1, "nonnfc": "e\u0301", "overflow": "x" * (1024 * 1024 + 1)}[kind]
    with pytest.raises(ProtocolError):
        HostTestRunner._validate_untrusted_junit_text(value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "authoritative",
    [1, {}, {"one": "error"}],
)
def test_junit_parser_rejects_unbound_native_text_mapping(
    task_tmp: Path, authoritative,
):
    runner, _config, _scenario, _evidence = _runner(task_tmp)
    directory = runner._collector.new_directory("junit-unbound")
    path = runner._collector.output_path(directory, "one.xml")
    path.write_text(
        '<testsuite tests="1"><testcase name="one" status="run"/></testsuite>',
        encoding="utf-8",
    )
    with pytest.raises(ProtocolError):
        runner._parse_junit(path, ("one",), directory, authoritative)


@pytest.mark.parametrize(
    ("status", "child"),
    [("fail", "<skipped/>"), ("skip", "<failure/>"), ("run", "<failure/>")],
)
def test_junit_parser_rejects_each_single_terminal_status_contradiction(
    task_tmp: Path, status: str, child: str,
):
    runner, _config, _scenario, _evidence = _runner(task_tmp)
    directory = runner._collector.new_directory("junit-contradiction")
    path = runner._collector.output_path(directory, "one.xml")
    path.write_text(
        f'<testsuite tests="1"><testcase name="one" status="{status}">{child}</testcase></testsuite>',
        encoding="utf-8",
    )
    with pytest.raises(ProtocolError):
        runner._parse_junit(path, ("one",), directory, {"one": "failed"})


def test_junit_parser_rejects_duplicate_stream_child(task_tmp: Path):
    runner, _config, _scenario, _evidence = _runner(task_tmp)
    directory = runner._collector.new_directory("junit-stream-duplicate")
    path = runner._collector.output_path(directory, "one.xml")
    path.write_text(
        '<testsuite tests="1"><testcase name="one" status="run">'
        '<system-out/><system-out/></testcase></testsuite>', encoding="utf-8",
    )
    with pytest.raises(ProtocolError):
        runner._parse_junit(path, ("one",), directory, {"one": "passed"})
