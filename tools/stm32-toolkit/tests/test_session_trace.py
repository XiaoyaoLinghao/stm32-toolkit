"""Offline tests for the run-specific SESSION-TRACE helper.

The helper is not packaged.  These tests never touch a real probe, USB
operation, registry or hardware: every inert fake driver, fake launch profile
and test-owned receipt lives in this module, and the helper receives them only
through its explicit Python-only private injection seam.  Real Windows child
processes exercise the actual helper ``main``/``child`` chain; the fixed test
bootstrap below is test-only and is never reachable from a production
environment variable, CLI argument or request record.
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
from collections.abc import Mapping, Sequence
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
TEST_MODULE_PATH = Path(__file__).resolve()
SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

# Former helper-side environment switches.  They must have no effect at all;
# the tests set them and still require the production launcher/backend.
REMOVED_FAKE_ENV = (
    "SESSION_TRACE_FAKE_MODE",
    "SESSION_TRACE_FAKE_PROBE",
    "SESSION_TRACE_FAKE_RECEIPT",
    "SESSION_TRACE_FAKE_SECONDS",
    "SESSION_TRACE_FAKE_RELEASE",
    "SESSION_TRACE_PRIVATE_MODE",
)


def _load_module(
    name: str = "session_trace_under_test", path: Path = HELPER_PATH
):
    """Load the saved helper exactly as a bootstrap importer would.

    The module is registered in ``sys.modules`` before ``exec_module`` so the
    dataclass machinery can resolve its own module (the historical collection
    failure), and a failed import deliberately removes exactly that entry.
    """

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    previous_module = sys.modules.get(name)
    previous_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if previous_module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous_module
        raise
    finally:
        sys.dont_write_bytecode = previous_bytecode
    return module


trace = _load_module()


@pytest.fixture(autouse=True)
def _clean_private_injection():
    """Never let an inert fake or fake launcher leak between tests."""

    trace._install_private_test_injection()
    yield
    trace._install_private_test_injection()


def _env(**extra: object) -> dict[str, str]:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC_ROOT) + ((os.pathsep + existing) if existing else "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for key in REMOVED_FAKE_ENV:
        env.pop(key, None)
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


def _config(project: Path, data: Path, run: Path, deadline: float = 3.0):
    return trace.AttemptConfig(
        output_dir=run,
        data_root=data,
        probe_selector="fake-probe-1",
        target="STM32F429ZITx",
        project_dir=project,
        deadline_seconds=deadline,
    )


def _read(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


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


def _expected_options(
    project: Path, target: str = "STM32F429ZITx"
) -> dict[str, object]:
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


@pytest.fixture
def release_cleanup():
    """Guarantee the unique test-owned inert-child release signal."""

    pending: list[Path] = []

    def register(path: Path) -> None:
        pending.append(path)

    yield register
    for path in pending:
        try:
            path.write_text("1", encoding="utf-8")
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Inert fakes (test module only; never selected by the production helper)
# ---------------------------------------------------------------------------


def _block(seconds: float) -> None:
    """Bounded wait whose frame is expected in the native traceback dump."""

    end = time.monotonic() + seconds
    while time.monotonic() < end:
        time.sleep(0.02)


def _block_until_release(seconds: float, release: str | None) -> None:
    """Bounded wait released only by this test's unique signal file."""

    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if release is not None and Path(release).exists():
            return
        time.sleep(0.02)


class _FakeProbe:
    unique_id = "fake-probe-1"


class _FakeSession:
    def __init__(self, driver: "_FakeDriver") -> None:
        self._driver = driver

    def open(self) -> None:
        self._driver.calls["sessionOpenCalls"] += 1  # type: ignore[index]
        self._driver.forbidden("open")

    def close(self) -> None:
        self._driver.calls["sessionCloseCalls"] += 1  # type: ignore[index]
        self._driver.write_receipt()
        if self._driver.mode == "close-error":
            raise RuntimeError("session close failed")

    def halt(self) -> None:
        self._driver.forbidden("halt")

    def resume(self) -> None:
        self._driver.forbidden("resume")

    def reset(self) -> None:
        self._driver.forbidden("reset")


class _FakeDriver:
    """One inert fake driver behind the real ``PyOCDBackend`` seam."""

    def __init__(self, profile: Mapping[str, object]) -> None:
        self.mode = str(profile.get("mode", "construct-ok"))
        self.seconds = float(profile.get("seconds") or 0.0)
        release = profile.get("release")
        self.release = None if release is None else str(release)
        receipt = profile.get("receipt")
        self.receipt = None if receipt is None else str(receipt)
        self.probe = _FakeProbe()
        self.calls: dict[str, object] = {
            "listProbes": 0,
            "createSession": 0,
            "selectedIsProbe": False,
            "sessionOpenCalls": 0,
            "sessionCloseCalls": 0,
            "forbiddenCalls": [],
            "options": None,
        }

    def write_receipt(self) -> None:
        if self.receipt is None:
            return
        Path(self.receipt).write_text(
            json.dumps(self.calls, sort_keys=True), encoding="utf-8"
        )

    def forbidden(self, name: str) -> None:
        forbidden = self.calls["forbiddenCalls"]
        assert isinstance(forbidden, list)
        forbidden.append(name)
        raise AssertionError(f"forbidden target call: {name}")

    def list_probes(self) -> tuple[object, ...]:
        self.calls["listProbes"] = int(self.calls["listProbes"]) + 1
        self.write_receipt()
        return (self.probe,)

    def create_session(
        self, probe: object, *, options: Mapping[str, object]
    ) -> object:
        self.calls["createSession"] = int(self.calls["createSession"]) + 1
        self.calls["selectedIsProbe"] = probe is self.probe
        self.calls["options"] = dict(options)
        self.write_receipt()
        if self.mode == "construct-error":
            raise RuntimeError("constructor failed")
        if self.mode == "construct-block-exit":
            _block(self.seconds)
        elif self.mode == "construct-block-stubborn":
            _block_until_release(self.seconds, self.release)
        return _FakeSession(self)

    def program_file(
        self, session: object, image: bytes, *, options: Mapping[str, object]
    ) -> None:
        self.forbidden("program_file")


def _make_driver_factory(profile: Mapping[str, object]):
    """Return the private backend factory seam value (a driver object)."""

    created: list[_FakeDriver] = []

    def factory() -> _FakeDriver:
        driver = _FakeDriver(profile)
        created.append(driver)
        return driver

    factory.created = created  # type: ignore[attr-defined]
    return factory


# ---------------------------------------------------------------------------
# Fixed test bootstrap (a separate real process; never a production capability)
# ---------------------------------------------------------------------------


def _make_child_launcher(config_path: Path):
    """Launch the fixed test child bootstrap instead of the raw helper child."""

    def launcher(argv: Sequence[str], cwd: str) -> object:
        argv = list(argv)
        # The parent must still have built the production child argv exactly;
        # only the test bootstrap substitutes the executable entry point.
        assert argv[3] == "child"
        output_dir = argv[4]
        return subprocess.Popen(
            [
                sys.executable,
                "-B",
                str(TEST_MODULE_PATH),
                "trace-child",
                str(config_path),
                output_dir,
            ],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=CREATE_NEW_PROCESS_GROUP,
            env=_env(),
        )

    return launcher


def _make_spy_launcher(config_path: Path):
    """Launch the fixed protocol spy child used for parent-validation cases."""

    def launcher(argv: Sequence[str], cwd: str) -> object:
        argv = list(argv)
        assert argv[3] == "child"
        output_dir = argv[4]
        return subprocess.Popen(
            [
                sys.executable,
                "-B",
                str(TEST_MODULE_PATH),
                "spy",
                str(config_path),
                output_dir,
            ],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=CREATE_NEW_PROCESS_GROUP,
            env=_env(),
        )

    return launcher


def _write_child_profile(tmp_path: Path, profile: Mapping[str, object]) -> Path:
    path = tmp_path / "child-profile.json"
    _write_json(path, {"profile": dict(profile)})
    return path


def _install_child_launcher(
    tmp_path: Path, profile: Mapping[str, object]
) -> Path:
    path = _write_child_profile(tmp_path, profile)
    trace._install_private_test_injection(launcher=_make_child_launcher(path))
    return path


def _install_spy_launcher(tmp_path: Path, scenario: Mapping[str, object]) -> None:
    path = tmp_path / "spy-profile.json"
    _write_json(path, dict(scenario))
    trace._install_private_test_injection(launcher=_make_spy_launcher(path))


def _write_parent_config(
    tmp_path: Path, profile: Mapping[str, object], argv: Sequence[str]
) -> Path:
    child_profile = dict(profile)
    child_path = _write_child_profile(tmp_path, child_profile)
    child_profile["configPath"] = str(child_path)
    _write_json(child_path, {"profile": child_profile})
    path = tmp_path / "parent-profile.json"
    _write_json(path, {"profile": child_profile, "argv": list(argv)})
    return path


def _run_parent_cli(
    config_path: Path, *, timeout: float = 60.0
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-B",
            str(TEST_MODULE_PATH),
            "trace-parent",
            str(config_path),
        ],
        cwd=str(config_path.parent),
        env=_env(),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _spy_run(
    scenario: Mapping[str, object], output_dir: Path
) -> int:
    """Emit exactly one crafted READY/CLAIM shape, then wait to be stopped."""

    assert _wait_for(output_dir / trace.REQUEST_FILE, 15.0)
    request = _read(output_dir / trace.REQUEST_FILE)
    base: dict[str, object] = {
        "schemaVersion": trace.SCHEMA_VERSION,
        "attemptId": request["attemptId"],
        "requestDigest": request["requestDigest"],
        "pid": os.getpid(),
        "sourceDigest": hashlib.sha256(HELPER_PATH.read_bytes()).hexdigest(),
        "interpreter": os.path.abspath(sys.executable),
    }
    claim = {**base, "claimedAtUnix": time.time()}
    ready = {**base, "leaseId": "lease-" + "a" * 32, "readyAtUnix": time.time()}
    kind = str(scenario.get("kind"))
    if kind == "claim-and-ready":
        _write_json(output_dir / trace.CLAIM_FILE, claim)
        _write_json(output_dir / trace.READY_FILE, ready)
    elif kind == "claim-only":
        _write_json(output_dir / trace.CLAIM_FILE, claim)
    elif kind == "ready-without-claim":
        _write_json(output_dir / trace.READY_FILE, ready)
    elif kind == "ready-bad-lease":
        _write_json(output_dir / trace.CLAIM_FILE, claim)
        _write_json(output_dir / trace.READY_FILE, {**ready, "leaseId": "not a lease"})
    elif kind == "ready-extra-entry":
        _write_json(output_dir / trace.CLAIM_FILE, claim)
        _write_json(output_dir / trace.READY_FILE, ready)
        _write_json(output_dir / "extra.txt", {"unexpected": True})
    elif kind == "result-then-linger":
        _write_json(output_dir / trace.CLAIM_FILE, claim)
        _write_json(output_dir / trace.READY_FILE, ready)
        traceback_bytes = b"session-trace child stack\n"
        (output_dir / trace.TRACEBACK_FILE).write_bytes(traceback_bytes)
        _write_json(
            output_dir / trace.EVENTS_FILE,
            {
                "schemaVersion": trace.SCHEMA_VERSION,
                "attemptId": request["attemptId"],
                "requestDigest": request["requestDigest"],
                "pid": os.getpid(),
                "events": [{"stage": "claim-reserved", "elapsedMs": 0}],
            },
        )
        _write_json(
            output_dir / trace.RESULT_FILE,
            {
                "schemaVersion": trace.SCHEMA_VERSION,
                "attemptId": request["attemptId"],
                "requestDigest": request["requestDigest"],
                "pid": os.getpid(),
                "sourceDigest": base["sourceDigest"],
                "interpreter": base["interpreter"],
                "leaseId": ready["leaseId"],
                "outcome": "ok",
                "ok": True,
                "physicalTargetState": "UNKNOWN",
                "facts": {
                    "driverAcquired": 1,
                    "enumerations": 1,
                    "selections": 1,
                    "sessionConstructed": True,
                    "sessionOpened": False,
                    "sessionClosed": 1,
                    "forbiddenCalls": [],
                    "probeFingerprint": None,
                },
                "sessionOptions": trace._session_options(request),
                "traceback": {
                    "armed": True,
                    "bytes": len(traceback_bytes),
                    "cancelled": True,
                },
                "errors": {key: None for key in trace.CHILD_ERROR_KEYS},
            },
        )
    else:  # pragma: no cover - closed test vocabulary
        raise AssertionError(f"unknown spy scenario: {kind}")
    seconds = float(scenario.get("seconds") or 10.0)
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if (output_dir / trace.TERMINATE_FILE).exists():
            return 0
        time.sleep(0.02)
    return 0


def _bootstrap_main(argv: Sequence[str]) -> int:
    if len(argv) < 2:
        print("session-trace-bootstrap: missing mode or config", file=sys.stderr)
        return 2
    mode = argv[0]
    config = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    if mode == "trace-parent":
        profile = config["profile"]
        trace._install_private_test_injection(
            launcher=_make_child_launcher(Path(str(profile["configPath"])))
        )
        return trace.main(list(config["argv"]))
    if mode == "trace-child":
        profile = config["profile"]
        trace._install_private_test_injection(
            backend_factory=_make_driver_factory(profile)
        )
        return trace.main(["child", str(argv[2])])
    if mode == "spy":
        return _spy_run(config, Path(str(argv[2])))
    print(f"session-trace-bootstrap: unknown mode {mode}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_bootstrap_main(sys.argv[1:]))


# --- appended tests ---


def _profile(
    *,
    mode: str = "construct-ok",
    seconds: float | None = None,
    release: Path | None = None,
    receipt: Path | None = None,
) -> dict[str, object]:
    return {
        "mode": mode,
        "seconds": 0.0 if seconds is None else float(seconds),
        "release": None if release is None else str(release),
        "receipt": None if receipt is None else str(receipt),
    }


def _main_with_child(
    tmp_path: Path,
    project: Path,
    data: Path,
    run: Path,
    profile: Mapping[str, object],
    *,
    deadline: float = 10.0,
    probe: str = "fake-probe-1",
) -> int:
    _install_child_launcher(tmp_path, profile)
    return trace.main(_args(project, data, run, probe=probe, deadline=deadline))


# ---------------------------------------------------------------------------
# R1/R2: entry refusal, dynamic import and production launch capability
# ---------------------------------------------------------------------------


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
    assert sys.modules["session_trace_import_probe"] is module


def test_dynamic_import_registers_before_exec_and_cleans_up_on_failure(
    tmp_path: Path,
) -> None:
    broken = tmp_path / "broken_helper.py"
    broken.write_text(
        "import sys\n"
        "raise RuntimeError('broken import')\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="broken import"):
        _load_module("session_trace_broken", broken)

    assert "session_trace_broken" not in sys.modules
    # A later good load of the real helper still registers and resolves its
    # dataclasses (the historical collection failure).
    module = _load_module("session_trace_reload_probe")
    assert module.AttemptConfig(
        output_dir=tmp_path / "run",
        data_root=tmp_path / "data",
        probe_selector="fake-probe-1",
        target="STM32F429ZITx",
        project_dir=tmp_path,
    ).deadline_seconds == trace.DEFAULT_DEADLINE_SECONDS


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

    assert trace.main(_args(project, data, run)) == 2
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert not (run / trace.REQUEST_FILE).exists()
    assert not (run / trace.ATTEMPT_FILE).exists()


def test_production_launcher_uses_saved_helper_source_and_interpreter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _data, run = _paths(tmp_path)
    run.mkdir()
    calls: list[tuple[list[str], dict[str, object]]] = []

    def recording_popen(argv: Sequence[str], **kwargs: object) -> object:
        calls.append((list(argv), dict(kwargs)))
        return object()

    monkeypatch.setattr(trace.subprocess, "Popen", recording_popen)
    stderr_sentinel = object()

    trace._launch_child(
        source_path=HELPER_PATH,
        interpreter=os.path.abspath(sys.executable),
        output_dir=run,
        project_dir=project,
        stderr=stderr_sentinel,
        launcher=None,
    )

    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv == [
        os.path.abspath(sys.executable),
        "-B",
        str(HELPER_PATH),
        "child",
        str(run),
    ]
    assert Path(argv[2]).name == "session_trace.py"
    assert kwargs["cwd"] == str(project)
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["stderr"] is stderr_sentinel
    assert kwargs["close_fds"] is True


def test_environment_cannot_select_a_fake_launcher_or_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in REMOVED_FAKE_ENV:
        monkeypatch.setenv(name, "construct-ok")
    assert [name for name in vars(trace) if "FAKE" in name.upper()] == []

    project, _data, run = _paths(tmp_path)
    run.mkdir()
    spawned: list[list[str]] = []

    def recording_popen(argv: Sequence[str], **kwargs: object) -> object:
        spawned.append(list(argv))
        return object()

    monkeypatch.setattr(trace.subprocess, "Popen", recording_popen)
    trace._launch_child(
        source_path=HELPER_PATH,
        interpreter=os.path.abspath(sys.executable),
        output_dir=run,
        project_dir=project,
        stderr=subprocess.DEVNULL,
        launcher=None,
    )
    assert spawned == [
        [
            os.path.abspath(sys.executable),
            "-B",
            str(HELPER_PATH),
            "child",
            str(run),
        ]
    ]

    backend, error = trace._acquire_backend()
    assert error is None
    from stm32_toolkit.probe.pyocd_backend import PyOCDBackend

    assert isinstance(backend, PyOCDBackend)
    assert backend._driver is None  # production default stays lazy


# --- appended tests 2 ---


# ---------------------------------------------------------------------------
# R7/R2: one real child chain through the unchanged helper main()
# ---------------------------------------------------------------------------


def test_successful_attempt_constructs_once_closes_and_correlates(
    tmp_path: Path,
) -> None:
    project, data, run = _paths(tmp_path)
    receipt_path = tmp_path / "receipt.json"

    assert (
        _main_with_child(
            tmp_path,
            project,
            data,
            run,
            _profile(receipt=receipt_path),
        )
        == 0
    )

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
    assert attempt["claim"] == {"verified": True}
    assert attempt["child"]["returncode"] == 0
    assert attempt["child"]["alive"] is False
    assert attempt["child"]["handleReleased"] is True
    assert attempt["errors"] == []
    assert attempt["unexpectedEntries"] == []
    assert attempt["result"]["leaseReleased"] is True
    assert attempt["events"] == {"verified": True}

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

    # Bounded fixed stage markers only, including the real acquisition boundary.
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
    assert stages.index("driver-acquired") < stages.index("probe-selected")
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
    assert (
        _main_with_child(tmp_path, project, data, run, _profile())
        == 0
    )
    result_before = (run / trace.RESULT_FILE).read_bytes()
    claim_before = (run / trace.CLAIM_FILE).read_bytes()

    # A second real (still inert) child bootstrap must refuse the reserved run.
    config_path = _write_child_profile(tmp_path, _profile())
    second_child = subprocess.run(
        [
            sys.executable,
            "-B",
            str(TEST_MODULE_PATH),
            "trace-child",
            str(config_path),
            str(run),
        ],
        cwd=str(tmp_path),
        env=_env(),
        capture_output=True,
        text=True,
        timeout=60.0,
    )

    assert second_child.returncode != 0
    assert (run / trace.RESULT_FILE).read_bytes() == result_before
    assert (run / trace.CLAIM_FILE).read_bytes() == claim_before
    assert trace.main(_args(project, data, run)) == 2


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
    receipt_path = tmp_path / "receipt.json"
    holder = _hold_lease(data)
    try:
        completed = _main_with_child(
            tmp_path,
            project,
            data,
            run,
            _profile(receipt=receipt_path),
            deadline=5.0,
        )

        assert completed != 0
        result = _read(run / trace.RESULT_FILE)
        assert result["outcome"] == "busy"
        assert result["ok"] is False
        assert result["errors"]["lease"] == "PROBE_BUSY"
        assert result["facts"]["sessionConstructed"] is False
        assert result["facts"]["driverAcquired"] == 0
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
    receipt_path = tmp_path / "receipt.json"
    holder = _hold_lease(data, workspace="handoff-holder")
    ticket = "a" * 64
    holder.reserve_external_handoff(ticket)
    holder.release()

    completed = _main_with_child(
        tmp_path,
        project,
        data,
        run,
        _profile(receipt=receipt_path),
        deadline=5.0,
    )

    assert completed != 0
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
    receipt_path = tmp_path / "receipt.json"

    completed = _main_with_child(
        tmp_path,
        project,
        data,
        run,
        _profile(mode="construct-error", receipt=receipt_path),
    )

    assert completed == 6
    attempt = _read(run / trace.ATTEMPT_FILE)
    result = _read(run / trace.RESULT_FILE)
    receipt = _read(receipt_path)
    assert attempt["ok"] is False
    assert attempt["grant"]["goWritten"] is True
    assert result["ok"] is False
    assert result["outcome"] == "construct-error"
    assert result["errors"]["construction"] == "RuntimeError"
    assert result["facts"]["driverAcquired"] == 1
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
    receipt_path = tmp_path / "receipt.json"

    completed = _main_with_child(
        tmp_path,
        project,
        data,
        run,
        _profile(mode="close-error", receipt=receipt_path),
    )

    assert completed == 6
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

    completed = _main_with_child(
        tmp_path,
        project,
        data,
        run,
        _profile(mode="construct-block-exit", seconds=1.5),
    )

    assert completed == 0
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
    receipt_path = tmp_path / "receipt.json"

    completed = _main_with_child(
        tmp_path,
        project,
        data,
        run,
        _profile(receipt=receipt_path),
        probe="other-probe",
    )

    assert completed == 6
    result = _read(run / trace.RESULT_FILE)
    receipt = _read(receipt_path)
    assert result["outcome"] == "selection-error"
    assert result["facts"]["driverAcquired"] == 1
    assert result["facts"]["enumerations"] == 1
    assert result["facts"]["selections"] == 0
    assert result["facts"]["sessionConstructed"] is False
    assert result["sessionOptions"] is None
    assert receipt["createSession"] == 0
    assert receipt["forbiddenCalls"] == []
    assert _read(_record_path(data, "other-probe"))["state"] == "released"


# --- appended tests 3 ---


# ---------------------------------------------------------------------------
# R3/R4/R5: parent grant decisions through real entry paths
# ---------------------------------------------------------------------------


def test_bad_ready_never_grants_go(tmp_path: Path) -> None:
    project, data, run = _paths(tmp_path)
    _install_spy_launcher(tmp_path, {"kind": "ready-bad-lease", "seconds": 10.0})

    outcome = trace.run_attempt(_config(project, data, run, deadline=4.0))

    assert outcome.outcome == "readiness-mismatch"
    assert outcome.ok is False
    assert outcome.exit_code == 3
    attempt = _read(run / trace.ATTEMPT_FILE)
    assert attempt["grant"] == {"readyMatched": False, "goWritten": False}
    assert attempt["ok"] is False
    assert (run / trace.CLAIM_FILE).exists()
    assert (run / trace.READY_FILE).exists()
    assert not (run / trace.GO_FILE).exists()


def test_missing_completed_claim_never_grants_go(tmp_path: Path) -> None:
    project, data, run = _paths(tmp_path)
    _install_spy_launcher(tmp_path, {"kind": "ready-without-claim", "seconds": 10.0})

    outcome = trace.run_attempt(_config(project, data, run, deadline=2.0))

    assert outcome.outcome == "readiness-mismatch"
    assert outcome.ok is False
    attempt = _read(run / trace.ATTEMPT_FILE)
    assert attempt["claim"] == {"verified": False}
    assert attempt["grant"] == {"readyMatched": True, "goWritten": False}
    assert "claim-unavailable" in attempt["errors"]
    assert not (run / trace.GO_FILE).exists()


def test_extra_one_shot_output_is_refused_before_grant(tmp_path: Path) -> None:
    project, data, run = _paths(tmp_path)
    _install_spy_launcher(tmp_path, {"kind": "ready-extra-entry", "seconds": 10.0})

    outcome = trace.run_attempt(_config(project, data, run, deadline=4.0))

    assert outcome.outcome == "readiness-mismatch"
    attempt = _read(run / trace.ATTEMPT_FILE)
    assert attempt["claim"] == {"verified": True}
    assert attempt["grant"] == {"readyMatched": True, "goWritten": False}
    assert "unexpected-entries" in attempt["errors"]
    assert attempt["unexpectedEntries"] == ["extra.txt"]
    assert not (run / trace.GO_FILE).exists()


def test_partial_startup_without_ready_never_grants_go(tmp_path: Path) -> None:
    project, data, run = _paths(tmp_path)
    _install_spy_launcher(tmp_path, {"kind": "claim-only", "seconds": 10.0})

    outcome = trace.run_attempt(_config(project, data, run, deadline=2.0))

    assert outcome.outcome == "readiness-timeout"
    assert outcome.exit_code == 4
    attempt = _read(run / trace.ATTEMPT_FILE)
    assert attempt["grant"] == {"readyMatched": False, "goWritten": False}
    assert attempt["ok"] is False
    assert (run / trace.CLAIM_FILE).exists()
    assert not (run / trace.READY_FILE).exists()
    assert not (run / trace.GO_FILE).exists()


def test_cancellation_after_ready_never_grants(tmp_path: Path) -> None:
    project, data, run = _paths(tmp_path)
    # READY is published but the claim never completes, so the parent waits;
    # the known cancellation must keep its own outcome inside that wait.
    _install_spy_launcher(tmp_path, {"kind": "ready-without-claim", "seconds": 10.0})
    cancel = threading.Event()
    cancelled: list[bool] = []

    def cancel_when_ready() -> None:
        cancelled.append(_wait_for(run / trace.READY_FILE, 5.0))
        # Let the parent match READY and settle into the claim wait; without a
        # claim it can never grant, so the cancel must be observed there.
        time.sleep(0.5)
        cancel.set()

    thread = threading.Thread(target=cancel_when_ready)
    thread.start()
    try:
        outcome = trace.run_attempt(
            _config(project, data, run, deadline=8.0), cancel_event=cancel
        )
    finally:
        thread.join(timeout=10.0)

    assert cancelled == [True]
    assert outcome.outcome == "cancelled"
    assert outcome.exit_code == 5
    attempt = _read(run / trace.ATTEMPT_FILE)
    assert attempt["initiating"]["outcome"] == "cancelled"
    assert attempt["claim"] == {"verified": False}
    assert attempt["grant"] == {"readyMatched": True, "goWritten": False}
    assert attempt["termination"]["terminateRequested"] is True
    assert not (run / trace.GO_FILE).exists()


def test_cancellation_during_post_result_exit_wait_is_kept(tmp_path: Path) -> None:
    project, data, run = _paths(tmp_path)
    _install_spy_launcher(tmp_path, {"kind": "result-then-linger", "seconds": 10.0})
    cancel = threading.Event()
    cancelled: list[bool] = []

    def cancel_after_result() -> None:
        seen = _wait_for(run / trace.RESULT_FILE, 5.0)
        # The parent has validated RESULT and is now waiting for exit; the
        # spy stays alive so the cancellation can only land in that loop.
        time.sleep(0.3)
        cancelled.append(seen)
        cancel.set()

    thread = threading.Thread(target=cancel_after_result)
    thread.start()
    try:
        outcome = trace.run_attempt(
            _config(project, data, run, deadline=8.0), cancel_event=cancel
        )
    finally:
        thread.join(timeout=10.0)

    assert cancelled == [True]
    assert outcome.outcome == "cancelled"
    assert outcome.exit_code == 5
    attempt = _read(run / trace.ATTEMPT_FILE)
    assert attempt["initiating"] == {
        "outcome": "cancelled",
        "error": "cancelled-after-result",
    }
    assert attempt["grant"] == {"readyMatched": True, "goWritten": True}
    assert attempt["result"]["present"] is True
    assert attempt["result"]["ok"] is True
    assert attempt["errors"] == []


def test_launch_time_cancellation_keeps_cancelled_outcome(tmp_path: Path) -> None:
    project, data, run = _paths(tmp_path)

    def cancelling_launcher(argv: Sequence[str], cwd: str) -> object:
        raise KeyboardInterrupt

    outcome = trace.run_attempt(
        _config(project, data, run), launcher=cancelling_launcher
    )

    assert outcome.outcome == "cancelled"
    assert outcome.ok is False
    assert outcome.exit_code == 5
    attempt = _read(run / trace.ATTEMPT_FILE)
    assert attempt["initiating"] == {
        "outcome": "cancelled",
        "error": "launch-cancelled",
    }
    assert attempt["child"]["pid"] is None
    assert attempt["grant"] == {"readyMatched": False, "goWritten": False}
    assert not (run / trace.GO_FILE).exists()


def test_launcher_failure_reports_unknown_without_granting(tmp_path: Path) -> None:
    project, data, run = _paths(tmp_path)

    def failing_launcher(argv: Sequence[str], cwd: str) -> object:
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


def _request_for(project: Path, data: Path, run: Path, *, deadline: float = 10.0):
    request = trace._build_request(
        _config(project, data, run, deadline=deadline),
        attempt_id="attempt-" + "1" * 32,
        session_id="session-" + "2" * 32,
        deadline_wall=time.time() + deadline,
    )
    return trace._validate_request(request)


def test_go_record_validation_refuses_any_identity_mismatch(tmp_path: Path) -> None:
    project, data, run = _paths(tmp_path)
    request = _request_for(project, data, run)
    interpreter = os.path.abspath(sys.executable)
    source_digest = "c" * 64
    lease_id = "lease-" + "3" * 32
    good = {
        "schemaVersion": 1,
        "attemptId": request["attemptId"],
        "requestDigest": request["requestDigest"],
        "pid": 4321,
        "sourceDigest": source_digest,
        "interpreter": interpreter,
        "leaseId": lease_id,
        "issuedAtUnix": time.time(),
    }

    trace._validate_go(
        good,
        request=request,
        pid=4321,
        source_digest=source_digest,
        interpreter=interpreter,
        lease_id=lease_id,
    )

    mutations = (
        {"pid": 4322},
        {"requestDigest": "0" * 64},
        {"attemptId": "attempt-" + "9" * 32},
        {"sourceDigest": "d" * 64},
        {"leaseId": "not a lease"},
        {"leaseId": "lease-" + "4" * 32},
        {"issuedAtUnix": float("nan")},
        {"issuedAtUnix": request["deadlineUnix"] + 1.0},
        {"issuedAtUnix": float("inf")},
    )
    for mutation in mutations:
        with pytest.raises(trace.SessionTraceError):
            trace._validate_go(
                {**good, **mutation},
                request=request,
                pid=4321,
                source_digest=source_digest,
                interpreter=interpreter,
                lease_id=lease_id,
            )
    with pytest.raises(trace.SessionTraceError):
        trace._validate_go(
            {**good, "extra": 1},
            request=request,
            pid=4321,
            source_digest=source_digest,
            interpreter=interpreter,
            lease_id=lease_id,
        )


def test_await_go_returns_closed_refusal_codes(tmp_path: Path) -> None:
    project, data, run = _paths(tmp_path)
    run.mkdir()
    request = _request_for(project, data, run)
    deadline = float(request["deadlineUnix"])
    interpreter = os.path.abspath(sys.executable)
    source_digest = "e" * 64
    acquired = "lease-" + "a" * 32
    good = {
        "schemaVersion": 1,
        "attemptId": request["attemptId"],
        "requestDigest": request["requestDigest"],
        "pid": os.getpid(),
        "sourceDigest": source_digest,
        "interpreter": interpreter,
        "leaseId": acquired,
        "issuedAtUnix": time.time(),
    }

    _write_json(run / trace.GO_FILE, {**good, "leaseId": "lease-" + "b" * 32})
    assert (
        trace._await_go(run, request, source_digest, interpreter, acquired)
        == "go-lease-mismatch"
    )

    _write_json(
        run / trace.GO_FILE, {**good, "issuedAtUnix": deadline + 10.0}
    )
    assert (
        trace._await_go(run, request, source_digest, interpreter, acquired)
        == "go-expired"
    )

    (run / trace.GO_FILE).write_text(
        json.dumps({**good, "issuedAtUnix": float("nan")}), encoding="utf-8"
    )
    assert (
        trace._await_go(run, request, source_digest, interpreter, acquired)
        == "go-identity-mismatch"
    )

    _write_json(run / trace.GO_FILE, good)
    assert (
        trace._await_go(run, request, source_digest, interpreter, acquired)
        == "accepted"
    )


def test_request_deadline_bounds_and_tamper_are_rejected(tmp_path: Path) -> None:
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

    for bad_deadline in (
        float("nan"),
        float("inf"),
        time.time() + trace.MAX_DEADLINE_SECONDS + 60.0,
        time.time() - 60.0,
    ):
        with pytest.raises(trace.SessionTraceError):
            # Rebuild so the digest matches the mutated deadline.
            mutated = trace._build_request(
                _config(project, data, run),
                attempt_id="attempt-" + "1" * 32,
                session_id="session-" + "2" * 32,
                deadline_wall=bad_deadline,
            )
            trace._validate_request(mutated)

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * (trace.MAX_RUN_FILE_BYTES + 1))
    with pytest.raises(trace.SessionTraceError):
        trace._read_json_until(oversized, time.time() + 1.0)


def test_stale_or_extra_child_outputs_refuse_before_backend(tmp_path: Path) -> None:
    project, data, run = _paths(tmp_path)
    request = _request_for(project, data, run)

    for index, stale in enumerate(
        (trace.GO_FILE, trace.RESULT_FILE, trace.TRACEBACK_FILE, trace.EVENTS_FILE)
    ):
        case = tmp_path / f"stale-{index}"
        case.mkdir()
        trace._write_json_exclusive(case / trace.REQUEST_FILE, request)
        _write_json(case / stale, {"schemaVersion": 1})
        factory = _make_driver_factory(_profile())
        trace._install_private_test_injection(backend_factory=factory)

        assert trace.child_main(case) == trace._EXIT_REFUSED
        assert factory.created == []
        assert not (case / trace.CLAIM_FILE).exists()

    # An extra unknown file is refused just as decisively.
    extra = tmp_path / "extra"
    extra.mkdir()
    trace._write_json_exclusive(extra / trace.REQUEST_FILE, request)
    _write_json(extra / "extra.txt", {"unexpected": True})
    factory = _make_driver_factory(_profile())
    trace._install_private_test_injection(backend_factory=factory)
    assert trace.child_main(extra) == trace._EXIT_REFUSED
    assert factory.created == []

    # An incomplete/foreign claim is not a reservation either.
    claim_case = tmp_path / "bad-claim"
    claim_case.mkdir()
    trace._write_json_exclusive(claim_case / trace.REQUEST_FILE, request)
    _write_json(
        claim_case / trace.CLAIM_FILE,
        {
            "schemaVersion": 1,
            "attemptId": request["attemptId"],
            "requestDigest": request["requestDigest"],
            "pid": 1,
            "sourceDigest": "f" * 64,
            "interpreter": os.path.abspath(sys.executable),
            "claimedAtUnix": time.time(),
        },
    )
    factory = _make_driver_factory(_profile())
    trace._install_private_test_injection(backend_factory=factory)
    assert trace.child_main(claim_case) == trace._EXIT_REFUSED
    assert factory.created == []
    assert not (data / "probe-registry").exists()


# --- appended tests 4 ---


# ---------------------------------------------------------------------------
# Actual parent main() timeout/cancellation with a surviving inert child
# ---------------------------------------------------------------------------


def test_parent_main_timeout_with_surviving_inert_child_is_bounded(
    tmp_path: Path, release_cleanup
) -> None:
    project, data, run = _paths(tmp_path)
    release = tmp_path / "unique-release-1.signal"
    release_cleanup(release)
    profile = _profile(
        mode="construct-block-stubborn", seconds=14.0, release=release
    )
    config = _write_parent_config(
        tmp_path, profile, _args(project, data, run, deadline=6.0)
    )

    started = time.monotonic()
    completed = _run_parent_cli(config, timeout=45.0)
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
    assert "_block_until_release" in text

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
def test_parent_main_cancellation_with_surviving_inert_child_is_bounded(
    tmp_path: Path, release_cleanup
) -> None:
    project, data, run = _paths(tmp_path)
    release = tmp_path / "unique-release-2.signal"
    release_cleanup(release)
    profile = _profile(
        mode="construct-block-stubborn", seconds=12.0, release=release
    )
    config = _write_parent_config(
        tmp_path, profile, _args(project, data, run, deadline=15.0)
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-B",
            str(TEST_MODULE_PATH),
            "trace-parent",
            str(config),
        ],
        cwd=str(tmp_path),
        env=_env(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=CREATE_NEW_PROCESS_GROUP,
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


# ---------------------------------------------------------------------------
# R6: truthfully failing success surfaces
# ---------------------------------------------------------------------------


def test_attempt_record_failure_fails_every_surface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project, data, run = _paths(tmp_path)
    original = trace._write_json_exclusive

    def failing_write(path: Path, payload: Mapping[str, object]) -> None:
        if Path(path).name == trace.ATTEMPT_FILE:
            raise OSError("disk full")
        original(path, payload)

    monkeypatch.setattr(trace, "_write_json_exclusive", failing_write)
    cancel = threading.Event()
    cancel.set()

    outcome = trace.run_attempt(_config(project, data, run), cancel_event=cancel)

    assert outcome.ok is False
    assert outcome.exit_code == 7
    assert outcome.report["ok"] is False
    assert outcome.report["exitCode"] == 7
    assert outcome.report["reportError"] == "OSError"
    assert "attempt-write-failed" in outcome.report["errors"]
    assert "disk full" not in json.dumps(outcome.report)
    assert not (run / trace.ATTEMPT_FILE).exists()

    captured = capsys.readouterr()
    printed = json.loads(captured.out.strip().splitlines()[-1])
    assert printed["ok"] is False
    assert printed["exitCode"] == 7
    assert "attempt report write failed" in captured.err.lower()


def test_preparation_failure_still_writes_an_attempt_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, data, run = _paths(tmp_path)

    def failing_digest(path: Path) -> str:
        raise OSError("source unavailable")

    monkeypatch.setattr(trace, "_file_digest", failing_digest)

    outcome = trace.run_attempt(_config(project, data, run))

    assert outcome.outcome == "parent-error"
    assert outcome.ok is False
    attempt = _read(run / trace.ATTEMPT_FILE)
    assert attempt["initiating"] == {
        "outcome": "parent-error",
        "error": "OSError",
    }
    assert "OSError" in attempt["errors"]
    assert not (run / trace.REQUEST_FILE).exists()
    assert not (run / trace.GO_FILE).exists()


def test_traceback_stat_failure_is_an_explicit_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        trace.faulthandler, "dump_traceback_later", lambda *a, **k: None
    )
    path = tmp_path / "traceback.txt"
    native = trace._NativeTraceback(path)

    assert native.arm() is None

    # A real unlink is impossible on Windows while the snapshot handle is
    # open, so only this run-owned path reports the stat failure.
    real_stat = Path.stat

    def failing_stat(self: Path, *args: object, **kwargs: object) -> object:
        if self.name == "traceback.txt":
            raise OSError("stat failed")
        return real_stat(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "stat", failing_stat)

    assert native.disarm() == "traceback-stat-failed"
    assert native.summary() == {"armed": True, "bytes": 0, "cancelled": True}


def test_traceback_stat_failure_fails_the_child_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Driver:
        def create_session(self, probe: object, *, options: object) -> object:
            return object()

    def failing_disarm(self: object) -> str:
        handle = getattr(self, "_file", None)
        if handle is not None:
            try:
                handle.close()  # type: ignore[attr-defined]
            except BaseException:
                pass
        setattr(self, "_file", None)
        return "traceback-stat-failed"

    monkeypatch.setattr(
        trace.faulthandler, "dump_traceback_later", lambda *a, **k: None
    )
    monkeypatch.setattr(trace._NativeTraceback, "disarm", failing_disarm)
    facts = trace._new_facts()
    errors: dict[str, str | None] = {key: None for key in trace.CHILD_ERROR_KEYS}
    meta: dict[str, object] = {"armed": False, "bytes": 0, "cancelled": False}

    trace._construct_and_close(
        facts,
        errors,
        meta,
        driver=Driver(),
        probe=object(),
        options={},
        traceback_path=tmp_path / "traceback.txt",
        events=[],
        started=time.monotonic(),
    )

    assert errors["tracebackClose"] == "traceback-stat-failed"
    assert facts["sessionConstructed"] is True
    assert trace._child_ok("ok", facts, errors, meta) is False


def test_lease_release_failure_is_an_overall_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import stm32_toolkit.probe.lease as lease_module

    class FailingLease:
        lease_id = "lease-" + "a" * 32

        def release(self) -> None:
            raise RuntimeError("release failed")

    class FakeManager:
        def __init__(self, root: Path) -> None:
            self.root = root

        def acquire(self, **kwargs: object) -> FailingLease:
            return FailingLease()

    monkeypatch.setattr(lease_module, "ProbeLeaseManager", FakeManager)
    project, data, run = _paths(tmp_path)
    run.mkdir()
    request = trace._build_request(
        _config(project, data, run, deadline=1.0),
        attempt_id="attempt-" + "1" * 32,
        session_id="session-" + "2" * 32,
        deadline_wall=time.time() + 1.0,
    )
    trace._write_json_exclusive(run / trace.REQUEST_FILE, request)
    factory = _make_driver_factory(_profile())
    trace._install_private_test_injection(backend_factory=factory)

    assert trace.child_main(run) == trace._EXIT_CHILD_FAILED

    result = _read(run / trace.RESULT_FILE)
    assert result["outcome"] == "go-timeout"
    assert result["ok"] is False
    assert result["errors"]["leaseRelease"] == "RuntimeError"
    assert result["facts"]["sessionConstructed"] is False
    assert factory.created == []


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
        def __init__(
            self, returncode: int | None, handle: Handle, wait_error: BaseException | None = None
        ) -> None:
            self.returncode = returncode
            self._handle = handle
            self.wait_error = wait_error

        def poll(self) -> int | None:
            return self.returncode

        def wait(self, timeout: float | None = None) -> int | None:
            if self.wait_error is not None:
                raise self.wait_error
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

    wait_failure = Process(7, Handle(), OSError("wait failed"))
    assert "process-wait-failed" in trace._release_terminal_process_handles(
        wait_failure
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
    assert trace._child_ok("ok", facts, errors, meta) is False


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
    assert trace._child_ok("ok", facts, errors, meta) is False


def test_real_result_and_claim_records_validate_and_reject_mutation(
    tmp_path: Path,
) -> None:
    project, data, run = _paths(tmp_path)
    assert _main_with_child(tmp_path, project, data, run, _profile()) == 0

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
    with pytest.raises(trace.SessionTraceError):
        trace._validate_result(
            {
                **result,
                "facts": {**result["facts"], "sessionOpened": True},
            },
            **kwargs,
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


# --- appended tests 5 ---
