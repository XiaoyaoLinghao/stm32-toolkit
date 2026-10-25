from __future__ import annotations

import asyncio
import io
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest


@dataclass(frozen=True)
class FakeEndpoint:
    host: str = "127.0.0.1"
    port: int = 45678
    token: str = field(default="d" * 64, repr=False)
    monitor_version: str = "1.3.1"

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
        return FakeEndpoint(port=config.port or 45678)

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


class InteractiveInput(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_version_command_reports_the_package_version() -> None:
    from stm32_monitor.cli import main

    output = io.StringIO()

    assert main(["version"], _stdout=output) == 0
    assert output.getvalue() == "1.3.1\n"


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
    assert payload["endpoint"]["monitorVersion"] == "1.3.1"
    assert payload["endpoint"]["accessUrl"].startswith(
        "http://127.0.0.1:45678/#token="
    )
    assert runtime.config.project_root == project
    assert runtime.config.data_root == data
    assert runtime.config.session_id == "session-a"
    assert runtime.config.port == 0
    assert runtime.stopped is True


def test_cli_rejects_legacy_and_override_options(tmp_path: Path) -> None:
    from stm32_monitor.cli import main

    for option in ("--open-browser", "--target", "--elf", "--svd", "--address"):
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


def test_cli_port_parser_accepts_ascii_decimal_and_rejects_invalid_values(tmp_path: Path) -> None:
    from stm32_monitor.cli import _parser, main

    base = ["--project", str(tmp_path), "--data-root", str(tmp_path / "data")]
    for command, tail in (("open", []), ("serve", ["--session-id", "session-a", "--json"])):
        assert _parser().parse_args([command, *base, *tail]).port is None
        assert _parser().parse_args([command, *base, *tail, "--port", "00001"]).port == 1
        assert _parser().parse_args([command, *base, *tail, "--port", "80"]).port == 80
        assert _parser().parse_args([command, *base, *tail, "--port", "65535"]).port == 65_535
        for value in ("0", "65536", "-1", "+1", " 1", "1 ", "1_000", "１", "x"):
            stderr = io.StringIO()
            with pytest.raises(SystemExit) as error:
                main([command, *base, *tail, "--port", value], _stderr=stderr)
            assert error.value.code == 2
            assert "port" in stderr.getvalue()


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


def test_adapter_cli_rejects_invalid_project_context_before_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import stm32_monitor.cli as cli

    workflow_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    loader_calls: list[object] = []

    def workflow_sentinel(*args: object, **kwargs: object) -> object:
        workflow_calls.append((args, kwargs))
        return object()

    def loader_sentinel(path: object) -> dict[str, object]:
        loader_calls.append(path)
        return {}

    monkeypatch.setattr(cli, "ingest_monitor_replay", workflow_sentinel)
    monkeypatch.setattr(cli, "_load_json_file", loader_sentinel)

    project = tmp_path / "project"
    project.mkdir()
    output = io.StringIO()
    code = cli.main(
        [
            "replay",
            "ingest",
            "--project",
            str(project),
            "--data-root",
            str(tmp_path / "data"),
            "--session-id",
            "session-a",
            "--operation-id",
            "operation-a",
            "--document-file",
            str(tmp_path / "missing-replay.json"),
            "--json",
        ],
        _stdout=output,
    )

    assert code == 1
    payload = json.loads(output.getvalue())
    assert payload["ok"] is False
    assert payload["operation"] == "monitor.replay.ingest"
    assert payload["code"] == "ANALYSIS_WORKFLOW_INVALID"
    assert payload["message"] == "Project configuration is invalid"
    assert workflow_calls == []
    assert loader_calls == []


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
        ["open", "--project", str(project), "--data-root", str((tmp_path / "data").resolve()), "--port", "8765"],
        _runtime_factory=lambda: runtime,
        _browser_open=lambda url: opened.append(url) or True,
        _stdout=io.StringIO(),
    )
    assert code == 0
    assert opened == ["http://127.0.0.1:8765/#token=" + "d" * 64]
    assert [item[0] if isinstance(item, tuple) else item for item in events] == [
        "start",
        "wait",
        "stop",
    ]
    assert isinstance(runtime.config.session_id, str)
    assert runtime.config.session_id.startswith("monitor-")
    assert runtime.config.port == 8765


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


def test_open_prints_only_the_token_free_endpoint_to_stdout(tmp_path: Path) -> None:
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
    assert output.getvalue() == "http://127.0.0.1:45678/\n"


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


def test_open_enter_redelivers_same_endpoint_without_restart_and_sanitizes_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from stm32_monitor import cli

    project = tmp_path / "project"
    project.mkdir()
    events: list[str] = []
    urls: list[str] = []
    stdin = InteractiveInput()
    stdout, stderr = io.StringIO(), io.StringIO()
    enters = iter([True, True, True])
    monkeypatch.setattr(cli, "_poll_terminal_enter", lambda stream: next(enters, False))

    class WaitingRuntime(RecordingRuntime):
        closed = asyncio.Event()

        async def wait_closed(self) -> None:
            events.append("wait")
            await self.closed.wait()

    runtime = WaitingRuntime(events)

    def opener(url: str) -> bool:
        urls.append(url)
        if len(urls) == 2:
            return False
        if len(urls) == 3:
            raise ValueError("private " + url)
        if len(urls) == 4:
            runtime.closed.set()
        return True

    code = cli.main(
        ["open", "--project", str(project), "--data-root", str(tmp_path / "data")],
        _runtime_factory=lambda: runtime, _browser_open=opener,
        _stdin=stdin, _stdout=stdout, _stderr=stderr,
    )
    assert code == 0
    assert events == ["start", "wait", "stop"]
    assert len(urls) == 4 and len(set(urls)) == 1
    assert stdout.getvalue() == "http://127.0.0.1:45678/\n"
    assert "token" not in stdout.getvalue() + stderr.getvalue()
    assert urls[0] not in stdout.getvalue() + stderr.getvalue()
    assert "private" not in stderr.getvalue()
    assert stderr.getvalue().count("failed") == 2


def test_open_non_tty_does_not_poll_or_read_stdin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from stm32_monitor import cli

    class NonTtyInput(io.StringIO):
        def read(self, *args):
            raise AssertionError("stdin read")

    monkeypatch.setattr(cli, "_poll_terminal_enter", lambda stream: pytest.fail("poll"))
    project = tmp_path / "project"
    project.mkdir()
    output = io.StringIO()
    code = cli.main(
        ["open", "--project", str(project), "--data-root", str(tmp_path / "data")],
        _runtime_factory=lambda: RecordingRuntime([]), _browser_open=lambda url: True,
        _stdin=NonTtyInput(), _stdout=output,
    )
    assert code == 0
    assert output.getvalue() == "http://127.0.0.1:45678/\n"


def test_open_unavailable_stdin_waits_and_stops_without_polling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from stm32_monitor import cli

    monkeypatch.setattr(cli, "_poll_terminal_enter", lambda stream: pytest.fail("poll"))
    project = tmp_path / "project"
    project.mkdir()
    events: list[str] = []
    opened: list[str] = []
    stdout, stderr = io.StringIO(), io.StringIO()
    code = cli.main(
        ["open", "--project", str(project), "--data-root", str(tmp_path / "data")],
        _runtime_factory=lambda: RecordingRuntime(events),
        _browser_open=lambda url: opened.append(url) or True,
        _stdin=None, _stdout=stdout, _stderr=stderr,
    )
    assert code == 0
    assert events == ["start", "wait", "stop"]
    assert opened == [FakeEndpoint().access_url]
    assert stdout.getvalue() == "http://127.0.0.1:45678/\n"
    assert stderr.getvalue() == ""
    assert "token" not in stdout.getvalue() + stderr.getvalue()


@pytest.mark.parametrize("probe_error", [AttributeError, TypeError])
def test_open_unusable_stdin_probe_is_non_interactive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, probe_error: type[Exception]
) -> None:
    from stm32_monitor import cli

    class UnusableInput(io.StringIO):
        def isatty(self) -> bool:
            raise probe_error("private terminal detail")

    monkeypatch.setattr(cli, "_poll_terminal_enter", lambda stream: pytest.fail("poll"))
    project = tmp_path / "project"
    project.mkdir()
    events: list[str] = []
    stdout, stderr = io.StringIO(), io.StringIO()
    code = cli.main(
        ["open", "--project", str(project), "--data-root", str(tmp_path / "data")],
        _runtime_factory=lambda: RecordingRuntime(events), _browser_open=lambda url: True,
        _stdin=UnusableInput(), _stdout=stdout, _stderr=stderr,
    )
    assert code == 0
    assert events == ["start", "wait", "stop"]
    assert stdout.getvalue() == "http://127.0.0.1:45678/\n"
    assert stderr.getvalue() == ""


def test_open_cancellation_stops_runtime_before_wait_closed_settles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from stm32_monitor import cli

    monkeypatch.setattr(cli, "_poll_terminal_enter", lambda stream: False)
    project = tmp_path / "project"
    project.mkdir()
    runtime = FakeRuntime()
    started = asyncio.Event()

    async def never_closed() -> None:
        started.set()
        await asyncio.Event().wait()

    runtime.wait_closed = never_closed  # type: ignore[method-assign]

    async def run() -> None:
        task = asyncio.create_task(cli._open(
            cli.MonitorConfig(project, tmp_path / "data", "session-a"), runtime,
            lambda url: True, io.StringIO(), InteractiveInput(), io.StringIO(),
        ))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        assert runtime.stopped

    asyncio.run(run())
