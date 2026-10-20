"""Fixed-width, parser-only compatibility for one GNU ARM asm clobber.

Only an ordinary string token in a proved extended-asm clobber entry is
eligible.  This never changes source files or code passed to GNU GCC.
"""

from __future__ import annotations

from collections.abc import Iterator


POLICY_VERSION = "gnu-asm-vfpcc-clobber-v1"

_ASM = frozenset((b"asm", b"__asm", b"__asm__"))
_QUALIFIERS = {
    b"volatile": "volatile", b"__volatile": "volatile", b"__volatile__": "volatile",
    b"inline": "inline", b"__inline": "inline", b"__inline__": "inline",
    b"goto": "goto", b"__goto": "goto", b"__goto__": "goto",
}
_PREFIXES = frozenset((b"L", b"u", b"U", b"u8"))
_OPEN = {"(": ")", "[": "]", "{": "}"}
_CLOSE = frozenset(_OPEN.values())
_OLD = b'"vfpcc"'
_NEW = b'"cc"   '


class _LexError(Exception):
    pass


def _identifier_part(byte: int) -> bool:
    return 65 <= byte <= 90 or 97 <= byte <= 122 or 48 <= byte <= 57 or byte == 95


def _quoted_end(data: bytes, start: int) -> int:
    quote = data[start]
    index = start + 1
    while index < len(data):
        byte = data[index]
        if byte == quote:
            return index + 1
        if byte == 92:  # escape, including an escaped physical newline
            index += 1
            if index < len(data) and data[index] == 13 and data[index:index + 2] == b"\r\n":
                index += 2
            elif index < len(data):
                index += 1
            else:
                raise _LexError
            continue
        if byte in (10, 13):
            raise _LexError
        index += 1
    raise _LexError


def _tokens(data: bytes, start: int = 0, line_start: bool = True) -> Iterator[tuple[str, int, int]]:
    """Yield significant C tokens; directives and comments provide no delimiters."""
    index = start
    length = len(data)
    while index < length:
        byte = data[index]
        if byte in (32, 9, 11, 12, 13):
            index += 1
            continue
        if byte == 10:
            line_start = True
            index += 1
            continue
        if byte == 92 and data[index + 1:index + 2] in (b"\n", b"\r"):
            index += 2
            if data[index - 1:index] == b"\r" and data[index:index + 1] == b"\n":
                index += 1
            continue
        if byte == 35 and line_start:  # preprocessor line marker/directive
            while index < length:
                end = data.find(b"\n", index)
                if end < 0:
                    return
                continued = end > index and data[end - 1] == 92
                index = end + 1
                if not continued:
                    break
            line_start = True
            continue
        if data[index:index + 2] == b"//":
            while True:
                end = data.find(b"\n", index + 2)
                if end < 0:
                    return
                continued = end > index and data[end - 1] == 92
                index = end + 1
                if not continued:
                    break
            line_start = True
            continue
        if data[index:index + 2] == b"/*":
            end = data.find(b"*/", index + 2)
            if end < 0:
                raise _LexError
            line_start = line_start or data.rfind(b"\n", index, end + 2) >= 0
            index = end + 2
            continue
        line_start = False
        token_start = index
        if _identifier_part(byte) and not 48 <= byte <= 57:
            index += 1
            while index < length and _identifier_part(data[index]):
                index += 1
            if data[token_start:index] in _PREFIXES and data[index:index + 1] in (b'"', b"'"):
                index = _quoted_end(data, index)
                yield "prefixed_string", token_start, index
            else:
                yield "identifier", token_start, index
        elif byte in (34, 39):
            index = _quoted_end(data, index)
            yield ("string" if byte == 34 else "character"), token_start, index
        else:
            index += 1
            yield chr(byte), token_start, index


def _asm_spans(data: bytes, after_keyword: int) -> tuple[list[tuple[int, int]], bool]:
    tokens = iter(_tokens(data, after_keyword, False))
    qualifiers: set[str] = set()
    token = next(tokens, None)
    while token is not None and token[0] == "identifier" and data[token[1]:token[2]] in _QUALIFIERS:
        qualifier = _QUALIFIERS[data[token[1]:token[2]]]
        if qualifier in qualifiers:
            return [], False
        qualifiers.add(qualifier)
        token = next(tokens, None)
    if token is None or token[0] != "(":
        return [], False

    expected = [")"]
    sections: list[list[tuple[str, int, int]]] = [[]]
    for token in tokens:
        kind = token[0]
        if kind in _OPEN:
            expected.append(_OPEN[kind])
        elif kind in _CLOSE:
            if kind != expected[-1]:
                return [], True
            expected.pop()
            if not expected:
                break
        elif kind == ":" and len(expected) == 1:
            sections.append([])
            if len(sections) > 5:
                return [], True
            continue
        sections[-1].append(token)
    else:
        return [], True

    # GNU extended asm starts with a (possibly concatenated) string template.
    # The fourth section is the comma-separated clobber list.  A fourth colon
    # begins asm-goto labels and ends clobber eligibility.
    if (len(sections) not in (4, 5) or not sections[0]
            or any(token[0] != "string" for token in sections[0])):
        return [], False
    clobbers = sections[3]
    if not clobbers or len(clobbers) % 2 == 0:
        return [], False
    if any(token[0] != ("string" if index % 2 == 0 else ",")
           for index, token in enumerate(clobbers)):
        return [], False
    return [(start, end) for kind, start, end in clobbers[::2]
            if data[start:end] == _OLD], False


def normalize_gnu_asm_clobbers(preprocessed: bytes) -> bytes:
    """Replace only proved standalone ``"vfpcc"`` clobber tokens in parser input."""
    spans: list[tuple[int, int]] = []
    try:
        for kind, start, end in _tokens(preprocessed):
            if kind == "identifier" and preprocessed[start:end] in _ASM:
                additions, malformed = _asm_spans(preprocessed, end)
                if malformed:
                    return preprocessed
                spans.extend(additions)
    except _LexError:
        return preprocessed
    if not spans:
        return preprocessed
    output = bytearray(preprocessed)
    for start, end in spans:
        output[start:end] = _NEW
    return bytes(output)
