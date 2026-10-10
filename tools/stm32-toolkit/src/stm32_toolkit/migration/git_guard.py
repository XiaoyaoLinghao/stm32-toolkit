"""Read-only, bounded Git evidence for the canonical project root.

Every invocation uses a fixed argument array, ``cwd=root``, ``stdin=DEVNULL``,
binary output, a 10-second timeout, and at most 1 MiB combined stdout/stderr.
No human-formatted Git output is parsed and no Git state is ever mutated.
Failures surface as ``MigrationPlanError`` with code ``MIGRATION_GIT_UNAVAILABLE``
and ``{"rule": <repository|head|status>}``.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from stm32_toolkit.migration.model import MigrationPlanError, full_sha_error

_GIT = "git"
_GIT_TIMEOUT = 10.0
_GIT_OUTPUT_LIMIT = 1024 * 1024  # 1 MiB combined stdout+stderr per invocation
_FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class _GitError(Exception):
    """Internal Git call failure; the caller maps it to the command's rule."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


def _git_unavailable(rule: str) -> MigrationPlanError:
    return MigrationPlanError(
        "MIGRATION_GIT_UNAVAILABLE",
        "Git evidence is unavailable",
        {"rule": rule},
    )


def _run_git(argv: list[str], cwd: Path) -> bytes:
    """Run one bounded read-only Git command and return its raw stdout bytes."""
    try:
        proc = subprocess.run(
            [_GIT, *argv],
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=_GIT_TIMEOUT,
            check=False,
        )
    except FileNotFoundError:
        raise _GitError("missing")
    except subprocess.TimeoutExpired:
        raise _GitError("timeout")
    combined = proc.stdout + proc.stderr
    if len(combined) > _GIT_OUTPUT_LIMIT:
        raise _GitError("overflow")
    if proc.returncode != 0:
        raise _GitError("nonzero")
    try:
        combined.decode("utf-8")
    except UnicodeDecodeError:
        raise _GitError("undecodable")
    return proc.stdout


def git_toplevel(root: Path) -> Path:
    """Canonical Git worktree toplevel for ``root``; raises on unavailability."""
    try:
        raw = _run_git(["rev-parse", "--show-toplevel"], root)
    except _GitError:
        raise _git_unavailable("repository")
    try:
        text = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        raise _git_unavailable("repository")
    if not text:
        raise _git_unavailable("repository")
    toplevel = Path(text)
    if not toplevel.is_absolute():
        raise _git_unavailable("repository")
    return toplevel


def git_head(root: Path) -> str:
    """Full committed HEAD SHA-256 hex; unborn/malformed raises rule ``head``."""
    try:
        raw = _run_git(["rev-parse", "HEAD"], root)
    except _GitError:
        raise _git_unavailable("head")
    try:
        head = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        raise _git_unavailable("head")
    if full_sha_error(head) is not None:
        raise _git_unavailable("head")
    assert _FULL_SHA_RE.match(head)
    return head


def porcelain_status(root: Path) -> bytes:
    """Raw porcelain v1 status bytes; any output means the worktree is dirty.

    Git ignored files produce no output and therefore do not dirty the
    baseline.  A failing or unreadable status call raises rule ``status``.
    """
    try:
        return _run_git(["status", "--porcelain=v1", "-z", "--untracked-files=all"], root)
    except _GitError:
        raise _git_unavailable("status")


def dirty_paths(status: bytes) -> tuple[tuple[str, str], ...]:
    """Classify porcelain-v1 -z entries as index, tracked, or untracked.

    Rename/copy entries have one extra NUL-delimited old name. The primary
    path is the destination shown by Git and all paths remain root-relative.
    """
    if not status:
        return ()
    parts = status.split(b"\0")
    if parts[-1] != b"":
        raise _git_unavailable("status")
    entries: list[tuple[str, str]] = []
    cursor = 0
    while cursor < len(parts) - 1:
        record = parts[cursor]
        cursor += 1
        if len(record) < 4 or record[2:3] != b" ":
            raise _git_unavailable("status")
        index, worktree = record[:1], record[1:2]
        try:
            path = record[3:].decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise _git_unavailable("status")
        if not path or path.startswith("/") or "\\" in path or any(
            part in {"", ".", ".."} for part in path.split("/")
        ):
            raise _git_unavailable("status")
        if index == b"?" and worktree == b"?":
            entries.append(("untracked", path))
        else:
            if index != b" ":
                entries.append(("index", path))
            if worktree != b" ":
                entries.append(("tracked", path))
        if index in {b"R", b"C"} or worktree in {b"R", b"C"}:
            if cursor >= len(parts) - 1:
                raise _git_unavailable("status")
            cursor += 1
    return tuple(entries)
