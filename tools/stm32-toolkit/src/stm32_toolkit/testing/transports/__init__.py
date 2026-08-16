"""Closed target-test transport adapters."""

from stm32_toolkit.testing.transports.base import TargetTransport
from stm32_toolkit.testing.transports.mailbox import BoundedMemoryReader, MailboxTransport
from stm32_toolkit.testing.transports.rtt import PyOcdRttBackend, RttTransport
from stm32_toolkit.testing.transports.semihosting import SemihostingBackend, SemihostingTransport
from stm32_toolkit.testing.transports.uart import ALLOWED_BAUDS, UartTransport, pyserial_factory

__all__ = [
    "ALLOWED_BAUDS",
    "BoundedMemoryReader",
    "MailboxTransport",
    "PyOcdRttBackend",
    "RttTransport",
    "SemihostingBackend",
    "SemihostingTransport",
    "TargetTransport",
    "UartTransport",
    "pyserial_factory",
]
