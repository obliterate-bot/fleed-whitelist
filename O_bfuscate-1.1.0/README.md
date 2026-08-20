# O_bfuscate 1.1

O_bfuscate is an offline, deterministic, Luau-aware source-protection tool. Version 1.1 focuses on large-script correctness and compatibility while retaining the hybrid VM and optional self-hosted keyed-function service introduced in 1.0.

Obfuscation only raises analysis cost. Do not place credentials, authoritative security decisions, or server secrets in client code.

## 1.1 additions

- Register-pressure estimation before code generation.
- Automatic global helper storage for chunks close to Luau's 200-register ceiling.
- Function-scoped string-vault and VM implementation state.
- Zero-persistent-local noise, watermark, and bitwise-number helpers.
- `WYNF_JIT`, `WYNF_JIT_MAX`, `WYNF_INLINE`, and `WYNF_NO_VIRTUALIZE` compatibility wrappers.
- Correct handling of contextual `type` as a runtime global.
- Correct VM statement boundaries for calls followed by later assignments.
- Component-level adaptive degradation that retains working VM and source transforms.
- Manifest fields for estimated chunk pressure, remaining helper budget, and selected helper storage.

## Installation

```bash
python -m pip install .
```

The provided wheel includes official Luau tools for Linux x86-64.

## Large-script build

```bash
o-bfuscate input.luau \
  --profile dense \
  --adaptive \
  --official-validate \
  --manifest build.json \
  -o output.obf.luau
```

`--helper-storage auto` is the default. It keeps helpers local on ordinary chunks and uses randomized globals when estimated active locals leave insufficient temporary-register headroom. Use `--helper-storage local` or `global` to override it.

## Compatibility macros

O_bfuscate recognizes its native `OBF_*` wrappers and the following wYnFuscate-style identity wrappers:

| Wrapper | O_bfuscate policy |
|---|---|
| `WYNF_JIT` | Light VM where the wrapper names a top-level function |
| `WYNF_JIT_MAX` | Hot/native |
| `WYNF_INLINE` | Hot/native |
| `WYNF_NO_VIRTUALIZE` | No VM |

Anonymous callback wrappers are removed as identity layers. If their enclosing function is virtualized, the nested closure is protected by that VM prototype.

## Security limits

Global helper storage intentionally trades namespace cleanliness for compiler headroom. Names are generated against all source identifiers, but code that dynamically enumerates globals can still observe them. Official compiler validation remains the source of truth; the register estimator is conservative and only selects a storage strategy.

## Whitelist dashboard

The self-hosted license service includes an authenticated dashboard for issuing
keys, enforcing expiration dates, binding keys to HWIDs, resetting device
bindings, publishing protected builds, and generating keyed loadstring loaders.

Create the database and its first project:

```bash
o-bfuscate-license init licenses.json \
  --project my-script \
  --secret-out my-script.secret
```

The command prints a dashboard admin token. Start the service:

```bash
o-bfuscate-license serve licenses.json --host 127.0.0.1 --port 8787
```

Open `http://127.0.0.1:8787/dashboard/` and sign in with the printed token.
The token is stored in browser session storage and is cleared when the tab is
closed. You can retrieve or rotate it from the host:

```bash
o-bfuscate-license admin-token licenses.json
o-bfuscate-license admin-token licenses.json --rotate
```

### Publish a gated build

For the strongest delivery boundary, store the protected Luau source as an
inline release. It is returned only after the loader's key, expiration, and
HWID checks pass:

```bash
o-bfuscate input.luau \
  --profile dense \
  --external-key-secret my-script.secret \
  --license-project my-script \
  -o output.obf.luau

o-bfuscate-license publish licenses.json \
  --project my-script \
  --build-id v1.0.0 \
  --artifact-file output.obf.luau
```

You can also publish an `https://` artifact URL in the dashboard or with
`--artifact-url`. The service proxies remote artifacts so the generated loader
does not expose the upstream URL.

The Loaders page generates both readable and one-line Luau loaders. A
HWID-locked key uses `RbxAnalyticsService:GetClientId()` as its device ID and
binds to the first successful request. Resetting the HWID makes the next device
the new owner.

### CLI key management

Dashboard operations remain available from the CLI:

```bash
# Strict HWID binding with a 30-day expiration
o-bfuscate-license issue licenses.json \
  --project my-script \
  --days 30 \
  --hwid-lock yes \
  --label "Customer A"

o-bfuscate-license reset-hwid licenses.json obf1_your_key
o-bfuscate-license revoke licenses.json obf1_your_key --reason "refunded"
```

New license records keep a SHA-256 lookup hash, a keyed hash of the bound HWID,
and an authenticated encrypted key copy for administrator-only reveal and
loader generation. Keep `licenses.json`, project secrets, and the admin token
private, place the service behind HTTPS for remote use, and back up the
database before rotating or migrating it.
