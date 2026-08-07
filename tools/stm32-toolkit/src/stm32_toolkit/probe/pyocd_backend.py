"""Fail-closed adapter from the ProbeBackend contract to PyOCD."""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from itertools import islice
from typing import Protocol, runtime_checkable

from .backend import FlashBackendReport, ProbeBackendError, ProbeDescriptor

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MIN_FREQUENCY_HZ = 100_000
_MAX_FREQUENCY_HZ = 50_000_000
_MAX_READ_BYTES = 65_536
_MAX_REGISTER_BATCH = 256


@runtime_checkable
class PyOCDDriver(Protocol):
    """The small external boundary used by PyOCDBackend and its tests."""

    def list_probes(self) -> tuple[object, ...]: ...

    def create_session(
        self, probe: object, *, options: Mapping[str, object]
    ) -> object: ...


class _DefaultPyOCDDriver:
    def __init__(self) -> None:
        try:
            from pyocd.core.session import Session
            from pyocd.probe.aggregator import DebugProbeAggregator
        except (ImportError, ModuleNotFoundError) as error:
            raise ProbeBackendError(
                "PROBE_BACKEND_UNAVAILABLE",
                "PyOCD support is not installed",
            ) from error
        self._aggregator = DebugProbeAggregator
        self._session_type = Session

    def list_probes(self) -> tuple[object, ...]:
        return tuple(self._aggregator.get_all_connected_probes())

    def create_session(
        self, probe: object, *, options: Mapping[str, object]
    ) -> object:
        return self._session_type(
            probe,
            auto_open=False,
            options=dict(options),
        )


def _valid_identifier(value: object) -> bool:
    return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None


def _display_text(value: object, *, fallback: str | None) -> str | None:
    if value is None:
        return fallback
    if not isinstance(value, str):
        raise ProbeBackendError(
            "PROBE_DESCRIPTOR_INVALID", "Debug probe descriptor is invalid"
        )
    text = value.strip()
    if not text:
        return fallback
    if len(text) > 128 or any(ord(character) < 32 for character in text):
        raise ProbeBackendError(
            "PROBE_DESCRIPTOR_INVALID", "Debug probe descriptor is invalid"
        )
    return text


class PyOCDBackend:
    """Own exactly one explicitly selected PyOCD Session."""

    def __init__(
        self,
        driver: PyOCDDriver | None = None,
        *,
        frequency_hz: int = 1_000_000,
    ) -> None:
        if (
            isinstance(frequency_hz, bool)
            or not isinstance(frequency_hz, int)
            or frequency_hz < _MIN_FREQUENCY_HZ
            or frequency_hz > _MAX_FREQUENCY_HZ
        ):
            raise ValueError("PyOCD frequency is invalid")
        self._driver = driver
        self._frequency_hz = frequency_hz
        self._session: object | None = None
        self._target: object | None = None
        self._probe_id: str | None = None
        self._target_name: str | None = None

    def _get_driver(self) -> PyOCDDriver:
        driver = self._driver
        if driver is None:
            driver = _DefaultPyOCDDriver()
            self._driver = driver
        return driver

    def _enumerate_raw(self) -> tuple[object, ...]:
        try:
            probes = tuple(self._get_driver().list_probes())
        except ProbeBackendError:
            raise
        except Exception as error:
            raise ProbeBackendError(
                "PROBE_ENUMERATION_FAILED", "Debug probe enumeration failed"
            ) from error
        for probe in probes:
            if not _valid_identifier(getattr(probe, "unique_id", None)):
                raise ProbeBackendError(
                    "PROBE_DESCRIPTOR_INVALID", "Debug probe descriptor is invalid"
                )
        return probes

    @staticmethod
    def _descriptor(probe: object) -> ProbeDescriptor:
        probe_id = getattr(probe, "unique_id", None)
        if not _valid_identifier(probe_id):
            raise ProbeBackendError(
                "PROBE_DESCRIPTOR_INVALID", "Debug probe descriptor is invalid"
            )
        vendor = _display_text(
            getattr(probe, "vendor_name", None), fallback="Unknown"
        )
        product_value = getattr(probe, "product_name", None)
        if product_value is None:
            product_value = getattr(probe, "description", None)
        product = _display_text(product_value, fallback="Unknown")
        board_info = getattr(probe, "associated_board_info", None)
        board_name = (
            None
            if board_info is None
            else _display_text(getattr(board_info, "name", None), fallback=None)
        )
        assert isinstance(probe_id, str)
        assert isinstance(vendor, str)
        assert isinstance(product, str)
        return ProbeDescriptor(
            probe_id=probe_id,
            vendor=vendor,
            product=product,
            board_name=board_name,
        )

    def list_probes(self) -> tuple[ProbeDescriptor, ...]:
        descriptors = tuple(self._descriptor(probe) for probe in self._enumerate_raw())
        return tuple(sorted(descriptors, key=lambda item: item.probe_id))

    def _select_probe(self, probe_id: str) -> object:
        matches = tuple(
            probe
            for probe in self._enumerate_raw()
            if getattr(probe, "unique_id", None) == probe_id
        )
        if not matches:
            raise ProbeBackendError(
                "PROBE_NOT_FOUND", "Selected debug probe is unavailable"
            )
        if len(matches) != 1:
            raise ProbeBackendError(
                "PROBE_SELECTION_AMBIGUOUS",
                "Selected debug probe identifier is ambiguous",
            )
        return matches[0]

    @staticmethod
    def _quiet_close(session: object) -> None:
        try:
            getattr(session, "close")()
        except Exception:
            pass

    def open_attach(
        self, probe_id: str, target: str, *, halt_on_connect: bool = False
    ) -> None:
        if not _valid_identifier(probe_id):
            raise ProbeBackendError(
                "PROBE_SELECTION_REQUIRED", "An exact probe identifier is required"
            )
        if halt_on_connect is not False:
            raise ProbeBackendError(
                "PROBE_OPERATION_LEVEL_DENIED",
                "Observation attach cannot halt the target",
            )
        if not _valid_identifier(target):
            raise ProbeBackendError("PROBE_TARGET_INVALID", "Target is invalid")

        probe = self._select_probe(probe_id)
        self.close()
        options: dict[str, object] = {
            "auto_unlock": False,
            "connect_mode": "attach",
            "frequency": self._frequency_hz,
            "no_config": True,
            "project_dir": os.getcwd(),
            "resume_on_disconnect": False,
            "target_override": target,
            "user_script": os.devnull,
        }
        session: object | None = None
        try:
            session = self._get_driver().create_session(probe, options=options)
            getattr(session, "open")()
            board = getattr(session, "board", None)
            session_target = None if board is None else getattr(board, "target", None)
            if session_target is None:
                raise ProbeBackendError(
                    "PROBE_TARGET_UNAVAILABLE", "Selected target is unavailable"
                )
        except ProbeBackendError:
            if session is not None:
                self._quiet_close(session)
            raise
        except Exception as error:
            if session is not None:
                self._quiet_close(session)
            raise ProbeBackendError(
                "PROBE_ATTACH_FAILED",
                "Debug probe attach failed",
                {"probeId": probe_id, "target": target},
            ) from error

        self._session = session
        self._target = session_target
        self._probe_id = probe_id
        self._target_name = target

    def _require_target(self) -> object:
        target = self._target
        if target is None or self._session is None:
            raise ProbeBackendError("PROBE_NOT_ATTACHED", "Probe is not attached")
        return target

    @staticmethod
    def _validate_memory_request(address: int, length: int) -> None:
        if (
            isinstance(address, bool)
            or not isinstance(address, int)
            or address < 0
            or address > 0xFFFF_FFFF
            or isinstance(length, bool)
            or not isinstance(length, int)
            or length < 1
            or length > _MAX_READ_BYTES
            or address + length > 0x1_0000_0000
        ):
            raise ProbeBackendError(
                "PROBE_READ_INVALID", "Memory read request is invalid"
            )

    def read_memory(self, address: int, length: int) -> bytes:
        self._validate_memory_request(address, length)
        target = self._require_target()
        try:
            result = getattr(target, "read_memory_block8")(address, length)
        except Exception as error:
            raise ProbeBackendError(
                "PROBE_READ_UNAVAILABLE",
                "Selected memory is unavailable",
                {"address": address, "length": length},
            ) from error

        details: dict[str, object] = {
            "address": address,
            "expectedLength": length,
        }
        try:
            iterator: Iterable[object] = iter(result)
            values = list(islice(iterator, length + 1))
            details["actualLength"] = len(values)
        except (TypeError, ValueError):
            values = []
        if len(values) != length or any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            or value > 255
            for value in values
        ):
            raise ProbeBackendError(
                "PROBE_PARTIAL_READ", "Memory read did not return exact bytes", details
            )
        return bytes(values)

    @staticmethod
    def _validate_register_names(names: tuple[str, ...]) -> None:
        if (
            not isinstance(names, tuple)
            or not 1 <= len(names) <= _MAX_REGISTER_BATCH
            or any(not _valid_identifier(name) for name in names)
        ):
            raise ProbeBackendError(
                "PROBE_REGISTER_INVALID", "Core register request is invalid"
            )

    def read_core_registers(self, names: tuple[str, ...]) -> Mapping[str, int]:
        self._validate_register_names(names)
        target = self._require_target()
        values: dict[str, int] = {}
        for name in names:
            try:
                result = list(getattr(target, "read_core_registers_raw")([name]))
                if (
                    len(result) != 1
                    or isinstance(result[0], bool)
                    or not isinstance(result[0], int)
                    or result[0] < 0
                    or result[0] >= 1 << 64
                ):
                    raise ValueError("invalid register result")
            except Exception as error:
                raise ProbeBackendError(
                    "PROBE_REGISTER_UNAVAILABLE",
                    "Selected core register is unavailable",
                    {"name": name},
                ) from error
            values[name] = result[0]
        return values

    def _control(self, operation: str) -> None:
        target = self._require_target()
        try:
            getattr(target, operation)()
        except Exception as error:
            raise ProbeBackendError(
                "PROBE_CONTROL_FAILED",
                "Target control operation failed",
                {"operation": operation},
            ) from error

    def halt(self) -> None:
        self._control("halt")

    def resume(self) -> None:
        self._control("resume")

    def step(self) -> None:
        self._control("step")

    def reset(self) -> None:
        self._control("reset")

    def flash_file(self, path: str) -> FlashBackendReport:
        self._require_target()
        raise ProbeBackendError(
            "PROBE_MODIFY_UNAVAILABLE",
            "Flash requires the verified firmware gate",
        )

    def close(self) -> None:
        session, self._session = self._session, None
        self._target = None
        self._probe_id = None
        self._target_name = None
        if session is not None:
            self._quiet_close(session)

