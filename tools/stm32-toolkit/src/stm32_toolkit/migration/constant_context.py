"""Bounded integer expressions and object-like macro resolution for source rules.

The ARMCC source rules need a small number of symbolic values: an absolute
placement address, an alignment bound, or a fixed array dimension.  This
module resolves those values without a preprocessor, an ``eval``, or a shell:

* **Expressions** are tokenised and parsed by a closed recursive-descent
  grammar over decimal/hex integer literals (standard unsigned/long
  suffixes), identifiers, parentheses, and a small operator set.  Identifiers
  are expanded *textually* before parsing, so ordinary C token precedence is
  preserved (``A * 4`` with ``A`` = ``1 + 2`` is ``9``, never ``12``).  Every
  intermediate value must stay a non-negative uint32; floats, octal-looking
  literals, casts, ``sizeof``, function-like usage, division by zero, and
  shifts outside 0..31 fail closed.  Type-dependent operators (unary ``~``)
  are rejected rather than guessed.
* **Macros** come only from explicit target defines and from quoted,
  project-contained includes resolved through the including file's directory
  and the reviewed target/scoped include search list.  Nested quoted paths
  (``cfg/memory.h``) are resolved component by component, and every parent
  component is checked for redirects before traversal.  System includes are
  never parsed.
* **Only ordinary object-like definitions** with unambiguous evidence are
  usable.  A used name that is conditionally defined, conditionally included,
  redefined, ``#undef``-ed, or function-like is unsupported even if one
  guessed value would work.  A missing quoted include makes otherwise
  unresolvable symbols report conservative unavailable evidence.
* **Every resolved include contributes a dependency digest** so planning can
  bind the exact bytes (including headers no compiler source lists) and a
  fresh PLAN/APPLY replan detects a changed, added, or shadowing header.

Every traversal, token count, recursion depth, file count, and byte count is
bounded; a bound is a stable resolution failure, never a partial guess.
Resolution is lazy: literal-only rule values never read a header.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path

MAX_UINT32 = 0xFFFFFFFF

MAX_EXPRESSION_CHARS = 4096
MAX_EXPRESSION_TOKENS = 512
MAX_EXPANDED_TOKENS = 4096
MAX_EXPRESSION_DEPTH = 32
MAX_MACRO_DEPTH = 16
MAX_MACRO_EXPANSIONS = 64
MAX_LITERAL_DIGITS = 64

MAX_INCLUDE_DEPTH = 8
MAX_INCLUDE_FILES = 64
MAX_INCLUDE_BYTES = 8 * 1024 * 1024
MAX_INCLUDE_COMPONENTS = 16
MAX_DIRECTORY_ENTRIES = 4096

_INT_RE = re.compile(r"0[xX][0-9a-fA-F]+|\d+")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_DEFINE_RE = re.compile(r"[ \t]+([A-Za-z_][A-Za-z0-9_]*)(\()?")
_UNDEF_RE = re.compile(r"[ \t]+([A-Za-z_][A-Za-z0-9_]*)")
_INCLUDE_RE = re.compile(r'[ \t]*"([^"\r\n]+)"')
_DIRECTIVE_RE = re.compile(r"#[ \t]*([A-Za-z_][A-Za-z0-9_]*)")

_SUFFIXES = frozenset({"", "u", "l", "ul", "lu", "ll", "ull", "llu"})
_CONDITIONALS = frozenset({"if", "ifdef", "ifndef", "elif", "else", "endif"})


class ConstantResolutionError(Exception):
    """A stable, bounded failure to resolve one expression or macro."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


class _SymbolNeeded(Exception):
    """Internal: a literal-only probe encountered an identifier."""


def _fail(code: str, detail: str = "") -> ConstantResolutionError:
    return ConstantResolutionError(code, detail)


# ---------------------------------------------------------------------------
# bounded integer expressions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Token:
    kind: str  # int, ident, op
    value: object


def _tokenize(expression: str) -> list[_Token]:
    if len(expression) > MAX_EXPRESSION_CHARS:
        raise _fail("limit", "expression character budget exceeded")
    tokens: list[_Token] = []
    index = 0
    length = len(expression)
    while index < length:
        char = expression[index]
        if char in " \t\r\n":
            index += 1
            continue
        match = _INT_RE.match(expression, index)
        if match is not None:
            text = match.group(0)
            if len(text) > MAX_LITERAL_DIGITS:
                raise _fail("limit", "integer literal exceeds the digit budget")
            cursor = match.end()
            while cursor < length and expression[cursor].isalpha():
                cursor += 1
            suffix = expression[match.end() : cursor].lower()
            if suffix not in _SUFFIXES:
                raise _fail("non-integer", "unsupported integer literal suffix")
            if text[:2].lower() == "0x":
                try:
                    value = int(text, 16)
                except ValueError:
                    raise _fail("non-integer", "invalid hexadecimal literal")
            else:
                if len(text) > 1 and text[0] == "0":
                    # C would read this as octal; the bounded decimal/hex
                    # subset refuses to reinterpret it as decimal.
                    raise _fail("non-integer", "octal-looking literal is unsupported")
                try:
                    value = int(text, 10)
                except ValueError:
                    raise _fail("non-integer", "invalid decimal literal")
            tokens.append(_Token("int", value))
            index = cursor
        elif char.isalpha() or char == "_":
            match = _IDENT_RE.match(expression, index)
            if match is None:
                raise _fail("syntax")
            tokens.append(_Token("ident", match.group(0)))
            index = match.end()
        else:
            pair = expression[index : index + 2]
            if pair in ("<<", ">>"):
                tokens.append(_Token("op", pair))
                index += 2
            elif char in "+-*/%&|^~()":
                tokens.append(_Token("op", char))
                index += 1
            else:
                raise _fail("syntax", "unsupported expression character")
        if len(tokens) > MAX_EXPRESSION_TOKENS:
            raise _fail("limit", "expression token budget exceeded")
    if not tokens:
        raise _fail("syntax", "empty expression")
    return tokens


def _expand(
    tokens: list[_Token],
    lookup,
    active: set[str],
    budget: list[int],
    depth: int,
) -> list[_Token]:
    """Expand identifiers textually, preserving ordinary C token precedence."""
    if depth > MAX_MACRO_DEPTH:
        raise _fail("limit", "macro expansion depth budget exceeded")
    result: list[_Token] = []
    for token in tokens:
        if token.kind != "ident":
            result.append(token)
        else:
            name = str(token.value)
            if name in active:
                raise _fail("cycle", "macro expansion is cyclic")
            replacement = lookup(name)
            if len(replacement) > MAX_EXPRESSION_CHARS:
                raise _fail("limit", "macro replacement is too long")
            active.add(name)
            try:
                expanded = _expand(
                    _tokenize(replacement), lookup, active, budget, depth + 1
                )
            finally:
                active.discard(name)
            result.extend(expanded)
        budget[0] += 1
        if budget[0] > MAX_EXPANDED_TOKENS:
            raise _fail("limit", "expanded expression token budget exceeded")
    return result


class _Parser:
    """Closed recursive-descent evaluator over expanded tokens."""

    def __init__(self, tokens: list[_Token]) -> None:
        self.tokens = tokens
        self.position = 0
        self.depth = 0
        self.unary_depth = 0

    def _peek(self) -> _Token | None:
        if self.position >= len(self.tokens):
            return None
        return self.tokens[self.position]

    def _op(self, value: str) -> bool:
        token = self._peek()
        if token is not None and token.kind == "op" and token.value == value:
            self.position += 1
            return True
        return False

    @staticmethod
    def _check(value: int) -> int:
        if value < 0:
            raise _fail("nonnegative", "negative value")
        if value > MAX_UINT32:
            raise _fail("overflow", "value exceeds uint32")
        return value

    def _enter(self) -> None:
        self.depth += 1
        if self.depth > MAX_EXPRESSION_DEPTH:
            raise _fail("limit", "expression nesting budget exceeded")

    def _leave(self) -> None:
        self.depth -= 1

    def parse(self) -> int:
        value = self._bitor()
        if self.position != len(self.tokens):
            raise _fail("syntax", "unexpected trailing expression token")
        return value

    def _bitor(self) -> int:
        self._enter()
        try:
            value = self._bitxor()
            while self._op("|"):
                value = self._check(value | self._bitxor())
            return value
        finally:
            self._leave()

    def _bitxor(self) -> int:
        value = self._bitand()
        while self._op("^"):
            value = self._check(value ^ self._bitand())
        return value

    def _bitand(self) -> int:
        value = self._shift()
        while self._op("&"):
            value = self._check(value & self._shift())
        return value

    def _shift(self) -> int:
        value = self._additive()
        while True:
            if self._op("<<"):
                count = self._additive()
                if count > 31:
                    raise _fail("limit", "shift count out of range")
                value = self._check(value << count)
            elif self._op(">>"):
                count = self._additive()
                if count > 31:
                    raise _fail("limit", "shift count out of range")
                value = self._check(value >> count)
            else:
                return value

    def _additive(self) -> int:
        value = self._multiplicative()
        while True:
            if self._op("+"):
                value = self._check(value + self._multiplicative())
            elif self._op("-"):
                value = self._check(value - self._multiplicative())
            else:
                return value

    def _multiplicative(self) -> int:
        value = self._unary()
        while True:
            if self._op("*"):
                value = self._check(value * self._unary())
            elif self._op("/"):
                divisor = self._unary()
                if divisor == 0:
                    raise _fail("syntax", "division by zero")
                value = self._check(value // divisor)
            elif self._op("%"):
                divisor = self._unary()
                if divisor == 0:
                    raise _fail("syntax", "division by zero")
                value = self._check(value % divisor)
            else:
                return value

    def _unary(self) -> int:
        # Unary operators are left-recursive by nature; count them explicitly
        # so a deeply expanded macro replacement is a controlled limit error
        # instead of a Python RecursionError.
        self.unary_depth += 1
        if self.unary_depth > MAX_EXPRESSION_DEPTH:
            self.unary_depth -= 1
            raise _fail("limit", "unary nesting budget exceeded")
        try:
            if self._op("+"):
                return self._unary()
            if self._op("-"):
                value = self._unary()
                if value != 0:
                    raise _fail("nonnegative", "negative value")
                return 0
            if (
                self._peek() is not None
                and self._peek().kind == "op"
                and self._peek().value == "~"
            ):
                raise _fail("unsupported", "type-dependent unary ~ is unsupported")
            return self._primary()
        finally:
            self.unary_depth -= 1

    def _primary(self) -> int:
        token = self._peek()
        if token is None:
            raise _fail("syntax", "unexpected end of expression")
        if token.kind == "int":
            self.position += 1
            return self._check(int(token.value))
        if token.kind == "op" and token.value == "(":
            self.position += 1
            self._enter()
            try:
                value = self._bitor()
            finally:
                self._leave()
            if not self._op(")"):
                raise _fail("syntax", "unbalanced parenthesis")
            return value
        raise _fail("syntax", "unexpected expression token")


def evaluate_integer(expression: str, lookup) -> int:
    """Evaluate a bounded uint32 expression, expanding macros textually."""
    tokens = _tokenize(expression)
    expanded = _expand(tokens, lookup, set(), [0], 0)
    return _Parser(expanded).parse()


# ---------------------------------------------------------------------------
# directive extraction
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Directive:
    keyword: str
    rest: str
    line: int


def _line_continues(text: str, newline: int) -> bool:
    """Whether the physical line ending at ``newline`` is backslash-spliced."""
    if newline > 0 and text[newline - 1] == "\\":
        return True
    return (
        newline > 1
        and text[newline - 1] == "\r"
        and text[newline - 2] == "\\"
    )


def _mask_comments(text: str) -> str:
    """Blank comments only, preserving string/character literal bytes.

    Newlines stay in place so logical line numbers remain meaningful.  A
    ``#`` inside a comment is therefore invisible, while a quoted include
    operand (``"cfg/memory.h"``) survives exactly.  A backslash-spliced
    ``//`` comment owns every continuation line, exactly as C translation
    phase 2 does, so a fake ``#define`` on a spliced line is never a
    directive.
    """
    output: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        pair = text[index : index + 2]
        if pair == "//":
            end = index + 2
            while True:
                newline = text.find("\n", end)
                if newline == -1:
                    end = length
                    break
                if _line_continues(text, newline):
                    end = newline + 1
                    continue
                end = newline
                break
            output.append(
                "".join("\n" if c == "\n" else " " for c in text[index:end])
            )
            index = end
        elif pair == "/*":
            end = text.find("*/", index + 2)
            end = length if end == -1 else end + 2
            output.append("".join("\n" if c == "\n" else " " for c in text[index:end]))
            index = end
        elif char in ('"', "'"):
            quote = char
            cursor = index + 1
            while cursor < length:
                if text[cursor] == "\\" and cursor + 1 < length:
                    cursor += 2
                    continue
                if text[cursor] == quote or text[cursor] == "\n":
                    cursor += 1
                    break
                cursor += 1
            cursor = min(cursor, length)
            output.append(text[index:cursor])
            index = cursor
        else:
            output.append(char)
            index += 1
    return "".join(output)


def _directives(text: str) -> list[_Directive]:
    """Split comment-masked text into logical preprocessor directives."""
    masked = _mask_comments(text)
    physical = masked.split("\n")
    directives: list[_Directive] = []
    index = 0
    while index < len(physical):
        raw = physical[index].rstrip("\r")
        stripped = raw.lstrip()
        if not stripped.startswith("#"):
            index += 1
            continue
        start_line = index + 1
        logical = stripped
        while logical.endswith("\\") and index + 1 < len(physical):
            index += 1
            logical = logical[:-1] + " " + physical[index].rstrip("\r").lstrip()
        match = _DIRECTIVE_RE.match(logical)
        if match is not None:
            directives.append(
                _Directive(match.group(1), logical[match.end() :], start_line)
            )
        index += 1
    return directives


# ---------------------------------------------------------------------------
# macro index
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Definition:
    name: str
    value: str
    function_like: bool
    path: str
    line: int
    conditional: bool


@dataclass
class _MacroIndex:
    root: Path
    source_path: str
    include_paths: tuple[str, ...]
    target_defines: tuple[str, ...]
    source_text: str

    definitions: dict[str, list[_Definition]] = field(default_factory=dict)
    undefs: set[str] = field(default_factory=set)
    system_includes: set[str] = field(default_factory=set)
    unresolved_quoted: bool = False
    dependencies: dict[str, tuple[str, int]] = field(default_factory=dict)
    children: dict[str, set[str]] = field(default_factory=dict)
    failure: ConstantResolutionError | None = None
    loaded: set[str] = field(default_factory=set)
    files: int = 0
    bytes: int = 0
    directory_cache: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    checked_bases: set[str] = field(default_factory=set)

    def build(self) -> None:
        self._add_target_defines()
        self._load(self.source_path, self.source_text, 0, tainted=False)

    # -- target defines ------------------------------------------------------

    def _add_target_defines(self) -> None:
        for raw in self.target_defines:
            text = raw.strip()
            if not text:
                continue
            name, separator, value = text.partition("=")
            name = name.strip()
            function_like = "(" in name
            if function_like:
                name = name.split("(", 1)[0].strip()
            if _IDENT_RE.fullmatch(name) is None:
                continue
            self._add(
                _Definition(
                    name=name,
                    value="" if function_like or not separator else value.strip(),
                    function_like=function_like,
                    path=".uvprojx",
                    line=0,
                    conditional=False,
                )
            )

    def _add(self, definition: _Definition) -> None:
        self.definitions.setdefault(definition.name, []).append(definition)

    # -- include loading -----------------------------------------------------

    def _load(self, rel_path: str, text: str, depth: int, *, tainted: bool) -> None:
        if depth > MAX_INCLUDE_DEPTH:
            raise _fail("limit", "include depth budget exceeded")
        if rel_path in self.loaded:
            if tainted:
                self._taint_file(rel_path)
            return
        self.loaded.add(rel_path)
        self.files += 1
        if self.files > MAX_INCLUDE_FILES:
            raise _fail("limit", "include file budget exceeded")
        self.bytes += len(text.encode("utf-8"))
        if self.bytes > MAX_INCLUDE_BYTES:
            raise _fail("limit", "include byte budget exceeded")

        directives = _directives(text)
        guard = _guard_info(directives)
        guard_indexes: set[int] = set()
        guard_tainted = tainted
        if guard is not None:
            guard_indexes, guard_name = guard
            # A guard name already defined elsewhere means the real
            # preprocessor would skip this body entirely.
            if any(
                definition.path != rel_path
                for definition in self.definitions.get(guard_name, ())
            ):
                guard_tainted = True

        conditional_depth = 0
        for position, directive in enumerate(directives):
            keyword = directive.keyword
            if keyword in _CONDITIONALS:
                if position in guard_indexes:
                    continue
                if keyword in ("if", "ifdef", "ifndef"):
                    conditional_depth += 1
                elif keyword == "endif":
                    conditional_depth = max(0, conditional_depth - 1)
                continue
            conditional = guard_tainted or conditional_depth > 0
            if keyword == "define":
                self._record_define(directive, rel_path, conditional)
            elif keyword == "undef":
                match = _UNDEF_RE.match(directive.rest)
                if match is not None:
                    self.undefs.add(match.group(1))
            elif keyword == "include":
                match = _INCLUDE_RE.match(directive.rest)
                if match is None:
                    system = directive.rest.strip()
                    if system:
                        self.system_includes.add(system[:200])
                    continue
                target = self._resolve_include(rel_path, match.group(1))
                if target is None:
                    self.unresolved_quoted = True
                    continue
                resolved_rel, dependency, body = target
                self.children.setdefault(rel_path, set()).add(resolved_rel)
                if dependency is not None:
                    self.dependencies[resolved_rel] = dependency
                self._load(resolved_rel, body, depth + 1, tainted=conditional)

    def _taint_file(self, rel_path: str, seen: set[str] | None = None) -> None:
        """Mark every definition from ``rel_path`` and its includes conditional."""
        visited = set() if seen is None else seen
        if rel_path in visited:
            return
        visited.add(rel_path)
        for name, definitions in list(self.definitions.items()):
            self.definitions[name] = [
                dataclasses.replace(definition, conditional=True)
                if definition.path == rel_path
                else definition
                for definition in definitions
            ]
        for child in self.children.get(rel_path, ()):
            self._taint_file(child, visited)

    def _record_define(self, directive: _Directive, path: str, conditional: bool) -> None:
        match = _DEFINE_RE.match(directive.rest)
        if match is None:
            return
        name = match.group(1)
        function_like = match.group(2) is not None
        value = "" if function_like else directive.rest[match.end() :].strip()
        self._add(
            _Definition(
                name=name,
                value=value,
                function_like=function_like,
                path=path,
                line=directive.line,
                conditional=conditional,
            )
        )

    # -- include resolution --------------------------------------------------

    def _host(self, rel: str) -> Path:
        return self.root if rel == "." else self.root.joinpath(*rel.split("/"))

    @staticmethod
    def _portable(name: str) -> bool:
        if not name or "\\" in name or "\x00" in name:
            return False
        if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
            return False
        return all(component not in (".", "..") for component in name.split("/"))

    def _directory(self, rel: str) -> dict[str, list[str]] | None:
        if rel in self.directory_cache:
            return self.directory_cache[rel]
        host = self._host(rel)
        try:
            info = os.lstat(host)
        except (FileNotFoundError, NotADirectoryError):
            return None
        except OSError:
            raise _fail("unreadable", "include directory is unreadable")
        if _is_redirect(info):
            raise _fail("redirect", "include directory redirects")
        if not stat.S_ISDIR(info.st_mode):
            return None
        mapping: dict[str, list[str]] = {}
        count = 0
        try:
            with os.scandir(host) as iterator:
                for entry in iterator:
                    count += 1
                    if count > MAX_DIRECTORY_ENTRIES:
                        raise _fail("limit", "directory listing budget exceeded")
                    mapping.setdefault(entry.name.casefold(), []).append(entry.name)
        except OSError:
            raise _fail("unreadable", "include directory is unreadable")
        self.directory_cache[rel] = mapping
        return mapping

    def _resolve_include(
        self, including: str, name: str
    ) -> tuple[str, tuple[str, int] | None, str] | None:
        if not self._portable(name):
            raise _fail("escape", "include path is not contained")
        components = name.split("/")
        if len(components) > MAX_INCLUDE_COMPONENTS:
            raise _fail("limit", "include path component budget exceeded")
        parent = including.rsplit("/", 1)[0] if "/" in including else ""
        search: list[str] = [parent or "."]
        for entry in self.include_paths:
            if entry == "." or self._portable(entry):
                search.append(entry)
        seen: set[str] = set()
        for base in search:
            if base in seen:
                continue
            seen.add(base)
            resolved = self._try_base(base, components)
            if resolved is not None:
                return resolved
        return None

    def _check_search_base(self, base: str) -> bool:
        """Validate every component of one search base from the project root.

        A redirect anywhere between the root and the search base (not only in
        the appended include components) fails closed before traversal.
        """
        if base == ".":
            return True
        if base in self.checked_bases:
            return True
        current = ""
        for component in base.split("/"):
            current = component if not current else f"{current}/{component}"
            host = self._host(current)
            try:
                info = os.lstat(host)
            except (FileNotFoundError, NotADirectoryError):
                return False
            except OSError:
                raise _fail("unreadable", "include search base is unreadable")
            if _is_redirect(info):
                raise _fail("redirect", "include search base redirects")
            if not stat.S_ISDIR(info.st_mode):
                return False
        self.checked_bases.add(base)
        return True

    def _try_base(
        self, base: str, components: list[str]
    ) -> tuple[str, tuple[str, int] | None, str] | None:
        if not self._check_search_base(base):
            return None
        current = base
        # Every parent component is inspected for redirects before traversal.
        for component in components[:-1]:
            current = component if current == "." else f"{current}/{component}"
            host = self._host(current)
            try:
                info = os.lstat(host)
            except (FileNotFoundError, NotADirectoryError):
                return None
            except OSError:
                raise _fail("unreadable", "include path is unreadable")
            if _is_redirect(info):
                raise _fail("redirect", "include parent redirects")
            if not stat.S_ISDIR(info.st_mode):
                return None
        mapping = self._directory(current)
        if mapping is None:
            return None
        final = components[-1]
        matches = mapping.get(final.casefold(), [])
        if len(matches) > 1:
            raise _fail("ambiguous", "include name matches multiple files")
        if not matches:
            return None
        rel = matches[0] if current == "." else f"{current}/{matches[0]}"
        host = self._host(rel)
        try:
            info = os.lstat(host)
        except OSError:
            raise _fail("unreadable", "include file is unreadable")
        if _is_redirect(info):
            raise _fail("redirect", "include file redirects")
        if not stat.S_ISREG(info.st_mode):
            raise _fail("unreadable", "include path is not a regular file")
        if info.st_size > MAX_INCLUDE_BYTES:
            raise _fail("limit", "include file exceeds the byte budget")
        try:
            resolved = host.resolve(strict=True)
            resolved.relative_to(self.root)
        except (OSError, RuntimeError, ValueError):
            raise _fail("escape", "include path escapes the project root")
        try:
            with host.open("rb") as handle:
                data = handle.read(info.st_size + 1)
        except OSError:
            raise _fail("unreadable", "include file is unreadable")
        if len(data) != info.st_size:
            raise _fail("unreadable", "include file changed while reading")
        try:
            body = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise _fail("unreadable", "include file is not UTF-8")
        return rel, (hashlib.sha256(data).hexdigest(), len(data)), body

    # -- resolution ----------------------------------------------------------

    def lookup(self, name: str) -> str:
        """Return the exact replacement text for one used object-like macro."""
        if self.failure is not None:
            raise self.failure
        if name in self.undefs:
            raise _fail("undef", "macro is undefined in the include chain")
        definitions = self.definitions.get(name)
        if not definitions:
            if self.unresolved_quoted or self.system_includes:
                raise _fail("unavailable", "macro has no resolvable quoted definition")
            raise _fail("undefined", "macro is not defined")
        if len(definitions) > 1:
            raise _fail("redefined", "macro is defined more than once")
        definition = definitions[0]
        if definition.conditional:
            raise _fail("conditional", "macro definition is conditional")
        if definition.function_like:
            raise _fail("function-like", "macro is function-like")
        if self.unresolved_quoted:
            # A missing quoted include could have changed this definition;
            # never guess the absence of an effect.
            raise _fail(
                "unavailable",
                "a quoted include in the chain could not be resolved",
            )
        if not definition.value:
            raise _fail("non-integer", "macro has no integer replacement")
        return definition.value


def _is_redirect(info: os.stat_result) -> bool:
    if stat.S_ISLNK(info.st_mode):
        return True
    return bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _guard_info(directives: list[_Directive]) -> tuple[set[int], str] | None:
    """Recognise only a structural ordinary include guard.

    The guard must be the first directive, immediately followed by an empty
    object-like ``#define`` of the same name, closed by the file's last
    directive, with no other conditional anywhere.  Anything else is a real
    conditional and keeps per-definition conditional provenance.
    """
    if len(directives) < 3:
        return None
    first = directives[0]
    if first.keyword != "ifndef":
        return None
    match = _IDENT_RE.match(first.rest.strip())
    if match is None:
        return None
    name = match.group(0)
    second = directives[1]
    if second.keyword != "define":
        return None
    defined = _DEFINE_RE.match(second.rest)
    if defined is None or defined.group(1) != name:
        return None
    if defined.group(2) is not None or second.rest[defined.end() :].strip():
        return None
    if directives[-1].keyword != "endif":
        return None
    for directive in directives[1:-1]:
        if directive.keyword in _CONDITIONALS:
            return None
    return {0, len(directives) - 1}, name


# ---------------------------------------------------------------------------
# per-source public surface
# ---------------------------------------------------------------------------


def _require_symbol(name: str) -> str:
    raise _SymbolNeeded(name)


class SourceSymbols:
    """Lazy, per-source symbolic resolver used by the token-aware rules.

    The macro index is built only when an expression really contains an
    identifier, so a literal-only placement/alignment never reads a header,
    never contributes a dependency, and cannot regress on an unrelated
    include.
    """

    def __init__(
        self,
        root: Path,
        source_path: str,
        source_text: str,
        include_paths: tuple[str, ...],
        defines: tuple[str, ...],
    ) -> None:
        self._index = _MacroIndex(
            root=root,
            source_path=source_path,
            include_paths=include_paths,
            target_defines=defines,
            source_text=source_text,
        )
        self._built = False

    def _ensure(self) -> _MacroIndex:
        if not self._built:
            self._built = True
            try:
                self._index.build()
            except ConstantResolutionError as error:
                self._index.failure = error
            except OSError:
                self._index.failure = _fail("unreadable", "source dependency read failed")
        return self._index

    def evaluate(self, expression: str) -> tuple[int | None, str | None]:
        try:
            return evaluate_integer(expression, _require_symbol), None
        except _SymbolNeeded:
            pass
        except ConstantResolutionError as error:
            return None, error.code
        index = self._ensure()
        try:
            return evaluate_integer(expression, index.lookup), None
        except ConstantResolutionError as error:
            return None, error.code

    def dependencies(self) -> tuple[tuple[str, str, int], ...]:
        if not self._built:
            return ()
        return tuple(
            (path, digest, size)
            for path, (digest, size) in sorted(self._index.dependencies.items())
        )


class SymbolSource:
    """Factory handed to ``rules.scan_sources`` for one planning pass."""

    def __init__(
        self,
        root: Path,
        include_paths: tuple[str, ...],
        defines: tuple[str, ...],
    ) -> None:
        self.root = root
        self.include_paths = include_paths
        self.defines = defines
        self._sources: list[SourceSymbols] = []

    def for_source(self, path: str, text: str) -> SourceSymbols:
        symbols = SourceSymbols(
            self.root, path, text, self.include_paths, self.defines
        )
        self._sources.append(symbols)
        return symbols

    def dependencies(self) -> tuple[tuple[str, str, int], ...]:
        merged: dict[str, tuple[str, int]] = {}
        for symbols in self._sources:
            for path, digest, size in symbols.dependencies():
                merged.setdefault(path, (digest, size))
        return tuple(
            (path, digest, size) for path, (digest, size) in sorted(merged.items())
        )


__all__ = [
    "ConstantResolutionError",
    "MAX_UINT32",
    "SourceSymbols",
    "SymbolSource",
    "evaluate_integer",
]
