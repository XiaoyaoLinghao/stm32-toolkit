"""Input snapshots, Git evidence, ELF validation, identity, and schema tests.

All unreadability is injected as deterministic ``PermissionError`` through
the module's read seam (no ``chmod(0)``, no skip, no xfail), matching the
established toolkit injection pattern.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from stm32_toolkit import __version__
from stm32_toolkit.build import identity as identity_mod
from stm32_toolkit.build.identity import (
    BuildError,
    compute_build_id,
    git_evidence,
    load_packaged_schema,
    snapshot_project_inputs,
    validate_elf,
    validate_identity_document,
)
from stm32_toolkit.build.map_file import MapError
from stm32_toolkit.project_model import load_project_model
from stm32_toolkit.process import ProcessError

from test_build_runner import (
    ELF_DEFECTS,
    FIXTURE_ROOT,
    build_elf_bytes,
    build_map_text,
    git,
    prepare_project,
    read_json,
)


def model_for(root: Path):
    return load_project_model(root)


def snapshot_for(root: Path):
    return snapshot_project_inputs(model_for(root))


def raise_on_open(path: Path, monkeypatch: pytest.MonkeyPatch, error: OSError) -> None:
    """Make ``Path.open`` raise ``error`` for ``path`` (platform-independent)."""
    real_open = Path.open

    def patched(self, mode: str = "r", *args, **kwargs):
        if mode == "rb" and self == path:
            raise error
        return real_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", patched)


def escape_redirect(link: Path, target: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Create an escaping redirect without administrator privileges.

    POSIX uses a real symlink.  Windows simulates the redirect
    deterministically through the module seams so traversal, lstat,
    resolve, and containment all observe the same simulated object: the
    directory enumeration presents the logical link entry, ``lstat``
    reports a symlink mode for it, and ``resolve`` maps it to the
    canonical target.
    """
    if os.name == "nt":
        simulated = {str(link): target}
        real_resolve = Path.resolve
        real_listdir = identity_mod._listdir
        real_lstat = identity_mod._lstat

        def resolve(self, strict: bool = False):
            text = str(self)
            for link_text, resolved in simulated.items():
                if text == link_text:
                    return resolved
                if text.startswith(link_text + os.sep):
                    return real_resolve(resolved / text[len(link_text) + 1 :], strict=strict)
            return real_resolve(self, strict=strict)

        def listdir(path):
            entries = list(real_listdir(path))
            for link_text in simulated:
                link_path = Path(link_text)
                if link_path.parent == Path(path) and link_path.name not in entries:
                    entries.append(link_path.name)
            return entries

        def fake_lstat(path):
            if Path(path) == link:
                return os.stat_result((0o120000, 0, 0, 0, 0, 0, 0, 0, 0, 0))
            return real_lstat(path)

        monkeypatch.setattr(Path, "resolve", resolve)
        monkeypatch.setattr(identity_mod, "_listdir", listdir)
        monkeypatch.setattr(identity_mod, "_lstat", fake_lstat)
    else:
        link.symlink_to(target)


# ---------------------------------------------------------------------------
# input snapshot
# ---------------------------------------------------------------------------


def test_snapshot_includes_manifest_sources_assembly_and_generated_files(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    snapshot = snapshot_for(root)
    paths = {entry.path for entry in snapshot.entries}
    assert ".stm32-project.json" in paths
    assert "Src/main.c" in paths
    assert "Startup/startup.s" in paths
    assert "CMakeLists.txt" in paths
    assert "CMakePresets.json" in paths
    assert "linker/stm32tk.ld" in paths
    assert "cmake/arm-none-eabi-gcc.cmake" in paths
    assert ".stm32-toolkit/generated-files.json" not in paths
    assert len(snapshot.entries) == len(paths)


def test_snapshot_hash_is_canonical_and_excludes_mtimes(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    first = snapshot_for(root)
    source = root / "Src" / "main.c"
    os.utime(source, ns=(2_000_000_000_000_000_000, 2_000_000_000_000_000_000))
    second = snapshot_for(root)
    assert first.sha256 == second.sha256
    assert first.newest_mtime_ns != second.newest_mtime_ns
    expected = identity_mod.sha256_hex(
        identity_mod.canonical_json_bytes(
            [
                {"path": entry.path, "size": entry.size, "sha256": entry.sha256}
                for entry in sorted(first.entries, key=lambda item: item.path)
            ]
        )
    )
    assert first.sha256 == expected
    assert first.newest_mtime_ns >= max(entry.mtime_ns for entry in first.entries)


def test_snapshot_recurses_include_directories_sorted(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    (root / "Inc").mkdir()
    (root / "Inc" / "b.h").write_text("b\n", encoding="utf-8")
    (root / "Inc" / "sub").mkdir()
    (root / "Inc" / "sub" / "a.h").write_text("a\n", encoding="utf-8")
    payload = json.loads((root / ".stm32-project.json").read_text(encoding="utf-8"))
    payload["build"]["includePaths"] = ["Inc"]
    (root / ".stm32-project.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    snapshot = snapshot_for(root)
    paths = [entry.path for entry in snapshot.entries]
    assert "Inc/b.h" in paths
    assert "Inc/sub/a.h" in paths
    assert paths == sorted(paths)


def test_snapshot_rejects_escaping_symlink(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path, git_repo=False)
    (root / "Inc").mkdir()
    outside = tmp_path / "outside.h"
    outside.write_text("x\n", encoding="utf-8")
    escape_redirect(root / "Inc" / "escape.h", outside, monkeypatch)
    payload = json.loads((root / ".stm32-project.json").read_text(encoding="utf-8"))
    payload["build"]["includePaths"] = ["Inc"]
    (root / ".stm32-project.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(BuildError) as error:
        snapshot_for(root)
    assert error.value.code == "BUILD_INPUT_INVALID"
    assert error.value.details["rule"] == "escape"


def test_snapshot_rejects_unreadable_file(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path, git_repo=False)
    raise_on_open(root / "Src" / "main.c", monkeypatch, PermissionError("injected"))
    with pytest.raises(BuildError) as error:
        snapshot_for(root)
    assert error.value.code == "BUILD_INPUT_INVALID"
    assert error.value.details == {"path": "Src/main.c", "rule": "unreadable"}


def test_snapshot_rejects_oversized_file(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path, git_repo=False)
    monkeypatch.setattr(identity_mod, "_FILE_LIMIT_BYTES", 4)
    with pytest.raises(BuildError) as error:
        snapshot_for(root)
    assert error.value.code == "BUILD_INPUT_INVALID"
    assert error.value.details["rule"] == "size"


def test_snapshot_rejects_file_count_limit(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path, git_repo=False)
    monkeypatch.setattr(identity_mod, "_FILE_LIMIT_COUNT", 2)
    with pytest.raises(BuildError) as error:
        snapshot_for(root)
    assert error.value.code == "BUILD_INPUT_INVALID"
    assert error.value.details == {"rule": "fileCount"}


def test_snapshot_rejects_aggregate_limit(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path, git_repo=False)
    monkeypatch.setattr(identity_mod, "_AGGREGATE_LIMIT_BYTES", 16)
    with pytest.raises(BuildError) as error:
        snapshot_for(root)
    assert error.value.code == "BUILD_INPUT_INVALID"
    assert error.value.details == {"rule": "aggregate"}


def test_snapshot_rejects_casefold_collision(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path, git_repo=False)
    inc_dir = root / "Inc"
    inc_dir.mkdir()
    # One physical file: on case-insensitive filesystems (NTFS) a second
    # case-only-different file cannot be created, so the collision is built
    # through a controllable directory-enumeration seam that presents both
    # logical paths to the walk.
    (inc_dir / "Board.H").write_text("x\n", encoding="utf-8")
    payload = json.loads((root / ".stm32-project.json").read_text(encoding="utf-8"))
    payload["build"]["includePaths"] = ["Inc"]
    (root / ".stm32-project.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    real_listdir = identity_mod._listdir
    real_lstat = identity_mod._lstat
    physical = inc_dir / "Board.H"
    virtual = inc_dir / "board.h"

    def collide_listdir(path):
        entries = list(real_listdir(path))
        if Path(path) == inc_dir and "board.h" not in entries:
            entries.append("board.h")
        return entries

    def collide_lstat(path):
        if Path(path) == virtual:
            return real_lstat(physical)
        return real_lstat(path)

    monkeypatch.setattr(identity_mod, "_listdir", collide_listdir)
    monkeypatch.setattr(identity_mod, "_lstat", collide_lstat)
    with pytest.raises(BuildError) as error:
        snapshot_for(root)
    assert error.value.code == "BUILD_INPUT_INVALID"
    assert error.value.details == {"path": "Inc/board.h", "rule": "collision"}


def test_snapshot_rejects_duplicate_path(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    payload = json.loads((root / ".stm32-project.json").read_text(encoding="utf-8"))
    payload["build"]["sources"] = ["Src/main.c", "CMakeLists.txt"]
    (root / ".stm32-project.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(BuildError) as error:
        snapshot_for(root)
    assert error.value.code == "BUILD_INPUT_INVALID"
    assert error.value.details == {"rule": "duplicate"}


def test_snapshot_rejects_sources_inside_build_outputs(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    payload = json.loads((root / ".stm32-project.json").read_text(encoding="utf-8"))
    payload["build"]["sources"] = ["build/arm-debug/generated.c"]
    (root / ".stm32-project.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(BuildError) as error:
        snapshot_for(root)
    assert error.value.code == "BUILD_INPUT_INVALID"
    assert error.value.details == {"path": "build/arm-debug/generated.c", "rule": "reserved"}


def test_snapshot_rejects_sources_inside_artifacts_migration(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    payload = json.loads((root / ".stm32-project.json").read_text(encoding="utf-8"))
    payload["build"]["sources"] = ["artifacts/migration/generated.c"]
    (root / ".stm32-project.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(BuildError) as error:
        snapshot_for(root)
    assert error.value.code == "BUILD_INPUT_INVALID"
    assert error.value.details == {"path": "artifacts/migration/generated.c", "rule": "reserved"}


def test_snapshot_rejects_special_files(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path, git_repo=False)
    (root / "Inc").mkdir()
    (root / "Inc" / "fifo").write_text("x\n", encoding="utf-8")
    payload = json.loads((root / ".stm32-project.json").read_text(encoding="utf-8"))
    payload["build"]["includePaths"] = ["Inc"]
    (root / ".stm32-project.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    real_lstat = identity_mod._lstat

    def fake_lstat(path):
        if Path(path).name == "fifo":
            return os.stat_result((0o020000, 0, 0, 0, 0, 0, 0, 0, 0, 0))
        return real_lstat(path)

    monkeypatch.setattr(identity_mod, "_lstat", fake_lstat)
    with pytest.raises(BuildError) as error:
        snapshot_for(root)
    assert error.value.code == "BUILD_INPUT_INVALID"
    assert error.value.details == {"path": "Inc/fifo", "rule": "regularFile"}


# ---------------------------------------------------------------------------
# git evidence
# ---------------------------------------------------------------------------


def test_git_evidence_clean_and_dirty(tmp_path: Path):
    root = prepare_project(tmp_path)
    evidence = git_evidence(root)
    assert len(evidence.head) == 40
    assert evidence.dirty is False
    (root / "Src" / "main.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
    evidence = git_evidence(root)
    assert evidence.dirty is True
    assert evidence.head == git_evidence(root).head


def test_git_evidence_detached_head(tmp_path: Path):
    root = prepare_project(tmp_path)
    git("checkout", "-q", "--detach", cwd=root)
    evidence = git_evidence(root)
    assert len(evidence.head) == 40
    assert evidence.dirty is False


def test_git_evidence_non_repository(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    with pytest.raises(BuildError) as error:
        git_evidence(root)
    assert error.value.code == "BUILD_GIT_INVALID"
    assert error.value.details == {"rule": "head"}


def test_git_evidence_excludes_build_outputs_from_dirty(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path)
    (root / "build").mkdir(parents=True)
    (root / "build" / "arm-debug").mkdir()
    (root / "build" / "arm-debug" / "firmware.elf").write_bytes(b"out")
    (root / "artifacts" / "migration").mkdir(parents=True)
    (root / "artifacts" / "migration" / "build-result.json").write_text("{}", encoding="utf-8")
    assert git_evidence(root).dirty is False


# ---------------------------------------------------------------------------
# ELF validation
# ---------------------------------------------------------------------------


def test_validate_elf_accepts_the_valid_image(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    model = model_for(root)
    elf_path = root / "firmware.elf"
    elf_path.write_bytes(build_elf_bytes())
    evidence = validate_elf(elf_path, model)
    assert evidence.entry_point == 0x08000011
    assert evidence.vector_address == 0x08000000
    assert evidence.reset_handler_address == 0x08000011
    assert evidence.size == elf_path.stat().st_size
    assert evidence.sha256 == identity_mod.sha256_hex(elf_path.read_bytes())


def test_validate_elf_accepts_fixed_section_at_encoded_address(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    model = model_for(root)
    elf_path = root / "firmware.elf"
    elf_path.write_bytes(
        build_elf_bytes(fixed_sections=((".stm32tk.abs.20000000", 0x20000000, 16),))
    )
    evidence = validate_elf(elf_path, model)
    assert evidence.sha256


def test_validate_elf_evidence_classifies_alloc_and_non_alloc_sections(tmp_path: Path):
    """ELF section evidence carries name, address, size, and SHF_ALLOC so
    MAP accounting can classify every output section from ELF flags."""
    root = prepare_project(tmp_path, git_repo=False)
    model = model_for(root)
    elf_path = root / "firmware.elf"
    elf_path.write_bytes(
        build_elf_bytes(
            nonalloc_sections=((".debug_info", 0x0, 0x1A2),),
            alloc_sections=((".rodata", 0x08000040, 0x100, 0x2),),
        )
    )
    evidence = validate_elf(elf_path, model)
    by_name = {section.name: section for section in evidence.sections}
    assert by_name[".isr_vector"].alloc is True
    assert by_name[".isr_vector"].address == 0x08000000
    assert by_name[".isr_vector"].size == 64
    assert by_name[".text"].alloc is True
    assert by_name[".rodata"].alloc is True
    assert by_name[".data"].alloc is True
    assert by_name[".bss"].alloc is True
    assert by_name[".debug_info"].alloc is False
    assert by_name[".debug_info"].address == 0
    assert by_name[".symtab"].alloc is False
    with pytest.raises(AttributeError):
        by_name[".text"].size = 1  # type: ignore[misc]


@pytest.mark.parametrize(
    ("defect", "rule"),
    [
        ("wrong-class", "class"),
        ("wrong-endian", "endian"),
        ("wrong-machine", "machine"),
        ("no-vector", "vector"),
        ("short-vector", "vectorSize"),
        ("reset-undefined", "resetHandlerUndefined"),
        ("no-symtab", "symbols"),
        ("undef-global", "undefinedSymbols"),
        ("entry-mismatch", "entry"),
        ("entry-even", "entryThumb"),
        ("vector-mismatch", "vectorReset"),
        ("alloc-escape", "sectionOutOfRange"),
        ("fixed-mismatch", "fixedSectionAddress"),
        ("vector-noalloc", "vectorAlloc"),
        ("vector-addr", "vectorRegion"),
        ("no-reset", "resetHandler"),
        ("truncated", "format"),
    ],
)
def test_validate_elf_rejects_defective_images(tmp_path: Path, defect: str, rule: str):
    root = prepare_project(tmp_path, git_repo=False)
    model = model_for(root)
    elf_path = root / "firmware.elf"
    elf_path.write_bytes(build_elf_bytes(**ELF_DEFECTS[defect]))
    with pytest.raises(BuildError) as error:
        validate_elf(elf_path, model)
    assert error.value.code == "BUILD_ARTIFACT_INVALID"
    assert error.value.details == {"path": "firmware.elf", "rule": rule}


def test_validate_elf_rejects_empty_file(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    elf_path = root / "firmware.elf"
    elf_path.write_bytes(b"")
    with pytest.raises(BuildError) as error:
        validate_elf(elf_path, model_for(root))
    assert error.value.details["rule"] == "empty"


def test_validate_elf_rejects_unreadable_file(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path, git_repo=False)
    elf_path = root / "firmware.elf"
    elf_path.write_bytes(build_elf_bytes())
    raise_on_open(elf_path, monkeypatch, PermissionError("injected"))
    with pytest.raises(BuildError) as error:
        validate_elf(elf_path, model_for(root))
    assert error.value.details == {"path": "firmware.elf", "rule": "unreadable"}


def test_validate_elf_rejects_oversized_file(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path, git_repo=False)
    elf_path = root / "firmware.elf"
    elf_path.write_bytes(build_elf_bytes())
    monkeypatch.setattr(identity_mod, "_ELF_LIMIT_BYTES", 16)
    with pytest.raises(BuildError) as error:
        validate_elf(elf_path, model_for(root))
    assert error.value.details["rule"] == "size"


def test_validate_elf_missing_file(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    with pytest.raises(BuildError) as error:
        validate_elf(root / "missing.elf", model_for(root))
    assert error.value.details == {"path": "missing.elf", "rule": "missing"}


# ---------------------------------------------------------------------------
# identity construction and schema
# ---------------------------------------------------------------------------


def _identity_document(root: Path, preset: str = "arm-debug", built_at_utc: str = "2026-08-06T08:00:00.000000Z") -> dict:
    model = model_for(root)
    snapshot = snapshot_project_inputs(model)
    evidence = git_evidence(root)
    elf_path = root / "build" / preset / "firmware.elf"
    elf_path.parent.mkdir(parents=True, exist_ok=True)
    elf_path.write_bytes(build_elf_bytes())
    elf = validate_elf(elf_path, model)
    return identity_mod.build_identity_document(
        model=model,
        preset=preset,
        git=evidence,
        snapshot=snapshot,
        elf=elf,
        elf_size=elf.size,
        elf_sha256=elf.sha256,
        map_size=0x1000,
        map_sha256="a" * 64,
        built_at_utc=built_at_utc,
    )


def test_identity_document_key_order_and_fields(tmp_path: Path):
    root = prepare_project(tmp_path)
    document = _identity_document(root)
    assert list(document) == [
        "schemaVersion",
        "buildId",
        "logicalProjectId",
        "toolkitVersion",
        "gitHead",
        "gitDirty",
        "inputSnapshotSha256",
        "newestInputMtimeNs",
        "targetDevice",
        "preset",
        "elfPath",
        "elfSha256",
        "elfSize",
        "mapPath",
        "mapSha256",
        "entryPoint",
        "vectorAddress",
        "resetHandlerAddress",
        "builtAtUtc",
    ]
    assert document["schemaVersion"] == 1
    assert document["toolkitVersion"] == __version__
    assert document["targetDevice"] == "STM32F407VGTx"
    assert document["preset"] == "arm-debug"
    assert document["elfPath"] == "build/arm-debug/firmware.elf"
    assert document["mapPath"] == "build/arm-debug/firmware.map"
    assert document["newestInputMtimeNs"] >= 0
    validate_identity_document(document)


def test_build_id_excludes_schema_build_id_and_timestamp(tmp_path: Path):
    root = prepare_project(tmp_path)
    document_a = _identity_document(root, built_at_utc="2026-08-06T08:00:00.000000Z")
    document_b = _identity_document(root, built_at_utc="2026-08-06T09:00:00.000000Z")
    assert document_a["buildId"] == document_b["buildId"]
    assert document_a["builtAtUtc"] != document_b["builtAtUtc"]
    rebuilt = compute_build_id(document_a)
    assert rebuilt == document_a["buildId"]
    without_meta = {
        key: value for key, value in document_a.items()
        if key not in ("schemaVersion", "buildId", "builtAtUtc")
    }
    expected = identity_mod.sha256_hex(identity_mod.canonical_json_bytes(without_meta))
    assert document_a["buildId"] == expected


def test_identity_release_preset_uses_release_paths(tmp_path: Path):
    root = prepare_project(tmp_path)
    document = _identity_document(root, preset="arm-release")
    assert document["preset"] == "arm-release"
    assert document["elfPath"] == "build/arm-release/firmware.elf"
    assert document["mapPath"] == "build/arm-release/firmware.map"
    validate_identity_document(document)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda doc: doc.pop("buildId"),
        lambda doc: doc.__setitem__("extra", 1),
        lambda doc: doc.__setitem__("schemaVersion", 2),
        lambda doc: doc.__setitem__("gitHead", "xyz"),
        lambda doc: doc.__setitem__("preset", "arm-host"),
        lambda doc: doc.__setitem__("elfPath", "/abs/elf"),
        lambda doc: doc.__setitem__("elfSha256", "not-a-hash"),
        lambda doc: doc.__setitem__("builtAtUtc", "2026-08-06T08:00:00"),
        lambda doc: doc.__setitem__("newestInputMtimeNs", -1),
        lambda doc: doc.__setitem__("gitDirty", 1),
    ],
)
def test_schema_rejects_invalid_documents(tmp_path: Path, mutator):
    root = prepare_project(tmp_path)
    document = _identity_document(root)
    mutator(document)
    with pytest.raises(BuildError) as error:
        validate_identity_document(document)
    assert error.value.code == "BUILD_EVIDENCE_FAILED"


def test_root_and_packaged_schemas_are_byte_identical(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[3]
    root_schema = (repo_root / "schemas" / "firmware-identity.schema.json").read_bytes()
    packaged = identity_mod.load_packaged_schema_bytes()
    assert packaged == root_schema
    assert json.loads(packaged.decode("utf-8")) == load_packaged_schema()


# ---------------------------------------------------------------------------
# atomic evidence helpers
# ---------------------------------------------------------------------------


def test_atomic_write_json_uses_exact_json_contract(tmp_path: Path):
    target = tmp_path / "nested" / "doc.json"
    identity_mod.atomic_write_json(target, {"b": 1, "a": {"c": "中文"}})
    raw = target.read_bytes()
    assert raw.startswith(b"{")
    assert raw.endswith(b"\n")
    assert b"\r" not in raw
    assert not raw.startswith(b"\xef\xbb\xbf")
    payload = json.loads(raw.decode("utf-8"))
    assert payload == {"b": 1, "a": {"c": "中文"}}
    assert "中文" in raw.decode("utf-8")


def test_atomic_write_text_normalizes_newlines(tmp_path: Path):
    target = tmp_path / "log.txt"
    identity_mod.atomic_write_text(target, "a\r\nb\rc\n")
    assert target.read_text(encoding="utf-8") == "a\nb\nc\n"


def test_atomic_write_replaces_existing_file(tmp_path: Path):
    target = tmp_path / "doc.json"
    target.write_text("old", encoding="utf-8")
    identity_mod.atomic_write_json(target, {"new": True})
    assert read_json(target) == {"new": True}


def test_atomic_write_cleans_temp_and_preserves_original_on_failure(tmp_path: Path, monkeypatch):
    target = tmp_path / "doc.json"
    target.write_text("original", encoding="utf-8")
    real_replace = identity_mod._replace

    def failing_replace(src, dst):
        raise OSError("injected replace failure")

    monkeypatch.setattr(identity_mod, "_replace", failing_replace)
    with pytest.raises(OSError):
        identity_mod.atomic_write_json(target, {"x": 1})
    assert target.read_text(encoding="utf-8") == "original"
    assert [path for path in tmp_path.iterdir() if ".tmp" in path.name] == []


def test_atomic_write_fsync_failure_propagates(tmp_path: Path, monkeypatch):
    target = tmp_path / "doc.json"
    real_fsync = identity_mod._fsync_file

    def failing_fsync(fd):
        raise OSError("injected fsync failure")

    monkeypatch.setattr(identity_mod, "_fsync_file", failing_fsync)
    with pytest.raises(OSError):
        identity_mod.atomic_write_json(target, {"x": 1})
    assert not target.exists()
    assert [path for path in tmp_path.iterdir() if ".tmp" in path.name] == []


def test_atomic_write_directory_fsync_failure_propagates(tmp_path: Path, monkeypatch):
    target = tmp_path / "doc.json"

    def failing_sync_directory(path):
        raise OSError("injected directory fsync failure")

    monkeypatch.setattr(identity_mod, "_sync_directory", failing_sync_directory)
    with pytest.raises(OSError):
        identity_mod.atomic_write_json(target, {"x": 1})
    assert [path for path in tmp_path.iterdir() if ".tmp" in path.name] == []


def test_parse_map_rejects_missing_map_file(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    with pytest.raises(MapError) as error:
        identity_mod.read_map_text(root / "missing.map", "missing.map")
    assert error.value.code == "BUILD_MAP_INVALID"
    assert error.value.details == {"path": "missing.map", "rule": "missing"}


def test_map_text_oversized_is_rejected(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path, git_repo=False)
    map_path = root / "firmware.map"
    map_path.write_text(build_map_text())
    monkeypatch.setattr(identity_mod, "_MAP_LIMIT_BYTES", 16)
    with pytest.raises(MapError) as error:
        identity_mod.read_map_text(map_path, "firmware.map")
    assert error.value.code == "BUILD_MAP_INVALID"
    assert error.value.details == {"path": "firmware.map", "rule": "size"}


# ---------------------------------------------------------------------------
# coverage closure: snapshot, git, ELF, schema, atomic helpers
# ---------------------------------------------------------------------------


def test_snapshot_rejects_missing_managed_manifest(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    (root / ".stm32-toolkit" / "generated-files.json").unlink()
    with pytest.raises(BuildError) as error:
        snapshot_for(root)
    assert error.value.code == "BUILD_INPUT_INVALID"
    assert error.value.details == {
        "path": ".stm32-toolkit/generated-files.json",
        "rule": "missing",
    }


def test_snapshot_rejects_malformed_managed_manifest(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    (root / ".stm32-toolkit" / "generated-files.json").write_bytes(b"{broken")
    with pytest.raises(BuildError) as error:
        snapshot_for(root)
    assert error.value.code == "BUILD_PROJECT_INVALID"
    assert error.value.details == {
        "path": ".stm32-toolkit/generated-files.json",
        "rule": "json",
    }


def test_snapshot_rejects_oversized_source_file(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path, git_repo=False)
    real_read = identity_mod._read_limited

    def selective(path, limit):
        if Path(path).name == "main.c":
            return b"x" * (limit + 1)
        return real_read(path, limit)

    monkeypatch.setattr(identity_mod, "_read_limited", selective)
    with pytest.raises(BuildError) as error:
        snapshot_for(root)
    assert error.value.code == "BUILD_INPUT_INVALID"
    assert error.value.details == {"path": "Src/main.c", "rule": "size"}


def test_snapshot_rejects_escaping_declared_source(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path, git_repo=False)
    model = model_for(root)  # the model is loaded before the redirect exists
    outside = tmp_path / "outside.c"
    outside.write_text("int main(void) { return 0; }\n", encoding="utf-8")
    (root / "Src" / "main.c").unlink()
    escape_redirect(root / "Src" / "main.c", outside, monkeypatch)
    with pytest.raises(BuildError) as error:
        snapshot_project_inputs(model)
    assert error.value.code == "BUILD_INPUT_INVALID"
    assert error.value.details == {"path": "Src/main.c", "rule": "escape"}


def test_snapshot_rejects_directory_as_declared_source(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    (root / "Src" / "main.c").unlink()
    (root / "Src" / "main.c").mkdir()
    with pytest.raises(BuildError) as error:
        snapshot_for(root)
    assert error.value.code == "BUILD_INPUT_INVALID"
    assert error.value.details == {"path": "Src/main.c", "rule": "regularFile"}


def test_snapshot_accepts_in_root_symlinked_header(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path, git_repo=False)
    (root / "Inc").mkdir()
    (root / "Inc" / "real.h").write_text("x\n", encoding="utf-8")
    escape_redirect(root / "Inc" / "link.h", root / "Inc" / "real.h", monkeypatch)
    payload = json.loads((root / ".stm32-project.json").read_text(encoding="utf-8"))
    payload["build"]["includePaths"] = ["Inc"]
    (root / ".stm32-project.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    snapshot = snapshot_for(root)
    paths = {entry.path for entry in snapshot.entries}
    assert "Inc/link.h" in paths
    assert "Inc/real.h" in paths


def test_snapshot_rejects_include_directory_escape(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path, git_repo=False)
    payload = json.loads((root / ".stm32-project.json").read_text(encoding="utf-8"))
    payload["build"]["includePaths"] = ["Inc"]
    (root / ".stm32-project.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    model = model_for(root)  # the model is loaded before the redirect exists
    outside = tmp_path / "outside-dir"
    outside.mkdir()
    (outside / "x.h").write_text("x\n", encoding="utf-8")
    escape_redirect(root / "Inc", outside, monkeypatch)
    with pytest.raises(BuildError) as error:
        snapshot_project_inputs(model)
    assert error.value.code == "BUILD_INPUT_INVALID"
    assert error.value.details == {"path": "Inc", "rule": "escape"}


def test_snapshot_rejects_redirect_loop(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path, git_repo=False)
    inc_dir = root / "Inc"
    inc_dir.mkdir()
    payload = json.loads((root / ".stm32-project.json").read_text(encoding="utf-8"))
    payload["build"]["includePaths"] = ["Inc"]
    (root / ".stm32-project.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    loop_link = inc_dir / "loop.h"
    if os.name == "nt":
        # Deterministic loop simulation: resolve raises for the link, lstat
        # reports a symlink, and the enumeration presents the logical entry.
        real_resolve = Path.resolve

        def resolve(self, strict: bool = False):
            if str(self) == str(loop_link):
                raise RuntimeError("symlink loop")
            return real_resolve(self, strict=strict)

        monkeypatch.setattr(Path, "resolve", resolve)
        real_listdir = identity_mod._listdir

        def listdir(path):
            entries = list(real_listdir(path))
            if Path(path) == inc_dir and "loop.h" not in entries:
                entries.append("loop.h")
            return entries

        monkeypatch.setattr(identity_mod, "_listdir", listdir)
        real_lstat = identity_mod._lstat

        def fake_lstat(path):
            if Path(path) == loop_link:
                return os.stat_result((0o120000, 0, 0, 0, 0, 0, 0, 0, 0, 0))
            return real_lstat(path)

        monkeypatch.setattr(identity_mod, "_lstat", fake_lstat)
    else:
        loop_link.symlink_to("loop.h")  # self-referential redirect loop
    with pytest.raises(BuildError) as error:
        snapshot_for(root)
    assert error.value.code == "BUILD_INPUT_INVALID"
    assert error.value.details == {"path": "Inc/loop.h", "rule": "escape"}


def test_snapshot_rejects_unreadable_include_dir(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path, git_repo=False)
    (root / "Inc").mkdir()
    payload = json.loads((root / ".stm32-project.json").read_text(encoding="utf-8"))
    payload["build"]["includePaths"] = ["Inc"]
    (root / ".stm32-project.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    real_lstat = identity_mod._lstat

    def fake_lstat(path):
        if Path(path).name == "Inc":
            raise PermissionError("injected")
        return real_lstat(path)

    monkeypatch.setattr(identity_mod, "_lstat", fake_lstat)
    with pytest.raises(BuildError) as error:
        snapshot_for(root)
    assert error.value.details == {"path": "Inc", "rule": "inspection"}


def test_snapshot_rejects_include_path_that_is_a_file(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    payload = json.loads((root / ".stm32-project.json").read_text(encoding="utf-8"))
    payload["build"]["includePaths"] = ["Src/main.c"]
    (root / ".stm32-project.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(BuildError) as error:
        snapshot_for(root)
    assert error.value.details == {"path": "Src/main.c", "rule": "directory"}


def test_snapshot_rejects_reserved_include_dir(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    payload = json.loads((root / ".stm32-project.json").read_text(encoding="utf-8"))
    payload["build"]["includePaths"] = ["build/arm-debug"]
    (root / ".stm32-project.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(BuildError) as error:
        snapshot_for(root)
    assert error.value.details == {"path": "build/arm-debug", "rule": "reserved"}


def test_snapshot_rejects_duplicate_include_dir(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    (root / "Inc").mkdir()
    (root / "Inc" / "a.h").write_text("a\n", encoding="utf-8")
    payload = json.loads((root / ".stm32-project.json").read_text(encoding="utf-8"))
    payload["build"]["includePaths"] = ["Inc", "Inc"]
    (root / ".stm32-project.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(BuildError) as error:
        snapshot_for(root)
    assert error.value.details == {"rule": "duplicate"}


def test_snapshot_rejects_unreadable_include_child(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path, git_repo=False)
    (root / "Inc").mkdir()
    (root / "Inc" / "a.h").write_text("a\n", encoding="utf-8")
    payload = json.loads((root / ".stm32-project.json").read_text(encoding="utf-8"))
    payload["build"]["includePaths"] = ["Inc"]
    (root / ".stm32-project.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    real_lstat = identity_mod._lstat

    def fake_lstat(path):
        if Path(path).name == "a.h":
            raise PermissionError("injected")
        return real_lstat(path)

    monkeypatch.setattr(identity_mod, "_lstat", fake_lstat)
    with pytest.raises(BuildError) as error:
        snapshot_for(root)
    assert error.value.details == {"path": "Inc/a.h", "rule": "inspection"}


def test_snapshot_rejects_include_listing_failure(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path, git_repo=False)
    (root / "Inc").mkdir()
    payload = json.loads((root / ".stm32-project.json").read_text(encoding="utf-8"))
    payload["build"]["includePaths"] = ["Inc"]
    (root / ".stm32-project.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def fake_listdir(path):
        raise PermissionError("injected")

    monkeypatch.setattr(identity_mod, "_listdir", fake_listdir)
    with pytest.raises(BuildError) as error:
        snapshot_for(root)
    assert error.value.details == {"path": "Inc", "rule": "inspection"}


def test_snapshot_hash_pass_rejects_special_file_race(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path, git_repo=False)
    (root / "Inc").mkdir()
    (root / "Inc" / "fifo").write_text("x\n", encoding="utf-8")
    payload = json.loads((root / ".stm32-project.json").read_text(encoding="utf-8"))
    payload["build"]["includePaths"] = ["Inc"]
    (root / ".stm32-project.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    real_lstat = identity_mod._lstat
    counts: dict[str, int] = {}

    def fake_lstat(path):
        name = Path(path).name
        counts[name] = counts.get(name, 0) + 1
        if name == "fifo" and counts[name] > 1:
            return os.stat_result((0o020000, 0, 0, 0, 0, 0, 0, 0, 0, 0))
        return real_lstat(path)

    monkeypatch.setattr(identity_mod, "_lstat", fake_lstat)
    with pytest.raises(BuildError) as error:
        snapshot_for(root)
    assert error.value.details == {"path": "Inc/fifo", "rule": "regularFile"}


def test_snapshot_hash_pass_rejects_missing_race(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path, git_repo=False)
    real_lstat = identity_mod._lstat
    counts: dict[str, int] = {}

    def fake_lstat(path):
        name = Path(path).name
        counts[name] = counts.get(name, 0) + 1
        if name == "main.c" and counts[name] > 1:
            raise FileNotFoundError()
        return real_lstat(path)

    monkeypatch.setattr(identity_mod, "_lstat", fake_lstat)
    with pytest.raises(BuildError) as error:
        snapshot_for(root)
    assert error.value.details == {"path": "Src/main.c", "rule": "missing"}


def test_walk_depth_escape_is_rejected(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    with pytest.raises(BuildError) as error:
        identity_mod._walk_include(root, "Inc", [], depth=65)
    assert error.value.details == {"path": "Inc", "rule": "escape"}


def test_require_input_path_rejects_non_portable_path(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    with pytest.raises(BuildError) as error:
        identity_mod._require_input_path(root, "../escape.c", [])
    assert error.value.details == {"path": "../escape.c", "rule": "portable"}


def test_git_evidence_spawn_failure_is_stable(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path)

    def failing(request):
        raise ProcessError("launch", "boom")

    monkeypatch.setattr(identity_mod, "run_process", failing)
    with pytest.raises(BuildError) as error:
        git_evidence(root)
    assert error.value.code == "BUILD_GIT_INVALID"
    assert error.value.details == {"rule": "head"}


def test_git_evidence_status_nonzero_is_stable(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path)
    real_run = identity_mod.run_process

    def selective(request):
        if "status" in request.argv:
            from stm32_toolkit.process import ProcessResult

            return ProcessResult(1, "", "", False, 0, False, False)
        return real_run(request)

    monkeypatch.setattr(identity_mod, "run_process", selective)
    with pytest.raises(BuildError) as error:
        git_evidence(root)
    assert error.value.details == {"rule": "status"}


def test_read_map_text_unreadable_is_rejected(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path, git_repo=False)
    map_path = root / "firmware.map"
    map_path.write_text(build_map_text())
    real_read = identity_mod._read_limited

    def selective(path, limit):
        if Path(path).name == "firmware.map":
            raise PermissionError("injected")
        return real_read(path, limit)

    monkeypatch.setattr(identity_mod, "_read_limited", selective)
    with pytest.raises(MapError) as error:
        identity_mod.read_map_text(map_path, "firmware.map")
    assert error.value.details == {"path": "firmware.map", "rule": "unreadable"}


def test_read_map_text_bad_encoding_is_rejected(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    map_path = root / "firmware.map"
    map_path.write_bytes(b"\xff\xfe\x00not a map")
    with pytest.raises(MapError) as error:
        identity_mod.read_map_text(map_path, "firmware.map")
    assert error.value.details == {"path": "firmware.map", "rule": "encoding"}


def test_validate_elf_lstat_failure_is_unreadable(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path, git_repo=False)
    elf_path = root / "firmware.elf"
    elf_path.write_bytes(build_elf_bytes())
    real_lstat = identity_mod._lstat

    def fake_lstat(path):
        if Path(path).name == "firmware.elf":
            raise PermissionError("injected")
        return real_lstat(path)

    monkeypatch.setattr(identity_mod, "_lstat", fake_lstat)
    with pytest.raises(BuildError) as error:
        validate_elf(elf_path, model_for(root))
    assert error.value.details == {"path": "firmware.elf", "rule": "unreadable"}


def test_validate_elf_directory_is_not_regular(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    elf_path = root / "firmware.elf"
    elf_path.mkdir()
    with pytest.raises(BuildError) as error:
        validate_elf(elf_path, model_for(root))
    assert error.value.details == {"path": "firmware.elf", "rule": "regularFile"}


def test_identity_validator_breakdown_is_stable(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path)
    document = _identity_document(root)

    def broken():
        raise RuntimeError("injected validator failure")

    monkeypatch.setattr(identity_mod, "_identity_validator", broken)
    with pytest.raises(BuildError) as error:
        validate_identity_document(document)
    assert error.value.code == "BUILD_EVIDENCE_FAILED"


def test_read_evidence_json_missing_and_oversized(tmp_path: Path):
    assert identity_mod.read_evidence_json(tmp_path / "missing.json", "missing.json", 1024) is None
    target = tmp_path / "doc.json"
    target.write_text('{"x": 1}\n', encoding="utf-8")
    assert identity_mod.read_evidence_json(target, "doc.json", 4) is None
    target.write_text("{broken", encoding="utf-8")
    assert identity_mod.read_evidence_json(target, "doc.json", 1024) is None
    target.write_text("[1, 2]", encoding="utf-8")
    assert identity_mod.read_evidence_json(target, "doc.json", 1024) is None


def test_hash_artifact_oversized_is_rejected(tmp_path: Path):
    target = tmp_path / "artifact.bin"
    target.write_bytes(b"x" * 100)
    with pytest.raises(BuildError) as error:
        identity_mod.hash_artifact(target, "artifact.bin", 16, "BUILD_MAP_INVALID")
    assert error.value.details == {"path": "artifact.bin", "rule": "size"}


def test_atomic_write_fdopen_and_unlink_failures(tmp_path: Path, monkeypatch):
    target = tmp_path / "doc.json"

    def failing_fdopen(fd, mode):
        raise OSError("injected fdopen failure")

    monkeypatch.setattr(os, "fdopen", failing_fdopen)
    with pytest.raises(OSError):
        identity_mod.atomic_write_json(target, {"x": 1})
    assert not target.exists()
    assert [path for path in tmp_path.iterdir() if ".tmp" in path.name] == []

    def failing_unlink(path):
        raise OSError("injected unlink failure")

    monkeypatch.setattr(os, "unlink", failing_unlink)
    real_replace = identity_mod._replace

    def failing_replace(src, dst):
        raise OSError("injected replace failure")

    monkeypatch.setattr(identity_mod, "_replace", failing_replace)
    with pytest.raises(OSError):
        identity_mod.atomic_write_json(target, {"x": 1})


def test_default_sync_directory_os_error_is_swallowed(monkeypatch):
    import tempfile as tempfile_mod

    with tempfile_mod.TemporaryDirectory() as directory:
        real_open = os.open

        def failing_open(path, flags, *args):
            raise OSError("injected")

        monkeypatch.setattr(os, "open", failing_open)
        identity_mod._default_sync_directory(Path(directory))
        monkeypatch.setattr(os, "open", real_open)
