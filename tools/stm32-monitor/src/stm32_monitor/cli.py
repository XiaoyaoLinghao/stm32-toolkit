"""CLI entry point for stm32-monitor."""

import sys
import os
import argparse
import logging
import webbrowser
import asyncio
from pathlib import Path

from .config import Config
from .elf_parser import parse_elf, find_elf
from .svd_parser import parse_svd, find_svd
from .pyocd_session import PyOCDSession
from .poller import Poller
from .sse_server import SSEServer

log = logging.getLogger("stm32_monitor")


def main():
    parser = argparse.ArgumentParser(
        description="STM32 Live Monitor — real-time variable monitoring via PyOCD",
    )
    parser.add_argument("--elf", help="Path to firmware ELF file (auto-discovered if omitted)")
    parser.add_argument("--target", default="stm32f429zgtx", help="Target chip (default: stm32f429zgtx)")
    parser.add_argument("--svd", help="Path to SVD file (auto-discovered if omitted)")
    parser.add_argument("--port", type=int, default=8888, help="Web server port (default: 8888)")
    parser.add_argument("--interval", type=int, default=1000, help="Poll interval in ms (default: 1000)")
    parser.add_argument("--preset", help="(deprecated) Use browser UI to save/load watch groups instead")
    parser.add_argument("--no-open", action="store_true", help="Don't open browser automatically")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # Load project config
    config = Config()
    if args.elf:
        config.set("elf", args.elf)
    if args.svd:
        config.set("svd", args.svd)

    # ---- ELF discovery ----
    _original_cwd = Path.cwd()
    elf_path = config.elf
    if elf_path and not Path(elf_path).is_absolute():
        elf_path = str(_original_cwd / elf_path)
    if not elf_path:
        elf_path = find_elf(str(_original_cwd))
    if not elf_path:
        print("ERROR: No firmware ELF file found.")
        print()
        print("  Expected:  build-fw/firmware.elf")
        print("  Or set:    stm32-monitor --elf <path>")
        print()
        print("  If this is a new STM32 project, run:")
        print("    /init-stm32-project    (generate CMake + VSCode config)")
        print("    Ctrl+Shift+B           (build firmware)")
        print("  Then try again.")
        print()
        print("  For Keil projects, run /migrate-keil first.")
        sys.exit(1)
    print(f"ELF: {elf_path}")

    # ---- ELF parsing ----
    print("Parsing ELF symbols...")
    elf_vars = parse_elf(elf_path)
    modules = sorted(set(v.get("module", "Other") for v in elf_vars))
    print(f"  Found {len(elf_vars)} global variables in {len(modules)} modules")

    # ---- SVD discovery ----
    svd_path = config.svd
    if svd_path and not Path(svd_path).is_absolute():
        svd_path = str(_original_cwd / svd_path)
    if not svd_path:
        svd_path = find_svd(args.target)
    svd_peripherals = []
    if svd_path:
        print(f"SVD: {svd_path}")
        try:
            svd_peripherals = parse_svd(svd_path)
            print(f"  Found {len(svd_peripherals)} peripherals")
        except Exception as e:
            print(f"  WARNING: SVD parse failed: {e}")
    else:
        print("SVD: not found (peripheral register monitoring disabled)")
        print("  Set STM32CUBECLT_PATH or configure .stm32-monitor.yaml")

    # ---- Probe connection ----
    print(f"Connecting to {args.target} (attach mode)...")
    print("  (Probe shown as 'n/a' in pyocd list if target not powered or SWD not connected)")

    session = PyOCDSession(target=args.target)
    try:
        session.open()
        print("  Connected. CPU running (not halted).")
    except Exception as e:
        print(f"ERROR: Cannot connect to target: {e}")
        print()
        print("Troubleshooting:")
        print("  1. Check SWDIO/SWCLK/GND connections")
        print("  2. Verify target board is powered")
        print("  3. Run: pyocd list  (check probe detected)")
        print("  4. Run: pyocd pack install stm32f429zgtx")
        sys.exit(1)

    # ---- Poller ----
    poller = Poller(session, poll_interval_ms=config.poll_interval_ms if not args.interval == 1000 else args.interval)
    poller.start()

    # ---- No built-in presets; users save/load via the browser UI ----
    if args.preset:
        print("Note: --preset is deprecated. Use the browser UI to save/load watch groups.")

    # ---- Web server ----
    def make_session():
        s = PyOCDSession(target=args.target)
        s.open()
        return s

    print(f"\nStarting web interface at http://localhost:{args.port}")
    server = SSEServer(poller, make_session, port=args.port)
    server.set_session(session)
    server.set_variable_data(elf_vars, svd_peripherals)

    # Open browser
    if not args.no_open:
        import threading
        def open_browser():
            import time
            time.sleep(1)
            webbrowser.open(f"http://localhost:{args.port}")
        threading.Thread(target=open_browser, daemon=True).start()

    # Run async server
    try:
        asyncio.run(_run_server(server))
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        poller.stop()
        session.close()
        print("Done.")


async def _run_server(server: SSEServer):
    runner = await server.start()
    while True:
        await asyncio.sleep(1)
