from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest

from stm32_monitor.models import WatchGroup, WatchItem
from stm32_monitor.protocol import success


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
