"""SVD peripheral parser: extract peripheral registers from CMSIS-SVD files."""

import os
import glob
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


def parse_svd(svd_path: str) -> list[dict]:
    """Parse SVD file and return list of peripherals with registers.

    Returns list of dicts: {name, base_address, registers: [{name, offset, size, description}]}
    """
    from cmsis_svd.parser import SVDParser

    svd = Path(svd_path)
    if not svd.exists():
        raise FileNotFoundError(f"SVD file not found: {svd_path}")

    parser = SVDParser.for_xml_file(str(svd))
    device = parser.get_device()

    peripherals = []
    for p in device.peripherals:
        registers = []
        for reg in p.registers:
            registers.append({
                "name": reg.name,
                "offset": reg.address_offset,
                "size": reg.size,
                "description": getattr(reg, "description", ""),
            })
        peripherals.append({
            "name": p.name,
            "base_address": p.base_address,
            "description": getattr(p, "description", ""),
            "registers": registers,
        })

    return peripherals


def find_svd(target: str = "") -> Optional[str]:
    """Auto-discover SVD file from multiple sources.

    Checks:
    1. .stm32-monitor.yaml (project config)
    2. .pyocd-debug.json (from /init-stm32-project)
    3. Any STM32CubeCLT version under C:/ST/
    4. STM32CUBECLT_PATH environment variable
    5. PyOCD built-in SVD
    """
    # 1. .stm32-monitor.yaml
    monitor_yaml = Path(".stm32-monitor.yaml")
    if monitor_yaml.exists():
        import yaml
        try:
            with open(monitor_yaml) as f:
                config = yaml.safe_load(f)
            if config and config.get("svd"):
                svd = Path(config["svd"])
                if svd.exists():
                    return str(svd)
        except Exception:
            log.debug("Failed to parse .stm32-monitor.yaml", exc_info=True)

    # 2. .pyocd-debug.json
    pyocd_json = Path(".pyocd-debug.json")
    if pyocd_json.exists():
        import json
        try:
            with open(pyocd_json) as f:
                config = json.load(f)
            svd_path = config.get("svd")
            if svd_path and Path(svd_path).exists():
                return svd_path
        except Exception:
            log.debug("Failed to parse .pyocd-debug.json", exc_info=True)

    # 3. Search all STM32CubeCLT versions under C:/ST/
    for clt_dir in _find_cubeclt_svd_dirs():
        svd = _find_svd_in_dir(clt_dir, target)
        if svd:
            return svd

    # 4. STM32CUBECLT_PATH environment variable
    env_path = os.environ.get("STM32CUBECLT_PATH", "")
    if env_path:
        svd_dir = Path(env_path) / "STMicroelectronics_CMSIS_SVD"
        if svd_dir.exists():
            svd = _find_svd_in_dir(svd_dir, target)
            if svd:
                return svd

    # 5. PyOCD built-in SVD
    try:
        import pyocd
        pyocd_svd = Path(pyocd.__file__).parent / "debug" / "svd" / "ST"
        if pyocd_svd.exists():
            for svd in sorted(pyocd_svd.glob("*.svd")):
                log.info("Using pyocd built-in SVD: %s", svd)
                return str(svd)
    except Exception:
        log.debug("PyOCD built-in SVD not found", exc_info=True)

    return None


def _find_cubeclt_svd_dirs() -> list[Path]:
    """Find all STM32CubeCLT SVD directories under C:/ST/. Returns by version (newest first)."""
    st_dir = Path("C:/ST")
    if not st_dir.exists():
        return []

    dirs = []
    for d in st_dir.glob("STM32CubeCLT_*"):
        svd_dir = d / "STMicroelectronics_CMSIS_SVD"
        if svd_dir.exists():
            dirs.append(svd_dir)

    # Sort by version string (newest first)
    dirs.sort(key=lambda d: d.parent.name, reverse=True)
    return dirs


def _find_svd_in_dir(svd_dir: Path, target: str = "") -> Optional[str]:
    """Find the best matching SVD file in a directory for the given target."""
    if not svd_dir.exists():
        return None

    if target:
        # Try exact chip match first (e.g. stm32f429zgtx -> STM32F429)
        chip_family = target.upper().rstrip("X")
        # Try various matching strategies
        patterns = [
            f"*{chip_family}*.svd",      # STM32F429*.svd
            f"*{chip_family[:8]}*.svd",   # STM32F429*.svd (shorter prefix)
            f"STM32F4*.svd",              # any F4 series
        ]
        for pattern in patterns:
            matches = sorted(svd_dir.glob(pattern))
            if matches:
                log.info("Found SVD: %s (pattern: %s)", matches[0], pattern)
                return str(matches[0])

    # No target specified: find any STM32F4
    for svd in sorted(svd_dir.glob("STM32F4*.svd")):
        return str(svd)

    # Fallback: any STM32 SVD
    for svd in sorted(svd_dir.glob("STM32*.svd")):
        return str(svd)

    return None


def get_peripheral_registers(svd_path: str, peripheral_name: str) -> list[dict]:
    """Get all registers for a specific peripheral."""
    peripherals = parse_svd(svd_path)
    for p in peripherals:
        if p["name"] == peripheral_name:
            return p["registers"]
    return []
