from __future__ import annotations

import io
import json
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

import stm32_monitor.cli as cli
from stm32_monitor.analysis import AnalysisRequest
from stm32_monitor.analysis_workflows import AnalysisPublication, AnalysisWorkflowError
from stm32_monitor.protocol import ProtocolResult
from stm32_monitor.replay import (
    INCOMPATIBLE_IDENTITY,
    MonitorReplayError,
    MonitorRunRef,
    OPERATION_CONFLICT,
    canonical_replay_json_bytes,
)
from stm32_toolkit.diagnostics import SourceChangeDeclaration
from stm32_toolkit.evidence import ArtifactRef, EVIDENCE_INVALID, EvidenceValidationError
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.project_model import ProjectManifestError


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


def _real_project(project: Path) -> None:
    payload = {
        "schemaVersion": 3,
        "logicalProjectId": str(PROJECT_ID),
        "generatedBy": {"tool": "stm32-toolkit", "version": "0.6"},
        "project": {"name": "analysis-cli", "origin": "manual"},
        "target": {"device": "stm32:stm32f429zi", "core": "cortex-m4"},
        "framework": {"type": "bare-metal", "version": None},
        "build": {
            "sources": [],
            "includePaths": [],
            "defines": [],
            "compileOptions": [],
            "assemblySources": [],
            "presets": [],
            "elf": None,
        },
        "memory": {"source": "manual", "regions": []},
        "debug": {"backend": "pyocd", "target": "board:fixture-01", "svd": None},
        "generation": {
            "cubeMxIoc": None,
            "managedManifest": ".stm32-toolkit/generated-files.json",
            "generatedDirectories": [],
            "userDirectories": [],
        },
    }
    project.mkdir()
    _write_json(project / ".stm32-project.json", payload)


def _valid_analysis_request_wire() -> dict[str, object]:
    def reference(role: str, run_id: str) -> MonitorRunRef:
        payload: dict[str, object] = {
            "schema": "stm32-monitor-run-ref/1",
            "operation_id": run_id,
            "scenario_role": role,
            "execution_source": "replay",
            "physical_transport_evidence": False,
            "origin_workspace_id": "a" * 64,
            "import_workspace_id": "a" * 64,
            "logical_project_id": str(PROJECT_ID),
            "origin_session_id": "session-a",
            "projected_session_id": "session-a",
            "origin_run_id": run_id,
            "projected_run_id": run_id,
            "target_device": "target",
            "probe_id": "replay:probe-v2",
            "physical_target": "replay:non-physical",
            "build_id": "b" * 64,
            "elf_sha256": "c" * 64,
            "input_snapshot_sha256": "d" * 64,
            "git_head": "e" * 40,
            "git_dirty": False,
            "flash_session_id": "replay:no-flash",
            "lease_id": "replay:no-lease",
            "dwarf_sha256": "f" * 64,
            "svd_sha256": "0" * 64,
            "group_id": "11111111-1111-4111-8111-111111111111",
            "group_revision": 1,
            "start_sequence": 0,
            "end_sequence_exclusive": 1,
            "start_captured_unix_ns": 100,
            "end_captured_unix_ns_exclusive": 101,
            "fixture_sha256": "1" * 64,
            "projected_batch_sha256s": ["2" * 64],
            "transcript_evidence_id": "3" * 64,
        }
        payload["run_ref_sha256"] = sha256(
            canonical_replay_json_bytes(payload)
        ).hexdigest()
        return MonitorRunRef.from_value(payload)

    before = reference(
        "failed-before", "33333333-3333-4333-8333-333333333333"
    )
    after = reference("fixed-after", "44444444-4444-4444-8444-444444444444")
    return AnalysisRequest(
        schema="stm32-monitor-analysis-request/1",
        before_run=before,
        after_run=after,
        selector_kind="variable",
        selector="counter",
        alignment="run-relative",
        minimum_valid_pairs=2,
    ).to_dict()


def _valid_source_change_wire() -> dict[str, object]:
    return SourceChangeDeclaration.new(
        before_source_sha256="8" * 64,
        after_source_sha256="9" * 64,
        before_build_id="a" * 64,
        before_elf_sha256="b" * 64,
        after_build_id="c" * 64,
        after_elf_sha256="d" * 64,
        changed_paths=("src/main.c", "src/monitor.c"),
        diff_evidence_id="e" * 64,
        diff_artifact=ArtifactRef(
            sha256="7" * 64,
            size_bytes=17,
            relative_path="changes.diff",
            kind="source-diff",
            media_type="text/x-diff",
        ),
        claimed_hypothesis_ids=("2" * 32,),
        validation_plan_id="0" * 64,
    ).to_dict()


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


def test_replay_adapter_ctrl_c_returns_130_without_protocol_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    data = tmp_path / "data"
    _project_and_model(monkeypatch, project)
    document = tmp_path / "document.json"
    document.write_text("{}", encoding="utf-8")
    calls = 0

    def interrupted(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        del args, kwargs
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "ingest_monitor_replay", interrupted, raising=False)
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

    assert code == 130
    assert calls == 1
    assert output.getvalue() == ""


def test_analysis_compare_projects_closed_inputs_and_calls_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    data = tmp_path / "data"
    _real_project(project)
    request_file = tmp_path / "request.json"
    request_wire = _valid_analysis_request_wire()
    _write_json(request_file, request_wire)
    request = AnalysisRequest.from_value(request_wire)
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
    assert args[7] is None
    assert args[0].workspace_root / "evidence" == args[1].root


def test_analysis_compare_loads_valid_source_change_and_calls_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    data = tmp_path / "data"
    _real_project(project)
    request_file = tmp_path / "request.json"
    source_file = tmp_path / "source-change.json"
    _write_json(request_file, _valid_analysis_request_wire())
    source_wire = _valid_source_change_wire()
    _write_json(source_file, source_wire)
    source_change = SourceChangeDeclaration.from_value(source_wire)
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
    assert json.loads(output.getvalue())["data"] == {
        "analysis_publication": _Publication().to_dict()
    }
    assert len(calls) == 1
    assert calls[0][7] == source_change


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


def test_analysis_provider_failure_is_sanitized_without_exception_or_path_leak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    data = tmp_path / "data"
    _project_and_model(monkeypatch, project)
    request_file = tmp_path / "request.json"
    _write_json(request_file, {"request": "closed"})
    request = object()
    monkeypatch.setattr(
        AnalysisRequest,
        "from_value",
        classmethod(lambda cls, value: request),
        raising=False,
    )
    private_path = tmp_path / "private-provider-secret.json"
    calls = 0

    def fail(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        del args, kwargs
        raise RuntimeError(f"private provider secret at {private_path}")

    monkeypatch.setattr(cli, "compare_monitor_runs", fail, raising=False)
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
            "--json",
        ],
        _stdout=output,
    )

    assert code == 1
    assert calls == 1
    payload = json.loads(output.getvalue())
    assert payload["code"] == "ENVIRONMENT_FAILURE"
    assert payload["message"] == "Monitor analysis provider failed"
    assert "private provider secret" not in output.getvalue()
    assert str(private_path) not in output.getvalue()


@pytest.mark.parametrize(
    ("error", "expected_code", "expected_message"),
    (
        (
            AnalysisWorkflowError("OPERATION_CONFLICT", "same operation"),
            "EVIDENCE_INTEGRITY_FAILURE",
            "same operation",
        ),
        (
            AnalysisWorkflowError("ENVIRONMENT_FAILURE", "provider unavailable"),
            "ENVIRONMENT_FAILURE",
            "provider unavailable",
        ),
        (
            MonitorReplayError("MONITOR_REPLAY_INVALID", "replay is invalid"),
            "ANALYSIS_WORKFLOW_INVALID",
            "replay is invalid",
        ),
        (
            EvidenceValidationError(EVIDENCE_INVALID, "evidence is invalid"),
            "EVIDENCE_INTEGRITY_FAILURE",
            "Evidence is invalid",
        ),
        (
            TypeError("bad analysis input"),
            "ANALYSIS_WORKFLOW_INVALID",
            "Monitor analysis input is invalid",
        ),
        (
            OSError("provider unavailable"),
            "ENVIRONMENT_FAILURE",
            "Monitor analysis provider failed",
        ),
    ),
)
def test_public_analysis_cli_maps_each_adapter_failure_class(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: BaseException,
    expected_code: str,
    expected_message: str,
) -> None:
    project = tmp_path / "project"
    data = tmp_path / "data"
    _real_project(project)
    request_file = tmp_path / "request.json"
    _write_json(request_file, _valid_analysis_request_wire())
    calls = 0

    def fail(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        del args, kwargs
        raise error

    monkeypatch.setattr(cli, "compare_monitor_runs", fail, raising=False)
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
            "--json",
        ],
        _stdout=output,
    )

    assert code == 1
    assert calls == 1
    payload = json.loads(output.getvalue())
    assert payload["code"] == expected_code
    assert payload["message"] == expected_message
    assert "bad analysis input" not in output.getvalue()


def test_analysis_file_permission_failure_is_environment_error_without_leaks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    _project_and_model(monkeypatch, project)
    private = tmp_path / "private-secret-request.json"

    def deny(cls: object, path: Path, *, maximum_bytes: int | None = None) -> bytes:
        raise PermissionError("private provider secret")

    monkeypatch.setattr(cli.EvidenceStore, "_read_file_bytes", classmethod(deny))
    output = io.StringIO()
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
            str(private),
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
    assert payload["code"] == "ENVIRONMENT_FAILURE"
    assert "private provider secret" not in output.getvalue()
    assert str(private) not in output.getvalue()


def test_project_manifest_permission_failure_is_environment_error_without_leaks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()

    def fail(_root: Path):
        try:
            raise PermissionError("private manifest provider secret")
        except PermissionError as cause:
            raise ProjectManifestError(
                "PROJECT_NOT_CONFIGURED", "manifest unavailable", {}
            ) from cause

    monkeypatch.setattr(cli, "load_project_model", fail)
    output = io.StringIO()
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
            str(tmp_path / "request.json"),
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
    assert payload["code"] == "ENVIRONMENT_FAILURE"
    assert "private manifest provider secret" not in output.getvalue()


def test_analysis_cli_rejects_schema_v2_context_before_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    fixture = (
        Path(__file__).resolve().parents[2]
        / "stm32-toolkit"
        / "tests"
        / "fixtures"
        / "minimal-gcc"
        / ".stm32-project.json"
    )
    (project / ".stm32-project.json").write_bytes(fixture.read_bytes())
    request_file = tmp_path / "request.json"
    _write_json(request_file, _valid_analysis_request_wire())
    calls: list[object] = []
    monkeypatch.setattr(
        cli,
        "compare_monitor_runs",
        lambda *args, **kwargs: calls.append((args, kwargs)),
        raising=False,
    )
    before = tuple(sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*")))
    output = io.StringIO()
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
            str(request_file),
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
    assert json.loads(output.getvalue()) == {
        "code": "ANALYSIS_WORKFLOW_INVALID",
        "data": None,
        "message": "Project schema version is invalid",
        "ok": False,
        "operation": "monitor.analysis.compare",
    }
    assert calls == []
    assert tuple(sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))) == before


def test_analysis_cli_rejects_noncanonical_request_before_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    _real_project(project)
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps(_valid_analysis_request_wire()), encoding="utf-8")
    request_bytes = request_file.read_bytes()
    calls: list[object] = []
    monkeypatch.setattr(
        cli,
        "compare_monitor_runs",
        lambda *args, **kwargs: calls.append((args, kwargs)),
        raising=False,
    )
    before = tuple(sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*")))
    output = io.StringIO()
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
            str(request_file),
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
    assert json.loads(output.getvalue()) == {
        "code": "ANALYSIS_WORKFLOW_INVALID",
        "data": None,
        "message": "JSON input is not canonical",
        "ok": False,
        "operation": "monitor.analysis.compare",
    }
    assert calls == []
    assert request_file.read_bytes() == request_bytes
    assert tuple(sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))) == before


def test_analysis_cli_rejects_invalid_request_model_before_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    _real_project(project)
    request_file = tmp_path / "request.json"
    request_wire = _valid_analysis_request_wire()
    request_wire["minimum_valid_pairs"] = 1
    _write_json(request_file, request_wire)
    request_bytes = request_file.read_bytes()
    calls: list[object] = []
    monkeypatch.setattr(
        cli,
        "compare_monitor_runs",
        lambda *args, **kwargs: calls.append((args, kwargs)),
        raising=False,
    )
    before = tuple(sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*")))
    output = io.StringIO()
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
            str(request_file),
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
    assert json.loads(output.getvalue()) == {
        "code": "ANALYSIS_WORKFLOW_INVALID",
        "data": None,
        "message": "analysis request is invalid",
        "ok": False,
        "operation": "monitor.analysis.compare",
    }
    assert calls == []
    assert request_file.read_bytes() == request_bytes
    assert tuple(sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))) == before


def test_analysis_cli_rejects_invalid_source_change_before_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    _real_project(project)
    request_file = tmp_path / "request.json"
    source_file = tmp_path / "source-change.json"
    _write_json(request_file, _valid_analysis_request_wire())
    source_wire = _valid_source_change_wire()
    source_wire["changed_paths"] = []
    _write_json(source_file, source_wire)
    source_bytes = source_file.read_bytes()
    calls: list[object] = []
    monkeypatch.setattr(
        cli,
        "compare_monitor_runs",
        lambda *args, **kwargs: calls.append((args, kwargs)),
        raising=False,
    )
    before = tuple(sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*")))
    output = io.StringIO()
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

    assert code == 1
    assert json.loads(output.getvalue()) == {
        "code": "ANALYSIS_WORKFLOW_INVALID",
        "data": None,
        "message": "source change declaration is invalid",
        "ok": False,
        "operation": "monitor.analysis.compare",
    }
    assert calls == []
    assert source_file.read_bytes() == source_bytes
    assert tuple(sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))) == before


def test_replay_adapter_maps_recognized_identity_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    _real_project(project)
    document = tmp_path / "document.json"
    document.write_text("{}", encoding="utf-8")
    calls: list[tuple[object, ...]] = []

    def fail(*args: object) -> object:
        calls.append(args)
        raise MonitorReplayError(INCOMPATIBLE_IDENTITY, "identity mismatch")

    monkeypatch.setattr(cli, "ingest_monitor_replay", fail, raising=False)
    before = tuple(sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*")))
    output = io.StringIO()
    code = cli.main(
        [
            "replay",
            "ingest",
            "--project",
            str(project),
            "--data-root",
            str(tmp_path / "data"),
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

    assert code == 1
    assert json.loads(output.getvalue()) == {
        "code": "INCOMPATIBLE_IDENTITY",
        "data": None,
        "message": "identity mismatch",
        "ok": False,
        "operation": "monitor.replay.ingest",
    }
    assert len(calls) == 1
    assert tuple(sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))) == before


def test_replay_adapter_maps_ingest_operation_conflict_to_integrity_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    _real_project(project)
    document = tmp_path / "document.json"
    document.write_text("{}", encoding="utf-8")
    calls: list[tuple[object, ...]] = []

    def fail(*args: object) -> object:
        calls.append(args)
        raise MonitorReplayError(OPERATION_CONFLICT, "operation already has different intent")

    monkeypatch.setattr(cli, "ingest_monitor_replay", fail, raising=False)
    before = tuple(sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*")))
    output = io.StringIO()
    code = cli.main(
        [
            "replay",
            "ingest",
            "--project",
            str(project),
            "--data-root",
            str(tmp_path / "data"),
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

    assert code == 1
    assert json.loads(output.getvalue()) == {
        "code": "EVIDENCE_INTEGRITY_FAILURE",
        "data": None,
        "message": "operation already has different intent",
        "ok": False,
        "operation": "monitor.replay.ingest",
    }
    assert len(calls) == 1
    assert tuple(sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))) == before
