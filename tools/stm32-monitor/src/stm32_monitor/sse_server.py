"""SSE + HTTP server for live monitoring web interface."""

import json
import time
import asyncio
import logging
from pathlib import Path
from aiohttp import web

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent.parent.parent / "static"
PROBE_IDLE_TIMEOUT = 30  # seconds before auto-detach when no SSE clients


class SSEServer:
    """Async HTTP server with SSE streaming for live variable monitoring."""

    def __init__(self, poller, session_factory, port: int = 8888):
        self._poller = poller
        self._session_factory = session_factory  # callable to create new PyOCDSession
        self._session = None  # set from cli after init
        self._port = port
        self._app = web.Application()
        self._sse_clients: set[web.StreamResponse] = set()
        self._last_client_disconnect = 0.0
        self._auto_detach_task = None
        self._probe_attached = True
        self._setup_routes()

    def set_session(self, session):
        """Set the PyOCD session reference."""
        self._session = session
    def _setup_routes(self):
        self._app.router.add_get("/", self._handle_index)
        self._app.router.add_get("/api/variables", self._handle_variables)
        self._app.router.add_post("/api/watch", self._handle_watch_set)
        self._app.router.add_get("/api/watch", self._handle_watch_get)
        self._app.router.add_get("/api/snapshot", self._handle_snapshot)
        self._app.router.add_get("/api/stream", self._handle_stream)
        self._app.router.add_post("/api/poll-rate", self._handle_poll_rate)
        self._app.router.add_post("/api/pause", self._handle_pause)
        self._app.router.add_post("/api/detach", self._handle_detach)
        self._app.router.add_post("/api/attach", self._handle_attach)
        self._app.router.add_get("/api/status", self._handle_status)
        self._app.router.add_get("/api/export", self._handle_export)
        self._app.router.add_static("/static", STATIC_DIR)

    # ---- Core API ----
    async def _handle_index(self, request):
        html = STATIC_DIR / "index.html"
        if html.exists():
            return web.FileResponse(html)
        return web.Response(text="index.html not found", status=404)

    async def _handle_variables(self, request):
        elf_vars = self._app.get("elf_variables", [])
        svd_peripherals = self._app.get("svd_peripherals", [])
        q = request.query.get("q", "").lower()
        if q:
            elf_vars = [v for v in elf_vars if q in v["name"].lower()]
        return web.json_response({
            "variables": elf_vars,
            "peripherals": svd_peripherals,
            "modules": sorted(set(v.get("module", "Other") for v in elf_vars)),
        })

    async def _handle_watch_set(self, request):
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
        var_names = data.get("variables", [])
        periph_names = data.get("peripherals", [])

        elf_vars = self._app.get("elf_variables", [])
        svd_peripherals = self._app.get("svd_peripherals", [])

        var_map = {v["name"]: v for v in elf_vars}
        watch_vars = []
        for name in var_names:
            # Support array[index] syntax: PC_send1[53] → read single byte at base+53
            import re
            m = re.match(r"^(.+)\[(\d+)\]$", name)
            if m:
                base_name, offset = m.group(1), int(m.group(2))
                if base_name in var_map:
                    v = var_map[base_name]
                    if offset < v["size"]:
                        watch_vars.append({
                            "name": f"{base_name}[{offset}]",
                            "address": v["address"] + offset,
                            "size": 1,
                            "type": "u8",
                        })
                continue

            if name in var_map:
                v = var_map[name]
                watch_vars.append({"name": name, "address": v["address"], "size": v["size"], "type": v["type"]})

        periph_map = {p["name"]: p for p in svd_peripherals}
        watch_periphs = []
        for name in periph_names:
            if isinstance(name, dict):
                watch_periphs.append(name)
            elif name in periph_map:
                watch_periphs.append(periph_map[name])

        self._poller.set_watch_list(watch_vars, watch_periphs)
        return web.json_response({"ok": True, "count": len(watch_vars) + len(watch_periphs)})

    async def _handle_watch_get(self, request):
        vars_list, periph_list = self._poller.get_watch_list()
        return web.json_response({
            "variables": [{"name": v["name"], "address": v["address"], "size": v["size"], "type": v["type"]}
                           for v in vars_list],
            "peripherals": periph_list,
        })

    async def _handle_snapshot(self, request):
        return web.json_response(self._poller.get_snapshot())

    # ---- SSE Stream ----
    async def _handle_stream(self, request):
        resp = web.StreamResponse(
            status=200, reason="OK",
            headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache", "Connection": "keep-alive"},
        )
        await resp.prepare(request)
        self._sse_clients.add(resp)

        try:
            last_ts = 0
            while self._probe_attached:
                snapshot = self._poller.get_snapshot()
                ts = snapshot["timestamp"]
                if ts != last_ts:
                    last_ts = ts
                    await resp.write(f"data: {json.dumps(snapshot)}\n\n".encode())
                await asyncio.sleep(0.05)
        except (ConnectionResetError, ConnectionAbortedError, asyncio.CancelledError):
            pass
        finally:
            self._sse_clients.discard(resp)
            if not self._sse_clients:
                self._last_client_disconnect = time.time()
                self._start_auto_detach_timer()
        return resp

    def _start_auto_detach_timer(self):
        """Start timer to auto-detach probe when no clients are connected."""
        if self._auto_detach_task and not self._auto_detach_task.done():
            self._auto_detach_task.cancel()
        self._auto_detach_task = asyncio.get_event_loop().create_task(self._auto_detach_after_timeout())

    async def _auto_detach_after_timeout(self):
        await asyncio.sleep(PROBE_IDLE_TIMEOUT)
        if not self._sse_clients and self._probe_attached:
            log.info("No SSE clients for %ds, auto-detaching probe", PROBE_IDLE_TIMEOUT)
            await self._do_detach()

    # ---- Probe lifecycle ----
    async def _handle_detach(self, request):
        """Release probe but keep HTTP server running."""
        try:
            await self._do_detach()
            return web.json_response({
                "ok": True,
                "exported": "snapshot.json",
                "message": "Probe released. Use /read-var in Claude Code, then click Reconnect.",
            })
        except Exception as e:
            log.error("Detach failed: %s", e)
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def _handle_attach(self, request):
        """Reconnect probe and resume monitoring."""
        try:
            await self._do_attach()
            return web.json_response({"ok": True, "message": "Probe reconnected"})
        except Exception as e:
            log.error("Attach failed: %s", e)
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def _do_detach(self):
        """Release probe."""
        self._probe_attached = False
        self._poller.export_snapshot_file("snapshot.json")
        self._poller.stop()
        if self._session:
            try:
                self._session.close()
            except Exception:
                log.debug("Error closing session", exc_info=True)
        log.info("Probe detached")

    async def _do_attach(self):
        """Reconnect probe."""
        import sys, os, time as _time
        # Kill stale pyocd
        if sys.platform == "win32":
            os.system("powershell -Command \"Get-Process pyocd -ErrorAction SilentlyContinue | Stop-Process -Force\" 2>NUL")
        else:
            os.system("pkill -f pyocd 2>/dev/null || true")
        _time.sleep(1.0)

        self._session = self._session_factory()
        self._session.open()
        self._poller._session = self._session
        self._poller.start()
        self._probe_attached = True
        log.info("Probe reconnected")

    async def _handle_status(self, request):
        return web.json_response({
            "probe_attached": self._probe_attached,
            "clients": len(self._sse_clients),
            "paused": getattr(self._poller, '_paused', False),
        })

    # ---- Utilities ----
    async def _handle_poll_rate(self, request):
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
        ms = data.get("interval_ms", 1000)
        self._poller.set_interval(ms)
        return web.json_response({"ok": True, "interval_ms": ms})

    async def _handle_pause(self, request):
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)
        paused = data.get("paused", False)
        if paused:
            self._poller.pause()
        else:
            self._poller.resume()
        return web.json_response({"ok": True, "paused": paused})

    async def _handle_export(self, request):
        try:
            self._poller.export_snapshot_file("snapshot.json")
            return web.json_response({"ok": True, "exported": "snapshot.json"})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    # ---- Server lifecycle ----
    async def start(self):
        runner = web.AppRunner(self._app)
        await runner.setup()
        site = web.TCPSite(runner, "localhost", self._port)
        await site.start()
        log.info(f"Web interface: http://localhost:{self._port}")
        return runner

    def set_variable_data(self, elf_vars: list[dict], svd_peripherals: list[dict]):
        self._app["elf_variables"] = elf_vars
        self._app["svd_peripherals"] = svd_peripherals
