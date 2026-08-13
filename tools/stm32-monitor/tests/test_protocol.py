from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest

from stm32_monitor.models import WatchGroup, WatchItem
from stm32_monitor.protocol import (
    _known_model_payload,
    _serialize_protocol_value,
    _snapshot_protocol_value,
    success,
)


NOW = datetime(2026, 8, 8, 1, 2, 3, tzinfo=timezone.utc)


def _groups(group_count: int, items_per_group: int) -> tuple[WatchGroup, ...]:
    return tuple(
        WatchGroup(
            UUID(int=group_index + 1),
            f"G{group_index:03d}",
            "",
            250,
            tuple(
                WatchItem.variable(f"value_{group_index}_{item_index}")
                for item_index in range(items_per_group)
            ),
            1,
            NOW,
            NOW,
        )
        for group_index in range(group_count)
    )


@pytest.mark.parametrize(
    ("group_count", "items_per_group"), ((1, 1), (128, 32))
)
def test_group_tuple_results_detach_single_and_full_4096_item_graphs(
    group_count: int, items_per_group: int
) -> None:
    groups = _groups(group_count, items_per_group)
    expected = success("groups.list", _groups(group_count, items_per_group))
    result = success("groups.list", groups)
    before = result.to_dict()
    before_repr = repr(result)

    assert result == expected
    assert result.data is not groups
    assert result.data[0] is not groups[0]
    assert result.data[0].items[0] is not groups[0].items[0]

    original_item = groups[0].items[0]
    original_group = groups[0]
    object.__setattr__(original_item, "selector", "tampered-item")
    object.__setattr__(original_group, "name", "Tampered group")
    object.__setattr__(original_group, "items", ())

    assert result.to_dict() == before
    assert repr(result) == before_repr
    assert result == expected


def test_group_tuple_results_reject_nested_subclasses_and_forged_values() -> None:
    class DerivedItem(WatchItem):
        pass

    derived = DerivedItem.variable("counter")
    group_with_subclass = WatchGroup(
        UUID(int=1), "Core", "", 250, (derived,), 1, NOW, NOW
    )
    with pytest.raises((TypeError, ValueError)):
        success("groups.list", (group_with_subclass,))

    forged = WatchItem.variable("counter")
    group_with_forgery = WatchGroup(
        UUID(int=2), "Core", "", 250, (forged,), 1, NOW, NOW
    )
    object.__setattr__(forged, "kind", "address")
    with pytest.raises((TypeError, ValueError)):
        success("groups.list", (group_with_forgery,))

    object.__setattr__(group_with_forgery, "items", [WatchItem.variable("counter")])
    with pytest.raises((TypeError, ValueError)):
        success("groups.list", (group_with_forgery,))


def _forged_class(module: str, name: str):
    """A JSON-encodable lookalike that spoofs a product type's module and name."""
    forged = type(name, (dict,), {"__module__": module})
    forged.__name__ = name
    return forged()


def test_known_model_payload_accepts_real_history_page() -> None:
    from stm32_monitor.history import HistoryPage

    page = HistoryPage.create((), next_cursor=None)
    assert _known_model_payload(page) == page.to_dict()


def test_known_model_payload_accepts_real_export_artifact() -> None:
    from pathlib import Path
    from uuid import UUID

    from stm32_monitor.exports import ExportArtifact

    artifact = ExportArtifact(
        UUID(int=1), Path("/tmp"), Path("/tmp/history.jsonl"),
        Path("/tmp/history.json"), "a" * 64, 4, 1,
    )
    assert _known_model_payload(artifact) == artifact.to_dict()


def test_known_model_payload_falls_through_for_forged_history_and_export() -> None:
    forged_history = _forged_class("stm32_monitor.history", "HistoryPage")
    forged_export = _forged_class("stm32_monitor.exports", "ExportArtifact")
    assert _known_model_payload(forged_history) is None
    assert _known_model_payload(forged_export) is None


def test_snapshot_and_serialize_take_the_identity_mismatch_fallthrough() -> None:
    forged_group = _forged_class("stm32_monitor.models", "GroupPage")
    forged_history = _forged_class("stm32_monitor.history", "HistoryPage")
    # Each call exercises the "module/name match but identity differs" fallthrough
    # in both the snapshot and serialization paths.  Forged values are not exact
    # JSON value types, so the helpers reject them with TypeError after taking
    # the identity-mismatch branch.
    assert _known_model_payload(forged_group) is None
    with pytest.raises(TypeError):
        _snapshot_protocol_value(forged_group)
    with pytest.raises(TypeError):
        _snapshot_protocol_value(forged_history)
    with pytest.raises(TypeError):
        _serialize_protocol_value(forged_group)
    with pytest.raises(TypeError):
        _serialize_protocol_value(forged_history)


def test_plain_list_and_tuple_payloads_are_snapshotted_not_frozen_in_place() -> None:
    result = success("example.op", (1, 2, 3))
    assert result.data == (1, 2, 3)
    assert result.to_dict()["data"] == [1, 2, 3]

    list_result = success("example.op", [{"a": 1}])
    assert list_result.to_dict()["data"] == [{"a": 1}]


def test_watch_group_collection_exceeding_128_groups_is_rejected() -> None:
    with pytest.raises(ValueError):
        success("groups.list", _groups(129, 1))
