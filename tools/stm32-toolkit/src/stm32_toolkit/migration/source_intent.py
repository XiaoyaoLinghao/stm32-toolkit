"""Bounded, immutable WFI source-intent choices for ARMCC-to-GCC migration.

A reviewed choice names one exact portable project-relative C source and one
exact ASCII C identifier.  Only a plain unconditional file-scope
zero-argument ``__asm void name(void)``/``name()`` definition whose body is
WFI alone can use the choice; Toolkit rewrites exactly that definition into
ordinary non-naked C executing ``__asm volatile ("wfi" ::: "memory");`` and
returning normally.  This records requested source behaviour, not binary
equivalence, and never requires a Keil disassembly/AXF baseline.

The module performs no filesystem I/O.  Transport validation rejects unknown
types, escaping or non-C paths, non-ASCII/overlong identifiers, excessive
counts, and duplicate selections; the token-aware scanner additionally rejects
unused and lexically ambiguous selections.
"""

from __future__ import annotations

import re

from stm32_toolkit.migration.model import (
    MigrationPlanError,
    WfiReturn,
    portable_path_error,
)

#: Hard bound on reviewed selections in one request.
MAX_WFI_RETURNS = 128
#: Hard bound on one ASCII C identifier in characters.
MAX_WFI_FUNCTION_LENGTH = 128
#: The exact GNU extended-asm statement the selected wrapper becomes.
WFI_NORMAL_BODY = '__asm volatile ("wfi" ::: "memory");'
#: Rule ID carried by the reviewed patch and its preview/report evidence.
WFI_RETURN_RULE_ID = "ARMCC_WFI_RETURN_INTENT"

_WFI_FUNCTION_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
#: Exact keys accepted in one public/raw ``wfiReturns`` object.
_WFI_OPTION_KEYS = frozenset({"path", "function"})


def _invalid(
    rule: str, message: str, **details: object
) -> MigrationPlanError:
    payload: dict[str, object] = {"field": "wfiReturns", "rule": rule}
    for key, value in details.items():
        payload[key] = value
    return MigrationPlanError("WFI_RETURNS_INVALID", message, payload)


def normalize_wfi_returns(value: object) -> tuple[WfiReturn, ...]:
    """Validate and deterministically order one reviewed selection request.

    ``None`` keeps the historical no-choice behavior.  Only an immutable
    ``tuple`` of :class:`WfiReturn` entries is accepted; mappings, lists,
    strings, and unvalidated transport values are refused rather than
    guessed.  Paths are contained portable project-relative ``.c`` sources and
    identifiers are ASCII C identifiers of at most 128 characters.  The
    returned tuple is sorted by ``(path, function)`` and contains no
    duplicates.
    """
    if value is None:
        return ()
    if type(value) is not tuple:
        raise _invalid(
            "type",
            "wfiReturns must be an immutable WfiReturn tuple",
        )
    if len(value) > MAX_WFI_RETURNS:
        raise _invalid(
            "limit",
            "wfiReturns exceeds the selection limit",
            limit=MAX_WFI_RETURNS,
        )
    seen: set[tuple[str, str]] = set()
    selections: list[WfiReturn] = []
    for item in value:
        if type(item) is not WfiReturn:
            raise _invalid(
                "type",
                "each wfiReturns entry must be a WfiReturn",
            )
        path = item.path
        function = item.function
        if (
            not isinstance(path, str)
            or portable_path_error(path) is not None
            or "\\" in path
        ):
            raise _invalid(
                "path",
                "wfiReturns path must be a portable project-relative path",
                path=path if isinstance(path, str) else "",
            )
        if not path.endswith(".c"):
            raise _invalid(
                "path",
                "wfiReturns path must name a C source",
                path=path,
            )
        if (
            not isinstance(function, str)
            or _WFI_FUNCTION_RE.fullmatch(function) is None
            or len(function) > MAX_WFI_FUNCTION_LENGTH
        ):
            raise _invalid(
                "function",
                "wfiReturns function must be an ASCII C identifier of at most"
                " 128 characters",
                function=function if isinstance(function, str) else "",
            )
        key = (path, function)
        if key in seen:
            raise _invalid(
                "duplicate",
                "wfiReturns contains a duplicate selection",
                path=path,
                function=function,
            )
        seen.add(key)
        selections.append(item)
    return tuple(sorted(selections, key=lambda item: (item.path, item.function)))


def normalize_wfi_return_options(value: object) -> tuple[WfiReturn, ...]:
    """Validate one public (CLI/MCP) ``wfiReturns`` request.

    ``None`` keeps the historical no-choice behavior.  The bounded transport
    value is a real ``list`` of objects with exactly ``path`` and ``function``
    string keys; a tuple, JSON string, mapping, or object with unknown/missing
    keys is refused rather than coerced.  Each object becomes one immutable
    :class:`WfiReturn` and the exact tuple then goes through
    :func:`normalize_wfi_returns`, so path, identifier, duplicate, count and
    deterministic-order rules stay identical to the internal contract.
    """
    if value is None:
        return ()
    if type(value) is not list:
        raise _invalid(
            "type",
            "wfiReturns must be a list of {path, function} objects",
        )
    if len(value) > MAX_WFI_RETURNS:
        raise _invalid(
            "limit",
            "wfiReturns exceeds the selection limit",
            limit=MAX_WFI_RETURNS,
        )
    selections: list[WfiReturn] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise _invalid(
                "type",
                "each wfiReturns entry must be an object",
                index=index,
            )
        keys = set(item)
        if keys - _WFI_OPTION_KEYS:
            # Never echo an arbitrary key: only the bounded rule is stable.
            raise _invalid(
                "unknownKey",
                "wfiReturns objects accept only path and function",
                index=index,
            )
        missing = _WFI_OPTION_KEYS - keys
        if missing:
            raise _invalid(
                "required",
                "each wfiReturns object requires path and function",
                index=index,
                missing=sorted(missing),
            )
        path = item["path"]
        function = item["function"]
        if not isinstance(path, str):
            raise _invalid(
                "type",
                "wfiReturns path must be a string",
                index=index,
            )
        if not isinstance(function, str):
            raise _invalid(
                "type",
                "wfiReturns function must be a string",
                index=index,
            )
        selections.append(WfiReturn(path, function))
    return normalize_wfi_returns(tuple(selections))


__all__ = [
    "MAX_WFI_FUNCTION_LENGTH",
    "MAX_WFI_RETURNS",
    "WFI_NORMAL_BODY",
    "WFI_RETURN_RULE_ID",
    "normalize_wfi_returns",
    "normalize_wfi_return_options",
]
