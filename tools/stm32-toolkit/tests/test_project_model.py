from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, fields
from importlib import resources
from pathlib import Path
from uuid import UUID

import pytest

from stm32_toolkit import __version__
from stm32_toolkit.project import ProjectManifest, ProjectManifestError
from stm32_toolkit.project_model import (
    BuildSpec,
    DebugSpec,
    FrameworkSpec,
    GenerationSpec,
    MemoryRegion,
    MemorySpec,
    ProjectInfo,
    ProjectModel,
    TargetSpec,
    load_project_model,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
V1_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "valid-project.json"


def _v1_payload() -> dict:
    return json.loads(V1_FIXTURE.read_text(encoding="utf-8"))


def _v2_payload() -> dict:
    return {
        "schemaVersion": 2,
        "logicalProjectId": "12345678-1234-5678-1234-567812345678",
        "generatedBy": {"tool": "stm32-toolkit", "version": __version__},
        "project": {"name": "firmware", "origin": "manual"},
        "target": {
            "device": "STM32F429ZGTx",
            "core": "cortex-m4",
            "fpu": "fpv4-sp-d16",
            "floatAbi": "hard",
            "devicePack": "Keil.STM32F4xx_DFP.2.16.0",
        },
        "framework": {"type": "hal", "version": "1.11.0"},
        "build": {
            "sources": ["App/main.c", "Core/main.c"],
            "includePaths": ["App", "Core/Inc"],
            "defines": ["USE_HAL_DRIVER", "STM32F429xx"],
            "compileOptions": ["-O2"],
            "assemblySources": ["Startup/startup.s"],
            "presets": ["debug", "release"],
            "elf": "build-fw/firmware.elf",
        },
        "memory": {
            "source": "manual",
            "regions": [
                {"name": "FLASH", "origin": 134217728, "length": 2097152, "attributes": "r-x"},
                {"name": "RAM", "origin": 536870912, "length": 262144, "attributes": "rwx"},
            ],
        },
        "debug": {"backend": "pyocd", "target": "stm32f429zgtx", "svd": "STM32F429.svd"},
        "generation": {
            "cubeMxIoc": "firmware.ioc",
            "managedManifest": ".stm32-toolkit/generated-files.json",
            "generatedDirectories": ["Core", "Drivers"],
            "userDirectories": ["App", "User"],
        },
    }


def _write_manifest(tmp_path: Path, payload: dict) -> Path:
    manifest_path = tmp_path / ".stm32-project.json"
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return manifest_path


def _set_path(payload: dict, field: str, value: object) -> None:
    """Set a dotted JSON path such as 'build.sources[0]' in place."""
    head, _, tail = field.partition("[")
    parts = head.split(".")
    container = payload
    if tail:
        for part in parts:
            container = container[part]
        container[int(tail[:-1])] = value
    else:
        for part in parts[:-1]:
            container = container[part]
        container[parts[-1]] = value


def test_v1_load_returns_frozen_compatibility_model(tmp_path: Path):
    manifest_path = _write_manifest(tmp_path, _v1_payload())
    before_bytes = manifest_path.read_bytes()
    before_mtime = manifest_path.stat().st_mtime_ns

    model = load_project_model(tmp_path)

    assert isinstance(model, ProjectModel)
    assert model.project_root == tmp_path.resolve()
    assert model.schema_version == 1
    assert model.logical_project_id == UUID("12345678-1234-5678-1234-567812345678")
    assert model.project == ProjectInfo(name="firmware", origin="manual")
    assert model.target == TargetSpec("STM32F429ZGTx", "cortex-m4", None, None, None)
    assert model.framework == FrameworkSpec(type="spl", version=None)
    assert model.build == BuildSpec(
        sources=("App/main.c",),
        include_paths=(),
        defines=(),
        compile_options=(),
        assembly_sources=(),
        presets=(),
        elf="build-fw/firmware.elf",
    )
    assert model.memory == MemorySpec(source="manual", regions=())
    assert model.debug == DebugSpec(backend="pyocd", target="stm32f429zgtx", svd=None)
    assert model.generation == GenerationSpec(
        tool="stm32-toolkit",
        version=__version__,
        cube_mx_ioc=None,
        managed_manifest=".stm32-toolkit/generated-files.json",
        generated_directories=(),
        user_directories=(),
    )

    assert manifest_path.read_bytes() == before_bytes
    assert manifest_path.stat().st_mtime_ns == before_mtime


@pytest.mark.parametrize(
    ("origin", "expected_source"),
    [
        ("keil-migration", "keil"),
        ("cubemx", "cubemx"),
        ("manual", "manual"),
        ("custom", "manual"),
    ],
)
def test_v1_model_maps_origin_to_memory_source(tmp_path: Path, origin: str, expected_source: str):
    payload = _v1_payload()
    payload["project"]["origin"] = origin

    _write_manifest(tmp_path, payload)

    model = load_project_model(tmp_path)
    assert model.schema_version == 1
    assert model.memory.source == expected_source
    assert model.memory.regions == ()


def test_v2_load_returns_exact_frozen_model(tmp_path: Path):
    _write_manifest(tmp_path, _v2_payload())

    model = load_project_model(tmp_path)

    assert model.project_root == tmp_path.resolve()
    assert model.schema_version == 2
    assert model.logical_project_id == UUID("12345678-1234-5678-1234-567812345678")
    assert model.project == ProjectInfo(name="firmware", origin="manual")
    assert model.target == TargetSpec(
        device="STM32F429ZGTx",
        core="cortex-m4",
        fpu="fpv4-sp-d16",
        float_abi="hard",
        device_pack="Keil.STM32F4xx_DFP.2.16.0",
    )
    assert model.framework == FrameworkSpec(type="hal", version="1.11.0")
    assert model.build == BuildSpec(
        sources=("App/main.c", "Core/main.c"),
        include_paths=("App", "Core/Inc"),
        defines=("USE_HAL_DRIVER", "STM32F429xx"),
        compile_options=("-O2",),
        assembly_sources=("Startup/startup.s",),
        presets=("debug", "release"),
        elf="build-fw/firmware.elf",
    )
    assert model.memory == MemorySpec(
        source="manual",
        regions=(
            MemoryRegion(name="FLASH", origin=134217728, length=2097152, attributes="r-x"),
            MemoryRegion(name="RAM", origin=536870912, length=262144, attributes="rwx"),
        ),
    )
    assert model.debug == DebugSpec(backend="pyocd", target="stm32f429zgtx", svd="STM32F429.svd")
    assert model.generation == GenerationSpec(
        tool="stm32-toolkit",
        version=__version__,
        cube_mx_ioc="firmware.ioc",
        managed_manifest=".stm32-toolkit/generated-files.json",
        generated_directories=("Core", "Drivers"),
        user_directories=("App", "User"),
    )


def test_all_model_containers_reject_mutation(tmp_path: Path):
    _write_manifest(tmp_path, _v2_payload())
    model = load_project_model(tmp_path)

    instances = [
        model,
        model.project,
        model.target,
        model.framework,
        model.build,
        model.memory,
        model.debug,
        model.generation,
        model.memory.regions[0],
    ]
    for instance in instances:
        for field in fields(instance):
            with pytest.raises(FrozenInstanceError):
                setattr(instance, field.name, None)

    tuples = [
        model.build.sources,
        model.build.include_paths,
        model.build.defines,
        model.build.compile_options,
        model.build.assembly_sources,
        model.build.presets,
        model.memory.regions,
        model.generation.generated_directories,
        model.generation.user_directories,
    ]
    for container in tuples:
        with pytest.raises(AttributeError):
            container.append("extra")
        with pytest.raises(TypeError):
            container[0] = "extra"


def test_root_and_packaged_v1_schemas_are_json_equivalent():
    root_schema = REPO_ROOT / "schemas" / "stm32-project-v1.schema.json"
    packaged_schema = resources.files("stm32_toolkit").joinpath(
        "schemas/stm32-project-v1.schema.json"
    )

    assert json.loads(root_schema.read_text(encoding="utf-8")) == json.loads(
        packaged_schema.read_text(encoding="utf-8")
    )


def test_root_and_packaged_v2_schemas_are_json_equivalent():
    root_schema = REPO_ROOT / "schemas" / "stm32-project.schema.json"
    packaged_schema = resources.files("stm32_toolkit").joinpath(
        "schemas/stm32-project.schema.json"
    )

    assert json.loads(root_schema.read_text(encoding="utf-8")) == json.loads(
        packaged_schema.read_text(encoding="utf-8")
    )


def test_missing_schema_version_returns_stable_error(tmp_path: Path):
    payload = _v2_payload()
    del payload["schemaVersion"]
    _write_manifest(tmp_path, payload)

    with pytest.raises(ProjectManifestError) as error:
        load_project_model(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": "schemaVersion", "rule": "required"}


def test_non_object_manifest_returns_stable_error(tmp_path: Path):
    (tmp_path / ".stm32-project.json").write_text("[1, 2, 3]", encoding="utf-8")

    with pytest.raises(ProjectManifestError) as error:
        load_project_model(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": "$", "rule": "type"}


def test_nonexistent_project_root_returns_not_configured_error(tmp_path: Path):
    missing_root = tmp_path / "missing-project"

    with pytest.raises(ProjectManifestError) as error:
        load_project_model(missing_root)

    assert error.value.code == "PROJECT_NOT_CONFIGURED"
    assert error.value.details == {"path": str(missing_root)}


def test_project_root_file_returns_not_configured_error_for_model(tmp_path: Path):
    project_file = tmp_path / "not-a-directory"
    project_file.write_text("content", encoding="utf-8")

    with pytest.raises(ProjectManifestError) as error:
        load_project_model(project_file)

    assert error.value.code == "PROJECT_NOT_CONFIGURED"
    assert error.value.details == {"path": str(project_file)}


def test_invalid_utf8_manifest_returns_stable_json_error_for_model(tmp_path: Path):
    (tmp_path / ".stm32-project.json").write_bytes(b"\xff")

    with pytest.raises(ProjectManifestError) as error:
        load_project_model(tmp_path)

    assert error.value.code == "PROJECT_JSON_INVALID"
    assert error.value.details == {"path": "$", "reason": "invalid_utf8"}


@pytest.mark.parametrize("bad_version", [True, "1", 1.0, 2.0])
def test_non_integer_schema_version_returns_type_error(tmp_path: Path, bad_version):
    payload = _v2_payload()
    payload["schemaVersion"] = bad_version
    _write_manifest(tmp_path, payload)

    with pytest.raises(ProjectManifestError) as error:
        load_project_model(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": "schemaVersion", "rule": "type"}


def test_unsupported_integer_schema_version_returns_stable_error(tmp_path: Path):
    payload = _v2_payload()
    payload["schemaVersion"] = 3
    _write_manifest(tmp_path, payload)

    with pytest.raises(ProjectManifestError) as error:
        load_project_model(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_VERSION_UNSUPPORTED"
    assert error.value.details == {"schemaVersion": 3, "supported": [1, 2]}


def test_unknown_top_level_property_returns_stable_error(tmp_path: Path):
    payload = _v2_payload()
    payload["watchGroups"] = []
    _write_manifest(tmp_path, payload)

    with pytest.raises(ProjectManifestError) as error:
        load_project_model(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": "watchGroups", "rule": "additionalProperties"}


def test_duplicate_memory_region_names_are_rejected(tmp_path: Path):
    payload = _v2_payload()
    payload["memory"]["regions"] = [
        {"name": "FLASH", "origin": 0, "length": 1024, "attributes": "r-x"},
        {"name": "FLASH", "origin": 1024, "length": 1024, "attributes": "rw-"},
    ]
    _write_manifest(tmp_path, payload)

    with pytest.raises(ProjectManifestError) as error:
        load_project_model(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": "memory.regions", "rule": "uniqueRegionName"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("build.sources[0]", "/etc/passwd"),
        ("build.includePaths[0]", "/opt/arm/include"),
        ("build.assemblySources[0]", "/tmp/startup.s"),
        ("build.elf", "/opt/tools/firmware.elf"),
        ("debug.svd", "/opt/keil/chip.svd"),
        ("generation.cubeMxIoc", "/etc/firmware.ioc"),
        ("generation.managedManifest", "/etc/generated-files.json"),
        ("generation.generatedDirectories[0]", "/tmp/generated"),
        ("generation.userDirectories[0]", "/tmp/user"),
    ],
)
def test_posix_absolute_paths_are_rejected(tmp_path: Path, field: str, value: str):
    payload = _v2_payload()
    _set_path(payload, field, value)
    _write_manifest(tmp_path, payload)

    with pytest.raises(ProjectManifestError) as error:
        load_project_model(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": field, "rule": "pathWithinProjectRoot"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("build.sources[0]", "C:\\outside\\main.c"),
        ("build.includePaths[0]", "C:/outside/include"),
        ("build.assemblySources[0]", "D:\\outside\\startup.s"),
        ("build.elf", "C:\\outside\\firmware.elf"),
        ("debug.svd", "C:\\outside\\chip.svd"),
        ("generation.cubeMxIoc", "C:\\outside\\firmware.ioc"),
        ("generation.managedManifest", "C:\\outside\\generated-files.json"),
        ("generation.generatedDirectories[0]", "C:\\outside\\generated"),
        ("generation.userDirectories[0]", "C:\\outside\\user"),
    ],
)
def test_windows_drive_absolute_paths_are_rejected_on_posix_hosts(
    tmp_path: Path, field: str, value: str
):
    payload = _v2_payload()
    _set_path(payload, field, value)
    _write_manifest(tmp_path, payload)

    with pytest.raises(ProjectManifestError) as error:
        load_project_model(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": field, "rule": "pathWithinProjectRoot"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("build.sources[0]", "\\\\server\\share\\main.c"),
        ("build.includePaths[0]", "\\\\server\\share\\include"),
        ("build.elf", "\\\\server\\share\\firmware.elf"),
        ("debug.svd", "\\\\server\\share\\chip.svd"),
        ("generation.cubeMxIoc", "\\\\server\\share\\firmware.ioc"),
        ("generation.generatedDirectories[0]", "\\\\server\\share\\generated"),
        ("generation.userDirectories[0]", "\\\\server\\share\\user"),
        ("generation.managedManifest", "\\\\server\\share\\generated-files.json"),
    ],
)
def test_unc_absolute_paths_are_rejected_on_posix_hosts(tmp_path: Path, field: str, value: str):
    payload = _v2_payload()
    _set_path(payload, field, value)
    _write_manifest(tmp_path, payload)

    with pytest.raises(ProjectManifestError) as error:
        load_project_model(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": field, "rule": "pathWithinProjectRoot"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("build.sources[0]", "../outside.c"),
        ("build.includePaths[0]", "../outside"),
        ("build.assemblySources[0]", "../outside/startup.s"),
        ("build.elf", "../outside/firmware.elf"),
        ("debug.svd", "../outside/chip.svd"),
        ("generation.cubeMxIoc", "../outside/firmware.ioc"),
        ("generation.managedManifest", "../outside/generated-files.json"),
        ("generation.generatedDirectories[0]", "../outside/generated"),
        ("generation.userDirectories[0]", "../outside/user"),
    ],
)
def test_parent_traversal_paths_are_rejected(tmp_path: Path, field: str, value: str):
    payload = _v2_payload()
    _set_path(payload, field, value)
    _write_manifest(tmp_path, payload)

    with pytest.raises(ProjectManifestError) as error:
        load_project_model(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": field, "rule": "pathWithinProjectRoot"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("build.sources[0]", "D:outside.c"),
        ("build.includePaths[0]", "D:outside/include"),
        ("build.assemblySources[0]", "E:startup.s"),
        ("build.elf", "D:build/firmware.elf"),
        ("debug.svd", "D:debug/chip.svd"),
        ("generation.cubeMxIoc", "D:firmware.ioc"),
        ("generation.managedManifest", "D:generated-files.json"),
        ("generation.generatedDirectories[0]", "D:generated"),
        ("generation.userDirectories[0]", "D:user"),
    ],
)
def test_windows_drive_relative_paths_are_rejected_on_posix_hosts(
    tmp_path: Path, field: str, value: str
):
    """Windows drive-qualified relative forms such as ``D:outside.c`` reject.

    Codex-observed RED: ``D:outside.c`` was accepted by the model loader on
    Linux. Work-order section 7.2: drive-qualified relative forms are not
    project-relative and must be rejected on every host.
    """
    payload = _v2_payload()
    _set_path(payload, field, value)
    _write_manifest(tmp_path, payload)

    with pytest.raises(ProjectManifestError) as error:
        load_project_model(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": field, "rule": "pathWithinProjectRoot"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("build.sources[0]", "D:outside.c"),
        ("build.assemblySources[0]", "D:startup.s"),
        ("build.elf", "D:build/firmware.elf"),
        ("generation.managedManifest", "D:generated-files.json"),
    ],
)
def test_windows_drive_relative_paths_are_rejected_in_compat_loader(
    tmp_path: Path, field: str, value: str
):
    """Both public loaders reject ``D:outside.c`` host-independently.

    Codex-observed RED: the compatibility view returned
    ``WindowsPath('D:outside.c')`` for an accepted drive-relative path.
    """
    payload = _v2_payload()
    _set_path(payload, field, value)
    _write_manifest(tmp_path, payload)

    with pytest.raises(ProjectManifestError) as error:
        ProjectManifest.load(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": field, "rule": "pathWithinProjectRoot"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("build.sources[0]", "..\\outside.c"),
        ("build.includePaths[0]", "..\\outside\\include"),
        ("build.assemblySources[0]", "..\\outside\\startup.s"),
        ("build.elf", "..\\outside\\firmware.elf"),
        ("debug.svd", "..\\outside\\chip.svd"),
        ("generation.cubeMxIoc", "..\\outside\\firmware.ioc"),
        ("generation.managedManifest", "..\\outside\\generated-files.json"),
        ("generation.generatedDirectories[0]", "..\\outside\\generated"),
        ("generation.userDirectories[0]", "..\\outside\\user"),
        ("build.sources[1]", "App\\..\\outside.c"),
    ],
)
def test_backslash_traversal_paths_are_rejected_on_posix_hosts(
    tmp_path: Path, field: str, value: str
):
    """``..`` traversal under the backslash convention is rejected on Linux.

    Work-order section 7.2: detect ``..`` traversal under both ``/`` and
    ``\\`` separator conventions so a manifest accepted on Linux cannot
    escape after relocation to Windows.
    """
    payload = _v2_payload()
    _set_path(payload, field, value)
    _write_manifest(tmp_path, payload)

    with pytest.raises(ProjectManifestError) as error:
        load_project_model(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": field, "rule": "pathWithinProjectRoot"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("build.sources[0]", "..\\outside.c"),
        ("build.elf", "..\\outside\\firmware.elf"),
        ("generation.managedManifest", "..\\outside\\generated-files.json"),
    ],
)
def test_backslash_traversal_paths_are_rejected_in_compat_loader(
    tmp_path: Path, field: str, value: str
):
    """Both public loaders reject backslash-convention traversal."""
    payload = _v2_payload()
    _set_path(payload, field, value)
    _write_manifest(tmp_path, payload)

    with pytest.raises(ProjectManifestError) as error:
        ProjectManifest.load(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": field, "rule": "pathWithinProjectRoot"}


@pytest.mark.parametrize(
    "error",
    [
        PermissionError(13, "Permission denied"),
        OSError(5, "Input/output error"),
    ],
)
def test_injected_lstat_failure_is_rejected_conservatively(
    tmp_path: Path, monkeypatch, error: OSError
):
    """PermissionError and other lstat failures reject, never treat as safe.

    Codex-observed RED: an injected ``PermissionError`` from ``os.lstat`` was
    treated as a missing component and the path was accepted. Work-order
    section 7.2: only confirmed missing/non-directory components may use the
    nonexistent-path fast path.
    """
    import os as _os

    payload = _v2_payload()
    payload["build"]["sources"] = ["App/main.c"]
    _write_manifest(tmp_path, payload)

    real_lstat = _os.lstat

    def failing_lstat(path):
        if str(path).rsplit(_os.sep, 1)[-1] == "App":
            raise error
        return real_lstat(path)

    monkeypatch.setattr("stm32_toolkit.project_model.os.lstat", failing_lstat)

    with pytest.raises(ProjectManifestError) as exc_info:
        load_project_model(tmp_path)

    assert exc_info.value.code == "PROJECT_SCHEMA_INVALID"
    assert exc_info.value.details == {
        "field": "build.sources[0]",
        "rule": "pathWithinProjectRoot",
    }


def test_injected_lstat_permission_error_is_rejected_in_compat_loader(
    tmp_path: Path, monkeypatch
):
    """The compatibility loader rejects an uninspectable component too."""
    import os as _os

    payload = _v2_payload()
    payload["build"]["sources"] = ["App/main.c"]
    _write_manifest(tmp_path, payload)

    real_lstat = _os.lstat

    def permission_denied_lstat(path):
        if str(path).rsplit(_os.sep, 1)[-1] == "App":
            raise PermissionError(13, "Permission denied")
        return real_lstat(path)

    monkeypatch.setattr(
        "stm32_toolkit.project_model.os.lstat", permission_denied_lstat
    )

    with pytest.raises(ProjectManifestError) as exc_info:
        ProjectManifest.load(tmp_path)

    assert exc_info.value.code == "PROJECT_SCHEMA_INVALID"
    assert exc_info.value.details == {
        "field": "build.sources[0]",
        "rule": "pathWithinProjectRoot",
    }


def test_file_symlink_cannot_escape_project_root(tmp_path: Path):
    outside = tmp_path.parent / "outside-model-file.c"
    outside.write_text("int outside;", encoding="utf-8")
    link = tmp_path / "linked.c"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symbolic links are unavailable in this test environment")

    payload = _v2_payload()
    payload["build"]["sources"] = ["linked.c"]
    _write_manifest(tmp_path, payload)

    with pytest.raises(ProjectManifestError) as error:
        load_project_model(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": "build.sources[0]", "rule": "pathWithinProjectRoot"}


def test_directory_symlink_parent_cannot_escape_project_root(tmp_path: Path):
    outside = tmp_path.parent / "outside-model-dir"
    outside.mkdir()
    link = tmp_path / "linked-dir"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable in this test environment")

    payload = _v2_payload()
    payload["build"]["sources"] = ["linked-dir/main.c"]
    _write_manifest(tmp_path, payload)

    with pytest.raises(ProjectManifestError) as error:
        load_project_model(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": "build.sources[0]", "rule": "pathWithinProjectRoot"}


def test_reparse_point_junction_parent_cannot_escape_project_root(
    tmp_path: Path, monkeypatch
):
    """NTFS junction escape is rejected through reparse-point detection.

    Linux cannot create a real NTFS junction, so the junction is simulated
    faithfully with three Windows-accurate behaviors: the junction node is a
    real directory; ``os.lstat`` reports it with the reparse-point attribute
    (FILE_ATTRIBUTE_REPARSE_POINT = 0x400) and a plain directory mode rather
    than a symlink mode; and path resolution follows the junction to its
    outside target exactly as Windows ``GetFinalPathNameByHandle`` does. The
    Codex Windows gate exercises a real NTFS junction and does not skip it.
    """
    import os as _os
    from types import SimpleNamespace

    outside = tmp_path.parent / "outside-reparse-dir"
    outside.mkdir()
    junction = tmp_path / "linked-dir"
    junction.mkdir()

    real_lstat = _os.lstat

    def junction_lstat(path):
        st = real_lstat(path)
        if str(path) == str(junction):
            return SimpleNamespace(
                st_mode=st.st_mode & ~0o170000 | 0o040000,
                st_file_attributes=0x400,
            )
        return st

    real_resolve = Path.resolve

    def junction_resolve(self, strict=False):
        resolved = real_resolve(self, strict=strict)
        text = str(self)
        if text == str(junction) or text.startswith(str(junction) + _os.sep):
            return Path(str(outside / _os.path.relpath(str(resolved), str(junction))))
        return resolved

    monkeypatch.setattr("stm32_toolkit.project_model.os.lstat", junction_lstat)
    monkeypatch.setattr(Path, "resolve", junction_resolve)

    payload = _v2_payload()
    payload["build"]["sources"] = ["linked-dir/main.c"]
    _write_manifest(tmp_path, payload)

    with pytest.raises(ProjectManifestError) as error:
        load_project_model(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": "build.sources[0]", "rule": "pathWithinProjectRoot"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("build.sources[0]", "App/\x00main.c"),
        ("build.includePaths[0]", "App/\x00inc"),
        ("build.assemblySources[0]", "Startup/\x00startup.s"),
        ("build.elf", "build/\x00firmware.elf"),
        ("debug.svd", "debug/\x00chip.svd"),
        ("generation.cubeMxIoc", "firmware.\x00ioc"),
        ("generation.managedManifest", ".stm32-toolkit/\x00generated-files.json"),
        ("generation.generatedDirectories[0]", "gen/\x00dir"),
        ("generation.userDirectories[0]", "user/\x00dir"),
    ],
)
def test_embedded_nul_paths_return_stable_structured_rejection(
    tmp_path: Path, field: str, value: str
):
    payload = _v2_payload()
    _set_path(payload, field, value)
    _write_manifest(tmp_path, payload)

    with pytest.raises(ProjectManifestError) as error:
        load_project_model(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": field, "rule": "pathWithinProjectRoot"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("build.sources[0]", "App/\x00main.c"),
        ("generation.managedManifest", ".stm32-toolkit/\x00generated-files.json"),
    ],
)
def test_embedded_nul_paths_return_stable_rejection_in_compat_loader(
    tmp_path: Path, field: str, value: str
):
    payload = _v2_payload()
    _set_path(payload, field, value)
    _write_manifest(tmp_path, payload)

    with pytest.raises(ProjectManifestError) as error:
        ProjectManifest.load(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": field, "rule": "pathWithinProjectRoot"}


def test_nonexistent_in_root_paths_load_safely(tmp_path: Path):
    payload = _v2_payload()
    payload["build"]["sources"] = ["future/main.c"]
    payload["build"]["includePaths"] = ["future/inc"]
    payload["build"]["elf"] = "out/never.elf"
    payload["debug"]["svd"] = "debug/never.svd"
    payload["generation"]["cubeMxIoc"] = "future/firmware.ioc"
    payload["generation"]["managedManifest"] = ".stm32-toolkit/generated-files.json"
    payload["generation"]["generatedDirectories"] = ["future/gen"]
    payload["generation"]["userDirectories"] = ["future/user"]
    _write_manifest(tmp_path, payload)

    model = load_project_model(tmp_path)

    assert model.build.sources == ("future/main.c",)
    assert model.build.include_paths == ("future/inc",)
    assert model.build.elf == "out/never.elf"
    assert model.debug.svd == "debug/never.svd"
    assert model.generation.cube_mx_ioc == "future/firmware.ioc"
    assert model.generation.managed_manifest == ".stm32-toolkit/generated-files.json"
    assert model.generation.generated_directories == ("future/gen",)
    assert model.generation.user_directories == ("future/user",)


def test_project_manifest_load_accepts_v1(tmp_path: Path, copy_fixture):
    copy_fixture("valid-project.json", tmp_path / ".stm32-project.json")

    manifest = ProjectManifest.load(tmp_path)

    assert manifest.logical_project_id == UUID("12345678-1234-5678-1234-567812345678")
    assert manifest.target_device == "STM32F429ZGTx"
    assert manifest.framework_type == "spl"
    assert manifest.source_paths == (tmp_path / "App/main.c",)
    assert manifest.assembly_source_paths == ()
    assert manifest.elf_path == tmp_path / "build-fw/firmware.elf"


def test_project_manifest_load_accepts_v2(tmp_path: Path):
    _write_manifest(tmp_path, _v2_payload())

    manifest = ProjectManifest.load(tmp_path)

    assert manifest.logical_project_id == UUID("12345678-1234-5678-1234-567812345678")
    assert manifest.target_device == "STM32F429ZGTx"
    assert manifest.framework_type == "hal"
    assert manifest.source_paths == (
        tmp_path / "App" / "main.c",
        tmp_path / "Core" / "main.c",
    )
    assert manifest.assembly_source_paths == (tmp_path / "Startup" / "startup.s",)
    assert manifest.elf_path == tmp_path / "build-fw" / "firmware.elf"


def test_project_manifest_explicit_v1_schema_path(tmp_path: Path, copy_fixture):
    copy_fixture("valid-project.json", tmp_path / ".stm32-project.json")
    schema_path = tmp_path / "schema-v1.json"
    schema_path.write_text(
        resources.files("stm32_toolkit")
        .joinpath("schemas/stm32-project-v1.schema.json")
        .read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    manifest = ProjectManifest.load(tmp_path, schema_path)

    assert manifest.framework_type == "spl"


def test_project_manifest_explicit_v2_schema_path(tmp_path: Path):
    _write_manifest(tmp_path, _v2_payload())
    schema_path = tmp_path / "schema-v2.json"
    schema_path.write_text(
        resources.files("stm32_toolkit")
        .joinpath("schemas/stm32-project.schema.json")
        .read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    manifest = ProjectManifest.load(tmp_path, schema_path)

    assert manifest.framework_type == "hal"


def test_project_manifest_explicit_v1_schema_rejects_v2_manifest(tmp_path: Path):
    _write_manifest(tmp_path, _v2_payload())
    schema_path = tmp_path / "schema-v1.json"
    schema_path.write_text(
        resources.files("stm32_toolkit")
        .joinpath("schemas/stm32-project-v1.schema.json")
        .read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    with pytest.raises(ProjectManifestError) as error:
        ProjectManifest.load(tmp_path, schema_path)

    # The v1 schema rejects v2-only sections; deterministic sorted errors put
    # the alphabetically-first unexpected property first.
    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": "build.presets", "rule": "additionalProperties"}


def _write_explicit_v2_schema(tmp_path: Path) -> Path:
    schema_path = tmp_path / "schema-v2.json"
    schema_path.write_text(
        resources.files("stm32_toolkit")
        .joinpath("schemas/stm32-project.schema.json")
        .read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return schema_path


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("build.sources[0]", "../outside/main.c"),
        ("build.includePaths[0]", "../outside/include"),
        ("build.assemblySources[0]", "../outside/startup.s"),
        ("build.elf", "../outside/firmware.elf"),
        ("debug.svd", "../outside/chip.svd"),
        ("generation.cubeMxIoc", "../outside/firmware.ioc"),
        ("generation.managedManifest", "../outside/generated-files.json"),
        ("generation.generatedDirectories[0]", "../outside/generated"),
        ("generation.userDirectories[0]", "../outside/user"),
    ],
)
def test_project_manifest_explicit_schema_validates_every_path_field(
    tmp_path: Path, field: str, value: str
):
    """Explicit-schema loads run complete post-schema path validation."""
    payload = _v2_payload()
    _set_path(payload, field, value)
    _write_manifest(tmp_path, payload)
    schema_path = _write_explicit_v2_schema(tmp_path)

    with pytest.raises(ProjectManifestError) as error:
        ProjectManifest.load(tmp_path, schema_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": field, "rule": "pathWithinProjectRoot"}


def test_project_manifest_default_schema_rejects_escaping_generation_path(
    tmp_path: Path,
):
    payload = _v2_payload()
    payload["generation"]["managedManifest"] = "../outside/generated-files.json"
    _write_manifest(tmp_path, payload)

    with pytest.raises(ProjectManifestError) as error:
        ProjectManifest.load(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {
        "field": "generation.managedManifest",
        "rule": "pathWithinProjectRoot",
    }


@pytest.mark.parametrize("bad_version", [True, "1", 1.0])
def test_project_manifest_load_rejects_non_integer_schema_version(
    tmp_path: Path, bad_version: object
):
    payload = _v2_payload()
    payload["schemaVersion"] = bad_version
    _write_manifest(tmp_path, payload)

    with pytest.raises(ProjectManifestError) as error:
        ProjectManifest.load(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": "schemaVersion", "rule": "type"}


def test_compat_loader_otherwise_valid_v1_unsupported_version_returns_unsupported(
    tmp_path: Path,
):
    """Otherwise valid v1-shaped unsupported integers are version-unsupported.

    Work-order section 7.2: default ``ProjectManifest.load`` returns
    ``PROJECT_SCHEMA_VERSION_UNSUPPORTED`` with ``{"schemaVersion": value,
    "supported": [1, 2]}`` when the manifest's only v1 schema defect is the
    unsupported integer ``schemaVersion`` (Codex-observed RED: version 99
    returned ``PROJECT_SCHEMA_INVALID``/``const``).
    """
    payload = _v1_payload()
    payload["schemaVersion"] = 99
    _write_manifest(tmp_path, payload)

    with pytest.raises(ProjectManifestError) as error:
        ProjectManifest.load(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_VERSION_UNSUPPORTED"
    assert error.value.details == {"schemaVersion": 99, "supported": [1, 2]}


def test_compat_loader_list_manifest_returns_object_type_error(tmp_path: Path):
    """A list manifest returns ``{"field": "$", "rule": "type"}``.

    Codex-observed RED: default ``ProjectManifest.load`` returned the wrong
    required-field error (``schemaVersion``/``required``) for a list.
    """
    (tmp_path / ".stm32-project.json").write_text("[1, 2, 3]", encoding="utf-8")

    with pytest.raises(ProjectManifestError) as error:
        ProjectManifest.load(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": "$", "rule": "type"}


def test_compat_loader_scalar_manifest_never_leaks_type_error(tmp_path: Path):
    """A scalar manifest such as JSON ``"schemaVersion"`` never leaks TypeError.

    Codex-observed RED: raw ``TypeError: string indices must be integers``
    escaped the compatibility loader for a scalar manifest.
    """
    (tmp_path / ".stm32-project.json").write_text('"schemaVersion"', encoding="utf-8")

    with pytest.raises(ProjectManifestError) as error:
        ProjectManifest.load(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": "$", "rule": "type"}


def test_compat_loader_explicit_schema_list_manifest_returns_object_type_error(
    tmp_path: Path,
):
    """Explicit-schema mode also requires a manifest object first."""
    (tmp_path / ".stm32-project.json").write_text("[1, 2, 3]", encoding="utf-8")
    schema_path = _write_explicit_v2_schema(tmp_path)

    with pytest.raises(ProjectManifestError) as error:
        ProjectManifest.load(tmp_path, schema_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": "$", "rule": "type"}


def test_compat_loader_preserves_invalid_project_required_precedence(
    tmp_path: Path,
):
    """The invalid-project.json required error keeps its precedence.

    Work-order section 7.2: when another v1 schema defect sorts before the
    version error, the older deterministic first error is preserved; the
    ``invalid-project.json`` fixture keeps returning missing
    ``logicalProjectId``/``required`` so the existing context contract stays
    green.
    """
    fixture = Path(__file__).resolve().parent / "fixtures" / "invalid-project.json"
    (tmp_path / ".stm32-project.json").write_text(
        fixture.read_text(encoding="utf-8"), encoding="utf-8"
    )

    with pytest.raises(ProjectManifestError) as error:
        ProjectManifest.load(tmp_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": "logicalProjectId", "rule": "required"}


@pytest.mark.parametrize("bad_version", [True, "1", 1.0])
def test_project_manifest_explicit_schema_rejects_non_integer_schema_version(
    tmp_path: Path, bad_version: object
):
    payload = _v2_payload()
    payload["schemaVersion"] = bad_version
    _write_manifest(tmp_path, payload)
    schema_path = _write_explicit_v2_schema(tmp_path)

    with pytest.raises(ProjectManifestError) as error:
        ProjectManifest.load(tmp_path, schema_path)

    assert error.value.code == "PROJECT_SCHEMA_INVALID"
    assert error.value.details == {"field": "schemaVersion", "rule": "type"}


def test_project_manifest_explicit_schema_rejects_unsupported_version(
    tmp_path: Path,
):
    payload = _v2_payload()
    payload["schemaVersion"] = 3
    _write_manifest(tmp_path, payload)
    schema_path = _write_explicit_v2_schema(tmp_path)

    with pytest.raises(ProjectManifestError) as error:
        ProjectManifest.load(tmp_path, schema_path)

    assert error.value.code == "PROJECT_SCHEMA_VERSION_UNSUPPORTED"
    assert error.value.details == {"schemaVersion": 3, "supported": [1, 2]}
