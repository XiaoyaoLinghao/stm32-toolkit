"""Lifecycle supervision for one in-process Probe Service."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from .backend import ProbeBackend
from .lease import ProbeLeaseManager
from .model import OperationLevel
from .service import (
    ProbeEndpoint,
    ProbeService,
    ProbeServiceError,
    _await_commit_completion,
    _await_task_completion,
)


@dataclass(frozen=True)
class ProbeServiceConfig:
    probe_id: str
    workspace_id: str
    session_id: str
    operation_level: OperationLevel
    session_root: Path
    project_root: Path | None = None


class ProbeServiceSupervisor:
    def __init__(
        self,
        *,
        config: ProbeServiceConfig,
        lease_manager: ProbeLeaseManager,
        backend_factory: Callable[[], ProbeBackend],
    ) -> None:
        self._config = config
        self._lease_manager = lease_manager
        self._backend_factory = backend_factory
        self._lifecycle_lock = asyncio.Lock()
        self._backend: ProbeBackend | None = None
        self._service: ProbeService | None = None
        self._endpoint: ProbeEndpoint | None = None

    @property
    def endpoint(self) -> ProbeEndpoint | None:
        return self._endpoint

    async def start(self, *, handoff_ticket: str | None = None) -> ProbeEndpoint:
        async with self._lifecycle_lock:
            if self._endpoint is not None:
                return self._endpoint

            backend: ProbeBackend | None = None
            try:
                backend = self._backend_factory()
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

    async def stop(self) -> None:
        async with self._lifecycle_lock:
            service = self._service
            backend = self._backend
            try:
                if service is not None:
                    stopping = asyncio.create_task(service.stop())
                    await _await_task_completion(stopping)
                elif backend is not None:
                    closing = asyncio.create_task(asyncio.to_thread(backend.close))
                    await _await_task_completion(closing)
            finally:
                self._service = None
                self._backend = None
                self._endpoint = None

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
