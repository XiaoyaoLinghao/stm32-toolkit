"""Authenticated loopback Probe Service owning one backend and one lease."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import secrets
import stat
from collections.abc import Coroutine, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable
from uuid import uuid4

from aiohttp import web

from stm32_toolkit import __version__
from stm32_toolkit.testing.artifacts import TestArtifactCollector
from stm32_toolkit.probe.flash import _canonical_target, load_fresh_firmware_facts

from .backend import ProbeAttachmentEvidence, ProbeBackend, ProbeBackendError
from .authorization import ControlAuthorizationError, ControlAuthorizationStore
from .lease import ProbeLease, ProbeLeaseManager, _RuntimeRootAuthority
from .model import OperationLevel, ProbeRequest, ProbeResponse
from .protocol import (
    MAX_REQUEST_BYTES,
    PROBE_PROTOCOL_VERSION,
    TARGET_ERROR_CODES,
    ProbeProtocolError,
    decode_request,
    encode_response,
)

_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_TARGET_REGISTER = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_ATTACH_RECOVERY_SECONDS = 1.0


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


async def _await_task_ignoring_cancellation(task: asyncio.Task[object]) -> object:
    """Finish one owned cleanup task even when its caller is cancelled."""
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
    return task.result()


async def _await_attach_outcome(
    task: asyncio.Task[object],
) -> tuple[str, object | BaseException | None]:
    """Wait for attach completion against one absolute recovery deadline."""
    deadline = asyncio.get_running_loop().time() + _ATTACH_RECOVERY_SECONDS
    while not task.done():
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            return "timeout", None
        waiter = asyncio.create_task(
            asyncio.wait_for(asyncio.shield(task), timeout=remaining)
        )
        try:
            await asyncio.shield(waiter)
        except asyncio.CancelledError:
            try:
                await _await_task_ignoring_cancellation(waiter)
            except asyncio.TimeoutError:
                if not task.done():
                    return "timeout", None
            except BaseException:
                pass
        except asyncio.TimeoutError:
            if not task.done():
                return "timeout", None
        except BaseException:
            pass
        if not task.done():
            continue

    if task.cancelled():
        return "error", asyncio.CancelledError()
    try:
        return "success", task.result()
    except BaseException as error:
        return "error", error


async def _run_owned_backend_call(call: Callable[[], object]) -> object:
    """Run one backend recovery call to completion across caller cancellation."""
    task = asyncio.create_task(asyncio.to_thread(call))
    return await _await_task_ignoring_cancellation(task)


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
        control_authorizations: ControlAuthorizationStore | None = None,
        artifact_collector: TestArtifactCollector | None = None,
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
        if not isinstance(control_authorizations, ControlAuthorizationStore):
            raise TypeError("Probe Service requires one persistent control authorization store")
        self._control_authorizations = control_authorizations
        if artifact_collector is not None and not isinstance(
            artifact_collector, TestArtifactCollector
        ):
            raise TypeError("Probe Service artifact collector is invalid")
        self._artifact_collector = artifact_collector
        self._session_directory_descriptor: int | None = None
        self._runner: web.AppRunner | None = None
        self._lease: ProbeLease | None = None
        self._endpoint: ProbeEndpoint | None = None
        self._backend_tasks: set[asyncio.Task[object]] = set()
        self._backend_modify_tasks: set[asyncio.Task[object]] = set()
        self._modifications_draining = False
        self._backend_lock = asyncio.Lock()
        self._observation_attachment_lock = asyncio.Lock()
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._stop_lock = asyncio.Lock()
        self._stopping = False
        self._observation_attachment: tuple[
            str, str, ProbeAttachmentEvidence
        ] | None = None

    def _store_capture(
        self, data: bytes, *, prefix: str, name: str, kind: str, media_type: str
    ) -> dict[str, object]:
        collector = self._artifact_collector
        if not isinstance(collector, TestArtifactCollector):
            raise ProbeBackendError(
                "PROBE_BACKEND_ERROR", "Probe capture Evidence store is unavailable"
            )
        try:
            directory = collector.new_directory(prefix)
            artifact = collector.write_and_ingest(
                directory, name, data, kind=kind, media_type=media_type
            )
        except Exception as error:
            raise ProbeBackendError(
                "PROBE_BACKEND_ERROR", "Probe capture Evidence publication failed"
            ) from error
        return artifact.to_dict()

    @staticmethod
    def _closed_target_identity(value: object) -> dict[str, object]:
        identity = dict(value) if isinstance(value, Mapping) else {}
        if (
            set(identity) != {"board_id", "mcu", "target_id", "probe_serial_hash"}
            or any(not isinstance(identity[field], str) or not identity[field] for field in ("board_id", "mcu", "target_id"))
            or not isinstance(identity["probe_serial_hash"], str)
            or len(identity["probe_serial_hash"]) != 64
            or any(character not in "0123456789abcdef" for character in identity["probe_serial_hash"])
        ):
            raise ProbeBackendError("PROBE_BACKEND_ERROR", "Target identity output is invalid")
        return identity

    def _reused_observation_attachment(
        self, probe_id: str, target: str
    ) -> ProbeAttachmentEvidence | None:
        accepted = self._observation_attachment
        if self._operation_level is not OperationLevel.OBSERVE or accepted is None:
            return None
        accepted_probe, accepted_target, evidence = accepted
        if probe_id != accepted_probe or _canonical_target(target) != accepted_target:
            raise ProbeBackendError(
                "PROBE_IDENTITY_MISMATCH",
                "Connected target identity does not match",
            )
        return evidence

    def _effective_target_transport_config(
        self, transport: str, supplied: Mapping[str, object]
    ) -> dict[str, object]:
        """Rebuild runtime-only transport facts from the current Project v3."""
        root = self._project_root
        if root is None:
            return dict(supplied)
        facts = load_fresh_firmware_facts(root)
        model = facts.model
        target_config = getattr(getattr(model, "testing", None), "target", None)
        configured = getattr(target_config, "transport", None)
        kind = getattr(configured, "kind", None)
        options = getattr(configured, "options", None)
        names = {
            "memory-mailbox": "mailbox", "rtt": "rtt", "uart": "uart",
            "semihosting": "semihosting",
        }
        if names.get(kind) != transport:
            raise ProbeBackendError("PROBE_BACKEND_ERROR", "Target transport configuration changed")
        if kind == "memory-mailbox":
            project = {"kind": kind, "options": {"address": options.address, "size": options.size}}
        elif kind == "rtt":
            project_options = {"channel": options.channel}
            if options.control_block_address is not None:
                project_options["controlBlockAddress"] = options.control_block_address
            project = {"kind": kind, "options": project_options}
        elif kind == "uart":
            project = {"kind": kind, "options": {"port": options.port, "baud": options.baud}}
        else:
            project = {"kind": kind, "options": {}}
        if dict(supplied) != project:
            raise ProbeBackendError("PROBE_BACKEND_ERROR", "Target transport configuration changed")
        physical = self._closed_target_identity(self._backend.target_identity())
        common = {
            "target_id": facts.target_device,
            "probe_id": physical["probe_serial_hash"],
        }
        ram = [
            {"start": region.origin, "size": region.length}
            for region in model.memory.regions
            if "w" in region.attributes.casefold()
        ]
        if transport == "mailbox":
            return {**project["options"], "ram": ram, **common}
        if transport == "rtt":
            return {
                "channel": project["options"]["channel"],
                "control_block_address": project["options"].get("controlBlockAddress"),
                "ram": ram, **common,
            }
        if transport == "uart":
            return {**project["options"], "data_bits": 8, "parity": "N", "stop_bits": 1, **common}
        return {
            "elf_path": str(root.joinpath(*facts.elf_path.split("/")).resolve(strict=True)),
            "elf_sha256": facts.elf_sha256,
            "host_files": False,
            **common,
        }

    @staticmethod
    def _closed_target_state(value: object) -> dict[str, object]:
        state = dict(value) if isinstance(value, Mapping) else {}
        if (
            set(state) != {"state", "reason"}
            or state["state"] not in {"running", "halted", "reset", "faulted"}
            or state["reason"] not in {"requested", "breakpoint", "watchpoint", "fault", "exception", "reset"}
        ):
            raise ProbeBackendError("PROBE_BACKEND_ERROR", "Target state output is invalid")
        return state

    def _target_observation_policy(self) -> tuple[tuple[tuple[int, int], ...], frozenset[str]]:
        provider = getattr(self._backend, "target_observation_policy", None)
        if not callable(provider):
            raise ProbeBackendError(
                "PROBE_OPERATION_UNAVAILABLE", "Target observation policy is unavailable"
            )
        policy = provider()
        if not isinstance(policy, Mapping) or set(policy) != {
            "readable_regions", "register_allowlist"
        }:
            raise ProbeBackendError(
                "PROBE_BACKEND_ERROR", "Target observation policy is invalid"
            )
        raw_regions = policy["readable_regions"]
        raw_registers = policy["register_allowlist"]
        if (
            not isinstance(raw_regions, (list, tuple))
            or not 1 <= len(raw_regions) <= 32
            or not isinstance(raw_registers, (list, tuple))
            or not 1 <= len(raw_registers) <= 64
        ):
            raise ProbeBackendError(
                "PROBE_BACKEND_ERROR", "Target observation policy is invalid"
            )
        regions: list[tuple[int, int]] = []
        for item in raw_regions:
            if (
                not isinstance(item, Mapping)
                or set(item) != {"start", "size"}
                or type(item["start"]) is not int
                or type(item["size"]) is not int
                or item["start"] < 0
                or item["size"] <= 0
                or item["start"] + item["size"] > 1 << 32
            ):
                raise ProbeBackendError(
                    "PROBE_BACKEND_ERROR", "Target observation policy is invalid"
                )
            regions.append((item["start"], item["size"]))
        if regions != sorted(regions) or any(
            start + size > next_start
            for (start, size), (next_start, _next_size) in zip(regions, regions[1:])
        ):
            raise ProbeBackendError(
                "PROBE_BACKEND_ERROR", "Target observation policy is invalid"
            )
        registers = list(raw_registers)
        if (
            any(
                not isinstance(name, str)
                or _TARGET_REGISTER.fullmatch(name) is None
                for name in registers
            )
            or len(registers) != len(set(registers))
        ):
            raise ProbeBackendError(
                "PROBE_BACKEND_ERROR", "Target observation policy is invalid"
            )
        return tuple(regions), frozenset(registers)

    def _authorize_target_memory(self, address: int, length: int) -> None:
        regions, _registers = self._target_observation_policy()
        if not any(
            start <= address and address + length <= start + size
            for start, size in regions
        ):
            raise ProbeBackendError(
                "PROBE_PROTOCOL_INVALID",
                "Target memory request is outside the readable profile",
            )

    def _authorize_target_registers(self, names: tuple[str, ...]) -> None:
        _regions, registers = self._target_observation_policy()
        if any(name not in registers for name in names):
            raise ProbeBackendError(
                "PROBE_PROTOCOL_INVALID",
                "Target register request is outside the profile allowlist",
            )

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
        preflight = getattr(self._backend, "preflight_target_capabilities", None)
        if callable(preflight):
            try:
                preflight(self._probe_id, self._operation_level)
            except ProbeBackendError as error:
                code = error.code if error.code in TARGET_ERROR_CODES else "PROBE_BACKEND_ERROR"
                raise ProbeServiceError(
                    code,
                    error.message if code == error.code else "Probe capability preflight failed",
                ) from None
            except Exception:
                raise ProbeServiceError(
                    "PROBE_BACKEND_ERROR", "Probe capability preflight failed"
                ) from None
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
        if (
            request.operation == "probe.attach"
            and self._operation_level is OperationLevel.OBSERVE
        ):
            loop = asyncio.get_running_loop()
            deadline = loop.time() + request.timeout_ms / 1000
            async with asyncio.timeout_at(deadline):
                async with self._observation_attachment_lock:
                    return await self._run_backend_inner(request)
        return await self._run_backend_inner(request)

    async def _run_backend_inner(self, request: ProbeRequest) -> object:
        observation_candidate: tuple[
            str, str, ProbeAttachmentEvidence
        ] | None = None

        def invoke() -> object:
            nonlocal observation_candidate
            if request.operation_level is OperationLevel.CONTROL:
                try:
                    authorization = self._control_authorizations.consume(
                        str(request.data["authorization"]),
                        operation=request.operation,
                        arguments={
                            key: value for key, value in request.data.items()
                            if key != "authorization"
                        },
                        workspace_id=request.workspace_id,
                        session_id=request.session_id,
                        identity=None,
                        state=None,
                    )
                except ControlAuthorizationError as error:
                    raise ProbeBackendError(error.code, error.message) from error
                identity = dict(self._backend.target_identity())
                state = dict(self._backend.target_state())
                if (
                    identity != authorization["identity_snapshot"]
                    or state != authorization["state_snapshot"]
                ):
                    raise ProbeBackendError(
                        "PROBE_AUTHORIZATION_INVALID",
                        "Control authorization target binding changed",
                    )
            if request.operation == "probe.list":
                return {"probes": [item.to_dict() for item in self._backend.list_probes()]}
            if request.operation == "probe.attach":
                probe_id = str(request.data.get("probeId", ""))
                target = str(request.data.get("target", ""))
                evidence = self._reused_observation_attachment(probe_id, target)
                if evidence is not None:
                    payload = evidence.to_dict()
                    payload["requestedTarget"] = target
                    return payload

                evidence = self._backend.open_attach(
                    probe_id,
                    target,
                    halt_on_connect=self._operation_level is OperationLevel.MODIFY,
                )
                resolved_target = getattr(evidence, "resolved_part_number", None)
                requested_target = request.data.get("target")
                if (
                    not isinstance(requested_target, str)
                    or not isinstance(resolved_target, str)
                    or _canonical_target(requested_target)
                    != _canonical_target(resolved_target)
                ):
                    initiating = ProbeBackendError(
                        "PROBE_IDENTITY_MISMATCH",
                        "Connected target identity does not match",
                    )
                    restoration_error: ProbeBackendError | None = None
                    if self._operation_level is OperationLevel.MODIFY:
                        try:
                            self._backend.resume()
                            state = self._closed_target_state(
                                self._backend.target_state()
                            )
                            if state["state"] != "running":
                                raise ProbeBackendError(
                                    "PROBE_BACKEND_ERROR",
                                    "Target resume state is invalid",
                                )
                        except BaseException:
                            restoration_error = ProbeBackendError(
                                "PROBE_BACKEND_ERROR", "Target restoration failed"
                            )
                    try:
                        self._backend.close()
                    except BaseException:
                        raise ProbeBackendError(
                            "PROBE_CLOSE_FAILED", "Probe attach cleanup failed"
                        ) from initiating
                    if restoration_error is not None:
                        raise restoration_error from None
                    raise ProbeBackendError(
                        "PROBE_IDENTITY_MISMATCH",
                        "Connected target identity does not match",
                    )
                payload = evidence.to_dict()
                if self._operation_level is OperationLevel.OBSERVE:
                    payload["requestedTarget"] = target
                    observation_candidate = (
                        probe_id,
                        _canonical_target(target),
                        evidence,
                    )
                return payload
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
            if request.operation == "target.identity.read":
                return self._closed_target_identity(self._backend.target_identity())
            if request.operation == "target.state.read":
                return self._closed_target_state(self._backend.target_state())
            if request.operation == "target.halt":
                self._backend.halt()
                state = self._closed_target_state(self._backend.target_state())
                if state["state"] != "halted":
                    raise ProbeBackendError("PROBE_BACKEND_ERROR", "Target halt result is invalid")
                return {"state": "halted", "reason": state["reason"]}
            if request.operation == "target.resume":
                self._backend.resume()
                state = self._closed_target_state(self._backend.target_state())
                if state["state"] != "running":
                    raise ProbeBackendError("PROBE_BACKEND_ERROR", "Target resume result is invalid")
                return {"state": "running"}
            if request.operation == "target.step":
                before_values = self._backend.read_core_registers(("pc",))
                if not isinstance(before_values, Mapping) or set(before_values) != {"pc"}:
                    raise ProbeBackendError("PROBE_BACKEND_ERROR", "Target step result is invalid")
                before = before_values["pc"]
                self._backend.step()
                after_values = self._backend.read_core_registers(("pc",))
                if not isinstance(after_values, Mapping) or set(after_values) != {"pc"}:
                    raise ProbeBackendError("PROBE_BACKEND_ERROR", "Target step result is invalid")
                after = after_values["pc"]
                if any(type(value) is not int or not 0 <= value < 1 << 64 for value in (before, after)):
                    raise ProbeBackendError("PROBE_BACKEND_ERROR", "Target step result is invalid")
                state = self._closed_target_state(self._backend.target_state())
                if state["state"] != "halted":
                    raise ProbeBackendError("PROBE_BACKEND_ERROR", "Target step result is invalid")
                return {"state": "halted", "reason": "requested", "pc_before": before, "pc_after": after}
            if request.operation == "target.breakpoint.set":
                result = dict(self._backend.set_temporary_breakpoint(int(request.data["address"]), int(request.data["size"])))
                if (
                    set(result) != {"breakpoint_id", "address", "kind", "size"}
                    or result["address"] != request.data["address"]
                    or result["size"] != request.data["size"]
                    or result["kind"] != "temporary"
                    or not isinstance(result["breakpoint_id"], str)
                ):
                    raise ProbeBackendError("PROBE_BACKEND_ERROR", "Target breakpoint result is invalid")
                return result
            if request.operation == "target.breakpoint.clear":
                result = dict(self._backend.clear_temporary_breakpoint(str(request.data["breakpoint_id"])))
                if result != {"breakpoint_id": request.data["breakpoint_id"], "cleared": True}:
                    raise ProbeBackendError("PROBE_BACKEND_ERROR", "Target breakpoint result is invalid")
                return result
            if request.operation == "target.registers.read":
                names = tuple(str(item) for item in request.data["names"])
                self._authorize_target_registers(names)
                values = self._backend.target_read_core_registers(names)
                if (
                    not isinstance(values, Mapping)
                    or set(values) != set(names)
                    or any(type(values[name]) is not int or not 0 <= values[name] < 1 << 64 for name in names)
                ):
                    raise ProbeBackendError("PROBE_BACKEND_ERROR", "Target register output is invalid")
                return {"registers": [{"name": name, "value": values[name], "width_bits": 32 if values[name] <= 0xFFFF_FFFF else 64} for name in names]}
            if request.operation == "target.memory.read":
                address, length = int(request.data["address"]), int(request.data["length"])
                self._authorize_target_memory(address, length)
                raw = self._backend.target_read_memory(address, length)
                if len(raw) != length:
                    raise ProbeBackendError("PROBE_BACKPRESSURE", "Target memory returned partial output")
                return {"address": address, "length": length, "data_base64": base64.b64encode(raw).decode("ascii"), "sha256": hashlib.sha256(raw).hexdigest()}
            if request.operation == "target.fault.capture":
                captured = dict(self._backend.capture_fault(int(request.data["max_stack_bytes"])))
                if set(captured) != {"fault_registers", "stack", "truncated"}:
                    raise ProbeBackendError("PROBE_BACKEND_ERROR", "Fault capture output is invalid")
                stack = captured.pop("stack")
                registers = captured.get("fault_registers")
                if (
                    not isinstance(stack, bytes)
                    or len(stack) > request.data["max_stack_bytes"]
                    or not isinstance(registers, Mapping)
                    or set(registers) != {"cfsr", "hfsr", "dfsr", "afsr", "mmfar", "bfar", "shcsr", "icsr"}
                    or any(type(value) is not int or not 0 <= value <= 0xFFFF_FFFF for value in registers.values())
                    or type(captured.get("truncated")) is not bool
                ):
                    raise ProbeBackendError("PROBE_BACKEND_ERROR", "Fault stack output is invalid")
                captured.update({
                    "stack_artifact": None if not stack else self._store_capture(
                        stack,
                        prefix="fault-stack",
                        name="fault-stack.bin",
                        kind="fault-stack",
                        media_type="application/octet-stream",
                    ),
                    "stack_bytes": len(stack),
                })
                return captured
            if request.operation == "target.logs.capture":
                captured = dict(self._backend.capture_logs(str(request.data["channel"]), int(request.data["max_bytes"]), int(request.data["duration_ms"])))
                if set(captured) != {"data", "truncated"}:
                    raise ProbeBackendError("PROBE_BACKEND_ERROR", "Log capture output is invalid")
                raw = captured.pop("data")
                if not isinstance(raw, bytes) or len(raw) > request.data["max_bytes"]:
                    raise ProbeBackendError("PROBE_BACKEND_ERROR", "Log capture output is invalid")
                if type(captured.get("truncated")) is not bool:
                    raise ProbeBackendError("PROBE_BACKEND_ERROR", "Log capture output is invalid")
                return {
                    "channel": request.data["channel"],
                    "artifact": self._store_capture(
                        raw,
                        prefix="target-logs",
                        name="target-logs.bin",
                        kind="target-logs",
                        media_type="application/octet-stream",
                    ),
                    "bytes": len(raw),
                    "duration_ms": request.data["duration_ms"],
                    "truncated": captured["truncated"],
                }
            if request.operation == "target.transport.open":
                transport = str(request.data["transport"])
                effective = self._effective_target_transport_config(
                    transport, request.data["config"]
                )
                result = dict(self._backend.open_target_transport(transport, effective, int(request.data["deadline_ms"])))
                if set(result) != {"transport_id", "identity"} or not isinstance(result["transport_id"], str):
                    raise ProbeBackendError("PROBE_BACKEND_ERROR", "Target transport result is invalid")
                identity = result["identity"]
                if not isinstance(identity, Mapping) or not identity or any(
                    not isinstance(key, str) or not isinstance(value, str) or not value
                    for key, value in identity.items()
                ):
                    raise ProbeBackendError("PROBE_BACKEND_ERROR", "Target transport identity is invalid")
                transport_fields = {
                    "mailbox": {"probe_id", "target_id", "transport", "config_digest", "address", "ring_size", "ram_bounds"},
                    "rtt": {"probe_id", "target_id", "transport", "config_digest", "channel", "control_block_address", "ram_bounds"},
                    "uart": {"probe_id", "target_id", "transport", "config_digest", "port", "baud", "data_bits", "parity", "stop_bits", "flow_control"},
                    "semihosting": {"probe_id", "target_id", "transport", "config_digest", "elf_path", "elf_sha256", "host_file_policy"},
                }[transport]
                projected = {key: value for key, value in identity.items() if key in transport_fields}
                result["identity"] = projected if set(projected) == transport_fields else dict(identity)
                if transport == "semihosting" and self._project_root is not None:
                    facts = load_fresh_firmware_facts(self._project_root)
                    result["identity"]["elf_path"] = facts.elf_path
                    result["identity"]["config_digest"] = hashlib.sha256(
                        json.dumps(
                            {
                                "elf_path": facts.elf_path,
                                "elf_sha256": facts.elf_sha256,
                                "host_files": False,
                                "profile_declared": True,
                            },
                            ensure_ascii=False, allow_nan=False,
                            separators=(",", ":"), sort_keys=True,
                        ).encode("utf-8")
                    ).hexdigest()
                return result
            if request.operation == "target.transport.read":
                captured = dict(self._backend.read_target_transport(str(request.data["transport_id"]), int(request.data["max_bytes"]), int(request.data["deadline_ms"])))
                if set(captured) != {"data", "eof"}:
                    raise ProbeBackendError("PROBE_BACKEND_ERROR", "Target transport output is invalid")
                raw = captured.pop("data")
                if not isinstance(raw, bytes) or len(raw) > request.data["max_bytes"]:
                    raise ProbeBackendError("PROBE_BACKEND_ERROR", "Target transport output is invalid")
                if type(captured.get("eof")) is not bool:
                    raise ProbeBackendError("PROBE_BACKEND_ERROR", "Target transport output is invalid")
                return {"data_base64": base64.b64encode(raw).decode("ascii"), "eof": captured["eof"]}
            if request.operation == "target.transport.close":
                result = dict(self._backend.close_target_transport(str(request.data["transport_id"])))
                if result != {"transport_id": request.data["transport_id"], "closed": True}:
                    raise ProbeBackendError("PROBE_BACKEND_ERROR", "Target transport cleanup result is invalid")
                return result
            raise ProbeBackendError("PROBE_OPERATION_UNSUPPORTED", "Operation is unsupported")

        is_modify = request.operation == "flash.program"
        is_attach = request.operation == "probe.attach"
        has_irreversible_native_effect = (
            is_modify or request.operation_level is OperationLevel.CONTROL
        )
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
            result = await asyncio.wait_for(
                asyncio.shield(task), timeout=request.timeout_ms / 1000
            )
            if observation_candidate is not None:
                self._observation_attachment = observation_candidate
            return result
        except (asyncio.TimeoutError, asyncio.CancelledError):
            if is_attach and self._operation_level is OperationLevel.OBSERVE:
                self._observation_attachment = None
            if not entered_backend.is_set():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            elif is_attach and not task.cancelled():
                outcome, value = await _await_attach_outcome(task)
                if outcome == "timeout":
                    initiating = ProbeBackendError(
                        "PROBE_TIMEOUT", "Attach recovery did not reach a terminal state"
                    )
                    abort = getattr(self._backend, "abort_owned_execution", None)
                    if callable(abort):
                        aborting = asyncio.create_task(asyncio.to_thread(abort))
                        try:
                            await _await_task_ignoring_cancellation(aborting)
                        except BaseException:
                            pass
                    raise ProbeBackendError(
                        "PROBE_CLOSE_FAILED", "Probe attach cleanup failed"
                    ) from initiating
                if outcome == "error":
                    if isinstance(value, ProbeBackendError) and value.code == "PROBE_CLOSE_FAILED":
                        raise ProbeBackendError(
                            value.code, value.message, value.details
                        ) from value
                    raise

                recovery_error: ProbeBackendError | None = None
                if self._operation_level is OperationLevel.MODIFY:
                    try:
                        await _run_owned_backend_call(self._backend.resume)
                        target_state = getattr(self._backend, "target_state", None)
                        if not callable(target_state):
                            raise ProbeBackendError(
                                "PROBE_BACKEND_ERROR", "Target state is unavailable"
                            )
                        state = self._closed_target_state(
                            await _run_owned_backend_call(target_state)
                        )
                        if state["state"] != "running":
                            raise ProbeBackendError(
                                "PROBE_BACKEND_ERROR",
                                "Target resume state is invalid",
                            )
                    except BaseException:
                        recovery_error = ProbeBackendError(
                            "PROBE_BACKEND_ERROR", "Probe attach recovery failed"
                        )
                try:
                    await _run_owned_backend_call(self._backend.close)
                except BaseException:
                    initiating = recovery_error or ProbeBackendError(
                        "PROBE_BACKEND_ERROR", "Probe attach recovery failed"
                    )
                    raise ProbeBackendError(
                        "PROBE_CLOSE_FAILED", "Probe attach cleanup failed"
                    ) from initiating
                if recovery_error is not None:
                    raise ProbeBackendError(
                        "PROBE_CLOSE_FAILED", "Probe attach cleanup failed"
                    ) from recovery_error
            elif has_irreversible_native_effect and not task.cancelled():
                abort = getattr(self._backend, "abort_owned_execution", None)
                if is_modify and not callable(abort):
                    # Preserve the accepted in-process guarded-flash commit point:
                    # once programming entered, its terminal report wins.
                    return await asyncio.shield(task)
                if callable(abort):
                    # The worker terminates only its exact owned child and performs
                    # a bounded join. The proxy call then reaches a terminal error.
                    aborting = asyncio.create_task(asyncio.to_thread(abort))
                    await asyncio.wait_for(asyncio.shield(aborting), timeout=3.0)
                    await asyncio.wait_for(
                        asyncio.gather(asyncio.shield(task), return_exceptions=True),
                        timeout=1.0,
                    )
                else:
                    # Bounded direct fakes are retained only as test seams. Never
                    # return while an irreversible fake action is still live.
                    await asyncio.shield(task)
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
                "PROBE_IDENTITY_MISMATCH" if request.operation.startswith("target.") else "PROBE_SESSION_MISMATCH",
                "Target request identity does not match" if request.operation.startswith("target.") else "Probe request does not match the owning session",
                request_id=request.request_id,
                operation=request.operation,
            )
        if request.lease_id != endpoint.lease_id:
            return self._failure(
                "PROBE_LEASE_INVALID" if request.operation.startswith("target.") else "PROBE_LEASE_LOST",
                "Target request lease is invalid" if request.operation.startswith("target.") else "Probe request lease is no longer active",
                request_id=request.request_id,
                operation=request.operation,
            )
        if not self._operation_level.allows(request.operation_level):
            return self._failure(
                "PROBE_AUTHORIZATION_REQUIRED" if request.operation.startswith("target.") else "PROBE_OPERATION_LEVEL_DENIED",
                "Target request requires a higher authorization level" if request.operation.startswith("target.") else "Probe request exceeds the granted operation level",
                request_id=request.request_id,
                operation=request.operation,
            )
        required_level = (
            OperationLevel.MODIFY
            if request.operation == "flash.program"
            else OperationLevel.CONTROL if request.operation in {
                "target.halt", "target.resume", "target.step", "target.breakpoint.set", "target.breakpoint.clear"
            } else OperationLevel.OBSERVE
        )
        if (
            request.operation_level is not required_level
            or not self._operation_level.allows(required_level)
        ):
            return self._failure(
                "PROBE_AUTHORIZATION_REQUIRED" if request.operation.startswith("target.") else "PROBE_OPERATION_LEVEL_DENIED",
                "Target operation authorization level is invalid" if request.operation.startswith("target.") else "Probe operation does not match the required operation level",
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
            code = error.code
            message = error.message
            details = error.details
            if request.operation.startswith("target.") and code not in TARGET_ERROR_CODES:
                code, message, details = "PROBE_BACKEND_ERROR", "Probe backend operation failed", {}
            response = ProbeResponse.failure(
                request.request_id,
                request.operation,
                code,
                message,
                details,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            response = ProbeResponse.failure(
                request.request_id,
                request.operation,
                "PROBE_BACKEND_ERROR" if request.operation.startswith("target.") else "PROBE_INTERNAL_ERROR",
                "Probe backend operation failed" if request.operation.startswith("target.") else "Probe Service operation failed",
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
        self._observation_attachment = None
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
