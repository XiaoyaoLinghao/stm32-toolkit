"""Application workflows for the managed Host testing evidence boundary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from hashlib import sha256
from typing import Callable, Mapping
from datetime import datetime, timezone

from stm32_toolkit.build.identity import (
    GitEvidence,
    InputSnapshot,
    git_evidence,
    snapshot_project_inputs,
)
from stm32_toolkit.evidence import (
    EVIDENCE_CORRUPT,
    EVIDENCE_INVALID,
    EVIDENCE_LIMIT_EXCEEDED,
    EVIDENCE_PATH_UNSAFE,
    EvidenceEnvelope,
    EvidenceIdentity,
    EvidenceIdentityContext,
    EvidenceValidationError,
)
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.project_model import ProjectManifestError, load_project_model
from stm32_toolkit.result import OperationResult
from stm32_toolkit.testing.host import HostTestRunner
from stm32_toolkit.testing.artifacts import TestArtifactCollector
from stm32_toolkit.testing.model import (
    TestCaseResult,
    TestProtocolError,
    TestRunManifest,
    host_target_device,
    calculate_inventory_digest,
)
from stm32_toolkit.testing.protocol import (
    TARGET_FRAME_V1,
    TARGET_FRAME_V2,
    calculate_case_inventory_digest,
)
from stm32_toolkit.testing.publication import TestRunPublisher, TestRunRepository
from stm32_toolkit.testing.replay import (
    MAX_REPLAY_DESCRIPTOR_BYTES,
    TargetReplayDescriptor,
    canonical_replay_json_bytes,
    load_target_replay_fixture,
)
from stm32_toolkit.testing.target import (
    ConsumedTargetRun,
    TargetFrameDecoder,
    TargetRunBinding,
    TargetRunValidator,
    PhysicalRunProvenance,
    PhysicalTargetFlashAdapter,
    ProbeClientTargetTransport,
    TargetRunError,
    TargetTestRunner,
)
from stm32_toolkit.probe.flash import load_fresh_firmware_facts
from stm32_toolkit.probe.client import ProbeClient, ProbeClientError
from stm32_toolkit.probe.lease import ProbeLeaseError, ProbeLeaseManager
from stm32_toolkit.probe.model import OperationLevel
from stm32_toolkit.probe.supervisor import ProbeServiceConfig, ProbeServiceSupervisor
from stm32_toolkit.probe.service import ProbeServiceError
from stm32_toolkit.probe.worker import ProbeWorkerConfig


_DISCOVER_OPERATION = "test.host.discover"
_RUN_OPERATION = "test.host.run"
_SHOW_OPERATION = "test.show"
_REPLAY_OPERATION = "test.target.replay"
_TARGET_PREPARE_OPERATION = "test.target.prepare"
_TARGET_EXECUTE_OPERATION = "test.target.execute"
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_PORTABLE_PROBE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass(frozen=True)
class TestingWorkflowContext:
    project_root: Path
    data_root: Path
    session_id: str


@dataclass(frozen=True)
class _WorkflowState:
    model: object
    host_config: object
    workspace: WorkspacePaths
    identity: EvidenceIdentityContext | None
    evidence_store: EvidenceStore
    results_root: Path


class _WorkflowFailure(Exception):
    """Internal typed failure used for context construction boundaries."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


# These are deliberately narrow seams for the fixed construction/read points
# of this module.  They are not a general dependency-injection facility.
_load_project_model = load_project_model
_snapshot_project_inputs = snapshot_project_inputs
_git_evidence = git_evidence
_host_runner_factory = HostTestRunner
_evidence_store_factory = EvidenceStore
_publisher_factory = TestRunPublisher
_repository_factory = TestRunRepository


_PUBLIC_MESSAGES = {
    EVIDENCE_INVALID: "Evidence is invalid.",
    EVIDENCE_CORRUPT: "Evidence is corrupt.",
    EVIDENCE_PATH_UNSAFE: "Evidence path is unsafe.",
    EVIDENCE_LIMIT_EXCEEDED: "Evidence limit exceeded.",
    "PROJECT_NOT_CONFIGURED": "Project is not configured.",
    "PROJECT_TESTING_NOT_CONFIGURED": "Project testing is not configured.",
    "PROJECT_JSON_INVALID": "Project manifest JSON is invalid.",
    "PROJECT_SCHEMA_INVALID": "Project manifest schema is invalid.",
    "PROJECT_SCHEMA_VERSION_UNSUPPORTED": "Project manifest schema version is unsupported.",
    "TEST_NO_CASES": "No test cases were discovered.",
    "TEST_CASE_NOT_FOUND": "A requested test case was not discovered.",
    "TEST_INVENTORY_CHANGED": "The test inventory changed.",
    "TEST_PROTOCOL_INVALID": "Test protocol is invalid.",
    "TEST_TIMEOUT": "Test operation timed out.",
    "TEST_TRANSPORT_UNAVAILABLE": "Target test transport is unavailable.",
    "TEST_AUTHORIZATION_INVALID": "Target test authorization is invalid.",
    "TEST_IDENTITY_MISMATCH": "Test identity does not match.",
    "TEST_EXECUTION_FAILED": "Test execution failed.",
    "TEST_FLASH_FAILED": "Target firmware flash failed.",
    "PROBE_BUSY": "The selected probe is busy.",
}

_TEST_CODE_MAP = {
    "TEST_PROCESS_TIMEOUT": "TEST_TIMEOUT",
    "TEST_PROCESS_ERROR": "TEST_EXECUTION_FAILED",
    "TEST_PROCESS_FAILED": "TEST_EXECUTION_FAILED",
    "TEST_FLASH_FAILED": "TEST_EXECUTION_FAILED",
    "TEST_DUPLICATE_CASE": "TEST_PROTOCOL_INVALID",
    "TEST_ENVIRONMENT_INVALID": "TEST_PROTOCOL_INVALID",
    "TEST_DISCOVERY_INVALID": "TEST_PROTOCOL_INVALID",
    "TEST_EVENT_PAYLOAD_INVALID": "TEST_PROTOCOL_INVALID",
    "TEST_EVENT_SEQUENCE_INVALID": "TEST_PROTOCOL_INVALID",
    "TEST_EXIT_MISMATCH": "TEST_PROTOCOL_INVALID",
    "TEST_NATIVE_RESULT_INVALID": "TEST_PROTOCOL_INVALID",
    "TEST_FRAME_CRC_INVALID": "TEST_PROTOCOL_INVALID",
    "TEST_FRAME_VERSION_INVALID": "TEST_PROTOCOL_INVALID",
    "TEST_STREAM_INCOMPLETE": "TEST_PROTOCOL_INVALID",
    "TEST_FRAME_TOO_LARGE": EVIDENCE_LIMIT_EXCEEDED,
    "TEST_FRAME_RECOVERY_LIMIT": EVIDENCE_LIMIT_EXCEEDED,
    "TEST_STREAM_TOO_LARGE": EVIDENCE_LIMIT_EXCEEDED,
    "TEST_PROCESS_OUTPUT_LIMIT": EVIDENCE_LIMIT_EXCEEDED,
    "TEST_RESULTS_UNSAFE": EVIDENCE_PATH_UNSAFE,
    "TEST_REPLAY_INVALID": "TEST_PROTOCOL_INVALID",
    "TEST_REPLAY_INTEGRITY": "TEST_PROTOCOL_INVALID",
    "TEST_REPLAY_FIXTURE_INVALID": "TEST_PROTOCOL_INVALID",
    "TEST_REPLAY_FIXTURE_UNSAFE": EVIDENCE_PATH_UNSAFE,
    "TEST_REPLAY_FIXTURE_LIMIT": EVIDENCE_LIMIT_EXCEEDED,
}


def _failure(operation: str, code: str) -> OperationResult[None]:
    if code not in _PUBLIC_MESSAGES:
        raise RuntimeError(f"unknown public workflow code: {code}")
    public_code = code
    return OperationResult.failure(
        operation,
        public_code,
        _PUBLIC_MESSAGES[public_code],
        {},
    )


def _project_failure(operation: str, error: BaseException) -> OperationResult[None]:
    code = getattr(error, "code", "PROJECT_NOT_CONFIGURED")
    return _failure(operation, code)


def _test_failure(operation: str, error: TestProtocolError) -> OperationResult[None]:
    code = _TEST_CODE_MAP.get(error.code, error.code)
    return _failure(operation, code)


def _evidence_failure(operation: str, error: EvidenceValidationError) -> OperationResult[None]:
    return _failure(operation, error.code)


def _exception_result(operation: str, error: BaseException) -> OperationResult[None]:
    if isinstance(error, _WorkflowFailure):
        return _failure(operation, error.code)
    if isinstance(error, EvidenceValidationError):
        return _evidence_failure(operation, error)
    if isinstance(error, TestProtocolError):
        return _test_failure(operation, error)
    if isinstance(error, ProjectManifestError):
        return _project_failure(operation, error)
    if isinstance(error, (ProbeClientError, ProbeLeaseError, ProbeServiceError, TargetRunError)):
        code = error.code
        if code == "PROBE_BUSY":
            return _failure(operation, "PROBE_BUSY")
        mapped = {
            "PROBE_IDENTITY_MISMATCH": "TEST_IDENTITY_MISMATCH",
            "PROBE_BACKEND_ERROR": "TEST_TRANSPORT_UNAVAILABLE",
            "PROBE_OPERATION_UNAVAILABLE": "TEST_TRANSPORT_UNAVAILABLE",
            "PROBE_SERVICE_UNAVAILABLE": "TEST_TRANSPORT_UNAVAILABLE",
        }.get(code, code)
        if mapped in _PUBLIC_MESSAGES:
            return _failure(operation, mapped)
        return _failure(operation, "TEST_EXECUTION_FAILED")
    if operation in {_TARGET_PREPARE_OPERATION, _TARGET_EXECUTE_OPERATION}:
        mapped = {
            "FIRMWARE_INPUT_CHANGED": "TEST_INVENTORY_CHANGED",
            "FIRMWARE_IDENTITY_MISMATCH": "TEST_IDENTITY_MISMATCH",
            "FLASH_PLAN_CHANGED": "TEST_INVENTORY_CHANGED",
            "FLASH_IMAGE_INVALID": "TEST_INVENTORY_CHANGED",
        }.get(getattr(error, "code", None))
        if mapped is not None:
            return _failure(operation, mapped)
    raise error


def _configured_workspace(
    context: TestingWorkflowContext,
    *,
    require_host: bool = True,
) -> tuple[object, WorkspacePaths]:
    if not isinstance(context, TestingWorkflowContext):
        raise _WorkflowFailure("PROJECT_NOT_CONFIGURED")
    try:
        model = _load_project_model(context.project_root)
    except ProjectManifestError:
        raise
    except (OSError, ValueError) as error:
        raise _WorkflowFailure("PROJECT_NOT_CONFIGURED") from error
    testing = getattr(model, "testing", None)
    if getattr(model, "schema_version", None) != 3 or testing is None:
        raise _WorkflowFailure("PROJECT_TESTING_NOT_CONFIGURED")
    if require_host and getattr(testing, "host", None) is None:
        raise _WorkflowFailure("PROJECT_TESTING_NOT_CONFIGURED")
    try:
        workspace = WorkspacePaths.from_roots(
            context.data_root,
            context.project_root,
            model.logical_project_id,
            context.session_id,
        )
        workspace.ensure()
    except (OSError, ValueError) as error:
        raise _WorkflowFailure("PROJECT_NOT_CONFIGURED") from error
    return model, workspace


def _make_state(
    context: TestingWorkflowContext,
    *,
    with_identity: bool,
    require_host: bool = True,
) -> _WorkflowState:
    model, workspace = _configured_workspace(context, require_host=require_host)
    identity: EvidenceIdentityContext | None = None
    if with_identity:
        snapshot: InputSnapshot = _snapshot_project_inputs(model)
        git: GitEvidence = _git_evidence(context.project_root)
        identity = EvidenceIdentityContext(
            workspace_id=workspace.workspace_id,
            project_id=str(model.logical_project_id),
            session_id=workspace.session_id,
            target_device=host_target_device(),
            input_snapshot_sha256=snapshot.sha256,
            git_commit=git.head,
            git_dirty=git.dirty,
        )
    evidence_store = _evidence_store_factory(workspace.workspace_root / "evidence")
    return _WorkflowState(
        model=model,
        host_config=getattr(model.testing, "host", None),
        workspace=workspace,
        identity=identity,
        evidence_store=evidence_store,
        results_root=workspace.session_root / "test-results",
    )


def _runner(state: _WorkflowState) -> object:
    return _host_runner_factory(
        project_root=state.workspace.project_root,
        evidence_store=state.evidence_store,
        results_root=state.results_root,
    )


def host_test_discover(context: TestingWorkflowContext) -> OperationResult[dict[str, object]]:
    """Discover Host tests and return the complete inventory plus its artifact."""
    try:
        state = _make_state(context, with_identity=True)
        runner = _runner(state)
        if state.identity is None:
            raise _WorkflowFailure("PROJECT_NOT_CONFIGURED")
        inventory = runner.discover(state.host_config, state.identity)
        artifact = getattr(runner, "discovery_artifact", None)
        if artifact is None:
            raise TestProtocolError("TEST_PROTOCOL_INVALID", "Host discovery artifact is missing")
        return OperationResult.success(
            _DISCOVER_OPERATION,
            {
                "inventory": inventory.to_dict(),
                "discovery_artifact": artifact.to_dict(),
            },
        )
    except Exception as error:
        return _exception_result(_DISCOVER_OPERATION, error)


def _valid_digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _valid_portable_probe_id(value: object) -> bool:
    return isinstance(value, str) and _PORTABLE_PROBE_ID.fullmatch(value) is not None


def _valid_case_ids(case_ids: object) -> bool:
    return (
        isinstance(case_ids, tuple)
        and all(isinstance(case_id, str) and bool(case_id) for case_id in case_ids)
        and len(case_ids) == len(set(case_ids))
    )


def _valid_physical_case_ids(case_ids: object) -> bool:
    if not _valid_case_ids(case_ids) or not case_ids or len(case_ids) > 4096:
        return False
    try:
        canonical = tuple(sorted(case_ids, key=lambda case_id: case_id.encode("utf-8")))
    except UnicodeEncodeError:
        return False
    return case_ids == canonical


@dataclass(frozen=True)
class TargetWorkflowSeams:
    """One private seam replacing only the physical backend in tests."""

    _test_backend_factory: Callable[[], object] | None = None


def _target_project_config(target: object) -> tuple[str, dict[str, object]]:
    configured = getattr(target, "transport", None)
    kind = getattr(configured, "kind", None)
    options = getattr(configured, "options", None)
    transport = {
        "memory-mailbox": "mailbox", "rtt": "rtt", "uart": "uart",
        "semihosting": "semihosting",
    }.get(kind)
    if transport == "mailbox":
        value = {"kind": kind, "options": {"address": options.address, "size": options.size}}
    elif transport == "rtt":
        members = {"channel": options.channel}
        if options.control_block_address is not None:
            members["controlBlockAddress"] = options.control_block_address
        value = {"kind": kind, "options": members}
    elif transport == "uart":
        value = {"kind": kind, "options": {"port": options.port, "baud": options.baud}}
    elif transport == "semihosting":
        value = {"kind": kind, "options": {}}
    else:
        raise TestProtocolError("TEST_PROTOCOL_INVALID", "Target transport is invalid")
    return transport, value


def _target_protocol(target: object) -> str:
    protocol = getattr(target, "protocol", TARGET_FRAME_V1)
    if protocol not in {TARGET_FRAME_V1, TARGET_FRAME_V2}:
        raise TestProtocolError("TEST_FRAME_VERSION_INVALID", "Target frame protocol is unsupported")
    return protocol


def _target_support_profile(model: object, facts: object, project: Mapping[str, object]) -> dict[str, object]:
    target = getattr(getattr(model, "testing", None), "target", None)
    transport, _ = _target_project_config(target)
    ram = sorted(
        (
            {"start": region.origin, "size": region.length}
            for region in model.memory.regions
            if "w" in region.attributes.casefold()
        ),
        key=lambda region: (region["start"], region["size"]),
    )
    profile: dict[str, object] = {
        "backend": "pyocd",
        "board_id": facts.target_device,
        "mcu": model.debug.target,
        "target_id": facts.target_device,
        "ram": ram,
    }
    options = dict(project["options"])
    if transport == "mailbox":
        profile["mailbox"] = options
    elif transport == "rtt":
        profile["rtt"] = {
            "channel": options["channel"],
            **({"control_block_address": options["controlBlockAddress"]} if "controlBlockAddress" in options else {}),
        }
    elif transport == "uart":
        profile["uart"] = options
    else:
        profile["semihosting"] = {"declared": True}
        profile["semihosting_runtime"] = {
            "elf_path": facts.elf_path,
            "elf_sha256": facts.elf_sha256,
        }
    return profile


def _target_state(context: TestingWorkflowContext) -> tuple[
    _WorkflowState, object, object, str, str, dict[str, object], dict[str, object]
]:
    state = _make_state(context, with_identity=False, require_host=False)
    facts = load_fresh_firmware_facts(context.project_root)
    target = getattr(getattr(facts.model, "testing", None), "target", None)
    if target is None:
        raise _WorkflowFailure("PROJECT_TESTING_NOT_CONFIGURED")
    transport, project_config = _target_project_config(target)
    protocol = _target_protocol(target)
    support = _target_support_profile(facts.model, facts, project_config)
    return state, facts.model, facts, transport, protocol, project_config, support


def _target_supervisor(
    context: TestingWorkflowContext,
    state: _WorkflowState,
    *, probe_id: str,
    level: OperationLevel,
    support: Mapping[str, object],
    seams: TargetWorkflowSeams,
    worker_config: ProbeWorkerConfig | None = None,
) -> ProbeServiceSupervisor:
    collector = TestArtifactCollector(
        state.results_root, state.evidence_store, project_root=state.workspace.project_root
    )
    config = ProbeServiceConfig(
        probe_id, state.workspace.workspace_id, state.workspace.session_id, level,
        state.workspace.session_root, context.project_root,
        artifact_collector=collector,
    )
    manager = ProbeLeaseManager(context.data_root)
    if seams._test_backend_factory is not None:
        return ProbeServiceSupervisor(
            config=config, lease_manager=manager,
            backend_factory=seams._test_backend_factory,
        )
    worker = worker_config or ProbeWorkerConfig(
        target_profile={**dict(support), "probe_id": probe_id}
    )
    return ProbeServiceSupervisor(config=config, lease_manager=manager, worker_config=worker)


async def target_test_prepare(
    context: TestingWorkflowContext,
    *,
    probe_id: str,
    case_ids: tuple[str, ...],
    recovery_under_reset: object = False,
    _seams: TargetWorkflowSeams = TargetWorkflowSeams(),
) -> OperationResult[dict[str, object]]:
    """Authorize exact fixed-after firmware facts without reading Target inventory."""
    supervisor: ProbeServiceSupervisor | None = None
    client: ProbeClient | None = None
    try:
        if (
            not isinstance(probe_id, str)
            or not probe_id
            or not _valid_physical_case_ids(case_ids)
            or type(recovery_under_reset) is not bool
        ):
            raise TestProtocolError("TEST_PROTOCOL_INVALID", "Physical Target request is invalid")
        if recovery_under_reset and not _valid_portable_probe_id(probe_id):
            raise TestProtocolError("TEST_PROTOCOL_INVALID", "Physical Target request is invalid")
        state, model, facts, transport, protocol, project_config, support = _target_state(context)
        probe_hash = sha256(probe_id.encode("utf-8")).hexdigest()
        expected_identity = EvidenceIdentity(
            state.workspace.workspace_id, str(model.logical_project_id),
            state.workspace.session_id, facts.build_id, facts.elf_sha256,
            facts.target_device, facts.input_snapshot_sha256, facts.git_commit,
            facts.git_dirty,
        )
        inventory_digest = calculate_inventory_digest("target", expected_identity, case_ids)
        case_inventory_digest = calculate_case_inventory_digest(case_ids)
        expected_target = {
            "board_id": facts.target_device, "mcu": str(model.debug.target),
            "target_id": facts.target_device, "probe_serial_hash": probe_hash,
        }
        if not recovery_under_reset:
            supervisor = _target_supervisor(
                context,
                state,
                probe_id=probe_id,
                level=OperationLevel.OBSERVE,
                support=support,
                seams=_seams,
            )
            endpoint = await supervisor.start()
            client = ProbeClient(endpoint)
            await client.attach(probe_id, str(model.debug.target))
            physical = await client.target_identity()
            if physical != expected_target:
                raise TargetRunError("TEST_IDENTITY_MISMATCH", "Physical Target identity changed")
        current_facts = load_fresh_firmware_facts(context.project_root)
        if (
            current_facts.build_id != facts.build_id
            or current_facts.elf_sha256 != facts.elf_sha256
            or current_facts.input_snapshot_sha256 != facts.input_snapshot_sha256
            or current_facts.git_commit != facts.git_commit
            or current_facts.git_dirty != facts.git_dirty
            or current_facts.target_device != facts.target_device
        ):
            raise TargetRunError("TEST_INVENTORY_CHANGED", "Physical Target inputs changed")
        runner = TargetTestRunner(
            state.workspace.session_root / "target-authorizations", client,
            object(), lambda _: object(), owns_probe=False,
        )
        binding = dict(
            workspace_id=state.workspace.workspace_id,
            project_id=str(model.logical_project_id),
            session_id=state.workspace.session_id,
            revision=facts.git_commit,
            input_snapshot_sha256=facts.input_snapshot_sha256,
            target=expected_target,
            probe_serial_hash=probe_hash,
            elf_path=facts.elf_path,
            elf_sha256=facts.elf_sha256,
            build_id=facts.build_id,
            inventory_digest=inventory_digest,
            transport=transport,
            transport_config=project_config,
            support_profile=support,
            cases=case_ids,
            timeout_ms=int(getattr(getattr(model.testing, "target"), "timeout_seconds")) * 1000,
            recovery_under_reset=recovery_under_reset,
        )
        if protocol == TARGET_FRAME_V2:
            binding.update(
                protocol=protocol,
                case_inventory_digest=case_inventory_digest,
                git_dirty=facts.git_dirty,
            )
        prepared = await runner.prepare(**binding)
        result = {
            "authorized_action_digest": prepared.action_digest,
            "expires_at_utc": prepared.expires_at_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "inventory_digest": inventory_digest,
            "case_ids": list(case_ids),
            "probe_serial_hash": probe_hash,
        }
        if protocol == TARGET_FRAME_V2:
            result.update({"protocol": protocol, "case_inventory_digest": case_inventory_digest})
        return OperationResult.success(_TARGET_PREPARE_OPERATION, result)
    except Exception as error:
        return _exception_result(_TARGET_PREPARE_OPERATION, error)
    finally:
        if client is not None:
            await client.close()
        if supervisor is not None:
            await supervisor.stop()


async def target_test_execute(
    context: TestingWorkflowContext,
    *,
    probe_id: str,
    authorized_action_digest: str,
    _seams: TargetWorkflowSeams = TargetWorkflowSeams(),
) -> OperationResult[dict[str, object]]:
    """Consume one intent, flash, validate fixed-after inventory, and publish."""
    supervisor: ProbeServiceSupervisor | None = None
    client: ProbeClient | None = None
    try:
        if not isinstance(probe_id, str) or not probe_id or not _valid_digest(authorized_action_digest):
            raise TargetRunError("TEST_AUTHORIZATION_INVALID", "Target authorization is invalid")
        state = _make_state(context, with_identity=False, require_host=False)
        auth_runner = TargetTestRunner(
            state.workspace.session_root / "target-authorizations", object(),
            object(), lambda _: object(), owns_probe=False,
        )
        loaded = auth_runner.load_prepared(authorized_action_digest)
        consumed = auth_runner.consume_prepared(authorized_action_digest)
        binding = consumed.binding
        if type(binding.get("recovery_under_reset")) is not bool:
            raise TargetRunError("TEST_AUTHORIZATION_INVALID", "Target recovery profile is invalid")
        if datetime.now(timezone.utc) >= loaded.expires_at_utc:
            raise TargetRunError("TEST_AUTHORIZATION_INVALID", "Target authorization expired")
        state, model, facts, transport, protocol, project_config, support = _target_state(context)
        probe_hash = sha256(probe_id.encode("utf-8")).hexdigest()
        expected_identity = EvidenceIdentity(
            state.workspace.workspace_id, str(model.logical_project_id),
            state.workspace.session_id, facts.build_id, facts.elf_sha256,
            facts.target_device, facts.input_snapshot_sha256, facts.git_commit,
            facts.git_dirty,
        )
        expected_inventory_digest = calculate_inventory_digest(
            "target", expected_identity, tuple(binding["cases"])
        )
        expected_case_inventory_digest = calculate_case_inventory_digest(tuple(binding["cases"]))
        if binding["probe_serial_hash"] != probe_hash:
            raise TargetRunError("TEST_IDENTITY_MISMATCH", "Physical probe identity changed")
        if (
            binding["workspace_id"] != state.workspace.workspace_id
            or binding["project_id"] != str(model.logical_project_id)
            or binding["session_id"] != state.workspace.session_id
            or binding["revision"] != facts.git_commit
            or binding["input_snapshot_sha256"] != facts.input_snapshot_sha256
            or binding["build_id"] != facts.build_id
            or binding["elf_sha256"] != facts.elf_sha256
            or binding["elf_path"] != facts.elf_path
            or binding["transport"] != transport
            or binding["transport_config"] != project_config
            or binding["support_profile"] != support
            or binding["inventory_digest"] != expected_inventory_digest
            or type(binding.get("recovery_under_reset")) is not bool
            or binding.get("protocol", TARGET_FRAME_V1) != protocol
            or (
                protocol == TARGET_FRAME_V2
                and (
                    binding.get("case_inventory_digest") != expected_case_inventory_digest
                    or binding.get("git_dirty") != facts.git_dirty
                )
            )
        ):
            raise TargetRunError("TEST_INVENTORY_CHANGED", "Physical Target inputs changed")
        normal_worker = ProbeWorkerConfig(
            target_profile={**dict(support), "probe_id": probe_id}
        )
        worker_config = (
            normal_worker.for_under_reset_recovery()
            if binding["recovery_under_reset"]
            else normal_worker
        )
        supervisor = _target_supervisor(
            context, state, probe_id=probe_id, level=OperationLevel.MODIFY,
            support=support, seams=_seams, worker_config=worker_config,
        )
        endpoint = await supervisor.start()
        client = ProbeClient(endpoint)
        await client.attach(probe_id, str(model.debug.target))
        if await client.target_identity() != binding["target"]:
            raise TargetRunError("TEST_IDENTITY_MISMATCH", "Physical Target identity changed")
        collector = TestArtifactCollector(
            state.results_root, state.evidence_store, project_root=state.workspace.project_root
        )
        runner = TargetTestRunner(
            state.workspace.session_root / "target-authorizations", client,
            PhysicalTargetFlashAdapter(
                project_root=context.project_root, raw_probe_id=probe_id, client=client
            ),
            lambda name: ProbeClientTargetTransport(client, project_config, name),
            artifact_collector=collector, owns_probe=False,
        )
        physical_consumed = ConsumedTargetRun(
            consumed.action_digest,
            consumed.binding,
            PhysicalRunProvenance(
                state.workspace.workspace_id, state.workspace.session_id, probe_hash,
                state.workspace.session_id, endpoint.lease_id,
            ),
        )
        result = await runner.run(
            None, authorized_action_digest,
            current_revision=facts.git_commit,
            current_inventory_digest=str(binding["inventory_digest"]),
            current_input_snapshot_sha256=facts.input_snapshot_sha256,
            consumed=physical_consumed,
        )
        manifest = result["test_manifest"]
        run_envelope = result["evidence"]
        publisher = _publisher_factory(
            state.evidence_store, state.workspace.project_root, state.results_root
        )
        published = publisher.publish_target_physical(manifest, run_envelope)
        return OperationResult.success(_TARGET_EXECUTE_OPERATION, published.public_data())
    except Exception as error:
        return _exception_result(_TARGET_EXECUTE_OPERATION, error)
    finally:
        if client is not None:
            await client.close()
        if supervisor is not None:
            await supervisor.stop()


def host_test_run(
    context: TestingWorkflowContext,
    *,
    inventory_digest: str,
    case_ids: tuple[str, ...],
) -> OperationResult[dict[str, object]]:
    """Freshly discover, bind the supplied inventory digest, run, and publish."""
    try:
        if not _valid_digest(inventory_digest):
            raise TestProtocolError("TEST_PROTOCOL_INVALID", "inventory digest is invalid")
        if not _valid_case_ids(case_ids):
            raise TestProtocolError("TEST_CASE_NOT_FOUND", "requested case IDs are invalid")
        state = _make_state(context, with_identity=True)
        runner = _runner(state)
        if state.identity is None:
            raise _WorkflowFailure("PROJECT_NOT_CONFIGURED")
        inventory = runner.discover(state.host_config, state.identity)
        if inventory.inventory_digest != inventory_digest:
            raise TestProtocolError("TEST_INVENTORY_CHANGED", "inventory digest changed")
        requested = inventory.case_ids if not case_ids else case_ids
        if any(case_id not in inventory.case_ids for case_id in requested):
            raise TestProtocolError("TEST_CASE_NOT_FOUND", "requested test case was not discovered")
        manifest = runner.run(inventory, case_ids)
        publisher = _publisher_factory(
            state.evidence_store,
            state.workspace.project_root,
            state.results_root,
        )
        published = publisher.publish_host(
            manifest,
            inventory_digest=inventory_digest,
        )
        return OperationResult.success(_RUN_OPERATION, published.public_data())
    except Exception as error:
        return _exception_result(_RUN_OPERATION, error)


def _target_replay_frames(
    fixture: object,
    operation_id: str,
) -> tuple[object, ...]:
    descriptor = getattr(fixture, "descriptor", None)
    stream_bytes = getattr(fixture, "stream_bytes", None)
    if not isinstance(descriptor, TargetReplayDescriptor) or not isinstance(stream_bytes, bytes):
        raise TestProtocolError("TEST_REPLAY_INVALID", "Target replay fixture is invalid")
    decoder = TargetFrameDecoder(max_stream_bytes=descriptor.stream.size_bytes)
    frames = decoder.feed(stream_bytes)
    decoder.finish()
    validator = TargetRunValidator(
        TargetRunBinding(
            descriptor.inventory_digest,
            descriptor.identity.build_id,
            descriptor.identity.elf_sha256,
            descriptor.identity.target_device,
        )
    )
    for frame in frames:
        validator.accept(frame)
    validator.finish()
    if not frames or frames[0].kind != 1 or frames[-1].kind != 5:
        raise TestProtocolError("TEST_REPLAY_INTEGRITY", "Target replay stream has no complete run")
    inventory = frames[0].payload
    if (
        inventory.get("mode") != "target"
        or inventory.get("identity") != descriptor.identity.to_dict()
        or inventory.get("inventory_digest") != descriptor.inventory_digest
    ):
        raise TestProtocolError(
            "TEST_REPLAY_INTEGRITY",
            "Target replay inventory identity contradicts its descriptor",
        )
    run_start = next((frame for frame in frames if frame.kind == 2), None)
    terminal = frames[-1]
    if run_start is None or run_start.payload.get("run_id") != operation_id:
        raise TestProtocolError(
            "TEST_REPLAY_INVALID",
            "operation_id must exactly match the frozen Target run ID",
        )
    if terminal.payload.get("state") != descriptor.expected_terminal_state:
        raise TestProtocolError(
            "TEST_REPLAY_INTEGRITY",
            "Target replay terminal state contradicts its descriptor",
        )
    return frames


def target_replay_run(
    context: TestingWorkflowContext,
    operation_id: str,
    descriptor_file: Path | str,
    stream_file: Path | str,
) -> OperationResult[dict[str, object]]:
    """Validate, execute, and durably publish one frozen Target replay."""
    try:
        if not isinstance(operation_id, str) or _RUN_ID.fullmatch(operation_id) is None:
            raise TestProtocolError("TEST_REPLAY_INVALID", "operation_id is invalid")
        state = _make_state(context, with_identity=False, require_host=False)
        fixture = load_target_replay_fixture(descriptor_file, stream_file)
        frames = _target_replay_frames(fixture, operation_id)
        descriptor = fixture.descriptor
        try:
            source_bytes = EvidenceStore._read_file_bytes(
                Path(descriptor_file), maximum_bytes=MAX_REPLAY_DESCRIPTOR_BYTES
            )
        except EvidenceValidationError:
            raise
        except (OSError, TypeError, ValueError) as error:
            raise TestProtocolError(
                "TEST_REPLAY_FIXTURE_INVALID",
                "descriptor could not be read for immutable publication",
            ) from error
        canonical_descriptor = canonical_replay_json_bytes(descriptor.to_dict())
        if source_bytes not in {canonical_descriptor, canonical_descriptor + b"\n"}:
            raise TestProtocolError(
                "TEST_REPLAY_INTEGRITY",
                "descriptor bytes changed between validation and publication",
            )

        collector = TestArtifactCollector(
            state.results_root,
            state.evidence_store,
            project_root=state.workspace.project_root,
        )
        input_directory = collector.new_directory("target-replay-input")
        descriptor_artifact = collector.write_and_ingest(
            input_directory,
            "descriptor.json",
            source_bytes,
            kind="target-replay-descriptor",
            media_type="application/json",
        )
        stream_artifact = collector.write_and_ingest(
            input_directory,
            "decoded-stream.bin",
            fixture.stream_bytes,
            kind="target-replay-stream",
            media_type="application/octet-stream",
        )
        inventory = frames[0].payload
        descriptor_parent = EvidenceEnvelope(
            identity=descriptor.identity,
            operation="target-replay-input",
            produced_at_utc=str(inventory["discovered_at_utc"]),
            parents=(),
            artifacts=(descriptor_artifact, stream_artifact),
            metadata={
                "replay_id": descriptor.replay_id,
                "scenario_role": descriptor.scenario_role,
                "stream_sha256": descriptor.stream.sha256,
                "stream_size_bytes": descriptor.stream.size_bytes,
                "execution_source": "replay",
                "physical_transport_evidence": False,
                "origin_workspace_id": descriptor.identity.workspace_id,
                "import_workspace_id": state.workspace.workspace_id,
            },
        )
        state.evidence_store.put_envelope(descriptor_parent)

        case_starts = {
            str(frame.payload["case_id"]): frame.payload
            for frame in frames
            if frame.kind == 3
        }
        cases = tuple(
            TestCaseResult(
                str(frame.payload["case_id"]),
                str(frame.payload["state"]),
                str(case_starts[str(frame.payload["case_id"])].get("started_at_utc")),
                str(frame.payload["ended_at_utc"]),
                int(frame.payload["duration_ms"]),
                frame.payload["message"],
                None,
                None,
            )
            for frame in frames
            if frame.kind == 4
        )
        output_directory = collector.new_directory("test-events")
        raw_artifact = collector.write_and_ingest(
            output_directory,
            "target-events.bin",
            fixture.stream_bytes,
            kind="test-events",
            media_type="application/vnd.stm32.target-events",
        )
        run_start = next(frame for frame in frames if frame.kind == 2)
        terminal = frames[-1]
        manifest = TestRunManifest(
            "stm32-test/1",
            operation_id,
            "target",
            str(terminal.payload["state"]),
            descriptor.identity,
            "replay",
            cases,
            str(run_start.payload["started_at_utc"]),
            str(terminal.payload["ended_at_utc"]),
            int(terminal.payload["duration_ms"]),
            None,
            None,
            raw_artifact,
        )
        publisher = _publisher_factory(
            state.evidence_store,
            state.workspace.project_root,
            state.results_root,
        )
        published = publisher.publish_target_replay(
            manifest,
            descriptor_parent,
            state.workspace.workspace_id,
        )
        return OperationResult.success(_REPLAY_OPERATION, published.public_data())
    except Exception as error:
        return _exception_result(_REPLAY_OPERATION, error)


def test_show(
    context: TestingWorkflowContext,
    *,
    run_id: str,
) -> OperationResult[dict[str, object]]:
    """Reload exactly one authoritative Host run through the repository."""
    try:
        state = _make_state(context, with_identity=False, require_host=False)
        repository = _repository_factory(state.evidence_store)
        published = repository.load(run_id)
        return OperationResult.success(_SHOW_OPERATION, published.public_data(authoritative=True))
    except Exception as error:
        return _exception_result(_SHOW_OPERATION, error)


__all__ = [
    "TestingWorkflowContext",
    "TargetWorkflowSeams",
    "host_test_discover",
    "host_test_run",
    "target_test_prepare",
    "target_test_execute",
    "target_replay_run",
    "test_show",
]
