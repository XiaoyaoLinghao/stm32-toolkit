"""Bounded authenticated aiohttp transport for one Monitor runtime."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from aiohttp import WSMsgType, web

from stm32_toolkit import __version__ as TOOLKIT_VERSION

from .auth import (
    MAX_REQUEST_BYTES,
    MONITOR_COOKIE_NAME,
    MonitorAuth,
    MonitorAuthError,
)
from .protocol import ProtocolResult

MONITOR_PROTOCOL_VERSION = "stm32-toolkit-monitor/1"
MONITOR_VERSION = "0.4.0"
_FORBIDDEN_KEYS = {
    "workspaceid",
    "projectroot",
    "dataroot",
    "target",
    "svd",
    "svdpath",
    "elf",
    "elfpath",
    "address",
    "operationlevel",
    "backend",
    "command",
}


@dataclass(frozen=True)
class MonitorEndpoint:
    host: str
    port: int
    token: str = field(repr=False)
    workspace_id: str
    session_id: str
    protocol: str = MONITOR_PROTOCOL_VERSION
    toolkit_version: str = TOOLKIT_VERSION
    monitor_version: str = MONITOR_VERSION

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def access_url(self) -> str:
        return f"{self.url}/#token={self.token}"


class _ServiceFailure(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _envelope(
    operation: str,
    *,
    data: object = None,
    code: str = "OK",
    message: str = "",
    details: Mapping[str, object] | None = None,
) -> dict[str, object]:
    return {
        "protocol": MONITOR_PROTOCOL_VERSION,
        "toolkitVersion": TOOLKIT_VERSION,
        "monitorVersion": MONITOR_VERSION,
        "ok": code == "OK",
        "operation": operation,
        "code": code,
        "message": message,
        "data": data if code == "OK" else None,
        "details": dict(details or {}),
    }


def _response(
    operation: str,
    *,
    data: object = None,
    code: str = "OK",
    message: str = "",
    details: Mapping[str, object] | None = None,
    status: int = 200,
) -> web.Response:
    return web.json_response(
        _envelope(operation, data=data, code=code, message=message, details=details),
        status=status,
    )


def _public_result(operation: str, value: object) -> tuple[object, str, str, Mapping[str, object]]:
    if isinstance(value, Mapping):
        return dict(value), "OK", "", {}
    if not isinstance(value, ProtocolResult):
        raise TypeError("runtime returned an unsupported result")
    payload = value.to_dict()
    if payload["ok"] is True:
        return payload["data"], "OK", "", {}
    details = payload["details"] if isinstance(payload["details"], Mapping) else {}
    return None, str(payload["code"]), str(payload["message"]), details


def _reject_overrides(value: object) -> None:
    pending = [value]
    nodes = 0
    while pending:
        current = pending.pop()
        nodes += 1
        if nodes > 20_000:
            raise _ServiceFailure(
                "MONITOR_REQUEST_INVALID", "Monitor request is invalid"
            )
        if isinstance(current, Mapping):
            for key, item in current.items():
                if not isinstance(key, str) or key.casefold().replace("_", "") in _FORBIDDEN_KEYS:
                    raise _ServiceFailure(
                        "MONITOR_REQUEST_INVALID", "Monitor request is invalid"
                    )
                pending.append(item)
        elif isinstance(current, list):
            pending.extend(current)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _ServiceFailure(
                "MONITOR_REQUEST_INVALID", "Monitor request is invalid"
            )
        result[key] = value
    return result


def _reject_constant(_value: str) -> object:
    raise _ServiceFailure("MONITOR_REQUEST_INVALID", "Monitor request is invalid")


def _query_values(request: web.Request) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in request.query.items():
        if key in result:
            raise _ServiceFailure(
                "MONITOR_REQUEST_INVALID", "Monitor request is invalid"
            )
        result[key] = value
    return result


@web.middleware
async def _protocol_errors(
    request: web.Request, handler
) -> web.StreamResponse:
    try:
        return await handler(request)
    except (web.HTTPNotFound, web.HTTPMethodNotAllowed) as error:
        return _response(
            "monitor.request",
            code="MONITOR_REQUEST_INVALID",
            message="Monitor request is invalid",
            status=error.status,
        )


class MonitorService:
    """One dynamic loopback listener bound to a single runtime identity."""

    def __init__(
        self,
        runtime: object,
        *,
        workspace_id: str,
        session_id: str,
        token_factory=None,
        send_delay_seconds: float = 0.0,
    ) -> None:
        if not isinstance(workspace_id, str) or not workspace_id:
            raise ValueError("Monitor workspace identity is invalid")
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("Monitor session identity is invalid")
        if not isinstance(send_delay_seconds, (int, float)) or not 0 <= send_delay_seconds <= 1:
            raise ValueError("Monitor send delay seam is invalid")
        self._runtime = runtime
        self._workspace_id = workspace_id
        self._session_id = session_id
        self._token_factory = token_factory
        self._send_delay_seconds = float(send_delay_seconds)
        self._runner: web.AppRunner | None = None
        self._endpoint: MonitorEndpoint | None = None
        self._auth: MonitorAuth | None = None
        self._stop_lock = asyncio.Lock()
        self._live_tasks: set[asyncio.Task[object]] = set()

    @property
    def endpoint(self) -> MonitorEndpoint | None:
        return self._endpoint

    async def start(self) -> MonitorEndpoint:
        if self._endpoint is not None:
            return self._endpoint
        application = web.Application(
            client_max_size=MAX_REQUEST_BYTES,
            middlewares=[_protocol_errors],
            handler_args={
                "max_field_size": MAX_REQUEST_BYTES,
                "max_line_size": MAX_REQUEST_BYTES,
            },
        )
        application.router.add_post("/api/v1/auth/bootstrap", self._bootstrap)
        application.router.add_get("/api/v1/status", self._route("monitor.status"))
        application.router.add_get("/api/v1/groups", self._route("monitor.groups.list"))
        application.router.add_post("/api/v1/groups", self._route("monitor.groups.create", body=True))
        application.router.add_patch(
            "/api/v1/groups/{resource_id}", self._route("monitor.groups.update", body=True)
        )
        application.router.add_delete(
            "/api/v1/groups/{resource_id}", self._route("monitor.groups.delete", body=True)
        )
        application.router.add_post(
            "/api/v1/groups/import", self._route("monitor.groups.import", body=True)
        )
        for action in ("connect", "release", "reconnect"):
            application.router.add_post(
                f"/api/v1/probe/{action}",
                self._route(f"monitor.probe.{action}", body=action == "connect"),
            )
        for action in ("start", "pause", "resume", "stop"):
            application.router.add_post(
                f"/api/v1/sampling/{action}",
                self._route(f"monitor.sampling.{action}", body=action == "start"),
            )
        application.router.add_get(
            "/api/v1/history", self._route("monitor.history.query", query=True)
        )
        application.router.add_post("/api/v1/exports", self._route("monitor.exports.create", body=True))
        application.router.add_get(
            "/api/v1/exports/{resource_id}", self._route("monitor.exports.get")
        )
        application.router.add_get("/api/v1/live", self._live)

        runner = web.AppRunner(application, access_log=None)
        try:
            await runner.setup()
            site = web.TCPSite(runner, host="127.0.0.1", port=0)
            await site.start()
            addresses = runner.addresses
            if len(addresses) != 1 or addresses[0][0] != "127.0.0.1":
                raise RuntimeError("Monitor Service did not bind exact IPv4 loopback")
            port = int(addresses[0][1])
            factory = self._token_factory
            auth = MonitorAuth.create(
                host="127.0.0.1",
                port=port,
                **({"token_factory": factory} if factory is not None else {}),
            )
            endpoint = MonitorEndpoint(
                "127.0.0.1",
                port,
                auth.token,
                self._workspace_id,
                self._session_id,
            )
        except BaseException:
            await runner.cleanup()
            raise
        self._runner = runner
        self._auth = auth
        self._endpoint = endpoint
        return endpoint

    def _authorize(self, request: web.Request, *, bootstrap: bool = False) -> str:
        auth = self._auth
        if auth is None:
            raise _ServiceFailure(
                "MONITOR_SERVICE_UNAVAILABLE", "Monitor Service is unavailable", 503
            )
        try:
            auth.require_header_budget(tuple(request.headers.items()))
            return auth.authorize(
                peer=request.remote,
                host=request.host,
                origin=request.headers.get("Origin"),
                authorization=request.headers.get("Authorization"),
                cookie=request.cookies.get(MONITOR_COOKIE_NAME),
                bootstrap=bootstrap,
            )
        except MonitorAuthError as error:
            raise _ServiceFailure(error.code, error.message, error.status) from None

    async def _bootstrap(self, request: web.Request) -> web.Response:
        try:
            self._authorize(request, bootstrap=True)
            if request.can_read_body or request.query:
                raise _ServiceFailure(
                    "MONITOR_REQUEST_INVALID", "Monitor request is invalid"
                )
        except _ServiceFailure as error:
            return _response(
                "monitor.auth.bootstrap",
                code=error.code,
                message=error.message,
                status=error.status,
            )
        response = _response("monitor.auth.bootstrap", data={"authenticated": True})
        assert self._auth is not None
        response.set_cookie(
            MONITOR_COOKIE_NAME,
            self._auth.token,
            httponly=True,
            samesite="Strict",
            path="/api/v1",
        )
        return response

    async def _read_json(self, request: web.Request) -> dict[str, object]:
        if request.content_type != "application/json":
            raise _ServiceFailure(
                "MONITOR_CONTENT_TYPE_REQUIRED",
                "Monitor Service requires application/json",
                415,
            )
        if request.content_length is not None and request.content_length > MAX_REQUEST_BYTES:
            raise _ServiceFailure(
                "MONITOR_REQUEST_TOO_LARGE", "Monitor request exceeds its size limit", 413
            )
        try:
            raw = await request.content.readexactly(MAX_REQUEST_BYTES + 1)
        except asyncio.IncompleteReadError as error:
            raw = error.partial
        if len(raw) > MAX_REQUEST_BYTES:
            raise _ServiceFailure(
                "MONITOR_REQUEST_TOO_LARGE", "Monitor request exceeds its size limit", 413
            )
        try:
            payload = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise _ServiceFailure(
                "MONITOR_REQUEST_INVALID", "Monitor request is invalid"
            ) from None
        if not isinstance(payload, dict):
            raise _ServiceFailure("MONITOR_REQUEST_INVALID", "Monitor request is invalid")
        _reject_overrides(payload)
        return payload

    def _route(
        self, operation: str, *, body: bool = False, query: bool = False
    ):
        async def handler(request: web.Request) -> web.Response:
            try:
                self._authorize(request)
                if body:
                    payload = await self._read_json(request)
                else:
                    if request.can_read_body:
                        raise _ServiceFailure(
                            "MONITOR_REQUEST_INVALID", "Monitor request is invalid"
                        )
                    payload = {}
                resource_id = request.match_info.get("resource_id")
                query_values = _query_values(request)
                if query_values and not query:
                    raise _ServiceFailure(
                        "MONITOR_REQUEST_INVALID", "Monitor request is invalid"
                    )
                _reject_overrides(query_values)
                value = await self._runtime.dispatch(
                    operation,
                    payload,
                    resource_id=resource_id,
                    query=query_values,
                )
                data, code, message, details = _public_result(operation, value)
                status = 200 if code == "OK" else 409
                return _response(
                    operation,
                    data=data,
                    code=code,
                    message=message,
                    details=details,
                    status=status,
                )
            except _ServiceFailure as error:
                return _response(
                    operation, code=error.code, message=error.message, status=error.status
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                return _response(
                    operation,
                    code="MONITOR_INTERNAL_ERROR",
                    message="Monitor Service request failed",
                    status=500,
                )

        return handler

    async def _live(self, request: web.Request) -> web.StreamResponse:
        try:
            self._authorize(request)
            if request.can_read_body or request.query:
                raise _ServiceFailure(
                    "MONITOR_REQUEST_INVALID", "Monitor request is invalid"
                )
        except _ServiceFailure as error:
            return _response(
                "monitor.live", code=error.code, message=error.message, status=error.status
            )
        websocket = web.WebSocketResponse(max_msg_size=MAX_REQUEST_BYTES)
        await websocket.prepare(request)
        queue: asyncio.Queue[tuple[object, int]] = asyncio.Queue(maxsize=8)

        async def produce() -> None:
            dropped = 0
            source = self._runtime.live_subscribe()
            async for item in source:
                if queue.full():
                    try:
                        _evicted, evicted_drops = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    else:
                        dropped += evicted_drops + 1
                queue.put_nowait((item, dropped))
                dropped = 0

        async def send() -> None:
            while not websocket.closed:
                item, dropped = await queue.get()
                if self._send_delay_seconds:
                    await asyncio.sleep(self._send_delay_seconds)
                await websocket.send_json(
                    _envelope(
                        "monitor.live",
                        data=item,
                        details={"subscriberDropped": dropped},
                    )
                )

        producer = asyncio.create_task(produce(), name="stm32-monitor-live-producer")
        sender = asyncio.create_task(send(), name="stm32-monitor-live-sender")
        self._live_tasks.update((producer, sender))
        try:
            async for message in websocket:
                if message.type in {WSMsgType.ERROR, WSMsgType.CLOSE, WSMsgType.CLOSED}:
                    break
                await websocket.close(code=1008, message=b"client messages are unsupported")
                break
        finally:
            producer.cancel()
            sender.cancel()
            await asyncio.gather(producer, sender, return_exceptions=True)
            self._live_tasks.discard(producer)
            self._live_tasks.discard(sender)
        return websocket

    async def stop(self) -> None:
        async with self._stop_lock:
            runner = self._runner
            if runner is None:
                return
            for task in tuple(self._live_tasks):
                task.cancel()
            if self._live_tasks:
                await asyncio.gather(*tuple(self._live_tasks), return_exceptions=True)
            await runner.cleanup()
            self._runner = None
            self._endpoint = None
            self._auth = None


__all__ = [
    "MONITOR_PROTOCOL_VERSION",
    "MONITOR_VERSION",
    "MonitorEndpoint",
    "MonitorService",
]
