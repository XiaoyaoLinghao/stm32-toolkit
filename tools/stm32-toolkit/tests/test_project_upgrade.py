from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType

import pytest

from stm32_toolkit import __version__
import stm32_toolkit.project_upgrade as upgrade_mod
from stm32_toolkit.project_model import ProjectManifestError, load_project_model
from stm32_toolkit.project_upgrade import (
    ProjectUpgradeError,
    UpgradePlan,
    apply_project_upgrade,
    apply_project_v2_to_v3_upgrade,
    plan_project_upgrade,
    plan_project_v2_to_v3_upgrade,
    upgrade_project_v2_to_v3,
)

MANIFEST_NAME = ".stm32-project.json"
V1_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "valid-project.json"
legacy_plan_project_upgrade = plan_project_upgrade
legacy_apply_project_upgrade = apply_project_upgrade
# The remaining regression cases exercise the independent v2-to-v3 route.
plan_project_upgrade = plan_project_v2_to_v3_upgrade
apply_project_upgrade = apply_project_v2_to_v3_upgrade


def _v2_payload() -> dict:
    return {
        "schemaVersion": 2,
        "logicalProjectId": "12345678-1234-5678-1234-567812345678",
        "generatedBy": {"tool": "stm32-toolkit", "version": __version__},
        "project": {"name": "firmware", "origin": "manual"},
        "target": {"device": "STM32F429ZGTx", "core": "cortex-m4"},
        "framework": {"type": "spl", "version": None},
        "build": {
            "sources": ["App/main.c"], "includePaths": [], "defines": [],
            "compileOptions": [], "assemblySources": [], "presets": [],
            "elf": "build-fw/firmware.elf",
        },
        "memory": {"source": "manual", "regions": []},
        "debug": {"backend": "pyocd", "target": "stm32f429zgtx", "svd": None},
        "generation": {
            "cubeMxIoc": None,
            "managedManifest": ".stm32-toolkit/generated-files.json",
            "generatedDirectories": [], "userDirectories": [],
        },
    }


def _write_v2(root: Path, *, newline: str = "\n") -> tuple[Path, str]:
    text = json.dumps(_v2_payload(), indent=2, ensure_ascii=False) + newline
    path = root / MANIFEST_NAME
    path.write_text(text, encoding="utf-8", newline="")
    return path, text


def _inventory(root: Path) -> dict[str, tuple[int, int]]:
    return {
        str(path.relative_to(root)): (path.stat().st_mtime_ns, path.stat().st_size)
        for path in sorted(root.rglob("*"))
    }


def test_v2_to_v3_plan_is_read_only_and_freezes_exact_candidate_and_diff(tmp_path: Path):
    manifest_path, source = _write_v2(tmp_path)
    before = _inventory(tmp_path)

    plan = plan_project_v2_to_v3_upgrade(tmp_path)

    assert manifest_path.read_text(encoding="utf-8") == source
    assert _inventory(tmp_path) == before
    assert plan.manifest_path == manifest_path.resolve()
    assert plan.source_sha256 == sha256(source.encode("utf-8")).hexdigest()
    assert (plan.from_version, plan.to_version) == (2, 3)
    assert plan.candidate == source.replace('"schemaVersion": 2', '"schemaVersion": 3', 1)
    assert plan.diff == (
        "--- .stm32-project.json (v2)\n"
        "+++ .stm32-project.json (v3)\n"
        "@@ -1,5 +1,5 @@\n"
        " {\n"
        '-  "schemaVersion": 2,\n'
        '+  "schemaVersion": 3,\n'
        '   "logicalProjectId": "12345678-1234-5678-1234-567812345678",\n'
        '   "generatedBy": {\n'
        '     "tool": "stm32-toolkit",\n'
    )
    assert len(plan.plan_digest) == len(plan.action_digest) == 64
    assert plan.plan_digest != plan.action_digest


def test_named_v2_to_v3_route_matches_public_planner(tmp_path: Path):
    _write_v2(tmp_path)
    first = upgrade_project_v2_to_v3(tmp_path)
    second = plan_project_v2_to_v3_upgrade(tmp_path)
    assert (first.candidate, first.diff, first.plan_digest, first.action_digest) == (
        second.candidate, second.diff, second.plan_digest, second.action_digest
    )


def test_plan_and_action_digests_bind_the_exact_frozen_upgrade(tmp_path: Path):
    _write_v2(tmp_path)
    plan = plan_project_v2_to_v3_upgrade(tmp_path)
    bound_plan = {
        "manifestPath": str(plan.manifest_path),
        "sourceSha256": plan.source_sha256,
        "fromVersion": 2,
        "toVersion": 3,
        "candidate": plan.candidate,
        "diff": plan.diff,
        "rootIdentity": dict(plan.root_identity),
        "manifestIdentity": dict(plan.manifest_identity),
    }
    expected_plan = sha256(
        json.dumps(
            bound_plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()
    expected_action = sha256(
        json.dumps(
            {
                "operation": "project.upgrade.v2-to-v3.apply",
                "planDigest": expected_plan,
                "sourceSha256": plan.source_sha256,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert plan.plan_digest == expected_plan
    assert plan.action_digest == expected_action


def test_plan_preserves_source_order_whitespace_and_newline(tmp_path: Path):
    payload = _v2_payload()
    source = json.dumps(payload, separators=(",", ": "), ensure_ascii=False)
    source = source.replace('{"schemaVersion": 2', '{  "schemaVersion": 2')
    (tmp_path / MANIFEST_NAME).write_text(source, encoding="utf-8", newline="")

    plan = plan_project_v2_to_v3_upgrade(tmp_path)

    assert plan.candidate == source.replace('"schemaVersion": 2', '"schemaVersion": 3', 1)
    assert not plan.candidate.endswith("\n")
    assert list(json.loads(plan.candidate)) == list(payload)


def test_proposed_is_recursively_immutable_valid_v3_and_has_no_testing(tmp_path: Path):
    _write_v2(tmp_path)
    plan = plan_project_v2_to_v3_upgrade(tmp_path)
    assert isinstance(plan.proposed, MappingProxyType)
    assert isinstance(plan.proposed["project"], MappingProxyType)
    assert isinstance(plan.proposed["build"]["sources"], tuple)
    assert plan.proposed["schemaVersion"] == 3
    assert "testing" not in plan.proposed
    with pytest.raises(TypeError):
        plan.proposed["schemaVersion"] = 2


def test_public_legacy_route_plans_v1_to_v2(tmp_path: Path):
    (tmp_path / MANIFEST_NAME).write_bytes(V1_FIXTURE.read_bytes())
    plan = legacy_plan_project_upgrade(tmp_path)
    assert (plan.from_version, plan.to_version) == (1, 2)
    assert plan.proposed["schemaVersion"] == 2
    result = legacy_apply_project_upgrade(plan, plan.action_digest, plan.plan_digest)
    assert result.ok is True
    assert load_project_model(tmp_path).schema_version == 2


def test_v3_returns_not_required(tmp_path: Path):
    payload = _v2_payload()
    payload["schemaVersion"] = 3
    (tmp_path / MANIFEST_NAME).write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ProjectUpgradeError) as caught:
        plan_project_v2_to_v3_upgrade(tmp_path)
    assert caught.value.code == "PROJECT_UPGRADE_NOT_REQUIRED"
    assert caught.value.details == {"schemaVersion": 3, "route": "v2-to-v3"}


@pytest.mark.parametrize("version", [0, 4, 99])
def test_unsupported_integer_version_returns_stable_error(tmp_path: Path, version: int):
    payload = _v2_payload()
    payload["schemaVersion"] = version
    (tmp_path / MANIFEST_NAME).write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ProjectUpgradeError) as caught:
        plan_project_v2_to_v3_upgrade(tmp_path)
    assert caught.value.code == "PROJECT_SCHEMA_VERSION_UNSUPPORTED"
    assert caught.value.details == {"schemaVersion": version, "supported": [1, 2, 3]}


@pytest.mark.parametrize("version", [True, 2.0, "2"])
def test_non_integer_schema_version_is_rejected(tmp_path: Path, version: object):
    payload = _v2_payload()
    payload["schemaVersion"] = version
    (tmp_path / MANIFEST_NAME).write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ProjectManifestError) as caught:
        plan_project_v2_to_v3_upgrade(tmp_path)
    assert caught.value.details == {"field": "schemaVersion", "rule": "type"}


def test_apply_requires_exact_action_digest_and_plan_digest(tmp_path: Path):
    manifest_path, source = _write_v2(tmp_path)
    plan = plan_project_upgrade(tmp_path)
    denied = apply_project_upgrade(plan, False, plan.plan_digest)
    assert denied.code == "PROJECT_UPGRADE_AUTHORIZATION_REQUIRED"
    assert apply_project_upgrade(plan, plan.action_digest, plan.plan_digest).code == "PROJECT_UPGRADE_AUTHORIZATION_CONSUMED"
    assert manifest_path.read_text(encoding="utf-8") == source


def test_authorized_apply_writes_exact_candidate_and_reports_digests(tmp_path: Path):
    manifest_path, _ = _write_v2(tmp_path)
    plan = plan_project_upgrade(tmp_path)
    result = apply_project_upgrade(plan, plan.action_digest, plan.plan_digest)
    assert result.ok is True
    assert result.data == {
        "path": str(manifest_path.resolve()), "fromVersion": 2, "toVersion": 3,
        "sourceSha256": plan.source_sha256,
        "resultSha256": sha256(plan.candidate.encode("utf-8")).hexdigest(),
        "planDigest": plan.plan_digest, "actionDigest": plan.action_digest,
    }
    assert manifest_path.read_text(encoding="utf-8") == plan.candidate
    assert load_project_model(tmp_path).schema_version == 3
    assert sorted(path.name for path in tmp_path.iterdir()) == [MANIFEST_NAME]


def test_authorization_is_single_use(tmp_path: Path):
    _write_v2(tmp_path)
    plan = plan_project_upgrade(tmp_path)
    first = apply_project_upgrade(plan, plan.action_digest, plan.plan_digest)
    second = apply_project_upgrade(plan, plan.action_digest, plan.plan_digest)
    assert first.ok is True
    assert second.code == "PROJECT_UPGRADE_AUTHORIZATION_CONSUMED"


def test_consumption_survives_registry_loss_like_a_later_process(tmp_path: Path):
    _write_v2(tmp_path)
    plan = plan_project_upgrade(tmp_path)
    assert apply_project_upgrade(plan, False, plan.plan_digest).code == "PROJECT_UPGRADE_AUTHORIZATION_REQUIRED"
    upgrade_mod._PREPARED.clear()
    equivalent = replace(plan)
    assert apply_project_upgrade(equivalent, equivalent.action_digest, equivalent.plan_digest).code == "PROJECT_UPGRADE_AUTHORIZATION_CONSUMED"


def test_same_path_project_root_replacement_is_consumed_and_not_written(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    _write_v2(root)
    plan = plan_project_upgrade(root)
    old = tmp_path / "old-project"
    root.rename(old)
    root.mkdir()
    replacement_path, replacement = _write_v2(root)
    result = apply_project_upgrade(plan, plan.action_digest, plan.plan_digest)
    assert result.code == "PROJECT_CHANGED_SINCE_PLAN"
    assert replacement_path.read_text(encoding="utf-8") == replacement
    assert apply_project_upgrade(plan, plan.action_digest, plan.plan_digest).code == "PROJECT_UPGRADE_AUTHORIZATION_CONSUMED"


def test_supported_writer_queues_on_shared_lock_then_apply_detects_change(tmp_path: Path):
    from threading import Event, Thread
    manifest, source = _write_v2(tmp_path)
    plan = plan_project_upgrade(tmp_path)
    started = Event()
    results = []
    with upgrade_mod.project_mutation_lock(tmp_path):
        thread = Thread(target=lambda: (started.set(), results.append(apply_project_upgrade(plan, plan.action_digest, plan.plan_digest))))
        thread.start()
        assert started.wait(2)
        manifest.write_text(source + " ", encoding="utf-8", newline="")
    thread.join(5)
    assert results[0].code == "PROJECT_CHANGED_SINCE_PLAN"


def test_concurrent_apply_consumes_exactly_once(tmp_path: Path):
    _write_v2(tmp_path)
    plan = plan_project_upgrade(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: apply_project_upgrade(
                    plan, plan.action_digest, plan.plan_digest
                ),
                range(2),
            )
        )
    assert sum(result.ok for result in results) == 1
    assert sorted(result.code for result in results) == [
        "OK",
        "PROJECT_UPGRADE_AUTHORIZATION_CONSUMED",
    ]


def test_plan_digest_mismatch_consumes_valid_action(tmp_path: Path):
    _write_v2(tmp_path)
    plan = plan_project_upgrade(tmp_path)
    denied = apply_project_upgrade(plan, plan.action_digest, "0" * 64)
    applied = apply_project_upgrade(plan, plan.action_digest, plan.plan_digest)
    assert denied.code == "PROJECT_UPGRADE_PLAN_DIGEST_MISMATCH"
    assert applied.code == "PROJECT_UPGRADE_AUTHORIZATION_CONSUMED"


def test_changed_source_is_rejected_without_overwrite_and_consumes_authorization(tmp_path: Path):
    manifest_path, source = _write_v2(tmp_path)
    plan = plan_project_upgrade(tmp_path)
    changed = source + " "
    manifest_path.write_text(changed, encoding="utf-8", newline="")
    result = apply_project_upgrade(plan, plan.action_digest, plan.plan_digest)
    retry = apply_project_upgrade(plan, plan.action_digest, plan.plan_digest)
    assert result.code == "PROJECT_CHANGED_SINCE_PLAN"
    assert result.details == {
        "path": str(manifest_path.resolve()), "expectedSha256": plan.source_sha256,
        "observedSha256": sha256(changed.encode("utf-8")).hexdigest(),
    }
    assert retry.code == "PROJECT_UPGRADE_AUTHORIZATION_CONSUMED"
    assert manifest_path.read_text(encoding="utf-8") == changed


def test_deleted_source_is_rejected_without_recreation(tmp_path: Path):
    manifest_path, _ = _write_v2(tmp_path)
    plan = plan_project_upgrade(tmp_path)
    manifest_path.unlink()
    result = apply_project_upgrade(plan, plan.action_digest, plan.plan_digest)
    assert result.code == "PROJECT_CHANGED_SINCE_PLAN"
    assert result.details["observedSha256"] is None
    assert not manifest_path.exists()


def test_reconstructed_or_mutated_plan_has_no_write_capability(tmp_path: Path):
    manifest_path, source = _write_v2(tmp_path)
    plan = plan_project_upgrade(tmp_path)
    reconstructed = UpgradePlan(
        manifest_path=plan.manifest_path, source_sha256=plan.source_sha256,
        from_version=2, to_version=3, proposed=plan.proposed,
        candidate=plan.candidate, diff=plan.diff, plan_digest=plan.plan_digest,
        action_digest=plan.action_digest, root_identity=plan.root_identity,
        manifest_identity=plan.manifest_identity,
    )
    mutated = replace(plan, candidate=plan.candidate + " ")
    first = apply_project_upgrade(reconstructed, reconstructed.action_digest, reconstructed.plan_digest)
    second = apply_project_upgrade(mutated, mutated.action_digest, mutated.plan_digest)
    assert first.code == "PROJECT_UPGRADE_PLAN_INVALID"
    assert second.code == "PROJECT_UPGRADE_AUTHORIZATION_CONSUMED"
    assert manifest_path.read_text(encoding="utf-8") == source


def test_failed_authorization_consumes_valid_action(tmp_path: Path):
    _write_v2(tmp_path)
    plan = plan_project_upgrade(tmp_path)
    denied = apply_project_upgrade(plan, "0" * 64, plan.plan_digest)
    applied = apply_project_upgrade(plan, plan.action_digest, plan.plan_digest)
    assert denied.code == "PROJECT_UPGRADE_AUTHORIZATION_REQUIRED"
    assert applied.code == "PROJECT_UPGRADE_AUTHORIZATION_CONSUMED"


def _raising_oserror(message: str):
    def raiser(*args, **kwargs):
        raise OSError(message)
    return raiser


@pytest.mark.parametrize("stage", ["write", "flush", "replace"])
def test_apply_io_failures_are_stable_and_do_not_leave_temp_files(
    tmp_path: Path, monkeypatch, stage: str
):
    manifest_path, source = _write_v2(tmp_path)
    plan = plan_project_upgrade(tmp_path)
    def fail_publish(*args):
        raise upgrade_mod._StageError(stage)
    monkeypatch.setattr(upgrade_mod, "_publish", fail_publish)
    result = apply_project_upgrade(plan, plan.action_digest, plan.plan_digest)
    assert result.code == "PROJECT_UPGRADE_IO_ERROR"
    assert result.details == {"path": str(manifest_path.resolve()), "stage": stage}
    assert "private" not in str(result.to_dict())
    assert manifest_path.read_text(encoding="utf-8") == source
    assert sorted(path.name for path in tmp_path.iterdir()) == [MANIFEST_NAME]


def test_apply_rejects_non_plan_input_without_exception():
    result = apply_project_upgrade(object(), "x", "y")  # type: ignore[arg-type]
    assert result.code == "PROJECT_UPGRADE_PLAN_INVALID"


def test_planner_reports_invalid_generated_candidate(tmp_path: Path, monkeypatch):
    _write_v2(tmp_path)
    monkeypatch.setattr(upgrade_mod, "_proposed_validation_error", lambda *args: ("x", "rule"))
    with pytest.raises(ProjectUpgradeError) as caught:
        plan_project_upgrade(tmp_path)
    assert caught.value.details == {"field": "x", "rule": "rule"}


def _prepared(plan: UpgradePlan):
    return upgrade_mod._PREPARED[plan.action_digest]


def test_mutating_registered_plan_is_rejected_and_consumes_action(tmp_path: Path):
    _write_v2(tmp_path)
    plan = plan_project_upgrade(tmp_path)
    object.__setattr__(plan, "candidate", plan.candidate + " ")
    result = apply_project_upgrade(plan, plan.action_digest, plan.plan_digest)
    assert result.code == "PROJECT_UPGRADE_PLAN_INVALID"
    assert apply_project_upgrade(plan, plan.action_digest, plan.plan_digest).code == "PROJECT_UPGRADE_AUTHORIZATION_CONSUMED"


@pytest.mark.parametrize(("field", "value"), [("from_version", 1), ("to_version", 2)])
def test_registered_plan_requires_exact_builtin_versions(
    tmp_path: Path, field: str, value: int
):
    _write_v2(tmp_path)
    plan = plan_project_upgrade(tmp_path)
    object.__setattr__(plan, field, value)
    _prepared(plan).signature = upgrade_mod._plan_signature(plan)
    result = apply_project_upgrade(plan, plan.action_digest, plan.plan_digest)
    assert result.code == "PROJECT_UPGRADE_PLAN_INVALID"
    assert result.details == {"fromVersion": plan.from_version, "toVersion": plan.to_version}


def test_registered_plan_requires_canonical_manifest_path(tmp_path: Path):
    _write_v2(tmp_path)
    plan = plan_project_upgrade(tmp_path)
    object.__setattr__(plan, "manifest_path", tmp_path / "other.json")
    _prepared(plan).signature = upgrade_mod._plan_signature(plan)
    result = apply_project_upgrade(plan, plan.action_digest, plan.plan_digest)
    assert result.details == {"field": "manifestPath", "rule": "canonicalProjectManifest"}


def test_apply_revalidates_candidate_schema_after_authorization(tmp_path: Path, monkeypatch):
    _write_v2(tmp_path)
    plan = plan_project_upgrade(tmp_path)
    monkeypatch.setattr(upgrade_mod, "_proposed_validation_error", lambda *args: ("x", "bad"))
    result = apply_project_upgrade(plan, plan.action_digest, plan.plan_digest)
    assert result.details == {"field": "source", "rule": "validSchemaVersion2"}


def test_apply_rejects_deterministic_diff_mismatch(tmp_path: Path):
    _write_v2(tmp_path)
    plan = plan_project_upgrade(tmp_path)
    object.__setattr__(plan, "diff", plan.diff + "tampered")
    _prepared(plan).signature = upgrade_mod._plan_signature(plan)
    result = apply_project_upgrade(plan, plan.action_digest, plan.plan_digest)
    assert result.details == {"field": "proposed", "rule": "deterministicUpgrade"}


def test_candidate_builder_rejects_non_v2_text():
    with pytest.raises(ProjectUpgradeError) as caught:
        upgrade_mod._build_candidate(b'{"schemaVersion": 22}')
    assert caught.value.details == {"field": "schemaVersion", "rule": "deterministicUpgrade"}


def test_proposed_validation_reports_schema_failure(tmp_path: Path):
    assert upgrade_mod._proposed_validation_error({"schemaVersion": 3}, tmp_path) == (
        "logicalProjectId",
        "required",
    )
