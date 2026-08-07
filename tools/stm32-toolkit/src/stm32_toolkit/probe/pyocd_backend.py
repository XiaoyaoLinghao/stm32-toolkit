"""Fail-closed adapter from the ProbeBackend contract to PyOCD."""

from __future__ import annotations

import os
import re
from io import BytesIO
from collections.abc import Iterable, Mapping
from itertools import islice
from typing import Protocol, runtime_checkable

from .backend import (
    FlashBackendReport,
    ProbeAttachmentEvidence,
    ProbeBackendError,
    ProbeDescriptor,
)

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MIN_FREQUENCY_HZ = 100_000
_MAX_FREQUENCY_HZ = 50_000_000
_MAX_READ_BYTES = 65_536
_MAX_REGISTER_BATCH = 256
_MAX_FLASH_BYTES = 64 * 1024 * 1024


@runtime_checkable
class PyOCDDriver(Protocol):
    """The small external boundary used by PyOCDBackend and its tests."""

    def list_probes(self) -> tuple[object, ...]: ...

    def create_session(
        self, probe: object, *, options: Mapping[str, object]
    ) -> object: ...

    def program_file(
        self, session: object, image: bytes, *, options: Mapping[str, object]
    ) -> None: ...


class _DefaultPyOCDDriver:
    def __init__(self) -> None:
        try:
            from pyocd.core.session import Session
            from pyocd.flash.file_programmer import FileProgrammer
            from pyocd.probe.aggregator import DebugProbeAggregator
        except (ImportError, ModuleNotFoundError) as error:
            raise ProbeBackendError(
                "PROBE_BACKEND_UNAVAILABLE",
                "PyOCD support is not installed",
            ) from error
        self._aggregator = DebugProbeAggregator
        self._session_type = Session
        self._programmer_type = FileProgrammer

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

    def program_file(
        self, session: object, image: bytes, *, options: Mapping[str, object]
    ) -> None:
        programmer = self._programmer_type(
            session,
            progress=options["progress"],
            chip_erase=options["chipErase"],
            trust_crc=options["trustCrc"],
            keep_unwritten=options["keepUnwritten"],
        )
        programmer.program(BytesIO(image), file_format=str(options["fileFormat"]))


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
        self._probe: object | None = None
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
            try:
                probe_id = getattr(probe, "unique_id", None)
            except Exception as error:
                raise ProbeBackendError(
                    "PROBE_DESCRIPTOR_INVALID", "Debug probe descriptor is invalid"
                ) from error
            if not _valid_identifier(probe_id):
                raise ProbeBackendError(
                    "PROBE_DESCRIPTOR_INVALID", "Debug probe descriptor is invalid"
                )
        return probes

    @staticmethod
    def _descriptor(probe: object) -> ProbeDescriptor:
        try:
            probe_id = getattr(probe, "unique_id", None)
            vendor_value = getattr(probe, "vendor_name", None)
            product_value = getattr(probe, "product_name", None)
            if product_value is None:
                product_value = getattr(probe, "description", None)
        except Exception as error:
            raise ProbeBackendError(
                "PROBE_DESCRIPTOR_INVALID", "Debug probe descriptor is invalid"
            ) from error
        if not _valid_identifier(probe_id):
            raise ProbeBackendError(
                "PROBE_DESCRIPTOR_INVALID", "Debug probe descriptor is invalid"
            )
        vendor = _display_text(vendor_value, fallback="Unknown")
        product = _display_text(product_value, fallback="Unknown")
        assert isinstance(probe_id, str)
        assert isinstance(vendor, str)
        assert isinstance(product, str)
        return ProbeDescriptor(
            probe_id=probe_id,
            vendor=vendor,
            product=product,
            board_name=None,
        )

    def list_probes(self) -> tuple[ProbeDescriptor, ...]:
        descriptors = tuple(self._descriptor(probe) for probe in self._enumerate_raw())
        return tuple(sorted(descriptors, key=lambda item: item.probe_id))

    def _select_probe(self, probe_id: str) -> object:
        matches: list[object] = []
        for probe in self._enumerate_raw():
            try:
                candidate = getattr(probe, "unique_id", None)
            except Exception as error:
                raise ProbeBackendError(
                    "PROBE_DESCRIPTOR_INVALID", "Debug probe descriptor is invalid"
                ) from error
            if candidate == probe_id:
                matches.append(probe)
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
    def _close_external(session: object, probe: object) -> None:
        close_error: Exception | None = None
        try:
            getattr(session, "close")()
        except Exception as error:
            close_error = error
        try:
            probe_is_open = bool(getattr(probe, "is_open", False))
        except Exception as error:
            probe_is_open = True
            if close_error is None:
                close_error = error
        if probe_is_open:
            try:
                getattr(probe, "close")()
            except Exception as error:
                if close_error is None:
                    close_error = error
        try:
            still_open = bool(getattr(probe, "is_open", False))
        except Exception:
            still_open = True
        if close_error is not None or still_open:
            raise ProbeBackendError(
                "PROBE_CLOSE_FAILED", "Debug probe cleanup failed"
            ) from close_error

    def open_attach(
        self, probe_id: str, target: str, *, halt_on_connect: bool = False
    ) -> ProbeAttachmentEvidence:
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
            "dap_protocol": "swd",
            "frequency": self._frequency_hz,
            "no_config": True,
            "pack.debug_sequences.enable": False,
            "primary_core": 0,
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
            cores = getattr(session_target, "cores", None)
            if not isinstance(cores, Mapping) or len(cores) != 1:
                raise ProbeBackendError(
                    "PROBE_TARGET_AMBIGUOUS",
                    "Selected target does not resolve to exactly one core",
                )
            try:
                part_number = _display_text(
                    getattr(session_target, "part_number", None), fallback=None
                )
            except Exception as error:
                raise ProbeBackendError(
                    "PROBE_TARGET_IDENTITY_UNAVAILABLE",
                    "Selected target identity is unavailable",
                ) from error
            if part_number is None or not _valid_identifier(part_number):
                raise ProbeBackendError(
                    "PROBE_TARGET_IDENTITY_UNAVAILABLE",
                    "Selected target identity is unavailable",
                )
        except ProbeBackendError:
            if session is not None:
                self._close_external(session, probe)
            raise
        except Exception as error:
            if session is not None:
                try:
                    self._close_external(session, probe)
                except ProbeBackendError:
                    raise
            raise ProbeBackendError(
                "PROBE_ATTACH_FAILED",
                "Debug probe attach failed",
                {"probeId": probe_id, "target": target},
            ) from error

        self._session = session
        self._target = session_target
        self._probe = probe
        self._probe_id = probe_id
        self._target_name = target
        return ProbeAttachmentEvidence(
            probe_id=probe_id,
            requested_target=target,
            resolved_part_number=part_number,
            core_count=1,
        )

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
        try:
            state = getattr(target, "get_state")()
            raw_state = getattr(state, "name", state)
            state_name = str(raw_state).lower()
            if state_name not in {
                "halted",
                "running",
                "reset",
                "sleeping",
                "lockedup",
                "programming",
            }:
                state_name = "unknown"
        except Exception:
            state_name = "unknown"
        if state_name != "halted":
            raise ProbeBackendError(
                "PROBE_REGISTER_UNAVAILABLE",
                "Core registers require an already halted target",
                {"state": state_name},
            )
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

    def flash_elf(self, image: bytes) -> FlashBackendReport:
        if not isinstance(image, bytes) or not 1 <= len(image) <= _MAX_FLASH_BYTES:
            raise ProbeBackendError(
                "PROBE_PROGRAM_INVALID", "Firmware image is invalid"
            )
        session = self._session
        self._require_target()
        assert session is not None
        options: dict[str, object] = {
            "chipErase": "sector",
            "trustCrc": False,
            "keepUnwritten": True,
            "progress": None,
            "fileFormat": "elf",
        }
        try:
            self._get_driver().program_file(session, image, options=options)
        except Exception as error:
            raise ProbeBackendError(
                "PROBE_PROGRAM_FAILED", "Firmware programming failed"
            ) from error
        return FlashBackendReport(
            bytes_programmed=None,
            sectors_programmed=None,
        )

    def close(self) -> None:
        session, self._session = self._session, None
        probe, self._probe = self._probe, None
        self._target = None
        self._probe_id = None
        self._target_name = None
        if session is not None and probe is not None:
            self._close_external(session, probe)
