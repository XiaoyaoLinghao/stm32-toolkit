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


def test_http_default_port_has_only_two_exact_authority_and_origin_forms() -> None:
    from stm32_monitor.auth import (
        MonitorAuth,
        MonitorAuthError,
        http_authority,
        http_origin,
        matches_http_host,
        matches_http_origin,
    )
    from stm32_monitor.service import MonitorEndpoint

    auth = MonitorAuth.create(
        host="127.0.0.1", port=80,
        token_factory=lambda size: TOKEN_BYTES if size == 32 else b"",
    )
    endpoint = MonitorEndpoint("127.0.0.1", 80, auth.token, "workspace", "session")
    assert http_authority("127.0.0.1", 80) == "127.0.0.1"
    assert http_origin("127.0.0.1", 80) == "http://127.0.0.1"
    assert auth.origin == endpoint.url == "http://127.0.0.1"
    assert endpoint.access_url == f"http://127.0.0.1/#token={TOKEN}"

    valid_hosts = ("127.0.0.1", "127.0.0.1:80")
    valid_origins = ("http://127.0.0.1", "http://127.0.0.1:80")
    for host in valid_hosts:
        assert matches_http_host(host, "127.0.0.1", 80)
        for origin in valid_origins:
            assert matches_http_origin(origin, "127.0.0.1", 80)
            assert auth.authorize(
                peer="127.0.0.1", host=host, origin=origin,
                authorization=f"Bearer {TOKEN}", cookie=None, bootstrap=True,
                method="POST", fetch_site="same-origin",
            ) == "bearer"
            assert auth.authorize(
                peer="127.0.0.1", host=host, origin=origin,
                authorization="", cookie=TOKEN, bootstrap=False, method="GET",
            ) == "cookie"

    bad_hosts = (
        "127.0.0.1:080", "127.0.0.1:81", "localhost", "127.0.0.1.",
        "127.0.0.1/path", "user@127.0.0.1", " 127.0.0.1", "127.0.0.1:80 ",
    )
    for host in bad_hosts:
        assert not matches_http_host(host, "127.0.0.1", 80)
        with pytest.raises(MonitorAuthError) as caught:
            auth.authorize(
                peer="127.0.0.1", host=host, origin=valid_origins[0],
                authorization=f"Bearer {TOKEN}", cookie=None, bootstrap=True,
                method="POST",
            )
        assert caught.value.code == "MONITOR_HOST_REJECTED"

    bad_origins = (
        "http://127.0.0.1:080", "http://127.0.0.1:81", "http://localhost",
        "http://127.0.0.1.", "http://127.0.0.1/path", "http://127.0.0.1?x=1",
        "http://127.0.0.1/#x", "https://127.0.0.1", "HTTP://127.0.0.1",
        "http://user@127.0.0.1", " http://127.0.0.1",
    )
    for origin in bad_origins:
        assert not matches_http_origin(origin, "127.0.0.1", 80)
        with pytest.raises(MonitorAuthError) as caught:
            auth.authorize(
                peer="127.0.0.1", host=valid_hosts[0], origin=origin,
                authorization=f"Bearer {TOKEN}", cookie=None, bootstrap=True,
                method="POST",
            )
        assert caught.value.code == "MONITOR_ORIGIN_REJECTED"


def test_nondefault_http_port_keeps_one_explicit_form() -> None:
    from stm32_monitor.auth import (
        MonitorAuthError, http_authority, http_origin, matches_http_host,
        matches_http_origin,
    )
    from stm32_monitor.service import MonitorEndpoint

    auth = _auth()
    endpoint = MonitorEndpoint("127.0.0.1", 43125, TOKEN, "workspace", "session")
    assert http_authority("127.0.0.1", 43125) == "127.0.0.1:43125"
    assert http_origin("127.0.0.1", 43125) == ORIGIN
    assert auth.origin == endpoint.url == ORIGIN
    assert matches_http_host("127.0.0.1:43125", "127.0.0.1", 43125)
    assert matches_http_origin(ORIGIN, "127.0.0.1", 43125)
    assert not matches_http_host("127.0.0.1", "127.0.0.1", 43125)
    assert not matches_http_origin("http://127.0.0.1", "127.0.0.1", 43125)
    with pytest.raises(MonitorAuthError) as host_error:
        auth.authorize(peer="127.0.0.1", host="127.0.0.1", origin=ORIGIN,
                       authorization=f"Bearer {TOKEN}", cookie=None, bootstrap=True)
    assert host_error.value.code == "MONITOR_HOST_REJECTED"
    with pytest.raises(MonitorAuthError) as origin_error:
        auth.authorize(peer="127.0.0.1", host="127.0.0.1:43125",
                       origin="http://127.0.0.1", authorization=f"Bearer {TOKEN}",
                       cookie=None, bootstrap=True)
    assert origin_error.value.code == "MONITOR_ORIGIN_REJECTED"


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


def test_header_budget_rejects_non_utf8_header_bytes() -> None:
    from stm32_monitor.auth import MonitorAuthError

    auth = _auth()
    with pytest.raises(MonitorAuthError) as caught:
        auth.require_header_budget((("X-Name", chr(0xD800)),))
    assert (caught.value.code, caught.value.status) == (
        "MONITOR_REQUEST_INVALID",
        400,
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


def test_create_rejects_non_loopback_endpoint_before_token_allocation() -> None:
    from stm32_monitor.auth import MonitorAuth

    calls = 0

    def token_factory(size: int) -> bytes:
        nonlocal calls
        calls += 1
        return b"s" * size

    valid = MonitorAuth.create(
        host="127.0.0.1", port=43125, token_factory=token_factory
    )
    assert valid.host == "127.0.0.1"
    assert valid.port == 43125
    calls_before_rejected_endpoint = calls

    with pytest.raises(ValueError, match="Monitor authentication endpoint is invalid"):
        MonitorAuth.create(
            host="localhost", port=43125, token_factory=token_factory
        )

    assert calls == calls_before_rejected_endpoint
