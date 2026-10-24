"""Bounded GNU ld section-fragment parsing and reading.

``generation.linkerFragment`` is an optional project-relative UTF-8 file that
the project owner writes.  It is never a general GNU linker-script
interpreter: this module accepts only explicit writable-RAM ``NOLOAD`` output
sections whose statements are ``. = ALIGN(n);``, ``*(selectors)`` or
``KEEP(*(selectors))``.  Every selector must stay inside its own output
section family, every region name must resolve exactly against the canonical
model region map, and every explicit address must start inside that region.

The parser is a small hand-written tokenizer/recursive-descent consumer with
fixed section/statement/selector/token bounds, so malformed or hostile input
fails deterministically rather than through unbounded regular-expression
backtracking.  C block comments are removed before tokenization; their text
is never interpreted as a directive.  The whole input must be consumed.

This module performs bounded filesystem reads only in
:func:`read_linker_fragment`; parsing itself is pure.  It has no Toolkit model
imports so the manifest/model loader and generation layer can share it.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from stm32_toolkit.memory_layout import region_facts

#: One reviewed fragment; larger files/lists are rejected, never sampled.
MAX_FRAGMENT_BYTES = 64 * 1024
MAX_SECTIONS = 32
MAX_STATEMENTS_PER_SECTION = 64
MAX_TOTAL_STATEMENTS = 256
MAX_SELECTORS_PER_STATEMENT = 64
MAX_TOTAL_SELECTORS = 256
MAX_NAME_LENGTH = 64
MAX_TOKENS = 8192
MAX_ALIGNMENT = 4096

_REPARSE_POINT_ATTRIBUTE = 0x400
_DRIVE_PREFIX_RE = re.compile(r"^[A-Za-z]:")

#: The two accepted selector spellings.  The pattern length is separately
#: bounded before matching, so these anchored classes cannot backtrack.
_SECTION_NAME_RE = re.compile(r"^\.[A-Za-z_][A-Za-z0-9_]*$")
_SELECTOR_SUFFIX_RE = re.compile(r"^(\.[A-Za-z_][A-Za-z0-9_]*)\.\*$")

#: Names/prefixes consumed by the managed template wildcards or owned by the
#: standard GNU metadata convention.  All entries are lowercase because the
#: comparison casefolds the candidate; these are rejected as broad prefixes
#: because ``*(.text*)``-style wildcards would otherwise steal an input
#: section from the fragment.
_WILDCARD_RESERVED_PREFIXES = (
    ".text",
    ".rodata",
    ".data",
    ".bss",
    # Standard small-data families: initialized and zero-initialized objects
    # selected by the compiler's small-data access model, never custom NOLOAD.
    ".sdata",
    ".sbss",
    # Thread-local initialized/zero-initialized storage.
    ".tdata",
    ".tbss",
    # Dynamic-linking metadata (the managed linker does not emit it, but the
    # family must never be mistaken for a custom writable section).
    ".dynamic",
    ".dynsym",
    ".dynstr",
    ".hash",
    ".isr_vector",
    ".arm",
    ".stm32tk.abs",
    ".gnu",
    ".debug",
    ".note",
    ".comment",
    ".symtab",
    ".strtab",
    ".shstrtab",
    ".group",
    ".llvm",
    ".ctors",
    ".dtors",
    ".got",
    ".plt",
    ".stab",
)

#: Standard GNU metadata/fixed families, matched on a family boundary so that
#: a legitimate custom name such as ``.region`` is not mistaken for ``.rel``.
_RESERVED_FAMILIES = (
    ".heap",
    ".stack",
    ".init",
    ".fini",
    ".preinit_array",
    ".init_array",
    ".fini_array",
    ".eh_frame",
    ".gcc_except_table",
    ".rel",
    ".rela",
    ".build_attributes",
    ".drectve",
    ".version",
)

REMEDIATION = (
    "Use generation.linkerFragment to name a project-relative UTF-8 GNU ld "
    "fragment containing only writable-RAM NOLOAD output sections: "
    "`.name [address] (NOLOAD) : { . = ALIGN(n); *(.name .name.*) } > REGION`. "
    "Selectors must stay in their own output family, the region must already "
    "exist as a writable memory.regions/extraRegions entry, and no managed or "
    "standard GNU section family may be selected. Then rerun "
    "stm32_project_configure PLAN/APPLY; never edit the managed linker or the "
    "generated-files digest."
)

BUILD_REMEDIATION = (
    "The managed configuration does not match the current linker fragment. "
    "Rerun stm32_project_configure PLAN/APPLY, then rebuild with --clean when "
    "the merged linker or fragment changed. Do not edit the managed linker or "
    "the generated-files digest."
)


class LinkerFragmentError(Exception):
    """A stable fragment failure with portable path/field/rule details."""

    code = "LINKER_FRAGMENT_INVALID"

    def __init__(
        self,
        message: str,
        path: str,
        rule: str,
        *,
        field: str = "fragment",
        line: int | None = None,
        column: int | None = None,
        remediation: str = REMEDIATION,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, object] = {
            "path": path,
            "field": field,
            "rule": rule,
            "remediation": remediation,
        }
        if line is not None:
            self.details["line"] = line
        if column is not None:
            self.details["column"] = column


def _fail(
    path: str,
    rule: str,
    message: str,
    *,
    field: str = "fragment",
    line: int | None = None,
    column: int | None = None,
) -> LinkerFragmentError:
    return LinkerFragmentError(
        message, path, rule, field=field, line=line, column=column
    )


@dataclass(frozen=True)
class FragmentStatement:
    """One validated statement: align, section selectors, or KEEP selectors."""

    kind: str  # "align" | "sections" | "keep"
    alignment: int | None = None
    selectors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"kind": self.kind}
        if self.kind == "align":
            payload["alignment"] = self.alignment
        else:
            payload["selectors"] = list(self.selectors)
        return payload

    def render_line(self) -> str:
        if self.kind == "align":
            return f". = ALIGN({self.alignment});"
        joined = " ".join(self.selectors)
        if self.kind == "keep":
            return f"KEEP(*({joined}))"
        return f"*({joined})"


@dataclass(frozen=True)
class FragmentSection:
    """One validated custom NOLOAD output section."""

    name: str
    address: int | None
    region: str
    statements: tuple[FragmentStatement, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "address": self.address,
            "region": self.region,
            "statements": [statement.to_dict() for statement in self.statements],
        }

    def statement_lines(self) -> tuple[str, ...]:
        return tuple(statement.render_line() for statement in self.statements)


@dataclass(frozen=True)
class LinkerFragment:
    """The immutable parsed fragment plus the exact raw-byte digest."""

    path: str
    sha256: str
    sections: tuple[FragmentSection, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "sections": [section.to_dict() for section in self.sections],
        }


# ---------------------------------------------------------------------------
# bounded reading
# ---------------------------------------------------------------------------


def _is_redirect(state: os.stat_result) -> bool:
    return stat.S_ISLNK(state.st_mode) or bool(
        getattr(state, "st_file_attributes", 0) & _REPARSE_POINT_ATTRIBUTE
    )


def _path_parts(path: str) -> list[str]:
    if not path or "\\" in path or path.startswith("/") or _DRIVE_PREFIX_RE.match(path):
        raise _fail(path, "path", "linker fragment path is not project-relative")
    parts = path.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise _fail(path, "path", "linker fragment path is not project-relative")
    return parts


def read_linker_fragment(
    root: Path, path: object, regions: Sequence[object]
) -> LinkerFragment:
    """Read one bounded fragment and parse it against the canonical regions.

    Every existing path component must be a non-redirecting directory and the
    terminal component a regular file.  The exact raw bytes are hashed before
    UTF-8 decoding and parsed once; callers cross-check later reads against
    the returned digest to refuse races.
    """
    if not isinstance(path, str) or not path:
        raise _fail(
            path if isinstance(path, str) else "generation.linkerFragment",
            "type",
            "linker fragment path must be a non-empty string",
        )
    parts = _path_parts(path)
    current = root
    for part in parts:
        current = current / part
        try:
            state = os.lstat(current)
        except FileNotFoundError:
            raise _fail(path, "missing", "linker fragment is missing") from None
        except NotADirectoryError:
            raise _fail(path, "missing", "linker fragment is missing") from None
        except OSError:
            raise _fail(path, "unreadable", "linker fragment is unreadable") from None
        if _is_redirect(state):
            raise _fail(
                path, "redirect", "linker fragment must not redirect at any component"
            )
    if not stat.S_ISREG(state.st_mode):
        raise _fail(
            path, "regularFile", "linker fragment is not a regular file"
        )
    try:
        with current.open("rb") as handle:
            data = handle.read(MAX_FRAGMENT_BYTES + 1)
    except OSError:
        raise _fail(path, "unreadable", "linker fragment is unreadable") from None
    if len(data) > MAX_FRAGMENT_BYTES:
        raise _fail(
            path, "size", "linker fragment exceeds the supported byte limit"
        )
    digest = hashlib.sha256(data).hexdigest()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise _fail(path, "encoding", "linker fragment is not valid UTF-8") from None
    sections = parse_linker_fragment(text, path, regions)
    return LinkerFragment(path=path, sha256=digest, sections=sections)


# ---------------------------------------------------------------------------
# tokenizer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Token:
    kind: str  # "word" | "number" | "punct"
    value: str
    line: int
    column: int


_WORD_START = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_$.*"
)
_WORD_CONTINUE = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$.*-"
)
_PUNCTUATION = frozenset("{}():;=>,")
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
_DECIMAL_DIGITS = frozenset("0123456789")
_WHITESPACE = frozenset(" \t\r\f\v")


def _strip_comments(text: str, path: str) -> str:
    """Replace every C block comment with spaces, preserving line numbers."""
    output: list[str] = []
    in_comment = False
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        following = text[index + 1] if index + 1 < length else ""
        if not in_comment:
            if char == "/" and following == "*":
                in_comment = True
                output.append("  ")
                index += 2
                continue
            output.append(char)
            index += 1
            continue
        if char == "*" and following == "/":
            in_comment = False
            output.append("  ")
            index += 2
            continue
        output.append("\n" if char == "\n" else " ")
        index += 1
    if in_comment:
        raise _fail(path, "comment", "linker fragment has an unterminated comment")
    return "".join(output)


def _tokenize(text: str, path: str) -> list[_Token]:
    tokens: list[_Token] = []
    line = 1
    column = 1
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char in _WHITESPACE:
            index += 1
            column += 1
            continue
        if char == "\n":
            index += 1
            line += 1
            column = 1
            continue
        if char in _PUNCTUATION:
            tokens.append(_Token("punct", char, line, column))
            index += 1
            column += 1
        elif char in _DECIMAL_DIGITS:
            start = index
            if char == "0" and index + 1 < length and text[index + 1] in "xX":
                index += 2
                while index < length and text[index] in _HEX_DIGITS:
                    index += 1
                if index == start + 2:
                    raise _fail(
                        path,
                        "number",
                        "linker fragment has an empty hexadecimal literal",
                        line=line,
                        column=column,
                    )
            else:
                while index < length and text[index] in _DECIMAL_DIGITS:
                    index += 1
            tokens.append(_Token("number", text[start:index], line, column))
            column += index - start
        elif char in _WORD_START:
            start = index
            index += 1
            while index < length and text[index] in _WORD_CONTINUE:
                index += 1
            tokens.append(_Token("word", text[start:index], line, column))
            column += index - start
        else:
            raise _fail(
                path,
                "character",
                "linker fragment contains an unsupported character",
                line=line,
                column=column,
            )
        if len(tokens) > MAX_TOKENS:
            raise _fail(
                path,
                "tokenCount",
                "linker fragment exceeds the supported token count",
            )
    return tokens


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------


def _parse_uint(token: _Token, path: str, field: str) -> int:
    raw = token.value
    if raw[:2].lower() == "0x":
        digits = raw[2:].lstrip("0") or "0"
        if len(digits) > 8:
            raise _fail(
                path,
                "range",
                "linker fragment number is out of range",
                field=field,
                line=token.line,
                column=token.column,
            )
        value = int(digits, 16)
    else:
        digits = raw.lstrip("0") or "0"
        if len(digits) > 10:
            raise _fail(
                path,
                "range",
                "linker fragment number is out of range",
                field=field,
                line=token.line,
                column=token.column,
            )
        value = int(digits, 10)
    if value > 0xFFFF_FFFF:
        raise _fail(
            path,
            "range",
            "linker fragment number is out of range",
            field=field,
            line=token.line,
            column=token.column,
        )
    return value


def _is_reserved(name: str) -> bool:
    folded = name.casefold()
    if any(folded.startswith(prefix) for prefix in _WILDCARD_RESERVED_PREFIXES):
        return True
    return any(
        folded == family or folded.startswith(family + ".")
        for family in _RESERVED_FAMILIES
    )


def _selector_shape(value: str) -> tuple[str, bool] | None:
    """Return ``(family, is_suffix)`` for an accepted selector spelling."""
    if len(value) > MAX_NAME_LENGTH:
        return None
    suffix = _SELECTOR_SUFFIX_RE.fullmatch(value)
    if suffix is not None:
        return (suffix.group(1), True)
    if _SECTION_NAME_RE.fullmatch(value) is not None:
        return (value, False)
    return None


def _patterns_overlap(
    first: tuple[str, bool], second: tuple[str, bool]
) -> bool:
    """Whether two selector patterns can match the same input section.

    An exact selector matches only its own name; a trailing ``.*`` selector
    matches names that begin with the family plus a dot.  The two spellings of
    one family (``.sram2`` and ``.sram2.*``) are therefore disjoint.
    """
    first_prefix, first_suffix = first
    second_prefix, second_suffix = second
    if first_suffix and second_suffix:
        return (
            first_prefix == second_prefix
            or first_prefix.startswith(second_prefix + ".")
            or second_prefix.startswith(first_prefix + ".")
        )
    if first_suffix:
        return second_prefix.startswith(first_prefix + ".")
    if second_suffix:
        return first_prefix.startswith(second_prefix + ".")
    return first_prefix == second_prefix


class _Parser:
    def __init__(
        self,
        tokens: Sequence[_Token],
        path: str,
        regions: Sequence[object],
    ) -> None:
        self._tokens = tokens
        self._path = path
        self._index = 0
        self._facts = region_facts(regions)
        self._regions = {fact.name: fact for fact in self._facts}
        self._total_statements = 0
        self._total_selectors = 0
        self._selector_patterns: list[tuple[str, bool]] = []
        self._selector_spellings: dict[str, str] = {}

    def _peek(self) -> _Token | None:
        if self._index < len(self._tokens):
            return self._tokens[self._index]
        return None

    def _advance(self) -> _Token:
        token = self._peek()
        if token is None:
            raise _fail(
                self._path,
                "syntax",
                "linker fragment ended unexpectedly",
                field="fragment",
            )
        self._index += 1
        return token

    def _expect_punct(self, value: str, field: str) -> _Token:
        token = self._peek()
        if token is None or token.kind != "punct" or token.value != value:
            raise _fail(
                self._path,
                "syntax",
                f"linker fragment expected '{value}'",
                field=field,
            )
        self._index += 1
        return token

    def _expect_word(self, value: str, field: str) -> _Token:
        token = self._peek()
        if token is None or token.kind != "word" or token.value != value:
            raise _fail(
                self._path,
                "syntax",
                f"linker fragment expected '{value}'",
                field=field,
            )
        self._index += 1
        return token

    def parse(self) -> tuple[FragmentSection, ...]:
        sections: list[FragmentSection] = []
        folded_names: dict[str, int] = {}
        while self._peek() is not None:
            if len(sections) >= MAX_SECTIONS:
                raise _fail(
                    self._path,
                    "count",
                    "linker fragment exceeds the supported section count",
                    field="sections",
                )
            start = self._peek()
            assert start is not None
            field = f"sections[{len(sections)}]"
            if (
                start.kind != "word"
                or len(start.value) > MAX_NAME_LENGTH
                or _SECTION_NAME_RE.fullmatch(start.value) is None
            ):
                raise _fail(
                    self._path,
                    "syntax",
                    "linker fragment expected a custom output section name",
                    field=field,
                    line=start.line,
                    column=start.column,
                )
            self._advance()
            name = start.value
            if _is_reserved(name):
                raise _fail(
                    self._path,
                    "reserved",
                    "linker fragment output section name is managed or reserved",
                    field=f"{field}.name",
                    line=start.line,
                    column=start.column,
                )
            folded = name.casefold()
            if folded in folded_names:
                raise _fail(
                    self._path,
                    "casefoldCollision",
                    "linker fragment output section names must be unique ignoring case",
                    field=f"{field}.name",
                )
            folded_names[folded] = len(sections)

            address: int | None = None
            token = self._peek()
            if token is not None and token.kind == "number":
                self._advance()
                address = _parse_uint(token, self._path, f"{field}.address")

            self._expect_punct("(", f"{field}.noload")
            self._expect_word("NOLOAD", f"{field}.noload")
            self._expect_punct(")", f"{field}.noload")
            self._expect_punct(":", f"{field}.separator")
            self._expect_punct("{", f"{field}.statements")
            statements = self._parse_statements(field, name)
            if not any(statement.selectors for statement in statements):
                raise _fail(
                    self._path,
                    "selectors",
                    "linker fragment section requires at least one selector",
                    field=f"{field}.statements",
                )
            self._expect_punct(">", f"{field}.region")
            region_token = self._peek()
            if region_token is None or region_token.kind != "word":
                raise _fail(
                    self._path,
                    "syntax",
                    "linker fragment expected a memory region name",
                    field=f"{field}.region",
                )
            self._advance()
            region_name = region_token.value
            fact = self._regions.get(region_name)
            if fact is None:
                raise _fail(
                    self._path,
                    "unknownRegion",
                    "linker fragment names an unknown memory region",
                    field=f"{field}.region",
                    line=region_token.line,
                    column=region_token.column,
                )
            if "w" not in fact.attributes:
                raise _fail(
                    self._path,
                    "regionAccess",
                    "linker fragment may only target a writable memory region",
                    field=f"{field}.region",
                    line=region_token.line,
                    column=region_token.column,
                )
            if address is not None and not (
                fact.origin <= address < fact.origin + fact.length
            ):
                raise _fail(
                    self._path,
                    "addressRegion",
                    "linker fragment explicit address is outside its region",
                    field=f"{field}.address",
                )
            trailing = self._peek()
            if trailing is not None and trailing.kind == "punct" and trailing.value == ";":
                self._advance()
            sections.append(
                FragmentSection(
                    name=name,
                    address=address,
                    region=region_name,
                    statements=tuple(statements),
                )
            )
        if not sections:
            raise _fail(
                self._path,
                "empty",
                "linker fragment contains no output section",
            )
        return tuple(sections)

    def _parse_statements(
        self, field: str, section_name: str
    ) -> list[FragmentStatement]:
        statements: list[FragmentStatement] = []
        while True:
            token = self._peek()
            if token is None:
                raise _fail(
                    self._path,
                    "syntax",
                    "linker fragment section is not terminated",
                    field=f"{field}.statements",
                )
            if token.kind == "punct" and token.value == "}":
                self._advance()
                break
            if token.kind != "word":
                raise _fail(
                    self._path,
                    "syntax",
                    "linker fragment statement is not supported",
                    field=f"{field}.statements",
                    line=token.line,
                    column=token.column,
                )
            statement_field = f"{field}.statements[{len(statements)}]"
            if token.value == ".":
                statement = self._parse_align(statement_field)
            elif token.value == "*":
                statement = self._parse_sections(section_name, statement_field)
            elif token.value == "KEEP":
                statement = self._parse_keep(section_name, statement_field)
            else:
                raise _fail(
                    self._path,
                    "unsupported",
                    "linker fragment statement is outside the supported subset",
                    field=statement_field,
                    line=token.line,
                    column=token.column,
                )
            statements.append(statement)
            self._total_statements += 1
            if len(statements) > MAX_STATEMENTS_PER_SECTION:
                raise _fail(
                    self._path,
                    "count",
                    "linker fragment section exceeds the supported statement count",
                    field=f"{field}.statements",
                )
            if self._total_statements > MAX_TOTAL_STATEMENTS:
                raise _fail(
                    self._path,
                    "count",
                    "linker fragment exceeds the supported statement count",
                    field="statements",
                )
        return statements

    def _parse_align(self, field: str) -> FragmentStatement:
        self._advance()  # "."
        self._expect_punct("=", field)
        self._expect_word("ALIGN", field)
        self._expect_punct("(", field)
        token = self._peek()
        if token is None or token.kind != "number":
            raise _fail(
                self._path,
                "syntax",
                "linker fragment ALIGN requires an integer",
                field=field,
            )
        self._advance()
        value = _parse_uint(token, self._path, f"{field}.alignment")
        if value == 0 or value > MAX_ALIGNMENT or (value & (value - 1)) != 0:
            raise _fail(
                self._path,
                "alignment",
                "linker fragment ALIGN must be a positive power of two at most 4096",
                field=f"{field}.alignment",
                line=token.line,
                column=token.column,
            )
        self._expect_punct(")", field)
        self._expect_punct(";", field)
        return FragmentStatement(kind="align", alignment=value)

    def _optional_semicolon(self) -> None:
        token = self._peek()
        if token is not None and token.kind == "punct" and token.value == ";":
            self._advance()

    def _parse_sections(
        self, section_name: str, statement_field: str
    ) -> FragmentStatement:
        self._advance()  # "*"
        selectors = self._parse_selector_list(section_name, statement_field)
        self._optional_semicolon()
        return FragmentStatement(kind="sections", selectors=selectors)

    def _parse_keep(
        self, section_name: str, statement_field: str
    ) -> FragmentStatement:
        self._advance()  # "KEEP"
        self._expect_punct("(", statement_field)
        self._expect_word("*", statement_field)
        selectors = self._parse_selector_list(section_name, statement_field)
        self._expect_punct(")", statement_field)
        self._optional_semicolon()
        return FragmentStatement(kind="keep", selectors=selectors)

    def _parse_selector_list(
        self, section_name: str, statement_field: str
    ) -> tuple[str, ...]:
        self._expect_punct("(", statement_field)
        raw: list[_Token] = []
        while True:
            token = self._peek()
            if token is None:
                raise _fail(
                    self._path,
                    "syntax",
                    "linker fragment selector list is not terminated",
                    field=f"{statement_field}.selectors",
                )
            if token.kind == "punct" and token.value == ")":
                self._advance()
                break
            if token.kind != "word":
                raise _fail(
                    self._path,
                    "syntax",
                    "linker fragment selector must be an exact custom section name",
                    field=f"{statement_field}.selectors",
                    line=token.line,
                    column=token.column,
                )
            self._advance()
            raw.append(token)
            if len(raw) > MAX_SELECTORS_PER_STATEMENT:
                raise _fail(
                    self._path,
                    "count",
                    "linker fragment statement exceeds the supported selector count",
                    field=f"{statement_field}.selectors",
                )
            following = self._peek()
            if (
                following is not None
                and following.kind == "punct"
                and following.value == ","
            ):
                self._advance()
                after = self._peek()
                if after is None or (
                    after.kind == "punct" and after.value in (",", ")")
                ):
                    raise _fail(
                        self._path,
                        "syntax",
                        "linker fragment selector list has a trailing comma",
                        field=f"{statement_field}.selectors",
                    )
        if not raw:
            raise _fail(
                self._path,
                "required",
                "linker fragment section requires at least one selector",
                field=f"{statement_field}.selectors",
            )
        selectors: list[str] = []
        for token in raw:
            value = token.value
            shape = (
                _selector_shape(value)
                if len(value) <= MAX_NAME_LENGTH
                else None
            )
            if shape is None:
                raise _fail(
                    self._path,
                    "selector",
                    "linker fragment selector is outside the supported grammar",
                    field=f"{statement_field}.selectors",
                    line=token.line,
                    column=token.column,
                )
            if value != section_name and value != section_name + ".*":
                raise _fail(
                    self._path,
                    "selectorFamily",
                    "linker fragment selector does not belong to its output section family",
                    field=f"{statement_field}.selectors",
                    line=token.line,
                    column=token.column,
                )
            folded = value.casefold()
            if folded in self._selector_spellings:
                raise _fail(
                    self._path,
                    "duplicate",
                    "linker fragment selectors must be unique and non-overlapping",
                    field=f"{statement_field}.selectors",
                    line=token.line,
                    column=token.column,
                )
            for prior in self._selector_patterns:
                if _patterns_overlap(shape, prior):
                    raise _fail(
                        self._path,
                        "overlap",
                        "linker fragment selectors must be unique and non-overlapping",
                        field=f"{statement_field}.selectors",
                        line=token.line,
                        column=token.column,
                    )
            self._selector_spellings[folded] = value
            self._selector_patterns.append(shape)
            selectors.append(value)
            self._total_selectors += 1
            if self._total_selectors > MAX_TOTAL_SELECTORS:
                raise _fail(
                    self._path,
                    "count",
                    "linker fragment exceeds the supported selector count",
                    field="selectors",
                )
        return tuple(selectors)


def parse_linker_fragment(
    text: str, path: str, regions: Sequence[object]
) -> tuple[FragmentSection, ...]:
    """Parse and validate one bounded fragment against the canonical map."""
    if not isinstance(text, str):
        raise _fail(path, "type", "linker fragment must be UTF-8 text")
    cleaned = _strip_comments(text, path)
    tokens = _tokenize(cleaned, path)
    if not tokens:
        raise _fail(path, "empty", "linker fragment contains no output section")
    parser = _Parser(tokens, path, regions)
    return parser.parse()


__all__ = [
    "BUILD_REMEDIATION",
    "FragmentSection",
    "FragmentStatement",
    "LinkerFragment",
    "LinkerFragmentError",
    "MAX_ALIGNMENT",
    "MAX_FRAGMENT_BYTES",
    "MAX_NAME_LENGTH",
    "MAX_SECTIONS",
    "MAX_SELECTORS_PER_STATEMENT",
    "MAX_STATEMENTS_PER_SECTION",
    "MAX_TOTAL_SELECTORS",
    "MAX_TOTAL_STATEMENTS",
    "REMEDIATION",
    "parse_linker_fragment",
    "read_linker_fragment",
]
