"""Closed target-test transport adapters."""

from stm32_toolkit.testing.transports.base import TargetTransport
from stm32_toolkit.testing.transports.mailbox import BoundedMemoryReader, MailboxTransport
from stm32_toolkit.testing.transports.rtt import PyOcdRttAdapter, PyOcdRttBackend, RttTransport
from stm32_toolkit.testing.transports.semihosting import PyOcdSemihostingAdapter, SemihostingBackend, SemihostingTransport
from stm32_toolkit.testing.transports.uart import ALLOWED_BAUDS, UartTransport, pyserial_factory

__all__ = [
    "ALLOWED_BAUDS",
    "BoundedMemoryReader",
    "MailboxTransport",
    "PyOcdRttAdapter",
    "PyOcdRttBackend",
    "PyOcdSemihostingAdapter",
    "RttTransport",
    "SemihostingBackend",
    "SemihostingTransport",
    "TargetTransport",
    "UartTransport",
    "pyserial_factory",
]
