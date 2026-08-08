from __future__ import annotations

import ast
import importlib
import importlib.util
import sys
import tomllib
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
    assert not (PACKAGE_ROOT / "static").exists()


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
                    if value.startswith("stm32") and any(char.isdigit() for char in value):
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
    tmp_path: Path, monkeypatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    for name in tuple(sys.modules):
        if name == "stm32_monitor" or name.startswith("stm32_monitor."):
            sys.modules.pop(name)
    imported = importlib.import_module("stm32_monitor")
    assert imported.__version__ == "0.4.0"
    assert not any(
        name == "pyocd" or name.startswith(("pyocd.", "cmsis_svd.", "yaml."))
        for name in sys.modules
    )
    assert tuple(project.iterdir()) == ()


def test_package_dependency_contract_uses_only_toolkit_and_aiohttp() -> None:
    metadata = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text("utf-8"))
    project = metadata["project"]
    assert project["name"] == "stm32-monitor"
    assert project["version"] == "0.4.0"
    assert project["dependencies"] == [
        "stm32-toolkit==0.4.0",
        "aiohttp>=3.9,<4",
    ]
