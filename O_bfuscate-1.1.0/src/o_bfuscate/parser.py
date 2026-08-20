from __future__ import annotations

from dataclasses import dataclass, field
import random
import re
from typing import Iterable

from .lexer import Token, TokenKind, significant
from .names import NameGenerator


class ParseError(ValueError):
    def __init__(self, message: str, token: Token):
        super().__init__(f"{message} at {token.line}:{token.column} near {token.text!r}")
        self.token = token


@dataclass(slots=True)
class Binding:
    source: str
    obfuscated: str


@dataclass(slots=True)
class Scope:
    bindings: dict[str, Binding] = field(default_factory=dict)


@dataclass(slots=True)
class Analysis:
    replacements: dict[int, str] = field(default_factory=dict)
    runtime_strings: set[int] = field(default_factory=set)
    runtime_numbers: set[int] = field(default_factory=set)
    runtime_booleans: set[int] = field(default_factory=set)
    runtime_nil: set[int] = field(default_factory=set)
    property_rewrites: list[tuple[int, int, str]] = field(default_factory=list)
    table_key_rewrites: list[tuple[int, str]] = field(default_factory=list)
    protected_names: set[str] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)


BINARY_PRECEDENCE: dict[str, tuple[int, bool]] = {
    "or": (1, False),
    "and": (2, False),
    "<": (3, False), ">": (3, False), "<=": (3, False), ">=": (3, False), "~=": (3, False), "==": (3, False),
    "|": (4, False),
    "~": (5, False),
    "&": (6, False),
    "<<": (7, False), ">>": (7, False),
    "..": (8, True),
    "+": (9, False), "-": (9, False),
    "*": (10, False), "/": (10, False), "//": (10, False), "%": (10, False),
    "^": (12, True),
}
UNARY = {"not", "-", "#", "~"}
ASSIGNMENT = {"=", "+=", "-=", "*=", "/=", "//=", "%=", "^=", "..=", "<<=", ">>="}
STATEMENT_STARTERS = {
    "local", "function", "if", "while", "repeat", "for", "do", "return", "break", "continue",
    "type", "export", "declare", "@",
}


_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def gather_protected_names(tokens: list[Token], extra: Iterable[str] = ()) -> set[str]:
    protected = {"self", "_", *extra}
    sig = significant(tokens)

    # Interpolation expressions are not rewritten directly. Preserve any names that
    # may be referenced inside them so renaming cannot change behavior.
    for token in sig:
        if token.kind == TokenKind.INTERP_STRING:
            text = token.text[1:-1]
            depth = 0
            buf: list[str] = []
            for ch in text:
                if ch == "{":
                    if depth:
                        buf.append(ch)
                    depth += 1
                elif ch == "}" and depth:
                    depth -= 1
                    if depth == 0:
                        protected.update(_IDENTIFIER_RE.findall("".join(buf)))
                        buf.clear()
                    else:
                        buf.append(ch)
                elif depth:
                    buf.append(ch)

    # typeof(valueExpression) occurs in type syntax. Preserve referenced names
    # rather than trying to rewrite inside every evolving Luau type construct.
    i = 0
    while i + 1 < len(sig):
        if sig[i].text == "typeof" and sig[i + 1].text == "(":
            depth = 1
            i += 2
            while i < len(sig) and depth:
                if sig[i].text == "(":
                    depth += 1
                elif sig[i].text == ")":
                    depth -= 1
                elif depth and sig[i].kind == TokenKind.IDENT:
                    protected.add(sig[i].text)
                i += 1
            continue
        i += 1
    return protected


class LuauAnalyzer:
    def __init__(
        self,
        all_tokens: list[Token],
        rng: random.Random,
        preserve_names: Iterable[str] = (),
    ) -> None:
        self.all_tokens = all_tokens
        self.tokens = [t for t in all_tokens if t.kind not in {TokenKind.WHITESPACE, TokenKind.COMMENT}]
        self.pos = 0
        used = {t.text for t in self.tokens if t.kind == TokenKind.IDENT}
        self.analysis = Analysis(protected_names=gather_protected_names(all_tokens, preserve_names))
        self.names = NameGenerator(rng, used)
        self.scopes: list[Scope] = [Scope()]

    def current(self) -> Token:
        return self.tokens[min(self.pos, len(self.tokens) - 1)]

    def previous(self) -> Token:
        return self.tokens[max(0, self.pos - 1)]

    def at(self, text: str) -> bool:
        return self.current().text == text

    def at_kind(self, kind: TokenKind) -> bool:
        return self.current().kind == kind

    def advance(self) -> Token:
        token = self.current()
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
        return token

    def accept(self, text: str) -> Token | None:
        if self.at(text):
            return self.advance()
        return None

    def expect(self, text: str) -> Token:
        if not self.at(text):
            raise ParseError(f"expected {text!r}", self.current())
        return self.advance()

    def expect_ident(self) -> Token:
        if self.current().kind != TokenKind.IDENT:
            raise ParseError("expected identifier", self.current())
        return self.advance()

    def push_scope(self) -> None:
        self.scopes.append(Scope())

    def pop_scope(self) -> None:
        if len(self.scopes) <= 1:
            raise RuntimeError("scope underflow")
        self.scopes.pop()

    def make_binding(self, token: Token) -> Binding:
        if token.text in self.analysis.protected_names or token.text.startswith("__O_"):
            binding = Binding(token.text, token.text)
        else:
            binding = Binding(token.text, self.names.next())
            self.analysis.replacements[token.index] = binding.obfuscated
        return binding

    def activate(self, binding: Binding) -> None:
        self.scopes[-1].bindings[binding.source] = binding

    def declare(self, token: Token) -> Binding:
        binding = self.make_binding(token)
        self.activate(binding)
        return binding

    def reference(self, token: Token) -> None:
        if token.text in self.analysis.protected_names:
            return
        for scope in reversed(self.scopes):
            binding = scope.bindings.get(token.text)
            if binding:
                if binding.obfuscated != token.text:
                    self.analysis.replacements[token.index] = binding.obfuscated
                return

    def has_newline_before_current(self) -> bool:
        if self.pos == 0:
            return False
        return "\n" in self.source_gap(self.previous(), self.current()) or "\r" in self.source_gap(self.previous(), self.current())

    def source_gap(self, left: Token, right: Token) -> str:
        # Reconstruct only the trivia between significant tokens from original tokens.
        parts: list[str] = []
        for token in self.all_tokens[left.index + 1:right.index]:
            parts.append(token.text)
        return "".join(parts)

    def run(self) -> Analysis:
        self.parse_block({""})
        if self.current().kind != TokenKind.EOF:
            raise ParseError("unexpected trailing token", self.current())
        return self.analysis

    def parse_block(self, terminators: set[str]) -> None:
        while self.current().kind != TokenKind.EOF and self.current().text not in terminators:
            if self.accept(";"):
                continue
            self.parse_statement()
            self.accept(";")

    def parse_statement(self) -> None:
        while self.at("@"):
            self.parse_attribute()

        text = self.current().text
        if text == "local":
            self.parse_local()
        elif text == "function":
            self.parse_function_statement()
        elif text == "if":
            self.parse_if_statement()
        elif text == "while":
            self.parse_while()
        elif text == "repeat":
            self.parse_repeat()
        elif text == "for":
            self.parse_for()
        elif text == "do":
            self.advance()
            self.push_scope()
            self.parse_block({"end"})
            self.expect("end")
            self.pop_scope()
        elif text == "return":
            self.advance()
            if self.current().kind != TokenKind.EOF and self.current().text not in {"end", "else", "elseif", "until", ";"}:
                self.parse_expr_list()
        elif text in {"break", "continue"}:
            self.advance()
        elif text == "type" and self.tokens[min(self.pos + 1, len(self.tokens) - 1)].kind == TokenKind.IDENT:
            self.parse_type_declaration(exported=False)
        elif text == "export":
            self.advance()
            if self.at("type"):
                self.parse_type_declaration(exported=True)
            else:
                raise ParseError("only 'export type' is valid here", self.current())
        elif text == "declare":
            self.parse_declare()
        else:
            self.parse_assignment_or_call_statement()

    def parse_attribute(self) -> None:
        self.expect("@")
        self.expect_ident()
        if self.accept("("):
            if not self.at(")"):
                self.parse_expr_list()
            self.expect(")")

    def parse_local(self) -> None:
        self.expect("local")
        if self.accept("function"):
            name = self.expect_ident()
            self.declare(name)  # recursive local function
            self.parse_function_body()
            return

        pending: list[Binding] = []
        while True:
            name = self.expect_ident()
            pending.append(self.make_binding(name))
            if self.accept(":"):
                self.skip_type_until({",", "=", ";"}, stop_on_newline=True)
            if not self.accept(","):
                break
        if self.accept("="):
            self.parse_expr_list()
        for binding in pending:
            self.activate(binding)

    def parse_function_statement(self) -> None:
        self.expect("function")
        base = self.expect_ident()
        self.reference(base)
        while self.accept("."):
            self.expect_ident()  # property name
        if self.accept(":"):
            self.expect_ident()  # method name
        self.parse_function_body()

    def parse_function_body(self) -> None:
        if self.at("<"):
            self.skip_balanced("<", ">")
        self.expect("(")
        self.push_scope()
        if not self.at(")"):
            while True:
                if self.accept("..."):
                    if self.accept(":"):
                        self.skip_type_until({",", ")"}, stop_on_newline=False)
                else:
                    param = self.expect_ident()
                    self.declare(param)
                    if self.accept(":"):
                        self.skip_type_until({",", ")"}, stop_on_newline=False)
                if not self.accept(","):
                    break
        self.expect(")")
        if self.accept(":"):
            self.skip_return_type()
        self.parse_block({"end"})
        self.expect("end")
        self.pop_scope()

    def parse_if_statement(self) -> None:
        self.expect("if")
        self.parse_expression()
        self.expect("then")
        self.push_scope()
        self.parse_block({"elseif", "else", "end"})
        self.pop_scope()
        while self.accept("elseif"):
            self.parse_expression()
            self.expect("then")
            self.push_scope()
            self.parse_block({"elseif", "else", "end"})
            self.pop_scope()
        if self.accept("else"):
            self.push_scope()
            self.parse_block({"end"})
            self.pop_scope()
        self.expect("end")

    def parse_while(self) -> None:
        self.expect("while")
        self.parse_expression()
        self.expect("do")
        self.push_scope()
        self.parse_block({"end"})
        self.expect("end")
        self.pop_scope()

    def parse_repeat(self) -> None:
        self.expect("repeat")
        self.push_scope()
        self.parse_block({"until"})
        self.expect("until")
        self.parse_expression()
        self.pop_scope()

    def parse_for(self) -> None:
        self.expect("for")
        pending: list[Binding] = []
        first = self.expect_ident()
        pending.append(self.make_binding(first))
        if self.accept("="):
            self.parse_expression()
            self.expect(",")
            self.parse_expression()
            if self.accept(","):
                self.parse_expression()
        else:
            while self.accept(","):
                pending.append(self.make_binding(self.expect_ident()))
            self.expect("in")
            self.parse_expr_list()
        self.expect("do")
        self.push_scope()
        for binding in pending:
            self.activate(binding)
        self.parse_block({"end"})
        self.expect("end")
        self.pop_scope()

    def parse_type_declaration(self, exported: bool) -> None:
        self.expect("type")
        self.expect_ident()  # type names are intentionally not renamed
        if self.at("<"):
            self.skip_balanced("<", ">")
        self.expect("=")
        self.skip_type_until({";"}, stop_on_newline=True)

    def parse_declare(self) -> None:
        self.expect("declare")
        # Declarations are type-level surface. Consume conservatively through the
        # current line or a balanced class block.
        if self.accept("class"):
            if self.current().kind == TokenKind.IDENT:
                self.advance()
            while self.current().kind != TokenKind.EOF and not self.at("end"):
                self.advance()
            self.accept("end")
            return
        while self.current().kind != TokenKind.EOF and not self.at(";"):
            if self.has_newline_before_current():
                break
            self.advance()

    def parse_assignment_or_call_statement(self) -> None:
        self.parse_expression()
        while self.accept(","):
            self.parse_expression()
        if self.current().text in ASSIGNMENT:
            self.advance()
            self.parse_expr_list()

    def parse_expr_list(self) -> None:
        self.parse_expression()
        while self.accept(","):
            self.parse_expression()

    def parse_expression(self, min_precedence: int = 0) -> None:
        if self.current().text in UNARY:
            self.advance()
            self.parse_expression(11)
        else:
            self.parse_primary()

        while True:
            op = self.current().text
            info = BINARY_PRECEDENCE.get(op)
            if info is None:
                break
            precedence, right_assoc = info
            if precedence < min_precedence:
                break
            self.advance()
            self.parse_expression(precedence if right_assoc else precedence + 1)

    def parse_primary(self) -> None:
        token = self.current()
        # `type` is both a Luau declaration keyword and a legacy runtime global.
        # In expression position (normally `type(value)`) it must be treated as a
        # callable global rather than as a type declaration.
        if token.text == "type":
            self.advance()
            self.parse_suffixes()
            return
        if token.kind == TokenKind.IDENT:
            self.reference(self.advance())
            self.parse_suffixes()
            return
        if token.kind == TokenKind.NUMBER:
            self.analysis.runtime_numbers.add(token.index)
            self.advance()
            self.parse_suffixes()
            return
        if token.kind in {TokenKind.STRING, TokenKind.INTERP_STRING}:
            if token.kind == TokenKind.STRING:
                self.analysis.runtime_strings.add(token.index)
            self.advance()
            self.parse_suffixes()
            return
        if token.text in {"true", "false"}:
            self.analysis.runtime_booleans.add(token.index)
            self.advance()
            self.parse_suffixes()
            return
        if token.text == "nil":
            self.analysis.runtime_nil.add(token.index)
            self.advance()
            self.parse_suffixes()
            return
        if token.text == "...":
            self.advance()
            self.parse_suffixes()
            return
        if token.text == "function":
            self.advance()
            self.parse_function_body()
            self.parse_suffixes()
            return
        if token.text == "{":
            self.parse_table()
            self.parse_suffixes()
            return
        if token.text == "(":
            self.advance()
            self.parse_expression()
            self.expect(")")
            self.parse_suffixes()
            return
        if token.text == "if":
            self.parse_if_expression()
            self.parse_suffixes()
            return
        raise ParseError("expected expression", token)

    def parse_suffixes(self) -> None:
        while True:
            if self.accept("["):
                self.parse_expression()
                self.expect("]")
            elif self.at("."):
                dot = self.advance()
                name = self.expect_ident()
                self.analysis.property_rewrites.append((dot.index, name.index, name.text))
            elif self.accept(":"):
                self.expect_ident()  # method name
                self.parse_call_args()
            elif self.at("(") or self.at("{") or self.current().kind in {TokenKind.STRING, TokenKind.INTERP_STRING}:
                self.parse_call_args()
            elif self.accept("::"):
                self.skip_type_until({",", ")", "]", "}", ";", "then", "do", "end", "else", "elseif", "until"}, stop_on_newline=False, stop_on_binary=True)
            else:
                break

    def parse_call_args(self) -> None:
        if self.accept("("):
            if not self.at(")"):
                self.parse_expr_list()
            self.expect(")")
        elif self.at("{"):
            self.parse_table()
        elif self.current().kind in {TokenKind.STRING, TokenKind.INTERP_STRING}:
            token = self.advance()
            if token.kind == TokenKind.STRING:
                self.analysis.runtime_strings.add(token.index)
        else:
            raise ParseError("expected call arguments", self.current())

    def parse_table(self) -> None:
        self.expect("{")
        while not self.at("}"):
            if self.accept("["):
                self.parse_expression()
                self.expect("]")
                self.expect("=")
                self.parse_expression()
            elif self.current().kind == TokenKind.IDENT and self.peek_text(1) == "=":
                key = self.advance()  # field name, not a variable reference
                self.analysis.table_key_rewrites.append((key.index, key.text))
                self.expect("=")
                self.parse_expression()
            else:
                self.parse_expression()
            if not (self.accept(",") or self.accept(";")):
                break
        self.expect("}")

    def parse_if_expression(self) -> None:
        self.expect("if")
        self.parse_expression()
        self.expect("then")
        self.parse_expression()
        while self.accept("elseif"):
            self.parse_expression()
            self.expect("then")
            self.parse_expression()
        self.expect("else")
        self.parse_expression()

    def peek_text(self, offset: int) -> str:
        idx = min(self.pos + offset, len(self.tokens) - 1)
        return self.tokens[idx].text

    def skip_balanced(self, opener: str, closer: str) -> None:
        self.expect(opener)
        depth = 1
        while depth and self.current().kind != TokenKind.EOF:
            if self.at(opener):
                depth += 1
            elif self.at(closer):
                depth -= 1
            self.advance()
        if depth:
            raise ParseError(f"unterminated {opener}{closer} group", self.current())

    def skip_return_type(self) -> None:
        start = self.pos
        depth = {"(": 0, "[": 0, "{": 0, "<": 0}
        close_for = {")": "(", "]": "[", "}": "{", ">": "<"}
        consumed = False
        while self.current().kind != TokenKind.EOF:
            text = self.current().text
            total = sum(depth.values())
            if consumed and total == 0:
                if text in {"return", "local", "if", "while", "repeat", "for", "do", "break", "continue", "type", "export", "declare", "@"}:
                    break
                if self.has_newline_before_current():
                    break
            if text in depth:
                depth[text] += 1
            elif text in close_for:
                opener = close_for[text]
                if depth[opener] > 0:
                    depth[opener] -= 1
                elif total == 0:
                    break
            consumed = True
            self.advance()
        if self.pos == start:
            raise ParseError("expected return type", self.current())

    def skip_type_until(
        self,
        stops: set[str],
        *,
        stop_on_newline: bool,
        stop_on_binary: bool = False,
    ) -> None:
        depth = {"(": 0, "[": 0, "{": 0, "<": 0}
        close_for = {")": "(", "]": "[", "}": "{", ">": "<"}
        consumed = False
        while self.current().kind != TokenKind.EOF:
            text = self.current().text
            total = sum(depth.values())
            if total == 0 and consumed:
                if text in stops:
                    break
                if stop_on_binary and text in BINARY_PRECEDENCE:
                    break
                if stop_on_newline and self.has_newline_before_current():
                    break
            if text in depth:
                depth[text] += 1
            elif text in close_for:
                opener = close_for[text]
                if depth[opener] > 0:
                    depth[opener] -= 1
                elif total == 0:
                    break
            consumed = True
            self.advance()
        if not consumed:
            raise ParseError("expected type", self.current())


def analyze(
    tokens: list[Token],
    rng: random.Random,
    preserve_names: Iterable[str] = (),
) -> Analysis:
    return LuauAnalyzer(tokens, rng, preserve_names).run()
