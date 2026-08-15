def node() -> None:
    assert True


def passed() -> None:
    assert True


def failed() -> None:
    assert False


def unexpected() -> None:
    assert True


def expected() -> None:
    import pytest
    pytest.skip("native fixture")


def wrong() -> None:
    assert True
