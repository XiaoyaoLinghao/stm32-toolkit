"""Configuration management: project-level settings only."""

import json
import yaml
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


class Config:
    """Load project config from .stm32-monitor.yaml or .pyocd-debug.json.

    Priority: CLI args > .stm32-monitor.yaml > .pyocd-debug.json > defaults

    Global preset concept removed — all watch groups live in localStorage
    (per browser) or in .stm32-monitor.yaml (per project, if exported).
    """

    def __init__(self, cwd: str = None):
        self.cwd = (Path(cwd) if cwd else Path.cwd()).resolve()
        self._data = {
            "target": "stm32f429zgtx",
            "elf": None,
            "svd": None,
            "poll_interval_ms": 1000,
            "port": 8888,
            "watch_groups": {},
        }
        self._load()

    def _load(self):
        # 1. .pyocd-debug.json (from /init-stm32-project)
        pyocd_json = self.cwd / ".pyocd-debug.json"
        if pyocd_json.exists():
            try:
                with open(pyocd_json) as f:
                    data = json.load(f)
                if data.get("target"):
                    self._data["target"] = data["target"]
                elf_path = data.get("elf") or data.get("firmware")
                if elf_path:
                    resolved = self.cwd / elf_path
                    if resolved.exists():
                        self._data["elf"] = str(resolved)
                if data.get("svd"):
                    self._data["svd"] = data["svd"]
            except Exception:
                log.debug("Failed to load .pyocd-debug.json", exc_info=True)

        # 2. .stm32-monitor.yaml overrides .pyocd-debug.json
        monitor_yaml = self.cwd / ".stm32-monitor.yaml"
        if monitor_yaml.exists():
            try:
                with open(monitor_yaml) as f:
                    data = yaml.safe_load(f)
                if data:
                    for key in ("target", "elf", "svd", "poll_interval_ms", "port", "watch_groups"):
                        if key in data:
                            self._data[key] = data[key]
            except Exception:
                log.debug("Failed to load .stm32-monitor.yaml", exc_info=True)

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value

    @property
    def target(self) -> str:
        return self._data["target"]

    @property
    def elf(self) -> Optional[str]:
        return self._data.get("elf")

    @property
    def svd(self) -> Optional[str]:
        return self._data.get("svd")

    @property
    def port(self) -> int:
        return self._data.get("port", 8888)

    @property
    def poll_interval_ms(self) -> int:
        return self._data.get("poll_interval_ms", 1000)

    @property
    def watch_groups(self) -> dict:
        return self._data.get("watch_groups", {})
