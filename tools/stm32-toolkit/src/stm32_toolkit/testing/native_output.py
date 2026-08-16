"""Strict shared adapters for frozen native test-runner output."""

from __future__ import annotations

import re
import unicodedata


class NativeOutputError(ValueError):
    """Native runner text is malformed or internally contradictory."""


class NativeExitMismatch(NativeOutputError):
    """Native per-node facts contradict the child process exit."""


def _node_name(value: str) -> str:
    if (
        not value or "\x00" in value or unicodedata.normalize("NFC", value) != value
        or len(value.encode("utf-8")) > 65536
    ):
        raise NativeOutputError("ctest-text native node name is invalid")
    return value


def parse_ctest_431_text(raw: bytes, *, exit_code: int | None = None) -> tuple[tuple[str, str], ...]:
    """Parse exact CTest 4.3.1 progress rows, summary, and process exit."""
    if not isinstance(raw, bytes) or len(raw) > 8 * 1024 * 1024:
        raise NativeOutputError("ctest-text native report exceeds its bound")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise NativeOutputError("ctest-text native report is invalid UTF-8") from exc
    row = re.compile(
        r"^\s*(?P<ordinal>[1-9][0-9]*)/(?P<total>[1-9][0-9]*) Test\s+#(?P<number>[1-9][0-9]*): "
        r"(?P<name>.+?) \.{3,}\s*(?P<status>Passed|Not Run|Skipped|\*\*\*Failed)\s+"
        r"(?P<seconds>[0-9]+(?:\.[0-9]+)?) sec$"
    )
    outcomes: list[tuple[str, str]] = []
    totals: set[int] = set()
    ordinals: list[int] = []
    for line in lines:
        match = row.fullmatch(line)
        if match is None:
            continue
        ordinals.append(int(match.group("ordinal")))
        totals.add(int(match.group("total")))
        status = match.group("status")
        outcomes.append((
            _node_name(match.group("name")),
            "failed" if status == "***Failed" else "skipped" if status in {"Not Run", "Skipped"} else "passed",
        ))
    result = tuple(outcomes)
    if (
        not result or len({node for node, _outcome in result}) != len(result)
        or totals != {len(result)} or ordinals != list(range(1, len(result) + 1))
    ):
        raise NativeOutputError("ctest-text native rows contradict inventory")
    summaries = [
        match for line in lines
        if (match := re.fullmatch(
            r"(?P<percent>[0-9]+)% tests passed, (?P<failed>[0-9]+) tests failed out of (?P<total>[0-9]+)",
            line,
        )) is not None
    ]
    if len(summaries) != 1:
        raise NativeOutputError("ctest-text native summary is missing or duplicated")
    summary = summaries[0]
    failed = sum(outcome == "failed" for _node, outcome in result)
    total = len(result)
    expected_percent = (2 * ((total - failed) * 100) + total) // (2 * total)
    if (
        int(summary.group("failed")) != failed
        or int(summary.group("total")) != total
        or int(summary.group("percent")) != expected_percent
    ):
        raise NativeOutputError("ctest-text native summary counts contradict nodes")
    if exit_code is None:
        return result
    if type(exit_code) is not int:
        raise NativeOutputError("ctest-text native exit code is invalid")
    if (exit_code == 0) == bool(failed):
        raise NativeExitMismatch("ctest-text native summary and exit code are inconsistent")
    return result
