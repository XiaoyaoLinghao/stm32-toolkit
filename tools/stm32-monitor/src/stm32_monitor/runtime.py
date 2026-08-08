"""Workspace-owned Monitor runtime and cancellation-safe lifecycle."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import os
import stat
from collections.abc import AsyncIterator, Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4

from stm32_toolkit import __version__ as TOOLKIT_VERSION
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.project_model import load_project_model

from .service import MONITOR_PROTOCOL_VERSION, MonitorEndpoint, MonitorService

_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class MonitorRuntimeError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _fail(code: str, message: str) -> MonitorRuntimeError:
    return MonitorRuntimeError(code, message)


def _redirect(path: Path, metadata: os.stat_result) -> bool:
    return path.is_symlink() or bool(
        getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT
    )


def _safe_project(value: object) -> Path:
    if not isinstance(value, Path) or not value.is_absolute():
        raise _fail("MONITOR_INPUT_INVALID", "Monitor project root is invalid")
    try:
        lexical = value.expanduser().absolute()
        metadata = os.lstat(lexical)
        canonical = lexical.resolve(strict=True)
    except (OSError, RuntimeError):
        raise _fail("MONITOR_INPUT_INVALID", "Monitor project root is invalid") from None
    if canonical != lexical or _redirect(lexical, metadata) or not stat.S_ISDIR(metadata.st_mode):
        raise _fail("MONITOR_INPUT_INVALID", "Monitor project root is invalid")
    return canonical


def _existing_prefixes(path: Path) -> tuple[Path, ...]:
    parts = path.parts
    if not parts:
        return ()
    current = Path(parts[0])
    result: list[Path] = [current]
    for component in parts[1:]:
        current /= component
        result.append(current)
    return tuple(result)


def _safe_data(value: object, project: Path) -> Path:
    if not isinstance(value, Path) or not value.is_absolute():
        raise _fail("MONITOR_INPUT_INVALID", "Monitor data root is invalid")
    lexical = value.expanduser().absolute()
    try:
        for component in _existing_prefixes(lexical):
            try:
                metadata = os.lstat(component)
            except FileNotFoundError:
                break
            if _redirect(component, metadata) or not stat.S_ISDIR(metadata.st_mode):
                raise OSError("unsafe data root")
        canonical = lexical.resolve(strict=False)
        canonical.relative_to(project)
    except ValueError:
        return canonical
    except (OSError, RuntimeError):
        raise _fail("MONITOR_INPUT_INVALID", "Monitor data root is invalid") from None
    raise _fail(
        "MONITOR_INPUT_INVALID", "Monitor data root must remain outside the project"
    )


def _ensure_owned_directory(data_root: Path, directory: Path) -> None:
    try:
        directory.relative_to(data_root)
        data_root.mkdir(parents=True, exist_ok=True)
        current = data_root
        relative = directory.relative_to(data_root)
        chain = (data_root, *(data_root.joinpath(*relative.parts[:index]) for index in range(1, len(relative.parts) + 1)))
        for current in chain:
            try:
                before = os.lstat(current)
            except FileNotFoundError:
                before = None
            if before is not None and (
                _redirect(current, before) or not stat.S_ISDIR(before.st_mode)
            ):
                raise OSError("unsafe runtime directory")
            current.mkdir(exist_ok=True)
            after = os.lstat(current)
            if _redirect(current, after) or not stat.S_ISDIR(after.st_mode):
                raise OSError("unsafe runtime directory")
            current.resolve(strict=True).relative_to(data_root.resolve(strict=True))
    except (OSError, RuntimeError, ValueError):
        raise _fail(
            "MONITOR_RUNTIME_PATH_UNSAFE", "Monitor runtime path is unavailable or unsafe"
        ) from None


class _WorkspaceLock:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._handle: BinaryIO | None = None

    def acquire(self) -> None:
        handle = self._path.open("a+b")
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
                os.fsync(handle.fileno())
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:  # pragma: no cover - exercised by Linux owner
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            handle.close()
            raise _fail("MONITOR_RUNTIME_BUSY", "A Monitor runtime already owns this workspace") from None
        self._handle = handle

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:  # pragma: no cover - exercised by Linux owner
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
            self._handle = None


def _atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    descriptor = -1
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = -1
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            os.chmod(path, 0o600)
    except OSError:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except OSError:
            pass
        raise _fail("MONITOR_RUNTIME_PATH_UNSAFE", "Monitor runtime record is unavailable") from None


async def _call_close(value: object | None) -> None:
    if value is None:
        return
    for name in ("close", "stop"):
        method = getattr(value, name, None)
        if callable(method):
            result = method()
            if inspect.isawaitable(result):
                await result
            return


async def _call(method: Callable[..., object], *args, **kwargs) -> object:
    result = method(*args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


def _exact(payload: Mapping[str, object], required: set[str], optional: set[str] | None = None) -> None:
    allowed = required | (optional or set())
    if set(payload) - allowed or not required.issubset(payload):
        raise ValueError("request fields are invalid")


def _integer(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("integer is invalid")
    return value


def _uuid(value: object) -> UUID:
    if not isinstance(value, str):
        raise ValueError("UUID is invalid")
    return UUID(value)


def _mapping_list(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise ValueError("items are invalid")
    return tuple(value)


def _probe_connect_request(payload: Mapping[str, object], request_type):
    _exact(payload, {"probeId", "expectedBuildId", "expectedElfSha256"})
    return request_type(
        payload["probeId"], payload["expectedBuildId"], payload["expectedElfSha256"]
    )


async def _await_owned(task: asyncio.Task[None]) -> asyncio.CancelledError | None:
    cancellation: asyncio.CancelledError | None = None
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError as error:
            if cancellation is None:
                cancellation = error
        except BaseException:
            break
    task.result()
    return cancellation


class MonitorRuntime:
    def __init__(
        self,
        *,
        group_store_factory: Callable[[WorkspacePaths], object] | None = None,
        history_store_factory: Callable[[WorkspacePaths], object] | None = None,
        exporter_factory: Callable[[WorkspacePaths, object], object] | None = None,
        sampler_factory: Callable[..., object] | None = None,
        observation_factory: Callable[..., object] | None = None,
        service_factory: Callable[..., object] = MonitorService,
    ) -> None:
        if group_store_factory is None:
            from .groups import GroupStore

            group_store_factory = GroupStore
        if history_store_factory is None:
            from .history import HistoryStore

            history_store_factory = HistoryStore
        if sampler_factory is None:
            from .sampler import MonitorSampler

            sampler_factory = MonitorSampler
        if observation_factory is None:
            from stm32_toolkit.monitor_observation import open_monitor_observation

            observation_factory = open_monitor_observation
        if exporter_factory is None:
            from .exports import HistoryExporter

            exporter_factory = HistoryExporter
        self._group_store_factory = group_store_factory
        self._history_store_factory = history_store_factory
        self._sampler_factory = sampler_factory
        self._observation_factory = observation_factory
        self._exporter_factory = exporter_factory
        self._service_factory = service_factory
        self._paths: WorkspacePaths | None = None
        self._config: object | None = None
        self._lock: _WorkspaceLock | None = None
        self._service: object | None = None
        self._group_store: object | None = None
        self._history_store: object | None = None
        self._exporter: object | None = None
        self._sampler: object | None = None
        self._observation: object | None = None
        self._probe_request: object | None = None
        self._endpoint: MonitorEndpoint | object | None = None
        self._runtime_record: Path | None = None
        self._cleanup_task: asyncio.Task[None] | None = None
        self._closed = asyncio.Event()

    @property
    def runtime_record(self) -> Path:
        if self._runtime_record is None:
            raise MonitorRuntimeError("MONITOR_SERVICE_UNAVAILABLE", "Monitor runtime is not started")
        return self._runtime_record

    async def start(self, config: object) -> MonitorEndpoint:
        from .models import MonitorConfig

        if type(config) is not MonitorConfig:
            raise _fail("MONITOR_INPUT_INVALID", "Monitor configuration is invalid")
        project = _safe_project(config.project_root)
        data = _safe_data(config.data_root, project)
        try:
            model = load_project_model(project)
            paths = WorkspacePaths.from_roots(
                data, project, model.logical_project_id, config.session_id
            )
        except Exception:
            raise _fail("MONITOR_INPUT_INVALID", "Monitor configuration is invalid") from None
        _ensure_owned_directory(paths.data_root, paths.workspace_root)
        _ensure_owned_directory(paths.data_root, paths.session_root)
        lock = _WorkspaceLock(paths.workspace_root / ".monitor-runtime.lock")
        lock.acquire()
        self._lock = lock
        self._paths = paths
        self._config = config
        try:
            groups = self._group_store_factory(paths)
            history = self._history_store_factory(paths)
            exporter = self._exporter_factory(paths, history)
            service = self._service_factory(
                self,
                workspace_id=paths.workspace_id,
                session_id=paths.session_id,
            )
            endpoint = await service.start()
            token = getattr(endpoint, "token", None)
            port = getattr(endpoint, "port", None)
            if (
                not isinstance(token, str)
                or len(token) != 64
                or any(character not in "0123456789abcdef" for character in token)
                or getattr(endpoint, "host", None) != "127.0.0.1"
                or type(port) is not int
                or not 1 <= port <= 65_535
                or getattr(endpoint, "workspace_id", None) != paths.workspace_id
                or getattr(endpoint, "session_id", None) != paths.session_id
            ):
                raise ValueError("invalid endpoint")
            record = paths.session_root / "monitor-runtime.json"
            _atomic_json(
                record,
                {
                    "protocol": MONITOR_PROTOCOL_VERSION,
                    "toolkitVersion": TOOLKIT_VERSION,
                    "host": "127.0.0.1",
                    "port": port,
                    "pid": os.getpid(),
                    "startedAtUtc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    "workspaceId": paths.workspace_id,
                    "sessionId": paths.session_id,
                    "tokenSha256": hashlib.sha256(token.encode("ascii")).hexdigest(),
                },
            )
        except BaseException:
            try:
                if "service" in locals():
                    await _call_close(service)
                if "exporter" in locals():
                    await _call_close(exporter)
                if "history" in locals():
                    await _call_close(history)
                if "groups" in locals():
                    await _call_close(groups)
            finally:
                lock.release()
                self._lock = None
            raise
        self._group_store = groups
        self._history_store = history
        self._exporter = exporter
        self._service = service
        self._endpoint = endpoint
        self._runtime_record = record
        self._closed.clear()
        return endpoint

    async def dispatch(
        self,
        operation: str,
        payload: dict[str, object],
        *,
        resource_id: str | None = None,
        query: dict[str, str] | None = None,
    ) -> object:
        from .exports import ExportRequest
        from .history import HistoryQuery
        from .models import ProbeConnectRequest, WatchItem
        from .protocol import ProtocolResult, failure, success

        paths = self._paths
        config = self._config
        groups = self._group_store
        history = self._history_store
        exporter = self._exporter
        if paths is None or config is None or groups is None or history is None or exporter is None:
            return failure(operation, "MONITOR_SERVICE_UNAVAILABLE", "Monitor runtime is not started")
        try:
            if operation == "monitor.status":
                _exact(payload, set())
                return success(
                    operation,
                    {
                        "workspaceId": paths.workspace_id,
                        "sessionId": paths.session_id,
                        "probeConnected": self._observation is not None,
                        "samplingActive": self._sampler is not None,
                    },
                )
            if operation == "monitor.groups.list":
                _exact(payload, set())
                return groups.list_groups()
            if operation == "monitor.groups.create":
                _exact(payload, {"name", "description", "intervalMs", "items", "authorized"})
                items = tuple(WatchItem.from_dict(item) for item in _mapping_list(payload["items"]))
                return groups.create_group(
                    payload["name"], payload["description"], _integer(payload["intervalMs"]), items,
                    authorized=payload["authorized"],
                )
            if operation == "monitor.groups.update":
                _exact(
                    payload,
                    {"expectedRevision", "authorized"},
                    {"name", "description", "intervalMs", "items"},
                )
                group_id = _uuid(resource_id)
                changes: dict[str, object] = {}
                for public, internal in (("name", "name"), ("description", "description")):
                    if public in payload:
                        changes[internal] = payload[public]
                if "intervalMs" in payload:
                    changes["interval_ms"] = _integer(payload["intervalMs"])
                if "items" in payload:
                    changes["items"] = tuple(
                        WatchItem.from_dict(item) for item in _mapping_list(payload["items"])
                    )
                return groups.update_group(
                    group_id,
                    expected_revision=_integer(payload["expectedRevision"]),
                    authorized=payload["authorized"],
                    **changes,
                )
            if operation == "monitor.groups.delete":
                _exact(payload, {"expectedRevision", "authorized"})
                return groups.delete_group(
                    _uuid(resource_id),
                    expected_revision=_integer(payload["expectedRevision"]),
                    authorized=payload["authorized"],
                )
            if operation == "monitor.groups.import":
                _exact(payload, {"document", "authorized"})
                document = json.dumps(
                    payload["document"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
                return groups.import_groups(document, authorized=payload["authorized"])
            if operation in {"monitor.probe.connect", "monitor.probe.reconnect"}:
                initial_connect = operation == "monitor.probe.connect"
                if initial_connect:
                    request = _probe_connect_request(payload, ProbeConnectRequest)
                else:
                    _exact(payload, set())
                    request = self._probe_request
                    if request is None:
                        return failure(operation, "MONITOR_REQUEST_INVALID", "No prior probe request exists")
                    await self._release_probe()
                result = await self._connect_probe(
                    operation, config, request, ProtocolResult, failure, success
                )
                if initial_connect and result.ok:
                    self._probe_request = request
                return result
            if operation == "monitor.probe.release":
                _exact(payload, set())
                await self._release_probe()
                return success(operation, {"released": True})
            if operation == "monitor.sampling.start":
                _exact(payload, {"groupId", "expectedRevision"})
                sampler = self._sampler
                if sampler is None:
                    return failure(operation, "MONITOR_REQUEST_INVALID", "A probe must be connected")
                return await _call(
                    sampler.start,
                    _uuid(payload["groupId"]),
                    expected_revision=_integer(payload["expectedRevision"]),
                )
            if operation in {
                "monitor.sampling.pause",
                "monitor.sampling.resume",
                "monitor.sampling.stop",
            }:
                _exact(payload, set())
                sampler = self._sampler
                if sampler is None:
                    return failure(operation, "MONITOR_REQUEST_INVALID", "A probe must be connected")
                action = operation.rsplit(".", 1)[1]
                return await _call(getattr(sampler, action))
            if operation == "monitor.history.query":
                _exact(payload, set())
                expected = {"sessionId", "startNs", "endNs"}
                allowed = expected | {"limit", "cursor"}
                if query is None or set(query) - allowed or not expected.issubset(query):
                    raise ValueError("history query is invalid")
                history_query = HistoryQuery(
                    query["sessionId"],
                    int(query["startNs"]),
                    int(query["endNs"]),
                    limit=int(query.get("limit", "10000")),
                    cursor=query.get("cursor"),
                )
                return history.query_history(history_query)
            if operation == "monitor.exports.create":
                _exact(payload, {"sessionId", "startNs", "endNs", "format", "authorized"})
                request = ExportRequest(
                    payload["sessionId"],
                    _integer(payload["startNs"]),
                    _integer(payload["endNs"]),
                    payload["format"],
                )
                return exporter.create_export(request, authorized=payload["authorized"])
            if operation == "monitor.exports.get":
                _exact(payload, set())
                return exporter.get_export(_uuid(resource_id))
        except (AttributeError, TypeError, ValueError):
            return failure(operation, "MONITOR_REQUEST_INVALID", "Monitor request is invalid")
        return failure(operation, "MONITOR_REQUEST_INVALID", "Monitor operation is unsupported")

    async def _connect_probe(self, operation, config, request, result_type, failure, success):
        from stm32_toolkit.monitor_observation import MonitorObservationRequest

        if self._observation is not None:
            return failure(operation, "MONITOR_PROBE_BUSY", "A probe is already connected")
        observation_request = MonitorObservationRequest(
            config.project_root,
            config.data_root,
            config.session_id,
            request.probe_id,
            request.expected_build_id,
            request.expected_elf_sha256,
        )
        opened = await _call(self._observation_factory, observation_request)
        if not isinstance(opened, result_type) and not all(
            hasattr(opened, name) for name in ("ok", "code", "message", "data")
        ):
            return failure(operation, "MONITOR_INTERNAL_ERROR", "Probe connection failed")
        if opened.ok is not True:
            return failure(operation, opened.code, opened.message, getattr(opened, "details", {}))
        observation = opened.data
        if observation is None:
            return failure(operation, "MONITOR_INTERNAL_ERROR", "Probe connection failed")
        try:
            sampler = self._sampler_factory(observation, self._group_store, self._history_store)
        except Exception:
            await _call_close(observation)
            raise
        self._observation = observation
        self._sampler = sampler
        binding = getattr(observation, "binding", None)
        return success(operation, binding.to_dict() if hasattr(binding, "to_dict") else {"connected": True})

    async def _release_probe(self) -> None:
        sampler, observation = self._sampler, self._observation
        self._sampler = None
        self._observation = None
        await _call_close(sampler)
        await _call_close(observation)

    async def live_subscribe(self) -> AsyncIterator[dict[str, object]]:
        sampler = self._sampler
        if sampler is None:
            while self._paths is not None:
                await asyncio.sleep(3600)
            return
        source = sampler.subscribe()
        async for item in source:
            if hasattr(item, "to_dict"):
                yield item.to_dict()
            elif isinstance(item, Mapping):
                yield dict(item)

    async def wait_closed(self) -> None:
        await self._closed.wait()

    async def stop(self) -> None:
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(
                self._stop_owned(), name="stm32-monitor-runtime-stop"
            )
        cancellation = await _await_owned(self._cleanup_task)
        if cancellation is not None:
            raise cancellation

    async def _stop_owned(self) -> None:
        first_error: BaseException | None = None
        for value in (
            self._service,
            self._sampler,
            self._observation,
            self._exporter,
            self._history_store,
            self._group_store,
        ):
            try:
                await _call_close(value)
            except BaseException as error:
                if first_error is None:
                    first_error = error
        record = self._runtime_record
        if record is not None:
            try:
                record.unlink()
            except FileNotFoundError:
                pass
            except OSError as error:
                if first_error is None:
                    first_error = error
        lock = self._lock
        if lock is not None:
            try:
                lock.release()
            except BaseException as error:
                if first_error is None:
                    first_error = error
        self._service = None
        self._sampler = None
        self._observation = None
        self._history_store = None
        self._exporter = None
        self._group_store = None
        self._endpoint = None
        self._paths = None
        self._lock = None
        self._config = None
        self._closed.set()
        if first_error is not None:
            raise _fail("MONITOR_CLEANUP_FAILED", "Monitor runtime cleanup failed") from None


__all__ = ["MonitorRuntime", "MonitorRuntimeError"]
