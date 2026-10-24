"""Token-aware ARMCC source classification and exact GCC-compatible rewrites.

The lexer walks decoded UTF-8 (or UTF-8 BOM) source text and distinguishes
code, line/block comments, ordinary strings, character literals, C++ raw
strings, and preprocessor directives.  Rewrites target exact code spans only;
comments, strings, character literals, raw strings, preprocessor bodies, and
identifier substrings are never rewritten.  Re-encoding preserves an existing
BOM and every original newline sequence.  Unsupported constructs become
stable blockers; apply can never bypass them.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from stm32_toolkit.migration.constant_context import (
    MAX_UINT32,
    ConstantResolutionError,
    evaluate_integer,
)
from stm32_toolkit.migration.model import (
    FixedSectionRequirement,
    IgnoredObservation,
    MigrationBlocker,
    MigrationPlanError,
)

SCAN_FILE_LIMIT = 8 * 1024 * 1024
SCAN_TOTAL_LIMIT = 64 * 1024 * 1024
MAX_EVIDENCE_CODEPOINTS = 200
MAX_ALIGNMENT = 4096

_SUPPORTED_LANGUAGES = ("c", "cxx")
_HWS = " \t"
_NEWLINE_SKIP = " \t\r\n"

#: ``<type-and-qualifiers> <identifier>[<bounded expression>]`` with no
#: pointer, initializer, function declarator, bit-field, or extra declarator.
_OBJECT_BODY_RE = re.compile(
    r"^[ \t]*((?:[A-Za-z_][A-Za-z0-9_]*[ \t]+)+)"
    r"([A-Za-z_][A-Za-z0-9_]*)[ \t]*"
    r"(?:\[[ \t]*([^\[\]\r\n]+)[ \t]*\])?[ \t]*$"
)
_PRAGMA_RE = re.compile(r"#\s*pragma\s+([A-Za-z_][A-Za-z0-9_]*)")
#: The single supported ARMCC pragma: exact standalone form, no continuation,
#: optional preserved trailing comment, no extra tokens.
_NO_SEMIHOSTING_CORE_RE = re.compile(
    r"#[ \t]*pragma[ \t]+import[ \t]*\([ \t]*__use_no_semihosting[ \t]*\)"
)
_NO_SEMIHOSTING_RE = re.compile(
    r"#[ \t]*pragma[ \t]+import[ \t]*\([ \t]*__use_no_semihosting[ \t]*\)"
    r"[ \t]*(?:(?://[^\r\n]*)|(?:/\*.*?\*/[ \t]*))*"
)
_NO_SEMIHOSTING_SPEC = "nosys.specs"

#: Storage/declaration forms that never describe a placed or aligned object.
_FORBIDDEN_DECLARATION_WORDS = frozenset({"extern", "typedef", "register", "auto"})
#: Known 32-bit scalar prototypes for the MSP setter (ARM AAPCS r0).  Any
#: other spelling (float, double, a struct/pointer typedef, unknown alias)
#: stays an explicit blocker instead of an assumed width.
_MSP_PARAMETER_RE = re.compile(
    r"[ \t]*(uint32_t|u32|unsigned[ \t]+int|unsigned[ \t]+long)"
    r"[ \t]+([A-Za-z_][A-Za-z0-9_]*)[ \t]*"
)


def pragma_is_supported(evidence: str) -> bool:
    """Whether inspection evidence is the one supported no-semihosting pragma.

    The planner uses this to reconcile the inspection's unconditional
    ``ARMCC_UNSUPPORTED_PRAGMA`` finding with the exact directive the
    token-aware rule rewrites; every other import/pragma keeps its blocker.
    """
    return _NO_SEMIHOSTING_RE.fullmatch(evidence.strip()) is not None


@dataclass(frozen=True)
class SourceScan:
    """Result of scanning one included C/C++ source."""

    path: str
    language: str
    before: bytes
    after: bytes
    rule_ids: tuple[str, ...]
    fixed_sections: tuple[FixedSectionRequirement, ...]
    blockers: tuple[MigrationBlocker, ...]
    ignored: tuple[IgnoredObservation, ...]
    #: Exact bytes of quoted-include dependencies used for symbolic values:
    #: ``(portable path, sha256, size)``.  Empty when no rule needed a macro.
    dependencies: tuple[tuple[str, str, int], ...] = ()
    #: Explicit linker specs requested by a rewritten directive.
    link_specs: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Placement:
    """A parsed absolute-placement declaration candidate."""

    path: str
    line: int
    column: int
    symbol: str
    address: int
    section: str
    evidence: str
    start: int
    end: int


@dataclass(frozen=True)
class _FileScan:
    scan: SourceScan
    placements: tuple[_Placement, ...]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _cap(text: str) -> str:
    return text[:MAX_EVIDENCE_CODEPOINTS]


def _line_text(text: str, position: int) -> str:
    start = text.rfind("\n", 0, position) + 1
    end = text.find("\n", position)
    if end == -1:
        end = len(text)
    return text[start:end].strip()


class _Scanner:
    """Single-pass lexical scanner producing rewrites, blockers, and placements."""

    def __init__(self, text: str, path: str, language: str, symbols=None) -> None:
        self.text = text
        self.n = len(text)
        self.path = path
        self.language = language
        self.symbols = symbols
        self.i = 0
        self.line = 1
        self.column = 1
        self.rewrites: list[tuple[int, int, str, str]] = []  # start, end, replacement, rule
        self.blockers: list[MigrationBlocker] = []
        self.ignored: list[IgnoredObservation] = []
        self.placements: list[dict] = []  # raw candidates
        self.link_specs: list[str] = []

    # -- position bookkeeping -------------------------------------------------

    def _advance(self, count: int) -> None:
        segment = self.text[self.i : self.i + count]
        newlines = segment.count("\n")
        if newlines:
            self.line += newlines
            last = segment.rfind("\n")
            self.column = len(segment) - last
        else:
            self.column += count
        self.i += count

    def _skip_hws(self, chars: str = _HWS) -> None:
        index = self.i
        while index < self.n and self.text[index] in chars:
            index += 1
        self._advance(index - self.i)

    def _peek_non_ws(self, chars: str = _NEWLINE_SKIP) -> str:
        index = self.i
        while index < self.n and self.text[index] in chars:
            index += 1
        return self.text[index] if index < self.n else ""

    def _balanced_end(self, open_index: int) -> int:
        """Index just past the balanced ``(`` group, ignoring comments/strings."""
        return _balanced_lexical(self.text, open_index, self.n, "(", ")")

    def _balanced_braces(self, open_index: int) -> int:
        return _balanced_lexical(self.text, open_index, self.n, "{", "}")

    def _blocker(self, code: str, position: int, message: str) -> None:
        self.blockers.append(
            MigrationBlocker(
                code,
                code,
                self.path,
                self._line_of(position),
                self._column_of(position),
                _cap(_line_text(self.text, position)),
                message,
            )
        )

    def _ignored_obs(self, rule_id: str, position: int) -> None:
        self.ignored.append(
            IgnoredObservation(
                rule_id,
                self.path,
                self._line_of(position),
                self._column_of(position),
                _cap(_line_text(self.text, position)),
            )
        )

    def _line_of(self, position: int) -> int:
        return 1 + self.text.count("\n", 0, position)

    def _column_of(self, position: int) -> int:
        return position - (self.text.rfind("\n", 0, position) + 1) + 1

    # -- main loop ------------------------------------------------------------

    def run(self) -> None:
        while self.i < self.n:
            char = self.text[self.i]
            if char == "\n":
                self._advance(1)
            elif char == "/" and self.text[self.i + 1 : self.i + 2] in ("/", "*"):
                self._skip_comment()
            elif char == '"':
                self._skip_quoted('"')
            elif char == "'":
                self._skip_quoted("'")
            elif char == "#":
                self._handle_directive()
            elif char.isalpha() or char == "_":
                self._handle_identifier()
            else:
                self._advance(1)

    def _skip_comment(self) -> None:
        if self.text[self.i + 1] == "/":
            # A backslash-spliced // comment owns every continuation line;
            # otherwise a fake #define/__at on the next line would be treated
            # as code.
            end = self.i + 2
            while True:
                newline = self.text.find("\n", end)
                if newline == -1:
                    end = self.n
                    break
                if self.text[newline - 1] == "\\" or (
                    newline > 1
                    and self.text[newline - 1] == "\r"
                    and self.text[newline - 2] == "\\"
                ):
                    end = newline + 1
                    continue
                end = newline
                break
            self._advance(end - self.i)
        else:
            end = self.text.find("*/", self.i + 2)
            self._advance(self.n - self.i if end == -1 else end + 2 - self.i)

    def _skip_quoted(self, quote: str) -> None:
        index = self.i + 1
        while index < self.n:
            char = self.text[index]
            if char == "\\":
                index += 2
                continue
            if char == quote or char == "\n":
                index += 1
                break
            index += 1
        self._advance(index - self.i)

    def _skip_raw_string(self, start: int) -> None:
        """Skip a C++ raw string ``R"delim( ... )delim"`` starting at ``start``."""
        index = start + 2  # after R"
        while index < self.n and self.text[index] not in "()\r\n\t \"\\":
            index += 1
        if index >= self.n or self.text[index] != "(":
            # Not a raw string after all: rewind to after R and continue.
            self._advance(start + 1 - self.i)
            return
        delim = self.text[start + 2 : index]
        close = self.text.find(")" + delim + '"', index + 1)
        if close == -1:
            close = self.n
        else:
            close = close + 2 + len(delim)
        self._advance(close - self.i)

    def _handle_directive(self) -> None:
        line_start = self.text.rfind("\n", 0, self.i) + 1
        if self.text[line_start : self.i].strip(" \t"):
            self._advance(1)  # '#' mid-line: ordinary character
            return
        position = self.i
        # Classify the first physical line of the directive.
        line_end = self.text.find("\n", self.i)
        if line_end == -1:
            line_end = self.n
        directive_end = line_end
        if line_end > self.i and self.text[line_end - 1] == "\r":
            directive_end = line_end - 1
        match = _PRAGMA_RE.match(self.text, self.i, line_end)
        if match is not None:
            token = match.group(1)
            rest = self.text[match.end() : line_end].lstrip(" \t")
            rest_token = rest.split(None, 1)[0] if rest else ""
            first_line = self.text[self.i : directive_end]
            continued = first_line.rstrip().endswith("\\")
            if token.startswith("import"):
                if (
                    not continued
                    and _NO_SEMIHOSTING_RE.fullmatch(first_line) is not None
                ):
                    # Remove exactly the directive span: a preserved trailing
                    # comment, the CR of a CRLF pair, and the newline all stay,
                    # so diagnostics keep their original line and bytes.
                    core = _NO_SEMIHOSTING_CORE_RE.match(
                        self.text, self.i, directive_end
                    )
                    assert core is not None
                    self.rewrites.append(
                        (self.i, core.end(), "", "ARMCC_NO_SEMIHOSTING_PRAGMA")
                    )
                    if _NO_SEMIHOSTING_SPEC not in self.link_specs:
                        self.link_specs.append(_NO_SEMIHOSTING_SPEC)
                else:
                    self._blocker(
                        "ARMCC_PRAGMA_UNSUPPORTED",
                        position,
                        "unsupported ARMCC pragma",
                    )
            elif (token == "arm" and rest_token == "section") or token.startswith("O"):
                self._blocker(
                    "ARMCC_PRAGMA_UNSUPPORTED", position, "unsupported ARMCC pragma"
                )
        # Skip the whole directive including line continuations.
        index = self.i
        while index < self.n:
            if self.text[index] == "\\" and self.text[index + 1 : index + 2] == "\n":
                index += 2
                continue
            if self.text[index] == "\n":
                index += 1
                break
            index += 1
        self._advance(index - self.i)

    def _handle_identifier(self) -> None:
        start = self.i
        index = self.i
        while index < self.n and (self.text[index].isalnum() or self.text[index] == "_"):
            index += 1
        token = self.text[start:index]
        self._advance(index - start)
        if token == "__irq":
            end = self.i
            while end < self.n and self.text[end] in _HWS:
                end += 1
            self.rewrites.append((start, end, "", "ARMCC_IRQ_QUALIFIER"))
        elif token == "__nop":
            self._maybe_intrinsic(start, "__NOP", "ARMCC_INTRINSIC_NOP")
        elif token == "__wfi":
            self._maybe_intrinsic(start, "__WFI", "ARMCC_INTRINSIC_WFI")
        elif token == "__asm":
            self._classify_asm(start)
        elif token == "__at":
            self._maybe_at_placement(start)
        elif token == "__align":
            self._classify_align(start)
        elif token == "__attribute__":
            self._classify_attribute(start)
        elif token == "R" and self.language == "cxx" and self.i < self.n and self.text[self.i] == '"':
            self._skip_raw_string(start)

    def _maybe_intrinsic(self, start: int, replacement: str, rule: str) -> None:
        index = self.i
        while index < self.n and self.text[index] in _HWS:
            index += 1
        if index < self.n and self.text[index] == "(":
            self.rewrites.append((start, self.i, replacement, rule))

    # -- inline/naked assembly ------------------------------------------------

    def _classify_asm(self, start: int) -> None:
        next_char = self._peek_non_ws()
        if next_char == "{":
            self._blocker("ARMCC_INLINE_ASSEMBLY_UNSUPPORTED", start, "brace-form inline assembly")
            return
        if next_char == "(":
            index = self.i
            while index < self.n and self.text[index] in _NEWLINE_SKIP:
                index += 1
            cursor = index + 1
            while cursor < self.n and self.text[cursor] in _NEWLINE_SKIP:
                cursor += 1
            if cursor < self.n and self.text[cursor] == '"':
                self._ignored_obs("ARMCC_COMPATIBLE_ASM", start)
                return
            self._blocker(
                "ARMCC_INLINE_ASSEMBLY_UNSUPPORTED",
                start,
                "inline assembly statement expression",
            )
            return
        prefix = self.text[self.text.rfind("\n", 0, start) + 1 : start]
        if self.language != "c" or prefix.strip(" \t"):
            # Only a plain file-scope ``__asm void ...`` definition is a
            # supported wrapper; storage classes or same-line prefixes stay
            # explicit blockers rather than being silently dropped.
            self._blocker(
                "ARMCC_INLINE_ASSEMBLY_UNSUPPORTED",
                start,
                "ARMCC __asm function declaration or body",
            )
            return
        parsed = self._parse_naked_function(self.i)
        if parsed is None:
            self._blocker(
                "ARMCC_INLINE_ASSEMBLY_UNSUPPORTED",
                start,
                "ARMCC __asm function declaration or body",
            )
            return
        end, replacement = parsed
        self.rewrites.append((start, end, replacement, "ARMCC_NAKED_ASM_FUNCTION"))
        self._advance(end - self.i)

    def _skip_ws(self, index: int) -> int:
        while index < self.n and self.text[index] in _NEWLINE_SKIP:
            index += 1
        return index

    def _read_identifier(self, index: int) -> tuple[str, int] | None:
        if index >= self.n or not (self.text[index].isalpha() or self.text[index] == "_"):
            return None
        cursor = index + 1
        while cursor < self.n and (
            self.text[cursor].isalnum() or self.text[cursor] == "_"
        ):
            cursor += 1
        return self.text[index:cursor], cursor

    def _parse_naked_function(self, index: int) -> tuple[int, str] | None:
        """Parse one exact supported ``__asm void`` wrapper, else ``None``.

        Only ``void name(void)``/``void name()`` with ``WFI``/``CPSID I``/
        ``CPSIE I`` plus an explicit ``BX LR``/``BX R14``, and
        ``void name(<known 32-bit scalar>)`` with ``MSR MSP, R0`` plus the same
        explicit return, are supported.  Comments between prototype tokens are
        ambiguous and rejected; body comments are preserved verbatim.
        """
        cursor = self._skip_ws(index)
        word = self._read_identifier(cursor)
        if word is None or word[0] != "void":
            return None
        cursor = self._skip_ws(word[1])
        name = self._read_identifier(cursor)
        if name is None:
            return None
        function_name, cursor = name
        cursor = self._skip_ws(cursor)
        if cursor >= self.n or self.text[cursor] != "(":
            return None
        params_end = self._balanced_end(cursor)
        if params_end == -1:
            return None
        params = self.text[cursor + 1 : params_end - 1]
        if "\n" in params or "\r" in params:
            return None
        stripped = params.strip()
        if stripped in ("", "void"):
            needs_parameter = False
        elif _MSP_PARAMETER_RE.fullmatch(params) is not None:
            needs_parameter = True
        else:
            return None
        cursor = self._skip_ws(params_end)
        if cursor >= self.n or self.text[cursor] != "{":
            return None
        body_end = self._balanced_braces(cursor)
        if body_end == -1:
            return None
        body = self.text[cursor + 1 : body_end - 1]
        parsed = _naked_instructions(body, needs_parameter)
        if parsed is None:
            return None
        instructions, comments = parsed
        if not self._line_tail_is_trivia(body_end):
            return None
        newline = (
            "\r\n"
            if "\r\n" in self.text[index:body_end]
            or self.text[body_end : body_end + 2] == "\r\n"
            else "\n"
        )
        lines = [
            f"__attribute__((naked)) void {function_name}({params.strip()})",
            "{",
            f'    __asm volatile ("{instructions}");',
        ]
        for comment in comments:
            for line in comment.splitlines() or [""]:
                lines.append("    " + line.rstrip("\r"))
        lines.append("}")
        return body_end, newline.join(lines)

    def _line_tail_is_trivia(self, index: int) -> bool:
        """Whether only whitespace/comments remain on the closing-brace line."""
        while index < self.n:
            char = self.text[index]
            if char in " \t\r":
                index += 1
            elif char == "\n":
                return True
            elif char == "/" and self.text[index + 1 : index + 2] == "/":
                return True
            elif char == "/" and self.text[index + 1 : index + 2] == "*":
                end = self.text.find("*/", index + 2)
                if end == -1:
                    return False
                index = end + 2
            else:
                return False
        return True

    # -- absolute placement and alignment -------------------------------------

    def _maybe_at_placement(self, start: int) -> None:
        index = self.i
        while index < self.n and self.text[index] in _HWS:
            index += 1
        if index >= self.n or self.text[index] != "(":
            return
        end = self._balanced_end(index)
        if end == -1:
            return
        self.placements.append(
            {
                "start": start,
                "end": end,
                "expr": self.text[index + 1 : end - 1].strip(),
                "position": start,
                "kind": "at",
            }
        )

    def _classify_attribute(self, start: int) -> None:
        index = self.i
        while index < self.n and self.text[index] in _HWS:
            index += 1
        if index >= self.n or self.text[index] != "(":
            return
        end = self._balanced_end(index)
        if end == -1:
            return
        content = self.text[index + 1 : end - 1]
        if re.search(r"(?<![A-Za-z0-9_])at[ \t]*\(", content) is None:
            if "section(" in content:
                self._ignored_obs("ARMCC_GCC_SECTION_ATTRIBUTE", start)
            return
        expression = _extract_at_expression(content)
        self.placements.append(
            {
                "start": start,
                "end": end,
                "expr": expression,
                "position": start,
                "kind": "attribute",
            }
        )

    def _classify_align(self, start: int) -> None:
        if self.language != "c":
            self._align_blocker(start, "ARMCC __align is supported only in C sources")
            return
        index = self.i
        while index < self.n and self.text[index] in _HWS:
            index += 1
        if index >= self.n or self.text[index] != "(":
            self._align_blocker(start, "uncertain __align grammar")
            return
        end = self._balanced_end(index)
        if end == -1:
            self._align_blocker(start, "uncertain __align grammar")
            return
        expression = self.text[index + 1 : end - 1].strip()
        if "\n" in expression or "\r" in expression:
            self._align_blocker(start, "uncertain __align grammar")
            return
        value, error = _evaluate(self.symbols, expression)
        if (
            error is not None
            or value is None
            or value < 1
            or value > MAX_ALIGNMENT
            or value & (value - 1)
        ):
            reason = (
                f" ({error})"
                if error is not None and re.search(r"[A-Za-z_]", expression)
                else ""
            )
            self._align_blocker(
                start, f"unsupported or unresolved __align bound{reason}"
            )
            return
        line_start = self.text.rfind("\n", 0, start) + 1
        line_end = self.text.find("\n", start)
        if line_end == -1:
            line_end = self.n
        spans = _line_attribute_spans(self.text, line_start, line_end)
        aligns = [span for span in spans if span[0] == "__align"]
        ats = [span for span in spans if span[0] == "__at" or (
            span[0] == "__attribute__"
            and _extract_at_expression(
                self.text[span[1] + len("__attribute__") : span[2]]
            )
            is not None
        )]
        if len(aligns) != 1 or len(ats) > 1:
            self._align_blocker(start, "conflicting alignment placement attributes")
            return
        view = _blank_spans(
            self.text,
            line_start,
            line_end,
            [s[1:] for s in spans if s[0] == "__align" or s in ats],
        )
        if "__attribute__" in view or "__at" in view or "__align" in view:
            self._align_blocker(start, "conflicting or unknown attribute combination")
            return
        declaration = _parse_declaration(view, self.symbols)
        if declaration is None:
            self._align_blocker(start, "unsupported __align declaration grammar")
            return
        self.rewrites.append(
            (start, end, f"__attribute__((aligned({value})))", "ARMCC_ALIGN_ATTRIBUTE")
        )

    def _align_blocker(self, position: int, message: str) -> None:
        self._blocker("ARMCC_ALIGN_UNSUPPORTED", position, message)


# ---------------------------------------------------------------------------
# declaration validation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Declaration:
    symbol: str
    array_expression: str | None


def _undefined_lookup(name: str) -> int:
    raise ConstantResolutionError("undefined", "no symbol context")


def _evaluate(symbols, expression: str) -> tuple[int | None, str | None]:
    """Evaluate one bounded expression; ``symbols`` may be absent (literals only)."""
    if symbols is not None:
        return symbols.evaluate(expression)
    try:
        return evaluate_integer(expression, _undefined_lookup), None
    except ConstantResolutionError as error:
        return None, error.code


def _strip_declaration_comment(text: str) -> str:
    text = text.rstrip()
    while text.endswith("*/"):
        start = text.rfind("/*")
        if start == -1:
            return text
        text = text[:start].rstrip()
    marker = text.find("//")
    if marker != -1:
        text = text[:marker].rstrip()
    return text


_DECIMAL_LITERAL_RE = re.compile(r"^[0-9]+$")
_LITERAL_ADDRESS_RE = re.compile(r"^(?:0[xX][0-9a-fA-F]+|[0-9]+)$")


def _parse_declaration(
    text: str, symbols, *, literal_bounds: bool = False
) -> _Declaration | None:
    """Parse a plain uninitialized object declaration; anything else is ``None``.

    Storage classes that never define the placed/aligned object (``extern``,
    ``typedef``, ...), zero-length arrays, pointers, initializers, functions,
    bit-fields, and multiple declarators are rejected.
    """
    cleaned = _strip_declaration_comment(text)
    if not cleaned.endswith(";"):
        return None
    cleaned = cleaned[:-1]
    match = _OBJECT_BODY_RE.match(cleaned)
    if match is None:
        return None
    words = match.group(1).split()
    if any(word in _FORBIDDEN_DECLARATION_WORDS for word in words):
        return None
    array_expression = match.group(3)
    if array_expression is not None:
        if literal_bounds:
            if _DECIMAL_LITERAL_RE.fullmatch(array_expression.strip()) is None:
                return None
        value, error = _evaluate(symbols, array_expression)
        if error is not None or value is None or value < 1 or value > MAX_UINT32:
            return None
    return _Declaration(match.group(2), array_expression)


def _extract_at_expression(content: str) -> str | None:
    """Return the expression of an exact ``((at(EXPR)))`` attribute body.

    ``content`` is the inside of the attribute's outer parentheses, so a
    canonical ``__attribute__((at(EXPR)))`` yields ``"(at(EXPR))"``.  Exactly
    one outer group and one ``at`` attribute are accepted; mixed attributes,
    extra tokens, and nested junk are never accepted.
    """
    text = content.strip()
    while text.startswith("("):
        end = _balanced_lexical(text, 0, len(text), "(", ")")
        if end == -1 or text[end:].strip():
            return None
        text = text[1 : end - 1].strip()
    if not text.startswith("at"):
        return None
    index = 2
    while index < len(text) and text[index] in _HWS:
        index += 1
    if index >= len(text) or text[index] != "(":
        return None
    end = _balanced_lexical(text, index, len(text), "(", ")")
    if end == -1 or text[end:].strip():
        return None
    expression = text[index + 1 : end - 1].strip()
    if not expression or "\n" in expression or "\r" in expression:
        return None
    return expression


def _balanced_lexical(
    text: str, index: int, limit: int, open_char: str, close_char: str
) -> int:
    """Index just past a balanced group, ignoring comments and strings."""
    depth = 0
    cursor = index
    while cursor < limit:
        char = text[cursor]
        if char in ('"', "'"):
            quote = char
            cursor += 1
            while cursor < limit:
                if text[cursor] == "\\":
                    cursor += 2
                    continue
                if text[cursor] == quote:
                    cursor += 1
                    break
                cursor += 1
            continue
        if char == "/" and text[cursor + 1 : cursor + 2] in ("/", "*"):
            if text[cursor + 1 : cursor + 2] == "/":
                end = text.find("\n", cursor + 2)
                cursor = limit if end == -1 or end > limit else end
            else:
                end = text.find("*/", cursor + 2)
                cursor = limit if end == -1 or end + 2 > limit else end + 2
            continue
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return cursor + 1
        cursor += 1
    return -1


def _line_attribute_spans(
    text: str, line_start: int, line_end: int
) -> list[tuple[str, int, int]]:
    """Lexically find ``__attribute__``/``__at``/``__align`` spans on one line."""
    spans: list[tuple[str, int, int]] = []
    index = line_start
    while index < line_end:
        char = text[index]
        if char in ('"', "'"):
            quote = char
            index += 1
            while index < line_end:
                if text[index] == "\\":
                    index += 2
                    continue
                if text[index] == quote:
                    index += 1
                    break
                index += 1
            continue
        if char == "/" and text[index + 1 : index + 2] == "/":
            break
        if char == "/" and text[index + 1 : index + 2] == "*":
            end = text.find("*/", index + 2)
            if end == -1 or end + 2 > line_end:
                break
            index = end + 2
            continue
        if char.isalpha() or char == "_":
            cursor = index + 1
            while cursor < line_end and (
                text[cursor].isalnum() or text[cursor] == "_"
            ):
                cursor += 1
            token = text[index:cursor]
            if token in ("__attribute__", "__at", "__align"):
                probe = cursor
                while probe < line_end and text[probe] in _HWS:
                    probe += 1
                if probe < line_end and text[probe] == "(":
                    close = _balanced_lexical(text, probe, line_end, "(", ")")
                    if close != -1:
                        spans.append((token, index, close))
                        index = close
                        continue
            index = cursor
            continue
        index += 1
    return spans


def _blank_spans(
    text: str, line_start: int, line_end: int, spans: list[tuple[int, int]]
) -> str:
    """Return the line text with the given spans replaced by spaces."""
    chars = list(text[line_start:line_end])
    for start, end in spans:
        for position in range(max(start, line_start) - line_start, min(end, line_end) - line_start):
            chars[position] = " "
    return "".join(chars)


def _naked_instructions(body: str, needs_parameter: bool) -> tuple[str, list[str]] | None:
    """Return exact GNU basic-asm text for one supported wrapper body.

    Every supported form is the explicit instruction followed by an explicit
    ``BX LR``/``BX R14``; Toolkit never invents a return the ARMCC source did
    not contain.  Comments are collected verbatim; anything else is a blocker.
    """
    tokens: list[str] = []
    comments: list[str] = []
    index = 0
    length = len(body)
    while index < length:
        char = body[index]
        if char in _NEWLINE_SKIP:
            index += 1
            continue
        if char == "/" and body[index + 1 : index + 2] == "/":
            end = body.find("\n", index + 2)
            end = length if end == -1 else end
            if end < length and (
                body[end - 1] == "\\"
                or (end > 1 and body[end - 1] == "\r" and body[end - 2] == "\\")
            ):
                # A spliced line comment owns the next physical line; the
                # bounds of this body would be ambiguous, so never rewrite it.
                return None
            comments.append(body[index:end].strip())
            index = end
            continue
        if char == "/" and body[index + 1 : index + 2] == "*":
            end = body.find("*/", index + 2)
            if end == -1:
                return None
            comments.append(body[index : end + 2].strip())
            index = end + 2
            continue
        if char.isalnum() or char == "_":
            cursor = index + 1
            while cursor < length and (
                body[cursor].isalnum() or body[cursor] == "_"
            ):
                cursor += 1
            tokens.append(body[index:cursor].upper())
            index = cursor
            continue
        if char == ",":
            index += 1
            continue
        return None
    upper = tokens
    returns = (
        ["BX", "LR"],
        ["BX", "R14"],
    )
    if not needs_parameter:
        if upper in (["WFI", *returns[0]], ["WFI", *returns[1]]):
            return "wfi\\n\\tbx lr", comments
        if upper in (["CPSID", "I", *returns[0]], ["CPSID", "I", *returns[1]]):
            return "cpsid i\\n\\tbx lr", comments
        if upper in (["CPSIE", "I", *returns[0]], ["CPSIE", "I", *returns[1]]):
            return "cpsie i\\n\\tbx lr", comments
        return None
    if upper in (
        ["MSR", "MSP", "R0", *returns[0]],
        ["MSR", "MSP", "R0", *returns[1]],
    ):
        return "msr msp, r0\\n\\tbx lr", comments
    return None


def _parse_placement(
    candidate: dict, text: str, symbols=None, language: str = "c"
) -> dict:
    """Validate one candidate and attach ``valid``/``symbol``/``address``/``section``."""
    expression = candidate["expr"]
    if expression is None:
        return {**candidate, "valid": False, "reason": "address"}
    if language != "c" and _LITERAL_ADDRESS_RE.match(expression) is None:
        # C++ keeps only the historically reviewed numeric literal form; new
        # symbolic forms are C-only.
        return {**candidate, "valid": False, "reason": "address"}
    address, error = _evaluate(symbols, expression)
    if error is not None:
        # Keep the bounded, stable resolution reason for symbolic expressions
        # so the blocker explains conditional/undefined/cycle/unavailable/limit
        # failures; literal grammar errors keep the legacy generic message.
        return {
            **candidate,
            "valid": False,
            "reason": "address",
            "resolution": (
                error if re.search(r"[A-Za-z_]", expression) else None
            ),
        }
    if address is None or address > MAX_UINT32:
        return {**candidate, "valid": False, "reason": "address"}
    line_start = text.rfind("\n", 0, candidate["start"]) + 1
    line_end = text.find("\n", candidate["start"])
    if line_end == -1:
        line_end = len(text)
    if line_end < candidate["end"]:
        return {**candidate, "valid": False, "reason": "line"}
    spans = _line_attribute_spans(text, line_start, line_end)
    at_spans = [
        span
        for span in spans
        if span[0] == "__at"
        or (
            span[0] == "__attribute__"
            and _extract_at_expression(
                text[span[1] + len("__attribute__") : span[2]]
            )
            is not None
        )
    ]
    if len(at_spans) != 1:
        return {**candidate, "valid": False, "reason": "declaration"}
    if language == "c":
        # A reviewed fixed address is exact, so an explicit __align bound must
        # divide it.  Only the same bounded expression the alignment rule
        # accepts is considered; unresolved or invalid bounds stay that rule's
        # blocker and never make the address check guess.
        align_spans = [span for span in spans if span[0] == "__align"]
        if len(align_spans) == 1:
            content = text[
                align_spans[0][1] + len("__align") : align_spans[0][2]
            ].strip()
            align_expression = (
                content[1:-1].strip()
                if content.startswith("(") and content.endswith(")")
                else None
            )
            alignment, align_error = (
                _evaluate(symbols, align_expression)
                if align_expression
                else (None, "syntax")
            )
            if (
                align_error is None
                and alignment is not None
                and 1 <= alignment <= MAX_ALIGNMENT
                and not alignment & (alignment - 1)
                and address % alignment
            ):
                return {
                    **candidate,
                    "valid": False,
                    "reason": "alignment",
                    "resolved_address": address,
                    "alignment": alignment,
                }
    view = _blank_spans(
        text,
        line_start,
        line_end,
        [span[1:] for span in spans if span in at_spans]
        + [span[1:] for span in spans if span[0] == "__align"],
    )
    if "__attribute__" in view or "__at" in view or "__align" in view:
        return {**candidate, "valid": False, "reason": "declaration"}
    declaration = _parse_declaration(
        view, symbols, literal_bounds=language != "c"
    )
    if declaration is None:
        return {**candidate, "valid": False, "reason": "declaration"}
    return {
        **candidate,
        "valid": True,
        "symbol": declaration.symbol,
        "address": address,
        "section": f".stm32tk.abs.{address:08x}",
    }


def _placements_blocker(candidate: dict, text: str) -> MigrationBlocker:
    position = candidate["position"]
    if candidate.get("reason") == "alignment":
        message = (
            f"absolute address 0x{candidate['resolved_address']:08x} does not "
            f"satisfy __align({candidate['alignment']}); the address must be a "
            "multiple of the alignment, so adjust the address or alignment; no "
            "placement rewrite was applied for this file"
        )
    elif candidate.get("resolution"):
        message = (
            "unsupported ARMCC absolute placement grammar: address expression "
            f"could not be resolved ({candidate['resolution']})"
        )
    else:
        message = "unsupported ARMCC absolute placement grammar"
    return MigrationBlocker(
        "ARMCC_ABSOLUTE_PLACEMENT_UNSUPPORTED",
        "ARMCC_ABSOLUTE_PLACEMENT_UNSUPPORTED",
        candidate["path"],
        candidate["line"],
        candidate["column"],
        _cap(_line_text(text, position)),
        message,
    )


def _placement_blocker(placement: _Placement, text: str) -> MigrationBlocker:
    return MigrationBlocker(
        "ARMCC_ABSOLUTE_PLACEMENT_UNSUPPORTED",
        "ARMCC_ABSOLUTE_PLACEMENT_UNSUPPORTED",
        placement.path,
        placement.line,
        placement.column,
        placement.evidence,
        "unsupported ARMCC absolute placement grammar",
    )


def _scan_file(
    path: str,
    data: bytes,
    language: str,
    placements_enabled: bool = True,
    symbols=None,
) -> _FileScan:
    """Scan one source; ``placements_enabled=False`` drops every placement rewrite.

    A file containing any unsupported absolute-placement construct keeps no
    placement rewrite at all (no partial rewrite), while the other supported
    rules still produce their exact edits.
    """
    bom = data.startswith(b"\xef\xbb\xbf")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        blocker = MigrationBlocker(
            "ARMCC_SOURCE_ENCODING_UNSUPPORTED",
            "ARMCC_SOURCE_ENCODING_UNSUPPORTED",
            path,
            0,
            0,
            "",
            "source encoding is not UTF-8; convert this file to UTF-8 outside Toolkit (the separate normalize-source-comments skill can preview and copy a reviewed comment-only UTF-8 file set), verify the bytes, then rerun inspect -> preflight -> plan after blockers and prerequisites are resolved; no file was written",
        )
        return _FileScan(
            SourceScan(path, language, data, data, (), (), (blocker,), ()),
            (),
        )

    provider = symbols.for_source(path, text) if symbols is not None else None
    scanner = _Scanner(text, path, language, provider)
    scanner.run()

    placements: list[_Placement] = []
    seen_address_symbol: set[tuple[int, str]] = set()
    seen_address: set[int] = set()
    invalid: list[dict] = []
    for candidate in scanner.placements:
        candidate["path"] = path
        candidate["line"] = scanner._line_of(candidate["position"])
        candidate["column"] = scanner._column_of(candidate["position"])
        parsed = _parse_placement(candidate, text, provider, language)
        if not parsed["valid"]:
            invalid.append(parsed)
            continue
        key = (parsed["address"], parsed["symbol"])
        if key in seen_address_symbol or parsed["address"] in seen_address:
            invalid.append(parsed)
            continue
        seen_address_symbol.add(key)
        seen_address.add(parsed["address"])
        placements.append(
            _Placement(
                path=path,
                line=parsed["line"],
                column=parsed["column"],
                symbol=parsed["symbol"],
                address=parsed["address"],
                section=parsed["section"],
                evidence=_cap(_line_text(text, parsed["position"])),
                start=parsed["start"],
                end=parsed["end"],
            )
        )

    fixed_sections: list[FixedSectionRequirement] = []
    if placements_enabled and not invalid:
        for placement in placements:
            fixed_sections.append(
                FixedSectionRequirement(
                    placement.section,
                    placement.address,
                    path,
                    placement.line,
                    placement.symbol,
                )
            )
            scanner.rewrites.append(
                (
                    placement.start,
                    placement.end,
                    f'__attribute__((section("{placement.section}"), used))',
                    "ARMCC_ABSOLUTE_PLACEMENT",
                )
            )
    if invalid:
        for candidate in invalid:
            scanner.blockers.append(_placements_blocker(candidate, text))
    if not placements_enabled:
        for placement in placements:
            scanner.blockers.append(_placement_blocker(placement, text))

    rewrites = sorted(scanner.rewrites, key=lambda item: item[0])
    parts: list[str] = []
    cursor = 0
    rule_order: list[str] = []
    seen_rules: set[str] = set()
    for start, end, replacement, rule in rewrites:
        if start < cursor:
            raise AssertionError("overlapping rewrite spans")
        parts.append(text[cursor:start])
        parts.append(replacement)
        cursor = end
        if rule not in seen_rules:
            seen_rules.add(rule)
            rule_order.append(rule)
    parts.append(text[cursor:])
    after_text = "".join(parts)
    after = (b"\xef\xbb\xbf" + after_text.encode("utf-8")) if bom else after_text.encode("utf-8")

    scan = SourceScan(
        path,
        language,
        data,
        after,
        tuple(rule_order),
        tuple(sorted(fixed_sections, key=lambda s: (s.address, s.section, s.source_path, s.line, s.symbol))),
        tuple(sorted(scanner.blockers, key=lambda b: (b.path, b.line, b.column, b.code, b.rule_id))),
        tuple(sorted(scanner.ignored, key=lambda o: (o.path, o.line, o.column, o.rule_id))),
        tuple(provider.dependencies()) if provider is not None else (),
        tuple(scanner.link_specs),
    )
    return _FileScan(scan, tuple(placements))


def scan_sources(entries: list[tuple[str, bytes, str]], symbols=None) -> tuple[SourceScan, ...]:
    """Scan included C/C++ sources and enforce cross-file placement uniqueness.

    A section address reused by declarations in different files blocks the
    later declarations' file (no placement rewrite there) while keeping the
    first declaration; the plan still reports every patch and every blocker.
    """
    total = 0
    for path, data, language in entries:
        if len(data) > SCAN_FILE_LIMIT:
            raise MigrationPlanError(
                "MIGRATION_LIMIT_EXCEEDED",
                "source file exceeds the per-file scan limit",
                {"scope": "file", "limitBytes": SCAN_FILE_LIMIT},
            )
        total += len(data)
        if total > SCAN_TOTAL_LIMIT:
            raise MigrationPlanError(
                "MIGRATION_LIMIT_EXCEEDED",
                "aggregate source size exceeds the scan limit",
                {"scope": "aggregate", "limitBytes": SCAN_TOTAL_LIMIT},
            )

    results = [
        _scan_file(path, data, language, symbols=symbols)
        for path, data, language in entries
    ]

    placements: list[tuple[int, str, int, int]] = []
    for index, result in enumerate(results):
        for placement in result.placements:
            placements.append((placement.address, placement.symbol, index, placement.line))

    offenders: set[int] = set()
    first_address: dict[int, tuple[str, int]] = {}
    seen_pairs: set[tuple[int, str]] = set()
    for address, symbol, index, line in sorted(
        placements, key=lambda item: (item[0], results[item[2]].scan.path, item[3], item[1])
    ):
        if address in first_address:
            offenders.add(index)
        else:
            first_address[address] = (results[index].scan.path, index)
        pair = (address, symbol)
        if pair in seen_pairs:
            offenders.add(index)
        seen_pairs.add(pair)

    if offenders:
        for index in sorted(offenders):
            path, data, language = entries[index]
            rescanned = _scan_file(
                path, data, language, placements_enabled=False, symbols=symbols
            )
            results[index] = rescanned

    return tuple(result.scan for result in results)
