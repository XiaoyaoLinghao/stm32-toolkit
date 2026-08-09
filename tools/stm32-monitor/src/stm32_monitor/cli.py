"""Bounded command-line entry point for the Monitor service."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys
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
    serve.add_argument("--json", action="store_true", required=True)
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


def main(
    argv: Sequence[str] | None = None,
    *,
    _runtime_factory: Callable[[], object] = MonitorRuntime,
    _stdout: TextIO = sys.stdout,
    _stderr: TextIO = sys.stderr,
) -> int:
    parser = _parser()
    with contextlib.redirect_stderr(_stderr):
        arguments = parser.parse_args(list(argv) if argv is not None else None)
    assert arguments.command == "serve"
    try:
        config = MonitorConfig(
            Path(arguments.project).expanduser().absolute(),
            Path(arguments.data_root).expanduser().absolute(),
            arguments.session_id,
        )
        return asyncio.run(_serve(config, _runtime_factory(), _stdout))
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


__all__ = ["main"]
