"""Firmware identity evidence contract tests (STM32TK-0305).

Covers input snapshotting, bounded Git evidence, ELF32 little-endian ARM
validation (vector table, Reset_Handler, entry point, undefined symbols),
identity construction with the schema-1 build id, schema validation, and the
atomic JSON helpers shared with the build runner.
"""

from __future__ import annotations

import json
import shutil
import struct
from pathlib import Path

import pytest

import stm32_toolkit.build.identity as identity_mod
from stm32_toolkit.build.identity import (
    BuildError,
    ElfEvidence,
    GitEvidence,
    InputSnapshot,
    InputSnapshotFile,
    build_identity,
    git_evidence,
    read_json_bounded,
    snapshot_inputs,
    snapshot_sha256,
    validate_elf,
    validate_identity_document,
    write_json_atomic,
    write_text_atomic,
)
from stm32_toolkit.build.model import MemoryUsage
from stm32_toolkit.process import ProcessRequest, run_process
from stm32_toolkit.project_model import load_project_model

FIXTURE = Path(__file__).parent / "fixtures" / "minimal-gcc"
SCHEMA_ROOT = Path(__file__).resolve().parents[3] / "schemas" / "firmware-identity.schema.json"
SCHEMA_PACKAGED = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "stm32_toolkit"
    / "schemas"
    / "firmware-identity.schema.json"
)


def _shstrtab(names: tuple[str, ...]) -> tuple[bytes, dict[str, int]]:
    out = b"\x00"
    offsets: dict[str, int] = {}
    for name in names:
        offsets[name] = len(out)
        out += name.encode("ascii") + b"\x00"
    return out, offsets


def _strtab(symbols: tuple[tuple[str, int, int, int, int, int], ...]) -> tuple[bytes, dict[int, int]]:
    """Build a string table and map symbol index to st_name."""
    out = b"\x00"
    names: dict[int, int] = {}
    for index, (name, *_rest) in enumerate(symbols):
        names[index] = len(out)
        out += name.encode("ascii") + b"\x00"
    return out, names


def write_test_elf(
    path: Path,
    *,
    entry: int = 0x08000401,
    reset_handler: int = 0x08000401,
    with_isr: bool = True,
    with_reset: bool = True,
    undefined: tuple[str, ...] = (),
    weak_undefined: tuple[str, ...] = (),
    elfclass: int = 32,
    little: bool = True,
    machine: int = 40,
) -> None:
    """Write a minimal ELF32/ELF64 little/big-endian test image."""
    if elfclass == 64:
        _write_test_elf64(path, entry=entry, reset_handler=reset_handler, machine=machine)
        return
    endian = "<" if little else ">"
    isr = (".isr_vector", 0x08000000, 0x400) if with_isr else None
    text = (".text", 0x08000400, 0x10)
    shstr, sh_offs = _shstrtab(
        (".shstrtab", ".isr_vector", ".text", ".symtab", ".strtab")
    )
    symbols: list[tuple[str, int, int, int, int, int]] = []
    if with_reset:
        symbols.append(("Reset_Handler", reset_handler, 2, 0x12, 0, 3))
        symbols.append(("main", reset_handler + 4, 2, 0x12, 0, 3))
    for name in undefined:
        symbols.append((name, 0, 0, 0x11, 0, 0))
    for name in weak_undefined:
        symbols.append((name, 0, 0, 0x22, 0, 0))
    strtab, name_offsets = _strtab(tuple(symbols))
    syms = struct.pack(endian + "IIIBBH", 0, 0, 0, 0, 0, 0)
    for index, (name, value, size, info, other, shndx) in enumerate(symbols):
        syms += struct.pack(
            endian + "IIIBBH", name_offsets[index], value, size, info, other, shndx
        )
    n_sections = 6 if isr is not None else 5
    isr_off = 52 + 40 * n_sections
    text_off = isr_off + 0x400
    symtab_off = text_off + 0x10
    strtab_off = symtab_off + len(syms)
    shstr_off = strtab_off + len(strtab)
    specs = [(".shstrtab", 3, 0, 0, shstr_off, len(shstr))]
    if isr is not None:
        specs.append((".isr_vector", 1, 2, isr[1], isr_off, isr[2]))
    specs.append((".text", 1, 6, text[1], text_off, text[2]))
    symtab_index = len(specs)
    specs.append((".symtab", 2, 0, 0, symtab_off, len(syms)))
    strtab_index = len(specs)
    specs.append((".strtab", 3, 0, 0, strtab_off, len(strtab)))
    shdrs = [struct.pack(endian + "IIIIIIIIII", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)]
    for index, (name, typ, flags, addr, off, size) in enumerate(specs):
        link = strtab_index if index == symtab_index else 0
        info = 1 if index == symtab_index else 0
        entsize = 16 if index == symtab_index else 0
        align = 4 if index == symtab_index else 1
        shdrs.append(
            struct.pack(
                endian + "IIIIIIIIII",
                sh_offs[name],
                typ,
                flags,
                addr,
                off,
                size,
                link,
                info,
                align,
                entsize,
            )
        )
    n_sections = len(shdrs)
    shoff = 52
    header = struct.pack(
        endian + "16sHHIIIIIHHHHHH",
        b"\x7fELF" + bytes([1, 1 if little else 2, 1, 0]) + b"\x00" * 8,
        2,
        machine,
        1,
        entry,
        0,
        shoff,
        0x05000000,
        52,
        0,
        0,
        40,
        n_sections,
        1,
    )
    payload = header + b"".join(shdrs)
    payload += b"\x00" * (isr_off - len(payload))
    payload += b"\x00" * 0x400
    payload += b"\x00" * 0x10
    payload += syms + strtab + shstr
    path.write_bytes(payload)


def _write_test_elf64(path: Path, *, entry: int, reset_handler: int, machine: int) -> None:
    endian = "<"
    shstr, sh_offs = _shstrtab((".shstrtab", ".isr_vector", ".text", ".symtab", ".strtab"))
    symbols = (("Reset_Handler", reset_handler, 2, 0x12, 0, 3),)
    strtab, name_offsets = _strtab(symbols)
    syms = struct.pack(endian + "IBBHQQ", 0, 0, 0, 0, 0, 0)
    syms += struct.pack(
        endian + "IBBHQQ", name_offsets[0], 0x12, 0, 3, reset_handler, 2
    )
    n_sections = 6
    isr_off = 64 + 64 * n_sections
    text_off = isr_off + 0x400
    symtab_off = text_off + 0x10
    strtab_off = symtab_off + len(syms)
    shstr_off = strtab_off + len(strtab)
    specs = [(".shstrtab", 3, 0, 0, shstr_off, len(shstr))]
    specs.append((".isr_vector", 1, 2, 0x08000000, isr_off, 0x400))
    specs.append((".text", 1, 6, 0x08000400, text_off, 0x10))
    symtab_index = len(specs)
    specs.append((".symtab", 2, 0, 0, symtab_off, len(syms)))
    strtab_index = len(specs)
    specs.append((".strtab", 3, 0, 0, strtab_off, len(strtab)))
    shdrs = [struct.pack(endian + "IIQQQQIIQQ", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)]
    for index, (name, typ, flags, addr, off, size) in enumerate(specs):
        link = strtab_index if index == symtab_index else 0
        info = 1 if index == symtab_index else 0
        entsize = 24 if index == symtab_index else 0
        align = 4 if index == symtab_index else 1
        shdrs.append(
            struct.pack(
                endian + "IIQQQQIIQQ",
                sh_offs[name],
                typ,
                flags,
                addr,
                off,
                size,
                link,
                info,
                align,
                entsize,
            )
        )
    n_sections = len(shdrs)
    shoff = 64
    header = struct.pack(
        endian + "16sHHIQQQIHHHHHH",
        b"\x7fELF" + bytes([2, 1, 1, 0]) + b"\x00" * 8,
        2,
        machine,
        1,
        entry,
        0,
        shoff,
        0,
        64,
        0,
        0,
        64,
        n_sections,
        1,
    )
    payload = header + b"".join(shdrs)
    payload += b"\x00" * (isr_off - len(payload))
    payload += b"\x00" * 0x400
    payload += b"\x00" * 0x10
    payload += syms + strtab + shstr
    path.write_bytes(payload)


@pytest.fixture
def minimal_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    shutil.copytree(FIXTURE, root)
    return root


def _git(command: str, cwd: Path, *args: str) -> int:
    result = run_process(
        ProcessRequest(argv=("git", command, *args), cwd=cwd, timeout_seconds=15.0)
    )
    return result.returncode if result.returncode is not None else 1


@pytest.fixture
def git_project(minimal_project: Path) -> Path:
    _git("init", minimal_project, "-b", "main")
    _git("add", minimal_project, ".")
    _git(
        "commit",
        minimal_project,
        "-m",
        "initial",
        "-c",
        "user.name=test",
        "-c",
        "user.email=test@example.com",
    )
    return minimal_project


def test_snapshot_is_deterministic_and_input_sensitive(minimal_project: Path):
    model = load_project_model(minimal_project)
    first = snapshot_inputs(minimal_project, model)
    second = snapshot_inputs(minimal_project, model)

    assert first == second
    assert first.sha256 == second.sha256
    assert len(first.sha256) == 64
    assert first.files == (
        InputSnapshotFile(".stm32-project.json", first.files[0].sha256),
        InputSnapshotFile("Src/main.c", first.files[1].sha256),
        InputSnapshotFile("Startup/startup.s", first.files[2].sha256),
    )
    assert [entry.path for entry in first.files] == sorted(entry.path for entry in first.files)

    (minimal_project / "Src" / "main.c").write_text(
        "int main(void) { return 1; }\n", encoding="utf-8"
    )
    changed = snapshot_inputs(minimal_project, model)
    assert changed.sha256 != first.sha256


def test_snapshot_missing_input_raises(minimal_project: Path):
    (minimal_project / "Src" / "main.c").unlink()
    model = load_project_model(minimal_project)

    with pytest.raises(BuildError) as error:
        snapshot_inputs(minimal_project, model)
    assert error.value.code == "BUILD_EVIDENCE_INVALID"
    assert error.value.details == {"path": "Src/main.c", "rule": "missingInput"}


def test_snapshot_oversized_input_raises(minimal_project: Path, monkeypatch):
    monkeypatch.setattr(identity_mod, "_MAX_INPUT_FILE_BYTES", 16)
    (minimal_project / "Src" / "main.c").write_text("x" * 100, encoding="utf-8")
    model = load_project_model(minimal_project)

    with pytest.raises(BuildError) as error:
        snapshot_inputs(minimal_project, model)
    assert error.value.details == {"path": "Src/main.c", "rule": "inputSize"}


def test_snapshot_aggregate_bound_raises(minimal_project: Path, monkeypatch):
    monkeypatch.setattr(identity_mod, "_MAX_INPUT_TOTAL_BYTES", 16)
    model = load_project_model(minimal_project)

    with pytest.raises(BuildError) as error:
        snapshot_inputs(minimal_project, model)
    assert error.value.details == {"rule": "inputSize"}


def test_snapshot_sha256_matches_full_snapshot(minimal_project: Path):
    model = load_project_model(minimal_project)
    full = snapshot_inputs(minimal_project, model)

    aggregate = snapshot_sha256(
        minimal_project,
        (".stm32-project.json", "Src/main.c", "Startup/startup.s"),
    )

    assert aggregate == full.sha256


def test_git_evidence_in_repo(git_project: Path):
    evidence = git_evidence(git_project)

    assert evidence.head is not None
    assert len(evidence.head) == 40
    assert all(ch in "0123456789abcdef" for ch in evidence.head)
    assert evidence.branch == "main"
    assert evidence.target is None


def test_git_evidence_with_origin_target(git_project: Path):
    _git("update-ref", git_project, "refs/remotes/origin/master", git_evidence(git_project).head)
    _git("symbolic-ref", git_project, "refs/remotes/origin/HEAD", "refs/remotes/origin/master")

    evidence = git_evidence(git_project)

    assert evidence.target == "origin/master"


def test_git_evidence_outside_repo(minimal_project: Path):
    evidence = git_evidence(minimal_project)

    assert evidence == GitEvidence(None, None, None)


def test_validate_elf_success(tmp_path: Path):
    elf = tmp_path / "firmware.elf"
    write_test_elf(elf)

    evidence = validate_elf(elf)

    assert evidence == ElfEvidence(
        entry_point=0x08000401,
        isr_vector_present=True,
        reset_handler_present=True,
        reset_handler_address=0x08000401,
        entry_point_consistent=True,
        undefined_symbols=(),
    )


def test_validate_elf_entry_point_mismatch(tmp_path: Path):
    elf = tmp_path / "firmware.elf"
    write_test_elf(elf, entry=0x08000000)

    evidence = validate_elf(elf)

    assert evidence.entry_point == 0x08000000
    assert evidence.entry_point_consistent is False


def test_validate_elf_missing_isr_vector(tmp_path: Path):
    elf = tmp_path / "firmware.elf"
    write_test_elf(elf, with_isr=False)

    evidence = validate_elf(elf)

    assert evidence.isr_vector_present is False


def test_validate_elf_missing_reset_handler(tmp_path: Path):
    elf = tmp_path / "firmware.elf"
    write_test_elf(elf, with_reset=False)

    evidence = validate_elf(elf)

    assert evidence.reset_handler_present is False
    assert evidence.reset_handler_address is None
    assert evidence.entry_point_consistent is False


def test_validate_elf_reports_undefined_non_weak_symbols(tmp_path: Path):
    elf = tmp_path / "firmware.elf"
    write_test_elf(
        elf,
        undefined=("mystery_fn",),
        weak_undefined=("__aeabi_unwind_cpp_pr0",),
    )

    evidence = validate_elf(elf)

    assert evidence.undefined_symbols == ("mystery_fn",)


def test_validate_elf_wrong_machine(tmp_path: Path):
    elf = tmp_path / "firmware.elf"
    write_test_elf(elf, machine=62)

    with pytest.raises(BuildError) as error:
        validate_elf(elf)
    assert error.value.code == "BUILD_EVIDENCE_INVALID"
    assert error.value.details == {"rule": "elfMachine"}


def test_validate_elf_wrong_class(tmp_path: Path):
    elf = tmp_path / "firmware.elf"
    write_test_elf(elf, elfclass=64)

    with pytest.raises(BuildError) as error:
        validate_elf(elf)
    assert error.value.details == {"rule": "elfClass"}


def test_validate_elf_big_endian(tmp_path: Path):
    elf = tmp_path / "firmware.elf"
    write_test_elf(elf, little=False)

    with pytest.raises(BuildError) as error:
        validate_elf(elf)
    assert error.value.details == {"rule": "elfData"}


def test_validate_elf_not_an_elf(tmp_path: Path):
    elf = tmp_path / "firmware.elf"
    elf.write_text("not an elf at all\n", encoding="utf-8")

    with pytest.raises(BuildError) as error:
        validate_elf(elf)
    assert error.value.details == {"rule": "elfFormat"}


def test_validate_elf_missing_file(tmp_path: Path):
    with pytest.raises(BuildError) as error:
        validate_elf(tmp_path / "missing.elf")
    assert error.value.details == {"rule": "missingElf"}


def test_validate_elf_oversized(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(identity_mod, "_MAX_ELF_BYTES", 64)
    elf = tmp_path / "firmware.elf"
    write_test_elf(elf)

    with pytest.raises(BuildError) as error:
        validate_elf(elf)
    assert error.value.details == {"rule": "elfSize"}


def _identity_kwargs(**overrides) -> dict:
    kwargs = dict(
        preset="arm-debug",
        clean_first=False,
        git=GitEvidence("a" * 40, "main", "origin/master"),
        snapshot=InputSnapshot(
            "b" * 64,
            (
                InputSnapshotFile(".stm32-project.json", "c" * 64),
                InputSnapshotFile("Src/main.c", "d" * 64),
            ),
        ),
        elf_path="build/arm-debug/firmware.elf",
        elf_sha256="e" * 64,
        elf_size=1234,
        map_path="build/arm-debug/firmware.map",
        map_sha256="f" * 64,
        map_size=5678,
        elf_evidence=ElfEvidence(
            entry_point=0x08000401,
            isr_vector_present=True,
            reset_handler_present=True,
            reset_handler_address=0x08000401,
            entry_point_consistent=True,
            undefined_symbols=(),
        ),
        memory_usage=(
            MemoryUsage("FLASH", 0x08000000, 0x100000, 0x6D0, 0.17),
            MemoryUsage("RAM", 0x20000000, 0x40000, 0x1618, 2.16),
        ),
        built_at_utc="2026-08-06T06:58:00Z",
    )
    kwargs.update(overrides)
    return kwargs


def test_build_identity_roundtrip_validates_and_is_deterministic():
    identity = build_identity(**_identity_kwargs())
    payload = identity.to_dict()

    assert identity.schema_version == 1
    assert len(identity.build_id) == 64
    assert payload["status"] == "success"
    assert payload["gitHead"] == "a" * 40
    assert payload["elf"] == {
        "path": "build/arm-debug/firmware.elf",
        "sha256": "e" * 64,
        "size": 1234,
    }
    assert payload["entryPoint"] == "0x8000401"
    assert payload["memoryUsage"][1] == {
        "region": "RAM",
        "origin": 0x20000000,
        "length": 0x40000,
        "used": 0x1618,
        "percent": 2.16,
    }
    validate_identity_document(payload)

    again = build_identity(**_identity_kwargs())
    assert again == identity
    assert again.to_dict() == payload


def test_build_id_excludes_schema_build_id_and_timestamp():
    identity = build_identity(**_identity_kwargs())
    moved = build_identity(**_identity_kwargs(built_at_utc="2026-08-07T00:00:00Z"))

    assert moved.build_id == identity.build_id
    assert moved.built_at_utc != identity.built_at_utc


def test_build_id_changes_with_evidence_fields():
    identity = build_identity(**_identity_kwargs())
    changed = build_identity(**_identity_kwargs(preset="arm-release"))

    assert changed.build_id != identity.build_id


def test_identity_paths_are_portable_and_relative():
    payload = build_identity(**_identity_kwargs()).to_dict()

    assert payload["elf"]["path"] == "build/arm-debug/firmware.elf"
    assert payload["map"]["path"] == "build/arm-debug/firmware.map"
    assert "/" in payload["elf"]["path"]


@pytest.mark.parametrize(
    ("mutate", "rule"),
    [
        (lambda p: p.update({"schemaVersion": 2}), "const"),
        (lambda p: p.update({"buildId": "xyz"}), "pattern"),
        (lambda p: p.update({"builtAtUtc": "not-a-date"}), "pattern"),
        (lambda p: p.update({"status": "failure"}), "const"),
        (lambda p: p.update({"gitHead": "short"}), "pattern"),
        (lambda p: p.pop("inputSnapshot"), "required"),
        (lambda p: p["inputSnapshot"].pop("sha256"), "required"),
        (lambda p: p["memoryUsage"].clear(), "minItems"),
        (lambda p: p["elf"].update({"size": 0}), "minimum"),
        (lambda p: p.update({"extra": True}), "additionalProperties"),
        (lambda p: p["undefinedSymbols"].append(""), "minLength"),
    ],
)
def test_identity_schema_rejects_tampering(mutate, rule):
    payload = build_identity(**_identity_kwargs()).to_dict()
    mutate(payload)

    with pytest.raises(BuildError) as error:
        validate_identity_document(payload)
    assert error.value.code == "BUILD_IDENTITY_INVALID"
    assert error.value.details["rule"] == rule


def test_write_json_atomic_roundtrip_no_residue(tmp_path: Path):
    target = tmp_path / "nested" / "identity.json"
    data = {"schemaVersion": 1, "name": "测试", "items": [1, 2]}

    write_json_atomic(target, data)
    loaded = read_json_bounded(target, 4096)

    assert loaded == data
    assert target.read_text(encoding="utf-8").endswith("\n")
    assert json.loads(target.read_text(encoding="utf-8")) == data
    assert sorted(path.name for path in tmp_path.rglob("*")) == [
        "identity.json",
        "nested",
    ]


def test_write_text_atomic_roundtrip(tmp_path: Path):
    target = tmp_path / "build.log"
    write_text_atomic(target, "line one\nline two\n")

    assert target.read_text(encoding="utf-8") == "line one\nline two\n"


def test_write_json_atomic_failure_leaves_no_tmp(tmp_path: Path):
    blocker = tmp_path / "blocker"
    blocker.write_text("file", encoding="utf-8")

    with pytest.raises(OSError):
        write_json_atomic(tmp_path / "blocker" / "identity.json", {"a": 1})

    assert sorted(path.name for path in tmp_path.iterdir()) == ["blocker"]


def test_read_json_bounded_rejects_oversize(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(identity_mod, "_MAX_EVIDENCE_JSON_BYTES", 16)
    target = tmp_path / "identity.json"
    write_json_atomic(target, {"payload": "x" * 100})

    with pytest.raises(BuildError) as error:
        read_json_bounded(target, identity_mod._MAX_EVIDENCE_JSON_BYTES)
    assert error.value.details == {"rule": "size"}


def test_read_json_bounded_rejects_malformed(tmp_path: Path):
    target = tmp_path / "identity.json"
    target.write_text("{not json", encoding="utf-8")

    with pytest.raises(BuildError) as error:
        read_json_bounded(target, 4096)
    assert error.value.details == {"rule": "format"}


def test_read_json_bounded_missing_file(tmp_path: Path):
    with pytest.raises(BuildError) as error:
        read_json_bounded(tmp_path / "missing.json", 4096)
    assert error.value.details == {"rule": "missing"}


def test_schema_root_and_packaged_copies_are_byte_identical():
    assert SCHEMA_ROOT.is_file()
    assert SCHEMA_PACKAGED.is_file()
    assert SCHEMA_ROOT.read_bytes() == SCHEMA_PACKAGED.read_bytes()


def test_packaged_schema_is_valid_against_metaschema():
    import jsonschema

    schema = json.loads(SCHEMA_PACKAGED.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    payload = build_identity(**_identity_kwargs()).to_dict()
    jsonschema.Draft202012Validator(schema).validate(payload)
