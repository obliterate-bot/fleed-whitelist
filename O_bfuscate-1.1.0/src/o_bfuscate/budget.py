from __future__ import annotations

from dataclasses import dataclass

from .lexer import Token, TokenKind, lex


@dataclass(slots=True, frozen=True)
class RegisterBudget:
    estimated_peak_locals: int
    root_locals: int
    limit: int = 200
    reserve: int = 12

    @property
    def available_for_helpers(self) -> int:
        return max(0, self.limit - self.reserve - self.estimated_peak_locals)

    @property
    def constrained(self) -> bool:
        return self.available_for_helpers <= 2


def _is_expression_if(tokens: list[Token], index: int, source: str) -> bool:
    if index <= 0:
        return False
    previous = tokens[index - 1]
    if previous.text in {"then", "else", "elseif"}:
        gap = source[previous.end:tokens[index].start]
        return "\n" not in gap and "\r" not in gap
    return previous.text in {
        "return", "=", ",", "(", "[", "{", ":", "and", "or",
        "+", "-", "*", "/", "//", "%", "^", "..", "<", ">",
        "<=", ">=", "==", "~=", "~", "&", "|", "<<", ">>", "not",
    }


def _count_local_names(tokens: list[Token], position: int) -> int:
    """Count names in a local declaration beginning after `local`."""
    if position >= len(tokens):
        return 0
    if tokens[position].text == "function":
        return 1 if position + 1 < len(tokens) and tokens[position + 1].kind == TokenKind.IDENT else 0
    count = 0
    i = position
    type_depth = 0
    expecting_name = True
    while i < len(tokens):
        token = tokens[i]
        text = token.text
        if expecting_name:
            if token.kind != TokenKind.IDENT:
                break
            count += 1
            expecting_name = False
            i += 1
            continue
        if text == "=":
            break
        if text == "," and type_depth == 0:
            expecting_name = True
            i += 1
            continue
        if text == ":" and type_depth == 0:
            type_depth = 1
            i += 1
            continue
        if type_depth:
            if text in {"(", "[", "{", "<"}:
                type_depth += 1
            elif text in {")", "]", "}", ">"}:
                type_depth = max(1, type_depth - 1)
            elif text in {",", "="} and type_depth == 1:
                type_depth = 0
                if text == ",":
                    expecting_name = True
                    i += 1
                    continue
                break
            i += 1
            continue
        break
    return count


def estimate_register_budget(source: str, *, limit: int = 200, reserve: int = 12) -> RegisterBudget:
    """Conservatively estimate active chunk-local pressure.

    Luau's allocator also needs temporary registers, so this deliberately leaves a
    reserve. The estimate is used only to choose helper storage; official compiler
    validation remains the source of truth.
    """
    tokens = [token for token in lex(source) if token.significant]
    scopes = [0]
    blocks: list[str] = []
    function_depth = 0
    pending_loop_do = 0
    peak = 0
    root_locals = 0
    i = 0
    while i < len(tokens):
        text = tokens[i].text
        if text == "function":
            blocks.append("function")
            function_depth += 1
        elif text == "if" and not _is_expression_if(tokens, i, source):
            blocks.append("scope")
            if function_depth == 0:
                scopes.append(0)
        elif text in {"while", "for"}:
            blocks.append("scope")
            pending_loop_do += 1
            if function_depth == 0:
                scopes.append(0)
        elif text == "repeat":
            blocks.append("repeat")
            if function_depth == 0:
                scopes.append(0)
        elif text == "do":
            if pending_loop_do:
                pending_loop_do -= 1
            else:
                blocks.append("scope")
                if function_depth == 0:
                    scopes.append(0)
        elif text in {"end", "until"} and blocks:
            kind = blocks.pop()
            if kind == "function":
                function_depth = max(0, function_depth - 1)
            elif function_depth == 0 and len(scopes) > 1:
                scopes.pop()
        elif text == "local" and function_depth == 0:
            count = _count_local_names(tokens, i + 1)
            scopes[-1] += count
            if len(scopes) == 1:
                root_locals += count
            peak = max(peak, sum(scopes))
        i += 1
    peak = max(peak, root_locals)
    return RegisterBudget(peak, root_locals, limit=limit, reserve=reserve)
