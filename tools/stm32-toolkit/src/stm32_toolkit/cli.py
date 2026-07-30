from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from stm32_toolkit.context import build_project_context
from stm32_toolkit.detection import detect_project
from stm32_toolkit.doctor import run_doctor
from stm32_toolkit.result import OperationResult


_VERSION = "0.2.0"


def main(argv: list[str] | None = None) -> int:
    """Run the command-line interface without changing the process directory."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "version":
        print(_VERSION)
        return 0

    project_root = getattr(args, "project_root", Path.cwd())
    try:
        result = _operation_result(args, project_root)
        _write_json(result)
    except Exception as error:
        print(f"stm32-toolkit: internal error: {error}", file=sys.stderr)
        return 1

    return 0 if result.ok else 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stm32-toolkit")
    _add_project_root(parser)
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("version")

    doctor = commands.add_parser("doctor")
    _add_project_root(doctor)
    _add_json(doctor)

    project = commands.add_parser("project")
    _add_project_root(project)
    project_commands = project.add_subparsers(dest="project_command", required=True)

    detect = project_commands.add_parser("detect")
    _add_project_root(detect)
    _add_json(detect)

    context = project_commands.add_parser("context")
    _add_project_root(context)
    context.add_argument("--data-root", required=True, type=Path)
    context.add_argument("--session-id", required=True)
    _add_json(context)
    return parser


def _add_project_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-root", type=Path, default=argparse.SUPPRESS)


def _add_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", required=True)


def _operation_result(args: argparse.Namespace, project_root: Path) -> OperationResult[dict[str, object]]:
    if args.command == "doctor":
        return run_doctor(project_root)
    if args.project_command == "detect":
        return _detect_result(project_root)
    return build_project_context(project_root, args.data_root, args.session_id)


def _detect_result(project_root: Path) -> OperationResult[dict[str, object]]:
    try:
        detection = detect_project(project_root)
    except (OSError, ValueError):
        return OperationResult.failure(
            "project.detect",
            "PROJECT_DETECTION_UNAVAILABLE",
            "Project detection is not available",
            {"path": str(project_root)},
        )
    return OperationResult.success("project.detect", detection.to_dict())


def _write_json(result: OperationResult[object]) -> None:
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
