import json
from importlib import resources
from pathlib import Path
from uuid import UUID

import pytest

from stm32_toolkit.project import ProjectManifest, ProjectManifestError


def test_load_valid_project(tmp_path: Path, copy_fixture):
    copy_fixture("valid-project.json", tmp_path / ".stm32-project.json")
    (tmp_path / "App").mkdir()
    (tmp_path / "App/main.c").write_text("int main(void) { return 0; }", encoding="utf-8")

    manifest = ProjectManifest.load(tmp_path)

    assert manifest.logical_project_id == UUID("12345678-1234-5678-1234-567812345678")
    assert manifest.target_device == "STM32F429ZGTx"
    assert manifest.framework_type == "spl"
    assert manifest.source_paths == (tmp_path / "App/main.c",)
    assert manifest.assembly_source_paths == ()
    assert manifest.elf_path == tmp_path / "build-fw/firmware.elf"


def test_load_retains_validated_assembly_sources(configured_project: Path):
    manifest_path = configured_project / ".stm32-project.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["build"]["assemblySources"] = ["Startup/startup.s"]
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    manifest = ProjectManifest.load(configured_project)

    assert manifest.assembly_source_paths == (
        configured_project / "Startup" / "startup.s",
    )


def test_invalid_project_returns_schema_error(tmp_path: Path, copy_fixture):
    copy_fixture("invalid-project.json", tmp_path / ".stm32-project.json")

    with pytest.raises(ProjectManifestError) as error:
        ProjectManifest.load(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": "logicalProjectId", "rule": "required"}


def test_missing_manifest_returns_stable_not_configured_error(tmp_path: Path):
    with pytest.raises(ProjectManifestError) as error:
        ProjectManifest.load(tmp_path)

    assert error.value.code == "PROJECT_NOT_CONFIGURED"
    assert error.value.details == {"path": ".stm32-project.json"}


def test_malformed_json_returns_location_without_decoder_message(tmp_path: Path):
    (tmp_path / ".stm32-project.json").write_text("{", encoding="utf-8")

    with pytest.raises(ProjectManifestError) as error:
        ProjectManifest.load(tmp_path)

    assert error.value.code == "PROJECT_JSON_INVALID"
    assert error.value.details == {"path": "$", "line": 1, "column": 2}


def test_schema_rejects_unknown_top_level_fields(configured_project: Path):
    manifest_path = configured_project / ".stm32-project.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["watchGroups"] = []
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProjectManifestError) as error:
        ProjectManifest.load(configured_project)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": "watchGroups", "rule": "additionalProperties"}


def test_source_path_cannot_escape_canonical_project_root(configured_project: Path):
    manifest_path = configured_project / ".stm32-project.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["build"]["sources"] = ["../outside.c"]
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProjectManifestError) as error:
        ProjectManifest.load(configured_project)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {
        "field": "build.sources[0]",
        "rule": "pathWithinProjectRoot",
    }


def test_source_symlink_cannot_escape_canonical_project_root(configured_project: Path):
    outside = configured_project.parent / "outside.c"
    outside.write_text("int outside;", encoding="utf-8")
    link = configured_project / "App" / "outside-link.c"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symbolic links are unavailable in this test environment")

    manifest_path = configured_project / ".stm32-project.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["build"]["sources"] = ["App/outside-link.c"]
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProjectManifestError) as error:
        ProjectManifest.load(configured_project)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {
        "field": "build.sources[0]",
        "rule": "pathWithinProjectRoot",
    }


def test_explicit_schema_path_is_used(configured_project: Path, tmp_path: Path):
    schema_path = tmp_path / "schema.json"
    schema_path.write_text('{"type": "object", "required": ["missing"]}', encoding="utf-8")

    with pytest.raises(ProjectManifestError) as error:
        ProjectManifest.load(configured_project, schema_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": "missing", "rule": "required"}


def test_malformed_explicit_schema_returns_stable_schema_error(configured_project: Path, tmp_path: Path):
    schema_path = tmp_path / "schema.json"
    schema_path.write_text('{"type": 12}', encoding="utf-8")

    with pytest.raises(ProjectManifestError) as error:
        ProjectManifest.load(configured_project, schema_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": "$schema", "rule": "invalidSchema"}


def test_packaged_schema_matches_plugin_root_schema():
    package_schema = resources.files("stm32_toolkit").joinpath("schemas/stm32-project.schema.json")
    root_schema = Path(__file__).resolve().parents[3] / "schemas/stm32-project.schema.json"
    assert json.loads(package_schema.read_text(encoding="utf-8")) == json.loads(
        root_schema.read_text(encoding="utf-8")
    )


def test_project_root_file_returns_not_configured_error(tmp_path: Path):
    """Catches accepting a file as a project directory."""
    project_file = tmp_path / "not-a-directory"
    project_file.write_text("content", encoding="utf-8")

    with pytest.raises(ProjectManifestError) as error:
        ProjectManifest.load(project_file)

    assert error.value.code == "PROJECT_NOT_CONFIGURED"
    assert error.value.details == {"path": str(project_file)}


def test_invalid_utf8_manifest_returns_stable_json_error(tmp_path: Path):
    """Catches decoder details leaking from malformed manifest bytes."""
    (tmp_path / ".stm32-project.json").write_bytes(b"\xff")

    with pytest.raises(ProjectManifestError) as error:
        ProjectManifest.load(tmp_path)

    assert error.value.code == "PROJECT_JSON_INVALID"
    assert error.value.details == {"path": "$", "reason": "invalid_utf8"}


def test_unavailable_explicit_schema_returns_stable_schema_error(
    configured_project: Path, tmp_path: Path
):
    """Catches schema I/O errors being mistaken for manifest errors."""
    schema_path = tmp_path / "missing-schema.json"

    with pytest.raises(ProjectManifestError) as error:
        ProjectManifest.load(configured_project, schema_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": "$schema", "rule": "unavailable"}


def test_invalid_utf8_explicit_schema_returns_stable_schema_error(
    configured_project: Path, tmp_path: Path
):
    """Catches invalid schema encoding escaping as a Unicode exception."""
    schema_path = tmp_path / "schema.json"
    schema_path.write_bytes(b"\xff")

    with pytest.raises(ProjectManifestError) as error:
        ProjectManifest.load(configured_project, schema_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": "$schema", "rule": "unavailable"}


def test_schema_error_formats_array_index_in_field_path(configured_project: Path):
    """Catches array validation errors losing the failing source index."""
    manifest_path = configured_project / ".stm32-project.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["build"]["sources"] = [17]
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProjectManifestError) as error:
        ProjectManifest.load(configured_project)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": "build.sources[0]", "rule": "type"}
