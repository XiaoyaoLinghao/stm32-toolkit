"""Bounded, exact-device CMSIS-SVD selection and read-risk metadata."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .model import DebugFirmwareBinding, MemoryRegionBinding

_MAX_SVD_BYTES = 8 * 1024 * 1024
_MAX_CANDIDATES = 32
_MAX_REGISTERS = 16_384
_MAX_XML_ELEMENTS = 100_000
_MAX_PERIPHERALS = 1_024
_MAX_CLUSTERS = 4_096
_MAX_REGISTER_DECLARATIONS = 16_384
_MAX_FIELDS = 65_536
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


@dataclass(frozen=True, init=False)
class SvdSelection:
    device: str
    path: str
    sha256: str
    registers: tuple[SvdRegister, ...]
    file_size: int
    readable_regions: tuple[MemoryRegionBinding, ...]
    _canonical_project_root: Path = field(repr=False)
    _canonical_path: Path = field(repr=False)
    _source_identity: tuple[int, int] = field(repr=False)

    @classmethod
    def _create(
        cls,
        *,
        device: str,
        path: str,
        sha256: str,
        registers: tuple[SvdRegister, ...],
        file_size: int,
        readable_regions: tuple[MemoryRegionBinding, ...],
        canonical_project_root: Path,
        canonical_path: Path,
        source_identity: tuple[int, int],
    ) -> "SvdSelection":
        instance = object.__new__(cls)
        for name, value in (
            ("device", device),
            ("path", path),
            ("sha256", sha256),
            ("registers", registers),
            ("file_size", file_size),
            ("readable_regions", readable_regions),
            ("_canonical_project_root", canonical_project_root),
            ("_canonical_path", canonical_path),
            ("_source_identity", source_identity),
        ):
            object.__setattr__(instance, name, value)
        return instance

    def register(self, path: str) -> SvdRegister:
        matches = tuple(item for item in self.registers if item.path == path)
        if len(matches) != 1:
            raise SvdError("SVD_REGISTER_NOT_FOUND", "SVD register was not found")
        return matches[0]

    def revalidate(
        self, binding: DebugFirmwareBinding, project_root: Path
    ) -> bool:
        if (
            not isinstance(binding, DebugFirmwareBinding)
            or binding.target_device != self.device
            or binding.memory_regions != self.readable_regions
            or not isinstance(project_root, Path)
        ):
            raise SvdError(
                "SVD_PROVENANCE_MISMATCH", "SVD selection provenance is invalid"
            )
        try:
            canonical_root = project_root.expanduser().absolute().resolve(strict=True)
        except OSError:
            raise SvdError(
                "SVD_PROVENANCE_MISMATCH", "SVD selection provenance is invalid"
            ) from None
        if canonical_root != self._canonical_project_root:
            raise SvdError(
                "SVD_PROVENANCE_MISMATCH", "SVD selection provenance is invalid"
            )
        current = _safe_read(project_root, Path(self.path))
        if (
            current.canonical_project_root != self._canonical_project_root
            or current.canonical_path != self._canonical_path
            or current.source_identity != self._source_identity
            or len(current.data) != self.file_size
            or hashlib.sha256(current.data).hexdigest() != self.sha256
        ):
            raise SvdError("SVD_INPUT_CHANGED", "SVD input changed after selection")
        _validate_register_ranges(self.registers, self.readable_regions)
        return True


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


@dataclass(frozen=True)
class _SafeRead:
    data: bytes
    canonical_project_root: Path
    canonical_path: Path
    source_identity: tuple[int, int]


def _safe_read(root: Path, candidate: Path) -> _SafeRead:
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
    return _SafeRead(
        data=data,
        canonical_project_root=resolved_root,
        canonical_path=path.resolve(strict=True),
        source_identity=(opened.st_dev, opened.st_ino),
    )


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


def _parse_xml(data: bytes) -> ET.Element:
    decoded = _decode_xml(data)
    parser = ET.XMLPullParser(events=("start", "end"))
    root: ET.Element | None = None
    count = 0
    try:
        for offset in range(0, len(decoded), 65_536):
            parser.feed(decoded[offset : offset + 65_536])
            for event, element in parser.read_events():
                if event == "start":
                    count += 1
                    if count > _MAX_XML_ELEMENTS:
                        raise _fail(
                            "SVD_SIZE_LIMIT", "SVD XML element count exceeds the limit"
                        )
                    if root is None:
                        root = element
        parser.close()
        for event, element in parser.read_events():
            if event == "start":
                count += 1
                if count > _MAX_XML_ELEMENTS:
                    raise _fail(
                        "SVD_SIZE_LIMIT", "SVD XML element count exceeds the limit"
                    )
                if root is None:
                    root = element
    except SvdError:
        raise
    except ET.ParseError:
        raise _fail("SVD_XML_INVALID", "SVD XML is malformed") from None
    if root is None:
        raise _fail("SVD_XML_INVALID", "SVD XML is malformed")
    return root


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


def _fields(
    register: ET.Element, size_bits: int, budget: "_Budget"
) -> tuple[SvdField, ...]:
    container = _child(register, "fields")
    if container is None:
        return ()
    result: list[SvdField] = []
    names: set[str] = set()
    used_mask = 0
    for field in _children(container, "field"):
        budget.claim("fields", field, _MAX_FIELDS)
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


@dataclass(frozen=True)
class _Defaults:
    size_bits: int | None
    access: str | None
    reset_value: int | None
    reset_mask: int | None


@dataclass
class _Budget:
    counts: dict[str, int] = field(default_factory=dict)
    claimed: set[tuple[str, int]] = field(default_factory=set)

    def claim(self, kind: str, element: ET.Element, limit: int) -> None:
        identity = (kind, id(element))
        if identity in self.claimed:
            return
        self.claimed.add(identity)
        count = self.counts.get(kind, 0) + 1
        if count > limit:
            raise _fail("SVD_SIZE_LIMIT", f"SVD {kind} count exceeds the limit")
        self.counts[kind] = count


@dataclass(frozen=True)
class _RegisterTemplate:
    size_bits: int
    access: str | None
    read_action: str | None
    reset_value: int | None
    reset_mask: int | None
    fields: tuple[SvdField, ...]


@dataclass(frozen=True)
class _ClusterTemplate:
    defaults: _Defaults
    container: ET.Element


def _optional_number(
    element: ET.Element, name: str, *, maximum: int
) -> int | None:
    value = _text(element, name)
    return _number(value, maximum=maximum) if value is not None else None


def _overlay_defaults(element: ET.Element, inherited: _Defaults) -> _Defaults:
    return _Defaults(
        size_bits=_optional_number(element, "size", maximum=1024)
        if _text(element, "size") is not None
        else inherited.size_bits,
        access=_text(element, "access") or inherited.access,
        reset_value=_optional_number(
            element, "resetValue", maximum=(1 << 64) - 1
        )
        if _text(element, "resetValue") is not None
        else inherited.reset_value,
        reset_mask=_optional_number(
            element, "resetMask", maximum=(1 << 64) - 1
        )
        if _text(element, "resetMask") is not None
        else inherited.reset_mask,
    )


def _valid_name_pattern(value: str) -> bool:
    return value.count("%s") <= 1 and _NAME.fullmatch(value.replace("%s", "0")) is not None


def _parse_registers(
    *,
    peripheral_name: str,
    container: ET.Element,
    base: int,
    defaults: _Defaults,
    budget: _Budget,
    result: list[SvdRegister],
    paths: set[str],
    prefix: str = "",
    parent_offset: int = 0,
) -> None:
    registers: dict[str, ET.Element] = {}
    clusters: dict[str, ET.Element] = {}
    for element in container:
        kind = _local(element)
        if kind not in ("register", "cluster"):
            continue
        name = _text(element, "name", required=True)
        assert name is not None
        if not _valid_name_pattern(name):
            raise _fail("SVD_XML_INVALID", f"SVD {kind} name is invalid")
        mapping = registers if kind == "register" else clusters
        if name in mapping:
            raise _fail("SVD_XML_INVALID", f"SVD {kind} declaration is ambiguous")
        mapping[name] = element
        budget.claim(
            "register declarations" if kind == "register" else "clusters",
            element,
            _MAX_REGISTER_DECLARATIONS if kind == "register" else _MAX_CLUSTERS,
        )

    register_cache: dict[str, _RegisterTemplate] = {}
    register_visiting: set[str] = set()

    def resolve_register(name: str) -> _RegisterTemplate:
        cached = register_cache.get(name)
        if cached is not None:
            return cached
        if name in register_visiting:
            raise _fail("SVD_XML_INVALID", "SVD derived register cycle is invalid")
        element = registers.get(name)
        if element is None:
            raise _fail("SVD_XML_INVALID", "SVD derived register scope is invalid")
        register_visiting.add(name)
        reference = element.attrib.get("derivedFrom")
        inherited = resolve_register(reference) if reference else None
        size_bits = _optional_number(element, "size", maximum=1024)
        if size_bits is None:
            size_bits = inherited.size_bits if inherited is not None else defaults.size_bits
        if size_bits not in (8, 16, 32, 64):
            raise _fail("SVD_XML_INVALID", "SVD register size is unsupported")
        access = _text(element, "access") or (
            inherited.access if inherited is not None else defaults.access
        )
        read_action = _text(element, "readAction") or (
            inherited.read_action if inherited is not None else None
        )
        fields_container = _child(element, "fields")
        fields = (
            _fields(element, size_bits, budget)
            if fields_container is not None
            else (inherited.fields if inherited is not None else ())
        )
        if any(field.bit_offset + field.bit_width > size_bits for field in fields):
            raise _fail("SVD_XML_INVALID", "SVD inherited field metadata is invalid")
        reset_value = _optional_number(
            element, "resetValue", maximum=(1 << 64) - 1
        )
        if reset_value is None:
            reset_value = (
                inherited.reset_value if inherited is not None else defaults.reset_value
            )
        reset_mask = _optional_number(
            element, "resetMask", maximum=(1 << 64) - 1
        )
        if reset_mask is None:
            reset_mask = (
                inherited.reset_mask if inherited is not None else defaults.reset_mask
            )
        width_mask = (1 << size_bits) - 1
        if (
            (reset_value is not None and reset_value & ~width_mask)
            or (reset_mask is not None and reset_mask & ~width_mask)
        ):
            raise _fail("SVD_XML_INVALID", "SVD reset metadata is invalid")
        template = _RegisterTemplate(
            size_bits, access, read_action, reset_value, reset_mask, fields
        )
        register_visiting.remove(name)
        register_cache[name] = template
        return template

    cluster_cache: dict[str, _ClusterTemplate] = {}
    cluster_visiting: set[str] = set()

    def resolve_cluster(name: str) -> _ClusterTemplate:
        cached = cluster_cache.get(name)
        if cached is not None:
            return cached
        if name in cluster_visiting:
            raise _fail("SVD_XML_INVALID", "SVD derived cluster cycle is invalid")
        element = clusters.get(name)
        if element is None:
            raise _fail("SVD_XML_INVALID", "SVD derived cluster scope is invalid")
        cluster_visiting.add(name)
        reference = element.attrib.get("derivedFrom")
        inherited = resolve_cluster(reference) if reference else None
        cluster_defaults = _overlay_defaults(
            element, inherited.defaults if inherited is not None else defaults
        )
        has_children = any(
            _local(child) in ("register", "cluster") for child in element
        )
        child_container = (
            element
            if has_children
            else (inherited.container if inherited is not None else element)
        )
        template = _ClusterTemplate(cluster_defaults, child_container)
        cluster_visiting.remove(name)
        cluster_cache[name] = template
        return template

    def count_expansions(scope: ET.Element) -> int:
        total = 0
        for child in scope:
            kind = _local(child)
            if kind == "register":
                total += len(_dim_values(child))
            elif kind == "cluster":
                child_name = _text(child, "name", required=True)
                assert child_name is not None
                template = resolve_cluster(child_name)
                total += len(_dim_values(child)) * count_expansions(template.container)
            if total > _MAX_REGISTERS:
                return total
        return total

    expected = count_expansions(container)
    if len(result) + expected > _MAX_REGISTERS:
        raise _fail("SVD_SIZE_LIMIT", "SVD register count exceeds the limit")

    for name_pattern, element in registers.items():
        template = resolve_register(name_pattern)
        offset = _number(_text(element, "addressOffset"))
        dimensions = _dim_values(element)
        if len(result) + len(dimensions) > _MAX_REGISTERS:
            raise _fail("SVD_SIZE_LIMIT", "SVD register count exceeds the limit")
        for index, delta in dimensions:
            name = _format_dim_name(name_pattern, index)
            path = f"{peripheral_name}.{prefix}{name}"
            address = base + parent_offset + offset + delta
            size_bytes = template.size_bits // 8
            if address < 0 or address + size_bytes > 0x1_0000_0000:
                raise _fail("SVD_XML_INVALID", "SVD register address overflows")
            if path in paths:
                raise _fail("SVD_XML_INVALID", "SVD register path is duplicated")
            paths.add(path)
            result.append(
                SvdRegister(
                    path,
                    address,
                    size_bytes,
                    template.access,
                    template.read_action,
                    template.reset_value,
                    template.reset_mask,
                    template.fields,
                )
            )
            if len(result) > _MAX_REGISTERS:
                raise _fail("SVD_SIZE_LIMIT", "SVD register count exceeds the limit")

    for name_pattern, element in clusters.items():
        template = resolve_cluster(name_pattern)
        cluster_offset = _number(_text(element, "addressOffset"))
        dimensions = _dim_values(element)
        descendant_count = count_expansions(template.container)
        if len(result) + len(dimensions) * descendant_count > _MAX_REGISTERS:
            raise _fail("SVD_SIZE_LIMIT", "SVD register count exceeds the limit")
        for index, delta in dimensions:
            expanded = _format_dim_name(name_pattern, index)
            _parse_registers(
                peripheral_name=peripheral_name,
                container=template.container,
                base=base,
                defaults=template.defaults,
                budget=budget,
                result=result,
                paths=paths,
                prefix=f"{prefix}{expanded}.",
                parent_offset=parent_offset + cluster_offset + delta,
            )


@dataclass(frozen=True)
class _PeripheralTemplate:
    element: ET.Element
    defaults: _Defaults
    base_address: int
    container: ET.Element | None


def _parse_document(data: bytes, portable_path: str) -> tuple[str, tuple[SvdRegister, ...]]:
    root = _parse_xml(data)
    if _local(root) != "device":
        raise _fail("SVD_XML_INVALID", "SVD root element is invalid")
    device = _text(root, "name", required=True)
    assert device is not None
    if _NAME.fullmatch(device) is None:
        raise _fail("SVD_XML_INVALID", "SVD device name is invalid")
    peripherals = _child(root, "peripherals")
    if peripherals is None:
        raise _fail("SVD_XML_INVALID", "SVD has no peripherals")
    device_defaults = _overlay_defaults(root, _Defaults(None, None, None, None))
    budget = _Budget()
    declarations: dict[str, ET.Element] = {}
    for peripheral in _children(peripherals, "peripheral"):
        budget.claim("peripherals", peripheral, _MAX_PERIPHERALS)
        name = _text(peripheral, "name", required=True)
        assert name is not None
        if not _valid_name_pattern(name) or name in declarations:
            raise _fail("SVD_XML_INVALID", "SVD peripheral declaration is ambiguous")
        declarations[name] = peripheral

    cache: dict[str, _PeripheralTemplate] = {}
    visiting: set[str] = set()

    def resolve(name: str) -> _PeripheralTemplate:
        cached = cache.get(name)
        if cached is not None:
            return cached
        if name in visiting:
            raise _fail("SVD_XML_INVALID", "SVD derived peripheral cycle is invalid")
        element = declarations.get(name)
        if element is None:
            raise _fail("SVD_XML_INVALID", "SVD derived peripheral scope is invalid")
        visiting.add(name)
        reference = element.attrib.get("derivedFrom")
        inherited = resolve(reference) if reference else None
        defaults = _overlay_defaults(
            element, inherited.defaults if inherited is not None else device_defaults
        )
        base = _optional_number(element, "baseAddress", maximum=0xFFFF_FFFF)
        if base is None:
            if inherited is None:
                raise _fail("SVD_XML_INVALID", "SVD peripheral base address is missing")
            base = inherited.base_address
        own_container = _child(element, "registers")
        container = (
            own_container
            if own_container is not None
            else (inherited.container if inherited is not None else None)
        )
        template = _PeripheralTemplate(element, defaults, base, container)
        visiting.remove(name)
        cache[name] = template
        return template

    registers: list[SvdRegister] = []
    paths: set[str] = set()
    for name_pattern in declarations:
        template = resolve(name_pattern)
        dimensions = _dim_values(template.element)
        for index, delta in dimensions:
            name = name_pattern if not index else _format_dim_name(name_pattern, index)
            if template.base_address + delta > 0xFFFF_FFFF:
                raise _fail("SVD_XML_INVALID", "SVD peripheral address overflows")
            if template.container is not None:
                _parse_registers(
                    peripheral_name=name,
                    container=template.container,
                    base=template.base_address + delta,
                    defaults=template.defaults,
                    budget=budget,
                    result=registers,
                    paths=paths,
                )
    return device, tuple(registers)


def _validate_readable_regions(
    readable_regions: object,
) -> tuple[MemoryRegionBinding, ...]:
    if (
        type(readable_regions) is not tuple
        or not 1 <= len(readable_regions) <= 64
        or not all(
            isinstance(region, MemoryRegionBinding) and "r" in region.attributes
            for region in readable_regions
        )
    ):
        raise _fail(
            "SVD_SELECTION_REQUIRED", "Trusted readable memory regions are required"
        )
    return readable_regions


def _validate_register_ranges(
    registers: tuple[SvdRegister, ...],
    readable_regions: tuple[MemoryRegionBinding, ...],
) -> None:
    for register in registers:
        end = register.address + register.size_bytes
        if not any(
            region.origin <= register.address
            and end <= region.origin + region.length
            for region in readable_regions
        ):
            raise _fail(
                "SVD_ADDRESS_OUT_OF_RANGE",
                "SVD register is outside trusted readable memory",
            )


def select_svd(
    project_root: Path,
    target_device: str,
    candidates: tuple[Path, ...],
    *,
    readable_regions: tuple[MemoryRegionBinding, ...],
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
    trusted_regions = _validate_readable_regions(readable_regions)
    documents: list[
        tuple[str, tuple[SvdRegister, ...], str, _SafeRead]
    ] = []
    seen: set[str] = set()
    for candidate in candidates:
        relative, portable = _portable_candidate(candidate)
        if portable in seen:
            raise _fail("SVD_SELECTION_REQUIRED", "SVD candidates are ambiguous")
        seen.add(portable)
        source = _safe_read(project_root, relative)
        device, registers = _parse_document(source.data, portable)
        documents.append((device, registers, portable, source))
    matches = tuple(item for item in documents if item[0] == target_device)
    if len(matches) != 1:
        raise _fail("SVD_SELECTION_REQUIRED", "An exact SVD selection is required")
    device, registers, portable, source = matches[0]
    _validate_register_ranges(registers, trusted_regions)
    return SvdSelection._create(
        device=device,
        path=portable,
        sha256=hashlib.sha256(source.data).hexdigest(),
        registers=registers,
        file_size=len(source.data),
        readable_regions=trusted_regions,
        canonical_project_root=source.canonical_project_root,
        canonical_path=source.canonical_path,
        source_identity=source.source_identity,
    )


__all__ = [
    "SvdError",
    "SvdField",
    "SvdRegister",
    "SvdSelection",
    "select_svd",
]
