"""Deterministic, read-only analysis of group/file include-only scopes.

Keil permits ``IncludePath`` on a group or file in addition to the target
include list.  The migration may represent such a scope only as an additive
target include directory: no source file may silently resolve to a different
header because a scope was merged.

This module performs the single analysis shared by preflight and planning:

* Only include-only scopes whose compiled sources are included C/C++ sources
  contribute.  A scope that also carries defines or misc controls keeps its
  existing ``ARMCC_OPTION_UNSUPPORTED`` blocker and is never partially merged.
  A scope that also compiles included assembly or an unknown ``other``
  language keeps the same blocker instead of dropping those semantics.
  Listed headers and precompiled libraries do not execute a compiler, so they
  are ignored for this decision.  An excluded file scope, a header/library-only
  group or file, or a group with no included source cannot broaden anything
  and is ignored.
* The inspection-normalized, root-relative path is resolved exactly once
  against the canonical project root.  It is never re-resolved against the
  ``.uvprojx`` directory.
* Every contributed directory must exist, be a real directory, stay inside
  the canonical root, be readable, and contain no unsupported symlink or
  reparse entry.
* Traversal and hashing are bounded by one aggregate budget for the whole
  analysis (entries, files, directories, depth, and hashed bytes).  A bound is
  a stable blocker, never a partial result.
* Conflict detection compares full case-insensitive include-relative lookup
  keys, not bare file names.  A lookup key that resolves to distinct files
  under different search roots is a blocker; the same physical file exposed
  through overlapping roots (for example ``USER`` and ``USER/IWDG``) is not.
* Each added directory records a bounded inventory digest so a fresh apply
  replan detects content changes, additions, or removals that Git ignores.

The analysis never writes, never runs subprocesses, and never consults Git.
"""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from stm32_toolkit.keil import KeilInspection, KeilScopedOptions, KeilSource
from stm32_toolkit.migration.model import IncludeMerge, MigrationBlocker, portable_path_error

_COMPILED_LANGUAGES = ("c", "cxx")
#: Listed headers and precompiled libraries are project entries, not compiler
#: invocations: a group or file include path has no compile effect through
#: them, so they never make a scope "unsupported".
_NON_COMPILED_LANGUAGES = ("header", "library")

#: One aggregate traversal budget for the whole analysis.  Include directories
#: and their contents are untrusted input; exceeding a bound is a blocker so a
#: partial inventory can never feed a conflict decision.
MAX_TOTAL_ENTRIES = 80_000
MAX_TOTAL_FILES = 40_000
MAX_TOTAL_DIRECTORIES = 8_000
MAX_HASH_BYTES = 64 * 1024 * 1024
MAX_SCAN_DEPTH = 32

#: Evidence strings are bounded consistently with inspection findings.
MAX_EVIDENCE = 200

INCLUDE_PATH_MISSING = "MIGRATION_INCLUDE_PATH_MISSING"
INCLUDE_PATH_NOT_DIRECTORY = "MIGRATION_INCLUDE_PATH_NOT_DIRECTORY"
INCLUDE_PATH_ESCAPES = "MIGRATION_INCLUDE_PATH_ESCAPES"
INCLUDE_PATH_UNREADABLE = "MIGRATION_INCLUDE_PATH_UNREADABLE"
INCLUDE_REDIRECT_UNSUPPORTED = "MIGRATION_INCLUDE_REDIRECT_UNSUPPORTED"
INCLUDE_LIMIT_EXCEEDED = "MIGRATION_INCLUDE_LIMIT_EXCEEDED"
INCLUDE_COLLISION = "MIGRATION_INCLUDE_COLLISION"

_PATH_MESSAGES = {
    "missing": (
        INCLUDE_PATH_MISSING,
        "scoped include path is missing; it must name an existing directory"
        " inside the project",
    ),
    "notDirectory": (
        INCLUDE_PATH_NOT_DIRECTORY,
        "scoped include path is not a directory",
    ),
    "escapes": (
        INCLUDE_PATH_ESCAPES,
        "scoped include path escapes the canonical project root",
    ),
    "unreadable": (
        INCLUDE_PATH_UNREADABLE,
        "scoped include path or its inventory cannot be read",
    ),
    "redirect": (
        INCLUDE_REDIRECT_UNSUPPORTED,
        "scoped include path or its inventory contains an unsupported"
        " symlink/reparse entry",
    ),
    "limit": (
        INCLUDE_LIMIT_EXCEEDED,
        "scoped include inventory exceeds the bounded analysis budget",
    ),
}


class _InventoryLimit(Exception):
    """Internal: one directory listing exceeded the sanity entry bound."""


@dataclass(frozen=True)
class ScopedIncludeAnalysis:
    """Proposed target include list plus reviewed merge evidence.

    ``include_paths`` equals the inspection target list when no scope is
    mergeable, so a blocked or scope-free conversion keeps its historical
    manifest bytes.  ``blockers`` is non-empty exactly when no merge may be
    applied (all-or-nothing per analysis: an invalid scope never contributes
    a partial subset).
    """

    include_paths: tuple[str, ...]
    merges: tuple[IncludeMerge, ...]
    blockers: tuple[MigrationBlocker, ...]


@dataclass(frozen=True)
class IncludeScopeClassification:
    """Include-only scopes split by whether their semantics are representable.

    ``mergeable`` scopes compile only included C/C++ sources and may contribute
    their directories to the target include list.  ``blocked`` scopes also
    compile included assembly or an unknown ``other`` language, so they keep
    the existing ``ARMCC_OPTION_UNSUPPORTED`` blocker.  Scopes with no compiled
    source (excluded files, listed headers, precompiled libraries, or a group
    with no included source) appear in neither tuple and are ignored.
    """

    mergeable: tuple[KeilScopedOptions, ...]
    blocked: tuple[KeilScopedOptions, ...]


@dataclass(frozen=True)
class _DirectoryInventory:
    canonical: Path
    files: tuple[str, ...]  # root-relative POSIX file paths
    digest: str | None
    file_count: int


@dataclass
class _ScanBudget:
    """Aggregate traversal budget shared by every directory in one analysis."""

    entries: int = 0
    files: int = 0
    directories: int = 0
    hash_bytes: int = 0

    def take_entry(self) -> bool:
        self.entries += 1
        return self.entries <= MAX_TOTAL_ENTRIES

    def take_file(self) -> bool:
        self.files += 1
        return self.files <= MAX_TOTAL_FILES

    def take_directory(self) -> bool:
        self.directories += 1
        return self.directories <= MAX_TOTAL_DIRECTORIES

    def take_hash_bytes(self, size: int) -> bool:
        self.hash_bytes += size
        return self.hash_bytes <= MAX_HASH_BYTES


@dataclass
class _NewDirectory:
    """One newly exposed directory awaiting inventory and conflict evidence."""

    rel: str
    canonical: Path
    key: str
    scope: str
    owner: str
    inventory: _DirectoryInventory | None = None


@dataclass
class _MergeEntry:
    scope: str
    owner: str
    rel: str
    key: str
    added: bool


@dataclass(frozen=True)
class _LookupEntry:
    """One file as a candidate resolution of one include-relative key."""

    root_rel: str
    file_rel: str
    physical: str
    new_index: int | None


# ---------------------------------------------------------------------------
# path and directory validation
# ---------------------------------------------------------------------------


def _is_redirect(path: str, entry_stat: os.stat_result) -> bool:
    """Whether one host entry is a symlink or Windows reparse point.

    The host path is part of the signature so a test can deterministically
    simulate a redirect without requiring privilege.  Production behavior
    depends only on the ``lstat`` result.
    """
    if stat.S_ISLNK(entry_stat.st_mode):
        return True
    attributes = getattr(entry_stat, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(reparse and attributes & reparse)


def _list_entries(directory: Path) -> list[tuple[str, str]]:
    """Return sorted ``(name, host path)`` entries of one directory.

    The listing itself has an absolute sanity bound so an adversarial
    directory cannot force unbounded memory use; the aggregate budget is
    applied by the caller.
    """
    entries: list[tuple[str, str]] = []
    with os.scandir(directory) as iterator:
        for entry in iterator:
            entries.append((entry.name, entry.path))
            if len(entries) > MAX_TOTAL_ENTRIES:
                raise _InventoryLimit
    entries.sort(key=lambda item: item[0])
    return entries


def _normalized_relative(rel: str) -> bool:
    """A portable root-relative directory spelling (``.`` names the root)."""
    if rel == ".":
        return True
    return portable_path_error(rel) is None


def _inspect_directory(root: Path, rel: str) -> tuple[Path | None, str | None]:
    """Resolve one inspection-normalized include directory exactly once.

    Returns ``(canonical, None)`` or ``(None, reason)`` where reason is a
    ``_PATH_MESSAGES`` key.  Every component, including the target, is
    ``lstat``-ed so an unsupported redirect is rejected before it is followed.
    """
    if not _normalized_relative(rel):
        return None, "escapes"
    components = () if rel == "." else tuple(rel.split("/"))
    current = root
    entry_stat: os.stat_result | None = None
    for component in components:
        current = current / component
        try:
            entry_stat = os.lstat(current)
        except (FileNotFoundError, NotADirectoryError):
            return None, "missing"
        except OSError:
            return None, "unreadable"
        if _is_redirect(str(current), entry_stat):
            return None, "redirect"
        if not stat.S_ISDIR(entry_stat.st_mode):
            return None, "notDirectory"
    if entry_stat is None:
        try:
            entry_stat = os.lstat(root)
        except (FileNotFoundError, NotADirectoryError):
            return None, "missing"
        except OSError:
            return None, "unreadable"
        if _is_redirect(str(root), entry_stat):
            return None, "redirect"
        if not stat.S_ISDIR(entry_stat.st_mode):
            return None, "notDirectory"
    try:
        canonical = current.resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return None, "unreadable"
    try:
        canonical.relative_to(root)
    except ValueError:
        return None, "escapes"
    return canonical, None


def _existing_directory(root: Path, rel: str) -> Path | None:
    """Canonical path of an existing target include directory, else ``None``.

    Missing, non-directory, and escaping target entries keep their historical
    inspection warning behavior and are simply not scanned; only newly
    exposed scopes are required to exist.
    """
    if not _normalized_relative(rel):
        return None
    candidate = root if rel == "." else root.joinpath(*rel.split("/"))
    try:
        if not candidate.is_dir():
            return None
        canonical = candidate.resolve(strict=True)
        canonical.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return None
    return canonical


def _directory_key(canonical: Path) -> str:
    return os.path.normcase(str(canonical))


def _file_identity(canonical: Path, file_rel: str) -> str:
    return os.path.normcase(str(canonical.joinpath(*file_rel.split("/"))))


def _join_rel(root_rel: str, file_rel: str) -> str:
    return file_rel if root_rel == "." else f"{root_rel}/{file_rel}"


# ---------------------------------------------------------------------------
# bounded directory inventory
# ---------------------------------------------------------------------------


def _scan_directory(
    canonical: Path, *, hash_content: bool, budget: _ScanBudget
) -> tuple[_DirectoryInventory | None, str | None]:
    """Inventory one directory tree within the aggregate traversal budget.

    Returns ``(inventory, None)`` or ``(None, reason)``.  Redirects, unreadable
    entries, and any exhausted bound abort the whole inventory so a partial
    file set is never compared.
    """
    stack: list[tuple[Path, str, int]] = [(canonical, "", 0)]
    files: list[str] = []
    digests: dict[str, str] = {}
    while stack:
        directory, rel_dir, depth = stack.pop()
        if depth > MAX_SCAN_DEPTH:
            return None, "limit"
        if not budget.take_directory():
            return None, "limit"
        try:
            listing = _list_entries(directory)
        except _InventoryLimit:
            return None, "limit"
        except (OSError, ValueError):
            return None, "unreadable"
        for name, host in listing:
            if not budget.take_entry():
                return None, "limit"
            rel = f"{rel_dir}/{name}" if rel_dir else name
            try:
                entry_stat = os.lstat(host)
            except OSError:
                return None, "unreadable"
            if _is_redirect(host, entry_stat):
                return None, "redirect"
            if stat.S_ISDIR(entry_stat.st_mode):
                stack.append((Path(host), rel, depth + 1))
                continue
            if not stat.S_ISREG(entry_stat.st_mode):
                return None, "unreadable"
            if not budget.take_file():
                return None, "limit"
            files.append(rel)
            if hash_content:
                if not budget.take_hash_bytes(entry_stat.st_size):
                    return None, "limit"
                try:
                    with open(host, "rb") as handle:
                        data = handle.read(entry_stat.st_size + 1)
                except OSError:
                    return None, "unreadable"
                if len(data) != entry_stat.st_size:
                    return None, "unreadable"
                digests[rel] = hashlib.sha256(data).hexdigest()
    digest: str | None = None
    if hash_content:
        builder = hashlib.sha256()
        for rel in sorted(files):
            builder.update(f"{rel}\x00{digests[rel]}\n".encode("utf-8"))
        digest = builder.hexdigest()
    ordered = tuple(sorted(files))
    return (
        _DirectoryInventory(
            canonical=canonical,
            files=ordered,
            digest=digest,
            file_count=len(ordered),
        ),
        None,
    )


# ---------------------------------------------------------------------------
# blockers
# ---------------------------------------------------------------------------


def _evidence(scope: str, owner: str, detail: str) -> str:
    return f"{scope}:{owner}|{detail}"[:MAX_EVIDENCE]


def _blocker(
    code: str,
    message: str,
    path: str,
    evidence: str,
) -> MigrationBlocker:
    return MigrationBlocker(code, code, path, 0, 0, evidence[:MAX_EVIDENCE], message)


def _blocker_path(rel: str, project_file: str) -> str:
    """A portable blocker path for one analyzed directory.

    An escaping or root spelling cannot be emitted as a portable path; the
    project file is the stable portable anchor for those cases.
    """
    if _normalized_relative(rel) and rel != ".":
        return rel
    if portable_path_error(project_file) is None:
        return project_file
    return rel


# ---------------------------------------------------------------------------
# scope classification
# ---------------------------------------------------------------------------


def classify_include_scopes(inspection: KeilInspection) -> IncludeScopeClassification:
    """Split include-only group/file scopes by representable semantics.

    A group scope covers every included compiled source in that group (group
    options apply to more than C/C++ compilation); a file scope covers that
    one file.  Listed headers and precompiled libraries are not compiled by
    the C compiler and are ignored for this decision.  Only a scope whose
    compiled sources are all included C/C++ may merge its directories.  A
    scope that also compiles included assembly or an unknown ``other``
    language keeps the existing option blocker, and a scope with no compiled
    source is ignored.
    """
    included_by_group: dict[str, list[KeilSource]] = {}
    included_by_path: dict[str, KeilSource] = {}
    for source in inspection.sources:
        if not source.included:
            continue
        included_by_group.setdefault(source.group, []).append(source)
        included_by_path.setdefault(source.path, source)

    mergeable: list[KeilScopedOptions] = []
    blocked: list[KeilScopedOptions] = []
    for option in inspection.scoped_options:
        if option.scope not in {"group", "file"}:
            continue
        if option.defines or option.misc_controls:
            # The ordinary scoped-option blocker already covers this scope.
            continue
        if not option.include_paths:
            continue
        if option.scope == "file":
            if not option.include_in_build:
                continue
            source = included_by_path.get(option.owner)
            if source is None:
                continue
            covered = (
                ()
                if source.language in _NON_COMPILED_LANGUAGES
                else (source,)
            )
        else:
            covered = tuple(
                source
                for source in included_by_group.get(option.owner, ())
                if source.language not in _NON_COMPILED_LANGUAGES
            )
        if not covered:
            # No compiler invocation is affected by this include path.
            continue
        if all(source.language in _COMPILED_LANGUAGES for source in covered):
            mergeable.append(option)
        else:
            blocked.append(option)
    return IncludeScopeClassification(tuple(mergeable), tuple(blocked))


# ---------------------------------------------------------------------------
# public analysis
# ---------------------------------------------------------------------------


def _result_with_blockers(
    inspection: KeilInspection, blockers: list[MigrationBlocker]
) -> ScopedIncludeAnalysis:
    return ScopedIncludeAnalysis(
        include_paths=tuple(inspection.include_paths),
        merges=(),
        blockers=tuple(blockers),
    )


def analyze_scoped_includes(root: Path, inspection: KeilInspection) -> ScopedIncludeAnalysis:
    """Analyze include-only group/file scopes without writing or touching Git."""
    options = classify_include_scopes(inspection).mergeable
    if not options:
        return ScopedIncludeAnalysis(tuple(inspection.include_paths), (), ())

    seen: set[str] = set()
    for rel in inspection.include_paths:
        canonical = _existing_directory(root, rel)
        if canonical is not None:
            seen.add(_directory_key(canonical))
        elif _normalized_relative(rel):
            # Missing target directories keep their inspection warning; their
            # canonical spelling still deduplicates a proposed scope path.
            candidate = root if rel == "." else root.joinpath(*rel.split("/"))
            try:
                seen.add(_directory_key(candidate.resolve(strict=False)))
            except (OSError, RuntimeError, ValueError):
                pass

    merge_entries: list[_MergeEntry] = []
    new_directories: list[_NewDirectory] = []
    blockers: list[MigrationBlocker] = []

    for option in options:
        scope_errors: list[tuple[str, str]] = []
        resolved: list[tuple[str, Path]] = []
        for rel in option.include_paths:
            canonical, error = _inspect_directory(root, rel)
            if error is not None:
                scope_errors.append((rel, error))
            else:
                assert canonical is not None
                resolved.append((rel, canonical))
        if scope_errors:
            for rel, reason in scope_errors:
                code, message = _PATH_MESSAGES[reason]
                blockers.append(
                    _blocker(
                        code,
                        message,
                        _blocker_path(rel, inspection.project_file),
                        _evidence(option.scope, option.owner, rel),
                    )
                )
            # An invalid scope never contributes a partial subset.
            continue
        for rel, canonical in resolved:
            key = _directory_key(canonical)
            added = key not in seen
            if added:
                seen.add(key)
                new_directories.append(
                    _NewDirectory(
                        rel=rel,
                        canonical=canonical,
                        key=key,
                        scope=option.scope,
                        owner=option.owner,
                    )
                )
            merge_entries.append(
                _MergeEntry(
                    scope=option.scope,
                    owner=option.owner,
                    rel=rel,
                    key=key,
                    added=added,
                )
            )

    if blockers:
        return _result_with_blockers(inspection, blockers)

    if new_directories:
        existing_directories: list[tuple[str, Path]] = []
        for rel in inspection.include_paths:
            canonical = _existing_directory(root, rel)
            if canonical is not None:
                existing_directories.append((rel, canonical))

        # One inventory per canonical directory: an existing target list may
        # repeat a directory under different spellings, and a new scope may
        # resolve to the same physical directory.  Traversing it once keeps
        # the aggregate budget honest.
        inventory_cache: dict[str, _DirectoryInventory] = {}
        budget = _ScanBudget()
        for rel, canonical in existing_directories:
            key = _directory_key(canonical)
            if key in inventory_cache:
                continue
            inventory, error = _scan_directory(
                canonical, hash_content=False, budget=budget
            )
            if error is not None:
                # One exhausted/unreadable inventory rejects the whole
                # analysis; further scans would only repeat the same bound.
                code, message = _PATH_MESSAGES[error]
                blockers.append(
                    _blocker(
                        code,
                        message,
                        _blocker_path(rel, inspection.project_file),
                        _evidence("target", rel, rel),
                    )
                )
                break
            assert inventory is not None
            inventory_cache[key] = inventory
        if not blockers:
            for new in new_directories:
                if new.key in inventory_cache:
                    continue
                inventory, error = _scan_directory(
                    new.canonical, hash_content=True, budget=budget
                )
                if error is not None:
                    code, message = _PATH_MESSAGES[error]
                    blockers.append(
                        _blocker(
                            code,
                            message,
                            _blocker_path(new.rel, inspection.project_file),
                            _evidence(new.scope, new.owner, new.rel),
                        )
                    )
                    break
                assert inventory is not None
                new.inventory = inventory
                inventory_cache[new.key] = inventory

        if not blockers:
            blockers.extend(
                _collision_blockers(
                    new_directories,
                    existing_directories,
                    inventory_cache,
                    inspection,
                )
            )

        if blockers:
            return _result_with_blockers(inspection, blockers)

    merges: list[IncludeMerge] = []
    appended: list[str] = []
    inventory_by_key = {
        new.key: new.inventory for new in new_directories if new.inventory is not None
    }
    for entry in merge_entries:
        if entry.added:
            inventory = inventory_by_key[entry.key]
            merges.append(
                IncludeMerge(
                    scope=entry.scope,
                    owner=entry.owner,
                    path=entry.rel,
                    decision="added",
                    inventory_sha256=inventory.digest,
                    inventory_files=inventory.file_count,
                )
            )
            appended.append(entry.rel)
        else:
            merges.append(
                IncludeMerge(
                    scope=entry.scope,
                    owner=entry.owner,
                    path=entry.rel,
                    decision="already-present",
                    inventory_sha256=None,
                    inventory_files=None,
                )
            )
    return ScopedIncludeAnalysis(
        include_paths=tuple(inspection.include_paths) + tuple(appended),
        merges=tuple(merges),
        blockers=(),
    )


def _collision_blockers(
    new_directories: list[_NewDirectory],
    existing_directories: list[tuple[str, Path]],
    inventory_cache: dict[str, _DirectoryInventory],
    inspection: KeilInspection,
) -> list[MigrationBlocker]:
    """Ambiguous include-relative keys involving a newly exposed directory.

    Every search root contributes each file under its root-relative lookup
    key.  The same key resolving to distinct physical files is ambiguous.  A
    file exposed through overlapping roots contributes several keys but each
    maps to that same physical file, so overlap alone is not a conflict.
    """
    entries_by_key: dict[str, list[_LookupEntry]] = {}
    roots = [(rel, canonical, None) for rel, canonical in existing_directories]
    roots.extend(
        (new.rel, new.canonical, index) for index, new in enumerate(new_directories)
    )
    for root_rel, canonical, new_index in roots:
        inventory = inventory_cache[_directory_key(canonical)]
        for file_rel in inventory.files:
            entries_by_key.setdefault(file_rel.casefold(), []).append(
                _LookupEntry(
                    root_rel=root_rel,
                    file_rel=file_rel,
                    physical=_file_identity(canonical, file_rel),
                    new_index=new_index,
                )
            )

    blockers: list[MigrationBlocker] = []
    for index, new in enumerate(new_directories):
        for key in sorted(entries_by_key):
            entries = entries_by_key[key]
            mine = [entry for entry in entries if entry.new_index == index]
            if not mine:
                continue
            if len({entry.physical for entry in entries}) < 2:
                continue
            other = next(
                entry for entry in entries if entry.physical != mine[0].physical
            )
            # The blocker path names the file the ambiguous lookup key would
            # select from the newly exposed directory, so each conflicting key
            # remains a distinct, portable blocker.
            blockers.append(
                _blocker(
                    INCLUDE_COLLISION,
                    "a newly exposed include directory resolves the same"
                    " include-relative key to a different file than another"
                    " search directory; header resolution would be ambiguous",
                    _blocker_path(
                        _join_rel(new.rel, mine[0].file_rel),
                        inspection.project_file,
                    ),
                    _evidence(
                        new.scope,
                        new.owner,
                        f"key:{key}|other:{_join_rel(other.root_rel, other.file_rel)}",
                    ),
                )
            )
    return blockers


__all__ = [
    "IncludeScopeClassification",
    "ScopedIncludeAnalysis",
    "analyze_scoped_includes",
    "classify_include_scopes",
]
