"""Bounded command-line entry point for the Monitor service."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import secrets
import sys
import webbrowser
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TextIO

from .models import MonitorConfig
from .runtime import MonitorRuntime, MonitorRuntimeError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stm32-monitor")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="start the authenticated monitor service")
    serve.add_argument("--project", required=True)
    serve.add_argument("--data-root", required=True)
    serve.add_argument("--session-id", required=True)
    serve.add_argument("--serve-ui", action="store_true")
    serve.add_argument("--json", action="store_true", required=True)
    open_command = commands.add_parser(
        "open", help="start the monitor service and open its UI in a browser"
    )
    open_command.add_argument("--project", required=True)
    open_command.add_argument("--data-root", required=True)
    open_command.add_argument("--session-id")
    return parser


async def _serve(config: MonitorConfig, runtime: object, stdout: TextIO) -> int:
    endpoint = await runtime.start(config)
    try:
        payload = {
            "ok": True,
            "endpoint": {
                "url": endpoint.url,
                "accessUrl": endpoint.access_url
                if hasattr(endpoint, "access_url")
                else f"{endpoint.url}/#token={endpoint.token}",
                "monitorVersion": endpoint.monitor_version,
            },
        }
        stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
        stdout.flush()
        await runtime.wait_closed()
        return 0
    finally:
        await runtime.stop()


async def _open(
    config: MonitorConfig,
    runtime: object,
    browser_open: Callable[[str], bool],
) -> int:
    endpoint = await runtime.start(config)
    try:
        access_url = getattr(endpoint, "access_url", None)
        if not isinstance(access_url, str) or not access_url:
            raise MonitorRuntimeError(
                "MONITOR_SERVICE_UNAVAILABLE", "Monitor Service is unavailable"
            )
        if browser_open(access_url) is not True:
            raise MonitorRuntimeError(
                "MONITOR_BROWSER_FAILED", "Monitor browser handoff failed"
            )
        await runtime.wait_closed()
        return 0
    finally:
        await runtime.stop()


def main(
    argv: Sequence[str] | None = None,
    *,
    _runtime_factory: Callable[..., object] = MonitorRuntime,
    _browser_open: Callable[[str], bool] = lambda url: webbrowser.open(url),
    _stdout: TextIO = sys.stdout,
    _stderr: TextIO = sys.stderr,
) -> int:
    parser = _parser()
    with contextlib.redirect_stderr(_stderr):
        arguments = parser.parse_args(list(argv) if argv is not None else None)
    assert arguments.command in {"serve", "open"}
    try:
        config = MonitorConfig(
            Path(arguments.project).expanduser().absolute(),
            Path(arguments.data_root).expanduser().absolute(),
            _session_id(arguments.session_id),
        )
        serve_ui = (
            bool(arguments.serve_ui)
            if arguments.command == "serve"
            else True
        )
        try:
            runtime: object = _runtime_factory(serve_ui=serve_ui)
        except TypeError:
            runtime = _runtime_factory()
        if arguments.command == "serve":
            return asyncio.run(_serve(config, runtime, _stdout))
        return asyncio.run(_open(config, runtime, _browser_open))
    except KeyboardInterrupt:
        return 130
    except MonitorRuntimeError as error:
        code, message = error.code, error.message
        _stdout.write(
            json.dumps(
                {"ok": False, "code": code, "message": message},
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        _stdout.flush()
        return 1
    except (OSError, RuntimeError, TypeError, ValueError):
        _stdout.write(
            json.dumps(
                {
                    "ok": False,
                    "code": "MONITOR_INPUT_INVALID",
                    "message": "Monitor service failed",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        _stdout.flush()
        return 1


def _session_id(value: str | None) -> str:
    return value if value is not None else "monitor-" + secrets.token_hex(16)


__all__ = ["main"]
