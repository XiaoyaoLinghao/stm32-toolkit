from __future__ import annotations

import json
import os
from collections.abc import Mapping as MappingABC
from hashlib import sha256
from importlib import resources
from pathlib import Path
from types import MappingProxyType
from uuid import UUID

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from stm32_toolkit import __version__
from stm32_toolkit.project import ProjectManifest, ProjectManifestError
from stm32_toolkit.project_model import load_project_model
from stm32_toolkit.project_upgrade import (
    ProjectUpgradeError,
    UpgradePlan,
    apply_project_upgrade,
    plan_project_upgrade,
)

V1_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "valid-project.json"
MANIFEST_NAME = ".stm32-project.json"


def _v1_payload(origin: str = "manual") -> dict:
    payload = json.loads(V1_FIXTURE.read_text(encoding="utf-8"))
    payload["project"]["origin"] = origin
    return payload


def _v2_payload() -> dict:
    return {
        "schemaVersion": 2,
        "logicalProjectId": "12345678-1234-5678-1234-567812345678",
        "generatedBy": {"tool": "stm32-toolkit", "version": __version__},
        "project": {"name": "firmware", "origin": "manual"},
        "target": {"device": "STM32F429ZGTx", "core": "cortex-m4"},
        "framework": {"type": "spl", "version": None},
        "build": {
            "sources": ["App/main.c"],
            "includePaths": [],
            "defines": [],
            "compileOptions": [],
            "assemblySources": [],
            "presets": [],
            "elf": "build-fw/firmware.elf",
        },
        "memory": {"source": "manual", "regions": []},
        "debug": {"backend": "pyocd", "target": "stm32f429zgtx", "svd": None},
        "generation": {
            "cubeMxIoc": None,
            "managedManifest": ".stm32-toolkit/generated-files.json",
            "generatedDirectories": [],
            "userDirectories": [],
        },
    }


def _write_manifest(tmp_path: Path, payload: dict) -> Path:
    manifest_path = tmp_path / MANIFEST_NAME
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return manifest_path


def _inventory(root: Path) -> dict[str, tuple[int, int]]:
    """Recursive (name, mtime_ns, size) snapshot proving tree immutability."""
    inventory: dict[str, tuple[int, int]] = {}
    for path in sorted(root.rglob("*")):
        stat = path.stat()
        inventory[str(path.relative_to(root))] = (stat.st_mtime_ns, stat.st_size)
    return inventory


def _thaw(value: object) -> object:
    if isinstance(value, MappingABC):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def test_plan_is_read_only_and_records_source_digest(tmp_path: Path):
    manifest_path = _write_manifest(tmp_path, _v1_payload())
    before_bytes = manifest_path.read_bytes()
    before_inventory = _inventory(tmp_path)

    plan = plan_project_upgrade(tmp_path)

    assert manifest_path.read_bytes() == before_bytes
    assert _inventory(tmp_path) == before_inventory
    assert plan.manifest_path == manifest_path.resolve()
    assert plan.source_sha256 == sha256(before_bytes).hexdigest()
    assert plan.from_version == 1
    assert plan.to_version == 2


@pytest.mark.parametrize(
    ("origin", "expected_source"),
    [
        ("keil-migration", "keil"),
        ("cubemx", "cubemx"),
        ("manual", "manual"),
        ("custom", "manual"),
    ],
)
def test_plan_maps_origin_to_memory_source(tmp_path: Path, origin: str, expected_source: str):
    _write_manifest(tmp_path, _v1_payload(origin=origin))

    plan = plan_project_upgrade(tmp_path)

    assert plan.proposed["memory"]["source"] == expected_source


def test_plan_applies_exact_v2_defaults_and_preserves_values(tmp_path: Path):
    payload = _v1_payload(origin="keil-migration")
    payload["framework"]["version"] = "1.5.0"
    _write_manifest(tmp_path, payload)

    plan = plan_project_upgrade(tmp_path)
    proposed = plan.proposed

    assert proposed["schemaVersion"] == 2
    assert proposed["generatedBy"] == {"tool": "stm32-toolkit", "version": __version__}
    assert proposed["build"]["presets"] == ()
    assert proposed["memory"] == {"source": "keil", "regions": ()}
    assert proposed["generation"] == {
        "cubeMxIoc": None,
        "managedManifest": ".stm32-toolkit/generated-files.json",
        "generatedDirectories": (),
        "userDirectories": (),
    }
    assert proposed["framework"]["version"] == "1.5.0"
    assert proposed["logicalProjectId"] == payload["logicalProjectId"]
    assert proposed["project"] == payload["project"]
    assert proposed["target"] == payload["target"]
    assert proposed["debug"] == payload["debug"]
    assert proposed["build"]["sources"] == tuple(payload["build"]["sources"])
    assert proposed["build"]["includePaths"] == tuple(payload["build"]["includePaths"])
    assert proposed["build"]["defines"] == tuple(payload["build"]["defines"])
    assert proposed["build"]["compileOptions"] == tuple(payload["build"]["compileOptions"])
    assert proposed["build"]["assemblySources"] == tuple(payload["build"]["assemblySources"])
    assert proposed["build"]["elf"] == payload["build"]["elf"]


def test_plan_omitted_framework_version_becomes_null(tmp_path: Path):
    payload = _v1_payload()
    del payload["framework"]["version"]
    _write_manifest(tmp_path, payload)

    plan = plan_project_upgrade(tmp_path)

    assert plan.proposed["framework"]["version"] is None


def test_proposed_mapping_is_recursively_immutable_and_valid_v2(tmp_path: Path):
    _write_manifest(tmp_path, _v1_payload())
    plan = plan_project_upgrade(tmp_path)

    assert isinstance(plan.proposed, MappingProxyType)
    assert isinstance(plan.proposed["project"], MappingProxyType)
    assert isinstance(plan.proposed["build"]["sources"], tuple)

    with pytest.raises(TypeError):
        plan.proposed["schemaVersion"] = 3
    with pytest.raises(TypeError):
        plan.proposed["project"]["name"] = "tampered"
    with pytest.raises(AttributeError):
        plan.proposed["build"]["sources"].append("tampered.c")

    schema = json.loads(
        resources.files("stm32_toolkit")
        .joinpath("schemas/stm32-project.schema.json")
        .read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = list(validator.iter_errors(_thaw(plan.proposed)))

    assert errors == []


def test_plan_v2_manifest_returns_not_required(tmp_path: Path):
    _write_manifest(tmp_path, _v2_payload())

    with pytest.raises(ProjectUpgradeError) as error:
        plan_project_upgrade(tmp_path)

    assert error.value.code == "PROJECT_UPGRADE_NOT_REQUIRED"
    assert error.value.details == {"schemaVersion": 2}


def test_plan_unsupported_integer_version_returns_stable_error(tmp_path: Path):
    payload = _v1_payload()
    payload["schemaVersion"] = 3
    _write_manifest(tmp_path, payload)

    with pytest.raises(ProjectUpgradeError) as error:
        plan_project_upgrade(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_VERSION_UNSUPPORTED"
    assert error.value.details == {"schemaVersion": 3, "supported": [1, 2]}


def test_plan_boolean_schema_version_returns_stable_error(tmp_path: Path):
    payload = _v1_payload()
    payload["schemaVersion"] = True
    _write_manifest(tmp_path, payload)

    with pytest.raises(ProjectManifestError) as error:
        plan_project_upgrade(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": "schemaVersion", "rule": "type"}


def test_plan_missing_manifest_returns_stable_error(tmp_path: Path):
    with pytest.raises(ProjectManifestError) as error:
        plan_project_upgrade(tmp_path)

    assert error.value.code == "PROJECT_NOT_CONFIGURED"
    assert error.value.details == {"path": MANIFEST_NAME}


def test_plan_malformed_json_returns_stable_error(tmp_path: Path):
    (tmp_path / MANIFEST_NAME).write_text("{", encoding="utf-8")

    with pytest.raises(ProjectManifestError) as error:
        plan_project_upgrade(tmp_path)

    assert error.value.code == "PROJECT_JSON_INVALID"
    assert error.value.details == {"path": "$", "line": 1, "column": 2}


def test_plan_invalid_utf8_returns_stable_error(tmp_path: Path):
    (tmp_path / MANIFEST_NAME).write_bytes(b"\xff")

    with pytest.raises(ProjectManifestError) as error:
        plan_project_upgrade(tmp_path)

    assert error.value.code == "PROJECT_JSON_INVALID"
    assert error.value.details == {"path": "$", "reason": "invalid_utf8"}


def test_plan_non_object_manifest_returns_stable_error(tmp_path: Path):
    (tmp_path / MANIFEST_NAME).write_text("[1, 2, 3]", encoding="utf-8")

    with pytest.raises(ProjectManifestError) as error:
        plan_project_upgrade(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": "$", "rule": "type"}


def test_plan_invalid_v1_manifest_returns_stable_error(tmp_path: Path):
    payload = _v1_payload()
    del payload["build"]
    _write_manifest(tmp_path, payload)

    with pytest.raises(ProjectManifestError) as error:
        plan_project_upgrade(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": "build", "rule": "required"}


def test_apply_success_replaces_atomically_with_expected_digests(tmp_path: Path):
    payload = _v1_payload()
    payload["project"]["name"] = "固件"
    manifest_path = _write_manifest(tmp_path, payload)
    plan = plan_project_upgrade(tmp_path)

    result = apply_project_upgrade(plan)

    assert result.ok is True
    assert result.operation == "project.upgrade"
    assert result.code == "OK"
    assert result.data is not None
    assert result.data["path"] == str(manifest_path.resolve())
    assert result.data["fromVersion"] == 1
    assert result.data["toVersion"] == 2
    assert result.data["sourceSha256"] == plan.source_sha256

    new_bytes = manifest_path.read_bytes()
    assert result.data["resultSha256"] == sha256(new_bytes).hexdigest()
    assert len(result.data["sourceSha256"]) == 64
    assert len(result.data["resultSha256"]) == 64

    text = new_bytes.decode("utf-8")
    assert not text.startswith("\ufeff")
    assert text.endswith("\n")
    assert not text.endswith("\n\n")
    assert "固件" in text

    payload_v2 = json.loads(text)
    assert payload_v2["schemaVersion"] == 2
    assert payload_v2["project"]["name"] == "固件"

    manifest = ProjectManifest.load(tmp_path)
    assert manifest.logical_project_id == UUID("12345678-1234-5678-1234-567812345678")
    assert manifest.framework_type == "spl"

    model = load_project_model(tmp_path)
    assert model.schema_version == 2
    assert model.build.presets == ()
    assert model.memory.source == "manual"

    assert sorted(path.name for path in tmp_path.iterdir()) == [MANIFEST_NAME]


def test_apply_changed_bytes_returns_digest_mismatch_without_writes(tmp_path: Path):
    manifest_path = _write_manifest(tmp_path, _v1_payload())
    plan = plan_project_upgrade(tmp_path)
    changed_bytes = manifest_path.read_bytes() + b" "

    manifest_path.write_bytes(changed_bytes)

    result = apply_project_upgrade(plan)

    assert result.ok is False
    assert result.code == "PROJECT_CHANGED_SINCE_PLAN"
    assert result.details == {
        "path": str(manifest_path.resolve()),
        "expectedSha256": plan.source_sha256,
        "observedSha256": sha256(changed_bytes).hexdigest(),
    }
    assert manifest_path.read_bytes() == changed_bytes
    assert sorted(path.name for path in tmp_path.iterdir()) == [MANIFEST_NAME]


def test_apply_deleted_manifest_returns_missing_evidence(tmp_path: Path):
    manifest_path = _write_manifest(tmp_path, _v1_payload())
    plan = plan_project_upgrade(tmp_path)
    manifest_path.unlink()

    result = apply_project_upgrade(plan)

    assert result.ok is False
    assert result.code == "PROJECT_CHANGED_SINCE_PLAN"
    assert result.details == {
        "path": str(manifest_path.resolve()),
        "expectedSha256": plan.source_sha256,
        "observedSha256": None,
    }
    assert not manifest_path.exists()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(("from_version", "to_version"), [(1, 3), (2, 3), (0, 2), (1, 1)])
def test_apply_invalid_plan_versions_fail_without_writes(
    tmp_path: Path, from_version: int, to_version: int
):
    manifest_path = _write_manifest(tmp_path, _v1_payload())
    plan = plan_project_upgrade(tmp_path)
    original_bytes = manifest_path.read_bytes()
    bad_plan = UpgradePlan(
        manifest_path=plan.manifest_path,
        source_sha256=plan.source_sha256,
        from_version=from_version,
        to_version=to_version,
        proposed=plan.proposed,
    )

    result = apply_project_upgrade(bad_plan)

    assert result.ok is False
    assert result.code == "PROJECT_UPGRADE_PLAN_INVALID"
    assert result.details == {"fromVersion": from_version, "toVersion": to_version}
    assert manifest_path.read_bytes() == original_bytes
    assert sorted(path.name for path in tmp_path.iterdir()) == [MANIFEST_NAME]


def test_apply_invalid_proposed_schema_fails_without_writes(tmp_path: Path):
    manifest_path = _write_manifest(tmp_path, _v1_payload())
    plan = plan_project_upgrade(tmp_path)
    original_bytes = manifest_path.read_bytes()
    tampered = _thaw(plan.proposed)
    del tampered["memory"]
    bad_plan = UpgradePlan(
        manifest_path=plan.manifest_path,
        source_sha256=plan.source_sha256,
        from_version=1,
        to_version=2,
        proposed=tampered,
    )

    result = apply_project_upgrade(bad_plan)

    assert result.ok is False
    assert result.code == "PROJECT_UPGRADE_PLAN_INVALID"
    assert result.details == {"field": "memory", "rule": "required"}
    assert manifest_path.read_bytes() == original_bytes
    assert sorted(path.name for path in tmp_path.iterdir()) == [MANIFEST_NAME]


def test_apply_invalid_proposed_duplicate_regions_fail_without_writes(tmp_path: Path):
    manifest_path = _write_manifest(tmp_path, _v1_payload())
    plan = plan_project_upgrade(tmp_path)
    original_bytes = manifest_path.read_bytes()
    tampered = _thaw(plan.proposed)
    tampered["memory"]["regions"] = [
        {"name": "FLASH", "origin": 0, "length": 1024, "attributes": "r-x"},
        {"name": "FLASH", "origin": 1024, "length": 1024, "attributes": "rw-"},
    ]
    bad_plan = UpgradePlan(
        manifest_path=plan.manifest_path,
        source_sha256=plan.source_sha256,
        from_version=1,
        to_version=2,
        proposed=tampered,
    )

    result = apply_project_upgrade(bad_plan)

    assert result.ok is False
    assert result.code == "PROJECT_UPGRADE_PLAN_INVALID"
    assert result.details == {"field": "memory.regions", "rule": "uniqueRegionName"}
    assert manifest_path.read_bytes() == original_bytes
    assert sorted(path.name for path in tmp_path.iterdir()) == [MANIFEST_NAME]


def _raising_oserror(message: str):
    def raiser(*args, **kwargs):
        raise OSError(message)

    return raiser


def test_apply_temp_write_failure_returns_io_error(tmp_path: Path, monkeypatch):
    manifest_path = _write_manifest(tmp_path, _v1_payload())
    plan = plan_project_upgrade(tmp_path)
    original_bytes = manifest_path.read_bytes()
    monkeypatch.setattr(os, "open", _raising_oserror("injected write failure"))

    result = apply_project_upgrade(plan)

    assert result.ok is False
    assert result.code == "PROJECT_UPGRADE_IO_ERROR"
    assert result.details == {"path": str(manifest_path.resolve()), "stage": "write"}
    assert "injected" not in result.message
    assert "injected" not in str(result.details)
    assert manifest_path.read_bytes() == original_bytes
    assert sorted(path.name for path in tmp_path.iterdir()) == [MANIFEST_NAME]


def test_apply_flush_failure_returns_io_error(tmp_path: Path, monkeypatch):
    manifest_path = _write_manifest(tmp_path, _v1_payload())
    plan = plan_project_upgrade(tmp_path)
    original_bytes = manifest_path.read_bytes()
    monkeypatch.setattr(os, "fsync", _raising_oserror("injected flush failure"))

    result = apply_project_upgrade(plan)

    assert result.ok is False
    assert result.code == "PROJECT_UPGRADE_IO_ERROR"
    assert result.details == {"path": str(manifest_path.resolve()), "stage": "flush"}
    assert "injected" not in result.message
    assert "injected" not in str(result.details)
    assert manifest_path.read_bytes() == original_bytes
    assert sorted(path.name for path in tmp_path.iterdir()) == [MANIFEST_NAME]


def test_apply_replace_failure_returns_io_error_and_cleans_temp(tmp_path: Path, monkeypatch):
    manifest_path = _write_manifest(tmp_path, _v1_payload())
    plan = plan_project_upgrade(tmp_path)
    original_bytes = manifest_path.read_bytes()
    monkeypatch.setattr(os, "replace", _raising_oserror("injected replace failure"))

    result = apply_project_upgrade(plan)

    assert result.ok is False
    assert result.code == "PROJECT_UPGRADE_IO_ERROR"
    assert result.details == {"path": str(manifest_path.resolve()), "stage": "replace"}
    assert "injected" not in result.message
    assert "injected" not in str(result.details)
    assert manifest_path.read_bytes() == original_bytes
    assert sorted(path.name for path in tmp_path.iterdir()) == [MANIFEST_NAME]


def test_apply_cleanup_failure_returns_cleanup_stage(tmp_path: Path, monkeypatch):
    manifest_path = _write_manifest(tmp_path, _v1_payload())
    plan = plan_project_upgrade(tmp_path)
    original_bytes = manifest_path.read_bytes()
    monkeypatch.setattr(os, "replace", _raising_oserror("injected replace failure"))
    monkeypatch.setattr(os, "unlink", _raising_oserror("injected cleanup failure"))

    result = apply_project_upgrade(plan)

    assert result.ok is False
    assert result.code == "PROJECT_UPGRADE_IO_ERROR"
    assert result.details == {"path": str(manifest_path.resolve()), "stage": "cleanup"}
    assert "injected" not in result.message
    assert "injected" not in str(result.details)
    assert manifest_path.read_bytes() == original_bytes


def test_apply_result_never_leaks_exception_or_environment_details(tmp_path: Path):
    manifest_path = _write_manifest(tmp_path, _v1_payload())
    plan = plan_project_upgrade(tmp_path)
    manifest_path.write_bytes(manifest_path.read_bytes() + b" ")

    result = apply_project_upgrade(plan)

    assert result.ok is False
    assert result.code == "PROJECT_CHANGED_SINCE_PLAN"
    rendered = str(result.to_dict())
    assert "Traceback" not in rendered
    # Inspect structured fields directly rather than comparing an unescaped
    # path with str(dict), which renders Windows separators escaped and fails
    # on Windows hosts.
    assert result.details["path"] == str(manifest_path.resolve())
    assert result.details["expectedSha256"] == plan.source_sha256
    assert result.details["observedSha256"] == sha256(
        manifest_path.read_bytes()
    ).hexdigest()


def test_apply_forged_plan_cannot_overwrite_arbitrary_digest_matching_file(
    tmp_path: Path,
):
    target = tmp_path / "notes.txt"
    target_bytes = b"digest-matching arbitrary content, not a manifest\n"
    target.write_bytes(target_bytes)
    forged = UpgradePlan(
        manifest_path=target.resolve(),
        source_sha256=sha256(target_bytes).hexdigest(),
        from_version=1,
        to_version=2,
        proposed={"schemaVersion": 2},
    )

    result = apply_project_upgrade(forged)

    assert result.ok is False
    assert result.code == "PROJECT_UPGRADE_PLAN_INVALID"
    assert result.details == {
        "field": "manifestPath",
        "rule": "canonicalProjectManifest",
    }
    assert target.read_bytes() == target_bytes
    assert sorted(path.name for path in tmp_path.iterdir()) == ["notes.txt"]


def test_apply_forged_plan_rejects_digest_matching_non_v1_manifest(
    tmp_path: Path,
):
    manifest_path = _write_manifest(tmp_path, _v2_payload())
    current_bytes = manifest_path.read_bytes()
    forged = UpgradePlan(
        manifest_path=manifest_path.resolve(),
        source_sha256=sha256(current_bytes).hexdigest(),
        from_version=1,
        to_version=2,
        proposed={},
    )

    result = apply_project_upgrade(forged)

    assert result.ok is False
    assert result.code == "PROJECT_UPGRADE_PLAN_INVALID"
    assert result.details == {"field": "source", "rule": "validSchemaVersion1"}
    assert manifest_path.read_bytes() == current_bytes
    assert sorted(path.name for path in tmp_path.iterdir()) == [MANIFEST_NAME]


def test_apply_forged_plan_rejects_non_object_digest_matching_source(
    tmp_path: Path,
):
    manifest_path = tmp_path / MANIFEST_NAME
    current_bytes = b"[1, 2, 3]"
    manifest_path.write_bytes(current_bytes)
    forged = UpgradePlan(
        manifest_path=manifest_path.resolve(),
        source_sha256=sha256(current_bytes).hexdigest(),
        from_version=1,
        to_version=2,
        proposed={},
    )

    result = apply_project_upgrade(forged)

    assert result.ok is False
    assert result.code == "PROJECT_UPGRADE_PLAN_INVALID"
    assert result.details == {"field": "source", "rule": "validSchemaVersion1"}
    assert manifest_path.read_bytes() == current_bytes
    assert sorted(path.name for path in tmp_path.iterdir()) == [MANIFEST_NAME]


def test_apply_valid_v2_but_nondeterministic_proposal_fails_without_writes(
    tmp_path: Path,
):
    manifest_path = _write_manifest(tmp_path, _v1_payload())
    plan = plan_project_upgrade(tmp_path)
    original_bytes = manifest_path.read_bytes()
    tampered = _thaw(plan.proposed)
    tampered["debug"]["backend"] = "gdb"
    forged = UpgradePlan(
        manifest_path=plan.manifest_path,
        source_sha256=plan.source_sha256,
        from_version=1,
        to_version=2,
        proposed=tampered,
    )

    result = apply_project_upgrade(forged)

    assert result.ok is False
    assert result.code == "PROJECT_UPGRADE_PLAN_INVALID"
    assert result.details == {"field": "proposed", "rule": "deterministicUpgrade"}
    assert manifest_path.read_bytes() == original_bytes
    assert sorted(path.name for path in tmp_path.iterdir()) == [MANIFEST_NAME]
