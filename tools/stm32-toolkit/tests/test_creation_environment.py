from __future__ import annotations

import hashlib
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


def test_missing_repository_is_typed_and_does_not_fallback(tmp_path: Path):
    install = tmp_path / "CubeMX"
    (install / "jre" / "bin").mkdir(parents=True)
    cubemx = install / "STM32CubeMX.exe"
    cubemx.write_bytes(b"cube")
    (install / "jre" / "bin" / "java.exe").write_bytes(b"java")
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
    (install / "jre" / "bin" / "java.exe").write_bytes(b"java")
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
    (install / "jre" / "bin" / "java.exe").write_bytes(b"java")
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
    (install / "jre" / "bin" / "java.exe").write_bytes(b"java")
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
    (install / "jre" / "bin" / "java.exe").write_bytes(b"java")
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
    (install / "jre" / "bin" / "java.exe").write_bytes(b"java")
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
