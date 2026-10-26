from __future__ import annotations

import asyncio
import argparse
import os
import stat
import sys
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit
from urllib.request import url2pathname

from mcp.server.fastmcp import Context, FastMCP
from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    StrictBool,
    StrictInt,
    StrictStr,
    model_serializer,
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
from stm32_toolkit.keil.model import KeilInspectionError
from stm32_toolkit.monitor_replay_contract import (
    ReplayContractError,
    validate_run_reference,
)
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
from stm32_toolkit.external_firmware import (
    FirmwareAdmitRequest,
    FirmwareImportRequest,
    firmware_admit_workflow,
    firmware_import_workflow,
)
from stm32_toolkit.hardware_workflows import (
    FaultWorkflowRequest,
    FlashImportedWorkflowRequest,
    FlashWorkflowRequest,
    HandoffBeginWorkflowRequest,
    HandoffEndWorkflowRequest,
    ProbeListWorkflowRequest,
    RegisterReadWorkflowRequest,
    VariableReadWorkflowRequest,
    VariableSampleWorkflowRequest,
    fault_workflow,
    flash_imported_workflow,
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
    preflight_keil_workflow,
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
    "debug handoff operations. Read and retain the complete OperationResult "
    "envelope (ok, code, message, data, details) before presenting a concise "
    "summary of the relevant fields; check ok before dereferencing data, and "
    "never discard ok=false details or capabilityDetails diagnostics. Verify "
    "version and tool binding from actual tool results, not from a launcher "
    "version."
)


class _RejectDuplicateArgument(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is not None:
            parser.error(f"argument {option_string}: repeated option")
        setattr(namespace, self.dest, values)


def _mcp_root_type(value: str) -> Path:
    if not value or not value.strip():
        raise argparse.ArgumentTypeError("root is empty")
    if "${" in value:
        raise argparse.ArgumentTypeError("root contains an unresolved path placeholder")
    root = Path(value)
    if not root.is_absolute():
        raise argparse.ArgumentTypeError("root must be an absolute path")
    return root
_CLIENT_ROOTS_TIMEOUT_SECONDS = 5.0
_DIGEST_PATTERN = r"^[0-9a-f]{64}$"
_PROBE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
_RUN_ID_PATTERN = r"^[a-z0-9][a-z0-9._-]*$"
_DIAGNOSTIC_OPERATION_PATTERN = r"^[a-z0-9][a-z0-9._-]{0,127}$"
_DIAGNOSTIC_SESSION_PATTERN = r"^[0-9a-f]{32}$"
_DIAGNOSTIC_REFERENCE_PATTERN = (
    r"^(?:[0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$"
)
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
FirmwareTarget = Annotated[str, Field(pattern=_PROBE_PATTERN)]
FlashFrequency = Annotated[StrictInt, Field(ge=100_000, le=50_000_000)]


class FirmwareFlashRegion(BaseModel):
    """One reviewed internal-Flash allowlist region declared by the caller."""

    model_config = ConfigDict(extra="forbid")

    start: Annotated[StrictInt, Field(ge=0, le=0xFFFF_FFFF)]
    length: Annotated[StrictInt, Field(ge=1, le=0xFFFF_FFFF)]
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

AcceptanceScenarioId = Literal[
    "legacy-keil-migration",
    "new-cubemx-project",
]
AcceptanceAttemptScenarioId = Literal[
    "legacy-keil-migration",
    "new-cubemx-project",
    "legacy-keil-physical-repair",
    "new-cubemx-physical-repair",
]
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
    "target-failure-observed",
    "diagnosis-completed",
    "firmware-built-after",
    "target-fix-verified",
]
AcceptanceRunId = RunId
AcceptanceDiagnosticRef = Annotated[
    StrictStr,
    Field(pattern=_DIAGNOSTIC_REFERENCE_PATTERN, min_length=32, max_length=36),
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


class SourceChangeIntentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    path: ProjectRelativePath
    before_sha256: Digest = Field(alias="beforeSha256")
    after_sha256: Digest = Field(alias="afterSha256")
    after_size: Annotated[StrictInt, Field(ge=0, le=8 * 1024 * 1024)] = Field(alias="afterSize")


class PhysicalSourceChangeIntentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Literal["stm32-source-change-intent/1"] = Field(alias="schema")
    changes: Annotated[
        list[SourceChangeIntentInput],
        BeforeValidator(_reject_json_tuple),
        Field(min_length=1, max_length=32),
    ]


class ContinuationBindInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    schema_: Literal["stm32-physical-continuation-request/1"] = Field(alias="schema")
    kind: Literal["bind"]
    predecessorAttemptId: AcceptanceUuid
    predecessorCheckpointId: Digest
    predecessorEvidenceId: Digest
    fixedAfterTestRunId: AcceptanceRunId
    fixedAfterEvidenceId: Digest
    diagnosticRevision: DiagnosticRevision
    diagnosticEventHead: Digest


class ContinuationReuseInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    schema_: Literal["stm32-physical-continuation-request/1"] = Field(alias="schema")
    kind: Literal["reuse"]
    continuationEvidenceId: Digest


class FinalizationBindInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    schema_: Literal["stm32-physical-continuation-request/2"] = Field(alias="schema")
    kind: Literal["bind"]
    predecessorAttemptId: AcceptanceUuid
    predecessorCheckpointId: Digest
    predecessorEvidenceId: Digest
    fixedAfterTestRunId: AcceptanceRunId
    fixedAfterEvidenceId: Digest
    diagnosticRevision: DiagnosticRevision
    diagnosticEventHead: Digest
    fixVerificationId: Digest


class FinalizationReuseInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    schema_: Literal["stm32-physical-continuation-request/2"] = Field(alias="schema")
    kind: Literal["reuse"]
    continuationEvidenceId: Digest


ContinuationInput = (
    ContinuationBindInput
    | ContinuationReuseInput
    | FinalizationBindInput
    | FinalizationReuseInput
)

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


class VerificationPlanV2Input(VerificationPlanInput):
    schema_: Literal["stm32-verification-plan/2"] = Field(alias="schema")
    continuation_evidence_id: Digest


VerificationPlanRequestInput = VerificationPlanInput | VerificationPlanV2Input


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
MonitorRunRefLogicalProjectId = Annotated[
    str,
    Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"),
]
MonitorRunRefSessionId = Annotated[
    str,
    Field(pattern=r"^[a-z0-9][a-z0-9_-]*$", min_length=1, max_length=MAX_STRING_BYTES),
    AfterValidator(_validate_test_string),
]
MonitorRunRefText = Annotated[
    str,
    Field(min_length=1, max_length=256),
    AfterValidator(_validate_test_string),
]
MonitorRunRefGitHead = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
MonitorRunRefUuid = Annotated[
    str,
    Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"),
]


class MonitorRunRefGitEvidence(BaseModel):
    """The bounded unavailable-Git record a snapshot reference carries."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["unavailable"]
    code: Literal["BUILD_GIT_INVALID"]
    rule: Literal["head", "status"]


class DiagnosticMonitorRunRef(BaseModel):
    """Closed v2 physical Monitor source reference accepted by the MCP edge."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Literal["stm32-monitor-run-ref/2"] = Field(alias="schema")
    operation_id: MonitorRunRefUuid
    scenario_role: Literal["failed-before", "fixed-after"]
    execution_source: Literal["physical"]
    physical_transport_evidence: Literal[True]
    origin_workspace_id: Digest
    import_workspace_id: Digest
    logical_project_id: MonitorRunRefLogicalProjectId
    origin_session_id: MonitorRunRefSessionId
    projected_session_id: MonitorRunRefSessionId
    origin_run_id: MonitorRunRefUuid
    projected_run_id: MonitorRunRefUuid
    target_device: MonitorRunRefText
    probe_id: MonitorRunRefText
    physical_target: MonitorRunRefText
    build_id: Digest
    elf_sha256: Digest
    input_snapshot_sha256: Digest
    #: Null Git fields are accepted only in the validated snapshot form below.
    git_head: MonitorRunRefGitHead | None
    git_dirty: StrictBool | None
    #: The snapshot provenance pair; both stay unset for the legacy Git form.
    source_baseline: Literal["input-snapshot-v1"] | None = None
    git_evidence: MonitorRunRefGitEvidence | None = None
    flash_session_id: MonitorRunRefText
    lease_id: MonitorRunRefText
    dwarf_sha256: Digest
    svd_sha256: Digest | None
    group_id: MonitorRunRefUuid
    group_revision: Annotated[StrictInt, Field(ge=1)]
    start_sequence: Annotated[StrictInt, Field(ge=0)]
    end_sequence_exclusive: Annotated[StrictInt, Field(ge=1)]
    start_captured_unix_ns: Annotated[StrictInt, Field(ge=0)]
    end_captured_unix_ns_exclusive: Annotated[StrictInt, Field(ge=1)]
    projected_batch_sha256s: Annotated[
        list[Digest], BeforeValidator(_reject_json_tuple), Field(min_length=1, max_length=1024)
    ]
    transcript_evidence_id: Digest
    run_ref_sha256: Digest
    source_record_sha256: Digest

    @model_validator(mode="before")
    @classmethod
    def _validate_replay_wire(cls, value: object) -> object:
        raw = (
            value.model_dump(mode="python", by_alias=True)
            if isinstance(value, BaseModel)
            else value
        )
        if isinstance(raw, dict) and "schema" not in raw and "schema_" in raw:
            raw = dict(raw)
            raw["schema"] = raw.pop("schema_")
        try:
            validate_run_reference(raw)
        except (ReplayContractError, TypeError, ValueError, OverflowError) as error:
            raise ValueError("monitor run reference violates replay contract") from error
        return raw

    @model_validator(mode="after")
    def _validate_lineage(self) -> "DiagnosticMonitorRunRef":
        if self.origin_run_id != self.operation_id or self.projected_run_id != self.operation_id:
            raise ValueError("Monitor reference run IDs must match operation_id")
        if self.origin_session_id != self.projected_session_id:
            raise ValueError("Physical Monitor reference sessions must match")
        if self.origin_workspace_id != self.import_workspace_id:
            raise ValueError("Physical Monitor reference workspaces must match")
        if self.end_sequence_exclusive <= self.start_sequence:
            raise ValueError("Monitor reference sequence window is invalid")
        if self.end_captured_unix_ns_exclusive <= self.start_captured_unix_ns:
            raise ValueError("Monitor reference capture window is invalid")
        return self

    @model_serializer(mode="wrap")
    def _serialize_reference(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, object]:
        """Omit only the two absent snapshot pair keys from a legacy reference.

        A snapshot reference dumps the complete validated pair.  Every other
        key stays exactly as serialized, so the legacy wire document keeps its
        accepted key set and the required nullable ``svd_sha256`` survives.
        """
        data = handler(self)
        for key in ("source_baseline", "git_evidence"):
            if data.get(key) is None:
                data.pop(key, None)
        return data


class DiagnosticPhysicalMonitorFactSelector(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["physical-monitor-fact/1"]
    continuation_evidence_id: Digest
    monitor_ref_evidence_id: Digest
    monitor_run_ref: DiagnosticMonitorRunRef
    selector_kind: Literal["variable", "register"]
    selector: DiagnosticText
    fact: Literal["value-varies", "bit-values-mask"]
    minimum_valid_samples: Annotated[StrictInt, Field(ge=1, le=1024)]
    bit_index: Annotated[StrictInt, Field(ge=0, le=31)] | None = None

    @model_validator(mode="after")
    def _validate_fact(self) -> "DiagnosticPhysicalMonitorFactSelector":
        if self.fact == "value-varies" and (
            self.bit_index is not None or "bit_index" in self.model_fields_set
        ):
            raise ValueError("value-varies does not accept bit_index")
        if (
            self.fact == "bit-values-mask"
            and (
                self.selector_kind != "register"
                or self.bit_index is None
                or "bit_index" not in self.model_fields_set
            )
        ):
            raise ValueError("bit-values-mask requires a register selector")
        return self


class DiagnosticPhysicalMonitorFactV2Selector(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["physical-monitor-fact/2"]
    monitor_ref_evidence_id: Digest
    monitor_run_ref: DiagnosticMonitorRunRef
    selector_kind: Literal["variable", "register"]
    selector: DiagnosticText
    fact: Literal["value-varies", "bit-values-mask"]
    minimum_valid_samples: Annotated[StrictInt, Field(ge=1, le=1024)]
    bit_index: Annotated[StrictInt, Field(ge=0, le=31)] | None = None

    @model_validator(mode="after")
    def _validate_fact(self) -> "DiagnosticPhysicalMonitorFactV2Selector":
        if self.monitor_run_ref.scenario_role != "failed-before":
            raise ValueError("v2 physical monitor facts require failed-before evidence")
        if self.fact == "value-varies" and (
            self.bit_index is not None or "bit_index" in self.model_fields_set
        ):
            raise ValueError("value-varies does not accept bit_index")
        if (
            self.fact == "bit-values-mask"
            and (
                self.selector_kind != "register"
                or self.bit_index is None
                or "bit_index" not in self.model_fields_set
            )
        ):
            raise ValueError("bit-values-mask requires a register selector")
        return self


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
    | DiagnosticCaseCountSelector
    | DiagnosticPhysicalMonitorFactSelector
    | DiagnosticPhysicalMonitorFactV2Selector,
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
        if kind in {"physical-monitor-fact/1", "physical-monitor-fact/2"}:
            if type(self.expected_value) is not int:
                raise ValueError("expected value is incompatible with selector")
            fact = self.selector.fact
            if fact == "value-varies" and self.expected_value not in {0, 1}:
                raise ValueError("expected value is incompatible with selector")
            if fact == "bit-values-mask" and self.expected_value not in {1, 2, 3}:
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


def _doctor_path(value: str | Path | None) -> Path | None:
    if value is None:
        return None
    if isinstance(value, Path):
        return value
    if isinstance(value, str):
        return Path(value)
    raise TypeError("doctor path arguments must be strings or paths")


def tool_doctor(
    runtime: ServerRuntime,
    *,
    probe_vscode_extensions: bool = True,
    vscode_path: str | Path | None = None,
    uv4_path: str | Path | None = None,
    armcc_path: str | Path | None = None,
) -> dict[str, object]:
    """Return the read-only environment diagnosis for the bound project."""
    return run_doctor(
        runtime.project_root,
        data_root=runtime.data_root,
        support_profile=runtime.support_profile,
        probe_vscode_extensions=probe_vscode_extensions,
        vscode_path=_doctor_path(vscode_path),
        uv4_path=_doctor_path(uv4_path),
        armcc_path=_doctor_path(armcc_path),
    ).to_dict()


def tool_project_detect(runtime: ServerRuntime) -> dict[str, object]:
    """Return project markers for the bound project."""
    try:
        detection = detect_project(runtime.project_root)
    except KeilInspectionError as error:
        return OperationResult.failure(
            "project.detect", error.code, error.message, error.details
        ).to_dict()
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


def tool_keil_preflight(
    runtime: ServerRuntime,
    uvprojx: str | None = None,
    target_name: str | None = None,
    startup_strategy: str | None = None,
    startup_source: str | None = None,
    memory_layout: object = None,
    extra_regions: object = None,
) -> dict[str, object]:
    """Return read-only migration analysis without requiring Git.

    A successful result means the technical analysis completed; it may still
    contain blockers.  Apply prerequisites and the absence of an applicable
    plan ID are reported separately.  Preflight never authorizes apply.
    """
    return preflight_keil_workflow(
        runtime.project_root,
        uvprojx=uvprojx,
        target_name=target_name,
        startup_strategy=startup_strategy,
        startup_source=startup_source,
        memory_layout=memory_layout,
        extra_regions=extra_regions,
    ).to_dict()


def tool_keil_convert(
    runtime: ServerRuntime,
    uvprojx: str | None = None,
    target_name: str | None = None,
    plan_id: str | None = None,
    authorized: bool = False,
    startup_strategy: str | None = None,
    startup_source: str | None = None,
    memory_layout: object = None,
    extra_regions: object = None,
) -> dict[str, object]:
    """Read-only conversion plan, or apply with the exact plan ID plus
    ``authorized=true``."""
    return convert_keil_workflow(
        runtime.project_root,
        uvprojx=uvprojx,
        target_name=target_name,
        plan_id=plan_id,
        authorized=authorized,
        startup_strategy=startup_strategy,
        startup_source=startup_source,
        memory_layout=memory_layout,
        extra_regions=extra_regions,
    ).to_dict()


def tool_project_configure(
    runtime: ServerRuntime,
    plan_id: str | None = None,
    authorized: bool = False,
    debug_backend: object = None,
    debug_target: object = None,
    vscode_toolkit_path: object = None,
    vscode_gcc_path: object = None,
) -> dict[str, object]:
    """Read-only configuration plan, or apply with the exact plan ID plus
    ``authorized=true``.

    Both debug options omitted keeps the historical route; both supplied
    select the explicit ``debug.backend``/``debug.target`` manifest edit.
    Both VS Code options supplied render validated absolute native executable
    paths; both omitted keep portable user-setting defaults.
    """
    return configure_project_workflow(
        runtime.project_root,
        plan_id=plan_id,
        authorized=authorized,
        debug_backend=debug_backend,
        debug_target=debug_target,
        vscode_toolkit_path=vscode_toolkit_path,
        vscode_gcc_path=vscode_gcc_path,
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
    runtime: ServerRuntime,
    context: Context | None,
    *,
    probe_vscode_extensions: bool = True,
    vscode_path: str | Path | None = None,
    uv4_path: str | Path | None = None,
    armcc_path: str | Path | None = None,
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "doctor")
    if failure is not None:
        return failure
    return tool_doctor(
        runtime,
        probe_vscode_extensions=probe_vscode_extensions,
        vscode_path=vscode_path,
        uv4_path=uv4_path,
        armcc_path=armcc_path,
    )


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


async def tool_keil_preflight_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    uvprojx: str | None = None,
    target_name: str | None = None,
    startup_strategy: str | None = None,
    startup_source: str | None = None,
    memory_layout: object = None,
    extra_regions: object = None,
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "keil-preflight")
    if failure is not None:
        return failure
    return tool_keil_preflight(
        runtime,
        uvprojx,
        target_name,
        startup_strategy,
        startup_source,
        memory_layout,
        extra_regions,
    )


async def tool_keil_convert_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    uvprojx: str | None = None,
    target_name: str | None = None,
    plan_id: str | None = None,
    authorized: bool = False,
    startup_strategy: str | None = None,
    startup_source: str | None = None,
    memory_layout: object = None,
    extra_regions: object = None,
) -> dict[str, object]:
    operation = (
        "keil-conversion-apply"
        if plan_id is not None or authorized is not False
        else "keil-conversion-plan"
    )
    failure = await _client_roots_failure(runtime, context, operation)
    if failure is not None:
        return failure
    return tool_keil_convert(
        runtime,
        uvprojx,
        target_name,
        plan_id,
        authorized,
        startup_strategy,
        startup_source,
        memory_layout,
        extra_regions,
    )


async def tool_project_configure_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    plan_id: str | None = None,
    authorized: bool = False,
    debug_backend: object = None,
    debug_target: object = None,
    vscode_toolkit_path: object = None,
    vscode_gcc_path: object = None,
) -> dict[str, object]:
    operation = (
        "project-configuration-apply"
        if plan_id is not None or authorized is not False
        else "project-configuration-plan"
    )
    failure = await _client_roots_failure(runtime, context, operation)
    if failure is not None:
        return failure
    return tool_project_configure(
        runtime,
        plan_id,
        authorized,
        debug_backend,
        debug_target,
        vscode_toolkit_path,
        vscode_gcc_path,
    )


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
    recovery_under_reset: object = False,
    frequency_hz: object = None,
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
            recovery_under_reset,
            frequency_hz=frequency_hz,
        ),
        flash_workflow,
    )


async def _firmware_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    operation: str,
    request: object,
    workflow: Callable[[object], OperationResult[object]],
) -> dict[str, object]:
    """Run one offline firmware workflow after validating client roots."""

    failure = await _client_roots_failure(runtime, context, operation)
    if failure is not None:
        return failure
    try:
        result = workflow(request)
        if not isinstance(result, OperationResult):
            raise TypeError("firmware workflow returned an invalid result")
        return result.to_dict()
    except asyncio.CancelledError:
        raise
    except Exception:
        return OperationResult.failure(
            operation,
            "FIRMWARE_INTERNAL_ERROR",
            "Firmware workflow failed",
            {},
        ).to_dict()


async def tool_firmware_import_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    firmware_path: str,
    expected_sha256: str,
    format: str,
    target: str,
    flash_regions: list[FirmwareFlashRegion] | tuple[FirmwareFlashRegion, ...],
    base_address: int | None = None,
    plan_id: str | None = None,
    authorized: object = False,
) -> dict[str, object]:
    return await _firmware_for_request(
        runtime,
        context,
        "stm32_firmware_import",
        FirmwareImportRequest(
            runtime.project_root,
            runtime.data_root,
            runtime.session_id,
            firmware_path,
            expected_sha256,
            format,
            target,
            tuple((region.start, region.length) for region in flash_regions),
            base_address,
            plan_id,
            authorized,
        ),
        firmware_import_workflow,
    )


async def tool_firmware_admit_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    import_id: str,
    expected_sha256: str,
) -> dict[str, object]:
    return await _firmware_for_request(
        runtime,
        context,
        "stm32_firmware_admit",
        FirmwareAdmitRequest(
            runtime.project_root,
            runtime.data_root,
            runtime.session_id,
            import_id,
            expected_sha256,
        ),
        firmware_admit_workflow,
    )


async def tool_flash_imported_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    probe_id: str,
    import_id: str,
    expected_sha256: str,
    authorized: object = False,
    frequency_hz: object = None,
) -> dict[str, object]:
    operation = "stm32_flash_imported"
    failure = await _client_roots_failure(runtime, context, operation)
    if failure is not None:
        return failure
    if authorized is not True:
        return _authorization_failure(operation)
    return await _hardware_for_request(
        runtime,
        None,
        operation,
        FlashImportedWorkflowRequest(
            runtime.project_root,
            runtime.data_root,
            runtime.session_id,
            probe_id,
            import_id,
            expected_sha256,
            True,
            frequency_hz=frequency_hz,
        ),
        flash_imported_workflow,
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
    halt_for_analysis: object = False,
) -> dict[str, object]:
    if type(halt_for_analysis) is not bool:
        return OperationResult.failure(
            "stm32_fault_analyze",
            "HARDWARE_INPUT_INVALID",
            "Fault halt selection is invalid",
            {},
        ).to_dict()
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
            halt_for_analysis,
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


def _diagnostic_step_data(step: DiagnosticObservationStep) -> dict[str, object]:
    """Dump one step while omitting only the inapplicable top-level bit index."""

    data = step.model_dump(mode="python", by_alias=True)
    selector = data.get("selector")
    if (
        isinstance(selector, dict)
        and selector.get("kind") in {"physical-monitor-fact/1", "physical-monitor-fact/2"}
        and selector.get("bit_index") is None
    ):
        selector.pop("bit_index", None)
    return data


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
    verification_plan: VerificationPlanRequestInput,
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
    recovery_under_reset: bool = False,
) -> dict[str, object]:
    failure = await _client_roots_failure(runtime, context, "test.target.prepare")
    if failure is not None:
        return failure
    return (
        await target_test_prepare(
            _testing_context(runtime),
            probe_id=probe_id,
            case_ids=tuple(case_ids),
            recovery_under_reset=recovery_under_reset,
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
    diagnostic_session_id: AcceptanceDiagnosticRef,
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
    scenario_id: AcceptanceAttemptScenarioId,
    scenario_version: AcceptanceScenarioVersion,
    continuation: ContinuationInput | None = None,
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
        **({} if continuation is None else {"continuation": _nested_model_data(continuation)}),
    ).to_dict()


async def tool_acceptance_attempt_checkpoint_for_request(
    runtime: ServerRuntime,
    context: Context | None,
    attempt_id: AcceptanceUuid,
    expected_revision: AcceptanceRevision,
    stage: AcceptanceAttemptStage,
    test_run_id: AcceptanceRunId | None = None,
    diagnostic_session_id: AcceptanceDiagnosticRef | None = None,
    acceptance_record_id: AcceptanceUuid | None = None,
    sourceChangeIntent: PhysicalSourceChangeIntentInput | None = None,
    fixVerificationId: Digest | None = None,
) -> dict[str, object]:
    operation = "acceptance.attempt.checkpoint"
    failure = await _client_roots_failure(runtime, context, operation)
    if failure is not None:
        return failure
    kwargs: dict[str, object] = {
        "attempt_id": attempt_id,
        "expected_revision": expected_revision,
        "stage": stage,
        "test_run_id": test_run_id,
        "diagnostic_session_id": diagnostic_session_id,
        "acceptance_record_id": acceptance_record_id,
    }
    if sourceChangeIntent is not None:
        kwargs["source_change_intent"] = _nested_model_data(sourceChangeIntent)
    if fixVerificationId is not None:
        kwargs["fix_verification_id"] = fixVerificationId
    return checkpoint_acceptance_attempt(
        _acceptance_recovery_context(runtime), **kwargs
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
    async def stm32_doctor(
        ctx: Context,
        probeVscodeExtensions: Annotated[
            StrictBool,
            Field(
                description=(
                    "Query the selected local VS Code CLI for the three "
                    "recommended extensions. Default true."
                )
            ),
        ] = True,
        vscodePath: Annotated[
            StrictStr,
            Field(
                description=(
                    "Absolute Code.exe or installed bin/code.cmd. The launcher "
                    "is parsed, never executed. Invalid values do not fall back."
                )
            ),
        ] | None = None,
        uv4Path: Annotated[
            StrictStr,
            Field(
                description=(
                    "Absolute Keil UV4.exe used only for static file-version "
                    "evidence; UV4 is never executed."
                )
            ),
        ] | None = None,
        armccPath: Annotated[
            StrictStr,
            Field(
                description=(
                    "Absolute armcc.exe queried only with the fixed --vsn "
                    "option; presence is not license or build evidence."
                )
            ),
        ] | None = None,
    ) -> dict[str, object]:
        """Diagnose the bound project's Toolkit environment.

        Read-only, with no install, editor-window, build, license, or hardware
        effect.  ``ok=true`` means the report was collected, not that every
        observation is ready.  By default the selected local VS Code CLI is
        asked for the three recommended extensions with the fixed
        ``--list-extensions --show-versions`` arguments; pass
        ``probeVscodeExtensions=false`` to skip.  Only the local default
        profile is inspected: this is not the active window, a remote host,
        enabled/activated extension state, or successful debug evidence.
        ``data.vscodeExtensions`` contains observed values only; declared
        support-profile values remain separately under
        ``data.creationSupport.vsCodeExtensions``.  Incomplete, truncated,
        malformed, ambiguous, nonzero, or timed-out output yields
        ``installed=null`` with a precise status and diagnostic, never a
        fabricated absence.
        ``data.creationSupport.vsCodeExtensionsSource`` is fixed to
        ``support-profile-declared`` to mark the declared provenance of
        ``creationSupport.vsCodeExtensions``; it never describes the live
        ``data.vscodeExtensions`` values.  ``data.keilTools`` reports bounded
        UV4/ARMCC discovery; ``toolkitNativeBuildSupported`` is always false,
        so use the Keil migration or external-firmware routes.  These
        observation options and fields are current v1.3.1 source behavior; a
        frozen or installed earlier 1.3.0 server does not expose them, and
        their absence there is not evidence that the MCP client is stale.  probeCore describes the
        managed runtime and probe lease directory.  Version and binding
        evidence comes from data.runtime.toolkitVersion and
        data.publicInventory: compare them with the actual tool list and input
        schemas the client exposes, and with stm32_project_context
        data.project.root.  A launcher/CLI version alone does not prove the
        bound server's version, and an inventory count is not proof that the
        client registered those tools.  After an upgrade restart VS Code once
        and verify again; missing tools or fields, or a different root, means
        stop the dependent operation and explain the mismatch.
        """
        return await tool_doctor_for_request(
            runtime,
            ctx,
            probe_vscode_extensions=probeVscodeExtensions,
            vscode_path=vscodePath,
            uv4_path=uv4Path,
            armcc_path=armccPath,
        )

    @mcp.tool(name=MCP_TOOL_NAMES["project_detect"])
    async def stm32_project_detect(ctx: Context) -> dict[str, object]:
        """Identify project markers under the bound project root.

        Read-only.  Detection reports files and a recommended action; it does
        not evaluate migration blockers or hardware readiness.
        """
        return await tool_project_detect_for_request(runtime, ctx)

    @mcp.tool(name=MCP_TOOL_NAMES["project_context"])
    async def stm32_project_context(ctx: Context) -> dict[str, object]:
        """Return the bound project's current readiness evidence.

        Start every workflow here.  The legacy capability booleans remain for
        compatibility; read capabilityDetails for per-capability status
        (available, blocked, or not-evaluated), reasons, and next steps.
        Constant-false hardware capabilities such as flash, targetTest,
        monitor, and breakpointDebug mean "not evaluated in context", not that
        the tools are missing.  Context does not enumerate probes or scan all
        sources.  For Keil, select the exact project-relative uvprojx from
        data.project.files; context does not list target names.  Use
        stm32_keil_inspect with the uvprojx and omit targetName when the exact
        target is unknown, then keep the returned
        data.inspection.target_name for stm32_keil_preflight and
        stm32_keil_convert; entry-point availability does not establish
        migration readiness.
        data.firmwareRoutes separates two explicitly selected routes.  The
        managed entry mirrors capabilityDetails.flash and identifies
        stm32_flash with the data.build.buildId/elfSha256 identity pins and
        Git-shaped provenance.  The imported entry is always not-evaluated
        here: context checked no firmware, target, plan, MAP, admission, or
        probe.  It identifies stm32_firmware_import -> stm32_firmware_admit ->
        stm32_flash_imported, needs no Git or managed model, and requires
        separate authorization for the immutable copy and then hardware.
        Tool availability is not image readiness; a managed blocker does not
        block the separate imported route, and no route switches
        automatically.  An imported receipt never unlocks managed debug,
        Monitor, Target tests, or recovery.
        """
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
        """Inspect one exact Keil target before migration.

        Call stm32_project_context first and pass its project-root-relative
        uvprojx.  Context does not list target names.  If the exact target is
        unknown, omit targetName: a KEIL_TARGET_SELECTION_REQUIRED failure
        lists the available choices in details.targets.  Let the user choose,
        then call inspect again with that exact targetName.  A successful
        inspection returns data.inspection.target_name; preserve that exact
        value as targetName for preflight and convert.  Do not guess a target.
        Inspection is read-only: entry-point availability does not establish
        migration readiness, and baseline.available only means a historical
        AXF/MAP was parsed.  Next call stm32_keil_preflight with the same
        uvprojx and targetName.
        """
        return await tool_keil_inspect_for_request(
            runtime, ctx, uvprojx, targetName, includeBaseline
        )

    @mcp.tool(name=MCP_TOOL_NAMES["keil_preflight"])
    async def stm32_keil_preflight(
        ctx: Context,
        uvprojx: str | None = None,
        targetName: str | None = None,
        startupStrategy: str | None = None,
        startupSource: str | None = None,
        memoryLayout: dict[str, str] | None = None,
        extraRegions: list[dict[str, Any]] | None = None,
    ) -> dict[str, object]:
        """Run read-only Keil migration preflight without requiring Git.

        Use the same project-root-relative uvprojx and exact targetName as
        inspect.  A successful result means analysis completed; it may still
        contain typed blockers.  Read analysis.blockers and planReadiness
        (technical/Git prerequisites for obtaining a plan) separately from
        applyReadiness, which stays ready=false with
        status=requires-reviewed-plan.  Preflight returns no applicable plan
        ID, writes nothing, does not transcode sources, replace startup code,
        or run git init, and never authorizes apply.  A source-encoding
        blocker may be prepared with the separate normalize-source-comments
        companion skill, whose instructions and helper live in its skill
        directory (there is no normalization MCP tool); that helper writes
        only reviewed copies outside the project, and preflight itself still
        writes nothing and does not transcode. Each blocker's additive
        remediation names a real MCP tool in tool or the separate Skill in
        skill, never conflates them. Its encoding summary applies only when
        every affected file's charset is explicitly declared and the change
        is comment-only; other bytes remain unsupported.
        To review the supported CMSIS startup route, pass
        startupStrategy="generate-cmsis-gcc".  Pass startupSource="<exact
        project-relative included ARMCC .s path>" when more than one included
        non-empty assembly source exists; without startupSource an ambiguous
        selection fails with MIGRATION_STARTUP_SELECTION_REQUIRED and
        details.candidates.  The same two values must be used for convert and
        apply; planReadiness.nextSteps repeats the exact startup choice to
        retain when the option is present.  The generated destination is
        Startup/stm32tk_startup_gcc.S; analysis.startup reports the exact
        source hash, vectors, reserved slots, stack/heap bytes, diagnostics
        and generated digest.  This is a reviewed migration patch, not ARMCC
        or Microlib equivalence.
        Managed multi-RAM memory requires a reviewed choice.  Read
        analysis.memoryLayout (status, resolved layout or null, and the actual
        flash/ram candidates).  status=requires-selection accompanies a
        MEMORY_LAYOUT_REQUIRED blocker while every other blocker is still
        returned; pass memoryLayout with exactly flash, data, bss, heap and
        stack keys, each naming an existing region.  memoryLayout is an
        object parameter: a JSON string or other non-object is rejected by the
        registered MCP input schema before this tool runs, while an object with
        unknown/incomplete roles or invalid region access returns the
        structured MEMORY_LAYOUT_INVALID field/rule/remediation.  Flash must be
        readable, executable and non-writable; data/bss/heap/stack must be
        readable and writable.  A writable executable RAM is never inferred as
        Flash, and CCM/external RAM is never selected automatically.  Use the
        same memoryLayout for preflight, the PLAN call and apply; an omitted
        mapping and an explicit all-main-RAM choice are different reviewed
        requests.  A native linker-script project keeps its own layout and
        cannot also declare memoryLayout.
        External RAM is a separate explicit request.  Pass extraRegions as a
        real JSON array of objects, not a JSON string; each object has exactly
        name, origin, length and attributes, with attributes rw- or rwx.  No
        origin, length, name or access is inferred from the device, an address
        expression or the board, and only 1-64 character ASCII linker names,
        exact integer origins/lengths and at most 32 non-overlapping entries
        are accepted.  The inspected Keil base regions are unchanged; the
        typed project map is base plus extras.  A non-empty request is bound
        into plan identity and is exposed as analysis.extraRegions; omitting
        or changing it is a different request.  The registered parameter is
        list[dict[str, Any]] so raw scalar values reach the shared validator:
        the MCP framework rejects a non-array or non-object entry before this
        tool runs, while invalid names/ranges/attributes, duplicate keys in a
        CLI JSON string, and overlaps with actual base regions return the
        structured EXTRA_REGIONS_INVALID field/rule/remediation.  Extra RAM
        adds RAM candidates and never a Flash candidate; data/bss/heap/stack
        are not placed there implicitly.  A missing extra leaves
        MIGRATION_FIXED_SECTION_OUTSIDE_MEMORY actionable: request the exact
        owner-supplied map and never guess a length.
        Each analysis.blockers entry adds remediation: category is
        needs-user-input or unsupported, with a concise summary, a real
        tool/Skill reference where applicable, and requiredInputs.  Only
        currently accepted preflight parameters are named (memoryLayout,
        extraRegions, startupStrategy, startupSource); preflight has no
        framework, FPU, or ABI override parameter, and no blocker is
        auto-fixable.
        blockerSummary.byRemediation counts the same classifications while
        total, byCode, and every original blocker field stay unchanged.
        When analysis is complete and no blockers remain, establish any Git
        prerequisite as an explicit project-owner decision, then call
        stm32_keil_convert with no planId to obtain a PLAN response.  Read
        its data.plan_id and data.patches[].unified_diff; only after review
        and explicit user authorization pass that exact value as planId with
        authorized=true.
        """
        return await tool_keil_preflight_for_request(
            runtime,
            ctx,
            uvprojx,
            targetName,
            startupStrategy,
            startupSource,
            memoryLayout,
            extraRegions,
        )

    @mcp.tool(name=MCP_TOOL_NAMES["keil_convert"])
    async def stm32_keil_convert(
        ctx: Context,
        uvprojx: str | None = None,
        targetName: str | None = None,
        planId: str | None = None,
        authorized: bool = False,
        startupStrategy: str | None = None,
        startupSource: str | None = None,
        memoryLayout: dict[str, str] | None = None,
        extraRegions: list[dict[str, Any]] | None = None,
    ) -> dict[str, object]:
        """Plan or explicitly apply one Keil-to-GCC migration.

        With no planId and authorized=false this returns a deterministic,
        Git-bound PLAN response whose identifier is data.plan_id and whose
        complete diff is data.patches[].unified_diff.  Keep the same uvprojx
        and exact targetName across every call.  Review every blocker, that
        exact data.plan_id, and the complete patches/diff before acting.
        Apply only after the user explicitly authorizes that exact plan: pass
        its data.plan_id as the apply request's planId with authorized=true.
        Pass the same startupStrategy="generate-cmsis-gcc" and
        startupSource="<exact project-relative source>" values used for
        preflight and plan; the options are bound into the plan digest, and a
        changed or omitted choice is never silently accepted on apply: the
        request fails with a structured validation error or PLAN_CHANGED.
        With the startup strategy the normal manifest/source patches are
        accompanied by a create-only startup patch for
        Startup/stm32tk_startup_gcc.S; the original ARMCC startup is
        preserved, and the plan records memory.stackSize, memory.heapSize and
        generation.runtimeInitialization=cmsis-gcc-v1 and reports
        data.startup with source/generated hashes, vectors and review
        warnings.  Review that evidence and the generated reset path; this is
        not ARMCC, ABI or Microlib behavioral equivalence.
        Pass the same memoryLayout object used for preflight when a managed
        multi-RAM layout is required.  The PLAN response exposes
        data.memory_layout (status, resolved layout or null, and actual
        candidates) and binds the exact explicit mapping into data.plan_id; an
        omitted mapping is a different reviewed choice, and apply refuses a
        changed or omitted mapping.  The generated linker places .data/.bss/
        heap/stack in their selected regions with the .data load address in
        the selected Flash.  This is offline placement evidence, not proof of
        CCM/external-RAM or board runtime behavior.
        Pass the same extraRegions array used for preflight to bind the exact
        owner-supplied external-RAM request into data.plan_id.  The PLAN
        response exposes data.extra_regions and the conversion report records
        extraRegions; the proposed manifest keeps the inspected Keil
        memory.regions unchanged and adds memory.extraRegions.  Omitting,
        shortening or changing any entry is a different request and apply
        returns a structured validation failure or PLAN_CHANGED without
        writing.  Extra RAM adds RAM candidates only: never a Flash candidate,
        and data/bss/heap/stack are not placed there implicitly.  The owner
        must arrange external-memory initialization before access; NOLOAD
        fixed sections are not promised initialized.  A native linker script
        remains user-owned and is not rewritten.
        The core replans and rechecks digest, Git, and drift guards before its
        first write.  Never run git init, transcode source text, replace ARMCC
        startup blindly, or reuse a stale plan ID; a missing Git repository is
        an explicit project-owner decision.
        """
        return await tool_keil_convert_for_request(
            runtime,
            ctx,
            uvprojx,
            targetName,
            planId,
            authorized,
            startupStrategy,
            startupSource,
            memoryLayout,
            extraRegions,
        )

    @mcp.tool(name=MCP_TOOL_NAMES["project_configure"])
    async def stm32_project_configure(
        ctx: Context,
        planId: str | None = None,
        authorized: bool = False,
        debugBackend: Any = None,
        debugTarget: Any = None,
        vscodeToolkitPath: Any = None,
        vscodeGccPath: Any = None,
    ) -> dict[str, object]:
        """Plan or explicitly apply managed GCC/CMake and VS Code configuration.

        With no planId and authorized=false this is a read-only PLAN response
        whose identifier is data.plan_id.  Review blockers, that exact
        data.plan_id, and the per-file status/diff first.  Apply only by
        passing that data.plan_id as the planId request argument with
        authorized=true after explicit user authorization.  Preserved unowned
        files are not generated or adopted.

        Omit debugBackend and debugTarget to keep the historical build-only
        route.  Pass both as raw strings to set exactly debug.backend and
        debug.target in the existing .stm32-project.json: the PLAN then also
        returns data.debug_configuration and data.manifest_edit (status,
        before/after SHA-256 and sizes, unified_diff).  One value alone, a
        non-string value, an empty/whitespace value or a backend other than
        \"pyocd\" fails with DEBUG_CONFIGURATION_INVALID and complete
        diagnostics before any write.  Pass the same pair on apply; a
        changed or omitted pair is a different plan and is refused without
        writing.  The pair records metadata only: it does not discover,
        install or verify a PyOCD target, and it is not a live debug session.

        Omit vscodeToolkitPath and vscodeGccPath for portable defaults: the
        generated tasks use `${config:stm32-toolkit.executablePath}` and
        IntelliSense uses `${config:stm32-toolkit.compilerPath}`, which must be
        absolute verified native paths in user-scope VS Code settings.  Pass
        both to render validated absolute native paths instead (Windows:
        regular `.exe` files, never `.cmd`/`.bat`, variables, directories,
        symlinks or reparse points).  The two paths bind the immutable plan:
        pass the same values on apply, or the request is a different plan and
        is refused before any write.  vscodeGccPath configures IntelliSense
        only; it does not silently select the CMake build toolchain.  This
        static validation is not a binary version or trust attestation.
        """
        return await tool_project_configure_for_request(
            runtime,
            ctx,
            planId,
            authorized,
            debugBackend,
            debugTarget,
            vscodeToolkitPath,
            vscodeGccPath,
        )

    @mcp.tool(name=MCP_TOOL_NAMES["build"])
    async def stm32_build(
        ctx: Context,
        preset: Literal["arm-debug", "arm-release"],
        clean: bool = False,
        timeoutSeconds: Annotated[int, Field(ge=1, le=3600)] = 300,
        authorized: bool = False,
    ) -> dict[str, object]:
        """Build one configured preset with explicit authorization.

        Read capabilityDetails.build from stm32_project_context, not only the
        legacy build boolean: blocked means a concrete prerequisite is
        missing, while not-evaluated means this context did not check it.
        The build never runs without authorized=true.  Git is not required:
        with a committed HEAD the identity is schema 1; when Git is missing,
        unborn or unreadable the identity is schema 2 with
        sourceBaseline="input-snapshot-v1", bounded gitEvidence
        {status:"unavailable", code:"BUILD_GIT_INVALID", rule:"head"},
        and null gitHead/gitDirty.  The gitEvidence rule is either "head" or
        "status".  Never treat null Git fields as clean and
        never fabricate a commit.  Schema-2 evidence is build-only: flash,
        debug, Target tests, Monitor and acceptance still require Git-shaped
        provenance, and shared firmware admission returns
        FIRMWARE_PROVENANCE_UNSUPPORTED before probe effects; wrappers may map
        that code under their existing protocol (acceptance recovery maps it
        to ACCEPTANCE_ATTEMPT_OUTPUT_INVALID).  Report the returned identity
        evidence exactly; a failed build leaves prior artifacts stale.

        Retain the complete BUILD_OUTPUT_STALE response before any further
        operation, because the next build overwrites the current log and
        result.  Details keep legacy path/rule and add a bounded reason:
        output-unavailable, prior-evidence-unavailable,
        prior-build-not-successful, input-snapshot-mismatch, or
        prior-evidence-mismatch; evidenceField/evidenceSource name only fixed
        fields and never echo recorded values.  For
        remediation.action=clean-rebuild (unchanged outputs with clean=false),
        the exact CLI tokens and MCP parameters preserve preset and
        timeoutSeconds and omit authorized.  CLI tokens are only the command
        tail, not a standalone invocation: prefix the caller-verified Toolkit
        executable and the required remediation.cli.projectRoot option
        (--project-root) with the same binding's verified absolute project
        root, even when the current directory is the project root; bare
        tokens are rejected.  The executable label is symbolic, not a real
        path, and the advice contains no absolute root or shell command.
        Send the MCP call to this same bound server/project.  Both are
        diagnostic advice, not authorization: execute them only under the
        user's applicable authorization for that exact clean build.
        For inspect-build-log
        (missing/unavailable output or clean already requested), inspect the
        build log and configuration instead of repeating a clean build; a
        clean build is not guaranteed to fix either case.  BUILD_PROJECT_INVALID
        (including managed-file drift or fragment provenance) is a
        configure/fragment repair problem, not stale output: do not clean or
        edit hashes to bypass it.
        """
        return await tool_build_for_request(
            runtime, ctx, preset, clean, timeoutSeconds, authorized
        )

    @mcp.tool(name=MCP_TOOL_NAMES["probe_list"])
    async def stm32_probe_list(ctx: Context) -> dict[str, object]:
        """Enumerate connected debug probes; read-only discovery only.

        Use this whenever the user only asks which probes are connected.  It
        requires no Toolkit manifest, configured build, debug backend, target,
        SVD, or firmware identity, and does not modify the board: it performs
        no attach, select, reset, halt, flash, lease, or project write.
        workspaceId is null with an
        explicit unbound discovery status when no valid project model exists;
        never invent one.  Discovery grants no board-modification permission
        and does not establish target identity or flash readiness.
        """
        return await tool_probe_list_for_request(runtime, ctx)

    @mcp.tool(name=MCP_TOOL_NAMES["flash"])
    async def stm32_flash(
        ctx: Context,
        probeId: ProbeId,
        expectedBuildId: Digest,
        expectedElfSha256: Digest,
        authorized: StrictBool = False,
        recoveryUnderReset: StrictBool = False,
        frequencyHz: FlashFrequency | None = None,
    ) -> dict[str, object]:
        """Flash one exact probe with the current firmware identity pins.

        Use the exact probeId returned by stm32_probe_list.  Read the current
        firmware pins from stm32_project_context as data.build.buildId and
        data.build.elfSha256 and pass them as expectedBuildId and
        expectedElfSha256; never fabricate or reuse stale identity.  Read
        capabilityDetails.flash rather than the legacy context boolean: a
        fresh schema-2 input-snapshot build has status=blocked because
        firmware admission requires Git-shaped provenance and returns
        FIRMWARE_PROVENANCE_UNSUPPORTED before any probe, lease or attach
        effect.  Restore a committed Git baseline and rebuild instead of
        fabricating a commit.  This is the managed route only: a blocked or
        failed managed route never authorizes or automatically switches to
        the separate imported route (stm32_firmware_import,
        stm32_firmware_admit, stm32_flash_imported), which needs its own
        explicit selection, inputs, and authorization.  An imported receipt
        is not a managed build identity and does not unlock debug, Monitor,
        Target tests, or recovery.  This tool modifies the board and runs
        only with authorized=true after explicit user authorization for this
        exact operation.  Under-reset recovery is a separate policy, never
        an automatic retry.  frequencyHz is an optional explicit debug
        frequency in Hz (100000..50000000); omit it to keep the configured
        default.  Under-reset recovery keeps its fixed 100000 Hz policy, so
        a conflicting explicit frequency fails before any effect.  The
        result's details.flashOptions records selected configuration, not a
        measured or verified hardware frequency.  details.recoverySuggestion
        can appear only for a failed managed normal (non-recovery) attempt:
        PROBE_PROGRAM_FAILED after owned cleanup, or PROBE_ATTACH_FAILED with
        a validated attachDiagnostic whose primary.stage is session-open or
        halt-verify and whose primary.reason is probe-disconnected, probe-io,
        transport-timeout, transport-fault, transport-error, target-response,
        target-register, debug-command, debug-operation, postcondition-failed,
        or backend-code.
        It is absent for cleanup, identity, stale/provenance, verification or
        readback, input, authorization, receipt, success, cancellation,
        already-recovery and imported results.  The suggestion is
        informational, requires new authorization, and never retries
        automatically.  Imported flash does not gain recovery from it.
        """
        return await tool_flash_for_request(
            runtime,
            ctx,
            probeId,
            expectedBuildId,
            expectedElfSha256,
            authorized,
            recoveryUnderReset,
            frequencyHz,
        )

    @mcp.tool(name=MCP_TOOL_NAMES["firmware_import"])
    async def stm32_firmware_import(
        ctx: Context,
        firmwarePath: ProjectRelativePath,
        expectedSha256: Digest,
        format: Literal["elf", "hex", "bin"],
        target: FirmwareTarget,
        flashRegions: Annotated[
            list[FirmwareFlashRegion], Field(min_length=1, max_length=32)
        ],
        baseAddress: Annotated[StrictInt, Field(ge=0, le=0xFFFF_FFFF)] | None = None,
        planId: Digest | None = None,
        authorized: StrictBool = False,
    ) -> dict[str, object]:
        """Plan or explicitly persist one immutable external firmware import.

        This is a source-only offline workflow: it does not require a managed
        project manifest, Git repository, build receipt, or SVD, and it never
        touches a probe, lease, worker, or board.  Use it only when the user
        explicitly selects this independent imported route; a managed
        context, provenance, or flash failure never switches to it
        automatically, and a context model error does not prove this tool is
        absent.  Without planId it returns a
        deterministic read-only PLAN with data.planId, data.importId,
        data.source (original path/SHA-256/size) and data.image (normalized
        ELF SHA-256/size/segments); keep those two hashes distinct.
        authorized=true without planId is an error.  With the exact returned
        planId and authorized=true it re-reads and re-analyzes the source and
        persists an immutable copy under the external data root.  Changing any
        source, option, or binding input invalidates the plan before writes; a
        conflicting existing import is never overwritten.  Import authorization
        covers only the offline copy and does not authorize hardware.
        AXF is parsed as ELF; BIN requires an explicit uint32 baseAddress and
        carries no debug symbols.  flashRegions is a reviewed declaration of
        STM32 internal application Flash addresses, not a measured chip
        capacity.  Next call stm32_firmware_admit offline, then select a probe
        and separately authorize stm32_flash_imported.
        """
        return await tool_firmware_import_for_request(
            runtime,
            ctx,
            firmwarePath,
            expectedSha256,
            format,
            target,
            flashRegions,
            baseAddress,
            planId,
            authorized,
        )

    @mcp.tool(name=MCP_TOOL_NAMES["firmware_admit"])
    async def stm32_firmware_admit(
        ctx: Context,
        importId: Digest,
        expectedSha256: Digest,
    ) -> dict[str, object]:
        """Admit one stored external import offline and read-only.

        expectedSha256 always pins the imported ORIGINAL source file, not the
        normalized ELF.  The workflow rebuilds the normalized image from the
        stored source and parameters instead of trusting stored assertions,
        and validates the canonical identity, target, and Flash regions
        against this project and data root.  It returns offlineReady=true and
        hardwareVerified=false plus the exact segment summaries and remaining
        hardware requirements.  It creates no service, lease, worker,
        authorization token, or receipt, and it cannot admit debug, Monitor,
        Target tests, legacy build evidence, or a current build identity.
        """
        return await tool_firmware_admit_for_request(
            runtime, ctx, importId, expectedSha256
        )

    @mcp.tool(name=MCP_TOOL_NAMES["flash_imported"])
    async def stm32_flash_imported(
        ctx: Context,
        probeId: ProbeId,
        importId: Digest,
        expectedSha256: Digest,
        authorized: StrictBool = False,
        frequencyHz: FlashFrequency | None = None,
    ) -> dict[str, object]:
        """Flash one admitted external import to one exact probe.

        Use the exact probeId returned by stm32_probe_list and the exact
        importId/sourceSha256 returned by stm32_firmware_admit.  This modifies
        the board and runs only with authorized=true after explicit user
        authorization for this exact operation.  Admission is revalidated
        before any supervisor, lease, or worker effect and again inside the
        owned action before attach/program; the caller cannot override the
        target, Flash regions, file paths, roots, backend, or provenance.
        The backend rejects the whole image before programming if any segment
        is outside the attached target's declared Flash map, and every planned
        byte is read back.  A distinct external-flash receipt is written only
        after successful readback and cleanup.  frequencyHz is an optional
        explicit debug frequency in Hz (100000..50000000); omit it to keep the
        configured default.  details.flashOptions records selected
        configuration, not a measured frequency.  This path adds no
        recovery-under-reset, reset, resume, handoff, debug, Monitor, or Target
        test capability, and its receipt does not unlock them.
        """
        return await tool_flash_imported_for_request(
            runtime,
            ctx,
            probeId,
            importId,
            expectedSha256,
            authorized,
            frequencyHz,
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
        """Begin one authorized debugger handoff for an exact probe.

        Requires the exact probeId and current buildId/ELF SHA-256 and
        authorized=true after explicit user authorization.  The returned
        ticket is one-time secret material: do not log or summarize it.
        """
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
        """Reacquire, verify, consume, and release one handoff ticket.

        Call once after the external debugger stops.  Do not expose the
        ticket, retry automatically, or assume the prior session is still
        valid.
        """
        return await tool_handoff_end_for_request(runtime, ctx, probeId, ticket)

    @mcp.tool(name=MCP_TOOL_NAMES["variable_read"])
    async def stm32_variable_read(
        ctx: Context,
        probeId: ProbeId,
        expectedBuildId: Digest,
        expectedElfSha256: Digest,
        expressions: Items,
    ) -> dict[str, object]:
        """Read typed DWARF variables from one exact probe.

        Requires the exact probeId and current buildId/ELF SHA-256.  Supply
        DWARF expressions only; the Toolkit derives types and locations from
        the bound ELF.  The read action performs no memory write and no
        explicit target control.  The shared OBSERVE attach may briefly halt
        and resume the core while connecting; this is not a state-preserving
        attach and is not halted-run analysis.  A schema-2 input-snapshot
        build is rejected by the shared firmware admission boundary before
        attach; wrappers may map its stable FIRMWARE_PROVENANCE_UNSUPPORTED
        code under their existing protocol.
        """
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
        """Take a finite typed sample series from one exact probe.

        Requires an exact probe and current firmware identity pins plus a
        bounded count or duration.  Sampling performs no memory write and no
        explicit target control.  The shared OBSERVE attach may briefly halt
        and resume the core while connecting; it is not state-preserving and
        does not make this halted-run analysis.  A schema-2 input-snapshot
        build is rejected by the shared firmware admission boundary before
        attach; wrappers may map its stable FIRMWARE_PROVENANCE_UNSUPPORTED
        code under their existing protocol.
        """
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
        """Read named peripheral registers from the project's exact SVD.

        Requires the exact probe, current firmware identity pins, and the
        configured project SVD; callers never supply a target, SVD, address,
        or access size.  acknowledgeAccessRisk confirms the caller reviewed
        the read-access risk and is not a substitute for target provenance.
        A schema-2 input-snapshot build is rejected by the shared firmware
        admission boundary before attach; wrappers may map its stable
        FIRMWARE_PROVENANCE_UNSUPPORTED code under their existing protocol.
        """
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
        haltForAnalysis: StrictBool = False,
    ) -> dict[str, object]:
        """Analyze the current Fault state, optionally with controlled halt.

        haltForAnalysis=true is an explicit CONTROL authorization: it performs
        one halt, analysis, and one resume with verified running state.  It
        requires a running target and exact firmware identity.  A schema-2
        input-snapshot build is rejected by the shared firmware admission
        boundary before attach; wrappers may map its stable
        FIRMWARE_PROVENANCE_UNSUPPORTED code under their existing protocol.
        Do not retry, reconnect, reset, or flash after an unknown/failed
        recovery.
        """
        return await tool_fault_analyze_for_request(
            runtime,
            ctx,
            probeId,
            expectedBuildId,
            expectedElfSha256,
            haltForAnalysis,
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
            [_diagnostic_step_data(step) for step in steps],
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
        verificationPlan: VerificationPlanRequestInput,
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
        ctx: Context,
        probeId: ProbeId,
        caseIds: Annotated[list[CaseId], Field(min_length=1, max_length=MAX_CASES), AfterValidator(_unique_case_ids)],
        recoveryUnderReset: StrictBool = False,
    ) -> dict[str, object]:
        return await tool_test_target_prepare_for_request(
            runtime, ctx, probeId, caseIds, recoveryUnderReset
        )

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
        diagnosticSessionId: AcceptanceDiagnosticRef,
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
        scenarioId: AcceptanceAttemptScenarioId,
        scenarioVersion: AcceptanceScenarioVersion,
        continuation: ContinuationInput | None = None,
    ) -> dict[str, object]:
        return await tool_acceptance_attempt_begin_for_request(
            runtime, ctx, attemptId, scenarioId, scenarioVersion, continuation
        )

    @mcp.tool(name=MCP_TOOL_NAMES["acceptance_attempt_checkpoint"])
    async def stm32_acceptance_attempt_checkpoint(
        ctx: Context,
        attemptId: AcceptanceUuid,
        expectedRevision: AcceptanceRevision,
        stage: AcceptanceAttemptStage,
        testRunId: AcceptanceRunId | None = None,
        diagnosticSessionId: AcceptanceDiagnosticRef | None = None,
        acceptanceRecordId: AcceptanceUuid | None = None,
        sourceChangeIntent: PhysicalSourceChangeIntentInput | None = None,
        fixVerificationId: Digest | None = None,
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
            sourceChangeIntent,
            fixVerificationId,
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
    parser.add_argument(
        "--project-root",
        required=True,
        type=_mcp_root_type,
        action=_RejectDuplicateArgument,
    )
    parser.add_argument(
        "--data-root",
        required=True,
        type=_mcp_root_type,
        action=_RejectDuplicateArgument,
    )
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
