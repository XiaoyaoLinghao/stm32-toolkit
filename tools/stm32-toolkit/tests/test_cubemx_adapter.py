from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import stm32_toolkit.cubemx_adapter as cubemx_adapter_module
from stm32_toolkit.creation_authorization import ConsumedCreationAuthorization
from stm32_toolkit.creation_authorization import CreationAuthorizationStore, CreationPrepareRequest
from stm32_toolkit.cubemx_adapter import (
    CubeMXAdapter,
    CubeMXAdapterError,
    CubeMXStagingContext,
)
from stm32_toolkit.generation.creation import CreationRequest, CreationSource
from stm32_toolkit.process import ProcessResult


def _capability(
    tmp_path: Path,
    *,
    source_kind: str = "mcu",
    framework: str = "hal",
    language: str = "c",
) -> ConsumedCreationAuthorization:
    if source_kind == "mcu":
        request = CreationRequest.from_mcu("STM32F429ZITx", "generated", framework=framework, language=language)
    elif source_kind == "board":
        request = CreationRequest.from_board("NUCLEO-F429ZI", "generated", framework=framework, language=language)
    else:
        source = tmp_path / "board.ioc"
        source.write_text("Mcu.Name=STM32F429ZI\n", encoding="utf-8")
        request = CreationRequest(
            CreationSource("ioc", source.name, hashlib.sha256(source.read_bytes()).hexdigest()),
            "generated",
            framework,
            language,
        )
    store = CreationAuthorizationStore(
        tmp_path / "capability-data",
        now=lambda: datetime(2026, 8, 23, 12, tzinfo=timezone.utc),
        nonce_factory=lambda: "nonce",
    )
    prepared = store.prepare(
        CreationPrepareRequest(
            request,
            tmp_path,
            "b" * 64,
            "c" * 64,
            "d" * 64,
            "2026-08-23T13:00:00Z",
        )
    )
    return store.consume(prepared.authorization_digest, authorized=True)


def _environment(tmp_path: Path) -> SimpleNamespace:
    java = tmp_path / "java.exe"
    cube = tmp_path / "STM32CubeMX.exe"
    java.write_bytes(b"java")
    cube.write_bytes(b"cube")
    repository = tmp_path / "Repository"
    repository.mkdir()
    return SimpleNamespace(
        java_executable=java,
        cubemx_executable=cube,
        cubemx_version="6.18.1-RC2",
        digest="d" * 64,
        repository=repository,
        native_source_token="STM32F429ZITx",
        native_descriptor_path=str(tmp_path / "descriptor.xml"),
        native_descriptor_sha256="e" * 64,
    )


def _native_fixture(name: str, container: Path, control: Path | None = None) -> str:
    """Load a static hand-sanitized r8 transcript; never derive responses."""
    fixture = Path(__file__).parent / "fixtures" / "cubemx-6.18" / "native-f429" / f"stdout-{name}-success.txt"
    text = fixture.read_text(encoding="utf-8")
    text = text.replace(r"C:\native-container", str(container.resolve()))
    if control is not None:
        text = text.replace(r"C:\control", str(control.resolve()))
    return text


def _native_project_root(container: Path) -> None:
    (container / "generated").mkdir()


def test_direct_adapter_call_without_consumed_capability_is_rejected(tmp_path: Path):
    adapter = CubeMXAdapter(_environment(tmp_path), runner=lambda request: None)
    with pytest.raises(CubeMXAdapterError) as error:
        adapter.generate(object(), CubeMXStagingContext(tmp_path))
    assert error.value.code == "CREATION_AUTHORIZATION_REQUIRED"


def test_adapter_rejects_forged_consumed_capability(tmp_path: Path):
    forged = ConsumedCreationAuthorization(
        authorization_digest="a" * 64,
        nonce="nonce",
        plan_id="b" * 64,
        action_digest="c" * 64,
        environment_digest="d" * 64,
        project_root=tmp_path,
        request=CreationRequest.from_mcu("STM32F429ZITx", "generated", framework="hal", language="c"),
        issued_at="2026-08-23T12:00:00Z",
        expires_at="2026-08-23T13:00:00Z",
        record_path=tmp_path / "authorization.json",
    )
    adapter = CubeMXAdapter(_environment(tmp_path), runner=lambda request: pytest.fail("CubeMX must not run"))
    with pytest.raises(CubeMXAdapterError) as error:
        adapter.generate(forged, CubeMXStagingContext(tmp_path))
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
        _native_project_root(staging)
        return ProcessResult(0, _native_fixture("mcu", staging), (Path(__file__).parent / "fixtures" / "cubemx-6.18" / "native-f429" / "stderr-warning.txt").read_text(encoding="utf-8"), False, 1, False, False)

    adapter = CubeMXAdapter(_environment(tmp_path), runner=runner)
    result = adapter.generate(_capability(tmp_path), CubeMXStagingContext(staging))
    assert result.invocations == 1
    assert len(calls) == 1
    request = calls[0]
    assert request.argv[0].endswith("java.exe")
    assert request.argv[-2] == "-q"
    assert request.argv[-1].endswith(".script")
    assert Path(request.argv[-1]).parent != staging
    assert not list(staging.glob(".stm32-toolkit-*"))
    assert "-jar" in request.argv
    assert "-Djava.net.useSystemProxies=false" in request.argv
    assert request.env is not None


@pytest.mark.parametrize(
    "source_kind,expected_load,expected_name",
    [
        ("mcu", "load STM32F429ZITx", "generated"),
        ("board", "loadboard NUCLEO-F429ZI allmodes", "generated"),
        ("ioc", "config load", "generated"),
    ],
)
def test_source_kind_script_uses_verified_commands_and_safe_deterministic_project(tmp_path: Path, source_kind: str, expected_load: str, expected_name: str):
    staging = tmp_path / "staging"
    staging.mkdir()
    observed: list[str] = []

    def runner(request):
        script = Path(request.argv[-1]).read_text(encoding="utf-8")
        observed.append(script)
        _native_project_root(staging)
        if source_kind == "mcu":
            output = _native_fixture("mcu", staging)
        elif source_kind == "board":
            output = _native_fixture("board", staging)
        else:
            output = _native_fixture("ioc", staging, Path(request.argv[-1]).parent)
        return ProcessResult(0, output, "", False, 1, False, False)

    adapter = CubeMXAdapter(_environment(tmp_path), runner=runner)
    result = adapter.generate(_capability(tmp_path, source_kind=source_kind), CubeMXStagingContext(staging))
    assert result.invocations == 1
    script = observed[0]
    assert expected_load in script
    assert f"project name {expected_name}" in script
    assert "SetStructure Advanced" in script
    assert "project structure Advanced" not in script
    assert "project path" in script and str(staging.resolve()) in script
    assert Path(result.script_path).parent != staging
    if source_kind == "ioc":
        assert "config load" in script
        assert str(tmp_path / "board.ioc") not in script
    else:
        assert "config load" not in script


def test_adapter_seeds_isolated_updater_repository_configuration_outside_staging(tmp_path: Path):
    staging = tmp_path / "staging"
    staging.mkdir()
    adapter = CubeMXAdapter(
        _environment(tmp_path),
        runner=lambda request: (_native_project_root(staging) or ProcessResult(
            0,
            _native_fixture("mcu", staging),
            "",
            False,
            1,
            False,
            False,
        )),
    )
    result = adapter.generate(_capability(tmp_path), CubeMXStagingContext(staging))
    assert result.project_root == staging / "generated"
    assert not hasattr(result, "control_root")
    assert not list(staging.glob(".stm32-toolkit-*"))


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


@pytest.mark.parametrize("mutation", ["missing_ok", "duplicate_ok", "reordered", "ko", "duplicate_bye"])
def test_static_native_transcript_protocol_variants_close(tmp_path: Path, mutation: str):
    staging = tmp_path / "staging"
    staging.mkdir()
    output = _native_fixture("mcu", staging)
    if mutation == "missing_ok":
        output = output.replace("OK\nproject name generated", "project name generated", 1)
    elif mutation == "duplicate_ok":
        output = output.replace("OK\nproject name generated", "OK\nOK\nproject name generated", 1)
    elif mutation == "reordered":
        output = output.replace("project name generated", 'project path "C:\\native-container"', 1)
    elif mutation == "ko":
        output = output.replace("OK\nproject name generated", "KO\nproject name generated", 1)
    else:
        output += "Bye bye\n"

    def runner(request):
        _native_project_root(staging)
        return ProcessResult(0, output, "", False, 1, False, False)

    with pytest.raises(CubeMXAdapterError) as error:
        CubeMXAdapter(_environment(tmp_path), runner=runner).generate(
            _capability(tmp_path), CubeMXStagingContext(staging)
        )
    assert error.value.code == "CUBEMX_PROTOCOL_INVALID"


def test_unrelated_error_log_text_does_not_override_successful_protocol(tmp_path: Path):
    staging = tmp_path / "staging"
    staging.mkdir()
    capability = _capability(tmp_path)
    output = "[ERROR] updater advertisement failed\n" + _native_fixture("mcu", staging)
    adapter = CubeMXAdapter(
        _environment(tmp_path),
        runner=lambda request: (_native_project_root(staging) or ProcessResult(0, output, "", False, 1, False, False)),
    )
    result = adapter.generate(capability, CubeMXStagingContext(staging))
    assert result.invocations == 1


@pytest.mark.parametrize(
    "process",
    [
        ProcessResult(1, "", "", False, 1, False, False),
        ProcessResult(0, "", "", True, 1, False, False),
        ProcessResult(0, "", "", False, 1, True, False),
        ProcessResult(0, "exit\nBye bye\n", "", False, 1, False, False),
    ],
)
def test_adapter_removes_control_root_on_every_native_failure(tmp_path: Path, process: ProcessResult):
    staging = tmp_path / "staging"
    staging.mkdir()
    observed: list[Path] = []

    def runner(request):
        observed.append(Path(request.argv[-1]).parent)
        return process

    adapter = CubeMXAdapter(_environment(tmp_path), runner=runner)
    with pytest.raises(CubeMXAdapterError):
        adapter.generate(_capability(tmp_path), CubeMXStagingContext(staging))
    assert observed and not observed[0].exists()


def test_closed_child_environment_binds_isolated_temp_and_tmp(tmp_path: Path):
    java = tmp_path / "jre" / "bin" / "java.exe"
    isolated_home = tmp_path / "control" / "home"
    repository = tmp_path / "Repository"
    isolated_temp = tmp_path / "control" / "temp"
    values = dict(cubemx_adapter_module._closed_environment(java, isolated_home, repository, isolated_temp))
    assert values["TEMP"] == str(isolated_temp.resolve())
    assert values["TMP"] == str(isolated_temp.resolve())
    assert values["STM32_TOOLKIT_HOME"] == str(isolated_home.resolve())


def test_adapter_rejects_extra_or_missing_native_output_root(tmp_path: Path):
    staging = tmp_path / "container"
    staging.mkdir()

    def runner(request):
        (staging / "generated").mkdir()
        (staging / "unexpected").mkdir()
        return ProcessResult(0, _native_fixture("mcu", staging), "", False, 1, False, False)

    adapter = CubeMXAdapter(_environment(tmp_path), runner=runner)
    with pytest.raises(CubeMXAdapterError) as error:
        adapter.generate(_capability(tmp_path), CubeMXStagingContext(staging))
    assert error.value.code == "CUBEMX_NATIVE_OUTPUT_INVALID"
    assert not list(staging.parent.glob(".stm32tk-cubemx-control-*"))


def test_adapter_cleans_control_root_when_setup_fails(tmp_path: Path, monkeypatch):
    staging = tmp_path / "container"
    staging.mkdir()

    def fail_seed(*args, **kwargs):
        raise CubeMXAdapterError("CUBEMX_NATIVE_OUTPUT_INVALID", "injected setup failure")

    monkeypatch.setattr(cubemx_adapter_module, "_seed_updater", fail_seed)
    adapter = CubeMXAdapter(_environment(tmp_path), runner=lambda request: pytest.fail("CubeMX must not run"))
    with pytest.raises(CubeMXAdapterError) as error:
        adapter.generate(_capability(tmp_path), CubeMXStagingContext(staging))
    assert error.value.code == "CUBEMX_NATIVE_OUTPUT_INVALID"
    assert not list(staging.parent.glob(".stm32tk-cubemx-control-*"))


def test_ioc_hash_and_staged_bytes_are_one_read(tmp_path: Path, monkeypatch):
    capability = _capability(tmp_path, source_kind="ioc")
    staging = tmp_path / "container"
    staging.mkdir()
    source = tmp_path / "board.ioc"
    original = source.read_bytes()
    reads = 0
    real_read_bytes = Path.read_bytes

    def read_once(path: Path):
        nonlocal reads
        if path.resolve() == source.resolve():
            reads += 1
            return original if reads == 1 else b"mutated-after-hash"
        return real_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", read_once)
    captured: list[bytes] = []

    def runner(request):
        control = Path(request.argv[-1]).parent
        captured.append((control / "input.ioc").read_bytes())
        _native_project_root(staging)
        return ProcessResult(0, _native_fixture("ioc", staging, control), "", False, 1, False, False)

    adapter = CubeMXAdapter(_environment(tmp_path), runner=runner)
    adapter.generate(capability, CubeMXStagingContext(staging))
    assert reads == 1
    assert captured == [original]


@pytest.mark.parametrize(
    "framework,source_kind,code",
    [("ll", "mcu", "CREATION_LL_CONFIGURATION_REQUIRED"), ("cpp", "mcu", "CREATION_CPP_CONFIGURATION_REQUIRED")],
)
def test_closed_configuration_preconditions_are_not_guessed(tmp_path: Path, framework: str, source_kind: str, code: str):
    adapter = CubeMXAdapter(_environment(tmp_path), runner=lambda request: pytest.fail("CubeMX must not run"))
    with pytest.raises(CubeMXAdapterError) as error:
        adapter.generate(_capability(tmp_path, framework="ll" if framework == "ll" else "hal", language="c" if framework == "ll" else "cpp"), CubeMXStagingContext(tmp_path))
    assert error.value.code == code
