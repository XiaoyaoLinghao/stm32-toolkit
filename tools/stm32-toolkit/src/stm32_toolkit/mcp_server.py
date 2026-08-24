from __future__ import annotations

import asyncio
import argparse
import os
import re
import stat
import sys
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit
from urllib.request import url2pathname

from mcp.server.fastmcp import Context, FastMCP
from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    model_validator,
)

from stm32_toolkit.public_inventory import MCP_TOOL_NAMES
from stm32_toolkit.acceptance.workflows import (
    AcceptanceWorkflowContext,
    describe_acceptance_scenario,
    record_acceptance_scenario,
    show_acceptance_scenario,
)
from stm32_toolkit.acceptance.recovery_workflows import (
    AcceptanceRecoveryContext,
    authorize_acceptance_source_change,
    begin_acceptance_attempt,
    checkpoint_acceptance_attempt,
    resume_acceptance_attempt,
    show_acceptance_attempt,
)
from stm32_toolkit.context import build_project_context
from stm32_toolkit.creation_workflows import (
    CreationPlanWorkflowRequest,
    apply_creation_workflow,
    plan_creation_workflow,
    prepare_creation_workflow,
)
from stm32_toolkit.regeneration import RegenerationWorkflowRequest
from stm32_toolkit.regeneration_workflows import (
    RegenerationAuthorizationStore,
    apply_regeneration_workflow,
    prepare_regeneration_workflow,
)
from stm32_toolkit.detection import detect_project
from stm32_toolkit.diagnostic_workflows import (
    DiagnosticWorkflowContext,
    diagnostic_add_verification_plan,
    diagnostic_add_plan,
    diagnostic_add_hypothesis,
    diagnostic_assess_hypothesis,
    diagnostic_attach_marker,
    diagnostic_begin,
    diagnostic_complete_verification,
    diagnostic_declare_source_change,
    diagnostic_run_plan,
    diagnostic_show,
    diagnostic_show_verification,
    diagnostic_start,
    diagnostic_start_verification,
)
from stm32_toolkit.doctor import run_doctor
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
from stm32_toolkit.identity import canonical_project_root, new_session_id
from stm32_toolkit.paths import require_safe_session_id
from stm32_toolkit.result import OperationResult
from stm32_toolkit.tool_support import ToolSupportProfile, SupportProfileRequest, discover_tool_support
from stm32_toolkit.workflows import (
    build_firmware_workflow,
    configure_project_workflow,
    convert_keil_workflow,
    inspect_keil_workflow,
)
from stm32_toolkit.testing_workflows import (
    TestingWorkflowContext,
    host_test_discover,
    host_test_run,
    target_test_prepare,
    target_test_execute,
    target_replay_run,
    test_show,
)
from stm32_toolkit.evidence.model import MAX_ARTIFACT_BYTES
from stm32_toolkit.testing.model import MAX_CASES, MAX_STRING_BYTES


_SERVER_NAME = "STM32 Toolkit"
_SERVER_INSTRUCTIONS = (
    "This server is permanently bound to one project root and exposes "
    "read-only inspection, planning, probe discovery, and observation plus "
    "explicitly authorized conversion, configuration, build, flash, and "
    "debug handoff operations."
)
_CLIENT_ROOTS_TIMEOUT_SECONDS = 5.0
_DIGEST_PATTERN = r"^[0-9a-f]{64}$"
_PROBE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
_RUN_ID_PATTERN = r"^[a-z0-9][a-z0-9._-]*$"
_DIAGNOSTIC_OPERATION_PATTERN = r"^[a-z0-9][a-z0-9._-]{0,127}$"
_DIAGNOSTIC_SESSION_PATTERN = r"^[0-9a-f]{32}$"
_DIAGNOSTIC_PLAN_PATTERN = r"^[0-9a-f]{64}$"
_ACCEPTANCE_UUID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
_PORTABLE_PATH_MAX_BYTES = 4096
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _validate_test_string(value: str) -> str:
    if (
        not value
        or unicodedata.normalize("NFC", value) != value
        or len(value.encode("utf-8")) > MAX_STRING_BYTES
    ):
        raise ValueError("test string must be non-empty, NFC, and within 65536 UTF-8 bytes")
    return value


ProbeId = Annotated[str, Field(pattern=_PROBE_PATTERN)]
Digest = Annotated[str, Field(pattern=_DIGEST_PATTERN)]
RunId = Annotated[
    str,
    Field(
        pattern=_RUN_ID_PATTERN,
        min_length=1,
        max_length=MAX_STRING_BYTES,
    ),
    AfterValidator(_validate_test_string),
]


DiagnosticOperationId = Annotated[
    str,
    Field(
        pattern=_DIAGNOSTIC_OPERATION_PATTERN,
        min_length=1,
        max_length=128,
    ),
]


DiagnosticSessionId = Annotated[
    str,
    Field(
        pattern=_DIAGNOSTIC_SESSION_PATTERN,
        min_length=32,
        max_length=32,
    ),
]


DiagnosticActor = Literal["user", "tool", "ai-client"]
DiagnosticFailedRunMode = Literal["host", "target"]
DiagnosticRevision = Annotated[StrictInt, Field(ge=0, le=10_000)]
DiagnosticText = Annotated[
    str,
    Field(min_length=1, max_length=MAX_STRING_BYTES),
    AfterValidator(_validate_test_string),
]
DiagnosticHypothesisId = Annotated[
    str,
    Field(
        pattern=_DIAGNOSTIC_SESSION_PATTERN,
        min_length=32,
        max_length=32,
    ),
]
DiagnosticPlanId = Annotated[
    str,
    Field(
        pattern=_DIAGNOSTIC_PLAN_PATTERN,
        min_length=64,
        max_length=64,
    ),
]
DiagnosticStepId = Annotated[
    str,
    Field(
        pattern=_DIAGNOSTIC_OPERATION_PATTERN,
        min_length=1,
        max_length=128,
    ),
]
DiagnosticPolarity = Literal["supports", "refutes"]

AcceptanceScenarioId = Literal["legacy-keil-migration", "new-cubemx-project"]
AcceptanceScenarioVersion = Literal["1"]
AcceptanceUuid = Annotated[
    StrictStr,
    Field(pattern=_ACCEPTANCE_UUID_PATTERN, min_length=36, max_length=36),
]
AcceptanceRevision = Annotated[StrictInt, Field(ge=0, le=7)]
AcceptanceAttemptStage = Literal[
    "project-materialized",
    "firmware-built-before",
    "target-failure-replayed",
    "diagnosis-completed",
    "firmware-built-after",
    "target-fix-verified",
]


def _validate_portable_project_path(value: str) -> str:
    """Validate the wire spelling of a project-relative file path."""
    if (
        not value
        or unicodedata.normalize("NFC", value) != value
        or "\\" in value
        or ":" in value
        or value.startswith("/")
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError("path must be a portable project-relative path")
    try:
        if len(value.encode("utf-8")) > _PORTABLE_PATH_MAX_BYTES:
            raise ValueError("path must be a portable project-relative path")
    except UnicodeEncodeError:
        raise ValueError("path must be a portable project-relative path") from None
    parts = value.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        raise ValueError("path must be a portable project-relative path")
    return value


ProjectRelativePath = Annotated[
    str,
    Field(min_length=1, max_length=_PORTABLE_PATH_MAX_BYTES),
    AfterValidator(_validate_portable_project_path),
]


def _reject_json_tuple(value: object) -> object:
    if isinstance(value, tuple):
        raise ValueError("JSON arrays must not be tuples")
    return value


JsonArray = Annotated[list[object], BeforeValidator(_reject_json_tuple)]


class DiagnosticArtifactInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sha256: Digest
    size_bytes: Annotated[StrictInt, Field(ge=0, le=MAX_ARTIFACT_BYTES)]
    relative_path: DiagnosticText
    kind: DiagnosticText
    media_type: DiagnosticText


class SourceChangeDeclarationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Literal["stm32-source-change-declaration/1"] = Field(
        alias="schema"
    )
    declaration_id: Digest
    before_source_sha256: Digest
    after_source_sha256: Digest
    before_build_id: Digest
    before_elf_sha256: Digest
    after_build_id: Digest
    after_elf_sha256: Digest
    changed_paths: Annotated[list[DiagnosticText], BeforeValidator(_reject_json_tuple), Field(min_length=1, max_length=128)]
    diff_evidence_id: Digest
    diff_artifact: DiagnosticArtifactInput
    claimed_hypothesis_ids: Annotated[
        list[DiagnosticHypothesisId],
        BeforeValidator(_reject_json_tuple),
        Field(min_length=1, max_length=16),
    ]
    validation_plan_id: Digest


class VerificationPlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Literal["stm32-verification-plan/1"] = Field(alias="schema")
    verification_plan_id: Digest
    diagnostic_session_id: DiagnosticSessionId
    failed_before_run_id: RunId
    failed_before_evidence_id: Digest
    source_change_declaration_id: Digest
    fixed_after_run_id: RunId
    fixed_after_evidence_id: Digest
    required_analysis_ids: Annotated[
        list[Digest], BeforeValidator(_reject_json_tuple), Field(min_length=1, max_length=16)
    ]
    required_analysis_evidence_ids: Annotated[
        list[Digest], BeforeValidator(_reject_json_tuple), Field(min_length=1, max_length=16)
    ]
    required_monitor_quality: Literal["VALID"]
    expected_changed: StrictBool
    plan_digest: Digest


class DiagnosticMarkerInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Literal["stm32-diagnostic-marker-ref/1"] = Field(alias="schema")
    marker_id: Digest
    marker_evidence_id: Digest
    analysis_id: Digest
    analysis_evidence_id: Digest
    diagnostic_session_id: DiagnosticSessionId
    hypothesis_id: DiagnosticHypothesisId
    polarity: DiagnosticPolarity
    label: Literal["change-observed", "no-change-observed", "analysis-inconclusive"]
    rationale: Annotated[str, Field(min_length=1, max_length=4096), AfterValidator(_validate_test_string)]

DiagnosticRunState = Literal[
    "discovered",
    "running",
    "passed",
    "failed",
    "error",
    "cancelled",
]
DiagnosticCaseState = Literal["passed", "failed", "skipped", "error", "timeout"]
DiagnosticCount = Annotated[StrictInt, Field(ge=0, le=100_000)]


class DiagnosticRunStateSelector(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["run-state"]


class DiagnosticCaseStateSelector(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["case-state"]
    case_id: DiagnosticText


class DiagnosticCaseCountSelector(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["case-count"]
    state: DiagnosticCaseState


DiagnosticSelector = Annotated[
    DiagnosticRunStateSelector
    | DiagnosticCaseStateSelector
    | DiagnosticCaseCountSelector,
    Field(discriminator="kind"),
]
DiagnosticExpectedValue = DiagnosticRunState | DiagnosticCaseState | DiagnosticCount


class DiagnosticObservationStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: DiagnosticStepId
    selector: DiagnosticSelector
    expected_value: DiagnosticExpectedValue
    purpose: DiagnosticText

    @model_validator(mode="after")
    def _validate_expected_value(self) -> "DiagnosticObservationStep":
        kind = self.selector.kind
        if kind == "run-state" and self.expected_value not in {
            "discovered",
            "running",
            "passed",
            "failed",
            "error",
            "cancelled",
        }:
            raise ValueError("expected value is incompatible with selector")
        if kind == "case-state" and self.expected_value not in {
            "passed",
            "failed",
            "skipped",
            "error",
            "timeout",
        }:
            raise ValueError("expected value is incompatible with selector")
        if kind == "case-count" and type(self.expected_value) is not int:
            raise ValueError("expected value is incompatible with selector")
        return self


def _reject_plan_steps_tuple(value: object) -> object:
    if isinstance(value, tuple):
        raise ValueError("steps must be a JSON array")
    return value


def _unique_diagnostic_step_ids(
    value: list[DiagnosticObservationStep],
) -> list[DiagnosticObservationStep]:
    if len({step.step_id for step in value}) != len(value):
        raise ValueError("step IDs must be unique")
    return value


DiagnosticPlanSteps = Annotated[
    list[DiagnosticObservationStep],
    BeforeValidator(_reject_plan_steps_tuple),
    Field(min_length=1, max_length=64),
    AfterValidator(_unique_diagnostic_step_ids),
]
Items = Annotated[list[str], Field(min_length=1, max_length=256)]


CaseId = Annotated[
    str,
    Field(min_length=1, max_length=MAX_STRING_BYTES),
    AfterValidator(_validate_test_string),
]


def _unique_case_ids(value: list[str] | None) -> list[str] | None:
    if value is not None and len(value) != len(set(value)):
        raise ValueError("caseIds must be unique")
    return value


UniqueCaseIds = Annotated[
    list[CaseId] | None,
    Field(max_length=MAX_CASES),
    AfterValidator(_unique_case_ids),
]


@dataclass(frozen=True)
class ServerRuntime:
    """Immutable, canonical project and data roots for one MCP process."""

    project_root: Path
    data_root: Path
    session_id: str
    support_profile: ToolSupportProfile

    @classmethod
    def create(
        cls,
        project_root: Path,
        data_root: Path,
        session_id: str | None = None,
    ) -> "ServerRuntime":
        try:
            canonical_project = canonical_project_root(project_root)
        except (OSError, ValueError) as error:
            raise ValueError("project root does not exist") from error
        if not canonical_project.is_dir():
            raise ValueError("project root is not a directory")

        resolved_session_id = require_safe_session_id(
            session_id if session_id is not None else new_session_id()
        )

        try:
            canonical_data = data_root.expanduser().resolve(strict=False)
        except (OSError, ValueError) as error:
            raise ValueError("data root is not available") from error
        _require_external_data_root(canonical_data, canonical_project)

        try:
            canonical_data.mkdir(exist_ok=True)
            canonical_data = canonical_data.resolve(strict=True)
        except (OSError, ValueError) as error:
            raise ValueError("data root is not available") from error
        if not canonical_data.is_dir():
            raise ValueError("data root is not a directory")
        _require_external_data_root(canonical_data, canonical_project)

        support = discover_tool_support(SupportProfileRequest(data_root=canonical_data), probe_versions=True)
        return cls(canonical_project, canonical_data, resolved_session_id, support)


def _require_external_data_root(data_root: Path, project_root: Path) -> None:
    try:
        data_root.relative_to(project_root)
    except ValueError:
        return
    raise ValueError("data root must be outside project root")


def tool_doctor(runtime: ServerRuntime) -> dict[str, object]:
    """Return the read-only environment diagnosis for the bound project."""
    return run_doctor(
        runtime.project_root,
        data_root=runtime.data_root,
        support_profile=runtime.support_profile,
    ).to_dict()


def tool_project_detect(runtime: ServerRuntime) -> dict[str, object]:
    """Return project markers for the bound project."""
    try:
        detection = detect_project(runtime.project_root)
    except (OSError, ValueError):
        return OperationResult.failure(
            "project.detect",
            "PROJECT_DETECTION_UNAVAILABLE",
            "Project detection is not available",
            {"path": str(runtime.project_root)},
        ).to_dict()
    return OperationResult.success("project.detect", detection.to_dict()).to_dict()


def tool_project_context(runtime: ServerRuntime) -> dict[str, object]:
    """Return context evidence using the runtime's stable session identifier."""
    return build_project_context(
        runtime.project_root,
        runtime.data_root,
        runtime.session_id,
    ).to_dict()


def tool_project_create_plan(
    runtime: ServerRuntime,
    source_kind: str,
    source: str,
    destination: str,
    framework: str,
    language: str,
) -> dict[str, object]:
    """Return a read-only CubeMX creation plan bound to this runtime."""
    request = CreationPlanWorkflowRequest(
        runtime.project_root,
        runtime.data_root,
        runtime.session_id,
        source_kind,
        source,
        destination,
        framework,
        language,
    )
    return plan_creation_workflow(request, support_profile=runtime.support_profile).to_dict()


def tool_project_create_prepare(
    runtime: ServerRuntime,
    source_kind: str,
    source: str,
    destination: str,
    framework: str,
    language: str,
    plan_id: str,
    action_digest: str,
) -> dict[str, object]:
    """Issue one single-use authorization for an exact VS07-A plan."""
    request = CreationPlanWorkflowRequest(
        runtime.project_root,
        runtime.data_root,
        runtime.session_id,
        source_kind,
        source,
        destination,
        framework,
        language,
    )
    result = prepare_creation_workflow(
        request,
        plan_id=plan_id,
        action_digest=action_digest,
        support_profile=runtime.support_profile,
    )
    return result.to_dict() if hasattr(result, "to_dict") else result


def tool_project_create_apply(
    runtime: ServerRuntime,
    authorization_digest: str,
    authorized: bool,
) -> dict[str, object]:
    """Consume one authorization and run the staged creation flow."""
    request = CreationPlanWorkflowRequest(
        runtime.project_root,
        runtime.data_root,
        runtime.session_id,
        "mcu",
        "STM32F429ZITx",
        "generated",
        "hal",
        "c",
    )
    result = apply_creation_workflow(
        request,
        authorization_digest=authorization_digest,
        authorized=authorized,
        support_profile=runtime.support_profile,
    )
    return result.to_dict() if hasattr(result, "to_dict") else result


def tool_project_regenerate_plan(
    runtime: ServerRuntime,
    destination: str,
) -> dict[str, object]:
    request = RegenerationWorkflowRequest(runtime.project_root, runtime.data_root, runtime.session_id, destination)
    from stm32_toolkit.regeneration import plan_regeneration

    return plan_regeneration(request, support_profile=runtime.support_profile).to_dict()


def tool_project_regenerate_prepare(
    runtime: ServerRuntime,
    destination: str,
    plan_id: str,
    action_digest: str,
    authorized: bool,
) -> dict[str, object]:
    request = RegenerationWorkflowRequest(runtime.project_root, runtime.data_root, runtime.session_id, destination)
    result = prepare_regeneration_workflow(
        request,
        plan_id=plan_id,
        action_digest=action_digest,
        authorized=authorized,
        support_profile=runtime.support_profile,
    )
    return result.to_dict()


def tool_project_regenerate_apply(
    runtime: ServerRuntime,
    authorization_digest: str,
    authorized: bool,
) -> dict[str, object]:
    store = RegenerationAuthorizationStore(runtime.data_root)
    try:
        destination = store.peek(authorization_digest).destination
    except Exception:
        destination = "invalid"
    request = RegenerationWorkflowRequest(runtime.project_root, runtime.data_root, runtime.session_id, destination)
    result = apply_regeneration_workflow(
        request,
        authorization_digest=authorization_digest,
        authorized=authorized,
        support_profile=runtime.support_profile,
        store=store,
    )
    return result.to_dict()


def tool_keil_inspect(
    runtime: ServerRuntime,
    uvprojx: str | None = None,
    target_name: str | None = None,
    include_baseline: bool = True,
) -> dict[str, object]:
    """Read-only Keil inspection and baseline for the bound project."""
    return inspect_keil_workflow(
        runtime.project_root,
        uvprojx=uvprojx,
        target_name=target_name,
        include_baseline=include_baseline,
    ).to_dict()


def tool_keil_convert(
    runtime: ServerRuntime,
    uvprojx: str | None = None,
    target_name: str | None = None,
    plan_id: str | None = None,
    authorized: bool = False,
) -> dict[str, object]:
    """Read-only conversion plan, or apply with the exact plan ID plus
    ``authorized=true``."""
    return convert_keil_workflow(
        runtime.project_root,
        uvprojx=uvprojx,
        target_name=target_name,
        plan_id=plan_id,
        authorized=authorized,
    ).to_dict()


def tool_project_configure(
    runtime: ServerRuntime,
    plan_id: str | None = None,
    authorized: bool = False,
) -> dict[str, object]:
    """Read-only configuration plan, or apply with the exact plan ID plus
    ``authorized=true``."""
    return configure_project_workflow(
        runtime.project_root,
        plan_id=plan_id,
        authorized=authorized,
    ).to_dict()


def tool_build(
    runtime: ServerRuntime,
    preset: str,
    clean: bool = False,
    timeout_seconds: int = 300,
    authorized: bool = False,
) -> dict[str, object]:
    """Run the guarded build for the bound project with explicit
    ``authorized=true``."""
    return build_firmware_workflow(
        runtime.project_root,
        preset=preset,
        clean=clean,
        timeout_seconds=timeout_seconds,
        authorized=authorized,
    ).to_dict()


async def tool_doctor_for_request(
    runtime: ServerRuntime, context: Context | None
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "doctor")
    return failure if failure is not None else tool_doctor(runtime)


async def tool_project_detect_for_request(
    runtime: ServerRuntime, context: Context | None
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "project.detect")
    return failure if failure is not None else tool_project_detect(runtime)


async def tool_project_context_for_request(
    runtime: ServerRuntime, context: Context | None
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "project.context")
    return failure if failure is not None else tool_project_context(runtime)


async def tool_project_create_plan_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    source_kind: str,
    source: str,
    destination: str,
    framework: str,
    language: str,
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "project-create-plan")
    return failure if failure is not None else tool_project_create_plan(runtime, source_kind, source, destination, framework, language)


async def tool_project_create_prepare_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    source_kind: str,
    source: str,
    destination: str,
    framework: str,
    language: str,
    plan_id: str,
    action_digest: str,
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "project-create-prepare")
    if failure is not None:
        return failure
    return tool_project_create_prepare(runtime, source_kind, source, destination, framework, language, plan_id, action_digest)


async def tool_project_create_apply_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    authorization_digest: str,
    authorized: bool,
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "project-create-apply")
    if failure is not None:
        return failure
    return tool_project_create_apply(runtime, authorization_digest, authorized)


async def tool_project_regenerate_plan_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    destination: str,
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "project-regenerate-plan")
    if failure is not None:
        return failure
    try:
        return tool_project_regenerate_plan(runtime, destination)
    except ValueError:
        return OperationResult.failure("project-regenerate-plan", "REGENERATION_INPUT_INVALID", "regeneration input is invalid", {}).to_dict()


async def tool_project_regenerate_prepare_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    destination: str,
    plan_id: str,
    action_digest: str,
    authorized: bool,
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "project-regenerate-prepare")
    if failure is not None:
        return failure
    try:
        return tool_project_regenerate_prepare(runtime, destination, plan_id, action_digest, authorized)
    except ValueError:
        return OperationResult.failure("project-regenerate-prepare", "REGENERATION_INPUT_INVALID", "regeneration input is invalid", {}).to_dict()


async def tool_project_regenerate_apply_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    authorization_digest: str,
    authorized: bool,
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "project-regenerate-apply")
    if failure is not None:
        return failure
    return tool_project_regenerate_apply(runtime, authorization_digest, authorized)


async def tool_keil_inspect_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    uvprojx: str | None = None,
    target_name: str | None = None,
    include_baseline: bool = True,
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "keil-inspect")
    if failure is not None:
        return failure
    return tool_keil_inspect(runtime, uvprojx, target_name, include_baseline)


async def tool_keil_convert_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    uvprojx: str | None = None,
    target_name: str | None = None,
    plan_id: str | None = None,
    authorized: bool = False,
) -> dict[str, object]:
    operation = (
        "keil-conversion-apply"
        if plan_id is not None or authorized is not False
        else "keil-conversion-plan"
    )
    failure = await _client_roots_failure(runtime, context, operation)
    if failure is not None:
        return failure
    return tool_keil_convert(runtime, uvprojx, target_name, plan_id, authorized)


async def tool_project_configure_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    plan_id: str | None = None,
    authorized: bool = False,
) -> dict[str, object]:
    operation = (
        "project-configuration-apply"
        if plan_id is not None or authorized is not False
        else "project-configuration-plan"
    )
    failure = await _client_roots_failure(runtime, context, operation)
    if failure is not None:
        return failure
    return tool_project_configure(runtime, plan_id, authorized)


async def tool_build_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    preset: str,
    clean: bool = False,
    timeout_seconds: int = 300,
    authorized: bool = False,
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "build")
    if failure is not None:
        return failure
    return tool_build(runtime, preset, clean, timeout_seconds, authorized)


async def _hardware_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    operation: str,
    request: object,
    workflow: Callable[[object], Awaitable[OperationResult[object]]],
) -> dict[str, object]:
    """Run one project-bound hardware workflow after validating client roots."""
    failure = await _client_roots_failure(runtime, context, operation)
    if failure is not None:
        return failure
    try:
        result = await workflow(request)
        if not isinstance(result, OperationResult):
            raise TypeError("hardware workflow returned an invalid result")
        return result.to_dict()
    except asyncio.CancelledError:
        raise
    except Exception:
        return OperationResult.failure(
            operation,
            "HARDWARE_INTERNAL_ERROR",
            "Hardware workflow failed",
            {},
        ).to_dict()


async def tool_probe_list_for_request(
    runtime: ServerRuntime, context: Context | None
) -> dict[str, object]:
    return await _hardware_for_request(
        runtime,
        context,
        "stm32_probe_list",
        ProbeListWorkflowRequest(runtime.project_root, runtime.data_root, runtime.session_id),
        probe_list_workflow,
    )


def _authorization_failure(operation: str) -> dict[str, object]:
    return OperationResult.failure(
        operation,
        "AUTHORIZATION_REQUIRED",
        "Explicit hardware authorization is required",
        {},
    ).to_dict()


async def tool_flash_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    probe_id: str,
    expected_build_id: str,
    expected_elf_sha256: str,
    authorized: object = False,
) -> dict[str, object]:
    operation = "stm32_flash"
    failure = await _client_roots_failure(runtime, context, operation)
    if failure is not None:
        return failure
    if authorized is not True:
        return _authorization_failure(operation)
    return await _hardware_for_request(
        runtime,
        None,
        operation,
        FlashWorkflowRequest(
            runtime.project_root,
            runtime.data_root,
            runtime.session_id,
            probe_id,
            expected_build_id,
            expected_elf_sha256,
            True,
        ),
        flash_workflow,
    )


async def tool_handoff_begin_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    probe_id: str,
    expected_build_id: str,
    expected_elf_sha256: str,
    authorized: object = False,
    previous_watch_selection: list[str] | tuple[str, ...] = (),
) -> dict[str, object]:
    operation = "stm32_debug_handoff_begin"
    failure = await _client_roots_failure(runtime, context, operation)
    if failure is not None:
        return failure
    if authorized is not True:
        return _authorization_failure(operation)
    return await _hardware_for_request(
        runtime,
        None,
        operation,
        HandoffBeginWorkflowRequest(
            runtime.project_root,
            runtime.data_root,
            runtime.session_id,
            probe_id,
            expected_build_id,
            expected_elf_sha256,
            True,
            tuple(previous_watch_selection),
        ),
        handoff_begin_workflow,
    )


async def tool_handoff_end_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    probe_id: str,
    ticket: str,
) -> dict[str, object]:
    return await _hardware_for_request(
        runtime,
        context,
        "stm32_debug_handoff_end",
        HandoffEndWorkflowRequest(
            runtime.project_root, runtime.data_root, runtime.session_id, probe_id, ticket
        ),
        handoff_end_workflow,
    )


async def tool_variable_read_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    probe_id: str,
    expected_build_id: str,
    expected_elf_sha256: str,
    expressions: list[str] | tuple[str, ...],
) -> dict[str, object]:
    return await _hardware_for_request(
        runtime,
        context,
        "stm32_variable_read",
        VariableReadWorkflowRequest(
            runtime.project_root,
            runtime.data_root,
            runtime.session_id,
            probe_id,
            expected_build_id,
            expected_elf_sha256,
            tuple(expressions),
        ),
        variable_read_workflow,
    )


async def tool_variable_sample_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    probe_id: str,
    expected_build_id: str,
    expected_elf_sha256: str,
    expressions: list[str] | tuple[str, ...],
    interval_ms: int,
    count: int | None = None,
    duration_ms: int | None = None,
) -> dict[str, object]:
    return await _hardware_for_request(
        runtime,
        context,
        "stm32_variable_sample",
        VariableSampleWorkflowRequest(
            runtime.project_root,
            runtime.data_root,
            runtime.session_id,
            probe_id,
            expected_build_id,
            expected_elf_sha256,
            tuple(expressions),
            interval_ms,
            count,
            duration_ms,
        ),
        variable_sample_workflow,
    )


async def tool_register_read_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    probe_id: str,
    expected_build_id: str,
    expected_elf_sha256: str,
    paths: list[str] | tuple[str, ...],
    acknowledge_access_risk: object = False,
) -> dict[str, object]:
    return await _hardware_for_request(
        runtime,
        context,
        "stm32_register_read",
        RegisterReadWorkflowRequest(
            runtime.project_root,
            runtime.data_root,
            runtime.session_id,
            probe_id,
            expected_build_id,
            expected_elf_sha256,
            tuple(paths),
            acknowledge_access_risk,
        ),
        register_read_workflow,
    )


async def tool_fault_analyze_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    probe_id: str,
    expected_build_id: str,
    expected_elf_sha256: str,
) -> dict[str, object]:
    return await _hardware_for_request(
        runtime,
        context,
        "stm32_fault_analyze",
        FaultWorkflowRequest(
            runtime.project_root,
            runtime.data_root,
            runtime.session_id,
            probe_id,
            expected_build_id,
            expected_elf_sha256,
        ),
        fault_workflow,
    )


def _testing_context(runtime: ServerRuntime) -> TestingWorkflowContext:
    return TestingWorkflowContext(
        project_root=runtime.project_root,
        data_root=runtime.data_root,
        session_id=runtime.session_id,
    )


def _diagnostic_context(runtime: ServerRuntime) -> DiagnosticWorkflowContext:
    return DiagnosticWorkflowContext(
        project_root=runtime.project_root,
        data_root=runtime.data_root,
        session_id=runtime.session_id,
    )


def _acceptance_context(runtime: ServerRuntime) -> AcceptanceWorkflowContext:
    return AcceptanceWorkflowContext(
        project_root=runtime.project_root,
        data_root=runtime.data_root,
        session_id=runtime.session_id,
    )


def _acceptance_recovery_context(runtime: ServerRuntime) -> AcceptanceRecoveryContext:
    return AcceptanceRecoveryContext(
        project_root=runtime.project_root,
        data_root=runtime.data_root,
        session_id=runtime.session_id,
    )


class _ProjectPathError(ValueError):
    """A caller path did not satisfy the MCP project-file boundary."""


def _path_component_is_link_or_reparse(info: object) -> bool:
    mode = getattr(info, "st_mode", 0)
    return stat.S_ISLNK(mode) or bool(getattr(info, "st_file_attributes", 0) & _REPARSE_POINT)


def _resolve_project_relative_file(runtime: ServerRuntime, value: str) -> Path:
    """Resolve one existing regular project file without following links."""
    try:
        normalized = _validate_portable_project_path(value)
        parts = normalized.split("/")
        candidate = runtime.project_root
        for index, part in enumerate(parts):
            candidate = candidate / part
            info = os.lstat(candidate)
            if _path_component_is_link_or_reparse(info):
                raise _ProjectPathError
            mode = getattr(info, "st_mode", 0)
            if index < len(parts) - 1 and not stat.S_ISDIR(mode):
                raise _ProjectPathError
            if index == len(parts) - 1 and not stat.S_ISREG(mode):
                raise _ProjectPathError
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(runtime.project_root)
        return resolved
    except _ProjectPathError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise _ProjectPathError from error


def _adapter_failure(operation: str, code: str, message: str) -> dict[str, object]:
    return OperationResult.failure(operation, code, message, {}).to_dict()


def _nested_model_data(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python", by_alias=True)
    return value


async def tool_test_target_replay_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    operation_id: DiagnosticOperationId,
    descriptor_path: ProjectRelativePath,
    stream_path: ProjectRelativePath,
) -> dict[str, object]:
    operation = "test.target.replay"
    failure = await _client_roots_failure(runtime, context, operation)
    if failure is not None:
        return failure
    try:
        descriptor_file = _resolve_project_relative_file(runtime, descriptor_path)
        stream_file = _resolve_project_relative_file(runtime, stream_path)
    except _ProjectPathError:
        return _adapter_failure(operation, "EVIDENCE_PATH_UNSAFE", "Evidence path is unsafe.")
    return target_replay_run(
        _testing_context(runtime),
        operation_id=operation_id,
        descriptor_file=descriptor_file,
        stream_file=stream_file,
    ).to_dict()


async def tool_diagnostic_declare_source_change_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    operation_id: DiagnosticOperationId,
    diagnostic_session_id: DiagnosticSessionId,
    expected_revision: DiagnosticRevision,
    source_change_declaration: SourceChangeDeclarationInput,
    actor: DiagnosticActor = "user",
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "diagnostic.source-change.declare")
    if failure is not None:
        return failure
    return diagnostic_declare_source_change(
        _diagnostic_context(runtime),
        operation_id=operation_id,
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=expected_revision,
        source_change_declaration=_nested_model_data(source_change_declaration),
        actor=actor,
    ).to_dict()


async def tool_diagnostic_add_verification_plan_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    operation_id: DiagnosticOperationId,
    diagnostic_session_id: DiagnosticSessionId,
    expected_revision: DiagnosticRevision,
    verification_plan: VerificationPlanInput,
    actor: DiagnosticActor = "user",
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "diagnostic.verification-plan.add")
    if failure is not None:
        return failure
    return diagnostic_add_verification_plan(
        _diagnostic_context(runtime),
        operation_id=operation_id,
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=expected_revision,
        verification_plan=_nested_model_data(verification_plan),
        actor=actor,
    ).to_dict()


async def tool_diagnostic_start_verification_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    operation_id: DiagnosticOperationId,
    diagnostic_session_id: DiagnosticSessionId,
    expected_revision: DiagnosticRevision,
    verification_plan_id: DiagnosticPlanId,
    actor: DiagnosticActor = "tool",
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "diagnostic.verification.start")
    if failure is not None:
        return failure
    return diagnostic_start_verification(
        _diagnostic_context(runtime),
        operation_id=operation_id,
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=expected_revision,
        verification_plan_id=verification_plan_id,
        actor=actor,
    ).to_dict()


async def tool_diagnostic_attach_marker_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    operation_id: DiagnosticOperationId,
    diagnostic_session_id: DiagnosticSessionId,
    expected_revision: DiagnosticRevision,
    diagnostic_marker_ref: DiagnosticMarkerInput,
    actor: DiagnosticActor = "tool",
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "diagnostic.marker.attach")
    if failure is not None:
        return failure
    return diagnostic_attach_marker(
        _diagnostic_context(runtime),
        operation_id=operation_id,
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=expected_revision,
        diagnostic_marker_ref=_nested_model_data(diagnostic_marker_ref),
        actor=actor,
    ).to_dict()


async def tool_diagnostic_complete_verification_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    operation_id: DiagnosticOperationId,
    diagnostic_session_id: DiagnosticSessionId,
    expected_revision: DiagnosticRevision,
    executed_operation_ids: list[DiagnosticOperationId],
    cancelled: StrictBool = False,
    actor: DiagnosticActor = "tool",
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "diagnostic.verification.complete")
    if failure is not None:
        return failure
    return diagnostic_complete_verification(
        _diagnostic_context(runtime),
        operation_id=operation_id,
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=expected_revision,
        executed_operation_ids=executed_operation_ids,
        cancelled=cancelled,
        actor=actor,
    ).to_dict()


async def tool_diagnostic_show_verification_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    diagnostic_session_id: DiagnosticSessionId,
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "diagnostic.verification.show")
    if failure is not None:
        return failure
    return diagnostic_show_verification(
        _diagnostic_context(runtime),
        diagnostic_session_id=diagnostic_session_id,
    ).to_dict()


async def tool_diagnostic_start_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    operation_id: DiagnosticOperationId,
    failed_test_run_id: RunId,
    actor: DiagnosticActor = "user",
    failed_run_mode: DiagnosticFailedRunMode = "host",
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "diagnostic.start")
    if failure is not None:
        return failure
    kwargs: dict[str, object] = {
        "operation_id": operation_id,
        "failed_test_run_id": failed_test_run_id,
        "actor": actor,
    }
    if failed_run_mode == "target":
        kwargs["failed_run_mode"] = "target"
    return diagnostic_start(
        _diagnostic_context(runtime),
        **kwargs,
    ).to_dict()


async def tool_diagnostic_show_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    diagnostic_session_id: DiagnosticSessionId,
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "diagnostic.show")
    if failure is not None:
        return failure
    return diagnostic_show(
        _diagnostic_context(runtime),
        diagnostic_session_id=diagnostic_session_id,
    ).to_dict()


async def tool_diagnostic_begin_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    operation_id: DiagnosticOperationId,
    diagnostic_session_id: DiagnosticSessionId,
    expected_revision: DiagnosticRevision,
    actor: DiagnosticActor = "user",
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "diagnostic.begin")
    if failure is not None:
        return failure
    return diagnostic_begin(
        _diagnostic_context(runtime),
        operation_id=operation_id,
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=expected_revision,
        actor=actor,
    ).to_dict()


async def tool_diagnostic_add_hypothesis_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    operation_id: DiagnosticOperationId,
    diagnostic_session_id: DiagnosticSessionId,
    expected_revision: DiagnosticRevision,
    statement: DiagnosticText,
    actor: DiagnosticActor = "user",
) -> dict[str, object]:
    failure = await _client_roots_failure(
        runtime, context, "diagnostic.hypothesis.add"
    )
    if failure is not None:
        return failure
    return diagnostic_add_hypothesis(
        _diagnostic_context(runtime),
        operation_id=operation_id,
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=expected_revision,
        statement=statement,
        actor=actor,
    ).to_dict()


async def tool_diagnostic_assess_hypothesis_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    operation_id: DiagnosticOperationId,
    diagnostic_session_id: DiagnosticSessionId,
    expected_revision: DiagnosticRevision,
    hypothesis_id: DiagnosticHypothesisId,
    plan_id: DiagnosticPlanId,
    step_id: DiagnosticStepId,
    polarity: DiagnosticPolarity,
    rationale: DiagnosticText,
    actor: DiagnosticActor = "user",
) -> dict[str, object]:
    failure = await _client_roots_failure(
        runtime, context, "diagnostic.hypothesis.assess"
    )
    if failure is not None:
        return failure
    return diagnostic_assess_hypothesis(
        _diagnostic_context(runtime),
        operation_id=operation_id,
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=expected_revision,
        hypothesis_id=hypothesis_id,
        plan_id=plan_id,
        step_id=step_id,
        polarity=polarity,
        rationale=rationale,
        actor=actor,
    ).to_dict()


async def tool_diagnostic_add_plan_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    operation_id: DiagnosticOperationId,
    diagnostic_session_id: DiagnosticSessionId,
    expected_revision: DiagnosticRevision,
    steps: list[dict[str, object]],
    actor: DiagnosticActor = "user",
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "diagnostic.plan.add")
    if failure is not None:
        return failure
    return diagnostic_add_plan(
        _diagnostic_context(runtime),
        operation_id=operation_id,
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=expected_revision,
        steps=steps,
        actor=actor,
    ).to_dict()


async def tool_diagnostic_run_plan_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    operation_id: DiagnosticOperationId,
    diagnostic_session_id: DiagnosticSessionId,
    expected_revision: DiagnosticRevision,
    plan_id: DiagnosticPlanId,
    actor: DiagnosticActor = "tool",
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "diagnostic.plan.run")
    if failure is not None:
        return failure
    return diagnostic_run_plan(
        _diagnostic_context(runtime),
        operation_id=operation_id,
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=expected_revision,
        plan_id=plan_id,
        actor=actor,
    ).to_dict()


async def tool_test_host_discover_for_request(
    runtime: ServerRuntime, context: Context | None
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "test.host.discover")
    if failure is not None:
        return failure
    return host_test_discover(_testing_context(runtime)).to_dict()


async def tool_test_host_run_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    inventory_digest: str,
    case_ids: list[str] | tuple[str, ...] | None = (),
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "test.host.run")
    if failure is not None:
        return failure
    return host_test_run(
        _testing_context(runtime),
        inventory_digest=inventory_digest,
        case_ids=tuple(case_ids or ()),
    ).to_dict()


async def tool_test_show_for_request(
    runtime: ServerRuntime, context: Context | None, run_id: str
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "test.show")
    if failure is not None:
        return failure
    return test_show(_testing_context(runtime), run_id=run_id).to_dict()


async def tool_test_target_prepare_for_request(
    runtime: ServerRuntime, context: Context | None, probe_id: str,
    case_ids: list[str] | tuple[str, ...],
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "test.target.prepare")
    if failure is not None:
        return failure
    return (
        await target_test_prepare(
            _testing_context(runtime), probe_id=probe_id, case_ids=tuple(case_ids)
        )
    ).to_dict()


async def tool_test_target_execute_for_request(
    runtime: ServerRuntime, context: Context | None, probe_id: str,
    authorized_action_digest: str,
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "test.target.execute")
    if failure is not None:
        return failure
    return (
        await target_test_execute(
            _testing_context(runtime), probe_id=probe_id,
            authorized_action_digest=authorized_action_digest,
        )
    ).to_dict()


async def tool_acceptance_scenario_describe_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    scenario_id: AcceptanceScenarioId,
    scenario_version: AcceptanceScenarioVersion,
) -> dict[str, object]:
    operation = "acceptance.scenario.describe"
    failure = await _client_roots_failure(runtime, context, operation)
    if failure is not None:
        return failure
    return describe_acceptance_scenario(
        _acceptance_context(runtime),
        scenario_id=scenario_id,
        scenario_version=scenario_version,
    ).to_dict()


async def tool_acceptance_scenario_record_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    record_id: AcceptanceUuid,
    scenario_id: AcceptanceScenarioId,
    scenario_version: AcceptanceScenarioVersion,
    failed_before_test_run_id: AcceptanceUuid,
    fixed_after_test_run_id: AcceptanceUuid,
    diagnostic_session_id: AcceptanceUuid,
) -> dict[str, object]:
    operation = "acceptance.scenario.record"
    failure = await _client_roots_failure(runtime, context, operation)
    if failure is not None:
        return failure
    return record_acceptance_scenario(
        _acceptance_context(runtime),
        record_id=record_id,
        scenario_id=scenario_id,
        scenario_version=scenario_version,
        failed_before_test_run_id=failed_before_test_run_id,
        fixed_after_test_run_id=fixed_after_test_run_id,
        diagnostic_session_id=diagnostic_session_id,
    ).to_dict()


async def tool_acceptance_scenario_show_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    record_id: AcceptanceUuid,
) -> dict[str, object]:
    operation = "acceptance.scenario.show"
    failure = await _client_roots_failure(runtime, context, operation)
    if failure is not None:
        return failure
    return show_acceptance_scenario(
        _acceptance_context(runtime), record_id=record_id
    ).to_dict()


async def tool_acceptance_attempt_begin_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    attempt_id: AcceptanceUuid,
    scenario_id: AcceptanceScenarioId,
    scenario_version: AcceptanceScenarioVersion,
) -> dict[str, object]:
    operation = "acceptance.attempt.begin"
    failure = await _client_roots_failure(runtime, context, operation)
    if failure is not None:
        return failure
    return begin_acceptance_attempt(
        _acceptance_recovery_context(runtime),
        attempt_id=attempt_id,
        scenario_id=scenario_id,
        scenario_version=scenario_version,
    ).to_dict()


async def tool_acceptance_attempt_checkpoint_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    attempt_id: AcceptanceUuid,
    expected_revision: AcceptanceRevision,
    stage: AcceptanceAttemptStage,
    test_run_id: AcceptanceUuid | None = None,
    diagnostic_session_id: AcceptanceUuid | None = None,
    acceptance_record_id: AcceptanceUuid | None = None,
) -> dict[str, object]:
    operation = "acceptance.attempt.checkpoint"
    failure = await _client_roots_failure(runtime, context, operation)
    if failure is not None:
        return failure
    return checkpoint_acceptance_attempt(
        _acceptance_recovery_context(runtime),
        attempt_id=attempt_id,
        expected_revision=expected_revision,
        stage=stage,
        test_run_id=test_run_id,
        diagnostic_session_id=diagnostic_session_id,
        acceptance_record_id=acceptance_record_id,
    ).to_dict()


async def tool_acceptance_attempt_authorize_source_change_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    attempt_id: AcceptanceUuid,
    expected_revision: AcceptanceRevision,
    action_digest: Digest,
    authorized: StrictBool,
) -> dict[str, object]:
    operation = "acceptance.attempt.authorize-source-change"
    failure = await _client_roots_failure(runtime, context, operation)
    if failure is not None:
        return failure
    return authorize_acceptance_source_change(
        _acceptance_recovery_context(runtime),
        attempt_id=attempt_id,
        expected_revision=expected_revision,
        action_digest=action_digest,
        authorized=authorized,
    ).to_dict()


async def tool_acceptance_attempt_show_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    attempt_id: AcceptanceUuid,
) -> dict[str, object]:
    operation = "acceptance.attempt.show"
    failure = await _client_roots_failure(runtime, context, operation)
    if failure is not None:
        return failure
    return show_acceptance_attempt(
        _acceptance_recovery_context(runtime), attempt_id=attempt_id
    ).to_dict()


async def tool_acceptance_attempt_resume_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    attempt_id: AcceptanceUuid,
) -> dict[str, object]:
    operation = "acceptance.attempt.resume"
    failure = await _client_roots_failure(runtime, context, operation)
    if failure is not None:
        return failure
    return resume_acceptance_attempt(
        _acceptance_recovery_context(runtime), attempt_id=attempt_id
    ).to_dict()


async def _client_roots_failure(
    runtime: ServerRuntime,
    context: Context | None,
    operation: str,
) -> dict[str, object] | None:
    if context is None:
        return None
    try:
        session = context.session
    except ValueError:
        # FastMCP's direct in-memory call path has no client request context.
        return None

    try:
        client_params = getattr(session, "client_params", None)
        capabilities = getattr(client_params, "capabilities", None)
        if getattr(capabilities, "roots", None) is None:
            return None
    except Exception:
        return _roots_unavailable(runtime, operation)

    inner_task: asyncio.Task | None = None
    try:
        inner_task = asyncio.ensure_future(session.list_roots())
        done, _pending = await asyncio.wait(
            {inner_task}, timeout=_CLIENT_ROOTS_TIMEOUT_SECONDS
        )
    except asyncio.CancelledError:
        # Only cancellation of the current tool task can surface here: cancel
        # the in-flight request so it cannot outlive the caller, then
        # propagate. This uses only public asyncio APIs and therefore also
        # behaves correctly on Python 3.10, where Task.cancelling() is not
        # available.
        if inner_task is not None:
            inner_task.cancel()
            try:
                await inner_task
            except BaseException:
                pass
        raise
    except Exception:
        return _roots_unavailable(runtime, operation)

    if not done:
        # Timeout: cancel and await the in-flight request before returning the
        # stable unavailable result.
        inner_task.cancel()
        try:
            await inner_task
        except asyncio.CancelledError:
            pass
        return _roots_unavailable(runtime, operation)

    try:
        result = inner_task.result()
        roots = result.roots
        if not roots:
            raise ValueError("client advertised roots but returned none")
        canonical_roots = tuple(_canonical_client_root(root.uri) for root in roots)
    except asyncio.CancelledError:
        # The client-roots request cancelled itself; report the stable result.
        return _roots_unavailable(runtime, operation)
    except Exception:
        return _roots_unavailable(runtime, operation)

    if len(canonical_roots) != 1 or canonical_roots[0] != runtime.project_root:
        return OperationResult.failure(
            operation,
            "UNSUPPORTED_MULTIROOT",
            "MCP client roots must contain only the bound project root",
            {
                "boundProjectRoot": str(runtime.project_root),
                "roots": [str(root) for root in canonical_roots],
            },
        ).to_dict()
    return None


def _canonical_client_root(uri: object) -> Path:
    parsed = urlsplit(str(uri))
    if parsed.scheme != "file" or parsed.query or parsed.fragment:
        raise ValueError("client root is not a plain file URI")
    uri_path = f"//{parsed.netloc}{parsed.path}" if parsed.netloc else parsed.path
    return canonical_project_root(Path(url2pathname(uri_path)))


def _roots_unavailable(
    runtime: ServerRuntime, operation: str
) -> dict[str, object]:
    return OperationResult.failure(
        operation,
        "MCP_ROOTS_UNAVAILABLE",
        "MCP client roots are unavailable",
        {"boundProjectRoot": str(runtime.project_root)},
    ).to_dict()


def _close_tool_input_schemas(
    mcp: FastMCP, names: tuple[str, ...]
) -> None:
    """Make the new testing request models reject fields outside their contract."""
    for name in names:
        tool = mcp._tool_manager.get_tool(name)
        if tool is None:
            raise RuntimeError(f"registered MCP tool is missing: {name}")
        model = tool.fn_metadata.arg_model
        model.model_config = ConfigDict(
            extra="forbid", arbitrary_types_allowed=True
        )
        model.model_rebuild(force=True)
        tool.parameters = model.model_json_schema()


def create_server(
    project_root: Path, data_root: Path, session_id: str | None = None
) -> FastMCP:
    """Create a FastMCP server permanently bound to one project runtime."""
    runtime = ServerRuntime.create(project_root, data_root, session_id)
    mcp = FastMCP(_SERVER_NAME, instructions=_SERVER_INSTRUCTIONS)

    @mcp.tool(name=MCP_TOOL_NAMES["doctor"])
    async def stm32_doctor(ctx: Context) -> dict[str, object]:
        return await tool_doctor_for_request(runtime, ctx)

    @mcp.tool(name=MCP_TOOL_NAMES["project_detect"])
    async def stm32_project_detect(ctx: Context) -> dict[str, object]:
        return await tool_project_detect_for_request(runtime, ctx)

    @mcp.tool(name=MCP_TOOL_NAMES["project_context"])
    async def stm32_project_context(ctx: Context) -> dict[str, object]:
        return await tool_project_context_for_request(runtime, ctx)

    @mcp.tool(name=MCP_TOOL_NAMES["project_create_plan"])
    async def stm32_project_create_plan(
        ctx: Context,
        sourceKind: Literal["mcu", "board", "ioc"],
        source: str,
        destination: str,
        framework: Literal["hal", "ll"],
        language: Literal["c", "cpp"],
    ) -> dict[str, object]:
        return await tool_project_create_plan_for_request(
            runtime, ctx, sourceKind, source, destination, framework, language
        )

    @mcp.tool(name=MCP_TOOL_NAMES["project_create_prepare"])
    async def stm32_project_create_prepare(
        ctx: Context,
        sourceKind: Literal["mcu", "board", "ioc"],
        source: str,
        destination: str,
        framework: Literal["hal", "ll"],
        language: Literal["c", "cpp"],
        planId: Digest,
        actionDigest: Digest,
    ) -> dict[str, object]:
        return await tool_project_create_prepare_for_request(
            runtime, ctx, sourceKind, source, destination, framework, language, planId, actionDigest
        )

    @mcp.tool(name=MCP_TOOL_NAMES["project_create_apply"])
    async def stm32_project_create_apply(
        ctx: Context,
        authorizationDigest: Digest,
        authorized: StrictBool,
    ) -> dict[str, object]:
        return await tool_project_create_apply_for_request(
            runtime, ctx, authorizationDigest, authorized
        )

    @mcp.tool(name=MCP_TOOL_NAMES["project_regenerate_plan"])
    async def stm32_project_regenerate_plan(
        ctx: Context,
        destination: ProjectRelativePath,
    ) -> dict[str, object]:
        return await tool_project_regenerate_plan_for_request(runtime, ctx, destination)

    @mcp.tool(name=MCP_TOOL_NAMES["project_regenerate_prepare"])
    async def stm32_project_regenerate_prepare(
        ctx: Context,
        destination: ProjectRelativePath,
        planId: Digest,
        actionDigest: Digest,
        authorized: StrictBool,
    ) -> dict[str, object]:
        return await tool_project_regenerate_prepare_for_request(
            runtime, ctx, destination, planId, actionDigest, authorized
        )

    @mcp.tool(name=MCP_TOOL_NAMES["project_regenerate_apply"])
    async def stm32_project_regenerate_apply(
        ctx: Context,
        authorizationDigest: Digest,
        authorized: StrictBool,
    ) -> dict[str, object]:
        return await tool_project_regenerate_apply_for_request(
            runtime, ctx, authorizationDigest, authorized
        )

    @mcp.tool(name=MCP_TOOL_NAMES["keil_inspect"])
    async def stm32_keil_inspect(
        ctx: Context,
        uvprojx: str | None = None,
        targetName: str | None = None,
        includeBaseline: bool = True,
    ) -> dict[str, object]:
        return await tool_keil_inspect_for_request(
            runtime, ctx, uvprojx, targetName, includeBaseline
        )

    @mcp.tool(name=MCP_TOOL_NAMES["keil_convert"])
    async def stm32_keil_convert(
        ctx: Context,
        uvprojx: str | None = None,
        targetName: str | None = None,
        planId: str | None = None,
        authorized: bool = False,
    ) -> dict[str, object]:
        return await tool_keil_convert_for_request(
            runtime, ctx, uvprojx, targetName, planId, authorized
        )

    @mcp.tool(name=MCP_TOOL_NAMES["project_configure"])
    async def stm32_project_configure(
        ctx: Context,
        planId: str | None = None,
        authorized: bool = False,
    ) -> dict[str, object]:
        return await tool_project_configure_for_request(runtime, ctx, planId, authorized)

    @mcp.tool(name=MCP_TOOL_NAMES["build"])
    async def stm32_build(
        ctx: Context,
        preset: Literal["arm-debug", "arm-release"],
        clean: bool = False,
        timeoutSeconds: Annotated[int, Field(ge=1, le=3600)] = 300,
        authorized: bool = False,
    ) -> dict[str, object]:
        return await tool_build_for_request(
            runtime, ctx, preset, clean, timeoutSeconds, authorized
        )

    @mcp.tool(name=MCP_TOOL_NAMES["probe_list"])
    async def stm32_probe_list(ctx: Context) -> dict[str, object]:
        return await tool_probe_list_for_request(runtime, ctx)

    @mcp.tool(name=MCP_TOOL_NAMES["flash"])
    async def stm32_flash(
        ctx: Context,
        probeId: ProbeId,
        expectedBuildId: Digest,
        expectedElfSha256: Digest,
        authorized: StrictBool = False,
    ) -> dict[str, object]:
        return await tool_flash_for_request(
            runtime,
            ctx,
            probeId,
            expectedBuildId,
            expectedElfSha256,
            authorized,
        )

    @mcp.tool(name=MCP_TOOL_NAMES["debug_handoff_begin"])
    async def stm32_debug_handoff_begin(
        ctx: Context,
        probeId: ProbeId,
        expectedBuildId: Digest,
        expectedElfSha256: Digest,
        authorized: StrictBool = False,
        previousWatchSelection: Annotated[list[str], Field(max_length=256)] = [],
    ) -> dict[str, object]:
        return await tool_handoff_begin_for_request(
            runtime,
            ctx,
            probeId,
            expectedBuildId,
            expectedElfSha256,
            authorized,
            previousWatchSelection,
        )

    @mcp.tool(name=MCP_TOOL_NAMES["debug_handoff_end"])
    async def stm32_debug_handoff_end(
        ctx: Context,
        probeId: ProbeId,
        ticket: Digest,
    ) -> dict[str, object]:
        return await tool_handoff_end_for_request(runtime, ctx, probeId, ticket)

    @mcp.tool(name=MCP_TOOL_NAMES["variable_read"])
    async def stm32_variable_read(
        ctx: Context,
        probeId: ProbeId,
        expectedBuildId: Digest,
        expectedElfSha256: Digest,
        expressions: Items,
    ) -> dict[str, object]:
        return await tool_variable_read_for_request(
            runtime,
            ctx,
            probeId,
            expectedBuildId,
            expectedElfSha256,
            expressions,
        )

    @mcp.tool(name=MCP_TOOL_NAMES["variable_sample"])
    async def stm32_variable_sample(
        ctx: Context,
        probeId: ProbeId,
        expectedBuildId: Digest,
        expectedElfSha256: Digest,
        expressions: Items,
        intervalMs: Annotated[int, Field(ge=1, le=3_600_000)],
        count: Annotated[int | None, Field(ge=1, le=10_000)] = None,
        durationMs: Annotated[int | None, Field(ge=1, le=3_600_000)] = None,
    ) -> dict[str, object]:
        return await tool_variable_sample_for_request(
            runtime,
            ctx,
            probeId,
            expectedBuildId,
            expectedElfSha256,
            expressions,
            intervalMs,
            count,
            durationMs,
        )

    @mcp.tool(name=MCP_TOOL_NAMES["register_read"])
    async def stm32_register_read(
        ctx: Context,
        probeId: ProbeId,
        expectedBuildId: Digest,
        expectedElfSha256: Digest,
        paths: Items,
        acknowledgeAccessRisk: StrictBool = False,
    ) -> dict[str, object]:
        return await tool_register_read_for_request(
            runtime,
            ctx,
            probeId,
            expectedBuildId,
            expectedElfSha256,
            paths,
            acknowledgeAccessRisk,
        )

    @mcp.tool(name=MCP_TOOL_NAMES["fault_analyze"])
    async def stm32_fault_analyze(
        ctx: Context,
        probeId: ProbeId,
        expectedBuildId: Digest,
        expectedElfSha256: Digest,
    ) -> dict[str, object]:
        return await tool_fault_analyze_for_request(
            runtime,
            ctx,
            probeId,
            expectedBuildId,
            expectedElfSha256,
        )

    @mcp.tool(name=MCP_TOOL_NAMES["diagnostic_start"])
    async def stm32_diagnostic_start(
        ctx: Context,
        operationId: DiagnosticOperationId,
        failedTestRunId: RunId,
        actor: DiagnosticActor = "user",
        failedRunMode: DiagnosticFailedRunMode = "host",
    ) -> dict[str, object]:
        kwargs: dict[str, object] = {}
        if failedRunMode == "target":
            kwargs["failed_run_mode"] = "target"
        return await tool_diagnostic_start_for_request(
            runtime, ctx, operationId, failedTestRunId, actor, **kwargs
        )

    @mcp.tool(name=MCP_TOOL_NAMES["diagnostic_show"])
    async def stm32_diagnostic_show(
        ctx: Context,
        diagnosticSessionId: DiagnosticSessionId,
    ) -> dict[str, object]:
        return await tool_diagnostic_show_for_request(
            runtime, ctx, diagnosticSessionId
        )

    @mcp.tool(name=MCP_TOOL_NAMES["diagnostic_begin"])
    async def stm32_diagnostic_begin(
        ctx: Context,
        operationId: DiagnosticOperationId,
        diagnosticSessionId: DiagnosticSessionId,
        expectedRevision: DiagnosticRevision,
        actor: DiagnosticActor = "user",
    ) -> dict[str, object]:
        return await tool_diagnostic_begin_for_request(
            runtime,
            ctx,
            operationId,
            diagnosticSessionId,
            expectedRevision,
            actor,
        )

    @mcp.tool(name=MCP_TOOL_NAMES["diagnostic_hypothesis_add"])
    async def stm32_diagnostic_hypothesis_add(
        ctx: Context,
        operationId: DiagnosticOperationId,
        diagnosticSessionId: DiagnosticSessionId,
        expectedRevision: DiagnosticRevision,
        statement: DiagnosticText,
        actor: DiagnosticActor = "user",
    ) -> dict[str, object]:
        return await tool_diagnostic_add_hypothesis_for_request(
            runtime,
            ctx,
            operationId,
            diagnosticSessionId,
            expectedRevision,
            statement,
            actor,
        )

    @mcp.tool(name=MCP_TOOL_NAMES["diagnostic_hypothesis_assess"])
    async def stm32_diagnostic_hypothesis_assess(
        ctx: Context,
        operationId: DiagnosticOperationId,
        diagnosticSessionId: DiagnosticSessionId,
        expectedRevision: DiagnosticRevision,
        hypothesisId: DiagnosticHypothesisId,
        planId: DiagnosticPlanId,
        stepId: DiagnosticStepId,
        polarity: DiagnosticPolarity,
        rationale: DiagnosticText,
        actor: DiagnosticActor = "user",
    ) -> dict[str, object]:
        return await tool_diagnostic_assess_hypothesis_for_request(
            runtime,
            ctx,
            operationId,
            diagnosticSessionId,
            expectedRevision,
            hypothesisId,
            planId,
            stepId,
            polarity,
            rationale,
            actor,
        )

    @mcp.tool(name=MCP_TOOL_NAMES["diagnostic_plan_add"])
    async def stm32_diagnostic_plan_add(
        ctx: Context,
        operationId: DiagnosticOperationId,
        diagnosticSessionId: DiagnosticSessionId,
        expectedRevision: DiagnosticRevision,
        steps: DiagnosticPlanSteps,
        actor: DiagnosticActor = "user",
    ) -> dict[str, object]:
        return await tool_diagnostic_add_plan_for_request(
            runtime,
            ctx,
            operationId,
            diagnosticSessionId,
            expectedRevision,
            [step.model_dump(mode="python") for step in steps],
            actor,
        )

    @mcp.tool(name=MCP_TOOL_NAMES["diagnostic_plan_run"])
    async def stm32_diagnostic_plan_run(
        ctx: Context,
        operationId: DiagnosticOperationId,
        diagnosticSessionId: DiagnosticSessionId,
        expectedRevision: DiagnosticRevision,
        planId: DiagnosticPlanId,
        actor: DiagnosticActor = "tool",
    ) -> dict[str, object]:
        return await tool_diagnostic_run_plan_for_request(
            runtime,
            ctx,
            operationId,
            diagnosticSessionId,
            expectedRevision,
            planId,
            actor,
        )

    @mcp.tool(name=MCP_TOOL_NAMES["test_target_replay"])
    async def stm32_test_target_replay(
        ctx: Context,
        operationId: DiagnosticOperationId,
        descriptorPath: ProjectRelativePath,
        streamPath: ProjectRelativePath,
    ) -> dict[str, object]:
        return await tool_test_target_replay_for_request(
            runtime, ctx, operationId, descriptorPath, streamPath
        )

    @mcp.tool(name=MCP_TOOL_NAMES["diagnostic_source_change_declare"])
    async def stm32_diagnostic_source_change_declare(
        ctx: Context,
        operationId: DiagnosticOperationId,
        diagnosticSessionId: DiagnosticSessionId,
        expectedRevision: DiagnosticRevision,
        sourceChangeDeclaration: SourceChangeDeclarationInput,
        actor: DiagnosticActor = "user",
    ) -> dict[str, object]:
        return await tool_diagnostic_declare_source_change_for_request(
            runtime,
            ctx,
            operationId,
            diagnosticSessionId,
            expectedRevision,
            sourceChangeDeclaration,
            actor,
        )

    @mcp.tool(name=MCP_TOOL_NAMES["diagnostic_verification_plan_add"])
    async def stm32_diagnostic_verification_plan_add(
        ctx: Context,
        operationId: DiagnosticOperationId,
        diagnosticSessionId: DiagnosticSessionId,
        expectedRevision: DiagnosticRevision,
        verificationPlan: VerificationPlanInput,
        actor: DiagnosticActor = "user",
    ) -> dict[str, object]:
        return await tool_diagnostic_add_verification_plan_for_request(
            runtime,
            ctx,
            operationId,
            diagnosticSessionId,
            expectedRevision,
            verificationPlan,
            actor,
        )

    @mcp.tool(name=MCP_TOOL_NAMES["diagnostic_verification_start"])
    async def stm32_diagnostic_verification_start(
        ctx: Context,
        operationId: DiagnosticOperationId,
        diagnosticSessionId: DiagnosticSessionId,
        expectedRevision: DiagnosticRevision,
        verificationPlanId: DiagnosticPlanId,
        actor: DiagnosticActor = "tool",
    ) -> dict[str, object]:
        return await tool_diagnostic_start_verification_for_request(
            runtime,
            ctx,
            operationId,
            diagnosticSessionId,
            expectedRevision,
            verificationPlanId,
            actor,
        )

    @mcp.tool(name=MCP_TOOL_NAMES["diagnostic_marker_attach"])
    async def stm32_diagnostic_marker_attach(
        ctx: Context,
        operationId: DiagnosticOperationId,
        diagnosticSessionId: DiagnosticSessionId,
        expectedRevision: DiagnosticRevision,
        diagnosticMarkerRef: DiagnosticMarkerInput,
        actor: DiagnosticActor = "tool",
    ) -> dict[str, object]:
        return await tool_diagnostic_attach_marker_for_request(
            runtime,
            ctx,
            operationId,
            diagnosticSessionId,
            expectedRevision,
            diagnosticMarkerRef,
            actor,
        )

    @mcp.tool(name=MCP_TOOL_NAMES["diagnostic_verification_complete"])
    async def stm32_diagnostic_verification_complete(
        ctx: Context,
        operationId: DiagnosticOperationId,
        diagnosticSessionId: DiagnosticSessionId,
        expectedRevision: DiagnosticRevision,
        executedOperationIds: Annotated[
            list[DiagnosticOperationId], Field(min_length=1, max_length=64)
        ],
        cancelled: StrictBool = False,
        actor: DiagnosticActor = "tool",
    ) -> dict[str, object]:
        return await tool_diagnostic_complete_verification_for_request(
            runtime,
            ctx,
            operationId,
            diagnosticSessionId,
            expectedRevision,
            executedOperationIds,
            cancelled,
            actor,
        )

    @mcp.tool(name=MCP_TOOL_NAMES["diagnostic_verification_show"])
    async def stm32_diagnostic_verification_show(
        ctx: Context,
        diagnosticSessionId: DiagnosticSessionId,
    ) -> dict[str, object]:
        return await tool_diagnostic_show_verification_for_request(
            runtime, ctx, diagnosticSessionId
        )

    @mcp.tool(name=MCP_TOOL_NAMES["test_host_discover"])
    async def stm32_test_host_discover(ctx: Context) -> dict[str, object]:
        return await tool_test_host_discover_for_request(runtime, ctx)

    @mcp.tool(name=MCP_TOOL_NAMES["test_host_run"])
    async def stm32_test_host_run(
        ctx: Context,
        inventoryDigest: Digest,
        caseIds: UniqueCaseIds = [],
    ) -> dict[str, object]:
        return await tool_test_host_run_for_request(
            runtime, ctx, inventoryDigest, caseIds
        )

    @mcp.tool(name=MCP_TOOL_NAMES["test_show"])
    async def stm32_test_show(
        ctx: Context,
        runId: RunId,
    ) -> dict[str, object]:
        return await tool_test_show_for_request(runtime, ctx, runId)

    @mcp.tool(name=MCP_TOOL_NAMES["test_target_prepare"])
    async def stm32_test_target_prepare(
        ctx: Context, probeId: ProbeId, caseIds: Annotated[list[CaseId], Field(min_length=1, max_length=MAX_CASES), AfterValidator(_unique_case_ids)],
    ) -> dict[str, object]:
        return await tool_test_target_prepare_for_request(runtime, ctx, probeId, caseIds)

    @mcp.tool(name=MCP_TOOL_NAMES["test_target_execute"])
    async def stm32_test_target_execute(
        ctx: Context, probeId: ProbeId, authorizedActionDigest: Digest,
    ) -> dict[str, object]:
        return await tool_test_target_execute_for_request(
            runtime, ctx, probeId, authorizedActionDigest
        )

    @mcp.tool(name=MCP_TOOL_NAMES["acceptance_scenario_describe"])
    async def stm32_acceptance_scenario_describe(
        ctx: Context,
        scenarioId: AcceptanceScenarioId,
        scenarioVersion: AcceptanceScenarioVersion,
    ) -> dict[str, object]:
        return await tool_acceptance_scenario_describe_for_request(
            runtime, ctx, scenarioId, scenarioVersion
        )

    @mcp.tool(name=MCP_TOOL_NAMES["acceptance_scenario_record"])
    async def stm32_acceptance_scenario_record(
        ctx: Context,
        recordId: AcceptanceUuid,
        scenarioId: AcceptanceScenarioId,
        scenarioVersion: AcceptanceScenarioVersion,
        failedBeforeTestRunId: AcceptanceUuid,
        fixedAfterTestRunId: AcceptanceUuid,
        diagnosticSessionId: AcceptanceUuid,
    ) -> dict[str, object]:
        return await tool_acceptance_scenario_record_for_request(
            runtime,
            ctx,
            recordId,
            scenarioId,
            scenarioVersion,
            failedBeforeTestRunId,
            fixedAfterTestRunId,
            diagnosticSessionId,
        )

    @mcp.tool(name=MCP_TOOL_NAMES["acceptance_scenario_show"])
    async def stm32_acceptance_scenario_show(
        ctx: Context,
        recordId: AcceptanceUuid,
    ) -> dict[str, object]:
        return await tool_acceptance_scenario_show_for_request(runtime, ctx, recordId)

    @mcp.tool(name=MCP_TOOL_NAMES["acceptance_attempt_begin"])
    async def stm32_acceptance_attempt_begin(
        ctx: Context,
        attemptId: AcceptanceUuid,
        scenarioId: AcceptanceScenarioId,
        scenarioVersion: AcceptanceScenarioVersion,
    ) -> dict[str, object]:
        return await tool_acceptance_attempt_begin_for_request(
            runtime, ctx, attemptId, scenarioId, scenarioVersion
        )

    @mcp.tool(name=MCP_TOOL_NAMES["acceptance_attempt_checkpoint"])
    async def stm32_acceptance_attempt_checkpoint(
        ctx: Context,
        attemptId: AcceptanceUuid,
        expectedRevision: AcceptanceRevision,
        stage: AcceptanceAttemptStage,
        testRunId: AcceptanceUuid | None = None,
        diagnosticSessionId: AcceptanceUuid | None = None,
        acceptanceRecordId: AcceptanceUuid | None = None,
    ) -> dict[str, object]:
        return await tool_acceptance_attempt_checkpoint_for_request(
            runtime,
            ctx,
            attemptId,
            expectedRevision,
            stage,
            testRunId,
            diagnosticSessionId,
            acceptanceRecordId,
        )

    @mcp.tool(name=MCP_TOOL_NAMES["acceptance_attempt_authorize_source_change"])
    async def stm32_acceptance_attempt_authorize_source_change(
        ctx: Context,
        attemptId: AcceptanceUuid,
        expectedRevision: AcceptanceRevision,
        actionDigest: Digest,
        authorized: StrictBool,
    ) -> dict[str, object]:
        return await tool_acceptance_attempt_authorize_source_change_for_request(
            runtime, ctx, attemptId, expectedRevision, actionDigest, authorized
        )

    @mcp.tool(name=MCP_TOOL_NAMES["acceptance_attempt_show"])
    async def stm32_acceptance_attempt_show(
        ctx: Context,
        attemptId: AcceptanceUuid,
    ) -> dict[str, object]:
        return await tool_acceptance_attempt_show_for_request(runtime, ctx, attemptId)

    @mcp.tool(name=MCP_TOOL_NAMES["acceptance_attempt_resume"])
    async def stm32_acceptance_attempt_resume(
        ctx: Context,
        attemptId: AcceptanceUuid,
    ) -> dict[str, object]:
        return await tool_acceptance_attempt_resume_for_request(runtime, ctx, attemptId)

    _close_tool_input_schemas(
        mcp,
        (
            "stm32_test_host_discover",
            "stm32_project_create_plan",
            "stm32_project_regenerate_plan",
            "stm32_project_regenerate_prepare",
            "stm32_project_regenerate_apply",
            "stm32_test_host_run",
            "stm32_test_show",
            "stm32_test_target_prepare",
            "stm32_test_target_execute",
            "stm32_test_target_replay",
            "stm32_diagnostic_start",
            "stm32_diagnostic_show",
            "stm32_diagnostic_begin",
            "stm32_diagnostic_hypothesis_add",
            "stm32_diagnostic_hypothesis_assess",
            "stm32_diagnostic_plan_add",
            "stm32_diagnostic_plan_run",
            "stm32_diagnostic_source_change_declare",
            "stm32_diagnostic_verification_plan_add",
            "stm32_diagnostic_verification_start",
            "stm32_diagnostic_marker_attach",
            "stm32_diagnostic_verification_complete",
            "stm32_diagnostic_verification_show",
            "stm32_acceptance_scenario_describe",
            "stm32_acceptance_scenario_record",
            "stm32_acceptance_scenario_show",
            "stm32_acceptance_attempt_begin",
            "stm32_acceptance_attempt_checkpoint",
            "stm32_acceptance_attempt_authorize_source_change",
            "stm32_acceptance_attempt_show",
            "stm32_acceptance_attempt_resume",
        ),
    )

    return mcp


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stm32-toolkit-mcp")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--session-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Start the project-bound MCP server on the stdio protocol transport."""
    args = _build_parser().parse_args(argv)
    try:
        mcp = create_server(args.project_root, args.data_root, args.session_id)
        mcp.run(transport="stdio")
    except Exception as error:
        print(f"stm32-toolkit-mcp: startup failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
