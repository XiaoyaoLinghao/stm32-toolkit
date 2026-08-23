from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from stm32_toolkit.creation_authorization import ConsumedCreationAuthorization
from stm32_toolkit.cubemx_adapter import (
    CubeMXAdapter,
    CubeMXAdapterError,
    CubeMXStagingContext,
)
from stm32_toolkit.generation.creation import CreationRequest
from stm32_toolkit.process import ProcessResult


def _capability(tmp_path: Path, *, framework: str = "hal", language: str = "c") -> ConsumedCreationAuthorization:
    return ConsumedCreationAuthorization(
        authorization_digest="a" * 64,
        nonce="nonce",
        plan_id="b" * 64,
        action_digest="c" * 64,
        environment_digest="d" * 64,
        project_root=tmp_path,
        request=CreationRequest.from_mcu("STM32F429ZITx", "generated", framework=framework, language=language),
        issued_at="2026-08-23T12:00:00Z",
        expires_at="2026-08-23T13:00:00Z",
        record_path=tmp_path / "authorization.json",
    )


def _environment(tmp_path: Path) -> SimpleNamespace:
    java = tmp_path / "java.exe"
    cube = tmp_path / "STM32CubeMX.exe"
    java.write_bytes(b"java")
    cube.write_bytes(b"cube")
    return SimpleNamespace(
        java_executable=java,
        cubemx_executable=cube,
        cubemx_version="6.18.1-RC2",
        digest="d" * 64,
    )


def test_direct_adapter_call_without_consumed_capability_is_rejected(tmp_path: Path):
    adapter = CubeMXAdapter(_environment(tmp_path), runner=lambda request: None)
    with pytest.raises(CubeMXAdapterError) as error:
        adapter.generate(object(), CubeMXStagingContext(tmp_path))
    assert error.value.code == "CREATION_AUTHORIZATION_REQUIRED"


def test_adapter_invokes_one_fixed_bounded_process_without_network_or_wrapper(tmp_path: Path):
    staging = tmp_path / "staging"
    staging.mkdir()
    calls: list[ProcessResult] = []

    def runner(request):
        calls.append(request)
        script = Path(request.argv[-1]).read_text(encoding="utf-8")
        assert "login" not in script.lower()
        assert "swmgr" not in script.lower()
        assert "xcubedl" not in script.lower()
        return ProcessResult(0, "load\nOK\nproject generate\nOK\nBye bye\n", "", False, 1, False, False)

    adapter = CubeMXAdapter(_environment(tmp_path), runner=runner)
    result = adapter.generate(_capability(tmp_path), CubeMXStagingContext(staging))
    assert result.invocations == 1
    assert len(calls) == 1
    request = calls[0]
    assert request.argv[0].endswith("java.exe")
    assert request.argv[-2] == "-q"
    assert request.argv[-1].endswith(".script")
    assert "-jar" in request.argv
    assert "-Djava.net.useSystemProxies=false" in request.argv
    assert request.env is not None


@pytest.mark.parametrize(
    "result,code",
    [
        (ProcessResult(1, "", "", False, 1, False, False), "CUBEMX_EXECUTION_FAILED"),
        (ProcessResult(0, "", "", True, 1, False, False), "CUBEMX_TIMEOUT"),
        (ProcessResult(0, "", "", False, 1, True, False), "CUBEMX_OUTPUT_TRUNCATED"),
        (ProcessResult(0, "load\nKO\nBye bye\n", "", False, 1, False, False), "CUBEMX_PROTOCOL_INVALID"),
        (ProcessResult(0, "load\nOK\n", "", False, 1, False, False), "CUBEMX_PROTOCOL_INVALID"),
    ],
)
def test_protocol_failures_are_typed_and_do_not_claim_generation(tmp_path: Path, result: ProcessResult, code: str):
    staging = tmp_path / "staging"
    staging.mkdir()
    adapter = CubeMXAdapter(_environment(tmp_path), runner=lambda request: result)
    with pytest.raises(CubeMXAdapterError) as error:
        adapter.generate(_capability(tmp_path), CubeMXStagingContext(staging))
    assert error.value.code == code


def test_unrelated_error_log_text_does_not_override_successful_protocol(tmp_path: Path):
    staging = tmp_path / "staging"
    staging.mkdir()
    output = "[ERROR] updater advertisement failed\nload\nOK\nproject generate\nOK\nBye bye\n"
    adapter = CubeMXAdapter(_environment(tmp_path), runner=lambda request: ProcessResult(0, output, "", False, 1, False, False))
    result = adapter.generate(_capability(tmp_path), CubeMXStagingContext(staging))
    assert result.invocations == 1


@pytest.mark.parametrize(
    "framework,source_kind,code",
    [("ll", "mcu", "CREATION_LL_CONFIGURATION_REQUIRED"), ("cpp", "mcu", "CREATION_CPP_CONFIGURATION_REQUIRED")],
)
def test_closed_configuration_preconditions_are_not_guessed(tmp_path: Path, framework: str, source_kind: str, code: str):
    adapter = CubeMXAdapter(_environment(tmp_path), runner=lambda request: pytest.fail("CubeMX must not run"))
    with pytest.raises(CubeMXAdapterError) as error:
        adapter.generate(_capability(tmp_path, framework="ll" if framework == "ll" else "hal", language="c" if framework == "ll" else "cpp"), CubeMXStagingContext(tmp_path))
    assert error.value.code == code
