from __future__ import annotations

import pytest


TOKEN_BYTES = bytes(range(32))
TOKEN = TOKEN_BYTES.hex()


def _auth():
    from stm32_monitor.auth import MonitorAuth

    return MonitorAuth.create(
        host="127.0.0.1",
        port=43125,
        token_factory=lambda size: TOKEN_BYTES if size == 32 else b"",
    )


def test_token_is_exactly_32_random_bytes_and_never_appears_in_repr() -> None:
    auth = _auth()

    assert auth.token == TOKEN
    assert auth.token_digest != TOKEN
    assert len(auth.token_digest) == 64
    assert TOKEN not in repr(auth)


@pytest.mark.parametrize("bad", [b"", b"x" * 31, b"x" * 33, "x" * 32])
def test_token_factory_must_return_exactly_32_bytes(bad: object) -> None:
    from stm32_monitor.auth import MonitorAuth

    with pytest.raises(ValueError, match="token factory"):
        MonitorAuth.create(
            host="127.0.0.1", port=43125, token_factory=lambda _size: bad
        )


def test_bearer_auth_accepts_exact_loopback_origin_and_rejects_wrong_token() -> None:
    from stm32_monitor.auth import MonitorAuthError

    auth = _auth()
    assert (
        auth.authorize(
            peer="127.0.0.1",
            host="127.0.0.1:43125",
            origin="http://127.0.0.1:43125",
            authorization=f"Bearer {TOKEN}",
            cookie=None,
            bootstrap=False,
        )
        == "bearer"
    )
    with pytest.raises(MonitorAuthError) as caught:
        auth.authorize(
            peer="127.0.0.1",
            host="127.0.0.1:43125",
            origin="http://127.0.0.1:43125",
            authorization="Bearer " + "f" * 64,
            cookie=None,
            bootstrap=False,
        )
    assert (caught.value.code, caught.value.status) == ("MONITOR_AUTH_REQUIRED", 401)
    assert TOKEN not in str(caught.value)


@pytest.mark.parametrize(
    ("peer", "host", "origin", "code"),
    [
        ("192.0.2.1", "127.0.0.1:43125", None, "MONITOR_PEER_REJECTED"),
        ("127.0.0.1", "localhost:43125", None, "MONITOR_HOST_REJECTED"),
        ("127.0.0.1", "evil.invalid", None, "MONITOR_HOST_REJECTED"),
        (
            "127.0.0.1",
            "127.0.0.1:43125",
            "http://localhost:43125",
            "MONITOR_ORIGIN_REJECTED",
        ),
    ],
)
def test_peer_host_and_origin_are_exact(peer: str, host: str, origin: str | None, code: str) -> None:
    from stm32_monitor.auth import MonitorAuthError

    with pytest.raises(MonitorAuthError) as caught:
        _auth().authorize(
            peer=peer,
            host=host,
            origin=origin,
            authorization=f"Bearer {TOKEN}",
            cookie=None,
            bootstrap=False,
        )
    assert caught.value.code == code


def test_cookie_auth_requires_exact_origin_and_bootstrap_requires_bearer() -> None:
    from stm32_monitor.auth import MonitorAuthError

    auth = _auth()
    assert (
        auth.authorize(
            peer="127.0.0.1",
            host="127.0.0.1:43125",
            origin="http://127.0.0.1:43125",
            authorization="",
            cookie=TOKEN,
            bootstrap=False,
        )
        == "cookie"
    )
    for origin, bootstrap in [(None, False), ("http://127.0.0.1:43125", True)]:
        with pytest.raises(MonitorAuthError) as caught:
            auth.authorize(
                peer="127.0.0.1",
                host="127.0.0.1:43125",
                origin=origin,
                authorization="",
                cookie=TOKEN,
                bootstrap=bootstrap,
            )
        assert caught.value.code == "MONITOR_AUTH_REQUIRED"


def test_header_budget_is_bounded_before_authentication() -> None:
    from stm32_monitor.auth import MAX_REQUEST_BYTES, MonitorAuthError

    auth = _auth()
    with pytest.raises(MonitorAuthError) as caught:
        auth.require_header_budget((("X-Fill", "x" * MAX_REQUEST_BYTES),))
    assert (caught.value.code, caught.value.status) == (
        "MONITOR_REQUEST_TOO_LARGE",
        431,
    )

