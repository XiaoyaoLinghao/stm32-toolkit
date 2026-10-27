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
    CAUSE_ENCODING,
    CAUSE_PATH,
    MAX_UINT32,
    ConstantResolutionError,
    evaluate_integer,
)
from stm32_toolkit.migration.model import (
    BLOCKER_HINT_DEPENDENCY_ENCODING,
    BLOCKER_HINT_DEPENDENCY_PATH,
    BLOCKER_HINT_WFI_MISSING_RETURN,
    FixedSectionRequirement,
    IgnoredObservation,
    MigrationBlocker,
    MigrationPlanError,
    WfiReturn,
)
from stm32_toolkit.migration.source_intent import (
    WFI_NORMAL_BODY,
    WFI_RETURN_RULE_ID,
    normalize_wfi_returns,
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

#: Identifier token that cannot start inside a numeric literal (so the ``x``
#: in ``0x100000000`` and integer-suffix letters are not symbolic).
_SYMBOLIC_RE = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z_][A-Za-z0-9_]*")

#: Storage/declaration forms that never describe a placed or aligned object.
_FORBIDDEN_DECLARATION_WORDS = frozenset({"extern", "typedef", "register", "auto"})
#: Known 32-bit scalar prototypes for the MSP setter (ARM AAPCS r0).  Any
#: other spelling (float, double, a struct/pointer typedef, unknown alias)
#: stays an explicit blocker instead of an assumed width.
_MSP_PARAMETER_RE = re.compile(
    r"[ \t]*(uint32_t|u32|unsigned[ \t]+int|unsigned[ \t]+long)"
    r"[ \t]+([A-Za-z_][A-Za-z0-9_]*)[ \t]*"
)

#: C++ raw-string encoding prefixes accepted immediately before the quote.
_RAW_STRING_PREFIXES = ("u8R", "uR", "UR", "LR", "R")


def _raw_string_quote(text: str, limit: int, start: int) -> int | None:
    """Opening-quote index of a C++ raw literal whose prefix starts at ``start``."""
    if start > 0 and (text[start - 1].isalnum() or text[start - 1] == "_"):
        return None
    for prefix in _RAW_STRING_PREFIXES:
        end = start + len(prefix)
        if end < limit and text[start:end] == prefix and text[end] == '"':
            return end
    return None


def _raw_string_end(text: str, limit: int, quote: int) -> int:
    """End index of a raw literal whose opening quote is ``quote``.

    Returns ``quote`` when the text is not actually a raw literal, so the
    caller can keep its ordinary quoted-literal handling.
    """
    index = quote + 1
    while index < limit and text[index] not in "()\r\n\t \"\\":
        index += 1
    if index >= limit or text[index] != "(":
        return quote
    delimiter = text[quote + 1 : index]
    close = text.find(")" + delimiter + '"', index + 1)
    return limit if close == -1 else close + 2 + len(delimiter)


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
class _WfiDefinition:
    """One lexically detected ``__asm void name`` definition candidate.

    ``eligible`` is true only for a plain unconditional file-scope
    zero-argument definition whose body is WFI alone.  ``reason`` is a stable
    bounded token (``prefix``/``conditional``/``nested``/``parameters``/
    ``body``/``explicitReturn``/``nonWfi``/``language``) and is empty for an
    eligible candidate.
    """

    path: str
    function: str
    line: int
    eligible: bool
    reason: str


@dataclass(frozen=True)
class _FileScan:
    scan: SourceScan
    placements: tuple[_Placement, ...]
    wfi_definitions: tuple[_WfiDefinition, ...] = ()


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

    def __init__(
        self,
        text: str,
        path: str,
        language: str,
        symbols=None,
        wfi_functions: frozenset[str] = frozenset(),
    ) -> None:
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
        #: Function names explicitly selected for the WFI normal-return choice.
        self.wfi_functions = wfi_functions
        self.wfi_definitions: list[_WfiDefinition] = []
        #: Lexical file scope: brace depth of ordinary code (directives,
        #: comments and literals never contribute) and preprocessor
        #: conditional nesting of real directives.
        self.brace_depth = 0
        self.conditional_depth = 0
        #: The last significant ordinary-code token, or ``None`` at file
        #: start.  Comments, whitespace and spliced newlines are trivia, so a
        #: storage class on a previous physical line is still visible.
        self._last_code_token: str | None = None
        #: Whether a real code token was seen on the current preprocessing
        #: line.  Comments, horizontal whitespace and spliced newlines are
        #: trivia and do not set it; a ``#`` is a directive only when it is
        #: still clear.
        self._line_has_code = False
        #: Set when a directive's logical prefix cannot be resolved lexically.
        #: Real conditional nesting then stays unknowable, so no later
        #: file-scope definition may be treated as plainly unconditional.
        self.directive_ambiguous = False

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

    def _blocker(
        self, code: str, position: int, message: str, diagnostic: str | None = None
    ) -> None:
        self.blockers.append(
            MigrationBlocker(
                code,
                code,
                self.path,
                self._line_of(position),
                self._column_of(position),
                _cap(_line_text(self.text, position)),
                message,
                diagnostic,
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
                self._line_has_code = False
            elif char == "\\" and self.text[self.i + 1 : self.i + 2] == "\n":
                # A spliced newline joins the next physical line, so a code
                # token already seen keeps the joined logical line non-directive.
                self._advance(2)
            elif char == "\\" and self.text[self.i + 1 : self.i + 3] == "\r\n":
                self._advance(3)
            elif char == "/" and self.text[self.i + 1 : self.i + 2] in ("/", "*"):
                self._skip_comment()
            elif char == '"':
                self._line_has_code = True
                self._last_code_token = '"literal"'
                self._skip_quoted('"')
            elif char == "'":
                self._line_has_code = True
                self._last_code_token = "'literal'"
                self._skip_quoted("'")
            elif char == "#":
                self._handle_directive()
            elif char.isalpha() or char == "_":
                self._handle_identifier()
            else:
                if char not in " \t\r\f\v":
                    self._line_has_code = True
                    if char == "{":
                        self.brace_depth += 1
                    elif char == "}":
                        self.brace_depth = max(0, self.brace_depth - 1)
                    self._last_code_token = char
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
            # A block comment is one trivia unit: neither its content nor its
            # internal newlines change the logical line's token state.
            end = self.text.find("*/", self.i + 2)
            self._advance(self.n - self.i if end == -1 else end + 2 - self.i)

    def _skip_quoted(self, quote: str) -> None:
        index = self.i + 1
        while index < self.n:
            char = self.text[index]
            if char == "\\":
                # Backslash-LF and backslash-CRLF both continue the literal;
                # a lone LF still bounds an unterminated literal.
                if self.text[index + 1 : index + 3] == "\r\n":
                    index += 3
                else:
                    index += 2
                continue
            if char == quote or char == "\n":
                index += 1
                break
            index += 1
        self._advance(index - self.i)

    def _skip_raw_string(self, quote: int) -> None:
        """Skip a C++ raw literal whose opening quote is at ``quote``."""
        end = _raw_string_end(self.text, self.n, quote)
        self._advance(end - self.i)

    def _directive_end(self, start: int) -> int:
        """Index just past the whole logical directive at ``start``.

        Comments and literals inside the directive are lexically skipped, so
        their contents and internal newlines never end the directive or start
        a new one.  Only a newline outside them terminates it; backslash
        newlines continue it.  This stays within the existing lexical bounds.
        """
        index = start
        while index < self.n:
            char = self.text[index]
            if char == "\\" and self.text[index + 1 : index + 2] == "\n":
                index += 2
                continue
            if (
                char == "\\"
                and self.text[index + 1 : index + 3] == "\r\n"
            ):
                index += 3
                continue
            if char == "/" and self.text[index + 1 : index + 2] == "/":
                newline = self.text.find("\n", index + 2)
                while newline != -1 and (
                    self.text[newline - 1] == "\\"
                    or (
                        newline > 1
                        and self.text[newline - 1] == "\r"
                        and self.text[newline - 2] == "\\"
                    )
                ):
                    newline = self.text.find("\n", newline + 1)
                if newline == -1:
                    return self.n
                index = newline
                continue
            if char == "/" and self.text[index + 1 : index + 2] == "*":
                close = self.text.find("*/", index + 2)
                index = self.n if close == -1 else close + 2
                continue
            if self.language == "cxx":
                raw_quote = _raw_string_quote(self.text, self.n, index)
                if raw_quote is not None:
                    raw_end = _raw_string_end(self.text, self.n, raw_quote)
                    if raw_end > raw_quote:
                        index = raw_end
                        continue
            if char in ('"', "'"):
                quote = char
                index += 1
                while index < self.n:
                    if self.text[index] == "\\":
                        if self.text[index + 1 : index + 3] == "\r\n":
                            index += 3
                        else:
                            index += 2
                        continue
                    if self.text[index] == quote:
                        index += 1
                        break
                    if self.text[index] == "\n":
                        break
                    index += 1
                continue
            if char == "\n":
                index += 1
                break
            index += 1
        return min(index, self.n)

    def _handle_directive(self) -> None:
        if self._line_has_code:
            # '#' after a real code token, including a token on a spliced
            # previous physical line, is an ordinary character.
            self._advance(1)
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
        # Conditional nesting is lexical file-scope evidence: a definition in a
        # conditional block cannot be proven to be the compiled definition.
        keyword = self._directive_keyword(position)
        if keyword is None:
            # An unresolvable directive prefix may hide a real conditional, so
            # later file-scope eligibility is never inferred to be plain.
            self.directive_ambiguous = True
        elif keyword in ("if", "ifdef", "ifndef"):
            self.conditional_depth += 1
        elif keyword == "endif":
            self.conditional_depth = max(0, self.conditional_depth - 1)
        # Skip the whole logical directive: comments and literals inside it are
        # one lexical unit, so a fake #pragma in a macro/comment body is never
        # scanned as a directive on its own.
        self._advance(self._directive_end(self.i) - self.i)
        self._line_has_code = False

    def _spliced_next(self, index: int) -> tuple[str, int]:
        """First character at/after ``index`` after backslash-newline splices."""
        while index < self.n:
            if self.text[index] == "\\":
                if self.text[index + 1 : index + 2] == "\n":
                    index += 2
                    continue
                if self.text[index + 1 : index + 3] == "\r\n":
                    index += 3
                    continue
            break
        return (self.text[index] if index < self.n else ""), index

    def _block_comment_end(self, index: int) -> int:
        """Index just past the ``*/`` closing a splice-aware block comment.

        Phase 2 splices before comments are recognised, so a ``/`` and ``*``
        pair, or a ``*`` and ``/`` pair, may be separated by a backslash-newline.
        """
        while index < self.n:
            char = self.text[index]
            if char == "\\":
                if self.text[index + 1 : index + 2] == "\n":
                    index += 2
                    continue
                if self.text[index + 1 : index + 3] == "\r\n":
                    index += 3
                    continue
            if char == "*":
                marker, slash = self._spliced_next(index + 1)
                if marker == "/":
                    return slash + 1
            index += 1
        return -1

    def _directive_keyword(self, position: int) -> str | None:
        """The first identifier of the directive's logical line, else ``None``.

        Preprocessor trivia between ``#`` and the keyword is normalized the
        way translation phases 2 and 3 do it: horizontal whitespace, line and
        block comments (which become one separator), and backslash-newline
        splices (LF and CRLF) are skipped.  A block comment may span physical
        lines and still leave one logical directive, a splice may split the
        keyword itself, and a splice may create a comment open (``#/`` +
        splice + ``**/if`` is ``#/**/if`` after splicing).  ``""`` is reserved
        for a genuine null directive where only trivia remains on the logical
        line.  ``None`` means the prefix cannot be resolved lexically, so a
        conditional must never be ruled out from it.
        """
        index = position + 1
        while index < self.n:
            char = self.text[index]
            if char in " \t\f\v":
                index += 1
                continue
            if char == "\r" and self.text[index + 1 : index + 2] != "\n":
                index += 1
                continue
            if char == "\\":
                if self.text[index + 1 : index + 2] == "\n":
                    index += 2
                    continue
                if self.text[index + 1 : index + 3] == "\r\n":
                    index += 3
                    continue
                return None
            if char == "/":
                # A comment delimiter may be split by a splice, so classify
                # against the next spliced character, never the next raw byte.
                marker, marker_at = self._spliced_next(index + 1)
                if marker == "/":
                    # The rest of the logical line is a comment, so no keyword
                    # follows the ``#`` (a null directive).
                    return ""
                if marker == "*":
                    close = self._block_comment_end(marker_at + 1)
                    if close == -1:
                        return None
                    index = close
                    continue
            break
        if index >= self.n or self.text[index] in "\r\n":
            # Only trivia remains on the logical line: a genuine null
            # directive hides no conditional.
            return ""
        if not (self.text[index].isalpha() or self.text[index] == "_"):
            # Unknown non-trivia punctuation after ``#`` cannot be resolved
            # lexically, and a real conditional may hide behind it, so it is
            # never treated as a harmless null directive.
            return None
        start = index
        while index < self.n:
            char = self.text[index]
            if char.isalnum() or char == "_":
                index += 1
                continue
            if char == "\\" and self.text[index + 1 : index + 2] == "\n":
                index += 2
                continue
            if char == "\\" and self.text[index + 1 : index + 3] == "\r\n":
                index += 3
                continue
            break
        return (
            self.text[start:index]
            .replace("\\\r\n", "")
            .replace("\\\n", "")
        )

    def _handle_identifier(self) -> None:
        self._line_has_code = True
        start = self.i
        index = self.i
        while index < self.n and (self.text[index].isalnum() or self.text[index] == "_"):
            index += 1
        token = self.text[start:index]
        self._advance(index - start)
        previous = self._last_code_token
        self._last_code_token = token
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
            self._classify_asm(start, previous)
        elif token == "__at":
            self._maybe_at_placement(start)
        elif token == "__align":
            self._classify_align(start)
        elif token == "__attribute__":
            self._classify_attribute(start)
        elif (
            self.language == "cxx"
            and token in _RAW_STRING_PREFIXES
            and self.i < self.n
            and self.text[self.i] == '"'
        ):
            self._skip_raw_string(self.i)

    def _maybe_intrinsic(self, start: int, replacement: str, rule: str) -> None:
        index = self.i
        while index < self.n and self.text[index] in _HWS:
            index += 1
        if index < self.n and self.text[index] == "(":
            self.rewrites.append((start, self.i, replacement, rule))

    # -- inline/naked assembly ------------------------------------------------

    def _classify_asm(
        self, start: int, previous_token: str | None = None
    ) -> None:
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
        prefix_blank = not prefix.strip(" \t")
        name_hint = self._asm_name_hint(self.i)
        candidate = (
            name_hint
            if name_hint is not None and self._asm_body_hint(self.i)
            else None
        )
        scope_reason = self._asm_scope_reason(prefix_blank, previous_token)
        if self.language != "c" or not prefix_blank:
            # Only a plain file-scope ``__asm void ...`` definition is a
            # supported wrapper; storage classes or same-line prefixes stay
            # explicit blockers rather than being silently dropped.
            self._record_wfi_definition(candidate, start, False, scope_reason or "prefix")
            self._blocker(
                "ARMCC_INLINE_ASSEMBLY_UNSUPPORTED",
                start,
                "ARMCC __asm function declaration or body",
            )
            return
        parsed = self._parse_naked_function(self.i)
        if parsed is None:
            self._record_wfi_definition(candidate, start, False, "unsupported")
            self._blocker(
                "ARMCC_INLINE_ASSEMBLY_UNSUPPORTED",
                start,
                "ARMCC __asm function declaration or body",
            )
            return
        function = candidate or parsed.name
        if parsed.replacement is None:
            # ARM assembly permits falling through into the next embedded
            # assembly function, so the source can be legitimate; its intended
            # return behaviour is still unknowable from the text.  Only an
            # exact plain WFI-only definition with a selection may become a
            # normal C return; everything else keeps the actionable blocker.
            if scope_reason is not None:
                reason = scope_reason
            elif parsed.instruction != "WFI" or parsed.needs_parameter:
                reason = "nonWfi"
            elif not parsed.wfi_eligible:
                reason = "body"
            else:
                reason = ""
            eligible = reason == ""
            self._record_wfi_definition(function, start, eligible, reason)
            if eligible and parsed.name in self.wfi_functions:
                self.rewrites.append(
                    (
                        start,
                        parsed.end,
                        self._wfi_normal_body(parsed, start),
                        WFI_RETURN_RULE_ID,
                    )
                )
                self._advance(parsed.end - self.i)
                self._last_code_token = "}"
                return
            self._blocker(
                "ARMCC_INLINE_ASSEMBLY_UNSUPPORTED",
                start,
                self._missing_return_message(parsed, scope_reason),
                # Only this exact scanner-established candidate may carry the
                # concrete wfiReturns remediation; no other embedded assembly
                # body is trusted to support that opt-in.
                BLOCKER_HINT_WFI_MISSING_RETURN if eligible else None,
            )
            return
        # An explicit BX LR/BX R14 wrapper keeps its current translation; it is
        # never eligible for the missing-return source-intent choice.
        self._record_wfi_definition(function, start, False, "explicitReturn")
        self.rewrites.append(
            (start, parsed.end, parsed.replacement, "ARMCC_NAKED_ASM_FUNCTION")
        )
        self._advance(parsed.end - self.i)
        self._last_code_token = "}"

    def _asm_scope_reason(
        self, prefix_blank: bool, previous_token: str | None
    ) -> str | None:
        """Why ``__asm`` is not a plain unconditional file-scope definition.

        Only the explicit WFI normal-return opt-in requires this evidence;
        existing explicit-return translations keep their historical scope
        handling.  ``None`` means the lexical position is plain.
        """
        if self.language != "c":
            return "language"
        if not prefix_blank:
            return "prefix"
        if self.conditional_depth > 0 or self.directive_ambiguous:
            return "conditional"
        if self.brace_depth > 0:
            return "nested"
        if previous_token not in (None, ";", "}"):
            # A storage class, attribute, or macro token on a previous
            # physical line still declares this function; a bare line break
            # never makes a prefixed function plain.
            return "prefix"
        return None

    def _asm_name_hint(self, index: int) -> str | None:
        """The declared name after ``__asm [whitespace] void [whitespace]``."""
        cursor = self._skip_ws(index)
        word = self._read_identifier(cursor)
        if word is None or word[0] != "void":
            return None
        cursor = self._skip_ws(word[1])
        name = self._read_identifier(cursor)
        return name[0] if name is not None else None

    def _asm_body_hint(self, index: int) -> bool:
        """Whether a ``{`` body follows the hinted prototype.

        A bare ``__asm void name(void);`` declaration is not a definition and
        must not make a selected definition look duplicated.
        """
        cursor = self._skip_ws(index)
        word = self._read_identifier(cursor)
        if word is None or word[0] != "void":
            return False
        cursor = self._skip_ws(word[1])
        name = self._read_identifier(cursor)
        if name is None:
            return False
        cursor = self._skip_ws(name[1])
        if cursor < self.n and self.text[cursor] == "(":
            end = self._balanced_end(cursor)
            if end == -1:
                return False
            cursor = self._skip_ws(end)
        return cursor < self.n and self.text[cursor] == "{"

    def _record_wfi_definition(
        self,
        function: str | None,
        start: int,
        eligible: bool,
        reason: str,
    ) -> None:
        """Record one definition candidate for selection reconciliation."""
        if function is None:
            return
        self.wfi_definitions.append(
            _WfiDefinition(
                self.path,
                function,
                self._line_of(start),
                eligible,
                reason,
            )
        )

    def _missing_return_message(
        self, parsed: "_NakedTranslation", scope_reason: str | None
    ) -> str:
        base = (
            f"ARMCC __asm function '{parsed.name}' ends after "
            f"'{parsed.instruction}' with no explicit return; control can "
            "fall through into the next embedded assembly function, which the "
            "ARM Compiler armcc User Guide documents as possible (section"
            " 7.30). Toolkit never invents BX LR or a CMSIS intrinsic and does"
            " not require a Keil disassembly/control-flow baseline."
        )
        if parsed.instruction == "WFI" and parsed.needs_parameter is False:
            if scope_reason is not None:
                return (
                    base
                    + " Only a plain unconditional file-scope zero-argument"
                    " WFI-only wrapper can use the wfiReturns normal-return"
                    " choice; this definition is not plain"
                    f" ({scope_reason}), so it needs a project-owned source"
                    " port."
                )
            if not parsed.wfi_eligible:
                return (
                    base
                    + " Only a body that is exactly one WFI token with at most"
                    " one trailing ';' (ordinary whitespace and comments"
                    " aside) can use the wfiReturns normal-return choice; this"
                    " body has other punctuation, so it needs a project-owned"
                    " source port."
                )
            return (
                base
                + ' Select wfiReturns=[{"path": "'
                + self.path
                + '", "function": "'
                + parsed.name
                + '"}] to convert this plain file-scope zero-argument'
                " WFI-only wrapper into ordinary non-naked C executing "
                + WFI_NORMAL_BODY
                + " and returning normally; that records requested source"
                " behaviour, not binary equivalence. Intentional"
                " fall-through needs a project-owned source port instead."
            )
        return (
            base
            + " Only a plain WFI-only wrapper can use the wfiReturns"
            " normal-return choice; '"
            + str(parsed.instruction)
            + "' is not eligible, so this needs a project-owned source port."
        )

    def _wfi_normal_body(self, parsed: "_NakedTranslation", start: int) -> str:
        """Normal non-naked C body: GNU asm WFI with memory clobber, no naked."""
        newline = (
            "\r\n"
            if "\r\n" in self.text[start : parsed.end]
            or self.text[parsed.end : parsed.end + 2] == "\r\n"
            else "\n"
        )
        lines = [
            f"void {parsed.name}({parsed.params})",
            "{",
            f"    {WFI_NORMAL_BODY}",
        ]
        for comment in parsed.comments:
            for line in comment.splitlines() or [""]:
                lines.append("    " + line.rstrip("\r"))
        lines.append("}")
        return newline.join(lines)

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

    def _parse_naked_function(self, index: int) -> "_NakedTranslation | None":
        """Parse one exact supported ``__asm void`` wrapper, else ``None``.

        Only ``void name(void)``/``void name()`` with ``WFI``/``CPSID I``/
        ``CPSIE I`` plus an explicit ``BX LR``/``BX R14``, and
        ``void name(<known 32-bit scalar>)`` with ``MSR MSP, R0`` plus the same
        explicit return, are supported.  A recognised instruction sequence
        that omits the explicit return returns a translation whose
        ``replacement`` is ``None``: the caller keeps its blocker and reports
        the missing return, it never invents one.  Comments between prototype
        tokens are ambiguous and rejected; body comments are preserved.
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
        if not self._line_tail_is_trivia(body_end):
            return None
        parsed = _naked_instructions(body, needs_parameter)
        if parsed is None:
            tokens = _naked_tokens(body, allow_semicolons=True)
            instruction = _missing_return_from_tokens(tokens, needs_parameter)
            if instruction is None:
                return None
            comments = tuple(tokens[1]) if tokens is not None else ()
            return _NakedTranslation(
                body_end,
                None,
                function_name,
                instruction,
                params.strip(),
                comments,
                needs_parameter,
                # The recognized missing-return diagnostic stays permissive so
                # legacy CPSID/MSR reporting is unchanged; only this strict
                # WFI form may become selected normal-return code.
                wfi_eligible=(
                    instruction == "WFI" and _wfi_only_body(body) is not None
                ),
            )
        instructions, comments = parsed
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
        return _NakedTranslation(
            body_end,
            newline.join(lines),
            function_name,
            None,
            params.strip(),
            tuple(comments),
            needs_parameter,
        )

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
        value, error, context, diagnostic = _evaluate(self.symbols, expression)
        if (
            error is not None
            or value is None
            or value < 1
            or value > MAX_ALIGNMENT
            or value & (value - 1)
        ):
            reason = ""
            if error is not None and _SYMBOLIC_RE.search(expression):
                reason = f" ({error})"
                if context is not None:
                    reason = f"{reason}: {context}"
            self._align_blocker(
                start,
                f"unsupported or unresolved __align bound{reason}",
                diagnostic,
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
        declaration, bound_failure, diagnostic = _parse_declaration(
            view, self.symbols
        )
        if declaration is None:
            if bound_failure is not None:
                self._align_blocker(
                    start,
                    f"__align declaration: {bound_failure}",
                    diagnostic,
                )
            else:
                self._align_blocker(start, "unsupported __align declaration grammar")
            return
        self.rewrites.append(
            (start, end, f"__attribute__((aligned({value})))", "ARMCC_ALIGN_ATTRIBUTE")
        )

    def _align_blocker(
        self, position: int, message: str, diagnostic: str | None = None
    ) -> None:
        self._blocker("ARMCC_ALIGN_UNSUPPORTED", position, message, diagnostic)


# ---------------------------------------------------------------------------
# declaration validation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Declaration:
    symbol: str
    array_expression: str | None


def _undefined_lookup(name: str) -> int:
    raise ConstantResolutionError("undefined", "no symbol context")


#: Map the trusted expression cause to the internal blocker hint.  No path,
#: message, or user-controlled text is ever inspected to make this choice.
_DIAGNOSTIC_FOR_CAUSE = {
    CAUSE_ENCODING: BLOCKER_HINT_DEPENDENCY_ENCODING,
    CAUSE_PATH: BLOCKER_HINT_DEPENDENCY_PATH,
}


def _evaluate(
    symbols, expression: str
) -> tuple[int | None, str | None, str | None, str | None]:
    """Evaluate one bounded expression; ``symbols`` may be absent (literals only).

    Returns ``(value, error_code, context, diagnostic)``.  ``context`` is the
    bounded, project-relative dependency description supplied by the symbol
    provider after a failure.  ``diagnostic`` is the trusted internal hint
    derived only from the provider's structured cause.
    """
    if symbols is not None:
        value, error = symbols.evaluate(expression)
        if error is None:
            return value, None, None, None
        describe = getattr(symbols, "failure_context", None)
        context = describe() if callable(describe) else None
        cause_of = getattr(symbols, "failure_cause", None)
        cause = cause_of() if callable(cause_of) else None
        return value, error, context, _DIAGNOSTIC_FOR_CAUSE.get(cause)
    try:
        return evaluate_integer(expression, _undefined_lookup), None, None, None
    except ConstantResolutionError as error:
        return None, error.code, None, None


def _bound_failure(
    expression: str,
    value: int | None,
    error: str | None,
    context: str | None,
) -> str:
    """Describe one unusable array bound without collapsing it into grammar.

    The bounded reason token keeps its established ``(reason)`` form; any
    dependency context is appended after the closing parenthesis so existing
    diagnostics remain a prefix of the enriched message.
    """
    bound = _cap(expression.strip())
    if error is not None:
        reason = f"array bound '{bound}' could not be resolved ({error})"
        return f"{reason}: {context}" if context is not None else reason
    return f"array bound '{bound}' is not a positive uint32 dimension ({value})"


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
) -> tuple[_Declaration | None, str | None, str | None]:
    """Parse a plain uninitialized object declaration.

    Returns ``(declaration, None, None)`` on success and ``(None, None, None)``
    for every unsupported declaration shape.  ``(None, description, hint)`` is
    reserved for a plain declaration whose array bound was rejected or could
    not be resolved, so the caller can distinguish a bound problem from
    unsupported declaration grammar.  Storage classes that never define the
    placed/aligned object (``extern``, ``typedef``, ...), zero-length arrays,
    pointers, initializers, functions, bit-fields, and multiple declarators
    are rejected as grammar.
    """
    cleaned = _strip_declaration_comment(text)
    if not cleaned.endswith(";"):
        return None, None, None
    cleaned = cleaned[:-1]
    match = _OBJECT_BODY_RE.match(cleaned)
    if match is None:
        return None, None, None
    words = match.group(1).split()
    if any(word in _FORBIDDEN_DECLARATION_WORDS for word in words):
        return None, None, None
    array_expression = match.group(3)
    if array_expression is not None:
        if literal_bounds:
            if _DECIMAL_LITERAL_RE.fullmatch(array_expression.strip()) is None:
                return None, None, None
        value, error, context, diagnostic = _evaluate(symbols, array_expression)
        if error is not None or value is None or value < 1 or value > MAX_UINT32:
            return (
                None,
                _bound_failure(array_expression, value, error, context),
                diagnostic,
            )
    return _Declaration(match.group(2), array_expression), None, None


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


@dataclass(frozen=True)
class _NakedTranslation:
    """One recognised ``__asm void`` wrapper.

    ``replacement`` is ``None`` only for a supported instruction sequence that
    omits the explicit return; ``instruction`` then names the instruction the
    body ends with so the blocker can explain the fall-through boundary.
    ``params`` is the stripped prototype parameter text, ``comments`` holds
    the verbatim body comments, and ``needs_parameter`` distinguishes the MSP
    setter from a zero-argument wrapper.
    """

    end: int
    replacement: str | None
    name: str
    instruction: str | None
    params: str = ""
    comments: tuple[str, ...] = ()
    needs_parameter: bool = False
    #: True only for the strict single-``WFI`` missing-return body the
    #: reviewed normal-return choice accepts: one ``WFI`` token with at most
    #: one trailing ``;`` and otherwise only whitespace and comments.  Legacy
    #: permissive tokenization never makes another body eligible.
    wfi_eligible: bool = False


def _naked_tokens(
    body: str, *, allow_semicolons: bool = False
) -> tuple[list[str], list[str]] | None:
    """Upper-case instruction tokens and verbatim comments, else ``None``.

    ``allow_semicolons`` is used only by the missing-return diagnostic so a
    one-line ARMCC body such as ``{ WFI; }`` can be recognised; it never
    broadens the rewritable forms.
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
        if allow_semicolons and char == ";":
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
    return tokens, comments


def _wfi_only_body(body: str) -> tuple[str, ...] | None:
    """Verbatim comments when ``body`` is exactly the reviewed WFI form.

    The normal-return selection contract is one ``WFI`` token with zero or one
    trailing ``;``; ordinary whitespace and body comments are the only other
    content.  Unlike the legacy permissive :func:`_naked_tokens` diagnostic,
    commas, extra or leading semicolons, and any other token are rejected, so
    a body such as ``WFI;;`` or ``,WFI`` never becomes eligible.  ``None``
    means the body is outside that contract.
    """
    comments: list[str] = []
    index = 0
    length = len(body)
    seen_wfi = False
    seen_semicolon = False
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
                # body bounds would be ambiguous, so never select it.
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
        if char == ";" and seen_wfi and not seen_semicolon:
            seen_semicolon = True
            index += 1
            continue
        if char.isalnum() or char == "_":
            cursor = index + 1
            while cursor < length and (
                body[cursor].isalnum() or body[cursor] == "_"
            ):
                cursor += 1
            if seen_wfi or body[index:cursor].upper() != "WFI":
                return None
            seen_wfi = True
            index = cursor
            continue
        return None
    return tuple(comments) if seen_wfi else None


def _naked_instructions(body: str, needs_parameter: bool) -> tuple[str, list[str]] | None:
    """Return exact GNU basic-asm text for one supported wrapper body.

    Every supported form is the explicit instruction followed by an explicit
    ``BX LR``/``BX R14``; Toolkit never invents a return the ARMCC source did
    not contain.  Comments are collected verbatim; anything else is a blocker.
    """
    parsed = _naked_tokens(body)
    if parsed is None:
        return None
    upper, comments = parsed
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


def _missing_return_from_tokens(
    parsed: tuple[list[str], list[str]] | None, needs_parameter: bool
) -> str | None:
    """Name the instruction of a recognised body that omits its return.

    Returns ``None`` for every other body, so unknown assembly keeps its
    generic blocker and is never described as a missing return.
    """
    if parsed is None:
        return None
    upper, _comments = parsed
    if not needs_parameter:
        if upper == ["WFI"]:
            return "WFI"
        if upper == ["CPSID", "I"]:
            return "CPSID I"
        if upper == ["CPSIE", "I"]:
            return "CPSIE I"
        return None
    if upper == ["MSR", "MSP", "R0"]:
        return "MSR MSP, R0"
    return None


def _naked_missing_return(body: str, needs_parameter: bool) -> str | None:
    """Tokenize and name one recognised body without an explicit return."""
    return _missing_return_from_tokens(
        _naked_tokens(body, allow_semicolons=True), needs_parameter
    )


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
    address, error, context, diagnostic = _evaluate(symbols, expression)
    if error is not None:
        # Keep the bounded, stable resolution reason for symbolic expressions
        # so the blocker explains conditional/undefined/cycle/unavailable/limit
        # failures, plus the project-relative dependency context when the
        # failure came from an unusable quoted include; literal grammar errors
        # keep the legacy generic message.
        symbolic = _SYMBOLIC_RE.search(expression) is not None
        return {
            **candidate,
            "valid": False,
            "reason": "address",
            "resolution": error if symbolic else None,
            "resolution_context": context if symbolic else None,
            "diagnostic": diagnostic if symbolic else None,
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
            alignment, align_error, _align_context, _align_diagnostic = (
                _evaluate(symbols, align_expression)
                if align_expression
                else (None, "syntax", None, None)
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
    declaration, bound_failure, diagnostic = _parse_declaration(
        view, symbols, literal_bounds=language != "c"
    )
    if declaration is None:
        return {
            **candidate,
            "valid": False,
            "reason": "declaration",
            "bound": bound_failure,
            "diagnostic": diagnostic,
        }
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
        resolution = (
            f"address expression could not be resolved "
            f"({candidate['resolution']})"
        )
        if candidate.get("resolution_context"):
            resolution = f"{resolution}: {candidate['resolution_context']}"
        message = f"ARMCC absolute placement: {resolution}"
    elif candidate.get("bound"):
        message = (
            "ARMCC absolute placement: "
            f"{candidate['bound']}; no placement rewrite was applied for this file"
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
        candidate.get("diagnostic"),
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
    wfi_functions: frozenset[str] = frozenset(),
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
    scanner = _Scanner(text, path, language, provider, wfi_functions)
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
    return _FileScan(
        scan,
        tuple(placements),
        tuple(
            sorted(
                scanner.wfi_definitions,
                key=lambda item: (item.path, item.line, item.function),
            )
        ),
    )


def scan_sources(
    entries: list[tuple[str, bytes, str]],
    symbols=None,
    wfi_returns: tuple[WfiReturn, ...] | None = None,
) -> tuple[SourceScan, ...]:
    """Scan included C/C++ sources and enforce cross-file placement uniqueness.

    A section address reused by declarations in different files blocks the
    later declarations' file (no placement rewrite there) while keeping the
    first declaration; the plan still reports every patch and every blocker.
    ``wfi_returns`` carries reviewed WFI normal-return selections: every
    selection must match exactly one plain unconditional file-scope
    zero-argument WFI-only definition, otherwise the request fails instead of
    being silently ignored.
    """
    choices = normalize_wfi_returns(wfi_returns)
    selected_by_path: dict[str, set[str]] = {}
    for choice in choices:
        selected_by_path.setdefault(choice.path, set()).add(choice.function)
    selected = {
        path: frozenset(functions)
        for path, functions in selected_by_path.items()
    }

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
        _scan_file(
            path,
            data,
            language,
            symbols=symbols,
            wfi_functions=selected.get(path, frozenset()),
        )
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
                path,
                data,
                language,
                placements_enabled=False,
                symbols=symbols,
                wfi_functions=selected.get(path, frozenset()),
            )
            results[index] = rescanned

    if choices:
        definitions = tuple(
            definition
            for result in results
            for definition in result.wfi_definitions
        )
        _validate_wfi_selections(choices, definitions)

    return tuple(result.scan for result in results)


def _validate_wfi_selections(
    choices: tuple[WfiReturn, ...], definitions: tuple[_WfiDefinition, ...]
) -> None:
    """Reconcile every reviewed selection with the scanned definitions.

    A selection that matches nothing, matches a name defined more than once,
    or names a definition that is not the exact plain unconditional
    file-scope zero-argument WFI-only form fails with a stable error.  No
    selection is ever silently ignored or broadened to another definition.
    """
    for choice in choices:
        in_path = [
            definition
            for definition in definitions
            if definition.path == choice.path
            and definition.function == choice.function
        ]
        anywhere = [
            definition
            for definition in definitions
            if definition.function == choice.function
        ]
        if not in_path:
            raise MigrationPlanError(
                "WFI_RETURN_UNUSED",
                "the selected WFI function was not found as a definition in"
                " the named compiled C source",
                {
                    "field": "wfiReturns",
                    "rule": "unused",
                    "path": choice.path,
                    "function": choice.function,
                },
            )
        if len(anywhere) != 1 or len(in_path) != 1:
            raise MigrationPlanError(
                "WFI_RETURN_AMBIGUOUS",
                "the selected WFI function has multiple definitions; the"
                " source-intent selection is ambiguous",
                {
                    "field": "wfiReturns",
                    "rule": "duplicateDefinition",
                    "path": choice.path,
                    "function": choice.function,
                },
            )
        definition = in_path[0]
        if not definition.eligible:
            raise MigrationPlanError(
                "WFI_RETURN_AMBIGUOUS",
                "the selected function is not a plain unconditional"
                " file-scope zero-argument WFI-only definition",
                {
                    "field": "wfiReturns",
                    "rule": definition.reason or "unsupported",
                    "path": choice.path,
                    "function": choice.function,
                    "line": definition.line,
                },
            )
