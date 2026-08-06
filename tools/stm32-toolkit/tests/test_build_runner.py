"""Build runner, locking, publication, and stale-output defense contracts.

Every fixture project is copied to a disposable pytest temporary directory,
managed configuration is generated through the STM32TK-0304 plan/apply path,
a git repository records the project state, and a Python ``cmake`` double
with an explicit ``sys.executable`` wrapper (hit-proven) stands in for the
real toolchain.  No real CMake/Ninja/ARM toolchain is required and no build
artifact is committed.
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
    text_addr: int = 0x08000040,
    text_size: int = 16,
    include_vector: bool = True,
    include_symtab: bool = True,
    reset_undefined: bool = False,
    undefined_global: tuple[str, ...] = (),
    undefined_weak: tuple[str, ...] = (),
    elf_class: int = 1,
    elf_data: int = 1,
    elf_machine: int = 40,
    fixed_sections: tuple[tuple[str, int, int], ...] = (),
    truncate: int = 0,
) -> bytes:
    """Build a minimal valid ELF32 little-endian ARM image for tests.

    Layout: ELF header, ``.isr_vector`` (first word 0x20020000, second word
    the reset handler), ``.text``, optional fixed ``.stm32tk.abs.*``
    sections, ``.symtab``/``.strtab``/``.shstrtab`` and the section header
    table.  ``truncate`` cuts the file short to emulate malformed input.
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
        add(".isr_vector", 1, 0x2, vector_addr, vector_data)
    text_index = add(".text", 1, 0x6, text_addr, b"\x00\xbf" * (text_size // 2))

    symbol_names = ["Reset_Handler", "main", *undefined_global, *undefined_weak]
    strtab = bytearray(b"\x00")
    name_offsets: dict[str, int] = {}
    for name in symbol_names:
        name_offsets[name] = len(strtab)
        strtab += name.encode("utf-8") + b"\x00"
    strtab_data = bytes(strtab)

    symbols: list[tuple[int, int, int, int, int, int]] = []  # (name, value, size, info, other, shndx)
    symbols.append((0, 0, 0, 0, 0, 0))  # null symbol
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

    shstr_names = [".isr_vector", ".text", ".symtab", ".strtab", ".shstrtab"]
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

FAKE_GIT_WRAPPER = """#!{python}
import os
import sys

mode = os.environ.get("FAKE_GIT_MODE", "ok")
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
        if env.get("FAKE_CMAKE_NO_OUTPUT") == "1":
            return 0
        regions = [
            (region["name"], region["origin"], region["length"])
            for region in payload["memory"]["regions"]
        ]
        defect_elf = env.get("FAKE_CMAKE_ELF_DEFECT", "")
        defect_map = env.get("FAKE_CMAKE_MAP_DEFECT", "")
        elf = build_elf_bytes(
            text_size=int(env.get("FAKE_CMAKE_ELF_TEXT_SIZE", "16")),
            **ELF_DEFECTS.get(defect_elf, {}),
        )
        if defect_map == "malformed":
            map_text = "this is not a GNU linker map\n"
        elif defect_map == "overflow":
            map_text = build_map_text(
                regions=regions, sections=((".text", 0x08000000, 0x200000, None),)
            )
        else:
            map_text = build_map_text(regions=regions)
        with open(elf_path, "wb") as handle:
            handle.write(elf)
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
    "truncated": {"truncate": 40},
}


def install_fake_cmake(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    env: dict[str, str] | None = None,
) -> Path:
    """Install the hit-proven fake ``cmake`` at the front of PATH."""
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    tests_dir = Path(__file__).parent
    if os.name == "nt":
        launcher = bin_dir / "cmake.cmd"
        launcher.write_text(
            f'@echo off\r\n"{sys.executable}" "{bin_dir / "fake_cmake.py"}" %*\r\n',
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
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("FAKE_CMAKE_HIT_FILE", str(hit_file))
    for key, value in (env or {}).items():
        monkeypatch.setenv(key, value)
    return hit_file


def install_fake_git(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mode: str) -> None:
    """Install a fake ``git`` binary that fails or emits malformed evidence."""
    bin_dir = tmp_path / "fakegit"
    bin_dir.mkdir(parents=True, exist_ok=True)
    launcher = bin_dir / "git"
    launcher.write_text(FAKE_GIT_WRAPPER.format(python=sys.executable), encoding="utf-8")
    launcher.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("FAKE_GIT_MODE", mode)


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


def test_map_overflow_returns_flash_overflow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path, env={"FAKE_CMAKE_MAP_DEFECT": "overflow"})
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "FLASH_OVERFLOW"
    assert result.details == {
        "region": "FLASH",
        "used": 2097152,
        "length": 1048576,
        "overflow": 1048576,
    }
    failure = read_json(result_path_for(root))
    assert failure["code"] == "FLASH_OVERFLOW"


def test_elf_invalid_returns_artifact_invalid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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
    install_fake_git(monkeypatch, tmp_path, "malformed")
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_GIT_INVALID"
    assert result.details == {"rule": "head"}


def test_git_invalid_nonzero_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = prepare_project(tmp_path)
    install_fake_git(monkeypatch, tmp_path, "exit1")
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_GIT_INVALID"


def test_git_invalid_overflow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = prepare_project(tmp_path)
    install_fake_git(monkeypatch, tmp_path, "overflow")
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is False
    assert result.code == "BUILD_GIT_INVALID"


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
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is True
    after = {
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }
    new_files = after - before
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
