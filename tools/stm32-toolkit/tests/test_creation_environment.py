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


def _support(tmp_path: Path, cubemx: Path) -> ToolSupportProfile:
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
            _support(tmp_path, cubemx),
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
