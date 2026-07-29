"""Variable poller: background thread for periodic variable reading."""

import time
import threading
import json
import logging
from typing import Optional

log = logging.getLogger(__name__)


class Poller:
    """Background poller that reads variables at a configurable interval.

    Manages a watch list of variables + peripherals, reads them
    via PyOCD session, and exposes latest data.
    """

    def __init__(self, session, poll_interval_ms: int = 1000):
        self._session = session
        self._variables: list[dict] = []  # {name, address, size, type}
        self._peripherals: list[dict] = []  # {name, base, registers: [...]}
        self._interval = poll_interval_ms / 1000.0
        self._running = False
        self._paused = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Latest data
        self._latest_snapshot: dict = {"timestamp": 0, "variables": {}, "peripherals": {}}
        self._history: list[dict] = []  # ring buffer
        self._max_history = 600  # 10 min at 1s interval

    def set_watch_list(self, variables: list[dict], peripherals: list[dict] = None):
        """Set the variables and peripherals to watch."""
        with self._lock:
            self._variables = variables
            self._peripherals = peripherals or []

    def get_watch_list(self) -> tuple[list[dict], list[dict]]:
        with self._lock:
            return list(self._variables), list(self._peripherals)

    def set_interval(self, ms: int):
        if ms is None:
            ms = 1000
        self._interval = max(50, ms) / 1000.0

    def start(self):
        if self._running:
            return
        self._running = True
        self._paused = False
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def get_snapshot(self) -> dict:
        """Get latest data snapshot."""
        with self._lock:
            return dict(self._latest_snapshot)

    def get_history(self) -> list[dict]:
        with self._lock:
            return list(self._history)

    def get_snapshot_json(self) -> str:
        """Export latest snapshot + history as JSON string."""
        with self._lock:
            return json.dumps({
                "snapshot": self._latest_snapshot,
                "history": self._history[-100:],  # last 100 points
                "variables": [
                    {"name": v["name"], "address": v["address"], "size": v["size"], "type": v["type"]}
                    for v in self._variables
                ],
            }, indent=2)

    def export_snapshot_file(self, path: str):
        """Export snapshot to a JSON file for AI analysis."""
        data = self.get_snapshot_json()
        with open(path, "w") as f:
            f.write(data)
        log.info(f"Snapshot exported to {path}")

    def _poll_loop(self):
        while self._running:
            if self._paused:
                time.sleep(0.1)
                continue

            t0 = time.time()

            try:
                snapshot = self._poll_once()
                with self._lock:
                    self._latest_snapshot = snapshot
                    self._history.append(snapshot)
                    if len(self._history) > self._max_history:
                        self._history = self._history[-self._max_history:]
            except Exception as e:
                log.debug("Poll cycle skipped: %s", e)

            elapsed = time.time() - t0
            sleep_time = self._interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _poll_once(self) -> dict:
        """Read all watched variables and peripherals once."""
        vars_data = {}
        periph_data = {}

        if self._variables:
            vars_data = self._session.bulk_read(self._variables)

        for p in self._peripherals:
            periph_data[p["name"]] = {}
            for reg in p["registers"]:
                try:
                    val = self._session.read_register(p["base_address"], reg["offset"], reg["size"])
                    periph_data[p["name"]][reg["name"]] = val
                except Exception:
                    periph_data[p["name"]][reg["name"]] = None

        return {
            "timestamp": time.time(),
            "variables": vars_data,
            "peripherals": periph_data,
        }
