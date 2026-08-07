"""Build runner, locking, publication, and stale-output defense contracts.

Every fixture project is copied to a disposable pytest temporary directory,
managed configuration is generated through the STM32TK-0304 plan/apply path,
a git repository records the project state, and Python ``cmake`` and ``git``
doubles (hit-proven) stand in for the real toolchain.  Interception uses a
narrow deterministic process-launch seam per double: only an original argv
whose executable is exactly ``"cmake"`` is mapped to ``sys.executable`` plus
the real ``fake_cmake.py`` script, and only an original argv whose
executable is exactly ``"git"`` is mapped to ``sys.executable`` plus the
real ``fake_git.py`` script; every other invocation (helper
``subprocess.run`` calls) is delegated unchanged down the seam chain to the
real ``subprocess.Popen``.  This never depends on Windows resolving a bare
``cmake``/``git`` to a ``.cmd`` launcher (CreateProcess appends ``.exe`` and
would find an ambient real CMake or Git).  No real CMake/Ninja/ARM toolchain
is required and no build artifact is committed.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

from stm32_toolkit.build import BuildReport, BuildRequest, FirmwareIdentity, MemoryUsage, run_build
from stm32_toolkit.build import identity as identity_mod
from stm32_toolkit.generation import apply_project_configuration, plan_project_configuration
from stm32_toolkit.project_model import load_project_model

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "minimal-gcc"

#: Default extra SHF_ALLOC sections that mirror the default MAP rows so the
#: deterministic ELF and MAP evidence always agree (VMA and size).
_DEFAULT_ALLOC_SECTIONS = ((".data", 0x20000000, 0x100, 0x3), (".bss", 0x20000100, 0x400, 0x3))

# ---------------------------------------------------------------------------
# deterministic ELF32 little-endian ARM builder (test-only)
# ---------------------------------------------------------------------------


def build_elf_bytes(
    *,
    entry: int = 0x08000011,
    reset_handler: int = 0x08000011,
    vector_word: int | None = None,
    vector_addr: int = 0x08000000,
    vector_size: int = 64,
    vector_flags: int = 0x2,
    text_addr: int = 0x08000040,
    text_size: int = 256,
    include_vector: bool = True,
    include_symtab: bool = True,
    include_reset_symbol: bool = True,
    reset_undefined: bool = False,
    undefined_global: tuple[str, ...] = (),
    undefined_weak: tuple[str, ...] = (),
    elf_class: int = 1,
    elf_data: int = 1,
    elf_machine: int = 40,
    fixed_sections: tuple[tuple[str, int, int], ...] = (),
    alloc_sections: tuple[tuple[str, int, int, int], ...] | None = None,
    nonalloc_sections: tuple[tuple[str, int, int], ...] = (),
    truncate: int = 0,
) -> bytes:
    """Build a minimal valid ELF32 little-endian ARM image for tests.

    Layout: ELF header, ``.isr_vector`` (first word 0x20020000, second word
    the reset handler), ``.text``, default ``.data``/``.bss`` SHF_ALLOC
    sections (mirroring the default MAP rows), extra ``alloc_sections``
    ``(name, addr, size, flags)`` and ``nonalloc_sections``
    ``(name, addr, size)`` (flags 0, e.g. debug/comment rows at VMA 0),
    optional fixed ``.stm32tk.abs.*`` sections,
    ``.symtab``/``.strtab``/``.shstrtab`` and the section header table.
    ``alloc_sections=None`` selects the default data/bss pair; an explicit
    empty tuple omits them.  ``truncate`` cuts the file short to emulate
    malformed input.
    """
    vector_second = reset_handler if vector_word is None else vector_word
    sections: list[dict] = []

    def add(
        name: str,
        sh_type: int,
        flags: int,
        addr: int,
        data: bytes,
        link: int = 0,
        info: int = 0,
        align: int = 4,
        entsize: int = 0,
    ) -> int:
        sections.append(
            {
                "name": name,
                "type": sh_type,
                "flags": flags,
                "addr": addr,
                "data": data,
                "link": link,
                "info": info,
                "align": align,
                "entsize": entsize,
            }
        )
        return len(sections) - 1

    if include_vector:
        if vector_size >= 8:
            vector_data = struct.pack("<II", 0x20020000, vector_second)
            vector_data += b"\x00" * (vector_size - len(vector_data))
        else:
            vector_data = struct.pack("<I", 0x20020000)[:vector_size]
        add(".isr_vector", 1, vector_flags, vector_addr, vector_data)
    text_index = add(".text", 1, 0x6, text_addr, b"\x00\xbf" * (text_size // 2))
    if alloc_sections is None:
        alloc_sections = _DEFAULT_ALLOC_SECTIONS
    for name, addr, size, flags in alloc_sections:
        add(name, 1, flags, addr, b"\x00" * size)
    for name, addr, size in nonalloc_sections:
        add(name, 1, 0, addr, b"\x00" * size)

    symbol_names = ["Reset_Handler", "main", *undefined_global, *undefined_weak]
    strtab = bytearray(b"\x00")
    name_offsets: dict[str, int] = {}
    for name in symbol_names:
        name_offsets[name] = len(strtab)
        strtab += name.encode("utf-8") + b"\x00"
    strtab_data = bytes(strtab)

    symbols: list[tuple[int, int, int, int, int, int]] = []  # (name, value, size, info, other, shndx)
    symbols.append((0, 0, 0, 0, 0, 0))  # null symbol
    if include_reset_symbol:
        if reset_undefined:
            symbols.append((name_offsets["Reset_Handler"], 0, 0, 0x10, 0, 0))  # undefined global
        else:
            symbols.append((name_offsets["Reset_Handler"], reset_handler, 8, 0x12, 0, text_index))
    symbols.append((name_offsets["main"], 0x08000050, 4, 0x12, 0, text_index))
    for name in undefined_global:
        symbols.append((name_offsets[name], 0, 0, 0x10, 0, 0))
    for name in undefined_weak:
        symbols.append((name_offsets[name], 0, 0, 0x20, 0, 0))

    strtab_index = add(".strtab", 3, 0, 0, strtab_data, align=1)

    symtab_data = b"".join(struct.pack("<IIIBBH", *symbol) for symbol in symbols)
    if include_symtab:
        add(
            ".symtab", 2, 0, 0, symtab_data, link=strtab_index + 1, info=1, align=4, entsize=16
        )

    fixed_names: list[str] = []
    for name, addr, size in fixed_sections:
        add(name, 1, 0x2, addr, b"\x00" * size)
        fixed_names.append(name)

    shstr_names = [".isr_vector", ".text"]
    shstr_names.extend(section[0] for section in alloc_sections)
    shstr_names.extend(section[0] for section in nonalloc_sections)
    shstr_names.extend([".symtab", ".strtab", ".shstrtab"])
    shstr_names.extend(fixed_names)
    shstr_data = b"\x00" + b"\x00".join(name.encode("utf-8") for name in shstr_names) + b"\x00"
    shstrtab_index = add(".shstrtab", 3, 0, 0, shstr_data, align=1)

    offset = 52
    for section in sections:
        offset = (offset + section["align"] - 1) // section["align"] * section["align"]
        section["offset"] = offset
        offset += len(section["data"])
    shoff = (offset + 3) // 4 * 4
    shnum = len(sections) + 1

    ident = b"\x7fELF" + bytes([elf_class, elf_data, 1, 0]) + b"\x00" * 8
    header = struct.pack(
        "<16sHHIIIIIHHHHHH",
        ident,
        2,  # e_type: ET_EXEC
        elf_machine,
        1,  # e_version
        entry,
        0,  # e_phoff
        shoff,
        0,  # e_flags
        52,  # e_ehsize
        0,  # e_phentsize
        0,  # e_phnum
        40,  # e_shentsize
        shnum,
        shstrtab_index + 1,
    )
    data = bytearray(header)
    for section in sections:
        data.extend(b"\x00" * (section["offset"] - len(data)))
        data.extend(section["data"])
    data.extend(b"\x00" * (shoff - len(data)))
    data.extend(b"\x00" * 40)  # null section header
    for section in sections:
        sh_name = shstr_data.find(b"\x00" + section["name"].encode("utf-8") + b"\x00") + 1
        data.extend(
            struct.pack(
                "<IIIIIIIIII",
                sh_name,
                section["type"],
                section["flags"],
                section["addr"],
                section["offset"],
                len(section["data"]),
                section["link"],
                section["info"],
                section["align"],
                section["entsize"],
            )
        )
    if truncate and truncate < len(data):
        return bytes(data[:truncate])
    return bytes(data)


# ---------------------------------------------------------------------------
# deterministic GNU ld MAP text builder (test-only)
# ---------------------------------------------------------------------------


def build_map_text(
    *,
    regions: tuple[tuple[str, int, int], ...] = (
        ("FLASH", 0x08000000, 0x100000),
        ("RAM", 0x20000000, 0x20000),
    ),
    region_attributes: tuple[str, ...] = ("xr", "xrw"),
    sections: tuple[tuple[str, int, int, int | None], ...] = (
        (".isr_vector", 0x08000000, 0x40, None),
        (".text", 0x08000040, 0x100, None),
        (".data", 0x20000000, 0x100, 0x08001000),
        (".bss", 0x20000100, 0x400, None),
    ),
    linesep: str = "\n",
    extra_lines: tuple[str, ...] = (),
) -> str:
    """Build a realistic GNU ld ``.map`` text with exact stable columns."""
    lines = [
        "Memory Configuration",
        "",
        "Name             Origin             Length             Attributes",
    ]
    for index, (name, origin, length) in enumerate(regions):
        attrs = region_attributes[index] if index < len(region_attributes) else "r"
        lines.append(f"{name:<16} 0x{origin:016x} 0x{length:016x} {attrs}")
    lines.append("*default*        0x0000000000000000 0xffffffffffffffff")
    lines.extend(["", "Linker script and memory map", ""])
    for name, addr, size, lma in sections:
        row = f"{name:<16} 0x{addr:016x} 0x{size:x}"
        if lma is not None:
            row += f" load address 0x{lma:016x}"
        lines.append(row)
    lines.extend(extra_lines)
    return linesep.join(lines) + linesep


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# fake cmake (explicit interpreter wrapper, hit-proven)
# ---------------------------------------------------------------------------

FAKE_CMAKE_WRAPPER = """#!{python}
import os
import sys

sys.path.insert(0, {tests_dir!r})
from test_build_runner import fake_cmake_main

sys.exit(fake_cmake_main(sys.argv[1:]))
"""

FAKE_GIT_SCRIPT = """import json
import os
import sys

hit_file = os.environ.get("FAKE_GIT_HIT_FILE")
if hit_file:
    with open(hit_file, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd()}) + "\\n")
mode = os.environ.get("FAKE_GIT_MODE", "ok")
if mode == "ok":
    if len(sys.argv) >= 2 and sys.argv[1] == "rev-parse":
        sys.stdout.write("a" * 40 + "\\n")
        sys.stdout.flush()
    sys.exit(0)
if mode == "exit1":
    sys.exit(1)
if mode == "malformed":
    sys.stdout.write("not-a-valid-sha\\n")
    sys.exit(0)
if mode == "overflow":
    sys.stdout.write("a" * 1048576 + "\\n")
    sys.exit(0)
if mode == "sleep":
    import time
    time.sleep(5)
    sys.exit(0)
sys.exit(3)
"""

FAKE_GIT_HIT_PREAMBLE = (
    "import json, os, sys\n"
    "hit_file = os.environ.get('FAKE_GIT_HIT_FILE')\n"
    "if hit_file:\n"
    "    with open(hit_file, 'a', encoding='utf-8') as handle:\n"
    "        handle.write(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd()}) + '\\n')\n"
)


def fake_cmake_main(argv: list[str]) -> int:
    """Stand-in for the real ``cmake`` binary; runs in a subprocess."""
    cwd = os.getcwd()
    env = os.environ
    hit_file = env.get("FAKE_CMAKE_HIT_FILE")
    if hit_file:
        with open(hit_file, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"argv": argv, "cwd": cwd}) + "\n")

    def out(text: str) -> None:
        text = text if env.get("FAKE_CMAKE_CRLF") != "1" else text.replace("\n", "\r\n")
        sys.stdout.write(text)
        sys.stdout.flush()

    sleep = float(env.get("FAKE_CMAKE_SLEEP", "0"))
    if sleep:
        import time

        time.sleep(sleep)
    flood = int(env.get("FAKE_CMAKE_FLOOD", "0"))
    if flood:
        line = "x" * 80 + "\n"
        for _ in range(flood):
            out(line)
    exit_code = int(env.get("FAKE_CMAKE_EXIT", "0"))
    fail_stage = env.get("FAKE_CMAKE_FAIL_STAGE", "configure")
    if len(argv) >= 2 and argv[0] == "--preset":
        out(f"[fake cmake configure] preset={argv[1]}\n")
        out(f"cwd={cwd}\n")
        if fail_stage == "configure" and exit_code:
            return exit_code
        os.makedirs(os.path.join(cwd, "build", argv[1]), exist_ok=True)
        return 0
    if len(argv) >= 3 and argv[0] == "--build" and argv[1] == "--preset":
        preset = argv[2]
        clean_first = "--clean-first" in argv[3:]
        out(f"[fake cmake build] preset={preset} clean_first={clean_first}\n")
        if fail_stage == "build" and exit_code:
            return exit_code
        with open(os.path.join(cwd, ".stm32-project.json"), "rb") as handle:
            payload = json.load(handle)
        elf_rel = payload["build"]["elf"]
        base = os.path.basename(elf_rel)
        stem = base[: -len(".elf")]
        elf_path = os.path.join(cwd, "build", preset, base)
        map_path = os.path.join(cwd, "build", preset, stem + ".map")
        os.makedirs(os.path.dirname(elf_path), exist_ok=True)
        touch_input = env.get("FAKE_CMAKE_TOUCH_INPUT")
        if touch_input:
            with open(os.path.join(cwd, touch_input), "ab") as handle:
                handle.write(b"/* fake cmake touched an input */\n")
        delete_input = env.get("FAKE_CMAKE_DELETE_INPUT")
        if delete_input:
            os.remove(os.path.join(cwd, delete_input))
        if env.get("FAKE_CMAKE_NO_OUTPUT") == "1":
            return 0
        regions = [
            (region["name"], region["origin"], region["length"])
            for region in payload["memory"]["regions"]
        ]
        defect_elf = env.get("FAKE_CMAKE_ELF_DEFECT", "")
        defect_map = env.get("FAKE_CMAKE_MAP_DEFECT", "")
        text_size = int(env.get("FAKE_CMAKE_ELF_TEXT_SIZE", "256"))
        elf_kwargs = dict(ELF_DEFECTS.get(defect_elf, {}))
        if defect_map == "overflow":
            # Consistent ELF/MAP evidence whose disjoint RAM LMAs overflow
            # the writable region (ELF validation still passes first).
            elf_kwargs["text_size"] = 0x20000
            elf_kwargs["alloc_sections"] = ((".rodata", 0x08020040, 0x20000, 0x2),)
        elif env.get("FAKE_CMAKE_DEBUG_MAP") == "1":
            # GNU ld style non-alloc debug/comment sections at VMA 0; the
            # MAP may omit their rows entirely (line wrapping) so only the
            # ELF carries them.
            elf_kwargs["nonalloc_sections"] = (
                (".debug_info", 0x0, 0x1A2),
                (".comment", 0x0, 0x2F),
            )
        elf = build_elf_bytes(text_size=text_size, **elf_kwargs)
        if defect_map == "malformed":
            map_text = "this is not a GNU linker map\n"
        elif defect_map == "overflow":
            map_text = build_map_text(
                regions=regions,
                sections=(
                    (".isr_vector", 0x08000000, 0x40, None),
                    (".text", 0x08000040, 0x20000, 0x20000000),
                    (".rodata", 0x08020040, 0x20000, 0x20010000),
                ),
            )
        elif defect_map == "unknown":
            map_text = build_map_text(
                regions=regions, sections=((".mystery", 0x08000040, 0x100, None),)
            )
        elif defect_map == "address":
            map_text = build_map_text(
                regions=regions, sections=((".text", 0x08000200, text_size, None),)
            )
        elif defect_map == "size":
            map_text = build_map_text(
                regions=regions, sections=((".text", 0x08000040, text_size + 0x10, None),)
            )
        elif defect_map == "missing-section":
            map_text = build_map_text(
                regions=regions,
                sections=(
                    (".isr_vector", 0x08000000, 0x40, None),
                    (".text", 0x08000040, text_size, None),
                    (".data", 0x20000000, 0x100, 0x08001000),
                ),
            )
        elif defect_map == "missing":
            map_text = None
        else:
            map_text = build_map_text(
                regions=regions,
                sections=(
                    (".isr_vector", 0x08000000, 0x40, None),
                    (".text", 0x08000040, text_size, None),
                    (".data", 0x20000000, 0x100, 0x08001000),
                    (".bss", 0x20000100, 0x400, None),
                ),
            )
        with open(elf_path, "wb") as handle:
            handle.write(elf)
        if map_text is not None:
            with open(map_path, "w", encoding="utf-8") as handle:
                handle.write(map_text)
        return 0
    sys.stderr.write(f"[fake cmake] unexpected argv {argv!r}\n")
    return 2


ELF_DEFECTS: dict[str, dict] = {
    "": {},
    "no-vector": {"include_vector": False},
    "short-vector": {"vector_size": 4},
    "reset-undefined": {"reset_undefined": True},
    "undef-global": {"undefined_global": ("external_helper",)},
    "weak-undefined": {"undefined_weak": ("optional_helper",)},
    "wrong-class": {"elf_class": 2},
    "wrong-endian": {"elf_data": 2},
    "wrong-machine": {"elf_machine": 8},
    "entry-mismatch": {"entry": 0x08000031},
    "entry-even": {"entry": 0x08000010, "reset_handler": 0x08000010, "vector_word": 0x08000010},
    "vector-mismatch": {"vector_word": 0x08000099},
    "alloc-escape": {"text_addr": 0x30000000},
    "no-symtab": {"include_symtab": False},
    "fixed-mismatch": {"fixed_sections": ((".stm32tk.abs.20000000", 0x20000100, 16),)},
    "vector-noalloc": {"vector_flags": 0},
    "vector-addr": {"vector_addr": 0x40000000},
    "no-reset": {"include_reset_symbol": False},
    "truncated": {"truncate": 40},
}


def fake_cmake_launcher(bin_dir: Path) -> Path:
    """The exact fake-``cmake`` launcher path installed for this host."""
    return bin_dir / ("cmake.cmd" if os.name == "nt" else "cmake")


class _FakeToolPopenSeam:
    """A narrow deterministic process-launch seam for a tool double.

    Only an original argv whose executable is exactly ``name`` (never a
    path, never an extension) is mapped to ``sys.executable`` plus the real
    ``fake_<name>.py`` script; the untouched product argv is recorded so the
    exact-argv contract can be asserted.  Every other invocation is
    delegated unchanged to ``fallback`` — a previously installed seam or the
    real ``subprocess.Popen`` implementation — so the other tool double,
    Git evidence, and helper ``subprocess.run`` calls are never intercepted.
    When the launch target has been removed (the launch-failure fixture),
    the seam raises ``FileNotFoundError`` exactly like a real spawn so the
    product returns ``BUILD_CONFIGURE_FAILED`` with ``rule=launch``.
    """

    def __init__(self, name: str, script: Path, recorded: Path, fallback) -> None:
        self._name = name
        self._script = script
        self._recorded = recorded
        self._fallback = fallback

    def __call__(self, *args, **kwargs):
        argv = args[0] if args else kwargs.get("args")
        if isinstance(argv, (list, tuple)) and argv and argv[0] == self._name:
            original = tuple(argv)
            with open(self._recorded, "a", encoding="utf-8") as handle:
                handle.write(json.dumps({"argv": list(original)}) + "\n")
            if not self._script.is_file():
                raise FileNotFoundError(2, f"fake {self._name} launch target is missing")
            mapped = (sys.executable, str(self._script), *original[1:])
            if args:
                args = (mapped,) + args[1:]
            else:
                kwargs["args"] = mapped
        return self._fallback(*args, **kwargs)


def install_fake_cmake(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    env: dict[str, str] | None = None,
) -> Path:
    """Install the hit-proven fake ``cmake`` behind a narrow launch seam.

    The seam maps only the product's exact bare ``"cmake"`` argv to
    ``sys.executable`` plus a real ``fake_cmake.py`` script that exists on
    disk, so interception never falls through to an ambient real CMake on
    any host.  The POSIX executable wrapper / Windows ``.cmd`` launcher are
    still installed for the launcher-probe contract (Windows only resolves
    ``.cmd`` when invoked by full path).  Returns the hit-file path.
    """
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    tests_dir = Path(__file__).parent
    script = bin_dir / "fake_cmake.py"
    script.write_text(
        FAKE_CMAKE_WRAPPER.format(python=sys.executable, tests_dir=str(tests_dir)),
        encoding="utf-8",
    )
    if os.name == "nt":
        launcher = bin_dir / "cmake.cmd"
        launcher.write_text(
            f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n',
            encoding="utf-8",
        )
    else:
        launcher = bin_dir / "cmake"
        launcher.write_text(
            FAKE_CMAKE_WRAPPER.format(python=sys.executable, tests_dir=str(tests_dir)),
            encoding="utf-8",
        )
        launcher.chmod(0o755)
    hit_file = tmp_path / "cmake-hit.jsonl"
    orig_file = tmp_path / "cmake-orig.jsonl"
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("FAKE_CMAKE_HIT_FILE", str(hit_file))
    for key, value in (env or {}).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(
        subprocess, "Popen", _FakeToolPopenSeam("cmake", script, orig_file, subprocess.Popen)
    )
    return hit_file


def install_fake_git(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mode: str
) -> tuple[Path, Path]:
    """Install the hit-proven fake ``git`` behind a narrow launch seam.

    The seam maps only the product's exact bare ``"git"`` argv to
    ``sys.executable`` plus a real ``fake_git.py`` script that exists on
    disk, so interception never depends on Windows PATH resolving a bare
    ``git`` to a ``.cmd`` launcher (CreateProcess appends ``.exe`` and
    would find an ambient real Git).  Falls back to the currently installed
    ``subprocess.Popen`` so the git seam composes with an already installed
    fake-``cmake`` seam.  Returns ``(hit_file, orig_file)``.
    """
    bin_dir = tmp_path / "fakegit"
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "fake_git.py"
    script.write_text(FAKE_GIT_SCRIPT, encoding="utf-8")
    return _install_git_seam(monkeypatch, tmp_path, script, mode=mode)


def install_fake_git_script(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, script_body: str
) -> tuple[Path, Path]:
    """Install a custom fake ``git`` script behind the same narrow seam.

    The body is prefixed with the shared hit-recording preamble so custom
    scripts prove they were actually invoked.  Returns ``(hit_file,
    orig_file)``.
    """
    bin_dir = tmp_path / "fakegit"
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "fake_git.py"
    script.write_text(FAKE_GIT_HIT_PREAMBLE + script_body, encoding="utf-8")
    return _install_git_seam(monkeypatch, tmp_path, script)


def _install_git_seam(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, script: Path, mode: str | None = None
) -> tuple[Path, Path]:
    """Install the narrow git seam; returns ``(hit_file, orig_file)``."""
    hit_file = tmp_path / "git-hit.jsonl"
    orig_file = tmp_path / "git-orig.jsonl"
    if mode is not None:
        monkeypatch.setenv("FAKE_GIT_MODE", mode)
    monkeypatch.setenv("FAKE_GIT_HIT_FILE", str(hit_file))
    monkeypatch.setattr(
        subprocess, "Popen", _FakeToolPopenSeam("git", script, orig_file, subprocess.Popen)
    )
    return hit_file, orig_file


def git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", "-c", "user.name=tk-test", "-c", "user.email=tk-test@example.com", *args],
        cwd=str(cwd),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def prepare_project(
    tmp_path: Path,
    *,
    overrides: dict | None = None,
    git_repo: bool = True,
    name: str = "project",
) -> Path:
    """Materialize the deterministic fixture with managed configuration."""
    root = tmp_path / name
    shutil.copytree(FIXTURE_ROOT, root)
    if overrides:
        manifest_path = root / ".stm32-project.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload.update(overrides)
        manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if git_repo:
        (root / ".gitignore").write_text(
            "build/\n.stm32-toolkit/build.lock\n__pycache__/\n*.pyc\n", encoding="utf-8"
        )
        git("init", "-q", cwd=root)
    model = load_project_model(root)
    plan = plan_project_configuration(model)
    applied = apply_project_configuration(plan)
    assert applied.ok is True, applied
    if git_repo:
        git("add", "-A", cwd=root)
        git("commit", "-q", "-m", "fixture", cwd=root)
    return root


def hit_records(hit_file: Path) -> list[dict]:
    if not hit_file.exists():
        return []
    return [
        json.loads(line)
        for line in hit_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def orig_argv_records(orig_file: Path) -> list[list[str]]:
    """The untouched product argv recorded by the launch seam, in order."""
    if not orig_file.exists():
        return []
    return [
        json.loads(line)["argv"]
        for line in orig_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def identity_path_for(root: Path, preset: str = "arm-debug") -> Path:
    return root / "build" / preset / "firmware-identity.json"


def result_path_for(root: Path) -> Path:
    return root / "artifacts" / "migration" / "build-result.json"


def log_path_for(root: Path) -> Path:
    return root / "artifacts" / "migration" / "build.log"


# ---------------------------------------------------------------------------
# request validation
# ---------------------------------------------------------------------------


def test_run_build_rejects_non_request(tmp_path: Path):
    result = run_build("not a BuildRequest")  # type: ignore[arg-type]
    assert result.ok is False
    assert result.code == "BUILD_REQUEST_INVALID"
    assert result.details == {"field": "request", "rule": "type"}


def test_run_build_rejects_invalid_request_fields(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    file_root = root / "file.txt"
    file_root.write_text("x", encoding="utf-8")
    cases = [
        (BuildRequest(project_root=tmp_path / "missing", preset="arm-debug"), "projectRoot", "value"),
        (BuildRequest(project_root=file_root, preset="arm-debug"), "projectRoot", "value"),
        (BuildRequest(project_root=root, preset="host"), "preset", "value"),
        (BuildRequest(project_root=root, preset="arm-debug", clean=1), "clean", "type"),  # type: ignore[arg-type]
        (BuildRequest(project_root=root, preset="arm-debug", timeout_seconds=30.0), "timeoutSeconds", "type"),  # type: ignore[arg-type]
        (BuildRequest(project_root=root, preset="arm-debug", timeout_seconds=0), "timeoutSeconds", "range"),
        (BuildRequest(project_root=root, preset="arm-debug", timeout_seconds=3601), "timeoutSeconds", "range"),
    ]
    for request, field, rule in cases:
        result = run_build(request)
        assert result.ok is False
        assert result.code == "BUILD_REQUEST_INVALID"
        assert result.details == {"field": field, "rule": rule}
        assert result.data is None


def test_run_build_rejects_bool_timeout_as_not_an_integer(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    result = run_build(BuildRequest(project_root=root, preset="arm-debug", timeout_seconds=True))  # type: ignore[arg-type]
    assert result.code == "BUILD_REQUEST_INVALID"
    assert result.details == {"field": "timeoutSeconds", "rule": "type"}


def test_run_build_requires_schema_v2_managed_configuration(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    (root / ".stm32-project.json").write_text(
        json.dumps({"schemaVersion": 1, "logicalProjectId": "12345678-1234-5678-1234-567812345678"}) + "\n",
        encoding="utf-8",
    )
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_PROJECT_INVALID"
    assert result.data is None


def test_run_build_requires_valid_managed_configuration(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    manifest_path = root / ".stm32-toolkit" / "generated-files.json"
    manifest_path.write_bytes(b"{broken")
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_PROJECT_INVALID"
    assert result.data is None


def test_run_build_rejects_drifted_generated_file(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    (root / "CMakeLists.txt").write_text("# user edit\n", encoding="utf-8")
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_PROJECT_INVALID"
    assert result.details == {"path": "CMakeLists.txt", "rule": "digest"}


# ---------------------------------------------------------------------------
# lock
# ---------------------------------------------------------------------------


def test_run_build_returns_busy_when_lock_is_held(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    lock_path = root / ".stm32-toolkit" / "build.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    import stm32_toolkit.build.runner as runner_mod

    held = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        assert runner_mod.try_acquire_lock(held) is True
        result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
        assert result.ok is False
        assert result.code == "BUILD_BUSY"
        assert result.details == {"path": ".stm32-toolkit/build.lock"}
        assert result.data is None
    finally:
        runner_mod.release_lock(held)
        os.close(held)


def test_stale_lock_file_does_not_block(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    lock_path = root / ".stm32-toolkit" / "build.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("stale", encoding="utf-8")
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is True
    assert lock_path.exists()


def test_lock_release_on_success_and_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    assert run_build(BuildRequest(project_root=root, preset="arm-debug")).ok is True
    monkeypatch.setenv("FAKE_CMAKE_EXIT", "7")
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.code == "BUILD_CONFIGURE_FAILED"
    import stm32_toolkit.build.runner as runner_mod

    lock_path = root / ".stm32-toolkit" / "build.lock"
    fd = os.open(lock_path, os.O_RDWR)
    try:
        assert runner_mod.try_acquire_lock(fd) is True
    finally:
        runner_mod.release_lock(fd)
        os.close(fd)


# ---------------------------------------------------------------------------
# stages and argv
# ---------------------------------------------------------------------------


def test_run_build_success_debug_publishes_exact_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    hit_file = install_fake_cmake(monkeypatch, tmp_path)
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is True
    assert result.operation == "build"
    assert result.code == "OK"
    report = result.data
    assert isinstance(report, BuildReport)
    assert isinstance(report.identity, FirmwareIdentity)
    assert isinstance(report.memory, tuple)
    assert all(isinstance(item, MemoryUsage) for item in report.memory)

    records = hit_records(hit_file)
    assert records[0]["argv"] == ["--preset", "arm-debug"]
    assert records[1]["argv"] == ["--build", "--preset", "arm-debug"]
    assert len(records) == 2
    # Explicit ambient-CMake proof: a real cmake invocation would leave no
    # hit record and could not produce the exact evidence below (no real
    # toolchain exists here), so exactly these two fake invocations with the
    # fixed product argv/cwd prove the fake was hit and ambient CMake was
    # never executed.
    assert [record["cwd"] for record in records] == [str(root), str(root)]
    # The launch seam recorded the product's untouched argv: it remains
    # exactly the fixed ("cmake", "--preset", preset) configure argv and
    # ("cmake", "--build", "--preset", preset) build argv — never a path,
    # never a shell string, and never an ambient real CMake.
    assert orig_argv_records(tmp_path / "cmake-orig.jsonl") == [
        ["cmake", "--preset", "arm-debug"],
        ["cmake", "--build", "--preset", "arm-debug"],
    ]

    identity_doc = read_json(identity_path_for(root))
    assert identity_doc["schemaVersion"] == 1
    assert identity_doc["preset"] == "arm-debug"
    assert identity_doc["gitDirty"] is False
    assert identity_doc["elfPath"] == "build/arm-debug/firmware.elf"
    assert identity_doc["mapPath"] == "build/arm-debug/firmware.map"
    assert identity_doc["targetDevice"] == "STM32F407VGTx"
    assert identity_doc["logicalProjectId"] == "12345678-1234-5678-1234-567812345678"
    assert identity_doc["toolkitVersion"] == "0.2.0"
    assert identity_doc["buildId"] == report.identity.build_id
    assert len(identity_doc["gitHead"]) == 40
    assert identity_doc["entryPoint"] == 0x08000011
    assert identity_doc["vectorAddress"] == 0x08000000
    assert identity_doc["resetHandlerAddress"] == 0x08000011
    assert identity_doc["elfSize"] > 0
    assert len(identity_doc["elfSha256"]) == 64
    assert len(identity_doc["mapSha256"]) == 64
    assert identity_doc["inputSnapshotSha256"] == report.identity.input_snapshot_sha256

    result_doc = read_json(result_path_for(root))
    assert list(result_doc) == [
        "schemaVersion",
        "status",
        "stage",
        "code",
        "buildId",
        "gitHead",
        "gitDirty",
        "inputSnapshotSha256",
        "targetDevice",
        "preset",
        "startedAtUtc",
        "finishedAtUtc",
        "durationMs",
        "artifacts",
        "memory",
        "warnings",
    ]
    assert result_doc["status"] == "success"
    assert result_doc["code"] == "OK"
    assert result_doc["buildId"] == identity_doc["buildId"]
    assert result_doc["preset"] == "arm-debug"
    assert result_doc["gitHead"] == identity_doc["gitHead"]
    assert result_doc["inputSnapshotSha256"] == identity_doc["inputSnapshotSha256"]
    assert result_doc["memory"] == [item.to_dict() for item in report.memory]
    assert {entry["path"] for entry in result_doc["artifacts"]} == {
        "artifacts/migration/build.log",
        "artifacts/migration/build-result.json",
        "build/arm-debug/firmware-identity.json",
        "build/arm-debug/firmware.elf",
        "build/arm-debug/firmware.map",
    }

    log_text = log_path_for(root).read_text(encoding="utf-8")
    assert "[stage:configure]" in log_text
    assert "[stage:build]" in log_text
    assert '"cmake"' in log_text
    assert "\r" not in log_text
    assert str(root) not in log_text
    assert "<PROJECT_ROOT>" in log_text


def test_run_build_success_release_never_references_debug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    result = run_build(BuildRequest(project_root=root, preset="arm-release"))
    assert result.ok is True
    identity_doc = read_json(identity_path_for(root, "arm-release"))
    assert identity_doc["preset"] == "arm-release"
    assert identity_doc["elfPath"] == "build/arm-release/firmware.elf"
    assert identity_doc["mapPath"] == "build/arm-release/firmware.map"
    result_doc = read_json(result_path_for(root))
    assert result_doc["preset"] == "arm-release"
    assert "arm-debug" not in json.dumps(identity_doc)
    assert "arm-debug" not in json.dumps(result_doc["artifacts"])
    assert not identity_path_for(root, "arm-debug").exists()


def test_clean_first_is_appended_only_when_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    hit_file = install_fake_cmake(monkeypatch, tmp_path)
    assert run_build(BuildRequest(project_root=root, preset="arm-debug", clean=True)).ok is True
    records = hit_records(hit_file)
    assert records[1]["argv"] == ["--build", "--preset", "arm-debug", "--clean-first"]
    hit_file.unlink()
    assert run_build(BuildRequest(project_root=root, preset="arm-debug", clean=False)).ok is True
    records = hit_records(hit_file)
    assert records[1]["argv"] == ["--build", "--preset", "arm-debug"]


# ---------------------------------------------------------------------------
# failures, stale outputs, publication
# ---------------------------------------------------------------------------


def test_configure_failure_publishes_failure_record_and_keeps_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    assert run_build(BuildRequest(project_root=root, preset="arm-debug")).ok is True
    identity_bytes = identity_path_for(root).read_bytes()
    monkeypatch.setenv("FAKE_CMAKE_EXIT", "3")
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_CONFIGURE_FAILED"
    assert result.data is None
    assert result.details == {
        "stage": "configure",
        "exitCode": 3,
        "log": "artifacts/migration/build.log",
    }
    assert identity_path_for(root).read_bytes() == identity_bytes
    failure = read_json(result_path_for(root))
    assert failure["status"] == "failure"
    assert failure["stage"] == "configure"
    assert failure["code"] == "BUILD_CONFIGURE_FAILED"
    assert failure["buildId"] is None
    assert failure["memory"] == []
    log_text = log_path_for(root).read_text(encoding="utf-8")
    assert "[stage:configure]" in log_text
    assert str(root) not in log_text


def test_build_failure_returns_build_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = prepare_project(tmp_path)
    install_fake_cmake(
        monkeypatch, tmp_path, env={"FAKE_CMAKE_EXIT": "9", "FAKE_CMAKE_FAIL_STAGE": "build"}
    )
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_FAILED"
    assert result.details == {
        "stage": "build",
        "exitCode": 9,
        "log": "artifacts/migration/build.log",
    }
    failure = read_json(result_path_for(root))
    assert failure["stage"] == "build"
    assert failure["code"] == "BUILD_FAILED"
    assert "fake cmake build" in log_path_for(root).read_text(encoding="utf-8")


def test_timeout_publishes_failure_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path, env={"FAKE_CMAKE_SLEEP": "30"})
    result = run_build(BuildRequest(project_root=root, preset="arm-debug", timeout_seconds=1))
    assert result.ok is False
    assert result.code == "BUILD_TIMEOUT"
    assert result.details["stage"] == "configure"
    assert result.details["timeoutSeconds"] == 1
    assert result.details["log"] == "artifacts/migration/build.log"
    assert result.data is None
    failure = read_json(result_path_for(root))
    assert failure["status"] == "failure"
    assert failure["code"] == "BUILD_TIMEOUT"


def test_exit_zero_without_outputs_is_stale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path, env={"FAKE_CMAKE_NO_OUTPUT": "1"})
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_OUTPUT_STALE"
    assert result.details == {"path": "build/arm-debug/firmware.elf", "rule": "missing"}
    assert not identity_path_for(root).exists()
    failure = read_json(result_path_for(root))
    assert failure["status"] == "failure"
    assert failure["code"] == "BUILD_OUTPUT_STALE"


def test_unchanged_outputs_without_prior_evidence_are_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path, env={"FAKE_CMAKE_NO_OUTPUT": "1"})
    elf_dir = root / "build" / "arm-debug"
    elf_dir.mkdir(parents=True, exist_ok=True)
    (elf_dir / "firmware.elf").write_bytes(b"pre-seeded ELF")
    (elf_dir / "firmware.map").write_text("pre-seeded MAP\n", encoding="utf-8")
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_OUTPUT_STALE"
    assert result.details["rule"] == "unverifiable"


def test_legitimate_noop_rebuild_shares_build_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    first = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert first.ok is True
    first_id = first.data.identity.build_id
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")
    second = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert second.ok is True
    assert second.data.identity.build_id == first_id
    second_doc = read_json(result_path_for(root))
    assert second_doc["status"] == "success"
    assert second_doc["buildId"] == first_id


def test_changed_outputs_are_accepted_with_new_build_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    first = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert first.ok is True
    first_id = first.data.identity.build_id
    monkeypatch.setenv("FAKE_CMAKE_ELF_TEXT_SIZE", "32")
    second = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert second.ok is True
    assert second.data.identity.build_id != first_id


def test_input_changed_during_build_returns_input_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path, env={"FAKE_CMAKE_TOUCH_INPUT": "Src/main.c"})
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_INPUT_CHANGED"
    assert result.details == {"path": "Src/main.c"}
    assert not identity_path_for(root).exists()
    failure = read_json(result_path_for(root))
    assert failure["status"] == "failure"
    assert failure["code"] == "BUILD_INPUT_CHANGED"


def test_header_changed_during_build_returns_input_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = tmp_path / "project"
    shutil.copytree(FIXTURE_ROOT, root)
    payload = json.loads((root / ".stm32-project.json").read_text(encoding="utf-8"))
    payload["build"]["includePaths"] = ["Inc"]
    (root / ".stm32-project.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    (root / "Inc").mkdir()
    (root / "Inc" / "board.h").write_text("#pragma once\n", encoding="utf-8")
    (root / ".gitignore").write_text("build/\n.stm32-toolkit/build.lock\n", encoding="utf-8")
    git("init", "-q", cwd=root)
    model = load_project_model(root)
    applied = apply_project_configuration(plan_project_configuration(model))
    assert applied.ok is True
    git("add", "-A", cwd=root)
    git("commit", "-q", "-m", "fixture", cwd=root)
    install_fake_cmake(monkeypatch, tmp_path, env={"FAKE_CMAKE_TOUCH_INPUT": "Inc/board.h"})
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_INPUT_CHANGED"
    assert result.details == {"path": "Inc/board.h"}


def test_map_invalid_publishes_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path, env={"FAKE_CMAKE_MAP_DEFECT": "malformed"})
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_MAP_INVALID"
    assert result.details == {"path": "build/arm-debug/firmware.map", "rule": "regions"}
    assert not identity_path_for(root).exists()


def test_map_overflow_returns_ram_overflow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Overflow is still detected with ELF-backed evidence: disjoint RAM
    LMA intervals of consistent FLASH sections exceed the writable region."""
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path, env={"FAKE_CMAKE_MAP_DEFECT": "overflow"})
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "RAM_OVERFLOW"
    assert result.details == {
        "region": "RAM",
        "used": 196608,
        "length": 131072,
        "overflow": 65536,
    }
    failure = read_json(result_path_for(root))
    assert failure["code"] == "RAM_OVERFLOW"


def test_map_unknown_section_not_in_elf_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path, env={"FAKE_CMAKE_MAP_DEFECT": "unknown"})
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_MAP_INVALID"
    assert result.details == {"path": "build/arm-debug/firmware.map", "rule": "unknown"}
    failure = read_json(result_path_for(root))
    assert failure["code"] == "BUILD_MAP_INVALID"


def test_map_elf_address_mismatch_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path, env={"FAKE_CMAKE_MAP_DEFECT": "address"})
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_MAP_INVALID"
    assert result.details == {"path": "build/arm-debug/firmware.map", "rule": "address"}


def test_map_elf_size_mismatch_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path, env={"FAKE_CMAKE_MAP_DEFECT": "size"})
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_MAP_INVALID"
    assert result.details == {"path": "build/arm-debug/firmware.map", "rule": "size"}


def test_alloc_elf_section_missing_from_map_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(
        monkeypatch, tmp_path, env={"FAKE_CMAKE_MAP_DEFECT": "missing-section"}
    )
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_MAP_INVALID"
    assert result.details == {"path": "build/arm-debug/firmware.map", "rule": "missing"}


def test_non_alloc_elf_sections_absent_from_map_are_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """GNU ld may omit debug rows; ELF debug/comment sections at VMA 0 are
    neither required in the MAP nor counted in memory."""
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path, env={"FAKE_CMAKE_DEBUG_MAP": "1"})
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is True
    assert [item.to_dict() for item in result.data.memory] == [
        {
            "name": "FLASH",
            "origin": 0x08000000,
            "length": 0x100000,
            "used": 0x240,
            "free": 0x100000 - 0x240,
        },
        {
            "name": "RAM",
            "origin": 0x20000000,
            "length": 0x20000,
            "used": 0x500,
            "free": 0x20000 - 0x500,
        },
    ]


def test_runner_orders_elf_validation_before_map_accounting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The ELF is fully validated first and its section evidence is handed
    to MAP accounting for the allocation classification."""
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    import stm32_toolkit.build.runner as runner_mod

    calls: list[str] = []
    real_validate_elf = runner_mod.validate_elf
    real_parse_map = runner_mod.parse_map

    def spy_validate_elf(path, model):
        calls.append("elf")
        return real_validate_elf(path, model)

    def spy_parse_map(text, regions, **kwargs):
        calls.append("map")
        assert kwargs.get("elf_sections") is not None
        return real_parse_map(text, regions, **kwargs)

    monkeypatch.setattr(runner_mod, "validate_elf", spy_validate_elf)
    monkeypatch.setattr(runner_mod, "parse_map", spy_parse_map)
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is True
    assert calls == ["elf", "map"]


def test_elf_invalid_returns_artifact_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path, env={"FAKE_CMAKE_ELF_DEFECT": "no-vector"})
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_ARTIFACT_INVALID"
    assert result.details == {"path": "build/arm-debug/firmware.elf", "rule": "vector"}
    assert not identity_path_for(root).exists()


def test_undefined_global_symbol_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path, env={"FAKE_CMAKE_ELF_DEFECT": "undef-global"})
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_ARTIFACT_INVALID"
    assert result.details == {"path": "build/arm-debug/firmware.elf", "rule": "undefinedSymbols"}


def test_weak_undefined_symbol_is_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path, env={"FAKE_CMAKE_ELF_DEFECT": "weak-undefined"})
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is True


def test_git_invalid_non_repository(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_GIT_INVALID"
    assert result.details == {"rule": "head"}


def test_git_invalid_malformed_head(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = prepare_project(tmp_path)
    hit_file, orig_file = install_fake_git(monkeypatch, tmp_path, "malformed")
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_GIT_INVALID"
    assert result.details == {"rule": "head"}
    # the narrow seam mapped exactly the product's fixed git argv and the
    # fake script actually ran (status is never reached once head is bad)
    assert orig_argv_records(orig_file) == [["git", "rev-parse", "--verify", "HEAD"]]
    assert [record["argv"] for record in hit_records(hit_file)] == [
        ["rev-parse", "--verify", "HEAD"]
    ]


def test_git_invalid_nonzero_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = prepare_project(tmp_path)
    hit_file, orig_file = install_fake_git(monkeypatch, tmp_path, "exit1")
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_GIT_INVALID"
    assert orig_argv_records(orig_file) == [["git", "rev-parse", "--verify", "HEAD"]]
    assert [record["argv"] for record in hit_records(hit_file)] == [
        ["rev-parse", "--verify", "HEAD"]
    ]


def test_git_invalid_overflow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = prepare_project(tmp_path)
    hit_file, orig_file = install_fake_git(monkeypatch, tmp_path, "overflow")
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_GIT_INVALID"
    assert orig_argv_records(orig_file) == [["git", "rev-parse", "--verify", "HEAD"]]
    assert [record["argv"] for record in hit_records(hit_file)] == [
        ["rev-parse", "--verify", "HEAD"]
    ]


def test_dirty_git_is_recorded_truthfully(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    (root / "Src" / "main.c").write_text("int main(void) { return 1; }\n", encoding="utf-8")
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is True
    identity_doc = read_json(identity_path_for(root))
    assert identity_doc["gitDirty"] is True


def test_publication_order_is_log_identity_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    import stm32_toolkit.build.runner as runner_mod

    order: list[str] = []
    real_text = runner_mod.atomic_write_text
    real_json = runner_mod.atomic_write_json

    def spy_text(path, text):
        order.append(Path(path).name)
        return real_text(path, text)

    def spy_json(path, payload):
        order.append(Path(path).name)
        return real_json(path, payload)

    monkeypatch.setattr(runner_mod, "atomic_write_text", spy_text)
    monkeypatch.setattr(runner_mod, "atomic_write_json", spy_json)
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is True
    assert order == ["build.log", "firmware-identity.json", "build-result.json"]


def test_publication_failure_at_result_returns_evidence_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    real_replace = identity_mod._replace

    def failing_replace(src, dst):
        if Path(dst).name == "build-result.json":
            raise OSError("injected replace failure")
        return real_replace(src, dst)

    monkeypatch.setattr(identity_mod, "_replace", failing_replace)
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_EVIDENCE_FAILED"
    assert result.details == {
        "path": "artifacts/migration/build-result.json",
        "phase": "result",
    }
    assert not result_path_for(root).exists()
    leftovers = [
        path for path in (root / "artifacts" / "migration").iterdir() if ".tmp" in path.name
    ]
    assert leftovers == []
    assert identity_path_for(root).exists()


def test_publication_failure_at_log_returns_evidence_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    real_replace = identity_mod._replace

    def failing_replace(src, dst):
        if Path(dst).name == "build.log":
            raise OSError("injected replace failure")
        return real_replace(src, dst)

    monkeypatch.setattr(identity_mod, "_replace", failing_replace)
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_EVIDENCE_FAILED"
    assert not log_path_for(root).exists()
    assert not result_path_for(root).exists()


def test_crlf_output_is_normalized_in_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path, env={"FAKE_CMAKE_CRLF": "1"})
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is True
    log_text = log_path_for(root).read_text(encoding="utf-8")
    assert "\r" not in log_text


def test_success_publication_writes_no_unrelated_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    before = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is True
    after = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }
    new_files = after - before
    # portable forward-slash inventory on every host (never os.sep, never
    # backslashes from Windows ``relative_to``) and no unrelated write
    assert new_files <= {
        "build/arm-debug/firmware.elf",
        "build/arm-debug/firmware.map",
        "build/arm-debug/firmware-identity.json",
        "artifacts/migration/build.log",
        "artifacts/migration/build-result.json",
        ".stm32-toolkit/build.lock",
    }


def test_json_contract_of_published_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    assert run_build(BuildRequest(project_root=root, preset="arm-debug")).ok is True
    for path in (identity_path_for(root), result_path_for(root)):
        raw = path.read_bytes()
        assert raw.startswith(b"{")
        assert not raw.startswith(b"\xef\xbb\xbf")
        assert raw.endswith(b"\n")
        assert b"\r" not in raw
        text = raw.decode("utf-8")
        assert "\n  " in text  # indent=2


def test_missing_source_publishes_failure_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    (root / "Src" / "main.c").unlink()
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_INPUT_INVALID"
    assert result.details == {"path": "Src/main.c", "rule": "missing"}
    failure = read_json(result_path_for(root))
    assert failure["status"] == "failure"
    assert failure["code"] == "BUILD_INPUT_INVALID"
    assert not identity_path_for(root).exists()


def test_git_failure_publishes_failure_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = prepare_project(tmp_path)
    cmake_hit = install_fake_cmake(monkeypatch, tmp_path)
    git_hit, git_orig = install_fake_git(monkeypatch, tmp_path, "exit1")
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_GIT_INVALID"
    # both seams are installed; git failed before any cmake stage ran
    assert orig_argv_records(git_orig) == [["git", "rev-parse", "--verify", "HEAD"]]
    assert [record["argv"] for record in hit_records(git_hit)] == [
        ["rev-parse", "--verify", "HEAD"]
    ]
    assert hit_records(cmake_hit) == []
    failure = read_json(result_path_for(root))
    assert failure["status"] == "failure"
    assert failure["code"] == "BUILD_GIT_INVALID"
    assert failure["stage"] == "git"
    assert not identity_path_for(root).exists()


def test_fake_git_and_cmake_seams_compose(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The git and cmake seams compose in one build on every host.

    With both seams installed, the product's bare ``"git"`` argv reaches
    the fake git script, its bare ``"cmake"`` argv reaches the fake cmake
    script, and an unrelated invocation is delegated unchanged to the real
    ``subprocess.Popen`` — no Windows PATH resolution of ``git.cmd`` is
    involved anywhere.  prepare_project's real ``git init/add/commit`` ran
    before either seam existed and is therefore never intercepted.
    """
    root = prepare_project(tmp_path)
    cmake_hit = install_fake_cmake(monkeypatch, tmp_path)
    git_hit, git_orig = install_fake_git(monkeypatch, tmp_path, "ok")
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is True
    # the fake git answered both fixed product argv with a synthetic HEAD
    # and a clean status (ambient Git would report the fixture's own SHA)
    assert orig_argv_records(git_orig) == [
        ["git", "rev-parse", "--verify", "HEAD"],
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
    ]
    assert [record["argv"] for record in hit_records(git_hit)] == [
        ["rev-parse", "--verify", "HEAD"],
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
    ]
    identity_doc = read_json(identity_path_for(root))
    assert identity_doc["gitHead"] == "a" * 40
    assert identity_doc["gitDirty"] is False
    # the cmake seam still routes configure and build to the cmake double
    assert [record["argv"] for record in hit_records(cmake_hit)] == [
        ["--preset", "arm-debug"],
        ["--build", "--preset", "arm-debug"],
    ]
    # an unrelated invocation is delegated to the real implementation
    completed = subprocess.run(
        [sys.executable, "-c", "print('delegated')"],
        cwd=str(tmp_path),
        capture_output=True,
        timeout=30,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == b"delegated"


def test_pre_configure_input_change_returns_input_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    # the fake git touches an input between the two pre-configure snapshots
    _, orig_file = install_fake_git_script(
        monkeypatch,
        tmp_path,
        "import os, sys\n"
        "with open('Src/main.c', 'ab') as handle:\n"
        "    handle.write(b'/* touched by fake git */\\n')\n"
        "if len(sys.argv) >= 2 and sys.argv[1] == 'rev-parse':\n"
        "    sys.stdout.write('a' * 40 + '\\n')\n"
        "    sys.stdout.flush()\n"
        "os._exit(0)\n",
    )
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_INPUT_CHANGED"
    assert result.details == {"path": "Src/main.c"}
    # the dynamic script ran behind the same narrow seam for both fixed argv
    assert orig_argv_records(orig_file) == [
        ["git", "rev-parse", "--verify", "HEAD"],
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
    ]
    failure = read_json(result_path_for(root))
    assert failure["code"] == "BUILD_INPUT_CHANGED"
    assert failure["stage"] == "snapshot"


def test_fake_cmake_launcher_reaches_the_python_double(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The installed launcher must execute the Python double on this host.

    Running the launcher directly with a probe argv must record a hit and
    answer with the double's unknown-argv exit code — proving the launcher
    chain is complete (Windows ``.cmd`` references a real script) and never
    falls through to an ambient real CMake.
    """
    hit_file = install_fake_cmake(monkeypatch, tmp_path)
    launcher = fake_cmake_launcher(tmp_path / "fakebin")
    assert launcher.exists()
    completed = subprocess.run(
        [str(launcher), "--probe"], cwd=str(tmp_path), capture_output=True, timeout=30
    )
    assert completed.returncode == 2  # the double's unknown-argv exit code
    assert b"[fake cmake] unexpected argv" in completed.stderr
    assert hit_records(hit_file) == [{"argv": ["--probe"], "cwd": str(tmp_path)}]


def test_launch_failure_returns_configure_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    target = tmp_path / "fakebin" / "fake_cmake.py"
    target.unlink()
    target.mkdir()  # the seam's launch target is destroyed: spawn must fail
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_CONFIGURE_FAILED"
    assert result.details == {"stage": "configure", "rule": "launch", "log": "artifacts/migration/build.log"}
    failure = read_json(result_path_for(root))
    assert failure["status"] == "failure"
    assert failure["code"] == "BUILD_CONFIGURE_FAILED"


def test_oversized_elf_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    monkeypatch.setattr(identity_mod, "_ELF_LIMIT_BYTES", 16)
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_ARTIFACT_INVALID"
    assert result.details == {"path": "build/arm-debug/firmware.elf", "rule": "size"}


def test_noop_rebuild_with_tampered_prior_evidence_is_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    assert run_build(BuildRequest(project_root=root, preset="arm-debug")).ok is True
    identity_path = identity_path_for(root)
    document = read_json(identity_path)
    document["buildId"] = "0" * 64
    identity_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_OUTPUT_STALE"
    assert result.details == {"path": "build/arm-debug/firmware.elf", "rule": "unverifiable"}


def test_release_noop_without_release_prior_evidence_is_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    assert run_build(BuildRequest(project_root=root, preset="arm-debug")).ok is True
    elf_dir = root / "build" / "arm-release"
    elf_dir.mkdir(parents=True, exist_ok=True)
    (elf_dir / "firmware.elf").write_bytes(build_elf_bytes())
    (elf_dir / "firmware.map").write_text(build_map_text())
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")
    result = run_build(BuildRequest(project_root=root, preset="arm-release"))
    assert result.ok is False
    assert result.code == "BUILD_OUTPUT_STALE"
    assert result.details == {"path": "build/arm-release/firmware.elf", "rule": "unverifiable"}


def test_failure_record_publication_failure_returns_evidence_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path, env={"FAKE_CMAKE_EXIT": "3"})
    real_replace = identity_mod._replace

    def failing_replace(src, dst):
        if Path(dst).name == "build-result.json":
            raise OSError("injected replace failure")
        return real_replace(src, dst)

    monkeypatch.setattr(identity_mod, "_replace", failing_replace)
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_EVIDENCE_FAILED"
    assert result.details == {
        "path": "artifacts/migration/build-result.json",
        "phase": "result",
    }
    assert not result_path_for(root).exists()


def test_lock_contention_via_seam(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = prepare_project(tmp_path, git_repo=False)
    import stm32_toolkit.build.runner as runner_mod

    monkeypatch.setattr(runner_mod, "_lock_impl", lambda fd: False)
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_BUSY"
    assert result.details == {"path": ".stm32-toolkit/build.lock"}


def raise_on_open(path: Path, monkeypatch: pytest.MonkeyPatch, error: OSError) -> None:
    """Make ``Path.open`` raise ``error`` for ``path`` (platform-independent)."""
    real_open = Path.open

    def patched(self, mode: str = "r", *args, **kwargs):
        if mode == "rb" and self == path:
            raise error
        return real_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", patched)


def rewrite_json(path: Path, mutator) -> None:
    document = read_json(path)
    mutator(document)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def tamper_identity(root: Path, mutator) -> None:
    path = identity_path_for(root)
    rewrite_json(path, mutator)
    document = read_json(path)
    document["buildId"] = identity_mod.compute_build_id(document)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# coverage closure: prerequisites, locks, publication, prior evidence
# ---------------------------------------------------------------------------


def test_run_build_rejects_wrong_generation_tool(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    rewrite_json(root / ".stm32-project.json", lambda doc: doc["generatedBy"].__setitem__("tool", "other"))
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.code == "BUILD_PROJECT_INVALID"
    assert result.details == {"field": "generation.tool", "rule": "tool"}


def test_run_build_rejects_wrong_generation_version(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    rewrite_json(root / ".stm32-project.json", lambda doc: doc["generatedBy"].__setitem__("version", "9.9.9"))
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.code == "BUILD_PROJECT_INVALID"
    assert result.details == {"field": "generation.version", "rule": "version"}


def test_run_build_rejects_non_portable_manifest_path(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    rewrite_json(
        root / ".stm32-project.json",
        lambda doc: doc["generation"].__setitem__("managedManifest", "a//b"),
    )
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.code == "BUILD_PROJECT_INVALID"
    assert result.details == {"path": "a//b", "rule": "manifest"}


def test_run_build_rejects_unreadable_manifest(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path, git_repo=False)
    raise_on_open(root / ".stm32-toolkit" / "generated-files.json", monkeypatch, PermissionError("injected"))
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.code == "BUILD_PROJECT_INVALID"
    assert result.details == {"path": ".stm32-toolkit/generated-files.json", "rule": "manifest"}


def test_run_build_rejects_foreign_manifest_record(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    rewrite_json(
        root / ".stm32-toolkit" / "generated-files.json",
        lambda doc: doc["files"].insert(
            next(index for index, item in enumerate(doc["files"]) if item["path"] == "linker/stm32tk.ld"),
            {"path": "extra.txt", "ownership": "managed", "templateVersion": 1, "sha256": "a" * 64},
        ),
    )
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.code == "BUILD_PROJECT_INVALID"
    assert result.details == {"path": "extra.txt", "rule": "ownership"}


def test_run_build_rejects_missing_generated_file(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    (root / "CMakeLists.txt").unlink()
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.code == "BUILD_PROJECT_INVALID"
    assert result.details == {"path": "CMakeLists.txt", "rule": "missing"}


def test_run_build_rejects_unreadable_generated_file(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path, git_repo=False)
    raise_on_open(root / "CMakeLists.txt", monkeypatch, PermissionError("injected"))
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.code == "BUILD_PROJECT_INVALID"
    assert result.details == {"path": "CMakeLists.txt", "rule": "unreadable"}


def test_map_missing_is_stale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path, env={"FAKE_CMAKE_MAP_DEFECT": "missing"})
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_OUTPUT_STALE"
    assert result.details == {"path": "build/arm-debug/firmware.map", "rule": "missing"}


def test_pre_configure_snapshot_raise_publishes_failure(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    _, orig_file = install_fake_git_script(
        monkeypatch,
        tmp_path,
        "import os, sys\n"
        "if len(sys.argv) >= 2 and sys.argv[1] == 'rev-parse':\n"
        "    sys.stdout.write('a' * 40 + '\\n')\n"
        "    sys.stdout.flush()\n"
        "else:\n"
        "    os.remove('Src/main.c')\n"
        "os._exit(0)\n",
    )
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_INPUT_INVALID"
    assert result.details == {"path": "Src/main.c", "rule": "missing"}
    # the dynamic script ran behind the same narrow seam for both fixed argv
    assert orig_argv_records(orig_file) == [
        ["git", "rev-parse", "--verify", "HEAD"],
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
    ]
    failure = read_json(result_path_for(root))
    assert failure["stage"] == "snapshot"


def test_post_build_snapshot_raise_publishes_failure(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path, env={"FAKE_CMAKE_DELETE_INPUT": "Src/main.c"})
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_INPUT_INVALID"
    assert result.details == {"path": "Src/main.c", "rule": "missing"}
    failure = read_json(result_path_for(root))
    assert failure["stage"] == "validate"


def test_success_identity_publication_failure(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    real_replace = identity_mod._replace

    def failing_replace(src, dst):
        if Path(dst).name == "firmware-identity.json":
            raise OSError("injected replace failure")
        return real_replace(src, dst)

    monkeypatch.setattr(identity_mod, "_replace", failing_replace)
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_EVIDENCE_FAILED"
    assert result.details == {
        "path": "build/arm-debug/firmware-identity.json",
        "phase": "identity",
    }
    assert not identity_path_for(root).exists()
    assert log_path_for(root).exists()


def test_failure_record_log_publication_failure(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path, env={"FAKE_CMAKE_EXIT": "3"})
    real_replace = identity_mod._replace

    def failing_replace(src, dst):
        if Path(dst).name == "build.log":
            raise OSError("injected replace failure")
        return real_replace(src, dst)

    monkeypatch.setattr(identity_mod, "_replace", failing_replace)
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_EVIDENCE_FAILED"
    assert result.details == {"path": "artifacts/migration/build.log", "phase": "log"}
    assert not log_path_for(root).exists()


@pytest.mark.parametrize(
    "tamper",
    [
        lambda root, _result: rewrite_json(result_path_for(root), lambda doc: doc.__setitem__("status", "failure")),
        lambda root, _result: rewrite_json(result_path_for(root), lambda doc: doc.__setitem__("preset", "arm-release")),
        lambda root, _result: rewrite_json(result_path_for(root), lambda doc: doc.__setitem__("targetDevice", "OTHER")),
        lambda root, _result: rewrite_json(result_path_for(root), lambda doc: doc.__setitem__("inputSnapshotSha256", "0" * 64)),
        lambda root, _result: rewrite_json(result_path_for(root), lambda doc: doc.__setitem__("gitHead", "0" * 40)),
        lambda root, _result: rewrite_json(result_path_for(root), lambda doc: doc.__setitem__("buildId", "1" * 64)),
        lambda root, _result: tamper_identity(root, lambda doc: doc.__setitem__("preset", "arm-release")),
        lambda root, _result: tamper_identity(root, lambda doc: doc.__setitem__("elfPath", "build/arm-debug/other.elf")),
        lambda root, _result: tamper_identity(root, lambda doc: doc.__setitem__("elfSha256", "0" * 64)),
        lambda root, _result: tamper_identity(root, lambda doc: doc.__setitem__("mapSha256", "0" * 64)),
    ],
)
def test_noop_rebuild_with_mismatched_prior_evidence_is_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tamper
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    first = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert first.ok is True
    tamper(root, first)
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_OUTPUT_STALE"
    assert result.details == {"path": "build/arm-debug/firmware.elf", "rule": "unverifiable"}


def test_artifact_state_edge_cases(tmp_path: Path, monkeypatch):
    import stm32_toolkit.build.runner as runner_mod

    assert runner_mod._artifact_state(tmp_path / "missing") == runner_mod._ArtifactState(False, 0, 0, "")
    target = tmp_path / "firmware.elf"
    target.write_bytes(b"x" * 100)
    assert runner_mod._artifact_state(target) == runner_mod._ArtifactState(True, 100, target.stat().st_mtime_ns, sha256_hex(b"x" * 100))
    raise_on_open(target, monkeypatch, PermissionError("injected"))
    state = runner_mod._artifact_state(target)
    assert state.exists is True
    assert state.sha256 == ""
    monkeypatch.setattr(runner_mod, "_ELF_LIMIT_BYTES", 16)
    state = runner_mod._artifact_state(target)
    assert state.exists is True
    assert state.sha256 == ""


def test_build_lock_direct_behavior(tmp_path: Path, monkeypatch):
    import stm32_toolkit.build.runner as runner_mod

    lock = runner_mod._BuildLock(tmp_path / "build.lock")
    assert lock.acquire() is True
    lock.release()
    lock.release()  # idempotent when already released

    real_open = os.open

    def failing_open(path, flags, *args):
        raise OSError("injected")

    monkeypatch.setattr(os, "open", failing_open)
    assert lock.acquire() is False

    monkeypatch.setattr(os, "open", real_open)

    def failing_close(fd):
        raise OSError("injected")

    monkeypatch.setattr(os, "close", failing_close)
    monkeypatch.setattr(runner_mod, "_lock_impl", lambda fd: False)
    assert lock.acquire() is False

    monkeypatch.setattr(runner_mod, "_lock_impl", lambda fd: True)
    assert lock.acquire() is True
    lock.release()


def test_model_artifact_paths_direct_validation(tmp_path: Path):
    from dataclasses import replace

    from stm32_toolkit.build.identity import model_artifact_paths

    root = prepare_project(tmp_path, git_repo=False)
    model = load_project_model(root)
    with pytest.raises(Exception) as error:
        model_artifact_paths(model, "host")
    assert getattr(error.value, "code", None) == "BUILD_REQUEST_INVALID"
    with pytest.raises(Exception) as error:
        model_artifact_paths(replace(model, build=replace(model.build, elf=None)), "arm-debug")
    assert getattr(error.value, "code", None) == "BUILD_PROJECT_INVALID"
    with pytest.raises(Exception) as error:
        model_artifact_paths(
            replace(model, build=replace(model.build, elf="build/arm-debug/")), "arm-debug"
        )
    assert getattr(error.value, "code", None) == "BUILD_PROJECT_INVALID"
    with pytest.raises(Exception) as error:
        model_artifact_paths(
            replace(model, build=replace(model.build, elf="build/arm-debug/x/evil.elf")),
            "arm-debug",
        )
    assert getattr(error.value, "code", None) == "BUILD_PROJECT_INVALID"
