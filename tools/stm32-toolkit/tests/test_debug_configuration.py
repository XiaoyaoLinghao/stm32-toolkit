"""PY-OCD-DEBUG-CONFIG core tests: shared validation, planning, atomic apply.

Every fixture is an authored synthetic Schema v2/v3 project below ``tmp_path``.
No PyOCD import, probe, network, hardware, original project or installed
runtime is touched.  These tests are the author's slice evidence; the primary
conversation agent runs them independently.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import replace
from pathlib import Path

import pytest

from stm32_toolkit.debug_configuration import (
    DEBUG_CONFIGURATION_INVALID,
    DebugConfiguration,
    DebugConfigurationError,
    describe_debug_configuration,
    normalize_debug_configuration,
)
from stm32_toolkit.generation import (
    GenerationError,
    ManifestEdit,
    apply_project_configuration,
    plan_project_configuration,
)
from stm32_toolkit.generation import configure as configure_mod
from stm32_toolkit.generation.managed_files import (
    FILE_LIMIT_BYTES,
    MANAGED_MANIFEST_PATH,
    model_sha256_for,
    parse_managed_manifest_facts,
    plan_id_for,
    unified_diff,
)
from stm32_toolkit.project_model import (
    ProjectManifestError,
    load_project_model,
    load_project_model_candidate,
)

from test_generation import (
    _redirect_path,
    fail_replace_at,
    sha256,
    standard_payload,
    staging_dir,
    write_project,
)

SOURCE_MANIFEST = ".stm32-project.json"
PAIR = ("pyocd", "stm32f407vg")


def no_debug_payload(**overrides) -> dict:
    payload = standard_payload()
    payload["debug"] = {}
    payload.update(overrides)
    return payload


def schema3_payload() -> dict:
    payload = standard_payload()
    payload["schemaVersion"] = 3
    payload["debug"] = {
        "svd": "docs/device.svd",
        "svdDevice": "STM32F407",
        "readableRegions": [
            {"name": "PERIPH", "origin": 0x40000000, "length": 0x10000},
        ],
    }
    return payload


def fragment_payload() -> dict:
    payload = no_debug_payload()
    payload["memory"] = {
        "source": payload["memory"]["source"],
        "regions": [
            *payload["memory"]["regions"],
            {"name": "CCM", "origin": 0x10000000, "length": 0x10000, "attributes": "rw-"},
        ],
        "layout": {
            "flash": "FLASH",
            "data": "RAM",
            "bss": "RAM",
            "heap": "RAM",
            "stack": "RAM",
        },
    }
    payload["generation"] = {
        **payload["generation"],
        "linkerFragment": "linker/user.ld",
    }
    return payload


def source_path(root: Path) -> Path:
    return root / SOURCE_MANIFEST


def managed_path(root: Path) -> Path:
    return root.joinpath(*MANAGED_MANIFEST_PATH.split("/"))


def content_snapshot(root: Path) -> dict[str, tuple]:
    """Bytes and modes without timestamps, so atomic restore can be compared."""
    snapshot: dict[str, tuple] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            snapshot[relative] = ("link", os.readlink(path))
        elif path.is_file():
            snapshot[relative] = (
                "file",
                stat.S_IMODE(os.lstat(path).st_mode),
                path.read_bytes(),
            )
        elif path.is_dir():
            snapshot[relative] = ("dir",)
    return snapshot


def paired_plan(tmp_path: Path, payload: dict | None = None, target: str = PAIR[1]):
    root = write_project(
        tmp_path / "project",
        no_debug_payload() if payload is None else payload,
    )
    model = load_project_model(root)
    plan = plan_project_configuration(
        model, debug_backend=PAIR[0], debug_target=target
    )
    return root, plan


# ---------------------------------------------------------------------------
# shared pure validation and diagnostics
# ---------------------------------------------------------------------------


def test_no_option_pair_returns_none():
    assert normalize_debug_configuration(None, None) is None


def test_exact_pair_is_accepted_without_coercion():
    configuration = normalize_debug_configuration("pyocd", "stm32f407vg")
    assert configuration == DebugConfiguration(backend="pyocd", target="stm32f407vg")


@pytest.mark.parametrize(
    ("backend", "target", "codes", "missing"),
    [
        ("pyocd", None, ["DEBUG_TARGET_MISSING"], ["debug.target"]),
        (None, "stm32f407vg", ["DEBUG_BACKEND_MISSING"], ["debug.backend"]),
        ("openocd", "stm32f407vg", ["DEBUG_BACKEND_UNSUPPORTED"], []),
        ("pyocd ", "stm32f407vg", ["DEBUG_BACKEND_UNSUPPORTED"], []),
        ("pyocd", " stm32f407vg", ["DEBUG_TARGET_MALFORMED"], []),
        ("pyocd", "", ["DEBUG_TARGET_MALFORMED"], []),
        ("", "stm32f407vg", ["DEBUG_BACKEND_UNSUPPORTED"], []),
        ("pyocd", 7, ["DEBUG_TARGET_MALFORMED"], []),
        (7, "stm32f407vg", ["DEBUG_BACKEND_UNSUPPORTED"], []),
        ("pyocd", "stm32f407vg\n", ["DEBUG_TARGET_MALFORMED"], []),
        ("pyocd", "a" * 129, ["DEBUG_TARGET_MALFORMED"], []),
        (7, 7, ["DEBUG_BACKEND_UNSUPPORTED", "DEBUG_TARGET_MALFORMED"], []),
    ],
)
def test_invalid_or_partial_pair_reports_complete_diagnostics(
    backend, target, codes, missing
):
    with pytest.raises(DebugConfigurationError) as info:
        normalize_debug_configuration(backend, target)
    error = info.value
    assert error.code == DEBUG_CONFIGURATION_INVALID
    assert [entry.code for entry in error.diagnostics] == codes
    assert list(error.missing_fields) == missing
    assert error.details["field"] == error.diagnostics[0].field
    assert error.details["rule"] == error.diagnostics[0].rule
    for entry in error.details["diagnostics"]:
        assert set(entry) == {"code", "field", "rule", "message", "remediation"}
        assert entry["remediation"]


def test_describe_reports_both_missing_fields_together():
    status = describe_debug_configuration(None, None)
    assert status.status == "needs-user-input"
    assert status.backend is None and status.target is None
    assert status.missing_fields == ("debug.backend", "debug.target")
    assert [entry.code for entry in status.diagnostics] == [
        "DEBUG_BACKEND_MISSING",
        "DEBUG_TARGET_MISSING",
    ]
    assert status.target_support == "not-checked"
    assert status.hardware_verified is False
    assert len(status.next_steps) == 2
    payload = status.to_dict()
    assert payload["status"] == "needs-user-input"
    assert payload["missingFields"] == ["debug.backend", "debug.target"]
    assert payload["targetSupport"] == "not-checked"
    assert payload["hardwareVerified"] is False


def test_describe_configured_pair_is_metadata_only():
    status = describe_debug_configuration("pyocd", "stm32f407vg")
    assert status.status == "configured"
    assert status.missing_fields == ()
    assert status.diagnostics == ()
    assert status.target_support == "not-checked"
    assert status.hardware_verified is False


def test_describe_echoes_only_string_values():
    status = describe_debug_configuration("openocd", 5)
    assert status.status == "needs-user-input"
    assert status.backend == "openocd"
    assert status.target is None
    assert [entry.code for entry in status.diagnostics] == [
        "DEBUG_BACKEND_UNSUPPORTED",
        "DEBUG_TARGET_MALFORMED",
    ]


# ---------------------------------------------------------------------------
# planning: legacy compatibility and the explicit pair
# ---------------------------------------------------------------------------


def test_no_option_plan_keeps_the_historical_shape_and_writes_nothing(tmp_path):
    root = write_project(tmp_path / "project", no_debug_payload())
    model = load_project_model(root)
    before = content_snapshot(root)
    plan = plan_project_configuration(model)
    assert plan.debug_configuration is None
    assert plan.manifest_edit is None
    assert set(plan.to_dict()) == {
        "plan_version",
        "plan_id",
        "model_sha256",
        "inputs",
        "files",
        "blockers",
        "managed_manifest_path",
    }
    assert plan.model_sha256 == model_sha256_for(model)
    assert plan.plan_id == plan_id_for(plan)
    assert content_snapshot(root) == before


def test_no_option_plan_accepts_schema3(tmp_path):
    root = write_project(tmp_path / "project", schema3_payload())
    plan = plan_project_configuration(load_project_model(root))
    assert plan.model.schema_version == 3
    assert plan.debug_configuration is None and plan.manifest_edit is None
    assert plan.model.debug.svd == "docs/device.svd"


def test_paired_plan_records_source_before_and_candidate_after(tmp_path):
    root = write_project(tmp_path / "project", no_debug_payload())
    source_bytes = source_path(root).read_bytes()
    before_payload = json.loads(source_bytes.decode("utf-8"))
    plan = plan_project_configuration(
        load_project_model(root), debug_backend="pyocd", debug_target="stm32f407vg"
    )
    edit = plan.manifest_edit
    assert plan.debug_configuration == DebugConfiguration("pyocd", "stm32f407vg")
    assert edit.path == SOURCE_MANIFEST
    assert edit.status == "update"
    assert edit.before_bytes == source_bytes
    assert edit.before_sha256 == sha256(source_bytes)
    assert edit.before_size == len(source_bytes)
    assert edit.after_bytes != source_bytes
    assert edit.after_sha256 == sha256(edit.after_bytes)
    assert edit.after_size == len(edit.after_bytes)
    assert '"backend": "pyocd"' in edit.unified_diff
    assert '"target": "stm32f407vg"' in edit.unified_diff
    after_payload = json.loads(edit.after_bytes.decode("utf-8"))
    assert after_payload["debug"] == {"backend": "pyocd", "target": "stm32f407vg"}
    expected = json.loads(json.dumps(before_payload))
    expected["debug"] = {"backend": "pyocd", "target": "stm32f407vg"}
    assert after_payload == expected
    inputs = {entry.path: entry for entry in plan.inputs}
    assert inputs[SOURCE_MANIFEST].sha256 == edit.before_sha256
    assert inputs[SOURCE_MANIFEST].size == edit.before_size
    assert plan.model.debug.backend == "pyocd"
    assert plan.model.debug.target == "stm32f407vg"
    assert plan.model_sha256 == model_sha256_for(plan.model)
    assert plan.plan_id == plan_id_for(plan)
    payload = plan.to_dict()
    assert payload["debug_configuration"] == {
        "backend": "pyocd",
        "target": "stm32f407vg",
    }
    assert payload["manifest_edit"]["before_sha256"] == edit.before_sha256
    assert "before_bytes" not in payload["manifest_edit"]
    assert "after_bytes" not in payload["manifest_edit"]
    assert source_path(root).read_bytes() == source_bytes


def test_pair_edit_preserves_unrelated_svd_and_memory_fields(tmp_path):
    payload = schema3_payload()
    root = write_project(tmp_path / "project", payload)
    before = json.loads(source_path(root).read_text("utf-8"))
    plan = plan_project_configuration(
        load_project_model(root), debug_backend="pyocd", debug_target="stm32f411xe"
    )
    after = json.loads(plan.manifest_edit.after_bytes.decode("utf-8"))
    assert after["debug"]["backend"] == "pyocd"
    assert after["debug"]["target"] == "stm32f411xe"
    assert after["debug"]["svd"] == before["debug"]["svd"]
    assert after["debug"]["svdDevice"] == before["debug"]["svdDevice"]
    assert after["debug"]["readableRegions"] == before["debug"]["readableRegions"]
    for key in (
        "schemaVersion",
        "logicalProjectId",
        "generatedBy",
        "project",
        "target",
        "framework",
        "build",
        "memory",
        "generation",
    ):
        assert after[key] == before[key]
    svd = root.joinpath("docs", "device.svd")
    svd_bytes = svd.read_bytes()
    assert apply_project_configuration(plan).ok
    assert svd.read_bytes() == svd_bytes
    reloaded = load_project_model(root)
    assert reloaded.debug.svd == "docs/device.svd"
    assert reloaded.debug.svd_device == "STM32F407"
    assert len(reloaded.debug.readable_regions) == 1


def test_paired_plan_is_deterministic(tmp_path):
    root, plan = paired_plan(tmp_path)
    again = plan_project_configuration(
        load_project_model(root), debug_backend=PAIR[0], debug_target=PAIR[1]
    )
    assert again.to_dict() == plan.to_dict()
    assert again.plan_id == plan.plan_id
    assert again.manifest_edit == plan.manifest_edit


def test_same_value_pair_preserves_exact_source_bytes(tmp_path):
    root = write_project(tmp_path / "project", standard_payload())
    raw = source_path(root).read_bytes()
    model = load_project_model(root)
    plan = plan_project_configuration(
        model, debug_backend="pyocd", debug_target="stm32f407vg"
    )
    edit = plan.manifest_edit
    assert edit.status == "unchanged"
    assert edit.before_bytes == raw and edit.after_bytes == raw
    assert edit.before_sha256 == edit.after_sha256
    assert edit.unified_diff == ""
    assert plan.model_sha256 == model_sha256_for(model)
    result = apply_project_configuration(plan)
    assert result.ok
    assert result.data["manifestEditStatus"] == "unchanged"
    assert source_path(root).read_bytes() == raw


def test_plan_never_writes_the_candidate(tmp_path):
    root = write_project(tmp_path / "project", no_debug_payload())
    before = content_snapshot(root)
    plan = plan_project_configuration(
        load_project_model(root), debug_backend="pyocd", debug_target="stm32f407vg"
    )
    assert plan.manifest_edit.after_bytes != source_path(root).read_bytes()
    assert content_snapshot(root) == before


@pytest.mark.parametrize(
    ("backend", "target"),
    [
        ("pyocd", None),
        (None, "stm32f407vg"),
        ("openocd", "stm32f407vg"),
        ("pyocd", "bad target"),
        (1, "stm32f407vg"),
        ("pyocd", "stm32f407vg "),
    ],
)
def test_core_refuses_invalid_pair_before_any_write(tmp_path, backend, target):
    root = write_project(tmp_path / "project", no_debug_payload())
    model = load_project_model(root)
    before = content_snapshot(root)
    with pytest.raises(GenerationError) as info:
        plan_project_configuration(model, debug_backend=backend, debug_target=target)
    assert info.value.code == DEBUG_CONFIGURATION_INVALID
    assert info.value.details["diagnostics"]
    assert content_snapshot(root) == before


# ---------------------------------------------------------------------------
# apply: paired-route success, identity and idempotence
# ---------------------------------------------------------------------------


def test_apply_writes_manifest_and_managed_identity_in_one_route(tmp_path):
    root, plan = paired_plan(tmp_path)
    before = source_path(root).read_bytes()
    result = apply_project_configuration(plan)
    assert result.ok
    assert result.data["manifestEditPath"] == SOURCE_MANIFEST
    assert result.data["manifestEditStatus"] == "update"
    assert SOURCE_MANIFEST in result.data["updatedPaths"]
    assert source_path(root).read_bytes() == plan.manifest_edit.after_bytes
    assert source_path(root).read_bytes() != before
    model_after = load_project_model(root)
    assert (model_after.debug.backend, model_after.debug.target) == PAIR
    assert model_sha256_for(model_after) == plan.model_sha256
    facts = parse_managed_manifest_facts(managed_path(root).read_bytes())
    assert facts.project_manifest_sha256 == plan.model_sha256
    assert SOURCE_MANIFEST not in {record.path for record in facts.records}
    replan = plan_project_configuration(
        model_after, debug_backend=PAIR[0], debug_target=PAIR[1]
    )
    assert replan.manifest_edit.status == "unchanged"
    assert replan.model_sha256 == plan.model_sha256


# ---------------------------------------------------------------------------
# apply: stale, omitted, tampered plans
# ---------------------------------------------------------------------------


def test_apply_refuses_stale_source_without_writes(tmp_path):
    root, plan = paired_plan(tmp_path)
    payload = json.loads(source_path(root).read_text("utf-8"))
    payload["project"]["name"] = "renamed"
    source_path(root).write_bytes(
        json.dumps(payload, indent=2).encode("utf-8") + b"\n"
    )
    before = content_snapshot(root)
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_INPUT_CHANGED"
    assert content_snapshot(root) == before
    assert not staging_dir(root, plan.plan_id).exists()


def test_edit_route_respects_generated_file_drift(tmp_path):
    root = write_project(tmp_path / "project", no_debug_payload())
    model = load_project_model(root)
    assert apply_project_configuration(plan_project_configuration(model)).ok
    (root / "CMakeLists.txt").write_bytes(b"user edited\n")
    model = load_project_model(root)
    plan = plan_project_configuration(
        model, debug_backend=PAIR[0], debug_target=PAIR[1]
    )
    assert any(
        blocker.code == "GENERATED_FILE_DRIFT" for blocker in plan.blockers
    )
    before = content_snapshot(root)
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATED_FILE_DRIFT"
    assert content_snapshot(root) == before


def test_apply_refuses_a_plan_missing_one_optional_field(tmp_path):
    root, plan = paired_plan(tmp_path)
    before = content_snapshot(root)
    for mutated in (
        replace(plan, debug_configuration=None),
        replace(plan, manifest_edit=None),
    ):
        result = apply_project_configuration(mutated)
        assert not result.ok
        assert result.code == "GENERATION_PLAN_INVALID"
        assert result.details["rule"] == "debugConfiguration"
    assert content_snapshot(root) == before


def test_apply_refuses_dropping_both_optional_fields(tmp_path):
    root, plan = paired_plan(tmp_path)
    stripped = replace(plan, debug_configuration=None, manifest_edit=None)
    stripped = replace(stripped, plan_id=plan_id_for(stripped))
    before = content_snapshot(root)
    result = apply_project_configuration(stripped)
    assert not result.ok
    assert result.code == "GENERATION_INPUT_CHANGED"
    assert content_snapshot(root) == before


def test_apply_refuses_a_forged_edit_from_another_pair(tmp_path):
    root = write_project(tmp_path / "project", no_debug_payload())
    model = load_project_model(root)
    plan_a = plan_project_configuration(
        model, debug_backend="pyocd", debug_target="stm32f407vg"
    )
    plan_b = plan_project_configuration(
        model, debug_backend="pyocd", debug_target="stm32f411xe"
    )
    forged = replace(plan_a, manifest_edit=plan_b.manifest_edit)
    forged = replace(forged, plan_id=plan_id_for(forged))
    before = content_snapshot(root)
    result = apply_project_configuration(forged)
    assert not result.ok
    assert result.code == "GENERATION_PLAN_INVALID"
    assert result.details["rule"] == "manifestEdit"
    assert content_snapshot(root) == before


def test_apply_refuses_extra_candidate_changes_even_with_recomputed_id(tmp_path):
    root = write_project(tmp_path / "project", no_debug_payload())
    model = load_project_model(root)
    plan = plan_project_configuration(
        model, debug_backend="pyocd", debug_target="stm32f407vg"
    )
    before = source_path(root).read_bytes()
    payload = json.loads(before.decode("utf-8"))
    payload["project"]["name"] = "renamed"
    payload["debug"] = {"backend": "pyocd", "target": "stm32f407vg"}
    after = json.dumps(payload, indent=2).encode("utf-8") + b"\n"
    forged_edit = ManifestEdit(
        path=SOURCE_MANIFEST,
        status="update",
        before_sha256=sha256(before),
        after_sha256=sha256(after),
        before_size=len(before),
        after_size=len(after),
        unified_diff=unified_diff(
            SOURCE_MANIFEST,
            before.decode("utf-8"),
            after.decode("utf-8"),
        ),
        before_bytes=before,
        after_bytes=after,
    )
    forged = replace(plan, manifest_edit=forged_edit)
    forged = replace(forged, plan_id=plan_id_for(forged))
    before_tree = content_snapshot(root)
    result = apply_project_configuration(forged)
    assert not result.ok
    assert result.code == "GENERATION_PLAN_INVALID"
    assert result.details["rule"] == "manifestEdit"
    assert content_snapshot(root) == before_tree


def test_apply_refuses_a_forged_unified_diff(tmp_path):
    root, plan = paired_plan(tmp_path)
    before = content_snapshot(root)
    forged_edit = replace(
        plan.manifest_edit,
        unified_diff="--- a/.stm32-project.json\n+++ b/.stm32-project.json\n",
    )
    forged = replace(plan, manifest_edit=forged_edit)
    forged = replace(forged, plan_id=plan_id_for(forged))
    result = apply_project_configuration(forged)
    assert not result.ok
    assert result.code == "GENERATION_PLAN_INVALID"
    assert result.details["rule"] == "manifestEdit"
    assert content_snapshot(root) == before


def test_apply_refuses_a_tampered_candidate_digest(tmp_path):
    root, plan = paired_plan(tmp_path)
    before = content_snapshot(root)
    edit = plan.manifest_edit
    forged_edit = replace(edit, after_sha256="0" * 64)
    forged = replace(plan, manifest_edit=forged_edit)
    forged = replace(forged, plan_id=plan_id_for(forged))
    result = apply_project_configuration(forged)
    assert not result.ok
    assert result.code == "GENERATION_PLAN_INVALID"
    assert result.details["rule"] == "manifestEdit"
    assert content_snapshot(root) == before


# ---------------------------------------------------------------------------
# apply: rollback covers the user-owned manifest
# ---------------------------------------------------------------------------


def test_rollback_restores_manifest_after_a_later_replace_failure(
    monkeypatch, tmp_path
):
    root, plan = paired_plan(tmp_path)
    before = content_snapshot(root)
    # Destinations are sorted: 1 = .stm32-project.json, 2 = managed manifest,
    # 3 = the first generated target.  Failing at 3 forces rollback of both
    # already-replaced user-owned and managed files.
    fail_replace_at(monkeypatch, {3})
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_APPLY_FAILED"
    assert result.details["phase"] == "replace"
    assert content_snapshot(root) == before
    assert not staging_dir(root, plan.plan_id).exists()


def test_rollback_restores_manifest_after_a_chmod_failure(monkeypatch, tmp_path):
    root, plan = paired_plan(tmp_path)
    before = content_snapshot(root)
    manifest_target = os.path.normcase(str(source_path(root).resolve()))
    original_chmod = os.chmod
    calls: list[str] = []

    def wrapper(path, mode):
        normalized = os.path.normcase(str(path))
        calls.append(normalized)
        if normalized == manifest_target:
            raise OSError("injected chmod failure")
        return original_chmod(path, mode)

    monkeypatch.setattr(configure_mod.os, "chmod", wrapper)
    result = apply_project_configuration(plan)
    assert not result.ok
    assert result.code == "GENERATION_APPLY_FAILED"
    assert result.details["phase"] == "replace"
    assert manifest_target in calls
    assert content_snapshot(root) == before
    assert not staging_dir(root, plan.plan_id).exists()


# ---------------------------------------------------------------------------
# fail-closed editing-route source reads
# ---------------------------------------------------------------------------


def test_plan_refuses_a_duplicate_key_manifest(tmp_path):
    root = write_project(tmp_path / "project", no_debug_payload())
    text = json.dumps(no_debug_payload(), indent=2)
    needle = '"debug": {}'
    assert needle in text
    text = text.replace(needle, '"debug": {"backend": "pyocd"}, "debug": {}', 1)
    source_path(root).write_bytes(text.encode("utf-8") + b"\n")
    model = load_project_model(root)
    with pytest.raises(GenerationError) as info:
        plan_project_configuration(
            model, debug_backend="pyocd", debug_target="stm32f407vg"
        )
    assert info.value.code == "GENERATION_MODEL_INVALID"


def test_plan_refuses_a_nonregular_manifest(tmp_path):
    root = write_project(tmp_path / "project", no_debug_payload())
    model = load_project_model(root)
    source_path(root).unlink()
    source_path(root).mkdir()
    with pytest.raises(GenerationError) as info:
        plan_project_configuration(
            model, debug_backend="pyocd", debug_target="stm32f407vg"
        )
    assert info.value.code == "GENERATION_MODEL_INVALID"
    assert info.value.details["rule"] == "regularFile"


def test_plan_refuses_a_redirecting_manifest(monkeypatch, tmp_path):
    root = write_project(tmp_path / "project", no_debug_payload())
    model = load_project_model(root)
    outside = tmp_path / "outside.json"
    source_path(root).rename(outside)
    _redirect_path(monkeypatch, source_path(root), outside, False)
    with pytest.raises(GenerationError) as info:
        plan_project_configuration(
            model, debug_backend="pyocd", debug_target="stm32f407vg"
        )
    assert info.value.code == "GENERATION_INPUT_INVALID"
    assert info.value.details["rule"] == "redirect"


def test_plan_refuses_an_oversize_manifest(tmp_path):
    root = write_project(tmp_path / "project", no_debug_payload())
    model = load_project_model(root)
    source_path(root).write_bytes(b"{" + b" " * (FILE_LIMIT_BYTES + 1) + b"}")
    with pytest.raises(GenerationError) as info:
        plan_project_configuration(
            model, debug_backend="pyocd", debug_target="stm32f407vg"
        )
    assert info.value.code == "GENERATION_INPUT_INVALID"
    assert info.value.details["rule"] == "size"


def test_candidate_seam_rejects_duplicate_keys(tmp_path):
    root = write_project(tmp_path / "project", no_debug_payload())
    raw = source_path(root).read_bytes()
    text = raw.decode("utf-8").replace(
        '"debug": {}', '"debug": {"backend": "pyocd"}, "debug": {}', 1
    )
    with pytest.raises(ProjectManifestError) as info:
        load_project_model_candidate(root, text.encode("utf-8"))
    assert info.value.code == "PROJECT_JSON_INVALID"


def test_candidate_seam_matches_the_disk_model(tmp_path):
    root = write_project(tmp_path / "project", no_debug_payload())
    raw = source_path(root).read_bytes()
    assert model_sha256_for(load_project_model_candidate(root, raw)) == model_sha256_for(
        load_project_model(root)
    )


# ---------------------------------------------------------------------------
# linker-fragment coexistence
# ---------------------------------------------------------------------------


FRAGMENT_TEXT = (
    "/* Authored synthetic fragment: no vendor or board facts. */\n"
    ".sram2 0x20000000 (NOLOAD) :\n"
    "{\n"
    "  . = ALIGN(8);\n"
    "  *(.sram2 .sram2.*)\n"
    "} > RAM\n"
    "\n"
    ".sram3 (NOLOAD) :\n"
    "{\n"
    "  KEEP(*(.sram3.*))\n"
    "} > CCM\n"
)


def test_pair_edit_coexists_with_a_linker_fragment(tmp_path):
    payload = fragment_payload()
    root = write_project(tmp_path / "project", payload)
    fragment = root.joinpath("linker", "user.ld")
    fragment.parent.mkdir(parents=True, exist_ok=True)
    fragment.write_text(FRAGMENT_TEXT, encoding="utf-8")
    fragment_bytes = fragment.read_bytes()
    model = load_project_model(root)
    plan = plan_project_configuration(
        model, debug_backend="pyocd", debug_target="stm32f407vg"
    )
    assert any(entry.path == "linker/user.ld" for entry in plan.inputs)
    after = json.loads(plan.manifest_edit.after_bytes.decode("utf-8"))
    assert after["generation"]["linkerFragment"] == "linker/user.ld"
    assert after["memory"] == payload["memory"]
    result = apply_project_configuration(plan)
    assert result.ok
    assert fragment.read_bytes() == fragment_bytes
    facts = parse_managed_manifest_facts(managed_path(root).read_bytes())
    assert facts.linker_fragment_path == "linker/user.ld"
    assert facts.linker_fragment_sha256 == sha256(fragment_bytes)
    model_after = load_project_model(root)
    assert (model_after.debug.backend, model_after.debug.target) == PAIR
    assert model_after.generation.linker_fragment is not None
    assert model_after.generation.linker_fragment.sha256 == sha256(fragment_bytes)
    linker = root.joinpath("linker", "stm32tk.ld").read_text("utf-8")
    assert ".sram2" in linker and ".sram3" in linker


# ---------------------------------------------------------------------------
# accidental surface checks
# ---------------------------------------------------------------------------


def test_source_manifest_is_never_a_generated_target_or_managed_record(tmp_path):
    root, plan = paired_plan(tmp_path)
    assert all(entry.path != SOURCE_MANIFEST for entry in plan.files)
    result = apply_project_configuration(plan)
    assert result.ok
    facts = parse_managed_manifest_facts(managed_path(root).read_bytes())
    assert SOURCE_MANIFEST not in {record.path for record in facts.records}
