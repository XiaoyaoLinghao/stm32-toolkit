from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from stm32_toolkit.creation_environment import (
    CreationEnvironmentError,
    CreationExecutionEnvironment,
    discover_creation_environment,
)
from stm32_toolkit.generation.creation import CreationRequest
from stm32_toolkit.tool_support import ToolFact, ToolSupportProfile


def _fact(tmp_path: Path, name: str, version: str) -> ToolFact:
    path = tmp_path / name
    path.write_bytes(name.encode())
    return ToolFact(name, path, version, "explicit", hashlib.sha256(path.read_bytes()).hexdigest())


def _support(tmp_path: Path, cubemx: Path, *, seed_descriptor: bool = True) -> ToolSupportProfile:
    if seed_descriptor:
        _descriptor(cubemx.parent)
    sibling_java = cubemx.parent / "jre" / "bin" / "java.exe"
    sibling_java.parent.mkdir(parents=True, exist_ok=True)
    sibling_java.write_bytes(b"java")
    return ToolSupportProfile(
        "3.12.10",
        ToolFact("cubeMx", cubemx, "6.18.1-RC2", "explicit", hashlib.sha256(cubemx.read_bytes()).hexdigest()),
        tmp_path,
        _fact(tmp_path, "gcc.exe", "14.3.1"),
        _fact(tmp_path, "cmake.exe", "4.3.1"),
        _fact(tmp_path, "ninja.exe", "1.13.2"),
        None,
        (),
        (),
    )


def _package(repository: Path) -> None:
    package = repository / "STM32Cube_FW_F4_V1.0.0"
    package.mkdir(parents=True)
    (package / "package.xml").write_text(
        '<package name="STM32Cube_FW_F4" version="1.0.0"/>', encoding="utf-8"
    )


def _descriptor(install: Path, *, ref_name: str = "STM32F429ZITx", nested: bool = False) -> Path:
    root = install / "db" / "mcu"
    if nested:
        root = root / "nested"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "STM32F429ZITx.xml"
    path.write_text(f'<Mcu RefName="{ref_name}"/>', encoding="utf-8")
    return path


def _mcu_index(install: Path, rows: list[tuple[str, str]], *, body: str | None = None) -> Path:
    root = install / "db" / "mcu"
    root.mkdir(parents=True, exist_ok=True)
    index = root / "families.xml"
    if body is None:
        body = "\n".join(f'<Mcu RefName="{ref_name}" Name="{name}"/>' for ref_name, name in rows)
        body = f"<Families>\n{body}\n</Families>\n"
    index.write_text(body, encoding="utf-8")
    return index


def _group_descriptor(install: Path, *, name: str = "STM32F429Z(E-G)Tx", ref_name: str | None = None, nested: bool = False) -> Path:
    root = install / "db" / "mcu"
    if nested:
        root = root / "nested"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{name}.xml"
    path.write_text(f'<Mcu RefName="{ref_name or name}"/>', encoding="utf-8")
    return path


def test_sibling_java_is_bound_to_cube_mx_install(tmp_path: Path):
    install = tmp_path / "CubeMX"
    (install / "jre" / "bin").mkdir(parents=True)
    cubemx = install / "STM32CubeMX.exe"
    cubemx.write_bytes(b"cube")
    java = install / "jre" / "bin" / "java.exe"
    java.write_bytes(b"java")
    repository = tmp_path / "repository"
    repository.mkdir()
    _package(repository)
    env = discover_creation_environment(
        _support(tmp_path, cubemx),
        CreationRequest.from_mcu("STM32F429ZITx", "generated", framework="hal", language="c"),
        repository=repository,
    )
    assert env.java_executable == java.resolve()
    assert env.cubemx_executable == cubemx.resolve()


def test_missing_cube_mx_is_typed_before_repository_fallback(tmp_path: Path):
    install = tmp_path / "CubeMX"
    install.mkdir()
    cubemx = install / "STM32CubeMX.exe"
    cubemx.write_bytes(b"cube")
    support = replace(_support(tmp_path, cubemx), cubemx=None)

    with pytest.raises(CreationEnvironmentError) as error:
        discover_creation_environment(
            support,
            CreationRequest.from_mcu("STM32F429ZITx", "generated", framework="hal", language="c"),
            repository=tmp_path / "missing-repository",
        )

    assert error.value.code == "CUBEMX_MISSING"


def test_missing_sibling_java_is_typed_before_repository_inspection(tmp_path: Path):
    install = tmp_path / "CubeMX"
    install.mkdir()
    cubemx = install / "STM32CubeMX.exe"
    cubemx.write_bytes(b"cube")
    repository = tmp_path / "repository"
    repository.mkdir()
    _package(repository)
    support = _support(tmp_path, cubemx, seed_descriptor=False)
    (install / "jre" / "bin" / "java.exe").unlink()

    with pytest.raises(CreationEnvironmentError) as error:
        discover_creation_environment(
            support,
            CreationRequest.from_mcu("STM32F429ZITx", "generated", framework="hal", language="c"),
            repository=repository,
        )

    assert error.value.code == "CUBEMX_JAVA_MISSING"


def test_ioc_family_selection_is_bound_to_project_source_bytes(tmp_path: Path):
    install = tmp_path / "CubeMX"
    (install / "jre" / "bin").mkdir(parents=True)
    cubemx = install / "STM32CubeMX.exe"
    cubemx.write_bytes(b"cube")
    (install / "jre" / "bin" / "java.exe").write_bytes(b"java")
    repository = tmp_path / "repository"
    repository.mkdir()
    _package(repository)
    g4_package = repository / "STM32Cube_FW_G4_V1.0.0"
    g4_package.mkdir()
    (g4_package / "package.xml").write_text(
        '<package name="STM32Cube_FW_G4" version="1.0.0"/>',
        encoding="utf-8",
    )
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "input.ioc").write_text("Mcu.Name=STM32F429ZITx\n", encoding="utf-8")

    environment = discover_creation_environment(
        _support(tmp_path, cubemx, seed_descriptor=False),
        CreationRequest.from_ioc("input.ioc", "generated", framework="hal", language="c"),
        repository=repository,
        project_root=project_root,
    )

    assert environment.package.name == "STM32Cube_FW_F4_V1.0.0"
    assert environment.package_name == "STM32Cube_FW_F4"


def test_package_json_metadata_is_an_accepted_environment_identity_source(tmp_path: Path):
    install = tmp_path / "CubeMX"
    (install / "jre" / "bin").mkdir(parents=True)
    cubemx = install / "STM32CubeMX.exe"
    cubemx.write_bytes(b"cube")
    (install / "jre" / "bin" / "java.exe").write_bytes(b"java")
    repository = tmp_path / "repository"
    package = repository / "STM32Cube_FW_F4_V1.2.3"
    package.mkdir(parents=True)
    (package / "package.json").write_text(
        '{"name":"STM32Cube_FW_F4","version":"1.2.3"}',
        encoding="utf-8",
    )

    environment = discover_creation_environment(
        _support(tmp_path, cubemx),
        CreationRequest.from_mcu("STM32F429ZITx", "generated", framework="hal", language="c"),
        repository=repository,
    )

    assert environment.package_name == "STM32Cube_FW_F4"
    assert environment.package_version == "1.2.3"


def test_missing_repository_is_typed_and_does_not_fallback(tmp_path: Path):
    install = tmp_path / "CubeMX"
    (install / "jre" / "bin").mkdir(parents=True)
    cubemx = install / "STM32CubeMX.exe"
    cubemx.write_bytes(b"cube")
    with pytest.raises(CreationEnvironmentError) as error:
        discover_creation_environment(
            _support(tmp_path, cubemx, seed_descriptor=False),
            CreationRequest.from_mcu("STM32F429ZITx", "generated", framework="hal", language="c"),
            repository=tmp_path / "missing",
        )
    assert error.value.code == "CUBEMX_REPOSITORY_MISSING"


def test_repository_package_ambiguity_is_closed(tmp_path: Path):
    install = tmp_path / "CubeMX"
    (install / "jre" / "bin").mkdir(parents=True)
    cubemx = install / "STM32CubeMX.exe"
    cubemx.write_bytes(b"cube")
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "STM32Cube_FW_F4_V1.0.0").mkdir()
    (repository / "STM32Cube_FW_F4_V1.1.0").mkdir()
    with pytest.raises(CreationEnvironmentError) as error:
        discover_creation_environment(
            _support(tmp_path, cubemx),
            CreationRequest.from_mcu("STM32F429ZITx", "generated", framework="hal", language="c"),
            repository=repository,
        )
    assert error.value.code == "CUBEMX_PACKAGE_AMBIGUOUS"


def test_matching_zip_archive_is_not_a_firmware_package_directory(tmp_path: Path):
    install = tmp_path / "CubeMX"
    (install / "jre" / "bin").mkdir(parents=True)
    cubemx = install / "STM32CubeMX.exe"
    cubemx.write_bytes(b"cube")
    repository = tmp_path / "repository"
    repository.mkdir()
    _package(repository)
    (repository / "STM32Cube_FW_F4_V1.28.3.zip").write_bytes(b"archive")
    environment = discover_creation_environment(
        _support(tmp_path, cubemx),
        CreationRequest.from_mcu("STM32F429ZITX", "generated", framework="hal", language="c"),
        repository=repository,
    )
    assert environment.package.name == "STM32Cube_FW_F4_V1.0.0"


def test_matching_unsafe_package_entry_closes(tmp_path: Path):
    install = tmp_path / "CubeMX"
    (install / "jre" / "bin").mkdir(parents=True)
    cubemx = install / "STM32CubeMX.exe"
    cubemx.write_bytes(b"cube")
    repository = tmp_path / "repository"
    repository.mkdir()
    _package(repository)
    (repository / "STM32Cube_FW_F4_V9.9.9").write_bytes(b"unsafe non-directory")
    with pytest.raises(CreationEnvironmentError) as error:
        discover_creation_environment(
            _support(tmp_path, cubemx),
            CreationRequest.from_mcu("STM32F429ZITX", "generated", framework="hal", language="c"),
            repository=repository,
        )
    assert error.value.code == "CUBEMX_REPOSITORY_INVALID"


def test_official_package_nested_template_depth_is_supported(tmp_path: Path):
    install = tmp_path / "CubeMX"
    (install / "jre" / "bin").mkdir(parents=True)
    cubemx = install / "STM32CubeMX.exe"
    cubemx.write_bytes(b"cube")
    repository = tmp_path / "repository"
    repository.mkdir()
    _package(repository)
    nested = repository / "STM32Cube_FW_F4_V1.0.0"
    for index in range(9):
        nested = nested / f"template-{index}"
    nested.mkdir(parents=True)
    (nested / "source.c").write_text("int source;\n", encoding="utf-8")
    environment = discover_creation_environment(
        _support(tmp_path, cubemx),
        CreationRequest.from_mcu("STM32F429ZITx", "generated", framework="hal", language="c"),
        repository=repository,
    )
    assert environment.package.name == "STM32Cube_FW_F4_V1.0.0"


def test_normalized_mcu_binds_case_correct_descriptor_token_and_digest(tmp_path: Path):
    install = tmp_path / "CubeMX"
    (install / "jre" / "bin").mkdir(parents=True)
    cubemx = install / "STM32CubeMX.exe"
    cubemx.write_bytes(b"cube")
    descriptor = _descriptor(install)
    repository = tmp_path / "repository"
    repository.mkdir()
    _package(repository)
    environment = discover_creation_environment(
        _support(tmp_path, cubemx),
        CreationRequest.from_mcu("STM32F429ZITX", "generated", framework="hal", language="c"),
        repository=repository,
    )
    assert environment.native_source_token == "STM32F429ZITx"
    assert environment.native_descriptor_path == descriptor.relative_to(install).as_posix()
    assert environment.native_descriptor_sha256 == hashlib.sha256(descriptor.read_bytes()).hexdigest()
    assert "nativeIndexPath" not in environment.to_dict()
    assert "nativeIndexSha256" not in environment.to_dict()


@pytest.mark.parametrize("requested", ["STM32F429ZETx", "STM32F429ZGTx"])
def test_missing_exact_descriptor_maps_index_refname_to_group_descriptor(tmp_path: Path, requested: str):
    install = tmp_path / "CubeMX"
    (install / "jre" / "bin").mkdir(parents=True)
    cubemx = install / "STM32CubeMX.exe"
    cubemx.write_bytes(b"cube")
    (install / "jre" / "bin" / "java.exe").write_bytes(b"java")
    index = _mcu_index(
        install,
        [
            ("STM32F429ZETx", "STM32F429Z(E-G)Tx"),
            ("STM32F429ZGTx", "STM32F429Z(E-G)Tx"),
        ],
    )
    descriptor = _group_descriptor(install)
    repository = tmp_path / "repository"
    repository.mkdir()
    _package(repository)

    environment = discover_creation_environment(
        _support(tmp_path, cubemx, seed_descriptor=False),
        CreationRequest.from_mcu(requested, "generated", framework="hal", language="c"),
        repository=repository,
    )

    assert environment.native_source_token == requested
    assert environment.native_source_token != "STM32F429Z(E-G)Tx"
    assert environment.native_descriptor_path == descriptor.relative_to(install).as_posix()
    assert environment.native_descriptor_sha256 == hashlib.sha256(descriptor.read_bytes()).hexdigest()
    assert environment.native_index_path == index.relative_to(install).as_posix()
    assert environment.native_index_sha256 == hashlib.sha256(index.read_bytes()).hexdigest()
    facts = environment.to_dict()
    assert facts["nativeIndexPath"] == "db/mcu/families.xml"
    assert facts["nativeIndexSha256"] == environment.native_index_sha256


def test_fallback_index_bytes_are_bound_by_environment_digest(tmp_path: Path):
    install = tmp_path / "CubeMX"
    (install / "jre" / "bin").mkdir(parents=True)
    cubemx = install / "STM32CubeMX.exe"
    cubemx.write_bytes(b"cube")
    (install / "jre" / "bin" / "java.exe").write_bytes(b"java")
    index = _mcu_index(install, [("STM32F429ZGTx", "STM32F429Z(E-G)Tx")])
    _group_descriptor(install)
    repository = tmp_path / "repository"
    repository.mkdir()
    _package(repository)
    request = CreationRequest.from_mcu("STM32F429ZGTx", "generated", framework="hal", language="c")
    first = discover_creation_environment(_support(tmp_path, cubemx, seed_descriptor=False), request, repository=repository)

    index.write_text(index.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    second = discover_creation_environment(_support(tmp_path, cubemx, seed_descriptor=False), request, repository=repository)

    assert first.digest != second.digest
    assert first.native_index_sha256 != second.native_index_sha256


@pytest.mark.parametrize(
    "rows,descriptor_name,descriptor_ref_name",
    [
        ([('STM32F429ZQTx', 'STM32F429Z(E-G)Tx')], "STM32F429Z(E-G)Tx", "STM32F429Z(E-G)Tx"),
        ([('STM32F429ZGTx', 'STM32F429Z(E-G)Tx'), ('STM32F429ZGTx', 'STM32F429Z(E-G)Tx')], "STM32F429Z(E-G)Tx", "STM32F429Z(E-G)Tx"),
        ([('STM32F429ZGTx', 'STM32F429Z(E-G)Tx')], "STM32F429Z(E-G)Tx", "STM32F429ZITx"),
        ([('STM32F429ZGTx', 'STM32F429Z(E-G)Tx')], "STM32F429Z(E-G)Tx", "stm32f429z(e-g)tx"),
        ([('STM32F429ZGTx', '../STM32F429Z(E-G)Tx')], "STM32F429Z(E-G)Tx", "STM32F429Z(E-G)Tx"),
        ([('STM32F429ZGTx', 'STM32F429Z.GTx')], "STM32F429Z.GTx", "STM32F429Z.GTx"),
        ([('STM32F429ZGTx', 'STM32F429ZGTx.xml')], "STM32F429ZGTx.xml", "STM32F429ZGTx.xml"),
    ],
)
def test_index_mapping_rejects_missing_duplicate_mismatched_or_unsafe_names(
    tmp_path: Path,
    rows: list[tuple[str, str]],
    descriptor_name: str,
    descriptor_ref_name: str,
):
    install = tmp_path / "CubeMX"
    (install / "jre" / "bin").mkdir(parents=True)
    cubemx = install / "STM32CubeMX.exe"
    cubemx.write_bytes(b"cube")
    (install / "jre" / "bin" / "java.exe").write_bytes(b"java")
    _mcu_index(install, rows)
    _group_descriptor(install, name=descriptor_name, ref_name=descriptor_ref_name)
    repository = tmp_path / "repository"
    repository.mkdir()
    _package(repository)
    with pytest.raises(CreationEnvironmentError) as error:
        discover_creation_environment(
            _support(tmp_path, cubemx, seed_descriptor=False),
            CreationRequest.from_mcu("STM32F429ZGTx", "generated", framework="hal", language="c"),
            repository=repository,
        )
    assert error.value.code == "CUBEMX_MCU_DESCRIPTOR_INVALID"


@pytest.mark.parametrize(
    "body",
    [
        '<!DOCTYPE Families [<!ENTITY x "bad">]><Families><Mcu RefName="STM32F429ZGTx" Name="STM32F429Z(E-G)Tx"/></Families>',
        '<Families><Mcu RefName="STM32F429ZGTx" Name="STM32F429' + ("A" * 124) + '"/></Families>',
    ],
)
def test_index_mapping_rejects_dtd_and_oversized_leaf_names(tmp_path: Path, body: str):
    install = tmp_path / "CubeMX"
    (install / "jre" / "bin").mkdir(parents=True)
    cubemx = install / "STM32CubeMX.exe"
    cubemx.write_bytes(b"cube")
    (install / "jre" / "bin" / "java.exe").write_bytes(b"java")
    _mcu_index(install, [], body=body)
    _group_descriptor(install)
    repository = tmp_path / "repository"
    repository.mkdir()
    _package(repository)
    with pytest.raises(CreationEnvironmentError) as error:
        discover_creation_environment(
            _support(tmp_path, cubemx, seed_descriptor=False),
            CreationRequest.from_mcu("STM32F429ZGTx", "generated", framework="hal", language="c"),
            repository=repository,
        )
    assert error.value.code == "CUBEMX_MCU_DESCRIPTOR_INVALID"


def test_index_mapping_rejects_oversized_index(tmp_path: Path):
    install = tmp_path / "CubeMX"
    (install / "jre" / "bin").mkdir(parents=True)
    cubemx = install / "STM32CubeMX.exe"
    cubemx.write_bytes(b"cube")
    (install / "jre" / "bin" / "java.exe").write_bytes(b"java")
    index = _mcu_index(install, [("STM32F429ZGTx", "STM32F429Z(E-G)Tx")])
    index.write_bytes(b"<Families>" + b" " * (16 * 1024 * 1024) + b"</Families>")
    _group_descriptor(install)
    repository = tmp_path / "repository"
    repository.mkdir()
    _package(repository)
    with pytest.raises(CreationEnvironmentError) as error:
        discover_creation_environment(
            _support(tmp_path, cubemx, seed_descriptor=False),
            CreationRequest.from_mcu("STM32F429ZGTx", "generated", framework="hal", language="c"),
            repository=repository,
        )
    assert error.value.code == "CUBEMX_MCU_DESCRIPTOR_INVALID"


def test_index_mapping_requires_one_literal_descriptor_inventory_match(tmp_path: Path):
    install = tmp_path / "CubeMX"
    (install / "jre" / "bin").mkdir(parents=True)
    cubemx = install / "STM32CubeMX.exe"
    cubemx.write_bytes(b"cube")
    (install / "jre" / "bin" / "java.exe").write_bytes(b"java")
    _mcu_index(install, [("STM32F429ZGTx", "STM32F429Z(E-G)Tx")])
    _group_descriptor(install)
    _group_descriptor(install, nested=True)
    repository = tmp_path / "repository"
    repository.mkdir()
    _package(repository)
    with pytest.raises(CreationEnvironmentError) as error:
        discover_creation_environment(
            _support(tmp_path, cubemx, seed_descriptor=False),
            CreationRequest.from_mcu("STM32F429ZGTx", "generated", framework="hal", language="c"),
            repository=repository,
        )
    assert error.value.code == "CUBEMX_MCU_DESCRIPTOR_INVALID"


@pytest.mark.parametrize("nested", [False, True])
def test_mcu_descriptor_mismatch_or_ambiguity_closes(tmp_path: Path, nested: bool):
    install = tmp_path / "CubeMX"
    (install / "jre" / "bin").mkdir(parents=True)
    cubemx = install / "STM32CubeMX.exe"
    cubemx.write_bytes(b"cube")
    (install / "jre" / "bin" / "java.exe").write_bytes(b"java")
    _descriptor(install, ref_name="STM32F429ZIy")
    if nested:
        _descriptor(install, nested=True)
    repository = tmp_path / "repository"
    repository.mkdir()
    _package(repository)
    with pytest.raises(CreationEnvironmentError) as error:
        discover_creation_environment(
            _support(tmp_path, cubemx, seed_descriptor=False),
            CreationRequest.from_mcu("STM32F429ZITX", "generated", framework="hal", language="c"),
            repository=repository,
        )
    assert error.value.code == "CUBEMX_MCU_DESCRIPTOR_INVALID"


def test_environment_digest_is_deterministic(tmp_path: Path):
    install = tmp_path / "CubeMX"
    (install / "jre" / "bin").mkdir(parents=True)
    cubemx = install / "STM32CubeMX.exe"
    cubemx.write_bytes(b"cube")
    (install / "jre" / "bin" / "java.exe").write_bytes(b"java")
    repository = tmp_path / "repository"
    package = repository / "STM32Cube_FW_F4_V1.0.0"
    package.mkdir(parents=True)
    (package / "package.xml").write_text('<package name="STM32Cube_FW_F4" version="1.0.0"/>', encoding="utf-8")
    request = CreationRequest.from_mcu("STM32F429ZITx", "generated", framework="hal", language="c")
    first = discover_creation_environment(_support(tmp_path, cubemx), request, repository=repository)
    second = discover_creation_environment(_support(tmp_path, cubemx), request, repository=repository)
    assert isinstance(first, CreationExecutionEnvironment)
    assert first.digest == second.digest
