"""BUILD-STALE-GUIDANCE: bounded diagnostics and conditional remediation.

These regressions keep the existing ``BUILD_OUTPUT_STALE`` admission
predicates unchanged while proving that the first failed comparison is named
with fixed fields, that recorded values are never echoed, and that advice
depends on the actual request (preset, clean, timeout) and observation.
All toolchain processes are the existing offline fake CMake/Git doubles; no
hardware, installation, or network path is touched.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

import stm32_toolkit.mcp_server as mcp_mod
from stm32_toolkit.build import BuildRequest, run_build
from stm32_toolkit.build.identity import compute_build_id
from stm32_toolkit.cli import main as cli_main
from stm32_toolkit.mcp_server import ServerRuntime

from test_build_runner import (
    identity_path_for,
    install_fake_cmake,
    log_path_for,
    prepare_project,
    read_json,
    release_log_path_for,
    release_result_path_for,
    result_path_for,
)
from test_build_snapshot import (
    identity_path as snapshot_identity_path,
    result_path as snapshot_result_path,
    snapshot_build,
)
from test_mcp_roots import _RootSession, _context


def _rewrite_identity_and_record(
    root: Path, mutator, *, identity_file=None, record_file=None
) -> None:
    """Mutate the identity, recompute its build ID, and sync the record."""
    identity_file = identity_file or identity_path_for(root)
    record_file = record_file or result_path_for(root)
    document = read_json(identity_file)
    mutator(document)
    document["buildId"] = compute_build_id(document)
    identity_file.write_text(json.dumps(document) + "\n", encoding="utf-8")
    record = read_json(record_file)
    record["buildId"] = document["buildId"]
    record_file.write_text(json.dumps(record) + "\n", encoding="utf-8")


def _assert_inspect_action(details: dict, *, clean: bool) -> None:
    assert details["remediation"]["action"] == "inspect-build-log"
    assert "cli" not in details["remediation"]
    assert "mcp" not in details["remediation"]
    assert details["cleanRequested"] is clean


def _assert_clean_rebuild_action(details: dict, preset: str, timeout: int) -> None:
    remediation = details["remediation"]
    assert remediation["action"] == "clean-rebuild"
    assert remediation["cli"]["executable"] == "caller-verified-stm32-toolkit"
    assert remediation["cli"]["workingDirectory"] == "project-root"
    # The tokens are only the command tail; the caller must prefix the
    # executable and the required explicit absolute project root.
    assert remediation["cli"]["projectRoot"] == {
        "option": "--project-root",
        "valueFrom": "same-bound-project-root",
        "required": True,
    }
    assert remediation["cli"]["arguments"] == [
        "build",
        "--preset",
        preset,
        "--clean",
        "--timeout-seconds",
        str(timeout),
    ]
    assert remediation["mcp"] == {
        "tool": "stm32_build",
        "arguments": {
            "preset": preset,
            "clean": True,
            "timeoutSeconds": timeout,
        },
    }
    assert remediation["authorizationRequired"] is True
    assert "Explicit user authorization" in remediation["authorization"]
    # Advice is not authorization: the proposed MCP call omits the flag.
    assert "authorized" not in remediation["mcp"]["arguments"]


# ---------------------------------------------------------------------------
# unavailable outputs
# ---------------------------------------------------------------------------


def test_missing_elf_is_output_unavailable_and_advises_log_inspection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path, env={"FAKE_CMAKE_NO_OUTPUT": "1"})

    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert result.ok is False
    assert result.code == "BUILD_OUTPUT_STALE"
    details = result.details
    assert details["path"] == "build/arm-debug/firmware.elf"
    assert details["rule"] == "missing"
    assert details["reason"] == "output-unavailable"
    assert details["evidenceSource"] == "output"
    assert "evidenceField" not in details
    assert details["preset"] == "arm-debug"
    _assert_inspect_action(details, clean=False)
    # No fresh identity and no admitted success: the failure receipt only.
    assert not identity_path_for(root).exists()
    failure = read_json(result_path_for(root))
    assert failure["status"] == "failure"
    assert failure["code"] == "BUILD_OUTPUT_STALE"
    assert failure["buildId"] is None
    # The bounded log keeps the existing message/code; diagnostics live on
    # the OperationResult and do not alter the failure receipt schema.
    log_text = log_path_for(root).read_text(encoding="utf-8")
    assert "code=BUILD_OUTPUT_STALE" in log_text
    assert "message=build outputs are stale" in log_text


def test_missing_map_is_output_unavailable_and_advises_log_inspection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(
        monkeypatch, tmp_path, env={"FAKE_CMAKE_MAP_DEFECT": "missing"}
    )

    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert result.ok is False
    assert result.code == "BUILD_OUTPUT_STALE"
    assert result.details["path"] == "build/arm-debug/firmware.map"
    assert result.details["rule"] == "missing"
    assert result.details["reason"] == "output-unavailable"
    assert result.details["evidenceSource"] == "output"
    _assert_inspect_action(result.details, clean=False)


def test_missing_output_with_clean_requested_still_advises_log_inspection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path, env={"FAKE_CMAKE_NO_OUTPUT": "1"})

    result = run_build(
        BuildRequest(project_root=root, preset="arm-debug", clean=True)
    )

    assert result.code == "BUILD_OUTPUT_STALE"
    assert result.details["reason"] == "output-unavailable"
    _assert_inspect_action(result.details, clean=True)


# ---------------------------------------------------------------------------
# clean-rebuild advice
# ---------------------------------------------------------------------------


def test_input_snapshot_mismatch_offers_exact_clean_rebuild_advice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    first = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert first.ok is True

    (root / "Src" / "main.c").write_text(
        "int main(void) { return 41; }\n", encoding="utf-8"
    )
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")

    result = run_build(
        BuildRequest(project_root=root, preset="arm-debug", timeout_seconds=300)
    )

    assert result.ok is False
    assert result.code == "BUILD_OUTPUT_STALE"
    details = result.to_dict()["details"]
    assert details["path"] == "build/arm-debug/firmware.elf"
    assert details["rule"] == "unverifiable"
    assert details["reason"] == "input-snapshot-mismatch"
    assert details["evidenceField"] == "inputSnapshotSha256"
    assert details["evidenceSource"] == "record"
    assert details["preset"] == "arm-debug"
    assert details["cleanRequested"] is False
    assert details["identityPath"] == "build/arm-debug/firmware-identity.json"
    assert details["logPath"] == "artifacts/migration/build.log"
    assert details["resultPath"] == "artifacts/migration/build-result.json"
    _assert_clean_rebuild_action(details, "arm-debug", 300)


def test_release_preset_and_nondefault_timeout_are_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    first = run_build(BuildRequest(project_root=root, preset="arm-release"))
    assert first.ok is True, first
    # The recorded evidence now names a different preset, so the accepted
    # admission comparison fails with the fixed preset discriminator.  The
    # release receipt pair is the release preset's own (POST134-A).
    record = read_json(release_result_path_for(root))
    record["preset"] = "arm-debug"
    release_result_path_for(root).write_text(json.dumps(record) + "\n", encoding="utf-8")
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")

    result = run_build(
        BuildRequest(
            project_root=root,
            preset="arm-release",
            timeout_seconds=777,
        )
    )

    assert result.ok is False
    assert result.code == "BUILD_OUTPUT_STALE"
    details = result.to_dict()["details"]
    assert details["reason"] == "prior-evidence-mismatch"
    assert details["evidenceField"] == "preset"
    assert details["evidenceSource"] == "record"
    assert details["path"] == "build/arm-release/firmware.elf"
    assert details["preset"] == "arm-release"
    assert details["cleanRequested"] is False
    assert details["identityPath"] == "build/arm-release/firmware-identity.json"
    assert details["logPath"] == "artifacts/migration/arm-release/build.log"
    assert details["resultPath"] == (
        "artifacts/migration/arm-release/build-result.json"
    )
    assert release_log_path_for(root).is_file()
    _assert_clean_rebuild_action(details, "arm-release", 777)


def test_clean_already_requested_advises_inspection_without_rebuild_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    first = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert first.ok is True

    (root / "Src" / "main.c").write_text(
        "int main(void) { return 42; }\n", encoding="utf-8"
    )
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")

    result = run_build(
        BuildRequest(
            project_root=root,
            preset="arm-debug",
            clean=True,
            timeout_seconds=123,
        )
    )

    assert result.ok is False
    assert result.code == "BUILD_OUTPUT_STALE"
    details = result.to_dict()["details"]
    assert details["reason"] == "input-snapshot-mismatch"
    assert details["evidenceField"] == "inputSnapshotSha256"
    _assert_inspect_action(details, clean=True)
    assert "123" not in json.dumps(details["remediation"])
    assert "0" * 64 not in json.dumps(details)


# ---------------------------------------------------------------------------
# prior receipt availability and success
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("broken", ["result", "identity"])
def test_malformed_receipt_is_prior_evidence_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, broken: str
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    assert run_build(BuildRequest(project_root=root, preset="arm-debug")).ok is True
    target = result_path_for(root) if broken == "result" else identity_path_for(root)
    target.write_text("{not-json\n", encoding="utf-8")
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")

    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert result.code == "BUILD_OUTPUT_STALE"
    details = result.to_dict()["details"]
    assert details["path"] == "build/arm-debug/firmware.elf"
    assert details["rule"] == "unverifiable"
    assert details["reason"] == "prior-evidence-unavailable"
    assert "evidenceField" not in details
    assert "evidenceSource" not in details
    _assert_clean_rebuild_action(details, "arm-debug", 300)


def test_non_success_receipt_is_previous_build_not_successful(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    assert run_build(BuildRequest(project_root=root, preset="arm-debug")).ok is True
    record = read_json(result_path_for(root))
    record["status"] = "failure"
    result_path_for(root).write_text(json.dumps(record) + "\n", encoding="utf-8")
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")

    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert result.code == "BUILD_OUTPUT_STALE"
    details = result.to_dict()["details"]
    assert details["reason"] == "prior-build-not-successful"
    assert details["evidenceField"] == "status"
    assert details["evidenceSource"] == "record"
    _assert_clean_rebuild_action(details, "arm-debug", 300)


@pytest.mark.parametrize(
    ("mutate", "expected_field"),
    [
        (lambda record: record.__setitem__("gitDirty", 0), "gitDirty"),
        (lambda record: record.__setitem__("code", "PARTIAL"), "code"),
        (lambda record: record.__setitem__("stage", "complete-later"), "stage"),
        (lambda record: record.__setitem__("schemaVersion", True), "schemaVersion"),
        (lambda record: record.__setitem__("schemaVersion", 2), "schemaVersion"),
    ],
    ids=[
        "numeric-dirty",
        "unsupported-code",
        "unsupported-stage",
        "bool-schema",
        "cross-schema",
    ],
)
def test_malformed_or_cross_schema_prior_record_is_never_reused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutate,
    expected_field: str,
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    assert run_build(BuildRequest(project_root=root, preset="arm-debug")).ok is True
    record = read_json(result_path_for(root))
    mutate(record)
    result_path_for(root).write_text(json.dumps(record) + "\n", encoding="utf-8")
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")

    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert result.ok is False
    assert result.code == "BUILD_OUTPUT_STALE"
    assert result.details["reason"] == "prior-evidence-mismatch"
    assert result.details["evidenceField"] == expected_field
    assert result.details["evidenceSource"] == "record"


# ---------------------------------------------------------------------------
# identity field discriminators
# ---------------------------------------------------------------------------


def test_invalid_identity_document_is_named_without_echoing_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    assert run_build(BuildRequest(project_root=root, preset="arm-debug")).ok is True
    document = read_json(identity_path_for(root))
    document["targetDevice"] = ["leak-marker"]
    identity_path_for(root).write_text(
        json.dumps(document) + "\n", encoding="utf-8"
    )
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")

    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert result.code == "BUILD_OUTPUT_STALE"
    details = result.to_dict()["details"]
    assert details["reason"] == "prior-evidence-mismatch"
    assert details["evidenceField"] == "identityDocument"
    assert details["evidenceSource"] == "identity"
    dumped = json.dumps(details)
    assert "leak-marker" not in dumped
    assert str(root) not in dumped
    assert root.as_posix() not in dumped


def test_identity_git_head_mismatch_is_named_after_earlier_checks_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    assert run_build(BuildRequest(project_root=root, preset="arm-debug")).ok is True
    # Recompute the identity build ID after changing gitHead and sync the
    # prior record's buildId, so the early comparisons all match and only the
    # record/identity provenance pair itself disagrees.
    _rewrite_identity_and_record(
        root, lambda document: document.__setitem__("gitHead", "0" * 40)
    )
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")

    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert result.ok is False
    assert result.code == "BUILD_OUTPUT_STALE"
    details = result.to_dict()["details"]
    assert details["path"] == "build/arm-debug/firmware.elf"
    assert details["rule"] == "unverifiable"
    assert details["reason"] == "prior-evidence-mismatch"
    assert details["evidenceField"] == "gitHead"
    assert details["evidenceSource"] == "record"
    assert details["preset"] == "arm-debug"
    assert details["cleanRequested"] is False
    _assert_clean_rebuild_action(details, "arm-debug", 300)


def test_snapshot_strict_result_mismatch_reports_snapshot_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, _identity, _record = snapshot_build(tmp_path, monkeypatch)
    record = read_json(snapshot_result_path(root))
    record.pop("gitHead")
    snapshot_result_path(root).write_text(
        json.dumps(record) + "\n", encoding="utf-8"
    )
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")

    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert result.code == "BUILD_OUTPUT_STALE"
    details = result.to_dict()["details"]
    assert details["reason"] == "prior-evidence-mismatch"
    assert details["evidenceField"] == "snapshotResult"
    assert details["evidenceSource"] == "record"
    assert details["cleanRequested"] is False
    _assert_clean_rebuild_action(details, "arm-debug", 300)


@pytest.mark.parametrize(
    ("field", "value", "expected_field", "expected_source"),
    [
        pytest.param(
            "logicalProjectId",
            "87654321-4321-8765-4321-876543218765",
            "logicalProjectId",
            "identity",
            id="project-id",
        ),
        pytest.param(
            "toolkitVersion",
            "0.0.0",
            "toolkitVersion",
            "identity",
            id="toolkit-version",
        ),
        pytest.param(
            "gitEvidence",
            {"status": "unavailable", "code": "BUILD_GIT_INVALID", "rule": "status"},
            "gitEvidence",
            "record",
            id="git-evidence",
        ),
    ],
)
def test_snapshot_identity_field_mismatches_are_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value,
    expected_field: str,
    expected_source: str,
):
    root, _identity, _record = snapshot_build(tmp_path, monkeypatch)
    _rewrite_identity_and_record(
        root,
        lambda document: document.__setitem__(field, value),
        identity_file=snapshot_identity_path(root),
        record_file=snapshot_result_path(root),
    )
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")

    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert result.code == "BUILD_OUTPUT_STALE"
    details = result.details
    assert details["reason"] == "prior-evidence-mismatch"
    assert details["evidenceField"] == expected_field
    assert details["evidenceSource"] == expected_source


def test_snapshot_identity_schema_mismatch_is_identity_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, _identity, _record = snapshot_build(tmp_path, monkeypatch)
    # Schema 2 requires null Git fields; a boolean is rejected by the shared
    # identity schema before any later provenance comparison.
    _rewrite_identity_and_record(
        root,
        lambda document: document.__setitem__("gitDirty", False),
        identity_file=snapshot_identity_path(root),
        record_file=snapshot_result_path(root),
    )
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")

    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert result.code == "BUILD_OUTPUT_STALE"
    assert result.details["reason"] == "prior-evidence-mismatch"
    assert result.details["evidenceField"] == "identityDocument"
    assert result.details["evidenceSource"] == "identity"


# ---------------------------------------------------------------------------
# provenance cross-mode
# ---------------------------------------------------------------------------


def test_git_to_snapshot_provenance_reuses_outputs_and_records_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from stm32_toolkit.build import identity as identity_mod

    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    assert run_build(BuildRequest(project_root=root, preset="arm-debug")).ok is True
    assert read_json(identity_path_for(root))["schemaVersion"] == 1
    # Git availability is optional traceability, not freshness: unchanged
    # inputs/artifacts remain reusable and the new success records the
    # truthful snapshot provenance rather than a fabricated commit.
    monkeypatch.setattr(
        "stm32_toolkit.build.runner.collect_build_git_evidence",
        lambda _root, _timeout=30: identity_mod.GitUnavailableEvidence(rule="head"),
    )
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")

    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert result.ok is True, result
    identity = read_json(identity_path_for(root))
    record = read_json(result_path_for(root))
    assert identity["schemaVersion"] == 2
    assert identity["gitHead"] is None and identity["gitDirty"] is None
    assert identity["sourceBaseline"] == "input-snapshot-v1"
    assert record["schemaVersion"] == 2
    assert record["buildId"] == identity["buildId"]


def test_snapshot_to_git_provenance_reuses_outputs_and_records_real_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from stm32_toolkit.build import identity as identity_mod

    root, _identity, _record = snapshot_build(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "stm32_toolkit.build.runner.collect_build_git_evidence",
        lambda _root, _timeout=30: identity_mod.GitEvidence(head="b" * 40, dirty=False),
    )
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")

    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert result.ok is True, result
    identity = read_json(identity_path_for(root))
    assert identity["schemaVersion"] == 1
    assert identity["gitHead"] == "b" * 40
    assert identity["gitDirty"] is False


# ---------------------------------------------------------------------------
# no mutation of accepted outputs/evidence, and unrelated guards
# ---------------------------------------------------------------------------


def test_stale_failure_preserves_outputs_and_prior_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    assert run_build(BuildRequest(project_root=root, preset="arm-debug")).ok is True
    elf_path = root / "build" / "arm-debug" / "firmware.elf"
    map_path = root / "build" / "arm-debug" / "firmware.map"
    elf_bytes = elf_path.read_bytes()
    map_bytes = map_path.read_bytes()
    identity_bytes = identity_path_for(root).read_bytes()

    (root / "Src" / "main.c").write_text(
        "int main(void) { return 43; }\n", encoding="utf-8"
    )
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")

    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert result.code == "BUILD_OUTPUT_STALE"
    assert elf_path.read_bytes() == elf_bytes
    assert map_path.read_bytes() == map_bytes
    # No fresh identity is published to make the stale outputs look current.
    assert identity_path_for(root).read_bytes() == identity_bytes
    failure = read_json(result_path_for(root))
    assert failure["status"] == "failure"
    assert failure["code"] == "BUILD_OUTPUT_STALE"
    assert failure["buildId"] is None
    assert failure["schemaVersion"] == 1


def test_managed_drift_is_refused_without_stale_guidance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    (root / "CMakeLists.txt").write_text(
        (root / "CMakeLists.txt").read_text(encoding="utf-8") + "\n# drift\n",
        encoding="utf-8",
    )

    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert result.ok is False
    assert result.code == "BUILD_PROJECT_INVALID"
    assert result.details["path"] == "CMakeLists.txt"
    assert result.details["rule"] == "digest"
    assert "reason" not in result.details
    assert "remediation" not in result.details


# ---------------------------------------------------------------------------
# public MCP/CLI boundaries
# ---------------------------------------------------------------------------


def test_mcp_stale_guidance_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    runtime = ServerRuntime.create(root, tmp_path / "plugin-data", "session-a")

    unauthorized = asyncio.run(
        mcp_mod.tool_build_for_request(
            runtime,
            _context(_RootSession([[root]])),
            preset="arm-debug",
            authorized=False,
        )
    )
    assert unauthorized["ok"] is False
    assert unauthorized["code"] == "AUTHORIZATION_REQUIRED"
    assert "remediation" not in unauthorized["details"]

    first = asyncio.run(
        mcp_mod.tool_build_for_request(
            runtime,
            _context(_RootSession([[root]])),
            preset="arm-debug",
            authorized=True,
        )
    )
    assert first["ok"] is True, first

    (root / "Src" / "main.c").write_text(
        "int main(void) { return 44; }\n", encoding="utf-8"
    )
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")

    stale = asyncio.run(
        mcp_mod.tool_build_for_request(
            runtime,
            _context(_RootSession([[root]])),
            preset="arm-debug",
            timeout_seconds=321,
            authorized=True,
        )
    )

    assert stale["ok"] is False
    assert stale["operation"] == "build"
    assert stale["code"] == "BUILD_OUTPUT_STALE"
    details = stale["details"]
    assert details["reason"] == "input-snapshot-mismatch"
    assert details["evidenceField"] == "inputSnapshotSha256"
    _assert_clean_rebuild_action(details, "arm-debug", 321)

    # The proposed MCP call must use the public camelCase schema of the same
    # registered tool and omit the authorization flag (default false).
    server = mcp_mod.create_server(root, tmp_path / "plugin-data", "session-a")
    tools = {
        tool.name: tool for tool in asyncio.run(server.list_tools())
    }
    schema = tools["stm32_build"].inputSchema
    proposed = details["remediation"]["mcp"]
    assert proposed["tool"] == "stm32_build"
    arguments = proposed["arguments"]
    assert set(arguments) == {"preset", "clean", "timeoutSeconds"}
    properties = schema["properties"]
    assert set(arguments) <= set(properties)
    assert arguments["preset"] in properties["preset"]["enum"]
    assert properties["preset"]["type"] == "string"
    assert properties["clean"]["type"] == "boolean"
    assert properties["clean"]["default"] is False
    assert arguments["clean"] is True
    assert properties["timeoutSeconds"]["type"] == "integer"
    assert properties["timeoutSeconds"]["default"] == 300
    assert arguments["timeoutSeconds"] == 321
    assert "authorized" not in arguments
    assert properties["authorized"]["type"] == "boolean"
    assert properties["authorized"]["default"] is False


def test_cli_clean_help_states_clean_first_scope(capsys):
    assert cli_main(["build", "--help"]) == 0
    output = " ".join(capsys.readouterr().out.split())
    assert "--clean-first" in output
    assert "does not delete" in output
    assert "does not guarantee fresh ELF/MAP evidence" in output
