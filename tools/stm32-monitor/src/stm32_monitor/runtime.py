"""Workspace-owned Monitor runtime and cancellation-safe lifecycle."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import os
import re
import stat
import unicodedata
from collections import deque
from collections.abc import AsyncIterator, Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4

from stm32_toolkit import __version__ as TOOLKIT_VERSION
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.project_model import load_project_model

from .service import MONITOR_PROTOCOL_VERSION, MONITOR_VERSION, MonitorEndpoint, MonitorService

_LIVE_END = object()
_REPLAY_EVENTS = 256
_LIVE_QUEUE_EVENTS = 256

_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_WINDOWS_ABSOLUTE = re.compile(r"[A-Za-z]:[\\/]")


class MonitorRuntimeError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _fail(code: str, message: str) -> MonitorRuntimeError:
    return MonitorRuntimeError(code, message)


def _probe_public_text(value: object, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if type(value) is not str:
        raise ValueError("probe metadata is invalid")
    normalized = unicodedata.normalize("NFC", value)
    portable = normalized.replace("\\", "/")
    if (
        not normalized
        or normalized != value
        or normalized.strip() != normalized
        or len(normalized) > 128
        or any(ord(character) < 32 or ord(character) == 127 for character in normalized)
        or normalized.startswith(("/", "\\"))
        or _WINDOWS_ABSOLUTE.match(normalized) is not None
        or any(component in (".", "..") for component in portable.split("/"))
    ):
        raise ValueError("probe metadata is invalid")
    return normalized


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
        handle: BinaryIO | None = None
        descriptor = -1
        created = False
        try:
            flags = os.O_RDWR | getattr(os, "O_BINARY", 0)
            try:
                descriptor = os.open(
                    self._path, flags | os.O_CREAT | os.O_EXCL, 0o600
                )
                created = True
                before = os.fstat(descriptor)
            except FileExistsError:
                before = os.lstat(self._path)
                self._validate_metadata(before)
                descriptor = os.open(
                    self._path, flags | getattr(os, "O_NOFOLLOW", 0)
                )
            handle = os.fdopen(descriptor, "r+b", closefd=True)
            descriptor = -1
            opened = os.fstat(handle.fileno())
            after = os.lstat(self._path)
            expected = self._validate_metadata(before)
            if self._validate_metadata(opened) != expected or self._validate_metadata(after) != expected:
                raise _fail(
                    "MONITOR_RUNTIME_PATH_UNSAFE", "Monitor runtime lock is unsafe"
                )
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            if created and size == 0:
                handle.write(b"\0")
                handle.flush()
                os.fsync(handle.fileno())
            elif not created and size == 1:
                handle.seek(0)
                if handle.read(1) != b"\0":
                    raise _fail(
                        "MONITOR_RUNTIME_PATH_UNSAFE", "Monitor runtime lock is unsafe"
                    )
            else:
                raise _fail(
                    "MONITOR_RUNTIME_PATH_UNSAFE", "Monitor runtime lock is unsafe"
                )
            if (
                self._validate_metadata(os.fstat(handle.fileno())) != expected
                or self._validate_metadata(os.lstat(self._path)) != expected
            ):
                raise _fail(
                    "MONITOR_RUNTIME_PATH_UNSAFE", "Monitor runtime lock is unsafe"
                )
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:  # pragma: no cover - exercised by Linux owner
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            if self._validate_metadata(os.lstat(self._path)) != expected:
                raise _fail(
                    "MONITOR_RUNTIME_PATH_UNSAFE", "Monitor runtime lock is unsafe"
                )
        except MonitorRuntimeError:
            if handle is not None:
                handle.close()
            elif descriptor >= 0:
                os.close(descriptor)
            raise
        except (OSError, BlockingIOError):
            if handle is not None:
                handle.close()
            elif descriptor >= 0:
                os.close(descriptor)
            raise _fail("MONITOR_RUNTIME_BUSY", "A Monitor runtime already owns this workspace") from None
        self._handle = handle

    def _validate_metadata(self, metadata: os.stat_result) -> tuple[int, int]:
        if (
            stat.S_ISLNK(metadata.st_mode)
            or bool(getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT)
            or not stat.S_ISREG(metadata.st_mode)
            or getattr(metadata, "st_nlink", 1) != 1
        ):
            raise _fail(
                "MONITOR_RUNTIME_PATH_UNSAFE", "Monitor runtime lock is unsafe"
            )
        return metadata.st_dev, metadata.st_ino

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


async def _close_independent(values: tuple[object | None, ...]) -> BaseException | None:
    first_error: BaseException | None = None
    for value in values:
        try:
            await _call_close(value)
        except BaseException as error:
            if first_error is None:
                first_error = error
    return first_error


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
    _exact(payload, {"probeId"})
    return request_type(payload["probeId"])


def _firmware_status(project_root: Path):
    from stm32_toolkit.probe.flash import _load_fresh_firmware

    from .models import FirmwareStatus

    current = _load_fresh_firmware(project_root)
    identity = current.identity
    return FirmwareStatus(
        str(identity["buildId"]),
        str(identity["elfSha256"]),
        str(identity["inputSnapshotSha256"]),
        str(identity["gitHead"]),
        identity["gitDirty"],
        str(identity["targetDevice"]),
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
        firmware_status_factory: Callable[[Path], object] = _firmware_status,
        probe_list_factory: Callable[..., object] | None = None,
        service_factory: Callable[..., object] = MonitorService,
        heartbeat_interval_seconds: float = 15.0,
        serve_ui: bool = False,
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
        if probe_list_factory is None:
            from stm32_toolkit.hardware_workflows import probe_list_workflow

            probe_list_factory = probe_list_workflow
        if exporter_factory is None:
            from .exports import HistoryExporter

            exporter_factory = HistoryExporter
        self._group_store_factory = group_store_factory
        self._history_store_factory = history_store_factory
        self._sampler_factory = sampler_factory
        self._observation_factory = observation_factory
        self._firmware_status_factory = firmware_status_factory
        self._probe_list_factory = probe_list_factory
        self._exporter_factory = exporter_factory
        self._service_factory = service_factory
        self._serve_ui = serve_ui
        if (
            type(heartbeat_interval_seconds) not in (int, float)
            or not 0.01 <= float(heartbeat_interval_seconds) <= 300
        ):
            raise ValueError("heartbeat interval is invalid")
        self._heartbeat_interval_seconds = float(heartbeat_interval_seconds)
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
        self._probe_lifecycle_lock = asyncio.Lock()
        self._binding_epoch = 0
        self._service_drops_total = 0
        self._event_id = 0
        self._state_revision = 0
        self._public_sequence = 0
        self._events: deque[object] = deque(maxlen=_REPLAY_EVENTS)
        self._private_anchors: deque[tuple[int, int, tuple[object, ...]]] = deque(
            maxlen=_REPLAY_EVENTS
        )
        self._live_subscribers: set[asyncio.Queue[object]] = set()
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._sample_task: asyncio.Task[None] | None = None
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
        groups: object | None = None
        history: object | None = None
        exporter: object | None = None
        service: object | None = None
        try:
            groups = self._group_store_factory(paths)
            history = self._history_store_factory(paths)
            exporter = self._exporter_factory(paths, history)
            service = self._service_factory(
                self,
                workspace_id=paths.workspace_id,
                session_id=paths.session_id,
                serve_ui=self._serve_ui,
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
                or getattr(endpoint, "monitor_version", None) != MONITOR_VERSION
            ):
                raise ValueError("invalid endpoint")
            record = paths.session_root / "monitor-runtime.json"
            _atomic_json(
                record,
                {
                    "protocol": MONITOR_PROTOCOL_VERSION,
                    "toolkitVersion": TOOLKIT_VERSION,
                    "monitorVersion": MONITOR_VERSION,
                    "host": "127.0.0.1",
                    "port": port,
                    "pid": os.getpid(),
                    "startedAtUtc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    "workspaceId": paths.workspace_id,
                    "sessionId": paths.session_id,
                    "tokenSha256": hashlib.sha256(token.encode("ascii")).hexdigest(),
                },
            )
        except BaseException as start_error:
            async def cleanup_partial() -> None:
                close_error = await _close_independent(
                    (service, exporter, history, groups)
                )
                lock_error: BaseException | None = None
                try:
                    lock.release()
                except BaseException as error:
                    lock_error = error
                if close_error is not None or lock_error is not None:
                    raise _fail(
                        "MONITOR_CLEANUP_FAILED", "Monitor runtime cleanup failed"
                    )

            cleanup = asyncio.create_task(
                cleanup_partial(), name="stm32-monitor-partial-start-cleanup"
            )
            cleanup_error: BaseException | None = None
            cleanup_cancellation: asyncio.CancelledError | None = None
            try:
                cleanup_cancellation = await _await_owned(cleanup)
            except BaseException as error:
                cleanup_error = error
            self._lock = None
            self._paths = None
            self._config = None
            if cleanup_error is not None:
                if not isinstance(cleanup_error, Exception):
                    raise cleanup_error
                raise _fail(
                    "MONITOR_CLEANUP_FAILED", "Monitor runtime cleanup failed"
                ) from None
            if isinstance(start_error, asyncio.CancelledError):
                raise start_error
            if cleanup_cancellation is not None:
                raise cleanup_cancellation
            raise start_error
        self._group_store = groups
        self._history_store = history
        self._exporter = exporter
        self._service = service
        self._endpoint = endpoint
        self._runtime_record = record
        self._closed.clear()
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(), name="stm32-monitor-heartbeat"
        )
        return endpoint

    def _publish_event(self, kind: str, data: Mapping[str, object]) -> dict[str, object]:
        from .models import LiveEvent

        self._event_id += 1
        event = LiveEvent(self._event_id, kind, data)
        self._public_sequence += 1
        self._events.append(event)
        for queue in tuple(self._live_subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                else:
                    self._service_drops_total += 1
            queue.put_nowait(event)
        return event.to_dict()

    def _private_event(self, kind: str, data: Mapping[str, object]):
        from .models import LiveEvent

        self._event_id += 1
        return LiveEvent(self._event_id, kind, data)

    def _bootstrap_events(self, *, gap: bool) -> tuple[dict[str, object], dict[str, object]]:
        assert self._paths is not None and self._config is not None
        hello = self._private_event(
            "hello",
            {
                "protocol": MONITOR_PROTOCOL_VERSION,
                "toolkitVersion": TOOLKIT_VERSION,
                "monitorVersion": MONITOR_VERSION,
                "stateRevision": self._state_revision,
            },
        )
        state = self._private_event(
            "state",
            {
                "stateRevision": self._state_revision,
                "gap": gap,
                "status": self._status(self._paths, self._config),
            },
        )
        self._private_anchors.append(
            (hello.event_id, self._public_sequence, (state,))
        )
        self._private_anchors.append(
            (state.event_id, self._public_sequence, ())
        )
        return hello.to_dict(), state.to_dict()

    def _publish_state(
        self, *, gap: bool = False, increment_revision: bool = True
    ) -> dict[str, object]:
        if self._paths is None or self._config is None:
            return {}
        if increment_revision:
            self._state_revision += 1
        return self._publish_event(
            "state",
            {
                "stateRevision": self._state_revision,
                "gap": gap,
                "status": self._status(self._paths, self._config),
            },
        )

    def _publish_sample(
        self, batch: Mapping[str, object], *, service_subscriber_drops: int = 0
    ) -> dict[str, object]:
        return self._publish_event(
            "sample",
            {
                "batch": dict(batch),
                "serviceSubscriberDrops": service_subscriber_drops,
            },
        )

    def _publish_heartbeat(self) -> dict[str, object]:
        return self._publish_event(
            "heartbeat",
            {
                "stateRevision": self._state_revision,
                "capturedAtUtc": datetime.now(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%S.%fZ"
                ),
            },
        )

    async def _heartbeat_loop(self) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._heartbeat_interval_seconds
        while self._paths is not None:
            await asyncio.sleep(max(0.0, deadline - loop.time()))
            if self._paths is None:
                return
            self._publish_heartbeat()
            deadline += self._heartbeat_interval_seconds
            now = loop.time()
            if deadline <= now:
                deadline = now + self._heartbeat_interval_seconds

    def _sampler_state_changed(self, _state: object) -> None:
        self._publish_state()

    async def _forward_samples(self, sampler: object) -> None:
        source = sampler.subscribe_deliveries()
        async for delivery in source:
            drops = getattr(delivery, "subscriber_drops", 0)
            drops = drops if type(drops) is int and drops > 0 else 0
            item = getattr(delivery, "batch", None)
            if hasattr(item, "to_dict"):
                payload = item.to_dict()
            elif isinstance(item, Mapping):
                payload = dict(item)
            else:
                continue
            self._service_drops_total += drops
            self._publish_sample(payload, service_subscriber_drops=drops)

    def record_service_drops(self, count: int) -> None:
        if type(count) is int and count > 0:
            self._service_drops_total += count

    def _current_firmware(self):
        from .models import FirmwareStatus

        paths = self._paths
        if paths is None:
            return None
        try:
            current = self._firmware_status_factory(paths.project_root)
        except Exception:
            return None
        return current if type(current) is FirmwareStatus else None

    async def _list_probes(self, operation: str, config, failure, success):
        from stm32_toolkit.hardware_workflows import ProbeListWorkflowRequest
        from stm32_toolkit.probe.backend import ProbeDescriptor
        from .models import ProbeConnectRequest

        request = ProbeListWorkflowRequest(
            config.project_root, config.data_root, config.session_id
        )
        try:
            result = await _call(self._probe_list_factory, request)
        except asyncio.CancelledError:
            raise
        except Exception:
            return failure(operation, "MONITOR_PROBE_ENUMERATION_FAILED", "Debug probe enumeration failed")
        if getattr(result, "ok", None) is not True:
            return failure(
                operation,
                "MONITOR_PROBE_ENUMERATION_FAILED",
                "Debug probe enumeration failed",
            )
        data = getattr(result, "data", None)
        probes = data.get("probes") if isinstance(data, Mapping) else None
        public_schema = frozenset({"probeId", "vendor", "product", "boardName"})
        production_schema = public_schema | frozenset({"hardwareId", "probeFingerprint"})
        if (
            type(probes) is not tuple
            or len(probes) > 64
        ):
            return failure(operation, "MONITOR_PROBE_ENUMERATION_FAILED", "Debug probe enumeration failed")
        try:
            schema = None
            if probes:
                if not isinstance(probes[0], Mapping):
                    raise ValueError("probe descriptor is invalid")
                schema = frozenset(probes[0])
                if schema not in (public_schema, production_schema):
                    raise ValueError("probe descriptor schema is invalid")
                if any(
                    not isinstance(item, Mapping) or frozenset(item) != schema
                    for item in probes
                ):
                    raise ValueError("probe descriptor schema is invalid")

            def project(item):
                probe_id = ProbeConnectRequest(item["probeId"]).probe_id
                vendor = _probe_public_text(item["vendor"])
                product = _probe_public_text(item["product"])
                board_name = _probe_public_text(item["boardName"], optional=True)
                if schema == production_schema:
                    descriptor = ProbeDescriptor(
                        probe_id=probe_id,
                        hardware_id=item["hardwareId"],
                        probe_fingerprint=item["probeFingerprint"],
                        vendor=vendor,
                        product=product,
                        board_name=board_name,
                    )
                    if (
                        descriptor.probe_id != item["probeId"]
                        or descriptor.hardware_id != item["hardwareId"]
                        or descriptor.probe_fingerprint != item["probeFingerprint"]
                    ):
                        raise ValueError("probe descriptor identity is invalid")
                return {
                    "probeId": probe_id,
                    "vendor": vendor,
                    "product": product,
                    "boardName": board_name,
                }

            ordered = sorted(
                (project(item) for item in probes),
                key=lambda item: item["probeId"],
            )
        except (KeyError, TypeError, ValueError):
            return failure(operation, "MONITOR_PROBE_ENUMERATION_FAILED", "Debug probe enumeration failed")
        if len({item["probeId"] for item in ordered}) != len(ordered):
            return failure(operation, "MONITOR_PROBE_ENUMERATION_FAILED", "Debug probe enumeration failed")
        return success(operation, {"probes": ordered})

    def _status(self, paths, config) -> dict[str, object]:
        model = load_project_model(paths.project_root)
        firmware = self._current_firmware()
        observation = self._observation
        raw_binding = getattr(observation, "binding", None)
        probe_id = getattr(raw_binding, "probe_id", None)
        if probe_id is None:
            payload = raw_binding.to_dict() if hasattr(raw_binding, "to_dict") else None
            probe_id = payload.get("probeId") if isinstance(payload, Mapping) else None
        sampler = self._sampler
        raw_state = getattr(sampler, "state", "IDLE") if sampler is not None else "IDLE"
        state = getattr(raw_state, "value", raw_state)
        if state not in {"IDLE", "STARTING", "RUNNING", "PAUSED", "PAUSED_BLOCKED", "STOPPING"}:
            state = "IDLE"
        group = getattr(sampler, "_group", None)
        run_id = getattr(sampler, "_run_id", None)
        sequence = getattr(sampler, "_sequence", 0)
        def drop_total(name: str) -> int:
            value = getattr(sampler, name, 0) if sampler is not None else 0
            return value if type(value) is int and value >= 0 else 0
        return {
            "workspaceId": paths.workspace_id,
            "sessionId": paths.session_id,
            "project": {
                "logicalProjectId": str(model.logical_project_id),
                "name": model.project.name,
                "targetDevice": model.target.device,
            },
            "firmware": None if firmware is None else firmware.to_dict(),
            "probe": {"connected": observation is not None, "probeId": probe_id},
            "sampling": {
                "state": state,
                "active": state in {"RUNNING", "PAUSED"},
                "blockedCode": getattr(sampler, "blocked_code", None),
                "groupId": None if group is None else str(getattr(group, "group_id", "")) or None,
                "groupRevision": None if group is None else getattr(group, "revision", None),
                "runId": None if run_id is None else str(run_id),
                "lastSequence": sequence - 1 if type(sequence) is int and sequence > 0 else None,
                "bindingEpoch": self._binding_epoch,
                "subscriberDrops": drop_total("subscriber_drops_total"),
                "historyDrops": drop_total("history_drops_total"),
                "deadlineDrops": drop_total("deadline_drops_total"),
                "serviceDrops": self._service_drops_total,
            },
            "probeConnected": observation is not None,
            "samplingActive": state in {"RUNNING", "PAUSED"},
        }

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
        if (
            paths is None
            or config is None
            or groups is None
            or history is None
            or exporter is None
            or self._cleanup_task is not None
        ):
            return failure(operation, "MONITOR_SERVICE_UNAVAILABLE", "Monitor runtime is not started")
        try:
            if operation == "monitor.status":
                _exact(payload, set())
                return success(operation, self._status(paths, config))
            if operation == "monitor.probes.list":
                _exact(payload, set())
                return await self._list_probes(operation, config, failure, success)
            if operation == "monitor.groups.list":
                _exact(payload, set())
                group_query = {} if query is None else query
                if set(group_query) - {"cursor", "limit"}:
                    raise ValueError("group query is invalid")
                group_limit = int(group_query.get("limit", "16"))
                if not 1 <= group_limit <= 16:
                    raise ValueError("group query is invalid")
                return groups.list_group_page(
                    cursor=group_query.get("cursor"),
                    limit=group_limit,
                )
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
                if self._probe_lifecycle_lock.locked():
                    return failure(
                        operation,
                        "MONITOR_PROBE_BUSY",
                        "A probe lifecycle transition is already in progress",
                    )
                async with self._probe_lifecycle_lock:
                    if not initial_connect:
                        release_error = await self._release_probe()
                        if release_error is not None:
                            if not isinstance(release_error, Exception):
                                raise release_error
                            return failure(
                                operation,
                                "MONITOR_CLEANUP_FAILED",
                                "Monitor probe cleanup failed",
                            )
                    result = await self._connect_probe(
                        operation, config, request, ProtocolResult, failure, success
                    )
                    if initial_connect and result.ok:
                        self._probe_request = request
                    return result
            if operation in {"monitor.catalog.variables", "monitor.catalog.registers"}:
                from stm32_toolkit.debug.types import (
                    CatalogPage,
                    RegisterDescriptor,
                    VariableDescriptor,
                )

                _exact(payload, set())
                allowed = {"query", "cursor", "limit"}
                if query is None or set(query) - allowed:
                    raise ValueError("catalog query is invalid")
                text_query = query.get("query", "")
                cursor = query.get("cursor")
                limit = int(query.get("limit", "100"))
                observation = self._observation
                if observation is None:
                    return failure(operation, "MONITOR_REQUEST_INVALID", "A probe must be connected")
                method_name = "list_variables" if operation.endswith("variables") else "list_registers"
                result = await _call(getattr(observation, method_name), text_query, cursor, limit)
                if getattr(result, "ok", None) is not True:
                    raw_code = getattr(result, "code", None)
                    code = (
                        "MONITOR_REQUEST_INVALID"
                        if isinstance(raw_code, str)
                        and raw_code.endswith(("QUERY_INVALID", "CURSOR_INVALID", "LIMIT_INVALID"))
                        else "MONITOR_PROVENANCE_CHANGED"
                    )
                    message = getattr(result, "message", "Monitor catalog request failed")
                    return failure(operation, code, message)
                data = getattr(result, "data", None)
                descriptor_type = (
                    VariableDescriptor
                    if operation.endswith("variables")
                    else RegisterDescriptor
                )
                if type(data) is not CatalogPage or any(
                    type(item) is not descriptor_type for item in data.items
                ):
                    return failure(
                        operation,
                        "MONITOR_PROVENANCE_CHANGED",
                        "Monitor catalog response is invalid",
                    )
                return success(operation, data.to_dict())
            if operation == "monitor.probe.release":
                _exact(payload, set())
                if self._probe_lifecycle_lock.locked():
                    return failure(
                        operation,
                        "MONITOR_PROBE_BUSY",
                        "A probe lifecycle transition is already in progress",
                    )
                async with self._probe_lifecycle_lock:
                    release_error = await self._release_probe()
                    if release_error is not None:
                        if not isinstance(release_error, Exception):
                            raise release_error
                        return failure(
                            operation,
                            "MONITOR_CLEANUP_FAILED",
                            "Monitor probe cleanup failed",
                        )
                    return success(operation, {"released": True})
            if operation == "monitor.sampling.start":
                _exact(payload, {"groupId", "expectedRevision"})
                if self._probe_lifecycle_lock.locked():
                    return failure(
                        operation,
                        "MONITOR_PROBE_BUSY",
                        "A probe lifecycle transition is already in progress",
                    )
                async with self._probe_lifecycle_lock:
                    sampler = self._sampler
                    if sampler is None:
                        return failure(operation, "MONITOR_REQUEST_INVALID", "A probe must be connected")
                    if self._sample_task is None or self._sample_task.done():
                        self._sample_task = asyncio.create_task(
                            self._forward_samples(sampler),
                            name="stm32-monitor-live-samples",
                        )
                    result = await _call(
                        sampler.start,
                        _uuid(payload["groupId"]),
                        expected_revision=_integer(payload["expectedRevision"]),
                    )
                    if getattr(result, "ok", False) and not hasattr(sampler, "set_state_listener"):
                        self._publish_state()
                    return result
            if operation in {
                "monitor.sampling.pause",
                "monitor.sampling.resume",
                "monitor.sampling.stop",
            }:
                _exact(payload, set())
                if self._probe_lifecycle_lock.locked():
                    return failure(
                        operation,
                        "MONITOR_PROBE_BUSY",
                        "A probe lifecycle transition is already in progress",
                    )
                async with self._probe_lifecycle_lock:
                    sampler = self._sampler
                    if sampler is None:
                        return failure(operation, "MONITOR_REQUEST_INVALID", "A probe must be connected")
                    action = operation.rsplit(".", 1)[1]
                    result = await _call(getattr(sampler, action))
                    if getattr(result, "ok", False) and not hasattr(sampler, "set_state_listener"):
                        self._publish_state()
                    return result
            if operation == "monitor.history.query":
                _exact(payload, set())
                expected = {"startNs", "endNs"}
                allowed = expected | {
                    "limit",
                    "cursor",
                    "runId",
                    "groupId",
                    "selectorKind",
                    "selector",
                }
                if query is None or set(query) - allowed or not expected.issubset(query):
                    raise ValueError("history query is invalid")
                if ("selectorKind" in query) != ("selector" in query):
                    raise ValueError("history selector query is invalid")
                history_query = HistoryQuery(
                    paths.session_id,
                    int(query["startNs"]),
                    int(query["endNs"]),
                    limit=int(query.get("limit", "10000")),
                    cursor=query.get("cursor"),
                    run_id=_uuid(query["runId"]) if "runId" in query else None,
                    group_id=_uuid(query["groupId"]) if "groupId" in query else None,
                    selector_kind=query.get("selectorKind"),
                    selector=query.get("selector"),
                )
                return history.query_history(history_query)
            if operation == "monitor.exports.create":
                _exact(payload, {"startNs", "endNs", "format", "authorized"})
                request = ExportRequest(
                    paths.session_id,
                    _integer(payload["startNs"]),
                    _integer(payload["endNs"]),
                    payload["format"],
                )
                return exporter.create_export(request, authorized=payload["authorized"])
            if operation == "monitor.exports.get":
                _exact(payload, set())
                return exporter.get_export(_uuid(resource_id))
            if operation == "monitor.exports.download":
                _exact(payload, set())
                return exporter.open_download(_uuid(resource_id))
        except (AttributeError, TypeError, ValueError):
            return failure(operation, "MONITOR_REQUEST_INVALID", "Monitor request is invalid")
        return failure(operation, "MONITOR_REQUEST_INVALID", "Monitor operation is unsupported")

    async def _connect_probe(self, operation, config, request, result_type, failure, success):
        from stm32_toolkit.monitor_observation import MonitorObservationRequest

        if self._observation is not None:
            return failure(operation, "MONITOR_PROBE_BUSY", "A probe is already connected")
        listed = await self._list_probes(operation, config, failure, success)
        if not listed.ok:
            return listed
        probes = listed.data.get("probes", []) if isinstance(listed.data, Mapping) else []
        if request.probe_id not in {item.get("probeId") for item in probes}:
            return failure(operation, "MONITOR_REQUEST_INVALID", "Probe ID is not currently discovered")
        firmware = self._current_firmware()
        if firmware is None:
            return failure(
                operation,
                "MONITOR_FIRMWARE_CHANGED",
                "Current debug firmware evidence is unavailable",
            )
        observation_request = MonitorObservationRequest(
            config.project_root,
            config.data_root,
            config.session_id,
            request.probe_id,
            firmware.build_id,
            firmware.elf_sha256,
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
        self._binding_epoch += 1
        listener = getattr(sampler, "set_state_listener", None)
        if callable(listener):
            listener(self._sampler_state_changed)
        self._publish_state()
        binding = getattr(observation, "binding", None)
        return success(operation, binding.to_dict() if hasattr(binding, "to_dict") else {"connected": True})

    async def _release_probe(self) -> BaseException | None:
        sampler, observation = self._sampler, self._observation
        sample_task = self._sample_task
        self._sample_task = None
        if sample_task is not None:
            sample_task.cancel()
            await asyncio.gather(sample_task, return_exceptions=True)
        self._sampler = None
        self._observation = None
        if sampler is not None or observation is not None:
            self._publish_state()
        return await _close_independent((sampler, observation))

    async def live_subscribe(
        self, *, after_event_id: int | None = None
    ) -> AsyncIterator[dict[str, object]]:
        from .models import LiveEvent

        if after_event_id is not None and (
            type(after_event_id) is not int or after_event_id < 1
        ):
            raise ValueError("after event ID is invalid")
        if self._paths is None:
            return
        if after_event_id is None:
            initial = self._bootstrap_events(gap=False)
        else:
            retained = tuple(self._events)
            if any(
                isinstance(event, LiveEvent) and event.event_id == after_event_id
                for event in retained
            ):
                initial = tuple(
                    event.to_dict()
                    for event in retained
                    if isinstance(event, LiveEvent) and event.event_id > after_event_id
                )
            else:
                anchor = next(
                    (
                        (sequence, pending)
                        for event_id, sequence, pending in self._private_anchors
                        if event_id == after_event_id
                    ),
                    None,
                )
                oldest = self._public_sequence - len(retained) + 1
                if anchor is not None and anchor[0] >= oldest - 1:
                    sequence, pending = anchor
                    start = max(0, sequence - oldest + 1)
                    initial = tuple(
                        event.to_dict()
                        for event in pending
                        if isinstance(event, LiveEvent)
                    ) + tuple(
                        event.to_dict()
                        for event in retained[start:]
                        if isinstance(event, LiveEvent)
                    )
                else:
                    initial = self._bootstrap_events(gap=True)
        queue: asyncio.Queue[object] = asyncio.Queue(maxsize=_LIVE_QUEUE_EVENTS)
        self._live_subscribers.add(queue)
        try:
            for event in initial:
                yield event
            while True:
                event = await queue.get()
                if event is _LIVE_END:
                    return
                if isinstance(event, LiveEvent):
                    yield event.to_dict()
        finally:
            self._live_subscribers.discard(queue)

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
        async with self._probe_lifecycle_lock:
            pass
        for task in (self._heartbeat_task, self._sample_task):
            if task is not None:
                task.cancel()
        await asyncio.gather(
            *(task for task in (self._heartbeat_task, self._sample_task) if task is not None),
            return_exceptions=True,
        )
        self._heartbeat_task = None
        self._sample_task = None
        for queue in tuple(self._live_subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(_LIVE_END)
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
        self._private_anchors.clear()
        self._closed.set()
        if first_error is not None:
            raise _fail("MONITOR_CLEANUP_FAILED", "Monitor runtime cleanup failed") from None


__all__ = ["MonitorRuntime", "MonitorRuntimeError"]
