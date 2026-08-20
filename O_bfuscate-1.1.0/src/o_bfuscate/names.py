from __future__ import annotations

import random
import string


RESERVED = {
    "and", "break", "continue", "do", "else", "elseif", "end", "export", "false", "for",
    "function", "if", "in", "local", "nil", "not", "or", "repeat", "return", "then", "true",
    "type", "until", "while", "declare",
}


class NameGenerator:
    def __init__(self, rng: random.Random, used: set[str] | None = None) -> None:
        self.rng = rng
        self.used = set(used or ()) | RESERVED
        self.counter = 0
        self.first = "IlO_"
        self.rest = "IlO_01"

    def next(self, prefix: str = "") -> str:
        while True:
            n = self.counter
            self.counter += 1
            chars = []
            chars.append(self.first[n % len(self.first)])
            n //= len(self.first)
            while n:
                chars.append(self.rest[n % len(self.rest)])
                n //= len(self.rest)
            candidate = prefix + "".join(chars)
            if candidate not in self.used:
                self.used.add(candidate)
                return candidate

    def random_name(self, length: int = 10) -> str:
        while True:
            candidate = "_" + "".join(self.rng.choice(string.ascii_letters + string.digits) for _ in range(length))
            if candidate not in self.used:
                self.used.add(candidate)
                return candidate
