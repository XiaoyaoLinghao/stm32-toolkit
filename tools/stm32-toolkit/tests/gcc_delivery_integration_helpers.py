"""Shared offline helpers for the GCC delivery integration journey.

This module is test-only infrastructure for the cross-branch GCC delivery
integration.  It contains no product behavior:

* one synthetic, non-Git Keil fixture whose authored C/header comments are GBK
  and whose required quoted macro header supplies the fixed-pool address,
* the existing ``normalize-source-comments`` helper invocation (preview and
  reviewed copy) plus the explicit complete prepared-tree copy described by
  that skill,
* real toolchain discovery and path scoping for the installed ARM GNU toolchain,
* small ELF/MAP evidence readers,
* an in-memory deterministic Probe backend that programs exactly the PT_LOAD
  payload of the ELF it actually receives and serves readback from that freshly
  programmed memory.

Nothing here fabricates build identities, compiler output, managed digests, or
firmware artifacts.  The real Toolkit build workflow produces all evidence.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from elftools.elf.elffile import ELFFile

from stm32_toolkit.hardware_workflows import (
    FlashWorkflowRequest,
    HardwareWorkflowSeams,
    flash_workflow,
)
from stm32_toolkit.probe.backend import (
    FlashBackendReport,
    ProbeBackendError,
    ProbeDescriptor,
)

from fakes.fake_probe import FakeProbeBackend

# ---------------------------------------------------------------------------
# fixture identity
# ---------------------------------------------------------------------------

PROBE_ID = "probe-a"
TARGET_NAME = "Legacy"
UVPROJX = "app.uvprojx"
STARTUP_SOURCE = "Startup/startup_synthetic.s"
FIXED_ADDRESS = 0x68000010
ALIGNMENT = 16
RUNTIME_LITERAL = "runtime /* not a comment */ __wfi()"
WFI_FUNCTION = "WFI_SET"
WFI_SOURCE = "Common/wfi.c"

EXTRA_SRAM2 = {
    "name": "SRAM2",
    "origin": 0x68000000,
    "length": 0x40000,
    "attributes": "rw-",
}
MAIN_RAM_LAYOUT = {
    "flash": "IROM1",
    "data": "IRAM1",
    "bss": "IRAM1",
    "heap": "IRAM1",
    "stack": "IRAM1",
}
WFI_RETURNS = [{"path": WFI_SOURCE, "function": WFI_FUNCTION}]
STARTUP_STRATEGY = "generate-cmsis-gcc"

_CPU = (
    'IROM(0x8000000,0x100000) IRAM(0x20000000,0x30000) '
    'IRAM2(0x10000000,0x10000) CPUTYPE("Cortex-M4")'
)

#: Authored GBK C source.  The only non-ASCII bytes are inside the C comment;
#: the runtime string literal stays ASCII and must never be rewritten.
MAIN_C_TEXT = (
    "/* 主循环：固定缓冲区布局来自板级头文件。 */\n"
    '#include "stm32f4xx.h"\n'
    '#include "board_layout.h"\n'
    "\n"
    "__align(16) volatile unsigned int aligned_runtime[BOARD_BUFFER_WORDS];\n"
    "__at(BOARD_FIXED_ADDRESS) volatile unsigned int fixed_buffer[4];\n"
    "\n"
    'static const char runtime_marker[] = "' + RUNTIME_LITERAL + '";\n'
    "\n"
    "void SystemInit(void)\n"
    "{\n"
    "}\n"
    "\n"
    "int main(void)\n"
    "{\n"
    "    unsigned int total = 0u;\n"
    "    unsigned int index;\n"
    "    for (index = 0u; index < BOARD_BUFFER_WORDS; ++index)\n"
    "    {\n"
    "        aligned_runtime[index] = index;\n"
    "        total += aligned_runtime[index];\n"
    "    }\n"
    "    total += fixed_buffer[0] + fixed_buffer[3];\n"
    "    total += (unsigned int)(unsigned char)runtime_marker[0];\n"
    "    return (int)(total & 0x1u);\n"
    "}\n"
)

#: The required quoted macro header.  It is selected for comment conversion
#: together with the C source and supplies the fixed-pool address expression.
HEADER_TEXT = (
    "/*\n"
    " * 板级内存布局：外部 SRAM2 固定地址与对齐缓冲区尺寸。\n"
    " */\n"
    "#ifndef BOARD_LAYOUT_H\n"
    "#define BOARD_LAYOUT_H\n"
    "\n"
    "/* Authored portability macro so the array declaration is valid in both\n"
    " * ARMCC and GNU C without relying on the Keil environment. */\n"
    "#ifndef __align\n"
    "#define __align(n) __attribute__((aligned(n)))\n"
    "#endif\n"
    "\n"
    "#define BOARD_FIXED_ADDRESS 0x68000010\n"
    "#define BOARD_BUFFER_WORDS 16\n"
    "\n"
    "#endif\n"
)

WFI_TEXT = (
    "/* 等待中断，迁移时选择正常返回。 */\n"
    "__asm void WFI_SET(void) { WFI; }\n"
)

LICENSE_TEXT = "Synthetic integration fixture license. Not a vendor license.\n"
README_TEXT = "Synthetic cross-branch GCC delivery fixture.\n"
DOCS_TEXT = "Synthetic unlisted resource retained across preparation.\n"
UNLISTED_SOURCE_TEXT = "/* synthetic unlisted source resource */\nint legacy_note;\n"
BINARY_RESOURCE = b"\x00\x01\x02synthetic-resource\xff\x00"

NORMALIZER_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "skills"
    / "normalize-source-comments"
    / "scripts"
    / "normalize_comments.py"
)


# ---------------------------------------------------------------------------
# digests and inventories
# ---------------------------------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tree_inventory(root: Path) -> dict[str, str]:
    """Map every regular file (portable relative path) to its SHA-256."""

    root = root.resolve()
    inventory: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        inventory[path.relative_to(root).as_posix()] = sha256_bytes(
            path.read_bytes()
        )
    return inventory


def tree_directories(root: Path) -> set[str]:
    root = root.resolve()
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_dir()
    }


def assert_no_git_metadata(*roots: Path) -> None:
    for root in roots:
        assert not (root / ".git").exists(), root
        assert ".git" not in tree_directories(root), root
        assert not any(
            part == ".git" for path in tree_inventory(root) for part in path.split("/")
        ), root


def assert_under(parent: Path, *paths: Path) -> None:
    parent = parent.resolve()
    for path in paths:
        resolved = path.resolve()
        assert resolved == parent or parent in resolved.parents, (parent, resolved)


# ---------------------------------------------------------------------------
# synthetic no-Git fixture
# ---------------------------------------------------------------------------


def build_no_git_project(root: Path) -> Path:
    """Create the disposable synthetic Keil project below ``root`` (no Git)."""

    from test_migration_plan import (  # local test helper reuse
        FRAMEWORK_INCLUDE,
        _add_group_scoped_controls,
        build_repo,
    )

    root.mkdir(parents=True, exist_ok=True)
    repo = build_repo(
        root,
        name="source",
        files={},
        uvprojx_kwargs={
            "device": "STM32F429ZGTx",
            "cpu": _CPU,
            "fpu": None,
            "output": "app",
            "defines": "USE_STDPERIPH_DRIVER,STM32F429xx",
            "groups": (
                ("Main", (("main.c", "1", "Main/main.c"),)),
                ("Common", (("wfi.c", "1", WFI_SOURCE),)),
                (
                    "Startup",
                    (("startup_synthetic.s", "2", STARTUP_SOURCE),),
                ),
            ),
            "includes": f"Main;Common;{FRAMEWORK_INCLUDE}",
        },
        commit=False,
    )

    authored: dict[str, bytes] = {
        "Main/main.c": MAIN_C_TEXT.encode("gbk"),
        "Board/board_layout.h": HEADER_TEXT.encode("gbk"),
        WFI_SOURCE: WFI_TEXT.encode("gbk"),
        STARTUP_SOURCE: _startup_bytes(),
        "LICENSE": LICENSE_TEXT.encode("utf-8"),
        "README.md": README_TEXT.encode("utf-8"),
        "Assets/logo.bin": BINARY_RESOURCE,
        "Docs/notes.txt": DOCS_TEXT.encode("utf-8"),
        "Legacy/notes.c": UNLISTED_SOURCE_TEXT.encode("utf-8"),
        f"{FRAMEWORK_INCLUDE}/stm32f4xx.h": b"#pragma once\n/* synthetic */\n",
    }
    for relative, data in authored.items():
        target = repo.joinpath(*relative.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    # One include-only scoped option: ``Board`` is exposed only by the Main
    # group, and the reviewed merge must carry it into the GCC include list.
    _add_group_scoped_controls(repo, "Main", include_paths="Board")
    assert not (repo / ".git").exists()
    return repo


def _startup_bytes() -> bytes:
    from startup_gcc_fixture import SYNTHETIC_STARTUP

    return SYNTHETIC_STARTUP.encode("utf-8")


# ---------------------------------------------------------------------------
# existing comment-normalization helper and complete prepared copy
# ---------------------------------------------------------------------------


def _run_normalizer(*arguments: str) -> tuple[subprocess.CompletedProcess, dict]:
    completed = subprocess.run(
        [sys.executable, "-I", str(NORMALIZER_SCRIPT), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
        check=False,
    )
    payload = json.loads(completed.stdout) if completed.stdout.strip() else {}
    return completed, payload


def preview_source_comments(
    source: Path, preview_dir: Path
) -> tuple[dict[str, object], dict[str, object]]:
    """Run the existing helper's read-only preview for the GBK selection."""

    completed, payload = _run_normalizer(
        "preview",
        "--project-root",
        str(source.resolve()),
        "--preview-dir",
        str(preview_dir),
        "--file",
        "Main/main.c=gbk",
        "--file",
        "Board/board_layout.h=gbk",
    )
    assert completed.returncode == 0, (completed.stdout, completed.stderr)
    assert payload["status"] == "ready", payload
    assert payload["readOnlyPreview"] is True
    plan_path = Path(payload["planPath"])
    assert plan_path.is_file()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan["planId"] == payload["planId"]
    return payload, plan


def copy_reviewed_comments(
    source: Path, preview_payload: dict[str, object], copy_dir: Path
) -> tuple[dict[str, object], dict[str, object]]:
    """Copy exactly the reviewed converted files from the reviewed plan."""

    completed, payload = _run_normalizer(
        "copy",
        "--project-root",
        str(source.resolve()),
        "--plan",
        str(preview_payload["planPath"]),
        "--plan-id",
        str(preview_payload["planId"]),
        "--output-dir",
        str(copy_dir),
    )
    assert completed.returncode == 0, (completed.stdout, completed.stderr)
    assert payload["status"] == "ok", payload
    assert payload["originalsUnchanged"] is True
    assert payload["outputsVerified"] is True
    manifest_path = Path(payload["manifestPath"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["planId"] == preview_payload["planId"]
    assert manifest["originalsUnchanged"] is True
    assert manifest["outputsVerified"] is True
    assert not (copy_dir / "INCOMPLETE.json").exists()
    return payload, manifest


def prepare_complete_project(
    source: Path,
    copy_dir: Path,
    manifest: dict[str, object],
    prepared: Path,
) -> dict[str, str]:
    """Copy the complete project tree and overlay only reviewed copies.

    This is the explicit complete-project preparation described by the skill;
    it is not a product API and it is not a migration.  ``.git`` metadata is
    never copied.  Every overlay is proven against the reviewed source digest
    and the helper's recorded output digest before it is written.
    """

    assert not prepared.exists()
    prepared.parent.mkdir(parents=True, exist_ok=True)
    assert_under(prepared.parent, prepared)

    selected = {entry["path"]: entry for entry in manifest["files"]}
    copied_outputs: set[str] = set()

    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if any(part == ".git" for part in relative.parts):
            continue
        target = prepared / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())

    for relative, entry in sorted(selected.items()):
        original = source.joinpath(*relative.split("/"))
        assert sha256_bytes(original.read_bytes()) == entry["sourceSha256"], relative
        converted = copy_dir.joinpath(*relative.split("/"))
        converted_bytes = converted.read_bytes()
        assert sha256_bytes(converted_bytes) == entry["outputSha256"], relative
        target = prepared.joinpath(*relative.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(converted_bytes)
        copied_outputs.add(relative)
        converted_bytes.decode("utf-8", "strict")

    # The copy directory contains only the reviewed files plus its manifest.
    actual_copies = {
        path.relative_to(copy_dir).as_posix()
        for path in copy_dir.rglob("*")
        if path.is_file()
    }
    assert actual_copies == copied_outputs | {"manifest.json"}

    prepared_inventory = tree_inventory(prepared)
    source_inventory = tree_inventory(source)
    assert set(prepared_inventory) == set(source_inventory)
    assert_no_git_metadata(prepared)
    for relative in selected:
        assert prepared_inventory[relative] == selected[relative]["outputSha256"]
    for relative in set(source_inventory) - set(selected):
        assert prepared_inventory[relative] == source_inventory[relative]
    return prepared_inventory


# ---------------------------------------------------------------------------
# installed offline toolchain
# ---------------------------------------------------------------------------

GNU_BIN = Path(
    os.environ.get(
        "STM32TK_ARM_GNU_BIN",
        r"C:/ST/STM32CubeCLT_1.22.0/GNU-tools-for-STM32/bin",
    )
)
CMAKE_BIN = Path(
    os.environ.get("STM32TK_CMAKE_BIN", r"C:/ST/STM32CubeCLT_1.22.0/CMake/bin")
)
NINJA_BIN = Path(
    os.environ.get("STM32TK_NINJA_BIN", r"C:/ST/STM32CubeCLT_1.22.0/Ninja/bin")
)


def require_tool(base: Path, name: str) -> str:
    for candidate in (base / f"{name}.exe", base / name):
        if candidate.is_file():
            return str(candidate)
    resolved = shutil.which(name)
    if resolved:
        return resolved
    raise AssertionError(
        f"required offline ARM GNU tool {name!r} was not found in {base}"
    )


def apply_toolchain_path(monkeypatch) -> tuple[str, str, str]:
    """Verify the installed tools and scope PATH to this test process only."""

    gcc = require_tool(GNU_BIN, "arm-none-eabi-gcc")
    cmake = require_tool(CMAKE_BIN, "cmake")
    ninja = require_tool(NINJA_BIN, "ninja")
    monkeypatch.setenv(
        "PATH",
        os.pathsep.join(
            [str(GNU_BIN), str(CMAKE_BIN), str(NINJA_BIN), os.environ.get("PATH", "")]
        ),
    )
    return gcc, cmake, ninja


# ---------------------------------------------------------------------------
# ELF / MAP evidence
# ---------------------------------------------------------------------------


def pt_load_segments(elf_bytes: bytes) -> tuple[tuple[int, bytes], ...]:
    elf = ELFFile(io.BytesIO(elf_bytes))
    segments: list[tuple[int, bytes]] = []
    for segment in elf.iter_segments():
        if segment.header.p_type != "PT_LOAD" or int(segment.header.p_filesz) == 0:
            continue
        segments.append((int(segment.header.p_paddr), bytes(segment.data())))
    return tuple(segments)


def elf_entry_and_symbols(elf_bytes: bytes) -> tuple[int, dict[str, int]]:
    elf = ELFFile(io.BytesIO(elf_bytes))
    symtab = elf.get_section_by_name(".symtab")
    assert symtab is not None
    symbols = {
        symbol.name: int(symbol["st_value"])
        for symbol in symtab.iter_symbols()
        if symbol.name
    }
    return int(elf.header["e_entry"]), symbols


# ---------------------------------------------------------------------------
# deterministic in-memory simulated programming backend
# ---------------------------------------------------------------------------

SIM_LOG_ENV = "STM32TK_TEST_SIM_PROBE_LOG"
SIM_MODE_ENV = "STM32TK_TEST_SIM_PROBE_MODE"


def _record(log_path: Path, event: str, **fields: object) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"event": event, **fields}, sort_keys=True) + "\n"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


class SimulatedProgramBackend(FakeProbeBackend):
    """Program the received ELF's PT_LOAD payload into simulated memory.

    ``read_memory`` therefore serves the bytes this run actually programmed;
    the backend starts with empty memory and never receives expected bytes.
    """

    def __init__(self, *, log_path: Path, mode: str = "ok") -> None:
        super().__init__(
            probes=(ProbeDescriptor(PROBE_ID, "ST", "ST-Link", None),),
            memory={},
            registers={},
        )
        self._log_path = Path(log_path)
        self._mode = mode

    def open_attach(self, probe_id: str, target: str, *, halt_on_connect: bool = False):
        evidence = super().open_attach(
            probe_id, target, halt_on_connect=halt_on_connect
        )
        _record(self._log_path, "open_attach", probeId=probe_id, target=target)
        return evidence

    def read_memory(self, address: int, length: int) -> bytes:
        data = super().read_memory(address, length)
        _record(
            self._log_path,
            "read_memory",
            address=address,
            length=length,
            bytes=len(data),
        )
        return data

    def flash_elf(self, image: bytes) -> FlashBackendReport:
        _record(self._log_path, "flash_elf", size=len(image))
        segments = pt_load_segments(bytes(image))
        assert segments, "the programmed ELF has no file-backed PT_LOAD segment"
        memory: dict[int, bytes] = {}
        for index, (address, payload) in enumerate(segments):
            if self._mode == "mismatch" and index == 0 and payload:
                payload = bytes([payload[0] ^ 0xFF]) + payload[1:]
            memory[address] = payload
            _record(
                self._log_path,
                "program_segment",
                address=address,
                length=len(payload),
            )
        # Replacing the preloaded map means readback must come from this exact
        # programmed content.
        self._memory = memory
        return FlashBackendReport(
            bytes_programmed=sum(len(entry) for entry in memory.values()),
            sectors_programmed=len(memory),
        )

    def flash_imported_elf(self, image: bytes) -> FlashBackendReport:
        _record(self._log_path, "flash_imported_elf", size=len(image))
        raise ProbeBackendError(
            "PROBE_PROGRAM_FAILED",
            "the imported-firmware route is not used by managed flash",
        )

    def flash_file(self, path: str) -> FlashBackendReport:
        _record(self._log_path, "flash_file", path=path)
        raise ProbeBackendError(
            "PROBE_PROGRAM_FAILED",
            "only the verified ELF programming route is permitted",
        )

    def close(self) -> None:
        _record(self._log_path, "close")
        super().close()


def simulated_backend_factory() -> object:
    """Module-level (picklable) factory used by the real supervisor/service."""

    log_path = os.environ.get(SIM_LOG_ENV)
    if not log_path:
        raise RuntimeError("simulated probe log path is not configured")
    return SimulatedProgramBackend(
        log_path=Path(log_path),
        mode=os.environ.get(SIM_MODE_ENV, "ok"),
    )


def read_probe_log(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    events: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def event_names(events: list[dict[str, object]]) -> list[str]:
    return [str(event.get("event")) for event in events]


# ---------------------------------------------------------------------------
# managed flash through the public workflow with the real service/client path
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FlashOutcome:
    result: object
    events: tuple[dict[str, object], ...]
    receipt_path: Path


def run_managed_flash(
    project_root: Path,
    data_root: Path,
    session_id: str,
    *,
    build_id: str,
    elf_sha256: str,
    authorized: object = True,
) -> FlashOutcome:
    """Call the public flash workflow; only the backend is a test seam."""

    seams = HardwareWorkflowSeams(
        _test_backend_factory=simulated_backend_factory,
    )
    request = FlashWorkflowRequest(
        project_root,
        data_root,
        session_id,
        PROBE_ID,
        build_id,
        elf_sha256,
        authorized,
    )
    result = asyncio.run(flash_workflow(request, _seams=seams))
    log_path = Path(os.environ[SIM_LOG_ENV])
    return FlashOutcome(
        result=result,
        events=tuple(read_probe_log(log_path)),
        receipt_path=project_root
        / "artifacts"
        / "migration"
        / "flash-result.json",
    )


# ---------------------------------------------------------------------------
# reversible relocation of fixture-owned trees
# ---------------------------------------------------------------------------


def relocate_fixture_tree(root: Path, path: Path, target: Path) -> Path:
    assert path.is_dir()
    assert_under(root, path, target)
    assert not target.exists()
    target.parent.mkdir(parents=True, exist_ok=True)
    path.rename(target)
    assert target.is_dir()
    assert not path.exists()
    return target


def copy_output_only(root: Path, output_root: Path, relocated: Path) -> Path:
    """Copy the delivered project without its owned build cache.

    No owned build state is deleted: the original output remains intact, and
    the relocated copy is rebuilt through the normal ``clean`` build workflow.
    """

    assert_under(root, output_root, relocated)
    assert not relocated.exists()
    relocated.parent.mkdir(parents=True, exist_ok=True)
    output_root = output_root.resolve()

    def ignore(directory: str, names: list[str]) -> set[str]:
        current = Path(directory).resolve()
        if current == output_root:
            return {name for name in names if name == "build"}
        return set()

    shutil.copytree(output_root, relocated, ignore=ignore)
    assert not (relocated / "build").exists()
    return relocated
