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

    POSIX uses a real symlink; Windows simulates the redirect by mapping
    ``Path.resolve`` for the link path to its canonical target (the inspected
    resolve-and-contain check is identical on both platforms).
    """
    if os.name == "nt":
        simulated = {str(link): target}
        real_resolve = Path.resolve

        def resolve(self, strict: bool = False):
            text = str(self)
            for link_text, resolved in simulated.items():
                if text == link_text:
                    return resolved
                if text.startswith(link_text + os.sep):
                    return real_resolve(resolved / text[len(link_text) + 1 :], strict=strict)
            return real_resolve(self, strict=strict)

        monkeypatch.setattr(Path, "resolve", resolve)
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


def test_snapshot_rejects_casefold_collision(tmp_path: Path):
    root = prepare_project(tmp_path, git_repo=False)
    (root / "Inc").mkdir()
    (root / "Inc" / "Board.H").write_text("x\n", encoding="utf-8")
    (root / "Inc" / "board.h").write_text("x\n", encoding="utf-8")
    payload = json.loads((root / ".stm32-project.json").read_text(encoding="utf-8"))
    payload["build"]["includePaths"] = ["Inc"]
    (root / ".stm32-project.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
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
