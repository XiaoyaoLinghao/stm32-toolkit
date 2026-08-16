"""Real-process tests for the CMake/CTest Host runner."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import time
from xml.etree import ElementTree

import pytest

from stm32_toolkit.evidence import EvidenceIdentity
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.process import ProcessError, ProcessResult
from stm32_toolkit.project_model import HostTestConfig
from stm32_toolkit.testing.artifacts import TestArtifactCollector as ArtifactCollector
from stm32_toolkit.testing.host import HostTestRunner
from stm32_toolkit.testing.model import (
    TestCaseResult as CaseResult,
    TestProtocolError as ProtocolError,
    create_inventory,
    host_target_device,
)


REPO = Path(__file__).resolve().parents[3]
JUNIT = REPO / "tools/stm32-toolkit/tests/release/fixtures/native-outcomes/ctest-4.3.1-junit.xml"
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
output = Path(argv[argv.index("--output-junit") + 1])
output.write_bytes(Path(os.environ["JUNIT_SOURCE"]).read_bytes())
print("ctest stdout")
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
        environment_allow=("SystemRoot", "SCENARIO_DIR", "JUNIT_SOURCE", "TEST_TOKEN"),
        environment_values={
            "SCENARIO_DIR": str(scenario),
            "JUNIT_SOURCE": str(JUNIT),
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
        == {"systemroot", "junit_source", "scenario_dir", "test_token"}
        for call in calls
    )
    assert runner.discovery_artifact is not None
    discovery_object = evidence / runner.discovery_artifact.relative_path
    assert discovery_object.is_file()
    payload = json.loads(discovery_object.read_text(encoding="utf-8"))
    assert payload["kind"] == "ctestInfo"
    assert payload["version"] == {"major": 1, "minor": 0}


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
    assert run_argv[4] == "--output-junit"
    junit_path = Path(run_argv[5])
    assert junit_path.is_absolute()
    assert REPO not in junit_path.parents
    assert manifest.state == "failed"
    assert [(case.case_id, case.state) for case in manifest.cases] == [
        ("native-fail", "failed"), ("native-pass", "passed")
    ]
    assert manifest.transport is None
    assert manifest.stdout is not None and manifest.stderr is not None
    assert (evidence / manifest.stdout.relative_path).read_text(encoding="utf-8") == "ctest stdout\n"
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
    alive = scenario / "child-alive.txt"
    deadline = time.monotonic() + 3
    while not alive.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert alive.exists()
    first = alive.stat().st_size
    time.sleep(0.4)
    assert alive.stat().st_size == first


def test_exit_and_junit_disagreement_is_rejected(task_tmp: Path):
    """A successful exit cannot override a failing native CTest case."""
    runner, config, scenario, _evidence = _runner(task_tmp)
    inventory = runner.discover(config, _identity())
    script = scenario / "fake_tool.py"
    script.write_text(FAKE_TOOL.replace("raise SystemExit(1)", "raise SystemExit(0)"), encoding="utf-8")

    with pytest.raises(ProtocolError) as caught:
        runner.run(inventory, ("native-fail", "native-pass"))

    assert caught.value.code == "TEST_EXIT_MISMATCH"


def test_artifact_collector_rejects_nonexternal_aliases_and_invalid_paths(
    task_tmp: Path, monkeypatch,
):
    """Only new files below the owned external root may become authoritative artifacts."""
    project = task_tmp / "project"
    project.mkdir()
    evidence = EvidenceStore(task_tmp / "evidence")
    with pytest.raises(TypeError):
        ArtifactCollector("results", evidence, project_root=project)
    with pytest.raises(ProtocolError):
        ArtifactCollector(project / "inside", evidence, project_root=project)
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
    with pytest.raises(OSError, match="fsync"):
        collector.write_and_ingest(
            directory, "fsync.txt", b"bytes", kind="test", media_type="text/plain"
        )
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
    with pytest.raises(TypeError):
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
    for selection in (["native-pass"], ("native-pass", "native-pass")):
        with pytest.raises(ProtocolError):
            runner.run(inventory, selection)


def test_junit_parser_maps_all_ctest_terminal_states_outputs_and_incomplete_case(task_tmp: Path):
    """CTest JUnit error/timeout/skipped/output and absent selected cases map without invention."""
    runner, _config, _scenario, evidence = _runner(task_tmp)
    directory = runner._collector.new_directory("junit-states")
    path = runner._collector.output_path(directory, "states.xml")
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<testsuite tests="4" failures="1" errors="1" skipped="1">'
        '<testcase name="error" time="0.001" status="fail"><error message="boom"/></testcase>'
        '<testcase name="timeout" time="0" status="fail"><failure message="Timeout"/></testcase>'
        '<testcase name="skip" time="0" status="notrun"><skipped message="disabled"/></testcase>'
        '<testcase name="pass" time="0" status="run"><system-out>out</system-out><system-err>err</system-err></testcase>'
        '</testsuite>',
        encoding="utf-8",
    )

    cases = runner._parse_junit(
        path, ("error", "timeout", "skip", "pass", "missing"), directory
    )

    assert [(case.case_id, case.state) for case in cases] == [
        ("error", "error"), ("timeout", "timeout"), ("skip", "skipped"),
        ("pass", "passed"), ("missing", "error"),
    ]
    assert cases[0].duration_ms == 1
    assert cases[3].stdout is not None and cases[3].stderr is not None
    assert (evidence / cases[3].stdout.relative_path).read_text(encoding="utf-8") == "out"
    assert cases[4].message == "case ended without a terminal result"


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
        runner._parse_junit(path, ("one",), directory)


def test_junit_duration_summary_and_run_state_boundaries_are_exact():
    """Fractional milliseconds, overflow, absent suites, and state priority stay deterministic."""
    assert HostTestRunner._junit_duration(None) == 0
    for value in ("nan", "-1", "0.0001", str(2**63)):
        with pytest.raises(ProtocolError):
            HostTestRunner._junit_duration(value)
    with pytest.raises(ProtocolError):
        HostTestRunner._validate_junit_summaries(ElementTree.fromstring("<testsuites/>"), [])
    passed = CaseResult("p", "passed", "2026-08-16T00:00:00.000000Z", "2026-08-16T00:00:00.000000Z", 0, None, None, None)
    failed = CaseResult("f", "failed", "2026-08-16T00:00:00.000000Z", "2026-08-16T00:00:00.000000Z", 0, None, None, None)
    error = CaseResult("e", "error", "2026-08-16T00:00:00.000000Z", "2026-08-16T00:00:00.000000Z", 0, None, None, None)
    assert HostTestRunner._run_state((passed,)) == "passed"
    assert HostTestRunner._run_state((failed,)) == "failed"
    assert HostTestRunner._run_state((failed, error)) == "error"
