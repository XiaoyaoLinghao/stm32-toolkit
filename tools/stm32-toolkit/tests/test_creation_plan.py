from __future__ import annotations

import hashlib
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest

from stm32_toolkit.generation.creation import (
    CreationInputError,
    CreationRequest,
    plan_project_creation,
)
from stm32_toolkit.tool_support import ToolFact, ToolSupportProfile
from stm32_toolkit.tool_support import ToolSupportIssue

_NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


def _tools(tmp_path: Path, *, cubemx: bool = True) -> ToolSupportProfile:
    def fact(name: str) -> ToolFact:
        path = tmp_path / f"{name}.exe"
        path.write_bytes(name.encode())
        return ToolFact(name, path, "1.0", "explicit", hashlib.sha256(path.read_bytes()).hexdigest())
    return ToolSupportProfile(
        "3.12.10", fact("cubeMx") if cubemx else None, tmp_path,
        fact("gcc"), fact("cmake"), fact("ninja"), fact("vsCode"), (), ()
    )


def test_creation_request_accepts_exactly_one_ioc_and_hashes_it(tmp_path: Path):
    ioc = tmp_path / "board.ioc"
    ioc.write_text("Mcu.Name=STM32F429ZI\n", encoding="utf-8")
    plan = plan_project_creation(
        tmp_path,
        CreationRequest.from_ioc("board.ioc", "generated", framework="hal", language="c"),
        _tools(tmp_path),
        now=_NOW,
    )
    assert plan.request.source.kind == "ioc"
    assert plan.request.source.sha256 == hashlib.sha256(ioc.read_bytes()).hexdigest()


def test_creation_plan_is_deterministic_expires_in_one_hour_and_is_json_closed(tmp_path: Path):
    request = CreationRequest.from_mcu("STM32F429ZITx", "generated", framework="hal", language="c")
    first = plan_project_creation(tmp_path, request, _tools(tmp_path), now=_NOW)
    second = plan_project_creation(tmp_path, request, _tools(tmp_path), now=_NOW)
    assert first.plan_id == second.plan_id
    assert first.action_digest == second.action_digest
    assert first.expires_at == "2026-08-23T13:00:00Z"
    assert tuple(first.to_dict()) == ("schemaVersion", "planId", "actionDigest", "expiresAt", "request", "toolProfileDigest", "destinationInventoryDigest", "blockers")


def test_missing_cubemx_returns_stable_blocker_without_writes(tmp_path: Path):
    tools = _tools(tmp_path, cubemx=False)
    before = tuple(sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")))
    plan = plan_project_creation(tmp_path, CreationRequest.from_mcu("STM32F429ZITx", "generated", framework="hal", language="c"), tools, now=_NOW)
    assert [item.code for item in plan.blockers] == ["CUBEMX_MISSING"]
    assert tuple(sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))) == before


@pytest.mark.parametrize("value", ["../outside", "/absolute", "C:\\absolute", "a\\..\\b", "a\x00b"])
def test_creation_request_rejects_unsafe_paths(value: str):
    with pytest.raises(CreationInputError):
        CreationRequest.from_mcu("STM32F429ZITx", value, framework="hal", language="c")


def test_ioc_requires_ioc_suffix_and_absent_empty_inventory_digests_differ(tmp_path: Path):
    bad = tmp_path / "input.txt"
    bad.write_text("Mcu.Name=STM32F4\n", encoding="utf-8")
    with pytest.raises(CreationInputError):
        plan_project_creation(tmp_path, CreationRequest.from_ioc("input.txt", "generated", framework="hal", language="c"), _tools(tmp_path), now=_NOW)
    request = CreationRequest.from_mcu("STM32F429ZITx", "generated", framework="hal", language="c")
    absent = plan_project_creation(tmp_path, request, _tools(tmp_path), now=_NOW)
    (tmp_path / "generated").mkdir()
    empty = plan_project_creation(tmp_path, request, _tools(tmp_path), now=_NOW)
    assert absent.destination_inventory_digest != empty.destination_inventory_digest


@pytest.mark.parametrize("payload", [b"\xff", b"x" * (2 * 1024 * 1024)], ids=["invalid-utf8", "oversize"])
def test_ioc_rejects_invalid_utf8_or_oversize(tmp_path: Path, payload: bytes):
    ioc = tmp_path / "bad.ioc"
    ioc.write_bytes(payload)
    with pytest.raises((CreationInputError, OSError, ValueError)):
        plan_project_creation(tmp_path, CreationRequest.from_ioc("bad.ioc", "generated", framework="hal", language="c"), _tools(tmp_path), now=_NOW)


def test_ioc_unreadable_file_is_closed(tmp_path: Path, monkeypatch):
    ioc = tmp_path / "unreadable.ioc"
    ioc.write_text("Mcu.Name=STM32F4\n", encoding="utf-8")
    original = Path.read_text

    def unreadable(path: Path, *args, **kwargs):
        if path == ioc:
            raise PermissionError("denied")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", unreadable)
    with pytest.raises(CreationInputError) as error:
        plan_project_creation(
            tmp_path,
            CreationRequest.from_ioc("unreadable.ioc", "generated", framework="hal", language="c"),
            _tools(tmp_path),
            now=_NOW,
        )
    assert error.value.code == "CREATION_IOC_UNAVAILABLE"


@pytest.mark.parametrize("target_kind", ["source", "destination"])
def test_source_and_destination_redirect_parents_are_rejected(tmp_path: Path, target_kind: str):
    outside = tmp_path.parent / f"outside-{target_kind}"
    outside.mkdir()
    redirect = tmp_path / f"redirect-{target_kind}"
    redirect.mkdir()
    import stm32_toolkit.generation.creation as creation
    original_lstat = creation.os.lstat

    def reparse_parent(path: Path):
        info = original_lstat(path)
        if Path(path) == redirect:
            return types.SimpleNamespace(
                st_mode=info.st_mode,
                st_file_attributes=getattr(creation, "_REPARSE", 0x400),
            )
        return info

    if target_kind == "source":
        (outside / "board.ioc").write_text("Mcu.Name=STM32F4\n", encoding="utf-8")
        request = CreationRequest.from_ioc("redirect-source/board.ioc", "generated", framework="hal", language="c")
    else:
        request = CreationRequest.from_mcu("STM32F429ZITx", "redirect-destination/generated", framework="hal", language="c")
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(creation.os, "lstat", reparse_parent)
    with pytest.raises(CreationInputError) as error:
        plan_project_creation(tmp_path, request, _tools(tmp_path), now=_NOW)
    monkeypatch.undo()
    assert error.value.code == "CREATION_PATH_INVALID"


def test_inventory_states_are_distinct_and_unsafe_is_closed(tmp_path: Path):
    request = CreationRequest.from_mcu("STM32F429ZITx", "generated", framework="hal", language="c")
    absent = plan_project_creation(tmp_path, request, _tools(tmp_path), now=_NOW)
    (tmp_path / "generated").mkdir()
    empty = plan_project_creation(tmp_path, request, _tools(tmp_path), now=_NOW)
    (tmp_path / "generated" / "main.c").write_text("int main(void) {}\n", encoding="utf-8")
    populated = plan_project_creation(tmp_path, request, _tools(tmp_path), now=_NOW)
    (tmp_path / "generated" / "main.c").unlink()
    (tmp_path / "generated").rmdir()
    (tmp_path / "generated").mkdir()
    import stm32_toolkit.generation.creation as creation
    original_lstat = creation.os.lstat

    def unsafe_inventory(path: Path):
        info = original_lstat(path)
        if Path(path) == tmp_path / "generated":
            return types.SimpleNamespace(
                st_mode=info.st_mode,
                st_file_attributes=getattr(creation, "_REPARSE", 0x400),
            )
        return info

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(creation.os, "lstat", unsafe_inventory)
    unsafe = plan_project_creation(tmp_path, request, _tools(tmp_path), now=_NOW)
    monkeypatch.undo()

    digests = {
        absent.destination_inventory_digest,
        empty.destination_inventory_digest,
        populated.destination_inventory_digest,
        unsafe.destination_inventory_digest,
    }
    assert len(digests) == 4
    assert [item.code for item in populated.blockers] == ["DESTINATION_NOT_EMPTY"]
    assert [item.code for item in unsafe.blockers] == ["DESTINATION_UNSAFE"]


def test_all_non_vscode_support_issues_propagate_in_sorted_order(tmp_path: Path):
    tools = _tools(tmp_path)
    tools = ToolSupportProfile(
        tools.python_version,
        tools.cubemx,
        tools.cubeclt_root,
        tools.gcc,
        tools.cmake,
        tools.ninja,
        tools.vscode,
        tools.vscode_extensions,
        (
            ToolSupportIssue("NINJA_PROBE_FAILED", "ninja", "fix ninja"),
            ToolSupportIssue("VSCODE_MISSING", "vsCode", "fix vscode"),
            ToolSupportIssue("CUBEMX_UNSUPPORTED", "cubeMx", "fix cubemx"),
            ToolSupportIssue("CMAKE_UNSUPPORTED", "cmake", "fix cmake"),
            ToolSupportIssue("PYTHON_UNSUPPORTED", "python", "fix python"),
            ToolSupportIssue("GCC_INVALID", "gcc", "fix gcc"),
        ),
    )
    request = CreationRequest.from_mcu("STM32F429ZITx", "generated", framework="hal", language="c")
    plan = plan_project_creation(tmp_path, request, tools, now=_NOW)
    assert [item.code for item in plan.blockers] == [
        "CUBEMX_UNSUPPORTED",
        "GCC_INVALID",
        "CMAKE_UNSUPPORTED",
        "NINJA_PROBE_FAILED",
        "PYTHON_UNSUPPORTED",
    ]


@pytest.mark.parametrize("kind", ["mcu", "board", "ioc"])
def test_all_creation_source_kinds_have_literal_plans(tmp_path: Path, kind: str):
    if kind == "mcu":
        request = CreationRequest.from_mcu("STM32F429ZITx", "generated", framework="hal", language="c")
    elif kind == "board":
        request = CreationRequest.from_board("NUCLEO-F429ZI", "generated", framework="hal", language="c")
    else:
        (tmp_path / "board.ioc").write_text("Mcu.Name=STM32F4\n", encoding="utf-8")
        request = CreationRequest.from_ioc("board.ioc", "generated", framework="hal", language="c")
    assert plan_project_creation(tmp_path, request, _tools(tmp_path), now=_NOW).request.source.kind == kind
