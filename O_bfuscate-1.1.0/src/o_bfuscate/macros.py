from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Literal

from .lexer import Token, TokenKind, lex
from .transforms import decode_luau_string


ProtectionMode = Literal["auto", "no-vm", "hot", "light", "full", "encrypt"]


@dataclass(slots=True)
class FunctionPolicy:
    mode: ProtectionMode = "auto"
    key_id: str | None = None
    source_map: bool | None = None
    integrity: bool | None = None
    optimize: bool | None = None
    no_upvalues: bool = False


@dataclass(slots=True)
class MacroResult:
    source: str
    policies: dict[str, FunctionPolicy] = field(default_factory=dict)
    forced_strings: bool = False
    forced_numbers: bool = False
    expanded_macros: int = 0
    warnings: list[str] = field(default_factory=list)
    prelude: str = ""


_MODE_ALIASES: dict[str, ProtectionMode] = {
    "auto": "auto",
    "vm": "full",
    "full": "full",
    "full-vm": "full",
    "light": "light",
    "light-vm": "light",
    "hot": "hot",
    "native": "hot",
    "no-vm": "no-vm",
    "novm": "no-vm",
    "encrypt": "encrypt",
    "encfunc": "encrypt",
}

_WRAPPER_MODES: dict[str, ProtectionMode] = {
    "OBF_ENCFUNC": "encrypt",
    "OBF_VM": "full",
    "OBF_LIGHT": "light",
    "OBF_JIT": "light",
    "OBF_JIT_MAX": "hot",
    "OBF_HOT": "hot",
    "OBF_NO_VM": "no-vm",
    "OBF_NO_UPVALUES": "full",
    # wYnFuscate-compatible policy aliases. These are identity wrappers in
    # development builds and are removed during protection.
    "WYNF_JIT": "light",
    "WYNF_JIT_MAX": "hot",
    "WYNF_INLINE": "hot",
    "WYNF_NO_VIRTUALIZE": "no-vm",
}


def _sig(source: str) -> list[Token]:
    return [token for token in lex(source) if token.significant]


def _is_expression_if(tokens: list[Token], index: int, source: str, body_start: int) -> bool:
    if index <= body_start:
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


def _function_end(tokens: list[Token], function_index: int, source: str) -> int:
    """Return the token index of the matching function `end`."""
    block = 1
    pending_loop_do = 0
    i = function_index + 1
    while i < len(tokens):
        text = tokens[i].text
        if text == "function":
            block += 1
        elif text == "if" and not _is_expression_if(tokens, i, source, function_index + 1):
            block += 1
        elif text in {"while", "for"}:
            block += 1
            pending_loop_do += 1
        elif text == "repeat":
            block += 1
        elif text == "do":
            if pending_loop_do:
                pending_loop_do -= 1
            else:
                block += 1
        elif text in {"end", "until"}:
            block -= 1
            if block == 0:
                return i
        i += 1
    raise ValueError("unterminated function macro")


def _decode_key(token: Token) -> str | None:
    if token.kind != TokenKind.STRING:
        return None
    try:
        return decode_luau_string(token.text).decode("utf-8")
    except (UnicodeError, ValueError):
        return None


def _parse_bool(value: str) -> bool | None:
    value = value.lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return None


def _policy_from_text(text: str) -> FunctionPolicy:
    fields: dict[str, str] = {}
    bare: list[str] = []
    for part in re.split(r"[\s,]+", text.strip()):
        if not part:
            continue
        if "=" in part:
            key, value = part.split("=", 1)
            fields[key.strip().lower()] = value.strip()
        else:
            bare.append(part.strip().lower())
    requested = fields.get("mode") or (bare[0] if bare else "auto")
    mode = _MODE_ALIASES.get(requested.lower(), "auto")
    return FunctionPolicy(
        mode=mode,
        key_id=fields.get("key") or fields.get("key-id") or fields.get("key_id"),
        source_map=_parse_bool(fields["source-map"]) if "source-map" in fields else None,
        integrity=_parse_bool(fields["integrity"]) if "integrity" in fields else None,
        optimize=_parse_bool(fields["optimize"]) if "optimize" in fields else None,
        no_upvalues=("no-upvalues" in bare) or (_parse_bool(fields.get("no-upvalues", "false")) is True),
    )


def _pragma_policies(source: str) -> dict[str, FunctionPolicy]:
    policies: dict[str, FunctionPolicy] = {}
    pending: FunctionPolicy | None = None
    pragma_re = re.compile(r"^\s*--\s*@obf\s+(.+?)\s*$", re.IGNORECASE)
    function_re = re.compile(r"^\s*local\s+function\s+([A-Za-z_][A-Za-z0-9_]*)")
    for line in source.splitlines():
        match = pragma_re.match(line)
        if match:
            pending = _policy_from_text(match.group(1))
            continue
        fn = function_re.match(line)
        if fn and pending is not None:
            policies[fn.group(1)] = pending
            pending = None
            continue
        if line.strip() and not line.lstrip().startswith("--"):
            pending = None
    return policies


def process_macros(source: str) -> MacroResult:
    """Expand O_bfuscate identity macros and collect per-function policies.

    Supported function wrappers:
        local f = OBF_ENCFUNC(function(...) ... end, "key-id")
        local f = OBF_VM(function(...) ... end)
        local f = OBF_LIGHT(function(...) ... end)
        local f = OBF_HOT(function(...) ... end)
        local f = OBF_NO_VM(function(...) ... end)

    Literal wrappers OBF_ENCSTR(value) and OBF_ENCNUM(value) are removed while
    forcing the corresponding global transform on for the build.
    """
    result = MacroResult(source=source, policies=_pragma_policies(source))
    tokens = _sig(source)
    replacements: list[tuple[int, int, str]] = []
    used_wynf = False
    depth = 0
    pending_loop_do = 0
    i = 0
    while i < len(tokens):
        token = tokens[i]
        text = token.text
        if (
            depth == 0
            and i + 5 < len(tokens)
            and text == "local"
            and tokens[i + 1].kind == TokenKind.IDENT
            and tokens[i + 2].text == "="
            and tokens[i + 3].text in _WRAPPER_MODES
            and tokens[i + 4].text == "("
            and tokens[i + 5].text == "function"
        ):
            name = tokens[i + 1].text
            macro = tokens[i + 3].text
            try:
                function_end = _function_end(tokens, i + 5, source)
            except ValueError as exc:
                result.warnings.append(f"macro {macro} for {name} was not expanded: {exc}")
                i += 1
                continue
            cursor = function_end + 1
            key_id: str | None = None
            if cursor < len(tokens) and tokens[cursor].text == ",":
                cursor += 1
                if cursor < len(tokens):
                    key_id = _decode_key(tokens[cursor])
                    cursor += 1
            if cursor >= len(tokens) or tokens[cursor].text != ")":
                result.warnings.append(f"macro {macro} for {name} has unsupported trailing arguments")
                i += 1
                continue
            function_token = tokens[i + 5]
            end_token = tokens[function_end]
            suffix = source[function_token.end:end_token.end]
            replacements.append((token.start, tokens[cursor].end, f"local function {name}{suffix}"))
            result.policies[name] = FunctionPolicy(
                mode=_WRAPPER_MODES[macro], key_id=key_id, no_upvalues=macro == "OBF_NO_UPVALUES"
            )
            result.expanded_macros += 1
            used_wynf |= macro.startswith("WYNF_")
            i = cursor + 1
            continue

        # Existing-local assignment wrappers, e.g. `f = WYNF_INLINE(function...)`.
        if (
            depth == 0
            and i + 4 < len(tokens)
            and token.kind == TokenKind.IDENT
            and tokens[i + 1].text == "="
            and tokens[i + 2].text in _WRAPPER_MODES
            and tokens[i + 3].text == "("
            and tokens[i + 4].text == "function"
        ):
            name = token.text
            macro = tokens[i + 2].text
            try:
                function_end = _function_end(tokens, i + 4, source)
            except ValueError as exc:
                result.warnings.append(f"macro {macro} for {name} was not expanded: {exc}")
                i += 1
                continue
            cursor = function_end + 1
            if cursor < len(tokens) and tokens[cursor].text == ",":
                result.warnings.append(f"macro {macro} for {name} has unsupported trailing arguments")
                i += 1
                continue
            if cursor >= len(tokens) or tokens[cursor].text != ")":
                i += 1
                continue
            function_token = tokens[i + 4]
            end_token = tokens[function_end]
            replacements.append((tokens[i + 2].start, tokens[cursor].end, source[function_token.start:end_token.end]))
            result.policies[name] = FunctionPolicy(
                mode=_WRAPPER_MODES[macro], no_upvalues=macro == "OBF_NO_UPVALUES"
            )
            result.expanded_macros += 1
            used_wynf |= macro.startswith("WYNF_")
            i = cursor + 1
            continue

        # Anonymous wrapper in an arbitrary expression. Strip the identity
        # wrapper; nested VM compilation can still protect the closure.
        if (
            text in _WRAPPER_MODES
            and i + 2 < len(tokens)
            and tokens[i + 1].text == "("
            and tokens[i + 2].text == "function"
        ):
            macro = text
            try:
                function_end = _function_end(tokens, i + 2, source)
            except ValueError:
                i += 1
                continue
            cursor = function_end + 1
            if cursor < len(tokens) and tokens[cursor].text == ")":
                replacements.append((token.start, tokens[cursor].end, source[tokens[i + 2].start:tokens[function_end].end]))
                result.expanded_macros += 1
                used_wynf |= macro.startswith("WYNF_")
                i = cursor + 1
                continue

        # Literal identity wrappers are deliberately restricted to one literal
        # argument. Complex expressions remain untouched and generate a warning.
        if (
            text in {"OBF_ENCSTR", "OBF_ENCNUM"}
            and i + 3 < len(tokens)
            and tokens[i + 1].text == "("
            and tokens[i + 3].text == ")"
        ):
            literal = tokens[i + 2]
            valid = (
                text == "OBF_ENCSTR" and literal.kind in {TokenKind.STRING, TokenKind.INTERP_STRING}
            ) or (text == "OBF_ENCNUM" and literal.kind == TokenKind.NUMBER)
            if valid:
                replacements.append((token.start, tokens[i + 3].end, source[literal.start:literal.end]))
                result.forced_strings |= text == "OBF_ENCSTR"
                result.forced_numbers |= text == "OBF_ENCNUM"
                result.expanded_macros += 1
                i += 4
                continue

        if text == "function":
            depth += 1
        elif text == "if" and not _is_expression_if(tokens, i, source, 0):
            depth += 1
        elif text in {"while", "for"}:
            depth += 1
            pending_loop_do += 1
        elif text == "repeat":
            depth += 1
        elif text == "do":
            if pending_loop_do:
                pending_loop_do -= 1
            else:
                depth += 1
        elif text in {"end", "until"} and depth:
            depth -= 1
        i += 1

    for start, end, replacement in sorted(replacements, reverse=True):
        result.source = result.source[:start] + replacement + result.source[end:]
    if used_wynf:
        result.prelude = "WYNF_OBFUSCATED=true;"
    return result
