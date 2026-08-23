from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import pytest

from stm32_toolkit.creation_workflows import (
    CreationPlanWorkflowRequest,
    apply_creation_workflow,
    plan_creation_workflow,
)
from stm32_toolkit.creation_authorization import (
    CreationAuthorizationError,
    CreationAuthorizationStore,
    CreationPrepareRequest,
)
from stm32_toolkit.creation_environment import CreationEnvironmentError
from stm32_toolkit.generation.creation import CreationRequest
from stm32_toolkit.tool_support import SupportProfileError, SupportProfileRequest, discover_tool_support


def test_plan_workflow_reports_missing_cubemx_as_plan_blocker(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("stm32_toolkit.creation_workflows.discover_tool_support", lambda request: __import__("stm32_toolkit.tool_support", fromlist=["ToolSupportProfile"]).ToolSupportProfile("3.12.10", None, None, None, None, None, None, (), ()))
    result = plan_creation_workflow(CreationPlanWorkflowRequest(tmp_path, tmp_path / "data", "session", "mcu", "STM32F429ZITx", "generated", "hal", "c"))
    assert result.ok is True
    assert result.data["blockers"][0]["code"] == "CUBEMX_MISSING"
    assert result.data["mutated"] is False


def test_workflow_rejects_malformed_input_without_exception_text(tmp_path: Path):
    result = plan_creation_workflow(CreationPlanWorkflowRequest(tmp_path, tmp_path / "data", "session", "bad", "value", "generated", "hal", "c"))
    assert result.ok is False
    assert result.code == "CREATION_INPUT_INVALID"
    assert "CreationInputError" not in result.message


def test_support_profile_rejects_path_outside_data_root(tmp_path: Path):
    outside = tmp_path.parent / "bad-profile.json"
    outside.write_text("{}", encoding="utf-8")
    with pytest.raises(SupportProfileError):
        discover_tool_support(
            SupportProfileRequest(profile_path=outside, data_root=tmp_path / "data")
        )


def test_workflow_uses_injected_fixed_clock_for_reproducible_plan(tmp_path: Path, monkeypatch):
    import stm32_toolkit.creation_workflows as workflows
    from stm32_toolkit.tool_support import ToolSupportProfile

    fixed = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(workflows, "_now_factory", lambda: fixed)
    support = ToolSupportProfile("3.12.10", None, None, None, None, None, None, (), ())
    monkeypatch.setattr(workflows, "discover_tool_support", lambda request: support)
    request = CreationPlanWorkflowRequest(
        tmp_path,
        tmp_path / "data",
        "session",
        "mcu",
        "STM32F429ZITx",
        "generated",
        "hal",
        "c",
    )
    result = plan_creation_workflow(request)
    assert result.ok is True
    assert result.data["expiresAt"] == "2026-08-23T13:00:00Z"


def test_workflow_environment_failure_is_closed_and_has_no_host_path(tmp_path: Path, monkeypatch):
    import stm32_toolkit.creation_workflows as workflows

    leaked = str(tmp_path / "secret-tool.exe")
    def fail(_request):
        raise SupportProfileError(f"invalid candidate {leaked}")

    monkeypatch.setattr(workflows, "discover_tool_support", fail)
    result = plan_creation_workflow(
        CreationPlanWorkflowRequest(
            tmp_path,
            tmp_path / "data",
            "session",
            "mcu",
            "STM32F429ZITx",
            "generated",
            "hal",
            "c",
        )
    )
    assert result.ok is False
    assert result.code == "CREATION_ENVIRONMENT_INVALID"
    assert leaked not in result.message
    assert leaked not in str(result.details)


def test_prepare_is_read_only_and_never_invokes_cubemx(tmp_path: Path, monkeypatch):
    import stm32_toolkit.creation_workflows as workflows
    from stm32_toolkit.tool_support import ToolSupportProfile

    calls: list[str] = []
    monkeypatch.setattr(workflows, "discover_creation_environment", lambda *args, **kwargs: calls.append("environment") or type("E", (), {"digest": "c" * 64})())
    monkeypatch.setattr(workflows, "discover_tool_support", lambda request: ToolSupportProfile("3.12.10", None, None, None, None, None, None, (), ()))
    request = CreationPlanWorkflowRequest(tmp_path, tmp_path / "data", "session", "mcu", "STM32F429ZITx", "generated", "hal", "c")
    planned = plan_creation_workflow(request)
    assert planned.ok is True
    result = workflows.prepare_creation_workflow(request, plan_id="a" * 64, action_digest="b" * 64)
    assert result.code == "CREATION_PLAN_CHANGED"
    assert calls == []
    assert tuple(tmp_path.rglob("*")) == ()


def test_prepare_requires_exact_plan_and_action_digests(tmp_path: Path, monkeypatch):
    import stm32_toolkit.creation_workflows as workflows
    from stm32_toolkit.tool_support import ToolSupportProfile

    support = ToolSupportProfile("3.12.10", None, None, None, None, None, None, (), ())
    monkeypatch.setattr(workflows, "discover_tool_support", lambda request: support)
    request = CreationPlanWorkflowRequest(tmp_path, tmp_path / "data", "session", "mcu", "STM32F429ZITx", "generated", "hal", "c")
    planned = plan_creation_workflow(request)
    assert planned.ok is True
    result = workflows.prepare_creation_workflow(request, plan_id="a" * 64, action_digest="b" * 64)
    assert result.code == "CREATION_PLAN_CHANGED"


def test_apply_consumes_before_environment_discovery_failure(tmp_path: Path, monkeypatch):
    import stm32_toolkit.creation_workflows as workflows
    from stm32_toolkit.tool_support import ToolSupportProfile

    data_root = tmp_path / "data"
    creation_request = CreationRequest.from_mcu(
        "STM32F429ZITx", "generated", framework="hal", language="c"
    )
    store = CreationAuthorizationStore(
        data_root,
        now=lambda: datetime(2026, 8, 23, 12, tzinfo=timezone.utc),
        nonce_factory=lambda: "nonce",
    )
    prepared = store.prepare(
        CreationPrepareRequest(
            creation_request,
            tmp_path,
            "a" * 64,
            "b" * 64,
            "c" * 64,
            "2026-08-23T13:00:00Z",
        )
    )
    monkeypatch.setattr(
        workflows,
        "discover_creation_environment",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            CreationEnvironmentError("CUBEMX_REPOSITORY_MISSING", "repository unavailable")
        ),
    )
    support = ToolSupportProfile("3.12.10", None, None, None, None, None, None, (), ())
    result = apply_creation_workflow(
        CreationPlanWorkflowRequest(
            tmp_path,
            data_root,
            "session",
            "mcu",
            "STM32F429ZITx",
            "generated",
            "hal",
            "c",
        ),
        authorization_digest=prepared.authorization_digest,
        authorized=True,
        store=store,
        support_profile=support,
    )
    assert result.code == "CUBEMX_REPOSITORY_MISSING"
    with pytest.raises(CreationAuthorizationError) as error:
        store.consume(prepared.authorization_digest, authorized=True)
    assert error.value.code == "CREATION_AUTHORIZATION_CONSUMED"
