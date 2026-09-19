import asyncio
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from mcp.types import FileUrl, ListRootsResult, Root
import stm32_toolkit.mcp_server as mcp_server
from stm32_toolkit.result import OperationResult

from stm32_toolkit.mcp_server import (
    ServerRuntime,
    create_server,
    tool_doctor_for_request,
    tool_project_context_for_request,
    tool_project_detect,
    tool_project_detect_for_request,
)


class _RootSession:
    def __init__(self, root_batches: list[list[Path]], *, error: Exception | None = None):
        self.client_params = SimpleNamespace(
            capabilities=SimpleNamespace(roots=object())
        )
        self._root_batches = iter(root_batches)
        self._error = error
        self.list_roots_calls = 0

    async def list_roots(self) -> ListRootsResult:
        self.list_roots_calls += 1
        if self._error is not None:
            raise self._error
        paths = next(self._root_batches)
        return ListRootsResult(
            roots=[Root(uri=FileUrl(path.resolve().as_uri())) for path in paths]
        )


def _runtime(tmp_path: Path) -> ServerRuntime:
    project = tmp_path / "project"
    project.mkdir()
    (project / "legacy.uvprojx").write_text("<Project/>", encoding="utf-8")
    return ServerRuntime.create(project, tmp_path / "plugin-data", "session-a")


def _context(session: object) -> SimpleNamespace:
    return SimpleNamespace(session=session)


def _tree_snapshot(root: Path) -> tuple[tuple[str, bool, bytes | None], ...]:
    return tuple(
        (
            str(path.relative_to(root)),
            path.is_dir(),
            path.read_bytes() if path.is_file() else None,
        )
        for path in sorted(root.rglob("*"))
    )


_MCP_MISMATCHED_ROOT_CASES = (
    (
        "create-prepare-mismatched-root",
        "tool_project_create_prepare_for_request",
        "tool_project_create_prepare",
        "project-create-prepare",
        ("mcu", "STM32F429ZGTx", "generated", "hal", "c", "a" * 64, "b" * 64),
    ),
    (
        "create-apply-mismatched-root",
        "tool_project_create_apply_for_request",
        "tool_project_create_apply",
        "project-create-apply",
        ("c" * 64, False),
    ),
    (
        "regenerate-plan-mismatched-root",
        "tool_project_regenerate_plan_for_request",
        "tool_project_regenerate_plan",
        "project-regenerate-plan",
        ("generated",),
    ),
    (
        "regenerate-prepare-mismatched-root",
        "tool_project_regenerate_prepare_for_request",
        "tool_project_regenerate_prepare",
        "project-regenerate-prepare",
        ("generated", "d" * 64, "e" * 64, False),
    ),
    (
        "regenerate-apply-mismatched-root",
        "tool_project_regenerate_apply_for_request",
        "tool_project_regenerate_apply",
        "project-regenerate-apply",
        ("f" * 64, False),
    ),
)


_MCP_MATCHING_ROOT_CASES = (
    (
        "create-prepare-matching-root",
        "tool_project_create_prepare_for_request",
        "tool_project_create_prepare",
        "project-create-prepare",
        ("mcu", "STM32F429ZGTx", "generated", "hal", "c", "a" * 64, "b" * 64),
    ),
    (
        "create-apply-matching-root",
        "tool_project_create_apply_for_request",
        "tool_project_create_apply",
        "project-create-apply",
        ("c" * 64, False),
    ),
    (
        "regenerate-plan-matching-root",
        "tool_project_regenerate_plan_for_request",
        "tool_project_regenerate_plan",
        "project-regenerate-plan",
        ("generated",),
    ),
    (
        "regenerate-prepare-matching-root",
        "tool_project_regenerate_prepare_for_request",
        "tool_project_regenerate_prepare",
        "project-regenerate-prepare",
        ("generated", "d" * 64, "e" * 64, False),
    ),
    (
        "regenerate-apply-matching-root",
        "tool_project_regenerate_apply_for_request",
        "tool_project_regenerate_apply",
        "project-regenerate-apply",
        ("f" * 64, False),
    ),
)


@pytest.mark.parametrize(
    ("case_id", "request_name", "delegate_name", "operation", "arguments"),
    _MCP_MISMATCHED_ROOT_CASES,
    ids=[case[0] for case in _MCP_MISMATCHED_ROOT_CASES],
)
def test_mcp_public_adapters_reject_mismatched_root(
    monkeypatch,
    tmp_path: Path,
    case_id: str,
    request_name: str,
    delegate_name: str,
    operation: str,
    arguments: tuple[object, ...],
):
    runtime = _runtime(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    session = _RootSession([[other]])
    context = _context(session)
    project_root = runtime.project_root
    data_root = runtime.data_root
    project_before = _tree_snapshot(project_root)
    data_before = _tree_snapshot(data_root)
    dispatches = []

    def recorder(*received):
        dispatches.append(received)
        return OperationResult.success(operation, {"unexpected": case_id}).to_dict()

    monkeypatch.setattr(mcp_server, delegate_name, recorder)
    original_arguments = tuple(arguments)
    result = asyncio.run(
        getattr(mcp_server, request_name)(runtime, context, *arguments)
    )

    assert result == {
        "protocol": "stm32-toolkit/1",
        "ok": False,
        "operation": operation,
        "code": "UNSUPPORTED_MULTIROOT",
        "message": "MCP client roots must contain only the bound project root",
        "data": None,
        "details": {
            "boundProjectRoot": str(project_root),
            "roots": [str(other.resolve())],
        },
    }
    assert dispatches == []
    assert session.list_roots_calls == 1
    assert arguments == original_arguments
    assert context.session is session
    assert runtime.project_root is project_root
    assert runtime.data_root is data_root
    assert _tree_snapshot(project_root) == project_before
    assert _tree_snapshot(data_root) == data_before


@pytest.mark.parametrize(
    ("case_id", "request_name", "delegate_name", "operation", "arguments"),
    _MCP_MATCHING_ROOT_CASES,
    ids=[case[0] for case in _MCP_MATCHING_ROOT_CASES],
)
def test_mcp_public_adapters_forward_matching_root(
    monkeypatch,
    tmp_path: Path,
    case_id: str,
    request_name: str,
    delegate_name: str,
    operation: str,
    arguments: tuple[object, ...],
):
    runtime = _runtime(tmp_path)
    session = _RootSession([[runtime.project_root]])
    context = _context(session)
    project_root = runtime.project_root
    data_root = runtime.data_root
    project_before = _tree_snapshot(project_root)
    data_before = _tree_snapshot(data_root)
    dispatches = []
    returned_results = []

    def recorder(*received):
        dispatches.append(received)
        returned = OperationResult.success(
            operation,
            {"case": case_id, "preserved": list(arguments)},
        ).to_dict()
        returned_results.append(returned)
        return returned

    monkeypatch.setattr(mcp_server, delegate_name, recorder)
    original_arguments = tuple(arguments)
    result = asyncio.run(
        getattr(mcp_server, request_name)(runtime, context, *arguments)
    )

    assert session.list_roots_calls == 1
    assert len(dispatches) == 1
    forwarded = dispatches[0]
    assert forwarded[0] is runtime
    assert forwarded[1:] == original_arguments
    assert tuple(type(value) for value in forwarded[1:]) == tuple(
        type(value) for value in original_arguments
    )
    assert result is returned_results[0]
    assert result == OperationResult.success(
        operation,
        {"case": case_id, "preserved": list(original_arguments)},
    ).to_dict()
    assert arguments == original_arguments
    assert context.session is session
    assert runtime.project_root is project_root
    assert runtime.data_root is data_root
    assert _tree_snapshot(project_root) == project_before
    assert _tree_snapshot(data_root) == data_before


_REMAINING_SESSION = "a" * 32
_REMAINING_A64 = "a" * 64
_REMAINING_B64 = "b" * 64
_REMAINING_C64 = "c" * 64
_REMAINING_D64 = "d" * 64
_REMAINING_E64 = "e" * 64
_REMAINING_F64 = "f" * 64
_REMAINING_UUID1 = "00000000-0000-4000-8000-000000000001"
_REMAINING_UUID2 = "00000000-0000-4000-8000-000000000002"
_REMAINING_UUID3 = "00000000-0000-4000-8000-000000000003"
_REMAINING_UUID4 = "00000000-0000-4000-8000-000000000004"


def _source_change_declaration_wire() -> dict[str, object]:
    return {
        "schema": "stm32-source-change-declaration/1",
        "declaration_id": _REMAINING_A64,
        "before_source_sha256": _REMAINING_B64,
        "after_source_sha256": _REMAINING_C64,
        "before_build_id": _REMAINING_D64,
        "before_elf_sha256": _REMAINING_E64,
        "after_build_id": _REMAINING_F64,
        "after_elf_sha256": _REMAINING_A64,
        "changed_paths": ["src/main.c"],
        "diff_evidence_id": _REMAINING_B64,
        "diff_artifact": {
            "sha256": _REMAINING_C64,
            "size_bytes": 1,
            "relative_path": "evidence.diff",
            "kind": "diff",
            "media_type": "text/plain",
        },
        "claimed_hypothesis_ids": [_REMAINING_SESSION],
        "validation_plan_id": _REMAINING_D64,
    }


def _verification_plan_wire() -> dict[str, object]:
    return {
        "schema": "stm32-verification-plan/1",
        "verification_plan_id": _REMAINING_C64,
        "diagnostic_session_id": _REMAINING_SESSION,
        "failed_before_run_id": "11111111-1111-4111-8111-111111111111",
        "failed_before_evidence_id": _REMAINING_D64,
        "source_change_declaration_id": _REMAINING_A64,
        "fixed_after_run_id": "22222222-2222-4222-8222-222222222222",
        "fixed_after_evidence_id": _REMAINING_E64,
        "required_analysis_ids": [_REMAINING_F64],
        "required_analysis_evidence_ids": [_REMAINING_A64],
        "required_monitor_quality": "VALID",
        "expected_changed": True,
        "plan_digest": _REMAINING_B64,
    }


def _diagnostic_marker_wire() -> dict[str, object]:
    return {
        "schema": "stm32-diagnostic-marker-ref/1",
        "marker_id": _REMAINING_A64,
        "marker_evidence_id": _REMAINING_B64,
        "analysis_id": _REMAINING_C64,
        "analysis_evidence_id": _REMAINING_D64,
        "diagnostic_session_id": _REMAINING_SESSION,
        "hypothesis_id": "b" * 32,
        "polarity": "supports",
        "label": "change-observed",
        "rationale": "the observation matches the hypothesis",
    }


def _source_change_intent_wire() -> dict[str, object]:
    return {
        "schema": "stm32-source-change-intent/1",
        "changes": [
            {
                "path": "src/main.c",
                "beforeSha256": _REMAINING_A64,
                "afterSha256": _REMAINING_B64,
                "afterSize": 12,
            }
        ],
    }


_REMAINING_ROOT_CASES = (
    ("keil-inspect", "tool_keil_inspect_for_request", "tool_keil_inspect", "keil-inspect"),
    ("flash", "tool_flash_for_request", "flash_workflow", "stm32_flash"),
    (
        "handoff-begin",
        "tool_handoff_begin_for_request",
        "handoff_begin_workflow",
        "stm32_debug_handoff_begin",
    ),
    (
        "diagnostic-source-change-declare",
        "tool_diagnostic_declare_source_change_for_request",
        "diagnostic_declare_source_change",
        "diagnostic.source-change.declare",
    ),
    (
        "diagnostic-verification-plan-add",
        "tool_diagnostic_add_verification_plan_for_request",
        "diagnostic_add_verification_plan",
        "diagnostic.verification-plan.add",
    ),
    (
        "diagnostic-verification-start",
        "tool_diagnostic_start_verification_for_request",
        "diagnostic_start_verification",
        "diagnostic.verification.start",
    ),
    (
        "diagnostic-marker-attach",
        "tool_diagnostic_attach_marker_for_request",
        "diagnostic_attach_marker",
        "diagnostic.marker.attach",
    ),
    (
        "diagnostic-verification-complete",
        "tool_diagnostic_complete_verification_for_request",
        "diagnostic_complete_verification",
        "diagnostic.verification.complete",
    ),
    (
        "diagnostic-verification-show",
        "tool_diagnostic_show_verification_for_request",
        "diagnostic_show_verification",
        "diagnostic.verification.show",
    ),
    ("test-target-prepare", "tool_test_target_prepare_for_request", "target_test_prepare", "test.target.prepare"),
    ("test-target-execute", "tool_test_target_execute_for_request", "target_test_execute", "test.target.execute"),
    (
        "acceptance-scenario-describe",
        "tool_acceptance_scenario_describe_for_request",
        "describe_acceptance_scenario",
        "acceptance.scenario.describe",
    ),
    (
        "acceptance-scenario-record",
        "tool_acceptance_scenario_record_for_request",
        "record_acceptance_scenario",
        "acceptance.scenario.record",
    ),
    (
        "acceptance-scenario-show",
        "tool_acceptance_scenario_show_for_request",
        "show_acceptance_scenario",
        "acceptance.scenario.show",
    ),
    (
        "acceptance-attempt-begin",
        "tool_acceptance_attempt_begin_for_request",
        "begin_acceptance_attempt",
        "acceptance.attempt.begin",
    ),
    (
        "acceptance-attempt-checkpoint",
        "tool_acceptance_attempt_checkpoint_for_request",
        "checkpoint_acceptance_attempt",
        "acceptance.attempt.checkpoint",
    ),
    (
        "acceptance-attempt-authorize-source-change",
        "tool_acceptance_attempt_authorize_source_change_for_request",
        "authorize_acceptance_source_change",
        "acceptance.attempt.authorize-source-change",
    ),
    (
        "acceptance-attempt-show",
        "tool_acceptance_attempt_show_for_request",
        "show_acceptance_attempt",
        "acceptance.attempt.show",
    ),
    (
        "acceptance-attempt-resume",
        "tool_acceptance_attempt_resume_for_request",
        "resume_acceptance_attempt",
        "acceptance.attempt.resume",
    ),
)

_REMAINING_ASYNC_PROVIDERS = {
    "flash_workflow",
    "handoff_begin_workflow",
    "target_test_prepare",
    "target_test_execute",
}


def _remaining_root_arguments(case_id: str) -> tuple[object, ...]:
    if case_id == "keil-inspect":
        return (None, None, True)
    if case_id == "flash":
        return ("probe-a", _REMAINING_A64, _REMAINING_B64, True, False)
    if case_id == "handoff-begin":
        return ("probe-a", _REMAINING_A64, _REMAINING_B64, True, ["counter"])
    if case_id == "diagnostic-source-change-declare":
        declaration = mcp_server.SourceChangeDeclarationInput.model_validate(
            _source_change_declaration_wire()
        )
        return ("diagnostic-operation-1", _REMAINING_SESSION, 1, declaration, "user")
    if case_id == "diagnostic-verification-plan-add":
        plan = mcp_server.VerificationPlanInput.model_validate(_verification_plan_wire())
        return ("diagnostic-operation-1", _REMAINING_SESSION, 1, plan, "user")
    if case_id == "diagnostic-verification-start":
        return ("diagnostic-operation-1", _REMAINING_SESSION, 1, _REMAINING_C64, "tool")
    if case_id == "diagnostic-marker-attach":
        marker = mcp_server.DiagnosticMarkerInput.model_validate(_diagnostic_marker_wire())
        return ("diagnostic-operation-1", _REMAINING_SESSION, 1, marker, "tool")
    if case_id == "diagnostic-verification-complete":
        return ("diagnostic-operation-1", _REMAINING_SESSION, 1, ["diagnostic-operation-1"], False, "tool")
    if case_id == "diagnostic-verification-show":
        return (_REMAINING_SESSION,)
    if case_id == "test-target-prepare":
        return ("probe-a", ["case-a"], False)
    if case_id == "test-target-execute":
        return ("probe-a", _REMAINING_A64)
    if case_id == "acceptance-scenario-describe":
        return ("legacy-keil-migration", "1")
    if case_id == "acceptance-scenario-record":
        return (
            _REMAINING_UUID1,
            "legacy-keil-migration",
            "1",
            _REMAINING_UUID2,
            _REMAINING_UUID3,
            _REMAINING_UUID4,
        )
    if case_id == "acceptance-scenario-show":
        return (_REMAINING_UUID1,)
    if case_id == "acceptance-attempt-begin":
        return (_REMAINING_UUID1, "legacy-keil-migration", "1", None)
    if case_id == "acceptance-attempt-checkpoint":
        intent = mcp_server.PhysicalSourceChangeIntentInput.model_validate(
            _source_change_intent_wire()
        )
        return (
            _REMAINING_UUID1,
            2,
            "target-failure-replayed",
            _REMAINING_UUID2,
            None,
            None,
            intent,
            _REMAINING_D64,
        )
    if case_id == "acceptance-attempt-authorize-source-change":
        return (_REMAINING_UUID1, 4, _REMAINING_A64, True)
    if case_id in {"acceptance-attempt-show", "acceptance-attempt-resume"}:
        return (_REMAINING_UUID1,)
    raise AssertionError(f"unhandled remaining root case: {case_id}")


def _remaining_recorder(
    case_id: str,
    provider_name: str,
    operation: str,
    calls: list[tuple[tuple[object, ...], dict[str, object]]],
    returned_values: list[object],
):
    if provider_name == "tool_keil_inspect":
        def recorder(*args: object, **kwargs: object) -> dict[str, object]:
            calls.append((args, kwargs))
            sentinel = {"operation": operation, "case": case_id}
            returned_values.append(sentinel)
            return sentinel

        return recorder

    if provider_name in _REMAINING_ASYNC_PROVIDERS:
        async def recorder(*args: object, **kwargs: object) -> OperationResult[object]:
            calls.append((args, kwargs))
            return OperationResult.success(operation, {"case": case_id})

        return recorder

    def recorder(*args: object, **kwargs: object) -> OperationResult[object]:
        calls.append((args, kwargs))
        return OperationResult.success(operation, {"case": case_id})

    return recorder


def _assert_runtime_context(context: object, runtime: ServerRuntime) -> None:
    assert context.project_root == runtime.project_root
    assert context.data_root == runtime.data_root
    assert context.session_id == runtime.session_id


def _assert_remaining_dispatch(
    case_id: str,
    provider_name: str,
    runtime: ServerRuntime,
    arguments: tuple[object, ...],
    calls: list[tuple[tuple[object, ...], dict[str, object]]],
) -> None:
    assert len(calls) == 1
    received, keyword_arguments = calls[0]
    if provider_name == "tool_keil_inspect":
        assert keyword_arguments == {}
        assert received == (runtime, *arguments)
        assert tuple(type(value) for value in received[1:]) == tuple(
            type(value) for value in arguments
        )
        return
    if provider_name == "flash_workflow":
        assert keyword_arguments == {}
        assert len(received) == 1
        request = received[0]
        assert isinstance(request, mcp_server.FlashWorkflowRequest)
        assert request.project_root == runtime.project_root
        assert request.data_root == runtime.data_root
        assert request.session_id == runtime.session_id
        assert request.probe_id == "probe-a"
        assert request.expected_build_id == _REMAINING_A64
        assert request.expected_elf_sha256 == _REMAINING_B64
        assert request.authorized is True
        assert request.recovery_under_reset is False
        return
    if provider_name == "handoff_begin_workflow":
        assert keyword_arguments == {}
        assert len(received) == 1
        request = received[0]
        assert isinstance(request, mcp_server.HandoffBeginWorkflowRequest)
        assert request.project_root == runtime.project_root
        assert request.data_root == runtime.data_root
        assert request.session_id == runtime.session_id
        assert request.probe_id == "probe-a"
        assert request.expected_build_id == _REMAINING_A64
        assert request.expected_elf_sha256 == _REMAINING_B64
        assert request.authorized is True
        assert request.previous_watch_selection == ("counter",)
        return
    if provider_name in {"target_test_prepare", "target_test_execute"}:
        assert len(received) == 1
        _assert_runtime_context(received[0], runtime)
        if provider_name == "target_test_prepare":
            assert keyword_arguments == {
                "probe_id": "probe-a",
                "case_ids": ("case-a",),
                "recovery_under_reset": False,
            }
        else:
            assert keyword_arguments == {
                "probe_id": "probe-a",
                "authorized_action_digest": _REMAINING_A64,
            }
        return

    assert len(received) == 1
    context = received[0]
    _assert_runtime_context(context, runtime)
    if provider_name.startswith("diagnostic_"):
        assert isinstance(context, mcp_server.DiagnosticWorkflowContext)
    elif provider_name in {
        "describe_acceptance_scenario",
        "record_acceptance_scenario",
        "show_acceptance_scenario",
    }:
        assert isinstance(context, mcp_server.AcceptanceWorkflowContext)
    else:
        assert isinstance(context, mcp_server.AcceptanceRecoveryContext)

    if case_id == "diagnostic-source-change-declare":
        assert keyword_arguments == {
            "operation_id": "diagnostic-operation-1",
            "diagnostic_session_id": _REMAINING_SESSION,
            "expected_revision": 1,
            "source_change_declaration": arguments[3].model_dump(mode="python", by_alias=True),
            "actor": "user",
        }
    elif case_id == "diagnostic-verification-plan-add":
        assert keyword_arguments == {
            "operation_id": "diagnostic-operation-1",
            "diagnostic_session_id": _REMAINING_SESSION,
            "expected_revision": 1,
            "verification_plan": arguments[3].model_dump(mode="python", by_alias=True),
            "actor": "user",
        }
    elif case_id == "diagnostic-verification-start":
        assert keyword_arguments == {
            "operation_id": "diagnostic-operation-1",
            "diagnostic_session_id": _REMAINING_SESSION,
            "expected_revision": 1,
            "verification_plan_id": _REMAINING_C64,
            "actor": "tool",
        }
    elif case_id == "diagnostic-marker-attach":
        assert keyword_arguments == {
            "operation_id": "diagnostic-operation-1",
            "diagnostic_session_id": _REMAINING_SESSION,
            "expected_revision": 1,
            "diagnostic_marker_ref": arguments[3].model_dump(mode="python", by_alias=True),
            "actor": "tool",
        }
    elif case_id == "diagnostic-verification-complete":
        assert keyword_arguments == {
            "operation_id": "diagnostic-operation-1",
            "diagnostic_session_id": _REMAINING_SESSION,
            "expected_revision": 1,
            "executed_operation_ids": ["diagnostic-operation-1"],
            "cancelled": False,
            "actor": "tool",
        }
    elif case_id == "diagnostic-verification-show":
        assert keyword_arguments == {"diagnostic_session_id": _REMAINING_SESSION}
    elif case_id == "acceptance-scenario-describe":
        assert keyword_arguments == {
            "scenario_id": "legacy-keil-migration",
            "scenario_version": "1",
        }
    elif case_id == "acceptance-scenario-record":
        assert keyword_arguments == {
            "record_id": _REMAINING_UUID1,
            "scenario_id": "legacy-keil-migration",
            "scenario_version": "1",
            "failed_before_test_run_id": _REMAINING_UUID2,
            "fixed_after_test_run_id": _REMAINING_UUID3,
            "diagnostic_session_id": _REMAINING_UUID4,
        }
    elif case_id == "acceptance-scenario-show":
        assert keyword_arguments == {"record_id": _REMAINING_UUID1}
    elif case_id == "acceptance-attempt-begin":
        assert keyword_arguments == {
            "attempt_id": _REMAINING_UUID1,
            "scenario_id": "legacy-keil-migration",
            "scenario_version": "1",
        }
    elif case_id == "acceptance-attempt-checkpoint":
        assert keyword_arguments == {
            "attempt_id": _REMAINING_UUID1,
            "expected_revision": 2,
            "stage": "target-failure-replayed",
            "test_run_id": _REMAINING_UUID2,
            "diagnostic_session_id": None,
            "acceptance_record_id": None,
            "source_change_intent": arguments[6].model_dump(mode="python", by_alias=True),
            "fix_verification_id": _REMAINING_D64,
        }
    elif case_id == "acceptance-attempt-authorize-source-change":
        assert keyword_arguments == {
            "attempt_id": _REMAINING_UUID1,
            "expected_revision": 4,
            "action_digest": _REMAINING_A64,
            "authorized": True,
        }
    elif case_id in {"acceptance-attempt-show", "acceptance-attempt-resume"}:
        assert keyword_arguments == {"attempt_id": _REMAINING_UUID1}
    else:
        raise AssertionError(f"unhandled dispatch assertions: {case_id}")


@pytest.mark.parametrize(
    ("case_id", "request_name", "provider_name", "operation"),
    _REMAINING_ROOT_CASES,
    ids=[case[0] for case in _REMAINING_ROOT_CASES],
)
def test_remaining_mcp_public_adapters_reject_mismatched_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    case_id: str,
    request_name: str,
    provider_name: str,
    operation: str,
):
    runtime = _runtime(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    session = _RootSession([[other]])
    context = _context(session)
    project_root = runtime.project_root
    data_root = runtime.data_root
    arguments = _remaining_root_arguments(case_id)
    arguments_before = deepcopy(arguments)
    argument_types = tuple(type(value) for value in arguments)
    project_before = _tree_snapshot(runtime.project_root)
    data_before = _tree_snapshot(runtime.data_root)
    dispatches: list[tuple[tuple[object, ...], dict[str, object]]] = []
    returned_values: list[object] = []
    recorder = _remaining_recorder(
        case_id, provider_name, operation, dispatches, returned_values
    )
    monkeypatch.setattr(mcp_server, provider_name, recorder)
    assert getattr(mcp_server, provider_name) is recorder

    result = asyncio.run(
        getattr(mcp_server, request_name)(runtime, context, *arguments)
    )

    assert result == {
        "protocol": "stm32-toolkit/1",
        "ok": False,
        "operation": operation,
        "code": "UNSUPPORTED_MULTIROOT",
        "message": "MCP client roots must contain only the bound project root",
        "data": None,
        "details": {
            "boundProjectRoot": str(runtime.project_root),
            "roots": [str(other.resolve())],
        },
    }
    assert dispatches == []
    assert session.list_roots_calls == 1
    assert arguments == arguments_before
    assert tuple(type(value) for value in arguments) == argument_types
    assert context.session is session
    assert runtime.project_root is project_root
    assert runtime.data_root is data_root
    assert _tree_snapshot(project_root) == project_before
    assert _tree_snapshot(data_root) == data_before


@pytest.mark.parametrize(
    ("case_id", "request_name", "provider_name", "operation"),
    _REMAINING_ROOT_CASES,
    ids=[case[0] for case in _REMAINING_ROOT_CASES],
)
def test_remaining_mcp_public_adapters_forward_matching_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    case_id: str,
    request_name: str,
    provider_name: str,
    operation: str,
):
    runtime = _runtime(tmp_path)
    session = _RootSession([[runtime.project_root]])
    context = _context(session)
    arguments = _remaining_root_arguments(case_id)
    arguments_before = deepcopy(arguments)
    argument_types = tuple(type(value) for value in arguments)
    project_before = _tree_snapshot(runtime.project_root)
    data_before = _tree_snapshot(runtime.data_root)
    dispatches: list[tuple[tuple[object, ...], dict[str, object]]] = []
    returned_values: list[object] = []
    recorder = _remaining_recorder(
        case_id, provider_name, operation, dispatches, returned_values
    )
    monkeypatch.setattr(mcp_server, provider_name, recorder)
    assert getattr(mcp_server, provider_name) is recorder

    result = asyncio.run(
        getattr(mcp_server, request_name)(runtime, context, *arguments)
    )

    assert session.list_roots_calls == 1
    _assert_remaining_dispatch(case_id, provider_name, runtime, arguments, dispatches)
    if provider_name == "tool_keil_inspect":
        expected = {"operation": operation, "case": case_id}
        assert result is returned_values[0]
    else:
        expected = OperationResult.success(operation, {"case": case_id}).to_dict()
    assert result == expected
    assert arguments == arguments_before
    assert tuple(type(value) for value in arguments) == argument_types
    assert context.session is session
    assert _tree_snapshot(runtime.project_root) == project_before
    assert _tree_snapshot(runtime.data_root) == data_before


def test_direct_and_no_roots_capability_calls_remain_bound_to_the_runtime(tmp_path: Path):
    runtime = _runtime(tmp_path)
    no_capability = SimpleNamespace(
        client_params=SimpleNamespace(capabilities=SimpleNamespace(roots=None))
    )

    direct = tool_project_detect(runtime)
    through_request = asyncio.run(
        tool_project_detect_for_request(runtime, _context(no_capability))
    )

    assert direct["data"]["kind"] == "keil"
    assert through_request == direct


def test_one_matching_client_root_is_accepted(tmp_path: Path):
    runtime = _runtime(tmp_path)
    session = _RootSession([[runtime.project_root]])

    result = asyncio.run(
        tool_project_detect_for_request(runtime, _context(session))
    )

    assert result["ok"] is True
    assert result["data"]["kind"] == "keil"
    assert session.list_roots_calls == 1


@pytest.mark.parametrize(
    ("request_tool", "operation"),
    [
        (tool_doctor_for_request, "doctor"),
        (tool_project_detect_for_request, "project.detect"),
        (tool_project_context_for_request, "project.context"),
    ],
)
def test_every_registered_wrapper_rejects_multiple_client_roots(
    tmp_path: Path,
    request_tool,
    operation: str,
):
    runtime = _runtime(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    session = _RootSession([[runtime.project_root, other]])

    result = asyncio.run(
        request_tool(runtime, _context(session))
    )

    assert result["ok"] is False
    assert result["operation"] == operation
    assert result["code"] == "UNSUPPORTED_MULTIROOT"
    assert result["details"]["boundProjectRoot"] == str(runtime.project_root)


def test_one_mismatched_client_root_is_rejected(tmp_path: Path):
    runtime = _runtime(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    session = _RootSession([[other]])

    result = asyncio.run(
        tool_project_detect_for_request(runtime, _context(session))
    )

    assert result["ok"] is False
    assert result["code"] == "UNSUPPORTED_MULTIROOT"
    assert result["details"]["boundProjectRoot"] == str(runtime.project_root)


def test_client_roots_inspection_failure_has_a_stable_error(tmp_path: Path):
    runtime = _runtime(tmp_path)
    session = _RootSession([], error=RuntimeError("roots unavailable"))

    result = asyncio.run(
        tool_project_detect_for_request(runtime, _context(session))
    )

    assert result["ok"] is False
    assert result["code"] == "MCP_ROOTS_UNAVAILABLE"
    assert result["message"] == "MCP client roots are unavailable"
    assert result["details"] == {"boundProjectRoot": str(runtime.project_root)}


def test_client_roots_timeout_cancels_request_and_returns_stable_error(
    monkeypatch,
    tmp_path: Path,
):
    runtime = _runtime(tmp_path)

    class NeverReturningSession:
        def __init__(self):
            self.client_params = SimpleNamespace(
                capabilities=SimpleNamespace(roots=object())
            )
            self.cancelled = False

        async def list_roots(self):
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise

    session = NeverReturningSession()
    monkeypatch.setattr(
        "stm32_toolkit.mcp_server._CLIENT_ROOTS_TIMEOUT_SECONDS",
        0.01,
        raising=False,
    )

    async def bounded_call():
        try:
            return await asyncio.wait_for(
                tool_project_detect_for_request(runtime, _context(session)),
                timeout=0.2,
            )
        except TimeoutError:
            return {"code": "HUNG"}

    result = asyncio.run(bounded_call())

    assert result["code"] == "MCP_ROOTS_UNAVAILABLE"
    assert result["message"] == "MCP client roots are unavailable"
    assert result["details"] == {"boundProjectRoot": str(runtime.project_root)}
    assert session.cancelled is True


def test_inner_roots_cancellation_returns_stable_unavailable(tmp_path: Path):
    runtime = _runtime(tmp_path)

    class CancelledSession:
        def __init__(self):
            self.client_params = SimpleNamespace(
                capabilities=SimpleNamespace(roots=object())
            )

        async def list_roots(self):
            raise asyncio.CancelledError

    async def bounded_call():
        try:
            return await tool_project_detect_for_request(
                runtime, _context(CancelledSession())
            )
        except asyncio.CancelledError:
            return {"code": "CANCELLED"}

    result = asyncio.run(bounded_call())

    assert result["code"] == "MCP_ROOTS_UNAVAILABLE"


def test_external_tool_cancellation_is_not_swallowed(tmp_path: Path):
    runtime = _runtime(tmp_path)

    class BlockingSession:
        def __init__(self):
            self.client_params = SimpleNamespace(
                capabilities=SimpleNamespace(roots=object())
            )
            self.started = asyncio.Event()

        async def list_roots(self):
            self.started.set()
            await asyncio.Event().wait()

    async def cancel_call():
        session = BlockingSession()
        call = asyncio.create_task(
            tool_project_detect_for_request(runtime, _context(session))
        )
        await session.started.wait()
        call.cancel()
        await call

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(cancel_call())


def test_client_capability_inspection_failure_has_the_same_stable_error(
    tmp_path: Path,
):
    runtime = _runtime(tmp_path)

    class BrokenCapabilitySession:
        @property
        def client_params(self):
            raise RuntimeError("client parameters unavailable")

    result = asyncio.run(
        tool_project_detect_for_request(
            runtime, _context(BrokenCapabilitySession())
        )
    )

    assert result["code"] == "MCP_ROOTS_UNAVAILABLE"
    assert result["details"] == {"boundProjectRoot": str(runtime.project_root)}

def test_client_roots_are_checked_again_for_every_call(tmp_path: Path):
    runtime = _runtime(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    session = _RootSession(
        [[runtime.project_root], [runtime.project_root, other]]
    )
    context = _context(session)

    first = asyncio.run(tool_project_detect_for_request(runtime, context))
    second = asyncio.run(tool_project_detect_for_request(runtime, context))

    assert first["ok"] is True
    assert second["code"] == "UNSUPPORTED_MULTIROOT"
    assert session.list_roots_calls == 2


def test_injected_context_does_not_add_arguments_to_tool_schemas(tmp_path: Path):
    runtime = _runtime(tmp_path)

    server = create_server(
        runtime.project_root, runtime.data_root, runtime.session_id
    )
    tools = asyncio.run(server.list_tools())

    # The injected ``ctx`` parameter must never surface as a schema property.
    assert all("ctx" not in tool.inputSchema.get("properties", {}) for tool in tools)
    zero_argument_tools = {
        "stm32_doctor",
        "stm32_project_detect",
        "stm32_project_context",
        "stm32_probe_list",
        "stm32_test_host_discover",
    }
    for tool in tools:
        if tool.name in zero_argument_tools:
            assert tool.inputSchema.get("properties", {}) == {}
            assert not tool.inputSchema.get("required", [])
        else:
            assert tool.inputSchema.get("properties", {})
