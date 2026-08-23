"""Bounded, authorization-gated STM32CubeMX CLI adapter."""

from __future__ import annotations

import os
import hashlib
import re
import shutil
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
    control_root: Path | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.staging_dir, Path) or not self.staging_dir.is_dir():
            raise CubeMXAdapterError("CUBEMX_NATIVE_OUTPUT_INVALID", "CubeMX staging directory is unavailable")
        if self.staging_dir.is_symlink() or ".." in self.staging_dir.parts:
            raise CubeMXAdapterError("CUBEMX_NATIVE_OUTPUT_INVALID", "CubeMX staging directory is unsafe")
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", self.script_name):
            raise CubeMXAdapterError("CUBEMX_NATIVE_OUTPUT_INVALID", "CubeMX script name is invalid")
        if type(self.timeout_seconds) is not int or not 1 <= self.timeout_seconds <= 3600:
            raise CubeMXAdapterError("CUBEMX_TIMEOUT", "CubeMX timeout is invalid")
        if self.control_root is not None:
            if not isinstance(self.control_root, Path) or not self.control_root.is_absolute():
                raise CubeMXAdapterError("CUBEMX_NATIVE_OUTPUT_INVALID", "CubeMX control root is unsafe")
            try:
                control = self.control_root.resolve(strict=False)
                staging = self.staging_dir.resolve(strict=True)
                control.relative_to(staging)
            except ValueError:
                pass
            except (OSError, RuntimeError):
                raise CubeMXAdapterError("CUBEMX_NATIVE_OUTPUT_INVALID", "CubeMX control root is unsafe") from None
            else:
                raise CubeMXAdapterError("CUBEMX_NATIVE_OUTPUT_INVALID", "CubeMX control root must be outside staging")
            if self.control_root.exists() and self.control_root.is_symlink():
                raise CubeMXAdapterError("CUBEMX_NATIVE_OUTPUT_INVALID", "CubeMX control root is unsafe")


@dataclass(frozen=True, slots=True)
class CubeMXExecutionResult:
    staging_dir: Path
    script_path: Path
    process: ProcessResult
    invocations: int = 1
    control_root: Path | None = None

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


def _quote(value: str) -> str:
    if not value or any(char in value for char in ('"', "\r", "\n", "\x00")):
        raise CubeMXAdapterError("CUBEMX_NATIVE_OUTPUT_INVALID", "CubeMX command value is invalid")
    return '"' + value + '"'


def _control_root(context: CubeMXStagingContext) -> Path:
    if context.control_root is not None:
        return context.control_root.resolve(strict=False)
    digest = hashlib.sha256(context.staging_dir.resolve(strict=True).as_posix().encode("utf-8")).hexdigest()[:16]
    return context.staging_dir.parent / f".stm32tk-cubemx-control-{digest}"


def _project_name(capability: ConsumedCreationAuthorization) -> str:
    source = capability.request.source.value
    if capability.request.source.kind == "ioc":
        source = Path(source).stem
    value = re.sub(r"[^A-Za-z0-9_-]", "_", source)
    value = value[:64] or "STM32Project"
    if not re.match(r"[A-Za-z_]", value):
        value = "Project_" + value
    return value


def _safe_ioc_source(capability: ConsumedCreationAuthorization, control_root: Path) -> Path:
    source = capability.project_root / capability.request.source.value
    try:
        info = os.lstat(source)
        if not stat.S_ISREG(info.st_mode) or source.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & 0x400):
            raise OSError
        source = source.resolve(strict=True)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
    except (OSError, RuntimeError, ValueError):
        raise CubeMXAdapterError("CREATION_PLAN_CHANGED", "authorized IOC source is unavailable") from None
    if capability.request.source.sha256 is None or digest != capability.request.source.sha256:
        raise CubeMXAdapterError("CREATION_PLAN_CHANGED", "authorized IOC source changed")
    target = control_root / "input.ioc"
    try:
        target.write_bytes(source.read_bytes())
    except OSError:
        raise CubeMXAdapterError("CUBEMX_NATIVE_OUTPUT_INVALID", "CubeMX IOC input cannot be staged") from None
    return target


def _script_for(capability: ConsumedCreationAuthorization, context: CubeMXStagingContext, control_root: Path) -> str:
    request = capability.request
    if request.source.kind == "mcu":
        source_command = f"load {request.source.value}"
    elif request.source.kind == "board":
        source_command = f"loadboard {request.source.value} allmodes"
    elif request.source.kind == "ioc":
        source_command = f"config load {_quote(_safe_ioc_source(capability, control_root).as_posix())}"
    else:
        raise CubeMXAdapterError("CREATION_SOURCE_INVALID", "CubeMX source kind is invalid")
    staging = context.staging_dir.resolve(strict=True).as_posix()
    lines = [
        source_command,
        f"project name {_project_name(capability)}",
        f"project path {_quote(staging)}",
        "project toolchain CMake",
        "project compiler GCC",
        "SetStructure Advanced",
        "project generate",
        "exit",
    ]
    return "\n".join(lines) + "\n"


def _closed_environment(java: Path, isolated_home: Path, repository: Path) -> tuple[tuple[str, str], ...]:
    # No ambient environment is inherited.  Only the Java lookup path and a
    # fixed isolated home are passed to the child; proxies point at a loopback
    # port that is not opened by Toolkit.
    return tuple(
        sorted(
            (
                ("PATH", java.parent.as_posix()),
                ("JAVA_HOME", java.parent.parent.as_posix()),
                ("STM32_TOOLKIT_HOME", isolated_home.as_posix()),
                ("STM32CUBE_REPOSITORY", repository.as_posix()),
            ),
            key=lambda item: item[0],
        )
    )


def _repository(environment: object) -> Path:
    try:
        candidate = Path(getattr(environment, "repository")).resolve(strict=True)
        info = os.lstat(candidate)
        if not stat.S_ISDIR(info.st_mode) or candidate.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & 0x400):
            raise OSError
        return candidate
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        raise CubeMXAdapterError("CREATION_EXECUTION_ENVIRONMENT_CHANGED", "Cube firmware repository facts changed") from None


def _seed_updater(home: Path, repository: Path, software_path: Path, cubemx_version: str) -> None:
    updater_root = home / ".stm32cubemx" / "plugins" / "updater"
    updater = updater_root / "updater.ini"

    def _ini_path(path: Path) -> str:
        return path.resolve(strict=True).as_posix().rstrip("/") + "/"

    try:
        updater.parent.mkdir(parents=True, exist_ok=True)
        updater.write_text(
            "[Data]\n"
            "DataLastStamp=0\n\n"
            "[Path]\n"
            f"SoftwarePath={_ini_path(software_path)}\n"
            f"RepositoryPath={_ini_path(repository)}\n"
            f"UpdaterPath={_ini_path(updater_root)}\n\n"
            "[ReStart]\n"
            "SoftCopy=0\n\n"
            "[TimeDate]\n"
            "CheckType=1\n"
            "LastCheckStamp=0\n"
            "IntervalDayCheck=5\n"
            "LastCheckConnectionStamp=0\n\n"
            "[Version]\n"
            "SoftType=0\n"
            "DbVersion=DB.6.0.181\n"
            f"SoftVersion=MX.{cubemx_version}\n\n"
            "[Proxy]\n"
            "Type=0\n"
            "Test=2\n"
            "Authentification=0\n",
            encoding="utf-8",
            newline="\n",
        )
    except OSError:
        raise CubeMXAdapterError("CUBEMX_NATIVE_OUTPUT_INVALID", "CubeMX updater configuration cannot be prepared") from None


def _validate_protocol(output: str, commands: list[str]) -> None:
    """Validate required protocol events in CubeMX's mixed log stream."""
    if not commands or commands[-1] != "exit":
        raise CubeMXAdapterError("CUBEMX_PROTOCOL_INVALID", "CubeMX command sequence is invalid")
    index = 0
    awaiting_ok = False
    exit_seen = False
    bye_seen = False
    for raw in output.splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.fullmatch(r"KO(?:\s+.*)?", line, re.IGNORECASE):
            raise CubeMXAdapterError("CUBEMX_PROTOCOL_INVALID", "CubeMX reported a protocol failure")
        if line == "Bye bye":
            if not exit_seen or awaiting_ok or index != len(commands):
                raise CubeMXAdapterError("CUBEMX_PROTOCOL_INVALID", "CubeMX protocol completion is incomplete")
            bye_seen = True
            continue
        if index < len(commands) and line == commands[index]:
            if awaiting_ok or bye_seen:
                raise CubeMXAdapterError("CUBEMX_PROTOCOL_INVALID", "CubeMX protocol command order is invalid")
            index += 1
            if line == "exit":
                exit_seen = True
            else:
                awaiting_ok = True
            continue
        if line in commands:
            raise CubeMXAdapterError("CUBEMX_PROTOCOL_INVALID", "CubeMX protocol command order is invalid")
        if line == "OK":
            if awaiting_ok:
                awaiting_ok = False
            continue
        # Native log4j/INFO/WARN/progress text is not protocol.
    if awaiting_ok or index != len(commands) or not exit_seen or not bye_seen:
        raise CubeMXAdapterError("CUBEMX_PROTOCOL_INVALID", "CubeMX protocol completion is incomplete")


def _remove_control_root(control_root: Path) -> None:
    try:
        if control_root.exists():
            shutil.rmtree(control_root)
    except OSError:
        raise CubeMXAdapterError("CUBEMX_NATIVE_OUTPUT_INVALID", "CubeMX control files cannot be cleaned") from None


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
        if not capability._is_store_issued():
            raise CubeMXAdapterError("CREATION_AUTHORIZATION_REQUIRED", "CubeMX requires the winning consumed authorization")
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
            repository = _repository(self.environment)
        except (TypeError, AttributeError):
            raise CubeMXAdapterError("CREATION_EXECUTION_ENVIRONMENT_CHANGED", "CubeMX execution facts are unavailable") from None
        control_root: Path | None = None
        try:
            control_root = _control_root(staging)
            isolated_home = control_root / "home"
            control_root.mkdir(parents=True, exist_ok=True)
            isolated_home.mkdir(parents=True, exist_ok=True)
            _seed_updater(isolated_home, repository, cubemx.parent, str(getattr(self.environment, "cubemx_version", "6.18.1-RC2")))
            script = control_root / staging.script_name
            script_text = _script_for(capability, staging, control_root)
            script.write_text(script_text, encoding="utf-8", newline="\n")
        except OSError:
            raise CubeMXAdapterError("CUBEMX_NATIVE_OUTPUT_INVALID", "CubeMX control files cannot be prepared") from None
        commands = [line for line in script_text.splitlines() if line and not line.startswith("#")]
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
                    env=_closed_environment(java, isolated_home, repository),
                )
            )
        except CubeMXAdapterError:
            if control_root is not None:
                _remove_control_root(control_root)
            raise
        except Exception:
            if control_root is not None:
                _remove_control_root(control_root)
            raise CubeMXAdapterError("CUBEMX_EXECUTION_FAILED", "CubeMX could not be started") from None
        if not isinstance(process, ProcessResult):
            raise CubeMXAdapterError("CUBEMX_EXECUTION_FAILED", "CubeMX returned no bounded process result")
        try:
            if process.timed_out:
                raise CubeMXAdapterError("CUBEMX_TIMEOUT", "CubeMX timed out")
            if process.stdout_truncated or process.stderr_truncated:
                raise CubeMXAdapterError("CUBEMX_OUTPUT_TRUNCATED", "CubeMX output exceeded its bound")
            if process.returncode != 0:
                raise CubeMXAdapterError("CUBEMX_EXECUTION_FAILED", "CubeMX exited unsuccessfully")
            output = f"{process.stdout}\n{process.stderr}"
            _validate_protocol(output, commands)
        except CubeMXAdapterError:
            if control_root is not None:
                _remove_control_root(control_root)
            raise
        return CubeMXExecutionResult(staging.staging_dir, script, process, control_root=control_root)

    apply = generate
    execute = generate

__all__ = ["CubeMXAdapter", "CubeMXAdapterError", "CubeMXExecutionResult", "CubeMXStagingContext"]
