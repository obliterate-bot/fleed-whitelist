from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Iterable


class TokenKind(str, Enum):
    IDENT = "ident"
    KEYWORD = "keyword"
    NUMBER = "number"
    STRING = "string"
    INTERP_STRING = "interp_string"
    SYMBOL = "symbol"
    COMMENT = "comment"
    WHITESPACE = "whitespace"
    EOF = "eof"


KEYWORDS = {
    "and", "break", "continue", "do", "else", "elseif", "end", "export",
    "false", "for", "function", "if", "in", "local", "nil", "not", "or",
    "repeat", "return", "then", "true", "type", "until", "while", "declare",
}

# Longest first.
SYMBOLS = (
    "...", "..=", "//=" , "<<=", ">>=", "::", "->", "+=", "-=", "*=", "/=", "%=", "^=",
    "==", "~=", "<=", ">=", "//", "<<", ">>", "..", "&&", "||",
    "+", "-", "*", "/", "%", "^", "#", "=", "<", ">", "(", ")", "{", "}", "[", "]",
    ";", ":", ",", ".", "&", "|", "~", "?", "@",
)

_NUMBER_RE = re.compile(
    r"(?:"
    r"0[xX][0-9a-fA-F_]+(?:\.(?!\.)[0-9a-fA-F_]*)?(?:[pP][+-]?[0-9_]+)?"
    r"|0[bB][01_]+"
    r"|(?:[0-9][0-9_]*(?:\.(?!\.)[0-9_]*)?|\.[0-9][0-9_]*)(?:[eE][+-]?[0-9_]+)?"
    r")"
)


@dataclass(slots=True)
class Token:
    kind: TokenKind
    text: str
    start: int
    end: int
    line: int
    column: int
    index: int = -1

    @property
    def significant(self) -> bool:
        return self.kind not in {TokenKind.WHITESPACE, TokenKind.COMMENT, TokenKind.EOF}


class LexError(ValueError):
    pass


def _long_bracket_level(source: str, pos: int) -> int | None:
    if pos >= len(source) or source[pos] != "[":
        return None
    i = pos + 1
    while i < len(source) and source[i] == "=":
        i += 1
    if i < len(source) and source[i] == "[":
        return i - pos - 1
    return None


def _consume_long_bracket(source: str, pos: int, level: int) -> int:
    close = "]" + ("=" * level) + "]"
    body_start = pos + level + 2
    idx = source.find(close, body_start)
    if idx < 0:
        raise LexError(f"unterminated long bracket at offset {pos}")
    return idx + len(close)


def _advance_position(text: str, line: int, column: int) -> tuple[int, int]:
    newlines = text.count("\n")
    if newlines == 0:
        return line, column + len(text)
    return line + newlines, len(text) - text.rfind("\n")


def lex(source: str) -> list[Token]:
    tokens: list[Token] = []
    i = 0
    line = 1
    column = 1

    def emit(kind: TokenKind, start: int, end: int, start_line: int, start_column: int) -> None:
        tokens.append(Token(kind, source[start:end], start, end, start_line, start_column, len(tokens)))

    while i < len(source):
        start = i
        start_line = line
        start_column = column
        ch = source[i]

        if ch.isspace():
            i += 1
            while i < len(source) and source[i].isspace():
                i += 1
            text = source[start:i]
            emit(TokenKind.WHITESPACE, start, i, start_line, start_column)
            line, column = _advance_position(text, line, column)
            continue

        if source.startswith("--", i):
            i += 2
            level = _long_bracket_level(source, i)
            if level is not None:
                i = _consume_long_bracket(source, i, level)
            else:
                while i < len(source) and source[i] not in "\r\n":
                    i += 1
            text = source[start:i]
            emit(TokenKind.COMMENT, start, i, start_line, start_column)
            line, column = _advance_position(text, line, column)
            continue

        if ch in "'\"":
            quote = ch
            i += 1
            escaped = False
            while i < len(source):
                cur = source[i]
                if escaped:
                    escaped = False
                    i += 1
                    continue
                if cur == "\\":
                    escaped = True
                    i += 1
                    continue
                if cur == quote:
                    i += 1
                    break
                if cur in "\r\n":
                    raise LexError(f"newline in quoted string at {start_line}:{start_column}")
                i += 1
            else:
                raise LexError(f"unterminated quoted string at {start_line}:{start_column}")
            text = source[start:i]
            emit(TokenKind.STRING, start, i, start_line, start_column)
            line, column = _advance_position(text, line, column)
            continue

        if ch == "`":
            # Interpolated strings are kept as one token. A later preservation pass
            # protects local names referenced inside interpolation expressions.
            i += 1
            escaped = False
            brace_depth = 0
            quote_stack: list[str] = []
            while i < len(source):
                cur = source[i]
                if escaped:
                    escaped = False
                    i += 1
                    continue
                if cur == "\\":
                    escaped = True
                    i += 1
                    continue
                if quote_stack:
                    q = quote_stack[-1]
                    if cur == q:
                        quote_stack.pop()
                    i += 1
                    continue
                if brace_depth and cur in "'\"":
                    quote_stack.append(cur)
                    i += 1
                    continue
                if cur == "{":
                    brace_depth += 1
                    i += 1
                    continue
                if cur == "}" and brace_depth:
                    brace_depth -= 1
                    i += 1
                    continue
                if cur == "`" and brace_depth == 0:
                    i += 1
                    break
                i += 1
            else:
                raise LexError(f"unterminated interpolated string at {start_line}:{start_column}")
            text = source[start:i]
            emit(TokenKind.INTERP_STRING, start, i, start_line, start_column)
            line, column = _advance_position(text, line, column)
            continue

        level = _long_bracket_level(source, i)
        if level is not None:
            i = _consume_long_bracket(source, i, level)
            text = source[start:i]
            emit(TokenKind.STRING, start, i, start_line, start_column)
            line, column = _advance_position(text, line, column)
            continue

        if ch.isalpha() or ch == "_":
            i += 1
            while i < len(source) and (source[i].isalnum() or source[i] == "_"):
                i += 1
            text = source[start:i]
            emit(TokenKind.KEYWORD if text in KEYWORDS else TokenKind.IDENT, start, i, start_line, start_column)
            line, column = _advance_position(text, line, column)
            continue

        if ch.isdigit() or (ch == "." and i + 1 < len(source) and source[i + 1].isdigit()):
            match = _NUMBER_RE.match(source, i)
            if not match:
                raise LexError(f"invalid number at {start_line}:{start_column}")
            i = match.end()
            text = source[start:i]
            emit(TokenKind.NUMBER, start, i, start_line, start_column)
            line, column = _advance_position(text, line, column)
            continue

        matched = None
        for symbol in SYMBOLS:
            if source.startswith(symbol, i):
                matched = symbol
                break
        if matched is None:
            raise LexError(f"unexpected character {ch!r} at {start_line}:{start_column}")
        i += len(matched)
        emit(TokenKind.SYMBOL, start, i, start_line, start_column)
        line, column = _advance_position(matched, line, column)

    tokens.append(Token(TokenKind.EOF, "", len(source), len(source), line, column, len(tokens)))
    return tokens


def significant(tokens: Iterable[Token]) -> list[Token]:
    return [token for token in tokens if token.significant]
