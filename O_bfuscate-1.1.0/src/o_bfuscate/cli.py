from __future__ import annotations

import argparse
from dataclasses import replace
import json
from importlib import resources
from pathlib import Path
import sys

from .lexer import LexError
from .parser import ParseError
from . import __version__
from .pipeline import Config, obfuscate
from .official import find_compiler, validate_source


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="o-bfuscate",
        description="O_bfuscate: a deterministic, Luau-aware source protection CLI.",
    )
    parser.add_argument("--version", action="version", version=f"O_bfuscate {__version__}")
    parser.add_argument("--write-macro-sdk", type=Path, help="write the identity macro SDK and exit")
    parser.add_argument("input", type=Path, nargs="?", help="input .lua/.luau file")
    parser.add_argument("-o", "--output", type=Path, help="output path (default: <input>.obf.luau)")
    parser.add_argument("--manifest", type=Path, help="write a JSON build manifest")
    parser.add_argument("--seed", type=int, help="reproducible build seed")
    parser.add_argument("--profile", choices=("fast", "balanced", "dense"), default="balanced", help="transformation profile")
    parser.add_argument("--no-rename", action="store_true", help="disable local/parameter renaming")
    parser.add_argument("--no-strings", action="store_true", help="disable runtime string vault")
    parser.add_argument("--no-numbers", action="store_true", help="disable integer splitting")
    parser.add_argument("--no-properties", action="store_true", help="do not rewrite dot/table keys through the string vault")
    parser.add_argument("--layered-strings", action="store_true", help="split strings into independently encoded chunks with masked vault indices")
    parser.add_argument("--no-layered-strings", action="store_true", help="disable layered string encoding included by the dense profile")
    parser.add_argument("--string-shards", type=int, choices=range(1, 9), default=None, metavar="1-8", help="split protected constants across independently keyed string vaults")
    parser.add_argument("--string-decoys", type=int, choices=range(0, 65), default=None, metavar="0-64", help="add unused encrypted string-vault entries")
    parser.add_argument("--noise", type=int, default=None, choices=range(0, 9), metavar="0-8", help="override harmless build-noise level")
    parser.add_argument("--opaque-predicates", action="store_true", help="use deterministic no-op branches for build noise")
    parser.add_argument("--no-opaque-predicates", action="store_true", help="disable opaque noise included by the dense profile")
    parser.add_argument("--no-literal-masking", action="store_true", help="leave runtime true/false/nil literals unchanged")
    parser.add_argument("--number-depth", type=int, choices=range(1, 6), default=None, metavar="1-5", help="arithmetic expression depth for integer masking")
    parser.add_argument("--bitwise-numbers", action="store_true", help="mix bit32 XOR reconstruction into eligible integer masks")
    parser.add_argument("--no-bitwise-numbers", action="store_true", help="disable bitwise integer masking included by the dense profile")
    parser.add_argument("--watermark", help="forensic watermark label; only a build-bound digest is emitted")
    parser.add_argument("--preserve", action="append", default=[], metavar="NAME", help="local name that must not be renamed")
    parser.add_argument("--strict-parser", action="store_true", help="fail instead of falling back to minification on unsupported syntax")
    parser.add_argument("--vm", action="store_true", help="virtualize eligible top-level local functions and their nested closures")
    parser.add_argument("--no-vm", action="store_true", help="disable virtualization included by the dense profile")
    parser.add_argument("--no-vm-constant-encryption", action="store_true", help="leave virtual-machine constants in readable tables")
    parser.add_argument("--no-vm-constant-shuffle", action="store_true", help="preserve compiler-order VM constant indices")
    parser.add_argument("--preserve-layout", action="store_true", help="apply transforms without removing original whitespace/comments")
    parser.add_argument("--no-protection-macros", action="store_true", help="do not expand OBF_* identity macros or --@obf policies")
    parser.add_argument("--function-policy", action="append", default=[], metavar="NAME=MODE[:KEY]", help="override a function policy: no-vm, hot, light, full, or encrypt")
    parser.add_argument("--no-vm-source-maps", action="store_true", help="disable original-line VM error remapping")
    parser.add_argument("--no-vm-integrity", action="store_true", help="disable non-destructive virtual bundle checksum validation")
    parser.add_argument("--no-vm-optimize", action="store_true", help="disable VM constant folding and jump threading")
    parser.add_argument("--no-vm-superoperators", action="store_true", help="disable fused VM instructions")
    parser.add_argument("--no-vm-polymorphic", action="store_true", help="disable register/operand/layout and dispatcher randomization")
    parser.add_argument("--no-vm-compression", action="store_true", help="disable zero-run VM bytecode compression")
    parser.add_argument("--vm-architecture", choices=("auto", "linear", "nested"), default="auto", help="embedded interpreter structure")
    parser.add_argument("--external-key-secret", type=Path, help="server-side project secret for externally keyed functions")
    parser.add_argument("--license-project", default="default", help="license project id embedded in keyed function metadata")
    parser.add_argument("--license-key-id", default="default", help="default external function-key id")
    parser.add_argument("--license-resolver", default="__O_LICENSE_RESOLVE", help="runtime global that returns raw function-key bytes")
    parser.add_argument("--encrypt-all-vm", action="store_true", help="externally key every virtualized function")
    parser.add_argument("--manifest-signing-secret", type=Path, help="HMAC secret used to sign the JSON manifest")
    parser.add_argument("--manifest-signing-key-id", default="default", help="identifier recorded with the manifest signature")
    parser.add_argument("--official-validate", action="store_true", help="require output to compile with the official Luau compiler")
    parser.add_argument("--adaptive", action="store_true", help="adapt individual components until the output officially compiles")
    parser.add_argument("--helper-storage", choices=("auto", "local", "global"), default="auto", help="store persistent generated helpers in locals or collision-resistant globals")
    parser.add_argument("--register-reserve", type=int, default=12, metavar="N", help="temporary-register reserve used by the large-chunk budget estimator")
    parser.add_argument("--luau-compiler", type=Path, help="path to luau-compile (bundled compiler is used by default)")
    parser.add_argument("--stdout", action="store_true", help="write obfuscated source to stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.write_macro_sdk is not None:
        sdk = resources.files("o_bfuscate").joinpath("macro_sdk.luau").read_text(encoding="utf-8")
        args.write_macro_sdk.parent.mkdir(parents=True, exist_ok=True)
        args.write_macro_sdk.write_text(sdk, encoding="utf-8")
        print(f"wrote {args.write_macro_sdk}")
        return 0
    if args.input is None:
        parser.error("input is required unless --write-macro-sdk is used")
    try:
        source = args.input.read_text(encoding="utf-8")
        profiles = {
            "fast": dict(
                rename_locals=True,
                encrypt_strings=False,
                split_numbers=False,
                encrypt_properties=False,
                layered_strings=False,
                string_shards=1,
                string_decoys=0,
                noise=0,
                opaque_predicates=False,
                number_depth=1,
                bitwise_numbers=False,
                virtualize=False,
            ),
            "balanced": dict(
                rename_locals=True,
                encrypt_strings=True,
                split_numbers=True,
                encrypt_properties=True,
                layered_strings=False,
                string_shards=1,
                string_decoys=0,
                noise=1,
                opaque_predicates=False,
                number_depth=2,
                bitwise_numbers=False,
                virtualize=False,
            ),
            "dense": dict(
                rename_locals=True,
                encrypt_strings=True,
                split_numbers=True,
                encrypt_properties=True,
                layered_strings=True,
                string_shards=3,
                string_decoys=6,
                noise=3,
                opaque_predicates=True,
                number_depth=5,
                bitwise_numbers=True,
                virtualize=True,
            ),
        }
        selected = profiles[args.profile]
        noise = selected["noise"] if args.noise is None else args.noise
        config = Config(
            seed=args.seed,
            rename_locals=bool(selected["rename_locals"]) and not args.no_rename,
            encrypt_strings=bool(selected["encrypt_strings"]) and not args.no_strings,
            split_numbers=bool(selected["split_numbers"]) and not args.no_numbers,
            encrypt_properties=bool(selected["encrypt_properties"]) and not args.no_properties,
            layered_strings=(bool(selected["layered_strings"]) or args.layered_strings)
            and not args.no_layered_strings,
            string_shards=int(selected["string_shards"] if args.string_shards is None else args.string_shards),
            string_decoys=int(selected["string_decoys"] if args.string_decoys is None else args.string_decoys),
            noise=int(noise),
            opaque_predicates=(bool(selected["opaque_predicates"]) or args.opaque_predicates)
            and not args.no_opaque_predicates,
            mask_literals=not args.no_literal_masking,
            number_depth=int(selected["number_depth"] if args.number_depth is None else args.number_depth),
            bitwise_numbers=(bool(selected["bitwise_numbers"]) or args.bitwise_numbers)
            and not args.no_bitwise_numbers,
            watermark=args.watermark,
            preserve_names=tuple(args.preserve),
            fail_on_parse_error=args.strict_parser,
            virtualize=(bool(selected["virtualize"]) or args.vm) and not args.no_vm,
            vm_encrypt_constants=not args.no_vm_constant_encryption,
            vm_shuffle_constants=not args.no_vm_constant_shuffle,
            preserve_layout=args.preserve_layout,
            process_protection_macros=not args.no_protection_macros,
            function_policies=tuple(args.function_policy),
            vm_source_maps=not args.no_vm_source_maps,
            vm_integrity=not args.no_vm_integrity,
            vm_optimize=not args.no_vm_optimize,
            vm_superoperators=not args.no_vm_superoperators,
            vm_polymorphic=not args.no_vm_polymorphic,
            vm_compress=not args.no_vm_compression,
            vm_architecture=args.vm_architecture,
            external_key_secret=args.external_key_secret.read_bytes() if args.external_key_secret else None,
            license_project=args.license_project,
            license_key_id=args.license_key_id,
            license_resolver=args.license_resolver,
            encrypt_all_vm=args.encrypt_all_vm,
            manifest_signing_secret=args.manifest_signing_secret.read_bytes() if args.manifest_signing_secret else None,
            manifest_signing_key_id=args.manifest_signing_key_id,
            helper_storage=args.helper_storage,
            register_reserve=max(0, args.register_reserve),
        )
        result = obfuscate(source, config)

        if args.official_validate or args.adaptive:
            compiler = find_compiler(args.luau_compiler)
            if compiler is None:
                raise RuntimeError("official Luau compiler not found; provide --luau-compiler")
            valid, diagnostic = validate_source(result.source, compiler)
            if args.adaptive and not valid:
                # Degrade one component at a time and keep successful VM/source
                # protection instead of jumping directly to a weak profile.
                current = replace(config, helper_storage="global")
                candidates = [("global_helpers", current)]
                steps = [
                    ("no_noise", dict(noise=0, opaque_predicates=False)),
                    ("no_decoys", dict(string_decoys=0)),
                    ("flat_string_vault", dict(layered_strings=False, string_shards=1, string_decoys=0)),
                    ("no_property_vault", dict(encrypt_properties=False)),
                    ("shallow_numbers", dict(number_depth=1, bitwise_numbers=False)),
                    ("no_literal_masks", dict(mask_literals=False)),
                    ("no_string_vault", dict(encrypt_strings=False, encrypt_properties=False, layered_strings=False, string_shards=1, string_decoys=0)),
                    ("no_number_masks", dict(split_numbers=False, bitwise_numbers=False)),
                    ("no_vm", dict(virtualize=False)),
                    ("rename_only", dict(virtualize=False, encrypt_properties=False, encrypt_strings=False, layered_strings=False, string_shards=1, string_decoys=0, split_numbers=False, bitwise_numbers=False, mask_literals=False, noise=0, opaque_predicates=False)),
                    ("branding_only", dict(virtualize=False, encrypt_properties=False, encrypt_strings=False, layered_strings=False, string_shards=1, string_decoys=0, split_numbers=False, bitwise_numbers=False, mask_literals=False, rename_locals=False, noise=0, opaque_predicates=False)),
                ]
                for tier, changes in steps:
                    current = replace(current, **changes)
                    candidates.append((tier, current))
                attempts: list[str] = []
                for tier, candidate in candidates:
                    candidate_result = obfuscate(source, candidate)
                    ok, error = validate_source(candidate_result.source, compiler)
                    if ok:
                        result = candidate_result
                        result.manifest["adaptive_tier"] = tier
                        result.manifest["official_luau_validated"] = True
                        result.warnings.append(f"adaptive compatibility tier selected: {tier}")
                        valid = True
                        break
                    attempts.append(f"{tier}: {error.splitlines()[0] if error else 'compile failed'}")
                if not valid:
                    raise RuntimeError("official Luau validation failed at every adaptive tier: " + "; ".join(attempts))
            elif not valid:
                raise RuntimeError(f"official Luau validation failed: {diagnostic}")
            else:
                result.manifest["official_luau_validated"] = True
    except FileNotFoundError:
        print(f"error: input not found: {args.input}", file=sys.stderr)
        return 2
    except (OSError, UnicodeError, ValueError, LexError, ParseError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    output = args.output or args.input.with_name(args.input.stem + ".obf.luau")
    if args.stdout:
        sys.stdout.write(result.source)
        if not result.source.endswith("\n"):
            sys.stdout.write("\n")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(result.source, encoding="utf-8")
        print(f"wrote {output}")

    manifest_path = args.manifest
    if manifest_path:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(result.manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {manifest_path}")

    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
