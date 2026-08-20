from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import hmac
import math
import random
import re
from typing import Any, Callable

from .lexer import Token, TokenKind, lex
from .macros import FunctionPolicy
from .names import NameGenerator


class VMCompileError(ValueError):
    pass


OPS = (
    "K", "GET", "SET", "GLOBAL", "SETGLOBAL", "MOVE", "UNARY", "BINARY",
    "GETIDX", "SETIDX", "CALL", "MCALL", "TCALL", "TMCALL", "JMP",
    "JFALSE", "RETURN", "RETURNPACK", "RETURNVARARG", "NEWTABLE",
    "FORCHECK", "FORSTEP", "ITERPREP", "ITERNEXTG", "UPGET", "UPSET",
    "CLOSURE", "VARARG", "VARARGN", "K2", "MOVE2", "NOP",
)


@dataclass(slots=True)
class FunctionSpec:
    name: str
    params: list[str]
    vararg: bool
    body: list[Token]
    start: int
    end: int
    line: int
    declaration_style: str = "declaration"
    scope_start: int = 0
    policy: FunctionPolicy = field(default_factory=FunctionPolicy)


@dataclass(slots=True)
class Prototype:
    index: int
    name: str
    params: list[str]
    vararg: bool
    code: list[list[Any]]
    lines: list[int]
    constants: list[Any]
    globals: set[str]
    max_register: int
    upvalue_names: list[str]
    capture_plan: list[tuple[int, int]]
    written_upvalues: set[int]
    source_map: bool
    integrity: bool
    optimize: bool
    protection_mode: str
    key_id: str | None
    key_scope: str


@dataclass(slots=True)
class VMBuild:
    replacements: list[tuple[int, int, str]] = field(default_factory=list)
    prelude: str = ""
    virtualized_functions: int = 0
    virtualized_prototypes: int = 0
    instruction_count: int = 0
    constant_count: int = 0
    encrypted_constant_bytes: int = 0
    captured_upvalues: int = 0
    writable_upvalues: int = 0
    iterator_loops: int = 0
    nested_closures: int = 0
    vararg_functions: int = 0
    optimized_instructions: int = 0
    superinstructions: int = 0
    integrity_checks: int = 0
    source_mapped_functions: int = 0
    externally_keyed_functions: int = 0
    plain_code_bytes: int = 0
    packed_code_bytes: int = 0
    compressed_functions: int = 0
    light_functions: int = 0
    full_functions: int = 0
    vm_architecture: str = "linear"
    warnings: list[str] = field(default_factory=list)


class PrototypeRegistry:
    def __init__(self) -> None:
        self.items: list[Prototype | None] = []

    def reserve(self) -> int:
        self.items.append(None)
        return len(self.items)

    def put(self, prototype: Prototype) -> None:
        self.items[prototype.index - 1] = prototype

    def resolved(self) -> list[Prototype]:
        if any(item is None for item in self.items):
            raise VMCompileError("internal unresolved VM prototype")
        return [item for item in self.items if item is not None]


@dataclass(slots=True)
class LValue:
    kind: str
    slot: int = 0
    name: str = ""
    base: int = 0
    key: int = 0


class FunctionCompiler:
    def __init__(
        self,
        tokens: list[Token],
        source: str,
        name: str,
        params: list[str],
        vararg: bool,
        registry: PrototypeRegistry,
        prototype_index: int,
        *,
        parent: FunctionCompiler | None = None,
        external_names: set[str] | None = None,
        source_map: bool = True,
        integrity: bool = True,
        optimize: bool = True,
        protection_mode: str = "full",
        key_id: str | None = None,
        key_scope: str | None = None,
    ) -> None:
        self.t = tokens
        self.source = source
        self.p = 0
        self.name = name
        self.params = params
        self.vararg = vararg
        self.registry = registry
        self.prototype_index = prototype_index
        self.parent = parent
        self.external_names = external_names or set()
        self.source_map = source_map
        self.integrity = integrity
        self.optimize = optimize
        self.protection_mode = protection_mode
        self.key_id = key_id
        self.key_scope = key_scope or name
        self.code: list[list[Any]] = []
        self.lines: list[int] = []
        self.current_line = tokens[0].line if tokens else 1
        self.constants: list[Any] = []
        self.constant_map: dict[tuple[type, Any], int] = {}
        self.locals: dict[str, int] = {n: i + 1 for i, n in enumerate(params)}
        self.scope_stack: list[list[tuple[str, int | None]]] = [[(n, None) for n in params]]
        self.loop_stack: list[dict[str, list[int]]] = []
        self.globals: set[str] = set()
        self.upvalues: dict[str, int] = {}
        self.upvalue_names: list[str] = []
        self.capture_plan: list[tuple[int, int]] = []
        self.written_upvalues: set[int] = set()
        self.next_reg = len(params) + 1
        self.max_reg = len(params)
        self.call_results: dict[int, int] = {}
        self.vararg_results: dict[int, int] = {}

    def cur(self) -> Token:
        if self.p >= len(self.t):
            return Token(TokenKind.EOF, "", 0, 0, 0, self.current_line)
        return self.t[self.p]

    def at(self, text: str) -> bool:
        return self.cur().text == text

    def take(self, text: str | None = None) -> Token:
        tok = self.cur()
        if text is not None and tok.text != text:
            raise VMCompileError(f"expected {text!r} near {tok.text!r}")
        self.p += 1
        if tok.line:
            self.current_line = tok.line
        return tok

    def accept(self, text: str) -> bool:
        if self.at(text):
            self.take()
            return True
        return False

    def push_scope(self) -> None:
        self.scope_stack.append([])

    def pop_scope(self) -> None:
        if len(self.scope_stack) <= 1:
            raise VMCompileError("cannot pop function scope")
        for name, previous in reversed(self.scope_stack.pop()):
            if previous is None:
                self.locals.pop(name, None)
            else:
                self.locals[name] = previous

    def declare_local(self, name: str, slot: int) -> None:
        previous = self.locals.get(name)
        self.scope_stack[-1].append((name, previous))
        self.locals[name] = slot

    def reg(self, count: int = 1) -> int:
        r = self.next_reg
        self.next_reg += count
        self.max_reg = max(self.max_reg, self.next_reg - 1)
        return r

    def emit(self, op: str, *args: Any, line: int | None = None) -> int:
        self.code.append([op, *args])
        self.lines.append(self.current_line if line is None else line)
        return len(self.code) - 1

    def patch(self, at: int, target: int) -> None:
        self.code[at][-1] = target + 1

    def const(self, value: Any) -> int:
        key = (type(value), value)
        if key not in self.constant_map:
            self.constant_map[key] = len(self.constants) + 1
            self.constants.append(value)
        return self.constant_map[key]

    def decode_string(self, text: str) -> str:
        from .transforms import decode_luau_string
        return decode_luau_string(text).decode("utf-8")

    def capture_descriptor(self, name: str) -> tuple[int, int] | None:
        if name in self.locals:
            return (0, self.locals[name])
        if name in self.upvalues:
            return (1, self.upvalues[name])
        if self.parent is None and name in self.external_names:
            index = self.ensure_upvalue(name, (2, 0))
            return (1, index)
        if self.parent is not None:
            parent_desc = self.parent.capture_descriptor(name)
            if parent_desc is not None:
                index = self.ensure_upvalue(name, parent_desc)
                return (1, index)
        return None

    def ensure_upvalue(self, name: str, descriptor: tuple[int, int] | None = None) -> int:
        if name in self.upvalues:
            return self.upvalues[name]
        if descriptor is None:
            if self.parent is not None:
                descriptor = self.parent.capture_descriptor(name)
            elif name in self.external_names:
                descriptor = (2, 0)
        if descriptor is None:
            raise VMCompileError(f"unresolved upvalue {name!r}")
        index = len(self.upvalue_names) + 1
        self.upvalues[name] = index
        self.upvalue_names.append(name)
        self.capture_plan.append(descriptor)
        return index

    def read_name(self, name: str) -> int:
        out = self.reg()
        if name in self.locals:
            self.emit("GET", out, self.locals[name])
            return out
        descriptor = self.capture_descriptor(name)
        if descriptor is not None:
            up = self.ensure_upvalue(name, descriptor)
            self.emit("UPGET", out, up)
            return out
        self.globals.add(name)
        self.emit("GLOBAL", out, self.const(name))
        return out

    def write_name(self, name: str, source_reg: int) -> None:
        if name in self.locals:
            self.emit("MOVE", self.locals[name], source_reg)
            return
        descriptor = self.capture_descriptor(name)
        if descriptor is not None:
            up = self.ensure_upvalue(name, descriptor)
            self.written_upvalues.add(up)
            self.emit("UPSET", up, source_reg)
            return
        self.globals.add(name)
        self.emit("SETGLOBAL", self.const(name), source_reg)

    def compile(self) -> Prototype:
        self.block({""})
        if self.cur().kind != TokenKind.EOF:
            raise VMCompileError(f"unsupported trailing token {self.cur().text!r}")
        if not self.code or self.code[-1][0] not in {"RETURN", "RETURNPACK", "RETURNVARARG", "TCALL", "TMCALL"}:
            self.emit("RETURN", 0, 0)
        prototype = Prototype(
            index=self.prototype_index,
            name=self.name,
            params=self.params,
            vararg=self.vararg,
            code=self.code,
            lines=self.lines,
            constants=self.constants,
            globals=self.globals,
            max_register=self.max_reg,
            upvalue_names=self.upvalue_names,
            capture_plan=self.capture_plan,
            written_upvalues=self.written_upvalues,
            source_map=self.source_map,
            integrity=self.integrity,
            optimize=self.optimize,
            protection_mode=self.protection_mode,
            key_id=self.key_id,
            key_scope=self.key_scope,
        )
        self.registry.put(prototype)
        return prototype

    def block(self, stops: set[str], *, scoped: bool = False) -> None:
        if scoped:
            self.push_scope()
        try:
            while self.cur().kind != TokenKind.EOF and self.cur().text not in stops:
                self.statement()
                self.accept(";")
        finally:
            if scoped:
                self.pop_scope()

    def _assignment_position(self) -> int | None:
        depth = 0
        i = self.p
        while i < len(self.t):
            text = self.t[i].text
            if depth == 0 and text in {"(", ":"}:
                # Function and method calls are expression statements. Without
                # this boundary a later statement's '=' can be misread as part
                # of the current lvalue when the source omits semicolons.
                return None
            if text in {"(", "[", "{"}:
                depth += 1
            elif text in {")", "]", "}"}:
                depth = max(0, depth - 1)
            elif depth == 0 and text in {"=", "+=", "-=", "*=", "/=", "//=", "%=", "^=", "..=", "<<=", ">>="}:
                return i
            elif depth == 0 and text in {";", "end", "else", "elseif", "until"}:
                return None
            i += 1
        return None

    def compile_lvalue(self, stop_tokens: set[str]) -> LValue:
        token = self.take()
        if token.kind != TokenKind.IDENT:
            raise VMCompileError("assignment target must start with an identifier")
        name = token.text
        if self.cur().text in stop_tokens:
            if name in self.locals:
                return LValue("local", slot=self.locals[name], name=name)
            descriptor = self.capture_descriptor(name)
            if descriptor is not None:
                return LValue("upvalue", slot=self.ensure_upvalue(name, descriptor), name=name)
            return LValue("global", name=name)
        base = self.read_name(name)
        final_key = 0
        while True:
            if self.accept("."):
                key = self.take()
                if key.kind != TokenKind.IDENT:
                    raise VMCompileError("expected property name")
                final_key = self.const(key.text)
            elif self.accept("["):
                key_reg = self.expr()
                self.take("]")
                final_key = -key_reg
            else:
                break
            if self.cur().text not in stop_tokens:
                next_base = self.reg()
                self.emit("GETIDX", next_base, base, final_key)
                base = next_base
        if self.cur().text not in stop_tokens or final_key == 0:
            raise VMCompileError(f"unsupported assignment target near {self.cur().text!r} after {name!r}")
        return LValue("index", base=base, key=final_key)

    def read_lvalue(self, target: LValue) -> int:
        if target.kind == "local":
            out = self.reg(); self.emit("GET", out, target.slot); return out
        if target.kind == "upvalue":
            out = self.reg(); self.emit("UPGET", out, target.slot); return out
        if target.kind == "global":
            self.globals.add(target.name)
            out = self.reg(); self.emit("GLOBAL", out, self.const(target.name)); return out
        out = self.reg(); self.emit("GETIDX", out, target.base, target.key); return out

    def write_lvalue(self, target: LValue, value: int) -> None:
        if target.kind == "local":
            self.emit("MOVE", target.slot, value)
        elif target.kind == "upvalue":
            self.written_upvalues.add(target.slot)
            self.emit("UPSET", target.slot, value)
        elif target.kind == "global":
            self.globals.add(target.name)
            self.emit("SETGLOBAL", self.const(target.name), value)
        else:
            self.emit("SETIDX", target.base, target.key, value)

    def expr_list(self, expected: int | None = None) -> list[int]:
        regs = [self.expr()]
        while self.accept(","):
            regs.append(self.expr())
        if expected is not None:
            remaining = expected - len(regs) + 1
            last = regs[-1]
            if remaining > 1 and self.expand_multi(last, remaining):
                regs.extend(last + offset for offset in range(1, remaining))
            while len(regs) < expected:
                nilreg = self.reg(); self.emit("K", nilreg, self.const(None)); regs.append(nilreg)
            regs = regs[:expected]
        return regs

    def expand_multi(self, register: int, count: int) -> bool:
        call_at = self.call_results.get(register)
        if call_at is not None:
            instruction = self.code[call_at]
            if instruction[0] in {"CALL", "MCALL"}:
                instruction[-2 if instruction[0] == "CALL" else -2] = count
                self.next_reg = max(self.next_reg, register + count)
                self.max_reg = max(self.max_reg, register + count - 1)
                return True
        vararg_at = self.vararg_results.get(register)
        if vararg_at is not None:
            self.code[vararg_at] = ["VARARGN", register, count]
            self.next_reg = max(self.next_reg, register + count)
            self.max_reg = max(self.max_reg, register + count - 1)
            return True
        return False

    def statement(self) -> None:
        if self.accept("local"):
            if self.accept("function"):
                name_token = self.take()
                if name_token.kind != TokenKind.IDENT:
                    raise VMCompileError("expected local function name")
                slot = self.reg()
                self.declare_local(name_token.text, slot)
                child = self.compile_nested_function(name_token.text, function_already_taken=True)
                self.emit("CLOSURE", slot, child)
                return
            names: list[str] = []
            while True:
                token = self.take()
                if token.kind != TokenKind.IDENT:
                    raise VMCompileError("expected local name")
                names.append(token.text)
                if self.accept(":"):
                    self.skip_type({",", "="})
                if not self.accept(","):
                    break
            values: list[int] = []
            if self.accept("="):
                values = self.expr_list(expected=len(names))
            for i, name in enumerate(names):
                slot = self.reg()
                self.declare_local(name, slot)
                if i < len(values):
                    self.emit("MOVE", slot, values[i])
                else:
                    self.emit("K", slot, self.const(None))
            return

        if self.accept("function"):
            target = self.compile_lvalue({"("})
            child_name = target.name or f"{self.name}$fn"
            child = self.compile_nested_function(child_name, function_already_taken=True)
            closure = self.reg(); self.emit("CLOSURE", closure, child)
            self.write_lvalue(target, closure)
            return

        if self.accept("return"):
            if self.cur().kind == TokenKind.EOF or self.cur().text in {"end", "else", "elseif", "until", ";"}:
                self.emit("RETURN", 0, 0)
                return
            if self.at("..."):
                self.take("...")
                self.emit("RETURNVARARG", 0, 0)
                return
            regs = [self.expr()]
            while self.accept(","):
                if self.at("..."):
                    self.take("...")
                    base = self.reg(len(regs))
                    for offset, reg in enumerate(regs):
                        self.emit("MOVE", base + offset, reg)
                    self.emit("RETURNVARARG", base, len(regs))
                    return
                regs.append(self.expr())
            last = regs[-1]
            call_at = self.call_results.get(last)
            if len(regs) == 1 and call_at is not None:
                inst = self.code[call_at]
                if inst[0] == "CALL":
                    self.code[call_at] = ["TCALL", inst[2], inst[3], inst[4], inst[6]]
                    return
                if inst[0] == "MCALL":
                    self.code[call_at] = ["TMCALL", inst[2], inst[3], inst[4], inst[5], inst[7]]
                    return
            if call_at is not None and len(regs) > 1:
                inst = self.code[call_at]
                if inst[0] in {"CALL", "MCALL"}:
                    inst[-2] = 0
                    base = self.reg(len(regs) - 1)
                    for offset, reg in enumerate(regs[:-1]):
                        self.emit("MOVE", base + offset, reg)
                    self.emit("RETURNPACK", base, len(regs) - 1, last)
                    return
            base = self.reg(len(regs))
            for offset, reg in enumerate(regs):
                self.emit("MOVE", base + offset, reg)
            self.emit("RETURN", base, len(regs))
            return

        if self.accept("break"):
            if not self.loop_stack:
                raise VMCompileError("break outside loop")
            self.loop_stack[-1]["breaks"].append(self.emit("JMP", 0))
            return
        if self.accept("continue"):
            if not self.loop_stack:
                raise VMCompileError("continue outside loop")
            self.loop_stack[-1]["continues"].append(self.emit("JMP", 0))
            return
        if self.accept("do"):
            self.block({"end"}, scoped=True); self.take("end"); return
        if self.accept("if"):
            self.compile_if_statement(); return
        if self.accept("while"):
            self.compile_while(); return
        if self.accept("repeat"):
            self.compile_repeat(); return
        if self.accept("for"):
            self.compile_for(); return
        if self.at("type") and self.p + 1 < len(self.t) and self.t[self.p + 1].kind == TokenKind.IDENT:
            self.take("type")
            self.skip_type_declaration()
            return
        if self.accept("export"):
            self.take("type")
            self.skip_type_declaration()
            return
        if self.cur().text == "declare":
            raise VMCompileError("declare statements are not valid inside virtualized runtime functions")

        assignment_at = self._assignment_position()
        if assignment_at is not None:
            targets: list[LValue] = []
            while self.p < assignment_at:
                targets.append(self.compile_lvalue({",", self.t[assignment_at].text}))
                if not self.accept(","):
                    break
            op = self.take().text
            if op != "=" and len(targets) != 1:
                raise VMCompileError("compound assignment requires one target")
            if op == "=":
                values = self.expr_list(expected=len(targets))
                for target, value in zip(targets, values):
                    self.write_lvalue(target, value)
            else:
                left = self.read_lvalue(targets[0])
                right = self.expr()
                value = self.reg(); self.emit("BINARY", value, self.const(op[:-1]), left, right)
                self.write_lvalue(targets[0], value)
            return

        self.expr()

    def compile_if_statement(self) -> None:
        cond = self.expr(); self.take("then")
        jf = self.emit("JFALSE", cond, 0)
        self.block({"elseif", "else", "end"}, scoped=True)
        exits: list[int] = []
        while self.accept("elseif"):
            exits.append(self.emit("JMP", 0)); self.patch(jf, len(self.code))
            cond = self.expr(); self.take("then")
            jf = self.emit("JFALSE", cond, 0)
            self.block({"elseif", "else", "end"}, scoped=True)
        if self.accept("else"):
            exits.append(self.emit("JMP", 0)); self.patch(jf, len(self.code)); jf = -1
            self.block({"end"}, scoped=True)
        self.take("end")
        if jf >= 0:
            self.patch(jf, len(self.code))
        for jump in exits:
            self.patch(jump, len(self.code))

    def compile_while(self) -> None:
        top = len(self.code)
        cond = self.expr(); self.take("do")
        jf = self.emit("JFALSE", cond, 0)
        loop = {"breaks": [], "continues": []}; self.loop_stack.append(loop)
        self.block({"end"}, scoped=True); self.take("end"); self.loop_stack.pop()
        for jump in loop["continues"]:
            self.patch(jump, top)
        self.emit("JMP", top + 1)
        exit_target = len(self.code); self.patch(jf, exit_target)
        for jump in loop["breaks"]:
            self.patch(jump, exit_target)

    def compile_repeat(self) -> None:
        top = len(self.code); self.push_scope()
        loop = {"breaks": [], "continues": []}; self.loop_stack.append(loop)
        try:
            self.block({"until"}); self.take("until")
            continue_target = len(self.code)
            for jump in loop["continues"]:
                self.patch(jump, continue_target)
            cond = self.expr(); self.emit("JFALSE", cond, top + 1)
        finally:
            self.loop_stack.pop(); self.pop_scope()
        exit_target = len(self.code)
        for jump in loop["breaks"]:
            self.patch(jump, exit_target)

    def compile_for(self) -> None:
        loop_names = [self.take().text]
        while self.accept(","):
            loop_names.append(self.take().text)
        if any(not name or not (name[0].isalpha() or name[0] == "_") for name in loop_names):
            raise VMCompileError("expected for-loop variable")
        if self.accept("="):
            if len(loop_names) != 1:
                raise VMCompileError("numeric for loops have one control variable")
            initial = self.expr(); self.take(","); limit = self.expr()
            if self.accept(","):
                step = self.expr()
            else:
                step = self.reg(); self.emit("K", step, self.const(1))
            self.take("do")
            slot = self.reg(); self.emit("MOVE", slot, initial)
            loop_top = len(self.code)
            check = self.emit("FORCHECK", slot, limit, step, 0)
            self.push_scope(); self.declare_local(loop_names[0], slot)
            loop = {"breaks": [], "continues": []}; self.loop_stack.append(loop)
            try:
                self.block({"end"}); self.take("end")
                continue_target = len(self.code)
                for jump in loop["continues"]:
                    self.patch(jump, continue_target)
                self.emit("FORSTEP", slot, step, loop_top + 1)
            finally:
                self.loop_stack.pop(); self.pop_scope()
            exit_target = len(self.code); self.patch(check, exit_target)
            for jump in loop["breaks"]:
                self.patch(jump, exit_target)
            return

        self.take("in")
        iterator_values = self.expr_list(expected=3)
        self.take("do")
        fn, state, control = iterator_values
        self.emit("ITERPREP", fn, state, control)
        slots_base = self.reg(max(1, len(loop_names)))
        loop_top = len(self.code)
        iterate = self.emit("ITERNEXTG", fn, state, control, slots_base, len(loop_names), 0)
        self.push_scope()
        for offset, loop_name in enumerate(loop_names):
            self.declare_local(loop_name, slots_base + offset)
        loop = {"breaks": [], "continues": []}; self.loop_stack.append(loop)
        try:
            self.block({"end"}); self.take("end")
            for jump in loop["continues"]:
                self.patch(jump, loop_top)
            self.emit("JMP", loop_top + 1)
        finally:
            self.loop_stack.pop(); self.pop_scope()
        exit_target = len(self.code); self.patch(iterate, exit_target)
        for jump in loop["breaks"]:
            self.patch(jump, exit_target)

    PRECEDENCE = {
        "or": 1, "and": 2, "<": 3, ">": 3, "<=": 3, ">=": 3, "~=": 3, "==": 3,
        "|": 4, "~": 5, "&": 6, "<<": 7, ">>": 7, "..": 8, "+": 9, "-": 9,
        "*": 10, "/": 10, "//": 10, "%": 10, "^": 12,
    }

    def expr(self, minimum: int = 0) -> int:
        if self.cur().text in {"not", "-", "#", "~"}:
            op = self.take().text; src = self.expr(11)
            out = self.reg(); self.emit("UNARY", out, self.const(op), src)
        else:
            out = self.primary()
        while self.cur().text in self.PRECEDENCE and self.PRECEDENCE[self.cur().text] >= minimum:
            op = self.take().text; prec = self.PRECEDENCE[op]
            if op == "and":
                dst = self.reg(); self.emit("MOVE", dst, out)
                skip = self.emit("JFALSE", out, 0)
                rhs = self.expr(prec + 1); self.emit("MOVE", dst, rhs)
                self.patch(skip, len(self.code)); out = dst; continue
            if op == "or":
                dst = self.reg(); self.emit("MOVE", dst, out)
                rhs_jump = self.emit("JFALSE", out, 0); done = self.emit("JMP", 0)
                self.patch(rhs_jump, len(self.code)); rhs = self.expr(prec + 1)
                self.emit("MOVE", dst, rhs); self.patch(done, len(self.code)); out = dst; continue
            rhs = self.expr(prec if op in {"^", ".."} else prec + 1)
            dst = self.reg(); self.emit("BINARY", dst, self.const(op), out, rhs); out = dst
        return out

    def _interpolation_parts(self, text: str) -> list[tuple[bool, str]]:
        body = text[1:-1]
        parts: list[tuple[bool, str]] = []
        literal: list[str] = []
        i = 0
        while i < len(body):
            if body[i] == "\\" and i + 1 < len(body):
                literal.append(body[i:i + 2]); i += 2; continue
            if body[i] != "{":
                literal.append(body[i]); i += 1; continue
            if literal:
                parts.append((False, "".join(literal))); literal.clear()
            depth = 1; start = i + 1; i += 1
            quote: str | None = None
            escaped = False
            while i < len(body) and depth:
                ch = body[i]
                if quote:
                    if escaped:
                        escaped = False
                    elif ch == "\\":
                        escaped = True
                    elif ch == quote:
                        quote = None
                else:
                    if ch in {"'", '"', "`"}:
                        quote = ch
                    elif ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            break
                i += 1
            if depth:
                raise VMCompileError("unterminated interpolated expression")
            parts.append((True, body[start:i])); i += 1
        if literal:
            parts.append((False, "".join(literal)))
        return parts

    def compile_expression_fragment(self, source: str) -> int:
        fragment = [token for token in lex(source) if token.significant]
        if not fragment or fragment[-1].kind != TokenKind.EOF:
            fragment.append(Token(TokenKind.EOF, "", 0, 0, 0, self.current_line))
        old_tokens, old_position = self.t, self.p
        self.t, self.p = fragment, 0
        try:
            result = self.expr()
            if self.cur().kind != TokenKind.EOF:
                raise VMCompileError(f"unsupported interpolation expression near {self.cur().text!r}")
            return result
        finally:
            self.t, self.p = old_tokens, old_position

    def compile_interpolation(self, text: str) -> int:
        parts: list[int] = []
        for expression, value in self._interpolation_parts(text):
            if not expression:
                if value:
                    reg = self.reg(); self.emit("K", reg, self.const(value)); parts.append(reg)
                continue
            rendered_value = self.compile_expression_fragment(value)
            fn = self.read_name("tostring")
            base = self.reg(); self.emit("MOVE", base, rendered_value)
            rendered = self.reg(); at = self.emit("CALL", rendered, fn, base, 1, 1, 0)
            self.call_results[rendered] = at; parts.append(rendered)
        if not parts:
            out = self.reg(); self.emit("K", out, self.const("")); return out
        out = parts[0]
        for part in parts[1:]:
            dst = self.reg(); self.emit("BINARY", dst, self.const(".."), out, part); out = dst
        return out

    def compile_if_expression(self) -> int:
        cond = self.expr(); self.take("then"); out = self.reg()
        false_jump = self.emit("JFALSE", cond, 0)
        yes = self.expr(); self.emit("MOVE", out, yes)
        done = self.emit("JMP", 0); self.patch(false_jump, len(self.code))
        if self.accept("elseif"):
            no = self.compile_if_expression()
        else:
            self.take("else"); no = self.expr()
        self.emit("MOVE", out, no); self.patch(done, len(self.code)); return out

    def parse_call_args(self) -> tuple[list[int], bool]:
        args: list[int] = []
        has_vararg = False
        if not self.at(")"):
            while True:
                if self.at("..."):
                    self.take("..."); has_vararg = True
                    if self.at(","):
                        raise VMCompileError("vararg expansion must be the final argument")
                    break
                args.append(self.expr())
                if not self.accept(","):
                    break
        self.take(")")
        return args, has_vararg

    def primary(self) -> int:
        tok = self.take()
        if tok.kind == TokenKind.NUMBER:
            text = tok.text.replace("_", "")
            if text.lower().startswith("0x"):
                value: int | float = int(text, 16)
            elif text.lower().startswith("0b"):
                value = int(text, 2)
            else:
                value = float(text) if any(c in text for c in ".eE") else int(text)
            if isinstance(value, float) and not math.isfinite(value):
                raise VMCompileError("non-finite numeric constant is not virtualized")
            out = self.reg(); self.emit("K", out, self.const(value))
        elif tok.kind == TokenKind.STRING:
            out = self.reg(); self.emit("K", out, self.const(self.decode_string(tok.text)))
        elif tok.kind == TokenKind.INTERP_STRING:
            out = self.compile_interpolation(tok.text)
        elif tok.text == "if":
            out = self.compile_if_expression()
        elif tok.text in {"nil", "true", "false"}:
            out = self.reg(); self.emit("K", out, self.const({"nil": None, "true": True, "false": False}[tok.text]))
        elif tok.text == "...":
            if not self.vararg:
                raise VMCompileError("vararg used outside a vararg function")
            out = self.reg(); at = self.emit("VARARG", out, 1); self.vararg_results[out] = at
        elif tok.text == "function":
            child = self.compile_nested_function(f"{self.name}$closure", function_already_taken=True)
            out = self.reg(); self.emit("CLOSURE", out, child)
        elif tok.text == "(":
            out = self.expr(); self.take(")")
        elif tok.text == "{":
            out = self.table_constructor()
        elif tok.kind == TokenKind.IDENT or tok.text == "type":
            out = self.read_name(tok.text)
        else:
            raise VMCompileError(f"unsupported expression near {tok.text!r}")

        while True:
            if self.accept("."):
                key = self.take()
                if key.kind != TokenKind.IDENT:
                    raise VMCompileError("expected property name")
                dst = self.reg(); self.emit("GETIDX", dst, out, self.const(key.text)); out = dst
            elif self.accept("["):
                keyreg = self.expr(); self.take("]")
                dst = self.reg(); self.emit("GETIDX", dst, out, -keyreg); out = dst
            elif self.accept(":"):
                method = self.take().text; self.take("(")
                args, has_vararg = self.parse_call_args()
                base = self.reg(max(1, len(args)))
                for offset, arg in enumerate(args): self.emit("MOVE", base + offset, arg)
                dst = self.reg(); at = self.emit("MCALL", dst, out, self.const(method), base, len(args), 1, 1 if has_vararg else 0)
                self.call_results[dst] = at; out = dst
            elif self.accept("("):
                args, has_vararg = self.parse_call_args()
                base = self.reg(max(1, len(args)))
                for offset, arg in enumerate(args): self.emit("MOVE", base + offset, arg)
                dst = self.reg(); at = self.emit("CALL", dst, out, base, len(args), 1, 1 if has_vararg else 0)
                self.call_results[dst] = at; out = dst
            elif self.accept("::"):
                self.skip_cast_type()
            else:
                break
        return out

    def table_constructor(self) -> int:
        out = self.reg(); self.emit("NEWTABLE", out); array_index = 1
        while not self.at("}"):
            if self.accept("["):
                key = self.expr(); self.take("]"); self.take("="); value = self.expr()
                self.emit("SETIDX", out, -key, value)
            elif self.cur().kind == TokenKind.IDENT and self.p + 1 < len(self.t) and self.t[self.p + 1].text == "=":
                key = self.take().text; self.take("="); value = self.expr()
                self.emit("SETIDX", out, self.const(key), value)
            else:
                value = self.expr(); self.emit("SETIDX", out, self.const(array_index), value); array_index += 1
            if not (self.accept(",") or self.accept(";")):
                break
        self.take("}"); return out

    def compile_nested_function(self, name: str, *, function_already_taken: bool) -> int:
        if not function_already_taken:
            self.take("function")
        if self.accept("<"):
            depth = 1
            while depth and self.cur().kind != TokenKind.EOF:
                if self.accept("<"): depth += 1
                elif self.accept(">"): depth -= 1
                else: self.take()
        self.take("(")
        params: list[str] = []
        vararg = False
        while not self.at(")"):
            if self.accept("..."):
                vararg = True
                if self.accept(":"):
                    self.skip_type({",", ")"})
            else:
                token = self.take()
                if token.kind != TokenKind.IDENT:
                    raise VMCompileError("expected function parameter")
                params.append(token.text)
                if self.accept(":"):
                    self.skip_type({",", ")"})
            if not self.accept(","):
                break
        self.take(")")
        if self.accept(":"):
            self.skip_return_type()
        body_start = self.p
        end_index = _matching_function_end(self.t, body_start, self.source)
        end_token = self.t[end_index]
        child_tokens = self.t[body_start:end_index] + [Token(TokenKind.EOF, "", end_token.start, end_token.start, 0, end_token.line)]
        child_index = self.registry.reserve()
        child = FunctionCompiler(
            child_tokens, self.source, name, params, vararg, self.registry, child_index,
            parent=self,
            source_map=self.source_map,
            integrity=self.integrity,
            optimize=self.optimize,
            protection_mode=self.protection_mode,
            key_id=self.key_id,
            key_scope=self.key_scope,
        )
        child.compile()
        self.p = end_index + 1
        return child_index

    def skip_cast_type(self) -> None:
        depth = 0
        stops = {".", "[", ":", "(", ",", ")", "]", "}", ";", "then", "do", "end", "else", "elseif", "until"}
        stops.update(self.PRECEDENCE)
        while self.cur().kind != TokenKind.EOF:
            text = self.cur().text
            if depth == 0 and text in stops:
                return
            if text in {"(", "{", "[", "<"}: depth += 1
            elif text in {")", "}", "]", ">"}:
                if depth == 0:
                    return
                depth -= 1
            self.take()

    def skip_type_declaration(self) -> None:
        starters = {"local", "function", "if", "while", "repeat", "for", "do", "return", "break", "continue", "type", "export", "end", "else", "elseif", "until"}
        depth = 0
        seen_equals = False
        while self.cur().kind != TokenKind.EOF:
            text = self.cur().text
            if text == ";" and depth == 0:
                self.take(); return
            if seen_equals and depth == 0 and text in starters:
                return
            if text == "=" and depth == 0:
                seen_equals = True
            elif text in {"(", "{", "[", "<"}: depth += 1
            elif text in {")", "}", "]", ">"}: depth = max(0, depth - 1)
            self.take()

    def skip_return_type(self) -> None:
        depth = 0
        starters = {"local", "function", "if", "while", "repeat", "for", "do", "return", "break", "continue", "end"}
        while self.cur().kind != TokenKind.EOF:
            text = self.cur().text
            if depth == 0 and text in starters:
                return
            if text in {"(", "{", "[", "<"}: depth += 1
            elif text in {")", "}", "]", ">"}: depth = max(0, depth - 1)
            self.take()

    def skip_type(self, stops: set[str]) -> None:
        depth = 0
        while self.cur().kind != TokenKind.EOF:
            if depth == 0 and self.cur().text in stops:
                return
            if self.cur().text in {"(", "{", "[", "<"}: depth += 1
            elif self.cur().text in {")", "}", "]", ">"}: depth = max(0, depth - 1)
            self.take()


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
        "return", "=", ",", "(", "[", "{", ":", "and", "or", "+", "-", "*",
        "/", "//", "%", "^", "..", "<", ">", "<=", ">=", "==", "~=", "~", "&",
        "|", "<<", ">>", "not",
    }


def _matching_function_end(tokens: list[Token], body_start: int, source: str) -> int:
    block = 1
    pending_loop_do = 0
    i = body_start
    while i < len(tokens):
        text = tokens[i].text
        if text == "function":
            block += 1
        elif text == "if" and not _is_expression_if(tokens, i, source, body_start):
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
    raise VMCompileError("unterminated nested function")


def _skip_type_tokens(tokens: list[Token], position: int, stops: set[str]) -> int:
    depth = 0
    while position < len(tokens):
        text = tokens[position].text
        if depth == 0 and text in stops:
            return position
        if text in {"(", "{", "[", "<"}: depth += 1
        elif text in {")", "}", "]", ">"}: depth = max(0, depth - 1)
        position += 1
    return position


def _parse_top_level_function_spec(
    tokens: list[Token],
    source: str,
    *,
    local_index: int,
    name_token: Token,
    signature_index: int,
    declaration_style: str,
    policy: FunctionPolicy,
) -> tuple[FunctionSpec, int]:
    name = name_token.text
    j = signature_index
    if j < len(tokens) and tokens[j].text == "<":
        generic_depth = 1
        j += 1
        while j < len(tokens) and generic_depth:
            if tokens[j].text == "<":
                generic_depth += 1
            elif tokens[j].text == ">":
                generic_depth -= 1
            j += 1
    if j >= len(tokens) or tokens[j].text != "(":
        raise VMCompileError(f"invalid parameter list for function {name}")
    j += 1
    params: list[str] = []
    vararg = False
    while j < len(tokens) and tokens[j].text != ")":
        if tokens[j].text == "...":
            vararg = True
            j += 1
            if j < len(tokens) and tokens[j].text == ":":
                j = _skip_type_tokens(tokens, j + 1, {",", ")"})
        else:
            if tokens[j].kind != TokenKind.IDENT:
                raise VMCompileError(f"invalid parameter in function {name}")
            params.append(tokens[j].text)
            j += 1
            if j < len(tokens) and tokens[j].text == ":":
                j = _skip_type_tokens(tokens, j + 1, {",", ")"})
        if j < len(tokens) and tokens[j].text == ",":
            j += 1
    if j >= len(tokens):
        raise VMCompileError(f"unterminated parameter list for {name}")
    j += 1
    if j < len(tokens) and tokens[j].text == ":":
        j += 1
        return_type_depth = 0
        starters = {
            "local", "function", "if", "while", "repeat", "for", "do",
            "return", "break", "continue", "end",
        }
        while j < len(tokens):
            text = tokens[j].text
            if return_type_depth == 0 and text in starters:
                break
            if text in {"(", "{", "[", "<"}:
                return_type_depth += 1
            elif text in {")", "}", "]", ">"}:
                return_type_depth = max(0, return_type_depth - 1)
            j += 1
    body_start = j
    end_index = _matching_function_end(tokens, body_start, source)
    end_token = tokens[end_index]
    body = tokens[body_start:end_index] + [
        Token(TokenKind.EOF, "", end_token.start, end_token.start, 0, end_token.line)
    ]
    start = tokens[local_index].start
    scope_start = start if declaration_style == "declaration" else end_token.end
    return (
        FunctionSpec(
            name=name,
            params=params,
            vararg=vararg,
            body=body,
            start=start,
            end=end_token.end,
            line=name_token.line,
            declaration_style=declaration_style,
            scope_start=scope_start,
            policy=policy,
        ),
        end_index,
    )


def _find_top_level_local_functions(
    source: str,
    policies: dict[str, FunctionPolicy] | None = None,
) -> list[FunctionSpec]:
    tokens = _sig(source)
    policies = policies or {}
    found: list[FunctionSpec] = []
    i = 0
    depth = 0
    pending_loop_do = 0
    while i + 2 < len(tokens):
        if depth == 0 and tokens[i].text == "local" and tokens[i + 1].text == "function":
            name_token = tokens[i + 2]
            spec, end_index = _parse_top_level_function_spec(
                tokens, source, local_index=i, name_token=name_token, signature_index=i + 3,
                declaration_style="declaration", policy=policies.get(name_token.text, FunctionPolicy()),
            )
            found.append(spec)
            i = end_index + 1
            continue

        if depth == 0 and tokens[i].text == "local" and tokens[i + 1].kind == TokenKind.IDENT:
            name_token = tokens[i + 1]
            j = i + 2
            if j < len(tokens) and tokens[j].text == ":":
                j = _skip_type_tokens(tokens, j + 1, {"="})
            if j + 1 < len(tokens) and tokens[j].text == "=" and tokens[j + 1].text == "function":
                spec, end_index = _parse_top_level_function_spec(
                    tokens, source, local_index=i, name_token=name_token, signature_index=j + 2,
                    declaration_style="assignment", policy=policies.get(name_token.text, FunctionPolicy()),
                )
                found.append(spec)
                i = end_index + 1
                continue

        text = tokens[i].text
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
    return found


def _top_level_local_declarations(source: str, functions: list[FunctionSpec]) -> list[tuple[int, str]]:
    tokens = _sig(source)
    spans = {spec.start: (spec.end, spec.name) for spec in functions}
    declarations: list[tuple[int, str]] = []
    depth = 0
    pending_loop_do = 0
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if depth == 0 and token.start in spans:
            end, name = spans[token.start]
            spec = next(item for item in functions if item.start == token.start)
            declarations.append((spec.scope_start, name))
            while i < len(tokens) and tokens[i].start < end:
                i += 1
            continue
        if depth == 0 and token.text == "local" and i + 1 < len(tokens) and tokens[i + 1].text != "function":
            j = i + 1
            while j < len(tokens) and tokens[j].kind == TokenKind.IDENT:
                declarations.append((tokens[j].start, tokens[j].text)); j += 1
                if j < len(tokens) and tokens[j].text == ":":
                    j = _skip_type_tokens(tokens, j + 1, {",", "="})
                if j < len(tokens) and tokens[j].text == ",":
                    j += 1; continue
                break
        text = token.text
        if text == "function": depth += 1
        elif text == "if" and not _is_expression_if(tokens, i, source, 0): depth += 1
        elif text in {"while", "for"}: depth += 1; pending_loop_do += 1
        elif text == "repeat": depth += 1
        elif text == "do":
            if pending_loop_do: pending_loop_do -= 1
            else: depth += 1
        elif text in {"end", "until"} and depth: depth -= 1
        i += 1
    return declarations


def _lua(value: Any) -> str:
    if value is None: return "nil"
    if value is True: return "true"
    if value is False: return "false"
    if isinstance(value, str):
        return '"' + "".join(f"\\{byte:03d}" for byte in value.encode("utf-8")) + '"'
    return repr(value)


def _lua_bytes(value: bytes) -> str:
    return '"' + "".join(f"\\{byte:03d}" for byte in value) + '"'


_CONSTANT_OPERANDS: dict[str, tuple[int, ...]] = {
    "K": (2,), "GLOBAL": (2,), "SETGLOBAL": (1,), "UNARY": (2,), "BINARY": (2,),
    "GETIDX": (3,), "SETIDX": (2,), "MCALL": (3,), "TMCALL": (2,),
    "K2": (2, 4),
}

_JUMP_OPERANDS: dict[str, tuple[int, ...]] = {
    "JMP": (1,), "JFALSE": (2,), "FORCHECK": (4,), "FORSTEP": (3,), "ITERNEXTG": (6,),
}

_REGISTER_OPERANDS: dict[str, tuple[int, ...]] = {
    "K": (1,), "GET": (1, 2), "SET": (1, 2), "GLOBAL": (1,), "SETGLOBAL": (2,),
    "MOVE": (1, 2), "UNARY": (1, 3), "BINARY": (1, 3, 4), "GETIDX": (1, 2),
    "SETIDX": (1, 3), "CALL": (1, 2, 3), "MCALL": (1, 2, 4), "TCALL": (1, 2),
    "TMCALL": (1, 3), "JFALSE": (1,), "RETURN": (1,), "RETURNPACK": (1, 3),
    "RETURNVARARG": (1,), "NEWTABLE": (1,), "FORCHECK": (1, 2, 3), "FORSTEP": (1, 2),
    "ITERPREP": (1, 2, 3), "ITERNEXTG": (1, 2, 3, 4), "UPGET": (1,), "UPSET": (2,),
    "CLOSURE": (1,), "VARARG": (1,), "VARARGN": (1,), "K2": (1, 3),
    "MOVE2": (1, 2, 3, 4),
}

_DYNAMIC_KEY_OPERANDS: dict[str, tuple[int, ...]] = {"GETIDX": (3,), "SETIDX": (2,)}


def _safe_binary(operator: str, left: Any, right: Any) -> Any:
    if operator == "+": return left + right
    if operator == "-": return left - right
    if operator == "*": return left * right
    if operator == "/": return left / right
    if operator == "//": return left // right
    if operator == "%": return left % right
    if operator == "^": return left ** right
    if operator == "..": return str(left) + str(right)
    if operator == "==": return left == right
    if operator == "~=": return left != right
    if operator == "<": return left < right
    if operator == ">": return left > right
    if operator == "<=": return left <= right
    if operator == ">=": return left >= right
    if operator == "&": return int(left) & int(right)
    if operator == "|": return int(left) | int(right)
    if operator == "~": return int(left) ^ int(right)
    if operator == "<<": return (int(left) << int(right)) & 0xFFFFFFFF
    if operator == ">>": return (int(left) & 0xFFFFFFFF) >> int(right)
    raise ValueError(operator)


def _safe_unary(operator: str, value: Any) -> Any:
    if operator == "not": return not value
    if operator == "-": return -value
    if operator == "#" and isinstance(value, str): return len(value)
    if operator == "~": return (~int(value)) & 0xFFFFFFFF
    raise ValueError(operator)


def _optimize_code(code: list[list[Any]], lines: list[int], constants: list[Any]) -> tuple[list[list[Any]], list[int], int]:
    constant_map = {(type(value), value): index for index, value in enumerate(constants, 1)}
    known: dict[int, Any] = {}
    changed = 0

    def const_index(value: Any) -> int:
        key = (type(value), value)
        if key not in constant_map:
            constant_map[key] = len(constants) + 1
            constants.append(value)
        return constant_map[key]

    jump_targets = {int(inst[position]) for inst in code for position in _JUMP_OPERANDS.get(inst[0], ()) if int(inst[position]) > 0}
    for index, instruction in enumerate(code, 1):
        op = instruction[0]
        if index in jump_targets:
            known.clear()
        if op == "K":
            known[int(instruction[1])] = constants[int(instruction[2]) - 1]
        elif op in {"GET", "MOVE"}:
            destination, source = int(instruction[1]), int(instruction[2])
            if source in known:
                known[destination] = known[source]
            else:
                known.pop(destination, None)
        elif op == "UNARY":
            destination, operator_index, source = int(instruction[1]), int(instruction[2]), int(instruction[3])
            if source in known:
                try:
                    value = _safe_unary(str(constants[operator_index - 1]), known[source])
                    code[index - 1] = ["K", destination, const_index(value)]; known[destination] = value; changed += 1
                except (ArithmeticError, TypeError, ValueError, OverflowError):
                    known.pop(destination, None)
            else:
                known.pop(destination, None)
        elif op == "BINARY":
            destination, operator_index, left, right = map(int, instruction[1:5])
            if left in known and right in known:
                try:
                    value = _safe_binary(str(constants[operator_index - 1]), known[left], known[right])
                    if isinstance(value, float) and not math.isfinite(value):
                        raise ValueError("non-finite")
                    code[index - 1] = ["K", destination, const_index(value)]; known[destination] = value; changed += 1
                except (ArithmeticError, TypeError, ValueError, OverflowError):
                    known.pop(destination, None)
            else:
                known.pop(destination, None)
        else:
            for position in _REGISTER_OPERANDS.get(op, ())[:1]:
                if position < len(instruction): known.pop(int(instruction[position]), None)
            if op in {"JMP", "JFALSE", "FORCHECK", "FORSTEP", "ITERNEXTG", "CALL", "MCALL", "TCALL", "TMCALL", "RETURN", "RETURNPACK", "RETURNVARARG"}:
                known.clear()

    # Jump threading is safe because targets are one-based instruction numbers.
    for instruction in code:
        for position in _JUMP_OPERANDS.get(instruction[0], ()):
            target = int(instruction[position])
            visited: set[int] = set()
            while 1 <= target <= len(code) and target not in visited and code[target - 1][0] == "JMP":
                visited.add(target); target = int(code[target - 1][1]); changed += 1
            instruction[position] = target
    return code, lines, changed


def _fuse_superinstructions(code: list[list[Any]], lines: list[int]) -> tuple[list[list[Any]], list[int], int]:
    targets = {int(inst[position]) for inst in code for position in _JUMP_OPERANDS.get(inst[0], ()) if int(inst[position]) > 0}
    new_code: list[list[Any]] = []
    new_lines: list[int] = []
    old_to_new: dict[int, int] = {}
    fused = 0
    i = 0
    while i < len(code):
        old_index = i + 1
        old_to_new[old_index] = len(new_code) + 1
        first = code[i]
        if i + 1 < len(code) and i + 2 not in targets:
            second = code[i + 1]
            if first[0] == second[0] == "K":
                new_code.append(["K2", first[1], first[2], second[1], second[2]])
                new_lines.append(lines[i]); old_to_new[i + 2] = len(new_code); fused += 1; i += 2; continue
            if first[0] == second[0] == "MOVE":
                new_code.append(["MOVE2", first[1], first[2], second[1], second[2]])
                new_lines.append(lines[i]); old_to_new[i + 2] = len(new_code); fused += 1; i += 2; continue
        new_code.append(first); new_lines.append(lines[i]); i += 1
    old_to_new[len(code) + 1] = len(new_code) + 1
    for instruction in new_code:
        for position in _JUMP_OPERANDS.get(instruction[0], ()):
            instruction[position] = old_to_new.get(int(instruction[position]), len(new_code) + 1)
    return new_code, new_lines, fused


def _insert_nops(code: list[list[Any]], lines: list[int], rng: random.Random, count: int) -> tuple[list[list[Any]], list[int]]:
    if count <= 0 or not code:
        return code, lines
    positions = sorted(rng.sample(range(len(code) + 1), k=min(count, len(code) + 1)))
    target_set = {int(inst[position]) for inst in code for position in _JUMP_OPERANDS.get(inst[0], ())}
    new_code: list[list[Any]] = []
    new_lines: list[int] = []
    old_to_new: dict[int, int] = {}
    inserts = set(positions)
    for old_index in range(1, len(code) + 2):
        if old_index - 1 in inserts:
            new_code.append(["NOP", rng.randrange(1, 65535)]); new_lines.append(lines[min(old_index - 1, len(lines) - 1)] if lines else 1)
        old_to_new[old_index] = len(new_code) + (0 if old_index == len(code) + 1 else 1)
        if old_index <= len(code):
            new_code.append(code[old_index - 1]); new_lines.append(lines[old_index - 1])
    old_to_new[len(code) + 1] = len(new_code) + 1
    for instruction in new_code:
        for position in _JUMP_OPERANDS.get(instruction[0], ()):
            instruction[position] = old_to_new.get(int(instruction[position]), len(new_code) + 1)
    return new_code, new_lines


def _shuffle_constants(code: list[list[Any]], constants: list[Any], rng: random.Random) -> list[Any]:
    if len(constants) < 2:
        return constants
    old_indices = list(range(1, len(constants) + 1)); rng.shuffle(old_indices)
    remap = {old: new for new, old in enumerate(old_indices, 1)}
    for instruction in code:
        for position in _CONSTANT_OPERANDS.get(instruction[0], ()):
            value = int(instruction[position])
            if value > 0:
                instruction[position] = remap[value]
    return [constants[old - 1] for old in old_indices]


def _encode_registers(code: list[list[Any]], offset: int, stride: int) -> None:
    def encode(value: int) -> int:
        return offset + value * stride if value > 0 else value
    for instruction in code:
        for position in _REGISTER_OPERANDS.get(instruction[0], ()):
            if position < len(instruction):
                instruction[position] = encode(int(instruction[position]))
        for position in _DYNAMIC_KEY_OPERANDS.get(instruction[0], ()):
            value = int(instruction[position])
            if value < 0:
                instruction[position] = -encode(-value)


def _derive_external_key(secret: bytes, project: str, build_id: str, key_id: str, function_name: str) -> bytes:
    message = f"o-bfuscate-v1\0{project}\0{build_id}\0{key_id}\0{function_name}".encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).digest()


_KEY_FINGERPRINT_PARAMS = (
    (2166136261, 257),
    (2246822519, 263),
    (3266489917, 269),
    (668265263, 271),
)


def _key_fingerprints(key: bytes) -> tuple[int, ...]:
    output: list[int] = []
    for seed, multiplier in _KEY_FINGERPRINT_PARAMS:
        value = seed
        for byte in key:
            value = (value * multiplier + byte) % 4294967296
        output.append(value)
    return tuple(output)


def _constant_records(constants: list[Any], rng: random.Random, external_key: bytes | None = None) -> tuple[str, str, int]:
    tags = list(range(31, 36)); rng.shuffle(tags)
    nil_tag, false_tag, true_tag, number_tag, string_tag = tags
    records: list[str] = []
    payload_bytes = 0
    stream_position = 0
    for value in constants:
        if value is None:
            tag = nil_tag; payload = bytes(rng.randrange(0, 256) for _ in range(rng.randint(1, 5)))
        elif value is False:
            tag = false_tag; payload = bytes(rng.randrange(0, 256) for _ in range(rng.randint(1, 5)))
        elif value is True:
            tag = true_tag; payload = bytes(rng.randrange(0, 256) for _ in range(rng.randint(1, 5)))
        elif isinstance(value, (int, float)):
            tag = number_tag; payload = repr(value).encode("ascii")
        elif isinstance(value, str):
            tag = string_tag; payload = value.encode("utf-8")
        else:
            raise VMCompileError(f"unsupported VM constant type: {type(value).__name__}")
        seed = rng.randrange(1, 256); multiplier = rng.randrange(1, 256, 2)
        increment = rng.randrange(0, 256); twist = rng.randrange(0, 256); reverse = rng.choice((False, True))
        data = payload[::-1] if reverse else payload
        state = seed; encoded = bytearray(); start_position = stream_position
        for position, byte in enumerate(data, 1):
            state = (state * multiplier + increment) % 256
            encoded_byte = (byte + state + position * twist) % 256
            if external_key:
                encoded_byte ^= external_key[stream_position % len(external_key)]
            encoded.append(encoded_byte); stream_position += 1
        payload_bytes += len(encoded)
        records.append("{" + ",".join((
            str(tag), _lua_bytes(bytes(encoded)), str(seed), str(multiplier), str(increment), str(twist),
            "1" if reverse else "0", str(start_position),
        )) + "}")
    tag_table = "{" + ",".join(map(str, (nil_tag, false_tag, true_tag, number_tag, string_tag))) + "}"
    return "{" + ",".join(records) + "}", tag_table, payload_bytes


_VM_OPERANDS = 7
_VM_RECORD_SIZE = 1 + _VM_OPERANDS * 2


def _zero_run_compress(value: bytes) -> bytes:
    output = bytearray()
    i = 0
    while i < len(value):
        if value[i] == 0:
            j = i
            while j < len(value) and value[j] == 0 and j - i < 255:
                j += 1
            run = j - i
            if run >= 3:
                output.extend((255, run)); i = j; continue
        if value[i] == 255:
            output.extend((255, 0))
        else:
            output.append(value[i])
        i += 1
    return bytes(output)


def _pack_code(
    code: list[list[Any]],
    opmap: dict[str, int],
    key: int,
    step: int,
    operand_permutation: list[int],
    external_key: bytes | None,
    compress: bool,
) -> tuple[bytes, int, int, bool]:
    plain = bytearray()
    for instruction in code:
        operands = [int(value) for value in instruction[1:]]
        if len(operands) > _VM_OPERANDS:
            raise VMCompileError("instruction has too many operands")
        operands.extend([0] * (_VM_OPERANDS - len(operands)))
        physical = [0] * _VM_OPERANDS
        for logical_index, physical_index in enumerate(operand_permutation):
            physical[physical_index] = operands[logical_index]
        plain.append(opmap[instruction[0]])
        for value in physical:
            if not -32768 <= value <= 65535:
                raise VMCompileError("VM operand exceeds packed 16-bit range")
            value &= 0xFFFF; plain.append(value & 0xFF); plain.append((value >> 8) & 0xFF)
    checksum = 2166136261
    for position, byte in enumerate(plain, 1):
        checksum = (checksum * 257 + byte + position) % 4294967296
    compressed = _zero_run_compress(bytes(plain)) if compress else bytes(plain)
    use_compressed = compress and len(compressed) < len(plain)
    payload = compressed if use_compressed else bytes(plain)
    encoded = bytearray()
    for position, byte in enumerate(payload, 1):
        value = (byte + key + position * step) & 0xFF
        if external_key:
            value ^= external_key[(position - 1) % len(external_key)]
        encoded.append(value)
    return bytes(encoded), checksum, len(plain), use_compressed


def _line_table(lines: list[int], enabled: bool) -> str:
    if not enabled:
        return "nil"
    return "{" + ",".join(str(max(1, line)) for line in lines) + "}"


def _capture_plan(plan: list[tuple[int, int]]) -> str:
    return "{" + ",".join("{" + f"{kind},{index}" + "}" for kind, index in plan) + "}"


def _handler_bodies() -> dict[str, str]:
    return {
        "K": "R[A1]=C[A2];P+=S",
        "GET": "R[A1]=R[A2];P+=S",
        "SET": "R[A1]=R[A2];P+=S",
        "GLOBAL": "R[A1]=E[C[A2]][1]();P+=S",
        "SETGLOBAL": "E[C[A1]][2](R[A2]);P+=S",
        "MOVE": "R[A1]=R[A2];P+=S",
        "UNARY": (
            "local a=R[A3];local q=C[A2];if q=='not'then R[A1]=not a elseif q=='-'then R[A1]=-a "
            "elseif q=='#'then R[A1]=#a else R[A1]=H.bnot(a)end;P+=S"
        ),
        "BINARY": (
            "local a,b,q=R[A3],R[A4],C[A2];if q=='+'then R[A1]=a+b elseif q=='-'then R[A1]=a-b "
            "elseif q=='*'then R[A1]=a*b elseif q=='/'then R[A1]=a/b elseif q=='//'then R[A1]=a//b "
            "elseif q=='%'then R[A1]=a%b elseif q=='^'then R[A1]=a^b elseif q=='..'then R[A1]=a..b "
            "elseif q=='=='then R[A1]=a==b elseif q=='~='then R[A1]=a~=b elseif q=='<'then R[A1]=a<b "
            "elseif q=='>'then R[A1]=a>b elseif q=='<='then R[A1]=a<=b elseif q=='>='then R[A1]=a>=b "
            "elseif q=='&'then R[A1]=H.band(a,b) elseif q=='|'then R[A1]=H.bor(a,b) elseif q=='~'then R[A1]=H.bxor(a,b) "
            "elseif q=='<<'then R[A1]=H.lshift(a,b)else R[A1]=H.rshift(a,b)end;P+=S"
        ),
        "GETIDX": "local k=A3>0 and C[A3]or R[-A3];R[A1]=R[A2][k];P+=S",
        "SETIDX": "local k=A2>0 and C[A2]or R[-A2];R[A1][k]=R[A3];P+=S",
        "CALL": (
            "local z=ca(A3,A4,A6);local v=table.pack(R[A2](table.unpack(z,1,z.n)));"
            "if A5==0 then R[A1]=v elseif A5==1 then R[A1]=v[1]else for j=1,A5 do R[A1+(j-1)*RS]=v[j]end end;P+=S"
        ),
        "MCALL": (
            "local z=ca(A4,A5,A7);local o=R[A2];local v=table.pack(o[C[A3]](o,table.unpack(z,1,z.n)));"
            "if A6==0 then R[A1]=v elseif A6==1 then R[A1]=v[1]else for j=1,A6 do R[A1+(j-1)*RS]=v[j]end end;P+=S"
        ),
        "TCALL": "local z=ca(A2,A3,A4);return R[A1](table.unpack(z,1,z.n))",
        "TMCALL": "local z=ca(A3,A4,A5);local o=R[A1];return o[C[A2]](o,table.unpack(z,1,z.n))",
        "JMP": "P=(A1-1)*S+1",
        "JFALSE": "if not R[A1]then P=(A2-1)*S+1 else P+=S end",
        "RETURN": "if A2==0 then return end;local o=table.create(A2);for j=0,A2-1 do o[#o+1]=R[A1+j*RS]end;return table.unpack(o,1,A2)",
        "RETURNPACK": (
            "local z=R[A3];local o=table.create(A2+(z.n or #z));for j=0,A2-1 do o[#o+1]=R[A1+j*RS]end;"
            "for j=1,(z.n or #z)do o[#o+1]=z[j]end;return table.unpack(o,1,#o)"
        ),
        "RETURNVARARG": (
            "local o=table.create(A2+math.max(0,VA.n-PC));for j=0,A2-1 do o[#o+1]=R[A1+j*RS]end;"
            "for j=PC+1,VA.n do o[#o+1]=VA[j]end;return table.unpack(o,1,#o)"
        ),
        "NEWTABLE": "R[A1]={};P+=S",
        "FORCHECK": "local s=R[A3];local n=R[A1];local l=R[A2];if(s>=0 and n>l)or(s<0 and n<l)then P=(A4-1)*S+1 else P+=S end",
        "FORSTEP": "R[A1]+=R[A2];P=(A3-1)*S+1",
        "ITERPREP": (
            "local f=R[A1];if type(f)~='function'then local m=getmetatable(f);if m and type(m.__iter)=='function'then "
            "local z=table.pack(m.__iter(f));R[A1],R[A2],R[A3]=z[1],z[2],z[3]elseif type(f)=='table'then "
            "R[A1],R[A2],R[A3]=next,f,nil else error('value is not iterable')end end;P+=S"
        ),
        "ITERNEXTG": (
            "local z=table.pack(R[A1](R[A2],R[A3]));R[A3]=z[1];if z[1]==nil then P=(A6-1)*S+1 else "
            "for j=1,A5 do R[A4+(j-1)*RS]=z[j]end;P+=S end"
        ),
        "UPGET": "R[A1]=ug(U[A2]);P+=S",
        "UPSET": "us(U[A1],R[A2]);P+=S",
        "CLOSURE": (
            "local cp=B[A2][L[7]];local cu={};for j=1,#cp do local d=cp[j];if d[1]==0 then cu[j]={0,R,RO+d[2]*RS}else cu[j]=U[d[2]]end end;"
            "R[A1]=function(...)return V(A2,cu,...)end;P+=S"
        ),
        "VARARG": "R[A1]=VA[PC+A2];P+=S",
        "VARARGN": "for j=1,A2 do R[A1+(j-1)*RS]=VA[PC+j]end;P+=S",
        "K2": "R[A1]=C[A2];R[A3]=C[A4];P+=S",
        "MOVE2": "R[A1]=R[A2];R[A3]=R[A4];P+=S",
        "NOP": "P+=S",
    }


def _render_dispatch(order: list[str], architecture: str) -> str:
    bodies = _handler_bodies()
    clauses = [(f"O==OP[{OPS.index(op) + 1}]", bodies[op]) for op in order]
    if architecture == "nested":
        def build(index: int) -> str:
            if index >= len(clauses):
                return "error('invalid virtual opcode')"
            condition, body = clauses[index]
            return f"if {condition} then {body} else {build(index + 1)} end"
        return build(0)
    parts: list[str] = []
    for index, (condition, body) in enumerate(clauses):
        parts.append(("if " if index == 0 else "elseif ") + condition + "then " + body)
    parts.append("else error('invalid virtual opcode')end")
    return " ".join(parts)


def _bundle_with_layout(fields: list[str], layout: list[int]) -> str:
    physical = ["nil"] * len(fields)
    for logical_index, physical_index in enumerate(layout):
        physical[physical_index] = fields[logical_index]
    return "{" + ",".join(physical) + "}"


def _automatic_mode(spec: FunctionSpec) -> str:
    significant = [token for token in spec.body if token.kind != TokenKind.EOF]
    loops = sum(token.text in {"for", "while", "repeat"} for token in significant)
    nested = sum(token.text == "function" for token in significant)
    calls = sum(token.text == "(" and index > 0 and significant[index - 1].kind == TokenKind.IDENT for index, token in enumerate(significant))
    # Large or loop-heavy functions are kept on the lighter interpreter profile
    # unless the author explicitly requests full protection.
    score = len(significant) + loops * 45 + nested * 30 + calls * 4
    return "light" if score >= 320 or loops >= 4 else "full"


def build_vm_backend(
    source: str,
    rng: random.Random,
    names: NameGenerator,
    *,
    encrypt_constants: bool = True,
    shuffle_constants: bool = True,
    policies: dict[str, FunctionPolicy] | None = None,
    vm_source_maps: bool = True,
    vm_integrity: bool = True,
    vm_optimize: bool = True,
    vm_superoperators: bool = True,
    vm_polymorphic: bool = True,
    vm_compress: bool = True,
    vm_architecture: str = "auto",
    external_key_secret: bytes | None = None,
    license_project: str = "default",
    license_key_id: str = "default",
    license_resolver: str = "__O_LICENSE_RESOLVE",
    build_id: str = "",
    encrypt_all: bool = False,
    helper_storage: str = "local",
) -> VMBuild:
    result = VMBuild()
    helper_storage = helper_storage.lower().strip()
    if helper_storage not in {"local", "global"}:
        raise VMCompileError("VM helper storage must be local or global")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", license_resolver):
        raise VMCompileError("license resolver must be a Luau identifier")
    try:
        functions = _find_top_level_local_functions(source, policies)
    except VMCompileError as exc:
        result.warnings.append(f"VM scan fallback: {exc}")
        return result
    if not functions:
        result.warnings.append("VM: no top-level local functions found")
        return result

    declarations = _top_level_local_declarations(source, functions)
    registry = PrototypeRegistry()
    top_levels: list[tuple[FunctionSpec, int, Prototype]] = []

    for spec in functions:
        policy = spec.policy
        mode = "encrypt" if encrypt_all else policy.mode
        if mode == "auto":
            mode = _automatic_mode(spec)
        if mode in {"no-vm", "hot"}:
            result.warnings.append(f"VM policy kept {spec.name} native ({mode})")
            continue
        key_id = policy.key_id or license_key_id
        if mode == "encrypt" and external_key_secret is None:
            result.warnings.append(f"VM skipped {spec.name}: encrypted policy requires --external-key-secret")
            continue
        visible_locals = {name for position, name in declarations if position <= spec.start}
        registry_mark = len(registry.items)
        prototype_index = registry.reserve()
        source_map = vm_source_maps if policy.source_map is None else policy.source_map
        integrity = (vm_integrity and mode != "light") if policy.integrity is None else policy.integrity
        optimize = vm_optimize if policy.optimize is None else policy.optimize
        compiler = FunctionCompiler(
            spec.body, source, spec.name, spec.params, spec.vararg, registry, prototype_index,
            external_names=visible_locals,
            source_map=source_map,
            integrity=integrity,
            optimize=optimize,
            protection_mode=mode,
            key_id=key_id if mode == "encrypt" else None,
            key_scope=spec.name,
        )
        try:
            prototype = compiler.compile()
            if policy.no_upvalues and prototype.upvalue_names:
                raise VMCompileError("OBF_NO_UPVALUES function captured lexical state")
        except (VMCompileError, ValueError, UnicodeError) as exc:
            registry.items = registry.items[:registry_mark]
            result.warnings.append(f"VM skipped {spec.name}: {exc}")
            continue
        top_levels.append((spec, prototype_index, prototype))

    if not top_levels:
        return result

    prototypes = registry.resolved()
    old_to_new = {prototype.index: new for new, prototype in enumerate(prototypes, 1)}
    for prototype in prototypes:
        prototype.index = old_to_new[prototype.index]
        for instruction in prototype.code:
            if instruction[0] == "CLOSURE":
                instruction[2] = old_to_new[int(instruction[2])]
    top_levels = [(spec, old_to_new[index], prototype) for spec, index, prototype in top_levels]

    layout = list(range(18))
    if vm_polymorphic:
        rng.shuffle(layout)
    layout_lua = "{" + ",".join(str(position + 1) for position in layout) + "}"
    bundles: list[str] = []
    env_names: set[str] = set()

    for prototype in prototypes:
        code = [instruction[:] for instruction in prototype.code]
        lines = list(prototype.lines)
        constants = list(prototype.constants)
        optimized = 0
        fused = 0
        if prototype.optimize:
            code, lines, optimized = _optimize_code(code, lines, constants)
        if vm_superoperators and prototype.protection_mode != "light":
            code, lines, fused = _fuse_superinstructions(code, lines)
        if vm_polymorphic and prototype.protection_mode != "light":
            code, lines = _insert_nops(code, lines, rng, rng.randint(0, max(1, min(4, len(code) // 8 + 1))))
        if shuffle_constants:
            constants = _shuffle_constants(code, constants, rng)

        opcode_values = list(range(19, 19 + len(OPS))); rng.shuffle(opcode_values)
        opmap = dict(zip(OPS, opcode_values))
        internal_key = rng.randrange(1, 256); step = rng.randrange(1, 256, 2)
        operand_permutation = list(range(_VM_OPERANDS)); rng.shuffle(operand_permutation)
        reg_stride = rng.choice((1, 3, 5, 7, 9, 11, 13)) if vm_polymorphic else 1
        max_offset = max(1, 30000 - max(1, prototype.max_register) * reg_stride)
        reg_offset = rng.randrange(1, min(251, max_offset)) if vm_polymorphic else 0
        _encode_registers(code, reg_offset, reg_stride)

        external_key: bytes | None = None
        key_meta = "nil"
        if prototype.protection_mode == "encrypt":
            assert external_key_secret is not None and prototype.key_id is not None
            external_key = _derive_external_key(
                external_key_secret, license_project, build_id, prototype.key_id, prototype.key_scope,
            )
            fingerprints = _key_fingerprints(external_key)
            key_meta = "{" + ",".join((
                _lua(license_project), _lua(build_id), _lua(prototype.key_id), _lua(prototype.key_scope),
                *(str(value) for value in fingerprints),
            )) + "}"
            result.externally_keyed_functions += 1

        packed, checksum, plain_bytes, compressed = _pack_code(
            code, opmap, internal_key, step, operand_permutation, external_key,
            vm_compress and prototype.protection_mode != "light",
        )
        if encrypt_constants:
            consts, tags, protected_bytes = _constant_records(constants, rng, external_key)
        else:
            consts = "{" + ",".join(_lua(value) for value in constants) + "}"
            tags = "nil"; protected_bytes = 0
        opcode_table = "{" + ",".join(str(opmap[op]) for op in OPS) + "}"
        operand_table = "{" + ",".join(str(position + 1) for position in operand_permutation) + "}"
        fields = [
            _lua_bytes(packed), consts, str(internal_key), str(step), opcode_table, tags,
            _capture_plan(prototype.capture_plan), str(reg_offset), str(reg_stride), str(len(prototype.params)),
            "1" if prototype.vararg else "0", _line_table(lines, prototype.source_map), _lua(prototype.name),
            key_meta, operand_table, str(checksum), "1" if prototype.integrity else "0",
            "1" if compressed else "0",
        ]
        bundles.append(_bundle_with_layout(fields, layout))
        env_names.update(prototype.globals)
        result.instruction_count += len(code)
        result.constant_count += len(constants)
        result.encrypted_constant_bytes += protected_bytes
        result.plain_code_bytes += plain_bytes
        result.packed_code_bytes += len(packed)
        result.compressed_functions += int(compressed)
        result.captured_upvalues += len(prototype.upvalue_names)
        result.writable_upvalues += len(prototype.written_upvalues)
        result.iterator_loops += sum(1 for instruction in code if instruction[0] == "ITERNEXTG")
        result.nested_closures += sum(1 for instruction in code if instruction[0] == "CLOSURE")
        result.vararg_functions += int(prototype.vararg)
        result.optimized_instructions += optimized
        result.superinstructions += fused
        result.integrity_checks += int(prototype.integrity)
        result.source_mapped_functions += int(prototype.source_map)
        result.light_functions += int(prototype.protection_mode == "light")
        result.full_functions += int(prototype.protection_mode in {"full", "encrypt"})

    vm_name = names.random_name(13)
    env_entries = []
    for global_name in sorted(env_names):
        env_entries.append(
            f"[{_lua(global_name)}]={{function()return {global_name} end,function(v){global_name}=v end}}"
        )
    env = "{" + ",".join(env_entries) + "}"
    btable = "{" + ",".join(bundles) + "}"

    architecture = vm_architecture
    if architecture == "auto":
        architecture = rng.choice(("linear", "nested")) if vm_polymorphic else "linear"
    if architecture not in {"linear", "nested"}:
        raise VMCompileError("vm architecture must be auto, linear, or nested")
    result.vm_architecture = architecture
    handler_order = list(OPS)
    if vm_polymorphic:
        rng.shuffle(handler_order)
    dispatch = _render_dispatch(handler_order, architecture)

    # L logical field positions: code, constants, key, step, opcodes, tags,
    # capture plan, register offset/stride, parameter count, vararg flag,
    # source lines, function name, external key metadata, operand map, checksum, integrity, compression.
    vm_declaration = "local " if helper_storage == "local" else ""
    result.prelude = (
        f"{vm_declaration}{vm_name}=(function()local B={btable};local E={env};local L={layout_lua};local H=bit32;local LR=function()return {license_resolver} end;local V;"
        "local function ug(d)if d[1]==0 then return d[2][d[3]]else return d[2]()end end;"
        "local function us(d,v)if d[1]==0 then d[2][d[3]]=v else d[3](v)end end;"
        "local function fp(k,s,m)local h=s;for i=1,#k do h=(h*m+string.byte(k,i))%4294967296 end;return h end;"
        "V=function(fi,U,...)local F=B[fi];local EI=F[L[1]];local KM=F[L[14]];local EK=nil;"
        "if KM then local RR=LR();if type(RR)~='function'then error('license resolver unavailable for '..KM[4],0)end;EK=RR(KM[1],KM[2],KM[3],KM[4]);"
        "if type(EK)~='string'or#EK<32 or fp(EK,2166136261,257)~=KM[5]or fp(EK,2246822519,263)~=KM[6]"
        "or fp(EK,3266489917,269)~=KM[7]or fp(EK,668265263,271)~=KM[8]then error('license denied for '..KM[4],0)end end;"
        "local function cb(p)local b=string.byte(EI,p);if EK then b=H.bxor(b,string.byte(EK,((p-1)%#EK)+1))end;return(b-F[L[3]]-p*F[L[4]])%256 end;"
        "local I=EI;local plain=false;if F[L[18]]==1 then local o={};local i=1;while i<=#EI do local b=cb(i);if b==255 then local n=cb(i+1);"
        "if n==0 then o[#o+1]=string.char(255)else o[#o+1]=string.rep(string.char(0),n)end;i+=2 else o[#o+1]=string.char(b);i+=1 end end;I=table.concat(o);plain=true end;"
        "local C;if F[L[6]]then C={};local T=F[L[6]];for ci=1,#F[L[2]]do local d=F[L[2]][ci];local s=d[2];local q=d[3];local u={};"
        "for cp=1,#s do local eb=string.byte(s,cp);if EK then eb=H.bxor(eb,string.byte(EK,((d[8]+cp-1)%#EK)+1))end;"
        "q=(q*d[4]+d[5])%256;local cj=d[7]==1 and(#s-cp+1)or cp;u[cj]=string.char((eb-q-cp*d[6])%256)end;"
        "local v=table.concat(u);local g=d[1];if g==T[2]then C[ci]=false elseif g==T[3]then C[ci]=true elseif g==T[4]then C[ci]=tonumber(v)elseif g==T[5]then C[ci]=v end end else C=F[L[2]]end;"
        "local RO,RS,PC=F[L[8]],F[L[9]],F[L[10]];local VA=table.pack(...);local R={};for i=1,PC do R[RO+i*RS]=VA[i]end;"
        "local P=1;local OP=F[L[5]];local PM=F[L[15]];local S=" + str(_VM_RECORD_SIZE) + ";local LM=F[L[12]];local LN=LM and LM[1]or 0;"
        "local function rb(p)if plain then return string.byte(I,p)else return cb(p)end end;"
        "local function w(p)local v=rb(p)+rb(p+1)*256;if v>=32768 then return v-65536 end;return v end;"
        "if F[L[17]]==1 then local z=2166136261;for i=1,#I do z=(z*257+rb(i)+i)%4294967296 end;"
        "if z~=F[L[16]]then error('virtual bundle integrity failure',0)end end;"
        "local function ca(base,count,extra)local z=table.create(count+(extra==1 and math.max(0,VA.n-PC)or 0));for j=0,count-1 do z[#z+1]=R[base+j*RS]end;"
        "if extra==1 then for j=PC+1,VA.n do z[#z+1]=VA[j]end end;z.n=#z;return z end;"
        "local function run()while true do local O=rb(P);local N={w(P+1),w(P+3),w(P+5),w(P+7),w(P+9),w(P+11),w(P+13)};"
        "local A1,A2,A3,A4,A5,A6,A7=N[PM[1]],N[PM[2]],N[PM[3]],N[PM[4]],N[PM[5]],N[PM[6]],N[PM[7]];"
        "if LM then LN=LM[math.floor((P-1)/S)+1]or LN end;" + dispatch + " end end;"
        "if LM then local z=table.pack(xpcall(run,function(e)return'virtualized '..F[L[13]]..':'..tostring(LN)..': '..tostring(e)end));"
        "if not z[1]then error(z[2],0)end;return table.unpack(z,2,z.n)end;return run()end;return V end)();"
    )

    for spec, prototype_index, prototype in top_levels:
        capture_descriptors = []
        for capture in prototype.upvalue_names:
            capture_descriptors.append(
                "{1,function()return " + capture + " end,function(v)" + capture + "=v end}"
            )
        captures = "{" + ",".join(capture_descriptors) + "}"
        if spec.declaration_style == "assignment":
            wrapper = f"local {spec.name}=function(...)return {vm_name}({prototype_index},{captures},...)end"
        else:
            wrapper = f"local function {spec.name}(...)return {vm_name}({prototype_index},{captures},...)end"
        result.replacements.append((spec.start, spec.end, wrapper))
        result.virtualized_functions += 1

    result.virtualized_prototypes = len(prototypes)
    return result
