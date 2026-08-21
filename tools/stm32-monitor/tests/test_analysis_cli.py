from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

import stm32_monitor.cli as cli
from stm32_monitor.analysis import AnalysisRequest
from stm32_monitor.analysis_workflows import AnalysisPublication
from stm32_monitor.protocol import ProtocolResult
from stm32_toolkit.diagnostics import SourceChangeDeclaration
from stm32_toolkit.paths import WorkspacePaths


PROJECT_ID = UUID("123e4567-e89b-42d3-a456-426614174000")


class _Ref:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def to_dict(self) -> dict[str, object]:
        return dict(self.payload)


class _Publication:
    def to_dict(self) -> dict[str, object]:
        return {
            "analysis_result": {"analysis_id": "a" * 64},
            "analysis_evidence_ref": {"evidence_id": "b" * 64},
            "diagnostic_marker": {"marker_id": "c" * 64},
            "diagnostic_marker_ref": {"marker_evidence_id": "d" * 64},
        }


class _BundleRef:
    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "stm32-monitor-analysis-bundle-ref/1",
            "bundle_id": "e" * 64,
            "evidence_id": "f" * 64,
            "artifact": {
                "sha256": "e" * 64,
                "size_bytes": 2,
                "relative_path": "objects/sha256/ee/" + "e" * 64,
                "kind": "monitor-analysis-bundle",
                "media_type": "application/json",
            },
        }


def _project_and_model(monkeypatch: pytest.MonkeyPatch, project: Path) -> None:
    project.mkdir()
    monkeypatch.setattr(
        cli,
        "load_project_model",
        lambda root: SimpleNamespace(schema_version=3, logical_project_id=PROJECT_ID),
        raising=False,
    )


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def test_protocol_accepts_only_the_four_analysis_boundary_codes() -> None:
    for code in (
        "ANALYSIS_WORKFLOW_INVALID",
        "INCOMPATIBLE_IDENTITY",
        "EVIDENCE_INTEGRITY_FAILURE",
        "ENVIRONMENT_FAILURE",
    ):
        result = ProtocolResult(False, "monitor.analysis.compare", code, "bounded", None)
        assert result.to_dict()["code"] == code


def test_replay_ingest_binds_workspace_evidence_and_calls_workflow_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    data = tmp_path / "data"
    _project_and_model(monkeypatch, project)
    document = tmp_path / "document.json"
    document.write_text("{}", encoding="utf-8")
    calls: list[tuple[object, object, str, Path]] = []

    def ingest(paths: object, evidence: object, operation_id: str, document_file: Path):
        calls.append((paths, evidence, operation_id, document_file))
        return _Ref({"schema": "monitor-run-ref/1"})

    monkeypatch.setattr(cli, "ingest_monitor_replay", ingest, raising=False)
    output = io.StringIO()
    code = cli.main(
        [
            "replay",
            "ingest",
            "--project",
            str(project),
            "--data-root",
            str(data),
            "--session-id",
            "monitor-a",
            "--operation-id",
            "33333333-3333-4333-8333-333333333333",
            "--document-file",
            str(document),
            "--json",
        ],
        _stdout=output,
    )

    assert code == 0
    payload = json.loads(output.getvalue())
    assert payload["operation"] == "monitor.replay.ingest"
    assert payload["data"] == {"monitor_run_ref": {"schema": "monitor-run-ref/1"}}
    assert len(calls) == 1
    paths, evidence, operation_id, document_file = calls[0]
    expected = WorkspacePaths.from_roots(data, project, PROJECT_ID, "monitor-a")
    assert paths == expected
    assert evidence.root == expected.workspace_root / "evidence"
    assert operation_id == "33333333-3333-4333-8333-333333333333"
    assert document_file == document


def test_analysis_compare_projects_closed_inputs_and_calls_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    data = tmp_path / "data"
    _project_and_model(monkeypatch, project)
    request_file = tmp_path / "request.json"
    _write_json(request_file, {"request": "closed"})
    source_file = tmp_path / "source.json"
    _write_json(source_file, {"declaration": "closed"})
    request = object()
    declaration = object()
    monkeypatch.setattr(
        AnalysisRequest,
        "from_value",
        classmethod(lambda cls, value: request),
        raising=False,
    )
    monkeypatch.setattr(
        SourceChangeDeclaration,
        "from_value",
        classmethod(lambda cls, value: declaration),
        raising=False,
    )
    calls: list[tuple[object, ...]] = []

    def compare(*args: object):
        calls.append(args)
        return _Publication()

    monkeypatch.setattr(cli, "compare_monitor_runs", compare, raising=False)
    output = io.StringIO()
    code = cli.main(
        [
            "analysis",
            "compare",
            "--project",
            str(project),
            "--data-root",
            str(data),
            "--session-id",
            "monitor-a",
            "--request-file",
            str(request_file),
            "--diagnostic-session-id",
            "1" * 32,
            "--hypothesis-id",
            "2" * 32,
            "--polarity",
            "supports",
            "--rationale",
            "changed",
            "--source-change-file",
            str(source_file),
            "--json",
        ],
        _stdout=output,
    )

    assert code == 0
    payload = json.loads(output.getvalue())
    assert payload["operation"] == "monitor.analysis.compare"
    assert payload["data"] == {"analysis_publication": _Publication().to_dict()}
    assert len(calls) == 1
    args = calls[0]
    assert args[2:7] == (request, "1" * 32, "2" * 32, "supports", "changed")
    assert args[7] is declaration
    assert args[0].workspace_root / "evidence" == args[1].root


def test_analysis_bundle_consumes_publication_without_comparing_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    data = tmp_path / "data"
    _project_and_model(monkeypatch, project)
    request_file = tmp_path / "request.json"
    publication_file = tmp_path / "publication.json"
    _write_json(request_file, {"request": "closed"})
    _write_json(publication_file, {"publication": "closed"})
    request = object()
    publication = object()
    monkeypatch.setattr(
        AnalysisRequest,
        "from_value",
        classmethod(lambda cls, value: request),
        raising=False,
    )
    monkeypatch.setattr(
        AnalysisPublication,
        "from_value",
        classmethod(lambda cls, value: publication),
        raising=False,
    )
    calls: list[tuple[object, ...]] = []

    def export(*args: object):
        calls.append(args)
        return b'{"schema":"stm32-monitor-analysis-bundle/1"}', _BundleRef()

    monkeypatch.setattr(cli, "export_analysis_bundle", export, raising=False)
    monkeypatch.setattr(
        cli,
        "compare_monitor_runs",
        lambda *args: pytest.fail("bundle must not compare again"),
        raising=False,
    )
    output = io.StringIO()
    code = cli.main(
        [
            "analysis",
            "bundle",
            "--project",
            str(project),
            "--data-root",
            str(data),
            "--session-id",
            "monitor-a",
            "--request-file",
            str(request_file),
            "--publication-file",
            str(publication_file),
            "--failed-before-test-run-id",
            "failed",
            "--fixed-after-test-run-id",
            "fixed",
            "--json",
        ],
        _stdout=output,
    )

    assert code == 0
    payload = json.loads(output.getvalue())
    assert payload["operation"] == "monitor.analysis.bundle"
    assert payload["data"]["analysis_bundle"] == {"schema": "stm32-monitor-analysis-bundle/1"}
    assert payload["data"]["analysis_bundle_ref"] == _BundleRef().to_dict()
    assert len(calls) == 1
    assert calls[0][2:6] == (request, publication, "failed", "fixed")


def test_analysis_file_errors_are_stable_and_do_not_leak_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    _project_and_model(monkeypatch, project)
    output = io.StringIO()
    missing = tmp_path / "private-secret-request.json"
    code = cli.main(
        [
            "analysis",
            "compare",
            "--project",
            str(project),
            "--data-root",
            str(tmp_path / "data"),
            "--session-id",
            "monitor-a",
            "--request-file",
            str(missing),
            "--diagnostic-session-id",
            "1" * 32,
            "--hypothesis-id",
            "2" * 32,
            "--polarity",
            "supports",
            "--rationale",
            "changed",
            "--json",
        ],
        _stdout=output,
    )

    assert code == 1
    payload = json.loads(output.getvalue())
    assert payload["code"] == "ANALYSIS_WORKFLOW_INVALID"
    assert str(missing) not in output.getvalue()
