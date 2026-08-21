#!/usr/bin/env node
// bin/obfuscate.js
// CLI for O_bfuscate V2

const fs = require('fs');
const path = require('path');
const { obfuscate, PRESETS } = require('../src/engine');

const args = process.argv.slice(2);

function printHelp() {
  console.log(`
\x1b[36m=========================================================\x1b[0m
\x1b[1m\x1b[35m  O_bfuscate V2\x1b[0m - High-Performance Luau Obfuscator
  \x1b[90mProtected by O_bfuscate v2, created by Undix\x1b[0m
\x1b[36m=========================================================\x1b[0m

\x1b[1mUSAGE:\x1b[0m
  node bin/obfuscate.js <input.luau> [options]

\x1b[1mOPTIONS:\x1b[0m
  -o, --output <path>       Output file destination (default: <input>.obf.luau)
  -p, --preset <preset>     Obfuscation preset:
                            - \x1b[32mmax-performance\x1b[0m (0.0% runtime loss, native NCG) [DEFAULT]
                            - \x1b[33mbalanced\x1b[0m (CFF + buffer strings + MBA)
                            - \x1b[31multra-secure\x1b[0m (Hardened deep CFF + confusables)
  --no-native               Disable --!native and --!optimize 2 headers
  --mangler <mode>          Mangler mode: hex_hash | barcode | confusables | minified
  --watermark <text>        Custom watermark comment
  -h, --help                Show this help message

\x1b[1mEXAMPLES:\x1b[0m
  node bin/obfuscate.js main.luau -o dist/main.luau
  node bin/obfuscate.js script.luau --preset ultra-secure
`);
}

if (args.length === 0 || args.includes('-h') || args.includes('--help')) {
  printHelp();
  process.exit(0);
}

let inputFile = null;
let outputFile = null;
let preset = 'max-performance';
let manglerMode = null;
let watermark = 'protected by O_bfuscate v2, created by Undix';
let nativeDirective = true;

for (let i = 0; i < args.length; i++) {
  const arg = args[i];
  if (arg === '-o' || arg === '--output') {
    outputFile = args[++i];
  } else if (arg === '-p' || arg === '--preset') {
    preset = args[++i];
  } else if (arg === '--mangler') {
    manglerMode = args[++i];
  } else if (arg === '--watermark') {
    watermark = args[++i];
  } else if (arg === '--no-native') {
    nativeDirective = false;
  } else if (!inputFile && !arg.startsWith('-')) {
    inputFile = arg;
  }
}

if (!inputFile) {
  console.error('\x1b[31m[ERROR] Please specify an input Luau script file.\x1b[0m');
  process.exit(1);
}

if (!fs.existsSync(inputFile)) {
  console.error(`\x1b[31m[ERROR] File not found: ${inputFile}\x1b[0m`);
  process.exit(1);
}

if (!outputFile) {
  const parsed = path.parse(inputFile);
  outputFile = path.join(parsed.dir, `${parsed.name}.obf${parsed.ext || '.luau'}`);
}

try {
  const source = fs.readFileSync(inputFile, 'utf8');
  console.log(`\x1b[36m[*] Obfuscating\x1b[0m: ${inputFile}`);
  console.log(`\x1b[36m[*] Preset\x1b[0m: ${preset}`);

  const options = {
    preset,
    watermark,
    nativeDirective
  };
  if (manglerMode) options.manglerMode = manglerMode;

  const result = obfuscate(source, options);

  fs.writeFileSync(outputFile, result.code, 'utf8');

  console.log(`\x1b[32m[✓] Successfully Obfuscated!\x1b[0m`);
  console.log(`\x1b[90m---------------------------------------------------\x1b[0m`);
  console.log(`  \x1b[1mOutput File:\x1b[0m         ${outputFile}`);
  console.log(`  \x1b[1mOriginal Size:\x1b[0m       ${result.stats.originalSize} bytes`);
  console.log(`  \x1b[1mObfuscated Size:\x1b[0m     ${result.stats.obfuscatedSize} bytes (${result.stats.ratio})`);
  console.log(`  \x1b[1mTime Taken:\x1b[0m          ${result.stats.timeMs} ms`);
  console.log(`  \x1b[1mSecurity Score:\x1b[0m      ${result.stats.securityRating}/100`);
  console.log(`  \x1b[1mPerformance:\x1b[0m         \x1b[32m${result.stats.performanceRating}\x1b[0m`);
  console.log(`\x1b[90m---------------------------------------------------\x1b[0m`);
} catch (err) {
  console.error(`\x1b[31m[FAILURE] Obfuscation error:\x1b[0m ${err.message}`);
  console.error(err.stack);
  process.exit(1);
}
