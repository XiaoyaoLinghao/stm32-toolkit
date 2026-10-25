"""Narrow CLI adapter for generated VS Code tasks (VSCODE-TASKS).

Generated tasks invoke exactly one of ``ide task flash``,
``ide task handoff-begin`` or ``ide task handoff-end``.  This adapter is not a
replacement for any MCP tool: it validates the explicit context and
confirmation, obtains firmware pins from the existing read-only
``_load_fresh_firmware`` admission (flash/handoff-begin only), and forwards the
exact request to the accepted hardware workflows, which keep their own checks.
Handoff-end therefore adds no admission, but the accepted end workflow still
revalidates current firmware/flash evidence around reacquisition; the adapter
surfaces that exact refusal rather than promising reclamation.

Nothing is stored here: no authorization, probe enumeration, session record or
handoff ticket.  ``--confirmation`` defaults to ``deny`` and an ``authorize``
value covers one invocation only.  A UI prompt cannot grant authority to an AI
caller.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

from stm32_toolkit.hardware_workflows import (
    FlashWorkflowRequest,
    HandoffBeginWorkflowRequest,
    HandoffEndWorkflowRequest,
    _WorkflowFailure,
    _safe_external_data_root,
    flash_workflow,
    handoff_begin_workflow,
    handoff_end_workflow,
)
from stm32_toolkit.paths import require_safe_session_id
from stm32_toolkit.probe.flash import _FlashFailure, _load_fresh_firmware
from stm32_toolkit.result import OperationResult

CONFIRMATION_DENY = "deny"
CONFIRMATION_AUTHORIZE = "authorize"
_CONFIRMATIONS = frozenset({CONFIRMATION_DENY, CONFIRMATION_AUTHORIZE})

_TASK_OPERATIONS = {
    "flash": "stm32_flash",
    "handoff-begin": "stm32_debug_handoff_begin",
    "handoff-end": "stm32_debug_handoff_end",
}
_TASK_LABELS = {
    "flash": "Flash Debug",
    "handoff-begin": "Handoff Begin Debug",
    "handoff-end": "Handoff End Debug",
}

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")

#: Patchable seams for synthetic tests.  Production calls these exact accepted
#: entry points; tests replace them (or pass explicit overrides) without any
#: probe, lease or backend effect.
_FRESH_FIRMWARE: Callable[[Path], object] = _load_fresh_firmware
_FLASH: Callable[[object], Awaitable[OperationResult[object]]] = flash_workflow
_HANDOFF_BEGIN: Callable[[object], Awaitable[OperationResult[object]]] = (
    handoff_begin_workflow
)
_HANDOFF_END: Callable[[object], Awaitable[OperationResult[object]]] = (
    handoff_end_workflow
)


def _failure(
    operation: str, field: str, rule: str, guidance: str
) -> OperationResult[object]:
    return OperationResult.failure(
        operation,
        "HARDWARE_INPUT_INVALID",
        "Hardware workflow input is invalid",
        {"field": field, "rule": rule, "guidance": guidance},
    )


def _resolve_project_root(value: object, operation: str) -> Path | OperationResult[object]:
    if not isinstance(value, Path):
        return _failure(
            operation,
            "project_root",
            "type",
            "Pass the generated task's absolute project root; do not construct "
            "an ad-hoc request.",
        )
    if not value.is_absolute():
        return _failure(
            operation,
            "project_root",
            "absolute",
            "The generated task binds an absolute project root; a relative "
            "path never selects the project implicitly.",
        )
    try:
        root = value.expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return _failure(
            operation,
            "project_root",
            "directory",
            "Use an existing, readable, non-redirected project root.",
        )
    if not root.is_dir():
        return _failure(
            operation,
            "project_root",
            "directory",
            "Use an existing, readable, non-redirected project root.",
        )
    return root


def _resolve_data_root(
    value: object, project_root: Path, operation: str
) -> Path | OperationResult[object]:
    """Preserve the accepted lexical data-root contract.

    ``_safe_external_data_root`` is the existing hardware validator: it walks
    every lexical component without following redirects and refuses a root
    inside the project.  The adapter only adds the explicit absolute
    requirement so a relative value is never resolved against the process cwd.
    Its structured diagnostic is forwarded unchanged.
    """
    if not isinstance(value, Path):
        return _failure(
            operation,
            "data_root",
            "type",
            "Pass the machine-owned Toolkit data root as a path outside the "
            "project root.",
        )
    if not value.is_absolute():
        return _failure(
            operation,
            "data_root",
            "absolute",
            "The generated task binds an absolute data root outside the "
            "project; a relative path is never resolved against the project.",
        )
    try:
        return _safe_external_data_root(value, project_root)
    except _WorkflowFailure as error:
        return OperationResult.failure(
            operation, error.code, error.message, error.details
        )


def _safe_ticket(ticket: object) -> bool:
    return isinstance(ticket, str) and _DIGEST.fullmatch(ticket) is not None


async def run_ide_task(
    task: object,
    *,
    project_root: object,
    data_root: object,
    session_id: object,
    probe_id: object,
    confirmation: object = CONFIRMATION_DENY,
    ticket: object = None,
    fresh_firmware: Callable[[Path], object] | None = None,
    flash: Callable[[object], Awaitable[OperationResult[object]]] | None = None,
    handoff_begin: Callable[[object], Awaitable[OperationResult[object]]] | None = None,
    handoff_end: Callable[[object], Awaitable[OperationResult[object]]] | None = None,
) -> OperationResult[object]:
    """Run one generated-task invocation and return the forwarded result.

    ``confirmation`` is checked first: anything other than the exact string
    ``authorize`` (including the default ``deny``) returns
    ``AUTHORIZATION_REQUIRED`` before the project model, firmware evidence or
    any hardware workflow is touched.  Flash and handoff-begin then use the
    existing fresh-firmware admission and forward its exact build ID/ELF
    SHA-256 plus the bound roots, session and probe.

    Handoff-end adds no adapter-side admission and forwards the original
    ticket unchanged.  That is delegation, not proof of reclamation: the
    accepted end workflow itself revalidates the current firmware and flash
    evidence before and after reacquisition, so stale source, ELF or build
    evidence can still refuse with its own error.  This adapter reports that
    exact failure/ownership result and never rebuilds, flashes, retries or
    claims cleanup.
    """
    if type(task) is not str or task not in _TASK_OPERATIONS:
        return _failure(
            "ide-task",
            "task",
            "value",
            "Use exactly one generated task action: flash, handoff-begin or "
            "handoff-end.",
        )
    operation = _TASK_OPERATIONS[task]
    label = _TASK_LABELS[task]

    if type(confirmation) is not str or confirmation not in _CONFIRMATIONS:
        return _failure(
            operation,
            "confirmation",
            "value",
            "Pass exactly `deny` or `authorize`; the generated tasks default "
            "to deny and never infer authorization.",
        )
    if confirmation != CONFIRMATION_AUTHORIZE:
        return OperationResult.failure(
            operation,
            "AUTHORIZATION_REQUIRED",
            "Explicit authorization is required for this task invocation",
            {
                "field": "confirmation",
                "rule": "authorize",
                "operation": operation,
                "task": task,
                "guidance": (
                    f"This invocation would run {label} on the named probe. "
                    "Generated VS Code tasks default to deny. After obtaining "
                    "explicit user authorization for this exact probe, rerun "
                    "this one invocation with --confirmation authorize. Nothing "
                    "is stored and the next task run does not inherit it."
                ),
            },
        )

    root = _resolve_project_root(project_root, operation)
    if isinstance(root, OperationResult):
        return root
    data = _resolve_data_root(data_root, root, operation)
    if isinstance(data, OperationResult):
        return data
    try:
        session = require_safe_session_id(session_id)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return _failure(
            operation,
            "session_id",
            "format",
            "Use a filesystem-safe session id: lowercase letters, digits, '-' "
            "or '_', starting with a letter or digit.",
        )
    if not isinstance(probe_id, str) or _IDENTIFIER.fullmatch(probe_id) is None:
        return _failure(
            operation,
            "probe_id",
            "identifier",
            "Use the exact probeId returned by stm32_probe_list; never "
            "construct, hash or guess a selector.",
        )
    if task == "handoff-end" and not _safe_ticket(ticket):
        return _failure(
            operation,
            "ticket",
            "digest",
            "Pass the original 64-character lowercase handoff ticket returned "
            "by the successful handoff-begin; tickets are never persisted for "
            "you.",
        )

    if task == "handoff-end":
        request: object = HandoffEndWorkflowRequest(
            root, data, session, probe_id, ticket
        )
        workflow = _HANDOFF_END if handoff_end is None else handoff_end
    else:
        admit = _FRESH_FIRMWARE if fresh_firmware is None else fresh_firmware
        try:
            firmware = admit(root)
        except _FlashFailure as error:
            # Preserve the original admission code, message and details
            # (including snapshot provenance refusal and build/input/artifact
            # failures) exactly, before any workflow or probe.
            return OperationResult.failure(
                operation, error.code, error.message, error.details
            )
        identity = getattr(firmware, "identity", None)
        if not isinstance(identity, Mapping):
            return OperationResult.failure(
                operation,
                "FIRMWARE_EVIDENCE_INVALID",
                "Firmware evidence is invalid",
                {"field": "identity", "rule": "admission"},
            )
        build_id = identity.get("buildId")
        elf_sha256 = identity.get("elfSha256")
        if not _safe_ticket(build_id) or not _safe_ticket(elf_sha256):
            return OperationResult.failure(
                operation,
                "FIRMWARE_EVIDENCE_INVALID",
                "Firmware evidence is invalid",
                {"field": "identity", "rule": "admission"},
            )
        if task == "flash":
            request = FlashWorkflowRequest(
                root, data, session, probe_id, str(build_id), str(elf_sha256), True
            )
            workflow = _FLASH if flash is None else flash
        else:
            request = HandoffBeginWorkflowRequest(
                root, data, session, probe_id, str(build_id), str(elf_sha256), True
            )
            workflow = _HANDOFF_BEGIN if handoff_begin is None else handoff_begin

    result = await workflow(request)
    if not isinstance(result, OperationResult):
        return OperationResult.failure(
            operation,
            "HARDWARE_INTERNAL_ERROR",
            "Hardware workflow failed",
            {},
        )
    return result


__all__ = [
    "CONFIRMATION_AUTHORIZE",
    "CONFIRMATION_DENY",
    "run_ide_task",
]
