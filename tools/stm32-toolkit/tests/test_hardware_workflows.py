from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from stm32_toolkit.hardware_workflows import (
    FaultWorkflowRequest,
    FlashWorkflowRequest,
    HandoffBeginWorkflowRequest,
    HandoffEndWorkflowRequest,
    HardwareWorkflowSeams,
    ProbeListWorkflowRequest,
    RegisterReadWorkflowRequest,
    VariableReadWorkflowRequest,
    VariableSampleWorkflowRequest,
    fault_workflow,
    flash_workflow,
    handoff_begin_workflow,
    handoff_end_workflow,
    probe_list_workflow,
    register_read_workflow,
    variable_read_workflow,
    variable_sample_workflow,
)
from stm32_toolkit.identity import compute_workspace_id
from stm32_toolkit.probe.backend import ProbeDescriptor
from stm32_toolkit.probe.model import OperationLevel
from stm32_toolkit.result import OperationResult


BUILD_ID = "1" * 64
ELF_SHA = "2" * 64
TICKET = "3" * 64


def _project(root: Path, *, svd: str | None = "device.svd", schema_version: int = 2) -> Path:
    root.mkdir()
    manifest = {
        "schemaVersion": schema_version,
        "logicalProjectId": "12345678-1234-5678-1234-567812345678",
        "generatedBy": {"tool": "stm32-toolkit", "version": "0.4.0"},
        "project": {"name": "hardware", "origin": "manual"},
        "target": {"device": "STM32F407VGTx", "core": "cortex-m4"},
        "framework": {"type": "spl", "version": None},
        "build": {
            "sources": [],
            "includePaths": [],
            "defines": [],
            "compileOptions": [],
            "assemblySources": [],
            "presets": ["arm-debug"],
            "elf": "build/arm-debug/firmware.elf",
        },
        "memory": {
            "source": "manual",
            "regions": [
                {"name": "FLASH", "origin": 0x08000000, "length": 0x100000, "attributes": "r-x"},
                {"name": "RAM", "origin": 0x20000000, "length": 0x20000, "attributes": "rwx"},
                {"name": "PERIPH", "origin": 0x40000000, "length": 0x10000000, "attributes": "rw-"},
            ],
        },
        "debug": {"backend": "pyocd", "target": "stm32f407vg", "svd": svd},
        "generation": {
            "cubeMxIoc": None,
            "managedManifest": ".stm32-toolkit/generated-files.json",
            "generatedDirectories": [],
            "userDirectories": [],
        },
    }
    if schema_version == 1:
        for key in ("generatedBy", "memory", "generation"):
            manifest.pop(key)
        manifest["build"].pop("presets")
    (root / ".stm32-project.json").write_bytes(
        (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    )
    if svd is not None:
        (root / svd).write_bytes(b"<device/>")
    return root.resolve()


@dataclass
class _Recorder:
    events: list[str]
    configs: list[object]

    def __init__(self) -> None:
        self.events = []
        self.configs = []


class _Client:
    def __init__(self, endpoint: object, recorder: _Recorder, *, close_error: bool = False) -> None:
        self.endpoint = endpoint
        self._recorder = recorder
        self._close_error = close_error

    async def close(self) -> None:
        self._recorder.events.append("client.close")
        if self._close_error:
            raise RuntimeError("secret close failure C:\\private\\runtime token=bad")


class _Supervisor:
    def __init__(self, config: object, recorder: _Recorder, *, stop_error: bool = False) -> None:
        self._config = config
        self._recorder = recorder
        self._stop_error = stop_error
        self.endpoint = None
        recorder.configs.append(config)

    async def start(self, **kwargs: object) -> object:
        self._recorder.events.append("supervisor.start")
        self.endpoint = SimpleNamespace(
            workspace_id=self._config.workspace_id,
            session_id=self._config.session_id,
            lease_id="lease-secret",
            probe_id=self._config.probe_id,
            operation_level=self._config.operation_level,
            token="token-secret",
            record_path=self._config.session_root / "probe-endpoint.json",
        )
        return self.endpoint

    async def stop(self) -> None:
        self._recorder.events.append("supervisor.stop")
        if self._stop_error:
            raise RuntimeError("private cleanup path C:\\runtime")
        self.endpoint = None


class _Backend:
    def __init__(self, recorder: _Recorder, *, list_error: bool = False) -> None:
        self._recorder = recorder
        self._list_error = list_error

    def list_probes(self) -> tuple[ProbeDescriptor, ...]:
        self._recorder.events.append("backend.list")
        if self._list_error:
            raise RuntimeError("serial token C:\\private")
        return (
            ProbeDescriptor("probe-a", "Arm", "CMSIS-DAP", None),
            ProbeDescriptor("probe-b", "ST", "ST-Link", "Board"),
        )

    def close(self) -> None:
        self._recorder.events.append("backend.close")


def _seams(
    recorder: _Recorder,
    *,
    operation: object | None = None,
    binding: object | None = None,
    stop_error: bool = False,
    close_error: bool = False,
    list_error: bool = False,
) -> HardwareWorkflowSeams:
    async def bind(request: object, client: object) -> OperationResult[object]:
        recorder.events.append("bind")
        recorder.binding_request = request
        return OperationResult.success("bind", binding if binding is not None else SimpleNamespace())

    async def default_operation(request: object, client: object) -> OperationResult[object]:
        recorder.events.append("operation")
        recorder.operation_request = request
        return OperationResult.success(
            "accepted-operation",
            {"status": "accepted", "leaseId": "must-not-leak", "nested": {"token": "bad"}},
        )

    selected_operation = operation or default_operation

    async def handoff_begin(request: object, supervisor: object, client: object) -> OperationResult[object]:
        return await selected_operation(request, client)

    async def handoff_end(
        ticket: object, supervisor: object, client_factory: object
    ) -> OperationResult[object]:
        return await selected_operation(ticket, None)

    return HardwareWorkflowSeams(
        backend_factory=lambda: _Backend(recorder, list_error=list_error),
        lease_manager_factory=lambda data_root: SimpleNamespace(data_root=data_root),
        supervisor_factory=lambda config, lease_manager, backend_factory: _Supervisor(
            config, recorder, stop_error=stop_error
        ),
        client_factory=lambda endpoint: _Client(endpoint, recorder, close_error=close_error),
        flash=selected_operation,
        handoff_begin=handoff_begin,
        handoff_end=handoff_end,
        bind=bind,
        read_variables=selected_operation,
        sample_variables=selected_operation,
        read_registers=selected_operation,
        analyze_fault=selected_operation,
        catalog_from_binding=lambda value: recorder.events.append("catalog") or "catalog",
        svd_select=lambda *args, **kwargs: recorder.events.append("svd") or "selection",
    )


def _run(awaitable: object) -> object:
    return asyncio.run(awaitable)


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_probe_list_is_bounded_read_only_and_closes_backend_without_lease(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    data_root = tmp_path / "data-alias" / ".." / "data"
    recorder = _Recorder()
    before = _snapshot(project)

    result = _run(
        probe_list_workflow(
            ProbeListWorkflowRequest(project, data_root, "session-a"),
            _seams=_seams(recorder),
        )
    )

    assert result.ok
    payload = result.to_dict()["data"]
    assert payload["sessionId"] == "session-a"
    assert payload["workspaceId"] == compute_workspace_id(
        UUID("12345678-1234-5678-1234-567812345678"), project
    )
    assert [item["probeId"] for item in payload["probes"]] == ["probe-a", "probe-b"]
    assert recorder.events == ["backend.list", "backend.close"]
    assert recorder.configs == []
    assert _snapshot(project) == before
    assert not data_root.resolve().exists()


def test_flash_derives_target_and_workspace_and_uses_modify_with_exact_pins(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    data_root = tmp_path / "data"
    recorder = _Recorder()

    result = _run(
        flash_workflow(
            FlashWorkflowRequest(
                project, data_root, "flash-session", "probe-a", BUILD_ID, ELF_SHA, True
            ),
            _seams=_seams(recorder),
        )
    )

    assert result.ok
    config = recorder.configs[0]
    request = recorder.operation_request
    assert config.operation_level is OperationLevel.MODIFY
    assert config.probe_id == "probe-a"
    assert config.session_id == "flash-session"
    assert config.project_root == project
    assert request.project_root == project
    assert request.probe_id == "probe-a"
    assert request.target == "stm32f407vg"
    assert request.expected_build_id == BUILD_ID
    assert request.expected_elf_sha256 == ELF_SHA
    assert request.authorized is True
    assert recorder.events == ["supervisor.start", "operation", "client.close", "supervisor.stop"]
    assert (data_root / "projects" / config.workspace_id / "sessions" / "flash-session").is_dir()
    assert not (data_root / "projects" / config.workspace_id / "monitor").exists()


@pytest.mark.parametrize("authorized", [False, "true", 1, None, [], {}])
def test_intrusive_workflows_require_exact_true_before_service(
    tmp_path: Path, authorized: object
) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()
    result = _run(
        flash_workflow(
            FlashWorkflowRequest(
                project, tmp_path / "data", "session-a", "probe-a", BUILD_ID, ELF_SHA, authorized
            ),
            _seams=_seams(recorder),
        )
    )
    assert not result.ok
    assert result.code == "AUTHORIZATION_REQUIRED"
    assert recorder.events == []


def test_handoff_begin_and_end_use_observe_and_end_before_release(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()
    seams = _seams(recorder)

    begin = _run(
        handoff_begin_workflow(
            HandoffBeginWorkflowRequest(
                project,
                tmp_path / "data",
                "origin-session",
                "probe-a",
                BUILD_ID,
                ELF_SHA,
                True,
                ("counter",),
            ),
            _seams=seams,
        )
    )
    assert begin.ok
    assert recorder.configs[0].operation_level is OperationLevel.OBSERVE
    request = recorder.operation_request
    assert request.expected_build_id == BUILD_ID
    assert request.expected_elf_sha256 == ELF_SHA
    assert request.authorized is True
    assert request.previous_watch_selection == ("counter",)

    recorder.events.clear()
    end = _run(
        handoff_end_workflow(
            HandoffEndWorkflowRequest(
                project, tmp_path / "data", "origin-session", "probe-a", TICKET
            ),
            _seams=seams,
        )
    )
    assert end.ok
    assert recorder.configs[-1].operation_level is OperationLevel.OBSERVE
    assert recorder.operation_request == TICKET
    assert recorder.events == ["operation", "supervisor.stop"]


@pytest.mark.parametrize(
    ("name", "request_factory", "workflow", "expected_event"),
    [
        (
            "variables",
            lambda p, d: VariableReadWorkflowRequest(
                p, d, "observe-a", "probe-a", BUILD_ID, ELF_SHA, ("counter",)
            ),
            variable_read_workflow,
            "catalog",
        ),
        (
            "sample",
            lambda p, d: VariableSampleWorkflowRequest(
                p, d, "observe-a", "probe-a", BUILD_ID, ELF_SHA, ("counter",), 100, 2, None
            ),
            variable_sample_workflow,
            "catalog",
        ),
        (
            "registers",
            lambda p, d: RegisterReadWorkflowRequest(
                p, d, "observe-a", "probe-a", BUILD_ID, ELF_SHA, ("GPIOA.IDR",), False
            ),
            register_read_workflow,
            "svd",
        ),
        (
            "fault",
            lambda p, d: FaultWorkflowRequest(
                p, d, "observe-a", "probe-a", BUILD_ID, ELF_SHA
            ),
            fault_workflow,
            None,
        ),
    ],
)
def test_read_workflows_bind_current_firmware_and_call_accepted_contracts(
    tmp_path: Path, name: str, request_factory: object, workflow: object, expected_event: str | None
) -> None:
    project = _project(tmp_path / f"project-{name}")
    recorder = _Recorder()
    binding = SimpleNamespace(project_root=project, memory_regions=("region",))

    result = _run(
        workflow(
            request_factory(project, tmp_path / f"data-{name}"),
            _seams=_seams(recorder, binding=binding),
        )
    )

    assert result.ok
    assert recorder.configs[0].operation_level is OperationLevel.OBSERVE
    bind = recorder.binding_request
    assert bind.project_root == project
    assert bind.probe_id == "probe-a"
    assert bind.target == "stm32f407vg"
    assert bind.workspace_id == recorder.configs[0].workspace_id
    assert bind.observation_session_id == "observe-a"
    assert bind.lease_id == "lease-secret"
    assert bind.expected_build_id == BUILD_ID
    assert bind.expected_elf_sha256 == ELF_SHA
    if expected_event is not None:
        assert expected_event in recorder.events
    if name == "variables":
        assert recorder.operation_request.catalog == "catalog"
        assert recorder.operation_request.expressions == ("counter",)
    elif name == "sample":
        assert recorder.operation_request.catalog == "catalog"
        assert recorder.operation_request.interval_ms == 100
        assert recorder.operation_request.count == 2
    elif name == "registers":
        assert recorder.operation_request.selection == "selection"
        assert recorder.operation_request.paths == ("GPIOA.IDR",)
    else:
        assert recorder.operation_request.binding is binding
    serialized = json.dumps(result.to_dict())
    assert "lease-secret" not in serialized
    assert "must-not-leak" not in serialized
    assert '"token"' not in serialized


def test_register_workflow_requires_exact_project_svd_before_service(tmp_path: Path) -> None:
    project = _project(tmp_path / "project", svd=None)
    recorder = _Recorder()
    result = _run(
        register_read_workflow(
            RegisterReadWorkflowRequest(
                project,
                tmp_path / "data",
                "session-a",
                "probe-a",
                BUILD_ID,
                ELF_SHA,
                ("GPIOA.IDR",),
                False,
            ),
            _seams=_seams(recorder),
        )
    )
    assert not result.ok
    assert result.code == "SVD_SELECTION_REQUIRED"
    assert recorder.events == []


def test_schema_v2_session_and_portable_input_validation_precedes_hardware(tmp_path: Path) -> None:
    project = _project(tmp_path / "project", schema_version=1)
    recorder = _Recorder()
    result = _run(
        variable_read_workflow(
            VariableReadWorkflowRequest(
                project, tmp_path / "data", "unsafe/session", "probe-a", BUILD_ID, ELF_SHA, ("x",)
            ),
            _seams=_seams(recorder),
        )
    )
    assert not result.ok
    assert result.code == "HARDWARE_INPUT_INVALID"
    assert recorder.events == []


def test_unsafe_existing_session_component_is_rejected_before_service(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    data = tmp_path / "data"
    (data / "projects").mkdir(parents=True)
    # The exact workspace component is unknown until the model is loaded, so a
    # file at the fixed projects component proves fail-closed traversal.
    (data / "projects").rmdir()
    (data / "projects").write_bytes(b"not a directory")
    recorder = _Recorder()
    result = _run(
        flash_workflow(
            FlashWorkflowRequest(project, data, "session-a", "probe-a", BUILD_ID, ELF_SHA, True),
            _seams=_seams(recorder),
        )
    )
    assert not result.ok
    assert result.code == "HARDWARE_RUNTIME_PATH_UNSAFE"
    assert recorder.events == []


def test_cleanup_failure_replaces_success_and_is_sanitized(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()
    result = _run(
        variable_read_workflow(
            VariableReadWorkflowRequest(
                project, tmp_path / "data", "session-a", "probe-a", BUILD_ID, ELF_SHA, ("x",)
            ),
            _seams=_seams(recorder, stop_error=True),
        )
    )
    assert not result.ok
    assert result.code == "HARDWARE_CLEANUP_FAILED"
    serialized = json.dumps(result.to_dict())
    assert "private" not in serialized.lower()
    assert "runtime" not in serialized.lower()


def test_raw_operation_exception_is_sanitized_and_cleanup_runs(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()

    async def explode(request: object, client: object) -> OperationResult[object]:
        recorder.events.append("operation")
        raise RuntimeError("token-secret C:\\private\\runtime")

    result = _run(
        flash_workflow(
            FlashWorkflowRequest(
                project, tmp_path / "data", "session-a", "probe-a", BUILD_ID, ELF_SHA, True
            ),
            _seams=_seams(recorder, operation=explode),
        )
    )
    assert not result.ok
    assert result.code == "HARDWARE_INTERNAL_ERROR"
    assert recorder.events[-2:] == ["client.close", "supervisor.stop"]
    serialized = json.dumps(result.to_dict())
    assert "token-secret" not in serialized
    assert "private" not in serialized


def test_cancellation_waits_for_client_and_service_cleanup_then_propagates(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()
    entered = asyncio.Event()

    async def block(request: object, client: object) -> OperationResult[object]:
        recorder.events.append("operation")
        entered.set()
        await asyncio.Future()

    async def scenario() -> None:
        task = asyncio.create_task(
            variable_read_workflow(
                VariableReadWorkflowRequest(
                    project,
                    tmp_path / "data",
                    "session-a",
                    "probe-a",
                    BUILD_ID,
                    ELF_SHA,
                    ("x",),
                ),
                _seams=_seams(recorder, operation=block),
            )
        )
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert recorder.events[-2:] == ["client.close", "supervisor.stop"]


def test_repeated_cancellation_cannot_interrupt_owned_transport_or_service_cleanup(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()
    operation_entered = asyncio.Event()
    close_entered = asyncio.Event()
    close_release = asyncio.Event()
    stop_entered = asyncio.Event()
    stop_release = asyncio.Event()

    class BarrierClient(_Client):
        async def close(self) -> None:
            recorder.events.append("client.close.enter")
            close_entered.set()
            await close_release.wait()
            recorder.events.append("client.close.exit")

    class BarrierSupervisor(_Supervisor):
        async def stop(self) -> None:
            recorder.events.append("supervisor.stop.enter")
            stop_entered.set()
            await stop_release.wait()
            recorder.events.append("supervisor.stop.exit")

    async def block(request: object, client: object) -> OperationResult[object]:
        recorder.events.append("operation")
        operation_entered.set()
        await asyncio.Future()

    seams = replace(
        _seams(recorder, operation=block),
        supervisor_factory=lambda config, lease_manager, backend_factory: BarrierSupervisor(
            config, recorder
        ),
        client_factory=lambda endpoint: BarrierClient(endpoint, recorder),
    )

    async def scenario() -> None:
        task = asyncio.create_task(
            variable_read_workflow(
                VariableReadWorkflowRequest(
                    project,
                    tmp_path / "data",
                    "session-a",
                    "probe-a",
                    BUILD_ID,
                    ELF_SHA,
                    ("x",),
                ),
                _seams=seams,
            )
        )
        await operation_entered.wait()
        task.cancel()
        await close_entered.wait()
        task.cancel()
        await asyncio.sleep(0)
        assert "client.close.exit" not in recorder.events
        assert "supervisor.stop.enter" not in recorder.events
        close_release.set()
        await stop_entered.wait()
        task.cancel()
        await asyncio.sleep(0)
        assert "supervisor.stop.exit" not in recorder.events
        stop_release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert recorder.events[-4:] == [
        "client.close.enter",
        "client.close.exit",
        "supervisor.stop.enter",
        "supervisor.stop.exit",
    ]


def test_probe_list_failure_and_close_failure_are_stable(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()
    result = _run(
        probe_list_workflow(
            ProbeListWorkflowRequest(project, tmp_path / "data", "session-a"),
            _seams=_seams(recorder, list_error=True),
        )
    )
    assert not result.ok
    assert result.code == "PROBE_ENUMERATION_FAILED"
    assert recorder.events == ["backend.list", "backend.close"]
    assert "private" not in json.dumps(result.to_dict()).lower()


def test_nested_missing_data_root_is_created_without_extra_workspace_directories(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()
    data_root = tmp_path / "missing" / "nested" / "data"
    result = _run(
        flash_workflow(
            FlashWorkflowRequest(
                project, data_root, "session-a", "probe-a", BUILD_ID, ELF_SHA, True
            ),
            _seams=_seams(recorder),
        )
    )
    assert result.ok
    config = recorder.configs[0]
    assert config.session_root.is_dir()
    assert not (config.session_root.parent.parent / "monitor").exists()


def test_probe_list_cancellation_waits_for_enumeration_before_backend_close(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path / "project")
    entered = threading.Event()
    release = threading.Event()
    exited = threading.Event()
    closed_concurrently: list[bool] = []

    class BlockingBackend:
        def list_probes(self) -> tuple[ProbeDescriptor, ...]:
            entered.set()
            release.wait(2)
            exited.set()
            return ()

        def close(self) -> None:
            closed_concurrently.append(not exited.is_set())

    seams = HardwareWorkflowSeams(backend_factory=BlockingBackend)

    async def scenario() -> None:
        task = asyncio.create_task(
            probe_list_workflow(
                ProbeListWorkflowRequest(project, tmp_path / "data", "session-a"),
                _seams=seams,
            )
        )
        await asyncio.to_thread(entered.wait, 1)
        task.cancel()
        threading.Timer(0.05, release.set).start()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert closed_concurrently == [False]


def test_probe_list_repeated_cancellation_waits_for_list_then_owned_close(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path / "project")
    list_entered = threading.Event()
    list_release = threading.Event()
    list_exited = threading.Event()
    close_entered = threading.Event()
    close_release = threading.Event()
    closed_concurrently: list[bool] = []

    class BlockingBackend:
        def list_probes(self) -> tuple[ProbeDescriptor, ...]:
            list_entered.set()
            list_release.wait(2)
            list_exited.set()
            return ()

        def close(self) -> None:
            closed_concurrently.append(not list_exited.is_set())
            close_entered.set()
            close_release.wait(2)

    async def scenario() -> None:
        task = asyncio.create_task(
            probe_list_workflow(
                ProbeListWorkflowRequest(project, tmp_path / "data", "session-a"),
                _seams=HardwareWorkflowSeams(backend_factory=BlockingBackend),
            )
        )
        await asyncio.to_thread(list_entered.wait, 1)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not close_entered.is_set()
        list_release.set()
        await asyncio.to_thread(close_entered.wait, 1)
        task.cancel()
        assert not task.done()
        close_release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert closed_concurrently == [False]


def test_cleanup_failure_has_priority_over_repeated_cancellation(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()
    operation_entered = asyncio.Event()
    close_entered = asyncio.Event()
    close_release = asyncio.Event()

    class FailingClient(_Client):
        async def close(self) -> None:
            close_entered.set()
            await close_release.wait()
            raise RuntimeError("transport cleanup failed")

    async def block(request: object, client: object) -> OperationResult[object]:
        operation_entered.set()
        await asyncio.Future()

    seams = replace(
        _seams(recorder, operation=block),
        client_factory=lambda endpoint: FailingClient(endpoint, recorder),
    )

    async def scenario() -> object:
        task = asyncio.create_task(
            flash_workflow(
                FlashWorkflowRequest(
                    project,
                    tmp_path / "data",
                    "session-a",
                    "probe-a",
                    BUILD_ID,
                    ELF_SHA,
                    True,
                ),
                _seams=seams,
            )
        )
        await operation_entered.wait()
        task.cancel()
        await close_entered.wait()
        task.cancel()
        close_release.set()
        return await task

    result = asyncio.run(scenario())
    assert not result.ok
    assert result.code == "HARDWARE_CLEANUP_FAILED"
    assert recorder.events[-1] == "supervisor.stop"


def test_catalog_stable_failure_is_preserved_and_absolute_roots_are_redacted(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()

    class CatalogError(Exception):
        code = "DWARF_INPUT_CHANGED"
        message = "ELF changed after catalog creation"
        details = {"source": str(project / "build" / "firmware.elf")}

    seams = _seams(recorder, binding=SimpleNamespace(project_root=project))
    seams = replace(
        seams,
        catalog_from_binding=lambda binding: (_ for _ in ()).throw(CatalogError()),
    )
    result = _run(
        variable_read_workflow(
            VariableReadWorkflowRequest(
                project, tmp_path / "data", "session-a", "probe-a", BUILD_ID, ELF_SHA, ("x",)
            ),
            _seams=seams,
        )
    )
    assert not result.ok
    assert result.code == "DWARF_INPUT_CHANGED"
    assert str(project).lower() not in json.dumps(result.to_dict()).lower()


def test_handoff_end_closes_the_client_created_by_the_accepted_contract(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()

    async def handoff_end(ticket: object, supervisor: object, client_factory: object) -> OperationResult[object]:
        endpoint = await supervisor.start(handoff_ticket=ticket)
        client_factory(endpoint)
        recorder.events.append("handoff.end")
        return OperationResult.success("handoff-end", {"restored": True})

    seams = _seams(recorder)
    seams = replace(seams, handoff_end=handoff_end)
    result = _run(
        handoff_end_workflow(
            HandoffEndWorkflowRequest(
                project, tmp_path / "data", "session-a", "probe-a", TICKET
            ),
            _seams=seams,
        )
    )
    assert result.ok
    assert recorder.events == [
        "supervisor.start",
        "handoff.end",
        "client.close",
        "supervisor.stop",
    ]


@pytest.mark.parametrize(
    "invalid_input",
    [
        object(),
        FlashWorkflowRequest(Path("missing"), Path("data"), "session-a", "probe-a", BUILD_ID, ELF_SHA, True),
    ],
)
def test_invalid_request_or_project_is_rejected_without_hardware(
    tmp_path: Path, invalid_input: object
) -> None:
    recorder = _Recorder()
    result = _run(flash_workflow(invalid_input, _seams=_seams(recorder)))
    assert not result.ok
    assert result.code == "HARDWARE_INPUT_INVALID"
    assert recorder.events == []


@pytest.mark.parametrize(
    ("probe_id", "build_id", "elf_sha"),
    [
        ("bad/probe", BUILD_ID, ELF_SHA),
        ("probe-a", "BAD", ELF_SHA),
        ("probe-a", BUILD_ID, "BAD"),
    ],
)
def test_probe_and_firmware_pins_fail_closed_before_service(
    tmp_path: Path, probe_id: str, build_id: str, elf_sha: str
) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()
    result = _run(
        fault_workflow(
            FaultWorkflowRequest(
                project, tmp_path / "data", "session-a", probe_id, build_id, elf_sha
            ),
            _seams=_seams(recorder),
        )
    )
    assert not result.ok
    assert result.code == "HARDWARE_INPUT_INVALID"
    assert recorder.events == []


@pytest.mark.parametrize("expressions", [(), ("x", "x"), ("",), ("bad\x00name",)])
def test_variable_selection_is_bounded_and_portable(
    tmp_path: Path, expressions: tuple[str, ...]
) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()
    result = _run(
        variable_read_workflow(
            VariableReadWorkflowRequest(
                project,
                tmp_path / "data",
                "session-a",
                "probe-a",
                BUILD_ID,
                ELF_SHA,
                expressions,
            ),
            _seams=_seams(recorder),
        )
    )
    assert not result.ok
    assert result.code == "HARDWARE_INPUT_INVALID"
    assert recorder.events == []


@pytest.mark.parametrize(
    ("interval", "count", "duration"),
    [(0, 1, None), (100, None, None), (100, 0, None), (100, None, 0)],
)
def test_sampling_requires_a_finite_bounded_request(
    tmp_path: Path, interval: int, count: int | None, duration: int | None
) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()
    result = _run(
        variable_sample_workflow(
            VariableSampleWorkflowRequest(
                project,
                tmp_path / "data",
                "session-a",
                "probe-a",
                BUILD_ID,
                ELF_SHA,
                ("x",),
                interval,
                count,
                duration,
            ),
            _seams=_seams(recorder),
        )
    )
    assert not result.ok
    assert result.code == "HARDWARE_INPUT_INVALID"
    assert recorder.events == []


def test_handoff_and_register_strict_inputs_are_rejected_before_service(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()
    seams = _seams(recorder)

    unauthorized = _run(
        handoff_begin_workflow(
            HandoffBeginWorkflowRequest(
                project, tmp_path / "data", "session-a", "probe-a", BUILD_ID, ELF_SHA, False
            ),
            _seams=seams,
        )
    )
    invalid_watch = _run(
        handoff_begin_workflow(
            HandoffBeginWorkflowRequest(
                project,
                tmp_path / "data",
                "session-a",
                "probe-a",
                BUILD_ID,
                ELF_SHA,
                True,
                ("",),
            ),
            _seams=seams,
        )
    )
    invalid_ticket = _run(
        handoff_end_workflow(
            HandoffEndWorkflowRequest(
                project, tmp_path / "data", "session-a", "probe-a", "bad"
            ),
            _seams=seams,
        )
    )
    invalid_ack = _run(
        register_read_workflow(
            RegisterReadWorkflowRequest(
                project,
                tmp_path / "data",
                "session-a",
                "probe-a",
                BUILD_ID,
                ELF_SHA,
                ("GPIOA.IDR",),
                "true",
            ),
            _seams=seams,
        )
    )
    assert unauthorized.code == "AUTHORIZATION_REQUIRED"
    assert invalid_watch.code == "HARDWARE_INPUT_INVALID"
    assert invalid_ticket.code == "HARDWARE_INPUT_INVALID"
    assert invalid_ack.code == "HARDWARE_INPUT_INVALID"
    assert recorder.events == []


def test_bind_failure_short_circuits_typed_operation_and_is_sanitized(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()

    async def bind(request: object, client: object) -> OperationResult[object]:
        recorder.events.append("bind")
        return OperationResult.failure(
            "bind", "DEBUG_BINDING_LOST", "Debug binding is unavailable", {"leaseId": "secret"}
        )

    seams = replace(_seams(recorder), bind=bind)
    result = _run(
        fault_workflow(
            FaultWorkflowRequest(
                project, tmp_path / "data", "session-a", "probe-a", BUILD_ID, ELF_SHA
            ),
            _seams=seams,
        )
    )
    assert not result.ok
    assert result.code == "DEBUG_BINDING_LOST"
    assert recorder.events == ["supervisor.start", "bind", "client.close", "supervisor.stop"]
    assert "lease" not in json.dumps(result.to_dict()).lower()


def test_invalid_service_identity_and_missing_client_close_fail_stably(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()

    class WrongSupervisor(_Supervisor):
        async def start(self, **kwargs: object) -> object:
            endpoint = await super().start(**kwargs)
            endpoint.probe_id = "wrong-probe"
            return endpoint

    seams = replace(
        _seams(recorder),
        supervisor_factory=lambda config, lease_manager, backend_factory: WrongSupervisor(config, recorder),
    )
    invalid = _run(
        flash_workflow(
            FlashWorkflowRequest(
                project, tmp_path / "data", "session-a", "probe-a", BUILD_ID, ELF_SHA, True
            ),
            _seams=seams,
        )
    )
    assert invalid.code == "HARDWARE_SERVICE_INVALID"

    recorder = _Recorder()
    seams = replace(_seams(recorder), client_factory=lambda endpoint: SimpleNamespace(endpoint=endpoint))
    missing_close = _run(
        flash_workflow(
            FlashWorkflowRequest(
                project, tmp_path / "data2", "session-b", "probe-a", BUILD_ID, ELF_SHA, True
            ),
            _seams=seams,
        )
    )
    assert missing_close.code == "HARDWARE_CLEANUP_FAILED"


def test_probe_list_rejects_unbounded_data_and_reports_close_failure(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()

    class TooManyBackend(_Backend):
        def list_probes(self) -> tuple[ProbeDescriptor, ...]:
            return tuple(
                ProbeDescriptor(f"probe-{index}", "v", "p", None) for index in range(65)
            )

        def close(self) -> None:
            raise RuntimeError("close failed")

    result = _run(
        probe_list_workflow(
            ProbeListWorkflowRequest(project, tmp_path / "data", "session-a"),
            _seams=replace(_seams(recorder), backend_factory=lambda: TooManyBackend(recorder)),
        )
    )
    assert result.code == "HARDWARE_CLEANUP_FAILED"


def test_fatal_operation_exit_runs_owned_cleanup_then_propagates(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()

    async def fatal(request: object, client: object) -> OperationResult[object]:
        recorder.events.append("operation")
        raise SystemExit(7)

    with pytest.raises(SystemExit):
        _run(
            flash_workflow(
                FlashWorkflowRequest(
                    project,
                    tmp_path / "data",
                    "session-a",
                    "probe-a",
                    BUILD_ID,
                    ELF_SHA,
                    True,
                ),
                _seams=_seams(recorder, operation=fatal),
            )
        )
    assert recorder.events[-2:] == ["client.close", "supervisor.stop"]


def test_fatal_enumeration_exit_closes_backend_then_propagates(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    recorder = _Recorder()

    class FatalBackend(_Backend):
        def list_probes(self) -> tuple[ProbeDescriptor, ...]:
            recorder.events.append("backend.list")
            raise SystemExit(8)

    with pytest.raises(SystemExit):
        _run(
            probe_list_workflow(
                ProbeListWorkflowRequest(project, tmp_path / "data", "session-a"),
                _seams=replace(
                    _seams(recorder), backend_factory=lambda: FatalBackend(recorder)
                ),
            )
        )
    assert recorder.events == ["backend.list", "backend.close"]
