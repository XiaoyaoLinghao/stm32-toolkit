from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from stm32_toolkit.creation_authorization import (
    CreationAuthorizationError,
    CreationAuthorizationStore,
    CreationPrepareRequest,
)
from stm32_toolkit.generation.creation import CreationRequest, CreationSource


NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


def _request() -> CreationRequest:
    return CreationRequest.from_mcu(
        "STM32F429ZITx", "generated", framework="hal", language="c"
    )


def _prepare(store: CreationAuthorizationStore):
    return store.prepare(
        CreationPrepareRequest(
            request=_request(),
            project_root=Path("C:/workspace"),
            plan_id="a" * 64,
            action_digest="b" * 64,
            environment_digest="c" * 64,
            expires_at="2026-08-23T13:00:00Z",
        )
    )


def test_prepare_writes_bounded_record_and_returns_single_use_digest(tmp_path: Path):
    store = CreationAuthorizationStore(tmp_path, now=lambda: NOW, nonce_factory=lambda: "nonce")
    result = _prepare(store)
    assert result.authorization_digest
    assert result.mutated is False
    record = tmp_path / "creation" / "authorizations" / f"{result.authorization_digest}.json"
    payload = json.loads(record.read_text(encoding="utf-8"))
    assert payload["state"] == "prepared"
    assert payload["planId"] == "a" * 64
    assert "nonce" in payload
    assert len(record.read_bytes()) < 32 * 1024


def test_consume_requires_exact_true_and_does_not_consume_false(tmp_path: Path):
    store = CreationAuthorizationStore(tmp_path, now=lambda: NOW, nonce_factory=lambda: "nonce")
    result = _prepare(store)
    with pytest.raises(CreationAuthorizationError) as error:
        store.consume(result.authorization_digest, authorized=1)
    assert error.value.code == "CREATION_AUTHORIZATION_REQUIRED"
    with pytest.raises(CreationAuthorizationError) as error:
        store.consume(result.authorization_digest, authorized=False)
    assert error.value.code == "CREATION_AUTHORIZATION_REQUIRED"
    capability = store.consume(result.authorization_digest, authorized=True)
    assert capability.plan_id == "a" * 64


def test_ioc_source_digest_survives_authorization_round_trip(tmp_path: Path):
    request = CreationRequest(
        CreationSource("ioc", "input.ioc", "d" * 64),
        "generated",
        "hal",
        "c",
    )
    store = CreationAuthorizationStore(tmp_path, now=lambda: NOW, nonce_factory=lambda: "nonce")
    prepared = store.prepare(
        CreationPrepareRequest(
            request,
            tmp_path,
            "a" * 64,
            "b" * 64,
            "c" * 64,
            "2026-08-23T13:00:00Z",
        )
    )
    consumed = store.consume(prepared.authorization_digest, authorized=True)
    assert consumed.request.source.sha256 == "d" * 64


@pytest.mark.parametrize(
    "creation_request",
    [
        CreationRequest.from_board("NUCLEO-F429ZI", "generated", framework="hal", language="c"),
        CreationRequest.from_ioc("input.ioc", "generated", framework="hal", language="c"),
    ],
)
def test_public_request_variants_round_trip_without_identity_loss(
    tmp_path: Path, creation_request: CreationRequest
):
    store = CreationAuthorizationStore(tmp_path, now=lambda: NOW, nonce_factory=lambda: "nonce")
    prepared = store.prepare(
        CreationPrepareRequest(
            creation_request,
            tmp_path,
            "a" * 64,
            "b" * 64,
            "c" * 64,
            "2026-08-23T13:00:00Z",
        )
    )

    consumed = store.consume(prepared.authorization_digest, authorized=True)

    assert consumed.request == creation_request
    assert consumed.request.source.kind == creation_request.source.kind
    assert consumed.request.source.value == creation_request.source.value
    assert consumed.request.source.sha256 == creation_request.source.sha256


def test_replay_is_rejected_after_consumption(tmp_path: Path):
    store = CreationAuthorizationStore(tmp_path, now=lambda: NOW, nonce_factory=lambda: "nonce")
    result = _prepare(store)
    store.consume(result.authorization_digest, authorized=True)
    with pytest.raises(CreationAuthorizationError) as error:
        store.consume(result.authorization_digest, authorized=True)
    assert error.value.code == "CREATION_AUTHORIZATION_CONSUMED"


def test_expired_capability_is_rejected(tmp_path: Path):
    store = CreationAuthorizationStore(tmp_path, now=lambda: NOW, nonce_factory=lambda: "nonce")
    result = _prepare(store)
    expired = NOW + timedelta(hours=2)
    store_with_later_clock = CreationAuthorizationStore(tmp_path, now=lambda: expired)
    with pytest.raises(CreationAuthorizationError) as error:
        store_with_later_clock.consume(result.authorization_digest, authorized=True)
    assert error.value.code == "CREATION_AUTHORIZATION_EXPIRED"


def test_peek_is_non_consuming_before_the_single_use_claim(tmp_path: Path):
    store = CreationAuthorizationStore(tmp_path, now=lambda: NOW, nonce_factory=lambda: "nonce")
    result = _prepare(store)

    peeked = store.peek(result.authorization_digest)
    assert peeked.authorization_digest == result.authorization_digest
    assert peeked.plan_id == "a" * 64
    assert peeked.project_root == Path("C:/workspace")
    record = store.authorization_root / f"{result.authorization_digest}.json"
    assert json.loads(record.read_text(encoding="utf-8"))["state"] == "prepared"

    consumed = store.consume(result.authorization_digest, authorized=True)
    assert consumed.request == _request()
    assert json.loads(record.read_text(encoding="utf-8"))["state"] == "consumed"


@pytest.mark.parametrize(
    "request_value",
    [
        None,
        {"source": {"kind": "mcu", "value": "STM32F429ZITx", "extra": "x"}, "destination": "generated", "framework": "hal", "language": "c"},
        {"source": {"kind": "mcu", "value": "STM32F429ZITx", "sha256": "d" * 64}, "destination": "generated", "framework": "hal", "language": "c"},
        {"source": {"kind": "board", "value": "NUCLEO-F429ZI", "sha256": "d" * 64}, "destination": "generated", "framework": "hal", "language": "c"},
        {"source": {"kind": "ioc", "value": "input.ioc", "sha256": "invalid"}, "destination": "generated", "framework": "hal", "language": "c"},
        {"source": {"kind": "unsupported", "value": "STM32F429ZITx"}, "destination": "generated", "framework": "hal", "language": "c"},
    ],
)
def test_persisted_request_shapes_are_rejected_before_authorization(
    tmp_path: Path, request_value: object
):
    """A caller cannot turn a valid record into a different public request."""
    store = CreationAuthorizationStore(tmp_path, now=lambda: NOW, nonce_factory=lambda: "nonce")
    prepared = _prepare(store)
    original = store.authorization_root / f"{prepared.authorization_digest}.json"
    payload = json.loads(original.read_text(encoding="utf-8"))
    original_snapshot = (original.read_bytes(), payload["state"])
    payload["request"] = request_value
    canonical = {key: value for key, value in payload.items() if key != "authorizationDigest"}
    canonical["state"] = "prepared"
    forged_digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    payload["authorizationDigest"] = forged_digest
    forged = store.authorization_root / f"{forged_digest}.json"
    forged.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    forged_snapshot = (forged.read_bytes(), json.loads(forged.read_text(encoding="utf-8"))["state"])

    def assert_records_unchanged() -> None:
        assert (original.read_bytes(), json.loads(original.read_text(encoding="utf-8"))["state"]) == original_snapshot
        assert (forged.read_bytes(), json.loads(forged.read_text(encoding="utf-8"))["state"]) == forged_snapshot

    with pytest.raises(CreationAuthorizationError) as peek_error:
        store.peek(forged_digest)
    assert peek_error.value.code == "CREATION_AUTHORIZATION_INVALID"
    assert_records_unchanged()
    with pytest.raises(CreationAuthorizationError) as consume_error:
        store.consume(forged_digest, authorized=True)
    assert consume_error.value.code == "CREATION_AUTHORIZATION_INVALID"
    assert_records_unchanged()


def test_malformed_record_is_closed_without_raw_record_data(tmp_path: Path):
    digest = "d" * 64
    path = tmp_path / "creation" / "authorizations" / f"{digest}.json"
    path.parent.mkdir(parents=True)
    path.write_text("{\"state\": [\"not-an-object\"]}", encoding="utf-8")
    with pytest.raises(CreationAuthorizationError) as error:
        CreationAuthorizationStore(tmp_path, now=lambda: NOW).consume(digest, authorized=True)
    assert error.value.code == "CREATION_AUTHORIZATION_INVALID"
    assert "not-an-object" not in str(error.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("request", {"source": {"kind": "mcu", "value": "STM32F429ZITx"}, "destination": "tampered", "framework": "hal", "language": "c"}),
        ("projectRoot", "C:/tampered"),
        ("planId", "d" * 64),
        ("actionDigest", "e" * 64),
        ("executionEnvironmentDigest", "f" * 64),
        ("expiresAt", "2026-08-23T14:00:00Z"),
        ("issuedAt", "2026-08-23T11:00:00Z"),
        ("nonce", "tampered-nonce"),
    ],
)
def test_record_integrity_rejects_prepared_payload_tampering(tmp_path: Path, field: str, value: object):
    store = CreationAuthorizationStore(tmp_path, now=lambda: NOW, nonce_factory=lambda: "nonce")
    result = _prepare(store)
    record = tmp_path / "creation" / "authorizations" / f"{result.authorization_digest}.json"
    payload = json.loads(record.read_text(encoding="utf-8"))
    payload[field] = value
    record.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")

    with pytest.raises(CreationAuthorizationError) as peek_error:
        store.peek(result.authorization_digest)
    assert peek_error.value.code == "CREATION_AUTHORIZATION_INVALID"
    with pytest.raises(CreationAuthorizationError) as consume_error:
        store.consume(result.authorization_digest, authorized=True)
    assert consume_error.value.code == "CREATION_AUTHORIZATION_INVALID"


def test_two_concurrent_consumers_have_exactly_one_winner(tmp_path: Path):
    store = CreationAuthorizationStore(tmp_path, now=lambda: NOW, nonce_factory=lambda: "nonce")
    result = _prepare(store)
    outcomes: list[str] = []
    barrier = threading.Barrier(2)

    def consume() -> None:
        barrier.wait()
        try:
            store.consume(result.authorization_digest, authorized=True)
        except CreationAuthorizationError as error:
            outcomes.append(error.code)
        else:
            outcomes.append("OK")

    threads = [threading.Thread(target=consume) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["CREATION_AUTHORIZATION_CONSUMED", "OK"]


def test_two_independent_processes_have_exactly_one_durable_consumer(tmp_path: Path):
    store = CreationAuthorizationStore(tmp_path, now=lambda: NOW, nonce_factory=lambda: "nonce")
    result = _prepare(store)
    markers = tmp_path / "markers"
    markers.mkdir()
    script = r'''
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import stm32_toolkit.creation_authorization as module
from stm32_toolkit.creation_authorization import CreationAuthorizationError, CreationAuthorizationStore

data_root = Path(sys.argv[1])
digest = sys.argv[2]
markers = Path(sys.argv[3])
real_replace = module.os.replace

def synchronized_replace(source, target):
    (markers / f"ready-{os.getpid()}").write_text("ready", encoding="utf-8")
    while not (markers / "release").exists():
        time.sleep(0.005)
    return real_replace(source, target)

module.os.replace = synchronized_replace
store = CreationAuthorizationStore(
    data_root,
    now=lambda: datetime(2026, 8, 23, 12, tzinfo=timezone.utc),
)
try:
    store.consume(digest, authorized=True)
except CreationAuthorizationError as error:
    print(error.code, flush=True)
else:
    print("OK", flush=True)
'''
    environment = os.environ.copy()
    source_root = str(Path(__file__).resolve().parents[1] / "src")
    environment["PYTHONPATH"] = source_root + os.pathsep + environment.get("PYTHONPATH", "")
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(tmp_path), result.authorization_digest, str(markers)],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    deadline = time.monotonic() + 10
    while not list(markers.glob("ready-*")) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert list(markers.glob("ready-*"))
    (markers / "release").write_text("release", encoding="utf-8")
    outputs = [process.communicate(timeout=10)[0].strip() for process in processes]
    assert sorted(outputs) == ["CREATION_AUTHORIZATION_CONSUMED", "OK"]

# Public construction and persisted-record boundary coverage approved for the
# authorization-boundaries slice.  These helpers intentionally use only the
# exported request/store APIs and the record's public JSON wire format.

def _authorization_request(
    project_root: Path, *, expires_at: str = "2026-08-23T13:00:00Z"
) -> CreationPrepareRequest:
    return CreationPrepareRequest(
        request=_request(),
        project_root=project_root,
        plan_id="a" * 64,
        action_digest="b" * 64,
        environment_digest="c" * 64,
        expires_at=expires_at,
    )


def _case_store(
    data_root: Path, *, now_value: datetime = NOW, nonce: str = "nonce"
) -> CreationAuthorizationStore:
    return CreationAuthorizationStore(
        data_root,
        now=lambda: now_value,
        nonce_factory=lambda: nonce,
    )


def _tree_snapshot(root: Path) -> dict[str, tuple[str, bytes | None]] | None:
    if not root.exists():
        return None
    snapshot: dict[str, tuple[str, bytes | None]] = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            snapshot[relative] = ("directory", None)
        elif path.is_file():
            snapshot[relative] = ("file", path.read_bytes())
        else:
            snapshot[relative] = ("other", None)
    return snapshot


def _assert_error(
    error: pytest.ExceptionInfo[CreationAuthorizationError],
    code: str,
    message: str,
) -> None:
    assert error.value.code == code
    assert error.value.message == message
    assert str(error.value) == message
    assert error.value.details == {}


def _immutable_record_digest(payload: dict[str, object]) -> str:
    canonical = {
        key: value for key, value in payload.items() if key != "authorizationDigest"
    }
    canonical["state"] = "prepared"
    return hashlib.sha256(
        json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def _alter_prepared_record(
    store: CreationAuthorizationStore,
    prepared_digest: str,
    mutate,
) -> tuple[Path, Path, str]:
    original = store.authorization_root / f"{prepared_digest}.json"
    payload = json.loads(original.read_text(encoding="utf-8"))
    mutate(payload)
    altered_digest = _immutable_record_digest(payload)
    payload["authorizationDigest"] = altered_digest
    altered = store.authorization_root / f"{altered_digest}.json"
    altered.write_bytes(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    )
    return original, altered, altered_digest


def _prepared_case(tmp_path: Path):
    data_root = tmp_path / "data"
    project_root = tmp_path / "project"
    store = _case_store(data_root)
    prepared = store.prepare(_authorization_request(project_root))
    return store, project_root, prepared


def _assert_consume_failure(
    store: CreationAuthorizationStore,
    digest: str,
    tmp_path: Path,
    project_root: Path,
    code: str,
    message: str,
) -> None:
    before = _tree_snapshot(tmp_path)
    project_before = _tree_snapshot(project_root)
    lock = store.authorization_locks_root / f"{digest}.lock"
    lock_before = lock.exists()
    with pytest.raises(CreationAuthorizationError) as error:
        store.consume(digest, authorized=True)
    _assert_error(error, code, message)
    after = _tree_snapshot(tmp_path)
    expected = dict(before or {})
    if not lock_before:
        expected[lock.relative_to(tmp_path).as_posix()] = ("file", b"\0")
    assert after == expected
    assert lock.is_file()
    assert lock.read_bytes() == b"\0"
    assert _tree_snapshot(project_root) == project_before


def _assert_peek_failure(
    store: CreationAuthorizationStore,
    digest: str,
    tmp_path: Path,
    project_root: Path,
    code: str,
    message: str,
) -> None:
    before = _tree_snapshot(tmp_path)
    project_before = _tree_snapshot(project_root)
    with pytest.raises(CreationAuthorizationError) as error:
        store.peek(digest)
    _assert_error(error, code, message)
    assert _tree_snapshot(tmp_path) == before
    assert _tree_snapshot(project_root) == project_before


def test_creation_authorization_prepare_request_type(tmp_path: Path):
    data_root = tmp_path / "data"
    project_root = tmp_path / "project"
    before = _tree_snapshot(tmp_path)
    with pytest.raises(CreationAuthorizationError) as error:
        CreationPrepareRequest(
            request=object(),
            project_root=project_root,
            plan_id="a" * 64,
            action_digest="b" * 64,
            environment_digest="c" * 64,
            expires_at="2026-08-23T13:00:00Z",
        )
    _assert_error(error, "CREATION_AUTHORIZATION_INVALID", "authorization request is invalid")
    assert _tree_snapshot(tmp_path) == before
    assert not data_root.exists()
    assert not project_root.exists()


def test_creation_authorization_prepare_root_relative(tmp_path: Path):
    before = _tree_snapshot(tmp_path)
    with pytest.raises(CreationAuthorizationError) as error:
        CreationPrepareRequest(
            request=_request(),
            project_root=Path("relative"),
            plan_id="a" * 64,
            action_digest="b" * 64,
            environment_digest="c" * 64,
            expires_at="2026-08-23T13:00:00Z",
        )
    _assert_error(error, "CREATION_AUTHORIZATION_INVALID", "authorization project root is invalid")
    assert _tree_snapshot(tmp_path) == before


def test_creation_authorization_prepare_invalid_digest(tmp_path: Path):
    before = _tree_snapshot(tmp_path)
    with pytest.raises(CreationAuthorizationError) as error:
        CreationPrepareRequest(
            request=_request(),
            project_root=tmp_path / "project",
            plan_id="bad",
            action_digest="b" * 64,
            environment_digest="c" * 64,
            expires_at="2026-08-23T13:00:00Z",
        )
    _assert_error(error, "CREATION_AUTHORIZATION_INVALID", "authorization digest is invalid")
    assert _tree_snapshot(tmp_path) == before


def test_creation_authorization_prepare_time_type(tmp_path: Path):
    before = _tree_snapshot(tmp_path)
    with pytest.raises(CreationAuthorizationError) as error:
        CreationPrepareRequest(
            request=_request(),
            project_root=tmp_path / "project",
            plan_id="a" * 64,
            action_digest="b" * 64,
            environment_digest="c" * 64,
            expires_at=None,
        )
    _assert_error(error, "CREATION_AUTHORIZATION_INVALID", "authorization expiry is invalid")
    assert _tree_snapshot(tmp_path) == before


def test_creation_authorization_store_data_root_type(tmp_path: Path):
    before = _tree_snapshot(tmp_path)
    with pytest.raises(ValueError) as error:
        CreationAuthorizationStore("not-a-path")
    assert str(error.value) == "data root"
    assert _tree_snapshot(tmp_path) == before


def test_creation_authorization_prepare_non_request(tmp_path: Path):
    data_root = tmp_path / "data"
    project_root = tmp_path / "project"
    store = _case_store(data_root)
    before = _tree_snapshot(tmp_path)
    with pytest.raises(CreationAuthorizationError) as error:
        store.prepare(None)
    _assert_error(error, "CREATION_AUTHORIZATION_INVALID", "authorization request is invalid")
    assert _tree_snapshot(tmp_path) == before
    assert not project_root.exists()


def test_creation_authorization_prepare_expired(tmp_path: Path):
    data_root = tmp_path / "data"
    project_root = tmp_path / "project"
    store = _case_store(data_root)
    before = _tree_snapshot(tmp_path)
    with pytest.raises(CreationAuthorizationError) as error:
        store.prepare(
            _authorization_request(
                project_root,
                expires_at="2026-08-23T12:00:00Z",
            )
        )
    _assert_error(error, "CREATION_AUTHORIZATION_EXPIRED", "authorization has expired")
    assert _tree_snapshot(tmp_path) == before
    assert not project_root.exists()


def test_creation_authorization_prepare_record_limit(tmp_path: Path):
    data_root = tmp_path / "data"
    project_root = tmp_path / "project"
    store = _case_store(data_root, nonce="n" * 65537)
    before = _tree_snapshot(tmp_path)
    with pytest.raises(CreationAuthorizationError) as error:
        store.prepare(_authorization_request(project_root))
    _assert_error(error, "CREATION_AUTHORIZATION_INVALID", "authorization record is oversized")
    assert _tree_snapshot(tmp_path) == before
    assert not project_root.exists()


def test_creation_authorization_consume_digest_type(tmp_path: Path):
    data_root = tmp_path / "data"
    project_root = tmp_path / "project"
    store = _case_store(data_root)
    before = _tree_snapshot(tmp_path)
    with pytest.raises(CreationAuthorizationError) as error:
        store.consume("bad", authorized=True)
    _assert_error(error, "CREATION_AUTHORIZATION_INVALID", "authorization digest is invalid")
    assert _tree_snapshot(tmp_path) == before
    assert not project_root.exists()


def test_creation_authorization_consume_oversized_wire(tmp_path: Path):
    store, project_root, prepared = _prepared_case(tmp_path)
    record = store.authorization_root / f"{prepared.authorization_digest}.json"
    record.write_bytes(b"x" * (64 * 1024 + 1))
    _assert_consume_failure(
        store,
        prepared.authorization_digest,
        tmp_path,
        project_root,
        "CREATION_AUTHORIZATION_INVALID",
        "authorization record is oversized",
    )


def test_creation_authorization_consume_nonobject_wire(tmp_path: Path):
    store, project_root, prepared = _prepared_case(tmp_path)
    record = store.authorization_root / f"{prepared.authorization_digest}.json"
    record.write_bytes(b"[]")
    _assert_consume_failure(
        store,
        prepared.authorization_digest,
        tmp_path,
        project_root,
        "CREATION_AUTHORIZATION_INVALID",
        "authorization record is malformed",
    )


def test_creation_authorization_consume_empty_nonce(tmp_path: Path):
    store, project_root, prepared = _prepared_case(tmp_path)
    original, altered, altered_digest = _alter_prepared_record(
        store,
        prepared.authorization_digest,
        lambda payload: payload.update(nonce=""),
    )
    assert original.read_bytes() != altered.read_bytes()
    _assert_consume_failure(
        store,
        altered_digest,
        tmp_path,
        project_root,
        "CREATION_AUTHORIZATION_INVALID",
        "authorization record is malformed",
    )


def test_creation_authorization_consume_field_digest(tmp_path: Path):
    store, project_root, prepared = _prepared_case(tmp_path)
    original, altered, altered_digest = _alter_prepared_record(
        store,
        prepared.authorization_digest,
        lambda payload: payload.update(actionDigest="bad"),
    )
    assert original.read_bytes() != altered.read_bytes()
    _assert_consume_failure(
        store,
        altered_digest,
        tmp_path,
        project_root,
        "CREATION_AUTHORIZATION_INVALID",
        "authorization record is malformed",
    )


def test_creation_authorization_consume_root_relative(tmp_path: Path):
    store, project_root, prepared = _prepared_case(tmp_path)
    original, altered, altered_digest = _alter_prepared_record(
        store,
        prepared.authorization_digest,
        lambda payload: payload.update(projectRoot="relative"),
    )
    assert original.read_bytes() != altered.read_bytes()
    _assert_consume_failure(
        store,
        altered_digest,
        tmp_path,
        project_root,
        "CREATION_AUTHORIZATION_INVALID",
        "authorization record is malformed",
    )


def test_creation_authorization_consume_request_field_type(tmp_path: Path):
    store, project_root, prepared = _prepared_case(tmp_path)

    def set_destination_to_none(payload: dict[str, object]) -> None:
        request = payload["request"]
        assert isinstance(request, dict)
        request["destination"] = None

    original, altered, altered_digest = _alter_prepared_record(
        store,
        prepared.authorization_digest,
        set_destination_to_none,
    )
    assert original.read_bytes() != altered.read_bytes()
    _assert_consume_failure(
        store,
        altered_digest,
        tmp_path,
        project_root,
        "CREATION_AUTHORIZATION_INVALID",
        "authorization record is malformed",
    )


def test_creation_authorization_peek_digest_type(tmp_path: Path):
    data_root = tmp_path / "data"
    project_root = tmp_path / "project"
    store = _case_store(data_root)
    before = _tree_snapshot(tmp_path)
    with pytest.raises(CreationAuthorizationError) as error:
        store.peek("bad")
    _assert_error(error, "CREATION_AUTHORIZATION_INVALID", "authorization digest is invalid")
    assert _tree_snapshot(tmp_path) == before
    assert not project_root.exists()


def test_creation_authorization_peek_oversized_wire(tmp_path: Path):
    store, project_root, prepared = _prepared_case(tmp_path)
    record = store.authorization_root / f"{prepared.authorization_digest}.json"
    record.write_bytes(b"x" * (64 * 1024 + 1))
    _assert_peek_failure(
        store,
        prepared.authorization_digest,
        tmp_path,
        project_root,
        "CREATION_AUTHORIZATION_INVALID",
        "authorization record is malformed",
    )


def test_creation_authorization_peek_envelope_shape(tmp_path: Path):
    store, project_root, prepared = _prepared_case(tmp_path)
    record = store.authorization_root / f"{prepared.authorization_digest}.json"
    record.write_bytes(b"[]")
    _assert_peek_failure(
        store,
        prepared.authorization_digest,
        tmp_path,
        project_root,
        "CREATION_AUTHORIZATION_INVALID",
        "authorization record is malformed",
    )


def test_creation_authorization_peek_consumed_state(tmp_path: Path):
    store, project_root, prepared = _prepared_case(tmp_path)
    store.consume(prepared.authorization_digest, authorized=True)
    _assert_peek_failure(
        store,
        prepared.authorization_digest,
        tmp_path,
        project_root,
        "CREATION_AUTHORIZATION_INVALID",
        "authorization record is malformed",
    )


def test_creation_authorization_peek_field_digest(tmp_path: Path):
    store, project_root, prepared = _prepared_case(tmp_path)
    original, altered, altered_digest = _alter_prepared_record(
        store,
        prepared.authorization_digest,
        lambda payload: payload.update(actionDigest="bad"),
    )
    assert original.read_bytes() != altered.read_bytes()
    _assert_peek_failure(
        store,
        altered_digest,
        tmp_path,
        project_root,
        "CREATION_AUTHORIZATION_INVALID",
        "authorization record is malformed",
    )


def test_creation_authorization_peek_expired(tmp_path: Path):
    store, project_root, prepared = _prepared_case(tmp_path)
    before = _tree_snapshot(tmp_path)
    later_store = _case_store(store.data_root, now_value=NOW + timedelta(hours=1))
    with pytest.raises(CreationAuthorizationError) as error:
        later_store.peek(prepared.authorization_digest)
    _assert_error(error, "CREATION_AUTHORIZATION_EXPIRED", "authorization has expired")
    assert _tree_snapshot(tmp_path) == before
    assert _tree_snapshot(project_root) is None


def test_creation_authorization_peek_root_relative(tmp_path: Path):
    store, project_root, prepared = _prepared_case(tmp_path)
    original, altered, altered_digest = _alter_prepared_record(
        store,
        prepared.authorization_digest,
        lambda payload: payload.update(projectRoot="relative"),
    )
    assert original.read_bytes() != altered.read_bytes()
    _assert_peek_failure(
        store,
        altered_digest,
        tmp_path,
        project_root,
        "CREATION_AUTHORIZATION_INVALID",
        "authorization record is malformed",
    )
