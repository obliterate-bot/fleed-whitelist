# Changelog

## Unreleased

- Added an authenticated, responsive whitelist dashboard with overview
  metrics, audit activity, project-aware license tables, and key search.
- Added strict HWID-on-first-use locking, dashboard HWID resets, editable
  expiration dates, key revoke/restore controls, and masked key display.
- Added gated inline or proxied release delivery through
  `/v1/loader/<project>` and one-line/readable loadstring generation.
- Added dashboard release publishing, admin-token rotation, exact expiration
  and HWID policy CLI flags, and schema-1 database migration.

## 1.1.0

- Added pre-emission chunk register-pressure estimation.
- Added `auto`, `local`, and `global` persistent helper storage.
- Collapsed each string vault into one persistent root reference and moved decoder internals into its constructor closure.
- Allowed the VM root to use global storage on register-constrained chunks.
- Scoped disposable watermark and noise locals; removed the persistent `bit32.bxor` alias.
- Added wYnFuscate wrapper compatibility and the `WYNF_OBFUSCATED` build guard.
- Fixed contextual `type` handling in the source analyzer and VM compiler.
- Fixed false assignment detection after function and method calls without semicolons.
- Replaced coarse adaptive tiers with cumulative, component-level degradation.
- Added large-chunk, VM statement-boundary, macro-compatibility, and runtime-equivalence tests.
