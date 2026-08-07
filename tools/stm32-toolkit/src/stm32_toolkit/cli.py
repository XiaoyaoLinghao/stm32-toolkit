from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from stm32_toolkit.context import build_project_context
from stm32_toolkit.detection import detect_project
from stm32_toolkit.doctor import run_doctor
from stm32_toolkit.result import OperationResult
from stm32_toolkit.workflows import (
    build_firmware_workflow,
    configure_project_workflow,
    convert_keil_workflow,
    inspect_keil_workflow,
)


_VERSION = "0.3.0"
_STDERR_LIMIT = 500


def main(argv: list[str] | None = None) -> int:
    """Run the command-line interface without changing the process directory."""
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
        _validate_cli_modes(parser, args)
    except SystemExit as error:
        # argparse reports grammar violations on stderr and exits 2; keep the
        # process contract while returning the code for in-process callers.
        return error.code if isinstance(error.code, int) else 2

    if args.command == "version":
        print(_VERSION)
        return 0

    project_root = getattr(args, "project_root", Path.cwd())
    try:
        result = _operation_result(args, project_root)
        _write_json(result)
    except Exception as error:
        message = str(error)
        if len(message) > _STDERR_LIMIT:
            message = message[:_STDERR_LIMIT] + "..."
        print(f"stm32-toolkit: internal error: {message}", file=sys.stderr)
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

    configure = project_commands.add_parser("configure")
    _add_workflow_root(configure)
    _add_json(configure)
    _add_dry_run_apply(configure)
    configure.add_argument("--plan-id")
    configure.add_argument("--authorized", action="store_true")

    keil = commands.add_parser("keil")
    _add_project_root(keil)
    keil_commands = keil.add_subparsers(dest="keil_command", required=True)

    inspect = keil_commands.add_parser("inspect")
    _add_workflow_root(inspect)
    _add_json(inspect)
    inspect.add_argument("--uvprojx")
    inspect.add_argument("--target-name")
    inspect.add_argument("--no-baseline", action="store_true")

    convert = keil_commands.add_parser("convert")
    _add_workflow_root(convert)
    _add_json(convert)
    convert.add_argument("--uvprojx")
    convert.add_argument("--target-name")
    _add_dry_run_apply(convert)
    convert.add_argument("--plan-id")
    convert.add_argument("--authorized", action="store_true")

    build = commands.add_parser("build")
    _add_workflow_root(build)
    build.add_argument(
        "--preset", required=True, choices=["arm-debug", "arm-release"]
    )
    build.add_argument("--clean", action="store_true")
    build.add_argument("--timeout-seconds", type=int, default=300)
    build.add_argument("--json", action="store_true")

    return parser


def _add_project_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-root", type=Path, default=argparse.SUPPRESS)


def _add_workflow_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project",
        "--project-root",
        dest="project_root",
        type=Path,
        default=argparse.SUPPRESS,
    )


def _add_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", required=True)


def _add_dry_run_apply(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")


def _validate_cli_modes(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Reject grammar violations that argparse cannot express alone."""
    apply_mode = getattr(args, "apply", False)
    authorized = getattr(args, "authorized", False)
    plan_id = getattr(args, "plan_id", None)
    if apply_mode and plan_id is None:
        parser.error("--apply requires --plan-id")
    if authorized and not apply_mode:
        parser.error("--authorized is valid only with --apply")
    if authorized and plan_id is None:
        parser.error("--authorized requires --plan-id")


def _operation_result(
    args: argparse.Namespace, project_root: Path
) -> OperationResult[object]:
    if args.command == "doctor":
        return run_doctor(project_root)
    if args.command == "keil":
        if args.keil_command == "inspect":
            return inspect_keil_workflow(
                project_root,
                uvprojx=args.uvprojx,
                target_name=args.target_name,
                include_baseline=not args.no_baseline,
            )
        return convert_keil_workflow(
            project_root,
            uvprojx=args.uvprojx,
            target_name=args.target_name,
            plan_id=args.plan_id,
            authorized=args.authorized,
        )
    if args.command == "project":
        if args.project_command == "detect":
            return _detect_result(project_root)
        if args.project_command == "context":
            return build_project_context(project_root, args.data_root, args.session_id)
        return configure_project_workflow(
            project_root,
            plan_id=args.plan_id,
            authorized=args.authorized,
        )
    if args.command == "build":
        # CLI invocation is the user's explicit process-level action.
        return build_firmware_workflow(
            project_root,
            preset=args.preset,
            clean=args.clean,
            timeout_seconds=args.timeout_seconds,
            authorized=True,
        )
    raise AssertionError(f"unhandled command {args.command}")


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
