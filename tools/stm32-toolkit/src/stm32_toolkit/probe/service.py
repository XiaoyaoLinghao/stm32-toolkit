"""Authenticated loopback Probe Service owning one backend and one lease."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import stat
from collections.abc import Coroutine
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable
from uuid import uuid4

from aiohttp import web

from stm32_toolkit import __version__

from .backend import ProbeBackend, ProbeBackendError
from .lease import ProbeLease, ProbeLeaseManager, _RuntimeRootAuthority
from .model import OperationLevel, ProbeRequest, ProbeResponse
from .protocol import (
    MAX_REQUEST_BYTES,
    PROBE_PROTOCOL_VERSION,
    ProbeProtocolError,
    decode_request,
    encode_response,
)

_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


async def _await_task_completion(task: asyncio.Task[object]) -> object:
    """Finish an owned task before propagating caller cancellation."""
    cancellation: asyncio.CancelledError | None = None
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError as error:
            if cancellation is None:
                cancellation = error
        except BaseException:
            break
    result = task.result()
    if cancellation is not None:
        raise cancellation
    return result


async def _await_commit_completion(task: asyncio.Task[object]) -> object:
    """Finish a commit task; success wins over late caller cancellation."""
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
        except BaseException:
            break
    return task.result()


class ProbeServiceError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ProbeEndpoint:
    protocol: str
    toolkit_version: str
    host: str
    port: int
    token: str = field(repr=False)
    workspace_id: str = ""
    session_id: str = ""
    lease_id: str = ""
    probe_id: str = ""
    operation_level: OperationLevel = OperationLevel.OBSERVE
    record_path: Path = field(default=Path(), repr=False, compare=False)

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def with_token(self, token: str) -> "ProbeEndpoint":
        return replace(self, token=token)

    def with_workspace(self, workspace_id: str) -> "ProbeEndpoint":
        return replace(self, workspace_id=workspace_id)

    def with_toolkit_version(self, toolkit_version: str) -> "ProbeEndpoint":
        return replace(self, toolkit_version=toolkit_version)

    def to_record(self) -> dict[str, object]:
        return {
            "protocol": self.protocol,
            "toolkitVersion": self.toolkit_version,
            "url": self.url,
            "token": self.token,
            "workspaceId": self.workspace_id,
            "sessionId": self.session_id,
            "leaseId": self.lease_id,
            "probeId": self.probe_id,
            "operationLevel": self.operation_level.value,
        }


def _write_endpoint(
    path: Path,
    endpoint: ProbeEndpoint,
    *,
    directory_descriptor: int | None = None,
) -> None:
    payload = json.dumps(
        endpoint.to_record(), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    descriptor = -1
    try:
        if directory_descriptor is None:
            descriptor = os.open(
                temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
        else:
            descriptor = os.open(
                temporary.name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=directory_descriptor,
            )
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if directory_descriptor is None:
            os.replace(temporary, path)
        else:
            os.replace(
                temporary.name,
                path.name,
                src_dir_fd=directory_descriptor,
                dst_dir_fd=directory_descriptor,
            )
        if os.name != "nt":
            if directory_descriptor is None:
                os.chmod(path, 0o600)
            else:
                os.chmod(path.name, 0o600, dir_fd=directory_descriptor)
    except OSError:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            if directory_descriptor is None:
                temporary.unlink()
            else:
                os.unlink(temporary.name, dir_fd=directory_descriptor)
        except OSError:
            pass
        raise


def _read_endpoint_record(
    path: Path, *, directory_descriptor: int | None = None
) -> dict[str, object]:
    if directory_descriptor is None:
        return json.loads(path.read_text(encoding="utf-8"))
    descriptor = os.open(path.name, os.O_RDONLY, dir_fd=directory_descriptor)
    with os.fdopen(descriptor, "rb") as handle:
        raw = handle.read(16_385)
    if len(raw) > 16_384:
        raise ValueError
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError
    return value


def _unlink_endpoint(
    path: Path, *, directory_descriptor: int | None = None
) -> None:
    if directory_descriptor is None:
        path.unlink()
    else:
        os.unlink(path.name, dir_fd=directory_descriptor)


async def _read_bounded_request_body(request: web.Request) -> bytes:
    if request.content_length is not None and request.content_length > MAX_REQUEST_BYTES:
        raise ProbeProtocolError(
            "PROBE_REQUEST_TOO_LARGE",
            "Probe request exceeds the body limit",
            {"limit": MAX_REQUEST_BYTES},
        )
    body = bytearray()
    while True:
        remaining = MAX_REQUEST_BYTES + 1 - len(body)
        if remaining <= 0:
            raise ProbeProtocolError(
                "PROBE_REQUEST_TOO_LARGE",
                "Probe request exceeds the body limit",
                {"limit": MAX_REQUEST_BYTES},
            )
        chunk = await request.content.read(min(65_536, remaining))
        if not chunk:
            return bytes(body)
        body.extend(chunk)
        if len(body) > MAX_REQUEST_BYTES:
            raise ProbeProtocolError(
                "PROBE_REQUEST_TOO_LARGE",
                "Probe request exceeds the body limit",
                {"limit": MAX_REQUEST_BYTES},
            )


def _ensure_safe_session_root(data_root: Path, session_root: Path) -> None:
    lexical_data = data_root.expanduser().absolute()
    lexical_session = session_root.expanduser().absolute()
    try:
        relative = lexical_session.relative_to(lexical_data)
    except ValueError as error:
        raise ProbeServiceError(
            "PROBE_SESSION_UNSAFE", "Probe session path is outside plugin data"
        ) from error

    for ancestor in reversed((lexical_data, *lexical_data.parents)):
        try:
            metadata = os.lstat(ancestor)
        except FileNotFoundError:
            continue
        except OSError as error:
            raise ProbeServiceError(
                "PROBE_SESSION_UNAVAILABLE", "Probe session path is unavailable"
            ) from error
        if (
            ancestor.is_symlink()
            or getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT
            or not stat.S_ISDIR(metadata.st_mode)
        ):
            raise ProbeServiceError(
                "PROBE_SESSION_UNSAFE", "Probe session path contains a redirect"
            )

    current = lexical_data
    for component in (None, *relative.parts):
        if component is not None:
            current /= component
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            try:
                current.mkdir()
                metadata = os.lstat(current)
            except OSError as error:
                raise ProbeServiceError(
                    "PROBE_SESSION_UNAVAILABLE", "Probe session path is unavailable"
                ) from error
        except OSError as error:
            raise ProbeServiceError(
                "PROBE_SESSION_UNAVAILABLE", "Probe session path is unavailable"
            ) from error
        if (
            current.is_symlink()
            or getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT
            or not stat.S_ISDIR(metadata.st_mode)
        ):
            raise ProbeServiceError(
                "PROBE_SESSION_UNSAFE", "Probe session path contains a redirect"
            )
    try:
        lexical_session.resolve(strict=True).relative_to(
            lexical_data.resolve(strict=True)
        )
    except (OSError, ValueError) as error:
        raise ProbeServiceError(
            "PROBE_SESSION_UNSAFE", "Probe session path is outside plugin data"
        ) from error


class ProbeService:
    def __init__(
        self,
        *,
        backend: ProbeBackend,
        lease_manager: ProbeLeaseManager,
        probe_id: str,
        workspace_id: str,
        session_id: str,
        operation_level: OperationLevel,
        session_root: Path,
        project_root: Path | None = None,
        token_factory: Callable[[], bytes] = lambda: secrets.token_bytes(32),
        heartbeat_interval_seconds: float = 5.0,
        body_read_timeout_seconds: float = 2.0,
        handoff_ticket: str | None = None,
        _runtime_root_authority: _RuntimeRootAuthority | None = None,
    ) -> None:
        self._backend = backend
        self._lease_manager = lease_manager
        self._probe_id = probe_id
        self._workspace_id = workspace_id
        self._session_id = session_id
        self._operation_level = operation_level
        self._session_root = session_root
        self._project_root = project_root
        self._token_factory = token_factory
        if heartbeat_interval_seconds <= 0 or heartbeat_interval_seconds > 60:
            raise ValueError("Probe Service heartbeat interval is invalid")
        if body_read_timeout_seconds <= 0 or body_read_timeout_seconds > 30:
            raise ValueError("Probe Service body read timeout is invalid")
        self._heartbeat_interval_seconds = heartbeat_interval_seconds
        self._body_read_timeout_seconds = body_read_timeout_seconds
        self._handoff_ticket = handoff_ticket
        self._runtime_root_authority = _runtime_root_authority
        self._session_directory_descriptor: int | None = None
        self._runner: web.AppRunner | None = None
        self._lease: ProbeLease | None = None
        self._endpoint: ProbeEndpoint | None = None
        self._backend_tasks: set[asyncio.Task[object]] = set()
        self._backend_modify_tasks: set[asyncio.Task[object]] = set()
        self._modifications_draining = False
        self._backend_lock = asyncio.Lock()
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._stop_lock = asyncio.Lock()
        self._stopping = False

    @property
    def endpoint(self) -> ProbeEndpoint | None:
        return self._endpoint

    async def start(self) -> ProbeEndpoint:
        if self._endpoint is not None:
            return self._endpoint
        session_directory_descriptor = (
            None
            if self._runtime_root_authority is None
            else self._runtime_root_authority.directory_descriptor(
                self._session_root
            )
        )
        if session_directory_descriptor is None:
            _ensure_safe_session_root(
                self._lease_manager.data_root, self._session_root
            )
        else:
            metadata = os.fstat(session_directory_descriptor)
            if not stat.S_ISDIR(metadata.st_mode):
                raise ProbeServiceError(
                    "PROBE_SESSION_UNSAFE", "Probe session path is not a directory"
                )
        token_bytes = self._token_factory()
        if not isinstance(token_bytes, bytes) or len(token_bytes) != 32:
            raise ValueError("Probe Service token factory must return 32 bytes")
        token = token_bytes.hex()

        application = web.Application(client_max_size=MAX_REQUEST_BYTES + 1)
        application.router.add_get("/health", self._handle_health)
        application.router.add_post("/v1/request", self._handle_request)
        runner = web.AppRunner(application, access_log=None)
        lease: ProbeLease | None = None
        endpoint: ProbeEndpoint | None = None
        try:
            await runner.setup()
            site = web.TCPSite(runner, host="127.0.0.1", port=0)
            await site.start()
            addresses = runner.addresses
            if len(addresses) != 1:
                raise RuntimeError("Probe Service did not bind exactly one endpoint")
            host, port = addresses[0][:2]
            lease = self._lease_manager.acquire(
                probe_id=self._probe_id,
                workspace_id=self._workspace_id,
                session_id=self._session_id,
                operation_level=self._operation_level,
                health_url=f"http://127.0.0.1:{port}/health",
                handoff_ticket=self._handoff_ticket,
                _runtime_root_authority=self._runtime_root_authority,
            )
            record_path = self._session_root / "probe-endpoint.json"
            endpoint = ProbeEndpoint(
                protocol=PROBE_PROTOCOL_VERSION,
                toolkit_version=__version__,
                host=str(host),
                port=int(port),
                token=token,
                workspace_id=self._workspace_id,
                session_id=self._session_id,
                lease_id=lease.lease_id,
                probe_id=self._probe_id,
                operation_level=self._operation_level,
                record_path=record_path,
            )
            if session_directory_descriptor is None:
                _write_endpoint(record_path, endpoint)
            else:
                _write_endpoint(
                    record_path,
                    endpoint,
                    directory_descriptor=session_directory_descriptor,
                )
        except BaseException:
            async def rollback_start() -> None:
                try:
                    await runner.cleanup()
                finally:
                    if endpoint is not None:
                        try:
                            if session_directory_descriptor is None:
                                _unlink_endpoint(endpoint.record_path)
                            else:
                                _unlink_endpoint(
                                    endpoint.record_path,
                                    directory_descriptor=session_directory_descriptor,
                                )
                        except (FileNotFoundError, OSError):
                            pass
                    if lease is not None:
                        try:
                            lease.release()
                        except Exception:
                            pass

            rollback = asyncio.create_task(rollback_start())
            try:
                await _await_task_completion(rollback)
            except BaseException:
                pass
            raise
        assert endpoint is not None
        assert lease is not None
        self._stopping = False
        self._modifications_draining = False
        self._runner = runner
        self._lease = lease
        self._endpoint = endpoint
        self._session_directory_descriptor = session_directory_descriptor
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(), name="stm32-toolkit-probe-heartbeat"
        )
        return endpoint

    async def _heartbeat_loop(self) -> None:
        try:
            while not self._stopping:
                await asyncio.sleep(self._heartbeat_interval_seconds)
                lease = self._lease
                if lease is None or self._stopping:
                    return
                heartbeat = asyncio.create_task(asyncio.to_thread(lease.heartbeat))
                await _await_task_completion(heartbeat)
        except asyncio.CancelledError:
            raise
        except Exception:
            self._stopping = True
            await self.stop()

    def _failure(
        self,
        code: str,
        message: str,
        *,
        request_id: str = "request-invalid",
        operation: str = "probe.request",
        details: dict[str, object] | None = None,
        status: int = 400,
    ) -> web.Response:
        response = ProbeResponse.failure(request_id, operation, code, message, details)
        return web.Response(
            body=encode_response(response),
            status=status,
            content_type="application/json",
        )

    def _request_access_failure(self, request: web.Request) -> web.Response | None:
        endpoint = self._endpoint
        if endpoint is None or self._stopping:
            return self._failure(
                "PROBE_SERVICE_UNAVAILABLE", "Probe Service is unavailable", status=503
            )
        if request.remote != "127.0.0.1":
            return self._failure(
                "PROBE_PEER_REJECTED", "Probe Service accepts loopback peers only", status=403
            )
        if request.host != f"127.0.0.1:{endpoint.port}":
            return self._failure(
                "PROBE_HOST_REJECTED", "Probe Service Host is invalid", status=403
            )
        origin = request.headers.get("Origin")
        if origin is not None and origin != endpoint.url:
            return self._failure(
                "PROBE_ORIGIN_REJECTED", "Probe Service Origin is invalid", status=403
            )
        supplied = request.headers.get("Authorization", "")
        expected = f"Bearer {endpoint.token}"
        if not secrets.compare_digest(supplied, expected):
            return self._failure(
                "PROBE_AUTH_REQUIRED", "Probe Service authentication failed", status=401
            )
        if request.content_type != "application/json":
            return self._failure(
                "PROBE_CONTENT_TYPE_REQUIRED",
                "Probe Service requires application/json",
                status=415,
            )
        return None

    async def _handle_health(self, request: web.Request) -> web.Response:
        endpoint = self._endpoint
        if (
            endpoint is None
            or request.remote != "127.0.0.1"
            or request.headers.get("X-Probe-Lease") != endpoint.lease_id
        ):
            return web.json_response({"ok": False}, status=403)
        return web.json_response(
            {
                "ok": True,
                "protocol": PROBE_PROTOCOL_VERSION,
                "toolkitVersion": __version__,
                "leaseId": endpoint.lease_id,
            }
        )

    async def _run_backend(self, request: ProbeRequest) -> object:
        def invoke() -> object:
            if request.operation == "probe.list":
                return {"probes": [item.to_dict() for item in self._backend.list_probes()]}
            if request.operation == "probe.attach":
                evidence = self._backend.open_attach(
                    str(request.data.get("probeId", "")),
                    str(request.data.get("target", "")),
                    halt_on_connect=False,
                )
                return evidence.to_dict()
            if request.operation == "memory.read":
                data = self._backend.read_memory(
                    int(request.data["address"]), int(request.data["length"])
                )
                return {"bytes": data.hex()}
            if request.operation == "register.read":
                names = tuple(str(item) for item in request.data["names"])
                return {"values": dict(self._backend.read_core_registers(names))}
            if request.operation == "flash.program":
                image = self._read_verified_elf(
                    request.data["elfPath"],
                    request.data["elfSha256"],
                    request.data["elfSize"],
                )
                return self._backend.flash_elf(image).to_dict()
            raise ProbeBackendError("PROBE_OPERATION_UNSUPPORTED", "Operation is unsupported")

        is_modify = request.operation == "flash.program"
        if is_modify and self._modifications_draining:
            raise ProbeBackendError(
                "PROBE_MODIFICATIONS_DRAINING",
                "Probe Service is draining modification operations",
            )

        entered_backend = asyncio.Event()

        async def invoke_serialized() -> object:
            async with self._backend_lock:
                entered_backend.set()
                return await asyncio.to_thread(invoke)

        task = asyncio.create_task(invoke_serialized())
        self._backend_tasks.add(task)
        if is_modify:
            self._backend_modify_tasks.add(task)
        task.add_done_callback(self._backend_task_finished)
        try:
            return await asyncio.wait_for(
                asyncio.shield(task), timeout=request.timeout_ms / 1000
            )
        except (asyncio.TimeoutError, asyncio.CancelledError):
            if not entered_backend.is_set():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            elif is_modify and not task.cancelled():
                return await asyncio.shield(task)
            raise

    def drain_modifications(self) -> Coroutine[object, object, None]:
        self._modifications_draining = True

        async def wait_for_registered_modifications() -> None:
            tasks = tuple(self._backend_modify_tasks)
            if tasks:
                await asyncio.gather(
                    *(asyncio.shield(task) for task in tasks),
                    return_exceptions=True,
                )

        return wait_for_registered_modifications()

    async def reserve_external_handoff(self, ticket: str) -> None:
        lease = self._lease
        if lease is None or self._endpoint is None or self._stopping:
            raise ProbeServiceError(
                "PROBE_SERVICE_UNAVAILABLE", "Probe Service is unavailable"
            )
        reservation = asyncio.create_task(
            asyncio.to_thread(lease.reserve_external_handoff, ticket)
        )
        await _await_task_completion(reservation)

    async def consume_external_handoff(self, ticket: str) -> None:
        lease = self._lease
        if lease is None or self._endpoint is None or self._stopping:
            raise ProbeServiceError(
                "PROBE_SERVICE_UNAVAILABLE", "Probe Service is unavailable"
            )
        consumption = asyncio.create_task(
            asyncio.to_thread(lease.consume_external_handoff, ticket)
        )
        await _await_commit_completion(consumption)

    def _backend_task_finished(self, task: asyncio.Task[object]) -> None:
        self._backend_tasks.discard(task)
        self._backend_modify_tasks.discard(task)
        if not task.cancelled():
            task.exception()

    def _read_verified_elf(
        self, relative_path: object, expected_sha256: object, expected_size: object
    ) -> bytes:
        if (
            not isinstance(relative_path, str)
            or not 5 <= len(relative_path) <= 1024
            or relative_path.startswith("/")
            or "\\" in relative_path
            or ":" in relative_path
            or any(ord(character) < 32 or ord(character) == 127 for character in relative_path)
            or not relative_path.endswith(".elf")
            or any(component in ("", ".", "..") for component in relative_path.split("/"))
            or not isinstance(expected_sha256, str)
            or len(expected_sha256) != 64
            or any(character not in "0123456789abcdef" for character in expected_sha256)
            or type(expected_size) is not int
            or not 1 <= expected_size <= 64 * 1024 * 1024
        ):
            raise ProbeBackendError(
                "FIRMWARE_PATH_INVALID", "Firmware evidence is invalid"
            )
        root = self._project_root
        if root is None:
            raise ProbeBackendError(
                "PROBE_PROJECT_ROOT_REQUIRED",
                "Probe Service requires an exact project root for programming",
            )
        try:
            lexical_root = root.expanduser().absolute()
            resolved_root = root.resolve(strict=True)
            if os.path.normcase(str(lexical_root)) != os.path.normcase(str(resolved_root)):
                raise ValueError("project root is not canonical")
            root_metadata = os.lstat(lexical_root)
            if (
                lexical_root.is_symlink()
                or getattr(root_metadata, "st_file_attributes", 0) & _REPARSE_POINT
                or not stat.S_ISDIR(root_metadata.st_mode)
            ):
                raise ValueError("project root is unsafe")

            parts = relative_path.split("/")
            current = lexical_root
            for index, component in enumerate(parts):
                current /= component
                metadata = os.lstat(current)
                if (
                    current.is_symlink()
                    or getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT
                ):
                    raise ValueError("firmware path contains a redirect")
                if index < len(parts) - 1 and not stat.S_ISDIR(metadata.st_mode):
                    raise ValueError("firmware parent is not a directory")
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("firmware is not a regular file")
            if current.resolve(strict=True).parent != resolved_root.joinpath(*parts).parent:
                raise ValueError("firmware path changed")
            if metadata.st_size != expected_size:
                raise ProbeBackendError(
                    "FIRMWARE_INPUT_CHANGED", "Firmware input changed before programming"
                )

            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
            descriptor = os.open(current, flags)
            try:
                opened = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or opened.st_size != expected_size
                    or (metadata.st_dev, metadata.st_ino)
                    != (opened.st_dev, opened.st_ino)
                ):
                    raise ProbeBackendError(
                        "FIRMWARE_INPUT_CHANGED",
                        "Firmware input changed before programming",
                    )
                chunks = bytearray()
                while len(chunks) <= expected_size:
                    chunk = os.read(descriptor, min(65_536, expected_size + 1 - len(chunks)))
                    if not chunk:
                        break
                    chunks.extend(chunk)
            finally:
                os.close(descriptor)
        except ProbeBackendError:
            raise
        except (OSError, ValueError):
            raise ProbeBackendError(
                "FIRMWARE_PATH_INVALID", "Firmware path is unavailable or unsafe"
            ) from None

        image = bytes(chunks)
        if (
            len(image) != expected_size
            or hashlib.sha256(image).hexdigest() != expected_sha256
        ):
            raise ProbeBackendError(
                "FIRMWARE_INPUT_CHANGED", "Firmware input changed before programming"
            )
        return image

    async def _handle_request(self, web_request: web.Request) -> web.Response:
        access_failure = self._request_access_failure(web_request)
        if access_failure is not None:
            return access_failure
        try:
            body = await asyncio.wait_for(
                _read_bounded_request_body(web_request),
                timeout=self._body_read_timeout_seconds,
            )
        except asyncio.TimeoutError:
            return self._failure(
                "PROBE_REQUEST_TIMEOUT",
                "Probe request body was not received before the deadline",
                status=408,
            )
        except ProbeProtocolError as error:
            return self._failure(
                error.code,
                error.message,
                details=error.details,
                status=413,
            )
        try:
            request = decode_request(body, __version__)
        except ProbeProtocolError as error:
            return self._failure(error.code, error.message, details=error.details)
        endpoint = self._endpoint
        assert endpoint is not None
        if (
            request.workspace_id != endpoint.workspace_id
            or request.session_id != endpoint.session_id
        ):
            return self._failure(
                "PROBE_SESSION_MISMATCH",
                "Probe request does not match the owning session",
                request_id=request.request_id,
                operation=request.operation,
            )
        if request.lease_id != endpoint.lease_id:
            return self._failure(
                "PROBE_LEASE_LOST",
                "Probe request lease is no longer active",
                request_id=request.request_id,
                operation=request.operation,
            )
        if not self._operation_level.allows(request.operation_level):
            return self._failure(
                "PROBE_OPERATION_LEVEL_DENIED",
                "Probe request exceeds the granted operation level",
                request_id=request.request_id,
                operation=request.operation,
            )
        required_level = (
            OperationLevel.MODIFY
            if request.operation == "flash.program"
            else OperationLevel.OBSERVE
        )
        if (
            request.operation_level is not required_level
            or not self._operation_level.allows(required_level)
        ):
            return self._failure(
                "PROBE_OPERATION_LEVEL_DENIED",
                "Probe operation does not match the required operation level",
                request_id=request.request_id,
                operation=request.operation,
            )
        try:
            data = await self._run_backend(request)
            response = ProbeResponse.success(request.request_id, request.operation, data)
        except asyncio.TimeoutError:
            response = ProbeResponse.failure(
                request.request_id,
                request.operation,
                "PROBE_TIMEOUT",
                "Probe backend operation timed out",
            )
        except ProbeBackendError as error:
            response = ProbeResponse.failure(
                request.request_id,
                request.operation,
                error.code,
                error.message,
                error.details,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            response = ProbeResponse.failure(
                request.request_id,
                request.operation,
                "PROBE_INTERNAL_ERROR",
                "Probe Service operation failed",
            )
        return web.Response(body=encode_response(response), content_type="application/json")

    async def stop(self) -> None:
        caller = asyncio.current_task()
        async with self._stop_lock:
            if self._runner is None and self._lease is None:
                return
            self._stopping = True
            stopping = asyncio.create_task(self._stop_owned_state(caller))
            await _await_task_completion(stopping)

    async def _stop_owned_state(
        self, caller: asyncio.Task[object] | None
    ) -> None:
        heartbeat = self._heartbeat_task
        runner = self._runner
        endpoint = self._endpoint
        lease = self._lease
        first_error: Exception | None = None

        if heartbeat is not None and heartbeat is not caller:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
        if runner is not None:
            try:
                await runner.cleanup()
            except Exception as error:
                if first_error is None:
                    first_error = error
        if self._backend_tasks:
            await asyncio.gather(*tuple(self._backend_tasks), return_exceptions=True)
        try:
            await asyncio.to_thread(self._backend.close)
        except Exception as error:
            if first_error is None:
                first_error = error
        if lease is not None:
            try:
                await asyncio.to_thread(lease.release)
            except Exception as error:
                if first_error is None:
                    first_error = error

        self._heartbeat_task = None
        self._runner = None
        self._lease = None
        self._endpoint = None
        if endpoint is not None:
            try:
                current = _read_endpoint_record(
                    endpoint.record_path,
                    directory_descriptor=self._session_directory_descriptor,
                )
                if current.get("leaseId") == endpoint.lease_id:
                    _unlink_endpoint(
                        endpoint.record_path,
                        directory_descriptor=self._session_directory_descriptor,
                    )
            except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
                pass
        self._session_directory_descriptor = None
        if first_error is not None:
            raise first_error
