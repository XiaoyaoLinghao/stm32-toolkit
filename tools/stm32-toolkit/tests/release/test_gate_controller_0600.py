from __future__ import annotations

import copy
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO = Path(__file__).resolve().parents[4]
RELEASE = REPO / "tools" / "release"
sys.path.insert(0, str(RELEASE))

import run_0600_gates as gates  # noqa: E402
from run_0600_gates import (  # noqa: E402
    ControllerError,
    GateRequest,
    GateRunOutput,
    HardwareContractController,
    execute_gate_process,
    main as gates_main,
    prepare_evidence_root,
    run_dev_coverage,
    run_gate_matrix,
    run_performance,
    run_wrapper_contract,
    validate_resource_locks,
    verify_support_root,
)
from verify_0600_release import (  # noqa: E402
    GateCatalog,
    GateFamily,
    VerificationError,
    canonical_json_bytes,
    create_shard_package,
    validate_audit_evidence,
    verify_gate_evidence,
    verify_shard_package,
)


CATALOG = RELEASE / "gates_0600.json"
PATH_HELPER = RELEASE / "path_contract_0600.ps1"
QUICK = RELEASE / "run_0600_quick.ps1"
CANDIDATE = RELEASE / "run_0600_candidate.ps1"
FINAL = RELEASE / "run_0600_final.ps1"
HARDWARE = RELEASE / "run_0600_hardware.ps1"
RUNNER = RELEASE / "run_0600_gates.py"
RUN_ID = "123e4567-e89b-42d3-a456-426614174000"
NOW = datetime(2026, 8, 15, 2, 3, 4, 123456, tzinfo=timezone.utc)


@pytest.fixture
def tmp_path() -> Path:
    """Use the approved external test root; the default user temp ACL is broken on this host."""
    root = Path(tempfile.mkdtemp(prefix="stm32tk-0601-task2-", dir=r"C:\tmp"))
    try:
        yield root
    finally:
        shutil.rmtree(root)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _gate(
    gate_id: str,
    *,
    prerequisites: tuple[str, ...] = (),
    resources: dict[str, str] | None = None,
) -> GateRequest:
    return GateRequest(
        gate_id=gate_id,
        argv=(sys.executable, "-c", "raise SystemExit(0)"),
        cwd=REPO,
        timeout_seconds=30,
        expected_nodes=(f"tests::{gate_id}",),
        prerequisites=prerequisites,
        resource_locks=resources or {},
    )


def test_quick_and_candidate_collect_all_independent_failures() -> None:
    """Returning after one independent failure must not hide the second one."""
    calls: list[str] = []

    def execute(gate: GateRequest, _env: dict[str, str]) -> GateRunOutput:
        calls.append(gate.gate_id)
        node = f"tests::{gate.gate_id}"
        return GateRunOutput(1, b"", gate.gate_id.encode(), (node,), ((node, "failed"),))

    quick = run_gate_matrix("quick", [_gate("A"), _gate("B")], execute=execute)
    candidate = run_gate_matrix(
        "candidate",
        [_gate("C"), _gate("D")],
        execute=execute,
        precheck=lambda _gate: None,
    )

    assert calls == ["A", "B", "C", "D"]
    assert [item.status for item in quick] == ["FAIL", "FAIL"]
    assert [item.status for item in candidate] == ["FAIL", "FAIL"]


def test_candidate_prechecks_each_shard_before_its_first_product_body() -> None:
    """A failed shard precheck must prevent that shard's product executable from starting."""
    events: list[str] = []

    def precheck(gate: GateRequest) -> None:
        events.append(f"pre:{gate.gate_id}")
        if gate.gate_id == "B":
            raise ControllerError("dirty worktree")

    def execute(gate: GateRequest, _env: dict[str, str]) -> GateRunOutput:
        events.append(f"body:{gate.gate_id}")
        node = f"tests::{gate.gate_id}"
        return GateRunOutput(0, b"ok", b"", (node,), ((node, "passed"),))

    results = run_gate_matrix(
        "candidate", [_gate("A"), _gate("B")], execute=execute, precheck=precheck
    )

    assert events == ["pre:A", "body:A", "pre:B"]
    assert [item.status for item in results] == ["PASS", "FAIL"]


def test_gate_postcheck_failure_cannot_leave_a_product_pass() -> None:
    """A worktree mutation observed immediately after a body must convert that gate to FAIL."""
    node = "tests::A"
    results = run_gate_matrix(
        "quick",
        [_gate("A")],
        execute=lambda _gate, _env: GateRunOutput(0, b"ok", b"", (node,), ((node, "passed"),)),
        precheck=lambda _gate: None,
        postcheck=lambda _gate: (_ for _ in ()).throw(ControllerError("dirty after body")),
    )

    assert [(item.status, item.reason) for item in results] == [("FAIL", "POSTCHECK_FAILED")]


def test_final_readiness_runs_no_product_body_and_final_execution_is_fail_fast() -> None:
    """Readiness must stay non-executing and final must stop after its first failed body."""
    bodies: list[str] = []

    def execute(gate: GateRequest, _env: dict[str, str]) -> GateRunOutput:
        bodies.append(gate.gate_id)
        node = f"tests::{gate.gate_id}"
        return GateRunOutput(1, b"", b"failed", (node,), ((node, "failed"),))

    readiness = run_gate_matrix(
        "final-readiness",
        [_gate("READY-A"), _gate("READY-B")],
        execute=execute,
        precheck=lambda _gate: None,
    )
    final = run_gate_matrix(
        "final", [_gate("A"), _gate("B")], execute=execute, precheck=lambda _gate: None
    )

    assert bodies == ["A"]
    assert [item.status for item in readiness] == ["PASS", "PASS"]
    assert [item.status for item in final] == ["FAIL"]


def test_dependency_failure_blocks_dependent_without_marking_it_pass() -> None:
    """A dependent product body must not run after its prerequisite failed."""
    calls: list[str] = []

    def execute(gate: GateRequest, _env: dict[str, str]) -> GateRunOutput:
        calls.append(gate.gate_id)
        exit_code = 1 if gate.gate_id == "A" else 0
        node = f"tests::{gate.gate_id}"
        outcome = "passed" if exit_code == 0 else "failed"
        return GateRunOutput(exit_code, b"", b"", (node,), ((node, outcome),))

    results = run_gate_matrix(
        "quick", [_gate("A"), _gate("B", prerequisites=("A",))], execute=execute
    )

    assert calls == ["A"]
    assert [item.status for item in results] == ["FAIL", "BLOCKED"]


def test_product_framework_has_zero_hidden_retries_and_node_inventory_is_exact() -> None:
    """A product failure or duplicate/deselected node must not trigger an implicit retry."""
    calls = 0

    def execute(gate: GateRequest, env: dict[str, str]) -> GateRunOutput:
        nonlocal calls
        calls += 1
        assert not any(key.startswith(("COVERAGE_", "COV_CORE_")) for key in env)
        assert "PYTEST_ADDOPTS" not in env
        return GateRunOutput(1, b"one", b"failure", ("wrong::node", "wrong::node"), (("wrong::node", "failed"), ("wrong::node", "failed")))

    result = run_gate_matrix("quick", [_gate("A")], execute=execute)[0]

    assert calls == 1
    assert result.status == "FAIL"
    assert result.reason == "NODE_INVENTORY_MISMATCH"


def test_gate_result_emits_bounded_metadata_and_stream_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dropping argv/cwd/timing/CodeHead or stream digests must make evidence incomplete."""
    monkeypatch.setenv("COVERAGE_PROCESS_START", "forbidden")
    monkeypatch.setenv("PYTEST_ADDOPTS", "--cov=stm32_toolkit")

    def execute(gate: GateRequest, env: dict[str, str]) -> GateRunOutput:
        assert "COVERAGE_PROCESS_START" not in env
        assert "PYTEST_ADDOPTS" not in env
        node = f"tests::{gate.gate_id}"
        return GateRunOutput(0, b"hello", b"", (node,), ((node, "passed"),), duration_ms=17)

    result = run_gate_matrix(
        "quick",
        [_gate("A")],
        execute=execute,
        run_id=RUN_ID,
        code_head="a" * 40,
        now=lambda: NOW,
    )[0]

    assert result.status == "PASS"
    assert result.metadata == {
        "architecture": platform.machine(),
        "argv": [sys.executable, "-c", "raise SystemExit(0)"],
        "code_head": "a" * 40,
        "cwd": str(REPO),
        "duration_ms": 17,
        "executable": sys.executable,
        "executable_version": platform.python_version(),
        "exit_code": 0,
        "gate_id": "A",
        "node_outcomes": [{"node_id": "tests::A", "outcome": "passed"}],
        "os": platform.system(),
        "retained_evidence": [],
        "run_id": RUN_ID,
        "seed": "stm32tk-0600:123e4567-e89b-42d3-a456-426614174000:A",
        "started_at_utc": "2026-08-15T02:03:04.123456Z",
        "stderr": {"bytes": 0, "sha256": _sha(b"")},
        "stdout": {"bytes": 5, "sha256": _sha(b"hello")},
        "timed_out": False,
    }


@pytest.mark.parametrize("outcome", ["skipped", "xfailed", "deselected", "unknown"])
def test_gate_matrix_rejects_every_nonexecuted_node_outcome(outcome: str) -> None:
    """A named node is not evidence of execution when its terminal outcome is not pass/fail."""
    node = "tests::A"

    result = run_gate_matrix(
        "quick",
        [_gate("A")],
        execute=lambda gate, env: GateRunOutput(0, b"", b"", (node,), ((node, outcome),)),
    )[0]

    assert result.status == "FAIL"
    assert result.reason == "NODE_OUTCOME_MISMATCH"


def test_real_gate_executor_uses_argv_timeout_and_retains_one_snapshot(tmp_path: Path) -> None:
    """The production executor must parse exact node outcomes and retain its streams/results."""
    script = tmp_path / "fake_gate.py"
    script.write_text(
        "import json\n"
        "print(json.dumps({'schema':'stm32-node-outcome/1','node_id':'tests::one','outcome':'passed'}))\n"
        "print(json.dumps({'schema':'stm32-node-outcome/1','node_id':'tests::two','outcome':'failed'}))\n",
        encoding="utf-8",
    )
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    gate = GateRequest(
        gate_id="REAL",
        argv=(sys.executable, str(script)),
        cwd=tmp_path,
        timeout_seconds=5,
        expected_nodes=("tests::one", "tests::two"),
    )

    output = execute_gate_process(gate, {}, evidence_root=evidence)

    assert output.exit_code == 0
    assert output.node_outcomes == (("tests::one", "passed"), ("tests::two", "failed"))
    assert output.selected_nodes == ("tests::one", "tests::two")
    assert output.duration_ms >= 0
    assert output.timed_out is False
    assert [item["path"] for item in output.retained_evidence] == [
        "REAL/result.json",
        "REAL/stderr.log",
        "REAL/stdout.log",
    ]


def test_real_gate_executor_times_out_and_cleans_up(tmp_path: Path) -> None:
    """A timeout must terminate the child tree and return bounded timeout evidence."""
    script = tmp_path / "slow_gate.py"
    script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    gate = GateRequest("SLOW", (sys.executable, str(script)), tmp_path, 1, ())

    output = execute_gate_process(gate, {}, evidence_root=evidence)

    assert output.timed_out is True
    assert output.exit_code == -1
    assert output.duration_ms >= 1000
    assert output.duration_ms < 10000


def test_resource_lock_conflicts_are_rejected_before_parallel_dispatch() -> None:
    """Two shards must not claim the same host/board/probe/UART/port/evidence resource."""
    first = _gate("A", resources={"probe": "probe-1"})
    second = _gate("B", resources={"probe": "probe-1"})

    with pytest.raises(ControllerError, match="resource lock conflict"):
        validate_resource_locks([first, second])

    validate_resource_locks(
        [_gate("A", resources={"probe": "probe-1"}), _gate("B", resources={"probe": "probe-2"})]
    )


def test_platform_shards_bind_one_logical_final_run_id() -> None:
    """Combining platform results from different finalRunIds must fail."""
    left = run_gate_matrix("final", [_gate("A")], execute=lambda gate, env: GateRunOutput(0, b"", b"", (f"tests::{gate.gate_id}",), ((f"tests::{gate.gate_id}", "passed"),)), precheck=lambda gate: None, run_id=RUN_ID)
    right = run_gate_matrix("final", [_gate("B")], execute=lambda gate, env: GateRunOutput(0, b"", b"", (f"tests::{gate.gate_id}",), ((f"tests::{gate.gate_id}", "passed"),)), precheck=lambda gate: None, run_id="223e4567-e89b-42d3-a456-426614174000")

    with pytest.raises(ControllerError, match="run id"):
        run_gate_matrix.bind_platform_shards([left, right])


@pytest.fixture
def performance_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    test_file = repo / "tools" / "stm32-toolkit" / "tests" / "test_store_performance.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_workload():\n    pass\n", encoding="utf-8")
    return repo, test_file


def test_performance_runner_invokes_entire_file_with_current_interpreter_and_isolated_env(
    performance_repo: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A shell/custom interpreter/partial-node invocation or inherited coverage must fail."""
    repo, test_file = performance_repo
    output = tmp_path / "performance.json"
    monkeypatch.setenv("PYTHONPATH", r"C:\attacker")
    monkeypatch.setenv("PYTEST_PLUGINS", "attacker_plugin")
    monkeypatch.setenv("PYTHONSTARTUP", r"C:\attacker.py")
    def runner(argv: list[str], *, cwd: Path, env: dict[str, str]) -> int:
        assert argv == [sys.executable, "-m", "pytest", str(test_file)]
        assert cwd == repo
        assert "COVERAGE_PROCESS_START" not in env
        assert "PYTHONPATH" not in env
        assert "PYTEST_PLUGINS" not in env
        assert "PYTHONSTARTUP" not in env
        payload = {
            "schema": "stm32-performance-run/1",
            "mode": "calibrate",
            "module": "STM32TK-0601",
            "profile_sha256": None,
            "test_file_sha256": _sha(test_file.read_bytes()),
            "workloads": [],
        }
        output.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        return 0

    result = run_performance(
        repo=repo,
        module="STM32TK-0601",
        test_file=test_file,
        mode="calibrate",
        output=output,
        performance_config=None,
        runner=runner,
    )

    assert result["mode"] == "calibrate"


def test_dev_coverage_cli_requires_the_literal_token_separator(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Without a literal `--`, pytest tokens must never reach the coverage runner."""
    calls: list[list[str]] = []

    def fake_run(
        repo: Path,
        task_id: str,
        evidence_root: Path,
        tokens: list[str],
    ) -> dict[str, object]:
        calls.append(tokens)
        return {"status": "PASS"}

    monkeypatch.setattr("run_0600_gates.run_dev_coverage", fake_run)
    base = [
        "dev-coverage",
        "--task-id", "STM32TK-0601",
        "--evidence-root", str(tmp_path / "evidence"),
    ]

    assert gates_main([*base, "tests/test_a.py"]) == 2
    assert calls == []
    assert gates_main([*base, "--", "tests/test_a.py"]) == 0
    assert calls == [["tests/test_a.py"]]


@pytest.mark.parametrize(
    "change",
    [
        "unknown-module",
        "wrong-name",
        "relative-output",
        "existing-output",
        "coverage-env",
        "shell-token",
    ],
)
def test_performance_runner_rejects_unknown_unsafe_stale_or_coverage_inputs(
    performance_repo: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    """Invalid module/path/digest/output/environment inputs must fail before pytest starts."""
    repo, test_file = performance_repo
    module = "STM32TK-0601"
    output = tmp_path / "result.json"
    runner_calls = 0
    if change == "unknown-module":
        module = "STM32TK-9999"
    elif change == "wrong-name":
        test_file = test_file.with_name("performance.py")
        test_file.write_text("pass\n", encoding="utf-8")
    elif change == "relative-output":
        output = Path("relative.json")
    elif change == "existing-output":
        output.write_text("occupied", encoding="utf-8")
    elif change == "coverage-env":
        monkeypatch.setenv("COVERAGE_PROCESS_START", "configured")
    elif change == "shell-token":
        test_file = test_file.with_name("test_bad;echo_performance.py")
        test_file.write_text("pass\n", encoding="utf-8")

    def runner(*_args: object, **_kwargs: object) -> int:
        nonlocal runner_calls
        runner_calls += 1
        return 0

    with pytest.raises(ControllerError):
        run_performance(repo, module, test_file, "calibrate", output, None, runner=runner)
    assert runner_calls == 0


def test_performance_verify_rejects_stale_workload_and_config_digest(
    performance_repo: tuple[Path, Path], tmp_path: Path
) -> None:
    """Changing the workload file or accepted profile must invalidate verification."""
    repo, test_file = performance_repo
    output = tmp_path / "result.json"
    config = tmp_path / "performance.json"
    config.write_text(
        json.dumps(
            {
                "schema": "stm32-performance-catalog/1",
                "profiles": [
                    {
                        "module": "STM32TK-0601",
                        "test_file": test_file.relative_to(repo).as_posix(),
                        "test_file_sha256": "0" * 64,
                        "profile_sha256": "1" * 64,
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ControllerError, match="digest"):
        run_performance(repo, "STM32TK-0601", test_file, "verify", output, config)


def _coverage_git(paths: list[str]):
    def run(args: list[str]) -> list[str]:
        assert args in (
            ["diff", "--name-only", "--diff-filter=ACMR", "HEAD", "--"],
            ["ls-files", "--others", "--exclude-standard"],
        )
        return paths if args[0] == "diff" else []

    return run


def test_dev_coverage_discovers_each_changed_product_file_and_requires_90_percent(
    tmp_path: Path,
) -> None:
    """Aggregate coverage must not hide an individual changed product file below 90%."""
    repo = tmp_path / "repo"
    product = repo / "tools/stm32-toolkit/src/stm32_toolkit/changed.py"
    test_file = repo / "tools/stm32-toolkit/tests/test_changed.py"
    product.parent.mkdir(parents=True)
    test_file.parent.mkdir(parents=True)
    product.write_text("VALUE = 1\n", encoding="utf-8")
    test_file.write_text("def test_changed(): pass\n", encoding="utf-8")
    evidence = tmp_path / "evidence"
    changed = product.relative_to(repo).as_posix()

    def runner(argv: list[str], *, cwd: Path, env: dict[str, str]) -> int:
        assert argv[:3] == [sys.executable, "-m", "pytest"]
        assert str(test_file) in argv
        assert "--cov=stm32_toolkit.changed" in argv
        assert not any(key.startswith(("COVERAGE_", "COV_CORE_")) for key in env)
        raw = {
            "files": {
                changed: {"summary": {"covered_branches": 9, "num_branches": 10}}
            }
        }
        (evidence / "coverage-raw.json").write_text(json.dumps(raw), encoding="utf-8")
        return 0

    result = run_dev_coverage(
        repo=repo,
        task_id="STM32TK-0601",
        evidence_root=evidence,
        pytest_tokens=[str(test_file), "--cov=stm32_toolkit.changed"],
        git_runner=_coverage_git([changed]),
        runner=runner,
    )

    assert result["files"] == [
        {"covered_branches": 9, "num_branches": 10, "path": changed, "percent": 90}
    ]
    assert (evidence / "branch-coverage.json").is_file()


@pytest.mark.parametrize(
    ("paths", "rows", "tokens"),
    [
        ([], {}, ["tests/test_changed.py"]),
        (["tools/stm32-toolkit/src/stm32_toolkit/a.py", "tools/stm32-toolkit/src/stm32_toolkit/A.py"], {}, ["tests/test_changed.py"]),
        (["tools/stm32-toolkit/src/stm32_toolkit/a.py"], {}, ["tests/test_changed.py"]),
        (["tools/stm32-toolkit/src/stm32_toolkit/a.py"], {"tools/stm32-toolkit/src/stm32_toolkit/b.py": (9, 10)}, ["tests/test_changed.py"]),
        (["tools/stm32-toolkit/src/stm32_toolkit/a.py"], {"tools/stm32-toolkit/src/stm32_toolkit/a.py": (8, 10)}, ["tests/test_changed.py"]),
        (["tools/stm32-toolkit/src/stm32_toolkit/a.py"], {"tools/stm32-toolkit/src/stm32_toolkit/a.py": (9, 10)}, ["tests/test_changed.py", ";", "echo"]),
    ],
)
def test_dev_coverage_rejects_no_change_duplicates_missing_rows_low_file_and_shell_tokens(
    tmp_path: Path, paths: list[str], rows: dict[str, tuple[int, int]], tokens: list[str]
) -> None:
    """Every changed product file needs one safe, integer, per-file branch row at >=90%."""
    repo = tmp_path / "repo"
    repo.mkdir()
    for path in paths:
        target = repo.joinpath(*path.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("pass\n", encoding="utf-8")
    evidence = tmp_path / "evidence"

    def runner(_argv: list[str], *, cwd: Path, env: dict[str, str]) -> int:
        raw = {
            "files": {
                path: {"summary": {"covered_branches": covered, "num_branches": total}}
                for path, (covered, total) in rows.items()
            }
        }
        (evidence / "coverage-raw.json").write_text(json.dumps(raw), encoding="utf-8")
        return 0

    with pytest.raises(ControllerError):
        run_dev_coverage(repo, "STM32TK-0601", evidence, tokens, _coverage_git(paths), runner)


def test_dev_coverage_rejects_duplicate_json_object_rows(tmp_path: Path) -> None:
    """Two literal JSON rows for one changed path must not collapse into one accepted row."""
    repo = tmp_path / "repo"
    changed = "tools/stm32-toolkit/src/stm32_toolkit/a.py"
    target = repo.joinpath(*changed.split("/"))
    target.parent.mkdir(parents=True)
    target.write_text("pass\n", encoding="utf-8")
    test_file = repo / "tools" / "stm32-toolkit" / "tests" / "test_a.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_a(): pass\n", encoding="utf-8")
    evidence = tmp_path / "evidence"

    def runner(_argv: list[str], *, cwd: Path, env: dict[str, str]) -> int:
        duplicate = (
            '{"files":{"' + changed + '":{"summary":{"covered_branches":9,"num_branches":10}},'
            '"' + changed + '":{"summary":{"covered_branches":9,"num_branches":10}}}}'
        )
        (evidence / "coverage-raw.json").write_text(duplicate, encoding="utf-8")
        return 0

    with pytest.raises(ControllerError):
        run_dev_coverage(
            repo,
            "STM32TK-0601",
            evidence,
            [str(test_file), "--cov=stm32_toolkit.a"],
            _coverage_git([changed]),
            runner,
        )


def _write_support(root: Path) -> Path:
    def write(relative: str, value: object | bytes) -> Path:
        path = root.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        data = value if isinstance(value, bytes) else (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
        path.write_bytes(data)
        return path

    versions = {
        "cmake": "4.3.1", "ctest": "4.3.1", "node": "24.18.0", "npm": "11.16.0",
        "powershell": "5.1.26100.9168", "pyocd": "0.45.1", "pyserial": "3.5",
        "python310": "3.10.11", "python312": "3.12.10", "wheelhouse": "offline-wheelhouse/1",
    }
    tools: dict[str, object] = {}
    for name, version in versions.items():
        relative = f"tools/{name}.json"
        tools[name] = {"record": relative, "version": version}
        if name == "wheelhouse":
            record = {"schema": "stm32tk-0600-tool-record/1", "name": name, "version": version, "path": "wheelhouse"}
        elif name in {"pyocd", "pyserial"}:
            record = {"schema": "stm32tk-0600-tool-record/1", "name": name, "version": version, "python": r"C:\fixture\python.exe"}
        else:
            record = {"schema": "stm32tk-0600-tool-record/1", "name": name, "version": version, "executable": rf"C:\fixture\{name}.exe"}
        write(relative, record)
    write("wheelhouse/package.whl", b"wheel")
    executable = write("chromium/chrome-win/chrome.exe", b"fake chromium executable")
    version_manifest = write(
        "chromium/chrome-win/141.0.7390.37.manifest",
        b'<assembly><assemblyIdentity version="141.0.7390.37"/></assembly>',
    )
    blank = write("feasibility/blank.html", b"<!doctype html><title>blank</title>\n")
    seed_value = {
        "schema": "stm32tk-0600-managed-chromium-profile-seed/1",
        "id": "stm32tk-0600-feasibility",
        "local_state": '{"profile":{"exit_type":"Normal"}}\n',
    }
    seed = write("feasibility/chromium-profile-seed.json", seed_value)
    firmware = write("firmware/feasibility.bin", b"firmware fixture")
    local_state = seed_value["local_state"].encode()

    package_members = []
    for path in sorted((root / "chromium/chrome-win").iterdir(), key=lambda item: item.name):
        data = path.read_bytes()
        package_members.append({"path": path.relative_to(root).as_posix(), "bytes": len(data), "sha256": _sha(data)})
    package_digest = _sha(json.dumps(package_members, sort_keys=True, separators=(",", ":")).encode())
    profile_value = {
        "schema": "stm32tk-0600-feasibility-profile/1",
        "windows_owner": "Codex",
        "host": {
            "platform": "Windows", "architecture": "AMD64", "host_id": "1" * 64,
            "windows_version": {"release": "11", "version": "10.0.26200", "build": "26200"},
        },
        "tools": tools,
        "chromium": {
            "executable": executable.relative_to(root).as_posix(), "executable_sha256": _sha(executable.read_bytes()),
            "version": "141.0.7390.37", "package_root": "chromium/chrome-win", "package_tree_sha256": package_digest,
            "managed_profile": {
                "id": "stm32tk-0600-feasibility", "seed": seed.relative_to(root).as_posix(), "sha256": _sha(seed.read_bytes()),
                "files": [{"path": "Local State", "bytes": len(local_state), "sha256": _sha(local_state)}],
            },
            "version_evidence": {"path": version_manifest.relative_to(root).as_posix(), "sha256": _sha(version_manifest.read_bytes())},
            "blank_page": {"path": blank.relative_to(root).as_posix(), "sha256": _sha(blank.read_bytes())},
        },
        "firmware_fixture": {"path": firmware.relative_to(root).as_posix(), "bytes": len(firmware.read_bytes()), "sha256": _sha(firmware.read_bytes())},
        "capabilities": {
            "ram": [{"start": 536870912, "size": 32768}],
            "mailbox": {"address": 536870912, "size": 4096},
            "rtt": {"channel": 0}, "uart": {"port": "COM7", "baud": 115200},
            "semihosting": {"declared": True},
        },
    }
    profile = write("feasibility/profile.json", profile_value)
    members = []
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.relative_to(root).as_posix()):
        data = path.read_bytes()
        members.append({"path": path.relative_to(root).as_posix(), "bytes": len(data), "sha256": _sha(data)})
    manifest = {"schema": "stm32tk-0600-support-manifest/1", "files": members}
    write("support-manifest.json", manifest)
    return profile


def test_support_root_is_exactly_manifest_bound_and_reread_unchanged(tmp_path: Path) -> None:
    """A support declaration must not replace exact path/size/hash and final reread checks."""
    profile = _write_support(tmp_path / "support")

    result = verify_support_root(profile)

    assert result["profile"]["path"] == "feasibility/profile.json"
    assert result["profile"]["bytes"] == len(profile.read_bytes())
    assert result["manifest"]["sha256"] == _sha((profile.parents[1] / "support-manifest.json").read_bytes())


@pytest.mark.parametrize("mutation", ["missing", "extra", "casefold", "hash", "link", "reread"])
def test_support_root_rejects_missing_extra_alias_link_hash_and_mutation(
    tmp_path: Path, mutation: str
) -> None:
    """Support caches must be complete, immutable, regular, and identity-unique."""
    root = tmp_path / "support"
    profile = _write_support(root)
    before_reread = None
    if mutation == "missing":
        (root / "tools/python312.json").unlink()
    elif mutation == "extra":
        (root / "extra.txt").write_text("extra", encoding="utf-8")
    elif mutation == "casefold":
        manifest_path = root / "support-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        alias = copy.deepcopy(manifest["files"][1])
        alias["path"] = "TOOLS/PYTHON312.JSON"
        manifest["files"].append(alias)
        manifest_path.write_bytes(
            (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
        )
    elif mutation == "hash":
        (root / "tools/python312.json").write_text("mutated", encoding="utf-8")
    elif mutation == "link":
        target = root / "wheelhouse"
        (target / "package.whl").unlink()
        target.rmdir()
        created = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                f"New-Item -ItemType Junction -Path '{target}' -Target '{root / 'feasibility'}' | Out-Null",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert created.returncode == 0, created.stderr
    else:
        before_reread = lambda: (root / "wheelhouse/package.whl").write_bytes(b"changed")

    with pytest.raises(ControllerError):
        verify_support_root(profile, before_reread=before_reread)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("schema", "fixture"),
        ("windows_owner", "user"),
        ("capabilities", {}),
        ("tools", {}),
        ("chromium", {}),
    ],
)
def test_support_profile_requires_task1_feasibility_contract(
    tmp_path: Path, field: str, replacement: object
) -> None:
    """A manifest-bound file is not support evidence unless Task 1 accepts its full profile."""
    root = tmp_path / "support"
    profile = _write_support(root)
    value = json.loads(profile.read_text(encoding="utf-8"))
    value[field] = replacement
    profile.write_bytes((json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode())
    manifest_path = root / "support-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = next(item for item in manifest["files"] if item["path"] == "feasibility/profile.json")
    entry["bytes"] = len(profile.read_bytes())
    entry["sha256"] = _sha(profile.read_bytes())
    manifest_path.write_bytes((json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode())

    with pytest.raises(ControllerError):
        verify_support_root(profile)


def test_support_profile_binds_tool_record_and_managed_chromium_proof(tmp_path: Path) -> None:
    """A profile-declared tool/version or browser proof must agree with retained support bytes."""
    root = tmp_path / "support"
    profile = _write_support(root)
    record = root / "tools/python312.json"
    value = json.loads(record.read_text(encoding="utf-8"))
    value["version"] = "3.12.9"
    record.write_bytes((json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode())
    manifest_path = root / "support-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = next(item for item in manifest["files"] if item["path"] == "tools/python312.json")
    entry["bytes"] = len(record.read_bytes())
    entry["sha256"] = _sha(record.read_bytes())
    manifest_path.write_bytes((json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode())

    with pytest.raises(ControllerError):
        verify_support_root(profile)


def test_evidence_root_must_be_new_absolute_and_then_stays_unique(tmp_path: Path) -> None:
    """Relative, existing, or reused evidence roots must never mix gate runs."""
    root = tmp_path / "evidence"
    prepared = prepare_evidence_root(root)

    assert prepared == root
    assert list(root.iterdir()) == []
    with pytest.raises(ControllerError):
        prepare_evidence_root(root)
    with pytest.raises(ControllerError):
        prepare_evidence_root(Path("relative-evidence"))


def test_retained_gate_evidence_requires_every_exact_file_byte_and_digest(tmp_path: Path) -> None:
    """A missing or changed log/result/screenshot/coverage/wheel must invalidate evidence."""
    names = ["gate.log", "result.json", "screen.png", "coverage.json", "package.whl"]
    refs = []
    for index, name in enumerate(names):
        data = f"file-{index}".encode()
        (tmp_path / name).write_bytes(data)
        refs.append({"path": name, "bytes": len(data), "sha256": _sha(data)})

    verify_gate_evidence(tmp_path, refs, expected_paths=names)
    (tmp_path / "coverage.json").write_bytes(b"changed")

    with pytest.raises(VerificationError):
        verify_gate_evidence(tmp_path, refs, expected_paths=names)


def test_gate_evidence_rejects_empty_incomplete_and_extra_inventories(tmp_path: Path) -> None:
    """Caller-selected empty references or unlisted root files cannot prove catalog evidence."""
    required = tmp_path / "result.json"
    required.write_bytes(b"result")
    reference = {"path": "result.json", "bytes": 6, "sha256": _sha(b"result")}

    with pytest.raises(VerificationError):
        verify_gate_evidence(tmp_path, [], expected_paths=["result.json"])
    with pytest.raises(VerificationError):
        verify_gate_evidence(tmp_path, [reference], expected_paths=[])
    (tmp_path / "extra.log").write_bytes(b"extra")
    with pytest.raises(VerificationError):
        verify_gate_evidence(tmp_path, [reference], expected_paths=["result.json"])


def _package_binding() -> dict[str, object]:
    return {
        "owner": "Codex",
        "platform": "windows-amd64",
        "run_id": RUN_ID,
        "code_head": "a" * 40,
        "catalog_sha256": "b" * 64,
        "locks": ["evidence-root:shard-A", "performance-host:host-A"],
        "support_sha256": "c" * 64,
        "status": "PASS",
    }


def test_local_shard_package_is_deterministic_sorted_and_fixed_metadata(tmp_path: Path) -> None:
    """Filesystem order, timestamps, permissions, or compression must not change a shard ZIP."""
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "z.log").write_bytes(b"z")
    (evidence / "a.json").write_bytes(b"{}\n")
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    first_ref = create_shard_package(evidence, first, _package_binding())
    second_ref = create_shard_package(evidence, second, _package_binding())

    assert first.read_bytes() == second.read_bytes()
    assert first_ref["bytes"] == len(first.read_bytes())
    assert first_ref["sha256"] == _sha(first.read_bytes())
    with zipfile.ZipFile(first) as archive:
        assert archive.namelist() == ["a.json", "shard-manifest.json", "z.log"]
        for info in archive.infolist():
            assert info.date_time == (1980, 1, 1, 0, 0, 0)
            assert info.create_system == 3
            assert info.external_attr == 0o100444 << 16
    verify_shard_package(first, first_ref, _package_binding())


def test_shard_verifier_rejects_package_mutation_between_snapshot_and_final_reread(
    tmp_path: Path,
) -> None:
    """Package verification must bind one byte snapshot and prove the path stayed unchanged."""
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "result.json").write_bytes(b"result")
    package = tmp_path / "shard.zip"
    binding = _package_binding()
    reference = create_shard_package(evidence, package, binding)

    with pytest.raises(VerificationError):
        verify_shard_package(
            package,
            reference,
            binding,
            before_final_reread=lambda: package.write_bytes(package.read_bytes() + b"changed"),
        )


@pytest.mark.parametrize("mutation", ["bytes", "binding", "extra", "traversal", "casefold", "absolute"])
def test_shard_verifier_rejects_archive_manifest_and_private_path_discrepancies(
    tmp_path: Path, mutation: str
) -> None:
    """Archive bytes, inner manifest, closed bindings, and safe member names must all agree."""
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "result.json").write_bytes(b"{}\n")
    package = tmp_path / "shard.zip"
    reference = create_shard_package(evidence, package, _package_binding())
    binding = _package_binding()
    if mutation == "bytes":
        package.write_bytes(package.read_bytes() + b"x")
    elif mutation == "binding":
        binding["run_id"] = "223e4567-e89b-42d3-a456-426614174000"
    else:
        members = {
            info.filename: zipfile.ZipFile(package).read(info.filename)
            for info in zipfile.ZipFile(package).infolist()
        }
        name = {
            "extra": "extra.txt",
            "traversal": "../escape.txt",
            "casefold": "RESULT.JSON",
            "absolute": "C:/Users/private/secret.txt",
        }[mutation]
        members[name] = b"x"
        with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_STORED) as archive:
            for member_name, data in sorted(members.items()):
                archive.writestr(member_name, data)
        reference = {"path": str(package), "bytes": len(package.read_bytes()), "sha256": _sha(package.read_bytes())}

    with pytest.raises(VerificationError):
        verify_shard_package(package, reference, binding)


def _audit(now: datetime = NOW) -> dict[str, object]:
    return {
        "schema": "stm32-offline-audit/1",
        "network": False,
        "advisory": {
            "source": "npm-advisory-snapshot",
            "database_version": "2026-08-14",
            "generated_at_utc": "2026-08-14T00:00:00.000000Z",
            "sha256": "a" * 64,
        },
        "cache_sha256": "b" * 64,
        "production": {"critical": 0, "high": 0, "moderate": 0, "low": 0},
        "development": {"critical": 0, "high": 0, "moderate": 3, "low": 4},
        "exceptions": [],
    }


def test_offline_audit_policy_accepts_only_pinned_fresh_zero_blocker_evidence() -> None:
    """Pinned offline evidence with zero production and zero dev high/critical is releasable."""
    validate_audit_evidence(_audit(), readiness_at=NOW, candidate_started_at=NOW)


@pytest.mark.parametrize("mutation", ["network", "stale", "prod", "dev", "late-exception", "expired", "extra"])
def test_audit_policy_rejects_network_stale_vulnerable_late_or_open_evidence(mutation: str) -> None:
    """Network output and policy-violating/late/expired exceptions cannot become release evidence."""
    value = _audit()
    if mutation == "network":
        value["network"] = True
    elif mutation == "stale":
        value["advisory"]["generated_at_utc"] = "2026-08-01T00:00:00.000000Z"
    elif mutation == "prod":
        value["production"]["low"] = 1
    elif mutation == "dev":
        value["development"]["high"] = 1
    elif mutation in {"late-exception", "expired"}:
        value["exceptions"] = [
            {
                "package": "fixture",
                "advisory_id": "ADV-1",
                "reachability": "unreachable",
                "approved_by": "user",
                "approved_at_utc": "2026-08-15T03:00:00.000000Z" if mutation == "late-exception" else "2026-08-01T00:00:00.000000Z",
                "expires_at_utc": "2026-08-20T00:00:00.000000Z" if mutation == "late-exception" else "2026-08-14T00:00:00.000000Z",
                "mitigation": "not imported by production",
            }
        ]
    else:
        value["advisory"]["extra"] = None

    with pytest.raises(VerificationError):
        validate_audit_evidence(value, readiness_at=NOW, candidate_started_at=NOW)


@dataclass
class FakeHardwareBackend:
    snapshot: dict[str, str]
    prepare_calls: list[str]
    observe_calls: list[str]
    execute_calls: list[str]
    fail_action: str | None = None
    artifacts: list[dict[str, object]] | None = None

    def prepare(self, action_id: str) -> dict[str, object]:
        self.prepare_calls.append(action_id)
        return {
            "snapshot": copy.deepcopy(self.snapshot),
            "counters": {
                "identity_state_read": 1,
                "control": 0,
                "modify": 0,
                "reset": 0,
                "halt": 0,
                "write": 0,
                "flash": 0,
            },
        }

    def observe(self, action_id: str) -> dict[str, str]:
        self.observe_calls.append(action_id)
        return copy.deepcopy(self.snapshot)

    def execute(self, action_id: str) -> dict[str, object]:
        self.execute_calls.append(action_id)
        return {"status": "FAIL" if action_id == self.fail_action else "PASS", "artifacts": self.artifacts or []}


class HardwareGit:
    def __init__(self, *, dirty: str = "", head: str = "b" * 40) -> None:
        self.dirty = dirty
        self.head = head

    def __call__(self, args: list[str]) -> str:
        if args == ["rev-parse", "HEAD"]:
            return self.head + "\n"
        if args == ["config", "--get", "remote.origin.url"]:
            return "https://github.com/XiaoyaoLinghao/stm32-toolkit.git\n"
        if args == ["status", "--porcelain=v1", "--untracked-files=all"]:
            return self.dirty
        if args[:2] == ["hash-object", "--"] or (args[0] == "rev-parse" and ":" in args[1]):
            return "d" * 40 + "\n"
        raise AssertionError(args)


def _hardware(
    tmp_path: Path,
    contract: str = "0600",
    *,
    backend: FakeHardwareBackend | None = None,
    tested: str | None = None,
    git: HardwareGit | None = None,
) -> tuple[HardwareContractController, FakeHardwareBackend]:
    fake = backend or FakeHardwareBackend(
        {
            "board_id": "board-A", "probe_serial_hash": "a" * 64,
            "uart_serial_hash": "c" * 64, "power_identity": "bench-A", "state": "running",
        },
        [],
        [],
        [],
    )
    random_calls = 0

    def random_bytes(count: int) -> bytes:
        nonlocal random_calls
        value = bytes((index + random_calls) % 256 for index in range(count))
        random_calls += 1
        return value

    support_profile = _write_support(tmp_path / f"support-{contract}")
    controller = HardwareContractController(
        contract=contract,
        repo=REPO,
        catalog=CATALOG,
        expected_code_head=tested or "a" * 40,
        controller_code_head="b" * 40,
        final_run_id=RUN_ID,
        evidence_root=tmp_path / f"hardware-{contract}",
        backend=fake,
        support_profile=support_profile,
        hardware_identity={
            "board_id": "board-A", "probe_serial_hash": "a" * 64,
            "uart_serial_hash": "c" * 64, "power_identity": "bench-A",
        },
        git_runner=git or HardwareGit(),
        now=lambda: NOW,
        random_bytes=random_bytes,
    )
    return controller, fake


def test_hardware_rejects_dirty_worktree_and_nonfixed_catalog_before_prepare(
    tmp_path: Path,
) -> None:
    """No product prepare API may run from a dirty worktree or caller-selected catalog path."""
    controller, backend = _hardware(tmp_path, git=HardwareGit(dirty="?? attacker.py\n"))
    with pytest.raises(ControllerError, match="worktree"):
        controller.prepare()
    assert backend.prepare_calls == []

    alias = tmp_path / "catalog.json"
    alias.write_bytes(CATALOG.read_bytes())
    with pytest.raises(ControllerError, match="fixed catalog"):
        HardwareContractController(
            contract="0600", repo=REPO, catalog=alias,
            expected_code_head="a" * 40, controller_code_head="b" * 40,
            final_run_id=RUN_ID, evidence_root=tmp_path / "bad-catalog",
            backend=backend, support_profile=controller.support_profile,
            hardware_identity=controller.hardware_identity, git_runner=HardwareGit(),
        )


def test_hardware_checkpoint_is_recursive_and_action_digest_is_recomputed(tmp_path: Path) -> None:
    """Editing retained prepared state cannot create a new authorization accepted by execute."""
    controller, backend = _hardware(tmp_path)
    prepared = controller.prepare()
    checkpoint = json.loads(controller.checkpoint_path.read_text(encoding="utf-8"))
    checkpoint["prepared"]["action_digest"] = "f" * 64
    controller.checkpoint_path.write_bytes(canonical_json_bytes(checkpoint))

    with pytest.raises(ControllerError, match="digest|checkpoint"):
        controller.execute(prepared["nonce"], "f" * 64, authorized=True)
    assert backend.execute_calls == []


@pytest.mark.parametrize(
    "mutation",
    [
        "root-extra", "action-extra", "action-state-bool", "nonce-duplicate",
        "history-extra", "summary-extra", "counter-bool", "complete-integer",
        "resource-extra",
    ],
)
def test_hardware_checkpoint_rejects_mutation_at_every_nested_boundary(
    tmp_path: Path, mutation: str
) -> None:
    """All retained checkpoint objects and exact JSON scalar types are recursively closed."""
    controller, backend = _hardware(tmp_path)
    prepared = controller.prepare()
    value = json.loads(controller.checkpoint_path.read_text(encoding="utf-8"))
    if mutation == "root-extra":
        value["extra"] = None
    elif mutation == "action-extra":
        value["actions"][0]["extra"] = None
    elif mutation == "action-state-bool":
        value["actions"][0]["state"] = False
    elif mutation == "nonce-duplicate":
        value["used_nonces"].append(value["used_nonces"][0])
    elif mutation == "history-extra":
        value["recovery_history"] = [{"record_sha256": "e" * 64, "event": "TARGET_POWER_LOSS", "action": value["actions"][0]["id"], "extra": None}]
    elif mutation == "summary-extra":
        value["prepared"]["summary"]["extra"] = None
    elif mutation == "counter-bool":
        value["prepared"]["counters"]["control"] = False
    elif mutation == "complete-integer":
        value["contract_complete"] = 0
    else:
        value["resource_locks"]["extra"] = "x"
    controller.checkpoint_path.write_bytes(canonical_json_bytes(value))

    with pytest.raises(ControllerError, match="checkpoint|action|nonce|recovery|prepared|completion|binding"):
        controller.execute(prepared["nonce"], prepared["action_digest"], authorized=True)
    assert backend.execute_calls == []


def test_hardware_identity_and_artifact_dual_codehead_bindings_are_mandatory(
    tmp_path: Path,
) -> None:
    """Identity drift and artifacts without both CodeHeads must fail before evidence acceptance."""
    controller, backend = _hardware(tmp_path)
    backend.snapshot["board_id"] = "different-board"
    with pytest.raises(ControllerError, match="hardware identity"):
        controller.prepare()
    assert backend.execute_calls == []

    controller, backend = _hardware(tmp_path / "second")
    backend.artifacts = [{"path": "raw-events.json", "sha256": "e" * 64}]
    prepared = controller.prepare()
    with pytest.raises(ControllerError, match="artifact"):
        controller.execute(prepared["nonce"], prepared["action_digest"], authorized=True)


def test_hardware_contracts_use_exact_separate_dispatch_sets(tmp_path: Path) -> None:
    """A 0400/0600 gate mix-up must fail before any hardware body."""
    old, _ = _hardware(tmp_path, "0400")
    new, _ = _hardware(tmp_path, "0600")

    assert old.action_ids == (
        "STM32TK-HW-0400-PROBE-ATTACH-READ",
        "STM32TK-HW-0400-FLASH-READBACK",
        "STM32TK-HW-0400-HANDOFF-REACQUIRE",
        "STM32TK-HW-0400-TYPED-READ-SAMPLE-FAULT",
        "STM32TK-HW-0400-CLI-MCP-WORKFLOWS",
    )
    assert new.action_ids == (
        "STM32TK-HW-0600-MAILBOX",
        "STM32TK-HW-0600-RTT",
        "STM32TK-HW-0600-UART",
        "STM32TK-HW-0600-SEMIHOSTING",
        "STM32TK-HW-0600-DIAGNOSTIC-CHAIN",
    )


def test_prepare_performs_one_observe_only_snapshot_and_emits_exact_authorization(tmp_path: Path) -> None:
    """Prepare must not execute/control/modify or authorize more than the next pending action."""
    controller, backend = _hardware(tmp_path)

    prepared = controller.prepare()
    checkpoint = json.loads(Path(prepared["checkpoint"]).read_text(encoding="utf-8"))

    assert set(prepared) == {"nonce", "action_digest", "expires_at_utc", "checkpoint"}
    assert prepared["nonce"] == "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
    assert re.fullmatch(r"[0-9a-f]{64}", prepared["action_digest"])
    assert prepared["expires_at_utc"] == "2026-08-15T02:18:04.123456Z"
    assert backend.prepare_calls == [controller.action_ids[0]]
    assert backend.observe_calls == []
    assert backend.execute_calls == []
    assert checkpoint["prepared"]["counters"] == {
        "identity_state_read": 1,
        "control": 0,
        "modify": 0,
        "reset": 0,
        "halt": 0,
        "write": 0,
        "flash": 0,
    }
    assert checkpoint["actions"][1]["state"] == "pending"
    assert checkpoint["controller_code_head"] == "b" * 40
    assert checkpoint["tested_code_head"] == "a" * 40


def test_execute_refuses_changed_identity_before_control_and_consumes_one_action(tmp_path: Path) -> None:
    """A changed snapshot must prevent CONTROL/MODIFY; a stable one executes exactly one action."""
    controller, backend = _hardware(tmp_path)
    prepared = controller.prepare()
    backend.snapshot["state"] = "halted"

    with pytest.raises(ControllerError, match="identity/state changed"):
        controller.execute(prepared["nonce"], prepared["action_digest"], authorized=True)
    assert backend.execute_calls == []

    backend.snapshot["state"] = "running"
    replacement = controller.prepare()
    result = controller.execute(
        replacement["nonce"], replacement["action_digest"], authorized=True
    )

    assert result["status"] == "PASS"
    assert backend.execute_calls == [controller.action_ids[0]]
    checkpoint = json.loads(controller.checkpoint_path.read_text(encoding="utf-8"))
    assert checkpoint["actions"][0]["state"] == "passed"
    assert checkpoint["actions"][1]["state"] == "pending"
    assert checkpoint["prepared"] is None
    assert result["controller_code_head"] == "b" * 40
    assert result["tested_code_head"] == "a" * 40


def test_authorization_is_single_use_and_next_action_requires_new_prepare(tmp_path: Path) -> None:
    """Consumed authorization must not replay or pre-authorize the next action."""
    controller, backend = _hardware(tmp_path)
    prepared = controller.prepare()
    controller.execute(prepared["nonce"], prepared["action_digest"], authorized=True)

    with pytest.raises(ControllerError):
        controller.execute(prepared["nonce"], prepared["action_digest"], authorized=True)
    assert backend.execute_calls == [controller.action_ids[0]]
    next_prepared = controller.prepare()
    assert next_prepared["nonce"] != prepared["nonce"]
    assert backend.prepare_calls == [controller.action_ids[0], controller.action_ids[1]]


def test_0400_rejects_controller_sha_substituted_for_tested_product_sha(tmp_path: Path) -> None:
    """The 0.6 controller commit must not masquerade as the product SHA tested for 0.4."""
    with pytest.raises(ControllerError, match="distinct tested product"):
        _hardware(tmp_path, "0400", tested="b" * 40)


def test_failed_hardware_action_is_isolated_and_no_later_action_runs(tmp_path: Path) -> None:
    """One terminal action failure must not execute or authorize later hardware actions."""
    controller, backend = _hardware(tmp_path)
    backend.fail_action = controller.action_ids[0]
    prepared = controller.prepare()

    result = controller.execute(prepared["nonce"], prepared["action_digest"], authorized=True)

    assert result["status"] == "FAIL"
    assert backend.execute_calls == [controller.action_ids[0]]
    with pytest.raises(ControllerError, match="terminal failure"):
        controller.prepare()


def test_hardware_resume_requires_program_recovery_record_and_fresh_authorization(
    tmp_path: Path,
) -> None:
    """A recoverable interruption must be recorded once and cannot replay the prepared action."""
    controller, backend = _hardware(tmp_path)
    prepared = controller.prepare()
    checkpoint = Path(prepared["checkpoint"])
    retained_digest = _sha(checkpoint.read_bytes())
    record = {
        "checkpoint": str(checkpoint),
        "classification": "RECOVERABLE_INFRA_ERROR",
        "code_head": "a" * 40,
        "event": "TARGET_POWER_LOSS",
        "interrupted_attempt_digest": retained_digest,
        "recorded_at_utc": "2026-08-15T02:04:04.123456Z",
        "reviewer": "Codex",
        "run_id": RUN_ID,
        "run_kind": "hardware-0600",
    }
    recovery = tmp_path / "recovery.json"
    recovery.write_bytes(
        (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    )

    resumed = controller.resume(checkpoint, recovery)

    assert resumed == {"action": controller.action_ids[0], "status": "FRESH_PREPARE_REQUIRED"}
    assert backend.execute_calls == []
    replacement = controller.prepare()
    assert replacement["nonce"] != prepared["nonce"]
    with pytest.raises(ControllerError, match="single-resume"):
        controller.resume(checkpoint, recovery)


@pytest.mark.parametrize("change", ["missing-auth", "expired", "wrong-nonce", "wrong-digest"])
def test_hardware_execute_rejects_missing_expired_or_mismatched_authorization(
    tmp_path: Path, change: str
) -> None:
    """Only the exact, unexpired, explicitly authorized prepared action may execute."""
    controller, backend = _hardware(tmp_path)
    prepared = controller.prepare()
    nonce = prepared["nonce"]
    digest = prepared["action_digest"]
    authorized = True
    if change == "missing-auth":
        authorized = False
    elif change == "expired":
        controller.now = lambda: datetime(2026, 8, 15, 3, 0, tzinfo=timezone.utc)
    elif change == "wrong-nonce":
        nonce = "f" * 64
    else:
        digest = "f" * 64

    with pytest.raises(ControllerError):
        controller.execute(nonce, digest, authorized=authorized)
    assert backend.execute_calls == []


def _run_powershell(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "path",
    [
        r"C:\tmp\nonexistent\output.json",
        r"\\server\share\nonexistent\output.json",
    ],
)
def test_powershell_51_path_contract_accepts_canonical_absolute_nonexistent_paths(path: str) -> None:
    """The shared helper must canonicalize without requiring the output to exist."""
    escaped = path.replace("'", "''")
    command = f". '{PATH_HELPER}'; ConvertTo-CanonicalAbsolutePath -Path '{escaped}' -Name 'Output'"
    completed = _run_powershell(command)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == path


@pytest.mark.parametrize(
    "path",
    [
        "",
        "relative\\file.json",
        "C:file.json",
        r"\root-relative.json",
        "/root-relative.json",
        r"\\?\C:\tmp\x",
        r"\\.\C:\tmp\x",
        r"\??\C:\tmp\x",
        r"C:\tmp\.\x",
        r"C:\tmp\part\..\x",
        "C:/tmp/mixed\\x",
        "C:\\tmp\\trailing\\",
    ],
)
def test_powershell_51_path_contract_rejects_relative_alias_and_normalization_paths(path: str) -> None:
    """Every alternate spelling must fail instead of aliasing a release path."""
    escaped = path.replace("'", "''")
    command = f". '{PATH_HELPER}'; ConvertTo-CanonicalAbsolutePath -Path '{escaped}' -Name 'Output'"
    completed = _run_powershell(command)

    assert completed.returncode != 0
    assert completed.stdout == ""


def test_all_software_wrappers_expose_closed_base_interface_and_reject_legacy_resume() -> None:
    """Unknown switches and the legacy ResumeRun spelling must be rejected by PowerShell binding."""
    expected_base = {
        "Matrix",
        "Module",
        "Shard",
        "RunId",
        "EvidenceRoot",
        "ExpectedCodeHead",
        "GateCatalog",
        "PerformanceCatalog",
        "SupportProfile",
        "ContractSelfTest",
    }
    for wrapper in (QUICK, CANDIDATE, FINAL):
        command = f"(Get-Command '{wrapper}').Parameters.Keys | ConvertTo-Json -Compress"
        completed = _run_powershell(command)
        assert completed.returncode == 0, completed.stderr
        parameters = set(json.loads(completed.stdout))
        assert expected_base <= parameters
        rejected = subprocess.run(
            ["powershell.exe", "-NoProfile", "-File", str(wrapper), "-ResumeRun"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert rejected.returncode != 0


def test_candidate_has_only_closed_resume_interface_and_context_cannot_supply_paths() -> None:
    """Candidate resume must require its authoritative ledger and separate recovery record."""
    completed = _run_powershell(
        f"(Get-Command '{CANDIDATE}').Parameters.Keys | ConvertTo-Json -Compress"
    )
    parameters = set(json.loads(completed.stdout))

    assert {"ResumeCandidateRun", "CandidateLedger", "RecoveryRecord"} <= parameters
    assert "ResumeRun" not in parameters
    assert "ControllerPath" not in parameters
    assert "VerifierPath" not in parameters
    assert "InvocationContext" not in parameters


def test_hardware_wrapper_closed_interface_rejects_unknown_and_wrong_contract_switches() -> None:
    """Hardware wrapper binding must expose only the authorization/checkpoint contract."""
    completed = _run_powershell(
        f"(Get-Command '{HARDWARE}').Parameters.Keys | ConvertTo-Json -Compress"
    )
    parameters = set(json.loads(completed.stdout))

    assert {
        "Contract",
        "Repo",
        "ExpectedCodeHead",
        "FinalRunId",
        "EvidenceRoot",
        "PrepareAction",
        "ExecuteAction",
        "Nonce",
        "ActionDigest",
        "Authorized",
        "ResumeContract",
        "Checkpoint",
        "RecoveryRecord",
        "ContractSelfTest",
    } <= parameters
    rejected = subprocess.run(
        ["powershell.exe", "-NoProfile", "-File", str(HARDWARE), "-UnknownSwitch"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert rejected.returncode != 0


def test_runner_cli_rejects_unknown_switch_and_shell_command_string(tmp_path: Path) -> None:
    """Argparse must reject unknown flags and a one-string shell command before dispatch."""
    completed = subprocess.run(
        [sys.executable, str(RUNNER), "performance", "--unknown", "x"],
        capture_output=True,
        text=True,
        check=False,
    )
    shell = subprocess.run(
        [sys.executable, str(RUNNER), "dev-coverage", "--task-id", "STM32TK-0601", "--evidence-root", str(tmp_path / "e"), "--", "pytest; echo unsafe"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert shell.returncode != 0


def test_contract_self_tests_use_only_fakes_and_report_pass() -> None:
    """Acceptance self-tests must exercise pass/fail/blocked paths without product or hardware access."""
    for wrapper, expected_mode in (
        (QUICK, "quick"), (CANDIDATE, "candidate"), (FINAL, "final"), (HARDWARE, "hardware")
    ):
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(wrapper),
                "-ContractSelfTest",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        assert completed.returncode == 0, completed.stderr
        result = json.loads(completed.stdout)
        assert result == {
            "hardware_access": 0,
            "mode": expected_mode,
            "network_access": 0,
            "product_bodies": 0,
            "status": "PASS",
        }


@pytest.mark.parametrize("mode", ["prepare", "execute", "resume"])
def test_public_hardware_cli_dispatches_every_validated_mode_to_state_machine(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    mode: str,
) -> None:
    """Public hardware modes must reach distinct state-machine methods while reserved work stays blocked."""
    calls: list[tuple[str, object]] = []

    class FakeController:
        def __init__(self, **kwargs: object) -> None:
            calls.append(("init", kwargs))

        def prepare_reserved(self) -> dict[str, object]:
            calls.append(("prepare", None))
            return {"status": "BLOCKED", "reason": "CATALOG_ACTION_RESERVED"}

        def execute(self, nonce: str, digest: str, *, authorized: bool) -> dict[str, object]:
            calls.append(("execute", (nonce, digest, authorized)))
            return {"status": "PASS"}

        def resume(self, checkpoint: Path, recovery: Path) -> dict[str, object]:
            calls.append(("resume", (checkpoint, recovery)))
            return {"status": "FRESH_PREPARE_REQUIRED"}

    monkeypatch.setattr(gates, "HardwareContractController", FakeController)
    monkeypatch.setattr(gates, "_git_text", lambda _repo, _args: "b" * 40)
    repo = tmp_path / "repo"
    repo.mkdir()
    evidence = tmp_path / "evidence"
    base = [
        "hardware", "--contract", "0600", "--repo", str(repo),
        "--expected-code-head", "a" * 40, "--final-run-id", RUN_ID,
        "--evidence-root", str(evidence), "--mode", mode,
    ]
    if mode == "execute":
        base.extend(["--nonce", "c" * 64, "--action-digest", "d" * 64, "--authorized"])
    elif mode == "resume":
        checkpoint = tmp_path / "checkpoint.json"
        recovery = tmp_path / "recovery.json"
        base.extend(["--checkpoint", str(checkpoint), "--recovery-record", str(recovery)])

    assert gates_main(base) == 0
    assert calls[1][0] == mode
    assert json.loads(capsys.readouterr().out)["status"] in {"BLOCKED", "PASS", "FRESH_PREPARE_REQUIRED"}


def test_terminal_candidate_wrapper_owns_ledger_and_writes_local_shard_package(
    tmp_path: Path,
) -> None:
    """Even BLOCKED candidate termination must atomically retain its own ledger/package."""
    candidate_root = tmp_path / "candidate"
    candidate_root.mkdir()
    evidence = candidate_root / "evidence"
    support_profile = _write_support(tmp_path / "support")
    code_head = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    result = run_wrapper_contract(
        kind="candidate",
        matrix="candidate",
        module="STM32TK-0601",
        shard="release-contract",
        run_id=RUN_ID,
        evidence_root=evidence,
        expected_code_head=code_head,
        gate_catalog=CATALOG,
        performance_catalog=RELEASE / "performance_0600.json",
        support_profile=support_profile,
        controller_path=RELEASE / "run_0600_candidate.ps1",
        now=lambda: NOW,
        verifier_blob_checker=lambda _repo, _head: RELEASE / "verify_0600_release.py",
        verifier_invoker=lambda _repo, _head, _argv: SimpleNamespace(returncode=0),
    )

    assert result["status"] == "BLOCKED"
    candidate_ledger = candidate_root / "candidate-ledger.json"
    retained = json.loads(candidate_ledger.read_text(encoding="utf-8"))
    assert retained["state"] == "blocked"
    assert retained["candidate_run_id"] == RUN_ID
    assert retained["controller_path"] == str(RELEASE / "run_0600_candidate.ps1")
    assert retained["checkpoint"] == str(evidence / "controller-result.json")
    package = Path(result["package"]["path"])
    package_manifest = package.with_name(package.name + ".manifest.json")
    assert package.is_file()
    assert package_manifest.read_bytes() == canonical_json_bytes(result["package"])
    verify_shard_package(package, result["package"], result["binding"])


def test_terminal_wrapper_schedules_executable_catalog_families_and_verifies_package(
    tmp_path: Path,
) -> None:
    """An executable family must run from catalog argv and determine PASS instead of a hardcoded BLOCKED."""
    support_profile = _write_support(tmp_path / "support")
    evidence = tmp_path / "quick-evidence"
    node = "fixture::node"
    command = (
        sys.executable,
        "-c",
        "import json;print(json.dumps({'schema':'stm32-node-outcome/1','node_id':'fixture::node','outcome':'passed'}))",
    )
    family = GateFamily(
        family_id="FIXTURE-EXECUTABLE",
        module="STM32TK-0601",
        matrices=("quick-0601",),
        owner_class="Codex/local derived agents",
        platform_class="windows-python",
        evidence_type="fixture",
        coverage_context="controller-off",
        command_argv=command,
        node_ids=(node,),
        prerequisites=(),
        reserved=False,
    )
    result = run_wrapper_contract(
        kind="quick", matrix="quick", module="STM32TK-0601", shard="fixture",
        run_id=RUN_ID, evidence_root=evidence, expected_code_head="a" * 40,
        gate_catalog=CATALOG, performance_catalog=RELEASE / "performance_0600.json",
        support_profile=support_profile, controller_path=QUICK, now=lambda: NOW,
        catalog_loader=lambda _path: GateCatalog((family,), ()),
        verifier_blob_checker=lambda _repo, _head: RELEASE / "verify_0600_release.py",
        gate_precheck=lambda _gate: None,
    )

    assert result["status"] == "PASS"
    retained = json.loads((evidence / "controller-result.json").read_text(encoding="utf-8"))
    assert retained["gate_inventory"] == ["FIXTURE-EXECUTABLE"]
    assert retained["gate_results"][0]["status"] == "PASS"
    verify_shard_package(Path(result["package"]["path"]), result["package"], result["binding"])


def test_terminal_final_wrapper_retains_closed_resume_checkpoint(tmp_path: Path) -> None:
    """A BLOCKED final shard must retain the one bounded final-windows resume checkpoint."""
    evidence = tmp_path / "final-evidence"
    support_profile = _write_support(tmp_path / "support")
    code_head = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    result = run_wrapper_contract(
        kind="final",
        matrix="final",
        module="STM32TK-0601",
        shard="windows",
        run_id=RUN_ID,
        evidence_root=evidence,
        expected_code_head=code_head,
        gate_catalog=CATALOG,
        performance_catalog=RELEASE / "performance_0600.json",
        support_profile=support_profile,
        controller_path=RELEASE / "run_0600_final.ps1",
        now=lambda: NOW,
        verifier_blob_checker=lambda _repo, _head: RELEASE / "verify_0600_release.py",
        verifier_invoker=lambda _repo, _head, _argv: SimpleNamespace(returncode=0),
    )

    checkpoint = json.loads((evidence / "checkpoint.json").read_text(encoding="utf-8"))
    assert result["status"] == "BLOCKED"
    assert checkpoint == {
        "schema": "stm32-final-checkpoint/1",
        "run_id": RUN_ID,
        "code_head": code_head,
        "controller_path": str(RELEASE / "run_0600_final.ps1"),
        "evidence_root": str(evidence),
        "state": "blocked",
        "resume_count": 0,
        "interruption_event": None,
    }
