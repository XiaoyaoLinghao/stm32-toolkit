from __future__ import annotations

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


def test_malformed_record_is_closed_without_raw_record_data(tmp_path: Path):
    digest = "d" * 64
    path = tmp_path / "creation" / "authorizations" / f"{digest}.json"
    path.parent.mkdir(parents=True)
    path.write_text("{\"state\": [\"not-an-object\"]}", encoding="utf-8")
    with pytest.raises(CreationAuthorizationError) as error:
        CreationAuthorizationStore(tmp_path, now=lambda: NOW).consume(digest, authorized=True)
    assert error.value.code == "CREATION_AUTHORIZATION_INVALID"
    assert "not-an-object" not in str(error.value)


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
