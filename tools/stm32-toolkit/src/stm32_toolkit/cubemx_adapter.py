"""Bounded, authorization-gated STM32CubeMX CLI adapter."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from stm32_toolkit.creation_authorization import ConsumedCreationAuthorization
from stm32_toolkit.process import ProcessRequest, ProcessResult, run_process


_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_MAX_IOC_BYTES = 1 * 1024 * 1024
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


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
    """One empty, same-volume generation container owned by apply."""

    staging_dir: Path
    script_name: str = ".stm32-toolkit-cubemx.script"
    timeout_seconds: int = 300

    def __post_init__(self) -> None:
        if not isinstance(self.staging_dir, Path) or not self.staging_dir.is_dir():
            raise CubeMXAdapterError("CUBEMX_NATIVE_OUTPUT_INVALID", "CubeMX staging directory is unavailable")
        try:
            info = os.lstat(self.staging_dir)
            resolved = self.staging_dir.resolve(strict=True)
            if not stat.S_ISDIR(info.st_mode) or self.staging_dir.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & _REPARSE):
                raise OSError
            if resolved != self.staging_dir.absolute().resolve(strict=True):
                raise OSError
        except (OSError, RuntimeError, ValueError):
            raise CubeMXAdapterError("CUBEMX_NATIVE_OUTPUT_INVALID", "CubeMX staging directory is unsafe") from None
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", self.script_name):
            raise CubeMXAdapterError("CUBEMX_NATIVE_OUTPUT_INVALID", "CubeMX script name is invalid")
        if type(self.timeout_seconds) is not int or not 1 <= self.timeout_seconds <= 3600:
            raise CubeMXAdapterError("CUBEMX_TIMEOUT", "CubeMX timeout is invalid")


@dataclass(frozen=True, slots=True)
class CubeMXExecutionResult:
    """The only native artifact exposed after adapter cleanup."""

    project_root: Path
    script_path: Path
    process: ProcessResult
    invocations: int = 1

    @property
    def stdout(self) -> str:
        return self.process.stdout

    @property
    def stderr(self) -> str:
        return self.process.stderr


def _safe_regular(path: Path) -> Path:
    try:
        lexical = path.absolute()
        resolved = lexical.resolve(strict=True)
        current = lexical
        while True:
            info = os.lstat(current)
            if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & _REPARSE):
                raise OSError
            if current == current.parent:
                break
            current = current.parent
        info = os.lstat(resolved)
        if not stat.S_ISREG(info.st_mode) or resolved.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & _REPARSE):
            raise OSError
        return resolved
    except (OSError, RuntimeError, ValueError):
        raise CubeMXAdapterError("CREATION_EXECUTION_ENVIRONMENT_CHANGED", "CubeMX executable facts changed") from None


def _safe_directory(path: Path) -> Path:
    try:
        lexical = path.absolute()
        resolved = lexical.resolve(strict=True)
        current = lexical
        while True:
            info = os.lstat(current)
            if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & _REPARSE):
                raise OSError
            if current == current.parent:
                break
            current = current.parent
        info = os.lstat(resolved)
        if not stat.S_ISDIR(info.st_mode) or resolved.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & _REPARSE):
            raise OSError
        return resolved
    except (OSError, RuntimeError, ValueError):
        raise CubeMXAdapterError("CREATION_EXECUTION_ENVIRONMENT_CHANGED", "Cube firmware repository facts changed") from None


def _quote(value: str) -> str:
    if not value or any(char in value for char in ('"', "\r", "\n", "\x00")):
        raise CubeMXAdapterError("CUBEMX_NATIVE_OUTPUT_INVALID", "CubeMX command value is invalid")
    return '"' + value + '"'


def _control_root(context: CubeMXStagingContext) -> Path:
    digest = hashlib.sha256(str(context.staging_dir.resolve(strict=True)).encode("utf-8")).hexdigest()[:16]
    return context.staging_dir.resolve(strict=True).parent / f".stm32tk-cubemx-control-{digest}"


def _destination_leaf(capability: ConsumedCreationAuthorization) -> str:
    value = capability.request.destination.replace("\\", "/").split("/")[-1]
    if value in {"", ".", ".."} or _SAFE_NAME.fullmatch(value) is None:
        raise CubeMXAdapterError("CREATION_DESTINATION_CHANGED", "authorized destination leaf is invalid")
    return value


def _safe_regular_inside(path: Path, root: Path) -> Path:
    try:
        lexical = path.absolute()
        resolved = lexical.resolve(strict=True)
        root = root.resolve(strict=True)
        resolved.relative_to(root)
        info = os.lstat(lexical)
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & _REPARSE):
            raise OSError
        current = lexical.parent
        while True:
            current.relative_to(root)
            parent_info = os.lstat(current)
            if stat.S_ISLNK(parent_info.st_mode) or bool(getattr(parent_info, "st_file_attributes", 0) & _REPARSE):
                raise OSError
            if current == root:
                break
            current = current.parent
        info = os.lstat(resolved)
        if not stat.S_ISREG(info.st_mode) or resolved.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & _REPARSE):
            raise OSError
        return resolved
    except (OSError, RuntimeError, ValueError):
        raise CubeMXAdapterError("CREATION_PLAN_CHANGED", "authorized IOC source is unavailable") from None


def _safe_ioc_source(capability: ConsumedCreationAuthorization, control_root: Path) -> Path:
    try:
        project_root = capability.project_root.resolve(strict=True)
        source = _safe_regular_inside(project_root / capability.request.source.value, project_root)
        info = os.lstat(source)
        if info.st_size > _MAX_IOC_BYTES:
            raise CubeMXAdapterError("CREATION_PLAN_CHANGED", "authorized IOC source is oversized")
        data = source.read_bytes()
    except CubeMXAdapterError:
        raise
    except (OSError, RuntimeError, ValueError):
        raise CubeMXAdapterError("CREATION_PLAN_CHANGED", "authorized IOC source is unavailable") from None
    expected = capability.request.source.sha256
    if expected is None or hashlib.sha256(data).hexdigest() != expected:
        raise CubeMXAdapterError("CREATION_PLAN_CHANGED", "authorized IOC source changed")
    target = control_root / "input.ioc"
    try:
        target.write_bytes(data)
    except OSError:
        raise CubeMXAdapterError("CUBEMX_NATIVE_OUTPUT_INVALID", "CubeMX IOC input cannot be staged") from None
    return target


def _script_for(
    capability: ConsumedCreationAuthorization,
    context: CubeMXStagingContext,
    control_root: Path,
    environment: object,
) -> str:
    request = capability.request
    if request.source.kind == "mcu":
        token = getattr(environment, "native_source_token", None)
        if not isinstance(token, str) or not token or re.fullmatch(r"STM32[A-Za-z0-9]+", token) is None:
            raise CubeMXAdapterError("CREATION_EXECUTION_ENVIRONMENT_CHANGED", "CubeMX MCU descriptor token is unavailable")
        source_command = f"load {token}"
    elif request.source.kind == "board":
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", request.source.value) is None:
            raise CubeMXAdapterError("CREATION_SOURCE_INVALID", "CubeMX board token is invalid")
        source_command = f"loadboard {request.source.value} allmodes"
    elif request.source.kind == "ioc":
        source_command = f"config load {_quote(str(_safe_ioc_source(capability, control_root).resolve(strict=True)))}"
    else:
        raise CubeMXAdapterError("CREATION_SOURCE_INVALID", "CubeMX source kind is invalid")
    staging = str(context.staging_dir.resolve(strict=True))
    lines = [
        source_command,
        f"project name {_destination_leaf(capability)}",
        f"project path {_quote(staging)}",
        "project toolchain CMake",
        "project compiler GCC",
        "SetStructure Advanced",
        "project generate",
        "exit",
    ]
    return "\n".join(lines) + "\n"


def _closed_environment(
    java: Path,
    isolated_home: Path,
    repository: Path,
    isolated_temp: Path,
) -> tuple[tuple[str, str], ...]:
    """Return the complete child environment; no ambient variables leak."""
    return tuple(
        sorted(
            (
                ("PATH", str(java.parent.resolve(strict=False))),
                ("JAVA_HOME", str(java.parent.parent.resolve(strict=False))),
                ("STM32_TOOLKIT_HOME", str(isolated_home.resolve(strict=False))),
                ("STM32CUBE_REPOSITORY", str(repository.resolve(strict=False))),
                ("TEMP", str(isolated_temp.resolve(strict=False))),
                ("TMP", str(isolated_temp.resolve(strict=False))),
            ),
            key=lambda item: item[0],
        )
    )


def _repository(environment: object) -> Path:
    try:
        return _safe_directory(Path(getattr(environment, "repository")))
    except (AttributeError, TypeError, ValueError):
        raise CubeMXAdapterError("CREATION_EXECUTION_ENVIRONMENT_CHANGED", "Cube firmware repository facts changed") from None


def _seed_updater(home: Path, repository: Path, software_path: Path, cubemx_version: str) -> None:
    updater_root = home / ".stm32cubemx" / "plugins" / "updater"
    updater = updater_root / "updater.ini"

    def _ini_path(path: Path) -> str:
        return str(path.resolve(strict=True)).rstrip("\\/") + "\\"

    try:
        updater_root.mkdir(parents=True, exist_ok=True)
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
    """Validate stdout protocol events while permitting native log noise."""
    if len(commands) != 8 or commands[-1] != "exit":
        raise CubeMXAdapterError("CUBEMX_PROTOCOL_INVALID", "CubeMX command sequence is invalid")
    index = 0
    awaiting_ok = False
    bye_seen = False
    for raw in output.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line == "OK":
            if not awaiting_ok:
                raise CubeMXAdapterError("CUBEMX_PROTOCOL_INVALID", "CubeMX returned an unexpected OK")
            awaiting_ok = False
            continue
        if line == "Bye bye":
            if bye_seen or index != len(commands) or awaiting_ok:
                raise CubeMXAdapterError("CUBEMX_PROTOCOL_INVALID", "CubeMX protocol completion is invalid")
            bye_seen = True
            continue
        if line == "KO" or line.startswith("KO "):
            raise CubeMXAdapterError("CUBEMX_PROTOCOL_INVALID", "CubeMX reported a protocol failure")
        if index < len(commands) and line == commands[index]:
            if awaiting_ok or bye_seen:
                raise CubeMXAdapterError("CUBEMX_PROTOCOL_INVALID", "CubeMX protocol command order is invalid")
            index += 1
            if line != "exit":
                awaiting_ok = True
            continue
        if line in commands:
            raise CubeMXAdapterError("CUBEMX_PROTOCOL_INVALID", "CubeMX protocol command order is invalid")
        # CubeMX emits INFO/WARN/ERROR lines on stdout in offline mode. They
        # are retained as evidence but are not protocol events.
    if index != len(commands) or awaiting_ok or not bye_seen:
        raise CubeMXAdapterError("CUBEMX_PROTOCOL_INVALID", "CubeMX protocol completion is incomplete")


def _native_output_root(container: Path, project_name: str) -> Path:
    try:
        entries = sorted(container.iterdir(), key=lambda path: path.name.casefold())
    except OSError:
        raise CubeMXAdapterError("CUBEMX_NATIVE_OUTPUT_INVALID", "CubeMX output container cannot be inspected") from None
    if len(entries) != 1 or entries[0].name != project_name:
        raise CubeMXAdapterError("CUBEMX_NATIVE_OUTPUT_INVALID", "CubeMX output root is not the authorized project child")
    child = entries[0]
    try:
        info = os.lstat(child)
        resolved = child.resolve(strict=True)
        resolved.relative_to(container.resolve(strict=True))
        if not stat.S_ISDIR(info.st_mode) or child.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & _REPARSE):
            raise OSError
    except (OSError, RuntimeError, ValueError):
        raise CubeMXAdapterError("CUBEMX_NATIVE_OUTPUT_INVALID", "CubeMX output root is unsafe") from None
    return resolved


def _remove_control_root(control_root: Path) -> None:
    try:
        if not os.path.lexists(control_root):
            return
        info = os.lstat(control_root)
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & _REPARSE):
            raise OSError
        if not stat.S_ISDIR(info.st_mode):
            raise OSError
        shutil.rmtree(control_root)
        if os.path.lexists(control_root):
            raise OSError
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
            java = _safe_regular(Path(getattr(self.environment, "java_executable")))
            cubemx = _safe_regular(Path(getattr(self.environment, "cubemx_executable")))
            repository = _repository(self.environment)
        except (AttributeError, TypeError, ValueError):
            raise CubeMXAdapterError("CREATION_EXECUTION_ENVIRONMENT_CHANGED", "CubeMX execution facts are unavailable") from None
        control_root = _control_root(staging)
        script: Path | None = None
        try:
            if os.path.lexists(control_root):
                raise CubeMXAdapterError("CUBEMX_NATIVE_OUTPUT_INVALID", "CubeMX control root is not fresh")
            container = staging.staging_dir.resolve(strict=True)
            if any(container.iterdir()):
                raise CubeMXAdapterError("CUBEMX_NATIVE_OUTPUT_INVALID", "CubeMX output container is not empty")
            project_name = _destination_leaf(capability)
            isolated_home = control_root / "home"
            isolated_temp = control_root / "temp"
            control_root.mkdir(parents=True, exist_ok=False)
            isolated_home.mkdir(parents=True, exist_ok=False)
            isolated_temp.mkdir(parents=True, exist_ok=False)
            _seed_updater(isolated_home, repository, cubemx.parent, str(getattr(self.environment, "cubemx_version", "6.18.1-RC2")))
            script = control_root / staging.script_name
            script_text = _script_for(capability, staging, control_root, self.environment)
            script.write_text(script_text, encoding="utf-8", newline="\n")
            commands = script_text.splitlines()
            process = self._runner(
                ProcessRequest(
                    argv=(
                        str(java),
                        "-Djava.net.useSystemProxies=false",
                        "-Dhttp.proxyHost=127.0.0.1",
                        "-Dhttp.proxyPort=9",
                        "-Dhttps.proxyHost=127.0.0.1",
                        "-Dhttps.proxyPort=9",
                        f"-Duser.home={isolated_home}",
                        "-jar",
                        str(cubemx),
                        "-q",
                        str(script),
                    ),
                    cwd=container,
                    timeout_seconds=staging.timeout_seconds,
                    max_output_bytes=8 * 1024 * 1024,
                    max_lines=20_000,
                    env=_closed_environment(java, isolated_home, repository, isolated_temp),
                )
            )
            if not isinstance(process, ProcessResult):
                raise CubeMXAdapterError("CUBEMX_EXECUTION_FAILED", "CubeMX returned no bounded process result")
            if process.timed_out:
                raise CubeMXAdapterError("CUBEMX_TIMEOUT", "CubeMX timed out")
            if process.stdout_truncated or process.stderr_truncated:
                raise CubeMXAdapterError("CUBEMX_OUTPUT_TRUNCATED", "CubeMX output exceeded its bound")
            if process.returncode != 0:
                raise CubeMXAdapterError("CUBEMX_EXECUTION_FAILED", "CubeMX exited unsuccessfully")
            _validate_protocol(process.stdout, commands)
            project_root = _native_output_root(container, project_name)
            return CubeMXExecutionResult(project_root, script, process)
        except CubeMXAdapterError:
            raise
        except (OSError, RuntimeError, TypeError, ValueError):
            raise CubeMXAdapterError("CUBEMX_EXECUTION_FAILED", "CubeMX could not be started") from None
        finally:
            _remove_control_root(control_root)

    apply = generate
    execute = generate


__all__ = ["CubeMXAdapter", "CubeMXAdapterError", "CubeMXExecutionResult", "CubeMXStagingContext"]
