"""Bounded command-line entry point for the Monitor service."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import errno
import json
import secrets
import sys
import webbrowser
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TextIO

from stm32_toolkit.diagnostics import SourceChangeDeclaration
from stm32_toolkit.evidence import EvidenceValidationError
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.project_model import ProjectManifestError, load_project_model

from .analysis import AnalysisError, AnalysisRequest
from .analysis_workflows import (
    ANALYSIS_WORKFLOW_INVALID,
    ENVIRONMENT_FAILURE,
    EVIDENCE_INTEGRITY_FAILURE,
    AnalysisPublication,
    AnalysisWorkflowError,
    compare_monitor_runs,
    export_analysis_bundle,
)
from .models import MonitorConfig
from .protocol import MAX_PROTOCOL_BYTES, ProtocolResult, ProtocolViolation, failure, parse_json_object, success
from .replay import (
    INCOMPATIBLE_IDENTITY,
    MONITOR_PHYSICAL_INVALID,
    MonitorReplayError,
    OPERATION_CONFLICT,
    canonical_replay_json_bytes,
    ingest_monitor_replay,
    publish_physical_monitor_run,
)
from .runtime import MonitorRuntime, MonitorRuntimeError


_ADAPTER_JSON_LIMIT = MAX_PROTOCOL_BYTES
_ADAPTER_CODES = frozenset(
    {
        ANALYSIS_WORKFLOW_INVALID,
        INCOMPATIBLE_IDENTITY,
        EVIDENCE_INTEGRITY_FAILURE,
        ENVIRONMENT_FAILURE,
        MONITOR_PHYSICAL_INVALID,
        OPERATION_CONFLICT,
    }
)


class _AdapterFailure(ValueError):
    def __init__(self, code: str, message: str) -> None:
        if code not in _ADAPTER_CODES or not message:
            raise ValueError("invalid adapter failure")
        super().__init__(message)
        self.code = code
        self.message = message


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

    replay = commands.add_parser("replay", help="import a Monitor replay")
    replay_commands = replay.add_subparsers(dest="replay_command", required=True)
    ingest = replay_commands.add_parser("ingest", help="ingest one replay document")
    _add_context_options(ingest, session_required=True)
    ingest.add_argument("--operation-id", required=True)
    ingest.add_argument("--document-file", required=True)
    ingest.add_argument("--json", action="store_true", required=True)
    ingest.set_defaults(adapter_operation="monitor.replay.ingest")

    physical = commands.add_parser("physical", help="publish a physical Monitor window")
    physical_commands = physical.add_subparsers(dest="physical_command", required=True)
    publish = physical_commands.add_parser("publish", help="publish one committed live window")
    _add_context_options(publish, session_required=True)
    publish.add_argument("--scenario-role", required=True)
    publish.add_argument("--test-run-id", required=True)
    publish.add_argument("--run-id", required=True)
    publish.add_argument("--group-id", required=True)
    publish.add_argument("--start-sequence", required=True, type=int)
    publish.add_argument("--end-sequence-exclusive", required=True, type=int)
    publish.add_argument("--start-captured-unix-ns", required=True, type=int)
    publish.add_argument("--end-captured-unix-ns-exclusive", required=True, type=int)
    publish.add_argument("--probe-id", required=True)
    publish.add_argument("--json", action="store_true", required=True)
    publish.set_defaults(adapter_operation="monitor.physical.publish")

    analysis = commands.add_parser("analysis", help="publish Monitor analysis")
    analysis_commands = analysis.add_subparsers(dest="analysis_command", required=True)
    compare = analysis_commands.add_parser("compare", help="compare two imported runs")
    _add_context_options(compare, session_required=True)
    compare.add_argument("--request-file", required=True)
    compare.add_argument("--diagnostic-session-id", required=True)
    compare.add_argument("--hypothesis-id", required=True)
    compare.add_argument("--polarity", required=True)
    compare.add_argument("--rationale", required=True)
    compare.add_argument("--source-change-file")
    compare.add_argument("--json", action="store_true", required=True)
    compare.set_defaults(adapter_operation="monitor.analysis.compare")

    bundle = analysis_commands.add_parser("bundle", help="export one analysis bundle")
    _add_context_options(bundle, session_required=True)
    bundle.add_argument("--request-file", required=True)
    bundle.add_argument("--publication-file", required=True)
    bundle.add_argument("--failed-before-test-run-id", required=True)
    bundle.add_argument("--fixed-after-test-run-id", required=True)
    bundle.add_argument("--source-change-file")
    bundle.add_argument("--json", action="store_true", required=True)
    bundle.set_defaults(adapter_operation="monitor.analysis.bundle")
    return parser


def _add_context_options(parser: argparse.ArgumentParser, *, session_required: bool) -> None:
    parser.add_argument("--project", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--session-id", required=session_required)


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
    if arguments.command in {"replay", "analysis", "physical"}:
        try:
            result = _run_adapter(arguments)
        except KeyboardInterrupt:
            return 130
        except BaseException as error:
            code, message = _adapter_error(
                error,
                adapter_operation=getattr(arguments, "adapter_operation", None),
            )
            result = failure(arguments.adapter_operation, code, message)
        _write_protocol_result(result, _stdout)
        return 0 if result.ok else 1
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


def _write_protocol_result(result: ProtocolResult[object], stdout: TextIO) -> None:
    stdout.write(json.dumps(result.to_dict(), sort_keys=True, separators=(",", ":")) + "\n")
    stdout.flush()


def _load_context(arguments: argparse.Namespace) -> tuple[WorkspacePaths, EvidenceStore]:
    project = Path(arguments.project).expanduser().absolute()
    data_root = Path(arguments.data_root).expanduser().absolute()
    try:
        model = load_project_model(project)
        if type(model.schema_version) is not int or model.schema_version != 3:
            raise _AdapterFailure(ANALYSIS_WORKFLOW_INVALID, "Project schema version is invalid")
        paths = WorkspacePaths.from_roots(
            data_root,
            project,
            model.logical_project_id,
            arguments.session_id,
        )
        evidence = EvidenceStore(paths.workspace_root / "evidence")
    except _AdapterFailure:
        raise
    except ProjectManifestError as error:
        if _has_provider_io_cause(error):
            raise _AdapterFailure(
                ENVIRONMENT_FAILURE, "Project provider is unavailable"
            ) from error
        raise _AdapterFailure(ANALYSIS_WORKFLOW_INVALID, "Project configuration is invalid") from error
    except (OSError, PermissionError) as error:
        raise _AdapterFailure(ENVIRONMENT_FAILURE, "Monitor analysis storage is unavailable") from error
    except (TypeError, ValueError, OverflowError) as error:
        raise _AdapterFailure(ANALYSIS_WORKFLOW_INVALID, "Monitor analysis context is invalid") from error
    return paths, evidence


def _decode_json_bytes(raw: bytes) -> dict[str, object]:
    if type(raw) is not bytes:
        raise _AdapterFailure(ANALYSIS_WORKFLOW_INVALID, "JSON input is invalid")
    try:
        value = parse_json_object(
            raw,
            limit=_ADAPTER_JSON_LIMIT,
            invalid_code=ANALYSIS_WORKFLOW_INVALID,
        )
        canonical = canonical_replay_json_bytes(value)
    except (ProtocolViolation, MonitorReplayError, TypeError, ValueError, OverflowError) as error:
        raise _AdapterFailure(ANALYSIS_WORKFLOW_INVALID, "JSON input is invalid") from error
    if raw not in (canonical, canonical + b"\n"):
        raise _AdapterFailure(ANALYSIS_WORKFLOW_INVALID, "JSON input is not canonical")
    return value


def _load_json_file(path_value: str) -> dict[str, object]:
    try:
        raw = EvidenceStore._read_file_bytes(
            Path(path_value).expanduser(), maximum_bytes=_ADAPTER_JSON_LIMIT
        )
    except EvidenceValidationError as error:
        raise _AdapterFailure(ANALYSIS_WORKFLOW_INVALID, "JSON input file is invalid") from error
    except (FileNotFoundError, NotADirectoryError, IsADirectoryError, TypeError, ValueError) as error:
        raise _AdapterFailure(ANALYSIS_WORKFLOW_INVALID, "JSON input file is invalid") from error
    except (PermissionError, OSError) as error:
        if _is_missing_path_error(error):
            raise _AdapterFailure(ANALYSIS_WORKFLOW_INVALID, "JSON input file is invalid") from error
        raise _AdapterFailure(ENVIRONMENT_FAILURE, "JSON input provider is unavailable") from error
    return _decode_json_bytes(raw)


def _model_wire(value: object, label: str) -> dict[str, object]:
    if type(value) is dict:
        return value
    serializer = getattr(value, "to_dict", None)
    if not callable(serializer):
        raise _AdapterFailure(ANALYSIS_WORKFLOW_INVALID, f"{label} is invalid")
    try:
        payload = serializer()
    except Exception as error:
        raise _AdapterFailure(ANALYSIS_WORKFLOW_INVALID, f"{label} is invalid") from error
    if type(payload) is not dict:
        raise _AdapterFailure(ANALYSIS_WORKFLOW_INVALID, f"{label} is invalid")
    return payload


def _load_request(path_value: str) -> AnalysisRequest:
    value = _load_json_file(path_value)
    try:
        return AnalysisRequest.from_value(value)
    except Exception as error:
        if isinstance(error, AnalysisWorkflowError):
            raise
        raise _AdapterFailure(ANALYSIS_WORKFLOW_INVALID, "analysis request is invalid") from error


def _load_source_change(path_value: str | None) -> SourceChangeDeclaration | None:
    if path_value is None:
        return None
    value = _load_json_file(path_value)
    try:
        return SourceChangeDeclaration.from_value(value)
    except Exception as error:
        if isinstance(error, AnalysisWorkflowError):
            raise
        raise _AdapterFailure(ANALYSIS_WORKFLOW_INVALID, "source change declaration is invalid") from error


def _load_publication(path_value: str) -> AnalysisPublication:
    value = _load_json_file(path_value)
    try:
        return AnalysisPublication.from_value(value)
    except AnalysisWorkflowError:
        raise
    except Exception as error:
        raise _AdapterFailure(ANALYSIS_WORKFLOW_INVALID, "analysis publication is invalid") from error


def _run_adapter(arguments: argparse.Namespace) -> ProtocolResult[object]:
    paths, evidence = _load_context(arguments)
    if arguments.adapter_operation == "monitor.replay.ingest":
        # The workflow owns replay semantics; the adapter still proves that the
        # caller supplied one bounded, regular, canonical JSON document before
        # handing the path to it.
        _load_json_file(arguments.document_file)
        reference = ingest_monitor_replay(
            paths,
            evidence,
            arguments.operation_id,
            Path(arguments.document_file),
        )
        return success(
            arguments.adapter_operation,
            {"monitor_run_ref": _model_wire(reference, "monitor run reference")},
        )

    if arguments.adapter_operation == "monitor.physical.publish":
        reference = publish_physical_monitor_run(
            paths,
            evidence,
            scenario_role=arguments.scenario_role,
            test_run_id=arguments.test_run_id,
            run_id=arguments.run_id,
            group_id=arguments.group_id,
            start_sequence=arguments.start_sequence,
            end_sequence_exclusive=arguments.end_sequence_exclusive,
            start_captured_unix_ns=arguments.start_captured_unix_ns,
            end_captured_unix_ns_exclusive=arguments.end_captured_unix_ns_exclusive,
            probe_id=arguments.probe_id,
        )
        return success(
            arguments.adapter_operation,
            {"monitor_run_ref": _model_wire(reference, "monitor run reference")},
        )

    request = _load_request(arguments.request_file)
    source_change = _load_source_change(arguments.source_change_file)
    if arguments.adapter_operation == "monitor.analysis.compare":
        publication = compare_monitor_runs(
            paths,
            evidence,
            request,
            arguments.diagnostic_session_id,
            arguments.hypothesis_id,
            arguments.polarity,
            arguments.rationale,
            source_change,
        )
        return success(
            arguments.adapter_operation,
            {"analysis_publication": _model_wire(publication, "analysis publication")},
        )

    publication = _load_publication(arguments.publication_file)
    payload, reference = export_analysis_bundle(
        paths,
        evidence,
        request,
        publication,
        arguments.failed_before_test_run_id,
        arguments.fixed_after_test_run_id,
        source_change,
    )
    bundle = _decode_json_bytes(payload)
    return success(
        arguments.adapter_operation,
        {
            "analysis_bundle": bundle,
            "analysis_bundle_ref": _model_wire(reference, "analysis bundle reference"),
        },
    )


def _adapter_error(
    error: BaseException,
    *,
    adapter_operation: str | None = None,
) -> tuple[str, str]:
    if isinstance(error, _AdapterFailure):
        return error.code, error.message
    if isinstance(error, AnalysisWorkflowError):
        code = error.code
        if code == "OPERATION_CONFLICT":
            code = EVIDENCE_INTEGRITY_FAILURE
        if code not in _ADAPTER_CODES:
            code = ANALYSIS_WORKFLOW_INVALID
        return code, error.message
    if isinstance(error, MonitorReplayError):
        if error.code == OPERATION_CONFLICT:
            if adapter_operation == "monitor.physical.publish":
                return OPERATION_CONFLICT, error.message
            return EVIDENCE_INTEGRITY_FAILURE, error.message
        if error.code in _ADAPTER_CODES:
            return error.code, error.message
        return ANALYSIS_WORKFLOW_INVALID, error.message
    if isinstance(error, (OSError, PermissionError)):
        return ENVIRONMENT_FAILURE, "Monitor analysis provider failed"
    if isinstance(error, EvidenceValidationError):
        return EVIDENCE_INTEGRITY_FAILURE, "Evidence is invalid"
    if isinstance(error, (AnalysisError, TypeError, ValueError, OverflowError, KeyError)):
        return ANALYSIS_WORKFLOW_INVALID, "Monitor analysis input is invalid"
    return ENVIRONMENT_FAILURE, "Monitor analysis provider failed"


def _has_provider_io_cause(error: BaseException) -> bool:
    """Classify only clearly distinguishable manifest provider failures."""

    current: BaseException | None = error.__cause__
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (PermissionError, OSError)):
            return not _is_missing_path_error(current)
        current = current.__cause__
    return False


def _is_missing_path_error(error: OSError) -> bool:
    return isinstance(error, (FileNotFoundError, NotADirectoryError, IsADirectoryError)) or getattr(
        error, "errno", None
    ) in (errno.ENOENT, errno.ENOTDIR, errno.EISDIR)


__all__ = ["main"]
