from __future__ import annotations

from pathlib import Path
import random
import tempfile
import unittest

from o_bfuscate import Config, obfuscate
from o_bfuscate.budget import estimate_register_budget
from o_bfuscate.macros import process_macros
from o_bfuscate.official import execute_source, validate_source


ROOT = Path(__file__).resolve().parents[1]
COMPILER = ROOT / "vendor/luau/linux-x86_64/luau-compile"
RUNTIME = ROOT / "vendor/luau/linux-x86_64/luau"


class ReleaseTests(unittest.TestCase):
    def assertCompiles(self, source: str) -> None:
        ok, diagnostic = validate_source(source, COMPILER)
        self.assertTrue(ok, diagnostic)

    def test_register_budget_switches_only_helper_storage(self) -> None:
        lines = [f'local v{i}=_G["x{i}"]' for i in range(199)]
        lines += ["local t={}"] + [f"t[{i + 1}]=v{i}" for i in range(199)] + ["print(#t)"]
        source = "\n".join(lines)
        budget = estimate_register_budget(source)
        self.assertEqual(budget.estimated_peak_locals, 200)

        local_result = obfuscate(source, Config(
            seed=11, encrypt_strings=True, split_numbers=False, noise=0,
            mask_literals=False, helper_storage="local",
        ))
        local_ok, _ = validate_source(local_result.source, COMPILER)
        self.assertFalse(local_ok)

        auto_result = obfuscate(source, Config(
            seed=11, encrypt_strings=True, split_numbers=False, noise=0,
            mask_literals=False, helper_storage="auto",
        ))
        self.assertEqual(auto_result.manifest["helper_storage"], "global")
        self.assertCompiles(auto_result.source)
        self.assertGreater(auto_result.manifest["stats"]["encrypted_strings"], 0)

    def test_wynf_compatibility_wrappers(self) -> None:
        source = """
if not WYNF_OBFUSCATED then
function WYNF_JIT(Fn) return Fn end
function WYNF_INLINE(Fn) return Fn end
end
local f
f = WYNF_INLINE(function(x) return x + 1 end)
local g = WYNF_JIT(function(x) return f(x) end)
local callback = table.sort({2, 1}, WYNF_JIT(function(a, b) return a < b end))
print(g(2))
"""
        result = process_macros(source)
        self.assertEqual(result.prelude, "WYNF_OBFUSCATED=true;")
        self.assertEqual(result.policies["f"].mode, "hot")
        self.assertEqual(result.policies["g"].mode, "light")
        self.assertNotIn("= WYNF_INLINE(function", result.source)
        self.assertNotIn("= WYNF_JIT(function", result.source)
        self.assertGreaterEqual(result.expanded_macros, 3)

    def test_vm_call_statement_boundary_and_contextual_type(self) -> None:
        source = """
local function run(value)
    local state = {n = 0}
    local function cleanup() state.n += 1 end
    cleanup()
    state.n = state.n + 1
    state.touch = function(self) self.n += 1 end
    state:touch()
    state.n = state.n + 1
    local checker = type
    return checker(value), state.n
end
local proxy = {n = 0}
function proxy:touch() self.n += 1 end
local function exercise()
    local checker = type
    proxy:touch()
    proxy.n = proxy.n + 1
    return checker(proxy), proxy.n
end
print(exercise())
"""
        result = obfuscate(source, Config(
            seed=12, virtualize=True, encrypt_strings=False, split_numbers=False,
            noise=0, mask_literals=False,
        ))
        self.assertEqual(result.manifest["stats"]["virtualized_functions"], 2)
        self.assertFalse(any("VM skipped" in warning for warning in result.warnings))
        self.assertCompiles(result.source)
        native = execute_source(source, RUNTIME)
        protected = execute_source(result.source, RUNTIME)
        self.assertEqual(native, protected)

    def test_dense_runtime_equivalence(self) -> None:
        source = """
local function outer(x, ...)
    local y = 3
    local function inc(z) y += z; return y end
    local sum = 0
    for i = 1, 3 do sum += i end
    local extra = select(1, ...)
    return inc(x) + sum + extra, {a = "ok", [x] = y}
end
local a, t = outer(4, 5)
print(a, t.a, t[4])
"""
        result = obfuscate(source, Config(
            seed=42, rename_locals=True, encrypt_strings=True,
            split_numbers=True, encrypt_properties=True, layered_strings=True,
            string_shards=3, string_decoys=4, noise=2,
            opaque_predicates=True, number_depth=4, bitwise_numbers=True,
            virtualize=True,
        ))
        self.assertCompiles(result.source)
        self.assertEqual(execute_source(source, RUNTIME), execute_source(result.source, RUNTIME))
        self.assertGreater(result.manifest["stats"]["nested_virtual_closures"], 0)
        self.assertGreater(result.manifest["stats"]["encrypted_strings"], 0)

    def test_deterministic_global_helpers(self) -> None:
        source = 'local value="secret"; print(value)\n'
        cfg = Config(seed=91, helper_storage="global", noise=0)
        first = obfuscate(source, cfg)
        second = obfuscate(source, cfg)
        self.assertEqual(first.source, second.source)
        self.assertEqual(first.manifest["helper_storage"], "global")
        self.assertCompiles(first.source)


if __name__ == "__main__":
    unittest.main()
