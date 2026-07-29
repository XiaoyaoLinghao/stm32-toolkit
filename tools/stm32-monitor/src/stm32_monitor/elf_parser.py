"""ELF symbol parser: extract global variables from ARM ELF files using arm-none-eabi-nm."""

import subprocess
import re
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


def parse_elf(elf_path: str) -> list[dict]:
    """Parse ELF file and return list of global variables with correct sizes.

    Uses plain nm for addr/section/name, then --size-sort for sizes.
    Merges by address to get both correct address and correct size.

    Returns list of dicts: {name, address, size, section, type, module}
    """
    elf = Path(elf_path)
    if not elf.exists():
        raise FileNotFoundError(f"ELF file not found: {elf_path}")

    # Pass 1: plain nm → correct addr (8 hex digits), section, name
    result1 = subprocess.check_output(
        ["arm-none-eabi-nm", str(elf)],
        text=True,
    )

    var_map = {}  # name → {address, section}
    for line in result1.split("\n"):
        parts = line.strip().split()
        if len(parts) < 3:
            continue
        addr_str, section = parts[0], parts[1]
        name = " ".join(parts[2:])

        if section not in ("B", "D", "d", "b"):
            continue
        if name.startswith("_") or name.startswith("__"):
            continue
        if len(addr_str) < 8:  # skip small/relative addresses
            continue

        try:
            addr = int(addr_str, 16)
        except ValueError:
            continue

        var_map[name] = {"address": addr, "section": section}

    # Pass 2: --size-sort → correct size (2nd column)
    result2 = subprocess.check_output(
        ["arm-none-eabi-nm", "--size-sort", str(elf)],
        text=True,
    )

    size_map = {}  # name → size
    for line in result2.split("\n"):
        parts = line.strip().split()
        if len(parts) < 3:
            continue
        size_str, section = parts[0], parts[1]
        name = " ".join(parts[2:])

        if section not in ("B", "D", "d", "b"):
            continue
        if name.startswith("_") or name.startswith("__"):
            continue
        # Skip lines that don't start with hex size
        try:
            size = int(size_str, 16)
        except ValueError:
            continue
        size_map[name] = size

    # Merge
    variables = []
    for name, info in var_map.items():
        size = size_map.get(name, 4)
        addr = info["address"]
        section = info["section"]

        if size == 1:
            vtype = "u8"
        elif size == 2:
            vtype = "u16"
        elif size == 4:
            vtype = "u32"
        elif size == 8:
            vtype = "u64"
        else:
            vtype = f"u8[{size}]"

        module = _guess_module(name)

        variables.append({
            "name": name,
            "address": addr,
            "size": size,
            "section": section,
            "type": vtype,
            "module": module,
        })

    log.info("Parsed %d global variables from ELF", len(variables))
    return sorted(variables, key=lambda v: v["name"])


def find_elf(cwd: str = ".") -> Optional[str]:
    """Auto-discover ELF file in project directory.

    Checks:
    1. .stm32-monitor.yaml (project config)
    2. .pyocd-debug.json (from /init-stm32-project)
    3. build-fw/firmware.elf (default)
    """
    cwd = Path(cwd)

    # 1. .stm32-monitor.yaml
    monitor_yaml = cwd / ".stm32-monitor.yaml"
    if monitor_yaml.exists():
        import yaml
        try:
            with open(monitor_yaml) as f:
                config = yaml.safe_load(f)
            if config and config.get("elf"):
                elf = cwd / config["elf"]
                if elf.exists():
                    return str(elf)
        except Exception:
            log.debug("Failed to parse .stm32-monitor.yaml", exc_info=True)

    # 2. .pyocd-debug.json
    pyocd_json = cwd / ".pyocd-debug.json"
    if pyocd_json.exists():
        import json
        try:
            with open(pyocd_json) as f:
                config = json.load(f)
            elf_path = config.get("elf") or config.get("firmware")
            if elf_path:
                elf = cwd / elf_path
                if elf.exists():
                    return str(elf)
        except Exception:
            log.debug("Failed to parse .pyocd-debug.json", exc_info=True)

    # 3. Default
    default = cwd / "build-fw" / "firmware.elf"
    if default.exists():
        return str(default)

    return None


def read_symbol(elf_path: str, symbol_name: str) -> Optional[dict]:
    """Read a single symbol from ELF, returning addr/section/name."""
    result = subprocess.check_output(
        ["arm-none-eabi-nm", elf_path],
        text=True,
    )
    for line in result.split("\n"):
        parts = line.strip().split()
        if len(parts) >= 3 and parts[-1] == symbol_name:
            try:
                return {
                    "address": int(parts[0], 16),
                    "section": parts[1],
                    "name": symbol_name,
                }
            except ValueError:
                pass
    return None


_MODULE_PATTERNS = [
    (r"^Motor\d", "Motor"),
    (r"^Motor_", "Motor"),
    (r"^CAN\d?_", "CAN"),
    (r"^CANopen", "CANopen"),
    (r"^USART\d?_", "USART"),
    (r"^UART\d?_", "USART"),
    (r"^RS485", "RS485"),
    (r"^GPIO_", "GPIO"),
    (r"^GPO_", "GPIO Output"),
    (r"^GPI_", "GPIO Input"),
    (r"^PC_", "PC Protocol"),
    (r"^YK_", "Remote Control"),
    (r"^BAT_", "Battery"),
    (r"^battery", "Battery"),
    (r"^Light_", "Light"),
    (r"^Wireless", "Wireless Charging"),
    (r"^Navigation", "Navigation"),
    (r"^kinematics", "Kinematics"),
    (r"^ADC", "ADC"),
    (r"^BEEP", "Beeper"),
    (r"^N3D_", "3D Navigation"),
    (r"^test(time)?$", "Timing"),
    (r"^test_", "Timing"),
    (r"^time(_|$)", "Timing"),
    (r"^mem\d", "Memory"),
    (r"^can_tx", "CAN"),
    (r"^can\d?_", "CAN"),
    (r"^receive", "UART RX"),
    (r"^serial", "UART RX"),
    (r"^CS_", "Ultrasonic"),
    (r"^US_", "Ultrasonic"),
    (r"^EM_", "Energy"),
    (r"^DC_", "Drive Controller"),
    (r"^DoubleCS", "Drive Controller"),
    (r"^Driver", "Drive Controller"),
    (r"^drive_", "Drive Controller"),
    (r"^fault_", "Fault"),
    (r"^FLAG", "Flags"),
    (r"^Model_", "Model Config"),
    (r"^Temperature", "Sensor"),
    (r"^Humidity", "Sensor"),
    (r"^depth_camera", "Depth Camera"),
    (r"^Front_depth", "Depth Camera"),
    (r"^Back_depth", "Depth Camera"),
    (r"^Fall", "Fall Detection"),
    (r"^cliff_", "Cliff"),
    (r"^bumper_", "Bumper"),
    (r"^safety_", "Safety"),
    (r"^safe_", "Safety"),
    (r"^emergency", "Safety"),
    (r"^SoftReset", "Safety"),
    (r"^Scram", "Safety"),
]


def _guess_module(name: str) -> str:
    for pattern, module in _MODULE_PATTERNS:
        if re.match(pattern, name):
            return module
    return "Other"
