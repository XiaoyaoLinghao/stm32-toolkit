"""Thin CLI/MCP-neutral adapter for the VS07-A creation plan."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from stm32_toolkit.generation.creation import CreationInputError, CreationRequest, plan_project_creation
from stm32_toolkit.result import OperationResult
from stm32_toolkit.tool_support import SupportProfileRequest, SupportProfileError, ToolSupportProfile, discover_tool_support


@dataclass(frozen=True, slots=True)
class CreationPlanWorkflowRequest:
    project_root: Path
    data_root: Path
    session_id: str
    source_kind: str
    source_value: str
    destination: str
    framework: str
    language: str


_now_factory = lambda: datetime.now(timezone.utc)


def _request(value: CreationPlanWorkflowRequest) -> CreationRequest:
    if value.source_kind == "mcu":
        return CreationRequest.from_mcu(value.source_value, value.destination, framework=value.framework, language=value.language)
    if value.source_kind == "board":
        return CreationRequest.from_board(value.source_value, value.destination, framework=value.framework, language=value.language)
    if value.source_kind == "ioc":
        return CreationRequest.from_ioc(value.source_value, value.destination, framework=value.framework, language=value.language)
    raise CreationInputError("CREATION_SOURCE_INVALID", "sourceKind")


def plan_creation_workflow(request: CreationPlanWorkflowRequest, *, support_profile: ToolSupportProfile | None = None) -> OperationResult[dict[str, object]]:
    try:
        creation_request = _request(request)
        support = support_profile or discover_tool_support(SupportProfileRequest(data_root=request.data_root))
        plan = plan_project_creation(request.project_root, creation_request, support, now=_now_factory())
        return OperationResult.success("project-create-plan", {**plan.to_dict(), "mutated": False})
    except CreationInputError as error:
        return OperationResult.failure("project-create-plan", "CREATION_INPUT_INVALID", "Creation request is invalid", {"field": error.field})
    except (OSError, ValueError, RuntimeError, SupportProfileError):
        return OperationResult.failure("project-create-plan", "CREATION_ENVIRONMENT_INVALID", "Creation environment is unavailable", {})
