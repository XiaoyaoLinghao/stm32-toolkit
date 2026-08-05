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

from stm32_toolkit.migration.model import (
    FixedSectionRequirement,
    IgnoredObservation,
    MigrationBlocker,
    MigrationPlanError,
)

SCAN_FILE_LIMIT = 8 * 1024 * 1024
SCAN_TOTAL_LIMIT = 64 * 1024 * 1024
MAX_EVIDENCE_CODEPOINTS = 200

_SUPPORTED_LANGUAGES = ("c", "cxx")
_HWS = " \t"
_NEWLINE_SKIP = " \t\r\n"

_ADDRESS_RE = re.compile(r"^(0[xX][0-9a-fA-F]+|\d+)$")
# <type-and-qualifiers> <identifier>[<decimal-count>]? ; with only horizontal
# whitespace and an optional trailing comment after the semicolon.
_DECLARATION_RE = re.compile(
    r"^[ \t]*((?:[A-Za-z_][A-Za-z0-9_]*[ \t]+)+)"
    r"([A-Za-z_][A-Za-z0-9_]*)[ \t]*"
    r"(?:\[[ \t]*([0-9]+)[ \t]*\])?[ \t]*;[ \t]*"
    r"(?:(?://[^\r\n]*)|(?:/\*.*?\*/)[ \t]*)*$"
)
_AT_ATTRIBUTE_RE = re.compile(
    r"^[ \t]*\([ \t]*at[ \t]*\([ \t]*([0-9a-fA-FxX]+)[ \t]*\)[ \t]*\)[ \t]*$"
)
_PRAGMA_RE = re.compile(r"#\s*pragma\s+([A-Za-z_][A-Za-z0-9_]*)")


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

    def __init__(self, text: str, path: str, language: str) -> None:
        self.text = text
        self.n = len(text)
        self.path = path
        self.language = language
        self.i = 0
        self.line = 1
        self.column = 1
        self.rewrites: list[tuple[int, int, str, str]] = []  # start, end, replacement, rule
        self.blockers: list[MigrationBlocker] = []
        self.ignored: list[IgnoredObservation] = []
        self.placements: list[dict] = []  # raw candidates

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
        """Index just past the balanced ``(`` group starting at ``open_index``."""
        depth = 0
        index = open_index
        while index < self.n:
            char = self.text[index]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return index + 1
            index += 1
        return -1

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
            end = self.text.find("\n", self.i + 2)
            self._advance(self.n - self.i if end == -1 else end - self.i)
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
        match = _PRAGMA_RE.match(self.text, self.i, line_end)
        if match is not None:
            token = match.group(1)
            rest = self.text[match.end() : line_end].lstrip(" \t")
            rest_token = rest.split(None, 1)[0] if rest else ""
            if (token == "arm" and rest_token == "section") or token.startswith(
                "import"
            ) or token.startswith("O"):
                self._blocker("ARMCC_PRAGMA_UNSUPPORTED", position, "unsupported ARMCC pragma")
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
        self._blocker(
            "ARMCC_INLINE_ASSEMBLY_UNSUPPORTED", start, "ARMCC __asm function declaration or body"
        )

    def _maybe_at_placement(self, start: int) -> None:
        index = self.i
        while index < self.n and self.text[index] in _HWS:
            index += 1
        if index >= self.n or self.text[index] != "(":
            return
        end = self._balanced_end(index)
        if end == -1:
            return
        raw = self.text[index + 1 : end - 1].strip()
        self.placements.append(
            {
                "start": start,
                "end": end,
                "raw_address": raw,
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
        if "at(" not in content:
            if "section(" in content:
                self._ignored_obs("ARMCC_GCC_SECTION_ATTRIBUTE", start)
            return
        match = _AT_ATTRIBUTE_RE.match(content)
        self.placements.append(
            {
                "start": start,
                "end": end,
                "raw_address": match.group(1) if match is not None else None,
                "position": start,
                "kind": "attribute",
            }
        )


# ---------------------------------------------------------------------------
# declaration validation
# ---------------------------------------------------------------------------


def _parse_placement(candidate: dict, text: str) -> dict:
    """Validate one candidate and attach ``valid``/``symbol``/``address``/``section``."""
    raw = candidate["raw_address"]
    if raw is None or _ADDRESS_RE.match(raw) is None:
        return {**candidate, "valid": False, "reason": "address"}
    address = int(raw, 16) if raw.lower().startswith("0x") else int(raw, 10)
    if address > 0xFFFFFFFF:
        return {**candidate, "valid": False, "reason": "address"}
    line_end = text.find("\n", candidate["start"])
    if line_end == -1:
        line_end = len(text)
    if line_end < candidate["end"]:
        return {**candidate, "valid": False, "reason": "line"}
    rest = text[candidate["end"] : line_end].rstrip("\r")
    match = _DECLARATION_RE.match(rest)
    if match is None:
        return {**candidate, "valid": False, "reason": "declaration"}
    symbol = match.group(2)
    return {
        **candidate,
        "valid": True,
        "symbol": symbol,
        "address": address,
        "section": f".stm32tk.abs.{address:08x}",
    }


def _placements_blocker(candidate: dict, text: str) -> MigrationBlocker:
    position = candidate["position"]
    return MigrationBlocker(
        "ARMCC_ABSOLUTE_PLACEMENT_UNSUPPORTED",
        "ARMCC_ABSOLUTE_PLACEMENT_UNSUPPORTED",
        candidate["path"],
        candidate["line"],
        candidate["column"],
        _cap(_line_text(text, position)),
        "unsupported ARMCC absolute placement grammar",
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
            "source encoding is not UTF-8",
        )
        return _FileScan(
            SourceScan(path, language, data, data, (), (), (blocker,), ()),
            (),
        )

    scanner = _Scanner(text, path, language)
    scanner.run()

    placements: list[_Placement] = []
    seen_address_symbol: set[tuple[int, str]] = set()
    seen_address: set[int] = set()
    invalid: list[dict] = []
    for candidate in scanner.placements:
        candidate["path"] = path
        candidate["line"] = scanner._line_of(candidate["position"])
        candidate["column"] = scanner._column_of(candidate["position"])
        parsed = _parse_placement(candidate, text)
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
    )
    return _FileScan(scan, tuple(placements))


def scan_sources(entries: list[tuple[str, bytes, str]]) -> tuple[SourceScan, ...]:
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

    results = [_scan_file(path, data, language) for path, data, language in entries]

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
            rescanned = _scan_file(path, data, language, placements_enabled=False)
            results[index] = rescanned

    return tuple(result.scan for result in results)
