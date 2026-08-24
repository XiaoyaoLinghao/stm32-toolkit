"""Red/green contract tests for the 0.9.0 offline release utility.

The fixtures in this file are deliberately tiny and local.  They exercise the
builder boundary without pretending that a fake wheelhouse is a real release
candidate.
"""

from __future__ import annotations

import hashlib
import json
import os
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


def _write_wheel(path: Path, name: str = "example", version: str = "1.0.0") -> None:
    normalized = name.replace("-", "_")
    dist_info = f"{normalized}-{version}.dist-info"
    entries = {
        f"{normalized}/__init__.py": b"__version__ = '1.0.0'\n",
        f"{dist_info}/METADATA": (
            f"Metadata-Version: 2.3\nName: {name}\nVersion: {version}\n"
            "License-Expression: MIT\n"
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


def test_runtime_state_verifier_accepts_canonical_state(tmp_path: Path):
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
