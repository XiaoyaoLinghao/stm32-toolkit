"""LINKER-FRAGMENT model, grammar, configuration and build-provenance tests.

Every fixture is an authored synthetic project below ``pytest`` ``tmp_path``.
No original project, hardware, network or installed runtime is touched.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from stm32_toolkit import __version__
from stm32_toolkit.build.identity import snapshot_project_inputs
from stm32_toolkit.build.model import (
    BUILD_PROJECT_INVALID,
    BuildError,
    BuildRequest,
)
from stm32_toolkit.build import runner as runner_mod
from stm32_toolkit.cli import main as cli_main
from stm32_toolkit.generation import (
    GenerationError,
    apply_project_configuration,
    plan_project_configuration,
)
from stm32_toolkit.generation import configure as configure_mod
from stm32_toolkit.generation.managed_files import (
    MANAGED_MANIFEST_PATH,
    build_managed_manifest_bytes,
    parse_managed_manifest_facts,
)
import stm32_toolkit.mcp_server as mcp_mod
from stm32_toolkit.workflows import configure_project_workflow
from stm32_toolkit.linker_fragment import (
    LinkerFragmentError,
    _patterns_overlap,
    parse_linker_fragment,
    read_linker_fragment,
)
from stm32_toolkit.project_model import MemoryRegion, ProjectManifestError, load_project_model

from test_generation import (
    EXPECTED_CMAKE,
    EXPECTED_LINKER,
    REPORT_PATH,
    report_payload,
    standard_payload,
    write_project,
    write_report_bytes,
    _redirect_path,
)

RAM = MemoryRegion("RAM", 0x20000000, 0x20000, "rw-")
CCM = MemoryRegion("CCM", 0x10000000, 0x10000, "rw-")
FLASH = MemoryRegion("FLASH", 0x08000000, 0x100000, "r-x")
REGIONS = (FLASH, RAM, CCM)
FRAGMENT_PATH = "linker/user.ld"
FRAGMENT_TEXT = (
    "/* Authored synthetic fragment: no vendor or board facts. */\n"
    ".sram2 0x20000000 (NOLOAD) :\n"
    "{\n"
    "  . = ALIGN(8);\n"
    "  *(.sram2 .sram2.*)\n"
    "} > RAM\n"
    "\n"
    ".sram3 (NOLOAD) :\n"
    "{\n"
    "  KEEP(*(.sram3.*))\n"
    "} > CCM\n"
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fragment_payload(**overrides) -> dict:
    payload = standard_payload()
    payload["memory"] = {
        "source": payload["memory"]["source"],
        "regions": [
            *payload["memory"]["regions"],
            {"name": "CCM", "origin": 0x10000000, "length": 0x10000, "attributes": "rw-"},
        ],
        # Two writable RAMs require an explicit reviewed managed layout.
        "layout": {
            "flash": "FLASH",
            "data": "RAM",
            "bss": "RAM",
            "heap": "RAM",
            "stack": "RAM",
        },
    }
    payload["generation"] = {
        **payload["generation"],
        "linkerFragment": FRAGMENT_PATH,
    }
    payload.update(overrides)
    return payload


def _fragment_project(tmp_path: Path, *, text: str = FRAGMENT_TEXT, payload=None) -> Path:
    root = write_project(tmp_path / "project", payload or _fragment_payload())
    fragment = root.joinpath(*FRAGMENT_PATH.split("/"))
    fragment.parent.mkdir(parents=True, exist_ok=True)
    fragment.write_text(text, encoding="utf-8")
    return root


def _plan_for(root: Path):
    return plan_project_configuration(load_project_model(root))


def _parse(text: str):
    return parse_linker_fragment(text, FRAGMENT_PATH, REGIONS)


# ---------------------------------------------------------------------------
# grammar
# ---------------------------------------------------------------------------


def test_parser_accepts_the_supported_subset_with_comments_and_keep():
    sections = _parse(FRAGMENT_TEXT)
    assert [section.name for section in sections] == [".sram2", ".sram3"]
    assert sections[0].address == 0x20000000
    assert sections[0].region == "RAM"
    assert [statement.kind for statement in sections[0].statements] == [
        "align",
        "sections",
    ]
    assert sections[1].address is None
    assert sections[1].region == "CCM"
    assert sections[1].statements[0].kind == "keep"
    assert sections[0].statement_lines() == (
        ". = ALIGN(8);",
        "*(.sram2 .sram2.*)",
    )
    assert sections[1].statement_lines() == ("KEEP(*(.sram3.*))",)


def test_parser_accepts_decimal_addresses_and_optional_semicolons():
    text = (
        ".scratch 536872960 (NOLOAD) :\n"
        "{\n"
        "  *(.scratch);\n"
        "  KEEP(*(.scratch.*));\n"
        "} > RAM;\n"
    )
    sections = _parse(text)
    assert sections[0].address == 0x20000800
    assert [item.kind for item in sections[0].statements] == ["sections", "keep"]


@pytest.mark.parametrize(
    ("text", "field", "rule"),
    [
        ("", "fragment", "empty"),
        ("/* only a comment */\n", "fragment", "empty"),
        ("MEMORY { RAM (rw) : ORIGIN = 0, LENGTH = 1 }\n", "sections[0]", "syntax"),
        ("ENTRY(Reset_Handler)\n", "sections[0]", "syntax"),
        (
            ".sram2 (NOLOAD) : { *(.sram2) } > RAM\ngarbage\n",
            "sections[1]",
            "syntax",
        ),
        (
            ".sram2 (NOLOAD) : { *(.sram2) } > RAM AT> FLASH\n",
            "sections[1]",
            "syntax",
        ),
        (
            ".sram2 (NOLOAD) : { INPUT(other.ld) } > RAM\n",
            "sections[0].statements[0]",
            "unsupported",
        ),
        (
            ".sram2 (NOLOAD) : { . = ALIGN(0); } > RAM\n",
            "sections[0].statements[0].alignment",
            "alignment",
        ),
        (
            ".sram2 (NOLOAD) : { . = ALIGN(3); } > RAM\n",
            "sections[0].statements[0].alignment",
            "alignment",
        ),
        (
            ".sram2 (NOLOAD) : { . = ALIGN(8192); } > RAM\n",
            "sections[0].statements[0].alignment",
            "alignment",
        ),
        (
            ".sram2 (NOLOAD) : { . = ALIGN(4) } > RAM\n",
            "sections[0].statements[0]",
            "syntax",
        ),
        (
            ".sram2 (NOLOAD) : { *(.sram2) } > RAM\n/* open",
            "fragment",
            "comment",
        ),
        (
            ".sram2 (NOLOAD) : { *(.sram2) } > RAM\n/section/\n",
            "fragment",
            "character",
        ),
        (
            ".sram2 0x100000000 (NOLOAD) : { *(.sram2) } > RAM\n",
            "sections[0].address",
            "range",
        ),
        (
            ".sram2 (NOLOAD) : { *(.sram2) } > MISSING\n",
            "sections[0].region",
            "unknownRegion",
        ),
        (
            ".sram2 (NOLOAD) : { *(.sram2) } > FLASH\n",
            "sections[0].region",
            "regionAccess",
        ),
        (
            ".sram2 0x30000000 (NOLOAD) : { *(.sram2) } > RAM\n",
            "sections[0].address",
            "addressRegion",
        ),
        (
            ".sram2 (NOLOAD) : { } > RAM\n",
            "sections[0].statements",
            "selectors",
        ),
        (
            ".sram2 (NOLOAD) : { *() } > RAM\n",
            "sections[0].statements[0].selectors",
            "required",
        ),
        (
            ".sram2 (NOLOAD) : { *(.sram2.buf) } > RAM\n",
            "sections[0].statements[0].selectors",
            "selectorFamily",
        ),
        (
            ".sram2 (NOLOAD) : { *(*.o) } > RAM\n",
            "sections[0].statements[0].selectors",
            "selector",
        ),
        (
            ".sram2 (NOLOAD) : { *(COMMON) } > RAM\n",
            "sections[0].statements[0].selectors",
            "selector",
        ),
        (
            ".sram2 (NOLOAD) : { *(.sram2) KEEP(*(.sram2)) } > RAM\n",
            "sections[0].statements[1].selectors",
            "duplicate",
        ),
        (
            ".SRAM2 (NOLOAD) : { *(.SRAM2) } > RAM\n"
            ".sram2 (NOLOAD) : { *(.sram2) } > RAM\n",
            "sections[1].name",
            "casefoldCollision",
        ),
        (
            ".data (NOLOAD) : { *(.data) } > RAM\n",
            "sections[0].name",
            "reserved",
        ),
        (
            ".sdata (NOLOAD) : { *(.sdata) } > RAM\n",
            "sections[0].name",
            "reserved",
        ),
        (
            ".sbss (NOLOAD) : { *(.sbss) } > RAM\n",
            "sections[0].name",
            "reserved",
        ),
        (
            ".tdata (NOLOAD) : { *(.tdata) } > RAM\n",
            "sections[0].name",
            "reserved",
        ),
        (
            ".tbss (NOLOAD) : { *(.tbss) } > RAM\n",
            "sections[0].name",
            "reserved",
        ),
        (
            ".dynamic (NOLOAD) : { *(.dynamic) } > RAM\n",
            "sections[0].name",
            "reserved",
        ),
        (
            ".dynsym (NOLOAD) : { *(.dynsym) } > RAM\n",
            "sections[0].name",
            "reserved",
        ),
        (
            ".dynstr (NOLOAD) : { *(.dynstr) } > RAM\n",
            "sections[0].name",
            "reserved",
        ),
        (
            ".hash (NOLOAD) : { *(.hash) } > RAM\n",
            "sections[0].name",
            "reserved",
        ),
        (
            ".SDATA (NOLOAD) : { *(.SDATA) } > RAM\n",
            "sections[0].name",
            "reserved",
        ),
        (
            ".text2 (NOLOAD) : { *(.text2) } > RAM\n",
            "sections[0].name",
            "reserved",
        ),
        (
            ".debug_info (NOLOAD) : { *(.debug_info) } > RAM\n",
            "sections[0].name",
            "reserved",
        ),
        (
            ".note_abi (NOLOAD) : { *(.note_abi) } > RAM\n",
            "sections[0].name",
            "reserved",
        ),
        (
            ".ctors (NOLOAD) : { *(.ctors) } > RAM\n",
            "sections[0].name",
            "reserved",
        ),
        (
            ".got (NOLOAD) : { *(.got) } > RAM\n",
            "sections[0].name",
            "reserved",
        ),
        (
            ".plt (NOLOAD) : { *(.plt) } > RAM\n",
            "sections[0].name",
            "reserved",
        ),
        (
            ".ARM.exidx (NOLOAD) : { *(.ARM.exidx) } > RAM\n",
            "sections[0].name",
            "reserved",
        ),
        (
            ".stm32tk.abs.08000000 (NOLOAD) : { *(.stm32tk.abs.08000000) } > RAM\n",
            "sections[0].name",
            "reserved",
        ),
        (
            ".heap (NOLOAD) : { *(.heap) } > RAM\n",
            "sections[0].name",
            "reserved",
        ),
        (
            ".stack (NOLOAD) : { *(.stack) } > RAM\n",
            "sections[0].name",
            "reserved",
        ),
        (
            ".init_array (NOLOAD) : { *(.init_array) } > RAM\n",
            "sections[0].name",
            "reserved",
        ),
    ],
)
def test_parser_rejects_out_of_subset_input(text, field, rule):
    with pytest.raises(LinkerFragmentError) as caught:
        _parse(text)
    assert caught.value.code == "LINKER_FRAGMENT_INVALID"
    assert caught.value.details["path"] == FRAGMENT_PATH
    assert caught.value.details["field"] == field
    assert caught.value.details["rule"] == rule
    assert "remediation" in caught.value.details


def test_parser_bounds_sections_statements_and_selectors():
    sections = "".join(
        f".s{i} (NOLOAD) : {{ *(.s{i}) }} > RAM\n" for i in range(33)
    )
    with pytest.raises(LinkerFragmentError) as caught:
        _parse(sections)
    assert caught.value.details["rule"] == "count"

    statements = ".s0 (NOLOAD) : {\n" + "".join(
        "  . = ALIGN(4);\n" for _ in range(65)
    ) + "} > RAM\n"
    with pytest.raises(LinkerFragmentError) as caught:
        _parse(statements)
    assert caught.value.details["rule"] == "count"

    selectors = ".s0 (NOLOAD) : { *(.s0 " + " ".join(
        ".s0.*" for _ in range(64)
    ) + ") } > RAM\n"
    with pytest.raises(LinkerFragmentError) as caught:
        _parse(selectors)
    assert caught.value.details["rule"] in {"count", "duplicate"}


def test_pattern_overlap_semantics_are_exact_family_aware():
    assert _patterns_overlap((".a", False), (".a", False))
    assert not _patterns_overlap((".a", False), (".a", True))
    assert _patterns_overlap((".a.b", False), (".a", True))
    assert _patterns_overlap((".a", True), (".a.b", True))
    assert not _patterns_overlap((".a", True), (".b", True))


# ---------------------------------------------------------------------------
# reading and model loading
# ---------------------------------------------------------------------------


def test_read_linker_fragment_hashes_exact_bytes(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    fragment = root / "linker" / "user.ld"
    fragment.parent.mkdir()
    raw = FRAGMENT_TEXT.replace("\n", "\r\n").encode("utf-8")
    fragment.write_bytes(raw)
    loaded = read_linker_fragment(root, FRAGMENT_PATH, REGIONS)
    assert loaded.sha256 == _sha(raw)
    assert [section.name for section in loaded.sections] == [".sram2", ".sram3"]


@pytest.mark.parametrize(
    ("mutate", "rule"),
    [
        ("missing", "missing"),
        ("directory", "regularFile"),
        ("oversize", "size"),
        ("encoding", "encoding"),
        ("absolute", "path"),
        ("traversal", "path"),
        ("backslash", "path"),
    ],
)
def test_read_linker_fragment_rejects_invalid_files(tmp_path, mutate, rule):
    root = tmp_path / "root"
    root.mkdir()
    fragment = root / "linker" / "user.ld"
    fragment.parent.mkdir()
    if mutate == "directory":
        fragment.mkdir()
    elif mutate == "oversize":
        fragment.write_bytes(b" " * (64 * 1024 + 1))
    elif mutate == "encoding":
        fragment.write_bytes(b"\xff\xfe\x00")
    elif mutate not in ("missing", "absolute", "traversal", "backslash"):
        fragment.write_text(FRAGMENT_TEXT, encoding="utf-8")
    path = {
        "absolute": "C:/outside.ld",
        "traversal": "../outside.ld",
        "backslash": "linker\\user.ld",
    }.get(mutate, FRAGMENT_PATH)
    with pytest.raises(LinkerFragmentError) as caught:
        read_linker_fragment(root, path, REGIONS)
    assert caught.value.details["rule"] == rule


def test_read_linker_fragment_rejects_a_redirecting_component(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    target = tmp_path / "outside"
    target.mkdir()
    (target / "user.ld").write_text(FRAGMENT_TEXT, encoding="utf-8")
    _redirect_path(monkeypatch, root / "linker", target, is_dir=True)
    with pytest.raises(LinkerFragmentError) as caught:
        read_linker_fragment(root, FRAGMENT_PATH, REGIONS)
    assert caught.value.details["rule"] == "redirect"


def test_read_linker_fragment_rejects_a_direct_file_redirect(tmp_path, monkeypatch):
    root = tmp_path / "root"
    (root / "linker").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "user.ld"
    target.write_text(FRAGMENT_TEXT, encoding="utf-8")
    _redirect_path(monkeypatch, root / "linker" / "user.ld", target, is_dir=False)
    with pytest.raises(LinkerFragmentError) as caught:
        read_linker_fragment(root, FRAGMENT_PATH, REGIONS)
    assert caught.value.details["rule"] == "redirect"


@pytest.mark.skipif(
    os.name == "nt",
    reason="unprivileged Windows file symlinks are unavailable; mocked coverage applies",
)
def test_read_linker_fragment_rejects_a_real_symlinked_file(tmp_path):
    root = tmp_path / "root"
    (root / "linker").mkdir(parents=True)
    target = tmp_path / "outside.ld"
    target.write_text(FRAGMENT_TEXT, encoding="utf-8")
    os.symlink(target, root / "linker" / "user.ld")
    with pytest.raises(LinkerFragmentError) as caught:
        read_linker_fragment(root, FRAGMENT_PATH, REGIONS)
    assert caught.value.details["rule"] == "redirect"


@pytest.mark.parametrize(
    "path",
    [
        "CMakeLists.txt",
        "linker/stm32tk.ld",
        ".vscode/settings.json",
        "LINKER/STM32TK.LD",
        "build/fragments/user.ld",
        "artifacts/migration/user.ld",
        ".stm32-toolkit/generated-files.json",
    ],
)
def test_model_load_rejects_fragment_paths_owned_by_generated_output(tmp_path, path):
    payload = _fragment_payload()
    payload["generation"]["linkerFragment"] = path
    root = write_project(tmp_path / "collision", payload)
    fragment = root.joinpath(*path.split("/"))
    fragment.parent.mkdir(parents=True, exist_ok=True)
    fragment.write_text(FRAGMENT_TEXT, encoding="utf-8")
    with pytest.raises(ProjectManifestError) as caught:
        load_project_model(root)
    assert caught.value.code == "LINKER_FRAGMENT_INVALID"
    assert caught.value.details["path"] == path
    assert caught.value.details["field"] == "generation.linkerFragment"
    assert caught.value.details["rule"] == "collision"
    assert caught.value.details["remediation"]


def test_model_load_binds_exact_fragment_and_rejects_native_combination(tmp_path):
    root = _fragment_project(tmp_path)
    model = load_project_model(root)
    fragment = model.generation.linker_fragment
    assert fragment is not None
    assert fragment.path == FRAGMENT_PATH
    assert fragment.sha256 == _sha((root / "linker" / "user.ld").read_bytes())
    assert [section.name for section in fragment.sections] == [".sram2", ".sram3"]

    native = _fragment_payload()
    native["generation"]["nativeLinkerScript"] = "linker/native.ld"
    native_root = write_project(tmp_path / "native", native)
    with pytest.raises(ProjectManifestError) as caught:
        load_project_model(native_root)
    assert caught.value.code == "LINKER_FRAGMENT_INVALID"
    assert caught.value.details["rule"] == "nativeLinkerOwned"


@pytest.mark.parametrize("value", ["", None, 3, ["linker/user.ld"]])
def test_model_load_rejects_empty_or_non_string_fragment_paths(tmp_path, value):
    payload = _fragment_payload()
    payload["generation"]["linkerFragment"] = value
    root = write_project(tmp_path / "invalid", payload)
    with pytest.raises(ProjectManifestError) as caught:
        load_project_model(root)
    assert caught.value.code == "PROJECT_SCHEMA_INVALID"


def test_model_load_rejects_a_fragment_colliding_with_a_declared_input(tmp_path):
    payload = _fragment_payload()
    payload["generation"]["linkerFragment"] = "Src/main.c"
    root = write_project(tmp_path / "collision", payload)
    with pytest.raises(ProjectManifestError) as caught:
        load_project_model(root)
    assert caught.value.code == "LINKER_FRAGMENT_INVALID"
    assert caught.value.details["rule"] == "collision"


def test_schema_v3_accepts_the_same_fragment_field(tmp_path):
    payload = _fragment_payload()
    payload["schemaVersion"] = 3
    root = _fragment_project(tmp_path, payload=payload)
    model = load_project_model(root)
    assert model.schema_version == 3
    assert model.generation.linker_fragment is not None


# ---------------------------------------------------------------------------
# configuration rendering and transactions
# ---------------------------------------------------------------------------


def test_absent_option_preserves_historical_rendered_bytes_and_hash(tmp_path):
    root = write_project(tmp_path / "absent")
    model = load_project_model(root)
    plan = plan_project_configuration(model)
    linker = next(item for item in plan.files if item.path == "linker/stm32tk.ld")
    cmake = next(item for item in plan.files if item.path == "CMakeLists.txt")
    assert linker.after_bytes == EXPECTED_LINKER.encode("utf-8")
    assert cmake.after_bytes == EXPECTED_CMAKE.encode("utf-8")
    assert b"LINK_DEPENDS" not in cmake.after_bytes
    assert b".sram" not in linker.after_bytes
    payload = json.loads(plan.managed_manifest_bytes.decode("utf-8"))
    assert "linkerFragment" not in payload
    # The fragment key is absent from the model identity payload entirely.
    from stm32_toolkit.generation.managed_files import _model_payload

    assert "linker_fragment" not in _model_payload(model)["generation"]


def test_fragment_renders_after_fixed_sections_and_before_data(tmp_path):
    root = _fragment_project(tmp_path)
    write_report_bytes(
        root,
        (
            json.dumps(
                report_payload(
                    [
                        {
                            "section": ".stm32tk.abs.20001000",
                            "address": 0x20001000,
                            "sourcePath": "Src/main.c",
                            "line": 1,
                            "symbol": "pinned",
                        }
                    ]
                )
            )
            + "\n"
        ).encode("utf-8"),
    )
    plan = _plan_for(root)
    linker = next(
        item for item in plan.files if item.path == "linker/stm32tk.ld"
    ).after_bytes.decode("utf-8")
    fixed = linker.index(".stm32tk.abs.20001000")
    fragment = linker.index(".sram2")
    fragment_aux = linker.index(".sram3")
    data = linker.index("  .data :")
    assert fixed < fragment < data
    assert fragment < fragment_aux < data
    assert "  .sram2 0x20000000 (NOLOAD) :" in linker
    assert "  .sram3 (NOLOAD) :" in linker
    assert "    KEEP(*(.sram3.*))" in linker
    cmake = next(
        item for item in plan.files if item.path == "CMakeLists.txt"
    ).after_bytes.decode("utf-8")
    assert cmake.count("LINK_DEPENDS") == 1
    assert '"${CMAKE_SOURCE_DIR}/linker/stm32tk.ld"' in cmake

    applied = apply_project_configuration(plan)
    assert applied.ok is True, applied.to_dict()
    manifest = json.loads(
        (root / MANAGED_MANIFEST_PATH).read_text(encoding="utf-8")
    )
    fragment_model = load_project_model(root).generation.linker_fragment
    assert fragment_model is not None
    assert manifest["linkerFragment"] == {
        "path": FRAGMENT_PATH,
        "sha256": fragment_model.sha256,
    }
    assert all(
        record["path"] != FRAGMENT_PATH for record in manifest["files"]
    )


def test_plan_binds_fragment_input_and_provenance_hash(tmp_path):
    root = _fragment_project(tmp_path)
    model = load_project_model(root)
    plan = plan_project_configuration(model)
    fragment = model.generation.linker_fragment
    assert fragment is not None
    entry = next(item for item in plan.inputs if item.path == FRAGMENT_PATH)
    assert entry.sha256 == fragment.sha256
    facts = parse_managed_manifest_facts(plan.managed_manifest_bytes)
    assert facts.linker_fragment_path == FRAGMENT_PATH
    assert facts.linker_fragment_sha256 == fragment.sha256
    # A tampered fragment input digest is rejected before any write.
    tampered = replace(
        plan,
        inputs=tuple(
            replace(item, sha256="0" * 64) if item.path == FRAGMENT_PATH else item
            for item in plan.inputs
        ),
    )
    rejected = apply_project_configuration(tampered)
    assert rejected.ok is False
    assert rejected.code == "GENERATION_PLAN_INVALID"
    assert not (root / "CMakeLists.txt").exists()


def test_mutated_fragment_between_plan_and_apply_is_refused_without_writes(tmp_path):
    root = _fragment_project(tmp_path)
    plan = _plan_for(root)
    fragment_path = root / "linker" / "user.ld"
    fragment_path.write_text(FRAGMENT_TEXT + "/* edit */\n", encoding="utf-8")
    before = sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))
    rejected = apply_project_configuration(plan)
    assert rejected.ok is False
    assert rejected.code == "GENERATION_INPUT_CHANGED"
    after = sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))
    assert after == before
    assert not (root / "CMakeLists.txt").exists()


def test_managed_linker_drift_still_blocks_apply(tmp_path):
    root = _fragment_project(tmp_path)
    plan = _plan_for(root)
    assert apply_project_configuration(plan).ok is True
    linker = root / "linker" / "stm32tk.ld"
    linker.write_text(linker.read_text(encoding="utf-8") + "/* drift */\n", encoding="utf-8")
    replanned = _plan_for(root)
    assert {blocker.code for blocker in replanned.blockers} == {"GENERATED_FILE_DRIFT"}
    rejected = apply_project_configuration(replanned)
    assert rejected.ok is False
    assert rejected.code == "GENERATED_FILE_DRIFT"
    assert linker.read_text(encoding="utf-8").endswith("/* drift */\n")


def test_removing_the_option_regenerates_without_provenance_or_fragment(tmp_path):
    root = _fragment_project(tmp_path)
    first = _plan_for(root)
    assert apply_project_configuration(first).ok is True
    manifest_path = root / ".stm32-project.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    del payload["generation"]["linkerFragment"]
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    model = load_project_model(root)
    assert model.generation.linker_fragment is None
    replanned = plan_project_configuration(model)
    linker = next(
        item for item in replanned.files if item.path == "linker/stm32tk.ld"
    ).after_bytes.decode("utf-8")
    assert ".sram2" not in linker
    facts = parse_managed_manifest_facts(replanned.managed_manifest_bytes)
    assert facts.linker_fragment_path is None
    assert apply_project_configuration(replanned).ok is True
    on_disk = json.loads(
        (root / MANAGED_MANIFEST_PATH).read_text(encoding="utf-8")
    )
    assert "linkerFragment" not in on_disk
    assert (root / "linker" / "user.ld").is_file()  # user-owned, untouched


def test_collect_inputs_refuses_a_fragment_changed_after_model_load(tmp_path):
    root = _fragment_project(tmp_path)
    model = load_project_model(root)
    (root / "linker" / "user.ld").write_text(
        FRAGMENT_TEXT + "/* race */\n", encoding="utf-8"
    )
    with pytest.raises(GenerationError) as caught:
        configure_mod._collect_inputs(root, model, None, None)
    assert caught.value.code == "LINKER_FRAGMENT_INVALID"
    assert caught.value.details["rule"] == "changed"


def _tree(root: Path) -> dict[str, tuple[object, ...]]:
    """Exact path/shape/byte snapshot used to prove no side effects."""
    snapshot: dict[str, tuple[object, ...]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            snapshot[relative] = ("link", os.readlink(path))
        elif path.is_file():
            snapshot[relative] = ("file", path.read_bytes())
        elif path.is_dir():
            snapshot[relative] = ("dir",)
    return snapshot


# ---------------------------------------------------------------------------
# public configuration PLAN/APPLY route
# ---------------------------------------------------------------------------


def test_public_configure_plan_apply_binds_the_fragment(tmp_path):
    root = _fragment_project(tmp_path)
    planned = configure_project_workflow(root)
    assert planned.ok is True, planned.to_dict()
    assert planned.operation == "project-configuration-plan"
    plan_data = planned.to_dict()["data"]
    fragment = load_project_model(root).generation.linker_fragment
    assert fragment is not None
    assert plan_data["plan_id"] == plan_project_configuration(
        load_project_model(root)
    ).plan_id
    inputs = {entry["path"]: entry for entry in plan_data["inputs"]}
    assert inputs[FRAGMENT_PATH]["sha256"] == fragment.sha256
    linker_plan = next(
        entry for entry in plan_data["files"] if entry["path"] == "linker/stm32tk.ld"
    )
    assert ".sram2 0x20000000 (NOLOAD)" in linker_plan["unified_diff"]
    assert plan_data["managed_manifest_path"] == MANAGED_MANIFEST_PATH
    before_apply = _tree(root)

    applied = configure_project_workflow(
        root, plan_id=plan_data["plan_id"], authorized=True
    )
    assert applied.ok is True, applied.to_dict()
    assert applied.operation == "project-configuration-apply"
    apply_data = applied.to_dict()["data"]
    assert "linker/stm32tk.ld" in apply_data["createdPaths"]
    assert apply_data["managedManifestPath"] == MANAGED_MANIFEST_PATH
    assert apply_data["modelSha256"] == plan_data["model_sha256"]
    assert _tree(root) != before_apply
    manifest = json.loads(
        (root / MANAGED_MANIFEST_PATH).read_text(encoding="utf-8")
    )
    assert manifest["linkerFragment"] == {
        "path": FRAGMENT_PATH,
        "sha256": fragment.sha256,
    }


def test_cli_configure_plan_and_failure_details(tmp_path, capsys):
    root = _fragment_project(tmp_path)
    assert (
        cli_main(
            ["project", "configure", "--project", str(root), "--dry-run", "--json"]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["operation"] == "project-configuration-plan"
    assert payload["ok"] is True
    assert len(payload["data"]["plan_id"]) == 64
    assert any(
        entry["path"] == FRAGMENT_PATH for entry in payload["data"]["inputs"]
    )

    invalid = _fragment_project(
        tmp_path / "invalid", text=".data (NOLOAD) : { *(.data) } > RAM\n"
    )
    before = _tree(invalid)
    assert (
        cli_main(
            ["project", "configure", "--project", str(invalid), "--dry-run", "--json"]
        )
        != 0
    )
    failure = json.loads(capsys.readouterr().out)
    assert failure["ok"] is False
    assert failure["code"] == "LINKER_FRAGMENT_INVALID"
    assert failure["details"]["path"] == FRAGMENT_PATH
    assert failure["details"]["field"] == "sections[0].name"
    assert failure["details"]["rule"] == "reserved"
    assert failure["details"]["remediation"]
    assert _tree(invalid) == before


def test_mcp_configure_plan_apply_route_uses_the_existing_tool(tmp_path):
    root = _fragment_project(tmp_path)
    runtime = mcp_mod.ServerRuntime.create(
        root, tmp_path / "plugin-data", "session-linker-fragment"
    )
    planned = mcp_mod.tool_project_configure(runtime)
    assert planned["ok"] is True, planned
    assert planned["operation"] == "project-configuration-plan"
    plan_data = planned["data"]
    linker_plan = next(
        entry for entry in plan_data["files"] if entry["path"] == "linker/stm32tk.ld"
    )
    assert ".sram2" in linker_plan["unified_diff"]
    applied = mcp_mod.tool_project_configure(
        runtime, plan_id=plan_data["plan_id"], authorized=True
    )
    assert applied["ok"] is True, applied
    assert applied["operation"] == "project-configuration-apply"
    assert "linker/stm32tk.ld" in applied["data"]["createdPaths"]
    assert (root / "linker" / "stm32tk.ld").is_file()
    assert json.loads(
        (root / MANAGED_MANIFEST_PATH).read_text(encoding="utf-8")
    )["linkerFragment"]["path"] == FRAGMENT_PATH


# ---------------------------------------------------------------------------
# snapshots and build provenance
# ---------------------------------------------------------------------------


def _configured_fragment_project(tmp_path: Path) -> Path:
    root = _fragment_project(tmp_path)
    plan = _plan_for(root)
    assert apply_project_configuration(plan).ok is True
    return root


def test_build_snapshot_includes_fragment_and_refuses_a_changed_fragment(tmp_path):
    root = _configured_fragment_project(tmp_path)
    model = load_project_model(root)
    fragment = model.generation.linker_fragment
    assert fragment is not None
    snapshot = snapshot_project_inputs(model)
    entry = next(item for item in snapshot.entries if item.path == FRAGMENT_PATH)
    assert entry.sha256 == fragment.sha256
    (root / "linker" / "user.ld").write_text(
        FRAGMENT_TEXT + "/* changed */\n", encoding="utf-8"
    )
    with pytest.raises(BuildError) as caught:
        snapshot_project_inputs(model)
    assert caught.value.code == "BUILD_INPUT_INVALID"
    assert caught.value.details["rule"] == "fragmentChanged"


def test_build_provenance_refuses_edit_removal_missing_and_model_change(tmp_path):
    edited = _configured_fragment_project(tmp_path / "edited")
    (edited / "linker" / "user.ld").write_text(
        FRAGMENT_TEXT + "/* edited */\n", encoding="utf-8"
    )
    with pytest.raises(BuildError) as caught:
        runner_mod._require_managed_configuration(edited)
    assert caught.value.code == BUILD_PROJECT_INVALID
    assert caught.value.details["rule"] == "linkerFragmentChanged"
    assert "remediation" in caught.value.details

    removed = _configured_fragment_project(tmp_path / "removed")
    manifest_path = removed / ".stm32-project.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    del payload["generation"]["linkerFragment"]
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(BuildError) as caught:
        runner_mod._require_managed_configuration(removed)
    assert caught.value.details["rule"] == "linkerFragmentRemoved"

    missing = _configured_fragment_project(tmp_path / "missing")
    managed_path = missing / MANAGED_MANIFEST_PATH
    managed = json.loads(managed_path.read_text(encoding="utf-8"))
    del managed["linkerFragment"]
    managed_path.write_text(json.dumps(managed, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(BuildError) as caught:
        runner_mod._require_managed_configuration(missing)
    assert caught.value.details["rule"] == "linkerFragmentMissing"

    changed = _configured_fragment_project(tmp_path / "model")
    manifest_path = changed / ".stm32-project.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["project"]["name"] = "renamed"
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(BuildError) as caught:
        runner_mod._require_managed_configuration(changed)
    assert caught.value.details["rule"] == "modelChanged"


def test_fragment_option_path_change_requires_reconfiguration_before_build(tmp_path):
    root = _configured_fragment_project(tmp_path)
    manifest_path = root / ".stm32-project.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    other_path = "linker/other.ld"
    payload["generation"]["linkerFragment"] = other_path
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (root / "linker" / "other.ld").write_text(FRAGMENT_TEXT, encoding="utf-8")

    with pytest.raises(BuildError) as caught:
        runner_mod._require_managed_configuration(root)
    assert caught.value.code == BUILD_PROJECT_INVALID
    assert caught.value.details["path"] == other_path
    assert caught.value.details["rule"] == "linkerFragmentChanged"
    assert caught.value.details["remediation"]

    replanned = _plan_for(root)
    assert replanned.blockers == ()
    assert apply_project_configuration(replanned).ok is True
    manifest = json.loads(
        (root / MANAGED_MANIFEST_PATH).read_text(encoding="utf-8")
    )
    assert manifest["linkerFragment"]["path"] == other_path
    # The user-owned original fragment is untouched by reconfiguration.
    assert (root / "linker" / "user.ld").is_file()
    runner_mod._require_managed_configuration(root)


def test_deleted_fragment_refuses_plan_and_build_without_side_effects(tmp_path):
    root = _configured_fragment_project(tmp_path)
    (root / "linker" / "user.ld").unlink()
    before = _tree(root)

    with pytest.raises(ProjectManifestError) as caught:
        load_project_model(root)
    assert caught.value.code == "LINKER_FRAGMENT_INVALID"
    assert caught.value.details["path"] == FRAGMENT_PATH
    assert caught.value.details["rule"] == "missing"

    failed_plan = configure_project_workflow(root)
    assert failed_plan.ok is False
    assert failed_plan.code == "LINKER_FRAGMENT_INVALID"
    assert failed_plan.details["rule"] == "missing"
    assert _tree(root) == before

    failed_build = runner_mod.run_build(BuildRequest(root, "arm-debug"))
    assert failed_build.ok is False
    assert failed_build.code == BUILD_PROJECT_INVALID
    assert failed_build.details["path"] == FRAGMENT_PATH
    assert failed_build.details["rule"] == "missing"
    assert failed_build.details["remediation"]
    assert _tree(root) == before


def test_build_refuses_before_any_process_spawn(tmp_path, monkeypatch):
    root = _configured_fragment_project(tmp_path)
    (root / "linker" / "user.ld").write_text(
        FRAGMENT_TEXT + "/* edited */\n", encoding="utf-8"
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("no process may be spawned for stale fragment evidence")

    monkeypatch.setattr(runner_mod, "_run_stage", forbidden)
    monkeypatch.setattr(runner_mod, "run_process", forbidden)
    result = runner_mod.run_build(BuildRequest(root, "arm-debug"))
    assert result.ok is False
    assert result.code == BUILD_PROJECT_INVALID
    assert result.details["rule"] == "linkerFragmentChanged"
    assert result.details["remediation"]


def _manifest_bytes_with_marker(marker) -> bytes:
    payload = json.loads(build_managed_manifest_bytes((), "a" * 64).decode("utf-8"))
    payload["linkerFragment"] = marker
    return json.dumps(payload, indent=2).encode("utf-8") + b"\n"


@pytest.mark.parametrize(
    "marker",
    [
        None,
        "linker/user.ld",
        ["linker/user.ld", "0" * 64],
        {"path": "linker/user.ld"},
        {"sha256": "0" * 64},
        {"path": "linker/user.ld", "sha256": "0" * 64, "size": 1},
        {"path": "", "sha256": "0" * 64},
        {"path": "../outside.ld", "sha256": "0" * 64},
        {"path": "C:/outside.ld", "sha256": "0" * 64},
        {"path": "linker\\user.ld", "sha256": "0" * 64},
        {"path": "linker/user.ld", "sha256": "abc"},
        {"path": "linker/user.ld", "sha256": "A" * 64},
        {"path": "linker/user.ld", "sha256": "z" * 64},
        {"path": "linker/user.ld", "sha256": 7},
    ],
)
def test_managed_manifest_rejects_malformed_fragment_provenance(marker):
    with pytest.raises(GenerationError) as caught:
        parse_managed_manifest_facts(_manifest_bytes_with_marker(marker))
    assert caught.value.code == "GENERATION_MANIFEST_INVALID"
    assert caught.value.details["rule"] == "fragment"
    assert caught.value.details["path"] == MANAGED_MANIFEST_PATH


def test_managed_manifest_accepts_only_the_exact_two_field_provenance():
    facts = parse_managed_manifest_facts(
        _manifest_bytes_with_marker(
            {"path": "linker/user.ld", "sha256": "0" * 64}
        )
    )
    assert facts.linker_fragment_path == "linker/user.ld"
    assert facts.linker_fragment_sha256 == "0" * 64
    # Omission remains historical: no provenance, exact prior bytes.
    omitted = parse_managed_manifest_facts(build_managed_manifest_bytes((), "a" * 64))
    assert omitted.linker_fragment_path is None
    assert omitted.linker_fragment_sha256 is None


def test_managed_manifest_bytes_without_fragment_are_historical():
    assert build_managed_manifest_bytes((), "a" * 64) == (
        b'{\n  "schemaVersion": 1,\n  "tool": "stm32-toolkit",\n'
        b'  "toolVersion": "'
        + __version__.encode()
        + b'",\n'
        b'  "templateVersion": 1,\n  "projectManifestSha256": "'
        + b"a" * 64
        + b'",\n'
        b'  "files": []\n}\n'
    )
