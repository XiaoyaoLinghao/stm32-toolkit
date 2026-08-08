from __future__ import annotations

import ast
import importlib.util
import re
import subprocess
import sys
from pathlib import Path


PACKAGE_ROOT = Path(__file__).parents[1]
SOURCE_ROOT = PACKAGE_ROOT / "src" / "stm32_monitor"
LEGACY_MODULES = (
    "config",
    "elf_parser",
    "svd_parser",
    "pyocd_session",
    "poller",
    "sse_server",
)
FORBIDDEN_DIRECT_IMPORTS = {"pyocd", "cmsis_svd", "yaml", "subprocess"}
FORBIDDEN_TEXT = (
    "localhost",
    ".stm32-monitor.yaml",
    ".pyocd-debug.json",
    "localstorage",
    "add_static",
    "taskkill",
    "stop-process",
    "pkill",
)


def _python_sources() -> tuple[Path, ...]:
    return tuple(sorted(SOURCE_ROOT.glob("*.py")))


def test_legacy_runtime_modules_and_static_assets_are_absent() -> None:
    for module_name in LEGACY_MODULES:
        assert not (SOURCE_ROOT / f"{module_name}.py").exists()
        assert importlib.util.find_spec(f"stm32_monitor.{module_name}") is None
    static_root = PACKAGE_ROOT / "static"
    assert not static_root.exists() or not any(static_root.rglob("*"))


def test_monitor_source_has_no_backend_process_or_legacy_runtime_path() -> None:
    findings: list[str] = []
    for path in _python_sources():
        source = path.read_text(encoding="utf-8")
        lowered = source.casefold()
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.partition(".")[0] for alias in node.names}
                if roots & FORBIDDEN_DIRECT_IMPORTS:
                    findings.append(f"{path.name}:{node.lineno}:forbidden import")
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").partition(".")[0]
                if root in FORBIDDEN_DIRECT_IMPORTS:
                    findings.append(f"{path.name}:{node.lineno}:forbidden import")
            elif isinstance(node, ast.Call):
                function = node.func
                if (
                    isinstance(function, ast.Attribute)
                    and isinstance(function.value, ast.Name)
                    and function.value.id == "os"
                    and function.attr in {"system", "kill", "killpg"}
                ):
                    findings.append(f"{path.name}:{node.lineno}:process control")
            elif isinstance(node, ast.Constant):
                if node.value == 8888:
                    findings.append(f"{path.name}:{node.lineno}:fixed port")
                if isinstance(node.value, str):
                    value = node.value.casefold()
                    if any(token in value for token in FORBIDDEN_TEXT):
                        findings.append(f"{path.name}:{node.lineno}:legacy runtime text")
                    if re.fullmatch(r"stm32[a-z]\d+[a-z0-9]*", value):
                        findings.append(f"{path.name}:{node.lineno}:default target")
        assert "from pyocd" not in lowered
    assert findings == []


def test_public_models_expose_no_raw_address_override() -> None:
    raw_address_fields: list[str] = []
    for path in _python_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if node.target.id.casefold() in {"address", "raw_address"}:
                    raw_address_fields.append(f"{path.name}:{node.lineno}")
    assert raw_address_fields == []


def test_ordinary_import_is_backend_lazy_and_does_not_write_project(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    check = """
import pathlib
import sys
sys.path.insert(0, sys.argv[1])
import stm32_monitor

assert stm32_monitor.__version__ == "0.4.0"
assert not any(
    name == "pyocd" or name.startswith(("pyocd.", "cmsis_svd.", "yaml."))
    for name in sys.modules
)
assert tuple(pathlib.Path.cwd().iterdir()) == ()
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-c", check, str(PACKAGE_ROOT / "src")],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert tuple(project.iterdir()) == ()


def test_package_dependency_contract_uses_only_toolkit_and_aiohttp() -> None:
    metadata_path = PACKAGE_ROOT / "pyproject.toml"
    assert metadata_path.stat().st_size <= 16 * 1024
    text = metadata_path.read_text(encoding="utf-8")
    assert '[project]\nname = "stm32-monitor"\nversion = "0.4.0"' in text
    prefix, marker, remainder = text.partition("dependencies = [")
    assert marker and prefix.count("dependencies") == 0
    dependency_text, closing, suffix = remainder.partition("]")
    assert closing and "dependencies" not in suffix
    dependencies = [
        line.strip().rstrip(",").strip('"')
        for line in dependency_text.splitlines()
        if line.strip()
    ]
    assert dependencies == [
        "stm32-toolkit==0.4.0",
        "aiohttp>=3.9,<4",
    ]
    lowered = text.casefold()
    assert not any(name in lowered for name in ("pyocd", "cmsis-svd", "pyyaml"))
