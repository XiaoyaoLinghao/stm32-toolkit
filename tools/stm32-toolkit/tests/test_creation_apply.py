from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from stm32_toolkit.creation_apply import CreationApplyRequest, apply_creation
from stm32_toolkit.creation_authorization import (
    CreationAuthorizationError,
    CreationAuthorizationStore,
    CreationPrepareRequest,
)
from stm32_toolkit.generation.creation import CreationRequest
from stm32_toolkit.result import OperationResult


def _authorization(tmp_path: Path):
    data = tmp_path / "data"
    request = CreationRequest.from_mcu("STM32F429ZITx", "generated", framework="hal", language="c")
    store = CreationAuthorizationStore(data, now=lambda: __import__("datetime").datetime(2026, 8, 23, 12, tzinfo=__import__("datetime").timezone.utc), nonce_factory=lambda: "nonce")
    prepared = store.prepare(CreationPrepareRequest(request, tmp_path, "a" * 64, "b" * 64, "c" * 64, "2026-08-23T13:00:00Z"))
    return data, store, prepared


class RecordingAdapter:
    def __init__(self, events: list[str]):
        self.events = events
        self.calls = 0

    def generate(self, capability, staging):
        self.calls += 1
        self.events.append("cubeMx")
        (staging.staging_dir / "native.txt").write_text("generated", encoding="utf-8")
        return SimpleNamespace(invocations=1)


def _validator(events: list[str]):
    def validate(staging, **kwargs):
        events.append("validate")
        return SimpleNamespace(ownership_manifest_path=".stm32-toolkit/cubemx-ownership.json", ownership_manifest_sha256="1" * 64)
    return validate


def test_apply_orders_one_generation_then_configure_and_two_builds_before_activation(tmp_path: Path):
    data, store, prepared = _authorization(tmp_path)
    events: list[str] = []
    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        adapter=RecordingAdapter(events),
        validate_native=_validator(events),
        configure=lambda root: events.append("configure") or OperationResult.success("configure", {"planId": "p"}),
        build=lambda root, preset: events.append(f"build:{preset}") or OperationResult.success("build", {"preset": preset, "identity": preset}),
        on_activate=lambda: events.append("activate"),
    )
    assert result.ok is True
    assert result.data["mutated"] is True
    assert events == ["cubeMx", "validate", "configure", "build:arm-debug", "build:arm-release", "activate"]
    assert (tmp_path / "generated" / "native.txt").read_text(encoding="utf-8") == "generated"


def test_empty_destination_is_replaced_only_after_both_builds(tmp_path: Path):
    (tmp_path / "generated").mkdir()
    data, store, prepared = _authorization(tmp_path)
    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        adapter=RecordingAdapter([]),
        validate_native=lambda staging, **kwargs: SimpleNamespace(ownership_manifest_path="m", ownership_manifest_sha256="1" * 64),
        configure=lambda root: OperationResult.success("configure", {}),
        build=lambda root, preset: OperationResult.success("build", {"preset": preset}),
    )
    assert result.ok is True
    assert (tmp_path / "generated").is_dir()
    assert not list(tmp_path.glob(".generated.backup-*"))


def test_release_build_failure_leaves_destination_absent_and_cleans_staging(tmp_path: Path):
    data, store, prepared = _authorization(tmp_path)
    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        adapter=RecordingAdapter([]),
        validate_native=lambda staging, **kwargs: SimpleNamespace(ownership_manifest_path="m", ownership_manifest_sha256="1" * 64),
        configure=lambda root: OperationResult.success("configure", {}),
        build=lambda root, preset: OperationResult.failure("build", "FAIL", "failed", {}) if preset == "arm-release" else OperationResult.success("build", {"preset": preset}),
    )
    assert result.ok is False
    assert result.code == "CREATION_RELEASE_BUILD_FAILED"
    assert not (tmp_path / "generated").exists()
    assert not list(tmp_path.glob(".stm32tk-creation-*"))


def test_populated_destination_is_rejected_without_consuming_generation_call(tmp_path: Path):
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "existing.txt").write_text("keep", encoding="utf-8")
    data, store, prepared = _authorization(tmp_path)
    adapter = RecordingAdapter([])
    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        adapter=adapter,
        validate_native=_validator([]),
        configure=lambda root: OperationResult.success("configure", {}),
        build=lambda root, preset: OperationResult.success("build", {}),
    )
    assert result.ok is False
    assert result.code == "CREATION_DESTINATION_CHANGED"
    assert adapter.calls == 0
    assert (tmp_path / "generated" / "existing.txt").read_text(encoding="utf-8") == "keep"


def test_apply_requires_exact_boolean_true(tmp_path: Path):
    data, store, prepared = _authorization(tmp_path)
    with pytest.raises(CreationAuthorizationError) as error:
        apply_creation(CreationApplyRequest(tmp_path, data, prepared.authorization_digest, False), store=store)
    assert error.value.code == "CREATION_AUTHORIZATION_REQUIRED"
