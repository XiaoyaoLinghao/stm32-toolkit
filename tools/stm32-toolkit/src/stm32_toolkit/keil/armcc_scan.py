"""Bounded read-only ARMCC source scan and framework evidence.

Receives normalized paths only; never discovers files itself. All reads are
bounded and read-only, and findings/evidence are deterministic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from stm32_toolkit.keil.model import KeilEvidence, KeilFinding, KeilInspectionError

SCAN_FILE_LIMIT = 8 * 1024 * 1024
SCAN_TOTAL_LIMIT = 64 * 1024 * 1024
MAX_EVIDENCE_CODEPOINTS = 200

_RULE_MESSAGES = {
    "ARMCC_IRQ_QUALIFIER": "ARMCC __irq qualifier",
    "ARMCC_INTRINSIC_NOP": "ARMCC __nop intrinsic call",
    "ARMCC_INTRINSIC_WFI": "ARMCC __WFI intrinsic call",
    "ARMCC_INLINE_ASSEMBLY_FUNCTION": "ARMCC __asm function declaration or body",
    "ARMCC_ABSOLUTE_PLACEMENT": "ARMCC absolute placement",
    "ARMCC_SCATTER_FILE": "non-empty scatter-file linker setting",
    "ARMCC_CUSTOM_SECTION": "ARMCC custom section",
    "ARMCC_UNSUPPORTED_PRAGMA": "unsupported ARMCC pragma",
    "ARMCC_SOURCE_ENCODING_UNSUPPORTED": "source encoding is not UTF-8; the separate normalize-source-comments skill can preview a reviewed comment-only UTF-8 copy outside the project",
}

_INCLUDE_HAL_RE = re.compile(r"stm32.*_hal\.h", re.IGNORECASE)
_INCLUDE_LL_RE = re.compile(r"stm32.*_ll_.*\.h", re.IGNORECASE)
_ATTRIBUTE_AT_RE = re.compile(r"\bat\s*\(")
_ATTRIBUTE_SECTION_RE = re.compile(r"\bsection\s*\(")
_INCLUDE_DIRECTIVE_RE = re.compile(r'#include\s*[<"]([^>"]+)[>"]')

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


@dataclass(frozen=True)
class ScanOutcome:
    findings: tuple[KeilFinding, ...]
    include_evidence: tuple[KeilEvidence, ...]
    unreadable: tuple[str, ...]
    read: tuple[str, ...]


def linker_findings(scatter_rel: str | None, linker_misc: str) -> tuple[KeilFinding, ...]:
    """Findings derived from linker settings rather than source text."""
    findings: list[KeilFinding] = []
    if scatter_rel:
        findings.append(
            KeilFinding(
                "ARMCC_SCATTER_FILE",
                "warning",
                scatter_rel,
                0,
                0,
                scatter_rel[:MAX_EVIDENCE_CODEPOINTS],
                _RULE_MESSAGES["ARMCC_SCATTER_FILE"],
            )
        )
    if "section(" in linker_misc:
        findings.append(
            KeilFinding(
                "ARMCC_CUSTOM_SECTION",
                "warning",
                scatter_rel or "",
                0,
                0,
                linker_misc.strip()[:MAX_EVIDENCE_CODEPOINTS],
                _RULE_MESSAGES["ARMCC_CUSTOM_SECTION"],
            )
        )
    return tuple(findings)


def scan_sources(files: list[tuple[str, Path, str]]) -> ScanOutcome:
    """Scan readable included C/C++/assembly files.

    ``files`` is a list of (relative path, absolute path, language) triples.
    Reads are bounded to ``SCAN_FILE_LIMIT + 1`` bytes and both the per-file
    and the aggregate limits are re-enforced on the bytes actually read, so a
    file that grows between ``stat`` and ``read`` is still rejected.
    """
    from stm32_toolkit.keil import uvprojx as _uvprojx  # lazy: avoid import cycle

    raw_findings: list[tuple[str, int, int, str, str, str]] = []
    include_items: list[tuple[str, str]] = []
    unreadable: list[str] = []
    read_paths: list[str] = []
    total = 0
    for rel, abs_path, language in files:
        try:
            size = abs_path.stat().st_size
        except FileNotFoundError:
            continue
        except NotADirectoryError:
            continue
        except OSError:
            unreadable.append(rel)
            continue
        if size > SCAN_FILE_LIMIT:
            raise KeilInspectionError(
                "KEIL_SCAN_LIMIT_EXCEEDED",
                "source file exceeds the per-file scan limit",
                {"limitBytes": SCAN_FILE_LIMIT, "scope": "file"},
            )
        if total + size > SCAN_TOTAL_LIMIT:
            raise KeilInspectionError(
                "KEIL_SCAN_LIMIT_EXCEEDED",
                "aggregate source size exceeds the inspection scan limit",
                {"limitBytes": SCAN_TOTAL_LIMIT, "scope": "inspection"},
            )
        try:
            data = _uvprojx._read_limited(abs_path, SCAN_FILE_LIMIT)
        except FileNotFoundError:
            continue
        except NotADirectoryError:
            continue
        except OSError:
            unreadable.append(rel)
            continue
        if len(data) > SCAN_FILE_LIMIT:
            raise KeilInspectionError(
                "KEIL_SCAN_LIMIT_EXCEEDED",
                "source file exceeds the per-file scan limit",
                {"limitBytes": SCAN_FILE_LIMIT, "scope": "file"},
            )
        total += len(data)
        if total > SCAN_TOTAL_LIMIT:
            raise KeilInspectionError(
                "KEIL_SCAN_LIMIT_EXCEEDED",
                "aggregate source size exceeds the inspection scan limit",
                {"limitBytes": SCAN_TOTAL_LIMIT, "scope": "inspection"},
            )
        read_paths.append(rel)
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raw_findings.append((rel, 0, 0, "ARMCC_SOURCE_ENCODING_UNSUPPORTED", "blocker", ""))
            continue
        scanner = _Scanner(text, language)
        found, includes = scanner.run()
        raw_findings.extend(
            (rel, line, column, rule_id, severity, evidence)
            for line, column, rule_id, severity, evidence in found
        )
        include_items.extend(includes)

    findings = tuple(
        KeilFinding(rule_id, severity, path, line, column, evidence, _RULE_MESSAGES[rule_id])
        for path, line, column, rule_id, severity, evidence in sorted(
            raw_findings, key=lambda item: (item[0], item[1], item[2], item[3])
        )
    )
    include_evidence: list[KeilEvidence] = []
    for framework, basename in include_items:
        evidence = KeilEvidence("include", basename, framework)
        if evidence not in include_evidence:
            include_evidence.append(evidence)
    return ScanOutcome(findings, tuple(include_evidence), tuple(unreadable), tuple(read_paths))


class _Scanner:
    """Lightweight lexical state machine ignoring comments and literals."""

    def __init__(self, text: str, language: str) -> None:
        self.text = text
        self.n = len(text)
        self.language = language
        self.i = 0
        self.line = 1
        self.column = 1
        self._line_starts = [0]
        for index, char in enumerate(text):
            if char == "\n":
                self._line_starts.append(index + 1)
        self.raw: list[tuple[int, int, str, str, str]] = []
        self.includes: list[tuple[str, str]] = []
        #: Whether a real code token was seen on the current preprocessing
        #: line; trivia and spliced newlines do not set it.
        self.line_has_code = False
    def run(self) -> tuple[list[tuple[int, int, str, str, str]], list[tuple[str, str]]]:
        while self.i < self.n:
            char = self.text[self.i]
            if char == "\n":
                self.i += 1
                self.line += 1
                self.column = 1
                self.line_has_code = False
            elif char == "\\" and self.text[self.i + 1 : self.i + 2] == "\n":
                self._jump(self.i + 2)
            elif char == "\\" and self.text[self.i + 1 : self.i + 3] == "\r\n":
                self._jump(self.i + 3)
            elif char == "/" and self.text[self.i + 1 : self.i + 2] in ("/", "*"):
                self._skip_comment()
            elif char == '"':
                self.line_has_code = True
                self._skip_quoted('"')
            elif char == "'":
                self.line_has_code = True
                self._skip_quoted("'")
            elif char == ";" and self.language == "asm":
                self._skip_line_comment()
            elif char == "#":
                self._handle_directive()
            elif char.isalpha() or char == "_":
                self._handle_identifier()
            else:
                if char not in " \t\r\f\v":
                    self.line_has_code = True
                self.i += 1
                self.column += 1
        return self.raw, self.includes

    def _jump(self, new_index: int) -> None:
        segment = self.text[self.i:new_index]
        newlines = segment.count("\n")
        if newlines:
            self.line += newlines
            last = self.text.rfind("\n", self.i, new_index)
            self.column = new_index - (last + 1) + 1
        else:
            self.column += new_index - self.i
        self.i = new_index

    def _skip_comment(self) -> None:
        if self.text[self.i + 1] == "/":
            # A backslash-spliced line comment owns every continuation line.
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
            self._jump(end)
        else:
            end = self.text.find("*/", self.i + 2)
            self._jump(self.n if end == -1 else end + 2)

    def _skip_raw_string(self, quote: int) -> None:
        """Skip a C++ raw literal whose opening quote is at ``quote``."""
        self._jump(_raw_string_end(self.text, self.n, quote))

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

    def _skip_line_comment(self) -> None:
        end = self.text.find("\n", self.i)
        self._jump(self.n if end == -1 else end)

    def _skip_quoted(self, quote: str) -> None:
        index = self.i + 1
        while index < self.n:
            char = self.text[index]
            if char == "\\":
                index += 2
                continue
            if char == quote:
                index += 1
                break
            index += 1
        self._jump(index)

    def _handle_directive(self) -> None:
        if self.line_has_code:
            # '#' after a real code token, including a token on a spliced
            # previous physical line, is an ordinary character.
            self.i += 1
            self.column += 1
            return
        end = self.text.find("\n", self.i)
        if end == -1:
            end = self.n
        directive = self.text[self.i : end]
        line, column = self.line, self.column
        # Skip the whole logical directive: comments and literals inside it are
        # one lexical unit, so a fake #pragma in a macro/comment body is never
        # scanned as a directive on its own.
        self._jump(self._directive_end(self.i))
        self.line_has_code = False
        self._classify_directive(directive, line, column)

    def _classify_directive(self, directive: str, line: int, column: int) -> None:
        parts = directive.split()
        if not parts:
            return
        name = parts[0]
        if name == "#include":
            match = _INCLUDE_DIRECTIVE_RE.search(directive)
            if match is not None:
                basename = match.group(1).rsplit("/", 1)[-1]
                if _INCLUDE_HAL_RE.fullmatch(basename):
                    self.includes.append(("hal", basename))
                elif _INCLUDE_LL_RE.fullmatch(basename):
                    self.includes.append(("ll", basename))
            return
        if name != "#pragma" or len(parts) < 2:
            return
        pragma = parts[1]
        tail = " ".join(parts[2:])
        if pragma == "arm" and tail.startswith("section"):
            self._record("ARMCC_CUSTOM_SECTION", "warning", line, column, directive)
        elif pragma.startswith("arm") or pragma.startswith("import") or pragma.startswith("O"):
            self._record("ARMCC_UNSUPPORTED_PRAGMA", "blocker", line, column, directive)

    def _handle_identifier(self) -> None:
        self.line_has_code = True
        start = self.i
        index = self.i
        while index < self.n and (self.text[index].isalnum() or self.text[index] == "_"):
            index += 1
        token = self.text[start:index]
        line, column = self.line, self.column
        self._jump(index)
        if (
            self.language == "cxx"
            and token in _RAW_STRING_PREFIXES
            and self.i < self.n
            and self.text[self.i] == '"'
        ):
            self._skip_raw_string(self.i)
            return
        if token == "__irq":
            self._record("ARMCC_IRQ_QUALIFIER", "warning", line, column)
        elif token == "__nop":
            if self._peek_char() == "(":
                self._record("ARMCC_INTRINSIC_NOP", "warning", line, column)
        elif token in ("__WFI", "__wfi"):
            if self._peek_char() == "(":
                self._record("ARMCC_INTRINSIC_WFI", "warning", line, column)
        elif token == "__at":
            if self._peek_char() == "(":
                self._record("ARMCC_ABSOLUTE_PLACEMENT", "blocker", line, column)
        elif token == "__attribute__":
            self._classify_attribute(line, column)
        elif token == "__asm":
            self._classify_asm(line, column)

    def _peek_char(self) -> str:
        index = self.i
        while index < self.n and self.text[index] in " \t\r\n":
            index += 1
        return self.text[index] if index < self.n else ""

    def _balanced_parens_content(self) -> str:
        index = self.i
        while index < self.n and self.text[index] in " \t\r\n":
            index += 1
        if index >= self.n or self.text[index] != "(":
            return ""
        depth = 0
        cursor = index
        while cursor < self.n:
            char = self.text[cursor]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return self.text[index + 1 : cursor]
            cursor += 1
        return ""

    def _classify_attribute(self, line: int, column: int) -> None:
        content = self._balanced_parens_content()
        if not content:
            return
        if _ATTRIBUTE_AT_RE.search(content):
            self._record("ARMCC_ABSOLUTE_PLACEMENT", "blocker", line, column)
        if _ATTRIBUTE_SECTION_RE.search(content):
            self._record("ARMCC_CUSTOM_SECTION", "warning", line, column)

    def _classify_asm(self, line: int, column: int) -> None:
        index = self.i
        while index < self.n and self.text[index] in " \t\r\n":
            index += 1
        if index >= self.n:
            return
        char = self.text[index]
        if char == "{":
            self._record("ARMCC_INLINE_ASSEMBLY_FUNCTION", "blocker", line, column)
        elif char == "(":
            cursor = index + 1
            while cursor < self.n and self.text[cursor] in " \t\r\n":
                cursor += 1
            if cursor >= self.n or self.text[cursor] not in ('"', "'"):
                self._record("ARMCC_INLINE_ASSEMBLY_FUNCTION", "blocker", line, column)
        else:
            self._record("ARMCC_INLINE_ASSEMBLY_FUNCTION", "blocker", line, column)

    def _record(
        self,
        rule_id: str,
        severity: str,
        line: int,
        column: int,
        evidence: str | None = None,
    ) -> None:
        if evidence is None:
            start = self._line_starts[line - 1]
            end = self._line_starts[line] if line < len(self._line_starts) else self.n
            evidence = self.text[start:end]
        self.raw.append(
            (line, column, rule_id, severity, evidence.strip()[:MAX_EVIDENCE_CODEPOINTS])
        )
