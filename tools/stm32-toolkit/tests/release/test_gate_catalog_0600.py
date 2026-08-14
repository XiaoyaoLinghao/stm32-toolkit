from __future__ import annotations

import copy
import hashlib
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

EXPECTED_FAMILY_RECORD_SHA256 = (
    "4c906acd9df70ceb22232c2ad2f8b526295df279baaed2d460d020edb4c3cd14",
    "9ace3bc4aca6021cb5bcade45c2f17de3a3a2eadc88c63b5e04e9e751477183b",
    "3f356eaaccab9278254b004859a291b1429193f6e0154f79d97a2833bc42ec15",
    "22a61556627769a5c4a20fba28f95a737ee218eaafe51a525a8df9d06f281c73",
    "7a3d8496791cdbb649ba37d658ced135a3dc24752f4f12a71b9c6118623069c0",
    "5df07d13412ce0f25cd401c46467fb2f136d69efd00b84afb2ac63e12f1beae2",
    "652dab609b52a588d773c22f96323304b43b6055aa9dee6ec9435ef5a92676ad",
    "d7baff1ebc507c4a925075004cd1388bd505ae9ab4eb2ba1806280528e7936a3",
    "c09f9dd956a50b53e9ee10646f8c72a6bf43b1fa4267f4582e67446921998732",
    "0db981533248f5e31c9cc552d9766d7aeaf60d58dfcf3556ce69500416ba8b54",
    "904a6583093405ca82dd0c01be6bdea0a514e894d5b64ba3361ba3b80ebae945",
    "2467f95df820de9d810e9c591db0371c3d2d98a55ab1553cbb9d29339d68e707",
    "08fb13f7c226385993a3d0636a5405e92005cbb9cd3c688ac14590eb09d2d64b",
    "1e9123ce76d7077a152b7d23d41baca43b15109d2ec713525546a70803566c06",
    "0543faf083aaff73d7494d9576fd181c4676910cde69ae9b44cfcb64851ae8e0",
)

EXPECTED_GATE_RECORD_SHA256 = (
    "ed1bee5a7edf14974f9cf035ac22a88b6db74caad5e4e5b62108eba872cc59cb",
    "910de3ce827b80e3997bea83dbfa3e266589a18ebc73909a388a2879759b6ffb",
    "529208f0ae2df3587b497bcb6f6818fecbacdffa3c869685aaa757b3f1324c2c",
    "13b5d5255e20dde26749da338217bb0943c2d5c36b1bdee1923512280f29f093",
    "51932db7d5b09977b8082324cdc0925e14622bf925e2409df02335e2796c28a5",
    "2d252a94a8b7a1935a79a484cf1e20f3b59451e14d718b4babb70e867430507b",
    "03a133db57a4d616ccf2e3dd1e26be2d1d64109dc0942f2ac30e623d41694581",
    "b3892476cd7f2719d7950480737e3f6330606f5f1000c873f1b7b84c09be2403",
    "47992f3a75feebfec39dab2b74952cfaeea7fdc448149385219cd17159e04067",
    "575de8621866ab27272f9295465db59907d51c4fb6ea3da2190162ca3a41739a",
)


@pytest.fixture
def catalog_data() -> dict[str, object]:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def test_gate_families_and_module_slots_are_frozen() -> None:
    """Deleting, renaming, or making a reserved module slot executable must fail."""
    catalog = load_catalog(CATALOG)

    assert catalog.family_ids == EXPECTED_FAMILY_IDS
    assert all(not entry.command_argv for entry in catalog.reserved_entries())
    assert all(not entry.node_ids for entry in catalog.reserved_entries())


def test_every_family_and_gate_record_matches_independent_literal_digest(
    catalog_data: dict[str, object],
) -> None:
    """Every scalar, list order, version, binding, timeout, and nested field is literal-bound."""
    digest = lambda value: hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    assert tuple(digest(item) for item in catalog_data["families"]) == EXPECTED_FAMILY_RECORD_SHA256
    assert tuple(digest(item) for item in catalog_data["gates"]) == EXPECTED_GATE_RECORD_SHA256


def test_every_semantic_field_of_every_family_rejects_type_correct_mutation(
    catalog_data: dict[str, object],
) -> None:
    """The validator compares every family field for all 15 records, not a sampled row."""
    mutators = (
        lambda row: row.__setitem__("id", row["id"] + "-MUTATED"),
        lambda row: row.__setitem__("module", "STM32TK-9999"),
        lambda row: row.__setitem__("purpose", "mutated purpose"),
        lambda row: row.__setitem__("owner_class", "mutated-owner"),
        lambda row: row.__setitem__("platform_class", "mutated-platform"),
        lambda row: row.__setitem__("evidence_type", "mutated-evidence"),
        lambda row: row.__setitem__("coverage_context", "mutated-context"),
        lambda row: row.__setitem__("matrices", ["mutated-matrix"]),
        lambda row: row.__setitem__("prerequisites", [] if row["prerequisites"] else ["EVIDENCE-0601"]),
        lambda row: row.__setitem__("command_argv", ["mutated-tool"]),
        lambda row: row.__setitem__("node_ids", ["mutated::node"]),
        lambda row: row.__setitem__("reserved", False),
        lambda row: row["impact_map"].__setitem__("product_paths", ["mutated/product"]),
        lambda row: row["impact_map"].__setitem__("test_paths", ["mutated/test"]),
    )
    for index in range(15):
        for mutate in mutators:
            candidate = copy.deepcopy(catalog_data)
            mutate(candidate["families"][index])
            with pytest.raises(CatalogError):
                validate_catalog_data(candidate, repo=REPO)


def test_every_semantic_field_of_every_hardware_gate_rejects_type_correct_mutation(
    catalog_data: dict[str, object],
) -> None:
    """All 10 gates freeze identities, versions, sources, locks, impact, and execution fields."""
    mutators = (
        lambda row: row.__setitem__("id", row["id"] + "-MUTATED"),
        lambda row: row.__setitem__("family_id", "HW-0600-DIAGNOSTIC" if row["family_id"] != "HW-0600-DIAGNOSTIC" else "HW-0600-TRANSPORT"),
        lambda row: row.__setitem__("contract", "9999"),
        lambda row: row.__setitem__("phase", "mutated-phase"),
        lambda row: row.__setitem__("owner_class", "Codex"),
        lambda row: row.__setitem__("platform_class", "mutated-platform"),
        lambda row: row.__setitem__("evidence_type", "mutated-evidence"),
        lambda row: row.__setitem__("coverage_context", "mutated-context"),
        lambda row: row.__setitem__("matrices", ["mutated-matrix"]),
        lambda row: row.__setitem__("working_directory", "tools"),
        lambda row: row.__setitem__("command_argv", ["mutated-tool"]),
        lambda row: row.__setitem__("required_tools", ["python312==0.0.0"]),
        lambda row: row.__setitem__("timeout_seconds", 901),
        lambda row: row.__setitem__("evidence_files", ["mutated.json"]),
        lambda row: row.__setitem__("node_inventory_source", "mutated.json"),
        lambda row: row.__setitem__("node_ids", ["mutated::node"]),
        lambda row: row.__setitem__("prerequisites", [] if row["prerequisites"] else ["STM32TK-HW-0600-MAILBOX"]),
        lambda row: row["resource_locks"].__setitem__("board", "mutated:board"),
        lambda row: row["impact_map"].__setitem__("product_paths", ["mutated/product"]),
        lambda row: row["impact_map"].__setitem__("test_paths", ["mutated/test"]),
        lambda row: row.__setitem__("source_binding", None if row["source_binding"] is not None else {
            "claim": "new-0600-catalog-id-for-historical-deferred-behavior",
            "path": "missing.md", "start_line": 1, "end_line": 1, "sha256": "0" * 64,
        }),
    )
    for index in range(10):
        for mutate in mutators:
            candidate = copy.deepcopy(catalog_data)
            mutate(candidate["gates"][index])
            with pytest.raises(CatalogError):
                validate_catalog_data(candidate, repo=REPO)


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


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("module", "STM32TK-0602"),
        ("purpose", "different purpose"),
        ("owner_class", "user"),
        ("platform_class", "linux-python"),
        ("evidence_type", "release"),
        ("coverage_context", "controller-off"),
        ("matrices", ["candidate-0601"]),
        ("impact_map", {"product_paths": ["tools/release"], "test_paths": ["tests"]}),
    ],
)
def test_every_family_semantic_field_is_frozen(
    catalog_data: dict[str, object], field: str, replacement: object
) -> None:
    """A well-typed but different family contract must not pass structural validation."""
    catalog_data["families"][0][field] = replacement

    with pytest.raises(CatalogError):
        validate_catalog_data(catalog_data, repo=REPO)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("phase", "candidate"),
        ("owner_class", "Codex"),
        ("platform_class", "windows-python"),
        ("evidence_type", "release"),
        ("coverage_context", "product-evidence"),
        ("matrices", ["hardware-0600"]),
        ("working_directory", "tools"),
        ("required_tools", ["python312"]),
        ("timeout_seconds", 901),
        ("evidence_files", ["result.json"]),
        ("impact_map", {"product_paths": ["tools/release"], "test_paths": ["tests"]}),
    ],
)
def test_every_hardware_gate_semantic_field_is_frozen(
    catalog_data: dict[str, object], field: str, replacement: object
) -> None:
    """A type-correct hardware gate semantic mutation must be rejected."""
    catalog_data["gates"][0][field] = replacement

    with pytest.raises(CatalogError):
        validate_catalog_data(catalog_data, repo=REPO)


def test_hardware_tools_are_bound_to_exact_frozen_versions(
    catalog_data: dict[str, object]
) -> None:
    """A support tool name without its frozen version is not an executable contract."""
    catalog_data["gates"][0]["required_tools"] = [
        "python312==3.12.10",
        "pyocd==0.45.1",
    ]

    validate_catalog_data(catalog_data, repo=REPO)
    catalog_data["gates"][0]["required_tools"] = ["python312", "pyocd==0.45.1"]
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
