"""Synthetic tests for the explicit reviewed comment-only replacement mode.

These tests use only temporary synthetic projects.  They never touch the
read-only robot project and they do not claim a complete migration, a buildable
project, ARMCC equivalence, or hardware acceptance.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HELPER_PATH = (
    REPO_ROOT
    / "skills"
    / "normalize-source-comments"
    / "scripts"
    / "normalize_comments.py"
)

HELPER_MODULE_NAME = "normalize_source_comments_replacement_under_test"


def _load_helper():
    spec = importlib.util.spec_from_file_location(HELPER_MODULE_NAME, HELPER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[HELPER_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


nc = _load_helper()

REPLACE = "?"


def _write(root: Path, relative: str, data: bytes) -> Path:
    target = root.joinpath(*relative.split("/"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def _read(root: Path, relative: str) -> bytes:
    return root.joinpath(*relative.split("/")).read_bytes()


def _preview(
    project: Path,
    preview_dir: Path,
    selections: list[str],
    replace_value: str | None = None,
) -> dict:
    return nc.preview_plan(
        str(project), str(preview_dir), selections, replace_value
    )


def _copy(
    project: Path,
    preview_dir: Path,
    plan_id: str,
    output: Path,
    confirmed: list[str] | None = None,
) -> dict:
    return nc.copy_plan(
        str(project),
        str(preview_dir / "plan.json"),
        plan_id,
        str(output),
        confirmed_files=confirmed,
    )


def _codes(file_entry: dict, severity: str | None = None) -> list[str]:
    return [
        finding["code"]
        for finding in file_entry["findings"]
        if severity is None or finding["severity"] == severity
    ]


def _plan_file(preview_dir: Path, relative: str) -> dict:
    plan = json.loads((preview_dir / "plan.json").read_text(encoding="utf-8"))
    return next(entry for entry in plan["files"] if entry["path"] == relative)


def _invalid_spans(data: bytes, codec: str) -> list[tuple[int, int]]:
    """Report the invalid byte spans exactly as a strict whole-body decode sees them."""

    spans: list[tuple[int, int]] = []
    offset = 0
    while offset < len(data):
        try:
            data[offset:].decode(codec)
        except UnicodeDecodeError as error:
            # A defensive advance keeps this oracle from looping if a codec
            # ever reports a zero-width error span.
            end = max(error.end, error.start + 1)
            spans.append((offset + error.start, offset + end))
            offset += end
            continue
        break
    return spans


def _replace_spans(data: bytes, spans: list[tuple[int, int]]) -> bytes:
    output = bytearray()
    position = 0
    for start, end in spans:
        output.extend(data[position:start])
        output.extend(b"?")
        position = end
    output.extend(data[position:])
    return bytes(output)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    return root


def test_strict_default_blocks_and_replace_mode_binds_mode_and_records(
    tmp_path: Path, project: Path
):
    source = b"// ok \xf3\nint x;\n"
    spans = _invalid_spans(source, "utf-8")
    assert spans and all(
        byte >= 0x80 for start, end in spans for byte in source[start:end]
    )
    original = _write(project, "App/a.c", source)

    strict = _preview(project, tmp_path / "preview-strict", ["App/a.c=utf-8"])
    assert strict["status"] == "blocked"
    strict_entry = _plan_file(tmp_path / "preview-strict", "App/a.c")
    assert strict_entry["decodeMode"] == "strict"
    assert strict_entry["lossy"] is False
    assert strict_entry["replacementRecords"] == []
    decode = next(
        finding
        for finding in strict_entry["findings"]
        if finding["code"] == "DECODE_ERROR"
    )
    assert "--replace-invalid-with" in decode["message"]
    assert "comment" in decode["message"].lower()
    strict_plan = json.loads(
        (tmp_path / "preview-strict" / "plan.json").read_text("utf-8")
    )
    assert strict_plan["mode"] == "strict"
    assert strict_plan["replacementValue"] is None

    preview_dir = tmp_path / "preview-replace"
    result = _preview(project, preview_dir, ["App/a.c=utf-8"], REPLACE)
    assert result["status"] == "ready"
    assert result["mode"] == "replace"
    assert result["replacementValue"] == REPLACE
    assert result["lossyFiles"] == ["App/a.c"]
    assert result["planId"] != strict["planId"]
    entry = _plan_file(preview_dir, "App/a.c")
    assert entry["decodeMode"] == "recovery"
    assert entry["decodeRoundTrip"] is False
    assert entry["unitRoundTrip"] is True
    assert entry["invalidByteUnits"] == len(spans)
    assert entry["lossy"] is True
    assert entry["replacementCount"] == len(spans)
    first_start, first_end = spans[0]
    record = entry["replacementRecords"][0]
    assert record == {
        "path": "App/a.c",
        "byteOffset": first_start,
        "byteLength": first_end - first_start,
        "originalBytes": source[first_start:first_end].hex(),
        "line": 1,
        "column": first_start + 1,
        "reason": "invalid-byte-unit",
        "replacement": REPLACE,
    }
    assert entry["outsideCommentSha256"] == entry["outputOutsideCommentSha256"]
    assert entry["idempotent"] is True
    expected = _replace_spans(source, spans)
    assert entry["outputSha256"] == nc._sha256(expected)
    assert original.read_bytes() == source

    output = tmp_path / "out"
    with pytest.raises(nc.ToolError) as missing:
        _copy(project, preview_dir, result["planId"], output)
    assert missing.value.code == "CONFIRMATION_REQUIRED"
    assert not output.exists()

    copied = _copy(project, preview_dir, result["planId"], output, ["App/a.c"])
    assert copied["status"] == "ok"
    assert copied["mode"] == "replace"
    assert copied["confirmedFiles"] == ["App/a.c"]
    assert _read(output, "App/a.c") == expected
    assert original.read_bytes() == source
    manifest = json.loads((output / "manifest.json").read_text("utf-8"))
    assert manifest["mode"] == "replace"
    assert manifest["replacementValue"] == REPLACE
    assert manifest["confirmedFiles"] == ["App/a.c"]
    assert manifest["lossyFiles"] == ["App/a.c"]
    assert manifest["totalReplacementCount"] == len(spans)
    assert manifest["files"][0]["lossy"] is True
    assert manifest["originalsUnchanged"] is True
    assert manifest["outputsVerified"] is True
    assert "complete" not in manifest


@pytest.mark.parametrize("codec", ["gb2312", "gbk", "gb18030"])
def test_legacy_invalid_comment_byte_is_replaced_only_in_opted_in_mode(
    tmp_path: Path, project: Path, codec: str
):
    source = b"// \xff"
    spans = _invalid_spans(source, codec)
    assert spans and all(
        byte >= 0x80 for start, end in spans for byte in source[start:end]
    )
    _write(project, "App/a.c", source)
    strict = _preview(project, tmp_path / "preview-strict", [f"App/a.c={codec}"])
    assert strict["status"] == "blocked"
    preview_dir = tmp_path / "preview-replace"
    result = _preview(project, preview_dir, [f"App/a.c={codec}"], REPLACE)
    assert result["status"] == "ready"
    entry = _plan_file(preview_dir, "App/a.c")
    assert entry["decodeMode"] == "recovery"
    assert entry["invalidByteUnits"] == len(spans)
    expected = _replace_spans(source, spans)
    assert expected == b"// ?"
    assert entry["outputSha256"] == nc._sha256(expected)
    assert all(
        record["reason"] == "invalid-byte-unit"
        for record in entry["replacementRecords"]
    )


def test_cp1252_undefined_byte_in_comment_is_replaced_with_review(
    tmp_path: Path, project: Path
):
    source = b"/* caf\xe9 \x81 */\nint x;\n"
    spans = _invalid_spans(source, "cp1252")
    assert spans
    _write(project, "App/cp.c", source)
    strict = _preview(project, tmp_path / "preview-strict", ["App/cp.c=cp1252"])
    assert strict["status"] == "blocked"
    preview_dir = tmp_path / "preview-replace"
    result = _preview(project, preview_dir, ["App/cp.c=cp1252"], REPLACE)
    assert result["status"] == "ready"
    entry = _plan_file(preview_dir, "App/cp.c")
    expected = bytearray()
    position = 0
    for start, end in spans:
        expected.extend(source[position:start])
        expected.extend(b"?")
        position = end
    expected.extend(source[position:])
    # The valid cp1252 character still converts to its UTF-8 bytes.
    expected = bytes(expected).replace(b"\xe9", "é".encode("utf-8"))
    assert entry["outputSha256"] == nc._sha256(expected)
    assert entry["changedUnits"] == 2


def test_disallowed_code_points_in_comment_are_replaced_with_reasons(
    tmp_path: Path, project: Path
):
    source = (
        "/*  ﷐ \u0081 � 中 */\nint x;\n"
    ).encode("utf-8")
    _write(project, "App/points.c", source)
    strict = _preview(project, tmp_path / "preview-strict", ["App/points.c=utf-8"])
    assert strict["status"] == "ready"
    strict_entry = _plan_file(tmp_path / "preview-strict", "App/points.c")
    assert strict_entry["changedUnits"] == 0
    assert strict_entry["outputSha256"] == strict_entry["sourceSha256"]
    for code in (
        "PRIVATE_USE_CODE_POINT",
        "C1_CONTROL_CODE_POINT",
        "REPLACEMENT_CODE_POINT",
        "NONCHARACTER_CODE_POINT",
    ):
        assert code in _codes(strict_entry)

    preview_dir = tmp_path / "preview-replace"
    result = _preview(project, preview_dir, ["App/points.c=utf-8"], REPLACE)
    assert result["status"] == "ready"
    entry = _plan_file(preview_dir, "App/points.c")
    assert entry["decodeMode"] == "strict"
    assert entry["decodeRoundTrip"] is True
    assert entry["lossy"] is True
    assert entry["replacementCount"] == 4
    assert entry["changedUnits"] == 4
    assert [record["reason"] for record in entry["replacementRecords"]] == [
        "private-use-code-point",
        "noncharacter-code-point",
        "c1-control-code-point",
        "replacement-code-point",
    ]
    assert entry["outputSha256"] == nc._sha256(
        "/* ? ? ? ? 中 */\nint x;\n".encode("utf-8")
    )


def test_gb18030_private_use_comment_unit_is_replaced_but_outside_blocks(
    tmp_path: Path, project: Path
):
    pua_source = b"/* \xa3\x42 */\nint x;\n"
    _write(project, "App/pua.c", pua_source)
    strict = _preview(project, tmp_path / "preview-strict", ["App/pua.c=gb18030"])
    assert strict["status"] == "blocked"
    preview_dir = tmp_path / "preview-replace"
    result = _preview(project, preview_dir, ["App/pua.c=gb18030"], REPLACE)
    assert result["status"] == "ready"
    entry = _plan_file(preview_dir, "App/pua.c")
    assert entry["replacementCount"] == 1
    record = entry["replacementRecords"][0]
    assert record["reason"] == "private-use-code-point"
    assert record["originalBytes"] == "a342"
    assert record["byteLength"] == 2
    assert entry["outputSha256"] == nc._sha256(b"/* ? */\nint x;\n")

    code_source = b"int x = \xa3\x42;\n"
    _write(project, "App/code.c", code_source)
    blocked = _preview(
        project, tmp_path / "preview-code", ["App/code.c=gb18030"], REPLACE
    )
    assert blocked["status"] == "blocked"
    code_entry = _plan_file(tmp_path / "preview-code", "App/code.c")
    assert "NON_COMMENT_NON_ASCII" in _codes(code_entry, "blocker")
    assert code_entry["outputSha256"] is None


def test_invalid_bytes_outside_comments_strings_chars_and_headers_block(
    tmp_path: Path, project: Path
):
    sources = {
        "App/code.c": b"int x = \xf3\xf4;\n",
        "App/string.c": b'char *s = "\xf3\xf4";\n',
        "App/char.c": b"char c = '\xf3\xf4';\n",
        "App/header.h": b"#include <\xf3\xf4.h>\n",
    }
    selections = []
    for relative, source in sources.items():
        _write(project, relative, source)
        selections.append(f"{relative}=utf-8")
    preview_dir = tmp_path / "preview"
    result = _preview(project, preview_dir, selections, REPLACE)
    assert result["status"] == "blocked"
    for relative in sources:
        entry = _plan_file(preview_dir, relative)
        assert entry["status"] == "blocked", relative
        assert entry["outputSha256"] is None, relative
        assert "NON_COMMENT_NON_ASCII" in _codes(entry, "blocker"), relative
        assert entry["replacementRecords"] == [], relative


def test_error_span_that_would_consume_ascii_is_blocked():
    with pytest.raises(nc._DecodeFailure) as crossing:
        nc._require_non_ascii_span(b"\xd6 ", 0, [0])
    assert crossing.value.code == "INVALID_SPAN_ASCII_UNSUPPORTED"
    assert crossing.value.message
    with pytest.raises(nc._DecodeFailure) as newline_crossing:
        nc._require_non_ascii_span(b"\xd6\n", 0, [0])
    assert newline_crossing.value.code == "INVALID_SPAN_ASCII_UNSUPPORTED"
    # A wholly non-ASCII span is accepted as an opaque replacement unit.
    nc._require_non_ascii_span(b"\xd6\xd7", 0, [0])
    with pytest.raises(nc._DecodeFailure):
        nc._require_non_ascii_span(b"", 0, [0])


def _ascii_crossing_gbk_span() -> tuple[bytes, int, int] | None:
    for candidate in (
        b"/* \xd6 \n*/\n",
        b"/* \xd6\n*/\n",
        b"/* \xd6\x7f */\n",
        b"/* \x81\x30\x81A */\n",
        b"/* \x81 \n*/\n",
    ):
        try:
            candidate.decode("gbk")
        except UnicodeDecodeError as error:
            span = candidate[error.start : error.end]
            if any(byte < 0x80 for byte in span):
                return candidate, error.start, error.end
    return None


def test_interpreter_ascii_consuming_span_is_blocked_end_to_end(
    tmp_path: Path, project: Path
):
    candidate = _ascii_crossing_gbk_span()
    if candidate is None:
        pytest.skip(
            "platform-only: this interpreter reports no ASCII-containing gbk "
            "error span; the guard is also covered directly above. Owner: "
            "coordinator; later phase: platform verification on another CPython."
        )
    source, start, end = candidate
    _write(project, "App/boundary.c", source)
    preview_dir = tmp_path / "preview"
    result = _preview(project, preview_dir, ["App/boundary.c=gbk"], REPLACE)
    assert result["status"] == "blocked"
    entry = _plan_file(preview_dir, "App/boundary.c")
    blockers = _codes(entry, "blocker")
    assert "INVALID_SPAN_ASCII_UNSUPPORTED" in blockers
    finding = next(
        finding
        for finding in entry["findings"]
        if finding["code"] == "INVALID_SPAN_ASCII_UNSUPPORTED"
    )
    assert finding["byteOffset"] == start
    assert finding["originalBytes"] == source[start:end].hex()
    assert entry["outputSha256"] is None


def test_preservation_of_bom_crlf_final_newline_and_valid_text(
    tmp_path: Path, project: Path
):
    source = (
        b"\xef\xbb\xbf// \xf3 \xe4\xb8\xad\r\nint x = 1;\r\nint y = 2;"
    )
    spans = _invalid_spans(source, "utf-8")
    assert spans
    _write(project, "App/preserve.c", source)
    preview_dir = tmp_path / "preview"
    result = _preview(project, preview_dir, ["App/preserve.c=utf-8"], REPLACE)
    assert result["status"] == "ready"
    entry = _plan_file(preview_dir, "App/preserve.c")
    assert entry["bom"] is True
    assert entry["newline"] == {
        "crlf": 2,
        "lf": 0,
        "cr": 0,
        "finalNewline": False,
        "finalSequence": "none",
    }
    expected = _replace_spans(source, spans)
    assert entry["outputSha256"] == nc._sha256(expected)
    assert expected.startswith(b"\xef\xbb\xbf// ? \xe4\xb8\xad\r\n")
    assert expected.endswith(b"int y = 2;")
    assert entry["outsideCommentSha256"] == entry["outputOutsideCommentSha256"]


def test_replacement_created_trigraph_blocks(tmp_path: Path, project: Path):
    source = b"/* ??\xf3/ x */\nint x;\n"
    spans = _invalid_spans(source, "utf-8")
    assert spans
    _write(project, "App/hazard.c", source)
    preview_dir = tmp_path / "preview"
    result = _preview(project, preview_dir, ["App/hazard.c=utf-8"], REPLACE)
    entry = _plan_file(preview_dir, "App/hazard.c")
    blockers = _codes(entry, "blocker")
    if all(byte >= 0x80 for start, end in spans for byte in source[start:end]):
        assert "REPLACEMENT_TRIGRAPH_HAZARD" in blockers
        assert entry["replacementRecords"][0]["reason"] == "invalid-byte-unit"
    else:
        assert "INVALID_SPAN_ASCII_UNSUPPORTED" in blockers
    assert result["status"] == "blocked"
    assert entry["outputSha256"] is None


def test_incomplete_constructs_still_block_in_replace_mode(
    tmp_path: Path, project: Path
):
    _write(project, "App/block.c", b"/* \xf3 unterminated\nint x;\n")
    _write(project, "App/raw.cpp", b'const char *s = R"(/* x */)";\n')
    _write(project, "App/hspace.c", b"// a \\ \nint x;\n")
    _write(project, "App/trigraph.c", b"// ??/\nint x;\n")
    preview_dir = tmp_path / "preview"
    result = _preview(
        project,
        preview_dir,
        [
            "App/block.c=utf-8",
            "App/raw.cpp=utf-8",
            "App/hspace.c=utf-8",
            "App/trigraph.c=utf-8",
        ],
        REPLACE,
    )
    assert result["status"] == "blocked"
    expected_codes = {
        "App/block.c": "UNTERMINATED_BLOCK_COMMENT",
        "App/raw.cpp": "RAW_STRING_UNSUPPORTED",
        "App/hspace.c": "BACKSLASH_HSPACE_NEWLINE_UNSUPPORTED",
        "App/trigraph.c": "TRIGRAPH_BACKSLASH_UNSUPPORTED",
    }
    for relative, code in expected_codes.items():
        entry = _plan_file(preview_dir, relative)
        assert code in _codes(entry, "blocker"), relative
        assert entry["outputSha256"] is None
        assert result["status"] == "blocked"


def test_confirmation_rules_reject_missing_duplicate_unknown_and_non_lossy(
    tmp_path: Path, project: Path
):
    _write(project, "App/lossy.c", b"// \xf3\nint a;\n")
    _write(project, "App/clean.c", b"// plain\nint b;\n")
    preview_dir = tmp_path / "preview"
    result = _preview(
        project, preview_dir, ["App/lossy.c=utf-8", "App/clean.c=utf-8"], REPLACE
    )
    assert result["status"] == "ready"
    assert result["lossyFiles"] == ["App/lossy.c"]
    plan_id = result["planId"]

    cases = [
        ([], "CONFIRMATION_REQUIRED"),
        (["App/lossy.c", "App/lossy.c"], "CONFIRMATION_DUPLICATE"),
        (["App/other.c"], "CONFIRMATION_UNKNOWN"),
        (["App/clean.c"], "CONFIRMATION_NOT_LOSSY"),
        (["App/lossy.c", "App/clean.c"], "CONFIRMATION_NOT_LOSSY"),
        (["../escape.c"], "CONFIRMATION_INVALID"),
    ]
    for index, (confirmed, code) in enumerate(cases):
        output = tmp_path / f"out-{index}"
        with pytest.raises(nc.ToolError) as error:
            _copy(project, preview_dir, plan_id, output, confirmed)
        assert error.value.code == code, (confirmed, error.value.code)
        assert not output.exists(), confirmed

    output = tmp_path / "out-ok"
    copied = _copy(project, preview_dir, plan_id, output, ["App/lossy.c"])
    assert copied["status"] == "ok"
    assert copied["confirmedFiles"] == ["App/lossy.c"]
    assert _read(output, "App/lossy.c") == b"// ?\nint a;\n"
    assert _read(output, "App/clean.c") == b"// plain\nint b;\n"

    # A strict plan requires no new confirmation and rejects stray ones.
    strict_file = _write(project, "App/strict.c", b"// \xd6\xd0\nint c;\n")
    strict_dir = tmp_path / "preview-strict"
    strict = _preview(project, strict_dir, ["App/strict.c=gbk"])
    assert strict["status"] == "ready"
    strict_output = tmp_path / "out-strict"
    with pytest.raises(nc.ToolError) as unexpected:
        _copy(project, strict_dir, strict["planId"], strict_output, ["App/strict.c"])
    assert unexpected.value.code == "CONFIRMATION_INVALID"
    assert not strict_output.exists()
    copied_strict = _copy(project, strict_dir, strict["planId"], strict_output)
    assert copied_strict["status"] == "ok"
    assert copied_strict["confirmedFiles"] == []
    assert strict_file.read_bytes() == b"// \xd6\xd0\nint c;\n"


def test_stale_source_and_tampered_replacement_plan_fail(
    tmp_path: Path, project: Path
):
    source = b"// \xf3\nint a;\n"
    _write(project, "App/a.c", source)
    preview_dir = tmp_path / "preview"
    result = _preview(project, preview_dir, ["App/a.c=utf-8"], REPLACE)
    assert result["status"] == "ready"

    _write(project, "App/a.c", source + b"// changed\n")
    with pytest.raises(nc.ToolError) as stale:
        _copy(project, preview_dir, result["planId"], tmp_path / "out-stale", ["App/a.c"])
    assert stale.value.code == "INPUT_CHANGED"
    assert not (tmp_path / "out-stale").exists()
    _write(project, "App/a.c", source)

    plan_path = preview_dir / "plan.json"
    plan = json.loads(plan_path.read_text("utf-8"))
    variant = json.loads(json.dumps(plan))
    variant["files"][0]["replacementRecords"][0]["originalBytes"] = "aa"
    variant["planId"] = nc.compute_plan_id(variant)
    forged = tmp_path / "forged-record.json"
    forged.write_text(json.dumps(variant, ensure_ascii=False), "utf-8")
    with pytest.raises(nc.ToolError) as tampered:
        nc.copy_plan(
            str(project),
            str(forged),
            variant["planId"],
            str(tmp_path / "out-forged"),
            confirmed_files=["App/a.c"],
        )
    assert tampered.value.code == "PLAN_TAMPERED"
    assert not (tmp_path / "out-forged").exists()

    downgraded = json.loads(json.dumps(plan))
    downgraded["mode"] = "strict"
    downgraded["replacementValue"] = None
    entry = downgraded["files"][0]
    entry["lossy"] = False
    entry["replacementCount"] = 0
    entry["replacementRecords"] = []
    entry["decodeMode"] = "strict"
    entry["decodeRoundTrip"] = True
    entry["invalidByteUnits"] = 0
    downgraded["planId"] = nc.compute_plan_id(downgraded)
    downgraded_path = tmp_path / "downgraded.json"
    downgraded_path.write_text(json.dumps(downgraded, ensure_ascii=False), "utf-8")
    with pytest.raises(nc.ToolError) as rederived:
        nc.copy_plan(
            str(project),
            str(downgraded_path),
            downgraded["planId"],
            str(tmp_path / "out-downgraded"),
        )
    assert rederived.value.code == "PLAN_TAMPERED"
    assert not (tmp_path / "out-downgraded").exists()

    with pytest.raises(nc.ToolError) as wrong_id:
        _copy(project, preview_dir, "0" * 64, tmp_path / "out-id", ["App/a.c"])
    assert wrong_id.value.code == "PLAN_ID_MISMATCH"


def test_old_plan_schema_fails_with_repreview_guidance(
    tmp_path: Path, project: Path
):
    _write(project, "App/a.c", b"int a;\n")
    preview_dir = tmp_path / "preview"
    result = _preview(project, preview_dir, ["App/a.c=gbk"])
    plan = json.loads((preview_dir / "plan.json").read_text("utf-8"))
    assert result["status"] == "ready"

    legacy = json.loads(json.dumps(plan))
    legacy["schemaVersion"] = 1
    legacy.pop("mode")
    legacy.pop("replacementValue")
    legacy_path = tmp_path / "legacy.json"
    legacy_path.write_text(json.dumps(legacy, ensure_ascii=False), "utf-8")
    with pytest.raises(nc.ToolError) as unsupported:
        nc.copy_plan(str(project), str(legacy_path), "0" * 64, str(tmp_path / "out"))
    assert unsupported.value.code == "PLAN_UNSUPPORTED"
    assert "preview" in unsupported.value.message
    assert not (tmp_path / "out").exists()

    old_helper = json.loads(json.dumps(plan))
    old_helper["helperVersion"] = "1.0.0"
    old_helper["planId"] = nc.compute_plan_id(old_helper)
    old_path = tmp_path / "old-helper.json"
    old_path.write_text(json.dumps(old_helper, ensure_ascii=False), "utf-8")
    with pytest.raises(nc.ToolError) as helper:
        nc.copy_plan(str(project), str(old_path), "0" * 64, str(tmp_path / "out-2"))
    assert helper.value.code == "PLAN_UNSUPPORTED"
    assert "preview" in helper.value.message


def test_replacement_record_bound_blocks_instead_of_omitting(
    tmp_path: Path, project: Path, monkeypatch
):
    source = "/* � � � */\n".encode("utf-8")
    _write(project, "App/many.c", source)
    full_dir = tmp_path / "preview-full"
    full = _preview(project, full_dir, ["App/many.c=utf-8"], REPLACE)
    assert full["status"] == "ready"
    full_entry = _plan_file(full_dir, "App/many.c")
    assert full_entry["replacementCount"] == 3

    monkeypatch.setattr(nc, "MAX_REPLACEMENT_RECORDS", 2)
    bounded_dir = tmp_path / "preview-bounded"
    bounded = _preview(project, bounded_dir, ["App/many.c=utf-8"], REPLACE)
    assert bounded["status"] == "blocked"
    entry = _plan_file(bounded_dir, "App/many.c")
    assert "REPLACEMENT_BOUND_EXCEEDED" in _codes(entry, "blocker")
    assert entry["outputSha256"] is None
    assert len(entry["replacementRecords"]) == 2
    with pytest.raises(nc.ToolError) as blocked_copy:
        _copy(project, bounded_dir, bounded["planId"], tmp_path / "out", ["App/many.c"])
    assert blocked_copy.value.code == "PLAN_BLOCKED"
    assert not (tmp_path / "out").exists()


def test_replacement_copy_containment_and_incomplete_marker(
    tmp_path: Path, project: Path, monkeypatch
):
    _write(project, "App/a.c", b"// \xf3\nint a;\n")
    preview_dir = tmp_path / "preview"
    result = _preview(project, preview_dir, ["App/a.c=utf-8"], REPLACE)
    assert result["status"] == "ready"

    with pytest.raises(nc.ToolError) as inside:
        _copy(project, preview_dir, result["planId"], project / "out", ["App/a.c"])
    assert inside.value.code == "OUTPUT_CONTAINMENT"
    assert not (project / "out").exists()

    original_write = nc._write_output_file
    calls = {"count": 0}

    def flaky(path: Path, data: bytes) -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("simulated replacement copy failure")
        original_write(path, data)

    monkeypatch.setattr(nc, "_write_output_file", flaky)
    output = tmp_path / "out-fail"
    with pytest.raises(nc.ToolError) as failure:
        _copy(project, preview_dir, result["planId"], output, ["App/a.c"])
    assert failure.value.code == "IO_FAILURE"
    assert not (output / "manifest.json").exists()
    marker = json.loads((output / "INCOMPLETE.json").read_text("utf-8"))
    assert marker["status"] == "incomplete"
    assert marker["planId"] == result["planId"]
    assert marker["filesWritten"] == []
    assert _read(project, "App/a.c") == b"// \xf3\nint a;\n"


def test_cli_replacement_preview_copy_and_option_validation(
    tmp_path: Path, project: Path
):
    source = b"// \xf3\nint a;\n"
    _write(project, "App/a.c", source)
    preview_dir = tmp_path / "preview"
    preview = subprocess.run(
        [
            sys.executable,
            str(HELPER_PATH),
            "preview",
            "--project-root",
            str(project),
            "--preview-dir",
            str(preview_dir),
            "--file",
            "App/a.c=utf-8",
            "--replace-invalid-with",
            REPLACE,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert preview.returncode == 0, preview.stderr
    payload = json.loads(preview.stdout)
    assert payload["mode"] == "replace"
    assert payload["lossyFiles"] == ["App/a.c"]
    plan_id = payload["planId"]

    missing_output = tmp_path / "out-missing"
    missing = subprocess.run(
        [
            sys.executable,
            str(HELPER_PATH),
            "copy",
            "--project-root",
            str(project),
            "--plan",
            str(preview_dir / "plan.json"),
            "--plan-id",
            plan_id,
            "--output-dir",
            str(missing_output),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert missing.returncode == 2
    assert json.loads(missing.stdout)["code"] == "CONFIRMATION_REQUIRED"
    assert not missing_output.exists()

    output = tmp_path / "out"
    copied = subprocess.run(
        [
            sys.executable,
            str(HELPER_PATH),
            "copy",
            "--project-root",
            str(project),
            "--plan",
            str(preview_dir / "plan.json"),
            "--plan-id",
            plan_id,
            "--output-dir",
            str(output),
            "--confirm-file",
            "App/a.c",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert copied.returncode == 0, copied.stderr
    assert json.loads(copied.stdout)["confirmedFiles"] == ["App/a.c"]
    assert _read(output, "App/a.c") == b"// ?\nint a;\n"
    assert _read(project, "App/a.c") == source

    bad_dir = tmp_path / "preview-bad"
    bad = subprocess.run(
        [
            sys.executable,
            str(HELPER_PATH),
            "preview",
            "--project-root",
            str(project),
            "--preview-dir",
            str(bad_dir),
            "--file",
            "App/a.c=utf-8",
            "--replace-invalid-with",
            "x",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert bad.returncode == 2
    assert json.loads(bad.stdout)["code"] == "REPLACEMENT_VALUE_UNSUPPORTED"
    assert not bad_dir.exists()


def test_replacement_preview_is_read_only_and_keeps_mixed_valid_text(
    tmp_path: Path, project: Path
):
    source = b"/* \xff \xd6\xd0 */\r\nint a;\r\n"
    original = _write(project, "App/mixed.c", source)
    spans = _invalid_spans(source, "gbk")
    assert len(spans) == 1
    preview_dir = tmp_path / "preview"
    result = _preview(project, preview_dir, ["App/mixed.c=gbk"], REPLACE)
    assert result["status"] == "ready"
    entry = _plan_file(preview_dir, "App/mixed.c")
    start, end = spans[0]
    assert source[start:end] == b"\xff"
    assert entry["replacementRecords"][0]["byteOffset"] == start
    assert entry["outputSha256"] == nc._sha256(
        source[:start] + b"?" + b"\xe4\xb8\xad */\r\nint a;\r\n"
    )
    assert entry["newline"] == {
        "crlf": 2,
        "lf": 0,
        "cr": 0,
        "finalNewline": True,
        "finalSequence": "CRLF",
    }
    assert original.read_bytes() == source
    # Preview alone never writes into the project or creates output copies.
    project_files = sorted(
        path.relative_to(project).as_posix()
        for path in project.rglob("*")
        if path.is_file()
    )
    assert project_files == ["App/mixed.c"]


@pytest.mark.parametrize(
    "source",
    [
        b"// \xa1\x5c\r\nint x;\r\n",
        b"// \xa1\x5c\nint x;\n",
        b"/* \xa1\x5c\r\n*/int x;\n",
        b"// \xa1\x5c",
    ],
)
def test_gb18030_pua_unit_ending_in_0x5c_at_line_end_stays_blocked(
    tmp_path: Path, project: Path, source: bytes
):
    # A1 5C is a *valid* two-byte GB18030 pair that decodes to the private-use
    # code point U+E4E2; it is not an opaque span.  The raw byte 0x5C at a
    # physical line end can splice the next line for a raw-byte lexer, so the
    # semantic ambiguity blocker must survive the replacement branch.
    character = b"\xa1\x5c".decode("gb18030")
    assert character == ""
    assert nc._replacement_reason(character) == "private-use-code-point"
    _write(project, "App/trail.c", source)

    strict_dir = tmp_path / "preview-strict"
    strict = _preview(project, strict_dir, ["App/trail.c=gb18030"])
    assert strict["status"] == "blocked"
    assert "DBCS_TRAIL_BACKSLASH_UNSUPPORTED" in _codes(
        _plan_file(strict_dir, "App/trail.c"), "blocker"
    )

    preview_dir = tmp_path / "preview-replace"
    result = _preview(project, preview_dir, ["App/trail.c=gb18030"], REPLACE)
    assert result["status"] == "blocked"
    entry = _plan_file(preview_dir, "App/trail.c")
    blockers = _codes(entry, "blocker")
    assert "DBCS_TRAIL_BACKSLASH_UNSUPPORTED" in blockers
    # Only the four replaceable classification blockers are suppressed; the
    # classification finding is gone while the semantic hazard stays.
    assert "PRIVATE_USE_CODE_POINT" not in _codes(entry)
    assert entry["outputSha256"] is None
    assert entry["idempotent"] is False

    output = tmp_path / "out"
    with pytest.raises(nc.ToolError) as blocked_copy:
        _copy(project, preview_dir, result["planId"], output, ["App/trail.c"])
    assert blocked_copy.value.code == "PLAN_BLOCKED"
    assert not output.exists()


def test_gb18030_pua_unit_mid_line_is_replaced(
    tmp_path: Path, project: Path
):
    source = b"// \xa1\x5cA\r\nint x;\r\n"
    _write(project, "App/mid.c", source)
    preview_dir = tmp_path / "preview"
    result = _preview(project, preview_dir, ["App/mid.c=gb18030"], REPLACE)
    assert result["status"] == "ready"
    entry = _plan_file(preview_dir, "App/mid.c")
    assert entry["replacementCount"] == 1
    record = entry["replacementRecords"][0]
    assert record["reason"] == "private-use-code-point"
    assert record["originalBytes"] == "a15c"
    assert record["byteLength"] == 2
    assert entry["outputSha256"] == nc._sha256(b"// ?A\r\nint x;\r\n")
    output = tmp_path / "out"
    _copy(project, preview_dir, result["planId"], output, ["App/mid.c"])
    assert _read(output, "App/mid.c") == b"// ?A\r\nint x;\r\n"
    assert _read(project, "App/mid.c") == source


def test_mixed_single_byte_review_warning_survives_replacement(
    tmp_path: Path, project: Path, monkeypatch
):
    # The DBCS/ASCII mixed artifact is a review warning, not one of the four
    # replaceable classes.  This focused branch test forces a mixed artifact to
    # be classified as replaceable so the "replaced=True" path must still emit
    # its review warning; real charsets may or may not produce such a pair.
    mixed_character = b"\x92s".decode("gbk")
    assert mixed_character == "抯"
    original_reason = nc._replacement_reason

    def classify(character: str) -> str | None:
        if character == mixed_character:
            return "private-use-code-point"
        return original_reason(character)

    monkeypatch.setattr(nc, "_replacement_reason", classify)
    source = b"/* ETHERNET\x92s DMA */\nint x;\n"
    _write(project, "App/mixed.c", source)
    preview_dir = tmp_path / "preview"
    result = _preview(project, preview_dir, ["App/mixed.c=gbk"], REPLACE)
    assert result["status"] == "ready"
    entry = _plan_file(preview_dir, "App/mixed.c")
    assert "MIXED_SINGLE_BYTE_ARTIFACT" in _codes(entry, "warning")
    assert entry["replacementCount"] == 1
    assert entry["replacementRecords"][0]["reason"] == "private-use-code-point"
    assert entry["outputSha256"] == nc._sha256(
        "/* ETHERNET? DMA */\nint x;\n".encode("utf-8")
    )


def test_decoded_limit_blocks_before_per_unit_mapping_allocation(
    tmp_path: Path, project: Path, monkeypatch
):
    import tracemalloc

    data = b"// " + b"a" * 2_000_000 + b"\n"
    monkeypatch.setattr(nc, "MAX_DECODED_CHARACTERS", 1000)
    _write(project, "App/big.c", data)
    preview_dir = tmp_path / "preview"
    tracemalloc.start()
    try:
        result = _preview(project, preview_dir, ["App/big.c=gbk"])
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert result["status"] == "blocked"
    entry = _plan_file(preview_dir, "App/big.c")
    decode = next(
        finding for finding in entry["findings"] if finding["code"] == "DECODE_ERROR"
    )
    assert "decoded character count" in decode["message"]
    assert "before building source mappings" in decode["message"]
    assert decode["byteOffset"] == 0
    # Two million per-unit offsets/opaque flags would need hundreds of
    # megabytes.  The accepted base rejected oversized decoded text before
    # that mapping allocation, and this slice must preserve that bound.
    assert peak < 64 * 1024 * 1024


def test_recovered_windows_enforce_cumulative_decoded_limit(
    tmp_path: Path, project: Path, monkeypatch
):
    window = nc._RECOVERY_FEED_BYTES
    data = b"// " + b"a" * (window + 5000) + b"\n"
    monkeypatch.setattr(nc, "MAX_DECODED_CHARACTERS", window)
    analysis = nc.analyze_bytes(
        data, "utf-8", "App/window.c", replace_value=REPLACE
    )
    assert analysis.status == "blocked"
    finding = next(
        finding for finding in analysis.findings if finding.code == "DECODE_ERROR"
    )
    assert "decoded character count" in finding.message
    assert finding.byte_offset == window


def test_recovered_carry_boundary_enforces_decoded_limit(
    tmp_path: Path, project: Path, monkeypatch
):
    window = nc._RECOVERY_FEED_BYTES
    data = b"a" * (window - 1) + "é".encode("utf-8") + b"\n"
    # The window ends inside the two-byte sequence, so the lead byte is carried
    # into the next window.  The cumulative bound must still fail at that carry
    # boundary instead of allocating mappings for it.
    monkeypatch.setattr(nc, "MAX_DECODED_CHARACTERS", window)
    analysis = nc.analyze_bytes(
        data, "utf-8", "App/carry.c", replace_value=REPLACE
    )
    assert analysis.status == "blocked"
    finding = next(
        finding for finding in analysis.findings if finding.code == "DECODE_ERROR"
    )
    assert "decoded character count" in finding.message
    assert finding.byte_offset == window - 1
    assert analysis.decode_mode == "strict"
    assert analysis.unit_round_trip is False
