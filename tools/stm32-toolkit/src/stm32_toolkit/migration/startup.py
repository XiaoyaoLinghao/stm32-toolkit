"""Bounded, read-only ARMCC CMSIS startup recognition and GCC generation.

The recognizer validates the *whole* active ARMASM file against the
conventional ST/CMSIS Cortex-M pattern.  It never executes input, never
evaluates arbitrary expressions, and never reads beyond the frozen byte limit.
Unsupported grammar produces portable path/line diagnostics instead of a
guessed translation.  The generator emits a deterministic GNU ``.S`` file;
the original ARMCC startup is never modified.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from stm32_toolkit.keil import KeilInspection
from stm32_toolkit.migration.model import (
    MigrationPlanError,
    StartupAnalysis,
    StartupDiagnostic,
    StartupHandler,
    StartupOptions,
    StartupVectorEntry,
    portable_path_error,
)

STARTUP_STRATEGY = "generate-cmsis-gcc"
STARTUP_GENERATED_PATH = "Startup/stm32tk_startup_gcc.S"
STARTUP_FILE_LIMIT_BYTES = 1024 * 1024
STARTUP_VECTOR_LIMIT = 1024
STARTUP_ALIGNMENT = 8
SUPPORTED_STARTUP_CORES = ("cortex-m3", "cortex-m4", "cortex-m7")
RUNTIME_INITIALIZATION = "cmsis-gcc-v1"

RESET_PATTERN = (
    "SystemInit->data-copy->bss-zero->__libc_init_array->main->infinite-loop"
)
_STARTUP_WARNINGS = (
    "MIGRATION_STARTUP_RUNTIME_REVIEW_REQUIRED: generated GCC runtime initialization replaces ARMCC/Microlib startup semantics and requires review",
    "MIGRATION_STARTUP_VALUES_FROM_SOURCE: stack and heap byte counts are preserved from the original startup source",
    "MIGRATION_STARTUP_ORIGINAL_PRESERVED: the original ARMCC startup source is never modified or deleted",
)

_MAX_EVIDENCE = 200
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_NUMBER_RE = re.compile(r"^(0[xX][0-9a-fA-F]+|\d+)$")
_CORE_SPLIT_RE = re.compile(r"[\s_]+")
_CONTINUATION_RE = re.compile(r"\\[ \t]*$")

# Logical statement patterns.  Directives and mnemonics are case-insensitive;
# symbol names preserve their original spelling.
_EQU_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s+EQU\s+(.+)$", re.IGNORECASE)
_PROC_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s+PROC$", re.IGNORECASE)
_ENDP_RE = re.compile(r"^ENDP$", re.IGNORECASE)
_SPACE_RE = re.compile(
    r"^([A-Za-z_][A-Za-z0-9_]*)\s+SPACE\s+([A-Za-z_][A-Za-z0-9_]*)$",
    re.IGNORECASE,
)
_LABEL_DCD_RE = re.compile(
    r"^([A-Za-z_][A-Za-z0-9_]*)\s+DCD\s+(.+)$", re.IGNORECASE
)
_DCD_RE = re.compile(r"^DCD\s+(.+)$", re.IGNORECASE)
_EXPORT_RE = re.compile(
    r"^EXPORT\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s+\[\s*WEAK\s*\])?$",
    re.IGNORECASE,
)
_IMPORT_RE = re.compile(r"^IMPORT\s+([A-Za-z_][A-Za-z0-9_]*)$", re.IGNORECASE)
_AREA_RE = re.compile(r"^AREA\s+(.+)$", re.IGNORECASE)
_PRESERVE8_RE = re.compile(r"^PRESERVE8$", re.IGNORECASE)
_THUMB_RE = re.compile(r"^THUMB$", re.IGNORECASE)
_ALIGN_RE = re.compile(r"^ALIGN$", re.IGNORECASE)
_END_RE = re.compile(r"^END$", re.IGNORECASE)
_B_DOT_RE = re.compile(r"^B\s+\.$", re.IGNORECASE)
_BLX_R0_RE = re.compile(r"^BLX\s+R0$", re.IGNORECASE)
_BX_R0_RE = re.compile(r"^BX\s+R0$", re.IGNORECASE)
_BX_LR_RE = re.compile(r"^BX\s+LR$", re.IGNORECASE)
_LDR_RE = re.compile(r"^LDR\s+R([0-3])\s*,\s*=\s*(.+)$", re.IGNORECASE)
_IF_MICROLIB_RE = re.compile(r"^IF\s+:DEF:__MICROLIB$", re.IGNORECASE)
_IF_ANY_RE = re.compile(r"^IF\b", re.IGNORECASE)
_ELSE_RE = re.compile(r"^ELSE$", re.IGNORECASE)
_ENDIF_RE = re.compile(r"^ENDIF$", re.IGNORECASE)

_INDIVIDUAL_HANDLER_BODY = (
    "export",
    "b-dot",
    "endp",
)
_RESET_BODY = (
    "export-reset",
    "import-systeminit",
    "import-main",
    "ldr-systeminit",
    "blx-r0",
    "ldr-main",
    "bx-r0",
    "endp",
)
_MICROLIB_IF_EXPORTS = ("__initial_sp", "__heap_base", "__heap_limit")


def _raise(code: str, message: str, details: dict[str, object]) -> MigrationPlanError:
    return MigrationPlanError(code, message, details)


def normalize_startup_core(raw: object) -> str | None:
    """Return the supported normalized core name, or ``None``."""
    if not isinstance(raw, str):
        return None
    value = _CORE_SPLIT_RE.sub("-", raw.strip().lower())
    while "--" in value:
        value = value.replace("--", "-")
    return value if value in SUPPORTED_STARTUP_CORES else None


def normalize_startup_options(
    strategy: object, source: object
) -> StartupOptions | None:
    """Validate the public startup options without touching the filesystem."""
    if strategy is None:
        if source is not None:
            raise _raise(
                "MIGRATION_STARTUP_OPTIONS_INVALID",
                "startupSource requires startupStrategy",
                {"field": "startupSource", "rule": "requiresStrategy"},
            )
        return None
    if type(strategy) is not str or strategy != STARTUP_STRATEGY:
        raise _raise(
            "MIGRATION_STARTUP_STRATEGY_UNSUPPORTED",
            "startupStrategy is not supported",
            {"field": "startupStrategy", "rule": "unsupported"},
        )
    if source is not None:
        if not isinstance(source, str):
            raise _raise(
                "MIGRATION_STARTUP_OPTIONS_INVALID",
                "startupSource must be a project-relative path",
                {"field": "startupSource", "rule": "type"},
            )
        reason = portable_path_error(source)
        if reason is None and "\\" in source:
            reason = "portablePath"
        if reason is not None:
            raise _raise(
                "MIGRATION_STARTUP_OPTIONS_INVALID",
                "startupSource is not a portable project-relative path",
                {"field": "startupSource", "rule": reason},
            )
    return StartupOptions(STARTUP_STRATEGY, source)


# ---------------------------------------------------------------------------
# physical/logical line handling
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _LogicalLine:
    text: str
    line: int
    unfinished: bool

    @property
    def column(self) -> int:
        return len(self.text) - len(self.text.lstrip()) + 1


def _logical_lines(text: str) -> tuple[_LogicalLine, ...]:
    physical = text.splitlines()
    result: list[_LogicalLine] = []
    index = 0
    while index < len(physical):
        start_line = index + 1
        parts: list[str] = []
        unfinished = False
        while True:
            current = physical[index]
            without_trailing = current.rstrip()
            if _CONTINUATION_RE.search(without_trailing):
                parts.append(without_trailing[: without_trailing.rfind("\\")])
                index += 1
                if index >= len(physical):
                    unfinished = True
                    break
                continue
            parts.append(current)
            index += 1
            break
        result.append(_LogicalLine("".join(parts), start_line, unfinished))
    return tuple(result)


def _strip_comment(text: str) -> str:
    position = text.find(";")
    return text if position < 0 else text[:position]


def _cap(text: str) -> str:
    return text.strip()[:_MAX_EVIDENCE]


# ---------------------------------------------------------------------------
# parsed evidence
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ParsedStartup:
    core: str | None
    stack_size: int | None
    heap_size: int | None
    vectors: tuple[StartupVectorEntry, ...]
    handlers: tuple[StartupHandler, ...]
    diagnostics: tuple[StartupDiagnostic, ...]

    @property
    def status(self) -> str:
        return "ready" if not self.diagnostics else "unsupported"

    @property
    def reserved_count(self) -> int:
        return sum(1 for entry in self.vectors if entry.reserved)


@dataclass(frozen=True)
class StartupOutcome:
    """Analysis plus the exact generated bytes and destination state."""

    analysis: StartupAnalysis
    generated_bytes: bytes | None
    selected_source: str
    destination_state: str  # missing, identical, or collision
    destination_bytes: bytes | None = None

    @property
    def ready(self) -> bool:
        return self.analysis.status == "ready" and self.generated_bytes is not None


class _Parser:
    def __init__(self, path: str, lines: tuple[_LogicalLine, ...], core: str | None) -> None:
        self.path = path
        self.lines = lines
        self.core = core
        self.diagnostics: list[StartupDiagnostic] = []

        self.equ_values: dict[str, tuple[int | None, str, int]] = {}
        self.labels: dict[str, int] = {}
        self.exports: dict[str, tuple[bool, int]] = {}  # weak flag, line
        self.imports: dict[str, int] = {}

        self.area: str | None = None
        self.areas_seen: set[str] = set()
        self.stack_area_line: int | None = None
        self.heap_area_line: int | None = None
        self.reset_area_line: int | None = None
        self.text_area_line: int | None = None

        self.stack_stage = 0  # 0=SPACE, 1=__initial_sp, 2=done
        self.heap_stage = 0  # 0=__heap_base, 1=SPACE, 2=__heap_limit, 3=done
        self.preserve8 = False
        self.thumb = False

        self.vector_label_line: int | None = None
        self.vector_end_line: int | None = None
        self.vectors: list[StartupVectorEntry] = []
        self.in_vectors = False
        self.vector_area_used = False

        self.proc: str | None = None
        self.proc_kind: str | None = None
        self.proc_stage = 0
        self.proc_start_line = 0
        self.reset_body: list[str] = []
        self.individual_handlers: dict[str, int] = {}
        self.default_handler_line: int | None = None
        self.alias_handlers: dict[str, int] = {}
        self.default_exports: list[tuple[str, int]] = []
        self.default_labels: list[tuple[str, int]] = []
        self.default_body_stage = 0  # 0=exports/labels, 1=after B ., 2=after ENDP

        self.align_seen = False
        self.microlib_state = "outside"  # outside, if, else, done
        self.microlib_if_exports: list[str] = []
        self.microlib_else_stage = 0
        self.microlib_ldr_index = 0
        self.ended = False

    # -- diagnostics --------------------------------------------------------

    def _diag(
        self,
        code: str,
        line: _LogicalLine,
        message: str,
        column: int | None = None,
    ) -> None:
        self.diagnostics.append(
            StartupDiagnostic(
                code=code,
                path=self.path,
                line=line.line,
                column=line.column if column is None else column,
                evidence=_cap(_strip_comment(line.text)),
                message=message,
            )
        )

    def _syntax(self, line: _LogicalLine) -> None:
        self._diag(
            "MIGRATION_STARTUP_GRAMMAR_UNSUPPORTED",
            line,
            "unsupported ARMCC startup statement; only the conventional CMSIS Cortex-M pattern is recognized",
        )

    # -- symbol bookkeeping -------------------------------------------------

    def _define_label(self, name: str, line: _LogicalLine) -> None:
        if name in self.labels:
            self._diag(
                "MIGRATION_STARTUP_DUPLICATE_LABEL",
                line,
                f"duplicate startup label {name}",
            )
            return
        self.labels[name] = line.line

    def _define_equ(self, name: str, value: str, line: _LogicalLine) -> None:
        if name in self.equ_values:
            self._diag(
                "MIGRATION_STARTUP_DUPLICATE_LABEL",
                line,
                f"duplicate startup EQU symbol {name}",
            )
            return
        if name in ("Stack_Size", "Heap_Size"):
            number = _NUMBER_RE.fullmatch(value.strip())
            if number is None:
                self._diag(
                    "MIGRATION_STARTUP_SIZE_INVALID",
                    line,
                    f"{name} must be an exact unsigned integer byte count",
                )
                self.equ_values[name] = (None, value, line.line)
                return
            parsed = int(value.strip(), 0)
            self.equ_values[name] = (parsed, value, line.line)
            return
        normalized = re.sub(r"\s+", "", value)
        if name == "__Vectors_Size" and normalized == "__Vectors_End-__Vectors":
            self.equ_values[name] = (None, value, line.line)
            return
        self._diag(
            "MIGRATION_STARTUP_EQU_UNSUPPORTED",
            line,
            "unsupported startup expression; only numeric sizes and __Vectors_End - __Vectors are recognized",
        )

    def _define_export(self, name: str, weak: bool, line: _LogicalLine) -> None:
        if name in self.exports:
            self._diag(
                "MIGRATION_STARTUP_DUPLICATE_EXPORT",
                line,
                f"duplicate or conflicting startup export {name}",
            )
            return
        self.exports[name] = (weak, line.line)
        if self.default_handler_line is not None and self.proc == "Default_Handler":
            self.default_exports.append((name, line.line))

    def _define_import(self, name: str, line: _LogicalLine) -> None:
        if name in self.imports:
            self._diag(
                "MIGRATION_STARTUP_DUPLICATE_IMPORT",
                line,
                f"duplicate startup import {name}",
            )
            return
        self.imports[name] = line.line

    # -- main loop ----------------------------------------------------------

    def run(self) -> _ParsedStartup:
        for logical in self.lines:
            if logical.unfinished:
                self._diag(
                    "MIGRATION_STARTUP_GRAMMAR_UNSUPPORTED",
                    logical,
                    "unterminated line continuation at end of file",
                )
                continue
            text = _strip_comment(logical.text).strip()
            if not text:
                continue
            if self.ended:
                self._diag(
                    "MIGRATION_STARTUP_GRAMMAR_UNSUPPORTED",
                    logical,
                    "active statement follows END",
                )
                continue
            self._statement(text, logical)

        self._finalize()
        return _ParsedStartup(
            core=self.core,
            stack_size=self._size_value("Stack_Size"),
            heap_size=self._size_value("Heap_Size"),
            vectors=tuple(self.vectors),
            handlers=self._handlers(),
            diagnostics=tuple(
                sorted(
                    self.diagnostics,
                    key=lambda item: (item.line, item.column, item.code),
                )
            ),
        )

    def _size_value(self, name: str) -> int | None:
        entry = self.equ_values.get(name)
        return entry[0] if entry is not None else None

    def _statement(self, text: str, line: _LogicalLine) -> None:
        if self.microlib_state in ("if", "else"):
            self._microlib_statement(text, line)
            return
        if self.proc is not None:
            # Every active statement inside a handler PROC is validated by the
            # exact-body recognizer, so custom instructions cannot slip
            # through a generic directive branch.
            self._proc_statement(text, line)
            return

        if _IF_ANY_RE.match(text):
            if _IF_MICROLIB_RE.match(text):
                if self.microlib_state != "outside":
                    self._diag(
                        "MIGRATION_STARTUP_CONDITIONAL_UNSUPPORTED",
                        line,
                        "nested startup conditional is not supported",
                    )
                    return
                self.microlib_state = "if"
                self.microlib_else_stage = 0
                return
            self._diag(
                "MIGRATION_STARTUP_CONDITIONAL_UNSUPPORTED",
                line,
                "only IF :DEF:__MICROLIB is recognized",
            )
            return
        if _ELSE_RE.match(text) or _ENDIF_RE.match(text):
            self._diag(
                "MIGRATION_STARTUP_CONDITIONAL_UNSUPPORTED",
                line,
                "conditional branch is outside the recognized Microlib block",
            )
            return

        if _PRESERVE8_RE.match(text):
            self.preserve8 = True
            return
        if _THUMB_RE.match(text):
            self.thumb = True
            return
        if _ALIGN_RE.match(text):
            self.align_seen = True
            return
        if _END_RE.match(text):
            self.ended = True
            return

        area_match = _AREA_RE.match(text)
        if area_match is not None:
            self._area(area_match.group(1), line)
            return

        equ_match = _EQU_RE.match(text)
        if equ_match is not None:
            self._define_equ(equ_match.group(1), equ_match.group(2), line)
            return

        if _ENDP_RE.match(text):
            self._endp(line)
            return

        proc_match = _PROC_RE.match(text)
        if proc_match is not None:
            self._begin_proc(proc_match.group(1), line)
            return

        space_match = _SPACE_RE.match(text)
        if space_match is not None:
            self._space(space_match.group(1), space_match.group(2), line)
            return

        export_match = _EXPORT_RE.match(text)
        if export_match is not None:
            self._export_statement(export_match.group(1), "[WEAK]" in text.upper(), line)
            return

        import_match = _IMPORT_RE.match(text)
        if import_match is not None:
            self._import_statement(import_match.group(1), line)
            return

        label_dcd = _LABEL_DCD_RE.match(text)
        if label_dcd is not None:
            self._vector_label(label_dcd.group(1), line)
            self._vector_dcd(label_dcd.group(2), line)
            return

        dcd_match = _DCD_RE.match(text)
        if dcd_match is not None:
            self._vector_dcd(dcd_match.group(1), line)
            return

        if _IDENT_RE.fullmatch(text):
            self._bare_label(text, line)
            return

        self._syntax(line)

    # -- areas --------------------------------------------------------------

    def _area(self, raw: str, line: _LogicalLine) -> None:
        parts = [part.strip() for part in raw.split(",")]
        name = parts[0]
        attributes = {part.upper() for part in parts[1:] if part}
        expected: dict[str, set[str]] = {
            "STACK": {"NOINIT", "READWRITE", "ALIGN=3"},
            "HEAP": {"NOINIT", "READWRITE", "ALIGN=3"},
            "RESET": {"DATA", "READONLY"},
            "|.text|": {"CODE", "READONLY"},
        }
        selected = name.upper() if name.upper() in ("STACK", "HEAP", "RESET") else name
        if selected not in expected or attributes != expected[selected]:
            self._diag(
                "MIGRATION_STARTUP_AREA_UNSUPPORTED",
                line,
                "unsupported startup AREA or attributes",
            )
            return
        if selected in self.areas_seen:
            self._diag(
                "MIGRATION_STARTUP_AREA_UNSUPPORTED",
                line,
                f"duplicate startup AREA {name}",
            )
            return
        self.areas_seen.add(selected)
        self.area = selected
        if selected == "STACK":
            self.stack_area_line = line.line
            self.stack_stage = 0
        elif selected == "HEAP":
            self.heap_area_line = line.line
            self.heap_stage = 0
        elif selected == "RESET":
            self.reset_area_line = line.line
        else:
            self.text_area_line = line.line
        if selected in ("STACK", "HEAP") and "ALIGN=3" not in attributes:
            self._diag(
                "MIGRATION_STARTUP_STACK_LAYOUT_UNSUPPORTED",
                line,
                "STACK and HEAP areas must be 8-byte aligned (ALIGN=3)",
            )

    def _space(self, label: str, symbol: str, line: _LogicalLine) -> None:
        if self.area == "STACK":
            if self.stack_stage != 0 or label != "Stack_Mem" or symbol != "Stack_Size":
                self._diag(
                    "MIGRATION_STARTUP_STACK_LAYOUT_UNSUPPORTED",
                    line,
                    "unexpected STACK reservation; expected Stack_Mem SPACE Stack_Size",
                )
                return
            self._define_label(label, line)
            self.stack_stage = 1
            return
        if self.area == "HEAP":
            if self.heap_stage != 1 or label != "Heap_Mem" or symbol != "Heap_Size":
                self._diag(
                    "MIGRATION_STARTUP_STACK_LAYOUT_UNSUPPORTED",
                    line,
                    "unexpected HEAP reservation; expected Heap_Mem SPACE Heap_Size",
                )
                return
            self._define_label(label, line)
            self.heap_stage = 2
            return
        self._diag(
            "MIGRATION_STARTUP_STACK_LAYOUT_UNSUPPORTED",
            line,
            "SPACE is only recognized for the conventional STACK and HEAP areas",
        )

    # -- exports and imports ------------------------------------------------

    def _export_statement(self, name: str, weak: bool, line: _LogicalLine) -> None:
        if self.area == "RESET" and name in (
            "__Vectors",
            "__Vectors_End",
            "__Vectors_Size",
        ):
            self._define_export(name, weak, line)
            return
        if self.area == "|.text|" and self.proc is not None:
            self._define_export(name, weak, line)
            return
        self._diag(
            "MIGRATION_STARTUP_GRAMMAR_UNSUPPORTED",
            line,
            "EXPORT is not recognized in this startup context",
        )

    def _import_statement(self, name: str, line: _LogicalLine) -> None:
        if self.area == "|.text|" and self.proc == "Reset_Handler" and name in (
            "SystemInit",
            "__main",
        ):
            self._define_import(name, line)
            return
        self._diag(
            "MIGRATION_STARTUP_GRAMMAR_UNSUPPORTED",
            line,
            "IMPORT is not recognized in this startup context",
        )

    # -- vector table -------------------------------------------------------

    def _vector_label(self, name: str, line: _LogicalLine) -> None:
        if self.area != "RESET":
            self._diag(
                "MIGRATION_STARTUP_VECTOR_UNSUPPORTED",
                line,
                "vector labels and DCD entries must be inside AREA RESET",
            )
            return
        if name == "__Vectors":
            if self.vector_label_line is not None or self.in_vectors:
                self._diag(
                    "MIGRATION_STARTUP_VECTOR_UNSUPPORTED",
                    line,
                    "multiple vector tables are not supported",
                )
                return
            self.vector_label_line = line.line
            self.in_vectors = True
            self.vector_area_used = True
            self._define_label(name, line)
            return
        self._diag(
            "MIGRATION_STARTUP_VECTOR_UNSUPPORTED",
            line,
            "unexpected label in AREA RESET",
        )

    def _vector_dcd(self, raw: str, line: _LogicalLine) -> None:
        if self.area != "RESET" or not self.in_vectors:
            self._diag(
                "MIGRATION_STARTUP_VECTOR_UNSUPPORTED",
                line,
                "DCD entries must follow the single __Vectors label in AREA RESET",
            )
            return
        if len(self.vectors) >= STARTUP_VECTOR_LIMIT:
            self._diag(
                "MIGRATION_STARTUP_VECTOR_LIMIT_EXCEEDED",
                line,
                "startup vector table exceeds the supported entry limit",
            )
            return
        value = raw.strip()
        index = len(self.vectors)
        if value == "0":
            self.vectors.append(StartupVectorEntry(index, None, True, line.line))
            return
        if _IDENT_RE.fullmatch(value) is None:
            self._diag(
                "MIGRATION_STARTUP_VECTOR_UNSUPPORTED",
                line,
                "vector entry must be a handler symbol or the reserved value 0; expressions are not supported",
            )
            return
        self.vectors.append(StartupVectorEntry(index, value, False, line.line))

    def _bare_label(self, name: str, line: _LogicalLine) -> None:
        if self.area == "STACK":
            if self.stack_stage != 1 or name != "__initial_sp":
                self._diag(
                    "MIGRATION_STARTUP_STACK_LAYOUT_UNSUPPORTED",
                    line,
                    "unexpected STACK label; expected __initial_sp after Stack_Mem",
                )
                return
            self._define_label(name, line)
            self.stack_stage = 2
            return
        if self.area == "HEAP":
            if self.heap_stage == 0 and name == "__heap_base":
                self._define_label(name, line)
                self.heap_stage = 1
                return
            if self.heap_stage == 2 and name == "__heap_limit":
                self._define_label(name, line)
                self.heap_stage = 3
                return
            self._diag(
                "MIGRATION_STARTUP_STACK_LAYOUT_UNSUPPORTED",
                line,
                "unexpected HEAP label; expected __heap_base and __heap_limit around Heap_Mem",
            )
            return
        if self.area == "RESET" and name == "__Vectors_End" and self.in_vectors:
            if self.vector_end_line is not None:
                self._diag(
                    "MIGRATION_STARTUP_VECTOR_UNSUPPORTED",
                    line,
                    "duplicate __Vectors_End label",
                )
                return
            self.vector_end_line = line.line
            self.in_vectors = False
            self._define_label(name, line)
            return
        if self.microlib_state == "else" and name == "__user_initial_stackheap":
            if self.microlib_else_stage != 1:
                self._diag(
                    "MIGRATION_STARTUP_GRAMMAR_UNSUPPORTED",
                    line,
                    "unexpected __user_initial_stackheap placement",
                )
                return
            self._define_label(name, line)
            self.microlib_else_stage = 2
            return
        self._diag(
            "MIGRATION_STARTUP_GRAMMAR_UNSUPPORTED",
            line,
            "unexpected bare label in the recognized startup grammar",
        )

    # -- PROC blocks --------------------------------------------------------

    def _begin_proc(self, name: str, line: _LogicalLine) -> None:
        if self.proc is not None:
            self._diag(
                "MIGRATION_STARTUP_GRAMMAR_UNSUPPORTED",
                line,
                "nested PROC is not supported",
            )
            return
        if self.area != "|.text|":
            self._diag(
                "MIGRATION_STARTUP_GRAMMAR_UNSUPPORTED",
                line,
                "handler PROC must be inside AREA |.text|",
            )
            return
        self._define_label(name, line)
        self.proc = name
        self.proc_start_line = line.line
        self.proc_stage = 0
        if name == "Reset_Handler":
            self.proc_kind = "reset"
            self.reset_body = []
        elif name == "Default_Handler":
            self.proc_kind = "default"
            self.default_handler_line = line.line
            self.default_body_stage = 0
        else:
            self.proc_kind = "individual"
            self.individual_handlers[name] = line.line

    def _proc_statement(self, text: str, line: _LogicalLine) -> None:
        if self.proc_kind == "reset":
            self._reset_statement(text, line)
            return
        if self.proc_kind == "individual":
            self._individual_statement(text, line)
            return
        self._default_statement(text, line)

    def _reset_statement(self, text: str, line: _LogicalLine) -> None:
        expected = _RESET_BODY[self.proc_stage] if self.proc_stage < len(_RESET_BODY) else None
        actual: str | None = None
        if _EXPORT_RE.match(text):
            match = _EXPORT_RE.match(text)
            assert match is not None
            if match.group(1) == "Reset_Handler" and "[WEAK]" in text.upper():
                actual = "export-reset"
                self._define_export("Reset_Handler", True, line)
        elif _IMPORT_RE.match(text):
            match = _IMPORT_RE.match(text)
            assert match is not None
            if match.group(1) == "SystemInit":
                actual = "import-systeminit"
                self._define_import("SystemInit", line)
            elif match.group(1) == "__main":
                actual = "import-main"
                self._define_import("__main", line)
        elif _LDR_RE.match(text):
            match = _LDR_RE.match(text)
            assert match is not None
            register, expression = match.group(1), re.sub(r"\s+", "", match.group(2))
            if register == "0" and expression == "SystemInit":
                actual = "ldr-systeminit"
            elif register == "0" and expression == "__main":
                actual = "ldr-main"
        elif _BLX_R0_RE.match(text):
            actual = "blx-r0"
        elif _BX_R0_RE.match(text):
            actual = "bx-r0"
        elif _ENDP_RE.match(text):
            actual = "endp"
        if expected is None or actual != expected:
            self._diag(
                "MIGRATION_STARTUP_RESET_UNSUPPORTED",
                line,
                "Reset_Handler body must be exactly EXPORT [WEAK], IMPORT SystemInit/__main, LDR/BLX SystemInit, LDR/BX __main, ENDP",
            )
            if actual == "endp":
                self._finish_proc(line)
            return
        self.reset_body.append(actual)
        self.proc_stage += 1
        if actual == "endp":
            self._finish_proc(line)

    def _individual_statement(self, text: str, line: _LogicalLine) -> None:
        expected = (
            _INDIVIDUAL_HANDLER_BODY[self.proc_stage]
            if self.proc_stage < len(_INDIVIDUAL_HANDLER_BODY)
            else None
        )
        actual: str | None = None
        if _EXPORT_RE.match(text):
            match = _EXPORT_RE.match(text)
            assert match is not None
            if match.group(1) == self.proc and "[WEAK]" in text.upper():
                actual = "export"
                self._define_export(self.proc or "", True, line)
        elif _B_DOT_RE.match(text):
            actual = "b-dot"
        elif _ENDP_RE.match(text):
            actual = "endp"
        if expected is None or actual != expected:
            self._diag(
                "MIGRATION_STARTUP_CUSTOM_HANDLER_UNSUPPORTED",
                line,
                "weak core handlers must contain only EXPORT [WEAK], an infinite-loop branch, and ENDP",
            )
            if actual == "endp":
                self._finish_proc(line)
            return
        self.proc_stage += 1
        if actual == "endp":
            self._finish_proc(line)

    def _default_statement(self, text: str, line: _LogicalLine) -> None:
        if self.default_body_stage == 0:
            export_match = _EXPORT_RE.match(text)
            if export_match is not None:
                if "[WEAK]" not in text.upper():
                    self._diag(
                        "MIGRATION_STARTUP_HANDLER_EXPORT_UNSUPPORTED",
                        line,
                        "Default_Handler aliases must be exported as weak",
                    )
                    return
                self._define_export(export_match.group(1), True, line)
                return
            if _IDENT_RE.fullmatch(text):
                # A bare label inside Default_Handler aliases the same loop.
                self._define_label(text, line)
                self.alias_handlers[text] = line.line
                return
            if _B_DOT_RE.match(text):
                self.default_body_stage = 1
                return
            self._diag(
                "MIGRATION_STARTUP_CUSTOM_HANDLER_UNSUPPORTED",
                line,
                "Default_Handler may contain only weak EXPORT aliases, bare alias labels, and one infinite-loop branch",
            )
            return
        if self.default_body_stage == 1:
            if _ENDP_RE.match(text):
                self.default_body_stage = 2
                self._finish_proc(line)
                return
            self._diag(
                "MIGRATION_STARTUP_CUSTOM_HANDLER_UNSUPPORTED",
                line,
                "Default_Handler may not contain code after its infinite-loop branch",
            )
            return
        self._diag(
            "MIGRATION_STARTUP_CUSTOM_HANDLER_UNSUPPORTED",
            line,
            "statement follows ENDP in Default_Handler",
        )

    def _finish_proc(self, line: _LogicalLine) -> None:
        if self.proc_kind == "reset":
            if tuple(self.reset_body) != _RESET_BODY:
                self._diag(
                    "MIGRATION_STARTUP_RESET_UNSUPPORTED",
                    line,
                    "Reset_Handler does not match the supported SystemInit -> __main sequence",
                )
        self.proc = None
        self.proc_kind = None
        self.proc_stage = 0

    def _endp(self, line: _LogicalLine) -> None:
        self._diag(
            "MIGRATION_STARTUP_GRAMMAR_UNSUPPORTED",
            line,
            "ENDP without an open PROC",
        )

    # -- Microlib block -----------------------------------------------------

    def _microlib_statement(self, text: str, line: _LogicalLine) -> None:
        if self.microlib_state == "if":
            if _ELSE_RE.match(text):
                if tuple(self.microlib_if_exports) != _MICROLIB_IF_EXPORTS:
                    self._diag(
                        "MIGRATION_STARTUP_MICROLIB_UNSUPPORTED",
                        line,
                        "Microlib branch must export __initial_sp, __heap_base and __heap_limit",
                    )
                self.microlib_state = "else"
                self.microlib_else_stage = 0
                return
            if _ENDIF_RE.match(text):
                self._diag(
                    "MIGRATION_STARTUP_MICROLIB_UNSUPPORTED",
                    line,
                    "Microlib conditional is missing its ELSE branch",
                )
                self.microlib_state = "done"
                return
            export_match = _EXPORT_RE.match(text)
            if export_match is not None and export_match.group(1) in _MICROLIB_IF_EXPORTS:
                name = export_match.group(1)
                if name in self.microlib_if_exports:
                    self._diag(
                        "MIGRATION_STARTUP_DUPLICATE_EXPORT",
                        line,
                        f"duplicate startup export {name}",
                    )
                else:
                    self.microlib_if_exports.append(name)
                self._define_export(name, "[WEAK]" in text.upper(), line)
                return
            self._diag(
                "MIGRATION_STARTUP_MICROLIB_UNSUPPORTED",
                line,
                "unsupported statement in the IF :DEF:__MICROLIB branch",
            )
            return

        if _ENDIF_RE.match(text):
            if self.microlib_else_stage < 5:
                self._diag(
                    "MIGRATION_STARTUP_MICROLIB_UNSUPPORTED",
                    line,
                    "__user_initial_stackheap branch is incomplete",
                )
            self.microlib_state = "done"
            return
        if _ELSE_RE.match(text):
            self._diag(
                "MIGRATION_STARTUP_CONDITIONAL_UNSUPPORTED",
                line,
                "nested ELSE is not supported",
            )
            return
        stage = self.microlib_else_stage
        if stage == 0:
            import_match = _IMPORT_RE.match(text)
            if import_match is not None and import_match.group(1) == "__use_two_region_memory":
                self._define_import("__use_two_region_memory", line)
                self.microlib_else_stage = 1
                return
        elif stage == 1:
            export_match = _EXPORT_RE.match(text)
            if export_match is not None and export_match.group(1) == "__user_initial_stackheap":
                self._define_export("__user_initial_stackheap", False, line)
                self.microlib_else_stage = 2
                return
        elif stage == 2:
            if _IDENT_RE.fullmatch(text) and text == "__user_initial_stackheap":
                self._define_label(text, line)
                self.microlib_else_stage = 3
                return
        elif stage == 3:
            ldr_match = _LDR_RE.match(text)
            if ldr_match is not None:
                register, expression = ldr_match.group(1), re.sub(r"\s+", "", ldr_match.group(2))
                expected = {
                    "0": "Heap_Mem",
                    "1": "(Stack_Mem+Stack_Size)",
                    "2": "(Heap_Mem+Heap_Size)",
                    "3": "Stack_Mem",
                }
                if (
                    register == str(self.microlib_ldr_index)
                    and expected.get(register) == expression
                ):
                    self.microlib_ldr_index += 1
                    if self.microlib_ldr_index == 4:
                        self.microlib_else_stage = 4
                    return
            self._diag(
                "MIGRATION_STARTUP_MICROLIB_UNSUPPORTED",
                line,
                "unsupported __user_initial_stackheap expression",
            )
            return
        elif stage == 4:
            if _BX_LR_RE.match(text):
                self.microlib_else_stage = 5
                return
        elif stage == 5:
            if _ALIGN_RE.match(text):
                self.microlib_else_stage = 6
                return
        self._diag(
            "MIGRATION_STARTUP_MICROLIB_UNSUPPORTED",
            line,
            "unsupported statement in the Microlib ELSE branch",
        )

    # -- final validation ---------------------------------------------------

    def _finalize(self) -> None:
        if self.core is None:
            self.diagnostics.append(
                StartupDiagnostic(
                    code="MIGRATION_STARTUP_CORE_UNSUPPORTED",
                    path=self.path,
                    line=0,
                    column=0,
                    evidence="",
                    message="startup generation supports normalized cortex-m3, cortex-m4 and cortex-m7 only",
                )
            )

        if self.stack_area_line is None:
            self.diagnostics.append(
                StartupDiagnostic(
                    code="MIGRATION_STARTUP_STACK_LAYOUT_UNSUPPORTED",
                    path=self.path,
                    line=0,
                    column=0,
                    evidence="",
                    message="the conventional STACK area is required",
                )
            )
        elif self.stack_stage != 2:
            self._layout_diagnostic(self.stack_area_line, "STACK area is incomplete")
        if self.heap_area_line is None:
            self.diagnostics.append(
                StartupDiagnostic(
                    code="MIGRATION_STARTUP_STACK_LAYOUT_UNSUPPORTED",
                    path=self.path,
                    line=0,
                    column=0,
                    evidence="",
                    message="the conventional HEAP area is required",
                )
            )
        elif self.heap_stage != 3:
            self._layout_diagnostic(self.heap_area_line, "HEAP area is incomplete")

        self._validate_size("Stack_Size", positive=True)
        self._validate_size("Heap_Size", positive=False)

        if not self.preserve8:
            self._layout_diagnostic(0, "PRESERVE8 is required")
        if not self.thumb:
            self._layout_diagnostic(0, "THUMB is required")

        if self.reset_area_line is None or self.vector_label_line is None:
            self.diagnostics.append(
                StartupDiagnostic(
                    code="MIGRATION_STARTUP_VECTOR_UNSUPPORTED",
                    path=self.path,
                    line=0,
                    column=0,
                    evidence="",
                    message="exactly one conventional __Vectors table is required",
                )
            )
        if self.vector_end_line is None:
            self.diagnostics.append(
                StartupDiagnostic(
                    code="MIGRATION_STARTUP_VECTOR_UNSUPPORTED",
                    path=self.path,
                    line=0,
                    column=0,
                    evidence="",
                    message="__Vectors_End is required after the vector entries",
                )
            )
        if self.vector_label_line is not None and self.vector_end_line is None:
            self.diagnostics.append(
                StartupDiagnostic(
                    code="MIGRATION_STARTUP_VECTOR_UNSUPPORTED",
                    path=self.path,
                    line=0,
                    column=0,
                    evidence="",
                    message="vector table has no end",
                )
            )
        if self.vector_label_line is not None and self.vector_end_line is not None:
            if len(self.vectors) < 2:
                self.diagnostics.append(
                    StartupDiagnostic(
                        code="MIGRATION_STARTUP_VECTOR_UNSUPPORTED",
                        path=self.path,
                        line=self.vector_label_line,
                        column=0,
                        evidence="",
                        message="vector table must contain at least the initial SP and reset handler",
                    )
                )
            else:
                first, second = self.vectors[0], self.vectors[1]
                if first.symbol != "__initial_sp" or first.reserved:
                    self._vector_diagnostic(
                        first.line,
                        "first vector word must be __initial_sp",
                    )
                if second.symbol != "Reset_Handler" or second.reserved:
                    self._vector_diagnostic(
                        second.line,
                        "second vector word must be Reset_Handler",
                    )

        vectors_size = self.equ_values.get("__Vectors_Size")
        if self.vector_label_line is not None and vectors_size is None:
            self.diagnostics.append(
                StartupDiagnostic(
                    code="MIGRATION_STARTUP_VECTOR_UNSUPPORTED",
                    path=self.path,
                    line=self.vector_end_line or self.vector_label_line,
                    column=0,
                    evidence="",
                    message="__Vectors_Size EQU __Vectors_End - __Vectors is required",
                )
            )
        for export_name in ("__Vectors", "__Vectors_End", "__Vectors_Size"):
            if self.exports.get(export_name) is None:
                self.diagnostics.append(
                    StartupDiagnostic(
                        code="MIGRATION_STARTUP_VECTOR_UNSUPPORTED",
                        path=self.path,
                        line=self.vector_label_line or 0,
                        column=0,
                        evidence=export_name,
                        message=f"EXPORT {export_name} is required for the conventional vector table",
                    )
                )
        if not self.align_seen:
            self._layout_diagnostic(0, "ALIGN is required by the conventional startup pattern")

        if self.text_area_line is None:
            self._layout_diagnostic(0, "AREA |.text|, CODE, READONLY is required")
        if "Reset_Handler" not in self.individual_handlers:
            self.diagnostics.append(
                StartupDiagnostic(
                    code="MIGRATION_STARTUP_RESET_UNSUPPORTED",
                    path=self.path,
                    line=0,
                    column=0,
                    evidence="",
                    message="the conventional Reset_Handler PROC is required",
                )
            )

        self._validate_vectors()
        self._validate_microlib()
        if not self.ended:
            self.diagnostics.append(
                StartupDiagnostic(
                    code="MIGRATION_STARTUP_GRAMMAR_UNSUPPORTED",
                    path=self.path,
                    line=0,
                    column=0,
                    evidence="",
                    message="the startup file must end with END",
                )
            )

    def _layout_diagnostic(self, line: int, message: str) -> None:
        self.diagnostics.append(
            StartupDiagnostic(
                code="MIGRATION_STARTUP_STACK_LAYOUT_UNSUPPORTED",
                path=self.path,
                line=line,
                column=0,
                evidence="",
                message=message,
            )
        )

    def _vector_diagnostic(self, line: int, message: str) -> None:
        self.diagnostics.append(
            StartupDiagnostic(
                code="MIGRATION_STARTUP_VECTOR_UNSUPPORTED",
                path=self.path,
                line=line,
                column=0,
                evidence="",
                message=message,
            )
        )

    def _validate_size(self, name: str, *, positive: bool) -> None:
        entry = self.equ_values.get(name)
        if entry is None:
            self.diagnostics.append(
                StartupDiagnostic(
                    code="MIGRATION_STARTUP_SIZE_INVALID",
                    path=self.path,
                    line=0,
                    column=0,
                    evidence="",
                    message=f"{name} EQU <bytes> is required",
                )
            )
            return
        value = entry[0]
        if value is None:
            return
        minimum = 1 if positive else 0
        if (
            value < minimum
            or value > 0xFFFFFFFF
            or value % STARTUP_ALIGNMENT != 0
        ):
            self.diagnostics.append(
                StartupDiagnostic(
                    code="MIGRATION_STARTUP_SIZE_INVALID",
                    path=self.path,
                    line=entry[2],
                    column=0,
                    evidence=_cap(entry[1]),
                    message=(
                        f"{name} must be a {'positive' if positive else 'nonnegative'} "
                        "8-byte-aligned unsigned 32-bit byte count"
                    ),
                )
            )

    def _validate_vectors(self) -> None:
        target_kinds: dict[str, str] = {}
        for entry in self.vectors:
            if entry.reserved:
                continue
            if entry.symbol == "__initial_sp":
                if entry.index != 0:
                    self._vector_diagnostic(
                        entry.line,
                        "__initial_sp is only recognized as the first vector word",
                    )
                continue
            if entry.symbol == "Reset_Handler":
                if entry.index != 1:
                    self._vector_diagnostic(
                        entry.line,
                        "Reset_Handler is only recognized as the second vector word",
                    )
                target_kinds.setdefault("Reset_Handler", "reset")
                continue
            if entry.symbol is None:
                continue
            if entry.symbol in self.individual_handlers:
                target_kinds[entry.symbol] = "individual"
            elif entry.symbol in self.alias_handlers:
                target_kinds[entry.symbol] = "default-alias"
            else:
                self.diagnostics.append(
                    StartupDiagnostic(
                        code="MIGRATION_STARTUP_UNDECLARED_HANDLER",
                        path=self.path,
                        line=entry.line,
                        column=0,
                        evidence=entry.symbol,
                        message="vector target has no recognized handler definition",
                    )
                )
                continue
            export = self.exports.get(entry.symbol)
            if export is None or not export[0]:
                self.diagnostics.append(
                    StartupDiagnostic(
                        code="MIGRATION_STARTUP_HANDLER_EXPORT_UNSUPPORTED",
                        path=self.path,
                        line=entry.line,
                        column=0,
                        evidence=entry.symbol,
                        message="vector handler must be exported as weak so a strong C definition can override it",
                    )
                )

        for name, line in self.individual_handlers.items():
            if name == "Reset_Handler":
                continue
            if name not in target_kinds:
                self.diagnostics.append(
                    StartupDiagnostic(
                        code="MIGRATION_STARTUP_UNREFERENCED_HANDLER",
                        path=self.path,
                        line=line,
                        column=0,
                        evidence=name,
                        message="handler PROC is not referenced by the vector table",
                    )
                )
        for name, line in self.alias_handlers.items():
            if name not in target_kinds:
                self.diagnostics.append(
                    StartupDiagnostic(
                        code="MIGRATION_STARTUP_UNREFERENCED_HANDLER",
                        path=self.path,
                        line=line,
                        column=0,
                        evidence=name,
                        message="Default_Handler alias is not referenced by the vector table",
                    )
                )
        if self.default_handler_line is not None:
            for name, line in self.default_exports:
                if name not in self.alias_handlers and name not in target_kinds:
                    self.diagnostics.append(
                        StartupDiagnostic(
                            code="MIGRATION_STARTUP_UNREFERENCED_HANDLER",
                            path=self.path,
                            line=line,
                            column=0,
                            evidence=name,
                            message="weak Default_Handler export is not a bare alias label or vector target",
                        )
                    )

    def _validate_microlib(self) -> None:
        if self.microlib_state == "outside":
            self.diagnostics.append(
                StartupDiagnostic(
                    code="MIGRATION_STARTUP_MICROLIB_UNSUPPORTED",
                    path=self.path,
                    line=0,
                    column=0,
                    evidence="",
                    message="the conventional IF :DEF:__MICROLIB / __user_initial_stackheap block is required",
                )
            )
        elif self.microlib_state == "if":
            self.diagnostics.append(
                StartupDiagnostic(
                    code="MIGRATION_STARTUP_MICROLIB_UNSUPPORTED",
                    path=self.path,
                    line=0,
                    column=0,
                    evidence="",
                    message="Microlib block has no ELSE",
                )
            )
        elif self.microlib_state == "else":
            self.diagnostics.append(
                StartupDiagnostic(
                    code="MIGRATION_STARTUP_MICROLIB_UNSUPPORTED",
                    path=self.path,
                    line=0,
                    column=0,
                    evidence="",
                    message="Microlib block has no ENDIF",
                )
            )
        if self.microlib_state == "done" and self.microlib_else_stage < 5:
            self.diagnostics.append(
                StartupDiagnostic(
                    code="MIGRATION_STARTUP_MICROLIB_UNSUPPORTED",
                    path=self.path,
                    line=0,
                    column=0,
                    evidence="",
                    message="__user_initial_stackheap boilerplate is incomplete",
                )
            )

    def _handlers(self) -> tuple[StartupHandler, ...]:
        result: list[StartupHandler] = []
        seen: set[str] = set()
        for entry in self.vectors:
            symbol = entry.symbol
            if symbol is None or symbol == "__initial_sp" or symbol in seen:
                continue
            seen.add(symbol)
            if symbol == "Reset_Handler":
                kind = "reset"
                definition_line = self.individual_handlers.get(symbol, entry.line)
            elif symbol in self.individual_handlers:
                kind = "individual"
                definition_line = self.individual_handlers[symbol]
            elif symbol in self.alias_handlers:
                kind = "default-alias"
                definition_line = self.alias_handlers[symbol]
            else:
                continue
            result.append(StartupHandler(symbol, kind, definition_line))
        return tuple(result)


# ---------------------------------------------------------------------------
# analysis and generation
# ---------------------------------------------------------------------------


def _candidates(inspection: KeilInspection, exact_bytes: Mapping[str, bytes]) -> tuple[str, ...]:
    paths = {
        source.path
        for source in inspection.sources
        if source.included
        and source.language == "asm"
        and len(exact_bytes.get(source.path, b"")) > 0
    }
    return tuple(sorted(paths))


def _select_source(
    inspection: KeilInspection,
    options: StartupOptions,
    exact_bytes: Mapping[str, bytes],
) -> str:
    if options.source is not None:
        source = next(
            (
                item
                for item in inspection.sources
                if item.path == options.source and item.included and item.language == "asm"
            ),
            None,
        )
        if source is None:
            raise _raise(
                "MIGRATION_STARTUP_SOURCE_INVALID",
                "startupSource is not an included ARMCC assembly source",
                {"path": options.source or "", "rule": "notIncludedAssembly"},
            )
        data = exact_bytes.get(source.path)
        if not data:
            raise _raise(
                "MIGRATION_STARTUP_SOURCE_INVALID",
                "startupSource is empty or unreadable",
                {"path": source.path, "rule": "emptyAssembly"},
            )
        return source.path

    candidates = _candidates(inspection, exact_bytes)
    if not candidates:
        raise _raise(
            "MIGRATION_STARTUP_SOURCE_NOT_FOUND",
            "no non-empty included ARMCC assembly startup candidate was found; pass startupSource explicitly",
            {"candidates": []},
        )
    if len(candidates) > 1:
        raise _raise(
            "MIGRATION_STARTUP_SELECTION_REQUIRED",
            "multiple ARMCC assembly candidates exist; select one explicitly with startupSource",
            {"candidates": list(candidates)},
        )
    return candidates[0]


def _read_destination(root: Path) -> tuple[str, bytes | None]:
    """Return (missing|identical-base-state, bytes); collisions classify later."""
    path = STARTUP_GENERATED_PATH
    absolute = root.joinpath(*path.split("/"))
    try:
        resolved = absolute.resolve(strict=False)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return "collision", None
    try:
        listing = os.lstat(resolved)
    except FileNotFoundError:
        return "missing", None
    except NotADirectoryError:
        return "missing", None
    except OSError:
        return "collision", None
    if not stat.S_ISREG(listing.st_mode):
        return "collision", None
    try:
        with resolved.open("rb") as handle:
            data = handle.read(STARTUP_FILE_LIMIT_BYTES + 1)
    except OSError:
        return "collision", None
    if len(data) > STARTUP_FILE_LIMIT_BYTES:
        return "collision", None
    return "present", data


def analyze_startup(
    root: Path,
    inspection: KeilInspection,
    options: StartupOptions,
    exact_bytes: Mapping[str, bytes],
) -> StartupOutcome:
    """Analyze and generate one selected startup without mutating the project."""
    source = _select_source(inspection, options, exact_bytes)
    if portable_path_error(source) is not None:
        raise _raise(
            "MIGRATION_STARTUP_SOURCE_INVALID",
            "selected startup path is not portable",
            {"path": source, "rule": "withinProjectRoot"},
        )
    if source == STARTUP_GENERATED_PATH:
        raise _raise(
            "MIGRATION_STARTUP_SOURCE_INVALID",
            "the generated destination cannot also be the selected source",
            {"path": source, "rule": "sameAsGeneratedPath"},
        )
    data = exact_bytes[source]
    if len(data) > STARTUP_FILE_LIMIT_BYTES:
        raise _raise(
            "MIGRATION_STARTUP_LIMIT_EXCEEDED",
            "startup source exceeds the per-file limit",
            {"scope": "startup", "limitBytes": STARTUP_FILE_LIMIT_BYTES},
        )
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = None

    core = normalize_startup_core(inspection.cpu)
    source_sha = hashlib.sha256(data).hexdigest()
    if text is None:
        parsed = _ParsedStartup(
            core=core,
            stack_size=None,
            heap_size=None,
            vectors=(),
            handlers=(),
            diagnostics=(
                StartupDiagnostic(
                    "MIGRATION_STARTUP_ENCODING_UNSUPPORTED",
                    source,
                    0,
                    0,
                    "",
                    "startup source is not UTF-8; convert and review it outside Toolkit",
                ),
            ),
        )
    else:
        parsed = _Parser(source, _logical_lines(text), core).run()

    generated: bytes | None = None
    destination_state = "missing"
    destination_bytes: bytes | None = None
    if parsed.status == "ready" and parsed.core is not None:
        generated = render_startup(
            source_path=source,
            source_sha256=source_sha,
            parsed=parsed,
        )
        destination_state, destination_bytes = _read_destination(root)
        if destination_state == "present":
            if destination_bytes == generated:
                destination_state = "identical"
            else:
                destination_state = "collision"
                parsed = _with_diagnostic(
                    parsed,
                    StartupDiagnostic(
                        "MIGRATION_STARTUP_TARGET_COLLISION",
                        STARTUP_GENERATED_PATH,
                        0,
                        0,
                        "",
                        "generated startup destination already exists with different bytes; it is never overwritten",
                    ),
                )
                generated = None
        elif destination_state == "collision":
            parsed = _with_diagnostic(
                parsed,
                StartupDiagnostic(
                    "MIGRATION_STARTUP_TARGET_COLLISION",
                    STARTUP_GENERATED_PATH,
                    0,
                    0,
                    "",
                    "generated startup destination cannot be inspected safely; it is never overwritten",
                ),
            )
            generated = None
    analysis = StartupAnalysis(
        strategy=options.strategy,
        status=parsed.status,
        source_path=source,
        source_sha256=source_sha,
        source_size=len(data),
        core=parsed.core,
        stack_size=parsed.stack_size,
        heap_size=parsed.heap_size,
        vector_count=len(parsed.vectors),
        reserved_count=parsed.reserved_count,
        vectors=parsed.vectors,
        handlers=parsed.handlers,
        reset_pattern=RESET_PATTERN,
        generated_path=STARTUP_GENERATED_PATH if generated is not None else None,
        generated_sha256=(
            hashlib.sha256(generated).hexdigest() if generated is not None else None
        ),
        generated_size=len(generated) if generated is not None else None,
        warnings=_STARTUP_WARNINGS,
        diagnostics=parsed.diagnostics,
    )
    if destination_state == "collision":
        # Keep generated evidence visible even though no file may be written.
        if analysis.generated_sha256 is None:
            candidate = render_startup(
                source_path=source,
                source_sha256=source_sha,
                parsed=parsed,
            )
            analysis = StartupAnalysis(
                strategy=analysis.strategy,
                status="unsupported",
                source_path=analysis.source_path,
                source_sha256=analysis.source_sha256,
                source_size=analysis.source_size,
                core=analysis.core,
                stack_size=analysis.stack_size,
                heap_size=analysis.heap_size,
                vector_count=analysis.vector_count,
                reserved_count=analysis.reserved_count,
                vectors=analysis.vectors,
                handlers=analysis.handlers,
                reset_pattern=analysis.reset_pattern,
                generated_path=STARTUP_GENERATED_PATH,
                generated_sha256=hashlib.sha256(candidate).hexdigest(),
                generated_size=len(candidate),
                warnings=analysis.warnings,
                diagnostics=analysis.diagnostics,
            )
    return StartupOutcome(
        analysis=analysis,
        generated_bytes=generated,
        selected_source=source,
        destination_state=destination_state,
        destination_bytes=destination_bytes,
    )


def _with_diagnostic(parsed: _ParsedStartup, diagnostic: StartupDiagnostic) -> _ParsedStartup:
    return _ParsedStartup(
        core=parsed.core,
        stack_size=parsed.stack_size,
        heap_size=parsed.heap_size,
        vectors=parsed.vectors,
        handlers=parsed.handlers,
        diagnostics=tuple(
            sorted(
                (*parsed.diagnostics, diagnostic),
                key=lambda item: (item.line, item.column, item.code),
            )
        ),
    )


def _word(entry: StartupVectorEntry) -> str:
    return ".word 0" if entry.reserved else f".word {entry.symbol}"


def render_startup(
    *,
    source_path: str,
    source_sha256: str,
    parsed: _ParsedStartup,
) -> bytes:
    """Render the deterministic GNU assembly startup for recognized evidence."""
    assert parsed.core is not None
    assert parsed.stack_size is not None
    assert parsed.heap_size is not None
    assert len(parsed.vectors) >= 2

    lines: list[str] = [
        "/* Generated by STM32 Toolkit from a recognized ARMCC CMSIS startup. */",
        f"/* Source: {source_path} */",
        f"/* Source SHA-256: {source_sha256} */",
        "/* REVIEW REQUIRED: this GNU runtime initialization is not binary, ABI or",
        " * behavioral equivalence with ARMCC or Microlib. Review the vector table,",
        " * stack/heap reservations and constructor path before applying it. */",
        f"/* Stack Size: 0x{parsed.stack_size:08x} bytes; Heap Size: 0x{parsed.heap_size:08x} bytes. */",
        "",
        "  .syntax unified",
        f"  .cpu {parsed.core}",
        "  .thumb",
        "",
        "  .global __Vectors",
        "  .global __Vectors_End",
        "  .global __Vectors_Size",
        "",
        '  .section .isr_vector,"a",%progbits',
        "  .align 2",
        "  .type __Vectors, %object",
        "__Vectors:",
    ]
    lines.extend(f"  {_word(entry)}" for entry in parsed.vectors)
    lines.extend(
        [
            "__Vectors_End:",
            "  .size __Vectors, __Vectors_End - __Vectors",
            "  .set __Vectors_Size, __Vectors_End - __Vectors",
            "",
            '  .section .text.Reset_Handler,"ax",%progbits',
            "  .align 2",
            "  .weak Reset_Handler",
            "  .type Reset_Handler, %function",
            "  .thumb_func",
            "Reset_Handler:",
            "  bl SystemInit",
            "  ldr r0, =_sidata",
            "  ldr r1, =_sdata",
            "  ldr r2, =_edata",
            "1:",
            "  cmp r1, r2",
            "  bcs 2f",
            "  ldr r3, [r0], #4",
            "  str r3, [r1], #4",
            "  b 1b",
            "2:",
            "  ldr r1, =_sbss",
            "  ldr r2, =_ebss",
            "  movs r3, #0",
            "3:",
            "  cmp r1, r2",
            "  bcs 4f",
            "  str r3, [r1], #4",
            "  b 3b",
            "4:",
            "  bl __libc_init_array",
            "  bl main",
            "5:",
            "  b 5b",
            "  .size Reset_Handler, . - Reset_Handler",
            "",
            "  .weak _init",
            "  .type _init, %function",
            "  .thumb_func",
            "_init:",
            "  bx lr",
            "  .size _init, . - _init",
            "",
            "  .weak _fini",
            "  .type _fini, %function",
            "  .thumb_func",
            "_fini:",
            "  bx lr",
            "  .size _fini, . - _fini",
            "",
        ]
    )

    for handler in parsed.handlers:
        if handler.kind != "individual":
            continue
        lines.extend(
            [
                f"  .weak {handler.name}",
                f"  .type {handler.name}, %function",
                "  .thumb_func",
                f"{handler.name}:",
                "  b .",
                f"  .size {handler.name}, . - {handler.name}",
                "",
            ]
        )
    aliases = [handler for handler in parsed.handlers if handler.kind == "default-alias"]
    if aliases:
        lines.extend(
            [
                "  .weak Default_Handler",
                "  .type Default_Handler, %function",
                "  .thumb_func",
                "Default_Handler:",
                "  b .",
                "  .size Default_Handler, . - Default_Handler",
                "",
            ]
        )
        for handler in aliases:
            lines.extend(
                [
                    f"  .weak {handler.name}",
                    f"  .thumb_set {handler.name}, Default_Handler",
                    "",
                ]
            )
    return ("\n".join(lines).rstrip("\n") + "\n").encode("utf-8")


__all__ = [
    "RUNTIME_INITIALIZATION",
    "STARTUP_FILE_LIMIT_BYTES",
    "STARTUP_GENERATED_PATH",
    "STARTUP_STRATEGY",
    "STARTUP_VECTOR_LIMIT",
    "SUPPORTED_STARTUP_CORES",
    "StartupOutcome",
    "analyze_startup",
    "normalize_startup_core",
    "normalize_startup_options",
    "render_startup",
]
