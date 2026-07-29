"""PyOCD session manager: attach-mode access to target memory without halting CPU."""

import os
import sys
import time
import struct
import logging

log = logging.getLogger(__name__)


class PyOCDSession:
    """PyOCD session wrapper with reconnect support.

    Uses attach mode to not halt the CPU. Keeps session open for
    repeated reads. Must call close() to release the probe.
    """

    MAX_RECONNECT_ATTEMPTS = 3

    def __init__(self, target: str = "stm32f429zgtx"):
        self.target = target
        self._session = None
        self._target = None

    def open(self):
        """Open PyOCD session in attach mode (does not halt CPU)."""
        self._kill_stale_pyocd()

        from pyocd.core.helpers import ConnectHelper
        try:
            self._session = ConnectHelper.session_with_chosen_probe(
                target_override=self.target,
                connect_mode="attach",
            )
            self._session.open()
            self._target = self._session.target
            log.info("PyOCD attached to %s", self.target)
        except RuntimeError as e:
            if "already open" in str(e).lower():
                log.warning("Probe is already in use by another process.")
                log.warning("Run: taskkill /F /IM pyocd.exe  or close the other tool.")
            raise

    def close(self):
        """Close session and release probe."""
        if self._session:
            try:
                self._session.close()
            except Exception:
                log.debug("Error closing session", exc_info=True)
            self._session = None
            self._target = None
            log.info("PyOCD session closed")

    def reconnect(self) -> bool:
        """Attempt to reconnect after disconnection. Returns True on success."""
        for attempt in range(1, self.MAX_RECONNECT_ATTEMPTS + 1):
            log.info("Reconnect attempt %d/%d", attempt, self.MAX_RECONNECT_ATTEMPTS)
            try:
                self.close()
                self.open()
                return True
            except Exception as e:
                log.warning("Reconnect %d failed: %s", attempt, e)
                time.sleep(1.0)
        return False

    @property
    def target_obj(self):
        return self._target

    def is_open(self) -> bool:
        return self._session is not None and self._session.is_open

    def read_u32(self, addr: int) -> int:
        return self._target.read32(addr)

    def read_u8(self, addr: int) -> int:
        return self._target.read_memory_block8(addr, 1)[0]

    def read_block(self, addr: int, length: int) -> bytes:
        return bytes(self._target.read_memory_block8(addr, length))

    def read_variable(self, addr: int, size: int) -> int:
        data = self._target.read_memory_block8(addr, size)
        return int.from_bytes(bytes(data), "little")

    def read_register(self, peripheral_base: int, offset: int, size: int = 4) -> int:
        data = self._target.read_memory_block8(peripheral_base + offset, size // 8)
        return int.from_bytes(bytes(data), "little")

    def bulk_read(self, variables: list[dict]) -> dict[str, int]:
        """Optimized bulk read: sort by address, read contiguous blocks.

        Each variable dict must have: name, address, size.
        Adjacent variables within 256 bytes are merged into a single read.
        """
        if not variables:
            return {}

        sorted_vars = sorted(variables, key=lambda v: v["address"])
        results = {}

        # Group adjacent variables into blocks (gap < 256 bytes = single read)
        blocks = []
        current_block = [sorted_vars[0]]
        for v in sorted_vars[1:]:
            prev_end = current_block[-1]["address"] + current_block[-1]["size"]
            if v["address"] - prev_end < 256:
                current_block.append(v)
            else:
                blocks.append(current_block)
                current_block = [v]
        blocks.append(current_block)

        for block in blocks:
            start = block[0]["address"]
            end = block[-1]["address"] + block[-1]["size"]
            raw = self.read_block(start, end - start)

            for v in block:
                offset = v["address"] - start
                try:
                    chunk = raw[offset:offset + v["size"]]
                    if v["size"] > 8:
                        val = chunk.hex()
                    else:
                        val = int.from_bytes(chunk, "little")
                except (IndexError, ValueError):
                    val = None
                results[v["name"]] = val

        return results

    @staticmethod
    def _kill_stale_pyocd():
        """Kill stray pyocd processes that might hold the probe."""
        try:
            if sys.platform == "win32":
                os.system(
                    "powershell -Command \"Get-Process pyocd -ErrorAction SilentlyContinue | Stop-Process -Force\" 2>NUL"
                )
            else:
                os.system("pkill -f pyocd 2>/dev/null || true")
            time.sleep(0.5)
        except Exception:
            log.debug("Error killing stale pyocd", exc_info=True)
