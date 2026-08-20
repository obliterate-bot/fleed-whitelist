from __future__ import annotations

from dataclasses import dataclass
import hashlib
import random
import secrets
from typing import Iterable

from .lexer import LexError, TokenKind, lex
from .budget import estimate_register_budget
from .names import NameGenerator
from .licensing import sign_manifest
from .macros import FunctionPolicy, process_macros
from .parser import Analysis, ParseError, analyze
from .vm import build_vm_backend
from .transforms import (
    BuildArtifacts,
    add_literal_masking,
    add_noise,
    add_number_splitting,
    add_string_vault,
    add_watermark,
    build_manifest,
    minify_fragment,
    minify_tokens,
    render_tokens_preserving_trivia,
)


@dataclass(slots=True)
class Config:
    seed: int | None = None
    rename_locals: bool = True
    encrypt_strings: bool = True
    split_numbers: bool = True
    encrypt_properties: bool = True
    layered_strings: bool = False
    string_shards: int = 1
    string_decoys: int = 0
    noise: int = 1
    opaque_predicates: bool = False
    mask_literals: bool = True
    number_depth: int = 2
    bitwise_numbers: bool = False
    watermark: str | None = None
    preserve_names: tuple[str, ...] = ()
    fail_on_parse_error: bool = False
    virtualize: bool = False
    vm_encrypt_constants: bool = True
    vm_shuffle_constants: bool = True
    preserve_layout: bool = False
    process_protection_macros: bool = True
    function_policies: tuple[str, ...] = ()
    vm_source_maps: bool = True
    vm_integrity: bool = True
    vm_optimize: bool = True
    vm_superoperators: bool = True
    vm_polymorphic: bool = True
    vm_compress: bool = True
    vm_architecture: str = "auto"
    external_key_secret: bytes | None = None
    license_project: str = "default"
    license_key_id: str = "default"
    license_resolver: str = "__O_LICENSE_RESOLVE"
    encrypt_all_vm: bool = False
    manifest_signing_secret: bytes | None = None
    manifest_signing_key_id: str = "default"
    helper_storage: str = "auto"
    register_limit: int = 200
    register_reserve: int = 12


@dataclass(slots=True)
class Result:
    source: str
    manifest: dict[str, object]
    warnings: list[str]


def obfuscate(source: str, config: Config | None = None) -> Result:
    config = config or Config()
    original_source = source
    original_bytes = source.encode("utf-8")
    seed = config.seed if config.seed is not None else secrets.randbits(63)
    rng = random.Random(seed)
    build_material = (seed & ((1 << 64) - 1)).to_bytes(8, "big") + b"\0" + original_bytes
    build_id = hashlib.blake2s(build_material, digest_size=8).hexdigest()
    if config.external_key_secret is not None and len(config.external_key_secret) < 32:
        raise ValueError("external function-key secret must contain at least 32 bytes")
    if config.encrypt_all_vm and config.external_key_secret is None:
        raise ValueError("encrypt_all_vm requires an external function-key secret")
    if config.encrypt_all_vm and not config.virtualize:
        raise ValueError("encrypt_all_vm requires VM virtualization")
    if config.manifest_signing_secret is not None and len(config.manifest_signing_secret) < 16:
        raise ValueError("manifest signing secret must contain at least 16 bytes")
    warnings: list[str] = []
    vm_functions = 0
    vm_instructions = 0
    vm_constants = 0
    vm_constant_bytes = 0
    vm_captures = 0
    vm_iterators = 0
    vm_prototypes = 0
    vm_nested_closures = 0
    vm_vararg_functions = 0
    vm_optimized = 0
    vm_superinstructions = 0
    vm_integrity_checks = 0
    vm_source_mapped = 0
    vm_external_keyed = 0
    vm_writable_upvalues = 0
    vm_plain_code_bytes = 0
    vm_packed_code_bytes = 0
    vm_compressed_functions = 0
    vm_light_functions = 0
    vm_full_functions = 0
    vm_architecture = "none"
    macro_count = 0
    policies: dict[str, FunctionPolicy] = {}
    force_strings = False
    force_numbers = False
    if config.process_protection_macros:
        macro_result = process_macros(source)
        source = macro_result.prelude + macro_result.source
        policies.update(macro_result.policies)
        warnings.extend(macro_result.warnings)
        macro_count = macro_result.expanded_macros
        force_strings = macro_result.forced_strings
        force_numbers = macro_result.forced_numbers
    for override in config.function_policies:
        if "=" not in override:
            warnings.append(f"ignored invalid function policy {override!r}")
            continue
        function_name, value = override.split("=", 1)
        mode, separator, key_id = value.partition(":")
        mode = mode.strip().lower()
        aliases = {"vm": "full", "full-vm": "full", "light-vm": "light", "native": "hot", "novm": "no-vm"}
        mode = aliases.get(mode, mode)
        if mode not in {"auto", "no-vm", "hot", "light", "full", "encrypt"}:
            warnings.append(f"ignored invalid function policy mode {mode!r} for {function_name!r}")
            continue
        policies[function_name.strip()] = FunctionPolicy(mode=mode, key_id=key_id.strip() if separator else None)

    effective_encrypt_strings = config.encrypt_strings or force_strings
    effective_split_numbers = config.split_numbers or force_numbers
    budget = estimate_register_budget(
        source, limit=max(32, int(config.register_limit)), reserve=max(0, int(config.register_reserve))
    )
    requested_helper_storage = config.helper_storage.lower().strip()
    helper_storage = requested_helper_storage
    if helper_storage not in {"auto", "local", "global"}:
        raise ValueError("helper_storage must be auto, local, or global")
    planned_helpers = int(config.virtualize) + int(effective_encrypt_strings)
    if helper_storage == "auto":
        helper_storage = (
            "global"
            if planned_helpers > 0 and budget.available_for_helpers < planned_helpers + 1
            else "local"
        )
    if helper_storage == "global":
        reason = "register-aware auto selection" if requested_helper_storage == "auto" else "explicit configuration"
        warnings.append(
            f"global helper storage selected ({reason}): estimated peak {budget.estimated_peak_locals}/{budget.limit}"
        )

    if config.virtualize:
        vm_tokens = lex(source)
        vm_used = {token.text for token in vm_tokens if token.kind == TokenKind.IDENT}
        vm_names = NameGenerator(rng, vm_used)
        vm_build = build_vm_backend(
            source,
            rng,
            vm_names,
            encrypt_constants=config.vm_encrypt_constants,
            shuffle_constants=config.vm_shuffle_constants,
            policies=policies,
            vm_source_maps=config.vm_source_maps,
            vm_integrity=config.vm_integrity,
            vm_optimize=config.vm_optimize,
            vm_superoperators=config.vm_superoperators,
            vm_polymorphic=config.vm_polymorphic,
            vm_compress=config.vm_compress,
            vm_architecture=config.vm_architecture,
            external_key_secret=config.external_key_secret,
            license_project=config.license_project,
            license_key_id=config.license_key_id,
            license_resolver=config.license_resolver,
            build_id=build_id,
            encrypt_all=config.encrypt_all_vm,
            helper_storage=helper_storage,
        )
        warnings.extend(vm_build.warnings)
        if vm_build.replacements:
            for start, end, replacement in sorted(vm_build.replacements, reverse=True):
                source = source[:start] + replacement + source[end:]
            source = vm_build.prelude + source
            vm_functions = vm_build.virtualized_functions
            vm_instructions = vm_build.instruction_count
            vm_constants = vm_build.constant_count
            vm_constant_bytes = vm_build.encrypted_constant_bytes
            vm_captures = vm_build.captured_upvalues
            vm_iterators = vm_build.iterator_loops
            vm_prototypes = vm_build.virtualized_prototypes
            vm_nested_closures = vm_build.nested_closures
            vm_vararg_functions = vm_build.vararg_functions
            vm_optimized = vm_build.optimized_instructions
            vm_superinstructions = vm_build.superinstructions
            vm_integrity_checks = vm_build.integrity_checks
            vm_source_mapped = vm_build.source_mapped_functions
            vm_external_keyed = vm_build.externally_keyed_functions
            vm_writable_upvalues = vm_build.writable_upvalues
            vm_plain_code_bytes = vm_build.plain_code_bytes
            vm_packed_code_bytes = vm_build.packed_code_bytes
            vm_compressed_functions = vm_build.compressed_functions
            vm_light_functions = vm_build.light_functions
            vm_full_functions = vm_build.full_functions
            vm_architecture = vm_build.vm_architecture

    tokens = lex(source)
    analysis: Analysis | None = None
    needs_analysis = config.rename_locals or effective_encrypt_strings or effective_split_numbers or config.mask_literals
    if needs_analysis:
        try:
            analysis = analyze(tokens, rng, config.preserve_names)
        except ParseError as exc:
            if config.fail_on_parse_error:
                raise
            warnings.append(f"AST-safe transforms disabled: {exc}")
            analysis = None

    safe_passthrough = analysis is None and needs_analysis and vm_functions == 0
    used = {token.text for token in tokens if token.kind == TokenKind.IDENT}
    names = NameGenerator(rng, used)
    artifacts = BuildArtifacts()

    if analysis is not None:
        if config.rename_locals:
            artifacts.replacements.update(analysis.replacements)
        if effective_encrypt_strings:
            add_string_vault(
                tokens,
                analysis,
                artifacts,
                rng,
                names,
                encrypt_properties=config.encrypt_properties,
                layered=config.layered_strings,
                shards=config.string_shards,
                decoys=config.string_decoys,
                helper_storage=helper_storage,
            )
        if effective_split_numbers:
            add_number_splitting(
                tokens,
                analysis,
                artifacts,
                rng,
                names,
                depth=config.number_depth,
                bitwise=config.bitwise_numbers,
            )
        if config.mask_literals:
            add_literal_masking(tokens, analysis, artifacts, rng)

    banner = "-- Protected by O_bfuscate, created by undix/O_bliterate\n"
    if safe_passthrough:
        # Unsupported grammar must never be aggressively minified. Trivia can be
        # semantically relevant in evolving Luau syntax, so preserve the exact
        # input and add only the requested branding comment.
        if original_source.startswith("--!"):
            line_end = original_source.find("\n")
            if line_end >= 0:
                output = original_source[:line_end + 1] + banner + original_source[line_end + 1:]
            else:
                output = original_source + "\n" + banner
        else:
            output = banner + original_source
    else:
        add_watermark(artifacts, config.watermark, build_id, names)
        add_noise(artifacts, rng, names, config.noise, opaque_predicates=config.opaque_predicates)
        if config.preserve_layout:
            body = render_tokens_preserving_trivia(tokens, artifacts.replacements)
            prelude = "".join(artifacts.prelude_parts)
            protected = prelude + body
            if protected.startswith("--!"):
                line_end = protected.find("\n")
                output = protected[:line_end + 1] + banner + protected[line_end + 1:]
            else:
                output = banner + protected
        else:
            body, directives = minify_tokens(tokens, artifacts.replacements)
            prelude = minify_fragment("".join(artifacts.prelude_parts)) if artifacts.prelude_parts else ""
            prefix = "\n".join(directives)
            if prefix:
                prefix += "\n"
            if prelude:
                output = prefix + banner + prelude + body
            else:
                output = prefix + banner + body

    # Validate the generated source lexically. This catches accidental token fusion
    # and malformed generated literals even when a Luau runtime is unavailable.
    try:
        lex(output)
    except LexError as exc:
        raise RuntimeError(f"generated invalid Luau token stream: {exc}") from exc

    config_dict = {
        "rename_locals": config.rename_locals,
        "encrypt_strings": config.encrypt_strings,
        "split_numbers": config.split_numbers,
        "encrypt_properties": config.encrypt_properties,
        "layered_strings": config.layered_strings,
        "string_shards": config.string_shards,
        "string_decoys": config.string_decoys,
        "noise": config.noise,
        "opaque_predicates": config.opaque_predicates,
        "mask_literals": config.mask_literals,
        "number_depth": config.number_depth,
        "bitwise_numbers": config.bitwise_numbers,
        "watermark": config.watermark is not None,
        "preserve_names": list(config.preserve_names),
        "virtualize": config.virtualize,
        "vm_encrypt_constants": config.vm_encrypt_constants,
        "vm_shuffle_constants": config.vm_shuffle_constants,
        "vm_source_maps": config.vm_source_maps,
        "vm_integrity": config.vm_integrity,
        "vm_optimize": config.vm_optimize,
        "vm_superoperators": config.vm_superoperators,
        "vm_polymorphic": config.vm_polymorphic,
        "vm_compress": config.vm_compress,
        "vm_architecture": config.vm_architecture,
        "function_policies": list(config.function_policies),
        "protection_macros": config.process_protection_macros,
        "external_keyed": config.external_key_secret is not None,
        "license_project": config.license_project if config.external_key_secret is not None else None,
        "license_key_id": config.license_key_id if config.external_key_secret is not None else None,
        "license_resolver": config.license_resolver if config.external_key_secret is not None else None,
        "encrypt_all_vm": config.encrypt_all_vm,
        "manifest_signed": config.manifest_signing_secret is not None,
        "helper_storage": helper_storage,
        "register_limit": budget.limit,
        "register_reserve": budget.reserve,
        "branding": "Protected by O_bfuscate, created by undix/O_bliterate",
        "preserve_layout": config.preserve_layout,
    }
    manifest = build_manifest(
        input_bytes=original_bytes,
        output_bytes=output.encode("utf-8"),
        build_id=build_id,
        seed=seed,
        config=config_dict,
        analysis=analysis,
        artifacts=artifacts,
        warnings=warnings,
    )
    manifest["stats"]["virtualized_functions"] = vm_functions
    manifest["stats"]["virtual_instructions"] = vm_instructions
    manifest["stats"]["virtual_constants"] = vm_constants
    manifest["stats"]["encrypted_virtual_constant_bytes"] = vm_constant_bytes
    manifest["stats"]["captured_virtual_upvalues"] = vm_captures
    manifest["stats"]["virtualized_iterator_loops"] = vm_iterators
    manifest["stats"]["virtualized_prototypes"] = vm_prototypes
    manifest["stats"]["nested_virtual_closures"] = vm_nested_closures
    manifest["stats"]["virtualized_vararg_functions"] = vm_vararg_functions
    manifest["stats"]["optimized_virtual_instructions"] = vm_optimized
    manifest["stats"]["virtual_superinstructions"] = vm_superinstructions
    manifest["stats"]["virtual_integrity_checks"] = vm_integrity_checks
    manifest["stats"]["source_mapped_virtual_functions"] = vm_source_mapped
    manifest["stats"]["externally_keyed_virtual_functions"] = vm_external_keyed
    manifest["stats"]["writable_virtual_upvalues"] = vm_writable_upvalues
    manifest["stats"]["plain_virtual_code_bytes"] = vm_plain_code_bytes
    manifest["stats"]["packed_virtual_code_bytes"] = vm_packed_code_bytes
    manifest["stats"]["compressed_virtual_functions"] = vm_compressed_functions
    manifest["stats"]["light_virtual_functions"] = vm_light_functions
    manifest["stats"]["full_virtual_functions"] = vm_full_functions
    manifest["stats"]["virtual_code_bytes_saved"] = max(0, vm_plain_code_bytes - vm_packed_code_bytes)
    manifest["stats"]["expanded_protection_macros"] = macro_count
    manifest["stats"]["estimated_peak_chunk_locals"] = budget.estimated_peak_locals
    manifest["stats"]["estimated_root_chunk_locals"] = budget.root_locals
    manifest["stats"]["helper_register_budget"] = budget.available_for_helpers
    manifest["vm_architecture"] = vm_architecture
    manifest["helper_storage"] = helper_storage
    if config.manifest_signing_secret is not None:
        manifest = sign_manifest(manifest, config.manifest_signing_secret, config.manifest_signing_key_id)
    return Result(output, manifest, warnings)
