from __future__ import annotations

import asyncio
import errno
import json
import multiprocessing
import os
import queue
from pathlib import Path

import pytest
from test_runtime import (
    FakeExporter,
    FakeStore,
    _project,
    _protocol_runtime,
    _ready_service,
)


async def _start_stop_and_assert_released(runtime, config, lock_path: Path) -> None:
    await runtime.start(config)
    try:
        record = runtime.runtime_record
    finally:
        await runtime.stop()
    assert not record.exists()
    assert lock_path.read_bytes() == b"\0"
    assert lock_path.stat().st_size == 1


@pytest.mark.parametrize(
    "initial_lock",
    (None, b"", b"\0"),
    ids=("fresh", "existing-empty", "existing-nul"),
)
def test_public_start_lock_fdopen_failure_releases_descriptor_and_allows_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, initial_lock: bytes | None
) -> None:
    import stm32_monitor.runtime as runtime_module
    from stm32_monitor.runtime import MonitorRuntimeError
    from stm32_toolkit.paths import WorkspacePaths
    from stm32_toolkit.project_model import load_project_model

    runtime, config, groups, histories, exporters, samplers, observations, requests = (
        _protocol_runtime(tmp_path)
    )
    project_before = {
        path.relative_to(config.project_root).as_posix(): path.read_bytes()
        for path in config.project_root.rglob("*")
        if path.is_file()
    }
    model = load_project_model(config.project_root)
    paths = WorkspacePaths.from_roots(
        config.data_root,
        config.project_root,
        model.logical_project_id,
        config.session_id,
    )
    lock_path = paths.workspace_root / ".monitor-runtime.lock"
    if initial_lock is None:
        assert not paths.workspace_root.exists()
    else:
        paths.workspace_root.mkdir(parents=True)
        lock_path.write_bytes(initial_lock)

    original_fdopen = runtime_module.os.fdopen
    injected_descriptors: list[int] = []
    fdopen_calls = 0

    def fail_once_for_lock(fd: int, *args: object, **kwargs: object):
        nonlocal fdopen_calls
        fdopen_calls += 1
        if fdopen_calls == 1:
            injected_descriptors.append(fd)
            raise OSError(errno.EMFILE, "injected lock allocation failure")
        return original_fdopen(fd, *args, **kwargs)

    monkeypatch.setattr(runtime_module.os, "fdopen", fail_once_for_lock)
    with pytest.raises(MonitorRuntimeError) as first_error:
        asyncio.run(runtime.start(config))
    assert first_error.value.code == "MONITOR_RUNTIME_BUSY"
    assert first_error.value.message == "A Monitor runtime already owns this workspace"
    assert fdopen_calls == 1
    assert len(injected_descriptors) == 1

    with pytest.raises(OSError) as closed_descriptor:
        os.fstat(injected_descriptors[0])
    assert closed_descriptor.value.errno == errno.EBADF

    expected_after_failure = b"" if initial_lock in (None, b"") else initial_lock
    assert lock_path.is_file()
    assert lock_path.read_bytes() == expected_after_failure
    assert {
        path.relative_to(paths.workspace_root).as_posix(): path.read_bytes()
        for path in paths.workspace_root.rglob("*")
        if path.is_file()
    } == {".monitor-runtime.lock": expected_after_failure}
    assert not groups
    assert not histories
    assert not exporters
    assert not samplers
    assert not observations
    assert not requests

    monkeypatch.setattr(runtime_module.os, "fdopen", original_fdopen)

    replacement = runtime_module.MonitorRuntime(
        group_store_factory=FakeStore,
        history_store_factory=FakeStore,
        exporter_factory=FakeExporter,
        sampler_factory=lambda *_args, **_kwargs: object(),
        observation_factory=lambda *_args, **_kwargs: None,
        service_factory=lambda *args, **kwargs: _ready_service(*args, **kwargs),
    )
    asyncio.run(_start_stop_and_assert_released(replacement, config, lock_path))
    assert {
        path.relative_to(config.project_root).as_posix(): path.read_bytes()
        for path in config.project_root.rglob("*")
        if path.is_file()
    } == project_before


@pytest.mark.parametrize("failure_phase", ("write", "flush", "fsync"))
def test_public_start_initialization_failure_releases_lock_and_allows_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_phase: str
) -> None:
    import stm32_monitor.runtime as runtime_module
    from stm32_monitor.runtime import MonitorRuntimeError
    from stm32_toolkit.paths import WorkspacePaths
    from stm32_toolkit.project_model import load_project_model

    runtime, config, groups, histories, exporters, samplers, observations, requests = (
        _protocol_runtime(tmp_path)
    )
    model = load_project_model(config.project_root)
    paths = WorkspacePaths.from_roots(
        config.data_root,
        config.project_root,
        model.logical_project_id,
        config.session_id,
    )
    lock_path = paths.workspace_root / ".monitor-runtime.lock"
    captured_fds: list[int] = []
    failed = False
    original_fdopen = runtime_module.os.fdopen
    original_fsync = runtime_module.os.fsync

    class FailingHandle:
        def __init__(self, wrapped):
            self._wrapped = wrapped

        def __getattr__(self, name):
            return getattr(self._wrapped, name)

        def write(self, value):
            nonlocal failed
            if failure_phase == "write" and not failed:
                failed = True
                raise OSError(errno.EIO, "injected lock write failure")
            return self._wrapped.write(value)

        def flush(self):
            nonlocal failed
            if failure_phase == "flush" and not failed:
                failed = True
                raise OSError(errno.EIO, "injected lock flush failure")
            return self._wrapped.flush()

        def close(self):
            return self._wrapped.close()

    def instrumented_fdopen(fd: int, *args: object, **kwargs: object):
        handle = original_fdopen(fd, *args, **kwargs)
        captured_fds.append(handle.fileno())
        return FailingHandle(handle)

    def instrumented_fsync(fd: int):
        nonlocal failed
        captured_fds.append(fd)
        if not failed:
            failed = True
            raise OSError(errno.EIO, "injected lock fsync failure")
        return original_fsync(fd)

    if failure_phase == "fsync":
        monkeypatch.setattr(runtime_module.os, "fsync", instrumented_fsync)
    else:
        monkeypatch.setattr(runtime_module.os, "fdopen", instrumented_fdopen)

    with pytest.raises(MonitorRuntimeError) as first_error:
        asyncio.run(runtime.start(config))
    assert first_error.value.code == "MONITOR_RUNTIME_BUSY"
    assert first_error.value.message == "A Monitor runtime already owns this workspace"
    assert failed
    assert len(captured_fds) == 1
    with pytest.raises(OSError) as closed_descriptor:
        os.fstat(captured_fds[0])
    assert closed_descriptor.value.errno == errno.EBADF
    assert lock_path.read_bytes() in (b"", b"\0")
    assert not groups
    assert not histories
    assert not exporters
    assert not samplers
    assert not observations
    assert not requests

    monkeypatch.setattr(runtime_module.os, "fdopen", original_fdopen)
    monkeypatch.setattr(runtime_module.os, "fsync", original_fsync)
    replacement = runtime_module.MonitorRuntime(
        group_store_factory=FakeStore,
        history_store_factory=FakeStore,
        exporter_factory=FakeExporter,
        sampler_factory=lambda *_args, **_kwargs: object(),
        observation_factory=lambda *_args, **_kwargs: None,
        service_factory=lambda *args, **kwargs: _ready_service(*args, **kwargs),
    )
    asyncio.run(_start_stop_and_assert_released(replacement, config, lock_path))


def _hold_public_runtime(
    project_root: str,
    data_root: str,
    release: object,
    events,
) -> None:
    from stm32_monitor.models import MonitorConfig
    from stm32_monitor.runtime import MonitorRuntime

    async def scenario() -> None:
        runtime = MonitorRuntime(
            group_store_factory=FakeStore,
            history_store_factory=FakeStore,
            exporter_factory=FakeExporter,
            sampler_factory=lambda *_args, **_kwargs: object(),
            observation_factory=lambda *_args, **_kwargs: None,
            service_factory=lambda *args, **kwargs: _ready_service(*args, **kwargs),
        )
        started = False
        stopped = False
        error_type = None
        error_code = None
        try:
            await runtime.start(
                MonitorConfig(Path(project_root), Path(data_root), "session-a")
            )
            started = True
            events.put({"event": "started", "pid": os.getpid()})
            while not release.is_set():
                await asyncio.sleep(0.01)
        except BaseException as error:
            error_type = type(error).__name__
            error_code = getattr(error, "code", None)
        finally:
            if started:
                try:
                    await runtime.stop()
                    stopped = True
                except BaseException as error:
                    error_type = type(error).__name__
                    error_code = getattr(error, "code", None)
            events.put(
                {
                    "event": "stopped" if stopped else "error",
                    "pid": os.getpid(),
                    "started": started,
                    "stopped": stopped,
                    "errorType": error_type,
                    "errorCode": error_code,
                }
            )

    asyncio.run(scenario())


def test_public_runtime_lock_competing_process_is_busy_then_reusable(tmp_path: Path) -> None:
    from stm32_monitor.models import MonitorConfig
    from stm32_monitor.runtime import MonitorRuntime, MonitorRuntimeError
    from stm32_toolkit.paths import WorkspacePaths
    from stm32_toolkit.project_model import load_project_model

    project = _project(tmp_path)
    data = (tmp_path / "data").resolve()
    config = MonitorConfig(project, data, "session-a")
    model = load_project_model(project)
    paths = WorkspacePaths.from_roots(data, project, model.logical_project_id, "session-a")
    context = multiprocessing.get_context("spawn")
    release = context.Event()
    events = context.Queue()
    owner = context.Process(
        target=_hold_public_runtime,
        args=(str(project), str(data), release, events),
    )
    owner.start()
    final_event = None
    try:
        try:
            started_event = events.get(timeout=15)
        except queue.Empty:
            pytest.fail("public child runtime did not report start")
        assert started_event["event"] == "started"
        assert type(started_event["pid"]) is int
        assert owner.is_alive(), "public child runtime exited before contention"
        print(json.dumps({"childRuntime": started_event}, sort_keys=True))
        contender = MonitorRuntime(
            group_store_factory=FakeStore,
            history_store_factory=FakeStore,
            exporter_factory=FakeExporter,
            sampler_factory=lambda *_args, **_kwargs: object(),
            observation_factory=lambda *_args, **_kwargs: None,
            service_factory=lambda *args, **kwargs: _ready_service(*args, **kwargs),
        )
        with pytest.raises(MonitorRuntimeError) as busy:
            asyncio.run(contender.start(config))
        assert busy.value.code == "MONITOR_RUNTIME_BUSY"
        assert busy.value.message == "A Monitor runtime already owns this workspace"
    finally:
        release.set()
        owner.join(15)
        if owner.is_alive():
            owner.terminate()
            owner.join(5)
        if owner.exitcode == 0:
            try:
                final_event = events.get(timeout=5)
            except queue.Empty:
                final_event = None
        events.close()
        events.join_thread()
    assert owner.exitcode == 0
    assert final_event is not None
    assert final_event["event"] == "stopped"
    assert type(final_event["pid"]) is int
    assert final_event["started"] is True
    assert final_event["stopped"] is True
    assert final_event["errorType"] is None
    assert final_event["errorCode"] is None
    print(json.dumps({"childRuntime": final_event}, sort_keys=True))

    replacement = MonitorRuntime(
        group_store_factory=FakeStore,
        history_store_factory=FakeStore,
        exporter_factory=FakeExporter,
        sampler_factory=lambda *_args, **_kwargs: object(),
        observation_factory=lambda *_args, **_kwargs: None,
        service_factory=lambda *args, **kwargs: _ready_service(*args, **kwargs),
    )
    asyncio.run(
        _start_stop_and_assert_released(
            replacement, config, paths.workspace_root / ".monitor-runtime.lock"
        )
    )


def test_public_flush_failure_settles_before_contending_start_and_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import stm32_monitor.runtime as runtime_module
    from stm32_monitor.runtime import MonitorRuntimeError
    from stm32_toolkit.paths import WorkspacePaths
    from stm32_toolkit.project_model import load_project_model

    runtime, config, groups, histories, exporters, samplers, observations, requests = (
        _protocol_runtime(tmp_path)
    )
    project = config.project_root
    data = config.data_root
    model = load_project_model(project)
    paths = WorkspacePaths.from_roots(data, project, model.logical_project_id, "session-a")
    lock_path = paths.workspace_root / ".monitor-runtime.lock"

    context = multiprocessing.get_context("spawn")
    release = context.Event()
    events = context.Queue()
    child_holder: dict[str, object] = {}
    coordination: dict[str, object] = {}
    original_fdopen = runtime_module.os.fdopen

    class FailingFlushHandle:
        def __init__(self, wrapped) -> None:
            self._wrapped = wrapped

        def __getattr__(self, name):
            return getattr(self._wrapped, name)

        def flush(self):
            if not coordination.get("flush_failed"):
                coordination["flush_failed"] = True
                raise OSError(errno.EIO, "injected lock flush failure")
            return self._wrapped.flush()

        def close(self):
            child = context.Process(
                target=_hold_public_runtime,
                args=(str(project), str(data), release, events),
            )
            child_holder["process"] = child
            child.start()
            try:
                started_event = events.get(timeout=15)
            except queue.Empty as error:
                coordination["child_start_error"] = type(error).__name__
                raise
            coordination["child_started"] = started_event
            return self._wrapped.close()

    def instrumented_fdopen(fd: int, *args: object, **kwargs: object):
        coordination["descriptor"] = fd
        return FailingFlushHandle(original_fdopen(fd, *args, **kwargs))

    monkeypatch.setattr(runtime_module.os, "fdopen", instrumented_fdopen)
    child = None
    final_event = None
    try:
        with pytest.raises(MonitorRuntimeError) as caught:
            asyncio.run(runtime.start(config))
        assert caught.value.code == "MONITOR_RUNTIME_BUSY"
        assert caught.value.message == "A Monitor runtime already owns this workspace"
        assert coordination["flush_failed"] is True
        started_event = coordination["child_started"]
        assert isinstance(started_event, dict)
        assert started_event["event"] == "started"
        assert type(started_event["pid"]) is int
        child = child_holder["process"]
        assert child.is_alive()
        assert not groups
        assert not histories
        assert not exporters
        assert not samplers
        assert not observations
        assert not requests
    finally:
        monkeypatch.setattr(runtime_module.os, "fdopen", original_fdopen)
        release.set()
        child = child_holder.get("process")
        if child is not None:
            child.join(15)
            if child.is_alive():
                child.terminate()
                child.join(5)
            if child.exitcode == 0:
                try:
                    final_event = events.get(timeout=5)
                except queue.Empty:
                    final_event = None
        events.close()
        events.join_thread()

    assert child is not None
    assert child.exitcode == 0
    assert isinstance(final_event, dict)
    assert final_event["event"] == "stopped"
    assert type(final_event["pid"]) is int
    assert final_event["started"] is True
    assert final_event["stopped"] is True
    assert final_event["errorType"] is None
    assert final_event["errorCode"] is None
    print(json.dumps({"childRuntime": final_event}, sort_keys=True))

    asyncio.run(_start_stop_and_assert_released(runtime, config, lock_path))


def test_public_cleanup_failure_closes_real_lock_descriptor_and_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import stm32_monitor.runtime as runtime_module
    from stm32_monitor.runtime import MonitorRuntimeError
    from stm32_toolkit.paths import WorkspacePaths
    from stm32_toolkit.project_model import load_project_model

    runtime, config, groups, histories, exporters, samplers, observations, requests = (
        _protocol_runtime(tmp_path)
    )
    project = config.project_root
    data = config.data_root
    model = load_project_model(project)
    paths = WorkspacePaths.from_roots(data, project, model.logical_project_id, "session-a")
    lock_path = paths.workspace_root / ".monitor-runtime.lock"

    original_fdopen = runtime_module.os.fdopen
    original_fsync = runtime_module.os.fsync
    captured_fds: list[int] = []
    close_calls = 0
    fsync_calls = 0

    class CloseThenRaiseHandle:
        def __init__(self, wrapped) -> None:
            self._wrapped = wrapped

        def __getattr__(self, name):
            return getattr(self._wrapped, name)

        def close(self):
            nonlocal close_calls
            close_calls += 1
            self._wrapped.close()
            raise OSError(errno.EIO, "injected lock close failure")

    def instrumented_fdopen(fd: int, *args: object, **kwargs: object):
        handle = original_fdopen(fd, *args, **kwargs)
        captured_fds.append(handle.fileno())
        return CloseThenRaiseHandle(handle)

    def failing_fsync(fd: int) -> None:
        nonlocal fsync_calls
        fsync_calls += 1
        if fsync_calls == 1:
            raise OSError(errno.EIO, "injected lock fsync failure")
        original_fsync(fd)

    monkeypatch.setattr(runtime_module.os, "fdopen", instrumented_fdopen)
    monkeypatch.setattr(runtime_module.os, "fsync", failing_fsync)
    with pytest.raises(MonitorRuntimeError) as caught:
        asyncio.run(runtime.start(config))
    assert caught.value.code == "MONITOR_CLEANUP_FAILED"
    assert caught.value.message == "Monitor runtime cleanup failed"
    assert close_calls == 1
    assert fsync_calls == 1
    assert len(captured_fds) == 1
    with pytest.raises(OSError) as closed_descriptor:
        os.fstat(captured_fds[0])
    assert closed_descriptor.value.errno == errno.EBADF
    assert lock_path.read_bytes() == b"\0"
    assert not (paths.session_root / "monitor-runtime.json").exists()
    assert not groups
    assert not histories
    assert not exporters
    assert not samplers
    assert not observations
    assert not requests

    monkeypatch.setattr(runtime_module.os, "fdopen", original_fdopen)
    monkeypatch.setattr(runtime_module.os, "fsync", original_fsync)
    asyncio.run(_start_stop_and_assert_released(runtime, config, lock_path))
