"""Public ``--flash-regions`` CLI diagnostics (POST134 specification section B).

The accepted schema is unchanged: a JSON array of 1..32 objects whose only
fields are integer ``start`` and ``length``.  These regressions pin the
*actionable* refusal contract: exit code 2, the historical
``stm32-toolkit: invalid arguments`` line, one extra line naming a closed reason
plus a bounded item index, and no echo of any caller-supplied value.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import stm32_toolkit.cli as cli
from stm32_toolkit.result import OperationResult

BASE = 0x0800_0000
SHA = "a" * 64
FIRST_LINE = "stm32-toolkit: invalid arguments"
REASON_PREFIX = "stm32-toolkit: --flash-regions: "
EXAMPLE = '[{"start":134217728,"length":65536}]'

JSON_REASON = "value must be valid JSON"
ARRAY_REASON = "value must be a JSON array of region objects"
COUNT_REASON = "value must contain 1 to 32 region objects"
ITEM_REASON = "must be a JSON object"
DUPLICATE_REASON = "contains a duplicate field"
FIELDS_REASON = "requires start and length"
KEYS_REASON = "must not contain fields other than start and length"
START_TYPE_REASON = (
    "start must be an integer; booleans, strings, and fractional numbers"
    " are not integers"
)
LENGTH_TYPE_REASON = (
    "length must be an integer; booleans, strings, and fractional numbers"
    " are not integers"
)

# Any of these appearing on stderr means a caller value was echoed.
LEAK_MARKERS = (
    "SECRET",
    "\x1b",
    "\x00",
    "FLASH",
    "origin",
    "0x08000000",
    "134217728",
    "not-json",
    "NaN",
)


def _argv(project: Path, data_root: Path, regions_value: str) -> list[str]:
    return [
        "firmware",
        "import",
        "--project-root",
        str(project),
        "--data-root",
        str(data_root),
        "--session-id",
        "session-a",
        "--firmware-path",
        "fw.bin",
        "--expected-sha256",
        SHA,
        "--format",
        "bin",
        "--target",
        "stm32f407vg",
        "--flash-regions",
        regions_value,
        "--base-address",
        str(BASE),
        "--dry-run",
        "--json",
    ]


def _too_many_regions() -> str:
    return json.dumps([{"start": BASE, "length": 16} for _ in range(33)])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "fw.bin").write_bytes(b"flash-regions-parser")
    return root


@pytest.fixture
def forbidden_workflow(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Fail loudly if any import/backend workflow runs after a parse refusal."""
    calls: list[object] = []

    def forbidden(request: object) -> OperationResult[object]:
        calls.append(request)
        raise AssertionError("firmware import workflow must not run")

    def forbidden_dispatch(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        raise AssertionError("dispatch must not run for a parse refusal")

    monkeypatch.setattr(cli, "firmware_import_workflow", forbidden)
    # No dispatch of any kind (import, backend, or hardware) may follow a
    # grammar refusal.
    monkeypatch.setattr(cli, "_operation_result", forbidden_dispatch)
    monkeypatch.setattr(cli, "_hardware_operation_result", forbidden_dispatch)
    return calls


def _refuse(
    capsys: pytest.CaptureFixture[str],
    project: Path,
    tmp_path: Path,
    value: str,
) -> str:
    data_root = tmp_path / "data"
    assert cli.main(_argv(project, data_root, value)) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert not data_root.exists(), "no workflow state may be created"
    return captured.err


REFUSALS = (
    # JSON grammar.
    ("not-json", JSON_REASON),
    ('[{"start":1,"length":2,"x":"\x1b[31mSECRET"}]', JSON_REASON),
    ('[{"start":NaN,"length":16}]', JSON_REASON),
    # Collection shape.
    ('{"start":134217728,"length":65536}', ARRAY_REASON),
    ('"region"', ARRAY_REASON),
    ("[]", COUNT_REASON),
    (_too_many_regions(), COUNT_REASON),
    # Item shape.
    ("[null]", f"region 1 {ITEM_REASON}"),
    ('[{"start":1,"length":2},[]]', f"region 2 {ITEM_REASON}"),
    ('[{"start":1,"length":2},"region"]', f"region 2 {ITEM_REASON}"),
    # Duplicate fields.
    ('[{"start":1,"start":2,"length":3}]', f"region 1 {DUPLICATE_REASON}"),
    (
        '[{"start":1,"length":2,"token":"a","token":"b"}]',
        f"region 1 {DUPLICATE_REASON}",
    ),
    # Missing required fields.
    ("[{}]", f"region 1 {FIELDS_REASON}"),
    ('[{"length":16}]', "region 1 requires start"),
    ('[{"start":1}]', "region 1 requires length"),
    # The user-reported shape: SVD/pyocd-style name/origin, not start/length.
    (
        '[{"name":"FLASH","origin":134217728,"length":65536}]',
        f"region 1 {KEYS_REASON}",
    ),
    (
        '[{"start":1,"length":2,"x":"\\u0000\\u001b[31mSECRET"}]',
        f"region 1 {KEYS_REASON}",
    ),
    # Field types; bool is not an int.
    ('[{"start":true,"length":16}]', f"region 1 {START_TYPE_REASON}"),
    ('[{"start":1,"length":false}]', f"region 1 {LENGTH_TYPE_REASON}"),
    ('[{"start":1.5,"length":16}]', f"region 1 {START_TYPE_REASON}"),
    ('[{"start":"0x08000000","length":16}]', f"region 1 {START_TYPE_REASON}"),
    # The index identifies the offending item, counted from 1.
    (
        '[{"start":1,"length":16},{"start":null,"length":2}]',
        f"region 2 {START_TYPE_REASON}",
    ),
)


@pytest.mark.parametrize(("value", "reason"), REFUSALS)
def test_public_cli_refuses_with_one_bounded_reason_line(
    value: str,
    reason: str,
    project: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    forbidden_workflow: list[object],
) -> None:
    error = _refuse(capsys, project, tmp_path, value)

    lines = error.splitlines()
    assert lines[0] == FIRST_LINE
    assert len(lines) == 2, error
    assert lines[1] == f"{REASON_PREFIX}{reason}"
    for leaked in LEAK_MARKERS:
        assert leaked not in error
    assert forbidden_workflow == []


@pytest.mark.parametrize(
    "value",
    (
        "not-json",
        '{"start":134217728,"length":65536}',
        "[]",
        _too_many_regions(),
    ),
)
def test_collection_level_reasons_carry_no_item_index(
    value: str, project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    error = _refuse(capsys, project, tmp_path, value)
    # Collection-level refusals never invent an item position.
    assert not any(f"region {index}" in error for index in range(0, 34))


@pytest.mark.parametrize(
    "value",
    (
        EXAMPLE,
        '[{"start":134217728,"length":65536},{"start":134283264,"length":4096}]',
        json.dumps(
            [{"start": BASE + 16 * index, "length": 16} for index in range(32)]
        ),
        '[{"start":0,"length":0}]',
        '[{"start":-1,"length":-1}]',
    ),
)
def test_valid_schema_parses_and_reaches_the_import_workflow(
    value: str,
    project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}

    def accepted(request: object) -> OperationResult[object]:
        captured["request"] = request
        return OperationResult.success("stm32-firmware-import", {"routed": True})

    monkeypatch.setattr(cli, "firmware_import_workflow", accepted)

    assert cli.main(_argv(project, tmp_path / "data", value)) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["data"] == {"routed": True}
    assert captured["request"] is not None

    parsed = cli._build_parser().parse_args(_argv(project, tmp_path / "data", value))
    expected = tuple(
        (item["start"], item["length"])
        for item in json.loads(value, parse_constant=cli._reject_json_constant)
    )
    # Out-of-range values are still accepted here: the schema is exact but
    # range/security validation stays in its existing layer.
    assert parsed.flash_regions == expected
    assert all(
        type(start) is int and type(length) is int
        for start, length in parsed.flash_regions
    )


def test_flash_regions_help_documents_schema_and_example(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A wide terminal keeps argparse from wrapping inside the example token.
    monkeypatch.setenv("COLUMNS", "200")
    assert cli.main(["firmware", "import", "--help"]) == 0
    help_text = capsys.readouterr().out
    collapsed = "".join(help_text.split())

    assert "--flash-regions" in collapsed
    assert '"start"and"length"' in collapsed
    assert "1..32" in collapsed
    # One concrete example: the exact accepted shape with real byte values.
    assert EXAMPLE in collapsed
    assert "134217728" in help_text
    assert "65536" in help_text


def _sanitized_argv(regions_value: str, extra: str) -> list[str]:
    """Import argv with one deliberately invalid unrelated argument."""
    return [
        "firmware",
        "import",
        "--project-root",
        "C:/project",
        "--data-root",
        "C:/data",
        "--session-id",
        "session-a",
        "--firmware-path",
        "fw.bin",
        "--expected-sha256",
        SHA,
        "--format",
        extra,
        "--target",
        "stm32f407vg",
        "--flash-regions",
        regions_value,
        "--dry-run",
        "--json",
    ]


@pytest.mark.parametrize(
    "argv",
    (
        # An unrelated choice failure keeps argparse's sanitized message only.
        _sanitized_argv(EXAMPLE, "SECRET-FORMAT"),
        # An unrecognized option name must not be echoed either.
        [
            *_sanitized_argv(EXAMPLE, "bin")[:-1],
            "--SECRET-OPTION",
            "--json",
        ],
    ),
)
def test_unrelated_argument_failures_remain_sanitized(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(argv) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"{FIRST_LINE}\n"
