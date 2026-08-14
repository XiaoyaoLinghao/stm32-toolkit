from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[4]
RELEASE = REPO / "tools" / "release"
sys.path.insert(0, str(RELEASE))

from verify_0600_release import (  # noqa: E402
    CatalogError,
    load_catalog,
    load_performance_catalog,
    validate_catalog_data,
    validate_performance_catalog_data,
)


CATALOG = RELEASE / "gates_0600.json"
PERFORMANCE = RELEASE / "performance_0600.json"

EXPECTED_FAMILY_IDS = (
    "EVIDENCE-0601",
    "DIAGNOSTICS-0601",
    "ANALYTICS-0601",
    "RELEASE-0601",
    "EVIDENCE-0602",
    "DIAGNOSTICS-0602",
    "ANALYTICS-0602",
    "RELEASE-0602",
    "EVIDENCE-0603",
    "DIAGNOSTICS-0603",
    "ANALYTICS-0603",
    "RELEASE-0603",
    "HW-0400-DEFERRED",
    "HW-0600-TRANSPORT",
    "HW-0600-DIAGNOSTIC",
)

EXPECTED_HARDWARE_GATE_IDS = (
    "STM32TK-HW-0400-PROBE-ATTACH-READ",
    "STM32TK-HW-0400-FLASH-READBACK",
    "STM32TK-HW-0400-HANDOFF-REACQUIRE",
    "STM32TK-HW-0400-TYPED-READ-SAMPLE-FAULT",
    "STM32TK-HW-0400-CLI-MCP-WORKFLOWS",
    "STM32TK-HW-0600-MAILBOX",
    "STM32TK-HW-0600-RTT",
    "STM32TK-HW-0600-UART",
    "STM32TK-HW-0600-SEMIHOSTING",
    "STM32TK-HW-0600-DIAGNOSTIC-CHAIN",
)

EXPECTED_SOURCE_BINDINGS = {
    "STM32TK-HW-0400-PROBE-ATTACH-READ": (
        "docs/codex/returns/STM32TK-0402-PYOCD-BACKEND/implementation-report.md",
        122,
        124,
        "b8cc975899f28e30a466097b7b0934b10faaf285fef670f8e98a806226934a30",
    ),
    "STM32TK-HW-0400-FLASH-READBACK": (
        "docs/codex/returns/STM32TK-0403-FLASH-HANDOFF/implementation-report.md",
        130,
        133,
        "0ffe0dd5e78aee1899da7b52f19fb6c2c6104af71d28a5ccf02b705e66dd3449",
    ),
    "STM32TK-HW-0400-HANDOFF-REACQUIRE": (
        "docs/codex/returns/STM32TK-0403-FLASH-HANDOFF/implementation-report.md",
        130,
        133,
        "0ffe0dd5e78aee1899da7b52f19fb6c2c6104af71d28a5ccf02b705e66dd3449",
    ),
    "STM32TK-HW-0400-TYPED-READ-SAMPLE-FAULT": (
        "docs/codex/returns/STM32TK-0404-TYPED-DEBUG/implementation-report.md",
        138,
        140,
        "9565b2053322f527ccc29b3eba95673d5cc19ada9f653e241c3f10a7e84a4bdf",
    ),
    "STM32TK-HW-0400-CLI-MCP-WORKFLOWS": (
        "docs/codex/returns/STM32TK-0405-CLI-MCP-RELEASE/implementation-report.md",
        140,
        142,
        "18aef58476244b43784caafa060ee19081ecd9c7af37f81b1f7823fbcdd84f50",
    ),
}


@pytest.fixture
def catalog_data() -> dict[str, object]:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def test_gate_families_and_module_slots_are_frozen() -> None:
    """Deleting, renaming, or making a reserved module slot executable must fail."""
    catalog = load_catalog(CATALOG)

    assert catalog.family_ids == EXPECTED_FAMILY_IDS
    assert all(not entry.command_argv for entry in catalog.reserved_entries())
    assert all(not entry.node_ids for entry in catalog.reserved_entries())


def test_hardware_gate_ids_and_dispatch_sets_are_exact_and_non_executable() -> None:
    """A renamed, omitted, or prematurely activated deferred hardware gate is invalid."""
    catalog = load_catalog(CATALOG)

    assert catalog.gate_ids == EXPECTED_HARDWARE_GATE_IDS
    assert catalog.hardware_gate_ids("0400") == EXPECTED_HARDWARE_GATE_IDS[:5]
    assert catalog.hardware_gate_ids("0600") == EXPECTED_HARDWARE_GATE_IDS[5:]
    assert all(not gate.command_argv and not gate.node_ids for gate in catalog.gates)


def test_hardware_entries_lock_board_probe_uart_and_evidence_root() -> None:
    """Removing any frozen physical/evidence lock must make concurrent dispatch unsafe."""
    catalog = load_catalog(CATALOG)
    expected = {
        "board": "hardware-input:board_id",
        "probe": "hardware-input:probe_serial_hash",
        "uart": "hardware-input:uart_serial_hash",
        "evidence-root": "checkpoint:evidence_root",
    }

    assert all(gate.resource_locks == expected for gate in catalog.gates)


def test_0400_ids_are_bound_to_exact_historical_paragraphs_without_historical_id_claims() -> None:
    """Moving or editing a cited 0.4 paragraph must break its newly defined 0.6-catalog ID."""
    catalog = load_catalog(CATALOG)
    by_id = {gate.gate_id: gate for gate in catalog.gates}

    for gate_id, (path, start, end, digest) in EXPECTED_SOURCE_BINDINGS.items():
        binding = by_id[gate_id].source_binding
        assert binding is not None
        assert (binding.path, binding.start_line, binding.end_line, binding.sha256) == (
            path,
            start,
            end,
            digest,
        )
        assert binding.claim == "new-0600-catalog-id-for-historical-deferred-behavior"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.__setitem__("unexpected", None),
        lambda value: value.pop("resource_lock_types"),
        lambda value: value["families"][0].__setitem__("unexpected", None),
        lambda value: value["families"][0].pop("impact_map"),
        lambda value: value["families"][0]["impact_map"].__setitem__("extra", []),
        lambda value: value["gates"][0].__setitem__("unexpected", None),
        lambda value: value["gates"][0].pop("evidence_files"),
        lambda value: value["gates"][0]["source_binding"].__setitem__("extra", "x"),
    ],
)
def test_catalog_is_recursively_closed(
    catalog_data: dict[str, object], mutate: object
) -> None:
    """An extra or missing field at any catalog nesting level must be rejected."""
    mutate(catalog_data)

    with pytest.raises(CatalogError):
        validate_catalog_data(catalog_data, repo=REPO)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["families"].append(copy.deepcopy(value["families"][0])),
        lambda value: value["gates"].append(copy.deepcopy(value["gates"][0])),
        lambda value: value["families"].pop(),
        lambda value: value["gates"].pop(),
        lambda value: value["families"][0].__setitem__("reserved", False),
        lambda value: value["families"][0]["command_argv"].append("pytest"),
        lambda value: value["families"][0]["node_ids"].append("fictional::node"),
        lambda value: value["gates"][0]["command_argv"].append("pytest"),
        lambda value: value["gates"][0]["node_ids"].append("fictional::node"),
    ],
)
def test_catalog_rejects_duplicates_missing_unreserved_and_executable_future_slots(
    catalog_data: dict[str, object], mutate: object
) -> None:
    """A duplicate, incomplete, activated, or fabricated reservation must fail closed."""
    mutate(catalog_data)

    with pytest.raises(CatalogError):
        validate_catalog_data(catalog_data, repo=REPO)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["families"][0]["prerequisites"].append("UNKNOWN-FAMILY"),
        lambda value: value["families"][0]["prerequisites"].append("DIAGNOSTICS-0601")
        or value["families"][1]["prerequisites"].append("EVIDENCE-0601"),
        lambda value: value["gates"][0]["prerequisites"].append("UNKNOWN-GATE"),
        lambda value: value["gates"][0]["prerequisites"].append(value["gates"][1]["id"])
        or value["gates"][1]["prerequisites"].append(value["gates"][0]["id"]),
    ],
)
def test_catalog_rejects_unknown_and_cyclic_prerequisites(
    catalog_data: dict[str, object], mutate: object
) -> None:
    """Unknown or cyclic dependencies must not be interpreted as blocked/pass ordering."""
    mutate(catalog_data)

    with pytest.raises(CatalogError):
        validate_catalog_data(catalog_data, repo=REPO)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["families"][0].__setitem__("matrices", "quick-0601"),
        lambda value: value["families"][0].__setitem__("reserved", 1),
        lambda value: value["gates"][0].__setitem__("timeout_seconds", True),
        lambda value: value["gates"][0].__setitem__("required_tools", {}),
        lambda value: value["gates"][0]["impact_map"].__setitem__("product_paths", "x"),
        lambda value: value["gates"][0]["resource_locks"].__setitem__("board", []),
    ],
)
def test_catalog_rejects_wrong_json_types_including_boolean_as_integer(
    catalog_data: dict[str, object], mutate: object
) -> None:
    """JSON coercion must not turn strings, objects, or booleans into catalog values."""
    mutate(catalog_data)

    with pytest.raises(CatalogError):
        validate_catalog_data(catalog_data, repo=REPO)


def test_catalog_rejects_changed_historical_paragraph_binding(
    catalog_data: dict[str, object]
) -> None:
    """A declared digest cannot replace rereading the exact report paragraph."""
    catalog_data["gates"][0]["source_binding"]["sha256"] = "0" * 64

    with pytest.raises(CatalogError):
        validate_catalog_data(catalog_data, repo=REPO)


def test_empty_performance_catalog_schema_is_versioned_and_closed() -> None:
    """Task 2 must not fabricate a workload or accepted calibration before its module exists."""
    profile = load_performance_catalog(PERFORMANCE)

    assert profile == {"profiles": [], "schema": "stm32-performance-catalog/1"}


@pytest.mark.parametrize(
    "value",
    [
        {"schema": "stm32-performance-catalog/1", "profiles": [], "extra": None},
        {"schema": "stm32-performance-catalog/1"},
        {"schema": "stm32-performance-catalog/0", "profiles": []},
        {"schema": "stm32-performance-catalog/1", "profiles": {}},
        {"schema": "stm32-performance-catalog/1", "profiles": [None]},
    ],
)
def test_performance_catalog_rejects_extra_missing_wrong_schema_and_wrong_type(
    value: object,
) -> None:
    """Unknown fields and non-profile values cannot become implicit release thresholds."""
    with pytest.raises(CatalogError):
        validate_performance_catalog_data(value)
