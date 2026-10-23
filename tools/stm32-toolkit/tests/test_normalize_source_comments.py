"""Focused tests for the standalone normalize-source-comments helper.

These are synthetic tests.  They do not modify the read-only robot project and
they do not claim a complete migration or a buildable project.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import sys
import warnings
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
SKILL_PATH = REPO_ROOT / "skills" / "normalize-source-comments" / "SKILL.md"
ARM_GCC = Path(
    r"C:/ST/STM32CubeCLT_1.22.0/GNU-tools-for-STM32/bin/arm-none-eabi-gcc.exe"
)
BASE_PYTHON = Path(
    r"C:/Users/zhy76/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
)
SKILL_VALIDATOR = Path(
    r"C:/Users/zhy76/.codex/skills/.system/skill-creator/scripts/quick_validate.py"
)

HELPER_MODULE_NAME = "normalize_source_comments_under_test"


def _load_helper():
    spec = importlib.util.spec_from_file_location(HELPER_MODULE_NAME, HELPER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[HELPER_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


nc = _load_helper()


def _write(root: Path, relative: str, data: bytes) -> Path:
    target = root.joinpath(*relative.split("/"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def _read(root: Path, relative: str) -> bytes:
    return root.joinpath(*relative.split("/")).read_bytes()


def _preview(project: Path, preview_dir: Path, selections: list[str]) -> dict:
    return nc.preview_plan(str(project), str(preview_dir), selections)


def _copy(project: Path, preview_dir: Path, plan_id: str, output: Path) -> dict:
    return nc.copy_plan(
        str(project),
        str(preview_dir / "plan.json"),
        plan_id,
        str(output),
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


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    return root


def test_gb2312_comment_only_crlf_conversion_and_copy(tmp_path: Path, project: Path):
    source = b"int x = 1; // \xd6\xd0\xce\xc4\r\nint y = 2;\r\n"
    original = _write(project, "App/gb.c", source)
    preview_dir = tmp_path / "preview"

    result = _preview(project, preview_dir, ["App/gb.c=gb2312"])

    assert result["status"] == "ready"
    assert result["blockers"] == 0
    entry = _plan_file(preview_dir, "App/gb.c")
    assert entry["status"] == "ready"
    assert entry["charset"] == "gb2312"
    assert entry["newline"] == {
        "crlf": 2,
        "lf": 0,
        "cr": 0,
        "finalNewline": True,
        "finalSequence": "CRLF",
    }
    assert entry["bom"] is False
    assert entry["decodeRoundTrip"] is True
    assert entry["idempotent"] is True
    assert entry["outsideCommentSha256"] == entry["outputOutsideCommentSha256"]
    assert entry["outputSha256"] == nc._sha256(
        b"int x = 1; // \xe4\xb8\xad\xe6\x96\x87\r\nint y = 2;\r\n"
    )

    output = tmp_path / "out"
    copied = _copy(project, preview_dir, result["planId"], output)

    assert copied["status"] == "ok"
    assert copied["copyOnly"] is True
    assert copied["notAProject"] is True
    assert _read(output, "App/gb.c") == (
        b"int x = 1; // \xe4\xb8\xad\xe6\x96\x87\r\nint y = 2;\r\n"
    )
    assert original.read_bytes() == source
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert "complete" not in manifest
    assert manifest["originalsUnchanged"] is True
    assert manifest["outputsVerified"] is True
    assert manifest["files"][0]["sourceSha256"] == entry["sourceSha256"]


def test_gbk_only_character_requires_gbk_and_gb2312_fails(
    tmp_path: Path, project: Path
):
    source = ("/* \u4e02 */\nint x;\n").encode("gbk")
    _write(project, "App/only-gbk.c", source)

    blocked = _preview(project, tmp_path / "preview-gb2312", ["App/only-gbk.c=gb2312"])
    assert blocked["status"] == "blocked"
    entry = _plan_file(tmp_path / "preview-gb2312", "App/only-gbk.c")
    assert entry["status"] == "blocked"
    assert entry["outputSha256"] is None
    decode = [f for f in entry["findings"] if f["code"] == "DECODE_ERROR"]
    assert len(decode) == 1
    assert decode[0]["line"] == 1
    assert decode[0]["byteOffset"] is not None

    ready = _preview(project, tmp_path / "preview-gbk", ["App/only-gbk.c=gbk"])
    assert ready["status"] == "ready"
    converted = _plan_file(tmp_path / "preview-gbk", "App/only-gbk.c")
    assert converted["changedUnits"] == 1
    assert converted["outputSha256"] == nc._sha256(
        ("/* \u4e02 */\nint x;\n").encode("utf-8")
    )


def test_gb18030_four_byte_comment_and_private_use_block(
    tmp_path: Path, project: Path
):
    emoji_source = ("/* \U0001F600 */\nint x;\n").encode("gb18030")
    _write(project, "App/emoji.c", emoji_source)
    ready = _preview(project, tmp_path / "preview-emoji", ["App/emoji.c=gb18030"])
    assert ready["status"] == "ready"
    entry = _plan_file(tmp_path / "preview-emoji", "App/emoji.c")
    assert entry["outputSha256"] == nc._sha256(
        ("/* \U0001F600 */\nint x;\n").encode("utf-8")
    )

    pua_source = b"/* \xa3\x42 */\nint x;\n"
    _write(project, "App/pua.c", pua_source)
    blocked = _preview(project, tmp_path / "preview-pua", ["App/pua.c=gb18030"])
    assert blocked["status"] == "blocked"
    pua = _plan_file(tmp_path / "preview-pua", "App/pua.c")
    assert "PRIVATE_USE_CODE_POINT" in _codes(pua, "blocker")
    assert pua["outputSha256"] is None


def test_mixed_per_file_charsets_and_explicit_cp1252(
    tmp_path: Path, project: Path
):
    _write(project, "App/a.c", ("/* \u4e2d */\nint a;\n").encode("gbk"))
    _write(project, "App/b.h", ("/* \u4e2d */\nint b;\n").encode("gb2312"))
    _write(project, "App/c.cpp", b"/* caf\xe9 \x92 */\nint c;\n")
    _write(
        project,
        "App/d.c",
        ("/* \u4e2d */\nconst char *s = \"\u4e2d\";\n").encode("utf-8"),
    )
    preview_dir = tmp_path / "preview"
    result = _preview(
        project,
        preview_dir,
        [
            "App/a.c=gbk",
            "App/b.h=gb2312",
            "App/c.cpp=cp1252",
            "App/d.c=utf-8",
        ],
    )
    assert result["status"] == "ready"
    assert _plan_file(preview_dir, "App/a.c")["changedUnits"] == 1
    assert _plan_file(preview_dir, "App/b.h")["changedUnits"] == 1
    cp = _plan_file(preview_dir, "App/c.cpp")
    assert cp["changedUnits"] == 2
    assert cp["outputSha256"] == nc._sha256(
        b"/* caf\xc3\xa9 \xe2\x80\x99 */\nint c;\n"
    )
    d = _plan_file(preview_dir, "App/d.c")
    assert d["outputSha256"] == d["sourceSha256"]
    assert d["changedUnits"] == 0
    assert "NON_COMMENT_NON_ASCII" in _codes(d, "warning")
    output = tmp_path / "out"
    _copy(project, preview_dir, result["planId"], output)
    assert _read(output, "App/a.c") == ("/* \u4e2d */\nint a;\n").encode("utf-8")
    assert _read(output, "App/d.c") == _read(project, "App/d.c")


def test_utf8_bom_crlf_and_final_newline_are_preserved(tmp_path: Path, project: Path):
    source = b"\xef\xbb\xbf/* \xe4\xb8\xad\xe6\x96\x87 */\r\nint x;"
    _write(project, "App/bom.h", source)
    preview_dir = tmp_path / "preview"
    result = _preview(project, preview_dir, ["App/bom.h=utf-8"])
    assert result["status"] == "ready"
    entry = _plan_file(preview_dir, "App/bom.h")
    assert entry["bom"] is True
    assert entry["newline"]["crlf"] == 1
    assert entry["newline"]["finalNewline"] is False
    assert entry["newline"]["finalSequence"] == "none"
    assert entry["outputSha256"] == entry["sourceSha256"]
    assert entry["changedUnits"] == 0

    second = _preview(tmp_path / "project", tmp_path / "preview-second", ["App/bom.h=utf-8"])
    assert second["planId"] == result["planId"]


def test_comment_lookalikes_in_strings_and_characters_are_not_comments(
    tmp_path: Path, project: Path
):
    source = (
        'const char *s = "// not a comment";\n'
        "char c = '/';\n"
        'const char *t = "/* not a comment */";\n'
        "/* \u4e2d\u6587 */\n"
    ).encode("gbk")
    _write(project, "App/lookalike.c", source)
    preview_dir = tmp_path / "preview"
    result = _preview(project, preview_dir, ["App/lookalike.c=gbk"])
    assert result["status"] == "ready"
    entry = _plan_file(preview_dir, "App/lookalike.c")
    assert entry["changedUnits"] == 2
    output = tmp_path / "out"
    _copy(project, preview_dir, result["planId"], output)
    converted = _read(output, "App/lookalike.c")
    assert b'"// not a comment"' in converted
    assert b'"/* not a comment */"' in converted
    assert "\u4e2d\u6587".encode("utf-8") in converted
    assert _read(project, "App/lookalike.c").startswith(
        b'const char *s = "// not a comment";'
    )


def test_legacy_non_comment_text_blocks_with_locations(tmp_path: Path, project: Path):
    _write(project, "App/literal.c", ('const char *s = "\u4e2d";\n').encode("gbk"))
    _write(project, "App/identifier.c", ("int \u4e2d;\n").encode("gbk"))
    _write(project, "App/header.h", b'#include <\xd6\xd0.h>\n')
    _write(project, "App/quoted.h", b'#include "\xd6\xd0.h"\n')
    preview_dir = tmp_path / "preview"
    result = _preview(
        project,
        preview_dir,
        [
            "App/literal.c=gbk",
            "App/identifier.c=gbk",
            "App/header.h=gbk",
            "App/quoted.h=gbk",
        ],
    )
    assert result["status"] == "blocked"
    for relative in (
        "App/literal.c",
        "App/identifier.c",
        "App/header.h",
        "App/quoted.h",
    ):
        entry = _plan_file(preview_dir, relative)
        assert entry["status"] == "blocked"
        assert entry["outputSha256"] is None
        assert "NON_COMMENT_NON_ASCII" in _codes(entry, "blocker")
        assert any(
            finding["line"] is not None and finding["column"] is not None
            for finding in entry["findings"]
        )


def test_utf8_non_comment_text_is_unchanged_with_warning(tmp_path: Path, project: Path):
    source = ("const char *s = \"\u4e2d\u6587\";\n").encode("utf-8")
    _write(project, "App/utf8.c", source)
    result = _preview(project, tmp_path / "preview", ["App/utf8.c=utf-8"])
    assert result["status"] == "ready"
    entry = _plan_file(tmp_path / "preview", "App/utf8.c")
    assert entry["outputSha256"] == entry["sourceSha256"]
    assert entry["changedUnits"] == 0
    assert "NON_COMMENT_NON_ASCII" in _codes(entry, "warning")


def test_raw_cpp_strings_are_rejected_explicitly(tmp_path: Path, project: Path):
    _write(project, "App/raw.cpp", b'const char *s = R"(/* not a comment */)";\n')
    _write(project, "App/raw8.cpp", b'const char *s = u8R"(x)";\n')
    preview_dir = tmp_path / "preview"
    result = _preview(
        project,
        preview_dir,
        ["App/raw.cpp=utf-8", "App/raw8.cpp=utf-8"],
    )
    assert result["status"] == "blocked"
    for relative in ("App/raw.cpp", "App/raw8.cpp"):
        entry = _plan_file(preview_dir, relative)
        assert "RAW_STRING_UNSUPPORTED" in _codes(entry, "blocker")
        assert entry["outputSha256"] is None


def test_spliced_line_comments_and_split_delimiters(tmp_path: Path, project: Path):
    source = (
        b"// first \\\r\n\xd6\xd0\r\n"
        b"int a;\r\n"
        b"/\\\r\n* \xd6\xd0 */\r\n"
        b"int b;\r\n"
        b"/\\\r\n/ \xd6\xd0\r\n"
        b"int c;\r\n"
    )
    _write(project, "App/spliced.c", source)
    preview_dir = tmp_path / "preview"
    result = _preview(project, preview_dir, ["App/spliced.c=gbk"])
    assert result["status"] == "ready"
    entry = _plan_file(preview_dir, "App/spliced.c")
    assert entry["commentCount"] == 3
    assert entry["changedUnits"] == 3
    assert entry["outputSha256"] == nc._sha256(
        (
            "// first \\\r\n\u4e2d\r\n"
            "int a;\r\n"
            "/\\\r\n* \u4e2d */\r\n"
            "int b;\r\n"
            "/\\\r\n/ \u4e2d\r\n"
            "int c;\r\n"
        ).encode("utf-8")
    )
    output = tmp_path / "out"
    _copy(project, preview_dir, result["planId"], output)
    converted = _read(output, "App/spliced.c")
    assert b"int a;\r\n" in converted
    assert b"int b;\r\n" in converted
    assert b"int c;\r\n" in converted
    assert converted.count("\u4e2d".encode("utf-8")) == 3


def test_backslash_horizontal_whitespace_newline_is_blocked(
    tmp_path: Path, project: Path
):
    _write(project, "App/hspace.c", b"// comment \\ \r\nint x;\r\n")
    result = _preview(project, tmp_path / "preview", ["App/hspace.c=gbk"])
    assert result["status"] == "blocked"
    entry = _plan_file(tmp_path / "preview", "App/hspace.c")
    assert "BACKSLASH_HSPACE_NEWLINE_UNSUPPORTED" in _codes(entry, "blocker")


def test_unterminated_constructs_block(tmp_path: Path, project: Path):
    _write(project, "App/block.c", b"/* east\nint x;\n")
    _write(project, "App/string.c", b'const char *s = "east\nint x;\n')
    _write(project, "App/char.c", b"char c = 'e\nint x;\n")
    _write(project, "App/header.h", b"#include <east\nint x;\n")
    preview_dir = tmp_path / "preview"
    result = _preview(
        project,
        preview_dir,
        [
            "App/block.c=gbk",
            "App/string.c=gbk",
            "App/char.c=gbk",
            "App/header.h=gbk",
        ],
    )
    assert result["status"] == "blocked"
    assert "UNTERMINATED_BLOCK_COMMENT" in _codes(
        _plan_file(preview_dir, "App/block.c"), "blocker"
    )
    assert "UNTERMINATED_STRING" in _codes(
        _plan_file(preview_dir, "App/string.c"), "blocker"
    )
    assert "UNTERMINATED_CHAR" in _codes(
        _plan_file(preview_dir, "App/char.c"), "blocker"
    )
    assert "UNTERMINATED_HEADER_NAME" in _codes(
        _plan_file(preview_dir, "App/header.h"), "blocker"
    )


def test_trigraph_backslash_blocks_and_other_trigraphs_warn(
    tmp_path: Path, project: Path
):
    _write(project, "App/trigraph.c", b"/* ??( ??[ */\nint x;\n")
    warning = _preview(project, tmp_path / "preview-warn", ["App/trigraph.c=gbk"])
    assert warning["status"] == "ready"
    warn_entry = _plan_file(tmp_path / "preview-warn", "App/trigraph.c")
    assert "TRIGRAPH_SEQUENCE_REVIEW" in _codes(warn_entry, "warning")
    assert warn_entry["outputSha256"] == warn_entry["sourceSha256"]

    _write(project, "App/trigraph-slash.c", b"// ??/\nint x;\n")
    blocked = _preview(
        project, tmp_path / "preview-block", ["App/trigraph-slash.c=gbk"]
    )
    assert blocked["status"] == "blocked"
    slash_entry = _plan_file(tmp_path / "preview-block", "App/trigraph-slash.c")
    assert "TRIGRAPH_BACKSLASH_UNSUPPORTED" in _codes(slash_entry, "blocker")


def test_dbcs_trail_backslash_at_line_end_blocks_but_mid_line_is_safe(
    tmp_path: Path, project: Path
):
    character = "\u4e57"
    assert character.encode("gbk") == b"\x81\\"
    _write(project, "App/trail.c", b"// " + character.encode("gbk") + b"\r\nint x;\r\n")
    blocked = _preview(project, tmp_path / "preview-block", ["App/trail.c=gbk"])
    assert blocked["status"] == "blocked"
    blocked_entry = _plan_file(tmp_path / "preview-block", "App/trail.c")
    assert "DBCS_TRAIL_BACKSLASH_UNSUPPORTED" in _codes(blocked_entry, "blocker")

    _write(project, "App/mid.c", b"// " + character.encode("gbk") + b"A\r\nint y;\r\n")
    ready = _preview(project, tmp_path / "preview-ready", ["App/mid.c=gbk"])
    assert ready["status"] == "ready"
    mid_entry = _plan_file(tmp_path / "preview-ready", "App/mid.c")
    assert mid_entry["changedUnits"] == 1
    assert mid_entry["outputSha256"] == nc._sha256(
        "// \u4e57A\r\nint y;\r\n".encode("utf-8")
    )


def test_invalid_bytes_report_offset_and_line(tmp_path: Path, project: Path):
    source = b"// ok\n/* \xf3 */\n"
    _write(project, "App/invalid.c", source)
    result = _preview(project, tmp_path / "preview", ["App/invalid.c=gbk"])
    assert result["status"] == "blocked"
    entry = _plan_file(tmp_path / "preview", "App/invalid.c")
    finding = next(f for f in entry["findings"] if f["code"] == "DECODE_ERROR")
    assert finding["byteOffset"] == 9
    assert finding["line"] == 2
    assert finding["column"] == 4
    assert finding["originalBytes"] == "f3"
    assert entry["outputSha256"] is None


def test_mixed_single_byte_artifact_is_reported_not_guessed(
    tmp_path: Path, project: Path
):
    source = b"/* ETHERNET\x92s DMA */\nint x;\n"
    _write(project, "App/mixed.c", source)
    result = _preview(project, tmp_path / "preview", ["App/mixed.c=gbk"])
    assert result["status"] == "ready"
    entry = _plan_file(tmp_path / "preview", "App/mixed.c")
    warnings_ = [f for f in entry["findings"] if f["code"] == "MIXED_SINGLE_BYTE_ARTIFACT"]
    assert len(warnings_) == 1
    assert warnings_[0]["originalBytes"] == "9273"
    assert warnings_[0]["decodedText"] == "\u62af"
    assert entry["outputSha256"] == nc._sha256(
        "/* ETHERNET\u62af DMA */\nint x;\n".encode("utf-8")
    )


def test_cp1252_is_explicit_and_never_guessed(tmp_path: Path, project: Path):
    source = b"/* caf\xe9 \x92 */\nint x;\n"
    _write(project, "App/cp.c", source)
    result = _preview(project, tmp_path / "preview", ["App/cp.c=cp1252"])
    assert result["status"] == "ready"
    entry = _plan_file(tmp_path / "preview", "App/cp.c")
    assert entry["changedUnits"] == 2
    assert entry["outputSha256"] == nc._sha256(
        b"/* caf\xc3\xa9 \xe2\x80\x99 */\nint x;\n"
    )

    wrong = _preview(project, tmp_path / "preview-wrong", ["App/cp.c=gbk"])
    assert wrong["status"] == "blocked"
    wrong_entry = _plan_file(tmp_path / "preview-wrong", "App/cp.c")
    assert "DECODE_ERROR" in _codes(wrong_entry, "blocker")

def test_plan_fields_are_canonical_and_deterministic(tmp_path: Path, project: Path):
    _write(project, "App/a.c", ("/* \u4e2d */\nint a;\n").encode("gbk"))
    first = _preview(project, tmp_path / "preview-a", ["App/a.c=gbk"])
    second = _preview(project, tmp_path / "preview-b", ["App/a.c=gbk"])
    assert first["planId"] == second["planId"]
    assert (tmp_path / "preview-a" / "plan.json").read_bytes() == (
        tmp_path / "preview-b" / "plan.json"
    ).read_bytes()
    assert len(first["planId"]) == 64
    plan = json.loads((tmp_path / "preview-a" / "plan.json").read_text("utf-8"))
    assert plan["planId"] == first["planId"]
    assert set(plan) == {
        "schemaVersion",
        "kind",
        "helperVersion",
        "sourceRoot",
        "limits",
        "status",
        "files",
        "planId",
    }
    entry = plan["files"][0]
    assert entry["outsideCommentSha256"] == entry["outputOutsideCommentSha256"]
    assert entry["decodeRoundTrip"] is True
    assert entry["idempotent"] is True


def test_tampered_plan_and_wrong_plan_id_fail(tmp_path: Path, project: Path):
    source = ("/* \u4e2d */\nint a;\n").encode("gbk")
    _write(project, "App/a.c", source)
    preview_dir = tmp_path / "preview"
    result = _preview(project, preview_dir, ["App/a.c=gbk"])
    plan_path = preview_dir / "plan.json"

    with pytest.raises(nc.ToolError) as wrong:
        nc.copy_plan(
            str(project), str(plan_path), "0" * 64, str(tmp_path / "out-wrong")
        )
    assert wrong.value.code == "PLAN_ID_MISMATCH"

    plan = json.loads(plan_path.read_text("utf-8"))
    plan["files"][0]["outputSha256"] = "0" * 64
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", "utf-8")
    with pytest.raises(nc.ToolError) as id_mismatch:
        nc.copy_plan(
            str(project), str(plan_path), result["planId"], str(tmp_path / "out-tamper")
        )
    assert id_mismatch.value.code == "PLAN_ID_MISMATCH"

    plan["planId"] = nc.compute_plan_id(plan)
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", "utf-8")
    with pytest.raises(nc.ToolError) as tampered:
        nc.copy_plan(
            str(project),
            str(plan_path),
            plan["planId"],
            str(tmp_path / "out-tamper-2"),
        )
    assert tampered.value.code == "PLAN_TAMPERED"
    assert not (tmp_path / "out-tamper-2").exists()


def test_stale_plan_input_changed_fails(tmp_path: Path, project: Path):
    source = ("/* \u4e2d */\nint a;\n").encode("gbk")
    _write(project, "App/a.c", source)
    preview_dir = tmp_path / "preview"
    result = _preview(project, preview_dir, ["App/a.c=gbk"])
    _write(project, "App/a.c", source + b"// changed\n")
    with pytest.raises(nc.ToolError) as stale:
        _copy(project, preview_dir, result["planId"], tmp_path / "out")
    assert stale.value.code == "INPUT_CHANGED"
    assert not (tmp_path / "out").exists()


def test_output_collision_and_containment(
    tmp_path: Path, project: Path, monkeypatch
):
    _write(project, "App/a.c", ("/* \u4e2d */\nint a;\n").encode("gbk"))
    preview_dir = tmp_path / "preview"
    result = _preview(project, preview_dir, ["App/a.c=gbk"])

    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(nc.ToolError) as exists:
        _copy(project, preview_dir, result["planId"], existing)
    assert exists.value.code == "OUTPUT_EXISTS"

    with pytest.raises(nc.ToolError) as inside:
        _copy(project, preview_dir, result["planId"], project / "out")
    assert inside.value.code == "OUTPUT_CONTAINMENT"

    with pytest.raises(nc.ToolError) as contains:
        _copy(project, preview_dir, result["planId"], project.parent)
    assert contains.value.code == "OUTPUT_CONTAINMENT"

    with pytest.raises(nc.ToolError) as preview_inside:
        _preview(project, project / "preview", ["App/a.c=gbk"])
    assert preview_inside.value.code == "OUTPUT_CONTAINMENT"

    def collision(path: Path, data: bytes) -> None:
        raise FileExistsError("simulated existing output")

    monkeypatch.setattr(nc, "_write_output_file", collision)
    with pytest.raises(nc.ToolError) as collided:
        _copy(project, preview_dir, result["planId"], tmp_path / "collision-out")
    assert collided.value.code == "OUTPUT_COLLISION"
    assert (tmp_path / "collision-out" / "INCOMPLETE.json").exists()


def test_path_charset_and_selection_validation(tmp_path: Path, project: Path):
    _write(project, "App/a.c", b"int a;\n")
    cases = [
        ("../a.c=gbk", "PATH_INVALID"),
        ("C:/a.c=gbk", "PATH_INVALID"),
        ("App/a:b.c=gbk", "PATH_INVALID"),
        ("App/./a.c=gbk", "PATH_INVALID"),
        ("App//a.c=gbk", "PATH_INVALID"),
        ("App/a.s=gbk", "UNSUPPORTED_FILE_TYPE"),
        ("App/a.c=windows-1252", "UNSUPPORTED_CHARSET"),
        ("App/a.c", "USAGE"),
        ("App/a.c=", "UNSUPPORTED_CHARSET"),
    ]
    for index, (selection, code) in enumerate(cases):
        with pytest.raises(nc.ToolError) as error:
            _preview(project, tmp_path / f"preview-{index}", [selection])
        assert error.value.code == code, selection

    with pytest.raises(nc.ToolError) as duplicate:
        _preview(project, tmp_path / "preview-dup", ["App/a.c=gbk", "App/a.c=gb2312"])
    assert duplicate.value.code == "DUPLICATE_PATH"

    with pytest.raises(nc.ToolError) as missing:
        _preview(project, tmp_path / "preview-missing", ["App/missing.c=gbk"])
    assert missing.value.code == "INPUT_MISSING"


def test_copy_contains_only_selected_files_and_preserves_originals(
    tmp_path: Path, project: Path
):
    a = _write(project, "App/a.c", ("/* \u4e2d */\nint a;\n").encode("gbk"))
    b = _write(project, "Inc/b.h", ("/* \u4e2d */\nint b;\n").encode("gbk"))
    c = _write(project, "App/c.c", ("/* \u4e2d */\nint c;\n").encode("gbk"))
    before = {path: path.read_bytes() for path in (a, b, c)}
    preview_dir = tmp_path / "preview"
    result = _preview(project, preview_dir, ["App/a.c=gbk", "Inc/b.h=gbk"])
    output = tmp_path / "out"
    _copy(project, preview_dir, result["planId"], output)

    files = sorted(
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file()
    )
    assert files == ["App/a.c", "Inc/b.h", "manifest.json"]
    for path, content in before.items():
        assert path.read_bytes() == content
    manifest = json.loads((output / "manifest.json").read_text("utf-8"))
    assert [entry["path"] for entry in manifest["files"]] == ["App/a.c", "Inc/b.h"]
    assert manifest["totalFiles"] == 2
    assert manifest["originalsUnchanged"] is True
    assert manifest["outputsVerified"] is True


def test_partial_failure_marks_incomplete_staging(
    tmp_path: Path, project: Path, monkeypatch
):
    _write(project, "App/a.c", ("/* \u4e2d */\nint a;\n").encode("gbk"))
    _write(project, "Shop/b.h", ("/* \u4e2d */\nint b;\n").encode("gbk"))
    preview_dir = tmp_path / "preview"
    result = _preview(project, preview_dir, ["App/a.c=gbk", "Shop/b.h=gbk"])
    original_write = nc._write_output_file
    calls = {"count": 0}

    def flaky(path: Path, data: bytes) -> None:
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("simulated I/O failure")
        original_write(path, data)

    monkeypatch.setattr(nc, "_write_output_file", flaky)
    output = tmp_path / "out"
    with pytest.raises(nc.ToolError) as failure:
        _copy(project, preview_dir, result["planId"], output)
    assert failure.value.code == "IO_FAILURE"
    assert (output / "App/a.c").exists()
    assert not (output / "Shop/b.h").exists()
    assert not (output / "manifest.json").exists()
    marker = json.loads((output / "INCOMPLETE.json").read_text("utf-8"))
    assert marker["status"] == "incomplete"
    assert marker["filesWritten"] == ["App/a.c"]
    assert marker["planId"] == result["planId"]


def test_configured_bounds_are_enforced(tmp_path: Path, project: Path, monkeypatch):
    for name in ("a.c", "b.c", "c.c"):
        _write(project, f"App/{name}", b"int x;\n")

    monkeypatch.setattr(nc, "MAX_FILES", 2)
    with pytest.raises(nc.ToolError) as too_many:
        _preview(
            project,
            tmp_path / "preview-files",
            ["App/a.c=gbk", "App/b.c=gbk", "App/c.c=gbk"],
        )
    assert too_many.value.code == "BOUNDS_EXCEEDED"

    monkeypatch.setattr(nc, "MAX_FILE_BYTES", 4)
    with pytest.raises(nc.ToolError) as too_large:
        _preview(project, tmp_path / "preview-file", ["App/a.c=gbk"])
    assert too_large.value.code == "BOUNDS_EXCEEDED"

    monkeypatch.setattr(nc, "MAX_FILE_BYTES", 1024)
    monkeypatch.setattr(nc, "MAX_TOTAL_BYTES", 5)
    with pytest.raises(nc.ToolError) as too_much:
        _preview(project, tmp_path / "preview-total", ["App/a.c=gbk", "App/b.c=gbk"])
    assert too_much.value.code == "BOUNDS_EXCEEDED"


def test_reparse_input_path_is_rejected(tmp_path: Path, project: Path, monkeypatch):
    target = _write(tmp_path, "outside.c", b"int x;\n")
    (project / "App").mkdir()
    link = project / "App" / "link.c"
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        # This host does not grant symlink creation.  Exercise the same guard
        # with a simulated reparse component rather than skipping the path
        # defense entirely; the real symlink branch remains platform-only.
        original = nc._is_reparse
        monkeypatch.setattr(
            nc,
            "_is_reparse",
            lambda path: str(path).replace("\\", "/").endswith("/link.c")
            or original(path),
        )
    with pytest.raises(nc.ToolError) as reparse:
        _preview(project, tmp_path / "preview", ["App/link.c=gbk"])
    assert reparse.value.code == "REPARSE_PATH"


def test_cli_subprocess_preview_copy_and_blocked_exit(
    tmp_path: Path, project: Path
):
    _write(project, "App/a.c", ("/* \u4e2d */\nint a;\n").encode("gbk"))
    preview_dir = tmp_path / "preview"
    command = [
        sys.executable,
        str(HELPER_PATH),
        "preview",
        "--project-root",
        str(project),
        "--preview-dir",
        str(preview_dir),
        "--file",
        "App/a.c=gbk",
    ]
    completed = subprocess.run(
        command, check=False, capture_output=True, text=True, encoding="utf-8", timeout=120
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "ready"
    plan_id = payload["planId"]

    output = tmp_path / "out"
    copy = subprocess.run(
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
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert copy.returncode == 0, copy.stderr
    assert json.loads(copy.stdout)["status"] == "ok"
    assert (output / "manifest.json").exists()

    wrong = subprocess.run(
        [
            sys.executable,
            str(HELPER_PATH),
            "copy",
            "--project-root",
            str(project),
            "--plan",
            str(preview_dir / "plan.json"),
            "--plan-id",
            "0" * 64,
            "--output-dir",
            str(tmp_path / "out-wrong"),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert wrong.returncode == 2
    assert json.loads(wrong.stdout)["code"] == "PLAN_ID_MISMATCH"

    _write(project, "App/bad.c", b"/* \xf3 */\n")
    blocked = subprocess.run(
        [
            sys.executable,
            str(HELPER_PATH),
            "preview",
            "--project-root",
            str(project),
            "--preview-dir",
            str(tmp_path / "preview-blocked"),
            "--file",
            "App/bad.c=gbk",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert blocked.returncode == 2
    assert json.loads(blocked.stdout)["status"] == "blocked"

    # Exit code 2 also covers an operational failure, which is reported as
    # status=failed rather than as a reviewed blocked plan.
    failed = subprocess.run(
        [
            sys.executable,
            str(HELPER_PATH),
            "preview",
            "--project-root",
            str(project),
            "--preview-dir",
            str(tmp_path / "preview-failed"),
            "--file",
            "../escape.c=gbk",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert failed.returncode == 2
    failed_payload = json.loads(failed.stdout)
    assert failed_payload["status"] == "failed"
    assert failed_payload["code"] == "PATH_INVALID"
    assert not (tmp_path / "preview-failed").exists()


def test_skill_frontmatter_and_bundled_quick_validate():
    assert SKILL_PATH.is_file()
    assert HELPER_PATH.is_file()
    skill = SKILL_PATH.read_text("utf-8")
    assert skill.startswith("---\nname: normalize-source-comments\n")
    frontmatter = skill.split("---", 2)[1]
    assert "\ndescription:" in frontmatter
    if not (BASE_PYTHON.is_file() and SKILL_VALIDATOR.is_file()):
        pytest.skip("bundled base interpreter or quick_validate is unavailable")
    completed = subprocess.run(
        [str(BASE_PYTHON), str(SKILL_VALIDATOR), str(SKILL_PATH.parent)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "valid" in completed.stdout.lower()


def test_arm_gnu_object_equivalence_for_comment_only_conversion(tmp_path: Path):
    if not ARM_GCC.exists():
        pytest.skip(f"ARM GNU compiler is unavailable at {ARM_GCC}")
    cases = [
        ("gb2312", "GB2312", "\u4e2d\u6587"),
        ("gbk", "GBK", "\u4e02"),
        ("gb18030", "GB18030", "\U0001F600"),
        ("cp1252", "CP1252", "caf\u00e9"),
    ]
    supported: set[str] = set()
    unsupported: dict[str, str] = {}
    base_command = [
        str(ARM_GCC),
        "-c",
        "-std=gnu11",
        "-O2",
        "-mcpu=cortex-m4",
        "-mthumb",
        "-fexec-charset=UTF-8",
    ]
    for name, gcc_charset, comment in cases:
        work = tmp_path / name
        work.mkdir()
        source = (
            f"/* {comment} */\nint add(int a, int b) {{ return a + b; }}\n"
        ).encode(name)
        analysis = nc.analyze_bytes(source, name, f"{name}.c")
        assert analysis.status == "ready", analysis.findings
        assert analysis.output is not None
        legacy_dir = work / "legacy"
        utf8_dir = work / "utf8"
        legacy_dir.mkdir()
        utf8_dir.mkdir()
        # The ELF FILE symbol records the basename, so both probes must use the
        # same basename in separate directories for a byte-level comparison.
        legacy_source = legacy_dir / "a.c"
        utf8_source = utf8_dir / "a.c"
        legacy_source.write_bytes(source)
        utf8_source.write_bytes(analysis.output)
        legacy_object = work / "legacy.o"
        utf8_object = work / "utf8.o"
        legacy = subprocess.run(
            base_command
            + [
                f"-finput-charset={gcc_charset}",
                "-o",
                str(legacy_object),
                str(legacy_source),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if legacy.returncode != 0:
            last_line = (legacy.stderr.strip().splitlines() or ["<no stderr>"])[-1]
            unsupported[name] = last_line
            continue
        utf8 = subprocess.run(
            base_command
            + [
                "-finput-charset=UTF-8",
                "-o",
                str(utf8_object),
                str(utf8_source),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert utf8.returncode == 0, utf8.stderr
        supported.add(name)
        assert legacy_object.read_bytes() == utf8_object.read_bytes(), (
            f"object mismatch for {name}"
        )
    assert {"gb2312", "gbk", "gb18030"} <= supported, (
        f"supported={sorted(supported)} unsupported={unsupported}"
    )
    if "cp1252" in unsupported:
        warnings.warn(
            f"GCC does not support CP1252 as an input charset here: {unsupported['cp1252']}",
            RuntimeWarning,
            stacklevel=2,
        )


def _directive_case_sources() -> dict[str, bytes]:
    header = bytes.fromhex("d6d0cec4")
    return {
        "repro": b"#include /*x*/ <dir//" + header + b".h>\n",
        "hash_comment": b"#/**/include <dir//" + header + b".h>\n",
        "between": b"#include/**/<dir//" + header + b".h>\n",
        "digraph": b"%:include <dir//" + header + b".h>\n",
        "trigraph": b"??=include <dir//" + header + b".h>\n",
        "header_comment": b"#include <dir/*x*/" + header + b".h>\n",
        "include_next": b"#include_next /*x*/ <dir//" + header + b".h>\n",
        "import_directive": b"#import /*x*/ <dir//" + header + b".h>\n",
        "embed": b"#embed /*x*/ <dir//" + header + b".h>\n",
        "orphan_comment": b"#include // comment\n<dir//" + header + b".h>\n",
        "has_include": b"__has_include(<dir//" + header + b".h>)\n",
        "has_include_next": b"__has_include_next(<dir//" + header + b".h>)\n",
        "import_unit": b"import <dir//" + header + b".h>;\n",
        "export_import": b"export import <dir//" + header + b".h>;\n",
    }


def test_preprocessing_header_names_are_never_comment_content(
    tmp_path: Path, project: Path
):
    sources = _directive_case_sources()
    selections = []
    for name, source in sources.items():
        suffix = ".cpp" if name in ("import_unit", "export_import") else ".c"
        relative = f"App/{name}{suffix}"
        _write(project, relative, source)
        selections.append(f"{relative}=gb18030")
    preview_dir = tmp_path / "preview"
    result = _preview(project, preview_dir, selections)
    assert result["status"] == "blocked"
    for name in sources:
        suffix = ".cpp" if name in ("import_unit", "export_import") else ".c"
        entry = _plan_file(preview_dir, f"App/{name}{suffix}")
        assert entry["status"] == "blocked", name
        assert entry["outputSha256"] is None, name
        blockers = _codes(entry, "blocker")
        if name == "trigraph":
            assert "TRIGRAPH_DIRECTIVE_UNSUPPORTED" in blockers
        elif name == "orphan_comment":
            assert "UNSUPPORTED_INCLUDE_FORM" in blockers
        else:
            assert "NON_COMMENT_NON_ASCII" in blockers, name
        if name == "repro":
            # The /*x*/ delta is a real comment; the two Chinese bytes in the
            # header name are not changed units and must never be proposed.
            assert entry["commentCount"] == 1
            assert entry["changedUnits"] == 0

    _write(project, "App/control-ascii.c", b"#include <dir//ascii.h>\nint x;\n")
    _write(
        project,
        "App/control-comment.c",
        b"#include /*" + bytes.fromhex("d6d0cec4") + b"*/ <ascii.h>\n",
    )
    controls = _preview(
        project,
        tmp_path / "preview-controls",
        ["App/control-ascii.c=gbk", "App/control-comment.c=gbk"],
    )
    assert controls["status"] == "ready"
    ascii_header = _plan_file(tmp_path / "preview-controls", "App/control-ascii.c")
    assert ascii_header["commentCount"] == 0
    assert ascii_header["changedUnits"] == 0
    comment_header = _plan_file(
        tmp_path / "preview-controls", "App/control-comment.c"
    )
    assert comment_header["commentCount"] == 1
    assert comment_header["changedUnits"] == 2


def test_blocking_findings_survive_presentation_cap(
    tmp_path: Path, project: Path
):
    capped = b"// A\x92s\n" * nc.MAX_FINDINGS + b"// \xa3B\n"
    _write(project, "App/capped.c", capped)
    preview_dir = tmp_path / "preview-capped"
    result = _preview(project, preview_dir, ["App/capped.c=gb18030"])
    assert result["status"] == "blocked"
    entry = _plan_file(preview_dir, "App/capped.c")
    assert entry["outputSha256"] is None
    assert any(finding["severity"] == "blocker" for finding in entry["findings"])
    with pytest.raises(nc.ToolError) as blocked_copy:
        _copy(project, preview_dir, result["planId"], tmp_path / "out-capped")
    assert blocked_copy.value.code == "PLAN_BLOCKED"

    trigraphs = (
        b"/* " + b"??( " * (nc.MAX_FINDINGS + 5) + b"??/ " + b"*/"
    )
    _write(project, "App/trigraph-capped.c", trigraphs)
    trigraph_dir = tmp_path / "preview-trigraph-capped"
    trigraph_result = _preview(
        project, trigraph_dir, ["App/trigraph-capped.c=gbk"]
    )
    assert trigraph_result["status"] == "blocked"
    trigraph_entry = _plan_file(trigraph_dir, "App/trigraph-capped.c")
    assert "TRIGRAPH_BACKSLASH_UNSUPPORTED" in _codes(trigraph_entry, "blocker")
    assert trigraph_entry["outputSha256"] is None


def test_combined_warning_sources_stay_copyable_and_a_late_blocker_blocks(
    tmp_path: Path, project: Path
):
    # One line contributes one trigraph warning and one DBCS mixed-byte warning,
    # so both independently bounded presentation lists are full at the same
    # time.  The resulting ready plan must still pass copy validation.
    combined = b"// ??( A\x92s\n" * nc.MAX_FINDINGS
    assert len(combined) < nc.MAX_FILE_BYTES
    _write(project, "App/combined.c", combined)
    preview_dir = tmp_path / "preview-combined"
    result = _preview(project, preview_dir, ["App/combined.c=gb18030"])
    assert result["status"] == "ready"
    assert result["warnings"] == nc.MAX_FINDINGS * 2
    entry = _plan_file(preview_dir, "App/combined.c")
    codes = _codes(entry)
    assert codes.count("TRIGRAPH_SEQUENCE_REVIEW") == nc.MAX_FINDINGS
    assert codes.count("MIXED_SINGLE_BYTE_ARTIFACT") == nc.MAX_FINDINGS
    assert len(entry["findings"]) == nc.MAX_FINDINGS * 2
    assert len(entry["findings"]) > nc.MAX_FINDINGS + 8
    assert len(entry["findings"]) <= nc.MAX_PRESENTED_FINDINGS
    assert entry["status"] == "ready"

    output = tmp_path / "out-combined"
    copied = _copy(project, preview_dir, result["planId"], output)
    assert copied["status"] == "ok"
    expected_line = "// ??( A" + chr(0x62AF) + "\n"
    assert _read(output, "App/combined.c") == (
        expected_line * nc.MAX_FINDINGS
    ).encode("utf-8")

    # The same warning volume plus a blocker after the scanner's presentation
    # cap must remain blocked; neither bound may hide the blocking state.
    late = combined + b"int \xa3B;\n"
    _write(project, "App/late.c", late)
    blocked_dir = tmp_path / "preview-late"
    blocked = _preview(project, blocked_dir, ["App/late.c=gb18030"])
    assert blocked["status"] == "blocked"
    late_entry = _plan_file(blocked_dir, "App/late.c")
    assert late_entry["status"] == "blocked"
    assert late_entry["outputSha256"] is None
    assert len(late_entry["findings"]) <= nc.MAX_PRESENTED_FINDINGS
    blocker_codes = _codes(late_entry, "blocker")
    assert "FINDINGS_TRUNCATED" in blocker_codes
    blocked_output = tmp_path / "out-late"
    with pytest.raises(nc.ToolError) as blocked_copy:
        _copy(project, blocked_dir, blocked["planId"], blocked_output)
    assert blocked_copy.value.code == "PLAN_BLOCKED"
    assert not blocked_output.exists()


def test_long_identifier_token_is_scanned_once():
    source = b"int " + b"a" * 50_000 + b" = 1; // \xd6\xd0\n"
    analysis = nc.analyze_bytes(source, "gbk", "App/long-token.c")
    assert analysis.status == "ready"
    assert analysis.comment_count == 1
    assert analysis.output == (
        b"int " + b"a" * 50_000 + b" = 1; // \xe4\xb8\xad\n"
    )


def test_decoded_character_limit_blocks_before_mapping_build(
    tmp_path: Path, project: Path, monkeypatch
):
    monkeypatch.setattr(nc, "MAX_DECODED_CHARACTERS", 10)
    _write(project, "App/long.c", b"// 01234567890123456789\n")
    preview_dir = tmp_path / "preview"
    result = _preview(project, preview_dir, ["App/long.c=gbk"])
    assert result["status"] == "blocked"
    entry = _plan_file(preview_dir, "App/long.c")
    decode = next(
        finding for finding in entry["findings"] if finding["code"] == "DECODE_ERROR"
    )
    assert "decoded character count" in decode["message"]
    assert entry["outputSha256"] is None
    plan = json.loads((preview_dir / "plan.json").read_text("utf-8"))
    assert plan["limits"]["maxDecodedCharacters"] == 10


def test_output_bounds_are_enforced_before_ready(
    tmp_path: Path, project: Path, monkeypatch
):
    monkeypatch.setattr(nc, "MAX_OUTPUT_BYTES", 5)
    _write(project, "App/expand.c", b"/* \xd6\xd0 */\nint x;\n")
    preview_dir = tmp_path / "preview-output"
    result = _preview(project, preview_dir, ["App/expand.c=gbk"])
    assert result["status"] == "blocked"
    entry = _plan_file(preview_dir, "App/expand.c")
    assert "OUTPUT_BOUND_EXCEEDED" in _codes(entry, "blocker")
    assert entry["outputSha256"] is None

    monkeypatch.setattr(nc, "MAX_OUTPUT_BYTES", 1024)
    monkeypatch.setattr(nc, "MAX_TOTAL_OUTPUT_BYTES", 5)
    _write(project, "App/small.c", b"int x;\n")
    with pytest.raises(nc.ToolError) as aggregate:
        _preview(project, tmp_path / "preview-total", ["App/small.c=gbk"])
    assert aggregate.value.code == "BOUNDS_EXCEEDED"


def test_reparse_ancestors_are_rejected(
    tmp_path: Path, project: Path, monkeypatch
):
    original = nc._is_reparse
    redirected_root = tmp_path / "redirected-root"
    redirected_preview = tmp_path / "redirected-preview"
    redirected_output = tmp_path / "redirected-output"
    redirected_plan = tmp_path / "redirected-plan"

    def identity(path: object) -> str:
        return os.path.normcase(os.path.abspath(os.fspath(path)))

    redirected = {
        identity(redirected_root),
        identity(redirected_preview),
        identity(redirected_output),
        identity(redirected_plan),
    }

    def fake(path: object) -> bool:
        # Only the exact redirected ancestor directories are reported as
        # reparse points.  Every descendant stays false, so this test can only
        # pass if the helper checks an ancestor rather than the leaf.
        if identity(path) in redirected:
            return True
        return original(path)

    monkeypatch.setattr(nc, "_is_reparse", fake)

    def assert_ancestor(error: nc.ToolError, ancestor: Path) -> None:
        assert error.details["component"] is not None
        assert identity(error.details["component"]) == identity(ancestor)

    nested_project = redirected_root / "project"
    nested_project.mkdir(parents=True)
    _write(nested_project, "App/a.c", b"int a;\n")
    assert nc._is_reparse(nested_project) is False
    assert nc._is_reparse(nested_project / "App") is False
    assert nc._is_reparse(nested_project / "App" / "a.c") is False
    with pytest.raises(nc.ToolError) as root_reparse:
        _preview(nested_project, tmp_path / "preview-root", ["App/a.c=gbk"])
    assert root_reparse.value.code == "REPARSE_PATH"
    assert_ancestor(root_reparse.value, redirected_root)
    assert not (tmp_path / "preview-root").exists()

    _write(project, "App/a.c", b"int a;\n")
    redirected_preview.mkdir()
    preview_leaf = redirected_preview / "preview"
    assert nc._is_reparse(preview_leaf) is False
    assert nc._is_reparse(project / "App" / "a.c") is False
    with pytest.raises(nc.ToolError) as preview_reparse:
        _preview(project, preview_leaf, ["App/a.c=gbk"])
    assert preview_reparse.value.code == "REPARSE_PATH"
    assert_ancestor(preview_reparse.value, redirected_preview)
    assert not preview_leaf.exists()

    ready_dir = tmp_path / "preview-ready"
    ready = _preview(project, ready_dir, ["App/a.c=gbk"])
    redirected_output.mkdir()
    output_leaf = redirected_output / "out"
    assert nc._is_reparse(output_leaf) is False
    with pytest.raises(nc.ToolError) as output_reparse:
        _copy(project, ready_dir, ready["planId"], output_leaf)
    assert output_reparse.value.code == "REPARSE_PATH"
    assert_ancestor(output_reparse.value, redirected_output)
    assert not output_leaf.exists()

    redirected_plan.mkdir()
    plan_copy = redirected_plan / "plan.json"
    plan_copy.write_bytes((ready_dir / "plan.json").read_bytes())
    assert nc._is_reparse(plan_copy) is False
    with pytest.raises(nc.ToolError) as plan_reparse:
        nc.copy_plan(
            str(project),
            str(plan_copy),
            ready["planId"],
            str(tmp_path / "out-plan"),
        )
    assert plan_reparse.value.code == "REPARSE_PATH"
    assert_ancestor(plan_reparse.value, redirected_plan)
    assert not (tmp_path / "out-plan").exists()

    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    link_parent = tmp_path / "link-parent"
    try:
        os.symlink(real_parent, link_parent, target_is_directory=True)
    except (OSError, NotImplementedError):
        link_parent = None
    if link_parent is not None:
        real_nested = link_parent / "project"
        real_nested.mkdir()
        _write(real_nested, "App/a.c", b"int a;\n")
        with pytest.raises(nc.ToolError) as real_reparse:
            _preview(real_nested, tmp_path / "preview-real", ["App/a.c=gbk"])
        assert real_reparse.value.code == "REPARSE_PATH"


def test_plan_metadata_requires_exact_types(tmp_path: Path, project: Path):
    _write(project, "App/a.c", b"/* ETHERNET\x92s DMA */\nint x;\n")
    preview_dir = tmp_path / "preview"
    result = _preview(project, preview_dir, ["App/a.c=gbk"])
    plan_path = preview_dir / "plan.json"
    plan = json.loads(plan_path.read_text("utf-8"))
    assert plan["files"][0]["findings"]

    tamperings = []
    variant = copy.deepcopy(plan)
    variant["schemaVersion"] = True
    tamperings.append(variant)
    variant = copy.deepcopy(plan)
    variant["files"][0]["sourceSize"] = float(variant["files"][0]["sourceSize"])
    tamperings.append(variant)
    variant = copy.deepcopy(plan)
    variant["files"][0]["newline"]["crlf"] = True
    tamperings.append(variant)
    variant = copy.deepcopy(plan)
    variant["files"][0]["bom"] = 1
    tamperings.append(variant)
    variant = copy.deepcopy(plan)
    variant["files"][0]["findings"][0]["severity"] = True
    tamperings.append(variant)
    variant = copy.deepcopy(plan)
    variant["files"] = "not-a-list"
    tamperings.append(variant)

    for index, variant in enumerate(tamperings):
        variant["planId"] = nc.compute_plan_id(variant)
        path = tmp_path / f"tampered-{index}.json"
        path.write_text(json.dumps(variant, ensure_ascii=False), "utf-8")
        with pytest.raises(nc.ToolError) as invalid:
            nc.copy_plan(
                str(project),
                str(path),
                variant["planId"],
                str(tmp_path / f"out-{index}"),
            )
        assert invalid.value.code == "PLAN_INVALID", index
        assert not (tmp_path / f"out-{index}").exists()

    nan_plan = tmp_path / "nan-plan.json"
    nan_plan.write_text('{"schemaVersion": NaN}', "utf-8")
    with pytest.raises(nc.ToolError) as malformed:
        nc.copy_plan(str(project), str(nan_plan), "0" * 64, str(tmp_path / "out-nan"))
    assert malformed.value.code == "PLAN_INVALID"


def test_incomplete_marker_is_durable_and_reserved_paths_are_rejected(
    tmp_path: Path, project: Path, monkeypatch
):
    _write(project, "App/a.c", b"int a;\n")
    _write(project, "App/b.c", b"int b;\n")
    preview_dir = tmp_path / "preview"
    result = _preview(project, preview_dir, ["App/a.c=gbk", "App/b.c=gbk"])
    original_write = nc._write_output_file
    output = tmp_path / "out"
    observed: list[bool] = []

    def observe(path: Path, data: bytes) -> None:
        observed.append((output / "INCOMPLETE.json").exists())
        original_write(path, data)

    monkeypatch.setattr(nc, "_write_output_file", observe)
    _copy(project, preview_dir, result["planId"], output)
    assert observed and all(observed)
    assert not (output / "INCOMPLETE.json").exists()
    assert (output / "manifest.json").exists()

    failing = tmp_path / "out-fail"
    calls = {"count": 0}

    def fail_first(path: Path, data: bytes) -> None:
        calls["count"] += 1
        assert (failing / "INCOMPLETE.json").exists()
        raise OSError("simulated failure")

    monkeypatch.setattr(nc, "_write_output_file", fail_first)
    with pytest.raises(nc.ToolError) as failure:
        _copy(project, preview_dir, result["planId"], failing)
    assert failure.value.code == "IO_FAILURE"
    marker = json.loads((failing / "INCOMPLETE.json").read_text("utf-8"))
    assert marker["stage"] == "failed"
    assert marker["filesWritten"] == []
    assert not (failing / "manifest.json").exists()

    for index, relative in enumerate(
        (
            "manifest.json/x.c",
            "manifest.json.partial/x.c",
            "INCOMPLETE.json/x.c",
            "INCOMPLETE.2.json/x.c",
        )
    ):
        with pytest.raises(nc.ToolError) as reserved:
            _preview(
                project,
                tmp_path / f"preview-reserved-{index}",
                [f"{relative}=gbk"],
            )
        assert reserved.value.code == "RESERVED_OUTPUT_PATH"

    plan = json.loads((preview_dir / "plan.json").read_text("utf-8"))
    plan["files"][0]["path"] = "manifest.json/x.c"
    plan["planId"] = nc.compute_plan_id(plan)
    tampered = tmp_path / "reserved-plan.json"
    tampered.write_text(json.dumps(plan, ensure_ascii=False), "utf-8")
    with pytest.raises(nc.ToolError) as reserved_plan:
        nc.copy_plan(
            str(project),
            str(tampered),
            plan["planId"],
            str(tmp_path / "out-reserved-plan"),
        )
    assert reserved_plan.value.code == "RESERVED_OUTPUT_PATH"


def test_reserved_metadata_aliases_are_rejected_before_output(
    tmp_path: Path, project: Path
):
    _write(project, "App/a.c", b"int a;\n")
    aliases = (
        "MANIFEST.JSON/x.c",
        "Manifest.Json.Partial/x.c",
        "incomplete.json/x.c",
        "INCOMPLETE.7.JSON/x.c",
        "manifest.json./x.c",
        "INCOMPLETE.json /x.c",
        "manifest.json.partial. /x.c",
    )
    for index, relative in enumerate(aliases):
        preview_dir = tmp_path / f"preview-alias-{index}"
        with pytest.raises(nc.ToolError) as alias:
            _preview(project, preview_dir, [f"{relative}=gbk"])
        assert alias.value.code == "RESERVED_OUTPUT_PATH", relative
        assert not preview_dir.exists(), relative

    preview_dir = tmp_path / "preview-base"
    result = _preview(project, preview_dir, ["App/a.c=gbk"])
    plan = json.loads((preview_dir / "plan.json").read_text("utf-8"))
    plan["files"][0]["path"] = "MANIFEST.JSON/x.c"
    plan["planId"] = nc.compute_plan_id(plan)
    tampered = tmp_path / "alias-plan.json"
    tampered.write_text(json.dumps(plan, ensure_ascii=False), "utf-8")
    output = tmp_path / "out-alias"
    with pytest.raises(nc.ToolError) as reserved_plan:
        nc.copy_plan(str(project), str(tampered), plan["planId"], str(output))
    assert reserved_plan.value.code == "RESERVED_OUTPUT_PATH"
    assert not output.exists()
    assert result["status"] == "ready"
