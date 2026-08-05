"""Tests for read-only Keil .uvprojx inspection (STM32TK-0302)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

import stm32_toolkit.keil.uvprojx as uvprojx_mod
from stm32_toolkit.keil import (
    KeilEvidence,
    KeilInspectionError,
    KeilInputDigest,
    KeilMemoryRegion,
    KeilScopedOptions,
    KeilSource,
    inspect_keil,
)

FIXTURES = Path(__file__).parent / "fixtures"
KEIL_FIXTURE = FIXTURES / "keil-project"

DEFAULT_CPU = 'IRAM(0x20000000,0x30000) IROM(0x8000000,0x100000) CPUTYPE("Cortex-M4")'
DEFAULT_OUT_DIR = ".\\Objects\\"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def snapshot_tree(root: Path) -> dict[str, tuple]:
    entries: dict[str, tuple] = {}
    for path in sorted(root.rglob("*")):
        rel = str(path.relative_to(root))
        lst = os.lstat(path)
        if stat.S_ISDIR(lst.st_mode):
            entries[rel] = ("dir", lst.st_mode)
        else:
            data = path.read_bytes()
            entries[rel] = (
                "file",
                hashlib.sha256(data).hexdigest(),
                len(data),
                lst.st_mode,
                lst.st_mtime_ns,
            )
    return entries


def project_xml(*targets: dict, xmlns: bool = True) -> str:
    """Build a Keil .uvprojx XML document from target dictionaries."""
    ns = ' xmlns="http://www.keil.com/project"' if xmlns else ""
    parts = ['<?xml version="1.0" encoding="UTF-8" ?>', f"<Project{ns}>", "  <Targets>"]
    for target in targets:
        parts.extend(
            [
                "    <Target>",
                f"      <TargetName>{target['name']}</TargetName>",
                f"      <pCCUsed>{target.get('pcc_used', '5060750::V5.06 update 7 (build 750)::ARMCC')}</pCCUsed>",
                f"      <uAC6>{target.get('uac6', '0')}</uAC6>",
                "      <TargetOption>",
                "        <TargetCommonOption>",
                f"          <Device>{target.get('device', 'STM32F429ZGTx')}</Device>",
            ]
        )
        if "pack_id" in target:
            parts.append(f"          <PackID>{target['pack_id']}</PackID>")
        if "cpu_field" in target:
            parts.append(f"          <{target['cpu_field'][0]}>{target['cpu_field'][1]}</{target['cpu_field'][0]}>")
        parts.append(
            f"          <Cpu>{target.get('cpu', DEFAULT_CPU)}</Cpu>"
        )
        if "float_abi" in target:
            parts.append(f"          <uFloatingPoint>{target['float_abi']}</uFloatingPoint>")
        parts.extend(
            [
                "        </TargetCommonOption>",
                f"        <OutputDirectory>{target.get('out_dir', DEFAULT_OUT_DIR)}</OutputDirectory>",
                f"        <OutputName>{target.get('out_name', 'firmware')}</OutputName>",
                "        <TargetArmAds>",
                "          <Cads>",
                "            <VariousControls>",
                f"              <Define>{target.get('defines', '')}</Define>",
                f"              <IncludePath>{target.get('include_paths', '')}</IncludePath>",
                f"              <MiscControls>{target.get('misc', '')}</MiscControls>",
                "            </VariousControls>",
                "          </Cads>",
                "          <LDads>",
                "            <VariousControls>",
                f"              <ScatterFile>{target.get('scatter', '')}</ScatterFile>",
                f"              <MiscControls>{target.get('ld_misc', '')}</MiscControls>",
                "            </VariousControls>",
                "          </LDads>",
                "        </TargetArmAds>",
                "      </TargetOption>",
                "      <Groups>",
            ]
        )
        for group in target.get("groups", []):
            parts.append("        <Group>")
            parts.append(f"          <GroupName>{group['name']}</GroupName>")
            parts.append("          <Files>")
            for file in group["files"]:
                parts.append("            <File>")
                parts.append(f"              <FileName>{file['name']}</FileName>")
                parts.append(f"              <FileType>{file.get('filetype', '1')}</FileType>")
                parts.append(f"              <FilePath>{file['path']}</FilePath>")
                if file.get("excluded"):
                    parts.append("              <IncludeInBuild>0</IncludeInBuild>")
                parts.append("            </File>")
            parts.append("          </Files>")
            parts.append("        </Group>")
        parts.append("      </Groups>")
        parts.append("    </Target>")
    parts.append("  </Targets>")
    parts.append("</Project>")
    return "\n".join(parts)


def write_project(
    root: Path,
    xml: str,
    files: dict[str, str | bytes] | None = None,
    name: str = "proj.uvprojx",
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    project_path = root / name
    project_path.write_text(xml, encoding="utf-8")
    for rel, content in (files or {}).items():
        posix_rel = rel.replace("\\", "/")
        path = root / posix_rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    return project_path


def simple_project(
    root: Path,
    *,
    defines: str = "",
    include_paths: str = "",
    sources: dict[str, str | bytes] | None = None,
    scatter: str = "",
    device: str = "STM32F429ZGTx",
    cpu: str = 'IRAM(0x20000000,0x30000) IROM(0x8000000,0x100000) CPUTYPE("Cortex-M4")',
    pcc_used: str = "5060750::V5.06 update 7 (build 750)::ARMCC",
    out_dir: str = ".\\Objects\\",
    out_name: str = "firmware",
    misc: str = "",
    ld_misc: str = "",
    extra: dict | None = None,
) -> Path:
    target = {
        "name": "Target 1",
        "defines": defines,
        "include_paths": include_paths,
        "scatter": scatter,
        "device": device,
        "cpu": cpu,
        "pcc_used": pcc_used,
        "out_dir": out_dir,
        "out_name": out_name,
        "misc": misc,
        "ld_misc": ld_misc,
        "groups": [
            {
                "name": "Group1",
                "files": [{"name": "a.c", "filetype": "1", "path": ".\\Src\\a.c"}],
            }
        ],
    }
    target.update(extra or {})
    xml = project_xml(target)
    return write_project(root, xml, sources or {".\\Src\\a.c": "int a;\n"})


@pytest.fixture
def keil_project(tmp_path: Path) -> Path:
    destination = tmp_path / "keil-project"
    shutil.copytree(KEIL_FIXTURE, destination)
    return destination


# ---------------------------------------------------------------------------
# exact extraction from the representative fixture
# ---------------------------------------------------------------------------


def test_main_fixture_exact_extraction(keil_project: Path) -> None:
    report = inspect_keil(keil_project)
    assert report.project_file == "legacy.uvprojx"
    assert report.target_name == "Legacy"
    assert report.device == "STM32F429ZGTx"
    assert report.device_pack == "Keil.STM32F4xx_DFP.2.16.1"
    assert report.cpu == "Cortex-M4"
    assert report.fpu == "FPU2"
    assert report.float_abi == "1"
    assert report.compiler == "armcc"
    assert report.compiler_version == "V5.06 update 7 (build 750)"
    assert report.defines == ("USE_STDPERIPH_DRIVER", "STM32F429xx")
    assert report.include_paths == ("Common", "Main", "Startup")
    assert report.sources == (
        KeilSource("Common/common.c", "Common", "c", True),
        KeilSource("Main/main.c", "Main", "c", True),
        KeilSource("Startup/startup_stm32f4xx.s", "Main", "asm", True),
    )
    assert report.linker_inputs == ()
    assert report.memory_regions == (
        KeilMemoryRegion("IROM1", 0x08000000, 0x100000, "r-x"),
        KeilMemoryRegion("IRAM1", 0x20000000, 0x30000, "rwx"),
    )
    output = report.output
    assert output.object_directory == "Objects"
    assert output.listing_directory == "Listing"
    assert output.output_name == "legacy"
    assert output.axf == "Objects/legacy.axf"
    assert output.map_file == "Objects/legacy.map"
    assert output.scatter_file == "Objects/legacy.sct"

    assert report.scoped_options == (
        KeilScopedOptions(
            "target",
            "Legacy",
            True,
            ("USE_STDPERIPH_DRIVER", "STM32F429xx"),
            ("Common", "Main", "Startup"),
            (),
        ),
        KeilScopedOptions("group", "Main", True, ("MAIN_GROUP_DEF",), (), ()),
        KeilScopedOptions("file", "Main/main.c", True, ("MAIN_FILE_DEF",), (), ()),
    )

    assert report.framework is None
    assert report.framework_candidates == ("spl",)
    assert report.framework_evidence == (
        KeilEvidence("define", "USE_STDPERIPH_DRIVER", "spl"),
    )

    expected_findings = [
        ("ARMCC_IRQ_QUALIFIER", "warning", "Common/common.c", 7, 1),
        ("ARMCC_INTRINSIC_NOP", "warning", "Common/common.c", 9, 5),
        ("ARMCC_INTRINSIC_WFI", "warning", "Common/common.c", 10, 5),
        ("ARMCC_INTRINSIC_WFI", "warning", "Common/common.c", 11, 5),
        ("ARMCC_CUSTOM_SECTION", "warning", "Common/common.c", 15, 1),
        ("ARMCC_UNSUPPORTED_PRAGMA", "blocker", "Common/common.c", 16, 1),
        ("ARMCC_UNSUPPORTED_PRAGMA", "blocker", "Common/common.c", 17, 1),
        ("ARMCC_CUSTOM_SECTION", "warning", "Common/common.c", 19, 1),
        ("ARMCC_ABSOLUTE_PLACEMENT", "blocker", "Common/common.c", 20, 1),
        ("ARMCC_SCATTER_FILE", "warning", "Objects/legacy.sct", 0, 0),
    ]
    assert [(f.rule_id, f.severity, f.path, f.line, f.column) for f in report.findings] == (
        expected_findings
    )

    codes = [w.code for w in report.warnings]
    assert codes == ["KEIL_FRAMEWORK_SELECTION_REQUIRED"]

    digest_map = {d.path: (d.sha256, d.size) for d in report.inputs}
    assert [d.path for d in report.inputs] == [
        "Common/common.c",
        "Main/main.c",
        "Startup/startup_stm32f4xx.s",
        "legacy.uvprojx",
    ]
    for rel in ("Common/common.c", "Main/main.c", "Startup/startup_stm32f4xx.s", "legacy.uvprojx"):
        raw = (keil_project / rel).read_bytes()
        assert digest_map[rel] == (hashlib.sha256(raw).hexdigest(), len(raw))
    assert report.project_sha256 == hashlib.sha256(
        (keil_project / "legacy.uvprojx").read_bytes()
    ).hexdigest()


def test_frozen_and_immutable(keil_project: Path) -> None:
    report = inspect_keil(keil_project)
    with pytest.raises(FrozenInstanceError):
        report.target_name = "other"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        report.sources[0].path = "other"  # type: ignore[misc]
    assert isinstance(report.sources, tuple)
    assert isinstance(report.warnings, tuple)
    assert isinstance(report.warnings[0].details, tuple)
    with pytest.raises(TypeError):
        report.warnings[0].details[0] = ("x", "y")  # type: ignore[index]
    # the error copies caller details on construction
    error = KeilInspectionError("X", "m", {"nested": [{"a": 1}]})
    assert error.details == {"nested": [{"a": 1}]}
    assert error.message == "m"
    assert error.code == "X"


def test_to_dict_shape_without_absolute_paths(keil_project: Path) -> None:
    report = inspect_keil(keil_project)
    data = report.to_dict()
    assert isinstance(data, dict)
    assert "project_root" not in data
    assert data["project_file"] == "legacy.uvprojx"
    assert data["defines"] == ["USE_STDPERIPH_DRIVER", "STM32F429xx"]
    assert data["sources"][0]["path"] == "Common/common.c"
    assert data["memory_regions"][0]["name"] == "IROM1"
    finding = data["findings"][0]
    assert set(finding) == {"rule_id", "severity", "path", "line", "column", "evidence", "message"}
    assert data["output"]["axf"] == "Objects/legacy.axf"
    assert data["inputs"][0]["path"] == "Common/common.c"
    json.dumps(data)

    def assert_no_absolute(value: object) -> None:
        if isinstance(value, str):
            assert not value.startswith("/")
            assert "\\" not in value
            assert "\x00" not in value
            assert str(keil_project) not in value
        elif isinstance(value, dict):
            for item in value.values():
                assert_no_absolute(item)
        elif isinstance(value, list):
            for item in value:
                assert_no_absolute(item)

    assert_no_absolute(data)
    assert json.dumps(inspect_keil(keil_project).to_dict()) == json.dumps(data)


# ---------------------------------------------------------------------------
# discovery and project selection
# ---------------------------------------------------------------------------


def test_no_project_found(tmp_path: Path) -> None:
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(tmp_path)
    assert error.value.code == "KEIL_PROJECT_NOT_FOUND"
    assert error.value.details == {"pattern": "*.uvprojx"}


def test_multiple_projects_require_selection(tmp_path: Path) -> None:
    write_project(tmp_path, "<Project/>", name="zeta.uvprojx")
    write_project(tmp_path, "<Project/>", name="Alpha.uvprojx")
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(tmp_path)
    assert error.value.code == "KEIL_PROJECT_SELECTION_REQUIRED"
    assert error.value.details == {"candidates": ["Alpha.uvprojx", "zeta.uvprojx"]}


def test_explicit_project_absolute_and_relative(keil_project: Path) -> None:
    absolute = inspect_keil(keil_project, uvprojx=keil_project / "legacy.uvprojx")
    relative = inspect_keil(keil_project, uvprojx=Path("legacy.uvprojx"))
    assert absolute.to_dict() == relative.to_dict()


def test_root_path_invalid(tmp_path: Path) -> None:
    cases = [
        None,
        "not-a-path",
        tmp_path / "missing",
        tmp_path / "missing" / "nested",
        tmp_path / ".uvprojx" / "file.txt",
    ]
    (tmp_path / "file.txt").write_text("x", encoding="utf-8")
    for case in cases:
        with pytest.raises(KeilInspectionError) as error:
            inspect_keil(case)  # type: ignore[arg-type]
        assert error.value.code == "KEIL_PROJECT_PATH_INVALID"
        assert error.value.details == {"field": "projectRoot", "rule": "directory"}
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(Path("bad\x00root"))
    assert error.value.code == "KEIL_PROJECT_PATH_INVALID"


def test_explicit_project_invalid(tmp_path: Path) -> None:
    root = tmp_path / "root"
    write_project(root, "<Project/>", name="proj.uvprojx")
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(root, uvprojx="proj.uvprojx")  # type: ignore[arg-type]
    assert error.value.code == "KEIL_PROJECT_PATH_INVALID"
    assert error.value.details == {"field": "uvprojx", "rule": "withinProjectRoot"}
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(root, uvprojx=root / "proj.txt")
    assert error.value.code == "KEIL_PROJECT_PATH_INVALID"
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(root, uvprojx=root / "missing.uvprojx")
    assert error.value.code == "KEIL_PROJECT_UNAVAILABLE"
    assert error.value.details == {"path": "missing.uvprojx"}
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(root, uvprojx=tmp_path / "outside.uvprojx")
    assert error.value.code == "KEIL_PROJECT_PATH_INVALID"
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(root, uvprojx=Path("bad\x00.uvprojx"))
    assert error.value.code == "KEIL_PROJECT_PATH_INVALID"


def test_explicit_project_is_directory(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "dir.uvprojx").mkdir()
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(root, uvprojx=root / "dir.uvprojx")
    assert error.value.code == "KEIL_PROJECT_UNAVAILABLE"


def test_unsafe_dtd_and_entity_rejected(keil_project: Path) -> None:
    (keil_project / "evil.uvprojx").write_text(
        "<!DOCTYPE foo [<!ENTITY x SYSTEM 'file:///etc/passwd'>]><Project/>", encoding="utf-8"
    )
    for payload in ("<!DOCTYPE", "<!ENTITY"):
        (keil_project / "evil.uvprojx").write_text(payload, encoding="utf-8")
        with pytest.raises(KeilInspectionError) as error:
            inspect_keil(keil_project, uvprojx=keil_project / "evil.uvprojx")
        assert error.value.code == "KEIL_XML_UNSAFE"
        assert error.value.details == {"rule": "doctypeOrEntity"}


def test_malformed_xml_reports_position(keil_project: Path) -> None:
    (keil_project / "evil.uvprojx").write_text("<Project><Targets></Project>", encoding="utf-8")
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(keil_project, uvprojx=keil_project / "evil.uvprojx")
    assert error.value.code == "KEIL_XML_INVALID"
    assert error.value.details["path"] == "evil.uvprojx"
    assert isinstance(error.value.details["line"], int)
    assert isinstance(error.value.details["column"], int)


def test_xml_size_cap(keil_project: Path) -> None:
    target = {
        "name": "Target 1",
        "groups": [],
        "defines": "A" * (8 * 1024 * 1024),
    }
    (keil_project / "big.uvprojx").write_text(project_xml(target), encoding="utf-8")
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(keil_project, uvprojx=keil_project / "big.uvprojx")
    assert error.value.code == "KEIL_XML_LIMIT_EXCEEDED"
    assert error.value.details == {"limitBytes": 8388608}


# ---------------------------------------------------------------------------
# target selection
# ---------------------------------------------------------------------------


def test_zero_targets(tmp_path: Path) -> None:
    root = tmp_path / "root"
    write_project(root, "<Project><Targets/></Project>")
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(root)
    assert error.value.code == "KEIL_TARGET_INVALID"


def test_multiple_targets_require_selection(tmp_path: Path) -> None:
    root = tmp_path / "root"
    write_project(
        root,
        project_xml(
            {"name": "Beta", "groups": []},
            {"name": "Alpha", "groups": []},
        ),
    )
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(root)
    assert error.value.code == "KEIL_TARGET_SELECTION_REQUIRED"
    assert error.value.details == {"targets": ["Alpha", "Beta"]}
    report = inspect_keil(root, target_name="Alpha")
    assert report.target_name == "Alpha"
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(root, target_name="alpha")
    assert error.value.code == "KEIL_TARGET_NOT_FOUND"
    assert error.value.details == {
        "targetName": "alpha",
        "targets": ["Alpha", "Beta"],
    }


def test_missing_device_and_cpu(tmp_path: Path) -> None:
    root = tmp_path / "root"
    write_project(root, project_xml({"name": "T", "device": "", "groups": []}))
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(root)
    assert error.value.code == "KEIL_TARGET_INVALID"
    assert error.value.details == {"field": "device", "rule": "missing"}
    write_project(
        root,
        project_xml({"name": "T", "cpu": "CLOCK(168000000)", "groups": []}),
    )
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(root)
    assert error.value.code == "KEIL_TARGET_INVALID"
    assert error.value.details == {"field": "cpu", "rule": "missing"}


def test_namespace_variants(tmp_path: Path) -> None:
    target = {
        "name": "T",
        "groups": [{"name": "G", "files": [{"name": "a.c", "path": ".\\a.c"}]}],
    }
    files = {".\\a.c": "int a;\n"}
    plain = tmp_path / "plain"
    write_project(plain, project_xml(target, xmlns=False), files)
    report_plain = inspect_keil(plain)
    assert report_plain.device == "STM32F429ZGTx"
    assert report_plain.sources[0].path == "a.c"
    prefixed = tmp_path / "prefixed"
    xml = project_xml(target, xmlns=False).replace("<Project>", '<Project xmlns:k="http://www.keil.com/project">')
    for name in ("Targets", "Target", "TargetName", "TargetOption", "TargetCommonOption", "Device",
                 "Cpu", "Groups", "Group", "GroupName", "Files", "File", "FileName", "FileType",
                 "FilePath", "pCCUsed"):
        xml = xml.replace(f"<{name}>", f"<k:{name}>").replace(f"</{name}>", f"</k:{name}>")
    write_project(prefixed, xml, files)
    report_prefixed = inspect_keil(prefixed)
    plain_dict = report_plain.to_dict()
    prefixed_dict = report_prefixed.to_dict()
    for item in (plain_dict, prefixed_dict):
        item.pop("project_sha256", None)
        item.pop("inputs", None)
    assert prefixed_dict == plain_dict


# ---------------------------------------------------------------------------
# options, compiler, memory
# ---------------------------------------------------------------------------


def test_compiler_family_and_version(tmp_path: Path) -> None:
    root = tmp_path / "root"
    simple_project(root, pcc_used="6190000::V6.19::ARMCLANG")
    report = inspect_keil(root)
    assert report.compiler == "armclang"
    assert report.compiler_version == "V6.19"
    simple_project(root, pcc_used="1234::V9.9::MYCC")
    report = inspect_keil(root)
    assert report.compiler == "unknown"
    assert report.compiler_version == "V9.9"
    assert "KEIL_COMPILER_UNKNOWN" in [w.code for w in report.warnings]
    simple_project(root, pcc_used="")
    report = inspect_keil(root)
    assert report.compiler == "unknown"
    assert report.compiler_version is None


def test_target_defines_dedup_and_order(tmp_path: Path) -> None:
    root = tmp_path / "root"
    simple_project(root, defines="B,A,B,A;A")
    report = inspect_keil(root)
    assert report.defines == ("B", "A")


def test_include_paths_split_and_dedup(tmp_path: Path) -> None:
    root = tmp_path / "root"
    simple_project(root, include_paths="X;Y;X;;Z")
    report = inspect_keil(root)
    assert report.include_paths == ("X", "Y", "Z")


def test_misc_controls_single_item_not_shell_split(tmp_path: Path) -> None:
    root = tmp_path / "root"
    simple_project(root, misc=" -O3 --c99 -D FOO ")
    report = inspect_keil(root)
    assert report.scoped_options[0].misc_controls == (" -O3 --c99 -D FOO ",)
    assert report.scoped_options[0].defines == ()


def test_memory_hex_decimal_zero_and_order(tmp_path: Path) -> None:
    root = tmp_path / "root"
    simple_project(
        root,
        cpu='IRAM(0x20000000,0x30000) IRAM2(0x20030000,0x0) IROM(0x8000000,0x100000) IROM2(1048576,65536) CPUTYPE("Cortex-M4")',
    )
    report = inspect_keil(root)
    assert report.memory_regions == (
        KeilMemoryRegion("IROM1", 0x08000000, 0x100000, "r-x"),
        KeilMemoryRegion("IROM2", 1048576, 65536, "r-x"),
        KeilMemoryRegion("IRAM1", 0x20000000, 0x30000, "rwx"),
    )


def test_memory_conflict_and_malformed(tmp_path: Path) -> None:
    root = tmp_path / "root"
    simple_project(root, cpu='IROM(0x8000000,0x100000) IROM(0x8000000,0x200000) CPUTYPE("Cortex-M4")')
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(root)
    assert error.value.code == "KEIL_MEMORY_CONFLICT"
    assert error.value.details == {"region": "IROM1"}
    simple_project(root, cpu='IROM(0x8000000,zzz) CPUTYPE("Cortex-M4")')
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(root)
    assert error.value.code == "KEIL_TARGET_INVALID"
    assert error.value.details == {"field": "memory", "rule": "parse"}


def test_memory_from_target_field(tmp_path: Path) -> None:
    root = tmp_path / "root"
    simple_project(root, cpu='CPUTYPE("Cortex-M4")', extra={"cpu_field": ("IROM1", "0x8000000 0x100000")})
    report = inspect_keil(root)
    assert report.memory_regions == (
        KeilMemoryRegion("IROM1", 0x08000000, 0x100000, "r-x"),
    )
    simple_project(
        root,
        cpu='IROM(0x8000000,0x100000) CPUTYPE("Cortex-M4")',
        extra={"cpu_field": ("IROM1", "0x9000000 0x100000")},
    )
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(root)
    assert error.value.code == "KEIL_MEMORY_CONFLICT"


def test_exclusion_from_build_and_duplicate_sources(tmp_path: Path) -> None:
    root = tmp_path / "root"
    xml = project_xml(
        {
            "name": "T",
            "groups": [
                {
                    "name": "G",
                    "files": [
                        {"name": "a.c", "path": ".\\Src\\a.c"},
                        {"name": "b.c", "path": ".\\Src\\b.c", "excluded": True},
                        {"name": "a2.c", "path": ".\\Src\\a.c"},
                    ],
                }
            ],
        }
    )
    files = {
        ".\\Src\\a.c": "int a;\n",
        ".\\Src\\b.c": "void __irq f(void) {}\n",
    }
    write_project(root, xml, files)
    report = inspect_keil(root)
    assert [s.path for s in report.sources] == ["Src/a.c", "Src/b.c"]
    assert report.sources[1].included is False
    assert "KEIL_DUPLICATE_SOURCE" in [w.code for w in report.warnings]
    assert report.inputs == (
        KeilInputDigest("Src/a.c", hashlib.sha256(b"int a;\n").hexdigest(), 7),
        KeilInputDigest("proj.uvprojx", hashlib.sha256(xml.encode("utf-8")).hexdigest(), len(xml.encode("utf-8"))),
    )
    assert not any(f.rule_id == "ARMCC_IRQ_QUALIFIER" for f in report.findings)


# ---------------------------------------------------------------------------
# path normalization and safety
# ---------------------------------------------------------------------------


def test_path_normalization_nested_and_mixed(keil_project: Path) -> None:
    nested = keil_project / "Nested"
    nested.mkdir()
    shutil.copyfile(keil_project / "legacy.uvprojx", nested / "legacy.uvprojx")
    for name in ("Common", "Main", "Startup", "Objects"):
        shutil.move(str(keil_project / name), str(nested / name))
    os.remove(keil_project / "legacy.uvprojx")
    report = inspect_keil(keil_project, uvprojx=keil_project / "Nested" / "legacy.uvprojx")
    assert report.project_file == "Nested/legacy.uvprojx"
    assert report.sources[0].path == "Nested/Common/common.c"
    assert report.include_paths == ("Nested/Common", "Nested/Main", "Nested/Startup")
    assert report.output.object_directory == "Nested/Objects"
    assert report.output.axf == "Nested/Objects/legacy.axf"
    assert report.output.map_file == "Nested/Objects/legacy.map"


def test_mixed_separators_normalized(tmp_path: Path) -> None:
    root = tmp_path / "root"
    xml = project_xml(
        {
            "name": "T",
            "groups": [{"name": "G", "files": [{"name": "a.c", "path": "Src\\mixed.c"}]}],
        }
    )
    write_project(root, xml, {"Src\\mixed.c": "int a;\n"})
    report = inspect_keil(root)
    assert report.sources[0].path == "Src/mixed.c"


@pytest.mark.parametrize(
    "bad_path",
    [
        "/etc/passwd",
        "C:\\Windows\\system32\\x.c",
        "D:file.c",
        "\\\\server\\share\\x.c",
        "//server/share/x.c",
        "..\\..\\outside.c",
        "../../outside.c",
    ],
)
def test_unsafe_source_paths_rejected(tmp_path: Path, bad_path: str) -> None:
    root = tmp_path / "root"
    xml = project_xml(
        {
            "name": "T",
            "groups": [{"name": "G", "files": [{"name": "a.c", "path": bad_path}]}],
        }
    )
    write_project(root, xml)
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(root)
    assert error.value.code == "KEIL_PATH_OUTSIDE_PROJECT"
    assert error.value.details == {"field": "source", "rule": "withinProjectRoot"}


def test_include_path_escape_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    simple_project(root, include_paths="C:\\outside")
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(root)
    assert error.value.code == "KEIL_PATH_OUTSIDE_PROJECT"
    assert error.value.details == {"field": "includePath", "rule": "withinProjectRoot"}


def test_output_directory_escape_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    simple_project(root, out_dir="..\\..\\escape\\")
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(root)
    assert error.value.code == "KEIL_PATH_OUTSIDE_PROJECT"
    assert error.value.details == {"field": "outputDirectory", "rule": "withinProjectRoot"}


def test_symlink_escape_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.c").write_text("int secret;\n", encoding="utf-8")
    xml = project_xml(
        {
            "name": "T",
            "groups": [{"name": "G", "files": [{"name": "a.c", "path": ".\\Link\\secret.c"}]}],
        }
    )
    write_project(root, xml, files={})
    os.symlink(outside, root / "Link")
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(root)
    assert error.value.code == "KEIL_PATH_OUTSIDE_PROJECT"
    assert "secret" not in str(error.value.details)


def test_symlink_inside_root_rejected_conservatively(tmp_path: Path) -> None:
    root = tmp_path / "root"
    xml = project_xml(
        {
            "name": "T",
            "groups": [{"name": "G", "files": [{"name": "a.c", "path": ".\\Link\\a.c"}]}],
        }
    )
    write_project(root, xml, {".\\Src\\a.c": "int a;\n"})
    os.symlink(root / "Src", root / "Link")
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(root)
    assert error.value.code == "KEIL_PATH_OUTSIDE_PROJECT"


def test_simulated_reparse_point_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "root"
    simple_project(root, sources={".\\Src\\a.c": "int a;\n"})
    (root / "Objects").mkdir()
    real_lstat = os.lstat

    class FakeStat:
        st_file_attributes = 0x400  # FILE_ATTRIBUTE_REPARSE_POINT

        def __init__(self, real):
            self._real = real

        @property
        def st_mode(self):
            return self._real.st_mode

    def fake_lstat(path):
        real = real_lstat(path)
        if str(path).endswith("Objects"):
            return FakeStat(real)
        return real

    monkeypatch.setattr(uvprojx_mod.os, "lstat", fake_lstat)
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(root)
    assert error.value.code == "KEIL_PATH_OUTSIDE_PROJECT"


def test_permission_error_during_inspection_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    simple_project(root, sources={".\\Src\\a.c": "int a;\n"})
    real_lstat = os.lstat

    def fake_lstat(path):
        if str(path).endswith("Objects"):
            raise PermissionError("denied")
        return real_lstat(path)

    monkeypatch.setattr(uvprojx_mod.os, "lstat", fake_lstat)
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(root)
    assert error.value.code == "KEIL_PATH_OUTSIDE_PROJECT"
    assert "denied" not in str(error.value.details)


def test_generic_oserror_during_inspection_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    simple_project(root, sources={".\\Src\\a.c": "int a;\n"})
    real_lstat = os.lstat

    def fake_lstat(path):
        if str(path).endswith("Src"):
            raise OSError("boom")
        return real_lstat(path)

    monkeypatch.setattr(uvprojx_mod.os, "lstat", fake_lstat)
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(root)
    assert error.value.code == "KEIL_PATH_OUTSIDE_PROJECT"
    assert "boom" not in str(error.value.details)


def test_missing_source_warning_no_creation(tmp_path: Path) -> None:
    root = tmp_path / "root"
    xml = project_xml(
        {
            "name": "T",
            "groups": [{"name": "G", "files": [{"name": "absent.c", "path": ".\\Missing\\absent.c"}]}],
        }
    )
    write_project(root, xml, files={})
    report = inspect_keil(root)
    assert [s.path for s in report.sources] == ["Missing/absent.c"]
    codes = [w.code for w in report.warnings]
    assert "KEIL_SOURCE_MISSING" in codes
    assert not (root / "Missing").exists()
    assert all(d.path != "Missing/absent.c" for d in report.inputs)


def test_missing_include_path_warning(tmp_path: Path) -> None:
    root = tmp_path / "root"
    simple_project(root, include_paths="Inc;MissingDir")
    report = inspect_keil(root)
    assert report.include_paths == ("Inc", "MissingDir")
    assert "KEIL_INCLUDE_PATH_MISSING" in [w.code for w in report.warnings]


# ---------------------------------------------------------------------------
# scanner
# ---------------------------------------------------------------------------


def test_scanner_ignores_comments_and_string_literals(tmp_path: Path) -> None:
    root = tmp_path / "root"
    content = (
        "// __irq __nop() __WFI() __asm { __at(0) #pragma import\n"
        "/* __irq __nop() __WFI() __asm { __at(0) */\n"
        'const char *a = "__irq __nop() __WFI() __asm{";\n'
        "char c = 'x';\n"
        "int x = __nop;  /* not a call */\n"
        "int y = 1;\n"
    )
    xml = project_xml(
        {
            "name": "T",
            "groups": [{"name": "G", "files": [{"name": "a.c", "path": ".\\Src\\a.c"}]}],
        }
    )
    write_project(root, xml, {".\\Src\\a.c": content})
    report = inspect_keil(root)
    assert report.findings == ()


def test_scanner_detects_all_rules_exact_positions(tmp_path: Path) -> None:
    root = tmp_path / "root"
    content = "\n".join(
        [
            "#include <stm32f4xx.h>",
            "",
            "__irq void handler(void) {",
            "    __nop();",
            "    __WFI();",
            "    __wfi();",
            "}",
            "",
            "__asm void declare(void);",
            "void body(void) { __asm { nop } }",
            "",
            "__attribute__((at(0x20000000))) int pinned;",
            "__at(0x20000004) int pinned2;",
            "__attribute__((section(\".custom\"))) int placed;",
            "",
            "#pragma arm section code=\".x\"",
            "#pragma arm import = 1",
            "#pragma import(__use_no_semihosting)",
            "#pragma O3",
            "#pragma once",
            "",
            "__asm(\"nop\");",
            'char *s = "__attribute__((at(1)))";',
        ]
    )
    xml = project_xml(
        {
            "name": "T",
            "groups": [{"name": "G", "files": [{"name": "a.c", "path": ".\\Src\\a.c"}]}],
        }
    )
    write_project(root, xml, {".\\Src\\a.c": content})
    report = inspect_keil(root)
    findings = [(f.rule_id, f.severity, f.line, f.column) for f in report.findings]
    assert findings == [
        ("ARMCC_IRQ_QUALIFIER", "warning", 3, 1),
        ("ARMCC_INTRINSIC_NOP", "warning", 4, 5),
        ("ARMCC_INTRINSIC_WFI", "warning", 5, 5),
        ("ARMCC_INTRINSIC_WFI", "warning", 6, 5),
        ("ARMCC_INLINE_ASSEMBLY_FUNCTION", "blocker", 9, 1),
        ("ARMCC_INLINE_ASSEMBLY_FUNCTION", "blocker", 10, 19),
        ("ARMCC_ABSOLUTE_PLACEMENT", "blocker", 12, 1),
        ("ARMCC_ABSOLUTE_PLACEMENT", "blocker", 13, 1),
        ("ARMCC_CUSTOM_SECTION", "warning", 14, 1),
        ("ARMCC_CUSTOM_SECTION", "warning", 16, 1),
        ("ARMCC_UNSUPPORTED_PRAGMA", "blocker", 17, 1),
        ("ARMCC_UNSUPPORTED_PRAGMA", "blocker", 18, 1),
        ("ARMCC_UNSUPPORTED_PRAGMA", "blocker", 19, 1),
    ]
    assert all(f.path == "Src/a.c" for f in report.findings)
    by_rule = {f.rule_id: f for f in report.findings}
    assert by_rule["ARMCC_CUSTOM_SECTION"].severity == "warning"
    assert by_rule["ARMCC_ABSOLUTE_PLACEMENT"].severity == "blocker"
    assert by_rule["ARMCC_INLINE_ASSEMBLY_FUNCTION"].severity == "blocker"
    assert by_rule["ARMCC_UNSUPPORTED_PRAGMA"].severity == "blocker"
    assert by_rule["ARMCC_IRQ_QUALIFIER"].evidence == "__irq void handler(void) {"


def test_evidence_capped_at_200_codepoints(tmp_path: Path) -> None:
    root = tmp_path / "root"
    content = "x = 1; " + "y" * 300 + " __irq void f(void) {}\n"
    xml = project_xml(
        {
            "name": "T",
            "groups": [{"name": "G", "files": [{"name": "a.c", "path": ".\\Src\\a.c"}]}],
        }
    )
    write_project(root, xml, {".\\Src\\a.c": content})
    report = inspect_keil(root)
    assert len(report.findings[0].evidence) == 200


def test_assembly_semicolon_comments_ignored(tmp_path: Path) -> None:
    root = tmp_path / "root"
    content = "; __irq __nop() __WFI() __asm {\n    AREA RESET\n    END\n"
    xml = project_xml(
        {
            "name": "T",
            "groups": [{"name": "G", "files": [{"name": "a.s", "path": ".\\Startup\\a.s", "filetype": "2"}]}],
        }
    )
    write_project(root, xml, {".\\Startup\\a.s": content})
    report = inspect_keil(root)
    assert report.sources[0].language == "asm"
    assert report.findings == ()


def test_invalid_encoding_blocker(tmp_path: Path) -> None:
    root = tmp_path / "root"
    xml = project_xml(
        {
            "name": "T",
            "groups": [{"name": "G", "files": [{"name": "a.c", "path": ".\\Src\\a.c"}]}],
        }
    )
    write_project(root, xml, {".\\Src\\a.c": b"int x = \xff\xfe;\n"})
    report = inspect_keil(root)
    encoding_findings = [f for f in report.findings if f.rule_id == "ARMCC_SOURCE_ENCODING_UNSUPPORTED"]
    assert len(encoding_findings) == 1
    assert encoding_findings[0].severity == "blocker"
    assert encoding_findings[0].evidence == ""
    assert encoding_findings[0].line == 0
    assert encoding_findings[0].column == 0
    assert any(d.path == "Src/a.c" for d in report.inputs)


def test_scan_file_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(uvprojx_mod.armcc_scan, "SCAN_FILE_LIMIT", 100)
    root = tmp_path / "root"
    xml = project_xml(
        {
            "name": "T",
            "groups": [{"name": "G", "files": [{"name": "a.c", "path": ".\\Src\\a.c"}]}],
        }
    )
    write_project(root, xml, {".\\Src\\a.c": "x" * 200})
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(root)
    assert error.value.code == "KEIL_SCAN_LIMIT_EXCEEDED"
    assert error.value.details == {"limitBytes": 100, "scope": "file"}


def test_scan_total_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(uvprojx_mod.armcc_scan, "SCAN_TOTAL_LIMIT", 250)
    root = tmp_path / "root"
    xml = project_xml(
        {
            "name": "T",
            "groups": [
                {
                    "name": "G",
                    "files": [
                        {"name": "a.c", "path": ".\\Src\\a.c"},
                        {"name": "b.c", "path": ".\\Src\\b.c"},
                        {"name": "c.c", "path": ".\\Src\\c.c"},
                    ],
                }
            ],
        }
    )
    write_project(
        root,
        xml,
        {
            ".\\Src\\a.c": "x" * 100,
            ".\\Src\\b.c": "y" * 100,
            ".\\Src\\c.c": "z" * 100,
        },
    )
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(root)
    assert error.value.code == "KEIL_SCAN_LIMIT_EXCEEDED"
    assert error.value.details == {"limitBytes": 250, "scope": "inspection"}


# ---------------------------------------------------------------------------
# framework inference
# ---------------------------------------------------------------------------


def test_framework_spl_two_categories(tmp_path: Path) -> None:
    root = tmp_path / "root"
    simple_project(
        root,
        defines="USE_STDPERIPH_DRIVER",
        include_paths="Libraries/STM32F4xx_StdPeriph_Driver/inc",
    )
    (root / "Libraries/STM32F4xx_StdPeriph_Driver/inc").mkdir(parents=True)
    report = inspect_keil(root)
    assert report.framework == "spl"
    assert report.framework_candidates == ("spl",)
    assert not any(w.code == "KEIL_FRAMEWORK_SELECTION_REQUIRED" for w in report.warnings)


def test_framework_hal_two_categories(tmp_path: Path) -> None:
    root = tmp_path / "root"
    simple_project(root, defines="USE_HAL_DRIVER", include_paths="Drivers/STM32F4xx_HAL_Driver/Inc")
    (root / "Drivers/STM32F4xx_HAL_Driver/Inc").mkdir(parents=True)
    report = inspect_keil(root)
    assert report.framework == "hal"
    assert report.framework_candidates == ("hal",)


def test_framework_ll_two_categories(tmp_path: Path) -> None:
    root = tmp_path / "root"
    simple_project(
        root,
        defines="USE_FULL_LL_DRIVER",
        sources={
            ".\\Drivers\\STM32F4xx_HAL_Driver\\Src\\stm32f4xx_ll_gpio.c": "int ll_gpio;\n"
        },
        extra={
            "groups": [
                {
                    "name": "G",
                    "files": [
                        {
                            "name": "stm32f4xx_ll_gpio.c",
                            "path": ".\\Drivers\\STM32F4xx_HAL_Driver\\Src\\stm32f4xx_ll_gpio.c",
                        }
                    ],
                }
            ]
        },
    )
    report = inspect_keil(root)
    assert report.framework == "ll"
    assert report.framework_candidates == ("hal", "ll")


def test_framework_hal_via_include_evidence(tmp_path: Path) -> None:
    root = tmp_path / "root"
    simple_project(
        root,
        defines="USE_HAL_DRIVER",
        sources={".\\Src\\a.c": '#include "stm32f4xx_hal.h"\nint a;\n'},
    )
    report = inspect_keil(root)
    assert report.framework == "hal"
    categories = {e.category for e in report.framework_evidence if e.framework == "hal"}
    assert categories == {"define", "include"}


def test_framework_ll_via_include_evidence(tmp_path: Path) -> None:
    root = tmp_path / "root"
    simple_project(
        root,
        defines="USE_FULL_LL_DRIVER",
        sources={".\\Src\\a.c": '#include "stm32f4xx_ll_gpio.h"\nint a;\n'},
    )
    report = inspect_keil(root)
    assert report.framework == "ll"


def test_framework_single_category_ambiguous(tmp_path: Path) -> None:
    root = tmp_path / "root"
    simple_project(root, defines="USE_HAL_DRIVER")
    report = inspect_keil(root)
    assert report.framework is None
    assert report.framework_candidates == ("hal",)
    assert "KEIL_FRAMEWORK_SELECTION_REQUIRED" in [w.code for w in report.warnings]


def test_framework_conflicting_evidence(tmp_path: Path) -> None:
    root = tmp_path / "root"
    simple_project(
        root,
        defines="USE_HAL_DRIVER,USE_STDPERIPH_DRIVER",
        include_paths="Drivers/STM32F4xx_HAL_Driver/Inc;Libraries/STM32F4xx_StdPeriph_Driver/inc",
    )
    (root / "Drivers/STM32F4xx_HAL_Driver/Inc").mkdir(parents=True)
    (root / "Libraries/STM32F4xx_StdPeriph_Driver/inc").mkdir(parents=True)
    report = inspect_keil(root)
    assert report.framework is None
    assert report.framework_candidates == ("hal", "spl")
    assert "KEIL_FRAMEWORK_SELECTION_REQUIRED" in [w.code for w in report.warnings]


def test_no_framework_evidence_no_warning(tmp_path: Path) -> None:
    root = tmp_path / "root"
    simple_project(root)
    report = inspect_keil(root)
    assert report.framework is None
    assert report.framework_candidates == ()
    assert report.framework_evidence == ()
    assert not any(w.code == "KEIL_FRAMEWORK_SELECTION_REQUIRED" for w in report.warnings)


# ---------------------------------------------------------------------------
# determinism and read-only guarantees
# ---------------------------------------------------------------------------


def test_repeated_inspection_equal_serialization(keil_project: Path) -> None:
    first = inspect_keil(keil_project).to_dict()
    second = inspect_keil(keil_project).to_dict()
    assert first == second


def test_inspection_read_only_snapshot(keil_project: Path) -> None:
    before = snapshot_tree(keil_project)
    inspect_keil(keil_project)
    inspect_keil(keil_project, uvprojx=keil_project / "legacy.uvprojx", target_name="Legacy")
    after = snapshot_tree(keil_project)
    assert after == before


# ---------------------------------------------------------------------------
# additional branch coverage
# ---------------------------------------------------------------------------


def test_linker_section_input_finding(tmp_path: Path) -> None:
    root = tmp_path / "root"
    simple_project(root, scatter=".\\Objects\\app.sct", ld_misc=" --keep section(.myregion) ")
    report = inspect_keil(root)
    custom = [f for f in report.findings if f.rule_id == "ARMCC_CUSTOM_SECTION" and f.line == 0]
    assert len(custom) == 1
    assert custom[0].path == "Objects/app.sct"
    assert custom[0].severity == "warning"
    assert report.output.scatter_file == "Objects/app.sct"


def test_unreadable_source_warning(tmp_path: Path) -> None:
    root = tmp_path / "root"
    simple_project(root, sources={".\\Src\\a.c": "int a;\n"})
    (root / "Src" / "a.c").chmod(0)
    try:
        report = inspect_keil(root)
        assert "KEIL_SOURCE_UNAVAILABLE" in [w.code for w in report.warnings]
        assert all(d.path != "Src/a.c" for d in report.inputs)
    finally:
        (root / "Src" / "a.c").chmod(0o644)


def test_scanner_edge_cases(tmp_path: Path) -> None:
    root = tmp_path / "root"
    content = (
        'char *unterminated = "abc\n'          # unterminated string to EOF
        "/* unterminated block comment"        # unterminated comment to EOF
    )
    xml = project_xml(
        {
            "name": "T",
            "groups": [{"name": "G", "files": [{"name": "a.c", "path": ".\\Src\\a.c"}]}],
        }
    )
    write_project(root, xml, {".\\Src\\a.c": content})
    assert inspect_keil(root).findings == ()

    root2 = tmp_path / "root2"
    content2 = (
        "// line comment to EOF __irq"
    )
    write_project(root2, project_xml({"name": "T", "groups": [{"name": "G", "files": [{"name": "a.c", "path": ".\\Src\\a.c"}]}]}), {".\\Src\\a.c": content2})
    assert inspect_keil(root2).findings == ()

    root3 = tmp_path / "root3"
    content3 = (
        "int x = __WFI;\n"
        "int y = __at;\n"
        "__attribute__ without parens\n"
        "__attribute__((unbalanced\n"
        'char *esc = "a\\"b";\n'
        "/* closed */ __irq void f(void);\n"
    )
    write_project(
        root3,
        project_xml({"name": "T", "groups": [{"name": "G", "files": [{"name": "a.c", "path": ".\\Src\\a.c"}]}]}),
        {".\\Src\\a.c": content3},
    )
    report = inspect_keil(root3)
    rules = [f.rule_id for f in report.findings]
    assert rules == ["ARMCC_IRQ_QUALIFIER"]

    root4 = tmp_path / "root4"
    write_project(
        root4,
        project_xml({"name": "T", "groups": [{"name": "G", "files": [{"name": "a.c", "path": ".\\Src\\a.c"}]}]}),
        {".\\Src\\a.c": "int x;\n__asm"},  # __asm at EOF: no classification
    )
    assert inspect_keil(root4).findings == ()


def test_asm_line_comment_to_eof(tmp_path: Path) -> None:
    root = tmp_path / "root"
    xml = project_xml(
        {
            "name": "T",
            "groups": [{"name": "G", "files": [{"name": "a.s", "path": ".\\Startup\\a.s", "filetype": "2"}]}],
        }
    )
    write_project(root, xml, {".\\Startup\\a.s": "; __irq __nop() __WFI()"})
    assert inspect_keil(root).findings == ()


def test_empty_source_path_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    xml = project_xml(
        {"name": "T", "groups": [{"name": "G", "files": [{"name": "", "path": ""}]}]}
    )
    write_project(root, xml)
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(root)
    assert error.value.code == "KEIL_TARGET_INVALID"
    assert error.value.details == {"field": "source", "rule": "missing"}


def test_include_path_dot(tmp_path: Path) -> None:
    root = tmp_path / "root"
    simple_project(root, include_paths=".")
    report = inspect_keil(root)
    assert report.include_paths == (".",)
    assert "KEIL_INCLUDE_PATH_MISSING" not in [w.code for w in report.warnings]


def test_include_path_dot_nested(tmp_path: Path) -> None:
    root = tmp_path / "root"
    nested = root / "Nested"
    simple_project(nested, include_paths=".")
    report = inspect_keil(root, uvprojx=nested / "proj.uvprojx")
    assert report.include_paths == ("Nested",)
    assert "KEIL_INCLUDE_PATH_MISSING" not in [w.code for w in report.warnings]


def test_scatter_file_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(uvprojx_mod.armcc_scan, "SCAN_FILE_LIMIT", 100)
    root = tmp_path / "root"
    simple_project(root, scatter=".\\Objects\\app.sct")
    (root / "Objects").mkdir()
    (root / "Objects" / "app.sct").write_text("x" * 200, encoding="utf-8")
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(root)
    assert error.value.code == "KEIL_SCAN_LIMIT_EXCEEDED"
    assert error.value.details == {"limitBytes": 100, "scope": "file"}


def test_compiler_uac6_fallback(tmp_path: Path) -> None:
    root = tmp_path / "root"
    simple_project(root, pcc_used="", extra={"uac6": "1"})
    report = inspect_keil(root)
    assert report.compiler == "armclang"
    assert report.compiler_version is None


def test_library_linker_inputs(tmp_path: Path) -> None:
    root = tmp_path / "root"
    xml = project_xml(
        {
            "name": "T",
            "groups": [
                {
                    "name": "G",
                    "files": [
                        {"name": "a.c", "path": ".\\Src\\a.c"},
                        {"name": "libarm.a", "path": ".\\Lib\\libarm.a", "filetype": "4"},
                    ],
                }
            ],
        }
    )
    write_project(root, xml, {".\\Src\\a.c": "int a;\n", ".\\Lib\\libarm.a": b"AR"})
    report = inspect_keil(root)
    assert report.linker_inputs == ("Lib/libarm.a",)
    assert report.sources[1].language == "library"
    assert all(d.path != "Lib/libarm.a" for d in report.inputs)


def test_stdlib_periph_driver_define_evidence(tmp_path: Path) -> None:
    root = tmp_path / "root"
    simple_project(
        root,
        defines="STM32F4xx_StdPeriph_Driver",
        include_paths="Libraries/STM32F4xx_StdPeriph_Driver/inc",
    )
    (root / "Libraries/STM32F4xx_StdPeriph_Driver/inc").mkdir(parents=True)
    report = inspect_keil(root)
    assert report.framework == "spl"


def test_project_directory_only_not_found(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "dir.uvprojx").mkdir()
    with pytest.raises(KeilInspectionError) as error:
        inspect_keil(root)
    assert error.value.code == "KEIL_PROJECT_NOT_FOUND"
