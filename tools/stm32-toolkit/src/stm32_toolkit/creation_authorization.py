"""Durable, single-use creation authorization records."""

from __future__ import annotations

import json
import os
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from stm32_toolkit.generation.creation import CreationRequest
from stm32_toolkit.generation.managed_files import canonical_json_bytes, sha256_hex

_DIGEST_CHARS = frozenset("0123456789abcdef")
_MAX_RECORD_BYTES = 64 * 1024
_LOCKS: dict[Path, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(path, threading.Lock())


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return _utc(value).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("time")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value).issubset(_DIGEST_CHARS)


class CreationAuthorizationError(ValueError):
    """Closed public authorization failure."""

    def __init__(self, code: str, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


@dataclass(frozen=True, slots=True)
class CreationPrepareRequest:
    request: CreationRequest
    project_root: Path
    plan_id: str
    action_digest: str
    environment_digest: str
    expires_at: str

    def __post_init__(self) -> None:
        if not isinstance(self.request, CreationRequest):
            raise CreationAuthorizationError("CREATION_AUTHORIZATION_INVALID", "authorization request is invalid")
        if not isinstance(self.project_root, Path) or not self.project_root.is_absolute():
            raise CreationAuthorizationError("CREATION_AUTHORIZATION_INVALID", "authorization project root is invalid")
        if not _digest(self.plan_id) or not _digest(self.action_digest) or not _digest(self.environment_digest):
            raise CreationAuthorizationError("CREATION_AUTHORIZATION_INVALID", "authorization digest is invalid")
        try:
            _parse_time(self.expires_at)
        except (TypeError, ValueError):
            raise CreationAuthorizationError("CREATION_AUTHORIZATION_INVALID", "authorization expiry is invalid") from None


@dataclass(frozen=True, slots=True)
class CreationAuthorizationResult:
    authorization_digest: str
    plan_id: str
    action_digest: str
    environment_digest: str
    expires_at: str
    # The record is written below the Toolkit data root; the planned project
    # destination remains byte-for-byte untouched, so the public workflow is
    # intentionally read-only from the user's project perspective.
    mutated: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "authorizationDigest": self.authorization_digest,
            "planId": self.plan_id,
            "actionDigest": self.action_digest,
            "executionEnvironmentDigest": self.environment_digest,
            "expiresAt": self.expires_at,
            "mutated": self.mutated,
        }


@dataclass(frozen=True, slots=True)
class ConsumedCreationAuthorization:
    authorization_digest: str
    nonce: str
    plan_id: str
    action_digest: str
    environment_digest: str
    project_root: Path
    request: CreationRequest
    issued_at: str
    expires_at: str
    record_path: Path

    @property
    def execution_environment_digest(self) -> str:
        return self.environment_digest

    def to_dict(self) -> dict[str, object]:
        return {
            "authorizationDigest": self.authorization_digest,
            "planId": self.plan_id,
            "actionDigest": self.action_digest,
            "executionEnvironmentDigest": self.environment_digest,
            "request": self.request.to_dict(),
        }


def _request_dict(value: object) -> CreationRequest:
    if not isinstance(value, dict):
        raise ValueError("request")
    source = value.get("source")
    if not isinstance(source, dict) or set(source) - {"kind", "value", "sha256"}:
        raise ValueError("source")
    kind, source_value = source.get("kind"), source.get("value")
    if kind == "mcu":
        result = CreationRequest.from_mcu(str(source_value), str(value.get("destination")), framework=str(value.get("framework")), language=str(value.get("language")))
    elif kind == "board":
        result = CreationRequest.from_board(str(source_value), str(value.get("destination")), framework=str(value.get("framework")), language=str(value.get("language")))
    elif kind == "ioc":
        result = CreationRequest(CreationRequest.from_ioc(str(source_value), str(value.get("destination")), framework=str(value.get("framework")), language=str(value.get("language"))).source, str(value.get("destination")), str(value.get("framework")), str(value.get("language")))
    else:
        raise ValueError("source kind")
    return result


class CreationAuthorizationStore:
    """File-backed capability store with atomic consume semantics."""

    def __init__(
        self,
        data_root: Path,
        *,
        now: Callable[[], datetime] | None = None,
        nonce_factory: Callable[[], str] | None = None,
    ) -> None:
        if not isinstance(data_root, Path):
            raise ValueError("data root")
        self.data_root = data_root.expanduser().resolve(strict=False)
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._nonce = nonce_factory or (lambda: secrets.token_urlsafe(24))

    @property
    def authorization_root(self) -> Path:
        return self.data_root / "creation" / "authorizations"

    @property
    def attempts_root(self) -> Path:
        return self.data_root / "creation" / "attempts"

    def prepare(self, request: CreationPrepareRequest) -> CreationAuthorizationResult:
        if not isinstance(request, CreationPrepareRequest):
            raise CreationAuthorizationError("CREATION_AUTHORIZATION_INVALID", "authorization request is invalid")
        try:
            now = _utc(self._now())
            expires = _parse_time(request.expires_at)
        except (TypeError, ValueError):
            raise CreationAuthorizationError("CREATION_AUTHORIZATION_INVALID", "authorization time is invalid") from None
        if expires <= now:
            raise CreationAuthorizationError("CREATION_AUTHORIZATION_EXPIRED", "authorization has expired")
        payload_base = {
            "schemaVersion": 1,
            "nonce": str(self._nonce()),
            "issuedAt": _iso(now),
            "expiresAt": request.expires_at,
            "state": "prepared",
            "planId": request.plan_id,
            "actionDigest": request.action_digest,
            "executionEnvironmentDigest": request.environment_digest,
            "projectRoot": request.project_root.as_posix(),
            "request": request.request.to_dict(),
        }
        digest = sha256_hex(canonical_json_bytes(payload_base))
        payload = {**payload_base, "authorizationDigest": digest}
        data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        if len(data) > _MAX_RECORD_BYTES:
            raise CreationAuthorizationError("CREATION_AUTHORIZATION_INVALID", "authorization record is oversized")
        root = self.authorization_root
        try:
            root.mkdir(parents=True, exist_ok=True)
            path = root / f"{digest}.json"
            with _lock_for(path):
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                fd = os.open(path, flags, 0o600)
                try:
                    os.write(fd, data)
                finally:
                    os.close(fd)
        except FileExistsError:
            raise CreationAuthorizationError("CREATION_AUTHORIZATION_INVALID", "authorization nonce collision") from None
        except OSError:
            raise CreationAuthorizationError("CREATION_AUTHORIZATION_STORE_UNAVAILABLE", "authorization store is unavailable") from None
        return CreationAuthorizationResult(digest, request.plan_id, request.action_digest, request.environment_digest, request.expires_at)

    def consume(self, authorization_digest: str, *, authorized: bool) -> ConsumedCreationAuthorization:
        if type(authorized) is not bool or authorized is not True:
            raise CreationAuthorizationError("CREATION_AUTHORIZATION_REQUIRED", "authorization must be the JSON boolean true")
        if not _digest(authorization_digest):
            raise CreationAuthorizationError("CREATION_AUTHORIZATION_INVALID", "authorization digest is invalid")
        path = self.authorization_root / f"{authorization_digest}.json"
        with _lock_for(path):
            try:
                data = path.read_bytes()
            except OSError:
                raise CreationAuthorizationError("CREATION_AUTHORIZATION_INVALID", "authorization record is unavailable") from None
            if len(data) > _MAX_RECORD_BYTES:
                raise CreationAuthorizationError("CREATION_AUTHORIZATION_INVALID", "authorization record is oversized")
            try:
                payload = json.loads(data.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError
                required = {"schemaVersion", "nonce", "issuedAt", "expiresAt", "state", "planId", "actionDigest", "executionEnvironmentDigest", "projectRoot", "request", "authorizationDigest"}
                if set(payload) != required or payload.get("schemaVersion") != 1 or payload.get("authorizationDigest") != authorization_digest:
                    raise ValueError
                if not isinstance(payload.get("nonce"), str) or not payload["nonce"] or payload.get("state") not in {"prepared", "consumed"}:
                    raise ValueError
                if not all(_digest(payload.get(field)) for field in ("planId", "actionDigest", "executionEnvironmentDigest")):
                    raise ValueError
                issued = _parse_time(payload["issuedAt"])
                expires = _parse_time(payload["expiresAt"])
                root = Path(str(payload["projectRoot"]))
                if not root.is_absolute() or root != root.resolve(strict=False):
                    raise ValueError
                request = _request_dict(payload["request"])
            except (UnicodeError, ValueError, TypeError, OSError, OverflowError):
                raise CreationAuthorizationError("CREATION_AUTHORIZATION_INVALID", "authorization record is malformed") from None
            if payload["state"] == "consumed":
                raise CreationAuthorizationError("CREATION_AUTHORIZATION_CONSUMED", "authorization has already been consumed")
            if _utc(self._now()) >= expires:
                raise CreationAuthorizationError("CREATION_AUTHORIZATION_EXPIRED", "authorization has expired")
            payload["state"] = "consumed"
            changed = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            temp = path.with_name(f".{path.name}.{self._nonce()}.tmp")
            try:
                temp.write_bytes(changed)
                os.replace(temp, path)
            except OSError:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass
                raise CreationAuthorizationError("CREATION_AUTHORIZATION_STORE_UNAVAILABLE", "authorization state cannot be consumed") from None
            return ConsumedCreationAuthorization(
                authorization_digest=authorization_digest,
                nonce=payload["nonce"],
                plan_id=payload["planId"],
                action_digest=payload["actionDigest"],
                environment_digest=payload["executionEnvironmentDigest"],
                project_root=root,
                request=request,
                issued_at=payload["issuedAt"],
                expires_at=payload["expiresAt"],
                record_path=path,
            )


__all__ = [
    "ConsumedCreationAuthorization",
    "CreationAuthorizationError",
    "CreationAuthorizationStore",
    "CreationPrepareRequest",
    "CreationAuthorizationResult",
]
