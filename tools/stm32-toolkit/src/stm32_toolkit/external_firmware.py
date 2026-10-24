"""Offline external-firmware import, admission, and imported-image programming.

This module owns the source-only external-firmware slice:

* strict ELF/AXF, Intel HEX and BIN analysis into deterministic PT_LOAD
  segments;
* a deterministic ARM ELF32 programming image whose SHA-256 is distinct from
  the original source SHA-256;
* a separate, immutable external-import store derived from the bound project
  root and the machine-owned data root;
* offline admission that reconstructs the image instead of trusting stored
  assertions; and
* the owned programming routine used by one authorized imported-image flash.

The store never fabricates a managed project model.  It does not require a
manifest, Git, a build receipt, or an SVD, and it cannot admit debug, Monitor,
Target tests, or a legacy build identity.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import re
import stat
import struct
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from elftools.elf.elffile import ELFFile

from stm32_toolkit import __version__
from stm32_toolkit.build.identity import utc_now_rfc3339
from stm32_toolkit.paths import WorkspacePaths, require_safe_session_id
from stm32_toolkit.probe.backend import FlashBackendReport
from stm32_toolkit.result import OperationResult

_IMPORT_OPERATION = "stm32_firmware_import"
_ADMIT_OPERATION = "stm32_firmware_admit"
_FLASH_OPERATION = "stm32_flash_imported"

_KIND = "stm32-external-firmware-import"
_SCHEMA_VERSION = 1
_PLAN_KIND = "stm32-external-firmware-import-plan"
_RECEIPT_KIND = "stm32-external-flash-receipt"

_SOURCE_LIMIT = 64 * 1024 * 1024
_IMAGE_LIMIT = 64 * 1024 * 1024
_MAX_SEGMENTS = 1024
_MAX_REGIONS = 32
# Bounds the intermediate record list while parsing Intel HEX.  Payload bytes
# are additionally capped by the normalized-image limit.  Lines are iterated
# without materializing the whole file as a Python list of strings.
_MAX_HEX_RECORDS = 1_048_576
_MAX_HEX_LINES = _MAX_HEX_RECORDS + 65_536
_MAX_HEX_LINE_BYTES = 11 + 255 * 2
_RECORD_LIMIT = 1024 * 1024
_RECEIPT_LIMIT = 64 * 1024
_MAX_READ_BYTES = 32_768
_ADDRESS_LIMIT = 1 << 32
_FLASH_START = 0x0800_0000
_FLASH_END = 0x1000_0000

_IMAGE_NAME = "image.elf"
_RECORD_NAME = "record.json"
_FIRMWARE_DIR = "firmware-imports"
_RECEIPT_DIR = "flash-receipts"

_FORMAT_SUFFIX = {"elf": ".elf", "hex": ".hex", "bin": ".bin"}
_TARGET_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
# Informational creation time only; it is not part of the deterministic
# identity and proves no cryptographic authenticity.
_TIMESTAMP_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$"
)
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_WINDOWS_DEVICE_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}

_PROVENANCE_GUIDANCE = (
    "External firmware is an imported source snapshot: it is not a current "
    "build, it does not create a managed project or build identity, and it "
    "cannot admit debug, Monitor, Target tests, or legacy flash evidence. "
    "Re-import after rebuilding to obtain a new deterministic identity."
)
_AUTHORIZATION_GUIDANCE = (
    "Review the PLAN response, then repeat the same request with that exact "
    "planId and authorized=true. Import authorization covers only the "
    "immutable offline import copy; probe selection and programming require "
    "a separate explicit stm32_flash_imported authorization."
)


class ExternalFirmwareError(Exception):
    """Stable, bounded failure for the external-firmware slice."""

    def __init__(
        self,
        code: str,
        message: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


def _fail(
    code: str,
    message: str,
    *,
    field: str | None = None,
    rule: str | None = None,
    guidance: str | None = None,
    **extra: object,
) -> ExternalFirmwareError:
    details: dict[str, object] = {}
    if field is not None:
        details["field"] = field
    if rule is not None:
        details["rule"] = rule
    if guidance is not None:
        details["guidance"] = guidance
    details.update(extra)
    return ExternalFirmwareError(code, message, details)


def _failure(
    operation: str, error: ExternalFirmwareError
) -> OperationResult[None]:
    return OperationResult.failure(
        operation, error.code, error.message, error.details
    )


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _digest(value: str, field: str) -> str:
    if (
        not isinstance(value, str)
        or _DIGEST_PATTERN.fullmatch(value) is None
    ):
        raise _fail(
            "FIRMWARE_INPUT_INVALID",
            "Firmware input is invalid",
            field=field,
            rule="sha256",
            guidance=(
                "Pass the exact lowercase SHA-256 of the original firmware "
                "file; never substitute the normalized image hash."
            ),
        )
    return value


def _portable_path(value: object, field: str = "firmwarePath") -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 1024
        or value.startswith(("/", "\\"))
        or "\\" in value
        or ":" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise _fail(
            "FIRMWARE_PATH_UNSAFE",
            "Firmware path is unavailable or unsafe",
            field=field,
            rule="portableRelativePath",
            guidance=(
                "Use a forward-slash path relative to the bound project root; "
                "absolute, drive, UNC, ADS, control-character and traversal "
                "paths are rejected."
            ),
        )
    parts = value.split("/")
    if any(
        not part
        or part in {".", ".."}
        or part != part.rstrip(" .")
        or part.split(".")[0].casefold() in _WINDOWS_DEVICE_NAMES
        for part in parts
    ):
        raise _fail(
            "FIRMWARE_PATH_UNSAFE",
            "Firmware path is unavailable or unsafe",
            field=field,
            rule="portableRelativePath",
            guidance=(
                "Use a forward-slash path relative to the bound project root; "
                "absolute, drive, UNC, ADS, control-character and traversal "
                "paths are rejected."
            ),
        )
    try:
        if len(value.encode("utf-8")) > 4096:
            raise ValueError
    except UnicodeEncodeError:
        raise _fail(
            "FIRMWARE_PATH_UNSAFE",
            "Firmware path is unavailable or unsafe",
            field=field,
            rule="portableRelativePath",
        ) from None
    except ValueError:
        raise _fail(
            "FIRMWARE_PATH_UNSAFE",
            "Firmware path is unavailable or unsafe",
            field=field,
            rule="portableRelativePath",
        ) from None
    return value


def _redirect(path: Path, info: os.stat_result) -> bool:
    return path.is_symlink() or bool(
        getattr(info, "st_file_attributes", 0) & _REPARSE_POINT
    )


def _lstat(path: Path) -> os.stat_result | None:
    try:
        return os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError:
        raise _fail(
            "FIRMWARE_PATH_UNSAFE",
            "Firmware path is unavailable or unsafe",
            rule="inspection",
        ) from None


def _walk_unredirected(lexical: Path, *, must_exist: bool) -> None:
    """Reject redirects, non-directories and unavailable components."""

    current = Path(lexical.anchor)
    for component in lexical.parts[1:] if lexical.anchor else lexical.parts:
        current /= component
        info = _lstat(current)
        if info is None:
            if must_exist:
                raise _fail(
                    "FIRMWARE_PATH_UNSAFE",
                    "Firmware path is unavailable or unsafe",
                    rule="missing",
                )
            return
        if _redirect(current, info) or not stat.S_ISDIR(info.st_mode):
            raise _fail(
                "FIRMWARE_PATH_UNSAFE",
                "Firmware path is unavailable or unsafe",
                rule="redirect",
            )


def _canonical_root(value: object, field: str) -> Path:
    if not isinstance(value, Path):
        raise _fail(
            "FIRMWARE_INPUT_INVALID",
            "Firmware input is invalid",
            field=field,
            rule="type",
            guidance="Pass the documented absolute root path.",
        )
    try:
        lexical = value.expanduser().absolute()
    except (OSError, RuntimeError, ValueError):
        raise _fail(
            "FIRMWARE_INPUT_INVALID",
            "Firmware input is invalid",
            field=field,
            rule="directory",
        ) from None
    _walk_unredirected(lexical, must_exist=True)
    try:
        canonical = lexical.resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        raise _fail(
            "FIRMWARE_INPUT_INVALID",
            "Firmware input is invalid",
            field=field,
            rule="directory",
        ) from None
    if not canonical.is_dir():
        raise _fail(
            "FIRMWARE_INPUT_INVALID",
            "Firmware input is invalid",
            field=field,
            rule="directory",
        )
    return canonical


def _canonical_data_root(value: object, project_root: Path) -> Path:
    if not isinstance(value, Path):
        raise _fail(
            "FIRMWARE_INPUT_INVALID",
            "Firmware input is invalid",
            field="data_root",
            rule="type",
            guidance=(
                "Pass the machine-owned Toolkit data root as a path outside "
                "the project root."
            ),
        )
    try:
        lexical = value.expanduser().absolute()
    except (OSError, RuntimeError, ValueError):
        raise _fail(
            "FIRMWARE_INPUT_INVALID",
            "Firmware input is invalid",
            field="data_root",
            rule="externalDirectory",
        ) from None
    _walk_unredirected(lexical, must_exist=False)
    try:
        canonical = lexical.resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        raise _fail(
            "FIRMWARE_INPUT_INVALID",
            "Firmware input is invalid",
            field="data_root",
            rule="externalDirectory",
        ) from None
    try:
        canonical.relative_to(project_root)
    except ValueError:
        return canonical
    raise _fail(
        "FIRMWARE_INPUT_INVALID",
        "Data root must remain outside the project root",
        field="data_root",
        rule="outsideProjectRoot",
        guidance=(
            "Choose a persistent data root outside the project tree; do not "
            "store machine state inside the project."
        ),
    )


def _safe_session_id(value: object) -> str:
    try:
        return require_safe_session_id(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise _fail(
            "FIRMWARE_INPUT_INVALID",
            "Firmware input is invalid",
            field="session_id",
            rule="format",
            guidance=(
                "Use a filesystem-safe session id: lowercase letters, digits, "
                "'-' or '_', starting with a letter or digit."
            ),
        ) from None


# ---------------------------------------------------------------------------
# Image formats
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImageSegment:
    address: int
    data: bytes

    def summary(self) -> dict[str, int]:
        return {"address": self.address, "length": len(self.data)}


@dataclass(frozen=True)
class ParsedImage:
    segments: tuple[ImageSegment, ...]
    entry_point: int | None


def _checked_segments(
    segments: Iterable[tuple[int, bytes]], *, rule: str
) -> tuple[ImageSegment, ...]:
    collected: list[ImageSegment] = []
    total = 0
    for address, payload in segments:
        if (
            type(address) is not int
            or not 0 <= address < _ADDRESS_LIMIT
            or not payload
            or address + len(payload) > _ADDRESS_LIMIT
        ):
            raise _fail(
                "FIRMWARE_IMAGE_INVALID",
                "Firmware image is invalid",
                rule=rule,
            )
        total += len(payload)
        if total > _IMAGE_LIMIT or len(collected) + 1 > _MAX_SEGMENTS:
            raise _fail(
                "FIRMWARE_IMAGE_INVALID",
                "Firmware image exceeds the programming limit",
                rule="size",
                limit=_IMAGE_LIMIT,
                maxSegments=_MAX_SEGMENTS,
            )
        collected.append(ImageSegment(address, bytes(payload)))
    collected.sort(key=lambda item: item.address)
    if not collected:
        raise _fail(
            "FIRMWARE_IMAGE_INVALID",
            "Firmware image contains no programmable data",
            rule=rule,
        )
    for previous, current in zip(collected, collected[1:]):
        if previous.address + len(previous.data) > current.address:
            raise _fail(
                "FIRMWARE_IMAGE_INVALID",
                "Firmware image contains overlapping segments",
                rule="overlap",
            )
    return tuple(collected)


def _parse_elf(data: bytes) -> ParsedImage:
    try:
        elf = ELFFile(io.BytesIO(data))
        header = elf.header
        ident = header["e_ident"]
    except Exception:
        raise _fail(
            "FIRMWARE_IMAGE_INVALID",
            "Firmware image is invalid",
            rule="elf",
            guidance=(
                "AXF files are parsed as ELF; pass a complete ARM ELF32 "
                "executable produced by the original toolchain."
            ),
        ) from None
    if (
        ident["EI_CLASS"] != "ELFCLASS32"
        or ident["EI_DATA"] != "ELFDATA2LSB"
        or ident.get("EI_VERSION") != "EV_CURRENT"
        or header["e_type"] != "ET_EXEC"
        or header["e_machine"] != "EM_ARM"
    ):
        raise _fail(
            "FIRMWARE_IMAGE_INVALID",
            "Firmware image is not a supported ARM ELF executable",
            rule="elfHeader",
        )
    try:
        ehsize = int(header["e_ehsize"])
        phoff = int(header["e_phoff"])
        phnum = int(header["e_phnum"])
        phentsize = int(header["e_phentsize"])
    except Exception:
        raise _fail(
            "FIRMWARE_IMAGE_INVALID",
            "Firmware image is invalid",
            rule="elfTable",
        ) from None
    if (
        ehsize != 52
        or phentsize != 32
        or phoff < 52
        or not 0 <= phnum <= _MAX_SEGMENTS
        or phoff + phnum * phentsize > len(data)
    ):
        raise _fail(
            "FIRMWARE_IMAGE_INVALID",
            "Firmware image tables are invalid",
            rule="elfTable",
        )
    entry = int(header["e_entry"])
    if not 0 <= entry < _ADDRESS_LIMIT:
        raise _fail(
            "FIRMWARE_IMAGE_INVALID",
            "Firmware image is invalid",
            rule="entryPoint",
        )
    # First pass: validate every PT_LOAD bound and accumulate the aggregate
    # size before any payload copy.  Aliasing file offsets and distinct
    # physical addresses both count toward the same programming limit.
    planned: list[tuple[object, int, int]] = []
    total = 0
    try:
        for segment in elf.iter_segments():
            kind = segment.header.p_type
            if kind == "PT_DYNAMIC":
                raise _fail(
                    "FIRMWARE_IMAGE_INVALID",
                    "Dynamic firmware images are not supported",
                    rule="dynamic",
                )
            if kind != "PT_LOAD":
                continue
            filesz = int(segment.header.p_filesz)
            memsz = int(segment.header.p_memsz)
            offset = int(segment.header.p_offset)
            address = int(segment.header.p_paddr)
            if filesz == 0:
                continue
            if (
                filesz > memsz
                or offset < 0
                or offset + filesz > len(data)
                or address < 0
                or address + filesz > _ADDRESS_LIMIT
            ):
                raise _fail(
                    "FIRMWARE_IMAGE_INVALID",
                    "Firmware image is invalid",
                    rule="segmentBounds",
                )
            total += filesz
            if total > _IMAGE_LIMIT or len(planned) + 1 > _MAX_SEGMENTS:
                raise _fail(
                    "FIRMWARE_IMAGE_INVALID",
                    "Firmware image exceeds the programming limit",
                    rule="size",
                    limit=_IMAGE_LIMIT,
                    maxSegments=_MAX_SEGMENTS,
                )
            planned.append((segment, address, filesz))
    except ExternalFirmwareError:
        raise
    except Exception:
        raise _fail(
            "FIRMWARE_IMAGE_INVALID",
            "Firmware image is invalid",
            rule="elfSegments",
        ) from None
    # Second pass: copy only the bounded, validated payloads.
    raw: list[tuple[int, bytes]] = []
    try:
        for segment, address, filesz in planned:
            payload = bytes(segment.data())
            if len(payload) != filesz:
                raise _fail(
                    "FIRMWARE_IMAGE_INVALID",
                    "Firmware image is truncated",
                    rule="segmentData",
                )
            raw.append((address, payload))
    except ExternalFirmwareError:
        raise
    except Exception:
        raise _fail(
            "FIRMWARE_IMAGE_INVALID",
            "Firmware image is invalid",
            rule="elfSegments",
        ) from None
    return ParsedImage(_checked_segments(raw, rule="segments"), entry)


def _iter_hex_lines(data: bytes):
    """Yield bounded ASCII Intel HEX lines without a whole-file line list."""

    if not data:
        raise _fail(
            "FIRMWARE_IMAGE_INVALID",
            "Intel HEX image is empty",
            rule="hexEmpty",
        )
    start = 0
    total = len(data)
    seen = 0
    while start <= total:
        end = data.find(b"\n", start)
        if end < 0:
            chunk = data[start:]
            next_start: int | None = None
        else:
            chunk = data[start:end]
            next_start = end + 1
        if chunk.endswith(b"\r"):
            chunk = chunk[:-1]
        if chunk:
            if len(chunk) > _MAX_HEX_LINE_BYTES:
                raise _fail(
                    "FIRMWARE_IMAGE_INVALID",
                    "Intel HEX record length is invalid",
                    rule="hexLength",
                )
            try:
                line = chunk.decode("ascii")
            except UnicodeDecodeError:
                raise _fail(
                    "FIRMWARE_IMAGE_INVALID",
                    "Intel HEX image is not strict ASCII",
                    rule="hexAscii",
                ) from None
            if any(ord(character) < 32 or ord(character) == 127 for character in line):
                raise _fail(
                    "FIRMWARE_IMAGE_INVALID",
                    "Intel HEX image contains invalid characters",
                    rule="hexAscii",
                )
            seen += 1
            if seen > _MAX_HEX_LINES:
                raise _fail(
                    "FIRMWARE_IMAGE_INVALID",
                    "Intel HEX image exceeds the record limit",
                    rule="size",
                    limit=_MAX_HEX_LINES,
                )
            yield line
        elif next_start is not None:
            # An internal blank line is not a valid Intel HEX record; let the
            # record parser reject it with the stable hexRecord diagnostic.
            yield ""
        if next_start is None:
            break
        start = next_start


def _parse_hex(data: bytes) -> ParsedImage:
    records: list[tuple[int, bytes]] = []
    base = 0
    entry: int | None = None
    seen_eof = False
    total = 0
    for line in _iter_hex_lines(data):
        if seen_eof:
            raise _fail(
                "FIRMWARE_IMAGE_INVALID",
                "Intel HEX image has records after EOF",
                rule="hexTrailing",
            )
        if not line.startswith(":"):
            raise _fail(
                "FIRMWARE_IMAGE_INVALID",
                "Intel HEX image is malformed",
                rule="hexRecord",
            )
        body = line[1:]
        if (
            len(body) < 10
            or len(body) % 2
            or any(character not in "0123456789abcdefABCDEF" for character in body)
        ):
            raise _fail(
                "FIRMWARE_IMAGE_INVALID",
                "Intel HEX image is malformed",
                rule="hexRecord",
            )
        count = int(body[0:2], 16)
        if len(body) != 8 + count * 2 + 2:
            raise _fail(
                "FIRMWARE_IMAGE_INVALID",
                "Intel HEX record length is invalid",
                rule="hexLength",
            )
        raw = bytes.fromhex(body)
        if sum(raw) & 0xFF:
            raise _fail(
                "FIRMWARE_IMAGE_INVALID",
                "Intel HEX checksum is invalid",
                rule="hexChecksum",
            )
        address = int(body[2:6], 16)
        record_type = int(body[6:8], 16)
        payload = raw[4 : 4 + count]
        if record_type == 0x00:
            absolute = base + address
            if absolute + count > _ADDRESS_LIMIT:
                raise _fail(
                    "FIRMWARE_IMAGE_INVALID",
                    "Intel HEX address wraps the 32-bit address space",
                    rule="hexAddress",
                )
            if count:
                total += count
                if total > _IMAGE_LIMIT or len(records) + 1 > _MAX_HEX_RECORDS:
                    raise _fail(
                        "FIRMWARE_IMAGE_INVALID",
                        "Intel HEX image exceeds the programming limit",
                        rule="size",
                        limit=_IMAGE_LIMIT,
                        maxRecords=_MAX_HEX_RECORDS,
                    )
                records.append((absolute, payload))
            continue
        if record_type == 0x01:
            if count != 0 or address != 0:
                raise _fail(
                    "FIRMWARE_IMAGE_INVALID",
                    "Intel HEX EOF record is invalid",
                    rule="hexEof",
                )
            seen_eof = True
            continue
        if record_type in (0x02, 0x04):
            # Extended addressing is a state change and may occur repeatedly,
            # including after data records (ordinary 64 KiB crossing).
            if count != 2 or address != 0:
                raise _fail(
                    "FIRMWARE_IMAGE_INVALID",
                    "Intel HEX extended address record is invalid",
                    rule="hexMetadata",
                )
            shift = 4 if record_type == 0x02 else 16
            base = int.from_bytes(payload, "big") << shift
            if base >= _ADDRESS_LIMIT:
                raise _fail(
                    "FIRMWARE_IMAGE_INVALID",
                    "Intel HEX extended address is invalid",
                    rule="hexMetadata",
                )
            continue
        if record_type in (0x03, 0x05):
            if count != 4 or address != 0 or entry is not None:
                raise _fail(
                    "FIRMWARE_IMAGE_INVALID",
                    "Intel HEX start address record is invalid",
                    rule="hexStart",
                )
            if record_type == 0x03:
                # Segment form: CS:IP, so the linear address is CS*16 + IP.
                cs = int.from_bytes(payload[0:2], "big")
                ip = int.from_bytes(payload[2:4], "big")
                value = (cs << 4) + ip
            else:
                value = int.from_bytes(payload, "big")
            if value >= _ADDRESS_LIMIT:
                raise _fail(
                    "FIRMWARE_IMAGE_INVALID",
                    "Intel HEX start address is invalid",
                    rule="hexStart",
                )
            entry = value
            continue
        raise _fail(
            "FIRMWARE_IMAGE_INVALID",
            "Intel HEX record type is unsupported",
            rule="hexType",
        )
    if not seen_eof:
        raise _fail(
            "FIRMWARE_IMAGE_INVALID",
            "Intel HEX image is missing its EOF record",
            rule="hexEof",
        )
    records.sort(key=lambda item: item[0])
    merged: list[tuple[int, bytearray]] = []
    for address, payload in records:
        if merged:
            previous_address, previous_payload = merged[-1]
            previous_end = previous_address + len(previous_payload)
            if address < previous_end:
                raise _fail(
                    "FIRMWARE_IMAGE_INVALID",
                    "Intel HEX image contains overlapping data",
                    rule="overlap",
                )
            if address == previous_end:
                # Linear-time contiguous accumulation.
                previous_payload.extend(payload)
                continue
        if len(merged) + 1 > _MAX_SEGMENTS:
            raise _fail(
                "FIRMWARE_IMAGE_INVALID",
                "Intel HEX image exceeds the segment limit",
                rule="size",
                maxSegments=_MAX_SEGMENTS,
            )
        merged.append((address, bytearray(payload)))
    segments = [(address, bytes(payload)) for address, payload in merged]
    return ParsedImage(_checked_segments(segments, rule="hexSegments"), entry)


def _parse_bin(data: bytes, base_address: int | None) -> ParsedImage:
    if base_address is None:
        raise _fail(
            "FIRMWARE_INPUT_INVALID",
            "Firmware input is invalid",
            field="baseAddress",
            rule="required",
            guidance=(
                "BIN images have no address metadata; pass the exact reviewed "
                "uint32 baseAddress. The Toolkit never infers a boot address."
            ),
        )
    if (
        type(base_address) is not int
        or not 0 <= base_address < _ADDRESS_LIMIT
        or base_address + len(data) > _ADDRESS_LIMIT
    ):
        raise _fail(
            "FIRMWARE_INPUT_INVALID",
            "Firmware input is invalid",
            field="baseAddress",
            rule="range",
            guidance="Pass an exact uint32 base address that fits the image.",
        )
    if not data:
        raise _fail(
            "FIRMWARE_IMAGE_INVALID",
            "Firmware image contains no programmable data",
            rule="empty",
        )
    return ParsedImage((ImageSegment(base_address, bytes(data)),), None)


def _normalized_elf(
    segments: tuple[ImageSegment, ...], entry_point: int | None
) -> bytes:
    count = len(segments)
    offset = 52 + 32 * count
    ident = b"\x7fELF" + bytes((1, 1, 1, 0)) + b"\x00" * 8
    header = ident + struct.pack(
        "<HHIIIIIHHHHHH",
        2,  # ET_EXEC
        40,  # EM_ARM
        1,  # EV_CURRENT
        entry_point if entry_point is not None else 0,
        52,  # e_phoff
        0,  # e_shoff
        0,  # e_flags
        52,  # e_ehsize
        32,  # e_phentsize
        count,
        0,  # e_shentsize
        0,  # e_shnum
        0,  # e_shstrndx
    )
    headers = bytearray()
    payload = bytearray()
    cursor = offset
    for segment in segments:
        headers.extend(
            struct.pack(
                "<IIIIIIII",
                1,  # PT_LOAD
                cursor,
                segment.address,
                segment.address,
                len(segment.data),
                len(segment.data),
                5,  # PF_R | PF_X
                1,  # no alignment requirement; p_offset/p_vaddr may differ mod 4
            )
        )
        payload.extend(segment.data)
        cursor += len(segment.data)
        if cursor > _IMAGE_LIMIT:
            raise _fail(
                "FIRMWARE_IMAGE_INVALID",
                "Firmware image exceeds the programming limit",
                rule="size",
                limit=_IMAGE_LIMIT,
            )
    if offset + len(payload) > _IMAGE_LIMIT:
        raise _fail(
            "FIRMWARE_IMAGE_INVALID",
            "Firmware image exceeds the programming limit",
            rule="size",
            limit=_IMAGE_LIMIT,
        )
    return bytes(header + headers + payload)


# ---------------------------------------------------------------------------
# Flash-region allowlist
# ---------------------------------------------------------------------------


def _validate_regions(value: object) -> tuple[tuple[int, int], ...]:
    if type(value) is not tuple or not 1 <= len(value) <= _MAX_REGIONS:
        raise _fail(
            "FIRMWARE_INPUT_INVALID",
            "Firmware input is invalid",
            field="flashRegions",
            rule="count",
            guidance=(
                "Pass 1..32 exact {start,length} integer pairs reviewed for "
                "this target; the allowlist is a declaration, not a measured "
                "chip capacity."
            ),
        )
    pairs: list[tuple[int, int]] = []
    for item in value:
        if type(item) is not tuple or len(item) != 2:
            raise _fail(
                "FIRMWARE_INPUT_INVALID",
                "Firmware input is invalid",
                field="flashRegions",
                rule="shape",
            )
        start, length = item
        if type(start) is not int or type(length) is not int:
            raise _fail(
                "FIRMWARE_INPUT_INVALID",
                "Firmware input is invalid",
                field="flashRegions",
                rule="integer",
                guidance="Use JSON integers; booleans, strings and floats are rejected.",
            )
        if (
            not _FLASH_START <= start < _FLASH_END
            or length <= 0
            or start + length > _FLASH_END
            or start + length > _ADDRESS_LIMIT
        ):
            raise _fail(
                "FIRMWARE_FLASH_REGION_INVALID",
                "Flash region declaration is invalid",
                field="flashRegions",
                rule="internalFlash",
                guidance=(
                    "Declare only STM32 internal application Flash addresses "
                    "with 0x08000000 <= start < end <= 0x10000000. RAM, "
                    "system, option-byte, OTP and external Flash regions are "
                    "out of scope."
                ),
            )
        pairs.append((start, length))
    if pairs != sorted(pairs):
        raise _fail(
            "FIRMWARE_FLASH_REGION_INVALID",
            "Flash region declaration is not canonical",
            field="flashRegions",
            rule="sorted",
            guidance="Sort regions by ascending start address.",
        )
    for (start, length), (next_start, _next_length) in zip(pairs, pairs[1:]):
        if start + length > next_start:
            raise _fail(
                "FIRMWARE_FLASH_REGION_INVALID",
                "Flash region declaration contains overlapping regions",
                field="flashRegions",
                rule="overlap",
            )
    return tuple(pairs)


def _segments_fit_regions(
    segments: tuple[ImageSegment, ...], regions: tuple[tuple[int, int], ...]
) -> None:
    for segment in segments:
        end = segment.address + len(segment.data)
        if not any(
            start <= segment.address and end <= start + length
            for start, length in regions
        ):
            raise _fail(
                "FIRMWARE_FLASH_REGION_INVALID",
                "Firmware segment is outside the declared Flash regions",
                field="flashRegions",
                rule="segment",
                address=segment.address,
                length=len(segment.data),
                guidance=(
                    "A programmed segment must fit entirely inside one "
                    "declared region. The Toolkit never drops, wraps, or "
                    "fills gaps around undeclared addresses."
                ),
            )


# ---------------------------------------------------------------------------
# Source-file access and deterministic identity
# ---------------------------------------------------------------------------


def _read_project_file(root: Path, relative: str, limit: int) -> bytes:
    parts = relative.split("/")
    current = root
    for index, component in enumerate(parts):
        current /= component
        info = _lstat(current)
        if info is None:
            raise _fail(
                "FIRMWARE_PATH_UNSAFE",
                "Firmware path is unavailable or unsafe",
                field="firmwarePath",
                rule="missing",
            )
        if _redirect(current, info):
            raise _fail(
                "FIRMWARE_PATH_UNSAFE",
                "Firmware path is unavailable or unsafe",
                field="firmwarePath",
                rule="redirect",
            )
        if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise _fail(
                "FIRMWARE_PATH_UNSAFE",
                "Firmware path is unavailable or unsafe",
                field="firmwarePath",
                rule="path",
            )
    if not stat.S_ISREG(info.st_mode):
        raise _fail(
            "FIRMWARE_PATH_UNSAFE",
            "Firmware path is unavailable or unsafe",
            field="firmwarePath",
            rule="regularFile",
        )
    if info.st_size > limit:
        raise _fail(
            "FIRMWARE_SOURCE_TOO_LARGE",
            "Firmware source exceeds the 64 MiB import limit",
            field="firmwarePath",
            rule="size",
            limit=limit,
        )
    try:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        descriptor = os.open(current, flags)
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino)
                or opened.st_size != info.st_size
            ):
                raise OSError("source changed")
            chunks = bytearray()
            while len(chunks) <= limit:
                chunk = os.read(descriptor, min(65_536, limit + 1 - len(chunks)))
                if not chunk:
                    break
                chunks.extend(chunk)
        finally:
            os.close(descriptor)
    except OSError:
        raise _fail(
            "FIRMWARE_PATH_UNSAFE",
            "Firmware path is unavailable or unsafe",
            field="firmwarePath",
            rule="unreadable",
        ) from None
    if len(chunks) > limit or len(chunks) != info.st_size:
        raise _fail(
            "FIRMWARE_SOURCE_TOO_LARGE",
            "Firmware source exceeds the 64 MiB import limit",
            field="firmwarePath",
            rule="size",
            limit=limit,
        )
    return bytes(chunks)


def _identity_document(
    *,
    project_root: Path,
    data_root: Path,
    workspace_id: str,
    source_path: str,
    format: str,
    source_sha256: str,
    source_size: int,
    base_address: int | None,
    target: str,
    regions: tuple[tuple[int, int], ...],
    image_sha256: str,
    image_size: int,
    segments: tuple[ImageSegment, ...],
    entry_point: int | None,
) -> dict[str, object]:
    return {
        "kind": _KIND,
        "schemaVersion": _SCHEMA_VERSION,
        "toolkitVersion": __version__,
        "workspaceId": workspace_id,
        "projectRootSha256": _root_binding(project_root),
        "dataRootSha256": _root_binding(data_root),
        "sourcePath": source_path,
        "format": format,
        "sourceSha256": source_sha256,
        "sourceSize": source_size,
        "baseAddress": base_address,
        "target": target,
        "flashRegions": [
            {"start": start, "length": length} for start, length in regions
        ],
        "imageSha256": image_sha256,
        "imageSize": image_size,
        "segments": [segment.summary() for segment in segments],
        "entryPoint": entry_point,
    }


@dataclass(frozen=True)
class ImportAnalysis:
    project_root: Path
    data_root: Path
    workspace_id: str
    imports_root: Path
    source_path: str
    format: str
    source_sha256: str
    source_bytes: bytes
    base_address: int | None
    target: str
    regions: tuple[tuple[int, int], ...]
    segments: tuple[ImageSegment, ...]
    entry_point: int | None
    image_bytes: bytes
    identity: dict[str, object]
    import_id: str
    plan_id: str


@dataclass(frozen=True)
class Admission:
    project_root: Path
    data_root: Path
    workspace_id: str
    import_id: str
    import_dir: Path
    source_path: str
    format: str
    source_sha256: str
    source_size: int
    target: str
    regions: tuple[tuple[int, int], ...]
    segments: tuple[ImageSegment, ...]
    entry_point: int | None
    image_sha256: str
    image_size: int
    image_filename: str
    created_at_utc: str


def _root_binding(root: Path) -> str:
    """Bind identity to the canonical root using OS-appropriate comparison."""

    text = str(root)
    if os.name == "nt":
        # Windows path comparison is case-insensitive and separator-neutral.
        text = text.replace("\\", "/").casefold()
    return sha256(text.encode("utf-8")).hexdigest()


def _external_workspace_id(project_root: Path, data_root: Path) -> str:
    combined = f"{_root_binding(project_root)}\0{_root_binding(data_root)}"
    return "external-" + sha256(combined.encode("utf-8")).hexdigest()[:24]


def _import_layout(project_root: Path, data_root: Path) -> tuple[str, Path, Path]:
    workspace_id = _external_workspace_id(project_root, data_root)
    workspace_root = data_root / "projects" / workspace_id
    return workspace_id, workspace_root, workspace_root / _FIRMWARE_DIR


def external_workspace_paths(
    project_root: Path, data_root: Path, session_id: str
) -> WorkspacePaths:
    """Bind the import workflow to its own deterministic workspace domain."""

    workspace_id, workspace_root, _imports_root = _import_layout(
        project_root, data_root
    )
    return WorkspacePaths(
        project_root=project_root,
        data_root=data_root,
        workspace_id=workspace_id,
        workspace_storage_key=workspace_id,
        session_id=session_id,
        workspace_root=workspace_root,
        monitor_root=workspace_root / "monitor",
        diagnostics_root=workspace_root / "diagnostics",
        logs_root=workspace_root / "logs",
        cache_root=workspace_root / "cache",
        session_root=workspace_root / "sessions" / session_id,
    )


def _parse_image(
    data: bytes, format: str, base_address: int | None
) -> ParsedImage:
    if format == "elf":
        return _parse_elf(data)
    if format == "hex":
        return _parse_hex(data)
    return _parse_bin(data, base_address)


def analyze_import(
    project_root: Path,
    data_root: Path,
    *,
    firmware_path: str,
    expected_sha256: str,
    format: str,
    target: str,
    flash_regions: tuple[tuple[int, int], ...],
    base_address: int | None,
) -> ImportAnalysis:
    """Read and analyze one source file without creating any state."""

    region_pairs = _validate_regions(flash_regions)
    if not isinstance(format, str) or format not in _FORMAT_SUFFIX:
        raise _fail(
            "FIRMWARE_INPUT_INVALID",
            "Firmware input is invalid",
            field="format",
            rule="enum",
            guidance="Use format elf (AXF is an ELF alias), hex, or bin.",
        )
    if base_address is not None and format != "bin":
        raise _fail(
            "FIRMWARE_INPUT_INVALID",
            "Firmware input is invalid",
            field="baseAddress",
            rule="forbidden",
            guidance="baseAddress is valid only for BIN images.",
        )
    if (
        not isinstance(target, str)
        or _TARGET_PATTERN.fullmatch(target) is None
    ):
        raise _fail(
            "FIRMWARE_INPUT_INVALID",
            "Firmware input is invalid",
            field="target",
            rule="identifier",
            guidance=(
                "Pass the exact supported pyOCD target identifier; the "
                "Toolkit never guesses or auto-selects a target."
            ),
        )
    source_path = _portable_path(firmware_path)
    expected = _digest(expected_sha256, "expectedSha256")
    source = _read_project_file(project_root, source_path, _SOURCE_LIMIT)
    source_sha256 = sha256(source).hexdigest()
    if source_sha256 != expected:
        raise _fail(
            "FIRMWARE_INPUT_CHANGED",
            "Firmware source changed before import",
            field="expectedSha256",
            rule="current",
            guidance=(
                "Re-read the current original file and pass its exact "
                "lowercase SHA-256; never reuse a stale pin."
            ),
        )
    parsed = _parse_image(source, format, base_address)
    _segments_fit_regions(parsed.segments, region_pairs)
    image = _normalized_elf(parsed.segments, parsed.entry_point)
    workspace_id, _workspace_root, imports_root = _import_layout(
        project_root, data_root
    )
    identity = _identity_document(
        project_root=project_root,
        data_root=data_root,
        workspace_id=workspace_id,
        source_path=source_path,
        format=format,
        source_sha256=source_sha256,
        source_size=len(source),
        base_address=base_address,
        target=target,
        regions=region_pairs,
        image_sha256=sha256(image).hexdigest(),
        image_size=len(image),
        segments=parsed.segments,
        entry_point=parsed.entry_point,
    )
    import_id = sha256(_canonical_bytes(identity)).hexdigest()
    plan_id = sha256(
        _canonical_bytes(
            {
                "kind": _PLAN_KIND,
                "schemaVersion": _SCHEMA_VERSION,
                "identity": identity,
            }
        )
    ).hexdigest()
    return ImportAnalysis(
        project_root=project_root,
        data_root=data_root,
        workspace_id=workspace_id,
        imports_root=imports_root,
        source_path=source_path,
        format=format,
        source_sha256=source_sha256,
        source_bytes=source,
        base_address=base_address,
        target=target,
        regions=region_pairs,
        segments=parsed.segments,
        entry_point=parsed.entry_point,
        image_bytes=image,
        identity=identity,
        import_id=import_id,
        plan_id=plan_id,
    )


def _analysis_payload(analysis: ImportAnalysis) -> dict[str, object]:
    return {
        "importId": analysis.import_id,
        "format": analysis.format,
        "target": analysis.target,
        "flashRegions": [
            {"start": start, "length": length}
            for start, length in analysis.regions
        ],
        "baseAddress": analysis.base_address,
        "source": {
            "path": analysis.source_path,
            "sha256": analysis.source_sha256,
            "size": len(analysis.source_bytes),
        },
        "image": {
            "sha256": sha256(analysis.image_bytes).hexdigest(),
            "size": len(analysis.image_bytes),
            "segments": [
                segment.summary() for segment in analysis.segments
            ],
            "entryPoint": analysis.entry_point,
        },
    }


# ---------------------------------------------------------------------------
# Immutable store
# ---------------------------------------------------------------------------


def _record_document(
    analysis: ImportAnalysis, *, created_at_utc: str
) -> dict[str, object]:
    suffix = _FORMAT_SUFFIX[analysis.format]
    return {
        "kind": _KIND,
        "schemaVersion": _SCHEMA_VERSION,
        "importId": analysis.import_id,
        "toolkitVersion": __version__,
        "workspaceId": analysis.workspace_id,
        "projectRootSha256": _root_binding(analysis.project_root),
        "dataRootSha256": _root_binding(analysis.data_root),
        "source": {
            "path": analysis.source_path,
            "fileName": "source" + suffix,
            "sha256": analysis.source_sha256,
            "size": len(analysis.source_bytes),
        },
        "format": analysis.format,
        "baseAddress": analysis.base_address,
        "target": analysis.target,
        "flashRegions": [
            {"start": start, "length": length}
            for start, length in analysis.regions
        ],
        "image": {
            "fileName": _IMAGE_NAME,
            "sha256": sha256(analysis.image_bytes).hexdigest(),
            "size": len(analysis.image_bytes),
            "segments": [
                segment.summary() for segment in analysis.segments
            ],
            "entryPoint": analysis.entry_point,
        },
        "createdAtUtc": created_at_utc,
    }


def _relative_chain(root: Path, target: Path) -> list[Path]:
    try:
        relative = target.relative_to(root)
    except ValueError:
        raise _fail(
            "FIRMWARE_IMPORT_STORE_UNSAFE",
            "Firmware import store is unavailable or unsafe",
            rule="containment",
        ) from None
    chain = [root]
    current = root
    for component in relative.parts:
        current /= component
        chain.append(current)
    return chain


def _require_directory_chain(
    root: Path, target: Path, *, require_leaf: bool
) -> None:
    """Reject redirects in every ancestor from one canonical root."""

    for item in _relative_chain(root, target):
        info = _lstat(item)
        if info is None:
            if require_leaf:
                raise _fail(
                    "FIRMWARE_IMPORT_NOT_FOUND",
                    "Firmware import was not found",
                    field="importId",
                    rule="missing",
                )
            return
        if _redirect(item, info) or not stat.S_ISDIR(info.st_mode):
            raise _fail(
                "FIRMWARE_IMPORT_STORE_UNSAFE",
                "Firmware import store is unavailable or unsafe",
                rule="redirect",
            )
        try:
            item.resolve(strict=True).relative_to(root)
        except (OSError, ValueError):
            raise _fail(
                "FIRMWARE_IMPORT_STORE_UNSAFE",
                "Firmware import store is unavailable or unsafe",
                rule="containment",
            ) from None


def _ensure_directory_chain(root: Path, directory: Path) -> None:
    for item in _relative_chain(root, directory):
        info = _lstat(item)
        if info is None:
            try:
                if item == root:
                    # The root's existing ancestors were checked by
                    # _canonical_data_root; only missing data-root components
                    # are created here.
                    item.mkdir(parents=True)
                else:
                    item.mkdir()
            except OSError:
                raise _fail(
                    "FIRMWARE_IMPORT_STORE_UNSAFE",
                    "Firmware import store is unavailable or unsafe",
                    rule="create",
                ) from None
            info = _lstat(item)
            if info is None:
                raise _fail(
                    "FIRMWARE_IMPORT_STORE_UNSAFE",
                    "Firmware import store is unavailable or unsafe",
                    rule="create",
                )
        if _redirect(item, info) or not stat.S_ISDIR(info.st_mode):
            raise _fail(
                "FIRMWARE_IMPORT_STORE_UNSAFE",
                "Firmware import store is unavailable or unsafe",
                rule="redirect",
            )
        try:
            item.resolve(strict=True).relative_to(root)
        except (OSError, ValueError):
            raise _fail(
                "FIRMWARE_IMPORT_STORE_UNSAFE",
                "Firmware import store is unavailable or unsafe",
                rule="containment",
            ) from None


def _write_new_file(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _publish_import(analysis: ImportAnalysis) -> bool:
    """Publish one immutable import; return True when newly created."""

    _ensure_directory_chain(
        analysis.data_root, analysis.imports_root
    )
    final = analysis.imports_root / analysis.import_id
    existing = _lstat(final)
    if existing is not None:
        record = _read_record(analysis.data_root, final)
        if _record_matches(record, analysis):
            _verify_stored_bytes(final, record, analysis)
            return False
        raise _fail(
            "FIRMWARE_IMPORT_CONFLICT",
            "A different immutable import already uses this identity",
            field="importId",
            rule="conflict",
            guidance=(
                "Never overwrite an import. Re-analyze the original source "
                "and use the identity returned by this request."
            ),
        )
    staging = analysis.imports_root / (".staging-" + os.urandom(16).hex())
    suffix = _FORMAT_SUFFIX[analysis.format]
    file_names = ("source" + suffix, _IMAGE_NAME, _RECORD_NAME)
    created_files: dict[str, tuple[int, int]] = {}
    staging_identity: tuple[int, int] | None = None
    try:
        staging.mkdir()
        staging_info = _lstat(staging)
        if (
            staging_info is None
            or _redirect(staging, staging_info)
            or not stat.S_ISDIR(staging_info.st_mode)
        ):
            raise _fail(
                "FIRMWARE_IMPORT_STORE_UNSAFE",
                "Firmware import store is unavailable or unsafe",
                rule="create",
            )
        staging_identity = (staging_info.st_dev, staging_info.st_ino)
        contents = {
            "source" + suffix: analysis.source_bytes,
            _IMAGE_NAME: analysis.image_bytes,
            _RECORD_NAME: _canonical_bytes(
                _record_document(
                    analysis, created_at_utc=utc_now_rfc3339()
                )
            ),
        }
        for name in file_names:
            path = staging / name
            _write_new_file(path, contents[name])
            info = _lstat(path)
            if info is None:
                raise _fail(
                    "FIRMWARE_IMPORT_STORE_UNSAFE",
                    "Firmware import store is unavailable or unsafe",
                    rule="create",
                )
            created_files[name] = (info.st_dev, info.st_ino)
        try:
            os.rename(staging, final)
        except OSError:
            existing = _lstat(final)
            if existing is None:
                raise _fail(
                    "FIRMWARE_IMPORT_STORE_UNSAFE",
                    "Firmware import store is unavailable or unsafe",
                    rule="publish",
                ) from None
            record = _read_record(analysis.data_root, final)
            if not _record_matches(record, analysis):
                raise _fail(
                    "FIRMWARE_IMPORT_CONFLICT",
                    "A different immutable import already uses this identity",
                    field="importId",
                    rule="conflict",
                ) from None
            _verify_stored_bytes(final, record, analysis)
            return False
    finally:
        _remove_owned_staging(staging, staging_identity, created_files)
    record = _read_record(analysis.data_root, final)
    if not _record_matches(record, analysis):
        raise _fail(
            "FIRMWARE_IMPORT_STORE_UNSAFE",
            "Firmware import store is unavailable or unsafe",
            rule="publish",
        )
    _verify_stored_bytes(final, record, analysis)
    return True


def _remove_owned_staging(
    staging: Path,
    staging_identity: tuple[int, int] | None,
    created_files: Mapping[str, tuple[int, int]],
) -> None:
    """Remove only exact files this call created, never unknown paths."""

    if staging_identity is None:
        return
    info = _lstat(staging)
    if (
        info is None
        or _redirect(staging, info)
        or not stat.S_ISDIR(info.st_mode)
        or (info.st_dev, info.st_ino) != staging_identity
    ):
        return
    for name, file_identity in created_files.items():
        path = staging / name
        try:
            current = _lstat(path)
        except ExternalFirmwareError:
            return
        if (
            current is None
            or _redirect(path, current)
            or not stat.S_ISREG(current.st_mode)
            or (current.st_dev, current.st_ino) != file_identity
        ):
            continue
        try:
            path.unlink()
        except OSError:
            pass
    try:
        staging.rmdir()
    except OSError:
        pass


def _record_matches(record: Mapping[str, object], analysis: ImportAnalysis) -> bool:
    source = record.get("source")
    image = record.get("image")
    if not isinstance(source, Mapping) or not isinstance(image, Mapping):
        return False
    return (
        record.get("importId") == analysis.import_id
        and record.get("toolkitVersion") == __version__
        and record.get("workspaceId") == analysis.workspace_id
        and record.get("projectRootSha256")
        == _root_binding(analysis.project_root)
        and record.get("dataRootSha256")
        == _root_binding(analysis.data_root)
        and record.get("format") == analysis.format
        and record.get("baseAddress") == analysis.base_address
        and record.get("target") == analysis.target
        and record.get("flashRegions")
        == [
            {"start": start, "length": length}
            for start, length in analysis.regions
        ]
        and source.get("path") == analysis.source_path
        and source.get("fileName")
        == "source" + _FORMAT_SUFFIX[analysis.format]
        and source.get("sha256") == analysis.source_sha256
        and source.get("size") == len(analysis.source_bytes)
        and image.get("fileName") == _IMAGE_NAME
        and image.get("sha256")
        == sha256(analysis.image_bytes).hexdigest()
        and image.get("size") == len(analysis.image_bytes)
        and image.get("segments")
        == [segment.summary() for segment in analysis.segments]
        and image.get("entryPoint") == analysis.entry_point
    )


def _verify_stored_bytes(
    directory: Path, record: Mapping[str, object], analysis: ImportAnalysis
) -> None:
    source = record["source"]
    image = record["image"]
    assert isinstance(source, Mapping) and isinstance(image, Mapping)
    source_name = source.get("fileName")
    image_name = image.get("fileName")
    if source_name != "source" + _FORMAT_SUFFIX[analysis.format] or image_name != _IMAGE_NAME:
        raise _fail(
            "FIRMWARE_IMPORT_INVALID",
            "Stored firmware import is invalid",
            path=_RECORD_NAME,
            rule="fileName",
        )
    stored_source = _read_store_file(directory, str(source_name), _SOURCE_LIMIT)
    stored_image = _read_store_file(directory, str(image_name), _IMAGE_LIMIT)
    if (
        stored_source != analysis.source_bytes
        or stored_image != analysis.image_bytes
    ):
        raise _fail(
            "FIRMWARE_IMPORT_INVALID",
            "Stored firmware import is invalid",
            rule="bytes",
        )


def _read_store_file(directory: Path, name: str, limit: int) -> bytes:
    path = directory / name
    info = _lstat(path)
    if info is None or not stat.S_ISREG(info.st_mode) or _redirect(path, info):
        raise _fail(
            "FIRMWARE_IMPORT_INVALID",
            "Stored firmware import is invalid",
            rule="file",
        )
    if info.st_size > limit:
        raise _fail(
            "FIRMWARE_IMPORT_INVALID",
            "Stored firmware import is invalid",
            rule="size",
        )
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino)
                or opened.st_size != info.st_size
            ):
                raise OSError("stored file changed")
            chunks = bytearray()
            while len(chunks) <= limit:
                chunk = os.read(
                    descriptor, min(65_536, limit + 1 - len(chunks))
                )
                if not chunk:
                    break
                chunks.extend(chunk)
        finally:
            os.close(descriptor)
    except OSError:
        raise _fail(
            "FIRMWARE_IMPORT_INVALID",
            "Stored firmware import is invalid",
            rule="read",
        ) from None
    if len(chunks) > limit:
        raise _fail(
            "FIRMWARE_IMPORT_INVALID",
            "Stored firmware import is invalid",
            rule="size",
        )
    return bytes(chunks)


def _reject_duplicate_json(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON field")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> object:
    raise ValueError("non-finite JSON number")


def _read_record(data_root: Path, directory: Path) -> dict[str, object]:
    _require_directory_chain(data_root, directory, require_leaf=True)
    data = _read_store_file(directory, _RECORD_NAME, _RECORD_LIMIT)
    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError, RecursionError):
        raise _fail(
            "FIRMWARE_IMPORT_INVALID",
            "Stored firmware import is invalid",
            path=_RECORD_NAME,
            rule="json",
        ) from None
    if not isinstance(value, dict):
        raise _fail(
            "FIRMWARE_IMPORT_INVALID",
            "Stored firmware import is invalid",
            path=_RECORD_NAME,
            rule="type",
        )
    if not _record_is_closed(value):
        raise _fail(
            "FIRMWARE_IMPORT_INVALID",
            "Stored firmware import is invalid",
            path=_RECORD_NAME,
            rule="fields",
        )
    return value


def _closed_text(value: object, *, limit: int = 128, digest: bool = False) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= limit
        and (not digest or _DIGEST_PATTERN.fullmatch(value) is not None)
    )


def _record_is_closed(record: Mapping[str, object]) -> bool:
    if set(record) != {
        "kind",
        "schemaVersion",
        "importId",
        "toolkitVersion",
        "workspaceId",
        "projectRootSha256",
        "dataRootSha256",
        "source",
        "format",
        "baseAddress",
        "target",
        "flashRegions",
        "image",
        "createdAtUtc",
    }:
        return False
    # Validate every type before using a value in membership or set
    # operations, so malformed JSON cannot raise TypeError.
    if (
        record["kind"] != _KIND
        or type(record["schemaVersion"]) is not int
        or record["schemaVersion"] != _SCHEMA_VERSION
        or not _closed_text(record["importId"], digest=True)
        or not _closed_text(record["toolkitVersion"], limit=64)
        or not _closed_text(record["workspaceId"])
        or not _closed_text(record["projectRootSha256"], digest=True)
        or not _closed_text(record["dataRootSha256"], digest=True)
        or not isinstance(record["format"], str)
        or record["format"] not in _FORMAT_SUFFIX
        or not _closed_text(record["target"])
        or _TARGET_PATTERN.fullmatch(str(record["target"])) is None
        or not isinstance(record["createdAtUtc"], str)
        or _TIMESTAMP_PATTERN.fullmatch(record["createdAtUtc"]) is None
    ):
        return False
    base_address = record["baseAddress"]
    if record["format"] == "bin":
        if type(base_address) is not int or not 0 <= base_address < _ADDRESS_LIMIT:
            return False
    elif base_address is not None:
        return False
    regions = record["flashRegions"]
    if not isinstance(regions, list) or not 1 <= len(regions) <= _MAX_REGIONS:
        return False
    for region in regions:
        if (
            not isinstance(region, dict)
            or set(region) != {"start", "length"}
            or type(region["start"]) is not int
            or type(region["length"]) is not int
        ):
            return False
    source = record["source"]
    if not isinstance(source, dict) or set(source) != {
        "path",
        "fileName",
        "sha256",
        "size",
    }:
        return False
    if (
        not isinstance(source["path"], str)
        or not isinstance(source["fileName"], str)
        or source["fileName"] != "source" + _FORMAT_SUFFIX[str(record["format"])]
        or not _closed_text(source["sha256"], digest=True)
        or type(source["size"]) is not int
        or not 0 < source["size"] <= _SOURCE_LIMIT
    ):
        return False
    try:
        _portable_path(source["path"])
    except ExternalFirmwareError:
        return False
    image = record["image"]
    if not isinstance(image, dict) or set(image) != {
        "fileName",
        "sha256",
        "size",
        "segments",
        "entryPoint",
    }:
        return False
    if (
        image["fileName"] != _IMAGE_NAME
        or not isinstance(image["sha256"], str)
        or _DIGEST_PATTERN.fullmatch(image["sha256"]) is None
        or type(image["size"]) is not int
        or not 0 < image["size"] <= _IMAGE_LIMIT
        or image["entryPoint"] is not None
        and (
            type(image["entryPoint"]) is not int
            or not 0 <= image["entryPoint"] < _ADDRESS_LIMIT
        )
    ):
        return False
    segments = image["segments"]
    if (
        not isinstance(segments, list)
        or not 1 <= len(segments) <= _MAX_SEGMENTS
    ):
        return False
    for segment in segments:
        if (
            not isinstance(segment, dict)
            or set(segment) != {"address", "length"}
            or type(segment["address"]) is not int
            or type(segment["length"]) is not int
            or not 0 < segment["length"]
            or not 0 <= segment["address"] < _ADDRESS_LIMIT
            or segment["address"] + segment["length"] > _ADDRESS_LIMIT
        ):
            return False
    return True


# ---------------------------------------------------------------------------
# Offline admission
# ---------------------------------------------------------------------------


def load_admission(
    project_root: Path,
    data_root: Path,
    *,
    import_id: str,
    expected_sha256: str,
) -> Admission:
    """Rebuild one stored import from its source and parameters."""

    digest = _digest(import_id, "importId")
    expected = _digest(expected_sha256, "expectedSha256")
    workspace_id, _workspace_root, imports_root = _import_layout(
        project_root, data_root
    )
    _require_directory_chain(data_root, imports_root, require_leaf=False)
    info = _lstat(imports_root)
    if info is None:
        raise _fail(
            "FIRMWARE_IMPORT_NOT_FOUND",
            "Firmware import was not found",
            field="importId",
            rule="missing",
            guidance=(
                "Import the original firmware with stm32_firmware_import and "
                "pass the exact returned importId; admissions are bound to "
                "this project and data root."
            ),
        )
    directory = imports_root / digest
    record = _read_record(data_root, directory)
    if (
        record["importId"] != digest
        or record["workspaceId"] != workspace_id
        or record["projectRootSha256"] != _root_binding(project_root)
        or record["dataRootSha256"] != _root_binding(data_root)
    ):
        raise _fail(
            "FIRMWARE_IMPORT_BINDING_MISMATCH",
            "Firmware import is not bound to this project and data root",
            field="importId",
            rule="binding",
            guidance=(
                "Use only an importId created by this Toolkit data root and "
                "project; do not copy import directories between projects."
            ),
        )
    if record["toolkitVersion"] != __version__:
        raise _fail(
            "FIRMWARE_IMPORT_INCOMPATIBLE",
            "Firmware import uses an incompatible Toolkit version",
            field="toolkitVersion",
            rule="current",
            actual=record["toolkitVersion"],
            supported=__version__,
            guidance=(
                "Re-import the original source with the current Toolkit; do "
                "not edit the stored record."
            ),
        )
    source = record["source"]
    image = record["image"]
    assert isinstance(source, Mapping) and isinstance(image, Mapping)
    format = str(record["format"])
    source_name = source["fileName"]
    if source_name != "source" + _FORMAT_SUFFIX[format]:
        raise _fail(
            "FIRMWARE_IMPORT_INVALID",
            "Stored firmware import is invalid",
            path=_RECORD_NAME,
            rule="fileName",
        )
    source_bytes = _read_store_file(
        directory, str(source_name), _SOURCE_LIMIT
    )
    if (
        len(source_bytes) != source["size"]
        or sha256(source_bytes).hexdigest() != source["sha256"]
    ):
        raise _fail(
            "FIRMWARE_IMPORT_INVALID",
            "Stored firmware import is invalid",
            rule="sourceSha256",
        )
    if source["sha256"] != expected:
        raise _fail(
            "FIRMWARE_INPUT_CHANGED",
            "Firmware source pin does not match the stored import",
            field="expectedSha256",
            rule="current",
            guidance=(
                "expectedSha256 pins the imported ORIGINAL file, not the "
                "normalized image. Re-read the admission response and pass "
                "its sourceSha256."
            ),
        )

    regions = _validate_regions(
        tuple(
            (region["start"], region["length"])
            for region in record["flashRegions"]
        )
    )
    base_address = record["baseAddress"]
    parsed = _parse_image(source_bytes, format, base_address)
    if (
        tuple(segment.summary() for segment in parsed.segments)
        != tuple(image["segments"])
    ):
        raise _fail(
            "FIRMWARE_IMPORT_INVALID",
            "Stored firmware import is invalid",
            rule="segments",
        )
    _segments_fit_regions(parsed.segments, regions)
    rebuilt = _normalized_elf(parsed.segments, parsed.entry_point)
    if (
        len(rebuilt) != image["size"]
        or sha256(rebuilt).hexdigest() != image["sha256"]
        or parsed.entry_point != image["entryPoint"]
    ):
        raise _fail(
            "FIRMWARE_IMPORT_INVALID",
            "Stored firmware import is invalid",
            rule="imageSha256",
        )
    stored_image = _read_store_file(directory, _IMAGE_NAME, _IMAGE_LIMIT)
    if stored_image != rebuilt:
        raise _fail(
            "FIRMWARE_IMPORT_INVALID",
            "Stored firmware import is invalid",
            rule="imageBytes",
        )

    identity = _identity_document(
        project_root=project_root,
        data_root=data_root,
        workspace_id=str(record["workspaceId"]),
        source_path=str(source["path"]),
        format=format,
        source_sha256=str(source["sha256"]),
        source_size=int(source["size"]),
        base_address=base_address,
        target=str(record["target"]),
        regions=regions,
        image_sha256=str(image["sha256"]),
        image_size=int(image["size"]),
        segments=parsed.segments,
        entry_point=parsed.entry_point,
    )
    if sha256(_canonical_bytes(identity)).hexdigest() != digest:
        raise _fail(
            "FIRMWARE_IMPORT_INVALID",
            "Stored firmware import is invalid",
            rule="importId",
        )
    return Admission(
        project_root=project_root,
        data_root=data_root,
        workspace_id=workspace_id,
        import_id=digest,
        import_dir=directory,
        source_path=str(source["path"]),
        format=format,
        source_sha256=str(source["sha256"]),
        source_size=int(source["size"]),
        target=str(record["target"]),
        regions=regions,
        segments=parsed.segments,
        entry_point=parsed.entry_point,
        image_sha256=str(image["sha256"]),
        image_size=int(image["size"]),
        image_filename=_IMAGE_NAME,
        created_at_utc=str(record["createdAtUtc"]),
    )


# ---------------------------------------------------------------------------
# Public offline workflows
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FirmwareImportRequest:
    project_root: Path
    data_root: Path
    session_id: str
    firmware_path: str
    expected_sha256: str
    format: str
    target: str
    flash_regions: tuple[tuple[int, int], ...]
    base_address: int | None = None
    plan_id: str | None = None
    authorized: object = False


@dataclass(frozen=True)
class FirmwareAdmitRequest:
    project_root: Path
    data_root: Path
    session_id: str
    import_id: str
    expected_sha256: str


def _require_request(request: object, expected_type: type[object]) -> None:
    if type(request) is not expected_type:
        raise _fail(
            "FIRMWARE_INPUT_INVALID",
            "Firmware input is invalid",
            field="request",
            rule="type",
            guidance=(
                "Call the public workflow or MCP tool with its documented "
                "request type; do not construct an ad-hoc object."
            ),
        )


def firmware_import_workflow(request: object) -> OperationResult[object]:
    try:
        _require_request(request, FirmwareImportRequest)
        typed: FirmwareImportRequest = request  # type: ignore[assignment]
        project_root = _canonical_root(typed.project_root, "project_root")
        data_root = _canonical_data_root(typed.data_root, project_root)
        _safe_session_id(typed.session_id)
        if type(typed.authorized) is not bool:
            raise _fail(
                "FIRMWARE_INPUT_INVALID",
                "Firmware input is invalid",
                field="authorized",
                rule="boolean",
                guidance="Pass authorized as an exact JSON boolean.",
            )
        if typed.plan_id is not None:
            _digest(typed.plan_id, "planId")
        analysis = analyze_import(
            project_root,
            data_root,
            firmware_path=typed.firmware_path,
            expected_sha256=typed.expected_sha256,
            format=typed.format,
            target=typed.target,
            flash_regions=typed.flash_regions,
            base_address=typed.base_address,
        )
        payload = _analysis_payload(analysis)
        if typed.plan_id is None:
            if typed.authorized is True:
                raise _fail(
                    "FIRMWARE_PLAN_REQUIRED",
                    "An import plan is required before authorization",
                    field="planId",
                    rule="required",
                    guidance=(
                        "Call stm32_firmware_import without planId to obtain a "
                        "deterministic PLAN, review it, then repeat the same "
                        "request with that exact planId and authorized=true."
                    ),
                )
            return OperationResult.success(
                _IMPORT_OPERATION,
                {
                    "mode": "firmware-import-plan",
                    "status": "planned",
                    "planId": analysis.plan_id,
                    **payload,
                    "provenance": {
                        "kind": "external-import",
                        "buildIdentity": None,
                        "gitVerified": False,
                        "guidance": _PROVENANCE_GUIDANCE,
                    },
                    "authorization": {
                        "required": True,
                        "scope": "immutable-import-copy",
                        "hardware": False,
                    },
                    "nextSteps": [
                        "Review data.source and data.image; the hashes are distinct fields.",
                        (
                            "Repeat the same request with planId="
                            + analysis.plan_id
                            + " and authorized=true to persist the immutable offline import."
                        ),
                        _AUTHORIZATION_GUIDANCE,
                    ],
                },
            )
        if typed.authorized is not True:
            raise _fail(
                "AUTHORIZATION_REQUIRED",
                "Explicit import authorization is required",
                field="authorized",
                rule="exactTrue",
                guidance=_AUTHORIZATION_GUIDANCE,
            )
        if typed.plan_id != analysis.plan_id:
            raise _fail(
                "FIRMWARE_PLAN_CHANGED",
                "Selected import plan changed",
                field="planId",
                rule="current",
                expected=analysis.plan_id,
                actual=typed.plan_id,
                guidance=(
                    "One or more source, option, or binding inputs changed. "
                    "Regenerate the PLAN and review it again before applying."
                ),
            )
        created = _publish_import(analysis)
        return OperationResult.success(
            _IMPORT_OPERATION,
            {
                "mode": "firmware-import-apply",
                "status": "imported",
                "created": created,
                "planId": analysis.plan_id,
                **payload,
                "provenance": {
                    "kind": "external-import",
                    "buildIdentity": None,
                    "gitVerified": False,
                    "guidance": _PROVENANCE_GUIDANCE,
                },
                "hardware": {
                    "authorized": False,
                    "hardwareVerified": False,
                    "next": (
                        "Call stm32_firmware_admit offline, select a probe with "
                        "stm32_probe_list, then separately authorize "
                        "stm32_flash_imported."
                    ),
                },
            },
        )
    except ExternalFirmwareError as error:
        return _failure(_IMPORT_OPERATION, error)
    except asyncio.CancelledError:
        raise
    except Exception:
        return OperationResult.failure(
            _IMPORT_OPERATION,
            "FIRMWARE_INTERNAL_ERROR",
            "Firmware import failed",
            {},
        )


def firmware_admit_workflow(request: object) -> OperationResult[object]:
    try:
        _require_request(request, FirmwareAdmitRequest)
        typed: FirmwareAdmitRequest = request  # type: ignore[assignment]
        project_root = _canonical_root(typed.project_root, "project_root")
        data_root = _canonical_data_root(typed.data_root, project_root)
        _safe_session_id(typed.session_id)
        admission = load_admission(
            project_root,
            data_root,
            import_id=typed.import_id,
            expected_sha256=typed.expected_sha256,
        )
        return OperationResult.success(
            _ADMIT_OPERATION,
            _admission_payload(admission),
        )
    except ExternalFirmwareError as error:
        return _failure(_ADMIT_OPERATION, error)
    except asyncio.CancelledError:
        raise
    except Exception:
        return OperationResult.failure(
            _ADMIT_OPERATION,
            "FIRMWARE_INTERNAL_ERROR",
            "Firmware admission failed",
            {},
        )


def _admission_payload(admission: Admission) -> dict[str, object]:
    return {
        "mode": "firmware-admission",
        "status": "admitted",
        "offlineReady": True,
        "hardwareVerified": False,
        "importId": admission.import_id,
        "sourceSha256": admission.source_sha256,
        "sourceSize": admission.source_size,
        "imageSha256": admission.image_sha256,
        "imageSize": admission.image_size,
        "format": admission.format,
        "target": admission.target,
        "flashRegions": [
            {"start": start, "length": length}
            for start, length in admission.regions
        ],
        "segments": [
            segment.summary() for segment in admission.segments
        ],
        "entryPoint": admission.entry_point,
        "remainingRequirements": [
            "An exact probe selector from stm32_probe_list; discovery establishes no target identity.",
            "Separate explicit stm32_flash_imported authorization for one exact probe and import.",
            "The attached target and native Flash map must accept every image segment before programming.",
            "Offline admission is not a reusable hardware authorization token or a current build identity.",
        ],
    }


# ---------------------------------------------------------------------------
# Imported-image programming
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImportedFlashRequest:
    project_root: Path
    data_root: Path
    probe_id: str
    import_id: str
    expected_sha256: str
    authorized: bool
    timeout_ms: int = 30_000


@dataclass(frozen=True)
class ImportedFlashReport:
    import_id: str
    source_sha256: str
    image_sha256: str
    image_size: int
    target: str
    probe_id: str
    workspace_id: str
    session_id: str
    verified_bytes: int
    segment_count: int
    started_at_utc: str
    finished_at_utc: str

    def to_dict(self) -> dict[str, object]:
        return {
            "importId": self.import_id,
            "sourceSha256": self.source_sha256,
            "imageSha256": self.image_sha256,
            "imageSize": self.image_size,
            "target": self.target,
            "probeId": self.probe_id,
            "workspaceId": self.workspace_id,
            "sessionId": self.session_id,
            "verifiedBytes": self.verified_bytes,
            "segmentCount": self.segment_count,
            "startedAtUtc": self.started_at_utc,
            "finishedAtUtc": self.finished_at_utc,
            "hardwareVerified": True,
            "runVerified": False,
        }


def _client_identity(
    client: object, request: ImportedFlashRequest, workspace_id: str
) -> tuple[str, str]:
    endpoint = getattr(client, "endpoint", None)
    endpoint_workspace = getattr(endpoint, "workspace_id", None)
    session_id = getattr(endpoint, "session_id", None)
    probe_id = getattr(endpoint, "probe_id", None)
    level = getattr(endpoint, "operation_level", None)
    level_value = getattr(level, "value", level)
    if (
        endpoint_workspace != workspace_id
        or probe_id != request.probe_id
        or level_value != "modify"
        or not isinstance(session_id, str)
        or not session_id
    ):
        raise _fail(
            "PROBE_ENDPOINT_INVALID",
            "Probe endpoint does not match the imported flash request",
            field="endpoint",
            rule="identity",
        )
    return workspace_id, session_id


def _validate_attachment(attachment: object, admission: Admission, probe_id: str) -> None:
    requested = getattr(attachment, "requested_target", None)
    resolved = getattr(attachment, "resolved_part_number", None)
    if (
        getattr(attachment, "probe_id", None) != probe_id
        or requested != admission.target
        or not isinstance(resolved, str)
        or _canonical_target(resolved) != _canonical_target(admission.target)
        or getattr(attachment, "core_count", None) != 1
    ):
        raise _fail(
            "FIRMWARE_IDENTITY_MISMATCH",
            "Connected target does not match the imported firmware identity",
            field="connectedTarget",
            rule="identity",
            guidance=(
                "Programming requires exactly the imported target, the "
                "selected probe, and a single-core attachment; no fallback "
                "target or probe is attempted."
            ),
        )


def admission_matches(first: Admission, current: Admission) -> bool:
    return (
        current.import_id == first.import_id
        and current.image_sha256 == first.image_sha256
        and current.image_size == first.image_size
        and current.source_sha256 == first.source_sha256
        and current.source_size == first.source_size
        and current.target == first.target
        and current.regions == first.regions
        and current.segments == first.segments
        and current.entry_point == first.entry_point
    )


def _require_same_import(first: Admission, current: Admission) -> None:
    if not admission_matches(first, current):
        raise _fail(
            "FIRMWARE_INPUT_CHANGED",
            "Firmware import changed during programming",
            field="importId",
            rule="current",
            guidance=(
                "A changed import must be re-imported and admitted again; "
                "never continue a stale programming handoff."
            ),
        )


def _canonical_target(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


async def _verify_segments(
    client: object,
    segments: tuple[ImageSegment, ...],
    *,
    timeout_ms: int,
) -> int:
    verified = 0
    for segment in segments:
        offset = 0
        while offset < len(segment.data):
            length = min(_MAX_READ_BYTES, len(segment.data) - offset)
            address = segment.address + offset
            actual = await client.read_memory(
                address, length, timeout_ms=timeout_ms
            )
            expected = segment.data[offset : offset + length]
            if type(actual) is not bytes or actual != expected:
                raise _fail(
                    "FIRMWARE_FLASH_VERIFY_FAILED",
                    "Programmed imported firmware readback did not match",
                    field="readback",
                    rule="bytes",
                    address=address,
                    length=length,
                    guidance=(
                        "A successful imported flash requires every planned "
                        "byte to match the normalized image; no retry or "
                        "partial success is reported."
                    ),
                )
            verified += length
            offset += length
    return verified


async def flash_imported_firmware(
    request: object, client: object
) -> OperationResult[ImportedFlashReport]:
    """Program one admitted immutable import through the owned service."""

    try:
        if type(request) is not ImportedFlashRequest:
            raise _fail(
                "FIRMWARE_INPUT_INVALID",
                "Firmware input is invalid",
                field="request",
                rule="type",
            )
        typed: ImportedFlashRequest = request  # type: ignore[assignment]
        if typed.authorized is not True:
            raise _fail(
                "AUTHORIZATION_REQUIRED",
                "Explicit imported flash authorization is required",
                field="authorized",
                rule="exactTrue",
            )
        project_root = _canonical_root(typed.project_root, "project_root")
        data_root = _canonical_data_root(typed.data_root, project_root)
        if (
            not isinstance(typed.probe_id, str)
            or _TARGET_PATTERN.fullmatch(typed.probe_id) is None
        ):
            raise _fail(
                "FIRMWARE_INPUT_INVALID",
                "Firmware input is invalid",
                field="probe_id",
                rule="identifier",
            )
        if (
            type(typed.timeout_ms) is not int
            or not 1 <= typed.timeout_ms <= 30_000
        ):
            raise _fail(
                "FIRMWARE_INPUT_INVALID",
                "Firmware input is invalid",
                field="timeoutMs",
                rule="range",
            )
        admission = load_admission(
            project_root,
            data_root,
            import_id=typed.import_id,
            expected_sha256=typed.expected_sha256,
        )
        workspace_id, session_id = _client_identity(
            client, typed, _external_workspace_id(project_root, data_root)
        )
        started = utc_now_rfc3339()
        try:
            attachment = await client.attach(typed.probe_id, admission.target)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if getattr(error, "code", None) == "PROBE_IDENTITY_MISMATCH":
                raise _fail(
                    "FIRMWARE_IDENTITY_MISMATCH",
                    "Connected target does not match the imported firmware identity",
                    field="connectedTarget",
                    rule="identity",
                    guidance=(
                        "Programming requires exactly the imported target, "
                        "the selected probe, and a single-core attachment; no "
                        "fallback target or probe is attempted."
                    ),
                ) from None
            raise
        _validate_attachment(attachment, admission, typed.probe_id)
        # Revalidate the immutable store after attach and immediately before
        # the programming RPC.  A changed or replaced record/bytes must cause
        # zero programming calls, not a stale image handoff.
        pre_program = load_admission(
            project_root,
            data_root,
            import_id=typed.import_id,
            expected_sha256=typed.expected_sha256,
        )
        _require_same_import(admission, pre_program)
        report: FlashBackendReport = (
            await client.program_verified_imported_elf(
                admission.image_filename,
                admission.image_sha256,
                admission.image_size,
                timeout_ms=typed.timeout_ms,
            )
        )
        if not isinstance(report, FlashBackendReport):
            raise _fail(
                "PROBE_RESPONSE_INVALID",
                "Probe Service programming response is invalid",
                field="programming",
                rule="response",
            )
        verified = await _verify_segments(
            client,
            admission.segments,
            timeout_ms=typed.timeout_ms,
        )
        current = load_admission(
            project_root,
            data_root,
            import_id=typed.import_id,
            expected_sha256=typed.expected_sha256,
        )
        _require_same_import(admission, current)
        finished = utc_now_rfc3339()
        return OperationResult.success(
            _FLASH_OPERATION,
            ImportedFlashReport(
                import_id=admission.import_id,
                source_sha256=admission.source_sha256,
                image_sha256=admission.image_sha256,
                image_size=admission.image_size,
                target=admission.target,
                probe_id=typed.probe_id,
                workspace_id=workspace_id,
                session_id=session_id,
                verified_bytes=verified,
                segment_count=len(admission.segments),
                started_at_utc=started,
                finished_at_utc=finished,
            ),
        )
    except asyncio.CancelledError:
        raise
    except ExternalFirmwareError as error:
        return _failure(_FLASH_OPERATION, error)
    except Exception as error:
        code = getattr(error, "code", None)
        message = getattr(error, "message", None)
        details = getattr(error, "details", None)
        if isinstance(code, str) and isinstance(message, str):
            return OperationResult.failure(
                _FLASH_OPERATION,
                code,
                message,
                details if isinstance(details, Mapping) else {},
            )
        return OperationResult.failure(
            _FLASH_OPERATION,
            "FIRMWARE_INTERNAL_ERROR",
            "Imported firmware programming failed",
            {},
        )


def write_flash_receipt(
    project_root: Path, data_root: Path, report: Mapping[str, object]
) -> dict[str, object]:
    """Commit one external-flash receipt after readback and cleanup."""

    _workspace_id, workspace_root, _imports_root = _import_layout(
        project_root, data_root
    )
    document: dict[str, object] = {
        "kind": _RECEIPT_KIND,
        "schemaVersion": _SCHEMA_VERSION,
        "status": "success",
        "code": "OK",
        "toolkitVersion": __version__,
        "importId": report["importId"],
        "sourceSha256": report["sourceSha256"],
        "imageSha256": report["imageSha256"],
        "imageSize": report["imageSize"],
        "target": report["target"],
        "probeSelectorDigest": sha256(
            str(report["probeId"]).encode("utf-8")
        ).hexdigest(),
        "workspaceId": report["workspaceId"],
        "sessionId": report["sessionId"],
        "verifiedBytes": report["verifiedBytes"],
        "segmentCount": report["segmentCount"],
        "startedAtUtc": report["startedAtUtc"],
        "finishedAtUtc": report["finishedAtUtc"],
        "operationLevel": "modify",
        "authorized": True,
        "hardwareVerified": True,
        "runVerified": False,
        "buildIdentity": None,
        "gitVerified": False,
    }
    payload = _canonical_bytes(document)
    if len(payload) > _RECEIPT_LIMIT:
        raise _fail(
            "EXTERNAL_FLASH_RECEIPT_FAILED",
            "External flash receipt exceeds its limit",
            field="receipt",
            rule="size",
        )
    receipt_id = sha256(payload).hexdigest()
    _ensure_directory_chain(data_root, workspace_root / _RECEIPT_DIR)
    path = workspace_root / _RECEIPT_DIR / (receipt_id + ".json")
    info = _lstat(path)
    if info is not None:
        if (
            not stat.S_ISREG(info.st_mode)
            or _redirect(path, info)
            or _read_store_file(path.parent, path.name, _RECEIPT_LIMIT) != payload
        ):
            raise _fail(
                "EXTERNAL_FLASH_RECEIPT_FAILED",
                "External flash receipt could not be committed",
                field="receipt",
                rule="conflict",
            )
    else:
        staging = path.parent / (".staging-" + os.urandom(16).hex())
        try:
            _write_new_file(staging, payload)
            try:
                os.rename(staging, path)
            except OSError:
                # Never accept an unknown destination as committed success.
                # The only acceptable race outcome is the exact same receipt.
                existing = _lstat(path)
                if existing is None:
                    raise _fail(
                        "EXTERNAL_FLASH_RECEIPT_FAILED",
                        "External flash receipt could not be committed",
                        field="receipt",
                        rule="publish",
                    ) from None
                if (
                    _redirect(path, existing)
                    or not stat.S_ISREG(existing.st_mode)
                    or _read_store_file(path.parent, path.name, _RECEIPT_LIMIT)
                    != payload
                ):
                    raise _fail(
                        "EXTERNAL_FLASH_RECEIPT_FAILED",
                        "External flash receipt could not be committed",
                        field="receipt",
                        rule="conflict",
                    ) from None
        finally:
            try:
                staging.unlink()
            except OSError:
                pass
    return {
        "receiptId": receipt_id,
        "receiptPath": _RECEIPT_DIR + "/" + receipt_id + ".json",
    }


__all__ = [
    "Admission",
    "ExternalFirmwareError",
    "FirmwareAdmitRequest",
    "FirmwareImportRequest",
    "ImageSegment",
    "ImportAnalysis",
    "ImportedFlashReport",
    "ImportedFlashRequest",
    "admission_matches",
    "analyze_import",
    "external_workspace_paths",
    "firmware_admit_workflow",
    "firmware_import_workflow",
    "flash_imported_firmware",
    "load_admission",
    "write_flash_receipt",
]
