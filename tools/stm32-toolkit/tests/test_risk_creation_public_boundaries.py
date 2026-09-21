from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
import test_creation_environment as environment_fixture
import test_cubemx_adapter as adapter_fixture
from stm32_toolkit.creation_environment import (
    CreationEnvironmentError,
    discover_creation_environment,
)
from stm32_toolkit.cubemx_adapter import (
    CubeMXAdapter,
    CubeMXAdapterError,
    CubeMXStagingContext,
)
from stm32_toolkit.generation.creation import CreationRequest
from stm32_toolkit.process import ProcessResult


def _tree_snapshot(root: Path) -> dict[str, tuple[str, bytes | None]]:
    snapshot: dict[str, tuple[str, bytes | None]] = {}
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            snapshot[relative] = ("directory", None)
        elif path.is_file():
            snapshot[relative] = ("file", path.read_bytes())
        else:
            snapshot[relative] = ("other", None)
    return snapshot


def _discovery_fixture(root: Path, *, indexed: bool = False):
    install = root / "CubeMX"
    (install / "jre" / "bin").mkdir(parents=True)
    cubemx = install / "STM32CubeMX.exe"
    cubemx.write_bytes(b"cube")
    repository = root / "repository"
    repository.mkdir()
    environment_fixture._package(repository)
    if indexed:
        environment_fixture._mcu_index(
            install,
            [("STM32F429ZGTx", "STM32F429Z(E-G)Tx")],
        )
        environment_fixture._group_descriptor(install)
        request = CreationRequest.from_mcu("STM32F429ZGTx", "generated", framework="hal", language="c")
    else:
        environment_fixture._descriptor(install)
        request = CreationRequest.from_mcu("STM32F429ZITx", "generated", framework="hal", language="c")
    support = environment_fixture._support(root, cubemx, seed_descriptor=False)
    return install, repository, support, request


def _discovery_mutation(
    variant: str,
    install: Path,
    repository: Path,
) -> Callable[[], None]:
    package = repository / "STM32Cube_FW_F4_V1.0.0"
    if variant == "package-malformed":
        metadata = package / "package.xml"
        original = metadata.read_bytes()
        metadata.write_bytes(b"<package")
        return lambda: metadata.write_bytes(original)
    if variant == "package-incomplete":
        metadata = package / "package.xml"
        original = metadata.read_bytes()
        metadata.write_text('<package name="" version=""/>', encoding="utf-8")
        return lambda: metadata.write_bytes(original)
    if variant == "descriptor-index-dtd":
        index = install / "db" / "mcu" / "families.xml"
        original = index.read_bytes()
        index.write_bytes(
            b'<!DOCTYPE Families [<!ENTITY x "blocked">]>'
            b'<Families><Mcu RefName="STM32F429ZGTx" Name="STM32F429Z(E-G)Tx"/></Families>'
        )
        return lambda: index.write_bytes(original)
    if variant == "cubemx-missing":
        cubemx = install / "STM32CubeMX.exe"
        original = cubemx.read_bytes()
        cubemx.unlink()
        return lambda: cubemx.write_bytes(original)
    if variant == "java-missing":
        java = install / "jre" / "bin" / "java.exe"
        original = java.read_bytes()
        java.unlink()
        return lambda: java.write_bytes(original)
    if variant == "repository-unsafe":
        unsafe = repository / "STM32Cube_FW_F4_V9.9.9"
        unsafe.write_bytes(b"not a directory")
        return lambda: unsafe.unlink()
    if variant == "package-missing":
        hidden = repository / "package-hidden"
        package.rename(hidden)
        return lambda: hidden.rename(package)
    if variant == "package-ambiguous":
        duplicate = repository / "STM32Cube_FW_F4_V2.0.0"
        duplicate.mkdir()
        (duplicate / "package.xml").write_text(
            '<package name="STM32Cube_FW_F4" version="2.0.0"/>',
            encoding="utf-8",
        )
        return lambda: shutil.rmtree(duplicate)
    raise AssertionError(f"unknown discovery variant: {variant}")


@pytest.mark.parametrize(
    ("variant", "expected_code", "expected_message", "indexed"),
    [
        (
            "package-malformed",
            "CUBEMX_PACKAGE_INVALID",
            "firmware package metadata is invalid",
            False,
        ),
        (
            "package-incomplete",
            "CUBEMX_PACKAGE_INVALID",
            "firmware package metadata is incomplete",
            False,
        ),
        (
            "descriptor-index-dtd",
            "CUBEMX_MCU_DESCRIPTOR_INVALID",
            "CubeMX MCU descriptor index contains a DTD or entity",
            True,
        ),
        (
            "cubemx-missing",
            "CUBEMX_INVALID",
            "STM32CubeMX executable is invalid",
            False,
        ),
        (
            "java-missing",
            "CUBEMX_JAVA_MISSING",
            "CubeMX sibling Java runtime is unavailable",
            False,
        ),
        (
            "repository-unsafe",
            "CUBEMX_REPOSITORY_INVALID",
            "Cube firmware repository contains an unsafe package",
            False,
        ),
        (
            "package-missing",
            "CUBEMX_PACKAGE_MISSING",
            "required Cube firmware package is unavailable",
            False,
        ),
        (
            "package-ambiguous",
            "CUBEMX_PACKAGE_AMBIGUOUS",
            "required Cube firmware package is ambiguous",
            False,
        ),
    ],
)
def test_public_discovery_refusal_restores_and_reuses_environment(
    tmp_path: Path,
    variant: str,
    expected_code: str,
    expected_message: str,
    indexed: bool,
) -> None:
    install, repository, support, request = _discovery_fixture(tmp_path, indexed=indexed)
    valid = discover_creation_environment(support, request, repository=repository)
    valid_wire = valid.to_dict()
    valid_digest = valid.digest
    before = _tree_snapshot(tmp_path)
    restore = _discovery_mutation(variant, install, repository)
    try:
        with pytest.raises(CreationEnvironmentError) as error:
            discover_creation_environment(support, request, repository=repository)
        assert error.value.code == expected_code
        assert error.value.message == expected_message
        assert str(error.value) == expected_message
    finally:
        restore()

    assert _tree_snapshot(tmp_path) == before
    recovered = discover_creation_environment(support, request, repository=repository)
    assert recovered.to_dict() == valid_wire
    assert recovered.digest == valid_digest


def _successful_process(staging: Path) -> ProcessResult:
    (staging / "generated").mkdir(exist_ok=True)
    return ProcessResult(
        0,
        adapter_fixture._native_fixture("mcu", staging),
        "",
        False,
        1,
        False,
        False,
    )


def _generation_case(root: Path, variant: str):
    source_kind = "ioc" if variant.startswith("ioc-") else "mcu"
    capability = adapter_fixture._capability(root, source_kind=source_kind)
    environment = adapter_fixture._environment(root)
    staging = root / "staging"
    staging.mkdir()
    user_file = root / "user-sentinel.txt"
    user_file.write_bytes(b"user-owned-bytes")
    calls: list[object] = []
    source = root / "board.ioc"
    source_original = source.read_bytes() if source.exists() else None
    original_token = environment.native_source_token

    def runner(request):
        calls.append(request)
        if variant == "protocol-invalid":
            return ProcessResult(0, "load STM32F429ZITx\n", "", False, 1, False, False)
        if variant == "result-invalid":
            return None
        if variant == "output-invalid":
            (staging / "generated").mkdir()
            (staging / "unexpected").mkdir()
            return _successful_process(staging)
        return _successful_process(staging)

    if variant == "ioc-changed":
        source.write_text("Mcu.Name=STM32F429ZI\nchanged=true\n", encoding="utf-8")
    elif variant == "ioc-type":
        source.unlink()
        source.mkdir()
    elif variant == "ioc-oversized":
        source.write_bytes(b"x" * (1 * 1024 * 1024 + 1))
    elif variant == "descriptor-invalid":
        environment.native_source_token = "invalid token"
    elif variant == "container-nonempty":
        (staging / "container-user-file.txt").write_bytes(b"preserve")
    adapter = CubeMXAdapter(environment, runner=runner)
    return capability, environment, staging, user_file, calls, source, source_original, original_token, adapter


@pytest.mark.parametrize(
    ("variant", "expected_code", "expected_message", "runner_calls"),
    [
        (
            "ioc-changed",
            "CREATION_PLAN_CHANGED",
            "authorized IOC source changed",
            0,
        ),
        (
            "ioc-type",
            "CREATION_PLAN_CHANGED",
            "authorized IOC source is unavailable",
            0,
        ),
        (
            "ioc-oversized",
            "CREATION_PLAN_CHANGED",
            "authorized IOC source is oversized",
            0,
        ),
        (
            "descriptor-invalid",
            "CREATION_EXECUTION_ENVIRONMENT_CHANGED",
            "CubeMX MCU descriptor token is unavailable",
            0,
        ),
        (
            "protocol-invalid",
            "CUBEMX_PROTOCOL_INVALID",
            "CubeMX protocol completion is incomplete",
            1,
        ),
        (
            "result-invalid",
            "CUBEMX_EXECUTION_FAILED",
            "CubeMX returned no bounded process result",
            1,
        ),
        (
            "output-invalid",
            "CUBEMX_NATIVE_OUTPUT_INVALID",
            "CubeMX output root is not the authorized project child",
            1,
        ),
        (
            "container-nonempty",
            "CUBEMX_NATIVE_OUTPUT_INVALID",
            "CubeMX output container is not empty",
            0,
        ),
    ],
)
def test_public_generation_refusal_preserves_user_files_and_fresh_recovery(
    tmp_path: Path,
    variant: str,
    expected_code: str,
    expected_message: str,
    runner_calls: int,
) -> None:
    (
        capability,
        environment,
        staging,
        user_file,
        calls,
        source,
        source_original,
        original_token,
        adapter,
    ) = _generation_case(tmp_path, variant)
    user_snapshot = user_file.read_bytes()
    staging_snapshot = _tree_snapshot(staging)

    with pytest.raises(CubeMXAdapterError) as error:
        adapter.generate(capability, CubeMXStagingContext(staging))

    assert error.value.code == expected_code
    assert error.value.message == expected_message
    assert str(error.value) == expected_message
    assert len(calls) == runner_calls
    assert user_file.read_bytes() == user_snapshot
    assert not list(tmp_path.glob(".stm32tk-cubemx-control-*"))
    if variant == "container-nonempty":
        assert _tree_snapshot(staging) == staging_snapshot
    if variant in {"ioc-changed", "ioc-type", "ioc-oversized"}:
        if source.is_dir():
            source.rmdir()
        assert source_original is not None
        source.write_bytes(source_original)
    if variant == "descriptor-invalid":
        environment.native_source_token = original_token

    recovery_root = tmp_path / "recovery"
    recovery_root.mkdir()
    fresh_capability = adapter_fixture._capability(recovery_root)
    recovery_environment = adapter_fixture._environment(recovery_root)
    recovery_staging = recovery_root / "staging"
    recovery_staging.mkdir()
    recovery_calls: list[object] = []

    def recovery_runner(request):
        recovery_calls.append(request)
        return _successful_process(recovery_staging)

    recovery = CubeMXAdapter(recovery_environment, runner=recovery_runner).generate(
        fresh_capability,
        CubeMXStagingContext(recovery_staging),
    )
    assert fresh_capability is not capability
    assert len(recovery_calls) == 1
    assert recovery.project_root == recovery_staging / "generated"
    assert sorted(path.name for path in recovery_staging.iterdir()) == ["generated"]
    assert not list(recovery_root.glob(".stm32tk-cubemx-control-*"))

