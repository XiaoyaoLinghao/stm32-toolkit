"""Regression tests for the pyocd 0.46.0 CMSIS-DAP HID read path.

These tests drive the real ``HidApiUSB.read`` implementation shipped in the
selected pyocd 0.46.0 install against a fake HID device object.  Importing
``HidApiUSB`` imports pyocd's HID backend module, which in turn imports its
bundled ``hid`` binding at import time; however no hardware I/O occurs: no USB
backend is started, no device is enumerated, opened, read or written, and no
debug session or target API is touched.  The fake only records the arguments of
``hid.device.read`` and replays synthetic payloads, and the implementation under
test is never copied or monkeypatched.

Covered contract:

* ``HidApiUSB.read`` asks the underlying HID device for a finite timeout, and
  the value it uses by default is the SDK constant
  ``Interface.DEFAULT_USB_TIMEOUT_MS`` (10000 ms in pyocd 0.46.0).
* A normal HID response is returned as ``bytes`` with the payload preserved,
  whether the backend handed back a ``list[int]`` or an already-bytes buffer.
* An empty HID response (device read timeout or disconnect) raises
  ``DAPAccessIntf.DeviceError`` instead of returning an empty buffer.

At import time the module validates the active pyocd build from installer
metadata rather than from a directory-name convention: the installed
distribution metadata version and the loaded module's own version must both
equal the release policy pin, and the loaded ``pyocd`` package must resolve to
the ``pyocd/__init__.py`` that the installed distribution reports.  A wrong
version or a pyocd package imported from a different origin fails hard at
collection time (no ``skip``), so an older or mismatched package cannot silently
satisfy the regression.  The guard itself is exercised by the metadata-only
regressions at the end of this module.
"""

from __future__ import annotations

import importlib.metadata
import json
import math
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

import pyocd
from pyocd.probe.pydapaccess import DAPAccessIntf
from pyocd.probe.pydapaccess.interface.hidapi_backend import HidApiUSB

POLICY = Path(__file__).parents[3] / "tools" / "release" / "release_0900_policy.json"
EXPECTED_PYOCD_VERSION = "0.46.0"
EXPECTED_DEFAULT_TIMEOUT_MS = 10000
POLICY_PLATFORM_OS = "windows"
EXPECTED_PLATFORM_NAME = "win32"
PACKAGE_INIT_RELATIVE_PATH = "pyocd/__init__.py"


def _assert_selected_sdk(
    policy: Mapping[str, Any],
    *,
    module_version: str,
    distribution_version: str,
    module_init: Path,
    distribution_init: Path,
    platform_name: str,
    default_timeout_ms: int,
) -> None:
    """Check supplied pyocd observations against the release policy pins.

    The checks are pure: they read no file, installer metadata or SDK, so the
    guard can be regression tested with synthetic observations while the real
    callers below feed it the live environment.
    """
    direct_pin = policy["directPins"]["pyocd"]
    resolved_pin = policy["resolvedPins"]["pyocd"]
    assert direct_pin == resolved_pin == EXPECTED_PYOCD_VERSION, (
        "the current release policy must pin pyocd "
        f"{EXPECTED_PYOCD_VERSION} for the finite HID read repair, got "
        f"direct={direct_pin!r} resolved={resolved_pin!r}"
    )

    assert module_version == direct_pin, (
        f"imported pyocd {module_version!r} does not match the policy pin "
        f"{direct_pin!r}; these regressions must run against the selected "
        "0.46.0 SDK, not an older package"
    )

    assert distribution_version == direct_pin, (
        "installed pyocd distribution metadata version "
        f"{distribution_version!r} does not match the policy pin "
        f"{direct_pin!r}; the selected 0.46.0 SDK must be the installed "
        "distribution"
    )

    assert Path(module_init) == Path(distribution_init), (
        "the imported pyocd package must come from the origin reported by the "
        f"installed distribution ({distribution_init}), got loaded module "
        f"origin {module_init}; a pyocd import from another directory cannot "
        "satisfy this regression"
    )

    assert (
        policy["platform"]["os"] == POLICY_PLATFORM_OS
        and platform_name == EXPECTED_PLATFORM_NAME
    ), (
        "the finite HID read timeout is the Windows repair; this regression "
        "must run on the policy platform windows/x86_64, got "
        f"{platform_name!r}"
    )

    assert default_timeout_ms == EXPECTED_DEFAULT_TIMEOUT_MS, (
        "selected pyocd build must expose the 10000 ms SDK default USB "
        f"timeout, got {default_timeout_ms!r}"
    )


def _require_selected_sdk() -> None:
    """Fail collection unless the imported pyocd is the policy's 0.46.0 layer."""
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    distribution = importlib.metadata.distribution("pyocd")
    _assert_selected_sdk(
        policy,
        module_version=str(getattr(pyocd, "__version__", "")),
        distribution_version=distribution.version,
        module_init=Path(pyocd.__file__).resolve(),
        distribution_init=Path(
            distribution.locate_file(PACKAGE_INIT_RELATIVE_PATH)
        ).resolve(),
        platform_name=sys.platform,
        default_timeout_ms=HidApiUSB.DEFAULT_USB_TIMEOUT_MS,
    )


_require_selected_sdk()


class FakeHidDevice:
    """Minimal stand-in for ``hid.device`` usable by ``HidApiUSB``.

    Only the attributes and methods the HID read path can reach are provided.
    Responses are replayed in order; an exhausted response queue yields an
    empty read, which is how the real backend reports a read timeout.
    """

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.read_calls: list[tuple[int, Any]] = []
        self.write_calls: list[Any] = []
        self.open_calls = 0
        self.close_calls = 0

    def open(self) -> None:
        self.open_calls += 1

    def close(self) -> None:
        self.close_calls += 1

    def read(self, size: int, timeout_ms: Any = None) -> Any:
        self.read_calls.append((size, timeout_ms))
        if not self._responses:
            return []
        return self._responses.pop(0)

    def write(self, data: Any) -> int:
        self.write_calls.append(data)
        return len(data)


def _device_info(**overrides: Any) -> dict[str, Any]:
    """Synthetic ``hid.enumerate`` style metadata; no USB backend involved."""
    info: dict[str, Any] = {
        "vendor_id": 0x0D28,
        "product_id": 0x0204,
        "manufacturer_string": "Test Manufacturer",
        "product_string": "Test CMSIS-DAP",
        "serial_number": "TEST0001",
        "path": b"fake-cmsis-dap-path-0001",
        "usage_page": 0xFF00,
    }
    info.update(overrides)
    return info


def _make_interface(
    responses: list[Any],
) -> tuple[HidApiUSB, FakeHidDevice]:
    """Build a ``HidApiUSB`` bound to a fake device in the open state.

    ``HidApiUSB.__init__`` starts closed; these tests exercise the read path
    directly, so the fake device is marked open instead of entering the real
    open/close handshake (which would probe report sizes on real hardware).
    """
    device = FakeHidDevice(responses)
    interface = HidApiUSB(device, _device_info())
    interface.closed = False
    return interface, device


def test_read_uses_sdk_default_finite_timeout_ms() -> None:
    interface, device = _make_interface([[0x01, 0x02, 0x03]])

    payload = interface.read()

    assert HidApiUSB.DEFAULT_USB_TIMEOUT_MS == EXPECTED_DEFAULT_TIMEOUT_MS
    assert device.read_calls, "HidApiUSB.read never read from the HID device"
    size, timeout_ms = device.read_calls[0]
    assert isinstance(timeout_ms, (int, float)) and not isinstance(
        timeout_ms, bool
    ), f"expected a numeric timeout for hid.device.read, got {timeout_ms!r}"
    assert math.isfinite(timeout_ms), (
        f"HID reads must use a finite timeout, got {timeout_ms!r}"
    )
    assert timeout_ms == EXPECTED_DEFAULT_TIMEOUT_MS, (
        "HidApiUSB.read must default to the SDK's 10000 ms USB timeout, got "
        f"{timeout_ms!r}"
    )
    assert isinstance(size, int) and size > 0, (
        f"expected a positive HID read size, got {size!r}"
    )
    assert device.write_calls == [], "HidApiUSB.read must not write to the device"
    assert payload == b"\x01\x02\x03"


def test_read_converts_list_payload_to_bytes() -> None:
    interface, device = _make_interface([[0xAA, 0x00, 0x55, 0xFF]])

    payload = interface.read()

    assert device.read_calls, "HidApiUSB.read never read from the HID device"
    assert isinstance(payload, bytes), (
        f"HidApiUSB.read must return bytes, got {type(payload).__name__}"
    )
    assert payload == b"\xaa\x00\x55\xff"


def test_read_preserves_bytes_payload() -> None:
    interface, device = _make_interface([b"\x10\x20\x30\x40"])

    payload = interface.read()

    assert device.read_calls, "HidApiUSB.read never read from the HID device"
    assert isinstance(payload, bytes)
    assert payload == b"\x10\x20\x30\x40"


def test_read_empty_response_raises_device_error() -> None:
    interface, device = _make_interface([[]])

    with pytest.raises(DAPAccessIntf.DeviceError):
        interface.read()

    assert device.read_calls, "HidApiUSB.read never read from the HID device"
    assert device.write_calls == [], "HidApiUSB.read must not write to the device"


def _synthetic_policy() -> dict[str, Any]:
    """Minimal policy document shaped like the tracked release policy."""
    return {
        "directPins": {"pyocd": EXPECTED_PYOCD_VERSION},
        "resolvedPins": {"pyocd": EXPECTED_PYOCD_VERSION},
        "platform": {"os": POLICY_PLATFORM_OS},
    }


def test_guard_admits_consistent_ordinary_site_packages_install() -> None:
    """The guard must accept a 0.46.0 SDK in any ordinary install directory."""
    site_packages = Path("C:/Users/example/project/.venv/Lib/site-packages")
    package_init = site_packages / PACKAGE_INIT_RELATIVE_PATH

    # No exception means the guard admitted this ordinary, non-candidate path.
    _assert_selected_sdk(
        _synthetic_policy(),
        module_version=EXPECTED_PYOCD_VERSION,
        distribution_version=EXPECTED_PYOCD_VERSION,
        module_init=package_init,
        distribution_init=package_init,
        platform_name=EXPECTED_PLATFORM_NAME,
        default_timeout_ms=EXPECTED_DEFAULT_TIMEOUT_MS,
    )


def test_guard_rejects_module_loaded_from_different_origin() -> None:
    """A pyocd import from outside the installed distribution must be rejected."""
    site_packages = Path("C:/Users/example/project/.venv/Lib/site-packages")
    distribution_init = site_packages / PACKAGE_INIT_RELATIVE_PATH
    stray_init = Path("D:/scratch/pyocd-checkout/src/pyocd/__init__.py")

    with pytest.raises(AssertionError, match="origin"):
        _assert_selected_sdk(
            _synthetic_policy(),
            module_version=EXPECTED_PYOCD_VERSION,
            distribution_version=EXPECTED_PYOCD_VERSION,
            module_init=stray_init,
            distribution_init=distribution_init,
            platform_name=EXPECTED_PLATFORM_NAME,
            default_timeout_ms=EXPECTED_DEFAULT_TIMEOUT_MS,
        )
