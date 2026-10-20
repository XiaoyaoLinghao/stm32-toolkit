"""The parser-only GNU asm compatibility policy must preserve source offsets."""

from __future__ import annotations

import pytest

from stm32_toolkit.debug import source_asm_compat
from stm32_toolkit.debug.source_asm_compat import normalize_gnu_asm_clobbers


@pytest.mark.parametrize("keyword", [b"asm", b"__asm", b"__asm__"])
def test_exact_extended_asm_clobber_keeps_every_other_byte(keyword: bytes) -> None:
    original = (b'# 20 "Src/main.c" 1\r\n'
                b'const char *ordinary = "vfpcc"; /* "vfpcc" */\r\n'
                + keyword + b' volatile ("vfpcc" : "=r"(out) : "r"(in) : "memory", "vfpcc");\r\n'
                + keyword + b' goto ("b %l0" : : "r"(in) : "vfpcc" : fail);\n')
    expected = original.replace(b': "memory", "vfpcc"', b': "memory", "cc"   ')
    expected = expected.replace(b': "vfpcc" : fail', b': "cc"    : fail')
    actual = normalize_gnu_asm_clobbers(original)
    assert actual == expected
    assert len(actual) == len(original)
    assert actual.count(b'\n') == original.count(b'\n')


@pytest.mark.parametrize("body", [
    b'asm("vfpcc");',
    b'asm volatile ("x" : "vfpcc"(out) : "r"(in) : "memory");',
    b'asm volatile ("x" : : "vfpcc"(in) : "memory");',
    b'asm goto ("x" : : : "memory" : "vfpcc");',
    b'asm volatile ("x" : : : L"vfpcc");',
    b'asm volatile ("x" : : : u8"vfpcc");',
    b'asm volatile ("x" : : : "vfpcc" "memory");',
    b'asm volatile ("x" : : : "memory" "vfpcc");',
    b'asm volatile ("x" : : : "vfpcc" + "memory");',
    b'asm volatile ("x" : : : "vfpcc\\\" ");',
    b'asm volatile ("x" : : : "vfpcc" [invalid]);',
    b'asm bogus ("x" : : : "vfpcc");',
    b'int __asm_suffix = 1; const char *s = "vfpcc";',
    b'// asm volatile ("x" : : : "vfpcc")\n',
    b'#define X asm volatile ("x" : : : "vfpcc")\n',
    b'asm volatile ("x" : : : "other");',
])
def test_non_clobber_or_unproved_tokens_are_untouched(body: bytes) -> None:
    assert normalize_gnu_asm_clobbers(body) == body


def test_nested_operand_colons_and_comments_do_not_move_clobber_boundary() -> None:
    original = (b'asm volatile ("x" : "=r"(out) : "r"((flag ? left : right)), '
                b'"r"(arr[index ? 1 : 0]) /* : "vfpcc" */ : "vfpcc", "memory");')
    expected = original.replace(b': "vfpcc", "memory"', b': "cc"   , "memory"')
    assert normalize_gnu_asm_clobbers(original) == expected


def test_unterminated_or_unbalanced_asm_cannot_transform() -> None:
    for content in (b'asm volatile ("x" : : : "vfpcc";',
                    b'asm volatile ("x" : : : "vfpcc" /*',
                    b'asm volatile ("x" : : : "vfpcc" ]);'):
        assert normalize_gnu_asm_clobbers(content) == content


@pytest.mark.parametrize("content", [
    b'//\\\r\nasm volatile ("x" : : : "vfpcc");\r\n',
    b'#define X \\\r\nasm volatile ("x" : : : "vfpcc");\r\n',
    b'asm\\\nvolatile ("x" : : : "vfpcc");\n',
    b'asm\\\rvolatile ("x" : : : "vfpcc");\r',
    b'asm volatile ("x" : : : "vfpcc");\\\n',
])
def test_raw_physical_line_splice_fails_closed_for_entire_input(content: bytes) -> None:
    assert normalize_gnu_asm_clobbers(content) == content


def test_nested_asm_uses_one_nonoverlapping_token_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    nested = b'asm(' * 1000 + b'"x" : : : "vfpcc"' + b')' * 1000
    standalone = b'; asm volatile ("x" : : : "vfpcc");'
    content = nested + standalone
    expected = nested + standalone.replace(b'"vfpcc"', b'"cc"   ')
    original_tokens = source_asm_compat._tokens
    calls = 0
    yielded = 0

    def counted_tokens(data: bytes, *args, **kwargs):
        nonlocal calls, yielded
        calls += 1
        for token in original_tokens(data, *args, **kwargs):
            yielded += 1
            yield token

    monkeypatch.setattr(source_asm_compat, "_tokens", counted_tokens)
    assert normalize_gnu_asm_clobbers(content) == expected
    assert calls == 1
    assert yielded <= len(content)
