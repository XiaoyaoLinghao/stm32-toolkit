from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
UTILITY = REPO_ROOT / "tools" / "release" / "build_0900_artifacts.py"


@pytest.fixture(scope="module")
def release_module():
    spec = importlib.util.spec_from_file_location("stm32tk_release_0900_security", UTILITY)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "value",
    [
        "../escape",
        "/absolute",
        "//server/share",
        r"C:\\absolute",
        "C:relative",
        r"\\?\C:\\device",
        "payload:stream",
        "payload\x00name",
        "payload\r\nname",
        "payload\tname",
        "payload\x7fname",
        "payload${TOKEN}",
        "payload&whoami",
        "payload|whoami",
        "%PATH%",
        "CON.txt",
        "LPT9.foo",
        "payload.",
        "payload ",
        "e\u0301.txt",
        "a/" + ("x" * 256),
        "a/" + ("x" * 4097),
    ],
)
def test_hostile_release_member_name_fails_closed(release_module, value: str):
    with pytest.raises(release_module.ReleaseError):
        release_module._validate_safe_relative(value)


def test_duplicate_json_keys_are_rejected_without_value_echo(release_module):
    with pytest.raises(release_module.ReleaseError, match="duplicate JSON key") as caught:
        release_module._strict_json(b'{"safe":1,"safe":2}', limit=1024)
    assert "safe" not in str(caught.value)


def test_case_folded_manifest_paths_are_rejected_before_reads(release_module, tmp_path: Path):
    release = tmp_path / "release"
    wheels = release / "wheels"
    wheels.mkdir(parents=True)
    manifest = {
        "schema": "stm32-toolkit-release/1",
        "productVersion": "0.9.0",
        "requiredPython": ">=3.12,<3.13",
        "platform": {"os": "windows", "architecture": "x86_64", "python": "cp312"},
        "source": {"repository": "https://github.com/XiaoyaoLinghao/stm32-toolkit.git", "commit": "a" * 40, "archive": "SOURCE.ZIP", "sha256": "a" * 64},
        "runtimeStateSchema": "stm32-toolkit-runtime-state/1",
        "wheels": [
            {"name": "one", "version": "1.0", "file": "release/wheels/A.whl", "sha256": "a" * 64, "size": 1, "direct": True, "license": "MIT"},
            {"name": "two", "version": "1.0", "file": "release/wheels/a.whl", "sha256": "b" * 64, "size": 1, "direct": False, "license": "MIT"},
        ],
        "artifacts": [],
        "publicInventory": {"mcpTools": 48, "skills": 8},
    }
    path = release / "release-manifest.json"
    path.write_text(json.dumps(manifest, separators=(",", ":")) + "\n", encoding="utf-8")
    with pytest.raises(release_module.ReleaseError):
        release_module._load_manifest(path)


def test_runtime_state_rejects_boolean_generation_and_future_schema(release_module, tmp_path: Path):
    state = tmp_path / "runtime-state.json"
    manifest = tmp_path / "release-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "stm32-toolkit-release/1",
                "productVersion": "0.9.0",
                "requiredPython": ">=3.12,<3.13",
                "platform": {"os": "windows", "architecture": "x86_64", "python": "cp312"},
                "source": {"repository": "https://github.com/XiaoyaoLinghao/stm32-toolkit.git", "commit": "a" * 40, "archive": "source.zip", "sha256": "a" * 64},
                "runtimeStateSchema": "stm32-toolkit-runtime-state/1",
                "wheels": [],
                "artifacts": [],
                "publicInventory": {"mcpTools": 48, "skills": 8},
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    base = {
        "activeVersion": "0.9.0",
        "highestInstalledVersion": "0.9.0",
        "releaseManifestSha256": "a" * 64,
        "sourceCommit": "a" * 40,
        "installGeneration": True,
    }
    state.write_text(json.dumps({"schema": "stm32-toolkit-runtime-state/1", **base}) + "\n", encoding="utf-8")
    status, _ = release_module._verify_runtime_state(state, manifest)
    assert status == "invalid"
    state.write_text(json.dumps({"schema": "stm32-toolkit-runtime-state/999", **{**base, "installGeneration": 1}}) + "\n", encoding="utf-8")
    status, _ = release_module._verify_runtime_state(state, manifest)
    assert status == "unsupported"


def test_runtime_state_refuses_a_recorded_higher_version_before_mutation(release_module, tmp_path: Path):
    manifest = tmp_path / "release-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "stm32-toolkit-release/1",
                "productVersion": "0.9.0",
                "requiredPython": ">=3.12,<3.13",
                "platform": {"os": "windows", "architecture": "x86_64", "python": "cp312"},
                "source": {"repository": "https://github.com/XiaoyaoLinghao/stm32-toolkit.git", "commit": "a" * 40, "archive": "source.zip", "sha256": "a" * 64},
                "runtimeStateSchema": "stm32-toolkit-runtime-state/1",
                "wheels": [],
                "artifacts": [],
                "publicInventory": {"mcpTools": 48, "skills": 8},
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    state = tmp_path / "runtime-state.json"
    state.write_text(
        json.dumps(
            {
                "schema": "stm32-toolkit-runtime-state/1",
                "activeVersion": "1.0.0",
                "highestInstalledVersion": "1.0.0",
                "releaseManifestSha256": "a" * 64,
                "sourceCommit": "a" * 40,
                "installGeneration": 4,
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    before = state.read_bytes()
    status, payload = release_module._verify_runtime_state(state, manifest)
    assert status == "downgrade-refused"
    assert payload["status"] == "downgrade-refused"
    assert state.read_bytes() == before


def test_runtime_state_malformed_json_is_reported_as_invalid(release_module, tmp_path: Path):
    manifest = tmp_path / "release-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "stm32-toolkit-release/1",
                "productVersion": "0.9.0",
                "requiredPython": ">=3.12,<3.13",
                "platform": {"os": "windows", "architecture": "x86_64", "python": "cp312"},
                "source": {"repository": "https://github.com/XiaoyaoLinghao/stm32-toolkit.git", "commit": "a" * 40, "archive": "source.zip", "sha256": "a" * 64},
                "runtimeStateSchema": "stm32-toolkit-runtime-state/1",
                "wheels": [],
                "artifacts": [],
                "publicInventory": {"mcpTools": 48, "skills": 8},
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    state = tmp_path / "runtime-state.json"
    state.write_text("{malformed\n", encoding="utf-8")
    status, payload = release_module._verify_runtime_state(state, manifest)
    assert status == "invalid"
    assert payload["status"] == "invalid"
