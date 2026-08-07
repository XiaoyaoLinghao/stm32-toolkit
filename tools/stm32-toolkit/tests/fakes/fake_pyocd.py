"""Complete deterministic doubles for the PyOCD adapter boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class FakeBoardInfo:
    name: str | None = None
    target: str | None = None
    binary: str | None = None
    vendor: str | None = None


class FakePyOCDProbe:
    def __init__(
        self,
        unique_id: object,
        *,
        vendor_name: object = "STMicroelectronics",
        product_name: object = "ST-LINK/V3",
        description: object = "ST-LINK debug probe",
        board_info: FakeBoardInfo | None = None,
    ) -> None:
        self.unique_id = unique_id
        self.vendor_name = vendor_name
        self.product_name = product_name
        self.description = description
        self.associated_board_info = board_info
        self.session: object | None = None
        self.is_open = False
        self.close_count = 0
        self.close_error: BaseException | None = None

    def close(self) -> None:
        self.close_count += 1
        if self.close_error is not None:
            raise self.close_error
        self.is_open = False


_DEFAULT_MEMORY_RESULT = object()


class FakePyOCDTarget:
    def __init__(
        self,
        *,
        memory: Mapping[int, bytes] | None = None,
        registers: Mapping[str, int] | None = None,
        state: object = "halted",
    ) -> None:
        self.memory = {address: bytes(data) for address, data in (memory or {}).items()}
        self.registers = dict(registers or {})
        self.state = state
        self.cores: dict[int, object] = {0: self}
        self.calls: list[tuple[object, ...]] = []
        self.memory_result: object = _DEFAULT_MEMORY_RESULT
        self.memory_error: BaseException | None = None
        self.register_errors: dict[str, BaseException] = {}

    def read_memory_block8(self, address: int, length: int) -> object:
        self.calls.append(("read_memory_block8", address, length))
        if self.memory_error is not None:
            raise self.memory_error
        if self.memory_result is not _DEFAULT_MEMORY_RESULT:
            return self.memory_result
        for base, data in self.memory.items():
            offset = address - base
            if offset >= 0 and offset + length <= len(data):
                return list(data[offset : offset + length])
        raise RuntimeError("fake memory is unavailable")

    def read_core_registers_raw(self, names: list[str]) -> list[int]:
        self.calls.append(("read_core_registers_raw", tuple(names)))
        if len(names) != 1:
            raise AssertionError("adapter must isolate register reads")
        name = names[0]
        if name in self.register_errors:
            raise self.register_errors[name]
        if name not in self.registers:
            raise RuntimeError("fake register is unavailable")
        return [self.registers[name]]

    def get_state(self) -> object:
        self.calls.append(("get_state",))
        return self.state

    def halt(self) -> None:
        self.calls.append(("halt",))

    def resume(self) -> None:
        self.calls.append(("resume",))

    def step(self) -> None:
        self.calls.append(("step",))

    def reset(self) -> None:
        self.calls.append(("reset",))


class FakePyOCDBoard:
    def __init__(self, target: FakePyOCDTarget | None) -> None:
        self.target = target


class FakePyOCDSession:
    def __init__(
        self,
        probe: FakePyOCDProbe,
        *,
        options: Mapping[str, object],
        target: FakePyOCDTarget | None,
    ) -> None:
        self.probe = probe
        self.options = dict(options)
        self.board = FakePyOCDBoard(target)
        self.open_count = 0
        self.close_count = 0
        self.open_error: BaseException | None = None
        self.close_error: BaseException | None = None

    def open(self) -> None:
        self.open_count += 1
        self.probe.is_open = True
        if self.open_error is not None:
            raise self.open_error

    def close(self) -> None:
        self.close_count += 1
        if self.open_error is not None:
            return
        if self.close_error is not None:
            raise self.close_error
        self.probe.is_open = False


_DEFAULT_TARGET = object()


class FakePyOCDDriver:
    def __init__(
        self,
        probes: tuple[FakePyOCDProbe, ...] = (),
        *,
        target: FakePyOCDTarget | None | object = _DEFAULT_TARGET,
    ) -> None:
        self.probes = probes
        self.target = FakePyOCDTarget() if target is _DEFAULT_TARGET else target
        self.list_error: BaseException | None = None
        self.create_error: BaseException | None = None
        self.session_open_error: BaseException | None = None
        self.session_close_error: BaseException | None = None
        self.created_sessions: list[FakePyOCDSession] = []

    def list_probes(self) -> tuple[FakePyOCDProbe, ...]:
        if self.list_error is not None:
            raise self.list_error
        return self.probes

    def create_session(
        self, probe: object, *, options: Mapping[str, object]
    ) -> FakePyOCDSession:
        if self.create_error is not None:
            raise self.create_error
        assert isinstance(probe, FakePyOCDProbe)
        session = FakePyOCDSession(
            probe,
            options=options,
            target=self.target,
        )
        session.open_error = self.session_open_error
        session.close_error = self.session_close_error
        self.created_sessions.append(session)
        return session
