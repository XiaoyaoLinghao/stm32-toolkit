"""The parser-only GNU asm compatibility policy must preserve source offsets."""

from __future__ import annotations

import pytest

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
