"""Fixed-width, parser-only compatibility for one GNU ARM asm clobber.

Only an ordinary string token in a proved extended-asm clobber entry is
eligible.  This never changes source files or code passed to GNU GCC.
"""

from __future__ import annotations

from collections.abc import Iterator


POLICY_VERSION = "gnu-asm-vfpcc-clobber-v2"

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


type _Token = tuple[str, int, int]


def _tokens(data: bytes) -> Iterator[_Token]:
    """Yield significant C tokens; directives and comments provide no delimiters."""
    index = 0
    length = len(data)
    line_start = True
    while index < length:
        byte = data[index]
        if byte in (32, 9, 11, 12, 13):
            index += 1
            continue
        if byte == 10:
            line_start = True
            index += 1
            continue
        if byte == 35 and line_start:  # preprocessor line marker/directive
            end = data.find(b"\n", index)
            if end < 0:
                return
            index = end + 1
            line_start = True
            continue
        if data[index:index + 2] == b"//":
            end = data.find(b"\n", index + 2)
            if end < 0:
                return
            index = end + 1
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


def _asm_spans(data: bytes, tokens: Iterator[_Token]) -> tuple[list[tuple[int, int]], bool, _Token | None]:
    """Consume one candidate from the shared token stream without rescanning it."""
    qualifiers: set[str] = set()
    token = next(tokens, None)
    while token is not None and token[0] == "identifier" and data[token[1]:token[2]] in _QUALIFIERS:
        qualifier = _QUALIFIERS[data[token[1]:token[2]]]
        if qualifier in qualifiers:
            return [], False, None
        qualifiers.add(qualifier)
        token = next(tokens, None)
    if token is None or token[0] != "(":
        return [], False, token

    expected = [")"]
    section = 0
    template_count = 0
    template_valid = True
    clobber_count = 0
    clobber_valid = True
    spans: list[tuple[int, int]] = []
    nested_asm = False
    for token in tokens:
        kind, start, end = token
        if kind in _OPEN:
            expected.append(_OPEN[kind])
        elif kind in _CLOSE:
            if kind != expected[-1]:
                return [], True, None
            expected.pop()
            if not expected:
                break
        elif kind == ":" and len(expected) == 1:
            section += 1
            if section > 4:
                return [], True, None
            continue
        if kind == "identifier" and data[start:end] in _ASM:
            nested_asm = True
        if section == 0:
            template_count += 1
            template_valid = template_valid and kind == "string"
        elif section == 3:
            clobber_valid = clobber_valid and kind == ("string" if clobber_count % 2 == 0 else ",")
            clobber_count += 1
            if kind == "string" and data[start:end] == _OLD:
                spans.append((start, end))
    else:
        return [], True, None

    # GNU extended asm starts with a (possibly concatenated) string template.
    # The fourth section is the comma-separated clobber list.  A fourth colon
    # begins asm-goto labels and ends clobber eligibility.
    if (nested_asm or section not in (3, 4) or not template_count or not template_valid
            or not clobber_count or clobber_count % 2 == 0 or not clobber_valid):
        return [], False, None
    return spans, False, None


def normalize_gnu_asm_clobbers(preprocessed: bytes) -> bytes:
    """Replace only proved standalone ``"vfpcc"`` clobber tokens in parser input."""
    # Physical line splicing changes token boundaries before C lexing.  GCC -E
    # normally removes it; retaining any splice makes this input unproved.
    if b"\\\n" in preprocessed or b"\\\r" in preprocessed:
        return preprocessed
    spans: list[tuple[int, int]] = []
    try:
        tokens = iter(_tokens(preprocessed))
        pending: _Token | None = None
        while True:
            token = pending if pending is not None else next(tokens, None)
            pending = None
            if token is None:
                break
            kind, start, end = token
            if kind == "identifier" and preprocessed[start:end] in _ASM:
                additions, malformed, pending = _asm_spans(preprocessed, tokens)
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
