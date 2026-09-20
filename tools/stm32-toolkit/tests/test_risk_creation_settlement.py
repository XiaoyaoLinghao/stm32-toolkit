from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import stm32_toolkit.creation_apply as creation_apply_module
from stm32_toolkit.creation_apply import CreationApplyRequest, apply_creation
from stm32_toolkit.result import OperationResult
from test_creation_apply import RecordingAdapter, _authorization, _validator

_ENVIRONMENT = SimpleNamespace(digest="c" * 64)


def _assert_failure_wire(
    result: OperationResult[object], code: str, message: str, attempt_id: str
) -> None:
    assert result.to_dict() == {
        "protocol": "stm32-toolkit/1",
        "ok": False,
        "operation": "project-create-apply",
        "code": code,
        "message": message,
        "data": None,
        "details": {"attemptId": attempt_id},
    }


def _assert_consumed(store, digest: str) -> None:
    record = store.authorization_root / f"{digest}.json"
    assert json.loads(record.read_text(encoding="utf-8"))["state"] == "consumed"


def _assert_destination_unchanged(
    root: Path, *, was_empty: bool, sentinel: bytes
) -> None:
    destination = root / "generated"
    if was_empty:
        assert destination.is_dir()
        assert list(destination.iterdir()) == []
    else:
        assert not destination.exists()
    assert (root / "user-sentinel.txt").read_bytes() == sentinel


def _fail_exact_cleanup(
    monkeypatch: pytest.MonkeyPatch, expected_root: Path
) -> list[Path]:
    calls: list[Path] = []
    real_rmtree = creation_apply_module.shutil.rmtree

    def fail_owned_root(path, *args, **kwargs):
        actual = Path(path)
        if actual == expected_root:
            calls.append(actual)
            raise OSError("injected owned-root cleanup failure")
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(creation_apply_module.shutil, "rmtree", fail_owned_root)
    return calls


@pytest.mark.parametrize(
    "cleanup_failure",
    [False, True],
    ids=["cleanup-succeeds", "cleanup-fails"],
)
def test_native_parser_failure_settles_owned_generation_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cleanup_failure: bool
) -> None:
    data, store, prepared = _authorization(tmp_path)
    destination = tmp_path / "generated"
    sentinel = b"user-owned"
    (tmp_path / "user-sentinel.txt").write_bytes(sentinel)
    attempt_id = "native-missing-cmake"
    generation_root = tmp_path / f".stm32tk-creation-{attempt_id}"
    if cleanup_failure:
        cleanup_calls = _fail_exact_cleanup(monkeypatch, generation_root)
    else:
        cleanup_calls = []
    events: list[str] = []

    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        environment=_ENVIRONMENT,
        adapter=RecordingAdapter(events),
        configure=lambda root: events.append("configure")
        or OperationResult.success("configure", {}),
        build=lambda root, preset: events.append(f"build:{preset}")
        or OperationResult.success("build", {"preset": preset}),
        on_activate=lambda: events.append("activate"),
        attempt_id_factory=lambda: attempt_id,
    )

    if cleanup_failure:
        _assert_failure_wire(
            result,
            "CREATION_ACTIVATION_ROLLBACK_FAILED",
            "creation staging cleanup failed",
            attempt_id,
        )
        assert cleanup_calls == [generation_root]
        assert generation_root.is_dir()
        assert (generation_root / "generated" / "native.txt").is_file()
    else:
        _assert_failure_wire(
            result,
            "CUBEMX_NATIVE_OUTPUT_INVALID",
            "required native file is unavailable",
            attempt_id,
        )
        assert not generation_root.exists()
        failure = data / "creation" / "attempts" / attempt_id / "failure.json"
        assert json.loads(failure.read_text(encoding="utf-8")) == {
            "code": "CUBEMX_NATIVE_OUTPUT_INVALID",
            "phase": "validation",
        }
    assert events == ["cubeMx"]
    assert not destination.exists()
    assert (tmp_path / "user-sentinel.txt").read_bytes() == sentinel
    _assert_consumed(store, prepared.authorization_digest)


@pytest.mark.parametrize(
    "cleanup_failure",
    [False, True],
    ids=["cleanup-succeeds", "cleanup-fails"],
)
def test_generation_provider_oserror_settles_owned_generation_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cleanup_failure: bool
) -> None:
    data, store, prepared = _authorization(tmp_path)
    destination = tmp_path / "generated"
    destination.mkdir()
    sentinel = b"user-owned"
    (tmp_path / "user-sentinel.txt").write_bytes(sentinel)
    attempt_id = "generation-provider-oserror"
    generation_root = tmp_path / f".stm32tk-creation-{attempt_id}"
    if cleanup_failure:
        cleanup_calls = _fail_exact_cleanup(monkeypatch, generation_root)
    else:
        cleanup_calls = []
    events: list[str] = []

    class FailingGenerationAdapter(RecordingAdapter):
        def generate(self, capability, staging):
            result = super().generate(capability, staging)
            (result.project_root / "partial.txt").write_text(
                "owned output", encoding="utf-8"
            )
            raise OSError("injected generation provider failure")

    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        environment=_ENVIRONMENT,
        adapter=FailingGenerationAdapter(events),
        validate_native=_validator(events),
        configure=lambda root: events.append("configure")
        or OperationResult.success("configure", {}),
        build=lambda root, preset: events.append(f"build:{preset}")
        or OperationResult.success("build", {"preset": preset}),
        on_activate=lambda: events.append("activate"),
        attempt_id_factory=lambda: attempt_id,
    )

    expected_code = (
        "CREATION_ACTIVATION_ROLLBACK_FAILED"
        if cleanup_failure
        else "CREATION_ACTIVATION_FAILED"
    )
    expected_message = (
        "creation staging cleanup failed"
        if cleanup_failure
        else "creation staging failed"
    )
    _assert_failure_wire(result, expected_code, expected_message, attempt_id)
    if cleanup_failure:
        assert cleanup_calls == [generation_root]
        assert generation_root.is_dir()
        assert (generation_root / "generated" / "partial.txt").read_text(
            encoding="utf-8"
        ) == "owned output"
    else:
        assert not generation_root.exists()
    assert not list(tmp_path.glob(".stm32tk-activation-*"))
    assert events == ["cubeMx"]
    _assert_destination_unchanged(tmp_path, was_empty=True, sentinel=sentinel)
    _assert_consumed(store, prepared.authorization_digest)


@pytest.mark.parametrize(
    "cleanup_failure",
    [False, True],
    ids=["cleanup-succeeds", "cleanup-fails"],
)
def test_configure_oserror_after_relocation_settles_activation_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cleanup_failure: bool
) -> None:
    data, store, prepared = _authorization(tmp_path)
    destination = tmp_path / "generated"
    destination.mkdir()
    sentinel = b"user-owned"
    (tmp_path / "user-sentinel.txt").write_bytes(sentinel)
    attempt_id = "configure-after-relocation"
    activation_root = tmp_path / f".stm32tk-activation-{attempt_id}"
    if cleanup_failure:
        cleanup_calls = _fail_exact_cleanup(monkeypatch, activation_root)
    else:
        cleanup_calls = []
    events: list[str] = []
    generation_roots: list[Path] = []
    configured_roots: list[Path] = []

    class RootRecordingAdapter(RecordingAdapter):
        def generate(self, capability, staging):
            generation_roots.append(staging.staging_dir)
            return super().generate(capability, staging)

    def configure(root: Path):
        configured_roots.append(root)
        events.append("configure")
        raise OSError("injected configure provider failure")

    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        environment=_ENVIRONMENT,
        adapter=RootRecordingAdapter(events),
        validate_native=_validator(events),
        configure=configure,
        build=lambda root, preset: events.append(f"build:{preset}")
        or OperationResult.success("build", {"preset": preset}),
        on_activate=lambda: events.append("activate"),
        attempt_id_factory=lambda: attempt_id,
    )

    expected_code = (
        "CREATION_ACTIVATION_ROLLBACK_FAILED"
        if cleanup_failure
        else "CREATION_ACTIVATION_FAILED"
    )
    expected_message = (
        "creation staging cleanup failed"
        if cleanup_failure
        else "creation staging failed"
    )
    _assert_failure_wire(result, expected_code, expected_message, attempt_id)
    assert generation_roots
    assert configured_roots == [activation_root]
    assert configured_roots[0].name.startswith(".stm32tk-activation-")
    assert (configured_roots[0] / "generated" / "native.txt").exists() is False
    assert (configured_roots[0] / "native.txt").is_file()
    assert not generation_roots[0].exists()
    if cleanup_failure:
        assert cleanup_calls == [activation_root]
        assert activation_root.is_dir()
        assert (activation_root / "native.txt").is_file()
    else:
        assert not activation_root.exists()
    assert not list(tmp_path.glob(".stm32tk-creation-*"))
    assert events == ["cubeMx", "validate", "configure"]
    _assert_destination_unchanged(tmp_path, was_empty=True, sentinel=sentinel)
    _assert_consumed(store, prepared.authorization_digest)
