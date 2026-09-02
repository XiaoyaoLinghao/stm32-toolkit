from __future__ import annotations

import importlib

import pytest


ATK_RAW = "ATK 20210914"
ATK_FINGERPRINT = "91d67402fe525a5d16bf226f59ab5ecea743eb69292e95719167263ed1fcbf8c"
ATK_SELECTOR = f"pyocd:{ATK_FINGERPRINT}"
LEGACY_RAW = "pyocd:legacy"
LEGACY_FINGERPRINT = "bd0fce68dc31a926e34b66a939564f46d56e0a6f835cf4ce453d69189e0a6bfb"
LEGACY_SELECTOR = f"pyocd:{LEGACY_FINGERPRINT}"
UNICODE_RAW = "探针 Ω Rev.B"
UNICODE_FINGERPRINT = "6f23f413153b810e751b25dee534d9f06237c3ac8295c0ccddb1ea1a002ee6d9"
PUNCTUATION_RAW = r"CMSIS-DAP_QM Rev.B #001 / \\ port *"
PUNCTUATION_FINGERPRINT = "4e5935ae758f5ba95bbad47253a8cf23e1bdedd44731aba13da92ac38277446f"


def _selector_api():
    """Load the production adapter while turning its absence into a RED failure."""
    try:
        module = importlib.import_module("stm32_toolkit.probe.selector")
    except ModuleNotFoundError as error:
        if error.name == "stm32_toolkit.probe.selector":
            pytest.fail("probe selector adapter is not implemented")
        raise
    try:
        return (
            module.valid_hardware_probe_id,
            module.probe_fingerprint,
            module.public_probe_selector,
        )
    except AttributeError as error:
        pytest.fail(f"probe selector adapter is incomplete: {error}")


def test_nonportable_hardware_id_maps_to_full_portable_selector():
    valid_hardware_probe_id, probe_fingerprint, public_probe_selector = _selector_api()

    assert valid_hardware_probe_id(ATK_RAW)
    assert probe_fingerprint(ATK_RAW) == ATK_FINGERPRINT
    assert public_probe_selector(ATK_RAW) == ATK_SELECTOR


def test_existing_portable_selectors_remain_exact():
    _valid_hardware_probe_id, _probe_fingerprint, public_probe_selector = _selector_api()

    assert public_probe_selector("probe-a") == "probe-a"
    assert public_probe_selector("0001A0000000") == "0001A0000000"


def test_reserved_prefix_is_never_treated_as_raw_public_selector():
    _valid_hardware_probe_id, probe_fingerprint, public_probe_selector = _selector_api()
    raw = "pyocd:" + "a" * 64

    assert public_probe_selector(raw) == "pyocd:" + probe_fingerprint(raw)
    assert public_probe_selector(raw) != raw


def test_reserved_legacy_raw_hardware_id_is_remapped_to_a_generated_selector():
    valid_hardware_probe_id, probe_fingerprint, public_probe_selector = _selector_api()

    assert valid_hardware_probe_id(LEGACY_RAW)
    assert probe_fingerprint(LEGACY_RAW) == LEGACY_FINGERPRINT
    assert public_probe_selector(LEGACY_RAW) == LEGACY_SELECTOR
    assert public_probe_selector(LEGACY_RAW) != LEGACY_RAW


@pytest.mark.parametrize(
    ("hardware_id", "fingerprint", "selector"),
    [
        (ATK_RAW, ATK_FINGERPRINT, ATK_SELECTOR),
        (PUNCTUATION_RAW, PUNCTUATION_FINGERPRINT, f"pyocd:{PUNCTUATION_FINGERPRINT}"),
        (UNICODE_RAW, UNICODE_FINGERPRINT, f"pyocd:{UNICODE_FINGERPRINT}"),
        ("p" * 129, None, None),
    ],
)
def test_printable_opaque_hardware_ids_are_admitted_and_mapped(
    hardware_id: str, fingerprint: str | None, selector: str | None
) -> None:
    valid_hardware_probe_id, probe_fingerprint, public_probe_selector = _selector_api()

    assert valid_hardware_probe_id(hardware_id)
    if fingerprint is not None:
        assert probe_fingerprint(hardware_id) == fingerprint
        assert public_probe_selector(hardware_id) == selector
    else:
        assert len(probe_fingerprint(hardware_id)) == 64
        assert public_probe_selector(hardware_id).startswith("pyocd:")
        assert public_probe_selector(hardware_id) != hardware_id


def test_hardware_id_utf8_limit_is_measured_in_encoded_bytes():
    valid_hardware_probe_id, probe_fingerprint, public_probe_selector = _selector_api()
    accepted = "Ω" * 256
    rejected = "Ω" * 257

    assert len(accepted.encode("utf-8")) == 512
    assert len(rejected.encode("utf-8")) == 514
    assert valid_hardware_probe_id(accepted)
    assert len(probe_fingerprint(accepted)) == 64
    assert public_probe_selector(accepted).startswith("pyocd:")
    assert not valid_hardware_probe_id(rejected)


@pytest.mark.parametrize(
    "hardware_id",
    [
        None,
        123,
        "",
        "a" * 513,
        "contains\x00nul",
        "contains\nnewline",
        "contains\ttab",
        "contains\x1bescape",
        "contains\u202ebidi",
        "\ud800",
    ],
)
def test_invalid_or_control_hardware_ids_fail_closed(hardware_id: object) -> None:
    valid_hardware_probe_id, _probe_fingerprint, _public_probe_selector = _selector_api()

    assert not valid_hardware_probe_id(hardware_id)
