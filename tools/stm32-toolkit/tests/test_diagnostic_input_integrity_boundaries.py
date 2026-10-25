"""Public workflow context and generated-identifier integrity boundaries."""

from __future__ import annotations

from pathlib import Path

import pytest

import stm32_toolkit.diagnostic_workflows as workflow_module
from stm32_toolkit.diagnostic_workflows import (
    DiagnosticWorkflowContext,
    diagnostic_begin,
    diagnostic_show,
    diagnostic_start,
)
from stm32_toolkit.diagnostics import (
    DIAGNOSTIC_IDENTITY_MISMATCH,
    DIAGNOSTIC_INVALID_EVENT,
)

from test_diagnostic_store import _authority_snapshot
from test_diagnostic_workflows import _fresh_context, _make_run


SID = "f" * 32


def _authority(workspace: object) -> dict[str, dict[str, bytes]]:
    return _authority_snapshot(
        workspace.diagnostics_root,  # type: ignore[attr-defined]
        workspace.workspace_root / "evidence",  # type: ignore[attr-defined]
    )


def test_wrong_context_type_is_refused_before_filesystem_work(tmp_path: Path) -> None:
    _context, _published, workspace = _make_run(tmp_path)
    before = _authority(workspace)

    result = diagnostic_show(object(), diagnostic_session_id=SID)  # type: ignore[arg-type]

    assert result.ok is False
    assert result.code == DIAGNOSTIC_IDENTITY_MISMATCH
    assert result.details == {}
    assert _authority(workspace) == before


def test_non_string_context_session_is_refused_before_filesystem_work(
    tmp_path: Path,
) -> None:
    context, _published, workspace = _make_run(tmp_path)
    malformed = DiagnosticWorkflowContext(
        Path(context.project_root),
        Path(context.data_root),
        123,  # type: ignore[arg-type]
    )
    before = _authority(workspace)

    result = diagnostic_show(malformed, diagnostic_session_id=SID)

    assert result.ok is False
    assert result.code == DIAGNOSTIC_IDENTITY_MISMATCH
    assert result.details == {}
    assert _authority(workspace) == before


def _investigating_session(context: DiagnosticWorkflowContext, published: object) -> str:
    started = diagnostic_start(
        _fresh_context(context),
        operation_id="producer-start",
        failed_test_run_id=published.manifest.run_id,  # type: ignore[attr-defined]
    )
    assert started.ok is True
    diagnostic_session_id = started.to_dict()["data"]["session"][
        "diagnostic_session_id"
    ]
    begun = diagnostic_begin(
        _fresh_context(context),
        operation_id="producer-begin",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=1,
    )
    assert begun.ok is True
    return diagnostic_session_id


@pytest.mark.parametrize(
    ("seam", "value"),
    [
        ("_session_id_factory", None),
        ("_session_id_factory", "not-a-diagnostic-session"),
        ("_utc_now", 123),
        ("_utc_now", "not-a-timestamp"),
        ("_hypothesis_id_factory", None),
        ("_hypothesis_id_factory", "not-a-hypothesis-id"),
    ],
    ids=[
        "session-id-wrong-type",
        "session-id-malformed",
        "timestamp-wrong-type",
        "timestamp-malformed",
        "hypothesis-id-wrong-type",
        "hypothesis-id-malformed",
    ],
)
def test_invalid_producer_output_is_refused_without_publishing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    seam: str,
    value: object,
) -> None:
    context, published, workspace = _make_run(tmp_path)
    hypothesis_session_id: str | None = None
    if seam == "_hypothesis_id_factory":
        hypothesis_session_id = _investigating_session(context, published)

    monkeypatch.setattr(workflow_module, seam, lambda: value)
    before = _authority(workspace)

    if hypothesis_session_id is not None:
        result = workflow_module.diagnostic_add_hypothesis(
            _fresh_context(context),
            operation_id="producer-hypothesis-seam",
            diagnostic_session_id=hypothesis_session_id,
            expected_revision=2,
            statement="producer output must be validated",
        )
    else:
        result = diagnostic_start(
            _fresh_context(context),
            operation_id="producer-start-seam",
            failed_test_run_id=published.manifest.run_id,  # type: ignore[attr-defined]
        )

    assert result.ok is False
    assert result.code == DIAGNOSTIC_INVALID_EVENT
    assert result.details == {}
    assert _authority(workspace) == before
