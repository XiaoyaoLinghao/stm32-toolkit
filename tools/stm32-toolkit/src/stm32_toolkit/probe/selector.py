"""Pure validation and public selection helpers for hardware probe identities."""

from __future__ import annotations

import re
from hashlib import sha256


_PORTABLE_SELECTOR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_RESERVED_PREFIX = "pyocd:"
_MAX_HARDWARE_ID_BYTES = 512


def valid_hardware_probe_id(value: object) -> bool:
    if not isinstance(value, str) or not value or not value.isprintable():
        return False
    try:
        return len(value.encode("utf-8", errors="strict")) <= _MAX_HARDWARE_ID_BYTES
    except UnicodeEncodeError:
        return False


def probe_fingerprint(hardware_id: str) -> str:
    if not valid_hardware_probe_id(hardware_id):
        raise ValueError("hardware probe identifier is invalid")
    return sha256(hardware_id.encode("utf-8")).hexdigest()


def public_probe_selector(hardware_id: str) -> str:
    fingerprint = probe_fingerprint(hardware_id)
    if _PORTABLE_SELECTOR.fullmatch(hardware_id) and not hardware_id.startswith(
        _RESERVED_PREFIX
    ):
        return hardware_id
    return f"{_RESERVED_PREFIX}{fingerprint}"
