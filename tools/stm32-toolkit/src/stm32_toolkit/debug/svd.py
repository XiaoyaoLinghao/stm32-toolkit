"""Bounded, exact-device CMSIS-SVD selection and read-risk metadata."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

_MAX_SVD_BYTES = 8 * 1024 * 1024
_MAX_CANDIDATES = 32
_MAX_REGISTERS = 16_384
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$")


class SvdError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class SvdField:
    name: str
    bit_offset: int
    bit_width: int
    mask: int


@dataclass(frozen=True)
class SvdRegister:
    path: str
    address: int
    size_bytes: int
    access: str | None
    read_action: str | None
    reset_value: int | None
    reset_mask: int | None
    fields: tuple[SvdField, ...]

    @property
    def has_read_side_effect(self) -> bool:
        return self.read_action not in (None, "none") or self.access not in (
            "read-only",
            "read-write",
            "read",
        )

    def authorize_read(self, acknowledge_access_risk: object, *, sampling: bool) -> bool:
        if self.access in ("write-only", "writeOnce"):
            raise SvdError(
                "SVD_REGISTER_WRITE_ONLY", "Write-only registers cannot be read"
            )
        if self.has_read_side_effect:
            if sampling:
                raise SvdError(
                    "SVD_REGISTER_NOT_SAMPLEABLE",
                    "Registers with read side effects cannot be sampled",
                )
            if acknowledge_access_risk is not True:
                raise SvdError(
                    "SVD_ACCESS_RISK_ACK_REQUIRED",
                    "Register read requires explicit access-risk acknowledgement",
                )
        return True


@dataclass(frozen=True)
class SvdSelection:
    device: str
    path: str
    sha256: str
    registers: tuple[SvdRegister, ...]

    def register(self, path: str) -> SvdRegister:
        matches = tuple(item for item in self.registers if item.path == path)
        if len(matches) != 1:
            raise SvdError("SVD_REGISTER_NOT_FOUND", "SVD register was not found")
        return matches[0]


def _fail(code: str, message: str) -> SvdError:
    return SvdError(code, message)


def _redirect(metadata: os.stat_result) -> bool:
    attributes = getattr(metadata, "st_file_attributes", 0) or 0
    return stat.S_ISLNK(metadata.st_mode) or bool(
        int(attributes) & _REPARSE_POINT
    )


def _portable_candidate(candidate: object) -> tuple[Path, str]:
    if not isinstance(candidate, Path):
        raise _fail("SVD_PATH_INVALID", "SVD candidate path is invalid")
    text = candidate.as_posix()
    if (
        not text
        or len(text) > 1024
        or candidate.is_absolute()
        or ":" in text
        or "\x00" in text
        or any(ord(character) < 32 or ord(character) == 127 for character in text)
        or any(part in ("", ".", "..") for part in text.split("/"))
        or not text.casefold().endswith(".svd")
    ):
        raise _fail("SVD_PATH_INVALID", "SVD candidate path is invalid")
    return candidate, text


def _safe_read(root: Path, candidate: Path) -> bytes:
    try:
        lexical_root = root.expanduser().absolute()
        resolved_root = root.resolve(strict=True)
        if lexical_root != resolved_root:
            raise ValueError("root is not canonical")
        components = [lexical_root]
        current = lexical_root
        for part in candidate.parts:
            current /= part
            components.append(current)
        parent_identity: list[tuple[int, int]] = []
        for component in components[:-1]:
            metadata = os.lstat(component)
            if _redirect(metadata) or not stat.S_ISDIR(metadata.st_mode):
                raise ValueError("unsafe parent")
            parent_identity.append((metadata.st_dev, metadata.st_ino))
        path = components[-1]
        metadata = os.lstat(path)
        if _redirect(metadata) or not stat.S_ISREG(metadata.st_mode):
            raise ValueError("unsafe file")
        if metadata.st_size > _MAX_SVD_BYTES:
            raise _fail("SVD_SIZE_LIMIT", "SVD file exceeds the size limit")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        try:
            opened = os.fstat(descriptor)
            named = os.lstat(path)
            if (
                _redirect(named)
                or not stat.S_ISREG(opened.st_mode)
                or not stat.S_ISREG(named.st_mode)
                or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
            ):
                raise _fail("SVD_INPUT_CHANGED", "SVD file changed while reading")
            chunks = bytearray()
            while len(chunks) <= _MAX_SVD_BYTES:
                chunk = os.read(
                    descriptor, min(65_536, _MAX_SVD_BYTES + 1 - len(chunks))
                )
                if not chunk:
                    break
                chunks.extend(chunk)
            named_after = os.lstat(path)
            after_parents: list[tuple[int, int]] = []
            for component in components[:-1]:
                parent = os.lstat(component)
                if _redirect(parent) or not stat.S_ISDIR(parent.st_mode):
                    raise _fail("SVD_INPUT_CHANGED", "SVD path changed while reading")
                after_parents.append((parent.st_dev, parent.st_ino))
            if (
                _redirect(named_after)
                or (opened.st_dev, opened.st_ino)
                != (named_after.st_dev, named_after.st_ino)
                or after_parents != parent_identity
            ):
                raise _fail("SVD_INPUT_CHANGED", "SVD path changed while reading")
        finally:
            os.close(descriptor)
    except SvdError:
        raise
    except (OSError, RuntimeError, ValueError):
        raise _fail("SVD_PATH_INVALID", "SVD candidate is unavailable or unsafe") from None
    data = bytes(chunks)
    if len(data) > _MAX_SVD_BYTES:
        raise _fail("SVD_SIZE_LIMIT", "SVD file exceeds the size limit")
    return data


def _decode_xml(data: bytes) -> str:
    candidates: list[str]
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        candidates = ["utf-16"]
    else:
        sample = data[:64]
        even = sample[0::2]
        odd = sample[1::2]
        if odd.count(0) >= max(2, len(odd) // 2):
            candidates = ["utf-16-le"]
        elif even.count(0) >= max(2, len(even) // 2):
            candidates = ["utf-16-be"]
        else:
            candidates = ["utf-8-sig"]
    decoded: str | None = None
    for encoding in candidates:
        try:
            value = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        if "<" in value and ">" in value:
            decoded = value.lstrip("\ufeff")
            break
    if decoded is None:
        raise _fail("SVD_XML_INVALID", "SVD XML encoding is invalid")
    folded = decoded.casefold()
    if "<!doctype" in folded or "<!entity" in folded:
        raise _fail("SVD_XML_UNSAFE", "SVD XML contains a forbidden declaration")
    return decoded


def _local(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _children(element: ET.Element, name: str) -> tuple[ET.Element, ...]:
    return tuple(child for child in element if _local(child) == name)


def _child(element: ET.Element, name: str) -> ET.Element | None:
    values = _children(element, name)
    return values[0] if values else None


def _text(element: ET.Element, name: str, *, required: bool = False) -> str | None:
    child = _child(element, name)
    value = None if child is None or child.text is None else child.text.strip()
    if required and not value:
        raise _fail("SVD_XML_INVALID", "SVD XML is missing required metadata")
    return value or None


def _number(value: str | None, *, maximum: int = 0xFFFF_FFFF) -> int:
    if value is None or len(value) > 32:
        raise _fail("SVD_XML_INVALID", "SVD numeric metadata is invalid")
    try:
        parsed = int(value, 0)
    except ValueError:
        raise _fail("SVD_XML_INVALID", "SVD numeric metadata is invalid") from None
    if parsed < 0 or parsed > maximum:
        raise _fail("SVD_XML_INVALID", "SVD numeric metadata is out of range")
    return parsed


def _fields(register: ET.Element, size_bits: int) -> tuple[SvdField, ...]:
    container = _child(register, "fields")
    if container is None:
        return ()
    result: list[SvdField] = []
    names: set[str] = set()
    used_mask = 0
    for field in _children(container, "field"):
        name = _text(field, "name", required=True)
        assert name is not None
        offset_text = _text(field, "bitOffset")
        width_text = _text(field, "bitWidth")
        if offset_text is None or width_text is None:
            lsb = _text(field, "lsb")
            msb = _text(field, "msb")
            offset = _number(lsb, maximum=255)
            top = _number(msb, maximum=255)
            width = top - offset + 1
        else:
            offset = _number(offset_text, maximum=255)
            width = _number(width_text, maximum=256)
        mask = ((1 << width) - 1) << offset if width > 0 else 0
        if (
            _NAME.fullmatch(name) is None
            or name in names
            or width < 1
            or offset + width > size_bits
            or used_mask & mask
        ):
            raise _fail("SVD_XML_INVALID", "SVD field metadata is invalid")
        names.add(name)
        used_mask |= mask
        result.append(SvdField(name, offset, width, mask))
    return tuple(result)


def _dim_values(element: ET.Element) -> tuple[tuple[str, int], ...]:
    dim_text = _text(element, "dim")
    if dim_text is None:
        return (("", 0),)
    dim = _number(dim_text, maximum=1024)
    increment = _number(_text(element, "dimIncrement"))
    indices_text = _text(element, "dimIndex")
    indices = (
        tuple(item.strip() for item in indices_text.split(","))
        if indices_text is not None
        else tuple(str(index) for index in range(dim))
    )
    if dim < 1 or len(indices) != dim or any(not item for item in indices):
        raise _fail("SVD_XML_INVALID", "SVD array metadata is invalid")
    return tuple((item, index * increment) for index, item in enumerate(indices))


def _format_dim_name(pattern: str, index: str) -> str:
    if not index:
        return pattern
    return pattern.replace("%s", index) if "%s" in pattern else f"{pattern}{index}"


def _parse_registers(
    peripheral: ET.Element,
    base: int,
    *,
    device_access: str | None,
    device_reset_value: int | None,
    device_reset_mask: int | None,
) -> tuple[SvdRegister, ...]:
    peripheral_name = _text(peripheral, "name", required=True)
    assert peripheral_name is not None
    if _NAME.fullmatch(peripheral_name) is None:
        raise _fail("SVD_XML_INVALID", "SVD peripheral name is invalid")
    inherited_access = _text(peripheral, "access") or device_access
    peripheral_reset_value = (
        _number(_text(peripheral, "resetValue"), maximum=(1 << 64) - 1)
        if _text(peripheral, "resetValue") is not None
        else device_reset_value
    )
    peripheral_reset_mask = (
        _number(_text(peripheral, "resetMask"), maximum=(1 << 64) - 1)
        if _text(peripheral, "resetMask") is not None
        else device_reset_mask
    )
    container = _child(peripheral, "registers")
    if container is None:
        return ()
    result: list[SvdRegister] = []
    by_name: dict[str, SvdRegister] = {}

    def add_register(element: ET.Element, prefix: str, parent_offset: int) -> None:
        name_pattern = _text(element, "name", required=True)
        assert name_pattern is not None
        offset = _number(_text(element, "addressOffset"))
        derived_name = element.attrib.get("derivedFrom")
        for index, delta in _dim_values(element):
            name = _format_dim_name(name_pattern, index)
            if _NAME.fullmatch(name) is None:
                raise _fail("SVD_XML_INVALID", "SVD register name is invalid")
            path = f"{peripheral_name}.{prefix}{name}"
            address = base + parent_offset + offset + delta
            if address > 0xFFFF_FFFF:
                raise _fail("SVD_XML_INVALID", "SVD register address overflows")
            inherited = by_name.get(derived_name or "")
            if derived_name and inherited is None:
                raise _fail("SVD_XML_INVALID", "SVD derived register is invalid")
            size_bits = (
                _number(_text(element, "size"), maximum=1024)
                if _text(element, "size") is not None
                else (inherited.size_bytes * 8 if inherited else 32)
            )
            if size_bits not in (8, 16, 32, 64):
                raise _fail("SVD_XML_INVALID", "SVD register size is unsupported")
            size_bytes = size_bits // 8
            if address + size_bytes > 0x1_0000_0000:
                raise _fail("SVD_XML_INVALID", "SVD register address overflows")
            access = _text(element, "access") or (
                inherited.access if inherited else inherited_access
            )
            read_action = _text(element, "readAction") or (
                inherited.read_action if inherited else None
            )
            fields = _fields(element, size_bits) or (inherited.fields if inherited else ())
            reset_value = (
                _number(_text(element, "resetValue"), maximum=(1 << 64) - 1)
                if _text(element, "resetValue") is not None
                else (
                    inherited.reset_value if inherited else peripheral_reset_value
                )
            )
            reset_mask = (
                _number(_text(element, "resetMask"), maximum=(1 << 64) - 1)
                if _text(element, "resetMask") is not None
                else (inherited.reset_mask if inherited else peripheral_reset_mask)
            )
            width_mask = (1 << size_bits) - 1
            if (
                reset_value is not None
                and reset_value & ~width_mask
                or reset_mask is not None
                and reset_mask & ~width_mask
            ):
                raise _fail("SVD_XML_INVALID", "SVD reset metadata is invalid")
            item = SvdRegister(
                path,
                address,
                size_bytes,
                access,
                read_action,
                reset_value,
                reset_mask,
                fields,
            )
            if any(existing.path == path for existing in result):
                raise _fail("SVD_XML_INVALID", "SVD register path is duplicated")
            result.append(item)
            by_name[name] = item
            by_name[path] = item

    for item in container:
        kind = _local(item)
        if kind == "register":
            add_register(item, "", 0)
        elif kind == "cluster":
            cluster_name = _text(item, "name", required=True)
            assert cluster_name is not None
            cluster_offset = _number(_text(item, "addressOffset"))
            for index, delta in _dim_values(item):
                expanded = _format_dim_name(cluster_name, index)
                if _NAME.fullmatch(expanded) is None:
                    raise _fail("SVD_XML_INVALID", "SVD cluster name is invalid")
                for register in _children(item, "register"):
                    add_register(
                        register, f"{expanded}.", cluster_offset + delta
                    )
        if len(result) > _MAX_REGISTERS:
            raise _fail("SVD_SIZE_LIMIT", "SVD register count exceeds the limit")
    return tuple(result)


def _parse_document(data: bytes, portable_path: str) -> SvdSelection:
    try:
        root = ET.fromstring(_decode_xml(data))
    except SvdError:
        raise
    except ET.ParseError:
        raise _fail("SVD_XML_INVALID", "SVD XML is malformed") from None
    if _local(root) != "device":
        raise _fail("SVD_XML_INVALID", "SVD root element is invalid")
    device = _text(root, "name", required=True)
    assert device is not None
    if _NAME.fullmatch(device) is None:
        raise _fail("SVD_XML_INVALID", "SVD device name is invalid")
    peripherals = _child(root, "peripherals")
    if peripherals is None:
        raise _fail("SVD_XML_INVALID", "SVD has no peripherals")
    registers: list[SvdRegister] = []
    device_access = _text(root, "access")
    device_reset_value = (
        _number(_text(root, "resetValue"), maximum=(1 << 64) - 1)
        if _text(root, "resetValue") is not None
        else None
    )
    device_reset_mask = (
        _number(_text(root, "resetMask"), maximum=(1 << 64) - 1)
        if _text(root, "resetMask") is not None
        else None
    )
    for peripheral in _children(peripherals, "peripheral"):
        base = _number(_text(peripheral, "baseAddress"))
        registers.extend(
            _parse_registers(
                peripheral,
                base,
                device_access=device_access,
                device_reset_value=device_reset_value,
                device_reset_mask=device_reset_mask,
            )
        )
        if len(registers) > _MAX_REGISTERS:
            raise _fail("SVD_SIZE_LIMIT", "SVD register count exceeds the limit")
    return SvdSelection(
        device,
        portable_path,
        hashlib.sha256(data).hexdigest(),
        tuple(registers),
    )


def select_svd(
    project_root: Path, target_device: str, candidates: tuple[Path, ...]
) -> SvdSelection:
    """Select exactly one explicit SVD whose device name exactly matches."""

    if (
        not isinstance(project_root, Path)
        or not isinstance(target_device, str)
        or _NAME.fullmatch(target_device) is None
        or type(candidates) is not tuple
        or not 1 <= len(candidates) <= _MAX_CANDIDATES
    ):
        raise _fail("SVD_SELECTION_REQUIRED", "An exact SVD selection is required")
    documents: list[SvdSelection] = []
    seen: set[str] = set()
    for candidate in candidates:
        relative, portable = _portable_candidate(candidate)
        if portable in seen:
            raise _fail("SVD_SELECTION_REQUIRED", "SVD candidates are ambiguous")
        seen.add(portable)
        documents.append(_parse_document(_safe_read(project_root, relative), portable))
    matches = tuple(item for item in documents if item.device == target_device)
    if len(matches) != 1:
        raise _fail("SVD_SELECTION_REQUIRED", "An exact SVD selection is required")
    return matches[0]


__all__ = [
    "SvdError",
    "SvdField",
    "SvdRegister",
    "SvdSelection",
    "select_svd",
]
