from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import random
import re
from typing import Iterable

from .lexer import SYMBOLS, Token, TokenKind, lex
from .names import NameGenerator
from .parser import Analysis


class TransformError(ValueError):
    pass


@dataclass(slots=True)
class BuildArtifacts:
    replacements: dict[int, str] = field(default_factory=dict)
    prelude_parts: list[str] = field(default_factory=list)
    string_count: int = 0
    number_count: int = 0
    property_count: int = 0
    string_chunk_count: int = 0
    boolean_count: int = 0
    nil_count: int = 0
    opaque_predicate_count: int = 0
    string_vault_count: int = 0
    string_decoy_count: int = 0
    bitwise_number_count: int = 0
    helper_names: list[str] = field(default_factory=list)


_COMMON_ESCAPES = {
    "a": 7,
    "b": 8,
    "f": 12,
    "n": 10,
    "r": 13,
    "t": 9,
    "v": 11,
    "\\": 92,
    '"': 34,
    "'": 39,
}


def decode_luau_string(text: str) -> bytes:
    if text.startswith("["):
        match = re.match(r"\[(=*)\[", text)
        if not match:
            raise TransformError("invalid long string")
        level = match.group(1)
        start = len(level) + 2
        end = len(text) - len(level) - 2
        body = text[start:end]
        if body.startswith("\r\n"):
            body = body[2:]
        elif body.startswith("\n") or body.startswith("\r"):
            body = body[1:]
        body = body.replace("\r\n", "\n").replace("\r", "\n")
        return body.encode("utf-8")

    if len(text) < 2 or text[0] not in "'\"" or text[-1] != text[0]:
        raise TransformError("unsupported string literal")

    body = text[1:-1]
    output = bytearray()
    i = 0
    while i < len(body):
        ch = body[i]
        if ch != "\\":
            output.extend(ch.encode("utf-8"))
            i += 1
            continue
        i += 1
        if i >= len(body):
            raise TransformError("trailing escape")
        esc = body[i]
        if esc in _COMMON_ESCAPES:
            output.append(_COMMON_ESCAPES[esc])
            i += 1
            continue
        if esc == "z":
            i += 1
            while i < len(body) and body[i].isspace():
                i += 1
            continue
        if esc == "x":
            if i + 2 >= len(body):
                raise TransformError("short hex escape")
            output.append(int(body[i + 1:i + 3], 16))
            i += 3
            continue
        if esc == "u" and i + 1 < len(body) and body[i + 1] == "{":
            close = body.find("}", i + 2)
            if close < 0:
                raise TransformError("unterminated unicode escape")
            codepoint = int(body[i + 2:close], 16)
            output.extend(chr(codepoint).encode("utf-8"))
            i = close + 1
            continue
        if esc.isdigit():
            j = i
            while j < len(body) and j < i + 3 and body[j].isdigit():
                j += 1
            value = int(body[i:j], 10)
            if value > 255:
                raise TransformError("decimal escape exceeds 255")
            output.append(value)
            i = j
            continue
        if esc == "\n":
            output.append(10)
            i += 1
            continue
        if esc == "\r":
            if i + 1 < len(body) and body[i + 1] == "\n":
                i += 1
            output.append(10)
            i += 1
            continue
        # Luau accepts escaped punctuation in several contexts. Preserve the
        # escaped character rather than risking plaintext fallback.
        output.extend(esc.encode("utf-8"))
        i += 1
    return bytes(output)


def _escaped_byte_string(data: bytes) -> str:
    return '"' + "".join(f"\\{byte:03d}" for byte in data) + '"'


def _encode_bytes(
    data: bytes,
    seed: int,
    multiplier: int,
    increment: int,
    twist: int = 0,
    reverse: bool = False,
) -> bytes:
    if reverse:
        data = data[::-1]
    state = seed & 0xFF
    out = bytearray()
    for position, byte in enumerate(data, 1):
        state = (state * multiplier + increment) % 256
        out.append((byte + state + position * twist) % 256)
    return bytes(out)


def _split_bytes(data: bytes, rng: random.Random) -> list[bytes]:
    if not data:
        return [b""]
    if len(data) <= 4:
        return [data]
    maximum_chunks = min(5, max(2, (len(data) + 5) // 6))
    chunk_count = rng.randint(2, maximum_chunks)
    cuts = sorted(rng.sample(range(1, len(data)), chunk_count - 1))
    bounds = [0, *cuts, len(data)]
    return [data[bounds[i]:bounds[i + 1]] for i in range(len(bounds) - 1)]


def add_string_vault(
    tokens: list[Token],
    analysis: Analysis,
    artifacts: BuildArtifacts,
    rng: random.Random,
    names: NameGenerator,
    *,
    encrypt_properties: bool = True,
    layered: bool = False,
    shards: int = 1,
    decoys: int = 0,
    helper_storage: str = "local",
) -> None:
    requests: list[tuple[str, tuple[int, ...], bytes]] = []

    for token_index in sorted(analysis.runtime_strings):
        token = tokens[token_index]
        try:
            raw = decode_luau_string(token.text)
        except (TransformError, UnicodeError, ValueError):
            continue
        requests.append(("literal", (token_index,), raw))

    if encrypt_properties:
        for dot_index, name_index, name in analysis.property_rewrites:
            requests.append(("property", (dot_index, name_index), name.encode("utf-8")))
        for name_index, name in analysis.table_key_rewrites:
            requests.append(("table_key", (name_index,), name.encode("utf-8")))

    if not requests:
        return

    unique = list(dict.fromkeys(raw for _, _, raw in requests))
    actual_set = set(unique)
    decoy_values: list[bytes] = []
    for _ in range(max(0, min(decoys, 64))):
        while True:
            length = rng.randint(3, 24)
            candidate = bytes(rng.randrange(0, 256) for _ in range(length))
            if candidate not in actual_set and candidate not in decoy_values:
                decoy_values.append(candidate)
                break

    entries = unique + decoy_values
    rng.shuffle(entries)
    shard_count = max(1, min(int(shards), 8, len(entries)))
    shard_entries: list[list[bytes]] = [[] for _ in range(shard_count)]
    for position, raw in enumerate(entries):
        shard_entries[position % shard_count].append(raw)

    helpers = [names.random_name(12) for _ in range(shard_count)]
    root_name = names.random_name(14)
    char_name = names.random_name(8)
    byte_name = names.random_name(8)
    concat_name = names.random_name(8)
    artifacts.helper_names.extend([root_name, *helpers, char_name, byte_name, concat_name])

    locations: dict[bytes, tuple[int, int]] = {}
    for shard_index, values in enumerate(shard_entries):
        for local_index, raw in enumerate(values, 1):
            locations[raw] = (shard_index, local_index)

    masks: list[tuple[int, int]] = []
    for _ in range(shard_count):
        masks.append((rng.randrange(3, 24), rng.randrange(19, 251)))

    def access(raw: bytes) -> str:
        shard_index, local_index = locations[raw]
        helper = f"{root_name}[{shard_index + 1}]"
        if not layered:
            return f"{helper}({local_index})"
        stride, offset = masks[shard_index]
        masked = local_index * stride + offset
        salt = rng.randrange(1_003, 90_001)
        return f"{helper}(({masked + salt}-{salt}))"

    property_count = 0
    for kind, indices, raw in requests:
        expression = access(raw)
        if kind == "literal":
            artifacts.replacements[indices[0]] = expression
        elif kind == "property":
            dot_index, name_index = indices
            artifacts.replacements[dot_index] = f"[{expression}]"
            artifacts.replacements[name_index] = ""
            property_count += 1
        else:
            artifacts.replacements[indices[0]] = f"[{expression}]"
            property_count += 1

    decoder_parts = [f"local {char_name},{byte_name},{concat_name}=string.char,string.byte,table.concat;"]
    chunk_count = 0
    for shard_index, values in enumerate(shard_entries):
        helper = helpers[shard_index]
        if layered:
            stride, offset = masks[shard_index]
            encoded_records: list[str] = []
            for raw in values:
                chunks: list[str] = []
                for chunk in _split_bytes(raw, rng):
                    seed = rng.randrange(1, 256)
                    multiplier = rng.randrange(1, 256, 2)
                    increment = rng.randrange(0, 256)
                    twist = rng.randrange(0, 256)
                    reverse = rng.choice((False, True))
                    encoded = _encode_bytes(chunk, seed, multiplier, increment, twist, reverse)
                    chunks.append(
                        "{" + ",".join((
                            _escaped_byte_string(encoded),
                            str(seed),
                            str(multiplier),
                            str(increment),
                            str(twist),
                            "1" if reverse else "0",
                        )) + "}"
                    )
                    chunk_count += 1
                encoded_records.append("{" + ",".join(chunks) + "}")
            encoded_table = ",".join(encoded_records)
            decoder_parts.append(
                f"local {helper}=(function()local e={{{encoded_table}}};local c={{}};"
                f"return function(x)local i=(x-{offset})//{stride};local v=c[i];if v then return v end;"
                f"local t={{}};for z=1,#e[i] do local d=e[i][z];local s=d[1];local q=d[2];local u={{}};"
                f"for p=1,#s do q=(q*d[3]+d[4])%256;local j=d[6]==1 and(#s-p+1)or p;"
                f"u[j]={char_name}(({byte_name}(s,p)-q-p*d[5])%256)end;t[z]={concat_name}(u)end;"
                f"v={concat_name}(t);c[i]=v;return v end end)();"
            )
        else:
            multiplier = rng.randrange(1, 256, 2)
            increment = rng.randrange(0, 256)
            encoded_entries: list[bytes] = []
            seeds: list[int] = []
            for raw in values:
                seed = rng.randrange(1, 256)
                seeds.append(seed)
                encoded_entries.append(_encode_bytes(raw, seed, multiplier, increment))
            encoded_table = ",".join(_escaped_byte_string(entry) for entry in encoded_entries)
            seed_table = ",".join(str(seed) for seed in seeds)
            decoder_parts.append(
                f"local {helper}=(function()local e={{{encoded_table}}};local k={{{seed_table}}};local c={{}};"
                f"return function(i)local v=c[i];if v then return v end;local s=e[i];local q=k[i];local t={{}};"
                f"for p=1,#s do q=(q*{multiplier}+{increment})%256;t[p]={char_name}(({byte_name}(s,p)-q)%256)end;"
                f"v={concat_name}(t);c[i]=v;return v end end)();"
            )
            chunk_count += len(values)

    storage = helper_storage.lower().strip()
    if storage not in {"local", "global"}:
        raise TransformError(f"unsupported helper storage mode: {helper_storage}")
    declaration = "local " if storage == "local" else ""
    decoder_body = "".join(decoder_parts) + "return{" + ",".join(helpers) + "}end)();"
    artifacts.prelude_parts.append(f"{declaration}{root_name}=(function(){decoder_body}")
    artifacts.string_count = len(unique)
    artifacts.string_chunk_count = chunk_count
    artifacts.string_vault_count = shard_count
    artifacts.string_decoy_count = len(decoy_values)
    artifacts.property_count = property_count

def _parse_integer_literal(text: str) -> int | None:
    cleaned = text.replace("_", "")
    try:
        if cleaned.lower().startswith("0x") and "." not in cleaned and "p" not in cleaned.lower():
            return int(cleaned, 16)
        if cleaned.lower().startswith("0b"):
            return int(cleaned, 2)
        if re.fullmatch(r"[0-9]+", cleaned):
            return int(cleaned, 10)
    except ValueError:
        return None
    return None


def add_number_splitting(
    tokens: list[Token],
    analysis: Analysis,
    artifacts: BuildArtifacts,
    rng: random.Random,
    names: NameGenerator,
    depth: int = 1,
    *,
    bitwise: bool = False,
) -> None:
    safe_limit = 9_007_199_254_740_000
    xor_name = "bit32.bxor" if bitwise else ""
    used_xor = False

    def encode(value: int, remaining: int) -> str:
        if remaining <= 0:
            return str(value)
        magnitude = rng.randint(2_003, 900_001)
        if value - magnitude < -safe_limit:
            magnitude = -magnitude
        if rng.choice((False, True)) and -safe_limit <= value + magnitude <= safe_limit:
            left = value + magnitude
            right = magnitude
            return f"({encode(left, remaining - 1)}-{encode(right, remaining - 1)})"
        left = magnitude
        right = value - magnitude
        return f"({encode(left, remaining - 1)}+{encode(right, remaining - 1)})"

    count = 0
    for token_index in sorted(analysis.runtime_numbers):
        if token_index in artifacts.replacements:
            continue
        value = _parse_integer_literal(tokens[token_index].text)
        if value is None or abs(value) > safe_limit:
            continue
        selected_depth = max(1, min(depth, 5))
        if bitwise and 0 <= value <= 0xFFFFFFFF and rng.random() < 0.65:
            key = rng.randrange(1, 0x100000000)
            encoded = value ^ key
            artifacts.replacements[token_index] = (
                f"{xor_name}({encode(encoded, max(0, selected_depth - 1))},"
                f"{encode(key, max(0, selected_depth - 1))})"
            )
            artifacts.bitwise_number_count += 1
            used_xor = True
        else:
            artifacts.replacements[token_index] = encode(value, selected_depth)
        count += 1
    artifacts.number_count = count

def add_literal_masking(
    tokens: list[Token],
    analysis: Analysis,
    artifacts: BuildArtifacts,
    rng: random.Random,
) -> None:
    true_templates = ("(1==1)", "(0<1)", "(2~=3)")
    false_templates = ("(1==0)", "(0>1)", "(2~=2)")
    for token_index in sorted(analysis.runtime_booleans):
        token = tokens[token_index]
        choices = true_templates if token.text == "true" else false_templates
        artifacts.replacements[token_index] = rng.choice(choices)
        artifacts.boolean_count += 1
    for token_index in sorted(analysis.runtime_nil):
        key = rng.randint(17, 997)
        artifacts.replacements[token_index] = f"({{}})[{key}]"
        artifacts.nil_count += 1


def add_watermark(artifacts: BuildArtifacts, watermark: str | None, build_id: str, names: NameGenerator) -> None:
    if watermark is None:
        return
    digest = hashlib.blake2s((watermark + "\0" + build_id).encode("utf-8"), digest_size=8).digest()
    left = int.from_bytes(digest[:4], "big")
    right = int.from_bytes(digest[4:], "big")
    a = names.random_name(9)
    b = names.random_name(9)
    artifacts.helper_names.extend([a, b])
    artifacts.prelude_parts.append(f"do local {a},{b}={left},{right};{a}={a}+({b}-{b}) end;")


def add_noise(
    artifacts: BuildArtifacts,
    rng: random.Random,
    names: NameGenerator,
    level: int,
    *,
    opaque_predicates: bool = False,
) -> None:
    for _ in range(max(0, level)):
        a = names.random_name(7)
        b = names.random_name(7)
        x = rng.randint(-500_000, 500_000)
        y = rng.randint(-500_000, 500_000)
        artifacts.helper_names.extend([a, b])
        if opaque_predicates:
            artifacts.prelude_parts.append(
                f"do local {a},{b}={x},{y};if(({a}*{a}+{a})%2)==0 then {a}={a}+{b}-{b} else {a}={a}-{b}+{b} end end;"
            )
            artifacts.opaque_predicate_count += 1
        else:
            artifacts.prelude_parts.append(f"do local {a},{b}={x},{y};{a}={a}+{b}-{b} end;")


_MULTI_SYMBOLS = set(SYMBOLS)


def _needs_space(left: str, right: str) -> bool:
    if not left or not right:
        return False
    a = left[-1]
    b = right[0]
    if (a.isalnum() or a == "_") and (b.isalnum() or b == "_"):
        return True
    if a == "-" and b == "-":
        return True
    if a == "/" and b == "/":
        return True
    # Prevent token fusion after trivia removal.
    max_left = left[-3:]
    max_right = right[:3]
    for li in range(1, min(3, len(max_left)) + 1):
        for ri in range(1, min(3, len(max_right)) + 1):
            if max_left[-li:] + max_right[:ri] in _MULTI_SYMBOLS:
                if li == len(max_left[-li:]) and ri == len(max_right[:ri]):
                    return True
    if a.isdigit() and b == ".":
        return True
    return False


def minify_tokens(tokens: list[Token], replacements: dict[int, str]) -> tuple[str, list[str]]:
    directives: list[str] = []
    pieces: list[str] = []
    previous = ""
    for token in tokens:
        if token.kind == TokenKind.EOF:
            break
        if token.kind == TokenKind.WHITESPACE:
            continue
        if token.kind == TokenKind.COMMENT:
            if token.text.startswith("--!") and token.text not in directives:
                directives.append(token.text)
            continue
        text = replacements.get(token.index, token.text)
        if text == "":
            continue
        if previous and _needs_space(previous, text):
            pieces.append(" ")
        pieces.append(text)
        previous = text
    return "".join(pieces), directives


def render_tokens_preserving_trivia(tokens: list[Token], replacements: dict[int, str]) -> str:
    """Apply token replacements without deleting whitespace or comments.

    This compatibility renderer is intentionally larger, but avoids changing
    newline-sensitive or newly introduced Luau grammar outside transformed spans.
    """
    pieces: list[str] = []
    for token in tokens:
        if token.kind == TokenKind.EOF:
            break
        pieces.append(replacements.get(token.index, token.text))
    return "".join(pieces)


def minify_fragment(source: str) -> str:
    tokens = lex(source)
    result, _ = minify_tokens(tokens, {})
    return result


def build_manifest(
    *,
    input_bytes: bytes,
    output_bytes: bytes,
    build_id: str,
    seed: int,
    config: dict[str, object],
    analysis: Analysis | None,
    artifacts: BuildArtifacts,
    warnings: list[str],
) -> dict[str, object]:
    return {
        "tool": "O_bfuscate",
        "format": 2,
        "version": "1.0.0",
        "build_id": build_id,
        "seed": seed,
        "input_sha256": hashlib.sha256(input_bytes).hexdigest(),
        "output_sha256": hashlib.sha256(output_bytes).hexdigest(),
        "config": config,
        "stats": {
            "input_bytes": len(input_bytes),
            "output_bytes": len(output_bytes),
            "renamed_tokens": len(analysis.replacements) if analysis else 0,
            "encrypted_strings": artifacts.string_count,
            "split_numbers": artifacts.number_count,
            "encrypted_properties": artifacts.property_count,
            "string_chunks": artifacts.string_chunk_count,
            "masked_booleans": artifacts.boolean_count,
            "masked_nil": artifacts.nil_count,
            "opaque_predicates": artifacts.opaque_predicate_count,
            "string_vaults": artifacts.string_vault_count,
            "string_decoys": artifacts.string_decoy_count,
            "bitwise_numbers": artifacts.bitwise_number_count,
        },
        "warnings": warnings,
    }
