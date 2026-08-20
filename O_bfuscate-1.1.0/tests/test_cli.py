from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest

from o_bfuscate.cli import main


ROOT = Path(__file__).resolve().parents[1]
COMPILER = ROOT / "vendor/luau/linux-x86_64/luau-compile"


class CliTests(unittest.TestCase):
    def test_adaptive_preserves_string_protection(self) -> None:
        lines = [f'local v{i}=_G["x{i}"]' for i in range(199)]
        lines += ["local t={}"] + [f"t[{i + 1}]=v{i}" for i in range(199)] + ["print(#t)"]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            input_path = root / "input.luau"
            output_path = root / "output.luau"
            manifest_path = root / "manifest.json"
            input_path.write_text("\n".join(lines), encoding="utf-8")
            rc = main([
                str(input_path), "-o", str(output_path), "--manifest", str(manifest_path),
                "--profile", "balanced", "--helper-storage", "local", "--adaptive",
                "--luau-compiler", str(COMPILER), "--seed", "17",
            ])
            self.assertEqual(rc, 0)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["adaptive_tier"], "global_helpers")
            self.assertGreater(manifest["stats"]["encrypted_strings"], 0)
            self.assertEqual(manifest["helper_storage"], "global")


if __name__ == "__main__":
    unittest.main()
