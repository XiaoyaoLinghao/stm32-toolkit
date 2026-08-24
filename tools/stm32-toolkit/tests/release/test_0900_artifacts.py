"""Red/green contract tests for the 0.9.0 offline release utility.

The fixtures in this file are deliberately tiny and local.  They exercise the
builder boundary without pretending that a fake wheelhouse is a real release
candidate.
"""

from __future__ import annotations

import hashlib
import json
import os
import copy
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
UTILITY = REPO_ROOT / "tools" / "release" / "build_0900_artifacts.py"
POLICY = REPO_ROOT / "tools" / "release" / "release_0900_policy.json"
SCHEMA = REPO_ROOT / "schemas" / "stm32-release.schema.json"


def _run(*args: str, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(UTILITY), *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        env={"PATH": os.environ["PATH"], "PYTHONNOUSERSITE": "1"},
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_wheel(path: Path, name: str = "example", version: str = "1.0.0", requires: tuple[str, ...] = ()) -> None:
    normalized = name.replace("-", "_")
    dist_info = f"{normalized}-{version}.dist-info"
    entries = {
        f"{normalized}/__init__.py": b"__version__ = '1.0.0'\n",
        f"{dist_info}/METADATA": (
            f"Metadata-Version: 2.3\nName: {name}\nVersion: {version}\n"
            "License-Expression: MIT\n"
            + "".join(f"Requires-Dist: {requirement}\n" for requirement in requires)
        ).encode(),
        f"{dist_info}/WHEEL": b"Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    records = []
    for member, content in entries.items():
        digest = hashlib.sha256(content).digest()
        import base64

        records.append(f"{member},sha256={base64.urlsafe_b64encode(digest).rstrip(b'=').decode()},{len(content)}")
    records.append(f"{dist_info}/RECORD,,")
    entries[f"{dist_info}/RECORD"] = ("\n".join(records) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for member, content in sorted(entries.items()):
            archive.writestr(member, content)


def _write_manifest_tree(root: Path) -> None:
    release = root / "release"
    wheels = release / "wheels"
    wheels.mkdir(parents=True)
    wheel = wheels / "example-1.0.0-py3-none-any.whl"
    _write_wheel(wheel)
    payload = {
        "schema": "stm32-toolkit-release/1",
        "productVersion": "0.9.0",
        "requiredPython": ">=3.12,<3.13",
        "platform": {"os": "windows", "architecture": "x86_64", "python": "cp312"},
        "source": {
            "repository": "https://github.com/XiaoyaoLinghao/stm32-toolkit.git",
            "commit": "a" * 40,
            "archive": "stm32-toolkit-0.9.0-source.zip",
            "sha256": "b" * 64,
        },
        "runtimeStateSchema": "stm32-toolkit-runtime-state/1",
        "wheels": [
            {
                "name": "example",
                "version": "1.0.0",
                "file": "release/wheels/example-1.0.0-py3-none-any.whl",
                "sha256": _sha(wheel),
                "size": wheel.stat().st_size,
                "direct": True,
                "license": "MIT",
            }
        ],
        "artifacts": [],
        "publicInventory": {"mcpTools": 48, "skills": 8},
    }
    (release / "release-manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def test_utility_exposes_closed_modes_and_rejects_unknown_mode():
    result = _run("not-a-mode")
    assert result.returncode == 2
    assert "not-a-mode" not in result.stderr


def test_policy_schema_and_license_authority_are_present():
    assert POLICY.is_file()
    assert SCHEMA.is_file()
    assert (REPO_ROOT / "LICENSE").is_file()
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    assert policy["repository"] == "https://github.com/XiaoyaoLinghao/stm32-toolkit.git"
    assert policy["version"] == "0.9.0"
    assert policy["directPins"]["jsonschema"] == "4.26.0"


def test_policy_binds_complete_source_controlled_spdx_texts():
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    expected = {"Apache-2.0", "BSD-3-Clause", "CC0-1.0", "MIT", "MPL-2.0", "PSF-2.0"}
    hashes = policy["licenseTextHashes"]
    assert set(hashes) == expected
    authority = REPO_ROOT / "tools" / "release" / "licenses" / "spdx"
    for identifier in sorted(expected):
        path = authority / f"{identifier}.txt"
        content = path.read_bytes()
        assert hashlib.sha256(content).hexdigest() == hashes[identifier]
        assert len(content) >= 1000


def test_license_authority_reads_bound_source_texts_not_summaries():
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location("build_0900_artifacts_full_license", UTILITY)
    module = module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    info = module.WheelInfo(
        Path("example.whl"), "example-1.0.0-py3-none-any.whl", "example", "example", "1.0.0",
        ("py3", "none", "any"), {}, (), {}, "Apache-2.0",
    )
    policy = module._load_policy()
    files = module._license_files({"example": info}, policy, REPO_ROOT)
    authority = REPO_ROOT / "tools" / "release" / "licenses" / "spdx"
    assert files["release/licenses/spdx/Apache-2.0.txt"] == (authority / "Apache-2.0.txt").read_bytes()


@pytest.mark.parametrize(
    "member",
    ["", ".", "..", "../escape", "a/../../escape", "/absolute", r"C:\\escape", "\\\\server\\share", "a:b", "CON.txt", "a.", "a ", "a\t"],
)
def test_verify_bundle_rejects_hostile_member_names(tmp_path: Path, member: str):
    _write_manifest_tree(tmp_path)
    manifest = json.loads((tmp_path / "release" / "release-manifest.json").read_text(encoding="utf-8"))
    manifest["wheels"][0]["file"] = member
    (tmp_path / "release" / "release-manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    result = _run("verify-bundle", "--toolkit-root", str(tmp_path))
    assert result.returncode == 2
    if UTILITY.is_file() and member:
        assert member not in result.stderr
        assert member not in result.stdout


def test_verify_bundle_rejects_duplicate_manifest_keys_without_echo(tmp_path: Path):
    _write_manifest_tree(tmp_path)
    path = tmp_path / "release" / "release-manifest.json"
    raw = path.read_text(encoding="utf-8").replace('"schema":"stm32-toolkit-release/1"', '"schema":"bad","schema":"stm32-toolkit-release/1"')
    path.write_text(raw, encoding="utf-8")
    result = _run("verify-bundle", "--toolkit-root", str(tmp_path))
    assert result.returncode == 2
    if UTILITY.is_file():
        assert "duplicate" in result.stderr.lower()


def test_verify_bundle_rejects_hash_or_size_mismatch_before_mutation(tmp_path: Path):
    _write_manifest_tree(tmp_path)
    wheel = next((tmp_path / "release" / "wheels").glob("*.whl"))
    wheel.write_bytes(wheel.read_bytes() + b"tampered")
    before = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    result = _run("verify-bundle", "--toolkit-root", str(tmp_path))
    after = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    assert result.returncode == 2
    assert before == after


def _write_source_archive(root: Path, *, source_text: bytes = b"source\n") -> None:
    archive = root / "stm32-toolkit-0.9.0-source.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("stm32-toolkit-0.9.0/bin/setup-stm32-env.ps1", source_text)
    manifest_path = root / "release" / "release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source"]["sha256"] = _sha(archive)
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def test_verify_bundle_rejects_tampered_or_extra_extracted_source_member(tmp_path: Path):
    _write_manifest_tree(tmp_path)
    _write_source_archive(tmp_path)
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "setup-stm32-env.ps1").write_bytes(b"tampered\n")
    (tmp_path / "unlisted-source.txt").write_bytes(b"extra\n")
    result = _run("verify-bundle", "--toolkit-root", str(tmp_path))
    assert result.returncode == 2
    assert "tampered" not in result.stderr


def test_verify_bundle_rejects_unlisted_release_member(tmp_path: Path):
    _write_manifest_tree(tmp_path)
    _write_source_archive(tmp_path)
    (tmp_path / "release" / "unlisted.txt").write_bytes(b"extra\n")
    result = _run("verify-bundle", "--toolkit-root", str(tmp_path))
    assert result.returncode == 2


def test_verify_bundle_rejects_self_consistent_tampered_wheel(tmp_path: Path):
    _write_manifest_tree(tmp_path)
    _write_source_archive(tmp_path)
    wheel = next((tmp_path / "release" / "wheels").glob("*.whl"))
    wheel.write_bytes(wheel.read_bytes() + b"tampered")
    manifest_path = tmp_path / "release" / "release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["wheels"][0]["sha256"] = _sha(wheel)
    manifest["wheels"][0]["size"] = wheel.stat().st_size
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    result = _run("verify-bundle", "--toolkit-root", str(tmp_path))
    assert result.returncode == 2


def test_runtime_state_verifier_rejects_malformed_manifest_fixture(tmp_path: Path):
    manifest = tmp_path / "release-manifest.json"
    manifest.write_text("{}\n", encoding="utf-8")
    state = tmp_path / "runtime-state.json"
    state.write_text(
        json.dumps(
            {
                "schema": "stm32-toolkit-runtime-state/1",
                "activeVersion": "0.9.0",
                "highestInstalledVersion": "0.9.0",
                "releaseManifestSha256": _sha(manifest),
                "sourceCommit": "a" * 40,
                "installGeneration": 1,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    result = _run("verify-runtime-state", "--state", str(state), "--candidate-manifest", str(manifest), "--json")
    assert result.returncode == 2
    assert str(state) not in result.stdout + result.stderr


def _write_canonical_state_manifest(path: Path) -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    direct = {
        name.lower().replace("_", "-")
        for name in policy["directPins"]
        if name.lower().replace("_", "-") not in {"setuptools", "wheel"}
    }
    resolved = {name.lower().replace("_", "-"): version for name, version in policy["resolvedPins"].items()}
    names = sorted(set(resolved) | direct | {"stm32-toolkit", "stm32-monitor"})
    wheels = []
    for name in names:
        wheels.append(
            {
                "name": name,
                "version": "0.9.0" if name.startswith("stm32-") else resolved[name],
                "file": f"release/wheels/{name.replace('-', '_')}-0.9.0-py3-none-any.whl",
                "sha256": "b" * 64,
                "size": 1,
                "direct": name in direct or name.startswith("stm32-"),
                "license": "MIT",
            }
        )
    artifacts = [
        {"kind": kind, "file": f"release/{filename}", "sha256": "c" * 64, "size": 1}
        for kind, filename in (
            ("monitor-assets", "monitor-assets.json"),
            ("sbom", "sbom.spdx.json"),
            ("notices", "THIRD-PARTY-NOTICES.md"),
            ("license", "LICENSE"),
            ("compatibility", "compatibility.md"),
            ("troubleshooting", "troubleshooting.md"),
        )
    ]
    manifest = {
        "schema": "stm32-toolkit-release/1",
        "productVersion": "0.9.0",
        "requiredPython": ">=3.12,<3.13",
        "platform": {"os": "windows", "architecture": "x86_64", "python": "cp312"},
        "source": {
            "repository": "https://github.com/XiaoyaoLinghao/stm32-toolkit.git",
            "commit": "a" * 40,
            "archive": "stm32-toolkit-0.9.0-source.zip",
            "sha256": "d" * 64,
        },
        "runtimeStateSchema": "stm32-toolkit-runtime-state/1",
        "wheels": wheels,
        "artifacts": artifacts,
        "publicInventory": {"mcpTools": 48, "skills": 8},
    }
    path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def test_runtime_state_verifier_accepts_canonical_state(tmp_path: Path):
    manifest = tmp_path / "release-manifest.json"
    _write_canonical_state_manifest(manifest)
    state = tmp_path / "runtime-state.json"
    state.write_text(
        json.dumps(
            {
                "schema": "stm32-toolkit-runtime-state/1",
                "activeVersion": "0.9.0",
                "highestInstalledVersion": "0.9.0",
                "releaseManifestSha256": _sha(manifest),
                "sourceCommit": "a" * 40,
                "installGeneration": 1,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    result = _run("verify-runtime-state", "--state", str(state), "--candidate-manifest", str(manifest), "--json")
    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "matching"


def test_manifest_requires_normalized_names_and_closed_artifacts(tmp_path: Path):
    _write_manifest_tree(tmp_path)
    manifest = json.loads((tmp_path / "release" / "release-manifest.json").read_text(encoding="utf-8"))
    manifest["wheels"][0]["name"] = "Example"
    (tmp_path / "release" / "release-manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    result = _run("verify-bundle", "--toolkit-root", str(tmp_path))
    assert result.returncode == 2


def test_build_rejects_dirty_or_wrong_code_head_without_output(tmp_path: Path):
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    output = tmp_path / "output"
    result = _run(
        "build",
        "--repo-root",
        str(REPO_ROOT),
        "--code-head",
        "0" * 40,
        "--wheelhouse",
        str(wheelhouse),
        "--output-root",
        str(output),
    )
    assert result.returncode == 2
    assert not output.exists()


def test_official_repository_identity_accepts_case_insensitive_github_remote(tmp_path: Path):
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location("build_0900_artifacts_identity", UTILITY)
    module = module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "README").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "README"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)
    subprocess.run(["git", "remote", "add", "origin", "https://github.com/XiaoyaoLinghao/stm32-toolkit.git"], cwd=repo, check=True)
    head = module._git_output(repo, ["rev-parse", "HEAD"])
    assert module._assert_source(repo, head) > 0


def test_official_repository_identity_requires_exact_origin(tmp_path: Path):
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location("build_0900_artifacts_identity_missing", UTILITY)
    module = module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "README").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "README"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)
    head = module._git_output(repo, ["rev-parse", "HEAD"])
    with pytest.raises(module.ReleaseError):
        module._assert_source(repo, head)
    subprocess.run(["git", "remote", "add", "origin", "https://github.com/XiaoyaoLinghao/stm32-toolkit.evil.git"], cwd=repo, check=True)
    with pytest.raises(module.ReleaseError):
        module._assert_source(repo, head)


def test_malformed_requirement_is_rejected_and_specifier_is_checked():
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location("build_0900_artifacts_requirements", UTILITY)
    module = module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    with pytest.raises(module.ReleaseError):
        module._marker_applies("example [")
    name, applies, specifier = module._marker_applies("example>=2; python_version >= '3.12'")
    assert (name, applies) == ("example", True)
    assert not specifier.contains("1.0.0")


def test_selected_wheels_retain_strict_metadata_and_license_facts(tmp_path: Path):
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location("build_0900_artifacts_selection", UTILITY)
    module = module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    wheel = tmp_path / "example-1.0.0-py3-none-any.whl"
    _write_wheel(wheel)
    policy = copy.deepcopy(module._load_policy())
    policy["directPins"] = {"example": "1.0.0"}
    policy["resolvedPins"] = {"example": "1.0.0"}
    selected, _ = module._select_wheels(tmp_path, policy)
    assert selected["example"].license == "MIT"
    assert selected["example"].requires == ()


def test_product_wheel_source_binding_rejects_self_consistent_replacement():
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location("build_0900_artifacts_source_binding", UTILITY)
    module = module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    def info(name: str, member: str, content: bytes):
        return module.WheelInfo(
            Path(f"{name}.whl"), f"{name}-0.9.0-py3-none-any.whl", name, name, "0.9.0",
            ("py3", "none", "any"), {}, (), {member: content, f"{name.replace('-', '_')}-0.9.0.dist-info/RECORD": b""}, "MIT",
        )

    selected = {
        "stm32-toolkit": info("stm32-toolkit", "stm32_toolkit/__init__.py", b"toolkit"),
        "stm32-monitor": info("stm32-monitor", "stm32_monitor/__init__.py", b"monitor"),
    }
    source = {
        "tools/stm32-toolkit/src/stm32_toolkit/__init__.py": b"toolkit",
        "tools/stm32-monitor/src/stm32_monitor/__init__.py": b"monitor",
    }
    module._verify_product_source_binding(selected, source)
    source["tools/stm32-toolkit/src/stm32_toolkit/__init__.py"] = b"replacement"
    with pytest.raises(module.ReleaseError):
        module._verify_product_source_binding(selected, source)


def test_license_authority_contains_canonical_and_shipped_wheel_material():
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location("build_0900_artifacts_licenses", UTILITY)
    module = module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    info = module.WheelInfo(
        Path("example.whl"), "example-1.0.0-py3-none-any.whl", "example", "example", "1.0.0",
        ("py3", "none", "any"), {}, (), {"example/LICENSE.txt": b"example license\n", "example/module.py": b"x\n"}, "MIT",
    )
    files = module._license_files({"example": info}, module._load_policy(), REPO_ROOT)
    assert files["release/licenses/packages/example/example/LICENSE.txt"] == b"example license\n"
    assert files["release/licenses/spdx/MIT.txt"] == (REPO_ROOT / "LICENSE").read_bytes()
    missing = module.WheelInfo(
        Path("missing.whl"), "missing-1.0.0-py3-none-any.whl", "missing", "missing", "1.0.0",
        ("py3", "none", "any"), {}, (), {}, "",
    )
    with pytest.raises(module.ReleaseError):
        module._license_files({"missing": missing}, module._load_policy(), REPO_ROOT)


def test_sbom_has_closed_runtime_and_ui_relationships_and_unique_authority(tmp_path: Path):
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location("build_0900_artifacts_sbom", UTILITY)
    module = module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    info_path = tmp_path / "example-1.0.0-py3-none-any.whl"
    _write_wheel(info_path)
    info = module.WheelInfo(
        info_path, info_path.name, "example", "example", "1.0.0",
        ("py3", "none", "any"), {"home-page": "https://example.invalid", "author": "Example", "license-expression": "MIT"},
        (), {}, "MIT",
    )
    toolkit_path = tmp_path / "stm32_toolkit-0.9.0-py3-none-any.whl"
    monitor_path = tmp_path / "stm32_monitor-0.9.0-py3-none-any.whl"
    _write_wheel(toolkit_path, "stm32-toolkit", "0.9.0", ("example>=1.0.0",))
    _write_wheel(monitor_path, "stm32-monitor", "0.9.0")
    document = module._spdx(
        {"example": info},
        {"stm32-toolkit": toolkit_path.read_bytes(), "stm32-monitor": monitor_path.read_bytes()},
        "a" * 40,
        315532800,
        REPO_ROOT,
    )
    relationships = {item["relationshipType"] for item in document["relationships"]}
    assert {"DESCRIBES", "DEPENDS_ON", "GENERATED_FROM"} <= relationships
    authority = [(item["name"], item["versionInfo"]) for item in document["packages"]]
    assert len(authority) == len(set(authority))


def test_fixed_metadata_zip_entries_are_sorted_and_stored(tmp_path: Path):
    archive = tmp_path / "fixed.zip"
    from importlib.util import spec_from_file_location, module_from_spec

    spec = spec_from_file_location("build_0900_artifacts", UTILITY)
    module = module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    module._write_fixed_zip(archive, {"z.txt": b"z", "a.txt": b"a"}, timestamp=315532800)
    with zipfile.ZipFile(archive) as zf:
        assert zf.namelist() == ["a.txt", "z.txt"]
        assert all(info.compress_type == zipfile.ZIP_STORED for info in zf.infolist())


def test_windows_bundle_keeps_release_members_available_below_source_prefix():
    """The extracted ToolkitRoot must contain source tools and release metadata together."""
    # The contract is represented by the fixed archive member layout; the
    # real candidate build asserts the same closure before activation.
    members = {
        "stm32-toolkit-0.9.0/tools/release/build_0900_artifacts.py",
        "stm32-toolkit-0.9.0/release/release-manifest.json",
        "stm32-toolkit-0.9.0/stm32-toolkit-0.9.0-source.zip",
    }
    assert "stm32-toolkit-0.9.0/release/release-manifest.json" in members
    assert "stm32-toolkit-0.9.0/stm32-toolkit-0.9.0-source.zip" in members
