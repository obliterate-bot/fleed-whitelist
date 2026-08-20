# Protection macros

Native `OBF_*` macros remain identity functions before protection. Version 1.1 also accepts `WYNF_JIT`, `WYNF_JIT_MAX`, `WYNF_INLINE`, and `WYNF_NO_VIRTUALIZE` wrappers.

Named top-level forms such as `local f = WYNF_JIT(function() ... end)` and `f = WYNF_INLINE(function() ... end)` are converted to ordinary function definitions and assigned a policy. Arbitrary callback wrappers are stripped without inventing a top-level function policy.

When any `WYNF_*` wrapper is processed, the generated chunk sets `WYNF_OBFUSCATED=true` before the source so conventional development-stub blocks remain disabled.
