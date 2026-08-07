"""Authenticated loopback Probe Service owning one backend and one lease."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import stat
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable
from uuid import uuid4

from aiohttp import web

from stm32_toolkit import __version__

from .backend import ProbeBackend, ProbeBackendError
from .lease import ProbeLease, ProbeLeaseManager
from .model import OperationLevel, ProbeRequest, ProbeResponse
from .protocol import (
    MAX_REQUEST_BYTES,
    PROBE_PROTOCOL_VERSION,
    ProbeProtocolError,
    decode_request,
    encode_response,
)

_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


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
        }


def _write_endpoint(path: Path, endpoint: ProbeEndpoint) -> None:
    payload = json.dumps(
        endpoint.to_record(), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    descriptor = -1
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = -1
            handle.write(payload)
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
        raise


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
        token_factory: Callable[[], bytes] = lambda: secrets.token_bytes(32),
        heartbeat_interval_seconds: float = 5.0,
        body_read_timeout_seconds: float = 2.0,
    ) -> None:
        self._backend = backend
        self._lease_manager = lease_manager
        self._probe_id = probe_id
        self._workspace_id = workspace_id
        self._session_id = session_id
        self._operation_level = operation_level
        self._session_root = session_root
        self._token_factory = token_factory
        if heartbeat_interval_seconds <= 0 or heartbeat_interval_seconds > 60:
            raise ValueError("Probe Service heartbeat interval is invalid")
        if body_read_timeout_seconds <= 0 or body_read_timeout_seconds > 30:
            raise ValueError("Probe Service body read timeout is invalid")
        self._heartbeat_interval_seconds = heartbeat_interval_seconds
        self._body_read_timeout_seconds = body_read_timeout_seconds
        self._runner: web.AppRunner | None = None
        self._lease: ProbeLease | None = None
        self._endpoint: ProbeEndpoint | None = None
        self._backend_tasks: set[asyncio.Task[object]] = set()
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
        _ensure_safe_session_root(
            self._lease_manager.data_root, self._session_root
        )
        token_bytes = self._token_factory()
        if not isinstance(token_bytes, bytes) or len(token_bytes) != 32:
            raise ValueError("Probe Service token factory must return 32 bytes")
        token = token_bytes.hex()

        application = web.Application(client_max_size=MAX_REQUEST_BYTES + 1)
        application.router.add_get("/health", self._handle_health)
        application.router.add_post("/v1/request", self._handle_request)
        runner = web.AppRunner(application, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, host="127.0.0.1", port=0)
        await site.start()
        addresses = runner.addresses
        if len(addresses) != 1:
            await runner.cleanup()
            raise RuntimeError("Probe Service did not bind exactly one endpoint")
        host, port = addresses[0][:2]
        lease: ProbeLease | None = None
        try:
            lease = self._lease_manager.acquire(
                probe_id=self._probe_id,
                workspace_id=self._workspace_id,
                session_id=self._session_id,
                operation_level=self._operation_level,
                health_url=f"http://127.0.0.1:{port}/health",
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
                record_path=record_path,
            )
            _write_endpoint(record_path, endpoint)
        except Exception:
            if lease is not None:
                lease.release()
            await runner.cleanup()
            raise
        self._runner = runner
        self._lease = lease
        self._endpoint = endpoint
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
                await asyncio.to_thread(lease.heartbeat)
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
                self._backend.open_attach(
                    str(request.data.get("probeId", "")),
                    str(request.data.get("target", "")),
                    halt_on_connect=False,
                )
                return {"attached": True}
            if request.operation == "memory.read":
                data = self._backend.read_memory(
                    int(request.data["address"]), int(request.data["length"])
                )
                return {"bytes": data.hex()}
            if request.operation == "register.read":
                names = tuple(str(item) for item in request.data["names"])
                return {"values": dict(self._backend.read_core_registers(names))}
            if request.operation == "probe.close":
                self._backend.close()
                return {"closed": True}
            raise ProbeBackendError("PROBE_OPERATION_UNSUPPORTED", "Operation is unsupported")

        entered_backend = asyncio.Event()

        async def invoke_serialized() -> object:
            async with self._backend_lock:
                entered_backend.set()
                return await asyncio.to_thread(invoke)

        task = asyncio.create_task(invoke_serialized())
        self._backend_tasks.add(task)
        task.add_done_callback(self._backend_task_finished)
        try:
            return await asyncio.wait_for(
                asyncio.shield(task), timeout=request.timeout_ms / 1000
            )
        except (asyncio.TimeoutError, asyncio.CancelledError):
            if not entered_backend.is_set():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            raise

    def _backend_task_finished(self, task: asyncio.Task[object]) -> None:
        self._backend_tasks.discard(task)
        if not task.cancelled():
            task.exception()

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
        async with self._stop_lock:
            if self._runner is None and self._lease is None:
                return
            self._stopping = True
            heartbeat, self._heartbeat_task = self._heartbeat_task, None
            current_task = asyncio.current_task()
            if heartbeat is not None and heartbeat is not current_task:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)
            backend_close_error: Exception | None = None
            try:
                await asyncio.to_thread(self._backend.close)
            except Exception as error:
                backend_close_error = error
            runner, self._runner = self._runner, None
            if runner is not None:
                await runner.cleanup()
            if self._backend_tasks:
                await asyncio.gather(*tuple(self._backend_tasks), return_exceptions=True)
            endpoint = self._endpoint
            if endpoint is not None:
                try:
                    current = json.loads(endpoint.record_path.read_text(encoding="utf-8"))
                    if current.get("leaseId") == endpoint.lease_id:
                        endpoint.record_path.unlink()
                except (FileNotFoundError, OSError, json.JSONDecodeError):
                    pass
            lease, self._lease = self._lease, None
            if lease is not None:
                lease.release()
            self._endpoint = None
            if backend_close_error is not None:
                raise backend_close_error
