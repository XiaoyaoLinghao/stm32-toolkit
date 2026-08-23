"""CLI/MCP-neutral adapters for VS07-A planning and VS07-B authorization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from stm32_toolkit.creation_authorization import (
    CreationAuthorizationError,
    CreationAuthorizationStore,
    CreationPrepareRequest,
)
from stm32_toolkit.creation_environment import CreationEnvironmentError, discover_creation_environment
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


def prepare_creation_workflow(
    request: CreationPlanWorkflowRequest,
    *,
    plan_id: str,
    action_digest: str,
    support_profile: ToolSupportProfile | None = None,
    repository: Path | None = None,
    store: CreationAuthorizationStore | None = None,
) -> OperationResult[dict[str, object]]:
    """Re-plan and issue one expiring, single-use creation capability.

    Preparation validates every prerequisite and writes only the authorization
    record under the caller's Toolkit data root.  It never starts CubeMX and
    never creates, removes, or changes the requested destination.
    """
    operation = "project-create-prepare"
    try:
        creation_request = _request(request)
        support = support_profile or discover_tool_support(
            SupportProfileRequest(data_root=request.data_root)
        )
        plan = plan_project_creation(
            request.project_root,
            creation_request,
            support,
            now=_now_factory(),
        )
    except CreationInputError as error:
        return OperationResult.failure(operation, "CREATION_INPUT_INVALID", "Creation request is invalid", {"field": error.field})
    except (OSError, ValueError, RuntimeError, SupportProfileError):
        return OperationResult.failure(operation, "CREATION_ENVIRONMENT_INVALID", "Creation environment is unavailable", {})
    if type(plan_id) is not str or type(action_digest) is not str:
        return OperationResult.failure(operation, "CREATION_PLAN_CHANGED", "The creation plan is not the current plan", {"currentPlanId": plan.plan_id, "currentActionDigest": plan.action_digest})
    if plan_id != plan.plan_id or action_digest != plan.action_digest:
        return OperationResult.failure(
            operation,
            "CREATION_PLAN_CHANGED",
            "The creation plan changed since planning",
            {"currentPlanId": plan.plan_id, "currentActionDigest": plan.action_digest},
        )
    if plan.blockers:
        blockers = [blocker.to_dict() for blocker in plan.blockers]
        first = plan.blockers[0]
        return OperationResult.failure(operation, first.code, "Creation prerequisites are unavailable", {"blockers": blockers})
    try:
        environment = discover_creation_environment(support, plan.request, repository=repository)
        authorization_store = store or CreationAuthorizationStore(request.data_root)
        authorization = authorization_store.prepare(
            CreationPrepareRequest(
                request=plan.request,
                project_root=request.project_root.expanduser().resolve(strict=True),
                plan_id=plan.plan_id,
                action_digest=plan.action_digest,
                environment_digest=environment.digest,
                expires_at=plan.expires_at,
            )
        )
    except CreationEnvironmentError as error:
        return OperationResult.failure(operation, error.code, error.message, {})
    except CreationAuthorizationError as error:
        return OperationResult.failure(operation, error.code, error.message, error.details)
    except (OSError, ValueError, RuntimeError):
        return OperationResult.failure(operation, "CREATION_AUTHORIZATION_INVALID", "Creation authorization could not be prepared", {})
    return OperationResult.success(
        operation,
        {
            **plan.to_dict(),
            **authorization.to_dict(),
            "executionEnvironmentDigest": environment.digest,
            "mutated": False,
        },
    )
