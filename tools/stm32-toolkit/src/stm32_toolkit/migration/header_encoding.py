"""Bounded, read-only inventory of quoted header encodings.

Migration planning needs to know which dependency files a set of already
selected translation units pulls in through quoted ``#include`` edges, what
exact bytes each one contains, and which dependency files are not strict
UTF-8.  This module answers that question without changing source text.

The inventory borrows :class:`_MacroIndex` purely as a *contained raw reader*:
``resolve_include_bytes`` keeps the component-by-component containment,
redirect refusal, case-insensitive collision detection and per-file byte
budget of semantic resolution, but this module never builds the macro index,
records a definition, evaluates a condition, or asks for decoded source.  A
refused edge is reported as bounded evidence and never followed.

Discovery is intentionally weaker than a preprocessor and fails conservative:

* Only full, ASCII, double-quoted operands become edges.  Angle includes are
  ignored and never swept from disk; dynamic, non-ASCII, malformed or
  trailing-garbage operands produce a diagnostic and no guessed filename.
* Backslash-newline (including CRLF) splices are removed before comment
  masking and directive splitting, so a continued string or comment cannot
  invent a directive line.
* A C++ raw string literal that the shared comment masker cannot prove
  (unterminated, or spanning physical lines) marks its file as incomplete and
  none of that file's apparent edges are followed.
* Files, bytes, include depth, visited directories and emitted diagnostics are
  explicitly bounded; hitting a bound is reported as ``complete=False`` with
  a stable diagnostic.

The result is a plain dictionary::

    {
        "complete": bool,
        "headers": [{"path", "sha256", "size", "utf8"}, ...],
        "nonUtf8Headers": [path, ...],
        "diagnostics": [{"including", "operand", "code", "message"}, ...],
        "counts": {"files", "bytes", "directories"},
    }

``headers`` lists dependency files discovered through quoted edges, sorted by
resolved project-relative path.  Selected source seeds are verified against
``expected_inputs`` but are not repeated as dependencies; their own source
encoding blockers are reported by the source-symbol layer.  Every list has a
stable order, and every path is project-relative.
"""

from __future__ import annotations

import hashlib
import re
from collections import deque
from collections.abc import Mapping
from pathlib import Path

from .constant_context import (
    ConstantResolutionError,
    _MacroIndex,
    _directives,
    _mask_comments,
)

MAX_INVENTORY_FILES = 4096
MAX_INVENTORY_BYTES = 64 * 1024 * 1024
MAX_INVENTORY_DEPTH = 32
MAX_INVENTORY_DIRECTORIES = 4096
MAX_INVENTORY_DIAGNOSTICS = 512

MAX_OPERAND_CHARS = 120
MAX_MESSAGE_CHARS = 240

_UTF8_BOM = b"\xef\xbb\xbf"
_INCLUDE_KEYWORDS = frozenset({"include", "import", "include_next"})

#: Full quoted operand only: 0x20..0x7E except the closing quote and the
#: non-portable backslash separator.  Anything else is a diagnostic.
_QUOTED_OPERAND_RE = re.compile(r'[ \t]*"([ -!#-\[\]-~]+)"[ \t]*')

#: C++ raw string introducer with an optional 0..16 character delimiter.
_RAW_STRING_OPEN_RE = re.compile(r'(?:u8|[uUL])?R"([^ ()\\\t\n\r\v\f]{0,16})\(')


def discover_header_encodings(
    root: Path,
    source_paths: tuple[str, ...],
    include_paths: tuple[str, ...],
    expected_inputs: Mapping[str, tuple[str, int]],
) -> dict[str, object]:
    """Inventory quoted dependencies of ``source_paths`` under ``root``.

    ``source_paths`` are already-selected, project-relative seed files.
    ``include_paths`` is the reviewed quoted search list, and
    ``expected_inputs`` maps a bound project-relative path to its expected
    ``(sha256, size)``; a mismatch is reported as ``changed`` evidence.

    The function only reads bytes: it never writes, never builds a macro
    index, and never follows an edge the contained resolver refused.
    """
    # Two raw-only indexes: seeds are resolved from the project root alone so
    # an include search list cannot shadow the exact selected source path.
    seed_index = _MacroIndex(
        root=root,
        source_path="",
        include_paths=(),
        target_defines=(),
        source_text="",
    )
    dependency_index = _MacroIndex(
        root=root,
        source_path="",
        include_paths=tuple(include_paths),
        target_defines=(),
        source_text="",
    )

    diagnostics: list[dict[str, str]] = []
    headers: dict[str, dict[str, object]] = {}
    non_utf8: set[str] = set()
    seen: set[str] = set()
    queue: deque[tuple[str, bytes, int]] = deque()

    complete = True
    truncated = False
    files = 0
    total_bytes = 0

    def directories_used() -> int:
        return len(seed_index.directory_cache) + len(
            dependency_index.directory_cache
        )

    def add_diagnostic(
        including: str, operand: str, code: str, message: str
    ) -> None:
        nonlocal complete, truncated
        complete = False
        if len(diagnostics) >= MAX_INVENTORY_DIAGNOSTICS:
            truncated = True
            return
        diagnostics.append(
            {
                "including": including,
                "operand": operand[:MAX_OPERAND_CHARS],
                "code": code,
                "message": message[:MAX_MESSAGE_CHARS],
            }
        )

    def build_result() -> dict[str, object]:
        reported = diagnostics
        if truncated and reported:
            reported = reported[: MAX_INVENTORY_DIAGNOSTICS - 1] + [
                {
                    "including": "",
                    "operand": "",
                    "code": "truncated",
                    "message": "diagnostic budget exceeded",
                }
            ]
        ordered = sorted(
            reported,
            key=lambda item: (
                item["including"],
                item["operand"],
                item["code"],
                item["message"],
            ),
        )
        return {
            "complete": complete,
            "headers": [headers[path] for path in sorted(headers)],
            "nonUtf8Headers": sorted(non_utf8),
            "diagnostics": ordered,
            "counts": {
                "files": files,
                "bytes": total_bytes,
                "directories": directories_used(),
            },
        }

    for seed in sorted(set(source_paths)):
        if files >= MAX_INVENTORY_FILES:
            add_diagnostic(seed, seed, "limit", "file budget exceeded")
            return build_result()
        try:
            located = seed_index.resolve_include_bytes("", seed)
        except ConstantResolutionError as error:
            add_diagnostic(seed, seed, error.code, _error_message(error))
            continue
        if located is None:
            add_diagnostic(
                seed,
                seed,
                "missing",
                "source file was not found under the project root",
            )
            continue
        rel, fingerprint, payload = located
        if rel in seen:
            continue
        if total_bytes + len(payload) > MAX_INVENTORY_BYTES:
            add_diagnostic(seed, seed, "limit", "byte budget exceeded")
            return build_result()
        digest = _digest(fingerprint, payload)
        expected = expected_inputs.get(rel)
        if expected is None and seed != rel:
            expected = expected_inputs.get(seed)
        if expected is not None and (expected[0], expected[1]) != (
            digest,
            len(payload),
        ):
            add_diagnostic(
                rel, rel, "changed", "input digest does not match the bound inputs"
            )
        seen.add(rel)
        files += 1
        total_bytes += len(payload)
        queue.append((rel, payload, 0))

    while queue:
        rel, payload, depth = queue.popleft()
        if directories_used() > MAX_INVENTORY_DIRECTORIES:
            add_diagnostic(rel, "", "limit", "directory budget exceeded")
            return build_result()
        operands, problems = _discover_edges(payload)
        for operand, code, message in problems:
            add_diagnostic(rel, operand, code, message)
        for operand in operands:
            if directories_used() > MAX_INVENTORY_DIRECTORIES:
                add_diagnostic(rel, operand, "limit", "directory budget exceeded")
                return build_result()
            try:
                located = dependency_index.resolve_include_bytes(rel, operand)
            except ConstantResolutionError as error:
                add_diagnostic(rel, operand, error.code, _error_message(error))
                continue
            if located is None:
                add_diagnostic(
                    rel, operand, "missing", "quoted include was not found"
                )
                continue
            dependency, fingerprint, body = located
            if dependency in seen:
                continue
            if depth + 1 > MAX_INVENTORY_DEPTH:
                add_diagnostic(
                    rel, operand, "limit", "include depth budget exceeded"
                )
                continue
            if files >= MAX_INVENTORY_FILES:
                add_diagnostic(rel, operand, "limit", "file budget exceeded")
                return build_result()
            if total_bytes + len(body) > MAX_INVENTORY_BYTES:
                add_diagnostic(rel, operand, "limit", "byte budget exceeded")
                return build_result()
            digest = _digest(fingerprint, body)
            expected = expected_inputs.get(dependency)
            if expected is not None and (expected[0], expected[1]) != (
                digest,
                len(body),
            ):
                add_diagnostic(
                    rel,
                    operand,
                    "changed",
                    "dependency digest does not match the bound inputs",
                )
            seen.add(dependency)
            files += 1
            total_bytes += len(body)
            utf8 = _is_utf8(body)
            headers[dependency] = {
                "path": dependency,
                "sha256": digest,
                "size": len(body),
                "utf8": utf8,
            }
            if not utf8:
                non_utf8.add(dependency)
            queue.append((dependency, body, depth + 1))

    return build_result()


def _discover_edges(data: bytes) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Return quoted operands and operand diagnostics for one file's bytes.

    Directive discovery works on a lossless ``latin-1`` byte projection: the
    bytes are never decoded as source, so invalid UTF-8 still yields exact
    ASCII directive text and every non-ASCII operand is rejected instead of
    guessed.  Comments are masked and splices removed first, and a raw string
    the masker cannot prove suppresses every edge in the file.
    """
    masked = _mask_comments(_logical_text(data))
    unproven = _unproven_raw_string(masked)
    if unproven is not None:
        return [], [("", "raw-string", unproven)]

    operands: list[str] = []
    found: set[str] = set()
    problems: list[tuple[str, str, str]] = []
    for directive in _directives(masked):
        if directive.keyword not in _INCLUDE_KEYWORDS:
            continue
        stripped = directive.rest.strip()
        if stripped.startswith("<"):
            if len(stripped) > 1 and stripped.endswith(">"):
                # System includes are never parsed or swept.
                continue
            problems.append(
                (
                    stripped[:MAX_OPERAND_CHARS],
                    "malformed",
                    "system include operand is not terminated",
                )
            )
            continue
        match = _QUOTED_OPERAND_RE.fullmatch(directive.rest)
        if match is None:
            problems.append(_operand_problem(directive.rest))
            continue
        operand = match.group(1)
        if operand in found:
            continue
        found.add(operand)
        operands.append(operand)
    return operands, problems


def _operand_problem(rest: str) -> tuple[str, str, str]:
    """Classify a non-literal include operand without guessing a filename."""
    operand = rest.strip()[:MAX_OPERAND_CHARS]
    if not operand:
        return operand, "malformed", "include directive has no operand"
    if any(ord(char) > 0x7E for char in rest):
        return operand, "non-ascii", "include operand is not ASCII"
    if "\\" in rest:
        return operand, "malformed", "include operand uses a backslash separator"
    if '"' in rest:
        return (
            operand,
            "malformed",
            "include operand is not one complete quoted path",
        )
    return operand, "dynamic", "include operand is not a literal quoted path"


def _logical_text(data: bytes) -> str:
    """Strip a UTF-8 BOM and translation-phase-2 splices, byte for byte."""
    body = data[3:] if data.startswith(_UTF8_BOM) else data
    text = body.decode("latin-1")
    if "\\\r\n" in text:
        text = text.replace("\\\r\n", "")
    if "\\\n" in text:
        text = text.replace("\\\n", "")
    return text


def _unproven_raw_string(masked: str) -> str | None:
    """Return why a raw string literal cannot be proven, or ``None``."""
    for match in _RAW_STRING_OPEN_RE.finditer(masked):
        closing = ")" + match.group(1) + '"'
        end = masked.find(closing, match.end())
        if end == -1:
            return "raw string literal is not terminated"
        if "\n" in masked[match.end() : end]:
            return "raw string literal spans multiple lines"
    return None


def _is_utf8(data: bytes) -> bool:
    try:
        data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return False
    return True


def _digest(fingerprint: tuple[str, int] | None, payload: bytes) -> str:
    if fingerprint is not None:
        return fingerprint[0]
    return hashlib.sha256(payload).hexdigest()


def _error_message(error: ConstantResolutionError) -> str:
    return (
        error.context
        or error.detail
        or "quoted include could not be resolved"
    )
