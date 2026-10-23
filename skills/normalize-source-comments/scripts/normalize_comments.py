#!/usr/bin/env python3
"""Comment-only source normalization for explicitly declared legacy charsets.

Standard-library helper for the ``normalize-source-comments`` skill.  It has
two deliberately separate operations:

``preview``
    Read-only with respect to the project.  Strictly decode each explicitly
    selected file, identify real C/C++ comments, derive UTF-8 replacement
    bytes, and write a plan plus a human-readable report to an external
    preview directory.

``copy``
    Re-read and re-derive every selected input, prove the reviewed plan is
    unchanged, then write converted *copies* into a new external directory.
    Originals are never written and existing output is never overwritten.

This helper is not a C compiler and does not replace a compiler migration.
It only rewrites non-ASCII characters inside comment content.  All other
bytes, comment delimiters, line endings, final-newline state and an existing
UTF-8 BOM are preserved.
"""

from __future__ import annotations

import argparse
import bisect
import difflib
import hashlib
import json
import os
import re
import stat
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

HELPER_VERSION = "1.0.0"
PLAN_SCHEMA_VERSION = 1
MANIFEST_SCHEMA_VERSION = 1
PLAN_KIND = "stm32-comment-normalization-plan"
MANIFEST_KIND = "stm32-comment-normalization-manifest"

ALLOWED_CHARSETS = ("utf-8", "gb2312", "gbk", "gb18030", "cp1252")
ALLOWED_SUFFIXES = {
    ".c",
    ".h",
    ".cc",
    ".cpp",
    ".cxx",
    ".hpp",
    ".hh",
    ".hxx",
    ".inl",
}

MAX_FILES = 256
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_DECODED_CHARACTERS = 1_000_000
MAX_OUTPUT_BYTES = 48 * 1024 * 1024
MAX_TOTAL_OUTPUT_BYTES = 192 * 1024 * 1024
MAX_PLAN_BYTES = 16 * 1024 * 1024
MAX_PREVIEW_BYTES = 32 * 1024 * 1024
MAX_FINDINGS = 200
# One global presentation bound shared by derivation and plan validation, so a
# legitimate ready preview is always copyable.  Each of the two lexing passes
# (trigraph scan, comment scanner) is capped independently at MAX_FINDINGS and
# can append at most one truncation marker; the NUL/binary check adds one, and
# the derived-output checks add at most five (per-file bound, UTF-8 validity,
# stability, outside-comment drift, idempotence).  MAX_FINDINGS * 2 + 8 is the
# conservative bounded allowance for that combination; several of those error
# branches cannot occur together, so it is an upper bound, not a tight count.
MAX_PRESENTED_FINDINGS = MAX_FINDINGS * 2 + 8
MAX_DIFF_LINES = 4000

TRIGRAPH_CHARS = "=/'()!<>-"
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_RESERVED_OUTPUT_NAMES = {
    "manifest.json",
    "manifest.json.partial",
    "INCOMPLETE.json",
}


def _portable_name_key(name: str) -> str:
    """Fold one path component the way a Windows filesystem resolves it.

    Windows compares names case-insensitively and ignores trailing dots and
    spaces when it creates a file or directory, so ``MANIFEST.JSON``,
    ``manifest.json.`` and ``manifest.json `` all alias the reserved manifest
    name.  Folding here rejects the collision before any output is created.
    """

    return name.rstrip(" .").casefold()


_RESERVED_OUTPUT_KEYS = {_portable_name_key(name) for name in _RESERVED_OUTPUT_NAMES}
_INCOMPLETE_NAME_KEY_RE = re.compile(r"incomplete\.\d+\.json")
_HEADER_DIRECTIVES = {"include", "include_next", "import", "embed"}
_HEADER_OPERATORS = {"__has_include", "__has_include_next", "__has_embed", "__has_embed_next"}


class ToolError(Exception):
    """A bounded, machine-readable failure."""

    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class _DecodeFailure(Exception):
    def __init__(
        self,
        message: str,
        byte_offset: int,
        line: int,
        column: int,
        original_bytes: str | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.byte_offset = byte_offset
        self.line = line
        self.column = column
        self.original_bytes = original_bytes


class _ScanAbort(Exception):
    def __init__(self, finding: "Finding"):
        super().__init__(finding.message)
        self.finding = finding


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str  # "blocker", "warning", or "info"
    message: str
    byte_offset: int | None = None
    line: int | None = None
    column: int | None = None
    original_bytes: str | None = None
    decoded_text: str | None = None

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "byteOffset": self.byte_offset,
            "line": self.line,
            "column": self.column,
            "originalBytes": self.original_bytes,
            "decodedText": self.decoded_text,
        }


@dataclass
class Analysis:
    path: str
    charset: str
    status: str
    source_size: int
    source_sha256: str
    output_size: int | None
    output_sha256: str | None
    outside_comment_sha256: str | None
    output_outside_comment_sha256: str | None
    comment_count: int
    comment_non_ascii_units: int
    changed_units: int
    newline: dict
    bom: bool
    decode_round_trip: bool
    idempotent: bool
    findings: list[Finding]
    output: bytes | None
    diff_lines: list[str]

    def to_plan_dict(self) -> dict:
        return {
            "path": self.path,
            "charset": self.charset,
            "status": self.status,
            "sourceSize": self.source_size,
            "sourceSha256": self.source_sha256,
            "outputSize": self.output_size,
            "outputSha256": self.output_sha256,
            "outsideCommentSha256": self.outside_comment_sha256,
            "outputOutsideCommentSha256": self.output_outside_comment_sha256,
            "commentCount": self.comment_count,
            "commentNonAsciiUnits": self.comment_non_ascii_units,
            "changedUnits": self.changed_units,
            "newline": self.newline,
            "bom": self.bom,
            "decodeRoundTrip": self.decode_round_trip,
            "idempotent": self.idempotent,
            "findings": [finding.to_dict() for finding in self.findings],
        }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hex(data: bytes) -> str:
    return data.hex()


def _fmt_hex(value: str) -> str:
    try:
        return " ".join(f"{byte:02x}" for byte in bytes.fromhex(value))
    except ValueError:
        return value


def _byte_line_starts(data: bytes) -> list[int]:
    starts = [0]
    index = 0
    length = len(data)
    while index < length:
        byte = data[index]
        if byte == 13:  # CR
            if index + 1 < length and data[index + 1] == 10:
                index += 2
            else:
                index += 1
            starts.append(index)
            continue
        if byte == 10:  # LF
            index += 1
            starts.append(index)
            continue
        index += 1
    return starts


def _loc(starts: list[int], offset: int) -> tuple[int, int]:
    index = bisect.bisect_right(starts, offset) - 1
    if index < 0:
        index = 0
    return index + 1, offset - starts[index] + 1


def _finding_at(
    code: str,
    severity: str,
    message: str,
    byte_offset: int,
    line_starts: list[int],
    original_bytes: str | None = None,
    decoded_text: str | None = None,
) -> Finding:
    line, column = _loc(line_starts, byte_offset)
    return Finding(
        code,
        severity,
        message,
        byte_offset,
        line,
        column,
        original_bytes,
        decoded_text,
    )


def _newline_info(data: bytes) -> dict:
    crlf = 0
    lf = 0
    cr = 0
    index = 0
    length = len(data)
    while index < length:
        byte = data[index]
        if byte == 13:
            if index + 1 < length and data[index + 1] == 10:
                crlf += 1
                index += 2
                continue
            cr += 1
            index += 1
            continue
        if byte == 10:
            lf += 1
        index += 1
    if data.endswith(b"\r\n"):
        final = "CRLF"
    elif data.endswith(b"\n"):
        final = "LF"
    elif data.endswith(b"\r"):
        final = "CR"
    else:
        final = "none"
    return {
        "crlf": crlf,
        "lf": lf,
        "cr": cr,
        "finalNewline": final != "none",
        "finalSequence": final,
    }


def _is_reparse(path: os.PathLike[str] | str) -> bool:
    try:
        info = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT)


def _check_no_reparse(root: Path, relative: str) -> None:
    if _is_reparse(root):
        raise ToolError(
            "REPARSE_PATH",
            "project root is a redirected or reparse path; use its real directory",
            {"path": str(root)},
        )
    current = root
    for part in relative.split("/"):
        current = current / part
        if _is_reparse(current):
            raise ToolError(
                "REPARSE_PATH",
                "input path contains a symbolic link, junction, or reparse point",
                {"path": relative, "component": part},
            )


def _check_raw_ancestors(path: os.PathLike[str] | str) -> None:
    """Reject a redirected ancestor before realpath can erase the evidence.

    ``os.path.abspath`` normalizes without following links.  Every existing
    component from the filesystem root to the leaf is checked with ``lstat``;
    missing components end the walk because they cannot redirect anything yet.
    """

    absolute = Path(os.path.abspath(os.fspath(path)))
    parts = absolute.parts
    if not parts:
        return
    current = Path(parts[0])
    if _is_reparse(current):
        raise ToolError(
            "REPARSE_PATH",
            "path has a redirected or reparse filesystem root",
            {"path": str(absolute), "component": str(current)},
        )
    for part in parts[1:]:
        current = current / part
        if _is_reparse(current):
            raise ToolError(
                "REPARSE_PATH",
                "path contains a symbolic link, junction, or reparse point in an ancestor",
                {"path": str(absolute), "component": str(current)},
            )
        if not current.exists():
            break


def _check_reserved_output_path(relative: str) -> None:
    first = relative.split("/", 1)[0]
    key = _portable_name_key(first)
    if key in _RESERVED_OUTPUT_KEYS or _INCOMPLETE_NAME_KEY_RE.fullmatch(key):
        raise ToolError(
            "RESERVED_OUTPUT_PATH",
            "selected path collides with a reserved output manifest or marker name",
            {"path": relative, "reserved": first},
        )


def _norm(path: os.PathLike[str] | str) -> str:
    return os.path.normcase(os.path.realpath(os.fspath(path)))


def _within(child: os.PathLike[str] | str, parent: os.PathLike[str] | str) -> bool:
    child_norm = _norm(child)
    parent_norm = _norm(parent)
    try:
        return os.path.commonpath([child_norm, parent_norm]) == parent_norm
    except ValueError:
        return False


def _same_path(first: os.PathLike[str] | str, second: os.PathLike[str] | str) -> bool:
    return _norm(first) == _norm(second)


def _normalize_relative(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ToolError("PATH_INVALID", "source path must be a non-empty relative path")
    if "\x00" in value:
        raise ToolError("PATH_INVALID", "source path contains a NUL character")
    raw = value.replace("\\", "/")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise ToolError(
            "PATH_INVALID",
            "source path must be project-root-relative, not absolute",
            {"path": value},
        )
    if raw.endswith("/"):
        raise ToolError("PATH_INVALID", "source path must name a file", {"path": value})
    parts = raw.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ToolError(
            "PATH_INVALID",
            "source path must not contain empty, dot, or parent components",
            {"path": value},
        )
    if any(":" in part for part in parts):
        raise ToolError(
            "PATH_INVALID",
            "source path must not contain drive or alternate-stream colons",
            {"path": value},
        )
    return "/".join(parts)


def _check_suffix(relative: str) -> None:
    suffix = Path(relative).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ToolError(
            "UNSUPPORTED_FILE_TYPE",
            "only explicit C/C++ source and header files are supported",
            {"path": relative, "suffix": suffix},
        )


def _read_bytes_limited(path: Path, limit: int, code: str = "IO_FAILURE") -> bytes:
    try:
        info = os.stat(path)
    except FileNotFoundError:
        raise ToolError("INPUT_MISSING", "file does not exist", {"path": str(path)})
    except OSError as error:
        raise ToolError(code, f"cannot stat file: {error}", {"path": str(path)}) from error
    if not stat.S_ISREG(info.st_mode):
        raise ToolError("INPUT_NOT_FILE", "path is not a regular file", {"path": str(path)})
    if info.st_size > limit:
        raise ToolError(
            "BOUNDS_EXCEEDED",
            "file exceeds the configured size limit",
            {"path": str(path), "size": info.st_size, "limit": limit},
        )
    try:
        with open(path, "rb") as stream:
            data = stream.read(limit + 1)
    except OSError as error:
        raise ToolError(code, f"cannot read file: {error}", {"path": str(path)}) from error
    if len(data) > limit:
        raise ToolError(
            "BOUNDS_EXCEEDED",
            "file exceeds the configured size limit",
            {"path": str(path), "limit": limit},
        )
    return data


def _read_input(root: Path, relative: str) -> bytes:
    _check_no_reparse(root, relative)
    target = root.joinpath(*relative.split("/"))
    if not _within(target, root):
        raise ToolError(
            "PATH_INVALID",
            "source path resolves outside the project root",
            {"path": relative},
        )
    return _read_bytes_limited(target, MAX_FILE_BYTES)


def _validate_project_root(value: str) -> Path:
    raw = Path(os.fspath(value))
    _check_raw_ancestors(raw)
    root = Path(os.path.realpath(raw))
    if not root.exists():
        raise ToolError("INPUT_MISSING", "project root does not exist", {"path": str(raw)})
    if not root.is_dir():
        raise ToolError("PATH_INVALID", "project root is not a directory", {"path": str(raw)})
    return root


def _resolve_external_dir(
    value: str,
    root: Path,
    kind: str,
    create: bool,
    must_not_exist: bool,
) -> Path:
    raw = Path(os.fspath(value))
    _check_raw_ancestors(raw)
    resolved = Path(os.path.realpath(raw))
    if _within(resolved, root) or _within(root, resolved):
        raise ToolError(
            "OUTPUT_CONTAINMENT",
            f"{kind} directory must be outside the source root and must not contain it",
            {"kind": kind, "path": str(resolved), "sourceRoot": str(root)},
        )
    if resolved.exists():
        if must_not_exist:
            raise ToolError(
                "OUTPUT_EXISTS",
                "output directory already exists; choose a new directory",
                {"path": str(resolved)},
            )
        if not resolved.is_dir():
            raise ToolError(
                "PATH_INVALID",
                f"{kind} path is not a directory",
                {"path": str(resolved)},
            )
        if _is_reparse(resolved):
            raise ToolError(
                "REPARSE_PATH",
                f"{kind} directory is a redirected or reparse path",
                {"kind": kind, "path": str(resolved)},
            )
        return resolved
    parent = resolved.parent
    if not parent.exists():
        raise ToolError(
            "OUTPUT_PARENT_MISSING",
            f"the parent directory of the new {kind} directory must already exist",
            {"kind": kind, "path": str(resolved)},
        )
    if not parent.is_dir():
        raise ToolError(
            "PATH_INVALID",
            f"the parent of the new {kind} directory is not a directory",
            {"path": str(parent)},
        )
    if _is_reparse(parent):
        raise ToolError(
            "REPARSE_PATH",
            f"the parent of the new {kind} directory is a redirected or reparse path",
            {"kind": kind, "path": str(parent)},
        )
    if create:
        try:
            os.mkdir(resolved)
        except FileExistsError:
            if not resolved.is_dir():
                raise ToolError(
                    "PATH_INVALID",
                    f"{kind} path is not a directory",
                    {"path": str(resolved)},
                )
            if _is_reparse(resolved):
                raise ToolError(
                    "REPARSE_PATH",
                    f"{kind} directory is a redirected or reparse path",
                    {"kind": kind, "path": str(resolved)},
                )
        except OSError as error:
            raise ToolError(
                "IO_FAILURE",
                f"cannot create {kind} directory: {error}",
                {"path": str(resolved)},
            ) from error
    return resolved


def _write_exclusive(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, 0o666)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise


def _check_collision(path: Path, data: bytes, limit: int = MAX_PLAN_BYTES) -> bool:
    if not path.exists():
        return False
    if _is_reparse(path):
        raise ToolError(
            "REPARSE_PATH",
            "destination path is a redirected or reparse path",
            {"path": str(path)},
        )
    if not path.is_file():
        raise ToolError(
            "PREVIEW_COLLISION",
            "destination path exists and is not a regular file",
            {"path": str(path)},
        )
    try:
        existing = _read_bytes_limited(path, limit, code="PREVIEW_COLLISION")
    except ToolError as error:
        raise ToolError(
            "PREVIEW_COLLISION",
            "existing preview file cannot be compared within the configured bound",
            {"path": str(path), "cause": error.code},
        ) from error
    if existing == data:
        return True
    raise ToolError(
        "PREVIEW_COLLISION",
        "destination already exists with different content; use a new preview directory",
        {"path": str(path)},
    )

def _decode_strict(data: bytes, charset: str) -> tuple[str, list[tuple[int, int]], bool, int]:
    if data.startswith((b"\xff\xfe", b"\xfe\xff", b"\x00\x00\xfe\xff", b"\xff\xfe\x00\x00")):
        raise _DecodeFailure(
            "UTF-16/UTF-32 BOM is outside the supported text formats",
            0,
            1,
            1,
            _hex(data[:2]),
        )
    bom = data.startswith(b"\xef\xbb\xbf")
    prefix = 3 if bom else 0
    line_starts = _byte_line_starts(data)
    codec = "utf-8" if charset == "utf-8" else charset
    if charset == "utf-8":
        body = data[prefix:]
        try:
            text = body.decode("utf-8", "strict")
        except UnicodeDecodeError as error:
            offset = prefix + error.start
            line, column = _loc(line_starts, offset)
            raise _DecodeFailure(
                f"strict UTF-8 decode failed: {error.reason}",
                offset,
                line,
                column,
                _hex(data[offset : offset + 1]),
            ) from error
        try:
            encoded = text.encode("utf-8")
        except UnicodeEncodeError as error:
            line, column = _loc(line_starts, prefix)
            raise _DecodeFailure(
                f"UTF-8 round-trip encode failed: {error.reason}",
                prefix,
                line,
                column,
            ) from error
        if encoded != body:
            line, column = _loc(line_starts, prefix)
            raise _DecodeFailure(
                "UTF-8 round-trip did not reproduce the input bytes",
                prefix,
                line,
                column,
            )
    else:
        if bom:
            raise _DecodeFailure(
                "UTF-8 BOM is present but a legacy charset was declared; "
                "declare utf-8 or resolve the BOM explicitly",
                0,
                1,
                1,
                "efbbbf",
            )
        body = data
        try:
            text = body.decode(charset, "strict")
        except UnicodeDecodeError as error:
            offset = prefix + error.start
            line, column = _loc(line_starts, offset)
            raise _DecodeFailure(
                f"strict {charset} decode failed: {error.reason}",
                offset,
                line,
                column,
                _hex(data[offset : offset + 1]),
            ) from error
        try:
            encoded = text.encode(charset)
        except UnicodeEncodeError as error:
            offset = prefix + len(body)
            line, column = _loc(line_starts, offset)
            raise _DecodeFailure(
                f"strict {charset} round-trip encode failed at character "
                f"{error.start}: {error.reason}",
                offset,
                line,
                column,
            ) from error
        if encoded != body:
            position = 0
            mismatch = prefix
            for character in text:
                piece = character.encode(charset)
                if body[position : position + len(piece)] != piece:
                    mismatch = prefix + position
                    break
                position += len(piece)
            line, column = _loc(line_starts, mismatch)
            raise _DecodeFailure(
                f"strict {charset} round-trip mismatch; refusing to invent bytes",
                mismatch,
                line,
                column,
                _hex(data[mismatch : mismatch + 1]),
            )

    if len(text) > MAX_DECODED_CHARACTERS:
        line, column = _loc(line_starts, prefix)
        raise _DecodeFailure(
            f"decoded character count {len(text)} exceeds the conservative "
            f"limit {MAX_DECODED_CHARACTERS}; the file is blocked before "
            "building source mappings",
            prefix,
            line,
            column,
        )
    offsets: list[tuple[int, int]] = []
    assembled = bytearray()
    position = prefix
    for character in text:
        piece = character.encode(codec)
        offsets.append((position, position + len(piece)))
        position += len(piece)
        assembled.extend(piece)
    if position != len(data) or bytes(assembled) != body:
        line, column = _loc(line_starts, prefix)
        raise _DecodeFailure(
            "per-character byte mapping did not reproduce the input bytes",
            prefix,
            line,
            column,
        )
    return text, offsets, bom, prefix


def _logical_view(
    text: str,
    offsets: list[tuple[int, int]],
    line_starts: list[int],
) -> tuple[list[str], list[int]]:
    characters: list[str] = []
    physical: list[int] = []
    index = 0
    length = len(text)
    while index < length:
        character = text[index]
        if character == "\\":
            cursor = index + 1
            whitespace_end = cursor
            while whitespace_end < length and text[whitespace_end] in " \t\v\f":
                whitespace_end += 1
            if (
                whitespace_end > cursor
                and whitespace_end < length
                and text[whitespace_end] in "\r\n"
            ):
                offset = offsets[index][0]
                raise _ScanAbort(
                    _finding_at(
                        "BACKSLASH_HSPACE_NEWLINE_UNSUPPORTED",
                        "blocker",
                        "backslash followed by horizontal whitespace before a "
                        "newline is a GCC extension; this helper blocks the file "
                        "rather than misclassify the following line",
                        offset,
                        line_starts,
                    )
                )
            if cursor < length and text[cursor] == "\n":
                index = cursor + 1
                continue
            if cursor < length and text[cursor] == "\r":
                if cursor + 1 < length and text[cursor + 1] == "\n":
                    index = cursor + 2
                else:
                    index = cursor + 1
                continue
        characters.append(character)
        physical.append(index)
        index += 1
    return characters, physical


def _is_ident_start(character: str) -> bool:
    return len(character) == 1 and character.isascii() and (
        character.isalpha() or character == "_"
    )


def _is_ident(character: str) -> bool:
    return len(character) == 1 and character.isascii() and (
        character.isalnum() or character == "_"
    )


def _is_ascii_letter(character: str) -> bool:
    return len(character) == 1 and character.isascii() and character.isalpha()


class _Scanner:
    """Conservative phase-3 comment locator over a spliced character view."""

    __slots__ = (
        "data",
        "text",
        "offsets",
        "physical",
        "charset",
        "legacy",
        "line_starts",
        "findings",
        "suppressed",
        "blocker_count",
        "blocker_suppressed",
        "content_intervals",
        "comment_count",
        "comment_non_ascii",
        "changed_units",
    )

    def __init__(
        self,
        data: bytes,
        text: str,
        offsets: list[tuple[int, int]],
        physical: list[int],
        charset: str,
        line_starts: list[int],
    ):
        self.data = data
        self.text = text
        self.offsets = offsets
        self.physical = physical
        self.charset = charset
        self.legacy = charset != "utf-8"
        self.line_starts = line_starts
        self.findings: list[Finding] = []
        self.suppressed = 0
        self.blocker_count = 0
        self.blocker_suppressed = 0
        self.content_intervals: list[tuple[int, int]] = []
        self.comment_count = 0
        self.comment_non_ascii = 0
        self.changed_units = 0

    def _finding(
        self,
        code: str,
        severity: str,
        message: str,
        *,
        logical_index: int | None = None,
        byte_offset: int | None = None,
        original: str | None = None,
        decoded: str | None = None,
    ) -> Finding:
        if byte_offset is None and logical_index is not None:
            byte_offset = self.offsets[self.physical[logical_index]][0]
        if byte_offset is None:
            return Finding(code, severity, message, None, None, None, original, decoded)
        line, column = _loc(self.line_starts, byte_offset)
        return Finding(code, severity, message, byte_offset, line, column, original, decoded)

    def _add(self, finding: Finding) -> None:
        if finding.severity == "blocker":
            self.blocker_count += 1
        if len(self.findings) < MAX_FINDINGS:
            self.findings.append(finding)
        else:
            self.suppressed += 1
            if finding.severity == "blocker":
                self.blocker_suppressed += 1

    def _abort(self, code: str, message: str, logical_index: int) -> None:
        raise _ScanAbort(
            self._finding(code, "blocker", message, logical_index=logical_index)
        )

    def run(self) -> None:
        index = 0
        length = len(self.physical)
        at_line_start = True
        while index < length:
            character = self.text[self.physical[index]]
            if character in "\r\n":
                at_line_start = True
                index += 1
                continue
            if at_line_start and character in " \t\v\f":
                index += 1
                continue
            if at_line_start and character == "#":
                at_line_start = False
                index = self._directive(index, 1)
                continue
            if (
                at_line_start
                and character == "%"
                and index + 1 < length
                and self.text[self.physical[index + 1]] == ":"
            ):
                at_line_start = False
                index = self._directive(index, 2)
                continue
            if at_line_start and _is_ident_start(character):
                consumed = self._line_start_import(index)
                if consumed is not None:
                    at_line_start = False
                    index = consumed
                    continue
            if (
                character == "/"
                and index + 1 < length
                and self.text[self.physical[index + 1]] == "/"
            ):
                index = self._line_comment(index)
                continue
            if (
                character == "/"
                and index + 1 < length
                and self.text[self.physical[index + 1]] == "*"
            ):
                previous = at_line_start
                next_index, saw_newline = self._block_comment(index)
                at_line_start = previous or saw_newline
                index = next_index
                continue
            at_line_start = False
            if character == "'":
                index = self._character_literal(index)
                continue
            if character == '"':
                index = self._string_literal(index)
                continue
            if _is_ident_start(character):
                end = index + 1
                while end < length and _is_ident(self.text[self.physical[end]]):
                    end += 1
                word = "".join(
                    self.text[self.physical[position]]
                    for position in range(index, end)
                )
                if (
                    word in ("R", "u8R", "uR", "UR", "LR")
                    and end < length
                    and self.text[self.physical[end]] == '"'
                ):
                    self._abort(
                        "RAW_STRING_UNSUPPORTED",
                        "C++ raw string literal is rejected explicitly; no file was written",
                        index,
                    )
                if word in _HEADER_OPERATORS:
                    consumed = self._header_operator(word, end)
                    if consumed is not None:
                        index = consumed
                        continue
                index = end
                continue
            if character == "\\":
                self._abort(
                    "STRAY_BACKSLASH",
                    "stray backslash outside a comment or literal",
                    index,
                )
            if ord(character) > 127:
                self._non_comment_non_ascii(index)
            index += 1

    def _skip_preprocessing_space(self, index: int) -> tuple[int, bool]:
        """Skip whitespace and comments between preprocessing tokens.

        A line comment ends the logical directive; the returned index is at
        its newline so the main loop can process the newline normally.  Block
        comments are consumed and their content is still marked as comment
        content, so comment-only conversion and findings are preserved.
        """

        length = len(self.physical)
        cursor = index
        while cursor < length:
            character = self.text[self.physical[cursor]]
            if character in " \t\v\f":
                cursor += 1
                continue
            if character in "\r\n":
                return cursor, True
            if (
                character == "/"
                and cursor + 1 < length
                and self.text[self.physical[cursor + 1]] == "/"
            ):
                cursor = self._line_comment(cursor)
                return cursor, True
            if (
                character == "/"
                and cursor + 1 < length
                and self.text[self.physical[cursor + 1]] == "*"
            ):
                cursor, _ = self._block_comment(cursor)
                continue
            return cursor, False
        return cursor, True

    def _parse_header(self, index: int) -> int:
        """Consume one preprocessing header-name token without comment lexing."""

        length = len(self.physical)
        opener = self.text[self.physical[index]]
        closer = ">" if opener == "<" else '"'
        position = index + 1
        while position < length:
            character = self.text[self.physical[position]]
            if character == closer:
                return position + 1
            if character in "\r\n":
                self._abort(
                    "UNTERMINATED_HEADER_NAME",
                    "unterminated preprocessing header name",
                    index,
                )
            if ord(character) > 127:
                self._non_comment_non_ascii(position)
            position += 1
        self._abort(
            "UNTERMINATED_HEADER_NAME",
            "unterminated preprocessing header name",
            index,
        )
        raise AssertionError("unreachable")

    def _directive(self, index: int, hash_length: int) -> int:
        length = len(self.physical)
        cursor, stopped = self._skip_preprocessing_space(index + hash_length)
        if stopped:
            return cursor
        start = cursor
        while cursor < length and _is_ident(self.text[self.physical[cursor]]):
            cursor += 1
        name = "".join(
            self.text[self.physical[position]] for position in range(start, cursor)
        )
        if name not in _HEADER_DIRECTIVES:
            return cursor
        cursor, stopped = self._skip_preprocessing_space(cursor)
        if stopped:
            self._abort(
                "UNSUPPORTED_INCLUDE_FORM",
                "include-like directive has no header-name or macro operand "
                "before the line ends; the form is unsupported and the file is blocked",
                start,
            )
        if cursor < length and self.text[self.physical[cursor]] in '<"':
            return self._parse_header(cursor)
        return cursor

    def _line_start_import(self, index: int) -> int | None:
        """Handle C++ header-unit import forms at the start of a line.

        ``import <header>;`` and ``export import <header>;`` use a header-name
        token, so comment-looking bytes inside ``<...>`` must not be lexed as
        comments.  Non-header module imports continue as ordinary code.
        """

        length = len(self.physical)
        start = index
        cursor = index
        while cursor < length and _is_ident(self.text[self.physical[cursor]]):
            cursor += 1
        word = "".join(
            self.text[self.physical[position]] for position in range(start, cursor)
        )
        if word not in ("import", "export"):
            return None
        if word == "export":
            cursor, stopped = self._skip_preprocessing_space(cursor)
            if stopped:
                return cursor
            next_start = cursor
            while cursor < length and _is_ident(self.text[self.physical[cursor]]):
                cursor += 1
            next_word = "".join(
                self.text[self.physical[position]]
                for position in range(next_start, cursor)
            )
            if next_word != "import":
                return cursor if cursor > next_start else next_start
        cursor, stopped = self._skip_preprocessing_space(cursor)
        if stopped:
            return cursor
        if cursor < length and self.text[self.physical[cursor]] in '<"':
            return self._parse_header(cursor)
        return cursor

    def _header_operator(self, word: str, end: int) -> int | None:
        """Handle __has_include/__has_embed style header-name operands."""

        length = len(self.physical)
        cursor, stopped = self._skip_preprocessing_space(end)
        if stopped:
            return cursor
        if cursor >= length or self.text[self.physical[cursor]] != "(":
            return cursor
        cursor, stopped = self._skip_preprocessing_space(cursor + 1)
        if stopped:
            return cursor
        if cursor < length and self.text[self.physical[cursor]] in '<"':
            return self._parse_header(cursor)
        return cursor

    def _line_comment(self, index: int) -> int:
        length = len(self.physical)
        position = index + 2
        start = position
        while position < length and self.text[self.physical[position]] not in "\r\n":
            position += 1
        self._content(start, position)
        self.comment_count += 1
        return position

    def _block_comment(self, index: int) -> tuple[int, bool]:
        length = len(self.physical)
        position = index + 2
        start = position
        saw_newline = False
        while position < length:
            character = self.text[self.physical[position]]
            if (
                character == "*"
                and position + 1 < length
                and self.text[self.physical[position + 1]] == "/"
            ):
                self._content(start, position)
                self.comment_count += 1
                return position + 2, saw_newline
            if character in "\r\n":
                saw_newline = True
            position += 1
        self._abort(
            "UNTERMINATED_BLOCK_COMMENT",
            "unterminated block comment",
            index,
        )
        raise AssertionError("unreachable")

    def _content(self, start: int, end: int) -> None:
        if end <= start:
            return
        for position in range(start, end):
            self._mark_content(position)
        first_physical = self.physical[start]
        last_physical = self.physical[end - 1] + 1
        if self.content_intervals and first_physical <= self.content_intervals[-1][1]:
            previous = self.content_intervals[-1]
            self.content_intervals[-1] = (
                previous[0],
                max(previous[1], last_physical),
            )
        else:
            self.content_intervals.append((first_physical, last_physical))

    def _mark_content(self, logical_index: int) -> None:
        physical_index = self.physical[logical_index]
        character = self.text[physical_index]
        if ord(character) <= 127:
            return
        self.comment_non_ascii += 1
        if self.legacy:
            self.changed_units += 1
        self._check_content_character(physical_index, character)

    def _check_content_character(self, physical_index: int, character: str) -> None:
        start, end = self.offsets[physical_index]
        raw = self.data[start:end]
        codepoint = ord(character)
        severity = "blocker" if self.legacy else "warning"
        raw_hex = _hex(raw)
        if 0xE000 <= codepoint <= 0xF8FF or 0xF0000 <= codepoint <= 0xFFFFD or 0x100000 <= codepoint <= 0x10FFFD:
            self._add(
                self._finding(
                    "PRIVATE_USE_CODE_POINT",
                    severity,
                    "private-use code point has no portable human meaning; review the source text explicitly",
                    logical_index=None,
                    byte_offset=start,
                    original=raw_hex,
                    decoded=character,
                )
            )
        if 0x80 <= codepoint <= 0x9F:
            self._add(
                self._finding(
                    "C1_CONTROL_CODE_POINT",
                    severity,
                    "C1 control code point often indicates a wrong charset; review the source text explicitly",
                    logical_index=None,
                    byte_offset=start,
                    original=raw_hex,
                    decoded=character,
                )
            )
        if codepoint == 0xFFFD:
            self._add(
                self._finding(
                    "REPLACEMENT_CODE_POINT",
                    severity,
                    "U+FFFD replacement character is ambiguous; review the source text explicitly",
                    logical_index=None,
                    byte_offset=start,
                    original=raw_hex,
                    decoded=character,
                )
            )
        if 0xFDD0 <= codepoint <= 0xFDEF or (codepoint & 0xFFFE) == 0xFFFE:
            self._add(
                self._finding(
                    "NONCHARACTER_CODE_POINT",
                    severity,
                    "Unicode noncharacter is not valid human text; review the source text explicitly",
                    logical_index=None,
                    byte_offset=start,
                    original=raw_hex,
                    decoded=character,
                )
            )
        if unicodedata.category(character) == "Cn":
            self._add(
                self._finding(
                    "UNASSIGNED_CODE_POINT",
                    "warning",
                    "code point is unassigned in this interpreter's Unicode database; review the decoded text",
                    logical_index=None,
                    byte_offset=start,
                    original=raw_hex,
                    decoded=character,
                )
            )
        if raw.endswith(b"\\") and (
            physical_index + 1 >= len(self.text)
            or self.text[physical_index + 1] in "\r\n"
        ):
            self._add(
                self._finding(
                    "DBCS_TRAIL_BACKSLASH_UNSUPPORTED",
                    "blocker",
                    "a non-ASCII character ends in byte 0x5C at a physical line end; "
                    "raw-byte and decoded lexers can disagree, so the file is blocked",
                    logical_index=None,
                    byte_offset=start,
                    original=raw_hex,
                    decoded=character,
                )
            )
        if (
            self.charset in ("gb2312", "gbk", "gb18030")
            and len(raw) == 2
            and 0x80 <= raw[0] <= 0x9F
            and (
                65 <= raw[1] <= 90
                or 97 <= raw[1] <= 122
            )
            and physical_index > 0
            and _is_ascii_letter(self.text[physical_index - 1])
        ):
            self._add(
                self._finding(
                    "MIXED_SINGLE_BYTE_ARTIFACT",
                    "warning",
                    "a DBCS pair with a 0x80-0x9F lead and an ASCII letter trail "
                    "is adjacent to an ASCII word; the trail byte may have been "
                    "consumed by the legacy decoder; review the decoded text",
                    logical_index=None,
                    byte_offset=start,
                    original=raw_hex,
                    decoded=character,
                )
            )

    def _non_comment_non_ascii(self, logical_index: int) -> None:
        physical_index = self.physical[logical_index]
        start, end = self.offsets[physical_index]
        raw = self.data[start:end]
        character = self.text[physical_index]
        if self.legacy:
            self._add(
                self._finding(
                    "NON_COMMENT_NON_ASCII",
                    "blocker",
                    "non-ASCII source bytes appear outside a comment; legacy "
                    "conversion would change non-comment bytes",
                    logical_index=logical_index,
                    original=_hex(raw),
                    decoded=character,
                )
            )
        else:
            self._add(
                self._finding(
                    "NON_COMMENT_NON_ASCII",
                    "warning",
                    "non-ASCII text appears outside a comment; UTF-8 output is unchanged",
                    logical_index=logical_index,
                    original=_hex(raw),
                    decoded=character,
                )
            )

    def _string_literal(self, index: int) -> int:
        length = len(self.physical)
        position = index + 1
        while position < length:
            character = self.text[self.physical[position]]
            if character == "\\":
                if position + 1 >= length:
                    self._abort(
                        "UNTERMINATED_STRING",
                        "unterminated string literal",
                        index,
                    )
                escaped = self.text[self.physical[position + 1]]
                if escaped in "\r\n":
                    self._abort(
                        "UNTERMINATED_STRING",
                        "unterminated string literal",
                        index,
                    )
                if ord(escaped) > 127:
                    self._non_comment_non_ascii(position + 1)
                position += 2
                continue
            if character == '"':
                return position + 1
            if character in "\r\n":
                self._abort(
                    "UNTERMINATED_STRING",
                    "unterminated string literal",
                    index,
                )
            if ord(character) > 127:
                self._non_comment_non_ascii(position)
            position += 1
        self._abort("UNTERMINATED_STRING", "unterminated string literal", index)
        raise AssertionError("unreachable")

    def _character_literal(self, index: int) -> int:
        length = len(self.physical)
        position = index + 1
        if position >= length:
            self._abort("UNTERMINATED_CHAR", "unterminated character literal", index)
        if self.text[self.physical[position]] == "'":
            self._abort("MALFORMED_CHAR_LITERAL", "empty character literal", index)
        while position < length:
            character = self.text[self.physical[position]]
            if character == "\\":
                if position + 1 >= length:
                    self._abort(
                        "UNTERMINATED_CHAR",
                        "unterminated character literal",
                        index,
                    )
                escaped = self.text[self.physical[position + 1]]
                if escaped in "\r\n":
                    self._abort(
                        "UNTERMINATED_CHAR",
                        "unterminated character literal",
                        index,
                    )
                if ord(escaped) > 127:
                    self._non_comment_non_ascii(position + 1)
                position += 2
                continue
            if character == "'":
                return position + 1
            if character in "\r\n":
                self._abort(
                    "UNTERMINATED_CHAR",
                    "unterminated character literal",
                    index,
                )
            if ord(character) > 127:
                self._non_comment_non_ascii(position)
            position += 1
        self._abort("UNTERMINATED_CHAR", "unterminated character literal", index)
        raise AssertionError("unreachable")


def _scan_trigraphs(
    text: str,
    offsets: list[tuple[int, int]],
    line_starts: list[int],
) -> tuple[list[Finding], int]:
    findings: list[Finding] = []
    suppressed = 0
    index = 0
    length = len(text)
    while index + 2 < length:
        if (
            text[index] == "?"
            and text[index + 1] == "?"
            and text[index + 2] in TRIGRAPH_CHARS
        ):
            offset = offsets[index][0]
            if text[index + 2] in ("/", "="):
                code = (
                    "TRIGRAPH_BACKSLASH_UNSUPPORTED"
                    if text[index + 2] == "/"
                    else "TRIGRAPH_DIRECTIVE_UNSUPPORTED"
                )
                message = (
                    "trigraph ??/ can create a backslash-newline splice; "
                    "the file is blocked rather than lexed incorrectly"
                    if text[index + 2] == "/"
                    else "trigraph ??= can create a preprocessing directive; "
                    "the file is blocked rather than lexed incorrectly"
                )
                findings.append(
                    _finding_at(
                        code,
                        "blocker",
                        message,
                        offset,
                        line_starts,
                    )
                )
                # A blocker is enough to stop conversion.  Returning here also
                # bounds the finding list and avoids scanning an arbitrarily
                # large tail for a file that cannot be written.
                return findings, suppressed
            if len(findings) < MAX_FINDINGS:
                findings.append(
                    _finding_at(
                        "TRIGRAPH_SEQUENCE_REVIEW",
                        "warning",
                        "trigraph sequence is not translated; review its lexical role",
                        offset,
                        line_starts,
                    )
                )
            else:
                suppressed += 1
            index += 3
            continue
        index += 1
    return findings, suppressed

def _build_output(
    data: bytes,
    text: str,
    offsets: list[tuple[int, int]],
    intervals: list[tuple[int, int]],
    prefix: int,
) -> bytes:
    output = bytearray()
    position = 0
    if prefix:
        output.extend(data[:prefix])
        position = prefix
    for first, last in intervals:
        start = offsets[first][0]
        end = offsets[last - 1][1]
        if start > position:
            output.extend(data[position:start])
        for physical_index in range(first, last):
            character = text[physical_index]
            byte_start, byte_end = offsets[physical_index]
            if ord(character) > 127:
                output.extend(character.encode("utf-8"))
            else:
                output.extend(data[byte_start:byte_end])
        position = max(position, end)
    if position < len(data):
        output.extend(data[position:])
    return bytes(output)


def _outside_digest(
    data: bytes,
    text: str,
    offsets: list[tuple[int, int]],
    intervals: list[tuple[int, int]],
    prefix: int,
) -> str:
    segments: list[bytes] = []
    position = 0
    if prefix:
        segments.append(data[:prefix])
        position = prefix
    for first, last in intervals:
        start = offsets[first][0]
        end = offsets[last - 1][1]
        if start > position:
            segments.append(data[position:start])
        position = max(position, end)
    if position < len(data):
        segments.append(data[position:])
    digest = hashlib.sha256()
    digest.update(len(segments).to_bytes(8, "big"))
    for segment in segments:
        digest.update(len(segment).to_bytes(8, "big"))
        digest.update(segment)
    return digest.hexdigest()


def _render_bytes(data: bytes) -> list[str]:
    lines: list[str] = []
    for line in data.splitlines(keepends=True):
        rendered: list[str] = []
        for byte in line:
            if byte == 9:
                rendered.append("\\t")
            elif byte == 13:
                rendered.append("\\r")
            elif byte == 10:
                rendered.append("\\n")
            elif byte == 92:
                rendered.append("\\\\")
            elif 32 <= byte <= 126:
                rendered.append(chr(byte))
            else:
                rendered.append(f"\\x{byte:02x}")
        lines.append("".join(rendered))
    return lines


def _diff_lines(source: bytes, output: bytes | None, relative: str, charset: str) -> list[str]:
    if output is None:
        return []
    source_lines = _render_bytes(source)
    output_lines = _render_bytes(output)
    diff = list(
        difflib.unified_diff(
            source_lines,
            output_lines,
            fromfile=f"{relative} ({charset})",
            tofile=f"{relative} (utf-8)",
            lineterm="",
        )
    )
    if len(diff) > MAX_DIFF_LINES:
        diff = diff[:MAX_DIFF_LINES] + ["... diff truncated at the configured line limit ..."]
    return diff


def _bound_findings(findings: list[Finding]) -> list[Finding]:
    """Apply the one global presentation bound without losing blocking state.

    Blocking findings are always preferred over warnings; if even the blockers
    cannot all be shown, the retained truncation marker is itself a blocker, so
    the file stays blocked.  The selected findings keep their incoming order
    and the marker is appended, which keeps re-derivation deterministic.
    """

    if len(findings) <= MAX_PRESENTED_FINDINGS:
        return findings
    blockers = [
        index
        for index, finding in enumerate(findings)
        if finding.severity == "blocker"
    ]
    others = [
        index
        for index, finding in enumerate(findings)
        if finding.severity != "blocker"
    ]
    if len(blockers) >= MAX_PRESENTED_FINDINGS:
        keep = set(blockers[: MAX_PRESENTED_FINDINGS - 1])
        marker = Finding(
            "FINDINGS_TRUNCATED",
            "blocker",
            f"{len(blockers) - len(keep)} additional blocker findings were "
            "suppressed at the global presentation limit; the file is blocked",
        )
    else:
        room = MAX_PRESENTED_FINDINGS - len(blockers) - 1
        suppressed = len(others) - room
        if suppressed <= 0:  # defensive: only reachable if the bound shrinks
            return findings
        keep = set(blockers) | set(others[:room])
        marker = Finding(
            "FINDINGS_TRUNCATED",
            "warning",
            f"{suppressed} additional findings were suppressed at the global "
            "presentation limit",
        )
    bounded = [
        finding for index, finding in enumerate(findings) if index in keep
    ]
    bounded.append(marker)
    return bounded


def analyze_bytes(
    data: bytes,
    charset: str,
    relative: str,
    *,
    check_output: bool = True,
) -> Analysis:
    source_size = len(data)
    source_sha256 = _sha256(data)
    newline = _newline_info(data)
    bom = data.startswith(b"\xef\xbb\xbf")
    findings: list[Finding] = []
    comment_count = 0
    comment_non_ascii = 0
    changed_units = 0
    intervals: list[tuple[int, int]] = []
    output: bytes | None = None
    output_size: int | None = None
    output_sha256: str | None = None
    outside_digest: str | None = None
    output_outside_digest: str | None = None
    decode_round_trip = False
    idempotent = False
    scanner: _Scanner | None = None
    scan_complete = False
    text: str | None = None
    offsets: list[tuple[int, int]] | None = None
    prefix = 0

    try:
        text, offsets, bom, prefix = _decode_strict(data, charset)
        decode_round_trip = True
        line_starts = _byte_line_starts(data)
        if "\x00" in text:
            findings.append(
                _finding_at(
                    "BINARY_OR_NUL_BYTE",
                    "blocker",
                    "NUL byte in source text indicates a binary or unsupported format",
                    0,
                    line_starts,
                )
            )
        trigraph_findings, trigraph_suppressed = _scan_trigraphs(
            text, offsets, line_starts
        )
        findings.extend(trigraph_findings)
        if trigraph_suppressed:
            findings.append(
                Finding(
                    "FINDINGS_TRUNCATED",
                    "warning",
                    f"{trigraph_suppressed} additional trigraph warnings were suppressed",
                )
            )
        _characters, physical = _logical_view(text, offsets, line_starts)
        scanner = _Scanner(data, text, offsets, physical, charset, line_starts)
        try:
            scanner.run()
            scan_complete = True
        except _ScanAbort as error:
            findings.append(error.finding)
        findings.extend(scanner.findings)
        comment_count = scanner.comment_count
        comment_non_ascii = scanner.comment_non_ascii
        changed_units = scanner.changed_units
        intervals = scanner.content_intervals
        if scanner.suppressed:
            if scanner.blocker_suppressed:
                findings.append(
                    Finding(
                        "FINDINGS_TRUNCATED",
                        "blocker",
                        f"{scanner.blocker_suppressed} additional blocker findings "
                        "were suppressed at the presentation limit; the file is blocked",
                    )
                )
            else:
                findings.append(
                    Finding(
                        "FINDINGS_TRUNCATED",
                        "warning",
                        f"{scanner.suppressed} additional findings were suppressed",
                    )
                )
    except _DecodeFailure as error:
        findings.append(
            Finding(
                "DECODE_ERROR",
                "blocker",
                error.message,
                error.byte_offset,
                error.line,
                error.column,
                error.original_bytes,
                None,
            )
        )
        decode_round_trip = False
    except _ScanAbort as error:
        findings.append(error.finding)

    findings.sort(
        key=lambda finding: (
            finding.byte_offset if finding.byte_offset is not None else -1,
            finding.code,
            finding.message,
            finding.original_bytes or "",
            finding.decoded_text or "",
        )
    )
    blocked = any(finding.severity == "blocker" for finding in findings) or (
        scanner is not None and scanner.blocker_count > 0
    )

    if (
        scan_complete
        and not blocked
        and text is not None
        and offsets is not None
    ):
        outside_digest = _outside_digest(data, text, offsets, intervals, prefix)
        output = _build_output(data, text, offsets, intervals, prefix)
        if len(output) > MAX_OUTPUT_BYTES:
            findings.append(
                Finding(
                    "OUTPUT_BOUND_EXCEEDED",
                    "blocker",
                    f"derived output is {len(output)} bytes, exceeding the "
                    f"configured per-file output limit {MAX_OUTPUT_BYTES}",
                )
            )
            blocked = True
        try:
            output.decode("utf-8", "strict")
        except UnicodeDecodeError:
            findings.append(
                Finding(
                    "OUTPUT_NOT_UTF8",
                    "blocker",
                    "derived output is not valid UTF-8",
                )
            )
            blocked = True
        if check_output and not blocked and output is not None:
            out_analysis = analyze_bytes(
                output, "utf-8", relative, check_output=False
            )
            if out_analysis.status != "ready":
                codes = ", ".join(
                    finding.code
                    for finding in out_analysis.findings
                    if finding.severity == "blocker"
                )
                findings.append(
                    Finding(
                        "OUTPUT_NOT_STABLE",
                        "blocker",
                        f"derived UTF-8 output did not re-validate: {codes}",
                    )
                )
                blocked = True
            elif out_analysis.outside_comment_sha256 != outside_digest:
                findings.append(
                    Finding(
                        "OUTSIDE_COMMENT_DRIFT",
                        "blocker",
                        "bytes outside comment content changed during conversion",
                    )
                )
                blocked = True
            elif out_analysis.output != output:
                findings.append(
                    Finding(
                        "OUTPUT_NOT_IDEMPOTENT",
                        "blocker",
                        "a second conversion of the derived output would change it",
                    )
                )
                blocked = True
            else:
                idempotent = True
                output_outside_digest = out_analysis.outside_comment_sha256

    findings.sort(
        key=lambda finding: (
            finding.byte_offset if finding.byte_offset is not None else -1,
            finding.code,
            finding.message,
            finding.original_bytes or "",
            finding.decoded_text or "",
        )
    )
    findings = _bound_findings(findings)
    blocked = any(finding.severity == "blocker" for finding in findings) or (
        scanner is not None and scanner.blocker_count > 0
    )
    status = "blocked" if blocked else "ready"
    if status == "blocked":
        output = None
        output_size = None
        output_sha256 = None
        outside_digest = None
        output_outside_digest = None
        idempotent = False
    else:
        assert output is not None
        output_size = len(output)
        output_sha256 = _sha256(output)
    diff_lines = _diff_lines(data, output, relative, charset) if output is not None else []

    return Analysis(
        path=relative,
        charset=charset,
        status=status,
        source_size=source_size,
        source_sha256=source_sha256,
        output_size=output_size,
        output_sha256=output_sha256,
        outside_comment_sha256=outside_digest,
        output_outside_comment_sha256=output_outside_digest,
        comment_count=comment_count,
        comment_non_ascii_units=comment_non_ascii,
        changed_units=changed_units,
        newline=newline,
        bom=bom,
        decode_round_trip=decode_round_trip,
        idempotent=idempotent,
        findings=findings,
        output=output,
        diff_lines=diff_lines,
    )


def _limits() -> dict:
    return {
        "maxFiles": MAX_FILES,
        "maxFileBytes": MAX_FILE_BYTES,
        "maxTotalBytes": MAX_TOTAL_BYTES,
        "maxDecodedCharacters": MAX_DECODED_CHARACTERS,
        "maxOutputBytes": MAX_OUTPUT_BYTES,
        "maxTotalOutputBytes": MAX_TOTAL_OUTPUT_BYTES,
    }


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def compute_plan_id(plan: dict) -> str:
    body = {key: value for key, value in plan.items() if key != "planId"}
    return hashlib.sha256(_canonical_json_bytes(body)).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _parse_selections(selections: list[str]) -> list[tuple[str, str]]:
    if not selections:
        raise ToolError("USAGE", "at least one --file REL=CHARSET is required")
    if len(selections) > MAX_FILES:
        raise ToolError(
            "BOUNDS_EXCEEDED",
            "selection exceeds the configured file-count limit",
            {"count": len(selections), "limit": MAX_FILES},
        )
    parsed: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in selections:
        if not isinstance(item, str) or "=" not in item:
            raise ToolError(
                "USAGE",
                "each --file value must use the exact form REL=CHARSET",
                {"value": str(item)},
            )
        relative_raw, charset_raw = item.rsplit("=", 1)
        relative = _normalize_relative(relative_raw)
        _check_suffix(relative)
        _check_reserved_output_path(relative)
        charset = charset_raw.strip().lower()
        if charset not in ALLOWED_CHARSETS:
            raise ToolError(
                "UNSUPPORTED_CHARSET",
                "charset must be explicitly declared as utf-8, gb2312, gbk, "
                "gb18030, or cp1252; no guessing or fallback is performed",
                {"path": relative, "charset": charset_raw},
            )
        key = os.path.normcase(relative)
        if key in seen:
            raise ToolError(
                "DUPLICATE_PATH",
                "each source path may be selected only once",
                {"path": relative},
            )
        seen.add(key)
        parsed.append((relative, charset))
    parsed.sort(key=lambda entry: entry[0])
    return parsed


def _file_summary(file_entry: dict) -> dict:
    findings = file_entry["findings"]
    return {
        "path": file_entry["path"],
        "charset": file_entry["charset"],
        "status": file_entry["status"],
        "sourceSize": file_entry["sourceSize"],
        "sourceSha256": file_entry["sourceSha256"],
        "outputSize": file_entry["outputSize"],
        "outputSha256": file_entry["outputSha256"],
        "blockers": sum(
            1 for finding in findings if finding["severity"] == "blocker"
        ),
        "warnings": sum(
            1 for finding in findings if finding["severity"] == "warning"
        ),
    }


def _format_finding(finding: dict) -> str:
    parts = [f"- [{finding['severity']}] `{finding['code']}`"]
    if finding["line"] is not None:
        parts.append(f"line {finding['line']} col {finding['column']}")
    if finding["byteOffset"] is not None:
        parts.append(f"byte {finding['byteOffset']}")
    parts.append(f"- {finding['message']}")
    if finding["originalBytes"]:
        parts.append(f"bytes `{_fmt_hex(finding['originalBytes'])}`")
    if finding["decodedText"] is not None:
        parts.append(
            "text " + json.dumps(finding["decodedText"], ensure_ascii=False)
        )
    return " ".join(parts)


def _render_preview(plan: dict, analyses: list[Analysis]) -> bytes:
    files = plan["files"]
    blockers = sum(
        1
        for file_entry in files
        for finding in file_entry["findings"]
        if finding["severity"] == "blocker"
    )
    warnings = sum(
        1
        for file_entry in files
        for finding in file_entry["findings"]
        if finding["severity"] == "warning"
    )
    lines = [
        "# Source comment normalization preview",
        "",
        f"- Plan ID: `{plan['planId']}`",
        f"- Source root: `{plan['sourceRoot']}`",
        f"- Status: **{plan['status']}**",
        f"- Files: {len(files)}",
        f"- Blockers: {blockers}",
        f"- Warnings: {warnings}",
        "",
        "This preview is read-only. It is not authorization to modify the "
        "original project, and it does not create a complete migrated project.",
        "",
    ]
    for file_entry, analysis in zip(files, analyses):
        lines.extend(
            [
                f"## `{file_entry['path']}`",
                "",
                f"- Declared charset: `{file_entry['charset']}`",
                f"- Status: **{file_entry['status']}**",
                f"- Source: {file_entry['sourceSize']} bytes, "
                f"`sha256:{file_entry['sourceSha256']}`",
            ]
        )
        if file_entry["outputSha256"] is None:
            lines.append("- Proposed output: none (blocked)")
        else:
            lines.extend(
                [
                    f"- Proposed output: {file_entry['outputSize']} bytes, "
                    f"`sha256:{file_entry['outputSha256']}`",
                    f"- Outside-comment source digest: "
                    f"`sha256:{file_entry['outsideCommentSha256']}`",
                    f"- Outside-comment output digest: "
                    f"`sha256:{file_entry['outputOutsideCommentSha256']}`",
                ]
            )
        newline = file_entry["newline"]
        lines.extend(
            [
                f"- Newlines: CRLF={newline['crlf']}, LF={newline['lf']}, "
                f"CR={newline['cr']}, final={newline['finalSequence']}",
                f"- UTF-8 BOM: {'yes' if file_entry['bom'] else 'no'}",
                f"- Strict decode/encode round-trip: "
                f"{'yes' if file_entry['decodeRoundTrip'] else 'no'}",
                f"- Idempotent: {'yes' if file_entry['idempotent'] else 'no'}",
                f"- Comments found: {file_entry['commentCount']}",
                f"- Non-ASCII comment units: "
                f"{file_entry['commentNonAsciiUnits']}",
                f"- Units changed by this conversion: {file_entry['changedUnits']}",
                "",
            ]
        )
        if file_entry["findings"]:
            lines.extend(["### Findings", ""])
            for finding in file_entry["findings"]:
                lines.append(_format_finding(finding))
            lines.append("")
        else:
            lines.extend(["### Findings", "", "None.", ""])
        lines.extend(["### Diff", ""])
        if analysis.output is None:
            lines.extend(["No proposed output; the file is blocked.", ""])
        elif not analysis.diff_lines:
            lines.extend(["No byte changes.", ""])
        else:
            lines.append("```diff")
            lines.extend(analysis.diff_lines)
            lines.append("```")
            lines.append("")
    return ("\n".join(lines) + "\n").encode("utf-8")

_PLAN_TOP_KEYS = {
    "schemaVersion",
    "kind",
    "helperVersion",
    "sourceRoot",
    "limits",
    "status",
    "files",
    "planId",
}
_PLAN_FILE_KEYS = {
    "path",
    "charset",
    "status",
    "sourceSize",
    "sourceSha256",
    "outputSize",
    "outputSha256",
    "outsideCommentSha256",
    "outputOutsideCommentSha256",
    "commentCount",
    "commentNonAsciiUnits",
    "changedUnits",
    "newline",
    "bom",
    "decodeRoundTrip",
    "idempotent",
    "findings",
}
_FINDING_KEYS = {
    "code",
    "severity",
    "message",
    "byteOffset",
    "line",
    "column",
    "originalBytes",
    "decodedText",
}
_NEWLINE_KEYS = {"crlf", "lf", "cr", "finalNewline", "finalSequence"}


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is not accepted: {value}")


def _read_plan_json(value: str) -> tuple[Path, dict]:
    path = Path(os.fspath(value))
    _check_raw_ancestors(path)
    if not path.exists():
        raise ToolError("PLAN_MISSING", "plan file does not exist", {"path": str(path)})
    data = _read_bytes_limited(path, MAX_PLAN_BYTES, code="PLAN_INVALID")
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        raise ToolError(
            "PLAN_INVALID",
            "plan file is not valid UTF-8",
            {"path": str(path), "reason": error.reason},
        ) from error
    try:
        plan = json.loads(
            text,
            object_pairs_hook=_no_duplicates,
            parse_constant=_reject_json_constant,
        )
    except (ValueError, RecursionError) as error:
        raise ToolError(
            "PLAN_INVALID",
            f"plan file is not valid JSON: {error}",
            {"path": str(path)},
        ) from error
    if not isinstance(plan, dict):
        raise ToolError("PLAN_INVALID", "plan file must contain one JSON object")
    return path, plan


def _exact_int(value: object) -> bool:
    return type(value) is int


def _exact_bool(value: object) -> bool:
    return type(value) is bool


def _exact_str(value: object) -> bool:
    return type(value) is str


def _validate_plan(plan: dict) -> None:
    try:
        _validate_plan_inner(plan)
    except ToolError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, IndexError) as error:
        raise ToolError(
            "PLAN_INVALID",
            f"plan validation failed: {type(error).__name__}: {error}",
        ) from error


def _validate_plan_inner(plan: dict) -> None:
    if not isinstance(plan, dict) or set(plan) != _PLAN_TOP_KEYS:
        raise ToolError(
            "PLAN_INVALID",
            "plan has unexpected or missing top-level fields",
            {"fields": sorted(plan) if isinstance(plan, dict) else []},
        )
    version = plan["schemaVersion"]
    if not _exact_int(version):
        raise ToolError("PLAN_INVALID", "schemaVersion must be an integer")
    if version != PLAN_SCHEMA_VERSION:
        raise ToolError(
            "PLAN_UNSUPPORTED",
            "plan schema version is not supported by this helper",
            {"schemaVersion": version},
        )
    if not _exact_str(plan["kind"]) or plan["kind"] != PLAN_KIND:
        raise ToolError("PLAN_INVALID", "plan kind is not supported")
    if not _exact_str(plan["helperVersion"]):
        raise ToolError("PLAN_INVALID", "helperVersion must be a string")
    if plan["helperVersion"] != HELPER_VERSION:
        raise ToolError(
            "PLAN_UNSUPPORTED",
            "plan was produced by a different helper version",
            {
                "planHelperVersion": plan["helperVersion"],
                "helperVersion": HELPER_VERSION,
            },
        )
    if not _exact_str(plan["sourceRoot"]) or not plan["sourceRoot"]:
        raise ToolError("PLAN_INVALID", "plan sourceRoot is invalid")
    limits = plan["limits"]
    if not isinstance(limits, dict) or set(limits) != set(_limits()):
        raise ToolError("PLAN_INVALID", "plan limits have unexpected or missing fields")
    for key, expected in _limits().items():
        if not _exact_int(limits[key]) or limits[key] != expected:
            raise ToolError(
                "PLAN_UNSUPPORTED",
                "plan limits differ from this helper's enforced limits",
                {"field": key, "planLimits": limits, "limits": _limits()},
            )
    if not _exact_str(plan["status"]):
        raise ToolError("PLAN_INVALID", "plan status must be a string")
    if plan["status"] != "ready":
        raise ToolError(
            "PLAN_BLOCKED",
            "plan is blocked; resolve every blocker and preview again",
            {"status": plan["status"]},
        )
    if not isinstance(plan["files"], list) or not plan["files"]:
        raise ToolError("PLAN_INVALID", "plan must select at least one file")
    if len(plan["files"]) > MAX_FILES:
        raise ToolError(
            "BOUNDS_EXCEEDED",
            "plan exceeds the configured file-count limit",
            {"count": len(plan["files"]), "limit": MAX_FILES},
        )
    if not _is_hex64(plan["planId"]):
        raise ToolError("PLAN_INVALID", "planId must be a lowercase 64-character hex digest")
    seen: set[str] = set()
    total_source = 0
    total_output = 0
    for entry in plan["files"]:
        if not isinstance(entry, dict) or set(entry) != _PLAN_FILE_KEYS:
            raise ToolError(
                "PLAN_INVALID",
                "plan file entry has unexpected or missing fields",
            )
        relative = entry["path"]
        if not _exact_str(relative):
            raise ToolError("PLAN_INVALID", "plan file path must be a string")
        normalized = _normalize_relative(relative)
        if normalized != relative:
            raise ToolError(
                "PLAN_INVALID",
                "plan file path is not canonical project-relative form",
                {"path": relative},
            )
        _check_suffix(relative)
        _check_reserved_output_path(relative)
        key = os.path.normcase(relative)
        if key in seen:
            raise ToolError(
                "PLAN_INVALID",
                "plan contains a duplicate file path",
                {"path": relative},
            )
        seen.add(key)
        if not _exact_str(entry["charset"]) or entry["charset"] not in ALLOWED_CHARSETS:
            raise ToolError(
                "PLAN_INVALID",
                "plan declares an unsupported charset",
                {"path": relative, "charset": entry["charset"]},
            )
        if not _exact_str(entry["status"]):
            raise ToolError("PLAN_INVALID", "invalid file status", {"path": relative})
        if entry["status"] != "ready":
            raise ToolError(
                "PLAN_BLOCKED",
                "plan contains a blocked file",
                {"path": relative, "status": entry["status"]},
            )
        if not _exact_int(entry["sourceSize"]) or entry["sourceSize"] < 0:
            raise ToolError("PLAN_INVALID", "invalid sourceSize", {"path": relative})
        if entry["sourceSize"] > MAX_FILE_BYTES:
            raise ToolError(
                "BOUNDS_EXCEEDED",
                "plan source file exceeds the configured per-file byte limit",
                {"path": relative, "limit": MAX_FILE_BYTES},
            )
        if not _exact_int(entry["outputSize"]) or entry["outputSize"] < 0:
            raise ToolError("PLAN_INVALID", "invalid outputSize", {"path": relative})
        if entry["outputSize"] > MAX_OUTPUT_BYTES:
            raise ToolError(
                "BOUNDS_EXCEEDED",
                "plan output file exceeds the configured per-file output limit",
                {"path": relative, "limit": MAX_OUTPUT_BYTES},
            )
        for field in (
            "sourceSha256",
            "outputSha256",
            "outsideCommentSha256",
            "outputOutsideCommentSha256",
        ):
            if not _is_hex64(entry[field]):
                raise ToolError(
                    "PLAN_INVALID",
                    f"invalid {field} digest",
                    {"path": relative},
                )
        if not _exact_bool(entry["decodeRoundTrip"]) or entry["decodeRoundTrip"] is not True:
            raise ToolError(
                "PLAN_INVALID",
                "decodeRoundTrip must be true",
                {"path": relative},
            )
        if not _exact_bool(entry["idempotent"]) or entry["idempotent"] is not True:
            raise ToolError(
                "PLAN_INVALID",
                "idempotent must be true",
                {"path": relative},
            )
        newline = entry["newline"]
        if not isinstance(newline, dict) or set(newline) != _NEWLINE_KEYS:
            raise ToolError("PLAN_INVALID", "invalid newline evidence", {"path": relative})
        for field in ("crlf", "lf", "cr"):
            if not _exact_int(newline[field]) or newline[field] < 0:
                raise ToolError(
                    "PLAN_INVALID",
                    f"invalid newline {field}",
                    {"path": relative},
                )
        if not _exact_bool(newline["finalNewline"]):
            raise ToolError("PLAN_INVALID", "invalid finalNewline", {"path": relative})
        if (
            not _exact_str(newline["finalSequence"])
            or newline["finalSequence"] not in ("none", "LF", "CR", "CRLF")
        ):
            raise ToolError("PLAN_INVALID", "invalid finalSequence", {"path": relative})
        if newline["finalNewline"] != (newline["finalSequence"] != "none"):
            raise ToolError(
                "PLAN_INVALID",
                "finalNewline and finalSequence are inconsistent",
                {"path": relative},
            )
        if not _exact_bool(entry["bom"]):
            raise ToolError("PLAN_INVALID", "invalid BOM evidence", {"path": relative})
        for field in ("commentCount", "commentNonAsciiUnits", "changedUnits"):
            if not _exact_int(entry[field]) or entry[field] < 0:
                raise ToolError(
                    "PLAN_INVALID",
                    f"invalid {field}",
                    {"path": relative},
                )
        if not isinstance(entry["findings"], list):
            raise ToolError("PLAN_INVALID", "invalid findings list", {"path": relative})
        finding_limit = MAX_PRESENTED_FINDINGS
        if len(entry["findings"]) > finding_limit:
            raise ToolError(
                "BOUNDS_EXCEEDED",
                "plan findings exceed the configured presentation limit",
                {"path": relative, "limit": finding_limit},
            )
        for finding in entry["findings"]:
            if not isinstance(finding, dict) or set(finding) != _FINDING_KEYS:
                raise ToolError(
                    "PLAN_INVALID",
                    "plan finding has unexpected or missing fields",
                    {"path": relative},
                )
            if not _exact_str(finding["code"]) or not _exact_str(finding["message"]):
                raise ToolError("PLAN_INVALID", "invalid finding text")
            if not _exact_str(finding["severity"]) or finding["severity"] not in (
                "blocker",
                "warning",
                "info",
            ):
                raise ToolError("PLAN_INVALID", "invalid finding severity")
            for field in ("byteOffset", "line", "column"):
                value = finding[field]
                if value is not None and (not _exact_int(value) or value < 0):
                    raise ToolError("PLAN_INVALID", f"invalid finding {field}")
            for field in ("originalBytes", "decodedText"):
                value = finding[field]
                if value is not None and not _exact_str(value):
                    raise ToolError("PLAN_INVALID", f"invalid finding {field}")
            if finding["severity"] == "blocker":
                raise ToolError(
                    "PLAN_BLOCKED",
                    "plan contains a blocker finding",
                    {"path": relative, "code": finding["code"]},
                )
        total_source += entry["sourceSize"]
        total_output += entry["outputSize"]
        if total_source > MAX_TOTAL_BYTES:
            raise ToolError(
                "BOUNDS_EXCEEDED",
                "plan exceeds the configured aggregate source byte limit",
                {"limit": MAX_TOTAL_BYTES},
            )
        if total_output > MAX_TOTAL_OUTPUT_BYTES:
            raise ToolError(
                "BOUNDS_EXCEEDED",
                "plan exceeds the configured aggregate output byte limit",
                {"limit": MAX_TOTAL_OUTPUT_BYTES},
            )


def _marker_payload(
    output_dir: Path,
    plan_id: str | None,
    *,
    stage: str,
    written: list[str],
    error: ToolError | None = None,
) -> dict:
    payload = {
        "status": "incomplete",
        "stage": stage,
        "planId": plan_id,
        "outputRoot": output_dir.as_posix(),
        "filesWritten": written,
        "note": "This owned staging directory is incomplete and has no final manifest.",
    }
    if error is not None:
        payload["code"] = error.code
        payload["message"] = error.message
        payload["details"] = error.details
    return payload


def _replace_marker(output_dir: Path, payload: dict) -> bool:
    path = output_dir / "INCOMPLETE.json"
    try:
        if _is_reparse(path) or (path.exists() and not path.is_file()):
            return False
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0)
        descriptor = os.open(path, flags, 0o666)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_json_bytes(payload))
            stream.flush()
            os.fsync(stream.fileno())
        return True
    except OSError:
        return False


def _write_incomplete(
    output_dir: Path,
    error: ToolError,
    written: list[str],
    plan_id: str | None,
) -> None:
    _replace_marker(
        output_dir,
        _marker_payload(
            output_dir,
            plan_id,
            stage="failed",
            written=written,
            error=error,
        ),
    )


def _write_output_file(path: Path, data: bytes) -> None:
    _write_exclusive(path, data)


def preview_plan(
    project_root: str,
    preview_dir: str,
    selections: list[str],
) -> dict:
    root = _validate_project_root(project_root)
    parsed = _parse_selections(selections)
    preview_root = _resolve_external_dir(
        preview_dir,
        root,
        "preview",
        create=True,
        must_not_exist=False,
    )
    analyses: list[Analysis] = []
    total = 0
    total_output = 0
    for relative, charset in parsed:
        data = _read_input(root, relative)
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise ToolError(
                "BOUNDS_EXCEEDED",
                "selection exceeds the configured aggregate byte limit",
                {"limit": MAX_TOTAL_BYTES},
            )
        analysis = analyze_bytes(data, charset, relative)
        if analysis.status == "ready" and analysis.output_size is not None:
            total_output += analysis.output_size
            if total_output > MAX_TOTAL_OUTPUT_BYTES:
                raise ToolError(
                    "BOUNDS_EXCEEDED",
                    "selection exceeds the configured aggregate output byte limit",
                    {"limit": MAX_TOTAL_OUTPUT_BYTES},
                )
        analyses.append(analysis)
    files = [analysis.to_plan_dict() for analysis in analyses]
    status = (
        "blocked"
        if any(file_entry["status"] == "blocked" for file_entry in files)
        else "ready"
    )
    plan = {
        "schemaVersion": PLAN_SCHEMA_VERSION,
        "kind": PLAN_KIND,
        "helperVersion": HELPER_VERSION,
        "sourceRoot": root.as_posix(),
        "limits": _limits(),
        "status": status,
        "files": files,
    }
    plan["planId"] = compute_plan_id(plan)
    plan_bytes = _json_bytes(plan)
    if len(plan_bytes) > MAX_PLAN_BYTES:
        raise ToolError(
            "BOUNDS_EXCEEDED",
            "plan exceeds the configured plan-file byte limit",
            {"limit": MAX_PLAN_BYTES},
        )
    preview_bytes = _render_preview(plan, analyses)
    if len(preview_bytes) > MAX_PREVIEW_BYTES:
        raise ToolError(
            "BOUNDS_EXCEEDED",
            "preview report exceeds the configured preview byte limit",
            {"limit": MAX_PREVIEW_BYTES},
        )
    plan_path = preview_root / "plan.json"
    preview_path = preview_root / "preview.md"

    plan_existed = _check_collision(plan_path, plan_bytes, MAX_PLAN_BYTES)
    preview_existed = _check_collision(preview_path, preview_bytes, MAX_PREVIEW_BYTES)
    if not preview_existed:
        try:
            _write_exclusive(preview_path, preview_bytes)
        except OSError as error:
            raise ToolError(
                "IO_FAILURE",
                f"cannot write preview report: {error}",
                {"path": str(preview_path)},
            ) from error
    if not plan_existed:
        try:
            _write_exclusive(plan_path, plan_bytes)
        except OSError as error:
            raise ToolError(
                "IO_FAILURE",
                f"cannot write plan: {error}",
                {"path": str(plan_path)},
            ) from error

    _, reloaded = _read_plan_json(str(plan_path))
    if compute_plan_id(reloaded) != plan["planId"] or reloaded.get("planId") != plan["planId"]:
        raise ToolError(
            "IO_FAILURE",
            "written plan did not reload with the expected plan ID",
            {"path": str(plan_path)},
        )
    summaries = [_file_summary(file_entry) for file_entry in files]
    blockers = sum(summary["blockers"] for summary in summaries)
    warnings = sum(summary["warnings"] for summary in summaries)
    return {
        "status": status,
        "planId": plan["planId"],
        "planPath": str(plan_path),
        "previewPath": str(preview_path),
        "sourceRoot": plan["sourceRoot"],
        "helperVersion": HELPER_VERSION,
        "blockers": blockers,
        "warnings": warnings,
        "files": summaries,
        "readOnlyPreview": True,
    }


def copy_plan(
    project_root: str,
    plan_file: str,
    expected_plan_id: str,
    output_dir: str,
) -> dict:
    plan_path, plan = _read_plan_json(plan_file)
    _validate_plan(plan)
    if not _is_hex64(expected_plan_id):
        raise ToolError(
            "PLAN_ID_INVALID",
            "expected plan ID must be a lowercase 64-character hex digest",
        )
    recomputed = compute_plan_id(plan)
    if plan.get("planId") != recomputed or expected_plan_id != recomputed:
        raise ToolError(
            "PLAN_ID_MISMATCH",
            "reviewed plan ID does not match the plan content; preview again and "
            "review the new plan",
            {
                "expected": expected_plan_id,
                "planId": plan.get("planId"),
                "recomputed": recomputed,
            },
        )
    root = _validate_project_root(project_root)
    if not _same_path(plan["sourceRoot"], root):
        raise ToolError(
            "PLAN_SOURCE_ROOT_MISMATCH",
            "plan was produced for a different source root",
            {"planSourceRoot": plan["sourceRoot"], "sourceRoot": root.as_posix()},
        )
    if plan["limits"] != _limits():
        raise ToolError(
            "PLAN_UNSUPPORTED",
            "plan limits differ from this helper's enforced limits",
        )

    derived: list[tuple[dict, bytes]] = []
    for entry in plan["files"]:
        relative = entry["path"]
        data = _read_input(root, relative)
        if _sha256(data) != entry["sourceSha256"]:
            raise ToolError(
                "INPUT_CHANGED",
                "source file changed after preview",
                {"path": relative},
            )
        current = analyze_bytes(data, entry["charset"], relative)
        if current.source_sha256 != entry["sourceSha256"]:
            raise ToolError(
                "INPUT_CHANGED",
                "source file changed after preview",
                {"path": relative},
            )
        if current.to_plan_dict() != entry:
            differing = sorted(
                key
                for key in _PLAN_FILE_KEYS
                if current.to_plan_dict().get(key) != entry.get(key)
            )
            raise ToolError(
                "PLAN_TAMPERED",
                "plan content does not match a fresh deterministic derivation",
                {"path": relative, "fields": differing},
            )
        if current.status != "ready" or current.output is None:
            raise ToolError(
                "PLAN_BLOCKED",
                "fresh derivation is blocked; no output was written",
                {"path": relative},
            )
        derived.append((entry, current.output))

    total_output = sum(len(output) for _, output in derived)
    if total_output > MAX_TOTAL_OUTPUT_BYTES:
        raise ToolError(
            "BOUNDS_EXCEEDED",
            "derived output exceeds the configured aggregate output byte limit",
            {"limit": MAX_TOTAL_OUTPUT_BYTES},
        )

    output_root = _resolve_external_dir(
        output_dir,
        root,
        "output",
        create=False,
        must_not_exist=True,
    )
    created = False
    written: list[str] = []
    try:
        try:
            os.mkdir(output_root)
            created = True
        except FileExistsError as error:
            raise ToolError(
                "OUTPUT_EXISTS",
                "output directory already exists; choose a new directory",
                {"path": str(output_root)},
            ) from error
        except OSError as error:
            raise ToolError(
                "IO_FAILURE",
                f"cannot create output directory: {error}",
                {"path": str(output_root)},
            ) from error

        initial_marker = _marker_payload(
            output_root,
            plan["planId"],
            stage="created",
            written=[],
        )
        if not _replace_marker(output_root, initial_marker):
            try:
                os.rmdir(output_root)
                created = False
            except OSError:
                pass
            raise ToolError(
                "IO_FAILURE",
                "cannot write the initial incomplete marker; refusing to create "
                "output without a durable incomplete marker",
                {"path": str(output_root / "INCOMPLETE.json")},
            )
        for reserved_name in ("manifest.json", "manifest.json.partial", "INCOMPLETE.json"):
            reserved = output_root / reserved_name
            if reserved.exists() and not reserved.is_file():
                raise ToolError(
                    "OUTPUT_COLLISION",
                    "a reserved output metadata path is already a non-file",
                    {"path": str(reserved)},
                )

        for entry, output in derived:
            relative = entry["path"]
            target = output_root.joinpath(*relative.split("/"))
            if not _within(target, output_root):
                raise ToolError(
                    "OUTPUT_CONTAINMENT",
                    "planned output path resolves outside the output directory",
                    {"path": relative},
                )
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
            except OSError as error:
                raise ToolError(
                    "IO_FAILURE",
                    f"cannot create output parent directory: {error}",
                    {"path": relative},
                ) from error
            try:
                _write_output_file(target, output)
            except FileExistsError as error:
                raise ToolError(
                    "OUTPUT_COLLISION",
                    "output file already exists; refusing to overwrite",
                    {"path": relative},
                ) from error
            except OSError as error:
                raise ToolError(
                    "IO_FAILURE",
                    f"cannot write output file: {error}",
                    {"path": relative},
                ) from error
            try:
                readback = _read_bytes_limited(target, MAX_OUTPUT_BYTES)
            except ToolError as error:
                try:
                    os.unlink(target)
                except OSError:
                    pass
                raise ToolError(
                    "OUTPUT_VERIFY_FAILED",
                    "output file could not be read back",
                    {"path": relative, "cause": error.code},
                ) from error
            if readback != output:
                try:
                    os.unlink(target)
                except OSError:
                    pass
                raise ToolError(
                    "OUTPUT_VERIFY_FAILED",
                    "output file bytes do not match the derived conversion",
                    {"path": relative},
                )
            written.append(relative)

        for entry, _ in derived:
            current = _read_input(root, entry["path"])
            if _sha256(current) != entry["sourceSha256"]:
                raise ToolError(
                    "INPUT_CHANGED",
                    "source file changed during copy; originals were not written",
                    {"path": entry["path"]},
                )

        manifest_files = []
        for entry, output in derived:
            output_hash = _sha256(output)
            if output_hash != entry["outputSha256"]:
                raise ToolError(
                    "OUTPUT_VERIFY_FAILED",
                    "derived output hash differs from the reviewed plan",
                    {"path": entry["path"]},
                )
            manifest_files.append(
                {
                    "path": entry["path"],
                    "charset": entry["charset"],
                    "sourceSize": entry["sourceSize"],
                    "sourceSha256": entry["sourceSha256"],
                    "outputSize": entry["outputSize"],
                    "outputSha256": entry["outputSha256"],
                    "outsideCommentSha256": entry["outsideCommentSha256"],
                }
            )
        manifest = {
            "schemaVersion": MANIFEST_SCHEMA_VERSION,
            "kind": MANIFEST_KIND,
            "planId": plan["planId"],
            "sourceRoot": plan["sourceRoot"],
            "outputRoot": output_root.as_posix(),
            "copyOnly": True,
            "notAProject": True,
            "note": "These are converted file copies, not a complete migrated or buildable project.",
            "files": manifest_files,
            "totalFiles": len(manifest_files),
            "totalSourceBytes": sum(entry["sourceSize"] for entry in manifest_files),
            "totalOutputBytes": sum(entry["outputSize"] for entry in manifest_files),
            "originalsUnchanged": True,
            "outputsVerified": True,
        }
        manifest_bytes = _json_bytes(manifest)
        manifest_path = output_root / "manifest.json"
        partial_path = output_root / "manifest.json.partial"
        try:
            _write_exclusive(partial_path, manifest_bytes)
        except OSError as error:
            raise ToolError(
                "IO_FAILURE",
                f"cannot write manifest staging file: {error}",
                {"path": str(partial_path)},
            ) from error
        try:
            if _read_bytes_limited(partial_path, MAX_PLAN_BYTES) != manifest_bytes:
                raise ToolError(
                    "OUTPUT_VERIFY_FAILED",
                    "manifest staging file did not verify",
                    {"path": str(partial_path)},
                )
            if manifest_path.exists():
                raise ToolError(
                    "OUTPUT_COLLISION",
                    "manifest already exists; refusing to overwrite",
                    {"path": str(manifest_path)},
                )
            os.rename(partial_path, manifest_path)
        except BaseException:
            try:
                os.unlink(partial_path)
            except OSError:
                pass
            raise

        marker_path = output_root / "INCOMPLETE.json"
        try:
            marker_path.unlink()
        except FileNotFoundError:
            pass
        except OSError as error:
            # The verified manifest is not allowed to make the directory look
            # complete while the durable incomplete marker remains.  Remove the
            # newly created manifest first; the marker is retained on failure.
            try:
                manifest_path.unlink()
            except OSError:
                pass
            raise ToolError(
                "IO_FAILURE",
                f"cannot remove the incomplete marker after manifest verification: {error}",
                {"path": str(marker_path)},
            ) from error

        summaries = [_file_summary(entry) for entry in plan["files"]]
        return {
            "status": "ok",
            "copyOnly": True,
            "notAProject": True,
            "planId": plan["planId"],
            "planPath": str(plan_path),
            "outputDir": str(output_root),
            "manifestPath": str(manifest_path),
            "files": summaries,
            "originalsUnchanged": True,
            "outputsVerified": True,
        }
    except ToolError as error:
        if created:
            _write_incomplete(output_root, error, written, plan.get("planId"))
        raise
    except OSError as error:
        wrapped = ToolError(
            "IO_FAILURE",
            f"copy failed: {error}",
            {"outputDir": str(output_root)},
        )
        if created:
            _write_incomplete(output_root, wrapped, written, plan.get("planId"))
        raise wrapped from error


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="normalize_comments.py",
        description=(
            "Preview or copy comment-only UTF-8 conversions for explicitly "
            "declared C/C++ source charsets."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    preview = subparsers.add_parser(
        "preview",
        help="read-only preview and external plan generation",
    )
    preview.add_argument("--project-root", required=True)
    preview.add_argument("--preview-dir", required=True)
    preview.add_argument(
        "--file",
        action="append",
        required=True,
        metavar="REL=CHARSET",
        help="project-root-relative C/C++ path and explicit charset",
    )
    copy = subparsers.add_parser(
        "copy",
        help="revalidate a reviewed plan and copy converted files",
    )
    copy.add_argument("--project-root", required=True)
    copy.add_argument("--plan", required=True)
    copy.add_argument("--plan-id", required=True)
    copy.add_argument("--output-dir", required=True)
    return parser


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="strict")
        except (AttributeError, OSError):
            pass
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "preview":
            payload = preview_plan(
                args.project_root,
                args.preview_dir,
                args.file,
            )
            _emit(payload)
            return 0 if payload["status"] == "ready" else 2
        if not _is_hex64(args.plan_id):
            raise ToolError(
                "PLAN_ID_INVALID",
                "expected plan ID must be a lowercase 64-character hex digest",
            )
        payload = copy_plan(
            args.project_root,
            args.plan,
            args.plan_id,
            args.output_dir,
        )
        _emit(payload)
        return 0
    except ToolError as error:
        _emit(
            {
                "status": "failed",
                "code": error.code,
                "message": error.message,
                "details": error.details,
            }
        )
        return 2
    except OSError as error:
        _emit(
            {
                "status": "failed",
                "code": "IO_FAILURE",
                "message": str(error),
                "details": {},
            }
        )
        return 2
    except Exception as error:  # pragma: no cover - last-resort boundary
        _emit(
            {
                "status": "failed",
                "code": "INTERNAL_ERROR",
                "message": f"{type(error).__name__}: {error}",
                "details": {},
            }
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
