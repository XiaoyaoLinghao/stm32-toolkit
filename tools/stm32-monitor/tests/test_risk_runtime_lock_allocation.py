from __future__ import annotations

import asyncio
import errno
import os
from pathlib import Path

import pytest
from test_runtime import FakeExporter, FakeStore, _protocol_runtime, _ready_service


def test_public_start_lock_fdopen_failure_leaves_zero_byte_lock_for_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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
    assert not paths.workspace_root.exists()

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

    assert lock_path.is_file()
    assert lock_path.stat().st_size == 0
    assert lock_path.read_bytes() == b""
    assert {
        path.relative_to(paths.workspace_root).as_posix(): path.read_bytes()
        for path in paths.workspace_root.rglob("*")
        if path.is_file()
    } == {".monitor-runtime.lock": b""}
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
    with pytest.raises(MonitorRuntimeError) as retry_error:
        asyncio.run(replacement.start(config))
    assert retry_error.value.code == "MONITOR_RUNTIME_PATH_UNSAFE"
    assert retry_error.value.message == "Monitor runtime lock is unsafe"
    assert lock_path.read_bytes() == b""
    assert lock_path.stat().st_size == 0
    assert {
        path.relative_to(paths.workspace_root).as_posix(): path.read_bytes()
        for path in paths.workspace_root.rglob("*")
        if path.is_file()
    } == {".monitor-runtime.lock": b""}
    assert {
        path.relative_to(config.project_root).as_posix(): path.read_bytes()
        for path in config.project_root.rglob("*")
        if path.is_file()
    } == project_before
