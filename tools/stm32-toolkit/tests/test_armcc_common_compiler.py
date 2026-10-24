"""Real ARM GNU evidence for the ARMCC-COMMON-SYNTAX rewrites.

The wrappers converted by :mod:`stm32_toolkit.migration.rules` are compiled at
O0/Og/O2 with the coordinator-supplied offline GNU Arm toolchain and
disassembled.  Every supported form must be exactly the reviewed instruction
followed by ``bx lr`` with no compiler prologue or stack access in between.
The composed ``__align`` + fixed-section declaration is compiled, linked at
its reviewed address with a synthetic linker script, and inspected in the
ELF.  This is offline object/ELF evidence only; it says nothing about a board,
the original Keil project, or behavioral equivalence.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from stm32_toolkit.generation import plan_project_configuration
from stm32_toolkit.keil import inspect_keil
from stm32_toolkit.migration import (
    StartupOptions,
    apply_keil_conversion,
    plan_keil_conversion,
    preflight_keil_conversion,
    rules,
)
from stm32_toolkit.project_model import load_project_model

from startup_gcc_fixture import GENERATED_SOURCE, STARTUP_SOURCE, startup_repo
from test_migration_plan import _add_group_scoped_controls, git_init
from test_startup_gcc_compiler import (
    _elf_sections,
    _elf_symbols,
    _entry_point,
    _run,
    _tool,
    _value,
)

CPU_FLAG = "-mcpu=cortex-m4"
NAKED_SOURCE = (
    "__asm void wait_wfi(void)\n"
    "{\n"
    "    WFI\n"
    "    BX LR\n"
    "}\n"
    "\n"
    "__asm void irq_off(void)\n"
    "{\n"
    "    CPSID I\n"
    "    BX LR\n"
    "}\n"
    "\n"
    "__asm void irq_on(void)\n"
    "{\n"
    "    CPSIE I\n"
    "    BX R14\n"
    "}\n"
    "\n"
    "__asm void set_stack(unsigned int top)\n"
    "{\n"
    "    MSR MSP, R0\n"
    "    BX LR\n"
    "}\n"
    "\n"
    "int main(void) { return 0; }\n"
)

EXPECTED = {
    "wait_wfi": "wfi",
    "irq_off": "cpsid i",
    "irq_on": "cpsie i",
    "set_stack": "msr msp, r0",
}


def _converted_source(tmp_path: Path, text: str = NAKED_SOURCE) -> Path:
    scan = rules.scan_sources([("Main/naked.c", text.encode("utf-8"), "c")])[0]
    assert scan.blockers == ()
    path = tmp_path / "naked.c"
    path.write_bytes(scan.after)
    return path


def _disassemble(object_path: Path) -> dict[str, list[str]]:
    # --no-show-raw-insn keeps only the decoded mnemonic/operands, so the
    # expected instruction text can be compared exactly without objdump's
    # leading hex words.
    output = _run(
        [
            _tool("arm-none-eabi-objdump"),
            "-d",
            "--no-show-raw-insn",
            str(object_path),
        ],
        cwd=object_path.parent,
    ).stdout
    functions: dict[str, list[str]] = {}
    current: str | None = None
    for line in output.splitlines():
        match = re.match(r"^[0-9a-f]+ <([^>]+)>:$", line.strip())
        if match is not None:
            current = match.group(1)
            functions[current] = []
            continue
        if current is None or ":" not in line:
            continue
        instruction = line.split(":", 1)[1].strip()
        if not instruction:
            continue
        functions[current].append(" ".join(instruction.split()).lower())
    return functions


@pytest.mark.parametrize("optimization", ["-O0", "-Og", "-O2"])
def test_naked_wrappers_are_instruction_then_bx_lr_without_stack_use(
    tmp_path: Path, optimization: str
) -> None:
    source = _converted_source(tmp_path)
    object_path = tmp_path / f"naked{optimization.replace('-', '_')}.o"
    _run(
        [
            _tool("arm-none-eabi-gcc"),
            CPU_FLAG,
            "-mthumb",
            "-std=gnu11",
            "-ffunction-sections",
            "-fdata-sections",
            optimization,
            "-c",
            str(source),
            "-o",
            str(object_path),
        ],
        cwd=tmp_path,
    )
    functions = _disassemble(object_path)
    for name, expected in EXPECTED.items():
        assert name in functions, f"missing function {name} in {functions}"
        sequence = functions[name]
        assert "bx lr" in sequence, f"{name} has no bx lr: {sequence}"
        before = sequence[: sequence.index("bx lr")]
        assert before == [expected], (
            f"{name} at {optimization} is not exactly {expected!r} then bx lr:"
            f" {sequence}"
        )
        # The exact sequence above already proves there is no compiler
        # prologue; assert the forbidden stack operations explicitly without
        # rejecting the intended ``msr msp, r0`` (whose ``sp`` is part of
        # ``msp``, not a standalone register token).
        for instruction in before:
            assert not re.search(
                r"(?<![A-Za-z0-9_])(push|pop|stmdb|ldmia|str|ldr|sub|add"
                r"|r13|sp)(?![A-Za-z0-9_])",
                instruction,
            ), (
                f"{name} at {optimization} uses a stack operation before"
                f" return: {instruction}"
            )


BOARD_HEADER = (
    "#ifndef BOARD_H\n"
    "#define BOARD_H\n"
    "#define BASE 0x20000000u\n"
    "#define OFFSET 0x100\n"
    "#define SIZE 32\n"
    "#endif\n"
)

COMMON_MAIN = (
    '#include "board.h"\n'
    "#include <stdint.h>\n"
    "\n"
    "#pragma import(__use_no_semihosting)\n"
    "\n"
    "__align(32) unsigned char pool[SIZE] __attribute__((at(BASE + OFFSET)));\n"
    "\n"
    "void SystemInit(void)\n"
    "{\n"
    "}\n"
    "\n"
    "int main(void)\n"
    "{\n"
    "    pool[0] = (unsigned char)(BASE & 0xffu);\n"
    "    return (int)pool[0];\n"
    "}\n"
)


def test_public_flow_links_with_rendered_script_and_explicit_nosys(tmp_path: Path) -> None:
    """Real preflight -> PLAN -> apply -> configure -> GNU link integration.

    The header is reached through a reviewed group-scoped include-only path,
    the C source uses the composed alignment/placement and the supported
    no-semihosting pragma, and the generated manifest supplies
    ``newlibSpecs=["nosys.specs"]``.  The link uses the actual rendered linker
    script and report, not a hand-written address.
    """
    repo = startup_repo(
        tmp_path,
        name="common-compiler",
        extra_groups=(("Board", (("board.h", "5", "Inc/board.h"),)),),
        extra_files={"Main/main.c": COMMON_MAIN, "Inc/board.h": BOARD_HEADER},
    )
    _add_group_scoped_controls(repo, "Main", include_paths="Inc")
    git_init(repo)

    inspection = inspect_keil(repo)
    startup = StartupOptions("generate-cmsis-gcc", STARTUP_SOURCE)
    preflight = preflight_keil_conversion(
        repo, inspection, startup_options=startup
    )
    assert preflight["analysis"]["blockers"] == []
    changes = {change["path"]: change for change in preflight["analysis"]["sourceChanges"]}
    assert "ARMCC_NO_SEMIHOSTING_PRAGMA" in changes["Main/main.c"]["ruleIds"]
    assert "ARMCC_ALIGN_ATTRIBUTE" in changes["Main/main.c"]["ruleIds"]
    assert "ARMCC_ABSOLUTE_PLACEMENT" in changes["Main/main.c"]["ruleIds"]

    plan = plan_keil_conversion(repo, inspection, startup_options=startup)
    assert plan.blockers == ()
    applied = apply_keil_conversion(plan)
    assert applied.ok is True, applied.to_dict()
    assert (repo / GENERATED_SOURCE).is_file()

    model = load_project_model(repo)
    assert model.build.newlib_specs == ("nosys.specs",)
    assert "Inc" in model.build.include_paths
    configuration = plan_project_configuration(model)
    assert configuration.blockers == ()
    cmake = next(
        entry for entry in configuration.files if entry.path == "CMakeLists.txt"
    ).after_bytes.decode("utf-8")
    assert cmake.count('"--specs=nosys.specs"') == 1
    assert '"--specs=nano.specs"' not in cmake
    linker_bytes = next(
        entry for entry in configuration.files if entry.path == "linker/stm32tk.ld"
    ).after_bytes
    assert b".stm32tk.abs.20000100" in linker_bytes

    build = tmp_path / "build-common"
    build.mkdir()
    linker = build / "stm32tk.ld"
    linker.write_bytes(linker_bytes)
    common = [CPU_FLAG, "-mthumb", "-ffunction-sections", "-fdata-sections", "-Og", "-g3"]
    objects = []
    for source, name in (
        (repo / GENERATED_SOURCE, "startup.o"),
        (repo / "Main" / "main.c", "main.o"),
    ):
        object_path = build / name
        _run(
            [
                _tool("arm-none-eabi-gcc"),
                *common,
                *[
                    "-I" + str(repo.joinpath(*include.split("/")))
                    for include in model.build.include_paths
                ],
                "-c",
                str(source),
                "-o",
                str(object_path),
            ],
            cwd=build,
        )
        objects.append(object_path)

    elf_path = build / "firmware.elf"
    _run(
        [
            _tool("arm-none-eabi-gcc"),
            CPU_FLAG,
            "-mthumb",
            "--specs=nosys.specs",
            "-nostartfiles",
            "-T",
            str(linker),
            f"-Wl,-Map={build / 'firmware.map'}",
            "-Wl,--gc-sections",
            *[str(obj) for obj in objects],
            "-o",
            str(elf_path),
        ],
        cwd=build,
    )

    sections = _elf_sections(elf_path)
    fixed = sections[".stm32tk.abs.20000100"]
    assert fixed["address"] == 0x20000100
    assert fixed["size"] == 32
    assert fixed["alignment"] >= 32
    symbols = _elf_symbols(elf_path)
    assert _value(symbols, "pool") == 0x20000100
    assert _value(symbols, "main")
    reset = _value(symbols, "Reset_Handler")
    assert reset != 0
    assert _entry_point(elf_path) & ~1 == reset & ~1
