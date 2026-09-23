from __future__ import annotations

import asyncio
import errno
import multiprocessing
import os
from pathlib import Path

import pytest
from test_runtime import (
    FakeExporter,
    FakeStore,
    _project,
    _protocol_runtime,
    _ready_service,
)


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
    asyncio.run(replacement.start(config))
    try:
        assert lock_path.read_bytes() == b"\0"
        assert lock_path.stat().st_size == 1
    finally:
        asyncio.run(replacement.stop())
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
    asyncio.run(replacement.start(config))
    try:
        assert lock_path.read_bytes() == b"\0"
    finally:
        asyncio.run(replacement.stop())


def _hold_public_runtime(
    project_root: str,
    data_root: str,
    ready: object,
    release: object,
    errors,
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
        try:
            await runtime.start(
                MonitorConfig(Path(project_root), Path(data_root), "session-a")
            )
            ready.set()
            while not release.is_set():
                await asyncio.sleep(0.01)
            await runtime.stop()
        except BaseException as error:
            errors.put(
                (
                    type(error).__name__,
                    getattr(error, "code", None),
                    getattr(error, "message", str(error)),
                )
            )
            ready.set()

    asyncio.run(scenario())


def test_public_runtime_lock_competing_process_is_busy_then_reusable(tmp_path: Path) -> None:
    from stm32_monitor.models import MonitorConfig
    from stm32_monitor.runtime import MonitorRuntime, MonitorRuntimeError

    project = _project(tmp_path)
    data = (tmp_path / "data").resolve()
    config = MonitorConfig(project, data, "session-a")
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    release = context.Event()
    errors = context.Queue()
    owner = context.Process(
        target=_hold_public_runtime,
        args=(str(project), str(data), ready, release, errors),
    )
    owner.start()
    try:
        assert ready.wait(15), "public child runtime did not reach start"
        assert errors.empty()
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
    assert owner.exitcode == 0
    assert errors.empty()

    replacement = MonitorRuntime(
        group_store_factory=FakeStore,
        history_store_factory=FakeStore,
        exporter_factory=FakeExporter,
        sampler_factory=lambda *_args, **_kwargs: object(),
        observation_factory=lambda *_args, **_kwargs: None,
        service_factory=lambda *args, **kwargs: _ready_service(*args, **kwargs),
    )
    asyncio.run(replacement.start(config))
    asyncio.run(replacement.stop())
