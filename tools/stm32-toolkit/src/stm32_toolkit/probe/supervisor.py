"""Lifecycle supervision for one in-process Probe Service."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType

from .backend import ProbeBackend
from .attach_diagnostics import CleanupFragment, make_cleanup_entry
from .pyocd_backend import PyOCDBackend
from .worker import ProbeBackendWorker, ProbeWorkerConfig
from .authorization import ControlAuthorizationStore
from .lease import ProbeLeaseManager
from .model import OperationLevel
from stm32_toolkit.testing.artifacts import TestArtifactCollector
from .service import (
    ProbeEndpoint,
    ProbeService,
    ProbeServiceCleanupError,
    ProbeServiceError,
    _await_commit_completion,
    _await_task_completion,
    _service_error_fields,
)


@dataclass(frozen=True)
class ProbeServiceConfig:
    probe_id: str
    workspace_id: str
    session_id: str
    operation_level: OperationLevel
    session_root: Path
    project_root: Path | None = None
    control_authorizations: ControlAuthorizationStore | None = field(
        default=None, repr=False, compare=False
    )
    artifact_collector: TestArtifactCollector | None = field(
        default=None, repr=False, compare=False
    )
    _runtime_root_authority: object | None = field(
        default=None, repr=False, compare=False
    )


class ProbeServiceSupervisor:
    def __init__(
        self,
        *,
        config: ProbeServiceConfig,
        lease_manager: ProbeLeaseManager,
        backend_factory: Callable[[], ProbeBackend] | None = None,
        worker_config: ProbeWorkerConfig | None = None,
    ) -> None:
        if (backend_factory is None) == (worker_config is None):
            raise TypeError("Exactly one production worker config or private test backend is required")
        if worker_config is not None and type(worker_config) is not ProbeWorkerConfig:
            raise TypeError("Probe worker configuration is invalid")
        self._config = config
        self._lease_manager = lease_manager
        self._backend_factory = backend_factory
        self._worker_config = worker_config
        self._control_authorizations = config.control_authorizations or ControlAuthorizationStore(
            (lease_manager.data_root / "control-authorizations").absolute()
        )
        self._lifecycle_lock = asyncio.Lock()
        self._backend: ProbeBackend | None = None
        self._service: ProbeService | None = None
        self._endpoint: ProbeEndpoint | None = None

    @property
    def endpoint(self) -> ProbeEndpoint | None:
        return self._endpoint

    @property
    def control_authorizations(self) -> ControlAuthorizationStore:
        return self._control_authorizations

    async def start(self, *, handoff_ticket: str | None = None) -> ProbeEndpoint:
        async with self._lifecycle_lock:
            if self._endpoint is not None:
                return self._endpoint

            backend: ProbeBackend | None = None
            try:
                if self._worker_config is not None:
                    backend = ProbeBackendWorker(config=self._worker_config)
                else:
                    assert self._backend_factory is not None
                    backend = self._backend_factory()
                    if isinstance(backend, PyOCDBackend):
                        backend.close()
                        raise TypeError("PyOCD production backends require a closed worker config")
                service = ProbeService(
                    backend=backend,
                    lease_manager=self._lease_manager,
                    probe_id=self._config.probe_id,
                    workspace_id=self._config.workspace_id,
                    session_id=self._config.session_id,
                    operation_level=self._config.operation_level,
                    session_root=self._config.session_root,
                    project_root=self._config.project_root,
                    handoff_ticket=handoff_ticket,
                    _runtime_root_authority=self._config._runtime_root_authority,
                    control_authorizations=self._control_authorizations,
                    artifact_collector=self._config.artifact_collector,
                )
                endpoint = await service.start()
            except BaseException:
                if backend is not None:
                    closing = asyncio.create_task(asyncio.to_thread(backend.close))
                    try:
                        await _await_task_completion(closing)
                    except BaseException:
                        pass
                raise

            self._backend = backend
            self._service = service
            self._endpoint = endpoint
            return endpoint

    async def stop(self) -> CleanupFragment:
        async with self._lifecycle_lock:
            service = self._service
            backend = self._backend
            fragment = CleanupFragment()
            try:
                if service is not None:
                    stopping = asyncio.create_task(service.stop())
                    fragment = await _await_task_completion(stopping)  # type: ignore[assignment]
                elif backend is not None:
                    closing = asyncio.create_task(asyncio.to_thread(backend.close))
                    try:
                        await _await_task_completion(closing)
                    except BaseException as error:
                        reason, source_code = _service_error_fields(error)
                        fragment = CleanupFragment.from_entries((
                            make_cleanup_entry(
                                "service-stop-backend-close",
                                "failed",
                                reason=reason,
                                source_code=source_code,
                            ),
                        ))
                        raise ProbeServiceCleanupError(fragment) from error
                    fragment = CleanupFragment.from_entries((
                        make_cleanup_entry("service-stop-backend-close", "succeeded"),
                    ))
            finally:
                self._service = None
                self._backend = None
                self._endpoint = None
            return fragment

    async def drain_modifications(self) -> None:
        async with self._lifecycle_lock:
            service = self._service
            if service is None or self._endpoint is None:
                raise ProbeServiceError(
                    "PROBE_SERVICE_UNAVAILABLE", "Probe Service is unavailable"
                )
            await service.drain_modifications()

    async def reserve_external_handoff(self, ticket: str) -> None:
        async with self._lifecycle_lock:
            service = self._service
            if service is None or self._endpoint is None:
                raise ProbeServiceError(
                    "PROBE_SERVICE_UNAVAILABLE", "Probe Service is unavailable"
                )
            await service.reserve_external_handoff(ticket)

    async def consume_external_handoff(self, ticket: str) -> None:
        async with self._lifecycle_lock:
            service = self._service
            if service is None or self._endpoint is None:
                raise ProbeServiceError(
                    "PROBE_SERVICE_UNAVAILABLE", "Probe Service is unavailable"
                )
            await service.consume_external_handoff(ticket)

    async def finalize_consumed_handoff(self, ticket: str) -> bool:
        async with self._lifecycle_lock:
            task = asyncio.create_task(
                asyncio.to_thread(
                    self._lease_manager.finalize_consumed_handoff,
                    probe_id=self._config.probe_id,
                    workspace_id=self._config.workspace_id,
                    session_id=self._config.session_id,
                    ticket=ticket,
                    _runtime_root_authority=self._config._runtime_root_authority,
                )
            )
            return bool(await _await_commit_completion(task))

    async def acknowledge_consumed_handoff(self, ticket: str) -> bool:
        async with self._lifecycle_lock:
            task = asyncio.create_task(
                asyncio.to_thread(
                    self._lease_manager.acknowledge_consumed_handoff,
                    probe_id=self._config.probe_id,
                    workspace_id=self._config.workspace_id,
                    session_id=self._config.session_id,
                    ticket=ticket,
                    _runtime_root_authority=self._config._runtime_root_authority,
                )
            )
            return bool(await _await_commit_completion(task))

    async def __aenter__(self) -> ProbeEndpoint:
        return await self.start()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.stop()
