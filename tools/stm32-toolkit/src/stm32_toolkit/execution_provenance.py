"""Closed execution-source policy shared by integrated product records."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class ExecutionProvenance:
    execution_source: str
    physical_transport_evidence: bool
    origin_workspace_id: str
    import_workspace_id: str
    origin_session_id: str
    current_session_id: str
    hardware_labels: Mapping[str, str]


def validate_execution_provenance(
    *,
    execution_source: object,
    physical_transport_evidence: object,
    origin_workspace_id: object,
    import_workspace_id: object,
    origin_session_id: object,
    current_session_id: object,
    hardware_labels: Mapping[str, object] | None = None,
) -> ExecutionProvenance:
    values = (origin_workspace_id, import_workspace_id, origin_session_id, current_session_id)
    labels = {} if hardware_labels is None else dict(hardware_labels)
    if (
        execution_source not in {"physical", "replay"}
        or type(physical_transport_evidence) is not bool
        or any(not isinstance(value, str) or not value for value in values)
    ):
        raise ValueError("execution provenance is invalid")
    expected_labels = {"probe_id", "target_id", "flash_session_id", "lease_id"}
    if execution_source == "physical":
        if (
            not physical_transport_evidence
            or origin_workspace_id != import_workspace_id
            or origin_session_id != current_session_id
            or set(labels) != expected_labels
            or any(not isinstance(value, str) or not value or value == "replay" for value in labels.values())
        ):
            raise ValueError("physical provenance is incompatible")
    elif physical_transport_evidence or (
        hardware_labels is not None
        and (set(labels) != expected_labels or any(value != "replay" for value in labels.values()))
    ):
        raise ValueError("replay provenance is incompatible")
    return ExecutionProvenance(
        str(execution_source),
        physical_transport_evidence,
        str(origin_workspace_id),
        str(import_workspace_id),
        str(origin_session_id),
        str(current_session_id),
        MappingProxyType({str(key): str(value) for key, value in labels.items()}),
    )


__all__ = ["ExecutionProvenance", "validate_execution_provenance"]
