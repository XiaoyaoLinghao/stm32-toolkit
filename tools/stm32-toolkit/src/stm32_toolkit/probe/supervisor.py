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
from .service import ProbeEndpoint, ProbeService


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

    async def start(self) -> ProbeEndpoint:
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
                )
                endpoint = await service.start()
            except BaseException:
                if backend is not None:
                    try:
                        await asyncio.to_thread(backend.close)
                    except Exception:
                        pass
                raise

            self._backend = backend
            self._service = service
            self._endpoint = endpoint
            return endpoint

    async def stop(self) -> None:
        async with self._lifecycle_lock:
            service, self._service = self._service, None
            backend, self._backend = self._backend, None
            self._endpoint = None

            if service is not None:
                await service.stop()
            elif backend is not None:
                await asyncio.to_thread(backend.close)

    async def __aenter__(self) -> ProbeEndpoint:
        return await self.start()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.stop()
