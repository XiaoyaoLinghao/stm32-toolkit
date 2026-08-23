"""Bounded, authorization-gated STM32CubeMX CLI adapter."""

from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from stm32_toolkit.creation_authorization import ConsumedCreationAuthorization
from stm32_toolkit.process import ProcessRequest, ProcessResult, run_process


class CubeMXAdapterError(ValueError):
    """A typed, bounded CubeMX invocation/protocol failure."""

    def __init__(self, code: str, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


class ProcessRunner(Protocol):
    def __call__(self, request: ProcessRequest) -> ProcessResult: ...


@dataclass(frozen=True, slots=True)
class CubeMXStagingContext:
    staging_dir: Path
    script_name: str = ".stm32-toolkit-cubemx.script"
    timeout_seconds: int = 300

    def __post_init__(self) -> None:
        if not isinstance(self.staging_dir, Path) or not self.staging_dir.is_dir():
            raise CubeMXAdapterError("CUBEMX_NATIVE_OUTPUT_INVALID", "CubeMX staging directory is unavailable")
        if self.staging_dir.is_symlink() or ".." in self.staging_dir.parts:
            raise CubeMXAdapterError("CUBEMX_NATIVE_OUTPUT_INVALID", "CubeMX staging directory is unsafe")
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", self.script_name):
            raise CubeMXAdapterError("CUBEMX_NATIVE_OUTPUT_INVALID", "CubeMX script name is invalid")
        if type(self.timeout_seconds) is not int or not 1 <= self.timeout_seconds <= 3600:
            raise CubeMXAdapterError("CUBEMX_TIMEOUT", "CubeMX timeout is invalid")


@dataclass(frozen=True, slots=True)
class CubeMXExecutionResult:
    staging_dir: Path
    script_path: Path
    process: ProcessResult
    invocations: int = 1

    @property
    def stdout(self) -> str:
        return self.process.stdout

    @property
    def stderr(self) -> str:
        return self.process.stderr


def _safe_leaf(path: Path) -> Path:
    try:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & 0x400):
            raise OSError
        return path.resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        raise CubeMXAdapterError("CUBEMX_EXECUTION_ENVIRONMENT_CHANGED", "CubeMX executable facts changed") from None


def _portable_source(capability: ConsumedCreationAuthorization) -> str:
    source = capability.request.source.value
    if capability.request.source.kind == "ioc":
        return source.replace("\\", "/")
    return source


def _script_for(capability: ConsumedCreationAuthorization, context: CubeMXStagingContext) -> str:
    request = capability.request
    lines = [
        f"load {_portable_source(capability)}",
        f"project name {context.staging_dir.name}",
        f"project path {context.staging_dir.as_posix()}",
        "project toolchain CMake",
        "project compiler GCC",
        "project structure Advanced",
        "project generate",
        "exit",
    ]
    if request.framework == "ll":
        # The caller can only reach this path after explicit `.ioc` evidence;
        # no per-peripheral setDriver guessing is performed here.
        lines.insert(1, "# existing-ioc-ll-selection")
    if request.language == "cpp":
        lines.insert(1, "# existing-ioc-cpp-selection")
    return "\n".join(lines) + "\n"


def _closed_environment(java: Path, isolated_home: Path) -> tuple[tuple[str, str], ...]:
    # No ambient environment is inherited.  Only the Java lookup path and a
    # fixed isolated home are passed to the child; proxies point at a loopback
    # port that is not opened by Toolkit.
    return tuple(
        sorted(
            (
                ("PATH", java.parent.as_posix()),
                ("JAVA_HOME", java.parent.parent.as_posix()),
                ("STM32_TOOLKIT_HOME", isolated_home.as_posix()),
            ),
            key=lambda item: item[0],
        )
    )


class CubeMXAdapter:
    """Invoke CubeMX once with process shape and protocol fixed in code."""

    def __init__(self, environment: object, *, runner: ProcessRunner | None = None) -> None:
        self.environment = environment
        self._runner = runner or run_process

    def generate(
        self,
        capability: ConsumedCreationAuthorization,
        staging: CubeMXStagingContext,
    ) -> CubeMXExecutionResult:
        if not isinstance(capability, ConsumedCreationAuthorization):
            raise CubeMXAdapterError("CREATION_AUTHORIZATION_REQUIRED", "CubeMX requires a consumed authorization")
        if not isinstance(staging, CubeMXStagingContext):
            raise CubeMXAdapterError("CUBEMX_NATIVE_OUTPUT_INVALID", "CubeMX staging context is invalid")
        request = capability.request
        if request.framework == "ll" and request.source.kind != "ioc":
            raise CubeMXAdapterError("CREATION_LL_CONFIGURATION_REQUIRED", "LL generation requires explicit IOC driver evidence")
        if request.language == "cpp" and request.source.kind != "ioc":
            raise CubeMXAdapterError("CREATION_CPP_CONFIGURATION_REQUIRED", "C++ generation requires explicit IOC language evidence")
        try:
            java = _safe_leaf(Path(getattr(self.environment, "java_executable")))
            cubemx = _safe_leaf(Path(getattr(self.environment, "cubemx_executable")))
        except (TypeError, AttributeError):
            raise CubeMXAdapterError("CREATION_EXECUTION_ENVIRONMENT_CHANGED", "CubeMX execution facts are unavailable") from None
        isolated_home = staging.staging_dir / ".stm32-toolkit-home"
        try:
            isolated_home.mkdir(exist_ok=True)
            script = staging.staging_dir / staging.script_name
            script.write_text(_script_for(capability, staging), encoding="utf-8", newline="\n")
        except OSError:
            raise CubeMXAdapterError("CUBEMX_NATIVE_OUTPUT_INVALID", "CubeMX staging cannot be prepared") from None
        argv = (
            java.as_posix(),
            "-Djava.net.useSystemProxies=false",
            "-Dhttp.proxyHost=127.0.0.1",
            "-Dhttp.proxyPort=9",
            "-Dhttps.proxyHost=127.0.0.1",
            "-Dhttps.proxyPort=9",
            f"-Duser.home={isolated_home.as_posix()}",
            "-jar",
            cubemx.as_posix(),
            "-q",
            script.as_posix(),
        )
        try:
            process = self._runner(
                ProcessRequest(
                    argv=argv,
                    cwd=staging.staging_dir,
                    timeout_seconds=staging.timeout_seconds,
                    max_output_bytes=1024 * 1024,
                    max_lines=20_000,
                    env=_closed_environment(java, isolated_home),
                )
            )
        except CubeMXAdapterError:
            raise
        except Exception:
            raise CubeMXAdapterError("CUBEMX_EXECUTION_FAILED", "CubeMX could not be started") from None
        if not isinstance(process, ProcessResult):
            raise CubeMXAdapterError("CUBEMX_EXECUTION_FAILED", "CubeMX returned no bounded process result")
        if process.timed_out:
            raise CubeMXAdapterError("CUBEMX_TIMEOUT", "CubeMX timed out")
        if process.stdout_truncated or process.stderr_truncated:
            raise CubeMXAdapterError("CUBEMX_OUTPUT_TRUNCATED", "CubeMX output exceeded its bound")
        if process.returncode != 0:
            raise CubeMXAdapterError("CUBEMX_EXECUTION_FAILED", "CubeMX exited unsuccessfully")
        output = f"{process.stdout}\n{process.stderr}"
        if re.search(r"(?im)^\s*KO\b", output):
            raise CubeMXAdapterError("CUBEMX_PROTOCOL_INVALID", "CubeMX reported a protocol failure")
        # The fixed script has two externally observable required commands for
        # protocol purposes: load and project generate.  Intermediate command
        # logging varies between CubeMX patch releases and is not trusted.
        if not re.search(r"(?im)^\s*load\b", output) or not re.search(r"(?im)^\s*project\s+generate\b", output):
            raise CubeMXAdapterError("CUBEMX_PROTOCOL_INVALID", "CubeMX protocol echoes are incomplete")
        if len(re.findall(r"(?im)^\s*OK\b", output)) < 2 or not re.search(r"(?im)\bBye bye\b", output):
            raise CubeMXAdapterError("CUBEMX_PROTOCOL_INVALID", "CubeMX protocol completion is incomplete")
        return CubeMXExecutionResult(staging.staging_dir, script, process)

    apply = generate
    execute = generate

__all__ = ["CubeMXAdapter", "CubeMXAdapterError", "CubeMXExecutionResult", "CubeMXStagingContext"]
