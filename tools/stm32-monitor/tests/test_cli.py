from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class FakeEndpoint:
    host: str = "127.0.0.1"
    port: int = 45678
    token: str = field(default="d" * 64, repr=False)
    monitor_version: str = "0.5.0"

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def access_url(self) -> str:
        return f"{self.url}/#token={self.token}"


class RecordingRuntime:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.config = None

    async def start(self, config):
        self.events.append("start")
        self.config = config
        return FakeEndpoint()

    async def wait_closed(self) -> None:
        self.events.append("wait")

    async def stop(self) -> None:
        self.events.append("stop")


class FakeRuntime:
    def __init__(self) -> None:
        self.config = None
        self.stopped = False

    async def start(self, config):
        self.config = config
        return FakeEndpoint()

    async def wait_closed(self) -> None:
        return None

    async def stop(self) -> None:
        self.stopped = True


def test_serve_cli_accepts_only_project_data_session_and_json(tmp_path: Path) -> None:
    from stm32_monitor.cli import main

    project = (tmp_path / "project").resolve()
    data = (tmp_path / "data").resolve()
    project.mkdir()
    output = io.StringIO()
    runtime = FakeRuntime()
    exit_code = main(
        [
            "serve",
            "--project",
            str(project),
            "--data-root",
            str(data),
            "--session-id",
            "session-a",
            "--json",
        ],
        _runtime_factory=lambda: runtime,
        _stdout=output,
    )

    assert exit_code == 0
    payload = json.loads(output.getvalue())
    assert payload["ok"] is True
    assert payload["endpoint"]["url"] == "http://127.0.0.1:45678"
    assert payload["endpoint"]["monitorVersion"] == "0.5.0"
    assert payload["endpoint"]["accessUrl"].startswith(
        "http://127.0.0.1:45678/#token="
    )
    assert runtime.config.project_root == project
    assert runtime.config.data_root == data
    assert runtime.config.session_id == "session-a"
    assert runtime.stopped is True


def test_cli_rejects_legacy_and_override_options(tmp_path: Path) -> None:
    from stm32_monitor.cli import main

    for option in ("--open-browser", "--port", "--target", "--elf", "--svd", "--address"):
        errors = io.StringIO()
        try:
            main(
                [
                    "serve",
                    "--project",
                    str(tmp_path),
                    "--data-root",
                    str(tmp_path / "data"),
                    "--session-id",
                    "session-a",
                    "--json",
                    option,
                    "attacker-value",
                ],
                _runtime_factory=FakeRuntime,
                _stderr=errors,
            )
        except SystemExit as error:
            assert error.code == 2
        else:
            raise AssertionError(f"legacy option was accepted: {option}")


def test_module_entrypoint_delegates_to_cli_without_importing_legacy_runtime() -> None:
    import runpy
    import sys

    original = sys.argv
    sys.argv = ["stm32-monitor", "--help"]
    try:
        try:
            runpy.run_module("stm32_monitor.__main__", run_name="__main__")
        except SystemExit as error:
            assert error.code == 0
    finally:
        sys.argv = original


def test_cli_returns_sanitized_json_failure_without_traceback(tmp_path: Path) -> None:
    from stm32_monitor.cli import main
    from stm32_monitor.runtime import MonitorRuntimeError

    class FailingRuntime(FakeRuntime):
        async def start(self, config):
            raise MonitorRuntimeError("MONITOR_RUNTIME_BUSY", "Workspace is busy")

    project = tmp_path / "project"
    project.mkdir()
    output = io.StringIO()
    code = main(
        [
            "serve",
            "--project",
            str(project),
            "--data-root",
            str(tmp_path / "data"),
            "--session-id",
            "session-a",
            "--json",
        ],
        _runtime_factory=FailingRuntime,
        _stdout=output,
    )
    assert code == 1
    assert json.loads(output.getvalue()) == {
        "ok": False,
        "code": "MONITOR_RUNTIME_BUSY",
        "message": "Workspace is busy",
    }

    class HostileRuntime(FakeRuntime):
        async def start(self, config):
            error = RuntimeError("SECRET C:\\private\\token.txt")
            error.code = "FORGED"  # type: ignore[attr-defined]
            error.message = "SECRET " + "d" * 64  # type: ignore[attr-defined]
            raise error

    hostile_output = io.StringIO()
    hostile_code = main(
        [
            "serve",
            "--project",
            str(project),
            "--data-root",
            str(tmp_path / "data"),
            "--session-id",
            "session-a",
            "--json",
        ],
        _runtime_factory=HostileRuntime,
        _stdout=hostile_output,
    )
    assert hostile_code == 1
    assert json.loads(hostile_output.getvalue()) == {
        "ok": False,
        "code": "MONITOR_INPUT_INVALID",
        "message": "Monitor service failed",
    }


def test_cli_maps_keyboard_interrupt_to_130(tmp_path: Path) -> None:
    from stm32_monitor.cli import main

    class InterruptedRuntime(FakeRuntime):
        async def start(self, config):
            raise KeyboardInterrupt

    project = tmp_path / "project"
    project.mkdir()
    code = main(
        [
            "serve",
            "--project",
            str(project),
            "--data-root",
            str(tmp_path / "data"),
            "--session-id",
            "session-a",
            "--json",
        ],
        _runtime_factory=InterruptedRuntime,
        _stdout=io.StringIO(),
    )
    assert code == 130


def test_serve_never_calls_the_browser_opener(tmp_path: Path) -> None:
    from stm32_monitor.cli import main

    project = (tmp_path / "project").resolve()
    project.mkdir()
    opened: list[str] = []
    runtime = RecordingRuntime([])
    code = main(
        [
            "serve",
            "--project",
            str(project),
            "--data-root",
            str((tmp_path / "data").resolve()),
            "--session-id",
            "session-a",
            "--json",
        ],
        _runtime_factory=lambda: runtime,
        _browser_open=lambda url: opened.append(url) or True,
        _stdout=io.StringIO(),
    )
    assert code == 0
    assert opened == []


def test_open_starts_then_opens_once_and_cleans_up(tmp_path: Path) -> None:
    from stm32_monitor.cli import main

    project = (tmp_path / "project").resolve()
    project.mkdir()
    events: list[object] = []
    opened: list[str] = []
    runtime = RecordingRuntime(events)
    code = main(
        ["open", "--project", str(project), "--data-root", str((tmp_path / "data").resolve())],
        _runtime_factory=lambda: runtime,
        _browser_open=lambda url: opened.append(url) or True,
        _stdout=io.StringIO(),
    )
    assert code == 0
    assert opened == ["http://127.0.0.1:45678/#token=" + "d" * 64]
    assert [item[0] if isinstance(item, tuple) else item for item in events] == [
        "start",
        "wait",
        "stop",
    ]
    assert isinstance(runtime.config.session_id, str)
    assert runtime.config.session_id.startswith("monitor-")


def test_open_accepts_an_explicit_session_id(tmp_path: Path) -> None:
    from stm32_monitor.cli import main

    project = (tmp_path / "project").resolve()
    project.mkdir()
    runtime = RecordingRuntime([])
    code = main(
        [
            "open",
            "--project",
            str(project),
            "--data-root",
            str((tmp_path / "data").resolve()),
            "--session-id",
            "explicit-session",
        ],
        _runtime_factory=lambda: runtime,
        _stdout=io.StringIO(),
    )
    assert code == 0
    assert runtime.config.session_id == "explicit-session"


def test_open_browser_handoff_failure_stops_runtime_sanitized(tmp_path: Path) -> None:
    from stm32_monitor.cli import main

    project = (tmp_path / "project").resolve()
    project.mkdir()
    events: list[str] = []
    output = io.StringIO()
    code = main(
        ["open", "--project", str(project), "--data-root", str((tmp_path / "data").resolve())],
        _runtime_factory=lambda: RecordingRuntime(events),
        _browser_open=lambda url: False,
        _stdout=output,
    )
    assert code == 1
    assert json.loads(output.getvalue()) == {
        "ok": False,
        "code": "MONITOR_BROWSER_FAILED",
        "message": "Monitor browser handoff failed",
    }
    assert events == ["start", "stop"]


def test_open_rejects_an_endpoint_without_a_valid_access_url(tmp_path: Path) -> None:
    from stm32_monitor.cli import main

    class NoAccessRuntime(RecordingRuntime):
        async def start(self, config):
            self.events.append("start")
            self.config = config
            return object()  # no access_url attribute -> MONITOR_SERVICE_UNAVAILABLE

    project = (tmp_path / "project").resolve()
    project.mkdir()
    events: list[str] = []
    output = io.StringIO()
    code = main(
        ["open", "--project", str(project), "--data-root", str((tmp_path / "data").resolve())],
        _runtime_factory=lambda: NoAccessRuntime(events),
        _stdout=output,
    )
    assert code == 1
    assert json.loads(output.getvalue()) == {
        "ok": False,
        "code": "MONITOR_SERVICE_UNAVAILABLE",
        "message": "Monitor Service is unavailable",
    }
    assert events == ["start", "stop"]


def test_open_prints_no_access_url_to_stdout(tmp_path: Path) -> None:
    from stm32_monitor.cli import main

    project = (tmp_path / "project").resolve()
    project.mkdir()
    output = io.StringIO()
    code = main(
        ["open", "--project", str(project), "--data-root", str((tmp_path / "data").resolve())],
        _runtime_factory=lambda: RecordingRuntime([]),
        _browser_open=lambda url: True,
        _stdout=output,
    )
    assert code == 0
    assert "token" not in output.getvalue()
    assert "#" not in output.getvalue()
    assert output.getvalue() == ""


def test_open_keyboard_interrupt_returns_130_and_cleans_up(tmp_path: Path) -> None:
    from stm32_monitor.cli import main

    class InterruptedAfterOpen(FakeRuntime):
        async def wait_closed(self) -> None:
            raise KeyboardInterrupt

    project = (tmp_path / "project").resolve()
    project.mkdir()
    runtime = InterruptedAfterOpen()
    code = main(
        ["open", "--project", str(project), "--data-root", str((tmp_path / "data").resolve())],
        _runtime_factory=lambda: runtime,
        _browser_open=lambda url: True,
        _stdout=io.StringIO(),
    )
    assert code == 130
    assert runtime.stopped is True
