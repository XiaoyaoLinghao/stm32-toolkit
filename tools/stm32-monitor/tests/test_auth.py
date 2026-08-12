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
            method="GET",
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
                method="GET",
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


ORIGIN = "http://127.0.0.1:43125"


@pytest.mark.parametrize(
    ("method", "origin", "fetch_site", "websocket"),
    [
        ("GET", ORIGIN, None, False),
        ("GET", None, "same-origin", False),
        ("HEAD", ORIGIN, None, False),
        ("HEAD", None, "same-origin", False),
        ("GET", ORIGIN, None, True),
        ("GET", None, "same-origin", True),
        ("POST", ORIGIN, None, False),
        ("POST", ORIGIN, "same-origin", False),
        ("PATCH", ORIGIN, None, False),
        ("PUT", ORIGIN, None, False),
        ("DELETE", ORIGIN, None, False),
    ],
)
def test_cookie_safe_matrix_allows_only_proved_same_origin(
    method: str, origin: str | None, fetch_site: str | None, websocket: bool
) -> None:
    assert (
        _auth().authorize(
            peer="127.0.0.1",
            host="127.0.0.1:43125",
            origin=origin,
            authorization="",
            cookie=TOKEN,
            bootstrap=False,
            method=method,
            fetch_site=fetch_site,
            websocket=websocket,
        )
        == "cookie"
    )


def _authorize_cookie(overrides: dict[str, object]) -> str:
    request = dict(
        peer="127.0.0.1",
        host="127.0.0.1:43125",
        origin=ORIGIN,
        authorization="",
        cookie=TOKEN,
        bootstrap=False,
        method="GET",
        fetch_site=None,
        websocket=False,
    )
    request.update(overrides)
    return _auth().authorize(
        peer=request["peer"],
        host=request["host"],
        origin=request["origin"],
        authorization=request["authorization"],
        cookie=request["cookie"],
        bootstrap=request["bootstrap"],
        method=request["method"],
        fetch_site=request["fetch_site"],
        websocket=request["websocket"],
    )


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"peer": "192.0.2.1"}, "MONITOR_PEER_REJECTED"),
        ({"host": "localhost:43125"}, "MONITOR_HOST_REJECTED"),
        ({"origin": "http://localhost:43125"}, "MONITOR_ORIGIN_REJECTED"),
        ({"origin": "null"}, "MONITOR_ORIGIN_REJECTED"),
        ({"fetch_site": "cross-site"}, "MONITOR_ORIGIN_REJECTED"),
        ({"fetch_site": "same-site"}, "MONITOR_ORIGIN_REJECTED"),
        ({"fetch_site": "none"}, "MONITOR_ORIGIN_REJECTED"),
        ({"origin": None, "fetch_site": None}, "MONITOR_AUTH_REQUIRED"),
        ({"method": "POST", "origin": None, "fetch_site": "same-origin"}, "MONITOR_AUTH_REQUIRED"),
        ({"method": "PATCH", "origin": None, "fetch_site": "same-origin"}, "MONITOR_AUTH_REQUIRED"),
        ({"method": "PUT", "origin": None, "fetch_site": "same-origin"}, "MONITOR_AUTH_REQUIRED"),
        ({"method": "DELETE", "origin": None, "fetch_site": "same-origin"}, "MONITOR_AUTH_REQUIRED"),
        ({"method": "OPTIONS"}, "MONITOR_AUTH_REQUIRED"),
        ({"method": "POST", "websocket": True}, "MONITOR_AUTH_REQUIRED"),
        ({"bootstrap": True}, "MONITOR_AUTH_REQUIRED"),
    ],
)
def test_cookie_safe_matrix_denies_every_unproved_request(
    overrides: dict[str, object], code: str
) -> None:
    from stm32_monitor.auth import MonitorAuthError

    with pytest.raises(MonitorAuthError) as caught:
        _authorize_cookie(overrides)
    assert caught.value.code == code


@pytest.mark.parametrize("origin", [None, "null", "http://localhost:43125"])
def test_bearer_requires_exact_origin_even_with_exact_token(origin: str | None) -> None:
    from stm32_monitor.auth import MonitorAuthError

    with pytest.raises(MonitorAuthError):
        _auth().authorize(
            peer="127.0.0.1",
            host="127.0.0.1:43125",
            origin=origin,
            authorization=f"Bearer {TOKEN}",
            cookie=None,
            bootstrap=True,
            method="POST",
            fetch_site="same-origin",
            websocket=False,
        )


def test_exact_origin_bearer_and_bootstrap_still_work() -> None:
    assert (
        _auth().authorize(
            peer="127.0.0.1",
            host="127.0.0.1:43125",
            origin=ORIGIN,
            authorization=f"Bearer {TOKEN}",
            cookie=None,
            bootstrap=True,
            method="POST",
            fetch_site="same-origin",
            websocket=False,
        )
        == "bearer"
    )
