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
import verify_0600_release as release_verifier  # noqa: E402
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
        for sibling in Path(r"C:\tmp").glob(f"{root.name}-coverage-*"):
            if sibling.parent.resolve() != Path(r"C:\tmp").resolve() or gates._is_reparse(sibling):
                raise AssertionError(f"unsafe coverage test cleanup target: {sibling}")
            if sibling.is_dir():
                shutil.rmtree(sibling)
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


def test_gate_matrix_retains_closed_decision_facts_for_every_control_branch() -> None:
    """A terminal reason must be derivable without trusting the reason string itself."""
    bodies: list[str] = []
    precheck = run_gate_matrix(
        "candidate",
        [_gate("PRECHECK")],
        execute=lambda gate, _env: (
            bodies.append(gate.gate_id), GateRunOutput(0, b"", b"", (), ())
        )[1],
        precheck=lambda _gate: (_ for _ in ()).throw(ControllerError("precheck")),
    )[0]
    postcheck = run_gate_matrix(
        "quick",
        [_gate("POSTCHECK")],
        execute=lambda gate, _env: (
            bodies.append(gate.gate_id),
            GateRunOutput(
                0, b"", b"", ("tests::POSTCHECK",),
                (("tests::POSTCHECK", "passed"),),
            ),
        )[1],
        precheck=lambda _gate: None,
        postcheck=lambda _gate: (_ for _ in ()).throw(ControllerError("postcheck")),
    )[0]

    assert bodies == ["POSTCHECK"]
    assert precheck.metadata["decision"] == {
        "postcheck": "NOT_RUN", "precheck": "FAIL", "prerequisites": []
    }
    assert postcheck.metadata["decision"] == {
        "postcheck": "FAIL", "precheck": "PASS", "prerequisites": []
    }


def test_gate_matrix_blocks_cross_module_failed_prerequisite_without_body() -> None:
    """A terminal FAIL owned by another module blocks its dependent before process creation."""
    bodies: list[str] = []
    result = run_gate_matrix(
        "quick",
        [_gate("DEPENDENT", prerequisites=("CROSS-MODULE",))],
        execute=lambda gate, _env: (
            bodies.append(gate.gate_id), GateRunOutput(0, b"", b"", (), ())
        )[1],
        prerequisite_statuses={"CROSS-MODULE": "FAIL"},
    )[0]

    assert bodies == []
    assert (result.status, result.reason) == ("BLOCKED", "PREREQUISITE_NOT_PASS")
    assert result.metadata["decision"] == {
        "postcheck": "NOT_RUN",
        "precheck": "NOT_RUN",
        "prerequisites": [{"gate_id": "CROSS-MODULE", "status": "FAIL"}],
    }


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
        "cwd": ".",
        "decision": {
            "postcheck": "NOT_REQUIRED",
            "precheck": "NOT_REQUIRED",
            "prerequisites": [],
        },
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
        "selected_nodes": ["tests::A"],
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


def test_gate_matrix_rejects_exit_zero_when_any_exact_node_failed() -> None:
    """A zero process exit cannot override an exact failed node outcome."""
    node = "tests::A"

    result = run_gate_matrix(
        "quick",
        [_gate("A")],
        execute=lambda _gate, _env: GateRunOutput(
            0, b"", b"", (node,), ((node, "failed"),)
        ),
    )[0]

    assert (result.status, result.reason) == ("FAIL", "PRODUCT_FAILURE")


def test_non_python_executable_metadata_uses_exact_file_digest(tmp_path: Path) -> None:
    """Non-Python version evidence is an exact executable digest, never a placeholder."""
    executable = tmp_path / "fixture-tool.exe"
    executable.write_bytes(b"fixture-tool-version-1")
    node = "tests::A"
    gate = GateRequest("A", (str(executable), "--fixture"), REPO, 5, (node,))

    result = run_gate_matrix(
        "quick",
        [gate],
        execute=lambda _gate, _env: GateRunOutput(
            0, b"", b"", (node,), ((node, "passed"),)
        ),
    )[0]

    assert result.metadata["executable"] == str(executable)
    assert result.metadata["executable_version"] == f"sha256:{_sha(executable.read_bytes())}"


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


def _coverage_evidence(tmp_path: Path, name: str = "evidence") -> Path:
    return Path(r"C:\tmp") / f"{tmp_path.name}-coverage-{name}"


def _create_junction(path: Path, target: Path) -> None:
    completed = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(path), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        pytest.skip(f"junction creation is unavailable: {completed.stderr}")


def _coverage_v7(rows: dict[str, tuple[int, int]]) -> dict[str, object]:
    """Return the closed coverage.py JSON format 3 emitted by the frozen pytest command."""
    def display(percent: float) -> str:
        if 0 < percent < 1:
            return "1"
        if 99 < percent < 100:
            return "99"
        return f"{percent:.0f}"

    def summary(covered: int, total: int, statements: int) -> dict[str, object]:
        combined_percent = 100.0 if statements + total == 0 else (statements + covered) * 100.0 / (statements + total)
        branch_percent = 100.0 if total == 0 else covered * 100.0 / total
        return {
            "covered_lines": statements,
            "num_statements": statements,
            "percent_covered": combined_percent,
            "percent_covered_display": display(combined_percent),
            "missing_lines": 0,
            "excluded_lines": 0,
            "percent_statements_covered": 100.0,
            "percent_statements_covered_display": "100",
            "num_branches": total,
            "num_partial_branches": 0,
            "covered_branches": covered,
            "missing_branches": total - covered,
            "percent_branches_covered": branch_percent,
            "percent_branches_covered_display": display(branch_percent),
        }

    files: dict[str, object] = {}
    for path, (covered, total) in rows.items():
        files[path] = {
            "executed_lines": [1],
            "summary": summary(covered, total, 1),
            "missing_lines": [],
            "excluded_lines": [],
            "executed_branches": [],
            "missing_branches": [],
            "functions": {},
            "classes": {},
        }
    return {
        "meta": {
            "format": 3,
            "version": "7.15.4",
            "timestamp": "2026-08-15T10:08:26.569114",
            "branch_coverage": True,
            "show_contexts": False,
        },
        "files": files,
        "totals": summary(sum(row[0] for row in rows.values()), sum(row[1] for row in rows.values()), len(rows)),
    }


_COVERAGE_PLAN_PATHS = (
    "docs/superpowers/plans/2026-08-14-stm32tk-0601-test-evidence.md",
    "docs/superpowers/plans/2026-08-14-stm32tk-0602-diagnostic-loop.md",
    "docs/superpowers/plans/2026-08-14-stm32tk-0603-monitor-analytics.md",
)


def _frozen_dev_coverage_commands() -> list[tuple[str, list[str]]]:
    commands: list[tuple[str, list[str]]] = []
    for relative in _COVERAGE_PLAN_PATHS:
        for line in (REPO / relative).read_text(encoding="utf-8").splitlines():
            if " dev-coverage " not in line:
                continue
            argv = line.split()
            task_id = argv[argv.index("--task-id") + 1]
            commands.append((task_id, argv[argv.index("--") + 1 :]))
    return commands


@pytest.mark.parametrize(
    ("task_id", "tokens"),
    _frozen_dev_coverage_commands(),
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_dev_coverage_accepts_every_frozen_plan_pytest_shape(
    tmp_path: Path, task_id: str, tokens: list[str]
) -> None:
    """Every planned 0601/0602/0603 coverage argv reaches pytest, not a controller grammar error."""
    repo = tmp_path / "repo"
    evidence = _coverage_evidence(tmp_path)
    requested_modules = [token.removeprefix("--cov=") for token in tokens if token.startswith("--cov=")]
    roots = sorted({module.split(".", 1)[0] for module in requested_modules})
    changed: list[str] = []
    for root in roots:
        package = "stm32-toolkit" if root == "stm32_toolkit" else "stm32-monitor"
        relative = f"tools/{package}/src/{root}/contract_fixture.py"
        product = repo.joinpath(*relative.split("/"))
        product.parent.mkdir(parents=True, exist_ok=True)
        product.write_text("VALUE = 1\n", encoding="utf-8")
        changed.append(relative)
    for token in tokens:
        if not token.startswith("tools/"):
            continue
        test = repo.joinpath(*token.split("/"))
        test.parent.mkdir(parents=True, exist_ok=True)
        test.write_text("def test_contract_fixture(): pass\n", encoding="utf-8")

    calls = 0

    def runner(argv: list[str], *, cwd: Path, env: dict[str, str]) -> int:
        nonlocal calls
        calls += 1
        assert cwd == repo
        assert argv[:3] == [sys.executable, "-m", "pytest"]
        if "--basetemp" in argv:
            Path(argv[argv.index("--basetemp") + 1]).mkdir()
        raw = _coverage_v7({path: (9, 10) for path in changed})
        (evidence / "coverage-raw.json").write_text(json.dumps(raw), encoding="utf-8")
        return 0

    result = run_dev_coverage(
        repo, task_id, evidence, tokens, _coverage_git(changed), runner
    )

    assert calls == 1
    assert result["task_id"] == task_id


def test_frozen_dev_coverage_inventory_covers_all_planned_tasks() -> None:
    """The self-hosting grammar test must not silently omit a frozen coverage command."""
    assert [task_id for task_id, _ in _frozen_dev_coverage_commands()] == [
        *(f"STM32TK-0601-T{task:02d}" for task in range(3, 12)),
        *(f"STM32TK-0602-T{task:02d}" for task in range(1, 11)),
        *(f"STM32TK-0603-T{task:02d}" for task in range(1, 8)),
        "STM32TK-0603-T11",
        "STM32TK-0603-T12",
    ]


@pytest.mark.parametrize(
    "tokens",
    [
        ["--basetemp"],
        ["--basetemp", "relative"],
        ["--basetemp", r"C:\tmp\bad;echo"],
        ["--basetemp", r"C:\tmp\one", "--basetemp", r"C:\tmp\two"],
    ],
)
def test_dev_coverage_rejects_invalid_basetemp_before_evidence_creation(
    tmp_path: Path, tokens: list[str]
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    evidence = _coverage_evidence(tmp_path)

    with pytest.raises(ControllerError):
        run_dev_coverage(repo, "STM32TK-0603-T12", evidence, tokens, _coverage_git([]))

    assert not evidence.exists()


def test_dev_coverage_rejects_basetemp_for_other_tasks_and_existing_paths(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    test_file = repo / "tools/stm32-toolkit/tests/test_a.py"
    product = repo / "tools/stm32-toolkit/src/stm32_toolkit/a.py"
    test_file.parent.mkdir(parents=True)
    product.parent.mkdir(parents=True)
    test_file.write_text("def test_a(): pass\n", encoding="utf-8")
    product.write_text("VALUE = 1\n", encoding="utf-8")
    existing = tmp_path / "existing-basetemp"
    existing.mkdir()
    for task_id in ("STM32TK-0601-T03", "STM32TK-0603-T12"):
        evidence = _coverage_evidence(tmp_path, task_id)
        with pytest.raises(ControllerError):
            run_dev_coverage(
                repo,
                task_id,
                evidence,
                [str(test_file), "--cov=stm32_toolkit.a", "--basetemp", str(existing)],
                _coverage_git([product.relative_to(repo).as_posix()]),
            )
        assert not evidence.exists()


@pytest.mark.parametrize("case", ["repository", "outside-tmp", "alias", "missing-parent"])
def test_dev_coverage_rejects_unsafe_absent_basetemp_before_evidence_creation(
    tmp_path: Path, case: str
) -> None:
    repo = tmp_path / "repo"
    test_file = repo / "tools/stm32-toolkit/tests/test_a.py"
    product = repo / "tools/stm32-toolkit/src/stm32_toolkit/a.py"
    test_file.parent.mkdir(parents=True)
    product.parent.mkdir(parents=True)
    test_file.write_text("def test_a(): pass\n", encoding="utf-8")
    product.write_text("VALUE = 1\n", encoding="utf-8")
    values = {
        "repository": str(repo / "basetemp"),
        "outside-tmp": r"C:\Windows\Temp\stm32tk-coverage-basetemp",
        "alias": r"C:\tmp\.\stm32tk-coverage-basetemp",
        "missing-parent": r"C:\tmp\missing-stm32tk-coverage-parent\basetemp",
    }
    evidence = _coverage_evidence(tmp_path)

    with pytest.raises(ControllerError):
        run_dev_coverage(
            repo,
            "STM32TK-0603-T12",
            evidence,
            [str(test_file), "--cov=stm32_toolkit.a", "--basetemp", values[case]],
            _coverage_git([product.relative_to(repo).as_posix()]),
        )

    assert not evidence.exists()


@pytest.mark.parametrize(
    ("task_id", "extra_tokens"),
    [
        ("STM32TK-0603-T01", []),
        ("STM32TK-0603-T12", ["--basetemp", r"C:\tmp\stm32tk-0603-package-312"]),
    ],
)
def test_dev_coverage_rejects_evidence_parent_junction_before_claiming_root(
    tmp_path: Path, task_id: str, extra_tokens: list[str],
) -> None:
    """A lexical C:\\tmp path must not redirect the derived basetemp outside C:\\tmp."""
    repo = tmp_path / "repo"
    test_file = repo / "tools/stm32-monitor/tests/test_package.py"
    product = repo / "tools/stm32-monitor/src/stm32_monitor/package.py"
    test_file.parent.mkdir(parents=True)
    product.parent.mkdir(parents=True)
    test_file.write_text("def test_package(): pass\n", encoding="utf-8")
    product.write_text("VALUE = 1\n", encoding="utf-8")
    linked_parent = tmp_path / "linked-parent"
    _create_junction(linked_parent, REPO)
    evidence = linked_parent / "must-not-be-created"
    try:
        with pytest.raises(ControllerError, match="direct child"):
            run_dev_coverage(
                repo,
                task_id,
                evidence,
                [str(test_file), "--cov=stm32_monitor.package", *extra_tokens],
                _coverage_git([product.relative_to(repo).as_posix()]),
            )
        assert not evidence.exists()
    finally:
        os.rmdir(linked_parent)


def test_dev_coverage_rejects_nested_evidence_root_before_claiming_it(tmp_path: Path) -> None:
    """Frozen coverage roots are unique direct children of C:\\tmp, never deeper paths."""
    repo = tmp_path / "repo"
    test_file = repo / "tools/stm32-monitor/tests/test_package.py"
    product = repo / "tools/stm32-monitor/src/stm32_monitor/package.py"
    test_file.parent.mkdir(parents=True)
    product.parent.mkdir(parents=True)
    test_file.write_text("def test_package(): pass\n", encoding="utf-8")
    product.write_text("VALUE = 1\n", encoding="utf-8")
    evidence = tmp_path / "nested-evidence"
    runner_calls = 0

    def runner(*_args: object, **_kwargs: object) -> int:
        nonlocal runner_calls
        runner_calls += 1
        return 0

    with pytest.raises(ControllerError, match="direct child"):
        run_dev_coverage(
            repo,
            "STM32TK-0603-T01",
            evidence,
            [str(test_file), "--cov=stm32_monitor.package"],
            _coverage_git([product.relative_to(repo).as_posix()]),
            runner,
        )

    assert runner_calls == 0
    assert not evidence.exists()


def test_dev_coverage_win32_directory_identity_uses_volume_and_file_index() -> None:
    """The retained identity comes from an open Win32 handle, not mutable timestamps."""
    with gates._open_locked_windows_directory(Path(r"C:\tmp")) as locked:
        assert locked.path == Path(r"C:\tmp")
        assert isinstance(locked.volume_serial, int)
        assert isinstance(locked.file_index, int)
        assert locked.file_index >= 0


def test_dev_coverage_fails_closed_without_windows_locking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No fallback may silently run coverage without the required Win32 handles."""
    repo = tmp_path / "repo"
    repo.mkdir()
    evidence = _coverage_evidence(tmp_path)
    monkeypatch.setattr(gates, "_coverage_windows_available", lambda: False)

    with pytest.raises(ControllerError, match="Windows directory locking"):
        gates._validate_coverage_attempt_location(repo, evidence)

    assert not evidence.exists()


def test_dev_coverage_rejects_prepositioned_root_junction(tmp_path: Path) -> None:
    """A direct-child name occupied by a junction is rejected as reparse state."""
    repo = tmp_path / "repo"
    test_file = repo / "tools/stm32-monitor/tests/test_package.py"
    product = repo / "tools/stm32-monitor/src/stm32_monitor/package.py"
    test_file.parent.mkdir(parents=True)
    product.parent.mkdir(parents=True)
    test_file.write_text("def test_package(): pass\n", encoding="utf-8")
    product.write_text("VALUE = 1\n", encoding="utf-8")
    evidence = _coverage_evidence(tmp_path)
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    _create_junction(evidence, replacement)
    try:
        with pytest.raises(ControllerError, match="reparse"):
            run_dev_coverage(
                repo,
                "STM32TK-0603-T01",
                evidence,
                [str(test_file), "--cov=stm32_monitor.package"],
                _coverage_git([product.relative_to(repo).as_posix()]),
            )
    finally:
        os.rmdir(evidence)


def test_dev_coverage_rejects_root_replaced_before_handle_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A create/open race that substitutes a junction fails before pytest."""
    repo = tmp_path / "repo"
    test_file = repo / "tools/stm32-monitor/tests/test_package.py"
    product = repo / "tools/stm32-monitor/src/stm32_monitor/package.py"
    test_file.parent.mkdir(parents=True)
    product.parent.mkdir(parents=True)
    test_file.write_text("def test_package(): pass\n", encoding="utf-8")
    product.write_text("VALUE = 1\n", encoding="utf-8")
    evidence = _coverage_evidence(tmp_path)
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    original_open = gates._open_locked_windows_directory
    replaced = False

    def replace_before_root_open(path: Path) -> object:
        nonlocal replaced
        if path == evidence and not replaced:
            replaced = True
            os.rmdir(evidence)
            _create_junction(evidence, replacement)
        return original_open(path)

    monkeypatch.setattr(gates, "_open_locked_windows_directory", replace_before_root_open)
    try:
        with pytest.raises(ControllerError, match="reparse"):
            run_dev_coverage(
                repo,
                "STM32TK-0603-T01",
                evidence,
                [str(test_file), "--cov=stm32_monitor.package"],
                _coverage_git([product.relative_to(repo).as_posix()]),
            )
    finally:
        if evidence.exists():
            os.rmdir(evidence)


def test_dev_coverage_rejects_target_created_before_root_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A competing target created after C:\\tmp is locked still loses create-new."""
    repo = tmp_path / "repo"
    test_file = repo / "tools/stm32-monitor/tests/test_package.py"
    product = repo / "tools/stm32-monitor/src/stm32_monitor/package.py"
    test_file.parent.mkdir(parents=True)
    product.parent.mkdir(parents=True)
    test_file.write_text("def test_package(): pass\n", encoding="utf-8")
    product.write_text("VALUE = 1\n", encoding="utf-8")
    evidence = _coverage_evidence(tmp_path)
    original_validate = gates._validate_coverage_attempt_location
    validations = 0

    def create_target_before_second_validation(repo_path: Path, root: Path) -> None:
        nonlocal validations
        validations += 1
        if validations == 2:
            root.mkdir()
        original_validate(repo_path, root)

    monkeypatch.setattr(gates, "_validate_coverage_attempt_location", create_target_before_second_validation)
    runner_calls = 0

    def runner(*_args: object, **_kwargs: object) -> int:
        nonlocal runner_calls
        runner_calls += 1
        return 0

    with pytest.raises(ControllerError, match="new path"):
        run_dev_coverage(
            repo,
            "STM32TK-0603-T01",
            evidence,
            [str(test_file), "--cov=stm32_monitor.package"],
            _coverage_git([product.relative_to(repo).as_posix()]),
            runner,
        )
    assert validations == 2
    assert runner_calls == 0


def test_dev_coverage_runner_cannot_replace_locked_root(tmp_path: Path) -> None:
    """A runner-time replacement is detected before any result is accepted."""
    repo = tmp_path / "repo"
    test_file = repo / "tools/stm32-monitor/tests/test_package.py"
    product = repo / "tools/stm32-monitor/src/stm32_monitor/package.py"
    test_file.parent.mkdir(parents=True)
    product.parent.mkdir(parents=True)
    test_file.write_text("def test_package(): pass\n", encoding="utf-8")
    product.write_text("VALUE = 1\n", encoding="utf-8")
    evidence = _coverage_evidence(tmp_path)
    changed = product.relative_to(repo).as_posix()

    def runner(argv: list[str], **_kwargs: object) -> int:
        os.rmdir(evidence)
        evidence.mkdir()
        return 0

    with pytest.raises(ControllerError, match="changed"):
        run_dev_coverage(
            repo,
            "STM32TK-0603-T01",
            evidence,
            [str(test_file), "--cov=stm32_monitor.package"],
            _coverage_git([changed]),
            runner,
        )


def test_dev_coverage_raw_read_occurs_while_root_is_locked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The no-delete root handle spans runner return and coverage JSON parsing."""
    repo = tmp_path / "repo"
    test_file = repo / "tools/stm32-monitor/tests/test_package.py"
    product = repo / "tools/stm32-monitor/src/stm32_monitor/package.py"
    test_file.parent.mkdir(parents=True)
    product.parent.mkdir(parents=True)
    test_file.write_text("def test_package(): pass\n", encoding="utf-8")
    product.write_text("VALUE = 1\n", encoding="utf-8")
    evidence = _coverage_evidence(tmp_path)
    moved = _coverage_evidence(tmp_path, "moved")
    changed = product.relative_to(repo).as_posix()
    original_load = gates._load_json

    def load_while_attempting_replace(path: Path) -> object:
        os.replace(evidence, moved)
        return original_load(path)

    monkeypatch.setattr(gates, "_load_json", load_while_attempting_replace)

    def runner(_argv: list[str], **_kwargs: object) -> int:
        (evidence / "coverage-raw.json").write_text(
            json.dumps(_coverage_v7({changed: (9, 10)})), encoding="utf-8"
        )
        return 0

    with pytest.raises(ControllerError):
        run_dev_coverage(
            repo,
            "STM32TK-0603-T01",
            evidence,
            [str(test_file), "--cov=stm32_monitor.package"],
            _coverage_git([changed]),
            runner,
        )


def test_dev_coverage_t12_failed_attempt_retries_same_frozen_argv_with_new_root(
    tmp_path: Path,
) -> None:
    """The fixed plan token names a namespace; each evidence attempt gets unique scratch."""
    repo = tmp_path / "repo"
    test_file = repo / "tools/stm32-monitor/tests/test_package.py"
    product = repo / "tools/stm32-monitor/src/stm32_monitor/package.py"
    test_file.parent.mkdir(parents=True)
    product.parent.mkdir(parents=True)
    test_file.write_text("def test_package(): pass\n", encoding="utf-8")
    product.write_text("VALUE = 1\n", encoding="utf-8")
    changed = product.relative_to(repo).as_posix()
    tokens = [
        str(test_file),
        "--cov=stm32_monitor.package",
        "--basetemp",
        r"C:\tmp\stm32tk-0603-package-312",
    ]
    first = _coverage_evidence(tmp_path, "attempt-1")
    second = _coverage_evidence(tmp_path, "attempt-2")
    actual: list[Path] = []

    def failing_runner(argv: list[str], **_kwargs: object) -> int:
        scratch = Path(argv[argv.index("--basetemp") + 1])
        actual.append(scratch)
        assert scratch.parent == first
        assert re.fullmatch(r"pytest-basetemp-[0-9a-f]{32}", scratch.name)
        scratch.mkdir()
        (first / "coverage-raw.json").write_text("retained failure\n", encoding="utf-8")
        return 1

    with pytest.raises(ControllerError, match="subprocess failed"):
        run_dev_coverage(
            repo, "STM32TK-0603-T12", first, tokens, _coverage_git([changed]), failing_runner
        )

    def successful_runner(argv: list[str], **_kwargs: object) -> int:
        scratch = Path(argv[argv.index("--basetemp") + 1])
        actual.append(scratch)
        assert scratch.parent == second
        assert re.fullmatch(r"pytest-basetemp-[0-9a-f]{32}", scratch.name)
        scratch.mkdir()
        (second / "coverage-raw.json").write_text(
            json.dumps(_coverage_v7({changed: (9, 10)})), encoding="utf-8"
        )
        return 0

    result = run_dev_coverage(
        repo, "STM32TK-0603-T12", second, tokens, _coverage_git([changed]), successful_runner
    )

    assert result["task_id"] == "STM32TK-0603-T12"
    assert actual[0] != actual[1]
    assert (first / "coverage-raw.json").read_text(encoding="utf-8") == "retained failure\n"
    assert actual[0].is_dir()


def test_dev_coverage_preflight_failure_does_not_claim_evidence_root(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    evidence = _coverage_evidence(tmp_path)

    with pytest.raises(ControllerError):
        run_dev_coverage(
            repo,
            "STM32TK-0603-T01",
            evidence,
            ["tools/stm32-monitor/tests/missing.py", "--cov=stm32_monitor.models"],
            _coverage_git([]),
        )

    assert not evidence.exists()


def test_dev_coverage_failed_execution_preserves_evidence_and_requires_new_root(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    product = repo / "tools/stm32-monitor/src/stm32_monitor/models.py"
    test_file = repo / "tools/stm32-monitor/tests/test_models.py"
    product.parent.mkdir(parents=True)
    test_file.parent.mkdir(parents=True)
    product.write_text("VALUE = 1\n", encoding="utf-8")
    test_file.write_text("def test_model(): pass\n", encoding="utf-8")
    changed = product.relative_to(repo).as_posix()
    evidence = _coverage_evidence(tmp_path, "attempt-1")

    def failing_runner(argv: list[str], *, cwd: Path, env: dict[str, str]) -> int:
        (evidence / "coverage-raw.json").write_text("retained failure\n", encoding="utf-8")
        return 1

    with pytest.raises(ControllerError, match="subprocess failed"):
        run_dev_coverage(
            repo,
            "STM32TK-0603-T01",
            evidence,
            [str(test_file), "--cov=stm32_monitor.models"],
            _coverage_git([changed]),
            failing_runner,
        )
    assert (evidence / "coverage-raw.json").read_text(encoding="utf-8") == "retained failure\n"

    with pytest.raises(ControllerError, match="new path"):
        run_dev_coverage(
            repo,
            "STM32TK-0603-T01",
            evidence,
            [str(test_file), "--cov=stm32_monitor.models"],
            _coverage_git([changed]),
        )


@pytest.mark.parametrize("version", ["7.10.7", "7.15.4"])
def test_dev_coverage_accepts_desensitized_real_format3_fixtures(version: str) -> None:
    """Frozen/current coverage JSON fixtures retain the exact real tool field shapes."""
    fixture = Path(__file__).parent / "fixtures" / "coverage" / f"coverage-{version}-format3.json"
    raw = json.loads(fixture.read_text(encoding="utf-8"))

    parsed = gates._validate_coverage_v7(raw)

    assert parsed["meta"]["version"] == version
    assert parsed["totals"]["covered_branches"] == 1


def test_dev_coverage_accepts_native_timestamp_without_fraction() -> None:
    """coverage uses datetime.isoformat(), which legitimately omits a zero microsecond fraction."""
    fixture = Path(__file__).parent / "fixtures" / "coverage" / "coverage-7.10.7-format3.json"
    raw = json.loads(fixture.read_text(encoding="utf-8"))

    assert gates._validate_coverage_v7(raw)["meta"]["timestamp"] == "2026-08-15T00:00:00"


@pytest.mark.parametrize("covered,total", [(1, 1000), (999, 1000)])
def test_dev_coverage_accepts_native_display_percent_clamping(covered: int, total: int) -> None:
    """coverage.py prevents nonzero percentages from displaying as 0 or 100 at precision zero."""
    raw = _coverage_v7({"tools/stm32-toolkit/src/stm32_toolkit/a.py": (covered, total)})

    assert gates._validate_coverage_v7(raw)["files"]


@pytest.mark.parametrize(
    "task_id",
    ["STM32TK-0601", "STM32TK-0601-T03", "STM32TK-0602-T01", "STM32TK-0603-T99"],
)
def test_dev_coverage_discovers_each_changed_product_file_and_requires_90_percent(
    tmp_path: Path, task_id: str,
) -> None:
    """Aggregate coverage must not hide an individual changed product file below 90%."""
    repo = tmp_path / "repo"
    product = repo / "tools/stm32-toolkit/src/stm32_toolkit/changed.py"
    test_file = repo / "tools/stm32-toolkit/tests/test_changed.py"
    product.parent.mkdir(parents=True)
    test_file.parent.mkdir(parents=True)
    product.write_text("VALUE = 1\n", encoding="utf-8")
    test_file.write_text("def test_changed(): pass\n", encoding="utf-8")
    evidence = _coverage_evidence(tmp_path)
    changed = product.relative_to(repo).as_posix()

    def runner(argv: list[str], *, cwd: Path, env: dict[str, str]) -> int:
        assert argv[:3] == [sys.executable, "-m", "pytest"]
        assert str(test_file) in argv
        assert "--cov=stm32_toolkit.changed" in argv
        assert argv[3:6] == ["-q", "-p", "no:cacheprovider"]
        assert not any(key.startswith(("COVERAGE_", "COV_CORE_")) for key in env)
        raw = _coverage_v7({changed: (9, 10)})
        (evidence / "coverage-raw.json").write_text(json.dumps(raw), encoding="utf-8")
        return 0

    result = run_dev_coverage(
        repo=repo,
        task_id=task_id,
        evidence_root=evidence,
        pytest_tokens=["-q", "-p", "no:cacheprovider", str(test_file), "--cov=stm32_toolkit.changed"],
        git_runner=_coverage_git([changed]),
        runner=runner,
    )

    assert result["files"] == [
        {"covered_branches": 9, "num_branches": 10, "path": changed, "percent": 90}
    ]
    assert result["task_id"] == task_id
    assert (evidence / "branch-coverage.json").is_file()


def test_dev_coverage_adds_exact_modules_for_changed_package_files(tmp_path: Path) -> None:
    """A frozen narrow --cov token must not leave another changed Python file unmeasured."""
    repo = tmp_path / "repo"
    package = repo / "tools/stm32-toolkit/src/stm32_toolkit/evidence"
    init_file = package / "__init__.py"
    model_file = package / "model.py"
    test_file = repo / "tools/stm32-toolkit/tests/test_evidence.py"
    package.mkdir(parents=True)
    test_file.parent.mkdir(parents=True)
    init_file.write_text("from .model import VALUE\n", encoding="utf-8")
    model_file.write_text("VALUE = 1\n", encoding="utf-8")
    test_file.write_text("def test_value(): pass\n", encoding="utf-8")
    changed = [init_file.relative_to(repo).as_posix(), model_file.relative_to(repo).as_posix()]
    evidence = _coverage_evidence(tmp_path)

    def runner(argv: list[str], *, cwd: Path, env: dict[str, str]) -> int:
        assert argv.count("--cov=stm32_toolkit.evidence") == 1
        assert argv.count("--cov=stm32_toolkit.evidence.model") == 1
        raw = _coverage_v7({path: (0, 0) for path in changed})
        (evidence / "coverage-raw.json").write_text(json.dumps(raw), encoding="utf-8")
        return 0

    result = run_dev_coverage(
        repo,
        "STM32TK-0601-T03",
        evidence,
        [str(test_file), "--cov=stm32_toolkit.evidence.model", "--cov=stm32_toolkit.evidence.model", "-q", "-p", "no:cacheprovider"],
        _coverage_git(changed),
        runner,
    )

    assert [row["path"] for row in result["files"]] == changed


@pytest.mark.parametrize(
    "tokens",
    [
        ["-q", "-q"],
        ["-Q"],
        ["-p"],
        ["-p", "other-plugin"],
        ["-pno:cacheprovider"],
        ["-P", "no:cacheprovider"],
        ["-p", "NO:cacheprovider"],
        ["no:cacheprovider"],
        ["-p", "no:cacheprovider", "-p", "no:cacheprovider"],
        ["-p", "no:cacheprovider;echo"],
    ],
)
def test_dev_coverage_rejects_noncanonical_duplicate_or_unpaired_pytest_flags(
    tmp_path: Path, tokens: list[str]
) -> None:
    """Only one exact `-q` and one adjacent `-p no:cacheprovider` pair are allowed."""
    repo = tmp_path / "repo"
    repo.mkdir()
    evidence = _coverage_evidence(tmp_path)
    runner_calls = 0

    def runner(*_args: object, **_kwargs: object) -> int:
        nonlocal runner_calls
        runner_calls += 1
        return 0

    with pytest.raises(ControllerError):
        run_dev_coverage(repo, "STM32TK-0601-T03", evidence, tokens, _coverage_git([]), runner)

    assert runner_calls == 0


@pytest.mark.parametrize(
    "task_id",
    [
        "stm32tk-0601-T03",
        "STM32TK-0601-t03",
        "STM32TK-0601-T00",
        "STM32TK-0601-T1",
        "STM32TK-0601-T001",
        "STM32TK-0601-T03-extra",
        "STM32TK-0604-T03",
        "STM32TK-9999",
    ],
)
def test_dev_coverage_rejects_noncanonical_or_unknown_task_ids_before_side_effects(
    tmp_path: Path, task_id: str
) -> None:
    """Coverage task IDs are exact, case-sensitive, and limited to known 0.6 modules."""
    repo = tmp_path / "repo"
    repo.mkdir()
    evidence = _coverage_evidence(tmp_path)

    with pytest.raises(ControllerError, match="unknown coverage task"):
        run_dev_coverage(repo, task_id, evidence, ["tests/test_changed.py"])

    assert not evidence.exists()


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
    evidence = _coverage_evidence(tmp_path)

    def runner(_argv: list[str], *, cwd: Path, env: dict[str, str]) -> int:
        raw = _coverage_v7(rows)
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
    evidence = _coverage_evidence(tmp_path)

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


@pytest.mark.parametrize(
    "mutation",
    [
        "root-extra",
        "meta-missing",
        "meta-extra",
        "format",
        "version",
        "branch-disabled",
        "timestamp-short-fraction",
        "row-missing",
        "row-extra",
        "summary-missing",
        "summary-extra",
        "summary-percent",
        "totals-counter",
        "totals-percent",
    ],
)
def test_dev_coverage_rejects_mutated_coverage_v7_contract(tmp_path: Path, mutation: str) -> None:
    """The public parser accepts only the closed branch-enabled coverage JSON format 3 shape."""
    repo = tmp_path / "repo"
    changed = "tools/stm32-toolkit/src/stm32_toolkit/a.py"
    product = repo.joinpath(*changed.split("/"))
    test_file = repo / "tools/stm32-toolkit/tests/test_a.py"
    product.parent.mkdir(parents=True)
    test_file.parent.mkdir(parents=True)
    product.write_text("pass\n", encoding="utf-8")
    test_file.write_text("def test_a(): pass\n", encoding="utf-8")
    evidence = _coverage_evidence(tmp_path)

    def runner(_argv: list[str], *, cwd: Path, env: dict[str, str]) -> int:
        raw = _coverage_v7({changed: (9, 10)})
        details = raw["files"][changed]
        if mutation == "root-extra":
            raw["extra"] = None
        elif mutation == "meta-missing":
            raw["meta"].pop("show_contexts")
        elif mutation == "meta-extra":
            raw["meta"]["extra"] = None
        elif mutation == "format":
            raw["meta"]["format"] = 2
        elif mutation == "version":
            raw["meta"]["version"] = "8.0.0"
        elif mutation == "branch-disabled":
            raw["meta"]["branch_coverage"] = False
        elif mutation == "timestamp-short-fraction":
            raw["meta"]["timestamp"] = "2026-08-15T10:08:26.1"
        elif mutation == "row-missing":
            details.pop("functions")
        elif mutation == "row-extra":
            details["extra"] = None
        elif mutation == "summary-missing":
            details["summary"].pop("missing_branches")
        elif mutation == "summary-extra":
            details["summary"]["extra"] = None
        elif mutation == "summary-percent":
            details["summary"]["percent_covered"] = 90.0
        elif mutation == "totals-counter":
            raw["totals"]["covered_branches"] = 8
        else:
            raw["totals"]["percent_branches_covered_display"] = "91"
        (evidence / "coverage-raw.json").write_text(json.dumps(raw), encoding="utf-8")
        return 0

    with pytest.raises(ControllerError):
        run_dev_coverage(
            repo,
            "STM32TK-0601-T03",
            evidence,
            [str(test_file), "--cov=stm32_toolkit.a", "-q", "-p", "no:cacheprovider"],
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


def test_shard_verifier_binds_archive_members_to_external_evidence_bytes(
    tmp_path: Path,
) -> None:
    """A self-consistent replacement ZIP cannot substitute different retained bytes."""
    retained = tmp_path / "retained"
    substituted = tmp_path / "substituted"
    retained.mkdir()
    substituted.mkdir()
    (retained / "result.json").write_bytes(b"retained\n")
    (substituted / "result.json").write_bytes(b"substituted\n")
    package = tmp_path / "shard.zip"
    binding = _package_binding()
    reference = create_shard_package(substituted, package, binding)

    with pytest.raises(VerificationError, match="external|retained|member"):
        verify_shard_package(
            package,
            reference,
            binding,
            evidence_root=retained,
        )


def test_shard_verifier_rejects_external_evidence_toctou(
    tmp_path: Path,
) -> None:
    """The external snapshot must stay byte-identical through the final reread."""
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    result = evidence / "result.json"
    result.write_bytes(canonical_json_bytes({"state": "retained"}))
    package = tmp_path / "shard.zip"
    binding = _package_binding()
    reference = create_shard_package(evidence, package, binding)

    with pytest.raises(VerificationError, match="changed"):
        verify_shard_package(
            package,
            reference,
            binding,
            evidence_root=evidence,
            before_final_reread=lambda: result.write_bytes(
                canonical_json_bytes({"state": "mutated"})
            ),
        )


def test_shard_verifier_rejects_unexpected_external_file_toctou(tmp_path: Path) -> None:
    """An excluded local checkpoint cannot make arbitrary late external files invisible."""
    evidence = tmp_path / "evidence-inventory"
    evidence.mkdir()
    result = evidence / "controller-result.json"
    checkpoint = evidence / "checkpoint.json"
    result.write_bytes(canonical_json_bytes({"state": "retained"}))
    checkpoint.write_bytes(canonical_json_bytes({"state": "local-checkpoint"}))
    package = tmp_path / "inventory.zip"
    binding = _package_binding()
    package_paths = ["controller-result.json"]
    reference = create_shard_package(
        evidence, package, binding, member_paths=package_paths
    )

    with pytest.raises(VerificationError, match="changed|unexpected|inventory"):
        verify_shard_package(
            package,
            reference,
            binding,
            evidence_root=evidence,
            expected_paths=package_paths,
            allowed_external_paths=["checkpoint.json", "controller-result.json"],
            before_final_reread=lambda: (evidence / "unexpected.txt").write_text(
                "late mutation", encoding="utf-8"
            ),
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"credential": "secret-value"},
        {"password": "password-value"},
        {"client-secret": "secret-value"},
        {"ACCESS_TOKEN": "token-value"},
        {"api.key": "api-value"},
        {"AUTHORIZATION": "Bearer abc.def"},
        {"session-cookie": "sid=abc"},
        {"Private.Key": "private-material"},
        {"passwd": "opaque-secret-material"},
        {"auth": "opaque-secret-material"},
        {"refresh_token": "opaque-secret-material"},
        {"proxy_auth": "opaque-secret-material"},
        {"db_passwd": "opaque-secret-material"},
        {"user_pwd": "opaque-secret-material"},
        {"proxyAuth": "opaque-secret-material"},
        {"aws_access_key": "ASIAABCDEFGHIJKLMNOP"},
        {"github_token": "opaque-secret-material"},
        {"ciJobToken": "opaque-secret-material"},
        {"diagnostic": "Bearer abc.def"},
        {"diagnostic": "Basic YWJjOmRlZg=="},
        {"diagnostic": "Cookie: sid=abc"},
        {"diagnostic": "api_key=abc.def"},
        {"diagnostic": "-----BEGIN PRIVATE KEY-----"},
        {"diagnostic": "https://user:password@example.invalid/resource"},
        {"diagnostic": "ghp_abcdefghijklmnopqrstuvwxyz1234567890"},
        {"diagnostic": "sk-proj-abcdefghijklmnopqrstuvwxyz1234567890"},
        {"diagnostic": "github_pat_abcdefghijklmnopqrstuvwxyz1234567890"},
        {"diagnostic": "glpat-abcdefghijklmnopqrstuvwxyz1234567890"},
        {"diagnostic": "xoxb-1234567890-abcdefghijklmnopqrstuvwxyz"},
        {"diagnostic": "AKIAABCDEFGHIJKLMNOP"},
        {"diagnostic": "ASIAABCDEFGHIJKLMNOP"},
        {"diagnostic": "AIzaabcdefghijklmnopqrstuvwxyz1234567890"},
        {"diagnostic_path": r"C:\Users\private\diagnostic.log"},
        {"diagnostic_path": r"\\server\private\diagnostic.log"},
        {"diagnostic_path": "//server/private/diagnostic.log"},
        {"diagnostic_path": r"\Windows\System32\config"},
        {"diagnostic_path": "/root/admin/diagnostic.log"},
        {"diagnostic_path": "/etc/toolkit.conf"},
        {"diagnostic": ",/etc/passwd"},
        {"diagnostic": "[/root/private-key]"},
    ],
)
def test_shard_verifier_rejects_private_or_credential_payload_fields(
    tmp_path: Path, payload: dict[str, str]
) -> None:
    """Safe member names cannot conceal credentials or absolute private paths in payloads."""
    evidence = tmp_path / "private-evidence"
    evidence.mkdir()
    (evidence / "result.json").write_bytes(canonical_json_bytes(payload))
    package = tmp_path / "private.zip"
    binding = _package_binding()
    reference = create_shard_package(evidence, package, binding)

    with pytest.raises(VerificationError, match="private|credential|portable"):
        verify_shard_package(
            package, reference, binding, evidence_root=evidence
        )


@pytest.mark.parametrize("alias", ["GITHUBTOKEN", "PROXYAUTH", "OAUTHTOKEN"])
def test_shard_verifier_rejects_compact_credential_alias_fields(
    tmp_path: Path, alias: str
) -> None:
    """Exact normalized compound aliases cannot hide in JSON field names."""
    evidence = tmp_path / "compact-alias-field"
    evidence.mkdir()
    (evidence / "result.json").write_bytes(
        canonical_json_bytes({alias: "opaque-secret-material"})
    )
    package = tmp_path / "compact-alias-field.zip"
    binding = _package_binding()
    reference = create_shard_package(evidence, package, binding)

    with pytest.raises(VerificationError, match="credential"):
        verify_shard_package(package, reference, binding, evidence_root=evidence)


@pytest.mark.parametrize(
    "payload",
    [
        b"Authorization: Bearer abc.def\n",
        b"Basic YWJjOmRlZg==\n",
        b"Cookie: sid=abc\n",
        b"api_key=abc.def\n",
        b"Auth: opaque-secret-material\n",
        b"refresh_token=opaque-secret-material\n",
        b"DATABASE_PASSWORD=opaque-secret-material\n",
        b"AWS_SECRET_ACCESS_KEY=abcdefghijklmnopqrstuvwxyz1234567890ABCD\n",
        b"PROXY_AUTH=opaque-secret-material\n",
        b"SERVICE_PASSWD=opaque-secret-material\n",
        b"GITHUB_TOKEN=opaque-secret-material\n",
        b"(DATABASE_PASSWORD=opaque-secret-material)\n",
        b"[AWS_SECRET_ACCESS_KEY=abcdefghijklmnopqrstuvwxyz1234567890ABCD]\n",
        b"|PROXY_AUTH=opaque-secret-material\n",
        b"'SERVICE_PASSWD'=opaque-secret-material\n",
        b"$env:GITHUB_TOKEN=opaque-secret-material\n",
        b"env:DATABASE_PASSWORD=opaque-secret-material\n",
        b"config:PROXY_AUTH=opaque-secret-material\n",
        b"-----BEGIN PRIVATE KEY-----\n",
        b"https://user:password@example.invalid/resource\n",
        b"ghp_abcdefghijklmnopqrstuvwxyz1234567890\n",
        b"sk-proj-abcdefghijklmnopqrstuvwxyz1234567890\n",
        b"//server/private/diagnostic.log\n",
        b"\\Windows\\System32\\config\n",
        b"/root/admin/diagnostic.log\n",
        b"/etc/toolkit.conf\n",
        b",/etc/passwd\n",
        b"[/root/private-key]\n",
    ],
)
def test_shard_verifier_rejects_private_or_credential_text_payloads(
    tmp_path: Path, payload: bytes
) -> None:
    """Text members apply the same path and credential-value policy as JSON strings."""
    evidence = tmp_path / "private-text-evidence"
    evidence.mkdir()
    (evidence / "result.log").write_bytes(payload)
    package = tmp_path / "private-text.zip"
    binding = _package_binding()
    reference = create_shard_package(evidence, package, binding)

    with pytest.raises(VerificationError, match="private|credential|portable"):
        verify_shard_package(package, reference, binding, evidence_root=evidence)


@pytest.mark.parametrize(
    "payload",
    [
        b"GITHUBTOKEN=opaque-secret-material\n",
        b"PROXYAUTH:opaque-secret-material\n",
        b"OAUTHTOKEN=opaque-secret-material\n",
        b"env:GITHUBTOKEN=opaque-secret-material\n",
        b"config:PROXYAUTH=opaque-secret-material\n",
        b"'OAUTHTOKEN'=opaque-secret-material\n",
        b'"GITHUBTOKEN":opaque-secret-material\n',
        b"$env:PROXYAUTH=opaque-secret-material\n",
        b"scope:OAUTHTOKEN=opaque-secret-material\n",
        b"tests::GITHUBTOKEN=opaque-secret-material\n",
        b"tests::GITHUB_TOKEN=opaque-secret-material\n",
        b"tests::OAUTH-TOKEN=opaque-secret-material\n",
    ],
)
def test_shard_verifier_rejects_compact_credential_alias_assignments(
    tmp_path: Path, payload: bytes
) -> None:
    """Exact compact aliases remain credentials in every supported assignment form."""
    evidence = tmp_path / "compact-alias-assignment"
    evidence.mkdir()
    (evidence / "result.log").write_bytes(payload)
    package = tmp_path / "compact-alias-assignment.zip"
    binding = _package_binding()
    reference = create_shard_package(evidence, package, binding)

    with pytest.raises(VerificationError, match="credential"):
        verify_shard_package(package, reference, binding, evidence_root=evidence)


def test_shard_verifier_rejects_empty_username_credential_uri(
    tmp_path: Path,
) -> None:
    """A packaged URI with an empty username cannot hide a non-empty password."""
    evidence = tmp_path / "empty-username-credential-uri"
    evidence.mkdir()
    (evidence / "result.log").write_bytes(
        b"git+path://:password@example.invalid/key\n"
    )
    package = tmp_path / "empty-username-credential-uri.zip"
    binding = _package_binding()
    reference = create_shard_package(evidence, package, binding)

    with pytest.raises(VerificationError, match="credential"):
        verify_shard_package(
            package, reference, binding, evidence_root=evidence
        )


@pytest.mark.parametrize(
    ("value", "forbidden"),
    [
        ("https://:password@example.invalid/key", True),
        ("https://user:password@example.invalid/key", True),
        ("https://user@example.invalid/key", True),
        ("https://user:@example.invalid/key", True),
        ("https://%75ser@example.invalid/key", True),
        ("https://:%70assword@example.invalid/key", True),
        ("git+ssh://user:%70assword@example.invalid/key", True),
        ("git+path://example.invalid/key", False),
        ("https://example.invalid/users/user@example.invalid", False),
        ("https://example.invalid/key?contact=user@example.invalid", False),
        (r"regex (\d+|\w+)", False),
    ],
)
def test_portable_string_credential_uri_userinfo_is_structural(
    value: str, forbidden: bool
) -> None:
    """Only URI authority userinfo is credential material; path/query text is not."""
    if forbidden:
        with pytest.raises(VerificationError, match="credential"):
            release_verifier._validate_portable_string(value)
    else:
        release_verifier._validate_portable_string(value)


@pytest.mark.parametrize(
    ("value", "forbidden"),
    [
        ("git+path://example.invalid/key", False),
        ("path://server/share/secret.txt", True),
        ("root://server/share/secret.txt", True),
        ("+path://server/share/secret.txt", True),
        ("1git+path://server/share/secret.txt", True),
        ("_git+path://server/share/secret.txt", True),
        ("git+path://user:password@example.invalid/key", True),
    ],
)
def test_portable_string_plus_uri_scheme_does_not_hide_labeled_roots_or_credentials(
    value: str, forbidden: bool
) -> None:
    """A valid plus-scheme is portable without making bare labels or credentials portable."""
    if forbidden:
        with pytest.raises(VerificationError, match="private|credential"):
            release_verifier._validate_portable_string(value)
    else:
        release_verifier._validate_portable_string(value)


@pytest.mark.parametrize(
    ("value", "forbidden"),
    [
        (r"regex (\d+|\w+)", False),
        (r"regex \d+\.\d+", False),
        (r"regex (\d+|\Windows\System32)", True),
        (r"regex \d+\.\Windows\System32", True),
        (r"\Windows\System32\config", True),
        (r"\.\Windows\System32", True),
    ],
)
def test_portable_string_regex_escapes_do_not_hide_windows_root_relative_paths(
    value: str, forbidden: bool
) -> None:
    """Regex alternation/literal-dot escapes stay portable without admitting rooted paths."""
    if forbidden:
        with pytest.raises(VerificationError, match="private"):
            release_verifier._validate_portable_string(value)
    else:
        release_verifier._validate_portable_string(value)


@pytest.mark.parametrize(
    ("payload", "forbidden"),
    [
        (b"PASS / FAIL\n", False),
        (b"PASS /root/private\n", True),
        (b"ratio 1 / 2\n", False),
        (b"ratio 1 /etc/toolkit.conf\n", True),
        (b"regex \\d+\n", False),
        (b"regex ^\\d+$\n", False),
        (b"regex \\d+\\s+\\w+\n", False),
        (b"regex ^\\d+\\s+\\w+$\n", False),
        (b"regex \\Windows\\System32\\config\n", True),
        (b"Basic tests passed\n", False),
        (b"Basic YWJjOmRlZg==\n", True),
        (b"Basic dXNlcjpwYXNz\n", True),
        (b"https://example.invalid/result\n", False),
        (b"ftp://example.invalid/pub/file\n", False),
        (b"resource-path://example.invalid/pub/file\n", False),
        (b"square-root://example.invalid/value\n", False),
        (b"https://user:password@example.invalid/result\n", True),
        (b"root C:\\\n", True),
        (b"path:/root/private.log\n", True),
        (b"path:C:\\Users\\Alice\\secret.txt\n", True),
        (b"path:\\Windows\\System32\\config\n", True),
        (b"path://server/share/secret.txt\n", True),
        (b"path:/\n", True),
        (b"path:\\\n", True),
        (b"path=/\n", True),
        (b"path = /\n", True),
        (b"root=\\\n", True),
        (b"///etc/passwd\n", True),
        (b"path:///root/private.log\n", True),
        (b"file:////server/share\n", True),
        (b"////server/share\n", True),
        (b"//secret.txt\n", True),
        (b"//root\n", True),
        (b"/\\private\n", True),
        (b"/\n", True),
        (b"\\\n", True),
        (b"//\n", True),
        (b"/@private\n", True),
        (b"/$HOME\n", True),
        ("/用户\n".encode("utf-8"), True),
        (b"file:///etc/passwd\n", True),
        (b"Bearer abc1234\n", True),
        (b"Bearer abc+123\n", True),
        (b"Bearer abcdefg\n", True),
        (b"Bearer 1234567\n", True),
        (b"Bearer abc123\n", True),
        (b"Bearer a.b\n", True),
    ],
)
def test_portable_text_grammar_distinguishes_prose_from_rooted_paths_and_credentials(
    tmp_path: Path, payload: bytes, forbidden: bool
) -> None:
    """Root and authorization grammar rejects credentials/paths without flagging prose."""
    evidence = tmp_path / "portable-grammar"
    evidence.mkdir()
    (evidence / "result.log").write_bytes(payload)
    package = tmp_path / "portable-grammar.zip"
    binding = _package_binding()
    reference = create_shard_package(evidence, package, binding)

    if forbidden:
        with pytest.raises(VerificationError, match="private|credential"):
            verify_shard_package(package, reference, binding, evidence_root=evidence)
    else:
        verify_shard_package(package, reference, binding, evidence_root=evidence)


@pytest.mark.parametrize(
    ("name", "payload"),
    [
        (
            "result.json",
            canonical_json_bytes({
                "author": "release-controller",
                "message": "authorization checks passed",
                "node_id": "tests/test_cookie_policy.py::test_relative_private_key_name",
                "path": "gates/result.json",
            }),
        ),
        (
            "result.log",
            b"authorization checks passed\nrelative/private_key/report.txt\n"
            b"tests::test_cookie=value\n",
        ),
    ],
)
def test_shard_verifier_allows_portable_relative_privacy_words(
    tmp_path: Path, name: str, payload: bytes
) -> None:
    """Privacy vocabulary without a credential value or absolute path remains portable."""
    evidence = tmp_path / "portable-control"
    evidence.mkdir()
    (evidence / name).write_bytes(payload)
    package = tmp_path / "portable-control.zip"
    binding = _package_binding()
    reference = create_shard_package(evidence, package, binding)

    verify_shard_package(package, reference, binding, evidence_root=evidence)


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
    def __init__(
        self, *, dirty: str = "", head: str = "b" * 40,
        origin: str = "https://github.com/XiaoyaoLinghao/stm32-toolkit.git",
    ) -> None:
        self.dirty = dirty
        self.head = head
        self.origin = origin

    def __call__(self, args: list[str]) -> str:
        if args == ["rev-parse", "HEAD"]:
            return self.head + "\n"
        if args == ["config", "--get", "remote.origin.url"]:
            return self.origin + "\n"
        if args == ["status", "--porcelain=v1", "--untracked-files=all"]:
            return self.dirty
        if args[:2] == ["hash-object", "--"] or (args[0] == "rev-parse" and ":" in args[1]):
            return "d" * 40 + "\n"
        raise AssertionError(args)


def _hardware_campaign(digest: str = "e" * 64) -> dict[str, object]:
    return {
        "schema": "stm32-hardware-campaign-binding/1",
        "campaign_id": "223e4567-e89b-42d3-a456-426614174000",
        "sha256": digest,
        "generator_code_head": "b" * 40,
        "evidence_owner": "user",
        "board_revision": "rev-A",
        "mcu_part": "STM32F446RE",
        "mcu_uid_hash": "4" * 64,
        "probe_model": "ST-LINK/V3",
        "uart_adapter_model": "FT232R",
        "firmware_0400_sha256": "5" * 64,
        "firmware_0400_build_id": "firmware-0400-A",
        "firmware_0600_sha256": "6" * 64,
        "firmware_0600_build_id": "firmware-0600-A",
    }


def _write_hardware_campaign_input(
    path: Path, support_profile: Path, firmware_0600: bytes
) -> Path:
    firmware_root = path.parent / f"{path.stem}-firmware"
    firmware_root.mkdir()
    firmware_0400_path = firmware_root / "firmware-0400.elf"
    firmware_0600_path = firmware_root / "firmware-0600.elf"
    firmware_0400_path.write_bytes(b"firmware-0400")
    firmware_0600_path.write_bytes(firmware_0600)

    def reference(member: Path) -> dict[str, object]:
        data = member.read_bytes()
        return {"path": str(member), "bytes": len(data), "sha256": _sha(data)}

    campaign = {
        "schema": "stm32-hardware-campaign-inputs/1",
        "campaign_id": "223e4567-e89b-42d3-a456-426614174000",
        "created_at_utc": "2026-08-15T02:03:04.123456Z",
        "generator_code_head": "b" * 40,
        "evidence_owner": "user",
        "board_id": "board-A",
        "board_revision": "rev-A",
        "mcu_part": "STM32F446RE",
        "mcu_uid_hash": "4" * 64,
        "probe_model": "ST-LINK/V3",
        "probe_serial_hash": "a" * 64,
        "uart_adapter_model": "FT232R",
        "uart_serial_hash": "c" * 64,
        "power_identity": "bench-A",
        "transports": ["mailbox", "rtt", "semihosting", "uart"],
        "support_profile": reference(support_profile),
        "support_manifest": reference(support_profile.parents[1] / "support-manifest.json"),
        "firmware_0400": {
            **reference(firmware_0400_path), "build_id": "firmware-0400-A"
        },
        "firmware_0600": {
            **reference(firmware_0600_path), "build_id": "firmware-0600-A"
        },
    }
    path.write_bytes(canonical_json_bytes(campaign))
    return path


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
        hardware_campaign=_hardware_campaign(),
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
            hardware_identity=controller.hardware_identity,
            hardware_campaign=controller.hardware_campaign,
            git_runner=HardwareGit(),
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


def test_hardware_rejects_boolean_counter_even_with_recomputed_digest(tmp_path: Path) -> None:
    """JSON booleans cannot impersonate integer counters under a self-consistent digest."""
    controller, backend = _hardware(tmp_path)
    prepared = controller.prepare()
    checkpoint = json.loads(controller.checkpoint_path.read_text(encoding="utf-8"))
    checkpoint["prepared"]["counters"]["control"] = False
    checkpoint["prepared"]["action_digest"] = controller._digest_for_prepared(
        checkpoint["prepared"]
    )
    controller.checkpoint_path.write_bytes(canonical_json_bytes(checkpoint))

    with pytest.raises(ControllerError, match="prepared|counter"):
        controller.execute(
            prepared["nonce"], checkpoint["prepared"]["action_digest"], authorized=True
        )
    assert backend.execute_calls == []


def test_hardware_authorization_rejects_full_campaign_substitution(tmp_path: Path) -> None:
    """A changed firmware/campaign digest cannot reuse a prepared hardware authorization."""
    support_profile = _write_support(tmp_path / "campaign-support")
    first_input = _write_hardware_campaign_input(
        tmp_path / "campaign-first.json", support_profile, b"firmware-0600-first"
    )
    second_input = _write_hardware_campaign_input(
        tmp_path / "campaign-second.json", support_profile, b"firmware-0600-second"
    )
    _, first_identity, first_campaign = gates.load_hardware_campaign_input(
        first_input, expected_generator_code_head="b" * 40
    )
    _, backend = _hardware(tmp_path)
    controller = HardwareContractController(
        contract="0600", repo=REPO, catalog=CATALOG,
        expected_code_head="a" * 40, controller_code_head="b" * 40,
        final_run_id=RUN_ID, evidence_root=tmp_path / "hardware-campaign",
        backend=backend, support_profile=support_profile,
        hardware_identity=first_identity, hardware_campaign=first_campaign,
        git_runner=HardwareGit(), now=lambda: NOW,
        random_bytes=lambda count: bytes(range(count)),
    )
    prepared = controller.prepare()
    _, replacement_identity, replacement_campaign = gates.load_hardware_campaign_input(
        second_input, expected_generator_code_head="b" * 40
    )
    assert replacement_identity == first_identity
    assert replacement_campaign["firmware_0600_sha256"] != first_campaign["firmware_0600_sha256"]

    replacement = HardwareContractController(
        contract=controller.contract, repo=controller.repo, catalog=controller.catalog,
        expected_code_head=controller.expected_code_head,
        controller_code_head=controller.controller_code_head,
        final_run_id=controller.final_run_id, evidence_root=controller.evidence_root,
        backend=backend, support_profile=controller.support_profile,
        hardware_identity=replacement_identity,
        hardware_campaign=replacement_campaign,
        git_runner=HardwareGit(), now=lambda: NOW,
    )
    with pytest.raises(ControllerError, match="campaign|binding|digest"):
        replacement.execute(
            prepared["nonce"], prepared["action_digest"], authorized=True
        )
    assert backend.execute_calls == []


def test_hardware_requires_exact_catalog_lock_names_and_canonical_origin(tmp_path: Path) -> None:
    """Hardware state binds the catalog's exact lock set and exact canonical GitHub URL."""
    controller, _ = _hardware(tmp_path)
    assert controller.resource_locks == {
        "board": "board-A",
        "evidence-root": str(tmp_path / "hardware-0600"),
        "probe": "a" * 64,
        "uart": "c" * 64,
    }

    backend = FakeHardwareBackend(
        {
            "board_id": "board-A", "probe_serial_hash": "a" * 64,
            "uart_serial_hash": "c" * 64, "power_identity": "bench-A",
            "state": "running",
        }, [], [], [],
    )
    with pytest.raises(ControllerError, match="origin"):
        _hardware(
            tmp_path / "variant",
            backend=backend,
            git=HardwareGit(origin="https://github.com/XiaoyaoLinghao/stm32-toolkit"),
        )
    assert backend.prepare_calls == []


def test_hardware_rejects_placeholder_identity_before_backend(tmp_path: Path) -> None:
    """A public-style reserved placeholder cannot stand in for campaign-bound identity."""
    backend = FakeHardwareBackend(
        {
            "board_id": "reserved-hardware-input", "probe_serial_hash": "0" * 64,
            "uart_serial_hash": "1" * 64, "power_identity": "reserved-hardware-input",
            "state": "running",
        }, [], [], [],
    )
    with pytest.raises(ControllerError, match="placeholder|identity"):
        HardwareContractController(
            contract="0600", repo=REPO, catalog=CATALOG,
            expected_code_head="a" * 40, controller_code_head="b" * 40,
            final_run_id=RUN_ID, evidence_root=tmp_path / "placeholder",
            backend=backend, support_profile=_write_support(tmp_path / "placeholder-support"),
            hardware_identity={
                "board_id": "reserved-hardware-input", "probe_serial_hash": "0" * 64,
                "uart_serial_hash": "1" * 64, "power_identity": "reserved-hardware-input",
            },
            hardware_campaign=_hardware_campaign(),
            git_runner=HardwareGit(),
        )
    assert backend.prepare_calls == []


def test_hardware_caller_trust_precedes_release_verifier_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An untrusted controller blob/HEAD must fail before lazy release-verifier code loads."""
    backend = FakeHardwareBackend(
        {
            "board_id": "board-A", "probe_serial_hash": "a" * 64,
            "uart_serial_hash": "c" * 64, "power_identity": "bench-A",
            "state": "running",
        }, [], [], [],
    )
    monkeypatch.setattr(
        gates,
        "_release_call",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("release verifier loaded before caller trust")
        ),
    )

    with pytest.raises(ControllerError, match="HEAD"):
        HardwareContractController(
            contract="0600", repo=REPO, catalog=CATALOG,
            expected_code_head="a" * 40, controller_code_head="b" * 40,
            final_run_id=RUN_ID, evidence_root=tmp_path / "untrusted-head",
            backend=backend, support_profile=_write_support(tmp_path / "trust-support"),
            hardware_identity={
                "board_id": "board-A", "probe_serial_hash": "a" * 64,
                "uart_serial_hash": "c" * 64, "power_identity": "bench-A",
            },
            hardware_campaign=_hardware_campaign(),
            git_runner=HardwareGit(head="c" * 40), now=lambda: NOW,
        )
    assert backend.prepare_calls == []
    assert backend.execute_calls == []


@pytest.mark.parametrize(
    ("field", "placeholder"),
    [
        ("board_revision", "boardFixtureRevA"),
        ("mcu_part", "mcuReservedPart42"),
        ("probe_model", "probeUnsetModel2"),
        ("uart_adapter_model", "uartTestAdapter7"),
        ("firmware_0400_build_id", "fwReservedBuild42"),
        ("firmware_0600_build_id", "fwUnsetBuild7"),
    ],
)
def test_hardware_controller_rejects_every_projected_campaign_placeholder_before_backend(
    tmp_path: Path, field: str, placeholder: str
) -> None:
    """A forged campaign projection cannot bypass the raw campaign placeholder policy."""
    valid, backend = _hardware(tmp_path)
    campaign = copy.deepcopy(valid.hardware_campaign)
    campaign[field] = placeholder

    with pytest.raises(ControllerError, match="campaign|placeholder|identity"):
        HardwareContractController(
            contract="0600", repo=REPO, catalog=CATALOG,
            expected_code_head="a" * 40, controller_code_head="b" * 40,
            final_run_id=RUN_ID, evidence_root=tmp_path / f"projected-{field}",
            backend=backend, support_profile=valid.support_profile,
            hardware_identity=valid.hardware_identity, hardware_campaign=campaign,
            git_runner=HardwareGit(), now=lambda: NOW,
        )
    assert backend.prepare_calls == []
    assert backend.execute_calls == []


@pytest.mark.parametrize(
    ("field", "placeholder"),
    [
        ("board_id", "boardFixtureRevA"),
        ("power_identity", "benchTestRail4"),
    ],
)
def test_hardware_controller_rejects_embedded_identity_placeholders_before_backend(
    tmp_path: Path, field: str, placeholder: str
) -> None:
    """Projected board/power identities use the same component-aware placeholder rule."""
    valid, backend = _hardware(tmp_path)
    identity = copy.deepcopy(valid.hardware_identity)
    identity[field] = placeholder

    with pytest.raises(ControllerError, match="placeholder|identity"):
        HardwareContractController(
            contract="0600", repo=REPO, catalog=CATALOG,
            expected_code_head="a" * 40, controller_code_head="b" * 40,
            final_run_id=RUN_ID, evidence_root=tmp_path / f"projected-{field}",
            backend=backend, support_profile=valid.support_profile,
            hardware_identity=identity, hardware_campaign=valid.hardware_campaign,
            git_runner=HardwareGit(), now=lambda: NOW,
        )
    assert backend.prepare_calls == []
    assert backend.observe_calls == []
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


def test_candidate_resume_executes_only_ledger_repository_runner(tmp_path: Path) -> None:
    """A copied wrapper cannot redirect resume execution to its sibling replacement runner."""
    trusted = tmp_path / "trusted"
    trusted_release = trusted / "tools/release"
    trusted_release.mkdir(parents=True)
    for source in (
        CANDIDATE, PATH_HELPER, RUNNER,
        RELEASE / "verify_0600_feasibility.py", RELEASE / "verify_0600_release.py",
    ):
        (trusted_release / source.name).write_bytes(source.read_bytes())
    for args in (
        ["init"], ["config", "user.email", "test@example.invalid"],
        ["config", "user.name", "test"], ["config", "core.autocrlf", "false"],
        ["add", "."], ["commit", "-m", "trusted"],
    ):
        subprocess.run(["git", "-C", str(trusted), *args], check=True, capture_output=True)
    head = subprocess.run(
        ["git", "-C", str(trusted), "rev-parse", "HEAD"], check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    candidate_root = tmp_path / "candidate"
    candidate_root.mkdir()
    ledger = candidate_root / "candidate-ledger.json"
    ledger.write_bytes(canonical_json_bytes({
        "controller_path": str(trusted_release / CANDIDATE.name),
        "expected_code_head": head,
    }))
    recovery = tmp_path / "recovery.json"
    recovery.write_bytes(b"{}\n")
    attacker = tmp_path / "attacker"
    attacker.mkdir()
    attacker_wrapper = attacker / CANDIDATE.name
    attacker_wrapper.write_bytes(CANDIDATE.read_bytes())
    (attacker / PATH_HELPER.name).write_bytes(PATH_HELPER.read_bytes())
    sentinel = tmp_path / "attacker-spawned.txt"
    (attacker / RUNNER.name).write_text(
        f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('spawned')\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(attacker_wrapper), "-ResumeCandidateRun", "-CandidateLedger", str(ledger),
            "-RecoveryRecord", str(recovery),
        ],
        capture_output=True, text=True, check=False,
    )
    for retained in (trusted / ".git").rglob("*"):
        if retained.is_file():
            os.chmod(retained, 0o666)

    assert completed.returncode != 0
    assert not sentinel.exists()


def test_final_resume_executes_only_checkpoint_repository_runner(tmp_path: Path) -> None:
    """Final resume must spawn the runner beneath the checkpoint-derived trusted worktree."""
    trusted = tmp_path / "trusted-final"
    trusted_release = trusted / "tools/release"
    trusted_release.mkdir(parents=True)
    for source in (
        FINAL, PATH_HELPER, RUNNER,
        RELEASE / "verify_0600_feasibility.py", RELEASE / "verify_0600_release.py",
    ):
        (trusted_release / source.name).write_bytes(source.read_bytes())
    for args in (
        ["init"], ["config", "user.email", "test@example.invalid"],
        ["config", "user.name", "test"], ["config", "core.autocrlf", "false"],
        ["add", "."], ["commit", "-m", "trusted"],
    ):
        subprocess.run(["git", "-C", str(trusted), *args], check=True, capture_output=True)
    head = subprocess.run(
        ["git", "-C", str(trusted), "rev-parse", "HEAD"], check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    evidence = tmp_path / "final-evidence"
    evidence.mkdir()
    checkpoint = evidence / "checkpoint.json"
    checkpoint.write_bytes(canonical_json_bytes({
        "controller_path": str(trusted_release / FINAL.name), "code_head": head,
    }))
    recovery = tmp_path / "final-recovery.json"
    recovery.write_bytes(b"{}\n")
    attacker = tmp_path / "attacker-final"
    attacker.mkdir()
    attacker_wrapper = attacker / FINAL.name
    attacker_wrapper.write_bytes(FINAL.read_bytes())
    (attacker / PATH_HELPER.name).write_bytes(PATH_HELPER.read_bytes())
    sentinel = tmp_path / "final-attacker-spawned.txt"
    (attacker / RUNNER.name).write_text(
        f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('spawned')\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(attacker_wrapper), "-ResumeFinalRun", "-FinalCheckpoint", str(checkpoint),
            "-RecoveryRecord", str(recovery),
        ],
        capture_output=True, text=True, check=False,
    )
    for retained in (trusted / ".git").rglob("*"):
        if retained.is_file():
            os.chmod(retained, 0o666)

    assert completed.returncode != 0
    assert not sentinel.exists()


def test_hardware_selftest_checks_runner_blob_before_spawn(tmp_path: Path) -> None:
    """Hardware ContractSelfTest cannot load a replacement runner before caller trust."""
    trusted = tmp_path / "trusted-hardware"
    trusted_release = trusted / "tools/release"
    trusted_release.mkdir(parents=True)
    for source in (
        HARDWARE, PATH_HELPER, RUNNER, CATALOG,
        RELEASE / "verify_0600_feasibility.py", RELEASE / "verify_0600_release.py",
    ):
        (trusted_release / source.name).write_bytes(source.read_bytes())
    for args in (
        ["init"], ["config", "user.email", "test@example.invalid"],
        ["config", "user.name", "test"], ["config", "core.autocrlf", "false"],
        ["add", "."], ["commit", "-m", "trusted"],
    ):
        subprocess.run(["git", "-C", str(trusted), *args], check=True, capture_output=True)
    sentinel = tmp_path / "hardware-attacker-spawned.txt"
    (trusted_release / RUNNER.name).write_text(
        f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('spawned')\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(trusted_release / HARDWARE.name), "-ContractSelfTest",
        ],
        capture_output=True, text=True, check=False,
    )
    for retained in (trusted / ".git").rglob("*"):
        if retained.is_file():
            os.chmod(retained, 0o666)

    assert completed.returncode != 0
    assert not sentinel.exists()


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
        "HardwareInput",
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

    def trusted_git(_repo: Path, args: list[str]) -> str:
        if args == ["rev-parse", "HEAD"]:
            return "b" * 40
        if args == ["config", "--get", "remote.origin.url"]:
            return "https://github.com/XiaoyaoLinghao/stm32-toolkit.git"
        if args[:2] == ["hash-object", "--"]:
            relative = args[2]
            return gates._git_blob_id(REPO.joinpath(*relative.split("/")).read_bytes())
        if args[0] == "rev-parse" and ":" in args[1]:
            relative = args[1].split(":", 1)[1]
            return gates._git_blob_id(REPO.joinpath(*relative.split("/")).read_bytes())
        raise AssertionError(args)

    monkeypatch.setattr(gates, "_git_text", trusted_git)
    campaign_profile = tmp_path / "campaign-support/feasibility/profile.json"
    campaign_identity = {
        "board_id": "board-campaign", "probe_serial_hash": "2" * 64,
        "uart_serial_hash": "3" * 64, "power_identity": "power-campaign",
    }
    campaign_binding = _hardware_campaign()
    monkeypatch.setattr(
        gates, "load_hardware_campaign_input",
        lambda _path, **_kwargs: (campaign_profile, campaign_identity, campaign_binding),
        raising=False,
    )
    repo = REPO
    evidence = tmp_path / "evidence"
    base = [
        "hardware", "--contract", "0600", "--repo", str(repo),
        "--expected-code-head", "a" * 40, "--final-run-id", RUN_ID,
        "--evidence-root", str(evidence), "--hardware-input", str(tmp_path / "campaign.json"),
        "--mode", mode,
    ]
    if mode == "execute":
        base.extend(["--nonce", "c" * 64, "--action-digest", "d" * 64, "--authorized"])
    elif mode == "resume":
        checkpoint = tmp_path / "checkpoint.json"
        recovery = tmp_path / "recovery.json"
        base.extend(["--checkpoint", str(checkpoint), "--recovery-record", str(recovery)])

    assert gates_main(base) == 0
    assert calls[0][1]["support_profile"] == campaign_profile
    assert calls[0][1]["hardware_identity"] == campaign_identity
    assert calls[0][1]["hardware_campaign"] == campaign_binding
    assert calls[1][0] == mode
    assert json.loads(capsys.readouterr().out)["status"] in {"BLOCKED", "PASS", "FRESH_PREPARE_REQUIRED"}


@pytest.mark.parametrize("mode", ["prepare", "execute", "resume"])
def test_public_hardware_cli_rechecks_caller_blobs_before_campaign_or_backend_access(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    mode: str,
) -> None:
    """A verifier replaced after trust cannot execute or reach campaign/backend state."""
    events: list[str] = []
    sentinel = tmp_path / "replacement-verifier-executed.txt"
    controller_head = "b" * 40
    trusted_source = b"TRUSTED_SOURCE = True\n"
    release_path = tmp_path / "verify_0600_release.py"
    feasibility_path = tmp_path / "verify_0600_feasibility.py"
    release_path.write_bytes(trusted_source)
    feasibility_path.write_bytes(trusted_source)
    trusted_blob = gates._git_blob_id(trusted_source)
    captured_sources = {
        gates.VERIFIER_RELATIVE_PATH: (release_path, trusted_source, trusted_blob),
        gates.FEASIBILITY_RELATIVE_PATH: (feasibility_path, trusted_source, trusted_blob),
    }
    trust_calls = 0

    def staged_trust(
        _repo: Path,
        _head: str,
        *,
        git_runner: object = None,
        capture_modules: bool = False,
    ) -> dict[str, tuple[Path, bytes, str]]:
        del git_runner
        nonlocal trust_calls
        trust_calls += 1
        if capture_modules:
            return captured_sources
        if release_path.read_bytes() != trusted_source:
            raise ControllerError(f"hardware caller blob changed: {gates.VERIFIER_RELATIVE_PATH}")
        return {}

    real_load = gates._load_verified_hardware_verifiers

    def replace_after_trust(
        repo: Path,
        head: str,
        sources: dict[str, tuple[Path, bytes, str]],
    ) -> None:
        events.append("replace")
        release_path.write_text(
            "from pathlib import Path\n"
            f"Path({str(sentinel)!r}).write_text('executed', encoding='utf-8')\n",
            encoding="utf-8",
        )
        real_load(repo, head, sources)

    def campaign_loader(_path: Path, **_kwargs: object) -> tuple[Path, dict[str, str], dict[str, object]]:
        events.append("campaign")
        sentinel.write_text("replacement verifier executed", encoding="utf-8")
        return tmp_path / "support/profile.json", {}, {}

    class BackendSentinel:
        def __init__(self, **_kwargs: object) -> None:
            events.append("controller")

        def prepare_reserved(self) -> dict[str, object]:
            events.append("backend")
            return {"status": "BLOCKED"}

        def execute(self, *_args: object, **_kwargs: object) -> dict[str, object]:
            events.append("backend")
            return {"status": "PASS"}

        def resume(self, *_args: object) -> dict[str, object]:
            events.append("backend")
            return {"status": "FRESH_PREPARE_REQUIRED"}

    monkeypatch.setattr(gates, "_git_text", lambda _repo, _args: controller_head)
    monkeypatch.setattr(gates, "_verify_hardware_caller_trust", staged_trust)
    monkeypatch.setattr(gates, "_load_verified_hardware_verifiers", replace_after_trust)
    monkeypatch.setattr(gates, "load_hardware_campaign_input", campaign_loader)
    monkeypatch.setattr(gates, "HardwareContractController", BackendSentinel)
    base = [
        "hardware", "--contract", "0600", "--repo", str(REPO),
        "--expected-code-head", "a" * 40, "--final-run-id", RUN_ID,
        "--evidence-root", str(tmp_path / "evidence"),
        "--hardware-input", str(tmp_path / "campaign.json"), "--mode", mode,
    ]
    if mode == "execute":
        base.extend(["--nonce", "c" * 64, "--action-digest", "d" * 64, "--authorized"])
    elif mode == "resume":
        base.extend([
            "--checkpoint", str(tmp_path / "checkpoint.json"),
            "--recovery-record", str(tmp_path / "recovery.json"),
        ])

    assert gates_main(base) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "blob" in captured.err
    assert events == ["replace"]
    assert trust_calls == 2
    assert not sentinel.exists()


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
        "py", "-3.12",
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


def test_terminal_wrapper_blocks_executable_with_reserved_prerequisite(
    tmp_path: Path,
) -> None:
    """Complete catalog prerequisites survive scheduling and reserved dependencies block bodies."""
    support_profile = _write_support(tmp_path / "support-prerequisite")
    evidence = tmp_path / "quick-prerequisite"
    calls: list[str] = []
    reserved = GateFamily(
        family_id="RESERVED", module="STM32TK-0601", matrices=("quick-0601",),
        owner_class="Codex/local derived agents", platform_class="windows-python",
        evidence_type="fixture", coverage_context="controller-off", command_argv=(),
        node_ids=(), prerequisites=(), reserved=True,
    )
    executable = GateFamily(
        family_id="EXECUTABLE", module="STM32TK-0601", matrices=("quick-0601",),
        owner_class="Codex/local derived agents", platform_class="windows-python",
        evidence_type="fixture", coverage_context="controller-off",
        command_argv=("py", "-3.12", "-c", "raise SystemExit(0)"),
        node_ids=("fixture::node",), prerequisites=("RESERVED",), reserved=False,
    )

    result = run_wrapper_contract(
        kind="quick", matrix="quick", module="STM32TK-0601", shard="fixture",
        run_id=RUN_ID, evidence_root=evidence, expected_code_head="a" * 40,
        gate_catalog=CATALOG, performance_catalog=RELEASE / "performance_0600.json",
        support_profile=support_profile, controller_path=QUICK, now=lambda: NOW,
        catalog_loader=lambda _path: GateCatalog((reserved, executable), ()),
        verifier_blob_checker=lambda _repo, _head: RELEASE / "verify_0600_release.py",
        gate_precheck=lambda gate: calls.append(gate.gate_id),
    )

    retained = json.loads((evidence / "controller-result.json").read_text(encoding="utf-8"))
    assert result["status"] == "BLOCKED"
    assert calls == []
    assert retained["prerequisites"] == [
        {"gate_id": "RESERVED", "requires": []},
        {"gate_id": "EXECUTABLE", "requires": ["RESERVED"]},
    ]
    assert [(row["gate_id"], row["status"], row["reason"]) for row in retained["gate_results"]] == [
        ("RESERVED", "BLOCKED", "RESERVED_CATALOG_FAMILY"),
        ("EXECUTABLE", "BLOCKED", "PREREQUISITE_NOT_PASS"),
    ]


def test_terminal_wrapper_blocks_cross_module_reserved_prerequisite(
    tmp_path: Path,
) -> None:
    """A requested module cannot discard a reserved prerequisite owned by another module."""
    support_profile = _write_support(tmp_path / "support-cross-module")
    evidence = tmp_path / "quick-cross-module"
    calls: list[str] = []
    cross_module = GateFamily(
        family_id="CROSS-MODULE", module="STM32TK-0601", matrices=("quick-0601",),
        owner_class="Codex/local derived agents", platform_class="windows-python",
        evidence_type="fixture", coverage_context="controller-off", command_argv=(),
        node_ids=(), prerequisites=(), reserved=True,
    )
    requested = GateFamily(
        family_id="REQUESTED", module="STM32TK-0602", matrices=("quick-0602",),
        owner_class="Codex/local derived agents", platform_class="windows-python",
        evidence_type="fixture", coverage_context="controller-off",
        command_argv=("py", "-3.12", "-c", "raise SystemExit(0)"),
        node_ids=("fixture::node",), prerequisites=("CROSS-MODULE",), reserved=False,
    )

    result = run_wrapper_contract(
        kind="quick", matrix="quick", module="STM32TK-0602", shard="fixture",
        run_id=RUN_ID, evidence_root=evidence, expected_code_head="a" * 40,
        gate_catalog=CATALOG, performance_catalog=RELEASE / "performance_0600.json",
        support_profile=support_profile, controller_path=QUICK, now=lambda: NOW,
        catalog_loader=lambda _path: GateCatalog((cross_module, requested), ()),
        verifier_blob_checker=lambda _repo, _head: RELEASE / "verify_0600_release.py",
        gate_precheck=lambda gate: calls.append(gate.gate_id),
    )

    terminal = json.loads((evidence / "controller-result.json").read_text(encoding="utf-8"))
    assert result["status"] == "BLOCKED"
    assert calls == []
    assert [(row["gate_id"], row["status"], row["reason"]) for row in terminal["gate_results"]] == [
        ("REQUESTED", "BLOCKED", "PREREQUISITE_NOT_PASS")
    ]
    assert terminal["gate_results"][0]["metadata"]["decision"]["prerequisites"] == [
        {"gate_id": "CROSS-MODULE", "status": "BLOCKED"}
    ]


def test_final_reserved_row_fail_fast_prevents_later_executable_and_verifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A leading reserved final row must stop a later independent product process."""
    support_profile = _write_support(tmp_path / "support-final-reserved")
    evidence = tmp_path / "final-reserved"
    calls: list[str] = []
    reserved = GateFamily(
        family_id="RESERVED", module="STM32TK-0601", matrices=("final-windows",),
        owner_class="Codex/local derived agents", platform_class="windows-python",
        evidence_type="fixture", coverage_context="controller-off", command_argv=(),
        node_ids=(), prerequisites=(), reserved=True,
    )
    executable = GateFamily(
        family_id="EXECUTABLE", module="STM32TK-0601", matrices=("final-windows",),
        owner_class="Codex/local derived agents", platform_class="windows-python",
        evidence_type="fixture", coverage_context="controller-off",
        command_argv=("py", "-3.12", "-c", "raise SystemExit(0)"),
        node_ids=("fixture::node",), prerequisites=(), reserved=False,
    )
    catalog = GateCatalog((reserved, executable), ())
    head = "a" * 40

    run_wrapper_contract(
        kind="final", matrix="final", module="STM32TK-0601", shard="windows",
        run_id=RUN_ID, evidence_root=evidence, expected_code_head=head,
        gate_catalog=CATALOG, performance_catalog=RELEASE / "performance_0600.json",
        support_profile=support_profile, controller_path=FINAL, now=lambda: NOW,
        catalog_loader=lambda _path: catalog,
        verifier_blob_checker=lambda _repo, _head: RELEASE / "verify_0600_release.py",
        verifier_invoker=lambda _repo, _head, _argv: SimpleNamespace(returncode=0),
        gate_precheck=lambda gate: calls.append(gate.gate_id),
    )
    terminal_path = evidence / "controller-result.json"
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    assert calls == []
    assert [(row["gate_id"], row["status"], row["reason"]) for row in terminal["gate_results"]] == [
        ("RESERVED", "BLOCKED", "RESERVED_CATALOG_FAMILY"),
        ("EXECUTABLE", "BLOCKED", "FINAL_FAIL_FAST"),
    ]
    monkeypatch.setattr(release_verifier, "FROZEN_SUPPORT_PROFILE", support_profile)
    assert release_verifier._verify_terminal_result(
        terminal_path, expected_head=head, expected_mode="final", catalog=catalog,
        catalog_sha256=terminal["catalog_sha256"],
        performance_sha256=terminal["performance_sha256"],
        support_profile_sha256=None,
    )["status"] == "BLOCKED"


def test_terminal_verifier_derives_row_status_from_exit_and_node_outcomes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A self-consistent package cannot label exit-zero/failed-node evidence PASS."""
    support_profile = _write_support(tmp_path / "support-terminal-row")
    evidence = tmp_path / "final-terminal-row"
    node = "fixture::failed"
    command = (
        "py", "-3.12", "-c",
        "import json;print(json.dumps({'schema':'stm32-node-outcome/1','node_id':'fixture::failed','outcome':'failed'}))",
    )
    family = GateFamily(
        family_id="FIXTURE-FAILED", module="STM32TK-0601", matrices=("final-windows",),
        owner_class="Codex/local derived agents", platform_class="windows-python",
        evidence_type="fixture", coverage_context="controller-off", command_argv=command,
        node_ids=(node,), prerequisites=(), reserved=False,
    )
    head = "a" * 40
    result = run_wrapper_contract(
        kind="final", matrix="final", module="STM32TK-0601", shard="windows",
        run_id=RUN_ID, evidence_root=evidence, expected_code_head=head,
        gate_catalog=CATALOG, performance_catalog=RELEASE / "performance_0600.json",
        support_profile=support_profile, controller_path=FINAL, now=lambda: NOW,
        catalog_loader=lambda _path: GateCatalog((family,), ()),
        verifier_blob_checker=lambda _repo, _head: RELEASE / "verify_0600_release.py",
        verifier_invoker=lambda _repo, _head, _argv: SimpleNamespace(returncode=0),
        gate_precheck=lambda _gate: None,
    )
    terminal_path = evidence / "controller-result.json"
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    assert terminal["gate_results"][0]["metadata"]["exit_code"] == 0
    assert terminal["gate_results"][0]["metadata"]["node_outcomes"] == [
        {"node_id": node, "outcome": "failed"}
    ]
    terminal["gate_results"][0]["status"] = "PASS"
    terminal["gate_results"][0]["reason"] = "PASS"
    terminal["status"] = "PASS"
    terminal["reason"] = "PASS"
    terminal["binding"]["status"] = "PASS"
    terminal_path.write_bytes(canonical_json_bytes(terminal))
    package_path = Path(result["package"]["path"])
    package_path.unlink()
    package_reference = create_shard_package(evidence, package_path, terminal["binding"])
    package_path.with_name(package_path.name + ".manifest.json").write_bytes(
        canonical_json_bytes(package_reference)
    )
    monkeypatch.setattr(release_verifier, "FROZEN_SUPPORT_PROFILE", support_profile)

    with pytest.raises(VerificationError, match="status|reason|outcome"):
        release_verifier._verify_terminal_result(
            terminal_path, expected_head=head, expected_mode="final",
            catalog=GateCatalog((family,), ()),
            catalog_sha256=terminal["catalog_sha256"],
            performance_sha256=terminal["performance_sha256"],
            support_profile_sha256=None,
        )


@pytest.mark.parametrize(
    ("case", "forged_reason"),
    [
        ("precheck", "PREREQUISITE_NOT_PASS"),
        ("prerequisite", "FINAL_FAIL_FAST"),
        ("fail-fast", "PREREQUISITE_NOT_PASS"),
        ("postcheck", "PRODUCT_FAILURE"),
    ],
)
def test_terminal_verifier_derives_control_reason_from_retained_facts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    forged_reason: str,
) -> None:
    """Changing a claimed control reason cannot change the retained control facts."""
    support_profile = _write_support(tmp_path / f"support-reason-{case}")
    evidence = tmp_path / f"final-reason-{case}"
    failing_node = "fixture::failed"
    failing_command = (
        "py", "-3.12", "-c",
        "import json;print(json.dumps({'schema':'stm32-node-outcome/1','node_id':'fixture::failed','outcome':'failed'}));raise SystemExit(1)",
    )

    def family(
        family_id: str,
        *,
        command: tuple[str, ...] = failing_command,
        nodes: tuple[str, ...] = (failing_node,),
        prerequisites: tuple[str, ...] = (),
        reserved: bool = False,
    ) -> GateFamily:
        return GateFamily(
            family_id=family_id, module="STM32TK-0601", matrices=("final-windows",),
            owner_class="Codex/local derived agents", platform_class="windows-python",
            evidence_type="fixture", coverage_context="controller-off",
            command_argv=command, node_ids=nodes, prerequisites=prerequisites,
            reserved=reserved,
        )

    check_calls: dict[str, int] = {}
    if case == "precheck":
        families = (family("TARGET"),)
        target = 0

        def gate_precheck(_gate: GateRequest) -> None:
            raise ControllerError("precheck failure")

    elif case == "prerequisite":
        families = (
            family("RESERVED", command=(), nodes=(), reserved=True),
            family("TARGET", prerequisites=("RESERVED",)),
        )
        target = 1
        gate_precheck = lambda _gate: None
    elif case == "fail-fast":
        families = (family("FIRST"), family("TARGET"))
        target = 1

        def gate_precheck(gate: GateRequest) -> None:
            if gate.gate_id == "FIRST":
                raise ControllerError("first gate precheck failure")

    else:
        families = (family("TARGET"),)
        target = 0

        def gate_precheck(gate: GateRequest) -> None:
            count = check_calls.get(gate.gate_id, 0)
            check_calls[gate.gate_id] = count + 1
            if count == 1:
                raise ControllerError("postcheck failure")

    catalog = GateCatalog(families, ())
    result = run_wrapper_contract(
        kind="final", matrix="final", module="STM32TK-0601", shard="windows",
        run_id=RUN_ID, evidence_root=evidence, expected_code_head="a" * 40,
        gate_catalog=CATALOG, performance_catalog=RELEASE / "performance_0600.json",
        support_profile=support_profile, controller_path=FINAL, now=lambda: NOW,
        catalog_loader=lambda _path: catalog,
        verifier_blob_checker=lambda _repo, _head: RELEASE / "verify_0600_release.py",
        verifier_invoker=lambda _repo, _head, _argv: SimpleNamespace(returncode=0),
        gate_precheck=gate_precheck,
    )
    terminal_path = evidence / "controller-result.json"
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    row = terminal["gate_results"][target]
    row["reason"] = forged_reason
    if case == "precheck":
        row["status"] = "BLOCKED"
        terminal["status"] = "BLOCKED"
        terminal["reason"] = "CATALOG_FAMILIES_RESERVED"
        terminal["binding"]["status"] = "BLOCKED"
    terminal_path.write_bytes(canonical_json_bytes(terminal))
    package_path = Path(result["package"]["path"])
    package_path.unlink()
    package_reference = create_shard_package(
        evidence,
        package_path,
        terminal["binding"],
        member_paths=terminal["evidence_inventory"],
    )
    package_path.with_name(package_path.name + ".manifest.json").write_bytes(
        canonical_json_bytes(package_reference)
    )
    monkeypatch.setattr(release_verifier, "FROZEN_SUPPORT_PROFILE", support_profile)

    with pytest.raises(VerificationError, match="reason|decision|precheck|postcheck|prerequisite|fail-fast"):
        release_verifier._verify_terminal_result(
            terminal_path, expected_head="a" * 40, expected_mode="final",
            catalog=catalog, catalog_sha256=terminal["catalog_sha256"],
            performance_sha256=terminal["performance_sha256"],
            support_profile_sha256=None,
        )


def test_terminal_verifier_accepts_all_pass_executable_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An all-PASS executable family derives aggregate PASS/PASS, not a reserved reason."""
    support_profile = _write_support(tmp_path / "support-terminal-pass")
    evidence = tmp_path / "final-terminal-pass"
    node = "fixture::passed"
    family = GateFamily(
        family_id="FIXTURE-PASSED", module="STM32TK-0601", matrices=("final-windows",),
        owner_class="Codex/local derived agents", platform_class="windows-python",
        evidence_type="fixture", coverage_context="controller-off",
        command_argv=(
            "py", "-3.12", "-c",
            "import json;print(json.dumps({'schema':'stm32-node-outcome/1','node_id':'fixture::passed','outcome':'passed'}))",
        ),
        node_ids=(node,), prerequisites=(), reserved=False,
    )
    head = "a" * 40
    run_wrapper_contract(
        kind="final", matrix="final", module="STM32TK-0601", shard="windows",
        run_id=RUN_ID, evidence_root=evidence, expected_code_head=head,
        gate_catalog=CATALOG, performance_catalog=RELEASE / "performance_0600.json",
        support_profile=support_profile, controller_path=FINAL, now=lambda: NOW,
        catalog_loader=lambda _path: GateCatalog((family,), ()),
        verifier_blob_checker=lambda _repo, _head: RELEASE / "verify_0600_release.py",
        verifier_invoker=lambda _repo, _head, _argv: SimpleNamespace(returncode=0),
        gate_precheck=lambda _gate: None,
    )
    monkeypatch.setattr(release_verifier, "FROZEN_SUPPORT_PROFILE", support_profile)
    terminal_path = evidence / "controller-result.json"
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))

    assert (terminal["status"], terminal["reason"]) == ("PASS", "PASS")
    assert release_verifier._verify_terminal_result(
        terminal_path, expected_head=head, expected_mode="final",
        catalog=GateCatalog((family,), ()),
        catalog_sha256=terminal["catalog_sha256"],
        performance_sha256=terminal["performance_sha256"],
        support_profile_sha256=None,
    )["status"] == "PASS"


@pytest.mark.parametrize(
    ("emitted_node", "emitted_outcome", "expected_reason"),
    [
        ("fixture::unexpected", "passed", "NODE_INVENTORY_MISMATCH"),
        ("fixture::expected", "skipped", "NODE_OUTCOME_MISMATCH"),
    ],
)
def test_terminal_verifier_accepts_truthful_node_mismatch_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    emitted_node: str,
    emitted_outcome: str,
    expected_reason: str,
) -> None:
    """Retained selected-node/outcome facts must independently prove mismatch failures."""
    support_profile = _write_support(tmp_path / f"support-{expected_reason}")
    evidence = tmp_path / f"final-{expected_reason}"
    command = (
        "py", "-3.12", "-c",
        "import json;print(json.dumps({"
        f"'schema':'stm32-node-outcome/1','node_id':'{emitted_node}',"
        f"'outcome':'{emitted_outcome}'"
        "}))",
    )
    family = GateFamily(
        family_id="FIXTURE-MISMATCH", module="STM32TK-0601",
        matrices=("final-windows",), owner_class="Codex/local derived agents",
        platform_class="windows-python", evidence_type="fixture",
        coverage_context="controller-off", command_argv=command,
        node_ids=("fixture::expected",), prerequisites=(), reserved=False,
    )
    head = "a" * 40
    run_wrapper_contract(
        kind="final", matrix="final", module="STM32TK-0601", shard="windows",
        run_id=RUN_ID, evidence_root=evidence, expected_code_head=head,
        gate_catalog=CATALOG, performance_catalog=RELEASE / "performance_0600.json",
        support_profile=support_profile, controller_path=FINAL, now=lambda: NOW,
        catalog_loader=lambda _path: GateCatalog((family,), ()),
        verifier_blob_checker=lambda _repo, _head: RELEASE / "verify_0600_release.py",
        verifier_invoker=lambda _repo, _head, _argv: SimpleNamespace(returncode=0),
        gate_precheck=lambda _gate: None,
    )
    terminal_path = evidence / "controller-result.json"
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    assert (terminal["gate_results"][0]["status"], terminal["gate_results"][0]["reason"]) == (
        "FAIL", expected_reason
    )
    monkeypatch.setattr(release_verifier, "FROZEN_SUPPORT_PROFILE", support_profile)

    assert release_verifier._verify_terminal_result(
        terminal_path, expected_head=head, expected_mode="final",
        catalog=GateCatalog((family,), ()),
        catalog_sha256=terminal["catalog_sha256"],
        performance_sha256=terminal["performance_sha256"],
        support_profile_sha256=None,
    )["status"] == "FAIL"


def test_terminal_verifier_reparses_retained_stdout_before_deriving_nodes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mutable metadata/result claims cannot contradict the retained process stdout."""
    support_profile = _write_support(tmp_path / "support-stdout-reparse")
    evidence = tmp_path / "final-stdout-reparse"
    expected_node = "fixture::expected"
    family = GateFamily(
        family_id="FIXTURE-STDOUT", module="STM32TK-0601",
        matrices=("final-windows",), owner_class="Codex/local derived agents",
        platform_class="windows-python", evidence_type="fixture",
        coverage_context="controller-off",
        command_argv=(
            "py", "-3.12", "-c",
            "import json;print(json.dumps({'schema':'stm32-node-outcome/1','node_id':'fixture::wrong','outcome':'passed'}))",
        ),
        node_ids=(expected_node,), prerequisites=(), reserved=False,
    )
    head = "a" * 40
    result = run_wrapper_contract(
        kind="final", matrix="final", module="STM32TK-0601", shard="windows",
        run_id=RUN_ID, evidence_root=evidence, expected_code_head=head,
        gate_catalog=CATALOG, performance_catalog=RELEASE / "performance_0600.json",
        support_profile=support_profile, controller_path=FINAL, now=lambda: NOW,
        catalog_loader=lambda _path: GateCatalog((family,), ()),
        verifier_blob_checker=lambda _repo, _head: RELEASE / "verify_0600_release.py",
        verifier_invoker=lambda _repo, _head, _argv: SimpleNamespace(returncode=0),
        gate_precheck=lambda _gate: None,
    )
    terminal_path = evidence / "controller-result.json"
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    metadata = terminal["gate_results"][0]["metadata"]
    forged_outcomes = [{"node_id": expected_node, "outcome": "passed"}]
    metadata["selected_nodes"] = [expected_node]
    metadata["node_outcomes"] = forged_outcomes
    process_path = evidence / "gates" / family.family_id / "result.json"
    process = json.loads(process_path.read_text(encoding="utf-8"))
    process["selected_nodes"] = [expected_node]
    process["node_outcomes"] = forged_outcomes
    process_bytes = canonical_json_bytes(process)
    process_path.write_bytes(process_bytes)
    for reference in metadata["retained_evidence"]:
        if reference["path"].endswith("/result.json"):
            reference["bytes"] = len(process_bytes)
            reference["sha256"] = _sha(process_bytes)
    terminal["gate_results"][0]["status"] = "PASS"
    terminal["gate_results"][0]["reason"] = "PASS"
    terminal["status"] = "PASS"
    terminal["reason"] = "PASS"
    terminal["binding"]["status"] = "PASS"
    terminal_path.write_bytes(canonical_json_bytes(terminal))
    package_path = Path(result["package"]["path"])
    package_path.unlink()
    package_reference = create_shard_package(
        evidence, package_path, terminal["binding"],
        member_paths=terminal["evidence_inventory"],
    )
    package_path.with_name(package_path.name + ".manifest.json").write_bytes(
        canonical_json_bytes(package_reference)
    )
    monkeypatch.setattr(release_verifier, "FROZEN_SUPPORT_PROFILE", support_profile)

    with pytest.raises(VerificationError, match="stdout|node|outcome"):
        release_verifier._verify_terminal_result(
            terminal_path, expected_head=head, expected_mode="final",
            catalog=GateCatalog((family,), ()),
            catalog_sha256=terminal["catalog_sha256"],
            performance_sha256=terminal["performance_sha256"],
            support_profile_sha256=None,
        )


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


def test_terminal_final_evidence_reopens_complete_support_root_and_freezes_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Final verification must revalidate Task 1 support and the closed audit state."""
    evidence = tmp_path / "final-support-audit"
    support_profile = _write_support(tmp_path / "support")
    head = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    run_wrapper_contract(
        kind="final", matrix="final", module="STM32TK-0601", shard="windows",
        run_id=RUN_ID, evidence_root=evidence, expected_code_head=head,
        gate_catalog=CATALOG, performance_catalog=RELEASE / "performance_0600.json",
        support_profile=support_profile, controller_path=FINAL, now=lambda: NOW,
        verifier_blob_checker=lambda _repo, _head: RELEASE / "verify_0600_release.py",
        verifier_invoker=lambda _repo, _head, _argv: SimpleNamespace(returncode=0),
    )
    monkeypatch.setattr(release_verifier, "FROZEN_SUPPORT_PROFILE", support_profile, raising=False)
    checkpoint = evidence / "checkpoint.json"
    terminal = json.loads((evidence / "controller-result.json").read_text(encoding="utf-8"))
    assert terminal["audit"] == {
        "evidence": None,
        "reason": "AUDIT_GATE_RESERVED",
        "schema": "stm32-terminal-audit/1",
        "status": "BLOCKED",
    }
    assert release_verifier.verify_final_evidence_file(
        checkpoint, expected_head=head, readiness=False
    )["status"] == "PASS"

    unexpected = evidence / "unexpected.txt"
    with pytest.raises(VerificationError, match="changed|inventory|unexpected"):
        release_verifier.verify_final_evidence_file(
            checkpoint, expected_head=head, readiness=False,
            before_final_reread=lambda: unexpected.write_text(
                "late mutation", encoding="utf-8"
            ),
        )
    unexpected.unlink()

    with pytest.raises(VerificationError, match="support|manifest|cache|digest"):
        release_verifier.verify_final_evidence_file(
            checkpoint, expected_head=head, readiness=False,
            before_final_reread=lambda: (
                support_profile.parents[1] / "wheelhouse/package.whl"
            ).write_bytes(b"mutated"),
        )


@pytest.mark.parametrize("mutation", ["missing", "forged", "nested-extra"])
def test_terminal_final_audit_is_recursively_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    """Missing, forged, or open audit records cannot be hidden by a replacement package."""
    evidence = tmp_path / f"final-audit-{mutation}"
    support_profile = _write_support(tmp_path / f"support-{mutation}")
    head = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    result = run_wrapper_contract(
        kind="final", matrix="final", module="STM32TK-0601", shard="windows",
        run_id=RUN_ID, evidence_root=evidence, expected_code_head=head,
        gate_catalog=CATALOG, performance_catalog=RELEASE / "performance_0600.json",
        support_profile=support_profile, controller_path=FINAL, now=lambda: NOW,
        verifier_blob_checker=lambda _repo, _head: RELEASE / "verify_0600_release.py",
        verifier_invoker=lambda _repo, _head, _argv: SimpleNamespace(returncode=0),
    )
    monkeypatch.setattr(release_verifier, "FROZEN_SUPPORT_PROFILE", support_profile, raising=False)
    result_path = evidence / "controller-result.json"
    terminal = json.loads(result_path.read_text(encoding="utf-8"))
    if mutation == "missing":
        terminal.pop("audit")
    elif mutation == "forged":
        terminal["audit"] = {
            "schema": "stm32-terminal-audit/1", "status": "PASS",
            "reason": "PASS", "evidence": None,
        }
    else:
        terminal["audit"]["extra"] = None
    result_path.write_bytes(canonical_json_bytes(terminal))
    package_path = Path(result["package"]["path"])
    package_path.unlink()
    reference = create_shard_package(evidence, package_path, result["binding"])
    package_path.with_name(package_path.name + ".manifest.json").write_bytes(
        canonical_json_bytes(reference)
    )

    with pytest.raises(VerificationError, match="audit|closed|terminal"):
        release_verifier.verify_final_evidence_file(
            evidence / "checkpoint.json", expected_head=head, readiness=False
        )
