from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import stat
import sys
import unicodedata
from pathlib import Path


class _RejectDuplicate(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is not None:
            parser.error(f"argument {option_string}: repeated option")
        setattr(namespace, self.dest, values)

from stm32_toolkit.context import build_project_context
from stm32_toolkit.creation_workflows import CreationPlanWorkflowRequest, plan_creation_workflow
from stm32_toolkit.detection import detect_project
from stm32_toolkit.diagnostic_workflows import (
    DiagnosticWorkflowContext,
    diagnostic_add_hypothesis,
    diagnostic_add_plan,
    diagnostic_assess_hypothesis,
    diagnostic_add_verification_plan,
    diagnostic_begin,
    diagnostic_attach_marker,
    diagnostic_complete_verification,
    diagnostic_declare_source_change,
    diagnostic_run_plan,
    diagnostic_show,
    diagnostic_show_verification,
    diagnostic_start,
    diagnostic_start_verification,
)
from stm32_toolkit.doctor import run_doctor
from stm32_toolkit.tool_support import SupportProfileRequest, discover_tool_support
from stm32_toolkit.hardware_workflows import (
    FaultWorkflowRequest,
    FlashWorkflowRequest,
    HandoffBeginWorkflowRequest,
    HandoffEndWorkflowRequest,
    ProbeListWorkflowRequest,
    RegisterReadWorkflowRequest,
    VariableReadWorkflowRequest,
    VariableSampleWorkflowRequest,
    fault_workflow,
    flash_workflow,
    handoff_begin_workflow,
    handoff_end_workflow,
    probe_list_workflow,
    register_read_workflow,
    variable_read_workflow,
    variable_sample_workflow,
)
from stm32_toolkit.result import OperationResult
from stm32_toolkit.testing_workflows import (
    TestingWorkflowContext,
    host_test_discover,
    host_test_run,
    target_test_prepare,
    target_test_execute,
    target_replay_run,
    test_show,
)
from stm32_toolkit.workflows import (
    build_firmware_workflow,
    configure_project_workflow,
    convert_keil_workflow,
    inspect_keil_workflow,
)


_VERSION = "0.5.0"
_STDERR_LIMIT = 500
_HARDWARE_COMMANDS = frozenset({"probe", "flash", "debug", "read", "fault"})
_TEST_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_DIAGNOSTIC_OPERATION_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_DIAGNOSTIC_SESSION_ID = re.compile(r"^[0-9a-f]{32}$")
_DIAGNOSTIC_RUN_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_DIAGNOSTIC_PLAN_ID = re.compile(r"^[0-9a-f]{64}$")
_DIAGNOSTIC_ACTORS = ("user", "tool", "ai-client")
_DIAGNOSTIC_MAX_BYTES = 64 * 1024
_STEPS_FILE_MAX_BYTES = 1024 * 1024
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class _SafeArgumentParser(argparse.ArgumentParser):
    """Argparse contract that never echoes caller values on grammar errors."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        kwargs.setdefault("allow_abbrev", False)
        super().__init__(*args, **kwargs)

    def error(self, message: str) -> None:
        self.exit(2, f"{self.prog}: invalid arguments\n")


class _StepsFileError(Exception):
    """Raised when a steps file cannot be safely loaded for the CLI."""


class _StepsFileAction(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Path,
        option_string: str | None = None,
    ) -> None:
        if getattr(namespace, "_steps_file_seen", False):
            parser.error("duplicate steps file")
        try:
            decoded = _read_steps_file(Path(values))
        except _StepsFileError:
            parser.error("invalid steps file")
        setattr(namespace, self.dest, decoded)
        setattr(namespace, "_steps_file_seen", True)


class _UniqueCaseAction(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str,
        option_string: str | None = None,
    ) -> None:
        current = tuple(getattr(namespace, self.dest, ()) or ())
        if values in current:
            parser.error("duplicate test case")
        setattr(namespace, self.dest, (*current, values))


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
    hardware = args.command in _HARDWARE_COMMANDS or getattr(args, "operation", "") in {
        "test.target.prepare", "test.target.execute"
    }
    try:
        result = (
            asyncio.run(_hardware_operation_result(args, project_root))
            if hardware
            else _operation_result(args, project_root)
        )
        _write_json(result)
    except Exception as error:
        if hardware:
            result = OperationResult.failure(
                _hardware_operation_name(args),
                "HARDWARE_INTERNAL_ERROR",
                "Hardware command failed",
                {},
            )
            _write_json(result)
            return 2
        message = str(error)
        if len(message) > _STDERR_LIMIT:
            message = message[:_STDERR_LIMIT] + "..."
        print(f"stm32-toolkit: internal error: {message}", file=sys.stderr)
        return 1

    return 0 if result.ok else 2


def _build_parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(prog="stm32-toolkit")
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

    create_plan = project_commands.add_parser("create-plan")
    _add_project_root(create_plan)
    create_plan.add_argument("--source-kind", choices=("mcu", "board", "ioc"), required=True, action=_RejectDuplicate)
    create_plan.add_argument("--source", required=True, action=_RejectDuplicate)
    create_plan.add_argument("--destination", required=True, action=_RejectDuplicate)
    create_plan.add_argument("--framework", choices=("hal", "ll"), required=True, action=_RejectDuplicate)
    create_plan.add_argument("--language", choices=("c", "cpp"), required=True, action=_RejectDuplicate)
    create_plan.add_argument("--support-profile", type=Path, action=_RejectDuplicate)
    _add_json(create_plan)

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

    probe = commands.add_parser("probe")
    probe_commands = probe.add_subparsers(dest="probe_command", required=True)
    probe_list = probe_commands.add_parser("list")
    _add_hardware_context(probe_list)

    flash = commands.add_parser("flash")
    _add_hardware_context(flash, probe=True, pins=True)
    flash.add_argument("--authorized", action="store_true")

    debug = commands.add_parser("debug")
    debug_commands = debug.add_subparsers(dest="debug_command", required=True)
    handoff = debug_commands.add_parser("handoff")
    handoff_commands = handoff.add_subparsers(dest="handoff_command", required=True)

    handoff_begin = handoff_commands.add_parser("begin")
    _add_hardware_context(handoff_begin, probe=True, pins=True)
    handoff_begin.add_argument("--authorized", action="store_true")
    handoff_begin.add_argument("--watch", action="append", default=[])

    handoff_end = handoff_commands.add_parser("end")
    _add_hardware_context(handoff_end, probe=True)
    handoff_end.add_argument("--ticket", required=True)

    read = commands.add_parser("read")
    read_commands = read.add_subparsers(dest="read_command", required=True)

    variable = read_commands.add_parser("variable")
    _add_hardware_context(variable, probe=True, pins=True)
    variable.add_argument("--expression", action="append", required=True)

    sample = read_commands.add_parser("sample")
    _add_hardware_context(sample, probe=True, pins=True)
    sample.add_argument("--expression", action="append", required=True)
    sample.add_argument("--interval-ms", required=True, type=_bounded_int(1, 3_600_000))
    sample.add_argument("--count", type=_bounded_int(1, 10_000))
    sample.add_argument("--duration-ms", type=_bounded_int(1, 3_600_000))

    register = read_commands.add_parser("register")
    _add_hardware_context(register, probe=True, pins=True)
    register.add_argument("--path", action="append", required=True)
    register.add_argument("--acknowledge-access-risk", action="store_true")

    fault = commands.add_parser("fault")
    _add_hardware_context(fault, probe=True, pins=True)

    test = commands.add_parser("test")
    test_commands = test.add_subparsers(dest="test_command", required=True)

    discover = test_commands.add_parser("discover")
    discover.set_defaults(operation="test.host.discover")
    _add_testing_context(discover)
    discover.add_argument("--mode", choices=["host"], required=True)

    run = test_commands.add_parser("run")
    run.set_defaults(operation="test.host.run")
    _add_testing_context(run)
    run.add_argument("--mode", choices=["host"], required=True)
    run.add_argument("--inventory-digest", required=True, type=_testing_digest)
    run.add_argument(
        "--case",
        dest="case_ids",
        action=_UniqueCaseAction,
        default=(),
    )

    show = test_commands.add_parser("show")
    show.set_defaults(operation="test.show")
    _add_testing_context(show)
    show.add_argument("run_id")

    replay = test_commands.add_parser("replay")
    replay.set_defaults(operation="test.target.replay")
    _add_testing_context(replay)
    replay.add_argument("--operation-id", required=True, type=_diagnostic_operation_id)
    replay.add_argument("--descriptor-file", required=True, type=Path)
    replay.add_argument("--stream-file", required=True, type=Path)

    target = test_commands.add_parser("target")
    target_commands = target.add_subparsers(dest="target_command", required=True)
    target_prepare = target_commands.add_parser("prepare")
    target_prepare.set_defaults(operation="test.target.prepare")
    _add_testing_context(target_prepare)
    target_prepare.add_argument("--probe-id", dest="probe_id", required=True)
    target_prepare.add_argument(
        "--case-id", dest="case_ids", action=_UniqueCaseAction, required=True, default=()
    )
    target_execute = target_commands.add_parser("execute")
    target_execute.set_defaults(operation="test.target.execute")
    _add_testing_context(target_execute)
    target_execute.add_argument("--probe-id", dest="probe_id", required=True)
    target_execute.add_argument(
        "--authorized-action-digest", required=True, type=_testing_digest
    )

    diagnose = commands.add_parser("diagnose")
    diagnose_commands = diagnose.add_subparsers(
        dest="diagnose_command", required=True
    )

    diagnostic_start = diagnose_commands.add_parser("start")
    diagnostic_start.set_defaults(operation="diagnostic.start")
    diagnostic_start.add_argument("failed_test_run_id", type=_diagnostic_run_id)
    diagnostic_start.add_argument(
        "--operation-id", required=True, type=_diagnostic_operation_id
    )
    diagnostic_start.add_argument(
        "--failed-run-mode", choices=("host", "target"), default="host"
    )
    diagnostic_start.add_argument(
        "--actor", choices=_DIAGNOSTIC_ACTORS, default="user"
    )
    _add_testing_context(diagnostic_start)

    diagnostic_show = diagnose_commands.add_parser("show")
    diagnostic_show.set_defaults(operation="diagnostic.show")
    diagnostic_show.add_argument(
        "diagnostic_session_id", type=_diagnostic_session_id
    )
    _add_testing_context(diagnostic_show)

    diagnostic_begin = diagnose_commands.add_parser("begin")
    diagnostic_begin.set_defaults(operation="diagnostic.begin")
    diagnostic_begin.add_argument(
        "diagnostic_session_id", type=_diagnostic_session_id
    )
    diagnostic_begin.add_argument(
        "--operation-id", required=True, type=_diagnostic_operation_id
    )
    diagnostic_begin.add_argument(
        "--expected-revision",
        required=True,
        type=_bounded_int(0, 10_000),
    )
    diagnostic_begin.add_argument(
        "--actor", choices=_DIAGNOSTIC_ACTORS, default="user"
    )
    _add_testing_context(diagnostic_begin)

    hypothesis = diagnose_commands.add_parser("hypothesis")
    hypothesis_commands = hypothesis.add_subparsers(
        dest="hypothesis_command", required=True
    )

    hypothesis_add = hypothesis_commands.add_parser("add")
    hypothesis_add.set_defaults(operation="diagnostic.hypothesis.add")
    hypothesis_add.add_argument(
        "diagnostic_session_id", type=_diagnostic_session_id
    )
    hypothesis_add.add_argument(
        "--operation-id", required=True, type=_diagnostic_operation_id
    )
    hypothesis_add.add_argument(
        "--expected-revision",
        required=True,
        type=_bounded_int(0, 10_000),
    )
    hypothesis_add.add_argument("--statement", required=True, type=_diagnostic_text)
    hypothesis_add.add_argument(
        "--actor", choices=_DIAGNOSTIC_ACTORS, default="user"
    )
    _add_testing_context(hypothesis_add)

    hypothesis_assess = hypothesis_commands.add_parser("assess")
    hypothesis_assess.set_defaults(operation="diagnostic.hypothesis.assess")
    hypothesis_assess.add_argument(
        "diagnostic_session_id", type=_diagnostic_session_id
    )
    hypothesis_assess.add_argument(
        "--operation-id", required=True, type=_diagnostic_operation_id
    )
    hypothesis_assess.add_argument(
        "--expected-revision",
        required=True,
        type=_bounded_int(0, 10_000),
    )
    hypothesis_assess.add_argument(
        "--hypothesis-id", required=True, type=_diagnostic_session_id
    )
    hypothesis_assess.add_argument(
        "--plan-id", required=True, type=_diagnostic_plan_id
    )
    hypothesis_assess.add_argument(
        "--step-id", required=True, type=_diagnostic_operation_id
    )
    hypothesis_assess.add_argument(
        "--polarity", required=True, choices=["supports", "refutes"]
    )
    hypothesis_assess.add_argument(
        "--rationale", required=True, type=_diagnostic_text
    )
    hypothesis_assess.add_argument(
        "--actor", choices=_DIAGNOSTIC_ACTORS, default="user"
    )
    _add_testing_context(hypothesis_assess)

    plan = diagnose_commands.add_parser("plan")
    plan_commands = plan.add_subparsers(dest="plan_command", required=True)

    plan_add = plan_commands.add_parser("add")
    plan_add.set_defaults(operation="diagnostic.plan.add")
    plan_add.add_argument("diagnostic_session_id", type=_diagnostic_session_id)
    plan_add.add_argument(
        "--operation-id", required=True, type=_diagnostic_operation_id
    )
    plan_add.add_argument(
        "--expected-revision",
        required=True,
        type=_bounded_int(0, 10_000),
    )
    plan_add.add_argument(
        "--steps-file",
        dest="steps",
        required=True,
        type=Path,
        action=_StepsFileAction,
    )
    plan_add.add_argument(
        "--actor", choices=_DIAGNOSTIC_ACTORS, default="user"
    )
    _add_testing_context(plan_add)

    plan_run = plan_commands.add_parser("run")
    plan_run.set_defaults(operation="diagnostic.plan.run")
    plan_run.add_argument("diagnostic_session_id", type=_diagnostic_session_id)
    plan_run.add_argument(
        "--operation-id", required=True, type=_diagnostic_operation_id
    )
    plan_run.add_argument(
        "--expected-revision",
        required=True,
        type=_bounded_int(0, 10_000),
    )
    plan_run.add_argument("--plan-id", required=True, type=_diagnostic_plan_id)
    plan_run.add_argument(
        "--actor", choices=_DIAGNOSTIC_ACTORS, default="tool"
    )
    _add_testing_context(plan_run)

    source_change = diagnose_commands.add_parser("source-change")
    source_change_commands = source_change.add_subparsers(
        dest="source_change_command", required=True
    )
    source_change_declare = source_change_commands.add_parser("declare")
    source_change_declare.set_defaults(operation="diagnostic.source-change.declare")
    source_change_declare.add_argument(
        "diagnostic_session_id", type=_diagnostic_session_id
    )
    source_change_declare.add_argument(
        "--operation-id", required=True, type=_diagnostic_operation_id
    )
    source_change_declare.add_argument(
        "--expected-revision", required=True, type=_bounded_int(0, 10_000)
    )
    source_change_declare.add_argument(
        "--declaration-file", required=True, type=Path, action=_StepsFileAction
    )
    source_change_declare.add_argument(
        "--actor", choices=_DIAGNOSTIC_ACTORS, default="user"
    )
    _add_diagnostic_tool_context(source_change_declare)

    verification_plan = diagnose_commands.add_parser("verification-plan")
    verification_plan_commands = verification_plan.add_subparsers(
        dest="verification_plan_command", required=True
    )
    verification_plan_add = verification_plan_commands.add_parser("add")
    verification_plan_add.set_defaults(operation="diagnostic.verification-plan.add")
    verification_plan_add.add_argument(
        "diagnostic_session_id", type=_diagnostic_session_id
    )
    verification_plan_add.add_argument(
        "--operation-id", required=True, type=_diagnostic_operation_id
    )
    verification_plan_add.add_argument(
        "--expected-revision", required=True, type=_bounded_int(0, 10_000)
    )
    verification_plan_add.add_argument(
        "--plan-file", required=True, type=Path, action=_StepsFileAction
    )
    verification_plan_add.add_argument(
        "--actor", choices=_DIAGNOSTIC_ACTORS, default="user"
    )
    _add_diagnostic_tool_context(verification_plan_add)

    verification = diagnose_commands.add_parser("verification")
    verification_commands = verification.add_subparsers(
        dest="verification_command", required=True
    )
    verification_start = verification_commands.add_parser("start")
    verification_start.set_defaults(operation="diagnostic.verification.start")
    verification_start.add_argument(
        "diagnostic_session_id", type=_diagnostic_session_id
    )
    verification_start.add_argument(
        "--operation-id", required=True, type=_diagnostic_operation_id
    )
    verification_start.add_argument(
        "--expected-revision", required=True, type=_bounded_int(0, 10_000)
    )
    verification_start.add_argument(
        "--verification-plan-id", required=True, type=_diagnostic_plan_id
    )
    verification_start.add_argument(
        "--actor", choices=_DIAGNOSTIC_ACTORS, default="tool"
    )
    _add_diagnostic_tool_context(verification_start)

    verification_complete = verification_commands.add_parser("complete")
    verification_complete.set_defaults(operation="diagnostic.verification.complete")
    verification_complete.add_argument(
        "diagnostic_session_id", type=_diagnostic_session_id
    )
    verification_complete.add_argument(
        "--operation-id", required=True, type=_diagnostic_operation_id
    )
    verification_complete.add_argument(
        "--expected-revision", required=True, type=_bounded_int(0, 10_000)
    )
    verification_complete.add_argument(
        "--executed-operation-id",
        dest="executed_operation_ids",
        action="append",
        required=True,
        type=_diagnostic_operation_id,
    )
    verification_complete.add_argument("--cancelled", action="store_true")
    verification_complete.add_argument(
        "--actor", choices=_DIAGNOSTIC_ACTORS, default="tool"
    )
    _add_diagnostic_tool_context(verification_complete)

    verification_show = verification_commands.add_parser("show")
    verification_show.set_defaults(operation="diagnostic.verification.show")
    verification_show.add_argument(
        "diagnostic_session_id", type=_diagnostic_session_id
    )
    _add_diagnostic_tool_context(verification_show)

    marker = diagnose_commands.add_parser("marker")
    marker_commands = marker.add_subparsers(dest="marker_command", required=True)
    marker_attach = marker_commands.add_parser("attach")
    marker_attach.set_defaults(operation="diagnostic.marker.attach")
    marker_attach.add_argument("diagnostic_session_id", type=_diagnostic_session_id)
    marker_attach.add_argument(
        "--operation-id", required=True, type=_diagnostic_operation_id
    )
    marker_attach.add_argument(
        "--expected-revision", required=True, type=_bounded_int(0, 10_000)
    )
    marker_attach.add_argument(
        "--marker-file", required=True, type=Path, action=_StepsFileAction
    )
    marker_attach.add_argument("--actor", choices=_DIAGNOSTIC_ACTORS, default="tool")
    _add_diagnostic_tool_context(marker_attach)

    return parser


def _add_project_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-root", type=Path, default=argparse.SUPPRESS, action=_RejectDuplicate)


def _add_workflow_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project",
        "--project-root",
        dest="project_root",
        type=Path,
        default=argparse.SUPPRESS,
    )


def _add_hardware_context(
    parser: argparse.ArgumentParser,
    *,
    probe: bool = False,
    pins: bool = False,
) -> None:
    parser.add_argument(
        "--project",
        "--project-root",
        dest="project_root",
        required=True,
        type=Path,
    )
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--session-id", required=True)
    if probe:
        parser.add_argument("--probe", required=True)
    if pins:
        parser.add_argument("--expected-build-id", required=True)
        parser.add_argument("--expected-elf-sha256", required=True)
    parser.add_argument("--json", action="store_true")


def _add_testing_context(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project",
        "--project-root",
        dest="project_root",
        required=True,
        type=Path,
    )
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--json", action="store_true")


def _add_diagnostic_tool_context(parser: argparse.ArgumentParser) -> None:
    """Add the explicit Toolkit-session roots used by verification callers."""
    parser.add_argument(
        "--project",
        "--project-root",
        dest="project_root",
        required=True,
        type=Path,
    )
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument(
        "--tool-session-id",
        "--session-id",
        dest="session_id",
        required=True,
    )
    parser.add_argument("--json", action="store_true")


def _testing_digest(value: str) -> str:
    if _TEST_DIGEST.fullmatch(value) is None:
        raise argparse.ArgumentTypeError("invalid inventory digest")
    return value


def _diagnostic_operation_id(value: str) -> str:
    if _DIAGNOSTIC_OPERATION_ID.fullmatch(value) is None:
        raise argparse.ArgumentTypeError("invalid diagnostic operation id")
    return value


def _diagnostic_session_id(value: str) -> str:
    if _DIAGNOSTIC_SESSION_ID.fullmatch(value) is None:
        raise argparse.ArgumentTypeError("invalid diagnostic session id")
    return value


def _diagnostic_run_id(value: str) -> str:
    try:
        within_limit = len(value.encode("utf-8")) <= _DIAGNOSTIC_MAX_BYTES
    except UnicodeEncodeError:
        within_limit = False
    if not within_limit or _DIAGNOSTIC_RUN_ID.fullmatch(value) is None:
        raise argparse.ArgumentTypeError("invalid failed test run id")
    return value


def _diagnostic_plan_id(value: str) -> str:
    if _DIAGNOSTIC_PLAN_ID.fullmatch(value) is None:
        raise argparse.ArgumentTypeError("invalid diagnostic plan id")
    return value


def _diagnostic_text(value: str) -> str:
    if not value or unicodedata.normalize("NFC", value) != value:
        raise argparse.ArgumentTypeError("invalid diagnostic text")
    try:
        within_limit = len(value.encode("utf-8")) <= _DIAGNOSTIC_MAX_BYTES
    except UnicodeEncodeError:
        within_limit = False
    if not within_limit:
        raise argparse.ArgumentTypeError("invalid diagnostic text")
    return value


def _steps_file_is_reparse(info: object) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & _REPARSE_POINT)


def _steps_file_leaf_identity(info: object) -> tuple[object, ...]:
    mode = getattr(info, "st_mode")
    if (
        _steps_file_is_reparse(info)
        or stat.S_ISLNK(mode)
        or not stat.S_ISREG(mode)
        or getattr(info, "st_nlink") != 1
    ):
        raise _StepsFileError
    return (
        getattr(info, "st_dev"),
        getattr(info, "st_ino"),
        stat.S_IFMT(mode),
        getattr(info, "st_nlink"),
        getattr(info, "st_size"),
    )


def _steps_file_parent_identity(info: object) -> tuple[object, ...]:
    mode = getattr(info, "st_mode")
    if (
        _steps_file_is_reparse(info)
        or stat.S_ISLNK(mode)
        or not stat.S_ISDIR(mode)
    ):
        raise _StepsFileError
    return (
        getattr(info, "st_dev"),
        getattr(info, "st_ino"),
        stat.S_IFMT(mode),
    )


def _steps_file_parent_snapshot(path: Path) -> tuple[tuple[object, ...], ...]:
    snapshot: list[tuple[object, ...]] = []
    for parent in reversed(path.parents):
        snapshot.append(_steps_file_parent_identity(os.lstat(parent)))
    return tuple(snapshot)


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"invalid JSON constant: {value}")


def _read_steps_file(path: Path) -> object:
    """Read one bounded JSON value from a stable, non-link regular file."""
    fd = -1
    try:
        absolute = Path(os.path.abspath(os.fspath(path)))
        parents_before = _steps_file_parent_snapshot(absolute)
        leaf_before = _steps_file_leaf_identity(os.lstat(absolute))
        if leaf_before[-1] > _STEPS_FILE_MAX_BYTES:
            raise _StepsFileError

        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(os.fspath(absolute), flags)
        leaf_open = _steps_file_leaf_identity(os.fstat(fd))
        if leaf_open != leaf_before:
            raise _StepsFileError

        payload = bytearray()
        while len(payload) <= _STEPS_FILE_MAX_BYTES:
            remaining = _STEPS_FILE_MAX_BYTES + 1 - len(payload)
            chunk = os.read(fd, min(64 * 1024, remaining))
            if not chunk:
                break
            payload.extend(chunk)
            if len(payload) > _STEPS_FILE_MAX_BYTES:
                raise _StepsFileError

        leaf_after_fd = _steps_file_leaf_identity(os.fstat(fd))
        if leaf_after_fd != leaf_open:
            raise _StepsFileError
        leaf_after_named = _steps_file_leaf_identity(os.lstat(absolute))
        if leaf_after_named != leaf_before:
            raise _StepsFileError
        if _steps_file_parent_snapshot(absolute) != parents_before:
            raise _StepsFileError

        text = bytes(payload).decode("utf-8", errors="strict")
        return json.loads(text, parse_constant=_reject_json_constant)
    except _StepsFileError:
        raise
    except (OSError, TypeError, UnicodeError, ValueError, RecursionError):
        raise _StepsFileError from None
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                raise _StepsFileError from None


def _bounded_int(minimum: int, maximum: int):
    def convert(value: str) -> int:
        try:
            integer = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError("invalid integer") from None
        if not minimum <= integer <= maximum:
            raise argparse.ArgumentTypeError("integer outside allowed range")
        return integer

    return convert


def _add_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", required=True)


def _add_dry_run_apply(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")


def _validate_cli_modes(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Reject grammar violations that argparse cannot express alone."""
    if args.command == "test":
        return
    if args.command == "read" and args.read_command == "sample":
        if args.count is None and args.duration_ms is None:
            parser.error("sample requires --count or --duration-ms")
        return
    if args.command in _HARDWARE_COMMANDS:
        return
    apply_mode = getattr(args, "apply", False)
    authorized = getattr(args, "authorized", False)
    plan_id = getattr(args, "plan_id", None)
    if apply_mode and plan_id is None:
        parser.error("--apply requires --plan-id")
    if authorized and not apply_mode:
        parser.error("--authorized is valid only with --apply")
    if authorized and plan_id is None:
        parser.error("--authorized requires --plan-id")


def _hardware_operation_name(args: argparse.Namespace) -> str:
    if args.command == "test" and args.test_command == "target":
        return f"test.target.{args.target_command}"
    if args.command == "probe":
        return "stm32_probe_list"
    if args.command == "flash":
        return "stm32_flash"
    if args.command == "debug":
        return (
            "stm32_debug_handoff_begin"
            if args.handoff_command == "begin"
            else "stm32_debug_handoff_end"
        )
    if args.command == "read":
        return {
            "variable": "stm32_variable_read",
            "sample": "stm32_variable_sample",
            "register": "stm32_register_read",
        }[args.read_command]
    return "stm32_fault_analyze"


async def _hardware_operation_result(
    args: argparse.Namespace,
    project_root: Path,
) -> OperationResult[object]:
    if args.command == "test" and args.test_command == "target":
        context = TestingWorkflowContext(project_root, args.data_root, args.session_id)
        if args.target_command == "prepare":
            return await target_test_prepare(
                context, probe_id=args.probe_id, case_ids=args.case_ids
            )
        return await target_test_execute(
            context,
            probe_id=args.probe_id,
            authorized_action_digest=args.authorized_action_digest,
        )
    common = (project_root, args.data_root, args.session_id)
    if args.command == "probe":
        return await probe_list_workflow(ProbeListWorkflowRequest(*common))
    if args.command == "flash":
        return await flash_workflow(
            FlashWorkflowRequest(
                *common,
                args.probe,
                args.expected_build_id,
                args.expected_elf_sha256,
                args.authorized,
            )
        )
    if args.command == "debug":
        if args.handoff_command == "begin":
            return await handoff_begin_workflow(
                HandoffBeginWorkflowRequest(
                    *common,
                    args.probe,
                    args.expected_build_id,
                    args.expected_elf_sha256,
                    args.authorized,
                    tuple(args.watch),
                )
            )
        return await handoff_end_workflow(
            HandoffEndWorkflowRequest(*common, args.probe, args.ticket)
        )
    if args.command == "read":
        pins = (
            *common,
            args.probe,
            args.expected_build_id,
            args.expected_elf_sha256,
        )
        if args.read_command == "variable":
            return await variable_read_workflow(
                VariableReadWorkflowRequest(*pins, tuple(args.expression))
            )
        if args.read_command == "sample":
            return await variable_sample_workflow(
                VariableSampleWorkflowRequest(
                    *pins,
                    tuple(args.expression),
                    args.interval_ms,
                    args.count,
                    args.duration_ms,
                )
            )
        return await register_read_workflow(
            RegisterReadWorkflowRequest(
                *pins,
                tuple(args.path),
                args.acknowledge_access_risk,
            )
        )
    return await fault_workflow(
        FaultWorkflowRequest(
            *common,
            args.probe,
            args.expected_build_id,
            args.expected_elf_sha256,
        )
    )


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
        if args.project_command == "create-plan":
            data_root = getattr(args, "data_root", project_root / ".stm32-toolkit-data")
            try:
                support = discover_tool_support(
                    SupportProfileRequest(profile_path=args.support_profile, data_root=data_root),
                    probe_versions=True,
                )
            except (OSError, ValueError, RuntimeError):
                return OperationResult.failure(
                    "project-create-plan",
                    "CREATION_ENVIRONMENT_INVALID",
                    "Creation environment is unavailable",
                    {},
                )
            return plan_creation_workflow(
                CreationPlanWorkflowRequest(
                    project_root=project_root,
                    data_root=data_root,
                    session_id="cli",
                    source_kind=args.source_kind,
                    source_value=args.source,
                    destination=args.destination,
                    framework=args.framework,
                    language=args.language,
                ),
                support_profile=support,
            )
        return configure_project_workflow(
            project_root,
            plan_id=args.plan_id,
            authorized=args.authorized,
        )
    if args.command == "test":
        context = TestingWorkflowContext(
            project_root=project_root,
            data_root=args.data_root,
            session_id=args.session_id,
        )
        if args.test_command == "discover":
            return host_test_discover(context)
        if args.test_command == "run":
            return host_test_run(
                context,
                inventory_digest=args.inventory_digest,
                case_ids=args.case_ids,
            )
        if args.test_command == "replay":
            return target_replay_run(
                context,
                operation_id=args.operation_id,
                descriptor_file=args.descriptor_file,
                stream_file=args.stream_file,
            )
        return test_show(context, run_id=args.run_id)
    if args.command == "diagnose":
        context = DiagnosticWorkflowContext(
            project_root, args.data_root, args.session_id
        )
        if args.diagnose_command == "start":
            return diagnostic_start(
                context,
                operation_id=args.operation_id,
                failed_test_run_id=args.failed_test_run_id,
                **(
                    {"failed_run_mode": args.failed_run_mode}
                    if args.failed_run_mode == "target"
                    else {}
                ),
                actor=args.actor,
            )
        if args.diagnose_command == "show":
            return diagnostic_show(
                context,
                diagnostic_session_id=args.diagnostic_session_id,
            )
        if args.diagnose_command == "begin":
            return diagnostic_begin(
                context,
                operation_id=args.operation_id,
                diagnostic_session_id=args.diagnostic_session_id,
                expected_revision=args.expected_revision,
                actor=args.actor,
            )
        if args.diagnose_command == "plan":
            if args.plan_command == "add":
                return diagnostic_add_plan(
                    context,
                    operation_id=args.operation_id,
                    diagnostic_session_id=args.diagnostic_session_id,
                    expected_revision=args.expected_revision,
                    steps=args.steps,
                    actor=args.actor,
                )
            return diagnostic_run_plan(
                context,
                operation_id=args.operation_id,
                diagnostic_session_id=args.diagnostic_session_id,
                expected_revision=args.expected_revision,
                plan_id=args.plan_id,
                actor=args.actor,
            )
        if args.diagnose_command == "source-change":
            return diagnostic_declare_source_change(
                context,
                operation_id=args.operation_id,
                diagnostic_session_id=args.diagnostic_session_id,
                expected_revision=args.expected_revision,
                source_change_declaration=args.declaration_file,
                actor=args.actor,
            )
        if args.diagnose_command == "verification-plan":
            return diagnostic_add_verification_plan(
                context,
                operation_id=args.operation_id,
                diagnostic_session_id=args.diagnostic_session_id,
                expected_revision=args.expected_revision,
                verification_plan=args.plan_file,
                actor=args.actor,
            )
        if args.diagnose_command == "verification":
            if args.verification_command == "start":
                return diagnostic_start_verification(
                    context,
                    operation_id=args.operation_id,
                    diagnostic_session_id=args.diagnostic_session_id,
                    expected_revision=args.expected_revision,
                    verification_plan_id=args.verification_plan_id,
                    actor=args.actor,
                )
            if args.verification_command == "complete":
                return diagnostic_complete_verification(
                    context,
                    operation_id=args.operation_id,
                    diagnostic_session_id=args.diagnostic_session_id,
                    expected_revision=args.expected_revision,
                    executed_operation_ids=args.executed_operation_ids,
                    cancelled=args.cancelled,
                    actor=args.actor,
                )
            return diagnostic_show_verification(
                context,
                diagnostic_session_id=args.diagnostic_session_id,
            )
        if args.diagnose_command == "marker":
            return diagnostic_attach_marker(
                context,
                operation_id=args.operation_id,
                diagnostic_session_id=args.diagnostic_session_id,
                expected_revision=args.expected_revision,
                diagnostic_marker_ref=args.marker_file,
                actor=args.actor,
            )
        if args.hypothesis_command == "add":
            return diagnostic_add_hypothesis(
                context,
                operation_id=args.operation_id,
                diagnostic_session_id=args.diagnostic_session_id,
                expected_revision=args.expected_revision,
                statement=args.statement,
                actor=args.actor,
            )
        return diagnostic_assess_hypothesis(
            context,
            operation_id=args.operation_id,
            diagnostic_session_id=args.diagnostic_session_id,
            expected_revision=args.expected_revision,
            hypothesis_id=args.hypothesis_id,
            plan_id=args.plan_id,
            step_id=args.step_id,
            polarity=args.polarity,
            rationale=args.rationale,
            actor=args.actor,
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
