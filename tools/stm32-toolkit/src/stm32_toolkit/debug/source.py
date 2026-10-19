"""Bounded, read-only C declaration discovery through an installed Clang frontend.

This adapter owns source discovery only.  DWARF remains the sole authority for
addresses and the existing read engine remains the sole selector authority.
"""

from __future__ import annotations

import ctypes
from bisect import bisect_right
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from stm32_toolkit.project_model import ProjectModel
from stm32_toolkit.generation.managed_files import CORE_CPU_FLAGS
from stm32_toolkit.process import _terminate_tree

if os.name == "nt":
    from stm32_toolkit.debug.source_windows import OwnedWindowsJob


MAX_UNITS = 256
MAX_DECLARATIONS = 100_000
MAX_FUNCTIONS = 100_000
MAX_UNIT_AST_BYTES = 80 * 1024 * 1024
MAX_UNIT_PREPROCESSED_BYTES = 32 * 1024 * 1024
MAX_TOTAL_AST_BYTES = 1024 * 1024 * 1024
MAX_UNIT_SECONDS = 30.0
MAX_TOTAL_SECONDS = 120.0
_MAX_COMPDB_BYTES = 8 * 1024 * 1024
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_COMPILER_RULE = re.compile(r"^build [^\r\n]+?: (C_COMPILER__[^\s:]+)", re.M)
_LINE_MARKER = re.compile(rb'^#\s+(\d+)\s+"((?:[^"\\]|\\.)*)"')
_KEEP_EXACT = frozenset({"-mthumb", "-mno-thumb", "-fshort-enums", "-funsigned-char", "-fsigned-char"})
_DROP_EXACT = frozenset({"-c", "-MD", "-MMD", "-MP", "-g", "-g0", "-g1", "-g2", "-g3", "-Og", "-O0", "-O1", "-O2", "-O3", "-Os", "-Oz", "-ffunction-sections", "-fdata-sections", "-fno-common", "-fno-builtin", "-fstack-usage"})
_KEEP_PREFIX = ("-std=", "-mcpu=", "-march=", "-mfpu=", "-mfloat-abi=", "-mabi=", "-fpack-struct=")


class SourceCatalogError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class SourceIssue:
    unit: str | None
    code: str
    message: str

    def to_dict(self) -> dict[str, object]:
        return {"unit": self.unit, "code": self.code, "message": self.message}


@dataclass(frozen=True)
class SourceDeclaration:
    id: str
    entity_id: str
    name: str
    type_name: str
    file: str
    line: int | None
    column: int | None
    storage: str
    scope_kind: str
    function: str | None
    scope_path: tuple[str, ...]
    translation_units: tuple[str, ...]
    function_id: str | None = None


@dataclass(frozen=True)
class SourceFunction:
    id: str
    name: str
    file: str
    line: int | None
    column: int | None
    translation_units: tuple[str, ...]


@dataclass(frozen=True)
class SourceIndex:
    engine_name: str
    engine_version: str
    input_kind: str
    total_units: int
    parsed_units: int
    issues: tuple[SourceIssue, ...]
    truncated: bool
    declarations: tuple[SourceDeclaration, ...]
    argument_fingerprint: str
    functions: tuple[SourceFunction, ...] = ()

    @property
    def complete(self) -> bool:
        return self.parsed_units == self.total_units and not self.issues and not self.truncated


def _safe_path(root: Path, candidate: Path, *, directory: bool = False) -> tuple[Path, str]:
    """Validate lexical and resolved containment, including Windows junctions."""
    try:
        lexical = candidate if candidate.is_absolute() else root / candidate
        lexical = lexical.absolute()
        relative = lexical.relative_to(root)
        current = root
        for component in relative.parts:
            current /= component
            info = os.lstat(current)
            if current.is_symlink() or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT:
                raise ValueError
        resolved = lexical.resolve(strict=True)
        if resolved != lexical or (not resolved.is_dir() if directory else not resolved.is_file()):
            raise ValueError
        relative = resolved.relative_to(root)
        text = relative.as_posix()
        if text in ("", ".") or len(text) > 512:
            raise ValueError
        return resolved, text
    except (OSError, RuntimeError, ValueError):
        raise SourceCatalogError("MONITOR_SOURCE_INDEX_FAILED", "Source path is outside the verified project") from None


def _installed_tool(name: str) -> Path | None:
    candidates: list[Path] = []
    st = Path("C:/ST")
    if st.is_dir():
        for root in sorted(st.glob("STM32CubeCLT_*/"), reverse=True)[:16]:
            if name == "clang":
                candidates.append(root / "st-arm-clang/bin/starm-clang.exe")
            elif name == "gcc":
                candidates.append(root / "GNU-tools-for-STM32/bin/arm-none-eabi-gcc.exe")
            else:
                candidates.append(root / "Ninja/bin/ninja.exe")
    if name == "clang":
        candidates.extend((Path("C:/Program Files/LLVM/bin/clang.exe"), Path("C:/LLVM/bin/clang.exe")))
        path = shutil.which("clang.exe") or shutil.which("clang")
    elif name == "gcc":
        path = shutil.which("arm-none-eabi-gcc.exe") or shutil.which("arm-none-eabi-gcc")
    else:
        path = shutil.which("ninja.exe") or shutil.which("ninja")
    if path:
        candidates.append(Path(path))
    expected = ({"starm-clang.exe", "clang.exe", "clang"} if name == "clang" else
                {"arm-none-eabi-gcc.exe", "arm-none-eabi-gcc"} if name == "gcc" else
                {"ninja.exe", "ninja"})
    for candidate in candidates:
        try:
            if candidate.name.lower() in expected and candidate.is_file() and not candidate.is_symlink():
                return candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
    return None


def _manifest_preset(model: ProjectModel) -> str | None:
    elf = getattr(model.build, "elf", None)
    if isinstance(elf, str):
        for preset in ("arm-debug", "arm-release"):
            if elf.startswith(f"build/{preset}/") and preset in model.build.presets:
                return preset
    return "arm-debug" if "arm-debug" in model.build.presets else None


def _template_options(model: ProjectModel, preset: str | None) -> list[str]:
    """The target/configuration flags from the existing managed CMake template."""
    target = getattr(model, "target", None)
    core = getattr(target, "core", None)
    result: list[str] = []
    if core is not None:
        cpu = CORE_CPU_FLAGS.get(core)
        if cpu is None:
            raise SourceCatalogError("MONITOR_SOURCE_INDEX_FAILED", "Target core has no supported C template")
        result.extend((cpu, "-mthumb"))
        fpu = getattr(target, "fpu", None)
        abi = getattr(target, "float_abi", None)
        if fpu is not None:
            if abi is None:
                raise SourceCatalogError("MONITOR_SOURCE_INDEX_FAILED", "Target ABI is incomplete")
            result.extend(("-mfpu=" + fpu, "-mfloat-abi=" + abi))
    result.extend(model.build.compile_options)
    if preset == "arm-debug":
        result.append("-Og")
    elif preset == "arm-release":
        result.append("-O2")
    return result


def _semantic_key(flags: list[str]) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
    includes: list[str] = []
    macros: dict[str, str] = {}
    other: dict[str, str] = {}
    cursor = 0
    while cursor < len(flags):
        flag = flags[cursor]
        cursor += 1
        if flag in {"-I", "-isystem", "-iquote", "-include"}:
            includes.extend((flag, flags[cursor]))
            cursor += 1
        elif flag.startswith(("-D", "-U")):
            macros[flag[2:].split("=", 1)[0]] = flag
        else:
            key = next((prefix for prefix in _KEEP_PREFIX if flag.startswith(prefix)), flag)
            if flag in {"-mthumb", "-mno-thumb"}:
                key = "thumb"
            elif flag.startswith("-O"):
                key = "optimization"
            elif flag in {"-funsigned-char", "-fsigned-char"}:
                key = "char-signedness"
            other[key] = flag
    return tuple(includes), tuple(sorted(macros.items())), tuple(sorted(other.items()))


def _windows_argv(command: str) -> list[str]:
    if not command or len(command) > 65_536:
        raise ValueError("compile command is invalid")
    if os.name != "nt":
        raise ValueError("Windows C command discovery requires Windows")
    argc = ctypes.c_int()
    parse = ctypes.windll.shell32.CommandLineToArgvW
    parse.argtypes = (ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int))
    parse.restype = ctypes.POINTER(ctypes.c_wchar_p)
    pointer = parse(command, ctypes.byref(argc))
    if not pointer:
        raise ValueError("compile command is invalid")
    try:
        return [pointer[index] for index in range(argc.value)]
    finally:
        ctypes.windll.kernel32.LocalFree(pointer)


@dataclass(frozen=True)
class SourcePlan:
    commands: tuple[tuple[str, Path, tuple[str, ...]], ...]
    input_kind: str
    engine_version: str
    fingerprint: str


class ClangSourceAdapter:
    """One owner for compiler children and a finite discovery budget."""

    def __init__(self, compiler: Path | None = None, ninja: Path | None = None,
                 preprocessor: Path | None = None) -> None:
        self.compiler = compiler or _installed_tool("clang")
        self.ninja = ninja or _installed_tool("ninja")
        self.preprocessor = preprocessor or _installed_tool("gcc")
        self._closed = threading.Event()
        self._child_lock = threading.Lock()
        self._run_lock = threading.Lock()
        self._index_lock = threading.Lock()
        self._child: subprocess.Popen[bytes] | None = None
        self._job = None

    def close(self) -> None:
        self._closed.set()
        with self._child_lock:
            child = self._child
            job = self._job
            try:
                if job is not None:
                    job.close()
            finally:
                try:
                    if child is not None:
                        if job is None and child.poll() is None:
                            _terminate_tree(child)
                        else:
                            self._reap_root(child)
                finally:
                    if child is not None and child.poll() is not None and self._child is child:
                        self._child = None
                    if job is not None and job.closed and self._job is job:
                        self._job = None

    @staticmethod
    def _reap_root(child: subprocess.Popen[bytes]) -> None:
        if child.poll() is None:
            try:
                child.kill()
            except OSError:
                pass
        try:
            child.wait(timeout=1)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=1)

    def _start_child(self, argv: list[str], cwd: Path):
        job = None
        child: subprocess.Popen[bytes] | None = None
        try:
            # Publish, assign and resume as one owned transition. close() sets
            # the event before entering this lock, and is checked before resume.
            with self._child_lock:
                if self._closed.is_set():
                    raise SourceCatalogError("MONITOR_SOURCE_INDEX_FAILED", "Source parser was closed")
                job = OwnedWindowsJob() if os.name == "nt" else None
                self._job = job
                child = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, shell=False,
                                         **({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000004}
                                            if os.name == "nt" else {"start_new_session": True}))
                self._child = child
                self._job = job
                if job is not None:
                    job.assign(int(child._handle))
                    if self._closed.is_set():
                        raise SourceCatalogError("MONITOR_SOURCE_INDEX_FAILED", "Source parser was closed")
                    job.resume_initial_thread(child.pid)
            return child, job
        except BaseException:
            cleanup_error: BaseException | None = None
            if job is not None:
                try:
                    job.close()
                except BaseException as error:
                    self._closed.set()
                    cleanup_error = error
            try:
                if child is not None:
                    try:
                        self._reap_root(child)
                    finally:
                        if child.stdout is not None:
                            child.stdout.close()
                        if child.stderr is not None:
                            child.stderr.close()
            except BaseException as error:
                self._closed.set()
                if cleanup_error is None:
                    cleanup_error = error
            finally:
                with self._child_lock:
                    if self._child is child:
                        self._child = None
                    if self._job is job and (job is None or job.closed):
                        self._job = None
            if cleanup_error is not None:
                raise cleanup_error
            raise

    def _run(self, argv: list[str], cwd: Path, byte_limit: int, seconds: float) -> bytes:
        # Dedicated bounded drains enforce limits as bytes arrive, including
        # stderr.  No compiler output is ever spooled or captured without a cap.
        if byte_limit < 1 or seconds <= 0:
            raise SourceCatalogError("MONITOR_SOURCE_INDEX_FAILED", "Source parser budget was exhausted")
        deadline = time.monotonic() + seconds
        while True:
            if self._closed.is_set():
                raise SourceCatalogError("MONITOR_SOURCE_INDEX_FAILED", "Source parser was closed")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SourceCatalogError("MONITOR_SOURCE_INDEX_FAILED", "Source parser budget was exhausted")
            if self._run_lock.acquire(timeout=min(remaining, 0.05)):
                break
        try:
            if self._closed.is_set():
                raise SourceCatalogError("MONITOR_SOURCE_INDEX_FAILED", "Source parser was closed")
            if time.monotonic() >= deadline:
                raise SourceCatalogError("MONITOR_SOURCE_INDEX_FAILED", "Source parser budget was exhausted")
            try:
                child, job = self._start_child(argv, cwd)
            except (OSError, subprocess.SubprocessError):
                raise SourceCatalogError("MONITOR_SOURCE_INDEX_FAILED", "Source parser could not start within policy") from None
            output = bytearray()
            errors = bytearray()
            exceeded = threading.Event()
            finished = [threading.Event(), threading.Event()]

            def drain(stream: object, sink: bytearray, limit: int, done: threading.Event) -> None:
                try:
                    while True:
                        chunk = stream.read1(64 * 1024)
                        if not chunk:
                            break
                        allowance = max(0, limit - len(sink))
                        if len(chunk) > allowance:
                            sink.extend(chunk[:allowance])
                            exceeded.set()
                            break
                        sink.extend(chunk)
                except OSError:
                    exceeded.set()
                finally:
                    done.set()

            stdout_thread = threading.Thread(target=drain, args=(child.stdout, output, byte_limit, finished[0]), daemon=True)
            stderr_thread = threading.Thread(target=drain, args=(child.stderr, errors, 256 * 1024, finished[1]), daemon=True)
            stdout_thread.start()
            stderr_thread.start()
            failed = False
            try:
                while True:
                    if self._closed.is_set() or exceeded.is_set() or time.monotonic() >= deadline:
                        failed = True
                        if job is not None:
                            job.close()
                        else:
                            _terminate_tree(child)
                        break
                    if child.poll() is not None and all(done.is_set() for done in finished):
                        break
                    time.sleep(0.01)
                stdout_thread.join(timeout=1)
                stderr_thread.join(timeout=1)
                if (failed or child.returncode != 0 or exceeded.is_set()
                        or not all(done.is_set() for done in finished)):
                    raise SourceCatalogError("MONITOR_SOURCE_INDEX_FAILED", "Source parser exceeded a fixed limit or could not process a compilation unit")
                return bytes(output)
            finally:
                cleanup_error: BaseException | None = None
                try:
                    if job is not None:
                        job.close()
                    elif child.poll() is None:
                        _terminate_tree(child)
                except BaseException as error:
                    cleanup_error = error
                    self._closed.set()
                try:
                    self._reap_root(child)
                except BaseException as error:
                    if cleanup_error is None:
                        cleanup_error = error
                    self._closed.set()
                for stream in (child.stdout, child.stderr):
                    try:
                        stream.close()
                    except BaseException as error:
                        if cleanup_error is None:
                            cleanup_error = error
                        self._closed.set()
                with self._child_lock:
                    if self._child is child:
                        self._child = None
                    if self._job is job and (job is None or job.closed):
                        self._job = None
                if cleanup_error is not None:
                    raise cleanup_error
        except (OSError, subprocess.SubprocessError):
            raise SourceCatalogError("MONITOR_SOURCE_INDEX_FAILED", "Source parser cleanup failed within policy") from None
        finally:
            self._run_lock.release()

    def _version(self, root: Path) -> str:
        if self.compiler is None or self.preprocessor is None:
            raise SourceCatalogError("MONITOR_SOURCE_ENGINE_MISSING", "Installed GNU Arm GCC and Clang frontends are required")
        clang = self._run([str(self.compiler), "--version"], root, 4096, 5.0)
        gcc = self._run([str(self.preprocessor), "--version"], root, 4096, 5.0)
        clang_line = clang.decode("utf-8", "replace").splitlines()[0].strip() if clang else ""
        gcc_line = gcc.decode("utf-8", "replace").splitlines()[0].strip() if gcc else ""
        if ("clang" not in clang_line.casefold() or "gcc" not in gcc_line.casefold()
                or len(clang_line) > 160 or len(gcc_line) > 160):
            raise SourceCatalogError("MONITOR_SOURCE_ENGINE_MISSING", "Installed source frontends are unsupported")
        return f"gcc:{gcc_line};clang:{clang_line}"

    def _compdb(self, model: ProjectModel) -> list[tuple[str, Path, list[str]]] | None:
        if self.ninja is None:
            return None
        root = model.project_root
        for preset in model.build.presets[:16]:
            candidate = root / "build" / preset
            if not (candidate / "build.ninja").exists():
                continue
            try:
                build_dir, _ = _safe_path(root, candidate, directory=True)
                build_ninja, _ = _safe_path(root, build_dir / "build.ninja")
                cache, _ = _safe_path(root, build_dir / "CMakeCache.txt")
                if cache.stat().st_size > 1024 * 1024:
                    return None
                cache_text = cache.read_text(encoding="utf-8")
                home = re.search(r"^CMAKE_HOME_DIRECTORY:INTERNAL=(.+)$", cache_text, re.M)
                build_type = re.search(r"^CMAKE_BUILD_TYPE:STRING=(.+)$", cache_text, re.M)
                toolchain = re.search(r"^CMAKE_TOOLCHAIN_FILE:FILEPATH=(.+)$", cache_text, re.M)
                expected_type = {"arm-debug": "Debug", "arm-release": "Release"}.get(preset)
                if (home is None or build_type is None or toolchain is None
                        or build_type.group(1).strip() != expected_type
                        or Path(home.group(1).strip()).resolve() != root
                        or Path(toolchain.group(1).strip()).resolve() != (root / "cmake/arm-none-eabi-gcc.cmake").resolve()):
                    return None
                rules = tuple(dict.fromkeys(_COMPILER_RULE.findall(build_ninja.read_text(encoding="utf-8"))))
                if not rules:
                    return None
                raw = self._run([str(self.ninja), "-C", str(build_dir), "-t", "compdb", *rules],
                                root, _MAX_COMPDB_BYTES, 10.0)
                document = json.loads(raw)
                if not isinstance(document, list):
                    raise ValueError
                commands: list[tuple[str, Path, list[str]]] = []
                for item in document:
                    if not isinstance(item, dict) or set(item) != {"directory", "command", "file", "output"}:
                        raise ValueError
                    working, _ = _safe_path(root, Path(item["directory"]), directory=True)
                    source, relative = _safe_path(root, working / item["file"])
                    if source.suffix.lower() != ".c":
                        continue
                    args = _windows_argv(item["command"])
                    commands.append((relative, working, args))
                current_sources = tuple(source for source in model.build.sources if source.lower().endswith(".c"))
                if (len(commands) != len(current_sources)
                        or set(source for source, _, _ in commands) != set(current_sources)
                        or len(set(source for source, _, _ in commands)) != len(commands)):
                    return None
                verified: list[tuple[str, Path, list[str]]] = []
                for source, working, args in commands:
                    original_args = args
                    try:
                        actual = self._flags(model, source, working, args)
                        expected = self._flags(model, source, root, None, preset=preset)
                        if _semantic_key(actual) != _semantic_key(expected):
                            args = ["unsupported-semantic-command"]
                    except (ValueError, SourceCatalogError, OSError):
                        # Keep this exact unit in coverage as unsupported; do
                        # not silently claim the old graph was fully parsed.
                        args = ["unsupported-semantic-command"]
                    if args[0] == "unsupported-semantic-command":
                        args.append(hashlib.sha256(json.dumps(original_args, separators=(",", ":")).encode("utf-8")).hexdigest())
                    verified.append((source, working, args))
                return verified
            except (OSError, UnicodeError, TypeError, ValueError, SourceCatalogError):
                return None
        return None

    def _flags(self, model: ProjectModel, source: str, cwd: Path, command: list[str] | None,
               *, preset: str | None = None) -> list[str]:
        root = model.project_root
        if command is None:
            original = [*("-D" + value for value in model.build.defines),
                        *("-I" + str(_safe_path(root, Path(value), directory=True)[0]) for value in model.build.include_paths),
                        *_template_options(model, preset if preset is not None else _manifest_preset(model)), source]
        else:
            if (not command or self.preprocessor is None
                    or Path(command[0]).name.lower() not in {"arm-none-eabi-gcc.exe", "arm-none-eabi-gcc"}
                    or Path(command[0]).resolve(strict=True) != self.preprocessor):
                raise ValueError("compiler command is unsupported")
            original = command[1:]
        flags: list[str] = []
        sources: list[str] = []
        index = 0
        while index < len(original):
            part = original[index]
            index += 1
            if not part or part.startswith("@") or "\x00" in part:
                raise ValueError("compile option is unsupported")
            if part in _DROP_EXACT - {"-Og", "-O0", "-O1", "-O2", "-O3", "-Os", "-Oz"} or re.fullmatch(r"-g[0-9]", part):
                continue
            if part in {"-Og", "-O0", "-O1", "-O2", "-O3", "-Os", "-Oz"}:
                flags.append(part)
                continue
            if part in {"-MT", "-MQ", "-MF", "-o"}:
                if index >= len(original):
                    raise ValueError("compile option is incomplete")
                index += 1
                continue
            if part.startswith(("-MT", "-MQ", "-MF", "-o")) and len(part) > 3:
                continue
            if part in ("-I", "-isystem", "-iquote", "-include", "-D", "-U", "-x", "-target"):
                if index >= len(original):
                    raise ValueError("compile option is incomplete")
                value = original[index]
                index += 1
                prefix = part
            elif part.startswith(("-I", "-D", "-U")) and len(part) > 2:
                prefix, value = part[:2], part[2:]
            elif part in _KEEP_EXACT or part.startswith(_KEEP_PREFIX):
                flags.append(part)
                continue
            elif not part.startswith("-"):
                _, relative = _safe_path(root, cwd / part)
                sources.append(relative)
                continue
            else:
                raise ValueError("compile option is unsupported")
            if prefix in ("-I", "-isystem", "-iquote", "-include"):
                resolved, _ = _safe_path(root, cwd / value, directory=prefix != "-include")
                flags.extend((prefix, str(resolved)))
            elif prefix in ("-D", "-U"):
                if len(value) > 1024 or not _IDENTIFIER.fullmatch(value.split("=", 1)[0]):
                    raise ValueError("macro option is unsupported")
                flags.append(prefix + value)
            elif prefix == "-x":
                if value not in ("c", "c-header"):
                    raise ValueError("language is unsupported")
                flags.extend((prefix, value))
            elif prefix == "-target":
                if value != "arm-none-eabi":
                    raise ValueError("target is unsupported")
                flags.extend((prefix, value))
        if sources != [source]:
            raise ValueError("compile input does not match the verified project")
        return flags

    def plan(self, model: ProjectModel) -> SourcePlan:
        root = model.project_root
        version = self._version(root)
        commands = self._compdb(model)
        if commands is None:
            commands = [(source, root, [source]) for source in model.build.sources if source.lower().endswith(".c")]
            input_kind = "manifest"
        else:
            input_kind = "compdb"
        stages = []
        for source, cwd, command in commands:
            try:
                flags = self._flags(model, source, cwd, None if input_kind == "manifest" else command)
                parser = [flag for flag in flags if flag in _KEEP_EXACT or flag.startswith(_KEEP_PREFIX)]
                stages.append([source, str(cwd), command, ["gcc", *flags, "-E", source],
                               ["clang", *parser, "-fsyntax-only", "-Xclang", "-ast-dump=json", "unit.i"]])
            except (OSError, ValueError, SourceCatalogError):
                stages.append([source, str(cwd), command, "unsupported"])
        raw = json.dumps(["gcc-e-line-markers-clang-i-v1", str(self.preprocessor), str(self.compiler), version, input_kind,
                          stages],
                         ensure_ascii=False, separators=(",", ":"))
        fingerprint = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return SourcePlan(tuple((source, cwd, tuple(command)) for source, cwd, command in commands),
                          input_kind, version, fingerprint)

    def index(self, model: ProjectModel, plan: SourcePlan | None = None) -> SourceIndex:
        with self._index_lock:
            if self._closed.is_set():
                raise SourceCatalogError("MONITOR_SOURCE_INDEX_FAILED", "Source index was closed")
            return self._index_locked(model, plan)

    def _index_locked(self, model: ProjectModel, plan: SourcePlan | None = None) -> SourceIndex:
        root = model.project_root
        plan = self.plan(model) if plan is None else plan
        deadline = time.monotonic() + MAX_TOTAL_SECONDS
        commands = list(plan.commands)
        input_kind = plan.input_kind
        total_units = len(commands)
        if total_units > MAX_UNITS:
            commands = commands[:MAX_UNITS]
            truncated = True
        else:
            truncated = False
        issues: list[SourceIssue] = []
        declarations: dict[str, SourceDeclaration] = {}
        functions: dict[str, SourceFunction] = {}
        parsed = 0
        total_bytes = 0
        for source, cwd, command in commands:
            if self._closed.is_set():
                raise SourceCatalogError("MONITOR_SOURCE_INDEX_FAILED", "Source index was closed")
            try:
                absolute, source = _safe_path(root, root / source)
                flags = self._flags(model, source, cwd, None if input_kind == "manifest" else list(command))
                remaining = deadline - time.monotonic()
                if remaining <= 0 or total_bytes >= MAX_TOTAL_AST_BYTES:
                    raise SourceCatalogError("MONITOR_SOURCE_INDEX_FAILED", "Source index exceeded its total budget")
                unit_deadline = time.monotonic() + min(MAX_UNIT_SECONDS, remaining)
                with tempfile.TemporaryDirectory(prefix="stm32-source-preprocessed-") as temporary:
                    preprocessed = Path(temporary) / "unit.i"
                    content = self._run([str(self.preprocessor), *flags, "-E", str(absolute)],
                                        cwd, min(MAX_UNIT_PREPROCESSED_BYTES, MAX_TOTAL_AST_BYTES - total_bytes),
                                        min(unit_deadline - time.monotonic(), deadline - time.monotonic()))
                    total_bytes += len(content)
                    preprocessed.write_bytes(content)
                    parser_flags = [flag for flag in flags if flag in _KEEP_EXACT
                                    or flag.startswith(_KEEP_PREFIX)]
                    remaining = min(unit_deadline - time.monotonic(), deadline - time.monotonic())
                    if remaining <= 0:
                        raise SourceCatalogError("MONITOR_SOURCE_INDEX_FAILED", "Source index exceeded its total budget")
                    raw = self._run([str(self.compiler), *parser_flags, "-fsyntax-only", "-Xclang", "-ast-dump=json", str(preprocessed)],
                                    cwd, min(MAX_UNIT_AST_BYTES, MAX_TOTAL_AST_BYTES - total_bytes),
                                    remaining)
                total_bytes += len(raw)
                ast = json.loads(raw)
                if not isinstance(ast, dict):
                    raise ValueError("AST root is invalid")
                for entry in _discover(ast, root, source, content):
                    if isinstance(entry, SourceFunction):
                        previous_function = functions.get(entry.id)
                        if previous_function is None:
                            if len(functions) >= MAX_FUNCTIONS:
                                truncated = True
                                raise SourceCatalogError("MONITOR_SOURCE_INDEX_FAILED", "Source function limit was reached")
                            functions[entry.id] = entry
                        else:
                            functions[entry.id] = SourceFunction(
                                entry.id, entry.name, entry.file, entry.line, entry.column,
                                tuple(sorted(set(previous_function.translation_units + entry.translation_units))))
                        continue
                    declaration = entry
                    previous = declarations.get(declaration.id)
                    if previous is None:
                        if len(declarations) >= MAX_DECLARATIONS:
                            truncated = True
                            raise SourceCatalogError("MONITOR_SOURCE_INDEX_FAILED", "Source declaration limit was reached")
                        declarations[declaration.id] = declaration
                    else:
                        units = tuple(sorted(set(previous.translation_units + declaration.translation_units)))
                        declarations[declaration.id] = SourceDeclaration(
                            previous.id, previous.entity_id, previous.name, previous.type_name, previous.file,
                            previous.line, previous.column, previous.storage,
                            previous.scope_kind, previous.function, previous.scope_path, units,
                            previous.function_id)
                parsed += 1
            except (OSError, UnicodeError, TypeError, ValueError, SourceCatalogError, json.JSONDecodeError):
                issues.append(SourceIssue(source, "MONITOR_SOURCE_INDEX_FAILED", "Compilation unit could not be indexed within the source policy"))
                if time.monotonic() >= deadline or total_bytes >= MAX_TOTAL_AST_BYTES:
                    truncated = True
                    break
        ordered = tuple(sorted(declarations.values(), key=lambda x: (x.file.casefold(), x.line or 0, x.column or 0, x.name, x.id)))
        ordered_functions = tuple(sorted(functions.values(), key=lambda x: (x.file.casefold(), x.line or 0, x.column or 0, x.name, x.id)))
        return SourceIndex("GNU Arm GCC + Clang", plan.engine_version, input_kind, total_units, parsed,
                           tuple(issues), truncated, ordered, plan.fingerprint, ordered_functions)


def _line_map(preprocessed: bytes) -> tuple[tuple[int, ...], tuple[tuple[str | None, int | None], ...]]:
    starts: list[int] = []
    locations: list[tuple[str | None, int | None]] = []
    offset = 0
    current_file: str | None = None
    current_line: int | None = None
    for raw_line in preprocessed.splitlines(keepends=True):
        starts.append(offset)
        marker = _LINE_MARKER.match(raw_line)
        if marker is not None:
            try:
                raw_name = marker.group(2).decode("utf-8", "strict")
                current_file = json.loads('"' + raw_name + '"')
                current_line = int(marker.group(1))
            except (UnicodeError, ValueError, json.JSONDecodeError):
                current_file = None
                current_line = None
            locations.append((None, None))
        else:
            locations.append((current_file, current_line))
            if current_line is not None:
                current_line += 1
        offset += len(raw_line)
    return tuple(starts), tuple(locations)


def _discover(ast: dict[str, object], root: Path, unit: str,
              preprocessed: bytes) -> Iterable[SourceDeclaration | SourceFunction]:
    starts, locations = _line_map(preprocessed)
    file_cache: dict[str, tuple[bytes, tuple[int, ...]]] = {}
    entities: dict[str, str] = {}
    # Clang omits repeated presumedFile/presumedLine. GCC line markers map each
    # AST byte offset back to the active source file and source line.
    stack: list[tuple[dict[str, object], str | None, str | None, tuple[str, ...]]] = [(ast, None, None, ())]
    while stack:
        node, function, function_id, scope = stack.pop()
        kind = node.get("kind")
        location = node.get("loc")
        loc = location if isinstance(location, dict) else {}
        point = loc.get("expansionLoc") or loc.get("spellingLoc") or loc
        point = point if isinstance(point, dict) else {}
        offset = point.get("offset")
        position = bisect_right(starts, offset) - 1 if type(offset) is int else -1
        mapped_file, mapped_line = locations[position] if position >= 0 else (None, None)
        raw_file = point.get("presumedFile") or mapped_file
        raw_line = point.get("presumedLine") or mapped_line
        if kind == "FunctionDecl" and node.get("isImplicit") is not True:
            name = node.get("name")
            if (not isinstance(name, str) or not name or len(name) > 256
                    or any(ord(character) < 32 for character in name)):
                raise SourceCatalogError("MONITOR_SOURCE_INDEX_FAILED", "A function name exceeds the source catalog policy")
            function = name
            function_id = None
            scope = ()
            if isinstance(raw_file, str) and not (raw_file.startswith("<") and raw_file.endswith(">")):
                candidate = Path(raw_file)
                external = False
                if candidate.is_absolute():
                    try:
                        candidate.relative_to(root)
                    except ValueError:
                        external = True
                if not external:
                    _, relative = _safe_path(root, candidate)
                    line = raw_line if type(raw_line) is int and raw_line > 0 else None
                    column = point.get("col") if type(point.get("col")) is int and point["col"] > 0 else None
                    identity = ["function", relative, line, column, function]
                    if line is None or column is None:
                        identity.extend((unit, offset))
                    function_id = hashlib.sha256(json.dumps(
                        identity, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
                    yield SourceFunction(function_id, function, relative, line, column, (unit,))
        elif kind in ("CompoundStmt", "ForStmt", "WhileStmt", "DoStmt", "SwitchStmt") and function is not None:
            begin = node.get("range")
            begin = begin.get("begin") if isinstance(begin, dict) else {}
            offset = begin.get("offset") if isinstance(begin, dict) else None
            scope = (*scope, f"block@{offset}" if type(offset) is int else "block")
        if kind in ("VarDecl", "ParmVarDecl") and node.get("isImplicit") is not True:
            name = node.get("name")
            if isinstance(name, str) and _IDENTIFIER.fullmatch(name):
                if not isinstance(raw_file, str):
                    raise SourceCatalogError("MONITOR_SOURCE_INDEX_FAILED", "A declaration has no source location")
                if raw_file.startswith("<") and raw_file.endswith(">"):
                    continue  # compiler builtins are outside the project
                candidate = Path(raw_file)
                if candidate.is_absolute():
                    try:
                        candidate.relative_to(root)
                    except ValueError:
                        continue  # verified external system header
                absolute, relative = _safe_path(root, candidate)
                if relative not in file_cache:
                    data = absolute.read_bytes()
                    file_starts = [0]
                    file_starts.extend(index + 1 for index, byte in enumerate(data) if byte == 10)
                    file_cache[relative] = data, tuple(file_starts)
                data, source_starts = file_cache[relative]
                line = raw_line if type(raw_line) is int and raw_line > 0 and raw_line <= len(source_starts) else None
                column = None
                if line is not None:
                    start = source_starts[line - 1]
                    end = source_starts[line] if line < len(source_starts) else len(data)
                    original_line = data[start:end]
                    candidate_col = point.get("col")
                    if (type(candidate_col) is int and candidate_col > 0 and
                            original_line[candidate_col - 1:candidate_col - 1 + len(name)] == name.encode("ascii")):
                        column = candidate_col
                    else:
                        matches = list(re.finditer(rb"\b" + re.escape(name.encode("ascii")) + rb"\b", original_line))
                        if len(matches) == 1:
                            column = matches[0].start() + 1
                type_data = node.get("type")
                type_name = type_data.get("qualType") if isinstance(type_data, dict) else None
                if not isinstance(type_name, str) or not type_name or len(type_name) > 256:
                    raise ValueError("AST type is invalid")
                raw_storage = node.get("storageClass")
                storage = raw_storage if raw_storage in {"static", "extern", "register"} else "none"
                if node.get("tlsKind") is not None:
                    storage = "thread_local"
                scope_kind = ("parameter" if kind == "ParmVarDecl" else
                              "static_local" if function is not None and storage == "static" else
                              "local" if function is not None else
                              "file_static" if storage == "static" else "global")
                identity = [relative, line, column, name, type_name, storage, scope_kind, function, scope]
                if line is None or column is None:
                    identity.extend((unit, offset))
                if scope_kind in {"file_static", "static_local"} and relative != unit:
                    identity.append(unit)
                key = hashlib.sha256(json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
                previous = node.get("previousDecl")
                entity = entities.get(previous, key) if isinstance(previous, str) else key
                ast_id = node.get("id")
                if isinstance(ast_id, str):
                    entities[ast_id] = entity
                yield SourceDeclaration(key, entity, name, type_name, relative, line, column,
                                        storage, scope_kind, function, scope, (unit,), function_id)
        children = node.get("inner")
        if isinstance(children, list):
            for child in reversed(children):
                if isinstance(child, dict):
                    stack.append((child, function, function_id, scope))


def _declarations(ast: dict[str, object], root: Path, unit: str,
                  preprocessed: bytes) -> Iterable[SourceDeclaration]:
    return (item for item in _discover(ast, root, unit, preprocessed)
            if isinstance(item, SourceDeclaration))
