"""Offline tests for the run-specific SESSION-TRACE helper.

The helper is not packaged.  These tests inject fixed fake backends/launchers
through its private seams and always use temporary lease roots; no real probe,
USB operation, registry or hardware is touched.  Real Windows child processes
exercise the actual CLI chain.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

HELPER_PATH = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "codex"
    / "returns"
    / "SESSION-TRACE"
    / "session_trace.py"
)
SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
PRIVATE_PREFIX = "SESSION_TRACE_PRIVATE_"


def _load_module(name: str = "session_trace_under_test"):
    spec = importlib.util.spec_from_file_location(name, HELPER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


trace = _load_module()


def _env(**extra: object) -> dict[str, str]:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC_ROOT) + ((os.pathsep + existing) if existing else "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for key in list(env):
        if key.startswith(PRIVATE_PREFIX):
            del env[key]
    env.update({key: str(value) for key, value in extra.items()})
    return env


def _paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    project = tmp_path / "project"
    project.mkdir()
    return project, tmp_path / "data", tmp_path / "run"


def _args(
    project: Path,
    data: Path,
    run: Path,
    *,
    probe: str = "fake-probe-1",
    target: str = "STM32F429ZITx",
    deadline: float = 10.0,
) -> list[str]:
    return [
        "run",
        "--output-dir",
        str(run),
        "--data-root",
        str(data),
        "--probe",
        probe,
        "--target",
        target,
        "--project-dir",
        str(project),
        "--deadline-seconds",
        str(deadline),
    ]


def _fake_env(
    tmp_path: Path,
    *,
    mode: str,
    seconds: float | None = None,
    probe: str = "fake-probe-1",
    release: Path | None = None,
) -> tuple[dict[str, str], Path]:
    receipt = tmp_path / "receipt.json"
    extra: dict[str, object] = {
        trace.FAKE_MODE_ENV: mode,
        trace.FAKE_PROBE_ENV: probe,
        trace.FAKE_RECEIPT_ENV: receipt,
    }
    if seconds is not None:
        extra[trace.FAKE_SECONDS_ENV] = seconds
    if release is not None:
        extra[trace.FAKE_RELEASE_ENV] = release
    return _env(**extra), receipt


def _run_cli(
    args: list[str],
    env: dict[str, str],
    tmp_path: Path,
    *,
    timeout: float = 60.0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(HELPER_PATH), *args],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


@pytest.fixture
def release_cleanup():
    """Guarantee the unique inert-child release signal even on failure."""

    pending: list[Path] = []

    def register(path: Path) -> None:
        pending.append(path)

    yield register
    for path in pending:
        try:
            path.write_text("1", encoding="utf-8")
        except OSError:
            pass


def _read(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _wait_for(path: Path, timeout: float) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if path.exists():
            return True
        time.sleep(0.02)
    return False


def _process_alive(pid: int) -> bool:
    assert pid > 0
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True
    import ctypes
    from ctypes import wintypes

    query = 0x1000  # PROCESS_QUERY_LIMITED_INFORMATION
    still_active = 259
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(query, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def _wait_for_death(pid: int, timeout: float) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if not _process_alive(pid):
            return True
        time.sleep(0.02)
    return False


def _record_path(data: Path, selector: str) -> Path:
    digest = hashlib.sha256(selector.encode("utf-8")).hexdigest()
    return data / "probe-registry" / f"{digest}.lock"


def _expected_options(project: Path, target: str = "STM32F429ZITx") -> dict[str, object]:
    return {
        "auto_unlock": False,
        "connect_mode": "halt",
        "dap_protocol": "swd",
        "frequency": 100_000,
        "no_config": True,
        "pack.debug_sequences.enable": True,
        "primary_core": 0,
        "project_dir": str(project),
        "resume_on_disconnect": False,
        "target_override": target,
        "user_script": os.devnull,
    }


def test_default_invocation_refuses_before_any_activity(tmp_path: Path) -> None:
    before = sorted(item.name for item in tmp_path.iterdir())

    assert trace.main([]) == 2

    completed = subprocess.run(
        [sys.executable, "-B", str(HELPER_PATH)],
        cwd=str(tmp_path),
        env=_env(),
        capture_output=True,
        text=True,
        timeout=60.0,
    )

    assert completed.returncode == 2
    assert "refusing" in completed.stderr.lower()
    assert sorted(item.name for item in tmp_path.iterdir()) == before


def test_import_creates_no_files_or_processes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    spawned: list[tuple[object, ...]] = []

    def guarded_popen(*args: object, **kwargs: object) -> object:
        spawned.append(args)
        raise AssertionError("import must not spawn a process")

    monkeypatch.setattr(subprocess, "Popen", guarded_popen)

    module = _load_module("session_trace_import_probe")

    assert spawned == []
    assert list(tmp_path.iterdir()) == []
    assert callable(module.main)
    assert callable(module.child_main)


def test_unknown_or_incomplete_arguments_refuse(tmp_path: Path) -> None:
    assert trace.main(["run"]) == 2
    assert trace.main(["bogus"]) == 2
    assert trace.main(["child"]) == 2
    assert trace.main(["run", "--output-dir", str(tmp_path / "x"), "--bogus", "1"]) == 2
    assert not (tmp_path / "x").exists()


def test_existing_output_directory_is_refused_without_touching_it(
    tmp_path: Path,
) -> None:
    project, data, run = _paths(tmp_path)
    run.mkdir()
    sentinel = run / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")

    completed = _run_cli(_args(project, data, run), _env(), tmp_path)

    assert completed.returncode == 2
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert not (run / trace.REQUEST_FILE).exists()
    assert not (run / trace.ATTEMPT_FILE).exists()


def test_successful_attempt_constructs_once_closes_and_correlates(
    tmp_path: Path,
) -> None:
    project, data, run = _paths(tmp_path)
    env, receipt_path = _fake_env(tmp_path, mode="construct-ok")

    completed = _run_cli(_args(project, data, run), env, tmp_path)

    assert completed.returncode == 0, completed.stderr
    attempt = _read(run / trace.ATTEMPT_FILE)
    claim = _read(run / trace.CLAIM_FILE)
    ready = _read(run / trace.READY_FILE)
    grant = _read(run / trace.GO_FILE)
    result = _read(run / trace.RESULT_FILE)
    events = _read(run / trace.EVENTS_FILE)
    receipt = _read(receipt_path)

    # Parent verdict and honest physical state.
    assert attempt["ok"] is True
    assert attempt["outcome"] == "ok"
    assert attempt["exitCode"] == 0
    assert attempt["physicalTargetState"] == "UNKNOWN"
    assert attempt["grant"] == {"readyMatched": True, "goWritten": True}
    assert attempt["child"]["returncode"] == 0
    assert attempt["child"]["alive"] is False
    assert attempt["child"]["handleReleased"] is True
    assert attempt["errors"] == []
    assert attempt["unexpectedEntries"] == []
    assert attempt["result"]["leaseReleased"] is True

    # Fresh identity and exact request/source/PID/lease correlation.
    assert claim["pid"] == ready["pid"] == grant["pid"] == result["pid"]
    assert claim["pid"] == attempt["child"]["pid"]
    assert claim["attemptId"] == ready["attemptId"] == result["attemptId"]
    assert claim["attemptId"] == attempt["attemptId"]
    assert {
        claim["requestDigest"],
        ready["requestDigest"],
        grant["requestDigest"],
        result["requestDigest"],
        attempt["requestDigest"],
    } == {attempt["requestDigest"]}
    assert claim["sourceDigest"] == ready["sourceDigest"] == result["sourceDigest"]
    assert claim["sourceDigest"] == attempt["sourceDigest"]
    assert ready["leaseId"] == grant["leaseId"] == result["leaseId"]
    assert claim["claimedAtUnix"] <= ready["readyAtUnix"] <= grant["issuedAtUnix"]

    # Exactly one selection and one construction with the accepted options.
    assert result["ok"] is True
    assert result["outcome"] == "ok"
    assert result["physicalTargetState"] == "UNKNOWN"
    facts = result["facts"]
    assert facts["driverAcquired"] == 1
    assert facts["enumerations"] == 1
    assert facts["selections"] == 1
    assert facts["sessionConstructed"] is True
    assert facts["sessionOpened"] is False
    assert facts["sessionClosed"] == 1
    assert facts["forbiddenCalls"] == []
    assert facts["probeFingerprint"] == hashlib.sha256(b"fake-probe-1").hexdigest()
    assert result["errors"] == {key: None for key in trace.CHILD_ERROR_KEYS}
    assert result["sessionOptions"] == _expected_options(project)

    assert receipt["listProbes"] == 1
    assert receipt["createSession"] == 1
    assert receipt["selectedIsProbe"] is True
    assert receipt["sessionOpenCalls"] == 0
    assert receipt["sessionCloseCalls"] == 1
    assert receipt["forbiddenCalls"] == []
    assert receipt["options"] == _expected_options(project)

    # Bounded fixed stage markers only.
    stages = [entry["stage"] for entry in events["events"]]
    for required in (
        "claim-reserved",
        "lease-acquired",
        "ready-published",
        "go-accepted",
        "driver-acquired",
        "probe-enumerated",
        "probe-selected",
        "faulthandler-armed",
        "session-constructed",
        "session-closed",
        "lease-released",
    ):
        assert required in stages
    assert all(entry["elapsedMs"] >= 0 for entry in events["events"])

    # The private traceback file is bounded metadata plus file/function frames.
    traceback_file = run / trace.TRACEBACK_FILE
    assert traceback_file.exists()
    assert attempt["traceback"]["bytes"] == traceback_file.stat().st_size
    assert result["traceback"]["armed"] is True
    assert result["traceback"]["cancelled"] is True

    # The child-owned lease is released and the registry is reusable.
    record = _read(_record_path(data, "fake-probe-1"))
    assert record["state"] == "released"
    from stm32_toolkit.probe.lease import ProbeLeaseManager
    from stm32_toolkit.probe.model import OperationLevel

    manager = ProbeLeaseManager(data)
    reused = manager.acquire(
        probe_id="fake-probe-1",
        workspace_id="reuse-check",
        session_id="reuse-session",
        operation_level=OperationLevel.OBSERVE,
        health_url="http://127.0.0.1:65535/health",
    )
    reused.release()


def test_second_child_and_second_parent_refuse_reuse(tmp_path: Path) -> None:
    project, data, run = _paths(tmp_path)
    env, _receipt = _fake_env(tmp_path, mode="construct-ok")

    assert _run_cli(_args(project, data, run), env, tmp_path).returncode == 0
    result_before = (run / trace.RESULT_FILE).read_bytes()
    claim_before = (run / trace.CLAIM_FILE).read_bytes()

    second_child = subprocess.run(
        [sys.executable, "-B", str(HELPER_PATH), "child", str(run)],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=60.0,
    )

    assert second_child.returncode != 0
    assert (run / trace.RESULT_FILE).read_bytes() == result_before
    assert (run / trace.CLAIM_FILE).read_bytes() == claim_before
    assert _run_cli(_args(project, data, run), env, tmp_path).returncode == 2


def _hold_lease(data: Path, workspace: str = "holder"):
    from stm32_toolkit.probe.lease import ProbeLeaseManager
    from stm32_toolkit.probe.model import OperationLevel

    manager = ProbeLeaseManager(data)
    return manager.acquire(
        probe_id="fake-probe-1",
        workspace_id=workspace,
        session_id="holder-session",
        operation_level=OperationLevel.OBSERVE,
        health_url="http://127.0.0.1:65535/health",
    )


def test_busy_probe_denies_ready_and_construction(tmp_path: Path) -> None:
    project, data, run = _paths(tmp_path)
    env, receipt_path = _fake_env(tmp_path, mode="construct-ok")
    holder = _hold_lease(data)
    try:
        completed = _run_cli(
            _args(project, data, run, deadline=5.0), env, tmp_path
        )

        assert completed.returncode != 0
        result = _read(run / trace.RESULT_FILE)
        assert result["outcome"] == "busy"
        assert result["ok"] is False
        assert result["errors"]["lease"] == "PROBE_BUSY"
        assert result["facts"]["sessionConstructed"] is False
        assert result["leaseId"] is None
        assert not (run / trace.READY_FILE).exists()
        assert not (run / trace.GO_FILE).exists()
        assert not receipt_path.exists()
        record = _read(_record_path(data, "fake-probe-1"))
        assert record["leaseId"] == holder.lease_id
        assert record["state"] == "active"
    finally:
        holder.release()


def test_external_handoff_owner_is_refused_not_taken_over(tmp_path: Path) -> None:
    project, data, run = _paths(tmp_path)
    env, receipt_path = _fake_env(tmp_path, mode="construct-ok")
    holder = _hold_lease(data, workspace="handoff-holder")
    ticket = "a" * 64
    holder.reserve_external_handoff(ticket)
    holder.release()

    completed = _run_cli(_args(project, data, run, deadline=5.0), env, tmp_path)

    assert completed.returncode != 0
    result = _read(run / trace.RESULT_FILE)
    assert result["outcome"] == "busy"
    assert result["errors"]["lease"] == "PROBE_BUSY"
    assert not (run / trace.GO_FILE).exists()
    assert not receipt_path.exists()
    record = _read(_record_path(data, "fake-probe-1"))
    assert record["state"] == "externally-owned"
    assert record["ticketSha256"] == hashlib.sha256(ticket.encode("ascii")).hexdigest()


def test_constructor_error_reports_narrow_facts_and_releases_lease(
    tmp_path: Path,
) -> None:
    project, data, run = _paths(tmp_path)
    env, receipt_path = _fake_env(tmp_path, mode="construct-error")

    completed = _run_cli(_args(project, data, run), env, tmp_path)

    assert completed.returncode == 6
    attempt = _read(run / trace.ATTEMPT_FILE)
    result = _read(run / trace.RESULT_FILE)
    receipt = _read(receipt_path)
    assert attempt["ok"] is False
    assert attempt["grant"]["goWritten"] is True
    assert result["ok"] is False
    assert result["outcome"] == "construct-error"
    assert result["errors"]["construction"] == "RuntimeError"
    assert result["facts"]["sessionConstructed"] is False
    assert result["facts"]["sessionClosed"] == 0
    assert result["facts"]["forbiddenCalls"] == []
    assert result["traceback"]["armed"] is True
    assert result["traceback"]["cancelled"] is True
    assert attempt["result"]["leaseReleased"] is True
    assert receipt["createSession"] == 1
    assert receipt["sessionCloseCalls"] == 0
    assert _read(_record_path(data, "fake-probe-1"))["state"] == "released"


def test_session_close_error_is_an_overall_failure(tmp_path: Path) -> None:
    project, data, run = _paths(tmp_path)
    env, receipt_path = _fake_env(tmp_path, mode="close-error")

    completed = _run_cli(_args(project, data, run), env, tmp_path)

    assert completed.returncode == 6
    result = _read(run / trace.RESULT_FILE)
    receipt = _read(receipt_path)
    assert result["ok"] is False
    assert result["outcome"] == "internal-error"
    assert result["facts"]["sessionConstructed"] is True
    assert result["facts"]["sessionClosed"] == 0
    assert result["errors"]["sessionClose"] == "RuntimeError"
    assert receipt["sessionCloseCalls"] == 1
    assert _read(_record_path(data, "fake-probe-1"))["state"] == "released"


def test_native_faulthandler_captures_blocked_constructor(tmp_path: Path) -> None:
    project, data, run = _paths(tmp_path)
    env, _receipt = _fake_env(
        tmp_path, mode="construct-block-exit", seconds=1.5
    )

    completed = _run_cli(_args(project, data, run), env, tmp_path)

    assert completed.returncode == 0, completed.stderr
    result = _read(run / trace.RESULT_FILE)
    attempt = _read(run / trace.ATTEMPT_FILE)
    text = (run / trace.TRACEBACK_FILE).read_text(
        encoding="utf-8", errors="replace"
    )
    assert result["ok"] is True
    assert result["traceback"]["armed"] is True
    assert result["traceback"]["cancelled"] is True
    assert result["traceback"]["bytes"] > 0
    assert attempt["traceback"]["bytes"] == (run / trace.TRACEBACK_FILE).stat().st_size
    assert "_block" in text
    assert "create_session" in text
    assert "File " in text
    assert "line" in text


def test_selection_mismatch_constructs_nothing(tmp_path: Path) -> None:
    project, data, run = _paths(tmp_path)
    env, receipt_path = _fake_env(tmp_path, mode="construct-ok")

    completed = _run_cli(
        _args(project, data, run, probe="other-probe"), env, tmp_path
    )

    assert completed.returncode == 6
    result = _read(run / trace.RESULT_FILE)
    receipt = _read(receipt_path)
    assert result["outcome"] == "selection-error"
    assert result["facts"]["selections"] == 0
    assert result["facts"]["sessionConstructed"] is False
    assert result["sessionOptions"] is None
    assert receipt["createSession"] == 0
    assert receipt["forbiddenCalls"] == []
    assert _read(_record_path(data, "other-probe"))["state"] == "released"


def test_bad_ready_never_grants_go(tmp_path: Path) -> None:
    project, data, run = _paths(tmp_path)
    env, receipt_path = _fake_env(tmp_path, mode="bad-ready")

    completed = _run_cli(_args(project, data, run, deadline=2.0), env, tmp_path)

    assert completed.returncode == 3
    attempt = _read(run / trace.ATTEMPT_FILE)
    result = _read(run / trace.RESULT_FILE)
    assert (run / trace.CLAIM_FILE).exists()
    assert (run / trace.READY_FILE).exists()
    assert not (run / trace.GO_FILE).exists()
    assert attempt["grant"] == {"readyMatched": False, "goWritten": False}
    assert attempt["ok"] is False
    assert result["outcome"] in ("cancelled-before-go", "go-timeout")
    assert result["facts"]["sessionConstructed"] is False
    assert not receipt_path.exists()


def test_partial_start_without_ready_never_grants_go(tmp_path: Path) -> None:
    project, data, run = _paths(tmp_path)
    env, receipt_path = _fake_env(tmp_path, mode="no-ready")

    completed = _run_cli(_args(project, data, run, deadline=3.0), env, tmp_path)

    assert completed.returncode == 3
    attempt = _read(run / trace.ATTEMPT_FILE)
    result = _read(run / trace.RESULT_FILE)
    assert (run / trace.CLAIM_FILE).exists()
    assert not (run / trace.READY_FILE).exists()
    assert not (run / trace.GO_FILE).exists()
    assert attempt["grant"]["goWritten"] is False
    assert result["outcome"] == "startup-aborted"
    assert result["ok"] is False
    assert not receipt_path.exists()


def _config(project: Path, data: Path, run: Path, deadline: float = 3.0):
    return trace.AttemptConfig(
        output_dir=run,
        data_root=data,
        probe_selector="fake-probe-1",
        target="STM32F429ZITx",
        project_dir=project,
        deadline_seconds=deadline,
    )


def test_cancellation_before_start_never_launches_or_grants(
    tmp_path: Path,
) -> None:
    project, data, run = _paths(tmp_path)
    cancel = threading.Event()
    cancel.set()

    outcome = trace.run_attempt(_config(project, data, run), cancel_event=cancel)

    assert outcome.outcome == "cancelled"
    assert outcome.ok is False
    assert outcome.exit_code == 5
    attempt = _read(run / trace.ATTEMPT_FILE)
    assert attempt["child"]["pid"] is None
    assert attempt["grant"] == {"readyMatched": False, "goWritten": False}
    assert not (run / trace.READY_FILE).exists()
    assert not (run / trace.GO_FILE).exists()
    assert not (run / trace.CLAIM_FILE).exists()


def test_launcher_failure_reports_unknown_without_granting(tmp_path: Path) -> None:
    project, data, run = _paths(tmp_path)

    def failing_launcher(argv: object, cwd: object) -> object:
        raise OSError("spawn failed")

    outcome = trace.run_attempt(
        _config(project, data, run), launcher=failing_launcher
    )

    assert outcome.outcome == "startup-failed"
    assert outcome.ok is False
    assert outcome.exit_code == 7
    attempt = _read(run / trace.ATTEMPT_FILE)
    assert attempt["child"]["pid"] is None
    assert attempt["child"]["alive"] is None
    assert attempt["grant"] == {"readyMatched": False, "goWritten": False}
    assert "launch-failed" in attempt["errors"]
    assert not (run / trace.GO_FILE).exists()


def test_parent_timeout_with_surviving_inert_child_is_bounded(
    tmp_path: Path, release_cleanup
) -> None:
    project, data, run = _paths(tmp_path)
    release = tmp_path / "unique-release-1.signal"
    release_cleanup(release)
    env, _receipt = _fake_env(
        tmp_path,
        mode="construct-block-stubborn",
        seconds=14.0,
        release=release,
    )

    started = time.monotonic()
    completed = _run_cli(
        _args(project, data, run, deadline=6.0), env, tmp_path, timeout=45.0
    )
    elapsed = time.monotonic() - started

    assert completed.returncode == 4
    assert elapsed < 14.0
    attempt = _read(run / trace.ATTEMPT_FILE)
    assert attempt["grant"] == {"readyMatched": True, "goWritten": True}
    assert attempt["ok"] is False
    assert attempt["child"]["alive"] is True
    assert attempt["child"]["handleReleased"] is False
    assert attempt["termination"] == {
        "terminateRequested": True,
        "joined": False,
        "alive": True,
    }
    assert (run / trace.TERMINATE_FILE).exists()
    pid = attempt["child"]["pid"]
    assert isinstance(pid, int)
    assert _process_alive(pid)
    assert not (run / trace.RESULT_FILE).exists()

    # The child still holds its real exact-probe OBSERVE lease and answers on
    # its real loopback-only health endpoint.
    record = _read(_record_path(data, "fake-probe-1"))
    assert record["state"] == "active"
    assert record["operationLevel"] == "observe"
    assert record["probeId"] == "fake-probe-1"
    lease_id = record["leaseId"]
    health_url = record["healthUrl"]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(
        urllib.request.Request(
            health_url, headers={"X-Probe-Lease": lease_id}, method="GET"
        ),
        timeout=2.0,
    ) as response:
        health = json.loads(response.read().decode("utf-8"))
    assert set(health) == {"ok", "protocol", "toolkitVersion", "leaseId"}
    assert health["ok"] is True
    assert health["leaseId"] == lease_id
    with pytest.raises(urllib.error.HTTPError):
        opener.open(
            urllib.request.Request(
                health_url, headers={"X-Probe-Lease": "lease-wrong"}, method="GET"
            ),
            timeout=2.0,
        )

    # The native stack is already captured while the child is still alive.
    text = (run / trace.TRACEBACK_FILE).read_text(
        encoding="utf-8", errors="replace"
    )
    assert "_block" in text

    release.write_text("1", encoding="utf-8")
    assert _wait_for(run / trace.RESULT_FILE, 20.0)
    assert _wait_for_death(pid, 20.0)
    result = _read(run / trace.RESULT_FILE)
    assert result["outcome"] == "cancelled-after-go"
    assert result["ok"] is False
    assert result["traceback"]["bytes"] > 0
    assert result["traceback"]["cancelled"] is True
    assert _read(_record_path(data, "fake-probe-1"))["state"] == "released"


@pytest.mark.skipif(
    os.name != "nt" or not hasattr(signal, "CTRL_BREAK_EVENT"),
    reason="native Windows process-group cancellation",
)
def test_parent_cancellation_with_surviving_inert_child_is_bounded(
    tmp_path: Path, release_cleanup
) -> None:
    project, data, run = _paths(tmp_path)
    release = tmp_path / "unique-release-2.signal"
    release_cleanup(release)
    env, _receipt = _fake_env(
        tmp_path,
        mode="construct-block-stubborn",
        seconds=12.0,
        release=release,
    )
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    process = subprocess.Popen(
        [sys.executable, "-B", str(HELPER_PATH), *_args(project, data, run, deadline=15.0)],
        cwd=str(tmp_path),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=flags,
    )
    try:
        assert _wait_for(run / trace.GO_FILE, 10.0)
        time.sleep(0.25)
        cancelled_at = time.monotonic()
        process.send_signal(signal.CTRL_BREAK_EVENT)
        stdout, stderr = process.communicate(timeout=20.0)
        elapsed = time.monotonic() - cancelled_at
        assert process.returncode == 5, stderr
        assert elapsed < 8.0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5.0)

    attempt = _read(run / trace.ATTEMPT_FILE)
    assert attempt["outcome"] == "cancelled"
    assert attempt["grant"]["goWritten"] is True
    assert attempt["child"]["alive"] is True
    assert attempt["termination"]["terminateRequested"] is True
    pid = attempt["child"]["pid"]
    assert isinstance(pid, int)
    assert _process_alive(pid)

    release.write_text("1", encoding="utf-8")
    assert _wait_for_death(pid, 20.0)
    assert _wait_for(run / trace.RESULT_FILE, 20.0)
    result = _read(run / trace.RESULT_FILE)
    assert result["outcome"] == "cancelled-after-go"
    assert result["ok"] is False
    assert result["traceback"]["bytes"] > 0
    assert result["traceback"]["cancelled"] is True


def test_go_record_validation_refuses_any_identity_mismatch(tmp_path: Path) -> None:
    project, data, run = _paths(tmp_path)
    request = trace._build_request(
        _config(project, data, run),
        attempt_id="attempt-" + "1" * 32,
        session_id="session-" + "2" * 32,
        deadline_wall=time.time() + 10.0,
    )
    interpreter = os.path.abspath(sys.executable)
    source_digest = "c" * 64
    good = {
        "schemaVersion": 1,
        "attemptId": request["attemptId"],
        "requestDigest": request["requestDigest"],
        "pid": 4321,
        "sourceDigest": source_digest,
        "interpreter": interpreter,
        "leaseId": "lease-" + "3" * 32,
        "issuedAtUnix": time.time(),
    }

    trace._validate_go(
        good, request=request, pid=4321, source_digest=source_digest, interpreter=interpreter
    )

    mutations = (
        {"pid": 4322},
        {"requestDigest": "0" * 64},
        {"attemptId": "attempt-" + "9" * 32},
        {"sourceDigest": "d" * 64},
        {"leaseId": "not a lease"},
    )
    for mutation in mutations:
        with pytest.raises(trace.SessionTraceError):
            trace._validate_go(
                {**good, **mutation},
                request=request,
                pid=4321,
                source_digest=source_digest,
                interpreter=interpreter,
            )
    with pytest.raises(trace.SessionTraceError):
        trace._validate_go(
            {**good, "extra": 1},
            request=request,
            pid=4321,
            source_digest=source_digest,
            interpreter=interpreter,
        )


def test_request_digest_bounds_and_tamper_are_rejected(tmp_path: Path) -> None:
    project, data, run = _paths(tmp_path)
    request = trace._build_request(
        _config(project, data, run),
        attempt_id="attempt-" + "1" * 32,
        session_id="session-" + "2" * 32,
        deadline_wall=time.time() + 10.0,
    )
    assert trace._validate_request(request)["requestDigest"] == request["requestDigest"]
    with pytest.raises(trace.SessionTraceError):
        trace._validate_request({**request, "target": "OTHER_TARGET"})
    with pytest.raises(trace.SessionTraceError):
        trace._validate_request({**request, "extra": 1})

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * (trace.MAX_RUN_FILE_BYTES + 1))
    with pytest.raises(trace.SessionTraceError):
        trace._read_json_until(oversized, time.time() + 1.0)


def test_partial_json_write_is_awaited_finitely(tmp_path: Path) -> None:
    path = tmp_path / "partial.json"
    payload = {"marker": "complete"}
    raw = json.dumps(payload).encode("utf-8")
    path.write_bytes(raw[:2])

    def finish() -> None:
        time.sleep(0.05)
        path.write_bytes(raw)

    thread = threading.Thread(target=finish)
    thread.start()
    try:
        assert trace._read_json_until(path, time.time() + 5.0) == payload
    finally:
        thread.join(timeout=5.0)


def test_terminal_handle_release_is_explicit_and_reports_failures() -> None:
    class Handle:
        def __init__(self, error: BaseException | None = None) -> None:
            self.closed = False
            self.error = error

        def Close(self) -> None:
            self.closed = True
            if self.error is not None:
                raise self.error

    class Process:
        def __init__(self, returncode: int | None, handle: Handle) -> None:
            self.returncode = returncode
            self._handle = handle

        def poll(self) -> int | None:
            return self.returncode

        def wait(self, timeout: float | None = None) -> int | None:
            return self.returncode

    handle = Handle()
    released = Process(7, handle)
    assert trace._release_terminal_process_handles(released) == []
    assert handle.closed is True
    assert released._handle is None

    failing = Process(7, Handle(OSError("close failed")))
    assert "process-handle-close-failed" in trace._release_terminal_process_handles(
        failing
    )

    class Live:
        def poll(self) -> None:
            return None

    assert trace._release_terminal_process_handles(Live()) == ["process-not-terminal"]


def test_lease_release_failure_is_reported() -> None:
    class FailingLease:
        def release(self) -> None:
            raise RuntimeError("release failed")

    assert trace._release_lease(FailingLease()) == "RuntimeError"


def test_faulthandler_arm_failure_prevents_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class CountingDriver:
        def __init__(self) -> None:
            self.created = 0

        def create_session(self, probe: object, *, options: object) -> object:
            self.created += 1
            return object()

    def failing_arm(*args: object, **kwargs: object) -> None:
        raise RuntimeError("arm failed")

    monkeypatch.setattr(trace.faulthandler, "dump_traceback_later", failing_arm)
    driver = CountingDriver()
    facts = trace._new_facts()
    errors: dict[str, str | None] = {key: None for key in trace.CHILD_ERROR_KEYS}
    meta: dict[str, object] = {"armed": False, "bytes": 0, "cancelled": False}
    events: list[dict[str, object]] = []

    trace._construct_and_close(
        facts,
        errors,
        meta,
        driver=driver,
        probe=object(),
        options={},
        traceback_path=tmp_path / "trace.txt",
        events=events,
        started=time.monotonic(),
    )

    assert driver.created == 0
    assert errors["tracebackArm"] == "faulthandler-arm-failed"
    assert facts["sessionConstructed"] is False
    assert meta["armed"] is False
    assert trace._child_ok("ok", facts, errors) is False


def test_faulthandler_cancel_failure_is_visible_and_not_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Session:
        def __init__(self) -> None:
            self.closed = 0

        def close(self) -> None:
            self.closed += 1

    class Driver:
        def __init__(self) -> None:
            self.session = Session()
            self.created = 0

        def create_session(self, probe: object, *, options: object) -> Session:
            self.created += 1
            return self.session

    def silent_arm(*args: object, **kwargs: object) -> None:
        return None

    def failing_cancel() -> None:
        raise RuntimeError("cancel failed")

    monkeypatch.setattr(trace.faulthandler, "dump_traceback_later", silent_arm)
    monkeypatch.setattr(
        trace.faulthandler, "cancel_dump_traceback_later", failing_cancel
    )
    driver = Driver()
    facts = trace._new_facts()
    errors: dict[str, str | None] = {key: None for key in trace.CHILD_ERROR_KEYS}
    meta: dict[str, object] = {"armed": False, "bytes": 0, "cancelled": False}

    trace._construct_and_close(
        facts,
        errors,
        meta,
        driver=driver,
        probe=object(),
        options={},
        traceback_path=tmp_path / "trace.txt",
        events=[],
        started=time.monotonic(),
    )

    assert driver.created == 1
    assert driver.session.closed == 1
    assert errors["tracebackCancel"] == "faulthandler-cancel-failed"
    assert facts["sessionConstructed"] is True
    assert facts["sessionClosed"] == 1
    assert meta["armed"] is True
    assert meta["cancelled"] is False
    assert trace._child_ok("ok", facts, errors) is False


def test_real_result_and_claim_records_validate_and_reject_mutation(
    tmp_path: Path,
) -> None:
    project, data, run = _paths(tmp_path)
    env, _receipt = _fake_env(tmp_path, mode="construct-ok")
    assert _run_cli(_args(project, data, run), env, tmp_path).returncode == 0

    request = _read(run / trace.REQUEST_FILE)
    result = _read(run / trace.RESULT_FILE)
    claim = _read(run / trace.CLAIM_FILE)

    kwargs = {
        "attempt_id": str(result["attemptId"]),
        "request_digest": str(result["requestDigest"]),
        "pid": int(result["pid"]),
        "source_digest": str(result["sourceDigest"]),
        "lease_id": str(result["leaseId"]),
        "request": request,
        "interpreter": str(result["interpreter"]),
    }
    trace._validate_result(result, **kwargs)

    with pytest.raises(trace.SessionTraceError):
        trace._validate_result({**result, "pid": int(result["pid"]) + 1}, **kwargs)
    with pytest.raises(trace.SessionTraceError):
        trace._validate_result({**result, "extra": 1}, **kwargs)
    with pytest.raises(trace.SessionTraceError):
        trace._validate_result(
            {**result, "physicalTargetState": "CONNECTED"}, **kwargs
        )

    trace._validate_claim(
        claim,
        attempt_id=str(claim["attemptId"]),
        request_digest=str(claim["requestDigest"]),
        pid=int(claim["pid"]),
        source_digest=str(claim["sourceDigest"]),
        interpreter=str(claim["interpreter"]),
    )
    with pytest.raises(trace.SessionTraceError):
        trace._validate_claim(
            {**claim, "pid": int(claim["pid"]) + 1},
            attempt_id=str(claim["attemptId"]),
            request_digest=str(claim["requestDigest"]),
            pid=int(claim["pid"]),
            source_digest=str(claim["sourceDigest"]),
            interpreter=str(claim["interpreter"]),
        )
